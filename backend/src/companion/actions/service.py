import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ValidationError
from sqlalchemy import select, update

from companion.actions.describe import describe
from companion.actions.tools import (
    ARGUMENTS,
    TOOL_NAMES,
    CreateReminderArgs,
    CreateTaskArgs,
    CreateWorkoutPlanArgs,
    Weekday,
)
from companion.actions.when import parse_when
from companion.db.models import (
    ActionKind,
    ActionStatus,
    Base,
    PendingAction,
    Reminder,
    Task,
    WorkoutPlan,
)
from companion.db.session import SessionFactory
from companion.llm import ToolCall

PENDING_LIFETIME = timedelta(minutes=10)

UNKNOWN_TOOL = "I can't do that one yet."
UNCLEAR_DETAILS = "I didn't quite catch the details. Can you say that again?"
UNCLEAR_REMINDER_TIME = "When should I remind you? Try something like 'tomorrow at 6 pm'."
UNCLEAR_DUE_DATE = "When is it due? Try something like 'Friday'."
TIME_IN_THE_PAST = "That time has already passed. When should it be?"
CANCELLED = "Okay, I scrapped it."
EXPIRED = "That one timed out, so I didn't save it. Want to try again?"
ALREADY_HANDLED = "That one's already been taken care of."
SAVED = {
    ActionKind.REMINDER: "Saved. I'll remind you.",
    ActionKind.TASK: "Saved to your tasks.",
    ActionKind.WORKOUT_PLAN: "Plan saved. Now you actually have to show up.",
}


@dataclass(frozen=True, slots=True)
class Proposal:
    action_id: uuid.UUID
    kind: ActionKind
    summary: str

    @property
    def question(self) -> str:
        return f"Got it, {self.summary}. Should I save it?"


@dataclass(frozen=True, slots=True)
class Rejection:
    message: str


@dataclass(frozen=True, slots=True)
class Resolution:
    action_id: uuid.UUID
    kind: ActionKind
    status: ActionStatus
    message: str


class ActionNotFoundError(LookupError):
    pass


class ActionGateway(Protocol):
    async def propose(self, call: ToolCall) -> Proposal | Rejection: ...

    async def pending(self) -> uuid.UUID | None: ...

    async def resolve(self, action_id: uuid.UUID, *, confirm: bool) -> Resolution: ...


def utc_now() -> datetime:
    return datetime.now(UTC)


class ActionService:
    def __init__(
        self,
        sessions: SessionFactory,
        *,
        clock: Callable[[], datetime] = utc_now,
        lifetime: timedelta = PENDING_LIFETIME,
    ) -> None:
        self._sessions = sessions
        self._clock = clock
        self._lifetime = lifetime

    async def propose(
        self, user_id: uuid.UUID, timezone: str, call: ToolCall
    ) -> Proposal | Rejection:
        kind = TOOL_NAMES.get(call.name)
        if kind is None:
            return Rejection(UNKNOWN_TOOL)
        try:
            args = ARGUMENTS[kind].model_validate_json(call.arguments)
        except ValidationError:
            return Rejection(UNCLEAR_DETAILS)

        now = self._clock().astimezone(ZoneInfo(timezone))
        payload = _payload(args, now)
        if isinstance(payload, Rejection):
            return payload

        async with self._sessions() as session, session.begin():
            await session.execute(
                update(PendingAction)
                .where(
                    PendingAction.user_id == user_id, PendingAction.status == ActionStatus.PENDING
                )
                .values(status=ActionStatus.CANCELLED, resolved_at=now)
            )
            action = PendingAction(
                id=uuid.uuid4(),
                user_id=user_id,
                kind=kind,
                payload=payload,
                status=ActionStatus.PENDING,
                expires_at=now + self._lifetime,
            )
            session.add(action)
        return Proposal(action_id=action.id, kind=kind, summary=describe(kind, payload, now))

    async def pending(self, user_id: uuid.UUID) -> uuid.UUID | None:
        async with self._sessions() as session:
            action_id: uuid.UUID | None = await session.scalar(
                select(PendingAction.id)
                .where(
                    PendingAction.user_id == user_id,
                    PendingAction.status == ActionStatus.PENDING,
                    PendingAction.expires_at > self._clock(),
                )
                .order_by(PendingAction.created_at.desc())
                .limit(1)
            )
        return action_id

    async def resolve(
        self, user_id: uuid.UUID, action_id: uuid.UUID, *, confirm: bool
    ) -> Resolution:
        now = self._clock()
        async with self._sessions() as session, session.begin():
            action = await session.scalar(
                select(PendingAction)
                .where(PendingAction.id == action_id, PendingAction.user_id == user_id)
                .with_for_update()
            )
            if action is None:
                raise ActionNotFoundError(action_id)
            if action.status is not ActionStatus.PENDING:
                return Resolution(action.id, action.kind, action.status, ALREADY_HANDLED)

            if not confirm:
                action.status, message = ActionStatus.CANCELLED, CANCELLED
            elif action.expires_at <= now:
                action.status, message = ActionStatus.EXPIRED, EXPIRED
            else:
                session.add(_record(action))
                action.status, message = ActionStatus.CONFIRMED, SAVED[action.kind]
            action.resolved_at = now
        return Resolution(action.id, action.kind, action.status, message)


