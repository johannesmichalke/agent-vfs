# agent-vfs

The best AI agents already use filesystems as memory. Now your agent can too.

agent-vfs gives your agent a persistent virtual filesystem backed by your own database. Agents use familiar file operations (`read`, `write`, `ls`, `grep`) while data lives in SQLite or Postgres.

```bash
pip install agent-vfs
```

```python
from agent_vfs import FileSystem, open_database

db = open_database("memory.db")  # SQLite, auto-creates table
fs = FileSystem(db, "agent-1")

fs.write("/notes.md", "# Meeting Notes\n- Ship agent-vfs")
content = fs.read("/notes.md")
```

Persistent memory that survives restarts, multi-tenant by default, no external services. One table in your database. Zero dependencies for SQLite (uses Python's built-in `sqlite3`).

Also available for TypeScript: `npm install agent-vfs` ([docs](https://github.com/johannesmichalke/agent-vfs))

## Use with any AI SDK

### OpenAI SDK

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
    result = handle_tool_call(call.function.name, call.function.arguments)
    messages.append({
        "role": "tool",
        "tool_call_id": call.id,
        "content": result["text"],
    })
```

### Anthropic SDK

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

## Tools (16)

| Tool | Description | Key Options |
|------|-------------|-------------|
| `read` | Read a file | `offset`, `limit` (line range) |
| `write` | Write a file (auto-creates parent dirs) | `summary` (optional description for search/ls) |
| `edit` | Find-and-replace (unique match required) | |
| `multi_edit` | Multiple find-and-replace edits in one call | |
| `append` | Append to a file (creates if missing) | |
| `ls` | List directory | `recursive`, `summaries` |
| `mkdir` | Create directory (idempotent, creates parents) | |
| `rm` | Remove file or directory (recursive) | |
| `grep` | Search file contents (regex) | `case_insensitive` |
| `glob` | Find files by name (glob pattern) | `type` (file/dir) |
| `mv` | Move or rename (overwrites target) | |
| `search` | Semantic search across all files (FTS5 + optional vectors) | `path`, `limit` |
| `tag` | Add a tag to a file or directory | |
| `untag` | Remove a tag from a file or directory | |
| `find_by_tag` | Find all files with a specific tag | `path` (scope) |
| `recent` | List recently modified files | `limit`, `path` (scope) |

## Search

Built-in full-text search (FTS5) with optional vector embeddings for hybrid semantic search.

```python
from agent_vfs import FileSystem, open_database
from agent_vfs.search import open_search

db = open_database("memory.db")

# FTS5 only (zero dependencies):
search = open_search(db, user_id)

# Hybrid FTS5 + vector (just add an API key):
search = open_search(db, user_id, "openai", os.environ["OPENAI_API_KEY"])

fs = FileSystem(db, user_id, search_index=search)

fs.write("/notes.md", "Architecture decisions", summary="Key design choices")
results = fs.search("architecture")
```

Supported embedding providers: `openai`, `openai-large`, `voyage`, `voyage-large`, `mistral`. Or pass a custom `url`, `model`, `api_key`, and `dimensions` to `open_embeddings()`.

## Multi-tenancy

One database, many users. Each `FileSystem` is scoped by user ID with full isolation at the DB layer:

```python
db = open_database("memory.db")
alice_fs = FileSystem(db, "alice")
bob_fs = FileSystem(db, "bob")

alice_fs.write("/secret.txt", "alice only")
bob_fs.read("/secret.txt")  # raises NotFoundError
```

## Production database

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

Custom table name:

```python
db = open_database("app.db", table_name="agent_files")
```

## License

MIT
