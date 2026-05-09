from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
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

    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


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
