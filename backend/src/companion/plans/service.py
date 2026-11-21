import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from companion.actions.matching import is_done
from companion.actions.service import user_today, utc_now
from companion.db.models import Reminder, Task, WeeklyPlan
from companion.db.session import SessionFactory


@dataclass(frozen=True, slots=True)
class TaskView:
    id: uuid.UUID
    title: str
    due_at: datetime | None
    repeat_days: list[str] | None
    time_of_day: time | None
    done: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ReminderView:
    id: uuid.UUID
    title: str
    remind_at: datetime
    repeat_days: list[str] | None
    delivered: bool


@dataclass(frozen=True, slots=True)
class WeeklyPlanView:
    id: uuid.UUID
    name: str
    sessions: list[dict[str, Any]]
    created_at: datetime


class ItemNotFoundError(LookupError):
    pass


Owned = type[Task] | type[Reminder] | type[WeeklyPlan]


def _view(task: Task, today: date) -> TaskView:
    return TaskView(
        task.id,
        task.title,
        task.due_at,
        task.repeat_days,
        task.time_of_day,
        is_done(task, today),
        task.created_at,
    )


class PlansService:
    def __init__(
        self, sessions: SessionFactory, *, clock: Callable[[], datetime] = utc_now
    ) -> None:
        self._sessions = sessions
        self._clock = clock

    async def _today(self, session: AsyncSession, user_id: uuid.UUID) -> date:
        return await user_today(session, user_id, self._clock())

    async def tasks(self, user_id: uuid.UUID) -> list[TaskView]:
        async with self._sessions() as session:
            today = await self._today(session, user_id)
            rows = await session.scalars(
                select(Task)
                .where(Task.user_id == user_id)
                .order_by(Task.done, Task.due_at.asc().nulls_last(), Task.created_at.desc())
            )
            return [_view(task, today) for task in rows]

    async def set_task_done(self, user_id: uuid.UUID, task_id: uuid.UUID, done: bool) -> TaskView:
        async with self._sessions() as session, session.begin():
            task = await session.scalar(
                select(Task).where(Task.id == task_id, Task.user_id == user_id)
            )
            if task is None:
                raise ItemNotFoundError(task_id)
            today = await self._today(session, user_id)
            if task.repeat_days:
                task.done_on = today if done else None
            else:
                task.done = done
            return _view(task, today)

    async def reminders(self, user_id: uuid.UUID) -> list[ReminderView]:
        async with self._sessions() as session:
            rows = await session.scalars(
                select(Reminder)
                .where(Reminder.user_id == user_id)
                .order_by(Reminder.delivered_at.is_not(None), Reminder.remind_at)
            )
            return [
                ReminderView(r.id, r.title, r.remind_at, r.repeat_days, r.delivered_at is not None)
                for r in rows
            ]

    async def weekly_plans(self, user_id: uuid.UUID) -> list[WeeklyPlanView]:
        async with self._sessions() as session:
            rows = await session.scalars(
                select(WeeklyPlan)
                .where(WeeklyPlan.user_id == user_id)
                .order_by(WeeklyPlan.created_at.desc())
            )
            return [WeeklyPlanView(p.id, p.name, p.sessions, p.created_at) for p in rows]

    async def remove(self, model: Owned, user_id: uuid.UUID, item_id: uuid.UUID) -> None:
        async with self._sessions() as session, session.begin():
            deleted = await session.scalar(
                delete(model)
                .where(model.id == item_id, model.user_id == user_id)
                .returning(model.id)
            )
            if deleted is None:
                raise ItemNotFoundError(item_id)
