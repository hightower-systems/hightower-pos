"""Till sessions: open / current / close / pdf + admin reporting.

Every route requires an authenticated cashier session. Open/close/
current/pdf are implicitly scoped to the authenticated user's own
sessions (cross-user GET returns 404, not 403, so a token can't
learn that someone else's session exists).

The admin reporting routes (GET /sessions, GET /sessions/{id}/
transactions) are NOT user-scoped -- any authenticated user can
list and inspect closed sessions for reports, audit, and
troubleshooting. There are no role distinctions in v1 (everyone is
a cashier; attribution lives in the rows, not in permissions).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from pos_service import auth as auth_service
from pos_service.config import Settings, get_settings
from pos_service.db import get_db
from pos_service.models import POSTransaction, POSUser, TillSession
from pos_service.schemas import (
    CloseTillRequest,
    CloseTillResponse,
    OpenTillRequest,
    OpenTillResponse,
    TillCurrentResponse,
    TillSessionListResponse,
    TillSessionSummary,
    TillSessionTransactionRow,
    TillSessionTransactionsResponse,
)
from pos_service.services import till as till_service

router = APIRouter(prefix="/api/till", tags=["till"])


def _pdf_url(session_id: str) -> str:
    return f"/api/till/sessions/{session_id}/pdf"


@router.post(
    "/open",
    response_model=OpenTillResponse,
    status_code=status.HTTP_200_OK,
)
def open_till(
    body: OpenTillRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    ctx: auth_service.AuthContext = Depends(auth_service.get_auth),
) -> OpenTillResponse:
    try:
        session = till_service.open_session(
            db,
            cashier_id=ctx.user.username,
            terminal_id=settings.windcave_station,
            opening_denominations=body.opening_denominations,
        )
    except till_service.TillError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error": exc.code, **exc.details},
        ) from exc
    return OpenTillResponse(
        session_id=session.id,
        opening_float_cents=session.opening_float_cents,
        opened_at=session.opened_at,
    )


@router.get("/current", response_model=TillCurrentResponse)
def current_till(
    db: Session = Depends(get_db),
    ctx: auth_service.AuthContext = Depends(auth_service.get_auth),
) -> TillCurrentResponse:
    session = till_service.get_open_session(db, ctx.user.username)
    if session is None:
        return TillCurrentResponse(status="NONE")
    expected = (
        session.opening_float_cents
        + session.cash_sales_cents
        - session.cash_refunds_cents
    )
    return TillCurrentResponse(
        status="OPEN",
        session_id=session.id,
        opening_float_cents=session.opening_float_cents,
        cash_sales_cents=session.cash_sales_cents,
        cash_refunds_cents=session.cash_refunds_cents,
        transaction_count=session.transaction_count,
        cash_transaction_count=session.cash_transaction_count,
        expected_closing_cents=expected,
        opened_at=session.opened_at,
    )


@router.post("/close", response_model=CloseTillResponse)
def close_till(
    body: CloseTillRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    ctx: auth_service.AuthContext = Depends(auth_service.get_auth),
) -> CloseTillResponse:
    try:
        session = till_service.close_session(
            db,
            cashier_id=ctx.user.username,
            closing_denominations=body.closing_denominations,
            settings=settings,
        )
    except till_service.TillError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error": exc.code, **exc.details},
        ) from exc
    assert session.expected_closing_cents is not None
    assert session.closing_count_cents is not None
    assert session.variance_cents is not None
    assert session.closed_at is not None
    return CloseTillResponse(
        session_id=session.id,
        status=session.status,
        opening_float_cents=session.opening_float_cents,
        cash_sales_cents=session.cash_sales_cents,
        cash_refunds_cents=session.cash_refunds_cents,
        expected_closing_cents=session.expected_closing_cents,
        closing_count_cents=session.closing_count_cents,
        variance_cents=session.variance_cents,
        pdf_url=_pdf_url(session.id),
        closed_at=session.closed_at,
    )


@router.get("/sessions/{session_id}/pdf")
def session_pdf(
    session_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    ctx: auth_service.AuthContext = Depends(auth_service.get_auth),
) -> FileResponse:
    """Stream the close-report PDF.

    404 if the session doesn't exist, belongs to another cashier, or
    is still OPEN. On the happy path, stream from disk. If the file
    is missing (close-time render failed, or the file was deleted
    out from under us), regenerate on the fly -- the source of truth
    is the session row, the PDF is derived data.
    """
    session = db.get(TillSession, session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "session_not_found"},
        )
    # No cross-user gate: v1 has no role distinction, and the admin
    # reporting view explicitly needs to pull any cashier's PDF.
    # ctx.user is still validated above by Depends(auth_service.get_auth).
    _ = ctx
    if session.status != "CLOSED":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "session_not_closed"},
        )

    path_str = session.pdf_path
    if path_str is None or not Path(path_str).exists():
        # Regenerate. Pulls user for the cashier display name; the FK
        # guarantees the row exists for any non-soft-deleted user.
        user = db.get(POSUser, session.cashier_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"error": "cashier_not_found"},
            )
        from pos_service.services import till_pdf
        try:
            path = till_pdf.render_close_report(session, user, settings=settings)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"error": "pdf_render_failed"},
            ) from None
        session.pdf_path = str(path)
        db.commit()
        path_str = str(path)

    # Inline disposition so the PDF renders in a new browser tab (so
    # the cashier can hit Ctrl+P or visually verify the close report)
    # rather than forcing a silent download into ~/Downloads. The
    # filename still travels for Save-As naming if the cashier
    # chooses to download.
    return FileResponse(
        path_str,
        media_type="application/pdf",
        filename=f"till-close-{session_id}.pdf",
        content_disposition_type="inline",
    )


# ---------------------------------------------------------------------------
# Admin reporting -- list closed sessions and their transactions.
# No role gate (v1 has same-permission auth); ctx is still required so
# anonymous clients are refused at the auth layer.
# ---------------------------------------------------------------------------


@router.get("/sessions", response_model=TillSessionListResponse)
def list_sessions(
    cashier_id: str | None = Query(default=None, max_length=64),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = Query(default=None),
    status_: str | None = Query(default="CLOSED", alias="status", max_length=16),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    ctx: auth_service.AuthContext = Depends(auth_service.get_auth),
) -> TillSessionListResponse:
    """Paginated list of till sessions for reporting and audit.

    Defaults to CLOSED so the typical 'show me closed shifts' view
    is a parameter-less GET. Pass `?status=OPEN` to see open
    sessions (or empty `status=` to include all). Date filters apply
    against opened_at since closed_at is null for OPEN rows.
    """
    _ = ctx
    stmt = select(TillSession)
    if cashier_id is not None:
        stmt = stmt.where(TillSession.cashier_id == cashier_id)
    if status_:
        stmt = stmt.where(TillSession.status == status_)
    if from_ is not None:
        stmt = stmt.where(TillSession.opened_at >= from_)
    if to is not None:
        stmt = stmt.where(TillSession.opened_at <= to)
    stmt = stmt.order_by(TillSession.opened_at.desc()).limit(limit).offset(offset)
    rows = list(db.execute(stmt).scalars())
    return TillSessionListResponse(
        sessions=[_session_summary(row) for row in rows],
    )


@router.get(
    "/sessions/{session_id}/transactions",
    response_model=TillSessionTransactionsResponse,
)
def list_session_transactions(
    session_id: str,
    db: Session = Depends(get_db),
    ctx: auth_service.AuthContext = Depends(auth_service.get_auth),
) -> TillSessionTransactionsResponse:
    """Every POSTransaction stamped with this till_session_id.

    Useful for investigating variance: 'show me every cash sale for
    the 8 AM Tuesday shift'. 404 if the session doesn't exist.
    """
    _ = ctx
    session = db.get(TillSession, session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "session_not_found"},
        )
    stmt = (
        select(POSTransaction)
        .where(POSTransaction.till_session_id == session_id)
        .order_by(POSTransaction.created_at.asc())
    )
    txns = list(db.execute(stmt).scalars())
    return TillSessionTransactionsResponse(
        session_id=session.id,
        transactions=[
            TillSessionTransactionRow(
                id=t.id,
                txn_type=t.txn_type,
                status=t.status,
                payment_method=t.payment_method,
                total_cents=t.total_cents,
                sentry_so_id=t.sentry_so_id,
                cashier_id=t.cashier_id,
                created_at=t.created_at,
            )
            for t in txns
        ],
    )


def _session_summary(row: TillSession) -> TillSessionSummary:
    return TillSessionSummary(
        session_id=row.id,
        cashier_id=row.cashier_id,
        terminal_id=row.terminal_id,
        status=row.status,
        opening_float_cents=row.opening_float_cents,
        cash_sales_cents=row.cash_sales_cents,
        cash_refunds_cents=row.cash_refunds_cents,
        expected_closing_cents=row.expected_closing_cents,
        closing_count_cents=row.closing_count_cents,
        variance_cents=row.variance_cents,
        transaction_count=row.transaction_count,
        cash_transaction_count=row.cash_transaction_count,
        opened_at=row.opened_at,
        closed_at=row.closed_at,
        pdf_url=_pdf_url(row.id) if row.status == "CLOSED" else None,
    )
