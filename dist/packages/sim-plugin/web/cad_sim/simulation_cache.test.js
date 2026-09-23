const test = require('node:test');
const assert = require('node:assert/strict');
const { createSimulationCache } = require('./simulation_cache');

class MemoryBackend {
  constructor() { this.stores = new Map(); this.failNextCommit = false; this.quotaFailures = 0; }
  _store(name) {
    if (!this.stores.has(name)) this.stores.set(name, new Map());
    return this.stores.get(name);
  }
  async get(store, key) { return this._store(store).get(key) || null; }
  async all(store) { return [...this._store(store).values()]; }
  async commit(operations) {
    if (this.quotaFailures > 0) {
      this.quotaFailures -= 1;
      const error = new Error('quota'); error.name = 'QuotaExceededError'; throw error;
    }
    if (this.failNextCommit) { this.failNextCommit = false; throw new Error('injected_write_failure'); }
    const copies = new Map([...this.stores].map(([name, rows]) => [name, new Map(rows)]));
    const target = name => {
      if (!copies.has(name)) copies.set(name, new Map());
      return copies.get(name);
    };
    operations.forEach(operation => {
      if (operation.type === 'put') target(operation.store).set(operation.value.key, structuredClone(operation.value));
      else if (operation.type === 'delete') target(operation.store).delete(operation.key);
    });
    this.stores = copies;
  }
}

const revision = char => `sha256:${char.repeat(64)}`;
const lease = ({ subject = '1', workspace = '9', row = 1, hash = revision('a'), expires = 10_000 } = {}) => ({
  auth_subject_gid: subject, workspace_gid: workspace, row_version: row,
  cache_revision_hash: hash, expires_at: new Date(expires).toISOString(), read_lease: 'signed-opaque-value',
});

test('never returns a workspace projection for another auth subject', async () => {
  const backend = new MemoryBackend();
  const cache = createSimulationCache({ indexedDB: backend, clock: () => 1_000 });
  await cache.putWorkspace({ authSubjectGid: '1', workspaceGid: '9', rowVersion: 1,
    cacheRevisionHash: revision('a'), lease: lease(), workspace: { nodes: [{ node_gid: '11' }] } });
  assert.equal(await cache.getWorkspace({ authSubjectGid: '2', workspaceGid: '9', lease: lease({ subject: '2' }) }), null);
  assert.equal((await cache.getWorkspace({ authSubjectGid: '1', workspaceGid: '9', lease: lease() })).workspace.nodes.length, 1);
});

test('expired lease hides cached protected data', async () => {
  let now = 1_000;
  const cache = createSimulationCache({ indexedDB: new MemoryBackend(), clock: () => now });
  const readLease = lease({ expires: 2_000 });
  await cache.putWorkspace({ authSubjectGid: '1', workspaceGid: '9', rowVersion: 1,
    cacheRevisionHash: revision('a'), lease: readLease, workspace: { name: 'cached' } });
  now = 2_001;
  assert.equal(await cache.getWorkspace({ authSubjectGid: '1', workspaceGid: '9', lease: readLease }), null);
});

test('failed generation write preserves previous generation', async () => {
  const backend = new MemoryBackend();
  const cache = createSimulationCache({ indexedDB: backend, clock: () => 1_000 });
  const firstLease = lease({ row: 1, hash: revision('a') });
  await cache.putWorkspace({ authSubjectGid: '1', workspaceGid: '9', rowVersion: 1,
    cacheRevisionHash: revision('a'), lease: firstLease, workspace: { name: 'first' } });
  backend.failNextCommit = true;
  await assert.rejects(cache.putWorkspace({ authSubjectGid: '1', workspaceGid: '9', rowVersion: 2,
    cacheRevisionHash: revision('b'), lease: lease({ row: 2, hash: revision('b') }), workspace: { name: 'partial' } }));
  assert.equal((await cache.getWorkspace({ authSubjectGid: '1', workspaceGid: '9', lease: firstLease })).workspace.name, 'first');
});

test('quota cleanup evicts complete expired workspaces and keeps live leased heads', async () => {
  let now = 1_000;
  const backend = new MemoryBackend();
  const cache = createSimulationCache({
    indexedDB: backend, clock: () => now,
    estimateStorage: async () => ({ quota: 1_000, usage: 900 }),
  });
  await cache.putWorkspace({ authSubjectGid: '1', workspaceGid: '9', rowVersion: 1,
    cacheRevisionHash: revision('a'), lease: lease({ workspace: '9', expires: 1_500 }), workspace: { name: 'old' } });
  await cache.putWorkspace({ authSubjectGid: '1', workspaceGid: '10', rowVersion: 1,
    cacheRevisionHash: revision('b'), lease: lease({ workspace: '10', hash: revision('b'), expires: 10_000 }), workspace: { name: 'live' } });
  now = 2_000;
  const result = await cache.compact();
  assert(result.evicted >= 1);
  assert.equal((await backend.all('workspace_heads')).some(row => row.workspaceGid === '9'), false);
  assert.equal((await backend.all('workspace_heads')).some(row => row.workspaceGid === '10'), true);
  assert.equal((await backend.all('workspace_generations')).some(row => row.workspaceGid === '9'), false);
});

