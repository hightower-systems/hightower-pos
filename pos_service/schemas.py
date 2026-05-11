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


# --- Admin reporting -----------------------------------------------------


class TillSessionSummary(BaseModel):
    """One row in the till-sessions admin list. closing_*, variance_*,
    and pdf_url are null for OPEN sessions."""

    session_id: str
    cashier_id: str
    terminal_id: str
    status: str  # OPEN | CLOSED
    opening_float_cents: int
    cash_sales_cents: int
    cash_refunds_cents: int
    expected_closing_cents: int | None = None
    closing_count_cents: int | None = None
    variance_cents: int | None = None
    transaction_count: int
    cash_transaction_count: int
    opened_at: datetime
    closed_at: datetime | None = None
    pdf_url: str | None = None


class TillSessionListResponse(BaseModel):
    sessions: list[TillSessionSummary]


class TillSessionTransactionRow(BaseModel):
    """Compact transaction view for the per-session 'show me every
    txn during this shift' admin endpoint. Lighter than the full
    POSTransaction row -- just enough for variance investigation."""

    id: str
    txn_type: str
    status: str
    payment_method: str | None = None
    total_cents: int
    sentry_so_id: str | None = None
    cashier_id: str
    created_at: datetime


class TillSessionTransactionsResponse(BaseModel):
    session_id: str
    transactions: list[TillSessionTransactionRow]


# --- User management ----------------------------------------------------


class UserSummary(BaseModel):
    """Admin-view row for a POS cashier. No password material on the
    wire (not even the hash) -- the only paths that ever touch a
    password are the create and reset-password handlers, and both
    take the plaintext as input only."""

    username: str
    display_name: str
    is_active: bool
    must_change_password: bool
    created_at: datetime


class UsersListResponse(BaseModel):
    users: list[UserSummary]


class CreateUserRequest(BaseModel):
    # Username constraints mirror what the auth model can store +
    # what feels safe on URL paths and printed receipts. 64 chars is
    # the SQLAlchemy String() column ceiling.
    username: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=128)
    initial_password: str = Field(min_length=8, max_length=256)


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=8, max_length=256)
