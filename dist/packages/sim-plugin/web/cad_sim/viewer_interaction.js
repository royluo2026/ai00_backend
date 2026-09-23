(function(root){
 'use strict';
 function sourceDescriptor(document,node){
  const source_node_id=String(node?.node_key||'');
  if(!source_node_id)throw Error('unmapped');
  if(node.parent_key===null&&node.has_children===false&&document?.product_tree?.nodes?.length===1
    &&String(document.product_tree.nodes[0].node_key)===source_node_id)return {source_node_id,kind:'single_part_root'};
  if(Array.isArray(node.occurrence_path)&&node.occurrence_path.length)return {source_node_id,kind:'occurrence_path',occurrence_path:node.occurrence_path.map(edge=>({occurrence_uid:edge.occurrence_uid,item_revision_uid:edge.item_revision_uid}))};
  throw Error('unmapped');
 }
 function createViewerInteraction({api,onState=()=>{}}){
  let id=null,phase='closed',generation=0,epoch=null,scope=null,pendingMainOpen=false;const refs=new Map(),mapping=new Map();
  const state=value=>{phase=value;onState(value);};
  const check=()=>{if(!id||['closed','outcome_unknown','opening'].includes(phase))throw Error(phase==='outcome_unknown'?phase:'interaction_not_ready');};
  function completed(response){
   if(response?.status!=='completed'){
    const code=response?.status==='outcome_unknown'?'outcome_unknown':response?.error_code||response?.status||'interaction_response_invalid';
    state(code);throw Error(code);
   }
   return response.result;
  }
  const controller={
   get state(){return phase;},get scope(){return scope;},
   async open(input,method='open'){
    await controller.close();const token=++generation;pendingMainOpen=true;state('opening');
    try{const response=await api[method](input);if(token!==generation){if(response?.result?.interaction_id)await api.close({interaction_id:response.result.interaction_id});throw Error('document_selection_changed');}pendingMainOpen=false;
     const result=completed(response);
     if(typeof result?.interaction_id!=='string')throw Error('interaction_response_invalid');id=result.interaction_id;scope={...input};state('ready');return result;
    }catch(error){if(token===generation){if(error.message!=='interaction_bridge_timeout')pendingMainOpen=false;state(error.message);}throw error;}
   },
   openFromLaunch(input){return controller.open(input,'openFromLaunch');},
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
   async close(){const old=id,opening=pendingMainOpen;++generation;id=null;scope=null;refs.clear();mapping.clear();epoch=null;state('closed');if(old)await api.close({interaction_id:old});else if(opening)await api.cancelOpen?.({});pendingMainOpen=false;},
  };return controller;
 }
 function frameAPI(win=root){
  if(win.parent===win)return win.electronAPI?.viewerInteraction||null;
  // Only a real desktop parent installs the isolated relay. Never borrow its
  // public API: that would attribute every iframe call to the parent frame.
  try{if(!win.parent.electronAPI)return null;}catch{return null;}
  let opening=false;
  const invoke=(method,input)=>new Promise((resolve,reject)=>{
   const isOpen=method==='open'||method==='openFromLaunch';
   if(isOpen){if(opening){reject(Error('interaction_open_pending'));return;}opening=true;}
   const channel=new win.MessageChannel();
   let abandoned=false;
   const timer=win.setTimeout(()=>{
    abandoned=true;
    // An open may still install a grant in Main. Keep its reply port alive so
    // we can close that exact late session; no second open until cleanup.
    if(!isOpen)channel.port1.close();
    reject(Error(method==='execute'?'outcome_unknown':'interaction_bridge_timeout'));
   },15000);
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
  return Object.freeze({enabled:()=>invoke('enabled'),open:input=>invoke('open',input),openFromLaunch:input=>invoke('openFromLaunch',input),cancelOpen:input=>invoke('cancelOpen',input),resolve:input=>invoke('resolve',input),execute:input=>invoke('execute',input),close:input=>invoke('close',input)});
 }
 const api={createViewerInteraction,sourceDescriptor,frameAPI};root.AI00ViewerInteraction=api;
 if(typeof module!=='undefined')module.exports=api;
})(typeof window==='undefined'?globalThis:window);
