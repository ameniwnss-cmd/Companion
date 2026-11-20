from typing import Protocol

import httpx


class SpeechError(Exception):
    pass


class SpeechToText(Protocol):
    async def transcribe(self, audio: bytes) -> str: ...


_CONTAINERS = (
    (b"\x1a\x45\xdf\xa3", "webm", "audio/webm"),
    (b"OggS", "ogg", "audio/ogg"),
    (b"RIFF", "wav", "audio/wav"),
    (b"ID3", "mp3", "audio/mpeg"),
    (b"\xff\xfb", "mp3", "audio/mpeg"),
)


def audio_format(audio: bytes) -> tuple[str, str] | None:
    for magic, extension, mime_type in _CONTAINERS:
        if audio.startswith(magic):
            return extension, mime_type
    if audio[4:8] == b"ftyp":
        return "m4a", "audio/mp4"
    return None


class FakeSpeechToText:
    def __init__(self, transcript: str = "I went to the gym today") -> None:
        self.transcript = transcript
        self.received: list[bytes] = []

    async def transcribe(self, audio: bytes) -> str:
        self.received.append(audio)
        return self.transcript


class GroqSpeechToText:
    def __init__(self, http: httpx.AsyncClient, *, api_key: str, model: str, base_url: str) -> None:
        self._http = http
        self._url = f"{base_url.rstrip('/')}/audio/transcriptions"
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._model = model

    async def transcribe(self, audio: bytes) -> str:
        detected = audio_format(audio)
        if detected is None:
            raise SpeechError("Unsupported audio format")
        extension, mime_type = detected
        try:
            response = await self._http.post(
                self._url,
                headers=self._headers,
                data={"model": self._model, "language": "en", "response_format": "json"},
                files={"file": (f"speech.{extension}", audio, mime_type)},
            )
            response.raise_for_status()
            text = response.json()["text"]
        except httpx.HTTPStatusError as exc:
            raise SpeechError(f"Groq returned HTTP {exc.response.status_code}") from exc
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise SpeechError(f"Transcription failed: {type(exc).__name__}") from exc
        if not isinstance(text, str):
            raise SpeechError("Transcription was not text")
        return text.strip()
