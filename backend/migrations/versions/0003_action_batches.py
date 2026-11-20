"""group pending actions into batches and remember the record each one created

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("pending_actions", sa.Column("batch_id", sa.Uuid(), nullable=True))
    op.execute("UPDATE pending_actions SET batch_id = id")
    op.alter_column("pending_actions", "batch_id", nullable=False)
    op.create_index(
        op.f("ix_pending_actions_batch_id"), "pending_actions", ["batch_id"], unique=False
    )
    op.add_column("pending_actions", sa.Column("record_id", sa.Uuid(), nullable=True))
    op.alter_column(
        "pending_actions",
        "status",
        type_=sa.Enum(
            "pending",
            "confirmed",
            "cancelled",
            "expired",
            "undone",
            name="actionstatus",
            native_enum=False,
            length=20,
        ),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.execute("UPDATE pending_actions SET status = 'cancelled' WHERE status = 'undone'")
    op.drop_column("pending_actions", "record_id")
    op.drop_index(op.f("ix_pending_actions_batch_id"), table_name="pending_actions")
    op.drop_column("pending_actions", "batch_id")
