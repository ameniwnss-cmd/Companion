import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ValidationError
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from companion.actions.describe import describe, spoken_list
from companion.actions.matching import is_done, matching, normalised
from companion.actions.repeat import in_week_order, next_occurrence
from companion.actions.tools import (
    KINDS,
    CompleteTaskArgs,
    CreateReminderArgs,
    CreateTaskArgs,
    CreateWeeklyPlanArgs,
    ItemArgs,
    UnknownToolError,
    Weekday,
    requested_items,
)
from companion.actions.when import parse_when
from companion.db.models import (
    ActionKind,
    ActionStatus,
    PendingAction,
    Reminder,
    Task,
    User,
    WeeklyPlan,
)
from companion.db.session import SessionFactory
from companion.llm import ToolCall

PENDING_LIFETIME = timedelta(minutes=10)
UNDO_WINDOW = timedelta(minutes=10)
MAX_BATCH_ITEMS = 10
MAX_OPEN_TASKS = 30

UNKNOWN_TOOL = "I can't do that one yet."
UNCLEAR_DETAILS = "I didn't quite catch the details. Can you say that again?"
UNCLEAR_REMINDER_TIME = "When should I remind you? Try something like 'tomorrow at 6 pm'."
UNCLEAR_DUE_DATE = "When is it due? Try something like 'Friday'."
UNCLEAR_TIME_OF_DAY = "What time of day should it be? Try something like '9am'."
TIME_IN_THE_PAST = "That time has already passed. When should it be?"
SKIPPED_SOME = "I didn't catch the details of the rest, so tell me those again after."
CANCELLED = "Okay, I scrapped it."
EXPIRED = "That one timed out, so I didn't save it. Want to try again?"
ALREADY_HANDLED = "That one's already been taken care of."
NOTHING_TO_UNDO = "There's nothing recent to undo."
UNDONE = "Done, I took it back."
NO_SUCH_TASK = "I can't find {title} on your quest list."
WHICH_TASK = "{title} could be {options}. Which one did you finish?"
ALREADY_DONE = "{title} is already ticked off."
ALREADY_LISTED = "{titles} {verb} already on your list."
SAVED = {
    ActionKind.REMINDER: "Saved. I'll remind you.",
    ActionKind.TASK: "Saved to your tasks.",
    ActionKind.WEEKLY_PLAN: "Plan saved. Now you actually have to show up.",
    ActionKind.COMPLETE_TASK: "Ticked off. Look at you go.",
}

Record = Task | Reminder | WeeklyPlan
RECORD_TYPES: dict[ActionKind, type[Record]] = {
    ActionKind.TASK: Task,
    ActionKind.REMINDER: Reminder,
    ActionKind.WEEKLY_PLAN: WeeklyPlan,
}


@dataclass(frozen=True, slots=True)
class ProposedItem:
    kind: ActionKind
    summary: str


@dataclass(frozen=True, slots=True)
class Proposal:
    action_id: uuid.UUID
    items: tuple[ProposedItem, ...]
    skipped: int = 0
    notes: tuple[str, ...] = ()

    @property
    def question(self) -> str:
        ticking = [item.kind is ActionKind.COMPLETE_TASK for item in self.items]
        if all(ticking):
            summaries = spoken_list([item.summary for item in self.items])
            question = f"Nice work. Should I tick off {summaries}?"
        elif len(self.items) == 1:
            question = f"Got it, {self.items[0].summary}. Should I save it?"
        else:
            summaries = spoken_list([_spoken(item) for item in self.items])
            ending = "Should I go ahead?" if any(ticking) else "Should I save them?"
            question = f"Got it, {len(self.items)} things: {summaries}. {ending}"
        return " ".join([question, *self.notes, *([SKIPPED_SOME] if self.skipped else [])])


def _spoken(item: ProposedItem) -> str:
    if item.kind is ActionKind.COMPLETE_TASK:
        return f"ticking off {item.summary}"
    return item.summary


