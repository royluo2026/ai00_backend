const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { JSDOM } = require('jsdom');
const { createAdapter, createController, unavailable } = require('./live_document_adoption');
const session = () => ({ document_session: 'native-session-A', display_name: 'assembly.jt', connection_id: 'trusted-connector' });
const result = { workspace_gid: '101', version_gid: '102', model_document_gid: '103', state: 'importing', created: true };
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; };
test('calibrates loaded tail of 16k tree without opening or writing',async()=>{
 const nodes=Array.from({length:16002},(_,i)=>({node_key:`cache:${i}`,cache_node_key:String(i),item_revision_uid:'rev',parent_key:null,visible:true,visibility_state:'visible'}));
 const document={document_gid:'2',source_kind:'teamcenter_cache_snapshot',product_tree:{nodes}};
 const viewer={node_map:{'15999':{instance_id:'native-last',parent_node_key:null},'16000':{instance_id:'native-mixed',parent_node_key:null}},excluded:[{node_key:'16000'}],visibility_context:'fresh'};
 let reads=0;const local={state:'ready',visibilityContext:'fresh',readVisibility:async({source_nodes})=>{reads++;assert.ok(source_nodes.length<=128);return {visibility_context:'fresh',structure_epoch:5,nodes:source_nodes.map(n=>({source_node_id:n.source_node_id,visible:false,visibility_state:'hidden'}))};},ensureReady:()=>{throw Error('unexpected_open');},executeCachedIntent:()=>{throw Error('unexpected_write');}};
 const adapter=createAdapter({getStore:()=>({state:{workspace:{workspace_gid:'1',row_version:1}}}),getLocalInteraction:()=>local,ensureCachedReady:()=>{throw Error('unexpected_open');}});
 const result=await adapter.calibrateLoadedCache({workspaceGid:'1',document,viewer,isCurrent:()=>true});
 assert.equal(reads,1);assert.equal(result.calibrated,1);assert.equal(nodes[15999].visible,false);assert.equal(nodes[0].visible,null);assert.equal(nodes[16000].visible,null);assert.equal(nodes[16001].visibility_state,'unknown');
});
test('late loaded-cache read or changed structure epoch cannot restore old booleans',async()=>{
 for(const mode of ['selection','tree','context','structure_epoch']){
  const nodes=Array.from({length:129},(_,i)=>({node_key:`cache:${i}`,cache_node_key:String(i),item_revision_uid:'rev',visible:true}));
  const document={document_gid:'2',source_kind:'teamcenter_cache_snapshot',product_tree:{nodes}};
  const viewer={node_map:Object.fromEntries(nodes.map((_,i)=>[String(i),{instance_id:`native-${i}`,parent_node_key:null}])),excluded:[],visibility_context:'fresh'};
  const store={state:{workspace:{workspace_gid:'1'}}};let read=0,current=true;
  const local={state:'ready',visibilityContext:'fresh',readVisibility:async({source_nodes})=>{read++;if(read===2){if(mode==='selection')current=false;if(mode==='tree')document.product_tree.nodes=[...nodes];if(mode==='context')local.visibilityContext='other';}return {visibility_context:mode==='context'&&read===2?'other':'fresh',structure_epoch:mode==='structure_epoch'&&read===2?6:5,nodes:source_nodes.map(n=>({source_node_id:n.source_node_id,visible:false,visibility_state:'hidden'}))};}};
  const adapter=createAdapter({getStore:()=>store,getLocalInteraction:()=>local});
  await assert.rejects(adapter.calibrateLoadedCache({workspaceGid:'1',document,viewer,isCurrent:()=>current}),/document_selection_changed|cache_structure_changed/);
  assert.ok(nodes.every(n=>n.visible===null&&n.visibility_state==='unknown'),mode);
 }
});

