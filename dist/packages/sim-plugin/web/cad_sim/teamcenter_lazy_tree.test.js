const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {JSDOM}=require('jsdom');
const tick=()=>new Promise(r=>setImmediate(r));
function page(){
  const dom=new JSDOM('<div id="modelDocumentList"></div>',{runScripts:'outside-only'});
  for(const file of ['model_document_collection.js','teamcenter_online_source.js','tree_projection_cache.js','cad_sim.js']) vm.runInContext(fs.readFileSync(path.join(__dirname,file),'utf8'),dom.getInternalVMContext());
  return dom;
}
test('local open completes in Main without independent identity, scope or workspace refresh',async()=>{
 const dom=page();await tick();
 vm.runInContext(`
  window.__calls=[];window._localViewerInteractionEnabled=async()=>true;
  window._openLocalViewerFromLaunch=async input=>{__calls.push(['local',input]);return {interaction_id:'opaque',workspace_row_version:5,document_gid:'2',document_session:'new-session'};};
  window._simulationEnvironmentWorkspace={store:{state:{workspace:{workspace_gid:'10',row_version:4}},openWorkspace:async()=>{throw Error('blocking_refresh');},applyOpenedDocument:()=>true}};
  _requireTeamcenterLogin=async()=>({state:'ready'});_cmdShow=()=>{};
  _requestVisMockupCommand=async(id,payload,options)=>{__calls.push([id,payload,options]);if(!id.endsWith('visualization.launch.request'))throw Error('independent_identity_forbidden');return {plan_id:'launch-v2',steps:[{status:'succeeded',result:{protocol:'ai00.viewer.opened-source.v1',launch:{launch_id:'l'},document_identity:{document_session:'new-session'}}}]};};
  _attachNativeViewport=async()=>{throw Error('legacy_attach');};
  _invokeCapability=async()=>{throw Error('redundant_cloud_call');};
  window.__pending=_openTeamcenterOnlineDocument({document_gid:'2',role:'primary',source_kind:'teamcenter_online',source_selector:{object_uid:'o'}},'new');
 `,dom.getInternalVMContext());
 await dom.window.__pending;
 const calls=JSON.parse(JSON.stringify(dom.window.__calls));
 assert.equal(calls[0][2].version,2);assert.equal(calls.length,2);
 assert.deepEqual(calls[1][1],{workspace_gid:'10',document_gid:'2',launch_operation_id:'launch-v2',expected_workspace_row_version:4,idempotency_key:'online-live-bind-launch-v2-2'});
 assert.equal(calls[1][0],'local');dom.window.close();
});
async function setup(){
  const dom=page();await tick();
  vm.runInContext(`
    _modelDocumentCollection=window.AI00ModelDocumentCollection.createCollection();
    window._simulationEnvironmentWorkspace={store:{state:{workspace:{workspace_gid:'10'}}}};
    window.__calls=[];
    window.__node=(id,parent,path,has=true)=>({occurrence_id:id,parent_occurrence_id:parent,occurrence_path:path,has_children:has,name:id,depth:path.length,child_order:0});
    window.__root=__node('root',null,[]);window.__child=__node('child','root',[{occurrence_uid:'edge',item_revision_uid:'rev'}],null);
    window.__page=(parent,nodes,cursor=0,next=null)=>({parent,nodes,cursor,next_cursor:next,child_count:nodes.length,complete:false,generation:'a'.repeat(32),source_identity_hash:'identity',captured_at:'2026-09-16',cache_hit:true});
    window.__doc={document_gid:'2',role:'primary',source_kind:'teamcenter_online',source_identity_hash:'identity',source_selector:{object_uid:'object'},media_type:'application/vnd.siemens.teamcenter.visualization-document'};
    _invokeCapability=async()=>({items:[{...__doc}]});
    _requestVisMockupCommand=async(id,payload)=>{__calls.push([id,payload]);if(!payload.parent_path.length)return{steps:[{result:__page(__root,[__child])}]};return new Promise((resolve,reject)=>{window.__resolve=resolve;window.__reject=reject;});};
    window.__pending=_refreshModelDocuments({workspace_gid:'10'},{useCache:true});
  `,dom.getInternalVMContext());
  await dom.window.__pending;return dom;
}
test('initial children browse renders root plus direct child, unknown disclosure and disabled visibility',async()=>{
  const dom=await setup(),d=dom.window.document;
  assert.equal(dom.window.__calls.length,1);assert.match(dom.window.__calls[0][0],/children.read.request$/);
  assert.equal(d.querySelectorAll('.cs-alternate-tree-item').length,2);
  assert.equal(d.querySelectorAll('.cs-alternate-tree-toggle')[1].disabled,false);
  assert.equal(vm.runInContext(`_modelDocumentCollection.state.documents[0].product_tree.nodes.find(node=>node.occurrence_id==='child').control_key`,dom.getInternalVMContext()),'tc:edge');
  assert.ok([...d.querySelectorAll('input')].every(x=>x.disabled));
  assert.equal(d.querySelector('.cs-model-document-tree').classList.contains('hidden'),false);dom.window.close();
});
test('bound embedded Teamcenter tree enables occurrence visibility controls',async()=>{
  const dom=await setup(),d=dom.window.document;
  vm.runInContext(`window._actOnModelNode=async()=>({visible:false});window._liveDocumentContextUnavailable=false;_setVmDocumentReady(true);_renderModelDocuments(_modelDocumentCollection.state.documents);`,dom.getInternalVMContext());
  const documentToggle=d.querySelector('.cs-model-document-toggle');
  if(d.querySelector('.cs-model-document-tree').classList.contains('hidden'))documentToggle.click();
  const checks=[...d.querySelectorAll('.cs-alternate-tree-check')];
  assert.ok(checks.length>=1);
  assert.ok(checks.every(check=>!check.disabled));
  dom.window.close();
});

test('visibility tooltip describes the selected local or cloud route',async()=>{
  const dom=await setup();
  try {
    for(const local of [false,true]){
      vm.runInContext(`window._actOnModelNode=async()=>({visible:false});window._localViewerInteraction=()=>${local?'({})':'null'};_renderModelDocuments(_modelDocumentCollection.state.documents);`,dom.getInternalVMContext());
      if(dom.window.document.querySelector('.cs-model-document-tree').classList.contains('hidden'))dom.window.document.querySelector('.cs-model-document-toggle').click();
      const check=dom.window.document.querySelector('.cs-alternate-tree-check');
      assert.equal(check.title,local?'显示 / 隐藏（本地交互会话）':'显示 / 隐藏（操作前核对文档绑定）');
    }
  }finally{dom.window.close();}
});

