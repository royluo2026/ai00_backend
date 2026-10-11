const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const { JSDOM } = require('jsdom');

const source = fs.readFileSync(path.join(__dirname, 'cad_sim.js'), 'utf8');

function page(attach, setVisible = () => {}) {
  const dom = new JSDOM(`<!doctype html><body>
    <div id="nativeViewportSlot"></div><div id="vmPlaceholder"></div>
    <div id="visTreeEmpty"></div><span id="vmStatusLabel"></span>
    <span id="vmStatusDot"></span><span id="vmDocumentLabel"></span>
  </body>`, { runScripts: 'outside-only', url: 'http://127.0.0.1/' });
  dom.window.electronAPI = { visMockupNativeView: { attach, setVisible } };
  dom.window.document.getElementById('nativeViewportSlot').getBoundingClientRect = () =>
    ({ left: 0, top: 0, width: 640, height: 480 });
  const addEventListener = dom.window.document.addEventListener.bind(dom.window.document);
  dom.window.document.addEventListener = (type, ...args) => {
    if (type !== 'DOMContentLoaded') addEventListener(type, ...args);
  };
  vm.runInContext(source, dom.getInternalVMContext());
  return dom;
}

function bindEnvironment(dom, binding = { state: 'bound', workspace_gid: '10', document_session: 'session-10' }) {
  dom.window._simulationEnvironmentWorkspace = { store: { state: { workspace: { workspace_gid: '10' } } } };
  dom.window.__nativeBinding = binding;
  vm.runInContext('_invokeCapability = async () => window.__nativeBinding', dom.getInternalVMContext());
  vm.runInContext("_requestVisMockupCommand = async () => ({ steps: [{ status: 'succeeded', result: { process_id: 42, document_session: 'session-10' } }] })", dom.getInternalVMContext());
}
test('returning to an existing workspace refreshes TC status without a login-button click',()=>{
 const dom=page(()=>{});dom.window.__refreshes=0;
 vm.runInContext('_refreshTeamcenterSessionButton=async()=>{window.__refreshes++;}',dom.getInternalVMContext());
 dom.window.dispatchEvent(new dom.window.MessageEvent('message',{data:{type:'workspace:visibility',visible:false}}));
 assert.equal(dom.window.__refreshes,0);
 dom.window.dispatchEvent(new dom.window.MessageEvent('message',{data:{type:'workspace:visibility',visible:true}}));
 assert.equal(dom.window.__refreshes,1);dom.window.close();
});

test('shared dialog occludes native viewport and closing one overlay does not reveal through another',()=>{
 const visible=[];const dom=page(()=>{throw Error('must not attach');},v=>visible.push(v));bindEnvironment(dom);
 dom.window._completeLocalViewerPresentation();
 const overlay=dom.window.document.createElement('dialog');overlay.className='ai00-dialog';overlay.open=true;dom.window.document.body.append(overlay);
 vm.runInContext('_syncNativeViewportOcclusion()',dom.getInternalVMContext());assert.equal(visible.at(-1),false);
 const form=dom.window.document.createElement('div');form.className='cs-modal-overlay';dom.window.document.body.append(form);overlay.remove();
 vm.runInContext('_syncNativeViewportOcclusion()',dom.getInternalVMContext());assert.equal(visible.at(-1),false);
 dom.window._liveDocumentContextUnavailable=true;form.remove();vm.runInContext('_syncNativeViewportOcclusion()',dom.getInternalVMContext());assert.equal(visible.at(-1),false);dom.window.close();
});

test('unbound viewport stages dimensions without revealing an unverified document',()=>{
 const visibility=[],bounds=[];
 const dom=page(()=>{throw Error('must_not_attach');},value=>visibility.push(value));
 bindEnvironment(dom);
 dom.window._liveDocumentContextUnavailable=true;
 dom.window.electronAPI.visMockupNativeView.updateBounds=value=>bounds.push(value);
 dom.window._notifyNativeViewportBounds();
 assert.equal(bounds.length,1);
 assert.equal(bounds[0].width,640);
 assert.equal(bounds[0].height,480);
 assert.equal(visibility.at(-1),false);
 dom.window.close();
});

