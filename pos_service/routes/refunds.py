from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pos_service.auth import get_current_user
from pos_service.clients import SentryClient, WindcaveClient
from pos_service.clients.sentry import get_sentry_client
from pos_service.clients.windcave import get_windcave_client
from pos_service.config import Settings, get_settings
from pos_service.db import get_db, get_engine
from pos_service.models import POSUser
from pos_service.services import refund as refund_service
from pos_service.services.checkout import CheckoutError

router = APIRouter(prefix="/api/refunds", tags=["refunds"])


def _to_http(exc: CheckoutError) -> HTTPException:
    detail: dict[str, Any] = {"error": exc.code}
    detail.update(exc.extra)
    return HTTPException(status_code=exc.http_status, detail=detail)


class LookupResponse(BaseModel):
    original_transaction_id: str
    original_sentry_so_id: str | None
    completed_at: str
    payment_method: str | None
    card_brand: str | None
    card_last4: str | None
    subtotal_cents: int
    tax_cents: int
    total_cents: int
    lines: list[dict[str, Any]]
    refundable: bool


@router.get("/lookup", response_model=LookupResponse)
def lookup(
    transaction_id: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: POSUser = Depends(get_current_user),
) -> LookupResponse:
    try:
        info = refund_service.lookup_refund(db, settings, transaction_id)
    except CheckoutError as exc:
        raise _to_http(exc) from exc
    return LookupResponse(**info)


class StartRequest(BaseModel):
    original_transaction_id: str


class StartResponse(BaseModel):
    refund_transaction_id: str
    status: str
    payment_method: str | None
    subtotal_cents: int
    tax_cents: int
    total_cents: int


@router.post("/start", response_model=StartResponse)
async def start(
    body: StartRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: POSUser = Depends(get_current_user),
) -> StartResponse:
    try:
        refund_txn = await refund_service.start_refund(
            db,
            settings,
            original_transaction_id=body.original_transaction_id,
            cashier_id=user.username,
        )
    except CheckoutError as exc:
        raise _to_http(exc) from exc
    return StartResponse(
        refund_transaction_id=refund_txn.id,
        status=refund_txn.status,
        payment_method=refund_txn.payment_method,
        subtotal_cents=refund_txn.subtotal_cents,
        tax_cents=refund_txn.tax_cents,
        total_cents=refund_txn.total_cents,
    )


class CardRefundResponse(BaseModel):
    refund_transaction_id: str
    status: str


@router.post(
    "/{refund_transaction_id}/charge-card", response_model=CardRefundResponse
)
async def charge_card(
    refund_transaction_id: str,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    sentry: SentryClient = Depends(get_sentry_client),
    windcave: WindcaveClient = Depends(get_windcave_client),
    engine: Engine = Depends(get_engine),
    user: POSUser = Depends(get_current_user),
) -> CardRefundResponse:
    try:
        refund_txn = await refund_service.charge_card_refund(
            db, settings, sentry, windcave, refund_txn_id=refund_transaction_id,
        )
    except CheckoutError as exc:
        raise _to_http(exc) from exc
    if refund_txn.status == "REFUND_PAYMENT_IN_FLIGHT":
        background.add_task(
            refund_service.poll_refund_until_complete, refund_txn.id, settings, engine
        )
    return CardRefundResponse(
        refund_transaction_id=refund_txn.id, status=refund_txn.status
    )


class CashRefundResponse(BaseModel):
    refund_transaction_id: str
    status: str
    refund_so_id: str | None


@router.post(
    "/{refund_transaction_id}/charge-cash", response_model=CashRefundResponse
)
async def charge_cash(
    refund_transaction_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    sentry: SentryClient = Depends(get_sentry_client),
    user: POSUser = Depends(get_current_user),
) -> CashRefundResponse:
    try:
        refund_txn = await refund_service.charge_cash_refund(
            db, settings, sentry, refund_txn_id=refund_transaction_id,
        )
    except CheckoutError as exc:
        raise _to_http(exc) from exc
    return CashRefundResponse(
        refund_transaction_id=refund_txn.id,
        status=refund_txn.status,
        refund_so_id=refund_txn.sentry_so_id,
    )


class StatusResponse(BaseModel):
    refund_transaction_id: str
    status: str
    is_terminal: bool
    result: dict[str, Any] | None


@router.get("/{refund_transaction_id}/status", response_model=StatusResponse)
def status_endpoint(
    refund_transaction_id: str,
    db: Session = Depends(get_db),
    user: POSUser = Depends(get_current_user),
) -> StatusResponse:
    try:
        body = refund_service.get_refund_status(db, refund_transaction_id)
    except CheckoutError as exc:
        raise _to_http(exc) from exc
    return StatusResponse(**body)


class CancelResponse(BaseModel):
    refund_transaction_id: str
    status: str


@router.post("/{refund_transaction_id}/cancel", response_model=CancelResponse)
async def cancel(
    refund_transaction_id: str,
    db: Session = Depends(get_db),
    user: POSUser = Depends(get_current_user),
) -> CancelResponse:
    try:
        refund_txn = await refund_service.cancel_refund(
            db, refund_txn_id=refund_transaction_id
        )
    except CheckoutError as exc:
        raise _to_http(exc) from exc
    return CancelResponse(
        refund_transaction_id=refund_txn.id, status=refund_txn.status
    )
