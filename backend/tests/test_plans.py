import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from companion.config import Environment, Settings
from companion.db.models import Reminder, Task, User, WeeklyPlan
from companion.db.session import SessionFactory
from companion.llm.fake import FakeLLM
from companion.main import create_app
from companion.plans.service import ItemNotFoundError, PlansService
from companion.users import get_or_create_user

SOON = datetime(2037, 11, 20, 9, 0, tzinfo=UTC)
SESSIONS = [{"day": "monday", "activity": "legs", "minutes": 40}]


async def seed(sessions: SessionFactory, user: User) -> None:
    async with sessions() as session, session.begin():
        session.add_all(
            [
                Task(user_id=user.id, title="done already", done=True),
                Task(user_id=user.id, title="no deadline"),
                Task(user_id=user.id, title="due soon", due_at=SOON),
                Reminder(user_id=user.id, title="later", remind_at=SOON + timedelta(days=1)),
                Reminder(
                    user_id=user.id,
                    title="already sent",
                    remind_at=SOON - timedelta(days=1),
                    delivered_at=SOON,
                ),
                Reminder(user_id=user.id, title="next", remind_at=SOON),
                WeeklyPlan(user_id=user.id, name="Get strong", sessions=SESSIONS),
            ]
        )


@pytest.fixture
def plans(sessions: SessionFactory) -> PlansService:
    return PlansService(sessions)


@pytest.fixture
async def other(sessions: SessionFactory) -> User:
    return await get_or_create_user(sessions, "mallory@example.com", None)


async def test_tasks_list_open_ones_first_by_due_date(
    plans: PlansService, sessions: SessionFactory, user: User
) -> None:
    await seed(sessions, user)

    assert [t.title for t in await plans.tasks(user.id)] == [
        "due soon",
        "no deadline",
        "done already",
    ]


async def test_reminders_list_upcoming_ones_first(
    plans: PlansService, sessions: SessionFactory, user: User
) -> None:
    await seed(sessions, user)

    reminders = await plans.reminders(user.id)

    assert [(r.title, r.delivered) for r in reminders] == [
        ("next", False),
        ("later", False),
        ("already sent", True),
    ]


async def test_a_task_can_be_ticked_off_and_items_deleted(
    plans: PlansService, sessions: SessionFactory, user: User
) -> None:
    await seed(sessions, user)
    task = (await plans.tasks(user.id))[0]
    [plan] = await plans.weekly_plans(user.id)

    assert (await plans.set_task_done(user.id, task.id, True)).done is True
    await plans.remove(WeeklyPlan, user.id, plan.id)

    assert await plans.weekly_plans(user.id) == []
    with pytest.raises(ItemNotFoundError):
        await plans.remove(WeeklyPlan, user.id, plan.id)


async def test_users_never_see_or_change_each_others_plans(
    plans: PlansService, sessions: SessionFactory, user: User, other: User
) -> None:
    await seed(sessions, user)
    task = (await plans.tasks(user.id))[0]
    reminder = (await plans.reminders(user.id))[0]

    assert await plans.tasks(other.id) == []
    assert await plans.reminders(other.id) == []
    assert await plans.weekly_plans(other.id) == []
    with pytest.raises(ItemNotFoundError):
        await plans.set_task_done(other.id, task.id, True)
    with pytest.raises(ItemNotFoundError):
        await plans.remove(Reminder, other.id, reminder.id)
    assert len(await plans.reminders(user.id)) == 3


@pytest.fixture
def client(settings: Settings, sessions: SessionFactory) -> Iterator[TestClient]:
    async def seed_dev_user() -> None:
        await seed(sessions, await get_or_create_user(sessions, settings.dev_user_email, None))

    asyncio.run(seed_dev_user())
    with TestClient(create_app(settings, llm=FakeLLM())) as client:
        yield client


def test_the_plans_api_lists_updates_and_deletes(client: TestClient) -> None:
    tasks = client.get("/dev/tasks").json()
    assert [t["title"] for t in tasks] == ["due soon", "no deadline", "done already"]

    ticked = client.patch(f"/dev/tasks/{tasks[0]['id']}", json={"done": True})
    assert ticked.status_code == 200
    assert ticked.json()["done"] is True

    reminders = client.get("/dev/reminders").json()
    assert client.delete(f"/dev/reminders/{reminders[0]['id']}").status_code == 204
    assert len(client.get("/dev/reminders").json()) == 2

    [plan] = client.get("/dev/weekly-plans").json()
    assert plan["sessions"] == SESSIONS
    assert client.delete(f"/dev/weekly-plans/{plan['id']}").status_code == 204
    assert client.delete(f"/dev/weekly-plans/{plan['id']}").status_code == 404


def test_invalid_task_updates_are_rejected(client: TestClient) -> None:
    task_id = client.get("/dev/tasks").json()[0]["id"]

    assert client.patch(f"/dev/tasks/{task_id}", json={"title": "x"}).status_code == 422
    assert client.patch(f"/dev/tasks/{task_id}", json={"done": "maybe"}).status_code == 422
    unknown = "00000000-0000-0000-0000-000000000000"
    assert client.patch(f"/dev/tasks/{unknown}", json={"done": True}).status_code == 404


def test_the_plans_api_does_not_exist_in_production() -> None:
    settings = Settings(
        environment=Environment.PRODUCTION,
        dev_text_channel=True,
        reminder_loop_enabled=False,
        _env_file=None,
    )

    with TestClient(create_app(settings, llm=FakeLLM())) as client:
        assert client.get("/dev/tasks").status_code == 404


async def test_a_repeating_task_is_done_for_today_only(
    sessions: SessionFactory, user: User
) -> None:
    today = datetime(2037, 11, 18, 10, 0, tzinfo=UTC)
    clock = [today]
    plans = PlansService(sessions, clock=lambda: clock[0])
    async with sessions() as session, session.begin():
        session.add(Task(user_id=user.id, title="apply", repeat_days=["wednesday", "thursday"]))
    [task] = await plans.tasks(user.id)

    ticked = await plans.set_task_done(user.id, task.id, True)
    assert ticked.done
    assert ticked.repeat_days == ["wednesday", "thursday"]

    clock[0] = today + timedelta(days=1)
    [tomorrow] = await plans.tasks(user.id)
    assert not tomorrow.done
