const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../src/Ai00.Connector.Adapters.VisMockup/teamcenter_visualization_launch.js'),'utf8');
const context={Java:{type:()=>({}),to:x=>x,from:x=>Array.from(x)}};
vm.createContext(context);
vm.runInContext(source.slice(0,source.indexOf('var input=')),context);
const frame=(type,id,payload={})=>({type,generation:'1',request_id:id.repeat(32),payload});
const login=()=>frame('login','a',{endpoint_id:'tc-production',username:'u',password:'secret'});
function run(input,denied=false){
  const output=[],counts={logins:0,prepares:0,cleanups:0,logouts:0};
  assert.equal(typeof context.runSession,'function');
  context.runSession({read:()=>input.shift()||null,write:x=>output.push(JSON.parse(JSON.stringify(x)))},{
    login:()=>{counts.logins++;return {
      prepare:()=>{counts.prepares++;if(denied&&counts.prepares===2)throw Error('AI00_CODE:teamcenter_object_not_found');return {type:'material_ready',material_path:'controlled',expected_visdoc_uid:'',source_identity_hash:'hash'};},
      cleanup:()=>counts.cleanups++,logout:()=>counts.logouts++
    };},launchId:()=> 'tclaunch:test'
  });
  assert.ok(!JSON.stringify(output).includes('secret'));
  return {output,counts};
}
test('two requests share one login and clean each material before logout',()=>{
  const {output,counts}=run([login(),frame('consume','b'),frame('material_consumed','b'),frame('consume','c'),frame('material_consumed','c'),frame('logout','d')]);
  assert.deepEqual(counts,{logins:1,prepares:2,cleanups:2,logouts:1});
  assert.deepEqual(output.map(x=>x.type),['ready','material_ready','result','material_ready','result','closed']);
  assert.equal(output[4].payload.ok,true);
});
test('second source is resolved again and permission failure cannot reuse earlier material',()=>{
  const {output,counts}=run([login(),frame('consume','b'),frame('material_consumed','b'),frame('consume','c')],true);
  assert.equal(counts.prepares,2);assert.equal(counts.cleanups,2);
  assert.equal(output.at(-1).payload.code,'teamcenter_object_not_found');
});
for(const [name,ack] of [
  ['wrong id',frame('material_consumed','c')],['wrong generation',{...frame('material_consumed','b'),generation:'2'}],
  ['second consume',frame('consume','c')],['unknown fields',{...frame('material_consumed','b'),secret:'bad'}],['EOF',null]
])test(`invalid ack ${name} closes without replay`,()=>{
  const {output,counts}=run([login(),frame('consume','b'),ack,frame('consume','d')]);
  assert.equal(counts.prepares,1);assert.equal(counts.cleanups,1);assert.equal(counts.logouts,1);
  assert.equal(output.at(-1).payload.ok,false);
});
test('consumer failure never becomes a success',()=>{
  const {output,counts}=run([login(),frame('consume','b'),frame('material_failed','b')]);
  assert.equal(counts.prepares,1);assert.equal(output.at(-1).payload.code,'teamcenter_visualization_consumer_failed');
});
test('wire parser rejects duplicate, excessive depth and oversized frames',()=>{
  assert.equal(typeof context.parseFrameLine,'function');
  const valid=JSON.stringify(login());
  assert.equal(context.parseFrameLine('AI00_TC_VIS_V2:'+valid).type,'login');
  for(const value of [valid.replace('"type":"login"','"type":"consume","type":"login"'),
    valid.replace('"username":"u"','"username":"x","username":"u"'),
    JSON.stringify({...login(),payload:{x:'x'.repeat(65536)}}),
    '{"x":'.repeat(40)+'0'+'}'.repeat(40)])
    assert.throws(()=>context.parseFrameLine('AI00_TC_VIS_V2:'+value));
});
test('expired authentication stops requests and releases the session',()=>{
  const input=[login(),frame('consume','b'),frame('consume','c')],out=[];let released=0,prepared=0;
  context.runSession({read:()=>input.shift()||null,write:x=>out.push(x)},{login:()=>({
    prepare:()=>{prepared++;throw Error('AI00_CODE:teamcenter_session_expired');},cleanup:()=>{},logout:()=>released++
  })});
  assert.equal(prepared,1);assert.equal(released,1);assert.equal(out.at(-1).payload.code,'teamcenter_session_expired');
});
test('SDK connection reuses FMS but reloads source on every prepare and refuses reauthentication',()=>{
  let fmsCount=0,loads=0,logouts=0,manager;const removed=[];
  const jt={getUid:()=> 'file',getTypeObject:()=>({isInstanceOf:t=>t==='ImanFile'}),getPropertyObject:()=>({getDisplayableValue:()=> 'bolt.jt'})};
  const dataset={getUid:()=> 'dataset',getTypeObject:()=>({getName:()=> 'DirectModel'}),getPropertyObject:()=>({getModelObjectArrayValue:()=>[jt]})};
  const dm={loadObjects:ids=>{loads++;const obj=ids[0]==='dataset'?dataset:jt;return {sizeOfPartialErrors:()=>0,sizeOfPlainObjects:()=>1,getPlainObject:()=>obj};},getProperties:()=>({sizeOfPartialErrors:()=>0})};
  const p={toAbsolutePath:()=> 'temp.jt'};
  const classes={
    'java.lang.System':{nanoTime:()=>1,err:{println:()=>{}}},
    'com.teamcenter.soa.client.Connection':function(endpoint,credentials){manager=credentials;this.setApplicationName=()=>{};this.release=()=>{};this.getSender=()=>({invoke3:()=>({serviceData:{sizeOfPartialErrors:()=>0},vviStrBuffersOutputMap:{isEmpty:()=>false,values:()=>({iterator:()=>({next:()=> 'Operation=Open\nOperationStructure=None\nVisDoc_Type=DirectModel\nVisDoc_UID=dataset'})})}})});},
    'com.teamcenter.services.strong.core.SessionService':{getService:()=>({login:()=>{assert.deepEqual([...manager.getCredentials()].slice(0,2),['u','p']);return {user:{}};},logout:()=>logouts++})},
    'com.teamcenter.services.strong.core.DataManagementService':{getService:()=>dm},
    'com.teamcenter.services.rac.visualization._2013_05.DataManagement':{IdInfo2:function(){},SessionInfo2:function(){}},
    'com.teamcenter.services.rac.visualization._2011_02.DataManagement$ServerInfo':function(){},
    'com.teamcenter.services.rac.visualization._2011_02.DataManagement$UserAgentDataInfo':function(){},
    'com.teamcenter.soa.client.FileManagementUtility':function(){fmsCount++;this.getFiles=()=>({sizeOfPartialErrors:()=>0,sizeOfFiles:()=>1,getFile:()=>({toPath:()=>p})});},
    'java.nio.file.Paths':{get:()=>p},
    'java.nio.file.Files':{createDirectories:()=>{},createTempFile:()=>p,copy:()=>{},deleteIfExists:x=>removed.push(x)}
  };
  const ctx={Java:{type:name=>classes[name]||{},to:x=>x,from:x=>x,extend:(base,methods)=>function(){Object.assign(this,methods);}}};
  vm.createContext(ctx);vm.runInContext(source.slice(0,source.indexOf('var input=')),ctx);
  const sdk=ctx.loginSdk({username:'u',password:'p'});
  assert.throws(()=>manager.getCredentials(),/teamcenter_session_expired/);
  const payload={source_selector:{endpoint_id:'tc-production',object_uid:'source'},expected_visdoc_uid:'uid',source_identity_hash:'hash',material_root:'secured',visualization_operation:'Open'};
  sdk.prepare(payload);sdk.cleanup();sdk.prepare(payload);sdk.cleanup();sdk.logout();
  assert.equal(fmsCount,1);assert.equal(loads,6);assert.equal(removed.length,2);assert.equal(logouts,1);
});
