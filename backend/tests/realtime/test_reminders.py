import asyncio
import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from companion.db.models import Reminder, User
from companion.db.session import SessionFactory
from companion.realtime.hub import ConnectionHub
from companion.realtime.reminders import ReminderDispatcher

NOW = datetime(2037, 11, 18, 13, 0, tzinfo=UTC)


class Inbox:
    def __init__(self, *, broken: bool = False) -> None:
        self.messages: list[dict[str, str]] = []
        self.broken = broken

    async def __call__(self, message: str) -> None:
        if self.broken:
            raise ConnectionError("socket closed")
        self.messages.append(json.loads(message))


@pytest.fixture
def hub() -> ConnectionHub:
    return ConnectionHub()


@pytest.fixture
def dispatcher(sessions: SessionFactory, hub: ConnectionHub) -> ReminderDispatcher:
    return ReminderDispatcher(sessions, hub, clock=lambda: NOW)


async def add_reminder(sessions: SessionFactory, user: User, title: str, minutes: int) -> None:
    async with sessions() as session, session.begin():
        session.add(
            Reminder(user_id=user.id, title=title, remind_at=NOW + timedelta(minutes=minutes))
        )


async def delivered_titles(sessions: SessionFactory) -> set[str]:
    async with sessions() as session:
        reminders = await session.scalars(
            select(Reminder).where(Reminder.delivered_at.is_not(None))
        )
        return {r.title for r in reminders}


async def test_due_reminders_are_sent_once_to_connected_users(
    dispatcher: ReminderDispatcher, hub: ConnectionHub, sessions: SessionFactory, user: User
) -> None:
    inbox = Inbox()
    hub.connect(user.id, inbox)
    await add_reminder(sessions, user, "call mom", minutes=-1)
    await add_reminder(sessions, user, "stretch", minutes=30)

    assert await dispatcher.dispatch_due() == 1
    assert await dispatcher.dispatch_due() == 0

    assert [m["title"] for m in inbox.messages] == ["call mom"]
    assert inbox.messages[0]["type"] == "reminder_due"
    assert inbox.messages[0]["text"] == "Hey, reminder: call mom."
    assert await delivered_titles(sessions) == {"call mom"}


async def test_reminders_wait_until_the_user_connects(
    dispatcher: ReminderDispatcher, hub: ConnectionHub, sessions: SessionFactory, user: User
) -> None:
    await add_reminder(sessions, user, "call mom", minutes=-5)

    assert await dispatcher.dispatch_due() == 0
    assert await delivered_titles(sessions) == set()

    hub.connect(user.id, Inbox())
    assert await dispatcher.dispatch_due() == 1


async def test_a_failed_send_is_retried_later(
    dispatcher: ReminderDispatcher, hub: ConnectionHub, sessions: SessionFactory, user: User
) -> None:
    hub.connect(user.id, Inbox(broken=True))
    await add_reminder(sessions, user, "call mom", minutes=-1)

    assert await dispatcher.dispatch_due() == 0
    assert await delivered_titles(sessions) == set()


async def test_the_loop_stops_promptly(dispatcher: ReminderDispatcher) -> None:
    stop = asyncio.Event()
    task = asyncio.create_task(dispatcher.run(stop, interval_seconds=60))
    await asyncio.sleep(0)

    stop.set()

    await asyncio.wait_for(task, timeout=2)


async def test_a_repeating_reminder_moves_on_to_its_next_day(
    dispatcher: ReminderDispatcher, hub: ConnectionHub, sessions: SessionFactory, user: User
) -> None:
    hub.connect(user.id, Inbox())
    async with sessions() as session, session.begin():
        session.add(
            Reminder(
                user_id=user.id,
                title="drink water",
                remind_at=NOW - timedelta(minutes=1),
                repeat_days=["wednesday", "friday"],
            )
        )

    assert await dispatcher.dispatch_due() == 1

    async with sessions() as session:
        reminder = await session.scalar(select(Reminder))
    assert reminder is not None
    assert reminder.delivered_at is None
    assert reminder.remind_at == datetime(2037, 11, 20, 12, 59, tzinfo=UTC)
    assert await dispatcher.dispatch_due() == 0
