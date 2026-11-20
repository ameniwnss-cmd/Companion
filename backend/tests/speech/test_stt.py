import httpx
import pytest

from companion.speech.stt import FakeSpeechToText, GroqSpeechToText, SpeechError, audio_format

WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 32
API_KEY = "gsk_test_secret"


@pytest.mark.parametrize(
    ("audio", "expected"),
    [
        (WEBM, ("webm", "audio/webm")),
        (b"OggS" + b"\x00" * 8, ("ogg", "audio/ogg")),
        (b"RIFF" + b"\x00" * 8, ("wav", "audio/wav")),
        (b"ID3" + b"\x00" * 8, ("mp3", "audio/mpeg")),
        (b"\x00\x00\x00\x20ftypM4A ", ("m4a", "audio/mp4")),
        (b"hello there", None),
        (b"", None),
    ],
)
def test_audio_format_is_detected_from_the_bytes(
    audio: bytes, expected: tuple[str, str] | None
) -> None:
    assert audio_format(audio) == expected


def groq(handler: httpx.MockTransport) -> GroqSpeechToText:
    return GroqSpeechToText(
        httpx.AsyncClient(transport=handler),
        api_key=API_KEY,
        model="whisper-test",
        base_url="https://groq.test/v1",
    )


async def test_groq_uploads_the_recording_and_returns_clean_text() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"text": "  Remind me to call mom. "})

    text = await groq(httpx.MockTransport(handler)).transcribe(WEBM)

    assert text == "Remind me to call mom."
    request = seen[0]
    assert str(request.url) == "https://groq.test/v1/audio/transcriptions"
    assert request.headers["authorization"] == f"Bearer {API_KEY}"
    body = request.content
    assert b'name="model"\r\n\r\nwhisper-test' in body
    assert b'name="language"\r\n\r\nen' in body
    assert b'filename="speech.webm"' in body
    assert WEBM in body


async def test_unknown_audio_is_rejected_without_a_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request expected")

    with pytest.raises(SpeechError):
        await groq(httpx.MockTransport(handler)).transcribe(b"not audio")


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(429, json={"error": "slow down"}),
        httpx.Response(200, json={"nope": True}),
        httpx.Response(200, json={"text": 42}),
        httpx.Response(200, content=b"not json"),
    ],
)
async def test_failures_raise_without_leaking_the_key(response: httpx.Response) -> None:
    with pytest.raises(SpeechError) as exc_info:
        await groq(httpx.MockTransport(lambda _: response)).transcribe(WEBM)

    assert API_KEY not in str(exc_info.value)


async def test_the_fake_records_what_it_heard() -> None:
    fake = FakeSpeechToText("hello")

    assert await fake.transcribe(WEBM) == "hello"
    assert fake.received == [WEBM]
