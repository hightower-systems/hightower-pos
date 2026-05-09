
import httpx
import respx
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from pos_service.models import POSPrice, POSTransaction, POSUser

SENTRY_BASE = "http://sentry.test"


def _login_cashier(client: TestClient, cashier: POSUser) -> None:
    client.post(
        "/api/auth/login", json={"username": "mike", "password": "supersecret"}
    )


def _validate_cart_ok() -> None:
    respx.post(f"{SENTRY_BASE}/api/pos/validate-cart").mock(
        return_value=httpx.Response(200, json={"valid": True})
    )


def _start_and_complete_cash_sale(
    client: TestClient, db: Session, cashier: POSUser
) -> str:
    db.add(POSPrice(sku="WIDGET-001", unit_price_cents=1999))
    db.commit()
    _validate_cart_ok()
    respx.post(f"{SENTRY_BASE}/api/pos/checkout").mock(
        return_value=httpx.Response(
            200, json={"so_id": "SO-PARENT", "so_number": "SO-PARENT", "replayed": False}
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
    return txn_id


def test_list_transactions_requires_auth(client: TestClient) -> None:
    r = client.get("/api/admin/transactions")
    assert r.status_code == 401


@respx.mock
def test_list_transactions_returns_recent_rows(
    client: TestClient, cashier: POSUser, db: Session
) -> None:
    _start_and_complete_cash_sale(client, db, cashier)
    r = client.get("/api/admin/transactions")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) >= 1
    assert rows[0]["txn_type"] == "sale"
    assert rows[0]["status"] == "COMPLETE"


@respx.mock
def test_list_transactions_filter_by_status(
    client: TestClient, cashier: POSUser, db: Session
) -> None:
    _start_and_complete_cash_sale(client, db, cashier)
    r = client.get(
        "/api/admin/transactions", params={"status": "INVENTORY_UPDATE_FAILED"}
    )
    assert r.status_code == 200
    assert r.json() == []


@respx.mock
def test_list_transactions_filter_by_txn_type(
    client: TestClient, cashier: POSUser, db: Session
) -> None:
    _start_and_complete_cash_sale(client, db, cashier)
    r = client.get("/api/admin/transactions", params={"txn_type": "refund"})
    assert r.status_code == 200
    assert r.json() == []


@respx.mock
def test_get_transaction_detail_includes_cart_and_tenders(
    client: TestClient, cashier: POSUser, db: Session
) -> None:
    txn_id = _start_and_complete_cash_sale(client, db, cashier)
    r = client.get(f"/api/admin/transactions/{txn_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == txn_id
    assert len(body["cart"]) == 1
    assert body["cart"][0]["sku"] == "WIDGET-001"
    assert len(body["tenders"]) == 1
    assert body["tenders"][0]["type"] == "cash"
    assert body["counterpart"] is None


@respx.mock
def test_get_transaction_detail_links_sale_to_refund_counterpart(
    client: TestClient, cashier: POSUser, db: Session
) -> None:
    sale_id = _start_and_complete_cash_sale(client, db, cashier)
    respx.post(f"{SENTRY_BASE}/api/pos/refund").mock(
        return_value=httpx.Response(
            200,
            json={
                "refund_so_id": "SO-REFUND",
                "original_so_id": "SO-PARENT",
                "replayed": False,
            },
        )
    )
    started = client.post(
        "/api/refunds/start", json={"original_transaction_id": sale_id}
    ).json()
    refund_id = started["refund_transaction_id"]
    client.post(f"/api/refunds/{refund_id}/charge-cash")

    sale_detail = client.get(f"/api/admin/transactions/{sale_id}").json()
    assert sale_detail["refund_transaction_id"] == refund_id
    assert sale_detail["counterpart"]["id"] == refund_id
    assert sale_detail["counterpart"]["txn_type"] == "refund"

    refund_detail = client.get(f"/api/admin/transactions/{refund_id}").json()
    assert refund_detail["parent_transaction_id"] == sale_id
    assert refund_detail["counterpart"]["id"] == sale_id
    assert refund_detail["counterpart"]["txn_type"] == "sale"


def test_get_transaction_404(client: TestClient, cashier: POSUser) -> None:
    _login_cashier(client, cashier)
    r = client.get("/api/admin/transactions/unknown")
    assert r.status_code == 404


@respx.mock
def test_retry_sentry_for_failed_sale_succeeds(
    client: TestClient, cashier: POSUser, db: Session
) -> None:
    db.add(POSPrice(sku="WIDGET-001", unit_price_cents=1999))
    db.commit()
    _validate_cart_ok()
    respx.post(f"{SENTRY_BASE}/api/pos/checkout").mock(
        side_effect=[
            httpx.Response(422, json={"error": "fulfillment_failed"}),
            httpx.Response(
                200,
                json={
                    "so_id": "SO-RETRIED",
                    "so_number": "SO-RETRIED",
                    "replayed": True,
                },
            ),
        ]
    )
    respx.post(f"{SENTRY_BASE}/api/inbound-activity-log").mock(
        return_value=httpx.Response(200, json={"ok": True})
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
    txn_row = db.get(POSTransaction, txn_id)
    db.refresh(txn_row)
    assert txn_row.status == "INVENTORY_UPDATE_FAILED"

    r = client.post(f"/api/admin/transactions/{txn_id}/retry-sentry")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "COMPLETE"
    assert body["sentry_so_id"] == "SO-RETRIED"
    assert body["succeeded"] is True


@respx.mock
def test_retry_sentry_rejects_wrong_state(
    client: TestClient, cashier: POSUser, db: Session
) -> None:
    txn_id = _start_and_complete_cash_sale(client, db, cashier)
    r = client.post(f"/api/admin/transactions/{txn_id}/retry-sentry")
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "invalid_state"
    assert r.json()["detail"]["expected_status"] == "INVENTORY_UPDATE_FAILED"


def test_retry_sentry_404(client: TestClient, cashier: POSUser) -> None:
    _login_cashier(client, cashier)
    r = client.post("/api/admin/transactions/unknown/retry-sentry")
    assert r.status_code == 404


@respx.mock
def test_retry_sentry_still_failing_returns_succeeded_false(
    client: TestClient, cashier: POSUser, db: Session
) -> None:
    db.add(POSPrice(sku="WIDGET-001", unit_price_cents=1999))
    db.commit()
    _validate_cart_ok()
    respx.post(f"{SENTRY_BASE}/api/pos/checkout").mock(
        return_value=httpx.Response(422, json={"error": "fulfillment_failed"})
    )
    respx.post(f"{SENTRY_BASE}/api/inbound-activity-log").mock(
        return_value=httpx.Response(200, json={"ok": True})
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
    r = client.post(f"/api/admin/transactions/{txn_id}/retry-sentry")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "INVENTORY_UPDATE_FAILED"
    assert body["succeeded"] is False
