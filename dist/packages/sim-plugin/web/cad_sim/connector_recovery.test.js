const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { JSDOM } = require('jsdom');
const { createBusinessFacade } = require('../../../../web/core/business_facade');
const { CapabilityClient, registerCapabilityIPC } = require('../../../core/electron/capability_client');
const { installedOfficialCapabilities } = require('../../../core/electron/official_capability_manifests');

test('recovery entry script is revalidated by the development server after a source fix', async () => {
  const { createServer } = require('vite');
  const server = await createServer({
    configFile: false, root: path.resolve(__dirname, '../../../..'), logLevel: 'silent',
    server: { host: '127.0.0.1', port: 0 }, optimizeDeps: { noDiscovery: true, include: [] },
  });
  try {
    await server.listen();
    const base = `http://127.0.0.1:${server.httpServer.address().port}`;
    const html = await (await fetch(`${base}/packages/sim-plugin/web/cad_sim/index.html`)).text();
    const dom = new JSDOM(html);
    const script = Array.from(dom.window.document.scripts).find(node => node.src.includes('connector_recovery.js'));
    const url = new URL(script.getAttribute('src'), `${base}/packages/sim-plugin/web/cad_sim/index.html`);
    dom.window.close();
    const response = await fetch(url);
    assert.equal(response.status, 200);
    assert.match(response.headers.get('cache-control'), /no-cache/);
  } finally { await server.close(); }
});

const OUTCOME_HASH=`sha256:${'a'.repeat(64)}`,PLAN_HASH=`sha256:${'b'.repeat(64)}`,FINGERPRINT=`sha256:${'c'.repeat(64)}`;
const item = {
  plan_id: 'plan-1', device_id: 'device-1', runtime_generation: 7,
  outcome_hash: OUTCOME_HASH, plan_hash:PLAN_HASH, recovery_fingerprint:FINGERPRINT, operation_id: 'operation-1', status: 'manual_review_required',
  eligible: true, error_code: 'connector_outcome_unknown', allowed_decisions: ['executed','not_executed','abandoned'], ineligible_reason: null,
};

function page({ search = { items: [item] }, resolve, confirm = () => true, refresh, invoke } = {}) {
  const dom = new JSDOM(`
    <div id="nativeViewportSlot"></div>
    <div id="viewerEmbedStatus"><span id="vmStatusLabel">本地连接器未就绪</span><button id="btnConnectorRecovery">处理未完成操作</button></div>
    <div id="connectorRecoveryOverlay" class="cs-modal-overlay hidden">
      <section role="dialog"><div id="connectorRecoveryStatus"></div><div id="connectorRecoveryItems"></div>
      <button id="connectorRecoverySelectAll">全选可处理项</button><button id="connectorRecoveryDeselectAll">取消全选</button>
      <div id="connectorRecoveryPagination"><button id="connectorRecoveryPrevPage">上一页</button><span id="connectorRecoveryPageInfo"></span><button id="connectorRecoveryNextPage">下一页</button></div>
      <div id="connectorRecoveryProgress"></div><div id="connectorRecoveryResults"></div>
      <textarea id="connectorRecoveryReason"></textarea>
      <label><input type="radio" name="connectorRecoveryDecision" value="not_executed">未执行</label>
      <label><input type="radio" name="connectorRecoveryDecision" value="executed">已执行</label>
      <label><input type="radio" name="connectorRecoveryDecision" value="abandoned">放弃并归档该未完成操作</label>
      <button id="connectorRecoveryChooseDocument" class="hidden">打开文档选择器</button>
      <button id="connectorRecoveryCancel">稍后处理</button><button id="connectorRecoveryConfirm">确认处理</button></section>
    </div><button id="btnSwitchVmDocument">切换</button><button id="btnLaunchVm">启动</button>`, { runScripts: 'outside-only', url: 'https://ai00.test/' });
  const calls = [], refreshes = [], chooser = [];
  dom.window.confirm = confirm;
  dom.window.AI00Business = { invoke: async (id, envelope, confirmation) => {
    calls.push({ id, envelope, confirmation });
    if (confirmation && !await confirmation()) throw Error('confirmation_cancelled');
    if (id.includes('.search')) {
      const value = typeof search === 'function' ? search(envelope) : search;
      const result = await value;
      return { page:1, page_size:5, total:result.items.length, page_count:result.items.length?1:0, ...result };
    }
    return resolve ? resolve(envelope) : { plan_id: 'plan-1', device_id: 'device-1', decision: envelope.payload.decision, audit_ref: 'audit-1', retry_started: false };
  } };
  dom.window._tryAutoConnect = async () => { refreshes.push('refresh'); return refresh?.(); };
  dom.window.document.getElementById('btnSwitchVmDocument').onclick = () => chooser.push('open');
  dom.window.eval(fs.readFileSync(path.join(__dirname, 'connector_recovery.js'), 'utf8'));
  const mounted = dom.window.AI00ConnectorRecovery.mount({ invoke });
  return { dom, document: dom.window.document, mounted, calls, refreshes, chooser };
}

async function flush() { await new Promise(resolve => setImmediate(resolve)); }

test('entry remains usable while Connector is offline and loads safe operation identity', async () => {
  const { dom, document, calls } = page();
  document.getElementById('btnConnectorRecovery').click(); await flush();
  assert.equal(document.getElementById('connectorRecoveryOverlay').classList.contains('hidden'), false);
  assert.equal(calls[0].id, 'simulation.connector.recovery.search');
  assert.deepEqual(JSON.parse(JSON.stringify(calls[0].envelope)), { version: 1, payload: {page:1,page_size:5} });
  assert.match(document.getElementById('connectorRecoveryItems').textContent, /operation-1/);
  assert.match(document.getElementById('connectorRecoveryItems').textContent, /connector_outcome_unknown/);
  assert.equal(document.body.textContent.includes(OUTCOME_HASH)||document.body.textContent.includes(PLAN_HASH)||document.body.textContent.includes(FINGERPRINT),false);
  dom.window.close();
});

