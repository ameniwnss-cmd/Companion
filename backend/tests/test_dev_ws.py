import json
from collections.abc import Iterator, Sequence
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.testclient import WebSocketTestSession
from starlette.websockets import WebSocketDisconnect

from companion.api.dev_ws import RATE_LIMITED
from companion.config import Environment, Settings
from companion.db.models import Reminder, User
from companion.db.session import SessionFactory
from companion.llm import ChatMessage, LLMReply, RateLimitedError, ToolCall
from companion.llm.fake import FakeLLM
from companion.main import create_app

REMINDER_CALL = ToolCall(
    "add_tasks_and_reminders", '{"reminders": [{"title": "call mom", "when": "tomorrow at 6pm"}]}'
)


def assistant(messages: Sequence[ChatMessage], json_mode: bool) -> str | LLMReply:
    if json_mode:
        return '{"mode": "normal"}'
    if "remind me" in messages[-1].content:
        return LLMReply(text="", tool_calls=(REMINDER_CALL,))
    return "Nice, keep going."


@pytest.fixture
def ws(settings: Settings, sessions: SessionFactory) -> Iterator[WebSocketTestSession]:
    app = create_app(settings, llm=FakeLLM(responder=assistant))
    with TestClient(app) as client, client.websocket_connect("/dev/ws?tz=Europe/Paris") as socket:
        yield socket


def send(ws: WebSocketTestSession, **event: Any) -> None:
    ws.send_text(json.dumps(event))


def receive(ws: WebSocketTestSession) -> dict[str, Any]:
    event: dict[str, Any] = json.loads(ws.receive_text())
    return event


def receive_turn(ws: WebSocketTestSession) -> list[dict[str, Any]]:
    events = [receive(ws)]
    while events[-1] != {"type": "status", "state": "idle"}:
        events.append(receive(ws))
    assert events[0] == {"type": "status", "state": "thinking"}
    return events[1:-1]


async def saved_reminders(sessions: SessionFactory) -> list[Reminder]:
    async with sessions() as session:
        return list(await session.scalars(select(Reminder)))


def test_a_message_gets_thinking_reply_idle(ws: WebSocketTestSession) -> None:
    send(ws, type="user_message", text="I went to the gym!")

    [reply] = receive_turn(ws)
    assert reply == {
        "type": "assistant_message",
        "text": "Nice, keep going.",
        "mode": "normal",
        "teasing_allowed": True,
    }


async def test_a_reminder_is_proposed_then_saved_when_the_user_says_yes(
    ws: WebSocketTestSession, sessions: SessionFactory
) -> None:
    send(ws, type="user_message", text="remind me to call mom tomorrow at 6pm")
    question, pending = receive_turn(ws)

    assert question["text"].startswith("Got it, a reminder to call mom, tomorrow at")
    assert pending["type"] == "pending_action"
    [item] = pending["items"]
    assert item["kind"] == "reminder"
    assert item["summary"].startswith("a reminder to call mom, tomorrow at")
    assert await saved_reminders(sessions) == []

    send(ws, type="user_message", text="yes")
    resolved, saved = receive_turn(ws)

    assert saved["text"] == "Saved. I'll remind you."
    assert resolved == {"type": "action_resolved", "id": pending["id"], "status": "confirmed"}
    assert [r.title for r in await saved_reminders(sessions)] == ["call mom"]


async def test_the_confirmation_card_can_cancel(
    ws: WebSocketTestSession, sessions: SessionFactory
) -> None:
    send(ws, type="user_message", text="remind me to call mom tomorrow at 6pm")
    _, pending = receive_turn(ws)

    send(ws, type="resolve_action", id=pending["id"], confirm=False)
    message, resolved = receive_turn(ws)

    assert message["text"] == "Okay, I scrapped it."
    assert resolved["status"] == "cancelled"
    assert await saved_reminders(sessions) == []


