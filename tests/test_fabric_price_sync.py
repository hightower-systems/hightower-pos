import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from pos_service.clients.fabric import FabricClientError
from pos_service.models import POSPrice
from pos_service.services.fabric_price_sync import run_loop, sync_once


class FakeFabric:
    def __init__(
        self,
        rows: list[tuple[str, int]] | None = None,
        *,
        raise_error: str | None = None,
    ) -> None:
        self._rows = rows or []
        self._raise_error = raise_error
        self.is_mock = False
        self.calls = 0

    def fetch_price_catalog(self) -> list[tuple[str, int]]:
        self.calls += 1
        if self._raise_error is not None:
            raise FabricClientError(self._raise_error)
        return list(self._rows)


def _read_prices(db_factory: sessionmaker[Session]) -> dict[str, int]:
    with db_factory() as session:
        return {
            row.sku: row.unit_price_cents
            for row in session.execute(select(POSPrice)).scalars().all()
        }


def test_sync_once_inserts_new_rows(engine: Engine, db_factory: sessionmaker[Session]):
    client = FakeFabric([("ROD-100", 19999), ("REEL-200", 24500), ("LINE-300", 1499)])

    result = sync_once(client, db_factory)

    assert result.rows_fetched == 3
    assert result.rows_upserted == 3
    assert result.error is None
    assert _read_prices(db_factory) == {
        "ROD-100": 19999,
        "REEL-200": 24500,
        "LINE-300": 1499,
    }


def test_sync_once_updates_existing_row_price(
    engine: Engine, db_factory: sessionmaker[Session]
):
    with db_factory() as session:
        session.add(POSPrice(sku="ROD-100", unit_price_cents=10000))
        session.commit()

    client = FakeFabric([("ROD-100", 19999)])
    result = sync_once(client, db_factory)

    assert result.rows_upserted == 1
    assert _read_prices(db_factory) == {"ROD-100": 19999}


def test_sync_once_empty_catalog_is_noop(
    engine: Engine, db_factory: sessionmaker[Session]
):
    client = FakeFabric([])

    result = sync_once(client, db_factory)

    assert result.rows_fetched == 0
    assert result.rows_upserted == 0
    assert result.error is None
    assert _read_prices(db_factory) == {}


def test_sync_once_wraps_fabric_error_without_writing(
    engine: Engine, db_factory: sessionmaker[Session]
):
    client = FakeFabric(raise_error="connection timeout")

    result = sync_once(client, db_factory)

    assert result.rows_fetched == 0
    assert result.rows_upserted == 0
    assert result.error == "connection timeout"
    assert _read_prices(db_factory) == {}


def test_sync_once_batches_large_catalog(
    engine: Engine, db_factory: sessionmaker[Session]
):
    rows = [(f"SKU-{i:05d}", 100 + i) for i in range(2500)]
    client = FakeFabric(rows)

    result = sync_once(client, db_factory)

    assert result.rows_upserted == 2500
    prices = _read_prices(db_factory)
    assert len(prices) == 2500
    assert prices["SKU-00000"] == 100
    assert prices["SKU-02499"] == 2599


@pytest.mark.asyncio
async def test_run_loop_iterates_until_cancelled(
    engine: Engine, db_factory: sessionmaker[Session]
):
    client = FakeFabric([("ROD-100", 19999)])
    task = asyncio.create_task(run_loop(client, db_factory, interval_s=0))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert client.calls >= 2
    assert _read_prices(db_factory) == {"ROD-100": 19999}


@pytest.mark.asyncio
async def test_run_loop_continues_through_fabric_errors(
    engine: Engine, db_factory: sessionmaker[Session]
):
    client = FakeFabric(raise_error="fabric is down")
    task = asyncio.create_task(run_loop(client, db_factory, interval_s=0))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert client.calls >= 2
