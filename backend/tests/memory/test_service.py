import asyncio
import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest

from companion.db.models import MemoryKind, User
from companion.db.session import SessionFactory
from companion.embeddings import FakeEmbedder
from companion.memory.extract import Candidate
from companion.memory.service import (
    RECENT_CONTEXT_LIFETIME,
    MemoryNotFoundError,
    MemoryService,
    UserMemory,
)
from companion.users import get_or_create_user


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2037, 11, 18, 13, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def memory(sessions: SessionFactory, clock: Clock) -> MemoryService:
    return MemoryService(sessions, FakeEmbedder(), clock=clock)


@pytest.fixture
async def other(sessions: SessionFactory) -> User:
    return await get_or_create_user(sessions, "mallory@example.com", None)


GOAL = Candidate(kind=MemoryKind.GOAL, content="Wants to run a 5k by March")
HABIT = Candidate(kind=MemoryKind.HABIT, content="Studies every evening after dinner")
PIZZA = Candidate(kind=MemoryKind.PREFERENCE, content="Loves pineapple pizza")


async def test_remembered_facts_are_listed(memory: MemoryService, user: User) -> None:
    await memory.remember(user.id, [GOAL, HABIT])

    assert {(m.kind, m.content) for m in await memory.list(user.id)} == {
        (GOAL.kind, GOAL.content),
        (HABIT.kind, HABIT.content),
    }


async def test_the_same_fact_is_updated_instead_of_duplicated(
    memory: MemoryService, user: User
) -> None:
    await memory.remember(user.id, [GOAL])
    await memory.remember(user.id, [Candidate(kind=MemoryKind.COMMITMENT, content=GOAL.content)])

    [only] = await memory.list(user.id)
    assert only.kind is MemoryKind.COMMITMENT


async def test_recall_puts_the_most_relevant_memory_first(
    memory: MemoryService, user: User
) -> None:
    await memory.remember(user.id, [PIZZA, GOAL, HABIT])

    recalled = await memory.recall(user.id, "should I run today or rest before my 5k?")

    assert recalled[0].content == GOAL.content


async def test_recent_context_expires_after_a_week(
    memory: MemoryService, user: User, clock: Clock
) -> None:
    this_week = Candidate(kind=MemoryKind.RECENT_CONTEXT, content="Has exams this week")
    await memory.remember(user.id, [this_week, GOAL])

    [context] = [m for m in await memory.list(user.id) if m.kind is MemoryKind.RECENT_CONTEXT]
    assert context.expires_at == clock.now + RECENT_CONTEXT_LIFETIME

    clock.now += RECENT_CONTEXT_LIFETIME + timedelta(minutes=1)

    assert [m.content for m in await memory.list(user.id)] == [GOAL.content]
    assert [m.content for m in await memory.recall(user.id, "exams")] == [GOAL.content]


async def test_editing_changes_content_kind_and_relevance(
    memory: MemoryService, user: User
) -> None:
    await memory.remember(user.id, [PIZZA, HABIT])
    [pizza] = [m for m in await memory.list(user.id) if m.content == PIZZA.content]

    edited = await memory.update(
        user.id, pizza.id, kind=MemoryKind.GOAL, content="Wants to swim twice a week"
    )

    assert (edited.kind, edited.content) == (MemoryKind.GOAL, "Wants to swim twice a week")
    assert (await memory.recall(user.id, "swim this week"))[0].id == pizza.id


async def test_deleting_and_forgetting_everything(memory: MemoryService, user: User) -> None:
    await memory.remember(user.id, [GOAL, HABIT, PIZZA])
    first = (await memory.list(user.id))[0]

    await memory.delete(user.id, first.id)
    assert len(await memory.list(user.id)) == 2

    assert await memory.forget_everything(user.id) == 2
    assert await memory.list(user.id) == []


async def test_users_never_see_or_change_each_others_memories(
    memory: MemoryService, user: User, other: User
) -> None:
    await memory.remember(user.id, [GOAL])
    [goal] = await memory.list(user.id)

    assert await memory.list(other.id) == []
    assert await memory.recall(other.id, GOAL.content) == []
    with pytest.raises(MemoryNotFoundError):
        await memory.update(other.id, goal.id, content="hijacked")
    with pytest.raises(MemoryNotFoundError):
        await memory.delete(other.id, goal.id)
    assert await memory.forget_everything(other.id) == 0
    assert [m.content for m in await memory.list(user.id)] == [GOAL.content]


async def test_another_users_identical_fact_is_not_treated_as_a_duplicate(
    memory: MemoryService, user: User, other: User
) -> None:
    await memory.remember(user.id, [GOAL])
    await memory.remember(other.id, [GOAL])

    assert len(await memory.list(user.id)) == 1
    assert len(await memory.list(other.id)) == 1


async def test_user_memory_learns_in_the_background(memory: MemoryService, user: User) -> None:
    seen: list[str] = []

    async def extractor(text: str) -> list[Candidate]:
        seen.append(text)
        return [GOAL]

    gateway = UserMemory(memory, user.id, extractor)
    gateway.observe("ok")
    gateway.observe("I really want to run a 5k by March")
    await gateway.settle()

    assert seen == ["I really want to run a 5k by March"]
    assert [m.content for m in await gateway.recall("5k")] == [GOAL.content]


async def test_a_failed_extraction_is_logged_not_raised(
    memory: MemoryService, user: User, caplog: pytest.LogCaptureFixture
) -> None:
    async def broken(text: str) -> list[Candidate]:
        raise RuntimeError("model fell over")

    gateway = UserMemory(memory, user.id, broken)
    with caplog.at_level(logging.ERROR, logger="companion"):
        gateway.observe("I want to learn to cook this month")
        await gateway.settle()

    assert "Learning from a message failed" in caplog.text
    assert await memory.list(user.id) == []


async def test_without_an_extractor_nothing_is_learned(memory: MemoryService, user: User) -> None:
    gateway = UserMemory(memory, user.id)

    gateway.observe("I want to learn to cook this month")
    await gateway.settle()

    assert await memory.list(user.id) == []


async def test_learning_waits_until_released(memory: MemoryService, user: User) -> None:
    async def extractor(text: str) -> list[Candidate]:
        return [GOAL]

    gateway = UserMemory(memory, user.id, extractor)
    gateway.observe("I really want to run a 5k by March")
    await asyncio.sleep(0)

    assert await memory.list(user.id) == []
    gateway.release()
    await gateway.settle()
    assert [m.content for m in await memory.list(user.id)] == [GOAL.content]


class CountingEmbedder(FakeEmbedder):
    def __init__(self) -> None:
        self.calls = 0

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        return await super().embed(texts)


async def test_waking_loads_the_embedding_model_in_the_background(
    sessions: SessionFactory, user: User
) -> None:
    embedder = CountingEmbedder()
    mine = UserMemory(MemoryService(sessions, embedder), user.id)

    mine.wake()
    await mine.settle()

    assert embedder.calls == 1
