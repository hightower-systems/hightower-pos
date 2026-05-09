"""customer attach on pos_transactions

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-09

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("pos_transactions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("customer_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("customer_name", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("customer_email", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("customer_phone", sa.String(), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_pos_transactions_customer_id"),
            ["customer_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("pos_transactions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_pos_transactions_customer_id"))
        batch_op.drop_column("customer_phone")
        batch_op.drop_column("customer_email")
        batch_op.drop_column("customer_name")
        batch_op.drop_column("customer_id")
