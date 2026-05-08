from datetime import datetime, timezone

import httpx
import pytest
import respx

from pos_service.clients.sentry import (
    CartLine,
    CheckoutLine,
    CheckoutRequest,
    ItemAvailability,
    PaymentSummary,
    RefundRequest,
    RefundSummary,
    SentryClient,
    SentryClientError,
    Tender,
)

BASE_URL = "http://sentry.test"


def _client(mock: bool = False) -> SentryClient:
    return SentryClient(base_url=BASE_URL, api_token="test-token", mock=mock, timeout_s=2.0)


def _availability_payload() -> dict:
    return {
        "sku": "WIDGET-001",
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


@respx.mock
async def test_lookup_availability_by_sku() -> None:
    route = respx.get(f"{BASE_URL}/api/pos/availability").mock(
        return_value=httpx.Response(200, json=_availability_payload())
    )
    item = await _client().lookup_availability(sku="WIDGET-001")
    assert route.called
    assert route.calls.last.request.url.params["sku"] == "WIDGET-001"
    assert route.calls.last.request.headers["authorization"] == "Bearer test-token"
    assert isinstance(item, ItemAvailability)
    assert item.sku == "WIDGET-001"
    assert item.availability[0].warehouse_id == "store"


@respx.mock
async def test_lookup_availability_by_barcode() -> None:
    respx.get(f"{BASE_URL}/api/pos/availability").mock(
        return_value=httpx.Response(200, json=_availability_payload())
    )
    item = await _client().lookup_availability(barcode="012345678901")
    assert item.barcode == "012345678901"


@respx.mock
async def test_lookup_availability_404_raises() -> None:
    respx.get(f"{BASE_URL}/api/pos/availability").mock(
        return_value=httpx.Response(404, json={"error": "item_not_found", "message": "no"})
    )
    with pytest.raises(SentryClientError) as exc:
        await _client().lookup_availability(sku="UNKNOWN")
    assert exc.value.status_code == 404
    assert exc.value.error_code == "item_not_found"


async def test_lookup_availability_requires_one_identifier() -> None:
    with pytest.raises(ValueError):
        await _client().lookup_availability()
    with pytest.raises(ValueError):
        await _client().lookup_availability(sku="X", barcode="Y")


@respx.mock
async def test_validate_cart_valid() -> None:
    respx.post(f"{BASE_URL}/api/pos/validate-cart").mock(
        return_value=httpx.Response(200, json={"valid": True})
    )
    result = await _client().validate_cart(
        [CartLine(sku="WIDGET-001", warehouse_id="store", bin_id="A-3-12", quantity=1)]
    )
    assert result.valid is True
    assert result.conflicts == []


@respx.mock
async def test_validate_cart_409_returns_conflicts() -> None:
    respx.post(f"{BASE_URL}/api/pos/validate-cart").mock(
        return_value=httpx.Response(
            409,
            json={
                "valid": False,
                "conflicts": [
                    {
                        "line_index": 0,
                        "sku": "WIDGET-001",
                        "warehouse_id": "store",
                        "bin_id": "A-3-12",
                        "requested_qty": 1,
                        "available_qty": 0,
                        "reason": "insufficient_stock",
                    }
                ],
            },
        )
    )
    result = await _client().validate_cart(
        [CartLine(sku="WIDGET-001", warehouse_id="store", bin_id="A-3-12", quantity=1)]
    )
    assert result.valid is False
    assert result.conflicts[0].reason == "insufficient_stock"


def _checkout_request(idem: str = "abc-123") -> CheckoutRequest:
    return CheckoutRequest(
        idempotency_key=idem,
        external_txn_ref="0000005400911209",
        cashier_id="mike",
        terminal_id="21235",
        completed_at=datetime(2026, 5, 8, 14, 23, 11, tzinfo=timezone.utc),
        payment_summary=PaymentSummary(
            method="card",
            subtotal_cents=4990,
            tax_cents=408,
            total_cents=5398,
            tenders=[
                Tender(
                    type="card",
                    amount_cents=5398,
                    card_brand="Visa",
                    card_last4="1111",
                    auth_code="000289",
                    external_ref="0000005400911209",
                )
            ],
        ),
        lines=[
            CheckoutLine(
                sku="WIDGET-001",
                warehouse_id="store",
                bin_id="A-3-12",
                quantity=1,
                unit_price_cents=1999,
                tax_cents=162,
                line_total_cents=2161,
            )
        ],
    )


@respx.mock
async def test_create_pos_so_returns_so_id() -> None:
    respx.post(f"{BASE_URL}/api/pos/checkout").mock(
        return_value=httpx.Response(
            200, json={"so_id": "SO-2026-04827", "so_number": "SO-2026-04827", "replayed": False}
        )
    )
    result = await _client().create_pos_so(_checkout_request())
    assert result.so_id == "SO-2026-04827"
    assert result.replayed is False


@respx.mock
async def test_create_pos_so_idempotent_replay_flag() -> None:
    respx.post(f"{BASE_URL}/api/pos/checkout").mock(
        return_value=httpx.Response(
            200, json={"so_id": "SO-2026-04827", "so_number": "SO-2026-04827", "replayed": True}
        )
    )
    result = await _client().create_pos_so(_checkout_request())
    assert result.replayed is True


@respx.mock
async def test_create_pos_so_409_idempotency_conflict_raises() -> None:
    respx.post(f"{BASE_URL}/api/pos/checkout").mock(
        return_value=httpx.Response(
            409, json={"error": "idempotency_conflict", "existing_so_id": "SO-X"}
        )
    )
    with pytest.raises(SentryClientError) as exc:
        await _client().create_pos_so(_checkout_request())
    assert exc.value.status_code == 409
    assert exc.value.error_code == "idempotency_conflict"


@respx.mock
async def test_create_pos_so_422_fulfillment_failed_raises() -> None:
    respx.post(f"{BASE_URL}/api/pos/checkout").mock(
        return_value=httpx.Response(
            422,
            json={
                "error": "fulfillment_failed",
                "message": "Could not decrement inventory",
                "failed_line_index": 0,
            },
        )
    )
    with pytest.raises(SentryClientError) as exc:
        await _client().create_pos_so(_checkout_request())
    assert exc.value.status_code == 422
    assert exc.value.error_code == "fulfillment_failed"


def _refund_request() -> RefundRequest:
    return RefundRequest(
        idempotency_key="9c4b-...",
        original_so_id="SO-2026-04827",
        original_external_txn_ref="0000005400911209",
        external_refund_ref="0000005400911999",
        cashier_id="mike",
        terminal_id="21235",
        completed_at=datetime(2026, 5, 9, 10, 14, 2, tzinfo=timezone.utc),
        refund_summary=RefundSummary(
            method="card",
            subtotal_cents=-4990,
            tax_cents=-408,
            total_cents=-5398,
            tenders=[
                Tender(
                    type="card",
                    amount_cents=-5398,
                    card_brand="Visa",
                    card_last4="1111",
                    auth_code="000291",
                    external_ref="0000005400911999",
                )
            ],
        ),
    )


@respx.mock
async def test_create_pos_refund_returns_credit_memo_id() -> None:
    respx.post(f"{BASE_URL}/api/pos/refund").mock(
        return_value=httpx.Response(
            200,
            json={
                "refund_so_id": "SO-2026-04901",
                "original_so_id": "SO-2026-04827",
                "replayed": False,
            },
        )
    )
    result = await _client().create_pos_refund(_refund_request())
    assert result.refund_so_id == "SO-2026-04901"
    assert result.original_so_id == "SO-2026-04827"


@respx.mock
async def test_create_pos_refund_422_window_expired() -> None:
    respx.post(f"{BASE_URL}/api/pos/refund").mock(
        return_value=httpx.Response(422, json={"error": "refund_window_expired"})
    )
    with pytest.raises(SentryClientError) as exc:
        await _client().create_pos_refund(_refund_request())
    assert exc.value.error_code == "refund_window_expired"


@respx.mock
async def test_log_inbound_activity_posts_payload() -> None:
    route = respx.post(f"{BASE_URL}/api/inbound-activity-log").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    await _client().log_inbound_activity(
        source="pos-service",
        event_type="checkout_failed_post_payment",
        payload={"foo": "bar"},
        error_context="ctx",
    )
    assert route.called
    sent = route.calls.last.request
    body = sent.read().decode()
    assert "checkout_failed_post_payment" in body
    assert sent.headers["authorization"] == "Bearer test-token"


@respx.mock
async def test_retries_5xx_then_succeeds() -> None:
    route = respx.get(f"{BASE_URL}/api/pos/availability").mock(
        side_effect=[
            httpx.Response(503, json={}),
            httpx.Response(503, json={}),
            httpx.Response(200, json=_availability_payload()),
        ]
    )
    item = await _client().lookup_availability(sku="WIDGET-001")
    assert route.call_count == 3
    assert item.sku == "WIDGET-001"


@respx.mock
async def test_retries_exhausted_raises() -> None:
    respx.get(f"{BASE_URL}/api/pos/availability").mock(
        return_value=httpx.Response(503, json={})
    )
    with pytest.raises(SentryClientError) as exc:
        await _client().lookup_availability(sku="WIDGET-001")
    assert exc.value.status_code == 503


@respx.mock
async def test_does_not_retry_4xx() -> None:
    route = respx.post(f"{BASE_URL}/api/pos/checkout").mock(
        return_value=httpx.Response(409, json={"error": "idempotency_conflict"})
    )
    with pytest.raises(SentryClientError):
        await _client().create_pos_so(_checkout_request())
    assert route.call_count == 1


async def test_mock_mode_lookup_availability_returns_canned_data() -> None:
    item = await _client(mock=True).lookup_availability(sku="ANY-SKU")
    assert item.sku == "ANY-SKU"
    assert len(item.availability) == 1
    assert item.availability[0].warehouse_id == "store"


async def test_mock_mode_validate_cart_always_valid() -> None:
    result = await _client(mock=True).validate_cart(
        [CartLine(sku="X", warehouse_id="store", bin_id="A-1-1", quantity=99)]
    )
    assert result.valid is True


async def test_mock_mode_create_pos_so_echoes_idempotency_key() -> None:
    result = await _client(mock=True).create_pos_so(_checkout_request("k0123456789"))
    assert "k0123456" in result.so_id


async def test_mock_mode_create_pos_refund_returns_fake_id() -> None:
    result = await _client(mock=True).create_pos_refund(_refund_request())
    assert result.refund_so_id.startswith("SO-MOCK-REFUND-")
    assert result.original_so_id == "SO-2026-04827"


async def test_mock_mode_log_inbound_activity_is_noop() -> None:
    await _client(mock=True).log_inbound_activity(
        source="pos-service", event_type="anything", payload={}
    )