@dataclass(frozen=True, slots=True)
class Rejection:
    message: str


@dataclass(frozen=True, slots=True)
class _Unmatched:
    message: str


@dataclass(frozen=True, slots=True)
class Resolution:
    action_id: uuid.UUID
    status: ActionStatus
    message: str


class ActionNotFoundError(LookupError):
    pass


class ActionGateway(Protocol):
    async def propose(self, calls: Sequence[ToolCall]) -> Proposal | Rejection: ...

    async def pending(self) -> uuid.UUID | None: ...

    async def resolve(self, action_id: uuid.UUID, *, confirm: bool) -> Resolution: ...

    async def last_saved(self) -> uuid.UUID | None: ...

    async def undo(self, action_id: uuid.UUID) -> Resolution: ...

    async def open_tasks(self) -> list[str]: ...


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
        self, user_id: uuid.UUID, timezone: str, calls: Sequence[ToolCall]
    ) -> Proposal | Rejection:
        now = self._clock().astimezone(ZoneInfo(timezone))
        requested = [item for call in calls for item in _requested(call)]
        tasks: list[Task] = []
        reminders: list[Reminder] = []
        if any(isinstance(item, CompleteTaskArgs | CreateTaskArgs) for item in requested):
            tasks = await self._tasks(user_id)
        if any(isinstance(item, CreateReminderArgs) for item in requested):
            reminders = await self._waiting_reminders(user_id)
        accepted: list[tuple[ActionKind, dict[str, Any]]] = []
        problems: list[Rejection | _Unmatched] = []
        duplicates: list[str] = []
        for item in requested:
            if isinstance(item, Rejection):
                problems.append(item)
                continue
            payload = _payload(item, now, tasks)
            if isinstance(payload, Rejection | _Unmatched):
                problems.append(payload)
                continue
            kind = KINDS[type(item)]
            if (existing := _already_saved(kind, payload, tasks, reminders)) is not None:
                if existing not in duplicates:
                    duplicates.append(existing)
            elif (kind, payload) not in accepted:
                accepted.append((kind, payload))
        accepted = accepted[:MAX_BATCH_ITEMS]
        if duplicates:
            problems.insert(0, _Unmatched(_already_listed(duplicates)))
        if not accepted:
            return Rejection(problems[0].message) if problems else Rejection(UNCLEAR_DETAILS)

        batch_id = uuid.uuid4()
        async with self._sessions() as session, session.begin():
            await session.execute(
                update(PendingAction)
                .where(
                    PendingAction.user_id == user_id, PendingAction.status == ActionStatus.PENDING
                )
                .values(status=ActionStatus.CANCELLED, resolved_at=now)
            )
            session.add_all(
                PendingAction(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    batch_id=batch_id,
                    kind=kind,
                    payload=payload,
                    status=ActionStatus.PENDING,
                    expires_at=now + self._lifetime,
                )
                for kind, payload in accepted
            )
        items = tuple(
            ProposedItem(kind, describe(kind, payload, now)) for kind, payload in accepted
        )
        return Proposal(
            action_id=batch_id,
            items=items,
            skipped=sum(isinstance(problem, Rejection) for problem in problems),
            notes=tuple(p.message for p in problems if isinstance(p, _Unmatched)),
        )

    async def open_tasks(self, user_id: uuid.UUID, timezone: str) -> list[str]:
        today = self._clock().astimezone(ZoneInfo(timezone)).date()
        tasks = await self._tasks(user_id)
        return [task.title for task in tasks if not is_done(task, today)][:MAX_OPEN_TASKS]

    async def _waiting_reminders(self, user_id: uuid.UUID) -> list[Reminder]:
        async with self._sessions() as session:
            return list(
                await session.scalars(
                    select(Reminder).where(
                        Reminder.user_id == user_id, Reminder.delivered_at.is_(None)
                    )
                )
            )

    async def _tasks(self, user_id: uuid.UUID) -> list[Task]:
        async with self._sessions() as session:
            return list(
                await session.scalars(
                    select(Task).where(Task.user_id == user_id).order_by(Task.created_at, Task.id)
                )
            )

    async def pending(self, user_id: uuid.UUID) -> uuid.UUID | None:
        async with self._sessions() as session:
            batch_id: uuid.UUID | None = await session.scalar(
                select(PendingAction.batch_id)
                .where(
                    PendingAction.user_id == user_id,
                    PendingAction.status == ActionStatus.PENDING,
                    PendingAction.expires_at > self._clock(),
                )
                .order_by(PendingAction.created_at.desc())
                .limit(1)
            )
        return batch_id

    async def resolve(
        self, user_id: uuid.UUID, action_id: uuid.UUID, *, confirm: bool
    ) -> Resolution:
        now = self._clock()
        async with self._sessions() as session, session.begin():
            batch = await _batch(session, user_id, action_id)
            waiting = [action for action in batch if action.status is ActionStatus.PENDING]
            if not waiting:
                return Resolution(action_id, batch[0].status, ALREADY_HANDLED)

            if not confirm:
                status, message = ActionStatus.CANCELLED, CANCELLED
            elif any(action.expires_at <= now for action in waiting):
                status, message = ActionStatus.EXPIRED, EXPIRED
            else:
                status = ActionStatus.CONFIRMED
                message = _saved_message([action.kind for action in waiting])
                today: date | None = None
                for action in waiting:
                    if action.kind is ActionKind.COMPLETE_TASK:
                        today = today or await user_today(session, user_id, now)
                        await _tick_off(session, action, today)
                        continue
                    record = _record(action)
                    session.add(record)
                    action.record_id = record.id
            for action in waiting:
                action.status, action.resolved_at = status, now
        return Resolution(action_id, status, message)

    async def last_saved(self, user_id: uuid.UUID) -> uuid.UUID | None:
        async with self._sessions() as session:
            batch_id: uuid.UUID | None = await session.scalar(
                select(PendingAction.batch_id)
                .where(
                    PendingAction.user_id == user_id,
                    PendingAction.status == ActionStatus.CONFIRMED,
                    PendingAction.resolved_at > self._clock() - UNDO_WINDOW,
                )
                .order_by(PendingAction.resolved_at.desc())
                .limit(1)
            )
        return batch_id

    async def undo(self, user_id: uuid.UUID, action_id: uuid.UUID) -> Resolution:
        now = self._clock()
        async with self._sessions() as session, session.begin():
            batch = await _batch(session, user_id, action_id)
            saved = [
                action
                for action in batch
                if action.status is ActionStatus.CONFIRMED
                and action.resolved_at is not None
                and action.resolved_at > now - UNDO_WINDOW
            ]
            if not saved:
                return Resolution(action_id, batch[0].status, NOTHING_TO_UNDO)
            for action in saved:
                if action.kind is ActionKind.COMPLETE_TASK:
                    await _untick(session, action)
                else:
                    record_type = RECORD_TYPES[action.kind]
                    await session.execute(
                        delete(record_type).where(
                            record_type.id == action.record_id, record_type.user_id == user_id
                        )
                    )
                action.status, action.resolved_at = ActionStatus.UNDONE, now
        return Resolution(action_id, ActionStatus.UNDONE, UNDONE)


