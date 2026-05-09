import httpx
import respx
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from pos_service.models import FabricOutboxEntry, POSPrice, POSUser

SENTRY_BASE = "http://sentry.test"


def _login_cashier(client: TestClient) -> None:
    client.post(
        "/api/auth/login", json={"username": "mike", "password": "supersecret"}
    )


def _ring_up_cash_sale(client: TestClient, db: Session) -> str:
    """Drive a complete cash sale through the public endpoints so the
    outbox row is written by the real checkout pipeline rather than
    inserted by hand. Returns the transaction id."""
    db.add(POSPrice(sku="WIDGET-001", unit_price_cents=1999))
    db.commit()
    respx.post(f"{SENTRY_BASE}/api/pos/validate-cart").mock(
        return_value=httpx.Response(200, json={"valid": True})
    )
    respx.post(f"{SENTRY_BASE}/api/pos/checkout").mock(
        return_value=httpx.Response(
            200,
            json={"so_id": "SO-1", "so_number": "SO-1", "replayed": False},
        )
    )

    started = client.post(
        "/api/checkout/start",
        json={
            "lines": [
                {
                    "sku": "WIDGET-001",
                    "name": "Widget",
                    "warehouse_id": "WH-STORE",
                    "bin_id": "BIN-A1",
                    "quantity": 1,
                    "is_taxable": True,
                }
            ]
        },
    )
    txn_id = started.json()["transaction_id"]
    client.post(
        f"/api/checkout/{txn_id}/charge-cash",
        json={"amount_tendered_cents": 5000},
    )
    return txn_id


@respx.mock
def test_completed_cash_sale_writes_a_fabric_outbox_row(
    client: TestClient, db: Session, cashier: POSUser
) -> None:
    _login_cashier(client)
    _ring_up_cash_sale(client, db)

    rows = list(db.query(FabricOutboxEntry).all())
    assert len(rows) == 1
    assert rows[0].status == "PENDING"
    assert rows[0].pos_transaction_id is not None
    assert rows[0].attempt_count == 0


@respx.mock
def test_list_fabric_outbox_requires_auth(client: TestClient) -> None:
    r = client.get("/api/admin/fabric-outbox")
    assert r.status_code == 401


@respx.mock
def test_list_fabric_outbox_returns_rows(
    client: TestClient, db: Session, cashier: POSUser
) -> None:
    _login_cashier(client)
    _ring_up_cash_sale(client, db)

    r = client.get("/api/admin/fabric-outbox")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["status"] == "PENDING"
    assert body[0]["attempt_count"] == 0


@respx.mock
def test_list_fabric_outbox_filters_by_status(
    client: TestClient, db: Session, cashier: POSUser
) -> None:
    _login_cashier(client)
    _ring_up_cash_sale(client, db)

    rows = list(db.query(FabricOutboxEntry).all())
    rows[0].status = "DLQ"
    db.commit()

    pending = client.get("/api/admin/fabric-outbox", params={"status": "PENDING"}).json()
    assert pending == []
    dlq = client.get("/api/admin/fabric-outbox", params={"status": "DLQ"}).json()
    assert len(dlq) == 1
    assert dlq[0]["status"] == "DLQ"


@respx.mock
def test_list_fabric_outbox_rejects_invalid_status(
    client: TestClient, cashier: POSUser
) -> None:
    _login_cashier(client)
    r = client.get("/api/admin/fabric-outbox", params={"status": "MADE_UP"})
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "invalid_status"


@respx.mock
def test_retry_dlq_entry_resets_to_pending(
    client: TestClient, db: Session, cashier: POSUser
) -> None:
    _login_cashier(client)
    _ring_up_cash_sale(client, db)
    entry = db.query(FabricOutboxEntry).one()
    entry.status = "DLQ"
    entry.attempt_count = 8
    entry.last_error = "fabric down"
    db.commit()

    r = client.post(f"/api/admin/fabric-outbox/{entry.id}/retry")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "PENDING"
    assert body["attempt_count"] == 0

    db.expire_all()
    fresh = db.query(FabricOutboxEntry).one()
    assert fresh.status == "PENDING"
    assert fresh.attempt_count == 0
    assert fresh.last_error is None


@respx.mock
def test_retry_pending_entry_returns_invalid_state(
    client: TestClient, db: Session, cashier: POSUser
) -> None:
    _login_cashier(client)
    _ring_up_cash_sale(client, db)
    entry = db.query(FabricOutboxEntry).one()

    r = client.post(f"/api/admin/fabric-outbox/{entry.id}/retry")
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "invalid_state"


@respx.mock
def test_retry_unknown_entry_returns_404(
    client: TestClient, cashier: POSUser
) -> None:
    _login_cashier(client)
    r = client.post("/api/admin/fabric-outbox/does-not-exist/retry")
    assert r.status_code == 404
