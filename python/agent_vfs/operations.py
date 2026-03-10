from __future__ import annotations

import re
import uuid

from .db.types import Database, NodeRow
from .errors import (
    EditConflictError,
    FileSizeError,
    IsDirectoryError,
    NotDirectoryError,
    NotFoundError,
)
from .paths import all_ancestors, base_name, glob_to_like, normalize, parent_path

DEFAULT_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


class FileSystem:
    def __init__(
        self,
        db: Database,
        user_id: str,
        *,
        max_file_size: int = DEFAULT_MAX_FILE_SIZE,
        search_index=None,
    ):
        self._db = db
        self._user_id = user_id
        self._max_file_size = max_file_size
        self._search_idx = search_index

    def read(
        self, path: str, *, offset: int | None = None, limit: int | None = None
    ) -> str:
        norm = normalize(path)
        node = self._db.get_node(self._user_id, norm)
        if not node:
            raise NotFoundError(norm)
        if node["is_dir"]:
            raise IsDirectoryError(norm)
        content = node["content"] or ""
        if offset is not None or limit is not None:
            lines = content.split("\n")
            start = (offset or 1) - 1  # 1-based to 0-based
            count = limit or len(lines)
            return "\n".join(lines[max(0, start) : start + count])
        return content

    def write(self, path: str, content: str, *, summary: str | None = None) -> None:
        norm = normalize(path)
        size = len(content.encode("utf-8"))
        if size > self._max_file_size:
            raise FileSizeError(size, self._max_file_size)

        self._ensure_parents(norm)

        existing = self._db.get_node(self._user_id, norm)
        if existing and existing["is_dir"]:
            raise IsDirectoryError(norm)
        version = existing["version"] + 1 if existing else 1
        resolved_summary = summary if summary is not None else (existing["summary"] if existing else None)

        self._db.upsert_node(
            NodeRow(
                id=existing["id"] if existing else str(uuid.uuid4()),
                user_id=self._user_id,
                path=norm,
                parent_path=parent_path(norm),
                name=base_name(norm),
                is_dir=False,
                content=content,
                summary=resolved_summary,
                version=version,
                size=size,
                created_at="",
                updated_at="",
            )
        )

        if self._search_idx:
            self._search_idx.index(norm, content, resolved_summary)

    def edit(self, path: str, old_string: str, new_string: str) -> None:
        norm = normalize(path)
        node = self._db.get_node(self._user_id, norm)
        if not node:
            raise NotFoundError(norm)
        if node["is_dir"]:
            raise IsDirectoryError(norm)

        content = node["content"] or ""
        occurrences = content.count(old_string)

        if occurrences == 0:
            raise EditConflictError(f"old_string not found in {norm}")
        if occurrences > 1:
            raise EditConflictError(
                f"old_string is not unique in {norm} (found {occurrences} occurrences)"
            )

        new_content = content.replace(old_string, new_string, 1)
        new_size = len(new_content.encode("utf-8"))
        if new_size > self._max_file_size:
            raise FileSizeError(new_size, self._max_file_size)

        self._db.update_content(
            self._user_id, norm, new_content, new_size, node["version"] + 1
        )

        if self._search_idx:
            self._search_idx.index(norm, new_content, node["summary"])

    def multi_edit(
        self, path: str, edits: list[dict[str, str]]
    ) -> None:
        norm = normalize(path)
        node = self._db.get_node(self._user_id, norm)
        if not node:
            raise NotFoundError(norm)
        if node["is_dir"]:
            raise IsDirectoryError(norm)

        content = node["content"] or ""
        for edit in edits:
            old = edit["old_string"]
            new = edit["new_string"]
            occurrences = content.count(old)
            if occurrences == 0:
                raise EditConflictError(
                    f"old_string not found in {norm}: {old[:40]}"
                )
            if occurrences > 1:
                raise EditConflictError(
                    f"old_string is not unique in {norm} "
                    f"(found {occurrences} occurrences): {old[:40]}"
                )
            content = content.replace(old, new, 1)

        new_size = len(content.encode("utf-8"))
        if new_size > self._max_file_size:
            raise FileSizeError(new_size, self._max_file_size)

        self._db.update_content(
            self._user_id, norm, content, new_size, node["version"] + 1
        )

        if self._search_idx:
            self._search_idx.index(norm, content, node["summary"])

    def ls(
        self, path: str, *, recursive: bool = False, summaries: bool = False
    ) -> list[dict]:
        norm = normalize(path)

        if norm != "/":
            node = self._db.get_node(self._user_id, norm)
            if not node:
                raise NotFoundError(norm)
            if not node["is_dir"]:
                raise NotDirectoryError(norm)

        if recursive:
            nodes = self._db.list_descendants(self._user_id, norm)
        else:
            nodes = self._db.list_children(self._user_id, norm)

        result = []
        for c in nodes:
            entry: dict = {
                "path": c["path"],
                "name": c["name"],
                "is_dir": c["is_dir"],
                "size": c["size"],
            }
            if summaries:
                entry["summary"] = c["summary"]
            result.append(entry)
        return result

    def mkdir(self, path: str) -> None:
        norm = normalize(path)
        if norm == "/":
            return
        self._ensure_parents(norm)
        self._ensure_dir(norm)

    def rm(self, path: str) -> None:
        norm = normalize(path)
        if norm == "/":
            raise ValueError("Cannot remove root directory")
        node = self._db.get_node(self._user_id, norm)
        if not node:
            raise NotFoundError(norm)

        if node["is_dir"]:
            self._db.delete_tree(self._user_id, norm)
        else:
            self._db.delete_node(self._user_id, norm)

        if self._search_idx:
            self._search_idx.remove(norm)

    def append(self, path: str, content: str) -> None:
        norm = normalize(path)
        node = self._db.get_node(self._user_id, norm)
        if not node:
            self.write(norm, content)
            return
        if node["is_dir"]:
            raise IsDirectoryError(norm)
        new_content = (node["content"] or "") + content
        new_size = len(new_content.encode("utf-8"))
        if new_size > self._max_file_size:
            raise FileSizeError(new_size, self._max_file_size)

        self._db.update_content(
            self._user_id, norm, new_content, new_size, node["version"] + 1
        )

        if self._search_idx:
            self._search_idx.index(norm, new_content, node["summary"])

    def grep(
        self,
        pattern: str,
        path: str | None = None,
        *,
        case_insensitive: bool = False,
    ) -> list[dict]:
        if len(pattern) > 1000:
            raise ValueError("Regex pattern too long (max 1000 characters)")

        path_prefix = normalize(path) if path else None

        has_regex = bool(re.search(r"[.*+?^${}()|[\]\\]", pattern))
        like_str = "%" if has_regex else pattern
        candidates = self._db.search_content(self._user_id, like_str, path_prefix)

        flags = re.MULTILINE | (re.IGNORECASE if case_insensitive else 0)
        regex = re.compile(pattern, flags)
        results: list[dict] = []

        for node in candidates:
            if not node["content"]:
                continue
            file_lines = node["content"].split("\n")
            matched = []
            for i, line in enumerate(file_lines):
                if regex.search(line):
                    matched.append({"line": i + 1, "text": line})
            if matched:
                results.append({"path": node["path"], "lines": matched})

        return results

    def glob(
        self,
        pattern: str,
        path: str | None = None,
        *,
        type: str | None = None,
    ) -> list[str]:
        path_prefix = normalize(path) if path else None
        like_pattern = glob_to_like(pattern)
        nodes = self._db.search_names(self._user_id, like_pattern, path_prefix)
        if type == "file":
            nodes = [n for n in nodes if not n["is_dir"]]
        elif type == "dir":
            nodes = [n for n in nodes if n["is_dir"]]
        return [n["path"] for n in nodes]

    def mv(self, src: str, dst: str) -> None:
        norm_from = normalize(src)
        norm_to = normalize(dst)

        source_node = self._db.get_node(self._user_id, norm_from)
        if not source_node:
            raise NotFoundError(norm_from)

        dest_node = self._db.get_node(self._user_id, norm_to)
        final_to = norm_to
        if dest_node and dest_node["is_dir"]:
            final_to = normalize(norm_to + "/" + base_name(norm_from))

        final_target = self._db.get_node(self._user_id, final_to)
        if final_target and not final_target["is_dir"]:
            self._db.delete_node(self._user_id, final_to)

        self._ensure_parents(final_to)

        self._db.move_node(
            self._user_id,
            norm_from,
            final_to,
            parent_path(final_to),
            base_name(final_to),
        )

        if source_node["is_dir"]:
            self._db.move_tree(self._user_id, norm_from, final_to)

    # ── Tags ──────────────────────────────────────────────────────────────

    def tag(self, path: str, tag: str) -> None:
        norm = normalize(path)
        node = self._db.get_node(self._user_id, norm)
        if not node:
            raise NotFoundError(norm)
        self._db.add_tag(self._user_id, norm, tag)

    def untag(self, path: str, tag: str) -> None:
        norm = normalize(path)
        self._db.remove_tag(self._user_id, norm, tag)

    def tags(self, path: str) -> list[str]:
        norm = normalize(path)
        return self._db.get_tags_for_path(self._user_id, norm)

    def find_by_tag(self, tag: str, path: str | None = None) -> list[dict]:
        path_prefix = normalize(path) if path else None
        nodes = self._db.find_by_tag(self._user_id, tag, path_prefix)
        return [
            {"path": c["path"], "name": c["name"], "is_dir": c["is_dir"], "size": c["size"]}
            for c in nodes
        ]

    # ── Recent ────────────────────────────────────────────────────────────

    def recent(self, *, limit: int = 20, path: str | None = None) -> list[dict]:
        path_prefix = normalize(path) if path else None
        nodes = self._db.list_recent(self._user_id, limit, path_prefix)
        return [
            {
                "path": c["path"],
                "name": c["name"],
                "size": c["size"],
                "updated_at": c["updated_at"],
                "summary": c["summary"],
            }
            for c in nodes
        ]

    # ── Search ────────────────────────────────────────────────────────────

    def search(self, query: str, **kwargs) -> list[dict]:
        if not self._search_idx:
            raise RuntimeError(
                "Search requires a SearchIndex. Pass search_index= in FileSystem constructor."
            )
        return self._search_idx.search(query, **kwargs)

    # ── Private helpers ───────────────────────────────────────────────────

    def _ensure_parents(self, path: str) -> None:
        for anc in all_ancestors(path):
            self._ensure_dir(anc)

    def _ensure_dir(self, path: str) -> None:
        if path == "/":
            return
        existing = self._db.get_node(self._user_id, path)
        if existing:
            if not existing["is_dir"]:
                raise NotDirectoryError(path)
            return
        self._db.upsert_node(
            NodeRow(
                id=str(uuid.uuid4()),
                user_id=self._user_id,
                path=path,
                parent_path=parent_path(path),
                name=base_name(path),
                is_dir=True,
                content=None,
                summary=None,
                version=1,
                size=0,
                created_at="",
                updated_at="",
            )
        )
