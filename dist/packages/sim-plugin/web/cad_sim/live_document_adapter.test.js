const test = require('node:test');
const assert = require('node:assert/strict');
const { createAdapter } = require('./live_document_adoption');
const session = `sha256:${'a'.repeat(64)}`;
const identity = (id, value = session) => ({ plan_id: id, steps: [{ status: 'succeeded', result: {
  document_session: value, process_id: 42, process_started_utc_ticks: '638000000000000000', document_handle: '2',
} }] });

test('single-part primary source root resolves a fresh sole runtime model, never its cache key',async()=>{
  const writes=[];let changed=false;let treeOptions;
  const document={role:'primary',source_kind:'teamcenter_online',product_tree:{document_session:session,nodes:[{node_key:'tc:sha256:root',parent_key:null,occurrence_path:[],has_children:false}]}};
  const adapter=createAdapter({readIdentity:async()=>identity('proof',changed?`sha256:${'b'.repeat(64)}`:session),
    getStore:()=>({state:{workspace:{workspace_gid:'10'}}}),invoke:async()=>({workspace_gid:'10',document_session:changed?null:session,state:changed?'unbound':'bound'}),
    readTree:async options=>{treeOptions=options;return {steps:[{status:'succeeded',result:{nodes:[{node_key:'1',parent_node_key:null,has_more:true},{node_key:'9',parent_node_key:'1',has_more:false}]}}]}},
    executeNodeAction:async(k,a)=>{writes.push([k,a]);return{visible:a==='show'};}});
  await adapter.actOnProductNode({workspaceGid:'10',document,nodeKey:'tc:sha256:root',action:'hide'});
  assert.deepEqual(writes,[['9','hide']]);
  assert.deepEqual(treeOptions,{max_depth:1,force_refresh:false,expected_document_session:session});
  changed=true;
  await assert.rejects(adapter.actOnProductNode({workspaceGid:'10',document,nodeKey:'tc:sha256:root',action:'show'}),/binding_mismatch/);
});

test('controls reuse a session-scoped root mapping and discard it on session or structure changes',async()=>{
  let currentSession=session, reads=0;
  const writes=[];
  const document={role:'primary',source_kind:'teamcenter_online',product_tree:{nodes:[{node_key:'tc:sha256:root',parent_key:null,occurrence_path:[],has_children:false}]}};
  const adapter=createAdapter({getStore:()=>({state:{workspace:{workspace_gid:'10'}}}),
    invoke:async()=>({workspace_gid:'10',document_session:currentSession,state:'bound'}),
    readTree:async()=>{reads++;return {steps:[{status:'succeeded',result:{nodes:[{node_key:String(reads),parent_node_key:null,has_more:false}]}}]};},
    executeNodeAction:async(k,a,o)=>writes.push([k,a,o.expected_document_session])});
  const act=action=>adapter.actOnProductNode({workspaceGid:'10',document,nodeKey:'tc:sha256:root',action});
  await act('hide'); await act('show'); await act('highlight'); await act('unhighlight');
  assert.equal(reads,1,'all control actions share the mapping');
  assert.deepEqual(writes.map(x=>x[0]),['1','1','1','1']);
  currentSession=`sha256:${'b'.repeat(64)}`;
  await act('hide');
  assert.equal(reads,2);
  assert.deepEqual(writes.at(-1),['2','hide',currentSession]);
  adapter.invalidateControlMappings();
  await act('show');
  assert.equal(reads,3);
  document.product_tree={...document.product_tree};
  await act('highlight');
  assert.equal(reads,4);
});

test('single-part source root rejects ambiguous or truncated native trees before any control',async()=>{
  for(const nodes of [[{node_key:'1',parent_node_key:null,has_more:true}],
    [{node_key:'1',parent_node_key:null,has_more:true},{node_key:'2',parent_node_key:'1',has_more:false},{node_key:'3',parent_node_key:'1',has_more:false}]]){
    const adapter=createAdapter({readIdentity:async()=>identity('proof'),getStore:()=>({state:{workspace:{workspace_gid:'10'}}}),
      invoke:async()=>({workspace_gid:'10',document_session:session,state:'bound'}),readTree:async()=>({steps:[{status:'succeeded',result:{nodes}}]}),executeNodeAction:()=>assert.fail('must not control ambiguous model')});
    await assert.rejects(adapter.actOnProductNode({workspaceGid:'10',document:{role:'primary',source_kind:'teamcenter_online',product_tree:{nodes:[{node_key:'tc:sha256:root',parent_key:null,occurrence_path:[],has_children:false}]}},nodeKey:'tc:sha256:root',action:'hide'}),/model_node_runtime_identity_unavailable/);
  }
});

