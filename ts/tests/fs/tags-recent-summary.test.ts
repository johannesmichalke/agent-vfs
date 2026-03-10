import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { FileSystem } from "../../src/fs/operations.js";
import { SqliteDatabase } from "../../src/db/sqlite.js";
import { SearchIndex } from "../../src/search/index.js";

let db: SqliteDatabase;
let fs: FileSystem;

beforeEach(async () => {
  db = new SqliteDatabase(":memory:");
  await db.initialize();
  const searchIdx = new SearchIndex(db, "test-user");
  fs = new FileSystem(db, "test-user", { searchIndex: searchIdx });
});

afterEach(async () => {
  await db.close();
});

// ── Summary ─────────────────────────────────────────────────────────────

describe("summary", () => {
  it("write with summary stores it", async () => {
    await fs.write("/doc.md", "Full content here", { summary: "A doc about stuff" });
    const entries = await fs.ls("/", { summaries: true });
    expect(entries[0].summary).toBe("A doc about stuff");
  });

  it("summary persists when content is edited", async () => {
    await fs.write("/doc.md", "original", { summary: "My summary" });
    await fs.edit("/doc.md", "original", "modified");
    const entries = await fs.ls("/", { summaries: true });
    expect(entries[0].summary).toBe("My summary");
  });

  it("summary persists when content is appended", async () => {
    await fs.write("/doc.md", "start", { summary: "Summary here" });
    await fs.append("/doc.md", " more");
    const entries = await fs.ls("/", { summaries: true });
    expect(entries[0].summary).toBe("Summary here");
  });

  it("write without summary preserves existing summary", async () => {
    await fs.write("/doc.md", "v1", { summary: "Preserved" });
    await fs.write("/doc.md", "v2");
    const entries = await fs.ls("/", { summaries: true });
    expect(entries[0].summary).toBe("Preserved");
  });

  it("write with new summary overwrites old summary", async () => {
    await fs.write("/doc.md", "v1", { summary: "Old" });
    await fs.write("/doc.md", "v2", { summary: "New" });
    const entries = await fs.ls("/", { summaries: true });
    expect(entries[0].summary).toBe("New");
  });

  it("ls without summaries flag omits summary field", async () => {
    await fs.write("/doc.md", "content", { summary: "Sum" });
    const entries = await fs.ls("/");
    expect(entries[0]).not.toHaveProperty("summary");
  });

  it("ls with summaries on recursive listing", async () => {
    await fs.write("/a/b.md", "content", { summary: "Deep summary" });
    const entries = await fs.ls("/", { recursive: true, summaries: true });
    const file = entries.find((e) => e.path === "/a/b.md");
    expect(file?.summary).toBe("Deep summary");
  });

  it("directories have null summary", async () => {
    await fs.mkdir("/mydir");
    const entries = await fs.ls("/", { summaries: true });
    expect(entries[0].summary).toBeNull();
  });
});

// ── Tags ────────────────────────────────────────────────────────────────

describe("tags", () => {
  it("tag and retrieve tags for a file", async () => {
    await fs.write("/prefs.md", "dark mode");
    await fs.tag("/prefs.md", "preferences");
    await fs.tag("/prefs.md", "ui");

    const tags = await fs.tags("/prefs.md");
    expect(tags).toContain("preferences");
    expect(tags).toContain("ui");
    expect(tags).toHaveLength(2);
  });

  it("tagging is idempotent", async () => {
    await fs.write("/doc.md", "x");
    await fs.tag("/doc.md", "test");
    await fs.tag("/doc.md", "test");
    const tags = await fs.tags("/doc.md");
    expect(tags).toHaveLength(1);
  });

  it("untag removes specific tag", async () => {
    await fs.write("/doc.md", "x");
    await fs.tag("/doc.md", "a");
    await fs.tag("/doc.md", "b");
    await fs.untag("/doc.md", "a");

    const tags = await fs.tags("/doc.md");
    expect(tags).toEqual(["b"]);
  });

  it("untag on non-tagged path is no-op", async () => {
    await fs.write("/doc.md", "x");
    await fs.untag("/doc.md", "nonexistent"); // should not throw
    const tags = await fs.tags("/doc.md");
    expect(tags).toEqual([]);
  });

  it("findByTag returns matching files", async () => {
    await fs.write("/a.md", "a");
    await fs.write("/b.md", "b");
    await fs.write("/c.md", "c");
    await fs.tag("/a.md", "important");
    await fs.tag("/b.md", "important");

    const results = await fs.findByTag("important");
    expect(results).toHaveLength(2);
    expect(results.map((r) => r.path).sort()).toEqual(["/a.md", "/b.md"]);
  });

  it("findByTag scopes to path prefix", async () => {
    await fs.write("/docs/a.md", "a");
    await fs.write("/notes/b.md", "b");
    await fs.tag("/docs/a.md", "ref");
    await fs.tag("/notes/b.md", "ref");

    const results = await fs.findByTag("ref", "/docs");
    expect(results).toHaveLength(1);
    expect(results[0].path).toBe("/docs/a.md");
  });

  it("findByTag returns empty for unknown tag", async () => {
    const results = await fs.findByTag("nope");
    expect(results).toEqual([]);
  });

  it("tag on non-existent file throws NotFoundError", async () => {
    await expect(fs.tag("/missing.md", "test")).rejects.toThrow("No such file");
  });

  it("tags on directory", async () => {
    await fs.mkdir("/project");
    await fs.tag("/project", "active");
    const tags = await fs.tags("/project");
    expect(tags).toEqual(["active"]);
  });

  it("tags are cleaned up when file is deleted", async () => {
    await fs.write("/doc.md", "x");
    await fs.tag("/doc.md", "temp");
    await fs.rm("/doc.md");

    const results = await fs.findByTag("temp");
    expect(results).toEqual([]);
  });

  it("tags are cleaned up when directory tree is deleted", async () => {
    await fs.write("/dir/a.md", "a");
    await fs.write("/dir/b.md", "b");
    await fs.tag("/dir/a.md", "tagged");
    await fs.tag("/dir/b.md", "tagged");
    await fs.rm("/dir");

    const results = await fs.findByTag("tagged");
    expect(results).toEqual([]);
  });

  it("tags follow file on mv", async () => {
    await fs.write("/old.md", "content");
    await fs.tag("/old.md", "important");
    await fs.mv("/old.md", "/new.md");

    const tags = await fs.tags("/new.md");
    expect(tags).toEqual(["important"]);
    // Old path should have no tags
    const oldTags = await fs.tags("/old.md");
    expect(oldTags).toEqual([]);
  });

  it("tags are returned sorted alphabetically", async () => {
    await fs.write("/doc.md", "x");
    await fs.tag("/doc.md", "zebra");
    await fs.tag("/doc.md", "alpha");
    await fs.tag("/doc.md", "middle");

    const tags = await fs.tags("/doc.md");
    expect(tags).toEqual(["alpha", "middle", "zebra"]);
  });
});

