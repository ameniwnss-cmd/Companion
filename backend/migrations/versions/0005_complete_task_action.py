"""pending actions can tick off an existing task

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS_BEFORE = ("task", "reminder", "weekly_plan")
KINDS_AFTER = ("task", "reminder", "weekly_plan", "complete_task")


def _kind(values: tuple[str, ...]) -> sa.Enum:
    return sa.Enum(*values, name="actionkind", native_enum=False, length=20)


def upgrade() -> None:
    op.alter_column(
        "pending_actions", "kind", type_=_kind(KINDS_AFTER), existing_type=_kind(KINDS_BEFORE)
    )


def downgrade() -> None:
    op.execute("DELETE FROM pending_actions WHERE kind = 'complete_task'")
    op.alter_column(
        "pending_actions", "kind", type_=_kind(KINDS_BEFORE), existing_type=_kind(KINDS_AFTER)
    )