test('single-part synthetic root reaches verified node control instead of empty child fanout',async()=>{
  const dom=await setup();
  vm.runInContext(`const doc=_modelDocumentCollection.state.documents[0];doc.product_tree.nodes=doc.product_tree.nodes.filter(n=>n.parent_key==null);doc.product_tree.nodes[0].has_children=false;
    window.__actions=[];window._actOnModelNode=async args=>{__actions.push(args.action);return{visible:true};};_renderModelDocuments([doc]);
    document.querySelector('.cs-model-document-toggle').click();`,dom.getInternalVMContext());
  dom.window.document.querySelector('.cs-alternate-tree-check').click();await tick();await tick();
  assert.deepEqual(Array.from(dom.window.__actions),['show']);dom.window.close();
});

test('Teamcenter occurrence controls stay actionable while runtime binding is checked on click',async()=>{
  const dom=await setup(),d=dom.window.document;
  vm.runInContext(`window._actOnModelNode=async()=>({visible:false});window._liveDocumentContextUnavailable=true;_setVmDocumentReady(false);for(const node of _modelDocumentCollection.state.documents[0].product_tree.nodes)delete node.control_key;_renderModelDocuments(_modelDocumentCollection.state.documents);`,dom.getInternalVMContext());
  const documentToggle=d.querySelector('.cs-model-document-toggle');
  if(d.querySelector('.cs-model-document-tree').classList.contains('hidden'))documentToggle.click();
  const checks=[...d.querySelectorAll('.cs-alternate-tree-check')];
  assert.ok(checks.length>=1);
  assert.ok(checks.every(check=>!check.disabled));
  assert.equal(vm.runInContext(`_modelDocumentCollection.state.documents[0].product_tree.nodes.find(node=>node.occurrence_id==='child').control_key`,dom.getInternalVMContext()),'tc:edge');
  dom.window.close();
});
test('old cached Teamcenter node refreshes its parent and uses the recovered raw occurrence locator',async()=>{
  const dom=await setup(),d=dom.window.document;
  vm.runInContext(`
    const stored=_modelDocumentCollection.state.documents[0].product_tree.nodes.find(node=>node.occurrence_id==='child');
    delete stored.occurrence_path;stored.control_key='tc:sha256:cached-path';
    window.__actions=[];
    window._actOnModelNode=async({document,nodeKey,action})=>{
      const current=document.product_tree.nodes.find(node=>String(node.node_key)===String(nodeKey));
      __actions.push([current.control_key,action]);return{visible:true};
    };
    const cachedNode=AI00ModelDocumentCollection.buildProductForest(_modelDocumentCollection.state.documents[0].product_tree.nodes)
      .flatMap(node=>[node,...node.children]).find(node=>node.occurrence_id==='child');
    window.__cachedRow=_buildProductTreeItem(cachedNode,'2');document.body.append(__cachedRow);
  `,dom.getInternalVMContext());
  dom.window.__cachedRow.querySelector('.cs-alternate-tree-check').click();await tick();await tick();
  assert.deepEqual(JSON.parse(JSON.stringify(dom.window.__actions)),[['tc:edge','show']]);
  assert.equal(dom.window.__calls.length,2,'one targeted Teamcenter refresh should recover the locator');
  dom.window.close();
});
test('old cached Teamcenter node with a raw control key still recovers its empty occurrence path',async()=>{
  const dom=await setup(),d=dom.window.document;
  vm.runInContext(`
    const stored=_modelDocumentCollection.state.documents[0].product_tree.nodes.find(node=>node.occurrence_id==='child');
    stored.occurrence_path=[];stored.control_key='tc:edge';
    window.__actions=[];
    window._actOnModelNode=async({document,nodeKey,action})=>{
      const current=document.product_tree.nodes.find(node=>String(node.node_key)===String(nodeKey));
      __actions.push([current.control_key,current.occurrence_path,action]);return{visible:true};
    };
    const cachedNode=AI00ModelDocumentCollection.buildProductForest(_modelDocumentCollection.state.documents[0].product_tree.nodes)
      .flatMap(node=>[node,...node.children]).find(node=>node.occurrence_id==='child');
    window.__cachedRow=_buildProductTreeItem(cachedNode,'2');document.body.append(__cachedRow);
  `,dom.getInternalVMContext());
  dom.window.__cachedRow.querySelector('.cs-alternate-tree-check').click();await tick();await tick();
  assert.deepEqual(JSON.parse(JSON.stringify(dom.window.__actions)),[[
    'tc:edge',[{occurrence_uid:'edge',item_revision_uid:'rev'}],'show',
  ]]);
  assert.equal(dom.window.__calls.length,2,'a raw control key must not bypass recovery of a missing occurrence path');
  dom.window.close();
});
test('expansion deduplicates; collapse during loading persists; failure retains nodes and retry',async()=>{
  const dom=await setup(),d=dom.window.document;
  const toggle=d.querySelectorAll('.cs-alternate-tree-toggle')[1];
  assert.ok(toggle);toggle.click();toggle.click();toggle.click();toggle.click();
  assert.equal(dom.window.__calls.length,2);
  dom.window.__reject(Error('read failed'));await tick();
  assert.match(d.body.textContent,/read failed/);assert.match(d.body.textContent,/child/);
  assert.equal(toggle.parentElement.nextElementSibling.classList.contains('hidden'),true);
  toggle.click();d.querySelector('[data-tc-retry]').click();
  assert.equal(dom.window.__calls.length,3);
  dom.window.__resolve({steps:[{result:dom.window.__page(dom.window.__child,[])}]});await tick();dom.window.close();
});
test('late child response cannot mutate a replaced source',async()=>{
  const dom=await setup(),d=dom.window.document;
  assert.ok(d.querySelectorAll('.cs-alternate-tree-toggle')[1]);d.querySelectorAll('.cs-alternate-tree-toggle')[1].click();
  vm.runInContext(`_modelDocumentCollection.replace([{...__doc,source_selector:{object_uid:'other'}}]);`,dom.getInternalVMContext());
  dom.window.__resolve({steps:[{result:dom.window.__page(dom.window.__child,[dom.window.__node('late','child',[],false)])}]});await tick();
  assert.doesNotMatch(d.body.textContent,/late/);dom.window.close();
});
test('load more pins generation, preserves siblings and does not drain pages',async()=>{
  const dom=await setup(),d=dom.window.document;
  const toggle=d.querySelectorAll('.cs-alternate-tree-toggle')[1];toggle.click();
  const grand=dom.window.__node('grand','child',[{occurrence_uid:'edge',item_revision_uid:'rev'},{occurrence_uid:'g',item_revision_uid:'r'}],false);
  dom.window.__resolve({steps:[{result:dom.window.__page(dom.window.__child,[grand],0,1)}]});await tick();
  assert.equal(dom.window.__calls.length,2);d.querySelector('[data-tc-more]').click();
  assert.equal(dom.window.__calls[2][1].generation,'a'.repeat(32));assert.equal(dom.window.__calls[2][1].cursor,1);
  dom.window.__reject(Error('temporary'));await tick();assert.match(d.body.textContent,/grand/);
  d.querySelector('[data-tc-retry]').click();
  const sibling={...grand,occurrence_id:'sibling',name:'sibling'};
  dom.window.__resolve({steps:[{result:dom.window.__page(dom.window.__child,[sibling],1,null)}]});await tick();
  assert.match(d.body.textContent,/grand/);assert.match(d.body.textContent,/sibling/);assert.equal(d.querySelector('[data-tc-more]'),null);dom.window.close();
});
test('loading more persists the expanded Teamcenter projection cache',async()=>{
  const dom=await setup(),d=dom.window.document;
  dom.window.__cacheWrites=[];
  dom.window.electronAPI={simulationTreeCache:{put:async(workspace,kind,data)=>{
    dom.window.__cacheWrites.push({workspace,kind,data:JSON.parse(JSON.stringify(data))});
  }}};
  const toggle=d.querySelectorAll('.cs-alternate-tree-toggle')[1];toggle.click();
  const grand=dom.window.__node('grand','child',[{occurrence_uid:'edge',item_revision_uid:'rev'},{occurrence_uid:'g',item_revision_uid:'r'}],false);
  dom.window.__resolve({steps:[{result:dom.window.__page(dom.window.__child,[grand],0,1)}]});await tick();
  assert.equal(dom.window.__cacheWrites.length,1);
  assert.equal(dom.window.__cacheWrites[0].workspace,'10');
  assert.equal(dom.window.__cacheWrites[0].kind,'models');
  assert.ok(dom.window.__cacheWrites[0].data.items[0].product_tree.nodes.some(node=>node.node_key==='tc:grand'));
  dom.window.close();
});
test('restored unloaded expansion does not fetch descendants and environment switch fences pending work',async()=>{
  const dom=await setup(),d=dom.window.document;
  vm.runInContext(`
    const host=document.getElementById('modelDocumentList');
    host._viewState={expanded:['doc:2','product:2:tc:root','product:2:tc:child']};
    _renderModelDocuments(_modelDocumentCollection.state.documents);
    window.AI00TreeProjectionCache.bindView(host,null,{workspaceGid:'10',kind:'models',viewState:host._viewState});
  `,dom.getInternalVMContext());
  assert.equal(dom.window.__calls.length,1);
  const child=d.querySelectorAll('.cs-alternate-tree-toggle')[1];assert.ok(child);
  assert.equal(child.parentElement.nextElementSibling.classList.contains('hidden'),true);child.click();
  vm.runInContext(`window.__switch=_refreshModelDocuments(null);`,dom.getInternalVMContext());await dom.window.__switch;
  dom.window.__resolve({steps:[{result:dom.window.__page(dom.window.__child,[])}]});await tick();
  assert.equal(d.querySelectorAll('.cs-alternate-tree-item').length,0);dom.window.close();
});
test('add binds then browses, and failed first read leaves a registered document with retry',async()=>{
  const dom=page();await tick();
  vm.runInContext(`
    _modelDocumentCollection=window.AI00ModelDocumentCollection.createCollection();window.__calls=[];
    const workspace={workspace_gid:'10',row_version:1};
    window._simulationEnvironmentWorkspace={store:{state:{workspace},openWorkspace:async()=>{}}};
    _requireTeamcenterLogin=async()=>({});_teamcenterSourceDialog=async()=>({display_name:'Online',insertion_instance_id:'once',source_selector:{object_uid:'o'}});
    _cmdShow=()=>{};
    _invokeCapability=async(id)=>{__calls.push(id);return id.endsWith('.bind')?{document_gid:'2'}:{items:[{document_gid:'2',role:'primary',source_kind:'teamcenter_online',source_selector:{object_uid:'o'},media_type:'application/vnd.siemens.teamcenter.visualization-document'}]};};
    _requestVisMockupCommand=async(id)=>{__calls.push(id);throw Error('offline');};
    window.__pending=_addTeamcenterSource();
  `,dom.getInternalVMContext());await dom.window.__pending;
  assert.deepEqual([...dom.window.__calls],['simulation.environment.online_source.bind','simulation.environment.model_document.search','simulation.teamcenter.product_structure.children.read.request']);
  assert.ok(dom.window.document.querySelector('[data-document-gid="2"]'));
  assert.match(dom.window.document.body.textContent,/重新读取结构/);dom.window.close();
});
test('online source page identity uses source content hash, not insertion identity',async()=>{
  const dom=await setup(),api=dom.window.AI00TeamcenterOnlineSource;
  const doc={source_kind:'teamcenter_online',source_identity_hash:'unique-insertion',content_sha256:'identity',source_selector:{object_uid:'object'}};
  const request=async()=>({steps:[{result:dom.window.__page(dom.window.__root,[dom.window.__child])}]});
  const tree=api.partialTree();
  await api.readChildren(request,doc,tree);
  assert.equal(tree.nodes.length,2);
  await assert.rejects(api.readChildren(request,{...doc,content_sha256:'different-source'},api.partialTree()),/teamcenter_children_page_invalid/);
  dom.window.close();
});