test('local readiness completes both the native presentation and legacy connected state',()=>{
 const dom=page(()=>{throw Error('must_not_attach');});bindEnvironment(dom);
 dom.window._liveDocumentContextUnavailable=true;
 dom.window._completeLocalViewerPresentation();
 assert.equal(vm.runInContext('_vmConnected',dom.getInternalVMContext()),true);
 assert.equal(dom.window._liveDocumentContextUnavailable,false);
 assert.equal(dom.window.document.getElementById('vmPlaceholder').classList.contains('hidden'),true);
 dom.window.close();
});

test('restored current document hides the empty viewport placeholder',()=>{
 const dom=page(()=>{});bindEnvironment(dom);
 dom.window._completeLocalViewerPresentation();
 dom.window._setVmStatus('connected','当前文档已显示');
 assert.equal(dom.window.document.getElementById('vmPlaceholder').classList.contains('hidden'),true);
 dom.window.close();
});

test('concurrent startup and environment attachment share one native operation', async () => {
  let calls = 0;
  const dom = page(async () => { calls++; return {state:'attached',pid:42}; });
  bindEnvironment(dom);
  await Promise.all([
    dom.window._attachNativeViewport(),
    dom.window._attachNativeViewport(),
  ]);
  assert.equal(calls, 1);
  dom.window.close();
});

test('freshly opened session embeds before historical association is updated', async () => {
  let calls=0;
  const dom=page(async()=>{calls++;return {state:'attached',pid:42};});
  bindEnvironment(dom,{state:'bound',workspace_gid:'10',document_session:'old-session'});
  vm.runInContext("_invokeCapability=async()=>{throw Error('must_not_read_old_binding');}",dom.getInternalVMContext());
  const result=await dom.window._attachNativeViewport({openedDocumentSession:'session-10'});
  assert.equal(result?.state,'attached');
  assert.equal(calls,1);
  dom.window.close();
});

test('fresh open identity cannot attach a different document activated meanwhile', async () => {
  let calls=0;
  const dom=page(async()=>{calls++;return {state:'attached',pid:42};});
  bindEnvironment(dom);
  const result=await dom.window._attachNativeViewport({openedDocumentSession:'different-session'});
  assert.equal(result?.error,'opened_document_identity_changed');
  assert.equal(calls,0);
  dom.window.close();
});

test('verified already attached process is reused without detach and reattach', async () => {
  let calls = 0;
  const dom = page(async () => { calls++; return {state:'attached',pid:42}; });
  bindEnvironment(dom);
  dom.window.electronAPI.visMockupNativeView.status = async () => ({state:'attached',pid:42});
  await dom.window._attachNativeViewport();
  assert.equal(calls, 0);
  assert.match(dom.window.document.getElementById('vmStatusLabel').textContent, /已内嵌/);
  dom.window.close();
});

