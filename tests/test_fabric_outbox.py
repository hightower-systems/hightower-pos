import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from pos_service.clients.fabric import FabricClientError
from pos_service.config import Settings
from pos_service.models import FabricOutboxEntry, POSTransaction
from pos_service.services.fabric_outbox import (
    MAX_ATTEMPTS,
    RETRY_SCHEDULE_SECONDS,
    DrainResult,
    build_payload,
    drain_once,
    enqueue,
)


def _make_settings() -> Settings:
    return Settings(
        windcave_currency="USD",
        windcave_device_id="AvidMax-Reg1",
    )


def _make_txn(db: Session, **overrides) -> POSTransaction:
    defaults = dict(
        id="txn-001",
        status="COMPLETE",
        txn_type="sale",
        cart_json=json.dumps(
            [
                {
                    "sku": "ROD-100",
                    "name": "Premium Fly Rod",
                    "warehouse_id": "WH-STORE",
                    "bin_id": "BIN-A1",
                    "quantity": 1,
                    "unit_price_cents": 19999,
                    "tax_cents": 1620,
                    "line_total_cents": 21619,
                }
            ]
        ),
        subtotal_cents=19999,
        tax_cents=1620,
        total_cents=21619,
        payment_method="card",
        sentry_so_id="SO-1",
        cashier_id="mike",
        terminal_id="TERM-1",
    )
    defaults.update(overrides)
    txn = POSTransaction(**defaults)
    db.add(txn)
    db.commit()
    return txn


class FakeWriter:
    is_mock = False

    def __init__(self, *, raise_error: str | None = None, fabric_so_id: str | None = None):
        self._raise_error = raise_error
        self._fabric_so_id = fabric_so_id
        self.calls: list[dict] = []

    async def write_sales_order(self, payload: dict) -> dict:
        self.calls.append(payload)
        if self._raise_error is not None:
            raise FabricClientError(self._raise_error)
        return {"fabric_so_id": self._fabric_so_id} if self._fabric_so_id else {}


def test_build_payload_carries_register_currency_and_lean_shape():
    txn = POSTransaction(
        id="txn-001",
        status="COMPLETE",
        txn_type="sale",
        cart_json=json.dumps([{"sku": "ROD-100", "quantity": 1}]),
        subtotal_cents=19999,
        tax_cents=1620,
        total_cents=21619,
        payment_method="card",
        sentry_so_id="SO-1",
        cashier_id="mike",
        terminal_id="TERM-1",
    )
    payload = build_payload(txn, settings=_make_settings())
    assert payload["external_so_ref"] == "txn-001"
    assert payload["sentry_so_id"] == "SO-1"
    assert payload["fulfillment_channel"] == "Store"
    assert payload["status"] == "shipped"
    assert payload["source"] == "POS"
    assert payload["register_id"] == "AvidMax-Reg1"
    assert payload["currency"] == "USD"
    assert payload["payment_method"] == "card"
    assert payload["lines"] == [{"sku": "ROD-100", "quantity": 1}]
    assert "card_brand" not in payload
    assert "card_last4" not in payload


def test_build_payload_for_refund_carries_parent_id_and_refund_type():
    txn = POSTransaction(
        id="refund-001",
        status="COMPLETE",
        txn_type="refund",
        parent_transaction_id="txn-original",
        cart_json="[]",
        subtotal_cents=19999,
        tax_cents=1620,
        total_cents=21619,
        payment_method="card",
        sentry_so_id="SO-R-1",
        cashier_id="mike",
        terminal_id="TERM-1",
    )
    payload = build_payload(txn, settings=_make_settings())
    assert payload["txn_type"] == "refund"
    assert payload["parent_transaction_id"] == "txn-original"
    assert payload["external_so_ref"] == "refund-001"


def test_enqueue_inserts_pending_row_in_caller_session(
    engine: Engine, db_factory: sessionmaker[Session]
):
    settings = _make_settings()
    with db_factory() as db:
        txn = _make_txn(db)
        entry = enqueue(db, txn, settings=settings)
        db.commit()
        assert entry.status == "PENDING"
        assert entry.attempt_count == 0

    with db_factory() as db:
        rows = list(db.execute(select(FabricOutboxEntry)).scalars())
        assert len(rows) == 1
        assert rows[0].pos_transaction_id == "txn-001"
        assert rows[0].status == "PENDING"
        payload = json.loads(rows[0].payload_json)
        assert payload["external_so_ref"] == "txn-001"


