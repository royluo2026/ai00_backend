import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

const engineUrl = new URL('../examples/project-readiness/readiness-engine.js', import.meta.url);
const engine = fs.existsSync(fileURLToPath(engineUrl)) ? await import(engineUrl) : {};

const craft = { status: 'ok', version_gid: 'bop-1', craft_commit_ref: 'craft://bop/version/bop-1/r3' };
const model = { status: 'ok', model_id: 'model-1', version_id: 'mv-1', snapshot_hash: `sha256:${'a'.repeat(64)}` };
const project = { status: 'ok', object_ref: 'project:p1', title: 'P1' };

test('classifies an exact completed craft and model simulation match as ready', () => {
  assert.equal(typeof engine.evaluateReadiness, 'function');
  const result = engine.evaluateReadiness({ project, craft, model, runs: [{
    run_id: 'run-1', status: 'completed', craft_commit_ref: craft.craft_commit_ref,
    model_snapshot_hash: model.snapshot_hash,
  }] });
  assert.equal(result.overall_status, 'ready');
  assert.equal(result.matched_run.run_id, 'run-1');
});

test('classifies a queued exact match as attention', () => {
  const result = engine.evaluateReadiness({ project, craft, model, runs: [{
    run_id: 'run-2', status: 'queued', craft_commit_ref: craft.craft_commit_ref,
    model_snapshot_hash: model.snapshot_hash,
  }] });
  assert.equal(result.overall_status, 'attention');
});

test('does not treat a canceled matching run as attention', () => {
  const result = engine.evaluateReadiness({ project, craft, model, runs: [{
    run_id: 'run-canceled', status: 'canceled', craft_commit_ref: craft.craft_commit_ref,
    model_snapshot_hash: model.snapshot_hash,
  }] });
  assert.equal(result.overall_status, 'blocked');
});

test('requires both governed references and never matches by one reference', () => {
  const result = engine.evaluateReadiness({ project, craft, model, runs: [{
    run_id: 'wrong-model', status: 'completed', craft_commit_ref: craft.craft_commit_ref,
    model_snapshot_hash: `sha256:${'b'.repeat(64)}`,
  }] });
  assert.equal(result.overall_status, 'blocked');
  assert.equal(result.matched_run, null);
});

test('keeps permission and provider failures distinct from business blocking', () => {
  const result = engine.evaluateReadiness({ project, craft: { status: 'inaccessible', error: 'permission_denied' }, model, runs: [] });
  assert.equal(result.overall_status, 'inaccessible');
  assert.equal(result.domains.craft.status, 'inaccessible');
});

test('selectFirstResolved retries bounded candidates and preserves failure evidence', async () => {
  assert.equal(typeof engine.selectFirstResolved, 'function');
  const attempted = [];
  const result = await engine.selectFirstResolved([1, 2, 3, 4, 5, 6], async value => {
    attempted.push(value);
    if (value < 3) throw new Error(`bad-${value}`);
    return { value };
  }, 5);
  assert.deepEqual(attempted, [1, 2, 3]);
  assert.deepEqual(result.value, { value: 3 });
  assert.equal(result.failures.length, 2);
});

test('history is deduplicated by report id and capped at twenty newest reports', () => {
  assert.equal(typeof engine.mergeHistory, 'function');
  const existing = Array.from({ length: 22 }, (_, index) => ({ report_id: `r${index}`, checked_at: `2026-08-${String(index + 1).padStart(2, '0')}` }));
  const merged = engine.mergeHistory(existing, { report_id: 'r21', checked_at: '2026-09-01', overall_status: 'ready' });
  assert.equal(merged.length, 20);
  assert.equal(merged[0].report_id, 'r21');
  assert.equal(merged[0].overall_status, 'ready');
  assert.equal(new Set(merged.map(item => item.report_id)).size, 20);
});
