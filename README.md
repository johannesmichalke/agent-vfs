# memoryfs

The best AI agents already use filesystems as memory. Now your agent can too.

memoryfs gives your agent a persistent virtual filesystem backed by your own database. Agents use familiar file operations — `read`, `write`, `ls`, `grep` — while data lives in SQLite or Postgres.

```bash
npm install memoryfs better-sqlite3
```

```ts
import { FileSystem, openDatabase } from "memoryfs";

const db = await openDatabase("memory.db"); // SQLite, auto-creates table
const fs = new FileSystem(db, "agent-1");

await fs.write("/notes.md", "# Meeting Notes\n- Ship memoryfs");
const content = await fs.read("/notes.md");
```

Persistent memory that survives restarts, multi-tenant by default, no external services. One table in your database.

## Why filesystems?

Agents like Claude Code already store memory in files (`~/.claude/`). The pattern works because agents understand files natively — no new API to learn, no retrieval pipeline to build.

A real filesystem per user doesn't work well in production (isolation, backups, scaling). memoryfs gives you the same interface backed by a single database table. No API keys, no hosted service — just a library.

## Use with any AI SDK

### Vercel AI SDK

```ts
import { generateText } from "ai";
import { openai } from "@ai-sdk/openai";
import { FileSystem, openDatabase } from "memoryfs";
import { createTools } from "memoryfs/ai";

const db = await openDatabase("memory.db");
const fs = new FileSystem(db, userId);

const { text } = await generateText({
  model: openai("gpt-4o"),
  tools: createTools(fs),
  prompt: "Save my preferences, then list all files",
});
```

### OpenAI SDK

```ts
import OpenAI from "openai";
import { FileSystem, openDatabase, openai } from "memoryfs";

const db = await openDatabase("memory.db");
const fs = new FileSystem(db, userId);
const { tools, handleToolCall } = openai(fs);

const response = await new OpenAI().chat.completions.create({
  model: "gpt-4o",
  messages,
  tools,
});

for (const call of response.choices[0].message.tool_calls ?? []) {
  const result = await handleToolCall(call.function.name, call.function.arguments);
  messages.push({ role: "tool", tool_call_id: call.id, content: result.text });
}
```

### Anthropic SDK

```ts
import Anthropic from "@anthropic-ai/sdk";
import { FileSystem, openDatabase, anthropic } from "memoryfs";

const db = await openDatabase("memory.db");
const fs = new FileSystem(db, userId);
const { tools, handleToolCall } = anthropic(fs);

const response = await new Anthropic().messages.create({
  model: "claude-sonnet-4-20250514",
  max_tokens: 1024,
  messages,
  tools,
});

for (const block of response.content) {
  if (block.type === "tool_use") {
    const result = await handleToolCall(block.name, block.input);
    messages.push({ role: "user", content: [{ type: "tool_result", tool_use_id: block.id, content: result.text }] });
  }
}
```

### Direct tool access

```ts
import { tools, callTool, getTool } from "memoryfs";

const readTool = getTool("read");
await readTool.call(fs, { path: "/notes.md" }); // { text: "...", isError?: boolean }

// Or dispatch by name
const result = await callTool(fs, "write", { path: "/notes.md", content: "hello" });
```

## Tools (11)

| Tool | Description | Key Options |
|------|-------------|-------------|
| `read` | Read a file | `offset`, `limit` (line range) |
| `write` | Write a file (auto-creates parent dirs) | |
| `edit` | Find-and-replace (unique match required) | |
| `multi_edit` | Multiple find-and-replace edits in one call | |
| `append` | Append to a file (creates if missing) | |
| `ls` | List directory | `recursive` |
| `mkdir` | Create directory (idempotent, creates parents) | |
| `rm` | Remove file or directory (recursive) | |
| `grep` | Search file contents (regex) | `case_insensitive` |
| `glob` | Find files by name (glob pattern) | `type` (file/dir) |
| `mv` | Move or rename (overwrites target) | |

## Multi-tenancy

One database, many users. Each `FileSystem` is scoped by user ID — full isolation at the DB layer:

```ts
const db = await openDatabase("memory.db");
const aliceFs = new FileSystem(db, "alice");
const bobFs   = new FileSystem(db, "bob");

await aliceFs.write("/secret.txt", "alice only");
await bobFs.read("/secret.txt"); // throws NotFoundError
```

## Production database

In production you likely already have a Postgres database.

**Option A: Drizzle**

```ts
// db/schema.ts — add to your existing Drizzle schema
import { nodesTable } from "memoryfs/drizzle";
export { nodesTable };
```

```bash
npx drizzle-kit generate && npx drizzle-kit migrate
```

```ts
import { PostgresDatabase, FileSystem } from "memoryfs";
const db = new PostgresDatabase(existingPool); // your existing pg.Pool
const fs = new FileSystem(db, userId);
```

**Option B: Raw SQL**

```ts
import { postgresSchema } from "memoryfs/schema";
// Add to your migration tool, or:
const db = new PostgresDatabase(pool);
await db.initialize(); // CREATE TABLE IF NOT EXISTS
```

**Option C: Custom adapter**

```ts
import type { Database } from "memoryfs";

class MyDatabase implements Database {
  async getNode(userId, path) { /* ... */ }
  async upsertNode(node) { /* ... */ }
  // 12 methods total
}
```

### Custom table name

```ts
const db = await openDatabase("app.db", { tableName: "agent_files" });
```

Works with all approaches — constructors, Drizzle (`createNodesTable("agent_files")`), and raw SQL (`getPostgresSchema("agent_files")`).

## Safety

- **File size limits** — Default 10 MB max per file. Configure via `new FileSystem(db, userId, { maxFileSize: ... })`.
- **Optimistic locking** — Concurrent edits are detected and rejected (version-checked at the DB level).
- **SQL injection prevention** — Parameterized queries everywhere. Table names validated against a strict regex whitelist.
- **Tenant isolation** — All queries scoped by `user_id`. No cross-tenant access possible at the DB layer.

## API

### `openDatabase(pathOrUrl, options?): Promise<Database>`

Auto-detects SQLite (file path) or Postgres (connection URL). Creates the table automatically.

### `new FileSystem(db, userId, options?)`

Creates a user-scoped filesystem. Options: `{ maxFileSize?: number }` (default 10 MB).

### `callTool(fs, name, args): Promise<ToolResult>`

Dispatches a tool call by name. Returns `{ text: string, isError?: boolean }`. Never throws.

## Development

```bash
npm install
npm run build
npm test          # 85 tests
```

## License

MIT
