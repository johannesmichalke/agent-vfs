# agent-vfs — Deferred Features

## Links / Symlinks
Bidirectional file relationships (`link(source, target, relation)`) for connecting related memories.
Alternative: **symlinks** — more filesystem-native, lets agents "file" the same document under multiple directories without duplication. Implementation: `is_symlink` flag + `target_path` column on nodes table, resolve on read.

**Why interesting:** Zep and A-MEM (NeurIPS 2025) both found that relational structure matters for complex recall. Symlinks are simpler and more natural than a separate links table.

## Version History / Diff
Store previous content on update, expose a `diff` tool to show what changed over time. The optimistic locking `version` field already exists but content history is not tracked.

**Challenge:** Can't use git since storage is a database. Would need a `node_history` table storing `(node_id, version, content, updated_at)`. Could get large — consider only storing diffs (e.g. structured patch format) rather than full snapshots.

**Why interesting:** HN community loved this from the "Git for AI memory" project — "you can see exactly what the AI knew then."

## Access Control / User Groups
Currently agent-vfs has `user_id` isolation (all-or-nothing). Groups would allow fine-grained permissions:
- Read-only access to shared knowledge bases
- Write access only to the agent's own workspace
- Sensitive files restricted to certain roles

**Design sketch:**
- Files get a `group` column (or use path-based rules)
- `FileSystem` constructor takes a `groups: string[]` + `role: "read" | "write" | "admin"`
- Enforcement at the FileSystem layer, not DB layer

**Why it matters:** Fits Clark-Wilson model (agent=UDI with restricted access). Not every agent loop should have access to everything. Critical for multi-agent setups.

## Temporal Decay
Exponential decay scoring for search results: `decayedScore = score * e^(-lambda * ageInDays)`.
Evergreen/pinned files skip decay. OpenClaw uses 30-day half-life by default.

**Current state:** `recent` tool exists (ORDER BY updated_at DESC). Decay would be an enhancement to `search` scoring — multiply relevance by recency factor.

## Auto-Flush / Context Compaction Hook
When an agent session approaches token limits, trigger a "save important context" flush before compaction. OpenClaw does this with a silent agentic turn + `NO_REPLY` flag.

**Not a tool** — this is application-layer behavior. But agent-vfs could provide a `summarizeAll()` helper that returns all files with summaries for the agent to review before compaction.

## Session Memory Indexing
Index conversation transcripts alongside file memory. Surfaces them in search results. OpenClaw does this with debounced async indexing (~100KB or 50 messages threshold).

## Postgres Full-Text Search + pgvector
Current search (FTS5 + sqlite-vec) is SQLite-only. Postgres equivalent would use `tsvector`/`tsquery` for full-text and `pgvector` for embeddings. The `SearchIndex` class is currently SQLite-specific — would need a `PostgresSearchIndex` variant.
