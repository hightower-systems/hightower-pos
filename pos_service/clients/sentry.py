import asyncio
import logging
from datetime import datetime
from typing import Any

import httpx
from fastapi import Depends
from pydantic import BaseModel, Field

from pos_service.config import Settings, get_settings

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 30.0
MAX_RETRIES = 3
INITIAL_BACKOFF_S = 0.5


class SentryClientError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_code: str | None = None,
        response_body: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.response_body = response_body or {}


class BinAvailability(BaseModel):
    bin_id: str
    bin_name: str
    qty: int


class WarehouseAvailability(BaseModel):
    warehouse_id: str
    warehouse_name: str
    qty_available: int
    bins: list[BinAvailability]


class ItemAvailability(BaseModel):
    sku: str
    name: str
    barcode: str | None = None
    is_taxable: bool = True
    availability: list[WarehouseAvailability] = Field(default_factory=list)


class CartLine(BaseModel):
    sku: str
    warehouse_id: str
    bin_id: str
    quantity: int


class CartConflict(BaseModel):
    line_index: int
    sku: str
    warehouse_id: str
    bin_id: str
    requested_qty: int
    available_qty: int
    reason: str


class ValidationResult(BaseModel):
    valid: bool
    conflicts: list[CartConflict] = Field(default_factory=list)


class CheckoutLine(BaseModel):
    sku: str
    warehouse_id: str
    bin_id: str
    quantity: int
    unit_price_cents: int
    tax_cents: int
    line_total_cents: int
    fulfillment_note: str | None = None


class Tender(BaseModel):
    type: str
    amount_cents: int
    card_brand: str | None = None
    card_last4: str | None = None
    auth_code: str | None = None
    external_ref: str | None = None
    amount_tendered_cents: int | None = None
    change_cents: int | None = None


class PaymentSummary(BaseModel):
    method: str
    subtotal_cents: int
    tax_cents: int
    total_cents: int
    tenders: list[Tender]


class CheckoutRequest(BaseModel):
    idempotency_key: str
    external_txn_ref: str | None = None
    cashier_id: str
    terminal_id: str
    completed_at: datetime
    payment_summary: PaymentSummary
    lines: list[CheckoutLine]


class CheckoutResult(BaseModel):
    so_id: str
    so_number: str
    replayed: bool = False


class RefundSummary(BaseModel):
    method: str
    subtotal_cents: int
    tax_cents: int
    total_cents: int
    tenders: list[Tender]


class RefundRequest(BaseModel):
    idempotency_key: str
    original_so_id: str
    original_external_txn_ref: str | None = None
    external_refund_ref: str | None = None
    cashier_id: str
    terminal_id: str
    completed_at: datetime
    refund_summary: RefundSummary


class RefundResult(BaseModel):
    refund_so_id: str
    original_so_id: str
    replayed: bool = False


