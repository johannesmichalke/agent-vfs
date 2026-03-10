from __future__ import annotations

from typing import Protocol, TypedDict


class EmbeddingProvider(Protocol):
    """Pluggable embedding provider. Bring your own embeddings."""

    @property
    def dimensions(self) -> int: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class SearchResult(TypedDict):
    path: str
    snippet: str
    score: float
    source: str  # "fts" | "vector" | "hybrid"


class SearchOptions(TypedDict, total=False):
    path: str | None
    limit: int
    fts_weight: float
