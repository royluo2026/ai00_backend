const test = require('node:test');
const assert = require('node:assert/strict');
const { createEnvironmentStore } = require('./environment_store');
const { createSimulationCache } = require('./simulation_cache');
const { createVmVersioningController } = require('./vm_versioning');

class MemoryBackend {
  constructor() { this.stores = new Map(); }
  store(name) {
    if (!this.stores.has(name)) this.stores.set(name, new Map());
    return this.stores.get(name);
  }
  async get(name, key) { return this.store(name).get(key) || null; }
  async all(name) { return [...this.store(name).values()]; }
  async commit(operations) {
    operations.forEach(operation => {
      if (operation.type === 'put') this.store(operation.store).set(operation.value.key, structuredClone(operation.value));
      if (operation.type === 'delete') this.store(operation.store).delete(operation.key);
    });
  }
}

class Storage {
  constructor() { this.values = new Map(); }
  getItem(key) { return this.values.get(key) ?? null; }
  setItem(key, value) { this.values.set(key, value); }
}

const hash = character => `sha256:${character.repeat(64)}`;
const lease = (rowVersion, revision) => ({
  auth_subject_gid: '11',
  workspace_gid: '33',
  row_version: rowVersion,
  cache_revision_hash: revision,
  expires_at: '2099-01-01T00:00:00Z',
  read_lease: `signed-lease-${rowVersion}-value`,
});

test('cached workspace, authoritative refresh and version reports share one projection without COM control calls', async () => {
  const calls = [];
  const cache = createSimulationCache({ indexedDB: new MemoryBackend(), clock: () => 1_000 });
  await cache.putWorkspace({
    authSubjectGid: '11', workspaceGid: '33', rowVersion: 1, cacheRevisionHash: hash('a'),
    lease: lease(1, hash('a')), workspace: { workspace_gid: '33', row_version: 1,
      cache_revision_hash: hash('a'), nodes: [{ node_gid: '71', name: 'cached' }], bindings: [] },
  });

  let serverRevision = 1;
  const invoke = async (capability, payload) => {
    calls.push([capability, payload]);
    if (capability === 'simulation.environment.workspace.cache_lease.get') {
      return lease(serverRevision, hash(serverRevision === 1 ? 'a' : 'b'));
    }
    if (capability === 'simulation.environment.workspace.get') return {
      workspace_gid: '33', row_version: 2, cache_revision_hash: hash('b'),
      nodes: [{ node_gid: '71', name: 'authoritative' }], bindings: [],
    };
    if (capability === 'simulation.vm_diff_report.generate') return { report_gid: '91' };
    if (capability === 'simulation.vm_diff_report.get') return { report_gid: '91', workspace_gid: '33', summary: { renamed: 1 } };
    if (capability === 'simulation.vm_diff_item.search') return {
      items: [{ sequence: 1, change_type: 'renamed', after_occurrence_gid: '71' }], next_cursor: null,
    };
    throw new Error(`unexpected capability: ${capability}`);
  };

  const store = createEnvironmentStore({ invoke, cache, getAuthSubjectGid: () => '11' });
  await store.openWorkspace('33');
  assert.equal(store.state.workspace.nodes[0].name, 'cached');
  assert.equal(store.state.cacheStatus, 'validated');

  serverRevision = 2;
  await store.openWorkspace('33');
  assert.equal(store.state.workspace.nodes[0].name, 'authoritative');
  assert.equal(store.state.cacheStatus, 'authoritative');

  const versioning = createVmVersioningController({ invoke, cache, storage: new Storage(), getAuthSubjectGid: () => '11' });
  await versioning.onFreshSnapshot({ workspaceGid: '33', snapshot_request_id: 'capture-1', snapshot_hash: hash('c') });
  assert.equal(calls.some(([id]) => id === 'simulation.vm_checkpoint.create'), false);
  const comparison = await versioning.compareNow({ beforeCheckpointGid: '81', afterCheckpointGid: '82' });
  assert.equal(comparison.items[0].change_type, 'renamed');
  assert.equal(versioning.isAutomaticComparisonEnabled('33'), false);

  const invokedIds = calls.map(([id]) => id);
  assert.equal(invokedIds.some(id => /visibility|highlight|show|hide/i.test(id)), false);
});
