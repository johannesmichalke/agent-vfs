# agent-vfs

The best AI agents already use filesystems as memory. Now your agent can too.

agent-vfs gives your agent a persistent virtual filesystem backed by your own database. Agents use familiar file operations (`read`, `write`, `ls`, `grep`) while data lives in SQLite or Postgres.

**TypeScript**
```bash
npm install agent-vfs better-sqlite3
```

**Python**
```bash
pip install agent-vfs
```

```ts
// TypeScript
const db = await openDatabase("memory.db");
const fs = new FileSystem(db, "agent-1");

await fs.write("/notes.md", "# Meeting Notes\n- Ship agent-vfs");
const content = await fs.read("/notes.md");
```

```python
# Python
db = open_database("memory.db")
fs = FileSystem(db, "agent-1")

fs.write("/notes.md", "# Meeting Notes\n- Ship agent-vfs")
content = fs.read("/notes.md")
```

Persistent memory that survives restarts, multi-tenant by default, no external services. One table in your database. Both packages share the same database schema, tool definitions, and API design.

## Why filesystems?

Agents like Claude Code already store memory in files (`~/.claude/`). The pattern works because agents understand files natively. No new API to learn, no retrieval pipeline to build.

A real filesystem per user doesn't work well in production (isolation, backups, scaling). agent-vfs gives you the same interface backed by a single database table. No API keys, no hosted service, just a library.

## Use with any AI SDK

### OpenAI SDK

<table>
<tr><th>TypeScript</th><th>Python</th></tr>
<tr><td>

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
  const result = await handleToolCall(
    call.function.name, call.function.arguments
  );
  messages.push({
    role: "tool", tool_call_id: call.id, content: result.text
  });
}
```

</td><td>

```python
from openai import OpenAI
from agent_vfs import FileSystem, open_database, openai

db = open_database("memory.db")
fs = FileSystem(db, user_id)
tools, handle_tool_call = openai(fs)

response = OpenAI().chat.completions.create(
    model="gpt-4o",
    messages=messages,
    tools=tools,
)

for call in response.choices[0].message.tool_calls or []:
    result = handle_tool_call(
        call.function.name, call.function.arguments
    )
    messages.append({
        "role": "tool",
        "tool_call_id": call.id,
        "content": result["text"],
    })
```

</td></tr>
</table>

### Anthropic SDK

<table>
<tr><th>TypeScript</th><th>Python</th></tr>
<tr><td>

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
    messages.push({
      role: "user",
      content: [{
        type: "tool_result",
        tool_use_id: block.id,
        content: result.text,
      }],
    });
  }
}
```

</td><td>

```python
from anthropic import Anthropic
from agent_vfs import FileSystem, open_database, anthropic

db = open_database("memory.db")
fs = FileSystem(db, user_id)
tools, handle_tool_call = anthropic(fs)

response = Anthropic().messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    messages=messages,
    tools=tools,
)

for block in response.content:
    if block.type == "tool_use":
        result = handle_tool_call(block.name, block.input)
        messages.append({
            "role": "user",
            "content": [{
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result["text"],
            }],
        })
```

</td></tr>
</table>

### Vercel AI SDK (TypeScript only)

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

### Direct tool access

```ts
// TypeScript
import { tools, callTool, getTool } from "agent-vfs";

const readTool = getTool("read");
await readTool.call(fs, { path: "/notes.md" }); // { text: "...", isError?: boolean }
const result = await callTool(fs, "write", { path: "/notes.md", content: "hello" });
```

```python
# Python
from agent_vfs import tools, call_tool, get_tool

read_tool = get_tool("read")
result = call_tool(fs, "write", {"path": "/notes.md", "content": "hello"})
```

## Example: chat agent with persistent memory

The most common pattern is an agent that loads its memory at the start of each session, then reads and writes files as it chats.

```python
from anthropic import Anthropic
from agent_vfs import FileSystem, open_database, anthropic

db = open_database("memory.db")
fs = FileSystem(db, user_id)
tools, handle_tool_call = anthropic(fs)

# Boot: load the agent's memory into the system prompt
try:
    memory = fs.read("/memory.md")
except FileNotFoundError:
    memory = "(no memory yet)"

system = f"""You are a helpful assistant with persistent memory.
Your current memory:
{memory}

You have filesystem tools. Use them to remember things across sessions.
Save important facts to /memory.md. Organize notes in folders as needed."""

messages = []

# Chat loop
while True:
    user_input = input("> ")
    messages.append({"role": "user", "content": user_input})

    response = Anthropic().messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=system,
        messages=messages,
        tools=tools,
    )

    # Handle tool calls until the model is done
    while response.stop_reason == "tool_use":
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = handle_tool_call(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result["text"],
                })
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})
        response = Anthropic().messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=system,
            messages=messages,
            tools=tools,
        )

    text = "".join(b.text for b in response.content if b.type == "text")
    print(text)
    messages.append({"role": "assistant", "content": response.content})
```

The agent will automatically use `write`, `read`, `ls`, and other tools to manage its own memory. On the next session, the boot step loads everything back.

## Tools (11)

Full tool schemas (the exact JSON your model receives) are documented in [docs/tools.md](ts/docs/tools.md).

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
// TypeScript
const aliceFs = new FileSystem(db, "alice");
const bobFs   = new FileSystem(db, "bob");

await aliceFs.write("/secret.txt", "alice only");
await bobFs.read("/secret.txt"); // throws NotFoundError
```

```python
# Python
alice_fs = FileSystem(db, "alice")
bob_fs = FileSystem(db, "bob")

alice_fs.write("/secret.txt", "alice only")
bob_fs.read("/secret.txt")  # raises NotFoundError
```

## Production database

In production you likely already have a Postgres database.

### TypeScript

**Drizzle**

```ts
// db/schema.ts
import { nodesTable } from "agent-vfs/drizzle";
export { nodesTable };
```

```bash
npx drizzle-kit generate && npx drizzle-kit migrate
```

```ts
import { PostgresDatabase, FileSystem } from "agent-vfs";
const db = new PostgresDatabase(existingPool); // your existing pg.Pool
const fs = new FileSystem(db, userId);
```

**Raw SQL**

```ts
import { postgresSchema } from "agent-vfs/schema";
const db = new PostgresDatabase(pool);
await db.initialize(); // CREATE TABLE IF NOT EXISTS
```

### Python

```bash
pip install agent-vfs[postgres]
```

```python
from agent_vfs import open_database, FileSystem

db = open_database("postgresql://user:pass@localhost/mydb")
fs = FileSystem(db, user_id)
```

Or bring your own connection:

```python
from agent_vfs.db.postgres import PostgresDatabase
import psycopg2

conn = psycopg2.connect("postgresql://...")
db = PostgresDatabase(conn)
db.initialize()
fs = FileSystem(db, user_id)
```

### Custom table name

```ts
// TypeScript
const db = await openDatabase("app.db", { tableName: "agent_files" });
```

```python
# Python
db = open_database("app.db", table_name="agent_files")
```

Works with all approaches: constructors, Drizzle (`createNodesTable("agent_files")`), and raw SQL (`get_postgres_schema("agent_files")`).

### Custom adapter

Implement the `Database` interface to use any backend:

```ts
// TypeScript
import type { Database } from "agent-vfs";

class MyDatabase implements Database {
  async getNode(userId, path) { /* ... */ }
  async upsertNode(node) { /* ... */ }
  // 12 methods total
}
```

```python
# Python — just implement the same methods
class MyDatabase:
    def get_node(self, user_id, path): ...
    def upsert_node(self, node): ...
    # 12 methods total
```

## License

MIT
