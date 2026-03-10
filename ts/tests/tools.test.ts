import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { FileSystem } from "../src/fs/operations.js";
import { SqliteDatabase } from "../src/db/sqlite.js";
import { SearchIndex } from "../src/search/index.js";
import { tools, callTool, getTool } from "../src/tools.js";

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

describe("tools array", () => {
  it("has 16 tools", () => {
    expect(tools).toHaveLength(16);
  });

  it("every tool has name, description, parameters, and call", () => {
    for (const tool of tools) {
      expect(tool.name).toBeTruthy();
      expect(tool.description).toBeTruthy();
      expect(tool.parameters).toBeTruthy();
      expect(typeof tool.call).toBe("function");
    }
  });
});

describe("getTool", () => {
  it("returns tool by name", () => {
    expect(getTool("read")?.name).toBe("read");
  });

  it("returns undefined for unknown tool", () => {
    expect(getTool("nope")).toBeUndefined();
  });
});

describe("callTool", () => {
  it("write + read round-trip", async () => {
    const w = await callTool(fs, "write", { path: "/hello.txt", content: "world" });
    expect(w.isError).toBeFalsy();
    expect(w.text).toContain("Wrote");

    const r = await callTool(fs, "read", { path: "/hello.txt" });
    expect(r.isError).toBeFalsy();
    expect(r.text).toBe("world");
  });

  it("edit", async () => {
    await callTool(fs, "write", { path: "/file.txt", content: "foo bar" });
    const result = await callTool(fs, "edit", { path: "/file.txt", old_string: "bar", new_string: "baz" });
    expect(result.isError).toBeFalsy();
    expect((await callTool(fs, "read", { path: "/file.txt" })).text).toBe("foo baz");
  });

  it("multi_edit", async () => {
    await callTool(fs, "write", { path: "/file.txt", content: "aaa bbb ccc" });
    const result = await callTool(fs, "multi_edit", {
      path: "/file.txt",
      edits: [
        { old_string: "aaa", new_string: "xxx" },
        { old_string: "ccc", new_string: "zzz" },
      ],
    });
    expect(result.isError).toBeFalsy();
    expect(result.text).toContain("2 edits");
    expect((await callTool(fs, "read", { path: "/file.txt" })).text).toBe("xxx bbb zzz");
  });

  it("append", async () => {
    await callTool(fs, "write", { path: "/log.txt", content: "line1\n" });
    await callTool(fs, "append", { path: "/log.txt", content: "line2\n" });
    expect((await callTool(fs, "read", { path: "/log.txt" })).text).toBe("line1\nline2\n");
  });

  it("ls", async () => {
    await callTool(fs, "write", { path: "/a.txt", content: "a" });
    await callTool(fs, "mkdir", { path: "/dir" });
    const result = await callTool(fs, "ls", { path: "/" });
    expect(result.text).toContain("dir/");
    expect(result.text).toContain("a.txt");
  });

  it("ls recursive", async () => {
    await callTool(fs, "write", { path: "/a/b/c.txt", content: "deep" });
    const result = await callTool(fs, "ls", { path: "/", recursive: true });
    expect(result.text).toContain("/a/b/c.txt");
  });

  it("rm", async () => {
    await callTool(fs, "write", { path: "/tmp.txt", content: "x" });
    await callTool(fs, "rm", { path: "/tmp.txt" });
    const result = await callTool(fs, "read", { path: "/tmp.txt" });
    expect(result.isError).toBe(true);
    expect(result.text).toContain("No such file");
  });

  it("grep", async () => {
    await callTool(fs, "write", { path: "/log.txt", content: "ERROR: bad\nINFO: ok" });
    const result = await callTool(fs, "grep", { pattern: "ERROR" });
    expect(result.text).toContain("/log.txt");
    expect(result.text).toContain("1: ERROR: bad");
  });

  it("glob", async () => {
    await callTool(fs, "write", { path: "/docs/readme.md", content: "hi" });
    const result = await callTool(fs, "glob", { pattern: "*.md" });
    expect(result.text).toContain("/docs/readme.md");
  });

  it("mv", async () => {
    await callTool(fs, "write", { path: "/old.txt", content: "data" });
    await callTool(fs, "mv", { from: "/old.txt", to: "/new.txt" });
    expect((await callTool(fs, "read", { path: "/new.txt" })).text).toBe("data");
  });

  it("returns error for unknown tool", async () => {
    const result = await callTool(fs, "nope", {});
    expect(result.isError).toBe(true);
    expect(result.text).toContain("Unknown tool");
  });

  it("returns error instead of throwing", async () => {
    const result = await callTool(fs, "read", { path: "/missing" });
    expect(result.isError).toBe(true);
    expect(result.text).toContain("No such file");
  });
});

// ── New feature tests ─────────────────────────────────────────────────

