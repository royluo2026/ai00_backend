const assert = require('assert');
const { createEnvironmentStore } = require('./environment_store');

require('node:test')('opened-document update fences a delayed refresh without another network read',async()=>{
  let finish,reads=0;
  const store=createEnvironmentStore({invoke:async()=>{reads++;return new Promise(resolve=>finish=resolve);}});
  store.applyServerUpdate({workspace:{workspace_gid:'10',row_version:1,nodes:[]}});
  const refresh=store.openWorkspace('10');
  assert.equal(typeof store.applyOpenedDocument,'function');
  assert.equal(store.applyOpenedDocument('10',1,{document_gid:'11',workspace_row_version:2,document_session:'session'}),true);
  finish({workspace_gid:'10',row_version:1,nodes:[]});await refresh;
  assert.equal(store.state.workspace.row_version,2);assert.equal(reads,1);
  assert.equal(store.state.workspace.live_document.document_gid,'11');
  assert.equal(store.applyOpenedDocument('other',2,{workspace_row_version:3}),false);
});

async function run() {
  const calls = [];
  const store = createEnvironmentStore({
    invoke: async (capability, payload) => {
      calls.push([capability, payload]);
      if (capability === 'simulation.environment.workspace.search') return { items: [{ workspace_gid: '90071992547409931', name: 'L5' }] };
      if (capability === 'craft.bop.repository.search') return { items: [] };
      if (capability.endsWith('.get')) return {
        workspace_gid: payload.workspace_gid,
        row_version: 4,
        nodes: [{ node_gid: '11', parent_gid: null, name: 'Line', node_type: 'line' }],
        bindings: [],
      };
      return { row_version: 5, patch: { op: 'create', node_gid: '12', parent_gid: '11', name: 'Station', node_type: 'station', position: 0 } };
    },
  });

  await store.loadRecords();
  await store.openWorkspace('90071992547409931');
  store.rememberView({ selectedNodeGid: '11', treeScrollTop: 182, modelScrollTop: 73 });
  await store.mutate('simulation.environment.structure_node.create', {
    workspace_gid: '90071992547409931', parent_gid: '11', name: 'Station', node_type: 'station', idempotency_key: 'k1', expected_row_version: 4,
  });

  assert.equal(store.state.workspace.workspace_gid, '90071992547409931');
  assert.equal(typeof store.state.workspace.workspace_gid, 'string');
  assert.equal(store.state.workspace.row_version, 5);
  assert.equal(store.state.workspace.nodes.length, 2);
  assert.deepEqual(store.state.view, { selectedNodeGid: '11', treeScrollTop: 182, modelScrollTop: 73 });
  assert.equal(calls.filter(([id]) => id.endsWith('.get')).length, 1, 'atomic edit must not reload the workspace');
  store.state.currentKind = 'private';
  await store.bindOccurrence({ nodeGid: '11', occurrenceGid: '77', idempotencyKey: 'bind-1' });
  assert.equal(calls.at(-1)[0], 'simulation.environment.binding.create');
  assert.equal(calls.filter(([id]) => id.endsWith('.get')).length, 1, 'binding must patch without reload');

  const lifecycleCalls = [];
  const lifecycle = createEnvironmentStore({ invoke: async (capability, payload) => {
    lifecycleCalls.push([capability, payload]);
    if (capability === 'simulation.environment.workspace.search') return { items: [
      { workspace_gid: '31', name: '私人环境', is_owner: true, row_version: 2 },
    ] };
    if (capability === 'craft.bop.repository.search') return { items: [
      { repository_gid: '41', project_gid: '501', row_version: 3 },
    ] };
    if (capability === 'craft.bop.space.search') return { items: [
      { space_gid: '42', repository_gid: '41', space_kind: 'team', row_version: 4 },
      { space_gid: '43', repository_gid: '41', space_kind: 'managed_personal', owner_user_gid: '30', row_version: 5 },
    ] };
    if (capability === 'craft.bop.space_version.search') return { items: [{ version_gid: '44' }] };
    if (capability === 'craft.bop.repository.fork.preview') return { preview_gid: '51',
      workflow_gid: '52', plan_hash: `sha256:${'a'.repeat(64)}`, allowed_decisions: [] };
    if (capability === 'craft.bop.repository.fork.apply') return { repository_gid: '61',
      team_space_gid: '62', fork_run_gid: '63', workflow_gid: '52', status: 'completed' };
    if (capability === 'simulation.environment.workspace_version.search') return { items: [
      { workspace_gid: '31', version_gid: '32', status: 'frozen', content_hash: `sha256:${'c'.repeat(64)}` },
    ] };
    if (capability === 'simulation.environment.workspace.fork.preview') return { preview_gid: '71',
      plan_hash: `sha256:${'d'.repeat(64)}` };
    if (capability === 'simulation.environment.workspace.fork.apply') return {
      workspace_gid: '72', version_gid: '73', owner_gid: '30', is_owner: true, name: '私人环境 Fork',
      review_type: 'other', version_label: 'V2', status: 'active', visibility: 'private',
      project_gids: [], primary_project_gid: null, updated_at: '2026-09-09T12:00:00Z',
      row_version: 1, nodes: [], bindings: [], fork_base: { workspace_gid: '31', version_gid: '32', content_hash: `sha256:${'c'.repeat(64)}` },
    };
    if (capability.endsWith('.delete')) return { deleted: true };
    throw new Error(`unexpected ${capability}`);
  }});
  await lifecycle.load();
  assert.equal((await lifecycle.loadSpaceVersions('42'))[0].version_gid, '44');
  await lifecycle.forkRepository({ sourceVersionGid: '44', targetProjectGid: '502',
    targetName: '目标项目 BOP', targetProjectName: '目标项目', forkDepth: 'process', includePersonalMigration: true });
  assert.deepEqual(lifecycleCalls.slice(-2).map(item => item[0]), [
    'craft.bop.repository.fork.preview', 'craft.bop.repository.fork.apply',
  ]);
  assert.equal(lifecycleCalls.at(-2)[1].target_name, '目标项目 BOP');
  assert.equal(lifecycleCalls.at(-2)[1].target_project_name, '目标项目');
  assert(lifecycle.state.repositories.some(item => item.repository_gid === '61'));
  const privateVersions = await lifecycle.ensurePrivateForkVersions(lifecycle.state.records[0]);
  await lifecycle.forkPrivate({ sourceWorkspaceGid: '31', sourceVersionGid: privateVersions[0].version_gid,
    targetName: '私人环境 Fork', targetVersionLabel: 'V2', forkDepth: 'process' });
  assert.equal(lifecycleCalls.at(-2)[1].fork_depth, 'process');
  assert.deepEqual(lifecycleCalls.slice(-2).map(item => item[0]), [
    'simulation.environment.workspace.fork.preview', 'simulation.environment.workspace.fork.apply',
  ]);
  await lifecycle.deleteRecord('private', lifecycle.state.records[0]);
  await lifecycle.deleteRecord('managed_personal', lifecycle.state.spaces.find(item => item.space_gid === '43'));
  await lifecycle.deleteRecord('team', lifecycle.state.spaces.find(item => item.space_gid === '42'));
  assert.deepEqual(lifecycleCalls.slice(-3).map(item => item[0]), [
    'simulation.environment.workspace.delete',
    'craft.bop.managed_personal_space.delete',
    'craft.bop.repository.delete',
  ]);
  assert.equal(lifecycle.state.records.length, 1, 'the newly forked private environment remains');
  assert.equal(lifecycle.state.repositories.length, 1, 'only the newly forked repository remains');
}

