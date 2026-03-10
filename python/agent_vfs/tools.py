from __future__ import annotations

from typing import Any

from .operations import FileSystem


def _ok(text: str) -> dict[str, Any]:
    return {"text": text}


def _err(e: Exception) -> dict[str, Any]:
    return {"text": str(e), "is_error": True}


TOOLS = [
    {
        "name": "read",
        "description": "Read a file's content. Use offset/limit to read specific line ranges.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to the file"},
                "offset": {"type": "number", "description": "Start reading from this line number (1-based)"},
                "limit": {"type": "number", "description": "Maximum number of lines to return"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write",
        "description": "Write content to a file (creates parent directories automatically). Optionally include a short summary for indexing.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to the file"},
                "content": {"type": "string", "description": "Content to write"},
                "summary": {"type": "string", "description": "Optional 1-2 sentence summary of the file's content (used for search and ls)"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "edit",
        "description": "Edit a file by replacing a unique string with a new string",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to the file"},
                "old_string": {"type": "string", "description": "The exact string to find (must be unique in the file)"},
                "new_string": {"type": "string", "description": "The replacement string"},
            },
            "required": ["path", "old_string", "new_string"],
        },
    },
    {
        "name": "multi_edit",
        "description": "Apply multiple find-and-replace edits to a single file in one operation. Each old_string must be unique.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to the file"},
                "edits": {
                    "type": "array",
                    "description": "List of edits to apply in order",
                    "items": {
                        "type": "object",
                        "properties": {
                            "old_string": {"type": "string", "description": "The exact string to find (must be unique)"},
                            "new_string": {"type": "string", "description": "The replacement string"},
                        },
                        "required": ["old_string", "new_string"],
                    },
                },
            },
            "required": ["path", "edits"],
        },
    },
    {
        "name": "append",
        "description": "Append content to the end of a file (creates file if it doesn't exist)",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to the file"},
                "content": {"type": "string", "description": "Content to append"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "ls",
        "description": "List directory contents. Use recursive to see full tree. Use summaries to show file descriptions.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to the directory"},
                "recursive": {"type": "boolean", "description": "List all files and directories recursively"},
                "summaries": {"type": "boolean", "description": "Show file summaries alongside names"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "mkdir",
        "description": "Create a directory (creates parent directories automatically, idempotent)",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to the directory"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "rm",
        "description": "Remove a file or directory (recursive for directories)",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to remove"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "grep",
        "description": "Search file contents using a regex pattern. Returns matching lines with line numbers.",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern to search for"},
                "path": {"type": "string", "description": "Directory to search in (default: /)"},
                "case_insensitive": {"type": "boolean", "description": "Case insensitive matching"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "glob",
        "description": "Find files by name pattern (glob)",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern (e.g. *.md, **/*.ts)"},
                "path": {"type": "string", "description": "Directory to search in (default: /)"},
                "type": {"type": "string", "enum": ["file", "dir"], "description": "Filter by type"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "mv",
        "description": "Move or rename a file or directory",
        "parameters": {
            "type": "object",
            "properties": {
                "from": {"type": "string", "description": "Source path"},
                "to": {"type": "string", "description": "Destination path"},
            },
            "required": ["from", "to"],
        },
    },
    # ── New tools ─────────────────────────────────────────────────────────
    {
        "name": "search",
        "description": "Semantic search across all files using full-text search (BM25) and optional vector embeddings. Returns ranked results with snippets.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language search query"},
                "path": {"type": "string", "description": "Restrict search to files under this path"},
                "limit": {"type": "number", "description": "Maximum results to return (default: 20)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "tag",
        "description": "Add a tag to a file or directory for categorization and retrieval",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to tag"},
                "tag": {"type": "string", "description": "Tag name (e.g. 'preferences', 'architecture', 'decision')"},
            },
            "required": ["path", "tag"],
        },
    },
    {
        "name": "untag",
        "description": "Remove a tag from a file or directory",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to untag"},
                "tag": {"type": "string", "description": "Tag to remove"},
            },
            "required": ["path", "tag"],
        },
    },
    {
        "name": "find_by_tag",
        "description": "Find all files and directories with a specific tag",
        "parameters": {
            "type": "object",
            "properties": {
                "tag": {"type": "string", "description": "Tag to search for"},
                "path": {"type": "string", "description": "Restrict to files under this path"},
            },
            "required": ["tag"],
        },
    },
    {
        "name": "recent",
        "description": "List recently modified files, ordered by last update time",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "number", "description": "Maximum number of files to return (default: 20)"},
                "path": {"type": "string", "description": "Restrict to files under this path"},
            },
        },
    },
]


def _call_read(fs: FileSystem, args: dict) -> dict:
    try:
        full = fs.read(args["path"], offset=args.get("offset"), limit=args.get("limit"))
        if args.get("offset") or args.get("limit"):
            lines = full.split("\n")
            start = args.get("offset", 1)
            return _ok(f"[lines {start}-{start + len(lines) - 1}]\n{full}")
        return _ok(full)
    except Exception as e:
        return _err(e)


def _call_write(fs: FileSystem, args: dict) -> dict:
    try:
        fs.write(args["path"], args["content"], summary=args.get("summary"))
        size = len(args["content"].encode("utf-8"))
        return _ok(f"Wrote {size} bytes to {args['path']}")
    except Exception as e:
        return _err(e)


def _call_edit(fs: FileSystem, args: dict) -> dict:
    try:
        fs.edit(args["path"], args["old_string"], args["new_string"])
        return _ok(f"Edited {args['path']}")
    except Exception as e:
        return _err(e)


def _call_multi_edit(fs: FileSystem, args: dict) -> dict:
    try:
        fs.multi_edit(args["path"], args["edits"])
        return _ok(f"Applied {len(args['edits'])} edits to {args['path']}")
    except Exception as e:
        return _err(e)


def _call_append(fs: FileSystem, args: dict) -> dict:
    try:
        fs.append(args["path"], args["content"])
        size = len(args["content"].encode("utf-8"))
        return _ok(f"Appended {size} bytes to {args['path']}")
    except Exception as e:
        return _err(e)


def _call_ls(fs: FileSystem, args: dict) -> dict:
    try:
        entries = fs.ls(
            args["path"],
            recursive=args.get("recursive", False),
            summaries=args.get("summaries", False),
        )
        if not entries:
            return _ok("(empty directory)")
        show_summaries = args.get("summaries", False)
        if args.get("recursive"):
            lines = []
            for e in entries:
                line = f"{e['path']}/" if e["is_dir"] else f"{e['path']}  ({e['size']} bytes)"
                if show_summaries and e.get("summary"):
                    line += f"  — {e['summary']}"
                lines.append(line)
        else:
            lines = []
            for e in entries:
                line = f"{e['name']}/" if e["is_dir"] else f"{e['name']}  ({e['size']} bytes)"
                if show_summaries and e.get("summary"):
                    line += f"  — {e['summary']}"
                lines.append(line)
        return _ok("\n".join(lines))
    except Exception as e:
        return _err(e)


def _call_mkdir(fs: FileSystem, args: dict) -> dict:
    try:
        fs.mkdir(args["path"])
        return _ok(f"Created {args['path']}")
    except Exception as e:
        return _err(e)


def _call_rm(fs: FileSystem, args: dict) -> dict:
    try:
        fs.rm(args["path"])
        return _ok(f"Removed {args['path']}")
    except Exception as e:
        return _err(e)


def _call_grep(fs: FileSystem, args: dict) -> dict:
    try:
        results = fs.grep(
            args["pattern"],
            args.get("path"),
            case_insensitive=args.get("case_insensitive", False),
        )
        if not results:
            return _ok("No matches found")
        parts = []
        for r in results:
            lines = "\n".join(f"  {l['line']}: {l['text']}" for l in r["lines"])
            parts.append(f"{r['path']}\n{lines}")
        return _ok("\n\n".join(parts))
    except Exception as e:
        return _err(e)


def _call_glob(fs: FileSystem, args: dict) -> dict:
    try:
        paths = fs.glob(args["pattern"], args.get("path"), type=args.get("type"))
        if not paths:
            return _ok("No files found")
        return _ok("\n".join(paths))
    except Exception as e:
        return _err(e)


def _call_mv(fs: FileSystem, args: dict) -> dict:
    try:
        fs.mv(args["from"], args["to"])
        return _ok(f"Moved {args['from']} -> {args['to']}")
    except Exception as e:
        return _err(e)


def _call_search(fs: FileSystem, args: dict) -> dict:
    try:
        kwargs: dict = {}
        if "path" in args:
            kwargs["path"] = args["path"]
        if "limit" in args:
            kwargs["limit"] = int(args["limit"])
        results = fs.search(args["query"], **kwargs)
        if not results:
            return _ok("No results found")
        lines = []
        for i, r in enumerate(results):
            lines.append(
                f"{i + 1}. {r['path']} [{r['source']}] (score: {r['score']:.3f})\n   {r['snippet']}"
            )
        return _ok("\n\n".join(lines))
    except Exception as e:
        return _err(e)


def _call_tag(fs: FileSystem, args: dict) -> dict:
    try:
        fs.tag(args["path"], args["tag"])
        return _ok(f"Tagged {args['path']} with #{args['tag']}")
    except Exception as e:
        return _err(e)


def _call_untag(fs: FileSystem, args: dict) -> dict:
    try:
        fs.untag(args["path"], args["tag"])
        return _ok(f"Removed #{args['tag']} from {args['path']}")
    except Exception as e:
        return _err(e)


def _call_find_by_tag(fs: FileSystem, args: dict) -> dict:
    try:
        entries = fs.find_by_tag(args["tag"], args.get("path"))
        if not entries:
            return _ok(f"No files found with #{args['tag']}")
        lines = [
            f"{e['path']}/" if e["is_dir"] else f"{e['path']}  ({e['size']} bytes)"
            for e in entries
        ]
        return _ok("\n".join(lines))
    except Exception as e:
        return _err(e)


def _call_recent(fs: FileSystem, args: dict) -> dict:
    try:
        kwargs: dict = {}
        if "limit" in args and args["limit"] is not None:
            kwargs["limit"] = int(args["limit"])
        if "path" in args and args["path"] is not None:
            kwargs["path"] = args["path"]
        entries = fs.recent(**kwargs)
        if not entries:
            return _ok("No recent files")
        lines = []
        for e in entries:
            line = f"{e['path']}  ({e['size']} bytes)  [{e['updated_at']}]"
            if e.get("summary"):
                line += f"\n  {e['summary']}"
            lines.append(line)
        return _ok("\n".join(lines))
    except Exception as e:
        return _err(e)


_HANDLERS = {
    "read": _call_read,
    "write": _call_write,
    "edit": _call_edit,
    "multi_edit": _call_multi_edit,
    "append": _call_append,
    "ls": _call_ls,
    "mkdir": _call_mkdir,
    "rm": _call_rm,
    "grep": _call_grep,
    "glob": _call_glob,
    "mv": _call_mv,
    "search": _call_search,
    "tag": _call_tag,
    "untag": _call_untag,
    "find_by_tag": _call_find_by_tag,
    "recent": _call_recent,
}

tools = TOOLS


def get_tool(name: str) -> dict | None:
    for t in TOOLS:
        if t["name"] == name:
            return t
    return None


def call_tool(fs: FileSystem, name: str, args: dict) -> dict:
    handler = _HANDLERS.get(name)
    if not handler:
        return {"text": f"Unknown tool: {name}", "is_error": True}
    return handler(fs, args)
