import asyncio
import contextlib
import json
import logging
from collections.abc import Callable
from datetime import datetime

from sqlalchemy import select

from companion.actions.service import utc_now
from companion.db.models import Reminder
from companion.db.session import SessionFactory
from companion.realtime.hub import ConnectionHub

logger = logging.getLogger(__name__)

BATCH_SIZE = 50


def reminder_event(reminder: Reminder) -> str:
    return json.dumps(
        {
            "type": "reminder_due",
            "id": str(reminder.id),
            "title": reminder.title,
            "text": f"Hey, reminder: {reminder.title}.",
        }
    )


class ReminderDispatcher:
    def __init__(
        self,
        sessions: SessionFactory,
        hub: ConnectionHub,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._sessions = sessions
        self._hub = hub
        self._clock = clock

    async def dispatch_due(self) -> int:
        online = self._hub.connected_users()
        if not online:
            return 0
        now = self._clock()
        delivered = 0
        async with self._sessions() as session, session.begin():
            due = await session.scalars(
                select(Reminder)
                .where(
                    Reminder.remind_at <= now,
                    Reminder.delivered_at.is_(None),
                    Reminder.user_id.in_(online),
                )
                .order_by(Reminder.remind_at)
                .limit(BATCH_SIZE)
                .with_for_update(skip_locked=True)
            )
            for reminder in due:
                if await self._hub.send(reminder.user_id, reminder_event(reminder)):
                    reminder.delivered_at = now
                    delivered += 1
        return delivered

    async def run(self, stop: asyncio.Event, interval_seconds: float) -> None:
        while not stop.is_set():
            try:
                await self.dispatch_due()
            except Exception:
                logger.exception("Reminder dispatch failed; retrying on the next tick")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