test('online document actions live in the context menu, including cached rows and insert readiness',async()=>{
  const dom=await setup(),d=dom.window.document;
  assert.equal(d.querySelectorAll('.cs-model-document-open-online').length,0);
  vm.runInContext(`window.__opens=[];window.__messages=[];window.__loginChecks=0;_requireTeamcenterLogin=async()=>{__loginChecks++;return {state:'ready'};};_requestVisMockupCommand=async(id,payload)=>{__opens.push(id);return {};};_cmdShow=(text,kind)=>__messages.push({text,kind});_setVmDocumentReady(false);_setTreeCacheStatus($('modelDocumentList'),{workspaceGid:'10',kind:'models',cached_at:'2026-09-16',cacheOnly:true});`,dom.getInternalVMContext());
  const openMenu=()=>{d.querySelector('.cs-model-document-name').dispatchEvent(new dom.window.MouseEvent('contextmenu',{bubbles:true,cancelable:true}));return [...d.querySelectorAll('[role="menuitem"]')];};
  let buttons=openMenu();
  assert.ok(buttons.some(b=>b.textContent==='刷新结构'));
  assert.equal(buttons.find(b=>b.textContent==='插入当前文档').disabled,true);
  buttons.find(b=>b.textContent==='新文档打开').click();await tick();
  assert.equal(dom.window.__loginChecks,1);
  assert.match(dom.window.__opens[0],/visualization.launch.request$/);
  assert.match(dom.window.__messages[0].text,/正在.*新.*VisMockup 文档/);
  vm.runInContext('_setVmDocumentReady(true)',dom.getInternalVMContext());
  buttons=openMenu();assert.equal(buttons.find(b=>b.textContent==='插入当前文档').disabled,false);
  buttons.find(b=>b.textContent==='插入当前文档').click();await tick();
  assert.equal(dom.window.__loginChecks,2);
  assert.match(dom.window.__opens[1],/visualization.insert.request$/);dom.window.close();
});

