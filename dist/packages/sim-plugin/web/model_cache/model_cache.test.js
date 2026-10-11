const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {JSDOM}=require('jsdom');
const root=path.resolve(__dirname,'../../../..');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
const batch=id=>({batch_id:id,project_gid:'1',project_name:'项目',phase:'阶段',display_name:id,
  source_selector:{revision_rule:'Latest',configuration_date:'2026-09-28T00:00:00Z'},
  status:'completed',created_at:'2026-09-28T00:00:00Z',completed_at:'2026-09-28T00:00:00Z',node_count:1,row_version:1});
function harness(invoke,setup=()=>{}){
  const dom=new JSDOM(fs.readFileSync(path.join(__dirname,'index.html'),'utf8'),{runScripts:'outside-only',url:'http://127.0.0.1:5173'});
  const win=dom.window;
  win.ResizeObserver=class{observe(){}disconnect(){}};
  win.HTMLDialogElement.prototype.showModal=function(){this.open=true;};
  win.HTMLDialogElement.prototype.close=function(){this.open=false;};
  win.AI00Business={invoke};
  win.crypto.randomUUID=require('node:crypto').randomUUID;
  win.electronAPI={getConnectorState:async()=>({status:'ready',health:'healthy'})};
  win.eval(fs.readFileSync(path.join(root,'web/components/grid_editor.js'),'utf8')+'\nwindow.GridEditor=GridEditor;');
  win.eval(fs.readFileSync(path.join(__dirname,'cache_model.js'),'utf8'));
  win.eval(fs.readFileSync(path.join(root,'packages/sim-plugin/web/cad_sim/teamcenter_session.js'),'utf8'));
  win.AI00TeamcenterOnlineSource={cachedRevisionRules:()=>['Latest'],revisionRules:async()=>['Latest'],search:async()=>[]};
  setup(win);
  win.eval(fs.readFileSync(path.join(__dirname,'model_cache.js'),'utf8'));
  return dom;
}

