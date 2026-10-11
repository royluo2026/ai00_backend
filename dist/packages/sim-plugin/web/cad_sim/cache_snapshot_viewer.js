(function(root,factory){
 const api=factory(root);if(typeof module==='object'&&module.exports)module.exports=api;
 root.AI00CacheSnapshotViewer=api;
})(typeof window!=='undefined'?window:globalThis,root=>{
 'use strict';
 const pins=['batch_id','generation','snapshot_hash','schema_version'];
 const inflight=new Set(['queued','running','leased','pending','executing','reconciling']);
 const terminal=new Set(['completed','failed','failed_without_effect','cancelled','expired','outcome_unknown','manual_review_required']);
 function sameIdentity(actual,expected){return actual&&pins.every(key=>actual[key]===expected[key]);}
 function mergeLoadedBranches(previous,next){
  if(!previous||!next.document_session||previous.document_session!==next.document_session||previous.document_gid!==next.document_gid||!next.package_hash||previous.package_hash!==next.package_hash||!sameIdentity(previous.identity,next.identity))return next;
  const node_map={...previous.node_map};
  for(const [key,value]of Object.entries(next.node_map||{})){
   const old=node_map[key];
   if(old&&old.instance_id!==value.instance_id)throw Error('cache_environment_mapping_conflict');
   node_map[key]=old?.parent_node_key!=null&&value.parent_node_key===null?{...value,parent_node_key:old.parent_node_key}:value;
  }
  const excluded=[...new Map([...(previous.excluded||[]),...(next.excluded||[])].map(item=>[item.node_key,item])).values()];
  // A new binding needs fresh visibility readback, even in the same document.
  return {...next,node_map,excluded,root_node_key:previous.root_node_key===null||next.root_node_key===null?null:next.root_node_key};
 }
 function captureResumeCandidate(document,viewer){
  if(!document?.product_tree?.nodes||!viewer?.package_hash||!/^sha256:[0-9a-f]{64}$/.test(viewer.document_session||'')||viewer.document_gid!==document.document_gid||!sameIdentity(viewer.identity,document.cache_binding))throw Error('cache_resume_candidate_invalid');
  const copy=(value,keys)=>Object.fromEntries(keys.filter(key=>Object.hasOwn(value||{},key)).map(key=>[key,value[key]]));
  const excluded=new Set((viewer.excluded||[]).map(item=>item.node_key));
  const nodes=document.product_tree.nodes.filter(node=>typeof node.cache_node_key==='string'&&Object.hasOwn(viewer.node_map||{},node.cache_node_key)&&!excluded.has(node.cache_node_key))
   .map(node=>({...copy(node,['node_key','cache_node_key','parent_key','parent_occurrence_id','occurrence_id','name','item_revision_uid','revision','has_children','node_type','children_count']),
    ...(Array.isArray(node.occurrence_path)?{occurrence_path:node.occurrence_path.map(edge=>copy(edge,['occurrence_uid','item_revision_uid']))}:{})}));
  const loaded=new Set(nodes.map(node=>node.cache_node_key));
  const mapping=viewer.node_map||{},preserved=new Set([...loaded,...excluded]),loadedPath=new Set(loaded);
  const retainParents=(start,withHandle)=>{
   const seen=new Set([start]);let parent=mapping[start]?.parent_node_key;
   while(typeof parent==='string'&&!seen.has(parent)&&Object.hasOwn(mapping,parent)){
    seen.add(parent);preserved.add(parent);if(withHandle)loadedPath.add(parent);
    parent=mapping[parent]?.parent_node_key;
   }
  };
  for(const key of loaded)retainParents(key,true);
  for(const key of excluded)retainParents(key,false);
  const node_map=Object.fromEntries(Object.entries(mapping).filter(([key])=>preserved.has(key)).map(([key,value])=>[key,copy(value,loadedPath.has(key)&&!excluded.has(key)?['instance_id','parent_node_key']:['parent_node_key'])]));
  const pages=Object.fromEntries(Object.entries(document.product_tree.pages||{}).filter(([,page])=>page.state==='loaded').map(([key,page])=>[key,copy(page,['state','generation','next_cursor'])]));
  return {workspace_gid:document.workspace_gid,document_gid:document.document_gid,cache_binding:copy(document.cache_binding,pins),package_hash:viewer.package_hash,document_session:viewer.document_session,workspace_row_version:viewer.workspace_row_version,identity:copy(viewer.identity,pins),node_map,excluded:(viewer.excluded||[]).map(item=>copy(item,['node_key','name','reason','error_code'])),root_node_key:viewer.root_node_key,
   product_tree:{state:'ready',source:'teamcenter_cache_snapshot',binding:copy(document.cache_binding,pins),context:{workspace_gid:document.workspace_gid,document_gid:document.document_gid},complete:false,node_count:nodes.length,nodes,pages}};
 }
 function prepareResumeDocument(document,candidate){
  if(document?.source_kind!=='teamcenter_cache_snapshot'||document.document_gid!==candidate?.document_gid||!sameIdentity(document.cache_binding,candidate.cache_binding)||document.content_sha256!==candidate.package_hash||!Array.isArray(document.product_tree?.nodes)||!Array.isArray(candidate.product_tree?.nodes))throw Error('cache_resume_candidate_mismatch');
  const nodes=document.product_tree.nodes.map(node=>({...node,visible:null,visibility_state:'unknown'}));
  const byKey=new Map(nodes.map(node=>[node.node_key,node]));
  const byCacheKey=new Map(nodes.filter(node=>typeof node.cache_node_key==='string').map(node=>[node.cache_node_key,node]));
  for(const node of candidate.product_tree.nodes){
   if(!Object.hasOwn(candidate.node_map||{},node.cache_node_key)||typeof node.node_key!=='string')throw Error('cache_environment_mapping_conflict');
   if(byCacheKey.has(node.cache_node_key)&&byCacheKey.get(node.cache_node_key).node_key!==node.node_key)throw Error('cache_environment_mapping_conflict');
   const current=byKey.get(node.node_key);
   if(current){
    if(['cache_node_key','item_revision_uid','parent_key'].some(key=>current[key]!=null&&node[key]!=null&&current[key]!==node[key]))throw Error('cache_environment_mapping_conflict');
   }else{const loaded={...node,visible:null,visibility_state:'unknown'};nodes.push(loaded);byKey.set(node.node_key,loaded);}
  }
  return {...document,product_tree:{...document.product_tree,nodes,node_count:nodes.length,pages:{...document.product_tree.pages,...candidate.product_tree.pages}}};
 }
 function create({invoke,interaction,cancelOpen=async()=>{throw Error('cache_open_cancel_unavailable');},localProgress=async()=>null,isCurrent=()=>true,onProgress=()=>{},log=()=>{},delay=ms=>new Promise(resolve=>setTimeout(resolve,ms)),randomId=()=>root.crypto.randomUUID(),retryStorage}){
  const jobs=new Map();let epoch=0;
  const current=input=>{if(input.open_epoch!==epoch||!isCurrent(input))throw Error('cache_open_interrupted');};
  const progress=(input,stage,detail={})=>{const value={workspace_gid:input.workspace_gid,document_gid:input.document_gid,batch_id:input.cache_binding.batch_id,root_node_key:input.root_node_key??null,source_node_id:input.source_node_id,node_name:input.node_name,stage,...detail};try{onProgress(value);}catch{}try{log('cache_viewer_'+stage,value);}catch{}};
  function cancel(job){
   if(!job.opened?.operation_id||job.cancelPending)return;
   const operation_id=job.opened.operation_id;
   job.cancelPending=Promise.resolve().then(()=>cancelOpen(operation_id)).then(
    ()=>progress(job.input,'cancel_requested',{operation_id,message:'已请求取消，最终结果以执行回执为准'}),
    error=>progress(job.input,'cancel_failed',{operation_id,error_code:error.message,message:'取消请求未送达，不能确认打开任务已停止'}));
  }
  async function admission(input,id,payload,options){
   let waits=0;
   for(;;){
    current(input);
    try{return await invoke(id,payload,options);}
    catch(error){
     if(!['capacity_unavailable','idempotency_in_progress'].includes(error.message))throw error;
     progress(input,'waiting_admission',{capability_id:id,status:'pending',reason:error.message,message:'等待已有请求确认或执行名额',sequence:++waits});
     await delay(Math.min(5000,1000*waits));
    }
   }
  }
  async function run(input,job){
   current(input);
   if(job.terminal)throw Error(job.terminal);
   if(!job.opened){
    let cursor=0,materialization=null,completed=0,total;
    do{
     current(input);progress(input,'inspecting',{completed,total,capability_id:'simulation.environment.cache_source.materialization.inspect'});
     const page=await invoke('simulation.environment.cache_source.materialization.inspect',{workspace_gid:input.workspace_gid,document_gid:input.document_gid,...(input.root_node_key?{root_node_key:input.root_node_key}:{}),cursor,page_size:500});current(input);
     if(!sameIdentity(page.identity,input.cache_binding)||!Array.isArray(page.files)||typeof page.materialization_hash!=='string'||materialization&&materialization!==page.materialization_hash)throw Error('cache_materialization_changed');
     materialization=page.materialization_hash;
     total=page.file_count;
     if(cursor===0)progress(input,'scope_resolved',{total:page.file_count,node_count:page.node_count,materialization_hash:materialization,message:input.node_name||'整个文档'});
     if(cursor===0)for(const excluded of page.excluded||[])progress(input,'node_excluded',{node_key:excluded.node_key,node_name:excluded.name,error_code:excluded.error_code,level:'warn',message:'该节点不加载，位置或文件依据不完整'});
     if(page.next_cursor!==null&&(!Number.isSafeInteger(page.next_cursor)||page.next_cursor<=cursor))throw Error('cache_materialization_cursor_invalid');
     completed+=page.files.length;
     progress(input,'dependencies_resolved',{completed,total:page.file_count,message:'已确认 TC 文件引用；本机缓存由 Connector 检查'});
     cursor=page.next_cursor;
    }while(cursor!==null);
    current(input);progress(input,'assembly_prepared',{completed});
    const workspace=await invoke('simulation.environment.workspace.get',{workspace_gid:input.workspace_gid});current(input);
    if(workspace.workspace_gid!==input.workspace_gid)throw Error('cache_open_workspace_mismatch');
    if(!job.admissionInput)job.admissionInput={workspace_gid:input.workspace_gid,document_gid:input.document_gid,...(input.root_node_key?{root_node_key:input.root_node_key}:{}),expected_workspace_row_version:workspace.row_version,materialization_hash:materialization};
    if(job.admissionInput.materialization_hash!==materialization)throw Error('cache_materialization_changed');
    progress(input,'waiting_admission',{completed,total,capability_id:'simulation.environment.cache_source.open.request',message:'正在校验装配并提交打开请求'});
    try{job.opened=await admission(input,'simulation.environment.cache_source.open.request',job.admissionInput,{idempotency:true,idempotencyKey:job.openKey,expectedResourceVersion:job.admissionInput.expected_workspace_row_version});}
    catch(error){if(error.message==='version_conflict'){job.admissionInput=null;job.openKey='cache-open-'+randomId();}throw error;}
   }
   const opened=job.opened;current(input);
   if(!sameIdentity(opened.identity,input.cache_binding)||typeof opened.operation_id!=='string'||!opened.operation_id||!opened.node_map||!Array.isArray(opened.excluded))throw Error('cache_open_admission_invalid');
   progress(input,'local_materialization',{operation_id:opened.operation_id,capability_id:'simulation.vismockup.command.get',message:'检查本机缓存，按需从 TC/FMS 下载并打开'});
   for(;;){
    current(input);const command=await invoke('simulation.vismockup.command.get',{operation_id:opened.operation_id});current(input);
    try{
     const local=await localProgress(opened.package_hash);current(input);
     if(local?.package_hash===opened.package_hash&&Date.parse(local.timestamp)>=job.started&&local.timestamp!==job.progressTimestamp){
      job.progressTimestamp=local.timestamp;progress(input,local.stage,{...local,operation_id:opened.operation_id});
     }
    }catch(error){if(error.message==='cache_open_interrupted')throw error;}
    if(command.operation_id!==opened.operation_id)throw Error('cache_open_operation_mismatch');
    if(command.status==='completed'){
     const step=command.outcome?.steps?.length===1?command.outcome.steps[0]:null,receipt=step?.result;
     if(step?.status!=='succeeded'||receipt?.protocol!=='ai00.viewer.opened-tc-cache.v1'||receipt.package_hash!==opened.package_hash||!sameIdentity(receipt.cache_binding,input.cache_binding))throw Error('cache_open_receipt_invalid');
     break;
    }
    if(terminal.has(command.status)){if(command.status==='failed'&&command.outcome?.steps?.length===1&&command.outcome.steps[0].status==='failed_without_effect')job.retryWithoutEffect=true;job.terminal=command.outcome?.steps?.at(-1)?.error_code||command.status;throw Error(job.terminal);}
    if(!inflight.has(command.status))throw Error('cache_open_status_invalid');
    await delay(500);
   }
   progress(input,'binding_document',{operation_id:opened.operation_id,capability_id:'simulation.environment.cache_source.live_document.bind'});
   const latest=await invoke('simulation.environment.workspace.get',{workspace_gid:input.workspace_gid});current(input);
   if(latest.workspace_gid!==input.workspace_gid)throw Error('cache_open_workspace_mismatch');
   if(job.boundVersion&&latest.row_version>job.boundVersion)job.bindInput=null;
   if(!job.bindInput)job.bindInput={workspace_gid:input.workspace_gid,document_gid:input.document_gid,launch_operation_id:opened.operation_id,expected_workspace_row_version:latest.row_version,idempotency_key:'cache-bind-'+opened.operation_id.slice(-64)+'-'+input.document_gid+'-'+latest.row_version};
   let bound;try{bound=await interaction.openFromCache(job.bindInput);}
   catch(error){if(error.message==='version_conflict')job.bindInput=null;throw error;}
   job.boundVersion=bound.workspace_row_version;current(input);
   if(bound.document_gid!==input.document_gid||!bound.visibility_context)throw Error('cache_open_binding_invalid');
   progress(input,'ready',{operation_id:opened.operation_id,message:`${opened.excluded.length} 个节点未加载`});
   return {...opened,...bound,root_node_key:input.root_node_key??null};
  }
  return Object.freeze({invalidate(){epoch++;for(const job of jobs.values())if(job.pending)cancel(job);},open(input){
   input={...input,open_epoch:epoch};
   const key=JSON.stringify([input.workspace_gid,input.document_gid,input.root_node_key??null,...pins.map(pin=>input.cache_binding?.[pin])]);
   let job=jobs.get(key);if(!job){job={openKey:'cache-open-'+randomId(),started:Date.now()};jobs.set(key,job);}
   if(job.pending)return job.pending;
   job.input=input;
   const resuming=job.interrupted===true;
   job.pending=(async()=>{
    try{return await run(input,job);}
    catch(error){
     // A new explicit click may replace a navigation-cancelled request only after its no-effect receipt.
     if(!resuming||!job.retryWithoutEffect||job.terminal!=='cancelled')throw error;
     current(input);
     progress(input,'retrying_cancelled',{operation_id:job.opened.operation_id,message:'上次打开已取消且未产生效果，开始本次打开'});
     job={openKey:'cache-open-'+randomId(),started:Date.now(),input,pending:job.pending};jobs.set(key,job);
     return run(input,job);
    }
   })().catch(error=>{if(job.opened&&!job.retryWithoutEffect)error.cache_effect_unknown=true;if(error.message==='cache_open_interrupted'){job.interrupted=true;cancel(job);}if(['document_closed','cache_open_evidence_stale'].includes(error.message)||job.retryWithoutEffect)jobs.delete(key);progress(input,'failed',{error_code:error.message,message:error.message});throw error;}).finally(()=>{job.pending=null;});
   return job.pending;
  }});
 }
 return Object.freeze({create,sameIdentity,mergeLoadedBranches,captureResumeCandidate,prepareResumeDocument});
});