test('cancelling Teamcenter login does not enqueue an online open command',async()=>{
  const dom=await setup(),d=dom.window.document;
  vm.runInContext(`window.__opens=[];_requireTeamcenterLogin=async()=>null;_requestVisMockupCommand=async(id)=>{__opens.push(id);return {};};_cmdShow=()=>{};`,dom.getInternalVMContext());
  d.querySelector('.cs-model-document-name').dispatchEvent(new dom.window.MouseEvent('contextmenu',{bubbles:true,cancelable:true}));
  [...d.querySelectorAll('[role="menuitem"]')].find(button=>button.textContent==='新文档打开').click();await tick();
  assert.deepEqual([...dom.window.__opens],[]);dom.window.close();
});

test('new Teamcenter document associates signed launch and runtime identity after embedding',async()=>{
  const dom=page();await tick();
  vm.runInContext(`
    window.__commands=[];window.__invocations=[];window.__attached=0;
    const workspace={workspace_gid:'10',row_version:4};
    window._simulationEnvironmentWorkspace={store:{state:{workspace},openWorkspace:async()=>{workspace.row_version=5;}}};
    _requireTeamcenterLogin=async()=>({state:'ready'});_cmdShow=()=>{};
    _vmDocumentReady=true;
    _requestVisMockupCommand=async(id,payload)=>{
      __commands.push(id);
      if(id.endsWith('identity.read.request')){
        return {plan_id:'identity-after',steps:[{status:'succeeded',result:{process_id:42,document_session:'new-session'}}]};
      }
      return {plan_id:'launch-operation',steps:[{status:'succeeded',result:{launch_id:'launch'}}]};
    };
    _invokeCapability=async(id,payload,options)=>{__invocations.push([id,payload,options]);return {workspace_gid:'10',document_gid:'2',state:'bound',document_session:'new-session',workspace_row_version:5,cache_revision_hash:'sha256:'+ 'a'.repeat(64)};};
    _attachNativeViewport=async()=>{__attached++;return {state:'attached',pid:42};};
    window.__pending=_openTeamcenterOnlineDocument({document_gid:'2',source_selector:{object_uid:'object'}},'new');
  `,dom.getInternalVMContext());
  await dom.window.__pending;
  assert.deepEqual([...dom.window.__commands],[
    'simulation.teamcenter.visualization.launch.request',
    'simulation.vismockup.document.identity.read.request',
  ]);
  assert.equal(dom.window.__invocations.length,1);
  assert.equal(dom.window.__invocations[0][0],'simulation.environment.online_source.live_document.bind');
  assert.deepEqual(JSON.parse(JSON.stringify(dom.window.__invocations[0][1])),{
    workspace_gid:'10',document_gid:'2',launch_operation_id:'launch-operation',identity_operation_id:'identity-after',
    expected_workspace_row_version:4,idempotency_key:'online-live-bind-launch-operation-2',
  });
  assert.equal(dom.window.__attached,1);
  assert.equal(dom.window._liveDocumentContextUnavailable,false);
  dom.window.close();
});

test('primary online open follows launch identity embed then association without reading historical binding',async()=>{
  const dom=page();await tick();
  vm.runInContext(`
    window.__order=[];window.__probe=null;
    const workspace={workspace_gid:'10',row_version:4};
    window._simulationEnvironmentWorkspace={store:{state:{workspace},openWorkspace:async()=>{}}};
    _requireTeamcenterLogin=async()=>({state:'ready'});_cmdShow=()=>{};
    _requestVisMockupCommand=async id=>{
      if(id.endsWith('visualization.launch.request')){__order.push('open');return {plan_id:'launch',steps:[{status:'succeeded',result:{launch_id:'launch'}}]};}
      __order.push('identity');return {plan_id:'identity',steps:[{status:'succeeded',result:{process_id:42,document_session:'new-session'}}]};
    };
    _attachNativeViewport=async probe=>{__order.push('embed');__probe=probe;return {state:'attached',pid:42};};
    _invokeCapability=async id=>{if(!id.endsWith('online_source.live_document.bind'))throw Error('historical_binding_must_not_gate_open');__order.push('associate');return {state:'bound'};};
    window.__pending=_openTeamcenterOnlineDocument({document_gid:'2',role:'primary',source_kind:'teamcenter_online',source_selector:{object_uid:'object'}},'new');
  `,dom.getInternalVMContext());
  await dom.window.__pending;
  assert.deepEqual([...dom.window.__order],['open','identity','embed','associate']);
  assert.equal(dom.window.__probe.openedDocumentSession,'new-session');
  assert.equal(vm.runInContext('_vmConnected',dom.getInternalVMContext()),true);
  dom.window.close();
});

test('reopening an online source rotates an existing environment binding instead of creating a second binding',async()=>{
  const dom=page();await tick();
  vm.runInContext(`
    window.__invocations=[];window.__attached=0;
    const workspace={workspace_gid:'10',row_version:4};
    window._simulationEnvironmentWorkspace={store:{state:{workspace},openWorkspace:async()=>{workspace.row_version=5;}}};
    _requireTeamcenterLogin=async()=>({state:'ready'});_cmdShow=()=>{};_vmDocumentReady=false;
    _requestVisMockupCommand=async id=>id.endsWith('visualization.launch.request')
      ? {plan_id:'launch-reopen',steps:[{status:'succeeded',result:{launch_id:'launch'}}]}
      : {plan_id:'identity-reopen',steps:[{status:'succeeded',result:{process_id:42,document_session:'sha256:'+ 'b'.repeat(64)}}]};
    _invokeCapability=async(id,payload,options)=>{
      __invocations.push([id,payload,options]);
      if(id.endsWith('online_source.live_document.bind'))return {workspace_gid:'10',document_gid:'2',state:'bound',document_session:'sha256:'+ 'b'.repeat(64),workspace_row_version:5};
      throw Error('unexpected_capability:'+id);
    };
    _attachNativeViewport=async()=>{__attached++;return {state:'attached',pid:42};};
    window.__pending=_openTeamcenterOnlineDocument({document_gid:'2',source_selector:{object_uid:'object'}},'new');
  `,dom.getInternalVMContext());
  await dom.window.__pending;
  assert.deepEqual([...dom.window.__invocations].map(item=>item[0]),[
    'simulation.environment.online_source.live_document.bind',
  ]);
  assert.deepEqual(JSON.parse(JSON.stringify(dom.window.__invocations[0][1])),{
    workspace_gid:'10',document_gid:'2',launch_operation_id:'launch-reopen',identity_operation_id:'identity-reopen',
    expected_workspace_row_version:4,idempotency_key:'online-live-bind-launch-reopen-2',
  });
  assert.equal(dom.window.__attached,1);
  dom.window.close();
});

