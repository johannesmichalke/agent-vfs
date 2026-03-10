from __future__ import annotations

from ..errors import EditConflictError
from ..schema import get_postgres_schema, validate_table_name
from .types import NodeRow


def _row_to_node(row: dict) -> NodeRow:
    return NodeRow(
        id=row["id"],
        user_id=row["user_id"],
        path=row["path"],
        parent_path=row["parent_path"],
        name=row["name"],
        is_dir=bool(row["is_dir"]),
        content=row["content"],
        summary=row.get("summary"),
        version=row["version"],
        size=row["size"],
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


class PostgresDatabase:
    def __init__(self, url_or_conn, *, table_name: str = "nodes"):
        """Accept a connection URL string or an existing psycopg2 connection."""
        if isinstance(url_or_conn, str):
            import psycopg2
            import psycopg2.extras

            self._conn = psycopg2.connect(url_or_conn)
            self._owns_conn = True
        else:
            self._conn = url_or_conn
            self._owns_conn = False
        self._table = validate_table_name(table_name)

    def _cursor(self):
        import psycopg2.extras

        return self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    def initialize(self) -> None:
        schema = get_postgres_schema(self._table)
        with self._cursor() as cur:
            for stmt in schema.split(";"):
                stmt = stmt.strip()
                if stmt:
                    cur.execute(stmt)
        self._conn.commit()

    def get_node(self, user_id: str, path: str) -> NodeRow | None:
        with self._cursor() as cur:
            cur.execute(
                f"SELECT * FROM {self._table} WHERE user_id = %s AND path = %s",
                (user_id, path),
            )
            row = cur.fetchone()
        return _row_to_node(row) if row else None

    def list_children(self, user_id: str, parent_path: str) -> list[NodeRow]:
        with self._cursor() as cur:
            cur.execute(
                f"SELECT * FROM {self._table} WHERE user_id = %s AND parent_path = %s "
                "ORDER BY is_dir DESC, name ASC",
                (user_id, parent_path),
            )
            return [_row_to_node(r) for r in cur.fetchall()]

    def list_descendants(self, user_id: str, path_prefix: str) -> list[NodeRow]:
        with self._cursor() as cur:
            if path_prefix == "/":
                cur.execute(
                    f"SELECT * FROM {self._table} WHERE user_id = %s ORDER BY path ASC",
                    (user_id,),
                )
            else:
                cur.execute(
                    f"SELECT * FROM {self._table} WHERE user_id = %s "
                    "AND (path = %s OR path LIKE %s) ORDER BY path ASC",
                    (user_id, path_prefix, path_prefix + "/%"),
                )
            return [_row_to_node(r) for r in cur.fetchall()]

    def upsert_node(self, node: NodeRow) -> None:
        with self._cursor() as cur:
            cur.execute(
                f"INSERT INTO {self._table} "
                "(id, user_id, path, parent_path, name, is_dir, content, summary, version, size) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (user_id, path) DO UPDATE SET "
                "content = EXCLUDED.content, summary = EXCLUDED.summary, "
                "version = EXCLUDED.version, size = EXCLUDED.size, updated_at = NOW()",
                (
                    node["id"],
                    node["user_id"],
                    node["path"],
                    node["parent_path"],
                    node["name"],
                    node["is_dir"],
                    node["content"],
                    node["summary"],
                    node["version"],
                    node["size"],
                ),
            )
        self._conn.commit()

    def update_content(
        self, user_id: str, path: str, content: str, size: int, version: int,
    ) -> None:
        with self._cursor() as cur:
            cur.execute(
                f"UPDATE {self._table} SET content = %s, size = %s, version = %s, "
                "updated_at = NOW() "
                "WHERE user_id = %s AND path = %s AND version = %s",
                (content, size, version, user_id, path, version - 1),
            )
            if cur.rowcount == 0:
                self._conn.rollback()
                raise EditConflictError(
                    f"Concurrent edit detected on {path} (expected version {version - 1})"
                )
        self._conn.commit()

    def update_summary(self, user_id: str, path: str, summary: str | None) -> None:
        with self._cursor() as cur:
            cur.execute(
                f"UPDATE {self._table} SET summary = %s, updated_at = NOW() "
                "WHERE user_id = %s AND path = %s",
                (summary, user_id, path),
            )
        self._conn.commit()

    def delete_node(self, user_id: str, path: str) -> None:
        with self._cursor() as cur:
            cur.execute(
                f"DELETE FROM {self._table} WHERE user_id = %s AND path = %s",
                (user_id, path),
            )
            cur.execute(
                f"DELETE FROM {self._table}_tags WHERE user_id = %s AND path = %s",
                (user_id, path),
            )
        self._conn.commit()

    def delete_tree(self, user_id: str, path_prefix: str) -> None:
        with self._cursor() as cur:
            cur.execute(
                f"DELETE FROM {self._table} WHERE user_id = %s "
                "AND (path = %s OR path LIKE %s)",
                (user_id, path_prefix, path_prefix + "/%"),
            )
            cur.execute(
                f"DELETE FROM {self._table}_tags WHERE user_id = %s "
                "AND (path = %s OR path LIKE %s)",
                (user_id, path_prefix, path_prefix + "/%"),
            )
        self._conn.commit()

    def move_node(
        self, user_id: str, old_path: str, new_path: str, new_parent: str, new_name: str,
    ) -> None:
        with self._cursor() as cur:
            cur.execute(
                f"UPDATE {self._table} SET path = %s, parent_path = %s, name = %s, "
                "updated_at = NOW() WHERE user_id = %s AND path = %s",
                (new_path, new_parent, new_name, user_id, old_path),
            )
            cur.execute(
                f"UPDATE {self._table}_tags SET path = %s WHERE user_id = %s AND path = %s",
                (new_path, user_id, old_path),
            )
        self._conn.commit()

    def move_tree(self, user_id: str, old_prefix: str, new_prefix: str) -> None:
        with self._cursor() as cur:
            cur.execute(
                f"SELECT path, parent_path FROM {self._table} "
                "WHERE user_id = %s AND path LIKE %s",
                (user_id, old_prefix + "/%"),
            )
            rows = cur.fetchall()
            for row in rows:
                new_path = new_prefix + row["path"][len(old_prefix):]
                new_parent_path = new_prefix + row["parent_path"][len(old_prefix):]
                cur.execute(
                    f"UPDATE {self._table} SET path = %s, parent_path = %s, "
                    "updated_at = NOW() WHERE user_id = %s AND path = %s",
                    (new_path, new_parent_path, user_id, row["path"]),
                )
                cur.execute(
                    f"UPDATE {self._table}_tags SET path = %s WHERE user_id = %s AND path = %s",
                    (new_path, user_id, row["path"]),
                )
        self._conn.commit()

    def search_content(self, user_id: str, like_pattern: str, path_prefix: str | None = None) -> list[NodeRow]:
        with self._cursor() as cur:
            if path_prefix and path_prefix != "/":
                cur.execute(
                    f"SELECT * FROM {self._table} WHERE user_id = %s AND is_dir = FALSE "
                    "AND content LIKE %s "
                    "AND (path = %s OR path LIKE %s)",
                    (user_id, f"%{like_pattern}%", path_prefix, path_prefix + "/%"),
                )
            else:
                cur.execute(
                    f"SELECT * FROM {self._table} WHERE user_id = %s AND is_dir = FALSE "
                    "AND content LIKE %s",
                    (user_id, f"%{like_pattern}%"),
                )
            return [_row_to_node(r) for r in cur.fetchall()]

    def search_names(self, user_id: str, like_pattern: str, path_prefix: str | None = None) -> list[NodeRow]:
        with self._cursor() as cur:
            if path_prefix and path_prefix != "/":
                cur.execute(
                    f"SELECT * FROM {self._table} WHERE user_id = %s "
                    "AND name LIKE %s "
                    "AND (path = %s OR path LIKE %s)",
                    (user_id, like_pattern, path_prefix, path_prefix + "/%"),
                )
            else:
                cur.execute(
                    f"SELECT * FROM {self._table} WHERE user_id = %s AND name LIKE %s",
                    (user_id, like_pattern),
                )
            return [_row_to_node(r) for r in cur.fetchall()]

    # ── Tags ──────────────────────────────────────────────────────────────

    def add_tag(self, user_id: str, path: str, tag: str) -> None:
        with self._cursor() as cur:
            cur.execute(
                f"INSERT INTO {self._table}_tags (user_id, path, tag) VALUES (%s, %s, %s) "
                "ON CONFLICT DO NOTHING",
                (user_id, path, tag),
            )
        self._conn.commit()

    def remove_tag(self, user_id: str, path: str, tag: str) -> None:
        with self._cursor() as cur:
            cur.execute(
                f"DELETE FROM {self._table}_tags WHERE user_id = %s AND path = %s AND tag = %s",
                (user_id, path, tag),
            )
        self._conn.commit()

    def get_tags_for_path(self, user_id: str, path: str) -> list[str]:
        with self._cursor() as cur:
            cur.execute(
                f"SELECT tag FROM {self._table}_tags WHERE user_id = %s AND path = %s ORDER BY tag",
                (user_id, path),
            )
            return [r["tag"] for r in cur.fetchall()]

    def find_by_tag(self, user_id: str, tag: str, path_prefix: str | None = None) -> list[NodeRow]:
        with self._cursor() as cur:
            if path_prefix and path_prefix != "/":
                cur.execute(
                    f"SELECT n.* FROM {self._table} n "
                    f"INNER JOIN {self._table}_tags t ON n.user_id = t.user_id AND n.path = t.path "
                    "WHERE n.user_id = %s AND t.tag = %s "
                    "AND (n.path = %s OR n.path LIKE %s) ORDER BY n.path",
                    (user_id, tag, path_prefix, path_prefix + "/%"),
                )
            else:
                cur.execute(
                    f"SELECT n.* FROM {self._table} n "
                    f"INNER JOIN {self._table}_tags t ON n.user_id = t.user_id AND n.path = t.path "
                    "WHERE n.user_id = %s AND t.tag = %s ORDER BY n.path",
                    (user_id, tag),
                )
            return [_row_to_node(r) for r in cur.fetchall()]

    # ── Recent ────────────────────────────────────────────────────────────

    def list_recent(self, user_id: str, limit: int = 20, path_prefix: str | None = None) -> list[NodeRow]:
        with self._cursor() as cur:
            if path_prefix and path_prefix != "/":
                cur.execute(
                    f"SELECT * FROM {self._table} "
                    "WHERE user_id = %s AND is_dir = FALSE "
                    "AND (path = %s OR path LIKE %s) "
                    "ORDER BY updated_at DESC LIMIT %s",
                    (user_id, path_prefix, path_prefix + "/%", limit),
                )
            else:
                cur.execute(
                    f"SELECT * FROM {self._table} "
                    "WHERE user_id = %s AND is_dir = FALSE "
                    "ORDER BY updated_at DESC LIMIT %s",
                    (user_id, limit),
                )
            return [_row_to_node(r) for r in cur.fetchall()]

    def close(self) -> None:
        if self._owns_conn:
            self._conn.close()
