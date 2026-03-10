"""Tests for tags, recent, and summary features."""

import pytest

from agent_vfs import FileSystem, open_database
from agent_vfs.errors import NotFoundError


@pytest.fixture
def fs(tmp_path):
    db = open_database(str(tmp_path / "test.db"))
    return FileSystem(db, "test-user")


# ── Summary ──────────────────────────────────────────────────────────────


class TestSummary:
    def test_write_with_summary(self, fs):
        fs.write("/f.txt", "content", summary="A test file")
        entries = fs.ls("/", summaries=True)
        assert entries[0]["summary"] == "A test file"

    def test_write_without_summary(self, fs):
        fs.write("/f.txt", "content")
        entries = fs.ls("/", summaries=True)
        assert entries[0]["summary"] is None

    def test_summary_preserved_on_overwrite(self, fs):
        fs.write("/f.txt", "v1", summary="My summary")
        fs.write("/f.txt", "v2")
        entries = fs.ls("/", summaries=True)
        assert entries[0]["summary"] == "My summary"

    def test_summary_overwritten_when_provided(self, fs):
        fs.write("/f.txt", "v1", summary="Old summary")
        fs.write("/f.txt", "v2", summary="New summary")
        entries = fs.ls("/", summaries=True)
        assert entries[0]["summary"] == "New summary"

    def test_ls_without_summaries_flag(self, fs):
        fs.write("/f.txt", "content", summary="A summary")
        entries = fs.ls("/")
        assert "summary" not in entries[0]

    def test_ls_with_summaries_flag(self, fs):
        fs.write("/f.txt", "content", summary="A summary")
        entries = fs.ls("/", summaries=True)
        assert "summary" in entries[0]

    def test_summary_in_recursive_ls(self, fs):
        fs.write("/a/b.txt", "content", summary="Deep file")
        entries = fs.ls("/", recursive=True, summaries=True)
        file_entry = next(e for e in entries if e["path"] == "/a/b.txt")
        assert file_entry["summary"] == "Deep file"


# ── Tags ─────────────────────────────────────────────────────────────────


class TestTags:
    def test_tag_and_retrieve(self, fs):
        fs.write("/f.txt", "content")
        fs.tag("/f.txt", "important")
        tags = fs.tags("/f.txt")
        assert tags == ["important"]

    def test_multiple_tags(self, fs):
        fs.write("/f.txt", "content")
        fs.tag("/f.txt", "alpha")
        fs.tag("/f.txt", "beta")
        tags = fs.tags("/f.txt")
        assert tags == ["alpha", "beta"]

    def test_tag_idempotent(self, fs):
        fs.write("/f.txt", "content")
        fs.tag("/f.txt", "dup")
        fs.tag("/f.txt", "dup")
        tags = fs.tags("/f.txt")
        assert tags == ["dup"]

    def test_untag(self, fs):
        fs.write("/f.txt", "content")
        fs.tag("/f.txt", "a")
        fs.tag("/f.txt", "b")
        fs.untag("/f.txt", "a")
        tags = fs.tags("/f.txt")
        assert tags == ["b"]

    def test_untag_nonexistent_is_silent(self, fs):
        fs.write("/f.txt", "content")
        fs.untag("/f.txt", "nope")  # No error

    def test_tag_nonexistent_file_raises(self, fs):
        with pytest.raises(NotFoundError):
            fs.tag("/nope.txt", "tag")

    def test_find_by_tag(self, fs):
        fs.write("/a.txt", "a")
        fs.write("/b.txt", "b")
        fs.write("/c.txt", "c")
        fs.tag("/a.txt", "important")
        fs.tag("/c.txt", "important")
        results = fs.find_by_tag("important")
        paths = [r["path"] for r in results]
        assert "/a.txt" in paths
        assert "/c.txt" in paths
        assert "/b.txt" not in paths

    def test_find_by_tag_with_path_prefix(self, fs):
        fs.write("/docs/a.txt", "a")
        fs.write("/code/b.txt", "b")
        fs.tag("/docs/a.txt", "review")
        fs.tag("/code/b.txt", "review")
        results = fs.find_by_tag("review", "/docs")
        paths = [r["path"] for r in results]
        assert "/docs/a.txt" in paths
        assert "/code/b.txt" not in paths

    def test_find_by_tag_empty(self, fs):
        results = fs.find_by_tag("nonexistent")
        assert results == []

    def test_tag_directory(self, fs):
        fs.mkdir("/mydir")
        fs.tag("/mydir", "project")
        tags = fs.tags("/mydir")
        assert tags == ["project"]

    def test_tags_cleaned_on_rm(self, fs):
        fs.write("/f.txt", "content")
        fs.tag("/f.txt", "tagged")
        fs.rm("/f.txt")
        results = fs.find_by_tag("tagged")
        assert results == []

    def test_tags_cleaned_on_rm_tree(self, fs):
        fs.write("/dir/a.txt", "a")
        fs.write("/dir/b.txt", "b")
        fs.tag("/dir/a.txt", "tagged")
        fs.tag("/dir/b.txt", "tagged")
        fs.rm("/dir")
        results = fs.find_by_tag("tagged")
        assert results == []

    def test_tags_follow_mv(self, fs):
        fs.write("/old.txt", "content")
        fs.tag("/old.txt", "moved")
        fs.mv("/old.txt", "/new.txt")
        results = fs.find_by_tag("moved")
        paths = [r["path"] for r in results]
        assert "/new.txt" in paths
        assert "/old.txt" not in paths


