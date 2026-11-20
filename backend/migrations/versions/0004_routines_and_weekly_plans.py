"""repeating tasks and reminders, and weekly plans for any activity

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS_BEFORE = ("task", "reminder", "workout_plan")
KINDS_AFTER = ("task", "reminder", "weekly_plan")


def _kind(values: tuple[str, ...]) -> sa.Enum:
    return sa.Enum(*values, name="actionkind", native_enum=False, length=20)


def upgrade() -> None:
    op.add_column("tasks", sa.Column("repeat_days", postgresql.JSONB(), nullable=True))
    op.add_column("tasks", sa.Column("time_of_day", sa.Time(), nullable=True))
    op.add_column("tasks", sa.Column("done_on", sa.Date(), nullable=True))
    op.add_column("reminders", sa.Column("repeat_days", postgresql.JSONB(), nullable=True))

    op.rename_table("workout_plans", "weekly_plans")
    op.execute("ALTER INDEX ix_workout_plans_user_id RENAME TO ix_weekly_plans_user_id")
    op.execute("ALTER TABLE weekly_plans RENAME CONSTRAINT workout_plans_pkey TO weekly_plans_pkey")
    op.execute(
        "ALTER TABLE weekly_plans RENAME CONSTRAINT workout_plans_user_id_fkey "
        "TO weekly_plans_user_id_fkey"
    )
    op.execute(
        """
        UPDATE weekly_plans SET sessions = (
            SELECT coalesce(jsonb_agg(jsonb_build_object(
                'day', s->'day', 'activity', s->'focus', 'minutes', s->'minutes'
            )), '[]'::jsonb)
            FROM jsonb_array_elements(sessions) AS s
        )
        """
    )
    op.alter_column(
        "pending_actions", "kind", type_=_kind(KINDS_AFTER), existing_type=_kind(KINDS_BEFORE)
    )
    op.execute("UPDATE pending_actions SET kind = 'weekly_plan' WHERE kind = 'workout_plan'")
    op.execute(
        """
        UPDATE pending_actions SET payload = jsonb_set(payload, '{sessions}', (
            SELECT coalesce(jsonb_agg(jsonb_build_object(
                'day', s->'day', 'activity', s->'focus', 'minutes', s->'minutes'
            )), '[]'::jsonb)
            FROM jsonb_array_elements(payload->'sessions') AS s
        ))
        WHERE kind = 'weekly_plan' AND payload ? 'sessions'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE weekly_plans SET sessions = (
            SELECT coalesce(jsonb_agg(jsonb_build_object(
                'day', s->'day', 'focus', s->'activity', 'minutes', coalesce(s->'minutes', '30')
            )), '[]'::jsonb)
            FROM jsonb_array_elements(sessions) AS s
        )
        """
    )
    op.execute("UPDATE pending_actions SET status = 'cancelled' WHERE kind = 'weekly_plan'")
    op.execute("UPDATE pending_actions SET kind = 'workout_plan' WHERE kind = 'weekly_plan'")
    op.alter_column(
        "pending_actions", "kind", type_=_kind(KINDS_BEFORE), existing_type=_kind(KINDS_AFTER)
    )
    op.execute(
        "ALTER TABLE weekly_plans RENAME CONSTRAINT weekly_plans_user_id_fkey "
        "TO workout_plans_user_id_fkey"
    )
    op.execute("ALTER TABLE weekly_plans RENAME CONSTRAINT weekly_plans_pkey TO workout_plans_pkey")
    op.execute("ALTER INDEX ix_weekly_plans_user_id RENAME TO ix_workout_plans_user_id")
    op.rename_table("weekly_plans", "workout_plans")
    op.drop_column("reminders", "repeat_days")
    op.drop_column("tasks", "done_on")
    op.drop_column("tasks", "time_of_day")
    op.drop_column("tasks", "repeat_days")