test('reports loading, empty, and search failure without fabricated operations', async () => {
  let finish; const loading = page({ search: () => new Promise(resolve => { finish = resolve; }) });
  loading.document.getElementById('btnConnectorRecovery').click();
  assert.match(loading.document.getElementById('connectorRecoveryStatus').textContent, /正在读取/);
  assert.equal(loading.document.getElementById('connectorRecoveryConfirm').disabled, true);
  finish({ items: [] }); await flush();
  assert.match(loading.document.getElementById('connectorRecoveryStatus').textContent, /没有待人工核对项/);
  assert.equal(loading.document.getElementById('connectorRecoveryConfirm').disabled, true);
  assert.equal(loading.document.querySelectorAll('[data-recovery-plan]').length, 0); loading.dom.window.close();
  const failed = page({ search: () => { throw Error('gateway_down'); } });
  failed.document.getElementById('btnConnectorRecovery').click(); await flush();
  assert.match(failed.document.getElementById('connectorRecoveryStatus').textContent, /gateway_down/);
  assert.equal(failed.document.getElementById('connectorRecoveryConfirm').disabled, true);
  failed.document.getElementById('connectorRecoveryConfirm').click();
  assert.match(failed.document.getElementById('connectorRecoveryStatus').textContent, /gateway_down/); failed.dom.window.close();
});

test('confirm enables only for a selected eligible item, decision, and valid reason', async () => {
  const p = page(); const button = p.document.getElementById('connectorRecoveryConfirm');
  p.document.getElementById('btnConnectorRecovery').click(); await flush();
  assert.equal(button.disabled, true);
  p.document.querySelector('[data-recovery-plan]').click(); p.document.querySelector('[value="not_executed"]').click();
  p.document.getElementById('connectorRecoveryReason').value = '已核对';
  p.document.getElementById('connectorRecoveryReason').dispatchEvent(new p.dom.window.Event('input'));
  assert.equal(button.disabled, false);
  p.document.getElementById('connectorRecoveryReason').value = ' '.repeat(2);
  p.document.getElementById('connectorRecoveryReason').dispatchEvent(new p.dom.window.Event('input'));
  assert.equal(button.disabled, true); p.dom.window.close();
});

test('starting a reload clears stale selection before the request completes', async () => {
  let searches = 0, finish;
  const p = page({ search: () => searches++ ? new Promise(resolve => { finish = resolve; }) : { items:[item] } });
  p.document.getElementById('btnConnectorRecovery').click(); await flush();
  p.document.querySelector('[data-recovery-plan]').click(); p.document.querySelector('[value="not_executed"]').click();
  const reason = p.document.getElementById('connectorRecoveryReason'); reason.value = '已核对'; reason.dispatchEvent(new p.dom.window.Event('input'));
  assert.equal(p.document.getElementById('connectorRecoveryConfirm').disabled, false);
  p.mounted.open();
  assert.equal(p.document.getElementById('connectorRecoveryConfirm').disabled, true);
  finish({items:[]}); await flush(); p.dom.window.close();
});

test('cancel and human confirmation refusal cause no mutation', async () => {
  const p = page({ confirm: () => false });
  p.document.getElementById('btnConnectorRecovery').click(); await flush();
  p.document.querySelector('[data-recovery-plan]').click();
  p.document.querySelector('[value="not_executed"]').click();
  p.document.getElementById('connectorRecoveryReason').value = '现场核对未执行';
  p.document.getElementById('connectorRecoveryReason').dispatchEvent(new p.dom.window.Event('input'));
  p.document.getElementById('connectorRecoveryConfirm').click(); await flush();
  assert.equal(p.calls.filter(call => call.id === 'simulation.connector.recovery.resolve').length, 0);
  p.document.getElementById('connectorRecoveryCancel').click();
  assert.equal(p.calls.filter(call => call.id === 'simulation.connector.recovery.resolve').length, 0);
  p.dom.window.close();
});

test('resolve sends exact payload, unique idempotency key, and blocks double submit', async () => {
  let finish; const p = page({ resolve: () => new Promise(resolve => { finish = resolve; }) });
  p.document.getElementById('btnConnectorRecovery').click(); await flush();
  p.document.querySelector('[data-recovery-plan]').click();
  p.document.querySelector('[value="not_executed"]').click();
  p.document.getElementById('connectorRecoveryReason').value = ' 现场核对未执行 ';
  p.document.getElementById('connectorRecoveryReason').dispatchEvent(new p.dom.window.Event('input'));
  p.document.getElementById('connectorRecoveryConfirm').click();
  p.document.getElementById('connectorRecoveryConfirm').click(); await flush();
  const writes = p.calls.filter(call => call.id === 'simulation.connector.recovery.resolve');
  assert.equal(writes.length, 1);
  assert.deepEqual(JSON.parse(JSON.stringify(writes[0].envelope.payload)), { plan_id:'plan-1', device_id:'device-1', expected_generation:7, expected_outcome_hash:OUTCOME_HASH, expected_plan_hash:PLAN_HASH, expected_recovery_fingerprint:FINGERPRINT, decision:'not_executed', reason:'现场核对未执行' });
  assert.match(writes[0].envelope.idempotency_key, /^simulation\.connector\.recovery\.resolve:/);
  finish({ plan_id:'plan-1', device_id:'device-1', decision:'not_executed', audit_ref:'audit-1', retry_started:false }); await flush();
  assert.deepEqual(p.refreshes, ['refresh']);
  assert.match(p.document.getElementById('connectorRecoveryResults').textContent, /audit-1/);
  p.dom.window.close();
});

