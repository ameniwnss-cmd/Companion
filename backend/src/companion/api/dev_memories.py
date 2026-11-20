import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from companion.api.dev_user import DevUserId
from companion.db.models import MemoryKind
from companion.memory.service import MemoryNotFoundError, MemoryService, MemoryView

router = APIRouter(prefix="/dev/memories", tags=["dev"])


class MemoryOut(BaseModel):
    id: uuid.UUID
    kind: MemoryKind
    content: str
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None

    @classmethod
    def of(cls, view: MemoryView) -> "MemoryOut":
        return cls(
            id=view.id,
            kind=view.kind,
            content=view.content,
            created_at=view.created_at,
            updated_at=view.updated_at,
            expires_at=view.expires_at,
        )


class MemoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    kind: MemoryKind | None = None
    content: Annotated[str, Field(min_length=1, max_length=300)] | None = None


def _memory(request: Request) -> MemoryService:
    service: MemoryService = request.app.state.memory
    return service


Memory = Annotated[MemoryService, Depends(_memory)]
UserId = DevUserId


@router.get("")
async def list_memories(memory: Memory, user_id: UserId) -> list[MemoryOut]:
    return [MemoryOut.of(view) for view in await memory.list(user_id)]


@router.patch("/{memory_id}")
async def update_memory(
    memory_id: uuid.UUID, changes: MemoryUpdate, memory: Memory, user_id: UserId
) -> MemoryOut:
    try:
        view = await memory.update(user_id, memory_id, kind=changes.kind, content=changes.content)
    except MemoryNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Memory not found") from exc
    return MemoryOut.of(view)


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(memory_id: uuid.UUID, memory: Memory, user_id: UserId) -> None:
    try:
        await memory.delete(user_id, memory_id)
    except MemoryNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Memory not found") from exc


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def forget_everything(memory: Memory, user_id: UserId) -> None:
    await memory.forget_everything(user_id)
