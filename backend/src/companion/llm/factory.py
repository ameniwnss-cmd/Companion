import httpx

from companion.config import (
    EmbeddingProviderName,
    LLMProviderName,
    Settings,
    SpeechToTextProviderName,
    TextToSpeechProviderName,
)
from companion.embeddings import Embedder, FakeEmbedder, OllamaEmbedder
from companion.llm.base import LLMProvider
from companion.llm.fake import FakeLLM
from companion.llm.groq import GroqLLM
from companion.llm.ollama import OllamaLLM
from companion.speech.stt import FakeSpeechToText, GroqSpeechToText, SpeechToText
from companion.speech.tts import FakeTextToSpeech, KokoroTextToSpeech, TextToSpeech


def build_llm(settings: Settings, http: httpx.AsyncClient) -> LLMProvider:
    match settings.llm_provider:
        case LLMProviderName.FAKE:
            return FakeLLM()
        case LLMProviderName.OLLAMA:
            return OllamaLLM(http, base_url=settings.ollama_base_url, model=settings.ollama_model)
        case LLMProviderName.GROQ:
            return GroqLLM(
                http,
                api_key=_groq_key(settings, "LLM_PROVIDER"),
                model=settings.groq_model,
                base_url=settings.groq_base_url,
            )


def build_embedder(settings: Settings, http: httpx.AsyncClient) -> Embedder:
    match settings.embedding_provider:
        case EmbeddingProviderName.FAKE:
            return FakeEmbedder()
        case EmbeddingProviderName.OLLAMA:
            return OllamaEmbedder(
                http, base_url=settings.ollama_base_url, model=settings.ollama_embedding_model
            )


def build_speech_to_text(settings: Settings, http: httpx.AsyncClient) -> SpeechToText:
    match settings.stt_provider:
        case SpeechToTextProviderName.FAKE:
            return FakeSpeechToText()
        case SpeechToTextProviderName.GROQ:
            return GroqSpeechToText(
                http,
                api_key=_groq_key(settings, "STT_PROVIDER"),
                model=settings.groq_stt_model,
                base_url=settings.groq_base_url,
            )


def build_text_to_speech(settings: Settings) -> TextToSpeech:
    match settings.tts_provider:
        case TextToSpeechProviderName.FAKE:
            return FakeTextToSpeech()
        case TextToSpeechProviderName.KOKORO:
            missing = [
                p
                for p in (settings.kokoro_model_path, settings.kokoro_voices_path)
                if not p.exists()
            ]
            if missing:
                raise ValueError(
                    f"TTS_PROVIDER=kokoro needs model files: {', '.join(map(str, missing))}"
                )
            return KokoroTextToSpeech(
                model_path=settings.kokoro_model_path,
                voices_path=settings.kokoro_voices_path,
                voice=settings.kokoro_voice,
                speed=settings.kokoro_speed,
            )


def _groq_key(settings: Settings, setting: str) -> str:
    api_key = settings.groq_api_key.get_secret_value() if settings.groq_api_key else ""
    if not api_key.strip():
        raise ValueError(f"{setting}=groq requires GROQ_API_KEY to be set")
    return api_key
