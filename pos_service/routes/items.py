from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from pos_service.auth import get_current_user
from pos_service.clients import SentryClient, SentryClientError, get_sentry_client
from pos_service.clients.sentry import WarehouseAvailability
from pos_service.config import Settings, get_settings
from pos_service.db import get_db
from pos_service.models import POSUser
from pos_service.services import pricing

router = APIRouter(prefix="/api/items", tags=["items"])


class ItemLookupResponse(BaseModel):
    sku: str
    name: str
    barcode: str | None
    unit_price_cents: int
    tax_rate: float
    is_taxable: bool
    availability: list[WarehouseAvailability]


@router.get("/lookup", response_model=ItemLookupResponse)
async def lookup_item(
    barcode: str | None = Query(default=None, max_length=64),
    sku: str | None = Query(default=None, max_length=64),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    sentry: SentryClient = Depends(get_sentry_client),
    user: POSUser = Depends(get_current_user),
) -> ItemLookupResponse:
    if (barcode is None) == (sku is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "exactly_one_identifier_required"},
        )
    try:
        avail = await sentry.lookup_availability(barcode=barcode, sku=sku)
    except SentryClientError as exc:
        if exc.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "item_not_found"},
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": "sentry_unavailable"},
        ) from exc

    price = pricing.get_price_cents(db, avail.sku)
    if price is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": "price_missing", "sku": avail.sku},
        )

    return ItemLookupResponse(
        sku=avail.sku,
        name=avail.name,
        barcode=avail.barcode,
        unit_price_cents=price,
        tax_rate=settings.tax_rate,
        is_taxable=avail.is_taxable,
        availability=avail.availability,
    )