test('cache first click calibrates generated instances, preserves excluded unknowns and never ensures online',async()=>{
 const nodes=[{node_key:'cache:root',cache_node_key:'root',item_revision_uid:'r',parent_key:null,has_children:true},{node_key:'cache:missing',cache_node_key:'missing',item_revision_uid:'r',parent_key:'cache:root'}];
 const document={document_gid:'2',source_kind:'teamcenter_cache_snapshot',product_tree:{nodes}};let writes=0,opens=0;
 const local={state:'ready',executeIntent:()=>{throw Error('online_forbidden');},ensureReady:()=>{throw Error('online_forbidden');},executeCachedIntent:async input=>{writes++;assert.equal(input.source_nodes[0].occurrence_path[0].occurrence_uid,'generated-root');assert.equal(input.source_selector,undefined);return {ok:true,visible:true};},readVisibility:async({source_nodes})=>({visibility_context:'cache-context',nodes:source_nodes.map(n=>({source_node_id:n.source_node_id,visible:false,visibility_state:'hidden'}))})};
 const adapter=createAdapter({getStore:()=>({state:{workspace:{workspace_gid:'1',row_version:1}}}),getLocalInteraction:()=>local,ensureCachedReady:async()=>{opens++;document._cacheViewer={node_map:{root:{instance_id:'generated-root',parent_node_key:null},missing:{instance_id:'generated-missing',parent_node_key:'root'}},excluded:[{node_key:'missing',reason:'transform_missing'}]};return {visibility_context:'cache-context'};}});
 const input={workspaceGid:'1',document,nodeKey:'cache:root',action:'show'};
 assert.equal((await adapter.actOnProductNode(input)).calibrated,true);assert.equal(writes,0);assert.equal(nodes[0].visible,null);assert.equal(nodes[1].visibility_state,'unknown');
 assert.equal(document._cacheViewer.native_visibility.root.visible,false,'native subset state is retained separately');
 await adapter.actOnProductNode(input);assert.equal(writes,1);assert.equal(nodes[0].visibility_state,'unknown','excluded descendants prevent aggregate confirmation after a successful action');
 await adapter.actOnProductNode({...input,calibrateOnly:true});assert.equal(writes,1,'open action only calibrates');
 await assert.rejects(adapter.actOnProductNode({...input,nodeKey:'cache:missing'}),/cache_node_excluded/);
 assert.ok(opens>0);
});

test('calibration refreshes real checkbox states without applying the initiating click',async()=>{
 const vm=require('node:vm'),path=require('node:path');
 for(const mode of ['visible','hidden','mixed','unknown','write_unknown']){
  const dom=new JSDOM('<body><div class="cs-model-document-tree"></div></body>',{runScripts:'outside-only',url:'http://127.0.0.1/'}),w=dom.window,ctx=dom.getInternalVMContext();
  try{
   vm.runInContext(fs.readFileSync(path.join(__dirname,'model_document_collection.js'),'utf8'),ctx);
   vm.runInContext(fs.readFileSync(path.join(__dirname,'cad_sim.js'),'utf8'),ctx);w.document.removeEventListener('DOMContentLoaded',w.init);
   w._simulationEnvironmentWorkspace={store:{state:{workspace:{workspace_gid:'1',row_version:1}}}};
   w._localViewerInteraction=()=>({executeIntent(){}});
   const gate=deferred();let actions=0;
   w._actOnModelNode=async()=>{actions++;await gate.promise;if(mode==='write_unknown')throw Error('outcome_unknown');w.__model.product_tree.nodes[1].visible=mode==='visible'?true:mode==='hidden'?false:null;w.__model.product_tree.nodes[1].visibility_state=mode;return {ok:true,calibrated:true};};
   vm.runInContext(`_cmdShow=()=>{};_simulationDebug=()=>{};
    window.__model={document_gid:'2',source_kind:'teamcenter_online',source_selector:{},product_tree:{nodes:[
     {node_key:'root',parent_key:null,visible:true,occurrence_path:[]},
     {node_key:'front',parent_key:'root',visible:false,occurrence_path:[{occurrence_uid:'front',item_revision_uid:'rev'}]},
     {node_key:'rear',parent_key:'root',visible:true,occurrence_path:[{occurrence_uid:'rear',item_revision_uid:'rev'}]}
    ]}};
    _modelDocumentCollection={state:{documents:[window.__model]}};
    const branch=window.AI00ModelDocumentCollection.buildProductForest(window.__model.product_tree.nodes)[0];
    document.querySelector('.cs-model-document-tree').append(...branch.children.map(node=>_buildProductTreeItem(node,'2')));`,ctx);
   if(mode==='write_unknown')vm.runInContext(`window.__model.product_tree.nodes[0].visibility_state='visible';document.querySelector('.cs-model-document-tree').append(_buildProductTreeItem(window.AI00ModelDocumentCollection.buildProductForest(window.__model.product_tree.nodes)[0],'2'));`,ctx);
   w.document.querySelector('.cs-alternate-tree-check').click();assert.ok([...w.document.querySelectorAll('.cs-alternate-tree-check')].every(check=>check.disabled));w.document.querySelectorAll('.cs-alternate-tree-name')[1].click();assert.equal(actions,1,'lock the owning document while calibration is in flight');gate.resolve();await new Promise(resolve=>setImmediate(resolve));
   const nodes=w.__model.product_tree.nodes;
   assert.equal(nodes[1].visible,mode==='visible'?true:mode==='hidden'?false:null,mode+' target');
   assert.equal(nodes[2].visible,true,'calibration must not hide siblings');
   const checks=w.document.querySelectorAll('.cs-alternate-tree-check');assert.equal(checks[0].dataset.visibility,mode==='write_unknown'?'unknown':mode);assert.equal(checks[1].dataset.visibility,'visible');
   if(mode==='write_unknown')assert.equal(checks[2].dataset.visibility,'unknown','failed descendant write must invalidate the calibrated ancestor');
   assert.ok([...checks].every(check=>!check.disabled));
   vm.runInContext(`window.__model.product_tree.nodes[0].visibility_state='mixed';document.body.append(_buildProductTreeItem(window.AI00ModelDocumentCollection.buildProductForest(window.__model.product_tree.nodes)[0],'2'));`,ctx);
   assert.equal(w.document.body.lastElementChild.querySelector('.cs-alternate-tree-check').indeterminate,true,'native mixed group state outranks incomplete cached descendants');
  }finally{dom.window.close();}
 }
});

