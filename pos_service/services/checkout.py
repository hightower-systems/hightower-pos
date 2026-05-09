import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_EVEN, Decimal

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from pos_service.clients.sentry import (
    CartLine,
    CheckoutLine,
    CheckoutRequest,
    PaymentSummary,
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
from pos_service.services import fabric_outbox, pricing

log = logging.getLogger(__name__)

TERMINAL_STATUSES = frozenset(
    {
        "COMPLETE",
        "PAYMENT_FAILED",
        "VALIDATION_FAILED",
        "INVENTORY_UPDATE_FAILED",
        "CANCELLED",
    }
)


class CheckoutError(Exception):
    def __init__(self, code: str, http_status: int = 400, **extra: object) -> None:
        super().__init__(code)
        self.code = code
        self.http_status = http_status
        self.extra = dict(extra)


def compute_line_tax(line_subtotal_cents: int, tax_rate: float, taxable: bool) -> int:
    if not taxable:
        return 0
    rate = Decimal(str(tax_rate))
    return int(
        (Decimal(line_subtotal_cents) * rate).quantize(
            Decimal("1"), rounding=ROUND_HALF_EVEN
        )
    )


async def start_checkout(
    db: Session,
    settings: Settings,
    sentry: SentryClient,
    *,
    lines: list[dict],
    cashier_id: str,
) -> POSTransaction:
    skus_without_price: list[str] = []
    line_prices: dict[str, int] = {}
    for line in lines:
        sku = line["sku"]
        if sku in line_prices:
            continue
        price = pricing.get_price_cents(db, sku)
        if price is None:
            if sku not in skus_without_price:
                skus_without_price.append(sku)
        else:
            line_prices[sku] = price
    if skus_without_price:
        raise CheckoutError(
            "price_missing", 422, skus_without_price=skus_without_price
        )

    rich_lines: list[dict] = []
    subtotal_cents = 0
    tax_cents = 0
    for line in lines:
        unit_price = line_prices[line["sku"]]
        line_subtotal = unit_price * line["quantity"]
        line_tax = compute_line_tax(line_subtotal, settings.tax_rate, line["is_taxable"])
        subtotal_cents += line_subtotal
        tax_cents += line_tax
        rich_lines.append(
            {
                "sku": line["sku"],
                "name": line.get("name", ""),
                "warehouse_id": line["warehouse_id"],
                "bin_id": line["bin_id"],
                "quantity": line["quantity"],
                "is_taxable": line["is_taxable"],
                "unit_price_cents": unit_price,
                "tax_cents": line_tax,
                "line_total_cents": line_subtotal + line_tax,
            }
        )
    total_cents = subtotal_cents + tax_cents

    txn = POSTransaction(
        id=str(uuid.uuid4()),
        status="PENDING_VALIDATION",
        txn_type="sale",
        cart_json=json.dumps(rich_lines),
        subtotal_cents=subtotal_cents,
        tax_cents=tax_cents,
        total_cents=total_cents,
        cashier_id=cashier_id,
        terminal_id=settings.windcave_station,
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)

    cart_lines = [
        CartLine(
            sku=line["sku"],
            warehouse_id=line["warehouse_id"],
            bin_id=line["bin_id"],
            quantity=line["quantity"],
        )
        for line in lines
    ]
    try:
        result = await sentry.validate_cart(cart_lines)
    except SentryClientError as exc:
        txn.status = "VALIDATION_FAILED"
        txn.last_error = f"sentry_unavailable: {exc}"
        db.commit()
        raise CheckoutError("sentry_unavailable", 502) from exc

    if not result.valid:
        txn.status = "VALIDATION_FAILED"
        txn.last_error = json.dumps([c.model_dump() for c in result.conflicts])
        db.commit()
        raise CheckoutError(
            "validation_failed",
            409,
            conflicts=[c.model_dump() for c in result.conflicts],
        )

    txn.status = "AWAITING_PAYMENT"
    db.commit()
    return txn


async def charge_cash(
    db: Session,
    settings: Settings,
    sentry: SentryClient,
    *,
    txn_id: str,
    amount_tendered_cents: int,
) -> POSTransaction:
    txn = _load_for_payment(db, txn_id)
    if amount_tendered_cents < txn.total_cents:
        raise CheckoutError(
            "insufficient_tender", 400, total_cents=txn.total_cents
        )

    change_cents = amount_tendered_cents - txn.total_cents
    txn.status = "PAYMENT_SUCCESS"
    txn.payment_method = "cash"
    txn.tenders_json = json.dumps(
        [
            {
                "type": "cash",
                "amount_cents": txn.total_cents,
                "amount_tendered_cents": amount_tendered_cents,
                "change_cents": change_cents,
            }
        ]
    )
    db.commit()

    await _send_to_sentry(db, sentry, txn, payment_method="cash", settings=settings)
    return txn


async def charge_card(
    db: Session,
    settings: Settings,
    sentry: SentryClient,
    windcave: WindcaveClient,
    *,
    txn_id: str,
) -> POSTransaction:
    txn = _load_for_payment(db, txn_id)

    try:
        initial = await windcave.charge(amount_cents=txn.total_cents, txn_ref=txn.id)
    except WindcaveClientError as exc:
        txn.status = "PAYMENT_FAILED"
        txn.last_error = f"windcave_unavailable: {exc}"
        db.commit()
        raise CheckoutError("windcave_unavailable", 502) from exc

    txn.payment_method = "card"
    txn.windcave_response_xml = initial.raw_xml
    if initial.complete:
        await _finalize_card_charge(db, txn, initial, sentry=sentry, settings=settings)
    else:
        txn.status = "PAYMENT_IN_FLIGHT"
        db.commit()
    return txn


async def cancel_checkout(
    db: Session,
    windcave: WindcaveClient,
    *,
    txn_id: str,
) -> POSTransaction:
    txn = db.get(POSTransaction, txn_id)
    if txn is None:
        raise CheckoutError("transaction_not_found", 404)
    if txn.status not in {"AWAITING_PAYMENT", "PAYMENT_IN_FLIGHT"}:
        raise CheckoutError("invalid_state", 400, current_status=txn.status)

    if txn.status == "PAYMENT_IN_FLIGHT" and txn.payment_method == "card":
        try:
            await windcave.cancel(txn_ref=txn.id)
        except WindcaveClientError as exc:
            log.warning("windcave cancel failed for %s: %s", txn.id, exc)

    txn.status = "CANCELLED"
    db.commit()
    return txn


def get_status(db: Session, settings: Settings, txn_id: str) -> dict:
    txn = db.get(POSTransaction, txn_id)
    if txn is None:
        raise CheckoutError("transaction_not_found", 404)

    is_terminal = txn.status in TERMINAL_STATUSES
    result: dict | None = None
    if txn.status in {"COMPLETE", "INVENTORY_UPDATE_FAILED"}:
        from pos_service.services.receipt import format_receipt

        tenders = json.loads(txn.tenders_json) if txn.tenders_json else []
        card_brand = None
        card_last4 = None
        for tender in tenders:
            if tender.get("type") == "card":
                card_brand = tender.get("card_brand")
                card_last4 = tender.get("card_last4")
                break
        result = {
            "so_id": txn.sentry_so_id,
            "windcave_txn_ref": txn.windcave_txn_ref,
            "card_brand": card_brand,
            "card_last4": card_last4,
            "subtotal_cents": txn.subtotal_cents,
            "tax_cents": txn.tax_cents,
            "total_cents": txn.total_cents,
            "payment_method": txn.payment_method,
            "receipt_content": format_receipt(txn, settings=settings),
        }
    return {
        "transaction_id": txn.id,
        "status": txn.status,
        "is_terminal": is_terminal,
        "result": result,
    }


async def poll_card_until_complete(
    txn_id: str, settings: Settings, engine: Engine
) -> None:
    """Background task. Polls Windcave status until complete or timeout, then
    finalises the transaction. Creates its own DB session and clients so it can
    safely outlive the request that scheduled it."""
    sentry = SentryClient.from_settings(settings)
    windcave = WindcaveClient.from_settings(settings)
    poll_interval_s = settings.windcave_poll_interval_ms / 1000
    deadline_s = float(settings.windcave_max_poll_duration_s)

    elapsed_s = 0.0
    final_status: WindcaveStatusResponse | None = None
    while elapsed_s < deadline_s:
        try:
            current = await windcave.status(txn_ref=txn_id)
        except WindcaveClientError as exc:
            log.warning("windcave status poll failed for %s: %s", txn_id, exc)
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
        txn = db.get(POSTransaction, txn_id)
        if txn is None or txn.status != "PAYMENT_IN_FLIGHT":
            return
        if final_status is None:
            txn.status = "PAYMENT_FAILED"
            txn.last_error = "polling_timeout"
            db.commit()
            return
        await _finalize_card_charge(
            db, txn, final_status, sentry=sentry, settings=settings
        )


async def _finalize_card_charge(
    db: Session,
    txn: POSTransaction,
    status: WindcaveStatusResponse,
    *,
    sentry: SentryClient,
    settings: Settings,
) -> None:
    txn.windcave_response_xml = status.raw_xml

    if status.signature_required:
        txn.status = "PAYMENT_FAILED"
        txn.last_error = "signature verification required (not supported in v1)"
        db.commit()
        return

    if not status.approved:
        txn.status = "PAYMENT_FAILED"
        if status.result is not None:
            txn.last_error = (
                f"declined: {status.result.response_text or status.result.response_code}"
            )
        else:
            txn.last_error = "declined"
        db.commit()
        return

    assert status.result is not None
    txn.status = "PAYMENT_SUCCESS"
    txn.payment_method = "card"
    txn.windcave_txn_ref = status.result.dps_txn_ref
    txn.tenders_json = json.dumps(
        [
            {
                "type": "card",
                "amount_cents": status.result.amount_cents or txn.total_cents,
                "card_brand": status.result.card_brand,
                "card_last4": status.result.card_last4,
                "auth_code": status.result.auth_code,
                "external_ref": status.result.dps_txn_ref,
            }
        ]
    )
    db.commit()

    await _send_to_sentry(db, sentry, txn, payment_method="card", settings=settings)


async def _send_to_sentry(
    db: Session,
    sentry: SentryClient,
    txn: POSTransaction,
    *,
    payment_method: str,
    settings: Settings,
) -> None:
    request = _build_checkout_request(txn, payment_method=payment_method)
    try:
        result = await sentry.create_pos_so(request)
    except SentryClientError as exc:
        log.warning("sentry checkout failed for txn %s: %s", txn.id, exc)
        txn.status = "INVENTORY_UPDATE_FAILED"
        txn.last_error = f"{exc.error_code or 'unknown'}: {exc}"
        fabric_outbox.enqueue(db, txn, settings=settings)
        db.commit()
        try:
            await sentry.log_inbound_activity(
                source="pos-service",
                event_type="checkout_failed_post_payment",
                payload=request.model_dump(mode="json"),
                error_context=str(exc),
            )
        except Exception:
            log.exception("inbound activity log fallback failed")
        return

    txn.status = "COMPLETE"
    txn.sentry_so_id = result.so_id
    fabric_outbox.enqueue(db, txn, settings=settings)
    db.commit()


def _build_checkout_request(
    txn: POSTransaction, *, payment_method: str
) -> CheckoutRequest:
    cart = json.loads(txn.cart_json)
    tenders = json.loads(txn.tenders_json) if txn.tenders_json else []
    return CheckoutRequest(
        idempotency_key=txn.id,
        external_txn_ref=txn.windcave_txn_ref,
        cashier_id=txn.cashier_id,
        terminal_id=txn.terminal_id,
        completed_at=datetime.now(UTC).replace(tzinfo=None),
        payment_summary=PaymentSummary(
            method=payment_method,
            subtotal_cents=txn.subtotal_cents,
            tax_cents=txn.tax_cents,
            total_cents=txn.total_cents,
            tenders=[Tender(**t) for t in tenders],
        ),
        lines=[
            CheckoutLine(
                sku=line["sku"],
                warehouse_id=line["warehouse_id"],
                bin_id=line["bin_id"],
                quantity=line["quantity"],
                unit_price_cents=line["unit_price_cents"],
                tax_cents=line["tax_cents"],
                line_total_cents=line["line_total_cents"],
            )
            for line in cart
        ],
    )


def _load_for_payment(db: Session, txn_id: str) -> POSTransaction:
    txn = db.get(POSTransaction, txn_id)
    if txn is None:
        raise CheckoutError("transaction_not_found", 404)
    if txn.txn_type != "sale":
        raise CheckoutError("invalid_state", 400, current_status=txn.status)
    if txn.status != "AWAITING_PAYMENT":
        raise CheckoutError("invalid_state", 400, current_status=txn.status)
    return txn
