import asyncio
import os
from collections.abc import AsyncIterator

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from companion.config import BACKEND_ROOT, Environment, Settings
from companion.conversation.personality import Personality
from companion.db.models import Base, User
from companion.db.session import SessionFactory, create_session_factory
from companion.llm.fake import FakeLLM
from companion.main import create_app
from companion.users import get_or_create_user

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://companion:companion@localhost:5433/companion_test"
)


async def _create_database_if_missing(url: str) -> None:
    name = make_url(url).database
    admin = create_async_engine(
        make_url(url).set(database="postgres"), isolation_level="AUTOCOMMIT", poolclass=NullPool
    )
    async with admin.connect() as connection:
        exists = await connection.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name}
        )
        if not exists:
            await connection.execute(text(f'CREATE DATABASE "{name}"'))
    await admin.dispose()


@pytest.fixture(scope="session")
def database_url() -> str:
    asyncio.run(_create_database_if_missing(TEST_DATABASE_URL))
    config = Config(BACKEND_ROOT / "alembic.ini")
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")
    return TEST_DATABASE_URL


@pytest.fixture
async def sessions(database_url: str) -> AsyncIterator[SessionFactory]:
    engine = create_async_engine(database_url, poolclass=NullPool)
    yield create_session_factory(engine)
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {tables} CASCADE"))
    await engine.dispose()


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
