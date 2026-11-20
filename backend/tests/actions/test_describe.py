from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from companion.actions.describe import describe, spoken_clock, spoken_list, spoken_time
from companion.db.models import ActionKind

PARIS = ZoneInfo("Europe/Paris")
NOW = datetime(2037, 11, 18, 14, 0, tzinfo=PARIS)


@pytest.mark.parametrize(
    ("hour", "minute", "spoken"),
    [(18, 0, "6 PM"), (9, 5, "9:05 AM"), (12, 0, "noon"), (0, 0, "midnight"), (12, 30, "12:30 PM")],
)
def test_spoken_clock(hour: int, minute: int, spoken: str) -> None:
    assert spoken_clock(datetime(2037, 1, 1, hour, minute)) == spoken


@pytest.mark.parametrize(
    ("moment", "spoken"),
    [
        (datetime(2037, 11, 18, 18, 0, tzinfo=PARIS), "today at 6 PM"),
        (datetime(2037, 11, 19, 9, 0, tzinfo=PARIS), "tomorrow at 9 AM"),
        (datetime(2037, 11, 24, 9, 0, tzinfo=PARIS), "on Tuesday at 9 AM"),
        (datetime(2037, 12, 2, 9, 0, tzinfo=PARIS), "on Wednesday, December 2 at 9 AM"),
    ],
)
def test_spoken_time_is_relative_to_now(moment: datetime, spoken: str) -> None:
    assert spoken_time(moment, NOW) == spoken


def test_spoken_time_uses_the_users_timezone() -> None:
    utc_moment = datetime(2037, 11, 19, 17, 0, tzinfo=ZoneInfo("UTC"))

    assert spoken_time(utc_moment, NOW) == "tomorrow at 6 PM"


@pytest.mark.parametrize(
    ("items", "spoken"),
    [([], ""), (["a"], "a"), (["a", "b"], "a and b"), (["a", "b", "c"], "a, b and c")],
)
def test_spoken_list(items: list[str], spoken: str) -> None:
    assert spoken_list(items) == spoken


def test_describe_each_kind() -> None:
    tomorrow_6pm = datetime(2037, 11, 19, 18, 0, tzinfo=PARIS).isoformat()

    assert (
        describe(ActionKind.REMINDER, {"title": "call mom", "remind_at": tomorrow_6pm}, NOW)
        == "a reminder to call mom, tomorrow at 6 PM"
    )
    assert describe(ActionKind.TASK, {"title": "buy milk", "due_at": None}, NOW) == (
        "a task: buy milk"
    )
    assert describe(ActionKind.TASK, {"title": "essay", "due_at": tomorrow_6pm}, NOW) == (
        "a task: essay, due tomorrow at 6 PM"
    )
    plan = {
        "name": "Get strong",
        "sessions": [
            {"day": "monday", "focus": "upper body", "minutes": 45},
            {"day": "thursday", "focus": "legs", "minutes": 40},
        ],
    }
    assert describe(ActionKind.WORKOUT_PLAN, plan, NOW) == (
        "a workout plan called Get strong: Monday upper body for 45 minutes "
        "and Thursday legs for 40 minutes"
    )
