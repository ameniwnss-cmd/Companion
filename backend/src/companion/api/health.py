from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from companion import __version__

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str


@router.get("/health")
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__)
