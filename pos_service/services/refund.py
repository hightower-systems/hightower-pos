import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from pos_service.clients.sentry import (
    RefundRequest,
    RefundSummary,
    SentryClient,
    SentryClientError,
    Tender,
)
from pos_service.clients.windcave import (
    WindcaveClient,
    WindcaveClientError,
    WindcaveStatusResponse,
)
from pos_service.config import Settings
from pos_service.models import POSTransaction
from pos_service.services import fabric_outbox
from pos_service.services import till as till_service
from pos_service.services.checkout import CheckoutError

log = logging.getLogger(__name__)

REFUND_TERMINAL_STATUSES = frozenset(
    {
        "COMPLETE",
        "REFUND_PAYMENT_FAILED",
        "REFUND_INVENTORY_UPDATE_FAILED",
        "CANCELLED",
    }
)

# A refund row in any of these states blocks a fresh refund attempt against
# the same original sale. REFUND_PAYMENT_FAILED and CANCELLED are intentionally
# absent: those represent attempts where money never left the merchant, so
# the cashier can retry.
REFUND_BLOCKING_STATES = frozenset(
    {
        "REFUND_PENDING",
        "REFUND_PAYMENT_IN_FLIGHT",
        "REFUND_PAYMENT_SUCCESS",
        "REFUND_INVENTORY_UPDATE_FAILED",
        "COMPLETE",
    }
)


def _now_naive_utc() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _existing_blocking_refund(
    db: Session, original_transaction_id: str
) -> POSTransaction | None:
    stmt = (
        select(POSTransaction)
        .where(
            POSTransaction.parent_transaction_id == original_transaction_id,
            POSTransaction.status.in_(REFUND_BLOCKING_STATES),
        )
        .limit(1)
    )
    return db.scalar(stmt)


def _card_brand_and_last4(tenders_json: str | None) -> tuple[str | None, str | None]:
    if not tenders_json:
        return None, None
    for tender in json.loads(tenders_json):
        if tender.get("type") == "card":
            return tender.get("card_brand"), tender.get("card_last4")
    return None, None


def lookup_refund(
    db: Session, settings: Settings, original_transaction_id: str
) -> dict:
    original = db.get(POSTransaction, original_transaction_id)
    if original is None:
        raise CheckoutError("transaction_not_found", 404)
    if original.txn_type != "sale":
        raise CheckoutError(
            "not_a_completed_sale", 422, current_status=original.status
        )
    if original.status != "COMPLETE":
        raise CheckoutError(
            "not_a_completed_sale", 422, current_status=original.status
        )

    days_since = (_now_naive_utc() - original.created_at).days
    if days_since > settings.refund_window_days:
        raise CheckoutError(
            "refund_window_expired", 422, days_since_sale=days_since
        )

    blocker = _existing_blocking_refund(db, original.id)
    if blocker is not None:
        raise CheckoutError(
            "already_refunded", 422, refund_transaction_id=blocker.id
        )

    cart = json.loads(original.cart_json)
    card_brand, card_last4 = _card_brand_and_last4(original.tenders_json)
    return {
        "original_transaction_id": original.id,
        "original_sentry_so_id": original.sentry_so_id,
        "completed_at": original.updated_at.isoformat(),
        "payment_method": original.payment_method,
        "card_brand": card_brand,
        "card_last4": card_last4,
        "subtotal_cents": original.subtotal_cents,
        "tax_cents": original.tax_cents,
        "total_cents": original.total_cents,
        "lines": cart,
        "refundable": True,
    }


async def start_refund(
    db: Session,
    settings: Settings,
    *,
    original_transaction_id: str,
    cashier_id: str,
) -> POSTransaction:
    # Re-run lookup gates (defensive: another cashier could have started a
    # refund between the React lookup call and this start call).
    lookup_refund(db, settings, original_transaction_id)
    original = db.get(POSTransaction, original_transaction_id)
    assert original is not None

    cart = json.loads(original.cart_json)
    refund_cart = []
    for line in cart:
        refund_cart.append(
            {
                **line,
                "quantity": -line["quantity"],
                "tax_cents": -line["tax_cents"],
                "line_total_cents": -line["line_total_cents"],
            }
        )

    refund_txn = POSTransaction(
        id=str(uuid.uuid4()),
        status="REFUND_PENDING",
        txn_type="refund",
        parent_transaction_id=original.id,
        cart_json=json.dumps(refund_cart),
        subtotal_cents=-original.subtotal_cents,
        tax_cents=-original.tax_cents,
        total_cents=-original.total_cents,
        payment_method=original.payment_method,
        cashier_id=cashier_id,
        terminal_id=original.terminal_id,
    )
    db.add(refund_txn)
    db.commit()
    db.refresh(refund_txn)
    return refund_txn


