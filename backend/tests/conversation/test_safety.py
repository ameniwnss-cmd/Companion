import pytest

from companion.conversation.safety import (
    Mode,
    classify,
    classify_with_llm,
    comments_on_looks,
    mentions_body,
    most_severe,
    rule_mode,
    update_teasing,
)
from companion.llm import ChatMessage, Role
from companion.llm.fake import FakeLLM


def llm_saying(answer: str) -> FakeLLM:
    return FakeLLM(responder=lambda _messages, _json: answer)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("I gained like five kilos, go on, roast me.", Mode.SUPPORTIVE),
        ("Honestly I failed my exam and everything is falling apart.", Mode.SUPPORTIVE),
        ("I can't sleep, I can't stop panicking, I don't know what to do.", Mode.CRISIS),
        ("I'm having panic attacks every night", Mode.CRISIS),
        ("Sometimes I don't want to be here anymore", Mode.CRISIS),
        ("I feel so stressed about tomorrow", Mode.SUPPORTIVE),
        ("my grandma died last week", Mode.SUPPORTIVE),
        ("I'll start studying on Monday, promise.", Mode.NORMAL),
        ("I went to the gym three times this week!", Mode.NORMAL),
        ("remind me to call my mom tomorrow at 6", Mode.NORMAL),
    ],
)
def test_rules_catch_sensitive_topics_and_distress(text: str, expected: Mode) -> None:
    assert rule_mode(text) is expected


def test_most_severe_picks_the_gentlest_handling() -> None:
    assert most_severe(Mode.NORMAL, Mode.CRISIS, Mode.SUPPORTIVE) is Mode.CRISIS
    assert most_severe(Mode.NORMAL, Mode.NORMAL) is Mode.NORMAL


@pytest.mark.parametrize(
    ("before", "text", "after"),
    [
        (True, "stop teasing please", False),
        (True, "Can you stop roasting me", False),
        (True, "don't roast me today", False),
        (True, "I'm not in the mood", False),
        (False, "ok you can tease me again", True),
        (False, "roast me again, I deserve it", True),
        (False, "teasing is back on", True),
        (False, "I did my reading", False),
        (True, "I did my reading", True),
        (False, "I gained weight, go on, roast me", False),
        (True, "stop teasing, don't tease me again", False),
    ],
)
def test_stop_teasing_is_a_hard_switch(before: bool, text: str, after: bool) -> None:
    assert update_teasing(before, text) is after


@pytest.mark.parametrize("answer", ['{"mode": "normal"}', '{"mode":"supportive"}'])
async def test_llm_classifier_parses_valid_json(answer: str) -> None:
    mode = await classify_with_llm(llm_saying(answer), [], "hello")

    assert mode.value in answer


@pytest.mark.parametrize(
    "answer",
    ["not json", '{"mode": "chaotic"}', '{"label": "normal"}', "[]"],
)
async def test_llm_classifier_fails_safe_on_bad_output(answer: str) -> None:
    assert await classify_with_llm(llm_saying(answer), [], "hello") is Mode.SUPPORTIVE


async def test_llm_classifier_fails_safe_when_the_provider_is_down() -> None:
    assert await classify_with_llm(FakeLLM(fail=True), [], "hello") is Mode.SUPPORTIVE


async def test_llm_classifier_sees_recent_context_in_json_mode() -> None:
    llm = llm_saying('{"mode": "normal"}')
    history = [ChatMessage(Role.USER, f"message {i}") for i in range(10)]

    await classify_with_llm(llm, history, "latest")

    call = llm.calls[0]
    assert call.json_mode
    prompt = call.messages[-1].content
    assert "message 9" in prompt
    assert "message 5" not in prompt
    assert "latest" in prompt


async def test_model_can_raise_the_mode_above_the_rules() -> None:
    assert await classify(llm_saying('{"mode": "supportive"}'), [], "meh, whatever") is (
        Mode.SUPPORTIVE
    )


async def test_model_cannot_lower_the_mode_below_the_rules() -> None:
    mode = await classify(llm_saying('{"mode": "normal"}'), [], "I gained weight, roast me")

    assert mode is Mode.SUPPORTIVE


async def test_crisis_rules_skip_the_model_call() -> None:
    llm = llm_saying('{"mode": "normal"}')

    assert await classify(llm, [], "I can't cope anymore") is Mode.CRISIS
    assert llm.calls == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("I gained five kilos", True),
        ("my body looks weird", True),
        ("Full body transformation!", True),
        ("I'm on a diet", True),
        ("I did my reading", False),
        ("Look at you go", False),
    ],
)
def test_mentions_body(text: str, expected: bool) -> None:
    assert mentions_body(text) is expected


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ("Look at you, getting swole.", True),
        ("You're looking good, bro.", True),
        ("Beach body by summer!", True),
        ("Three workouts? Look at you go.", False),
        ("Full body workout tomorrow.", False),
        ("That run looks like a plan.", False),
    ],
)
def test_comments_on_looks(reply: str, expected: bool) -> None:
    assert comments_on_looks(reply) is expected