test('progress refresh backs off and never overlaps slow reads or re-queries unchanged data',async()=>{
  const scheduled=[],calls=[];let pending=null,version=1;
  const dom=harness(async(id)=>{
    calls.push(id);
    if(id.endsWith('.list')){
      if(pending)await pending.promise;
      return {batches:[{...batch('A'),status:'running',row_version:version}],can_trigger:true};
    }
    return {...result('A'),batch:{...batch('A'),status:'running',row_version:version}};
  },win=>{
    Object.defineProperty(win.document,'hidden',{value:false,configurable:true});
    win.setTimeout=(callback,delay)=>{scheduled.push({callback,delay});return scheduled.length;};
    win.clearTimeout=()=>{};
    win.setInterval=(callback,delay)=>{scheduled.push({callback,delay});return scheduled.length;};
    win.clearInterval=()=>{};
  });
  try{
    await tick();const doc=dom.window.document;
    assert.equal(scheduled[0].delay,10000,'active batches need one progress refresh every ten seconds');
    doc.querySelector('.batch').click();await tick();
    const queryCount=()=>calls.filter(id=>id.endsWith('.query')).length;
    pending=deferred();let count=scheduled.length;
    const polling=scheduled.at(-1).callback();await tick();
    assert.equal(scheduled.length,count,'slow reads do not schedule overlapping progress refreshes');
    pending.resolve();pending=null;await polling;
    assert.equal(queryCount(),1,'unchanged batches do not reload rows');
    assert.equal(scheduled.length,count+1);
    version++;await scheduled.at(-1).callback();
    assert.equal(queryCount(),2,'new persisted data refreshes rows once');
    Object.defineProperty(doc,'hidden',{value:true,configurable:true});
    const callCount=calls.length;await scheduled.at(-1).callback();
    assert.equal(calls.length,callCount,'hidden pages do not poll');
  }finally{dom.window.close();}
});
test('a failed user query after progress updates still retries rows on the next poll',async()=>{
  let refresh,version=1,indexWait=null,queryWait=null,queries=0;
  const dom=harness(async(id)=>{
    if(id.endsWith('.list')){if(indexWait)await indexWait.promise;return {batches:[{...batch('A'),status:'running',row_version:version}],can_trigger:true};}
    ++queries;if(queryWait)await queryWait.promise;
    return {...result('A'),batch:{...batch('A'),status:'running',row_version:version}};
  },win=>{
    Object.defineProperty(win.document,'hidden',{value:false});
    win.setTimeout=callback=>{refresh=callback;return 1;};win.clearTimeout=()=>{};
  });
  try{
    await tick();const doc=dom.window.document;doc.querySelector('.batch').click();await tick();
    indexWait=deferred();const polling=refresh();await tick();
    let failQuery;queryWait={promise:new Promise((_,reject)=>{failQuery=reject;})};
    doc.getElementById('mode').dispatchEvent(new dom.window.Event('change'));await tick();
    version=2;indexWait.resolve();indexWait=null;await polling;
    failQuery(Error('temporary query failure'));queryWait=null;await tick();
    assert.equal(queries,2);await refresh();assert.equal(queries,3,'the last successfully rendered version remains stale until rows load');
    await refresh();assert.equal(queries,3,'successful retry removes the pending refresh');
  }finally{dom.window.close();}
});
function result(id){return {batch:batch(id),rows:[{node_key:'node',data_json:JSON.stringify({text:'<b>'+id+'</b>',zero:0,flag:false,empty:'',nil:null,long:'x'.repeat(10000)})}],fields:['/text','/zero','/flag','/empty','/nil','/long'],total:1,next_cursor:null};}
test('matrix columns and full four-row values are visible without changing original TC JSON',async()=>{
  const matrix=Array.from({length:16},(_,i)=>i+1);
  const raw={properties_result:{raw_fields:Object.entries({bl_occ_xform:matrix,bl_occ_xform_matrix:matrix.map(n=>n+20),bl_abs_xform_matrix:matrix.map(n=>n+40),bl_bounding_boxes:[1,2,3,4,5,6]}).map(([field,value])=>({field,read_state:'value',value_json:JSON.stringify(value)}))}};
  const dom=harness(async id=>id.endsWith('.list')?{batches:[batch('A')],can_trigger:true}:{...result('A'),rows:[{node_key:'node',data_json:JSON.stringify(raw)}],fields:[]});
  try{
    await tick();const doc=dom.window.document;doc.querySelector('.batch').click();await tick();
    for(const label of ['默认变换矩阵','绝对变换矩阵','相对变换矩阵','限定框'])assert.match(doc.getElementById('grid').textContent,new RegExp(label));
    doc.querySelector('.ge-td-num-open').click();
    const terms=[...doc.querySelectorAll('#detail-values dt')];
    const term=terms.find(t=>t.textContent==='默认变换矩阵');assert(term);
    assert.equal(term.nextElementSibling.textContent,'1  2  3  4\n5  6  7  8\n9  10  11  12\n13  14  15  16');
    assert.deepEqual(JSON.parse(doc.getElementById('detail-raw').textContent),raw);
  }finally{dom.window.close();}
});
test('valid PLMXML matrices remain visible when fallback properties are unavailable',async()=>{
  const matrix=Array.from({length:16},(_,i)=>i%5===0?1:0);
  const raw={properties_result:{raw_fields:['bl_plmxml_occ_xform','bl_plmxml_abs_xform','bl_occ_xform_matrix','bl_abs_xform_matrix'].map(field=>({field,read_state:field.includes('plmxml')?'value':'unavailable',value_json:JSON.stringify(field.includes('plmxml')?matrix:null)}))}};
  const dom=harness(async id=>id.endsWith('.list')?{batches:[batch('A')],can_trigger:true}:{...result('A'),rows:[{node_key:'node',data_json:JSON.stringify(raw)}],fields:[]});
  try{
    await tick();const doc=dom.window.document;doc.querySelector('.batch').click();await tick();
    assert(!doc.getElementById('grid').textContent.includes('TC 字段不可读'),'readable matrix projection takes priority over a denied fallback');
  }finally{dom.window.close();}
});
test('batch switching clears old rows immediately and discards late responses; full values open through reused grid',async()=>{
  const pending=[];
  const dom=harness(async(id,envelope)=>{
    if(id.endsWith('.list'))return {batches:[batch('A'),batch('B')],can_trigger:true};
    if(id.endsWith('.query')){const d=deferred();pending.push({batch:envelope.payload.batch_id,...d});return d.promise;}
    throw Error(id);
  });
  try{
    await tick();const doc=dom.window.document;
    doc.querySelectorAll('.batch')[0].click();await tick();pending[0].resolve(result('A'));await tick();
    assert.match(doc.getElementById('grid').textContent,/<b>A<\/b>/);
    assert.equal(doc.querySelector('#grid b'),null,'TC values must remain escaped text');
    doc.querySelector('.ge-td-num-open').click();
    assert.equal(doc.getElementById('detail').hidden,false);
    assert.match(doc.getElementById('detail-values').textContent,/false/);
    assert(doc.getElementById('detail-values').textContent.includes('x'.repeat(10000)));
    doc.querySelectorAll('.batch')[1].click();
    assert(!doc.getElementById('grid').textContent.includes('<b>A</b>'));
    await tick();
    doc.querySelectorAll('.batch')[0].click();await tick();
    pending[2].resolve(result('A'));await tick();pending[1].resolve(result('B'));await tick();
    assert.equal(doc.getElementById('batch-title').textContent,'A');
    assert(!doc.getElementById('grid').textContent.includes('<b>B</b>'));
  }finally{dom.window.close();}
});
test('changing TC selector or cancelling creation discards in-flight source results',async()=>{
  const dom=harness(async(id)=>id.endsWith('.list')?{batches:[],can_trigger:true}:{data:[{gid:'1',name:'项目',project_code:'W10'}]});
  try{
    await tick();const win=dom.window,doc=win.document;const source=deferred();
    win.AI00TeamcenterOnlineSource.search=()=>source.promise;
    doc.getElementById('create').click();await tick();
    doc.getElementById('tc-search').click();await tick();
    const project=doc.querySelector('[name=project]');project.dispatchEvent(new win.Event('change'));
    source.resolve([{item_id:'W10-ENG00001',revision_id:'00',display_name:'Stale',source_selector:{}}]);await tick();
    assert.equal(doc.getElementById('tc-results').childElementCount,0);
    assert.equal(doc.getElementById('submit-create').disabled,true);
  }finally{dom.window.close();}
});

