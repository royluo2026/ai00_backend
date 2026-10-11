const test=require('node:test'),assert=require('node:assert/strict');
const {create,mergeLoadedBranches,captureResumeCandidate,prepareResumeDocument}=require('./cache_snapshot_viewer');
const identity={batch_id:'a'.repeat(32),generation:'b'.repeat(32),snapshot_hash:null,schema_version:1};
const input={workspace_gid:'1',document_gid:'2',cache_binding:identity,root_node_key:'part'};
function rig(overrides={},options={}){
 const calls=[],progress=[];let count=0,current=true;
 const handlers={
  'simulation.environment.cache_source.materialization.inspect':async()=>({identity,files:[{node_key:'part',item_revision_uid:'r',dataset_uid:'d',file_uid:'f',file_name:'part.jt',relation_type:'IMAN_Rendering',operation_id:null}],file_count:1,node_count:1,excluded:[],materialization_hash:'fixed',next_cursor:null}),
  'simulation.environment.workspace.get':async()=>({workspace_gid:'1',row_version:1}),
  'simulation.environment.cache_source.open.request':async()=>({identity,operation_id:'open',package_hash:'package',node_map:{part:{instance_id:'instance',parent_node_key:null}},excluded:[]}),
  'simulation.vismockup.command.get':async()=>({operation_id:'open',status:'completed',outcome:{steps:[{status:'succeeded',result:{protocol:'ai00.viewer.opened-tc-cache.v1',package_hash:'package',cache_binding:identity}}]}}),
  ...overrides
 };
 const controller=create({invoke:async(id,p,o)=>{calls.push({id,p,o});if(!handlers[id])throw Error('unexpected_upload_path:'+id);return handlers[id](p,o);},
  interaction:{openFromCache:async()=>({document_gid:'2',workspace_row_version:2,visibility_context:{}})},isCurrent:()=>current,
  onProgress:p=>progress.push(p),delay:async()=>{},randomId:()=>String(++count),...options});
 return {controller,calls,progress,leave(){current=false;}};
}
test('navigation cancels the submitted operation and never binds its late result',async()=>{
 const cancelled=[];let r,bound=false;
 r=rig({'simulation.vismockup.command.get':async()=>{r.controller.invalidate();return {operation_id:'open',status:'running'};}},
  {cancelOpen:async id=>cancelled.push(id),interaction:{openFromCache:async()=>{bound=true;}}});
 await assert.rejects(r.controller.open(input),/cache_open_interrupted/);
 assert.deepEqual(cancelled,['open']);assert.equal(bound,false);
});
test('admission returning after navigation still cancels its exact operation',async()=>{
 const cancelled=[];let r;
 r=rig({'simulation.environment.cache_source.open.request':async()=>{r.controller.invalidate();return {identity,operation_id:'late',node_map:{},excluded:[]};}},
  {cancelOpen:async id=>cancelled.push(id)});
 await assert.rejects(r.controller.open(input),/cache_open_interrupted/);assert.deepEqual(cancelled,['late']);
 assert.equal(r.calls.some(c=>c.id==='simulation.vismockup.command.get'),false);
});
test('cancellation transport failure is logged without claiming the native task stopped',async()=>{
 let r;
 r=rig({'simulation.vismockup.command.get':async()=>{r.controller.invalidate();return {operation_id:'open',status:'running'};}},
  {cancelOpen:async()=>{throw Error('pipe_unavailable');}});
 await assert.rejects(r.controller.open(input),/cache_open_interrupted/);
 assert.ok(r.progress.some(p=>p.stage==='cancel_failed'&&p.error_code==='pipe_unavailable'));
 assert.equal(r.progress.some(p=>p.stage==='cancel_requested'),false);
});
test('cold local open queues one TC-backed open and never asks for cloud JT acquisition',async()=>{
 const r=rig();await r.controller.open(input);
 assert.equal(r.calls.some(c=>c.id.includes('file.fetch')),false);
 assert.equal(r.calls.filter(c=>c.id.endsWith('open.request')).length,1);
 assert.equal(r.progress.some(p=>p.stage==='local_materialization'),true);
});
test('each client creates its own open even when the shared batch is identical',async()=>{
 const a=rig(),b=rig();await a.controller.open(input);await b.controller.open(input);
 assert.equal(a.calls.filter(c=>c.id.endsWith('open.request')).length,1);assert.equal(b.calls.filter(c=>c.id.endsWith('open.request')).length,1);
});
test('scope is preserved through inspection and admission',async()=>{
 const r=rig();await r.controller.open(input);
 for(const c of r.calls.filter(c=>c.id.endsWith('inspect')||c.id.endsWith('open.request')))assert.equal(c.p.root_node_key,'part');
});
test('large cached assemblies use bounded pages and report admission separately from inspection',async()=>{
 const r=rig({'simulation.environment.cache_source.materialization.inspect':async p=>({identity,files:Array.from({length:p.cursor===0?500:1},()=>({node_key:'part'})),file_count:501,node_count:501,excluded:[],materialization_hash:'fixed',next_cursor:p.cursor===0?500:null})});
 await r.controller.open(input);
 assert.deepEqual(r.calls.filter(c=>c.id.endsWith('inspect')).map(c=>[c.p.cursor,c.p.page_size]),[[0,500],[500,500]]);
 assert.ok(r.progress.some(p=>p.stage==='inspecting'&&p.completed===500&&p.total===501));
 assert.ok(r.progress.some(p=>p.stage==='waiting_admission'&&p.completed===501&&p.capability_id.endsWith('open.request')));
});
test('unprepared batch is not repaired by downloading on click',async()=>{
 const r=rig({'simulation.environment.cache_source.materialization.inspect':async()=>{throw Error('cache_assembly_not_prepared');}});
 await assert.rejects(r.controller.open(input),/cache_assembly_not_prepared/);assert.equal(r.calls.length,1);
});
test('snapshot mismatch stops before native admission',async()=>{
 const r=rig({'simulation.environment.cache_source.materialization.inspect':async()=>({identity:{...identity,batch_id:'other'},files:[],materialization_hash:'fixed'})});
 await assert.rejects(r.controller.open(input),/cache_materialization_changed/);
});
test('unknown native outcome is retained without a new admission',async()=>{
 const r=rig({'simulation.vismockup.command.get':async()=>({operation_id:'open',status:'outcome_unknown'})});
 await assert.rejects(r.controller.open(input),/outcome_unknown/);await assert.rejects(r.controller.open(input),/outcome_unknown/);
 assert.equal(r.calls.filter(c=>c.id.endsWith('open.request')).length,1);
});
test('navigation before admission stops the open',async()=>{
 let r;r=rig({'simulation.environment.workspace.get':async()=>{r.leave();return {workspace_gid:'1',row_version:1};}});
 await assert.rejects(r.controller.open(input),/cache_open_interrupted/);assert.equal(r.calls.some(c=>c.id.endsWith('open.request')),false);
});
test('same environment merges logical branches without losing parent ancestry',()=>{
 const previous={document_gid:'2',document_session:'s',package_hash:'package',identity,node_map:{a:{instance_id:'a',parent_node_key:'root'}},excluded:[]};
 const next={...previous,node_map:{a:{instance_id:'a',parent_node_key:null},b:{instance_id:'b',parent_node_key:'a'}}};
 assert.equal(mergeLoadedBranches(previous,next).node_map.a.parent_node_key,'root');
 assert.equal(mergeLoadedBranches(previous,{...next,document_session:'new'}).node_map.a.parent_node_key,null);
});
test('merge only the same package and native session',()=>{
 const previous={document_gid:'2',document_session:'session',package_hash:'hash-a',identity,node_map:{a:{instance_id:'a',parent_node_key:'root'}},excluded:[],root_node_key:'a'};
 const next={...previous,node_map:{b:{instance_id:'b',parent_node_key:'root'}},root_node_key:'b'};
 assert.deepEqual(Object.keys(mergeLoadedBranches(previous,next).node_map),['a','b']);
 for(const changed of [{package_hash:'hash-b'},{document_session:'other'},{identity:{...identity,batch_id:'other'}}])
  assert.deepEqual(Object.keys(mergeLoadedBranches(previous,{...next,...changed}).node_map),['b']);
});
test('candidate contains only loaded structure',()=>{
 const viewer={document_gid:'2',document_session:'sha256:'+'a'.repeat(64),package_hash:'package',identity,node_map:{part:{instance_id:'native',parent_node_key:null,jt_path:'C:\\private.jt'}},excluded:[{node_key:'missing',error_code:'missing',credential:'secret'}],root_node_key:'part',native_visibility:{part:{visible:true}},visibility_context:'old-context',tc_open_payload:{credential:'secret'}};
 const tree={state:'ready',source:'teamcenter_cache_snapshot',binding:identity,context:{workspace_gid:'1',document_gid:'2',credential:'secret'},node_count:2,complete:false,pages:{roots:{state:'loaded',next_cursor:null,credential:'secret'}},nodes:[{node_key:'cache:part',cache_node_key:'part',name:'Part',parent_key:null,item_revision_uid:'revision',has_children:false,occurrence_path:[{occurrence_uid:'occ',item_revision_uid:'revision',credential:'secret'}],visible:true,visibility_state:'visible',control_key:'old',jt_path:'C:\\private.jt',credential:'secret'},{node_key:'cache:missing',cache_node_key:'missing',visible:false}]};
 const candidate=captureResumeCandidate({workspace_gid:'1',document_gid:'2',cache_binding:identity,product_tree:tree},viewer);
 assert.deepEqual(candidate.node_map,{part:{instance_id:'native',parent_node_key:null}});
 assert.equal(candidate.product_tree.nodes.length,1,'only mapped, loaded nodes are retained');
 for(const secret of ['native_visibility','visible','visibility_state','control_key','tc_open_payload','jt_path','credential','private.jt','old-context'])assert.equal(JSON.stringify(candidate).includes(secret),false,secret);
 assert.equal(JSON.stringify(tree).includes('private.jt'),true,'capture does not mutate the displayed tree');
});
test('candidate keeps excluded ancestry so a loaded parent stays unknown',()=>{
 const {cacheIncompleteAncestors}=require('./viewer_interaction');
 const viewer={document_gid:'2',document_session:'sha256:'+'a'.repeat(64),package_hash:'package',identity,
  node_map:{assembly:{instance_id:'native-assembly',parent_node_key:null},missing:{instance_id:'native-missing',parent_node_key:'assembly'}},
  excluded:[{node_key:'missing',error_code:'missing'}],root_node_key:'assembly'};
 const document={workspace_gid:'1',document_gid:'2',cache_binding:identity,product_tree:{pages:{roots:{state:'loaded'}},nodes:[
  {node_key:'cache:assembly',cache_node_key:'assembly',parent_key:null,item_revision_uid:'r'},
  {node_key:'cache:missing',cache_node_key:'missing',parent_key:'cache:assembly',item_revision_uid:'r'}]}};
 const candidate=captureResumeCandidate(document,viewer);
 assert.deepEqual(candidate.product_tree.nodes.map(node=>node.cache_node_key),['assembly']);
 assert.equal(cacheIncompleteAncestors(candidate).has('assembly'),true);
 assert.equal(JSON.stringify(candidate).includes('native-missing'),false,'excluded native handles are not retained');
});
test('candidate retains mapped path ancestors absent from the displayed page',()=>{
 const {sourceDescriptor,cacheIncompleteAncestors}=require('./viewer_interaction');
 const viewer={document_gid:'2',document_session:'sha256:'+'a'.repeat(64),package_hash:'package',identity,
  node_map:{root:{instance_id:'native-root',parent_node_key:null},branch:{instance_id:'native-branch',parent_node_key:'root'},part:{instance_id:'native-part',parent_node_key:'branch'},missing:{instance_id:'native-missing',parent_node_key:'branch'}},
  excluded:[{node_key:'missing'}],root_node_key:'root'};
 const document={workspace_gid:'1',document_gid:'2',source_kind:'teamcenter_cache_snapshot',cache_binding:identity,product_tree:{pages:{roots:{state:'loaded'}},nodes:[
  {node_key:'cache:root',cache_node_key:'root',item_revision_uid:'r'},
  {node_key:'cache:part',cache_node_key:'part',item_revision_uid:'r'}]}};
 const candidate=captureResumeCandidate(document,viewer);
 const descriptor=sourceDescriptor({...document,_cacheViewer:candidate},document.product_tree.nodes[1]);
 assert.deepEqual(descriptor.occurrence_path.map(edge=>edge.occurrence_uid),['native-root','native-branch','native-part']);
 assert.equal(cacheIncompleteAncestors(candidate).has('root'),true);
 assert.equal(JSON.stringify(candidate).includes('native-missing'),false);
});
test('resume preparation rejects a conflicting refreshed mapping without touching the document',()=>{
 const document={document_gid:'2',source_kind:'teamcenter_cache_snapshot',cache_binding:identity,content_sha256:'sha256:'+'c'.repeat(64),product_tree:{state:'ready',nodes:[{node_key:'cache:root',cache_node_key:'root',item_revision_uid:'new'}],pages:{}}};
 const candidate={document_gid:'2',cache_binding:identity,package_hash:document.content_sha256,product_tree:{nodes:[{node_key:'cache:root',cache_node_key:'root',item_revision_uid:'old'}],pages:{}},node_map:{root:{instance_id:'native',parent_node_key:null}}};
 assert.throws(()=>prepareResumeDocument(document,candidate),/cache_environment_mapping_conflict/);
 assert.equal(document.product_tree.nodes[0].item_revision_uid,'new');
 const staged=prepareResumeDocument(document,{...candidate,product_tree:{nodes:[{node_key:'cache:other',cache_node_key:'other',item_revision_uid:'other'}],pages:{other:{state:'loaded'}}},node_map:{other:{instance_id:'other',parent_node_key:null}}});
 assert.equal(staged.product_tree.nodes.length,2);assert.equal(document.product_tree.nodes.length,1);
});
test('resume preparation rejects a changed structural key for the same cached node',()=>{
 const document={document_gid:'2',source_kind:'teamcenter_cache_snapshot',cache_binding:identity,content_sha256:'sha256:'+'c'.repeat(64),product_tree:{nodes:[{node_key:'cache:new',cache_node_key:'part',item_revision_uid:'r'}],pages:{}}};
 const candidate={document_gid:'2',cache_binding:identity,package_hash:document.content_sha256,product_tree:{nodes:[{node_key:'cache:old',cache_node_key:'part',item_revision_uid:'r'}],pages:{}},node_map:{part:{instance_id:'native',parent_node_key:null}}};
 assert.throws(()=>prepareResumeDocument(document,candidate),/cache_environment_mapping_conflict/);
 assert.deepEqual(document.product_tree.nodes.map(node=>node.node_key),['cache:new']);
});

