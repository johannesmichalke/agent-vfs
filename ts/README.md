# agent-vfs

The best AI agents already use filesystems as memory. Now your agent can too.

agent-vfs gives your agent a persistent virtual filesystem backed by your own database. Agents use familiar file operations (`read`, `write`, `ls`, `grep`) while data lives in SQLite or Postgres.

```bash
npm install agent-vfs better-sqlite3
```

```ts
import { FileSystem, openDatabase } from "agent-vfs";

const db = await openDatabase("memory.db"); // SQLite, auto-creates table
const fs = new FileSystem(db, "agent-1");

await fs.write("/notes.md", "# Meeting Notes\n- Ship agent-vfs");
const content = await fs.read("/notes.md");
```

Persistent memory that survives restarts, multi-tenant by default, no external services. One table in your database.

Also available for Python: `pip install agent-vfs` ([docs](https://github.com/johannesmichalke/agent-vfs))

## Use with any AI SDK

### Vercel AI SDK

```ts
import { generateText } from "ai";
import { openai } from "@ai-sdk/openai";
import { FileSystem, openDatabase } from "agent-vfs";
import { createTools } from "agent-vfs/ai";

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
import { FileSystem, openDatabase, openai } from "agent-vfs";

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
import { FileSystem, openDatabase, anthropic } from "agent-vfs";

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

## Tools (11)

Full tool schemas: [docs/tools.md](docs/tools.md)

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

One database, many users. Each `FileSystem` is scoped by user ID with full isolation at the DB layer:

```ts
const db = await openDatabase("memory.db");
const aliceFs = new FileSystem(db, "alice");
const bobFs   = new FileSystem(db, "bob");

await aliceFs.write("/secret.txt", "alice only");
await bobFs.read("/secret.txt"); // throws NotFoundError
```

## Production database

```ts
import { PostgresDatabase, FileSystem } from "agent-vfs";
const db = new PostgresDatabase(existingPool); // your existing pg.Pool
const fs = new FileSystem(db, userId);
```

Custom table name:

```ts
const db = await openDatabase("app.db", { tableName: "agent_files" });
```

## License

MIT
