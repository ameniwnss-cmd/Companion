import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select

from companion.db.models import Reminder, Task, WorkoutPlan
from companion.db.session import SessionFactory


@dataclass(frozen=True, slots=True)
class TaskView:
    id: uuid.UUID
    title: str
    due_at: datetime | None
    done: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ReminderView:
    id: uuid.UUID
    title: str
    remind_at: datetime
    delivered: bool


@dataclass(frozen=True, slots=True)
class WorkoutPlanView:
    id: uuid.UUID
    name: str
    sessions: list[dict[str, Any]]
    created_at: datetime


class ItemNotFoundError(LookupError):
    pass


Owned = type[Task] | type[Reminder] | type[WorkoutPlan]


class PlansService:
    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    async def tasks(self, user_id: uuid.UUID) -> list[TaskView]:
        async with self._sessions() as session:
            rows = await session.scalars(
                select(Task)
                .where(Task.user_id == user_id)
                .order_by(Task.done, Task.due_at.asc().nulls_last(), Task.created_at.desc())
            )
            return [TaskView(t.id, t.title, t.due_at, t.done, t.created_at) for t in rows]

    async def set_task_done(self, user_id: uuid.UUID, task_id: uuid.UUID, done: bool) -> TaskView:
        async with self._sessions() as session, session.begin():
            task = await session.scalar(
                select(Task).where(Task.id == task_id, Task.user_id == user_id)
            )
            if task is None:
                raise ItemNotFoundError(task_id)
            task.done = done
            return TaskView(task.id, task.title, task.due_at, task.done, task.created_at)

    async def reminders(self, user_id: uuid.UUID) -> list[ReminderView]:
        async with self._sessions() as session:
            rows = await session.scalars(
                select(Reminder)
                .where(Reminder.user_id == user_id)
                .order_by(Reminder.delivered_at.is_not(None), Reminder.remind_at)
            )
            return [
                ReminderView(r.id, r.title, r.remind_at, r.delivered_at is not None) for r in rows
            ]

    async def workout_plans(self, user_id: uuid.UUID) -> list[WorkoutPlanView]:
        async with self._sessions() as session:
            rows = await session.scalars(
                select(WorkoutPlan)
                .where(WorkoutPlan.user_id == user_id)
                .order_by(WorkoutPlan.created_at.desc())
            )
            return [WorkoutPlanView(p.id, p.name, p.sessions, p.created_at) for p in rows]

    async def remove(self, model: Owned, user_id: uuid.UUID, item_id: uuid.UUID) -> None:
        async with self._sessions() as session, session.begin():
            deleted = await session.scalar(
                delete(model)
                .where(model.id == item_id, model.user_id == user_id)
                .returning(model.id)
            )
            if deleted is None:
                raise ItemNotFoundError(item_id)
