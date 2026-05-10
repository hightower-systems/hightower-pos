import httpx
import respx
from fastapi.testclient import TestClient

from pos_service.models import POSPrice, POSUser

SENTRY_BASE = "http://sentry.test"


def _login_cashier(client: TestClient, cashier: POSUser) -> None:
    r = client.post(
        "/api/auth/login", json={"username": "mike", "password": "supersecret"}
    )
    assert r.status_code == 200


def _availability_payload(sku: str = "WIDGET-001") -> dict:
    return {
        "sku": sku,
        "name": "Widget Mark I",
        "barcode": "012345678901",
        "is_taxable": True,
        "availability": [
            {
                "warehouse_id": "store",
                "warehouse_name": "Retail Floor",
                "qty_available": 1,
                "bins": [{"bin_id": "A-3-12", "bin_name": "A-3-12", "qty": 1}],
            }
        ],
    }


def test_lookup_requires_auth(client: TestClient) -> None:
    r = client.get("/api/items/lookup", params={"sku": "WIDGET-001"})
    assert r.status_code == 401


def test_lookup_blocked_when_admin_must_change_password(
    client: TestClient, admin: POSUser
) -> None:
    client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    r = client.get("/api/items/lookup", params={"sku": "WIDGET-001"})
    assert r.status_code == 403
    assert r.json()["detail"]["error"] == "password_change_required"


def test_lookup_requires_one_identifier(client: TestClient, cashier: POSUser) -> None:
    _login_cashier(client, cashier)
    r = client.get("/api/items/lookup")
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "exactly_one_identifier_required"
    r = client.get("/api/items/lookup", params={"sku": "X", "barcode": "Y"})
    assert r.status_code == 400


@respx.mock
def test_lookup_happy_path_by_sku(
    client: TestClient, cashier: POSUser, db
) -> None:
    db.add(POSPrice(sku="WIDGET-001", unit_price_cents=1999))
    db.commit()
    respx.get(f"{SENTRY_BASE}/api/v1/pos/availability").mock(
        return_value=httpx.Response(200, json=_availability_payload())
    )
    _login_cashier(client, cashier)
    r = client.get("/api/items/lookup", params={"sku": "WIDGET-001"})
    assert r.status_code == 200
    body = r.json()
    assert body["sku"] == "WIDGET-001"
    assert body["name"] == "Widget Mark I"
    assert body["unit_price_cents"] == 1999
    assert abs(body["tax_rate"] - 0.0810) < 1e-9
    assert body["is_taxable"] is True
    assert body["availability"][0]["warehouse_id"] == "store"


@respx.mock
def test_lookup_happy_path_by_barcode(
    client: TestClient, cashier: POSUser, db
) -> None:
    db.add(POSPrice(sku="WIDGET-001", unit_price_cents=1999))
    db.commit()
    route = respx.get(f"{SENTRY_BASE}/api/v1/pos/availability").mock(
        return_value=httpx.Response(200, json=_availability_payload())
    )
    _login_cashier(client, cashier)
    r = client.get("/api/items/lookup", params={"barcode": "012345678901"})
    assert r.status_code == 200
    assert route.calls.last.request.url.params["barcode"] == "012345678901"


@respx.mock
def test_lookup_404_from_sentry_returns_item_not_found(
    client: TestClient, cashier: POSUser
) -> None:
    respx.get(f"{SENTRY_BASE}/api/v1/pos/availability").mock(
        return_value=httpx.Response(404, json={"error": "item_not_found"})
    )
    _login_cashier(client, cashier)
    r = client.get("/api/items/lookup", params={"sku": "UNKNOWN"})
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "item_not_found"


@respx.mock
def test_lookup_5xx_from_sentry_returns_502(
    client: TestClient, cashier: POSUser
) -> None:
    respx.get(f"{SENTRY_BASE}/api/v1/pos/availability").mock(
        return_value=httpx.Response(503, json={})
    )
    _login_cashier(client, cashier)
    r = client.get("/api/items/lookup", params={"sku": "WIDGET-001"})
    assert r.status_code == 502
    assert r.json()["detail"]["error"] == "sentry_unavailable"


@respx.mock
def test_lookup_returns_422_when_price_missing(
    client: TestClient, cashier: POSUser, db
) -> None:
    respx.get(f"{SENTRY_BASE}/api/v1/pos/availability").mock(
        return_value=httpx.Response(200, json=_availability_payload())
    )
    _login_cashier(client, cashier)
    r = client.get("/api/items/lookup", params={"sku": "WIDGET-001"})
    assert r.status_code == 422
    body = r.json()
    assert body["detail"]["error"] == "price_missing"
    assert body["detail"]["sku"] == "WIDGET-001"
