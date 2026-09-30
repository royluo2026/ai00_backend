const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const script=fs.readFileSync(path.resolve(__dirname,'../src/Ai00.Connector.Adapters.VisMockup/teamcenter_readonly_worker.js'),'utf8');
function fixture(count=10000){
  const calls={expand:0,properties:[],relations:0};
  const object=(uid,fields)=>({getUid:()=>uid,getTypeObject:()=>({getName:()=> 'Part'}),getPropertyObject:name=>{
    if(!(name in fields))throw Error('unavailable');const value=fields[name];
    return {getDisplayableValue:()=>value,getModelObjectValue:()=>value,getModelObjectArrayValue:()=>value,getDoubleArrayValue:()=>value};
  }});
  const revisions=Array.from({length:20},(_,i)=>object('r'+i,{object_name:'Part '+i,item_id:'P'+i,item_revision_id:'00',owning_user:'owner',owning_group:'group',c9_weight:'0',c9_unitweight:'kg',items_tag:object('i'+i,{})}));
  const line=(i)=>object('l'+i,{bl_occurrence_uid:'O'+i,bl_revision:revisions[i%20],bl_line_name:'Node '+i,bl_rev_item_revision_id:'00',bl_item_object_type:'Part',C9_bl_torque:'12',C9_bl_torqueimpor:'重要',catiaOccurrenceName:'P.'+i,catiaFileName:'P.CATPart',C9_bl_vpps:'VP',C9_bl_fnaname:'零件',bl_formatted_parent_name:'根',catiaParentPartName:'ROOT',C9_bl_parentvpps:'ROOT-VP',C9_bl_parentvppsname:'车型'});
  const lines=Array.from({length:count},(_,i)=>line(i));
  const context={Java:{to:x=>x,from:x=>x},ExpandPSAllLevelsInfo:function(){},ExpandPSAllLevelsPref:function(){},ExpandGRMRelationsPref2:function(){},RelationAndTypesFilter:function(){},
    structure:{expandPSAllLevels:info=>{calls.expand++;assert.equal(info.parentBomLines[0],lines[0]);return {output:[{parent:{bomLine:lines[0],objectOfBOMLine:revisions[0]},children:lines.slice(1).map((bomLine,i)=>({bomLine,objectOfBOMLine:revisions[(i+1)%20]}))}]};}},
    dm:{getProperties:(objects,names)=>{calls.properties.push({count:objects.length,names:[...names]});return {};},expandGRMRelationsForPrimary:objects=>{calls.relations++;return {output:objects.map(inputObject=>({inputObject,relationshipData:[]}))};}},
    observationTiming:()=>{},serviceErrors:data=>data?.errors||[],fail:code=>{throw Error(code)},
    display:(o,k)=>{try{return String(o.getPropertyObject(k).getDisplayableValue()??'')}catch{return ''}},
    modelObject:(o,k)=>{try{return o.getPropertyObject(k).getModelObjectValue()}catch{return null}},
    modelObjects:(o,k)=>{try{return o.getPropertyObject(k).getModelObjectArrayValue()}catch{return []}},
    doubleArray:(o,k,n)=>{try{const a=o.getPropertyObject(k).getDoubleArrayValue();return Array.isArray(a)&&a.length===n?a:null}catch{return null}}};
  vm.createContext(context);vm.runInContext(script.slice(script.indexOf('var structureNodes ='),script.indexOf('function fail(')),context);
  return {context,calls,lines,revisions};
}
test('10000 occurrences use one all-level expansion and bounded set property reads, preserving repeated instances',()=>{
  const {context:c,calls,lines,revisions}=fixture();
  const manifest=c.captureCacheStructure(lines[0],revisions[0]);
  assert.equal(manifest.node_count,10000);assert.equal(calls.expand,1);
  const pages=[];for(let cursor=0;cursor<10000;cursor+=200)pages.push(c.cacheStructurePage(cursor,200));
  assert.equal(pages.length,50);assert.equal(calls.expand,1);
  assert.equal(pages[0].nodes[0].child_count,9999);assert.equal(pages[0].nodes[1].has_children,false);
  const row1=pages[0].nodes[1],row21=pages[0].nodes[21];
  assert.equal(row1.item_revision_uid,row21.item_revision_uid);assert.notDeepEqual(row1.occurrence_path,row21.occurrence_path);
  for(const page of pages){
    const result=c.readCachePropertyBatch(lines[0],revisions[0],page.nodes.map(row=>row.occurrence_path));
    assert.equal(result.length,page.nodes.length);
    const values=Object.fromEntries(result[0].result.raw_fields.map(field=>[field.field,JSON.parse(field.value_json)]));
    assert.equal(values.C9_bl_parentvpps,'ROOT-VP');assert.equal(values.C9_bl_torque,'12');assert.deepEqual(values.IMAN_Rendering,[]);
  }
  assert(calls.properties.every(call=>call.count<=500),'TC property requests have bounded set sizes');
  assert(calls.properties.length<=200,'no per-node TC property reads');
  assert(calls.relations<=50,'JT relation reads operate on revision sets');
  assert.equal(calls.relations,1,'verified shared revision references are reused within this source window');
  assert.equal(calls.expand,1,'formatting/property pages do not expand ancestors');
});
test('required property and JT failures reject the bulk page; optional matrices remain unavailable',()=>{
  const {context:c,lines,revisions}=fixture(3);c.captureCacheStructure(lines[0],revisions[0]);
  const paths=c.cacheStructurePage(0,200).nodes.map(row=>row.occurrence_path),get=c.dm.getProperties;
  c.dm.getProperties=(objects,names)=>names.includes('C9_bl_torque')?{errors:['access denied']}:get(objects,names);
  assert.throws(()=>c.readCachePropertyBatch(lines[0],revisions[0],paths),/teamcenter_structure_properties_failed/);
  c.dm.getProperties=get;c.dm.expandGRMRelationsForPrimary=()=>({serviceData:{errors:['access denied']}});
  assert.throws(()=>c.readCachePropertyBatch(lines[0],revisions[0],paths),/teamcenter_geometry_properties_failed/);
  c.dm.expandGRMRelationsForPrimary=objects=>({output:objects.map(inputObject=>({inputObject,relationshipData:[]}))});
  c.dm.getProperties=(objects,names)=>names.includes('bl_plmxml_occ_xform')?{errors:['property absent']}:get(objects,names);
  const result=c.readCachePropertyBatch(lines[0],revisions[0],paths);
  assert.equal(result[0].result.raw_fields.find(field=>field.field==='bl_plmxml_occ_xform').read_state,'unavailable');
});
test('bulk structure and required/reference failures are not published as empty values',()=>{
  const {context:c,lines,revisions}=fixture(3);
  const diagnostics=[];c.observationTiming=(stage,count,detail)=>diagnostics.push({stage,count,detail});
  c.structure.expandPSAllLevels=()=>({serviceData:{errors:[{codes:[123],messages:['access denied']}]}});
  assert.throws(()=>c.captureCacheStructure(lines[0],revisions[0]),/teamcenter_structure_expand_failed/);
  assert.equal(diagnostics.find(d=>d.stage==='cache_structure_errors')?.detail[0].codes[0],123);
  assert.throws(()=>c.cacheStructurePage(0,200),/teamcenter_cache_structure_not_ready/);
});
test('unreachable objects returned by all-level expansion cannot publish a truncated tree',()=>{
  const {context:c,lines,revisions}=fixture(3);
  c.structure.expandPSAllLevels=()=>({output:[{parent:{bomLine:lines[0],objectOfBOMLine:revisions[0]},children:[{bomLine:lines[1],objectOfBOMLine:revisions[1]}]},{parent:{bomLine:lines[2],objectOfBOMLine:revisions[2]},children:[]}]});
  assert.throws(()=>c.captureCacheStructure(lines[0],revisions[0]),/teamcenter_structure_response_invalid/);
});
test('only TC read-permission errors are skipped for the configured accessible cache scope',()=>{
  const {context:c,lines,revisions}=fixture(3),expand=c.structure.expandPSAllLevels;
  const diagnostics=[];c.observationTiming=(stage,count,detail)=>diagnostics.push({stage,count,detail});
  c.structure.expandPSAllLevels=(...args)=>({...expand(...args),serviceData:{errors:[{codes:[214000],messages:['read denied']}]}});
  assert.equal(c.captureCacheStructure(lines[0],revisions[0]).node_count,3);
  assert.equal(diagnostics.find(d=>d.stage==='cache_permission_errors')?.count,1);
  c.cacheFlatRows=null;c.structure.expandPSAllLevels=(...args)=>({...expand(...args),serviceData:{errors:[{codes:[214000,999],messages:['read denied','server error']}]}});
  assert.throws(()=>c.captureCacheStructure(lines[0],revisions[0]),/teamcenter_structure_expand_failed/);
});
test('permission-denied business properties retain unavailable state instead of empty success',()=>{
  const {context:c,lines,revisions}=fixture(3),get=lines[1].getPropertyObject;
  c.captureCacheStructure(lines[0],revisions[0]);
  lines[1].getPropertyObject=name=>{if(name==='catiaFileName')throw Error('read denied');return get(name)};
  c.dm.getProperties=(objects,names)=>names.includes('catiaFileName')?{errors:[{codes:[214000],messages:['read denied']}]}:{};
  const rows=c.readCachePropertyBatch(lines[0],revisions[0],c.cacheStructurePage(0,200).nodes.map(row=>row.occurrence_path));
  const denied=rows[1].result.raw_fields.find(f=>f.field==='catiaFileName');
  assert.equal(denied.read_state,'unavailable');assert.equal(denied.value_json,'null');
  const cached=rows[0].result.raw_fields.find(f=>f.field==='catiaFileName');
  assert.equal(cached.read_state,'unavailable','old loaded properties cannot mask a current denied read');
});
test('optional matrix and bounding box errors cannot publish previously loaded values',()=>{
  const {context:c,lines,revisions}=fixture(3),get=lines[0].getPropertyObject;
  const optional=['bl_plmxml_occ_xform','bl_occ_xform_matrix','bl_plmxml_abs_xform','bl_abs_xform_matrix','bl_bounding_boxes'];
  lines[0].getPropertyObject=name=>optional.includes(name)?{getDisplayableValue:()=> 'old matrix',getDoubleArrayValue:()=>Array(name==='bl_bounding_boxes'?6:16).fill(99)}:get(name);
  c.captureCacheStructure(lines[0],revisions[0]);
  for(const errors of [[{codes:[214000],messages:['read denied']}],['property absent']]){
    c.dm.getProperties=(objects,names)=>names.some(name=>optional.includes(name))?{errors}:{};
    const rows=c.readCachePropertyBatch(lines[0],revisions[0],c.cacheStructurePage(0,200).nodes.map(row=>row.occurrence_path));
    for(const name of optional){
      const field=rows[0].result.raw_fields.find(field=>field.field===name);
      assert.equal(field.read_state,'unavailable');assert.equal(field.value_json,'null');
    }
  }
  c.dm.getProperties=()=>({});
  const rows=c.readCachePropertyBatch(lines[0],revisions[0],[[]]);
  assert.equal(rows[0].result.raw_fields.find(field=>field.field==='bl_plmxml_abs_xform').read_state,'value','a later successful request clears the unavailable marker');
});
test('one absent optional alias preserves successfully read matrix fields using field groups',()=>{
  const {context:c,lines,revisions,calls}=fixture(200),get=lines[0].getPropertyObject;
  lines[0].getPropertyObject=name=>['bl_plmxml_abs_xform','bl_abs_xform_matrix'].includes(name)?{getDisplayableValue:()=> 'matrix',getDoubleArrayValue:()=>Array(16).fill(1)}:get(name);
  c.captureCacheStructure(lines[0],revisions[0]);
  c.dm.getProperties=(objects,names)=>{calls.properties.push({count:objects.length,names:[...names]});return names.includes('bl_abs_xform_matrix')?{errors:['property absent']}:{};};
  const before=calls.properties.length;
  const rows=c.readCachePropertyBatch(lines[0],revisions[0],c.cacheStructurePage(0,200).nodes.map(row=>row.occurrence_path));
  assert.equal(rows[0].result.raw_fields.find(field=>field.field==='bl_plmxml_abs_xform').read_state,'value');
  assert.equal(rows[0].result.raw_fields.find(field=>field.field==='bl_abs_xform_matrix').read_state,'unavailable');
  assert(calls.properties.length-before<=12,'optional alias errors split fields, not individual nodes');
});
test('large property blocks are byte paged before crossing the native frame boundary',()=>{
  const {context:c,lines,revisions}=fixture(200);c.captureCacheStructure(lines[0],revisions[0]);
  c.readNodeProperties=()=>({properties:{name:'part'},raw_fields:[{field:'large',value_json:JSON.stringify('值"\\'.repeat(140000))}]});
  const paths=c.cacheStructurePage(0,200).nodes.map(row=>row.occurrence_path);
  const rows=c.readCachePropertyBatch(lines[0],revisions[0],paths);
  assert(rows.length>0&&rows.length<paths.length);
  assert(Buffer.byteLength(JSON.stringify({rows}))<8*1024*1024);
  assert.equal(c.utf8Bytes('a值😀'),8);
});
