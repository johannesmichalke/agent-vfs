import { describe, it, expect } from "vitest";
import { openEmbeddings } from "../../src/search/embeddings.js";

describe("openEmbeddings", () => {
  it("creates OpenAI provider with correct dimensions", () => {
    const provider = openEmbeddings("openai", "sk-test-key");
    expect(provider.dimensions).toBe(1536);
    expect(typeof provider.embed).toBe("function");
  });

  it("creates Voyage provider", () => {
    const provider = openEmbeddings("voyage", "pa-test-key");
    expect(provider.dimensions).toBe(512);
  });

  it("creates OpenAI large provider", () => {
    const provider = openEmbeddings("openai-large", "sk-test-key");
    expect(provider.dimensions).toBe(3072);
  });

  it("creates Voyage large provider", () => {
    const provider = openEmbeddings("voyage-large", "pa-test-key");
    expect(provider.dimensions).toBe(1024);
  });

  it("creates Mistral provider", () => {
    const provider = openEmbeddings("mistral", "test-key");
    expect(provider.dimensions).toBe(1024);
  });

  it("throws for unknown provider name", () => {
    expect(() => openEmbeddings("unknown-provider", "key")).toThrow(
      'Unknown embedding provider: "unknown-provider"'
    );
  });

  it("throws when no API key provided for preset", () => {
    expect(() => openEmbeddings("openai")).toThrow("API key required");
  });

  it("accepts custom config object", () => {
    const provider = openEmbeddings({
      url: "https://my-server.com/embed",
      model: "my-model",
      apiKey: "custom-key",
      dimensions: 768,
    });
    expect(provider.dimensions).toBe(768);
    expect(typeof provider.embed).toBe("function");
  });

  it("lists available providers in error message", () => {
    try {
      openEmbeddings("nope", "key");
    } catch (e) {
      expect((e as Error).message).toContain("openai");
      expect((e as Error).message).toContain("voyage");
      expect((e as Error).message).toContain("mistral");
    }
  });
});
