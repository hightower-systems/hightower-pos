import httpx
import respx
from fastapi.testclient import TestClient

from pos_service.models import POSUser

SENTRY_BASE = "http://sentry.test"


def _login_cashier(client: TestClient, cashier: POSUser) -> None:
    client.post(
        "/api/auth/login", json={"username": "mike", "password": "supersecret"}
    )


def test_dependencies_requires_auth(client: TestClient) -> None:
    r = client.get("/api/health/dependencies")
    assert r.status_code == 401


@respx.mock
def test_dependencies_sentry_reachable_via_404(
    client: TestClient, cashier: POSUser
) -> None:
    """A 404 from Sentry's availability endpoint means Sentry is up and
    answering; the SKU is just unknown. The health probe treats 404 as
    a positive reachability signal."""
    respx.get(f"{SENTRY_BASE}/api/v1/pos/availability").mock(
        return_value=httpx.Response(404, json={"error": "item_not_found"})
    )
    _login_cashier(client, cashier)
    r = client.get("/api/health/dependencies")
    assert r.status_code == 200
    body = r.json()
    assert body["sentry"]["reachable"] is True
    assert body["sentry"]["latency_ms"] is not None
    assert body["sentry"]["error"] is None


@respx.mock
def test_dependencies_sentry_unreachable_on_5xx(
    client: TestClient, cashier: POSUser
) -> None:
    respx.get(f"{SENTRY_BASE}/api/v1/pos/availability").mock(
        return_value=httpx.Response(503, json={})
    )
    _login_cashier(client, cashier)
    r = client.get("/api/health/dependencies")
    assert r.status_code == 200
    body = r.json()
    assert body["sentry"]["reachable"] is False
    assert body["sentry"]["error"] is not None


@respx.mock
def test_dependencies_reports_windcave_config(
    client: TestClient, cashier: POSUser
) -> None:
    respx.get(f"{SENTRY_BASE}/api/v1/pos/availability").mock(
        return_value=httpx.Response(404, json={"error": "item_not_found"})
    )
    _login_cashier(client, cashier)
    r = client.get("/api/health/dependencies")
    body = r.json()
    assert body["windcave"]["configured"] is True
    assert body["windcave"]["mock"] is False


@respx.mock
def test_dependencies_returns_terminal_id_and_version(
    client: TestClient, cashier: POSUser
) -> None:
    respx.get(f"{SENTRY_BASE}/api/v1/pos/availability").mock(
        return_value=httpx.Response(404, json={"error": "item_not_found"})
    )
    _login_cashier(client, cashier)
    r = client.get("/api/health/dependencies")
    body = r.json()
    assert body["terminal_id"] == "test"
    assert body["version"]


def test_dependencies_with_mock_sentry_short_circuits(
    client: TestClient, cashier: POSUser, settings
) -> None:
    """Mock-mode Sentry returns reachable=True without making an HTTP call,
    so respx isn't needed and probes are instant."""
    settings.sentry_mock = True
    try:
        _login_cashier(client, cashier)
        r = client.get("/api/health/dependencies")
        body = r.json()
        assert body["sentry"]["reachable"] is True
        assert body["sentry"]["latency_ms"] == 0
    finally:
        settings.sentry_mock = False
