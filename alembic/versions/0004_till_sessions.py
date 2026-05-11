"""till_sessions + till_session_id on pos_transactions

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-11

Adds per-cashier-shift till tracking. Schema follows 06-till-sessions.md:
- till_sessions table with status (OPEN/CLOSED), opening/closing
  denomination JSON blobs, running cash tallies, expected vs counted
  variance computed at close.
- Partial unique index enforces one OPEN session per cashier.
  SQLite has supported partial indexes since 3.8 so this works in
  the dev/Docker SQLite deployment without a switch to Postgres.
- pos_transactions gains a nullable till_session_id FK; cash totals
  for variance math sum only rows where this column points at the
  closing session, so historical rows (NULL) are correctly ignored.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "till_sessions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("cashier_id", sa.String(), nullable=False),
        sa.Column("terminal_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("opening_float_cents", sa.Integer(), nullable=False),
        sa.Column("opening_denominations_json", sa.Text(), nullable=False),
        sa.Column("closing_count_cents", sa.Integer(), nullable=True),
        sa.Column("closing_denominations_json", sa.Text(), nullable=True),
        sa.Column("expected_closing_cents", sa.Integer(), nullable=True),
        sa.Column("variance_cents", sa.Integer(), nullable=True),
        sa.Column("cash_sales_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "cash_refunds_cents", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "transaction_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "cash_transaction_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "opened_at",
            sa.DateTime(),
            server_default=sa.func.current_timestamp(),
            nullable=False,
        ),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("pdf_path", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["cashier_id"], ["pos_users.username"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_till_sessions_cashier_id",
        "till_sessions",
        ["cashier_id"],
        unique=False,
    )
    op.create_index(
        "ix_till_sessions_status",
        "till_sessions",
        ["status"],
        unique=False,
    )
    # Partial unique index: at most one OPEN till per cashier.
    # SQLite-compatible (>=3.8). Postgres supports the same syntax
    # if/when this schema gets ported.
    op.create_index(
        "idx_one_open_till_per_cashier",
        "till_sessions",
        ["cashier_id"],
        unique=True,
        sqlite_where=sa.text("status = 'OPEN'"),
        postgresql_where=sa.text("status = 'OPEN'"),
    )

    with op.batch_alter_table("pos_transactions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("till_session_id", sa.String(), nullable=True))
        batch_op.create_foreign_key(
            "fk_pos_transactions_till_session",
            "till_sessions",
            ["till_session_id"],
            ["id"],
        )
        batch_op.create_index(
            batch_op.f("ix_pos_transactions_till_session_id"),
            ["till_session_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("pos_transactions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_pos_transactions_till_session_id"))
        batch_op.drop_constraint(
            "fk_pos_transactions_till_session", type_="foreignkey"
        )
        batch_op.drop_column("till_session_id")

    op.drop_index("idx_one_open_till_per_cashier", table_name="till_sessions")
    op.drop_index("ix_till_sessions_status", table_name="till_sessions")
    op.drop_index("ix_till_sessions_cashier_id", table_name="till_sessions")
    op.drop_table("till_sessions")
