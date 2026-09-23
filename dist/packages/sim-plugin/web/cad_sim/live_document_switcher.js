(function (root) {
  'use strict';
  function createAdapter({ getNativeView, readDocument, invoke, getStore, reconnectDocument, prepareDocumentSelection = async () => {}, onContext = () => {} }) {
    // Only identity-verified observations map a COM document session to a native
    // window token. Titles never fill gaps; unobserved sessions fail explicitly.
    const observedWindows = new Map();
    let generation = 0, nativeSwitching = false, expectedWorkspace = null;
    let queue = Promise.resolve();
    function enqueue(run) { const pending = queue.then(run); queue = pending.catch(() => {}); return pending; }
    async function bindCurrent(current, expectedGid = null, preserveEnvironment = false) {
      const doc = await readDocument();
      if (!current()) return { status: 'superseded' };
      const binding = await invoke('simulation.environment.live_document.binding.get', { identity_operation_id: doc.identity_operation_id });
      if (!current()) return { status: 'superseded' };
      if (!binding || binding.state === 'unavailable' || binding.document_session !== doc.document_session) throw Error('document_binding_unavailable');
      if (preserveEnvironment && !binding.workspace_gid) {
        onContext(false);
        return {status:'unbound',environmentId:getStore()?.state?.workspace?.workspace_gid||null,bindingState:'unbound'};
      }
      if (expectedGid !== null && binding.workspace_gid !== expectedGid) throw Error('document_environment_binding_mismatch');
      if (doc.native_window_key) observedWindows.set(doc.document_session, doc.native_window_key);
      const store = getStore();
      expectedWorkspace = binding.workspace_gid || null;
      try {
        if (binding.workspace_gid) {
          if (store?.state?.workspace?.workspace_gid !== binding.workspace_gid)
            await store.openWorkspace(binding.workspace_gid, { isCurrent: current });
        } else store?.clearSelection?.();
      } finally { expectedWorkspace = null; }
      if (!current()) return { status: 'superseded' };
      onContext(true);
      return { status: 'committed', environmentId: binding.workspace_gid || null, bindingState: binding.state };
    }
    const api = {
      canReconnect() { return !!getStore()?.state?.workspace?.workspace_gid && typeof reconnectDocument === 'function'; },
      reconnectEnvironment(key, {isCurrent = () => true} = {}) {
        const token = ++generation, workspaceGid = getStore()?.state?.workspace?.workspace_gid;
        const current = () => token === generation && isCurrent()
          && getStore()?.state?.workspace?.workspace_gid === workspaceGid;
        return enqueue(async () => {
          if (!current()) return {status:'superseded'};
          if (!workspaceGid || !reconnectDocument) throw Error('environment_selection_required');
          nativeSwitching = true;
          onContext(false);
          try {
            const status = await getNativeView().selectDocument(key);
            if (!current()) return {status:'superseded'};
            if (!['attached','documentChanged'].includes(status?.state)
              || (status.documentKey && status.documentKey !== key)) throw Error('document_switch_identity_mismatch');
            await reconnectDocument(workspaceGid, {isCurrent:current, expectedWindowKey:key});
            if (!current()) return {status:'superseded'};
            const result = await bindCurrent(current, workspaceGid, true);
            return result.status === 'superseded' ? result
              : {...result, status:'reconnected', structureVerification:'unverified'};
          } catch (error) { if (current()) onContext(false); throw error; }
          finally { nativeSwitching = false; }
        });
      },
      recoverEnvironment({isCurrent = () => true} = {}) {
        const token=++generation,workspaceGid=getStore()?.state?.workspace?.workspace_gid;
        const current=()=>token===generation&&isCurrent()
          &&getStore()?.state?.workspace?.workspace_gid===workspaceGid;
        return enqueue(async()=>{
          if(!current())return {status:'superseded'};
          if(!workspaceGid)throw Error('environment_selection_required');
          nativeSwitching=true;onContext(false);
          const native=getNativeView();let original=null;
          try{
            const binding=await invoke('simulation.environment.live_document.binding.get',{workspace_gid:workspaceGid});
            if(!current())return {status:'superseded'};
            if(String(binding?.workspace_gid)!==String(workspaceGid)||!binding.document_session
              ||!['bound','importing'].includes(binding.state))throw Error('document_binding_unavailable');
            const windows=await api.listDocuments();
            original=windows.find(item=>item.current)?.key||null;
            for(const candidate of windows){
              if(!current())return {status:'superseded'};
              try{
                const status=await native.selectDocument(candidate.key);
                if(!['attached','documentChanged'].includes(status?.state)
                  ||(status.documentKey&&status.documentKey!==candidate.key))continue;
                const document=await readDocument();
                if(document.document_session!==binding.document_session)continue;
                observedWindows.set(document.document_session,candidate.key);
                const result=await bindCurrent(current,String(workspaceGid),true);
                return result.status==='superseded'?result:{...result,status:'recovered'};
              }catch(_){/* Probe the next bounded native window by signed identity. */}
            }
            if(original&&current())await native.selectDocument(original).catch?.(()=>{});
            throw Error('bound_document_window_unavailable');
          }catch(error){if(current())onContext(false);throw error;}
          finally{nativeSwitching=false;}
        });
      },
      isOwnWorkspaceChange(gid) { return nativeSwitching && (gid || null) === expectedWorkspace; },
      cancel() { ++generation; },
      async listDocuments() {
        const native = getNativeView();
        if (!native?.listDocuments) throw Error('文档切换连接尚未就绪，请更新并重启 AI00 测试客户端');
        await prepareDocumentSelection();
        return native.listDocuments();
      },
      selectDocument(key, { isCurrent = () => true } = {}) {
        const token = ++generation;
        const current = () => token === generation && isCurrent();
        return enqueue(async () => {
          if (!current()) return { status: 'superseded' };
          nativeSwitching = true;
          let nativeSelected = false;
          try {
            const status = await getNativeView().selectDocument(key);
            if (!current()) return { status: 'superseded' };
            if (!['attached', 'documentChanged'].includes(status?.state)) throw Error(status?.error || 'document_switch_failed');
            if (status.documentKey && status.documentKey !== key) throw Error('document_switch_identity_mismatch');
            nativeSelected = true;
            return await bindCurrent(current);
          } catch (error) {
            if (!current()) return { status: 'superseded' };
            getStore()?.clearSelection?.();
            onContext(nativeSelected);
            if (nativeSelected) return { status: 'selected_unverified', environmentId: null, bindingState: 'unavailable', error: error.message };
            throw error;
          }
          finally { nativeSwitching = false; }
        });
      },
      observeCurrentDocument() {
        if (nativeSwitching) return Promise.resolve({ status: 'superseded' });
        const token = ++generation, current = () => token === generation;
        return enqueue(async () => {
          if (!current()) return { status: 'superseded' };
          nativeSwitching = true;
          try { return await bindCurrent(current, null, true); }
          catch (error) {
            if (!current()) return { status: 'superseded' };
            onContext(false);
            return { status: 'selected_unverified', environmentId: getStore()?.state?.workspace?.workspace_gid || null, bindingState: 'unavailable', error: error.message };
          }
          finally { nativeSwitching = false; }
        });
      },
      selectEnvironment(workspaceGid) {
        const token = ++generation, current = () => token === generation;
        return enqueue(async () => {
          if (!current()) return { status: 'superseded' };
          nativeSwitching = true;
          try {
            const binding = await invoke('simulation.environment.live_document.binding.get', { workspace_gid: workspaceGid });
            if (!current()) return { status: 'superseded' };
            if (binding?.state === 'unbound') { onContext(false); return { status: 'unbound', environmentId: workspaceGid }; }
            if (!binding?.document_session || binding.state === 'unavailable' || binding.workspace_gid !== workspaceGid) throw Error('document_binding_unavailable');
            const active = await readDocument();
            if (!current()) return { status: 'superseded' };
            if (active.document_session !== binding.document_session) {
              const key = observedWindows.get(binding.document_session);
              const windows = await api.listDocuments();
              if (!current()) return { status: 'superseded' };
              if (!key || !windows.some(item => item.key === key)) throw Error('bound_document_window_unavailable');
              const status = await getNativeView().selectDocument(key);
              if (!current()) return { status: 'superseded' };
              if (!['attached', 'documentChanged'].includes(status?.state)) throw Error(status?.error || 'document_switch_failed');
            }
            return await bindCurrent(current, workspaceGid);
          } catch (error) { if (current()) onContext(false); throw error; }
          finally { nativeSwitching = false; }
        });
      },
    };
    return api;
  }
  function mount({ adapter, document = root.document } = {}) {
    const overlay = document.getElementById('liveDocumentSwitcher');
    const items = document.getElementById('documentSwitcherItems');
    const status = document.getElementById('documentSwitcherStatus');
    const entry = document.getElementById('btnSwitchVmDocument');
    const label = document.getElementById('vmDocumentLabel');
    if (!overlay || !entry) return;
    let generation = 0, opener = entry;
    const currentAdapter = () => adapter || root._liveDocumentSelection;
    function close() { ++generation; overlay.classList.add('hidden'); opener.focus(); }
    async function open() {
      const token = ++generation;
      overlay.classList.remove('hidden'); items.replaceChildren(); status.textContent = '正在读取已打开的文档…';
      document.getElementById('documentSwitcherClose').focus();
      const current = () => token === generation && !overlay.classList.contains('hidden');
      try {
        const api = currentAdapter();
        if (!api?.listDocuments) throw new Error('文档切换连接尚未就绪，当前无法读取真实窗口列表');
        const documents = await api.listDocuments();
        if (!current()) return;
        if (!Array.isArray(documents) || documents.length > 256) throw new Error('document_list_invalid');
        const keys = new Set();
        for (const doc of documents) {
          if (typeof doc.key !== 'string' || !doc.key || keys.has(doc.key)) throw new Error('document_identity_invalid');
          keys.add(doc.key);
        }
        for (const doc of documents) {
          const card = document.createElement('section'); card.className = 'cs-document-card'; card.dataset.documentCard = doc.key;
          const heading = document.createElement('div'); heading.className = 'cs-document-title';
          heading.textContent = `${doc.current ? '当前 · ' : ''}${doc.name || '未命名文档'}`;
          heading.title = doc.name || '未命名文档';
          const actions = document.createElement('div'); actions.className = 'cs-document-actions';
          card.append(heading,actions); items.append(card);
          const button = document.createElement('button'); button.type = 'button'; button.className = 'cs-btn';
          button.dataset.documentKey = doc.key;
          button.textContent = '切换到此文档';
          button.setAttribute('aria-label',`切换到 ${doc.name || '未命名文档'}`);
          button.title = doc.bindingLabel || '切换后核对仿真环境绑定';
          button.onclick = async () => {
            if (!current()) return;
            items.querySelectorAll('button').forEach(item => { item.disabled = true; });
            status.textContent = '正在切换文档并核对环境绑定…';
            try {
              if (!api.selectDocument) throw new Error('文档切换连接尚未就绪');
              const result = await api.selectDocument(doc.key, { isCurrent: current });
              if (!current()) return;
              if (result?.status === 'superseded') return;
              if (!result || result.status === 'failed') throw new Error(result?.error || 'document_switch_failed');
              status.textContent = result.environmentId ? '已切换文档及绑定环境'
                : result.bindingState === 'unavailable' ? '已切换文档，环境绑定暂无法核对' : '已切换文档 · 未绑定仿真环境';
            } catch (error) { if (current()) status.textContent = error.message || '文档切换失败'; }
            finally { if (current()) items.querySelectorAll('button').forEach(item => { item.disabled = false; }); }
          };
          actions.append(button);
          if (api.canReconnect?.()) {
            const reconnect = document.createElement('button'); reconnect.type = 'button'; reconnect.className = 'cs-btn';
            reconnect.dataset.reconnectKey = doc.key;
            reconnect.textContent = '恢复到当前环境';
            reconnect.setAttribute('aria-label',`将 ${doc.name || '未命名文档'} 恢复到当前环境，保留缓存`);
            reconnect.title = '需确认此文档来源；只恢复连接，不刷新结构、不覆盖备选层次结构';
            reconnect.onclick = async () => {
              if (!current()) return;
              items.querySelectorAll('button').forEach(item => { item.disabled = true; });
              root._cmdShow?.('');
              status.textContent = '正在核对文档并请求恢复连接…';
              try {
                const result = await api.reconnectEnvironment(doc.key, {isCurrent:current});
                if (current() && result?.status === 'reconnected') {
                  status.textContent = '已恢复连接 · 保留结构缓存，内容尚未核对；旧节点控制需重新定位';
                  root._cmdShow?.('文档连接已恢复 · 缓存节点尚未核对；无需重复关联');
                }
              } catch (error) {
                if (current()) {
                  status.textContent = `恢复连接未完成：${error.message || 'unknown_error'}`;
                  root._cmdShow?.(status.textContent,'err');
                }
              }
              finally { if (current()) items.querySelectorAll('button').forEach(item => { item.disabled = false; }); }
            };
            actions.append(reconnect);
          }
        }
        status.textContent = documents.length ? `${documents.length} 个已打开文档` : '没有已打开的 VisMockup 文档';
      } catch (error) { if (current()) { items.replaceChildren(); status.textContent = error.message || '读取文档失败'; } }
    }
    const show = event => { opener = event.currentTarget; void open(); };
    entry.addEventListener('click', show); label?.addEventListener('click', show);
    document.getElementById('documentSwitcherClose').onclick = close;
    document.getElementById('documentSwitcherRefresh').onclick = open;
    overlay.onkeydown = event => {
      if (event.key === 'Escape') { event.preventDefault(); close(); }
      if (event.key === 'Tab') {
        const buttons = [...overlay.querySelectorAll('button:not(:disabled)')];
        if (event.shiftKey && document.activeElement === buttons[0]) { event.preventDefault(); buttons.at(-1).focus(); }
        else if (!event.shiftKey && document.activeElement === buttons.at(-1)) { event.preventDefault(); buttons[0].focus(); }
      }
    };
    return { open, close, dispose() { close(); entry.removeEventListener('click', show); label?.removeEventListener('click', show); } };
  }
  root.AI00LiveDocumentSwitcher = { createAdapter, mount };
})(typeof window !== 'undefined' ? window : globalThis);
