import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from pos_service.clients.sentry import SentryClient, SentryClientError
from pos_service.models import POSTransaction
from pos_service.services.checkout import _build_checkout_request
from pos_service.services.refund import _build_refund_request

log = logging.getLogger(__name__)


@dataclass
class RetryReport:
    scanned: int = 0
    succeeded: list[str] = field(default_factory=list)
    still_failing: list[str] = field(default_factory=list)


async def retry_one_sale(
    db: Session, sentry: SentryClient, txn: POSTransaction
) -> bool:
    request = _build_checkout_request(
        txn, payment_method=txn.payment_method or "cash"
    )
    try:
        result = await sentry.create_pos_so(request)
    except SentryClientError as exc:
        txn.last_error = f"{exc.error_code or 'unknown'}: {exc}"
        txn.retry_count = (txn.retry_count or 0) + 1
        db.commit()
        return False
    txn.status = "COMPLETE"
    txn.sentry_so_id = result.so_id
    txn.last_error = None
    txn.retry_count = (txn.retry_count or 0) + 1
    db.commit()
    return True


async def retry_one_refund(
    db: Session, sentry: SentryClient, refund_txn: POSTransaction
) -> bool:
    original = db.get(POSTransaction, refund_txn.parent_transaction_id)
    if original is None:
        log.warning(
            "refund %s has no parent (id=%s); skipping retry",
            refund_txn.id,
            refund_txn.parent_transaction_id,
        )
        return False
    request = _build_refund_request(refund_txn, original)
    try:
        result = await sentry.create_pos_refund(request)
    except SentryClientError as exc:
        refund_txn.last_error = f"{exc.error_code or 'unknown'}: {exc}"
        refund_txn.retry_count = (refund_txn.retry_count or 0) + 1
        db.commit()
        return False
    refund_txn.status = "COMPLETE"
    refund_txn.sentry_so_id = result.refund_so_id
    refund_txn.last_error = None
    refund_txn.retry_count = (refund_txn.retry_count or 0) + 1
    original.refund_transaction_id = refund_txn.id
    db.commit()
    return True


async def retry_failed_sales(db: Session, sentry: SentryClient) -> RetryReport:
    stmt = select(POSTransaction).where(
        POSTransaction.txn_type == "sale",
        POSTransaction.status == "INVENTORY_UPDATE_FAILED",
    )
    rows = list(db.scalars(stmt))
    report = RetryReport(scanned=len(rows))
    for txn in rows:
        if await retry_one_sale(db, sentry, txn):
            report.succeeded.append(txn.id)
        else:
            report.still_failing.append(txn.id)
    return report


async def retry_failed_refunds(db: Session, sentry: SentryClient) -> RetryReport:
    stmt = select(POSTransaction).where(
        POSTransaction.txn_type == "refund",
        POSTransaction.status == "REFUND_INVENTORY_UPDATE_FAILED",
    )
    rows = list(db.scalars(stmt))
    report = RetryReport(scanned=len(rows))
    for refund_txn in rows:
        if await retry_one_refund(db, sentry, refund_txn):
            report.succeeded.append(refund_txn.id)
        else:
            report.still_failing.append(refund_txn.id)
    return report
