import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from companion import __version__
from companion.actions.service import ActionService
from companion.api import dev_memories, dev_plans, dev_ws, health
from companion.config import Settings, get_settings
from companion.conversation.personality import Personality
from companion.db.session import create_engine, create_session_factory
from companion.embeddings import Embedder
from companion.embeddings import warm_up as warm_up_embedder
from companion.llm import LLMProvider
from companion.llm.factory import (
    build_embedder,
    build_llm,
    build_speech_to_text,
    build_text_to_speech,
)
from companion.log_config import configure_logging
from companion.memory.service import MemoryService
from companion.performance import disable_power_throttling
from companion.plans.service import PlansService
from companion.realtime.hub import ConnectionHub
from companion.realtime.reminders import ReminderDispatcher
from companion.speech.stt import SpeechToText
from companion.speech.tts import TextToSpeech


def create_app(
    settings: Settings | None = None,
    *,
    llm: LLMProvider | None = None,
    embedder: Embedder | None = None,
    listener: SpeechToText | None = None,
    voice: TextToSpeech | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    personality = Personality.load(settings.personality_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        disable_power_throttling()
        engine = create_engine(settings.database_url)
        sessions = create_session_factory(engine)
        hub = ConnectionHub()
        app.state.sessions = sessions
        app.state.actions = ActionService(sessions)
        app.state.plans = PlansService(sessions)
        app.state.hub = hub
        app.state.reminders = ReminderDispatcher(sessions, hub)

        stop = asyncio.Event()
        loop_task = None
        if settings.reminder_loop_enabled:
            loop_task = asyncio.create_task(
                app.state.reminders.run(stop, settings.reminder_poll_seconds)
            )
        try:
            async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as http:
                app.state.llm = llm or build_llm(settings, http)
                memory_embedder = embedder or build_embedder(settings, http)
                app.state.memory = MemoryService(sessions, memory_embedder)
                app.state.listener = listener or build_speech_to_text(settings, http)
                app.state.voice = voice or build_text_to_speech(settings)
                warm_ups = asyncio.gather(
                    app.state.voice.warm_up(), warm_up_embedder(memory_embedder)
                )
                yield
                await warm_ups
        finally:
            stop.set()
            if loop_task is not None:
                await loop_task
            await engine.dispose()

    app = FastAPI(title="Voice Companion API", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.personality = personality

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    if settings.dev_text_channel_enabled:
        app.include_router(dev_ws.router)
        app.include_router(dev_memories.router)
        app.include_router(dev_plans.router)
    return app


app = create_app()
