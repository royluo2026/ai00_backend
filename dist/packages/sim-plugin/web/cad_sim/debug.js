(function(root){
 'use strict';
 const labels={
  local_cache_checked:'检查本机 JT 缓存',jt_download_started:'从 TC/FMS 下载 JT',jt_download_completed:'JT 下载完成',local_file_verified:'本机 JT 校验完成',local_materialization_failed:'本机 JT 准备失败',native_open_started:'VisMockup 开始载入',native_open_completed:'VisMockup 载入完成',
  cache_viewer_dependencies_resolved:'已确认 TC 文件引用',cache_viewer_assembly_prepared:'共享装配依据就绪',cache_viewer_local_materialization:'本机下载与打开',
  cache_viewer_stage:'固定快照模型加载',cache_viewer_waiting_admission:'等待执行名额或已有请求',cache_viewer_node_excluded:'缓存节点未加载及原因',cache_viewer_inspecting:'读取固定快照',cache_viewer_file_requested:'请求精确 JT 文件',cache_viewer_file_completed:'精确 JT 文件就绪',cache_viewer_files_progress:'缓存文件获取进度',cache_viewer_building_package:'构建缓存装配',cache_viewer_opening_document:'打开缓存装配',cache_viewer_binding_document:'核对缓存文档身份',cache_viewer_ready:'缓存文档就绪',cache_viewer_failed:'缓存文档打开失败',
  cache_snapshot_page_started:'读取固定缓存批次节点',cache_snapshot_page_completed:'缓存批次节点读取完成',cache_snapshot_page_failed:'缓存批次节点读取失败',cache_snapshot_detail_completed:'缓存批次属性读取完成',cache_snapshot_detail_failed:'缓存批次属性读取失败',
  node_document_prepared:'所选版本独立文档已登记',document_source_resolution:'确认文档打开来源',gateway_source_unassociated:'所选文档尚未打开',
  source_scope_mismatch:'所属文档与显隐校准说明',source_scope_choice:'模型打开范围选择',source_open_started:'开始打开所属文档',source_open_completed:'所属文档打开完成',source_open_failed:'所属文档打开失败',
  visibility_calibration_started:'读取 VisMockup 实际显隐',visibility_calibration_completed:'实际显隐读取完成',
  visibility_calibrated:'节点实际显隐回读',
  document_management_read:'读取后台文档列表',document_management_failed:'后台文档列表读取失败',document_close_started:'请求关闭非活动文档',document_close_completed:'非活动文档已关闭',document_close_pending:'等待原生窗口完成关闭',document_close_failed:'关闭文档失败',document_close_bulk_completed:'批量关闭非活动文档结束',
  current_document_preview_completed:'当前文档已显示在右侧',current_document_preview_failed:'当前文档显示失败',
  environment_document_identity_check:'正在核对环境对应的窗口身份',environment_document_identity_mismatch:'窗口身份不匹配，继续查找',environment_document_restored:'已恢复环境对应的文档窗口',environment_cache_controls_calibrated:'缓存实例控制与显隐已校准',environment_cache_controls_rejected:'缓存控制恢复拒绝，保留原生窗口',environment_document_detach_failed:'旧环境文档连接释放失败',
  tc_path_choice_required:'缓存路径不一致，等待用户选择',tc_path_choice:'缓存处理选择',tc_path_baseline_saved:'原缓存对比基线已保存',tc_path_refreshed:'按用户选择刷新分支',tc_path_refresh_failed:'分支刷新失败',
  gateway_capability_started:'调用 Capability',gateway_capability_completed:'Capability 返回',gateway_capability_failed:'Capability 调用失败',gateway_capability_awaiting_confirmation:'等待用户确认',
  live_tree_verification_started:'验证当前文档与环境绑定',live_tree_binding_mismatch:'文档与环境绑定不一致',live_tree_session_verified:'读取前后文档身份一致',live_tree_result_verified:'实时树结果验证通过',live_tree_verification_failed:'实时树验证失败',plmxml_tree_page:'读取 PLMXML 模型树分页',plmxml_tree_verified:'PLMXML 分页完整性验证通过',plmxml_tree_failed:'PLMXML 模型树验证失败',
  intent_started:'操作开始',intent_completed:'操作结束',intent_mapped:'定位目标已确认',request_started:'请求发送',request_completed:'请求返回',request_failed:'请求失败',
  execute_received:'原生执行受理',execute_admitted:'操作已写入执行日志',native_started:'进入原生执行队列',native_write:'调用 VisMockup',native_settled:'原生调用返回',native_failed:'原生调用失败',adapter_failed:'原生适配失败',visibility_readback:'显隐状态回读',target_completed:'节点执行结果',execute_completed:'执行结果落盘',journal_failed:'执行日志写入失败',node_mapped:'节点定位成功',node_unmapped:'节点定位失败',runtime_started:'Connector 已启动',
  ui_action_started:'页面节点操作',ui_state_applied:'界面状态已更新',ui_action_failed:'页面节点操作失败',ui_notice:'页面提示',ui_error:'页面异常',
  capability_started:'业务能力请求',capability_completed:'业务能力返回',capability_failed:'业务能力失败',command_progress:'Connector 命令状态',command_step:'Connector 执行步骤',
  projection_lookup:'查询结构缓存',projection_hit:'结构缓存命中',projection_miss:'结构缓存未命中',projection_rejected:'结构缓存校验未通过',projection_preview:'展示缓存预览（未核对）',projection_accepted:'复用结构缓存（未核对）',projection_read_started:'获取模型树',projection_read_completed:'模型树获取完成',projection_write:'保存结构缓存',projection_failed:'结构获取失败',projection_fallback:'回退到已有结构缓存',projection_removed:'失效缓存已清理',projection_storage_failed:'缓存存储失败',projection_stale:'丢弃过期结构响应',
  tc_page_started:'读取 Teamcenter 子节点',tc_page_shared:'复用正在读取的分页请求',tc_page_validated:'来源 / 游标 / 代次校验通过',tc_page_rejected:'分页校验失败',tc_page_applied:'模型树分页已合并',tc_page_stale:'丢弃旧环境的分页响应',tc_page_failed:'模型树分页读取失败',
  native_tree_started:'原生模型树读取',native_tree_traversal:'遍历原生模型树',native_tree_completed:'原生模型树读取完成',native_tree_failed:'原生模型树读取失败',native_cache_lookup:'查询 Connector 树缓存',native_cache_miss:'Connector 树缓存未命中',native_cache_validation:'校验 Connector 缓存身份',native_cache_hit:'Connector 树缓存命中',native_cache_write:'写入 Connector 树缓存',native_cache_saved:'Connector 树缓存已保存',native_cache_skipped:'Connector 缓存写入跳过',ui_tree_validated:'模型树结果检查',ui_tree_rendered:'模型树已渲染',
 };
 const actions={show:'显示',hide:'隐藏',highlight:'高亮',unhighlight:'取消高亮'};
 const methods={resolve_nodes:'节点定位',prepare_document:'准备文档',activate_document:'激活文档',ensureReady:'确认文档就绪',openFromCache:'缓存模型关联',executeCachedIntent:'缓存实例操作',executeIntent:'模型操作',execute:'原生执行'};
 function awaitingConfirmation(event){return event.stage==='gateway_capability_awaiting_confirmation'||event.stage==='gateway_capability_failed'&&event.detail?.error_code==='confirmation_required';}
 function stateOf(event){const d=event.detail||{};if(awaitingConfirmation(event)||event.stage==='gateway_source_unassociated')return'info';if(d.status==='outcome_unknown'||['verifying','unverified'].includes(d.cache_state)||d.verified===false||d.level==='warn')return'unknown';if(d.level==='error'||d.error_code||/failed|rejected|unmapped|journal_failed|ui_error/.test(event.stage)||['failed','rejected','Faulted','cancelled'].includes(d.status))return'error';if(d.status==='pending')return'info';if(event.stage==='runtime_started')return'success';if(/started|lookup|traversal|native_write|admitted/.test(event.stage)||['queued','running','executing','leased'].includes(d.status))return'running';if(d.verified===true||/completed|validated|verified|applied|saved|node_mapped|readback/.test(event.stage)||['completed','succeeded','RanToCompletion'].includes(d.status))return'success';return'info';}
 function createPanel({document:doc,api,schedule=setTimeout,cancel=clearTimeout}){
  const $=id=>doc.getElementById(id);let events=[],paused=false,since=0,timer,disposed=false,visible=[];
  function render(){
   const query=$('search').value.trim().toLowerCase(),filter=$('filter').value;
   const current=events.filter(e=>Date.parse(e.timestamp)>=since);
   const keys=e=>['operation_id','trace_id','request_id','intent_id'].filter(k=>e.detail?.[k]).map(k=>k+':'+e.detail[k]);
   const matches=new Set(current.filter(e=>!query||JSON.stringify(e).toLowerCase().includes(query)).map(e=>e.id));
   // A queued Capability returns before its command fails. Keep the correlated
   // operation/trace even when those later records don't repeat the Capability ID.
   const related=new Set(current.filter(e=>matches.has(e.id)).flatMap(keys));
   visible=current.filter(e=>(matches.has(e.id)||keys(e).some(k=>related.has(k)))&&(filter!=='errors'||['error','unknown'].includes(stateOf(e)))&&(filter!=='tree'||/tree|cache|projection|tc_page|tc_path|structure|snapshot|verification/.test(JSON.stringify(e)))&&(filter!=='control'||!/projection|tc_page|native_cache/.test(e.stage)));
   const list=$('timeline'),scroll=list.scrollTop,existing=new Map([...list.querySelectorAll('[data-event-id]')].map(el=>[el.dataset.eventId,el]));
   const rows=visible.map(e=>{
    if(existing.has(e.id))return existing.get(e.id);
    const row=doc.createElement('details');row.className='event '+stateOf(e);row.dataset.eventId=e.id;
    const summary=doc.createElement('summary'),d=e.detail;
    const add=(cls,value)=>{const el=doc.createElement('span');el.className=cls;el.textContent=value;summary.append(el);};
    add('time',new Date(e.timestamp).toLocaleTimeString('zh-CN',{hour12:false})+'.'+String(new Date(e.timestamp).getMilliseconds()).padStart(3,'0'));
    add('source',e.source);add('mark',({error:'✕',unknown:'?',success:'✓',running:'›',info:'·'})[stateOf(e)]);
    add('title',([actions[d.action]||methods[d.method],awaitingConfirmation(e)?labels.gateway_capability_awaiting_confirmation:labels[e.stage]||e.stage]).filter(Boolean).join(' · '));
    add('duration',Number.isFinite(d.elapsed_ms)?Math.round(d.elapsed_ms)+' ms':'');row.append(summary);
    const capability=d.capability_id?d.capability_id+(d.capability_version!=null?' @ v'+d.capability_version:''):null;
    const local=!capability&&(/^(projection_(lookup|hit|miss|preview|accepted|rejected|write|fallback|removed|storage_failed|stale)|native_cache_|ui_tree_|tc_page_(validated|rejected|applied|stale)|live_tree_(session_verified|result_verified|binding_mismatch)|plmxml_tree_verified)/.test(e.stage)||e.source==='Connector');
    const context=doc.createElement('span');context.className='context';context.textContent=[d.node_name,capability,local?'本地处理':null,d.status,d.error_code,d.failed_step_id?'失败步骤 '+d.failed_step_id:null,d.reason,d.message,d.node_count!=null?d.node_count+' 节点':null,d.cache_state,d.operation_id?'操作 '+d.operation_id:null,d.request_id?'请求 '+d.request_id:null].filter(Boolean).join(' · ');if(context.textContent)summary.append(context);
    const detail=doc.createElement('pre');detail.textContent=JSON.stringify(e,null,2);row.append(detail);return row;
   });
   if(!rows.length){const empty=doc.createElement('p');empty.className='empty';empty.textContent=events.length?'没有符合筛选条件的记录':'继续操作数模，执行步骤会显示在这里。';rows.push(empty);}
   list.replaceChildren(...rows);list.scrollTop=$('follow').checked?list.scrollHeight:scroll;
   const errors=visible.filter(e=>stateOf(e)==='error').length,hiddenErrors=current.filter(e=>stateOf(e)==='error').length-errors;
   $('summary').textContent='显示 '+visible.length+' / '+current.length+' 条 · '+errors+' 条错误 · '+visible.filter(e=>stateOf(e)==='unknown').length+' 条待确认'+(hiddenErrors?' · 筛选隐藏 '+hiddenErrors+' 条错误':'');
   $('resetFilters').hidden=!query&&filter==='all';
  }
  async function refresh(){
   try{const data=await api.read();if(disposed||paused)return;events=data.events;render();$('connection').textContent='● 实时';$('connection').className='';$('sources').textContent=data.sources.map(s=>s.source+'：'+(s.state==='ready'?'已接入':s.state==='missing'?'尚无记录':'读取失败 '+s.error_code)).join(' · ');}
   catch(error){if(!disposed){$('connection').textContent='日志读取失败 · '+error.message;$('connection').className='read-error';}}
  }
  const loop=async()=>{if(disposed)return;if(!paused)await refresh();if(!disposed)timer=schedule(loop,1000);};
  $('search').addEventListener('input',render);$('filter').addEventListener('change',render);
  $('resetFilters').addEventListener('click',()=>{$('search').value='';$('filter').value='all';render();});
  $('pause').addEventListener('click',()=>{paused=!paused;$('pause').textContent=paused?'继续刷新':'暂停刷新';$('connection').textContent=paused?'Ⅱ 已暂停显示':'● 实时';if(!paused)void refresh();});
  $('clear').addEventListener('click',()=>{since=Date.now();render();});
  $('copy').addEventListener('click',async()=>{try{await api.copy(visible.map(e=>JSON.stringify(e)).join('\n'));$('copy').textContent='已复制';}catch{$('copy').textContent='复制失败';}schedule(()=>{if(!disposed)$('copy').textContent='复制日志';},1800);});
  void loop();return{refresh,dispose(){disposed=true;cancel(timer);}};
 }
 if(typeof module==='object')module.exports={createPanel,stateOf};
 if(root.document&&root.AI00SimulationDebug){const panel=createPanel({document:root.document,api:root.AI00SimulationDebug});root.addEventListener('unload',()=>panel.dispose(),{once:true});}
})(typeof window==='undefined'?globalThis:window);
