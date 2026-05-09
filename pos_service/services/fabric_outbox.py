"""Fabric SO outbox: transactional write at COMPLETE + drain worker.

The cashier-facing flow is unchanged by Fabric. When a sale (or refund)
hits its terminal state in the POS Service, enqueue() inserts a
fabric_outbox row in the SAME database transaction as the status flip.
A separate asyncio task (run_loop) drains pending entries by POSTing the
payload to the Fabric transaction service via FabricClient.write_sales_order.

Resilience: Fabric being down does not block sales. Pending entries
accumulate locally and replay automatically when the transaction
service comes back. Per-attempt backoff schedule mirrors the Sentry-side
sentry-dispatcher (sentry-wms api/services/webhook_dispatcher/retry.py)
for cross-system consistency. Cumulative window before DLQ is ~14.6h.

Single-instance assumption (single POS Service container per register):
SQLite serialises the claim UPDATE so SELECT FOR UPDATE SKIP LOCKED is
not needed. Multi-register expansion is also when the POS Service moves
to Postgres; both happen together.

The drain worker only starts when FabricClient.is_mock is False (i.e.,
FABRIC_TRANSACTION_SERVICE_URL is set). Mock-mode dev machines accumulate
PENDING rows that drain when the URL is wired in.
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from pos_service.clients.fabric import FabricClientError
from pos_service.config import Settings
from pos_service.models import FabricOutboxEntry, POSTransaction

log = logging.getLogger(__name__)

# Mirror Sentry-side dispatcher schedule (sentry-wms
# api/services/webhook_dispatcher/retry.py RETRY_SCHEDULE_SECONDS).
# Slot 0 fires immediately; slots 1..N are wait-times before the next
# retry. After exhausting the schedule the entry flips to DLQ.
RETRY_SCHEDULE_SECONDS: tuple[int, ...] = (
    0,
    4,
    15,
    60,
    300,
    1800,
    7200,
    43200,
)
MAX_ATTEMPTS = len(RETRY_SCHEDULE_SECONDS)
DEFAULT_BATCH_SIZE = 50


class _SOWriter(Protocol):
    is_mock: bool

    async def write_sales_order(
        self, payload: dict[str, Any]
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class DrainResult:
    claimed: int
    delivered: int
    failed: int
    dlq: int
    duration_s: float


def _now_naive_utc() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def build_payload(txn: POSTransaction, *, settings: Settings) -> dict[str, Any]:
    """Construct the SO payload posted to the Fabric transaction service.

    Per the architecture call: payload is intentionally lean. Tender
    detail (card brand / last4 / auth code) is omitted; the POS Service
    keeps that locally for receipts and reconciliation. fulfillment_channel
    is the literal 'Store' the engineer specified, and status is 'shipped'
    because Sentry uses that as the closed terminal status for retail
    (no pick/pack/invoice flow at the register).
    """
    cart: list[Any] = []
    if txn.cart_json:
        try:
            cart = json.loads(txn.cart_json)
        except json.JSONDecodeError:
            cart = []
    completed_at = txn.updated_at or txn.created_at
    return {
        "external_so_ref": txn.id,
        "sentry_so_id": txn.sentry_so_id,
        "txn_type": txn.txn_type,
        "parent_transaction_id": txn.parent_transaction_id,
        "source": "POS",
        "fulfillment_channel": "Store",
        "status": "shipped",
        "register_id": settings.windcave_device_id,
        "cashier_id": txn.cashier_id,
        "terminal_id": txn.terminal_id,
        "completed_at": completed_at.isoformat() if completed_at else None,
        "currency": settings.windcave_currency,
        "subtotal_cents": txn.subtotal_cents,
        "tax_cents": txn.tax_cents,
        "total_cents": txn.total_cents,
        "payment_method": txn.payment_method,
        "lines": cart,
    }


def enqueue(
    db: Session, txn: POSTransaction, *, settings: Settings
) -> FabricOutboxEntry:
    """Insert a PENDING outbox row in the caller's DB session.

    The caller commits as part of the same transaction that flips the
    POSTransaction to its terminal status, so the outbox row and the
    status flip persist together (transactional outbox pattern).
    """
    entry = FabricOutboxEntry(
        id=str(uuid.uuid4()),
        pos_transaction_id=txn.id,
        payload_json=json.dumps(build_payload(txn, settings=settings)),
        status="PENDING",
        attempt_count=0,
        next_attempt_at=_now_naive_utc(),
    )
    db.add(entry)
    return entry


def _claim_due(
    db: Session, *, batch_size: int
) -> list[str]:
    now = _now_naive_utc()
    stmt = (
        select(FabricOutboxEntry)
        .where(
            FabricOutboxEntry.status == "PENDING",
            FabricOutboxEntry.next_attempt_at <= now,
        )
        .order_by(FabricOutboxEntry.created_at)
        .limit(batch_size)
    )
    entries = list(db.execute(stmt).scalars())
    ids = [e.id for e in entries]
    for entry in entries:
        entry.status = "IN_FLIGHT"
    db.commit()
    return ids


def _mark_delivered(
    db: Session, entry_id: str, fabric_so_id: str | None
) -> None:
    entry = db.get(FabricOutboxEntry, entry_id)
    if entry is None:
        return
    entry.status = "DELIVERED"
    entry.fabric_so_id = fabric_so_id
    entry.last_error = None
    db.commit()


def _mark_failed(db: Session, entry_id: str, error: str) -> str:
    """Bump attempt_count, schedule the next retry, or flip to DLQ.
    Returns the new status so the caller can count outcomes."""
    entry = db.get(FabricOutboxEntry, entry_id)
    if entry is None:
        return "MISSING"
    entry.attempt_count += 1
    entry.last_error = error
    if entry.attempt_count >= MAX_ATTEMPTS:
        entry.status = "DLQ"
    else:
        wait_s = RETRY_SCHEDULE_SECONDS[entry.attempt_count]
        entry.status = "PENDING"
        entry.next_attempt_at = _now_naive_utc() + timedelta(seconds=wait_s)
    db.commit()
    return entry.status


async def drain_once(
    client: _SOWriter,
    session_factory: sessionmaker[Session],
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> DrainResult:
    started = time.monotonic()
    delivered = failed = dlq = 0

    with session_factory() as session:
        claimed_ids = _claim_due(session, batch_size=batch_size)

    for entry_id in claimed_ids:
        with session_factory() as session:
            entry = session.get(FabricOutboxEntry, entry_id)
            if entry is None or entry.status != "IN_FLIGHT":
                continue
            payload = json.loads(entry.payload_json)
        try:
            result = await client.write_sales_order(payload)
        except FabricClientError as exc:
            with session_factory() as session:
                new_status = _mark_failed(session, entry_id, str(exc))
            if new_status == "DLQ":
                dlq += 1
            else:
                failed += 1
            continue
        with session_factory() as session:
            _mark_delivered(
                session, entry_id, fabric_so_id=(result or {}).get("fabric_so_id")
            )
        delivered += 1

    return DrainResult(
        claimed=len(claimed_ids),
        delivered=delivered,
        failed=failed,
        dlq=dlq,
        duration_s=time.monotonic() - started,
    )


async def run_loop(
    client: _SOWriter,
    session_factory: sessionmaker[Session],
    interval_s: int,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> None:
    log.info(
        "fabric_outbox_drain_started",
        extra={
            "interval_s": interval_s,
            "batch_size": batch_size,
            "is_mock": client.is_mock,
        },
    )
    while True:
        try:
            result = await drain_once(client, session_factory, batch_size=batch_size)
            if result.claimed > 0:
                log.info(
                    "fabric_outbox_drain",
                    extra={
                        "claimed": result.claimed,
                        "delivered": result.delivered,
                        "failed": result.failed,
                        "dlq": result.dlq,
                        "duration_s": result.duration_s,
                    },
                )
        except asyncio.CancelledError:
            log.info("fabric_outbox_drain_cancelled")
            raise
        except Exception:
            log.exception("fabric_outbox_drain_loop_unexpected")
        await asyncio.sleep(interval_s)
