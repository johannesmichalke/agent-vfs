"""Tests for FTS5 search, chunker, and embeddings."""

import pytest

from agent_vfs import FileSystem, open_database
from agent_vfs.search import SearchIndex, split_into_chunks, open_embeddings


@pytest.fixture
def db(tmp_path):
    return open_database(str(tmp_path / "test.db"))


@pytest.fixture
def search_fs(db):
    """FileSystem with SearchIndex attached (FTS only)."""
    idx = SearchIndex(db, "test-user")
    return FileSystem(db, "test-user", search_index=idx)


# ── FTS5 Search ──────────────────────────────────────────────────────────


class TestFTSSearch:
    def test_basic_keyword_search(self, search_fs):
        search_fs.write("/notes.txt", "The quick brown fox jumps over the lazy dog")
        results = search_fs.search("fox")
        assert len(results) >= 1
        assert any(r["path"] == "/notes.txt" for r in results)

    def test_search_returns_snippet(self, search_fs):
        search_fs.write("/f.txt", "Python is a great programming language")
        results = search_fs.search("Python")
        assert len(results) >= 1
        assert "Python" in results[0]["snippet"] or "python" in results[0]["snippet"].lower()

    def test_search_no_results(self, search_fs):
        search_fs.write("/f.txt", "hello world")
        results = search_fs.search("nonexistentxyz")
        assert results == []

    def test_search_porter_stemming(self, search_fs):
        search_fs.write("/f.txt", "The runners were running fast")
        results = search_fs.search("running")
        assert len(results) >= 1

    def test_search_multi_word(self, search_fs):
        search_fs.write("/a.txt", "Python web framework")
        search_fs.write("/b.txt", "Python data science")
        results = search_fs.search("Python web")
        # Both may match "Python" but the one with both words should rank higher
        assert len(results) >= 1

    def test_search_path_scoping(self, search_fs):
        search_fs.write("/docs/guide.txt", "Setup instructions for the project")
        search_fs.write("/code/main.py", "Setup the main application")
        results = search_fs.search("Setup", path="/docs")
        paths = [r["path"] for r in results]
        assert "/docs/guide.txt" in paths
        assert "/code/main.py" not in paths

    def test_search_limit(self, search_fs):
        for i in range(10):
            search_fs.write(f"/f{i}.txt", f"common keyword number {i}")
        results = search_fs.search("common", limit=3)
        assert len(results) <= 3

    def test_search_special_chars_safe(self, search_fs):
        search_fs.write("/f.txt", "test content with special chars")
        # These should not cause FTS5 syntax errors
        results = search_fs.search('test "with quotes"')
        # Just verify no exception is raised
        assert isinstance(results, list)

    def test_search_empty_query(self, search_fs):
        search_fs.write("/f.txt", "content")
        results = search_fs.search("")
        assert results == []

    def test_search_whitespace_query(self, search_fs):
        search_fs.write("/f.txt", "content")
        results = search_fs.search("   ")
        assert results == []

    def test_search_reindexes_on_edit(self, search_fs):
        search_fs.write("/f.txt", "old keyword")
        search_fs.edit("/f.txt", "old keyword", "new keyword")
        old_results = search_fs.search("old")
        new_results = search_fs.search("new")
        assert len(old_results) == 0
        assert len(new_results) >= 1

    def test_search_reindexes_on_append(self, search_fs):
        search_fs.write("/f.txt", "start")
        search_fs.append("/f.txt", " appended content")
        results = search_fs.search("appended")
        assert len(results) >= 1

    def test_search_removes_on_rm(self, search_fs):
        search_fs.write("/f.txt", "searchable content")
        search_fs.rm("/f.txt")
        results = search_fs.search("searchable")
        assert results == []

    def test_search_summary_indexed(self, search_fs):
        search_fs.write("/f.txt", "plain content", summary="Architecture decisions for the project")
        results = search_fs.search("Architecture")
        assert len(results) >= 1
        assert results[0]["path"] == "/f.txt"

    def test_search_source_is_fts(self, search_fs):
        search_fs.write("/f.txt", "content for fts")
        results = search_fs.search("content")
        assert len(results) >= 1
        assert results[0]["source"] == "fts"

    def test_search_requires_search_index(self, db):
        fs = FileSystem(db, "test-user")  # No search_index
        with pytest.raises(RuntimeError, match="SearchIndex"):
            fs.search("query")


