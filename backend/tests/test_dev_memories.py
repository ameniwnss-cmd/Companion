import asyncio
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from companion.config import Environment, Settings
from companion.db.models import MemoryKind
from companion.db.session import SessionFactory
from companion.embeddings import FakeEmbedder
from companion.llm.fake import FakeLLM
from companion.main import create_app
from companion.memory.extract import Candidate
from companion.memory.service import MemoryService
from companion.users import get_or_create_user


@pytest.fixture
def client(settings: Settings, sessions: SessionFactory) -> Iterator[TestClient]:
    async def seed() -> None:
        dev = await get_or_create_user(sessions, settings.dev_user_email, None)
        other = await get_or_create_user(sessions, "someone-else@example.com", None)
        service = MemoryService(sessions, FakeEmbedder())
        await service.remember(dev.id, [Candidate(kind=MemoryKind.GOAL, content="Run a 5k")])
        await service.remember(other.id, [Candidate(kind=MemoryKind.HABIT, content="Not yours")])

    asyncio.run(seed())
    app = create_app(settings, llm=FakeLLM(), embedder=FakeEmbedder())
    with TestClient(app) as client:
        yield client


def test_lists_only_the_dev_users_memories(client: TestClient) -> None:
    response = client.get("/dev/memories")

    assert response.status_code == 200
    [memory] = response.json()
    assert (memory["kind"], memory["content"]) == ("goal", "Run a 5k")


def test_edits_a_memory(client: TestClient) -> None:
    [memory] = client.get("/dev/memories").json()

    response = client.patch(
        f"/dev/memories/{memory['id']}", json={"kind": "commitment", "content": " Run a 10k "}
    )

    assert response.status_code == 200
    assert (response.json()["kind"], response.json()["content"]) == ("commitment", "Run a 10k")


@pytest.mark.parametrize(
    "changes", [{"content": ""}, {"kind": "secret"}, {"content": "x" * 301}, {"owner": "me"}]
)
def test_rejects_invalid_edits(client: TestClient, changes: dict[str, str]) -> None:
    [memory] = client.get("/dev/memories").json()

    assert client.patch(f"/dev/memories/{memory['id']}", json=changes).status_code == 422


def test_deletes_one_memory_then_everything(client: TestClient) -> None:
    [memory] = client.get("/dev/memories").json()

    assert client.delete(f"/dev/memories/{memory['id']}").status_code == 204
    assert client.delete(f"/dev/memories/{memory['id']}").status_code == 404
    assert client.get("/dev/memories").json() == []
    assert client.delete("/dev/memories").status_code == 204


def test_unknown_memories_are_not_found(client: TestClient) -> None:
    unknown = "00000000-0000-0000-0000-000000000000"

    assert client.patch(f"/dev/memories/{unknown}", json={"content": "x"}).status_code == 404
    assert client.delete(f"/dev/memories/{unknown}").status_code == 404


def test_the_memory_api_does_not_exist_in_production() -> None:
    settings = Settings(
        environment=Environment.PRODUCTION,
        dev_text_channel=True,
        reminder_loop_enabled=False,
        _env_file=None,
    )

    with TestClient(create_app(settings, llm=FakeLLM())) as client:
        assert client.get("/dev/memories").status_code == 404
