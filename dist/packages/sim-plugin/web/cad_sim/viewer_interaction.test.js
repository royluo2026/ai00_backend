const test=require('node:test'),assert=require('node:assert/strict');
const {createViewerInteraction,sourceDescriptor}=require('./viewer_interaction');
test('missing own geometry marks every compact-map ancestor incomplete without excluding valid siblings',()=>{
 const {cacheIncompleteAncestors}=require('./viewer_interaction');
 const viewer={node_map:{root:{instance_id:'r',parent_node_key:null},group:{instance_id:'g',parent_node_key:'root'},missing:{instance_id:'m',parent_node_key:'group'},sibling:{instance_id:'s',parent_node_key:'root'}},excluded:[{node_key:'missing'}]};
 assert.deepEqual([...cacheIncompleteAncestors(viewer)],['group','root']);
 assert.equal(cacheIncompleteAncestors(viewer).has('sibling'),false);
});
test('cached source descriptors use generated instance paths before root shortcuts',()=>{
 const node={node_key:'cache:n',cache_node_key:'n',parent_key:null,has_children:false,item_revision_uid:'revision',occurrence_path:[]};
 const document={source_kind:'teamcenter_cache_snapshot',product_tree:{nodes:[node]},_cacheViewer:{node_map:{root:{instance_id:'instance-root',parent_node_key:null},n:{instance_id:'instance-n',parent_node_key:'root'}}}};
 assert.deepEqual(sourceDescriptor(document,node),{source_node_id:'cache:n',kind:'occurrence_path',occurrence_path:[{occurrence_uid:'instance-root',item_revision_uid:'revision'},{occurrence_uid:'instance-n',item_revision_uid:'revision'}]});
 document._cacheViewer.excluded=[{node_key:'n',reason:'transform_missing'}];assert.throws(()=>sourceDescriptor(document,node),/cache_node_excluded/);
 document._cacheViewer.excluded=[];document._cacheViewer.node_map.root.parent_node_key='n';assert.throws(()=>sourceDescriptor(document,node),/cache_node_mapping_invalid/);
 document._cacheViewer.node_map.root.parent_node_key=null;delete document._cacheViewer.node_map.root;assert.throws(()=>sourceDescriptor(document,node),/cache_node_mapping_invalid/);
});
test('cached controller opens and calibrates without an online readiness call',async()=>{
 const calls=[],scope={workspace_gid:'1',document_gid:'2'},source_nodes=[{source_node_id:'n',kind:'document_root'}];
 const c=createViewerInteraction({api:{openFromCache:async input=>{calls.push(input);return {status:'completed',result:{interaction_id:'cache-session',visibility_context:'context',...scope}};},ensureReady:()=>{throw Error('online_forbidden');},readVisibility:async input=>({status:'completed',result:{nodes:[],visibility_context:'context'}}),executeCachedIntent:async input=>{calls.push(input);return {status:'completed',result:{}};},close:async()=>{},cancelOpen:async()=>{}}});
 assert.equal((await c.openFromCache(scope)).visibility_context,'context');assert.deepEqual(c.scope,scope);
 assert.equal((await c.readVisibility({source_nodes})).visibility_context,'context');
 assert.equal((await c.executeCachedIntent({...scope,source_nodes,action:'hide',visibility_context:'context'})).visible,false);
 await c.close();await assert.rejects(c.executeCachedIntent({...scope,source_nodes,action:'show',visibility_context:'context'}),/cache_document_not_ready/);
 assert.equal(calls.length,2);
});
test('page cache resume uses its own bridge and late completion is fenced',async()=>{
 const input={workspace_gid:'1',document_gid:'2',identity_operation_id:'fresh',expected_document_session:'sha256:'+'a'.repeat(64),expected_workspace_row_version:2,idempotency_key:'resume'};
 let finish,closed=[];const c=createViewerInteraction({api:{resumeFromCache:()=>new Promise(resolve=>finish=resolve),openFromCache:()=>{throw Error('old_open_forbidden');},close:async p=>closed.push(p),cancelOpen:async()=>{}}});
 const pending=c.resumeFromCache(input);await new Promise(r=>setImmediate(r));await c.close();
 finish({status:'completed',result:{interaction_id:'late',document_gid:'2',workspace_row_version:2,visibility_context:'context'}});
 await assert.rejects(pending,/document_selection_changed/);assert.deepEqual(closed,[{interaction_id:'late'}]);assert.equal(c.state,'closed');
});
test('a replaced readiness context cannot execute an intent calibrated against the old document',async()=>{
 let writes=0;const c=createViewerInteraction({api:{ensureReady:async()=>({status:'completed',result:{visibility_context:'new-context'}}),executeIntent:async()=>{writes++;return {status:'completed',result:{}};}}});
 await assert.rejects(c.executeIntent({scope:{workspace_gid:'1',document_gid:'2'},source_selector:{},source_nodes:[{source_node_id:'front',kind:'document_root'}],action:'show',visibility_context:'old-context'}),/visibility_calibration_required/);assert.equal(writes,0);
});
test('calibration forwards readiness intent and reads actual visibility without a native write',async()=>{
 const source_nodes=[{source_node_id:'front',kind:'document_root'}],result={nodes:[{source_node_id:'front',visible:null,visibility_state:'mixed'}],structure_epoch:3};
 const c=createViewerInteraction({api:{ensureReady:async input=>{assert.deepEqual(input.source_nodes,source_nodes);assert.equal(input.action,'show');return {status:'completed',result:{visibility_context:'session-1'}};},readVisibility:async input=>{assert.deepEqual(input,{workspace_gid:'1',document_gid:'2',source_nodes});return {status:'completed',result};},executeIntent:async()=>{throw Error('unexpected_write');}}});
 assert.equal((await c.ensureReady({scope:{workspace_gid:'1',document_gid:'2'},source_selector:{},source_nodes,action:'show'})).visibility_context,'session-1');
 assert.equal(await c.readVisibility({source_nodes}),result);
});

