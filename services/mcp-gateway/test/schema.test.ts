import test from "node:test";
import assert from "node:assert/strict";
import { CapabilityClient, CapabilityInvocationError, CapabilityTransportError } from "../src/capability-client.js";
import { projectResult } from "../src/projection.js";
import { jsonSchemaToZod } from "../src/schema.js";

test("converts required object properties and rejects missing values", () => {
  const schema = jsonSchemaToZod({ type: "object", required: ["gid"], properties: { gid: { type: "string", minLength: 1 }, limit: { type: "integer" } } });
  assert.equal(schema.safeParse({ gid: "k1", limit: 2 }).success, true);
  assert.equal(schema.safeParse({ limit: 2 }).success, false);
});

test("delegated invocation preserves full CapabilityResultV2 transport", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = (async () => ({ ok: true, status: 200, json: async () => ({
    ok: true, status: "completed", capability_id: "system.echo", major_version: 1,
    data: { value: 1 }, operation_ref: null, artifact_refs: [], error: null,
    evidence: [{ kind: "test.ref", reference: "test://1" }], warnings: [], correlation: { request_id: "req_1" },
  }) })) as unknown as typeof fetch;
  try {
    const client = new CapabilityClient("http://base", "service-secret-with-at-least-32-bytes");
    const result: any = await client.invoke("delegation", { id: "system.echo", major_version: 1 } as any,
      "rel_0123456789abcdef0123456789abcdef", {}, "req_1");
    assert.equal(result.status, "completed");
    assert.equal(result.evidence[0].reference, "test://1");
  } finally { globalThis.fetch = original; }
});

test("HTTP and protocol failures remain distinguishable", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = (async () => ({ ok: false, status: 409, json: async () => ({ error: { code: "conflict" } }) })) as unknown as typeof fetch;
  try {
    const client = new CapabilityClient("http://base", "service-secret-with-at-least-32-bytes");
    await assert.rejects(client.invoke("delegation", { id: "system.echo", major_version: 1 } as any,
      "rel_0123456789abcdef0123456789abcdef", {}, "req_1"), CapabilityInvocationError);
  } finally { globalThis.fetch = original; }
  globalThis.fetch = (async () => { throw new Error("offline"); }) as typeof fetch;
  try {
    const client = new CapabilityClient("http://base", "service-secret-with-at-least-32-bytes");
    await assert.rejects(client.invoke("delegation", { id: "system.echo", major_version: 1 } as any,
      "rel_0123456789abcdef0123456789abcdef", {}, "req_1"), CapabilityTransportError);
  } finally { globalThis.fetch = original; }
});

test("MCP projection uses output allowlist and preserves references", () => {
  const projected: any = projectResult({ ok: true, status: "completed", capability_id: "x", major_version: 1,
    data: { allowed: "yes", secret_token: "no" }, artifact_refs: [{ artifact_id: "a1" }],
    evidence: [{ kind: "source", reference: "doc://1", metadata: { secret: "no" } }] },
    { type: "object", additionalProperties: false, properties: { allowed: { type: "string" }, secret_token: { type: "string" } } });
  assert.deepEqual(projected.data, { allowed: "yes" });
  assert.deepEqual(projected.artifact_refs, [{ artifact_id: "a1" }]);
  assert.equal(JSON.stringify(projected).includes("secret"), false);
});

test("MCP projection bounds large model-visible results", () => {
  const projected: any = projectResult({ ok: true, data: { value: "x".repeat(10_000) } },
    { type: "object", additionalProperties: false, properties: { value: { type: "string" } } }, 256);
  assert.equal(projected.truncated, true);
  assert.ok(JSON.stringify(projected.data).length < 600);
});
