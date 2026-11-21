import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from companion.actions.service import (
    ALREADY_HANDLED,
    CANCELLED,
    EXPIRED,
    MAX_BATCH_ITEMS,
    NOTHING_TO_UNDO,
    SAVED,
    SKIPPED_SOME,
    TIME_IN_THE_PAST,
    UNCLEAR_DETAILS,
    UNCLEAR_REMINDER_TIME,
    UNCLEAR_TIME_OF_DAY,
    UNDONE,
    UNKNOWN_TOOL,
    ActionNotFoundError,
    ActionService,
    Proposal,
    ProposedItem,
    Rejection,
)
from companion.actions.tools import TASKS_AND_REMINDERS
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


def task(**fields: Any) -> ToolCall:
    return call(TASKS_AND_REMINDERS, tasks=[fields])


def reminder(**fields: Any) -> ToolCall:
    return call(TASKS_AND_REMINDERS, reminders=[fields])


REMINDER = reminder(title="call mom", when="tomorrow at 6pm")


async def proposal(service: ActionService, user: User, *tool_calls: ToolCall) -> Proposal:
    outcome = await service.propose(user.id, PARIS, tool_calls or [REMINDER])
    assert isinstance(outcome, Proposal)
    return outcome


async def batch(sessions: SessionFactory, batch_id: uuid.UUID) -> list[PendingAction]:
    async with sessions() as session:
        return list(
            await session.scalars(
                select(PendingAction)
                .where(PendingAction.batch_id == batch_id)
                .order_by(PendingAction.created_at)
            )
        )


async def test_a_proposal_is_stored_as_pending_with_a_spoken_summary(
    service: ActionService, user: User, sessions: SessionFactory
) -> None:
    outcome = await proposal(service, user)

    assert outcome.items == (
        ProposedItem(ActionKind.REMINDER, "a reminder to call mom, tomorrow at 6 PM"),
    )
    assert outcome.question == "Got it, a reminder to call mom, tomorrow at 6 PM. Should I save it?"
    assert await service.pending(user.id) == outcome.action_id
    [action] = await batch(sessions, outcome.action_id)
    assert action.payload == {"title": "call mom", "remind_at": "2037-11-19T18:00:00+01:00"}
    assert action.status is ActionStatus.PENDING


@pytest.mark.parametrize(
    ("tool_call", "message"),
    [
        (call("delete_everything"), UNKNOWN_TOOL),
        (call(TASKS_AND_REMINDERS), UNCLEAR_DETAILS),
        (ToolCall(TASKS_AND_REMINDERS, "not json"), UNCLEAR_DETAILS),
        (reminder(title="x"), UNCLEAR_DETAILS),
        (reminder(title="x", when="whenever"), UNCLEAR_REMINDER_TIME),
        (reminder(title="x", when="today at 9am"), TIME_IN_THE_PAST),
    ],
)
async def test_bad_proposals_are_rejected_without_storing_anything(
    service: ActionService, user: User, tool_call: ToolCall, message: str
) -> None:
    outcome = await service.propose(user.id, PARIS, [tool_call])

    assert outcome == Rejection(message)
    assert await service.pending(user.id) is None


async def test_a_new_proposal_replaces_the_pending_one(
    service: ActionService, user: User, sessions: SessionFactory
) -> None:
    first = await proposal(service, user)
    second = await proposal(service, user, task(title="buy milk"))

    assert await service.pending(user.id) == second.action_id
    [replaced] = await batch(sessions, first.action_id)
    assert replaced.status is ActionStatus.CANCELLED


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
        task(title="buy milk"),
        task(title="essay", due="friday"),
    ]:
        pending = await proposal(service, user, tool_call)
        await service.resolve(user.id, pending.action_id, confirm=True)

    async with sessions() as session:
        tasks = {t.title: t for t in await session.scalars(select(Task))}
    assert tasks["buy milk"].due_at is None
    assert tasks["essay"].due_at == datetime(2037, 11, 20, 8, 0, tzinfo=UTC)
    assert not tasks["essay"].done


async def test_confirming_a_weekly_plan_stores_days_in_week_order(
    service: ActionService, user: User, sessions: SessionFactory
) -> None:
    plan = call(
        "create_weekly_plan",
        name="Get strong",
        days=[
            {"day": "friday", "activity": "legs", "minutes": 40},
            {"day": "monday", "activity": "polish the portfolio"},
        ],
    )
    pending = await proposal(service, user, plan)

    await service.resolve(user.id, pending.action_id, confirm=True)

    async with sessions() as session:
        saved = await session.scalar(select(WeeklyPlan))
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
    outcome = await service.propose(user.id, "America/New_York", [REMINDER])

    assert isinstance(outcome, Proposal)
    assert outcome.items[0].summary == "a reminder to call mom, tomorrow at 6 PM"


