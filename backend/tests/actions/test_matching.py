from dataclasses import dataclass
from datetime import date

import pytest

from companion.actions.matching import is_done, matching, normalised

TODAY = date(2037, 11, 18)


@dataclass(frozen=True)
class Item:
    title: str
    repeat_days: list[str] | None = None
    done: bool = False
    done_on: date | None = None


TASKS = [Item("Apply for jobs"), Item("buy milk"), Item("buy eggs"), Item("run")]


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("  Apply   for JOBS! ", "apply for jobs"),
        ("“clean” my room", "clean my room"),
        ("...", ""),
    ],
)
def test_titles_are_normalised(title: str, expected: str) -> None:
    assert normalised(title) == expected


def test_an_exact_title_wins_whatever_the_case_and_punctuation() -> None:
    assert matching("apply for jobs.", TASKS) == [TASKS[0]]


def test_an_exact_title_beats_a_partial_one() -> None:
    tasks = [Item("run errands"), Item("run")]

    assert matching("run", tasks) == [tasks[1]]


def test_identical_titles_resolve_to_the_first() -> None:
    tasks = [Item("buy milk"), Item("buy milk")]

    assert matching("buy milk", tasks) == [tasks[0]]


@pytest.mark.parametrize(
    ("title", "expected"),
    [("jobs", ["Apply for jobs"]), ("I went for a run today", ["run"])],
)
def test_a_unique_partial_match_works_in_either_direction(title: str, expected: list[str]) -> None:
    assert [task.title for task in matching(title, TASKS)] == expected


def test_a_vague_title_returns_every_candidate() -> None:
    assert [task.title for task in matching("buy", TASKS)] == ["buy milk", "buy eggs"]


@pytest.mark.parametrize("title", ["walk the dog", "jo", "brunch", "!!!"])
def test_partial_matches_need_whole_words(title: str) -> None:
    assert matching(title, TASKS) == []


def test_a_one_off_task_is_done_until_reopened() -> None:
    assert is_done(Item("x", done=True), TODAY)
    assert not is_done(Item("x"), TODAY)


def test_a_repeating_task_is_only_done_for_the_day_it_was_ticked() -> None:
    routine = Item("x", repeat_days=["monday"], done_on=TODAY)

    assert is_done(routine, TODAY)
    assert not is_done(routine, date(2037, 11, 19))