@dataclass(frozen=True, slots=True)
class UserActions:
    service: ActionService
    user_id: uuid.UUID
    timezone: str

    async def propose(self, call: ToolCall) -> Proposal | Rejection:
        return await self.service.propose(self.user_id, self.timezone, call)

    async def pending(self) -> uuid.UUID | None:
        return await self.service.pending(self.user_id)

    async def resolve(self, action_id: uuid.UUID, *, confirm: bool) -> Resolution:
        return await self.service.resolve(self.user_id, action_id, confirm=confirm)


def _future_time(phrase: str, now: datetime, unclear: str) -> datetime | Rejection:
    moment = parse_when(phrase, now)
    if moment is None:
        return Rejection(unclear)
    if moment <= now:
        return Rejection(TIME_IN_THE_PAST)
    return moment


def _payload(args: BaseModel, now: datetime) -> dict[str, Any] | Rejection:
    match args:
        case CreateReminderArgs():
            remind_at = _future_time(args.when, now, UNCLEAR_REMINDER_TIME)
            if isinstance(remind_at, Rejection):
                return remind_at
            return {"title": args.title, "remind_at": remind_at.isoformat()}
        case CreateTaskArgs():
            if args.due is None:
                return {"title": args.title, "due_at": None}
            due_at = _future_time(args.due, now, UNCLEAR_DUE_DATE)
            if isinstance(due_at, Rejection):
                return due_at
            return {"title": args.title, "due_at": due_at.isoformat()}
        case CreateWorkoutPlanArgs():
            week_order = list(Weekday)
            sessions = sorted(args.sessions, key=lambda s: week_order.index(s.day))
            return {"name": args.name, "sessions": [s.model_dump(mode="json") for s in sessions]}
    raise TypeError(f"unsupported arguments: {type(args).__name__}")


def _record(action: PendingAction) -> Base:
    payload = action.payload
    match action.kind:
        case ActionKind.REMINDER:
            return Reminder(
                user_id=action.user_id,
                title=payload["title"],
                remind_at=datetime.fromisoformat(payload["remind_at"]),
            )
        case ActionKind.TASK:
            due_at = payload["due_at"]
            return Task(
                user_id=action.user_id,
                title=payload["title"],
                due_at=datetime.fromisoformat(due_at) if due_at else None,
            )
        case ActionKind.WORKOUT_PLAN:
            return WorkoutPlan(
                user_id=action.user_id, name=payload["name"], sessions=payload["sessions"]
            )