async def test_several_items_are_proposed_and_confirmed_together(
    service: ActionService, user: User, sessions: SessionFactory
) -> None:
    pending = await proposal(
        service,
        user,
        task(title="buy milk"),
        task(title="essay", due="friday"),
        REMINDER,
    )

    assert [item.summary for item in pending.items] == [
        "a task: buy milk",
        "a task: essay, due on Friday at 9 AM",
        "a reminder to call mom, tomorrow at 6 PM",
    ]
    assert pending.question == (
        "Got it, 3 things: a task: buy milk, a task: essay, due on Friday at 9 AM and "
        "a reminder to call mom, tomorrow at 6 PM. Should I save them?"
    )

    resolution = await service.resolve(user.id, pending.action_id, confirm=True)

    assert resolution.status is ActionStatus.CONFIRMED
    assert resolution.message == "Saved all 3."
    async with sessions() as session:
        assert {t.title for t in await session.scalars(select(Task))} == {"buy milk", "essay"}
        assert await session.scalar(select(Reminder.title)) == "call mom"
    saved = await batch(sessions, pending.action_id)
    assert all(a.status is ActionStatus.CONFIRMED for a in saved)


async def test_one_call_can_hold_several_tasks_and_reminders(
    service: ActionService, user: User
) -> None:
    both = call(
        TASKS_AND_REMINDERS,
        tasks=[{"title": "buy milk"}, {"title": "call the bank"}],
        reminders=[{"title": "drink water", "when": "tomorrow at 9pm"}],
    )

    pending = await proposal(service, user, both)

    assert [(item.kind, item.summary) for item in pending.items] == [
        (ActionKind.TASK, "a task: buy milk"),
        (ActionKind.TASK, "a task: call the bank"),
        (ActionKind.REMINDER, "a reminder to drink water, tomorrow at 9 PM"),
    ]


async def test_items_with_bad_details_are_skipped_and_mentioned(
    service: ActionService, user: User, sessions: SessionFactory
) -> None:
    pending = await proposal(
        service,
        user,
        task(title="buy milk"),
        reminder(title="x", when="whenever"),
    )

    assert len(pending.items) == 1
    assert pending.skipped == 1
    assert pending.question.endswith(SKIPPED_SOME)
    assert len(await batch(sessions, pending.action_id)) == 1


async def test_a_repeated_tool_call_is_proposed_once(
    service: ActionService, user: User, sessions: SessionFactory
) -> None:
    pending = await proposal(service, user, REMINDER, REMINDER)

    assert len(pending.items) == 1
    assert len(await batch(sessions, pending.action_id)) == 1


async def test_a_batch_is_capped(service: ActionService, user: User) -> None:
    calls = [task(title=f"task {n}") for n in range(MAX_BATCH_ITEMS + 5)]

    pending = await proposal(service, user, *calls)

    assert len(pending.items) == MAX_BATCH_ITEMS


async def test_cancelling_a_batch_saves_none_of_it(
    service: ActionService, user: User, sessions: SessionFactory
) -> None:
    pending = await proposal(service, user, task(title="a"), REMINDER)

    await service.resolve(user.id, pending.action_id, confirm=False)

    async with sessions() as session:
        assert await session.scalar(select(Task)) is None
        assert await session.scalar(select(Reminder)) is None


async def test_undo_removes_what_was_just_saved(
    service: ActionService, user: User, sessions: SessionFactory
) -> None:
    pending = await proposal(service, user, task(title="buy milk"), REMINDER)
    await service.resolve(user.id, pending.action_id, confirm=True)
    assert await service.last_saved(user.id) == pending.action_id

    resolution = await service.undo(user.id, pending.action_id)

    assert resolution.status is ActionStatus.UNDONE
    assert resolution.message == UNDONE
    assert await service.last_saved(user.id) is None
    async with sessions() as session:
        assert await session.scalar(select(Task)) is None
        assert await session.scalar(select(Reminder)) is None


async def test_undo_leaves_other_saved_items_alone(
    service: ActionService, user: User, sessions: SessionFactory
) -> None:
    kept = await proposal(service, user, task(title="keep me"))
    await service.resolve(user.id, kept.action_id, confirm=True)
    dropped = await proposal(service, user, task(title="drop me"))
    await service.resolve(user.id, dropped.action_id, confirm=True)

    await service.undo(user.id, dropped.action_id)

    async with sessions() as session:
        assert [t.title for t in await session.scalars(select(Task))] == ["keep me"]


async def test_undo_only_works_for_a_short_while(
    service: ActionService, user: User, sessions: SessionFactory, clock: Clock
) -> None:
    pending = await proposal(service, user)
    await service.resolve(user.id, pending.action_id, confirm=True)
    clock.now += timedelta(minutes=11)

    assert await service.last_saved(user.id) is None
    resolution = await service.undo(user.id, pending.action_id)

    assert resolution.message == NOTHING_TO_UNDO
    async with sessions() as session:
        assert await session.scalar(select(Reminder)) is not None


