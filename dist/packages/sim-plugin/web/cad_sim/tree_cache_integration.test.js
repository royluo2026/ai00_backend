const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {JSDOM}=require('jsdom');
function page(){
  const dom=new JSDOM('<div id="modelDocumentList"></div><div id="alternateHierarchyList"></div>',{runScripts:'outside-only'});
  for(const file of ['model_document_collection.js','tree_projection_cache.js','cad_sim.js']) vm.runInContext(fs.readFileSync(path.join(__dirname,file),'utf8'),dom.getInternalVMContext());
  return dom;
}
test('cached model checkbox and name dispatch node actions instead of being disabled',async()=>{
  const dom=page();await new Promise(r=>setImmediate(r));
  vm.runInContext(`
    _modelDocumentCollection=window.AI00ModelDocumentCollection.createCollection();
    const doc={document_gid:'2',role:'primary',source_kind:'live_document',media_type:'application/vnd.siemens.teamcenter.visualization-document',product_tree:{document_session:'session',state:'ready',node_count:1,nodes:[{node_key:'7',name:'Part',visible:false}]}};
    _modelDocumentCollection.replace([doc]);
    window._simulationEnvironmentWorkspace={store:{state:{workspace:{workspace_gid:'10'}}}};
    window.__actions=[];window._actOnModelNode=async x=>{window.__actions.push(x.action);return{visible:true};};
    _renderModelDocuments([doc]);_setTreeCacheStatus(document.getElementById('modelDocumentList'),{workspaceGid:'10',kind:'models',cacheOnly:true,cached_at:'2026-09-15T00:00:00Z'});
  `,dom.getInternalVMContext());
  dom.window.document.querySelector('.cs-model-document-toggle').click();
  const check=dom.window.document.querySelector('.cs-alternate-tree-check');assert.equal(check.disabled,false);
  check.click();await new Promise(r=>setImmediate(r));assert.equal(check.checked,true);
  dom.window.document.querySelector('.cs-alternate-tree-name').click();await new Promise(r=>setImmediate(r));
  assert.deepEqual([...dom.window.__actions],['show','highlight']);dom.window.close();
});
test('parent visibility includes collapsed descendants and child changes update ancestor state',async()=>{
  const dom=page();await new Promise(r=>setImmediate(r));
  vm.runInContext(`
    _modelDocumentCollection=window.AI00ModelDocumentCollection.createCollection();
    const doc={document_gid:'2',role:'primary',media_type:'application/plmxml+xml',product_tree:{document_session:'session',state:'ready',node_count:3,nodes:[
      {node_key:'7',name:'Root',visible:true},{node_key:'8',parent_key:'7',name:'Same',visible:true},
      {node_key:'9',parent_key:'7',name:'Same',visible:false}]}};
    _modelDocumentCollection.replace([doc]);
    window._simulationEnvironmentWorkspace={store:{state:{workspace:{workspace_gid:'10'}}}};
    window.__actions=[];window._actOnModelNode=async x=>{window.__actions.push([x.nodeKey,x.action]);return{visible:x.action==='show'};};
    _renderModelDocuments([doc]);
  `,dom.getInternalVMContext());
  const document=dom.window.document;
  document.querySelector('.cs-model-document-toggle').click();
  const parent=document.querySelector('.cs-alternate-tree-check');
  assert.equal(parent.indeterminate,true);
  parent.click();await new Promise(r=>setImmediate(r));
  document.querySelector('.cs-alternate-tree-toggle').click();
  let checks=[...document.querySelectorAll('.cs-alternate-tree-check')];
  assert.deepEqual(checks.map(c=>c.checked),[true,true,true]);
  checks[2].click();await new Promise(r=>setImmediate(r));
  assert.equal(parent.indeterminate,true);
  assert.deepEqual(checks.map(c=>c.checked),[false,true,false]);
  assert.equal(JSON.stringify(dom.window.__actions),JSON.stringify([['7','show'],['9','hide']]));
  dom.window.close();
});

