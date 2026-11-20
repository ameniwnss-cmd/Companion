import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from companion.actions.service import (
    ALREADY_HANDLED,
    CANCELLED,
    EXPIRED,
    SAVED,
    TIME_IN_THE_PAST,
    UNCLEAR_DETAILS,
    UNCLEAR_REMINDER_TIME,
    UNKNOWN_TOOL,
    ActionNotFoundError,
    ActionService,
    Proposal,
    Rejection,
)
from companion.db.models import (
    ActionKind,
    ActionStatus,
    PendingAction,
    Reminder,
    Task,
    User,
    WorkoutPlan,
)
from companion.db.session import SessionFactory
from companion.llm import ToolCall
from companion.users import get_or_create_user

PARIS = "Europe/Paris"


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2037, 11, 18, 13, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def service(sessions: SessionFactory, clock: Clock) -> ActionService:
    return ActionService(sessions, clock=clock)


def call(tool: str, /, **arguments: Any) -> ToolCall:
    return ToolCall(name=tool, arguments=json.dumps(arguments))


REMINDER = call("create_reminder", title="call mom", when="tomorrow at 6pm")


async def proposal(service: ActionService, user: User, tool_call: ToolCall = REMINDER) -> Proposal:
    outcome = await service.propose(user.id, PARIS, tool_call)
    assert isinstance(outcome, Proposal)
    return outcome


async def test_a_proposal_is_stored_as_pending_with_a_spoken_summary(
    service: ActionService, user: User, sessions: SessionFactory
) -> None:
    outcome = await proposal(service, user)

    assert outcome.kind is ActionKind.REMINDER
    assert outcome.summary == "a reminder to call mom, tomorrow at 6 PM"
    assert outcome.question == "Got it, a reminder to call mom, tomorrow at 6 PM. Should I save it?"
    assert await service.pending(user.id) == outcome.action_id
    async with sessions() as session:
        action = await session.get_one(PendingAction, outcome.action_id)
    assert action.payload == {"title": "call mom", "remind_at": "2037-11-19T18:00:00+01:00"}
    assert action.status is ActionStatus.PENDING


@pytest.mark.parametrize(
    ("tool_call", "message"),
    [
        (call("delete_everything"), UNKNOWN_TOOL),
        (ToolCall("create_reminder", "not json"), UNCLEAR_DETAILS),
        (call("create_reminder", title="x"), UNCLEAR_DETAILS),
        (call("create_reminder", title="x", when="whenever"), UNCLEAR_REMINDER_TIME),
        (call("create_reminder", title="x", when="today at 9am"), TIME_IN_THE_PAST),
    ],
)
async def test_bad_proposals_are_rejected_without_storing_anything(
    service: ActionService, user: User, tool_call: ToolCall, message: str
) -> None:
    outcome = await service.propose(user.id, PARIS, tool_call)

    assert outcome == Rejection(message)
    assert await service.pending(user.id) is None


async def test_a_new_proposal_replaces_the_pending_one(
    service: ActionService, user: User, sessions: SessionFactory
) -> None:
    first = await proposal(service, user)
    second = await proposal(service, user, call("create_task", title="buy milk"))

    assert await service.pending(user.id) == second.action_id
    async with sessions() as session:
        assert (await session.get_one(PendingAction, first.action_id)).status is (
            ActionStatus.CANCELLED
        )


async def test_confirming_a_reminder_saves_it(
    service: ActionService, user: User, sessions: SessionFactory
) -> None:
    pending = await proposal(service, user)

    resolution = await service.resolve(user.id, pending.action_id, confirm=True)

    assert resolution.status is ActionStatus.CONFIRMED
    assert resolution.message == SAVED[ActionKind.REMINDER]
    assert await service.pending(user.id) is None
    async with sessions() as session:
        reminder = await session.scalar(select(Reminder))
    assert reminder is not None
    assert reminder.user_id == user.id
    assert reminder.title == "call mom"
    assert reminder.remind_at == datetime(2037, 11, 19, 17, 0, tzinfo=UTC)


async def test_confirming_tasks_with_and_without_due_dates(
    service: ActionService, user: User, sessions: SessionFactory
) -> None:
    for tool_call in [
        call("create_task", title="buy milk"),
        call("create_task", title="essay", due="friday"),
    ]:
        pending = await proposal(service, user, tool_call)
        await service.resolve(user.id, pending.action_id, confirm=True)

    async with sessions() as session:
        tasks = {t.title: t for t in await session.scalars(select(Task))}
    assert tasks["buy milk"].due_at is None
    assert tasks["essay"].due_at == datetime(2037, 11, 20, 8, 0, tzinfo=UTC)
    assert not tasks["essay"].done


async def test_confirming_a_workout_plan_stores_sessions_in_week_order(
    service: ActionService, user: User, sessions: SessionFactory
) -> None:
    plan = call(
        "create_workout_plan",
        name="Get strong",
        sessions=[
            {"day": "friday", "focus": "legs", "minutes": 40},
            {"day": "monday", "focus": "upper body", "minutes": 45},
        ],
    )
    pending = await proposal(service, user, plan)

    await service.resolve(user.id, pending.action_id, confirm=True)

    async with sessions() as session:
        saved = await session.scalar(select(WorkoutPlan))
    assert saved is not None
    assert [s["day"] for s in saved.sessions] == ["monday", "friday"]


async def test_cancelling_saves_nothing(
    service: ActionService, user: User, sessions: SessionFactory
) -> None:
    pending = await proposal(service, user)

    resolution = await service.resolve(user.id, pending.action_id, confirm=False)

    assert resolution.status is ActionStatus.CANCELLED
    assert resolution.message == CANCELLED
    async with sessions() as session:
        assert await session.scalar(select(Reminder)) is None


async def test_an_old_proposal_expires_instead_of_saving(
    service: ActionService, user: User, sessions: SessionFactory, clock: Clock
) -> None:
    pending = await proposal(service, user)
    clock.now += timedelta(minutes=11)

    assert await service.pending(user.id) is None
    resolution = await service.resolve(user.id, pending.action_id, confirm=True)

    assert resolution.status is ActionStatus.EXPIRED
    assert resolution.message == EXPIRED
    async with sessions() as session:
        assert await session.scalar(select(Reminder)) is None


async def test_an_action_is_resolved_only_once(service: ActionService, user: User) -> None:
    pending = await proposal(service, user)
    await service.resolve(user.id, pending.action_id, confirm=True)

    again = await service.resolve(user.id, pending.action_id, confirm=False)

    assert again.status is ActionStatus.CONFIRMED
    assert again.message == ALREADY_HANDLED


async def test_users_can_never_see_or_resolve_each_others_actions(
    service: ActionService, user: User, sessions: SessionFactory
) -> None:
    other = await get_or_create_user(sessions, "mallory@example.com", PARIS)
    pending = await proposal(service, user)

    assert await service.pending(other.id) is None
    with pytest.raises(ActionNotFoundError):
        await service.resolve(other.id, pending.action_id, confirm=True)
    assert await service.pending(user.id) == pending.action_id


async def test_times_are_read_in_the_users_timezone(service: ActionService, user: User) -> None:
    outcome = await service.propose(user.id, "America/New_York", REMINDER)

    assert isinstance(outcome, Proposal)
    assert outcome.summary == "a reminder to call mom, tomorrow at 6 PM"