test('new Teamcenter document does not enumerate native windows before the owned session is ready',async()=>{
  const dom=page();await tick();
  vm.runInContext(`
    window.__commands=[];window.__selected=[];window.__listed=0;window.__attached=0;
    const workspace={workspace_gid:'10',row_version:4};
    window._simulationEnvironmentWorkspace={store:{state:{workspace},openWorkspace:async()=>{workspace.row_version=5;}}};
    _requireTeamcenterLogin=async()=>({state:'ready'});_cmdShow=()=>{};_vmDocumentReady=true;
    window.__native={
      status:async()=>({state:'detached',pid:null}),
      listDocuments:async()=>{__listed++;throw Error('native_view_unavailable');},
      selectDocument:async key=>{__selected.push(key);throw Error('native_view_unavailable');},
    };
    window.electronAPI={visMockupNativeView:__native};
    _requestVisMockupCommand=async(id)=>{
      __commands.push(id);
      if(id.endsWith('visualization.launch.request'))return {plan_id:'launch-native',steps:[{status:'succeeded',result:{launch_id:'launch'}}]};
      return {plan_id:'identity-new',steps:[{status:'succeeded',result:{process_id:42,document_session:'new-session'}}]};
    };
    _invokeCapability=async id=>id.endsWith('binding.get')?{state:'unbound'}:{workspace_gid:'10',document_gid:'2',state:'bound',document_session:'new-session',workspace_row_version:5};
    _attachNativeViewport=async()=>{__attached++;return {state:'attached',pid:42};};
    window.__pending=_openTeamcenterOnlineDocument({document_gid:'2',source_selector:{object_uid:'object'}},'new');
  `,dom.getInternalVMContext());
  await dom.window.__pending;
  assert.equal(dom.window.__listed,0);
  assert.deepEqual([...dom.window.__selected],[]);
  assert.deepEqual([...dom.window.__commands],[
    'simulation.teamcenter.visualization.launch.request',
    'simulation.vismockup.document.identity.read.request',
  ]);
  dom.window.close();
});

test('failed post-launch binding is retried without launching Teamcenter again',async()=>{
  const dom=page();await tick();
  vm.runInContext(`
    window.__launches=0;window.__binds=0;
    const workspace={workspace_gid:'10',row_version:4};
    window._simulationEnvironmentWorkspace={store:{state:{workspace},openWorkspace:async()=>{}}};
    _requireTeamcenterLogin=async()=>({state:'ready'});_cmdShow=()=>{};_attachNativeViewport=async()=>({state:'attached'});
    _vmDocumentReady=true;
    let identityRead=0;
    _requestVisMockupCommand=async(id)=>{
      if(id.endsWith('identity.read.request')){identityRead++;return {plan_id:'identity-'+identityRead,steps:[{status:'succeeded',result:{process_id:42,document_session:identityRead===1?'old':'new'}}]};}
      __launches++;return {plan_id:'launch-once',steps:[{status:'succeeded',result:{launch_id:'launch'}}]};
    };
    _invokeCapability=async id=>{if(id.endsWith('binding.get'))return {state:'unbound'};__binds++;if(__binds===1)throw Error('temporary_bind_failure');return {state:'bound',workspace_row_version:5};};
    window.__doc={document_gid:'2',source_selector:{object_uid:'object'}};
    window.__first=_openTeamcenterOnlineDocument(__doc,'new').catch(error=>error.message);
  `,dom.getInternalVMContext());
  assert.match(await dom.window.__first,/文档已打开，绑定未完成/);
  assert.equal(dom.window.__launches,1);
  await vm.runInContext('_retryPendingTeamcenterOnlineBinding(__doc)',dom.getInternalVMContext());
  assert.equal(dom.window.__launches,1);
  assert.equal(dom.window.__binds,2);
  dom.window.close();
});

test('binding failure placeholder exposes one-click retry for the current online model',async()=>{
  const dom=page(),d=dom.window.document;await tick();
  d.body.insertAdjacentHTML('beforeend','<div id="vmPlaceholder"><svg></svg><p>old</p></div>');
  vm.runInContext(`
    _modelDocumentCollection=window.AI00ModelDocumentCollection.createCollection();
    window.__doc={document_gid:'2',role:'primary',source_kind:'teamcenter_online',source_selector:{object_uid:'object'},media_type:'application/vnd.siemens.teamcenter.visualization-document'};
    _modelDocumentCollection.replace([__doc]);
    window._simulationEnvironmentWorkspace={store:{state:{workspace:{workspace_gid:'10'}}}};
    window._liveDocumentContextUnavailable=true;
    _pendingTeamcenterOnlineBinding={documentGid:'2'};
    window.__opens=[];
    _openTeamcenterOnlineDocument=async(document,mode)=>{__opens.push([document.document_gid,mode]);return true;};
    _setVmStatus('error','文档已打开，绑定未完成：new_document_identity_timeout；请重试绑定，不要重复打开文档');
  `,dom.getInternalVMContext());
  const retry=d.querySelector('[data-recover-online-document]');
  assert.ok(retry);
  assert.equal(retry.textContent,'继续完成内嵌');
  retry.click();await tick();
  assert.deepEqual(JSON.parse(JSON.stringify(dom.window.__opens)),[['2','new']]);
  dom.window.close();
});

test('model placeholder starts a dedicated session instead of recovering a historical document',async()=>{
  const dom=page(),d=dom.window.document;await tick();
  d.body.insertAdjacentHTML('beforeend','<div id="vmPlaceholder"><svg></svg><p>old</p></div>');
  vm.runInContext(`
    _modelDocumentCollection=window.AI00ModelDocumentCollection.createCollection();
    window.__doc={document_gid:'2',role:'primary',source_kind:'teamcenter_online',source_selector:{object_uid:'object'},media_type:'application/vnd.siemens.teamcenter.visualization-document'};
    _modelDocumentCollection.replace([__doc]);
    window._simulationEnvironmentWorkspace={store:{state:{workspace:{workspace_gid:'10'}}}};
    window._liveDocumentContextUnavailable=true;window.__recovered=0;window.__opened=0;
    window._liveDocumentSelection={recoverEnvironment:async()=>{__recovered++;window._liveDocumentContextUnavailable=false;return {status:'recovered'};}};
    _attachNativeViewport=async()=>({state:'attached'});
    _openTeamcenterOnlineDocument=async()=>{__opened++;return true;};
    _setVmStatus('unavailable','缓存已保留 · 请点击文档名选择“恢复到当前环境”');
  `,dom.getInternalVMContext());
  d.querySelector('[data-recover-online-document]').click();await tick();
  assert.equal(dom.window.__recovered,0);
  assert.equal(dom.window.__opened,1);
  dom.window.close();
});

