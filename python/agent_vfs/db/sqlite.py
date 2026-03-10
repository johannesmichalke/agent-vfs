from __future__ import annotations

import sqlite3

from ..errors import EditConflictError
from ..schema import get_sqlite_schema, validate_table_name
from .types import NodeRow


def _row_to_node(row: sqlite3.Row) -> NodeRow:
    return NodeRow(
        id=row["id"],
        user_id=row["user_id"],
        path=row["path"],
        parent_path=row["parent_path"],
        name=row["name"],
        is_dir=bool(row["is_dir"]),
        content=row["content"],
        summary=row["summary"],
        version=row["version"],
        size=row["size"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class SqliteDatabase:
    def __init__(self, db_path: str, *, table_name: str = "nodes"):
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._table = validate_table_name(table_name)

    @property
    def table_name(self) -> str:
        return self._table

    @property
    def connection(self) -> sqlite3.Connection:
        """Expose raw connection for extensions (e.g. sqlite-vec)."""
        return self._conn

    def initialize(self) -> None:
        schema = get_sqlite_schema(self._table)
        for stmt in schema.split(";"):
            stmt = stmt.strip()
            if stmt:
                self._conn.execute(stmt)
        self._conn.commit()

    def get_node(self, user_id: str, path: str) -> NodeRow | None:
        cur = self._conn.execute(
            f"SELECT * FROM {self._table} WHERE user_id = ? AND path = ?",
            (user_id, path),
        )
        row = cur.fetchone()
        return _row_to_node(row) if row else None

    def list_children(self, user_id: str, parent_path: str) -> list[NodeRow]:
        cur = self._conn.execute(
            f"SELECT * FROM {self._table} WHERE user_id = ? AND parent_path = ? "
            "ORDER BY is_dir DESC, name ASC",
            (user_id, parent_path),
        )
        return [_row_to_node(r) for r in cur.fetchall()]

    def list_descendants(self, user_id: str, path_prefix: str) -> list[NodeRow]:
        if path_prefix == "/":
            cur = self._conn.execute(
                f"SELECT * FROM {self._table} WHERE user_id = ? ORDER BY path ASC",
                (user_id,),
            )
        else:
            cur = self._conn.execute(
                f"SELECT * FROM {self._table} WHERE user_id = ? "
                "AND (path = ? OR path LIKE ?) ORDER BY path ASC",
                (user_id, path_prefix, path_prefix + "/%"),
            )
        return [_row_to_node(r) for r in cur.fetchall()]

    def upsert_node(self, node: NodeRow) -> None:
        self._conn.execute(
            f"INSERT INTO {self._table} "
            "(id, user_id, path, parent_path, name, is_dir, content, summary, version, size) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id, path) DO UPDATE SET "
            "content = excluded.content, summary = excluded.summary, "
            "version = excluded.version, size = excluded.size, "
            "updated_at = datetime('now')",
            (
                node["id"],
                node["user_id"],
                node["path"],
                node["parent_path"],
                node["name"],
                1 if node["is_dir"] else 0,
                node["content"],
                node["summary"],
                node["version"],
                node["size"],
            ),
        )
        self._conn.commit()

        # Update FTS index for files
        if not node["is_dir"] and node["content"] is not None:
            self._fts_upsert(node["user_id"], node["path"], node["content"], node["summary"])

    def update_content(
        self,
        user_id: str,
        path: str,
        content: str,
        size: int,
        version: int,
    ) -> None:
        cur = self._conn.execute(
            f"UPDATE {self._table} SET content = ?, size = ?, version = ?, "
            "updated_at = datetime('now') "
            "WHERE user_id = ? AND path = ? AND version = ?",
            (content, size, version, user_id, path, version - 1),
        )
        if cur.rowcount == 0:
            self._conn.rollback()
            raise EditConflictError(
                f"Concurrent edit detected on {path} (expected version {version - 1})"
            )
        self._conn.commit()

        # Update FTS index
        row = self._conn.execute(
            f"SELECT summary FROM {self._table} WHERE user_id = ? AND path = ?",
            (user_id, path),
        ).fetchone()
        self._fts_upsert(user_id, path, content, row["summary"] if row else None)

    def update_summary(self, user_id: str, path: str, summary: str | None) -> None:
        self._conn.execute(
            f"UPDATE {self._table} SET summary = ?, updated_at = datetime('now') "
            "WHERE user_id = ? AND path = ?",
            (summary, user_id, path),
        )
        self._conn.commit()

        row = self._conn.execute(
            f"SELECT content FROM {self._table} WHERE user_id = ? AND path = ?",
            (user_id, path),
        ).fetchone()
        if row and row["content"] is not None:
            self._fts_upsert(user_id, path, row["content"], summary)

    def delete_node(self, user_id: str, path: str) -> None:
        self._conn.execute(
            f"DELETE FROM {self._table} WHERE user_id = ? AND path = ?",
            (user_id, path),
        )
        self._fts_remove(user_id, path)
        self._conn.execute(
            f"DELETE FROM {self._table}_tags WHERE user_id = ? AND path = ?",
            (user_id, path),
        )
        self._conn.commit()

    def delete_tree(self, user_id: str, path_prefix: str) -> None:
        self._conn.execute(
            f"DELETE FROM {self._table} WHERE user_id = ? AND (path = ? OR path LIKE ?)",
            (user_id, path_prefix, path_prefix + "/%"),
        )
        self._conn.execute(
            f"DELETE FROM {self._table}_fts WHERE user_id = ? AND (path = ? OR path LIKE ?)",
            (user_id, path_prefix, path_prefix + "/%"),
        )
        self._conn.execute(
            f"DELETE FROM {self._table}_tags WHERE user_id = ? AND (path = ? OR path LIKE ?)",
            (user_id, path_prefix, path_prefix + "/%"),
        )
        self._conn.commit()

    def move_node(
        self,
        user_id: str,
        old_path: str,
        new_path: str,
        new_parent: str,
        new_name: str,
    ) -> None:
        self._conn.execute(
            f"UPDATE {self._table} SET path = ?, parent_path = ?, name = ?, "
            "updated_at = datetime('now') WHERE user_id = ? AND path = ?",
            (new_path, new_parent, new_name, user_id, old_path),
        )
        self._conn.execute(
            f"UPDATE {self._table}_fts SET path = ? WHERE user_id = ? AND path = ?",
            (new_path, user_id, old_path),
        )
        self._conn.execute(
            f"UPDATE {self._table}_tags SET path = ? WHERE user_id = ? AND path = ?",
            (new_path, user_id, old_path),
        )
        self._conn.commit()

    def move_tree(
        self, user_id: str, old_prefix: str, new_prefix: str
    ) -> None:
        cur = self._conn.execute(
            f"SELECT path, parent_path FROM {self._table} "
            "WHERE user_id = ? AND path LIKE ?",
            (user_id, old_prefix + "/%"),
        )
        rows = cur.fetchall()
        for row in rows:
            new_path = new_prefix + row["path"][len(old_prefix):]
            new_parent_path = new_prefix + row["parent_path"][len(old_prefix):]
            self._conn.execute(
                f"UPDATE {self._table} SET path = ?, parent_path = ?, "
                "updated_at = datetime('now') WHERE user_id = ? AND path = ?",
                (new_path, new_parent_path, user_id, row["path"]),
            )
            self._conn.execute(
                f"UPDATE {self._table}_fts SET path = ? WHERE user_id = ? AND path = ?",
                (new_path, user_id, row["path"]),
            )
            self._conn.execute(
                f"UPDATE {self._table}_tags SET path = ? WHERE user_id = ? AND path = ?",
                (new_path, user_id, row["path"]),
            )
        self._conn.commit()

    def search_content(
        self,
        user_id: str,
        like_pattern: str,
        path_prefix: str | None = None,
    ) -> list[NodeRow]:
        if path_prefix and path_prefix != "/":
            cur = self._conn.execute(
                f"SELECT * FROM {self._table} WHERE user_id = ? AND is_dir = 0 "
                "AND content LIKE ? ESCAPE '\\' "
                "AND (path = ? OR path LIKE ?)",
                (user_id, f"%{like_pattern}%", path_prefix, path_prefix + "/%"),
            )
        else:
            cur = self._conn.execute(
                f"SELECT * FROM {self._table} WHERE user_id = ? AND is_dir = 0 "
                "AND content LIKE ? ESCAPE '\\'",
                (user_id, f"%{like_pattern}%"),
            )
        return [_row_to_node(r) for r in cur.fetchall()]

    def search_names(
        self,
        user_id: str,
        like_pattern: str,
        path_prefix: str | None = None,
    ) -> list[NodeRow]:
        if path_prefix and path_prefix != "/":
            cur = self._conn.execute(
                f"SELECT * FROM {self._table} WHERE user_id = ? "
                "AND name LIKE ? ESCAPE '\\' "
                "AND (path = ? OR path LIKE ?)",
                (user_id, like_pattern, path_prefix, path_prefix + "/%"),
            )
        else:
            cur = self._conn.execute(
                f"SELECT * FROM {self._table} WHERE user_id = ? "
                "AND name LIKE ? ESCAPE '\\'",
                (user_id, like_pattern),
            )
        return [_row_to_node(r) for r in cur.fetchall()]

    # ── Tags ──────────────────────────────────────────────────────────────

    def add_tag(self, user_id: str, path: str, tag: str) -> None:
        self._conn.execute(
            f"INSERT OR IGNORE INTO {self._table}_tags (user_id, path, tag) VALUES (?, ?, ?)",
            (user_id, path, tag),
        )
        self._conn.commit()

    def remove_tag(self, user_id: str, path: str, tag: str) -> None:
        self._conn.execute(
            f"DELETE FROM {self._table}_tags WHERE user_id = ? AND path = ? AND tag = ?",
            (user_id, path, tag),
        )
        self._conn.commit()

    def get_tags_for_path(self, user_id: str, path: str) -> list[str]:
        cur = self._conn.execute(
            f"SELECT tag FROM {self._table}_tags WHERE user_id = ? AND path = ? ORDER BY tag",
            (user_id, path),
        )
        return [r["tag"] for r in cur.fetchall()]

    def find_by_tag(
        self, user_id: str, tag: str, path_prefix: str | None = None
    ) -> list[NodeRow]:
        if path_prefix and path_prefix != "/":
            cur = self._conn.execute(
                f"SELECT n.* FROM {self._table} n "
                f"INNER JOIN {self._table}_tags t ON n.user_id = t.user_id AND n.path = t.path "
                "WHERE n.user_id = ? AND t.tag = ? "
                "AND (n.path = ? OR n.path LIKE ?) ORDER BY n.path",
                (user_id, tag, path_prefix, path_prefix + "/%"),
            )
        else:
            cur = self._conn.execute(
                f"SELECT n.* FROM {self._table} n "
                f"INNER JOIN {self._table}_tags t ON n.user_id = t.user_id AND n.path = t.path "
                "WHERE n.user_id = ? AND t.tag = ? ORDER BY n.path",
                (user_id, tag),
            )
        return [_row_to_node(r) for r in cur.fetchall()]

    # ── Recent ────────────────────────────────────────────────────────────

    def list_recent(
        self, user_id: str, limit: int = 20, path_prefix: str | None = None
    ) -> list[NodeRow]:
        if path_prefix and path_prefix != "/":
            cur = self._conn.execute(
                f"SELECT * FROM {self._table} "
                "WHERE user_id = ? AND is_dir = 0 "
                "AND (path = ? OR path LIKE ?) "
                "ORDER BY updated_at DESC LIMIT ?",
                (user_id, path_prefix, path_prefix + "/%", limit),
            )
        else:
            cur = self._conn.execute(
                f"SELECT * FROM {self._table} "
                "WHERE user_id = ? AND is_dir = 0 "
                "ORDER BY updated_at DESC LIMIT ?",
                (user_id, limit),
            )
        return [_row_to_node(r) for r in cur.fetchall()]

    # ── FTS5 ──────────────────────────────────────────────────────────────

    def fts_search(
        self,
        user_id: str,
        query: str,
        path_prefix: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        """Search using FTS5. Returns list of {path, snippet, rank}."""
        import re as _re

        safe_query = _re.sub(r'["*^(){}[\]:]', " ", query).strip()
        if not safe_query:
            return []

        fts_query = " ".join(f'"{t}"' for t in safe_query.split() if t)

        if path_prefix and path_prefix != "/":
            cur = self._conn.execute(
                f"SELECT path, snippet({self._table}_fts, 0, '>>>', '<<<', '...', 32) as snippet, rank "
                f"FROM {self._table}_fts "
                f"WHERE {self._table}_fts MATCH ? AND user_id = ? "
                "AND (path = ? OR path LIKE ?) "
                "ORDER BY rank LIMIT ?",
                (fts_query, user_id, path_prefix, path_prefix + "/%", limit),
            )
        else:
            cur = self._conn.execute(
                f"SELECT path, snippet({self._table}_fts, 0, '>>>', '<<<', '...', 32) as snippet, rank "
                f"FROM {self._table}_fts "
                f"WHERE {self._table}_fts MATCH ? AND user_id = ? "
                "ORDER BY rank LIMIT ?",
                (fts_query, user_id, limit),
            )
        return [{"path": r["path"], "snippet": r["snippet"], "rank": r["rank"]} for r in cur.fetchall()]

    # ── Chunks (for vector search) ────────────────────────────────────────

    def upsert_chunks(
        self, user_id: str, node_path: str, chunks: list[dict]
    ) -> None:
        self._conn.execute(
            f"DELETE FROM {self._table}_chunks WHERE user_id = ? AND node_path = ?",
            (user_id, node_path),
        )
        for chunk in chunks:
            self._conn.execute(
                f"INSERT INTO {self._table}_chunks (id, user_id, node_path, chunk_index, content) "
                "VALUES (?, ?, ?, ?, ?)",
                (chunk["id"], user_id, node_path, chunk["index"], chunk["content"]),
            )
        self._conn.commit()

    def get_chunks(self, user_id: str, node_path: str) -> list[dict]:
        cur = self._conn.execute(
            f"SELECT id, chunk_index, content FROM {self._table}_chunks "
            "WHERE user_id = ? AND node_path = ? ORDER BY chunk_index",
            (user_id, node_path),
        )
        return [{"id": r["id"], "chunk_index": r["chunk_index"], "content": r["content"]} for r in cur.fetchall()]

    def delete_chunks(self, user_id: str, node_path: str) -> None:
        self._conn.execute(
            f"DELETE FROM {self._table}_chunks WHERE user_id = ? AND node_path = ?",
            (user_id, node_path),
        )
        self._conn.commit()

    # ── FTS5 internal helpers ─────────────────────────────────────────────

    def _fts_upsert(self, user_id: str, path: str, content: str, summary: str | None) -> None:
        self._conn.execute(
            f"DELETE FROM {self._table}_fts WHERE user_id = ? AND path = ?",
            (user_id, path),
        )
        self._conn.execute(
            f"INSERT INTO {self._table}_fts (content, summary, user_id, path) VALUES (?, ?, ?, ?)",
            (content, summary or "", user_id, path),
        )
        self._conn.commit()

    def _fts_remove(self, user_id: str, path: str) -> None:
        self._conn.execute(
            f"DELETE FROM {self._table}_fts WHERE user_id = ? AND path = ?",
            (user_id, path),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
