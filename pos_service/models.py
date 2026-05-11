from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pos_service.db import Base


class POSTransaction(Base):
    __tablename__ = "pos_transactions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    txn_type: Mapped[str] = mapped_column(String, nullable=False, default="sale")

    parent_transaction_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("pos_transactions.id"), nullable=True, index=True
    )
    refund_transaction_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("pos_transactions.id"), nullable=True
    )

    cart_json: Mapped[str] = mapped_column(Text, nullable=False)
    subtotal_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    tax_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    total_cents: Mapped[int] = mapped_column(Integer, nullable=False)

    payment_method: Mapped[str | None] = mapped_column(String, nullable=True)
    tenders_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    windcave_txn_ref: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    windcave_response_xml: Mapped[str | None] = mapped_column(Text, nullable=True)
    sentry_so_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    cashier_id: Mapped[str] = mapped_column(String, nullable=False)
    terminal_id: Mapped[str] = mapped_column(String, nullable=False)

    customer_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    customer_name: Mapped[str | None] = mapped_column(String, nullable=True)
    customer_email: Mapped[str | None] = mapped_column(String, nullable=True)
    customer_phone: Mapped[str | None] = mapped_column(String, nullable=True)

    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Stamped at PAYMENT_SUCCESS with whichever till session was open
    # for the cashier at finalize time. Nullable so pre-feature
    # transactions and any txn that completes when no till is open
    # (defensive case) still persist; the till math sums only stamped
    # rows.
    till_session_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("till_sessions.id"), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class TillSession(Base):
    __tablename__ = "till_sessions"
    # Partial unique index: at most one OPEN session per cashier.
    # Mirrors the production-side definition in alembic mig 0004 so
    # tests built off Base.metadata.create_all enforce the same
    # invariant.
    __table_args__ = (
        Index(
            "idx_one_open_till_per_cashier",
            "cashier_id",
            unique=True,
            sqlite_where=text("status = 'OPEN'"),
            postgresql_where=text("status = 'OPEN'"),
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)  # UUID4
    cashier_id: Mapped[str] = mapped_column(
        String, ForeignKey("pos_users.username"), nullable=False, index=True
    )
    terminal_id: Mapped[str] = mapped_column(String, nullable=False)
    # OPEN | CLOSED. A partial unique index on (cashier_id) WHERE
    # status='OPEN' enforces one open session per cashier; see
    # alembic mig 0004.
    status: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # JSON: {"hundred": 1, "fifty": 2, "twenty": 5, ...}. The
    # canonical denomination key set lives in services/till.py
    # (DENOMINATIONS); writing one place keeps the React side and
    # the PDF renderer in lockstep on key names.
    opening_float_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    opening_denominations_json: Mapped[str] = mapped_column(Text, nullable=False)

    # Populated at close. Nullable so the row is creatable in the
    # OPEN state without bogus zero values that look like a real
    # zero-cash close.
    closing_count_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    closing_denominations_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_closing_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    variance_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Running tallies updated as cash transactions complete during
    # the open session. Cash refunds DECREMENT cash_sales when the
    # in-app refund flow is used (per till plan doc + user clarif:
    # the v1 'refunds NOT reflected' note in the doc predates the
    # built-and-shipping refund flow).
    cash_sales_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cash_refunds_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    transaction_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cash_transaction_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    opened_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Filesystem path to the generated close-report PDF. Populated by
    # services/till_pdf.py in Phase 2; left nullable in Phase 1.
    pdf_path: Mapped[str | None] = mapped_column(String, nullable=True)


class POSUser(Base):
    __tablename__ = "pos_users"

    username: Mapped[str] = mapped_column(String, primary_key=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class POSSession(Base):
    __tablename__ = "pos_sessions"

    session_token: Mapped[str] = mapped_column(String, primary_key=True)
    username: Mapped[str] = mapped_column(
        String, ForeignKey("pos_users.username"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class POSPrice(Base):
    __tablename__ = "pos_prices"

    sku: Mapped[str] = mapped_column(String, primary_key=True)
    unit_price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class POSPriceImport(Base):
    __tablename__ = "pos_price_imports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    rows_imported: Mapped[int] = mapped_column(Integer, nullable=False)
    rows_rejected: Mapped[int] = mapped_column(Integer, nullable=False)
    rejected_lines_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    imported_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )


class FabricOutboxEntry(Base):
    __tablename__ = "fabric_outbox"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    pos_transaction_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("pos_transactions.id"),
        nullable=False,
        index=True,
    )
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, index=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    fabric_so_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