async def test_the_undo_button_takes_back_a_saved_action(
    ws: WebSocketTestSession, sessions: SessionFactory
) -> None:
    send(ws, type="user_message", text="remind me to call mom tomorrow at 6pm")
    _, pending = receive_turn(ws)
    send(ws, type="resolve_action", id=pending["id"], confirm=True)
    receive_turn(ws)
    assert [r.title for r in await saved_reminders(sessions)] == ["call mom"]

    send(ws, type="undo_action", id=pending["id"])
    message, resolved = receive_turn(ws)

    assert message["text"] == "Done, I took it back."
    assert resolved == {"type": "action_resolved", "id": pending["id"], "status": "undone"}
    assert await saved_reminders(sessions) == []


def test_undoing_an_unknown_action_is_an_error(ws: WebSocketTestSession) -> None:
    send(ws, type="undo_action", id="00000000-0000-0000-0000-000000000000")

    assert receive_turn(ws) == [{"type": "error", "detail": "That action doesn't exist"}]


def test_resolving_an_unknown_action_is_an_error(ws: WebSocketTestSession) -> None:
    send(ws, type="resolve_action", id="00000000-0000-0000-0000-000000000000", confirm=True)

    assert receive_turn(ws) == [{"type": "error", "detail": "That action doesn't exist"}]


async def test_the_users_timezone_comes_from_the_connection(
    ws: WebSocketTestSession, sessions: SessionFactory
) -> None:
    async with sessions() as session:
        user = await session.scalar(select(User))
    assert user is not None
    assert user.timezone == "Europe/Paris"


@pytest.mark.parametrize(
    "payload",
    ["not json", json.dumps({"type": "hack"}), json.dumps({"type": "user_message", "text": ""})],
)
def test_invalid_messages_get_an_error_and_the_socket_stays_open(
    ws: WebSocketTestSession, payload: str
) -> None:
    ws.send_text(payload)
    assert receive(ws) == {"type": "error", "detail": "Invalid message"}

    send(ws, type="user_message", text="still there?")
    assert receive(ws)["state"] == "thinking"


def test_whitespace_only_text_is_rejected(ws: WebSocketTestSession) -> None:
    send(ws, type="user_message", text="   ")

    assert receive_turn(ws) == [{"type": "error", "detail": "Message is empty"}]


def test_a_provider_outage_is_reported_without_details(
    settings: Settings, sessions: SessionFactory
) -> None:
    app = create_app(settings, llm=FakeLLM(fail=True))
    with TestClient(app) as client, client.websocket_connect("/dev/ws") as ws:
        send(ws, type="user_message", text="hello")

        assert receive_turn(ws) == [
            {"type": "error", "detail": "The companion is unavailable right now"}
        ]


@pytest.mark.parametrize(
    "settings_override",
    [
        {"environment": Environment.DEVELOPMENT, "dev_text_channel": False},
        {"environment": Environment.PRODUCTION, "dev_text_channel": True},
    ],
)
def test_the_dev_channel_does_not_exist_when_disabled(settings_override: dict[str, Any]) -> None:
    settings = Settings(**settings_override, reminder_loop_enabled=False, _env_file=None)

    with (
        TestClient(create_app(settings, llm=FakeLLM())) as client,
        pytest.raises(WebSocketDisconnect),
    ):
        client.websocket_connect("/dev/ws").__enter__()


def test_a_rate_limit_gets_a_friendly_message(settings: Settings, sessions: SessionFactory) -> None:
    def limited(_messages: Sequence[ChatMessage], json_mode: bool) -> str:
        if json_mode:
            return '{"mode": "normal"}'
        raise RateLimitedError("slow down")

    app = create_app(settings, llm=FakeLLM(responder=limited))
    with TestClient(app) as client, client.websocket_connect("/dev/ws") as ws:
        send(ws, type="user_message", text="hello")

        assert receive_turn(ws) == [{"type": "error", "detail": RATE_LIMITED}]
