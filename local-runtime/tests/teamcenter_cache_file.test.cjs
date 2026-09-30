const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const script=fs.readFileSync(path.resolve(__dirname,'../src/Ai00.Connector.Adapters.VisMockup/teamcenter_readonly_worker.js'),'utf8');
test('fixed JT fetch loads only the exact ImanFile, preserves failure and never traverses BOM',()=>{
 const start=script.indexOf('function readCacheFile(');assert.ok(start>=0,'native fixed file reader exists');
 const calls=[],file={getUid:()=> 'fixed-file',getTypeObject:()=>({isInstanceOf:t=>t==='ImanFile'})};
 const target={toAbsolutePath:()=>({toString:()=>'/managed/file.jt'})};
 const context={Java:{to:x=>x,type:name=>name==='java.nio.file.Files'?{createTempFile:()=>target,copy:()=>{},size:()=>32,deleteIfExists:()=>{}}:name==='java.nio.file.Paths'?{get:()=> '/managed'}:{REPLACE_EXISTING:'replace'}},
   serviceErrors:d=>d.errors||[],display:()=> 'fixed.jt',fail:c=>{throw Error(c)}};
 vm.createContext(context);vm.runInContext(script.slice(start,script.indexOf('\nfunction fail(',start)),context);
 const dm={loadObjects:uids=>{calls.push([...uids]);return {sizeOfPlainObjects:()=>1,getPlainObject:()=>file}},getProperties:()=>({})};
 const fms={getFiles:files=>({sizeOfFiles:()=>1,getFile:()=>({toPath:()=>'/tc/fixed'})})};
 const result=context.readCacheFile(dm,fms,{file_uid:'fixed-file',file_name:'fixed.jt'},'/managed');
 assert.deepEqual(calls,[['fixed-file']]);assert.equal(result.byte_size,32);assert.equal(result.local_path,'/managed/file.jt');
 dm.loadObjects=()=>({errors:[{code:214000}]});assert.throws(()=>context.readCacheFile(dm,fms,{file_uid:'fixed-file',file_name:'fixed.jt'},'/managed'),/teamcenter_file_unavailable/);
});