test('ineligible operation is disabled and cannot be resolved', async () => {
  const p = page({ search: { items: [{ ...item, eligible:false, error_code:'unsupported_generation' }] } });
  p.document.getElementById('btnConnectorRecovery').click(); await flush();
  assert.equal(p.document.querySelector('[data-recovery-plan]').disabled, true);
  assert.match(p.document.getElementById('connectorRecoveryItems').textContent, /unsupported_generation/);
  p.dom.window.close();
});

test('executed decision keeps results visible and offers a separate chooser without launching', async () => {
  const p = page(); p.dom.window.document.getElementById('btnLaunchVm').onclick = () => assert.fail('must not launch');
  p.document.getElementById('btnConnectorRecovery').click(); await flush();
  p.document.querySelector('[data-recovery-plan]').click(); p.document.querySelector('[value="executed"]').click();
  p.document.getElementById('connectorRecoveryReason').value = '现场确认已执行';
  p.document.getElementById('connectorRecoveryReason').dispatchEvent(new p.dom.window.Event('input'));
  p.document.getElementById('connectorRecoveryConfirm').click(); await flush();
  assert.deepEqual(p.refreshes, ['refresh']); assert.deepEqual(p.chooser, []);
  assert.equal(p.document.getElementById('connectorRecoveryOverlay').classList.contains('hidden'), false);
  assert.match(p.document.getElementById('connectorRecoveryResults').textContent,/audit-1/);
  const chooser=p.document.getElementById('connectorRecoveryChooseDocument');assert.equal(chooser.classList.contains('hidden'),false);chooser.click();assert.deepEqual(p.chooser,['open']);
  p.dom.window.close();
});

test('executed decision reports other remaining blockers before opening the chooser', async () => {
  let searches = 0; const notices = [];
  const p = page({ search: () => ({ items: searches++ ? [{...item, plan_id:'plan-2', operation_id:'operation-2'}] : [item] }) });
  p.dom.window._cmdShow = message => notices.push(message);
  p.document.getElementById('btnConnectorRecovery').click(); await flush();
  p.document.querySelector('[data-recovery-plan]').click(); p.document.querySelector('[value="executed"]').click();
  const reason = p.document.getElementById('connectorRecoveryReason'); reason.value='现场确认已执行'; reason.dispatchEvent(new p.dom.window.Event('input'));
  p.document.getElementById('connectorRecoveryConfirm').click(); await flush();
  assert.match(notices.at(-1), /成功 1 项.*仍有 1 项待人工核对/);
  assert.deepEqual(p.chooser, []);
  assert.equal(p.document.getElementById('connectorRecoveryOverlay').classList.contains('hidden'),false);
  p.dom.window.close();
});

test('successful not-executed resolution keeps remaining blockers visible', async () => {
  let searches = 0;
  const p = page({ search: () => ({ items: searches++ ? [{...item,plan_id:'plan-2',operation_id:'operation-2'}] : [item] }) });
  p.document.getElementById('btnConnectorRecovery').click(); await flush();
  p.document.querySelector('[data-recovery-plan]').click(); p.document.querySelector('[value="not_executed"]').click();
  p.document.getElementById('connectorRecoveryReason').value = '未发生';
  p.document.getElementById('connectorRecoveryReason').dispatchEvent(new p.dom.window.Event('input'));
  p.document.getElementById('connectorRecoveryConfirm').click(); await flush();
  assert.match(p.document.getElementById('connectorRecoveryStatus').textContent, /仍有 1 项/);
  assert.match(p.document.getElementById('connectorRecoveryItems').textContent, /operation-2/);
  p.dom.window.close();
});

test('committed decision stays successful when connection or blocker refresh fails', async () => {
  let searches = 0;
  const p = page({ search: () => { if (searches++) throw Error('refresh_failed'); return {items:[item]}; }, refresh: () => { throw Error('connector_offline'); } });
  p.document.getElementById('btnConnectorRecovery').click(); await flush();
  p.document.querySelector('[data-recovery-plan]').click(); p.document.querySelector('[value="not_executed"]').click();
  const reason = p.document.getElementById('connectorRecoveryReason'); reason.value='未发生'; reason.dispatchEvent(new p.dom.window.Event('input'));
  p.document.getElementById('connectorRecoveryConfirm').click(); await flush();
  const text = p.document.getElementById('connectorRecoveryStatus').textContent;
  assert.match(text, /成功 1 项/); assert.match(text, /刷新失败/);
  assert.match(p.document.getElementById('connectorRecoveryResults').textContent, /audit-1/);
  assert.doesNotMatch(text, /处理失败|没有剩余阻塞/); p.dom.window.close();
});

test('closing during submit prevents future sends, late chooser, or status mutation', async () => {
  let finish; const p = page({ search:{items:[item,{...item,plan_id:'plan-2',operation_id:'operation-2'}]}, resolve: () => new Promise(resolve => { finish = resolve; }) });
  p.document.getElementById('btnConnectorRecovery').click(); await flush();
  p.document.querySelector('[value="executed"]').click(); p.document.getElementById('connectorRecoverySelectAll').click();
  const reason=p.document.getElementById('connectorRecoveryReason'); reason.value='已执行'; reason.dispatchEvent(new p.dom.window.Event('input'));
  assert.equal(p.document.getElementById('connectorRecoveryConfirm').disabled, false);
  p.document.getElementById('connectorRecoveryConfirm').click(); await flush(); p.document.getElementById('connectorRecoveryCancel').click();
  finish({audit_ref:'audit-late'}); await flush();
  assert.equal(p.calls.filter(call=>call.id==='simulation.connector.recovery.resolve').length,1);
  assert.doesNotMatch(p.document.getElementById('connectorRecoveryResults').textContent,/audit-late/);
  assert.deepEqual(p.chooser, []); assert.equal(p.document.getElementById('connectorRecoveryOverlay').classList.contains('hidden'), true);
  p.dom.window.close();
});

