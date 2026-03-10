"""Hybrid search index combining FTS5 (keyword/BM25) with optional vector search.

Without an EmbeddingProvider: uses FTS5 only (zero dependencies).
With an EmbeddingProvider: uses hybrid FTS5 + vector scoring.

Currently SQLite-only.
"""

from __future__ import annotations

import uuid

from ..db.sqlite import SqliteDatabase
from .chunker import split_into_chunks
from .embeddings import open_embeddings
from .types import EmbeddingProvider, SearchResult


class SearchIndex:
    def __init__(
        self,
        db: SqliteDatabase,
        user_id: str,
        embedding_provider: EmbeddingProvider | None = None,
    ):
        self._db = db
        self._user_id = user_id
        self._embedding_provider = embedding_provider
        self._vec_table_created = False

    def index(self, path: str, content: str, summary: str | None = None) -> None:
        """Index a file's content for search. Call after write/edit/append."""
        # FTS5 is handled automatically by SqliteDatabase

        # Vector indexing (optional)
        if self._embedding_provider and content:
            self._index_vectors(path, content)

    def remove(self, path: str) -> None:
        """Remove a file from the search index. Call after rm."""
        self._db.delete_chunks(self._user_id, path)
        if self._vec_table_created:
            self._remove_vectors(path)

    def search(
        self,
        query: str,
        *,
        path: str | None = None,
        limit: int = 20,
        fts_weight: float = 0.3,
    ) -> list[SearchResult]:
        """Search for files matching the query."""
        vector_weight = 1.0 - fts_weight

        # FTS5 search
        fts_results = self._db.fts_search(self._user_id, query, path, limit)

        # Normalize FTS scores
        fts_map: dict[str, float] = {}
        if fts_results:
            max_rank = max(abs(r["rank"]) for r in fts_results)
            for r in fts_results:
                fts_map[r["path"]] = abs(r["rank"]) / max_rank if max_rank > 0 else 1.0

        # Vector search (optional)
        vector_map: dict[str, dict] = {}
        if self._embedding_provider and self._vec_table_created:
            for r in self._search_vectors(query, path, limit):
                vector_map[r["path"]] = {"score": r["score"], "snippet": r["snippet"]}

        # Merge results
        all_paths = set(fts_map.keys()) | set(vector_map.keys())
        merged: list[SearchResult] = []

        for p in all_paths:
            fts_score = fts_map.get(p, 0.0)
            vec_result = vector_map.get(p)
            vec_score = vec_result["score"] if vec_result else 0.0

            if p in fts_map and p in vector_map:
                score = fts_weight * fts_score + vector_weight * vec_score
                source = "hybrid"
            elif p in vector_map:
                score = vector_weight * vec_score
                source = "vector"
            else:
                score = fts_weight * fts_score
                source = "fts"

            fts_entry = next((r for r in fts_results if r["path"] == p), None)
            snippet = fts_entry["snippet"] if fts_entry else (vec_result["snippet"] if vec_result else "")

            merged.append(SearchResult(path=p, snippet=snippet, score=score, source=source))

        merged.sort(key=lambda r: r["score"], reverse=True)
        return merged[:limit]

    # ── Vector indexing internals ─────────────────────────────────────────

    def _index_vectors(self, path: str, content: str) -> None:
        provider = self._embedding_provider
        assert provider is not None
        if not self._ensure_vec_table(provider.dimensions):
            return

        self._remove_vectors(path)

        chunks = split_into_chunks(content)
        chunk_records = [
            {"id": str(uuid.uuid4()), "index": i, "content": c}
            for i, c in enumerate(chunks)
        ]
        self._db.upsert_chunks(self._user_id, path, chunk_records)

        embeddings = provider.embed(chunks)

        conn = self._db.connection
        for i, rec in enumerate(chunk_records):
            conn.execute(
                f"INSERT INTO {self._db.table_name}_vec (chunk_id, embedding) VALUES (?, ?)",
                (rec["id"], _float_list_to_blob(embeddings[i])),
            )
        conn.commit()

    def _remove_vectors(self, path: str) -> None:
        chunks = self._db.get_chunks(self._user_id, path)
        if not chunks:
            return
        conn = self._db.connection
        for chunk in chunks:
            conn.execute(
                f"DELETE FROM {self._db.table_name}_vec WHERE chunk_id = ?",
                (chunk["id"],),
            )
        conn.commit()

    def _search_vectors(
        self, query: str, path_prefix: str | None, limit: int
    ) -> list[dict]:
        provider = self._embedding_provider
        assert provider is not None
        query_embedding = provider.embed([query])[0]

        conn = self._db.connection
        table = self._db.table_name
        rows = conn.execute(
            f"SELECT v.chunk_id, v.distance, c.node_path, c.content "
            f"FROM {table}_vec v "
            f"INNER JOIN {table}_chunks c ON v.chunk_id = c.id "
            f"WHERE c.user_id = ? AND v.embedding MATCH ? "
            f"ORDER BY v.distance LIMIT ?",
            (self._user_id, _float_list_to_blob(query_embedding), limit * 2),
        ).fetchall()

        filtered = rows
        if path_prefix and path_prefix != "/":
            filtered = [
                r for r in rows
                if r["node_path"] == path_prefix or r["node_path"].startswith(path_prefix + "/")
            ]

        by_path: dict[str, dict] = {}
        for row in filtered:
            score = 1.0 / (1.0 + row["distance"])
            p = row["node_path"]
            if p not in by_path or by_path[p]["score"] < score:
                snippet = row["content"][:200] + "..." if len(row["content"]) > 200 else row["content"]
                by_path[p] = {"score": score, "snippet": snippet}

        return [{"path": p, **v} for p, v in by_path.items()]

    def _ensure_vec_table(self, dimensions: int) -> bool:
        if self._vec_table_created:
            return True
        try:
            self._db.connection.execute(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS {self._db.table_name}_vec USING vec0("
                f"chunk_id TEXT PRIMARY KEY, embedding float[{dimensions}])"
            )
            self._vec_table_created = True
            return True
        except Exception:
            return False


def open_search(
    db: SqliteDatabase,
    user_id: str,
    provider: str | None = None,
    api_key: str | None = None,
) -> SearchIndex:
    """One-liner to create a SearchIndex.

        # FTS5 only:
        search = open_search(db, user_id)

        # Hybrid FTS5 + vector:
        search = open_search(db, user_id, "openai", os.environ["OPENAI_API_KEY"])
    """
    embedding_provider = None
    if provider and api_key:
        embedding_provider = open_embeddings(provider, api_key=api_key)
    return SearchIndex(db, user_id, embedding_provider)


def _float_list_to_blob(values: list[float]) -> bytes:
    """Convert a list of floats to a bytes blob (little-endian float32)."""
    import struct
    return struct.pack(f"<{len(values)}f", *values)
