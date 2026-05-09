import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from pos_service.auth import get_current_user
from pos_service.config import Settings, get_settings
from pos_service.db import get_db
from pos_service.models import POSPrice, POSUser
from pos_service.services import pricing

router = APIRouter(prefix="/api/prices", tags=["prices"])


class PriceRow(BaseModel):
    sku: str
    unit_price_cents: int
    updated_at: datetime


class RejectedLineModel(BaseModel):
    row: int
    raw: str
    reason: str


class ImportResponse(BaseModel):
    rows_imported: int
    rows_rejected: int
    rejected_lines: list[RejectedLineModel]
    import_id: int


class ImportSummary(BaseModel):
    id: int
    filename: str
    rows_imported: int
    rows_rejected: int
    imported_by: str
    created_at: datetime


@router.get("", response_model=list[PriceRow])
def list_prices_endpoint(
    search: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    user: POSUser = Depends(get_current_user),
) -> list[PriceRow]:
    return [
        PriceRow(
            sku=p.sku, unit_price_cents=p.unit_price_cents, updated_at=p.updated_at
        )
        for p in pricing.list_prices(db, search=search, limit=limit)
    ]


@router.get("/imports", response_model=list[ImportSummary])
def list_imports_endpoint(
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    user: POSUser = Depends(get_current_user),
) -> list[ImportSummary]:
    return [
        ImportSummary(
            id=row.id,
            filename=row.filename,
            rows_imported=row.rows_imported,
            rows_rejected=row.rows_rejected,
            imported_by=row.imported_by,
            created_at=row.created_at,
        )
        for row in pricing.list_imports(db, limit=limit)
    ]


@router.get("/{sku}", response_model=PriceRow)
def get_price_endpoint(
    sku: str,
    db: Session = Depends(get_db),
    user: POSUser = Depends(get_current_user),
) -> PriceRow:
    row = db.get(POSPrice, sku)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "price_not_found"},
        )
    return PriceRow(
        sku=row.sku, unit_price_cents=row.unit_price_cents, updated_at=row.updated_at
    )


@router.post("/import", response_model=ImportResponse)
async def import_prices_endpoint(
    file: UploadFile,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: POSUser = Depends(get_current_user),
) -> ImportResponse:
    raw = await file.read()
    try:
        result = pricing.import_csv(
            db,
            file=io.BytesIO(raw),
            filename=file.filename or "uploaded.csv",
            imported_by=user.username,
            max_rows=settings.price_csv_max_rows,
        )
    except pricing.PricingError as exc:
        detail: dict = {"error": exc.code}
        if exc.code == "too_many_rows":
            detail["max"] = settings.price_csv_max_rows
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
        ) from exc
    return ImportResponse(
        rows_imported=result.rows_imported,
        rows_rejected=result.rows_rejected,
        rejected_lines=[
            RejectedLineModel(row=r.row, raw=r.raw, reason=r.reason)
            for r in result.rejected_lines
        ],
        import_id=result.import_id,
    )
