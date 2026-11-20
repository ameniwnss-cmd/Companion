import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from companion.conversation.personality import Personality
from companion.conversation.service import MEMORY_GUIDE, Conversation, memory_block
from companion.db.models import MemoryKind
from companion.embeddings import EmbeddingError
from companion.llm import ChatMessage
from companion.llm.fake import FakeLLM
from companion.memory.service import MemoryView

NOW = datetime(2037, 11, 18, tzinfo=UTC)
GOAL = MemoryView(uuid.uuid4(), MemoryKind.GOAL, "Wants to run a 5k by March", NOW, NOW, None)
CONTEXT = MemoryView(uuid.uuid4(), MemoryKind.RECENT_CONTEXT, "Has exams this week", NOW, NOW, NOW)


@dataclass
class FakeMemory:
    remembered: list[MemoryView] = field(default_factory=lambda: [GOAL, CONTEXT])
    broken: bool = False
    recalled_for: list[str] = field(default_factory=list)
    observed: list[str] = field(default_factory=list)

    async def recall(self, text: str) -> list[MemoryView]:
        self.recalled_for.append(text)
        if self.broken:
            raise EmbeddingError("embedder down")
        return self.remembered

    def observe(self, text: str) -> None:
        self.observed.append(text)


def mode_llm(mode: str = "normal") -> FakeLLM:
    def respond(_messages: Sequence[ChatMessage], json_mode: bool) -> str:
        return f'{{"mode": "{mode}"}}' if json_mode else "Let's get that run in."

    return FakeLLM(responder=respond)


def reply_prompt(llm: FakeLLM) -> str:
    return [c for c in llm.calls if not c.json_mode][-1].messages[0].content


def test_memory_block_lists_each_memory_with_its_kind() -> None:
    assert memory_block([GOAL, CONTEXT]) == (
        f"{MEMORY_GUIDE}\n- goal: Wants to run a 5k by March\n- recent context: Has exams this week"
    )
    assert memory_block([]) == ""


async def test_relevant_memories_are_added_to_the_prompt(personality: Personality) -> None:
    llm, memory = mode_llm(), FakeMemory()

    await Conversation(llm, personality, memory=memory).respond("should I run today?")

    assert memory.recalled_for == ["should I run today?"]
    assert memory_block([GOAL, CONTEXT]) in reply_prompt(llm)


async def test_each_normal_turn_is_offered_for_learning(personality: Personality) -> None:
    memory = FakeMemory()

    await Conversation(mode_llm(), personality, memory=memory).respond("I want to run a 5k")

    assert memory.observed == ["I want to run a 5k"]


async def test_nothing_is_learned_from_a_crisis(personality: Personality) -> None:
    memory = FakeMemory()

    await Conversation(mode_llm(), personality, memory=memory).respond("I can't cope anymore")

    assert memory.observed == []


async def test_the_companion_still_answers_if_recall_fails(personality: Personality) -> None:
    llm, memory = mode_llm(), FakeMemory(broken=True)

    turn = await Conversation(llm, personality, memory=memory).respond("should I run today?")

    assert turn.reply == "Let's get that run in."
    assert MEMORY_GUIDE not in reply_prompt(llm)
