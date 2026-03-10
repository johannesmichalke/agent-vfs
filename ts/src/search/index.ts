import { randomUUID } from "node:crypto";
import type { SqliteDatabase } from "../db/sqlite.js";
import type { EmbeddingProvider, SearchResult, SearchOptions } from "./types.js";
import { splitIntoChunks } from "./chunker.js";
import { openEmbeddings } from "./embeddings.js";

/**
 * Hybrid search index combining FTS5 (keyword/BM25) with optional vector search.
 *
 * - Without an EmbeddingProvider: uses FTS5 only (zero dependencies).
 * - With an EmbeddingProvider: uses hybrid FTS5 + vector scoring.
 *
 * Currently SQLite-only. Postgres support can be added via tsvector + pgvector.
 */
export class SearchIndex {
  private vecTableCreated = false;

  constructor(
    private db: SqliteDatabase,
    private userId: string,
    private embeddingProvider?: EmbeddingProvider
  ) {}

  /**
   * Index a file's content (and optional summary) for search.
   * Call this after write/edit/append operations.
   */
  async index(path: string, content: string, summary?: string | null): Promise<void> {
    // FTS5 is handled automatically by SqliteDatabase.upsertNode / updateContent

    // Vector indexing (optional)
    if (this.embeddingProvider && content.length > 0) {
      await this.indexVectors(path, content);
    }
  }

  /**
   * Remove a file from the search index.
   * Call this after rm operations.
   */
  async remove(path: string): Promise<void> {
    // FTS5 removal is handled by SqliteDatabase.deleteNode / deleteTree

    // Remove vector chunks
    this.db.deleteChunks(this.userId, path);
    if (this.vecTableCreated) {
      this.removeVectors(path);
    }
  }

  /**
   * Search for files matching the query.
   */
  async search(query: string, opts?: SearchOptions): Promise<SearchResult[]> {
    const limit = opts?.limit ?? 20;
    const ftsWeight = opts?.ftsWeight ?? 0.3;
    const vectorWeight = 1 - ftsWeight;
    const pathPrefix = opts?.path;

    // FTS5 search
    const ftsResults = this.db.ftsSearch(this.userId, query, pathPrefix, limit);

    // Normalize FTS scores (rank is negative in FTS5 — more negative = better)
    const ftsMap = new Map<string, number>();
    if (ftsResults.length > 0) {
      const maxRank = Math.max(...ftsResults.map((r) => Math.abs(r.rank)));
      for (const r of ftsResults) {
        ftsMap.set(r.path, maxRank > 0 ? Math.abs(r.rank) / maxRank : 1);
      }
    }

    // Vector search (optional)
    const vectorMap = new Map<string, { score: number; snippet: string }>();
    if (this.embeddingProvider && this.vecTableCreated) {
      const vectorResults = await this.searchVectors(query, pathPrefix, limit);
      for (const r of vectorResults) {
        vectorMap.set(r.path, { score: r.score, snippet: r.snippet });
      }
    }

    // Merge results
    const allPaths = new Set([...ftsMap.keys(), ...vectorMap.keys()]);
    const merged: SearchResult[] = [];

    for (const path of allPaths) {
      const ftsScore = ftsMap.get(path) ?? 0;
      const vecResult = vectorMap.get(path);
      const vecScore = vecResult?.score ?? 0;

      let score: number;
      let source: SearchResult["source"];

      if (ftsMap.has(path) && vectorMap.has(path)) {
        score = ftsWeight * ftsScore + vectorWeight * vecScore;
        source = "hybrid";
      } else if (vectorMap.has(path)) {
        score = vectorWeight * vecScore;
        source = "vector";
      } else {
        score = ftsWeight * ftsScore;
        source = "fts";
      }

      // Use FTS snippet if available, otherwise vector snippet
      const ftsEntry = ftsResults.find((r) => r.path === path);
      const snippet = ftsEntry?.snippet ?? vecResult?.snippet ?? "";

      merged.push({ path, snippet, score, source });
    }

    // Sort by score descending
    merged.sort((a, b) => b.score - a.score);
    return merged.slice(0, limit);
  }

  // ── Vector indexing internals ─────────────────────────────────────────