run().then(() => console.log('environment store: PASS'));

(async function groupsAndViewpoint() {
  const store = createEnvironmentStore({ invoke: async (capability) => {
    if (capability === 'simulation.environment.workspace.search') return { items: [{ workspace_gid: '31', name: '临时评审' }] };
    if (capability === 'project.project.read.atomic.projects_search') return {
      items: [{ gid: '20', project_name: 'X13-2026' }],
    };
    if (capability === 'craft.bop.repository.search') return { items: [{ repository_gid: '10', project_gid: '20' }] };
    if (capability === 'craft.bop.space.search') return { items: [
      { space_gid: '11', repository_gid: '10', space_kind: 'team' },
      { space_gid: '12', repository_gid: '10', space_kind: 'managed_personal' },
    ] };
    throw new Error('unexpected');
  }});
  await store.load();
  assert.deepEqual(store.state.groups.map(group => group.kind), ['project_spaces', 'personal_project_spaces', 'private']);
  assert.deepEqual(store.state.groups.map(group => group.label), ['项目空间', '个人项目空间', '私人仿真环境']);
  assert.equal(store.state.groups[0].items[0].display_label, 'X13-2026');
  assert.equal(store.state.groups[1].items[0].display_label, 'X13-2026');
  store.rememberView({ selectedNodeGid: '88', treeScrollTop: 120, modelScrollTop: 45 });
  store.applyServerUpdate({ records: [{ workspace_gid: '32' }] });
  assert.deepEqual(store.state.view, { selectedNodeGid: '88', treeScrollTop: 120, modelScrollTop: 45 });
})();

(async function projectsRemainVisibleBeforeSpacesAreProvisioned() {
  const store = createEnvironmentStore({ invoke: async capability => {
    if (capability === 'simulation.environment.workspace.search') return { items: [] };
    if (capability === 'project.project.read.atomic.projects_search') return { items: [{ gid: '21', project_name: '空项目' }] };
    if (capability === 'craft.bop.repository.search') return { items: [] };
    throw new Error(`unexpected ${capability}`);
  }});
  await store.load();
  assert.deepEqual(store.state.groups.slice(0, 2).map(group => group.items.map(item => [item.display_label, item.unavailable])), [
    [['空项目', true]], [['空项目', true]],
  ]);
})();