@pytest.mark.asyncio
async def test_drain_once_delivers_pending_entry_and_records_fabric_so_id(
    engine: Engine, db_factory: sessionmaker[Session]
):
    settings = _make_settings()
    with db_factory() as db:
        txn = _make_txn(db)
        enqueue(db, txn, settings=settings)
        db.commit()

    writer = FakeWriter(fabric_so_id="FAB-1")
    result = await drain_once(writer, db_factory)

    assert result.claimed == 1
    assert result.delivered == 1
    assert result.failed == 0
    assert result.dlq == 0
    assert len(writer.calls) == 1
    with db_factory() as db:
        entry = db.execute(select(FabricOutboxEntry)).scalar_one()
        assert entry.status == "DELIVERED"
        assert entry.fabric_so_id == "FAB-1"
        assert entry.last_error is None


@pytest.mark.asyncio
async def test_drain_once_skips_entries_not_yet_due(
    engine: Engine, db_factory: sessionmaker[Session]
):
    settings = _make_settings()
    with db_factory() as db:
        txn = _make_txn(db)
        entry = enqueue(db, txn, settings=settings)
        entry.next_attempt_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(
            seconds=60
        )
        db.commit()

    writer = FakeWriter()
    result = await drain_once(writer, db_factory)
    assert result.claimed == 0
    assert writer.calls == []


@pytest.mark.asyncio
async def test_drain_once_failure_schedules_next_retry_with_backoff(
    engine: Engine, db_factory: sessionmaker[Session]
):
    settings = _make_settings()
    with db_factory() as db:
        txn = _make_txn(db)
        enqueue(db, txn, settings=settings)
        db.commit()

    writer = FakeWriter(raise_error="503 service unavailable")
    result = await drain_once(writer, db_factory)
    assert result.delivered == 0
    assert result.failed == 1
    assert result.dlq == 0

    with db_factory() as db:
        entry = db.execute(select(FabricOutboxEntry)).scalar_one()
        assert entry.status == "PENDING"
        assert entry.attempt_count == 1
        assert entry.last_error == "503 service unavailable"
        wait = (entry.next_attempt_at - datetime.now(UTC).replace(tzinfo=None))
        assert wait.total_seconds() >= RETRY_SCHEDULE_SECONDS[1] - 1


@pytest.mark.asyncio
async def test_drain_once_flips_to_dlq_after_max_attempts(
    engine: Engine, db_factory: sessionmaker[Session]
):
    settings = _make_settings()
    with db_factory() as db:
        txn = _make_txn(db)
        entry = enqueue(db, txn, settings=settings)
        entry.attempt_count = MAX_ATTEMPTS - 1
        db.commit()

    writer = FakeWriter(raise_error="still down")
    result = await drain_once(writer, db_factory)
    assert result.dlq == 1
    assert result.failed == 0

    with db_factory() as db:
        entry = db.execute(select(FabricOutboxEntry)).scalar_one()
        assert entry.status == "DLQ"
        assert entry.attempt_count == MAX_ATTEMPTS


@pytest.mark.asyncio
async def test_drain_once_with_no_pending_entries_returns_zeroes(
    engine: Engine, db_factory: sessionmaker[Session]
):
    writer = FakeWriter()
    result = await drain_once(writer, db_factory)
    assert isinstance(result, DrainResult)
    assert result.claimed == 0
    assert result.delivered == 0


@pytest.mark.asyncio
async def test_drain_once_processes_multiple_entries_in_one_pass(
    engine: Engine, db_factory: sessionmaker[Session]
):
    settings = _make_settings()
    with db_factory() as db:
        for i in range(3):
            txn = _make_txn(db, id=f"txn-{i:03d}")
            enqueue(db, txn, settings=settings)
        db.commit()

    writer = FakeWriter(fabric_so_id="FAB")
    result = await drain_once(writer, db_factory)
    assert result.claimed == 3
    assert result.delivered == 3
    with db_factory() as db:
        statuses = {
            row.status
            for row in db.execute(select(FabricOutboxEntry)).scalars()
        }
        assert statuses == {"DELIVERED"}
