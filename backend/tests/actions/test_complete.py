import json
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import delete, select

from companion.actions.service import (
    ALREADY_DONE,
    MAX_OPEN_TASKS,
    NO_SUCH_TASK,
    SAVED,
    SKIPPED_SOME,
    UNDONE,
    WHICH_TASK,
    ActionNotFoundError,
    ActionService,
    Proposal,
    ProposedItem,
    Rejection,
)
from companion.actions.tools import COMPLETE_TASKS, TASKS_AND_REMINDERS
from companion.db.models import ActionKind, ActionStatus, PendingAction, Task, User
from companion.db.session import SessionFactory
from companion.llm import ToolCall
from companion.users import get_or_create_user

PARIS = "Europe/Paris"
TODAY = date(2037, 11, 18)


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


def tick(*titles: str) -> ToolCall:
    return ToolCall(COMPLETE_TASKS, json.dumps({"titles": list(titles)}))


async def add_task(
    sessions: SessionFactory,
    user: User,
    title: str,
    *,
    repeat_days: list[str] | None = None,
    done: bool = False,
    done_on: date | None = None,
) -> uuid.UUID:
    task = Task(
        id=uuid.uuid4(),
        user_id=user.id,
        title=title,
        repeat_days=repeat_days,
        done=done,
        done_on=done_on,
    )
    async with sessions() as session, session.begin():
        session.add(task)
    return task.id


async def load(sessions: SessionFactory, task_id: uuid.UUID) -> Task:
    async with sessions() as session:
        task = await session.get(Task, task_id)
    assert task is not None
    return task


async def proposal(service: ActionService, user: User, *calls: ToolCall) -> Proposal:
    outcome = await service.propose(user.id, PARIS, calls)
    assert isinstance(outcome, Proposal), outcome
    return outcome


async def test_ticking_off_proposes_the_exact_task_and_asks_first(
    service: ActionService, user: User, sessions: SessionFactory
) -> None:
    task_id = await add_task(sessions, user, "Apply for jobs")

    pending = await proposal(service, user, tick("apply for jobs"))

    assert pending.items == (ProposedItem(ActionKind.COMPLETE_TASK, "Apply for jobs"),)
    assert pending.question == "Nice work. Should I tick off Apply for jobs?"
    assert not (await load(sessions, task_id)).done
    async with sessions() as session:
        action = await session.scalar(select(PendingAction))
    assert action is not None
    assert action.payload == {
        "task_id": str(task_id),
        "title": "Apply for jobs",
        "repeating": False,
    }


async def test_confirming_marks_a_one_off_task_done_and_undo_reopens_it(
    service: ActionService, user: User, sessions: SessionFactory
) -> None:
    task_id = await add_task(sessions, user, "buy milk")
    pending = await proposal(service, user, tick("buy milk"))

    resolution = await service.resolve(user.id, pending.action_id, confirm=True)

    assert resolution.status is ActionStatus.CONFIRMED
    assert resolution.message == SAVED[ActionKind.COMPLETE_TASK]
    assert (await load(sessions, task_id)).done

    undone = await service.undo(user.id, pending.action_id)

    assert undone.message == UNDONE
    task = await load(sessions, task_id)
    assert not task.done
    assert task.title == "buy milk"


async def test_a_repeating_task_is_ticked_off_for_today_only(
    service: ActionService, user: User, sessions: SessionFactory
) -> None:
    yesterday = TODAY - timedelta(days=1)
    task_id = await add_task(
        sessions, user, "stretch", repeat_days=["wednesday"], done_on=yesterday
    )
    pending = await proposal(service, user, tick("stretch"))

    assert pending.question == "Nice work. Should I tick off stretch for today?"
    await service.resolve(user.id, pending.action_id, confirm=True)

    task = await load(sessions, task_id)
    assert task.done_on == TODAY
    assert not task.done

    await service.undo(user.id, pending.action_id)

    assert (await load(sessions, task_id)).done_on == yesterday


