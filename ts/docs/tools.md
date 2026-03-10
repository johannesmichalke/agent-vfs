# Tool Reference

agent-vfs exposes 16 tools. These are the exact schemas your model receives when you use `createTools(fs)`, `openai(fs)`, or `anthropic(fs)`.

You can also inspect them at runtime:

```ts
import { tools } from "agent-vfs";
console.log(JSON.stringify(tools, null, 2));
```

## read

Read a file's content. Use offset/limit to read specific line ranges.

```json
{
  "name": "read",
  "parameters": {
    "type": "object",
    "properties": {
      "path": { "type": "string", "description": "Absolute path to the file" },
      "offset": { "type": "number", "description": "Start reading from this line number (1-based)" },
      "limit": { "type": "number", "description": "Maximum number of lines to return" }
    },
    "required": ["path"]
  }
}
```

## write

Write content to a file (creates parent directories automatically). Optionally include a short summary for indexing.

```json
{
  "name": "write",
  "parameters": {
    "type": "object",
    "properties": {
      "path": { "type": "string", "description": "Absolute path to the file" },
      "content": { "type": "string", "description": "Content to write" },
      "summary": { "type": "string", "description": "Optional 1-2 sentence summary of the file's content (used for search and ls)" }
    },
    "required": ["path", "content"]
  }
}
```

## edit

Edit a file by replacing a unique string with a new string.

```json
{
  "name": "edit",
  "parameters": {
    "type": "object",
    "properties": {
      "path": { "type": "string", "description": "Absolute path to the file" },
      "old_string": { "type": "string", "description": "The exact string to find (must be unique in the file)" },
      "new_string": { "type": "string", "description": "The replacement string" }
    },
    "required": ["path", "old_string", "new_string"]
  }
}
```

## multi_edit

Apply multiple find-and-replace edits to a single file in one operation. Each old_string must be unique.

```json
{
  "name": "multi_edit",
  "parameters": {
    "type": "object",
    "properties": {
      "path": { "type": "string", "description": "Absolute path to the file" },
      "edits": {
        "type": "array",
        "description": "List of edits to apply in order",
        "items": {
          "type": "object",
          "properties": {
            "old_string": { "type": "string", "description": "The exact string to find (must be unique)" },
            "new_string": { "type": "string", "description": "The replacement string" }
          },
          "required": ["old_string", "new_string"]
        }
      }
    },
    "required": ["path", "edits"]
  }
}
```

## append

Append content to the end of a file (creates file if it doesn't exist).

```json
{
  "name": "append",
  "parameters": {
    "type": "object",
    "properties": {
      "path": { "type": "string", "description": "Absolute path to the file" },
      "content": { "type": "string", "description": "Content to append" }
    },
    "required": ["path", "content"]
  }
}
```

## ls

List directory contents. Use recursive to see full tree. Use summaries to show file descriptions.

```json
{
  "name": "ls",
  "parameters": {
    "type": "object",
    "properties": {
      "path": { "type": "string", "description": "Absolute path to the directory" },
      "recursive": { "type": "boolean", "description": "List all files and directories recursively" },
      "summaries": { "type": "boolean", "description": "Show file summaries alongside names" }
    },
    "required": ["path"]
  }
}
```

## mkdir

Create a directory (creates parent directories automatically, idempotent).

```json
{
  "name": "mkdir",
  "parameters": {
    "type": "object",
    "properties": {
      "path": { "type": "string", "description": "Absolute path to the directory" }
    },
    "required": ["path"]
  }
}
```

## rm

Remove a file or directory (recursive for directories).

```json
{
  "name": "rm",
  "parameters": {
    "type": "object",
    "properties": {
      "path": { "type": "string", "description": "Absolute path to remove" }
    },
    "required": ["path"]
  }
}
```

## grep

Search file contents using a regex pattern. Returns matching lines with line numbers.

```json
{
  "name": "grep",
  "parameters": {
    "type": "object",
    "properties": {
      "pattern": { "type": "string", "description": "Regex pattern to search for" },
      "path": { "type": "string", "description": "Directory to search in (default: /)" },
      "case_insensitive": { "type": "boolean", "description": "Case insensitive matching" }
    },
    "required": ["pattern"]
  }
}
```

## glob

Find files by name pattern (glob).

```json
{
  "name": "glob",
  "parameters": {
    "type": "object",
    "properties": {
      "pattern": { "type": "string", "description": "Glob pattern (e.g. *.md, **/*.ts)" },
      "path": { "type": "string", "description": "Directory to search in (default: /)" },
      "type": { "type": "string", "enum": ["file", "dir"], "description": "Filter by type" }
    },
    "required": ["pattern"]
  }
}
```

## mv

Move or rename a file or directory.

```json
{
  "name": "mv",
  "parameters": {
    "type": "object",
    "properties": {
      "from": { "type": "string", "description": "Source path" },
      "to": { "type": "string", "description": "Destination path" }
    },
    "required": ["from", "to"]
  }
}
```

## search

Semantic search across all files using full-text search (BM25) and optional vector embeddings. Returns ranked results with snippets.

```json
{
  "name": "search",
  "parameters": {
    "type": "object",
    "properties": {
      "query": { "type": "string", "description": "Natural language search query" },
      "path": { "type": "string", "description": "Restrict search to files under this path" },
      "limit": { "type": "number", "description": "Maximum results to return (default: 20)" }
    },
    "required": ["query"]
  }
}
```

## tag

Add a tag to a file or directory for categorization and retrieval.

```json
{
  "name": "tag",
  "parameters": {
    "type": "object",
    "properties": {
      "path": { "type": "string", "description": "Absolute path to tag" },
      "tag": { "type": "string", "description": "Tag name (e.g. 'preferences', 'architecture', 'decision')" }
    },
    "required": ["path", "tag"]
  }
}
```

## untag

Remove a tag from a file or directory.

```json
{
  "name": "untag",
  "parameters": {
    "type": "object",
    "properties": {
      "path": { "type": "string", "description": "Absolute path to untag" },
      "tag": { "type": "string", "description": "Tag to remove" }
    },
    "required": ["path", "tag"]
  }
}
```

## find_by_tag

Find all files and directories with a specific tag.

```json
{
  "name": "find_by_tag",
  "parameters": {
    "type": "object",
    "properties": {
      "tag": { "type": "string", "description": "Tag to search for" },
      "path": { "type": "string", "description": "Restrict to files under this path" }
    },
    "required": ["tag"]
  }
}
```

## recent

List recently modified files, ordered by last update time.

```json
{
  "name": "recent",
  "parameters": {
    "type": "object",
    "properties": {
      "limit": { "type": "number", "description": "Maximum number of files to return (default: 20)" },
      "path": { "type": "string", "description": "Restrict to files under this path" }
    }
  }
}
```
