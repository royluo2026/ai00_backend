import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

const runtimeUrl = new URL('../examples/project-readiness/readiness-runtime.js', import.meta.url);
const runtime = fs.existsSync(fileURLToPath(runtimeUrl)) ? await import(runtimeUrl) : {};

const hash = `sha256:${'c'.repeat(64)}`;
const complete = data => ({ ok: true, status: 'completed', data, error: null });

test('manifest grants exactly the capabilities used by the readiness runtime', () => {
  const manifestUrl = new URL('../examples/project-readiness/plugin.json', import.meta.url);
  const manifest = fs.existsSync(fileURLToPath(manifestUrl)) ? JSON.parse(fs.readFileSync(fileURLToPath(manifestUrl), 'utf8')) : {};
  assert.deepEqual(manifest.permissions, runtime.DECLARED_CAPABILITIES);
  assert.equal(manifest.plugin_id, 'devteam.ai00.project-readiness');
  assert.equal(manifest.data.uninstall, 'delete');
});

test('runs a bounded four-domain check exclusively through declared capabilities', async () => {
  assert.equal(typeof runtime.runReadinessCheck, 'function');
  const calls = [];
  const client = { invoke: async (id, payload) => {
    calls.push([id, payload]);
    const fixtures = {
      'craft.bop.version.list': complete({ items: [{ version_gid:'bop-1', archived:false }, { version_gid:'bop-2', archived:false }], next_cursor:null }),
      'craft.bop.execution_structure.get': payload.version_gid === 'bop-1'
        ? { ok:false, status:'failed', error:{ code:'version_not_published', message:'not published' } }
        : complete({ version_gid:'bop-2', craft_commit_ref:'craft://bop/version/bop-2/r2', revision:2, node_count:3 }),
      'digital_model.model.search': complete({ items:[{ model_id:'m1', latest_version_id:'v1', name:'M1', project_ref:'project:p1' }], total:1, query:'' }),
      'digital_model.version.get': complete({ snapshot_ref:{ model_id:'m1', version_id:'v1', snapshot_hash:hash, artifact_ref:{} }, version_label:'1', components:[] }),
      'simulation.run.search': complete({ items:[{ run_id:'r1', status:'queued', craft_commit_ref:'craft://bop/version/bop-2/r2', model_snapshot_hash:hash }], total:1 }),
    };
    return fixtures[id];
  } };

  const report = await runtime.runReadinessCheck(client, { object_ref:'project:p1', title:'P1', summary:'active' }, { reportId:'report-1', now:'2026-08-13T12:00:00Z', catalogRelease:'rel-1' });
  assert.equal(report.overall_status, 'attention');
  assert.equal(report.evidence_refs.bop_version_gid, 'bop-2');
  assert.equal(report.evidence_refs.model_snapshot_hash, hash);
  assert.deepEqual(calls[0], ['craft.bop.version.list', { project_gid:'p1', include_archived:false, page_size:5 }]);
  assert.equal(calls.filter(([id]) => id === 'craft.bop.execution_structure.get').length, 2);
  assert.deepEqual(calls.find(([id]) => id === 'simulation.run.search'), ['simulation.run.search', { limit:200 }]);
});

test('retries one optimistic history conflict with a fresh read', async () => {
  assert.equal(typeof runtime.saveHistory, 'function');
  let reads = 0; let writes = 0;
  const client = {
    storageGet: async key => {
      assert.equal(key, 'history/v1'); reads += 1;
      return reads === 1
        ? complete({ key, value:{ schema_version:1, items:[{report_id:'old'}] }, version:2 })
        : complete({ key, value:{ schema_version:1, items:[{report_id:'other'}] }, version:3 });
    },
    storagePut: async (key, value, expectedVersion) => {
      writes += 1;
      if (writes === 1) return { ok:false, status:'failed', error:{ code:'provider_failed', message:'plugin storage version conflict' } };
      assert.equal(expectedVersion, 3);
      assert.equal(value.schema_version, 1);
      assert.equal(value.items[0].report_id, 'new');
      assert.equal(value.items[1].report_id, 'other');
      return complete({ key, version:4 });
    },
  };
  const stored = await runtime.saveHistory(client, { report_id:'new', checked_at:'2026-08-13' });
  assert.equal(stored.version, 4);
  assert.equal(reads, 2);
  assert.equal(writes, 2);
});

test('classifies exhausted business candidates as blocked but provider denial as inaccessible', () => {
  assert.equal(runtime.classifyCandidateFailures([
    { code:'version_not_published', error:'not published' },
  ]), 'blocked');
  assert.equal(runtime.classifyCandidateFailures([
    { code:'permission_denied', error:'denied' },
  ]), 'inaccessible');
  assert.equal(runtime.classifyCandidateFailures([
    { code:'provider_failed', error:'failed' },
  ]), 'inaccessible');
});

test('creates a report id when crypto.randomUUID is unavailable on local HTTP', async () => {
  const originalCrypto = globalThis.crypto;
  Object.defineProperty(globalThis, 'crypto', {
    configurable: true,
    value: {
      getRandomValues(bytes) {
        for (let index = 0; index < bytes.length; index += 1) bytes[index] = index;
        return bytes;
      },
    },
  });
  try {
    const client = { invoke: async id => {
      const fixtures = {
        'craft.bop.version.list': complete({ items: [] }),
        'digital_model.model.search': complete({ items: [] }),
        'simulation.run.search': complete({ items: [] }),
      };
      return fixtures[id];
    } };
    const report = await runtime.runReadinessCheck(client, { object_ref:'project:p1', title:'P1' }, { now:'2026-08-17T00:00:00Z' });
    assert.equal(report.report_id, '00010203-0405-4607-8809-0a0b0c0d0e0f');
  } finally {
    Object.defineProperty(globalThis, 'crypto', { configurable: true, value: originalCrypto });
  }
});
