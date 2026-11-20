from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class EmbeddingProviderName(StrEnum):
    FAKE = "fake"
    OLLAMA = "ollama"


class SpeechToTextProviderName(StrEnum):
    FAKE = "fake"
    GROQ = "groq"


class TextToSpeechProviderName(StrEnum):
    FAKE = "fake"
    KOKORO = "kokoro"


class LLMProviderName(StrEnum):
    FAKE = "fake"
    OLLAMA = "ollama"
    GROQ = "groq"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Environment = Environment.DEVELOPMENT
    log_level: str = "INFO"

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:4200"])

    database_url: str = "postgresql+asyncpg://companion:companion@localhost:5433/companion"

    dev_text_channel: bool = False
    dev_user_email: str = "dev@companion.local"

    llm_provider: LLMProviderName = LLMProviderName.FAKE
    llm_timeout_seconds: float = 30.0
    groq_api_key: SecretStr | None = None
    groq_model: str = "openai/gpt-oss-120b"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:4b-instruct-2507-q4_K_M"

    embedding_provider: EmbeddingProviderName = EmbeddingProviderName.FAKE
    ollama_embedding_model: str = "all-minilm"
    memory_extraction_enabled: bool = True

    stt_provider: SpeechToTextProviderName = SpeechToTextProviderName.FAKE
    groq_stt_model: str = "whisper-large-v3-turbo"
    max_audio_bytes: int = 5_000_000
    tts_provider: TextToSpeechProviderName = TextToSpeechProviderName.FAKE
    kokoro_model_path: Path = BACKEND_ROOT / ".models" / "kokoro" / "kokoro-v1.0.int8.onnx"
    kokoro_voices_path: Path = BACKEND_ROOT / ".models" / "kokoro" / "voices-v1.0.bin"
    kokoro_voice: str = "bm_fable"
    kokoro_speed: float = 1.1

    personality_path: Path = BACKEND_ROOT / "config" / "personality.md"

    reminder_loop_enabled: bool = True
    reminder_poll_seconds: float = 30.0

    @property
    def dev_text_channel_enabled(self) -> bool:
        return self.dev_text_channel and self.environment is not Environment.PRODUCTION


@lru_cache
def get_settings() -> Settings:
    return Settings()
