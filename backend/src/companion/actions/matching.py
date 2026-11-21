import re
from collections.abc import Sequence
from datetime import date
from typing import Protocol

_NOT_WORDS = re.compile(r"[^\w]+")


class Titled(Protocol):
    @property
    def title(self) -> str: ...


class Tickable(Titled, Protocol):
    @property
    def repeat_days(self) -> list[str] | None: ...

    @property
    def done(self) -> bool: ...

    @property
    def done_on(self) -> date | None: ...


def is_done(task: Tickable, today: date) -> bool:
    return task.done_on == today if task.repeat_days else task.done


def normalised(title: str) -> str:
    return " ".join(_NOT_WORDS.sub(" ", title.casefold()).split())


def matching[T: Titled](title: str, tasks: Sequence[T]) -> list[T]:
    wanted = normalised(title)
    if not wanted:
        return []
    exact = [task for task in tasks if normalised(task.title) == wanted]
    if exact:
        return exact[:1]
    padded = f" {wanted} "
    partial = []
    for task in tasks:
        candidate = normalised(task.title)
        if candidate and (padded in f" {candidate} " or f" {candidate} " in padded):
            partial.append(task)
    return partial
