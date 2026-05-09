"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-08

"""
from collections.abc import Sequence

import bcrypt
import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pos_users",
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("must_change_password", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("username"),
    )

    users_table = sa.table(
        "pos_users",
        sa.column("username", sa.String()),
        sa.column("password_hash", sa.String()),
        sa.column("display_name", sa.String()),
        sa.column("is_active", sa.Boolean()),
        sa.column("must_change_password", sa.Boolean()),
    )
    admin_hash = bcrypt.hashpw(b"admin", bcrypt.gensalt()).decode("utf-8")
    op.bulk_insert(
        users_table,
        [
            {
                "username": "admin",
                "password_hash": admin_hash,
                "display_name": "Administrator",
                "is_active": True,
                "must_change_password": True,
            }
        ],
    )

    op.create_table(
        "pos_sessions",
        sa.Column("session_token", sa.String(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["username"], ["pos_users.username"]),
        sa.PrimaryKeyConstraint("session_token"),
    )
    with op.batch_alter_table("pos_sessions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_pos_sessions_expires_at"), ["expires_at"], unique=False
        )

    op.create_table(
        "pos_prices",
        sa.Column("sku", sa.String(), nullable=False),
        sa.Column("unit_price_cents", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("sku"),
    )

    op.create_table(
        "pos_price_imports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("rows_imported", sa.Integer(), nullable=False),
        sa.Column("rows_rejected", sa.Integer(), nullable=False),
        sa.Column("rejected_lines_json", sa.Text(), nullable=True),
        sa.Column("imported_by", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "pos_transactions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("txn_type", sa.String(), nullable=False),
        sa.Column("parent_transaction_id", sa.String(), nullable=True),
        sa.Column("refund_transaction_id", sa.String(), nullable=True),
        sa.Column("cart_json", sa.Text(), nullable=False),
        sa.Column("subtotal_cents", sa.Integer(), nullable=False),
        sa.Column("tax_cents", sa.Integer(), nullable=False),
        sa.Column("total_cents", sa.Integer(), nullable=False),
        sa.Column("payment_method", sa.String(), nullable=True),
        sa.Column("tenders_json", sa.Text(), nullable=True),
        sa.Column("windcave_txn_ref", sa.String(), nullable=True),
        sa.Column("windcave_response_xml", sa.Text(), nullable=True),
        sa.Column("sentry_so_id", sa.String(), nullable=True),
        sa.Column("cashier_id", sa.String(), nullable=False),
        sa.Column("terminal_id", sa.String(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["parent_transaction_id"], ["pos_transactions.id"]),
        sa.ForeignKeyConstraint(["refund_transaction_id"], ["pos_transactions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("pos_transactions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_pos_transactions_status"), ["status"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_pos_transactions_parent_transaction_id"),
            ["parent_transaction_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_pos_transactions_sentry_so_id"), ["sentry_so_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_pos_transactions_windcave_txn_ref"),
            ["windcave_txn_ref"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("pos_transactions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_pos_transactions_windcave_txn_ref"))
        batch_op.drop_index(batch_op.f("ix_pos_transactions_sentry_so_id"))
        batch_op.drop_index(batch_op.f("ix_pos_transactions_parent_transaction_id"))
        batch_op.drop_index(batch_op.f("ix_pos_transactions_status"))
    op.drop_table("pos_transactions")

    op.drop_table("pos_price_imports")
    op.drop_table("pos_prices")

    with op.batch_alter_table("pos_sessions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_pos_sessions_expires_at"))
    op.drop_table("pos_sessions")

    op.drop_table("pos_users")
