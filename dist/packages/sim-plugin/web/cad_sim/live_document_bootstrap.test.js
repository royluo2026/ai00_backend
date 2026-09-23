const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

test('page cache-busts the dedicated-session bootstrap', () => {
  const html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');
  for (const name of ['cad_sim','viewer_interaction','live_document_adoption','live_document_bootstrap']) {
    const match=html.match(new RegExp('src="('+name+'\\.js\\?(?:rev|v)=20260922-local-interaction-1)"'));
    assert.ok(match,`${name} must load the current interaction implementation`);
    assert.ok(fs.statSync(path.join(__dirname,match[1].split('?')[0])).size>0);
  }
  assert.doesNotMatch(html, /live_document_bootstrap\.js\?v=20260916-reconnect-snapshot/);
});

test('page bootstrap injects adapters without auto-connecting on environment or native changes', async () => {
  const dom = new JSDOM('<button id="vmDocumentLabel">Document A</button>', { runScripts: 'outside-only' });
  const w = dom.window, calls = [];
  let listener, options, switcherOptions;
  const store = { state: { workspace: null }, subscribe(fn) { listener = fn; } };
  const selection = { isOwnWorkspaceChange: () => false, cancel() {},
    selectEnvironment: async gid => calls.push(gid), observeCurrentDocument: async () => calls.push('native') };
  w._simulationEnvironmentWorkspace = { store };
  w._eAPI = () => ({ visMockupNativeView: {} });
  w._requireConnectorRuntime = async () => calls.push('ready');
  w._requestVisMockupCommand = async (id, payload, opts) => { calls.push([id, opts.confirmation]); return 'outcome'; };
  w._invokeCapability = () => {};
  w._notifyNativeViewportBounds = () => {};
  w._attachNativeViewport = async () => { calls.push('attach'); return {state:'attached'}; };
  let invalidations=0;
  w.AI00LiveDocumentAdoption = { createAdapter(o) { options = o; return { invalidateControlMappings() { invalidations++; }, readCurrentDocument() { calls.push('readDocument'); } }; }, mount(o) { assert.ok(o.adapter); } };
  w.AI00LiveDocumentSwitcher = { createAdapter(o) { switcherOptions = o; return selection; }, mount(o) { assert.equal(o.adapter, selection); } };
  w.eval(fs.readFileSync(path.join(__dirname, 'live_document_bootstrap.js'), 'utf8'));
  w.AI00LiveDocumentBootstrap();
  assert.equal(await options.readIdentity(), 'outcome');
  listener({ workspace: { workspace_gid: '12' } });
  assert.equal(w._liveDocumentContextUnavailable, true, 'old viewport hides before asynchronous environment verification');
  listener({ workspace: { workspace_gid: '12' } });
  w.dispatchEvent(new w.Event('ai00:live-document-changed'));
  await Promise.resolve();
  switcherOptions.onContext(true);
  assert.equal(invalidations,3,'initial context, environment switch and document switch invalidate mappings');
  await switcherOptions.readDocument();
  await Promise.resolve();
  assert.deepEqual(calls, ['ready', ['simulation.vismockup.document.identity.read.request', false], 'attach', 'readDocument']);
  assert.equal(w._liveDocumentSelection, selection);
  dom.window.close();
});

for (const bound of [true, false]) test(`environment selection waits for an explicit model open (${bound ? 'historically bound' : 'unbound'})`, async () => {
  const dom = new JSDOM('<div id="nativeViewportSlot"></div><span id="vmStatusLabel"></span><button id="vmDocumentLabel">Assembly</button>', { runScripts: 'outside-only' });
  const w = dom.window;
  const session = 'sha256:' + 'a'.repeat(64);
  const workspace = {workspace_gid:'10'};
  let attached = false, attachCount = 0;
  const native = {
    status: async () => ({state:attached?'attached':'detached',pid:attached?42:null}),
    listDocuments: async () => {
      assert.equal(attached, true, 'listDocuments must not run before initial attachment');
      return [{key:'vmwin:1',current:true,name:'Assembly'}];
    },
    attach: async () => {attached = true; attachCount++; return {state:'attached',pid:42};},
    setVisible() {}, updateBounds() {},
  };
  w.electronAPI = {visMockupNativeView:native};
  w.document.getElementById('nativeViewportSlot').getBoundingClientRect = () => ({left:0,top:0,width:640,height:480});
  const listen = w.document.addEventListener.bind(w.document);
  w.document.addEventListener = (type,...args) => {if(type!=='DOMContentLoaded') listen(type,...args);};
  w._simulationEnvironmentWorkspace = {store:{state:{workspace},subscribe(fn){fn(this.state);}}};
  for (const file of ['cad_sim.js','live_document_adoption.js','live_document_switcher.js','live_document_bootstrap.js'])
    require('node:vm').runInContext(fs.readFileSync(path.join(__dirname,file),'utf8'),dom.getInternalVMContext());
  w.eval(`_requireConnectorRuntime = async () => {}; _invokeCapability = async () => (${JSON.stringify({workspace_gid:'10',state:bound?'bound':'unbound',document_session:bound?session:null})});
    _requestVisMockupCommand = async () => (${JSON.stringify({plan_id:'identity-operation',steps:[{status:'succeeded',result:{process_id:42,document_session:session}}]})});`);
  w.AI00LiveDocumentBootstrap();
  await new Promise(resolve=>setTimeout(resolve,50));
  assert.equal(attachCount,0,w.document.getElementById('vmStatusLabel').textContent);
  assert.equal(w.document.getElementById('vmStatusLabel').textContent,'请从模型文件展开到目标节点后打开');
  dom.window.close();
});

test('environment selection never probes an old VisMockup document identity', async () => {
  const dom = new JSDOM('<span id="vmDocumentLabel">Assembly</span><span id="vmStatusLabel"></span>', { runScripts: 'outside-only' });
  const w = dom.window;
  let listener;
  const store = { state: { workspace: null }, subscribe(fn) { listener = fn; } };
  w._simulationEnvironmentWorkspace = { store };
  w._eAPI = () => ({ visMockupNativeView: {} });
  w._invokeCapability = () => {};
  w._notifyNativeViewportBounds = () => {};
  w._setVmStatus = (_state, message) => { w.document.getElementById('vmStatusLabel').textContent = message; };
  w.AI00LiveDocumentAdoption = { createAdapter: () => ({invalidateControlMappings() {}}), mount: () => {} };
  let probes = 0;
  w.AI00LiveDocumentSwitcher = {
    createAdapter: () => ({
      isOwnWorkspaceChange: () => false,
      cancel() {},
      selectEnvironment: async () => { probes++; throw Error('vismockup_process_identity_unavailable'); },
    }),
    mount: () => {},
  };
  w.eval(fs.readFileSync(path.join(__dirname, 'live_document_bootstrap.js'), 'utf8'));
  w.AI00LiveDocumentBootstrap();
  listener({ workspace: { workspace_gid: '12' } });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(probes, 0);
  assert.equal(w.document.getElementById('vmStatusLabel').textContent, '请从模型文件展开到目标节点后打开');
  dom.window.close();
});