test('confirmed reconnect preserves snapshots and never reads model or AH structure', async () => {
  const reopened = `sha256:${'b'.repeat(64)}`, calls=[];
  const workspace={workspace_gid:'10',row_version:4,name:'cached environment'};
  const adapter=createAdapter({readIdentity:async()=>identity('proof',reopened),getDisplayName:()=> 'same',
    getStore:()=>({state:{workspace}}),confirmRebind:async()=>true,
    readTree:()=>assert.fail('reconnect must not read tree'),readHierarchyInventory:()=>assert.fail('must not read AH'),
    refreshWorkspace:()=>assert.fail('must not force-refresh projections'),
    invoke:async(cap,payload,options)=>{
      calls.push([cap,payload,options]);
      if(cap.endsWith('binding.get')) return {workspace_gid:'10',document_session:session,state:'bound'};
      return {workspace_gid:'10',document_session:reopened,workspace_row_version:5,cache_revision_hash:'new',state:'bound'};
    }});
  const result=await adapter.reconnectDocument('10');
  assert.equal(result.document_session,reopened);
  assert.equal(result.structure_verification,'unverified');
  assert.equal(calls.at(-1)[1].expected_document_session,session);
  assert.equal(calls.at(-1)[2].confirmation,true);
  assert.equal(workspace.row_version,5);
});

test('reconnect cancellation and selection or document changes prevent binding writes', async () => {
  for(const scenario of ['cancel','selection','document']) {
    const workspace={workspace_gid:'10',row_version:4}; let currentSession=`sha256:${'b'.repeat(64)}`;
    const adapter=createAdapter({readIdentity:async()=>identity('proof',currentSession),getDisplayName:()=> 'same',
      getStore:()=>({state:{workspace}}),confirmRebind:async()=>{
        if(scenario==='selection') workspace.workspace_gid='11';
        if(scenario==='document') currentSession=`sha256:${'c'.repeat(64)}`;
        return scenario!=='cancel';
      },invoke:async cap=>{
        assert.ok(cap.endsWith('binding.get'),'no binding write after stale confirmation');
        return {workspace_gid:'10',document_session:session,state:'bound'};
      }});
    await assert.rejects(adapter.reconnectDocument('10'),/cancelled|selection_changed|session_changed/);
  }
});

test('dismissal after committed reconnect reconciles versions but does not refresh snapshots',async()=>{
  const reopened=`sha256:${'b'.repeat(64)}`,workspace={workspace_gid:'10',row_version:4};let current=true;
  const adapter=createAdapter({readIdentity:async()=>identity('proof',reopened),getStore:()=>({state:{workspace}}),
    confirmRebind:()=>true,invoke:async cap=>{
      if(cap.endsWith('binding.get')) return {workspace_gid:'10',document_session:session,state:'bound'};
      current=false;return {workspace_gid:'10',document_session:reopened,workspace_row_version:5,cache_revision_hash:'new'};
    }});
  await assert.rejects(adapter.reconnectDocument('10',{isCurrent:()=>current}),/document_selection_changed/);
  assert.equal(workspace.row_version,5);assert.equal(workspace.cache_revision_hash,'new');
});

