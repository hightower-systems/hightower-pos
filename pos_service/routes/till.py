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

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from pos_service import auth as auth_service
from pos_service.config import Settings, get_settings
from pos_service.db import get_db
from pos_service.models import TillSession
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
    ctx: auth_service.AuthContext = Depends(auth_service.get_auth),
) -> CloseTillResponse:
    try:
        session = till_service.close_session(
            db,
            cashier_id=ctx.user.username,
            closing_denominations=body.closing_denominations,
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
    ctx: auth_service.AuthContext = Depends(auth_service.get_auth),
) -> Response:
    """Stream the close-report PDF. Phase 1 is a placeholder that
    returns 503 not_implemented when the session exists but the PDF
    has not been generated (Phase 2 wires reportlab). 404 if no such
    session, 404 if the session is still OPEN."""
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
    if session.pdf_path is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "pdf_not_yet_implemented"},
        )
    # Phase 2 wires the actual disk read + Response(content=..., media_type=...).
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"error": "pdf_not_yet_implemented"},
    )
