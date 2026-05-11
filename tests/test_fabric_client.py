import json

import httpx
import pytest
import respx

from pos_service.clients.fabric import (
    PRICE_CATALOG_PATH,
    FabricClient,
    FabricClientError,
)
from pos_service.config import Settings


@pytest.mark.asyncio
async def test_mock_mode_when_url_empty():
    client = FabricClient(base_url="")
    assert client.is_mock is True
    assert await client.fetch_price_catalog() == []
    await client.aclose()


@pytest.mark.asyncio
async def test_aclose_in_mock_mode_is_safe():
    client = FabricClient(base_url="")
    await client.aclose()
    assert client.is_mock is True


@pytest.mark.asyncio
async def test_from_settings_threads_through_url_and_key():
    settings = Settings(
        fabric_transaction_service_url="https://fabric.test",
        fabric_api_key="bearer-xyz",
        fabric_request_timeout_s=15.0,
    )
    client = FabricClient.from_settings(settings)
    try:
        assert client.is_mock is False
        assert client._client is not None
        assert client._client.headers.get("Authorization") == "Bearer bearer-xyz"
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_from_settings_with_empty_url_is_mock():
    settings = Settings(fabric_transaction_service_url="")
    client = FabricClient.from_settings(settings)
    assert client.is_mock is True


@pytest.mark.asyncio
@respx.mock
async def test_fetch_price_catalog_parses_rows():
    base = "https://fabric.test"
    respx.get(f"{base}{PRICE_CATALOG_PATH}").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"sku": "ROD-100", "unit_price_cents": 19999},
                {"sku": "REEL-200", "unit_price_cents": 24500},
                {"sku": "LINE-300", "unit_price_cents": 1499},
            ],
        ),
    )

    client = FabricClient(base_url=base, api_key="bearer-xyz")
    try:
        rows = await client.fetch_price_catalog()
    finally:
        await client.aclose()

    assert sorted(rows) == [
        ("LINE-300", 1499),
        ("REEL-200", 24500),
        ("ROD-100", 19999),
    ]
    assert all(isinstance(sku, str) and isinstance(cents, int) for sku, cents in rows)


@pytest.mark.asyncio
@respx.mock
async def test_fetch_price_catalog_sends_bearer_header_when_key_set():
    base = "https://fabric.test"
    captured: dict[str, str] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("authorization", "")
        return httpx.Response(200, json=[])

    respx.get(f"{base}{PRICE_CATALOG_PATH}").mock(side_effect=_capture)

    client = FabricClient(base_url=base, api_key="bearer-xyz")
    try:
        await client.fetch_price_catalog()
    finally:
        await client.aclose()

    assert captured["authorization"] == "Bearer bearer-xyz"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_price_catalog_omits_authorization_when_no_key():
    base = "https://fabric.test"
    captured: dict[str, str | None] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("authorization")
        return httpx.Response(200, json=[])

    respx.get(f"{base}{PRICE_CATALOG_PATH}").mock(side_effect=_capture)

    client = FabricClient(base_url=base, api_key="")
    try:
        await client.fetch_price_catalog()
    finally:
        await client.aclose()

    assert captured["authorization"] is None


@pytest.mark.asyncio
@respx.mock
async def test_fetch_price_catalog_returns_empty_for_empty_response():
    base = "https://fabric.test"
    respx.get(f"{base}{PRICE_CATALOG_PATH}").mock(
        return_value=httpx.Response(200, json=[]),
    )
    client = FabricClient(base_url=base)
    try:
        assert await client.fetch_price_catalog() == []
    finally:
        await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_fetch_price_catalog_wraps_5xx_as_fabric_client_error():
    base = "https://fabric.test"
    respx.get(f"{base}{PRICE_CATALOG_PATH}").mock(
        return_value=httpx.Response(503, json={"error": "down"}),
    )
    client = FabricClient(base_url=base)
    try:
        with pytest.raises(FabricClientError, match="price catalog fetch failed"):
            await client.fetch_price_catalog()
    finally:
        await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_fetch_price_catalog_rejects_non_list_payload():
    base = "https://fabric.test"
    respx.get(f"{base}{PRICE_CATALOG_PATH}").mock(
        return_value=httpx.Response(200, json={"unexpected": "shape"}),
    )
    client = FabricClient(base_url=base)
    try:
        with pytest.raises(FabricClientError, match="non-list payload"):
            await client.fetch_price_catalog()
    finally:
        await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_fetch_price_catalog_rejects_malformed_rows():
    base = "https://fabric.test"
    respx.get(f"{base}{PRICE_CATALOG_PATH}").mock(
        return_value=httpx.Response(
            200, json=[{"sku": "ROD-100", "price": "wrong-key"}]
        ),
    )
    client = FabricClient(base_url=base)
    try:
        with pytest.raises(FabricClientError, match="malformed rows"):
            await client.fetch_price_catalog()
    finally:
        await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_lookup_customer_returns_match_dict():
    from pos_service.clients.fabric import CUSTOMER_LOOKUP_PATH

    base = "https://fabric.test"
    respx.get(f"{base}{CUSTOMER_LOOKUP_PATH}").mock(
        return_value=httpx.Response(
            200,
            json={
                "customer_id": "cust-1",
                "display_name": "Pat Smith",
                "email": "pat@example.com",
                "phone": "+13035551234",
                "registered": True,
            },
        )
    )
    client = FabricClient(base_url=base)
    try:
        match = await client.lookup_customer(email="pat@example.com")
    finally:
        await client.aclose()
    assert match is not None
    assert match["customer_id"] == "cust-1"
    assert match["registered"] is True