test('creation uses BOP stages, project search and a server allocated version',async()=>{
  const calls=[];
  const dom=harness(async(id,envelope)=>{
    calls.push({id,...envelope});
    if(id.endsWith('.list'))return {batches:[],can_trigger:true};
    if(id.endsWith('.create'))return batch('v1');
    if(id.endsWith('.query'))return result('v1');
    return {data:[{gid:'1',name:'W10-2026-A',project_code:'W10'}]};
  });
  try{
    await tick();const win=dom.window,doc=win.document;
    let searched;
    const selector={endpoint_id:'tc-production',root_item_id:'W10-ENG00001',root_revision_id:'00'};
    win.AI00TeamcenterOnlineSource.search=async(_transport,input)=>{searched=input;return [
      {item_id:'W10-ENG00001',revision_id:'00',display_name:'项目数模',source_selector:selector},
      {item_id:'W10-ENG00002',revision_id:'00',display_name:'不匹配',source_selector:{}},
      {item_id:'W10-ENG00001',revision_id:'01',display_name:'其他版本',source_selector:{}}
    ];};
    doc.getElementById('create').click();await tick();
    const form=doc.getElementById('create-form');
    assert.deepEqual([...form.elements.phase.options].slice(1).map(item=>item.value),['Pre-TG0','TG0','TG1','PreTG2','TG2','EP1','EP2','PPV','PP','P','SOP']);
    assert.equal(form.elements.displayName,undefined);
    assert.equal(form.elements.query,undefined);
    assert.equal(form.elements.revision,undefined);
    assert.equal(form.elements.projectNumber.value,'W10');
    assert.equal(form.elements.projectNumber.readOnly,true);
    doc.getElementById('tc-search').click();await tick();
    assert.equal(searched.query,'W10-ENG00001');assert.equal(searched.revision_id,'00');
    assert.equal(doc.getElementById('tc-results').childElementCount,1);
    doc.querySelector('#tc-results button').click();
    assert.equal(doc.getElementById('submit-create').disabled,true,'a data stage is required');
    form.elements.phase.value='EP1';form.elements.phase.dispatchEvent(new win.Event('change'));
    assert.equal(doc.getElementById('submit-create').disabled,false);
    form.dispatchEvent(new win.Event('submit',{cancelable:true}));await tick();await tick();
    const created=calls.find(call=>call.id.endsWith('.create')).payload;
    assert.equal(created.project_gid,'1');assert.equal(created.phase,'EP1');
    assert.equal(Object.hasOwn(created,'display_name'),false);
    assert.deepEqual(created.source_selector,selector);
    const bop=fs.readFileSync(path.join(root,'packages/craft-plugin/web/lineage_view/lifecycle_panel.js'),'utf8');
    const declared=JSON.parse(bop.match(/const _LC_DATA_STAGES = (\[[^;]+\]);/)[1].replace(/'/g,'"'));
    assert.deepEqual([...form.elements.phase.options].slice(1).map(item=>item.value),declared);
  }finally{dom.window.close();}
});

test('search during dialog initialization cannot discard the pending project list',async()=>{
  const projects=deferred();let searches=0;
  const dom=harness(async(id)=>id.endsWith('.list')?{batches:[],can_trigger:true}:projects.promise);
  try{
    await tick();const doc=dom.window.document;
    dom.window.AI00TeamcenterOnlineSource.search=async()=>{searches++;return [];};
    doc.getElementById('create').click();await tick();
    assert.equal(doc.getElementById('tc-search').disabled,true);
    doc.getElementById('tc-search').click();
    projects.resolve({data:[{gid:'1',name:'W10',project_code:'W10'}]});await tick();
    assert.equal(doc.querySelector('[name=project]').options.length,1);
    assert.equal(doc.querySelector('[name=projectNumber]').value,'W10');
    assert.equal(doc.getElementById('tc-search').disabled,false);
    assert.equal(searches,0);
  }finally{dom.window.close();}
});

test('projects become usable independently of a slow revision-rule read; rules are loaded on demand',async()=>{
  const projects=deferred(),rules=deferred();let reads=0;
  const dom=harness(async(id)=>id.endsWith('.list')?{batches:[],can_trigger:true}:projects.promise);
  try{
    await tick();const win=dom.window,doc=win.document,form=doc.getElementById('create-form');
    win.AI00TeamcenterOnlineSource.cachedRevisionRules=()=>null;
    win.AI00TeamcenterOnlineSource.revisionRules=()=>{reads++;return rules.promise;};
    doc.getElementById('create').click();await tick();
    assert.equal(reads,0,'opening must not queue a TC read');
    assert.equal(form.elements.rule.value,'Latest Working');
    assert.equal(form.elements.rule.disabled,false);
    assert.equal(form.elements.date.disabled,false);
    form.elements.rule.dispatchEvent(new win.Event('pointerdown'));await tick();
    assert.equal(reads,1);
    projects.resolve({data:[{gid:'1',name:'W10',project_code:'W10'}]});await tick();
    assert.equal(form.elements.project.disabled,false);
    assert.equal(form.elements.projectNumber.value,'W10');
    assert.equal(doc.getElementById('tc-search').disabled,false,'slow TC rules must not block project search');
    assert.match(doc.getElementById('rule-status').textContent,/正在/);
    rules.resolve(['Released','Latest Working']);await tick();
    assert.equal(form.elements.rule.value,'Latest Working','retain the rule already chosen');
    assert.equal(doc.getElementById('rule-status').textContent,'');
  }finally{dom.window.close();}
});

test('a revision-rule failure retains the default and project choices and can be retried',async()=>{
  const dom=harness(async(id)=>id.endsWith('.list')?{batches:[],can_trigger:true}:{data:[{gid:'1',name:'W10',project_code:'W10'}]});
  try{
    await tick();const win=dom.window,doc=win.document,form=doc.getElementById('create-form');let reads=0;
    win.AI00TeamcenterOnlineSource.cachedRevisionRules=()=>null;
    win.AI00TeamcenterOnlineSource.revisionRules=async()=>{if(++reads===1)throw Error('TC 暂不可用');return ['Latest Working','Released'];};
    doc.getElementById('create').click();await tick();
    form.elements.rule.dispatchEvent(new win.Event('keydown',{bubbles:true}));
    const down=new win.KeyboardEvent('keydown',{key:'ArrowDown'});form.elements.rule.dispatchEvent(down);await tick();
    assert.equal(form.elements.project.options.length,1);
    assert.equal(form.elements.rule.value,'Latest Working');
    assert.equal(doc.getElementById('tc-search').disabled,false);
    assert.match(doc.getElementById('rule-status').textContent,/TC 暂不可用/);
    form.elements.rule.dispatchEvent(down);await tick();
    assert.equal(reads,2);assert.equal(form.elements.rule.options.length,2);
    assert.equal(doc.getElementById('rule-status').textContent,'');
  }finally{dom.window.close();}
});

test('reopening while rules load still applies the cache filled by the older dialog',async()=>{
  const dom=harness(async(id)=>id.endsWith('.list')?{batches:[],can_trigger:true}:{data:[{gid:'1',name:'W10',project_code:'W10'}]});
  try{
    await tick();const win=dom.window,doc=win.document,form=doc.getElementById('create-form');
    const pending=deferred();let cached=null,reads=0;
    win.AI00TeamcenterOnlineSource.cachedRevisionRules=()=>cached;
    win.AI00TeamcenterOnlineSource.revisionRules=async()=>{reads++;cached=await pending.promise;return cached;};
    doc.getElementById('create').click();await tick();
    form.elements.rule.dispatchEvent(new win.Event('pointerdown'));await tick();
    doc.getElementById('cancel-create').click();doc.getElementById('create').click();await tick();
    pending.resolve(['Latest Working','Released']);await tick();
    assert.equal(form.elements.rule.options.length,1,'the cancelled dialog must not update the new one');
    form.elements.rule.dispatchEvent(new win.Event('pointerdown'));await tick();
    assert.equal(form.elements.rule.options.length,2,'the new dialog must apply rules cached by the older read');
    assert.equal(form.elements.rule.value,'Latest Working');assert.equal(reads,1);
  }finally{dom.window.close();}
});

test('TC table defaults to leaf values; containers, original JSON and server filter paths remain available',async()=>{
  const raw={structure:{name:'模型',depth:2,has_children:false},properties_result:{properties:{},raw_fields:[{object_kind:'ItemRevision',field:'object_name',value_json:'"<b>TC 名称</b>"'}]},empty:[]};
  let fields=Object.keys(require('./cache_model.js').flatten(raw));const calls=[];
  const dom=harness(async(id,envelope)=>{
    calls.push({id,payload:envelope.payload});
    return id.endsWith('.list')?{batches:[batch('A')],can_trigger:true}:{batch:batch('A'),rows:[{node_key:'node',data_json:JSON.stringify(raw)}],fields,total:1,next_cursor:null};
  });
  try{
    await tick();const doc=dom.window.document;doc.querySelector('.batch').click();await tick();
    const grid=doc.getElementById('grid');
    assert(!grid.textContent.includes('"raw_fields"'),'parent JSON must not duplicate every value');
    assert.match(grid.textContent,/结构 › 名称/);assert.match(grid.textContent,/<b>TC 名称<\/b>/);
    assert.equal(grid.querySelector('.cache-node-name')?.style.paddingLeft,'28px','tree name visibly preserves depth');
    assert.match(grid.querySelector('.cache-node-name').title,/第 3 层/);
    assert.equal(grid.querySelector('b'),null);
    const parent=[...doc.querySelectorAll('#column-options label')].find(label=>label.textContent==='结构');
    assert(parent);assert.equal(parent.querySelector('input').checked,false);
    parent.querySelector('input').click();assert.match(grid.textContent,/对象 · 3 个字段/);
    const properties=[...doc.querySelectorAll('#column-options label')].find(label=>label.textContent==='属性信息 › 模型属性').querySelector('input');
    properties.click();properties.click();assert.equal(properties.checked,true);
    raw.properties_result.properties.name='新增属性';fields=Object.keys(require('./cache_model.js').flatten(raw));
    doc.getElementById('refresh').click();await tick();await tick();
    assert.equal([...doc.querySelectorAll('#column-options label')].find(label=>label.textContent==='结构').querySelector('input').checked,true,'refresh retains explicit container choices');
    assert.equal([...doc.querySelectorAll('#column-options label')].find(label=>label.textContent==='属性信息 › 模型属性').querySelector('input').checked,true,'catalog growth retains a leaf explicitly selected before children arrived');
    doc.querySelector('.ge-td-num-open').click();
    assert(!doc.getElementById('detail-values').textContent.includes('"raw_fields"'));
    assert.equal(doc.getElementById('detail-raw').textContent,JSON.stringify(raw,null,2));
    doc.getElementById('add-filter').click();
    assert([...doc.querySelectorAll('[aria-label="筛选字段"] option')].some(option=>option.value==='/structure'));
    const field=doc.querySelector('[aria-label="筛选字段"]'),op=doc.querySelector('[aria-label="筛选操作"]'),input=doc.querySelector('[aria-label="筛选值"]');
    field.value='/properties_result/raw_fields/0/value_json';op.value='eq';input.value='<b>TC 名称</b>';
    input.dispatchEvent(new dom.window.Event('change'));await tick();
    const filter=calls.filter(call=>call.id.endsWith('.query')).at(-1).payload.filters[0];
    assert.equal(JSON.parse(filter.value_json),raw.properties_result.raw_fields[0].value_json,'typing the displayed TC value must generate its stored equality value');
  }finally{dom.window.close();}
});

test('TC raw equality keeps literal quotes, backslashes, null text and numeric text distinct from null',async()=>{
  const calls=[],raw={structure:{name:'模型'},properties_result:{raw_fields:[{value_json:'"value"'}]}},fields=Object.keys(require('./cache_model.js').flatten(raw));
  const dom=harness(async(id,envelope)=>{
    if(id.endsWith('.list'))return {batches:[batch('A')],can_trigger:true};
    calls.push(JSON.parse(JSON.stringify(envelope.payload)));
    return {batch:batch('A'),rows:[{node_key:'node',data_json:JSON.stringify(raw)}],fields,total:1,next_cursor:null};
  });
  try{
    await tick();const win=dom.window,doc=win.document;doc.querySelector('.batch').click();await tick();doc.getElementById('add-filter').click();
    const field=doc.querySelector('[aria-label="筛选字段"]');field.value='/properties_result/raw_fields/0/value_json';field.dispatchEvent(new win.Event('change'));await tick();
    const op=doc.querySelector('[aria-label="筛选操作"]');op.value='eq';op.dispatchEvent(new win.Event('change'));await tick();
    for(const text of ['"Quoted name"','path\\file','null','0','false','']){
      const input=doc.querySelector('[aria-label="筛选值"]');input.value=text;input.dispatchEvent(new win.Event('change'));await tick();
      assert.equal(JSON.parse(calls.at(-1).filters[0].value_json),JSON.stringify(text));
    }
    const kind=doc.querySelector('[aria-label="筛选值类型"]');assert(kind);kind.value='null';kind.dispatchEvent(new win.Event('change'));await tick();
    assert.equal(JSON.parse(calls.at(-1).filters[0].value_json),'null');
    assert.equal(doc.querySelector('[aria-label="筛选值"]').disabled,true);
  }finally{dom.window.close();}
});


test('structure-only rows clearly mark required Simulation attributes as pending',async()=>{
  const raw={structure:{name:'模型',depth:0}},fields=Object.keys(require('./cache_model.js').flatten(raw));
  const dom=harness(async id=>id.endsWith('.list')?{batches:[batch('A')],can_trigger:true}:{batch:batch('A'),rows:[{node_key:'node',data_json:JSON.stringify(raw)}],fields,total:1,next_cursor:null});
  try{
    await tick();const doc=dom.window.document;doc.querySelector('.batch').click();await tick();
    const grid=doc.getElementById('grid');
    for(const label of ['扭矩','扭矩重要度','零组件类型','所有者','所属组','catiaOccurrenceName','catiaFileName','VPPS','VPPS描述'])assert(grid.textContent.includes(label),label);
    assert.match(grid.textContent,/待采集属性/);
    const torque=[...doc.querySelectorAll('#column-options label')].find(label=>label.title==='/properties_result/properties/torque_raw');
    torque.querySelector('input').click();doc.getElementById('refresh').click();await tick();await tick();
    assert.equal([...doc.querySelectorAll('#column-options label')].find(label=>label.title==='/properties_result/properties/torque_raw').querySelector('input').checked,false,'pending column choices survive refresh');
    assert(![...doc.querySelectorAll('.ge-table th')].some(th=>th.textContent==='属性信息 › 模型属性 › 扭矩'));

    doc.getElementById('add-filter').click();
    assert(![...doc.querySelectorAll('[aria-label="筛选字段"] option')].some(o=>o.value==='/properties_result/properties/torque_raw'),'pending display does not invent a stored TC field');
  }finally{dom.window.close();}
});


test('JT reference arrays expose every value in detail and support explicit JSON equality',async()=>{
  const refs=[{dataset_uid:'dataset',file_uid:'file',file_name:'模型.jt',relation_type:'IMAN_Rendering'}],calls=[];
  const raw={structure:{name:'模型'},properties_result:{raw_fields:[{field:'IMAN_Rendering',read_state:'value',value_json:JSON.stringify(refs)}]}},fields=Object.keys(require('./cache_model.js').flatten(raw));
  const dom=harness(async(id,envelope)=>{
    if(id.endsWith('.list'))return {batches:[batch('A')],can_trigger:true};
    calls.push(JSON.parse(JSON.stringify(envelope.payload)));
    return {batch:batch('A'),rows:[{node_key:'node',data_json:JSON.stringify(raw)}],fields,total:1,next_cursor:null};
  });
  try{
    await tick();const win=dom.window,doc=win.document;doc.querySelector('.batch').click();await tick();doc.querySelector('.ge-td-num-open').click();
    for(const label of ['数模数据集 UID','数模文件 UID','数模文件名','关联关系'])assert(doc.getElementById('detail-values').textContent.includes(label),label);
    assert(!doc.getElementById('detail-values').textContent.includes('"dataset_uid"'),'values are rendered separately, not a JSON blob');
    doc.getElementById('add-filter').click();const field=doc.querySelector('[aria-label="筛选字段"]');field.value='/properties_result/raw_fields/0/value_json';field.dispatchEvent(new win.Event('change'));await tick();
    const op=doc.querySelector('[aria-label="筛选操作"]');op.value='eq';op.dispatchEvent(new win.Event('change'));await tick();
    const kind=doc.querySelector('[aria-label="筛选值类型"]');kind.value='json';kind.dispatchEvent(new win.Event('change'));await tick();
    const input=doc.querySelector('[aria-label="筛选值"]');input.value=JSON.stringify(refs);input.dispatchEvent(new win.Event('change'));await tick();
    assert.equal(JSON.parse(calls.at(-1).filters[0].value_json),JSON.stringify(refs));
    const count=calls.length;input.value='[invalid';input.dispatchEvent(new win.Event('change'));await tick();
    assert.equal(calls.length,count,'invalid JSON does not query with a stale or invented value');assert.match(doc.getElementById('notice').textContent,/JSON/);
  }finally{dom.window.close();}
});


test('instance metadata columns show exact TC values while original records remain inspectable',async()=>{
  const raw={structure:{name:'模型',occurrence_path:[{occurrence_uid:'occ-2',item_revision_uid:'rev'}]},properties_result:{properties:{},raw_fields:Object.entries({catiaOccurrenceName:'ITEM.2',catiaFileName:'ITEM.CATPart',C9_bl_vpps:'VP-01',C9_bl_fnaname:'前悬架'}).map(([field,value])=>({field,read_state:'value',value_json:JSON.stringify(value)}))}},fields=Object.keys(require('./cache_model.js').flatten(raw));
  const dom=harness(async id=>id.endsWith('.list')?{batches:[batch('A')],can_trigger:true}:{batch:batch('A'),rows:[{node_key:'node',data_json:JSON.stringify(raw)}],fields,total:1,next_cursor:null});
  try{
    await tick();const doc=dom.window.document;doc.querySelector('.batch').click();await tick();
    const headers=[...doc.querySelectorAll('.ge-table th')].map(th=>th.textContent);
    assert(headers.some(label=>label.endsWith('catiaOccurrenceName（项目内唯一标识）')));assert(headers.some(label=>label.endsWith('VPPS描述')));
    assert.match(doc.getElementById('grid').textContent,/ITEM\.2/);assert.match(doc.getElementById('grid').textContent,/前悬架/);
    doc.querySelector('.ge-td-num-open').click();assert.equal(doc.getElementById('detail-raw').textContent,JSON.stringify(raw,null,2));
  }finally{dom.window.close();}
});
