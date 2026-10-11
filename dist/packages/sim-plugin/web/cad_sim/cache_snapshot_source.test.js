const {test}=require('node:test');
const assert=require('node:assert/strict');
const source=require('./cache_snapshot_source.js');
const binding={batch_id:'a'.repeat(32),generation:'b'.repeat(32),snapshot_hash:null,schema_version:1};
const root={node_key:'root',parent_occurrence_id:null,child_order:0,name:'Root',has_children:true,occurrence_path:[]};
const page=(nodes,next_cursor=null)=>({identity:{...binding},nodes,next_cursor,manifest:{node_count:20,completed_at:'2026-09-28',readiness:{geometry_files:'not_requested'}}});

test('explicit source reads roots then only requested children, pins version and identity',async()=>{
 const calls=[];const tree=source.partialTree(binding);
 const invoke=async(id,payload,options)=>{calls.push({id,payload,options});return calls.length===1?page([root]):page([{...root,node_key:'child',parent_occurrence_id:'root',has_children:false}]);};
 await source.readChildren(invoke,tree);
 assert.equal(calls[0].payload.scope,'roots');assert.equal(calls[0].options.version,2);
 assert.equal(calls[0].payload.batch_id,binding.batch_id);assert.equal(calls[0].payload.expected_generation,binding.generation);
 await source.readChildren(invoke,tree,'root');
 assert.equal(calls[1].payload.scope,'children');assert.equal(calls[1].payload.node_key,'root');
 assert.equal(tree.nodes.length,2);assert.equal(tree.nodes[1].parent_key,tree.nodes[0].node_key);
 assert.equal(tree.nodes[0].visible,null);assert.equal(tree.nodes[0].control_key,null);
});
test('mismatched batch and generation fail without accepting nodes or falling back',async()=>{
 for(const identity of [{...binding,batch_id:'b'.repeat(32)},{...binding,generation:'c'.repeat(32)}]){
  const tree=source.partialTree(binding);let calls=0;
  await assert.rejects(source.readChildren(async()=>{calls++;return {...page([root]),identity};},tree),/cache_snapshot_identity_mismatch/);
  assert.equal(tree.nodes.length,0);assert.equal(calls,1);
 }
});
test('late responses do not populate abandoned trees; duplicate requests share one read',async()=>{
 const tree=source.partialTree(binding);let resolve,calls=0,current=true;
 const invoke=()=>{calls++;return new Promise(r=>resolve=r);};
 const first=source.readChildren(invoke,tree,null,{isCurrent:()=>current});
 const second=source.readChildren(invoke,tree,null,{isCurrent:()=>current});
 assert.equal(calls,1);current=false;resolve(page([root]));await Promise.all([first,second]);
 assert.equal(tree.nodes.length,0);assert.notEqual(tree.pages.roots.state,'loading');
});
test('failed next page keeps nodes and cursor; retry appends without duplicate',async()=>{
 const tree=source.partialTree(binding);await source.readChildren(async()=>page([root],'next'),tree);
 await assert.rejects(source.readChildren(async()=>{throw Error('offline');},tree,null,{more:true}),/offline/);
 assert.equal(tree.nodes.length,1);assert.equal(tree.pages.roots.next_cursor,'next');
 let request;await source.readChildren(async(_,p)=>{request=p;return page([{...root,node_key:'other'}]);},tree,null,{more:true});
 assert.equal(request.cursor,'next');assert.equal(tree.nodes.length,2);
});
test('detail queries only fixed batch node and retains raw read states',async()=>{
 const tree=source.partialTree(binding);let request;
 const properties_result={properties:{name:'Old'},raw_fields:[{field:'matrix',read_state:'unavailable',value_json:'null'}]};
 const result=await source.readNode(async(_,p)=>{request=p;return page([{...root,properties_result}]);},tree,'root');
 assert.equal(request.projection,'properties');assert.equal(request.scope,'node');assert.deepEqual(result.properties_result,properties_result);
});