test('placeholder follows environment, binding, failure and actual embedding rather than generic connected text',()=>{
  const dom=page(async()=>({state:'attached'})),ctx=dom.getInternalVMContext();
  const ph=dom.window.document.getElementById('vmPlaceholder');
  vm.runInContext("_onConnected({document_ready:true})",ctx);
  assert.match(ph.textContent,/请选择仿真环境/);
  assert.doesNotMatch(ph.textContent,/正在加载|高亮/);
  bindEnvironment(dom);
  for(const [state,message,expected] of [
    ['unavailable','当前仿真环境未绑定 VisMockup 文档',/未绑定/],
    ['unavailable','缓存已保留 · 请点击文档名选择“恢复到当前环境”',/恢复到当前环境/],
    ['error','VisMockup 内嵌失败：vismockup_3d_view_unavailable',/vismockup_3d_view_unavailable/],
    ['connecting','等待 VisMockup 三维视图…',/等待 VisMockup/],
  ]) {
    dom.window.__message=message;dom.window.__state=state;
    vm.runInContext('_setVmStatus(window.__state,window.__message)',ctx);
    assert.match(ph.textContent,expected);
    assert.doesNotMatch(ph.textContent,/点击 BOP|已连接/);
    assert.equal(ph.classList.contains('hidden'),false);
  }
  vm.runInContext("_applyNativeViewStatus({state:'attached'})",ctx);
  assert.equal(ph.classList.contains('hidden'),true);
  dom.window._liveDocumentContextUnavailable=true;
  vm.runInContext('_notifyNativeViewportBounds()',ctx);
  assert.equal(ph.classList.contains('hidden'),false);
  assert.match(ph.textContent,/核对/);
  dom.window.close();
});

test('Teamcenter document identity keeps the project prefix while local paths use their basename', () => {
  const dom = page(async () => ({ state: 'attached' }));
  vm.runInContext("_setVmDocumentLabel({ document_name: 'W10-ENG00001/00;1-工程分支(Top Engineering) (视图)' })", dom.getInternalVMContext());
  assert.equal(dom.window.document.getElementById('vmDocumentLabel').textContent,
    'W10-ENG00001/00;1-工程分支(Top Engineering) (视图)');
  vm.runInContext("_setVmDocumentLabel({ document_path: 'D:\\\\Temp\\\\vis\\\\model.plmxml' })", dom.getInternalVMContext());
  assert.equal(dom.window.document.getElementById('vmDocumentLabel').textContent, 'model.plmxml');
  dom.window.close();
});

test('workspace tab visibility hides and restores the native VisMockup child window', () => {
  const values = [];
  const dom = page(async () => ({ state: 'attached' }), visible => values.push(visible));
  dom.window.dispatchEvent(new dom.window.MessageEvent('message', {
    data: { type: 'workspace:visibility', visible: false }, source: dom.window,
  }));
  dom.window.dispatchEvent(new dom.window.MessageEvent('message', {
    data: { type: 'workspace:visibility', visible: true }, source: dom.window,
  }));
  assert.deepEqual(values, [false, true]);
  dom.window.close();
});

test('connected VisMockup without an active document waits instead of attaching an absent view', async () => {
  let calls = 0;
  const dom = page(async () => { calls++; return { state: 'error', error: 'vismockup_3d_view_unavailable' }; });
  vm.runInContext('_onConnected({ ready: true, document_ready: false, pid: 42 })', dom.getInternalVMContext());
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(calls, 0);
  assert.match(dom.window.document.getElementById('vmStatusLabel').textContent, /暂无活动文档/);
  assert.match(dom.window.document.getElementById('vmPlaceholder').textContent, /打开模型后/);
  assert.doesNotMatch(dom.window.document.getElementById('vmPlaceholder').textContent, /独立窗口/);
  dom.window.close();
});

test('a model view created shortly after open is attached without another user action', async () => {
  let calls = 0;
  const dom = page(async () => ++calls === 1
    ? { state: 'error', error: 'vismockup_3d_view_unavailable' }
    : { state: 'attached', pid: 42, documentName: 'model.plmxml' });
  dom.window.setTimeout = callback => { setImmediate(callback); return 1; };
  bindEnvironment(dom);
  vm.runInContext('_vmConnected = true', dom.getInternalVMContext());
  await vm.runInContext('_attachNativeViewport({ pid: 42 })', dom.getInternalVMContext());
  assert.equal(calls, 2);
  assert.match(dom.window.document.getElementById('vmStatusLabel').textContent, /已内嵌/);
  dom.window.close();
});