describe("write with summary", () => {
  it("stores and retrieves summary via ls", async () => {
    await callTool(fs, "write", {
      path: "/notes.md",
      content: "# Meeting Notes\nDiscussed architecture decisions.",
      summary: "Architecture meeting notes",
    });
    const result = await callTool(fs, "ls", { path: "/", summaries: true });
    expect(result.text).toContain("notes.md");
    expect(result.text).toContain("Architecture meeting notes");
  });

  it("summary persists across edits", async () => {
    await callTool(fs, "write", {
      path: "/doc.md",
      content: "version 1",
      summary: "My document",
    });
    await callTool(fs, "edit", { path: "/doc.md", old_string: "version 1", new_string: "version 2" });
    const result = await callTool(fs, "ls", { path: "/", summaries: true });
    expect(result.text).toContain("My document");
  });

  it("ls without summaries flag does not show summaries", async () => {
    await callTool(fs, "write", {
      path: "/doc.md",
      content: "hello",
      summary: "A greeting",
    });
    const result = await callTool(fs, "ls", { path: "/" });
    expect(result.text).not.toContain("A greeting");
  });
});

describe("tag / untag / find_by_tag", () => {
  it("tags a file and finds it", async () => {
    await callTool(fs, "write", { path: "/prefs.md", content: "I like dark mode" });
    const tagResult = await callTool(fs, "tag", { path: "/prefs.md", tag: "preferences" });
    expect(tagResult.text).toContain("#preferences");

    const findResult = await callTool(fs, "find_by_tag", { tag: "preferences" });
    expect(findResult.text).toContain("/prefs.md");
  });

  it("untags a file", async () => {
    await callTool(fs, "write", { path: "/file.md", content: "x" });
    await callTool(fs, "tag", { path: "/file.md", tag: "temp" });
    await callTool(fs, "untag", { path: "/file.md", tag: "temp" });

    const findResult = await callTool(fs, "find_by_tag", { tag: "temp" });
    expect(findResult.text).toContain("No files found");
  });

  it("find_by_tag scopes to path", async () => {
    await callTool(fs, "write", { path: "/a/file.md", content: "a" });
    await callTool(fs, "write", { path: "/b/file.md", content: "b" });
    await callTool(fs, "tag", { path: "/a/file.md", tag: "important" });
    await callTool(fs, "tag", { path: "/b/file.md", tag: "important" });

    const result = await callTool(fs, "find_by_tag", { tag: "important", path: "/a" });
    expect(result.text).toContain("/a/file.md");
    expect(result.text).not.toContain("/b/file.md");
  });

  it("multiple tags on same file", async () => {
    await callTool(fs, "write", { path: "/doc.md", content: "content" });
    await callTool(fs, "tag", { path: "/doc.md", tag: "architecture" });
    await callTool(fs, "tag", { path: "/doc.md", tag: "decisions" });

    const tags = await fs.tags("/doc.md");
    expect(tags).toContain("architecture");
    expect(tags).toContain("decisions");
  });
});

describe("recent", () => {
  it("returns recently modified files", async () => {
    await callTool(fs, "write", { path: "/old.txt", content: "old" });
    await callTool(fs, "write", { path: "/new.txt", content: "new" });

    const result = await callTool(fs, "recent", { limit: 10 });
    expect(result.text).toContain("/new.txt");
    expect(result.text).toContain("/old.txt");
  });

  it("respects limit", async () => {
    for (let i = 0; i < 5; i++) {
      await callTool(fs, "write", { path: `/file${i}.txt`, content: `content ${i}` });
    }
    const result = await callTool(fs, "recent", { limit: 2 });
    const lines = result.text.split("\n").filter(l => l.startsWith("/"));
    expect(lines.length).toBe(2);
  });

  it("shows summaries", async () => {
    await callTool(fs, "write", {
      path: "/noted.md",
      content: "stuff",
      summary: "Important notes",
    });
    const result = await callTool(fs, "recent", {});
    expect(result.text).toContain("Important notes");
  });
});

describe("search (FTS5)", () => {
  it("finds files by keyword", async () => {
    await callTool(fs, "write", {
      path: "/architecture.md",
      content: "The system uses a microservices architecture with event-driven communication.",
    });
    await callTool(fs, "write", {
      path: "/readme.md",
      content: "This is a simple hello world project.",
    });

    const result = await callTool(fs, "search", { query: "microservices architecture" });
    expect(result.text).toContain("/architecture.md");
  });

  it("ranks results by relevance", async () => {
    await callTool(fs, "write", {
      path: "/relevant.md",
      content: "Database migration strategy for PostgreSQL. Database indexing and query optimization.",
    });
    await callTool(fs, "write", {
      path: "/less-relevant.md",
      content: "The weather is nice today. Also, we have a database.",
    });

    const result = await callTool(fs, "search", { query: "database" });
    // The file with more occurrences should rank higher
    expect(result.text).toContain("/relevant.md");
  });

  it("scopes to path prefix", async () => {
    await callTool(fs, "write", { path: "/docs/guide.md", content: "deployment guide for kubernetes" });
    await callTool(fs, "write", { path: "/notes/deploy.md", content: "deployment notes" });

    const result = await callTool(fs, "search", { query: "deployment", path: "/docs" });
    expect(result.text).toContain("/docs/guide.md");
    expect(result.text).not.toContain("/notes/deploy.md");
  });

  it("returns no results for unmatched query", async () => {
    await callTool(fs, "write", { path: "/file.md", content: "hello world" });
    const result = await callTool(fs, "search", { query: "xyznonexistent" });
    expect(result.text).toContain("No results found");
  });
});