test('closing a document fences late visibility readback',async()=>{
 let finish;const c=createViewerInteraction({api:{ensureReady:async()=>({status:'completed',result:{}}),readVisibility:()=>new Promise(resolve=>finish=resolve),cancelOpen:async()=>{}}});
 await c.ensureReady({scope:{workspace_gid:'1',document_gid:'2'},source_selector:{}});const reading=c.readVisibility({source_nodes:[]});await c.close();finish({status:'completed',result:{nodes:[]}});await assert.rejects(reading,/document_selection_changed/);assert.equal(c.state,'closed');
});
test('node intent reaches readiness and cancellation prevents execution',async()=>{
 const source_nodes=[{source_node_id:'front',kind:'occurrence_path',occurrence_path:[{occurrence_uid:'a',item_revision_uid:'r'}]}];let executed=false;
 const c=createViewerInteraction({api:{ensureReady:async input=>{assert.deepEqual(input.source_nodes,source_nodes);assert.equal(input.action,'show');return {status:'rejected',error_code:'confirmation_cancelled'};},executeIntent:async()=>{executed=true;}}});
 await assert.rejects(c.executeIntent({scope:{workspace_gid:'1',document_gid:'2'},source_selector:{},source_nodes,action:'show'}),/confirmation_cancelled/);
 assert.equal(executed,false);
});
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
test('demand-driven hide then show coalesces to one Main intent with final absolute state',async()=>{
 let finish;const calls=[];
 const c=createViewerInteraction({api:{ensureReady:async()=>({status:'completed',result:{}}),executeIntent:input=>{calls.push(input);return new Promise(resolve=>finish=resolve);}}});
 const scope={workspace_gid:'1',document_gid:'2',expected_workspace_row_version:3},source_selector={endpoint_id:'ep'};
 const source_nodes=[{source_node_id:'n',kind:'single_part_root'}];
 const hide=c.executeIntent({scope,source_selector,source_nodes,action:'hide'});
 const show=c.executeIntent({scope,source_selector,source_nodes,action:'show'});
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(calls.length,1);assert.equal(calls[0].action,'show');
 finish({status:'completed',result:{targets:[{status:'completed'}]}});
 assert.equal((await hide).visible,true);assert.equal((await show).visible,true);
});
test('demand-driven intents preserve order across distinct targets and outcome unknown blocks writes',async()=>{
 const calls=[];const c=createViewerInteraction({api:{ensureReady:async()=>({status:'completed',result:{}}),executeIntent:async input=>{calls.push(input.source_nodes[0].source_node_id);return input.source_nodes[0].source_node_id==='b'?{status:'outcome_unknown'}:{status:'completed',result:{targets:[{status:'completed'}]}};}}});
 const base={scope:{workspace_gid:'1',document_gid:'2',expected_workspace_row_version:3},source_selector:{endpoint_id:'ep'}};
 const first=c.executeIntent({...base,source_nodes:[{source_node_id:'a',kind:'single_part_root'}],action:'hide'});
 const second=c.executeIntent({...base,source_nodes:[{source_node_id:'b',kind:'single_part_root'}],action:'highlight'});
 await first;await assert.rejects(second,/outcome_unknown/);
 await assert.rejects(c.executeIntent({...base,source_nodes:[{source_node_id:'c',kind:'single_part_root'}],action:'show'}),/outcome_unknown/);
 assert.deepEqual(calls,['a','b']);
});
test('environment selection alone does not invoke Main open',()=>{
 let calls=0;createViewerInteraction({api:{ensureReady:async()=>{calls++;}}});assert.equal(calls,0);
});

