const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const script=fs.readFileSync(path.resolve(__dirname,'../src/Ai00.Connector.Adapters.VisMockup/teamcenter_readonly_worker.js'),'utf8');
test('raw cache includes the same JT references and spatial fields as Simulation observations',()=>{
  const object=(uid,fields)=>({getUid:()=>uid,getTypeObject:()=>({getName:()=> 'Part',isInstanceOf:type=>type==='Dataset'&&uid==='dataset'}),getPropertyObject:name=>{
    if(!(name in fields))throw Error('not available');const value=fields[name];
    return {getDisplayableValue:()=>value,getDoubleArrayValue:()=>value,getModelObjectValue:()=>value,getModelObjectArrayValue:()=>value};
  }});
  const item=object('item',{}),file=object('file',{original_file_name:'模型.jt'}),dataset=object('dataset',{ref_list:[file]});
  const revision=object('revision',{object_name:'模型',item_id:'ITEM',item_revision_id:'00',owning_user:'owner',owning_group:'group',c9_weight:'0',c9_unitweight:'kg',items_tag:item});
  const matrix=Array.from({length:16},(_,i)=>i%5===0?1:0);
  const line=object('line',{bl_line_name:'模型',bl_occurrence_uid:'occ',C9_bl_torque:'12',C9_bl_torqueimpor:'重要',catiaOccurrenceName:'ITEM.2',catiaFileName:'ITEM.CATPart',C9_bl_vpps:'VP-01',C9_bl_fnaname:'前悬架',bl_formatted_parent_name:'父总成',catiaParentPartName:'ASSEMBLY',C9_bl_parentvpps:'50',C9_bl_parentvppsname:'底盘',bl_plmxml_occ_xform:matrix,bl_plmxml_abs_xform:matrix,bl_bounding_boxes:[0,0,0,1,2,3]});
  const getLineProperty=line.getPropertyObject;
  line.getPropertyObject=name=>['bl_occ_xform','bl_plmxml_def_occ_xform','bl_plmxml_def_abs_xform'].includes(name)?{getDoubleArrayValue:()=>matrix,getDisplayableValue:()=>matrix.join(' ')}:getLineProperty(name);
  const context={Java:{to:x=>x,from:x=>x},ExpandGRMRelationsPref2:function(){},RelationAndTypesFilter:function(){},
    dm:{getProperties:()=>({}),expandGRMRelationsForPrimary:()=>({output:[{inputObject:revision,relationshipData:[{relationshipObjects:[{otherSideObject:dataset}]}]}]})},
    observationTiming:()=>{},serviceErrors:data=>data?.errors||[],fail:code=>{throw Error(code)},
    display:(o,k)=>{try{return String(o.getPropertyObject(k).getDisplayableValue()??'')}catch{return ''}},
    modelObject:(o,k)=>{try{return o.getPropertyObject(k).getModelObjectValue()}catch{return null}},
    modelObjects:(o,k)=>{try{return o.getPropertyObject(k).getModelObjectArrayValue()}catch{return []}},
    doubleArray:(o,k,n)=>{try{const a=o.getPropertyObject(k).getDoubleArrayValue();return Array.isArray(a)&&a.length===n?a:null}catch{return null}}};
  vm.createContext(context);
  const helper=script.indexOf('function readGeometryReferences('),properties=script.indexOf('function readNodeProperties(');
  vm.runInContext(script.slice(script.indexOf('var structureNodes ='),script.indexOf('function fail(')),context);
  const raw=JSON.parse(JSON.stringify(context.readNodeProperties(line,revision,[],true)));
  assert.equal(raw.properties.torque_raw,'12');assert.equal(raw.properties.torque_importance,'重要');assert.equal(raw.properties.owning_user,'owner');assert.equal(raw.properties.component_type,'Part');
  const fields=Object.fromEntries(raw.raw_fields.map(field=>[field.field,JSON.parse(field.value_json)]));
  assert.deepEqual(fields.IMAN_Rendering,[{dataset_uid:'dataset',file_uid:'file',file_name:'模型.jt',relation_type:'IMAN_Rendering'}]);
  assert.equal(fields.catiaOccurrenceName,'ITEM.2');assert.equal(fields.catiaFileName,'ITEM.CATPart');assert.equal(fields.C9_bl_vpps,'VP-01');assert.equal(fields.C9_bl_fnaname,'前悬架');assert.equal(fields.bl_formatted_parent_name,'父总成');assert.equal(fields.catiaParentPartName,'ASSEMBLY');assert.equal(fields.C9_bl_parentvpps,'50');assert.equal(fields.C9_bl_parentvppsname,'底盘');
  assert.equal(fields.items_tag,'item');assert.deepEqual(fields.bl_plmxml_occ_xform,matrix);assert.deepEqual(fields.bl_bounding_boxes,[0,0,0,1,2,3]);
  for(const name of ['bl_occ_xform','bl_plmxml_def_occ_xform','bl_plmxml_def_abs_xform'])assert.deepEqual(fields[name],matrix);
  assert.deepEqual(Object.keys(context.readNodeProperties(line,revision,[],false)).sort(),Object.keys(raw.properties).sort(),'standard node-properties contract is unchanged');
  assert(script.includes('readGeometryReferences(revisionValues)'),'full observations reuse the same relationship reader');
  context.dm.expandGRMRelationsForPrimary=()=>({output:[],serviceData:{errors:['TC access failure']}});
  assert.throws(()=>context.readNodeProperties(line,revision,[],true),/teamcenter_geometry_properties_failed/,'a failed link read must not publish a verified empty reference list');
  context.dm.expandGRMRelationsForPrimary=()=>({output:[]});
  assert.throws(()=>context.readNodeProperties(line,revision,[],true),/teamcenter_geometry_properties_failed/,'missing revision output is unverified, not a verified empty reference list');
  context.dm.expandGRMRelationsForPrimary=()=>({output:[{inputObject:revision,relationshipData:[{relationshipObjects:[{otherSideObject:object('dataset',{})}]}]}]});
  assert.throws(()=>context.readNodeProperties(line,revision,[],true),/teamcenter_geometry_properties_failed/,'unloaded dataset refs must not become an empty reference list');
  const brokenFile=object('file',{}),brokenDataset=object('dataset',{ref_list:[brokenFile]});
  context.dm.expandGRMRelationsForPrimary=()=>({output:[{inputObject:revision,relationshipData:[{relationshipObjects:[{otherSideObject:brokenDataset}]}]}]});
  assert.throws(()=>context.readNodeProperties(line,revision,[],true),/teamcenter_geometry_properties_failed/,'unloaded file names must not become an empty reference list');
  context.dm.expandGRMRelationsForPrimary=()=>({output:[{inputObject:revision,relationshipData:[]}]});
  const noGeometry=JSON.parse(JSON.stringify(context.readNodeProperties(line,revision,[],true)));
  assert.deepEqual(JSON.parse(noGeometry.raw_fields.find(field=>field.field==='IMAN_Rendering').value_json),[],'successful TC response with no rendering relation is a verified empty result');
});