test('Teamcenter root visibility fans out through real child occurrence locators',async()=>{
  const dom=page();await new Promise(r=>setImmediate(r));
  vm.runInContext(`
    _modelDocumentCollection=window.AI00ModelDocumentCollection.createCollection();
    const doc={document_gid:'2',role:'primary',source_kind:'teamcenter_online',source_selector:{object_uid:'uid'},media_type:'application/vnd.siemens.teamcenter.visualization-document',product_tree:{state:'ready',node_count:3,nodes:[
      {node_key:'tc:root',name:'Root',visible:false},
      {node_key:'tc:a',control_key:'tc:occ-a',parent_key:'tc:root',name:'Same',visible:false},
      {node_key:'tc:b',control_key:'tc:occ-b',parent_key:'tc:root',name:'Same',visible:false}]}};
    _modelDocumentCollection.replace([doc]);
    window._simulationEnvironmentWorkspace={store:{state:{workspace:{workspace_gid:'10'}}}};
    window.__actions=[];window._actOnModelNode=async x=>{window.__actions.push([x.nodeKey,x.action]);return{visible:true};};
    _renderModelDocuments([doc]);
  `,dom.getInternalVMContext());
  const document=dom.window.document;
  document.querySelector('.cs-model-document-toggle').click();
  document.querySelector('.cs-alternate-tree-check').click();
  await new Promise(r=>setImmediate(r));
  assert.deepEqual([...dom.window.__actions].map(x=>[...x]),[['tc:a','show'],['tc:b','show']]);
  assert.equal(document.querySelector('.cs-alternate-tree-check').checked,true);
  dom.window.close();
});

