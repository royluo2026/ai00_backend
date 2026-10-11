(function(root,factory){
  const api=factory();
  if(typeof module==='object'&&module.exports) module.exports=api;
  else root.AI00TreeProjectionCache=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
  function create(getApi,diagnostic=()=>{}){
    return {async run({workspaceGid,kind,load,render:display,isCurrent,useCache=false,previewCache=true,acceptCached=()=>true,preserveFreshItems=false}){
      const api=getApi?.(); let cached=null,view=null;
      const started=Date.now(),trace_id=globalThis.crypto?.randomUUID?.();
      const trace=(stage,detail={})=>{try{diagnostic(stage,{trace_id,workspace_gid:workspaceGid,cache_kind:kind,elapsed_ms:Date.now()-started,...detail});}catch{}};
      const render=(data,meta)=>display(data,{...meta,...(!data.items?.length?{cached_at:undefined,pending:false}:{}),workspaceGid,kind,viewState:view?.data});
      trace('projection_lookup');
      try { cached=await api?.get(workspaceGid,kind);trace(cached?'projection_hit':'projection_miss',{cached_at:cached?.cached_at}); } catch(error) { trace('projection_storage_failed',{error_code:error?.message,action:'read'}); }
      try { view=await api?.get(workspaceGid,kind+'-view'); } catch(_) {}
      if(!isCurrent()){trace('projection_stale');return;}
      if(cached) {
        try {
          if(!Array.isArray(cached.data?.items)) throw Error('cache_projection_invalid');
          if(previewCache){render(cached.data,{cached_at:cached.cached_at,pending:!useCache,cacheOnly:useCache});trace('projection_preview',{cached_at:cached.cached_at,item_count:cached.data.items.length,cache_state:'unverified'});}
          if(useCache&&acceptCached(cached.data)){trace('projection_accepted',{cache_state:'unverified'});return;}
          if(useCache)trace('projection_rejected',{reason:'accept_cached_false'});
        } catch(error) {trace('projection_rejected',{error_code:error?.message});cached=null;}
      }
      try {
        trace('projection_read_started');const data=await load(cached?.data);
        if(!isCurrent()){trace('projection_stale');return;}
        const failure=data.items?.find(item=>item.product_tree_error)?.product_tree_error;
        if(failure&&(/forbidden|unauthorized|not_found|permission_denied/.test(failure)||cached&&!preserveFreshItems)) throw Error(failure);
        render(data,{error:failure||null,...(failure&&cached&&previewCache?{cached_at:cached.cached_at}:{})});
        trace('projection_read_completed',{item_count:data.items?.length,error_code:failure||null});
        if(!failure&&api?.put) { try { await api.put(workspaceGid,kind,data);trace('projection_write'); } catch(error) {trace('projection_storage_failed',{action:'write',error_code:error?.message});} }
      } catch(error) {
        if(!isCurrent()) return;
        const message=error?.message||'tree_refresh_failed';
        trace('projection_failed',{error_code:message});
        if(/forbidden|unauthorized|not_found|permission_denied/.test(message)) {
          try { await api?.remove(workspaceGid,kind);trace('projection_removed'); } catch(error) {trace('projection_storage_failed',{action:'remove',error_code:error?.message});}
          render({items:[]},{error:message}); throw error;
        }
        if(cached){render(cached.data,{cached_at:cached.cached_at,error:message});trace('projection_fallback',{cached_at:cached.cached_at,cache_state:'unverified'});}
        else throw error;
      }
    }};
  }
  function bindView(host,api,{workspaceGid,kind,viewState}) {
    const same=host._viewWorkspace===workspaceGid&&host._viewKind===kind;
    host._viewWorkspace=workspaceGid; host._viewKind=kind;
    if(!same||!host._viewState) host._viewState=viewState||{expanded:[],scrollTop:0};
    host._viewRestoring=true;
    const expanded=new Set(host._viewState.expanded||[]);
    for(let pass=0;pass<64;pass++) {
      let changed=false;
      for(const row of host.querySelectorAll('[data-cache-view-key]')) {
        if(!expanded.has(row.dataset.cacheViewKey)) continue;
        const content=row.querySelector(':scope > .cs-model-document-tree, :scope > .cs-alternate-hierarchy-tree, :scope > .cs-alternate-tree-children');
        if(!content?.classList.contains('hidden')) continue;
        const toggle=row.querySelector(':scope > .cs-model-document-summary > button, :scope > .cs-alternate-tree-line > button, :scope > .cs-alternate-hierarchy-summary');
        if(toggle&&!toggle.disabled&&row.dataset.lazyUnloaded!=='true'&&(!row.dataset.cacheViewKey.startsWith('ah:')||content.childElementCount)) {toggle.click();changed=true;}
      }
      if(!changed) break;
    }
    host.scrollTop=host._viewState.scrollTop||0;
    host._viewRestoring=false;
    if(host._viewListener) return;
    host._viewListener=true;
    const remember=()=>{
      if(host._viewRestoring) return;
      const expanded=[];
      for(const row of host.querySelectorAll('[data-cache-view-key]')) {
        const content=row.querySelector(':scope > .cs-model-document-tree, :scope > .cs-alternate-hierarchy-tree, :scope > .cs-alternate-tree-children');
        if(content&&!content.classList.contains('hidden')) expanded.push(row.dataset.cacheViewKey);
      }
      host._viewState={expanded,scrollTop:host.scrollTop};
      const workspace=host._viewWorkspace,kind=host._viewKind,state=host._viewState;
      clearTimeout(host._viewTimer);
      host._viewTimer=setTimeout(()=>{void api?.put(workspace,kind+'-view',state).catch(()=>{});},200);
    };
    host.addEventListener('click',()=>{if(!host._viewRestoring) queueMicrotask(remember);},true);
    host.addEventListener('scroll',remember,{passive:true});
  }
  return {create,bindView};
});
