const fs=require('node:fs'),path=require('node:path'),readline=require('node:readline');
const mode=process.argv[2]||'normal',prefix='AI00_TC_VIS_V2:';
let pending,count=0,logins=0;
function send(request,type,payload){process.stdout.write(prefix+JSON.stringify({type,generation:request.generation,request_id:request.request_id,payload})+'\n');}
readline.createInterface({input:process.stdin}).on('line',line=>{
 const request=JSON.parse(line.slice(prefix.length));
 if(request.type==='login'){
  if(++logins!==1)process.exit(8);
  if(mode==='oversize'){process.stdout.write(prefix+'x'.repeat(70000)+'\n');return;}
  if(mode==='duplicate'){process.stdout.write(prefix+'{"type":"ready","type":"ready","generation":"1","request_id":"'+request.request_id+'","payload":{}}\n');return;}
  if(mode==='wrong-id'){request.request_id='f'.repeat(32);}
  if(mode==='wrong-generation'){request.generation='999';}
  if(mode==='noise'){
   process.stdout.write('x'.repeat(2*1024*1024)+'\n');
   for(let i=0;i<100;i++)process.stderr.write('password secret\nAI00_TC_TIMING_V1:{"phase":"login","elapsed_ms":1}\n');
  }
  send(request,'ready',{});
  if(mode==='unsolicited')for(let i=0;i<32;i++)send(request,'ready',{});
  if(mode==='idle-crash')setTimeout(()=>process.exit(9),50);
  return;
 }
 if(request.type==='logout'){if(mode==='ignore-logout')return;send(request,'closed',{});process.exit(0);}
 if(request.type==='consume'){
  count++;pending=request;
  if(mode==='crash-before')process.exit(9);
  if(mode==='hang-before')return;
  const material=path.join(request.payload.material_root,'model.jt');fs.writeFileSync(material,'JT');
  send(request,'material_ready',{type:'material_ready',material_path:material,expected_visdoc_uid:request.payload.expected_visdoc_uid,source_identity_hash:request.payload.source_identity_hash});return;
 }
 if(request.type==='material_consumed'||request.type==='material_failed'){
  if(mode==='crash-after')process.exit(9);
  if(mode==='hang-after')return;
  if(mode==='late'){pending.generation='0';}
  send(pending,'result',request.type==='material_failed'?{ok:false,code:'teamcenter_visualization_consumer_failed'}:{ok:true,result:{launch_id:'tclaunch:'+String(count).padStart(64,'0'),runner_started:true,expected_visdoc_uid:pending.payload.expected_visdoc_uid,source_identity_hash:pending.payload.source_identity_hash}});
 }
}).on('close',()=>{if(mode==='ignore-logout')setInterval(()=>{},1000);else process.exit(0);});
