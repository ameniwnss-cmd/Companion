import json
import math

import httpx
import pytest
from pydantic import SecretStr

from companion.config import EmbeddingProviderName, Settings
from companion.embeddings import (
    EMBEDDING_DIMENSIONS,
    KEEP_LOADED,
    EmbeddingError,
    FakeEmbedder,
    OllamaEmbedder,
    warm_up,
)
from companion.llm.factory import build_embedder


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


async def test_fake_vectors_are_normalised_and_similar_texts_are_closer() -> None:
    goal, similar, unrelated = await FakeEmbedder().embed(
        ["wants to run a 5k", "run a 5k in march", "likes pineapple pizza"]
    )

    assert len(goal) == EMBEDDING_DIMENSIONS
    assert math.isclose(math.sqrt(sum(v * v for v in goal)), 1.0)
    assert cosine(goal, similar) > cosine(goal, unrelated)


def ollama(handler: httpx.MockTransport) -> OllamaEmbedder:
    return OllamaEmbedder(httpx.AsyncClient(transport=handler), base_url="http://o/", model="mini")


async def test_ollama_embeds_a_batch_and_normalises() -> None:
    bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://o/api/embed"
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"embeddings": [[2.0] * EMBEDDING_DIMENSIONS] * 2})

    vectors = await ollama(httpx.MockTransport(handler)).embed(["a", "b"])

    assert bodies == [{"model": "mini", "input": ["a", "b"], "keep_alive": KEEP_LOADED}]
    assert len(vectors) == 2
    assert math.isclose(vectors[0][0], 1 / math.sqrt(EMBEDDING_DIMENSIONS))


async def test_ollama_skips_the_call_for_nothing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request expected")

    assert await ollama(httpx.MockTransport(handler)).embed([]) == []


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500),
        httpx.Response(200, json={"nope": []}),
        httpx.Response(200, json={"embeddings": [[1.0, 2.0]]}),
        httpx.Response(200, json={"embeddings": []}),
    ],
)
async def test_ollama_failures_raise(response: httpx.Response) -> None:
    with pytest.raises(EmbeddingError):
        await ollama(httpx.MockTransport(lambda _: response)).embed(["a"])


@pytest.mark.parametrize(
    ("provider", "expected"),
    [(EmbeddingProviderName.FAKE, FakeEmbedder), (EmbeddingProviderName.OLLAMA, OllamaEmbedder)],
)
def test_builds_the_configured_embedder(provider: EmbeddingProviderName, expected: type) -> None:
    settings = Settings(embedding_provider=provider, groq_api_key=SecretStr("k"), _env_file=None)

    assert isinstance(build_embedder(settings, httpx.AsyncClient()), expected)


async def test_warming_up_loads_the_model_once() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"embeddings": [[1.0] * EMBEDDING_DIMENSIONS]})

    await warm_up(ollama(httpx.MockTransport(handler)))

    assert len(requests) == 1


async def test_a_failed_warm_up_does_not_stop_the_app() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    await warm_up(ollama(httpx.MockTransport(handler)))
