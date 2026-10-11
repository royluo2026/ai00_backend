'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const {createBusinessFacade}=require('./business_facade');
const envelope={version:1,payload:{operation:'delete',gid:'one'},idempotency_key:'stable'};
const id='craft.standard_operation.change.apply';
function setup(confirm){const calls=[];const host={AI00Dialogs:{confirm},electronAPI:{invokeCapability:async(_id,body)=>{calls.push(body);return body.confirmation?{success:true,data:{ok:true,status:'completed',data:{gid:'one'}}}:{success:false,error:{code:'confirmation_required',confirmation_challenge:'challenge-one'}};}}};return{calls,api:createBusinessFacade(host)};}
test('shared confirmation remains pending and cancelling sends no approval',async()=>{
 let decide;const {api,calls}=setup(()=>new Promise(r=>decide=r));const pending=api.invoke(id,envelope);await Promise.resolve();await Promise.resolve();
 assert.equal(typeof decide,'function');assert.equal(calls.length,1);decide(false);await assert.rejects(pending,/cancelled/);assert.equal(calls.length,1);
});
test('approval preserves body and idempotency; custom confirmation overrides default once',async()=>{
 const {api,calls}=setup(()=>{throw Error('default must not run');});let count=0;
 assert.equal((await api.invoke(id,envelope,async()=>{count++;return true;})).gid,'one');assert.equal(count,1);
 assert.deepEqual(calls[1],{...envelope,confirmation:{challenge_id:'challenge-one',approved:true}});
});
test('missing dialog or thrown confirmation cannot approve',async()=>{
 const {api,calls}=setup(()=>{throw Error('dialog_unavailable');});await assert.rejects(api.invoke(id,envelope),/dialog_unavailable/);assert.equal(calls.length,1);
});