test('environment change while resolving the new document prevents bind and embed',async()=>{
  const dom=page();await tick();
  vm.runInContext(`
    window.__binds=0;window.__attached=0;
    const state={workspace:{workspace_gid:'10',row_version:4}};
    window._simulationEnvironmentWorkspace={store:{state,openWorkspace:async()=>{}}};
    _requireTeamcenterLogin=async()=>({state:'ready'});_cmdShow=()=>{};_vmDocumentReady=false;
    _requestVisMockupCommand=async(id)=>{
      if(id.endsWith('visualization.launch.request'))return {plan_id:'launch-switch',steps:[{status:'succeeded',result:{launch_id:'launch'}}]};
      state.workspace={workspace_gid:'20',row_version:1};
      return {plan_id:'identity-new',steps:[{status:'succeeded',result:{process_id:42,document_session:'new'}}]};
    };
    _invokeCapability=async id=>{if(id.endsWith('binding.get'))return {state:'unbound'};__binds++;return {state:'bound'};};
    _attachNativeViewport=async()=>{__attached++;return {state:'attached'};};
    window.__changed=_openTeamcenterOnlineDocument({document_gid:'2',source_selector:{object_uid:'object'}},'new').catch(error=>error.message);
  `,dom.getInternalVMContext());
  assert.match(await dom.window.__changed,/online_binding_environment_changed/);
  assert.equal(dom.window.__binds,0);assert.equal(dom.window.__attached,0);
  dom.window.close();
});

test('Teamcenter login hides the native viewport before focusing credentials',async()=>{
  const dom=page();await tick();const d=dom.window.document;
  vm.runInContext(`
    window.__focusOrder=[];
    _syncNativeViewportOcclusion=()=>__focusOrder.push('occlude');
    requestAnimationFrame=callback=>{__focusOrder.push('frame');callback();};
    window.__loginPending=_teamcenterLoginDialog();
  `,dom.getInternalVMContext());
  assert.deepEqual([...dom.window.__focusOrder],['occlude','frame']);
  assert.equal(d.activeElement,d.querySelector('[name="username"]'));
  d.querySelector('[data-cancel]').click();await dom.window.__loginPending;dom.window.close();
});

