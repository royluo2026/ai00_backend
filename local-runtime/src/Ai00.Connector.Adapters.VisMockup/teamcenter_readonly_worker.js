/* AI00 Teamcenter 14 read-only worker. One authenticated bounded command per process. */
var BufferedReader = Java.type('java.io.BufferedReader');
var InputStreamReader = Java.type('java.io.InputStreamReader');
var Connection = Java.type('com.teamcenter.soa.client.Connection');
var CredentialManager = Java.type('com.teamcenter.soa.client.CredentialManager');
var SoaConstants = Java.type('com.teamcenter.soa.SoaConstants');
var SessionService = Java.type('com.teamcenter.services.strong.core.SessionService');
var DataManagementService = Java.type('com.teamcenter.services.strong.core.DataManagementService');
var StructureManagementService = Java.type('com.teamcenter.services.strong.cad.StructureManagementService');
var CreateBOMWindowsInfo = Java.type('com.teamcenter.services.strong.cad._2007_01.StructureManagement$CreateBOMWindowsInfo');
var RevisionRuleConfigInfo = Java.type('com.teamcenter.services.strong.cad._2007_01.StructureManagement$RevisionRuleConfigInfo');
var ExpandPSAllLevelsInfo = Java.type('com.teamcenter.services.strong.cad._2008_06.StructureManagement$ExpandPSAllLevelsInfo');
var ExpandPSAllLevelsPref = Java.type('com.teamcenter.services.strong.cad._2008_06.StructureManagement$ExpandPSAllLevelsPref');
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

if (!closed(request, ['command', 'payload']) || ['status', 'search', 'observe'].indexOf(request.command) < 0) fail('teamcenter_worker_command_forbidden');
var endpointId = (request.command === 'status' || request.command === 'search') ? request.payload.endpoint_id : request.payload.source_selector.endpoint_id;
if (endpointId !== 'tc-production') fail('teamcenter_endpoint_forbidden');

