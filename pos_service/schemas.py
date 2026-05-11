from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class TillSessionBrief(BaseModel):
    """Compact till-session summary attached to login + logout
    responses so the React client can route the user into the
    open-till modal (or skip it) without a second round-trip."""

    session_id: str
    status: str  # OPEN | CLOSED
    opened_at: datetime


class UserInfo(BaseModel):
    username: str
    display_name: str
    expires_at: datetime
    must_change_password: bool
    # Present and OPEN when the cashier has an open till; null when
    # they don't (login pushes them into open-till modal). The field
    # is omitted (not null) when this response shape is used outside
    # the login/me context.
    till_session: TillSessionBrief | None = None


class LogoutResponse(BaseModel):
    """200 on logout. The optional warning field lets the React
    client put up a 'you have an open till' confirmation without
    blocking the logout itself -- the cashier still gets logged out."""

    logged_out: bool = True
    warning: str | None = None
    session_id: str | None = None


class OpenTillRequest(BaseModel):
    # The dict keys must be drawn from services.till.DENOMINATION_KEYS;
    # validation is in services.till.denominations_to_cents so the
    # error shape stays consistent between this endpoint and close.
    opening_denominations: dict[str, int]


class CloseTillRequest(BaseModel):
    closing_denominations: dict[str, int]


class TillCurrentResponse(BaseModel):
    """GET /api/till/current. status='NONE' when no open session;
    all other fields populated only when status='OPEN'."""

    status: str  # OPEN | NONE
    session_id: str | None = None
    opening_float_cents: int | None = None
    cash_sales_cents: int | None = None
    cash_refunds_cents: int | None = None
    transaction_count: int | None = None
    cash_transaction_count: int | None = None
    expected_closing_cents: int | None = None
    opened_at: datetime | None = None


class OpenTillResponse(BaseModel):
    session_id: str
    opening_float_cents: int
    opened_at: datetime


class CloseTillResponse(BaseModel):
    session_id: str
    status: str
    opening_float_cents: int
    cash_sales_cents: int
    cash_refunds_cents: int
    expected_closing_cents: int
    closing_count_cents: int
    variance_cents: int
    pdf_url: str
    closed_at: datetime
