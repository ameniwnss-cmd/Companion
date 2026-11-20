import json
from collections.abc import Sequence
from typing import Any

import httpx

from companion.llm.base import ChatMessage, LLMError, LLMReply, ToolCall, ToolSpec, openai_tools


class OllamaLLM:
    def __init__(self, http: httpx.AsyncClient, *, base_url: str, model: str) -> None:
        self._http = http
        self._url = f"{base_url.rstrip('/')}/api/chat"
        self._model = model

    async def chat(
        self,
        messages: Sequence[ChatMessage],
        *,
        temperature: float = 0.7,
        max_tokens: int = 512,
        json_mode: bool = False,
        tools: Sequence[ToolSpec] = (),
    ) -> LLMReply:
        body: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": m.role.value, "content": m.content} for m in messages],
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if json_mode:
            body["format"] = "json"
        if tools:
            body["tools"] = openai_tools(tools)

        try:
            response = await self._http.post(self._url, json=body)
            response.raise_for_status()
            message = response.json()["message"]
            content = message["content"]
            if not isinstance(content, str):
                raise TypeError("non-text content")
            return LLMReply(
                text=content,
                tool_calls=tuple(
                    ToolCall(
                        name=call["function"]["name"],
                        arguments=json.dumps(call["function"]["arguments"]),
                    )
                    for call in message.get("tool_calls") or []
                ),
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError, AttributeError) as exc:
            raise LLMError(f"Ollama request failed: {type(exc).__name__}") from exc
