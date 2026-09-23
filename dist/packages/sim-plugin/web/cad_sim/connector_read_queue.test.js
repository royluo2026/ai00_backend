const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'cad_sim.js'),'utf8');
function context(){
  const ctx=vm.createContext({window:{crypto:{randomUUID:()=> 'operation-uuid'}},document:{},setTimeout:fn=>setImmediate(fn)});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'cad_sim.js'),'utf8').split('let _connectorPairingApproval')[0],ctx);
  return ctx;
}
test('page entry waits for an explicit model open instead of attaching to an arbitrary VisMockup',()=>{
  const init=source.slice(source.indexOf('async function init()'),source.indexOf('function _applyTheme()'));
  assert.doesNotMatch(init,/_tryAutoConnect/);
  assert.doesNotMatch(init,/正在检测 VisMockup/);
  assert.match(init,/打开模型时启动专用 VisMockup/);
  const html=fs.readFileSync(path.join(__dirname,'index.html'),'utf8');
  assert.match(html,/id="btnLaunchVm"[^>]*hidden/);
  assert.match(html,/展开模型路径后点击“打开”/);
});
test('connector write requests carry a stable operation idempotency key while reads remain keyless',async()=>{
  const ctx=context();const calls=[];
  ctx._invokeCapability=async(id,payload,options)=>{calls.push({id,payload,options});return{operation_id:`op-${calls.length}`};};
  ctx._waitVisMockupCommand=async id=>id;
  await ctx._requestVisMockupCommand('simulation.vismockup.application.attach.request',{}, {confirmation:false});
  await ctx._requestVisMockupCommand('simulation.vismockup.document.identity.read.request',{}, {confirmation:false});
  assert.equal(calls[0].options.idempotencyKey,'simulation.vismockup.application.attach.request:operation-uuid');
  assert.equal(calls[1].options.idempotencyKey,undefined);
});
test('overlapping identity reads queue fresh plans instead of colliding or reusing old identity',async()=>{
  const ctx=context(); let active=false,calls=0,finish;
  ctx._invokeCapability=async()=>{if(active) throw Error('reconciliation_required');active=true;return{operation_id:++calls};};
  ctx._waitVisMockupCommand=id=>new Promise(resolve=>{finish=()=>{active=false;resolve(id);};});
  const one=ctx._requestVisMockupCommand('simulation.vismockup.document.identity.read.request',{}, {confirmation:false});
  const two=ctx._requestVisMockupCommand('simulation.vismockup.document.identity.read.request',{}, {confirmation:false});
  two.catch(()=>{});
  await new Promise(r=>setImmediate(r));
  assert.equal(calls,1); finish(); assert.equal(await one,1);
  await new Promise(r=>setImmediate(r)); assert.equal(calls,2); finish(); assert.equal(await two,2);
});
test('read failure releases queue and writes are never retried',async()=>{
  const ctx=context();let calls=0;
  ctx._invokeCapability=async id=>{calls++;throw Error(id.includes('tree.read')?'permission_denied':'reconciliation_required');};
  const id='simulation.vismockup.tree.read.request';
  await assert.rejects(ctx._requestVisMockupCommand(id),/permission_denied/);
  await assert.rejects(ctx._requestVisMockupCommand(id),/permission_denied/);
  await assert.rejects(ctx._requestVisMockupCommand('simulation.vismockup.node.visibility.change.request'),/reconciliation_required/);
  assert.equal(calls,3);
});
test('read admission waits out an older session, but never replays an admitted command',async()=>{
  const ctx=context();let calls=0;
  ctx._invokeCapability=async()=>{if(++calls===1) throw Error('reconciliation_required');return{operation_id:'fresh'};};
  ctx._waitVisMockupCommand=async id=>id;
  const id='simulation.vismockup.document.identity.read.request';
  assert.equal(await ctx._requestVisMockupCommand(id),'fresh');
  assert.equal(calls,2);
  ctx._waitVisMockupCommand=async()=>{throw Error('outcome_unknown');};
  await assert.rejects(ctx._requestVisMockupCommand(id),/outcome_unknown/);
  assert.equal(calls,3);
});