test('simulation plugin declares both recovery capability consumers', () => {
  const manifest = JSON.parse(fs.readFileSync(path.join(__dirname, '..', '..', 'manifest.json'), 'utf8'));
  const bindings = manifest.capability_bindings.map(binding => `${binding.id}@${binding.major}`);
  assert.ok(bindings.includes('simulation.connector.recovery.search@1'));
  assert.ok(bindings.includes('simulation.connector.recovery.resolve@1'));
});

test('real page keeps recovery confirmation disabled before scripts finish mounting', () => {
  const html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');
  const dom = new JSDOM(html);
  assert.equal(dom.window.document.getElementById('connectorRecoveryConfirm').disabled, true);
  dom.window.close();
});

test('real business facade and desktop CapabilityClient accept the recovery search envelope', async () => {
  const requests = [];
  const client = new CapabilityClient({
    origin: 'https://gateway.test',
    auth: { withAccessToken: fn => fn('fixture-token'), refresh: async () => false },
    fetchImpl: async (_url, options) => {
      requests.push(JSON.parse(options.body));
      return Response.json({ success:true, data:{ ok:true, status:'completed', capability_id:'simulation.connector.recovery.search', major_version:1, data:{items:[]}, error:null } });
    },
  });
  const host = { location:{protocol:'app:',origin:'app://root'}, electronAPI:{invokeCapability:(...args)=>client.invoke(...args)} };
  const result = await createBusinessFacade(host).invoke('simulation.connector.recovery.search', {version:1,payload:{}});
  assert.deepEqual(result, {items:[]});
  assert.deepEqual(requests[0].payload, {});
  assert.equal(requests[0].version, 1);
  assert.match(requests[0].idempotency_key, /^simulation\.connector\.recovery\.search:/);
});

test('preload and registered IPC dispatch recovery search from the real plugin frame', async () => {
  const requests = [], handlers = {}, exposed = {};
  const client = new CapabilityClient({
    origin:'https://gateway.test', auth:{withAccessToken:fn=>fn('fixture-token'),refresh:async()=>false},
    fetchImpl:async(_url,options)=>{requests.push(JSON.parse(options.body));return Response.json({success:true,data:{ok:true,status:'completed',capability_id:'simulation.connector.recovery.search',major_version:1,data:{items:[]},error:null}});},
  });
  registerCapabilityIPC({handle:(name,handler)=>{handlers[name]=handler;}}, client, {manifestAllows:installedOfficialCapabilities(path.join(__dirname,'..','..','..','..'))});
  const event={senderFrame:{url:'app://root/packages/sim-plugin/web/cad_sim/index.html',top:{url:'app://root/web/index.html'}},sender:{isDestroyed:()=>false}};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname,'..','..','..','core','electron','preload.js'),'utf8'), {URLSearchParams,globalThis:{crypto:{randomUUID:()=> '12345678-1234-1234-1234-123456789abc'}},require:name=>{
    assert.equal(name,'electron'); return {contextBridge:{exposeInMainWorld:(key,value)=>{exposed[key]=value;}},ipcRenderer:{invoke:(_channel,...args)=>handlers['capability:invoke'](event,...args),on:()=>{},send:()=>{},removeListener:()=>{}}};
  }});
  const child={location:{protocol:'app:',origin:'app://root'},parent:{location:{protocol:'app:',origin:'app://root'},electronAPI:exposed.electronAPI},crypto:{randomUUID:()=> '12345678-1234-1234-1234-123456789abc'}};
  const result=await createBusinessFacade(child).invoke('simulation.connector.recovery.search',{version:1,payload:{}});
  assert.deepEqual(result,{items:[]}); assert.equal(requests.length,1);
});

test('invalid invocation diagnostics identify the validation stage without leaking values', async () => {
  const warnings = [], handlers = {};
  const originalWarn = console.warn; console.warn = (...args) => warnings.push(args);
  try {
    const client = new CapabilityClient({origin:'https://gateway.test',auth:{},fetchImpl:async()=>assert.fail('invalid request must not dispatch')});
    const clientFailure=await client.invoke('simulation.connector.recovery.search',{version:1,payload:['payload-secret']});
    assert.equal(clientFailure.error.code,'invalid_invocation'); assert.equal(clientFailure.error.message,'invalid_invocation:capability_client');
    registerCapabilityIPC({handle:(name,handler)=>{handlers[name]=handler;}},client);
    const event={senderFrame:{url:'app://root/packages/sim-plugin/web/cad_sim/index.html',top:{url:'app://root/web/index.html'}},sender:{isDestroyed:()=>false}};
    const ipcFailure=await handlers['capability:invoke'](event,'simulation.connector.recovery.search',{version:'1',payload:{token:'token-secret'}});
    assert.equal(ipcFailure.error.code,'invalid_invocation'); assert.equal(ipcFailure.error.message,'invalid_invocation:capability_ipc');
    const host={console:{warn:(...args)=>warnings.push(args)},location:{protocol:'https:',origin:'https://app.test'}};
    await assert.rejects(createBusinessFacade(host).invoke('simulation.connector.recovery.search',{version:1,payload:{},unexpected:'renderer-secret'}),error=>error.code==='invalid_invocation'&&error.message==='invalid_invocation:business_facade');
  } finally { console.warn = originalWarn; }
  const text=JSON.stringify(warnings);
  assert.match(text,/capability_client|capability_ipc|business_facade/);
  assert.doesNotMatch(text,/payload-secret|token-secret|renderer-secret/);
});

