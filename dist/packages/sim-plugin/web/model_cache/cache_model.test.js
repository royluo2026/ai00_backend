const test = require('node:test');
const assert = require('node:assert/strict');
const model = require('./cache_model.js');

test('default, relative, absolute and bounding box properties stay distinct and readable',()=>{
  const defaultMatrix=Array.from({length:16},(_,i)=>i+1),relative=defaultMatrix.map(n=>n+20),absolute=defaultMatrix.map(n=>n+40);
  const raw_fields=Object.entries({bl_occ_xform:defaultMatrix.join(' '),bl_occ_xform_matrix:relative,bl_abs_xform_matrix:absolute,bl_bounding_boxes:[1,2,3,4,5,6]}).map(([field,value])=>({field,read_state:'value',value_json:JSON.stringify(value)}));
  const result=model.modelProperties({properties_result:{raw_fields}});
  assert.deepEqual(result.default_transform,defaultMatrix);assert.deepEqual(result.relative_transform,relative);assert.deepEqual(result.absolute_transform,absolute);assert.deepEqual(result.bbox,[1,2,3,4,5,6]);
  for(const [key,label]of Object.entries({default_transform:'默认变换矩阵',relative_transform:'相对变换矩阵',absolute_transform:'绝对变换矩阵',bbox:'限定框'}))assert.match(model.fieldLabel('/properties_result/properties/'+key),new RegExp(label));
  assert.equal(model.modelProperties({}).default_transform,null,'old caches never invent default matrices from relative matrices');
});

test('TC PLMXML default occurrence matrix takes precedence over the empty legacy alias',()=>{
  const matrix=Array.from({length:16},(_,i)=>i+1);
  const raw_fields=Object.entries({bl_occ_xform:'',bl_plmxml_def_occ_xform:matrix.join(' '),bl_plmxml_occ_xform:matrix.map(n=>n+40)}).map(([field,value])=>({field,read_state:'value',value_json:JSON.stringify(value)}));
  assert.deepEqual(model.modelProperties({properties_result:{raw_fields}}).default_transform,matrix);
  assert.equal(model.modelFieldSources.default_transform,'bl_plmxml_def_occ_xform');
});

test('groups projects and phases with newest batches first', () => {
  const groups=model.groupBatches([
    {batch_id:'old',project_gid:'1',project_name:'P',phase:'A',created_at:'2026-01-01'},
    {batch_id:'new',project_gid:'1',project_name:'P',phase:'A',created_at:'2026-09-28'},
    {batch_id:'other',project_gid:'2',project_name:'Q',phase:'B',created_at:'2026-09-28'},
  ]);
  assert.deepEqual(groups.find(group=>group.id==='1').phases[0].batches.map(x=>x.batch_id),['new','old']);
  assert.equal(groups.length,2);
});
test('all fields and values preserve types, containers, escaped keys and long strings', () => {
  const value={x:0,y:false,z:null,empty:'',nested:{'a/b':'x'.repeat(10000)},array:[1,false]};
  const fields=model.flatten(value);
  assert.equal(fields['/y'],false); assert.equal(fields['/z'],null);
  assert.equal(fields['/nested/a~1b'].length,10000);
  assert.deepEqual(fields['/array'],[1,false]);
  assert.equal(model.display(''),'""'); assert.equal(model.display(null),'null');
});
test('shared snapshot consumes completed exact project/selector only and every page',async()=>{
  const selector={a:1,b:2}; const calls=[];
  const invoke=async(id,payload)=>{
    calls.push([id,payload]);
    if(id.endsWith('.list'))return {batches:[{batch_id:'wrong',project_gid:'8',status:'completed',source_selector:selector},{batch_id:'ready',project_gid:'7',status:'completed',source_selector:{b:2,a:1}},{batch_id:'pending',project_gid:'7',status:'running',source_selector:selector}]};
    return {batch:{status:'completed'},rows:[{data_json:JSON.stringify({structure:{occurrence_id:String(payload.cursor),name:'raw'},properties_result:{properties:{item_id:'item',revision_id:'00'},raw_fields:[{field:'IMAN_Rendering',read_state:'value',value_json:'[]'}]}})}],next_cursor:payload.cursor===0?500:null};
  };
  const result=await model.readSnapshot(invoke,'7',selector,node=>node);
  assert.equal(result.nodes.length,2);assert.equal(result.nodes[0].item_id,'item');
  assert.equal(calls[1][1].batch_id,'ready');assert.equal(calls[2][1].cursor,500);
});

test('readable fields omit duplicate containers without losing empty values or escaped paths',()=>{
  const raw={structure:{name:'数模',path:[{uid:'TC'}]},empty:[],nil:null,'a/b':{},properties_result:{raw_fields:[{field:'object_name',value_json:'"长文本"'}]}};
  const flat=model.flatten(raw),keys=model.leafFields(Object.keys(flat));
  assert(!keys.includes('/structure'));assert(!keys.includes('/structure/path'));
  assert(keys.includes('/empty'));assert(keys.includes('/a~1b'));assert(keys.includes('/nil'));
  assert.equal(model.fieldLabel('/structure/name'),'结构 › 名称');
  assert.equal(model.fieldLabel('/a~1b'),'a/b');
  assert.equal(model.fieldDisplay('/properties_result/raw_fields/0/value_json',flat['/properties_result/raw_fields/0/value_json']),'长文本');
  assert.equal(model.fieldDisplay('/custom/value_json','not-json'),'not-json');
  assert.equal(model.cellDisplay({nested:[1,false]}),'对象 · 1 个字段（点击行查看）');
  assert.equal(model.cellDisplay([]),'空数组');
});


