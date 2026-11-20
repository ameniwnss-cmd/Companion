import hashlib
import logging
import math
import re
from collections.abc import Sequence
from typing import Protocol

import httpx

from companion.llm import LLMError

logger = logging.getLogger(__name__)

EMBEDDING_DIMENSIONS = 384
KEEP_LOADED = "24h"

_WORD = re.compile(r"[a-z0-9']+")


class Embedder(Protocol):
    async def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class EmbeddingError(LLMError):
    pass


def _normalised(vector: list[float]) -> list[float]:
    length = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / length for value in vector]


class FakeEmbedder:
    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._bag_of_words(text) for text in texts]

    @staticmethod
    def _bag_of_words(text: str) -> list[float]:
        vector = [0.0] * EMBEDDING_DIMENSIONS
        for word in _WORD.findall(text.lower()):
            digest = hashlib.sha256(word.encode()).digest()
            vector[int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSIONS] += 1.0
        return _normalised(vector)


class OllamaEmbedder:
    def __init__(self, http: httpx.AsyncClient, *, base_url: str, model: str) -> None:
        self._http = http
        self._url = f"{base_url.rstrip('/')}/api/embed"
        self._model = model

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        try:
            response = await self._http.post(
                self._url,
                json={"model": self._model, "input": list(texts), "keep_alive": KEEP_LOADED},
            )
            response.raise_for_status()
            vectors = response.json()["embeddings"]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise EmbeddingError(f"Ollama embedding failed: {type(exc).__name__}") from exc

        if len(vectors) != len(texts) or any(len(v) != EMBEDDING_DIMENSIONS for v in vectors):
            raise EmbeddingError(f"Expected {len(texts)} vectors of {EMBEDDING_DIMENSIONS} numbers")
        return [_normalised([float(value) for value in vector]) for vector in vectors]


async def warm_up(embedder: Embedder) -> None:
    try:
        await embedder.embed(["warm up"])
    except EmbeddingError:
        logger.warning("Warming up the embedding model failed", exc_info=True)