test('reconnect rejects a different active window even when its identity is internally consistent',async()=>{
  const adapter=createAdapter({getNativeView:()=>({listDocuments:async()=>[{key:'vmwin:other',current:true}],status:async()=>({pid:42})}),
    readIdentity:async()=>identity('proof'),invoke:()=>assert.fail('wrong window must not reach binding'),
    getStore:()=>({state:{workspace:{workspace_gid:'10',row_version:4}}})});
  await assert.rejects(adapter.reconnectDocument('10',{expectedWindowKey:'vmwin:chosen'}),/document_window_identity_changed/);
});
test('cached node actions verify session and binding without rereading the tree',async()=>{
  const writes=[];let currentSession=session;
  const document={product_tree:{document_session:session,nodes:[{node_key:'7',name:'same'},{node_key:'8',name:'same'}]}};
  const adapter=createAdapter({readIdentity:async()=>identity('proof',currentSession),getDisplayName:()=> 'same',
    getStore:()=>({state:{workspace:{workspace_gid:'10'}}}),
    invoke:async()=>({workspace_gid:'10',document_session:currentSession}),
    readTree:()=>assert.fail('must not rescan'),executeNodeAction:async(k,a)=>{writes.push([k,a]);return{ok:true,visible:true};}});
  await adapter.actOnProductNode({workspaceGid:'10',document,nodeKey:'8',action:'show'});
  assert.deepEqual(writes,[['8','show']]);
  currentSession=`sha256:${'b'.repeat(64)}`;
  await assert.rejects(adapter.actOnProductNode({workspaceGid:'10',document,nodeKey:'8',action:'hide'}),/model_node_relocation_required/);
  assert.equal(writes.length,1);
});

test('bound Teamcenter online nodes use their occurrence key without a live-tree session',async()=>{
  const writes=[];
  const document={source_kind:'teamcenter_online',product_tree:{source:'teamcenter_children',nodes:[
    {node_key:'tc:occurrence-42',occurrence_id:'occurrence-42',name:'Part/01'}]}};
  const adapter=createAdapter({readIdentity:async()=>identity('proof'),
    getStore:()=>({state:{workspace:{workspace_gid:'10'}}}),
    invoke:async cap=>{
      assert.ok(cap.endsWith('binding.get'));
      return {workspace_gid:'10',document_session:session,state:'bound'};
    },
    readTree:()=>assert.fail('must not rescan'),executeNodeAction:async(k,a)=>{writes.push([k,a]);return{visible:false};}});
  await adapter.actOnProductNode({workspaceGid:'10',document,nodeKey:'tc:occurrence-42',action:'hide'});
  assert.deepEqual(writes,[['tc:occurrence-42','hide']]);
});

test('bound Teamcenter online nodes use the raw PLM occurrence control key, not the cached path hash',async()=>{
  const writes=[];
  const document={source_kind:'teamcenter_online',product_tree:{source:'teamcenter_children',nodes:[
    {node_key:'tc:sha256:cached-path',occurrence_id:'sha256:cached-path',control_key:'tc:plm-instance-42',name:'Part/01'}]}};
  const adapter=createAdapter({readIdentity:async()=>identity('proof'),
    getStore:()=>({state:{workspace:{workspace_gid:'10'}}}),
    invoke:async()=>({workspace_gid:'10',document_session:session,state:'bound'}),
    executeNodeAction:async(k,a)=>{writes.push([k,a]);return{visible:false};}});
  await adapter.actOnProductNode({workspaceGid:'10',document,nodeKey:'tc:sha256:cached-path',action:'hide'});
  assert.deepEqual(writes,[['tc:plm-instance-42','hide']]);
});

test('bound Teamcenter online nodes never send a cached path hash to VisMockup',async()=>{
  const writes=[];
  const document={source_kind:'teamcenter_online',product_tree:{source:'teamcenter_children',nodes:[
    {node_key:'tc:sha256:cached-path',occurrence_id:'sha256:cached-path',name:'Part/01'}]}};
  const adapter=createAdapter({readIdentity:async()=>identity('proof'),
    getStore:()=>({state:{workspace:{workspace_gid:'10'}}}),
    invoke:async()=>({workspace_gid:'10',document_session:session,state:'bound'}),
    executeNodeAction:async(k,a)=>{writes.push([k,a]);return{visible:false};}});
  await assert.rejects(
    adapter.actOnProductNode({workspaceGid:'10',document,nodeKey:'tc:sha256:cached-path',action:'hide'}),
    /model_node_runtime_identity_unavailable/);
  assert.deepEqual(writes,[]);
});