# ── Chunker ──────────────────────────────────────────────────────────────


class TestChunker:
    def test_short_text_single_chunk(self):
        text = "Hello world"
        chunks = split_into_chunks(text)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_long_text_multiple_chunks(self):
        words = [f"word{i}" for i in range(1000)]
        text = " ".join(words)
        chunks = split_into_chunks(text, chunk_size=100, overlap=20)
        assert len(chunks) > 1
        # Each chunk should have roughly 100 words
        for chunk in chunks:
            assert len(chunk.split()) <= 100

    def test_overlap_between_chunks(self):
        words = [f"w{i}" for i in range(200)]
        text = " ".join(words)
        chunks = split_into_chunks(text, chunk_size=100, overlap=20)
        assert len(chunks) >= 2
        # Check that chunks overlap
        first_words = set(chunks[0].split())
        second_words = set(chunks[1].split())
        overlap = first_words & second_words
        assert len(overlap) > 0

    def test_empty_text(self):
        chunks = split_into_chunks("")
        assert len(chunks) == 1
        assert chunks[0] == ""

    def test_custom_chunk_size(self):
        words = [f"w{i}" for i in range(500)]
        text = " ".join(words)
        chunks = split_into_chunks(text, chunk_size=50, overlap=10)
        assert len(chunks) > 5


# ── Embeddings ───────────────────────────────────────────────────────────


class TestEmbeddings:
    def test_openai_preset(self):
        provider = open_embeddings("openai", api_key="test-key")
        assert provider.dimensions == 1536

    def test_openai_large_preset(self):
        provider = open_embeddings("openai-large", api_key="test-key")
        assert provider.dimensions == 3072

    def test_voyage_preset(self):
        provider = open_embeddings("voyage", api_key="test-key")
        assert provider.dimensions == 512

    def test_voyage_large_preset(self):
        provider = open_embeddings("voyage-large", api_key="test-key")
        assert provider.dimensions == 1024

    def test_mistral_preset(self):
        provider = open_embeddings("mistral", api_key="test-key")
        assert provider.dimensions == 1024

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown embedding provider"):
            open_embeddings("nonexistent", api_key="test-key")

    def test_missing_api_key_raises(self):
        with pytest.raises(ValueError, match="API key required"):
            open_embeddings("openai")

    def test_custom_provider(self):
        provider = open_embeddings(
            url="https://example.com/embed",
            model="custom-model",
            api_key="test-key",
            dimensions=768,
        )
        assert provider.dimensions == 768

    def test_custom_provider_missing_fields(self):
        with pytest.raises(ValueError, match="Custom provider requires"):
            open_embeddings(url="https://example.com/embed")


# ── Mock-based hybrid search ─────────────────────────────────────────────


class MockEmbeddingProvider:
    """Mock embedding provider for testing hybrid search without HTTP calls."""

    def __init__(self, dimensions: int = 4):
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        # Return deterministic vectors based on text length
        return [[float(len(t) % 10) / 10.0] * self._dimensions for t in texts]


class TestMockHybridSearch:
    def test_search_with_mock_embeddings(self, db):
        """Test that SearchIndex works with a mock embedding provider.

        Note: This test may skip vector indexing if sqlite-vec is not installed,
        but it should still work with FTS5 alone.
        """
        mock_provider = MockEmbeddingProvider()
        idx = SearchIndex(db, "test-user", mock_provider)
        fs = FileSystem(db, "test-user", search_index=idx)

        fs.write("/f.txt", "Important architecture decisions about the system")
        results = fs.search("architecture")
        assert len(results) >= 1
        assert any(r["path"] == "/f.txt" for r in results)
