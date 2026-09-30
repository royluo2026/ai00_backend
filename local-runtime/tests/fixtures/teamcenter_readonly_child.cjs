const readline=require('node:readline');let lines=0,count=0;const mode=process.argv[2]||'normal';
readline.createInterface({input:process.stdin}).on('line',line=>{
  if(++lines<=2)return;
  const request=JSON.parse(line);count++;
  if(mode==='exit')process.exit(23);
  if(mode==='hang')return;
  const frame=mode==='expire'?{ok:false,code:'teamcenter_session_expired'}:{ok:true,result:{count,command:request.command}};
  if(request.command==='cache_file'&&frame.result)frame.result.file_ref=request.payload.file_ref;
  if(mode==='bulk-large'){
    const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
    const source=fs.readFileSync(path.join(__dirname,'teamcenter_readonly_worker.js'),'utf8');
    const paths=request.payload.occurrence_paths,revision={getUid:()=> 'rev'},context={
      Java:{to:x=>x},structureKey:JSON.stringify,structureNodes:Object.fromEntries(paths.map(p=>[JSON.stringify(p),{line:{},revision}])),
      captureCacheStructure:()=>{},structureProperties:()=>{},observationTiming:()=>{},fail:code=>{throw Error(code)},
      cachePreparedRevisions:{},cacheRevisionGeometry:{},dm:{getProperties:()=>({})},readGeometryReferences:()=>()=>[],
      readNodeProperties:()=>({properties:{name:'Part'},raw_fields:[{field:'large',value_json:JSON.stringify('值"\\'.repeat(100000))}]})};
    vm.createContext(context);
    vm.runInContext(source.match(/var cacheSpatialProperties=\[[^;]+;/)[0],context);
    vm.runInContext(source.slice(source.indexOf('function utf8Bytes('),source.indexOf('function readGeometryReferences(')),context);
    frame.result={rows:context.readCachePropertyBatch({},revision,paths)};
  }
  frame.request_id=mode==='wrong-id'?'incorrect':request.request_id;
  process.stdout.write('AI00_TC_READ_V1:'+JSON.stringify(frame)+'\n');
});