test('calibration reads bounded batches and leaves unmapped or excess cache nodes unknown',async()=>{
 const nodes=Array.from({length:2001},(_,i)=>({node_key:String(i),visible:true,occurrence_path:[{occurrence_uid:'o'+i,item_revision_uid:'r'}]})),sizes=[];
 const document={document_gid:'2',source_kind:'teamcenter_online',source_selector:{},product_tree:{nodes}};
 const local={ensureReady:async()=>({visibility_context:'session-1'}),readVisibility:async({source_nodes})=>{sizes.push(source_nodes.length);return {nodes:source_nodes.map(node=>({source_node_id:node.source_node_id,visible:node.source_node_id!=='1',visibility_state:node.source_node_id==='1'?'unknown':'visible'}))};},executeIntent:async()=>{throw Error('first_click_must_not_write');}};
 const adapter=createAdapter({getStore:()=>({state:{workspace:{workspace_gid:'1',row_version:1}}}),getLocalInteraction:()=>local,invoke:()=>{throw Error('unexpected_bind');}});
 assert.equal((await adapter.actOnProductNode({workspaceGid:'1',document,nodeKey:'0',action:'hide'})).calibrated,true);
 assert.equal(sizes.length,16);assert.ok(sizes.every(size=>size<=128));assert.equal(sizes.reduce((a,b)=>a+b,0),2000);assert.equal(nodes[0].visible,true);assert.equal(nodes[1].visible,null);assert.equal(nodes[2000].visible,null);assert.equal(nodes[2000].visibility_state,'unknown');
});

test('an unknown node beyond the cache budget is sampled first and a later explicit action is allowed',async()=>{
 const nodes=Array.from({length:2002},(_,i)=>({node_key:String(i),parent_key:i===2001?'2000':null,visible:true,occurrence_path:[{occurrence_uid:'o'+i,item_revision_uid:'r'}]})),sampled=[];let writes=0;
 const document={document_gid:'2',source_kind:'teamcenter_online',source_selector:{},product_tree:{nodes}};
 const local={ensureReady:async()=>({visibility_context:'session-1'}),readVisibility:async({source_nodes})=>{sampled.push(...source_nodes.map(n=>n.source_node_id));return {visibility_context:'session-1',nodes:source_nodes.map(n=>({source_node_id:n.source_node_id,visible:null,visibility_state:'unknown'}))};},executeIntent:async()=>{writes++;return {ok:true,visible:true};}};
 const adapter=createAdapter({getStore:()=>({state:{workspace:{workspace_gid:'1',row_version:1}}}),getLocalInteraction:()=>local});const input={workspaceGid:'1',document,nodeKey:'2001',action:'show'};
 const first=await adapter.actOnProductNode(input);assert.equal(first.calibrated,true);assert.equal(first.calibration_unknown,true);assert.deepEqual(sampled.slice(0,2),['2001','2000']);assert.equal(writes,0);
 await adapter.actOnProductNode(input);assert.equal(writes,1);assert.equal(nodes[2001].visible,null,'unknown readback must override optimistic action state');
});