async def test_today_is_the_users_local_day(
    service: ActionService, user: User, sessions: SessionFactory, clock: Clock
) -> None:
    clock.now = datetime(2037, 11, 18, 23, 30, tzinfo=UTC)
    task_id = await add_task(sessions, user, "stretch", repeat_days=["thursday"])

    pending = await proposal(service, user, tick("stretch"))
    await service.resolve(user.id, pending.action_id, confirm=True)

    assert (await load(sessions, task_id)).done_on == date(2037, 11, 19)


async def test_declining_leaves_the_task_open(
    service: ActionService, user: User, sessions: SessionFactory
) -> None:
    task_id = await add_task(sessions, user, "buy milk")
    pending = await proposal(service, user, tick("buy milk"))

    await service.resolve(user.id, pending.action_id, confirm=False)

    assert not (await load(sessions, task_id)).done


async def test_several_tasks_are_ticked_off_together(
    service: ActionService, user: User, sessions: SessionFactory
) -> None:
    milk = await add_task(sessions, user, "buy milk")
    bank = await add_task(sessions, user, "call the bank")

    pending = await proposal(service, user, tick("buy milk", "call the bank"))
    resolution = await service.resolve(user.id, pending.action_id, confirm=True)

    assert pending.question == "Nice work. Should I tick off buy milk and call the bank?"
    assert resolution.message == "Ticked off all 2."
    assert (await load(sessions, milk)).done
    assert (await load(sessions, bank)).done


async def test_naming_the_same_task_twice_ticks_it_once(
    service: ActionService, user: User, sessions: SessionFactory
) -> None:
    await add_task(sessions, user, "apply for jobs")

    pending = await proposal(service, user, tick("apply for jobs", "jobs"))

    assert len(pending.items) == 1


async def test_a_partial_title_is_enough_when_it_is_unique(
    service: ActionService, user: User, sessions: SessionFactory
) -> None:
    await add_task(sessions, user, "apply for jobs")
    await add_task(sessions, user, "buy milk")

    pending = await proposal(service, user, tick("jobs"))

    assert pending.items[0].summary == "apply for jobs"


async def test_an_unknown_task_is_not_guessed(
    service: ActionService, user: User, sessions: SessionFactory
) -> None:
    await add_task(sessions, user, "buy milk")

    outcome = await service.propose(user.id, PARIS, [tick("walk the dog")])

    assert outcome == Rejection(NO_SUCH_TASK.format(title="walk the dog"))
    assert await service.pending(user.id) is None


async def test_an_ambiguous_title_asks_which_one(
    service: ActionService, user: User, sessions: SessionFactory
) -> None:
    await add_task(sessions, user, "buy milk")
    await add_task(sessions, user, "buy eggs")

    outcome = await service.propose(user.id, PARIS, [tick("buy")])

    assert outcome == Rejection(WHICH_TASK.format(title="buy", options="buy milk or buy eggs"))
    assert await service.pending(user.id) is None


async def test_a_finished_task_is_reported_as_already_done(
    service: ActionService, user: User, sessions: SessionFactory
) -> None:
    await add_task(sessions, user, "buy milk", done=True)
    await add_task(sessions, user, "stretch", repeat_days=["wednesday"], done_on=TODAY)

    for title in ["buy milk", "stretch"]:
        outcome = await service.propose(user.id, PARIS, [tick(title)])

        assert outcome == Rejection(ALREADY_DONE.format(title=title))


async def test_unmatched_titles_are_mentioned_next_to_the_rest(
    service: ActionService, user: User, sessions: SessionFactory
) -> None:
    await add_task(sessions, user, "buy milk")
    new_task = ToolCall(TASKS_AND_REMINDERS, json.dumps({"tasks": [{"title": "clean"}]}))

    pending = await proposal(service, user, tick("buy milk", "walk the dog"), new_task)

    assert pending.question == (
        "Got it, 2 things: ticking off buy milk and a task: clean. Should I go ahead? "
        + NO_SUCH_TASK.format(title="walk the dog")
    )
    assert not pending.question.endswith(SKIPPED_SOME)


