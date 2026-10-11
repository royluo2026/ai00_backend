const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const { JSDOM } = require('jsdom');

function setup() {
  const dom = new JSDOM('<div id="modelDocumentList"></div>', { runScripts: 'outside-only' });
  const context = dom.getInternalVMContext();
  for (const file of ['model_document_collection.js', 'cad_sim.js']) {
    vm.runInContext(fs.readFileSync(path.join(__dirname, file), 'utf8'), context);
  }
  vm.runInContext(`
    document.removeEventListener('DOMContentLoaded', init);
    _modelDocumentCollection = AI00ModelDocumentCollection.createCollection();
    _modelDocumentCollection.replace([
      {document_gid:'1',role:'primary',media_type:'model/vnd.jt',display_name:'Main'},
      {document_gid:'2',role:'inserted',media_type:'model/vnd.jt',display_name:'Tool'}
    ]);
    _modelDocumentCollection.state.selectedDocumentGid='2';
    _modelDocumentWorkspaceGid='10';
    window._simulationEnvironmentWorkspace={store:{state:{workspace:{workspace_gid:'10',row_version:7,dirty:true}}}};
    window.calls=[];window.events=[];
    window.addEventListener('simulation:model-document-removed',event=>window.events.push(event.detail));
    _persistModelProjectionCache=async()=>{};
    _cmdShow=()=>{};
    _invokeCapability=async(id,payload,options)=>{window.calls.push({id,payload,options});
      if(window.failure)throw Error(window.failure);
      if(window.pending)await window.pending;
      return {workspace_gid:'10',document_gid:'2',removed:true,workspace_row_version:8,cache_revision_hash:'sha256:test'};
    };
    _renderModelDocuments(_modelDocumentCollection.state.documents);
  `, context);
  return { dom, context };
}

test('only inserted model gets removal action; success changes association and preserves dirty workspace', async () => {
  const { dom, context } = setup();
  try {
    assert.equal(dom.window.document.querySelector('[data-document-gid="1"] .cs-model-document-remove'), null);
    assert.equal(dom.window.document.querySelector('[data-document-gid="2"] .cs-model-document-remove'), null);
    const menuFor=gid=>{
      dom.window.document.querySelector(`[data-document-gid="${gid}"] .cs-model-document-summary`).dispatchEvent(new dom.window.MouseEvent('contextmenu',{bubbles:true,cancelable:true}));
      return [...dom.window.document.querySelectorAll('[role="menuitem"]')].find(button=>button.textContent==='移除');
    };
    assert.equal(menuFor('1'),undefined);
    assert.ok(menuFor('2'));
    await vm.runInContext("_removeModelDocument('2')", context);
    const call = dom.window.calls[0];
    assert.equal(call.id, 'simulation.environment.model_document.remove');
    assert.equal(call.payload.expected_row_version, 7);
    assert.equal(call.options.confirmation, true);
    assert.equal(call.options.idempotency, true);
    assert.equal(vm.runInContext('_modelDocumentCollection.state.selectedDocumentGid', context), '1');
    assert.equal(dom.window._simulationEnvironmentWorkspace.store.state.workspace.dirty, true);
    assert.equal(dom.window._simulationEnvironmentWorkspace.store.state.workspace.row_version, 8);
    assert.equal(dom.window.events[0].document_gid, '2');
    assert.equal(dom.window.document.querySelector('[data-document-gid="2"]'), null);
  } finally { dom.window.close(); }
});

test('primary model is rejected before invoking a capability', async () => {
  const { dom, context } = setup();
  try {
    await assert.rejects(vm.runInContext("_removeModelDocument('1')", context), /primary_model_document_protected/);
    assert.equal(dom.window.calls.length, 0);
  } finally { dom.window.close(); }
});

for (const failure of ['version_conflict', 'permission_denied', 'provider_failed']) {
  test(`removal ${failure} keeps tree and selection intact`, async () => {
    const { dom, context } = setup();
    try {
      dom.window.failure = failure;
      await assert.rejects(vm.runInContext("_removeModelDocument('2')", context), new RegExp(failure));
      assert.ok(dom.window.document.querySelector('[data-document-gid="2"]'));
      assert.equal(vm.runInContext('_modelDocumentCollection.state.selectedDocumentGid', context), '2');
      assert.equal(dom.window.events.length, 0);
      assert.equal(dom.window._simulationEnvironmentWorkspace.store.state.workspace.row_version, 7);
    } finally { dom.window.close(); }
  });
}

test('pending removal does not optimistically change tree and suppresses duplicate clicks', async () => {
  const { dom, context } = setup();
  try {
    let finish;
    dom.window.pending = new Promise(resolve => { finish = resolve; });
    const pending = vm.runInContext("_removeModelDocument('2')", context);
    await vm.runInContext("_removeModelDocument('2')", context);
    assert.equal(dom.window.calls.length, 1);
    assert.ok(dom.window.document.querySelector('[data-document-gid="2"]'));
    finish(); await pending;
    assert.equal(dom.window.document.querySelector('[data-document-gid="2"]'), null);
  } finally { dom.window.close(); }
});

test('right-click removal reports failure without hiding or selecting the document', async () => {
  const { dom } = setup();
  try {
    dom.window.failure = 'version_conflict';
    let rowClicks = 0;
    const row = dom.window.document.querySelector('[data-document-gid="2"]');
    row.addEventListener('click', () => { rowClicks++; });
    row.querySelector('.cs-model-document-summary').dispatchEvent(new dom.window.MouseEvent('contextmenu',{bubbles:true,cancelable:true}));
    [...dom.window.document.querySelectorAll('[role="menuitem"]')].find(button=>button.textContent==='移除').click();
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(rowClicks, 0);
    assert.equal(dom.window.calls.length, 1);
    assert.equal(dom.window.document.querySelector('[role="menu"]'),null);
    assert.equal(row.isConnected, true);
  } finally { dom.window.close(); }
});

test('completed removal for previous environment cannot alter current environment', async () => {
  const { dom, context } = setup();
  try {
    let finish;
    dom.window.pending = new Promise(resolve => { finish = resolve; });
    const pending = vm.runInContext("_removeModelDocument('2')", context);
    vm.runInContext(`
      window._simulationEnvironmentWorkspace.store.state.workspace={workspace_gid:'20',row_version:9};
      _modelDocumentWorkspaceGid='20';
      _modelDocumentCollection.replace([{document_gid:'3',role:'primary',media_type:'model/vnd.jt'}]);
      _renderModelDocuments(_modelDocumentCollection.state.documents);
    `, context);
    finish(); await pending;
    assert.equal(dom.window._simulationEnvironmentWorkspace.store.state.workspace.row_version, 9);
    assert.equal(vm.runInContext('_modelDocumentCollection.state.selectedDocumentGid', context), '3');
    assert.equal(dom.window.events[0].workspace_gid, '10');
  } finally { dom.window.close(); }
});
