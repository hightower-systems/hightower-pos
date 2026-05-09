"""Four-hourly Fabric -> pos_prices price catalog sync.

A long-lived asyncio task (started from the FastAPI lifespan in
pos_service.main) calls FabricClient.fetch_price_catalog() every
fabric_sync_interval_s seconds and upserts the result into the local
pos_prices SQLite cache. The cashier path
(pos_service.routes.items.lookup -> pos_service.services.pricing.get_price_cents)
reads only from that cache, so a Fabric outage never blocks a sale -- it
just lets prices age until Fabric recovers and the next sync lands.

The CSV import path (POST /api/prices/import) and this Fabric poll both
write to the same pos_prices table; whichever ran most recently per SKU
wins. CSV is a manual override; Fabric is the routine source of truth.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import func
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, sessionmaker

from pos_service.clients.fabric import FabricClientError
from pos_service.models import POSPrice

log = logging.getLogger(__name__)

UPSERT_BATCH_SIZE = 1000


class _PriceFetcher(Protocol):
    is_mock: bool
    async def fetch_price_catalog(self) -> list[tuple[str, int]]: ...


@dataclass(frozen=True)
class SyncResult:
    rows_fetched: int
    rows_upserted: int
    duration_s: float
    error: str | None = None


async def sync_once(
    client: _PriceFetcher, session_factory: sessionmaker[Session]
) -> SyncResult:
    started = time.monotonic()
    try:
        rows = await client.fetch_price_catalog()
    except FabricClientError as exc:
        return SyncResult(
            rows_fetched=0,
            rows_upserted=0,
            duration_s=time.monotonic() - started,
            error=str(exc),
        )

    if not rows:
        return SyncResult(
            rows_fetched=0,
            rows_upserted=0,
            duration_s=time.monotonic() - started,
        )

    payload = [{"sku": sku, "unit_price_cents": cents} for sku, cents in rows]

    with session_factory() as session:
        for i in range(0, len(payload), UPSERT_BATCH_SIZE):
            batch = payload[i : i + UPSERT_BATCH_SIZE]
            stmt = sqlite_insert(POSPrice).values(batch)
            stmt = stmt.on_conflict_do_update(
                index_elements=["sku"],
                set_={
                    "unit_price_cents": stmt.excluded.unit_price_cents,
                    "updated_at": func.now(),
                },
            )
            session.execute(stmt)
        session.commit()

    return SyncResult(
        rows_fetched=len(rows),
        rows_upserted=len(rows),
        duration_s=time.monotonic() - started,
    )


async def run_loop(
    client: _PriceFetcher,
    session_factory: sessionmaker[Session],
    interval_s: int,
) -> None:
    log.info(
        "fabric_price_sync_started",
        extra={"interval_s": interval_s, "is_mock": client.is_mock},
    )
    while True:
        try:
            result = await sync_once(client, session_factory)
            if result.error:
                log.error(
                    "fabric_price_sync_failed",
                    extra={"error": result.error, "duration_s": result.duration_s},
                )
            else:
                log.info(
                    "fabric_price_sync_complete",
                    extra={
                        "rows_fetched": result.rows_fetched,
                        "rows_upserted": result.rows_upserted,
                        "duration_s": result.duration_s,
                    },
                )
        except asyncio.CancelledError:
            log.info("fabric_price_sync_cancelled")
            raise
        except Exception:
            log.exception("fabric_price_sync_loop_unexpected")
        await asyncio.sleep(interval_s)
