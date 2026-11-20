import uuid
from datetime import datetime, time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from companion.api.dev_user import DevUserId
from companion.db.models import Reminder, Task, WeeklyPlan
from companion.plans.service import ItemNotFoundError, Owned, PlansService

router = APIRouter(prefix="/dev", tags=["dev"])


class TaskOut(BaseModel):
    id: uuid.UUID
    title: str
    due_at: datetime | None
    repeat_days: list[str] | None
    time_of_day: time | None
    done: bool
    created_at: datetime


class TaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    done: bool


class ReminderOut(BaseModel):
    id: uuid.UUID
    title: str
    remind_at: datetime
    repeat_days: list[str] | None
    delivered: bool


class WeeklyPlanOut(BaseModel):
    id: uuid.UUID
    name: str
    sessions: list[dict[str, Any]]
    created_at: datetime


def _plans(request: Request) -> PlansService:
    service: PlansService = request.app.state.plans
    return service


Plans = Annotated[PlansService, Depends(_plans)]


async def _remove(
    plans: PlansService, model: Owned, user_id: uuid.UUID, item_id: uuid.UUID
) -> None:
    try:
        await plans.remove(model, user_id, item_id)
    except ItemNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found") from exc


@router.get("/tasks")
async def list_tasks(plans: Plans, user_id: DevUserId) -> list[TaskOut]:
    return [TaskOut.model_validate(t, from_attributes=True) for t in await plans.tasks(user_id)]


@router.patch("/tasks/{task_id}")
async def update_task(
    task_id: uuid.UUID, changes: TaskUpdate, plans: Plans, user_id: DevUserId
) -> TaskOut:
    try:
        task = await plans.set_task_done(user_id, task_id, changes.done)
    except ItemNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found") from exc
    return TaskOut.model_validate(task, from_attributes=True)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: uuid.UUID, plans: Plans, user_id: DevUserId) -> None:
    await _remove(plans, Task, user_id, task_id)


@router.get("/reminders")
async def list_reminders(plans: Plans, user_id: DevUserId) -> list[ReminderOut]:
    return [
        ReminderOut.model_validate(r, from_attributes=True) for r in await plans.reminders(user_id)
    ]


@router.delete("/reminders/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reminder(reminder_id: uuid.UUID, plans: Plans, user_id: DevUserId) -> None:
    await _remove(plans, Reminder, user_id, reminder_id)


@router.get("/weekly-plans")
async def list_weekly_plans(plans: Plans, user_id: DevUserId) -> list[WeeklyPlanOut]:
    return [
        WeeklyPlanOut.model_validate(p, from_attributes=True)
        for p in await plans.weekly_plans(user_id)
    ]


@router.delete("/weekly-plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_weekly_plan(plan_id: uuid.UUID, plans: Plans, user_id: DevUserId) -> None:
    await _remove(plans, WeeklyPlan, user_id, plan_id)
