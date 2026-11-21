import asyncio
import os
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from companion.config import Environment, Settings
from companion.conversation.personality import Personality
from companion.db.models import User
from companion.db.session import SessionFactory, create_session_factory
from companion.db.setup import create_database_if_missing, empty_database, migrate
from companion.llm.fake import FakeLLM
from companion.main import create_app
from companion.users import get_or_create_user

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://companion:companion@localhost:5433/companion_test"
)


@pytest.fixture(scope="session")
def database_url() -> str:
    asyncio.run(create_database_if_missing(TEST_DATABASE_URL))
    migrate(TEST_DATABASE_URL)
    return TEST_DATABASE_URL


@pytest.fixture
async def sessions(database_url: str) -> AsyncIterator[SessionFactory]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    yield create_session_factory(engine)
    await engine.dispose()
    await empty_database(database_url)


@pytest.fixture
async def user(sessions: SessionFactory) -> User:
    return await get_or_create_user(sessions, "ada@example.com", "Europe/Paris")


@pytest.fixture
def settings() -> Settings:
    return Settings(
        environment=Environment.TEST,
        dev_text_channel=True,
        database_url=TEST_DATABASE_URL,
        reminder_loop_enabled=False,
        _env_file=None,
    )


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def personality(settings: Settings) -> Personality:
    return Personality.load(settings.personality_path)


@pytest.fixture
def app(settings: Settings, fake_llm: FakeLLM) -> FastAPI:
    return create_app(settings, llm=fake_llm)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