var connection = null;
var session = null;
var bomWindow = null;
var exitCode = 1;
try {
  connection = new Connection('http://192.168.44.150:7001/tc', new CredentialImpl(), SoaConstants.REST, SoaConstants.HTTP);
  connection.setApplicationName('AI00 Read Only Product Structure');
  session = SessionService.getService(connection);
  var login = session.login(state.user, state.password, '', '', 'zh_CN', 'AI00ReadOnlyProductStructure');
  if (!login || !login.user) throw new Error('authentication_failed');
  if (request.command === 'status') {
    print(JSON.stringify({ ok: true, result: { state: 'ready', endpoint_id: endpointId } }));
    exitCode = 0;
  } else if (request.command === 'search') {
    var search=request.payload;
    if(!closed(search,['endpoint_id','item_id','revision_id','revision_rule','configuration_date'])||!search.item_id||!search.revision_id)fail('teamcenter_search_input_invalid');
    var dmSearch=DataManagementService.getService(connection),info=new GetItemFromIdInfo();info.itemId=String(search.item_id);info.revIds=Java.to([String(search.revision_id)],'java.lang.String[]');
    var found=dmSearch.getItemFromId(Java.to([info],'com.teamcenter.services.strong.core._2007_01.DataManagement$GetItemFromIdInfo[]'),1,null),items=[];
    Java.from(found.output||[]).forEach(function(out){
      var item=out.item;Java.from(out.itemRevOutput||[]).forEach(function(revOut){var revision=revOut.itemRevision;if(!item||!revision)return;
        dmSearch.getProperties(Java.to([item,revision],'com.teamcenter.soa.client.model.ModelObject[]'),Java.to(['object_name','object_string','item_id','item_revision_id','owning_user','owning_group'],'java.lang.String[]'));
        items.push({display_name:display(revision,'object_string')||display(revision,'object_name'),item_id:display(revision,'item_id')||String(search.item_id),revision_id:display(revision,'item_revision_id')||String(search.revision_id),component_type:String(revision.getTypeObject().getName()),owning_user:display(revision,'owning_user'),owning_group:display(revision,'owning_group'),source_selector:{endpoint_id:'tc-production',object_uid:String(item.getUid()),item_revision_uid:String(revision.getUid()),bom_view_uid:'',revision_rule:String(search.revision_rule),configuration_date:String(search.configuration_date)}});
      });
    });
    print(JSON.stringify({ok:true,result:{items:items}}));exitCode=0;
  } else {
    var payload = request.payload;
    if (!closed(payload, ['source_selector', 'max_nodes', 'max_depth', 'property_projection'])) fail('teamcenter_observe_input_invalid');
    var selector = payload.source_selector;
    if (!closed(selector, ['endpoint_id','object_uid','item_revision_uid','bom_view_uid','revision_rule','configuration_date']) ||
        Number(payload.max_nodes) < 1 || Number(payload.max_nodes) > 250000 || Number(payload.max_depth) < 1 || Number(payload.max_depth) > 128)
      fail('teamcenter_observe_input_invalid');
    var dm = DataManagementService.getService(connection);
    var structure = StructureManagementService.getService(connection);
    var requestedUids = [String(selector.item_revision_uid || selector.object_uid)];
    if (selector.bom_view_uid) requestedUids.push(String(selector.bom_view_uid));
    var objects = loaded(dm.loadObjects(Java.to(requestedUids, 'java.lang.String[]')));
    var revision = objects[requestedUids[0]];
    var bomView = selector.bom_view_uid ? objects[String(selector.bom_view_uid)] : null;
    if (!revision) fail('teamcenter_source_not_found');

    var rulesResponse = structure.getRevisionRules();
    var rules = Java.from(rulesResponse.output || []).map(function (entry) { return entry.revRule; }).filter(function (item) { return item !== null; });
    if (rules.length) dm.getProperties(Java.to(rules, 'com.teamcenter.soa.client.model.ModelObject[]'), Java.to(['object_name'], 'java.lang.String[]'));
    var rule = null;
    rules.some(function (item) { if (display(item, 'object_name') === String(selector.revision_rule)) { rule = item; return true; } return false; });
    if (!rule) fail('teamcenter_revision_rule_not_found');

    var createInfo = new CreateBOMWindowsInfo();
    createInfo.clientId = 'AI00ReadOnlyProductStructure';
    createInfo.itemRev = revision;
    if (bomView) createInfo.bomView = bomView;
    var ruleInfo = new RevisionRuleConfigInfo();
    ruleInfo.clientId = 'AI00ReadOnlyProductStructureRule'; ruleInfo.revRule = rule;
    createInfo.revRuleConfigInfo = ruleInfo;
    var created = structure.createBOMWindows(Java.to([createInfo], 'com.teamcenter.services.strong.cad._2007_01.StructureManagement$CreateBOMWindowsInfo[]'));
    if (!created.output || !created.output.length || !created.output[0].bomLine) fail('teamcenter_bom_window_failed');
    bomWindow = created.output[0].bomWindow;
    var rootLine = created.output[0].bomLine;
    var expandInfo = new ExpandPSAllLevelsInfo();
    expandInfo.parentBomLines = Java.to([rootLine], 'com.teamcenter.soa.client.model.strong.BOMLine[]');
    expandInfo.excludeFilter = 'None2';
    var expandPref = new ExpandPSAllLevelsPref(); expandPref.expItemRev = false;
    var expanded = structure.expandPSAllLevels(expandInfo, expandPref);
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
    for (var lp = 0; lp < lines.length; lp += batchSize)
      dm.getProperties(Java.to(lines.slice(lp, lp + batchSize), 'com.teamcenter.soa.client.model.ModelObject[]'),
        Java.to(['bl_occurrence_uid','bl_sequence_no','bl_plmxml_occ_xform','bl_plmxml_abs_xform','bl_occ_xform_matrix','bl_abs_xform_matrix','bl_bounding_boxes','bl_line_name','C9_bl_torque','C9_bl_torqueimpor'], 'java.lang.String[]'));
    for (var rp = 0; rp < revisionValues.length; rp += batchSize)
      dm.getProperties(Java.to(revisionValues.slice(rp, rp + batchSize), 'com.teamcenter.soa.client.model.ModelObject[]'),
        Java.to(['object_name','item_id','item_revision_id','owning_user','owning_group','items_tag','c9_weight','c9_unitweight'], 'java.lang.String[]'));

    var relationPref = new ExpandGRMRelationsPref2(); relationPref.expItemRev = false; relationPref.returnRelations = true;
    var relationFilter = new RelationAndTypesFilter(); relationFilter.relationTypeName = 'IMAN_Rendering';
    relationFilter.otherSideObjectTypes = Java.to([], 'java.lang.String[]');
    relationPref.info = Java.to([relationFilter], 'com.teamcenter.services.strong.core._2007_06.DataManagement$RelationAndTypesFilter[]');
    var datasetsByRevision = {}; var datasets = {};
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
    var datasetValues = Object.keys(datasets).map(function (uid) { return datasets[uid]; });
    for (var dp = 0; dp < datasetValues.length; dp += batchSize)
      dm.getProperties(Java.to(datasetValues.slice(dp, dp + batchSize), 'com.teamcenter.soa.client.model.ModelObject[]'), Java.to(['ref_list'], 'java.lang.String[]'));
    var files = {};
    datasetValues.forEach(function (dataset) { modelObjects(dataset, 'ref_list').forEach(function (file) { if (file) files[String(file.getUid())] = file; }); });
    var fileValues = Object.keys(files).map(function (uid) { return files[uid]; });
    for (var fp = 0; fp < fileValues.length; fp += batchSize)
      dm.getProperties(Java.to(fileValues.slice(fp, fp + batchSize), 'com.teamcenter.soa.client.model.ModelObject[]'), Java.to(['original_file_name'], 'java.lang.String[]'));

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
    print(JSON.stringify({ ok: true, result: { nodes: resultNodes } }));
    exitCode = 0;
  }
} catch (error) {
  var message = String(error && error.message ? error.message : error);
  var marker = message.indexOf('AI00_CODE:');
  var code = marker >= 0 ? message.substring(marker + 10).replace(/\s.*$/, '') : 'teamcenter_worker_failed';
  java.lang.System.err.println(code);
  print(JSON.stringify({ ok: false, code: code }));
} finally {
  try { if (bomWindow && connection) StructureManagementService.getService(connection).closeBOMWindows(Java.to([bomWindow], 'com.teamcenter.soa.client.model.strong.BOMWindow[]')); } catch (ignoredClose) {}
  try { if (session) session.logout(); } catch (ignoredLogout) {}
  state.password = ''; state.user = '';
  if (connection) connection.release();
}
java.lang.System.exit(exitCode);
