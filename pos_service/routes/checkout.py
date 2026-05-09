from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pos_service.auth import get_current_user
from pos_service.clients import SentryClient, WindcaveClient
from pos_service.clients.sentry import get_sentry_client
from pos_service.clients.windcave import get_windcave_client
from pos_service.config import Settings, get_settings
from pos_service.db import get_db, get_engine
from pos_service.models import POSUser
from pos_service.services import checkout as checkout_service
from pos_service.services.checkout import CheckoutError

router = APIRouter(prefix="/api/checkout", tags=["checkout"])


def _to_http(exc: CheckoutError) -> HTTPException:
    detail: dict[str, Any] = {"error": exc.code}
    detail.update(exc.extra)
    return HTTPException(status_code=exc.http_status, detail=detail)


class CartLineIn(BaseModel):
    sku: str
    name: str = ""
    warehouse_id: str
    bin_id: str
    quantity: int = Field(gt=0)
    is_taxable: bool = True


class CustomerAttachIn(BaseModel):
    customer_id: str | None = None
    name: str | None = None
    email: str | None = None
    phone: str | None = None


class StartRequest(BaseModel):
    lines: list[CartLineIn] = Field(min_length=1)
    customer: CustomerAttachIn | None = None


class StartResponse(BaseModel):
    transaction_id: str
    status: str
    tax_rate: float
    subtotal_cents: int
    tax_cents: int
    total_cents: int


@router.post("/start", response_model=StartResponse)
async def start(
    body: StartRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    sentry: SentryClient = Depends(get_sentry_client),
    user: POSUser = Depends(get_current_user),
) -> StartResponse:
    try:
        txn = await checkout_service.start_checkout(
            db,
            settings,
            sentry,
            lines=[line.model_dump() for line in body.lines],
            cashier_id=user.username,
            customer=body.customer.model_dump() if body.customer else None,
        )
    except CheckoutError as exc:
        raise _to_http(exc) from exc
    return StartResponse(
        transaction_id=txn.id,
        status=txn.status,
        tax_rate=settings.tax_rate,
        subtotal_cents=txn.subtotal_cents,
        tax_cents=txn.tax_cents,
        total_cents=txn.total_cents,
    )


class CashTenderRequest(BaseModel):
    amount_tendered_cents: int = Field(gt=0)


class CashResponse(BaseModel):
    transaction_id: str
    status: str
    change_cents: int
    so_id: str | None


@router.post("/{transaction_id}/charge-cash", response_model=CashResponse)
async def charge_cash(
    transaction_id: str,
    body: CashTenderRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    sentry: SentryClient = Depends(get_sentry_client),
    user: POSUser = Depends(get_current_user),
) -> CashResponse:
    try:
        txn = await checkout_service.charge_cash(
            db,
            settings,
            sentry,
            txn_id=transaction_id,
            amount_tendered_cents=body.amount_tendered_cents,
        )
    except CheckoutError as exc:
        raise _to_http(exc) from exc
    return CashResponse(
        transaction_id=txn.id,
        status=txn.status,
        change_cents=body.amount_tendered_cents - txn.total_cents,
        so_id=txn.sentry_so_id,
    )


class CardChargeResponse(BaseModel):
    transaction_id: str
    status: str


@router.post("/{transaction_id}/charge-card", response_model=CardChargeResponse)
async def charge_card(
    transaction_id: str,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    sentry: SentryClient = Depends(get_sentry_client),
    windcave: WindcaveClient = Depends(get_windcave_client),
    engine: Engine = Depends(get_engine),
    user: POSUser = Depends(get_current_user),
) -> CardChargeResponse:
    try:
        txn = await checkout_service.charge_card(
            db, settings, sentry, windcave, txn_id=transaction_id,
        )
    except CheckoutError as exc:
        raise _to_http(exc) from exc
    if txn.status == "PAYMENT_IN_FLIGHT":
        background.add_task(
            checkout_service.poll_card_until_complete, txn.id, settings, engine
        )
    return CardChargeResponse(transaction_id=txn.id, status=txn.status)


class StatusResponse(BaseModel):
    transaction_id: str
    status: str
    is_terminal: bool
    result: dict[str, Any] | None


@router.get("/{transaction_id}/status", response_model=StatusResponse)
def status_endpoint(
    transaction_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: POSUser = Depends(get_current_user),
) -> StatusResponse:
    try:
        body = checkout_service.get_status(db, settings, transaction_id)
    except CheckoutError as exc:
        raise _to_http(exc) from exc
    return StatusResponse(**body)


class CancelResponse(BaseModel):
    transaction_id: str
    status: str


@router.post("/{transaction_id}/cancel", response_model=CancelResponse)
async def cancel(
    transaction_id: str,
    db: Session = Depends(get_db),
    windcave: WindcaveClient = Depends(get_windcave_client),
    user: POSUser = Depends(get_current_user),
) -> CancelResponse:
    try:
        txn = await checkout_service.cancel_checkout(
            db, windcave, txn_id=transaction_id,
        )
    except CheckoutError as exc:
        raise _to_http(exc) from exc
    return CancelResponse(transaction_id=txn.id, status=txn.status)