test('readiness without a PID resolves the document identity before native attachment', async () => {
  const requests = [];
  const dom = page(async request => { requests.push(request); return { state: 'attached', pid: 42 }; });
  bindEnvironment(dom);
  await vm.runInContext('_attachNativeViewport({ ready: true })', dom.getInternalVMContext());
  assert.equal(requests.length, 1);
  assert.equal(requests[0].pid, 42);
  dom.window.close();
});

test('native attachment waits for a selected simulation environment', async () => {
  let calls = 0;
  const dom = page(async () => { calls++; return { state: 'attached' }; });
  await vm.runInContext('_attachNativeViewport({ pid: 42 })', dom.getInternalVMContext());
  assert.equal(calls, 0);
  assert.equal(dom.window.document.getElementById('vmStatusLabel').textContent, '请先选择仿真环境');
  dom.window.close();
});

test('explicit document selection initializes a hidden native session without an environment', async () => {
  let calls=0;
  const visibility=[];
  const dom=page(async()=>{calls++;return {state:'attached',pid:42};},value=>visibility.push(value));
  const overlay=dom.window.document.createElement('div');overlay.className='cs-modal-overlay';dom.window.document.body.append(overlay);
  vm.runInContext("_requestVisMockupCommand = async () => ({steps:[{status:'succeeded',result:{process_id:42,document_session:'session'}}]})",dom.getInternalVMContext());
  await vm.runInContext('_attachNativeViewport({forDocumentSelection:true})',dom.getInternalVMContext());
  assert.equal(calls,1);
  assert.equal(visibility.at(-1),false);
  dom.window.close();
});

test('cached model projection is not accepted as a selected environment', async () => {
  let calls = 0;
  const dom = page(async () => { calls++; return { state: 'attached', pid: 42 }; });
  dom.window.__nativeBinding = { state: 'bound', workspace_gid: '10', document_session: 'session-10' };
  vm.runInContext("_modelDocumentWorkspaceGid = '10'; _invokeCapability = async () => window.__nativeBinding",
    dom.getInternalVMContext());
  await vm.runInContext('_attachNativeViewport({ pid: 42 })', dom.getInternalVMContext());
  assert.equal(calls, 0);
  dom.window.close();
});

test('native attachment waits when the selected environment has no VisMockup document binding', async () => {
  let calls = 0;
  const dom = page(async () => { calls++; return { state: 'attached' }; });
  bindEnvironment(dom, { state: 'unbound', workspace_gid: '10' });
  await vm.runInContext('_attachNativeViewport({ pid: 42 })', dom.getInternalVMContext());
  assert.equal(calls, 0);
  assert.equal(dom.window.document.getElementById('vmStatusLabel').textContent,
    '当前仿真环境未绑定 VisMockup 文档');
  dom.window.close();
});

test('a different active document cannot be embedded just because an environment has a binding', async () => {
  let calls = 0;
  const dom = page(async () => { calls++; return {state:'attached'}; });
  bindEnvironment(dom);
  vm.runInContext("_requestVisMockupCommand = async () => ({steps:[{status:'succeeded',result:{process_id:42,document_session:'another-document'}}]})",dom.getInternalVMContext());
  const result = await vm.runInContext('_attachNativeViewport({pid:42})',dom.getInternalVMContext());
  assert.equal(calls,0);
  assert.equal(result.error,'document_environment_binding_mismatch');
  dom.window.close();
});

test('native documentChanged has already reattached and does not attach a second time', async () => {
  let calls = 0, changes = 0;
  const dom = page(async () => { calls++; return { state: 'attached' }; });
  dom.window.addEventListener('ai00:live-document-changed', () => changes++);
  vm.runInContext("_applyNativeViewStatus({ state: 'documentChanged', pid: 42, documentName: 'B' })", dom.getInternalVMContext());
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(calls, 0);
  assert.equal(changes, 1);
  assert.equal(dom.window.document.getElementById('vmDocumentLabel').textContent, 'B');
  assert.equal(dom.window.document.getElementById('vmStatusLabel').textContent, '已内嵌');
  dom.window.close();
});
