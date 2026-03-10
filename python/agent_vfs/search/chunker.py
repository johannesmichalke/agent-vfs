from __future__ import annotations


def split_into_chunks(
    text: str,
    *,
    chunk_size: int = 400,
    overlap: int = 80,
) -> list[str]:
    """Split text into overlapping chunks for embedding.

    Uses whitespace-based token approximation.
    """
    words = text.split()
    if len(words) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0

    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunks.append(" ".join(words[start:end]))
        if end >= len(words):
            break
        start += chunk_size - overlap

    return chunks
