const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {JSDOM}=require('jsdom');
const tick=()=>new Promise(r=>setImmediate(r));
test('groups by project identity and data version across pages without losing selection or collapse state',async()=>{
 const dom=new JSDOM('',{runScripts:'outside-only'});dom.window.eval(fs.readFileSync(path.join(__dirname,'cache_snapshot_picker.js'),'utf8'));
 const batch=(id,project,version)=>({batch_id:id,project_gid:project,project_name:'同名项目',display_name:version,status:'completed',phase:'SOP'});
 const a=batch('a','1','v1'),b=batch('b','1','v2'),c=batch('c','2','v1'),e=batch('e','1','v1');let pages=0;
 const invoke=async(id,p)=>id.endsWith('.list')?{batches:++pages===1?[a,b,c]:[a,e],next_cursor:pages===1?3:null}:{identity:{batch_id:p.batch_id},manifest:{node_count:1}};
 try{
  const overlay=await dom.window.AI00CacheSnapshotPicker.open({invoke,workspace:{workspace_gid:'10'},isCurrent:()=>true,onAdded:()=>{}});
  const projects=overlay.querySelectorAll('.cs-cache-project');assert.equal(projects.length,2);
  const versions=projects[0].querySelectorAll('.cs-cache-version');assert.equal(versions.length,2);assert.match(versions[0].querySelector('summary').textContent,/v1/);
  overlay.querySelector('[data-batch="a"]').click();await tick();versions[0].open=false;
  overlay.querySelector('[data-more]').click();await tick();
  assert.equal(overlay.querySelectorAll('.cs-cache-project').length,2);assert.equal(versions[0].querySelectorAll('[data-batch]').length,2);assert.equal(versions[0].open,false);assert.equal(overlay.querySelectorAll('[data-batch]').length,4);
  assert.equal(overlay.querySelector('[data-batch="a"]').getAttribute('aria-pressed'),'true');
  overlay.querySelector('[data-batch="c"]').click();await tick();assert.equal(overlay.querySelectorAll('[aria-pressed="true"]').length,1);assert.equal(overlay.querySelector('[data-batch="a"]').getAttribute('aria-pressed'),'false');
 }finally{dom.window.close();}
});
test('selection is visible immediately, survives pagination and ignores stale validation',async()=>{
 const dom=new JSDOM('',{runScripts:'outside-only'});dom.window.eval(fs.readFileSync(path.join(__dirname,'cache_snapshot_picker.js'),'utf8'));
 const batches=['a','b'].map((id,i)=>({batch_id:id.repeat(32),status:'completed',project_name:'W10',display_name:`v${i+1}`,completed_at:`2026-09-2${i+1}`}));
 const pending={};let lists=0;
 const invoke=async(id,p)=>id.endsWith('.list')?{batches:++lists===1?batches:[],next_cursor:lists===1?2:null}:new Promise((resolve,reject)=>{pending[p.batch_id]={resolve,reject};});
 try{
  const overlay=await dom.window.AI00CacheSnapshotPicker.open({invoke,workspace:{workspace_gid:'10'},isCurrent:()=>true,onAdded:()=>{}});
  const rows=overlay.querySelectorAll('[data-batch]'),add=overlay.querySelector('[data-add]'),summary=overlay.querySelector('[data-selection]');
  rows[0].click();assert.equal(rows[0].getAttribute('aria-pressed'),'true');assert.equal(rows[0].classList.contains('selected'),true);assert.equal(add.disabled,true);assert.match(summary.textContent,/W10.*v1.*2026-09-21/);
  rows[1].click();assert.equal(rows[0].getAttribute('aria-pressed'),'false');assert.equal(rows[1].getAttribute('aria-pressed'),'true');assert.match(summary.textContent,/v2/);
  pending[batches[0].batch_id].resolve({identity:{batch_id:batches[0].batch_id},manifest:{node_count:1}});await tick();assert.equal(add.disabled,true);
  pending[batches[1].batch_id].resolve({identity:{batch_id:batches[1].batch_id},manifest:{node_count:2}});await tick();assert.equal(add.disabled,false);
  const status=overlay.querySelector('[data-status]').textContent;overlay.querySelector('[data-more]').click();await tick();assert.equal(overlay.querySelector('[data-status]').textContent,status);assert.match(summary.textContent,/v2/);
  rows[0].click();pending[batches[0].batch_id].reject(Error('validation_failed'));await tick();assert.equal(add.disabled,true);assert.equal(rows[0].getAttribute('aria-pressed'),'true');assert.match(summary.textContent,/v1/);
 }finally{dom.window.close();}
});
test('picker binds only selected completed batch using latest workspace revision; environment change prevents writes',async()=>{
 const dom=new JSDOM('',{runScripts:'outside-only'});
 dom.window.eval(fs.readFileSync(path.join(__dirname,'cache_snapshot_picker.js'),'utf8'));
 const calls=[];let current=true,added;
 const identity={batch_id:'a'.repeat(32),generation:'b'.repeat(32),snapshot_hash:null,schema_version:1};
 const invoke=async(id,p,o)=>{calls.push({id,p,o});
  if(id.endsWith('.list'))return {batches:[{batch_id:identity.batch_id,status:'completed',project_name:'W10',phase:'SOP',display_name:'old',completed_at:'yesterday'},{batch_id:'x',status:'running'}],next_cursor:null};
  if(id==='simulation.model_cache.query')return {identity,manifest:{node_count:123},nodes:[],next_cursor:null};
  if(id.endsWith('workspace.get'))return {workspace_gid:'10',row_version:9};
  return {document_gid:'20',workspace_row_version:10};};
 try{
  const overlay=await dom.window.AI00CacheSnapshotPicker.open({invoke,workspace:{workspace_gid:'10',row_version:2},isCurrent:()=>current,onAdded:r=>{added=r;}});
  const reopened=await dom.window.AI00CacheSnapshotPicker.open({invoke,workspace:{workspace_gid:'10',row_version:2},isCurrent:()=>current,onAdded:()=>{}});
  assert.equal(reopened,overlay);
  assert.equal(overlay.querySelectorAll('[data-batch]').length,1);
  overlay.querySelector('[data-batch]').click();await tick();
  current=false;overlay.querySelector('[data-add]').click();await tick();
  assert.equal(calls.filter(c=>c.id.endsWith('cache_source.bind')).length,0);
  current=true;overlay.querySelector('[data-add]').click();await tick();await tick();
  const call=calls.find(c=>c.id.endsWith('cache_source.bind'));
  assert.equal(call.p.expected_row_version,9);assert.equal(call.p.cache_binding.batch_id,identity.batch_id);
  assert.equal(call.o.expectedResourceVersion,9);assert.equal(added.document_gid,'20');
 }finally{dom.window.close();}
});

