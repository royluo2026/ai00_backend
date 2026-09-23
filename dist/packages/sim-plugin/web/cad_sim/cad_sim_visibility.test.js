const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const { JSDOM } = require('jsdom');
const snapshotTree = require('./vm_snapshot_tree.js');

const source = fs.readFileSync(path.join(__dirname, 'cad_sim.js'), 'utf8');
const styleSource = fs.readFileSync(path.join(__dirname, 'cad_sim.css'), 'utf8');
const markupSource = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');

test('routine full-show and full-hide controls do not ask for browser confirmation', () => {
  assert.match(source, /visibility\.change\.request', \{ action: 'all_on' \}, \{ confirmation: false \}/);
  assert.match(source, /visibility\.change\.request', \{ action: 'all_off' \}, \{ confirmation: false \}/);
});

test('command completion polling does not add a full second of UI latency', () => {
  const waiter = source.slice(source.indexOf('async function _waitVisMockupCommand'), source.indexOf('const _visReadQueues'));
  assert.match(waiter, /setTimeout\(resolve, 200\)/);
});

test('command completion polling survives a transient provider failure without replaying the write', () => {
  const waiter = source.slice(source.indexOf('async function _waitVisMockupCommand'), source.indexOf('const _visReadQueues'));
  assert.match(waiter, /catch \(error\)/);
  assert.match(waiter, /error\?\.message !== 'provider_failed'/);
  assert.doesNotMatch(waiter, /visibility\.change\.request/);
});

test('uncertain command status preserves the adapter error code for recovery UI', async () => {
  const waiter = source.slice(source.indexOf('async function _waitVisMockupCommand'), source.indexOf('const _visReadQueues'));
  const context = vm.createContext({
    _invokeCapability: async () => ({
      status: 'outcome_unknown',
      outcome: { steps: [{ error_code: 'teamcenter_login_required' }] },
    }),
  });
  vm.runInContext(waiter, context);
  await assert.rejects(context._waitVisMockupCommand('operation-1', 1), /teamcenter_login_required/);
});

test('VM tree node visibility and highlight use governed Connector requests', () => {
  const action = source.slice(source.indexOf('async function _visNodeAction'), source.indexOf('/** 右键上下文菜单 */'));
  assert.match(action, /simulation\.vismockup\.node\.visibility\.change\.request/);
  assert.match(action, /simulation\.vismockup\.node\.selection\.change\.request/);
  assert.doesNotMatch(action, /_bridge\(/);
});

test('VM tree checkbox sends explicit idempotent visibility states and keeps node state current', async () => {
  const dom = new JSDOM('<!doctype html><body></body>', { runScripts: 'outside-only', url: 'http://127.0.0.1/' });
  vm.runInContext(source, dom.getInternalVMContext());
  vm.runInContext(`
    _vmConnected = true;
    window.__visibilityActions = [];
    _requestVisMockupCommand = async (_capabilityId, payload) => {
      window.__visibilityActions.push(payload.action);
      return { steps: [{ result: { visible: payload.action === 'show' } }] };
    };
    window.__row = _buildVisNodeEl({ key: 'node-1', name: '节点 1', visible: true, children: [] }, 1);
    document.body.appendChild(window.__row);
  `, dom.getInternalVMContext());

  const checkbox = dom.window.document.querySelector('.cs-vis-visibility');
  assert.equal(checkbox.checked, true);
  checkbox.click();
  await new Promise(resolve => setImmediate(resolve));
  vm.runInContext('_vmConnected = true;', dom.getInternalVMContext());
  checkbox.click();
  await new Promise(resolve => setImmediate(resolve));

  assert.deepEqual([...dom.window.__visibilityActions], ['hide', 'show']);
  dom.window.close();
});

test('VisMockup tree actions carry the matching Teamcenter occurrence path', async () => {
  const dom = new JSDOM('<!doctype html><body></body>', { runScripts: 'outside-only', url: 'http://127.0.0.1/' });
  dom.window.AI00VmSnapshotTree = snapshotTree;
  vm.runInContext(source, dom.getInternalVMContext());
  const occurrencePath = [
    { occurrence_uid: 'parent-instance', item_revision_uid: 'parent-revision' },
    { occurrence_uid: 'deep-instance', item_revision_uid: 'deep-revision' },
  ];
  vm.runInContext(`
    _vmConnected = true;
    _modelDocumentCollection = { state: { documents: [{
      source_kind: 'teamcenter_online', role: 'primary', product_tree: { nodes: [{
        node_key: 'tc:full-node-key', control_key: 'tc:deep-instance', occurrence_path: ${JSON.stringify(occurrencePath)}
      }] }
    }] } };
    _visNodeMap = {};
    _updateVisVisibilityControls = () => {};
    _updateAlternateVisibilityControls = () => {};
    window.__visCalls = [];
    _requestVisMockupCommand = async (capabilityId, payload) => {
      window.__visCalls.push([capabilityId, payload]);
      return { steps: [{ result: { visible: true } }] };
    };
  `, dom.getInternalVMContext());

  await vm.runInContext("_visNodeAction('tc:deep-instance', 'show')", dom.getInternalVMContext());

  assert.deepEqual(JSON.parse(JSON.stringify(dom.window.__visCalls[0][1])), {
    node_key: 'tc:deep-instance', action: 'show', occurrence_path: occurrencePath,
  });
  dom.window.close();
});

test('VisMockup tree actions load missing Teamcenter ancestors before sending a deep-node path', async () => {
  const dom = new JSDOM('<!doctype html><body></body>', { runScripts: 'outside-only', url: 'http://127.0.0.1/' });
  dom.window.AI00VmSnapshotTree = snapshotTree;
  vm.runInContext(source, dom.getInternalVMContext());
  vm.runInContext(`
    _vmConnected = true;
    _visTreeSnapshot = { children: [{ children: [{ key: 'tc:root', children: [
      { key: 'tc:parent', children: [{ key: 'tc:deep-instance', children: [] }] }
    ] }] }] };
    _modelDocumentCollection = { state: { documents: [{
      source_kind: 'teamcenter_online', role: 'primary', source_selector: { object_uid: 'online-model' },
      product_tree: { nodes: [{ node_key: 'tc:root', parent_key: null, occurrence_path: [], has_children: true }] }
    }] } };
    _visNodeMap = {};
    _updateVisVisibilityControls = () => {};
    _updateAlternateVisibilityControls = () => {};
    window.__visCalls = [];
    window.__reads = [];
    window.AI00TeamcenterOnlineSource = { readChildren: async (_request, _document, tree, parentPath) => {
      window.__reads.push(parentPath);
      if (!parentPath.length) tree.nodes.push({
        node_key: 'tc:parent', parent_key: 'tc:root',
        occurrence_path: [{ occurrence_uid: 'parent-instance', item_revision_uid: 'parent-revision' }], has_children: true,
      });
      else tree.nodes.push({
        node_key: 'tc:deep-instance', parent_key: 'tc:parent',
        occurrence_path: [
          ...parentPath,
          { occurrence_uid: 'deep-instance', item_revision_uid: 'deep-revision' },
        ], has_children: false,
      });
    } };
    _requestVisMockupCommand = async (_capabilityId, payload) => {
      window.__visCalls.push(payload);
      return { steps: [{ result: { visible: true } }] };
    };
  `, dom.getInternalVMContext());

  await vm.runInContext("_visNodeAction('tc:deep-instance', 'show')", dom.getInternalVMContext());

  assert.equal(dom.window.__reads.length, 2);
  assert.deepEqual(JSON.parse(JSON.stringify(dom.window.__visCalls[0].occurrence_path)), [
    { occurrence_uid: 'parent-instance', item_revision_uid: 'parent-revision' },
    { occurrence_uid: 'deep-instance', item_revision_uid: 'deep-revision' },
  ]);
  dom.window.close();
});

test('VM parent checkbox reflects mixed descendants and unknown depth', () => {
  const dom = new JSDOM('<!doctype html><body></body>', { runScripts: 'outside-only', url: 'http://127.0.0.1/' });
  vm.runInContext(fs.readFileSync(path.join(__dirname, 'model_document_collection.js'), 'utf8'), dom.getInternalVMContext());
  vm.runInContext(source, dom.getInternalVMContext());
  vm.runInContext(`
    _vmConnected = true;
    window.__parent = { key: 'parent', name: '父项', visible: true, children: [
      { key: 'a', name: 'A', visible: true, children: [] },
      { key: 'b', name: 'B', visible: false, children: [] },
    ] };
    _visTreeSnapshot = { key: null, children: [window.__parent] };
    document.body.append(_buildVisNodeEl(window.__parent, 0));
    _updateVisVisibilityControls();
  `, dom.getInternalVMContext());
  const parent = dom.window.document.querySelector('.cs-vis-visibility');
  assert.equal(parent.indeterminate, true);
  vm.runInContext('window.__parent.children[1].visible = true; _updateVisVisibilityControls();', dom.getInternalVMContext());
  assert.equal(parent.checked, true);
  vm.runInContext('window.__parent.children[1].has_more = true; _updateVisVisibilityControls();', dom.getInternalVMContext());
  assert.equal(parent.disabled, true);
  dom.window.close();
});

test('alternate hierarchy visibility derives empty, blue, mixed, and unknown states from runtime nodes', () => {
  const dom = new JSDOM('<!doctype html><body></body>', { runScripts: 'outside-only', url: 'http://127.0.0.1/' });
  vm.runInContext(fs.readFileSync(path.join(__dirname, 'model_document_collection.js'), 'utf8'), dom.getInternalVMContext());
  vm.runInContext(source, dom.getInternalVMContext());
  vm.runInContext(`
    _vmConnected = true;
    _visNodeMap = {
      a: { node: { key: 'a', visible: false } },
      b: { node: { key: 'b', visible: false } },
    };
    window.__item = { kind: 'node', name: '父项', children: [
      { kind: 'placement', name: 'A', source_ref: { node_key: 'a' }, children: [] },
      { kind: 'placement', name: 'B', source_ref: { occurrence_key: 'b' }, children: [] },
    ] };
    window.__row = _buildAlternateTreeItem(window.__item, {});
    document.body.append(window.__row);
  `, dom.getInternalVMContext());
  const check = dom.window.document.querySelector('.cs-alternate-tree-check');
  assert.equal(check.checked, false);
  assert.equal(check.indeterminate, false);
  vm.runInContext('_visNodeMap.a.node.visible = true; _updateAlternateVisibilityControls();', dom.getInternalVMContext());
  assert.equal(check.indeterminate, true);
  vm.runInContext('_visNodeMap.b.node.visible = true; _updateAlternateVisibilityControls();', dom.getInternalVMContext());
  assert.equal(check.checked, true);
  vm.runInContext('delete _visNodeMap.b; _updateAlternateVisibilityControls();', dom.getInternalVMContext());
  assert.equal(check.disabled, true);
  assert.equal(check.checked, false);
  dom.window.close();
});

test('failed alternate batch stops writes and reconciles through a read-only tree refresh', async () => {
  const dom = new JSDOM('<!doctype html><body></body>', { runScripts: 'outside-only', url: 'http://127.0.0.1/' });
  vm.runInContext(fs.readFileSync(path.join(__dirname, 'model_document_collection.js'), 'utf8'), dom.getInternalVMContext());
  vm.runInContext(source, dom.getInternalVMContext());
  vm.runInContext(`
    _vmConnected = true;
    _visNodeMap = { a: { node: { key: 'a', visible: false } }, b: { node: { key: 'b', visible: false } } };
    window.__actions = [];
    _visNodeAction = async (key, action) => {
      window.__actions.push([key, action]);
      if (key === 'b') return { ok: false };
      _visNodeMap[key].node.visible = true;
      return { ok: true };
    };
    _loadVisTree = async () => {
      window.__refreshed = true;
      _visNodeMap.a.node.visible = false;
      _updateAlternateVisibilityControls();
      return true;
    };
    window.__row = _buildAlternateTreeItem({ kind: 'node', children: [
      { kind: 'placement', source_ref: { occurrence_key: 'a' }, children: [] },
      { kind: 'placement', source_ref: { occurrence_key: 'b' }, children: [] },
    ] }, {});
    document.body.append(window.__row);
  `, dom.getInternalVMContext());
  const check = dom.window.document.querySelector('.cs-alternate-tree-check');
  check.click();
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual([...dom.window.__actions].map(item => [...item]), [['a', 'show'], ['b', 'show']]);
  assert.equal(dom.window.__refreshed, true);
  assert.equal(check.checked, false);
  dom.window.close();
});

test('failed readback marks affected alternate visibility unknown', async () => {
  const dom = new JSDOM('<!doctype html><body></body>', { runScripts: 'outside-only', url: 'http://127.0.0.1/' });
  vm.runInContext(fs.readFileSync(path.join(__dirname, 'model_document_collection.js'), 'utf8'), dom.getInternalVMContext());
  vm.runInContext(source, dom.getInternalVMContext());
  vm.runInContext(`
    _vmConnected = true;
    _visNodeMap = { a: { node: { key: 'a', visible: false } } };
    _visNodeAction = async () => ({ ok: false });
    _loadVisTree = async () => false;
    window.__row = _buildAlternateTreeItem({ kind: 'placement', source_ref: { node_key: 'a' }, children: [] }, {});
    document.body.append(window.__row);
  `, dom.getInternalVMContext());
  const check = dom.window.document.querySelector('.cs-alternate-tree-check');
  check.click();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(check.disabled, true);
  assert.equal(check.checked, false);
  dom.window.close();
});

test('concurrent Connector detectors share one version-bound pairing approval', () => {
  const runtime = source.slice(source.indexOf('let _connectorPairingApproval'), source.indexOf('function _visMockupProbeResult'));
  assert.match(runtime, /_connectorPairingApproval\?\.id !== state\.pairing\.id/);
  assert.match(runtime, /await _connectorPairingApproval\.promise/);
  assert.match(runtime, /pairing_version_conflict/);
});

test('idempotent simulation writes send the payload key in the invocation envelope', async () => {
  const dom = new JSDOM('<!doctype html><body></body>', { runScripts: 'outside-only', url: 'http://127.0.0.1/' });
  dom.window.AI00Business = {
    invoke: async (_id, envelope) => envelope,
    available: () => false,
  };
  vm.runInContext(source, dom.getInternalVMContext());
  const envelope = await vm.runInContext(`_invokeCapability(
    'simulation.environment.plmxml.insert',
    { workspace_gid: '10', idempotency_key: 'model-document-10-hash' },
    { idempotency: true }
  )`, dom.getInternalVMContext());
  assert.equal(envelope.idempotency_key, 'model-document-10-hash');
  dom.window.close();
});

test('BOP version discovery accepts the governed version_gid response key', async () => {
  const dom = new JSDOM('<!doctype html><body><select id="bopVersionSel"></select></body>', {
    runScripts: 'outside-only', url: 'http://127.0.0.1/'
  });
  dom.window.AI00Business = {
    available: () => true,
    invoke: async () => ({ items: [{ version_gid: '205576954294833152', bop_name: 'W10-2026', status: 'active' }] }),
  };
  vm.runInContext(source, dom.getInternalVMContext());
  await vm.runInContext('_loadBopVersions()', dom.getInternalVMContext());
  const option = dom.window.document.querySelector('#bopVersionSel option[value="205576954294833152"]');
  assert.ok(option, 'version_gid must become the option value used by the loader');
  dom.window.close();
});

test('BOP line discovery uses the governed bounded node type filter', () => {
  assert.match(source, /craft\.bop\.alt_hierarchy\.read',\s*\{\s*version_gid:\s*version\.value,\s*node_types:\s*\['line',\s*'line_process'\]/);
  assert.match(source, /structure\?\.entries[\s\S]*\['line',\s*'line_process'\]\.includes\(item\.node_type\)/);
});

test('model documents and alternate hierarchies use independent bounded scroll surfaces', () => {
  assert.match(markupSource, /id="modelDocumentsPanel"[\s\S]*id="modelDocumentList"/);
  assert.match(markupSource, /id="alternateHierarchyList"/);
  assert.match(styleSource, /\.cs-model-documents-panel \.cs-model-documents\s*\{[\s\S]*?overflow-y\s*:\s*auto/);
  assert.match(styleSource, /\.cs-environment-stack \.cs-vis-panel \.cs-alternate-hierarchies\s*\{[\s\S]*?overflow-y\s*:\s*auto/);
  assert.match(styleSource, /\.cs-model-document-list\s*\{[^}]*overflow\s*:\s*visible/);
});

test('model files and alternate hierarchies occupy separate draggable columns', () => {
  assert.match(markupSource, /id="modelDocumentsPanel"[\s\S]*id="modelDocumentList"/);
  assert.match(markupSource, /id="simulationEnvironmentPanel"[\s\S]*id="alternateHierarchyList"/);
  assert.match(styleSource, /\.cs-model-documents-panel\s*\{[\s\S]*?flex-direction:\s*column/);
  assert.match(styleSource, /\.cs-model-documents-panel \.cs-model-documents\s*\{[\s\S]*?overflow-y:\s*auto/);
  assert.match(source, /const targetTree = \$\('alternateHierarchyList'\)/);
  assert.match(source, /modelDocumentsPanel\?\.classList\.toggle\('collapsed', !open\)/);
});

test('resource and empty VM panels consume their available column height', () => {
  assert.match(styleSource, /\.cs-object-panel \.cs-resource-library\s*\{[\s\S]*?max-height:\s*none[\s\S]*?flex:\s*1 1 auto/);
  assert.match(styleSource, /\.cs-resource-groups\s*\{[^}]*flex:\s*1 1 auto/);
  assert.match(styleSource, /\.cs-vis-panel:has\(#visTreeBody:empty\) \.cs-alternate-hierarchies\s*\{[\s\S]*?flex:\s*1 1 auto/);
});

test('product tree renders descendants only after a row is expanded', () => {
  const fn = source.slice(source.indexOf('function _buildProductTreeItem'), source.indexOf('function _renderAlternateHierarchies'));
  assert.match(fn, /let rendered\s*=\s*false/);
  assert.match(fn, /if \(!hidden && !rendered\)/);
});

test('dragging a product node carries its occurrence instead of the document root', () => {
  const documents = source.slice(source.indexOf('function _renderModelDocuments'), source.indexOf('function _renderAlternateHierarchies'));
  assert.match(documents, /summary\.draggable = true/);
  assert.match(documents, /line\.draggable = true/);
  assert.match(documents, /application\/x-ai00-model-node/);
  assert.match(documents, /node_key: item\.node_key/);
  assert.match(source, /modelNodeJson \? _placeModelNode/);
  assert.match(source, /source_ref: \{ document_gid: source\.document_gid, node_key: modelNode\.node_key/);
});

test('workspace refresh reuses parsed product trees for unchanged documents', () => {
  const refresh = source.slice(source.indexOf('async function _refreshModelDocuments'), source.indexOf('function _dependencyFilename'));
  assert.match(refresh, /priorTrees = new Map/);
  assert.match(refresh, /prior\?\.content_sha256 === item\.content_sha256/);
  assert.match(refresh, /if \(!item\.media_type\.includes\('plmxml'\) \|\| !item\.artifact_ref \|\| item\.product_tree\) return/);
});

test('structure tree visibility controls use a minimal empty-or-check glyph', () => {
  assert.match(styleSource, /\.cs-alternate-tree-check[^}]*appearance\s*:\s*none/);
  assert.match(styleSource, /\.cs-alternate-tree-check:checked[^}]*background-image\s*:/);
  assert.match(styleSource, /\.cs-vis-visibility:checked[^}]*background-image\s*:/);
  assert.match(styleSource, /\.cs-alternate-tree-check:checked,\.cs-vis-visibility:checked\{[^}]*background-color:transparent/);
  assert.match(styleSource, /\.cs-alternate-tree-check:indeterminate,\.cs-vis-visibility:indeterminate\{[^}]*stroke='%2394a3b8'/);
});
