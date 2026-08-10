import test from "node:test";
import assert from "node:assert/strict";
import { CapabilityClient, CapabilityInvocationError } from "../src/capability-client.js";
import { jsonSchemaToZod } from "../src/schema.js";

test("converts required object properties and rejects missing values", () => {
  const schema = jsonSchemaToZod({ type: "object", required: ["gid"], properties: { gid: { type: "string", minLength: 1 }, limit: { type: "integer" } } });
  assert.equal(schema.safeParse({ gid: "k1", limit: 2 }).success, true);
  assert.equal(schema.safeParse({ limit: 2 }).success, false);
});

test("MCP discovery is filtered and invocation preserves error and evidence fields", async () => {
  const originalFetch = globalThis.fetch;
  const urls: string[] = [];
  globalThis.fetch = (async (input: string | URL | Request) => {
    urls.push(String(input));
    return {
      ok: true,
      status: 200,
      json: async () => ({
        success: true,
        data: { ok: true, capability_id: "system.echo", version: 1, data: { value: 1 }, error: null, evidence: [{ kind: "test.ref", reference: "test://1", digest: null, summary: "", metadata: {} }], audit: {} },
      }),
    } as Response;
  }) as typeof fetch;
  try {
    const client = new CapabilityClient("http://base");
    const spec: any = { id: "system.echo", version: 1 };
    const result = await client.invoke("token", spec, { value: 1 });
    assert.equal(result.error, null);
    assert.equal(result.evidence.at(0)?.reference, "test://1");
    await client.list("token");
    assert.equal(urls[1], "http://base/api/v1/capabilities?execution=cloud&consumer=mcp");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("MCP HTTP failures become structured CapabilityResult errors", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => ({
    ok: false,
    status: 409,
    headers: { get: (name: string) => name === "X-Request-ID" ? "mcp-error-1" : null },
    json: async () => ({ success: false, detail: { code: "confirmation_required", message: "Confirmation is required", retryable: false, details: { capability_id: "system.job.cancel" } } }),
  })) as unknown as typeof fetch;
  try {
    const client = new CapabilityClient("http://base");
    const spec: any = { id: "system.job.cancel", version: 1 };
    await assert.rejects(
      client.invoke("token", spec, { job_gid: "job-1" }, "mcp-error-1"),
      (error: unknown) => {
        assert.equal(error instanceof CapabilityInvocationError, true);
        const result = (error as CapabilityInvocationError).toResult();
        assert.equal(result.ok, false);
        assert.equal(result.capability_id, "system.job.cancel");
        assert.equal(result.error?.code, "confirmation_required");
        assert.equal(result.error?.retryable, false);
        assert.equal(result.audit.request_id, "mcp-error-1");
        assert.deepEqual(result.evidence, []);
        return true;
      },
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});
test("MCP client sends a stable request id and normalizes success audit", async () => {
  const originalFetch = globalThis.fetch;
  let seenHeaders: Record<string, string> | undefined;
  globalThis.fetch = (async (_input: string | URL | Request, init?: RequestInit) => {
    seenHeaders = init?.headers as Record<string, string>;
    return {
      ok: true,
      status: 200,
      headers: { get: () => "mcp-request-1" },
      json: async () => ({
        success: true,
        data: { ok: true, capability_id: "system.echo", version: 1, data: { value: 1 }, error: null, evidence: [], audit: {} },
      }),
    } as unknown as Response;
  }) as typeof fetch;
  try {
    const client = new CapabilityClient("http://base");
    const result = await client.invoke("token", { id: "system.echo", version: 1 } as any, { value: 1 }, "mcp-request-1");
    assert.equal(seenHeaders?.["X-AI00-Source"], "mcp");
    assert.equal(seenHeaders?.["X-Request-ID"], "mcp-request-1");
    assert.equal(result.audit.source, "mcp");
    assert.equal(result.audit.request_id, "mcp-request-1");
  } finally {
    globalThis.fetch = originalFetch;
  }
});