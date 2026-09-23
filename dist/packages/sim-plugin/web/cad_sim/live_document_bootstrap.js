(function (root) {
  'use strict';
  root.AI00LiveDocumentBootstrap = function () {
    if (root._liveDocumentSelection) return;
    const getStore = () => root._simulationEnvironmentWorkspace?.store;
    const getNativeView = () => _eAPI()?.visMockupNativeView;
    const interactionAPI = root.AI00ViewerInteraction?.frameAPI(root);
    let localMode = false;
    const showRoute = state => {
      const marker=root.document.getElementById('viewerInteractionRoute');if(!marker)return;
      marker.dataset.route=localMode?'local':'cloud';marker.dataset.state=state;
      const labels={ready:'就绪',closed:'待打开模型',opening:'授权中',mapping_pending:'映射中',busy:'忙碌',outcome_unknown:'结果未知 · 控制已暂停',authorization_expired:'授权已过期'};
      marker.textContent=localMode?`本地交互 · ${labels[state]||state}`:'服务端交互';
      marker.title=localMode?'本地管道 · 60 秒授权 / 30 秒续期；未知结果不会重发':'本地交互开关关闭';
    };
    const local = interactionAPI && root.AI00ViewerInteraction.createViewerInteraction({api:interactionAPI,onState(state){
      showRoute(state);
      if(state==='outcome_unknown')root._cmdShow?.('操作结果未知；已暂停本地控制，请核对原生视图并重新建立运行关联。不会自动重发。','err');
    }});
    const enabled = interactionAPI ? interactionAPI.enabled().then(value=>{localMode=value===true;showRoute('closed');return localMode;}) : Promise.resolve(false);
    // A bridge error must not silently select the old cloud path.
    enabled.catch(()=>{const marker=root.document.getElementById('viewerInteractionRoute');if(marker){marker.dataset.route='unavailable';marker.textContent='交互通道不可用';}});
    if(!interactionAPI)showRoute('closed');
    root._localViewerInteractionEnabled = () => enabled;
    root._localViewerInteraction = () => localMode ? local : null;
    root._openLocalViewerInteraction = input => local.open(input);
    root._openLocalViewerFromLaunch = input => local.openFromLaunch(input);
    const closeLocal = () => {void local?.close().catch(error=>root._cmdShow?.(error.message,'err'));};
    root.addEventListener('pagehide',closeLocal);
    root.addEventListener('ai00:live-document-changed',closeLocal);
    _eAPI()?.onAuthStateChanged?.(state=>{if(state.mode==='none')closeLocal();});
    const adoption = root.AI00LiveDocumentAdoption.createAdapter({
      getStore, getNativeView,
      getLocalInteraction: () => localMode ? local : null,
      executeNodeAction: async (node_key,action,options) => {
        const id=['show','hide'].includes(action)?'simulation.vismockup.node.visibility.change.request':'simulation.vismockup.node.selection.change.request';
        const payload={node_key,action};
        if(Array.isArray(options?.occurrence_path)&&options.occurrence_path.length) payload.occurrence_path=options.occurrence_path;
        if(typeof options?.expected_document_session==='string') payload.expected_document_session=options.expected_document_session;
        const outcome=await _requestVisMockupCommand(id,payload,{confirmation:false});
        const result=outcome?.steps?.at(-1)?.result;
        if(!result) throw Error('model_node_control_result_missing');
        return result;
      },
      refreshWorkspace: async workspace => {
        await Promise.all([root._refreshModelDocuments?.(workspace), root._refreshAlternateHierarchies?.(workspace)]);
      },
      getDisplayName: () => root.document.getElementById('vmDocumentLabel')?.textContent,
      readTree: (options) => _requestVisMockupCommand('simulation.vismockup.tree.read.request',
        { max_depth: options?.max_depth ?? 8, force_refresh: options?.force_refresh ?? true,
          ...(typeof options?.expected_document_session==='string'
            ? {expected_document_session:options.expected_document_session} : {}) }, { confirmation: false }),
      invoke: (...args) => _invokeCapability(...args),
      readIdentity: async () => {
        await _requireConnectorRuntime();
        return _requestVisMockupCommand('simulation.vismockup.document.identity.read.request', {}, { confirmation: false });
      },
      readHierarchyInventory: async payload => {
        await _requireConnectorRuntime();
        return _requestVisMockupCommand('simulation.vismockup.document.hierarchy_inventory.read.request', payload, { confirmation: false });
      },
      confirmRebind: ({ workspace, document, refreshStructure }) => root.confirm(
        `当前 VisMockup 文档不是“${workspace.name || '当前仿真环境'}”保存的运行会话。\n\n` +
        `候选文档：${document.display_name || '当前 VisMockup 文档'}\n` +
        '尚无完整来源与版本证据，请确认这是该环境应使用的文档。同名不代表内容相同。\n\n' +
        (refreshStructure ? '确认重新绑定并刷新结构？' : '确认只恢复连接？保留模型及备选层次缓存，不重读全树、不覆盖 VisMockup 手工操作。缓存内容尚未核对，旧节点不能直接控制新会话。'),
      ),
    });
    const selection = root.AI00LiveDocumentSwitcher.createAdapter({
      getStore, getNativeView,
      reconnectDocument: adoption.reconnectDocument,
      prepareDocumentSelection: async () => {
        const native = getNativeView();
        const status = await native?.status?.();
        if (['attached', 'documentChanged'].includes(status?.state)) return;
        await _requireConnectorRuntime();
        const attached = await root._attachNativeViewport?.({ forDocumentSelection: true });
        if (attached?.state !== 'attached') throw Error(attached?.error || 'document_selection_unavailable');
      },
      readDocument: async () => {
        const native = getNativeView();
        const status = await native?.status?.();
        if (status?.state !== 'attached' && status?.state !== 'documentChanged') {
          const attached = await root._attachNativeViewport?.();
          if (attached?.state !== 'attached') throw Error(attached?.error || 'bound_document_window_unavailable');
        }
        return adoption.readCurrentDocument();
      },
      invoke: (...args) => _invokeCapability(...args),
      onContext(verified) {
        closeLocal();
        adoption.invalidateControlMappings();
        root._liveDocumentContextUnavailable = !verified;
        _notifyNativeViewportBounds();
      },
    });
    root._readLiveModelProductTree = adoption.readProductTree;
    root._actOnModelNode = adoption.actOnProductNode;
    root._invalidateModelControlMappings = () => { adoption.invalidateControlMappings();closeLocal(); };
    root._liveDocumentSelection = selection;
    root._liveDocumentSwitcher = root.AI00LiveDocumentSwitcher.mount({ adapter: selection });
    root._liveDocumentAdoption = root.AI00LiveDocumentAdoption.mount({ adapter: adoption });
    function hidePending() {
      closeLocal();
      adoption.invalidateControlMappings();
      root._liveDocumentContextUnavailable = true;
      _notifyNativeViewportBounds();
    }
    let selected;
    const onEnvironment = state => {
      const next = state.workspace?.workspace_gid || null;
      if (next === selected) return;
      selected = next;
      if (selection.isOwnWorkspaceChange(next)) return;
      selection.cancel();
      hidePending();
      root._setVmStatus?.('unavailable', next
        ? '请从模型文件展开到目标节点后打开'
        : '请先选择仿真环境');
    };
    getStore()?.subscribe(onEnvironment);
    if (getStore()?.state) onEnvironment(getStore().state);
    root.document.addEventListener('click', event => {
      if (event.target.closest?.('[data-record-gid],[data-workspace-gid]')) selection.cancel();
    }, true);
  };
})(window);
