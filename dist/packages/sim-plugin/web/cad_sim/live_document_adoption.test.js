const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { JSDOM } = require('jsdom');
const { createController, unavailable } = require('./live_document_adoption');
const session = () => ({ document_session: 'native-session-A', display_name: 'assembly.jt', connection_id: 'trusted-connector' });
const result = { workspace_gid: '101', version_gid: '102', model_document_gid: '103', state: 'importing', created: true };
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; };

test('committed model opens before slow hierarchy inventory finishes', async () => {
  const inventory = deferred(), opened = [];
  const controller = createController({ makeKey: () => 'model-first', adapter: {
    readCurrentDocument: async () => session(),
    adopt: async () => result,
    openWorkspace: async gid => opened.push(gid),
    importHierarchies: () => inventory.promise,
  } });
  await controller.open();
  const pending = controller.confirm();
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(opened, ['101']);
  assert.equal(controller.state.model, '已登记');
  inventory.reject(new Error('inventory unavailable'));
  await pending;
  assert.deepEqual(opened, ['101']);
  assert.equal(controller.state.errorCode, 'hierarchy_import_failed');
});

test('no adapter fails closed and cannot submit', async () => {
  const controller = createController();
  await controller.open('shown-title.jt');
  await controller.confirm();
  assert.equal(controller.state.error, unavailable);
  assert.equal(controller.state.document, null);
  assert.equal(controller.state.operationKey, null);
});

test('pins exact session, ignores duplicate clicks, importing is not model/AH completion', async () => {
  const document = session(), pending = deferred(), calls = [], opened = [];
  const controller = createController({ makeKey: () => 'intent-1', adapter: {
    readCurrentDocument: async () => document,
    adopt: request => { calls.push(request); return pending.promise; },
    openWorkspace: async gid => opened.push(gid),
  } });
  await controller.open(); controller.setName('我的环境');
  document.document_session = 'native-session-B';
  const submitting = controller.confirm(); await controller.confirm();
  assert.equal(calls.length, 1);
  assert.equal(calls[0].document.document_session, 'native-session-A');
  assert.equal(calls[0].operation_key, 'intent-1');
  assert.equal(calls[0].name, '我的环境');
  pending.resolve(result); await submitting;
  assert.deepEqual(opened, ['101']);
  assert.equal(controller.state.model, '已登记');
  assert.equal(controller.state.ah, '待导入');
});

test('unknown outcome keeps key across dismissal/reopen and never resubmits', async () => {
  let calls = 0;
  const controller = createController({ makeKey: () => 'reconcile-me', adapter: {
    readCurrentDocument: async () => session(),
    adopt: async () => { calls++; throw new Error('timeout'); }, openWorkspace: async () => {},
  } });
  await controller.open(); await controller.confirm(); controller.dismiss();
  await controller.open(); await controller.confirm();
  assert.equal(calls, 1); assert.equal(controller.state.operationKey, 'reconcile-me');
  assert.equal(controller.state.phase, 'unknown');
});

for (const action of ['dismiss', 'selectionChanged']) test(`late completion after ${action} cannot select A`, async () => {
  const pending = deferred(); let opened = 0;
  const controller = createController({ makeKey: () => 'key', adapter: {
    readCurrentDocument: async () => session(), adopt: () => pending.promise, openWorkspace: async () => { opened++; },
  } });
  await controller.open(); const submitting = controller.confirm(); controller[action]();
  pending.resolve(result); await submitting;
  assert.equal(opened, 0);
  if (action === 'dismiss') assert.equal(controller.state.visible, false);
});

test('reused binding selects only while intent remains current; async selection has a live fence', async () => {
  const pending = deferred(); let selected = 'B';
  const controller = createController({ makeKey: () => 'key', adapter: {
    readCurrentDocument: async () => session(), adopt: async () => ({ ...result, created: false }),
    openWorkspace: async (gid, { isCurrent }) => { await pending.promise; if (isCurrent()) selected = gid; },
  } });
  await controller.open(); const submitting = controller.confirm(); await Promise.resolve();
  assert.match(controller.state.binding, /复用/);
  controller.selectionChanged(); pending.resolve(); await submitting;
  assert.equal(selected, 'B');
});

test('late document read cannot reopen a dismissed dialog; title/path is not a session', async () => {
  const pending = deferred();
  const controller = createController({ adapter: { readCurrentDocument: () => pending.promise, adopt() {}, openWorkspace() {} } });
  const opening = controller.open(); controller.dismiss(); pending.resolve(session()); await opening;
  assert.equal(controller.state.visible, false); assert.equal(controller.state.document, null);
  const invalid = createController({ adapter: { readCurrentDocument: async () => ({ display_name: 'a.jt', pid: 10, path: 'a.jt' }), adopt() {}, openWorkspace() {} } });
  await invalid.open(); assert.equal(invalid.state.phase, 'error');
});

