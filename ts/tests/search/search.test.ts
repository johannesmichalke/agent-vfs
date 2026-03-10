import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { FileSystem } from "../../src/fs/operations.js";
import { SqliteDatabase } from "../../src/db/sqlite.js";
import { SearchIndex } from "../../src/search/index.js";
import type { EmbeddingProvider } from "../../src/search/types.js";
import { splitIntoChunks } from "../../src/search/chunker.js";

let db: SqliteDatabase;
let fs: FileSystem;
let searchIdx: SearchIndex;

beforeEach(async () => {
  db = new SqliteDatabase(":memory:");
  await db.initialize();
  searchIdx = new SearchIndex(db, "test-user");
  fs = new FileSystem(db, "test-user", { searchIndex: searchIdx });
});

afterEach(async () => {
  await db.close();
});

// ── FTS5 Search ─────────────────────────────────────────────────────────

describe("FTS5 search", () => {
  it("finds file by exact keyword", async () => {
    await fs.write("/doc.md", "PostgreSQL is a relational database");
    const results = await fs.search("PostgreSQL");
    expect(results.length).toBe(1);
    expect(results[0].path).toBe("/doc.md");
    expect(results[0].source).toBe("fts");
  });

  it("uses porter stemming (finds 'running' when searching 'run')", async () => {
    await fs.write("/log.md", "The server is running smoothly");
    const results = await fs.search("run");
    expect(results.length).toBe(1);
    expect(results[0].path).toBe("/log.md");
  });

  it("finds across multiple files and ranks by relevance", async () => {
    await fs.write("/a.md", "database database database optimization");
    await fs.write("/b.md", "the database is located nearby");
    await fs.write("/c.md", "no match here at all");

    const results = await fs.search("database");
    expect(results.length).toBe(2);
    // File with more occurrences should rank higher
    expect(results[0].path).toBe("/a.md");
    expect(results[1].path).toBe("/b.md");
  });

  it("returns snippets with match markers", async () => {
    await fs.write("/doc.md", "The quick brown fox jumps over the lazy dog");
    const results = await fs.search("fox");
    expect(results.length).toBe(1);
    expect(results[0].snippet).toContain("fox");
  });

  it("handles multi-word queries (implicit AND)", async () => {
    await fs.write("/both.md", "The cat sat on the mat");
    await fs.write("/only-cat.md", "The cat is sleeping");
    await fs.write("/only-mat.md", "The mat is blue");

    const results = await fs.search("cat mat");
    // Only the file with both words should match
    expect(results.length).toBe(1);
    expect(results[0].path).toBe("/both.md");
  });

  it("scopes to path prefix", async () => {
    await fs.write("/docs/api.md", "REST API documentation");
    await fs.write("/notes/api.md", "API meeting notes");

    const results = await fs.search("API", { path: "/docs" });
    expect(results.length).toBe(1);
    expect(results[0].path).toBe("/docs/api.md");
  });

  it("respects limit", async () => {
    for (let i = 0; i < 10; i++) {
      await fs.write(`/file${i}.md`, `matching keyword content ${i}`);
    }
    const results = await fs.search("keyword", { limit: 3 });
    expect(results.length).toBe(3);
  });

  it("returns empty for no match", async () => {
    await fs.write("/doc.md", "hello world");
    const results = await fs.search("xyznonexistent");
    expect(results.length).toBe(0);
  });

  it("handles special characters in query safely", async () => {
    await fs.write("/doc.md", "hello (world) [test]");
    const results = await fs.search("hello (world)");
    // Should not crash, may or may not match depending on sanitization
    expect(Array.isArray(results)).toBe(true);
  });

  it("indexes summary alongside content", async () => {
    await fs.write("/doc.md", "Some unrelated content here", {
      summary: "Architecture decision record for microservices",
    });
    const results = await fs.search("microservices");
    expect(results.length).toBe(1);
    expect(results[0].path).toBe("/doc.md");
  });

  it("re-indexes on edit", async () => {
    await fs.write("/doc.md", "original content about cats");
    let results = await fs.search("cats");
    expect(results.length).toBe(1);

    await fs.edit("/doc.md", "cats", "dogs");
    results = await fs.search("cats");
    expect(results.length).toBe(0);
    results = await fs.search("dogs");
    expect(results.length).toBe(1);
  });

  it("re-indexes on append", async () => {
    await fs.write("/doc.md", "hello");
    await fs.append("/doc.md", " world database");

    const results = await fs.search("database");
    expect(results.length).toBe(1);
  });

  it("removes from index on rm", async () => {
    await fs.write("/doc.md", "searchable content");
    await fs.rm("/doc.md");

    const results = await fs.search("searchable");
    expect(results.length).toBe(0);
  });

  it("handles empty query gracefully", async () => {
    await fs.write("/doc.md", "content");
    const results = await fs.search("");
    expect(results.length).toBe(0);
  });

  it("handles whitespace-only query", async () => {
    await fs.write("/doc.md", "content");
    const results = await fs.search("   ");
    expect(results.length).toBe(0);
  });
});