(async function openedProjectSpaceKeepsItsDisplayLabel() {
  const store = createEnvironmentStore({ invoke: async (capability, payload) => {
    if (capability === 'craft.bop.space.get') return { space_gid: payload.space_gid, nodes: [], bindings: [] };
    throw new Error(`unexpected ${capability}`);
  }});
  await store.openRecord('team', { record_gid: '91', display_label: 'W10' });
  assert.equal(store.state.workspace.display_label, 'W10');
  assert.equal(store.state.workspace.workspace_gid, '91');
})();

(async function oneRepositoryFailureDoesNotHideHealthyProjectSpaces() {
  const store = createEnvironmentStore({ invoke: async (capability, payload) => {
    if (capability === 'simulation.environment.workspace.search') return { items: [] };
    if (capability === 'project.project.read.atomic.projects_search') return { items: [
      { gid: '21', project_name: '故障项目' },
      { gid: '22', project_name: 'W10-2026' },
    ] };
    if (capability === 'craft.bop.repository.search') return { items: [
      { repository_gid: '31', project_gid: '21' },
      { repository_gid: '32', project_gid: '22' },
    ] };
    if (capability === 'craft.bop.space.search' && payload.repository_gid === '31') {
      const error = new Error('capacity_unavailable');
      error.code = 'capacity_unavailable';
      throw error;
    }
    if (capability === 'craft.bop.space.search' && payload.repository_gid === '32') return { items: [
      { space_gid: '41', repository_gid: '32', space_kind: 'team' },
      { space_gid: '42', repository_gid: '32', space_kind: 'managed_personal' },
    ] };
    throw new Error(`unexpected ${capability}`);
  }});

  await store.load();

  const w10Team = store.state.groups[0].items.find(item => item.display_label === 'W10-2026');
  const w10Personal = store.state.groups[1].items.find(item => item.display_label === 'W10-2026');
  const failedProject = store.state.groups[0].items.find(item => item.display_label === '故障项目');
  assert.equal(w10Team.record_gid, '41');
  assert.equal(w10Personal.record_gid, '42');
  assert.equal(failedProject.status, '加载失败', 'a failed lookup must not masquerade as an unprovisioned project');
})();

const test = require('node:test');

test('openWorkspace renders a matching authorized cache without a full get', async () => {
  const events = [];
  const cached = { workspace_gid: '91', row_version: 4, cache_revision_hash: `sha256:${'a'.repeat(64)}`, nodes: [{ node_gid: '11' }], bindings: [] };
  const lease = { auth_subject_gid: '30', workspace_gid: '91', row_version: 4,
    cache_revision_hash: cached.cache_revision_hash, expires_at: '2099-01-01T00:00:00Z', read_lease: 'signed-lease-value' };
  const store = createEnvironmentStore({
    getAuthSubjectGid: () => '30',
    cache: { getWorkspace: async () => { events.push('cache'); return { workspace: cached }; } },
    invoke: async capability => { events.push(capability); if (capability.endsWith('cache_lease.get')) return lease; throw new Error('full_get_not_expected'); },
  });
  store.subscribe(state => { if (state.workspace) events.push(`render:${state.cacheStatus}`); });
  await store.openWorkspace('91');
  assert.deepEqual(events, ['simulation.environment.workspace.cache_lease.get', 'cache', 'render:validated']);
});

test('changed cache revision fetches and publishes the authoritative workspace', async () => {
  const calls = []; const writes = [];
  const hash = `sha256:${'b'.repeat(64)}`;
  const lease = { auth_subject_gid: '30', workspace_gid: '91', row_version: 5,
    cache_revision_hash: hash, expires_at: '2099-01-01T00:00:00Z', read_lease: 'signed-lease-value' };
  const store = createEnvironmentStore({
    getAuthSubjectGid: () => '30',
    cache: { getWorkspace: async () => null, putWorkspace: async value => writes.push(value) },
    invoke: async capability => {
      calls.push(capability);
      if (capability.endsWith('cache_lease.get')) return lease;
      return { workspace_gid: '91', row_version: 5, cache_revision_hash: hash, nodes: [], bindings: [] };
    },
  });
  await store.openWorkspace('91');
  assert.deepEqual(calls, ['simulation.environment.workspace.cache_lease.get', 'simulation.environment.workspace.get']);
  assert.equal(writes[0].cacheRevisionHash, hash);
  assert.equal(store.state.cacheStatus, 'authoritative');
});

