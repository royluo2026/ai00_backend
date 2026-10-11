'use strict';
(async()=>{
 const host=window.AI00DialogHost;
 const off=host.onTheme(theme=>document.documentElement.dataset.theme=theme);
 window.addEventListener('pagehide',off,{once:true});
 const data=await host.ready();document.documentElement.dataset.theme=data.theme;
 const approved=await window.AI00Dialogs.confirm(data);
 await host.answer(data.request_id,approved===true);
})().catch(()=>{document.body.textContent='确认窗口不可用，请关闭并重试。';});
