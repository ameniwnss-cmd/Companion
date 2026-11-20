from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from companion.actions.when import parse_when

PARIS = ZoneInfo("Europe/Paris")
NOW = datetime(2037, 11, 18, 14, 0, tzinfo=PARIS)


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2037, 11, day, hour, minute, tzinfo=PARIS)


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [
        ("tomorrow at 6pm", at(19, 18)),
        ("Tomorrow, 6 P.M.", at(19, 18)),
        ("tomorrow at 6", at(19, 18)),
        ("tomorrow morning", at(19, 9)),
        ("tomorrow at 6 in the morning", at(19, 6)),
        ("next tuesday morning", at(24, 9)),
        ("tuesday", at(24, 9)),
        ("on friday at 9:30am", at(20, 9, 30)),
        ("wednesday at 10am", at(25, 10)),
        ("day after tomorrow at 7:15 pm", at(20, 19, 15)),
        ("tonight", at(18, 21)),
        ("tonight at 9", at(18, 21)),
        ("this evening", at(18, 19)),
        ("at 3", at(18, 15)),
        ("at 8", at(19, 8)),
        ("at noon", at(19, 12)),
        ("18:30", at(18, 18, 30)),
        ("in 20 minutes", at(18, 14, 20)),
        ("in two hours", at(18, 16)),
        ("in an hour", at(18, 15)),
        ("in half an hour", at(18, 14, 30)),
        ("in 3 days", at(21, 14)),
    ],
)
def test_understands_how_people_say_times(phrase: str, expected: datetime) -> None:
    assert parse_when(phrase, NOW) == expected


def test_a_time_today_that_has_passed_is_returned_as_said() -> None:
    assert parse_when("today at 9am", NOW) == at(18, 9)


def test_results_keep_the_users_timezone() -> None:
    result = parse_when("tomorrow at 6pm", NOW)

    assert result is not None
    assert result.tzinfo is PARIS


@pytest.mark.parametrize("phrase", ["", "sometime", "whenever you want", "at 25", "13pm", "99:99"])
def test_unclear_phrases_return_none(phrase: str) -> None:
    assert parse_when(phrase, NOW) is None
