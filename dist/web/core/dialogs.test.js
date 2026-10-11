'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const {JSDOM}=require('jsdom');
const fs=require('node:fs');
const path=require('node:path');
function setup(t){
 const dom=new JSDOM('<button id="origin">打开</button>',{url:'https://app.test'});
 t.after(()=>dom.window.close());
 const proto=dom.window.HTMLDialogElement.prototype;
 proto.showModal=function(){this.open=true;};
 proto.close=function(){this.open=false;this.dispatchEvent(new dom.window.Event('close'));};
 assert.ok(fs.existsSync(path.join(__dirname,'dialogs.js')),'shared dialog implementation required');
 const api=require('./dialogs').createDialogs(dom.window);
 const doc=dom.window.document;
 const click=which=>doc.querySelector('[data-dialog-'+which+']').click();
 return {dom,api,doc,click};
}
test('ancestor dialog publishes occlusion to same-origin child documents',async t=>{
 const {dom,api,doc,click}=setup(t);const frame=doc.createElement('iframe');doc.body.append(frame);
 const events=[];frame.contentWindow.addEventListener('ai00:dialog-visibility',e=>events.push(e.detail.open));
 const pending=api.confirm('parent');assert.equal(events.at(-1),true);
 click('cancel');await pending;assert.equal(events.at(-1),false);
});
test('workspace hiding cancels pending dialogs instead of occluding the next tab',async t=>{
 const {dom,api,doc}=setup(t);const first=api.confirm('first'),next=api.confirm('second');
 dom.window.dispatchEvent(new dom.window.MessageEvent('message',{source:dom.window.parent,data:{type:'workspace:visibility',visible:false}}));
 assert.equal(doc.querySelector('dialog'),null);assert.equal(await first,false);assert.equal(await next,false);
 dom.window.dispatchEvent(new dom.window.MessageEvent('message',{source:dom.window.parent,data:{type:'workspace:visibility',visible:true}}));
 const again=api.confirm('visible again');assert.ok(doc.querySelector('dialog'));api.dispose();assert.equal(await again,false);
});
test('confirmation waits, escapes text, and cancellation restores focus',async t=>{
 const {api,doc,click}=setup(t);doc.getElementById('origin').focus();
 let finished=false;const pending=api.confirm({title:'删除',message:'<img src=x onerror=alert(1)>',tone:'danger'});
 pending.then(()=>finished=true);await Promise.resolve();
 assert.equal(finished,false);assert.equal(doc.querySelector('img'),null);
 assert.match(doc.querySelector('dialog').textContent,/<img/);
 assert.equal(doc.activeElement,doc.querySelector('[data-dialog-cancel]'));
 click('cancel');assert.equal(await pending,false);assert.equal(doc.activeElement.id,'origin');
});
test('empty prompt value is not cancellation; affirmative confirm is boolean',async t=>{
 const {api,doc,click}=setup(t);
 const input=api.prompt({message:'名称',defaultValue:'old'});doc.querySelector('input').value='';click('confirm');assert.equal(await input,'');
 const cancel=api.prompt({message:'名称'});click('cancel');assert.equal(await cancel,null);
 const yes=api.confirm({message:'继续？'});click('confirm');assert.equal(await yes,true);
});
test('queue cancellation does not close active request and disposal settles all',async t=>{
 const {api,doc,dom,click}=setup(t);const events=[];
 dom.window.addEventListener('ai00:dialog-visibility',e=>events.push(e.detail.open));
 const first=api.confirm({message:'first'});const abort=new dom.window.AbortController();
 const second=api.confirm({message:'second',signal:abort.signal});abort.abort();
 assert.equal(await second,false);assert.match(doc.querySelector('dialog').textContent,/first/);
 const third=api.prompt({message:'third'});click('cancel');assert.equal(await first,false);
 assert.match(doc.querySelector('dialog').textContent,/third/);api.dispose();assert.equal(await third,null);
 assert.equal(doc.querySelector('dialog'),null);assert.equal(events.at(-1),false);
 assert.equal(await api.confirm({message:'after dispose'}),false);
});
test('escape, pagehide and already-aborted requests never approve',async t=>{
 const {api,doc,dom}=setup(t);const abort=new dom.window.AbortController();abort.abort();
 assert.equal(await api.confirm({message:'no',signal:abort.signal}),false);assert.equal(doc.querySelector('dialog'),null);
 const escaped=api.confirm({message:'esc'});doc.querySelector('dialog').dispatchEvent(new dom.window.Event('cancel',{cancelable:true}));assert.equal(await escaped,false);
 const pending=api.prompt({message:'leave'});dom.window.dispatchEvent(new dom.window.Event('pagehide'));assert.equal(await pending,null);
});
test('form submit confirms once and nested business form keeps its values',async t=>{
 const {api,doc,dom}=setup(t);
 const business=doc.createElement('form');business.innerHTML='<input id="reason" value="review reason">';doc.body.append(business);doc.getElementById('reason').focus();
 const pending=api.prompt({message:'输入'});doc.querySelector('[data-dialog-input]').value='value';
 doc.querySelector('dialog form').dispatchEvent(new dom.window.Event('submit',{cancelable:true}));
 assert.equal(await pending,'value');assert.equal(doc.getElementById('reason').value,'review reason');assert.equal(doc.activeElement.id,'reason');
});
