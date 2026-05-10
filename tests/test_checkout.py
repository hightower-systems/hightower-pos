import json

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from pos_service.models import POSPrice, POSTransaction, POSUser
from pos_service.services.checkout import compute_line_tax

SENTRY_BASE = "http://sentry.test"
WINDCAVE_BASE = "http://windcave.test"


def _login_cashier(client: TestClient, cashier: POSUser) -> None:
    r = client.post(
        "/api/auth/login", json={"username": "mike", "password": "supersecret"}
    )
    assert r.status_code == 200


def _seed_prices(db: Session, *items: tuple[str, int]) -> None:
    for sku, cents in items:
        db.add(POSPrice(sku=sku, unit_price_cents=cents))
    db.commit()


def _validate_cart_ok() -> None:
    respx.post(f"{SENTRY_BASE}/api/v1/pos/validate-cart").mock(
        return_value=httpx.Response(200, json={"valid": True})
    )


def _start_cart(client: TestClient) -> dict:
    r = client.post(
        "/api/checkout/start",
        json={
            "lines": [
                {
                    "sku": "WIDGET-001",
                    "warehouse_id": "store",
                    "bin_id": "A-3-12",
                    "quantity": 1,
                    "is_taxable": True,
                }
            ]
        },
    )
    return r.json()


@pytest.fixture
def windcave_mock_mode(settings):
    settings.windcave_mock = True
    yield
    settings.windcave_mock = False


def test_compute_line_tax_zero_when_not_taxable() -> None:
    assert compute_line_tax(1999, 0.0810, taxable=False) == 0


def test_compute_line_tax_basic_rate() -> None:
    # 1999 * 0.0810 = 161.919 -> 162
    assert compute_line_tax(1999, 0.0810, taxable=True) == 162
    # 5398 * 0.0810 = 437.238 -> 437
    assert compute_line_tax(5398, 0.0810, taxable=True) == 437
    # 100 * 0.05 = 5.0 -> 5
    assert compute_line_tax(100, 0.05, taxable=True) == 5


def test_compute_line_tax_banker_rounding_at_half() -> None:
    # 50 * 0.05 = 2.50 -> ROUND_HALF_EVEN -> 2 (nearest even)
    assert compute_line_tax(50, 0.05, taxable=True) == 2
    # 30 * 0.05 = 1.50 -> ROUND_HALF_EVEN -> 2 (nearest even)
    assert compute_line_tax(30, 0.05, taxable=True) == 2


def test_start_requires_auth(client: TestClient) -> None:
    r = client.post(
        "/api/checkout/start",
        json={
            "lines": [
                {
                    "sku": "X",
                    "warehouse_id": "s",
                    "bin_id": "b",
                    "quantity": 1,
                    "is_taxable": True,
                }
            ]
        },
    )
    assert r.status_code == 401