test('select all eligible and deselect exclude unsupported rows', async () => {
  const p=page({search:{items:[item,{...item,plan_id:'plan-2',operation_id:'operation-2'},{...item,plan_id:'plan-x',operation_id:'operation-x',eligible:false}]}});
  p.document.getElementById('btnConnectorRecovery').click();await flush();
  p.document.querySelector('[value="not_executed"]').click();p.document.getElementById('connectorRecoverySelectAll').click();
  assert.equal(p.document.querySelectorAll('[data-recovery-plan][aria-pressed="true"]').length,2);
  p.document.getElementById('connectorRecoveryDeselectAll').click();
  assert.equal(p.document.querySelectorAll('[data-recovery-plan][aria-pressed="true"]').length,0);p.dom.window.close();
});

test('batch freezes inputs and resolves selected operations serially with separate keys and one human confirmation',async()=>{
  const order=[],prompts=[];let releaseFirst;
  const p=page({search:{items:[item,{...item,plan_id:'plan-2',operation_id:'operation-2'}]},confirm:message=>{prompts.push(message);return true;},resolve:envelope=>{
    order.push(envelope.payload.plan_id);if(order.length===1)return new Promise(resolve=>{releaseFirst=()=>resolve({audit_ref:'audit-1'});});return {audit_ref:'audit-2'};
  }});
  p.document.getElementById('btnConnectorRecovery').click();await flush();p.document.querySelector('[value="not_executed"]').click();p.document.getElementById('connectorRecoverySelectAll').click();
  const reason=p.document.getElementById('connectorRecoveryReason');reason.value='批量现场核对';reason.dispatchEvent(new p.dom.window.Event('input'));
  p.document.getElementById('connectorRecoveryConfirm').click();await flush();
  assert.deepEqual(order,['plan-1']);assert.equal(reason.disabled,true);assert.equal(prompts.length,1);assert.match(prompts[0],/2 项.*operation-1.*operation-2/s);
  releaseFirst();await flush();await flush();assert.deepEqual(order,['plan-1','plan-2']);
  const writes=p.calls.filter(call=>call.id==='simulation.connector.recovery.resolve');assert.notEqual(writes[0].envelope.idempotency_key,writes[1].envelope.idempotency_key);
  assert.match(p.document.getElementById('connectorRecoveryResults').textContent,/audit-1/);assert.match(p.document.getElementById('connectorRecoveryResults').textContent,/audit-2/);p.dom.window.close();
});

test('batch continues after definitive item failure but stops on coded stale conflict',async()=>{
  const plans=['plan-1','plan-2','plan-3'].map((plan_id,index)=>({...item,plan_id,operation_id:`operation-${index+1}`}));
  const p=page({search:{items:plans},resolve:envelope=>{if(envelope.payload.plan_id==='plan-1')throw Error('validation_error');if(envelope.payload.plan_id==='plan-2')throw Object.assign(Error('opaque rejection'),{code:'stale_resource_version'});return {audit_ref:'must-not-run'};}});
  p.document.getElementById('btnConnectorRecovery').click();await flush();p.document.querySelector('[value="not_executed"]').click();p.document.getElementById('connectorRecoverySelectAll').click();
  const reason=p.document.getElementById('connectorRecoveryReason');reason.value='批量核对';reason.dispatchEvent(new p.dom.window.Event('input'));p.document.getElementById('connectorRecoveryConfirm').click();await flush();await flush();
  assert.deepEqual(p.calls.filter(c=>c.id==='simulation.connector.recovery.resolve').map(c=>c.envelope.payload.plan_id),['plan-1','plan-2']);
  assert.match(p.document.getElementById('connectorRecoveryResults').textContent,/validation_error/);assert.match(p.document.getElementById('connectorRecoveryStatus').textContent,/已停止/);p.dom.window.close();
});

test('confirmation refusal writes nothing and unknown outcome stops remaining as uncertain',async()=>{
  const plans=[item,{...item,plan_id:'plan-2',operation_id:'operation-2'}];const refused=page({search:{items:plans},confirm:()=>false});
  refused.document.getElementById('btnConnectorRecovery').click();await flush();refused.document.querySelector('[value="executed"]').click();refused.document.getElementById('connectorRecoverySelectAll').click();
  const rr=refused.document.getElementById('connectorRecoveryReason');rr.value='核对';rr.dispatchEvent(new refused.dom.window.Event('input'));refused.document.getElementById('connectorRecoveryConfirm').click();await flush();
  assert.equal(refused.calls.filter(c=>c.id==='simulation.connector.recovery.resolve').length,0);refused.dom.window.close();
  const uncertain=page({search:{items:plans},resolve:()=>{throw Error('outcome_unknown');}});uncertain.document.getElementById('btnConnectorRecovery').click();await flush();uncertain.document.querySelector('[value="executed"]').click();uncertain.document.getElementById('connectorRecoverySelectAll').click();
  const ur=uncertain.document.getElementById('connectorRecoveryReason');ur.value='核对';ur.dispatchEvent(new uncertain.dom.window.Event('input'));uncertain.document.getElementById('connectorRecoveryConfirm').click();await flush();
  assert.equal(uncertain.calls.filter(c=>c.id==='simulation.connector.recovery.resolve').length,1);assert.match(uncertain.document.getElementById('connectorRecoveryResults').textContent,/结果不确定/);uncertain.dom.window.close();
});

