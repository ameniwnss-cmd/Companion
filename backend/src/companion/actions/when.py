import re
from datetime import date, datetime, time, timedelta

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
DEFAULT_TIME = time(9)
PARTS_OF_DAY = {
    "morning": time(9),
    "afternoon": time(15),
    "evening": time(19),
    "night": time(21),
    "tonight": time(21),
}
EVENING_PARTS = {"afternoon", "evening", "night", "tonight"}
LATEST_AMBIGUOUS_PM_HOUR = 7

_NUMBERS = {
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "fifteen": 15,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "forty-five": 45,
}
_UNITS = {"minute": "minutes", "min": "minutes", "hour": "hours", "day": "days", "week": "weeks"}

_HALF_HOUR = re.compile(r"\bin half an hour\b")
_RELATIVE = re.compile(r"\bin (\d+|" + "|".join(_NUMBERS) + r") (minute|min|hour|day|week)s?\b")
_AM_PM = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)(?=\W|$)")
_TWENTY_FOUR_HOUR = re.compile(r"\b(\d{1,2}):(\d{2})\b")
_BARE_HOUR = re.compile(r"\b(?:at|around|by) (\d{1,2})\b")
_WEEKDAY = re.compile(r"\b(" + "|".join(WEEKDAYS) + r")\b")


def parse_when(phrase: str, now: datetime) -> datetime | None:
    text = " ".join(phrase.lower().replace(",", " ").split())

    relative = _relative(text, now)
    if relative is not None:
        return relative

    day = _day(text, now.date())
    part = next((name for name in PARTS_OF_DAY if re.search(rf"\b{name}\b", text)), None)
    clock = _clock(text, part)

    if day is None and clock is None and part is None:
        return None
    if clock is None:
        clock = PARTS_OF_DAY[part] if part else DEFAULT_TIME
    if day is None:
        candidate = datetime.combine(now.date(), clock, tzinfo=now.tzinfo)
        return candidate if candidate > now else candidate + timedelta(days=1)
    return datetime.combine(day, clock, tzinfo=now.tzinfo)


def _relative(text: str, now: datetime) -> datetime | None:
    if _HALF_HOUR.search(text):
        return now + timedelta(minutes=30)
    match = _RELATIVE.search(text)
    if match is None:
        return None
    amount = int(match[1]) if match[1].isdigit() else _NUMBERS[match[1]]
    return now + timedelta(**{_UNITS[match[2]]: amount})


def _day(text: str, today: date) -> date | None:
    if "day after tomorrow" in text:
        return today + timedelta(days=2)
    if re.search(r"\btomorrow\b", text):
        return today + timedelta(days=1)
    if re.search(r"\b(today|tonight|this (morning|afternoon|evening))\b", text):
        return today
    weekday = _WEEKDAY.search(text)
    if weekday is None:
        return None
    days_ahead = (WEEKDAYS.index(weekday[1]) - today.weekday()) % 7 or 7
    return today + timedelta(days=days_ahead)


def _clock(text: str, part: str | None) -> time | None:
    if re.search(r"\b(noon|midday)\b", text):
        return time(12)
    if re.search(r"\bmidnight\b", text):
        return time(0)

    if match := _AM_PM.search(text):
        hour, minute = int(match[1]), int(match[2] or 0)
        if not 1 <= hour <= 12 or minute > 59:
            return None
        is_pm = match[3].startswith("p")
        return time(hour % 12 + (12 if is_pm else 0), minute)

    if match := _TWENTY_FOUR_HOUR.search(text):
        hour, minute = int(match[1]), int(match[2])
        if hour > 23 or minute > 59:
            return None
        return _resolve_ambiguous(hour, minute, part)

    if match := _BARE_HOUR.search(text):
        hour = int(match[1])
        if hour > 23:
            return None
        return _resolve_ambiguous(hour, 0, part)
    return None


def _resolve_ambiguous(hour: int, minute: int, part: str | None) -> time:
    in_the_evening = part in EVENING_PARTS
    probably_pm = part is None and hour <= LATEST_AMBIGUOUS_PM_HOUR
    if 1 <= hour <= 11 and (in_the_evening or probably_pm):
        hour += 12
    return time(hour, minute)
