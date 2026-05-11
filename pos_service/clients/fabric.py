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
import uuid
from typing import Any

import httpx
from fastapi import Request

from pos_service.config import Settings

log = logging.getLogger(__name__)

# Defaults for the three Fabric transaction-service endpoints. Operators
# override at runtime via the FABRIC_*_PATH env vars without rebuilding
# the image; the constants here are the values used when no override is
# supplied (and the values respx tests pin against).
PRICE_CATALOG_PATH = "/api/v1/prices/catalog"
SALES_ORDERS_PATH = "/api/v1/sales_orders"
CUSTOMER_LOOKUP_PATH = "/api/v1/customers/lookup"
CUSTOMER_CREATE_PATH = "/api/v1/customers"
DEFAULT_AUTH_HEADER_NAME = "Authorization"
DEFAULT_AUTH_HEADER_VALUE_PREFIX = "Bearer "


class FabricClientError(Exception):
    """Raised when a Fabric REST call fails after the client is constructed."""


class FabricClient:
    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        timeout_s: float = 30.0,
        *,
        price_catalog_path: str = PRICE_CATALOG_PATH,
        sales_orders_path: str = SALES_ORDERS_PATH,
        customer_lookup_path: str = CUSTOMER_LOOKUP_PATH,
        customer_create_path: str = CUSTOMER_CREATE_PATH,
        auth_header_name: str = DEFAULT_AUTH_HEADER_NAME,
        auth_header_value_prefix: str = DEFAULT_AUTH_HEADER_VALUE_PREFIX,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout_s = timeout_s
        self._price_catalog_path = price_catalog_path
        self._sales_orders_path = sales_orders_path
        self._customer_lookup_path = customer_lookup_path
        self._customer_create_path = customer_create_path
        self._client: httpx.AsyncClient | None = None
        if base_url:
            headers: dict[str, str] = {"Accept": "application/json"}
            if api_key:
                headers[auth_header_name] = f"{auth_header_value_prefix}{api_key}"
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
            price_catalog_path=settings.fabric_price_catalog_path,
            sales_orders_path=settings.fabric_sales_orders_path,
            customer_lookup_path=settings.fabric_customer_lookup_path,
            customer_create_path=settings.fabric_customer_create_path,
            auth_header_name=settings.fabric_auth_header_name,
            auth_header_value_prefix=settings.fabric_auth_header_value_prefix,
        )

    @property
    def is_mock(self) -> bool:
        return self._client is None

    async def fetch_price_catalog(self) -> list[tuple[str, int]]:
        if self._client is None:
            return []
        try:
            response = await self._client.get(self._price_catalog_path)
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
            response = await self._client.post(self._sales_orders_path, json=payload)
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

    async def lookup_customer(
        self,
        *,
        name: str | None = None,
        email: str | None = None,
        phone: str | None = None,
    ) -> dict[str, Any] | None:
        """Look up a customer in Fabric by name, email, and/or phone.

        Per the architecture call: the Fabric customer platform performs
        fuzzy matching across an indexed identity store. The POS Service
        sends whatever the cashier typed; the platform decides whether
        the identity matches a registered or unregistered record. Returns
        the matched customer (registered=true) or null when nothing
        matches; the caller surfaces null as 'unregistered' in the UI.

        Mock mode raises FabricClientError so the cashier sees a clear
        503 rather than a silent miss.
        """
        if self._client is None:
            raise FabricClientError("fabric_mock_mode")
        params: dict[str, str] = {}
        if name:
            params["name"] = name
        if email:
            params["email"] = email
        if phone:
            params["phone"] = phone
        if not params:
            raise FabricClientError("at_least_one_query_param_required")
        try:
            response = await self._client.get(self._customer_lookup_path, params=params)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPError as exc:
            raise FabricClientError(
                f"customer lookup failed: {exc}"
            ) from exc
        if body is None:
            return None
        if not isinstance(body, dict):
            raise FabricClientError(
                f"customer lookup returned non-object payload: {type(body).__name__}"
            )
        return body

    async def create_customer(
        self,
        *,
        name: str | None = None,
        email: str | None = None,
        phone: str | None = None,
    ) -> dict[str, Any]:
        """Create a customer in the Fabric transaction service.

        Used by the cashier UI when a lookup returns no match and the
        cashier wants to register the customer (vs. just attaching
        the typed info as an unregistered ride-along on the sale).

        Mock mode returns a synthetic customer_id so dev boxes can
        exercise the full create-attach UX without Fabric creds.
        Production callers should reach a real Fabric instance.
        """
        if name is None and email is None and phone is None:
            raise FabricClientError("at_least_one_field_required")
        if self._client is None:
            # Synthetic id stamps the same shape Fabric would return so
            # the downstream code (attach + checkout serialization)
            # doesn't branch on mock vs real.
            return {
                "customer_id": f"mock-{uuid.uuid4()}",
                "display_name": name,
                "email": email,
                "phone": phone,
                "registered": True,
            }
        payload: dict[str, Any] = {}
        if name:
            payload["name"] = name
        if email:
            payload["email"] = email
        if phone:
            payload["phone"] = phone
        try:
            response = await self._client.post(
                self._customer_create_path, json=payload
            )
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPError as exc:
            raise FabricClientError(f"customer create failed: {exc}") from exc
        if not isinstance(body, dict):
            raise FabricClientError(
                f"customer create returned non-object payload: {type(body).__name__}"
            )
        return body

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


def get_fabric_client(request: Request) -> FabricClient:
    """FastAPI dependency that hands out the lifespan-managed FabricClient.

    The lifespan stashes one FabricClient on app.state; endpoints reuse it
    so the httpx connection pool is shared across requests rather than
    rebuilt per call. Tests override this dependency with their own client
    via app.dependency_overrides.
    """
    return request.app.state.fabric_client
