import asyncio
import io
import wave
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from companion.speech.tts import (
    PAUSE_AFTER_CLIP_SECONDS,
    SAMPLE_RATE,
    FakeTextToSpeech,
    KokoroTextToSpeech,
    speech_clips,
    to_wav,
)


@pytest.mark.parametrize(
    ("text", "clips"),
    [
        (
            "Nice work, three gym sessions already! When's the next one? Let's go.",
            ["Nice work, three gym sessions already!", "When's the next one? Let's go."],
        ),
        (
            "Bro! Three times this week? That's real consistency.",
            ["Bro! Three times this week?", "That's real consistency."],
        ),
        ("Saved. I'll remind you.", ["Saved. I'll remind you."]),
        ("One sentence only", ["One sentence only"]),
        ("  ", []),
    ],
)
def test_the_first_words_get_their_own_clip_so_speech_starts_sooner(
    text: str, clips: list[str]
) -> None:
    assert speech_clips(text) == clips


def test_to_wav_writes_16_bit_mono_and_clips_loud_samples() -> None:
    samples = np.array([0.0, 0.5, 2.0, -2.0], dtype=np.float32)

    with wave.open(io.BytesIO(to_wav(samples, SAMPLE_RATE))) as reader:
        assert (reader.getnchannels(), reader.getsampwidth(), reader.getframerate()) == (
            1,
            2,
            SAMPLE_RATE,
        )
        pcm = np.frombuffer(reader.readframes(4), dtype="<i2")
    assert pcm.tolist() == [0, 16383, 32767, -32767]


async def test_the_fake_returns_a_short_wav_and_records_text() -> None:
    fake = FakeTextToSpeech()

    audio = await fake.synthesize("hi")

    assert audio.startswith(b"RIFF")
    assert fake.spoken == ["hi"]


class FakeKokoro:
    loads = 0

    def __init__(self, model: str, voices: str) -> None:
        FakeKokoro.loads += 1
        self.paths = (model, voices)
        self.calls: list[dict[str, Any]] = []

    def create(self, text: str, **options: Any) -> tuple[np.ndarray, int]:
        self.calls.append({"text": text, **options})
        return np.zeros(240, dtype=np.float32), SAMPLE_RATE


async def test_kokoro_loads_once_and_uses_the_configured_voice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import kokoro_onnx

    FakeKokoro.loads = 0
    monkeypatch.setattr(kokoro_onnx, "Kokoro", FakeKokoro)
    voice = KokoroTextToSpeech(
        model_path=Path("model.onnx"), voices_path=Path("voices.bin"), voice="af_heart", speed=1.1
    )

    first, second = await asyncio.gather(voice.synthesize("Hi."), voice.synthesize("Bye."))

    assert first.startswith(b"RIFF")
    assert second.startswith(b"RIFF")
    assert FakeKokoro.loads == 1


async def test_each_clip_ends_with_a_short_natural_pause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import kokoro_onnx

    monkeypatch.setattr(kokoro_onnx, "Kokoro", FakeKokoro)
    voice = KokoroTextToSpeech(
        model_path=Path("m"), voices_path=Path("v"), voice="af_heart", speed=1.0
    )

    with wave.open(io.BytesIO(await voice.synthesize("Hi."))) as reader:
        frames = reader.getnframes()

    assert frames == 240 + int(SAMPLE_RATE * PAUSE_AFTER_CLIP_SECONDS)