@dataclass(frozen=True, slots=True)
class UserActions:
    service: ActionService
    user_id: uuid.UUID
    timezone: str

    async def propose(self, calls: Sequence[ToolCall]) -> Proposal | Rejection:
        return await self.service.propose(self.user_id, self.timezone, calls)

    async def pending(self) -> uuid.UUID | None:
        return await self.service.pending(self.user_id)

    async def resolve(self, action_id: uuid.UUID, *, confirm: bool) -> Resolution:
        return await self.service.resolve(self.user_id, action_id, confirm=confirm)

    async def last_saved(self) -> uuid.UUID | None:
        return await self.service.last_saved(self.user_id)

    async def undo(self, action_id: uuid.UUID) -> Resolution:
        return await self.service.undo(self.user_id, action_id)

    async def open_tasks(self) -> list[str]:
        return await self.service.open_tasks(self.user_id, self.timezone)


async def user_today(session: AsyncSession, user_id: uuid.UUID, now: datetime) -> date:
    timezone = await session.scalar(select(User.timezone).where(User.id == user_id))
    return now.astimezone(ZoneInfo(timezone or "UTC")).date()


def _saved_message(kinds: list[ActionKind]) -> str:
    if len(kinds) == 1:
        return SAVED[kinds[0]]
    if all(kind is ActionKind.COMPLETE_TASK for kind in kinds):
        return f"Ticked off all {len(kinds)}."
    return f"Saved all {len(kinds)}."


