import asyncio
import io
import logging
import re
import wave
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import numpy as np

if TYPE_CHECKING:
    from kokoro_onnx import Kokoro

logger = logging.getLogger(__name__)

SAMPLE_RATE = 24_000
PAUSE_AFTER_CLIP_SECONDS = 0.2
MIN_LEAD_WORDS = 4
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


class TextToSpeech(Protocol):
    async def synthesize(self, text: str) -> bytes: ...

    async def warm_up(self) -> None: ...


def speech_clips(text: str) -> list[str]:
    sentences = [s for s in (p.strip() for p in _SENTENCE_END.split(text)) if s]
    lead: list[str] = []
    while sentences and sum(len(s.split()) for s in lead) < MIN_LEAD_WORDS:
        lead.append(sentences.pop(0))
    return [" ".join(part) for part in (lead, sentences) if part]


def to_wav(samples: np.ndarray, sample_rate: int) -> bytes:
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        writer.writeframes(pcm.tobytes())
    return buffer.getvalue()


class FakeTextToSpeech:
    def __init__(self) -> None:
        self.spoken: list[str] = []

    async def synthesize(self, text: str) -> bytes:
        self.spoken.append(text)
        return to_wav(np.zeros(SAMPLE_RATE // 10, dtype=np.float32), SAMPLE_RATE)

    async def warm_up(self) -> None:
        return None


class KokoroTextToSpeech:
    def __init__(self, *, model_path: Path, voices_path: Path, voice: str, speed: float) -> None:
        self._model_path = model_path
        self._voices_path = voices_path
        self._voice = voice
        self._speed = speed
        self._engine: Kokoro | None = None
        self._lock = asyncio.Lock()

    async def _load(self) -> "Kokoro":
        async with self._lock:
            if self._engine is None:
                from kokoro_onnx import Kokoro

                self._engine = await asyncio.to_thread(
                    Kokoro, str(self._model_path), str(self._voices_path)
                )
            return self._engine

    async def warm_up(self) -> None:
        try:
            await self.synthesize("Hi.")
        except Exception:
            logger.exception("Warming up the voice failed")

    async def synthesize(self, text: str) -> bytes:
        engine = await self._load()
        samples, sample_rate = await asyncio.to_thread(
            engine.create, text, voice=self._voice, speed=self._speed, lang="en-us"
        )
        pause = np.zeros(int(sample_rate * PAUSE_AFTER_CLIP_SECONDS), dtype=samples.dtype)
        return to_wav(np.concatenate([samples, pause]), sample_rate)