async def charge_card_refund(
    db: Session,
    settings: Settings,
    sentry: SentryClient,
    windcave: WindcaveClient,
    *,
    refund_txn_id: str,
) -> POSTransaction:
    refund_txn = _load_refund_for_payment(db, refund_txn_id)
    if refund_txn.payment_method != "card":
        raise CheckoutError("tender_mismatch", 400, expected="card")

    original = db.get(POSTransaction, refund_txn.parent_transaction_id)
    if original is None or not original.windcave_txn_ref:
        raise CheckoutError("missing_original_dps_txn_ref", 500)

    try:
        initial = await windcave.refund(
            amount_cents=abs(refund_txn.total_cents),
            original_dps_txn_ref=original.windcave_txn_ref,
            txn_ref=refund_txn.id,
        )
    except WindcaveClientError as exc:
        refund_txn.status = "REFUND_PAYMENT_FAILED"
        refund_txn.last_error = f"windcave_unavailable: {exc}"
        db.commit()
        raise CheckoutError("windcave_unavailable", 502) from exc

    refund_txn.windcave_response_xml = initial.raw_xml
    if initial.complete:
        await _finalize_refund_charge(
            db, refund_txn, initial, sentry=sentry, settings=settings
        )
    else:
        refund_txn.status = "REFUND_PAYMENT_IN_FLIGHT"
        db.commit()
    return refund_txn


async def charge_cash_refund(
    db: Session,
    settings: Settings,
    sentry: SentryClient,
    *,
    refund_txn_id: str,
) -> POSTransaction:
    refund_txn = _load_refund_for_payment(db, refund_txn_id)
    if refund_txn.payment_method != "cash":
        raise CheckoutError("tender_mismatch", 400, expected="cash")

    refund_txn.status = "REFUND_PAYMENT_SUCCESS"
    refund_txn.tenders_json = json.dumps(
        [{"type": "cash", "amount_cents": refund_txn.total_cents}]
    )
    db.commit()

    await _send_refund_to_sentry(db, sentry, refund_txn, settings=settings)
    return refund_txn


async def cancel_refund(db: Session, *, refund_txn_id: str) -> POSTransaction:
    refund_txn = db.get(POSTransaction, refund_txn_id)
    if refund_txn is None or refund_txn.txn_type != "refund":
        raise CheckoutError("transaction_not_found", 404)
    if refund_txn.status not in {"REFUND_PENDING", "REFUND_PAYMENT_IN_FLIGHT"}:
        raise CheckoutError("invalid_state", 400, current_status=refund_txn.status)
    refund_txn.status = "CANCELLED"
    db.commit()
    return refund_txn


def get_refund_status(db: Session, settings: Settings, refund_txn_id: str) -> dict:
    refund_txn = db.get(POSTransaction, refund_txn_id)
    if refund_txn is None or refund_txn.txn_type != "refund":
        raise CheckoutError("transaction_not_found", 404)

    is_terminal = refund_txn.status in REFUND_TERMINAL_STATUSES
    result: dict | None = None
    if refund_txn.status in {"COMPLETE", "REFUND_INVENTORY_UPDATE_FAILED"}:
        from pos_service.services.receipt import format_receipt

        card_brand, card_last4 = _card_brand_and_last4(refund_txn.tenders_json)
        parent: POSTransaction | None = None
        if refund_txn.parent_transaction_id:
            parent = db.get(POSTransaction, refund_txn.parent_transaction_id)
        result = {
            "refund_so_id": refund_txn.sentry_so_id,
            "windcave_txn_ref": refund_txn.windcave_txn_ref,
            "card_brand": card_brand,
            "card_last4": card_last4,
            "subtotal_cents": refund_txn.subtotal_cents,
            "tax_cents": refund_txn.tax_cents,
            "total_cents": refund_txn.total_cents,
            "payment_method": refund_txn.payment_method,
            "receipt_content": format_receipt(
                refund_txn, settings=settings, parent=parent
            ),
        }
    return {
        "refund_transaction_id": refund_txn.id,
        "status": refund_txn.status,
        "is_terminal": is_terminal,
        "result": result,
    }


async def poll_refund_until_complete(
    refund_txn_id: str, settings: Settings, engine: Engine
) -> None:
    sentry = SentryClient.from_settings(settings)
    windcave = WindcaveClient.from_settings(settings)
    poll_interval_s = settings.windcave_poll_interval_ms / 1000
    deadline_s = float(settings.windcave_max_poll_duration_s)

    elapsed_s = 0.0
    final_status: WindcaveStatusResponse | None = None
    while elapsed_s < deadline_s:
        try:
            current = await windcave.status(txn_ref=refund_txn_id)
        except WindcaveClientError as exc:
            log.warning(
                "windcave status poll failed for refund %s: %s", refund_txn_id, exc
            )
            await asyncio.sleep(poll_interval_s)
            elapsed_s += poll_interval_s
            continue
        if current.complete:
            final_status = current
            break
        await asyncio.sleep(poll_interval_s)
        elapsed_s += poll_interval_s

    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        refund_txn = db.get(POSTransaction, refund_txn_id)
        if refund_txn is None or refund_txn.status != "REFUND_PAYMENT_IN_FLIGHT":
            return
        if final_status is None:
            refund_txn.status = "REFUND_PAYMENT_FAILED"
            refund_txn.last_error = "polling_timeout"
            db.commit()
            return
        await _finalize_refund_charge(
            db, refund_txn, final_status, sentry=sentry, settings=settings
        )