test('successful items cannot be selected or resubmitted in the same dialog',async()=>{
  const plans=[item,{...item,plan_id:'plan-2',operation_id:'operation-2'}];let plan2Attempts=0;
  const p=page({search:{items:plans},resolve:envelope=>{if(envelope.payload.plan_id==='plan-2'){plan2Attempts++;throw Error('validation_error');}return {audit_ref:'audit-1'};}});
  p.document.getElementById('btnConnectorRecovery').click();await flush();p.document.querySelector('[value="not_executed"]').click();p.document.getElementById('connectorRecoverySelectAll').click();
  const reason=p.document.getElementById('connectorRecoveryReason');reason.value='核对';reason.dispatchEvent(new p.dom.window.Event('input'));p.document.getElementById('connectorRecoveryConfirm').click();await flush();await flush();
  const buttons=p.document.querySelectorAll('[data-recovery-plan]');assert.equal(buttons[0].disabled,true);buttons[1].click();assert.equal(p.document.getElementById('connectorRecoveryConfirm').disabled,false);
  p.document.getElementById('connectorRecoveryConfirm').click();await flush();await flush();
  const writes=p.calls.filter(c=>c.id==='simulation.connector.recovery.resolve').map(c=>c.envelope.payload.plan_id);assert.deepEqual(writes,['plan-1','plan-2','plan-2']);assert.equal(plan2Attempts,2);p.dom.window.close();
});

test('abandoned is explained and sent without claiming executed or not executed',async()=>{
  const p=page();p.document.getElementById('btnConnectorRecovery').click();await flush();p.document.querySelector('[data-recovery-plan]').click();p.document.querySelector('[value="abandoned"]').click();
  const reason=p.document.getElementById('connectorRecoveryReason');reason.value='无法安全判断，归档';reason.dispatchEvent(new p.dom.window.Event('input'));p.document.getElementById('connectorRecoveryConfirm').click();await flush();
  const write=p.calls.find(call=>call.id==='simulation.connector.recovery.resolve');assert.equal(write.envelope.payload.decision,'abandoned');p.dom.window.close();
});

test('select all follows current decision, reports selected count, and enables confirmation',async()=>{
  const plans=[item,{...item,plan_id:'plan-2',operation_id:'operation-2',allowed_decisions:['abandoned']},{...item,plan_id:'plan-3',operation_id:'operation-3',allowed_decisions:['executed','abandoned']}];
  const p=page({search:{items:plans}});p.document.getElementById('btnConnectorRecovery').click();await flush();
  const selectAll=p.document.getElementById('connectorRecoverySelectAll');assert.equal(selectAll.disabled,true);
  p.document.querySelector('[value="executed"]').click();assert.equal(selectAll.disabled,false);assert.match(selectAll.textContent,/全选当前结论可处理项（2）/);selectAll.click();
  const reason=p.document.getElementById('connectorRecoveryReason');reason.value='核对';reason.dispatchEvent(new p.dom.window.Event('input'));
  assert.equal(p.document.querySelectorAll('[aria-pressed="true"]').length,2);assert.match(p.document.getElementById('connectorRecoveryStatus').textContent,/已选 2\/2/);assert.equal(p.document.getElementById('connectorRecoveryConfirm').disabled,false);p.dom.window.close();
});

test('missing outcome hash can only be abandoned and sends fingerprint without null fences',async()=>{
  const missingFingerprint=`sha256:${'d'.repeat(64)}`;const missing={...item,plan_id:'plan-missing',operation_id:'operation-missing',outcome_hash:null,plan_hash:null,eligible:true,allowed_decisions:['abandoned'],ineligible_reason:null,recovery_fingerprint:missingFingerprint};
  const unknown={...item,plan_id:'plan-unknown',operation_id:'operation-unknown',eligible:true,allowed_decisions:['abandoned']};
  const p=page({search:{items:[missing,unknown]}});p.document.getElementById('btnConnectorRecovery').click();await flush();
  const rows=p.document.querySelectorAll('[data-recovery-plan]');p.document.querySelector('[value="abandoned"]').click();assert.equal(rows[0].disabled,false);assert.match(rows[0].textContent,/缺少结果摘要，仅可放弃并归档/);assert.doesNotMatch(rows[1].textContent,/缺少结果摘要/);p.document.getElementById('connectorRecoverySelectAll').click();
  const reason=p.document.getElementById('connectorRecoveryReason');reason.value='缺少摘要归档';reason.dispatchEvent(new p.dom.window.Event('input'));p.document.getElementById('connectorRecoveryConfirm').click();await flush();
  const payload=p.calls.find(call=>call.id==='simulation.connector.recovery.resolve').envelope.payload;assert.deepEqual(JSON.parse(JSON.stringify(payload)),{plan_id:'plan-missing',device_id:'device-1',expected_generation:7,expected_recovery_fingerprint:missingFingerprint,decision:'abandoned',reason:'缺少摘要归档'});assert.equal(p.document.body.textContent.includes(missingFingerprint),false);p.dom.window.close();
});

test('malformed durable item is safely labeled unknown and remains abandonable without exposing hashes',async()=>{
  const malformedFingerprint=`sha256:${'e'.repeat(64)}`;const malformed={...item,operation_id:'unknown_operation',outcome_hash:null,plan_hash:null,recovery_fingerprint:malformedFingerprint,allowed_decisions:['abandoned'],ineligible_reason:null};const p=page({search:{items:[malformed]}});
  p.document.getElementById('btnConnectorRecovery').click();await flush();p.document.querySelector('[value="abandoned"]').click();assert.equal(p.document.querySelector('[data-recovery-plan]').disabled,false);assert.match(p.document.getElementById('connectorRecoveryItems').textContent,/unknown_operation/);assert.equal(p.document.body.textContent.includes(malformedFingerprint),false);p.dom.window.close();
});

