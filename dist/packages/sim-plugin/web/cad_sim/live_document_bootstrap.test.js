const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

test('cached model action checks the current source before any native open', async()=>{
 const dom=new JSDOM('<div id="modelDocumentList"></div>',{runScripts:'outside-only'}),w=dom.window;
 const removed=[],calls=[];
 const workspace={workspace_gid:'1',row_version:1};
 const document={workspace_gid:'1',document_gid:'2',role:'primary',source_kind:'teamcenter_cache_snapshot',
  source_identity_hash:'sha256:'+'a'.repeat(64),cache_binding:{batch_id:'batch',generation:null,snapshot_hash:null,schema_version:1}};
 w._simulationEnvironmentWorkspace={store:{state:{workspace},subscribe(){}}};
 w._eAPI=()=>({simulationTreeCache:{remove:async(...args)=>removed.push(args)}});
 w._discardCachedModelProjection=async gid=>w._eAPI().simulationTreeCache.remove(gid,'models');
 w._invokeCapability=async(id,payload,options)=>{calls.push([id,payload,options]);return {items:[]};};
 w._refreshModelDocuments=async()=>{calls.push(['refresh']);};
 w._notifyNativeViewportBounds=()=>{};
 let native=0;
 w.AI00LiveDocumentAdoption={createAdapter:()=>({invalidateControlMappings(){},async actOnProductNode(){native++;return {ok:true};}}),mount(){}};
 w.AI00LiveDocumentSwitcher={createAdapter:()=>({isOwnWorkspaceChange:()=>false,cancel(){}}),mount(){}};
 try{
  w.eval(fs.readFileSync(path.join(__dirname,'live_document_bootstrap.js'),'utf8'));
  w.AI00LiveDocumentBootstrap();await new Promise(r=>setImmediate(r));
  await assert.rejects(w._actOnModelNode({workspaceGid:'1',document,nodeKey:'cache:root',action:'show'}),/cache_model_document_not_found/);
  assert.equal(native,0);
  assert.ok(calls.some(call=>JSON.stringify(call)===JSON.stringify(['simulation.environment.model_document.search',{workspace_gid:'1'},{version:2}])));
  assert.deepEqual(removed,[['1','models']]);
  w._invokeCapability=async()=>({items:[{...document}]});
  await w._actOnModelNode({workspaceGid:'1',document,nodeKey:'cache:root',action:'show'});
  assert.equal(native,1,'matching current source may continue to the native path');
 }finally{w.close();}
});