for(const outcome of ['failed_without_effect','outcome_unknown','succeeded'])test('resume after navigation respects previous '+outcome+' receipt',async()=>{
 let r,reads=0,opens=0;
 r=rig({
  'simulation.environment.cache_source.open.request':async()=>({identity,operation_id:'open-'+(++opens),package_hash:'package',node_map:{part:{instance_id:'instance',parent_node_key:null}},excluded:[]}),
  'simulation.vismockup.command.get':async p=>{
   if(++reads===1){r.controller.invalidate();return {operation_id:p.operation_id,status:'running'};}
   if(p.operation_id==='open-1'&&outcome!=='succeeded')return {operation_id:p.operation_id,status:outcome==='failed_without_effect'?'failed':'outcome_unknown',outcome:{steps:[{status:outcome,error_code:'cancelled'}]}};
   return {operation_id:p.operation_id,status:'completed',outcome:{steps:[{status:'succeeded',result:{protocol:'ai00.viewer.opened-tc-cache.v1',package_hash:'package',cache_binding:identity}}]}};
  }
 },{cancelOpen:async()=>{}});
 await assert.rejects(r.controller.open(input),/cache_open_interrupted/);
 if(outcome==='outcome_unknown')await assert.rejects(r.controller.open(input),error=>error.message==='cancelled'&&error.cache_effect_unknown===true);
 else assert.equal((await r.controller.open(input)).operation_id,outcome==='failed_without_effect'?'open-2':'open-1');
 assert.equal(opens,outcome==='failed_without_effect'?2:1);
});
