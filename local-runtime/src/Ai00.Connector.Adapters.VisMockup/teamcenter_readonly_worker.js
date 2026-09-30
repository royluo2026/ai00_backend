/* AI00 Teamcenter 14 read-only worker. Cloud capture can reuse an authenticated bounded session. */
var BufferedReader = Java.type('java.io.BufferedReader');
var InputStreamReader = Java.type('java.io.InputStreamReader');
var Connection = Java.type('com.teamcenter.soa.client.Connection');
var CredentialManager = Java.type('com.teamcenter.soa.client.CredentialManager');
var SoaConstants = Java.type('com.teamcenter.soa.SoaConstants');
var SessionService = Java.type('com.teamcenter.services.strong.core.SessionService');
var DataManagementService = Java.type('com.teamcenter.services.strong.core.DataManagementService');
var StructureManagementService = Java.type('com.teamcenter.services.strong.cad.StructureManagementService');
var SavedQueryService = Java.type('com.teamcenter.services.strong.query.SavedQueryService');
var SavedQueryInput = Java.type('com.teamcenter.services.strong.query._2007_06.SavedQuery$SavedQueryInput');
var CreateBOMWindowsInfo = Java.type('com.teamcenter.services.strong.cad._2007_01.StructureManagement$CreateBOMWindowsInfo');
var RevisionRuleConfigInfo = Java.type('com.teamcenter.services.strong.cad._2007_01.StructureManagement$RevisionRuleConfigInfo');
var ExpandPSAllLevelsInfo = Java.type('com.teamcenter.services.strong.cad._2008_06.StructureManagement$ExpandPSAllLevelsInfo');
var ExpandPSAllLevelsPref = Java.type('com.teamcenter.services.strong.cad._2008_06.StructureManagement$ExpandPSAllLevelsPref');
var ExpandPSOneLevelInfo = Java.type('com.teamcenter.services.strong.cad._2008_06.StructureManagement$ExpandPSOneLevelInfo');
var ExpandPSOneLevelPref = Java.type('com.teamcenter.services.strong.cad._2008_06.StructureManagement$ExpandPSOneLevelPref');
var ExpandGRMRelationsPref2 = Java.type('com.teamcenter.services.strong.core._2007_09.DataManagement$ExpandGRMRelationsPref2');
var RelationAndTypesFilter = Java.type('com.teamcenter.services.strong.core._2007_06.DataManagement$RelationAndTypesFilter');
var GetItemFromIdInfo = Java.type('com.teamcenter.services.strong.core._2007_01.DataManagement$GetItemFromIdInfo');

var input = new BufferedReader(new InputStreamReader(java.lang.System['in'], 'UTF-8'));
var state = { user: String(input.readLine() || ''), password: String(input.readLine() || ''), group: '', role: '' };
var request = JSON.parse(String(input.readLine() || '{}'));
var CredentialImpl = Java.extend(CredentialManager, {
  getCredentialType: function () { return CredentialManager.CLIENT_CREDENTIAL_TYPE_STD; },
  getCredentials: function () { return Java.to([state.user, state.password, state.group, state.role], 'java.lang.String[]'); },
  setUserPassword: function (user, password) { state.user = String(user || ''); state.password = String(password || ''); },
  setGroupRole: function (group, role) { state.group = String(group || ''); state.role = String(role || ''); }
});

