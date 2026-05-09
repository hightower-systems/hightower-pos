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
