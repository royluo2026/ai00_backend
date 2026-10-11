(function(root){
 'use strict';
 const incompleteCache=new WeakMap();
 function cacheIncompleteAncestors(viewer){
  if(!viewer)return new Set();
  if(incompleteCache.has(viewer))return incompleteCache.get(viewer);
  const result=new Set(),map=viewer.node_map||{};
  for(const excluded of viewer.excluded||[]){
   const seen=new Set();let key=map[excluded.node_key]?.parent_node_key;
   while(typeof key==='string'&&!seen.has(key)){
    seen.add(key);result.add(key);key=map[key]?.parent_node_key;
   }
  }
  incompleteCache.set(viewer,result);return result;
 }
 function sourceDescriptor(document,node){
  const source_node_id=String(node?.node_key||'');
  if(!source_node_id)throw Error('unmapped');
  if(document?.source_kind==='teamcenter_cache_snapshot'){
   const viewer=document._cacheViewer,map=viewer?.node_map,path=[],seen=new Set();let key=node.cache_node_key;
   if(viewer?.excluded?.some(item=>item.node_key===key))throw Error('cache_node_excluded');
   while(key!=null){
    if(typeof key!=='string'||seen.has(key)||path.length>=128||!map||!Object.hasOwn(map,key))throw Error('cache_node_mapping_invalid');
    seen.add(key);const entry=map[key];
    if(typeof entry?.instance_id!=='string'||!entry.instance_id||!Object.hasOwn(entry,'parent_node_key')||(entry.parent_node_key!==null&&typeof entry.parent_node_key!=='string'))throw Error('cache_node_mapping_invalid');
    path.push(entry.instance_id);key=entry.parent_node_key;
   }
   if(!path.length)throw Error('cache_node_excluded');path.reverse();
   return {source_node_id,kind:'occurrence_path',occurrence_path:path.map(occurrence_uid=>({occurrence_uid,item_revision_uid:String(node.item_revision_uid||'cache-instance')}))};
  }
  if(node.parent_key===null&&node.has_children===false&&document?.product_tree?.nodes?.length===1
    &&String(document.product_tree.nodes[0].node_key)===source_node_id)return {source_node_id,kind:'single_part_root'};
  if(node.parent_key===null&&Array.isArray(node.occurrence_path)&&node.occurrence_path.length===0&&document?.source_kind==='teamcenter_online')return {source_node_id,kind:'document_root'};
  if(Array.isArray(node.occurrence_path)&&node.occurrence_path.length)return {source_node_id,kind:'occurrence_path',occurrence_path:node.occurrence_path.map(edge=>({occurrence_uid:edge.occurrence_uid,item_revision_uid:edge.item_revision_uid}))};
  throw Error('unmapped');
 }
 function createViewerInteraction({api,onState=()=>{},onReady=()=>{}}){
  let id=null,phase='closed',generation=0,epoch=null,scope=null,pendingMainOpen=false,mainOwned=false,visibilityContext=null;const refs=new Map(),mapping=new Map(),intentPending=new Map(),scopeChains=new Map();
  const state=(value,action)=>{phase=value;onState(value,action);};
  const check=()=>{if(!id||['closed','outcome_unknown','opening'].includes(phase))throw Error(phase==='outcome_unknown'?phase:'interaction_not_ready');};
  function completed(response){
   if(response?.status!=='completed'){
    const code=response?.status==='outcome_unknown'?'outcome_unknown':response?.error_code||response?.status||'interaction_response_invalid';
    state(code);throw Error(code);
   }
   return response.result;
  }
  const controller={
   get state(){return phase;},get scope(){return scope;},get visibilityContext(){return visibilityContext;},
   async open(input,method='open'){
    await controller.close();const token=++generation;pendingMainOpen=true;state('opening');
    try{const response=await api[method](input);if(token!==generation){if(response?.result?.interaction_id)await api.close({interaction_id:response.result.interaction_id});throw Error('document_selection_changed');}pendingMainOpen=false;
     const result=completed(response);
     if(typeof result?.interaction_id!=='string')throw Error('interaction_response_invalid');id=result.interaction_id;scope={...input};state('ready');return result;
    }catch(error){if(token===generation){if(error.message!=='interaction_bridge_timeout')pendingMainOpen=false;state(error.message);}throw error;}
   },
   openFromLaunch(input){return controller.open(input,'openFromLaunch');},
   async openFromCache(input){
    const result=await controller.open(input,'openFromCache');
    if(typeof result.visibility_context!=='string'||!result.visibility_context)throw Error('interaction_visibility_context_invalid');
    mainOwned=true;visibilityContext=result.visibility_context;onReady(result,{...input,source_kind:'teamcenter_cache_snapshot'});return result;
   },
   async resumeFromCache(input){
    const result=await controller.open(input,'resumeFromCache');
    try{
     if(typeof result.visibility_context!=='string'||!result.visibility_context||result.document_gid!==input.document_gid||result.document_session!==input.expected_document_session||result.workspace_row_version!==input.expected_workspace_row_version)throw Error('interaction_visibility_context_invalid');
     mainOwned=true;visibilityContext=result.visibility_context;
     onReady(result,{...input,source_kind:'teamcenter_cache_snapshot'});
     return result;
    }catch(error){await controller.close();throw error;}
   },
   executeCachedIntent(input){
    const token=generation,key=JSON.stringify([input.workspace_gid,input.document_gid]);
    const previous=scopeChains.get(key)||Promise.resolve();
    const pending=previous.catch(()=>{}).then(async()=>{
     if(phase==='outcome_unknown')throw Error('outcome_unknown');
     if(token!==generation||!mainOwned||phase!=='ready'||scope?.workspace_gid!==input.workspace_gid||scope?.document_gid!==input.document_gid||input.visibility_context!==visibilityContext)throw Error('cache_document_not_ready');
     if(!['show','hide','highlight','unhighlight'].includes(input.action))throw Error('node_action_unsupported');
     state('executing',input.action);
     try{const response=await api.executeCachedIntent(input);if(token!==generation)throw Error('document_selection_changed');completed(response);state('ready');return {ok:true,...(['show','hide'].includes(input.action)?{visible:input.action==='show'}:{selected:input.action==='highlight'}),timings:response.timings};}
     catch(error){if(token===generation)state(error?.message||'interaction_rejected');throw error;}
    }).finally(()=>{if(scopeChains.get(key)===pending)scopeChains.delete(key);});
    scopeChains.set(key,pending);return pending;
   },
   async ensureReady({scope:nextScope,source_selector,source_nodes,action}){
    if(phase==='outcome_unknown')throw Error('outcome_unknown');const token=++generation;
    mainOwned=true;state('opening');try{const result=completed(await api.ensureReady({...nextScope,source_selector,...(source_nodes?{source_nodes,action}:{})}));
    if(token!==generation)throw Error('document_selection_changed');
    onReady(result,nextScope);
    scope={...nextScope};state('ready');return result;
    }catch(error){if(token===generation)state(error?.message||'interaction_rejected');throw error;}
   },
   async readVisibility({source_nodes}){
    if(!mainOwned||!scope||phase!=='ready')throw Error(phase==='outcome_unknown'?phase:'interaction_not_ready');
    const token=generation;state('calibrating');
    try{const response=await api.readVisibility({workspace_gid:scope.workspace_gid,document_gid:scope.document_gid,source_nodes});
     if(token!==generation)throw Error('document_selection_changed');
     const result=completed(response);if(!Array.isArray(result?.nodes))throw Error('interaction_visibility_invalid');
     state('ready');return result;
    }catch(error){if(token===generation)state(error?.message||'interaction_rejected');throw error;}
   },
   executeIntent(input){
    if(!['show','hide','highlight','unhighlight'].includes(input?.action))return Promise.reject(Error('node_action_unsupported'));
    if(phase==='outcome_unknown')return Promise.reject(Error('outcome_unknown'));
    const family=['show','hide'].includes(input.action)?'visibility':'selection';
    const scopeKey=JSON.stringify([input.scope?.workspace_gid,input.scope?.document_gid]);
    const key=JSON.stringify([scopeKey,input.source_nodes,family]);
    const queued=intentPending.get(key);if(queued&&!queued.dispatched){queued.latest=input;return queued.promise;}
    const entry={latest:input,dispatched:false};
    const previous=scopeChains.get(scopeKey)||Promise.resolve();
    entry.promise=Promise.resolve().then(async()=>{
     await previous.catch(error=>{if(phase==='outcome_unknown')throw error;});
     if(phase==='outcome_unknown')throw Error('outcome_unknown');
     entry.dispatched=true;state('opening');
     const token=++generation;mainOwned=true;let response;try{
      const ready=completed(await api.ensureReady({...entry.latest.scope,source_selector:entry.latest.source_selector,source_nodes:entry.latest.source_nodes,action:entry.latest.action}));
      if(token!==generation)throw Error('document_selection_changed');
      if(entry.latest.visibility_context!=null&&entry.latest.visibility_context!==ready?.visibility_context)throw Error('visibility_calibration_required');
      onReady(ready,entry.latest.scope);
      state('executing',entry.latest.action);
      response=await api.executeIntent({...entry.latest.scope,source_selector:entry.latest.source_selector,source_nodes:entry.latest.source_nodes,action:entry.latest.action,...(entry.latest.visibility_context!=null?{visibility_context:entry.latest.visibility_context}:{})});
     }
     catch(error){if(error?.message==='outcome_unknown')state('outcome_unknown');else state(error?.message||'interaction_rejected');throw error;}
     if(token!==generation)throw Error('document_selection_changed');
     completed(response);scope={...entry.latest.scope};state('ready');
     return {ok:true,...(family==='visibility'?{visible:entry.latest.action==='show'}:{selected:entry.latest.action==='highlight'}),timings:response.timings};
    }).finally(()=>{if(intentPending.get(key)===entry)intentPending.delete(key);if(scopeChains.get(scopeKey)===entry.promise)scopeChains.delete(scopeKey);});
    intentPending.set(key,entry);scopeChains.set(scopeKey,entry.promise);return entry.promise;
   },
   async resolve(source_nodes){
    check();const token=generation;
    const missing=source_nodes.filter(n=>!refs.has(JSON.stringify(n)));
    if(missing.length){
     const key=JSON.stringify(missing);
     if(!mapping.has(key)){
      state('mapping_pending');
      const pending=(async()=>{
       const response=await api.resolve({interaction_id:id,source_nodes:missing});
       if(token!==generation)throw Error('document_selection_changed');
       const result=completed(response);
       if(!Number.isSafeInteger(result?.structure_epoch)||!Array.isArray(result.nodes)||result.nodes.length!==missing.length)throw Error('interaction_mapping_invalid');
       if(epoch!==result.structure_epoch)refs.clear();epoch=result.structure_epoch;
       result.nodes.forEach((node,i)=>{if(node.source_node_id!==missing[i].source_node_id||node.status!=='mapped'||typeof node.node_ref!=='string')throw Error(node.error_code||'unmapped');refs.set(JSON.stringify(missing[i]),node.node_ref);});
       state('ready');
      })().finally(()=>{if(token===generation)mapping.delete(key);});mapping.set(key,pending);
     }
     await mapping.get(key);
    }
    const targets=source_nodes.map(n=>refs.get(JSON.stringify(n)));if(targets.some(n=>!n))throw Error('mapping_pending');return targets;
   },
   async execute({source_nodes,action}){
    if(!['show','hide','highlight','unhighlight'].includes(action))throw Error('node_action_unsupported');
    check();const token=generation,targets=await controller.resolve(source_nodes);check();
    if(token!==generation)throw Error('document_selection_changed');
    const operation_id=['show','hide'].includes(action)?'vismockup.node.visibility.change@1':'vismockup.node.selection.change@1';
    let response;
    try{response=await api.execute({interaction_id:id,operation_id,targets,arguments:{action}});}catch{if(token===generation)state('outcome_unknown');throw Error('outcome_unknown');}
    if(token!==generation)throw Error('document_selection_changed');
    const result=completed(response);
    if(result?.targets?.some(t=>t.status==='outcome_unknown')){state('outcome_unknown');throw Error('outcome_unknown');}
    if(!Array.isArray(result?.targets)||result.targets.length!==targets.length||result.targets.some((t,i)=>t.node_ref!==targets[i]||t.status!=='completed'))throw Error(result?.targets?.find(t=>t.status!=='completed')?.error_code||'interaction_target_failed');
    state('ready');return {ok:true,...(['show','hide'].includes(action)?{visible:action==='show'}:{selected:action==='highlight'}),timings:response.timings};
   },
   async close(){const old=id,releaseMain=mainOwned||pendingMainOpen;++generation;id=null;scope=null;visibilityContext=null;refs.clear();mapping.clear();intentPending.clear();scopeChains.clear();epoch=null;state('closed');if(old)await api.close({interaction_id:old});if(releaseMain)await api.cancelOpen?.({});pendingMainOpen=false;mainOwned=false;},
  };return controller;
 }
 function frameAPI(win=root){
  if(win.parent===win)return win.electronAPI?.viewerInteraction||null;
  // Only a real desktop parent installs the isolated relay. Never borrow its
  // public API: that would attribute every iframe call to the parent frame.
  try{if(!win.parent.electronAPI)return null;}catch{return null;}
  let opening=false;
  const invoke=(method,input)=>new Promise((resolve,reject)=>{
   const isOpen=method==='open'||method==='openFromLaunch'||method==='openFromCache'||method==='resumeFromCache';
   if(isOpen){if(opening){reject(Error('interaction_open_pending'));return;}opening=true;}
   const channel=new win.MessageChannel();
   let abandoned=false;
   // Source opening/binding may await human confirmation; model commands must
   // still time out promptly and remain fenced against replay.
   const timeoutMs=method==='ensureReady'||method==='openFromLaunch'||method==='openFromCache'?3600000:method==='resumeFromCache'?60000:method==='executeIntent'||method==='executeCachedIntent'?120000:method==='execute'?90000:method==='readVisibility'?60000:method==='resolve'?35000:15000;
   const timer=win.setTimeout(()=>{
    abandoned=true;
    // An open may still install a grant in Main. Keep its reply port alive so
    // we can close that exact late session; no second open until cleanup.
    if(!isOpen)channel.port1.close();
    reject(Error(method==='execute'||method==='executeIntent'||method==='executeCachedIntent'?'outcome_unknown':'interaction_bridge_timeout'));
   },timeoutMs);
   channel.port1.onmessage=async event=>{
    win.clearTimeout(timer);channel.port1.close();
    if(isOpen&&abandoned){
     const id=event.data.result?.result?.interaction_id;
     if(id){
      try{const result=await invoke('close',{interaction_id:id});if(result?.status==='completed')opening=false;}catch{}
      // Failed/unknown cleanup remains fenced until frame/session teardown.
     }else opening=false;
     return;
    }
    if(isOpen)opening=false;
    event.data.error?reject(Error(event.data.error)):resolve(event.data.result);
   };
   win.parent.postMessage({type:'ai00:viewer-interaction',request_id:win.crypto.randomUUID(),method,input},win.location.origin,[channel.port2]);
  });
  return Object.freeze({debugOpen:input=>invoke('debugOpen',input),debugRecord:input=>invoke('debugRecord',input),enabled:()=>invoke('enabled'),open:input=>invoke('open',input),openFromLaunch:input=>invoke('openFromLaunch',input),openFromCache:input=>invoke('openFromCache',input),resumeFromCache:input=>invoke('resumeFromCache',input),ensureReady:input=>invoke('ensureReady',input),readVisibility:input=>invoke('readVisibility',input),executeIntent:input=>invoke('executeIntent',input),executeCachedIntent:input=>invoke('executeCachedIntent',input),cancelOpen:input=>invoke('cancelOpen',input),resolve:input=>invoke('resolve',input),execute:input=>invoke('execute',input),close:input=>invoke('close',input)});
 }
 const api={createViewerInteraction,sourceDescriptor,frameAPI,cacheIncompleteAncestors};root.AI00ViewerInteraction=api;
 if(typeof module!=='undefined')module.exports=api;
})(typeof window==='undefined'?globalThis:window);
