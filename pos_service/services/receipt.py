import json
import logging

from lxml import etree

from pos_service.config import Settings
from pos_service.models import POSTransaction

log = logging.getLogger(__name__)

RECEIPT_WIDTH = 30


def format_receipt(
    transaction: POSTransaction,
    *,
    settings: Settings,
    parent: POSTransaction | None = None,
) -> str:
    """Plain-text receipt content for the print agent, 30 cols wide.

    For refunds, parent must be provided so the receipt can render the
    original transaction id and date alongside the REFUND header.
    """
    is_refund = transaction.txn_type == "refund"
    out: list[str] = []

    out.append(_center(settings.store_name, RECEIPT_WIDTH))
    if settings.store_address_line_1:
        out.append(_center(settings.store_address_line_1, RECEIPT_WIDTH))
    if settings.store_address_line_2:
        out.append(_center(settings.store_address_line_2, RECEIPT_WIDTH))
    if settings.store_phone:
        out.append(_center(settings.store_phone, RECEIPT_WIDTH))
    out.append("=" * RECEIPT_WIDTH)

    if is_refund:
        out.append(_center("REFUND", RECEIPT_WIDTH))
        if parent is not None:
            out.append(_center(f"Orig txn: {parent.id[:12]}", RECEIPT_WIDTH))
            out.append(
                _center(f"Orig date: {parent.created_at:%Y-%m-%d}", RECEIPT_WIDTH)
            )
        out.append("=" * RECEIPT_WIDTH)

    use_windcave_rcpt = (
        transaction.payment_method == "card" and bool(transaction.windcave_response_xml)
    )
    if use_windcave_rcpt:
        rcpt = _extract_windcave_receipt(transaction.windcave_response_xml or "")
        if rcpt:
            out.append(rcpt)
        else:
            out.extend(_cart_body_lines(transaction, is_refund))
    else:
        out.extend(_cart_body_lines(transaction, is_refund))

    out.append("-" * RECEIPT_WIDTH)
    rate_label = f"({settings.tax_rate * 100:.2f}%)"
    if is_refund:
        out.append(
            _pad_pair(
                "Refund subtotal",
                _money(transaction.subtotal_cents, signed=True),
                RECEIPT_WIDTH,
            )
        )
        out.append(
            _pad_pair(
                f"Refund tax {rate_label}",
                _money(transaction.tax_cents, signed=True),
                RECEIPT_WIDTH,
            )
        )
        out.append("-" * RECEIPT_WIDTH)
        out.append(
            _pad_pair(
                "REFUND TOTAL",
                _money(transaction.total_cents, signed=True),
                RECEIPT_WIDTH,
            )
        )
    else:
        out.append(
            _pad_pair(
                "Subtotal", _money(transaction.subtotal_cents), RECEIPT_WIDTH
            )
        )
        out.append(
            _pad_pair(
                f"Tax {rate_label}", _money(transaction.tax_cents), RECEIPT_WIDTH
            )
        )
        out.append("-" * RECEIPT_WIDTH)
        out.append(
            _pad_pair("TOTAL", _money(transaction.total_cents), RECEIPT_WIDTH)
        )

    out.append("")
    out.extend(_tender_lines(transaction, is_refund))

    out.append("=" * RECEIPT_WIDTH)
    if not is_refund:
        out.append(_center("Thank you!", RECEIPT_WIDTH))
    txn_label = "Refund txn" if is_refund else "Transaction"
    out.append(_center(f"{txn_label}: {transaction.id[:12]}", RECEIPT_WIDTH))
    out.append(_center(f"{transaction.created_at:%Y-%m-%d %H:%M:%S}", RECEIPT_WIDTH))

    return "\n".join(out)


def _cart_body_lines(transaction: POSTransaction, is_refund: bool) -> list[str]:
    if not transaction.cart_json:
        return []
    cart = json.loads(transaction.cart_json)
    out: list[str] = []
    for line in cart:
        sku = line.get("sku", "")
        name = line.get("name") or ""
        header = f"{sku} {name}".strip() if name else sku
        out.append(header[:RECEIPT_WIDTH])
        qty = abs(int(line["quantity"]))
        unit_price = int(line["unit_price_cents"]) / 100
        line_total_cents = int(line["line_total_cents"])
        right = (
            f"-{_money(abs(line_total_cents))}" if is_refund else _money(line_total_cents)
        )
        left = f"  Qty {qty} @ ${unit_price:.2f}"
        out.append(_pad_pair(left, right, RECEIPT_WIDTH))
    return out


def _tender_lines(transaction: POSTransaction, is_refund: bool) -> list[str]:
    tenders = json.loads(transaction.tenders_json) if transaction.tenders_json else []
    out: list[str] = []
    for tender in tenders:
        ttype = tender.get("type")
        if ttype == "card":
            brand = tender.get("card_brand") or "Card"
            last4 = tender.get("card_last4") or "----"
            if is_refund:
                out.append(f"Refunded to: {brand} ****{last4}")
            else:
                out.append(f"Paid: {brand} ****{last4}")
            auth = tender.get("auth_code")
            if auth:
                out.append(f"Auth: {auth}")
        elif ttype == "cash":
            if is_refund:
                out.append(
                    _pad_pair(
                        "Cash returned",
                        _money(abs(int(tender["amount_cents"]))),
                        RECEIPT_WIDTH,
                    )
                )
            else:
                tendered = int(tender.get("amount_tendered_cents") or tender["amount_cents"])
                change = int(tender.get("change_cents") or 0)
                out.append(_pad_pair("Cash tendered", _money(tendered), RECEIPT_WIDTH))
                out.append(_pad_pair("Change", _money(change), RECEIPT_WIDTH))
    return out


def _extract_windcave_receipt(xml_str: str) -> str:
    if not xml_str.strip().startswith("<"):
        return ""
    try:
        root = etree.fromstring(xml_str.encode("utf-8"))
    except etree.XMLSyntaxError:
        return ""
    return (root.findtext("Rcpt") or "").strip()


def _center(text: str, width: int) -> str:
    text = text.strip()
    if len(text) >= width:
        return text[:width]
    return text.center(width)


def _pad_pair(left: str, right: str, width: int) -> str:
    if len(left) + len(right) + 1 > width:
        truncated = left[: max(width - len(right) - 1, 0)]
        return f"{truncated} {right}"
    pad = width - len(left) - len(right)
    return f"{left}{' ' * pad}{right}"


def _money(cents: int, *, signed: bool = False) -> str:
    if signed and cents < 0:
        return f"-${abs(cents) / 100:.2f}"
    return f"${cents / 100:.2f}"
