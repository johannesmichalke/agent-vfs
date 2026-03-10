import { createRequire } from "node:module";
import type BetterSqlite3 from "better-sqlite3";
import type { Database, NodeRow } from "./types.js";
import { getSqliteSchema, validateTableName } from "../schema.js";
import { EditConflictError } from "../fs/errors.js";

const require = createRequire(import.meta.url);

interface SqliteRow {
  id: string;
  user_id: string;
  path: string;
  parent_path: string;
  name: string;
  is_dir: number;
  content: string | null;
  summary: string | null;
  version: number;
  size: number;
  created_at: string;
  updated_at: string;
}

function rowToNode(row: SqliteRow): NodeRow {
  return {
    id: row.id,
    user_id: row.user_id,
    path: row.path,
    parent_path: row.parent_path,
    name: row.name,
    is_dir: row.is_dir === 1,
    content: row.content,
    summary: row.summary,
    version: row.version,
    size: row.size,
    created_at: row.created_at,
    updated_at: row.updated_at,
  };
}

export class SqliteDatabase implements Database {
  private db: BetterSqlite3.Database;
  private table: string;

  constructor(dbPath: string, options?: { tableName?: string }) {
    const Database = require("better-sqlite3") as typeof BetterSqlite3;
    this.db = new Database(dbPath);
    this.db.pragma("journal_mode = WAL");
    this.db.pragma("foreign_keys = ON");
    this.table = validateTableName(options?.tableName ?? "nodes");
  }

  /** Expose the underlying better-sqlite3 instance for extensions (e.g. sqlite-vec). */
  get rawDb(): BetterSqlite3.Database {
    return this.db;
  }

  get tableName(): string {
    return this.table;
  }

  async initialize(): Promise<void> {
    this.db.exec(getSqliteSchema(this.table));
  }

  async getNode(userId: string, path: string): Promise<NodeRow | undefined> {
    const row = this.db
      .prepare(`SELECT * FROM ${this.table} WHERE user_id = ? AND path = ?`)
      .get(userId, path) as SqliteRow | undefined;
    return row ? rowToNode(row) : undefined;
  }

  async listChildren(userId: string, parentPath: string): Promise<NodeRow[]> {
    const rows = this.db
      .prepare(
        `SELECT * FROM ${this.table} WHERE user_id = ? AND parent_path = ? ORDER BY is_dir DESC, name ASC`
      )
      .all(userId, parentPath) as SqliteRow[];
    return rows.map(rowToNode);
  }

  async listDescendants(userId: string, pathPrefix: string): Promise<NodeRow[]> {
    if (pathPrefix === "/") {
      const rows = this.db
        .prepare(`SELECT * FROM ${this.table} WHERE user_id = ? ORDER BY path ASC`)
        .all(userId) as SqliteRow[];
      return rows.map(rowToNode);
    }
    const rows = this.db
      .prepare(
        `SELECT * FROM ${this.table} WHERE user_id = ? AND (path = ? OR path LIKE ?) ORDER BY path ASC`
      )
      .all(userId, pathPrefix, pathPrefix + "/%") as SqliteRow[];
    return rows.map(rowToNode);
  }

  async upsertNode(node: Omit<NodeRow, "created_at" | "updated_at">): Promise<void> {
    this.db
      .prepare(
        `INSERT INTO ${this.table} (id, user_id, path, parent_path, name, is_dir, content, summary, version, size)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
         ON CONFLICT(user_id, path) DO UPDATE SET
           content = excluded.content,
           summary = excluded.summary,
           version = excluded.version,
           size = excluded.size,
           updated_at = datetime('now')`
      )
      .run(
        node.id,
        node.user_id,
        node.path,
        node.parent_path,
        node.name,
        node.is_dir ? 1 : 0,
        node.content,
        node.summary,
        node.version,
        node.size
      );

    // Update FTS index for files
    if (!node.is_dir && node.content != null) {
      this.ftsUpsert(node.user_id, node.path, node.content, node.summary);
    }
  }

