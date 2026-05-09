"""Fabric Transaction Service REST client for the POS Service.

The Fabric transaction service is a single REST surface that handles every
read and write the POS Service needs from Microsoft Fabric: the live price
catalog the four-hour polling worker pulls into pos_prices (B2), the
sales-order writeback the outbox drain posts on every COMPLETE checkout
(Phase C), and the customer lookup endpoint the cashier UI calls when
attaching a customer (Phase D). The transaction service routes each call
to the right Fabric-side table or platform; the POS Service does not talk
to Fabric SQL directly.

This shape is the result of the architecture call captured in
/Users/michaelhightower/Downloads/AvidMaxmkv.txt -- earlier drafts had
the POS Service opening a pyodbc connection to gl.dbo.* and writing
schema-faithful payloads. The Fabric engineer's directive was 'send what
you got, the transaction service will figure it out,' so the client is a
thin httpx wrapper rather than a SQL+marshalling layer.

v1 surface:
    fetch_price_catalog() -> list[(sku, unit_price_cents)]
        Pulled every 4 hours by pos_service.services.fabric_price_sync
        into the local pos_prices SQLite cache. The cashier path
        (pos_service.routes.items.lookup) reads only the cache, so a
        Fabric outage never blocks a sale -- prices drift inside the
        four-hour window until Fabric recovers.

write_sales_order() and lookup_customer() land in subsequent phases.

Mock mode: an empty FABRIC_TRANSACTION_SERVICE_URL leaves the httpx
client unconstructed and turns fetch_price_catalog() into a no-op
returning []. This is the same opt-out posture the Sentry and Windcave
clients use so dev machines without Fabric credentials don't error on
startup or churn the price cache.
"""

import logging
from typing import Any

import httpx

from pos_service.config import Settings

log = logging.getLogger(__name__)

# TODO(integration): confirm the actual paths with the Fabric engineer
# when the transaction service URL + auth are finalised. Per the
# AvidMaxmkv.txt call, the transaction service is one REST surface that
# routes our payloads to the right Fabric tables.
PRICE_CATALOG_PATH = "/api/v1/prices/catalog"
SALES_ORDERS_PATH = "/api/v1/sales_orders"


class FabricClientError(Exception):
    """Raised when a Fabric REST call fails after the client is constructed."""


class FabricClient:
    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        timeout_s: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout_s = timeout_s
        self._client: httpx.AsyncClient | None = None
        if base_url:
            headers: dict[str, str] = {"Accept": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers=headers,
                timeout=timeout_s,
            )

    @classmethod
    def from_settings(cls, settings: Settings) -> "FabricClient":
        return cls(
            base_url=settings.fabric_transaction_service_url,
            api_key=settings.fabric_api_key,
            timeout_s=settings.fabric_request_timeout_s,
        )

    @property
    def is_mock(self) -> bool:
        return self._client is None

    async def fetch_price_catalog(self) -> list[tuple[str, int]]:
        if self._client is None:
            return []
        try:
            response = await self._client.get(PRICE_CATALOG_PATH)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise FabricClientError(
                f"price catalog fetch failed: {exc}"
            ) from exc

        if not isinstance(payload, list):
            raise FabricClientError(
                f"price catalog fetch returned non-list payload: {type(payload).__name__}"
            )

        try:
            return [
                (str(item["sku"]), int(item["unit_price_cents"]))
                for item in payload
            ]
        except (KeyError, TypeError, ValueError) as exc:
            raise FabricClientError(
                f"price catalog fetch returned malformed rows: {exc}"
            ) from exc

    async def write_sales_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST a completed SO (or refund SO) to the Fabric transaction service.

        Payload shape is intentionally lean per the architecture call:
        external_so_ref + sentry_so_id + status + totals + lines, plus a
        few register/cashier identifiers. The transaction service routes
        the payload to the right Fabric-side table; the POS Service is
        not authoritative on Fabric's schema.

        Returns the parsed JSON response (typically {"fabric_so_id": ...}).
        Mock mode (no client constructed) raises FabricClientError so the
        outbox drain treats it as a delivery failure rather than silently
        succeeding on a dev box without Fabric credentials.
        """
        if self._client is None:
            raise FabricClientError("fabric_mock_mode")
        try:
            response = await self._client.post(SALES_ORDERS_PATH, json=payload)
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPError as exc:
            raise FabricClientError(
                f"sales order write failed: {exc}"
            ) from exc
        if not isinstance(body, dict):
            raise FabricClientError(
                f"sales order write returned non-object payload: {type(body).__name__}"
            )
        return body

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
