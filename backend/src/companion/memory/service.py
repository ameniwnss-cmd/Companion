import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol

from sqlalchemy import ColumnElement, delete, or_, select

from companion.actions.service import utc_now
from companion.db.models import Memory, MemoryKind
from companion.db.session import SessionFactory
from companion.embeddings import Embedder
from companion.memory.extract import Candidate, worth_extracting

logger = logging.getLogger(__name__)

DUPLICATE_DISTANCE = 0.15
RECALL_LIMIT = 6
RECENT_CONTEXT_LIFETIME = timedelta(days=7)


@dataclass(frozen=True, slots=True)
class MemoryView:
    id: uuid.UUID
    kind: MemoryKind
    content: str
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None

    @classmethod
    def of(cls, memory: Memory) -> "MemoryView":
        return cls(
            memory.id,
            memory.kind,
            memory.content,
            memory.created_at,
            memory.updated_at,
            memory.expires_at,
        )


class MemoryNotFoundError(LookupError):
    pass


class MemoryService:
    def __init__(
        self,
        sessions: SessionFactory,
        embedder: Embedder,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._sessions = sessions
        self._embedder = embedder
        self._clock = clock

    def _expiry(self, kind: MemoryKind) -> datetime | None:
        return (
            self._clock() + RECENT_CONTEXT_LIFETIME if kind is MemoryKind.RECENT_CONTEXT else None
        )

    def _active(self) -> ColumnElement[bool]:
        return or_(Memory.expires_at.is_(None), Memory.expires_at > self._clock())

    async def remember(self, user_id: uuid.UUID, candidates: Sequence[Candidate]) -> None:
        if not candidates:
            return
        vectors = await self._embedder.embed([c.content for c in candidates])
        async with self._sessions() as session, session.begin():
            for candidate, vector in zip(candidates, vectors, strict=True):
                existing = await session.scalar(
                    select(Memory)
                    .where(
                        Memory.user_id == user_id,
                        Memory.embedding.cosine_distance(vector) < DUPLICATE_DISTANCE,
                    )
                    .order_by(Memory.embedding.cosine_distance(vector))
                    .limit(1)
                )
                memory = existing or Memory(user_id=user_id)
                memory.kind = candidate.kind
                memory.content = candidate.content
                memory.embedding = vector
                memory.expires_at = self._expiry(candidate.kind)
                session.add(memory)

    async def recall(
        self, user_id: uuid.UUID, text: str, limit: int = RECALL_LIMIT
    ) -> list[MemoryView]:
        [vector] = await self._embedder.embed([text])
        async with self._sessions() as session:
            memories = await session.scalars(
                select(Memory)
                .where(Memory.user_id == user_id, self._active())
                .order_by(Memory.embedding.cosine_distance(vector))
                .limit(limit)
            )
            return [MemoryView.of(m) for m in memories]

    async def list(self, user_id: uuid.UUID) -> list[MemoryView]:
        async with self._sessions() as session:
            memories = await session.scalars(
                select(Memory)
                .where(Memory.user_id == user_id, self._active())
                .order_by(Memory.kind, Memory.updated_at.desc())
            )
            return [MemoryView.of(m) for m in memories]

    async def update(
        self,
        user_id: uuid.UUID,
        memory_id: uuid.UUID,
        *,
        kind: MemoryKind | None = None,
        content: str | None = None,
    ) -> MemoryView:
        vector = (await self._embedder.embed([content]))[0] if content is not None else None
        async with self._sessions() as session, session.begin():
            memory = await session.scalar(
                select(Memory).where(Memory.id == memory_id, Memory.user_id == user_id)
            )
            if memory is None:
                raise MemoryNotFoundError(memory_id)
            if kind is not None:
                memory.kind = kind
                memory.expires_at = self._expiry(kind)
            if content is not None and vector is not None:
                memory.content = content
                memory.embedding = vector
            await session.flush()
            await session.refresh(memory)
            return MemoryView.of(memory)

    async def delete(self, user_id: uuid.UUID, memory_id: uuid.UUID) -> None:
        async with self._sessions() as session, session.begin():
            deleted = await session.scalar(
                delete(Memory)
                .where(Memory.id == memory_id, Memory.user_id == user_id)
                .returning(Memory.id)
            )
            if deleted is None:
                raise MemoryNotFoundError(memory_id)

    async def forget_everything(self, user_id: uuid.UUID) -> int:
        async with self._sessions() as session, session.begin():
            deleted = await session.scalars(
                delete(Memory).where(Memory.user_id == user_id).returning(Memory.id)
            )
            return len(deleted.all())


class MemoryGateway(Protocol):
    async def recall(self, text: str) -> list[MemoryView]: ...

    def observe(self, text: str) -> None: ...


Extractor = Callable[[str], Awaitable[list[Candidate]]]


@dataclass
class UserMemory:
    service: MemoryService
    user_id: uuid.UUID
    extractor: Extractor | None = None
    _tasks: set[asyncio.Task[None]] = field(default_factory=set)
    _waiting: list[str] = field(default_factory=list)

    async def recall(self, text: str) -> list[MemoryView]:
        return await self.service.recall(self.user_id, text)

    def observe(self, text: str) -> None:
        if self.extractor is None or not worth_extracting(text):
            return
        self._waiting.append(text)

    def release(self) -> None:
        if self.extractor is None:
            return
        for text in self._waiting:
            task = asyncio.create_task(self._learn(self.extractor, text))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        self._waiting.clear()

    async def settle(self) -> None:
        self.release()
        await asyncio.gather(*self._tasks)

    async def _learn(self, extractor: Extractor, text: str) -> None:
        try:
            await self.service.remember(self.user_id, await extractor(text))
        except Exception:
            logger.exception("Learning from a message failed")