test('source mapper produces a valid prefixed forest for a complete snapshot',async()=>{
  const dom=page();await tick();const api=dom.window.AI00TeamcenterOnlineSource;
  const tree=await api.readSnapshot(async()=>({node_count:2,nodes:[{occurrence_id:'r',parent_occurrence_id:null},{occurrence_id:'c',parent_occurrence_id:'r'}],next_cursor:null}),'snapshot');
  const forest=dom.window.AI00ModelDocumentCollection.buildProductForest(tree.nodes);
  assert.equal(forest.length,1);assert.equal(forest[0].children[0].node_key,'tc:c');assert.equal(tree.complete,true);dom.window.close();
});
test('reopening cached partial tree skips Connector reads; only explicit refresh invalidates children cache',async()=>{
  const dom=await setup();
  vm.runInContext(`
    const cached={items:_modelDocumentCollection.state.documents};
    window.electronAPI={simulationTreeCache:{get:async(_w,k)=>k==='models'?{data:cached,cached_at:'2026-09-16'}:null,put:async()=>{}}};
    window.__pending=_refreshModelDocuments({workspace_gid:'10'},{useCache:true});
  `,dom.getInternalVMContext());await dom.window.__pending;
  assert.equal(dom.window.__calls.length,1);
  vm.runInContext(`window.__pending=_refreshModelDocuments({workspace_gid:'10'},{refreshChildren:true});`,dom.getInternalVMContext());await dom.window.__pending;
  assert.equal(dom.window.__calls.length,2);assert.equal(dom.window.__calls[1][1].refresh,true);dom.window.close();
});
test('pending child survives ancestor collapse and reopening and updates the visible wrapper',async()=>{
  const dom=await setup(),d=dom.window.document;
  d.querySelectorAll('.cs-alternate-tree-toggle')[1].click();
  const root=d.querySelector('.cs-alternate-tree-toggle');root.click();root.click();
  const child=d.querySelectorAll('.cs-alternate-tree-toggle')[1];
  if(child.parentElement.nextElementSibling.classList.contains('hidden'))child.click();
  const grand=dom.window.__node('resolved-grandchild','child',[{occurrence_uid:'edge',item_revision_uid:'rev'},{occurrence_uid:'g',item_revision_uid:'r'}],false);
  dom.window.__resolve({steps:[{result:dom.window.__page(dom.window.__child,[grand])}]});await tick();
  assert.match(d.body.textContent,/resolved-grandchild/);assert.doesNotMatch(child.parentElement.nextElementSibling.textContent,/读取中/);
  assert.equal(dom.window.__calls.length,2);dom.window.close();
});
test('cached old projection cannot hide a newly bound document when initial children read fails',async()=>{
  const dom=page();await tick();
  vm.runInContext(`
    _modelDocumentCollection=window.AI00ModelDocumentCollection.createCollection();window.__messages=[];
    const workspace={workspace_gid:'10',row_version:1};
    const old={document_gid:'1',role:'primary',source_kind:'artifact',media_type:'application/plmxml+xml',content_sha256:'same',product_tree:{state:'ready',node_count:1,nodes:[{node_key:'old',name:'retained-old'}]}};
    const added={document_gid:'2',role:'inserted',source_kind:'teamcenter_online',source_selector:{object_uid:'o'},media_type:'application/vnd.siemens.teamcenter.visualization-document'};
    window.electronAPI={simulationTreeCache:{get:async(_w,k)=>k==='models'?{data:{items:[old]},cached_at:'2026-09-16'}:null,put:async()=>{}}};
    window._simulationEnvironmentWorkspace={store:{state:{workspace},openWorkspace:async()=>{}}};
    _requireTeamcenterLogin=async()=>({});_teamcenterSourceDialog=async()=>({display_name:'Online',insertion_instance_id:'once',source_selector:{object_uid:'o'}});
    _cmdShow=(text,kind)=>__messages.push({text,kind});
    _invokeCapability=async(id)=>id.endsWith('.bind')?{document_gid:'2'}:{items:[{...old,product_tree:undefined},added]};
    _requestVisMockupCommand=()=>new Promise((_resolve,reject)=>{window.__rejectInitialRead=reject;});window.__pending=_addTeamcenterSource();
  `,dom.getInternalVMContext());await tick();
  assert.ok(dom.window.document.querySelector('[data-document-gid="2"]'), 'registration must be visible before the SDK read finishes');
  dom.window.__rejectInitialRead(Error('offline'));await dom.window.__pending;
  assert.ok(dom.window.document.querySelector('[data-document-gid="2"]'));
  assert.ok(dom.window.document.querySelector('[data-document-gid="1"]'));
  assert.match(dom.window.document.body.textContent,/重新读取结构/);
  assert.equal(dom.window.__messages.at(-1).kind,'err');assert.match(dom.window.__messages.at(-1).text,/已登记/);dom.window.close();
});
test('stale paging generation retries from first page and replaces old siblings only on success',async()=>{
  const dom=await setup(),d=dom.window.document;
  d.querySelectorAll('.cs-alternate-tree-toggle')[1].click();
  const grand=dom.window.__node('old-page-child','child',[{occurrence_uid:'edge',item_revision_uid:'rev'},{occurrence_uid:'g',item_revision_uid:'r'}],false);
  dom.window.__resolve({steps:[{result:dom.window.__page(dom.window.__child,[grand],0,1)}]});await tick();
  d.querySelector('[data-tc-more]').click();dom.window.__reject(Error('teamcenter_children_generation_stale'));await tick();
  d.querySelector('[data-tc-retry]').click();
  assert.equal(dom.window.__calls.at(-1)[1].cursor,0);assert.equal(dom.window.__calls.at(-1)[1].generation,null);
  assert.match(d.body.textContent,/old-page-child/);
  const next={...grand,occurrence_id:'new-page-child',name:'new-page-child'};
  dom.window.__resolve({steps:[{result:{...dom.window.__page(dom.window.__child,[next]),generation:'b'.repeat(32)}}]});await tick();
  assert.match(d.body.textContent,/new-page-child/);assert.doesNotMatch(d.body.textContent,/old-page-child/);dom.window.close();
});
test('same-generation cached root reread retains loaded descendants while explicit refresh prunes',async()=>{
  const dom=await setup(),api=dom.window.AI00TeamcenterOnlineSource;
  const tree=api.partialTree(),doc={source_selector:{object_uid:'o'},source_identity_hash:'identity'};
  const rootPage=dom.window.__page(dom.window.__root,[dom.window.__child]);
  const rootRead=async()=>({steps:[{result:rootPage}]});
  await api.readChildren(rootRead,doc,tree);
  const grand=dom.window.__node('grand','child',[{occurrence_uid:'edge',item_revision_uid:'rev'},{occurrence_uid:'g',item_revision_uid:'r'}],false);
  await api.readChildren(async()=>({steps:[{result:dom.window.__page(dom.window.__child,[grand])}]}),doc,tree,dom.window.__child.occurrence_path);
  await api.readChildren(rootRead,doc,tree);
  assert.ok(tree.nodes.some(node=>node.node_key==='tc:grand'));
  assert.equal(tree.pages[JSON.stringify(dom.window.__child.occurrence_path)].state,'loaded');
  await api.readChildren(rootRead,doc,tree,[],{refresh:true});
  assert.equal(tree.nodes.some(node=>node.node_key==='tc:grand'),false);dom.window.close();
});
test('new ancestor generation invalidates pending descendant reads without resurrecting removed nodes',async()=>{
  const dom=await setup(),d=dom.window.document;
  vm.runInContext(`
    _modelDocumentCollection.state.documents[0].product_tree.pages['[]'].next_cursor=1;
    _requestVisMockupCommand=async(id,payload)=>{__calls.push([id,payload]);return new Promise((resolve,reject)=>{window.__resolve=resolve;window.__reject=reject;});};
  `,dom.getInternalVMContext());
  const root=d.querySelector('.cs-alternate-tree-toggle');root.click();root.click();
  d.querySelectorAll('.cs-alternate-tree-toggle')[1].click();
  const resolveOldChild=dom.window.__resolve;
  d.querySelector('[data-tc-more]').click();dom.window.__reject(Error('teamcenter_children_generation_stale'));await tick();
  d.querySelector('[data-tc-retry]').click();
  dom.window.__resolve({steps:[{result:{...dom.window.__page(dom.window.__root,[]),generation:'b'.repeat(32)}}]});await tick();
  const grand=dom.window.__node('resurrected','child',[{occurrence_uid:'edge',item_revision_uid:'rev'},{occurrence_uid:'g',item_revision_uid:'r'}],false);
  resolveOldChild({steps:[{result:dom.window.__page(dom.window.__child,[grand])}]});await tick();
  const nodeKeys=vm.runInContext(`_modelDocumentCollection.state.documents[0].product_tree.nodes.map(node=>node.node_key)`,dom.getInternalVMContext());
  assert.deepEqual([...nodeKeys],['tc:root']);
  root.click();root.click();assert.doesNotMatch(d.body.textContent,/child|resurrected/);dom.window.close();
});
test('adding a source reads only the new TC document and preserves unrelated cached live structure',async()=>{
  const dom=page();await tick();
  vm.runInContext(`
    _modelDocumentCollection=window.AI00ModelDocumentCollection.createCollection();window.__calls=[];window.__liveReads=0;window.__invokes=[];
    const workspace={workspace_gid:'10',row_version:1};
    const old={document_gid:'1',role:'primary',source_kind:'live_document',source_identity_hash:'live-id',media_type:'application/vnd.siemens.teamcenter.visualization-document',product_tree:{state:'ready',node_count:1,nodes:[{node_key:'live',name:'cached-live'}]}};
    const added={document_gid:'2',role:'inserted',source_kind:'teamcenter_online',source_selector:{object_uid:'o'},media_type:'application/vnd.siemens.teamcenter.visualization-document'};
    const snapshot={...added,document_gid:'3',observation_id:'existing-snapshot',product_tree:{state:'ready',node_count:1,nodes:[{node_key:'snapshot-root'}]}};
    const otherTc={...added,document_gid:'4',source_selector:{object_uid:'other'},product_tree:{state:'ready',source:'teamcenter_children',node_count:1,nodes:[{node_key:'other-root'}],pages:{}}};
    window.electronAPI={simulationTreeCache:{get:async(_w,k)=>k==='models'?{data:{items:[old,snapshot,otherTc]},cached_at:'2026-09-16'}:null,put:async()=>{}}};
    window._simulationEnvironmentWorkspace={store:{state:{workspace},openWorkspace:async()=>{}}};
    window._readLiveModelProductTree=async()=>{__liveReads++;throw Error('stale-live-document');};
    _requireTeamcenterLogin=async()=>({});_teamcenterSourceDialog=async()=>({display_name:'Online',insertion_instance_id:'once',source_selector:{object_uid:'o'}});_cmdShow=()=>{};
    _invokeCapability=async(id)=>{__invokes.push(id);return id.endsWith('.bind')?{document_gid:'2'}:{items:[{...old,product_tree:undefined},added,{...snapshot,product_tree:undefined},{...otherTc,product_tree:undefined}]};};
    _requestVisMockupCommand=async(id,payload)=>{__calls.push([id,payload]);return {steps:[{result:{parent:{occurrence_id:'tc-root',parent_occurrence_id:null,occurrence_path:[],has_children:false},nodes:[],cursor:0,next_cursor:null,child_count:0,complete:false,generation:'a'.repeat(32),cache_hit:true,captured_at:'2026-09-16'}}]};};
    window.__pending=_addTeamcenterSource();
  `,dom.getInternalVMContext());await dom.window.__pending;
  assert.equal(dom.window.__liveReads,0);assert.equal(dom.window.__calls.length,1);assert.equal(dom.window.__calls[0][1].refresh,false);
  assert.deepEqual([...dom.window.__invokes],['simulation.environment.online_source.bind','simulation.environment.model_document.search']);
  assert.equal(vm.runInContext(`_modelDocumentCollection.state.documents[0].product_tree.nodes[0].name`,dom.getInternalVMContext()),'cached-live');
  assert.doesNotMatch(dom.window.document.body.textContent,/校验|stale-live-document/);dom.window.close();
});
test('invalidated descendant completion cannot clear a replacement request for the same path',async()=>{
  const dom=await setup(),api=dom.window.AI00TeamcenterOnlineSource,tree=api.partialTree();
  const doc={source_selector:{object_uid:'o'},source_identity_hash:'identity'},child=dom.window.__child;
  await api.readChildren(async()=>({steps:[{result:dom.window.__page(dom.window.__root,[child])}]}),doc,tree);
  let resolveOld,resolveNew;
  const old=api.readChildren(()=>new Promise(r=>resolveOld=r),doc,tree,child.occurrence_path);
  await api.readChildren(async()=>({steps:[{result:{...dom.window.__page(dom.window.__root,[child]),generation:'b'.repeat(32)}}]}),doc,tree,[],{refresh:true});
  const replacement=api.readChildren(()=>new Promise(r=>resolveNew=r),doc,tree,child.occurrence_path);
  resolveOld({steps:[{result:dom.window.__page(child,[])}]});await old;
  assert.equal(tree.pages[JSON.stringify(child.occurrence_path)].state,'loading');
  const duplicate=api.readChildren(()=>{throw Error('duplicate request');},doc,tree,child.occurrence_path);
  assert.equal(duplicate,replacement);
  resolveNew({steps:[{result:dom.window.__page(child,[])}]});await replacement;
  assert.equal(tree.pages[JSON.stringify(child.occurrence_path)].state,'loaded');dom.window.close();
});
test('targeted add makes interrupted unrelated child reads retryable without reusing old promises',async()=>{
  const dom=await setup(),d=dom.window.document;
  vm.runInContext(`
    const saved=JSON.stringify({items:_modelDocumentCollection.state.documents});
    window.electronAPI={simulationTreeCache:{get:async(_w,k)=>k==='models'?{data:JSON.parse(saved),cached_at:'2026-09-16'}:null,put:async()=>{}}};
  `,dom.getInternalVMContext());
  d.querySelectorAll('.cs-alternate-tree-toggle')[1].click();
  const resolveOld=dom.window.__resolve;
  vm.runInContext(`
    window.__oldTree=_modelDocumentCollection.state.documents[0].product_tree;
    const originalRead=_requestVisMockupCommand;
    _requestVisMockupCommand=(id,payload)=>payload.source_selector.object_uid==='new'
      ? (__calls.push([id,payload]),Promise.resolve({steps:[{result:__page(__root,[])}]})) : originalRead(id,payload);
    _invokeCapability=async()=>({items:[{...__doc},{...__doc,document_gid:'3',role:'inserted',source_selector:{object_uid:'new'}}]});
    window.__pending=_refreshModelDocuments({workspace_gid:'10'},{refreshDocumentGid:'3'});
  `,dom.getInternalVMContext());await dom.window.__pending;
  resolveOld({steps:[{result:dom.window.__page(dom.window.__child,[])}]});await tick();
  const state=vm.runInContext(`_modelDocumentCollection.state.documents[0].product_tree.pages[JSON.stringify(__child.occurrence_path)].state`,dom.getInternalVMContext());
  assert.equal(state,'failed');assert.equal(dom.window.__calls.length,3);
  const row=d.querySelector('[data-document-gid="2"]');
  if(row.querySelector('.cs-model-document-tree').classList.contains('hidden'))row.querySelector('.cs-model-document-toggle').click();
  for(const key of ['tc:root','tc:child']){
    const node=[...row.querySelectorAll('[data-cache-view-key]')].find(n=>n.dataset.cacheViewKey==='product:2:'+key);
    if(node.querySelector(':scope > .cs-alternate-tree-children').classList.contains('hidden'))node.querySelector(':scope > .cs-alternate-tree-line > button').click();
  }
  row.querySelector('[data-tc-retry]').click();assert.equal(dom.window.__calls.length,4);
  dom.window.__resolve({steps:[{result:dom.window.__page(dom.window.__child,[])}]});await tick();
  assert.equal(vm.runInContext(`_modelDocumentCollection.state.documents[0].product_tree.pages[JSON.stringify(__child.occurrence_path)].state`,dom.getInternalVMContext()),'loaded');
  dom.window.close();
});

