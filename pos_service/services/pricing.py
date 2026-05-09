import csv
import io
import json
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import BinaryIO

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from pos_service.models import POSPrice, POSPriceImport

EXPECTED_HEADER = ("sku", "price")
REJECTED_LINES_CAP = 100


class PricingError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass
class RejectedLine:
    row: int
    raw: str
    reason: str


@dataclass
class ImportResult:
    rows_imported: int
    rows_rejected: int
    rejected_lines: list[RejectedLine]
    import_id: int


def get_price_cents(db: Session, sku: str) -> int | None:
    row = db.get(POSPrice, sku)
    return row.unit_price_cents if row is not None else None


def list_prices(
    db: Session, *, search: str | None = None, limit: int = 50
) -> list[POSPrice]:
    stmt = select(POSPrice)
    if search:
        stmt = stmt.where(POSPrice.sku.like(f"%{search}%"))
    stmt = stmt.order_by(POSPrice.sku).limit(limit)
    return list(db.scalars(stmt))


def list_imports(db: Session, *, limit: int = 50) -> list[POSPriceImport]:
    stmt = select(POSPriceImport).order_by(POSPriceImport.id.desc()).limit(limit)
    return list(db.scalars(stmt))


def import_csv(
    db: Session,
    *,
    file: BinaryIO,
    filename: str,
    imported_by: str,
    max_rows: int,
) -> ImportResult:
    raw_bytes = file.read()
    text = raw_bytes.decode("utf-8-sig", errors="replace")

    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration as exc:
        raise PricingError("bad_header", "csv is empty") from exc

    normalized_header = tuple(h.strip().lower() for h in header)
    if normalized_header != EXPECTED_HEADER:
        raise PricingError(
            "bad_header",
            f"expected header {EXPECTED_HEADER!r}, got {tuple(header)!r}",
        )

    raw_rows: list[tuple[int, list[str]]] = []
    for row_num, row in enumerate(reader, start=2):
        if not row or all(not cell.strip() for cell in row):
            continue
        raw_rows.append((row_num, row))

    if len(raw_rows) > max_rows:
        raise PricingError(
            "too_many_rows",
            f"{len(raw_rows)} data rows exceed the {max_rows}-row cap",
        )

    upserts: list[dict] = []
    rejected: list[RejectedLine] = []
    for row_num, row in raw_rows:
        raw_line = ",".join(row)
        if len(row) < 2:
            rejected.append(RejectedLine(row=row_num, raw=raw_line, reason="missing_columns"))
            continue
        sku = row[0].strip()
        price_text = row[1].strip()
        if not sku:
            rejected.append(RejectedLine(row=row_num, raw=raw_line, reason="empty_sku"))
            continue
        try:
            price = Decimal(price_text)
        except (InvalidOperation, ValueError):
            rejected.append(
                RejectedLine(row=row_num, raw=raw_line, reason="price_not_numeric")
            )
            continue
        if price < 0:
            rejected.append(RejectedLine(row=row_num, raw=raw_line, reason="price_negative"))
            continue
        cents = int((price * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        upserts.append({"sku": sku, "unit_price_cents": cents})

    if upserts:
        stmt = sqlite_insert(POSPrice).values(upserts)
        stmt = stmt.on_conflict_do_update(
            index_elements=["sku"],
            set_={"unit_price_cents": stmt.excluded.unit_price_cents},
        )
        db.execute(stmt)

    capped = rejected[:REJECTED_LINES_CAP]
    audit = POSPriceImport(
        filename=filename,
        rows_imported=len(upserts),
        rows_rejected=len(rejected),
        rejected_lines_json=(
            json.dumps([r.__dict__ for r in capped]) if capped else None
        ),
        imported_by=imported_by,
    )
    db.add(audit)
    db.commit()
    db.refresh(audit)

    return ImportResult(
        rows_imported=len(upserts),
        rows_rejected=len(rejected),
        rejected_lines=capped,
        import_id=audit.id,
    )


__all__ = [
    "EXPECTED_HEADER",
    "REJECTED_LINES_CAP",
    "ImportResult",
    "PricingError",
    "RejectedLine",
    "get_price_cents",
    "import_csv",
    "list_imports",
    "list_prices",
]
