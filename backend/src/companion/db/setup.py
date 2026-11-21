from alembic import command
from alembic.config import Config
from sqlalchemy import make_url, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from companion.config import BACKEND_ROOT
from companion.db.models import Base


async def create_database_if_missing(url: str) -> None:
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


def migrate(url: str) -> None:
    config = Config(BACKEND_ROOT / "alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    config.attributes["configure_logger"] = False
    command.upgrade(config, "head")


async def empty_database(url: str) -> None:
    engine = create_async_engine(url, poolclass=NullPool)
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    async with engine.begin() as connection:
        await connection.execute(text(f"TRUNCATE {tables} CASCADE"))
    await engine.dispose()
