/* Independent project cache App. TC transport is the existing governed Connector. */
(async function(){
  'use strict';
  const $=id=>document.getElementById(id),M=window.AI00ModelCache;
  const status={queued:'等待缓存',running:'正在缓存',paused:'已暂停',waiting_connector:'等待 Connector',waiting_auth:'等待 TC 登录',needs_refresh:'数据已变化，需新建批次',failed:'缓存失败',completed:'结构缓存完成'};
  const preparation={not_prepared:'装配数据待准备',queued:'装配数据准备中',ready:'装配依据就绪 · JT 按需下载',partial:'部分装配可用 · 缺项可查看',failed:'装配准备失败'};
  const api=()=>window.electronAPI||window.parent?.electronAPI;
  const invoke=(id,payload={},options={})=>window.AI00Business.invoke(id,{version:1,payload,...options});
  const write=(id,payload,options={})=>invoke(id,payload,{idempotency_key:crypto.randomUUID(),...options});
  let batches=[],selected=null,grid=null,querySequence=0,queryBusy=0,renderedBatchId=null,renderedVersion=null,cursor=0,total=0,next=null,catalog=[],filters=[],hidden=new Set(),columnChoices=new Map(),detailRow=null,canTrigger=false,source=null,busy=false,listBusy=false;
  const escape=value=>String(value).replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  function notice(error){$('notice').textContent=error?.message||String(error||'');}
  function option(value,label){const el=document.createElement('option');el.value=value;el.textContent=label;return el;}
  function theme(){try{document.documentElement.dataset.theme=window.parent.document.documentElement.dataset.theme||'dark';}catch{}}
  theme();window.addEventListener('message',event=>{if(event.data?.type==='theme')document.documentElement.dataset.theme=event.data.theme||'dark';});

  async function requireRuntime(){
    const state=await api()?.getConnectorState?.();
    if(state?.status!=='ready'||state?.health!=='healthy')throw Error('请先在 AI00 App 中启动并连接 Connector');
    if(state.pairing?.state==='created')await window.AI00Business.invoke('simulation.connector.pairing.approve',{version:2,payload:{pairing_id:state.pairing.id,expected_version:1}},()=>window.AI00Dialogs.confirm('确认将当前 Connector 绑定到本账号？'));
    return state;
  }
  let commandQueue=Promise.resolve();
  function requestConnector(id,payload){
    const run=async()=>{
      await requireRuntime();
      const operation=await invoke(id,payload);
      for(let attempt=0;attempt<750;attempt++){
        const command=await invoke('simulation.vismockup.command.get',{operation_id:operation.operation_id});
        if(command.status==='completed')return command.outcome;
        if(['failed','expired','cancelled','outcome_unknown','manual_review_required'].includes(command.status))throw Error(command.outcome?.steps?.at(-1)?.error_code||command.status);
        await new Promise(resolve=>setTimeout(resolve,400));
      }
      throw Error('TC 查询超时，请检查 Connector 状态');
    };
    const pending=commandQueue.catch(()=>{}).then(run);commandQueue=pending;return pending;
  }

  function renderTree(){
    const openKeys=new Set([...$('tree').querySelectorAll('details[open]')].map(el=>el.dataset.key));
    const hadTree=$('tree').childElementCount>0;
    $('tree').replaceChildren();
    for(const project of M.groupBatches(batches)){
      const group=document.createElement('details');group.dataset.key='p:'+project.id;group.open=!hadTree||openKeys.has(group.dataset.key);
      const title=document.createElement('summary');title.textContent=project.name||`项目 ${project.id}`;group.append(title);
      for(const phase of project.phases){
        const subgroup=document.createElement('details');subgroup.dataset.key='s:'+project.id+':'+phase.name;subgroup.open=!hadTree||openKeys.has(subgroup.dataset.key);
        const label=document.createElement('summary');label.textContent=phase.name;subgroup.append(label);
        for(const batch of phase.batches){
          const button=document.createElement('button');button.className='batch'+(selected?.batch_id===batch.batch_id?' active':'');
          const name=document.createElement('span');name.textContent=batch.display_name;
          const meta=document.createElement('small');meta.textContent=`${new Date(batch.created_at).toLocaleString()} · ${status[batch.status]}${batch.status==='completed'?' · '+(preparation[batch.preparation_status]||preparation.not_prepared):''} · ${batch.node_count} 个节点`;
          button.append(name,meta);button.onclick=()=>selectBatch(batch);subgroup.append(button);
        }
        group.append(subgroup);
      }
      $('tree').append(group);
    }
    if(!batches.length){const empty=document.createElement('p');empty.className='empty';empty.textContent='暂无可查看的缓存批次';$('tree').append(empty);}
  }
  function metadata(){
    if(!selected)return;
    $('batch-title').textContent=selected.display_name;
    $('batch-meta').textContent=`${selected.project_name} / ${selected.phase||'未分期'} · ${status[selected.status]} · 创建 ${new Date(selected.created_at).toLocaleString()}${selected.completed_at?' · 完成 '+new Date(selected.completed_at).toLocaleString():''} · 版本规则 ${selected.source_selector.revision_rule} · 配置时间 ${new Date(selected.source_selector.configuration_date).toLocaleString()}`;
    $('batch-meta').title=JSON.stringify(selected.source_selector,null,2);
    if(selected.status==='running')$('batch-meta').textContent+=catalog.some(path=>path.startsWith('/properties_result/'))?' · 正在补全节点属性':' · 正在采集结构树，完成后读取节点属性';
    const pause=['queued','running','waiting_connector','waiting_auth'].includes(selected.status);
    $('control').hidden=!canTrigger||!['queued','running','waiting_connector','waiting_auth','paused','failed'].includes(selected.status);
    $('control').textContent=pause?'暂停缓存':'继续缓存';$('control').dataset.action=pause?'pause':'resume';
    if(selected.status==='completed'){
      $('batch-meta').textContent+=' · '+(preparation[selected.preparation_status]||preparation.not_prepared)+' · 共用装配数据，JT 由各客户端自行下载';
      if(selected.preparation_error)$('batch-meta').textContent+=' · '+selected.preparation_error;
      $('control').hidden=!canTrigger||['ready','partial','queued'].includes(selected.preparation_status);
      $('control').textContent='准备装配数据';$('control').dataset.action='prepare';
    }
    if(selected.error_code)$('batch-meta').textContent+=' · '+selected.error_code;
  }
  async function loadIndex(){
    if(listBusy)return;listBusy=true;
    try{
      const loaded=[];let indexCursor=0,index;
      do{index=await invoke('simulation.model_cache.list',{cursor:indexCursor,page_size:500});loaded.push(...index.batches);indexCursor=index.next_cursor??null;}while(indexCursor!==null);
      batches=loaded;canTrigger=index.can_trigger;$('create').hidden=!canTrigger;
      if(selected){selected=batches.find(batch=>batch.batch_id===selected.batch_id)||selected;metadata();}
      renderTree();
    }catch(error){notice(error);}finally{listBusy=false;}
  }
  async function selectBatch(batch){++querySequence;selected=batch;cursor=0;hidden=new Set();columnChoices=new Map();filters=[];currentRows=[];catalog=[];total=0;next=null;grid?.destroy();grid=null;$('grid').textContent='正在读取缓存…';$('count').textContent='';$('prev').disabled=$('next').disabled=true;renderFilters();renderTree();metadata();$('detail').hidden=true;await query();}
  function renderColumns(){
    $('column-options').replaceChildren();
    for(const key of displayColumns()){
      const label=document.createElement('label'),box=document.createElement('input');box.type='checkbox';box.checked=!hidden.has(key);
      box.onchange=()=>{columnChoices.set(key,box.checked);box.checked?hidden.delete(key):hidden.add(key);renderGrid();};label.title=key;label.append(box,document.createTextNode(M.fieldLabel(key)));$('column-options').append(label);
    }
  }
  let currentRows=[];
  const propertyColumns=['item_id','revision_id','component_type','owning_user','owning_group','weight_raw','unit_weight_raw','torque_raw','torque_importance',...Object.keys(M.modelFieldSources)].map(key=>'/properties_result/properties/'+key);
  const displayColumns=()=>[...new Set([...catalog,...propertyColumns])];
  let previousCursors=[];
  function renderGrid(){
    grid?.destroy();
    const priority=key=>key==='/structure/name'?0:key.startsWith('/properties_result/properties/')?1:key.startsWith('/structure/')?2:key.startsWith('/properties_result/raw_fields/')?3:4;
    const columns=displayColumns().filter(key=>!hidden.has(key)).sort((a,b)=>priority(a)-priority(b)).map(key=>({key,label:M.fieldLabel(key),width:key==='/structure/name'?320:220,editable:false}));
    const rows=currentRows.map(row=>{
      const raw=JSON.parse(row.data_json),values=M.flatten(raw),properties=M.modelProperties(raw);
      for(const key of Object.keys(M.modelFieldSources))if(Object.hasOwn(properties,key))values['/properties_result/properties/'+key]=properties[key];
      return {...values,gid:row.node_key,_raw:raw};
    });
    grid=new GridEditor({containerEl:$('grid'),columns,rows,readOnly:true,draggableRows:false,onRowClick:row=>showDetail(row._raw),cellRenderer:Object.fromEntries(columns.map(col=>[col.key,(value,row)=>{
      const source=M.modelFieldSources[col.key.split('/').at(-1)],entry=source?row._raw.properties_result?.raw_fields?.find(field=>field.field===source):null;
      const text=col.key.startsWith('/properties_result/properties/')&&!row._raw.properties_result?'待采集属性':source&&Array.isArray(value)?M.cellDisplay(value):source&&!entry?'未采集此字段':entry?.read_state==='unavailable'?'TC 字段不可读':M.cellDisplay(M.fieldValue(col.key,value));
      if(col.key==='/structure/name'){
        const depth=Math.min(128,Math.max(0,Number(row._raw.structure.depth)||0));
        return `<span class="cache-node-name" style="padding-left:${Math.min(depth,12)*14}px" title="第 ${depth+1} 层 · ${escape(text)}">${depth?'↳ ':''}${escape(text)}</span>`;
      }
      return `<span title="${escape(text)}">${escape(text)}</span>`;
    }]))});
    if(!rows.length){const empty=document.createElement('p');empty.className='empty';empty.textContent='没有符合条件的已缓存数据';$('grid').append(empty);}
  }
  async function query(){
    if(!selected)return;
    if(cursor===0)previousCursors=[];
    const sequence=++querySequence,batchId=selected.batch_id;
    ++queryBusy;
    try{
      const result=await invoke('simulation.model_cache.query',{batch_id:batchId,search:$('search').value,filters,mode:$('mode').value,cursor,page_size:100});
      if(sequence!==querySequence||selected.batch_id!==batchId)return;
      currentRows=result.rows;catalog=result.fields;total=result.total;next=result.next_cursor;selected=result.batch;
      const leaves=new Set(M.leafFields(catalog));
      hidden=new Set(displayColumns().filter(key=>columnChoices.has(key)?!columnChoices.get(key):catalog.includes(key)&&!leaves.has(key)));
      renderColumns();renderGrid();metadata();$('count').textContent=`${total} 条匹配 · 当前 ${total?cursor+1:0}–${cursor+currentRows.length} · ${leaves.size} 个值字段（点击行查看完整值与原始数据）`;
      $('prev').disabled=cursor===0;$('next').disabled=next===null;
      renderedBatchId=batchId;renderedVersion=result.batch.row_version;
    }catch(error){if(sequence===querySequence)notice(error);}finally{--queryBusy;}
  }
  function showDetail(row){detailRow=row;$('detail').hidden=false;renderDetail();}
  function renderDetail(){
    $('detail-values').replaceChildren();const list=document.createElement('dl'),search=$('detail-search').value.toLocaleLowerCase();
    const spatial=M.modelProperties(detailRow);
    for(const key of ['default_transform','absolute_transform','relative_transform','bbox']){
      const source=M.modelFieldSources[key],entry=detailRow.properties_result?.raw_fields?.find(field=>field.field===source),label=M.fieldLabel('/'+key),value=spatial[key];
      const text=Array.isArray(value)?(value.length===16?Array.from({length:4},(_,row)=>value.slice(row*4,row*4+4).join('  ')).join('\n'):value.join('  ')):!entry?'未采集此字段':entry.read_state==='unavailable'?'TC 字段不可读':M.display(value);
      if(!(label+' '+source+' '+text).toLocaleLowerCase().includes(search))continue;
      const term=document.createElement('dt'),definition=document.createElement('dd'),pre=document.createElement('pre');term.textContent=label;term.title=source;pre.textContent=text;definition.append(pre);list.append(term,definition);
    }
    const values=M.flatten(detailRow);
    for(const key of Object.keys(values))if(/^\/properties_result\/raw_fields\/\d+\/value_json$/.test(key)){
      const decoded=M.fieldValue(key,values[key]);if(decoded&&typeof decoded==='object')M.flatten(decoded,key,values);
    }
    for(const key of M.leafFields(Object.keys(values))){
      const text=M.fieldDisplay(key,values[key]),label=M.fieldLabel(key);
      if(!(key+' '+label+' '+text).toLocaleLowerCase().includes(search))continue;
      const term=document.createElement('dt'),definition=document.createElement('dd'),pre=document.createElement('pre');term.textContent=label;term.title=key;pre.textContent=text;definition.append(pre);list.append(term,definition);
    }
    $('detail-values').append(list);$('detail-raw').textContent=JSON.stringify(detailRow,null,2);
  }
  function filterValue(text,field,op,kind='text'){
    if(/^\/properties_result\/raw_fields\/\d+\/value_json$/.test(field)&&['eq','ne'].includes(op)){
      return JSON.stringify(JSON.stringify(kind==='null'?null:kind==='json'?JSON.parse(text):text));
    }
    let value=text;try{value=JSON.parse(text);}catch{}
    return JSON.stringify(value);
  }
  function renderFilters(){
    $('filters').replaceChildren();
    filters.forEach((filter,index)=>{
      const row=document.createElement('div');row.className='filter';
      const field=document.createElement('select');field.setAttribute('aria-label','筛选字段');for(const path of catalog)field.append(option(path,M.fieldLabel(path)));field.value=filter.field;
      const op=document.createElement('select');op.setAttribute('aria-label','筛选操作');for(const [key,label]of [['eq','等于'],['ne','不等于'],['contains','包含'],['exists','字段存在'],['empty','为空'],['not_empty','非空'],['gt','大于'],['gte','大于等于'],['lt','小于'],['lte','小于等于']])op.append(option(key,label));op.value=filter.op;
      const value=document.createElement('input');value.setAttribute('aria-label','筛选值');value.placeholder='文本或 JSON 值';
      let expected=JSON.parse(filter.value_json);if(['eq','ne'].includes(filter.op))expected=M.fieldValue(filter.field,expected);
      const rawEquality=/^\/properties_result\/raw_fields\/\d+\/value_json$/.test(filter.field)&&['eq','ne'].includes(filter.op);
      const kind=document.createElement('select');kind.setAttribute('aria-label','筛选值类型');kind.append(option('text','文本'),option('null','空值（null）'),option('json','JSON 数组或对象'));kind.value=rawEquality&&expected===null?'null':rawEquality&&typeof expected!=='string'?'json':'text';
      value.value=expected===null?(rawEquality?'':'null'):typeof expected==='string'?expected:JSON.stringify(expected);
      if(rawEquality){value.placeholder='输入表格显示的文本';value.disabled=kind.value==='null';}
      const remove=document.createElement('button');remove.textContent='×';remove.setAttribute('aria-label','删除筛选条件');
      const change=()=>{
        let encoded;try{encoded=filterValue(value.value,field.value,op.value,kind.value);}catch{notice('请输入有效的 JSON 值');return;}
        notice('');filter.field=field.value;filter.op=op.value;filter.value_json=encoded;value.disabled=kind.value==='null';cursor=0;void query();
      };
      field.onchange=op.onchange=()=>{change();renderFilters();};value.onchange=kind.onchange=change;
      remove.onclick=()=>{filters.splice(index,1);renderFilters();cursor=0;void query();};row.append(field,op);if(rawEquality)row.append(kind);row.append(value,remove);$('filters').append(row);
    });
  }
  $('add-filter').onclick=()=>{if(!catalog.length)return;filters.push({field:catalog[0],op:'contains',value_json:'""'});renderFilters();};
  $('columns-button').onclick=()=>{$('columns').open=!$('columns').open;};
  let timer;$('search').oninput=()=>{clearTimeout(timer);timer=setTimeout(()=>{cursor=0;void query();},250);};$('mode').onchange=()=>{cursor=0;void query();};
  $('prev').onclick=()=>{cursor=previousCursors.pop()??0;void query();};$('next').onclick=()=>{if(next!==null){previousCursors.push(cursor);cursor=next;void query();}};
  $('detail-search').oninput=renderDetail;$('close-detail').onclick=()=>{$('detail').hidden=true;};
  $('refresh').onclick=async()=>{notice('');await loadIndex();await query();};
  $('control').onclick=async()=>{const button=$('control');button.disabled=true;try{await write('simulation.model_cache.control',{batch_id:selected.batch_id,action:button.dataset.action,expected_version:selected.row_version},{expected_resource_version:String(selected.row_version)});await loadIndex();await query();}catch(error){notice(error);}finally{button.disabled=false;}};

  $('login').onclick=async()=>{
    try{await requireRuntime();const state=await api().teamcenterGetSession();if(window.AI00TeamcenterSession.isReady(state)){notice(`TC 已登录：${state.masked_username}`);return;}$('login-dialog').showModal();}catch(error){notice(error);}
  };
  const login=$('login-form');
  function closeLogin(){login.elements.password.value='';$('login-dialog').close();}
  $('cancel-login').onclick=closeLogin;$('login-dialog').addEventListener('cancel',()=>{login.elements.password.value='';});
  login.onsubmit=async event=>{event.preventDefault();const button=login.querySelector('[type=submit]');button.disabled=true;try{const state=await api().teamcenterLogin({endpoint_id:'tc-production',username:login.elements.username.value.trim(),password:login.elements.password.value,remember:false});if(!window.AI00TeamcenterSession.isReady(state))throw Error('TC 会话尚未就绪');notice(`TC 已登录：${state.masked_username}`);window.AI00TeamcenterOnlineSource.clearRevisionRules();closeLogin();}catch(error){$('login-error').textContent=error.message;}finally{login.elements.password.value='';button.disabled=false;}};
  const form=$('create-form');
  // 借用 BOP 的阶段选项；缓存阶段独立选择，不与 BOP 状态联动。
  const dataStages=['Pre-TG0','TG0','TG1','PreTG2','TG2','EP1','EP2','PPV','PP','P','SOP'];
  form.elements.phase.replaceChildren(option('','请选择数据阶段'),...dataStages.map(stage=>option(stage,stage)));
  function updateSubmit(){ $('submit-create').disabled=!source||!form.elements.project.value||!form.elements.phase.value; }
  function invalidateSource(){++sourceSequence;source=null;$('tc-results').replaceChildren();updateSubmit();$('source-label').textContent='条件已变化，请重新查找';}
  function selectProject(){form.elements.projectNumber.value=form.elements.project.selectedOptions[0]?.dataset.projectNumber||'';invalidateSource();}
  let dialogSequence=0,loadingSource=false,loadDialogRules=()=>{};
  form.elements.rule.addEventListener('pointerdown',()=>void loadDialogRules());
  $('create').onclick=async()=>{
    const sequence=++dialogSequence;++sourceSequence;source=null;$('tc-results').replaceChildren();$('source-label').textContent='尚未选择数模';$('submit-create').disabled=true;$('create-error').textContent='';
    loadingSource=true;$('tc-search').disabled=true;
    form.elements.project.disabled=true;
    form.elements.project.replaceChildren(option('','正在加载项目…'));form.elements.projectNumber.value='';form.elements.phase.value='';
    form.elements.date.value=new Date(Date.now()-new Date().getTimezoneOffset()*60000).toISOString().slice(0,16);
    const ruleSelect=form.elements.rule;
    const applyRules=rules=>{const selected=ruleSelect.value;ruleSelect.replaceChildren(...rules.map(rule=>option(rule,rule)));ruleSelect.value=rules.includes(selected)?selected:(rules.includes('Latest Working')?'Latest Working':rules[0]);};
    applyRules(window.AI00TeamcenterOnlineSource.cachedRevisionRules()||['Latest Working']);
    $('rule-status').textContent='';
    let rulesStarted=false;
    const updateRules=rules=>{const previous=ruleSelect.value;applyRules(rules);$('rule-status').textContent='';if(ruleSelect.value!==previous)invalidateSource();};
    const loadRules=async()=>{
      const cached=window.AI00TeamcenterOnlineSource.cachedRevisionRules();
      if(cached){updateRules(cached);return;}
      if(rulesStarted)return;
      rulesStarted=true;$('rule-status').textContent='正在从 TC 读取其他修订规则，可先使用当前规则';
      try{
        const rules=await window.AI00TeamcenterOnlineSource.revisionRules(requestConnector);
        if(sequence!==dialogSequence)return;
        updateRules(rules);
      }catch(error){if(sequence===dialogSequence){rulesStarted=false;$('rule-status').textContent=`修订规则读取失败：${error.message}，再次展开可重试`;}}
    };
    loadDialogRules=loadRules;
    ruleSelect.onkeydown=event=>{if(['ArrowDown','Enter',' '].includes(event.key))void loadRules();};
    $('create-dialog').showModal();
    try{
      const projects=await invoke('project.project.read.atomic.projects_search',{arguments:{}});
      if(sequence!==dialogSequence)return;
      const items=Array.isArray(projects)?projects:projects.data||projects.items||[];
      form.elements.project.replaceChildren(...items.map(project=>{const item=option(String(project.gid||project.project_gid),project.project_name||project.name||project.project_code);item.dataset.projectNumber=project.project_code||'';return item;}));
      if(!items.length)form.elements.project.append(option('','暂无可用项目'));
      selectProject();
    }catch(error){if(sequence===dialogSequence)$('create-error').textContent=error.message;}
    finally{if(sequence===dialogSequence){loadingSource=false;form.elements.project.disabled=false;$('tc-search').disabled=busy||!form.elements.project.value;}}
  };
  $('cancel-create').onclick=()=>{++dialogSequence;++sourceSequence;$('create-dialog').close();};
  $('create-dialog').addEventListener('cancel',()=>{++dialogSequence;++sourceSequence;});
  let sourceSequence=0;
  $('tc-search').onclick=async()=>{
    if(busy||loadingSource)return;busy=true;const button=$('tc-search');button.disabled=true;source=null;$('submit-create').disabled=true;
    const sequence=++sourceSequence;
    try{
      if(!form.elements.projectNumber.value)throw Error('项目缺少项目号，请先完善项目资料');
      const input=window.AI00TeamcenterSession.projectSearchInput(form.elements.projectNumber.value,form.elements.rule.value,new Date(form.elements.date.value).toISOString());
      const found=await window.AI00TeamcenterOnlineSource.search(requestConnector,input);
      const items=found.filter(item=>item.item_id.toLocaleLowerCase()===input.query.toLocaleLowerCase()&&item.revision_id===input.revision_id);
      if(sequence!==sourceSequence)return;
      $('tc-results').replaceChildren();
      for(const item of items){const pick=document.createElement('button');pick.type='button';pick.textContent=item.display_name;pick.onclick=()=>{source=item;$('source-label').textContent=item.display_name;updateSubmit();};$('tc-results').append(pick);}
      if(!items.length)$('source-label').textContent='没有找到符合条件的数模';
    }catch(error){if(sequence===sourceSequence)$('create-error').textContent=error.message;}finally{busy=false;button.disabled=loadingSource;}
  };
  // Editing selector inputs invalidates the selection rather than caching a stale search result.
  form.elements.project.addEventListener('change',selectProject);
  form.elements.phase.addEventListener('change',updateSubmit);
  for(const name of ['rule','date'])form.elements[name].addEventListener('input',invalidateSource);
  form.onsubmit=async event=>{event.preventDefault();if(!source||!form.elements.project.value||!form.elements.phase.value)return;const button=$('submit-create');button.disabled=true;
    try{
      const batch=await write('simulation.model_cache.create',{project_gid:form.elements.project.value,project_name:form.elements.project.selectedOptions[0].textContent,phase:form.elements.phase.value,source_selector:source.source_selector,trigger_kind:'manual'});
      $('create-dialog').close();await loadIndex();await selectBatch(batch);
    }catch(error){$('create-error').textContent=error.message;}finally{button.disabled=false;}
  };
  await loadIndex();
  // Progress reads do not drive caching. Serialize them and reload rows only after a persisted change.
  let poll,closed=false;
  const schedule=()=>{if(!closed)poll=setTimeout(refreshProgress,batches.some(batch=>(['queued','running','waiting_connector'].includes(batch.status)||batch.preparation_status==='queued'))?10000:30000);};
  async function refreshProgress(){
    try{
      if(closed||document.hidden||listBusy||queryBusy)return;
      const batchId=selected?.batch_id;
      await loadIndex();
      if(!closed&&!queryBusy&&selected?.batch_id===batchId&&selected&&(renderedBatchId!==batchId||selected.row_version!==renderedVersion))await query();
    }finally{schedule();}
  }
  schedule();
  window.addEventListener('pagehide',()=>{closed=true;clearTimeout(poll);clearTimeout(timer);grid?.destroy();++querySequence;});
})();
