/* AI00 Teamcenter 14 read-only worker. One authenticated bounded command per process. */
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

function observationTiming(stage, count) {
  if (request.command !== 'observe' && request.command !== 'children') return;
  try {
    var system = Java.type('java.lang.System'), now = Number(system.nanoTime());
    if (typeof observationTiming.started === 'undefined') observationTiming.started = now;
    var pid = Java.type('java.lang.ProcessHandle').current().pid();
    var file = Java.type('java.nio.file.Paths').get(system.getProperty('java.io.tmpdir'), 'ai00-teamcenter-observe-' + pid + '.timing.jsonl');
    var row = JSON.stringify({ stage: stage, elapsed_ms: Math.round((now - observationTiming.started) / 1000000), count: Number(count || 0) }) + '\n';
    var options = Java.type('java.nio.file.StandardOpenOption');
    Java.type('java.nio.file.Files').write(file, new (Java.type('java.lang.String'))(row).getBytes('UTF-8'), options.CREATE, options.APPEND);
  } catch (ignoredTiming) { /* Diagnostic I/O must not fail the read operation. */ }
}
function readChildrenLevel(root, rootRevision, path) {
  function properties(objects, names) {
    for (var offset = 0; offset < objects.length; offset += 500) {
      if (serviceErrors(dm.getProperties(Java.to(objects.slice(offset, offset + 500), 'com.teamcenter.soa.client.model.ModelObject[]'), Java.to(names, 'java.lang.String[]'))).length)
        fail('teamcenter_structure_properties_failed');
    }
  }
  function node(line, revision, nodePath, order) {
    return {occurrence_id:'', parent_occurrence_id:null, occurrence_path:nodePath, depth:nodePath.length, child_order:order,
      name:display(line,'bl_line_name'),item_revision_uid:String(revision.getUid()),revision_id:display(line,'bl_rev_item_revision_id'),component_type:display(line,'bl_item_object_type'),has_children:null};
  }
  var line = root, revision = rootRevision, walked = [], order = 0;
  for (var depth = 0; depth <= path.length; depth++) {
    var info = new ExpandPSOneLevelInfo(); info.parentBomLines = Java.to([line], 'com.teamcenter.soa.client.model.strong.BOMLine[]'); info.excludeFilter = 'None2';
    var pref = new ExpandPSOneLevelPref(); pref.expItemRev = true;
    observationTiming('children_expand_start', depth);
    var response = structure.expandPSOneLevel(info, pref);
    observationTiming('children_expand_done', depth);
    if (serviceErrors(response.serviceData).length) fail('teamcenter_structure_expand_failed');
    var outputs = Java.from(response.output || []);
    if (outputs.length !== 1 || !outputs[0].parent || !outputs[0].parent.bomLine || String(outputs[0].parent.bomLine.getUid()) !== String(line.getUid())) fail('teamcenter_structure_response_invalid');
    var children = Java.from(outputs[0].children || []);
    if (children.length > 250000) fail('teamcenter_node_limit_exceeded');
    var lines = children.map(function(child){if(!child.bomLine)fail('teamcenter_structure_response_invalid');return child.bomLine;});
    observationTiming('children_properties_start', lines.length);
    properties(lines, ['bl_occurrence_uid','bl_revision','bl_line_name','bl_rev_item_revision_id','bl_item_object_type']);
    observationTiming('children_properties_done', lines.length);
    var seen = {}, entries = children.map(function(child,index){
      var childRevision = child.objectOfBOMLine || modelObject(child.bomLine,'bl_revision');
      var occurrence = display(child.bomLine,'bl_occurrence_uid');
      if (!occurrence || !childRevision) fail('teamcenter_occurrence_identity_invalid');
      var edge = {occurrence_uid:occurrence,item_revision_uid:String(childRevision.getUid())};
      var key = JSON.stringify(edge);
      if(seen[key])fail('teamcenter_occurrence_identity_invalid');seen[key]=true;
      return {line:child.bomLine,revision:childRevision,edge:edge,order:index};
    });
    if(depth === path.length){
      properties([line],['bl_line_name','bl_rev_item_revision_id','bl_item_object_type']);
      var parent = node(line,revision,walked,order);parent.has_children=entries.length>0;
      return {parent:parent,nodes:entries.map(function(entry){return node(entry.line,entry.revision,walked.concat([entry.edge]),entry.order);})};
    }
    var matches=entries.filter(function(entry){return entry.edge.occurrence_uid===path[depth].occurrence_uid&&entry.edge.item_revision_uid===path[depth].item_revision_uid;});
    if(matches.length!==1)fail('teamcenter_parent_path_not_found');
    line=matches[0].line;revision=matches[0].revision;order=matches[0].order;walked.push(matches[0].edge);
  }
}
function readNodeProperties(root, rootRevision, path) {
  function properties(objects, names) {
    if (objects.length && serviceErrors(dm.getProperties(
      Java.to(objects, 'com.teamcenter.soa.client.model.ModelObject[]'),
      Java.to(names, 'java.lang.String[]'))).length) fail('teamcenter_structure_properties_failed');
  }
  var line = root, revision = rootRevision;
  for (var depth = 0; depth < path.length; depth++) {
    var info = new ExpandPSOneLevelInfo();
    info.parentBomLines = Java.to([line], 'com.teamcenter.soa.client.model.strong.BOMLine[]');
    info.excludeFilter = 'None2';
    var pref = new ExpandPSOneLevelPref(); pref.expItemRev = true;
    var response = structure.expandPSOneLevel(info, pref);
    if (serviceErrors(response.serviceData).length) fail('teamcenter_structure_expand_failed');
    var outputs = Java.from(response.output || []);
    if (outputs.length !== 1 || !outputs[0].parent || !outputs[0].parent.bomLine
        || String(outputs[0].parent.bomLine.getUid()) !== String(line.getUid()))
      fail('teamcenter_structure_response_invalid');
    var children = Java.from(outputs[0].children || []);
    var lines = children.map(function (child) {
      if (!child.bomLine) fail('teamcenter_structure_response_invalid');
      return child.bomLine;
    });
    properties(lines, ['bl_occurrence_uid', 'bl_revision']);
    var matches = children.map(function (child) {
      var childRevision = child.objectOfBOMLine || modelObject(child.bomLine, 'bl_revision');
      return {line: child.bomLine, revision: childRevision,
        occurrence_uid: display(child.bomLine, 'bl_occurrence_uid')};
    }).filter(function (child) {
      return child.revision && child.occurrence_uid === path[depth].occurrence_uid
        && String(child.revision.getUid()) === path[depth].item_revision_uid;
    });
    if (matches.length !== 1) fail('teamcenter_parent_path_not_found');
    line = matches[0].line; revision = matches[0].revision;
  }
  properties([line], ['bl_line_name', 'bl_occurrence_uid', 'C9_bl_torque', 'C9_bl_torqueimpor']);
  properties([revision], ['object_name', 'item_id', 'item_revision_id', 'owning_user',
    'owning_group', 'c9_weight', 'c9_unitweight']);
  var componentType = '';
  try { componentType = String(revision.getTypeObject().getName()); } catch (ignoredType) {}
  function value(object, name) { return display(object, name) || null; }
  return {
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
}
function fail(code) { throw new Error('AI00_CODE:' + code); }
function serviceErrors(sd) {
  var values = [];
  if (!sd || typeof sd.sizeOfPartialErrors !== 'function') return values;
  for (var i = 0; i < sd.sizeOfPartialErrors(); i++) {
    var stack = sd.getPartialError(i);
    values.push({ codes: Java.from(stack.getCodes()), messages: Java.from(stack.getMessages()).map(String) });
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

if (!closed(request, ['command', 'payload']) || ['status', 'revision_rules', 'search', 'observe', 'children', 'node_properties'].indexOf(request.command) < 0) fail('teamcenter_worker_command_forbidden');
var endpointId = (request.command === 'status' || request.command === 'revision_rules' || request.command === 'search') ? request.payload.endpoint_id : request.payload.source_selector.endpoint_id;
if (endpointId !== 'tc-production') fail('teamcenter_endpoint_forbidden');

var connection = null;
var session = null;
var bomWindow = null;
var exitCode = 1;
try {
  observationTiming('login_start', 0);
  connection = new Connection('http://192.168.44.150:7001/tc', new CredentialImpl(), SoaConstants.REST, SoaConstants.HTTP);
  connection.setApplicationName('AI00 Read Only Product Structure');
  session = SessionService.getService(connection);
  var login = session.login(state.user, state.password, '', '', 'zh_CN', 'AI00ReadOnlyProductStructure');
  if (!login || !login.user) throw new Error('authentication_failed');
  observationTiming('login_done', 0);
  if (request.command === 'status') {
    print(JSON.stringify({ ok: true, result: { state: 'ready', endpoint_id: endpointId } }));
    exitCode = 0;
  } else if (request.command === 'revision_rules') {
    if (!closed(request.payload, ['endpoint_id'])) fail('teamcenter_revision_rules_input_invalid');
    var ruleDm=DataManagementService.getService(connection),ruleStructure=StructureManagementService.getService(connection);
    var ruleResponse=ruleStructure.getRevisionRules();
    var revisionRules=Java.from(ruleResponse.output||[]).map(function(entry){return entry.revRule;}).filter(function(rule){return rule!==null;});
    if(revisionRules.length)ruleDm.getProperties(Java.to(revisionRules,'com.teamcenter.soa.client.model.ModelObject[]'),Java.to(['object_name'],'java.lang.String[]'));
    var ruleNames=revisionRules.map(function(rule){return display(rule,'object_name');}).filter(function(name){return !!name;});
    print(JSON.stringify({ok:true,result:{rules:ruleNames}}));exitCode=0;
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
    print(JSON.stringify({ok:true,result:{items:items}}));exitCode=0;
  } else {
    var payload = request.payload;
    var childrenCommand = request.command === 'children';
    var nodePropertiesCommand = request.command === 'node_properties';
    var structureReadCommand = childrenCommand || nodePropertiesCommand;
    var expectedPayload = childrenCommand ? ['source_selector','parent_path']
      : nodePropertiesCommand ? ['source_selector','occurrence_path']
      : ['source_selector', 'max_nodes', 'max_depth', 'property_projection'];
    if (!closed(payload, expectedPayload)) fail(nodePropertiesCommand ? 'teamcenter_node_properties_input_invalid' : 'teamcenter_observe_input_invalid');
    if(childrenCommand && (!Array.isArray(payload.parent_path)||payload.parent_path.length>128)) fail('teamcenter_children_input_invalid');
    if(nodePropertiesCommand && (!Array.isArray(payload.occurrence_path)||payload.occurrence_path.length>128)) fail('teamcenter_node_properties_input_invalid');
    var selector = payload.source_selector;
    if (!closed(selector, ['endpoint_id','object_uid','item_revision_uid','bom_view_uid','revision_rule','configuration_date']) ||
        (!structureReadCommand && (Number(payload.max_nodes) < 1 || Number(payload.max_nodes) > 250000 || Number(payload.max_depth) < 1 || Number(payload.max_depth) > 128)))
      fail('teamcenter_observe_input_invalid');
    var dm = DataManagementService.getService(connection);
    var structure = StructureManagementService.getService(connection);
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
    if(childrenCommand){
      print(JSON.stringify({ok:true,result:readChildrenLevel(rootLine,revision,payload.parent_path)}));exitCode=0;
    } else if(nodePropertiesCommand){
      print(JSON.stringify({ok:true,result:readNodeProperties(rootLine,revision,payload.occurrence_path)}));exitCode=0;
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

    var relationPref = new ExpandGRMRelationsPref2(); relationPref.expItemRev = false; relationPref.returnRelations = true;
    var relationFilter = new RelationAndTypesFilter(); relationFilter.relationTypeName = 'IMAN_Rendering';
    relationFilter.otherSideObjectTypes = Java.to([], 'java.lang.String[]');
    relationPref.info = Java.to([relationFilter], 'com.teamcenter.services.strong.core._2007_06.DataManagement$RelationAndTypesFilter[]');
    var datasetsByRevision = {}; var datasets = {};
    observationTiming('geometry_relations_start', revisionValues.length);
    for (var gp = 0; gp < revisionValues.length; gp += batchSize) {
      var relationResponse = dm.expandGRMRelationsForPrimary(Java.to(revisionValues.slice(gp, gp + batchSize), 'com.teamcenter.soa.client.model.ModelObject[]'), relationPref);
      Java.from(relationResponse.output || []).forEach(function (output) {
        var primaryUid = output.inputObject ? String(output.inputObject.getUid()) : '';
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
    observationTiming('geometry_relations_done', Object.keys(datasets).length);
    var datasetValues = Object.keys(datasets).map(function (uid) { return datasets[uid]; });
    for (var dp = 0; dp < datasetValues.length; dp += batchSize)
      dm.getProperties(Java.to(datasetValues.slice(dp, dp + batchSize), 'com.teamcenter.soa.client.model.ModelObject[]'), Java.to(['ref_list'], 'java.lang.String[]'));
    observationTiming('dataset_properties_done', datasetValues.length);
    var files = {};
    datasetValues.forEach(function (dataset) { modelObjects(dataset, 'ref_list').forEach(function (file) { if (file) files[String(file.getUid())] = file; }); });
    var fileValues = Object.keys(files).map(function (uid) { return files[uid]; });
    for (var fp = 0; fp < fileValues.length; fp += batchSize)
      dm.getProperties(Java.to(fileValues.slice(fp, fp + batchSize), 'com.teamcenter.soa.client.model.ModelObject[]'), Java.to(['original_file_name'], 'java.lang.String[]'));

    observationTiming('file_properties_done', fileValues.length);
    function geometry(revisionUid) {
      var result = [];
      (datasetsByRevision[revisionUid] || []).forEach(function (datasetUid) {
        modelObjects(datasets[datasetUid], 'ref_list').forEach(function (file) {
          var name = display(file, 'original_file_name');
          if (/\.jt$/i.test(name)) result.push({ dataset_uid: datasetUid, file_uid: String(file.getUid()), file_name: name, relation_type: 'IMAN_Rendering' });
        });
      });
      return result;
    }
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
    print(JSON.stringify({ ok: true, result: { nodes: resultNodes } }));
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
  print(JSON.stringify({ ok: false, code: code }));
} finally {
  observationTiming('cleanup_start', 0);
  try { if (bomWindow && connection) StructureManagementService.getService(connection).closeBOMWindows(Java.to([bomWindow], 'com.teamcenter.soa.client.model.strong.BOMWindow[]')); } catch (ignoredClose) {}
  try { if (session) session.logout(); } catch (ignoredLogout) {}
  state.password = ''; state.user = '';
  if (connection) connection.release();
  observationTiming('cleanup_done', 0);
}
java.lang.System.exit(exitCode);