test('visibility context changes during calibration discard every batch result',async()=>{
 const nodes=Array.from({length:129},(_,i)=>({node_key:String(i),visible:false,occurrence_path:[{occurrence_uid:'o'+i,item_revision_uid:'r'}]}));let reads=0;
 const local={ensureReady:async()=>({visibility_context:'session-1'}),readVisibility:async({source_nodes})=>({visibility_context:++reads===1?'session-1':'session-2',nodes:source_nodes.map(n=>({source_node_id:n.source_node_id,visible:true,visibility_state:'visible'}))}),executeIntent:async()=>{throw Error('unexpected_write');}};
 const adapter=createAdapter({getStore:()=>({state:{workspace:{workspace_gid:'1',row_version:1}}}),getLocalInteraction:()=>local});
 await assert.rejects(adapter.actOnProductNode({workspaceGid:'1',document:{document_gid:'2',source_kind:'teamcenter_online',source_selector:{},product_tree:{nodes}},nodeKey:'0',action:'show'}),/document_selection_changed/);
 assert.ok(nodes.every(node=>node.visible===null&&node.visibility_state==='unknown'));
});
test('selected assembly and descendants retain the owning document and full occurrence paths',async()=>{
 const workspace={workspace_gid:'1',row_version:7},inputs=[],calls=[];
 const path=[{occurrence_uid:'chassis',item_revision_uid:'chassis-rev'},{occurrence_uid:'front',item_revision_uid:'front-08'}];
 const document={document_gid:'2',source_kind:'teamcenter_online',source_selector:{endpoint_id:'ep',object_uid:'whole-chassis',item_revision_uid:'root-rev',bom_view_uid:'root-bom',revision_rule:'Latest Working',configuration_date:'2026-09-17T00:00:00Z'},product_tree:{nodes:[{node_key:'front',name:'Front /08',occurrence_path:path,has_children:true},{node_key:'bolt',occurrence_path:[...path,{occurrence_uid:'bolt',item_revision_uid:'bolt-rev'}]}]}};
 const before=JSON.stringify(document.product_tree.nodes.map(node=>node.occurrence_path));let context='session-1';
 const local={ensureReady:async input=>{assert.equal(input.scope.document_gid,'2');assert.equal(input.source_selector,document.source_selector);return {visibility_context:context};},readVisibility:async({source_nodes})=>({nodes:source_nodes.map(node=>({source_node_id:node.source_node_id,visible:node.source_node_id==='bolt',visibility_state:node.source_node_id==='bolt'?'visible':'hidden'}))}),executeIntent:async input=>{inputs.push(input);return {ok:true,visible:input.action==='show'};}};
 const adapter=createAdapter({getStore:()=>({state:{workspace}}),getLocalInteraction:()=>local,invoke:async(id,payload)=>{calls.push({id,payload});throw Error('unexpected_source_registration');}});
 const result=await adapter.actOnProductNode({workspaceGid:'1',document,nodeKey:'front',action:'show'});
 assert.equal(result.calibrated,true);assert.equal(result.visible,undefined);assert.equal(inputs.length,0);assert.equal(document.product_tree.nodes[1].visible,true);
 await adapter.actOnProductNode({workspaceGid:'1',document,nodeKey:'front',action:'show'});
 assert.equal(inputs[0].scope.document_gid,'2');assert.equal(inputs[0].scope.expected_workspace_row_version,7);assert.deepEqual(inputs[0].source_nodes[0].occurrence_path,path);
 await adapter.actOnProductNode({workspaceGid:'1',document,nodeKey:'bolt',action:'hide'});
 await adapter.actOnProductNode({workspaceGid:'1',document,nodeKey:'bolt',action:'show'});
 assert.equal(calls.length,0);assert.ok(inputs.every(input=>input.scope.document_gid==='2'&&input.source_selector===document.source_selector));assert.deepEqual(inputs[1].source_nodes[0].occurrence_path,[...path,{occurrence_uid:'bolt',item_revision_uid:'bolt-rev'}]);assert.deepEqual(inputs[2].source_nodes,inputs[1].source_nodes);
 assert.equal(JSON.stringify(document.product_tree.nodes.map(node=>node.occurrence_path)),before,'never rewrite cached revision paths');
 context='session-2';assert.equal((await adapter.actOnProductNode({workspaceGid:'1',document,nodeKey:'front',action:'show'})).calibrated,true);assert.equal(inputs.length,3,'new session recalibrates without writing');
 document.product_tree.nodes.push({node_key:'new-child',occurrence_path:[...path,{occurrence_uid:'new',item_revision_uid:'new-rev'}],visible:true});
 assert.equal((await adapter.actOnProductNode({workspaceGid:'1',document,nodeKey:'new-child',action:'hide'})).calibrated,true);assert.equal(inputs.length,3,'newly expanded cached nodes must be read before accepting an action');assert.equal(document.product_tree.nodes.at(-1).visible,false);
 local.executeIntent=async()=>{throw Error('visibility_calibration_required');};
 await assert.rejects(adapter.actOnProductNode({workspaceGid:'1',document,nodeKey:'front',action:'show'}),/visibility_calibration_required/);assert.ok(document.product_tree.nodes.every(node=>node.visibility_state==='unknown'));
 assert.equal((await adapter.actOnProductNode({workspaceGid:'1',document,nodeKey:'front',action:'show'})).calibrated,true,'rejected pinned context must invalidate the adapter calibration');
});
test('unknown native outcome fences subsequent queued node actions',async()=>{
 let writes=0;const local={state:'ready',ensureReady:async()=>({visibility_context:'session-1'}),readVisibility:async()=>({nodes:[{source_node_id:'n',visible:true,visibility_state:'visible'}]}),executeIntent:async()=>{writes++;local.state='outcome_unknown';throw Error('outcome_unknown');}};
 const adapter=createAdapter({getStore:()=>({state:{workspace:{workspace_gid:'1',row_version:1}}}),getLocalInteraction:()=>local,invoke:()=>{throw Error('unexpected_bind');}});
 const input={workspaceGid:'1',document:{document_gid:'2',source_kind:'teamcenter_online',source_selector:{},product_tree:{nodes:[{node_key:'n',occurrence_path:[{occurrence_uid:'o',item_revision_uid:'r'}]}]}},nodeKey:'n',action:'hide'};
 assert.equal((await adapter.actOnProductNode(input)).calibrated,true);await assert.rejects(adapter.actOnProductNode(input),/outcome_unknown/);await assert.rejects(adapter.actOnProductNode({...input,action:'show'}),/outcome_unknown/);assert.equal(writes,1);
});

test('online node action submits source and operation intent without an existing document session',async()=>{
 let input;const document={document_gid:'2',source_kind:'teamcenter_online',source_selector:{endpoint_id:'ep'},product_tree:{nodes:[{node_key:'n',parent_key:null,has_children:false,occurrence_path:[]}]}};
 const local={ensureReady:async value=>{input=value;return {visibility_context:'session-1'};},readVisibility:async()=>({nodes:[{source_node_id:'n',visible:true,visibility_state:'visible'}]}),executeIntent:async()=>{throw Error('calibration_must_not_write');}};
 const adapter=createAdapter({getStore:()=>({state:{workspace:{workspace_gid:'1',row_version:7}}}),getLocalInteraction:()=>local,invoke:()=>{throw Error('cloud_forbidden');}});
 const result=await adapter.actOnProductNode({workspaceGid:'1',document,nodeKey:'n',action:'hide'});
 assert.equal(result.calibrated,true);assert.equal(document.product_tree.nodes[0].visible,true);assert.equal(input.source_nodes[0].kind,'single_part_root');assert.equal(input.scope.expected_workspace_row_version,7);assert.equal(input.action,'hide');assert.equal(input.source_selector.endpoint_id,'ep');
});

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