  async updateContent(
    userId: string,
    path: string,
    content: string,
    size: number,
    version: number
  ): Promise<void> {
    const result = this.db
      .prepare(
        `UPDATE ${this.table} SET content = ?, size = ?, version = ?, updated_at = datetime('now')
         WHERE user_id = ? AND path = ? AND version = ?`
      )
      .run(content, size, version, userId, path, version - 1);
    if (result.changes === 0) {
      throw new EditConflictError(`Concurrent edit detected on ${path} (expected version ${version - 1})`);
    }

    // Update FTS index
    const node = this.db
      .prepare(`SELECT summary FROM ${this.table} WHERE user_id = ? AND path = ?`)
      .get(userId, path) as { summary: string | null } | undefined;
    this.ftsUpsert(userId, path, content, node?.summary ?? null);
  }

  async updateSummary(userId: string, path: string, summary: string | null): Promise<void> {
    this.db
      .prepare(
        `UPDATE ${this.table} SET summary = ?, updated_at = datetime('now')
         WHERE user_id = ? AND path = ?`
      )
      .run(summary, userId, path);

    // Update FTS index
    const node = this.db
      .prepare(`SELECT content FROM ${this.table} WHERE user_id = ? AND path = ?`)
      .get(userId, path) as { content: string | null } | undefined;
    if (node?.content != null) {
      this.ftsUpsert(userId, path, node.content, summary);
    }
  }

  async deleteNode(userId: string, path: string): Promise<void> {
    this.db
      .prepare(`DELETE FROM ${this.table} WHERE user_id = ? AND path = ?`)
      .run(userId, path);
    this.ftsRemove(userId, path);
    this.db
      .prepare(`DELETE FROM ${this.table}_tags WHERE user_id = ? AND path = ?`)
      .run(userId, path);
  }

  async deleteTree(userId: string, pathPrefix: string): Promise<void> {
    this.db
      .prepare(
        `DELETE FROM ${this.table} WHERE user_id = ? AND (path = ? OR path LIKE ?)`
      )
      .run(userId, pathPrefix, pathPrefix + "/%");
    // Clean up FTS entries
    this.db
      .prepare(
        `DELETE FROM ${this.table}_fts WHERE user_id = ? AND (path = ? OR path LIKE ?)`
      )
      .run(userId, pathPrefix, pathPrefix + "/%");
    // Clean up tags
    this.db
      .prepare(
        `DELETE FROM ${this.table}_tags WHERE user_id = ? AND (path = ? OR path LIKE ?)`
      )
      .run(userId, pathPrefix, pathPrefix + "/%");
  }

  async moveNode(
    userId: string,
    oldPath: string,
    newPath: string,
    newParent: string,
    newName: string
  ): Promise<void> {
    this.db
      .prepare(
        `UPDATE ${this.table} SET path = ?, parent_path = ?, name = ?, updated_at = datetime('now')
         WHERE user_id = ? AND path = ?`
      )
      .run(newPath, newParent, newName, userId, oldPath);

    // Update FTS path
    this.db
      .prepare(
        `UPDATE ${this.table}_fts SET path = ? WHERE user_id = ? AND path = ?`
      )
      .run(newPath, userId, oldPath);

    // Update tags path
    this.db
      .prepare(
        `UPDATE ${this.table}_tags SET path = ? WHERE user_id = ? AND path = ?`
      )
      .run(newPath, userId, oldPath);
  }

  async moveTree(userId: string, oldPrefix: string, newPrefix: string): Promise<void> {
    const rows = this.db
      .prepare(
        `SELECT path, parent_path FROM ${this.table} WHERE user_id = ? AND path LIKE ?`
      )
      .all(userId, oldPrefix + "/%") as Array<{
      path: string;
      parent_path: string;
    }>;

    const update = this.db.prepare(
      `UPDATE ${this.table} SET path = ?, parent_path = ?, updated_at = datetime('now')
       WHERE user_id = ? AND path = ?`
    );

    const updateFts = this.db.prepare(
      `UPDATE ${this.table}_fts SET path = ? WHERE user_id = ? AND path = ?`
    );

    const updateTags = this.db.prepare(
      `UPDATE ${this.table}_tags SET path = ? WHERE user_id = ? AND path = ?`
    );

    const transaction = this.db.transaction(() => {
      for (const row of rows) {
        const newPath = newPrefix + row.path.slice(oldPrefix.length);
        const newParentPath =
          newPrefix + row.parent_path.slice(oldPrefix.length);
        update.run(newPath, newParentPath, userId, row.path);
        updateFts.run(newPath, userId, row.path);
        updateTags.run(newPath, userId, row.path);
      }
    });
    transaction();
  }

