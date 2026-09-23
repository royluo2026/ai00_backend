const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../src/Ai00.Connector.Adapters.VisMockup/teamcenter_visualization_launch.js'),'utf8');
const timings=[];
let nanos=0;
const clock={nanoTime:()=>nanos+=1000000,err:{println:line=>timings.push(line)}};
const context={Java:{type:name=>name==='java.lang.System'?clock:{},to:x=>x,from:x=>Array.from(x)}};
vm.createContext(context);
vm.runInContext(source.slice(0,source.indexOf('var input=')),context);
test('phase timing preserves values and original errors without logging them',()=>{
  assert.equal(typeof context.timed,'function');
  timings.length=0;
  const value={secret:'must not log'};
  assert.equal(context.timed('login',()=>value),value);
  const failure=new Error('password secret');
  assert.throws(()=>context.timed('logout',()=>{throw failure;}),error=>error===failure);
  assert.deepEqual(timings.map(line=>JSON.parse(line.slice('AI00_TC_TIMING_V1:'.length))),[
    {phase:'login',elapsed_ms:1},{phase:'logout',elapsed_ms:1}
  ]);
});
test('FMS file lookup and transfer have separate numeric timings',()=>{
  timings.length=0;
  const file={getUid:()=> 'f',getTypeObject:()=>({isInstanceOf:()=>true})};
  const dm={loadObjects:()=>({sizeOfPartialErrors:()=>0,sizeOfPlainObjects:()=>1,getPlainObject:()=>file})};
  const failure=new Error('ticket secret');
  assert.throws(()=>context.downloadDirectModelFile(dm,{getFiles:()=>{throw failure;}},{file_uid:'f'}),e=>e===failure);
  assert.deepEqual(timings.map(line=>JSON.parse(line.slice('AI00_TC_TIMING_V1:'.length))),[
    {phase:'file_load',elapsed_ms:1},{phase:'fms_get_files',elapsed_ms:1}
  ]);
});
function service(names,returnedUid='dataset-1') {
  const files=names.map((name,i)=>({getUid:()=>`file-${i}`,getPropertyObject:key=>{assert.equal(key,'original_file_name');return {getDisplayableValue:()=>name};}}));
  const dataset={getUid:()=>returnedUid,getTypeObject:()=>({getName:()=> 'DirectModel',isInstanceOf:()=>false}),getPropertyObject:key=>{assert.equal(key,'ref_list');return {getModelObjectArrayValue:()=>files};}};
  return {loadObjects:ids=>{assert.deepEqual([...ids],['dataset-1']);return {sizeOfPartialErrors:()=>0,sizeOfPlainObjects:()=>1,getPlainObject:()=>dataset};},getProperties:()=>({sizeOfPartialErrors:()=>0})};
}
test('resolves only the launch dataset and its sole JT file',()=>{
  assert.equal(typeof context.resolveDirectModelFile,'function');
  assert.deepEqual(JSON.parse(JSON.stringify(context.resolveDirectModelFile(service(['readme.txt','bolt_01.jt']),'dataset-1'))),{dataset_uid:'dataset-1',file_uid:'file-1',file_name:'bolt_01.jt'});
});
test('rejects absent, ambiguous, mismatched and path-valued files',()=>{
  assert.equal(typeof context.resolveDirectModelFile,'function');
  for(const names of [[],['a.jt','b.jt'],['../a.jt']]) assert.throws(()=>context.resolveDirectModelFile(service(names),'dataset-1'));
  assert.throws(()=>context.resolveDirectModelFile(service(['a.jt'],'other'),'dataset-1'));
});

test('downloads the exact TC-resolved ImanFile through FMS',()=>{
  const file={getUid:()=> 'file-1',getTypeObject:()=>({isInstanceOf:type=>type==='ImanFile'})};
  const dm={loadObjects:ids=>{assert.deepEqual([...ids],['file-1']);return {sizeOfPartialErrors:()=>0,sizeOfPlainObjects:()=>1,getPlainObject:()=>file};}};
  const local={toPath:()=> 'fcc/bolt.jt'};
  const fms={getFiles:files=>{assert.deepEqual([...files],[file]);return {sizeOfPartialErrors:()=>0,sizeOfFiles:()=>1,getFile:()=>local};}};
  assert.equal(context.downloadDirectModelFile(dm,fms,{file_uid:'file-1'}),local);
  for(const count of [0,2]) assert.throws(()=>context.downloadDirectModelFile(dm,{getFiles:()=>({sizeOfPartialErrors:()=>0,sizeOfFiles:()=>count})},{file_uid:'file-1'}),/teamcenter_direct_model_download_failed/);
  assert.throws(()=>context.downloadDirectModelFile(dm,{getFiles:()=>({sizeOfPartialErrors:()=>1,sizeOfFiles:()=>1})},{file_uid:'file-1'}),/teamcenter_direct_model_download_failed/);
});