test('successful binding followed by a refresh failure retries refresh without inserting again',async()=>{
 const dom=new JSDOM('',{runScripts:'outside-only'});dom.window.eval(fs.readFileSync(path.join(__dirname,'cache_snapshot_picker.js'),'utf8'));
 let binds=0,refreshes=0;
 const identity={batch_id:'a'.repeat(32),generation:null,snapshot_hash:null,schema_version:1};
 const invoke=async id=>id.endsWith('.list')?{batches:[{status:'completed',batch_id:identity.batch_id}],next_cursor:null}
  :id==='simulation.model_cache.query'?{identity,manifest:{node_count:1}}
  :id.endsWith('workspace.get')?{workspace_gid:'10',row_version:1}:(binds++,{document_gid:'20'});
 try{
  const overlay=await dom.window.AI00CacheSnapshotPicker.open({invoke,workspace:{workspace_gid:'10'},isCurrent:()=>true,onAdded:async()=>{if(++refreshes===1)throw Error('refresh_failed');}});
  overlay.querySelector('[data-batch]').click();await tick();overlay.querySelector('[data-add]').click();await tick();
  assert.equal(overlay.isConnected,true);assert.match(overlay.querySelector('[data-error]').textContent,/refresh_failed/);
  overlay.querySelector('[data-add]').click();await tick();assert.equal(binds,1);assert.equal(refreshes,2);assert.equal(overlay.isConnected,false);
 }finally{dom.window.close();}
});