test('entry reuses both trees without reads and explicit model refresh still reads live',async()=>{
  const dom=page(); await new Promise(resolve=>setImmediate(resolve));
  vm.runInContext(`
    _modelDocumentCollection=window.AI00ModelDocumentCollection.createCollection();
    window._simulationEnvironmentWorkspace={store:{state:{workspace:{workspace_gid:'10'}}}};
    window.__reads=0;
    window.__doc={document_gid:'2',role:'primary',source_kind:'live_document',media_type:'application/vnd.siemens.teamcenter.visualization-document',product_tree:{state:'ready',node_count:1,nodes:[{node_key:'r',name:'Root'}]}};
    window.electronAPI={simulationTreeCache:{get:async(_w,k)=>['models','alternate'].includes(k)?{cached_at:'2026-09-15T00:00:00Z',data:{items:k==='models'?[window.__doc]:[]}}:null,put:async()=>{}}};
    _invokeCapability=async()=>{window.__reads++;return{items:[window.__doc]};};
    window._readLiveModelProductTree=async()=>{window.__reads++;return window.__doc.product_tree;};
    window.__pending=Promise.all([_refreshModelDocuments(undefined,{useCache:true}),_refreshAlternateHierarchies(undefined,null,{useCache:true})]);
  `,dom.getInternalVMContext());
  await dom.window.__pending;
  assert.equal(dom.window.__reads,0);
  const host=dom.window.document.getElementById('modelDocumentList');
  assert.doesNotMatch(host.textContent,/未自动重读|后台校验/);
  assert.equal(host.querySelector('.cs-tree-cache-status button'),null);
  host.dispatchEvent(new dom.window.MouseEvent('contextmenu',{bubbles:true,cancelable:true}));
  const refresh=dom.window.document.querySelector('[role="menuitem"]');
  assert.equal(refresh?.textContent,'刷新结构'); refresh.click();
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(dom.window.__reads,2);
  dom.window.close();
});
test('switch removes the previous environment before cache I/O completes',async()=>{
  const dom=page(); await new Promise(resolve=>setImmediate(resolve));
  vm.runInContext(`
    _modelDocumentCollection=window.AI00ModelDocumentCollection.createCollection();
    _modelDocumentWorkspaceGid='9'; _alternateHierarchyWorkspaceGid='9';
    document.getElementById('modelDocumentList').textContent='previous-model';
    document.getElementById('alternateHierarchyList').textContent='previous-AH';
    window.electronAPI={simulationTreeCache:{get:()=>new Promise(()=>{})}};
    _refreshModelDocuments({workspace_gid:'10'});
    _refreshAlternateHierarchies({workspace_gid:'10'});
  `,dom.getInternalVMContext());
  assert.doesNotMatch(dom.window.document.body.textContent,/previous-/);
  dom.window.close();
});
test('cached primary tree appears before live read and remains browse-only on failure',async()=>{
  const dom=page();
  await new Promise(resolve=>setImmediate(resolve));
  vm.runInContext(`
    _modelDocumentCollection=window.AI00ModelDocumentCollection.createCollection();
    window.__doc={document_gid:'2',role:'primary',source_kind:'live_document',source_identity_hash:'identity-a',media_type:'application/vnd.siemens.teamcenter.visualization-document',product_tree:{state:'ready',node_count:2,nodes:[{node_key:'r',parent_key:null,name:'Root'},{node_key:'c',parent_key:'r',name:'Child'}]}};
    window.__gets=[];
    window.electronAPI={simulationTreeCache:{get:async(_w,k)=>{window.__gets.push(k);return k==='models'?{data:{items:[window.__doc]},cached_at:'2026-09-15T00:00:00Z'}:null},put:async()=>{throw Error('should not overwrite old tree')}}};
    _invokeCapability=async()=>({items:[{...window.__doc,product_tree:undefined}]});
    window._readLiveModelProductTree=()=>new Promise((_r,reject)=>window.__reject=reject);
    window.__pending=_refreshModelDocuments({workspace_gid:'10'});
  `,dom.getInternalVMContext());
  await new Promise(resolve=>setImmediate(resolve));
  const host=dom.window.document.getElementById('modelDocumentList');
  assert.deepEqual([...dom.window.__gets],['models','models-view']);
  assert.equal(host.dataset.cachePending,'true');
  assert.match(host.textContent,/读取中/);
  host.querySelector('.cs-model-document-toggle').click();
  assert.match(host.textContent,/Root/);
  const event=new dom.window.Event('dragstart',{bubbles:true,cancelable:true});
  assert.equal(host.querySelector('.cs-model-document-summary').dispatchEvent(event),false);
  dom.window.__reject(Error('connector_unavailable')); await dom.window.__pending;
  assert.match(host.textContent,/读取失败，保留已缓存结构：connector_unavailable/);
  assert.equal(host.dataset.cachePending,'true');
  dom.window.close();
});
test('view state restores nested lazy product expansion without enabling cached actions',()=>{
  const dom=page();
  vm.runInContext(`
    _renderModelDocuments([{document_gid:'2',role:'primary',media_type:'application/plmxml+xml',product_tree:{state:'ready',node_count:2,nodes:[{node_key:'r',parent_key:null,name:'Root'},{node_key:'c',parent_key:'r',name:'Child'}]}}]);
    _setTreeCacheStatus(document.getElementById('modelDocumentList'),{workspaceGid:'10',kind:'models',cached_at:'2026-09-15T00:00:00Z',viewState:{expanded:['doc:2','product:2:r'],scrollTop:0}});
  `,dom.getInternalVMContext());
  assert.match(dom.window.document.getElementById('modelDocumentList').textContent,/Child/);
  assert.equal(dom.window.document.querySelector('.cs-model-document-tree').classList.contains('hidden'),false);
  dom.window.close();
});
test('cached alternate hierarchy is visible before server refresh and cannot edit or drop',async()=>{
  const dom=page(); await new Promise(resolve=>setImmediate(resolve));
  vm.runInContext(`
    _modelDocumentCollection=window.AI00ModelDocumentCollection.createCollection();
    window.electronAPI={simulationTreeCache:{get:async(_w,k)=>k==='alternate'?{cached_at:'2026-09-15T00:00:00Z',data:{selected_gid:'20',items:[{hierarchy_gid:'20',row_version:1,name:'AH cache',nodes:[{node_gid:'21',parent_gid:null,name:'Cached node'}],placements:[]}]}}:null,put:async()=>{}}};
    _invokeCapability=()=>new Promise((_r,reject)=>window.__reject=reject);
    window.__pending=_refreshAlternateHierarchies({workspace_gid:'10'});
  `,dom.getInternalVMContext());
  await new Promise(resolve=>setImmediate(resolve));
  const host=dom.window.document.getElementById('alternateHierarchyList');
  assert.match(host.textContent,/Cached node/);
  assert.equal(host.querySelector('input').disabled,true);
  for(const type of ['contextmenu','drop']) assert.equal(host.querySelector('.cs-alternate-hierarchy-row').dispatchEvent(new dom.window.Event(type,{bubbles:true,cancelable:true})),false);
  dom.window.__reject(Error('provider_failed')); await dom.window.__pending;
  assert.match(host.textContent,/读取失败，保留已缓存结构：provider_failed/);
  assert.doesNotMatch(host.textContent,/后台校验|校验失败/);
  dom.window.close();
});
