import json
from datetime import UTC, datetime

import httpx
import respx
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from pos_service.config import Settings
from pos_service.models import POSPrice, POSTransaction, POSUser
from pos_service.services.receipt import RECEIPT_WIDTH, format_receipt

SENTRY_BASE = "http://sentry.test"


def _settings() -> Settings:
    return Settings(
        sentry_base_url="http://x",
        sentry_api_token="x",
        windcave_base_url="http://x",
        windcave_user="x",
        windcave_key="x",
        windcave_station="x",
        tax_rate=0.0810,
        store_name="AvidMax",
        store_address_line_1="1234 Main St",
        store_address_line_2="Centennial CO",
        store_phone="(303) 555-1234",
        session_secret_key="x" * 32,
        database_url="sqlite:///:memory:",
        allowed_origins="http://x",
    )


def _cash_sale_row() -> POSTransaction:
    return POSTransaction(
        id="abc12345-6789-0000-0000-000000000000",
        status="COMPLETE",
        txn_type="sale",
        cart_json=json.dumps(
            [
                {
                    "sku": "WIDGET-001",
                    "name": "Widget Mark I",
                    "warehouse_id": "store",
                    "bin_id": "A-3-12",
                    "quantity": 2,
                    "is_taxable": True,
                    "unit_price_cents": 1999,
                    "tax_cents": 324,
                    "line_total_cents": 4322,
                }
            ]
        ),
        subtotal_cents=3998,
        tax_cents=324,
        total_cents=4322,
        payment_method="cash",
        tenders_json=json.dumps(
            [
                {
                    "type": "cash",
                    "amount_cents": 4322,
                    "amount_tendered_cents": 5000,
                    "change_cents": 678,
                }
            ]
        ),
        cashier_id="mike",
        terminal_id="t1",
        created_at=datetime(2026, 5, 8, 14, 23, 11, tzinfo=UTC).replace(tzinfo=None),
        updated_at=datetime(2026, 5, 8, 14, 23, 11, tzinfo=UTC).replace(tzinfo=None),
    )


def _card_sale_row(windcave_xml: str) -> POSTransaction:
    return POSTransaction(
        id="def12345-6789-0000-0000-000000000000",
        status="COMPLETE",
        txn_type="sale",
        cart_json=json.dumps(
            [
                {
                    "sku": "WIDGET-001",
                    "name": "Widget Mark I",
                    "warehouse_id": "store",
                    "bin_id": "A-3-12",
                    "quantity": 1,
                    "is_taxable": True,
                    "unit_price_cents": 1999,
                    "tax_cents": 162,
                    "line_total_cents": 2161,
                }
            ]
        ),
        subtotal_cents=1999,
        tax_cents=162,
        total_cents=2161,
        payment_method="card",
        windcave_txn_ref="0000000100e1a6f9",
        windcave_response_xml=windcave_xml,
        sentry_so_id="SO-2026-04827",
        tenders_json=json.dumps(
            [
                {
                    "type": "card",
                    "amount_cents": 2161,
                    "card_brand": "Visa",
                    "card_last4": "1111",
                    "auth_code": "000289",
                    "external_ref": "0000000100e1a6f9",
                }
            ]
        ),
        cashier_id="mike",
        terminal_id="t1",
        created_at=datetime(2026, 5, 8, 14, 23, 11, tzinfo=UTC).replace(tzinfo=None),
        updated_at=datetime(2026, 5, 8, 14, 23, 11, tzinfo=UTC).replace(tzinfo=None),
    )


WINDCAVE_RCPT_XML = (
    "<Scr><TxnType>Status</TxnType><TxnRef>x</TxnRef><Complete>1</Complete>"
    "<RcptW>30</RcptW><Rcpt>*-EFTPOS-* VISA 1111 APPROVED</Rcpt>"
    "<Result><AP>1</AP><RC>00</RC><CT>Visa</CT><CN>411111******1111</CN>"
    "<TR>0000000100e1a6f9</TR><AmtA>2161</AmtA></Result></Scr>"
)


def test_format_cash_sale_receipt() -> None:
    txn = _cash_sale_row()
    out = format_receipt(txn, settings=_settings())
    lines = out.split("\n")

    # Every line fits the 30-char width
    for line in lines:
        assert len(line) <= RECEIPT_WIDTH, f"line too wide: {line!r}"

    assert "AvidMax" in out
    assert "1234 Main St" in out
    assert "Centennial CO" in out
    assert "(303) 555-1234" in out
    assert "WIDGET-001" in out
    assert "Widget Mark I" in out
    assert "Qty 2 @ $19.99" in out
    assert "$43.22" in out
    assert "Subtotal" in out
    assert "Tax (8.10%)" in out
    assert "TOTAL" in out
    assert "Cash tendered" in out
    assert "$50.00" in out
    assert "Change" in out
    assert "$6.78" in out
    assert "Thank you!" in out
    assert "abc12345" in out