  async searchContent(
    userId: string,
    likePattern: string,
    pathPrefix?: string
  ): Promise<NodeRow[]> {
    if (pathPrefix && pathPrefix !== "/") {
      const rows = this.db
        .prepare(
          `SELECT * FROM ${this.table} WHERE user_id = ? AND is_dir = 0
           AND content LIKE ? ESCAPE '\\'
           AND (path = ? OR path LIKE ?)`
        )
        .all(userId, `%${likePattern}%`, pathPrefix, pathPrefix + "/%") as SqliteRow[];
      return rows.map(rowToNode);
    }
    const rows = this.db
      .prepare(
        `SELECT * FROM ${this.table} WHERE user_id = ? AND is_dir = 0
         AND content LIKE ? ESCAPE '\\'`
      )
      .all(userId, `%${likePattern}%`) as SqliteRow[];
    return rows.map(rowToNode);
  }

  async searchNames(
    userId: string,
    likePattern: string,
    pathPrefix?: string
  ): Promise<NodeRow[]> {
    if (pathPrefix && pathPrefix !== "/") {
      const rows = this.db
        .prepare(
          `SELECT * FROM ${this.table} WHERE user_id = ? AND name LIKE ? ESCAPE '\\'
           AND (path = ? OR path LIKE ?)`
        )
        .all(userId, likePattern, pathPrefix, pathPrefix + "/%") as SqliteRow[];
      return rows.map(rowToNode);
    }
    const rows = this.db
      .prepare(
        `SELECT * FROM ${this.table} WHERE user_id = ? AND name LIKE ? ESCAPE '\\'`
      )
      .all(userId, likePattern) as SqliteRow[];
    return rows.map(rowToNode);
  }

  // ── Tags ──────────────────────────────────────────────────────────────

  async addTag(userId: string, path: string, tag: string): Promise<void> {
    this.db
      .prepare(
        `INSERT OR IGNORE INTO ${this.table}_tags (user_id, path, tag) VALUES (?, ?, ?)`
      )
      .run(userId, path, tag);
  }

  async removeTag(userId: string, path: string, tag: string): Promise<void> {
    this.db
      .prepare(
        `DELETE FROM ${this.table}_tags WHERE user_id = ? AND path = ? AND tag = ?`
      )
      .run(userId, path, tag);
  }

  async getTagsForPath(userId: string, path: string): Promise<string[]> {
    const rows = this.db
      .prepare(
        `SELECT tag FROM ${this.table}_tags WHERE user_id = ? AND path = ? ORDER BY tag`
      )
      .all(userId, path) as Array<{ tag: string }>;
    return rows.map((r) => r.tag);
  }

  async findByTag(userId: string, tag: string, pathPrefix?: string): Promise<NodeRow[]> {
    if (pathPrefix && pathPrefix !== "/") {
      const rows = this.db
        .prepare(
          `SELECT n.* FROM ${this.table} n
           INNER JOIN ${this.table}_tags t ON n.user_id = t.user_id AND n.path = t.path
           WHERE n.user_id = ? AND t.tag = ?
           AND (n.path = ? OR n.path LIKE ?)
           ORDER BY n.path`
        )
        .all(userId, tag, pathPrefix, pathPrefix + "/%") as SqliteRow[];
      return rows.map(rowToNode);
    }
    const rows = this.db
      .prepare(
        `SELECT n.* FROM ${this.table} n
         INNER JOIN ${this.table}_tags t ON n.user_id = t.user_id AND n.path = t.path
         WHERE n.user_id = ? AND t.tag = ?
         ORDER BY n.path`
      )
      .all(userId, tag) as SqliteRow[];
    return rows.map(rowToNode);
  }

  // ── Recent ────────────────────────────────────────────────────────────

  async listRecent(userId: string, limit: number = 20, pathPrefix?: string): Promise<NodeRow[]> {
    if (pathPrefix && pathPrefix !== "/") {
      const rows = this.db
        .prepare(
          `SELECT * FROM ${this.table}
           WHERE user_id = ? AND is_dir = 0
           AND (path = ? OR path LIKE ?)
           ORDER BY updated_at DESC LIMIT ?`
        )
        .all(userId, pathPrefix, pathPrefix + "/%", limit) as SqliteRow[];
      return rows.map(rowToNode);
    }
    const rows = this.db
      .prepare(
        `SELECT * FROM ${this.table}
         WHERE user_id = ? AND is_dir = 0
         ORDER BY updated_at DESC LIMIT ?`
      )
      .all(userId, limit) as SqliteRow[];
    return rows.map(rowToNode);
  }

