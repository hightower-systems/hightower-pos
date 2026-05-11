import json

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


def _seed_and_start(client: TestClient, db: Session) -> str:
    db.add(POSPrice(sku="WIDGET-001", unit_price_cents=1999))
    db.commit()
    respx.post(f"{SENTRY_BASE}/api/v1/pos/validate-cart").mock(
        return_value=httpx.Response(200, json={"valid": True})
    )
    started = client.post(
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
    return started.json()["transaction_id"]


@respx.mock
def test_double_charge_cash_blocked_by_state_machine(
    client: TestClient, cashier: POSUser, db: Session
) -> None:
    _login_cashier(client, cashier)
    txn_id = _seed_and_start(client, db)
    respx.post(f"{SENTRY_BASE}/api/v1/pos/checkout").mock(
        return_value=httpx.Response(
            200, json={"so_id": "SO-1", "so_number": "SO-1", "replayed": False}
        )
    )
    first = client.post(
        f"/api/checkout/{txn_id}/charge-cash",
        json={"amount_tendered_cents": 3000},
    )
    assert first.status_code == 200
    assert first.json()["status"] == "COMPLETE"

    second = client.post(
        f"/api/checkout/{txn_id}/charge-cash",
        json={"amount_tendered_cents": 3000},
    )
    assert second.status_code == 400
    assert second.json()["detail"]["error"] == "invalid_state"
    assert second.json()["detail"]["current_status"] == "COMPLETE"


@respx.mock
def test_charge_cash_sends_idempotency_key_equal_to_transaction_id(
    client: TestClient, cashier: POSUser, db: Session
) -> None:
    _login_cashier(client, cashier)
    txn_id = _seed_and_start(client, db)
    checkout_route = respx.post(f"{SENTRY_BASE}/api/v1/pos/checkout").mock(
        return_value=httpx.Response(
            200, json={"so_id": "SO-1", "so_number": "SO-1", "replayed": False}
        )
    )
    r = client.post(
        f"/api/checkout/{txn_id}/charge-cash",
        json={"amount_tendered_cents": 3000},
    )
    assert r.status_code == 200
    assert checkout_route.called
    sent_body = json.loads(checkout_route.calls.last.request.content)
    assert sent_body["idempotency_key"] == txn_id


@respx.mock
def test_sentry_replay_flag_does_not_break_completion(
    client: TestClient, cashier: POSUser, db: Session
) -> None:
    _login_cashier(client, cashier)
    txn_id = _seed_and_start(client, db)
    respx.post(f"{SENTRY_BASE}/api/v1/pos/checkout").mock(
        return_value=httpx.Response(
            200,
            json={"so_id": "SO-EXISTING", "so_number": "SO-EXISTING", "replayed": True},
        )
    )
    r = client.post(
        f"/api/checkout/{txn_id}/charge-cash",
        json={"amount_tendered_cents": 3000},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "COMPLETE"
    assert r.json()["so_id"] == "SO-EXISTING"
    txn_row = db.get(POSTransaction, txn_id)
    db.refresh(txn_row)
    assert txn_row.sentry_so_id == "SO-EXISTING"


@respx.mock
def test_double_cancel_blocked_by_state_machine(
    client: TestClient, cashier: POSUser, db: Session
) -> None:
    _login_cashier(client, cashier)
    txn_id = _seed_and_start(client, db)
    first = client.post(f"/api/checkout/{txn_id}/cancel")
    assert first.status_code == 200
    second = client.post(f"/api/checkout/{txn_id}/cancel")
    assert second.status_code == 400
    assert second.json()["detail"]["error"] == "invalid_state"
