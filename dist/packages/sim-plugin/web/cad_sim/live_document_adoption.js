(function (root) {
  'use strict';
  const unavailable = '当前连接尚未提供实时文档绑定，暂不能创建；不会导出或重载模型';
  const trace=(stage,detail)=>{try{root._simulationDebug?.(stage,detail);}catch{}};

  function createAdapter({ readIdentity, readHierarchyInventory, readTree, invoke, getStore, getDisplayName, getNativeView, refreshWorkspace, executeNodeAction, getLocalInteraction, ensureCachedReady, confirmRebind = () => false }) {
    const pendingTrees = new Map();
    let nodeActionChain=Promise.resolve();const calibratedDocuments=new WeakMap();
    let controlMappings = new WeakMap();
    const invalidateControlMappings = () => { controlMappings = new WeakMap(); };
    async function readRuntimeIdentity() {
      const outcome = await readIdentity();
      const step = outcome?.steps?.length === 1 ? outcome.steps[0] : null;
      if (!outcome?.plan_id || step?.status !== 'succeeded'
        || !/^sha256:[a-f0-9]{64}$/.test(step?.result?.document_session || ''))
        throw new Error('document_identity_unavailable');
      return { ...step.result, identity_operation_id: outcome.plan_id };
    }
    async function readCurrentDocument() {
      const native = getNativeView?.();
      const before = native ? (await native.listDocuments()).find(item => item.current) : null;
      const process = native ? await native.status() : null;
      if (native && !before?.key) throw new Error('document_window_identity_unavailable');
      const outcome = await readIdentity();
      const step = outcome?.steps?.length === 1 ? outcome.steps[0] : null;
      if (!outcome?.plan_id || step?.status !== 'succeeded'
        || !/^sha256:[a-f0-9]{64}$/.test(step?.result?.document_session || '')) {
        throw new Error('document_identity_unavailable');
      }
      if (native) {
        const after = (await native.listDocuments()).find(item => item.current);
        const afterProcess = await native.status();
        if (after?.key !== before.key || process?.pid !== afterProcess?.pid || process?.pid !== step.result.process_id)
          throw new Error('document_window_identity_changed');
      }
      // Backend re-verifies persisted signed evidence; this object is not an attestation.
      return { ...step.result, identity_operation_id: outcome.plan_id,
        native_window_key: before?.key || null,
        display_name: getDisplayName?.() || '当前 VisMockup 文档' };
    }
    async function rebindDocument(workspaceKey, before, binding, { isCurrent = () => true, refreshStructure = false, expectedWindowKey } = {}) {
      const store = getStore?.(), workspace = store?.state?.workspace;
      const valid = () => isCurrent() && store?.state?.workspace === workspace
        && String(workspace?.workspace_gid) === workspaceKey;
      if (!valid() || !Number.isInteger(workspace?.row_version)) throw Error('document_selection_changed');
      const expectedVersion = workspace.row_version;
      if (!await confirmRebind({workspace, binding, document:before, refreshStructure}))
        throw Error(refreshStructure ? 'document_session_changed' : 'document_reconnect_cancelled');
      if (!valid() || workspace.row_version !== expectedVersion) throw Error('document_selection_changed');
      const current = getNativeView ? await readCurrentDocument() : await readRuntimeIdentity();
      if (expectedWindowKey && current.native_window_key !== expectedWindowKey) throw Error('document_window_identity_changed');
      if (current.document_session !== before.document_session) throw Error('document_session_changed');
      if (!valid()) throw Error('document_selection_changed');
      const idempotencyKey = `live-document-rebind:${workspaceKey}:${current.identity_operation_id}`;
      const result = await invoke('simulation.environment.live_document.rebind', {
        workspace_gid:workspaceKey, identity_operation_id:current.identity_operation_id,
        expected_document_session:binding.document_session, expected_workspace_row_version:expectedVersion,
        idempotency_key:idempotencyKey,
      }, {confirmation:true,idempotency:true,idempotencyKey});
      if (String(result?.workspace_gid) !== workspaceKey || result.document_session !== current.document_session)
        throw Error('document_environment_binding_mismatch');
      // Update concurrency tokens, not snapshot sessions or native node handles.
      // A dismissed dialog cannot undo a committed write. Reconcile only the
      // still-selected original version, never overwrite a newer workspace read.
      if (store?.state?.workspace === workspace && String(workspace?.workspace_gid) === workspaceKey
        && workspace.row_version === expectedVersion) {
        if (Number.isInteger(result.workspace_row_version)) workspace.row_version = result.workspace_row_version;
        if (result.cache_revision_hash) workspace.cache_revision_hash = result.cache_revision_hash;
      }
      if (!valid()) throw Error('document_selection_changed');
      return {...result, structure_verification:'unverified'};
    }
    async function calibrateLoadedCache({workspaceGid,document,viewer,isCurrent=()=>true}){
      const store=getStore?.(),workspace=store?.state?.workspace,tree=document?.product_tree,nodes=tree?.nodes,local=getLocalInteraction?.();
      if(document?.source_kind!=='teamcenter_cache_snapshot'||!Array.isArray(nodes)||!viewer?.node_map||!local||local.state!=='ready'||typeof viewer.visibility_context!=='string'||local.visibilityContext!==viewer.visibility_context)throw Error('cache_document_not_ready');
      const current=()=>{if(!isCurrent()||store?.state?.workspace!==workspace||String(workspace?.workspace_gid)!==String(workspaceGid)||document.product_tree!==tree||document.product_tree.nodes!==nodes||local.visibilityContext!==viewer.visibility_context||local.state==='outcome_unknown')throw Error('document_selection_changed');};
      const descriptors=root.AI00ViewerInteraction || (typeof require==='function'?require('./viewer_interaction'):null);
      const probe={...document,_cacheViewer:viewer},excluded=new Set((viewer.excluded||[]).map(entry=>entry.node_key));
      const selected=nodes.flatMap(item=>{
        if(!Object.hasOwn(viewer.node_map,item.cache_node_key)||excluded.has(item.cache_node_key))return [];
        try{return [{item,descriptor:descriptors.sourceDescriptor(probe,item)}];}catch{return [];}
      });
      const observed=new Map();let structureEpoch=null;
      try{
        current();
        for(let offset=0;offset<selected.length;offset+=128){
          const batch=selected.slice(offset,offset+128);
          const result=await local.readVisibility({source_nodes:batch.map(entry=>entry.descriptor)});current();
          if(!Number.isSafeInteger(result?.structure_epoch)||structureEpoch!==null&&result.structure_epoch!==structureEpoch)throw Error('cache_structure_changed');
          structureEpoch=result.structure_epoch;
          if(result.visibility_context!==viewer.visibility_context||!Array.isArray(result.nodes)||result.nodes.length!==batch.length)throw Error('document_selection_changed');
          for(let index=0;index<batch.length;index++){
            const value=result.nodes[index],{item,descriptor}=batch[index];
            if(value.source_node_id!==descriptor.source_node_id)throw Error('document_selection_changed');
            if(value.error_code)continue;
            if(value.visibility_state==='mixed')observed.set(item,{visible:null,visibility_state:'mixed'});
            else if(value.visibility_state==='visible'&&value.visible===true||value.visibility_state==='hidden'&&value.visible===false)observed.set(item,{visible:value.visible,visibility_state:value.visibility_state});
          }
        }
        current();
        const incomplete=descriptors.cacheIncompleteAncestors(viewer);
        viewer.native_visibility=Object.create(null);
        for(const item of nodes){
          const value=observed.get(item)||{visible:null,visibility_state:'unknown'};
          viewer.native_visibility[item.cache_node_key]={...value};
          Object.assign(item,incomplete.has(item.cache_node_key)&&value.visibility_state!=='mixed'?{visible:null,visibility_state:'unknown'}:value);
        }
        return {calibrated:observed.size,unknown_count:nodes.filter(item=>item.visibility_state==='unknown').length};
      }catch(error){for(const item of nodes){item.visible=null;item.visibility_state='unknown';}throw error;}
    }
    return {
      invalidateControlMappings,
      calibrateLoadedCache,
      readCurrentDocument,
      async reconnectDocument(workspaceGid, {isCurrent = () => true, expectedWindowKey} = {}) {
        const workspaceKey = String(workspaceGid);
        const before = await readCurrentDocument();
        if (expectedWindowKey && before.native_window_key !== expectedWindowKey) throw Error('document_window_identity_changed');
        const binding = await invoke('simulation.environment.live_document.binding.get', {workspace_gid:workspaceKey});
        if (!isCurrent()) throw Error('document_selection_changed');
        if (String(binding?.workspace_gid) !== workspaceKey || !binding.document_session
          || !['bound','importing'].includes(binding.state)) throw Error('document_binding_unavailable');
        if (binding.document_session === before.document_session)
          return {...binding, structure_verification:'unverified'};
        return rebindDocument(workspaceKey, before, binding, {isCurrent, expectedWindowKey});
      },
      async actOnProductNode({workspaceGid,document,nodeKey,action,isCurrent=()=>true,calibrateOnly=false}) {
        if(!['show','hide','highlight','unhighlight'].includes(action)) throw Error('node_action_unsupported');
        const node=document?.product_tree?.nodes?.find(n=>String(n.node_key)===String(nodeKey));
        const local=getLocalInteraction?.();
        const cached=document?.source_kind==='teamcenter_cache_snapshot';
        if(cached&&!node)throw Error('cache_scope_node_not_found');
        if(cached&&(!local||typeof ensureCachedReady!=='function'))throw Error('cache_document_not_ready');
        if(local){
          const workspace=getStore()?.state?.workspace;
          if(!isCurrent()||String(workspace?.workspace_gid)!==String(workspaceGid))throw Error('interaction_scope_mismatch');
          const descriptors=root.AI00ViewerInteraction || (typeof require==='function'?require('./viewer_interaction'):null);
          if(typeof local.executeIntent==='function'){
            if((!cached&&(document?.source_kind!=='teamcenter_online'||!document.source_selector))||!Number.isInteger(workspace.row_version))throw Error('model_node_runtime_identity_unavailable');
            const pending=nodeActionChain.catch(()=>{}).then(async()=>{
              const current=()=>{if(!isCurrent()||String(getStore()?.state?.workspace?.workspace_gid)!==String(workspaceGid))throw Error('document_selection_changed');};
              current();if(local.state==='outcome_unknown')throw Error('outcome_unknown');
              const cachedReady=cached?await ensureCachedReady(document,node):null;current();
              const input={scope:{workspace_gid:String(workspaceGid),document_gid:String(document.document_gid),expected_workspace_row_version:getStore().state.workspace.row_version},...(cached?{}:{source_selector:document.source_selector}),source_nodes:[descriptors.sourceDescriptor(document,node)],action};
              const ready=cached?cachedReady:await local.ensureReady(input);current();
              if(typeof ready?.visibility_context!=='string'||!ready.visibility_context)throw Error('interaction_visibility_context_invalid');
              const nodes=document.product_tree.nodes,signature=JSON.stringify(nodes.map(n=>[n.node_key,n.occurrence_path])),prior=calibratedDocuments.get(document);
              const readback=async()=>{
                calibratedDocuments.delete(document);
                for(const item of nodes){item.visible=null;item.visibility_state='unknown';}
                const byKey=new Map(nodes.map(item=>[String(item.node_key),item])),priority=new Set();let ancestor=node;
                while(ancestor&&!priority.has(ancestor)&&priority.size<2000){priority.add(ancestor);ancestor=ancestor.parent_key==null?null:byKey.get(String(ancestor.parent_key));}
                const selected=[...priority,...nodes.filter(item=>!priority.has(item))].slice(0,2000).flatMap(item=>{try{return [{item,descriptor:descriptors.sourceDescriptor(document,item)}];}catch{return [];}}),attempted=new Set(),observed=new Map();
                for(let offset=0;offset<selected.length;offset+=128){
                  const batch=selected.slice(offset,offset+128),result=await local.readVisibility({source_nodes:batch.map(entry=>entry.descriptor)});current();
                  if(document.product_tree.nodes!==nodes)throw Error('document_selection_changed');
                  if(result.visibility_context!=null&&result.visibility_context!==ready.visibility_context)throw Error('document_selection_changed');
                  const values=new Map(result.nodes.map(value=>[value.source_node_id,value]));
                  for(const {item,descriptor}of batch){
                    attempted.add(descriptor.source_node_id);
                    const value=values.get(descriptor.source_node_id),state=value?.visibility_state;
                    if(value?.error_code)continue;
                    if(state==='mixed')observed.set(item,{visible:null,visibility_state:state});
                    else if((state==='visible'&&value.visible===true)||(state==='hidden'&&value.visible===false))observed.set(item,{visible:value.visible,visibility_state:state});
                  }
                }
                const incomplete=cached?descriptors.cacheIncompleteAncestors(document._cacheViewer):null;
                if(cached)document._cacheViewer.native_visibility=Object.create(null);
                for(const item of nodes){
                  const native=observed.get(item)||{visible:null,visibility_state:'unknown'};
                  if(cached)document._cacheViewer.native_visibility[item.cache_node_key]={...native};
                  Object.assign(item,incomplete?.has(item.cache_node_key)?{visible:null,visibility_state:'unknown'}:native);
                }
                calibratedDocuments.set(document,{context:ready.visibility_context,nodes,signature,attempted});
              };
              if(calibrateOnly||prior?.context!==ready.visibility_context||prior.nodes!==nodes||prior.signature!==signature||!prior.attempted.has(String(node.node_key))){await readback();return {ok:true,calibrated:true,calibration_unknown:nodes.some(item=>item.visibility_state==='unknown')};}
              input.scope.expected_workspace_row_version=getStore().state.workspace.row_version;
              input.visibility_context=ready.visibility_context;
              let result;try{result=cached?await local.executeCachedIntent({workspace_gid:input.scope.workspace_gid,document_gid:input.scope.document_gid,source_nodes:input.source_nodes,action,visibility_context:ready.visibility_context}):await local.executeIntent(input);}catch(error){if(['visibility_calibration_required','cache_document_not_ready','outcome_unknown'].includes(error?.message)){calibratedDocuments.delete(document);for(const item of nodes){item.visible=null;item.visibility_state='unknown';}}throw error;}current();await readback();
              const {visible,...confirmed}=result;return {...confirmed,readback:true};
            });
            nodeActionChain=pending;return pending;
          }
          if(local.scope?.workspace_gid!==String(workspaceGid)||local.scope?.document_gid!==String(document?.document_gid))throw Error('interaction_scope_mismatch');
          return local.execute({source_nodes:[descriptors.sourceDescriptor(document,node)],action});
        }
        const onlineOccurrence=document?.source_kind==='teamcenter_online'
          && /^tc:.+/.test(String(node?.node_key||''));
        if((!onlineOccurrence&&!document?.product_tree?.document_session)||!node)
          throw Error('model_node_runtime_identity_unavailable');
        // Control only needs the selected environment binding here. The
        // Connector validates the bound session atomically inside the write
        // operation; issuing a separate identity plan on every click made a
        // local COM action pay the full durable-plan cost again.
        const binding=await invoke('simulation.environment.live_document.binding.get',{workspace_gid:String(workspaceGid)});
        const expectedSession=binding?.document_session;
        if(String(binding?.workspace_gid)!==String(workspaceGid)
          ||!/^sha256:[a-f0-9]{64}$/.test(String(expectedSession||'')))
          throw Error('document_environment_binding_mismatch');
        // This opaque locator is resolved against the current document's native
        // occurrence path in the local runtime. Never reuse an old numeric handle.
        const locator=/^cad:[a-f0-9]{64}$/.test(node.control_key||'') ? node.control_key : null;
        const isRawOnlineLocator=value=>/^tc:(?!sha256:)[^\s]+$/.test(String(value||''));
        const occurrencePath=Array.isArray(node.occurrence_path)?node.occurrence_path:[];
        const occurrenceUid=occurrencePath.length?occurrencePath.at(-1)?.occurrence_uid:null;
        const pathLocator=onlineOccurrence&&occurrenceUid?`tc:${occurrenceUid}`:null;
        const onlineLocator=onlineOccurrence&&isRawOnlineLocator(node.control_key) ? node.control_key
          : isRawOnlineLocator(pathLocator) ? pathLocator : null;
        const onlineNodeKey=onlineOccurrence&&isRawOnlineLocator(node.node_key) ? String(node.node_key) : null;
        let runtimeRootKey=null;
        if(onlineOccurrence&&!onlineLocator&&!onlineNodeKey&&document.role==='primary'
          &&node.parent_key==null&&Array.isArray(node.occurrence_path)&&node.occurrence_path.length===0
          &&node.has_children===false&&document.product_tree.nodes.length===1){
          const mappings=controlMappings;
          const scope=JSON.stringify([String(workspaceGid),expectedSession,binding.cache_revision_hash||'',String(nodeKey)]);
          const cached=mappings.get(document.product_tree);
          if(cached?.scope===scope) runtimeRootKey=cached.nodeKey;
          else {
          const outcome=await readTree({max_depth:1,force_refresh:false,expected_document_session:expectedSession});
          const step=outcome?.steps?.length===1?outcome.steps[0]:null;
          const nodes=step?.status==='succeeded'&&Array.isArray(step.result?.nodes)?step.result.nodes:[];
          const roots=nodes.filter(n=>n.parent_node_key==null);
          const leaves=nodes.filter(n=>n.has_more===false);
          if(roots.length!==1||leaves.length!==1||nodes.length>2||!nodes.length
            ||(nodes.length===2&&leaves[0].parent_node_key!==roots[0].node_key)
            ||!/^\d+$/.test(String(leaves[0].node_key)))throw Error('model_node_runtime_identity_unavailable');
          runtimeRootKey=String(leaves[0].node_key);
          if(mappings!==controlMappings) throw Error('model_node_relocation_required');
          mappings.set(document.product_tree,{scope,nodeKey:runtimeRootKey});
          }
        }
        // Teamcenter node_key is commonly a hash of the complete occurrence path.
        // VisMockup exposes the raw occurrence UID, so sending tc:sha256:* can
        // never match and causes an expensive full-tree COM scan. Fail closed
        // unless a raw occurrence locator was preserved by the tree projection.
        if(onlineOccurrence&&!onlineLocator&&!onlineNodeKey&&!runtimeRootKey) throw Error('model_node_runtime_identity_unavailable');
        if(!onlineOccurrence&&document.product_tree.document_session!==expectedSession&&!locator) throw Error('model_node_relocation_required');
        if(!isCurrent()||String(getStore()?.state?.workspace?.workspace_gid)!==String(workspaceGid)) throw Error('document_selection_changed');
        if(typeof executeNodeAction!=='function') throw Error('model_node_control_unavailable');
        const options={expected_document_session:expectedSession};
        if(onlineOccurrence && occurrencePath.length) options.occurrence_path=occurrencePath;
        try {
          return await executeNodeAction(runtimeRootKey||locator||onlineLocator||onlineNodeKey||String(node.node_key),action,options);
        } catch(error) {
          invalidateControlMappings();
          throw error; // Never replay a write whose outcome may be unknown.
        }
      },
      readProductTree(workspaceGid, { allowRebind = false } = {}) {
        invalidateControlMappings();
        const workspaceKey = String(workspaceGid);
        const key = `${workspaceKey}:${allowRebind ? 'rebind' : 'strict'}`;
        if (pendingTrees.has(key)) return pendingTrees.get(key);
        const pending = (async () => {
          trace('live_tree_verification_started',{workspace_gid:workspaceKey});
          const before = await readRuntimeIdentity();
          let binding = await invoke('simulation.environment.live_document.binding.get', { workspace_gid: workspaceKey });
          if (String(binding?.workspace_gid) !== workspaceKey || binding.document_session !== before.document_session) {
            trace('live_tree_binding_mismatch',{workspace_gid:workspaceKey,level:'warn',reason:allowRebind?'rebind_allowed':'strict_binding_required'});
            if (!allowRebind || !binding?.document_session) throw new Error('document_environment_binding_mismatch');
            binding = await rebindDocument(workspaceKey, before, binding, {refreshStructure:true});
          }
          const outcome = await readTree();
          const after = await readRuntimeIdentity();
          if (after.document_session !== before.document_session) throw new Error('document_session_changed');
          trace('live_tree_session_verified',{workspace_gid:workspaceKey,reason:'identity_before_after_matches'});
          const step = outcome?.steps?.length === 1 ? outcome.steps[0] : null;
          if (step?.status !== 'succeeded' || !Array.isArray(step.result?.nodes)) throw new Error('vismockup_tree_result_invalid');
          const nodes = step.result.nodes.map((node, index) => ({ ...node, parent_key: node.parent_node_key, child_order: index }));
          const parents = new Set(nodes.map(node => node.parent_key).filter(key => key != null));
          trace('live_tree_result_verified',{workspace_gid:workspaceKey,node_count:nodes.length,complete:!nodes.some(node=>node.has_more&&!parents.has(node.node_key))});
          return { state: 'ready', nodes, node_count: nodes.length,
            complete: !nodes.some(node => node.has_more && !parents.has(node.node_key)),
            document_session: before.document_session, observed_at: new Date().toISOString() };
        })().catch(error=>{trace('live_tree_verification_failed',{workspace_gid:workspaceKey,error_code:error.message});throw error;}).finally(() => pendingTrees.delete(key));
        pendingTrees.set(key, pending);
        return pending;
      },
      async adopt({ document, name, operation_key }) {
        const current = await readCurrentDocument();
        if (current.document_session !== document.document_session) throw new Error('document_session_changed');
        return invoke('simulation.environment.live_document.adopt', {
          identity_operation_id: current.identity_operation_id, name,
          document_display_name: current.display_name, idempotency_key: operation_key,
        }, { version: 2, idempotency: true, idempotencyKey: operation_key });
      },
      async importHierarchies({ document, workspace_gid, operation_key, onProgress = () => {} }) {
        if (typeof readHierarchyInventory !== 'function') throw new Error('hierarchy_inventory_unavailable');
        let start = 0, imported = 0, total = null;
        for (;;) {
          const outcome = await readHierarchyInventory({ document_session: document.document_session,
            start_index: start, page_size: 4, max_nodes: 100000 });
          const step = outcome?.steps?.length === 1 ? outcome.steps[0] : null;
          const page = step?.result;
          if (!outcome?.plan_id || step?.status !== 'succeeded' || page?.document_session !== document.document_session
            || page?.start_index !== start || !Array.isArray(page?.hierarchies)) throw new Error('hierarchy_inventory_unavailable');
          const applied = await invoke('simulation.environment.live_document.inventory.apply', {
            workspace_gid: String(workspace_gid), inventory_operation_id: outcome.plan_id,
            idempotency_key: `${operation_key}:ah:${start}`,
          }, { idempotency: true, idempotencyKey: `${operation_key}:ah:${start}` });
          imported += Number(applied?.imported_hierarchy_count || 0);
          total = Number(applied?.total_hierarchies ?? page.total_hierarchies ?? 0);
          onProgress({ imported, total, complete: applied?.complete === true });
          if (applied?.complete === true && applied?.next_index == null) return { imported, total };
          if (!Number.isInteger(applied?.next_index) || applied.next_index <= start) throw new Error('hierarchy_inventory_cursor_invalid');
          start = applied.next_index;
        }
      },
      async openWorkspace(gid, options) {
        const store = getStore();
        if (!store?.openWorkspace) throw new Error('environment_store_unavailable');
        const result = await store.openWorkspace(gid, options);
        await refreshWorkspace?.(store.state?.workspace || result);
        return result;
      },
    };
  }

  function createController({ adapter, onChange = () => {}, makeKey = () => root.crypto.randomUUID() } = {}) {
    const operations = new Map();
    let generation = 0;
    let expectedSelection = null;
    const state = { visible: false, phase: 'idle', document: null, name: '', error: '', operationKey: null,
      binding: '未绑定', model: '未开始', ah: '未开始' };
    const emit = () => onChange({ ...state });
    const ready = () => ['readCurrentDocument', 'adopt', 'openWorkspace'].every(key => typeof adapter?.[key] === 'function');
    const current = token => token === generation && state.visible;
    const validName = name => typeof name === 'string' && name.trim().length > 0 && name.length <= 200;
    async function selectWorkspace(operation, token) {
      if (!current(token) || operation.selecting) return;
      const selection = { token, workspaceGid: String(operation.result.workspace_gid) };
      expectedSelection = selection;
      Object.assign(operation, { selecting: true, error: '', errorCode: null });
      Object.assign(state, operation); emit();
      try {
        // Integration checks this again after reads, before committing selection.
        await adapter.openWorkspace(operation.result.workspace_gid, { isCurrent: () => current(token) });
      } catch (error) {
        Object.assign(operation, { errorCode: 'workspace_open_failed', error: `workspace_open_failed：${error.message || '环境打开失败'}；绑定已保留，可重试打开环境` });
      } finally {
        operation.selecting = false;
        if (expectedSelection === selection) expectedSelection = null;
        if (current(token)) { Object.assign(state, operation); emit(); }
      }
    }
    return {
      state,
      async open(displayName = '—') {
        const token = ++generation;
        Object.assign(state, { visible: true, phase: 'reading', document: null, displayName, name: '', error: '',
          operationKey: null, binding: '未绑定', model: '未开始', ah: '未开始', result: null, selecting: false, errorCode: null });
        if (!ready()) { state.phase = 'unavailable'; state.error = unavailable; emit(); return; }
        emit();
        try {
          const document = await adapter.readCurrentDocument();
          if (!current(token)) return;
          if (typeof document?.document_session !== 'string' || !document.document_session.trim() || !document.display_name) throw new Error('当前连接未返回可信文档会话');
          // Copy the authoritative session once; names and paths never identify a session.
          state.document = Object.freeze(structuredClone(document));
          state.displayName = document.display_name;
          state.name = document.display_name;
          const operation = operations.get(document.document_session);
          Object.assign(state, operation || { phase: 'ready' });
          if (operation?.phase === 'submitting') state.error = '该文档绑定请求仍在处理中，请保留操作编号核对结果';
        } catch (error) { if (current(token)) { state.phase = 'error'; state.error = error.message || '读取当前文档失败'; } }
        if (current(token)) emit();
      },
      setName(name) { if (state.phase === 'ready') { state.name = typeof name === 'string' ? name : ''; state.error = validName(name) ? '' : '环境名称须为 1–200 个字符'; emit(); } },
      dismiss() { ++generation; state.visible = false; emit(); },
      selectionChanged(workspaceGid) {
        if (workspaceGid != null && expectedSelection && current(expectedSelection.token)
          && String(workspaceGid) === expectedSelection.workspaceGid) return;
        ++generation;
        if (state.visible) { state.phase = 'superseded'; state.error = '环境选择已改变，请关闭此窗口；已有请求可通过操作编号核对'; emit(); }
      },
      async confirm() {
        if (!state.visible || state.phase !== 'ready' || !ready()) return;
        if (!validName(state.name)) { state.error = '环境名称须为 1–200 个字符'; emit(); return; }
        const token = generation;
        const document = state.document;
        const name = state.name.trim();
        const operation = { phase: 'submitting', operationKey: makeKey(), binding: '绑定中', model: '未开始', ah: '未开始', error: '' };
        operations.set(document.document_session, operation);
        Object.assign(state, operation); emit();
        try {
          const result = await adapter.adopt({ document, name, operation_key: operation.operationKey });
          if (!result?.workspace_gid || !result.version_gid || !result.model_document_gid || result.state !== 'importing' || typeof result.created !== 'boolean') throw new Error('绑定及主模型登记结果尚未确认，请使用操作编号核对');
          Object.assign(operation, { phase: 'bound', result: Object.freeze({ ...result }), binding: result.created ? '已绑定 · 导入中' : '已复用绑定 · 导入中', model: '已登记', ah: '待导入' });
          // Display the committed model immediately; native AH enumeration can
          // take time and must not delay the model-file panel.
          await selectWorkspace(operation, token);
          if (operation.errorCode === 'workspace_open_failed') return;
          if (typeof adapter.importHierarchies === 'function') {
            operation.ah = '读取中';
            if (current(token)) { Object.assign(state, operation); emit(); }
            const summary = await adapter.importHierarchies({ document, workspace_gid: result.workspace_gid,
              operation_key: operation.operationKey, onProgress(progress) {
                operation.ah = progress.complete ? `已导入 ${progress.imported} 个` : `导入中 ${progress.imported}/${progress.total ?? '…'}`;
                if (current(token)) { Object.assign(state, operation); emit(); }
              } });
            operation.ah = `已导入 ${summary.imported} 个`;
            operation.binding = result.created ? '已绑定' : '已复用绑定';
          }
        } catch (error) {
          if (operation.result) {
            Object.assign(operation, { phase: 'bound', errorCode: 'hierarchy_import_failed',
              ah: '导入未完成', error: `${error.message || '备选层次结构导入失败'}；环境和主模型已保存，可稍后继续导入` });
            if (current(token)) { Object.assign(state, operation); emit(); }
            return;
          }
          Object.assign(operation, { phase: 'unknown', error: `${error.message || '请求结果未知'}；请保留操作编号核对，暂不重复提交` });
          if (current(token)) { Object.assign(state, operation); emit(); }
          return;
        }
        if (current(token)) { Object.assign(state, operation); emit(); }
      },
      async retrySelection() {
        if (state.phase !== 'bound' || state.errorCode !== 'workspace_open_failed') return;
        const operation = operations.get(state.document?.document_session);
        if (operation?.result) await selectWorkspace(operation, generation);
      },
    };
  }

  function mount({ adapter, document = root.document } = {}) {
    const entry = document.getElementById('btnAdoptCurrentDocument');
    if (!entry) return;
    const overlay = document.getElementById('liveDocumentAdoption');
    const field = document.getElementById('adoptionName');
    const confirm = document.getElementById('adoptionConfirm');
    const controller = createController({ adapter, onChange(state) {
      overlay.classList.toggle('hidden', !state.visible);
      document.getElementById('adoptionDocument').textContent = state.displayName || '—';
      if (field.value !== state.name) field.value = state.name;
      field.disabled = state.phase !== 'ready';
      const retry = state.phase === 'bound' && state.errorCode === 'workspace_open_failed';
      confirm.textContent = retry ? '重试打开环境' : '创建环境';
      confirm.disabled = state.selecting || (!retry && (state.phase !== 'ready' || !state.name.trim() || state.name.length > 200));
      document.getElementById('adoptionBinding').textContent = state.binding;
      document.getElementById('adoptionModel').textContent = state.model;
      document.getElementById('adoptionAh').textContent = state.ah;
      document.getElementById('adoptionError').textContent = state.error;
      document.getElementById('adoptionOperation').textContent = state.operationKey ? `操作编号：${state.operationKey}` : '';
    } });
    entry.onclick = () => { void controller.open(document.getElementById('vmDocumentLabel').textContent); document.getElementById('adoptionClose').focus(); };
    const dismiss = () => { controller.dismiss(); entry.focus(); };
    document.getElementById('adoptionClose').onclick = dismiss;
    document.getElementById('adoptionCancel').onclick = dismiss;
    field.oninput = () => controller.setName(field.value);
    confirm.onclick = () => { void (controller.state.phase === 'bound' ? controller.retrySelection() : controller.confirm()); };
    overlay.onkeydown = event => {
      if (event.key === 'Escape') { event.preventDefault(); dismiss(); }
      if (event.key === 'Tab') {
        const focusable = Array.from(overlay.querySelectorAll('button:not(:disabled), input:not(:disabled)'));
        const first = focusable[0], last = focusable.at(-1);
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    };
    const store = root._simulationEnvironmentWorkspace?.store;
    let selected = store?.state.workspace?.workspace_gid || null;
    const unsubscribe = store?.subscribe(state => {
      const next = state.workspace?.workspace_gid || null;
      if (selected !== next) { selected = next; controller.selectionChanged(next); }
    });
    const documentChanged = () => controller.selectionChanged();
    // Invalidate at user selection intent, before the workspace read completes.
    const records = document.getElementById('environmentRecordsBody');
    const selectRecord = event => {
      if (event.target.closest('[data-record-gid],[data-workspace-gid]')) controller.selectionChanged();
    };
    records?.addEventListener('click', selectRecord, true);
    root.addEventListener('ai00:live-document-changed', documentChanged);
    return { controller, dispose() { unsubscribe?.(); records?.removeEventListener('click', selectRecord, true); root.removeEventListener('ai00:live-document-changed', documentChanged); controller.dismiss(); } };
  }
  root.AI00LiveDocumentAdoption = { createAdapter, createController, mount, unavailable };
  if (typeof module !== 'undefined') module.exports = root.AI00LiveDocumentAdoption;
})(typeof window !== 'undefined' ? window : globalThis);
