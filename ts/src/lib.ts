// Core
export { FileSystem } from "./fs/operations.js";
export type { FileSystemOptions } from "./fs/operations.js";
export { openDatabase } from "./db/index.js";
export type { Database, NodeRow } from "./db/types.js";

// Tools
export { tools, getTool, callTool } from "./tools.js";
export type { Tool, ToolResult, ToolName } from "./tools.js";

// SDK adapters
export { openai, anthropic } from "./adapters.js";

// Search
export { SearchIndex, openSearch } from "./search/index.js";
export { splitIntoChunks } from "./search/chunker.js";
export { openEmbeddings } from "./search/embeddings.js";
export type { EmbeddingProvider, SearchResult, SearchOptions } from "./search/types.js";

// Database implementations (bring-your-own-client)
export { SqliteDatabase } from "./db/sqlite.js";
export { PostgresDatabase } from "./db/postgres.js";
export type { PgClient } from "./db/postgres.js";

// Errors
export {
  NotFoundError,
  IsDirectoryError,
  NotDirectoryError,
  EditConflictError,
  FileSizeError,
} from "./fs/errors.js";
