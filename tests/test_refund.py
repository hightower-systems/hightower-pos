import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from pos_service.models import POSPrice, POSTransaction, POSUser

SENTRY_BASE = "http://sentry.test"
WINDCAVE_BASE = "http://windcave.test"


def _login_cashier(client: TestClient, cashier: POSUser) -> None:
    client.post(
        "/api/auth/login", json={"username": "mike", "password": "supersecret"}
    )


def _validate_cart_ok() -> None:
    respx.post(f"{SENTRY_BASE}/api/v1/pos/validate-cart").mock(
        return_value=httpx.Response(200, json={"valid": True})
    )


def _seed_prices(db: Session, *items: tuple[str, int]) -> None:
    for sku, cents in items:
        db.add(POSPrice(sku=sku, unit_price_cents=cents))
    db.commit()


def _start_cart(client: TestClient) -> str:
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
    return r.json()["transaction_id"]


@pytest.fixture
def windcave_mock_mode(settings):
    settings.windcave_mock = True
    yield
    settings.windcave_mock = False


def _completed_cash_sale(
    client: TestClient, db: Session, cashier: POSUser
) -> str:
    """Helper that drives a real cash sale through to COMPLETE and returns
    the transaction id, so refund tests have a refundable parent."""
    _seed_prices(db, ("WIDGET-001", 1999))
    _validate_cart_ok()
    respx.post(f"{SENTRY_BASE}/api/v1/pos/checkout").mock(
        return_value=httpx.Response(
            200,
            json={"so_id": "SO-PARENT", "so_number": "SO-PARENT", "replayed": False},
        )
    )
    _login_cashier(client, cashier)
    txn_id = _start_cart(client)
    r = client.post(
        f"/api/checkout/{txn_id}/charge-cash",
        json={"amount_tendered_cents": 3000},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "COMPLETE"
    return txn_id


def _completed_card_sale(
    client: TestClient, db: Session, cashier: POSUser, settings
) -> str:
    """Helper that drives a real card sale through to COMPLETE in mock mode
    so the parent has a windcave_txn_ref the refund can reference."""
    settings.windcave_mock = True
    try:
        _seed_prices(db, ("WIDGET-001", 1999))
        _validate_cart_ok()
        respx.post(f"{SENTRY_BASE}/api/v1/pos/checkout").mock(
            return_value=httpx.Response(
                200,
                json={
                    "so_id": "SO-CARD-PARENT",
                    "so_number": "SO-CARD-PARENT",
                    "replayed": False,
                },
            )
        )
        _login_cashier(client, cashier)
        txn_id = _start_cart(client)
        r = client.post(f"/api/checkout/{txn_id}/charge-card")
        assert r.status_code == 200
        assert r.json()["status"] == "COMPLETE"
        return txn_id
    finally:
        settings.windcave_mock = False


@respx.mock
def test_lookup_requires_auth(client: TestClient) -> None:
    r = client.get("/api/refunds/lookup", params={"transaction_id": "x"})
    assert r.status_code == 401


@respx.mock
def test_lookup_404_unknown_transaction(client: TestClient, cashier: POSUser) -> None:
    _login_cashier(client, cashier)
    r = client.get("/api/refunds/lookup", params={"transaction_id": "unknown"})
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "transaction_not_found"


@respx.mock
def test_lookup_happy_path_for_completed_cash_sale(
    client: TestClient, cashier: POSUser, db: Session
) -> None:
    txn_id = _completed_cash_sale(client, db, cashier)
    r = client.get("/api/refunds/lookup", params={"transaction_id": txn_id})
    assert r.status_code == 200
    body = r.json()
    assert body["original_transaction_id"] == txn_id
    assert body["payment_method"] == "cash"
    assert body["original_sentry_so_id"] == "SO-PARENT"
    assert body["total_cents"] == 2161
    assert body["refundable"] is True
    assert len(body["lines"]) == 1


@respx.mock
def test_lookup_for_non_complete_sale_returns_422(
    client: TestClient, cashier: POSUser, db: Session
) -> None:
    _seed_prices(db, ("WIDGET-001", 1999))
    _validate_cart_ok()
    _login_cashier(client, cashier)
    txn_id = _start_cart(client)  # status will be AWAITING_PAYMENT
    r = client.get("/api/refunds/lookup", params={"transaction_id": txn_id})
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "not_a_completed_sale"


@respx.mock
def test_lookup_window_expired(
    client: TestClient, cashier: POSUser, db: Session, settings
) -> None:
    txn_id = _completed_cash_sale(client, db, cashier)
    # Backdate the original sale beyond the refund window
    txn = db.get(POSTransaction, txn_id)
    txn.created_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(
        days=settings.refund_window_days + 1
    )
    db.commit()
    r = client.get("/api/refunds/lookup", params={"transaction_id": txn_id})
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "refund_window_expired"
    assert r.json()["detail"]["days_since_sale"] >= settings.refund_window_days + 1


@respx.mock
def test_start_creates_pending_refund_with_negated_totals(
    client: TestClient, cashier: POSUser, db: Session
) -> None:
    txn_id = _completed_cash_sale(client, db, cashier)
    r = client.post(
        "/api/refunds/start", json={"original_transaction_id": txn_id}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "REFUND_PENDING"
    assert body["payment_method"] == "cash"
    assert body["subtotal_cents"] == -1999
    assert body["tax_cents"] == -162
    assert body["total_cents"] == -2161

    refund_id = body["refund_transaction_id"]
    refund_row = db.get(POSTransaction, refund_id)
    assert refund_row.txn_type == "refund"
    assert refund_row.parent_transaction_id == txn_id
    cart = json.loads(refund_row.cart_json)
    assert cart[0]["quantity"] == -1
    assert cart[0]["line_total_cents"] == -2161


@respx.mock
def test_start_blocks_already_pending_refund(
    client: TestClient, cashier: POSUser, db: Session
) -> None:
    txn_id = _completed_cash_sale(client, db, cashier)
    first = client.post(
        "/api/refunds/start", json={"original_transaction_id": txn_id}
    )
    assert first.status_code == 200
    second = client.post(
        "/api/refunds/start", json={"original_transaction_id": txn_id}
    )
    assert second.status_code == 422
    assert second.json()["detail"]["error"] == "already_refunded"
    assert (
        second.json()["detail"]["refund_transaction_id"]
        == first.json()["refund_transaction_id"]
    )


@respx.mock
def test_charge_cash_refund_happy_path(
    client: TestClient, cashier: POSUser, db: Session
) -> None:
    txn_id = _completed_cash_sale(client, db, cashier)
    refund_route = respx.post(f"{SENTRY_BASE}/api/v1/pos/refund").mock(
        return_value=httpx.Response(
            200,
            json={
                "refund_so_id": "SO-REFUND-001",
                "original_so_id": "SO-PARENT",
                "replayed": False,
            },
        )
    )
    started = client.post(
        "/api/refunds/start", json={"original_transaction_id": txn_id}
    ).json()
    refund_id = started["refund_transaction_id"]
    r = client.post(f"/api/refunds/{refund_id}/charge-cash")
    assert r.status_code == 200
    assert r.json()["status"] == "COMPLETE"
    assert r.json()["refund_so_id"] == "SO-REFUND-001"
    assert refund_route.called

    refund_row = db.get(POSTransaction, refund_id)
    assert refund_row.sentry_so_id == "SO-REFUND-001"

    # Original is now linked to the refund row
    db.refresh(refund_row)
    original = db.get(POSTransaction, txn_id)
    db.refresh(original)
    assert original.refund_transaction_id == refund_id


@respx.mock
def test_charge_cash_refund_tender_mismatch_against_card_sale(
    client: TestClient, cashier: POSUser, db: Session, settings
) -> None:
    txn_id = _completed_card_sale(client, db, cashier, settings)
    started = client.post(
        "/api/refunds/start", json={"original_transaction_id": txn_id}
    ).json()
    refund_id = started["refund_transaction_id"]
    r = client.post(f"/api/refunds/{refund_id}/charge-cash")
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "tender_mismatch"


@respx.mock
def test_charge_card_refund_tender_mismatch_against_cash_sale(
    client: TestClient, cashier: POSUser, db: Session
) -> None:
    txn_id = _completed_cash_sale(client, db, cashier)
    started = client.post(
        "/api/refunds/start", json={"original_transaction_id": txn_id}
    ).json()
    refund_id = started["refund_transaction_id"]
    r = client.post(f"/api/refunds/{refund_id}/charge-card")
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "tender_mismatch"


@respx.mock
def test_charge_card_refund_mock_mode_completes(
    client: TestClient,
    cashier: POSUser,
    db: Session,
    settings,
    windcave_mock_mode,
) -> None:
    txn_id = _completed_card_sale(client, db, cashier, settings)
    settings.windcave_mock = True  # turn back on after the sale helper turned it off
    respx.post(f"{SENTRY_BASE}/api/v1/pos/refund").mock(
        return_value=httpx.Response(
            200,
            json={
                "refund_so_id": "SO-MOCK-RF",
                "original_so_id": "SO-CARD-PARENT",
                "replayed": False,
            },
        )
    )
    started = client.post(
        "/api/refunds/start", json={"original_transaction_id": txn_id}
    ).json()
    refund_id = started["refund_transaction_id"]
    r = client.post(f"/api/refunds/{refund_id}/charge-card")
    assert r.status_code == 200
    assert r.json()["status"] == "COMPLETE"


INITIAL_INCOMPLETE_XML = """<Scr>
  <TxnType>Status</TxnType>
  <TxnRef>x</TxnRef>
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


def _final_approved_refund_xml(txn_ref: str) -> str:
    return f"""<Scr>
  <TxnType>Status</TxnType>
  <TxnRef>{txn_ref}</TxnRef>
  <StatusId>6</StatusId>
  <TxnStatusId>8</TxnStatusId>
  <Complete>1</Complete>
  <RcptW>30</RcptW>
  <Rcpt>*-EFTPOS-* REFUND APPROVED</Rcpt>
  <Result>
    <AC>000291</AC>
    <AP>1</AP>
    <CN>411111******1111</CN>
    <CT>Visa</CT>
    <DT>20260509101402</DT>
    <RC>00</RC>
    <RT></RT>
    <TR>0000000200999999</TR>
    <AmtA>2161</AmtA>
  </Result>
  <ReCo></ReCo>
  <Tmo>20</Tmo>
  <DL1>APPROVED</DL1>
</Scr>"""


def _final_declined_refund_xml(txn_ref: str) -> str:
    return f"""<Scr>
  <TxnType>Status</TxnType>
  <TxnRef>{txn_ref}</TxnRef>
  <StatusId>6</StatusId>
  <TxnStatusId>8</TxnStatusId>
  <Complete>1</Complete>
  <Result>
    <AP>0</AP>
    <RC>05</RC>
    <RT>DO NOT HONOUR</RT>
    <TR>0000000200000002</TR>
    <AmtA>2161</AmtA>
  </Result>
  <ReCo></ReCo>
  <Tmo>20</Tmo>
  <DL1>DECLINED</DL1>
</Scr>"""


@respx.mock
def test_charge_card_refund_real_path_polls_until_approved(
    client: TestClient, cashier: POSUser, db: Session, settings
) -> None:
    txn_id = _completed_card_sale(client, db, cashier, settings)
    respx.post(f"{SENTRY_BASE}/api/v1/pos/refund").mock(
        return_value=httpx.Response(
            200,
            json={
                "refund_so_id": "SO-RF-X",
                "original_so_id": "SO-CARD-PARENT",
                "replayed": False,
            },
        )
    )
    started = client.post(
        "/api/refunds/start", json={"original_transaction_id": txn_id}
    ).json()
    refund_id = started["refund_transaction_id"]
    respx.post(WINDCAVE_BASE).mock(
        side_effect=[
            httpx.Response(200, content=INITIAL_INCOMPLETE_XML),
            httpx.Response(200, content=INITIAL_INCOMPLETE_XML),
            httpx.Response(200, content=_final_approved_refund_xml(refund_id)),
        ]
    )
    r = client.post(f"/api/refunds/{refund_id}/charge-card")
    assert r.status_code == 200
    refund_row = db.get(POSTransaction, refund_id)
    db.refresh(refund_row)
    assert refund_row.status == "COMPLETE"
    assert refund_row.windcave_txn_ref == "0000000200999999"
    assert refund_row.sentry_so_id == "SO-RF-X"
    original = db.get(POSTransaction, txn_id)
    db.refresh(original)
    assert original.refund_transaction_id == refund_id


@respx.mock
def test_charge_card_refund_declined_marks_payment_failed(
    client: TestClient, cashier: POSUser, db: Session, settings
) -> None:
    txn_id = _completed_card_sale(client, db, cashier, settings)
    started = client.post(
        "/api/refunds/start", json={"original_transaction_id": txn_id}
    ).json()
    refund_id = started["refund_transaction_id"]
    respx.post(WINDCAVE_BASE).mock(
        side_effect=[
            httpx.Response(200, content=INITIAL_INCOMPLETE_XML),
            httpx.Response(200, content=_final_declined_refund_xml(refund_id)),
        ]
    )
    r = client.post(f"/api/refunds/{refund_id}/charge-card")
    assert r.status_code == 200
    refund_row = db.get(POSTransaction, refund_id)
    db.refresh(refund_row)
    assert refund_row.status == "REFUND_PAYMENT_FAILED"
    assert "DO NOT HONOUR" in (refund_row.last_error or "")


@respx.mock
def test_failed_refund_does_not_block_retry(
    client: TestClient, cashier: POSUser, db: Session, settings
) -> None:
    txn_id = _completed_card_sale(client, db, cashier, settings)
    started = client.post(
        "/api/refunds/start", json={"original_transaction_id": txn_id}
    ).json()
    failed_refund_id = started["refund_transaction_id"]
    respx.post(WINDCAVE_BASE).mock(
        side_effect=[
            httpx.Response(200, content=INITIAL_INCOMPLETE_XML),
            httpx.Response(200, content=_final_declined_refund_xml(failed_refund_id)),
        ]
    )
    client.post(f"/api/refunds/{failed_refund_id}/charge-card")

    # The first attempt is REFUND_PAYMENT_FAILED; a fresh /start should succeed.
    second = client.post(
        "/api/refunds/start", json={"original_transaction_id": txn_id}
    )
    assert second.status_code == 200
    assert second.json()["refund_transaction_id"] != failed_refund_id


@respx.mock
def test_charge_cash_refund_sentry_failure_marks_inventory_update_failed(
    client: TestClient, cashier: POSUser, db: Session
) -> None:
    txn_id = _completed_cash_sale(client, db, cashier)
    respx.post(f"{SENTRY_BASE}/api/v1/pos/refund").mock(
        return_value=httpx.Response(422, json={"error": "fulfillment_failed"})
    )
    activity_log = respx.post(f"{SENTRY_BASE}/api/inbound-activity-log").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    started = client.post(
        "/api/refunds/start", json={"original_transaction_id": txn_id}
    ).json()
    refund_id = started["refund_transaction_id"]
    r = client.post(f"/api/refunds/{refund_id}/charge-cash")
    assert r.status_code == 200
    assert r.json()["status"] == "REFUND_INVENTORY_UPDATE_FAILED"
    assert activity_log.called


@respx.mock
def test_status_endpoint_for_refund(
    client: TestClient, cashier: POSUser, db: Session
) -> None:
    txn_id = _completed_cash_sale(client, db, cashier)
    started = client.post(
        "/api/refunds/start", json={"original_transaction_id": txn_id}
    ).json()
    refund_id = started["refund_transaction_id"]
    r = client.get(f"/api/refunds/{refund_id}/status")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "REFUND_PENDING"
    assert body["is_terminal"] is False
    assert body["result"] is None


@respx.mock
def test_status_unknown_refund_404(client: TestClient, cashier: POSUser) -> None:
    _login_cashier(client, cashier)
    r = client.get("/api/refunds/unknown/status")
    assert r.status_code == 404


@respx.mock
def test_cancel_pending_refund(
    client: TestClient, cashier: POSUser, db: Session
) -> None:
    txn_id = _completed_cash_sale(client, db, cashier)
    started = client.post(
        "/api/refunds/start", json={"original_transaction_id": txn_id}
    ).json()
    refund_id = started["refund_transaction_id"]
    r = client.post(f"/api/refunds/{refund_id}/cancel")
    assert r.status_code == 200
    assert r.json()["status"] == "CANCELLED"

    # After cancel, lookup allows a fresh refund attempt
    lookup = client.get("/api/refunds/lookup", params={"transaction_id": txn_id})
    assert lookup.status_code == 200
    assert lookup.json()["refundable"] is True