test('bound Teamcenter online nodes recover the raw locator from occurrence path',async()=>{
  const writes=[];
  const document={source_kind:'teamcenter_online',product_tree:{source:'teamcenter_children',nodes:[
    {node_key:'tc:sha256:cached-path',occurrence_id:'sha256:cached-path',
      occurrence_path:[{occurrence_uid:'parent-instance'},{occurrence_uid:'leaf-instance'}],name:'Part/01'}]}};
  const adapter=createAdapter({readIdentity:async()=>identity('proof'),
    getStore:()=>({state:{workspace:{workspace_gid:'10'}}}),
    invoke:async()=>({workspace_gid:'10',document_session:session,state:'bound'}),
    executeNodeAction:async(k,a,options)=>{writes.push([k,a,options]);return{visible:true};}});
  await adapter.actOnProductNode({workspaceGid:'10',document,nodeKey:'tc:sha256:cached-path',action:'show'});
  assert.deepEqual(writes,[['tc:leaf-instance','show',{
    expected_document_session:session,
    occurrence_path:document.product_tree.nodes[0].occurrence_path
  }]]);
});

test('reopened document uses the cached instance locator, not the old handle or same-name sibling',async()=>{
  const reopened=`sha256:${'b'.repeat(64)}`, writes=[];
  const keyA=`cad:${'1'.repeat(64)}`,keyB=`cad:${'2'.repeat(64)}`;
  const document={product_tree:{document_session:session,nodes:[
    {node_key:'7',name:'Bolt/01',control_key:keyA}, {node_key:'8',name:'Bolt/01',control_key:keyB}]}};
  const adapter=createAdapter({readIdentity:async()=>identity('proof',reopened),
    getStore:()=>({state:{workspace:{workspace_gid:'10'}}}),
    invoke:async()=>({workspace_gid:'10',document_session:reopened}),
    readTree:()=>assert.fail('must not rescan'),executeNodeAction:async(k,a)=>writes.push([k,a])});
  await adapter.actOnProductNode({workspaceGid:'10',document,nodeKey:'8',action:'hide'});
  assert.deepEqual(writes,[[keyB,'hide']]);
  assert.equal(document.product_tree.document_session,session,'mapping must not mark the old snapshot fresh');
  document.product_tree.nodes[1].control_key='cad:invalid';
  await assert.rejects(adapter.actOnProductNode({workspaceGid:'10',document,nodeKey:'8',action:'show'}),/model_node_relocation_required/);
  assert.equal(writes.length,1);
});

test('overlapping reads share one operation but a later refresh still reads live state', async () => {
  let calls = 0, finish;
  const adapter = createAdapter({ readIdentity: async () => identity('op'),
    invoke: async () => ({ workspace_gid: '10', document_session: session }),
    readTree: () => { calls++; return new Promise(resolve => { finish = resolve; }); } });
  const one = adapter.readProductTree('10');
  const two = adapter.readProductTree('10');
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(calls, 1);
  finish({ steps: [{ status: 'succeeded', result: { nodes: [] } }] });
  await Promise.all([one, two]);
  const later = adapter.readProductTree('10');
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(calls, 2);
  finish({ steps: [{ status: 'succeeded', result: { nodes: [] } }] });
  await later;
});

test('live model tree keeps distinct same-name nodes and checks the environment binding', async () => {
  const adapter = createAdapter({ readIdentity: async () => identity('op'), getDisplayName: () => 'W10',
    getNativeView: () => ({ listDocuments: () => { throw new Error('native_view_unavailable'); } }),
    invoke: async () => ({ workspace_gid: '10', document_session: session }),
    readTree: async () => ({ steps: [{ status: 'succeeded', result: { nodes: [
      { node_key: '1', parent_node_key: null, name: 'root', has_more: true },
      { node_key: '2', parent_node_key: '1', name: 'same', has_more: false },
      { node_key: '3', parent_node_key: '1', name: 'same', has_more: true },
    ] } }] }) });
  const tree = await adapter.readProductTree('10');
  assert.equal(tree.node_count, 3);
  assert.equal(tree.nodes[2].parent_key, '1');
  assert.equal(tree.complete, false);
  assert.equal(tree.document_session, session);
  await assert.rejects(adapter.readProductTree('11'), /document_environment_binding_mismatch/);
});

