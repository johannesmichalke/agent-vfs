from __future__ import annotations

from typing import Protocol, TypedDict


class NodeRow(TypedDict):
    id: str
    user_id: str
    path: str
    parent_path: str
    name: str
    is_dir: bool
    content: str | None
    summary: str | None
    version: int
    size: int
    created_at: str
    updated_at: str


class Database(Protocol):
    def initialize(self) -> None: ...
    def get_node(self, user_id: str, path: str) -> NodeRow | None: ...
    def list_children(self, user_id: str, parent_path: str) -> list[NodeRow]: ...
    def list_descendants(self, user_id: str, path_prefix: str) -> list[NodeRow]: ...
    def upsert_node(self, node: NodeRow) -> None: ...
    def update_content(
        self,
        user_id: str,
        path: str,
        content: str,
        size: int,
        version: int,
    ) -> None: ...
    def update_summary(
        self, user_id: str, path: str, summary: str | None
    ) -> None: ...
    def delete_node(self, user_id: str, path: str) -> None: ...
    def delete_tree(self, user_id: str, path_prefix: str) -> None: ...
    def move_node(
        self,
        user_id: str,
        old_path: str,
        new_path: str,
        new_parent: str,
        new_name: str,
    ) -> None: ...
    def move_tree(
        self, user_id: str, old_prefix: str, new_prefix: str
    ) -> None: ...
    def search_content(
        self,
        user_id: str,
        like_pattern: str,
        path_prefix: str | None = None,
    ) -> list[NodeRow]: ...
    def search_names(
        self,
        user_id: str,
        like_pattern: str,
        path_prefix: str | None = None,
    ) -> list[NodeRow]: ...

    # Tags
    def add_tag(self, user_id: str, path: str, tag: str) -> None: ...
    def remove_tag(self, user_id: str, path: str, tag: str) -> None: ...
    def get_tags_for_path(self, user_id: str, path: str) -> list[str]: ...
    def find_by_tag(
        self, user_id: str, tag: str, path_prefix: str | None = None
    ) -> list[NodeRow]: ...

    # Recent
    def list_recent(
        self, user_id: str, limit: int = 20, path_prefix: str | None = None
    ) -> list[NodeRow]: ...

    def close(self) -> None: ...