test('a completed model action refreshes the existing tree even without a checkbox click handler',async()=>{
 const vm=require('node:vm');
 const dom=new JSDOM('<div id="modelDocumentList"></div>',{runScripts:'outside-only'}),w=dom.window,c=dom.getInternalVMContext();
 try{
  for(const file of ['model_document_collection.js','cad_sim.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,file),'utf8'),c);
  vm.runInContext(`document.removeEventListener('DOMContentLoaded',init);_cmdShow=()=>{};_simulationDebug=()=>{};
   window.model={document_gid:'2',media_type:'application/teamcenter',source_kind:'teamcenter_online',source_selector:{},product_tree:{state:'ready',node_count:1,nodes:[{node_key:'root',parent_key:null,name:'Assembly',visible:null,visibility_state:'unknown',occurrence_path:[]}]}};
   _modelDocumentCollection={state:{documents:[model]}};
   window._simulationEnvironmentWorkspace={store:{state:{workspace:{workspace_gid:'1',row_version:1}},subscribe(){}}};
   window._eAPI=()=>({});window._notifyNativeViewportBounds=()=>{};
   window.AI00LiveDocumentAdoption={createAdapter:()=>({invalidateControlMappings(){},async actOnProductNode(){const state=window.nextState||'visible';Object.assign(model.product_tree.nodes[0],{visible:state==='visible'?true:null,visibility_state:state});if(window.testError)throw Error('native_readback_failed');return {ok:true,calibrated:true};}}),mount(){}};
   window.AI00LiveDocumentSwitcher={createAdapter:()=>({isOwnWorkspaceChange:()=>false,cancel(){}}),mount(){}};`,c);
  w.eval(fs.readFileSync(path.join(__dirname,'live_document_bootstrap.js'),'utf8'));w.AI00LiveDocumentBootstrap();await new Promise(r=>setImmediate(r));
  vm.runInContext(`_renderModelDocuments([model]);document.querySelector('.cs-model-document-toggle').click();`,c);
  const check=w.document.querySelector('.cs-alternate-tree-check');assert.equal(check.dataset.visibility,'unknown');
  await w._actOnModelNode({workspaceGid:'1',document:w.model,nodeKey:'root',action:'show'});
  assert.equal(check.dataset.visibility,'visible');assert.equal(check.checked,true);
  w.nextState='unknown';w.testError=true;
  await assert.rejects(w._actOnModelNode({workspaceGid:'1',document:w.model,nodeKey:'root',action:'show'}),/native_readback_failed/);
  assert.equal(check.dataset.visibility,'unknown');assert.equal(check.checked,false);
  w.nextState='visible';w.testError=false;w._simulationEnvironmentWorkspace.store.state.workspace={workspace_gid:'other'};
  await w._actOnModelNode({workspaceGid:'1',document:w.model,nodeKey:'root',action:'show'});
  assert.equal(check.dataset.visibility,'unknown','late results cannot repaint a different environment');
 }finally{w.close();}
});

test('cache bind replay accepts its committed version and external context changes cancel pending cache work',async()=>{
 const dom=new JSDOM('<span id="viewerInteractionRoute"></span>',{runScripts:'outside-only'}),w=dom.window;
 let options,cancellations=0,presented=0,cached=0;
 const store={state:{workspace:null},subscribe(){}};
 w._simulationEnvironmentWorkspace={store};w._eAPI=()=>({});w._notifyNativeViewportBounds=()=>{};
 w._cancelCacheSnapshotOpening=()=>{cancellations++;};w._completeLocalViewerPresentation=()=>{presented++;};
 w._ensureCacheSnapshotViewer=async()=>{cached++;return {visibility_context:'cache'};};
 w.AI00ViewerInteraction={frameAPI:()=>({enabled:async()=>true}),createViewerInteraction:o=>{options=o;return {close:async()=>{},ensureReady:async()=>{throw Error('online_forbidden');}};}};
 w.AI00LiveDocumentAdoption={createAdapter:()=>({invalidateControlMappings(){}}),mount(){}};
 w.AI00LiveDocumentSwitcher={createAdapter:()=>({isOwnWorkspaceChange:()=>false,cancel(){}}),mount(){}};
 try{
  w.eval(fs.readFileSync(path.join(__dirname,'live_document_bootstrap.js'),'utf8'));w.AI00LiveDocumentBootstrap();await new Promise(r=>setImmediate(r));
  store.state.workspace={workspace_gid:'1',row_version:2};
  const scope={workspace_gid:'1',document_gid:'2',expected_workspace_row_version:1,source_kind:'teamcenter_cache_snapshot'};
  options.onReady({document_gid:'2',workspace_row_version:2},scope);assert.equal(presented,1);
  assert.throws(()=>options.onReady({document_gid:'2',workspace_row_version:1},scope),/document_selection_changed/);
  assert.throws(()=>options.onReady({document_gid:'2',workspace_row_version:2},{...scope,source_kind:'teamcenter_online'}),/document_selection_changed/);
  assert.equal((await w._ensureLocalViewerReady({source_kind:'teamcenter_cache_snapshot',document_gid:'2'})).visibility_context,'cache');assert.equal(cached,1);
  cancellations=0;options.onState('closed');assert.equal(cancellations,0,'internal close during cached binding must not cancel its own job');
  w.dispatchEvent(new w.Event('ai00:live-document-changed'));assert.equal(cancellations,1);
 }finally{w.close();}
});

test('page cache-busts the dedicated-session bootstrap', () => {
  const html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');
  for (const name of ['cad_sim','viewer_document_manager','viewer_interaction','live_document_adoption','live_document_bootstrap']) {
    const version = name==='viewer_document_manager'?'rev=20260928-document-manager-1':name==='viewer_interaction'?'rev=20260928-cache-viewer-1':'rev=20260929-cache-subtree-1';
    const match=html.match(new RegExp('src="('+name+'\\.js\\?'+version+')"'));
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


function restorationPage({keys=['vmmanage:1','vmmanage:2'],bound=true,identityError=null,resume=false,realCalibration=false}={}) {
 const dom=new JSDOM('<span id="vmStatusLabel"></span>',{runScripts:'outside-only'}),w=dom.window;
 let listener,authChanged,active=keys[0],attached=null,finishIdentity=null,pending=false;
 const sessions={'vmmanage:1':'sha256:'+'b'.repeat(64),'vmmanage:2':'sha256:'+'a'.repeat(64)};
 const bindings={'10':sessions['vmmanage:2'],'20':sessions['vmmanage:1']};
 const calls=[],shown=[],resumes=[],calibrations=[],diagnostics=[],reads=[];let candidate=null,finishResume=null,delayResume=false,closeCount=0,resumeFailure=null;
 const store={state:{workspace:null},subscribe(fn){listener=fn;}};
 w._simulationEnvironmentWorkspace={store};
 w._eAPI=()=>({onAuthStateChanged:callback=>{authChanged=callback;},visMockupNativeView:{manageDocuments:async()=>({documents:keys.map(key=>({key,name:'same name',current:key===active}))}),detach:async()=>{attached=null;}}});
 w._notifyNativeViewportBounds=()=>{};w._setVmStatus=(_,message)=>{w.document.getElementById('vmStatusLabel').textContent=message;};
 w._requireConnectorRuntime=async()=>{};
 w._invokeCapability=async(id,input)=>{
   calls.push([id,input]);assert.equal(id,'simulation.environment.live_document.binding.get','automatic recovery is read-only');
   const gid=input.workspace_gid||Object.keys(bindings).find(gid=>bindings[gid]===input.identity_operation_id);
   return {workspace_gid:gid,state:bound?'bound':'unbound',document_session:bound?bindings[gid]:null};
 };
 w._requestVisMockupCommand=async id=>{
   calls.push([id]);assert.equal(id,'simulation.vismockup.document.identity.read.request');
   if(pending){pending=false;await new Promise(resolve=>{finishIdentity=resolve;});}
   if(identityError)throw Error(identityError);
   return {plan_id:sessions[active],steps:[{status:'succeeded',result:{process_id:42,document_session:sessions[active]}}]};
 };
 w._attachNativeViewport=async probe=>{assert.equal(w._liveDocumentContextUnavailable,true);active=probe.managedDocumentKey;attached=active;return {state:'attached',pid:42};};
 w._completeLocalViewerPresentation=()=>{shown.push([store.state.workspace.workspace_gid,attached]);w._liveDocumentContextUnavailable=false;};
 if(resume){
  const binding={batch_id:'a'.repeat(32),generation:'b'.repeat(32),snapshot_hash:null,schema_version:1};
  const document={document_gid:'2',source_kind:'teamcenter_cache_snapshot',cache_binding:binding,content_sha256:'sha256:'+'c'.repeat(64),product_tree:{state:'ready',nodes:[{node_key:'cache:part',cache_node_key:'part',item_revision_uid:'r',visible:null,visibility_state:'unknown'}],pages:{roots:{state:'loaded'}},node_count:1}};
  w._cacheSnapshotResumeCandidate=(workspaceGid,documentGid)=>workspaceGid==='10'&&documentGid==='2'?candidate:null;
  w._cacheSnapshotResumeCandidatesForWorkspace=workspaceGid=>workspaceGid==='10'&&candidate?[candidate]:[];
  w._forgetCacheSnapshotResumeCandidate=()=>{candidate=null;};
  w._cacheSnapshotCurrentDocument=()=>document;
  w.AI00CacheSnapshotViewer=require('./cache_snapshot_viewer');
  w._refreshModelDocuments=async()=>{};
  w._syncModelDocumentVisibility=()=>{};
  w._simulationDebug=(stage,detail)=>diagnostics.push({stage,detail});
  const local={close:async()=>{closeCount++;},get state(){return 'ready';},get visibilityContext(){return 'fresh';},
   resumeFromCache:async input=>{resumes.push(input);if(delayResume)await new Promise(resolve=>finishResume=resolve);if(resumeFailure)throw Error(resumeFailure);return {workspace_row_version:1,document_gid:'2',document_session:sessions['vmmanage:2'],visibility_context:'fresh'};},
   readVisibility:async({source_nodes})=>{reads.push(source_nodes);return {visibility_context:'fresh',structure_epoch:1,nodes:source_nodes.map(node=>({source_node_id:node.source_node_id,visibility_state:'visible',visible:true}))};}};
  w.AI00ViewerInteraction={frameAPI:()=>({enabled:async()=>true}),createViewerInteraction:()=>local};
  w.AI00LiveDocumentAdoption=realCalibration?{createAdapter:()=>require('./live_document_adoption').createAdapter({getStore:()=>store,getLocalInteraction:()=>local,ensureCachedReady:()=>{throw Error('unexpected_cache_open');}}),mount:()=>{}}
   :{createAdapter:()=>({invalidateControlMappings(){},calibrateLoadedCache:async input=>{calibrations.push(input);return {calibrated:1,unknown_count:0};}}),mount:()=>{}};
  w.__resumeFixture={binding,document};
 }else w.AI00LiveDocumentAdoption={createAdapter:()=>({invalidateControlMappings(){}}),mount:()=>{}};
 w.AI00LiveDocumentSwitcher={createAdapter:()=>({isOwnWorkspaceChange:()=>false,cancel(){}}),mount:()=>{}};
 w.eval(fs.readFileSync(path.join(__dirname,'live_document_bootstrap.js'),'utf8'));w.AI00LiveDocumentBootstrap();
 const flush=()=>new Promise(resolve=>setImmediate(resolve));
 return {dom,w,calls,shown,resumes,calibrations,diagnostics,reads,flush,get attached(){return attached;},get status(){return w.document.getElementById('vmStatusLabel').textContent;},
   enableResume:()=>{const {binding,document}=w.__resumeFixture;candidate={workspace_gid:'10',document_gid:'2',cache_binding:{...binding},package_hash:document.content_sha256,document_session:sessions['vmmanage:2'],workspace_row_version:1,identity:{...binding},node_map:{part:{instance_id:'native-part',parent_node_key:null}},excluded:[],root_node_key:'part',product_tree:{nodes:[{node_key:'cache:part',cache_node_key:'part',item_revision_uid:'r'}],pages:{roots:{state:'loaded'}},state:'ready',node_count:1}};return candidate;},
   delayResume:()=>{delayResume=true;},finishResume:()=>finishResume(),failResume:code=>{resumeFailure=code;},authLost:()=>authChanged({mode:'none'}),get closeCount(){return closeCount;},
   select:async gid=>{store.state={workspace:gid?{workspace_gid:gid,row_version:1}:null};listener(store.state);await flush();},
   close:key=>{keys=keys.filter(item=>item!==key);},delayIdentity:()=>{pending=true;},finishIdentity:()=>finishIdentity(),
   changeBinding:(gid,session)=>{bindings[gid]=session;},changeActive:key=>{active=key;}};
}

test('first W10 selection must not adopt the active small-part window; repeated switches verify separate bindings',async()=>{
 const p=restorationPage();
 for(const gid of ['10','20','10','20','10']){await p.select(gid);assert.equal(p.attached,gid==='10'?'vmmanage:2':'vmmanage:1');}
 assert.deepEqual(p.shown,[['10','vmmanage:2'],['20','vmmanage:1'],['10','vmmanage:2'],['20','vmmanage:1'],['10','vmmanage:2']]);
 assert.equal(p.w._liveDocumentContextUnavailable,false);p.dom.window.close();
});

test('switch back resumes and reads loaded cache only',async()=>{
 const p=restorationPage({resume:true,realCalibration:true});await p.select('10');await p.select('20');p.enableResume();await p.select('10');
 assert.equal(p.resumes.length,1,JSON.stringify(p.diagnostics));assert.equal(p.resumes[0].identity_operation_id,'sha256:'+'a'.repeat(64));
 assert.equal(p.resumes[0].expected_workspace_row_version,1);assert.equal(p.reads.length,1);assert.ok(p.reads.every(batch=>batch.length<=128));
 assert.equal(p.w.__resumeFixture.document.product_tree.nodes[0].visibility_state,'visible');
 assert.equal(p.w.__resumeFixture.document._cacheViewer.node_map.part.instance_id,'native-part');
 assert.equal(JSON.stringify(p.w.__resumeFixture.document).includes('_cacheViewer'),false);
 assert.equal(p.calls.some(([id])=>id.includes('open.request')),false);
 assert.ok(p.diagnostics.some(entry=>entry.stage==='environment_document_restored'));
 assert.ok(p.diagnostics.some(entry=>entry.stage==='environment_cache_controls_calibrated'));
 assert.doesNotMatch(JSON.stringify(p.diagnostics),/native-part|session_nonce|credential|private[.]jt/);
 p.dom.window.close();
});
test('missing or mismatched candidate is display only',async()=>{
 for(const mode of ['missing','batch','package','session','version','mapping']){
  const p=restorationPage({resume:true});await p.select('10');await p.select('20');
  const candidate=mode==='missing'?null:p.enableResume();
  if(mode==='batch')candidate.cache_binding.batch_id='different';
  if(mode==='package')candidate.package_hash='sha256:'+'d'.repeat(64);
  if(mode==='session')candidate.document_session='sha256:'+'e'.repeat(64);
  if(mode==='version')candidate.workspace_row_version=2;
  if(mode==='mapping')candidate.product_tree.nodes[0].item_revision_uid='different';
  await p.select('10');assert.equal(p.resumes.length,0,mode);assert.equal(p.shown.length,3,mode);
  assert.equal(p.w.__resumeFixture.document._cacheViewer,undefined,mode);
  p.dom.window.close();
 }
});
test('late cache resume cannot restore controls after selection, pagehide or auth loss',async()=>{
 for(const mode of ['selection','pagehide','auth']){
  const p=restorationPage({resume:true});await p.select('10');await p.select('20');p.enableResume();p.delayResume();
  await p.select('10');assert.equal(p.resumes.length,1);
  if(mode==='selection')await p.select('20');else if(mode==='pagehide')p.w.dispatchEvent(new p.w.Event('pagehide'));else p.authLost();
  p.finishResume();await p.flush();assert.equal(p.w.__resumeFixture.document._cacheViewer,undefined);assert.equal(p.calibrations.length,0);
  assert.equal(p.w._cacheSnapshotResumeCandidatesForWorkspace('10').length,0,mode+' must quarantine the stale candidate');p.dom.window.close();
 }
});
test('failed cache resume releases the local session while keeping the native window visible',async()=>{
 for(const code of ['interaction_bridge_timeout','authorization_expired','outcome_unknown']){
  const p=restorationPage({resume:true});await p.select('10');await p.select('20');p.enableResume();p.failResume(code);
  const before=p.closeCount;await p.select('10');
  assert.equal(p.resumes.length,1,code);assert.ok(p.closeCount>before+1,code+' must close after the selection close');
  assert.equal(p.w._cacheSnapshotResumeCandidatesForWorkspace('10').length,0,code);
  assert.equal(p.w.__resumeFixture.document._cacheViewer,undefined,code);
  assert.equal(p.attached,'vmmanage:2',code);
  p.dom.window.close();
 }
});

test('closed bound window never falls back to another current document',async()=>{
 const p=restorationPage();await p.select('10');await p.select('20');p.close('vmmanage:2');await p.select('10');
 assert.equal(p.attached,null);assert.equal(p.w._liveDocumentContextUnavailable,true);assert.match(p.status,/已关闭|关联失效/);
 assert.equal(p.shown.length,2);p.dom.window.close();
});

test('unbound environment does not preview or associate the current window',async()=>{
 const p=restorationPage({bound:false});await p.select('10');assert.equal(p.attached,null);assert.equal(p.shown.length,0);
 assert.match(p.status,/未关联/);p.dom.window.close();
});

test('binding changes invalidate a cached environment-to-window association',async()=>{
 const p=restorationPage();await p.select('10');await p.select('20');p.changeBinding('10','missing-session');await p.select('10');
 assert.equal(p.attached,null);assert.equal(p.shown.length,2);p.dom.window.close();
});

test('late identity result cannot reveal a document after switching environments',async()=>{
 const p=restorationPage();p.delayIdentity();await p.select('10');await p.select('20');p.finishIdentity();await p.flush();
 assert.deepEqual(p.shown,[['20','vmmanage:1']]);assert.equal(p.attached,'vmmanage:1');p.dom.window.close();
});

test('identity read failure leaves viewport unavailable and does not claim restored',async()=>{
 const p=restorationPage({identityError:'vismockup_process_identity_unavailable'});await p.select('10');
 assert.equal(p.attached,null);assert.equal(p.shown.length,0);assert.match(p.status,/未能恢复/);p.dom.window.close();
});

test('active window changing during identity read cannot be remembered',async()=>{
 const p=restorationPage();p.delayIdentity();await p.select('10');p.changeActive('vmmanage:2');p.finishIdentity();await p.flush();
 assert.equal(p.attached,null);assert.equal(p.shown.length,0);assert.match(p.status,/未能恢复/);p.dom.window.close();
});
