import json

import httpx
import pytest
import respx
from sqlalchemy.orm import Session

from pos_service.clients.sentry import SentryClient
from pos_service.models import POSTransaction
from pos_service.services import reconciliation

SENTRY_BASE = "http://sentry.test"


def _client() -> SentryClient:
    return SentryClient(
        base_url=SENTRY_BASE,
        api_token="test-token",
        timeout_s=2.0,
        initial_backoff_s=0.0,
    )


def _failed_sale_row(db: Session, txn_id: str = "sale-1") -> POSTransaction:
    txn = POSTransaction(
        id=txn_id,
        status="INVENTORY_UPDATE_FAILED",
        txn_type="sale",
        cart_json=json.dumps(
            [
                {
                    "sku": "WIDGET-001",
                    "name": "Widget Mark I",
                    "warehouse_id": "store",
                    "bin_id": "A-3-12",
                    "quantity": 1,
                    "is_taxable": True,
                    "unit_price_cents": 1999,
                    "tax_cents": 162,
                    "line_total_cents": 2161,
                }
            ]
        ),
        subtotal_cents=1999,
        tax_cents=162,
        total_cents=2161,
        payment_method="cash",
        tenders_json=json.dumps(
            [
                {
                    "type": "cash",
                    "amount_cents": 2161,
                    "amount_tendered_cents": 3000,
                    "change_cents": 839,
                }
            ]
        ),
        cashier_id="mike",
        terminal_id="t1",
        last_error="fulfillment_failed: ...",
    )
    db.add(txn)
    db.commit()
    return txn


def _failed_refund_row(
    db: Session, parent_id: str, refund_id: str = "ref-1"
) -> POSTransaction:
    refund = POSTransaction(
        id=refund_id,
        status="REFUND_INVENTORY_UPDATE_FAILED",
        txn_type="refund",
        parent_transaction_id=parent_id,
        cart_json=json.dumps(
            [
                {
                    "sku": "WIDGET-001",
                    "name": "Widget Mark I",
                    "warehouse_id": "store",
                    "bin_id": "A-3-12",
                    "quantity": -1,
                    "is_taxable": True,
                    "unit_price_cents": 1999,
                    "tax_cents": -162,
                    "line_total_cents": -2161,
                }
            ]
        ),
        subtotal_cents=-1999,
        tax_cents=-162,
        total_cents=-2161,
        payment_method="cash",
        tenders_json=json.dumps([{"type": "cash", "amount_cents": -2161}]),
        cashier_id="mike",
        terminal_id="t1",
        last_error="fulfillment_failed: ...",
    )
    db.add(refund)
    db.commit()
    return refund


@pytest.mark.asyncio
@respx.mock
async def test_retry_failed_sales_succeeds(db: Session) -> None:
    txn = _failed_sale_row(db)
    respx.post(f"{SENTRY_BASE}/api/v1/pos/checkout").mock(
        return_value=httpx.Response(
            200,
            json={"so_id": "SO-RECON-1", "so_number": "SO-RECON-1", "replayed": False},
        )
    )
    report = await reconciliation.retry_failed_sales(db, _client())
    assert report.scanned == 1
    assert report.succeeded == [txn.id]
    assert report.still_failing == []
    db.refresh(txn)
    assert txn.status == "COMPLETE"
    assert txn.sentry_so_id == "SO-RECON-1"
    assert txn.last_error is None
    assert txn.retry_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_retry_failed_sales_still_failing_increments_retry_count(
    db: Session,
) -> None:
    txn = _failed_sale_row(db)
    respx.post(f"{SENTRY_BASE}/api/v1/pos/checkout").mock(
        return_value=httpx.Response(422, json={"error": "fulfillment_failed"})
    )
    report = await reconciliation.retry_failed_sales(db, _client())
    assert report.scanned == 1
    assert report.succeeded == []
    assert report.still_failing == [txn.id]
    db.refresh(txn)
    assert txn.status == "INVENTORY_UPDATE_FAILED"
    assert txn.retry_count == 1
    assert "fulfillment_failed" in (txn.last_error or "")


@pytest.mark.asyncio
async def test_retry_failed_sales_no_rows_returns_empty_report(db: Session) -> None:
    report = await reconciliation.retry_failed_sales(db, _client())
    assert report.scanned == 0
    assert report.succeeded == []
    assert report.still_failing == []


@pytest.mark.asyncio
@respx.mock
async def test_retry_failed_refunds_succeeds_and_links_parent(db: Session) -> None:
    parent = _failed_sale_row(db, txn_id="parent-1")
    parent.status = "COMPLETE"
    parent.sentry_so_id = "SO-PARENT"
    db.commit()
    refund = _failed_refund_row(db, parent_id=parent.id)
    respx.post(f"{SENTRY_BASE}/api/v1/pos/refund").mock(
        return_value=httpx.Response(
            200,
            json={
                "refund_so_id": "SO-REFUND-RECON",
                "original_so_id": "SO-PARENT",
                "replayed": False,
            },
        )
    )
    report = await reconciliation.retry_failed_refunds(db, _client())
    assert report.succeeded == [refund.id]
    db.refresh(refund)
    db.refresh(parent)
    assert refund.status == "COMPLETE"
    assert refund.sentry_so_id == "SO-REFUND-RECON"
    assert parent.refund_transaction_id == refund.id


@pytest.mark.asyncio
@respx.mock
async def test_retry_failed_refunds_still_failing(db: Session) -> None:
    parent = _failed_sale_row(db, txn_id="parent-2")
    parent.status = "COMPLETE"
    db.commit()
    refund = _failed_refund_row(db, parent_id=parent.id, refund_id="ref-2")
    respx.post(f"{SENTRY_BASE}/api/v1/pos/refund").mock(
        return_value=httpx.Response(422, json={"error": "fulfillment_failed"})
    )
    report = await reconciliation.retry_failed_refunds(db, _client())
    assert report.still_failing == [refund.id]
    db.refresh(refund)
    assert refund.status == "REFUND_INVENTORY_UPDATE_FAILED"
    assert refund.retry_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_retry_failed_refunds_skips_when_parent_missing(db: Session) -> None:
    refund = _failed_refund_row(db, parent_id="ghost-id", refund_id="ref-orphan")
    report = await reconciliation.retry_failed_refunds(db, _client())
    assert report.scanned == 1
    assert report.succeeded == []
    assert report.still_failing == [refund.id]
