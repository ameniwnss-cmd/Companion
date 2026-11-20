import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

import httpx

from companion.llm.base import (
    ChatMessage,
    LLMError,
    LLMReply,
    RateLimitedError,
    ToolCall,
    ToolCallError,
    ToolSpec,
    openai_tools,
)

MAX_RATE_LIMIT_WAIT_SECONDS = 5.0


class GroqLLM:
    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        api_key: str,
        model: str,
        base_url: str,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._http = http
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._model = model
        self._sleep = sleep

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
            "temperature": temperature,
            "max_completion_tokens": max_tokens,
        }
        if self._model.startswith("openai/gpt-oss"):
            body["reasoning_effort"] = "low"
        if json_mode:
            # Strict json_schema mode has open bug reports on Groq. Callers validate the JSON.
            body["response_format"] = {"type": "json_object"}
        if tools:
            body["tools"] = openai_tools(tools)

        try:
            response = await self._post(body)
            response.raise_for_status()
            message = response.json()["choices"][0]["message"]
            return LLMReply(
                text=_as_text(message.get("content")),
                tool_calls=tuple(
                    ToolCall(
                        name=_as_text(call["function"]["name"]),
                        arguments=_as_text(call["function"]["arguments"]),
                    )
                    for call in message.get("tool_calls") or []
                ),
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == httpx.codes.TOO_MANY_REQUESTS:
                raise RateLimitedError("Groq rate limit reached") from exc
            if _is_rejected_tool_call(exc.response):
                raise ToolCallError("Groq rejected a malformed tool call") from exc
            # Never put the request in the error message: its headers carry the API key.
            raise LLMError(f"Groq returned HTTP {exc.response.status_code}") from exc
        except (
            httpx.HTTPError,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
            AttributeError,
        ) as exc:
            raise LLMError(f"Groq request failed: {type(exc).__name__}") from exc

    async def _post(self, body: dict[str, Any]) -> httpx.Response:
        response = await self._http.post(self._url, json=body, headers=self._headers)
        wait = _retry_after(response)
        if wait is not None and wait <= MAX_RATE_LIMIT_WAIT_SECONDS:
            await self._sleep(wait)
            response = await self._http.post(self._url, json=body, headers=self._headers)
        return response


def _retry_after(response: httpx.Response) -> float | None:
    if response.status_code != httpx.codes.TOO_MANY_REQUESTS:
        return None
    try:
        return float(response.headers["retry-after"])
    except (KeyError, ValueError):
        return None


def _as_text(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise TypeError("expected text")
    return value


def _is_rejected_tool_call(response: httpx.Response) -> bool:
    if response.status_code != httpx.codes.BAD_REQUEST:
        return False
    try:
        return bool(response.json()["error"]["code"] == "tool_use_failed")
    except (ValueError, KeyError, TypeError):
        return False
