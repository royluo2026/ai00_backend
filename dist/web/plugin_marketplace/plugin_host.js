(() => {
  'use strict';
  const api = window.electronAPI || window.parent.electronAPI;
  const status = document.getElementById('mount-status'), reopen = document.getElementById('reopen');
  let mount, dispose, generation = 0;
  const toolbar=document.getElementById('artifact-toolbar'),saveButton=document.getElementById('save-artifact'),saveStatus=document.getElementById('save-status');
  let artifactId;
  async function request(action, ...args) {
    const result = await api.pluginMount[action](...args);
    if (!result?.ok) throw Object.assign(new Error(result?.error || 'plugin_transport_failed'), {code:result?.error || 'plugin_transport_failed'});
    return result.value;
  }
  function close() {
    generation++; dispose?.(); dispose = null;
    artifactId=null;toolbar.hidden=true;
    if (mount) { void request('close', mount.handle).catch(() => {}); mount = null; }
  }
  function failed(message) { close(); status.hidden = false; status.textContent = message; reopen.hidden = false; }
  async function open() {
    close(); const current = generation;
    status.hidden = false; status.textContent = '正在打开插件…'; reopen.hidden = true;
    try {
      const opened = await request('open', new URLSearchParams(location.search).get('plugin_id'));
      if (current !== generation) { void request('close', opened.handle).catch(() => {}); return; }
      mount = opened;
      dispose = window.AI00PluginHost.mountAi00Plugin({
        container: document.getElementById('plugin-host'), url: opened.url,
        grantedCapabilities: Object.keys(opened.capabilityVersions), capabilityVersions: opened.capabilityVersions,
        catalogRelease: opened.catalogRelease,
        invoke: async (id, payload) => {
          try {
            const result=await request('invoke', opened.handle, id, payload);
            if(current===generation&&result.ok&&result.data?.artifact_ref&&typeof result.data.file_name==='string'){
              artifactId=result.data.artifact_ref.artifact_id;toolbar.hidden=false;saveStatus.textContent=result.data.file_name+' 已生成';
            }
            return result;
          }
          catch (error) {
            const code = error.code || 'plugin_transport_failed';
            if (current === generation && ['mount_unavailable', 'authentication_required', 'plugin_mount_denied'].includes(code)) failed('插件授权已失效，请重新打开。');
            return { ok:false, status:'rejected', capability_id:id, major_version:opened.capabilityVersions[id], data:null, operation_ref:null, artifact_refs:[],
              error:{code, message:code, retryable:false, details:{}}, evidence:[], warnings:[], correlation:{request_id:null,trace_id:null} };
          }
        },
      });
      status.hidden = true;
    } catch (_) { if (current === generation) failed('暂时无法打开插件，请确认已登录且插件已启用。'); }
  }
  reopen.addEventListener('click', open);
  saveButton.addEventListener('click',async()=>{
    if(!mount||!artifactId)return;
    const current=generation;saveButton.disabled=true;
    try{await request('save',mount.handle,artifactId);if(current===generation)saveStatus.textContent='已保存到所选位置';}
    catch(error){if(current===generation)saveStatus.textContent=error.code==='native_selection_cancelled'?'已取消保存':'保存未完成，请重试';}
    finally{saveButton.disabled=false;}
  });
  window.addEventListener('pagehide', close);
  const unsubscribe = api?.onAuthStateChanged?.(() => failed('登录状态已变化，请重新打开插件。'));
  window.addEventListener('pagehide', () => unsubscribe?.());
  void open();
})();
