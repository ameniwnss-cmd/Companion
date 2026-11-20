from collections.abc import Collection
from datetime import datetime, time, timedelta

from companion.actions.tools import Weekday

WEEK = list(Weekday)


def in_week_order(days: Collection[Weekday]) -> list[Weekday]:
    return [day for day in WEEK if day in days]


def weekday_of(moment: datetime) -> Weekday:
    return WEEK[moment.weekday()]


def next_occurrence(days: Collection[Weekday], at: time, now: datetime) -> datetime:
    for ahead in range(8):
        date = (now + timedelta(days=ahead)).date()
        if WEEK[date.weekday()] not in days:
            continue
        moment = datetime.combine(date, at, tzinfo=now.tzinfo)
        if moment > now:
            return moment
    raise ValueError("no repeat days given")