class SentryClient:
    def __init__(
        self,
        base_url: str,
        api_token: str,
        mock: bool = False,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        initial_backoff_s: float = INITIAL_BACKOFF_S,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = api_token
        self._mock = mock
        self._timeout_s = timeout_s
        self._initial_backoff_s = initial_backoff_s

    @classmethod
    def from_settings(cls, settings: Settings) -> "SentryClient":
        return cls(
            base_url=settings.sentry_base_url,
            api_token=settings.sentry_api_token,
            mock=settings.sentry_mock,
            initial_backoff_s=settings.sentry_initial_backoff_s,
        )

    @property
    def is_mock(self) -> bool:
        return self._mock

    async def lookup_availability(
        self, *, barcode: str | None = None, sku: str | None = None
    ) -> ItemAvailability:
        if (barcode is None) == (sku is None):
            raise ValueError("lookup_availability requires exactly one of barcode or sku")
        if self._mock:
            return _mock_item_availability(sku=sku, barcode=barcode)
        params = {"barcode": barcode} if barcode else {"sku": sku}
        r = await self._request("GET", "/api/v1/pos/availability", params=params)
        if r.status_code == 404:
            body = _safe_json(r)
            raise SentryClientError(
                "item_not_found",
                status_code=404,
                error_code=body.get("error", "item_not_found"),
                response_body=body,
            )
        self._raise_for_status(r)
        return ItemAvailability.model_validate(r.json())

    async def validate_cart(self, lines: list[CartLine]) -> ValidationResult:
        if self._mock:
            return ValidationResult(valid=True)
        body = {"lines": [line.model_dump() for line in lines]}
        r = await self._request("POST", "/api/v1/pos/validate-cart", json=body)
        if r.status_code == 409:
            payload = _safe_json(r)
            return ValidationResult.model_validate(payload)
        self._raise_for_status(r)
        return ValidationResult.model_validate(r.json())

    async def create_pos_so(self, request: CheckoutRequest) -> CheckoutResult:
        if self._mock:
            return CheckoutResult(
                so_id=f"SO-MOCK-{request.idempotency_key[:8]}",
                so_number=f"SO-MOCK-{request.idempotency_key[:8]}",
                replayed=False,
            )
        r = await self._request(
            "POST",
            "/api/v1/pos/checkout",
            json=request.model_dump(mode="json", exclude_none=True),
        )
        if r.status_code in {409, 422}:
            body = _safe_json(r)
            raise SentryClientError(
                body.get("error", "checkout_failed"),
                status_code=r.status_code,
                error_code=body.get("error"),
                response_body=body,
            )
        self._raise_for_status(r)
        return CheckoutResult.model_validate(r.json())

    async def create_pos_refund(self, request: RefundRequest) -> RefundResult:
        if self._mock:
            return RefundResult(
                refund_so_id=f"SO-MOCK-REFUND-{request.idempotency_key[:8]}",
                original_so_id=request.original_so_id,
                replayed=False,
            )
        r = await self._request(
            "POST",
            "/api/v1/pos/refund",
            json=request.model_dump(mode="json", exclude_none=True),
        )
        if r.status_code in {409, 422}:
            body = _safe_json(r)
            raise SentryClientError(
                body.get("error", "refund_failed"),
                status_code=r.status_code,
                error_code=body.get("error"),
                response_body=body,
            )
        self._raise_for_status(r)
        return RefundResult.model_validate(r.json())

    async def log_inbound_activity(
        self,
        *,
        source: str,
        event_type: str,
        payload: dict[str, Any],
        error_context: str | None = None,
    ) -> None:
        if self._mock:
            log.info("sentry mock: inbound_activity_log %s %s", source, event_type)
            return
        body = {
            "source": source,
            "event_type": event_type,
            "payload": payload,
            "error_context": error_context,
        }
        r = await self._request("POST", "/api/inbound-activity-log", json=body)
        self._raise_for_status(r)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
    ) -> httpx.Response:
        headers = {"X-WMS-Token": self._token}
        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                async with httpx.AsyncClient(
                    base_url=self._base_url,
                    timeout=self._timeout_s,
                    headers=headers,
                ) as client:
                    r = await client.request(method, path, params=params, json=json)
                if 500 <= r.status_code < 600:
                    last_exc = SentryClientError(
                        f"sentry returned {r.status_code} for {method} {path}",
                        status_code=r.status_code,
                        response_body=_safe_json(r),
                    )
                    await self._backoff(attempt)
                    continue
                return r
            except (httpx.NetworkError, httpx.TimeoutException) as exc:
                last_exc = exc
                await self._backoff(attempt)
                continue
        assert last_exc is not None
        if isinstance(last_exc, SentryClientError):
            raise last_exc
        raise SentryClientError(
            f"sentry request failed after {MAX_RETRIES} attempts: {last_exc!r}"
        ) from last_exc

    async def _backoff(self, attempt: int) -> None:
        if self._initial_backoff_s <= 0:
            return
        await asyncio.sleep(self._initial_backoff_s * (2**attempt))

    @staticmethod
    def _raise_for_status(r: httpx.Response) -> None:
        if r.is_success:
            return
        body = _safe_json(r)
        raise SentryClientError(
            body.get("error", f"sentry returned {r.status_code}"),
            status_code=r.status_code,
            error_code=body.get("error"),
            response_body=body,
        )


def _safe_json(r: httpx.Response) -> dict[str, Any]:
    try:
        body = r.json()
    except Exception:
        return {}
    if isinstance(body, dict):
        return body
    return {}


def _mock_item_availability(*, sku: str | None, barcode: str | None) -> ItemAvailability:
    key = sku or barcode or "MOCK"
    return ItemAvailability(
        sku=sku or "MOCK-SKU",
        name=f"Mock item ({key})",
        barcode=barcode,
        is_taxable=True,
        availability=[
            WarehouseAvailability(
                warehouse_id="store",
                warehouse_name="Retail Floor",
                qty_available=10,
                bins=[BinAvailability(bin_id="A-1-1", bin_name="A-1-1", qty=10)],
            )
        ],
    )


def get_sentry_client(settings: Settings = Depends(get_settings)) -> SentryClient:
    return SentryClient.from_settings(settings)
