const assert = require('assert');
global.AI00SimulationEnvironmentStore = require('./environment_store.js');
global.AI00SimulationEnvironmentRecords = { render() {} };
global.AI00SimulationEnvironmentTree = { render() {} };
require('./environment_workspace.js');

{
  const derive = global.AI00SimulationEnvironmentWorkspace.deriveWorkspaceActions;
  assert.deepStrictEqual(derive({ workspace: null }), {
    insert: false, save: false, sync: false, export: false, writeback: false,
    reason: '请先新建或打开个人仿真环境',
  });
  assert.deepStrictEqual(derive({ workspace: { status: 'active', is_owner: true }, hasBopSource: true }), {
    insert: true, save: true, sync: true, export: true, writeback: false, reason: '',
  });
}

{
  let now = 1000;
  let tick;
  let cleared;
  const target = { textContent: '' };
  const timer = global.AI00SimulationEnvironmentWorkspace.createElapsedIndicator(target, '正在加载：W10', {
    now: () => now,
    setInterval: handler => { tick = handler; return 7; },
    clearInterval: id => { cleared = id; },
  });
  assert.strictEqual(target.textContent, '正在加载：W10 · 已用 0s');
  now = 4600;
  tick();
  assert.strictEqual(target.textContent, '正在加载：W10 · 已用 3s');
  assert.strictEqual(timer.elapsedSeconds(), 3);
  timer.stop();
  assert.strictEqual(cleared, 7);
}

function element() {
  const listeners = {};
  return {
    textContent: '', scrollTop: 0,
    addEventListener(type, handler) { listeners[type] = handler; },
    async dispatch(type, event = {}) { return listeners[type]?.(event); },
  };
}

function flush() { return new Promise(resolve => setImmediate(resolve)); }

function dialogElement() {
  const listeners = {};
  const classes = new Set(['hidden']);
  const submit = { disabled: false };
  return {
    dataset: {}, value: '', checked: false, disabled: false, textContent: '', children: [],
    classList: {
      add(value) { classes.add(value); }, remove(value) { classes.delete(value); },
      toggle(value, force) { if (force) classes.add(value); else classes.delete(value); },
      contains(value) { return classes.has(value); },
    },
    addEventListener(type, handler) { listeners[type] = handler; },
    dispatch(type, event = {}) { return listeners[type]?.(event); },
    replaceChildren(...children) { this.children = children; this.value = children[0]?.value || ''; },
    querySelector(selector) { return selector === 'button[type="submit"]' ? submit : null; },
    submit,
  };
}