function observationTiming(stage, count, detail) {
  if (request.command !== 'observe' && request.command !== 'children' && String(request.command).indexOf('cache_') !== 0) return;
  try {
    var system = Java.type('java.lang.System'), now = Number(system.nanoTime());
    if (typeof observationTiming.started === 'undefined') observationTiming.started = now;
    var pid = Java.type('java.lang.ProcessHandle').current().pid();
    var file = Java.type('java.nio.file.Paths').get(system.getProperty('java.io.tmpdir'), 'ai00-teamcenter-observe-' + pid + (persistent?'_'+requestId:'') + '.timing.jsonl');
    var event = { stage: stage, elapsed_ms: Math.round((now - observationTiming.started) / 1000000), count: Number(count || 0) };
    if (detail) event.detail=detail.slice(0,20).map(function(error){return {codes:error.codes.slice(0,20),messages:error.messages.slice(0,20).map(function(message){return String(message).slice(0,512);}),object_uid:error.object_uid,object_type:error.object_type,levels:error.levels,client_index:error.client_index};});
    var row = JSON.stringify(event) + '\n';
    var options = Java.type('java.nio.file.StandardOpenOption');
    Java.type('java.nio.file.Files').write(file, new (Java.type('java.lang.String'))(row).getBytes('UTF-8'), options.CREATE, options.APPEND);
  } catch (ignoredTiming) { /* Diagnostic I/O must not fail the read operation. */ }
}
var structureNodes = Object.create(null), structureNodeCount = 0, cacheFlatRows=null;
var cacheRevisionGeometry=Object.create(null),cachePreparedRevisions=Object.create(null),cacheDeniedProperties=Object.create(null);
var cacheSpatialProperties=['bl_occ_xform','bl_plmxml_def_occ_xform','bl_plmxml_def_abs_xform','bl_plmxml_occ_xform','bl_occ_xform_matrix','bl_plmxml_abs_xform','bl_abs_xform_matrix','bl_bounding_boxes'];
function structureKey(path) {
  return JSON.stringify(path.map(function(edge){return [edge.occurrence_uid,edge.item_revision_uid];}));
}
function cacheReadPolicy(enabled) {
  if(!enabled){
    if(cachePolicyActive){
      connection.setObjectPropertyPolicy(cacheNormalPolicy);
      if(bomWindow)StructureManagementService.getService(connection).closeBOMWindows(Java.to([bomWindow],'com.teamcenter.soa.client.model.strong.BOMWindow[]'));
      bomWindow=null;bomContext=null;structureNodes=Object.create(null);structureNodeCount=0;cacheFlatRows=null;
      cacheRevisionGeometry=Object.create(null);cachePreparedRevisions=Object.create(null);cacheDeniedProperties=Object.create(null);cachePolicyActive=false;
    }
    return;
  }
  if(!cachePolicyName){
    var ObjectPropertyPolicy=Java.type('com.teamcenter.soa.common.ObjectPropertyPolicy');
    var PolicyProperty=Java.type('com.teamcenter.soa.common.PolicyProperty');
    var policy=new ObjectPropertyPolicy();
    policy.setModifier(PolicyProperty.WITH_PROPERTIES,false);
    policy.setModifier(PolicyProperty.EXCLUDE_MODIFIABLE,true);
    policy.addType('BOMLine',Java.to(['bl_occurrence_uid','bl_revision'],'java.lang.String[]'));
    policy.getType('BOMLine').setModifier(PolicyProperty.EXCLUDE_PARENT_PROPERTIES,true);
    cacheNormalPolicy=connection.getCurrentObjectPropertyPolicy();
    cachePolicyName=String(session.setObjectPropertyPolicy(policy));
    if(!cachePolicyName)fail('teamcenter_cache_policy_failed');
  }
  connection.setObjectPropertyPolicy(cachePolicyName);
  cachePolicyActive=true;
}
function cacheAccessibleErrors(errors) {
  var denied=errors.filter(function(error){return error.codes&&error.codes.length&&error.codes.every(function(code){return Number(code)===214000;});});
  if(denied.length)observationTiming('cache_permission_errors',denied.length,denied);
  return errors.filter(function(error){return denied.indexOf(error)<0;});
}
function structureProperties(objects, names, allowDenied, optional) {
  function unavailable(group,fields){group.forEach(function(object){var uid=String(object.getUid());if(!cacheDeniedProperties[uid])cacheDeniedProperties[uid]=Object.create(null);fields.forEach(function(field){cacheDeniedProperties[uid][field]=true;});});}
  function read(group,fields){
    var errors=serviceErrors(dm.getProperties(Java.to(group,'com.teamcenter.soa.client.model.ModelObject[]'),Java.to(fields,'java.lang.String[]')));
    if((allowDenied?cacheAccessibleErrors(errors):errors).length){
      if(!optional)fail('teamcenter_structure_properties_failed');
      // Optional aliases vary by installation. Split only fields across the
      // whole object set so one absent alias cannot hide a readable matrix.
      if(fields.length>1){var optionalSplit=Math.floor(fields.length/2);read(group,fields.slice(0,optionalSplit));read(group,fields.slice(optionalSplit));return;}
      unavailable(group,fields);return;
    }
    if(errors.length){
      // Only denied reads pay for diagnostic bisection. A cached getter is not
      // evidence that this request could read the property.
      if(group.length>1){var middle=Math.floor(group.length/2);read(group.slice(0,middle),fields);read(group.slice(middle),fields);}
      else if(fields.length>1){var split=Math.floor(fields.length/2);read(group,fields.slice(0,split));read(group,fields.slice(split));}
      else unavailable(group,fields);
    }else if(allowDenied)group.forEach(function(object){var denied=cacheDeniedProperties[String(object.getUid())];if(denied)fields.forEach(function(field){delete denied[field];});});
  }
  for(var offset=0;offset<objects.length;offset+=500)read(objects.slice(offset,offset+500),names);
}
function cacheFieldDenied(object,name){var fields=cacheDeniedProperties[String(object.getUid())];return !!(fields&&fields[name]);}
function cacheDisplay(object,name){return cacheFieldDenied(object,name)?'':display(object,name);}
function expandStructureEntry(entry) {
  if (entry.children) return entry.children;
  var info = new ExpandPSOneLevelInfo(); info.parentBomLines = Java.to([entry.line], 'com.teamcenter.soa.client.model.strong.BOMLine[]'); info.excludeFilter = 'None2';
  var pref = new ExpandPSOneLevelPref(); pref.expItemRev = true;
  observationTiming('children_expand_start', entry.path.length);
  var response = structure.expandPSOneLevel(info, pref);
  observationTiming('children_expand_done', entry.path.length);
  if (serviceErrors(response.serviceData).length) fail('teamcenter_structure_expand_failed');
  var outputs = Java.from(response.output || []);
  if (outputs.length !== 1 || !outputs[0].parent || !outputs[0].parent.bomLine || String(outputs[0].parent.bomLine.getUid()) !== String(entry.line.getUid())) fail('teamcenter_structure_response_invalid');
  var children = Java.from(outputs[0].children || []);
  if (children.length > 250000 || structureNodeCount + children.length > 250000) fail('teamcenter_node_limit_exceeded');
  var lines = children.map(function(child){if(!child.bomLine)fail('teamcenter_structure_response_invalid');return child.bomLine;});
  observationTiming('children_properties_start', lines.length);
  structureProperties(lines, ['bl_occurrence_uid','bl_revision','bl_line_name','bl_rev_item_revision_id','bl_item_object_type']);
  observationTiming('children_properties_done', lines.length);
  var seen = Object.create(null), entries = children.map(function(child,index){
    var revision = child.objectOfBOMLine || modelObject(child.bomLine,'bl_revision');
    var occurrence = display(child.bomLine,'bl_occurrence_uid');
    if (!occurrence || !revision) fail('teamcenter_occurrence_identity_invalid');
    var edge = {occurrence_uid:occurrence,item_revision_uid:String(revision.getUid())};
    var path = entry.path.concat([edge]), key = structureKey(path);
    if(seen[key])fail('teamcenter_occurrence_identity_invalid');seen[key]=true;
    return {line:child.bomLine,revision:revision,path:path,order:index,detailsLoaded:true};
  });
  // Publish only a completely validated level. Paths distinguish repeated instances of one revision.
  entries.forEach(function(child){structureNodes[structureKey(child.path)]=child;});
  structureNodeCount += entries.length; entry.children = entries;
  return entries;
}
function locateStructureEntry(root, rootRevision, path) {
  if (!structureNodes['[]']) {structureNodes['[]']={line:root,revision:rootRevision,path:[],order:0,detailsLoaded:false};structureNodeCount=1;}
  var key = structureKey(path);
  if (structureNodes[key]) return structureNodes[key];
  var entry = structureNodes['[]'];
  for (var depth=0;depth<path.length;depth++) {
    var prefix=structureKey(path.slice(0,depth+1));
    if (!structureNodes[prefix]) expandStructureEntry(entry);
    entry=structureNodes[prefix];
    if (!entry) fail('teamcenter_parent_path_not_found');
  }
  return entry;
}
function readChildrenLevel(root, rootRevision, path) {
  function node(line, revision, nodePath, order) {
    return {occurrence_id:'', parent_occurrence_id:null, occurrence_path:nodePath, depth:nodePath.length, child_order:order,
      name:display(line,'bl_line_name'),item_revision_uid:String(revision.getUid()),revision_id:display(line,'bl_rev_item_revision_id'),component_type:display(line,'bl_item_object_type'),has_children:null};
  }
  var entry=locateStructureEntry(root,rootRevision,path),entries=expandStructureEntry(entry);
  if(!entry.detailsLoaded){structureProperties([entry.line],['bl_line_name','bl_rev_item_revision_id','bl_item_object_type']);entry.detailsLoaded=true;}
  var parent=node(entry.line,entry.revision,entry.path,entry.order);parent.has_children=entries.length>0;
  return {parent:parent,nodes:entries.map(function(child){return node(child.line,child.revision,child.path,child.order);})};
}
function captureCacheStructure(root, rootRevision) {
  if(cacheFlatRows)return {node_count:cacheFlatRows.length};
  var info=new ExpandPSAllLevelsInfo();info.parentBomLines=Java.to([root],'com.teamcenter.soa.client.model.strong.BOMLine[]');info.excludeFilter='None2';
  var pref=new ExpandPSAllLevelsPref();pref.expItemRev=true;
  observationTiming('cache_structure_expand_start',0);
  var response=structure.expandPSAllLevels(info,pref);
  observationTiming('cache_structure_expand_done',(response.output||[]).length);
  var expansionErrors=cacheAccessibleErrors(serviceErrors(response.serviceData));
  if(expansionErrors.length){observationTiming('cache_structure_errors',expansionErrors.length,expansionErrors);fail('teamcenter_structure_expand_failed');}
  var objects=Object.create(null),children=Object.create(null),parentSeen=Object.create(null);
  function remember(line,revision){
    if(!line)fail('teamcenter_structure_response_invalid');var uid=String(line.getUid());
    if(objects[uid]&&revision&&objects[uid].revision&&String(objects[uid].revision.getUid())!==String(revision.getUid()))fail('teamcenter_structure_response_invalid');
    if(!objects[uid])objects[uid]={line:line,revision:revision};else if(revision)objects[uid].revision=revision;
  }
  remember(root,rootRevision);
  Java.from(response.output||[]).forEach(function(output){
    if(!output.parent)fail('teamcenter_structure_response_invalid');
    remember(output.parent.bomLine,output.parent.objectOfBOMLine);
    var uid=String(output.parent.bomLine.getUid());if(parentSeen[uid])fail('teamcenter_structure_response_invalid');parentSeen[uid]=true;
    children[uid]=Java.from(output.children||[]).map(function(child){remember(child.bomLine,child.objectOfBOMLine);return String(child.bomLine.getUid());});
  });
  var values=Object.keys(objects).map(function(uid){return objects[uid];});
  if(values.length>250000)fail('teamcenter_node_limit_exceeded');
  structureProperties(values.map(function(value){return value.line;}),['bl_occurrence_uid','bl_revision','bl_line_name','bl_rev_item_revision_id','bl_item_object_type'],true);
  var queue=[{uid:String(root.getUid()),path:[],order:0,ancestors:[]}],rows=[],locators=Object.create(null),visited=Object.create(null);
  for(var offset=0;offset<queue.length;offset++){
    if(queue.length>250000)fail('teamcenter_node_limit_exceeded');
    var current=queue[offset],object=objects[current.uid],revision=object.revision||modelObject(object.line,'bl_revision');
    visited[current.uid]=true;
    if(!revision||current.path.length>128||current.ancestors.indexOf(current.uid)>=0)fail('teamcenter_structure_response_invalid');
    var key=structureKey(current.path);if(locators[key])fail('teamcenter_occurrence_identity_invalid');
    var entry={line:object.line,revision:revision,path:current.path,order:current.order,detailsLoaded:true,children:[]};locators[key]=entry;
    var descendants=children[current.uid]||[];
    rows.push({occurrence_id:current.path.length?current.path[current.path.length-1].occurrence_uid:'root',parent_occurrence_id:null,occurrence_path:current.path,
      depth:current.path.length,child_order:current.order,name:cacheDisplay(object.line,'bl_line_name'),item_revision_uid:String(revision.getUid()),
      revision_id:cacheDisplay(object.line,'bl_rev_item_revision_id'),component_type:cacheDisplay(object.line,'bl_item_object_type'),has_children:descendants.length>0,child_count:descendants.length});
    var seen=Object.create(null);
    descendants.forEach(function(uid,index){
      var child=objects[uid],childRevision=child.revision||(cacheFieldDenied(child.line,'bl_revision')?null:modelObject(child.line,'bl_revision')),occurrence=cacheDisplay(child.line,'bl_occurrence_uid');
      if(!childRevision||!occurrence)fail('teamcenter_occurrence_identity_invalid');
      var path=current.path.concat([{occurrence_uid:occurrence,item_revision_uid:String(childRevision.getUid())}]),childKey=structureKey(path);
      if(seen[childKey])fail('teamcenter_occurrence_identity_invalid');seen[childKey]=true;
      queue.push({uid:uid,path:path,order:index,ancestors:current.ancestors.concat([current.uid])});
    });
  }
  if(Object.keys(objects).some(function(uid){return !visited[uid];}))fail('teamcenter_structure_response_invalid');
  // Publish only the fully validated flat topology; no partial tree escapes on errors.
  rows.forEach(function(row){if(row.occurrence_path.length)locators[structureKey(row.occurrence_path.slice(0,-1))].children.push(locators[structureKey(row.occurrence_path)]);});
  structureNodes=locators;structureNodeCount=rows.length;cacheFlatRows=rows;
  observationTiming('cache_structure_ready_done', rows.length);
  return {node_count:rows.length};
}
function cacheStructurePage(cursor,size){
  if(!cacheFlatRows)fail('teamcenter_cache_structure_not_ready');
  if(cursor<0||cursor>cacheFlatRows.length||size<1||size>500||cursor%1||size%1)fail('teamcenter_cache_page_invalid');
  var nodes=cacheFlatRows.slice(cursor,cursor+size),next=cursor+nodes.length;
  return {cursor:cursor,next_cursor:next<cacheFlatRows.length?next:null,node_count:cacheFlatRows.length,nodes:nodes};
}
function utf8Bytes(text){
  var bytes=0;
  for(var i=0;i<text.length;i++){
    var code=text.charCodeAt(i);
    if(code<128)bytes++;else if(code<2048)bytes+=2;
    else if(code>=0xD800&&code<=0xDBFF&&i+1<text.length&&text.charCodeAt(i+1)>=0xDC00&&text.charCodeAt(i+1)<=0xDFFF){bytes+=4;i++;}
    else bytes+=3;
  }
  return bytes;
}
function readCachePropertyBatch(root,rootRevision,paths){
  if(!Array.isArray(paths)||paths.length<1||paths.length>256)fail('teamcenter_cache_page_invalid');
  captureCacheStructure(root,rootRevision);
  var entries=paths.map(function(path){var entry=structureNodes[structureKey(path)];if(!entry)fail('teamcenter_parent_path_not_found');return entry;});
  var lines=entries.map(function(entry){return entry.line;}),revisions=Object.create(null);
  entries.forEach(function(entry){var uid=String(entry.revision.getUid());if(!cachePreparedRevisions[uid])revisions[uid]=entry.revision;});
  var revisionValues=Object.keys(revisions).map(function(uid){return revisions[uid];});
  observationTiming('cache_properties_start',entries.length);
  structureProperties(lines,['bl_line_name','bl_occurrence_uid','C9_bl_torque','C9_bl_torqueimpor','catiaOccurrenceName','catiaFileName','C9_bl_vpps','C9_bl_fnaname','bl_formatted_parent_name','catiaParentPartName','C9_bl_parentvpps','C9_bl_parentvppsname'],true);
  structureProperties(revisionValues,['object_name','item_id','item_revision_id','owning_user','owning_group','c9_weight','c9_unitweight','items_tag'],true);
  // Optional matrix fields retain individual unavailable states rather than failing the page.
  structureProperties(lines,cacheSpatialProperties,true,true);
  var geometry=readGeometryReferences(revisionValues,true);
  revisionValues.forEach(function(revision){var uid=String(revision.getUid());cacheRevisionGeometry[uid]=geometry(uid);cachePreparedRevisions[uid]=true;});
  var prepared={geometry:function(uid){return cacheRevisionGeometry[uid];}};
  var result=[],bytes=1024;
  for(var index=0;index<paths.length;index++){
    var row={occurrence_path:paths[index],result:readNodeProperties(root,rootRevision,paths[index],true,prepared)},size=utf8Bytes(JSON.stringify(row));
    if(size>7*1024*1024)fail('cache_page_too_large');
    if(result.length&&bytes+size+1>8*1024*1024)break;
    result.push(row);bytes+=size+1;
  }
  observationTiming('cache_properties_done',result.length);
  return result;
}
function readGeometryReferences(revisionValues, strict) {
  var batchSize=256;
  function checked(data) { if (strict && serviceErrors(data).length) fail('teamcenter_geometry_properties_failed'); }
  var relationPref = new ExpandGRMRelationsPref2(); relationPref.expItemRev = false; relationPref.returnRelations = true;
  var relationFilter = new RelationAndTypesFilter(); relationFilter.relationTypeName = 'IMAN_Rendering';
  relationFilter.otherSideObjectTypes = Java.to([], 'java.lang.String[]');
  relationPref.info = Java.to([relationFilter], 'com.teamcenter.services.strong.core._2007_06.DataManagement$RelationAndTypesFilter[]');
  var datasetsByRevision = {}; var datasets = {}; var seenRevisions = {};
  function referenceFiles(dataset) {
    if (!strict) return modelObjects(dataset, 'ref_list');
    try { return Java.from(dataset.getPropertyObject('ref_list').getModelObjectArrayValue() || []); }
    catch (ignoredRefList) { fail('teamcenter_geometry_properties_failed'); }
  }
  function fileName(file) {
    if (!strict) return display(file, 'original_file_name');
    try { var name=file.getPropertyObject('original_file_name').getDisplayableValue();if(name!==null&&String(name))return String(name); }
    catch (ignoredFileName) {}
    fail('teamcenter_geometry_properties_failed');
  }
  observationTiming('geometry_relations_start', revisionValues.length);
  for (var gp = 0; gp < revisionValues.length; gp += batchSize) {
    var relationResponse = dm.expandGRMRelationsForPrimary(Java.to(revisionValues.slice(gp, gp + batchSize), 'com.teamcenter.soa.client.model.ModelObject[]'), relationPref);
    checked(relationResponse.serviceData);
    Java.from(relationResponse.output || []).forEach(function (output) {
    var primaryUid = output.inputObject ? String(output.inputObject.getUid()) : '';
    if (strict && !primaryUid) fail('teamcenter_geometry_properties_failed');
    seenRevisions[primaryUid] = true;
    if (!datasetsByRevision[primaryUid]) datasetsByRevision[primaryUid] = [];
    Java.from(output.relationshipData || []).forEach(function (relationData) {
      Java.from(relationData.relationshipObjects || []).forEach(function (relationship) {
      var other = relationship.otherSideObject;
      if (other && other.getTypeObject().isInstanceOf('Dataset')) {
        var datasetUid = String(other.getUid()); datasets[datasetUid] = other;
        datasetsByRevision[primaryUid].push(datasetUid);
      }
      });
    });
    });
  }
  if (strict) revisionValues.forEach(function (revision) { if (!seenRevisions[String(revision.getUid())]) fail('teamcenter_geometry_properties_failed'); });
  observationTiming('geometry_relations_done', Object.keys(datasets).length);
  var datasetValues = Object.keys(datasets).map(function (uid) { return datasets[uid]; });
  for (var dp = 0; dp < datasetValues.length; dp += batchSize)
    checked(dm.getProperties(Java.to(datasetValues.slice(dp, dp + batchSize), 'com.teamcenter.soa.client.model.ModelObject[]'), Java.to(['ref_list'], 'java.lang.String[]')));
  observationTiming('dataset_properties_done', datasetValues.length);
  var files = {};
  datasetValues.forEach(function (dataset) { referenceFiles(dataset).forEach(function (file) { if (file) files[String(file.getUid())] = file; else if(strict)fail('teamcenter_geometry_properties_failed'); }); });
  var fileValues = Object.keys(files).map(function (uid) { return files[uid]; });
  for (var fp = 0; fp < fileValues.length; fp += batchSize)
    checked(dm.getProperties(Java.to(fileValues.slice(fp, fp + batchSize), 'com.teamcenter.soa.client.model.ModelObject[]'), Java.to(['original_file_name'], 'java.lang.String[]')));

  observationTiming('file_properties_done', fileValues.length);
  function geometry(revisionUid) {
    var result = [];
    (datasetsByRevision[revisionUid] || []).forEach(function (datasetUid) {
    referenceFiles(datasets[datasetUid]).forEach(function (file) {
      var name = fileName(file);
      if (/\.jt$/i.test(name)) result.push({ dataset_uid: datasetUid, file_uid: String(file.getUid()), file_name: name, relation_type: 'IMAN_Rendering' });
    });
    });
    return result;
  }
  return geometry;
}
function readNodeProperties(root, rootRevision, path, preserveRaw,prepared) {
  function properties(objects, names) {
    if (objects.length && serviceErrors(dm.getProperties(
      Java.to(objects, 'com.teamcenter.soa.client.model.ModelObject[]'),
      Java.to(names, 'java.lang.String[]'))).length) fail('teamcenter_structure_properties_failed');
  }
  var entry=locateStructureEntry(root,rootRevision,path),line=entry.line,revision=entry.revision;
  if(!prepared){
    properties([line], ['bl_line_name', 'bl_occurrence_uid', 'C9_bl_torque', 'C9_bl_torqueimpor']);
    properties([revision], ['object_name', 'item_id', 'item_revision_id', 'owning_user',
      'owning_group', 'c9_weight', 'c9_unitweight']);
  }
  var componentType = '';
  try { componentType = String(revision.getTypeObject().getName()); } catch (ignoredType) {}
  function value(object, name) { return prepared&&cacheFieldDenied(object,name)?null:display(object, name) || null; }
  var projection = {
    name: value(line, 'bl_line_name') || value(revision, 'object_name'),
    item_id: value(revision, 'item_id'),
    revision_id: value(revision, 'item_revision_id'),
    component_type: componentType || null,
    owning_user: value(revision, 'owning_user'),
    owning_group: value(revision, 'owning_group'),
    weight_raw: value(revision, 'c9_weight'),
    unit_weight_raw: value(revision, 'c9_unitweight'),
    torque_raw: value(line, 'C9_bl_torque'),
    torque_importance: value(line, 'C9_bl_torqueimpor'),
    occurrence_uid: path.length ? value(line, 'bl_occurrence_uid') : null
  };
  if (!preserveRaw) return projection;
  var rawFields=[];
  function raw(object,kind,name,read) {
    var entry={object_uid:String(object.getUid()),object_kind:kind,field:name,read_state:'unavailable',value_json:'null'};
    if(prepared&&cacheFieldDenied(object,name)){rawFields.push(entry);return;}
    try {
      var result=read ? read() : object.getPropertyObject(name).getDisplayableValue();
      entry.read_state=result===null?'null':'value';
      entry.value_json=JSON.stringify(result===null?null:read?result:String(result));
    } catch (ignoredRaw) {}
    rawFields.push(entry);
  }
  ['bl_line_name','bl_occurrence_uid','C9_bl_torque','C9_bl_torqueimpor'].forEach(function(name){raw(line,'BOMLine',name);});
  ['object_name','item_id','item_revision_id','owning_user','owning_group','c9_weight','c9_unitweight'].forEach(function(name){raw(revision,'ItemRevision',name);});
  // Verified on the current TC BOMLine type; these belong to the occurrence, not its shared revision.
  var instanceFields=['catiaOccurrenceName','catiaFileName','C9_bl_vpps','C9_bl_fnaname','bl_formatted_parent_name','catiaParentPartName','C9_bl_parentvpps','C9_bl_parentvppsname'];
  if(!prepared)properties([line],instanceFields);
  instanceFields.forEach(function(name){raw(line,'BOMLine',name);});
  // TC installations may expose only one of the matrix properties. Preserve individual unavailable states.
  if(!prepared){
    dm.getProperties(Java.to([line], 'com.teamcenter.soa.client.model.ModelObject[]'),Java.to(cacheSpatialProperties, 'java.lang.String[]'));
    properties([revision],['items_tag']);
  }
  cacheSpatialProperties.forEach(function(name){
    raw(line,'BOMLine',name,function(){return doubleArray(line,name,name==='bl_bounding_boxes'?6:16)||line.getPropertyObject(name).getDisplayableValue();});
  });
  raw(revision,'ItemRevision','items_tag',function(){var item=revision.getPropertyObject('items_tag').getModelObjectValue();return item?String(item.getUid()):null;});
  var references=prepared?prepared.geometry(String(revision.getUid())):readGeometryReferences([revision],true)(String(revision.getUid()));
  if(references.length>256)fail('teamcenter_worker_response_too_large');
  rawFields.push({object_uid:String(revision.getUid()),object_kind:'ItemRevision',field:'IMAN_Rendering',read_state:'value',value_json:JSON.stringify(references)});
  return {properties:projection,raw_fields:rawFields};
}
function readCacheFile(dm,fms,reference,outputRoot){
  observationTiming('cache_file_load_objects_start',0);
  var loaded=dm.loadObjects(Java.to([reference.file_uid],'java.lang.String[]'));
  observationTiming('cache_file_load_objects_done',loaded.sizeOfPlainObjects());
  if(serviceErrors(loaded).length||loaded.sizeOfPlainObjects()!==1)fail('teamcenter_file_unavailable');
  var file=loaded.getPlainObject(0);
  if(String(file.getUid())!==reference.file_uid||!file.getTypeObject().isInstanceOf('ImanFile'))fail('teamcenter_file_unavailable');
  observationTiming('cache_file_properties_start',1);
  if(serviceErrors(dm.getProperties(Java.to([file],'com.teamcenter.soa.client.model.ModelObject[]'),Java.to(['original_file_name'],'java.lang.String[]'))).length||display(file,'original_file_name')!==reference.file_name)fail('teamcenter_file_identity_mismatch');
  observationTiming('cache_file_properties_done',1);
  observationTiming('cache_file_fms_start',1);
  var downloaded=fms.getFiles(Java.to([file],'com.teamcenter.soa.client.model.ModelObject[]'));
  observationTiming('cache_file_fms_done',downloaded.sizeOfFiles());
  if(serviceErrors(downloaded).length||downloaded.sizeOfFiles()!==1)fail('teamcenter_file_download_failed');
  var Files=Java.type('java.nio.file.Files'),Paths=Java.type('java.nio.file.Paths');
  observationTiming('cache_file_copy_start',1);
  var target=Files.createTempFile(Paths.get(outputRoot),'ai00-cache-file-','.jt');
  try{
    Files.copy(downloaded.getFile(0).toPath(),target,Java.type('java.nio.file.StandardCopyOption').REPLACE_EXISTING);
    var size=Number(Files.size(target));
    observationTiming('cache_file_copy_done',size);
    if(size<24||size>512*1024*1024)fail('teamcenter_file_size_invalid');
    return {local_path:String(target.toAbsolutePath().toString()),byte_size:size};
  }catch(error){try{Files.deleteIfExists(target);}catch(ignored){}throw error;}
}
function fileByteSize(object){
  // TC14 ImanFile.file_size is rounded display text (for example "551 Kb").
  // Its byte_size property is the exact decimal byte count, exposed as a string.
  var raw;
  try{raw=String(object.getPropertyObject('byte_size').getStringValue()).trim();}catch(ignored){
    observationTiming('cache_file_size_unavailable',0,[{codes:[],messages:['ImanFile.byte_size could not be read'],object_uid:String(object.getUid())}]);
    fail('teamcenter_file_size_unavailable');
  }
  if(!/^\d+$/.test(raw))fail('teamcenter_file_size_unavailable');
  var size=Number(raw);
  // The Connector's Nashorn does not implement Number.isSafeInteger.
  if(size<1||size>9007199254740991)fail('teamcenter_file_size_invalid');
  return size;
}
function readCacheFilePreflight(dm,files){
  var uids=files.map(function(file){return file.file_uid;});
  var loadedObjects=dm.loadObjects(Java.to(uids,'java.lang.String[]'));
  if(serviceErrors(loadedObjects).length||loadedObjects.sizeOfPlainObjects()!==uids.length)fail('teamcenter_file_unavailable');
  var objects=[];
  for(var objectIndex=0;objectIndex<loadedObjects.sizeOfPlainObjects();objectIndex++)objects.push(loadedObjects.getPlainObject(objectIndex));
  if(objects.length!==uids.length)fail('teamcenter_file_unavailable');
  for(var i=0;i<objects.length;i++)
    if(String(objects[i].getUid())!==uids[i]||!objects[i].getTypeObject().isInstanceOf('ImanFile'))fail('teamcenter_file_unavailable');
  if(serviceErrors(dm.getProperties(Java.to(objects,'com.teamcenter.soa.client.model.ModelObject[]'),Java.to(['original_file_name','byte_size'],'java.lang.String[]'))).length)
    fail('teamcenter_file_properties_unavailable');
  return {files:files.map(function(expected){
    var index=uids.indexOf(expected.file_uid),file=objects[index],name=display(file,'original_file_name');
    if(name!==expected.file_name)fail('teamcenter_file_identity_mismatch');
    var size=fileByteSize(file);
    return {file_uid:expected.file_uid,file_name:name,file_size:size};
  })};
}
function fail(code) { throw new Error('AI00_CODE:' + code); }
function serviceErrors(sd) {
  var values = [];
  if (!sd || typeof sd.sizeOfPartialErrors !== 'function') return values;
  for (var i = 0; i < sd.sizeOfPartialErrors(); i++) {
    var stack = sd.getPartialError(i);
    var error={ codes: Java.from(stack.getCodes()), messages: Java.from(stack.getMessages()).map(String) };
    try { error.levels=Java.from(stack.getLevels()); } catch (ignoredLevels) {}
    try { if(stack.hasAssociatedObject()){var object=stack.getAssociatedObject();error.object_uid=String(object.getUid());error.object_type=String(object.getTypeObject().getName());} } catch (ignoredAssociatedObject) {}
    try { if(stack.hasClientIndex())error.client_index=Number(stack.getClientIndex()); } catch (ignoredClientIndex) {}
    values.push(error);
  }
  return values;
}
function loaded(sd) {
  var values = {};
  for (var i = 0; i < sd.sizeOfPlainObjects(); i++) values[String(sd.getPlainObject(i).getUid())] = sd.getPlainObject(i);
  for (var j = 0; j < sd.sizeOfUpdatedObjects(); j++) values[String(sd.getUpdatedObject(j).getUid())] = sd.getUpdatedObject(j);
  return values;
}
function display(object, name) {
  try { return String(object.getPropertyObject(name).getDisplayableValue()); } catch (ignored) { return ''; }
}
function modelObject(object, name) {
  try { return object.getPropertyObject(name).getModelObjectValue(); } catch (ignored) { return null; }
}
function modelObjects(object, name) {
  try { return Java.from(object.getPropertyObject(name).getModelObjectArrayValue()); } catch (ignored) { return []; }
}
function transform(object) {
  var values = doubleArray(object, 'bl_plmxml_occ_xform', 16) || doubleArray(object, 'bl_occ_xform_matrix', 16);
  if (values) return values;
  var text = display(object, 'bl_plmxml_occ_xform') || display(object, 'bl_occ_xform_matrix');
  if (!text) return null;
  var parts = text.match(/[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?/g) || [];
  if (parts.length !== 16) return null;
  return parts.map(Number);
}
function doubleArray(object, name, length) {
  try { var values=Java.from(object.getPropertyObject(name).getDoubleArrayValue()).map(Number);return values.length===length?values:null; }
  catch (ignored) { return null; }
}
function closed(value, fields) {
  if (!value || Array.isArray(value) || typeof value !== 'object') return false;
  var actual = Object.keys(value).sort(); fields = fields.slice().sort();
  return JSON.stringify(actual) === JSON.stringify(fields);
}

var connection = null, session = null, bomWindow = null, bomContext = null, modelFileFms = null;
var cachePolicyName=null,cacheNormalPolicy=null,cachePolicyActive=false;
var persistent = request.keep_session === true, requestId = null, exitCode = 1;
function respond(result) {
  if (persistent) result.request_id=requestId;
  print((persistent?'AI00_TC_READ_V1:':'')+JSON.stringify(result));
}
function closeReadSession() {
  if(modelFileFms){try{modelFileFms.term();}catch(ignoredFms){}modelFileFms=null;}
  observationTiming('cleanup_start', 0);
  try { if (bomWindow && connection) StructureManagementService.getService(connection).closeBOMWindows(Java.to([bomWindow], 'com.teamcenter.soa.client.model.strong.BOMWindow[]')); } catch (ignoredClose) {}
  try { if (session) session.logout(); } catch (ignoredLogout) {}
  state.password = ''; state.user = '';
  if (connection) connection.release();
  connection=null;session=null;bomWindow=null;bomContext=null;structureNodes=Object.create(null);structureNodeCount=0;cacheFlatRows=null;cacheRevisionGeometry=Object.create(null);cachePreparedRevisions=Object.create(null);
  observationTiming('cleanup_done', 0);
}
try {
  while (request) {
    exitCode=1;observationTiming.started=undefined;
    requestId=persistent?request.request_id:null;
    if (!closed(request,persistent?['command','payload','keep_session','request_id']:['command','payload'])
        || persistent && (request.keep_session!==true || typeof requestId!=='string' || !/^[a-f0-9]{32}$/.test(requestId)
          || ['children','node_properties','node_properties_raw','cache_structure','cache_structure_page','cache_properties','cache_file','cache_file_preflight'].indexOf(request.command)<0)
        || ['status','revision_rules','search','observe','children','node_properties','node_properties_raw','cache_structure','cache_structure_page','cache_properties','cache_file','cache_file_preflight'].indexOf(request.command)<0
        || !persistent && request.command.indexOf('cache_')===0)
      fail('teamcenter_worker_command_forbidden');
    var endpointId=(request.command==='status'||request.command==='revision_rules'||request.command==='search')?request.payload.endpoint_id:request.payload.source_selector.endpoint_id;
    if (endpointId!=='tc-production') fail('teamcenter_endpoint_forbidden');
try {
  if (!connection) {
  observationTiming('login_start', 0);
  connection = new Connection('http://192.168.44.150:7001/tc', new CredentialImpl(), SoaConstants.REST, SoaConstants.HTTP);
  connection.setApplicationName('AI00 Read Only Product Structure');
  session = SessionService.getService(connection);
  var login = session.login(state.user, state.password, '', '', 'zh_CN', 'AI00ReadOnlyProductStructure');
  if (!login || !login.user) throw new Error('authentication_failed');
  observationTiming('login_done', 0);
  }
  if (request.command === 'status') {
    respond({ ok: true, result: { state: 'ready', endpoint_id: endpointId } });
    exitCode = 0;
  } else if (request.command === 'revision_rules') {
    if (!closed(request.payload, ['endpoint_id'])) fail('teamcenter_revision_rules_input_invalid');
    var ruleDm=DataManagementService.getService(connection),ruleStructure=StructureManagementService.getService(connection);
    var ruleResponse=ruleStructure.getRevisionRules();
    var revisionRules=Java.from(ruleResponse.output||[]).map(function(entry){return entry.revRule;}).filter(function(rule){return rule!==null;});
    if(revisionRules.length)ruleDm.getProperties(Java.to(revisionRules,'com.teamcenter.soa.client.model.ModelObject[]'),Java.to(['object_name'],'java.lang.String[]'));
    var ruleNames=revisionRules.map(function(rule){return display(rule,'object_name');}).filter(function(name){return !!name;});
    respond({ok:true,result:{rules:ruleNames}});exitCode=0;
  } else if (request.command === 'search') {
    var search=request.payload;
    if(!closed(search,['endpoint_id','item_id','revision_id','revision_rule','configuration_date'])||!search.item_id)fail('teamcenter_search_input_invalid');
    var dmSearch=DataManagementService.getService(connection),queryService=SavedQueryService.getService(connection),queryName='__Item_Revision_name_ID_and_rev';
    var definitions=queryService.getSavedQueries(),queryDefinition=null;
    Java.from(definitions.queries||[]).some(function(definition){if(String(definition.name)===queryName){queryDefinition=definition.query;return true;}return false;});
    if(!queryDefinition)fail('teamcenter_saved_query_not_found');
    var description=queryService.describeSavedQueries(Java.to([queryDefinition],'com.teamcenter.soa.client.model.strong.ImanQuery[]'));
    if(serviceErrors(description.serviceData).length)fail('teamcenter_search_definition_failed');
    var entryNames={};
    Java.from(description.fieldLists||[]).forEach(function(list){Java.from(list.fields||[]).forEach(function(field){entryNames[String(field.attributeName)]=String(field.entryName);});});
    function queryEntry(attribute){if(!entryNames[attribute])fail('teamcenter_search_field_unavailable');return entryNames[attribute];}
    var query=String(search.item_id),revisionId=String(search.revision_id||''),matches={},ordered=[];
    function executeBatch(specs){
      var inputs=specs.map(function(spec){
        var saved=new SavedQueryInput(),entries=[queryEntry(spec[0])],values=[spec[1]];
        saved.query=queryDefinition;saved.entries=Java.to(entries,'java.lang.String[]');saved.values=Java.to(values,'java.lang.String[]');
        saved.limitList=Java.to([],'com.teamcenter.soa.client.model.ModelObject[]');saved.limitListCount=0;saved.maxNumToReturn=5001;saved.maxNumToInflate=5001;saved.resultsType=0;
        return saved;
      });
      var response=queryService.executeSavedQueries(Java.to(inputs,'com.teamcenter.services.strong.query._2007_06.SavedQuery$SavedQueryInput[]'));
      if(serviceErrors(response.serviceData).length)fail('teamcenter_search_failed');
      Java.from(response.arrayOfResults||[]).forEach(function(result){var objects=Java.from(result.objects||[]);if(objects.length>5000)fail('teamcenter_search_too_broad');objects.forEach(function(object){var uid=String(object.getUid());if(!matches[uid]){matches[uid]=object;ordered.push(object);}});});
    }
    executeBatch([['items_tag.item_id',query]]);
    if(!ordered.length)executeBatch([['items_tag.item_id','*'+query+'*'],['object_name','*'+query+'*']]);
    var revisions=ordered,items=[];
    if(revisions.length)dmSearch.getProperties(Java.to(revisions,'com.teamcenter.soa.client.model.ModelObject[]'),Java.to(['object_name','object_string','item_id','item_revision_id','owning_user','owning_group','items_tag'],'java.lang.String[]'));
    if(revisionId)revisions=revisions.filter(function(revision){return display(revision,'item_revision_id')===revisionId;});
    var itemByRevision={},itemsByUid={};
    revisions.forEach(function(revision){var item=modelObject(revision,'items_tag');if(item){itemByRevision[String(revision.getUid())]=item;itemsByUid[String(item.getUid())]=item;}});
    var itemValues=Object.keys(itemsByUid).map(function(uid){return itemsByUid[uid];});
    if(itemValues.length)dmSearch.getProperties(Java.to(itemValues,'com.teamcenter.soa.client.model.ModelObject[]'),Java.to(['item_id'],'java.lang.String[]'));
    revisions.forEach(function(revision){
      var item=itemByRevision[String(revision.getUid())];if(!item)return;
      items.push({display_name:display(revision,'object_string')||display(revision,'object_name'),item_id:display(item,'item_id')||display(revision,'item_id'),revision_id:display(revision,'item_revision_id'),component_type:String(revision.getTypeObject().getName()),owning_user:display(revision,'owning_user'),owning_group:display(revision,'owning_group'),source_selector:{endpoint_id:'tc-production',object_uid:String(item.getUid()),item_revision_uid:String(revision.getUid()),bom_view_uid:'',revision_rule:String(search.revision_rule),configuration_date:String(search.configuration_date)}});
    });
    respond({ok:true,result:{items:items}});exitCode=0;
  } else if(request.command==='cache_file'){
    var filePayload=request.payload,reference=filePayload.file_ref;
    if(!closed(filePayload,['source_selector','file_ref','output_root'])||!closed(reference,['dataset_uid','file_uid','file_name','relation_type'])||reference.relation_type!=='IMAN_Rendering'||typeof reference.file_uid!=='string'||!reference.file_uid||reference.file_uid.length>128||typeof reference.file_name!=='string'||reference.file_name.length>512||!(/\.jt$/i.test(reference.file_name))||(/[\\/\x00-\x1f]/.test(reference.file_name))||typeof filePayload.output_root!=='string'||!filePayload.output_root)fail('teamcenter_file_input_invalid');
    if(!modelFileFms)modelFileFms=new (Java.type('com.teamcenter.soa.client.FileManagementUtility'))(connection);
    respond({ok:true,result:readCacheFile(DataManagementService.getService(connection),modelFileFms,reference,filePayload.output_root)});exitCode=0;
  } else if(request.command==='cache_file_preflight'){
    var preflightPayload=request.payload,preflightFiles=preflightPayload.files;
    if(!closed(preflightPayload,['source_selector','files'])||!Array.isArray(preflightFiles)||preflightFiles.length<1||preflightFiles.length>8)fail('cache_file_preflight_input_invalid');
    var seenPreflight=Object.create(null);
    preflightFiles.forEach(function(file){
      if(!closed(file,['file_uid','file_name'])||typeof file.file_uid!=='string'||!file.file_uid||file.file_uid.length>128||typeof file.file_name!=='string'||file.file_name.length>512||!(/\.jt$/i.test(file.file_name))||(/[\\/\x00-\x1f]/.test(file.file_name))||seenPreflight[file.file_uid])fail('cache_file_preflight_input_invalid');
      seenPreflight[file.file_uid]=true;
    });
    respond({ok:true,result:readCacheFilePreflight(DataManagementService.getService(connection),preflightFiles)});exitCode=0;
  } else {
    var payload = request.payload;
    var childrenCommand = request.command === 'children';
    var nodePropertiesCommand = request.command === 'node_properties' || request.command === 'node_properties_raw';
    var bulkCommand=request.command.indexOf('cache_')===0;
    if(!bulkCommand)cacheReadPolicy(false);
    var structureReadCommand = childrenCommand || nodePropertiesCommand || bulkCommand;
    var expectedPayload = childrenCommand ? (persistent?['source_selector','parent_path','refresh']:['source_selector','parent_path'])
      : nodePropertiesCommand ? ['source_selector','occurrence_path']
      : request.command==='cache_structure'?['source_selector','capture_key']
      : request.command==='cache_structure_page'?['source_selector','native_generation','cursor','page_size']
      : request.command==='cache_properties'?['source_selector','native_generation','occurrence_paths']
      : ['source_selector', 'max_nodes', 'max_depth', 'property_projection'];
    if (!closed(payload, expectedPayload)) fail(nodePropertiesCommand ? 'teamcenter_node_properties_input_invalid' : 'teamcenter_observe_input_invalid');
    if(request.command==='cache_structure'&&(typeof payload.capture_key!=='string'||!/^[a-f0-9]{32}$/.test(payload.capture_key)))fail('teamcenter_cache_page_invalid');
    if(persistent&&childrenCommand&&typeof payload.refresh!=='boolean')fail('teamcenter_children_input_invalid');
    if(childrenCommand && (!Array.isArray(payload.parent_path)||payload.parent_path.length>128)) fail('teamcenter_children_input_invalid');
    if(nodePropertiesCommand && (!Array.isArray(payload.occurrence_path)||payload.occurrence_path.length>128)) fail('teamcenter_node_properties_input_invalid');
    var selector = payload.source_selector;
    if (!closed(selector, ['endpoint_id','object_uid','item_revision_uid','bom_view_uid','revision_rule','configuration_date']) ||
        (!structureReadCommand && (Number(payload.max_nodes) < 1 || Number(payload.max_nodes) > 250000 || Number(payload.max_depth) < 1 || Number(payload.max_depth) > 128)))
      fail('teamcenter_observe_input_invalid');
    var dm = DataManagementService.getService(connection);
    var structure = StructureManagementService.getService(connection);
    var selectorKey=JSON.stringify(['endpoint_id','object_uid','item_revision_uid','bom_view_uid','revision_rule','configuration_date'].map(function(name){return selector[name];}));
    if (!bomContext || bomContext.key !== selectorKey || persistent && childrenCommand && payload.refresh || request.command==='cache_structure' && bomContext.captureKey!==payload.capture_key) {
      if (bomWindow) structure.closeBOMWindows(Java.to([bomWindow], 'com.teamcenter.soa.client.model.strong.BOMWindow[]'));
      bomWindow=null; bomContext=null;structureNodes=Object.create(null);structureNodeCount=0;cacheFlatRows=null;cacheRevisionGeometry=Object.create(null);cachePreparedRevisions=Object.create(null);cacheDeniedProperties=Object.create(null);
    var requestedUids = [String(selector.item_revision_uid || selector.object_uid)];
    if (selector.bom_view_uid) requestedUids.push(String(selector.bom_view_uid));
    observationTiming('source_load_start', 0);
    var loadResponse = dm.loadObjects(Java.to(requestedUids, 'java.lang.String[]'));
    observationTiming('source_load_done', 0);
    if(structureReadCommand && serviceErrors(loadResponse).length)fail('teamcenter_source_not_found');
    var objects = loaded(loadResponse);
    var revision = objects[requestedUids[0]];
    var bomView = selector.bom_view_uid ? objects[String(selector.bom_view_uid)] : null;
    if (!revision) fail('teamcenter_source_not_found');

    var rulesResponse = structure.getRevisionRules();
    if(structureReadCommand && serviceErrors(rulesResponse.serviceData).length)fail('teamcenter_revision_rule_not_found');
    var rules = Java.from(rulesResponse.output || []).map(function (entry) { return entry.revRule; }).filter(function (item) { return item !== null; });
    if (rules.length) {var ruleProperties=dm.getProperties(Java.to(rules, 'com.teamcenter.soa.client.model.ModelObject[]'), Java.to(['object_name'], 'java.lang.String[]'));if(structureReadCommand&&serviceErrors(ruleProperties).length)fail('teamcenter_revision_rule_not_found');}
    var rule = null;
    rules.some(function (item) { if (display(item, 'object_name') === String(selector.revision_rule)) { rule = item; return true; } return false; });
    if (!rule) fail('teamcenter_revision_rule_not_found');

    var createInfo = new CreateBOMWindowsInfo();
    createInfo.clientId = 'AI00ReadOnlyProductStructure';
    createInfo.itemRev = revision;
    if (bomView) createInfo.bomView = bomView;
    var ruleInfo = new RevisionRuleConfigInfo();
    ruleInfo.clientId = 'AI00ReadOnlyProductStructureRule'; ruleInfo.revRule = rule;
    if(structureReadCommand){
      var RuleEntryProps=Java.type('com.teamcenter.services.strong.cad._2007_01.StructureManagement$RevisionRuleEntryProps');
      var ruleProps=new RuleEntryProps();
      ruleProps.date=Java.type('java.util.GregorianCalendar').from(Java.type('java.time.OffsetDateTime').parse(String(selector.configuration_date)).toZonedDateTime());
      ruleProps.today=false;ruleInfo.props=ruleProps;
    }
    createInfo.revRuleConfigInfo = ruleInfo;
    observationTiming('bom_window_start', 0);
    var created = structure.createBOMWindows(Java.to([createInfo], 'com.teamcenter.services.strong.cad._2007_01.StructureManagement$CreateBOMWindowsInfo[]'));
    observationTiming('bom_window_done', 0);
    if (!created.output || !created.output.length || !created.output[0].bomLine) fail('teamcenter_bom_window_failed');
    bomWindow = created.output[0].bomWindow;
    if(structureReadCommand && serviceErrors(created.serviceData).length)fail('teamcenter_bom_window_failed');
    var rootLine = created.output[0].bomLine;
    bomContext={key:selectorKey,root:rootLine,revision:revision};
    structureNodes=Object.create(null);structureNodeCount=0;
    } else { var rootLine=bomContext.root;var revision=bomContext.revision; }
    if(bulkCommand){
      cacheReadPolicy(true);
      if(request.command==='cache_structure'){
        bomContext.captureKey=payload.capture_key;
        var manifest=captureCacheStructure(rootLine,revision);
        if(!bomContext.bulkToken)bomContext.bulkToken=String(Java.type('java.util.UUID').randomUUID()).replace(/-/g,'');
        respond({ok:true,result:{node_count:manifest.node_count,native_generation:bomContext.bulkToken}});
      }else{
        if(typeof payload.native_generation!=='string'||payload.native_generation!==bomContext.bulkToken)fail('teamcenter_cache_generation_stale');
        if(request.command==='cache_structure_page')respond({ok:true,result:cacheStructurePage(payload.cursor,payload.page_size)});
        else{
          if(!Array.isArray(payload.occurrence_paths)||payload.occurrence_paths.some(function(path){return !Array.isArray(path)||path.length>128||path.some(function(edge){return !closed(edge,['occurrence_uid','item_revision_uid'])||typeof edge.occurrence_uid!=='string'||!edge.occurrence_uid||edge.occurrence_uid.length>128||typeof edge.item_revision_uid!=='string'||!edge.item_revision_uid||edge.item_revision_uid.length>128;});}))fail('teamcenter_cache_page_invalid');
          respond({ok:true,result:{rows:readCachePropertyBatch(rootLine,revision,payload.occurrence_paths)}});
        }
      }
      exitCode=0;
    } else if(childrenCommand){
      respond({ok:true,result:readChildrenLevel(rootLine,revision,payload.parent_path)});exitCode=0;
    } else if(nodePropertiesCommand){
      respond({ok:true,result:readNodeProperties(rootLine,revision,payload.occurrence_path,request.command==='node_properties_raw')});exitCode=0;
    } else {
    var expandInfo = new ExpandPSAllLevelsInfo();
    expandInfo.parentBomLines = Java.to([rootLine], 'com.teamcenter.soa.client.model.strong.BOMLine[]');
    expandInfo.excludeFilter = 'None2';
    var expandPref = new ExpandPSAllLevelsPref(); expandPref.expItemRev = false;
    observationTiming('expand_start', 0);
    var expanded = structure.expandPSAllLevels(expandInfo, expandPref);
    observationTiming('expand_done', (expanded.output || []).length);
    if (serviceErrors(expanded.serviceData).length) fail('teamcenter_structure_expand_failed');

    var raw = {};
    var children = {};
    function remember(line, object) {
      if (!line) return;
      var uid = String(line.getUid());
      if (!raw[uid]) raw[uid] = { line: line, object: object };
    }
    remember(rootLine, revision);
    Java.from(expanded.output || []).forEach(function (output) {
      var parent = output.parent;
      remember(parent.bomLine, parent.objectOfBOMLine);
      var parentUid = String(parent.bomLine.getUid());
      if (!children[parentUid]) children[parentUid] = [];
      Java.from(output.children || []).forEach(function (child) {
        remember(child.bomLine, child.objectOfBOMLine);
        children[parentUid].push(String(child.bomLine.getUid()));
      });
    });
    if (Object.keys(raw).length > Number(payload.max_nodes)) fail('teamcenter_node_limit_exceeded');

    var rawValues = Object.keys(raw).map(function (uid) { return raw[uid]; });
    var lines = rawValues.map(function (item) { return item.line; });
    var revisions = {};
    rawValues.forEach(function (item) { if (item.object) revisions[String(item.object.getUid())] = item.object; });
    var revisionValues = Object.keys(revisions).map(function (uid) { return revisions[uid]; });
    var batchSize = 256;
    observationTiming('line_properties_start', lines.length);
    for (var lp = 0; lp < lines.length; lp += batchSize) {
      dm.getProperties(Java.to(lines.slice(lp, lp + batchSize), 'com.teamcenter.soa.client.model.ModelObject[]'),
        Java.to(['bl_occurrence_uid','bl_sequence_no','bl_plmxml_occ_xform','bl_plmxml_abs_xform','bl_occ_xform_matrix','bl_abs_xform_matrix','bl_bounding_boxes','bl_line_name','C9_bl_torque','C9_bl_torqueimpor'], 'java.lang.String[]'));
      observationTiming('line_properties_batch', Math.min(lp + batchSize, lines.length));
    }
    observationTiming('revision_properties_start', revisionValues.length);
    for (var rp = 0; rp < revisionValues.length; rp += batchSize) {
      dm.getProperties(Java.to(revisionValues.slice(rp, rp + batchSize), 'com.teamcenter.soa.client.model.ModelObject[]'),
        Java.to(['object_name','item_id','item_revision_id','owning_user','owning_group','items_tag','c9_weight','c9_unitweight'], 'java.lang.String[]'));
      observationTiming('revision_properties_batch', Math.min(rp + batchSize, revisionValues.length));
    }

    var geometry = readGeometryReferences(revisionValues);
    var resultNodes = [];
    var queue = [{ uid: String(rootLine.getUid()), parent: null, depth: 0, order: 0 }];
    for (var qi = 0; qi < queue.length; qi++) {
      var current = queue[qi];
      if (current.depth > Number(payload.max_depth)) fail('teamcenter_depth_limit_exceeded');
      var item = raw[current.uid]; var object = item.object;
      var revisionUid = object ? String(object.getUid()) : '';
      var stableOccurrence = display(item.line, 'bl_occurrence_uid') || current.uid;
      var itemObject = object ? modelObject(object, 'items_tag') : null;
      resultNodes.push({
        occurrence_id: stableOccurrence,
        parent_occurrence_id: current.parent,
        depth: current.depth,
        child_order: current.order,
        name: display(item.line, 'bl_line_name') || (object ? display(object, 'object_name') : ''),
        item_uid: itemObject ? String(itemObject.getUid()) : '',
        item_id: object ? display(object, 'item_id') : '',
        item_revision_uid: revisionUid,
        revision_id: object ? display(object, 'item_revision_id') : '',
        component_type: object ? String(object.getTypeObject().getName()) : '',
        owning_user: object ? display(object, 'owning_user') : '',
        owning_group: object ? display(object, 'owning_group') : '',
        transform: transform(item.line),
        absolute_transform: doubleArray(item.line,'bl_plmxml_abs_xform',16)||doubleArray(item.line,'bl_abs_xform_matrix',16),
        transform_unit: 'm', transform_convention: 'teamcenter_plmxml_4x4_row_major',
        bbox: doubleArray(item.line,'bl_bounding_boxes',6), bbox_unit: 'm',
        torque_raw: display(item.line,'C9_bl_torque')||null,
        torque_importance: display(item.line,'C9_bl_torqueimpor')||null,
        weight_raw: object?(display(object,'c9_weight')||null):null,
        unit_weight_raw: object?(display(object,'c9_unitweight')||null):null,
        geometry_refs: geometry(revisionUid)
      });
      (children[current.uid] || []).forEach(function (childUid, index) {
        var childStable = display(raw[childUid].line, 'bl_occurrence_uid') || childUid;
        queue.push({ uid: childUid, parent: stableOccurrence, depth: current.depth + 1, order: index });
      });
    }
    observationTiming('serialize_start', resultNodes.length);
    respond({ ok: true, result: { nodes: resultNodes } });
    observationTiming('serialize_done', resultNodes.length);
    exitCode = 0;
    }
  }
} catch (error) {
  // Only a source line number is persisted: never exception text, credentials or model payloads.
  observationTiming('failed_line', Number(error && error.lineNumber) || 0);
  var message = String(error && error.message ? error.message : error);
  var marker = message.indexOf('AI00_CODE:');
  var code = marker >= 0 ? message.substring(marker + 10).replace(/\s.*$/, '')
    : /authentication_failed|invalid credentials|login failed/i.test(message) ? 'teamcenter_authentication_failed'
    : /session.*(?:expired|invalid)|not logged/i.test(message) ? 'teamcenter_session_expired'
    : 'teamcenter_worker_failed';
  java.lang.System.err.println(code);
  respond({ ok: false, code: code });
}
    observationTiming('command_done', 0);
    if (!persistent || exitCode !== 0) break;
    var next = input.readLine();
    if (next === null) break;
    request = JSON.parse(String(next));
  }
} finally { closeReadSession(); }
java.lang.System.exit(exitCode);
