from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from companion.llm.base import ChatMessage, LLMError, LLMReply, ToolSpec


@dataclass(frozen=True, slots=True)
class FakeCall:
    messages: tuple[ChatMessage, ...]
    json_mode: bool
    tools: tuple[ToolSpec, ...] = ()


Responder = Callable[[Sequence[ChatMessage], bool], str | LLMReply]


def _default_responder(messages: Sequence[ChatMessage], json_mode: bool) -> str:
    if json_mode:
        return '{"mode": "normal"}'
    return "Okay, I hear you. What's the one thing you'll do today?"


@dataclass
class FakeLLM:
    responder: Responder = _default_responder
    fail: bool = False
    calls: list[FakeCall] = field(default_factory=list)

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 512,
        json_mode: bool = False,
        tools: Sequence[ToolSpec] = (),
    ) -> LLMReply:
        self.calls.append(FakeCall(tuple(messages), json_mode, tuple(tools)))
        if self.fail:
            raise LLMError("fake provider is down")
        reply = self.responder(messages, json_mode)
        return reply if isinstance(reply, LLMReply) else LLMReply(text=reply)