async def _owned_task(
    session: AsyncSession, user_id: uuid.UUID, task_id: uuid.UUID | None
) -> Task | None:
    if task_id is None:
        return None
    return await session.scalar(
        select(Task).where(Task.id == task_id, Task.user_id == user_id).with_for_update()
    )


async def _tick_off(session: AsyncSession, action: PendingAction, today: date) -> None:
    task = await _owned_task(session, action.user_id, uuid.UUID(action.payload["task_id"]))
    if task is None:
        return
    previous_done_on = task.done_on.isoformat() if task.done_on else None
    action.payload = {
        **action.payload,
        "previous": {"done": task.done, "done_on": previous_done_on},
    }
    if task.repeat_days:
        task.done_on = today
    else:
        task.done = True
    action.record_id = task.id


async def _untick(session: AsyncSession, action: PendingAction) -> None:
    previous = action.payload.get("previous")
    task = await _owned_task(session, action.user_id, action.record_id)
    if task is None or previous is None:
        return
    task.done = previous["done"]
    task.done_on = date.fromisoformat(previous["done_on"]) if previous["done_on"] else None


async def _batch(
    session: AsyncSession, user_id: uuid.UUID, batch_id: uuid.UUID
) -> list[PendingAction]:
    batch = list(
        await session.scalars(
            select(PendingAction)
            .where(PendingAction.batch_id == batch_id, PendingAction.user_id == user_id)
            .order_by(PendingAction.created_at, PendingAction.id)
            .with_for_update()
        )
    )
    if not batch:
        raise ActionNotFoundError(batch_id)
    return batch


def _requested(call: ToolCall) -> list[ItemArgs | Rejection]:
    try:
        requested: list[ItemArgs | Rejection] = [*requested_items(call)]
    except UnknownToolError:
        return [Rejection(UNKNOWN_TOOL)]
    except ValidationError:
        return [Rejection(UNCLEAR_DETAILS)]
    return requested or [Rejection(UNCLEAR_DETAILS)]


def _already_saved(
    kind: ActionKind, payload: dict[str, Any], tasks: list[Task], reminders: list[Reminder]
) -> str | None:
    title = normalised(payload.get("title", ""))
    saved: list[Task] | list[Reminder] = []
    if kind is ActionKind.TASK:
        saved = [
            task
            for task in tasks
            if normalised(task.title) == title and (task.repeat_days or not task.done)
        ]
    elif kind is ActionKind.REMINDER:
        remind_at = datetime.fromisoformat(payload["remind_at"])
        saved = [
            reminder
            for reminder in reminders
            if normalised(reminder.title) == title and reminder.remind_at == remind_at
        ]
    return saved[0].title if saved else None


def _already_listed(titles: list[str]) -> str:
    verb = "is" if len(titles) == 1 else "are"
    return ALREADY_LISTED.format(titles=spoken_list(titles), verb=verb)