test('live model tree rejects results after a document switch', async () => {
  let reads = 0;
  const adapter = createAdapter({ readIdentity: async () => identity('op', ++reads === 1 ? session : `sha256:${'b'.repeat(64)}`),
    getDisplayName: () => 'same name', invoke: async () => ({ workspace_gid: '10', document_session: session }),
    readTree: async () => ({ steps: [{ status: 'succeeded', result: { nodes: [] } }] }) });
  await assert.rejects(adapter.readProductTree('10'), /document_session_changed/);
});

test('manual refresh explicitly rebinds a reopened document before reading its tree', async () => {
  const oldSession=`sha256:${'a'.repeat(64)}`,newSession=`sha256:${'b'.repeat(64)}`;
  const calls=[];
  const adapter=createAdapter({
    readIdentity:async()=>identity('plan-new',newSession),
    readTree:async()=>({steps:[{status:'succeeded',result:{nodes:[{node_key:'7',parent_node_key:null,name:'Root'}]}}]}),
    invoke:async(cap,payload)=>{
      calls.push([cap,payload]);
      if(cap.endsWith('binding.get')) return {workspace_gid:'10',document_session:oldSession,state:'bound'};
      if(cap.endsWith('rebind')) return {workspace_gid:'10',document_session:newSession,state:'bound'};
      throw Error('unexpected capability');
    },
    getStore:()=>({state:{workspace:{workspace_gid:'10',row_version:4}}}),
    confirmRebind:()=>true,
  });

  const tree=await adapter.readProductTree('10',{allowRebind:true});

  assert.equal(tree.node_count,1);
  assert.deepEqual(calls[0],['simulation.environment.live_document.binding.get',{workspace_gid:'10'}]);
  assert.equal(calls[1][0],'simulation.environment.live_document.rebind');
  assert.equal(calls[1][1].expected_document_session,oldSession);
  assert.equal(calls[1][1].identity_operation_id,'plan-new');
  assert.equal(calls[1][1].expected_workspace_row_version,4);
});

test('manual refresh cancellation never reads or rebinds the current document', async () => {
  const oldSession=`sha256:${'a'.repeat(64)}`,newSession=`sha256:${'b'.repeat(64)}`;
  let treeReads=0,rebinds=0;
  const adapter=createAdapter({
    readIdentity:async()=>identity('plan-new',newSession),
    readTree:async()=>{treeReads++;return {steps:[{status:'succeeded',result:{nodes:[]}}]};},
    invoke:async cap=>{
      if(cap.endsWith('binding.get')) return {workspace_gid:'10',document_session:oldSession,state:'bound'};
      if(cap.endsWith('rebind')) rebinds++;
    },
    getStore:()=>({state:{workspace:{workspace_gid:'10',row_version:4}}}),
    confirmRebind:()=>false,
  });

  await assert.rejects(adapter.readProductTree('10',{allowRebind:true}),/document_session_changed/);
  assert.equal(treeReads,0);assert.equal(rebinds,0);
});

test('adoption sends a fresh operation reference plus descriptive document name to governed backend', async () => {
  const calls = [];
  let reads = 0;
  const adapter = createAdapter({ readIdentity: async () => identity(`op-${++reads}`),
    getDisplayName: () => '同名产品', getStore: () => ({}),
    invoke: async (...args) => { calls.push(args); return { state: 'importing' }; } });
  const document = await adapter.readCurrentDocument();
  assert.equal(document.display_name, '同名产品');
  await adapter.adopt({ document, name: '环境', operation_key: 'stable-key' });
  assert.equal(reads, 2);
  assert.deepEqual(calls, [['simulation.environment.live_document.adopt', {
    identity_operation_id: 'op-2', name: '环境', document_display_name: '同名产品', idempotency_key: 'stable-key',
  }, { version: 2, idempotency: true, idempotencyKey: 'stable-key' }]]);
});

test('opening an adopted environment force-refreshes its model documents even when workspace id is unchanged', async () => {
  const calls = [];
  const store = { state: { workspace: { workspace_gid: '10' } },
    openWorkspace: async gid => { calls.push(['open', gid]); return store.state.workspace; } };
  const adapter = createAdapter({ readIdentity: async () => identity('op'), invoke: async () => ({}),
    getDisplayName: () => 'W10', getStore: () => store,
    refreshWorkspace: async workspace => calls.push(['refresh', workspace.workspace_gid]) });
  await adapter.openWorkspace('10');
  assert.deepEqual(calls, [['open', '10'], ['refresh', '10']]);
});

