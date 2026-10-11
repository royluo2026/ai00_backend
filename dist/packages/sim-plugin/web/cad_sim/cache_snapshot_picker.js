(function(root){
 'use strict';
 async function open({invoke,workspace,isCurrent,onAdded}){
  const d=root.document,existing=d.getElementById('cacheSnapshotPickerOverlay');if(existing)return existing;
  const overlay=d.createElement('div');overlay.id='cacheSnapshotPickerOverlay';overlay.className='cs-modal-overlay';
  overlay.innerHTML='<div class="cs-modal cs-teamcenter-source-dialog"><div class="cs-modal-title">从共用数模缓存加载</div><p>选择已完成的缓存批次。模型树和属性固定在该批次，直接 TC 来源继续保留。</p><div data-results style="max-height:320px;overflow:auto"></div><button type="button" class="cs-btn" data-more>加载更多批次</button><div data-status role="status"></div><div class="cs-model-document-warning" data-error role="alert"></div><div class="cs-cache-selection" data-selection role="status">尚未选择批次</div><div class="cs-modal-actions"><button type="button" class="cs-btn" data-cancel>关闭</button><button type="button" class="cs-btn cs-btn-primary" data-add disabled>加载选中批次</button></div></div>';
  d.body.append(overlay);
  const results=overlay.querySelector('[data-results]'),status=overlay.querySelector('[data-status]'),error=overlay.querySelector('[data-error]');
  const add=overlay.querySelector('[data-add]'),more=overlay.querySelector('[data-more]'),summary=overlay.querySelector('[data-selection]');
  let cursor=0,selection=null,selectionRequest=0,busy=false,insertionId=null,boundResult=null;
  const active=()=>overlay.isConnected&&isCurrent();
  const projects=new Map(),seenBatches=new Set();
  const group=(parent,className,label,open)=>{
   const details=d.createElement('details');details.className=className;details.open=open;
   const heading=d.createElement('summary');heading.textContent=label;details.append(heading);parent.append(details);return details;
  };
  const batchGroup=batch=>{
   const projectKey=batch.project_gid||batch.project_name||'unknown';
   if(!projects.has(projectKey))projects.set(projectKey,{element:group(results,'cs-cache-project',batch.project_name||'未命名项目',true),versions:new Map()});
   const project=projects.get(projectKey),versionKey=JSON.stringify([batch.phase||'',batch.display_name||'']);
   if(!project.versions.has(versionKey))project.versions.set(versionKey,group(project.element,'cs-cache-version',[batch.phase,batch.display_name||'未标注版本'].filter(Boolean).join(' · '),project.versions.size===0));
   return project.versions.get(versionKey);
  };
  overlay.querySelector('[data-cancel]').onclick=()=>{if(!busy){selectionRequest++;overlay.remove();}};
  const load=async()=>{
   more.disabled=true;error.textContent='';if(!selectionRequest)status.textContent='读取缓存批次…';
   try{
    const page=await invoke('simulation.model_cache.list',{cursor,page_size:100});if(!active())return;
    for(const batch of page.batches.filter(b=>b.status==='completed')){
     if(seenBatches.has(batch.batch_id))continue;seenBatches.add(batch.batch_id);
     const button=d.createElement('button');button.type='button';button.className='cs-btn cs-cache-batch';button.dataset.batch=batch.batch_id;button.setAttribute('aria-pressed','false');
     const label=[batch.project_name,batch.phase,batch.display_name,batch.completed_at,batch.batch_id.slice(0,8)].filter(Boolean).join(' · ');
     const marker=d.createElement('span');marker.className='cs-cache-batch-marker';marker.setAttribute('aria-hidden','true');
     const text=d.createElement('span');text.textContent=[batch.completed_at||batch.created_at||'时间未记录',batch.batch_id.slice(0,8)].join(' · ');button.append(marker,text);button.title=label+' · '+batch.batch_id;
     button.onclick=async()=>{
      if(busy||boundResult)return;const request=++selectionRequest;selection=null;add.disabled=true;error.textContent='';status.textContent='核对批次…';
      for(const row of results.querySelectorAll('[data-batch]')){row.classList.toggle('selected',row===button);row.setAttribute('aria-pressed',String(row===button));}
      summary.textContent='当前选择：'+label;
      try{
       const page=await invoke('simulation.model_cache.query',{batch_id:batch.batch_id,scope:'roots',projection:'structure',page_size:1},{version:2});
       if(!active()||request!==selectionRequest)return;
       if(page.identity?.batch_id!==batch.batch_id||!page.manifest)throw Error('cache_snapshot_identity_mismatch');
       selection={identity:page.identity,batch};insertionId=Array.from(root.crypto.getRandomValues(new Uint8Array(16)),value=>value.toString(16).padStart(2,'0')).join('');
       status.textContent=`${page.manifest.node_count} 个节点 · ${['ready','partial'].includes(batch.preparation_status)?'装配依据已准备，JT 将按需下载到本机':'可浏览结构；请先在数模缓存模块准备装配数据'}`;
       add.disabled=false;
      }catch(exc){if(request===selectionRequest&&active()){error.textContent=exc.message;status.textContent='批次核对失败';}}
     };batchGroup(batch).append(button);
    }
    cursor=page.next_cursor;more.hidden=cursor==null;
    if(!selectionRequest)status.textContent=results.children.length?'请选择一个缓存批次':'这一页没有已完成批次';
   }catch(exc){if(active())error.textContent=exc.message;}
   finally{more.disabled=false;}
  };
  more.onclick=()=>void load();
  add.onclick=async()=>{
   if(busy||!selection)return;
   if(!active()){error.textContent='仿真环境已切换，请关闭后重新选择';return;}
   busy=true;add.disabled=true;error.textContent='';status.textContent='正在关联缓存批次…';
   const chosen=selection;
   try{
    if(!boundResult){
    const latest=await invoke('simulation.environment.workspace.get',{workspace_gid:workspace.workspace_gid});
    if(!active()||latest.workspace_gid!==workspace.workspace_gid)throw Error('仿真环境已切换，请重新选择');
    boundResult=await invoke('simulation.environment.cache_source.bind',{
     workspace_gid:workspace.workspace_gid,expected_row_version:latest.row_version,
     display_name:[chosen.batch.project_name,chosen.batch.display_name||chosen.batch.phase||chosen.batch.batch_id].filter(Boolean).join(' · ').slice(0,255),
     insertion_instance_id:insertionId,cache_binding:chosen.identity,
    },{idempotency:true,idempotencyKey:'cache-source-'+insertionId,expectedResourceVersion:latest.row_version});
    }
    if(!active())return;
    await onAdded(boundResult);overlay.remove();
   }catch(exc){if(overlay.isConnected){error.textContent=exc.message;status.textContent=boundResult?'批次已关联，列表刷新失败，可重试':'插入未完成，可重试';}}
   finally{busy=false;add.disabled=false;}
  };
  await load();return overlay;
 }
 root.AI00CacheSnapshotPicker=Object.freeze({open});
})(window);
