const test=require('node:test'),assert=require('node:assert/strict'),{JSDOM}=require('jsdom');
const {createManager}=require('./viewer_document_manager');
function rig(api){
 const dom=new JSDOM('<body><button data-viewer-documents></button><button data-viewer-documents></button></body>',{pretendToBeVisual:true}),timers=new Map(),events=[];let visible=true,next=0;
 const manager=createManager({document:dom.window.document,getAPI:()=>api,isVisible:()=>visible,schedule:fn=>{timers.set(++next,fn);return next;},cancel:id=>timers.delete(id),diagnostic:(stage,detail)=>events.push({stage,detail})});
 return {manager,dom,timers,events,setVisible(value){visible=value;manager.visibilityChanged();},dispose(){manager.dispose();dom.window.close();}};
}
test('counts every native document, protects multiple current documents, and renders names safely',async()=>{
 const r=rig({manageDocuments:async()=>({limit:10,documents:[{key:'a',name:'<img src=x onerror=bad()>',current:true},{key:'b',name:'Hidden active',current:true},{key:'c',name:'Inactive',current:false}]})});
 try{await r.manager.refresh();assert.ok([...r.dom.window.document.querySelectorAll('[data-viewer-documents]')].every(button=>button.textContent==='文档 3/10'));
  await r.manager.open();assert.equal(r.dom.window.document.querySelectorAll('img').length,0);assert.match(r.dom.window.document.querySelector('[role=dialog]').textContent,/<img src=x onerror=bad\(\)>/);assert.equal(r.dom.window.document.querySelectorAll('[data-close-document]').length,1);
  assert.equal(r.events.filter(event=>event.stage==='document_management_read').length,1,'unchanged snapshots must not flood diagnostics');
 }finally{r.dispose();}
});
test('full capacity warns and failed reads show unknown count rather than zero',async()=>{
 let fail=false;const r=rig({manageDocuments:async()=>{if(fail)throw Error('native_unavailable');return {limit:10,documents:Array.from({length:10},(_,i)=>({key:String(i),name:'Doc '+i,current:i===0}))};}});
 try{await r.manager.open();assert.match(r.dom.window.document.querySelector('[role=dialog]').textContent,/已达到 10 个文档上限/);fail=true;assert.equal(await r.manager.refresh(),false);assert.equal(r.dom.window.document.querySelector('[data-viewer-documents]').textContent,'文档 ?/10');assert.equal(r.dom.window.document.querySelectorAll('[data-close-document]:not(:disabled)').length,0);}finally{r.dispose();}
});
test('closing rechecks the native current flag instead of trusting the displayed snapshot',async()=>{
 let current=false,closes=0;const r=rig({manageDocuments:async()=>({limit:10,documents:[{key:'a',name:'A',current}]}),closeDocument:async()=>{closes++;return {status:'closed'};}});
 try{await r.manager.open();current=true;await r.manager.closeOne('a');assert.equal(closes,0);assert.equal(r.dom.window.document.querySelector('[data-viewer-documents]').textContent,'文档 1/10');}finally{r.dispose();}
});
test('bulk closes only inactive documents, uses real counts, and stops at an unsaved native prompt',async()=>{
 let docs=[{key:'a',name:'Current',current:true},{key:'b',name:'B',current:false},{key:'c',name:'C',current:false},{key:'d',name:'D',current:false}],calls=[],reads=0;
 const r=rig({manageDocuments:async()=>{reads++;return {limit:10,documents:docs};},closeDocument:async key=>{calls.push(key);if(key==='b'){docs=docs.filter(doc=>doc.key!==key);return {status:'closed'};}return {status:'pending'};}});
 try{await r.manager.open();await r.manager.closeInactive();assert.deepEqual(calls,['b','c']);assert.equal(reads,6);assert.equal(r.dom.window.document.querySelector('[data-viewer-documents]').textContent,'文档 3/10');assert.match(r.dom.window.document.querySelector('[role=dialog]').textContent,/关闭尚未完成/);assert.ok(r.events.some(event=>event.stage==='document_close_pending'));assert.doesNotMatch(JSON.stringify(r.events),/"key"|vmmanage:/);}finally{r.dispose();}
});
test('native close errors stop bulk and refresh authoritative count',async()=>{
 let calls=0;const r=rig({manageDocuments:async()=>({limit:10,documents:[{key:'a',name:'A',current:false},{key:'b',name:'B',current:false}]}),closeDocument:async()=>{calls++;throw Error('document_close_failed');}});
 try{await r.manager.open();await r.manager.closeInactive();assert.equal(calls,1);assert.equal(r.dom.window.document.querySelector('[data-viewer-documents]').textContent,'文档 2/10');assert.ok(r.events.some(event=>event.stage==='document_close_failed'));}finally{r.dispose();}
});
test('polling pauses while the simulation page is hidden and is disposed without further reads',async()=>{
 let reads=0;const r=rig({manageDocuments:async()=>{reads++;return {limit:10,documents:[]};}});
 try{await r.manager.refresh();assert.equal(r.timers.size,1);r.setVisible(false);assert.equal(r.timers.size,0);const before=reads;r.setVisible(true);await r.manager.refresh();assert.equal(reads,before+1);r.manager.dispose();assert.equal(r.timers.size,0);r.setVisible(true);await r.manager.refresh();assert.equal(reads,before+1);}finally{r.dispose();}
});
test('resuming during an old polling read creates only one active timer',async()=>{
 let finish,slow=false;const r=rig({manageDocuments:async()=>{if(slow)return new Promise(resolve=>finish=()=>resolve({limit:10,documents:[]}));return {limit:10,documents:[]};}});
 try{await r.manager.refresh();slow=true;const [id,tick]=[...r.timers][0];r.timers.delete(id);const polling=tick();r.setVisible(false);r.setVisible(true);slow=false;finish();await polling;assert.equal(r.timers.size,1);}finally{r.dispose();}
});
test('dismissing the manager during bulk close stops before closing another document',async()=>{
 let finish,calls=0;const r=rig({manageDocuments:async()=>({limit:10,documents:[{key:'a',name:'A',current:false},{key:'b',name:'B',current:false}]}),closeDocument:async()=>{calls++;return calls===1?new Promise(resolve=>finish=()=>resolve({status:'closed'})):{status:'closed'};}});
 try{await r.manager.open();const closing=r.manager.closeInactive();await new Promise(resolve=>setImmediate(resolve));r.dom.window.document.querySelector('[role=dialog]').dispatchEvent(new r.dom.window.KeyboardEvent('keydown',{key:'Escape',bubbles:true}));finish();await closing;assert.equal(calls,1);}finally{r.dispose();}
});