def test_format_card_sale_receipt_uses_windcave_rcpt() -> None:
    txn = _card_sale_row(WINDCAVE_RCPT_XML)
    out = format_receipt(txn, settings=_settings())
    assert "*-EFTPOS-* VISA 1111 APPROVED" in out
    assert "Subtotal" in out
    assert "TOTAL" in out
    assert "Paid: Visa ****1111" in out
    assert "Auth: 000289" in out


def test_format_card_sale_receipt_falls_back_to_cart_when_xml_empty() -> None:
    txn = _card_sale_row(windcave_xml="")
    out = format_receipt(txn, settings=_settings())
    assert "WIDGET-001" in out
    assert "Qty 1 @ $19.99" in out


def test_format_cash_refund_receipt() -> None:
    parent = _cash_sale_row()
    refund = POSTransaction(
        id="ref12345-6789-0000-0000-000000000000",
        status="COMPLETE",
        txn_type="refund",
        parent_transaction_id=parent.id,
        cart_json=json.dumps(
            [
                {
                    **json.loads(parent.cart_json)[0],
                    "quantity": -2,
                    "tax_cents": -324,
                    "line_total_cents": -4322,
                }
            ]
        ),
        subtotal_cents=-3998,
        tax_cents=-324,
        total_cents=-4322,
        payment_method="cash",
        sentry_so_id="SO-2026-04901",
        tenders_json=json.dumps([{"type": "cash", "amount_cents": -4322}]),
        cashier_id="mike",
        terminal_id="t1",
        created_at=datetime(2026, 5, 9, 10, 14, 2, tzinfo=UTC).replace(tzinfo=None),
        updated_at=datetime(2026, 5, 9, 10, 14, 2, tzinfo=UTC).replace(tzinfo=None),
    )
    out = format_receipt(refund, settings=_settings(), parent=parent)
    lines = out.split("\n")
    for line in lines:
        assert len(line) <= RECEIPT_WIDTH

    assert "REFUND" in out
    assert f"Orig txn: {parent.id[:12]}" in out
    assert "Refund subtotal" in out
    assert "-$39.98" in out
    assert "Refund tax (8.10%)" in out
    assert "REFUND TOTAL" in out
    assert "-$43.22" in out
    assert "Cash returned" in out
    assert "$43.22" in out
    assert "Thank you!" not in out
    assert "Refund txn:" in out


def test_format_card_refund_receipt_uses_refund_xml() -> None:
    parent = _card_sale_row(WINDCAVE_RCPT_XML)
    refund_xml = (
        "<Scr><TxnType>Status</TxnType><TxnRef>x</TxnRef><Complete>1</Complete>"
        "<RcptW>30</RcptW><Rcpt>*-EFTPOS-* REFUND APPROVED</Rcpt>"
        "<Result><AP>1</AP><RC>00</RC><CT>Visa</CT><CN>411111******1111</CN>"
        "<TR>0000000200999999</TR><AmtA>2161</AmtA></Result></Scr>"
    )
    refund = POSTransaction(
        id="rf123456-6789-0000-0000-000000000000",
        status="COMPLETE",
        txn_type="refund",
        parent_transaction_id=parent.id,
        cart_json=json.dumps(
            [
                {
                    **json.loads(parent.cart_json)[0],
                    "quantity": -1,
                    "tax_cents": -162,
                    "line_total_cents": -2161,
                }
            ]
        ),
        subtotal_cents=-1999,
        tax_cents=-162,
        total_cents=-2161,
        payment_method="card",
        windcave_txn_ref="0000000200999999",
        windcave_response_xml=refund_xml,
        sentry_so_id="SO-2026-04901",
        tenders_json=json.dumps(
            [
                {
                    "type": "card",
                    "amount_cents": -2161,
                    "card_brand": "Visa",
                    "card_last4": "1111",
                    "auth_code": "000291",
                    "external_ref": "0000000200999999",
                }
            ]
        ),
        cashier_id="mike",
        terminal_id="t1",
        created_at=datetime(2026, 5, 9, 10, 14, 2, tzinfo=UTC).replace(tzinfo=None),
        updated_at=datetime(2026, 5, 9, 10, 14, 2, tzinfo=UTC).replace(tzinfo=None),
    )
    out = format_receipt(refund, settings=_settings(), parent=parent)
    assert "REFUND" in out
    assert "*-EFTPOS-* REFUND APPROVED" in out
    assert "Refunded to: Visa ****1111" in out
    assert "REFUND TOTAL" in out
    assert "-$21.61" in out