# ── Tags multi-tenant isolation ──────────────────────────────────────────


class TestTagsIsolation:
    def test_tags_isolated_between_users(self, tmp_path):
        db = open_database(str(tmp_path / "test.db"))
        alice = FileSystem(db, "alice")
        bob = FileSystem(db, "bob")

        alice.write("/f.txt", "alice data")
        bob.write("/f.txt", "bob data")

        alice.tag("/f.txt", "secret")
        assert alice.tags("/f.txt") == ["secret"]
        assert bob.tags("/f.txt") == []

        alice_results = alice.find_by_tag("secret")
        bob_results = bob.find_by_tag("secret")
        assert len(alice_results) == 1
        assert len(bob_results) == 0


# ── Recent ───────────────────────────────────────────────────────────────


class TestRecent:
    def test_recent_returns_files(self, fs):
        fs.write("/a.txt", "a")
        fs.write("/b.txt", "b")
        results = fs.recent()
        paths = [r["path"] for r in results]
        assert "/a.txt" in paths
        assert "/b.txt" in paths

    def test_recent_excludes_directories(self, fs):
        fs.mkdir("/mydir")
        fs.write("/f.txt", "content")
        results = fs.recent()
        paths = [r["path"] for r in results]
        assert "/f.txt" in paths
        assert "/mydir" not in paths

    def test_recent_ordering(self, fs):
        fs.write("/first.txt", "1")
        fs.write("/second.txt", "2")
        # Edit first.txt to bump its updated_at
        fs.edit("/first.txt", "1", "1-edited")
        results = fs.recent()
        # first.txt was edited last, so it should be first
        assert results[0]["path"] == "/first.txt"

    def test_recent_limit(self, fs):
        for i in range(5):
            fs.write(f"/f{i}.txt", f"content {i}")
        results = fs.recent(limit=2)
        assert len(results) == 2

    def test_recent_path_scoping(self, fs):
        fs.write("/docs/a.txt", "a")
        fs.write("/code/b.txt", "b")
        results = fs.recent(path="/docs")
        paths = [r["path"] for r in results]
        assert "/docs/a.txt" in paths
        assert "/code/b.txt" not in paths

    def test_recent_includes_summary(self, fs):
        fs.write("/f.txt", "content", summary="My file")
        results = fs.recent()
        assert results[0]["summary"] == "My file"

    def test_recent_includes_updated_at(self, fs):
        fs.write("/f.txt", "content")
        results = fs.recent()
        assert "updated_at" in results[0]
        assert results[0]["updated_at"] is not None

    def test_recent_empty(self, fs):
        results = fs.recent()
        assert results == []


# ── Recent multi-tenant isolation ────────────────────────────────────────


class TestRecentIsolation:
    def test_recent_isolated_between_users(self, tmp_path):
        db = open_database(str(tmp_path / "test.db"))
        alice = FileSystem(db, "alice")
        bob = FileSystem(db, "bob")

        alice.write("/alice-file.txt", "alice data")
        bob.write("/bob-file.txt", "bob data")

        alice_recent = alice.recent()
        bob_recent = bob.recent()

        alice_paths = [r["path"] for r in alice_recent]
        bob_paths = [r["path"] for r in bob_recent]

        assert "/alice-file.txt" in alice_paths
        assert "/bob-file.txt" not in alice_paths
        assert "/bob-file.txt" in bob_paths
        assert "/alice-file.txt" not in bob_paths
