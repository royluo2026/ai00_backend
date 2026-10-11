const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{JSDOM}=require('jsdom');
const {createPanel,stateOf}=require('./debug');
test('pending native and batch document closes never report successful completion',()=>{
 for(const stage of ['document_close_pending','document_close_bulk_completed'])assert.equal(stateOf({stage,detail:{status:'pending'}}),'info');
 assert.equal(stateOf({stage:'document_close_completed',detail:{status:'closed'}}),'success');
 assert.equal(stateOf({stage:'document_close_bulk_completed',detail:{status:'failed'}}),'error');
});
test('confirmation challenges render as info while true failures and unverified caches keep their state',()=>{
 for(const stage of ['gateway_capability_failed','gateway_capability_awaiting_confirmation'])assert.equal(stateOf({stage,detail:{status:'rejected',error_code:'confirmation_required'}}),'info');
 for(const error_code of ['scope_denied','confirmation_mismatch','confirmation_failed'])assert.equal(stateOf({stage:'gateway_capability_failed',detail:{error_code}}),'error');
 assert.equal(stateOf({stage:'projection_accepted',detail:{cache_state:'unverified',verified:false}}),'unknown');
 assert.equal(stateOf({stage:'gateway_capability_completed',detail:{status:'failed'}}),'error');
});

test('timeline labels confirmation challenges and failed step IDs in collapsed rows',async()=>{
 const dom=new JSDOM(fs.readFileSync(path.join(__dirname,'debug.html'),'utf8')),d=dom.window.document;
 const events=[{id:'a',timestamp:'2026-09-28T01:00:00Z',source:'Main',stage:'gateway_capability_failed',detail:{error_code:'confirmation_required'}},{id:'b',timestamp:'2026-09-28T01:00:01Z',source:'Main',stage:'gateway_capability_failed',detail:{status:'failed',failed_step_id:'identity',error_code:'document_identity_unavailable'}}];
 const panel=createPanel({document:d,api:{read:async()=>({events,sources:[]})},schedule:()=>1,cancel:()=>{}});
 await panel.refresh();const rows=d.querySelectorAll('summary');assert.match(rows[0].textContent,/等待用户确认/);assert.equal(d.querySelector('.event').className,'event info');assert.match(rows[1].textContent,/失败步骤 identity/);
 panel.dispose();dom.window.close();
});
test('broader document scope warning remains visible in errors filter and correlates the user choice',async()=>{
 const dom=new JSDOM(fs.readFileSync(path.join(__dirname,'debug.html'),'utf8')),d=dom.window.document;
 const events=[{id:'warning',timestamp:new Date().toISOString(),source:'Main',stage:'source_scope_mismatch',detail:{intent_id:'open-1',level:'warn',error_code:'document_open_scope_broader_than_selection',expected:'selected_subtree',observed:'document',capability_id:'simulation.teamcenter.visualization.launch.request',capability_version:2}},{id:'choice',timestamp:new Date().toISOString(),source:'Main',stage:'source_scope_choice',detail:{intent_id:'open-1',action:'cancel',status:'cancelled'}}];
 const panel=createPanel({document:d,api:{read:async()=>({events,sources:[]})},schedule:()=>1,cancel:()=>{}});
 await panel.refresh();d.getElementById('search').value='document_open_scope_broader_than_selection';d.getElementById('filter').value='errors';d.getElementById('search').dispatchEvent(new dom.window.Event('input'));
 assert.equal(d.querySelectorAll('.event').length,2);assert.match(d.querySelector('summary').textContent,/所属文档与显隐校准说明/);assert.equal(d.querySelector('.mark').textContent,'?');
 assert.match(d.querySelector('pre').textContent,/selected_subtree/);panel.dispose();dom.window.close();
});