async def test_nothing_unsaved_can_be_undone(service: ActionService, user: User) -> None:
    pending = await proposal(service, user)

    resolution = await service.undo(user.id, pending.action_id)

    assert resolution.status is ActionStatus.PENDING
    assert resolution.message == NOTHING_TO_UNDO


async def test_users_can_never_undo_each_others_actions(
    service: ActionService, user: User, sessions: SessionFactory
) -> None:
    other = await get_or_create_user(sessions, "mallory@example.com", PARIS)
    pending = await proposal(service, user)
    await service.resolve(user.id, pending.action_id, confirm=True)

    assert await service.last_saved(other.id) is None
    with pytest.raises(ActionNotFoundError):
        await service.undo(other.id, pending.action_id)
    async with sessions() as session:
        assert await session.scalar(select(Reminder)) is not None


async def test_a_repeating_task_is_saved_once_with_its_days_and_time(
    service: ActionService, user: User, sessions: SessionFactory
) -> None:
    routine = task(title="apply for jobs", repeat=["friday", "monday"], at="9am")

    pending = await proposal(service, user, routine)
    await service.resolve(user.id, pending.action_id, confirm=True)

    assert pending.items[0].summary == "a task: apply for jobs, every Monday and Friday at 9 AM"
    async with sessions() as session:
        [saved] = list(await session.scalars(select(Task)))
    assert saved.repeat_days == ["monday", "friday"]
    assert saved.time_of_day is not None
    assert saved.time_of_day.hour == 9
    assert saved.due_at is None


async def test_a_repeating_reminder_starts_at_the_next_matching_day(
    service: ActionService, user: User, sessions: SessionFactory
) -> None:
    pending = await proposal(
        service, user, reminder(title="stretch", when="9pm", repeat=["monday"])
    )
    await service.resolve(user.id, pending.action_id, confirm=True)

    assert pending.items[0].summary == "a reminder to stretch, every Monday at 9 PM"
    async with sessions() as session:
        saved = await session.scalar(select(Reminder))
    assert saved is not None
    assert saved.repeat_days == ["monday"]
    assert saved.remind_at == datetime(2037, 11, 23, 20, 0, tzinfo=UTC)


async def test_items_already_saved_are_not_saved_again(
    service: ActionService, user: User, sessions: SessionFactory
) -> None:
    first = await proposal(service, user, task(title="Call the Bank"), REMINDER)
    await service.resolve(user.id, first.action_id, confirm=True)

    again = await proposal(
        service,
        user,
        task(title="apply for jobs", repeat=["monday"]),
        task(title="call the bank"),
        REMINDER,
    )

    assert [item.summary for item in again.items] == ["a task: apply for jobs, every Monday"]
    assert again.question == (
        "Got it, a task: apply for jobs, every Monday. Should I save it? "
        "Call the Bank and call mom are already on your list."
    )
    await service.resolve(user.id, again.action_id, confirm=True)
    async with sessions() as session:
        assert len(list(await session.scalars(select(Task)))) == 2
        assert len(list(await session.scalars(select(Reminder)))) == 1


async def test_only_duplicates_is_said_instead_of_proposed(
    service: ActionService, user: User
) -> None:
    first = await proposal(service, user, task(title="buy milk"))
    await service.resolve(user.id, first.action_id, confirm=True)

    outcome = await service.propose(user.id, PARIS, [task(title="Buy milk!")])

    assert outcome == Rejection("buy milk is already on your list.")
    assert await service.pending(user.id) is None


async def test_a_finished_task_or_a_new_time_can_be_added_again(
    service: ActionService, user: User, sessions: SessionFactory
) -> None:
    first = await proposal(service, user, task(title="buy milk"), REMINDER)
    await service.resolve(user.id, first.action_id, confirm=True)
    async with sessions() as session, session.begin():
        milk = await session.scalar(select(Task))
        assert milk is not None
        milk.done = True

    again = await proposal(
        service, user, task(title="buy milk"), reminder(title="call mom", when="tomorrow at 8pm")
    )

    assert len(again.items) == 2


async def test_another_users_items_never_count_as_duplicates(
    service: ActionService, user: User, sessions: SessionFactory
) -> None:
    other = await get_or_create_user(sessions, "mallory@example.com", PARIS)
    first = await proposal(service, user, task(title="buy milk"), REMINDER)
    await service.resolve(user.id, first.action_id, confirm=True)

    theirs = await proposal(service, other, task(title="buy milk"), REMINDER)

    assert len(theirs.items) == 2


async def test_a_repeating_item_needs_a_clear_time(service: ActionService, user: User) -> None:
    outcome = await service.propose(
        user.id, PARIS, [task(title="x", repeat=["monday"], at="whenever")]
    )

    assert outcome == Rejection(UNCLEAR_TIME_OF_DAY)
