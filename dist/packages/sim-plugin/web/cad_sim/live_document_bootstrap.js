(function (root) {
  'use strict';
  root.AI00LiveDocumentBootstrap = function () {
    if (root._liveDocumentSelection) return;
    const getStore = () => root._simulationEnvironmentWorkspace?.store;
    const getNativeView = () => _eAPI()?.visMockupNativeView;
    const interactionAPI = root.AI00ViewerInteraction?.frameAPI(root);
    let localMode = false;
    let previewEpoch=0,previewFlight=Promise.resolve();
    const environmentWindows=new Map();
    let routeTimer=null,startedAt=null;
    const showRoute = (state,action) => {
      root.clearInterval(routeTimer);routeTimer=null;
      const busy=localMode&&['opening','calibrating','mapping_pending','executing','busy'].includes(state);
      if(busy){if(startedAt===null)startedAt=Date.now();}else startedAt=null;
      const actions={show:'正在显示模型',hide:'正在隐藏模型',highlight:'正在高亮节点',unhighlight:'正在取消高亮'};
      const labels={ready:'就绪',closed:'待打开模型',opening:'正在打开 / 关联模型',calibrating:'正在按 VisMockup 校准显隐',mapping_pending:'正在定位模型节点',executing:actions[action]||'正在执行操作',busy:'正在处理',outcome_unknown:'? 结果未知 · 控制已暂停',authorization_expired:'授权已过期',confirmation_cancelled:'已取消打开'};
      labels.vismockup_document_limit_exceeded='已达 10 个文档上限，请关闭非活动文档';
      labels.vismockup_document_limit_unverifiable='无法确认文档数量，暂不能新开文档';
      const render=()=>root.document.querySelectorAll('#viewerInteractionRoute, [data-viewer-interaction-route]').forEach(marker=>{
        marker.dataset.route=localMode?'local':'cloud';marker.dataset.state=state;
        marker.setAttribute('aria-busy',String(busy));
        marker.textContent=localMode?`本地交互 · ${labels[state]||`操作未完成 · ${state}`}${busy?`… ${Math.floor((Date.now()-startedAt)/1000)} 秒`:''}`:'服务端交互';
        marker.title=busy?'操作仍在进行中，请等待。等待时间不代表失败。':localMode?'本地交互状态；详细执行过程请查看调试日志':'本地交互开关关闭';
      });
      render();if(busy)routeTimer=root.setInterval(render,1000);
    };
    root.addEventListener('pagehide',()=>root.clearInterval(routeTimer));
    const local = interactionAPI && root.AI00ViewerInteraction.createViewerInteraction({api:interactionAPI,onState(state,action){
      showRoute(state,action);
      if(['closed','outcome_unknown','cache_document_not_ready','document_selection_changed'].includes(state))root._invalidateCacheSnapshotVisibility?.(state);
      if(state==='outcome_unknown')root._cmdShow?.('操作结果未知；已暂停本地控制，请核对原生视图并重新建立运行关联。不会自动重发。','err');
    },onReady(result,scope){
      const workspace=getStore()?.state?.workspace;
      if(String(workspace?.workspace_gid)!==scope.workspace_gid||(scope.source_kind!=='teamcenter_cache_snapshot'&&workspace.row_version!==scope.expected_workspace_row_version)
        ||result?.document_gid!==scope.document_gid||!Number.isSafeInteger(result.workspace_row_version)
        ||result.workspace_row_version<workspace.row_version||result.workspace_row_version<scope.expected_workspace_row_version)throw Error('document_selection_changed');
      if(workspace.row_version!==result.workspace_row_version){workspace.row_version=result.workspace_row_version;delete workspace.cache_revision_hash;}
      root._completeLocalViewerPresentation();
    }});
    // Finish a display-only attachment before an explicit operation chooses its
    // exact document. Preview never opens a source or grants tree controls.
    const resumeFromCache=local?.resumeFromCache?.bind(local);
    if(local)for(const method of ['ensureReady','open','openFromLaunch','openFromCache','resumeFromCache']){
      if(typeof local[method]!=='function')continue;
      const original=local[method].bind(local);
      local[method]=async(...args)=>{previewEpoch++;await previewFlight;return original(...args);};
    }
    const enabled = interactionAPI ? interactionAPI.enabled().then(value=>{localMode=value===true;showRoute('closed');return localMode;}) : Promise.resolve(false);
    // A bridge error must not silently select the old cloud path.
    enabled.catch(()=>{root.document.querySelectorAll('#viewerInteractionRoute, [data-viewer-interaction-route]').forEach(marker=>{marker.dataset.route='unavailable';marker.textContent='交互通道不可用';});});
    if(!interactionAPI)showRoute('closed');
    root._localViewerInteractionEnabled = () => enabled;
    root._localViewerInteraction = () => localMode ? local : null;
    root._openLocalViewerInteraction = input => local.open(input);
    root._openLocalViewerFromLaunch = input => local.openFromLaunch(input);
    root._ensureLocalViewerReady = (document,node) => {
      const workspace=getStore()?.state?.workspace;
      if(document?.source_kind==='teamcenter_cache_snapshot'){
        if(!localMode||typeof root._ensureCacheSnapshotViewer!=='function')throw Error('cache_document_not_ready');
        return root._ensureCacheSnapshotViewer(document,node);
      }
      if(!localMode||!workspace?.workspace_gid||!Number.isInteger(workspace.row_version)||!document?.document_gid||!document?.source_selector)throw Error('interaction_scope_invalid');
      return local.ensureReady({scope:{workspace_gid:String(workspace.workspace_gid),document_gid:String(document.document_gid),expected_workspace_row_version:workspace.row_version},source_selector:document.source_selector});
    };
    const closeLocal = () => Promise.resolve(local?.close()).catch(error=>root._cmdShow?.(error.message,'err'));
    const cancelPreviewAndClose=()=>{previewEpoch++;root._cancelCacheSnapshotOpening?.();void closeLocal();};
    root.addEventListener('pagehide',cancelPreviewAndClose);
    root.addEventListener('ai00:live-document-changed',cancelPreviewAndClose);
    _eAPI()?.onAuthStateChanged?.(state=>{if(state.mode==='none'){root._invalidateCacheSnapshotVisibility?.('auth_lost');root._forgetCacheSnapshotResumeCandidate?.();cancelPreviewAndClose();}});
    const adoption = root.AI00LiveDocumentAdoption.createAdapter({
      getStore, getNativeView,
      getLocalInteraction: () => localMode ? local : null,
      ensureCachedReady: (document,node) => root._ensureLocalViewerReady(document,node),
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
      confirmRebind: async ({ workspace, document, refreshStructure }) => (await root.AI00Dialogs.confirm(
        `当前 VisMockup 文档不是“${workspace.name || '当前仿真环境'}”保存的运行会话。\n\n` +
        `候选文档：${document.display_name || '当前 VisMockup 文档'}\n` +
        '尚无完整来源与版本证据，请确认这是该环境应使用的文档。同名不代表内容相同。\n\n' +
        (refreshStructure ? '确认重新绑定并刷新结构？' : '确认只恢复连接？保留模型及备选层次缓存，不重读全树、不覆盖 VisMockup 手工操作。缓存内容尚未核对，旧节点不能直接控制新会话。'),
      )),
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
    root._actOnModelNode = async input => {
      try {
        if(input.document?.source_kind==='teamcenter_cache_snapshot'){
          const workspace=getStore()?.state?.workspace;
          if(String(workspace?.workspace_gid)!==String(input.workspaceGid))throw Error('document_selection_changed');
          let current;
          try { current=await _invokeCapability('simulation.environment.model_document.search',{workspace_gid:String(input.workspaceGid)},{version:2}); }
          catch(error){
            if(/not_found|forbidden|unauthorized|permission_denied/.test(error?.code||error?.message||''))
              await root._discardCachedModelProjection?.(input.workspaceGid);
            throw error;
          }
          if(input.isCurrent&&!input.isCurrent()||getStore()?.state?.workspace!==workspace)throw Error('document_selection_changed');
          const source=current?.items?.find(item=>String(item.document_gid)===String(input.document.document_gid));
          const expected=input.document;
          const binding=item=>[item?.batch_id,item?.generation,item?.snapshot_hash,item?.schema_version];
          if(!source||!source.cache_binding||!expected.cache_binding
            ||String(source.workspace_gid)!==String(input.workspaceGid)||source.role!==expected.role
            ||source.source_kind!==expected.source_kind||source.source_identity_hash!==expected.source_identity_hash
            ||source.content_sha256!==expected.content_sha256
            ||JSON.stringify(binding(source.cache_binding))!==JSON.stringify(binding(expected.cache_binding))){
            await root._discardCachedModelProjection?.(input.workspaceGid);
            await root._refreshModelDocuments?.(workspace,{useCache:false}).catch(()=>{});
            throw Error('cache_model_document_not_found');
          }
        }
        return await adoption.actOnProductNode(input);
      }
      finally {
        if (String(getStore()?.state?.workspace?.workspace_gid) === String(input.workspaceGid))
          root._syncModelDocumentVisibility?.(input.document);
      }
    };
    root._invalidateModelControlMappings = () => { adoption.invalidateControlMappings();closeLocal(); };
    root._liveDocumentSelection = selection;
    root._liveDocumentSwitcher = root.AI00LiveDocumentSwitcher.mount({ adapter: selection });
    root._liveDocumentAdoption = root.AI00LiveDocumentAdoption.mount({ adapter: adoption });
    root.addEventListener('simulation:model-document-removed',event=>{
      const detail=event.detail;
      if(String(local?.scope?.workspace_gid)===String(detail?.workspace_gid)&&String(local?.scope?.document_gid)===String(detail?.document_gid)){
        previewEpoch++;adoption.invalidateControlMappings();void closeLocal();
      }
    });
    function hidePending() {
      root._cancelCacheSnapshotOpening?.();
      const closing=closeLocal();
      adoption.invalidateControlMappings();
      root._liveDocumentContextUnavailable = true;
      root._setVmDocumentReady?.(false);
      root._setVmDocumentLabel?.({document_ready:false});
      _notifyNativeViewportBounds();
      return closing;
    }
    async function resumeCacheControls(workspaceGid,binding,identity,isCurrent){
      const candidates=root._cacheSnapshotResumeCandidatesForWorkspace?.(workspaceGid)||[];
      if(!candidates.length||!localMode||!local?.resumeFromCache)return;
      const candidate=candidates.length===1?candidates[0]:null;
      const workspace=getStore()?.state?.workspace;
      try{
        if(!candidate||candidate.workspace_gid!==workspaceGid||candidate.document_session!==binding.document_session||!Number.isSafeInteger(workspace?.row_version)||candidate.workspace_row_version!==workspace.row_version||binding.state!=='bound')throw Error('cache_resume_candidate_mismatch');
        if(typeof root._refreshModelDocuments!=='function'||typeof root._cacheSnapshotCurrentDocument!=='function'||typeof root.AI00CacheSnapshotViewer?.prepareResumeDocument!=='function')throw Error('cache_resume_candidate_mismatch');
        await root._refreshModelDocuments(workspace,{refreshDocumentGid:candidate.document_gid,refreshChildren:true});
        if(!isCurrent()||getStore()?.state?.workspace!==workspace||workspace.row_version!==candidate.workspace_row_version||root._cacheSnapshotResumeCandidate?.(workspaceGid,candidate.document_gid)!==candidate)throw Error('document_selection_changed');
        const document=root._cacheSnapshotCurrentDocument(workspaceGid,candidate.document_gid);
        const originalTree=document?.product_tree;
        const staged=root.AI00CacheSnapshotViewer.prepareResumeDocument(document,candidate);
        const valid=()=>isCurrent()&&getStore()?.state?.workspace===workspace&&workspace.row_version===candidate.workspace_row_version&&root._cacheSnapshotCurrentDocument(workspaceGid,candidate.document_gid)===document&&document.product_tree===originalTree&&root._cacheSnapshotResumeCandidate?.(workspaceGid,candidate.document_gid)===candidate;
        if(!valid())throw Error('document_selection_changed');
        const result=await resumeFromCache({workspace_gid:workspaceGid,document_gid:candidate.document_gid,identity_operation_id:identity.identity_operation_id,expected_document_session:binding.document_session,expected_workspace_row_version:workspace.row_version,idempotency_key:`cache-resume:${identity.identity_operation_id}:${candidate.document_gid}:${workspace.row_version}`});
        if(!valid()||result.document_session!==candidate.document_session||result.visibility_context!==local.visibilityContext&&local.visibilityContext!=null)throw Error('document_selection_changed');
        const viewer={...candidate,visibility_context:result.visibility_context};
        const readback=await adoption.calibrateLoadedCache({workspaceGid,document:staged,viewer,isCurrent:valid});
        if(!valid())throw Error('document_selection_changed');
        document.product_tree=staged.product_tree;
        Object.defineProperty(document,'_cacheViewer',{value:viewer,writable:true,configurable:true,enumerable:false});
        root._renderCacheSnapshotResumeDocument?.(document);
        root._syncModelDocumentVisibility?.(document);
        root._simulationDebug?.('environment_cache_controls_calibrated',{workspace_gid:workspaceGid,document_gid:candidate.document_gid,status:'completed',batch_id:candidate.cache_binding.batch_id,loaded_count:readback.calibrated,unknown_count:readback.unknown_count});
      }catch(error){
        if(!isCurrent()){
          if(candidate&&root._cacheSnapshotResumeCandidate?.(workspaceGid,candidate.document_gid)===candidate)root._forgetCacheSnapshotResumeCandidate?.(workspaceGid,candidate.document_gid);
          return;
        }
        await local.close().catch(()=>{});
        root._forgetCacheSnapshotResumeCandidate?.(workspaceGid,candidate?.document_gid);
        root._invalidateCacheSnapshotVisibility?.(error?.message==='outcome_unknown'?'outcome_unknown':undefined);
        root._simulationDebug?.('environment_cache_controls_rejected',{workspace_gid:workspaceGid,document_gid:candidate?.document_gid,status:'rejected',error_code:/^[a-z][a-z0-9_]+$/.test(error?.message||'')?error.message:'cache_resume_failed'});
      }
    }
    let selected;
    const onEnvironment = state => {
      const next = state.workspace?.workspace_gid || null;
      if (next === selected) return;
      selected = next;
      if (selection.isOwnWorkspaceChange(next)) return;
      selection.cancel();
      const token=++previewEpoch,closing=hidePending();
      root._setVmStatus?.('unavailable', next
        ? '请从模型文件展开到目标节点后打开'
        : '请先选择仿真环境');
      if(next&&environmentWindows.has(String(next)))root._setVmStatus?.('connecting','正在恢复该环境的文档…');
      {
        const previous=previewFlight;
        previewFlight=(async()=>{
          await previous;await closing;
          const current=()=>token===previewEpoch&&String(getStore()?.state?.workspace?.workspace_gid)===String(next);
          if(!current())return;
          try{
            await getNativeView()?.detach?.();if(!current()||!next)return;
            root._setVmStatus?.('connecting','正在核对环境与文档…');
            const binding=await _invokeCapability('simulation.environment.live_document.binding.get',{workspace_gid:String(next)});
            if(!current())return;
            if(!binding?.document_session||String(binding.workspace_gid)!==String(next)||!['bound','importing'].includes(binding.state)){
              root._setVmStatus?.('unavailable','当前环境未关联活动文档，请点击模型打开');return;
            }
            const snapshot=await getNativeView()?.manageDocuments?.();
            if(!current())return;
            const cached=environmentWindows.get(String(next));
            const windows=[...(snapshot?.documents||[])].sort((a,b)=>Number(b.key===cached)-Number(a.key===cached));
            await _requireConnectorRuntime();if(!current())return;
            for(const candidate of windows){
              if(!current())return;
              root._simulationDebug?.('environment_document_identity_check',{workspace_gid:String(next),status:'running',capability_id:'simulation.vismockup.document.identity.read.request',window_key:candidate.key});
              const attached=await root._attachNativeViewport?.({managedDocumentKey:candidate.key});
              if(!current())return;
              if(attached?.state!=='attached')throw Error(attached?.error||'native_view_attach_failed');
              const before=await getNativeView().manageDocuments();if(!current())return;
              const outcome=await _requestVisMockupCommand('simulation.vismockup.document.identity.read.request',{}, {confirmation:false});
              if(!current())return;
              const step=outcome?.steps?.length===1?outcome.steps[0]:null;
              const after=await getNativeView().manageDocuments();if(!current())return;
              const activeKey=snapshot=>{const active=snapshot.documents.filter(item=>item.current);return active.length===1?active[0].key:null;};
              if(activeKey(before)!==candidate.key||activeKey(after)!==candidate.key)throw Error('document_window_identity_changed');
              if(!outcome?.plan_id||step?.status!=='succeeded'||!step.result?.document_session||step.result.process_id!==attached.pid)
                throw Error(step?.error_code||'document_identity_unavailable');
              if(step.result.document_session!==binding.document_session){
                root._simulationDebug?.('environment_document_identity_mismatch',{workspace_gid:String(next),status:'skipped',window_key:candidate.key});continue;
              }
              const verified=await _invokeCapability('simulation.environment.live_document.binding.get',{identity_operation_id:outcome.plan_id});
              if(!current())return;
              if(String(verified?.workspace_gid)!==String(next)||verified.document_session!==binding.document_session||!['bound','importing'].includes(verified.state))throw Error('document_environment_binding_mismatch');
              const confirmed=await getNativeView().manageDocuments();if(!current())return;
              if(activeKey(confirmed)!==candidate.key)throw Error('document_window_identity_changed');
              environmentWindows.set(String(next),candidate.key);
              root._completeLocalViewerPresentation();
              root._setVmStatus?.('connected','当前文档已显示');
              root._simulationDebug?.('environment_document_restored',{workspace_gid:String(next),status:'completed',window_key:candidate.key,document_session:binding.document_session});
              await resumeCacheControls(String(next),binding,{identity_operation_id:outcome.plan_id},current);
              return;
            }
            environmentWindows.delete(String(next));throw Error('environment_document_window_unavailable');
          }catch(error){
            if(!current())return;
            await getNativeView()?.detach?.();if(!current())return;
            root._setVmDocumentReady?.(false);root._setVmDocumentLabel?.({document_ready:false});
            root._setVmStatus?.('unavailable',error?.message==='environment_document_window_unavailable'?'该环境的文档窗口已关闭或关联失效，请点击模型重新打开':'未能恢复该环境文档，请点击模型重试');
            root._simulationDebug?.('current_document_preview_failed',{workspace_gid:String(next),status:'failed',error_code:error?.message||'native_view_attach_failed'});
          }
        })();
      }
    };
    getStore()?.subscribe(onEnvironment);
    if (getStore()?.state) onEnvironment(getStore().state);
    root.document.addEventListener('click', event => {
      if (event.target.closest?.('[data-record-gid],[data-workspace-gid]')) selection.cancel();
    }, true);
  };
})(window);
