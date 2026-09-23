const test = require('node:test');
test('closing or reopening a same-title document preserves cached environment without rebinding',async()=>{
  const {dom}=page(); const {createAdapter}=dom.window.AI00LiveDocumentSwitcher;
  let closed=true,cleared=0;const contexts=[];
  const store={state:{workspace:{workspace_gid:'10'}},clearSelection:()=>cleared++};
  const adapter=createAdapter({getStore:()=>store,getNativeView:()=>({}),onContext:value=>contexts.push(value),
    readDocument:async()=>{if(closed)throw Error('native_view_unavailable');return{document_session:'new-session',display_name:'same.plmxml',identity_operation_id:'new-op'};},
    invoke:async()=>({state:'unbound',workspace_gid:null,document_session:'new-session'})});
  await adapter.observeCurrentDocument(); closed=false; await adapter.observeCurrentDocument();
  dom.window.close();
  assert.equal(cleared,0);
  assert.equal(contexts.at(-1),false);
});
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

function page(adapter) {
  const dom = new JSDOM(fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8'), { runScripts: 'outside-only' });
  dom.window.eval(fs.readFileSync(path.join(__dirname, 'live_document_switcher.js'), 'utf8'));
  const mounted = dom.window.AI00LiveDocumentSwitcher.mount({ adapter });
  return { dom, document: dom.window.document, mounted };
}

test('explicit reconnect selects exact candidate and keeps environment and snapshots',async()=>{
  const {dom}=page(),calls=[],contexts=[];
  const store={state:{workspace:{workspace_gid:'10'}},clearSelection:()=>assert.fail('must keep environment')};
  const adapter=dom.window.AI00LiveDocumentSwitcher.createAdapter({getStore:()=>store,
    getNativeView:()=>({selectDocument:async key=>{calls.push(key);return {state:'attached',documentKey:key};}}),
    reconnectDocument:async(gid,{isCurrent})=>{assert.equal(gid,'10');assert.ok(isCurrent());calls.push('rebind');return {document_session:'new'};},
    readDocument:async()=>({document_session:'new',identity_operation_id:'proof',native_window_key:'vmwin:2'}),
    invoke:async()=>({workspace_gid:'10',state:'bound',document_session:'new'}),onContext:v=>contexts.push(v)});
  const result=await adapter.reconnectEnvironment('vmwin:2');
  assert.equal(result.status,'reconnected'); assert.equal(result.structureVerification,'unverified');
  assert.deepEqual(calls,['vmwin:2','rebind']);assert.equal(contexts.at(-1),true);
  dom.window.close();
});

test('explicit recovery finds an unobserved bound session by signed identity, never by duplicate title',async()=>{
  const {dom}=page();const selections=[],contexts=[];let current='A';
  const store={state:{workspace:{workspace_gid:'10'}},openWorkspace:async()=>{}};
  const adapter=dom.window.AI00LiveDocumentSwitcher.createAdapter({getStore:()=>store,
    getNativeView:()=>({
      listDocuments:async()=>['A','B'].map(key=>({key:`vmwin:${key}`,name:'same',current:key===current})),
      selectDocument:async key=>{current=key.split(':')[1];selections.push(key);return {state:'documentChanged',documentKey:key};},
    }),
    readDocument:async()=>({identity_operation_id:`proof-${current}`,document_session:`session-${current}`,native_window_key:`vmwin:${current}`}),
    invoke:async(_,payload)=>({workspace_gid:'10',state:'bound',document_session:payload.workspace_gid?'session-B':`session-${current}`}),
    onContext:value=>contexts.push(value),
  });
  const result=await adapter.recoverEnvironment();
  assert.equal(result.status,'recovered');
  assert.equal(result.environmentId,'10');
  assert.deepEqual(selections,['vmwin:A','vmwin:B']);
  assert.equal(contexts.at(-1),true);
  dom.window.close();
});

test('selector offers reconnect separately from switching and reports snapshot not verified',async()=>{
  const calls=[],notifications=[];
  const {dom,document,mounted}=page({listDocuments:async()=>[{key:'vmwin:2',name:'same'}],
    canReconnect:()=>true,reconnectEnvironment:async key=>{calls.push(key);return {status:'reconnected'};}});
  dom.window._cmdShow=(message,type)=>notifications.push([message,type]);
  await mounted.open();
  const cards=document.querySelectorAll('[data-document-card]');
  assert.equal(cards.length,1);
  assert.equal(cards[0].querySelectorAll('button').length,2);
  assert.match(cards[0].querySelector('.cs-document-title').textContent,/same/);
  document.querySelector('[data-reconnect-key]').click();
  await new Promise(resolve=>setImmediate(resolve));
  assert.deepEqual(calls,['vmwin:2']);
  assert.equal(notifications[0][0],'');
  assert.match(notifications.at(-1)[0],/连接已恢复.*节点尚未核对/);
  assert.match(document.getElementById('documentSwitcherStatus').textContent,/缓存.*未核对/);
  mounted.dispose();dom.window.close();
});

test('manual document selector initializes the native session before enumerating windows', async () => {
  const {dom} = page();
  const calls = [];
  const adapter = dom.window.AI00LiveDocumentSwitcher.createAdapter({
    getNativeView: () => ({listDocuments:async()=>{calls.push('list');return [];}}),
    prepareDocumentSelection:async()=>{calls.push('prepare');},
  });
  await adapter.listDocuments();
  assert.deepEqual(calls,['prepare','list']);
  dom.window.close();
});

test('switch button is in operations group and document label opens the same selector', async () => {
  const { dom, document, mounted } = page({ listDocuments: async () => [] });
  const button = document.getElementById('btnSwitchVmDocument');
  assert.ok(button);
  assert.equal(button.closest('#ai00StatusBar'), null);
  button.click();
  await Promise.resolve();
  assert.equal(document.getElementById('liveDocumentSwitcher').classList.contains('hidden'), false);
  document.getElementById('documentSwitcherClose').click();
  document.getElementById('vmDocumentLabel').click();
  await Promise.resolve();
  assert.equal(document.getElementById('liveDocumentSwitcher').classList.contains('hidden'), false);
  mounted.dispose(); dom.window.close();
});

test('same-name native documents remain separate choices and select exact key', async () => {
  const selected = [];
  const { dom, document, mounted } = page({
    listDocuments: async () => [{ key: 'doc-1', name: 'same', current: true }, { key: 'doc-2', name: 'same', current: false }],
    selectDocument: async key => { selected.push(key); return { environmentId: null }; },
  });
  await mounted.open();
  const buttons = document.querySelectorAll('[data-document-key]');
  assert.equal(buttons.length, 2);
  buttons[1].click();
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(selected, ['doc-2']);
  assert.match(document.getElementById('documentSwitcherStatus').textContent, /未绑定/);
  mounted.dispose(); dom.window.close();
});

test('missing adapter reports unavailable without fabricated document choices', async () => {
  const { dom, document, mounted } = page();
  await mounted.open();
  assert.equal(document.querySelectorAll('[data-document-key]').length, 0);
  assert.match(document.getElementById('documentSwitcherStatus').textContent, /尚未就绪/);
  mounted.dispose(); dom.window.close();
});

test('native choice resolves a signed identity before switching its bound environment', async () => {
  const actions = [];
  const { dom, mounted } = page();
  const adapter = dom.window.AI00LiveDocumentSwitcher.createAdapter({
    getNativeView: () => ({ selectDocument: async key => { actions.push(key); return { state: 'documentChanged' }; } }),
    readDocument: async () => ({ identity_operation_id: 'op-1', document_session: 'session-1', native_window_key: 'vmwin:1' }),
    invoke: async (cap, payload) => { actions.push([cap, payload]); return { state: 'importing', workspace_gid: '123', document_session: 'session-1' }; },
    getStore: () => ({ openWorkspace: async gid => actions.push(gid) }),
  });
  const result = await adapter.selectDocument('vmwin:1');
  assert.equal(result.environmentId, '123');
  assert.equal(actions[0], 'vmwin:1');
  assert.equal(actions[1][0], 'simulation.environment.live_document.binding.get');
  assert.equal(actions[1][1].identity_operation_id, 'op-1');
  assert.equal(actions[2], '123');
  mounted.dispose(); dom.window.close();
});

test('unbound native document clears selected environment, never reuses the old environment', async () => {
  let cleared = 0;
  const { dom, mounted } = page();
  const adapter = dom.window.AI00LiveDocumentSwitcher.createAdapter({
    getNativeView: () => ({ selectDocument: async () => ({ state: 'documentChanged' }) }),
    readDocument: async () => ({ identity_operation_id: 'op', document_session: 's', native_window_key: 'vmwin:1' }),
    invoke: async () => ({ state: 'unbound', workspace_gid: null, document_session: 's' }),
    getStore: () => ({ clearSelection: () => cleared++ }),
  });
  assert.equal((await adapter.selectDocument('vmwin:1')).environmentId, null);
  assert.equal(cleared, 1);
  mounted.dispose(); dom.window.close();
});

test('document stays visible after native switch when environment identity is unavailable', async () => {
  const context = []; let cleared = 0;
  const { dom, mounted } = page();
  const adapter = dom.window.AI00LiveDocumentSwitcher.createAdapter({
    getNativeView: () => ({ selectDocument: async () => ({ state: 'documentChanged', documentKey: 'vmwin:2' }) }),
    readDocument: async () => { throw Error('vismockup_process_identity_unavailable'); },
    invoke: async () => assert.fail('unverified identity must not query a binding'),
    getStore: () => ({ clearSelection() { cleared++; } }),
    onContext: value => context.push(value),
  });
  const result = await adapter.selectDocument('vmwin:2');
  assert.equal(result.status, 'selected_unverified');
  assert.equal(result.environmentId, null);
  assert.equal(cleared, 1);
  assert.deepEqual(context, [true]);
  mounted.dispose(); dom.window.close();
});

test('environment selection activates only a previously identity-verified exact native window', async () => {
  let current = 'A'; const selections = [];
  const { dom, mounted } = page();
  const adapter = dom.window.AI00LiveDocumentSwitcher.createAdapter({
    getNativeView: () => ({ listDocuments: async () => ['A', 'B'].map(k => ({ key: `vmwin:${k}`, current: k === current })),
      selectDocument: async key => { current = key.split(':')[1]; selections.push(key); return { state: 'documentChanged' }; } }),
    readDocument: async () => ({ identity_operation_id: current, document_session: current, native_window_key: `vmwin:${current}` }),
    invoke: async (_, payload) => ({ state: 'importing', workspace_gid: payload.workspace_gid || current, document_session: payload.workspace_gid || current }),
    getStore: () => ({ openWorkspace: async () => {} }),
  });
  await adapter.observeCurrentDocument();
  current = 'B'; await adapter.observeCurrentDocument();
  assert.equal((await adapter.selectEnvironment('A')).environmentId, 'A');
  assert.deepEqual(selections, ['vmwin:A']);
  await assert.rejects(adapter.selectEnvironment('unseen'), /bound_document_window_unavailable/);
  assert.deepEqual(selections, ['vmwin:A']);
  mounted.dispose(); dom.window.close();
});

test('dismissed selection cannot change environment after a delayed identity read', async () => {
  let resolve; const read = new Promise(yes => { resolve = yes; });
  let current = true;
  const { dom, mounted } = page();
  const adapter = dom.window.AI00LiveDocumentSwitcher.createAdapter({
    getNativeView: () => ({ selectDocument: async () => ({ state: 'documentChanged' }) }),
    readDocument: () => read, invoke: () => assert.fail('stale selection must not query binding'),
    getStore: () => ({ openWorkspace: () => assert.fail('stale selection must not commit') }),
  });
  const selection = adapter.selectDocument('vmwin:1', { isCurrent: () => current });
  await Promise.resolve(); current = false;
  resolve({ identity_operation_id: 'op', document_session: 'session' });
  assert.equal((await selection).status, 'superseded');
  mounted.dispose(); dom.window.close();
});
