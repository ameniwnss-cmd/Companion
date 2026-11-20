from datetime import datetime
from typing import Any

from companion.db.models import ActionKind

WEEK_AHEAD_DAYS = 7


def spoken_clock(moment: datetime) -> str:
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


def spoken_list(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} and {items[-1]}"


def describe(kind: ActionKind, payload: dict[str, Any], now: datetime) -> str:
    match kind:
        case ActionKind.REMINDER:
            when = spoken_time(datetime.fromisoformat(payload["remind_at"]), now)
            return f"a reminder to {payload['title']}, {when}"
        case ActionKind.TASK:
            task = f"a task: {payload['title']}"
            if payload["due_at"] is None:
                return task
            return f"{task}, due {spoken_time(datetime.fromisoformat(payload['due_at']), now)}"
        case ActionKind.WORKOUT_PLAN:
            sessions = [
                f"{s['day'].capitalize()} {s['focus']} for {s['minutes']} minutes"
                for s in payload["sessions"]
            ]
            return f"a workout plan called {payload['name']}: {spoken_list(sessions)}"
