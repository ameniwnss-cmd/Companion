import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession

from companion.api.dev_ws import NOT_HEARD, TOO_LONG
from companion.config import Settings
from companion.db.session import SessionFactory
from companion.llm.fake import FakeLLM
from companion.main import create_app
from companion.speech.stt import FakeSpeechToText, SpeechError
from companion.speech.tts import FakeTextToSpeech

WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 64
REPLY = "Three times? Look at you. Let's make it four."


def two_sentence_llm() -> FakeLLM:
    return FakeLLM(responder=lambda _m, json_mode: '{"mode": "normal"}' if json_mode else REPLY)


class BrokenEars:
    async def transcribe(self, audio: bytes) -> str:
        raise SpeechError("mic garbage")


def connect(
    settings: Settings, *, listener: Any = None, speak: bool = False
) -> Iterator[tuple[WebSocketTestSession, FakeTextToSpeech]]:
    voice = FakeTextToSpeech()
    app = create_app(
        settings,
        llm=two_sentence_llm(),
        listener=listener or FakeSpeechToText("I went to the gym three times"),
        voice=voice,
    )
    url = "/dev/ws?speak=true" if speak else "/dev/ws"
    with TestClient(app) as client, client.websocket_connect(url) as ws:
        yield ws, voice


@pytest.fixture
def quiet(
    settings: Settings, sessions: SessionFactory
) -> Iterator[tuple[WebSocketTestSession, FakeTextToSpeech]]:
    yield from connect(settings)


@pytest.fixture
def speaking(
    settings: Settings, sessions: SessionFactory
) -> Iterator[tuple[WebSocketTestSession, FakeTextToSpeech]]:
    yield from connect(settings, speak=True)


def turn(ws: WebSocketTestSession) -> list[dict[str, Any] | bytes]:
    events: list[dict[str, Any] | bytes] = []
    while True:
        message = ws.receive()
        if message.get("bytes") is not None:
            events.append(message["bytes"])
            continue
        event: dict[str, Any] = json.loads(message["text"])
        events.append(event)
        if event == {"type": "status", "state": "idle"}:
            return events


def test_a_recording_is_transcribed_captioned_and_answered(
    quiet: tuple[WebSocketTestSession, FakeTextToSpeech],
) -> None:
    ws, voice = quiet

    ws.send_bytes(WEBM)
    events = turn(ws)

    assert events[0] == {"type": "status", "state": "thinking"}
    assert events[1] == {"type": "user_transcript", "text": "I went to the gym three times"}
    assert isinstance(events[2], dict)
    assert events[2]["type"] == "assistant_message"
    assert events[2]["text"] == REPLY
    assert not any(isinstance(e, bytes) for e in events)
    assert voice.spoken == []


def test_with_speak_on_the_reply_starts_with_a_short_lead_clip(
    speaking: tuple[WebSocketTestSession, FakeTextToSpeech],
) -> None:
    ws, voice = speaking

    ws.send_bytes(WEBM)
    events = turn(ws)

    assert {"type": "status", "state": "speaking"} in events
    audio = [e for e in events if isinstance(e, bytes)]
    assert all(clip.startswith(b"RIFF") for clip in audio)
    assert voice.spoken == ["Three times? Look at you.", "Let's make it four."]


def test_typed_messages_are_spoken_too_when_speak_is_on(
    speaking: tuple[WebSocketTestSession, FakeTextToSpeech],
) -> None:
    ws, _ = speaking

    ws.send_text(json.dumps({"type": "user_message", "text": "hey"}))
    events = turn(ws)

    assert len([e for e in events if isinstance(e, bytes)]) == 2


def test_a_recording_that_is_too_long_is_refused(
    settings: Settings, sessions: SessionFactory
) -> None:
    small = settings.model_copy(update={"max_audio_bytes": 10})
    for ws, _ in connect(small):
        ws.send_bytes(WEBM)

        assert json.loads(ws.receive_text()) == {"type": "error", "detail": TOO_LONG}


@pytest.mark.parametrize("listener", [FakeSpeechToText(""), BrokenEars()])
def test_silence_or_a_failed_transcription_asks_to_try_again(
    settings: Settings, sessions: SessionFactory, listener: Any
) -> None:
    for ws, _ in connect(settings, listener=listener):
        ws.send_bytes(WEBM)

        assert turn(ws) == [
            {"type": "status", "state": "thinking"},
            {"type": "error", "detail": NOT_HEARD},
            {"type": "status", "state": "idle"},
        ]
