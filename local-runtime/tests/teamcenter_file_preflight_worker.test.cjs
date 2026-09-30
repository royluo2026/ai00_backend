const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../src/Ai00.Connector.Adapters.VisMockup/teamcenter_readonly_worker.js'),'utf8');
function run(property){
 const object={getUid:()=> 'file',getTypeObject:()=>({isInstanceOf:()=>true}),getPropertyObject:name=>{
  if(name==='byte_size')return property;
  if(name==='file_size')return {getStringValue:()=> '551 Kb',getDisplayableValue:()=> '551 Kb'};
  return {getDisplayableValue:()=> 'part.jt'};
 }};
 const context={Java:{to:x=>x},serviceErrors:()=>[],fail:code=>{throw Error(code)},Number,String,
  observationTiming:()=>{},display:(o,name)=>String(o.getPropertyObject(name).getDisplayableValue()),
  dm:{loadObjects:()=>({sizeOfPlainObjects:()=>1,getPlainObject:()=>object}),getProperties:(_,names)=>{assert(names.includes('byte_size'));assert(!names.includes('file_size'));return {};}}};
 vm.createContext(context);
 for(const name of ['readCacheFilePreflight','fileByteSize']){
  const start=source.indexOf('function '+name+'(');assert(start>=0,name+' is missing');
  vm.runInContext(source.slice(start,source.indexOf('\nfunction ',start+1)),context);
 }
 return context.readCacheFilePreflight(context.dm,[{file_uid:'file',file_name:'part.jt'}]).files[0].file_size;
}
assert.equal(run({getStringValue:()=> '564224'}),564224);
assert.equal(run({getStringValue:()=> ' 2621440 '}),2621440);
assert.throws(()=>run({getStringValue:()=> '0'}),/teamcenter_file_size_invalid/);
assert.throws(()=>run({getStringValue:()=> ''}),/teamcenter_file_size_unavailable/);
assert.throws(()=>run({getStringValue:()=> '551 Kb'}),/teamcenter_file_size_unavailable/);
assert.throws(()=>run({getStringValue:()=> '1.5'}),/teamcenter_file_size_unavailable/);
assert.throws(()=>run({getStringValue:()=> '9007199254740992'}),/teamcenter_file_size_invalid/);
assert.throws(()=>run({getStringValue:()=>{throw Error('property not loaded');}}),/teamcenter_file_size_unavailable/);
console.log('Teamcenter preflight reads ImanFile.byte_size and rejects formatted file_size: PASS');
