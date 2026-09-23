'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const {createBusinessFacade}=require('./business_facade');

const unavailable={success:false,data:null,error:{code:'invocation_unavailable'}};
const completed=data=>({success:true,data:{ok:true,status:'completed',data},error:null});

test('retries one transient desktop failure for a governed read',async()=>{
 let calls=0;
 const api=createBusinessFacade({electronAPI:{invokeCapability:async()=>++calls===1?unavailable:completed({items:['ok']})}});
 assert.deepEqual(await api.invoke('craft.bop.version.list',{version:1,payload:{}}),{items:['ok']});
 assert.equal(calls,2);
});

test('keeps retrying a governed read through a backend restart window',async()=>{
 let calls=0;
 const api=createBusinessFacade({electronAPI:{invokeCapability:async()=>++calls<6?unavailable:completed({items:['ok']})}});
 assert.deepEqual(await api.invoke('base.capability_registry.search',{version:1,payload:{query:'',limit:100}}),{items:['ok']});
 assert.equal(calls,6);
});

test('does not replay a governed write after an unavailable invocation',async()=>{
 let calls=0;
 const api=createBusinessFacade({electronAPI:{invokeCapability:async()=>{calls++;return unavailable;}}});
 await assert.rejects(api.invoke('craft.bop.entry.change.apply',{version:1,payload:{operation:'update'}}),/invocation_unavailable/);
 assert.equal(calls,1);
});

test('reuses a payload idempotency key at the invocation boundary',async()=>{
 let envelope;
 const api=createBusinessFacade({electronAPI:{invokeCapability:async(_id,body)=>{envelope=body;return completed({preview_gid:'1'});}}});
 await api.invoke('craft.bop.repository.fork.preview',{version:1,payload:{idempotency_key:'fork-preview-1'}});
 assert.equal(envelope.idempotency_key,'fork-preview-1');
});
