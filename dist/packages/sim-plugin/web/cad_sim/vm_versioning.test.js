const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { createVmVersioningController } = require('./vm_versioning');

class Storage {
  constructor() { this.values = new Map(); }
  getItem(key) { return this.values.get(key) ?? null; }
  setItem(key, value) { this.values.set(key, value); }
}

function setup() {
  const calls = []; const storage = new Storage(); let checkpoint = 0;
  const controller = createVmVersioningController({ storage, getAuthSubjectGid: () => '7',
    captureSnapshot: async () => ({ snapshot_request_id: 'r1', snapshot_hash: `sha256:${'a'.repeat(64)}` }),
    invoke: async (id, payload) => {
      calls.push([id, payload]);
      if (id === 'simulation.vm_checkpoint.create') return { checkpoint_gid: String(++checkpoint), ...payload };
      if (id === 'simulation.vm_diff_report.generate') return { report_gid: '9', summary: { added: 1 } };
      if (id === 'simulation.vm_diff_report.get') return { report_gid: '9', summary: { added: 1 } };
      if (id === 'simulation.vm_diff_item.search') return { items: [{ sequence: 1, change_type: 'added' }], next_cursor: null };
    } });
  return { controller, calls, storage };
}

test('simulation toolbar exposes snapshot, one-shot comparison and automatic switch', () => {
  const html = fs.readFileSync(require.resolve('./index.html'), 'utf8');
  assert.match(html, /id="btnVmCheckpoint"[^>]*>创建快照/);
  assert.match(html, /id="btnVmCompare"[^>]*>立即对比/);
  assert.match(html, /id="vmAutoCompare"/);
  assert.match(html, /aria-live="polite"/);
});

test('automatic preference is isolated by authenticated user and workspace', () => {
  const { controller, storage } = setup();
  controller.setAutomaticComparison({ workspaceGid: '11', enabled: true });
  assert.equal(controller.isAutomaticComparisonEnabled('11'), true);
  const other = createVmVersioningController({ storage, getAuthSubjectGid: () => '8', invoke: async () => {} });
  assert.equal(other.isAutomaticComparisonEnabled('11'), false);
});

test('manual checkpoint captures a fresh snapshot and keeps exact provenance', async () => {
  const { controller, calls } = setup();
  const result = await controller.createCheckpoint({ workspaceGid: '11', scope: 'personal', name: '手动版本' });
  assert.equal(result.snapshot_request_id, 'r1');
  assert.equal(calls[0][0], 'simulation.vm_checkpoint.create');
  assert.equal(calls[0][1].snapshot_hash, `sha256:${'a'.repeat(64)}`);
});

test('switch off validates freshness but creates no automatic report', async () => {
  const { controller, calls } = setup();
  await controller.onFreshSnapshot({ workspaceGid: '11', snapshot_request_id: 'r1', snapshot_hash: `sha256:${'a'.repeat(64)}` });
  assert.equal(controller.state.lastSnapshot.snapshot_request_id, 'r1');
  assert.equal(calls.length, 0);
});

test('compare now runs once without enabling automatic mode', async () => {
  const { controller, calls } = setup();
  const result = await controller.compareNow({ workspaceGid: '11', beforeCheckpointGid: '1', afterCheckpointGid: '2' });
  assert.equal(result.report.report_gid, '9');
  assert.equal(result.items[0].change_type, 'added');
  assert.equal(controller.isAutomaticComparisonEnabled('11'), false);
  assert.equal(calls.filter(([id]) => id === 'simulation.vm_diff_report.generate').length, 1);
});

test('report items are requested in pages of 200', async () => {
  const { controller, calls } = setup();
  await controller.loadReport('9');
  assert.equal(calls.find(([id]) => id === 'simulation.vm_diff_item.search')[1].page_size, 200);
});
