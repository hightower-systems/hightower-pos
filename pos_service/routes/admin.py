import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from pos_service.auth import get_current_user
from pos_service.clients import SentryClient
from pos_service.clients.sentry import SentryClientError, get_sentry_client
from pos_service.db import get_db
from pos_service.models import POSTransaction, POSUser
from pos_service.services import reconciliation

router = APIRouter(prefix="/api/admin", tags=["admin"])


class TransactionSummary(BaseModel):
    id: str
    status: str
    txn_type: str
    payment_method: str | None
    subtotal_cents: int
    tax_cents: int
    total_cents: int
    sentry_so_id: str | None
    cashier_id: str
    terminal_id: str
    parent_transaction_id: str | None
    refund_transaction_id: str | None
    last_error: str | None
    retry_count: int
    created_at: datetime
    updated_at: datetime


class TransactionDetail(TransactionSummary):
    cart: list[dict[str, Any]]
    tenders: list[dict[str, Any]]
    windcave_txn_ref: str | None
    counterpart: TransactionSummary | None


def _summary(txn: POSTransaction) -> TransactionSummary:
    return TransactionSummary(
        id=txn.id,
        status=txn.status,
        txn_type=txn.txn_type,
        payment_method=txn.payment_method,
        subtotal_cents=txn.subtotal_cents,
        tax_cents=txn.tax_cents,
        total_cents=txn.total_cents,
        sentry_so_id=txn.sentry_so_id,
        cashier_id=txn.cashier_id,
        terminal_id=txn.terminal_id,
        parent_transaction_id=txn.parent_transaction_id,
        refund_transaction_id=txn.refund_transaction_id,
        last_error=txn.last_error,
        retry_count=txn.retry_count or 0,
        created_at=txn.created_at,
        updated_at=txn.updated_at,
    )


@router.get("/transactions", response_model=list[TransactionSummary])
def list_transactions(
    status_filter: str | None = Query(default=None, alias="status"),
    txn_type: str | None = Query(default=None, pattern="^(sale|refund)$"),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    user: POSUser = Depends(get_current_user),
) -> list[TransactionSummary]:
    stmt = select(POSTransaction).order_by(POSTransaction.created_at.desc())
    if status_filter:
        stmt = stmt.where(POSTransaction.status == status_filter)
    if txn_type:
        stmt = stmt.where(POSTransaction.txn_type == txn_type)
    stmt = stmt.limit(limit)
    return [_summary(row) for row in db.scalars(stmt)]


@router.get("/transactions/{transaction_id}", response_model=TransactionDetail)
def get_transaction(
    transaction_id: str,
    db: Session = Depends(get_db),
    user: POSUser = Depends(get_current_user),
) -> TransactionDetail:
    txn = db.get(POSTransaction, transaction_id)
    if txn is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "transaction_not_found"},
        )
    counterpart_txn: POSTransaction | None = None
    if txn.txn_type == "sale" and txn.refund_transaction_id:
        counterpart_txn = db.get(POSTransaction, txn.refund_transaction_id)
    elif txn.txn_type == "refund" and txn.parent_transaction_id:
        counterpart_txn = db.get(POSTransaction, txn.parent_transaction_id)

    cart = json.loads(txn.cart_json) if txn.cart_json else []
    tenders = json.loads(txn.tenders_json) if txn.tenders_json else []
    summary = _summary(txn)
    return TransactionDetail(
        **summary.model_dump(),
        cart=cart,
        tenders=tenders,
        windcave_txn_ref=txn.windcave_txn_ref,
        counterpart=_summary(counterpart_txn) if counterpart_txn else None,
    )


class RetrySentryResponse(BaseModel):
    transaction_id: str
    status: str
    sentry_so_id: str | None
    succeeded: bool


@router.post(
    "/transactions/{transaction_id}/retry-sentry",
    response_model=RetrySentryResponse,
)
async def retry_sentry(
    transaction_id: str,
    db: Session = Depends(get_db),
    sentry: SentryClient = Depends(get_sentry_client),
    user: POSUser = Depends(get_current_user),
) -> RetrySentryResponse:
    txn = db.get(POSTransaction, transaction_id)
    if txn is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "transaction_not_found"},
        )

    expected_status = (
        "INVENTORY_UPDATE_FAILED"
        if txn.txn_type == "sale"
        else "REFUND_INVENTORY_UPDATE_FAILED"
    )
    if txn.status != expected_status:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_state",
                "current_status": txn.status,
                "expected_status": expected_status,
            },
        )

    try:
        if txn.txn_type == "sale":
            ok = await reconciliation.retry_one_sale(db, sentry, txn)
        else:
            ok = await reconciliation.retry_one_refund(db, sentry, txn)
    except SentryClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": exc.error_code or "sentry_unavailable"},
        ) from exc

    return RetrySentryResponse(
        transaction_id=txn.id,
        status=txn.status,
        sentry_so_id=txn.sentry_so_id,
        succeeded=ok,
    )
