"""Till sessions: open / current / close / pdf.

Every route requires an authenticated cashier session. The till
session is implicitly scoped to ctx.user.username; the request body
does not carry cashier_id (and would be ignored if it did) -- only
the authenticated user can open or close their own till.

The PDF endpoint in Phase 1 returns 404 with a placeholder body
indicating Phase 2 will generate the file. The session row still
records pdf_path = None until Phase 2.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from pos_service import auth as auth_service
from pos_service.config import Settings, get_settings
from pos_service.db import get_db
from pos_service.models import POSUser, TillSession
from pos_service.schemas import (
    CloseTillRequest,
    CloseTillResponse,
    OpenTillRequest,
    OpenTillResponse,
    TillCurrentResponse,
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
    if session is None or session.cashier_id != ctx.user.username:
        # 404 (not 403) for the cross-user case so a token doesn't
        # learn that a session_id it shouldn't see exists.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "session_not_found"},
        )
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

    return FileResponse(
        path_str,
        media_type="application/pdf",
        filename=f"till-close-{session_id}.pdf",
    )