async def _finalize_refund_charge(
    db: Session,
    refund_txn: POSTransaction,
    status: WindcaveStatusResponse,
    *,
    sentry: SentryClient,
    settings: Settings,
) -> None:
    refund_txn.windcave_response_xml = status.raw_xml

    if status.signature_required:
        refund_txn.status = "REFUND_PAYMENT_FAILED"
        refund_txn.last_error = (
            "signature verification required (not supported in v1)"
        )
        db.commit()
        return

    if not status.approved:
        refund_txn.status = "REFUND_PAYMENT_FAILED"
        if status.result is not None:
            refund_txn.last_error = (
                f"declined: {status.result.response_text or status.result.response_code}"
            )
        else:
            refund_txn.last_error = "declined"
        db.commit()
        return

    assert status.result is not None
    refund_txn.status = "REFUND_PAYMENT_SUCCESS"
    refund_txn.windcave_txn_ref = status.result.dps_txn_ref
    amount_signed = -(status.result.amount_cents or abs(refund_txn.total_cents))
    refund_txn.tenders_json = json.dumps(
        [
            {
                "type": "card",
                "amount_cents": amount_signed,
                "card_brand": status.result.card_brand,
                "card_last4": status.result.card_last4,
                "auth_code": status.result.auth_code,
                "external_ref": status.result.dps_txn_ref,
            }
        ]
    )
    db.commit()

    await _send_refund_to_sentry(db, sentry, refund_txn, settings=settings)


async def _send_refund_to_sentry(
    db: Session,
    sentry: SentryClient,
    refund_txn: POSTransaction,
    *,
    settings: Settings,
) -> None:
    original = db.get(POSTransaction, refund_txn.parent_transaction_id)
    assert original is not None
    request = _build_refund_request(refund_txn, original)
    try:
        result = await sentry.create_pos_refund(request)
    except SentryClientError as exc:
        log.warning("sentry refund failed for refund %s: %s", refund_txn.id, exc)
        refund_txn.status = "REFUND_INVENTORY_UPDATE_FAILED"
        refund_txn.last_error = f"{exc.error_code or 'unknown'}: {exc}"
        fabric_outbox.enqueue(db, refund_txn, settings=settings)
        db.commit()
        try:
            await sentry.log_inbound_activity(
                source="pos-service",
                event_type="refund_failed_post_payment",
                payload=request.model_dump(mode="json"),
                error_context=str(exc),
            )
        except Exception:
            log.exception("inbound activity log fallback failed")
        return

    refund_txn.status = "COMPLETE"
    refund_txn.sentry_so_id = result.refund_so_id
    original.refund_transaction_id = refund_txn.id
    # Refund attribution rule (per till plan + user clarification):
    # the refund attributes to the currently-open shift, NOT the
    # original sale's shift. A refund for yesterday's sale processed
    # today decrements today's expected_closing. Cash refund flow
    # adds to cash_refunds_cents; card refunds get the till_session_id
    # stamp for the admin 'all transactions' view but don't move the
    # cash math.
    till_service.attribute_transaction(db, refund_txn, is_refund=True)
    fabric_outbox.enqueue(db, refund_txn, settings=settings)
    db.commit()


def _build_refund_request(
    refund_txn: POSTransaction, original: POSTransaction
) -> RefundRequest:
    refund_tenders = (
        json.loads(refund_txn.tenders_json) if refund_txn.tenders_json else []
    )
    return RefundRequest(
        idempotency_key=refund_txn.id,
        original_so_id=original.sentry_so_id or "",
        original_external_txn_ref=original.windcave_txn_ref,
        external_refund_ref=refund_txn.windcave_txn_ref,
        cashier_id=refund_txn.cashier_id,
        terminal_id=refund_txn.terminal_id,
        completed_at=_now_naive_utc(),
        refund_summary=RefundSummary(
            method=refund_txn.payment_method or "cash",
            subtotal_cents=refund_txn.subtotal_cents,
            tax_cents=refund_txn.tax_cents,
            total_cents=refund_txn.total_cents,
            tenders=[Tender(**t) for t in refund_tenders],
        ),
    )


def _load_refund_for_payment(db: Session, refund_txn_id: str) -> POSTransaction:
    refund_txn = db.get(POSTransaction, refund_txn_id)
    if refund_txn is None or refund_txn.txn_type != "refund":
        raise CheckoutError("transaction_not_found", 404)
    if refund_txn.status != "REFUND_PENDING":
        raise CheckoutError("invalid_state", 400, current_status=refund_txn.status)
    return refund_txn
