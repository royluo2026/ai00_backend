import test from "node:test";
import assert from "node:assert/strict";

import { isCapabilityResultV2 } from "../src/index.js";


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