// ── Recent ──────────────────────────────────────────────────────────────

describe("recent", () => {
  it("returns files ordered by most recently updated", async () => {
    await fs.write("/first.md", "1");
    await fs.write("/second.md", "2");
    // Edit bumps updated_at — ensures different timestamps even in fast in-memory SQLite
    await fs.edit("/first.md", "1", "1 updated");

    const recent = await fs.recent({ limit: 10 });
    // /first.md was edited last, so it should be first
    expect(recent[0].path).toBe("/first.md");
    expect(recent).toHaveLength(2);
  });

  it("edit bumps file to top of recent", async () => {
    await fs.write("/a.md", "alpha");
    await fs.write("/b.md", "beta");
    // Edit /a.md — should become most recent
    await fs.edit("/a.md", "alpha", "alpha updated");

    const recent = await fs.recent({ limit: 10 });
    expect(recent[0].path).toBe("/a.md");
  });

  it("append bumps file to top of recent", async () => {
    await fs.write("/a.md", "alpha");
    await fs.write("/b.md", "beta");
    await fs.append("/a.md", " more");

    const recent = await fs.recent({ limit: 10 });
    expect(recent[0].path).toBe("/a.md");
  });

  it("respects limit parameter", async () => {
    for (let i = 0; i < 10; i++) {
      await fs.write(`/file${i}.md`, `content ${i}`);
    }
    const recent = await fs.recent({ limit: 3 });
    expect(recent).toHaveLength(3);
  });

  it("defaults to 20 results", async () => {
    for (let i = 0; i < 25; i++) {
      await fs.write(`/file${i}.md`, `content ${i}`);
    }
    const recent = await fs.recent();
    expect(recent).toHaveLength(20);
  });

  it("scopes to path prefix", async () => {
    await fs.write("/docs/a.md", "a");
    await fs.write("/notes/b.md", "b");
    await fs.write("/docs/c.md", "c");

    const recent = await fs.recent({ path: "/docs" });
    expect(recent).toHaveLength(2);
    expect(recent.every((r) => r.path.startsWith("/docs/"))).toBe(true);
  });

  it("only returns files, not directories", async () => {
    await fs.mkdir("/mydir");
    await fs.write("/mydir/file.md", "content");

    const recent = await fs.recent({ limit: 10 });
    expect(recent.every((r) => !r.path.endsWith("/mydir"))).toBe(true);
  });

  it("includes summaries in results", async () => {
    await fs.write("/doc.md", "content", { summary: "A great document" });
    const recent = await fs.recent();
    expect(recent[0].summary).toBe("A great document");
  });

  it("returns empty when no files exist", async () => {
    const recent = await fs.recent();
    expect(recent).toEqual([]);
  });

  it("includes updatedAt timestamp", async () => {
    await fs.write("/doc.md", "content");
    const recent = await fs.recent();
    expect(recent[0].updatedAt).toBeTruthy();
    expect(typeof recent[0].updatedAt).toBe("string");
  });
});

// ── Multi-tenant isolation ──────────────────────────────────────────────

describe("multi-tenant isolation", () => {
  it("tags are isolated between users", async () => {
    const fs1 = new FileSystem(db, "user1");
    const fs2 = new FileSystem(db, "user2");

    await fs1.write("/doc.md", "user1 content");
    await fs2.write("/doc.md", "user2 content");
    await fs1.tag("/doc.md", "shared-tag");

    const user1Tags = await fs1.tags("/doc.md");
    const user2Tags = await fs2.tags("/doc.md");
    expect(user1Tags).toEqual(["shared-tag"]);
    expect(user2Tags).toEqual([]);
  });

  it("recent is isolated between users", async () => {
    const fs1 = new FileSystem(db, "user1");
    const fs2 = new FileSystem(db, "user2");

    await fs1.write("/private.md", "secret");

    const user2Recent = await fs2.recent();
    expect(user2Recent).toEqual([]);
  });

  it("search is isolated between users", async () => {
    const searchIdx1 = new SearchIndex(db, "user1");
    const searchIdx2 = new SearchIndex(db, "user2");
    const fs1 = new FileSystem(db, "user1", { searchIndex: searchIdx1 });
    const fs2 = new FileSystem(db, "user2", { searchIndex: searchIdx2 });

    await fs1.write("/secret.md", "classified information");

    const results = await fs2.search("classified");
    expect(results).toEqual([]);
  });
});