test('readiness completion reconciles page version and view before dispatching the intent',async()=>{
 const steps=[],scope={workspace_gid:'1',document_gid:'2',expected_workspace_row_version:3};
 const result={document_gid:'2',workspace_row_version:4};
 const c=createViewerInteraction({onReady:(value,current)=>{assert.equal(value,result);assert.equal(current,scope);steps.push('ready');},api:{
  ensureReady:async()=>({status:'completed',result}),
  executeIntent:async()=>{steps.push('execute');return {status:'completed',result:{}};}
 }});
 await c.executeIntent({scope,source_selector:{endpoint_id:'ep'},source_nodes:[{source_node_id:'n',kind:'single_part_root'}],action:'show'});
 assert.deepEqual(steps,['ready','execute']);
});

test('a cancelled readiness completion never reconciles the page',async()=>{
 let finish,ready=0;
 const c=createViewerInteraction({onReady:()=>ready++,api:{ensureReady:()=>new Promise(r=>finish=r),cancelOpen:async()=>{}}});
 const opening=c.ensureReady({scope:{workspace_gid:'1',document_gid:'2'},source_selector:{}});
 await c.close();finish({status:'completed',result:{}});
 await assert.rejects(opening,/document_selection_changed/);assert.equal(ready,0);
});
test('demand-driven close always releases Main and fences a late readiness result',async()=>{
 let finish,released=0;const c=createViewerInteraction({api:{ensureReady:()=>new Promise(resolve=>finish=resolve),cancelOpen:async()=>{released++;return {status:'completed'};}}});
 const pending=c.ensureReady({scope:{workspace_gid:'1',document_gid:'2',expected_workspace_row_version:1},source_selector:{endpoint_id:'ep'}});await new Promise(resolve=>setImmediate(resolve));
 await c.close();assert.equal(released,1);finish({status:'completed',result:{document_gid:'2',workspace_row_version:1}});
 await assert.rejects(pending,/document_selection_changed/);assert.equal(c.state,'closed');
});
test('opening permits confirmation while execution has a bounded 90s bridge deadline',async()=>{
 const {MessageChannel}=require('node:worker_threads'),{frameAPI}=require('./viewer_interaction');
 const timers=new Map(),ports=[],channels=[];let next=0;
 const win={MessageChannel:class extends MessageChannel{constructor(){super();channels.push(this);}},crypto:require('node:crypto'),location:{origin:'app://root'},
  setTimeout:(fn,ms)=>{timers.set(++next,{fn,ms});return next;},clearTimeout:id=>timers.delete(id),
  parent:{electronAPI:{},postMessage:(_message,_origin,p)=>ports.push(p[0])}};
 const api=frameAPI(win);
 try{
  for(const method of ['ensureReady','openFromLaunch','execute']){
   let error=null;const pending=api[method]({}).catch(e=>{error=e;});
   const timer=timers.get(next);
   assert.equal(timer.ms,method==='execute'?90000:3600000);
   if(method==='execute')timer.fn();
   ports.at(-1).postMessage({result:{status:'completed',result:{interaction_id:'session'}}});
   await pending;
   assert.equal(error?.message||null,method==='execute'?'outcome_unknown':null,method);
  }
 }finally{for(const channel of channels){channel.port1.close();channel.port2.close();}}
});
test('model intent bridge waits for bounded native mapping before declaring outcome unknown',async()=>{
 const {MessageChannel}=require('node:worker_threads'),{frameAPI}=require('./viewer_interaction');
 const timers=[],ports=[];
 const win={MessageChannel,crypto:require('node:crypto'),location:{origin:'app://root'},
  setTimeout:(fn,ms)=>{timers.push({fn,ms});return timers.length;},clearTimeout:()=>{},
  parent:{electronAPI:{},postMessage:(_message,_origin,p)=>ports.push(p[0])}};
 const pending=frameAPI(win).executeIntent({action:'show'});
 try{
  assert.equal(timers[0].ms,120000);
  for(const timer of timers)if(timer.ms<=60000)timer.fn();
  ports[0].postMessage({result:{status:'completed',result:{targets:[{status:'completed'}]}}});
  assert.equal((await pending).status,'completed');
 }finally{for(const port of ports)port.close();}
});
test('node resolution bridge outlives the native mapping deadline',async()=>{
 const {MessageChannel}=require('node:worker_threads'),{frameAPI}=require('./viewer_interaction');
 const timers=[],ports=[];
 const win={MessageChannel,crypto:require('node:crypto'),location:{origin:'app://root'},
  setTimeout:(fn,ms)=>{timers.push({fn,ms});return timers.length;},clearTimeout:()=>{},
  parent:{electronAPI:{},postMessage:(_message,_origin,p)=>ports.push(p[0])}};
 const pending=frameAPI(win).resolve({interaction_id:'session'});
 try{
  assert.ok(timers[0].ms>=35000);
  ports[0].postMessage({result:{status:'completed',result:{nodes:[]}}});
  assert.equal((await pending).status,'completed');
 }finally{for(const port of ports)port.close();}
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
 const dom=new JSDOM('<span id="viewerInteractionRoute"></span><span data-viewer-interaction-route></span>',{runScripts:'outside-only'}),w=dom.window;
 let onState;
 w.AI00ViewerInteraction={frameAPI:()=>({enabled:async()=>true}),createViewerInteraction:options=>{onState=options.onState;return {close:async()=>{}};}};
 w._eAPI=()=>({});w._notifyNativeViewportBounds=()=>{};
 w.AI00LiveDocumentAdoption={createAdapter:()=>({}),mount:()=>{}};
 w.AI00LiveDocumentSwitcher={createAdapter:()=>({}),mount:()=>{}};
 w.eval(fs.readFileSync(path.join(__dirname,'live_document_bootstrap.js'),'utf8'));w.AI00LiveDocumentBootstrap();
 await w._localViewerInteractionEnabled();
 const marker=w.document.getElementById('viewerInteractionRoute');assert.equal(marker.dataset.route,'local');assert.match(marker.textContent,/本地/);
 onState('opening');assert.match(marker.textContent,/正在打开/);assert.equal(marker.getAttribute('aria-busy'),'true');
 assert.equal(w.document.querySelector('[data-viewer-interaction-route]').textContent,marker.textContent);
 onState('executing','hide');assert.match(marker.textContent,/正在隐藏/);
 onState('ready');assert.match(marker.textContent,/就绪/);assert.equal(marker.getAttribute('aria-busy'),'false');
 onState('outcome_unknown');assert.match(marker.textContent,/结果未知/);assert.equal(marker.dataset.state,'outcome_unknown');dom.window.close();
});

