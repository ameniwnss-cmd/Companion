from collections.abc import Sequence

import pytest

from companion.conversation.personality import Personality
from companion.conversation.safety import Mode
from companion.llm import ChatMessage, LLMReply, RateLimitedError, ToolCall
from companion.llm.fake import FakeLLM
from evals.cases import CASES
from evals.checks import judged, mode, no_actions, proposes, repeats_on
from evals.harness import Case, Judge, run_case
from evals.report import render, score_by_category

BOTH = ToolCall(
    "add_tasks_and_reminders",
    '{"tasks": [{"title": "milk"}], "reminders": [{"title": "mom", "when": "9pm"}]}',
)
ROUTINE = ToolCall(
    "add_tasks_and_reminders",
    '{"tasks": [{"title": "apply", "repeat": ["monday", "friday"], "at": "9am"}]}',
)


def llm(*calls: ToolCall, verdict: str = '{"pass": true, "reason": "fine"}') -> FakeLLM:
    def respond(messages: Sequence[ChatMessage], json_mode: bool) -> str | LLMReply:
        if json_mode and "Criterion:" in messages[-1].content:
            return verdict
        if json_mode:
            return '{"mode": "normal"}'
        return LLMReply(text="On it.", tool_calls=calls)

    return FakeLLM(responder=respond)


async def run(case: Case, model: FakeLLM, personality: Personality) -> bool:
    result = await run_case(case, model, personality, Judge(model))
    return result.passed


async def test_tool_checks_read_the_proposed_items(personality: Personality) -> None:
    both = Case("both", "tools", ("add milk and remind me",), (proposes(tasks=1, reminders=1),))
    routine = Case(
        "routine", "tools", ("every monday and friday",), (repeats_on("monday", "friday"),)
    )

    assert await run(both, llm(BOTH), personality)
    assert not await run(both, llm(), personality)
    assert await run(routine, llm(ROUTINE), personality)
    assert not await run(routine, llm(BOTH), personality)


async def test_mode_and_no_action_checks(personality: Personality) -> None:
    calm = Case("calm", "safety", ("I went for a run",), (mode(Mode.NORMAL), no_actions()))

    assert await run(calm, llm(), personality)
    assert not await run(calm, llm(BOTH), personality)


@pytest.mark.parametrize(
    ("verdict", "passed"),
    [
        ('{"pass": true, "reason": "teases kindly"}', True),
        ('{"pass": false, "reason": "lectures"}', False),
        ("not json at all", False),
    ],
)
async def test_the_judge_grades_tone(personality: Personality, verdict: str, passed: bool) -> None:
    teasing = Case("tease", "personality", ("I skipped the gym",), (judged("It teases."),))

    assert await run(teasing, llm(verdict=verdict), personality) is passed


async def test_rate_limits_are_waited_out(personality: Personality) -> None:
    replies = iter([RateLimitedError("slow down")])

    def respond(_messages: Sequence[ChatMessage], json_mode: bool) -> str:
        if json_mode:
            return '{"mode": "normal"}'
        error = next(replies, None)
        if error is not None:
            raise error
        return "Hi."

    pauses: list[float] = []

    async def pause(seconds: float) -> None:
        pauses.append(seconds)

    model = FakeLLM(responder=respond)
    calm = Case("calm", "safety", ("hello",), (no_actions(),))
    result = await run_case(calm, model, personality, Judge(model), pause=pause)

    assert result.passed
    assert len(pauses) == 1


async def test_the_report_scores_categories_and_explains_failures(
    personality: Personality,
) -> None:
    good = Case("good", "tools", ("add milk",), (proposes(tasks=1, reminders=1),))
    bad = Case("bad", "safety", ("hi",), (no_actions(),))
    model = llm(BOTH)
    results = [
        await run_case(good, model, personality, Judge(model)),
        await run_case(bad, model, personality, Judge(model)),
    ]

    report = render(results, "test-model", runs=1)

    assert score_by_category(results) == {"tools": (1, 1), "safety": (0, 1)}
    assert "| **Total** | **1/2** |" in report
    assert "### bad (safety)" in report
    assert "Failed: proposes nothing" in report


def test_every_case_is_named_once_and_checks_something() -> None:
    names = [case.name for case in CASES]

    assert len(names) == len(set(names))
    assert all(case.turns and case.checks for case in CASES)
    assert {case.category for case in CASES} == {"personality", "safety", "tools", "honesty"}
