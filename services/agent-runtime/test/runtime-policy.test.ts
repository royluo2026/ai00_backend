import test from "node:test";
import assert from "node:assert/strict";
import { CapabilityClient } from "../src/capability-client.js";
import { autonomousCapabilities } from "../src/pi-runtime.js";
import { open, seal } from "../src/crypto.js";

const base: any = { version: 1, description: "", execution: "cloud", permissions: [], input_schema: {}, output_schema: {}, tags: [] };
test("only cloud read capabilities without confirmation are autonomous", () => {
  const result = autonomousCapabilities([
    { ...base, id: "a.read", risk: "read", confirmation: "none" },
    { ...base, id: "a.write", risk: "write", confirmation: "none" },
    { ...base, id: "a.confirm", risk: "read", confirmation: "user" },
    { ...base, id: "a.local", execution: "local", risk: "read", confirmation: "none" },
  ]);
  assert.deepEqual(result.map(item => item.id), ["a.read"]);
});
test("session state is authenticated encryption", () => {
  const key = Buffer.alloc(32, 7);
  const encoded = seal({ messages: ["private"] }, key);
  assert.equal(encoded.includes("private"), false);
  assert.deepEqual(open(encoded, key), { messages: ["private"] });
  assert.throws(() => open(encoded.slice(0, -1) + "x", key));
});
test("agent discovery is server-filtered and invocation preserves CapabilityResult", async () => {
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
    const result = await client.invoke("token", { ...base, id: "system.echo", risk: "read", confirmation: "none" }, { value: 1 });
    assert.equal(result.capability_id, "system.echo");
    assert.equal(result.evidence.at(0)?.reference, "test://1");
    await client.list("token");
    assert.equal(urls[1], "http://base/api/v1/capabilities?consumer=agent");
  } finally {
    globalThis.fetch = originalFetch;
  }
});
