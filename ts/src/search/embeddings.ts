import type { EmbeddingProvider } from "./types.js";

/**
 * Built-in embedding providers. Just pass your API key — no setup needed.
 *
 * ```ts
 * // OpenAI
 * const embeddings = openEmbeddings("openai", process.env.OPENAI_API_KEY);
 *
 * // Voyage AI
 * const embeddings = openEmbeddings("voyage", process.env.VOYAGE_API_KEY);
 *
 * // Or bring your own:
 * const embeddings = openEmbeddings({
 *   url: "https://my-api.com/embeddings",
 *   model: "my-model",
 *   apiKey: "...",
 *   dimensions: 768,
 * });
 *
 * // Then plug it in:
 * const search = new SearchIndex(db, userId, embeddings);
 * const fs = new FileSystem(db, userId, { searchIndex: search });
 * ```
 */

interface ProviderConfig {
  url: string;
  model: string;
  apiKey: string;
  dimensions: number;
  /** Header name for auth. Default: "Authorization" with "Bearer " prefix. */
  authHeader?: string;
}

const PRESETS: Record<string, Omit<ProviderConfig, "apiKey">> = {
  openai: {
    url: "https://api.openai.com/v1/embeddings",
    model: "text-embedding-3-small",
    dimensions: 1536,
  },
  "openai-large": {
    url: "https://api.openai.com/v1/embeddings",
    model: "text-embedding-3-large",
    dimensions: 3072,
  },
  voyage: {
    url: "https://api.voyageai.com/v1/embeddings",
    model: "voyage-3-lite",
    dimensions: 512,
  },
  "voyage-large": {
    url: "https://api.voyageai.com/v1/embeddings",
    model: "voyage-3",
    dimensions: 1024,
  },
  mistral: {
    url: "https://api.mistral.ai/v1/embeddings",
    model: "mistral-embed",
    dimensions: 1024,
  },
};

/**
 * Create an embedding provider with minimal config.
 *
 * @param providerOrConfig - Provider name ("openai", "voyage", "mistral") or custom config
 * @param apiKey - API key (required for preset providers)
 */
export function openEmbeddings(
  providerOrConfig: string | ProviderConfig,
  apiKey?: string
): EmbeddingProvider {
  let config: ProviderConfig;

  if (typeof providerOrConfig === "string") {
    const preset = PRESETS[providerOrConfig];
    if (!preset) {
      throw new Error(
        `Unknown embedding provider: "${providerOrConfig}". Available: ${Object.keys(PRESETS).join(", ")}. Or pass a custom config object.`
      );
    }
    if (!apiKey) {
      throw new Error(`API key required for "${providerOrConfig}" provider.`);
    }
    config = { ...preset, apiKey };
  } else {
    config = providerOrConfig;
  }

  return {
    dimensions: config.dimensions,
    async embed(texts: string[]): Promise<number[][]> {
      return batchEmbed(config, texts);
    },
  };
}

/**
 * Embed texts via HTTP API with automatic batching.
 * Most APIs accept batches of up to ~100 texts. We batch at 96 to be safe.
 */
async function batchEmbed(
  config: ProviderConfig,
  texts: string[]
): Promise<number[][]> {
  const BATCH_SIZE = 96;
  const results: number[][] = [];

  for (let i = 0; i < texts.length; i += BATCH_SIZE) {
    const batch = texts.slice(i, i + BATCH_SIZE);
    const response = await fetch(config.url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${config.apiKey}`,
      },
      body: JSON.stringify({
        model: config.model,
        input: batch,
      }),
    });

    if (!response.ok) {
      const body = await response.text().catch(() => "");
      throw new Error(
        `Embedding API error (${response.status}): ${body.slice(0, 200)}`
      );
    }

    const json = (await response.json()) as {
      data: Array<{ embedding: number[]; index: number }>;
    };

    // Sort by index to maintain order
    const sorted = json.data.sort((a, b) => a.index - b.index);
    for (const item of sorted) {
      results.push(item.embedding);
    }
  }

  return results;
}
