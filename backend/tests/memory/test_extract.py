import json
from collections.abc import Sequence

import pytest

from companion.db.models import MemoryKind
from companion.llm import ChatMessage, LLMError
from companion.llm.fake import FakeLLM
from companion.memory.extract import (
    EXTRACTION_PROMPT,
    Candidate,
    extract_memories,
    worth_extracting,
)


def llm_answering(payload: object) -> FakeLLM:
    text = payload if isinstance(payload, str) else json.dumps(payload)

    def respond(_messages: Sequence[ChatMessage], _json_mode: bool) -> str:
        return text

    return FakeLLM(responder=respond)


@pytest.mark.parametrize(
    ("text", "worth_it"),
    [
        ("I want to run a 5k by March", True),
        ("I prefer workouts in the morning", True),
        ("yes please", False),
        ("ok", False),
        ("thanks man", False),
    ],
)
def test_short_answers_are_not_worth_extracting(text: str, worth_it: bool) -> None:
    assert worth_extracting(text) is worth_it


async def test_extracts_typed_memories_in_json_mode() -> None:
    llm = llm_answering(
        {
            "memories": [
                {"kind": "goal", "content": " Wants to run a 5k by March "},
                {"kind": "preference", "content": "Prefers morning workouts"},
            ]
        }
    )

    memories = await extract_memories(llm, "I want to run a 5k by March, mornings are best")

    assert memories == [
        Candidate(kind=MemoryKind.GOAL, content="Wants to run a 5k by March"),
        Candidate(kind=MemoryKind.PREFERENCE, content="Prefers morning workouts"),
    ]
    call = llm.calls[0]
    assert call.json_mode
    assert call.messages[0].content == EXTRACTION_PROMPT


async def test_sensitive_memories_are_never_stored_even_if_the_model_returns_them() -> None:
    llm = llm_answering(
        {
            "memories": [
                {"kind": "goal", "content": "Wants to lose 5 kilos"},
                {"kind": "recent_context", "content": "Feels depressed this week"},
                {"kind": "habit", "content": "Studies every evening"},
            ]
        }
    )

    memories = await extract_memories(llm, "a long message about my week")

    assert [m.content for m in memories] == ["Studies every evening"]


async def test_at_most_three_memories_per_turn() -> None:
    llm = llm_answering(
        {"memories": [{"kind": "habit", "content": f"Habit {i}"} for i in range(5)]}
    )

    assert len(await extract_memories(llm, "lots of habits here")) == 3


@pytest.mark.parametrize(
    "answer",
    ["not json", {"memories": [{"kind": "secret", "content": "x"}]}, {"memories": "nope"}, []],
)
async def test_unusable_answers_extract_nothing(answer: object) -> None:
    assert await extract_memories(llm_answering(answer), "some message here") == []


async def test_provider_failures_are_raised_for_the_caller_to_handle() -> None:
    with pytest.raises(LLMError):
        await extract_memories(FakeLLM(fail=True), "some message here")
