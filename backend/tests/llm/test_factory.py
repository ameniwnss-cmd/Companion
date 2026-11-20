from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from companion.config import (
    LLMProviderName,
    Settings,
    SpeechToTextProviderName,
    TextToSpeechProviderName,
)
from companion.llm.factory import build_llm, build_speech_to_text, build_text_to_speech
from companion.llm.fake import FakeLLM
from companion.llm.groq import GroqLLM
from companion.llm.ollama import OllamaLLM
from companion.speech.stt import FakeSpeechToText, GroqSpeechToText
from companion.speech.tts import FakeTextToSpeech, KokoroTextToSpeech


@pytest.mark.parametrize(
    ("provider", "expected"),
    [
        (LLMProviderName.FAKE, FakeLLM),
        (LLMProviderName.OLLAMA, OllamaLLM),
        (LLMProviderName.GROQ, GroqLLM),
    ],
)
def test_builds_the_configured_provider(provider: LLMProviderName, expected: type) -> None:
    settings = Settings(llm_provider=provider, groq_api_key=SecretStr("k"), _env_file=None)

    assert isinstance(build_llm(settings, httpx.AsyncClient()), expected)


@pytest.mark.parametrize("api_key", [None, SecretStr(""), SecretStr("   ")])
def test_groq_without_an_api_key_fails_at_startup(api_key: SecretStr | None) -> None:
    settings = Settings(llm_provider=LLMProviderName.GROQ, groq_api_key=api_key, _env_file=None)

    with pytest.raises(ValueError, match="GROQ_API_KEY"):
        build_llm(settings, httpx.AsyncClient())


def test_groq_speech_to_text_needs_the_key() -> None:
    settings = Settings(
        stt_provider=SpeechToTextProviderName.GROQ, groq_api_key=None, _env_file=None
    )

    with pytest.raises(ValueError, match="STT_PROVIDER=groq requires GROQ_API_KEY"):
        build_speech_to_text(settings, httpx.AsyncClient())


def test_speech_providers_are_built_from_settings(tmp_path: Path) -> None:
    model, voices = tmp_path / "m.onnx", tmp_path / "v.bin"
    model.touch()
    voices.touch()
    settings = Settings(
        stt_provider=SpeechToTextProviderName.GROQ,
        groq_api_key=SecretStr("k"),
        tts_provider=TextToSpeechProviderName.KOKORO,
        kokoro_model_path=model,
        kokoro_voices_path=voices,
        _env_file=None,
    )

    assert isinstance(build_speech_to_text(settings, httpx.AsyncClient()), GroqSpeechToText)
    assert isinstance(build_text_to_speech(settings), KokoroTextToSpeech)
    defaults = Settings(_env_file=None)
    assert isinstance(build_speech_to_text(defaults, httpx.AsyncClient()), FakeSpeechToText)
    assert isinstance(build_text_to_speech(defaults), FakeTextToSpeech)


def test_kokoro_without_model_files_fails_at_startup(tmp_path: Path) -> None:
    settings = Settings(
        tts_provider=TextToSpeechProviderName.KOKORO,
        kokoro_model_path=tmp_path / "missing.onnx",
        _env_file=None,
    )

    with pytest.raises(ValueError, match=r"missing.onnx"):
        build_text_to_speech(settings)