test('selection failure preserves binding/result/key and retries only selection', async () => {
  let adoptions = 0, selections = 0;
  const controller = createController({ makeKey: () => 'same-key', adapter: {
    readCurrentDocument: async () => session(), adopt: async () => { adoptions++; return result; },
    openWorkspace: async () => { if (++selections === 1) throw new Error('network'); },
  } });
  await controller.open(); await controller.confirm();
  assert.equal(controller.state.phase, 'bound');
  assert.equal(controller.state.errorCode, 'workspace_open_failed');
  assert.deepEqual(controller.state.result, result);
  assert.equal(controller.state.operationKey, 'same-key');
  controller.dismiss(); await controller.open();
  await controller.confirm(); await controller.retrySelection();
  assert.equal(adoptions, 1); assert.equal(selections, 2);
  assert.equal(controller.state.phase, 'bound'); assert.equal(controller.state.error, '');
  assert.equal(controller.state.operationKey, 'same-key');
});

test('controller rejects non-string, empty and overlong environment names before adoption', async () => {
  let adoptions = 0;
  const controller = createController({ makeKey: () => 'key', adapter: {
    readCurrentDocument: async () => session(), adopt: async () => { adoptions++; return result; }, openWorkspace: async () => {},
  } });
  await controller.open();
  for (const name of [null, 5, {}, '   ', 'x'.repeat(201)]) {
    controller.setName(name); await controller.confirm();
    assert.match(controller.state.error, /1–200/);
  }
  assert.equal(adoptions, 0);
  controller.setName('x'.repeat(200)); await controller.confirm(); assert.equal(adoptions, 1);
});

test('mounted subscription accepts own selection but invalidates other selections and explicit intent', async () => {
  const dom = new JSDOM(fs.readFileSync(`${__dirname}/index.html`, 'utf8'), { runScripts: 'outside-only' });
  dom.window.structuredClone = structuredClone;
  dom.window.crypto.randomUUID = () => 'mounted-key';
  let listener, fence, mode = 'own';
  const store = { state: { workspace: null }, subscribe(fn) { listener = fn; return () => {}; } };
  dom.window._simulationEnvironmentWorkspace = { store };
  dom.window.eval(fs.readFileSync(`${__dirname}/live_document_adoption.js`, 'utf8'));
  const mounted = dom.window.AI00LiveDocumentAdoption.mount({ adapter: {
    readCurrentDocument: async () => ({ ...session(), document_session: mode }), adopt: async () => result,
    openWorkspace: async (gid, { isCurrent }) => {
      listener({ workspace: { workspace_gid: mode === 'other' ? 'B' : gid } });
      if (mode === 'click') {
        const record = dom.window.document.createElement('button'); record.dataset.workspaceGid = gid;
        dom.window.document.getElementById('environmentRecordsBody').append(record); record.click();
      }
      if (mode === 'document') dom.window.dispatchEvent(new dom.window.CustomEvent('ai00:live-document-changed'));
      fence = isCurrent();
    },
  } });
  await mounted.controller.open(); await mounted.controller.confirm();
  assert.equal(fence, true); assert.equal(mounted.controller.state.phase, 'bound');
  for (mode of ['other', 'click', 'document']) {
    await mounted.controller.open(); await mounted.controller.confirm();
    assert.equal(fence, false, mode); assert.equal(mounted.controller.state.phase, 'superseded', mode);
  }
  mounted.dispose(); dom.window.close();
});

test('real page entry works without environment, renders inline failure and accessible close', async () => {
  const dom = new JSDOM(fs.readFileSync(`${__dirname}/index.html`, 'utf8'), { runScripts: 'outside-only' });
  dom.window.eval(fs.readFileSync(`${__dirname}/live_document_adoption.js`, 'utf8'));
  const mounted = dom.window.AI00LiveDocumentAdoption.mount();
  const doc = dom.window.document;
  doc.getElementById('vmDocumentLabel').textContent = 'current.jt';
  doc.getElementById('btnAdoptCurrentDocument').click();
  assert.equal(doc.getElementById('btnAdoptCurrentDocument').previousElementSibling.id, 'btnEnvironmentInsert');
  assert.equal(doc.getElementById('ai00StatusBar').contains(doc.getElementById('btnAdoptCurrentDocument')), false);
  assert.equal(doc.getElementById('adoptionDocument').textContent, 'current.jt');
  assert.equal(doc.getElementById('adoptionError').textContent, unavailable);
  assert.equal(doc.getElementById('adoptionConfirm').disabled, true);
  assert.equal(doc.getElementById('liveDocumentAdoption').classList.contains('hidden'), false);
  dom.window.dispatchEvent(new dom.window.CustomEvent('ai00:live-document-changed'));
  assert.equal(mounted.controller.state.phase, 'superseded');
  doc.getElementById('btnAdoptCurrentDocument').click();
  const record = doc.createElement('button'); record.dataset.workspaceGid = 'B';
  doc.getElementById('environmentRecordsBody').append(record); record.click();
  assert.equal(mounted.controller.state.phase, 'superseded');
  doc.getElementById('adoptionClose').click();
  assert.equal(mounted.controller.state.visible, false);
  mounted.dispose(); dom.window.close();
});