@respx.mock
def test_start_happy_path_single_taxable_line(
    client: TestClient, cashier: POSUser, db: Session
) -> None:
    _seed_prices(db, ("WIDGET-001", 1999))
    _validate_cart_ok()
    _login_cashier(client, cashier)
    r = client.post(
        "/api/checkout/start",
        json={
            "lines": [
                {
                    "sku": "WIDGET-001",
                    "warehouse_id": "store",
                    "bin_id": "A-3-12",
                    "quantity": 1,
                    "is_taxable": True,
                }
            ]
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "AWAITING_PAYMENT"
    assert body["subtotal_cents"] == 1999
    assert body["tax_cents"] == 162
    assert body["total_cents"] == 2161
    assert body["transaction_id"]
    txn_row = db.get(POSTransaction, body["transaction_id"])
    assert txn_row is not None
    assert txn_row.status == "AWAITING_PAYMENT"
    cart = json.loads(txn_row.cart_json)
    assert cart[0]["unit_price_cents"] == 1999
    assert cart[0]["tax_cents"] == 162


@respx.mock
def test_start_with_non_taxable_line_skips_tax(
    client: TestClient, cashier: POSUser, db: Session
) -> None:
    _seed_prices(db, ("STAMP-1", 100))
    _validate_cart_ok()
    _login_cashier(client, cashier)
    r = client.post(
        "/api/checkout/start",
        json={
            "lines": [
                {
                    "sku": "STAMP-1",
                    "warehouse_id": "store",
                    "bin_id": "A-1-1",
                    "quantity": 2,
                    "is_taxable": False,
                }
            ]
        },
    )
    assert r.status_code == 200
    assert r.json()["tax_cents"] == 0
    assert r.json()["total_cents"] == 200


def test_start_missing_price_returns_422(
    client: TestClient, cashier: POSUser
) -> None:
    _login_cashier(client, cashier)
    r = client.post(
        "/api/checkout/start",
        json={
            "lines": [
                {
                    "sku": "NO-PRICE",
                    "warehouse_id": "store",
                    "bin_id": "A-1-1",
                    "quantity": 1,
                    "is_taxable": True,
                }
            ]
        },
    )
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "price_missing"
    assert "NO-PRICE" in r.json()["detail"]["skus_without_price"]


@respx.mock
def test_start_validation_409_marks_validation_failed_and_returns_conflicts(
    client: TestClient, cashier: POSUser, db: Session
) -> None:
    _seed_prices(db, ("WIDGET-001", 1999))
    respx.post(f"{SENTRY_BASE}/api/v1/pos/validate-cart").mock(
        return_value=httpx.Response(
            409,
            json={
                "valid": False,
                "conflicts": [
                    {
                        "line_index": 0,
                        "sku": "WIDGET-001",
                        "warehouse_id": "store",
                        "bin_id": "A-3-12",
                        "requested_qty": 1,
                        "available_qty": 0,
                        "reason": "insufficient_stock",
                    }
                ],
            },
        )
    )
    _login_cashier(client, cashier)
    r = client.post(
        "/api/checkout/start",
        json={
            "lines": [
                {
                    "sku": "WIDGET-001",
                    "warehouse_id": "store",
                    "bin_id": "A-3-12",
                    "quantity": 1,
                    "is_taxable": True,
                }
            ]
        },
    )
    assert r.status_code == 409
    body = r.json()
    assert body["detail"]["error"] == "validation_failed"
    assert body["detail"]["conflicts"][0]["reason"] == "insufficient_stock"


@respx.mock
def test_charge_cash_happy_path(
    client: TestClient, cashier: POSUser, db: Session
) -> None:
    _seed_prices(db, ("WIDGET-001", 1999))
    _validate_cart_ok()
    respx.post(f"{SENTRY_BASE}/api/v1/pos/checkout").mock(
        return_value=httpx.Response(
            200,
            json={"so_id": "SO-2026-001", "so_number": "SO-2026-001", "replayed": False},
        )
    )
    _login_cashier(client, cashier)
    started = _start_cart(client)
    txn_id = started["transaction_id"]
    r = client.post(
        f"/api/checkout/{txn_id}/charge-cash",
        json={"amount_tendered_cents": 3000},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "COMPLETE"
    assert body["change_cents"] == 3000 - 2161
    assert body["so_id"] == "SO-2026-001"


@respx.mock
def test_charge_cash_insufficient_tender(
    client: TestClient, cashier: POSUser, db: Session
) -> None:
    _seed_prices(db, ("WIDGET-001", 1999))
    _validate_cart_ok()
    _login_cashier(client, cashier)
    started = _start_cart(client)
    txn_id = started["transaction_id"]
    r = client.post(
        f"/api/checkout/{txn_id}/charge-cash",
        json={"amount_tendered_cents": 100},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "insufficient_tender"


def test_charge_cash_unknown_transaction(
    client: TestClient, cashier: POSUser
) -> None:
    _login_cashier(client, cashier)
    r = client.post(
        "/api/checkout/unknown-id/charge-cash",
        json={"amount_tendered_cents": 1000},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "transaction_not_found"


@respx.mock
def test_charge_cash_sentry_failure_marks_inventory_update_failed(
    client: TestClient, cashier: POSUser, db: Session
) -> None:
    _seed_prices(db, ("WIDGET-001", 1999))
    _validate_cart_ok()
    respx.post(f"{SENTRY_BASE}/api/v1/pos/checkout").mock(
        return_value=httpx.Response(422, json={"error": "fulfillment_failed"})
    )
    activity_log = respx.post(f"{SENTRY_BASE}/api/inbound-activity-log").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    _login_cashier(client, cashier)
    started = _start_cart(client)
    txn_id = started["transaction_id"]
    r = client.post(
        f"/api/checkout/{txn_id}/charge-cash",
        json={"amount_tendered_cents": 3000},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "INVENTORY_UPDATE_FAILED"
    assert activity_log.called


@respx.mock
def test_charge_card_mock_mode_completes_synchronously(
    client: TestClient,
    cashier: POSUser,
    db: Session,
    windcave_mock_mode,
) -> None:
    _seed_prices(db, ("WIDGET-001", 1999))
    _validate_cart_ok()
    respx.post(f"{SENTRY_BASE}/api/v1/pos/checkout").mock(
        return_value=httpx.Response(
            200,
            json={"so_id": "SO-MOCK", "so_number": "SO-MOCK", "replayed": False},
        )
    )
    _login_cashier(client, cashier)
    started = _start_cart(client)
    txn_id = started["transaction_id"]
    r = client.post(f"/api/checkout/{txn_id}/charge-card")
    assert r.status_code == 200
    assert r.json()["status"] == "COMPLETE"
    txn_row = db.get(POSTransaction, txn_id)
    assert txn_row.sentry_so_id == "SO-MOCK"


INITIAL_INCOMPLETE_XML = """<Scr>
  <TxnType>Status</TxnType>
  <TxnRef>txn-id</TxnRef>
  <StatusId>3</StatusId>
  <TxnStatusId>2</TxnStatusId>
  <Complete>0</Complete>
  <ReCo/>
  <Tmo>20</Tmo>
  <DL1>PRESENT/INSERT</DL1>
  <DL2>SWIPE CARD</DL2>
  <B1 en="0"/>
  <B2 en="1">CANCEL</B2>
</Scr>"""


def _final_approved_xml(txn_ref: str) -> str:
    return f"""<Scr>
  <TxnType>Status</TxnType>
  <TxnRef>{txn_ref}</TxnRef>
  <StatusId>6</StatusId>
  <TxnStatusId>8</TxnStatusId>
  <Complete>1</Complete>
  <RcptW>30</RcptW>
  <Rcpt>*-EFTPOS-* APPROVED</Rcpt>
  <Result>
    <AC>000289</AC>
    <AP>1</AP>
    <CN>411111******1111</CN>
    <CT>Visa</CT>
    <DT>20260508140000</DT>
    <RC>00</RC>
    <RT></RT>
    <TR>0000000100e1a6f9</TR>
    <AmtA>2161</AmtA>
  </Result>
  <ReCo></ReCo>
  <Tmo>20</Tmo>
  <DL1>APPROVED</DL1>
</Scr>"""


def _final_declined_xml(txn_ref: str) -> str:
    return f"""<Scr>
  <TxnType>Status</TxnType>
  <TxnRef>{txn_ref}</TxnRef>
  <StatusId>6</StatusId>
  <TxnStatusId>8</TxnStatusId>
  <Complete>1</Complete>
  <Result>
    <AP>0</AP>
    <CN>411111******2222</CN>
    <CT>Visa</CT>
    <DT>20260508140000</DT>
    <RC>05</RC>
    <RT>DO NOT HONOUR</RT>
    <TR>0000000200000001</TR>
    <AmtA>2161</AmtA>
  </Result>
  <ReCo></ReCo>
  <Tmo>20</Tmo>
  <DL1>DECLINED</DL1>
</Scr>"""


def _signature_complete_xml(txn_ref: str) -> str:
    return f"""<Scr>
  <TxnType>Status</TxnType>
  <TxnRef>{txn_ref}</TxnRef>
  <StatusId>4</StatusId>
  <TxnStatusId>7</TxnStatusId>
  <Complete>1</Complete>
  <RcptW>30</RcptW>
  <Rcpt>signature receipt</Rcpt>
  <ReCo></ReCo>
  <Tmo>20</Tmo>
  <DL1>SIGNATURE OK?</DL1>
  <DL2>YES/NO</DL2>
  <B1 en="1">YES</B1>
  <B2 en="1">NO</B2>
</Scr>"""


@respx.mock
def test_charge_card_real_path_polls_until_approved(
    client: TestClient, cashier: POSUser, db: Session
) -> None:
    _seed_prices(db, ("WIDGET-001", 1999))
    _validate_cart_ok()
    respx.post(f"{SENTRY_BASE}/api/v1/pos/checkout").mock(
        return_value=httpx.Response(
            200, json={"so_id": "SO-X", "so_number": "SO-X", "replayed": False}
        )
    )
    _login_cashier(client, cashier)
    started = _start_cart(client)
    txn_id = started["transaction_id"]
    respx.post(WINDCAVE_BASE).mock(
        side_effect=[
            httpx.Response(200, content=INITIAL_INCOMPLETE_XML),
            httpx.Response(200, content=INITIAL_INCOMPLETE_XML),
            httpx.Response(200, content=_final_approved_xml(txn_id)),
        ]
    )
    r = client.post(f"/api/checkout/{txn_id}/charge-card")
    assert r.status_code == 200
    txn_row = db.get(POSTransaction, txn_id)
    db.refresh(txn_row)
    assert txn_row.status == "COMPLETE"
    assert txn_row.windcave_txn_ref == "0000000100e1a6f9"
    assert txn_row.sentry_so_id == "SO-X"


@respx.mock
def test_charge_card_declined_marks_payment_failed(
    client: TestClient, cashier: POSUser, db: Session
) -> None:
    _seed_prices(db, ("WIDGET-001", 1999))
    _validate_cart_ok()
    _login_cashier(client, cashier)
    started = _start_cart(client)
    txn_id = started["transaction_id"]
    respx.post(WINDCAVE_BASE).mock(
        side_effect=[
            httpx.Response(200, content=INITIAL_INCOMPLETE_XML),
            httpx.Response(200, content=_final_declined_xml(txn_id)),
        ]
    )
    r = client.post(f"/api/checkout/{txn_id}/charge-card")
    assert r.status_code == 200
    txn_row = db.get(POSTransaction, txn_id)
    db.refresh(txn_row)
    assert txn_row.status == "PAYMENT_FAILED"
    assert "DO NOT HONOUR" in (txn_row.last_error or "")


@respx.mock
def test_charge_card_complete_with_signature_required_fails(
    client: TestClient, cashier: POSUser, db: Session
) -> None:
    _seed_prices(db, ("WIDGET-001", 1999))
    _validate_cart_ok()
    _login_cashier(client, cashier)
    started = _start_cart(client)
    txn_id = started["transaction_id"]
    respx.post(WINDCAVE_BASE).mock(
        side_effect=[
            httpx.Response(200, content=INITIAL_INCOMPLETE_XML),
            httpx.Response(200, content=_signature_complete_xml(txn_id)),
        ]
    )
    r = client.post(f"/api/checkout/{txn_id}/charge-card")
    assert r.status_code == 200
    txn_row = db.get(POSTransaction, txn_id)
    db.refresh(txn_row)
    assert txn_row.status == "PAYMENT_FAILED"
    assert "signature" in (txn_row.last_error or "")


@respx.mock
def test_charge_card_polling_timeout_fails(
    client: TestClient, cashier: POSUser, db: Session
) -> None:
    _seed_prices(db, ("WIDGET-001", 1999))
    _validate_cart_ok()
    _login_cashier(client, cashier)
    started = _start_cart(client)
    txn_id = started["transaction_id"]
    respx.post(WINDCAVE_BASE).mock(
        return_value=httpx.Response(200, content=INITIAL_INCOMPLETE_XML)
    )
    r = client.post(f"/api/checkout/{txn_id}/charge-card")
    assert r.status_code == 200
    txn_row = db.get(POSTransaction, txn_id)
    db.refresh(txn_row)
    assert txn_row.status == "PAYMENT_FAILED"
    assert txn_row.last_error == "polling_timeout"


@respx.mock
def test_status_endpoint_for_in_progress_and_complete(
    client: TestClient, cashier: POSUser, db: Session
) -> None:
    _seed_prices(db, ("WIDGET-001", 1999))
    _validate_cart_ok()
    _login_cashier(client, cashier)
    started = _start_cart(client)
    txn_id = started["transaction_id"]
    r = client.get(f"/api/checkout/{txn_id}/status")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "AWAITING_PAYMENT"
    assert body["is_terminal"] is False
    assert body["result"] is None

    respx.post(f"{SENTRY_BASE}/api/v1/pos/checkout").mock(
        return_value=httpx.Response(
            200, json={"so_id": "SO-1", "so_number": "SO-1", "replayed": False}
        )
    )
    client.post(
        f"/api/checkout/{txn_id}/charge-cash",
        json={"amount_tendered_cents": 3000},
    )
    r = client.get(f"/api/checkout/{txn_id}/status")
    body = r.json()
    assert body["status"] == "COMPLETE"
    assert body["is_terminal"] is True
    assert body["result"]["so_id"] == "SO-1"
    assert body["result"]["payment_method"] == "cash"


def test_status_unknown_transaction_returns_404(
    client: TestClient, cashier: POSUser
) -> None:
    _login_cashier(client, cashier)
    r = client.get("/api/checkout/unknown/status")
    assert r.status_code == 404


@respx.mock
def test_cancel_awaiting_payment(
    client: TestClient, cashier: POSUser, db: Session
) -> None:
    _seed_prices(db, ("WIDGET-001", 1999))
    _validate_cart_ok()
    _login_cashier(client, cashier)
    started = _start_cart(client)
    txn_id = started["transaction_id"]
    r = client.post(f"/api/checkout/{txn_id}/cancel")
    assert r.status_code == 200
    assert r.json()["status"] == "CANCELLED"


@respx.mock
def test_cancel_after_complete_returns_400(
    client: TestClient, cashier: POSUser, db: Session
) -> None:
    _seed_prices(db, ("WIDGET-001", 1999))
    _validate_cart_ok()
    respx.post(f"{SENTRY_BASE}/api/v1/pos/checkout").mock(
        return_value=httpx.Response(
            200, json={"so_id": "SO-1", "so_number": "SO-1", "replayed": False}
        )
    )
    _login_cashier(client, cashier)
    started = _start_cart(client)
    txn_id = started["transaction_id"]
    client.post(
        f"/api/checkout/{txn_id}/charge-cash",
        json={"amount_tendered_cents": 3000},
    )
    r = client.post(f"/api/checkout/{txn_id}/cancel")
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "invalid_state"
