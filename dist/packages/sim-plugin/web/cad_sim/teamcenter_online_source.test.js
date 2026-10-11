const assert = require('node:assert/strict');
require('./teamcenter_online_source.js');

(async () => {
  const calls = [];
  const nodes = [{ occurrence_id:'a',parent_occurrence_id:null,depth:0,child_order:0,name:'Root',item_uid:'i',item_id:'A',item_revision_uid:'r',revision_id:'01',component_type:'Assembly',owning_user:'u',owning_group:'g',transform:null,bbox:null,geometry_refs:[] }];
  const invoke = async (id, payload) => {
    calls.push([id,payload]);
    if (id.endsWith('online_source.bind')) return {source_gid:'11',document_gid:'12',source_identity_hash:'sha256:'+'c'.repeat(64)};
    if (id.endsWith('observation.begin')) return {observation_gid:'13'};
    if (id.endsWith('snapshot.page.get')) return {observation_id:payload.observation_id,cursor:0,next_cursor:null,nodes,node_count:1};
    return {};
  };
  const requestConnector = async id => id.includes('.observe.')
    ? {steps:[{result:{observation_id:'tcobs:'+'a'.repeat(64),source_identity_hash:'sha256:'+'c'.repeat(64),captured_at:'2026-09-16T00:00:00Z',node_count:1,page_count:1,complete:true}}]}
    : {steps:[{result:{observation_id:'tcobs:'+'a'.repeat(64),cursor:0,next_cursor:null,nodes,page_hash:'sha256:'+'b'.repeat(64)}}]};
  const source={display_name:'Tool2025',insertion_instance_id:'insert-1',source_selector:{endpoint_id:'tc-production',object_uid:'o',item_revision_uid:'r',bom_view_uid:'b',revision_rule:'Latest Working',configuration_date:'2026-09-16T00:00:00Z'}};
  const result=await globalThis.AI00TeamcenterOnlineSource.observeAndPersist({invoke,requestConnector,workspace:{workspace_gid:'10',row_version:2},source});
  assert.equal(result.document_gid,'12');
  assert.deepEqual(calls.map(item=>item[0]),['simulation.environment.online_source.bind','simulation.product_structure.observation.begin','simulation.product_structure.observation.page.append','simulation.product_structure.observation.publish']);
  const tree=await globalThis.AI00TeamcenterOnlineSource.readSnapshot(invoke,'tcobs:'+'a'.repeat(64));
  assert.equal(tree.nodes[0].node_key,'tc:a'); assert.equal(tree.nodes[0].revision,'01');
  const matches=await globalThis.AI00TeamcenterOnlineSource.search(async()=>({steps:[{result:{items:[{display_name:'A/01'}]}}]}),{
    endpoint_id:'tc-production',query:'A',revision_id:'01',revision_rule:'Latest Working',configuration_date:'2026-09-16T00:00:00Z',limit:20});
  assert.equal(matches[0].display_name,'A/01');
  const propertyCalls=[];
  const document={source_selector:source.source_selector};
  const node={occurrence_path:[{occurrence_uid:'occ-1',item_revision_uid:'rev-1'}]};
  const properties=await globalThis.AI00TeamcenterOnlineSource.readNodeProperties(async(...args)=>{
    propertyCalls.push(args);
    return {steps:[{result:{source_identity_hash:'sha256:'+'d'.repeat(64),captured_at:'2026-09-17T00:00:00Z',cache_hit:true,properties:{name:'A'}}}]};
  },document,node);
  assert.equal(propertyCalls[0][0],'simulation.teamcenter.node_properties.read.request');
  assert.deepEqual(propertyCalls[0][1],{source_selector:document.source_selector,occurrence_path:node.occurrence_path});
  assert.deepEqual(propertyCalls[0][2],{confirmation:false,waitAttempts:750});
  assert.equal(properties.cache_hit,true);
  let revisionRuleRequests=0;
  const requestRevisionRules=async()=>{revisionRuleRequests+=1;return {steps:[{result:{rules:['Latest Working','Latest Released']}}]};};
  const rules=await globalThis.AI00TeamcenterOnlineSource.revisionRules(requestRevisionRules);
  assert.deepEqual(rules,['Latest Working','Latest Released']);
  assert.deepEqual(globalThis.AI00TeamcenterOnlineSource.cachedRevisionRules(),rules);
  assert.deepEqual(await globalThis.AI00TeamcenterOnlineSource.revisionRules(requestRevisionRules),rules);
  assert.equal(revisionRuleRequests,1,'revision rules should be read only once per Teamcenter login session');
  globalThis.AI00TeamcenterOnlineSource.clearRevisionRules();
  assert.equal(globalThis.AI00TeamcenterOnlineSource.cachedRevisionRules(),null);
  await globalThis.AI00TeamcenterOnlineSource.revisionRules(requestRevisionRules);
  assert.equal(revisionRuleRequests,2,'a new Teamcenter login session should read rules again');
  const actions=[];
  const connector=async(id,payload)=>{actions.push([id,payload]);return {steps:[{result:{launch_id:'x'}}]};};
  await globalThis.AI00TeamcenterOnlineSource.openOnline(connector,source,'new');
  await globalThis.AI00TeamcenterOnlineSource.openOnline(connector,source,'insert');
  assert.deepEqual(actions.map(item=>item[0]),[
    'simulation.teamcenter.visualization.launch.request','simulation.teamcenter.visualization.insert.request']);
  const cached=[];
  await globalThis.AI00TeamcenterOnlineSource.openOnline(async(...args)=>{cached.push(args);return{};},source,'new',
    {batch_id:'a'.repeat(32),node_key:'occ-1'});
  await globalThis.AI00TeamcenterOnlineSource.openOnline(async(...args)=>{cached.push(args);return{};},source,'insert',
    {batch_id:'a'.repeat(32),node_key:'occ-1'});
  assert.deepEqual(cached.map(([,payload,options])=>[payload,options.version]),[
    [{cache_source:{batch_id:'a'.repeat(32),node_key:'occ-1'},expected_visdoc_uid:''},3],
    [{cache_source:{batch_id:'a'.repeat(32),node_key:'occ-1'},expected_visdoc_uid:''},2],
  ]);
  console.log('teamcenter_online_source tests passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
