(function(root){
 'use strict';
 function createManager({document:doc,getAPI,isVisible=()=>true,schedule=setTimeout,cancel=clearTimeout,diagnostic=()=>{}}){
  const entries=[...doc.querySelectorAll('[data-viewer-documents]')],win=doc.defaultView;
  let documents=null,overlay=null,list=null,notice=null,bulk=null,refreshButton=null,timer,readFlight,disposed=false,closing=false,message='',readError='',lastCount,opener,pollGeneration=0,closeGeneration=0;
  const visible=()=>!disposed&&!doc.hidden&&isVisible();
  const trace=(stage,detail)=>{try{diagnostic(stage,detail);}catch{}};
  const errorCode=error=>/^[a-z][a-z0-9_]+$/.test(error?.message||'')?error.message:'document_management_failed';
  const element=(tag,className,text)=>{const item=doc.createElement(tag);if(className)item.className=className;if(text!=null)item.textContent=text;return item;};
  function render(){
   for(const entry of entries){entry.textContent='文档 '+(documents?documents.length:'?')+'/10';entry.dataset.full=String(documents?.length>=10);entry.title=documents?.length>=10?'已达到 10 个文档上限，请关闭非活动文档后再打开':'查看全部 VisMockup 文档并关闭非活动文档';}
   if(!overlay)return;
   notice.textContent=[documents?.length>=10?'已达到 10 个文档上限，不能打开新文档；请先关闭非活动文档。':'',message,readError].filter(Boolean).join(' ');
   bulk.disabled=closing||!documents?.some(item=>!item.current);refreshButton.disabled=closing;
   const rows=(documents||[]).map(item=>{
    const row=element('div','cs-document-manager-row'),name=element('span','cs-document-manager-name',item.name||'未命名文档');name.title=item.name;row.append(name);
    if(item.current)row.append(element('span','cs-document-manager-current','当前 · 不可关闭'));
    else{const button=element('button','cs-btn','关闭');button.type='button';button.dataset.closeDocument='';button.disabled=closing;button.addEventListener('click',()=>void closeOne(item.key));row.append(button);}
    return row;
   });
   list.replaceChildren(...(rows.length?rows:[element('p','cs-document-manager-empty',documents?'尚未打开文档':'无法读取文档列表，请刷新重试')]));
  }
  async function refresh(){
   if(disposed)return false;if(readFlight)return readFlight;
   readFlight=(async()=>{
    try{
     const api=getAPI();if(typeof api?.manageDocuments!=='function')throw Error('document_management_unavailable');
     const result=await api.manageDocuments();if(disposed)return false;
     if(result?.limit!==10||!Array.isArray(result.documents)||result.documents.some(item=>typeof item?.key!=='string'||!item.key||typeof item.name!=='string'||typeof item.current!=='boolean')||new Set(result.documents.map(item=>item.key)).size!==result.documents.length)throw Error('document_management_invalid');
     documents=result.documents.map(({key,name,current})=>({key,name,current}));readError='';
     if(lastCount!==documents.length){trace('document_management_read',{node_count:documents.length,current_count:documents.filter(item=>item.current).length,limit:10,status:'completed'});lastCount=documents.length;}
     render();return true;
    }catch(error){
     if(disposed)return false;documents=null;readError='文档读取失败，请刷新重试。';
     if(lastCount!==null){trace('document_management_failed',{status:'failed',error_code:errorCode(error),limit:10});lastCount=null;}
     render();return false;
    }
   })().finally(()=>{readFlight=null;});return readFlight;
  }
  async function closeKeys(requested){
   if(disposed||closing)return;closing=true;message='';render();let closed=0,stopped='completed';const generation=closeGeneration;
   try{
    if(!await refresh()){stopped='failed';return;}
    const keys=requested||documents.filter(item=>!item.current).map(item=>item.key);
    for(const key of keys){
     if(!visible()||generation!==closeGeneration){stopped='cancelled';break;}
     if(!await refresh()){stopped='failed';break;}
     if(!visible()||generation!==closeGeneration){stopped='cancelled';break;}
     const target=documents.find(item=>item.key===key);if(!target||target.current)continue;
     trace('document_close_started',{node_name:target.name,status:'started'});
     let response;
     try{const api=getAPI();if(typeof api?.closeDocument!=='function')throw Error('document_management_unavailable');response=await api.closeDocument(key);if(!['closed','pending'].includes(response?.status))throw Error('document_close_failed');}
     catch(error){if(readFlight)await readFlight;await refresh();message='关闭文档失败，请刷新列表后重试。';trace('document_close_failed',{node_name:target.name,status:'failed',error_code:errorCode(error)});stopped='failed';break;}
     if(readFlight)await readFlight;const read=await refresh();
     if(response.status==='pending'){message='关闭尚未完成，请查看 VisMockup 中的提示；批量关闭已停止。';trace('document_close_pending',{node_name:target.name,status:'pending'});stopped='pending';break;}
     trace('document_close_completed',{node_name:target.name,status:'closed'});closed++;
     if(!read){stopped='failed';break;}
    }
   }finally{closing=false;if(!requested)trace('document_close_bulk_completed',{node_count:closed,status:stopped});render();}
  }
  const closeOne=key=>closeKeys([key]),closeInactive=()=>closeKeys();
  function closePopup(){closeGeneration++;if(!overlay)return;overlay.remove();overlay=null;win?.dispatchEvent(new win.Event('ai00:dialog-visibility'));if(visible())opener?.focus();}
  async function open(event){
   event?.stopPropagation();if(disposed)return;
   opener=event?.currentTarget||entries[0];
   if(!overlay){
    message='';overlay=element('div','cs-modal-overlay cs-document-manager-overlay');
    const panel=element('section','cs-modal cs-document-manager');panel.setAttribute('role','dialog');panel.setAttribute('aria-modal','true');panel.setAttribute('aria-labelledby','viewerDocumentsTitle');
    const title=element('h2','cs-modal-title','VisMockup 文档');title.id='viewerDocumentsTitle';
    const hint=element('p','cs-document-manager-hint','列出 VisMockup 模型文档窗口（包括隐藏窗口）。当前文档不会关闭；切换文档请使用视图区已有的文档名称入口。');
    notice=element('p','cs-document-manager-notice');notice.setAttribute('role','status');
    list=element('div','cs-document-manager-list');
    const actions=element('div','cs-modal-actions');
    refreshButton=element('button','cs-btn','刷新');refreshButton.type='button';refreshButton.addEventListener('click',()=>{message='';void refresh();});
    bulk=element('button','cs-btn','关闭全部非活动文档');bulk.type='button';bulk.addEventListener('click',()=>void closeInactive());
    const dismiss=element('button','cs-btn','完成');dismiss.type='button';dismiss.addEventListener('click',closePopup);
    actions.append(refreshButton,bulk,dismiss);panel.append(title,hint,notice,list,actions);overlay.append(panel);
    overlay.addEventListener('click',event=>{if(event.target===overlay)closePopup();});
    overlay.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();closePopup();}if(event.key==='Tab'){const buttons=[...overlay.querySelectorAll('button:not(:disabled)')],index=buttons.indexOf(doc.activeElement);if(event.shiftKey&&index<=0){event.preventDefault();buttons.at(-1)?.focus();}else if(!event.shiftKey&&index===buttons.length-1){event.preventDefault();buttons[0]?.focus();}}});
    doc.body.append(overlay);win?.dispatchEvent(new win.Event('ai00:dialog-visibility'));dismiss.focus();
   }
   render();await refresh();
  }
  function scheduleNext(generation){if(visible()&&generation===pollGeneration)timer=schedule(async()=>{timer=null;if(visible()&&!closing)await refresh();scheduleNext(generation);},5000);}
  function visibilityChanged(){const generation=++pollGeneration;if(timer!=null)cancel(timer);timer=null;if(visible()){void refresh();scheduleNext(generation);}else closePopup();}
  function dispose(){if(disposed)return;disposed=true;pollGeneration++;if(timer!=null)cancel(timer);timer=null;closePopup();for(const entry of entries)entry.removeEventListener('click',open);doc.removeEventListener('visibilitychange',visibilityChanged);win?.removeEventListener('pagehide',dispose);}
  for(const entry of entries)entry.addEventListener('click',open);
  doc.addEventListener('visibilitychange',visibilityChanged);win?.addEventListener('pagehide',dispose,{once:true});render();visibilityChanged();
  return {open,refresh,closeOne,closeInactive,visibilityChanged,dispose};
 }
 const api={createManager};if(typeof module==='object')module.exports=api;root.AI00ViewerDocumentManager=api;
})(typeof window==='undefined'?globalThis:window);