test('node intent stays opening until ready and executing until the native result returns',async()=>{
 let finishOpen,finishExecute;const states=[];
 const controller=createViewerInteraction({api:{ensureReady:()=>new Promise(r=>finishOpen=r),executeIntent:()=>new Promise(r=>finishExecute=r)},onState:(...state)=>states.push(state)});
 const pending=controller.executeIntent({scope:{workspace_gid:'1',document_gid:'2'},source_selector:{},source_nodes:[],action:'show'});
 await new Promise(r=>setImmediate(r));assert.equal(controller.state,'opening');
 finishOpen({status:'completed',result:{}});await new Promise(r=>setImmediate(r));
 assert.equal(controller.state,'executing');assert.deepEqual(states.at(-1),['executing','show']);
 finishExecute({status:'completed'});await pending;assert.equal(controller.state,'ready');
});

test('bootstrap readiness removes the unavailable overlay and reconciles the selected version',async()=>{
 const {JSDOM}=require('jsdom'),fs=require('node:fs'),path=require('node:path');
 const dom=new JSDOM('<span id="viewerInteractionRoute"></span>',{runScripts:'outside-only'}),w=dom.window;
 const workspace={workspace_gid:'1',row_version:3,cache_revision_hash:'old'};
 w._simulationEnvironmentWorkspace={store:{state:{workspace},subscribe:()=>{}}};
 w._liveDocumentContextUnavailable=true;
 w.AI00ViewerInteraction={createViewerInteraction,frameAPI:()=>({enabled:async()=>true,cancelOpen:async()=>{},ensureReady:async()=>({status:'completed',result:{document_gid:'2',workspace_row_version:4}})})};
 w._eAPI=()=>({});w._notifyNativeViewportBounds=()=>{};
 w._setVmStatus=(state,message)=>{w.__status={state,message};};
 w._completeLocalViewerPresentation=()=>{w._liveDocumentContextUnavailable=false;w._setVmStatus('connected','已内嵌');};
 w.AI00LiveDocumentAdoption={createAdapter:()=>({invalidateControlMappings:()=>{}}),mount:()=>{}};
 w.AI00LiveDocumentSwitcher={createAdapter:()=>({isOwnWorkspaceChange:()=>false,cancel:()=>{}}),mount:()=>{}};
 w.eval(fs.readFileSync(path.join(__dirname,'live_document_bootstrap.js'),'utf8'));w.AI00LiveDocumentBootstrap();
 await w._localViewerInteractionEnabled();
 await w._ensureLocalViewerReady({document_gid:'2',source_selector:{endpoint_id:'ep'}});
 assert.equal(w._liveDocumentContextUnavailable,false);assert.equal(workspace.row_version,4);
 assert.equal(workspace.cache_revision_hash,undefined);assert.equal(w.__status.message,'已内嵌');
 dom.window.close();
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