def test_format_receipt_handles_empty_store_info() -> None:
    settings = Settings(
        sentry_base_url="http://x",
        sentry_api_token="x",
        windcave_base_url="http://x",
        windcave_user="x",
        windcave_key="x",
        windcave_station="x",
        tax_rate=0.0810,
        store_name="AvidMax",
        store_address_line_1="",
        store_address_line_2="",
        store_phone="",
        session_secret_key="x" * 32,
        database_url="sqlite:///:memory:",
        allowed_origins="http://x",
    )
    txn = _cash_sale_row()
    out = format_receipt(txn, settings=settings)
    assert "AvidMax" in out


# --- Endpoint integration ---


def _login_cashier(client: TestClient, cashier: POSUser) -> None:
    client.post(
        "/api/auth/login", json={"username": "mike", "password": "supersecret"}
    )


def _validate_cart_ok() -> None:
    respx.post(f"{SENTRY_BASE}/api/v1/pos/validate-cart").mock(
        return_value=httpx.Response(200, json={"valid": True})
    )


@respx.mock
def test_checkout_status_includes_receipt_content_after_cash_sale(
    client: TestClient, cashier: POSUser, db: Session
) -> None:
    db.add(POSPrice(sku="WIDGET-001", unit_price_cents=1999))
    db.commit()
    _validate_cart_ok()
    respx.post(f"{SENTRY_BASE}/api/v1/pos/checkout").mock(
        return_value=httpx.Response(
            200, json={"so_id": "SO-1", "so_number": "SO-1", "replayed": False}
        )
    )
    _login_cashier(client, cashier)
    started = client.post(
        "/api/checkout/start",
        json={
            "lines": [
                {
                    "sku": "WIDGET-001",
                    "name": "Widget Mark I",
                    "warehouse_id": "store",
                    "bin_id": "A-3-12",
                    "quantity": 1,
                    "is_taxable": True,
                }
            ]
        },
    ).json()
    txn_id = started["transaction_id"]
    client.post(
        f"/api/checkout/{txn_id}/charge-cash",
        json={"amount_tendered_cents": 3000},
    )
    r = client.get(f"/api/checkout/{txn_id}/status")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "COMPLETE"
    rc = body["result"]["receipt_content"]
    assert "WIDGET-001" in rc
    assert "Widget Mark I" in rc
    assert "TOTAL" in rc
    assert "Cash tendered" in rc


@respx.mock
def test_refund_status_includes_receipt_content_after_cash_refund(
    client: TestClient, cashier: POSUser, db: Session
) -> None:
    db.add(POSPrice(sku="WIDGET-001", unit_price_cents=1999))
    db.commit()
    _validate_cart_ok()
    respx.post(f"{SENTRY_BASE}/api/v1/pos/checkout").mock(
        return_value=httpx.Response(
            200,
            json={"so_id": "SO-PARENT", "so_number": "SO-PARENT", "replayed": False},
        )
    )
    respx.post(f"{SENTRY_BASE}/api/v1/pos/refund").mock(
        return_value=httpx.Response(
            200,
            json={
                "refund_so_id": "SO-REFUND",
                "original_so_id": "SO-PARENT",
                "replayed": False,
            },
        )
    )
    _login_cashier(client, cashier)
    started = client.post(
        "/api/checkout/start",
        json={
            "lines": [
                {
                    "sku": "WIDGET-001",
                    "name": "Widget Mark I",
                    "warehouse_id": "store",
                    "bin_id": "A-3-12",
                    "quantity": 1,
                    "is_taxable": True,
                }
            ]
        },
    ).json()
    sale_id = started["transaction_id"]
    client.post(
        f"/api/checkout/{sale_id}/charge-cash",
        json={"amount_tendered_cents": 3000},
    )
    refund = client.post(
        "/api/refunds/start", json={"original_transaction_id": sale_id}
    ).json()
    refund_id = refund["refund_transaction_id"]
    client.post(f"/api/refunds/{refund_id}/charge-cash")
    r = client.get(f"/api/refunds/{refund_id}/status")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "COMPLETE"
    rc = body["result"]["receipt_content"]
    assert "REFUND" in rc
    assert "REFUND TOTAL" in rc
    assert "Orig txn:" in rc
    assert sale_id[:12] in rc