test('missing cache signing configuration falls back to an authoritative workspace read', async () => {
  const calls = [];
  const unavailable = new Error('cache_lease_signing_key_unavailable');
  unavailable.code = 'cache_lease_signing_key_unavailable';
  const store = createEnvironmentStore({
    getAuthSubjectGid: () => '30',
    cache: { getWorkspace: async () => { throw new Error('unsigned_cache_must_not_be_read'); } },
    invoke: async capability => {
      calls.push(capability);
      if (capability.endsWith('cache_lease.get')) throw unavailable;
      return { workspace_gid: '91', row_version: 1, cache_revision_hash: `sha256:${'e'.repeat(64)}`, nodes: [], bindings: [] };
    },
  });
  await store.openWorkspace('91');
  assert.deepEqual(calls, [
    'simulation.environment.workspace.cache_lease.get',
    'simulation.environment.workspace.get',
  ]);
  assert.equal(store.state.cacheStatus, 'authoritative');
});

test('expired lease never renders cached nodes and cache failures fall back to gateway get', async () => {
  const renders = [];
  const hash = `sha256:${'c'.repeat(64)}`;
  const store = createEnvironmentStore({
    getAuthSubjectGid: () => '30',
    cache: { getWorkspace: async () => { throw new Error('indexeddb_broken'); }, putWorkspace: async () => {} },
    invoke: async capability => capability.endsWith('cache_lease.get')
      ? { auth_subject_gid: '30', workspace_gid: '91', row_version: 1, cache_revision_hash: hash,
        expires_at: '2000-01-01T00:00:00Z', read_lease: 'signed-lease-value' }
      : { workspace_gid: '91', row_version: 1, cache_revision_hash: hash, nodes: [], bindings: [] },
  });
  store.subscribe(state => renders.push(state.workspace));
  await store.openWorkspace('91');
  assert.equal(renders.filter(Boolean).length, 1);
  assert.equal(store.state.cacheStatus, 'authoritative');
});

test('permission denial clears subject cache and does not reuse stale data', async () => {
  let cleared = null; let fullGet = false;
  const denied = new Error('permission_denied'); denied.code = 'permission_denied';
  const store = createEnvironmentStore({
    getAuthSubjectGid: () => '30',
    cache: { clearLocal: async value => { cleared = value; }, getWorkspace: async () => ({ workspace: { workspace_gid: '91' } }) },
    invoke: async capability => { if (capability.endsWith('cache_lease.get')) throw denied; fullGet = true; },
  });
  await assert.rejects(store.openWorkspace('91'), /permission_denied/);
  assert.deepEqual(cleared, { authSubjectGid: '30' });
  assert.equal(fullGet, false);
  assert.equal(store.state.workspace, null);
});

test('network failure may show only a still-leased offline cache and keeps it read-only', async () => {
  const cached = { workspace_gid: '91', row_version: 4, cache_revision_hash: `sha256:${'a'.repeat(64)}`, nodes: [], bindings: [] };
  const store = createEnvironmentStore({
    getAuthSubjectGid: () => '30',
    cache: { getWorkspace: async ({ lease }) => lease ? null : { workspace: cached } },
    invoke: async () => { const error = new Error('network_unavailable'); error.code = 'network_unavailable'; throw error; },
  });
  assert.equal((await store.openWorkspace('91')).workspace_gid, '91');
  assert.equal(store.state.cacheStatus, 'offline');
  assert.equal(store.state.readOnly, true);
  await assert.rejects(store.mutate('simulation.environment.structure_node.create', { workspace_gid: '91' }), /workspace_read_only/);
});

test('successful mutation advances memory and publishes a newly leased cache generation', async () => {
  const writes = []; const hash = `sha256:${'d'.repeat(64)}`;
  const store = createEnvironmentStore({
    getAuthSubjectGid: () => '30',
    cache: { putWorkspace: async value => writes.push(value) },
    invoke: async capability => capability.endsWith('cache_lease.get')
      ? { auth_subject_gid: '30', workspace_gid: '91', row_version: 2, cache_revision_hash: hash,
        expires_at: '2099-01-01T00:00:00Z', read_lease: 'signed-lease-value' }
      : { entity_gid: '11', row_version: 2, cache_revision_hash: hash,
        patch: { op: 'create', node_gid: '11', parent_gid: null, node_type: 'line', name: 'Line', position: 0 } },
  });
  store.applyServerUpdate({ workspace: { workspace_gid: '91', row_version: 1,
    cache_revision_hash: `sha256:${'a'.repeat(64)}`, nodes: [], bindings: [] } });
  await store.mutate('simulation.environment.structure_node.create', { workspace_gid: '91' });
  assert.equal(store.state.workspace.cache_revision_hash, hash);
  assert.equal(writes.length, 1);
  assert.equal(writes[0].rowVersion, 2);
});