test('legacy item without allowed decisions stays disabled',async()=>{
  const legacy={...item};delete legacy.allowed_decisions;const p=page({search:{items:[legacy]}});p.document.getElementById('btnConnectorRecovery').click();await flush();assert.equal(p.document.querySelector('[data-recovery-plan]').disabled,true);p.document.querySelector('[value="abandoned"]').click();assert.equal(p.document.querySelector('[data-recovery-plan]').disabled,true);assert.match(p.document.getElementById('connectorRecoverySelectAll').textContent,/（0）/);p.dom.window.close();
});

test('recovery rows use checkbox visuals and dialog has a viewport fallback around a scrollable list',()=>{
  const html=fs.readFileSync(path.join(__dirname,'index.html'),'utf8');assert.match(html,/放弃并归档该未完成操作/);assert.match(html,/不重试、不宣称已执行\/未执行、不撤销外部效果/);
  const css=fs.readFileSync(path.join(__dirname,'cad_sim.css'),'utf8');assert.match(css,/\.cs-recovery-dialog\s*\{[^}]*max-height:\s*calc\(100vh - 32px\)[^}]*overflow-y:\s*auto/s);assert.match(css,/\.cs-recovery-items\s*\{[^}]*flex:\s*1[^}]*min-height:\s*0[^}]*overflow:\s*auto/s);assert.match(css,/\.cs-recovery-check/);assert.match(css,/aria-pressed="true"[^}]*background/s);
});

test('real page uses unique recovery CSS and script revisions with bounded wide wrapping layout',()=>{
  const html=fs.readFileSync(path.join(__dirname,'index.html'),'utf8');assert.match(html,/cad_sim\.css\?rev=20260917-online-binding-recovery-2/);assert.match(html,/connector_recovery\.js\?rev=20260916-recovery-fingerprint-1/);
  const css=fs.readFileSync(path.join(__dirname,'cad_sim.css'),'utf8');assert.match(css,/\.cs-recovery-dialog\s*\{[^}]*width:\s*min\(900px, calc\(100vw - 32px\)\)/s);assert.match(css,/\.cs-recovery-items\s*\{[^}]*overflow(?:-y)?:\s*auto/s);assert.match(css,/\.cs-recovery-item-body\s*\{[^}]*min-width:\s*0/s);assert.match(css,/overflow-wrap:\s*anywhere/);
});

test('pagination sends exact payload, reports totals, clears selection, and disables boundaries',async()=>{
  const searches=[];const p=page({search:envelope=>{searches.push(envelope.payload);return envelope.payload.page===1?{items:[item],page:1,page_size:5,total:6,page_count:2}:{items:[{...item,plan_id:'plan-6',operation_id:'operation-6'}],page:2,page_size:5,total:6,page_count:2};}});
  p.document.getElementById('btnConnectorRecovery').click();await flush();assert.deepEqual(JSON.parse(JSON.stringify(searches[0])),{page:1,page_size:5});assert.match(p.document.getElementById('connectorRecoveryPageInfo').textContent,/第 1 \/ 2 页 · 共 6 项/);assert.equal(p.document.getElementById('connectorRecoveryPrevPage').disabled,true);
  p.document.querySelector('[value="executed"]').click();p.document.querySelector('[data-recovery-plan]').click();p.document.getElementById('connectorRecoveryNextPage').click();await flush();assert.deepEqual(JSON.parse(JSON.stringify(searches[1])),{page:2,page_size:5});assert.match(p.document.getElementById('connectorRecoveryPageInfo').textContent,/第 2 \/ 2 页 · 共 6 项/);assert.equal(p.document.getElementById('connectorRecoveryNextPage').disabled,true);assert.equal(p.document.querySelectorAll('[aria-pressed="true"]').length,0);p.dom.window.close();
});

test('post-resolve refresh falls back from an emptied last page to the final valid page',async()=>{
  const searches=[];let resolved=false;const p=page({search:envelope=>{searches.push(envelope.payload.page);if(envelope.payload.page===1)return {items:[item],page:1,page_size:5,total:resolved?5:6,page_count:resolved?1:2};if(!resolved)return {items:[{...item,plan_id:'plan-6',operation_id:'operation-6'}],page:2,page_size:5,total:6,page_count:2};return {items:[],page:2,page_size:5,total:5,page_count:1};},resolve:()=>{resolved=true;return {audit_ref:'audit-6'};}});
  p.document.getElementById('btnConnectorRecovery').click();await flush();p.document.getElementById('connectorRecoveryNextPage').click();await flush();p.document.querySelector('[value="not_executed"]').click();p.document.querySelector('[data-recovery-plan]').click();const reason=p.document.getElementById('connectorRecoveryReason');reason.value='末页核对';reason.dispatchEvent(new p.dom.window.Event('input'));p.document.getElementById('connectorRecoveryConfirm').click();await flush();await flush();
  assert.deepEqual(searches,[1,2,2,1]);assert.match(p.document.getElementById('connectorRecoveryPageInfo').textContent,/第 1 \/ 1 页 · 共 5 项/);assert.match(p.document.getElementById('connectorRecoveryResults').textContent,/audit-6/);p.dom.window.close();
});