def _completion(title: str, tasks: list[Task], today: date) -> dict[str, Any] | _Unmatched:
    found = matching(title, [task for task in tasks if not is_done(task, today)])
    if len(found) == 1:
        [task] = found
        return {"task_id": str(task.id), "title": task.title, "repeating": bool(task.repeat_days)}
    if found:
        options = spoken_list([task.title for task in found[:3]], last="or")
        return _Unmatched(WHICH_TASK.format(title=title, options=options))
    finished = matching(title, [task for task in tasks if is_done(task, today)])
    if finished:
        return _Unmatched(ALREADY_DONE.format(title=finished[0].title))
    return _Unmatched(NO_SUCH_TASK.format(title=title))


def _future_time(phrase: str, now: datetime, unclear: str) -> datetime | Rejection:
    moment = parse_when(phrase, now)
    if moment is None:
        return Rejection(unclear)
    if moment <= now:
        return Rejection(TIME_IN_THE_PAST)
    return moment


def _time_of_day(phrase: str, now: datetime) -> time | Rejection:
    moment = parse_when(phrase, now)
    return Rejection(UNCLEAR_TIME_OF_DAY) if moment is None else moment.time()


def _days(repeat: list[Weekday]) -> list[str]:
    return [day.value for day in in_week_order(repeat)]


def _payload(
    args: BaseModel, now: datetime, tasks: list[Task]
) -> dict[str, Any] | Rejection | _Unmatched:
    match args:
        case CreateReminderArgs(repeat=list() as repeat):
            at = _time_of_day(args.when, now)
            if isinstance(at, Rejection):
                return at
            first = next_occurrence(repeat, at, now)
            return {
                "title": args.title,
                "remind_at": first.isoformat(),
                "repeat_days": _days(repeat),
            }
        case CreateReminderArgs():
            remind_at = _future_time(args.when, now, UNCLEAR_REMINDER_TIME)
            if isinstance(remind_at, Rejection):
                return remind_at
            return {"title": args.title, "remind_at": remind_at.isoformat()}
        case CreateTaskArgs(repeat=list() as repeat):
            payload: dict[str, Any] = {
                "title": args.title,
                "due_at": None,
                "repeat_days": _days(repeat),
                "time_of_day": None,
            }
            if args.at is not None:
                at = _time_of_day(args.at, now)
                if isinstance(at, Rejection):
                    return at
                payload["time_of_day"] = at.isoformat(timespec="minutes")
            return payload
        case CreateTaskArgs():
            if args.due is None:
                return {"title": args.title, "due_at": None}
            due_at = _future_time(args.due, now, UNCLEAR_DUE_DATE)
            if isinstance(due_at, Rejection):
                return due_at
            return {"title": args.title, "due_at": due_at.isoformat()}
        case CreateWeeklyPlanArgs():
            week_order = list(Weekday)
            days = sorted(args.days, key=lambda d: week_order.index(d.day))
            return {"name": args.name, "sessions": [d.model_dump(mode="json") for d in days]}
        case CompleteTaskArgs():
            return _completion(args.title, tasks, now.date())
    raise TypeError(f"unsupported arguments: {type(args).__name__}")


def _record(action: PendingAction) -> Record:
    payload = action.payload
    match action.kind:
        case ActionKind.REMINDER:
            return Reminder(
                id=uuid.uuid4(),
                user_id=action.user_id,
                title=payload["title"],
                remind_at=datetime.fromisoformat(payload["remind_at"]),
                repeat_days=payload.get("repeat_days"),
            )
        case ActionKind.TASK:
            due_at = payload["due_at"]
            at = payload.get("time_of_day")
            return Task(
                id=uuid.uuid4(),
                user_id=action.user_id,
                title=payload["title"],
                due_at=datetime.fromisoformat(due_at) if due_at else None,
                repeat_days=payload.get("repeat_days"),
                time_of_day=time.fromisoformat(at) if at else None,
            )
        case ActionKind.WEEKLY_PLAN:
            return WeeklyPlan(
                id=uuid.uuid4(),
                user_id=action.user_id,
                name=payload["name"],
                sessions=payload["sessions"],
            )
        case ActionKind.COMPLETE_TASK:
            raise ValueError("ticking off a task changes an existing record")