test('capability search keeps asynchronous operation and trace failures and discloses hidden errors',async()=>{
 const dom=new JSDOM(fs.readFileSync(path.join(__dirname,'debug.html'),'utf8')),d=dom.window.document;
 const capability='simulation.teamcenter.product_structure.children.read.request';
 const row=(id,stage,detail)=>({id,stage,detail,source:'页面',timestamp:'2026-09-28T03:06:11Z'});
 const events=[row('start','tc_page_started',{capability_id:capability,trace_id:'t1'}),row('accepted','capability_completed',{capability_id:capability,operation_id:'op1'}),row('step','command_step',{operation_id:'op1',error_code:'teamcenter_parent_path_not_found'}),row('failed','tc_page_failed',{trace_id:'t1',error_code:'teamcenter_parent_path_not_found'}),row('other','tc_page_failed',{trace_id:'t2',error_code:'unrelated_failure'})];
 const panel=createPanel({document:d,api:{read:async()=>({events,sources:[]})},schedule:()=>1,cancel:()=>{}});
 await panel.refresh();d.getElementById('search').value=capability;d.getElementById('search').dispatchEvent(new dom.window.Event('input'));
 assert.deepEqual([...d.querySelectorAll('.event')].map(e=>e.dataset.eventId),['start','accepted','step','failed']);
 assert.match(d.getElementById('summary').textContent,/筛选隐藏 1 条错误/);
 d.getElementById('filter').value='errors';d.getElementById('filter').dispatchEvent(new dom.window.Event('change'));
 assert.deepEqual([...d.querySelectorAll('.event')].map(e=>e.dataset.eventId),['step','failed']);
 d.getElementById('resetFilters').click();assert.equal(d.querySelectorAll('.event').length,5);assert.equal(d.getElementById('search').value,'');assert.equal(d.getElementById('filter').value,'all');
 panel.dispose();dom.window.close();
});

test('collapsed steps expose the real capability version and operation, and identify local cache processing',async()=>{
 const dom=new JSDOM(fs.readFileSync(path.join(__dirname,'debug.html'),'utf8')),d=dom.window.document;
 const events=[{id:'a',timestamp:'2026-09-28T01:00:00Z',source:'Main',stage:'gateway_capability_completed',detail:{capability_id:'simulation.teamcenter.visualization.launch.request',capability_version:2,operation_id:'op-1'}},{id:'b',timestamp:'2026-09-28T01:00:01Z',source:'页面',stage:'projection_lookup',detail:{}}];
 const panel=createPanel({document:d,api:{read:async()=>({events,sources:[]})},schedule:()=>1,cancel:()=>{}});
 await panel.refresh();const rows=d.querySelectorAll('summary');
 assert.match(rows[0].textContent,/simulation\.teamcenter\.visualization\.launch\.request @ v2/);assert.match(rows[0].textContent,/操作 op-1/);assert.match(rows[1].textContent,/本地处理/);
 d.getElementById('search').value='op-1';d.getElementById('search').dispatchEvent(new dom.window.Event('input'));assert.equal(d.querySelectorAll('.event').length,1);
 panel.dispose();dom.window.close();
});
test('debug timeline safely shows steps, filters errors, preserves open detail and copies the filtered view',async()=>{
 const dom=new JSDOM(fs.readFileSync(path.join(__dirname,'debug.html'),'utf8'));
 const d=dom.window.document,events=[{id:'a',timestamp:'2026-09-28T01:00:00Z',source:'Main',stage:'request_started',detail:{action:'show'}},{id:'b',timestamp:'2026-09-28T01:00:01Z',source:'页面',stage:'tc_page_rejected',detail:{error_code:'generation_mismatch',message:'<img src=x onerror=evil()>'}},{id:'c',timestamp:'2026-09-28T01:00:02Z',source:'Connector',stage:'native_cache_hit',detail:{cache_state:'verifying'}}];
 let copied;const panel=createPanel({document:d,api:{read:async()=>({events,sources:[{source:'Main',state:'ready'}]}),copy:async text=>{copied=text;}},schedule:()=>1,cancel:()=>{}});
 await panel.refresh();assert.equal(d.querySelectorAll('.event').length,3);assert.equal(d.querySelectorAll('img').length,0);
 d.querySelector('.event').open=true;await panel.refresh();assert.equal(d.querySelector('.event').open,true);
 d.getElementById('filter').value='errors';d.getElementById('filter').dispatchEvent(new dom.window.Event('change'));assert.equal(d.querySelectorAll('.event').length,2);
 d.getElementById('copy').click();await Promise.resolve();assert.match(copied,/generation_mismatch/);assert.doesNotMatch(copied,/request_started/);
 assert.equal(stateOf(events[2]),'unknown');panel.dispose();dom.window.close();
});
