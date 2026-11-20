from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest

from companion.actions.describe import days_phrase
from companion.actions.repeat import next_occurrence
from companion.actions.tools import Weekday

PARIS = ZoneInfo("Europe/Paris")
THURSDAY_NOON = datetime(2037, 11, 19, 12, 0, tzinfo=PARIS)


@pytest.mark.parametrize(
    ("days", "phrase"),
    [
        (list(Weekday), "every day"),
        (
            [Weekday.FRIDAY, Weekday.MONDAY, Weekday.TUESDAY, Weekday.WEDNESDAY, Weekday.THURSDAY],
            "every weekday",
        ),
        ([Weekday.SUNDAY, Weekday.SATURDAY], "every weekend"),
        ([Weekday.THURSDAY, Weekday.MONDAY], "every Monday and Thursday"),
        ([Weekday.FRIDAY], "every Friday"),
    ],
)
def test_days_are_said_naturally(days: list[Weekday], phrase: str) -> None:
    assert days_phrase(days) == phrase


def test_the_next_occurrence_can_be_later_today() -> None:
    assert next_occurrence([Weekday.THURSDAY], time(18), THURSDAY_NOON) == datetime(
        2037, 11, 19, 18, 0, tzinfo=PARIS
    )


def test_a_time_already_passed_today_moves_to_the_next_repeat_day() -> None:
    assert next_occurrence([Weekday.THURSDAY, Weekday.MONDAY], time(9), THURSDAY_NOON) == datetime(
        2037, 11, 23, 9, 0, tzinfo=PARIS
    )


def test_a_weekly_repeat_comes_back_a_week_later() -> None:
    assert next_occurrence([Weekday.THURSDAY], time(12), THURSDAY_NOON) == datetime(
        2037, 11, 26, 12, 0, tzinfo=PARIS
    )


def test_daylight_saving_keeps_the_local_time() -> None:
    before_switch = datetime(2037, 10, 24, 20, 0, tzinfo=PARIS)

    after = next_occurrence(list(Weekday), time(9), before_switch)

    assert after == datetime(2037, 10, 25, 9, 0, tzinfo=PARIS)
    assert after.utcoffset() != before_switch.utcoffset()


def test_no_days_is_a_mistake() -> None:
    with pytest.raises(ValueError, match="no repeat days"):
        next_occurrence([], time(9), THURSDAY_NOON)
