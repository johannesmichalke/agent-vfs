import pytest

from agent_vfs import FileSystem, open_database, call_tool, get_tool, tools
from agent_vfs.adapters import openai, anthropic
from agent_vfs.search import SearchIndex


@pytest.fixture
def fs(tmp_path):
    db = open_database(str(tmp_path / "test.db"))
    return FileSystem(db, "test-user")


@pytest.fixture
def search_fs(tmp_path):
    db = open_database(str(tmp_path / "test.db"))
    idx = SearchIndex(db, "test-user")
    return FileSystem(db, "test-user", search_index=idx)


class TestCallTool:
    def test_write_and_read(self, fs):
        result = call_tool(fs, "write", {"path": "/f.txt", "content": "hello"})
        assert not result.get("is_error")
        result = call_tool(fs, "read", {"path": "/f.txt"})
        assert result["text"] == "hello"

    def test_unknown_tool(self, fs):
        result = call_tool(fs, "nope", {})
        assert result["is_error"]

    def test_error_returns_text(self, fs):
        result = call_tool(fs, "read", {"path": "/missing.txt"})
        assert result["is_error"]
        assert "No such file" in result["text"]


class TestGetTool:
    def test_existing(self):
        t = get_tool("read")
        assert t is not None
        assert t["name"] == "read"

    def test_missing(self):
        assert get_tool("nope") is None


class TestToolsList:
    def test_count(self):
        assert len(tools) == 16


class TestOpenAIAdapter:
    def test_format(self, fs):
        tool_defs, handle = openai(fs)
        assert len(tool_defs) == 16
        assert tool_defs[0]["type"] == "function"
        assert "name" in tool_defs[0]["function"]

    def test_handle_string_args(self, fs):
        _, handle = openai(fs)
        result = handle("write", '{"path": "/f.txt", "content": "hi"}')
        assert not result.get("is_error")

    def test_handle_dict_args(self, fs):
        _, handle = openai(fs)
        handle("write", {"path": "/f.txt", "content": "hi"})
        result = handle("read", {"path": "/f.txt"})
        assert result["text"] == "hi"


class TestAnthropicAdapter:
    def test_format(self, fs):
        tool_defs, handle = anthropic(fs)
        assert len(tool_defs) == 16
        assert "input_schema" in tool_defs[0]

    def test_handle(self, fs):
        _, handle = anthropic(fs)
        handle("write", {"path": "/f.txt", "content": "hi"})
        result = handle("read", {"path": "/f.txt"})
        assert result["text"] == "hi"


class TestNewTools:
    def test_write_with_summary(self, fs):
        result = call_tool(fs, "write", {"path": "/f.txt", "content": "hello", "summary": "A greeting"})
        assert not result.get("is_error")
        result = call_tool(fs, "ls", {"path": "/", "summaries": True})
        assert "A greeting" in result["text"]

    def test_ls_with_summaries(self, fs):
        call_tool(fs, "write", {"path": "/f.txt", "content": "hello", "summary": "My summary"})
        result = call_tool(fs, "ls", {"path": "/", "summaries": True})
        assert "My summary" in result["text"]

    def test_tag_tool(self, fs):
        call_tool(fs, "write", {"path": "/f.txt", "content": "hello"})
        result = call_tool(fs, "tag", {"path": "/f.txt", "tag": "important"})
        assert not result.get("is_error")
        assert "Tagged" in result["text"]

    def test_untag_tool(self, fs):
        call_tool(fs, "write", {"path": "/f.txt", "content": "hello"})
        call_tool(fs, "tag", {"path": "/f.txt", "tag": "old"})
        result = call_tool(fs, "untag", {"path": "/f.txt", "tag": "old"})
        assert not result.get("is_error")
        assert "Removed" in result["text"]

    def test_find_by_tag_tool(self, fs):
        call_tool(fs, "write", {"path": "/a.txt", "content": "a"})
        call_tool(fs, "write", {"path": "/b.txt", "content": "b"})
        call_tool(fs, "tag", {"path": "/a.txt", "tag": "mytag"})
        result = call_tool(fs, "find_by_tag", {"tag": "mytag"})
        assert not result.get("is_error")
        assert "/a.txt" in result["text"]
        assert "/b.txt" not in result["text"]

    def test_find_by_tag_empty(self, fs):
        result = call_tool(fs, "find_by_tag", {"tag": "nonexistent"})
        assert not result.get("is_error")
        assert "No files found" in result["text"]

    def test_recent_tool(self, fs):
        call_tool(fs, "write", {"path": "/f.txt", "content": "hello"})
        result = call_tool(fs, "recent", {})
        assert not result.get("is_error")
        assert "/f.txt" in result["text"]

    def test_recent_empty(self, fs):
        result = call_tool(fs, "recent", {})
        assert not result.get("is_error")
        assert "No recent files" in result["text"]

    def test_recent_with_limit(self, fs):
        for i in range(5):
            call_tool(fs, "write", {"path": f"/f{i}.txt", "content": f"content {i}"})
        result = call_tool(fs, "recent", {"limit": 2})
        assert not result.get("is_error")
        # Should have at most 2 entries
        lines = [l for l in result["text"].split("\n") if l.startswith("/")]
        assert len(lines) <= 2

    def test_search_tool(self, search_fs):
        call_tool(search_fs, "write", {"path": "/f.txt", "content": "The architecture of the system"})
        result = call_tool(search_fs, "search", {"query": "architecture"})
        assert not result.get("is_error")
        assert "/f.txt" in result["text"]

    def test_search_no_results(self, search_fs):
        call_tool(search_fs, "write", {"path": "/f.txt", "content": "hello"})
        result = call_tool(search_fs, "search", {"query": "nonexistentxyz"})
        assert not result.get("is_error")
        assert "No results" in result["text"]

    def test_get_new_tools(self):
        for name in ["search", "tag", "untag", "find_by_tag", "recent"]:
            t = get_tool(name)
            assert t is not None, f"Tool '{name}' not found"
            assert t["name"] == name
