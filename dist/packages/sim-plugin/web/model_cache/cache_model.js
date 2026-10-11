(function(root,factory){
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  root.AI00ModelCache=api;
})(typeof window!=='undefined'?window:globalThis,()=>{
  'use strict';
  function flatten(value,prefix='',result=Object.create(null)){
    if(prefix)result[prefix]=value;
    if(value&&typeof value==='object')for(const [key,child]of Object.entries(value))flatten(child,prefix+'/'+key.replaceAll('~','~0').replaceAll('/','~1'),result);
    return result;
  }
  function display(value){return value===undefined?'—':typeof value==='string'?(value===''?'""':value):JSON.stringify(value,null,2);}
  function leafFields(paths){
    const parents=new Set();
    for(const path of paths)for(let end=path.lastIndexOf('/');end>0;end=path.lastIndexOf('/',end-1))parents.add(path.slice(0,end));
    return paths.filter(path=>!parents.has(path));
  }
  const labels={structure:'结构',page:'采集信息',properties_result:'属性信息',properties:'模型属性',raw_fields:'TC 原始字段',
    name:'名称',item_id:'零组件编号',revision_id:'修订版本',component_type:'零组件类型',depth:'层级',child_order:'子节点顺序',has_children:'有子节点',
    occurrence_id:'实例标识',parent_occurrence_id:'父实例标识',occurrence_path:'实例路径',occurrence_uid:'实例 UID',item_revision_uid:'修订 UID',
    owning_user:'所有者',owning_group:'所属组',weight_raw:'重量',unit_weight_raw:'单位重量',torque_raw:'扭矩',torque_importance:'扭矩重要度',
    dataset_uid:'数模数据集 UID',file_uid:'数模文件 UID',file_name:'数模文件名',relation_type:'关联关系',IMAN_Rendering:'TC 数模引用（JT）',items_tag:'零组件 UID',
    catia_occurrence_name:'catiaOccurrenceName（项目内唯一标识）',catia_file_name:'catiaFileName',vpps:'VPPS',vpps_desc:'VPPS描述',
    parent_name:'父级',catia_parent_part_name:'父级零组件（catiaParentPartName）',parent_vpps:'父级 VPPS',parent_vpps_name:'父级 VPPS 名称',
    default_transform:'默认变换矩阵',relative_transform:'相对变换矩阵',absolute_transform:'绝对变换矩阵',bbox:'限定框',
    object_uid:'对象 UID',object_kind:'对象类型',field:'字段名',read_state:'读取状态',value_json:'值',
    captured_at:'采集时间',cache_hit:'命中本地缓存',generation:'缓存代次',source_identity_hash:'数据源标识',cursor:'当前游标',next_cursor:'下一页游标',child_count:'子节点数量',complete:'完整性'};
  function fieldLabel(path){return path.slice(1).split('/').map(part=>{
    const key=part.replaceAll('~1','/').replaceAll('~0','~');return labels[key]||(/^\d+$/.test(key)?`第 ${Number(key)+1} 项`:key);
  }).join(' › ');}
  function fieldValue(path,value){
    if(/^\/properties_result\/raw_fields\/\d+\/value_json$/.test(path)&&typeof value==='string')try{return JSON.parse(value);}catch{}
    return value;
  }
  function fieldDisplay(path,value){return display(fieldValue(path,value));}
  function cellDisplay(value){
    if(Array.isArray(value))return value.length?`数组 · ${value.length} 项（点击行查看）`:'空数组';
    if(value&&typeof value==='object'){const count=Object.keys(value).length;return count?`对象 · ${count} 个字段（点击行查看）`:'空对象';}
    return display(value);
  }
  function groupBatches(batches){
    const projects=new Map();
    for(const batch of [...batches].sort((a,b)=>b.created_at.localeCompare(a.created_at)||b.batch_id.localeCompare(a.batch_id))){
      if(!projects.has(batch.project_gid))projects.set(batch.project_gid,{id:batch.project_gid,name:batch.project_name,phases:new Map()});
      const project=projects.get(batch.project_gid),phase=batch.phase||'未分期';
      if(!project.phases.has(phase))project.phases.set(phase,{name:phase,batches:[]});
      project.phases.get(phase).batches.push(batch);
    }
    return [...projects.values()].map(project=>({...project,phases:[...project.phases.values()]}));
  }
  const stable=value=>value&&typeof value==='object'?(Array.isArray(value)?value.map(stable):Object.fromEntries(Object.keys(value).sort().map(key=>[key,stable(value[key])]))):value;
  const modelFieldSources=Object.freeze({catia_occurrence_name:'catiaOccurrenceName',catia_file_name:'catiaFileName',vpps:'C9_bl_vpps',vpps_desc:'C9_bl_fnaname',parent_name:'bl_formatted_parent_name',catia_parent_part_name:'catiaParentPartName',parent_vpps:'C9_bl_parentvpps',parent_vpps_name:'C9_bl_parentvppsname',default_transform:'bl_plmxml_def_occ_xform',relative_transform:'bl_occ_xform_matrix',absolute_transform:'bl_abs_xform_matrix',bbox:'bl_bounding_boxes'});
  function modelProperties(data){
    const result=Object.fromEntries(Object.entries(data.properties_result?.properties||{}).filter(([,value])=>value!==null));
    const raw=Object.create(null);
    for(const entry of data.properties_result?.raw_fields||[])if(['value','null'].includes(entry.read_state))try{raw[entry.field]=JSON.parse(entry.value_json);}catch{}
    for(const [key,source]of Object.entries(modelFieldSources))if(raw[source]===null||typeof raw[source]==='string')result[key]=raw[source];
    if(typeof raw.items_tag==='string')result.item_uid=raw.items_tag;
    if(Array.isArray(raw.IMAN_Rendering)&&raw.IMAN_Rendering.length<=256&&raw.IMAN_Rendering.every(ref=>ref&&['dataset_uid','file_uid','file_name','relation_type'].every(key=>typeof ref[key]==='string')))result.geometry_refs=raw.IMAN_Rendering;
    const numbers=(value,length)=>{
      if(typeof value==='string')value=(value.match(/[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?/g)||[]).map(Number);
      return Array.isArray(value)&&value.length===length&&value.every(n=>typeof n==='number'&&Number.isFinite(n))?value:null;
    };
    result.transform=numbers(raw.bl_plmxml_occ_xform,16)||numbers(raw.bl_occ_xform_matrix,16);
    result.relative_transform=result.transform;
    result.default_transform=numbers(raw.bl_plmxml_def_occ_xform,16)||numbers(raw.bl_occ_xform,16);
    result.absolute_transform=numbers(raw.bl_plmxml_abs_xform,16)||numbers(raw.bl_abs_xform_matrix,16);
    result.bbox=numbers(raw.bl_bounding_boxes,6);
    result.transform_unit=result.transform||result.absolute_transform?'m':null;
    result.transform_convention=result.transform||result.absolute_transform?'teamcenter_plmxml_4x4_row_major':null;
    result.bbox_unit=result.bbox?'m':null;
    return result;
  }
  async function readSnapshot(invoke,projectGid,selector,mapNode){
    if(!projectGid)return null;
    let batch,indexCursor=0;
    do{
      const index=await invoke('simulation.model_cache.list',{cursor:indexCursor,page_size:500});
      batch=index.batches.find(batch=>batch.project_gid===String(projectGid)&&batch.status==='completed'&&JSON.stringify(stable(batch.source_selector))===JSON.stringify(stable(selector)));
      indexCursor=index.next_cursor??null;
    }while(!batch&&indexCursor!==null);
    if(!batch)return null;
    const nodes=[];let cursor=0;
    do{
      const page=await invoke('simulation.model_cache.query',{batch_id:batch.batch_id,search:'',filters:[],mode:'and',cursor,page_size:500});
      if(page.batch.status!=='completed')throw Error('cloud_cache_snapshot_incomplete');
      for(const row of page.rows){
        const data=JSON.parse(row.data_json),properties=modelProperties(data);
        // Older caches cannot serve Simulation until their geometry references have been read.
        if(properties.geometry_refs===undefined)return null;
        nodes.push({...mapNode({...data.structure,...properties}),cloud_properties_result:data.properties_result,cloud_raw_fields:data.properties_result?.raw_fields});
      }
      cursor=page.next_cursor;
    }while(cursor!==null);
    return {state:'ready',source:'teamcenter_cloud_cache',cache_batch_id:batch.batch_id,captured_at:batch.completed_at,complete:true,node_count:nodes.length,nodes,pages:{}};
  }
  return Object.freeze({flatten,display,leafFields,fieldLabel,fieldValue,fieldDisplay,cellDisplay,groupBatches,modelFieldSources,modelProperties,readSnapshot});
});
