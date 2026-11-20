import json

import httpx
import pytest

from companion.llm import (
    ChatMessage,
    LLMError,
    LLMReply,
    RateLimitedError,
    Role,
    ToolCall,
    ToolCallError,
    ToolSpec,
)
from companion.llm.groq import GroqLLM

API_KEY = "gsk_test_secret"
MESSAGES = [ChatMessage(Role.SYSTEM, "be nice"), ChatMessage(Role.USER, "hi")]


def make_llm(handler: httpx.MockTransport, model: str = "openai/gpt-oss-120b") -> GroqLLM:
    http = httpx.AsyncClient(transport=handler)
    return GroqLLM(http, api_key=API_KEY, model=model, base_url="https://groq.test/v1/")


def completion(content: object) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


async def test_sends_an_openai_compatible_request_and_returns_the_text() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return completion("hey you")

    reply = await make_llm(httpx.MockTransport(handler)).chat(MESSAGES, temperature=0.3)

    assert reply == LLMReply(text="hey you")
    request = seen[0]
    assert str(request.url) == "https://groq.test/v1/chat/completions"
    assert request.headers["authorization"] == f"Bearer {API_KEY}"
    body = json.loads(request.content)
    assert body["model"] == "openai/gpt-oss-120b"
    assert body["temperature"] == 0.3
    assert body["messages"] == [
        {"role": "system", "content": "be nice"},
        {"role": "user", "content": "hi"},
    ]
    assert body["reasoning_effort"] == "low"
    assert "response_format" not in body


async def test_json_mode_requests_a_json_object() -> None:
    bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return completion('{"mode": "normal"}')

    await make_llm(httpx.MockTransport(handler)).chat(MESSAGES, json_mode=True)

    assert bodies[0]["response_format"] == {"type": "json_object"}


async def test_non_reasoning_models_get_no_reasoning_effort() -> None:
    bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return completion("ok")

    await make_llm(httpx.MockTransport(handler), model="qwen/qwen3-32b").chat(MESSAGES)

    assert "reasoning_effort" not in bodies[0]


async def test_http_errors_raise_without_leaking_the_api_key() -> None:
    llm = make_llm(httpx.MockTransport(lambda _: httpx.Response(503, json={"error": "overloaded"})))

    with pytest.raises(LLMError) as exc_info:
        await llm.chat(MESSAGES)

    assert "503" in str(exc_info.value)
    assert API_KEY not in str(exc_info.value)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, json={"unexpected": "shape"}),
        httpx.Response(200, content=b"not json"),
        completion(42),
    ],
)
async def test_unusable_responses_raise(response: httpx.Response) -> None:
    llm = make_llm(httpx.MockTransport(lambda _: response))

    with pytest.raises(LLMError):
        await llm.chat(MESSAGES)


async def test_network_failures_raise() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    with pytest.raises(LLMError):
        await make_llm(httpx.MockTransport(handler)).chat(MESSAGES)


TOOL = ToolSpec("create_reminder", "Remind the user.", {"type": "object", "properties": {}})


async def test_tools_are_offered_and_tool_calls_are_returned() -> None:
    bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        message = {
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "create_reminder", "arguments": '{"title": "x"}'},
                }
            ],
        }
        return httpx.Response(200, json={"choices": [{"message": message}]})

    reply = await make_llm(httpx.MockTransport(handler)).chat(MESSAGES, tools=[TOOL])

    assert reply == LLMReply(text="", tool_calls=(ToolCall("create_reminder", '{"title": "x"}'),))
    assert bodies[0]["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "create_reminder",
                "description": "Remind the user.",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]


async def test_no_tools_key_is_sent_when_no_tools_are_offered() -> None:
    bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return completion("ok")

    await make_llm(httpx.MockTransport(handler)).chat(MESSAGES)

    assert "tools" not in bodies[0]


async def test_a_reply_with_no_text_is_an_empty_string() -> None:
    llm = make_llm(httpx.MockTransport(lambda _: completion(None)))

    assert await llm.chat(MESSAGES) == LLMReply(text="")


async def test_a_rejected_tool_call_raises_a_tool_call_error() -> None:
    rejected = httpx.Response(
        400, json={"error": {"code": "tool_use_failed", "message": "did not match schema"}}
    )

    with pytest.raises(ToolCallError):
        await make_llm(httpx.MockTransport(lambda _: rejected)).chat(MESSAGES, tools=[TOOL])


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(400, json={"error": {"code": "invalid_request"}}),
        httpx.Response(400, content=b"not json"),
        httpx.Response(500, json={"error": {"code": "tool_use_failed"}}),
    ],
)
async def test_other_errors_are_not_tool_call_errors(response: httpx.Response) -> None:
    with pytest.raises(LLMError) as exc_info:
        await make_llm(httpx.MockTransport(lambda _: response)).chat(MESSAGES)

    assert not isinstance(exc_info.value, ToolCallError)


class Sleeper:
    def __init__(self) -> None:
        self.waits: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.waits.append(seconds)


def rate_limited(retry_after: str | None) -> httpx.Response:
    headers = {"retry-after": retry_after} if retry_after is not None else {}
    return httpx.Response(429, headers=headers, json={"error": {"code": "rate_limit_exceeded"}})


async def test_a_short_rate_limit_is_waited_out_and_retried_once() -> None:
    responses = [rate_limited("1.5"), completion("made it")]
    sleeper = Sleeper()
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: responses.pop(0)))
    llm = GroqLLM(http, api_key=API_KEY, model="m", base_url="https://groq.test/v1", sleep=sleeper)

    assert await llm.chat(MESSAGES) == LLMReply(text="made it")
    assert sleeper.waits == [1.5]


@pytest.mark.parametrize("retry_after", ["30", None, "soon"])
async def test_a_long_or_unknown_rate_limit_is_reported(retry_after: str | None) -> None:
    sleeper = Sleeper()
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: rate_limited(retry_after)))
    llm = GroqLLM(http, api_key=API_KEY, model="m", base_url="https://groq.test/v1", sleep=sleeper)

    with pytest.raises(RateLimitedError):
        await llm.chat(MESSAGES)
    assert sleeper.waits == []


async def test_a_second_rate_limit_after_waiting_is_reported() -> None:
    sleeper = Sleeper()
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: rate_limited("1")))
    llm = GroqLLM(http, api_key=API_KEY, model="m", base_url="https://groq.test/v1", sleep=sleeper)

    with pytest.raises(RateLimitedError):
        await llm.chat(MESSAGES)
    assert sleeper.waits == [1.0]