async def test_a_mixed_batch_saves_and_ticks_together(
    service: ActionService, user: User, sessions: SessionFactory
) -> None:
    milk = await add_task(sessions, user, "buy milk")
    new_task = ToolCall(TASKS_AND_REMINDERS, json.dumps({"tasks": [{"title": "clean"}]}))
    pending = await proposal(service, user, tick("buy milk"), new_task)

    resolution = await service.resolve(user.id, pending.action_id, confirm=True)

    assert resolution.message == "Saved all 2."
    assert (await load(sessions, milk)).done
    async with sessions() as session:
        assert {t.title for t in await session.scalars(select(Task))} == {"buy milk", "clean"}

    await service.undo(user.id, pending.action_id)

    async with sessions() as session:
        [left] = list(await session.scalars(select(Task)))
    assert left.title == "buy milk"
    assert not left.done


async def test_a_task_deleted_before_confirming_is_skipped(
    service: ActionService, user: User, sessions: SessionFactory
) -> None:
    task_id = await add_task(sessions, user, "buy milk")
    pending = await proposal(service, user, tick("buy milk"))
    async with sessions() as session, session.begin():
        await session.execute(delete(Task).where(Task.id == task_id))

    resolution = await service.resolve(user.id, pending.action_id, confirm=True)
    undone = await service.undo(user.id, pending.action_id)

    assert resolution.status is ActionStatus.CONFIRMED
    assert undone.status is ActionStatus.UNDONE


async def test_open_tasks_lists_only_what_is_left_today(
    service: ActionService, user: User, sessions: SessionFactory
) -> None:
    await add_task(sessions, user, "buy milk")
    await add_task(sessions, user, "done already", done=True)
    await add_task(sessions, user, "stretch", repeat_days=["wednesday"], done_on=TODAY)
    await add_task(sessions, user, "read", repeat_days=["wednesday"], done_on=TODAY - timedelta(1))

    assert await service.open_tasks(user.id, PARIS) == ["buy milk", "read"]


async def test_open_tasks_are_capped(
    service: ActionService, user: User, sessions: SessionFactory
) -> None:
    for n in range(MAX_OPEN_TASKS + 3):
        await add_task(sessions, user, f"task {n}")

    assert len(await service.open_tasks(user.id, PARIS)) == MAX_OPEN_TASKS


async def test_users_can_never_see_or_tick_off_each_others_tasks(
    service: ActionService, user: User, sessions: SessionFactory
) -> None:
    other = await get_or_create_user(sessions, "mallory@example.com", PARIS)
    task_id = await add_task(sessions, user, "buy milk")

    assert await service.open_tasks(other.id, PARIS) == []
    outcome = await service.propose(other.id, PARIS, [tick("buy milk")])
    assert outcome == Rejection(NO_SUCH_TASK.format(title="buy milk"))

    pending = await proposal(service, user, tick("buy milk"))
    with pytest.raises(ActionNotFoundError):
        await service.resolve(other.id, pending.action_id, confirm=True)
    assert not (await load(sessions, task_id)).done

    await service.resolve(user.id, pending.action_id, confirm=True)
    with pytest.raises(ActionNotFoundError):
        await service.undo(other.id, pending.action_id)
    assert (await load(sessions, task_id)).done


async def test_a_forged_action_cannot_tick_off_another_users_task(
    service: ActionService, user: User, sessions: SessionFactory
) -> None:
    other = await get_or_create_user(sessions, "mallory@example.com", PARIS)
    victim_task = await add_task(sessions, user, "buy milk")
    batch_id = uuid.uuid4()
    async with sessions() as session, session.begin():
        session.add(
            PendingAction(
                id=uuid.uuid4(),
                user_id=other.id,
                batch_id=batch_id,
                kind=ActionKind.COMPLETE_TASK,
                payload={"task_id": str(victim_task), "title": "buy milk", "repeating": False},
                status=ActionStatus.PENDING,
                expires_at=datetime(2037, 11, 18, 14, 0, tzinfo=UTC),
            )
        )

    await service.resolve(other.id, batch_id, confirm=True)

    assert not (await load(sessions, victim_task)).done
