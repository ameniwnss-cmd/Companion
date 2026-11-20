import json
from typing import Any

import httpx
import pytest

from companion.llm import ChatMessage, LLMError, LLMReply, Role, ToolCall, ToolSpec
from companion.llm.ollama import OllamaLLM

MESSAGES = [ChatMessage(Role.USER, "hi")]


def make_llm(handler: httpx.MockTransport) -> OllamaLLM:
    return OllamaLLM(
        httpx.AsyncClient(transport=handler), base_url="http://ollama.test/", model="qwen-test"
    )


async def test_sends_a_non_streaming_chat_request() -> None:
    bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://ollama.test/api/chat"
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "yo"}})

    reply = await make_llm(httpx.MockTransport(handler)).chat(
        MESSAGES, temperature=0.2, max_tokens=64
    )

    assert reply == LLMReply(text="yo")
    assert bodies[0] == {
        "model": "qwen-test",
        "messages": [{"role": "user", "content": "hi"}],
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": 64},
    }


async def test_json_mode_sets_the_format() -> None:
    bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": "{}"}})

    await make_llm(httpx.MockTransport(handler)).chat(MESSAGES, json_mode=True)

    assert bodies[0]["format"] == "json"


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500),
        httpx.Response(200, json={"no": "message"}),
        httpx.Response(200, json={"message": {"content": 42}}),
    ],
)
async def test_failures_raise(response: httpx.Response) -> None:
    with pytest.raises(LLMError):
        await make_llm(httpx.MockTransport(lambda _: response)).chat(MESSAGES)


async def test_tool_calls_are_returned_with_arguments_as_json_text() -> None:
    bodies: list[dict[str, Any]] = []
    tool = ToolSpec("create_task", "Add a task.", {"type": "object"})

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        message = {
            "content": "",
            "tool_calls": [{"function": {"name": "create_task", "arguments": {"title": "milk"}}}],
        }
        return httpx.Response(200, json={"message": message})

    reply = await make_llm(httpx.MockTransport(handler)).chat(MESSAGES, tools=[tool])

    assert reply.tool_calls == (ToolCall("create_task", '{"title": "milk"}'),)
    assert bodies[0]["tools"][0]["function"]["name"] == "create_task"