@pytest.mark.asyncio
@respx.mock
async def test_lookup_customer_returns_none_on_404():
    from pos_service.clients.fabric import CUSTOMER_LOOKUP_PATH

    base = "https://fabric.test"
    respx.get(f"{base}{CUSTOMER_LOOKUP_PATH}").mock(
        return_value=httpx.Response(404)
    )
    client = FabricClient(base_url=base)
    try:
        assert await client.lookup_customer(name="nope") is None
    finally:
        await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_lookup_customer_returns_none_on_null_body():
    from pos_service.clients.fabric import CUSTOMER_LOOKUP_PATH

    base = "https://fabric.test"
    respx.get(f"{base}{CUSTOMER_LOOKUP_PATH}").mock(
        return_value=httpx.Response(
            200,
            content=b"null",
            headers={"content-type": "application/json"},
        )
    )
    client = FabricClient(base_url=base)
    try:
        assert await client.lookup_customer(name="anyone") is None
    finally:
        await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_create_customer_posts_and_returns_dict():
    base = "https://fabric.test"
    route = respx.post(f"{base}/api/v1/customers").mock(
        return_value=httpx.Response(
            201,
            json={
                "customer_id": "cust-99",
                "display_name": "Pat New",
                "email": "pat@example.com",
                "phone": "555-1234",
                "registered": True,
            },
        )
    )
    client = FabricClient(base_url=base)
    try:
        created = await client.create_customer(
            name="Pat New", email="pat@example.com", phone="555-1234",
        )
    finally:
        await client.aclose()
    assert created["customer_id"] == "cust-99"
    assert created["registered"] is True
    # Body posted contained the three fields we passed.
    body = json.loads(route.calls.last.request.content.decode())
    assert body == {
        "name": "Pat New",
        "email": "pat@example.com",
        "phone": "555-1234",
    }


@pytest.mark.asyncio
async def test_create_customer_mock_mode_returns_synthetic_id():
    """No base URL -> mock mode. Synthetic customer_id stamps the same
    shape Fabric would return so the downstream attach/checkout code
    path doesn't branch on mock vs real."""
    client = FabricClient(base_url="")
    try:
        created = await client.create_customer(name="Mock Pat")
    finally:
        await client.aclose()
    assert created["customer_id"].startswith("mock-")
    assert created["display_name"] == "Mock Pat"
    assert created["registered"] is True


@pytest.mark.asyncio
async def test_create_customer_requires_at_least_one_field():
    client = FabricClient(base_url="https://fabric.test")
    try:
        with pytest.raises(FabricClientError):
            await client.create_customer()
    finally:
        await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_create_customer_wraps_5xx_as_fabric_client_error():
    base = "https://fabric.test"
    respx.post(f"{base}/api/v1/customers").mock(
        return_value=httpx.Response(503, json={})
    )
    client = FabricClient(base_url=base)
    try:
        with pytest.raises(FabricClientError):
            await client.create_customer(name="Pat")
    finally:
        await client.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_paths_are_overridable_via_constructor():
    base = "https://fabric.test"
    respx.get(f"{base}/custom/prices").mock(
        return_value=httpx.Response(200, json=[])
    )
    client = FabricClient(
        base_url=base,
        price_catalog_path="/custom/prices",
    )
    try:
        rows = await client.fetch_price_catalog()
    finally:
        await client.aclose()
    assert rows == []


@pytest.mark.asyncio
@respx.mock
async def test_auth_header_name_and_prefix_overridable():
    base = "https://fabric.test"
    captured: dict[str, str | None] = {}

    def _capture(request: httpx.Request) -> httpx.Response:
        captured["x-api-key"] = request.headers.get("x-api-key")
        captured["authorization"] = request.headers.get("authorization")
        return httpx.Response(200, json=[])

    respx.get(f"{base}/api/v1/prices/catalog").mock(side_effect=_capture)

    client = FabricClient(
        base_url=base,
        api_key="raw-key-xyz",
        auth_header_name="X-API-Key",
        auth_header_value_prefix="",
    )
    try:
        await client.fetch_price_catalog()
    finally:
        await client.aclose()

    assert captured["x-api-key"] == "raw-key-xyz"
    assert captured["authorization"] is None


@pytest.mark.asyncio
async def test_from_settings_threads_paths_and_auth_format_through():
    settings = Settings(
        fabric_transaction_service_url="https://fabric.test",
        fabric_api_key="key",
        fabric_price_catalog_path="/custom/prices",
        fabric_sales_orders_path="/custom/orders",
        fabric_customer_lookup_path="/custom/customers",
        fabric_auth_header_name="X-API-Key",
        fabric_auth_header_value_prefix="",
    )
    client = FabricClient.from_settings(settings)
    try:
        assert client._price_catalog_path == "/custom/prices"
        assert client._sales_orders_path == "/custom/orders"
        assert client._customer_lookup_path == "/custom/customers"
        assert client._client is not None
        assert client._client.headers.get("X-API-Key") == "key"
        assert client._client.headers.get("Authorization") is None
    finally:
        await client.aclose()
