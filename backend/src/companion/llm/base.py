from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Role
    content: str


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ToolCall:
    name: str
    arguments: str


@dataclass(frozen=True, slots=True)
class LLMReply:
    text: str
    tool_calls: tuple[ToolCall, ...] = field(default=())


class LLMError(Exception):
    pass


class ToolCallError(LLMError):
    pass


class RateLimitedError(LLMError):
    pass


class LLMProvider(Protocol):
    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 512,
        json_mode: bool = False,
        tools: Sequence[ToolSpec] = (),
    ) -> LLMReply:
        """Return the model's reply: text, and any tool calls it chose to make.

        With `json_mode`, the provider is asked to return a JSON object. Callers must still
        validate it, and must validate tool call arguments: no provider can be fully trusted
        to follow a schema.
        """
        ...


def openai_tools(tools: Sequence[ToolSpec]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }
        for tool in tools
    ]
