from typing import Any

import pytest
from fastapi.testclient import TestClient

from pos_service.clients.fabric import (
    FabricClient,
    FabricClientError,
    get_fabric_client,
)
from pos_service.models import POSUser


def _login(client: TestClient) -> None:
    client.post(
        "/api/auth/login", json={"username": "mike", "password": "supersecret"}
    )


class FakeFabric:
    is_mock = False

    def __init__(
        self,
        *,
        match: dict[str, Any] | None = None,
        raise_error: str | None = None,
    ) -> None:
        self.match = match
        self.raise_error = raise_error
        self.calls: list[dict[str, Any]] = []

    async def lookup_customer(
        self,
        *,
        name: str | None = None,
        email: str | None = None,
        phone: str | None = None,
    ) -> dict[str, Any] | None:
        self.calls.append({"name": name, "email": email, "phone": phone})
        if self.raise_error is not None:
            raise FabricClientError(self.raise_error)
        return self.match


@pytest.fixture
def fake_fabric() -> FakeFabric:
    return FakeFabric()


@pytest.fixture
def client_with_fabric(client: TestClient, fake_fabric: FakeFabric) -> TestClient:
    client.app.dependency_overrides[get_fabric_client] = lambda: fake_fabric
    return client


def test_lookup_requires_auth(client: TestClient) -> None:
    r = client.get("/api/customers/lookup", params={"email": "x@y"})
    assert r.status_code == 401


def test_lookup_rejects_empty_query(
    client_with_fabric: TestClient, cashier: POSUser
) -> None:
    _login(client_with_fabric)
    r = client_with_fabric.get("/api/customers/lookup")
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "at_least_one_query_param_required"


def test_lookup_returns_match_when_fabric_returns_one(
    client: TestClient,
    cashier: POSUser,
    fake_fabric: FakeFabric,
) -> None:
    fake_fabric.match = {
        "customer_id": "cust-1",
        "display_name": "Pat Smith",
        "email": "pat@example.com",
        "phone": "+13035551234",
        "registered": True,
    }
    client.app.dependency_overrides[get_fabric_client] = lambda: fake_fabric
    _login(client)

    r = client.get("/api/customers/lookup", params={"email": "pat@example.com"})
    assert r.status_code == 200
    body = r.json()
    assert body["customer_id"] == "cust-1"
    assert body["display_name"] == "Pat Smith"
    assert body["registered"] is True
    assert fake_fabric.calls[-1]["email"] == "pat@example.com"


def test_lookup_returns_null_when_fabric_returns_none(
    client: TestClient,
    cashier: POSUser,
    fake_fabric: FakeFabric,
) -> None:
    fake_fabric.match = None
    client.app.dependency_overrides[get_fabric_client] = lambda: fake_fabric
    _login(client)

    r = client.get("/api/customers/lookup", params={"name": "Pat"})
    assert r.status_code == 200
    assert r.json() is None


def test_lookup_returns_503_when_fabric_unavailable(
    client: TestClient,
    cashier: POSUser,
) -> None:
    fake = FakeFabric(raise_error="connection refused")
    client.app.dependency_overrides[get_fabric_client] = lambda: fake
    _login(client)

    r = client.get("/api/customers/lookup", params={"email": "pat@example.com"})
    assert r.status_code == 503
    assert r.json()["detail"]["error"] == "fabric_unavailable"


def test_lookup_uses_display_name_or_falls_back_to_name(
    client: TestClient,
    cashier: POSUser,
    fake_fabric: FakeFabric,
) -> None:
    fake_fabric.match = {
        "customer_id": "cust-2",
        "name": "Jane Doe",
        "email": None,
        "phone": None,
        "registered": False,
    }
    client.app.dependency_overrides[get_fabric_client] = lambda: fake_fabric
    _login(client)

    r = client.get("/api/customers/lookup", params={"name": "Jane"})
    assert r.status_code == 200
    assert r.json()["display_name"] == "Jane Doe"


@pytest.mark.asyncio
async def test_fabric_client_lookup_customer_mock_mode_raises():
    client = FabricClient(base_url="")
    with pytest.raises(FabricClientError, match="fabric_mock_mode"):
        await client.lookup_customer(email="x@y.com")
    await client.aclose()


@pytest.mark.asyncio
async def test_fabric_client_lookup_customer_requires_at_least_one_param():
    client = FabricClient(base_url="https://fabric.test")
    try:
        with pytest.raises(FabricClientError, match="at_least_one_query_param_required"):
            await client.lookup_customer()
    finally:
        await client.aclose()
