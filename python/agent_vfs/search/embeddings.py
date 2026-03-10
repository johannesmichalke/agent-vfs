"""Built-in embedding providers. Just pass your API key.

    # OpenAI
    embeddings = open_embeddings("openai", api_key=os.environ["OPENAI_API_KEY"])

    # Voyage AI
    embeddings = open_embeddings("voyage", api_key=os.environ["VOYAGE_API_KEY"])

    # Custom
    embeddings = open_embeddings(
        url="https://my-api.com/embeddings",
        model="my-model",
        api_key="...",
        dimensions=768,
    )
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.request import Request, urlopen


_PRESETS: dict[str, dict] = {
    "openai": {
        "url": "https://api.openai.com/v1/embeddings",
        "model": "text-embedding-3-small",
        "dimensions": 1536,
    },
    "openai-large": {
        "url": "https://api.openai.com/v1/embeddings",
        "model": "text-embedding-3-large",
        "dimensions": 3072,
    },
    "voyage": {
        "url": "https://api.voyageai.com/v1/embeddings",
        "model": "voyage-3-lite",
        "dimensions": 512,
    },
    "voyage-large": {
        "url": "https://api.voyageai.com/v1/embeddings",
        "model": "voyage-3",
        "dimensions": 1024,
    },
    "mistral": {
        "url": "https://api.mistral.ai/v1/embeddings",
        "model": "mistral-embed",
        "dimensions": 1024,
    },
}


@dataclass
class _HttpEmbeddingProvider:
    url: str
    model: str
    api_key: str
    _dimensions: int

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        return _batch_embed(self.url, self.model, self.api_key, texts)


def open_embeddings(
    provider: str | None = None,
    *,
    api_key: str | None = None,
    url: str | None = None,
    model: str | None = None,
    dimensions: int | None = None,
) -> _HttpEmbeddingProvider:
    """Create an embedding provider with minimal config.

    Args:
        provider: Preset name ("openai", "voyage", "mistral", etc.) or None for custom.
        api_key: API key (required).
        url: Custom API URL (only for custom providers).
        model: Custom model name (only for custom providers).
        dimensions: Vector dimensionality (only for custom providers).
    """
    if provider is not None:
        preset = _PRESETS.get(provider)
        if not preset:
            available = ", ".join(_PRESETS.keys())
            raise ValueError(
                f'Unknown embedding provider: "{provider}". Available: {available}. '
                "Or pass url/model/dimensions for a custom provider."
            )
        if not api_key:
            raise ValueError(f'API key required for "{provider}" provider.')
        return _HttpEmbeddingProvider(
            url=preset["url"],
            model=preset["model"],
            api_key=api_key,
            _dimensions=preset["dimensions"],
        )

    # Custom provider
    if not all([url, model, api_key, dimensions]):
        raise ValueError("Custom provider requires url, model, api_key, and dimensions.")
    return _HttpEmbeddingProvider(
        url=url,  # type: ignore
        model=model,  # type: ignore
        api_key=api_key,  # type: ignore
        _dimensions=dimensions,  # type: ignore
    )


def _batch_embed(
    url: str, model: str, api_key: str, texts: list[str]
) -> list[list[float]]:
    """Embed texts via HTTP API with automatic batching."""
    BATCH_SIZE = 96
    results: list[list[float]] = []

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        body = json.dumps({"model": model, "input": batch}).encode()
        req = Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        with urlopen(req) as resp:
            data = json.loads(resp.read())

        sorted_data = sorted(data["data"], key=lambda x: x["index"])
        for item in sorted_data:
            results.append(item["embedding"])

    return results
