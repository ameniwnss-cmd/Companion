from collections.abc import Sequence

import pytest

from companion.conversation.personality import Personality
from companion.conversation.safety import Mode
from companion.conversation.service import (
    BODY_SAFE_REPLY,
    CRISIS_SUPPORT_LINE,
    MAX_HISTORY_MESSAGES,
    RETRY_NOTES,
    Conversation,
    ReplyProblem,
)
from companion.llm import ChatMessage, LLMError, Role
from companion.llm.fake import FakeLLM


def scripted(reply: str, mode: str = "normal") -> FakeLLM:

    def respond(_messages: Sequence[ChatMessage], json_mode: bool) -> str:
        return f'{{"mode": "{mode}"}}' if json_mode else reply

    return FakeLLM(responder=respond)


def reply_system_prompt(llm: FakeLLM) -> str:
    reply_calls = [call for call in llm.calls if not call.json_mode]
    return reply_calls[-1].messages[0].content


async def test_a_normal_turn_uses_the_teasing_personality(personality: Personality) -> None:
    llm = scripted("Monday again? Name the day and I'll hold you to it.")
    conversation = Conversation(llm, personality)

    turn = await conversation.respond("I'll start on Monday")

    assert turn.mode is Mode.NORMAL
    assert turn.teasing_allowed
    assert turn.reply == "Monday again? Name the day and I'll hold you to it."
    assert "Teasing rules" not in reply_system_prompt(llm)
    assert "Tease behaviour" in reply_system_prompt(llm)


async def test_replies_are_cleaned_for_speech(personality: Personality) -> None:
    conversation = Conversation(scripted("**Yes!** 🔥 One. Two. Three. Four."), personality)

    turn = await conversation.respond("did it")

    assert turn.reply == "Yes! One. Two."


async def test_crisis_always_ends_with_the_support_line(personality: Personality) -> None:
    llm = scripted("Breathe with me for a second.")
    conversation = Conversation(llm, personality)

    turn = await conversation.respond("I can't stop panicking")

    assert turn.mode is Mode.CRISIS
    assert turn.reply == f"Breathe with me for a second. {CRISIS_SUPPORT_LINE}"


async def test_stop_teasing_persists_across_turns(personality: Personality) -> None:
    llm = scripted("Okay.")
    conversation = Conversation(llm, personality)

    await conversation.respond("stop teasing please")
    turn = await conversation.respond("I also didn't do my reading today")

    assert turn.teasing_allowed is False
    assert "Tease behaviour" not in reply_system_prompt(llm)
    assert "asked you to stop teasing" in reply_system_prompt(llm)


async def test_history_is_sent_to_the_model_and_capped(personality: Personality) -> None:
    llm = scripted("ok")
    conversation = Conversation(llm, personality)

    for i in range(MAX_HISTORY_MESSAGES):
        await conversation.respond(f"message {i}")

    assert len(conversation.history) == MAX_HISTORY_MESSAGES
    assert conversation.history[-2] == ChatMessage(Role.USER, f"message {MAX_HISTORY_MESSAGES - 1}")
    last_call = [c for c in llm.calls if not c.json_mode][-1]
    assert last_call.messages[-1] == ChatMessage(Role.USER, f"message {MAX_HISTORY_MESSAGES - 1}")


@pytest.mark.parametrize("text", ["", "   ", "x" * 2001])
async def test_invalid_input_is_rejected(personality: Personality, text: str) -> None:
    with pytest.raises(ValueError):
        await Conversation(scripted("ok"), personality).respond(text)


async def test_a_provider_failure_leaves_the_conversation_unchanged(
    personality: Personality,
) -> None:
    llm = scripted("ok")
    conversation = Conversation(llm, personality)
    await conversation.respond("hello")

    llm.fail = True
    with pytest.raises(LLMError):
        await conversation.respond("stop teasing")

    assert len(conversation.history) == 2
    assert conversation.teasing_allowed is True


def drafts(*replies: str) -> FakeLLM:
    queue = list(replies)

    def respond(_messages: Sequence[ChatMessage], json_mode: bool) -> str:
        if json_mode:
            return '{"mode": "normal"}'
        return queue.pop(0) if len(queue) > 1 else queue[0]

    return FakeLLM(responder=respond)


async def test_a_body_joke_is_retried_with_a_targeted_note(personality: Personality) -> None:
    llm = drafts("Five kilos? Full body transformation!", "Not roasting that. How are you feeling?")

    turn = await Conversation(llm, personality).respond("I gained five kilos, roast me")

    assert turn.reply == "Not roasting that. How are you feeling?"
    assert RETRY_NOTES[ReplyProblem.MENTIONS_BODY] in reply_system_prompt(llm)


async def test_a_repeated_body_joke_falls_back_to_a_safe_line(personality: Personality) -> None:
    llm = drafts("Five kilos? Full body transformation!")

    turn = await Conversation(llm, personality).respond("I gained five kilos, roast me")

    assert turn.reply == BODY_SAFE_REPLY


async def test_body_words_are_fine_when_the_user_did_not_bring_up_their_body(
    personality: Personality,
) -> None:
    llm = drafts("Full body workout tomorrow then, no excuses.")

    turn = await Conversation(llm, personality).respond("what should I train tomorrow?")

    assert turn.reply == "Full body workout tomorrow then, no excuses."
    assert len([c for c in llm.calls if not c.json_mode]) == 1


async def test_copying_a_style_example_is_retried(personality: Personality) -> None:
    llm = drafts(
        """Okay, that's the third "I'll start Monday" this month. Do it.""",
        "Monday, huh? Name the hour too.",
    )

    turn = await Conversation(llm, personality).respond("I'll start Monday")

    assert turn.reply == "Monday, huh? Name the hour too."
    retry_prompt = reply_system_prompt(llm)
    assert RETRY_NOTES[ReplyProblem.COPIES_EXAMPLE] in retry_prompt
    assert "I'm writing it down" not in retry_prompt
    assert "Tease behaviour" in retry_prompt


async def test_a_second_copy_is_accepted_rather_than_looping(personality: Personality) -> None:
    llm = drafts("Two workouts this week? Nice.")

    turn = await Conversation(llm, personality).respond("did two workouts")

    assert turn.reply == "Two workouts this week? Nice."
    assert len([c for c in llm.calls if not c.json_mode]) == 2


async def test_a_comment_on_looks_is_retried_even_unprompted(personality: Personality) -> None:
    llm = drafts(
        "Three sessions? Look at you, getting swole.", "Three sessions? That's real consistency."
    )

    turn = await Conversation(llm, personality).respond("went to the gym three times")

    assert turn.reply == "Three sessions? That's real consistency."
    assert RETRY_NOTES[ReplyProblem.COMMENTS_ON_LOOKS] in reply_system_prompt(llm)