test('document switch between opening dialog and confirming prevents adoption', async () => {
  let reads = 0;
  const adapter = createAdapter({ readIdentity: async () => identity('op', ++reads === 1 ? session : `sha256:${'b'.repeat(64)}`),
    getDisplayName: () => '同名产品', getStore: () => ({}), invoke: () => assert.fail('must not write') });
  const document = await adapter.readCurrentDocument();
  await assert.rejects(adapter.adopt({ document, name: '环境', operation_key: 'key' }), /document_session_changed/);
});

test('missing identity or failed native step cannot become a trusted document', async () => {
  for (const outcome of [{}, { ...identity('op'), steps: [{ status: 'failed', result: { document_session: session } }] }]) {
    const adapter = createAdapter({ readIdentity: async () => outcome,
      getDisplayName: () => '产品', getStore: () => ({}), invoke: () => assert.fail('must not write') });
    await assert.rejects(adapter.readCurrentDocument(), /document_identity_unavailable/);
  }
});

test('selection forwards current-intent guard into the actual environment store', async () => {
  const calls = [], guard = () => true;
  const adapter = createAdapter({ readIdentity: async () => identity('op'), getDisplayName: () => '产品',
    getStore: () => ({ openWorkspace: async (...args) => calls.push(args) }), invoke: () => {} });
  await adapter.openWorkspace('123', { isCurrent: guard });
  assert.equal(calls[0][0], '123');
  assert.equal(calls[0][1].isCurrent, guard);
});

test('native window and Connector process must remain correlated across identity read', async () => {
  for (const changed of ['window', 'process', 'none']) {
    let reads = 0;
    const adapter = createAdapter({ getNativeView: () => ({ status: async () => ({ pid: 42 }),
      listDocuments: async () => [{ key: ++reads > 1 && changed === 'window' ? 'vmwin:2' : 'vmwin:1', current: true }] }),
      readIdentity: async () => { const outcome = identity('op'); if (changed === 'process') outcome.steps[0].result.process_id = 99; return outcome; },
      getDisplayName: () => 'model', getStore: () => ({}), invoke: () => {},
    });
    if (changed === 'none') assert.equal((await adapter.readCurrentDocument()).native_window_key, 'vmwin:1');
    else await assert.rejects(adapter.readCurrentDocument(), /document_window_identity_changed/);
  }
});

test('alternate hierarchies are read and applied in bounded cursor pages', async () => {
  const calls = [];
  const pages = [
    { plan_id: 'inventory-0', steps: [{ status: 'succeeded', result: { document_session: session,
      start_index: 0, next_index: 4, total_hierarchies: 5, hierarchies: [{}, {}, {}, {}] } }] },
    { plan_id: 'inventory-4', steps: [{ status: 'succeeded', result: { document_session: session,
      start_index: 4, next_index: null, total_hierarchies: 5, hierarchies: [{}] } }] },
  ];
  const adapter = createAdapter({ readIdentity: async () => identity('identity'), getDisplayName: () => '产品',
    getStore: () => ({}), readHierarchyInventory: async payload => { calls.push(['read', payload]); return pages.shift(); },
    invoke: async (id, payload, options) => { calls.push([id, payload, options]);
      const start = Number(payload.idempotency_key.split(':').at(-1));
      return { imported_hierarchy_count: start ? 1 : 4, total_hierarchies: 5,
        next_index: start ? null : 4, complete: Boolean(start) };
    } });
  const progress = [];
  const result = await adapter.importHierarchies({ document: { document_session: session }, workspace_gid: '10',
    operation_key: 'adopt-key', onProgress: value => progress.push(value) });
  assert.deepEqual(result, { imported: 5, total: 5 });
  assert.equal(calls.filter(item => item[0] === 'read').length, 2);
  assert.equal(calls[1][0], 'simulation.environment.live_document.inventory.apply');
  assert.equal(calls[1][1].inventory_operation_id, 'inventory-0');
  assert.deepEqual(progress.at(-1), { imported: 5, total: 5, complete: true });
});