test('targeted add preserves newer loaded descendants over serialized older projection',async()=>{
  const dom=await setup(),d=dom.window.document;
  vm.runInContext(`
    const saved=JSON.stringify({items:_modelDocumentCollection.state.documents});
    window.electronAPI={simulationTreeCache:{get:async(_w,k)=>k==='models'?{data:JSON.parse(saved),cached_at:'2026-09-16'}:null,put:async()=>{}}};
  `,dom.getInternalVMContext());
  d.querySelectorAll('.cs-alternate-tree-toggle')[1].click();
  const grand=dom.window.__node('grand','child',[{occurrence_uid:'edge',item_revision_uid:'rev'},{occurrence_uid:'g',item_revision_uid:'r'}],false);
  dom.window.__resolve({steps:[{result:dom.window.__page(dom.window.__child,[grand])}]});await tick();
  vm.runInContext(`
    _invokeCapability=async()=>({items:[{...__doc},{...__doc,document_gid:'3',role:'inserted',source_selector:{object_uid:'new'}}]});
    window.__pending=_refreshModelDocuments({workspace_gid:'10'},{refreshDocumentGid:'3'});
  `,dom.getInternalVMContext());await dom.window.__pending;
  const keys=vm.runInContext(`_modelDocumentCollection.state.documents[0].product_tree.nodes.map(node=>node.node_key)`,dom.getInternalVMContext());
  assert.deepEqual([...keys],['tc:root','tc:child','tc:grand']);
  assert.equal(dom.window.__calls.length,3);
  assert.equal(dom.window.__calls.at(-1)[1].source_selector.object_uid,'new');
  dom.window.close();
});
