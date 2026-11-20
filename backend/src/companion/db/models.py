import uuid
from datetime import date, datetime, time
from enum import StrEnum
from typing import Annotated, Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, String, Time, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from companion.embeddings import EMBEDDING_DIMENSIONS

UuidPk = Annotated[uuid.UUID, mapped_column(primary_key=True, default=uuid.uuid4)]
OwnerId = Annotated[
    uuid.UUID, mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
]
Timestamp = Annotated[datetime, mapped_column(DateTime(timezone=True))]
CreatedAt = Annotated[datetime, mapped_column(DateTime(timezone=True), server_default=func.now())]
UpdatedAt = Annotated[
    datetime,
    mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now()),
]
Title = Annotated[str, mapped_column(String(200))]
Json = Annotated[Any, mapped_column(JSONB)]


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[UuidPk]
    email: Mapped[str] = mapped_column(String(320), unique=True)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    created_at: Mapped[CreatedAt]


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[UuidPk]
    user_id: Mapped[OwnerId]
    title: Mapped[Title]
    due_at: Mapped[Timestamp | None]
    repeat_days: Mapped[list[str] | None] = mapped_column(JSONB)
    time_of_day: Mapped[time | None] = mapped_column(Time)
    done: Mapped[bool] = mapped_column(default=False)
    done_on: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[CreatedAt]


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[UuidPk]
    user_id: Mapped[OwnerId]
    title: Mapped[Title]
    remind_at: Mapped[Timestamp] = mapped_column(index=True)
    repeat_days: Mapped[list[str] | None] = mapped_column(JSONB)
    delivered_at: Mapped[Timestamp | None]
    created_at: Mapped[CreatedAt]


class WeeklyPlan(Base):
    __tablename__ = "weekly_plans"

    id: Mapped[UuidPk]
    user_id: Mapped[OwnerId]
    name: Mapped[Title]
    sessions: Mapped[Json]
    created_at: Mapped[CreatedAt]


class ActionKind(StrEnum):
    TASK = "task"
    REMINDER = "reminder"
    WEEKLY_PLAN = "weekly_plan"


class ActionStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    UNDONE = "undone"


def _string_enum(enum: type[StrEnum]) -> Enum:
    return Enum(enum, native_enum=False, length=20, values_callable=lambda e: [m.value for m in e])


class PendingAction(Base):
    __tablename__ = "pending_actions"

    id: Mapped[UuidPk]
    user_id: Mapped[OwnerId]
    batch_id: Mapped[uuid.UUID] = mapped_column(index=True)
    kind: Mapped[ActionKind] = mapped_column(_string_enum(ActionKind))
    payload: Mapped[Json]
    record_id: Mapped[uuid.UUID | None]
    status: Mapped[ActionStatus] = mapped_column(
        _string_enum(ActionStatus), default=ActionStatus.PENDING
    )
    expires_at: Mapped[Timestamp]
    resolved_at: Mapped[Timestamp | None]
    created_at: Mapped[CreatedAt]


class MemoryKind(StrEnum):
    PREFERENCE = "preference"
    GOAL = "goal"
    COMMITMENT = "commitment"
    HABIT = "habit"
    RECENT_CONTEXT = "recent_context"


class Memory(Base):
    __tablename__ = "memories"
    __table_args__ = (
        Index(
            "ix_memories_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[UuidPk]
    user_id: Mapped[OwnerId]
    kind: Mapped[MemoryKind] = mapped_column(_string_enum(MemoryKind))
    content: Mapped[str] = mapped_column(String(300))
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    expires_at: Mapped[Timestamp | None]
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]
