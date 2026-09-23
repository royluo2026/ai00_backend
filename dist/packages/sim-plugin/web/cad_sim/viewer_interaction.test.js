const test=require('node:test'),assert=require('node:assert/strict');
const {createViewerInteraction,sourceDescriptor}=require('./viewer_interaction');
test('environment cancellation fences a Main open before it can attach',async()=>{
 let finish,cancelled=0;
 const c=createViewerInteraction({api:{openFromLaunch:()=>new Promise(resolve=>finish=resolve),cancelOpen:async()=>{cancelled++;},close:async()=>{}}});
 const opening=c.openFromLaunch({workspace_gid:'1',document_gid:'2'});await new Promise(r=>setImmediate(r));
 await c.close();assert.equal(cancelled,1);
 finish({status:'rejected',error_code:'interaction_owner_invalid'});
 await assert.rejects(opening,/document_selection_changed/);
});
test('bridge timeout followed by environment change sends cancellation before late completion',async()=>{
 const {MessageChannel}=require('node:worker_threads'),{frameAPI}=require('./viewer_interaction');
 const requests=[],timers=new Map();let next=0;
 const win={MessageChannel,crypto:require('node:crypto'),location:{origin:'app://root'},setTimeout:fn=>{timers.set(++next,fn);return next;},clearTimeout:id=>timers.delete(id),parent:{electronAPI:{},postMessage:(message,_origin,ports)=>requests.push({message,port:ports[0]})}};
 const controller=createViewerInteraction({api:frameAPI(win)}),tick=()=>new Promise(r=>setImmediate(r));
 try{
  const opening=controller.openFromLaunch({workspace_gid:'1',document_gid:'2'}),failed=assert.rejects(opening,/interaction_bridge_timeout/);
  await tick();timers.get(1)();await failed;
  const closing=controller.close();await tick();
  assert.equal(requests[1]?.message.method,'cancelOpen');
  requests[1].port.postMessage({result:{status:'completed',result:null}});await closing;
  requests[0].port.postMessage({result:{status:'rejected',error_code:'interaction_owner_invalid'}});
  await tick();assert.equal(controller.state,'closed');assert.equal(controller.scope,null);
 }finally{for(const request of requests)request.port.close();}
});
test('timed-out iframe open closes its late session before admitting another open',async()=>{
 const {MessageChannel}=require('node:worker_threads');
 const {frameAPI}=require('./viewer_interaction');
 const timers=new Map(),requests=[];let next=0;
 const win={MessageChannel,crypto:require('node:crypto'),location:{origin:'app://root'},
  setTimeout:fn=>{timers.set(++next,fn);return next;},clearTimeout:id=>timers.delete(id),
  parent:{electronAPI:{},postMessage:(message,_origin,ports)=>requests.push({message,port:ports[0]})}};
 const api=frameAPI(win),input={workspace_gid:'1',document_gid:'2'};
 const tick=()=>new Promise(resolve=>setTimeout(resolve,15));
 try {
  const opening=api.open(input),failed=assert.rejects(opening,/interaction_bridge_timeout/);
  timers.get(1)();await failed;
  requests[0].port.postMessage({result:{status:'completed',result:{interaction_id:'late-session'}}});
  await tick();
  assert.equal(requests.length,2,'late successful open must issue close, never execute or reopen');
  assert.equal(requests[1].message.method,'close');
  assert.deepEqual(requests[1].message.input,{interaction_id:'late-session'});
  await assert.rejects(api.open(input),/interaction_open_pending/);
  requests[1].port.postMessage({result:{status:'completed',result:null}});await tick();
  const retry=api.open(input);
  assert.equal(requests[2].message.method,'open');
  requests[2].port.postMessage({result:{status:'completed',result:{interaction_id:'new-session'}}});
  assert.equal((await retry).result.interaction_id,'new-session');
 }finally{for(const request of requests)request.port.close();}
});
test('failed late-open cleanup stays fenced and execute timeout never resends',async()=>{
 const {MessageChannel}=require('node:worker_threads');
 const {frameAPI}=require('./viewer_interaction');
 const timers=new Map(),requests=[];let next=0;
 const win={MessageChannel,crypto:require('node:crypto'),location:{origin:'app://root'},
  setTimeout:fn=>{timers.set(++next,fn);return next;},clearTimeout:id=>timers.delete(id),
  parent:{electronAPI:{},postMessage:(message,_origin,ports)=>requests.push({message,port:ports[0]})}};
 const api=frameAPI(win),input={workspace_gid:'1',document_gid:'2'};
 const tick=()=>new Promise(resolve=>setTimeout(resolve,15));
 try {
  const failed=assert.rejects(api.open(input),/interaction_bridge_timeout/);timers.get(1)();await failed;
  requests[0].port.postMessage({result:{status:'completed',result:{interaction_id:'late'}}});await tick();
  requests[1].port.postMessage({result:{status:'rejected',error_code:'interaction_pipe_closed'}});await tick();
  await assert.rejects(api.open(input),/interaction_open_pending/);assert.equal(requests.length,2);
  const unknown=assert.rejects(api.execute({interaction_id:'late'}),/outcome_unknown/);
  timers.get(3)();await unknown;
  requests[2].port.postMessage({result:{status:'completed'}});await tick();
  assert.equal(requests.length,3,'execute timeout must not replay or issue fallback');
 }finally{for(const request of requests)request.port.close();}
});
test('runtime scanner requires an owned exception for the local iframe transport',()=>{
 const {runtimeCalls}=require('../../../../scripts/test_no_desktop_business_bypass');
 const fs=require('node:fs');
 const calls=runtimeCalls(fs.readFileSync(require('node:path').join(__dirname,'viewer_interaction.js'),'utf8'),'packages/sim-plugin/web/cad_sim/viewer_interaction.js').hits;
 assert.equal(calls.filter(c=>c.rule==='local_viewer_transport').length,1);
 const allow=require('../../../../scripts/desktop_runtime_allowlist.json');
 assert.ok(allow.some(a=>a.file==='packages/sim-plugin/web/cad_sim/viewer_interaction.js'&&a.call_sha256===calls[0].call_sha256&&a.source_sha256===calls[0].source_sha256),'current bridge must retain its exact owned transport exception');
 assert.equal(runtimeCalls('fetch("http://localhost:9999/execute")','web/fixture.js').hits.length,1);
 assert.equal(runtimeCalls('new ActiveXObject("VisMockup")','web/fixture.js').hits.length,1);
});
test('production adoption uses local session without binding.get or command.get',async()=>{
 const {createAdapter}=require('./live_document_adoption');
 const document={document_gid:'2',source_kind:'teamcenter_online',product_tree:{nodes:[{node_key:'n',parent_key:null,has_children:false,occurrence_path:[]}]}};
 const local={scope:{workspace_gid:'1',document_gid:'2'},execute:async input=>({ok:true,visible:input.action==='show'})};
 const adapter=createAdapter({getStore:()=>({state:{workspace:{workspace_gid:'1'}}}),getLocalInteraction:()=>local,invoke:()=>{throw Error('cloud_forbidden');}});
 const result=await adapter.actOnProductNode({workspaceGid:'1',document,nodeKey:'n',action:'hide'});assert.equal(result.visible,false);
});
test('four actions reuse one mapping and use opaque targets without cloud calls',async()=>{
 const calls=[],states=[];
 const api={open:async()=>({status:'completed',result:{interaction_id:'session'}}),close:async()=>({status:'completed'}),
  resolve:async input=>{calls.push(['resolve',input]);return {status:'completed',result:{structure_epoch:3,nodes:[{source_node_id:'n',status:'mapped',node_ref:'opaque'}]}};},
  execute:async input=>{calls.push(['execute',input]);return {status:'completed',result:{targets:[{node_ref:'opaque',status:'completed'}]}};}};
 const c=createViewerInteraction({api,onState:s=>states.push(s)});
 await c.open({workspace_gid:'1',document_gid:'2'});
 for(const action of ['show','hide','highlight','unhighlight'])await c.execute({source_nodes:[{source_node_id:'n',kind:'single_part_root'}],action});
 assert.equal(calls.filter(c=>c[0]==='resolve').length,1);
 assert.deepEqual(calls.filter(c=>c[0]==='execute').map(c=>c[1].arguments.action),['show','hide','highlight','unhighlight']);
 assert.ok(calls.filter(c=>c[0]==='execute').every(c=>c[1].targets[0]==='opaque'));
 assert.equal(states.at(-1),'ready');
});
test('outcome unknown blocks further writes and never reports success',async()=>{
 let writes=0;const c=createViewerInteraction({api:{open:async()=>({status:'completed',result:{interaction_id:'s'}}),resolve:async()=>({status:'completed',result:{structure_epoch:1,nodes:[{source_node_id:'n',status:'mapped',node_ref:'r'}]}}),execute:async()=>{writes++;return {status:'outcome_unknown'};}}});
 await c.open({workspace_gid:'1',document_gid:'2'});
 const input={source_nodes:[{source_node_id:'n',kind:'single_part_root'}],action:'hide'};
 await assert.rejects(c.execute(input),/outcome_unknown/);await assert.rejects(c.execute(input),/outcome_unknown/);assert.equal(writes,1);
});
test('descriptor reuses exact occurrence edges and fails closed for ambiguous roots',()=>{
 const node={node_key:'tc:hash',occurrence_path:[{occurrence_uid:'o',item_revision_uid:'r'}]};
 assert.deepEqual(sourceDescriptor({product_tree:{nodes:[node]}},node),{source_node_id:'tc:hash',kind:'occurrence_path',occurrence_path:node.occurrence_path});
 assert.throws(()=>sourceDescriptor({product_tree:{nodes:[{},{ }]}},{node_key:'root',occurrence_path:[],has_children:true}),/unmapped/);
});
test('proven opened single leaf root takes precedence over retained assembly ancestor path',()=>{
 const node={node_key:'leaf',parent_key:null,has_children:false,occurrence_path:[{occurrence_uid:'assembly',item_revision_uid:'assembly-rev'},{occurrence_uid:'leaf',item_revision_uid:'leaf-rev'}]};
 assert.deepEqual(sourceDescriptor({product_tree:{nodes:[node]}},node),{source_node_id:'leaf',kind:'single_part_root'});
 assert.equal(sourceDescriptor({product_tree:{nodes:[node,{}]}},node).kind,'occurrence_path');
 assert.equal(sourceDescriptor({product_tree:{nodes:[{...node,has_children:true}]}},{...node,has_children:true}).kind,'occurrence_path');
});
test('late mapping failure cannot overwrite a newly opened session state',async()=>{
 let finish,opens=0;
 const c=createViewerInteraction({api:{open:async()=>({status:'completed',result:{interaction_id:String(++opens)}}),close:async()=>({status:'completed'}),resolve:()=>new Promise(resolve=>finish=resolve)}});
 await c.open({workspace_gid:'1',document_gid:'2'});
 const pending=c.resolve([{source_node_id:'n',kind:'single_part_root'}]);
 await c.open({workspace_gid:'1',document_gid:'3'});
 finish({status:'rejected',error_code:'authorization_expired'});
 await assert.rejects(pending,/document_selection_changed/);assert.equal(c.state,'ready');assert.equal(c.scope.document_gid,'3');
});
test('partial or not-started target results never update UI as a completed action',async()=>{
 const c=createViewerInteraction({api:{open:async()=>({status:'completed',result:{interaction_id:'s'}}),resolve:async()=>({status:'completed',result:{structure_epoch:1,nodes:[{source_node_id:'n',status:'mapped',node_ref:'r'}]}}),execute:async()=>({status:'completed',result:{targets:[{node_ref:'r',status:'not_started',error_code:'viewer_busy'}]}})}});
 await c.open({workspace_gid:'1',document_gid:'2'});
 await assert.rejects(c.execute({source_nodes:[{source_node_id:'n',kind:'single_part_root'}],action:'hide'}),/viewer_busy/);
});
test('visible route marker distinguishes Main enabled local from cloud and unknown',async()=>{
 const {JSDOM}=require('jsdom'),fs=require('node:fs'),path=require('node:path');
 const dom=new JSDOM('<span id="viewerInteractionRoute"></span>',{runScripts:'outside-only'}),w=dom.window;
 let onState;
 w.AI00ViewerInteraction={frameAPI:()=>({enabled:async()=>true}),createViewerInteraction:options=>{onState=options.onState;return {close:async()=>{}};}};
 w._eAPI=()=>({});w._notifyNativeViewportBounds=()=>{};
 w.AI00LiveDocumentAdoption={createAdapter:()=>({}),mount:()=>{}};
 w.AI00LiveDocumentSwitcher={createAdapter:()=>({}),mount:()=>{}};
 w.eval(fs.readFileSync(path.join(__dirname,'live_document_bootstrap.js'),'utf8'));w.AI00LiveDocumentBootstrap();
 await w._localViewerInteractionEnabled();
 const marker=w.document.getElementById('viewerInteractionRoute');assert.equal(marker.dataset.route,'local');assert.match(marker.textContent,/本地/);
 onState('outcome_unknown');assert.match(marker.textContent,/结果未知/);assert.equal(marker.dataset.state,'outcome_unknown');dom.window.close();
});
test('VM node action uses the bound source descriptor locally and never probes cloud',async()=>{
 const {JSDOM}=require('jsdom'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
 const dom=new JSDOM('',{runScripts:'outside-only'}),w=dom.window;
 w.AI00ViewerInteraction={sourceDescriptor};
 vm.runInContext(fs.readFileSync(path.join(__dirname,'cad_sim.js'),'utf8'),dom.getInternalVMContext());
 w.eval(`_vmConnected=true;_modelDocumentCollection={state:{documents:[{document_gid:'2',product_tree:{nodes:[{node_key:'tc:key',occurrence_path:[{occurrence_uid:'o',item_revision_uid:'r'}]}]}}]}};
 window._localViewerInteraction=()=>({scope:{document_gid:'2'},execute:async input=>{window.__input=input;return {ok:true,visible:false};}});
 _requestVisMockupCommand=async()=>{throw Error('cloud_forbidden');};_cmdShow=()=>{};_updateVisVisibilityControls=()=>{};_updateAlternateVisibilityControls=()=>{};`);
 const result=await w._visNodeAction('tc:key','hide');assert.equal(result.ok,true);assert.equal(w.__input.source_nodes[0].kind,'occurrence_path');dom.window.close();
});
