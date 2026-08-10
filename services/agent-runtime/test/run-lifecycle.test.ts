import test from "node:test";
import assert from "node:assert/strict";
import { InMemoryRunRepository, RunStore } from "../src/run-store.js";
import { ToolSelector } from "../src/tool-selector.js";

const key = Buffer.alloc(32, 9);

test("run resumes after runtime restart without persisting the raw delegation", async () => {
  const repository = new InMemoryRunRepository();
  const first = new RunStore(repository, key);
  const run = await first.create({
    sessionId: "as_1", tenantId: "tenant_1", requestedBy: "user_1",
    channelType: "feishu_group", goal: "检查工艺", uiContext: { selected: "line_1" },
    catalogRelease: "rel_0123456789abcdef0123456789abcdef",
    delegationId: "delegation_1", delegationToken: "secret-delegation-token",
    participants: [
      { principalId: "user_1", principalType: "user", role: "owner" },
      { principalId: "user_2", principalType: "user", role: "participant" },
    ],
  });
  const running = await first.transition(run.runId, run.version, "running");
  await first.transition(run.runId, running.version, "awaiting_approval");

  const reopened = new RunStore(repository, key);
  const recovered = await reopened.loadForParticipant(run.runId, "user_2");
  assert.equal(recovered.status, "awaiting_approval");
  assert.equal(reopened.delegationToken(recovered), "secret-delegation-token");
  assert.equal(JSON.stringify(repository.snapshot()).includes("secret-delegation-token"), false);
  assert.equal(JSON.stringify(repository.snapshot()).includes("检查工艺"), false);
  assert.equal(JSON.stringify(repository.snapshot()).includes("line_1"), false);
  await assert.rejects(() => reopened.loadForParticipant(run.runId, "user_3"), /participant_required/);
});

test("run transitions are compare-and-set and terminal states cannot resume", async () => {
  const repository = new InMemoryRunRepository();
  const store = new RunStore(repository, key);
  const run = await store.create({
    sessionId: "as_1", tenantId: "tenant_1", requestedBy: "user_1", channelType: "web",
    goal: "test", uiContext: {}, catalogRelease: "rel_0123456789abcdef0123456789abcdef",
    delegationId: "delegation_1", delegationToken: "secret", participants: [],
  });
  const running = await store.transition(run.runId, run.version, "running");
  await assert.rejects(() => store.transition(run.runId, run.version, "completed"), /version_conflict/);
  const cancelled = await store.transition(run.runId, running.version, "cancelled");
  await assert.rejects(() => store.transition(run.runId, cancelled.version, "running"), /invalid_transition/);
  await store.recordToolResult({ runId: run.runId, callId: "call_1", capabilityId: "system.echo", majorVersion: 1,
    fullResult: { ok: true, data: { complete: true } }, projectedResult: { ok: true, data: { summary: "complete" } } });
  assert.deepEqual(repository.resultSnapshot()[0]?.fullResult, { ok: true, data: { complete: true } });
});

test("tool selection is catalog-pinned, agent-exposed, deterministic and bounded", () => {
  const selector = new ToolSelector(2);
  const release = "rel_0123456789abcdef0123456789abcdef";
  const selected = selector.select("工艺 知识", release, [
    { id: "craft.bop.get", major_version: 1, description: "工艺 BOP", exposure: { agent: true }, side_effect_level: "read" },
    { id: "knowledge.search", major_version: 1, description: "知识 搜索", exposure: { agent: true }, side_effect_level: "read" },
    { id: "system.hidden", major_version: 1, description: "工艺", exposure: { agent: false }, side_effect_level: "read" },
  ]);
  assert.equal(selected.catalogRelease, release);
  assert.deepEqual(selected.tools.map(item => item.id), ["craft.bop.get", "knowledge.search"]);
  assert.equal(selected.tools.length, 2);
});
