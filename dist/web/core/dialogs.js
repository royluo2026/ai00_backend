(function(root,factory){
 'use strict';
 const api=factory();
 if(typeof module==='object'&&module.exports)module.exports=api;
 if(root&&!root.AI00Dialogs)root.AI00Dialogs=api.createDialogs(root);
})(typeof window==='undefined'?null:window,function(){
 'use strict';
 function createDialogs(win){
  const doc=win.document,queue=[];let active=null,disposed=false,suspended=false,serial=0;
  const cancelled=kind=>kind==='prompt'?null:kind==='confirm'?false:undefined;
  function relatedWindows(){
   let root=win;
   try{while(root.parent!==root&&root.parent.document)root=root.parent;}catch{}
   const windows=[];
   function visit(w){try{if(!w.document)return;windows.push(w);for(const frame of w.document.querySelectorAll('iframe')){
    let visible=true;for(let el=frame;el;el=el.parentElement){const style=w.getComputedStyle(el);if(el.hidden||style.display==='none'||style.visibility==='hidden'){visible=false;break;}}
    if(visible)visit(frame.contentWindow);
   }}catch{}}
   visit(root);return windows;
  }
  const isAnyOpen=()=>relatedWindows().some(w=>w.document.querySelector('dialog.ai00-dialog[open]'));
  const visibility=()=>{const open=isAnyOpen();for(const w of relatedWindows())w.dispatchEvent(new w.CustomEvent('ai00:dialog-visibility',{detail:{open}}));};
  function next(){
   if(active||disposed||suspended||!queue.length)return;
   const entry=active=queue.shift(),o=entry.options;
   const dialog=doc.createElement('dialog');entry.dialog=dialog;entry.focus=doc.activeElement;
   dialog.className='ai00-dialog';dialog.dataset.tone=['info','warning','danger'].includes(o.tone)?o.tone:'info';
   const id='ai00-dialog-'+(++serial);
   dialog.setAttribute('aria-labelledby',id);dialog.setAttribute('aria-describedby',id+'-message');
   const form=doc.createElement('form');form.method='dialog';
   const header=doc.createElement('header');header.className='ai00-dialog-header';
   const icon=doc.createElement('span');icon.className='ai00-dialog-icon';icon.setAttribute('aria-hidden','true');icon.textContent=dialog.dataset.tone==='danger'?'!':'i';
   const title=doc.createElement('h2');title.id=id;title.className='ai00-dialog-title';title.textContent=o.title||(entry.kind==='alert'?'提示':entry.kind==='prompt'?'请输入':'确认操作');
   const close=doc.createElement('button');close.type='button';close.className='ai00-dialog-close';close.textContent='×';close.setAttribute('aria-label','关闭');close.onclick=()=>entry.finish(cancelled(entry.kind));
   header.append(icon,title,close);
   const body=doc.createElement('div');body.className='ai00-dialog-body';
   const message=doc.createElement('p');message.id=id+'-message';message.textContent=String(o.message??'');body.append(message);
   if(o.detail){const details=doc.createElement('details'),summary=doc.createElement('summary'),pre=doc.createElement('pre');summary.textContent='查看详情';pre.textContent=String(o.detail);details.append(summary,pre);body.append(details);}
   let input;
   if(entry.kind==='prompt'){input=doc.createElement('input');input.dataset.dialogInput='';input.value=String(o.defaultValue??'');input.setAttribute('aria-label',o.message||o.title||'输入');body.append(input);}
   const actions=doc.createElement('footer');actions.className='ai00-dialog-actions';
   const cancel=doc.createElement('button');cancel.type='button';cancel.dataset.dialogCancel='';cancel.textContent=o.cancelText||'取消';cancel.onclick=()=>entry.finish(cancelled(entry.kind));
   const confirm=doc.createElement('button');confirm.type='submit';confirm.dataset.dialogConfirm='';confirm.className='ai00-dialog-primary';confirm.textContent=o.confirmText||(entry.kind==='alert'?'知道了':'确认');
   if(entry.kind!=='alert')actions.append(cancel);actions.append(confirm);form.append(header,body,actions);dialog.append(form);
   form.onsubmit=e=>{e.preventDefault();entry.finish(entry.kind==='prompt'?input.value:entry.kind==='confirm'?true:undefined);};
   dialog.addEventListener('cancel',e=>{e.preventDefault();entry.finish(cancelled(entry.kind));});
   dialog.addEventListener('close',()=>entry.finish(cancelled(entry.kind)));
   doc.body.append(dialog);
   try{dialog.showModal();visibility(true);(input||(entry.kind==='confirm'?cancel:confirm)).focus();input?.select();}
   catch(error){entry.finish(cancelled(entry.kind),error);}
  }
  function ask(kind,options,defaultValue){
   if(typeof options!=='object'||options===null)options={message:String(options??''),defaultValue};
   if(disposed||suspended||options.signal?.aborted)return Promise.resolve(cancelled(kind));
   return new Promise((resolve,reject)=>{
    const entry={kind,options};let finished=false;
    const abort=()=>entry.finish(cancelled(kind));
    entry.finish=(value,error)=>{
     if(finished)return;finished=true;options.signal?.removeEventListener('abort',abort);
     const index=queue.indexOf(entry);if(index>=0)queue.splice(index,1);
     if(active===entry){active=null;entry.dialog?.remove();if(entry.focus?.isConnected)entry.focus.focus();visibility(false);}
     if(error)reject(error);else resolve(value);next();
    };
    options.signal?.addEventListener('abort',abort,{once:true});queue.push(entry);next();
   });
  }
  function workspaceVisibility(event){
   if(event.source!==win.parent||event.data?.type!=='workspace:visibility')return;
   suspended=event.data.visible===false;
   if(suspended){active?.finish(cancelled(active.kind));for(const e of [...queue])e.finish(cancelled(e.kind));}
   visibility();
  }
  function dispose(){if(disposed)return;disposed=true;active?.finish(cancelled(active.kind));for(const e of [...queue])e.finish(cancelled(e.kind));win.removeEventListener('pagehide',dispose);win.removeEventListener('message',workspaceVisibility);}
  win.addEventListener('pagehide',dispose);
  win.addEventListener('message',workspaceVisibility);
  return Object.freeze({alert:o=>ask('alert',o),confirm:o=>ask('confirm',o),prompt:(o,value)=>ask('prompt',o,value),isAnyOpen,dispose});
 }
 return {createDialogs};
});