test('binding and report projections expose the complete public adapter surface', async () => {
  const backend = new MemoryBackend();
  const cache = createSimulationCache({ indexedDB: backend, clock: () => 1_000 });
  await cache.putBindings({ authSubjectGid: '1', workspaceGid: '9', generation: 'g1', bindings: [{ bindingGid: '7' }] });
  assert.equal((await cache.getBindings({ authSubjectGid: '1', workspaceGid: '9' })).bindings[0].bindingGid, '7');
  await cache.putSnapshotSummary({ authSubjectGid: '1', workspaceGid: '9', snapshot: { snapshot_gid: '8' } });
  await cache.putDiffSummary({ authSubjectGid: '1', workspaceGid: '9', report: { report_gid: '10' } });
  await cache.clearLocal({ authSubjectGid: '1' });
  assert.equal((await backend.all('binding_heads')).length, 0);
  assert.equal(typeof cache.compact, 'function');
});

test('quota write failure compacts and retries exactly once', async () => {
  const backend = new MemoryBackend(); backend.quotaFailures = 1;
  const cache = createSimulationCache({ indexedDB: backend, clock: () => 1_000,
    estimateStorage: async () => ({ quota: 1_000, usage: 900 }) });
  await cache.putWorkspace({ authSubjectGid: '1', workspaceGid: '9', rowVersion: 1,
    cacheRevisionHash: revision('a'), lease: lease(), workspace: { name: 'saved-after-cleanup' } });
  assert.equal((await backend.all('workspace_heads')).length, 1);
});

test('unrelated workspace node changes keep the target binding fresh', async () => {
  const cache = createSimulationCache({ indexedDB: new MemoryBackend(), clock: () => 1_000 });
  await cache.putBindings({ authSubjectGid: '1', workspaceGid: '9', generation: 'g1', bindings: [
    { bindingGid: '7', workspaceNodeGid: '11', workspaceNodeRowVersion: 2,
      vmDocumentIdentityHash: revision('a'), vmOccurrenceGid: '21', vmNodeFingerprint: revision('b'), reviewState: 'confirmed' },
  ] });
  const result = await cache.getBindings({ authSubjectGid: '1', workspaceGid: '9',
    workspaceNodeVersions: { 11: 2, 12: 99 }, vmDocumentHash: revision('a'),
    vmNodeFingerprints: { 21: revision('b') } });
  assert.equal(result.bindings[0].cacheState, 'valid');
});

test('node and VM revisions invalidate only the binding that references them', async () => {
  const cache = createSimulationCache({ indexedDB: new MemoryBackend(), clock: () => 1_000 });
  await cache.putBindings({ authSubjectGid: '1', workspaceGid: '9', generation: 'g1', bindings: [
    { bindingGid: '7', workspaceNodeGid: '11', workspaceNodeRowVersion: 2,
      vmDocumentIdentityHash: revision('a'), vmOccurrenceGid: '21', vmNodeFingerprint: revision('b'), reviewState: 'confirmed' },
    { bindingGid: '8', workspaceNodeGid: '12', workspaceNodeRowVersion: 3,
      vmDocumentIdentityHash: revision('a'), vmOccurrenceGid: '22', vmNodeFingerprint: revision('c'), reviewState: 'confirmed' },
  ] });
  const result = await cache.getBindings({ authSubjectGid: '1', workspaceGid: '9',
    workspaceNodeVersions: { 11: 3, 12: 3 }, vmDocumentHash: revision('a'),
    vmNodeFingerprints: { 21: revision('b'), 22: revision('d') } });
  assert.deepEqual(result.bindings.map(item => item.cacheState), ['stale', 'stale']);
  assert.deepEqual(result.bindings.map(item => item.staleReason), ['workspace_node_changed', 'vm_node_changed']);
});

test('changed VM document invalidates every binding generation', async () => {
  const cache = createSimulationCache({ indexedDB: new MemoryBackend(), clock: () => 1_000 });
  await cache.putBindings({ authSubjectGid: '1', workspaceGid: '9', generation: 'g1', bindings: [
    { bindingGid: '7', workspaceNodeGid: '11', workspaceNodeRowVersion: 2,
      vmDocumentIdentityHash: revision('a'), vmOccurrenceGid: '21', vmNodeFingerprint: revision('b'), reviewState: 'confirmed' },
  ] });
  const result = await cache.getBindings({ authSubjectGid: '1', workspaceGid: '9',
    workspaceNodeVersions: { 11: 2 }, vmDocumentHash: revision('f'), vmNodeFingerprints: { 21: revision('b') } });
  assert.equal(result.bindings[0].staleReason, 'vm_document_changed');
});

test('ambiguous candidate is review-required and never auto-applied', async () => {
  const cache = createSimulationCache({ indexedDB: new MemoryBackend(), clock: () => 1_000 });
  await cache.putBindings({ authSubjectGid: '1', workspaceGid: '9', generation: 'g1', bindings: [
    { bindingGid: '7', workspaceNodeGid: '11', workspaceNodeRowVersion: 2,
      vmDocumentIdentityHash: revision('a'), vmOccurrenceGid: '21', vmNodeFingerprint: revision('b'),
      reviewState: 'candidate', cacheState: 'ambiguous' },
  ] });
  const result = await cache.getBindings({ authSubjectGid: '1', workspaceGid: '9',
    workspaceNodeVersions: { 11: 2 }, vmDocumentHash: revision('a'), vmNodeFingerprints: { 21: revision('b') } });
  assert.equal(result.bindings[0].cacheState, 'ambiguous');
  assert.equal(result.bindings[0].reviewState, 'candidate');
  assert.equal(result.bindings[0].canAutoApply, false);
});