// ── Search without SearchIndex ──────────────────────────────────────────

describe("search without SearchIndex", () => {
  it("throws helpful error when no SearchIndex configured", async () => {
    const plainFs = new FileSystem(db, "test-user");
    await expect(plainFs.search("hello")).rejects.toThrow("SearchIndex");
  });
});

// ── Chunker ─────────────────────────────────────────────────────────────

describe("splitIntoChunks", () => {
  it("returns single chunk for short text", () => {
    const chunks = splitIntoChunks("hello world");
    expect(chunks).toEqual(["hello world"]);
  });

  it("splits long text into overlapping chunks", () => {
    const words = Array.from({ length: 1000 }, (_, i) => `word${i}`);
    const text = words.join(" ");
    const chunks = splitIntoChunks(text, { chunkSize: 400, overlap: 80 });

    expect(chunks.length).toBeGreaterThan(1);
    // Check overlap: last 80 words of chunk 0 should appear in chunk 1
    const chunk0Words = chunks[0].split(" ");
    const chunk1Words = chunks[1].split(" ");
    const tail = chunk0Words.slice(-80);
    const head = chunk1Words.slice(0, 80);
    expect(tail).toEqual(head);
  });

  it("uses custom chunk size and overlap", () => {
    const words = Array.from({ length: 100 }, (_, i) => `w${i}`);
    const text = words.join(" ");
    const chunks = splitIntoChunks(text, { chunkSize: 30, overlap: 10 });
    expect(chunks.length).toBeGreaterThan(3);
  });

  it("handles text exactly at chunk size", () => {
    const words = Array.from({ length: 400 }, (_, i) => `w${i}`);
    const text = words.join(" ");
    const chunks = splitIntoChunks(text);
    expect(chunks).toEqual([text]);
  });
});

// ── Mock Embedding Provider ─────────────────────────────────────────────

describe("hybrid search with mock embeddings", () => {
  function createMockProvider(): EmbeddingProvider {
    // Simple mock: hash text to a deterministic vector
    return {
      dimensions: 4,
      async embed(texts: string[]): Promise<number[][]> {
        return texts.map((text) => {
          // Simple deterministic embedding based on character codes
          const hash = [0, 0, 0, 0];
          for (let i = 0; i < text.length; i++) {
            hash[i % 4] += text.charCodeAt(i);
          }
          const norm = Math.sqrt(hash.reduce((a, b) => a + b * b, 0));
          return hash.map((v) => v / (norm || 1));
        });
      },
    };
  }

  it("creates SearchIndex with mock embeddings without crashing", async () => {
    const mockDb = new SqliteDatabase(":memory:");
    await mockDb.initialize();
    const provider = createMockProvider();
    const idx = new SearchIndex(mockDb, "test-user", provider);

    // Note: sqlite-vec is not installed, so vector indexing will silently skip.
    // FTS still works.
    const mockFs = new FileSystem(mockDb, "test-user", { searchIndex: idx });
    await mockFs.write("/doc.md", "hello world");
    const results = await mockFs.search("hello");
    expect(results.length).toBe(1);

    await mockDb.close();
  });
});