  // ── FTS5 ──────────────────────────────────────────────────────────────

  ftsSearch(
    userId: string,
    query: string,
    pathPrefix?: string,
    limit: number = 20
  ): Array<{ path: string; snippet: string; rank: number }> {
    // Escape FTS5 special characters for safe querying
    const safeQuery = query.replace(/["*^(){}[\]:]/g, " ").trim();
    if (!safeQuery) return [];

    // Use implicit AND by splitting into tokens
    const ftsQuery = safeQuery
      .split(/\s+/)
      .filter(Boolean)
      .map((t) => `"${t}"`)
      .join(" ");

    if (pathPrefix && pathPrefix !== "/") {
      const rows = this.db
        .prepare(
          `SELECT path, snippet(${this.table}_fts, 0, '>>>', '<<<', '...', 32) as snippet, rank
           FROM ${this.table}_fts
           WHERE ${this.table}_fts MATCH ? AND user_id = ?
           AND (path = ? OR path LIKE ?)
           ORDER BY rank LIMIT ?`
        )
        .all(ftsQuery, userId, pathPrefix, pathPrefix + "/%", limit) as Array<{
        path: string;
        snippet: string;
        rank: number;
      }>;
      return rows;
    }

    const rows = this.db
      .prepare(
        `SELECT path, snippet(${this.table}_fts, 0, '>>>', '<<<', '...', 32) as snippet, rank
         FROM ${this.table}_fts
         WHERE ${this.table}_fts MATCH ? AND user_id = ?
         ORDER BY rank LIMIT ?`
      )
      .all(ftsQuery, userId, limit) as Array<{
      path: string;
      snippet: string;
      rank: number;
    }>;
    return rows;
  }

  // ── Chunks (for vector search) ────────────────────────────────────────

  upsertChunks(userId: string, nodePath: string, chunks: Array<{ index: number; content: string; id: string }>): void {
    // Remove old chunks for this path
    this.db
      .prepare(`DELETE FROM ${this.table}_chunks WHERE user_id = ? AND node_path = ?`)
      .run(userId, nodePath);

    const insert = this.db.prepare(
      `INSERT INTO ${this.table}_chunks (id, user_id, node_path, chunk_index, content)
       VALUES (?, ?, ?, ?, ?)`
    );

    const transaction = this.db.transaction(() => {
      for (const chunk of chunks) {
        insert.run(chunk.id, userId, nodePath, chunk.index, chunk.content);
      }
    });
    transaction();
  }

  getChunks(userId: string, nodePath: string): Array<{ id: string; chunk_index: number; content: string }> {
    return this.db
      .prepare(
        `SELECT id, chunk_index, content FROM ${this.table}_chunks
         WHERE user_id = ? AND node_path = ? ORDER BY chunk_index`
      )
      .all(userId, nodePath) as Array<{ id: string; chunk_index: number; content: string }>;
  }

  deleteChunks(userId: string, nodePath: string): void {
    this.db
      .prepare(`DELETE FROM ${this.table}_chunks WHERE user_id = ? AND node_path = ?`)
      .run(userId, nodePath);
  }

  // ── FTS5 internal helpers ─────────────────────────────────────────────

  private ftsUpsert(userId: string, path: string, content: string, summary: string | null): void {
    // Delete existing entry first (FTS5 doesn't support UPDATE well)
    this.db
      .prepare(`DELETE FROM ${this.table}_fts WHERE user_id = ? AND path = ?`)
      .run(userId, path);
    this.db
      .prepare(
        `INSERT INTO ${this.table}_fts (content, summary, user_id, path) VALUES (?, ?, ?, ?)`
      )
      .run(content, summary ?? "", userId, path);
  }

  private ftsRemove(userId: string, path: string): void {
    this.db
      .prepare(`DELETE FROM ${this.table}_fts WHERE user_id = ? AND path = ?`)
      .run(userId, path);
  }

  async close(): Promise<void> {
    this.db.close();
  }
}
