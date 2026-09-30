const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const script=fs.readFileSync(path.resolve(__dirname,'../src/Ai00.Connector.Adapters.VisMockup/teamcenter_readonly_worker.js'),'utf8');
function run(commands,mutateOnReopen=false){
  const counts={login:0,logout:0,bom:0,close:0,expands:[],loads:0,policies:[],policyRegistrations:0};
  const object=(uid,fields={})=>({getUid:()=>uid,getTypeObject:()=>({getName:()=> 'Part'}),getPropertyObject:name=>({getDisplayableValue:()=>fields[name]??'',getModelObjectValue:()=>fields[name]??null})});
  const revision=object('rev',{item_id:'ITEM'}),root=object('root'),a=object('a',{bl_occurrence_uid:'A',bl_line_name:'A'}),b=object('b',{bl_occurrence_uid:'B',bl_line_name:'B'}),leaf=object('leaf',{bl_occurrence_uid:'L',bl_line_name:'L'}),rule=object('rule',{object_name:'Latest Working'});
  const children={root:[a,b],a:[leaf],b:[],leaf:[]};
  const sd={sizeOfPlainObjects:()=>1,getPlainObject:()=>revision,sizeOfUpdatedObjects:()=>0};
  const dm={loadObjects:()=>{counts.loads++;return sd},getProperties:()=>({})};
  const structure={getRevisionRules:()=>({output:[{revRule:rule}]}),createBOMWindows:()=>{counts.bom++;if(mutateOnReopen&&counts.bom===2)children.root.push(object('new',{bl_occurrence_uid:'NEW'}));return {output:[{bomLine:root,bomWindow:{}}]}},closeBOMWindows:()=>{counts.close++},expandPSOneLevel:info=>{const line=info.parentBomLines[0];counts.expands.push(line.getUid());return {output:[{parent:{bomLine:line},children:children[line.getUid()].map(line=>({bomLine:line,objectOfBOMLine:revision}))}]};},expandPSAllLevels:()=>{counts.expands.push('all');return {output:Object.entries(children).filter(([,v])=>v.length).map(([uid,nodes])=>({parent:{bomLine:[root,a,b,leaf].find(line=>line.getUid()===uid),objectOfBOMLine:revision},children:nodes.map(bomLine=>({bomLine,objectOfBOMLine:revision}))}))};}};
  const lines=['user','secret',...commands.map((c,i)=>JSON.stringify({...c,keep_session:true,request_id:String(i+1).padStart(32,'0')}))],outputs=[];
  function Dummy(){}
  const types={'java.util.UUID':{randomUUID:()=> '12345678-1234-1234-1234-123456789abc'},'java.io.BufferedReader':function(){return {readLine:()=>lines.length?lines.shift():null}},'com.teamcenter.soa.client.Connection':function(){this.setApplicationName=()=>{};this.release=()=>{}},'com.teamcenter.services.strong.core.SessionService':{getService:()=>({login:()=>{counts.login++;return {user:{}}},logout:()=>{counts.logout++}})},'com.teamcenter.services.strong.core.DataManagementService':{getService:()=>dm},'com.teamcenter.services.strong.cad.StructureManagementService':{getService:()=>structure},'java.time.OffsetDateTime':{parse:()=>({toZonedDateTime:()=>({})})},'java.util.GregorianCalendar':{from:()=>({})}};
  types['com.teamcenter.soa.client.Connection']=function(){this.setApplicationName=()=>{};this.release=()=>{};this.getCurrentObjectPropertyPolicy=()=> 'normal-policy';this.setObjectPropertyPolicy=name=>counts.policies.push(name)};
  types['com.teamcenter.services.strong.core.SessionService']={getService:()=>({login:()=>{counts.login++;return {user:{}}},logout:()=>{counts.logout++},setObjectPropertyPolicy:policy=>{counts.policyRegistrations++;assert.deepEqual(Array.from(policy.names),['bl_occurrence_uid','bl_revision']);assert.equal(policy.withProperties,false);assert.equal(policy.excludeParentProperties,true);return 'cache-policy'}})};
  types['com.teamcenter.soa.common.ObjectPropertyPolicy']=function(){this.addType=(name,fields)=>{assert.equal(name,'BOMLine');this.names=fields};this.getType=()=>({setModifier:(key,value)=>this[key]=value});this.setModifier=(key,value)=>this[key]=value};
  types['com.teamcenter.soa.common.PolicyProperty']={WITH_PROPERTIES:'withProperties',EXCLUDE_MODIFIABLE:'excludeIsModifiable',EXCLUDE_PARENT_PROPERTIES:'excludeParentProperties'};
  const context={Java:{type:name=>types[name]||Dummy,to:x=>x,from:x=>x,extend:()=>Dummy},java:{lang:{System:{in:{},err:{println:()=>{}},exit:()=>{}}}},print:text=>outputs.push(String(text))};
  vm.runInNewContext(script,context);
  const results=outputs.map(text=>JSON.parse(text.replace(/^AI00_TC_READ_V1:/,'')));
  return {counts,results};
}
const selector={endpoint_id:'tc-production',object_uid:'item',item_revision_uid:'rev',bom_view_uid:'',revision_rule:'Latest Working',configuration_date:'2026-09-28T08:00:00Z'};
const edge=occurrence_uid=>({occurrence_uid,item_revision_uid:'rev'});
const children=(parent_path=[],source_selector=selector,refresh=false)=>({command:'children',payload:{source_selector,parent_path,refresh}});
test('multiple node tasks reuse login, BOM and exact occurrence paths; restart can locate an unseen path',()=>{
  const {counts,results}=run([children(),children([edge('A')]),children([edge('A'),edge('L')]),{command:'node_properties',payload:{source_selector:selector,occurrence_path:[edge('B')]}},children([edge('B')])]);
  assert.equal(results.length,5,'all tasks complete without restarting the worker');assert(results.every(r=>r.ok),JSON.stringify(results));
  assert.equal(counts.login,1);assert.equal(counts.bom,1);assert.equal(counts.loads,1);assert.equal(counts.logout,1);assert.equal(counts.close,1);
  assert.deepEqual(counts.expands,['root','a','leaf','b'],'no repeated ancestors, including when reading properties');
  assert.equal(results[1].result.parent.occurrence_path[0].occurrence_uid,'A');assert.equal(results[3].result.occurrence_uid,'B','same revision does not merge separate instances');
  const resumed=run([children([edge('A'),edge('L')])]);assert(resumed.results[0].ok);assert.deepEqual(resumed.counts.expands,['root','a','leaf']);
});
test('source selector change resets BOM and locator; invalid occurrence cannot reuse a nearby node',()=>{
  const changed={...selector,configuration_date:'2026-09-29T08:00:00Z'};
  const {counts,results}=run([children(),children([],changed),children([edge('missing')],changed)]);
  assert.equal(results.length,3);assert.equal(counts.login,1);assert.equal(counts.bom,2);assert.equal(counts.close,2);assert.deepEqual(counts.expands,['root','root']);
  assert.equal(results[2].ok,false);assert.equal(results[2].code,'teamcenter_parent_path_not_found');
});
test('explicit cloud refresh reopens BOM and reads changed TC children',()=>{
  const {counts,results}=run([children(),children([],selector,true)],true);
  assert.equal(results.length,2);assert(results.every(r=>r.ok));assert.equal(results[0].result.nodes.length,2);assert.equal(results[1].result.nodes.length,3);
  assert.equal(counts.login,1);assert.equal(counts.bom,2);assert.deepEqual(counts.expands,['root','root']);
});
test('bulk private commands reuse a configured window and refuse pages from another generation',()=>{
  const token='12345678123412341234123456789abc';
  const {counts,results}=run([{command:'cache_structure',payload:{source_selector:selector,capture_key:'a'.repeat(32)}},{command:'cache_structure_page',payload:{source_selector:selector,native_generation:token,cursor:0,page_size:200}},{command:'cache_structure_page',payload:{source_selector:{...selector,configuration_date:'2026-09-29T08:00:00Z'},native_generation:token,cursor:0,page_size:200}}]);
  assert.equal(results.length,3);assert.equal(results[0].ok,true,JSON.stringify(results));assert.equal(results[0].result.node_count,4);assert.equal(results[1].result.nodes.length,4);
  assert.equal(results[2].ok,false);assert.equal(results[2].code,'teamcenter_cache_generation_stale');assert.equal(counts.login,1);assert.deepEqual(counts.expands,['all']);
});
test('each new capture key reopens the same selector and sees changed topology without another login',()=>{
  const capture=key=>({command:'cache_structure',payload:{source_selector:selector,capture_key:key.repeat(32)}});
  const {counts,results}=run([capture('a'),capture('a'),capture('b')],true);
  assert(results.every(r=>r.ok),JSON.stringify(results));
  assert.deepEqual(results.map(r=>r.result.node_count),[4,4,5]);
  assert.equal(counts.login,1);assert.equal(counts.bom,2);assert.deepEqual(counts.expands,['all','all']);
});
test('bulk policy limits automatic properties and restores the previous policy for normal reads',()=>{
  const capture={command:'cache_structure',payload:{source_selector:selector,capture_key:'a'.repeat(32)}};
  const {counts,results}=run([capture,capture,children()]);
  assert(results.every(r=>r.ok),JSON.stringify(results));
  assert.equal(counts.policyRegistrations,1);
  assert.deepEqual(counts.policies,['cache-policy','cache-policy','normal-policy']);
  assert.deepEqual(counts.expands,['all','root'],'normal reads must build a fresh strict locator');
});
