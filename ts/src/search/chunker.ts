/**
 * Split text into overlapping chunks for embedding.
 *
 * Uses a simple token-count approximation (split on whitespace).
 * For production use with precise token counting, wrap this with a
 * proper tokenizer (tiktoken, etc.).
 */
export function splitIntoChunks(
  text: string,
  opts?: { chunkSize?: number; overlap?: number }
): string[] {
  const chunkSize = opts?.chunkSize ?? 400;
  const overlap = opts?.overlap ?? 80;

  const words = text.split(/\s+/);
  if (words.length <= chunkSize) return [text];

  const chunks: string[] = [];
  let start = 0;

  while (start < words.length) {
    const end = Math.min(start + chunkSize, words.length);
    chunks.push(words.slice(start, end).join(" "));
    if (end >= words.length) break;
    start += chunkSize - overlap;
  }

  return chunks;
}
