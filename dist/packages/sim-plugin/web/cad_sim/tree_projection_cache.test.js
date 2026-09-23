const test = require('node:test');
const assert = require('node:assert/strict');
const { create } = require('./tree_projection_cache');

test('targeted load retains local data without entering cache preview state',async()=>{
  const views=[];
  const cache=create(()=>({get:async()=>({data:{items:[{name:'old'}]},cached_at:'2026-09-16'}),put:async()=>{}}));
  await cache.run({workspaceGid:'1',kind:'models',previewCache:false,isCurrent:()=>true,
    render:(d,m)=>views.push(m),load:async()=>({items:[]})});
  assert.equal(views.length,1);
  assert.equal(views[0].pending,false);
  assert.equal(views[0].cached_at,undefined);
});

test('new model read failure is not labelled as failure of unrelated cached structures',async()=>{
  const views=[];
  const cache=create(()=>({get:async()=>({data:{items:[{name:'old'}]},cached_at:'old'}),put:async()=>{}}));
  await cache.run({workspaceGid:'1',kind:'models',previewCache:false,preserveFreshItems:true,isCurrent:()=>true,
    render:(d,m)=>views.push({d,m}),load:async()=>({items:[{name:'new',product_tree_error:'teamcenter_worker_failed'}]})});
  assert.equal(views.length,1);
  assert.equal(views[0].d.items[0].name,'new');
  assert.equal(views[0].m.error,'teamcenter_worker_failed');
  assert.equal(views[0].m.cached_at,undefined);
});

test('empty cached collections have no structure cache status while fetching their list',async()=>{
  const views=[];
  const cache=create(()=>({get:async()=>({data:{items:[]},cached_at:'2026-09-16'}),put:async()=>{}}));
  await cache.run({workspaceGid:'1',kind:'models',isCurrent:()=>true,
    render:(d,m)=>views.push(m),load:async()=>({items:[]})});
  assert.equal(views[0].cached_at,undefined);
  assert.equal(views[0].pending,false);
});
test('runtime restart preserves both model and AH snapshots without rewriting their session',async()=>{
  for(const kind of ['models','alternate']) {
    const data={items:[{product_tree:{document_session:'old',nodes:[{node_key:'7'}]}}]},views=[];
    const cache=create(()=>({get:async(_w,k)=>k===kind?{data,cached_at:'old'}:null,
      remove:()=>assert.fail('session change is not permission revocation'),put:()=>assert.fail('do not rewrite snapshot')}));
    await cache.run({workspaceGid:'1',kind,isCurrent:()=>true,render:(d,m)=>views.push({d,m}),
      load:async()=>{throw Error('document_session_changed');}});
    assert.equal(views.at(-1).d,data);
    assert.equal(views.at(-1).m.error,'document_session_changed');
  }
});
test('entry cache hit skips authoritative loader; explicit refresh still replaces it',async()=>{
  let loads=0; const views=[];
  const cache=create(()=>({get:async(_w,k)=>k==='models'?{data:{items:[]},cached_at:'2026-09-15T00:00:00Z'}:null,put:async()=>{}}));
  const options={workspaceGid:'1',kind:'models',useCache:true,isCurrent:()=>true,render:(d,m)=>views.push(m),load:async()=>{loads++;return{items:[]};}};
  await cache.run(options);
  assert.equal(loads,0); assert.equal(views.at(-1).cacheOnly,true); assert.equal(views.at(-1).pending,false);
  await cache.run({...options,useCache:false}); assert.equal(loads,1);
});
test('cached tree renders before refresh and transient failure preserves it', async () => {
  const views=[], writes=[];
  const data={items:[{name:'old'}]}; let reject;
  const cache=create(()=>({get:async()=>({data,cached_at:'2026-09-15T01:00:00Z'}),put:async(...a)=>writes.push(a)}));
  const pending=cache.run({workspaceGid:'1',kind:'models',isCurrent:()=>true,render:(d,m)=>views.push({d,m}),load:()=>new Promise((_,r)=>reject=r)});
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(views[0].m.pending,true); assert.equal(views[0].d,data);
  reject(Error('provider_failed')); await pending;
  assert.equal(views.at(-1).m.error,'provider_failed'); assert.equal(writes.length,0);
});
test('switch fences late results; successful refresh replaces cache', async () => {
  let current=true,finish; const rendered=[],written=[];
  const cache=create(()=>({get:async()=>null,put:async(...args)=>written.push(args)}));
  const pending=cache.run({workspaceGid:'1',kind:'alternate',isCurrent:()=>current,render:d=>rendered.push(d),load:()=>new Promise(r=>finish=r)});
  await new Promise(resolve=>setImmediate(resolve)); current=false; finish({items:[]}); await pending;
  assert.equal(rendered.length,0); assert.equal(written.length,0);
  current=true;
  await cache.run({workspaceGid:'2',kind:'alternate',isCurrent:()=>current,render:d=>rendered.push(d),load:async()=>({items:[]})});
  assert.equal(written[0][0],'2'); assert.equal(rendered.length,1);
});
test('permission revocation removes the projection instead of retaining cached business data',async()=>{
  const removed=[],views=[];
  const cache=create(()=>({get:async(_w,k)=>k==='models'?{data:{items:[]},cached_at:'old'}:null,remove:async(...a)=>removed.push(a)}));
  await assert.rejects(cache.run({workspaceGid:'1',kind:'models',isCurrent:()=>true,render:d=>views.push(d),load:async()=>{throw Error('workspace_forbidden')}}),/workspace_forbidden/);
  assert.equal(removed.length,1); assert.deepEqual(views.at(-1),{items:[]});
});
