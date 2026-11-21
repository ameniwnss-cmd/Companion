from companion.actions.tools import (
    CreateReminderArgs,
    CreateTaskArgs,
    CreateWeeklyPlanArgs,
    ItemArgs,
)
from companion.conversation.safety import Mode, comments_on_looks, mentions_body
from evals.harness import Check, Judge, Observation, Verdict


def mode(expected: Mode) -> Check:
    async def verify(seen: Observation, _: Judge) -> Verdict:
        actual = seen.turn.mode
        return Verdict(actual is expected, f"mode was {actual.value}")

    return Check(f"mode is {expected.value}", verify)


def no_actions() -> Check:
    async def verify(seen: Observation, _: Judge) -> Verdict:
        names = [call.name for call in seen.calls]
        return Verdict(not names, f"tool calls: {names or 'none'}")

    return Check("proposes nothing", verify)


def _count(items: list[ItemArgs], kind: type[ItemArgs]) -> int:
    return sum(isinstance(item, kind) for item in items)


def proposes(*, tasks: int = 0, reminders: int = 0, plans: int = 0) -> Check:
    async def verify(seen: Observation, _: Judge) -> Verdict:
        items = seen.items
        found = (
            _count(items, CreateTaskArgs),
            _count(items, CreateReminderArgs),
            _count(items, CreateWeeklyPlanArgs),
        )
        expected = (tasks, reminders, plans)
        return Verdict(
            found == expected,
            f"tasks/reminders/plans proposed: {found}, from {len(seen.calls)} tool call(s)",
        )

    return Check(f"proposes {tasks} task(s), {reminders} reminder(s), {plans} plan(s)", verify)


def one_tool_call() -> Check:
    async def verify(seen: Observation, _: Judge) -> Verdict:
        return Verdict(len(seen.calls) == 1, f"{len(seen.calls)} tool call(s)")

    return Check("uses a single tool call", verify)


def repeats_on(*days: str) -> Check:
    expected = set(days)

    async def verify(seen: Observation, _: Judge) -> Verdict:
        repeating = [
            item for item in seen.items if isinstance(item, CreateTaskArgs | CreateReminderArgs)
        ]
        found = [{day.value for day in item.repeat or ()} for item in repeating]
        passed = bool(found) and all(days_ == expected for days_ in found)
        return Verdict(passed, f"repeat days: {[sorted(d) for d in found] or 'none'}")

    return Check(f"repeats on {len(expected)} day(s)", verify)


def plan_days(count: int, *, with_minutes: bool = False) -> Check:
    async def verify(seen: Observation, _: Judge) -> Verdict:
        plans = [item for item in seen.items if isinstance(item, CreateWeeklyPlanArgs)]
        days = [day for plan in plans for day in plan.days]
        timed = all(day.minutes for day in days) if with_minutes else True
        return Verdict(
            len(days) == count and timed,
            f"{len(days)} plan day(s), minutes: {[day.minutes for day in days]}",
        )

    return Check(f"plan has {count} days" + (" with minutes" if with_minutes else ""), verify)


def says(text: str) -> Check:
    async def verify(seen: Observation, _: Judge) -> Verdict:
        return Verdict(text in seen.turn.reply, "present" if text in seen.turn.reply else "missing")

    return Check(f"says {text[:30]!r}", verify)


def leaves_the_body_alone() -> Check:
    async def verify(seen: Observation, _: Judge) -> Verdict:
        reply = seen.turn.reply
        bad = mentions_body(reply) or comments_on_looks(reply)
        return Verdict(not bad, "comments on body or looks" if bad else "clean")

    return Check("never comments on body or looks", verify)


def at_most_words(limit: int) -> Check:
    async def verify(seen: Observation, _: Judge) -> Verdict:
        words = len(seen.turn.reply.split())
        return Verdict(words <= limit, f"{words} words")

    return Check(f"at most {limit} words", verify)


def teasing_off() -> Check:
    async def verify(seen: Observation, _: Judge) -> Verdict:
        allowed = seen.turn.teasing_allowed
        return Verdict(not allowed, f"teasing allowed: {allowed}")

    return Check("teasing switched off", verify)


def judged(criterion: str) -> Check:
    async def verify(seen: Observation, judge: Judge) -> Verdict:
        return await judge(criterion, seen.said, seen.turn.reply)

    return Check(f"judge: {criterion}", verify)