test('cloud snapshot restores Simulation JT references, identity, geometry and business properties',async()=>{
  const matrix=Array.from({length:16},(_,i)=>i%5===0?1:0),refs=[{dataset_uid:'dataset',file_uid:'file',file_name:'模型.jt',relation_type:'IMAN_Rendering'}];
  const raw_fields=Object.entries({IMAN_Rendering:refs,items_tag:'item',catiaOccurrenceName:'ITEM.2',catiaFileName:'ITEM.CATPart',C9_bl_vpps:'VP-01',C9_bl_fnaname:'前悬架',bl_formatted_parent_name:'父总成',catiaParentPartName:'ASSEMBLY',C9_bl_parentvpps:'50',C9_bl_parentvppsname:'底盘',bl_plmxml_occ_xform:matrix,bl_plmxml_abs_xform:matrix,bl_bounding_boxes:[0,0,0,1,2,3]}).map(([field,value])=>({field,read_state:'value',value_json:JSON.stringify(value)}));
  const properties={torque_raw:'12',torque_importance:'重要',component_type:'Part',owning_user:'owner',owning_group:'group'};
  const invoke=async id=>id.endsWith('.list')?{batches:[{batch_id:'A',project_gid:'1',status:'completed',source_selector:{}}],next_cursor:null}:{batch:{status:'completed'},rows:[{data_json:JSON.stringify({structure:{name:'模型'},properties_result:{properties,raw_fields}})}],next_cursor:null};
  require('../cad_sim/teamcenter_online_source.js');
  const snapshot=await model.readSnapshot(invoke,'1',{},globalThis.AI00TeamcenterOnlineSource.productNode),node=snapshot.nodes[0];
  assert.deepEqual(node.geometry_refs,refs);assert.equal(node.item_uid,'item');assert.deepEqual(node.transform,matrix);assert.deepEqual(node.absolute_transform,matrix);assert.deepEqual(node.bbox,[0,0,0,1,2,3]);
  assert.equal(node.catia_occurrence_name,'ITEM.2');assert.equal(node.catia_file_name,'ITEM.CATPart');assert.equal(node.vpps,'VP-01');assert.equal(node.vpps_desc,'前悬架');assert.equal(node.parent_name,'父总成');assert.equal(node.catia_parent_part_name,'ASSEMBLY');assert.equal(node.parent_vpps,'50');assert.equal(node.parent_vpps_name,'底盘');
  assert.equal(node.transform_unit,'m');assert.equal(node.transform_convention,'teamcenter_plmxml_4x4_row_major');assert.equal(node.bbox_unit,'m');
  for(const [key,value]of Object.entries(properties))assert.equal(node[key],value);
  assert.deepEqual(node.cloud_raw_fields,raw_fields,'original TC records remain unchanged');
});

test('spatial fallbacks match native numeric text parsing and unavailable values remain unknown',()=>{
  const field=(name,value,state='value')=>({field:name,read_state:state,value_json:JSON.stringify(value)});
  const matrix=Array.from({length:16},(_,i)=>i%5===0?1:0);
  const properties=model.modelProperties({properties_result:{raw_fields:[field('bl_plmxml_occ_xform',null,'unavailable'),field('bl_occ_xform_matrix',matrix.join(' ')),field('IMAN_Rendering',null,'unavailable')]}});
  assert.deepEqual(properties.transform,matrix);assert.equal(properties.geometry_refs,undefined);
  assert.deepEqual(model.modelProperties({properties_result:{raw_fields:[field('IMAN_Rendering',[])]}}).geometry_refs,[],'verified absence differs from unavailable');
  assert.equal(model.modelProperties({}).geometry_refs,undefined,'old caches do not claim verified empty JT references');
});


test('legacy snapshots without verified TC geometry references fall back to live Simulation reads',async()=>{
  const invoke=async id=>id.endsWith('.list')?{batches:[{batch_id:'A',project_gid:'1',status:'completed',source_selector:{}}],next_cursor:null}:{batch:{status:'completed'},rows:[{data_json:JSON.stringify({structure:{name:'legacy'},properties_result:{properties:{item_id:'ITEM'}}})}],next_cursor:null};
  assert.equal(await model.readSnapshot(invoke,'1',{},node=>node),null);
});


test('two occurrences of the same revision retain their distinct project CATIA identities',async()=>{
  const invoke=async id=>id.endsWith('.list')?{batches:[{batch_id:'A',project_gid:'1',status:'completed',source_selector:{}}],next_cursor:null}:{batch:{status:'completed'},rows:['left','right'].map(name=>({data_json:JSON.stringify({structure:{occurrence_id:name,item_revision_uid:'same-revision'},properties_result:{properties:{item_id:'same-item'},raw_fields:[{field:'IMAN_Rendering',read_state:'value',value_json:'[]'},{field:'catiaOccurrenceName',read_state:'value',value_json:JSON.stringify(name)}]}})})),next_cursor:null};
  const snapshot=await model.readSnapshot(invoke,'1',{},globalThis.AI00TeamcenterOnlineSource.productNode);
  assert.deepEqual(snapshot.nodes.map(node=>[node.node_key,node.catia_occurrence_name,node.item_revision_uid]),[['tc:left','left','same-revision'],['tc:right','right','same-revision']]);
});
