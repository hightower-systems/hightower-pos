"""fabric outbox

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-09

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fabric_outbox",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("pos_transaction_id", sa.String(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("fabric_so_id", sa.String(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["pos_transaction_id"], ["pos_transactions.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("fabric_outbox", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_fabric_outbox_pos_transaction_id"),
            ["pos_transaction_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_fabric_outbox_status"),
            ["status"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_fabric_outbox_next_attempt_at"),
            ["next_attempt_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("fabric_outbox", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_fabric_outbox_next_attempt_at"))
        batch_op.drop_index(batch_op.f("ix_fabric_outbox_status"))
        batch_op.drop_index(batch_op.f("ix_fabric_outbox_pos_transaction_id"))
    op.drop_table("fabric_outbox")
