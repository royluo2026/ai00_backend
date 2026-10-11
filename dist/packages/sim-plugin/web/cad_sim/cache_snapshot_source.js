(function(root,factory){
  const api=factory(root);
  if(typeof module==='object'&&module.exports)module.exports=api;
  root.AI00CacheSnapshotSource=api;
})(typeof window!=='undefined'?window:globalThis,root=>{
  'use strict';
  const pending=new WeakMap();
  const identityKeys=['batch_id','generation','snapshot_hash','schema_version'];
  function partialTree(binding,context={}){
    return {state:'ready',source:'teamcenter_cache_snapshot',binding:{...binding},context,complete:false,node_count:0,nodes:[],pages:{}};
  }
  function validate(tree,page){
    if(!page?.identity||!Array.isArray(page.nodes)||page.nodes.length>500
      ||!(page.next_cursor===null||typeof page.next_cursor==='string'))throw Error('cache_snapshot_page_invalid');
    for(const key of identityKeys){
      // An older batch without a recorded digest stays pinned by batch/generation.
      if(key==='snapshot_hash'&&tree.binding[key]==null)continue;
      if(page.identity[key]!==tree.binding[key])throw Error('cache_snapshot_identity_mismatch');
    }
  }
  const payload=(tree,scope,nodeKey)=>({batch_id:tree.binding.batch_id,scope,projection:'structure',page_size:100,
    expected_generation:tree.binding.generation,expected_snapshot_hash:tree.binding.snapshot_hash,
    ...(nodeKey==null?{}:{node_key:nodeKey})});
  function productNode(node){
    if(typeof node.node_key!=='string'||!node.node_key||typeof node.has_children!=='boolean')throw Error('cache_snapshot_node_invalid');
    return {...node,cache_node_key:node.node_key,node_key:'cache:'+node.node_key,
      parent_key:node.parent_occurrence_id==null?null:'cache:'+node.parent_occurrence_id,
      revision:node.revision_id,visible:null,control_key:null};
  }
  function report(stage,tree,detail){try{root._simulationDebug?.(stage,{capability_id:'simulation.model_cache.query',capability_version:2,...tree.context,...tree.binding,message:`缓存批次 ${tree.binding.batch_id} · 节点 ${detail?.node_key??'根层'}`,...detail});}catch{}}
  function readChildren(invoke,tree,nodeKey=null,{more=false,isCurrent=()=>true}={}){
    const key=nodeKey??'roots';let reads=pending.get(tree);
    if(!reads){reads=new Map();pending.set(tree,reads);}
    if(reads.has(key))return reads.get(key);
    const old=tree.pages[key];
    if(more&&old?.next_cursor==null)return Promise.resolve();
    const request={...payload(tree,nodeKey==null?'roots':'children',nodeKey),cursor:more?old.next_cursor:null};
    tree.pages[key]={...old,state:'loading',error:null};
    const started=Date.now();report('cache_snapshot_page_started',tree,{node_key:nodeKey,cursor:request.cursor});
    const task=(async()=>{
      try{
        const page=await invoke('simulation.model_cache.query',request,{version:2});
        if(!isCurrent()){tree.pages[key]={...old,state:'failed',error:'cache_snapshot_read_interrupted'};return;}
        validate(tree,page);
        if(page.next_cursor!==null&&page.next_cursor===request.cursor)throw Error('cache_snapshot_cursor_stalled');
        const incoming=page.nodes.map(productNode);
        if(incoming.some(node=>node.parent_occurrence_id!==nodeKey))throw Error('cache_snapshot_parent_mismatch');
        const nodes=new Map(tree.nodes.map(node=>[node.node_key,node]));
        for(const node of incoming)nodes.set(node.node_key,{...nodes.get(node.node_key),...node});
        tree.nodes=[...nodes.values()];tree.node_count=tree.nodes.length;
        if(page.manifest)tree.manifest=page.manifest;
        tree.pages[key]={state:'loaded',generation:tree.binding.generation,next_cursor:page.next_cursor,error:null};
        report('cache_snapshot_page_completed',tree,{node_key:nodeKey,node_count:incoming.length,next_cursor:page.next_cursor,elapsed_ms:Date.now()-started});
      }catch(error){
        if(isCurrent())tree.pages[key]={...old,state:'failed',error:error.message};
        report('cache_snapshot_page_failed',tree,{node_key:nodeKey,error_code:error.message,elapsed_ms:Date.now()-started});throw error;
      }finally{reads.delete(key);}
    })();
    reads.set(key,task);return task;
  }
  async function readNode(invoke,tree,nodeKey){
    try{
      const page=await invoke('simulation.model_cache.query',{...payload(tree,'node',nodeKey),projection:'properties'},{version:2});
      validate(tree,page);
      if(page.nodes.length!==1||page.nodes[0].node_key!==nodeKey||!page.nodes[0].properties_result)throw Error('cache_snapshot_node_invalid');
      report('cache_snapshot_detail_completed',tree,{node_key:nodeKey});return page.nodes[0];
    }catch(error){report('cache_snapshot_detail_failed',tree,{node_key:nodeKey,error_code:error.message});throw error;}
  }
  return Object.freeze({partialTree,readChildren,readNode,productNode});
});
