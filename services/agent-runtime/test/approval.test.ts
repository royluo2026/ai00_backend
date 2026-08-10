import test from "node:test";
import assert from "node:assert/strict";
import { ApprovalDispatcher, InMemoryApprovalRepository } from "../src/approval-dispatcher.js";
import { projectCapabilityResult } from "../src/projection.js";
import { CapabilityClient } from "../src/capability-client.js";

test("approval is bound to run capability payload and may be decided once", async () => {
  const dispatcher = new ApprovalDispatcher(new InMemoryApprovalRepository(), Buffer.alloc(32, 3));
  const request = await dispatcher.request({
    runId: "run_1", capabilityId: "craft.write", majorVersion: 1,
    requestId: "req_1", payload: { value: 1 }, challenge: { reason: "write" },
  });
  await assert.rejects(() => dispatcher.decide(request.approvalRequestId, "user_2", "approved", { value: 2 }), /payload_mismatch/);
  const decided = await dispatcher.decide(request.approvalRequestId, "user_2", "approved", { value: 1 });
  assert.equal(decided.status, "approved");
  await assert.rejects(() => dispatcher.decide(request.approvalRequestId, "user_2", "rejected", { value: 1 }), /approval_already_decided/);
});

test("agent projection bounds model-visible data while retaining references", () => {
  const projected = projectCapabilityResult({
    ok: true, status: "completed", capability_id: "knowledge.search", major_version: 1,
    data: { text: "x".repeat(20_000), secret_token: "must-not-leak" },
    operation_ref: { operation_id: "op_1" }, artifact_refs: [{ artifact_id: "art_1" }],
    error: null, evidence: [{ kind: "source", reference: "doc://1" }], warnings: [],
    correlation: { request_id: "req_1", trace_id: "trace_1" },
  }, 1024, {
    type: "object", additionalProperties: false,
    properties: { text: { type: "string" }, secret_token: { type: "string" } },
  });
  assert.equal(JSON.stringify(projected).includes("must-not-leak"), false);
  assert.equal(projected.truncated, true);
  assert.deepEqual(projected.artifact_refs, [{ artifact_id: "art_1" }]);
});

test("backend calls use service credential and delegation, never user bearer", async () => {
  const originalFetch = globalThis.fetch;
  const headers: Headers[] = [];
  globalThis.fetch = (async (_input: string | URL | Request, init?: RequestInit) => {
    headers.push(new Headers(init?.headers));
    return { ok: true, status: 200, json: async () => ({ descriptors: [], release_id: "rel_0123456789abcdef0123456789abcdef" }) } as Response;
  }) as typeof fetch;
  try {
    const client = new CapabilityClient("http://base", "service-secret");
    await client.listDelegated("delegation-secret", "rel_0123456789abcdef0123456789abcdef");
    assert.equal(headers[0]?.get("authorization"), null);
    assert.equal(headers[0]?.get("x-ai00-token"), null);
    assert.equal(headers[0]?.get("x-ai00-delegation"), "delegation-secret");
    assert.equal(headers[0]?.get("x-ai00-service-credential"), "service-secret");
  } finally {
    globalThis.fetch = originalFetch;
  }
});