  private async indexVectors(path: string, content: string): Promise<void> {
    const provider = this.embeddingProvider!;
    if (!this.ensureVecTable(provider.dimensions)) {
      // sqlite-vec not available — skip vector indexing silently
      return;
    }

    // Remove old vectors first
    this.removeVectors(path);

    const chunks = splitIntoChunks(content);
    const chunkRecords = chunks.map((c, i) => ({
      id: randomUUID(),
      index: i,
      content: c,
    }));

    // Store chunks in the chunks table
    this.db.upsertChunks(this.userId, path, chunkRecords);

    // Generate embeddings
    const embeddings = await provider.embed(chunks);

    // Insert new vectors
    const rawDb = this.db.rawDb;
    const insert = rawDb.prepare(
      `INSERT INTO ${this.db.tableName}_vec (chunk_id, embedding) VALUES (?, ?)`
    );
    const transaction = rawDb.transaction(() => {
      for (let i = 0; i < chunkRecords.length; i++) {
        insert.run(chunkRecords[i].id, new Float32Array(embeddings[i]));
      }
    });
    transaction();
  }

  private removeVectors(path: string): void {
    // Get chunk IDs for this path, then delete from vec table
    const chunks = this.db.getChunks(this.userId, path);
    if (chunks.length === 0) return;

    const rawDb = this.db.rawDb;
    const del = rawDb.prepare(`DELETE FROM ${this.db.tableName}_vec WHERE chunk_id = ?`);
    const transaction = rawDb.transaction(() => {
      for (const chunk of chunks) {
        del.run(chunk.id);
      }
    });
    transaction();
  }

  private async searchVectors(
    query: string,
    pathPrefix: string | undefined,
    limit: number
  ): Promise<Array<{ path: string; score: number; snippet: string }>> {
    const provider = this.embeddingProvider!;
    const [queryEmbedding] = await provider.embed([query]);

    const rawDb = this.db.rawDb;
    const tableName = this.db.tableName;

    // Find nearest chunks via sqlite-vec
    const rows = rawDb
      .prepare(
        `SELECT v.chunk_id, v.distance, c.node_path, c.content
         FROM ${tableName}_vec v
         INNER JOIN ${tableName}_chunks c ON v.chunk_id = c.id
         WHERE c.user_id = ? AND v.embedding MATCH ?
         ORDER BY v.distance
         LIMIT ?`
      )
      .all(this.userId, new Float32Array(queryEmbedding), limit * 2) as Array<{
      chunk_id: string;
      distance: number;
      node_path: string;
      content: string;
    }>;

    // Filter by path prefix if needed
    let filtered = rows;
    if (pathPrefix && pathPrefix !== "/") {
      filtered = rows.filter(
        (r) => r.node_path === pathPrefix || r.node_path.startsWith(pathPrefix + "/")
      );
    }

    // Deduplicate by path (keep best chunk per file)
    const byPath = new Map<string, { score: number; snippet: string }>();
    for (const row of filtered) {
      const score = 1 / (1 + row.distance); // Convert distance to similarity
      if (!byPath.has(row.node_path) || byPath.get(row.node_path)!.score < score) {
        const snippet =
          row.content.length > 200
            ? row.content.slice(0, 200) + "..."
            : row.content;
        byPath.set(row.node_path, { score, snippet });
      }
    }

    return Array.from(byPath.entries()).map(([path, { score, snippet }]) => ({
      path,
      score,
      snippet,
    }));
  }

  /** Returns true if vec table is available. */
  private ensureVecTable(dimensions: number): boolean {
    if (this.vecTableCreated) return true;
    try {
      this.db.rawDb.exec(
        `CREATE VIRTUAL TABLE IF NOT EXISTS ${this.db.tableName}_vec USING vec0(
          chunk_id TEXT PRIMARY KEY,
          embedding float[${dimensions}]
        )`
      );
      this.vecTableCreated = true;
      return true;
    } catch {
      // sqlite-vec extension not loaded — vector search will be disabled
      return false;
    }
  }
}

/**
 * One-liner to create a SearchIndex with an embedding provider.
 *
 * ```ts
 * // FTS5 only (no API key needed):
 * const search = openSearch(db, userId);
 *
 * // Hybrid FTS5 + vector (just add API key):
 * const search = openSearch(db, userId, "openai", process.env.OPENAI_API_KEY);
 *
 * const fs = new FileSystem(db, userId, { searchIndex: search });
 * ```
 */
export function openSearch(
  db: SqliteDatabase,
  userId: string,
  provider?: string,
  apiKey?: string
): SearchIndex {
  let embeddingProvider: EmbeddingProvider | undefined;
  if (provider && apiKey) {
    embeddingProvider = openEmbeddings(provider, apiKey);
  }
  return new SearchIndex(db, userId, embeddingProvider);
}

export { splitIntoChunks } from "./chunker.js";
export { openEmbeddings } from "./embeddings.js";
export type { EmbeddingProvider, SearchResult, SearchOptions } from "./types.js";
