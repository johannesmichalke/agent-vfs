import type { FileSystem } from "./fs/operations.js";

export interface ToolResult {
  text: string;
  isError?: boolean;
}

export interface Tool {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
  call(fs: FileSystem, args: Record<string, unknown>): Promise<ToolResult>;
}

function ok(text: string): ToolResult {
  return { text };
}

function err(e: unknown): ToolResult {
  return { text: (e as Error).message, isError: true };
}

export const tools: Tool[] = [
  {
    name: "read",
    description: "Read a file's content. Use offset/limit to read specific line ranges.",
    parameters: {
      type: "object",
      properties: {
        path: { type: "string", description: "Absolute path to the file" },
        offset: { type: "number", description: "Start reading from this line number (1-based)" },
        limit: { type: "number", description: "Maximum number of lines to return" },
      },
      required: ["path"],
    },
    async call(fs, args) {
      try {
        const full = await fs.read(args.path as string);
        if (args.offset || args.limit) {
          const lines = full.split("\n");
          const start = (args.offset as number) ?? 1;
          const count = (args.limit as number) ?? lines.length;
          const slice = lines.slice(Math.max(0, start - 1), start - 1 + count);
          return ok(`[lines ${start}-${start + slice.length - 1} of ${lines.length}]\n${slice.join("\n")}`);
        }
        return ok(full);
      } catch (e) { return err(e); }
    },
  },
  {
    name: "write",
    description: "Write content to a file (creates parent directories automatically). Optionally include a short summary for indexing.",
    parameters: {
      type: "object",
      properties: {
        path: { type: "string", description: "Absolute path to the file" },
        content: { type: "string", description: "Content to write" },
        summary: { type: "string", description: "Optional 1-2 sentence summary of the file's content (used for search and ls)" },
      },
      required: ["path", "content"],
    },
    async call(fs, args) {
      try {
        await fs.write(args.path as string, args.content as string, {
          summary: args.summary as string | undefined,
        });
        return ok(`Wrote ${Buffer.byteLength(args.content as string)} bytes to ${args.path}`);
      } catch (e) { return err(e); }
    },
  },
  {
    name: "edit",
    description: "Edit a file by replacing a unique string with a new string",
    parameters: {
      type: "object",
      properties: {
        path: { type: "string", description: "Absolute path to the file" },
        old_string: { type: "string", description: "The exact string to find (must be unique in the file)" },
        new_string: { type: "string", description: "The replacement string" },
      },
      required: ["path", "old_string", "new_string"],
    },
    async call(fs, args) {
      try {
        await fs.edit(args.path as string, args.old_string as string, args.new_string as string);
        return ok(`Edited ${args.path}`);
      } catch (e) { return err(e); }
    },
  },
  {
    name: "multi_edit",
    description: "Apply multiple find-and-replace edits to a single file in one operation. Each old_string must be unique.",
    parameters: {
      type: "object",
      properties: {
        path: { type: "string", description: "Absolute path to the file" },
        edits: {
          type: "array",
          description: "List of edits to apply in order",
          items: {
            type: "object",
            properties: {
              old_string: { type: "string", description: "The exact string to find (must be unique)" },
              new_string: { type: "string", description: "The replacement string" },
            },
            required: ["old_string", "new_string"],
          },
        },
      },
      required: ["path", "edits"],
    },
    async call(fs, args) {
      try {
        await fs.multiEdit(args.path as string, args.edits as Array<{ old_string: string; new_string: string }>);
        return ok(`Applied ${(args.edits as unknown[]).length} edits to ${args.path}`);
      } catch (e) { return err(e); }
    },
  },
  {
    name: "append",
    description: "Append content to the end of a file (creates file if it doesn't exist)",
    parameters: {
      type: "object",
      properties: {
        path: { type: "string", description: "Absolute path to the file" },
        content: { type: "string", description: "Content to append" },
      },
      required: ["path", "content"],
    },
    async call(fs, args) {
      try {
        await fs.append(args.path as string, args.content as string);
        return ok(`Appended ${Buffer.byteLength(args.content as string)} bytes to ${args.path}`);
      } catch (e) { return err(e); }
    },
  },
  {
    name: "ls",
    description: "List directory contents. Use recursive to see full tree. Use summaries to show file descriptions.",
    parameters: {
      type: "object",
      properties: {
        path: { type: "string", description: "Absolute path to the directory" },
        recursive: { type: "boolean", description: "List all files and directories recursively" },
        summaries: { type: "boolean", description: "Show file summaries alongside names" },
      },
      required: ["path"],
    },
    async call(fs, args) {
      try {
        const entries = await fs.ls(args.path as string, {
          recursive: args.recursive as boolean | undefined,
          summaries: args.summaries as boolean | undefined,
        });
        if (entries.length === 0) return ok("(empty directory)");

        const showSummaries = args.summaries as boolean | undefined;

        if (args.recursive) {
          return ok(entries.map(e => {
            let line = e.isDir ? `${e.path}/` : `${e.path}  (${e.size} bytes)`;
            if (showSummaries && e.summary) line += `  — ${e.summary}`;
            return line;
          }).join("\n"));
        }
        return ok(entries.map(e => {
          let line = e.isDir ? `${e.name}/` : `${e.name}  (${e.size} bytes)`;
          if (showSummaries && e.summary) line += `  — ${e.summary}`;
          return line;
        }).join("\n"));
      } catch (e) { return err(e); }
    },
  },
  {
    name: "mkdir",
    description: "Create a directory (creates parent directories automatically, idempotent)",
    parameters: {
      type: "object",
      properties: {
        path: { type: "string", description: "Absolute path to the directory" },
      },
      required: ["path"],
    },
    async call(fs, args) {
      try {
        await fs.mkdir(args.path as string);
        return ok(`Created ${args.path}`);
      } catch (e) { return err(e); }
    },
  },
  {
    name: "rm",
    description: "Remove a file or directory (recursive for directories)",
    parameters: {
      type: "object",
      properties: {
        path: { type: "string", description: "Absolute path to remove" },
      },
      required: ["path"],
    },
    async call(fs, args) {
      try {
        await fs.rm(args.path as string);
        return ok(`Removed ${args.path}`);
      } catch (e) { return err(e); }
    },
  },
  {
    name: "grep",
    description: "Search file contents using a regex pattern. Returns matching lines with line numbers.",
    parameters: {
      type: "object",
      properties: {
        pattern: { type: "string", description: "Regex pattern to search for" },
        path: { type: "string", description: "Directory to search in (default: /)" },
        case_insensitive: { type: "boolean", description: "Case insensitive matching" },
      },
      required: ["pattern"],
    },
    async call(fs, args) {
      try {
        const results = await fs.grep(
          args.pattern as string,
          args.path as string | undefined,
          { case_insensitive: args.case_insensitive as boolean | undefined }
        );
        if (results.length === 0) return ok("No matches found");
        return ok(results.map(
          r => `${r.path}\n${r.lines.map(l => `  ${l.line}: ${l.text}`).join("\n")}`
        ).join("\n\n"));
      } catch (e) { return err(e); }
    },
  },
  {
    name: "glob",
    description: "Find files by name pattern (glob)",
    parameters: {
      type: "object",
      properties: {
        pattern: { type: "string", description: "Glob pattern (e.g. *.md, **/*.ts)" },
        path: { type: "string", description: "Directory to search in (default: /)" },
        type: { type: "string", enum: ["file", "dir"], description: "Filter by type" },
      },
      required: ["pattern"],
    },
    async call(fs, args) {
      try {
        const paths = await fs.glob(
          args.pattern as string,
          args.path as string | undefined,
          { type: args.type as "file" | "dir" | undefined }
        );
        if (paths.length === 0) return ok("No files found");
        return ok(paths.join("\n"));
      } catch (e) { return err(e); }
    },
  },
  {
    name: "mv",
    description: "Move or rename a file or directory",
    parameters: {
      type: "object",
      properties: {
        from: { type: "string", description: "Source path" },
        to: { type: "string", description: "Destination path" },
      },
      required: ["from", "to"],
    },
    async call(fs, args) {
      try {
        await fs.mv(args.from as string, args.to as string);
        return ok(`Moved ${args.from} -> ${args.to}`);
      } catch (e) { return err(e); }
    },
  },

  // ── New tools ─────────────────────────────────────────────────────────

  {
    name: "search",
    description: "Semantic search across all files using full-text search (BM25) and optional vector embeddings. Returns ranked results with snippets.",
    parameters: {
      type: "object",
      properties: {
        query: { type: "string", description: "Natural language search query" },
        path: { type: "string", description: "Restrict search to files under this path" },
        limit: { type: "number", description: "Maximum results to return (default: 20)" },
      },
      required: ["query"],
    },
    async call(fs, args) {
      try {
        const results = await fs.search(args.query as string, {
          path: args.path as string | undefined,
          limit: args.limit as number | undefined,
        });
        if (results.length === 0) return ok("No results found");
        return ok(results.map((r, i) =>
          `${i + 1}. ${r.path} [${r.source}] (score: ${r.score.toFixed(3)})\n   ${r.snippet}`
        ).join("\n\n"));
      } catch (e) { return err(e); }
    },
  },
  {
    name: "tag",
    description: "Add a tag to a file or directory for categorization and retrieval",
    parameters: {
      type: "object",
      properties: {
        path: { type: "string", description: "Absolute path to tag" },
        tag: { type: "string", description: "Tag name (e.g. 'preferences', 'architecture', 'decision')" },
      },
      required: ["path", "tag"],
    },
    async call(fs, args) {
      try {
        await fs.tag(args.path as string, args.tag as string);
        return ok(`Tagged ${args.path} with #${args.tag}`);
      } catch (e) { return err(e); }
    },
  },
  {
    name: "untag",
    description: "Remove a tag from a file or directory",
    parameters: {
      type: "object",
      properties: {
        path: { type: "string", description: "Absolute path to untag" },
        tag: { type: "string", description: "Tag to remove" },
      },
      required: ["path", "tag"],
    },
    async call(fs, args) {
      try {
        await fs.untag(args.path as string, args.tag as string);
        return ok(`Removed #${args.tag} from ${args.path}`);
      } catch (e) { return err(e); }
    },
  },
  {
    name: "find_by_tag",
    description: "Find all files and directories with a specific tag",
    parameters: {
      type: "object",
      properties: {
        tag: { type: "string", description: "Tag to search for" },
        path: { type: "string", description: "Restrict to files under this path" },
      },
      required: ["tag"],
    },
    async call(fs, args) {
      try {
        const entries = await fs.findByTag(
          args.tag as string,
          args.path as string | undefined
        );
        if (entries.length === 0) return ok(`No files found with #${args.tag}`);
        return ok(entries.map(e =>
          e.isDir ? `${e.path}/` : `${e.path}  (${e.size} bytes)`
        ).join("\n"));
      } catch (e) { return err(e); }
    },
  },
  {
    name: "recent",
    description: "List recently modified files, ordered by last update time",
    parameters: {
      type: "object",
      properties: {
        limit: { type: "number", description: "Maximum number of files to return (default: 20)" },
        path: { type: "string", description: "Restrict to files under this path" },
      },
    },
    async call(fs, args) {
      try {
        const entries = await fs.recent({
          limit: args.limit as number | undefined,
          path: args.path as string | undefined,
        });
        if (entries.length === 0) return ok("No recent files");
        return ok(entries.map(e => {
          let line = `${e.path}  (${e.size} bytes)  [${e.updatedAt}]`;
          if (e.summary) line += `\n  ${e.summary}`;
          return line;
        }).join("\n"));
      } catch (e) { return err(e); }
    },
  },
];

export type ToolName = Tool["name"];

const toolMap = new Map(tools.map(t => [t.name, t]));

export function getTool(name: string): Tool | undefined {
  return toolMap.get(name);
}

export async function callTool(fs: FileSystem, name: string, args: Record<string, unknown>): Promise<ToolResult> {
  const tool = toolMap.get(name);
  if (!tool) return { text: `Unknown tool: ${name}`, isError: true };
  return tool.call(fs, args);
}