(async () => {
  const originalOption = global.Option;
  const originalEvent = global.Event;
  global.Option = function Option(text, value) { this.textContent = text; this.value = value; };
  const forkElements = {
    overlay: dialogElement(), form: dialogElement(), sourceVersion: dialogElement(),
    targetProject: dialogElement(), targetRepository: dialogElement(), targetProjectField: dialogElement(),
    targetRepositoryField: dialogElement(), depth: dialogElement(), depthField: dialogElement(),
    privateFields: dialogElement(), targetName: dialogElement(), targetVersion: dialogElement(),
    targetNameLabel: dialogElement(), targetVersionField: dialogElement(),
    includePersonal: dialogElement(), includePersonalField: dialogElement(), summary: dialogElement(),
    error: dialogElement(), cancel: dialogElement(),
  };
  forkElements.depth.value = 'all';
  const forkView = global.AI00SimulationEnvironmentWorkspace.createForkDialog(forkElements);
  const forkOpen = forkView.open({
    kind: 'team', record: { name: 'W10 主 BOP', version_label: 'V2' },
    versions: [{ version_gid: '9001', version_label: '基线 2' }],
    projects: [{ gid: '8001', name: 'W10-2027' }], repositories: [],
  });
  assert.strictEqual(forkElements.overlay.classList.contains('hidden'), false);
  assert.strictEqual(forkElements.depthField.classList.contains('hidden'), false, 'team fork must show copy depth');
  assert.strictEqual(forkElements.sourceVersion.value, '9001');
  assert.strictEqual(forkElements.privateFields.classList.contains('hidden'), false, 'team fork must show repository name');
  forkElements.form.dispatch('submit', { preventDefault() {} });
  assert.deepStrictEqual(await forkOpen, {
    sourceVersionGid: '9001', forkDepth: 'all', expectedTargetSlot: 0,
    targetProjectGid: '8001', targetName: 'W10 主 BOP Fork', targetProjectName: 'W10-2027',
    includePersonalMigration: false,
  });
  global.Option = originalOption;

  const { JSDOM } = require('jsdom');
  const dialogDom = new JSDOM(`<div id="overlay" class="hidden"><form id="form"><input id="name"><select id="primary"></select><select id="review"><option value="scattered_review">零散评审</option></select><input id="version"><select id="status"><option value="active">活动</option></select><select id="visibility"><option value="private">私人</option></select><input id="updated"><div id="error"></div><button id="cancel" type="button">取消</button><button id="save" type="submit">保存</button></form></div>`);
  const doc = dialogDom.window.document;
  global.Option = dialogDom.window.Option;
  global.Event = dialogDom.window.Event;
  const compactDialog = global.AI00SimulationEnvironmentWorkspace.createDialog({
    overlay: doc.getElementById('overlay'), form: doc.getElementById('form'), title: doc.createElement('div'),
    name: doc.getElementById('name'), primary: doc.getElementById('primary'), reviewType: doc.getElementById('review'),
    version: doc.getElementById('version'), workspaceStatus: doc.getElementById('status'), visibility: doc.getElementById('visibility'),
    updated: doc.getElementById('updated'), error: doc.getElementById('error'), cancel: doc.getElementById('cancel'), save: doc.getElementById('save'),
  });
  const compactResult = compactDialog.open({
    mode: 'create', workspace: { name: '主项目环境', review_type: 'scattered_review', version_label: 'V1', status: 'active', visibility: 'private', primary_project_gid: null },
    projects: [{ gid: '501', name: 'W10' }], projectsPromise: Promise.resolve([{ gid: '501', name: 'W10' }]),
  });
  await flush();
  doc.getElementById('primary').value = '501';
  doc.getElementById('form').requestSubmit();
  assert.deepStrictEqual(await compactResult, {
    name: '主项目环境', review_type: 'scattered_review', version_label: 'V1', status: 'active', visibility: 'private',
    project_gids: ['501'], primary_project_gid: '501',
  });
  global.Option = originalOption;
  global.Event = originalEvent;


  const calls = [];
  const newButton = element();
  const dialogCalls = [];
  const draft = {
    name: '仿真环境 1', review_type: 'node_review', version_label: 'V1',
    status: 'active', visibility: 'private', project_gids: ['501', '502'], primary_project_gid: '501',
  };
  const controller = global.AI00SimulationEnvironmentWorkspace.createController({
    invoke: async (capability, request) => {
      calls.push([capability, request]);
      if (capability === 'craft.bop.repository.search') return { data: { items: [] } };
      if (capability.endsWith('.create')) return { data: {
        workspace_gid: '202', version_gid: '203', name: request.payload.name,
        status: 'active', row_version: 1, nodes: [], bindings: [],
      } };
      return { data: { items: [{ workspace_gid: '101', name: 'W1' }] } };
    },
    recordsView: global.AI00SimulationEnvironmentRecords,
    treeView: global.AI00SimulationEnvironmentTree,
    elements: {
      records: element(), tree: element(), status: element(), newButton,
      actions: { writeback: element() },
    },
    dialogView: { open(value) { dialogCalls.push(value); return Promise.resolve(draft); } },
  });
  await controller.start();
  assert.strictEqual(calls[0][0], 'simulation.environment.workspace.search');
  assert.deepStrictEqual(calls[0][1], { version: 1, payload: { page_size: 50 } });
  assert.strictEqual(controller.store.state.records[0].workspace_gid, '101');
  await newButton.dispatch('click');
  assert.strictEqual(calls[1][0], 'project.project.read.atomic.projects_search');
  assert.strictEqual(calls[2][0], 'craft.bop.repository.search');
  assert.strictEqual(calls[3][0], 'simulation.environment.workspace.create');
  assert.deepStrictEqual(calls[3][1], { version: 1, payload: draft });
  assert.strictEqual(dialogCalls.length, 1);
  assert.strictEqual(controller.store.state.workspace.workspace_gid, '202');
  assert.strictEqual(controller.store.state.records[0].workspace_gid, '202');

  const failedButton = element();
  const failedStatus = element();
  const failed = global.AI00SimulationEnvironmentWorkspace.createController({
    invoke: async capability => {
      if (capability.endsWith('.search')) return { data: { items: [] } };
      const error = new Error('provider_failed'); error.code = 'provider_failed'; throw error;
    },
    recordsView: global.AI00SimulationEnvironmentRecords,
    treeView: global.AI00SimulationEnvironmentTree,
    elements: { records: element(), tree: element(), status: failedStatus, newButton: failedButton },
    dialogView: { open() { return Promise.resolve({ name: '失败环境', review_type: 'scattered_review', version_label: 'V1', status: 'active', visibility: 'private', project_gids: [], primary_project_gid: null }); } },
  });
  await failed.start();
  await failedButton.dispatch('click');
  await flush();
  assert.strictEqual(failedStatus.textContent, '创建失败：provider_failed');

  let releaseSearch;
  let queuedDialogOpened = false;
  const slowCalls = [];
  const queuedButton = element();
  const queued = global.AI00SimulationEnvironmentWorkspace.createController({
    invoke: async (capability, request) => {
      slowCalls.push(capability);
      if (capability === 'simulation.environment.workspace.search') {
        await new Promise(resolve => { releaseSearch = resolve; });
        return { data: { items: [] } };
      }
      if (capability === 'craft.bop.repository.search') return { data: { items: [] } };
      return { data: { workspace_gid: '303', version_gid: '304', name: request.payload.name,
        status: 'active', row_version: 1, nodes: [], bindings: [] } };
    },
    recordsView: global.AI00SimulationEnvironmentRecords,
    treeView: global.AI00SimulationEnvironmentTree,
    elements: { records: element(), tree: element(), status: element(), newButton: queuedButton },
    dialogView: { open() { queuedDialogOpened = true; return Promise.resolve({ name: '排队创建', review_type: 'other', version_label: 'V1', status: 'active', visibility: 'private', project_gids: [], primary_project_gid: null }); } },
  });
  const starting = queued.start();
  const clicking = queuedButton.dispatch('click');
  assert.strictEqual(queuedDialogOpened, true, 'dialog must open before initial workspace loading completes');
  await flush();
  assert.ok(
    slowCalls.includes('simulation.environment.workspace.create'),
    'a stalled initial search must not block an explicitly confirmed workspace create',
  );
  assert.strictEqual(queued.store.state.workspace.workspace_gid, '303');
  releaseSearch();
  await Promise.all([starting, clicking]);
  assert.deepStrictEqual(slowCalls, [
    'simulation.environment.workspace.search',
    'project.project.read.atomic.projects_search',
    'simulation.environment.workspace.create',
    'craft.bop.repository.search',
  ]);
  assert.strictEqual(queued.store.state.workspace.workspace_gid, '303');
  assert.strictEqual(queued.store.state.records[0].workspace_gid, '303', 'late search results must not erase the created workspace');

  const editButton = element();
  const editCalls = [];
  const editing = global.AI00SimulationEnvironmentWorkspace.createController({
    invoke: async (capability, request) => {
      editCalls.push([capability, request]);
      if (capability === 'simulation.environment.workspace.search') return { data: { items: [{ workspace_gid: '401', version_gid: '402', name: '旧名称', review_type: 'other', version_label: 'A', status: 'active', visibility: 'private', project_gids: [], primary_project_gid: null, owner_gid: '30', is_owner: true, row_version: 3 }] } };
      if (capability === 'craft.bop.repository.search') return { data: { items: [] } };
      if (capability === 'project.project.read.atomic.projects_search') return { data: [] };
      if (capability === 'simulation.environment.workspace.get') return { data: { workspace_gid: '401', version_gid: '402', name: '旧名称', review_type: 'other', version_label: 'A', status: 'active', visibility: 'private', project_gids: [], primary_project_gid: null, owner_gid: '30', is_owner: true, updated_at: '2026-09-09T12:00:00', row_version: 3, nodes: [], bindings: [] } };
      return { data: { entity_gid: '401', row_version: 4, patch: { op: 'update_workspace', name: '新名称', review_type: 'node_review', version_label: 'B', status: 'baseline', visibility: 'shared', project_gids: ['501'], primary_project_gid: '501' } } };
    },
    recordsView: global.AI00SimulationEnvironmentRecords,
    treeView: global.AI00SimulationEnvironmentTree,
    elements: { records: editButton, tree: element(), status: element(), newButton: element() },
    dialogView: { open() { return Promise.resolve({ name: '新名称', review_type: 'node_review', version_label: 'B', status: 'baseline', visibility: 'shared', project_gids: ['501'], primary_project_gid: '501' }); } },
  });
  await editing.start();
  await editing.store.openWorkspace('401');
  await editButton.dispatch('click', { target: { closest(selector) { return selector === '[data-action="edit"]' ? { dataset: { workspaceGid: '401' } } : null; } } });
  assert.strictEqual(editCalls.at(-1)[0], 'simulation.environment.workspace.update');
  assert.strictEqual(editCalls.at(-1)[1].idempotency_key, editCalls.at(-1)[1].payload.idempotency_key);
  assert.strictEqual(editing.store.state.workspace.name, '新名称');
  assert.strictEqual(editing.store.state.records[0].name, '新名称');

  const lifecycleRecords = element();
  const lifecycleCalls = [];
  const lifecycle = global.AI00SimulationEnvironmentWorkspace.createController({
    invoke: async (capability, request) => {
      lifecycleCalls.push([capability, request]);
      if (capability === 'simulation.environment.workspace.search') return { data: { items: [
        { workspace_gid: '801', name: '可清理环境', is_owner: true, row_version: 2 },
      ] } };
      if (capability === 'craft.bop.repository.search') return { data: { items: [
        { repository_gid: '501', project_gid: '601', row_version: 3 },
      ] } };
      if (capability === 'craft.bop.space.search') return { data: { items: [
        { space_gid: '502', repository_gid: '501', space_kind: 'team', row_version: 1, head_row_version: 1 },
      ] } };
      if (capability === 'craft.bop.space_version.search') return { data: { items: [{ version_gid: '503' }] } };
      if (capability === 'project.project.read.atomic.projects_search') return { data: [{ gid: '602', name: '目标项目' }] };
      if (capability === 'craft.bop.repository.fork.preview') return { data: { preview_gid: '701',
        plan_hash: `sha256:${'a'.repeat(64)}`, allowed_decisions: [] } };
      if (capability === 'craft.bop.repository.fork.apply') return { data: { repository_gid: '702', team_space_gid: '703' } };
      if (capability === 'simulation.environment.workspace.delete') return { data: { deleted: true } };
      throw new Error(`unexpected ${capability}`);
    },
    recordsView: global.AI00SimulationEnvironmentRecords,
    treeView: global.AI00SimulationEnvironmentTree,
    elements: { records: lifecycleRecords, tree: element(), status: element(), newButton: element() },
    dialogView: { open() { return Promise.resolve(null); } },
    forkDialogView: { open() { return Promise.resolve({ sourceVersionGid: '503',
      targetProjectGid: '602', targetName: '目标项目 BOP', targetProjectName: '目标项目',
      forkDepth: 'process', includePersonalMigration: false }); } },
    confirmDelete: () => true,
  });
  await lifecycle.start();
  await lifecycleRecords.dispatch('click', { target: { closest(selector) {
    return selector === '[data-action="fork"]' ? { dataset: { recordKind: 'team', recordGid: '502' } } : null;
  } } });
  assert.deepStrictEqual(lifecycleCalls.slice(-2).map(item => item[0]), [
    'craft.bop.repository.fork.preview', 'craft.bop.repository.fork.apply',
  ]);
  await lifecycleRecords.dispatch('click', { target: { closest(selector) {
    return selector === '[data-action="delete"]' ? { dataset: { recordKind: 'private', recordGid: '801' } } : null;
  } } });
  assert.strictEqual(lifecycleCalls.at(-1)[0], 'simulation.environment.workspace.delete');

  const replayRecords = element();
  let replayed = null;
  const replay = global.AI00SimulationEnvironmentWorkspace.createController({
    invoke: async capability => capability === 'simulation.environment.workspace.search'
      ? { data: { items: [{ workspace_gid: '901', version_gid: '902', name: '冻结分析', status: 'frozen', is_owner: true }] } }
      : { data: { items: [] } },
    recordsView: global.AI00SimulationEnvironmentRecords,
    treeView: global.AI00SimulationEnvironmentTree,
    elements: { records: replayRecords, tree: element(), status: element(), newButton: element() },
    dialogView: { open() { return Promise.resolve(null); } },
    forkDialogView: { open() { return Promise.resolve(null); } },
    openFrozen: async record => { replayed = record; },
  });
  await replay.start();
  await replayRecords.dispatch('click', { target: { closest(selector) {
    return selector === '[data-action="replay"]' ? { dataset: { recordGid: '901' } } : null;
  } } });
  assert.strictEqual(replayed.version_gid, '902');
  console.log('environment workspace: PASS');
})().catch(error => { console.error(error); process.exitCode = 1; });
