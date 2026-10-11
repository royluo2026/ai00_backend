'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
require('./teamcenter_session');
const ready={state:'ready',code:'ready',masked_username:'u***r'},out={state:'logged_out',code:'logged_out',masked_username:''};
test('late old status cannot replace the successful login state',async()=>{
 let finishOld;const states=[];const make=globalThis.AI00TeamcenterSession.createSessionState;assert.equal(typeof make,'function');
 const state=make({api:{teamcenterGetSession:()=>new Promise(r=>finishOld=r),teamcenterLogin:async()=>ready},onChange:(...x)=>states.push(x)});
 const old=state.refresh();await state.login({});finishOld(out);await old;assert.equal(states.at(-1)[0],'ready');assert.equal(states.at(-1)[1],ready);
});
test('logout and disposal invalidate pending successful responses',async()=>{
 let finishOld;const states=[];const make=globalThis.AI00TeamcenterSession.createSessionState;assert.equal(typeof make,'function');
 const state=make({api:{teamcenterGetSession:()=>new Promise(r=>finishOld=r),teamcenterLogout:async()=>out},onChange:s=>states.push(s)});
 const old=state.refresh();await state.logout();finishOld(ready);await old;assert.equal(states.at(-1),'signed-out');
 const late=state.refresh();state.dispose();const count=states.length;finishOld(ready);await late;assert.equal(states.length,count);
});
test('subscribed session changes refresh state and unsubscribe on disposal',async()=>{
 let notify,removed=false;const states=[];const make=globalThis.AI00TeamcenterSession.createSessionState;assert.equal(typeof make,'function');
 const state=make({api:{teamcenterGetSession:async()=>ready,onTeamcenterSessionChanged:fn=>{notify=fn;return()=>removed=true;}},onChange:s=>states.push(s)});
 await notify();assert.equal(states.at(-1),'ready');state.dispose();assert.equal(removed,true);
});
