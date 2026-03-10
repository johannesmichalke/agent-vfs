/**
 * Pluggable embedding provider interface.
 *
 * Bring your own embeddings — OpenAI, Voyage, local GGUF, etc.
 *
 * ```ts
 * const provider: EmbeddingProvider = {
 *   dimensions: 1536,
 *   async embed(texts) {
 *     const res = await openai.embeddings.create({ model: "text-embedding-3-small", input: texts });
 *     return res.data.map(d => d.embedding);
 *   },
 * };
 * ```
 */
export interface EmbeddingProvider {
  /** Dimensionality of the embedding vectors. */
  dimensions: number;
  /** Embed one or more texts. Returns one vector per input text. */
  embed(texts: string[]): Promise<number[][]>;
}

export interface SearchResult {
  /** File path. */
  path: string;
  /** Matched text snippet. */
  snippet: string;
  /** Combined relevance score (higher = more relevant). */
  score: number;
  /** Which source contributed this result. */
  source: "fts" | "vector" | "hybrid";
}

export interface SearchOptions {
  /** Restrict search to files under this path prefix. */
  path?: string;
  /** Maximum number of results. Default: 20. */
  limit?: number;
  /**
   * Weight for FTS vs vector results when both are available.
   * 0 = vector only, 1 = FTS only, 0.3 = 30% FTS + 70% vector (default).
   */
  ftsWeight?: number;
}