test('empty post-resolve result normalizes an old later page and disables previous page',async()=>{
  let resolved=false;const p=page({search:envelope=>resolved?{items:[],page:envelope.payload.page,page_size:5,total:0,page_count:0}:envelope.payload.page===1?{items:[item],page:1,page_size:5,total:6,page_count:2}:{items:[{...item,plan_id:'plan-6',operation_id:'operation-6'}],page:2,page_size:5,total:6,page_count:2},resolve:()=>{resolved=true;return {audit_ref:'audit-empty'};}});
  p.document.getElementById('btnConnectorRecovery').click();await flush();p.document.getElementById('connectorRecoveryNextPage').click();await flush();p.document.querySelector('[value="not_executed"]').click();p.document.querySelector('[data-recovery-plan]').click();const reason=p.document.getElementById('connectorRecoveryReason');reason.value='清空末页';reason.dispatchEvent(new p.dom.window.Event('input'));p.document.getElementById('connectorRecoveryConfirm').click();await flush();await flush();
  assert.match(p.document.getElementById('connectorRecoveryPageInfo').textContent,/第 0 \/ 0 页 · 共 0 项/);assert.equal(p.document.getElementById('connectorRecoveryPrevPage').disabled,true);p.dom.window.close();
});

test('selection status updates to zero after deselecting the last item or changing decision',async()=>{
  const plans=[{...item,allowed_decisions:['executed']},{...item,plan_id:'plan-2',operation_id:'operation-2',allowed_decisions:['abandoned']}];const p=page({search:{items:plans}});
  p.document.getElementById('btnConnectorRecovery').click();await flush();p.document.querySelector('[value="executed"]').click();p.document.querySelector('[data-recovery-plan]').click();assert.match(p.document.getElementById('connectorRecoveryStatus').textContent,/已选 1\/1/);
  p.document.querySelector('[data-recovery-plan]').click();assert.match(p.document.getElementById('connectorRecoveryStatus').textContent,/已选 0\/1/);
  p.document.querySelector('[data-recovery-plan]').click();p.document.querySelector('[value="abandoned"]').click();assert.match(p.document.getElementById('connectorRecoveryStatus').textContent,/已选 0\/1/);p.dom.window.close();
});

test('confirmation and results distinguish duplicate operation ids by plan and device',async()=>{
  const prompts=[];const plans=[item,{...item,plan_id:'plan-2',device_id:'device-2'}];
  const p=page({search:{items:plans},confirm:message=>{prompts.push(message);return true;}});
  p.document.getElementById('btnConnectorRecovery').click();await flush();p.document.querySelector('[value="not_executed"]').click();p.document.getElementById('connectorRecoverySelectAll').click();
  const reason=p.document.getElementById('connectorRecoveryReason');reason.value='相同操作编号核对';reason.dispatchEvent(new p.dom.window.Event('input'));p.document.getElementById('connectorRecoveryConfirm').click();await flush();await flush();
  assert.match(prompts[0],/decision=not_executed/);assert.match(prompts[0],/reason=相同操作编号核对/);assert.match(prompts[0],/plan=plan-1.*device=device-1.*plan=plan-2.*device=device-2/s);
  const result=p.document.getElementById('connectorRecoveryResults').textContent;assert.match(result,/plan-1.*device-1/);assert.match(result,/plan-2.*device-2/);p.dom.window.close();
});

test('actual state and runtime errors plus unknown write errors stop remaining dispatch',async()=>{
  const codes=['recovery_state_changed','runtime_owner_mismatch','runtime_session_invalid','outcome_persistence_failed','invalid_response','runtime_timeout','future_unclassified_write_error'];
  for(const code of codes){
    const plans=[item,{...item,plan_id:'plan-2',operation_id:'operation-2'}];
    const p=page({search:{items:plans},resolve:()=>{throw Object.assign(Error('opaque'),{code});}});
    p.document.getElementById('btnConnectorRecovery').click();await flush();p.document.querySelector('[value="not_executed"]').click();p.document.getElementById('connectorRecoverySelectAll').click();
    const reason=p.document.getElementById('connectorRecoveryReason');reason.value='核对';reason.dispatchEvent(new p.dom.window.Event('input'));p.document.getElementById('connectorRecoveryConfirm').click();await flush();await flush();
    assert.equal(p.calls.filter(call=>call.id==='simulation.connector.recovery.resolve').length,1,code);assert.match(p.document.getElementById('connectorRecoveryStatus').textContent,/已停止/,code);p.dom.window.close();
  }
});

test('closing before a delayed real facade challenge refuses confirmation and sends no confirmed write',async()=>{
  let releaseChallenge;const envelopes=[];
  const host={location:{protocol:'app:',origin:'app://root'},electronAPI:{invokeCapability:async(id,envelope)=>{
    if(id.endsWith('.search'))return {success:true,data:{ok:true,status:'completed',data:{items:[item],page:1,page_size:5,total:1,page_count:1}}};
    envelopes.push(envelope);if(!envelope.confirmation)return {success:false,data:{ok:false,status:'rejected',error:{code:'confirmation_required',confirmation_challenge:'12345678-1234-1234-1234-123456789abc'}}};
    return {success:true,data:{ok:true,status:'completed',data:{audit_ref:'must-not-write'}}};
  }}};
  const facade=createBusinessFacade(host);const delayedInvoke=async(id,envelope,confirmation)=>{
    if(id.endsWith('.resolve'))await new Promise(resolve=>{releaseChallenge=resolve;});return facade.invoke(id,envelope,confirmation);
  };
  const p=page({invoke:delayedInvoke});p.document.getElementById('btnConnectorRecovery').click();await flush();
  p.document.querySelector('[data-recovery-plan]').click();p.document.querySelector('[value="not_executed"]').click();const reason=p.document.getElementById('connectorRecoveryReason');reason.value='核对';reason.dispatchEvent(new p.dom.window.Event('input'));
  p.document.getElementById('connectorRecoveryConfirm').click();await flush();p.document.getElementById('connectorRecoveryCancel').click();releaseChallenge();await flush();await flush();
  assert.equal(envelopes.filter(envelope=>envelope.confirmation).length,0);assert.equal(p.document.getElementById('connectorRecoveryOverlay').classList.contains('hidden'),true);p.dom.window.close();
});
