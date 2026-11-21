from collections.abc import Collection
from datetime import datetime, time
from typing import Any

from companion.actions.repeat import WEEK, in_week_order
from companion.actions.tools import Weekday
from companion.db.models import ActionKind

WEEK_AHEAD_DAYS = 7
WEEKDAYS = frozenset(WEEK[:5])
WEEKEND = frozenset(WEEK[5:])


def spoken_clock(moment: datetime | time) -> str:
    if (moment.hour, moment.minute) == (12, 0):
        return "noon"
    if (moment.hour, moment.minute) == (0, 0):
        return "midnight"
    hour = moment.hour % 12 or 12
    suffix = "AM" if moment.hour < 12 else "PM"
    return f"{hour} {suffix}" if moment.minute == 0 else f"{hour}:{moment.minute:02d} {suffix}"


def spoken_time(moment: datetime, now: datetime) -> str:
    local = moment.astimezone(now.tzinfo)
    days_away = (local.date() - now.date()).days
    if days_away == 0:
        day = "today"
    elif days_away == 1:
        day = "tomorrow"
    elif days_away < WEEK_AHEAD_DAYS:
        day = f"on {local:%A}"
    else:
        day = f"on {local:%A}, {local:%B} {local.day}"
    return f"{day} at {spoken_clock(local)}"


def spoken_list(items: list[str], last: str = "and") -> str:
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} {last} {items[-1]}"


def days_phrase(days: Collection[Weekday | str]) -> str:
    chosen = frozenset(Weekday(day) for day in days)
    if chosen == frozenset(WEEK):
        return "every day"
    if chosen == WEEKDAYS:
        return "every weekday"
    if chosen == WEEKEND:
        return "every weekend"
    return "every " + spoken_list([day.value.capitalize() for day in in_week_order(chosen)])


def describe(kind: ActionKind, payload: dict[str, Any], now: datetime) -> str:
    match kind:
        case ActionKind.REMINDER:
            remind_at = datetime.fromisoformat(payload["remind_at"])
            if payload.get("repeat_days"):
                local = remind_at.astimezone(now.tzinfo)
                when = f"{days_phrase(payload['repeat_days'])} at {spoken_clock(local)}"
            else:
                when = spoken_time(remind_at, now)
            return f"a reminder to {payload['title']}, {when}"
        case ActionKind.TASK:
            task = f"a task: {payload['title']}"
            if payload.get("repeat_days"):
                repeats = f"{task}, {days_phrase(payload['repeat_days'])}"
                at = payload.get("time_of_day")
                return f"{repeats} at {spoken_clock(time.fromisoformat(at))}" if at else repeats
            if payload["due_at"] is None:
                return task
            return f"{task}, due {spoken_time(datetime.fromisoformat(payload['due_at']), now)}"
        case ActionKind.WEEKLY_PLAN:
            days = [
                f"{d['day'].capitalize()} {d['activity']}"
                + (f" for {d['minutes']} minutes" if d.get("minutes") else "")
                for d in payload["sessions"]
            ]
            return f"a weekly plan called {payload['name']}: {spoken_list(days)}"
        case ActionKind.COMPLETE_TASK:
            title: str = payload["title"]
            return f"{title} for today" if payload.get("repeating") else title
