import test from "node:test";
import assert from "node:assert/strict";

import { createRequestId, isCapabilityResultV2 } from "../src/index.js";


test("recognizes the complete CapabilityResultV2 transport shape", () => {
  const result = {
    ok: true,
    status: "completed",
    capability_id: "craft.routing.get",
    major_version: 1,
    data: {},
    operation_ref: null,
    artifact_refs: [],
    error: null,
    evidence: [],
    warnings: [],
    correlation: { request_id: "req_1", trace_id: "trace_1" },
  };
  assert.equal(isCapabilityResultV2(result), true);
  assert.equal(isCapabilityResultV2({ success: true, data: {} }), false);
});

test("creates a secure request id without crypto.randomUUID", () => {
  const requestId = createRequestId({
    getRandomValues(bytes) {
      for (let index = 0; index < bytes.length; index += 1) bytes[index] = index;
      return bytes;
    },
  });
  assert.equal(requestId, "00010203-0405-4607-8809-0a0b0c0d0e0f");
});
