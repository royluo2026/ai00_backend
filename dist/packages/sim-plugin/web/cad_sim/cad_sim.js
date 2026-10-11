/**
 * cad_sim.js — 数模仿真控制界面 v3
 * VisMockup 作为独立窗口运行，此页面负责：连接控制、BOP 结构树、文件打开、节点高亮
 */

// Production Web must never call a workstation loopback service. Legacy handlers
// remain fail-closed until each operation is routed through a governed Simulation
// Capability and AI00 Connector execution plan.
async function _bridge(_ns, _method, ..._args) {
  return {
    success: false,
    error: 'local_bridge_disabled: 请使用 AI00 Connector 受治理流程',
    data: {},
  };
}

const _eAPI = () => window.electronAPI || window.parent?.electronAPI;
const $ = id => document.getElementById(id);
function _simulationDebug(stage,detail={}) {
  try {
    const api=window.AI00ViewerInteraction?.frameAPI(window);
    void api?.debugRecord?.({stage,workspace_gid:window._simulationEnvironmentWorkspace?.store?.state?.workspace?.workspace_gid,...detail})?.catch(()=>{});
  } catch (_) { /* Diagnostics cannot interrupt model work. */ }
}
window._simulationDebug=_simulationDebug;

async function _invokeCapability(id,payload={}, {confirmation=false,idempotency=false,version=1,idempotencyKey,approvalReference,expectedResourceVersion}={}) {
  if (approvalReference) throw new Error('downstream_confirmation_receipt_unavailable');
  const envelope = {
    version,
    payload,
    idempotency_key: idempotencyKey || (idempotency ? payload.idempotency_key : undefined),
  };
  // BOP projection uses optimistic concurrency.  The row version belongs in
  // the invocation envelope as well as the closed capability payload; putting
  // it only in payload makes the Gateway reject the request before the
  // provider can build a preview.
  if (expectedResourceVersion !== undefined && expectedResourceVersion !== null && String(expectedResourceVersion).trim()) {
    envelope.expected_resource_version = String(expectedResourceVersion);
  }
  const started=performance.now(),trace_id=window.crypto?.randomUUID?.(),poll=id==='simulation.vismockup.command.get';
  if(!poll)_simulationDebug('capability_started',{trace_id,capability_id:id,capability_version:version,operation_id:payload.operation_id});
  try {
    const result=await window.AI00Business.invoke(id, envelope, confirmation ? async () => true : undefined);
    if(!poll)_simulationDebug('capability_completed',{trace_id,capability_id:id,capability_version:version,operation_id:result?.operation_id,elapsed_ms:performance.now()-started});
    return result;
  } catch(error) {
    _simulationDebug('capability_failed',{trace_id,capability_id:id,capability_version:version,operation_id:payload.operation_id,error_code:error?.message||'capability_failed',elapsed_ms:performance.now()-started});throw error;
  }
}

async function _waitVisMockupCommand(operationId, maxAttempts = 750) {
  let lastStatus;const started=performance.now();
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    let command;
    try {
      command = await _invokeCapability('simulation.vismockup.command.get', { operation_id: operationId });
    } catch (error) {
      if (error?.message !== 'provider_failed') throw error;
      await new Promise(resolve => setTimeout(resolve, 200));
      continue;
    }
    if(command.status!==lastStatus){lastStatus=command.status;_simulationDebug('command_progress',{operation_id:operationId,status:command.status,elapsed_ms:performance.now()-started});}
    if (['completed', 'failed', 'cancelled', 'outcome_unknown', 'manual_review_required', 'expired'].includes(command.status)) {
      for(const step of command.outcome?.steps||[])_simulationDebug('command_step',{operation_id:operationId,status:step.status,error_code:step.error_code,message:step.step_id});
      if (command.status !== 'completed') {
        const error = command.outcome?.steps?.at(-1)?.error_code || command.status;
        throw new Error(error);
      }
      return command.outcome;
    }
    await new Promise(resolve => setTimeout(resolve, 200));
  }
  throw new Error('connector_command_timeout');
}

const _visReadQueues = new Map();
const _visQueuedReadCapabilities = new Set([
  'simulation.vismockup.document.identity.read.request',
  'simulation.vismockup.tree.read.request',
  'simulation.vismockup.document.hierarchy_inventory.read.request',
  'simulation.teamcenter.product_structure.observe.request',
  'simulation.teamcenter.product_structure.children.read.request',
  'simulation.teamcenter.node_properties.read.request',
  'simulation.teamcenter.product.search.request',
  'simulation.teamcenter.revision_rule.search.request',
  'simulation.teamcenter.product_structure.page.read.request',
]);
const _visWriteCommandCapabilities = new Set([
  'simulation.environment.runtime_package.open.request',
  'simulation.teamcenter.visualization.launch.request',
  'simulation.teamcenter.visualization.insert.request',
  'simulation.vismockup.application.attach.request',
  'simulation.vismockup.application.launch.request',
  'simulation.vismockup.model.close.request',
  'simulation.vismockup.model.insert.request',
  'simulation.vismockup.model.open.request',
  'simulation.vismockup.node.selection.change.request',
  'simulation.vismockup.node.visibility.change.request',
  'simulation.vismockup.visibility.change.request',
]);
function _newVisCommandIdempotencyKey(capabilityId) {
  const operationId = window.crypto?.randomUUID?.()
    || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${capabilityId}:${operationId}`;
}
async function _requestVisMockupCommand(capabilityId, payload = {}, { confirmation = true, waitAttempts = 750, idempotencyKey, version = 1 } = {}) {
  const changesStructure = /\.(?:model\.(?:open|insert|close)|application\.(?:attach|launch)|visualization\.(?:launch|insert)|runtime_package\.open)\.request$/.test(capabilityId);
  const operationIdempotencyKey = idempotencyKey || payload.idempotency_key
    || (_visWriteCommandCapabilities.has(capabilityId) ? _newVisCommandIdempotencyKey(capabilityId) : undefined);
  const execute = async () => {
    if (changesStructure) window._invalidateModelControlMappings?.();
    try {
    let operation;
    for (let attempt = 0; ; attempt++) {
      try {
        operation = await _invokeCapability(capabilityId, payload, {
          version,
          confirmation,
          idempotency: Boolean(operationIdempotencyKey),
          idempotencyKey: operationIdempotencyKey,
        });
        break;
      } catch (error) {
        // Admission only: an old read/session can still hold the server lease.
        // Never replay an admitted outcome, a write, or a permission failure.
        if (!_visQueuedReadCapabilities.has(capabilityId) || error?.message !== 'reconciliation_required' || attempt >= 59) throw error;
        await new Promise(resolve => setTimeout(resolve, 5000));
      }
    }
    return await _waitVisMockupCommand(operation.operation_id, waitAttempts);
    } finally {
      if (changesStructure) window._invalidateModelControlMappings?.();
    }
  };
  if (!_visQueuedReadCapabilities.has(capabilityId)) return execute();
  // Each caller gets a fresh observation. Sharing identity results could hide a
  // document switch; overlapping equivalent plans are rejected by the server.
  const previous = _visReadQueues.get(capabilityId) || Promise.resolve();
  const pending = previous.catch(() => {}).then(execute);
  _visReadQueues.set(capabilityId, pending);
  try { return await pending; }
  finally { if (_visReadQueues.get(capabilityId) === pending) _visReadQueues.delete(capabilityId); }
}

let _connectorPairingApproval = null;
async function _requireConnectorRuntime() {
  const api = _eAPI();
  if (!api?.getConnectorState) throw new Error('desktop_connector_unavailable');
  for (let attempt = 0; attempt < 60; attempt++) {
    const state = await api.getConnectorState();
    if (state?.status === 'ready' && state?.health === 'healthy') {
      if (state.pairing?.state === 'created') {
        if (_connectorPairingApproval?.id !== state.pairing.id) {
          _connectorPairingApproval = {
            id: state.pairing.id,
            promise: window.AI00Business.invoke('simulation.connector.pairing.approve', {
              version: 2,
              payload: { pairing_id: state.pairing.id, expected_version: 1 },
            }, async () => (await window.AI00Dialogs.confirm('确认将此 AI00 App 绑定到当前账号？'))),
          };
        }
        try { await _connectorPairingApproval.promise; }
        catch (error) {
          // Another concurrent detector may have completed the same version-bound
          // approval first. Poll the authoritative Connector state in that case.
          if (error?.message !== 'pairing_version_conflict') throw error;
        }
      }
      if (!state.pairing || state.pairing.state === 'activated') return state;
      await new Promise(resolve => setTimeout(resolve, 250));
      continue;
    }
    if (state?.status !== 'starting') throw new Error(state?.diagnostic || 'desktop_connector_unavailable');
    await new Promise(resolve => setTimeout(resolve, 250));
  }
  throw new Error('desktop_connector_start_timeout');
}

function _visMockupProbeResult(outcome) {
  const value = outcome?.steps?.at(-1)?.result || {};
  return {
    ready: value.ready ?? value.Ready ?? false,
    status: value.status ?? value.Status ?? 'unavailable',
    process_ready: value.process_ready ?? value.ProcessReady ?? false,
    document_ready: value.document_ready ?? value.DocumentReady ?? false,
    product_version: value.product_version ?? value.ProductVersion ?? '',
    pid: value.pid ?? value.Pid ?? value.process_id ?? value.ProcessId ?? null,
    document_name: value.document_name ?? value.DocumentName ?? value.document_path ?? value.DocumentPath ?? '',
  };
}



async function _artifactFromFile(file) {
return (await window.AI00Business.invoke('base.artifact.import',{version:1,payload:{},native_io:{select:'model'}})).artifact_ref;
}

async function _modelArtifactFromFile() {
  return window.AI00Business.invoke('base.artifact.import', { version: 1, payload: {}, native_io: { select: 'model' } });
}

// ── VisMockup 状态 ────────────────────────────────────────────────────────────
let _vmConnected = false;
let _vmDocumentReady = false;
let _vmAction = 'connect';
let _nativeStatusUnsubscribe = null;
let _nativeViewportOccluded = false;
let _workspacePageVisible = true;
let _viewerDocumentManager = null;
let _catiaScanDone = false;   // scan_vis_catia_map 是否完成

// ── Vis 结构树状态 ─────────────────────────────────────────────────────────────
let _visExpandedKeys = new Set();
let _visNodeMap      = {};   // key → { node, nodeEl, visibilityEl }
const _alternateVisibilityChecks = new Set();
let _alternateVisibilityBatchPending = false;
let _visCtxMenu      = null;
let _alternateContextMenu = null;
let _pendingTeamcenterOnlineBinding = null;
let _visTreeLoaded   = false; // 是否已成功加载过结构树（缓存命中时跳过加载指示）
let _visTreeSnapshot = null;
const VM_FULL_SYNC_DEPTH = 8; // 采集固定全量；下拉框只控制本地展开层级
let _bopVmBindingDraft = null;
let _modelDocumentCollection = null;
let _modelDocumentWorkspaceGid = null;
let _alternateHierarchyWorkspaceGid = null;
let _resourceWorkspaceGid = null;

function _setVmDocumentReady(ready) {
  _vmDocumentReady = Boolean(ready);
  document.querySelectorAll('.cs-alternate-context-menu [data-online-mode="insert"]').forEach(button => {
    button.disabled = !_vmDocumentReady;
    button.title = _vmDocumentReady ? '' : '当前 VisMockup 没有活动文档';
  });
}

// ── BOP 状态 ──────────────────────────────────────────────────────────────────
let _bopVersions      = [];
let _bopVersionLoadError = null;
let _bopEntries       = [];
let _bopEntryIndex    = {};   // gid → entry（含完整 parts 数组）
let _bopChildMap      = {};   // parent_gid → [entry...]（按 sort_order 排序）
let _bopSubtreeParts  = {};   // gid → 子树内唯一 catia_occ 总数
let _bopSubtreeMatched = {};  // gid → 子树内与 VM 已匹配的唯一 catia_occ 数
let _vmCatiaSet       = new Set();  // scan 后 VM 中存在的所有 catiaOccurrenceName
let _selectedBopGid   = null;
let _tasks          = [];

// ── 详情面板状态 ──────────────────────────────────────────────────────────────
let _dpOpen         = false;
let _dpBopRootGid   = null;   // 当前详情面板的 BOP 树根 gid
let _dpBopSelGid    = null;   // 当前选中的树节点 gid
let _dpExpandedGids = new Set(); // 已展开的 gid
let _teamcenterDetailRequest = 0;
let _teamcenterDetailSelection = null;
function _invalidateTeamcenterNodeDetail() {
  _teamcenterDetailRequest += 1;
  _teamcenterDetailSelection = null;
}

// BOP 节点类型标签
const _BOP_NT_MAP = {
  'line_process':     { label: '线体',   color: '#89b4fa' },
  'station_process':  { label: '工位',   color: '#74c7ec' },
  'operator_process': { label: '岗位',   color: '#a6e3a1' },
  'operation':        { label: '工序',   color: '#fab387' },
  'knowledge':        { label: '知识',   color: '#2d9444' },
  'rule':             { label: '规则',   color: '#d4a017' },
};

// ── 初始化 ───────────────────────────────────────────────────────────────────
async function init() {
  $('btnSimulationDebug')?.addEventListener('click',async()=>{
    try{const api=window.AI00ViewerInteraction?.frameAPI(window);if(!api?.debugOpen)throw Error('请在 AI00 桌面端查看本机调试日志');await api.debugOpen({});}
    catch(error){_cmdShow(error?.message||'调试窗口打开失败','err');}
  });
  _applyTheme();
  _initWorkspaceLayout();
  _bindToolbar();
  _bindCmdBar();
  _bindModal();
  _bindBopPanel();
  _bindVisPanel();
  _bindModelDocuments();
  _bindPanelWidthHandles();
  _bindEnvironmentActions();
  _initGovernedCapture();
  _initVmVersioning();
  _initDetailPanel();
  _viewerDocumentManager?.dispose();
  _viewerDocumentManager=window.AI00ViewerDocumentManager?.createManager({document,getAPI:()=>_eAPI()?.visMockupNativeView,isVisible:()=>_workspacePageVisible&&!$('csDetailPanel')?.classList.contains('hidden'),diagnostic:_simulationDebug});
  _setVmStatus('disconnected', '打开模型时启动专用 VisMockup');
  await Promise.all([_loadBopVersions(), _loadTasks()]);
}

function _applyTheme() {
  try {
    const t = window.parent?.document?.documentElement?.getAttribute('data-theme') || 'dark';
    document.documentElement.setAttribute('data-theme', t);
  } catch(_) {}
}

// ── VisMockup 连接 ────────────────────────────────────────────────────────────

/** 页面加载时自动尝试连接已运行的 VisMockup（不启动新进程） */
async function _tryAutoConnect() {
  _setLaunchButton('connect');
  try {
    await _requireConnectorRuntime();
    const outcome = await _requestVisMockupCommand('simulation.vismockup.application.attach.request', {}, { confirmation: false });
    const probe = _visMockupProbeResult(outcome);
    if (probe.ready) return _onConnected(probe);
    _vmConnected = false;
    _setVmDocumentReady(false);
    _setLaunchButton(probe.process_ready ? 'reconnect' : 'launch');
    _setVmStatus(
      probe.process_ready ? 'error' : 'disconnected',
      probe.process_ready ? 'VisMockup 已打开，但当前实例无法接入自动化' : 'VisMockup 未运行',
    );
  } catch (error) {
    _vmConnected = false;
    _setVmDocumentReady(false);
    _setLaunchButton('connect');
    const connectorError = /^(desktop_connector_|runtime_)/.test(error?.message || '');
    const message = error?.message || '未知错误';
    _setVmStatus('error', connectorError ? '本地连接器未就绪'
      : message.includes('reconciliation_required') ? '连接任务等待结果核对'
      : `VisMockup 连接检查失败：${message}`);
  }
}

function _initWorkspaceLayout() {
  const shell = $('simulationShell');
  if (!shell) return;

  const setPressed = (button, pressed) => button?.setAttribute('aria-pressed', String(pressed));
  const objectPanel = $('simulationObjectPanel');
  const environmentPanel = $('simulationEnvironmentPanel');
  const environmentToggle = $('btnToggleEnvironmentPanel');
  const environmentRecords = $('environmentRecordsPanel');
  const visPanel = $('visPanel');
  const modelDocumentsPanel = $('modelDocumentsPanel');
  const resourcePanel = $('resourceLibraryPanel');
  const documentToggle = $('btnToggleVisPanel');
  const resourceToggle = $('btnToggleResourceSection');
  if (objectPanel) {
    objectPanel.append(environmentToggle, environmentRecords, resourceToggle, resourcePanel);
  }
  if (environmentPanel) {
    environmentPanel.append(documentToggle, visPanel);
  }
  const vmTreeActions = visPanel?.querySelector('.cs-vis-actions');
  const actionBar = $('ai00ActionBar');
  const actionSpacer = actionBar?.querySelector('.cs-toolbar-spacer');
  if (vmTreeActions && actionBar && actionSpacer) actionBar.insertBefore(vmTreeActions, actionSpacer);
  const setSectionOpen = (panel, toggle, open) => {
    panel?.classList.toggle('collapsed', !open);
    toggle?.setAttribute('aria-expanded', String(open));
    const icon = toggle?.querySelector('.cs-capsule-icon');
    if (icon) icon.textContent = open ? '⌃' : '⌄';
  };
  const setObjectPanelOpen = open => {
    objectPanel?.classList.toggle('collapsed', !open);
    const toggle = $('btnResourceMode');
    toggle?.setAttribute('aria-pressed', String(open));
    if (toggle) toggle.title = open ? '折叠产品与资源面板' : '展开产品与资源面板';
    _notifyNativeViewportBounds();
  };
  documentToggle?.addEventListener('click', () => {
    const open = visPanel?.classList.contains('collapsed');
    setSectionOpen(visPanel, documentToggle, open);
    modelDocumentsPanel?.classList.toggle('collapsed', !open);
  });
  resourceToggle?.addEventListener('click', () => setSectionOpen(resourcePanel, resourceToggle, resourcePanel?.classList.contains('collapsed')));
  $('btnResourceMode')?.addEventListener('click', event => {
    const enabled = objectPanel?.classList.contains('collapsed');
    setObjectPanelOpen(enabled);
    shell.classList.toggle('resource-mode', enabled);
    shell.classList.remove('focus-mode');
    setPressed(event.currentTarget, enabled);
    setPressed($('btnFocus3d'), false);
    setPressed($('btnToggleBopPanel'), true);
    _notifyNativeViewportBounds();
  });
  $('btnToggleBopPanel')?.addEventListener('click', event => {
    const hidden = shell.classList.toggle('bop-hidden');
    shell.classList.remove('focus-mode');
    setPressed(event.currentTarget, !hidden);
    setPressed($('btnFocus3d'), false);
    _notifyNativeViewportBounds();
  });
  $('btnFocus3d')?.addEventListener('click', event => {
    const enabled = !shell.classList.contains('focus-mode');
    shell.classList.toggle('focus-mode', enabled);
    shell.classList.remove('bop-hidden');
    setPressed(event.currentTarget, enabled);
    setPressed($('btnToggleBopPanel'), !enabled);
    _notifyNativeViewportBounds();
  });

  const nativeSlot = $('nativeViewportSlot');
  const detailPanel = $('csDetailPanel');
  const placeholder = $('workspacePlaceholder');
  const labels = {
    tasks: '任务与结果将在此汇总仿真任务、执行状态与结果。',
    history: '操作记录将在此展示当前仿真环境的受治理操作轨迹。',
    issues: '问题提报入口正在建设中。',
    files: '工艺文件入口正在建设中。',
  };
  document.querySelectorAll('[data-workspace-tab]').forEach(button => {
    button.addEventListener('click', () => {
      const tab = button.dataset.workspaceTab;
      document.querySelectorAll('[data-workspace-tab]').forEach(item => item.classList.toggle('active', item === button));
      const showNative = tab === 'viewer' || tab === 'detail';
      nativeSlot?.classList.toggle('hidden', !showNative);
      detailPanel?.classList.toggle('hidden', !showNative);
      placeholder?.classList.toggle('hidden', showNative);
      if (placeholder && !showNative) placeholder.textContent = labels[tab] || '';
      if (tab === 'detail' && detailPanel && !detailPanel.classList.contains('open')) $('dpHandle')?.click();
      _viewerDocumentManager?.visibilityChanged();
      _notifyNativeViewportBounds();
    });
  });

  $('xiaorouBall')?.addEventListener('click', _openXiaorou);
  $('xiaorouChatClose')?.addEventListener('click', () => _setXiaorouOpen(false));
  $('xiaorouChatSend')?.addEventListener('click', _sendXiaorouMessage);
  $('xiaorouChatInput')?.addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void _sendXiaorouMessage();
    }
  });

  new MutationObserver(_syncNativeViewportOcclusion).observe(document.body, {
    attributes: true, attributeFilter: ['class','open'], childList: true, subtree: true,
  });
  window.addEventListener('ai00:dialog-visibility',_syncNativeViewportOcclusion);
  _syncNativeViewportOcclusion();

  if (nativeSlot && typeof ResizeObserver === 'function') {
    new ResizeObserver(_notifyNativeViewportBounds).observe(nativeSlot);
  }
  nativeSlot?.addEventListener('pointerdown', () => {
    const visMockupNativeView = _eAPI()?.visMockupNativeView;
    void visMockupNativeView?.focus?.();
  });

  const visMockupNativeView = _eAPI()?.visMockupNativeView;
  if (visMockupNativeView?.onStatus) {
    _nativeStatusUnsubscribe?.();
    _nativeStatusUnsubscribe = visMockupNativeView.onStatus(_applyNativeViewStatus);
  }
  void visMockupNativeView?.status?.().then(_applyNativeViewStatus).catch(() => {});
  window.addEventListener('pagehide', () => {
    _nativeStatusUnsubscribe?.();
    _nativeStatusUnsubscribe = null;
    void visMockupNativeView?.detach?.();
  }, { once: true });
  window.addEventListener('resize', _notifyNativeViewportBounds);
}

function _openXiaorou() {
  const chat = $('xiaorouChat');
  _setXiaorouOpen(chat?.classList.contains('hidden'));
}

function _setXiaorouOpen(open) {
  $('simulationShell')?.classList.toggle('xiaorou-open', open);
  $('xiaorouChat')?.classList.toggle('hidden', !open);
  const toggle = $('xiaorouBall');
  toggle?.setAttribute('aria-expanded', String(open));
  if (toggle) toggle.title = open ? '折叠小柔 AI 助手' : '展开小柔 AI 助手（Alt+R）';
  _notifyNativeViewportBounds();
  if (open) $('xiaorouChatInput')?.focus();
}

function _appendXiaorouMessage(role, text = '') {
  const messages = $('xiaorouChatMessages');
  messages?.querySelector('.cs-xiaorou-empty')?.remove();
  const row = document.createElement('div');
  row.className = `cs-xiaorou-message ${role}`;
  const bubble = document.createElement('div');
  bubble.className = 'cs-xiaorou-bubble';
  bubble.textContent = text;
  row.appendChild(bubble);
  messages?.appendChild(row);
  if (messages) messages.scrollTop = messages.scrollHeight;
  return bubble;
}

async function _sendXiaorouMessage() {
  const input = $('xiaorouChatInput');
  const send = $('xiaorouChatSend');
  const text = input?.value.trim();
  if (!text || !input || !send) return;
  input.value = '';
  input.disabled = true;
  send.disabled = true;
  _appendXiaorouMessage('user', text);
  const answer = _appendXiaorouMessage('ai', '…');
  try {
    let content = '';
    let streamError = false;
    answer.textContent = '';
    await window.AI00Business.stream('agent.interaction.chat.change.apply', {
      version: 3,
      payload: { operation: 'chat_stream', body: { message: text, context: { text: '当前模块：数模仿真' } } },
    }, {
      onToken(token) {
        content += token;
        answer.textContent = content;
        const messages = $('xiaorouChatMessages');
        if (messages) messages.scrollTop = messages.scrollHeight;
      },
      onError(message) {
        streamError = true;
        answer.textContent = `错误：${message}`;
      },
    });
    if (!content && !streamError) answer.textContent = '（无回复）';
  } catch (error) {
    answer.textContent = `请求失败：${error.message}`;
  } finally {
    input.disabled = false;
    send.disabled = false;
    input.focus();
  }
}

function _nativeViewportBounds() {
  const slot = $('nativeViewportSlot');
  if (!slot || slot.classList.contains('hidden')) return null;
  const rect = slot.getBoundingClientRect();
  let x = rect.left;
  let y = rect.top;
  try {
    let currentWindow = window;
    while (currentWindow.frameElement) {
      const frameRect = currentWindow.frameElement.getBoundingClientRect();
      x += frameRect.left;
      y += frameRect.top;
      currentWindow = currentWindow.parent;
    }
  } catch (_) {
    // Cross-origin ancestors cannot expose their frame bounds. The direct page
    // coordinates are still valid for the native host that owns this frame.
  }
  return {
    x: Math.round(x), y: Math.round(y),
    width: Math.max(0, Math.round(rect.width)), height: Math.max(0, Math.round(rect.height)),
  };
}

function _notifyNativeViewportBounds() {
  _renderVmPlaceholder();
  const bounds = _nativeViewportBounds();
  const nativeView = _eAPI()?.visMockupNativeView || _eAPI()?.visMockupView;
  const visible = _workspacePageVisible && !_nativeViewportOccluded && !window._liveDocumentContextUnavailable && Boolean(bounds?.width && bounds?.height);
  nativeView?.setVisible?.(visible);
  // Stage layout before readiness; an unbound view remains hidden, but Main
  // needs its dimensions to perform the first exact native attachment.
  if (bounds?.width && bounds?.height) nativeView?.updateBounds?.(bounds);
  if (!visible) return;
  window.dispatchEvent(new CustomEvent('ai00:native-viewport-bounds', { detail: bounds }));
}

async function _hasNativeViewportDocumentBinding() {
  const workspace = window._simulationEnvironmentWorkspace?.store?.state?.workspace;
  if (!workspace?.workspace_gid) {
    _setVmStatus('unavailable', '请先选择仿真环境');
    return false;
  }
  try {
    const binding = await _invokeCapability('simulation.environment.live_document.binding.get', {
      workspace_gid: workspace.workspace_gid,
    });
    const bound = binding?.document_session
      && String(binding.workspace_gid) === String(workspace.workspace_gid)
      && !['unbound', 'unavailable'].includes(binding.state);
    if (bound) return binding;
  } catch (error) {
    const code = error?.message || '';
    if (!['not_found', 'binding_not_found', 'document_binding_unavailable'].includes(code)) {
      _setVmStatus('error', `文档绑定读取失败：${code || 'unknown_error'}`);
      return false;
    }
  }
  _setVmStatus('unavailable', '当前仿真环境未绑定 VisMockup 文档');
  return false;
}

function _syncNativeViewportOcclusion() {
  const occluded = Boolean(window.AI00Dialogs?.isAnyOpen?.() || document.querySelector(
    '.cs-modal-overlay:not(.hidden), .cs-meta-overlay, dialog.ai00-dialog[open]',
  ));
  if (occluded === _nativeViewportOccluded) return;
  _nativeViewportOccluded = occluded;
  _notifyNativeViewportBounds();
}

let _nativeAttachFlight = null;
function _attachNativeViewport(probe = {}) {
  const workspaceGid = window._simulationEnvironmentWorkspace?.store?.state?.workspace?.workspace_gid;
  const manual = probe.managedDocumentKey || (probe.currentDocumentPreview === true ? 'current-preview' : probe.forDocumentSelection === true);
  const openedDocumentSession = probe.openedDocumentSession || null;
  if (_nativeAttachFlight) {
    if (_nativeAttachFlight.workspaceGid === workspaceGid && _nativeAttachFlight.manual === manual
        && _nativeAttachFlight.openedDocumentSession === openedDocumentSession)
      return _nativeAttachFlight.promise;
    // Different intents must not detach a window while an earlier attach is in flight.
    return _nativeAttachFlight.promise.catch(() => {}).then(() => {
      if (workspaceGid !== window._simulationEnvironmentWorkspace?.store?.state?.workspace?.workspace_gid) return;
      return _attachNativeViewport(probe);
    });
  }
  const flight = {workspaceGid, manual, openedDocumentSession};
  flight.promise = _performNativeViewportAttach(probe).finally(() => {
    if (_nativeAttachFlight === flight) _nativeAttachFlight = null;
  });
  _nativeAttachFlight = flight;
  return flight.promise;
}

async function _performNativeViewportAttach(probe = {}) {
  const visMockupNativeView = _eAPI()?.visMockupNativeView;
  const bounds = _nativeViewportBounds();
  if (!visMockupNativeView?.attach || !bounds?.width || !bounds?.height) return;
  const workspaceGid = window._simulationEnvironmentWorkspace?.store?.state?.workspace?.workspace_gid;
  const current = () => workspaceGid === window._simulationEnvironmentWorkspace?.store?.state?.workspace?.workspace_gid;
  if(probe.managedDocumentKey){
    const status=await visMockupNativeView.restoreDocument({key:probe.managedDocumentKey,bounds});
    if(!current())return;
    _applyNativeViewStatus(status);_syncNativeViewportOcclusion();_notifyNativeViewportBounds();return status;
  }
  const manualSelection = probe.forDocumentSelection === true || probe.currentDocumentPreview === true;
  const openedDocumentSession = probe.openedDocumentSession || null;
  const binding = manualSelection || openedDocumentSession ? null : await _hasNativeViewportDocumentBinding();
  if ((!manualSelection && !openedDocumentSession && !binding) || !current()) return;
  // The readiness response has no PID. Resolve the same document runtime used
  // by model synchronization before selecting a native window.
  let targetPid;
  if(probe.currentDocumentPreview===true){
    // Showing the already-open native window does not require a Connector
    // binding. Model controls still establish their exact session separately.
    const snapshot=await visMockupNativeView.manageDocuments();
    if(!current())return;
    if(snapshot.documents?.filter(item=>item.current).length!==1)throw Error('current_document_ambiguous');
    targetPid=0;
  }else{
    try {
      const identity = await _requestVisMockupCommand('simulation.vismockup.document.identity.read.request', {}, { confirmation: false });
      const step = identity?.steps?.length === 1 ? identity.steps[0] : null;
      if (step?.status !== 'succeeded' || !Number.isInteger(step.result?.process_id) || step.result.process_id <= 0)
        throw new Error('document_identity_unavailable');
      if (!current()) return;
      if (openedDocumentSession && step.result.document_session !== openedDocumentSession)
        throw new Error('opened_document_identity_changed');
      if (!manualSelection && !openedDocumentSession && step.result.document_session !== binding.document_session)
        throw new Error('document_environment_binding_mismatch');
      targetPid = step.result.process_id;
    } catch (error) {
      if (!current()) return;
      _applyNativeViewStatus({ state: 'error', error: error?.message || 'document_identity_unavailable' });
      return { state: 'error', error: error?.message || 'document_identity_unavailable' };
    }
  }
  const existing = await visMockupNativeView.status?.();
  if (!current()) return;
  if (existing?.state === 'attached' && existing.pid === targetPid) {
    _applyNativeViewStatus(existing);
    _syncNativeViewportOcclusion();
    _notifyNativeViewportBounds();
    return existing;
  }
  for (let attempt = 0; attempt < 20; attempt++) {
    if (!current()) return;
    let status;
    try {
      status = await visMockupNativeView.attach({ pid: targetPid, bounds });
    } catch (error) {
      status = { state: 'error', error: error?.message || 'native_view_attach_failed' };
    }
    if (status?.error === 'vismockup_3d_view_unavailable' && attempt < 19 && (_vmConnected || openedDocumentSession)) {
      _setVmStatus('connecting', '等待 VisMockup 三维视图…');
      await new Promise(resolve => setTimeout(resolve, 500));
      if (!_vmConnected && !openedDocumentSession) return;
      continue;
    }
    if (!current()) return;
    _applyNativeViewStatus(status);
    _syncNativeViewportOcclusion();
    _notifyNativeViewportBounds();
    return status;
  }
}

function _applyNativeViewStatus(status = {}) {
  if (status.documentName) _setVmDocumentLabel({ document_name: status.documentName });
  if (status.state === 'attached') {
    _setVmDocumentReady(true);
    _setVmStatus('connected', '已内嵌');
  } else if (status.state === 'documentChanged') {
    _setVmDocumentReady(true);
    // Native refresh already restored the old renderer and attached the new one.
    _setVmStatus('connected', '已内嵌');
    window.dispatchEvent(new CustomEvent('ai00:live-document-changed'));
    _notifyNativeViewportBounds();
  } else if (status.state === 'error' && status.error) {
    _setVmStatus('error', `VisMockup 内嵌失败：${status.error}`);
  } else if (status.state === 'detached') {
    _setVmDocumentReady(false);
  }
}

function _setVmDocumentLabel(probe = {}) {
  const path = probe.document_name || probe.documentName || probe.document_path || probe.path || '';
  const raw = String(path).trim();
  const isLocalPath = /^(?:[a-z]:[\\/]|\\\\|\/)/i.test(raw);
  const name = isLocalPath ? raw.split(/[\\/]/).filter(Boolean).pop() : raw;
  const label = $('vmDocumentLabel');
  if (!label) return;
  label.textContent = name || (probe.document_ready === false ? '未打开模型' : '当前模型');
  label.title = path || label.textContent;
  label.setAttribute('aria-label', `切换 VisMockup 文档：${label.textContent}`);
}

function _setViewerEnvironmentLabel(state = window._simulationEnvironmentWorkspace?.store?.state) {
  const label = $('viewerEnvironmentLabel');
  if (!label) return;
  const workspace = state?.workspace;
  const name = workspace?.display_label || workspace?.name || workspace?.project_name || '';
  label.textContent = `仿真环境：${name || '未选择'}`;
  label.title = workspace
    ? window.AI00SimulationEnvironmentTree?.environmentLabel?.(workspace, state.currentKind) || label.textContent
    : label.textContent;
}

/** 工具栏手动连接、启动或重新连接按钮 */
async function _launchAndConnect() {
  const attachOnly = _vmConnected || _vmAction === 'connect';
  _setVmStatus('connecting', attachOnly ? '正在连接…' : '正在启动…');
  try {
    await _requireConnectorRuntime();
    const outcome = await _requestVisMockupCommand(
      attachOnly
        ? 'simulation.vismockup.application.attach.request'
        : 'simulation.vismockup.application.launch.request',
      {}, { confirmation: !attachOnly },
    );
    const probe = _visMockupProbeResult(outcome);
    if (!probe.ready) throw new Error(probe.process_ready ? 'VisMockup 已打开，但当前实例无法接入自动化' : 'VisMockup 未运行');
    _onConnected(probe);
  } catch (error) {
    _vmConnected = false;
    _setVmDocumentReady(false);
    _setLaunchButton('launch');
    _setVmStatus('error', error.message || (attachOnly ? '连接失败' : '启动失败'));
  }
}

function _setLaunchButton(action) {
  _vmAction = action;
  const button = $('btnLaunchVm');
  const label = $('btnLaunchVmLabel');
  const text = action === 'launch' ? '启动 VisMockup'
    : action === 'reconnect' ? '重新连接' : '连接 VisMockup';
  if (button) button.title = text;
  if (label) label.textContent = text;
}

function _onConnected(probe = {}) {
  _vmConnected = true;
  _setVmDocumentReady(probe.document_ready !== false);
  _setLaunchButton('reconnect');
  _setVmStatus('connected', probe.document_ready === false ? 'VisMockup 已连接，暂无活动文档' : 'VisMockup 已连接');
  _setVmDocumentLabel(probe);
  if (probe.document_ready !== false) void _attachNativeViewport(probe);
  $('visTreeEmpty').textContent = '点击“从 VisMockup 重新加载结构树”读取当前模型';
  $('visTreeEmpty').classList.remove('hidden');
}

// ── VisMockup 状态 UI ─────────────────────────────────────────────────────────

const _VM_STATUS = {
  connected:   { color: 'var(--green)',    title: 'VisMockup 已连接' },
  connecting:  { color: 'var(--yellow)',   title: '正在连接…' },
  error:       { color: 'var(--red)',      title: '连接错误' },
  disconnected:{ color: 'var(--text-dim)', title: '未连接' },
  unavailable: { color: 'var(--text-dim)', title: '不可用' },
};

let _vmPresentation = {state:'disconnected', message:'尚未连接 VisMockup'};
function _renderVmPlaceholder() {
  const ph = $('vmPlaceholder');
  if (!ph) return;
  const {state,message} = _vmPresentation;
  const selected = !!window._simulationEnvironmentWorkspace?.store?.state?.workspace?.workspace_gid;
  const ready = selected && state === 'connected' && ['已内嵌','当前文档已显示'].includes(message) && !window._liveDocumentContextUnavailable;
  const renderKey = JSON.stringify([state,message,selected,ready]);
  if (ph.dataset.presentation === renderKey) return;
  ph.dataset.presentation = renderKey;
  ph.querySelector('[data-recover-online-document]')?.remove();
  ph.classList.toggle('hidden', ready);
  if (ready) return;
  let title = message, hint = '';
  if (!selected && ['connected','unavailable'].includes(state)) {
    title = '请选择仿真环境';
    hint = '从左侧选择环境，再连接其绑定的 VisMockup 文档。';
    if (message.includes('暂无活动文档')) hint += '打开模型后将在此显示三维视图。';
  } else if (/未绑定/.test(message)) {
    hint = '点击上方文档名选择文档，或从当前 VisMockup 文档创建环境。';
  } else if (/缓存已保留|绑定待核对|document_environment_binding_mismatch|bound_document_window_unavailable/.test(message)) {
    title = '文档连接待恢复';
    hint = '点击上方文档名，选择“恢复到当前环境”；保留结构缓存，内容尚未核对。';
  } else if (state === 'error') {
    hint = '请核对文档和连接状态后重试；已有结构缓存不会因连接失败被清除。';
  } else if (state === 'connecting') {
    hint = '连接就绪后显示三维视图；此状态不代表结构已核对。';
  } else if (/暂无活动文档|模型已关闭/.test(message)) {
    hint = '打开模型后将在此显示三维视图，请再核对环境与文档绑定。';
  } else if (state === 'connected') {
    title = '文档绑定待核对';
    hint = '连接服务已就绪；核对当前环境的文档后才能显示三维视图。';
  } else if (/打开模型时启动专用 VisMockup/.test(message)) {
    title = '等待打开模型';
    hint = '先在模型文件中展开到目标路径，再点击“打开”；AI00 将创建并控制专用 VisMockup 窗口。';
  } else {
    hint = '从模型文件打开文档后，AI00 将连接其专用 VisMockup 会话。';
  }
  ph.querySelectorAll('p').forEach(node => node.remove());
  const heading = document.createElement('p'), detail = document.createElement('p');
  heading.textContent = title;
  heading.style.color = state === 'error' ? 'var(--red)' : 'var(--text-dim)';
  detail.textContent = hint; detail.style.cssText = 'font-size:11px;opacity:.75;margin-top:4px;max-width:420px';
  ph.append(heading,detail);
  const onlineDocument = selected && _modelDocumentCollection?.state?.documents?.find(item =>
    item?.source_kind === 'teamcenter_online' && item?.role === 'primary');
  if (onlineDocument && window._liveDocumentContextUnavailable) {
    const retrying = String(_pendingTeamcenterOnlineBinding?.documentGid) === String(onlineDocument.document_gid);
    const recover = document.createElement('button');
    recover.type = 'button'; recover.className = 'cs-btn cs-vm-recovery';
    recover.dataset.recoverOnlineDocument = String(onlineDocument.document_gid);
    recover.textContent = retrying ? '继续完成内嵌' : '打开当前模型';
    recover.title = retrying ? '继续核对已经打开的文档，不会再次打开或重读结构树'
      : '使用当前模型文件保存的 Teamcenter 在线来源启动专用后台会话；缓存结构不变';
    recover.onclick = async () => {
      if (recover.disabled) return;
      recover.disabled = true;
      try {
        if(await window._localViewerInteractionEnabled?.()===true)await window._ensureLocalViewerReady(onlineDocument);
        else await _openTeamcenterOnlineDocument(onlineDocument,'new');
        _cmdShow('模型已在专用后台会话中打开并内嵌');
      } catch (error) {
        _cmdShow(error?.message || '文档绑定未完成','err');
      } finally { recover.disabled = false; }
    };
    ph.append(recover);
  }
  ph.setAttribute('role','status'); ph.setAttribute('aria-live','polite');
  const icon = ph.querySelector('svg'); if (icon) icon.setAttribute('stroke','currentColor');
}

function _setVmStatus(state, msg) {
  const info = _VM_STATUS[state] || _VM_STATUS.error;
  const dot  = $('vmStatusDot');
  const lbl  = $('vmStatusLabel');
  if (dot) { dot.style.background = info.color; dot.title = info.title; }
  if (lbl) lbl.textContent = msg || info.title;
  _vmPresentation = {state, message:msg || info.title};
  _renderVmPlaceholder();
}

function _showBanner(msg, type = 'info') {
  const banner = $('vmBanner'), text = $('vmBannerText');
  if (!banner || !text) return;
  text.textContent = msg;
  banner.classList.remove('hidden');
  banner.classList.toggle('cs-vm-banner-error', type === 'error');
  clearTimeout(banner._hideTimer);
  banner._hideTimer = setTimeout(() => banner.classList.add('hidden'), 6000);
}

// ── 工具栏绑定 ────────────────────────────────────────────────────────────────

function _bindToolbar() {
  $('btnLaunchVm')?.addEventListener('click', _launchAndConnect);
  $('btnOpenFile')?.addEventListener('click', _openFileInViewer);
  $('btnCloseFile')?.addEventListener('click', _closeFileInViewer);
  $('btnResetCamera')?.addEventListener('click', _resetCamera);
  $('btnNewTask')?.addEventListener('click', () => _openTaskModal());
}

// ── 测试命令条 ────────────────────────────────────────────────────────────────

function _cmdShow(msg, type = 'ok') {
  if(msg)_simulationDebug('ui_notice',{message:String(msg),level:type==='err'?'error':'info'});
  const el = $('cmdResult');
  if (!el) return;
  el.textContent = msg;
  el.className = `cs-cmd-result ${type}`;
}

function _bindCmdBar() {
  const cmds = [
    ['cmdAllOn',     async () => { await _requestVisMockupCommand('simulation.vismockup.visibility.change.request', { action: 'all_on' }, { confirmation: false }); return { success: true }; }, r => { _syncAllVisibility(true);  return `全显 ✓`; }],
    ['cmdAllOff',    async () => { await _requestVisMockupCommand('simulation.vismockup.visibility.change.request', { action: 'all_off' }, { confirmation: false }); return { success: true }; }, r => { _syncAllVisibility(false); return `全隐 ✓`; }],
    ['cmdSelVisible',() => _bridge('vis_mockup', 'select_visible_nodes'),   r => `选可见 ✓`],
    ['cmdDesel',     () => _bridge('vis_mockup', 'deselect_all_nodes'),     r => `取消选 ✓`],
    ['cmdDynHlOn',   () => _bridge('vis_mockup', 'set_dynamic_highlight', { on: true }),  r => `动态高亮 ON ✓`],
    ['cmdDynHlOff',  () => _bridge('vis_mockup', 'set_dynamic_highlight', { on: false }), r => `动态高亮 OFF ✓`],
    ['cmdDocInfo',   () => _bridge('vis_mockup', 'get_doc_info'),
      r => {
        const d = r.data;
        _setVmDocumentLabel(d);
        const name = (d.path || '').split(/[\\/]/).pop() || d.path;
        return `${name} | 可见:${d.num_visible} 加载:${d.num_loaded} 选中:${d.num_selected}`;
      }
    ],
    ['cmdCapture',   () => _bridge('vis_mockup', 'capture_image'),
      r => r.data.exists ? `截图 ✓ ${r.data.path.split(/[\\/]/).pop()}` : `截图写入失败`
    ],
    ['cmdLoadAllGeo', () => _bridge('vis_mockup', 'load_all_geometry'),
      r => `全量几何已加载：${r.data.loaded} 个节点`
    ],
  ];

  for (const [id, fn, fmt] of cmds) {
    $(id)?.addEventListener('click', async () => {
      if (!_vmConnected) { _cmdShow('未连接 VisMockup', 'err'); return; }
      _cmdShow('…');
      try {
        const r = await fn();
        if (r?.success) _cmdShow(fmt(r), 'ok');
        else            _cmdShow(r?.error || '失败', 'err');
      } catch(e) {
        _cmdShow(String(e), 'err');
      }
    });
  }

  $('cmdDebugTree')?.addEventListener('click', async () => {
    console.log('[AI00] Debug树 clicked, _vmConnected=', _vmConnected);
    if (!_vmConnected) { _cmdShow('未连接 VisMockup', 'err'); return; }
    _cmdShow('读取原始树结构…');
    try {
      const r = await _bridge('vis_mockup', 'debug_vis_tree');
      console.log('[AI00] debug_vis_tree response:', r);
      if (r?.success) {
        console.group('[AI00] debug_vis_tree');
        console.log('doc_count:', r.data.doc_count);
        console.log('root_key:', r.data.root_key);
        // 汇总打印 small_key_nodes（太多就只打前20和后20）
        const skn = r.data.small_key_nodes || {};
        const sknKeys = Object.keys(skn).map(Number).sort((a,b)=>a-b);
        console.log(`small_key_nodes 共找到 ${sknKeys.length} 个节点，key 范围: ${sknKeys[0]} ~ ${sknKeys[sknKeys.length-1]}`);
        // 只打印 key 最小的20个和最大的20个，帮助定位 AH 节点位置
        const showKeys = sknKeys.length <= 40 ? sknKeys :
          [...sknKeys.slice(0, 20), '...', ...sknKeys.slice(-20)];
        showKeys.forEach(k => {
          if (k === '...') { console.log('  ...'); return; }
          console.log(`  key=${k}  name="${skn[k].name}"  nc=${skn[k].nc}`);
        });
        if (r.data.parent_tree) {
          console.log('parent_tree (key=RootNode-2):\n' + JSON.stringify(r.data.parent_tree, null, 2));
        }
        if (r.data.viewlist_debug) {
          const vd = r.data.viewlist_debug;
          console.log('viewlist_debug:', JSON.stringify({
            num_views: vd.num_views, av_handle_raw: vd.av_handle_raw,
            doc_handle: vd.doc_handle, av_handle_err: vd.av_handle_err,
          }));
          if (vd.handle_probe) {
            console.log('handle_probe (found views):');
            Object.entries(vd.handle_probe).forEach(([h,v]) =>
              console.log(`  h=${h}: root="${v.root}" nc=${v.nc}`));
          }
          if (vd.export_results) {
            console.log('ExportEx results:');
            Object.entries(vd.export_results).forEach(([k,v]) => {
              if (v.err) console.log(`  ${k}: ERR ${v.err}`);
              else console.log(`  ${k}: exists=${v.exists} size=${v.size}`);
            });
          }
        }
        if (r.data.all_views_info?.length) {
          console.log('all_views_info:');
          r.data.all_views_info.forEach(v => console.log(' ', JSON.stringify(v)));
        } else {
          console.log('all_views_info: []');
        }
        if (r.data.all_nodes_debug) {
          const and = r.data.all_nodes_debug;
          console.log(`all_nodes total=${and.total}`, and.error || '');
          if (and.sample) {
            const si = Object.keys(and.sample).map(Number).sort((a,b)=>a-b);
            si.forEach(i => {
              const s = and.sample[String(i)];
              if (s.err) console.log(`  [${i}] ERR: ${s.err}`);
              else console.log(`  [${i}] key=${s.key} nc=${s.nc} "${s.name}"`);
            });
          }
        }
        if (r.data.hier_debug) {
          console.log('hier_debug:', JSON.stringify(r.data.hier_debug, null, 2));
        }
        console.groupEnd();
        _cmdShow(`Debug完成，共 ${sknKeys.length} 个节点，key 范围 ${sknKeys[0]}~${sknKeys[sknKeys.length-1]}，详见 D:\\Temp\\debug_vis_auto.json`, 'ok');
      } else {
        console.error('[AI00] debug_vis_tree failed:', r);
        _cmdShow(r?.error || 'debug失败', 'err');
      }
    } catch(e) {
      console.error('[AI00] debug_vis_tree exception:', e);
      _cmdShow(String(e), 'err');
    }
  });

  // 诊断 catia 匹配
  $('cmdDebugCatiaMatch')?.addEventListener('click', _debugCatiaMatch);
}

async function _debugCatiaMatch() {
  // 0a. 用已有的 _visNodeMap 检查 VM 节点 name 字段格式
  const vmNodeNames = Object.values(_visNodeMap).map(v => v.node?.name).filter(Boolean);
  if (vmNodeNames.length) {
    console.group('[AI00] VM 节点 name 样本（来自已加载结构树）');
    vmNodeNames.slice(0, 15).forEach((n, i) => console.log(`  VM name[${i}] len=${n.length} | "${n}"`));
    console.groupEnd();
  } else {
    console.log('[AI00] _visNodeMap 为空，请先刷新 VM 结构树');
  }

  // 0b. 打出 DISPID 6/7/8/19 及 MetaDataProperties
  if (_vmConnected) {
    const pr = await _bridge('vis_mockup', 'debug_catia_props');
    if (pr?.success) {
      console.group('[AI00] VM 节点 DISPID 诊断（找哪个字段存了 catiaOccurrenceName）');
      (pr.data.samples || []).forEach((s, i) => {
        const d = s.dispids || {};
        console.log(`节点[${i}] key=${s.key} depth=${s.depth} nc=${s.nc}`);
        console.log(`  Name(7)         = "${d.Name}"`);
        console.log(`  Fullname(8)     = "${d.Fullname}"`);
        console.log(`  DataStoreName(6)= "${d.DataStoreName}"`);
        console.log(`  CADID(19)       = "${d.CADID}"`);
        const pkeys = Object.keys(s.props || {});
        if (pkeys.length) pkeys.forEach(k => console.log(`  MetaData.${k} = "${s.props[k]}"`));
        else console.log('  MetaData: (空)');
      });
      console.groupEnd();
    }
  }
  // 收集 BOP 侧所有非空 catia_occ（去重）
  const bopAllSet = new Set(
    _bopEntries.flatMap(e => (e.parts || []).map(p => p.catia_occ).filter(Boolean))
  );
  const bopSample = [...bopAllSet].slice(0, 10);

  // ── 用 VM 树 node.name 做交叉比对（不依赖扫描）──────────────────
  if (vmNodeNames.length && bopSample.length) {
    const vmNameSet   = new Set(vmNodeNames);
    const vmNameLower = new Set(vmNodeNames.map(n => n.toLowerCase()));
    console.group('[AI00] BOP catia_occ vs VM node.name 交叉比对');
    let exactHit = 0, caseHit = 0;
    bopSample.forEach((v, i) => {
      const exact = vmNameSet.has(v);
      const ci    = !exact && vmNameLower.has(v.toLowerCase());
      if (exact) exactHit++;
      if (ci)    caseHit++;
      console.log(`  BOP[${i}] ${exact ? '✅exact' : ci ? '⚠️case' : '❌'} | "${v}"`);
    });
    // 也打几个 VM name 样本做肉眼对比
    console.log(`VM node.name 样本（共 ${vmNodeNames.length} 个）：`);
    vmNodeNames.slice(0, 8).forEach((n, i) => console.log(`  VM[${i}] "${n}"`));
    console.log(`结论：${exactHit} 精确命中，${caseHit} 大小写差异命中`);
    console.groupEnd();
  }
  // ────────────────────────────────────────────────────────────────

  // 如果还没扫描，先扫描
  if (!_vmCatiaSet.size) {
    if (!_vmConnected) { _cmdShow('未连接 VM，无法诊断', 'err'); return; }
    _cmdShow('正在扫描 VM 节点…');
    const sr = await _bridge('vis_mockup', 'scan_vis_catia_map');
    if (sr?.success) { _catiaScanDone = true; await _refreshVmMatchCounts(); }
    else { _cmdShow(sr?.error || '扫描失败', 'err'); return; }
  }
  const vmSample = [..._vmCatiaSet].slice(0, 10);

  console.group('[AI00] Catia 匹配诊断');
  console.log(`BOP catia_occ 唯一值共 ${bopAllSet.size} 个，取前${bopSample.length}个样本：`);
  bopSample.forEach((v, i) => {
    const hit = _vmCatiaSet.has(v);
    console.log(`  BOP[${i}] ${hit ? '✅' : '❌'} len=${v.length} | "${v}"`);
  });
  console.log(`VM catiaOccurrenceName 唯一值共 ${_vmCatiaSet.size} 个，取前${vmSample.length}个样本：`);
  vmSample.forEach((v, i) => console.log(`  VM[${i}]  len=${v.length} | "${v}"`));

  // 大小写不敏感匹配
  const vmLower = new Map([..._vmCatiaSet].map(v => [v.toLowerCase(), v]));
  const caseHits = bopSample.filter(v => !_vmCatiaSet.has(v) && vmLower.has(v.toLowerCase()));
  if (caseHits.length) {
    console.warn('大小写不匹配的值（BOP → VM实际值）：');
    caseHits.forEach(v => console.warn(`  "${v}" → "${vmLower.get(v.toLowerCase())}"`));
  }
  // 去空格匹配
  const vmTrim = new Map([..._vmCatiaSet].map(v => [v.trim(), v]));
  const trimHits = bopSample.filter(v => !_vmCatiaSet.has(v) && vmTrim.has(v.trim()));
  if (trimHits.length) console.warn('首尾空格导致不匹配：', trimHits);

  console.groupEnd();
  _cmdShow(
    `BOP ${bopAllSet.size} 值 / VM ${_vmCatiaSet.size} 值` +
    (caseHits.length ? ` ⚠️ 大小写不匹配${caseHits.length}个` : '') +
    (trimHits.length ? ` ⚠️ 空格问题${trimHits.length}个` : '') +
    ' — 详见F12控制台',
    caseHits.length || trimHits.length ? 'warn' : 'ok'
  );
}

async function _openFileInViewer() {
try{_setVmStatus('connecting','打开文件中…');const artifactRef=await _artifactFromFile();await _requestVisMockupCommand('simulation.vismockup.model.open.request',{artifact_ref:artifactRef});_onConnected();}catch(error){if(error.code!=='native_selection_cancelled')_setVmStatus('error',error.message||'打开文件失败');}
}

async function _closeFileInViewer() {
  try {
    _setVmStatus('connecting', '关闭 AI00 模型中…');
    await _requestVisMockupCommand('simulation.vismockup.model.close.request');
    _setVmStatus('connected', '模型已关闭，Connector 在线');
  } catch (error) { _setVmStatus('error', error.message || '关闭模型失败'); }
}

async function _resetCamera() {
  if (!_vmConnected) return;
  await _bridge('vis_mockup', 'reset_view', {});
}

// ── BOP 版本面板 ──────────────────────────────────────────────────────────────

function _bindBopPanel() {
  $('btnRefreshVers')?.addEventListener('click', _loadBopVersions);
  $('btnLoadBopVer')?.addEventListener('click', () => {
    const sel = $('bopVersionSel');
    if (sel?.value) _loadBopTree(sel.value);
  });
  $('bopVersionSel')?.addEventListener('change', () => {
    const gid = $('bopVersionSel')?.value;
    if (gid) _loadBopTree(gid);
  });
  $('btnToggleManual')?.addEventListener('click', () => {
    const row = $('bopManualRow');
    if (row) {
      const hidden = row.classList.toggle('hidden');
      $('btnToggleManual').textContent = hidden ? '手动输入 GID' : '收起';
    }
  });
  $('btnLoadBopGid')?.addEventListener('click', () => {
    const gid = $('bopGidInput')?.value?.trim();
    if (gid) _loadBopTree(gid);
  });
  $('bopGidInput')?.addEventListener('keydown', e => {
    if (e.key === 'Enter') { const gid = e.target.value.trim(); if (gid) _loadBopTree(gid); }
  });
}

async function _loadBopVersions() {
  const cf = window.AI00Business?.available() || window.AI00Business?.available();
  if (!cf) return;
  try {
    const data = await _invokeCapability('craft.bop.version.list', {
      include_archived: false,
      page_size: 100,
    });
    const raw = Array.isArray(data)
      ? data
      : (data?.items || data?.versions || data?.data?.items || data?.data?.versions || data?.data || []);
    _bopVersions = (Array.isArray(raw) ? raw : [])
      .map(item => {
        const gid = String(item?.version_gid || item?.gid || '').trim();
        return gid ? { ...item, gid, version_gid: String(item?.version_gid || gid) } : null;
      })
      .filter(Boolean);
    _bopVersionLoadError = null;
    _renderVersionSelector();
  } catch(e) {
    _bopVersionLoadError = e;
    console.warn('[cad_sim] loadBopVersions:', e);
  }
}

function _renderVersionSelector() {
  const sel = $('bopVersionSel');
  if (!sel) return;
  const prev = sel.value;
  sel.innerHTML = '<option value="">-- 选择 BOP 版本 --</option>' +
    _bopVersions.map(v => {
      const label = v.bop_name || v.name || v.gid;
      const status = v.status ? ` [${v.status}]` : '';
      return `<option value="${v.gid}">${_esc(label + status)}</option>`;
    }).join('');
  if (prev && _bopVersions.some(v => v.gid === prev)) sel.value = prev;
}

async function _loadBopTree(versionGid) {
  if (!versionGid) return;
  _selectedBopGid = versionGid;
  $('bopTreeLoading').classList.remove('hidden');
  $('bopTreeEmpty').classList.add('hidden');
  $('bopTreeBody').innerHTML = '';
  $('bopVerStatus').classList.add('hidden');

  const cf = window.AI00Business?.available() || window.AI00Business?.available();
  if (!cf) {
    $('bopTreeLoading').classList.add('hidden');
    $('bopTreeEmpty').textContent = '需要飞书登录才能加载 BOP 数据';
    $('bopTreeEmpty').classList.remove('hidden');
    return;
  }
  try {
    // 用 alt-hier 端点：返回带 parts（catia_occ）的完整条目列表
    const data = await _invokeCapability('craft.bop.alt_hierarchy.read', {
      version_gid: versionGid,
    });
    _bopEntries = data?.entries || [];
    _bopEntryIndex = Object.fromEntries(_bopEntries.map(e => [e.gid, e]));
    // 构建父子映射（parent_gid → children[]，按 sort_order 排序）
    _bopChildMap = {};
    for (const e of _bopEntries) {
      const key = e.parent_gid || '__root__';
      (_bopChildMap[key] = _bopChildMap[key] || []).push(e);
    }
    for (const arr of Object.values(_bopChildMap)) {
      arr.sort((a, b) => (a.sort_order ?? 999) - (b.sort_order ?? 999));
    }
    _computeSubtreeParts();

    const ver = _bopVersions.find(v => v.gid === versionGid);
    if (ver?.status) {
      const statusEl = $('bopVerStatus');
      statusEl.textContent = `状态: ${ver.status}`;
      statusEl.className = `cs-bop-ver-status cs-bop-ver-${ver.status}`;
      statusEl.classList.remove('hidden');
    }

    const roots = _buildTree(_bopEntries);
    $('bopTreeBody').innerHTML = _renderBopNodes(roots, 0);
    _bindBopTreeEvents();
    _refreshBopVmBindingDraft();
  } catch(e) {
    $('bopTreeEmpty').textContent = `加载失败: ${e.message}`;
    $('bopTreeEmpty').classList.remove('hidden');
  } finally {
    $('bopTreeLoading').classList.add('hidden');
  }
}

/** 计算每个 BOP 节点子树内唯一 catia_occ 数量，存入 _bopSubtreeParts。 */
function _computeSubtreeParts() {
  _bopSubtreeParts = {};
  const cache = {};  // gid → Set<catia_occ>
  function _collect(gid) {
    if (cache[gid]) return cache[gid];
    const entry = _bopEntryIndex[gid];
    if (!entry) return (cache[gid] = new Set());
    const set = new Set();
    for (const p of (entry.parts || [])) {
      if (p.catia_occ) set.add(p.catia_occ);
    }
    for (const child of (_bopChildMap[gid] || [])) {
      for (const occ of _collect(child.gid)) set.add(occ);
    }
    cache[gid] = set;
    return set;
  }
  for (const e of _bopEntries) {
    _bopSubtreeParts[e.gid] = _collect(e.gid).size;
  }
}

/** 计算每个节点子树内与 VM _vmCatiaSet 匹配的唯一 catia_occ 数，存入 _bopSubtreeMatched。 */
function _computeSubtreeMatched() {
  _bopSubtreeMatched = {};
  if (!_vmCatiaSet.size) return;
  const cache = {};
  function _collect(gid) {
    if (cache[gid]) return cache[gid];
    const entry = _bopEntryIndex[gid];
    if (!entry) return (cache[gid] = new Set());
    const set = new Set();
    for (const p of (entry.parts || [])) {
      if (p.catia_occ && _vmCatiaSet.has(p.catia_occ)) set.add(p.catia_occ);
    }
    for (const child of (_bopChildMap[gid] || [])) {
      for (const occ of _collect(child.gid)) set.add(occ);
    }
    cache[gid] = set;
    return set;
  }
  for (const e of _bopEntries) {
    _bopSubtreeMatched[e.gid] = _collect(e.gid).size;
  }
}

/** 扫描完成后从 Python 拉取 catia 键集合，重算匹配数，更新 BOP 树徽标（不重建 DOM）。 */
async function _refreshVmMatchCounts() {
  const r = await _bridge('vis_mockup', 'get_catia_map_keys');
  if (!r?.success) return;
  _vmCatiaSet = new Set(r.data.keys || []);
  _computeSubtreeMatched();
  _updateBopBadges();
}

/** 就地更新 BOP 树中所有 [data-badge-gid] 徽标，显示 matched/total 格式。 */
function _updateBopBadges() {
  const hasScan = _vmCatiaSet.size > 0;
  $('bopTreeBody')?.querySelectorAll('[data-badge-gid]').forEach(el => {
    const gid     = el.dataset.badgeGid;
    const total   = _bopSubtreeParts[gid]  || 0;
    const matched = _bopSubtreeMatched[gid] || 0;
    if (total === 0) { el.style.display = 'none'; return; }
    el.style.display = '';
    if (hasScan) {
      el.innerHTML = `<span style="color:${matched===total?'var(--green)':matched>0?'var(--yellow)':'var(--red)'}">${matched}</span><span style="opacity:.5">/${total}</span>`;
      el.title = `VM 已匹配 ${matched} / 子树共 ${total} 个零件`;
      el.className = 'cs-bop-part-badge' + (matched===total?' cs-bop-badge-full':matched>0?' cs-bop-badge-partial':' cs-bop-badge-none');
    } else {
      el.textContent = String(total);
      el.title = `子树共 ${total} 个零件（按 catiaOccurrenceName 统计）`;
      el.className = 'cs-bop-part-badge';
    }
  });
}

function _refreshBopVmBindingDraft() {
  const status = $('bindingDraftStatus');
  if (!window.AI00BopVmBindingDraft || !_visTreeSnapshot || !_bopEntries.length) {
    _bopVmBindingDraft = null;
    if (status) status.textContent = '';
    return;
  }
  _bopVmBindingDraft = window.AI00BopVmBindingDraft.build(_bopEntries, _visTreeSnapshot);
  const labels = { parts: '零件精确', vpps: 'VPPS 精确', structure_only: '仅结构' };
  if (status) {
    status.textContent = `页面候选：${labels[_bopVmBindingDraft.mode]} · 自动 ${_bopVmBindingDraft.auto_count} · 待复核 ${_bopVmBindingDraft.review_count}`;
    status.dataset.state = _bopVmBindingDraft.review_count ? 'review' : 'ready';
  }
  _vmCatiaSet = new Set(
    window.AI00BopVmBindingDraft.flatten(_visTreeSnapshot.children || [])
      .flatMap(node => [node.catia_name, node.name]).filter(Boolean),
  );
  _computeSubtreeMatched();
  _updateBopBadges();
}

function _buildTree(entries) {
  const map = {}, roots = [];
  entries.forEach(e => { map[e.gid] = { ...e, children: [] }; });
  entries.forEach(e => {
    if (e.parent_gid && map[e.parent_gid]) map[e.parent_gid].children.push(map[e.gid]);
    else roots.push(map[e.gid]);
  });
  const sort = arr => {
    arr.sort((a, b) => (a.seq_no ?? 999) - (b.seq_no ?? 999));
    arr.forEach(n => sort(n.children));
  };
  sort(roots);
  return roots;
}

function _renderBopNodes(nodes, depth) {
  return nodes.map(n => {
    const hasChildren = n.children?.length > 0;
    const indent = depth * 14 + 8;
    const typeClass = `cs-bop-type-${n.node_type || 'other'}`;
    const subtreeCount = _bopSubtreeParts[n.gid] || 0;
    const partBadge = `<span class="cs-bop-part-badge" data-badge-gid="${n.gid}"
        title="子树共 ${subtreeCount} 个零件（按 catiaOccurrenceName 统计）"
        style="${subtreeCount === 0 ? 'display:none' : ''}">${subtreeCount}</span>`;
    return `
      <div class="cs-bop-row" data-gid="${n.gid}" data-title="${_esc(n.title || '')}"
           data-parts="${_esc(JSON.stringify((n.parts||[]).map(p=>p.catia_occ).filter(Boolean)))}">
        <div class="cs-bop-node ${typeClass}" style="padding-left:${indent}px">
          <span class="cs-bop-toggle ${hasChildren ? '' : 'cs-bop-leaf'}" data-gid="${n.gid}">
            ${hasChildren ? '▶' : '·'}
          </span>
          <span class="cs-bop-label">${_esc(n.title || n.gid)}</span>
          ${partBadge}
        </div>
        ${hasChildren ? `<div class="cs-bop-children" data-parent="${n.gid}" style="display:none">
          ${_renderBopNodes(n.children, depth + 1)}
        </div>` : ''}
      </div>
    `;
  }).join('');
}

function _bindBopTreeEvents() {
  $('bopTreeBody').querySelectorAll('.cs-bop-node').forEach(el => {
    el.addEventListener('click', async e => {
      const row   = el.closest('.cs-bop-row');
      const gid   = row?.dataset?.gid;
      const title = row?.dataset?.title || '';
      if (!gid) return;

      $('bopTreeBody').querySelectorAll('.cs-bop-node').forEach(n => n.classList.remove('active'));
      el.classList.add('active');

      const children = el.parentElement.querySelector(`.cs-bop-children[data-parent="${gid}"]`);
      const toggle   = el.querySelector('.cs-bop-toggle');
      if (children) {
        const isOpen = children.style.display !== 'none';
        children.style.display = isOpen ? 'none' : '';
        if (toggle) toggle.textContent = isOpen ? '▶' : '▼';
      }

      $('nodePathLabel').textContent = title || gid;

      // 详情面板
      _showBopDetail(_bopEntryIndex[gid]);

      // 取该节点（及其所有子孙）的全部 catia_occ，批量高亮 VM 节点
      if (_vmConnected) {
        const allParts = _collectBopRowParts(row);
        if (allParts.length > 0) {
          if (!_catiaScanDone) {
            _cmdShow('正在扫描 VM 节点…');
            const sr = await _bridge('vis_mockup', 'scan_vis_catia_map');
            if (sr?.success) { _catiaScanDone = true; _refreshVmMatchCounts(); }
          }
          const r = await _bridge('vis_mockup', 'highlight_nodes_by_catia',
            { catia_names: allParts, mode: 'highlight' });
          if (r?.success) {
            const inTree = r.data.keys?.length > 0 ? _selectVisTreeNodes(r.data.keys) : 0;
            const treeHint = inTree > 0 ? `，VM树已选中 ${inTree} 个` : '';
            _cmdShow(`高亮 ${r.data.matched}/${allParts.length} 个零件${treeHint}`, 'ok');
          } else {
            _cmdShow(r?.error || '高亮失败', 'err');
          }
        }
      }
    });
  });
}

/** 收集一个 BOP 行及其所有展开子孙行的全部 catia_occ */
function _collectBopRowParts(row) {
  const parts = new Set();
  const _collect = el => {
    try {
      const raw = el.dataset?.parts;
      if (raw) JSON.parse(raw).forEach(p => { if (p) parts.add(p); });
    } catch(_) {}
    el.querySelectorAll('.cs-bop-row').forEach(_collect);
  };
  _collect(row);
  return [...parts];
}

/** 在 VM 结构树 UI 中选中（高亮）指定 node key 列表，返回实际找到的数量，并滚动到第一个 */
function _selectVisTreeNodes(keys) {
  $('visTreeBody').querySelectorAll('.cs-vis-node.cs-vis-active')
    .forEach(n => n.classList.remove('cs-vis-active'));
  let firstEl = null;
  let count = 0;
  for (const key of keys) {
    const entry = _visNodeMap[key];
    if (!entry) continue;
    entry.nodeEl.classList.add('cs-vis-active');
    count++;
    if (!firstEl) firstEl = entry.nodeEl;
  }
  if (firstEl) firstEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  return count;
}

// ── 底部详情面板 ───────────────────────────────────────────────────────────────

function _initDetailPanel() {
  const panel  = $('csDetailPanel');
  const handle = $('dpHandle');
  const resize = $('dpResize');
  const close  = $('dpClose');
  if (!panel) return;

  handle?.addEventListener('click', () => {
    _dpOpen = true;
    panel.classList.add('open');
    // 补充渲染（面板关闭时发生的点击会记录 root，打开时补渲染）
    if (_dpBopRootGid && $('dpBopContent') && !$('dpBopContent').classList.contains('hidden')) {
      _renderBopTree();
      _renderBopNodeDetail(_dpBopSelGid || _dpBopRootGid);
    }
  });
  close?.addEventListener('click', () => {
    _invalidateTeamcenterNodeDetail();
    _dpOpen = false;
    panel.classList.remove('open');
  });

  // BOP 树点击事件委托（持久绑定，innerHTML 变化不影响）
  $('dpBopTree')?.addEventListener('click', e => {
    const item = e.target.closest('.cs-dp-tree-item');
    if (!item) return;
    const gid = item.dataset.gid;
    const toggle = e.target.closest('.cs-dp-tree-toggle');
    if (toggle && !toggle.classList.contains('leaf')) {
      if (_dpExpandedGids.has(gid)) _dpExpandedGids.delete(gid);
      else _dpExpandedGids.add(gid);
      _renderBopTree();
      return;
    }
    _dpBopSelGid = gid;
    $('dpBopTree').querySelectorAll('.cs-dp-tree-item.selected')
      .forEach(el => el.classList.remove('selected'));
    item.classList.add('selected');
    _renderBopNodeDetail(gid);
  });

  // 拖拽调高
  let _dragging = false, _startY = 0, _startH = 240;
  resize?.addEventListener('mousedown', e => {
    _dragging = true;
    _startY = e.clientY;
    _startH = panel.offsetHeight;
    resize.classList.add('active');
    document.body.style.cursor = 'ns-resize';
    document.body.style.userSelect = 'none';
  });
  document.addEventListener('mousemove', e => {
    if (!_dragging) return;
    const newH = Math.max(120, Math.min(window.innerHeight * 0.6,
      _startH + (_startY - e.clientY)));
    panel.style.setProperty('--dp-h', newH + 'px');
  });
  document.addEventListener('mouseup', () => {
    if (!_dragging) return;
    _dragging = false;
    resize.classList.remove('active');
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  });
}

function _showBopDetail(entry) {
  if (!entry) return;
  _invalidateTeamcenterNodeDetail();

  // 始终更新把手标签
  const handleLabel = $('dpHandleLabel');
  if (handleLabel) handleLabel.textContent = `BOP: ${entry.title || entry.gid} ▲`;

  // 面板关闭时不更新内容
  if (!_dpOpen) return;

  // 头部
  const srcTag = $('dpSourceTag');
  if (srcTag) { srcTag.textContent = 'BOP'; srcTag.style.cssText = 'background:rgba(137,180,250,.15);color:#89b4fa'; }
  const titleEl = $('dpTitle');
  if (titleEl) titleEl.textContent = entry.title || entry.gid;

  // 显隐
  $('dpPlaceholder')?.classList.add('hidden');
  $('dpVisContent')?.classList.add('hidden');
  $('dpBopContent')?.classList.remove('hidden');

  // 初始化树状态（如果是新的根节点则重置）
  if (_dpBopRootGid !== entry.gid) {
    _dpBopRootGid  = entry.gid;
    _dpBopSelGid   = entry.gid;
    _dpExpandedGids.clear();
    _dpExpandedGids.add(entry.gid);
    // 默认也展开第一层子节点（工位以下）
    (_bopChildMap[entry.gid] || []).forEach(c => _dpExpandedGids.add(c.gid));
  }

  _renderBopTree();
  _renderBopNodeDetail(_dpBopSelGid);
}

/** 渲染 BOP 子树（左侧树，从 _dpBopRootGid 开始） */
function _renderBopTree() {
  const treeEl = $('dpBopTree');
  if (!treeEl || !_dpBopRootGid) return;

  const html = [];
  _renderBopTreeNode(_dpBopRootGid, 0, html);
  treeEl.innerHTML = html.join('');
  // 事件由 _initDetailPanel 中通过事件委托统一处理
}

function _renderBopTreeNode(gid, depth, html) {
  const entry = _bopEntryIndex[gid];
  if (!entry) return;
  const children   = _bopChildMap[gid] || [];
  const hasChildren = children.length > 0;
  const isExpanded  = _dpExpandedGids.has(gid);
  const isSelected  = _dpBopSelGid === gid;
  const indent      = depth * 16 + 8;
  const nt = _BOP_NT_MAP[entry.node_type] || { label: '?', color: '#6c7086' };

  html.push(`<div class="cs-dp-tree-item${isSelected ? ' selected' : ''}" data-gid="${gid}" style="padding-left:${indent}px">`);
  html.push(`<span class="cs-dp-tree-toggle${hasChildren ? (isExpanded ? ' expanded' : '') : ' leaf'}">▶</span>`);
  html.push(`<span class="cs-dp-tree-dot" style="background:${nt.color}"></span>`);
  html.push(`<span class="cs-dp-tree-label">${_esc(entry.title || entry.gid)}</span>`);
  const subCount  = _bopSubtreeParts[gid]   || 0;
  const subMatch  = _bopSubtreeMatched[gid] || 0;
  if (subCount > 0) {
    const hasScan = _vmCatiaSet.size > 0;
    const badgeInner = hasScan
      ? `<span style="color:${subMatch===subCount?'var(--green)':subMatch>0?'var(--yellow)':'var(--red)'}">${subMatch}</span><span style="opacity:.5">/${subCount}</span>`
      : String(subCount);
    const badgeTitle = hasScan
      ? `VM 已匹配 ${subMatch} / 子树共 ${subCount} 个零件`
      : `子树共 ${subCount} 个零件`;
    const cls = hasScan
      ? (subMatch===subCount ? 'cs-bop-badge-full' : subMatch>0 ? 'cs-bop-badge-partial' : 'cs-bop-badge-none')
      : '';
    html.push(`<span class="cs-dp-tree-partbadge ${cls}" title="${badgeTitle}">${badgeInner}</span>`);
  }
  html.push('</div>');

  if (hasChildren && isExpanded) {
    for (const child of children) _renderBopTreeNode(child.gid, depth + 1, html);
  }
}

/** 渲染右侧：字段 + 零件表（针对树中选中的节点） */
function _renderBopNodeDetail(gid) {
  const right = $('dpBopRight');
  if (!right) return;
  const entry = _bopEntryIndex[gid];
  if (!entry) { right.innerHTML = '<div class="cs-dp-empty-hint">未找到节点</div>'; return; }

  const nt = _BOP_NT_MAP[entry.node_type] || { label: entry.node_type || '节点', color: '#6c7086' };
  let html = `
    <div class="cs-dp-section-title">基本信息</div>
    <div class="cs-dp-field-row">
      <span class="cs-dp-field-label">类型</span>
      <span class="cs-dp-nt-badge" style="background:${nt.color}">${_esc(nt.label)}</span>
    </div>
    <div class="cs-dp-field-row">
      <span class="cs-dp-field-label">标题</span>
      <span class="cs-dp-field-val">${_esc(entry.title || '—')}</span>
    </div>
    ${entry.vpps ? `<div class="cs-dp-field-row">
      <span class="cs-dp-field-label">VPPS</span>
      <span class="cs-dp-field-val mono">${_esc(entry.vpps)}</span>
    </div>` : ''}
    ${entry.level != null ? `<div class="cs-dp-field-row">
      <span class="cs-dp-field-label">Level</span>
      <span class="cs-dp-field-val">${_esc(String(entry.level))}</span>
    </div>` : ''}
    ${entry.ai00_level != null ? `<div class="cs-dp-field-row">
      <span class="cs-dp-field-label">AI00 L</span>
      <span class="cs-dp-field-val">${_esc(String(entry.ai00_level))}</span>
    </div>` : ''}
    ${entry.sort_order != null ? `<div class="cs-dp-field-row">
      <span class="cs-dp-field-label">顺序</span>
      <span class="cs-dp-field-val">${_esc(String(entry.sort_order))}</span>
    </div>` : ''}
    <div class="cs-dp-field-row" style="margin-top:4px">
      <span class="cs-dp-field-label" style="opacity:.5">GID</span>
      <span class="cs-dp-field-val mono" style="opacity:.4;font-size:9px">${_esc(entry.gid)}</span>
    </div>
  `;

  const parts = entry.parts || [];
  if (parts.length === 0) {
    html += `<div class="cs-dp-section-title" style="margin-top:10px">关联零件</div>
      <div class="cs-dp-empty-hint">无关联零件</div>`;
  } else {
    html += `<div class="cs-dp-section-title" style="margin-top:10px">关联零件（${parts.length}）</div>
      <table class="cs-dp-parts-table">
        <thead><tr><th>图号</th><th>名称</th><th>Catia Occ</th><th>数量</th></tr></thead>
        <tbody>${parts.map(p => `<tr>
          <td class="mono">${_esc(p.part_no || '—')}</td>
          <td>${_esc(p.name || '—')}</td>
          <td class="mono">${_esc(p.catia_occ || '—')}</td>
          <td>${p.quantity != null ? _esc(String(p.quantity)) : '—'}</td>
        </tr>`).join('')}</tbody>
      </table>`;
  }
  right.innerHTML = html;
}

function _showVisDetail(node) {
  const panel = $('csDetailPanel');
  if (!panel || !node) return;
  _invalidateTeamcenterNodeDetail();

  // 把手标签
  const handleLabel = $('dpHandleLabel');
  if (handleLabel) handleLabel.textContent = `VM: ${node.name || 'node:' + node.key} ▲`;

  if (!_dpOpen) return;

  // 头部
  const srcTag = $('dpSourceTag');
  if (srcTag) {
    srcTag.textContent = 'VM';
    srcTag.style.cssText = 'background:rgba(166,227,161,.15);color:#a6e3a1';
  }
  const titleEl = $('dpTitle');
  if (titleEl) titleEl.textContent = node.name || `node:${node.key}`;

  // 显隐
  $('dpPlaceholder')?.classList.add('hidden');
  $('dpBopContent')?.classList.add('hidden');
  $('dpVisContent')?.classList.remove('hidden');

  // LEFT: 节点基本信息
  const left = $('dpVisLeft');
  if (left) {
    left.innerHTML = `
      <div class="cs-dp-section-title">节点信息</div>
      ${node.catia_name ? `<div class="cs-dp-field-row">
        <span class="cs-dp-field-label">Catia名</span>
        <span class="cs-dp-field-val mono">${_esc(node.catia_name)}</span>
      </div>` : ''}
      <div class="cs-dp-field-row">
        <span class="cs-dp-field-label">Key</span>
        <span class="cs-dp-field-val mono">${_esc(String(node.key || ''))}</span>
      </div>
      <div class="cs-dp-field-row">
        <span class="cs-dp-field-label">可见性</span>
        <span class="cs-dp-field-val">${node.visible ? '✓ 可见' : '✗ 隐藏'}</span>
      </div>
      <div class="cs-dp-field-row">
        <span class="cs-dp-field-label">子节点</span>
        <span class="cs-dp-field-val">${node.children?.length ?? 0}${node.has_more ? '+' : ''}</span>
      </div>
    `;
  }

  // RIGHT: PLM 元数据（按需加载）
  const right = $('dpVisRight');
  if (!right) return;
  right.innerHTML = `
    <div class="cs-dp-section-title">PLM 元数据</div>
    <button class="cs-dp-meta-btn" id="dpVisMetaBtn">加载元数据</button>
  `;
  right.querySelector('#dpVisMetaBtn')?.addEventListener('click', async () => {
    const btn = right.querySelector('#dpVisMetaBtn');
    if (btn) btn.textContent = '加载中…';
    if (!_vmConnected) { if (btn) btn.textContent = '未连接 VisMockup'; return; }
    const r = await _bridge('vis_mockup', 'get_node_metadata', { node_key: node.key });
    if (!r?.success) {
      right.innerHTML = `<div class="cs-dp-section-title">PLM 元数据</div>
        <div class="cs-dp-empty-hint">${_esc(r?.error || '加载失败')}</div>`;
      return;
    }
    const d = r.data;
    let html = '<div class="cs-dp-section-title">节点属性</div>';
    for (const [k, label] of [['PrintableName','名称'],['Fullname','全称'],
        ['DataStoreName','文件名'],['CADID','CADID']]) {
      if (d[k]) html += `<div class="cs-dp-field-row">
        <span class="cs-dp-field-label">${label}</span>
        <span class="cs-dp-field-val mono">${_esc(d[k])}</span>
      </div>`;
    }
    const meta = d['_metadata'] || {};
    const mkeys = Object.keys(meta).sort((a, b) => {
      const pri = ['catiaoccurrencename','__PLM_INST_UID'];
      const ia = pri.indexOf(a), ib = pri.indexOf(b);
      if (ia >= 0 && ib >= 0) return ia - ib;
      if (ia >= 0) return -1; if (ib >= 0) return 1;
      return a.localeCompare(b);
    });
    if (mkeys.length > 0) {
      html += `<div class="cs-dp-section-title">MetaData (${mkeys.length})</div>`;
      for (const k of mkeys) {
        html += `<div class="cs-dp-field-row">
          <span class="cs-dp-field-label" title="${_esc(k)}" style="overflow:hidden;text-overflow:ellipsis;max-width:100px">${_esc(k)}</span>
          <span class="cs-dp-field-val mono">${_esc(String(meta[k]))}</span>
        </div>`;
      }
    }
    right.innerHTML = html || '<div class="cs-dp-empty-hint">无可读元数据</div>';
  });
}



async function _loadTasks() {
  const cf = window.AI00Business?.available() || window.AI00Business?.available();
  if (!cf) return;
  try {
    const data = await _invokeCapability('project.task.read.atomic.tasks_search', {
      arguments: { list_gid: 'sim_eval', page_size: 200 },
    });
    _tasks = data?.items || data?.data || data || [];
  } catch(e) { console.warn('[cad_sim] loadTasks:', e); }
}

function _bindModal() {
  $('taskModalCancel')?.addEventListener('click', _closeTaskModal);
  $('taskModalSave')?.addEventListener('click', _saveTask);
  $('taskModalOverlay')?.addEventListener('click', e => {
    if (e.target === $('taskModalOverlay')) _closeTaskModal();
  });
}

function _openTaskModal() {
  $('taskModalGid').value = '';
  $('taskModalTitle').value = '';
  $('taskModalType').value = 'early_eval';
  $('taskModalWorkPlan').value = '';
  $('taskModalOverlay').classList.remove('hidden');
  $('taskModalTitle').focus();
}

function _closeTaskModal() { $('taskModalOverlay').classList.add('hidden'); }

async function _saveTask() {
  const title = $('taskModalTitle').value.trim();
  if (!title) { (await window.AI00Dialogs.alert('请输入任务标题')); return; }
  const cf = window.AI00Business?.available() || window.AI00Business?.available();
  if (!cf) { (await window.AI00Dialogs.alert('需要飞书登录才能创建任务')); return; }
  try {
    await _invokeCapability('project.task.change.apply.atomic.tasks_create', {
      title,
      list_gid: 'sim_eval',
      bop_version_gid: _selectedBopGid || null,
      task_type: $('taskModalType').value,
      work_plan_gid: $('taskModalWorkPlan').value.trim() || null,
    });
    _closeTaskModal();
    await _loadTasks();
  } catch(e) { (await window.AI00Dialogs.alert('创建失败: ' + e.message)); }
}

// ── VisMockup 结构树 ──────────────────────────────────────────────────────────

async function _captureOpSequence(overrideRootGid = null, progressCb = null) {
  return _openGovernedCapture(overrideRootGid, progressCb);
}

function _bindVisPanel() {
  // force=true：强制重新遍历（忽略缓存）
  $('btnRefreshVisTree')?.addEventListener('click', () => _loadVisTree(true));
  $('btnOpenPlmxmlTree')?.addEventListener('click', () => _openPlmxmlTree());
  $('vmPlmxmlFile')?.addEventListener('change', event => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (file) _openPlmxmlTree(file);
  });
  $('vmTreeDepth')?.addEventListener('change', () => _applyVisTreeOpenDepth());
  $('btnScanCatiaMap')?.addEventListener('click', async () => {
    if (!_vmConnected) { _cmdShow('未连接 VisMockup', 'err'); return; }
    _cmdShow('扫描中…');
    const r = await _bridge('vis_mockup', 'scan_vis_catia_map');
    if (r?.success) {
      _catiaScanDone = true;
      _cmdShow(`扫描完成：${r.data.count} 个映射节点`, 'ok');
      _refreshVmMatchCounts();
    } else {
      _cmdShow(r?.error || '扫描失败', 'err');
    }
  });
  $('btnCaptureOps')?.addEventListener('click', () => _openGovernedCapture());

  // 跨面板入口：assoc_panel 通过 window.top._cadSimCapture(lineGid, progressCb) 触发
  // 注意：lineage_view 可能嵌套在 craft_hub 内，window.parent 不是 workspace，需用 window.top
  const _topWin = window.top || window.parent || window;
  _topWin._cadSimCapture = (lineGid, progressCb) =>
    _openGovernedCapture(lineGid, progressCb);
}

let _alternateProjectionCached = false;
const _teamcenterInitialExpand = new Set();
function _setTreeCacheStatus(host, meta = {}) {
  if (!host) return;
  host._cacheMeta = meta;
  host.dataset.cachePending = meta.cached_at && (!meta.cacheOnly || meta.kind === 'models') ? 'true' : 'false';
  if (!host._cacheGuard) {
    host._cacheGuard = true;
    for (const type of ['contextmenu','dragstart','drop','click']) host.addEventListener(type, event => {
      if(['click','contextmenu'].includes(type)&&event.target.closest('[data-model-runtime-control]')) return;
      if (host.dataset.cachePending !== 'true' || (type === 'click' && !event.target.closest('input'))) return;
      if(type==='contextmenu') _showAlternateContextMenu(event,[]);
      event.preventDefault(); event.stopImmediatePropagation();
    }, true);
    host.addEventListener('contextmenu',event=>_showAlternateContextMenu(event,[]));
  }
  host.querySelector(':scope > .cs-tree-cache-status')?.remove();
  if (meta.cached_at || meta.error) {
    const status = document.createElement('div'); status.className = `${meta.cacheOnly ? 'cs-model-document-empty' : 'cs-model-document-warning'} cs-tree-cache-status`;
    status.textContent = meta.cacheOnly
      ? `结构缓存 · ${new Date(meta.cached_at).toLocaleString()} · 内容未核对`
      : meta.cached_at
      ? `缓存 ${new Date(meta.cached_at).toLocaleString()} · ${meta.error ? `读取失败，保留已缓存结构：${meta.error}` : meta.pending ? '读取中…' : '内容未核对'}（只读）`
      : `读取失败：${meta.error}`;
    status.title = meta.error || '结构缓存与运行会话独立；旧运行节点须重新定位，不能按同名文件自动关联';
    host.prepend(status);
  }
  if(meta.workspaceGid) window.AI00TreeProjectionCache.bindView(host,_eAPI()?.simulationTreeCache,meta);
}
function _projectionCache() {
  return window.AI00TreeProjectionCache.create(() => _eAPI()?.simulationTreeCache,_simulationDebug);
}

window._discardCachedModelProjection = async workspaceGid => {
  if(String(_modelDocumentWorkspaceGid)!==String(workspaceGid))return;
  _modelDocumentCollection?.replace([]);
  _renderModelDocuments([]);
  _setTreeCacheStatus($('modelDocumentList'),{error:'cache_model_document_not_found'});
  try { await _eAPI()?.simulationTreeCache?.remove?.(workspaceGid,'models'); }
  catch(error){_simulationDebug('projection_storage_failed',{workspace_gid:workspaceGid,cache_kind:'models',action:'remove',error_code:error?.message});}
};

async function _persistModelProjectionCache({required=false}={}) {
  const workspaceGid = _modelDocumentWorkspaceGid;
  const api = _eAPI()?.simulationTreeCache;
  if (!workspaceGid || typeof api?.put !== 'function') {if(required)throw Error('tree_cache_unavailable');return;}
  try {
    await api.put(workspaceGid, 'models', { items: _modelDocumentCollection.state.documents });
    _simulationDebug('projection_write',{workspace_gid:workspaceGid,cache_kind:'models',item_count:_modelDocumentCollection.state.documents.length,reason:'lazy_page_persisted'});
  } catch (error) { _simulationDebug('projection_storage_failed',{workspace_gid:workspaceGid,cache_kind:'models',action:'write',error_code:error?.message});if(required)throw error; }
}

const _modelDocumentRemovals = new Set();
async function _removeModelDocument(documentGid) {
  const workspace = window._simulationEnvironmentWorkspace?.store?.state?.workspace;
  const item = _modelDocumentCollection?.state.documents.find(item => item.document_gid === documentGid);
  if (!workspace?.workspace_gid || _modelDocumentWorkspaceGid !== workspace.workspace_gid) throw new Error('请先选择仿真环境');
  if (!item) throw new Error('model_document_not_found');
  if (item.role !== 'inserted') throw new Error('primary_model_document_protected');
  const removalKey = `${workspace.workspace_gid}:${documentGid}`;
  if (_modelDocumentRemovals.has(removalKey)) return;
  _modelDocumentRemovals.add(removalKey);
  try {
    const expectedVersion = workspace.row_version;
    const result = await _invokeCapability('simulation.environment.model_document.remove', {
      workspace_gid: workspace.workspace_gid, document_gid: documentGid, expected_row_version: expectedVersion,
      idempotency_key: `model-remove-${removalKey}-${window.crypto?.randomUUID?.() || Date.now()}`,
    }, { confirmation: true, idempotency: true });
    if (result?.removed !== true || result.document_gid !== documentGid || result.workspace_gid !== workspace.workspace_gid) throw new Error('model_document_remove_unverified');
    window.dispatchEvent(new CustomEvent('simulation:model-document-removed', {detail: {workspace_gid: workspace.workspace_gid, document_gid: documentGid}}));
    if (window._simulationEnvironmentWorkspace?.store?.state?.workspace !== workspace || _modelDocumentWorkspaceGid !== workspace.workspace_gid) return;
    ++_modelRefreshGeneration;
    // Keep unsaved environment edits; removal returns the authoritative revision.
    if (workspace.row_version === expectedVersion) {
      workspace.row_version = result.workspace_row_version;
      workspace.cache_revision_hash = result.cache_revision_hash;
    }
    _modelDocumentCollection.replace(_modelDocumentCollection.state.documents.filter(item => item.document_gid !== documentGid));
    _renderModelDocuments(_modelDocumentCollection.state.documents);
    await _persistModelProjectionCache();
    _cmdShow(`${item.display_name || documentGid} 已从当前环境移除，源文件保留`, 'ok');
  } finally { _modelDocumentRemovals.delete(removalKey); }
}

let _cacheSnapshotViewerController=null;
const _cacheSnapshotResumeCandidates=new Map();
const _cacheSnapshotResumeKey=(workspaceGid,documentGid)=>`${workspaceGid}:${documentGid}`;
window._cacheSnapshotResumeCandidate=(workspaceGid,documentGid)=>_cacheSnapshotResumeCandidates.get(_cacheSnapshotResumeKey(workspaceGid,documentGid))||null;
window._cacheSnapshotResumeCandidatesForWorkspace=workspaceGid=>[..._cacheSnapshotResumeCandidates.values()].filter(value=>value.workspace_gid===String(workspaceGid));
window._cacheSnapshotCurrentDocument=(workspaceGid,documentGid)=>String(_modelDocumentWorkspaceGid)===String(workspaceGid)?_modelDocumentCollection?.state?.documents?.find(item=>String(item.document_gid)===String(documentGid))||null:null;
window._forgetCacheSnapshotResumeCandidate=(workspaceGid,documentGid)=>{
  if(workspaceGid==null||documentGid==null)_cacheSnapshotResumeCandidates.clear();
  else _cacheSnapshotResumeCandidates.delete(_cacheSnapshotResumeKey(workspaceGid,documentGid));
};
window.addEventListener('pagehide',()=>window._forgetCacheSnapshotResumeCandidate());
window.addEventListener('simulation:model-document-removed',event=>window._forgetCacheSnapshotResumeCandidate(event.detail?.workspace_gid,event.detail?.document_gid));
window._cancelCacheSnapshotOpening=()=>_cacheSnapshotViewerController?.invalidate?.();
function _cacheSnapshotReason(code){
  return ({
    relative_missing_absolute_may_be_placeholder:'缓存缺少相对装配位置，现有绝对矩阵不能单独作为可靠位置',
    relative_transform_invalid:'缓存中的相对装配位置格式无效',
    transform_composition_mismatch:'相对位置与父级位置组合后，与缓存的绝对位置不一致',
    parent_absolute_unavailable:'缓存缺少可用的父级绝对位置，无法核对装配位置',
    root_absolute_missing:'缓存缺少根节点的绝对位置',root_absolute_invalid:'缓存中的根节点绝对位置无效',
    absolute_transform_missing:'缓存缺少节点的绝对位置',absolute_transform_invalid:'缓存中的节点绝对位置无效',
    cache_absolute_transform_unavailable:'缓存中没有可用的绝对装配位置',
    cache_transform_unavailable:'缓存中的装配位置尚未通过核对',transform_missing:'缓存缺少可靠的装配位置',
    cache_geometry_references_unavailable:'缓存中未能取得模型文件引用',
    cache_geometry_reference_unsupported:'缓存中的模型文件引用不是受支持的 JT 文件',
    cache_node_excluded:'此节点缺少可靠的装配或模型文件信息',
  })[code]||'此节点缺少可靠的装配或模型文件信息';
}
function _renderCacheSnapshotExclusions(model,row){
  row.querySelector('.cs-cache-exclusions')?.remove();
  const excluded=model._cacheViewer?.excluded;if(!excluded?.length)return;
  const details=document.createElement('details');details.className='cs-cache-exclusions cs-model-document-warning';
  const summary=document.createElement('summary');summary.textContent=`${excluded.length} 个节点未加载`;details.append(summary);
  const list=document.createElement('ul');
  const names=new Map((model.product_tree?.nodes||[]).map(node=>[node.cache_node_key,node.name]));
  for(const entry of excluded){const item=document.createElement('li');item.textContent=`${entry.name||names.get(entry.node_key)||entry.node_key}：${_cacheSnapshotReason(entry.error_code||entry.reason)}`;item.title=entry.node_key;list.append(item);}
  details.append(list);row.append(details);
}
function _cacheSnapshotExclusion(model,node){
  if(!model._cacheViewer)return null;
  const excluded=model._cacheViewer.excluded?.find(item=>item.node_key===node.cache_node_key);
  if(excluded)return excluded.reason||excluded.error_code||'cache_node_excluded';
  if(model._cacheViewer.node_map?.[node.cache_node_key])return null;
  return null; // A branch outside this materialization remains available to load.
}
window._invalidateCacheSnapshotVisibility=reason=>{
  if(reason==='outcome_unknown'||reason==='auth_lost')window._forgetCacheSnapshotResumeCandidate();
  for(const model of _modelDocumentCollection?.state?.documents||[]){
    if(model.source_kind!=='teamcenter_cache_snapshot')continue;
    delete model._cacheViewer;
    for(const node of model.product_tree?.nodes||[]){node.visible=null;node.visibility_state='unknown';}
    for(const row of $('modelDocumentList')?.querySelectorAll('.cs-model-document-row')||[])if(row.dataset.documentGid===String(model.document_gid))_renderCacheSnapshotExclusions(model,row);
  }
  for(const row of $('modelDocumentList')?.querySelectorAll('.cs-alternate-tree-item')||[])row._syncModelVisibility?.();
};
window._ensureCacheSnapshotViewer=async (model,node)=>{
  model=_modelDocumentCollection?.state?.documents?.find(item=>String(item.document_gid)===String(model?.document_gid))||model;
  const workspace=window._simulationEnvironmentWorkspace?.store?.state?.workspace,local=window._localViewerInteraction?.();
  if(!workspace?.workspace_gid||!model?.cache_binding||!local||!window.AI00CacheSnapshotViewer)throw Error('cache_document_not_ready');
  if(local.state==='outcome_unknown'){window._forgetCacheSnapshotResumeCandidate(workspace.workspace_gid,model.document_gid);throw Error('outcome_unknown');}
  if(node&&(!node.cache_node_key||!model.product_tree?.nodes?.some(item=>item.node_key===node.node_key&&item.cache_node_key===node.cache_node_key)))throw Error('cache_scope_node_not_found');
  const coversScope=model._cacheViewer&&(node?Object.hasOwn(model._cacheViewer.node_map||{},node.cache_node_key):!model._cacheViewer.root_node_key);
  if(coversScope&&local.state==='ready'&&local.scope?.workspace_gid===String(workspace.workspace_gid)&&local.scope.document_gid===String(model.document_gid)&&local.visibilityContext===model._cacheViewer.visibility_context)return model._cacheViewer;
  const input={workspace_gid:String(workspace.workspace_gid),document_gid:String(model.document_gid),cache_binding:model.cache_binding,...(node?{root_node_key:node.cache_node_key,source_node_id:node.node_key,node_name:node.name}:{})};
  const current=value=>String(window._simulationEnvironmentWorkspace?.store?.state?.workspace?.workspace_gid)===value.workspace_gid&&(_modelDocumentCollection?.state?.documents||[]).some(doc=>String(doc.document_gid)===value.document_gid&&JSON.stringify(doc.cache_binding)===JSON.stringify(value.cache_binding));
  if(!current(input))throw Error('document_selection_changed');
  if(!_cacheSnapshotViewerController)_cacheSnapshotViewerController=window.AI00CacheSnapshotViewer.create({invoke:(...args)=>_invokeCapability(...args),interaction:local,cancelOpen:id=>{const api=_eAPI();if(!api?.cancelModelOpen)throw Error('cache_open_cancel_unavailable');return api.cancelModelOpen(id);},localProgress:hash=>_eAPI()?.modelFileProgress?.(hash),isCurrent:current,log:_simulationDebug,onProgress:progress=>{
    if(String(window._simulationEnvironmentWorkspace?.store?.state?.workspace?.workspace_gid)!==progress.workspace_gid)return;
    const labels={local_cache_checked:'检查本机 JT 缓存',jt_download_started:'正在从 TC/FMS 下载 JT',jt_download_completed:'JT 已下载，正在校验',local_file_verified:'本机 JT 已校验',local_materialization_failed:'本机 JT 准备失败',native_open_started:'正在载入 VisMockup',native_open_completed:'VisMockup 已载入',dependencies_resolved:'已确认 TC 文件引用',assembly_prepared:'装配依据就绪',local_materialization:'检查本机缓存，按需从 TC/FMS 下载并打开',waiting_admission:'等待执行名额',inspecting:'读取固定快照',scope_resolved:'已确认加载范围',node_excluded:'部分缓存节点未加载',file_requested:'获取 JT 文件',file_started:'获取 JT 文件',file_result_retry:'等待 FMS 文件结果',batch_requested:'提交 JT 文件批次',batch_admitted:'JT 文件批次已提交',batch_running:'正在获取 JT 文件',batch_result_retry:'等待 JT 文件批次结果',batch_result_received:'已读取批次明细',batch_history_replaced:'重新准备 JT 文件',batch_preflight_failed:'批次预检失败',batch_outcome_unknown:'JT 文件批次结果待确认',file_failed:'JT 文件获取失败',file_outcome_unknown:'JT 文件结果待确认',file_completed:'JT 文件就绪',files_progress:'获取 JT 文件',building_package:'组装固定快照',opening_document:'打开缓存模型',binding_document:'核对缓存文档',ready:'缓存模型已打开',failed:'缓存模型打开失败'};
    const detail=progress.error_code==='cache_package_result_limit'
      ? '装配描述或打开请求超过当前运行端的大小上限；尚未打开或截图'
      : progress.stage==='node_excluded'?`${progress.name||''} · ${_cacheSnapshotReason(progress.error_code)}`:progress.message;
    const message=(labels[progress.stage]||progress.stage)+(Number.isFinite(progress.total)?` · ${progress.completed||0}/${progress.total}`:'')+(Number.isFinite(progress.cache_hits)?` · 本机命中 ${progress.cache_hits}`:'')+(detail?` · ${detail}`:'');
    for(const marker of document.querySelectorAll('#viewerInteractionRoute, [data-viewer-interaction-route]')){marker.textContent=message;marker.dataset.state=progress.stage;marker.setAttribute('aria-busy',String(!['ready','failed'].includes(progress.stage)));}
  }});
  const previous=model._cacheViewer;
  _cmdShow('');
  let opened,result;
  try{
    opened=await _cacheSnapshotViewerController.open(input);
    result=window.AI00CacheSnapshotViewer.mergeLoadedBranches(previous,opened);
  }catch(error){if(error.cache_effect_unknown||/outcome_unknown|interaction_bridge_timeout|cache_open_interrupted|cache_environment_mapping_conflict/.test(error.message))window._forgetCacheSnapshotResumeCandidate(input.workspace_gid,input.document_gid);throw error;}
  if(!current(input))throw Error('document_selection_changed');
  // Runtime mapping and calibration never enter the persisted structure cache.
  Object.defineProperty(model,'_cacheViewer',{value:result,writable:true,configurable:true,enumerable:false});
  try{
    const candidate=window.AI00CacheSnapshotViewer.captureResumeCandidate({...input,product_tree:model.product_tree},result);
    _cacheSnapshotResumeCandidates.set(_cacheSnapshotResumeKey(input.workspace_gid,input.document_gid),candidate);
  }catch{window._forgetCacheSnapshotResumeCandidate(input.workspace_gid,input.document_gid);}
  for(const row of $('modelDocumentList')?.querySelectorAll('.cs-model-document-row')||[])if(row.dataset.documentGid===String(model.document_gid))_renderCacheSnapshotExclusions(model,row);
  for(const node of model.product_tree?.nodes||[]){node.visible=null;node.visibility_state='unknown';}
  for(const row of $('modelDocumentList')?.querySelectorAll('.cs-alternate-tree-item')||[])row._syncModelVisibility?.();
  return result;
};
async function _openCachedModelDocument(model){
  model=_modelDocumentCollection?.state?.documents?.find(item=>String(item.document_gid)===String(model?.document_gid))||model;
  try{
    await window._ensureLocalViewerReady(model);
    const node=model.product_tree?.nodes?.find(node=>!_cacheSnapshotExclusion(model,node));
    if(node)await window._actOnModelNode({workspaceGid:window._simulationEnvironmentWorkspace.store.state.workspace.workspace_gid,document:model,nodeKey:node.node_key,action:'show',calibrateOnly:true});
    for(const row of $('modelDocumentList')?.querySelectorAll('.cs-alternate-tree-item')||[])row._syncModelVisibility?.();
    _cmdShow('缓存模型已打开；显隐以 VisMockup 回读为准，未加载节点保留问号');
  }catch(error){_cmdShow(error.message||'缓存模型打开失败','err');}
}
window._syncModelDocumentVisibility = model => {
  if (!_modelDocumentCollection?.state?.documents?.includes(model)) return;
  const branches = new Map(), stack = window.AI00ModelDocumentCollection.buildProductForest(model.product_tree?.nodes || []);
  while (stack.length) { const node = stack.pop(); branches.set(String(node.node_key), node); stack.push(...node.children); }
  for (const documentRow of $('modelDocumentList')?.querySelectorAll('.cs-model-document-row') || []) {
    if (documentRow.dataset.documentGid !== String(model.document_gid)) continue;
    for (const row of documentRow.querySelectorAll('.cs-alternate-tree-item')) row._syncModelVisibility?.(branches);
  }
};
window._renderCacheSnapshotResumeDocument=model=>{
  if(_modelDocumentCollection?.state?.documents?.includes(model))_renderModelDocuments(_modelDocumentCollection.state.documents);
};
function _renderModelDocuments(items = []) {
  for(const model of items)if(model.source_kind==='teamcenter_cache_snapshot'&&!model._cacheViewer)for(const node of model.product_tree?.nodes||[]){node.visible=null;node.visibility_state='unknown';}
  const host = $('modelDocumentList');
  if (!host) return;
  if (!items.length) {
    host.innerHTML = '<span class="cs-model-document-empty">尚未添加模型文件</span>';
    return;
  }
  host.replaceChildren(...items.map(item => {
    if(item.source_kind==='teamcenter_online')window.AI00TeamcenterOnlineSource?.hydrateControlKeys?.(item.product_tree);
    const row = document.createElement('div');
    row.className = 'cs-model-document-row';
    row.dataset.documentGid = item.document_gid;
    row.dataset.cacheViewKey = 'doc:'+item.document_gid;
    const type = item.source_kind==='teamcenter_cache_snapshot' ? '缓存批次' : item.media_type.includes('teamcenter') ? '在线' : item.media_type.includes('jt') ? 'JT' : 'PLMXML';
    const hasTree = item.product_tree?.state === 'ready' && item.product_tree.node_count > 0;
    row.innerHTML = `<div class="cs-model-document-summary"><button type="button" class="cs-model-document-toggle" ${hasTree ? '' : 'disabled'}>${hasTree ? '▸' : ''}</button><span class="cs-model-document-role">${item.role === 'primary' ? '主文件' : '插入'}</span><span class="cs-model-document-name"></span><span class="cs-model-document-count"></span><span class="cs-model-document-type">${type}</span></div><div class="cs-model-document-tree hidden"></div>`;
    const name = row.querySelector('.cs-model-document-name');
    name.textContent = item.display_name || item.document_gid;
    name.title = name.textContent;
    const count = row.querySelector('.cs-model-document-count');
    const pendingDependencies = item.product_tree?.dependency_locations || [];
    count.textContent = item.product_tree_loading ? '读取中…' : hasTree
      ? item.product_tree.source==='teamcenter_children' ? `已加载 ${item.product_tree.node_count} 项 · 按需读取`
      : `${item.product_tree.node_count} 项${item.product_tree.complete === false ? ' · 深层结构未读完' : ''}${pendingDependencies.length ? ` · ${pendingDependencies.length} 个引用待解析` : ''}` : '';
    count.title = count.textContent;
    count.classList.toggle('cs-model-document-count-warning', pendingDependencies.length > 0);
    const tree = row.querySelector('.cs-model-document-tree');
    if (item.product_tree?.state === 'dependency_required') {
      const missing = document.createElement('div'); missing.className = 'cs-model-document-warning';
      missing.textContent = `缺少引用文件：${item.product_tree.dependency_locations.join('、')}`;
      tree.replaceChildren(missing); tree.classList.remove('hidden');
    } else if (item.product_tree_error && !hasTree) {
      const error = document.createElement('div'); error.className = 'cs-model-document-warning';
      error.textContent = `结构读取失败：${item.product_tree_error}`; tree.replaceChildren(error); tree.classList.remove('hidden');
      const retry = document.createElement('button'); retry.type = 'button'; retry.textContent = '重新读取结构';
      retry.addEventListener('click', () => { retry.disabled = true; void _refreshModelDocuments(undefined,{refreshDocumentGid:String(item.document_gid),refreshChildren:true}).catch(err => _cmdShow(err.message || '结构读取失败', 'err')); });
      tree.append(retry);
    } else if (hasTree) {
      const forest = window.AI00ModelDocumentCollection.buildProductForest(item.product_tree.nodes);
      let rendered = false;
      row.querySelector('.cs-model-document-toggle').addEventListener('click', event => {
        event.stopPropagation();
        const hidden = tree.classList.toggle('hidden');
        event.currentTarget.textContent = hidden ? '▸' : '▾';
        if (!hidden && !rendered) { tree.replaceChildren(...forest.map(node => _buildProductTreeItem(node, item.document_gid))); rendered = true; }
      });
      if(item.product_tree.source==='teamcenter_cache_snapshot') {
        const info=document.createElement('div');info.className='cs-model-document-empty';
        info.textContent=`固定批次 ${item.cache_binding.batch_id} · ${item._cacheViewer?'已加载有效实例；未加载节点保留问号':'可打开有效实例并校准显隐'}`;row.append(info);
        const open=document.createElement('button');open.type='button';open.textContent='打开缓存模型';open.dataset.modelRuntimeControl='true';open.disabled=!window.AI00CacheSnapshotViewer;
        open.onclick=async event=>{event.stopPropagation();open.disabled=true;try{await _openCachedModelDocument(item);}finally{open.disabled=!window.AI00CacheSnapshotViewer;}};row.append(open);
        const rootsPage=item.product_tree.pages.roots;
        if(rootsPage?.next_cursor!=null||rootsPage?.error){
          const more=document.createElement('button');more.type='button';more.textContent=rootsPage.error?'重试根节点读取':'加载更多根节点';
          more.onclick=async()=>{more.disabled=true;try{
            await window.AI00CacheSnapshotSource.readChildren(_invokeCapability,item.product_tree,null,{more:rootsPage.next_cursor!=null,isCurrent:()=>_modelDocumentCollection.state.documents.includes(item)});
            if(_modelDocumentCollection.state.documents.includes(item))_renderModelDocuments(_modelDocumentCollection.state.documents);
          }catch(error){more.textContent=`重试：${error.message}`;more.disabled=false;}};row.append(more);
        }
      }
      if(item.product_tree.source==='teamcenter_children') {
        if(item.product_tree_error){const warning=document.createElement('div');warning.className='cs-model-document-warning';warning.textContent=`结构读取失败，保留已加载内容：${item.product_tree_error}`;row.append(warning);}
        const hostHasView=$('modelDocumentList')?._viewState;
        if(!hostHasView||_teamcenterInitialExpand.delete(String(item.document_gid))){row.querySelector('.cs-model-document-toggle').click();tree.querySelector('.cs-alternate-tree-item[data-lazy-unloaded="false"] > .cs-alternate-tree-line > .cs-alternate-tree-toggle:not(:disabled)')?.click();}
      }
    }
    const summary = row.querySelector('.cs-model-document-summary');
    if(item.source_kind==='teamcenter_cache_snapshot')_renderCacheSnapshotExclusions(item,row);
    summary.draggable = item.source_kind!=='teamcenter_cache_snapshot';
    summary.addEventListener('contextmenu', event => _showAlternateContextMenu(event, [...(item.source_kind==='teamcenter_cache_snapshot'?[{label:'打开缓存模型',disabled:!window.AI00CacheSnapshotViewer,run:()=>_openCachedModelDocument(item)}]:[]),...(item.role === 'inserted' ? [{
      label:'移除', danger:true,
      disabled:_modelDocumentRemovals.has(`${_modelDocumentWorkspaceGid}:${item.document_gid}`),
      run:()=>{void _removeModelDocument(item.document_gid).catch(error=>_cmdShow(error.message||'模型移除失败','err'));},
    }] : [])]));
    summary.addEventListener('dragstart', event => {
      if(item.source_kind==='teamcenter_cache_snapshot'){event.preventDefault();return;}
      event.dataTransfer?.setData('application/x-ai00-model-document', item.document_gid);
      if (event.dataTransfer) event.dataTransfer.effectAllowed = 'copy';
    });
    return row;
  }));
}

const _teamcenterDetailFields = [
  ['name','名称'], ['item_id','Item ID'], ['revision_id','版本'],
  ['component_type','对象类型'], ['owning_user','所有者'],
  ['owning_group','所属组'], ['weight_raw','重量'],
  ['unit_weight_raw','单位重量'], ['torque_raw','扭矩'],
  ['torque_importance','扭矩重要度'], ['occurrence_uid','实例 UID'],
];

function _teamcenterKnownProperties(node) {
  return {
    name: node.name || null,
    item_id: node.item_id || null,
    revision_id: node.revision || node.revision_id || null,
    component_type: node.component_type || null,
    owning_user: node.owning_user || null,
    owning_group: node.owning_group || null,
    weight_raw: node.weight_raw || null,
    unit_weight_raw: node.unit_weight_raw || null,
    torque_raw: node.torque_raw || null,
    torque_importance: node.torque_importance || null,
    occurrence_uid: node.occurrence_path?.at(-1)?.occurrence_uid || null,
  };
}

function _renderTeamcenterNodeDetail(modelDocument, node, state = {}) {
  const panel = $('csDetailPanel');
  if (!panel) return;
  _dpOpen = true;
  panel.classList.add('open');
  const values = { ..._teamcenterKnownProperties(node), ...(state.properties || {}) };
  const title = values.name || node.name || node.node_key;
  const handle = $('dpHandleLabel');
  if (handle) handle.textContent = `Teamcenter: ${title} ▲`;
  const source = $('dpSourceTag');
  if (source) {
    source.textContent = modelDocument.source_kind==='teamcenter_cache_snapshot'?'项目缓存批次':state.loaded && state.cacheHit ? '本地缓存' : 'Teamcenter';
    source.style.cssText = state.loaded && state.cacheHit
      ? 'background:rgba(137,180,250,.15);color:#89b4fa'
      : 'background:rgba(166,227,161,.15);color:#a6e3a1';
  }
  const titleElement = $('dpTitle');
  if (titleElement) titleElement.textContent = title;
  $('dpPlaceholder')?.classList.add('hidden');
  $('dpBopContent')?.classList.add('hidden');
  $('dpVisContent')?.classList.remove('hidden');
  const left = $('dpVisLeft');
  if (left) left.innerHTML = `<div class="cs-dp-section-title">${modelDocument.source_kind==='teamcenter_cache_snapshot'?'缓存模型节点':'在线模型节点'}</div>
    <div class="cs-dp-field-row"><span class="cs-dp-field-label">节点</span><span class="cs-dp-field-val mono">${_esc(node.node_key || '')}</span></div>
    <div class="cs-dp-field-row"><span class="cs-dp-field-label">来源</span><span class="cs-dp-field-val">${modelDocument.source_kind==='teamcenter_cache_snapshot'?'缓存批次 '+_esc(modelDocument.cache_binding.batch_id):'Teamcenter 在线结构'}</span></div>`;
  const rows = _teamcenterDetailFields
    .filter(([key]) => values[key] !== null && values[key] !== undefined && String(values[key]).trim() !== '')
    .map(([key,label]) => `<div class="cs-dp-field-row"><span class="cs-dp-field-label">${label}</span><span class="cs-dp-field-val mono">${_esc(String(values[key]))}</span></div>`)
    .join('');
  const right = $('dpVisRight');
  if (!right) return;
  const status = state.loading
    ? '<div class="cs-dp-empty-hint" data-teamcenter-detail-loading>读取中…</div>'
    : state.error
      ? `<div class="cs-dp-empty-hint">属性读取失败：${_esc(state.error)}</div><button class="cs-dp-meta-btn" type="button" data-teamcenter-detail-retry>${state.loginRequired ? '登录并重试' : '重试'}</button>`
      : '';
  right.innerHTML = `<div class="cs-dp-section-title">节点属性</div>${rows}${status}`;
  if(modelDocument.source_kind==='teamcenter_cache_snapshot'&&state.rawFields){
    const details=document.createElement('details'),summary=document.createElement('summary'),raw=document.createElement('pre');
    summary.textContent=`批次原始属性与读取状态（${state.rawFields.length} 项）`;
    raw.style.cssText='white-space:pre-wrap;overflow-wrap:anywhere';raw.textContent=JSON.stringify(state.rawFields,null,2);
    details.append(summary,raw);right.append(details);
  }
  right.querySelector('[data-teamcenter-detail-retry]')?.addEventListener('click', async event => {
    event.currentTarget.disabled = true;
    if (state.loginRequired && !await _requireTeamcenterLogin()) {
      event.currentTarget.disabled = false;
      return;
    }
    void _selectTeamcenterNodeDetail(modelDocument, node);
  });
}

async function _selectTeamcenterNodeDetail(modelDocument, node) {
  const request = ++_teamcenterDetailRequest;
  const identity = `${modelDocument.document_gid}:${node.node_key}`;
  _teamcenterDetailSelection = identity;
  _renderTeamcenterNodeDetail(modelDocument, node, {loading:true});
  try {
    const currentNode = Array.isArray(node?.occurrence_path) ? node : await _ensureTeamcenterControlNode(
      modelDocument, node, () => request === _teamcenterDetailRequest && _teamcenterDetailSelection === identity, true);
    const result = modelDocument.source_kind==='teamcenter_cache_snapshot'
      ? (await window.AI00CacheSnapshotSource.readNode(_invokeCapability,modelDocument.product_tree,currentNode.cache_node_key)).properties_result
      : currentNode.cloud_properties_result || await window.AI00TeamcenterOnlineSource.readNodeProperties(
        _requestVisMockupCommand, modelDocument, currentNode);
    if (request !== _teamcenterDetailRequest || _teamcenterDetailSelection !== identity) return;
    _renderTeamcenterNodeDetail(modelDocument, currentNode, {
      loaded:true, cacheHit:result.cache_hit, properties:result.properties,rawFields:result.raw_fields,
    });
  } catch (error) {
    if (request !== _teamcenterDetailRequest || _teamcenterDetailSelection !== identity) return;
    const code = error?.message || 'teamcenter_node_properties_unavailable';
    _renderTeamcenterNodeDetail(modelDocument, node, {
      error:code, loginRequired:code === 'teamcenter_login_required',
    });
  }
}

const _isRawTeamcenterControlKey=value=>/^tc:(?!sha256:)[^\s]+$/.test(String(value||''));
async function _ensureTeamcenterControlNode(modelDocument,item,isCurrent,requireOccurrencePath=false) {
  if(modelDocument?.source_kind!=='teamcenter_online')return item;
  const tree=modelDocument?.product_tree,path=Array.isArray(item?.occurrence_path)?item.occurrence_path:null;
  const occurrenceUid=path?.length?path.at(-1)?.occurrence_uid:null;
  const derived=occurrenceUid?`tc:${occurrenceUid}`:null;
  if(_isRawTeamcenterControlKey(derived))item.control_key=derived;
  const syntheticRoot=item?.parent_key==null&&Array.isArray(path)&&path.length===0;
  if(requireOccurrencePath ? path?.length>0||syntheticRoot : _isRawTeamcenterControlKey(item?.control_key))return item;
  const parent=tree?.nodes?.find(node=>String(node.node_key)===String(item?.parent_key));
  const parentPath=path?.length ? path.slice(0,-1) : Array.isArray(parent?.occurrence_path)?parent.occurrence_path:[];
  await window.AI00TeamcenterOnlineSource.readChildren(_requestVisMockupCommand,modelDocument,tree,parentPath,{refresh:true,isCurrent});
  if(!isCurrent())throw Error('document_selection_changed');
  const refreshed=tree.nodes.find(node=>String(node.node_key)===String(item.node_key));
  if(!refreshed)throw Error('model_node_runtime_identity_unavailable');
  if(requireOccurrencePath&&(refreshed.occurrence_path?.length>0
    ||refreshed.parent_key==null&&Array.isArray(refreshed.occurrence_path)))return refreshed;
  if(_isRawTeamcenterControlKey(refreshed.control_key)||refreshed.parent_key==null)return refreshed;
  throw Error('model_node_runtime_identity_unavailable');
}

function _buildProductTreeItem(item, documentGid) {
  const wrapper = document.createElement('div'); wrapper.className = 'cs-alternate-tree-item';
  wrapper.dataset.cacheViewKey = 'product:'+documentGid+':'+item.node_key;
  const line = document.createElement('div'); line.className = 'cs-alternate-tree-line';
  const children = document.createElement('div'); children.className = 'cs-alternate-tree-children hidden';
  const toggle = document.createElement('button'); toggle.type = 'button'; toggle.className = 'cs-alternate-tree-toggle';
  const modelDocument=_modelDocumentCollection?.state.documents.find(doc=>String(doc.document_gid)===String(documentGid));
  const cachedSnapshot=modelDocument?.source_kind==='teamcenter_cache_snapshot';
  const lazy=cachedSnapshot||modelDocument?.product_tree?.source==='teamcenter_children';
  const pageKey=node=>cachedSnapshot?node.cache_node_key:JSON.stringify(node.occurrence_path);
  if(lazy)wrapper.dataset.lazyUnloaded=modelDocument.product_tree.pages[pageKey(item)]?'false':'true';
  toggle.textContent = item.children.length || lazy&&item.has_children!==false ? '▸' : ''; toggle.disabled = !item.children.length && !(lazy&&item.has_children!==false);
  let rendered = false;
  toggle.addEventListener('click', event => {
    event.stopPropagation(); const hidden = children.classList.toggle('hidden'); toggle.textContent = hidden ? '▸' : '▾';
    if(lazy){
      if(!hidden){renderLazy();const page=modelDocument.product_tree.pages[pageKey(item)];if(!page&&!$('modelDocumentList')?._viewRestoring)void loadLazy();}
    } else if (!hidden && !rendered) { children.replaceChildren(...currentBranch(item.node_key).children.map(node => _buildProductTreeItem(node, documentGid))); rendered = true; }
  });
  const treeState=modelDocument?.product_tree;
  const refreshGeneration=_modelRefreshGeneration, workspaceGid=_modelDocumentWorkspaceGid;
  const selector=JSON.stringify(modelDocument?.source_selector);
  const current=()=>refreshGeneration===_modelRefreshGeneration&&workspaceGid===_modelDocumentWorkspaceGid
    && _modelDocumentCollection.state.documents.some(doc=>doc.document_gid===modelDocument.document_gid&&doc.product_tree===treeState&&JSON.stringify(doc.source_selector)===selector);
  let renderedLazyGeneration;
  const renderLazy=()=>{
    const page=treeState.pages[pageKey(item)];
    wrapper.dataset.lazyUnloaded=page?'false':'true';
    const forest=window.AI00ModelDocumentCollection.buildProductForest(treeState.nodes);
    const find=nodes=>{for(const node of nodes){if(node.node_key===item.node_key)return node;const found=find(node.children);if(found)return found;}};
    item.children=find(forest)?.children||[];
    const existing=new Map(renderedLazyGeneration===page?.generation?Array.from(children.children).filter(row=>row.dataset.cacheViewKey).map(row=>[row.dataset.cacheViewKey,row]):[]);
    renderedLazyGeneration=page?.generation;
    children.replaceChildren(...item.children.map(node=>existing.get('product:'+documentGid+':'+node.node_key)||_buildProductTreeItem(node,documentGid)));
    if(page?.state==='loading'){const status=document.createElement('div');status.textContent='读取中…';children.append(status);}
    if(page?.error || page?.next_cursor!=null){
      const action=document.createElement('button');action.type='button';
      action.textContent=page.restart_required?'分页缓存已更新，从首页重试':page.error?`重试：${page.error}`:'加载更多';
      if(page.error)action.dataset.tcRetry='true';else action.dataset.tcMore='true';
      action.disabled=page.state==='loading';
      action.addEventListener('click',event=>{event.stopPropagation();void loadLazy(!page.restart_required&&page.next_cursor!=null);});children.append(action);
    }
    if(page?.captured_at){const info=document.createElement('div');info.className='cs-model-document-empty';info.textContent=`${page.cache_hit?'Connector 缓存':'已读取'} · ${page.captured_at}`;children.append(info);}
    syncVisibility();
  };
  if(lazy)wrapper._refreshLazy=renderLazy;
  const loadLazy=async(more=false)=>{
    const pending=cachedSnapshot
      ? window.AI00CacheSnapshotSource.readChildren(_invokeCapability,treeState,item.cache_node_key,{more,isCurrent:current})
      : window.AI00TeamcenterOnlineSource.readChildren(_requestVisMockupCommand,modelDocument,treeState,item.occurrence_path,{more,isCurrent:current});
    renderLazy();
    try{await pending;}catch(error){
      if(!cachedSnapshot&&error.message==='teamcenter_parent_path_not_found'&&current()){
        const detail={document_gid:documentGid,node_name:item.name,source_node_id:item.node_key};
        _simulationDebug('tc_path_choice_required',{...detail,level:'warn',error_code:error.message});
        const refresh=await window.AI00Dialogs?.confirm({title:'缓存路径与当前配置不一致',tone:'warning',
          message:`“${item.name||item.node_key}”无法按当前 Teamcenter 配置继续读取。可能是版本或装配结构已变化，并不代表缓存的旧树无效。\n\n保留缓存：继续查看已缓存的旧结构，本次不补读缺失的子节点。\n刷新分支：按当前配置重新读取最近有效的上层分支，并保留原缓存作为对比基线。`,
          cancelText:'保留缓存',confirmText:'保留基线并刷新'});
        if(!current())return;
        _simulationDebug('tc_path_choice',{...detail,action:refresh?'refresh':'keep_cache'});
        if(refresh){
          try{
            if(!modelDocument.product_tree_baseline)modelDocument.product_tree_baseline=JSON.parse(JSON.stringify({captured_at:new Date().toISOString(),source_selector:modelDocument.source_selector,product_tree:treeState}));
            await _persistModelProjectionCache({required:true});
            if(!current())return;
            _simulationDebug('tc_path_baseline_saved',{...detail,node_count:modelDocument.product_tree_baseline.product_tree.node_count});
            const refreshed=await window.AI00TeamcenterOnlineSource.refreshAncestor(_requestVisMockupCommand,modelDocument,treeState,item.occurrence_path,current);
            if(!refreshed||!current())return;
            window._invalidateModelControlMappings?.();
            _renderModelDocuments(_modelDocumentCollection.state.documents);
            window.AI00TreeProjectionCache.bindView($('modelDocumentList'),_eAPI()?.simulationTreeCache,{workspaceGid,kind:'models'});
            _simulationDebug('tc_path_refreshed',{...detail,node_count:treeState.node_count});
            _cmdShow('分支已刷新，原缓存对比基线已保留');
          }catch(refreshError){_simulationDebug('tc_path_refresh_failed',{...detail,error_code:refreshError.message});_cmdShow('刷新未完成：'+refreshError.message,'err');}
        }
      }
    }
    if(!current())return;
    const visibleWrapper=Array.from($('modelDocumentList')?.querySelectorAll('[data-cache-view-key]')||[]).find(row=>row.dataset.cacheViewKey===wrapper.dataset.cacheViewKey);
    visibleWrapper?._refreshLazy();
    const count=visibleWrapper?.closest('.cs-model-document-row')?.querySelector('.cs-model-document-count');
    if(count)count.textContent=`已加载 ${treeState.node_count} 项 · 按需读取`;
    await _persistModelProjectionCache();
  };
  const check = document.createElement('input'); check.type = 'checkbox'; check.className = 'cs-alternate-tree-check';
  const controllable=Boolean(window._actOnModelNode&&(cachedSnapshot?window.AI00CacheSnapshotViewer:(modelDocument?.product_tree?.document_session
    ||modelDocument?.source_kind==='teamcenter_online')));
  const currentBranch=key=>{
    const stack=window.AI00ModelDocumentCollection.buildProductForest(modelDocument?.product_tree?.nodes||[]);
    while(stack.length){const node=stack.pop();if(String(node.node_key)===String(key))return node;stack.push(...node.children);}
    return item;
  };
  const visibilityState=(branch=currentBranch(item.node_key))=>{
    if(cachedSnapshot&&(_cacheSnapshotExclusion(modelDocument,item)||window.AI00ViewerInteraction?.cacheIncompleteAncestors(modelDocument._cacheViewer).has(item.cache_node_key)))return {checked:false,indeterminate:false,unknown:true};
    if(['visible','hidden','mixed','unknown'].includes(branch.visibility_state))return {checked:branch.visibility_state==='visible',indeterminate:branch.visibility_state==='mixed',unknown:branch.visibility_state==='unknown'};
    // Lazy refreshes replace child objects; stored nodes are the shared source
    // for every row, including retained ancestors and collapsed branches.
    const leaves=[]; const stack=[branch];
    while(stack.length){
      const node=stack.pop();
      if(node.children.length){
        stack.push(...node.children);
        const page=lazy?treeState.pages[pageKey(node)]:null;
        // Unloaded siblings cannot be inferred from the visible page. A prior
        // confirmed branch operation can supply their state; otherwise unknown.
        if(lazy&&(!page||page.state!=='loaded'||page.next_cursor!=null))leaves.push(node);
      }else leaves.push(node);
    }
    const shown=leaves.filter(node=>node.visible===true).length;
    const unknown=leaves.some(node=>typeof node.visible!=='boolean');
    return {checked:!unknown&&shown===leaves.length,indeterminate:!unknown&&shown>0&&shown<leaves.length,unknown};
  };
  wrapper._syncModelVisibility=branches=>{
    if(cachedSnapshot){const reason=_cacheSnapshotExclusion(modelDocument,item),incomplete=window.AI00ViewerInteraction?.cacheIncompleteAncestors(modelDocument._cacheViewer).has(item.cache_node_key);check.disabled=!controllable||Boolean(reason);check.title=reason?`未加载 · ${_cacheSnapshotReason(reason)}`:incomplete?'部分节点未加载，显隐仅作用于已加载部分':modelDocument._cacheViewer?'显示 / 隐藏（缓存实例）':'打开缓存模型并读取实际显隐；本次不会直接改变显隐';}
    const state=visibilityState(branches?.get(String(item.node_key)));check.checked=state.checked;check.indeterminate=state.indeterminate;
    check.dataset.visibility=state.unknown?'unknown':state.indeterminate?'mixed':state.checked?'visible':'hidden';
    check.setAttribute('aria-label',state.unknown?'显隐状态未确认':state.indeterminate?'部分显示':state.checked?'已显示':'已隐藏');
  };
  const syncVisibility=()=>{
    const branches=new Map(),stack=window.AI00ModelDocumentCollection.buildProductForest(modelDocument.product_tree.nodes);
    while(stack.length){const node=stack.pop();branches.set(String(node.node_key),node);stack.push(...node.children);}
    for(const row of line.closest('.cs-model-document-tree')?.querySelectorAll('.cs-alternate-tree-item')||[wrapper])row._syncModelVisibility?.(branches);
  };
  const applyVisibility=(target,visible)=>{
    const affected=new Set(),stack=[currentBranch(target.node_key)];
    while(stack.length){const node=stack.pop();affected.add(String(node.node_key));stack.push(...node.children);}
    for(const stored of modelDocument.product_tree.nodes)if(affected.has(String(stored.node_key))){stored.visible=visible;delete stored.visibility_state;}
    const byKey=new Map(modelDocument.product_tree.nodes.map(stored=>[String(stored.node_key),stored]));
    for(const key of affected){const seen=new Set();let parent=byKey.get(key)?.parent_key;while(parent!=null&&!seen.has(String(parent))){seen.add(String(parent));const ancestor=byKey.get(String(parent));if(!ancestor)break;if(!affected.has(String(parent))){ancestor.visible=null;delete ancestor.visibility_state;}parent=ancestor.parent_key;}}
    syncVisibility();
  };
  check.disabled=!controllable; wrapper._syncModelVisibility(new Map([[String(item.node_key),item]]));
  check.title=controllable?(window._localViewerInteraction?.()?'显示 / 隐藏（本地交互会话）':'显示 / 隐藏（操作前核对文档绑定）'):'尚无运行节点身份，请先关联当前 VisMockup 文档';
  if(cachedSnapshot)wrapper._syncModelVisibility();
  const icon = document.createElement('span'); icon.className = 'cs-alternate-tree-icon cs-alternate-tree-icon-model'; icon.textContent = item.children.length ? '◇' : '▣';
  const name = document.createElement('span'); name.className = 'cs-alternate-tree-name'; name.textContent = item.name || item.node_key;
  name.title = [name.textContent, item.bom_line, item.item_id, item.revision].filter(Boolean).join(' · ');
  if(controllable) {
    line.dataset.modelRuntimeControl='true';
    let pending=false;
    const run=async action=>{
      if(cachedSnapshot&&_cacheSnapshotExclusion(modelDocument,item))return;
      const tree=line.closest('.cs-model-document-tree');
      if(pending||tree?.dataset.runtimeBusy==='true')return;
      const workspace=window._simulationEnvironmentWorkspace?.store?.state?.workspace;
      if(!workspace?.workspace_gid)return;
      const controls=[...tree?.querySelectorAll('.cs-alternate-tree-check')||[]].map(control=>[control,control.disabled]);
      if(tree)tree.dataset.runtimeBusy='true';for(const [control]of controls)control.disabled=true;
      pending=true;check.disabled=true;line.setAttribute('aria-busy','true');_cmdShow('');
      const trace_id=window.crypto?.randomUUID?.(),started=performance.now();
      _simulationDebug('ui_action_started',{trace_id,document_gid:documentGid,source_node_id:item.node_key,node_name:item.name,action});
      let activeTarget;
      try {
        const localInteraction=window._localViewerInteraction?.();
        const resolvedOccurrenceRoot=modelDocument?.source_kind==='teamcenter_online'
          &&item?.parent_key==null&&!_isRawTeamcenterControlKey(item?.control_key)
          &&item.children.some(node=>_isRawTeamcenterControlKey(node.control_key));
        const currentNode=cachedSnapshot||localInteraction||resolvedOccurrenceRoot
          ?item:await _ensureTeamcenterControlNode(modelDocument,item,()=>line.isConnected,true);
        // A Teamcenter source root is synthetic and has no occurrence UID.  Do
        // not send its cache key to VisMockup: fan the action out through the
        // distinct direct-child occurrences instead.  Their control_key values
        // preserve duplicate instances under the same parent.
        const refreshedForest=window.AI00ModelDocumentCollection.buildProductForest(modelDocument.product_tree.nodes);
        const findNode=nodes=>{for(const node of nodes){if(String(node.node_key)===String(currentNode.node_key))return node;const found=findNode(node.children);if(found)return found;}};
        const renderedNode=findNode(refreshedForest)||currentNode;
        const singlePartRoot=modelDocument?.role==='primary'&&currentNode.parent_key==null
          &&Array.isArray(currentNode.occurrence_path)&&currentNode.occurrence_path.length===0
          &&currentNode.has_children===false&&modelDocument.product_tree.nodes.length===1;
        const targets=typeof localInteraction?.executeIntent!=='function'&&modelDocument?.source_kind==='teamcenter_online'&&!_isRawTeamcenterControlKey(currentNode.control_key)&&!singlePartRoot
          ? renderedNode.children.filter(node=>_isRawTeamcenterControlKey(node.control_key)) : [currentNode];
        if(!targets.length)throw Error('model_node_runtime_identity_unavailable');
        for(const target of targets){
          const actionableTarget=cachedSnapshot||localInteraction||_isRawTeamcenterControlKey(target.control_key)
            ?target:await _ensureTeamcenterControlNode(modelDocument,target,()=>line.isConnected,true);
          activeTarget=actionableTarget;
          const result=await window._actOnModelNode({workspaceGid:workspace.workspace_gid,document:modelDocument,nodeKey:actionableTarget.node_key,action,isCurrent:()=>line.isConnected});
          if(!line.isConnected)return;
          if(result.calibrated)_cmdShow(result.calibration_unknown?'已读取 VisMockup 实际显隐，部分节点仍未确认；请核对 ? 状态后操作':'已按 VisMockup 实际显隐校准，请按当前勾选状态操作',result.calibration_unknown?'warn':'ok');
          if(typeof result.visible==='boolean')applyVisibility(actionableTarget,result.visible);
          if(typeof result.selected==='boolean')line.classList.toggle('cs-vis-active',result.selected);
          _simulationDebug('ui_state_applied',{trace_id,document_gid:documentGid,source_node_id:actionableTarget.node_key,node_name:actionableTarget.name,action,observed:result.visible??result.selected,elapsed_ms:performance.now()-started});
          activeTarget=null;
        }
        if(!line.isConnected)return;
      } catch(error) {
        const reason=error?.message||'model_node_control_failed';
        _simulationDebug('ui_action_failed',{trace_id,document_gid:documentGid,source_node_id:activeTarget?.node_key||item.node_key,action,error_code:reason,elapsed_ms:performance.now()-started});
        if(activeTarget&&line.isConnected&&['show','hide'].includes(action)&&/outcome_unknown|transport_unknown/.test(reason))applyVisibility(activeTarget,null);
        const hint=reason==='vismockup_document_limit_exceeded'?'已达到 10 个文档上限，请在“文档 N/10”中关闭非活动文档后再打开。':reason==='model_node_relocation_required'
          ? '文档已连接；这份旧缓存未保存实例定位标识，需要右键“刷新结构”补采一次。以后按实例路径定位，无需每次重读；本次未执行节点操作'
          : /vismockup_cad_locator_missing/.test(reason) ? '本地实例定位缓存缺失，请右键“刷新结构”补采；未执行节点操作'
          : /vismockup_cad_instance_(unmapped|ambiguous|changed)/.test(reason) ? '当前文档中的实例已变化或无法唯一定位；未按同名零件猜测，请刷新结构后重试'
          : reason==='model_node_runtime_identity_unavailable'||reason==='vismockup_online_occurrence_locator_invalid'
            ? '未取得该节点的 Teamcenter 实例定位标识；已尝试刷新结构，本次未执行节点操作'
          : reason==='document_session_changed'?'VisMockup 文档会话已变化，请核对当前文档；未执行节点操作':reason;
        check.title=hint;_cmdShow(hint,'err');
      } finally {pending=false;check.disabled=false;if(tree)delete tree.dataset.runtimeBusy;for(const [control,disabled]of controls)control.disabled=disabled;line.removeAttribute('aria-busy');syncVisibility();}
    };
    check.addEventListener('click',event=>{event.preventDefault();event.stopPropagation();const shown=cachedSnapshot?modelDocument._cacheViewer?.native_visibility?.[item.cache_node_key]?.visible:undefined;void run((typeof shown==='boolean'?shown:visibilityState().checked)?'hide':'show');});
    name.addEventListener('click',event=>{event.stopPropagation();void run('highlight');});
    line.addEventListener('contextmenu',event=>_showAlternateContextMenu(event,[
      {label:'显示',run:()=>run('show')},{label:'隐藏',run:()=>run('hide')},
      {label:'高亮',run:()=>run('highlight')},{label:'取消高亮',run:()=>run('unhighlight')},
    ]));
  }
  if(lazy) name.addEventListener('click',event=>{
    event.stopPropagation();
    void _selectTeamcenterNodeDetail(modelDocument,item);
  });
  line.draggable = !cachedSnapshot;
  line.addEventListener('dragstart', event => {
    if(cachedSnapshot){event.preventDefault();return;}
    event.stopPropagation();
    event.dataTransfer?.setData('application/x-ai00-model-node', JSON.stringify({ document_gid: documentGid, node_key: item.node_key }));
    if (event.dataTransfer) event.dataTransfer.effectAllowed = 'copy';
  });
  line.append(toggle, check, icon, name); wrapper.append(line, children); return wrapper;
}

function _closeAlternateContextMenu() {
  _alternateContextMenu?.remove();
  _alternateContextMenu = null;
}

function _showAlternateContextMenu(event, actions) {
  event.preventDefault();
  event.stopPropagation();
  _closeAlternateContextMenu();
  const host=event.target.closest?.('#modelDocumentList, #alternateHierarchyList');
  const meta=host?._cacheMeta;
  const documentRow=event.target.closest?.('.cs-model-document-summary')?.closest('.cs-model-document-row');
  const onlineDocument=documentRow&&_modelDocumentCollection?.state.documents.find(item=>String(item.document_gid)===documentRow.dataset.documentGid&&item.source_kind==='teamcenter_online');
  if(onlineDocument) actions=[...actions,...['new','insert'].map(mode=>({
    label:mode==='new'&&String(_pendingTeamcenterOnlineBinding?.documentGid)===String(onlineDocument.document_gid)
      ?'重试绑定并内嵌':mode==='new'?'新文档打开':'插入当前文档',onlineMode:mode,
    disabled:Boolean(documentRow._onlineOpening)||(mode==='insert'&&!_vmDocumentReady),
    run:async()=>{
      if(documentRow._onlineOpening)return;
      if(mode==='insert'&&!_vmDocumentReady){_cmdShow('当前 VisMockup 没有可插入的活动文档','err');return;}
      documentRow._onlineOpening=true;
      try{
        const opened=await _openTeamcenterOnlineDocument(onlineDocument,mode);
        if(!opened)return;
        _cmdShow(mode==='new'?'已在新的 VisMockup 文档中打开':'已插入当前 VisMockup 文档','ok');
        if(mode==='insert')setTimeout(()=>_tryAutoConnect(),1500);
      }catch(error){_cmdShow(error?.message||'在线模型打开失败','err');}
      finally{documentRow._onlineOpening=false;}
    },
  }))];
  if(meta?.workspaceGid) actions=[...actions,{label:'刷新结构',run:async()=>{
    const workspace=window._simulationEnvironmentWorkspace?.store?.state?.workspace;
    if(String(workspace?.workspace_gid)!==String(meta.workspaceGid)) return;
    try { if(meta.kind==='models') await _refreshModelDocuments(workspace,{allowRebind:true,refreshChildren:true}); else await _refreshAlternateHierarchies(workspace); }
    catch(error) { _cmdShow(error?.message||'结构刷新失败','err'); }
  }}];
  const menu = document.createElement('div');
  menu.className = 'cs-environment-context-menu cs-alternate-context-menu';
  menu.setAttribute('role', 'menu');
  for (const action of actions) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `cs-environment-context-action${action.danger ? ' danger' : ''}`;
    button.setAttribute('role', 'menuitem');
    button.textContent = action.label;
    button.disabled = Boolean(action.disabled);
    if(action.onlineMode)button.dataset.onlineMode=action.onlineMode;
    button.addEventListener('click', () => { _closeAlternateContextMenu(); action.run(); });
    menu.appendChild(button);
  }
  document.body.appendChild(menu);
  menu.style.left = `${Math.max(4, Math.min(event.clientX, window.innerWidth - menu.offsetWidth - 8))}px`;
  menu.style.top = `${Math.max(4, Math.min(event.clientY, window.innerHeight - menu.offsetHeight - 8))}px`;
  _alternateContextMenu = menu;
  menu.querySelector('button')?.focus();
}

function _renderAlternateHierarchies(items = []) {
  const host = $('alternateHierarchyList');
  if (!host) return;
  _closeAlternateContextMenu();
  _alternateVisibilityChecks.clear();
  if (!items.length) { host.innerHTML = '<span class="cs-model-document-empty">暂无备选层次结构，可新建或从 BOP Fork 生成</span>'; return; }
  host.replaceChildren(...items.map(item => {
    const row = document.createElement('div');
    row.className = 'cs-alternate-hierarchy-row'; row.tabIndex = 0;
    row.dataset.cacheViewKey = 'ah:'+item.hierarchy_gid;
    row.title = '右键编辑或删除';
    if (item.hierarchy_gid === _modelDocumentCollection.state.selectedHierarchyGid) row.classList.add('active');
    row.innerHTML = '<div class="cs-alternate-hierarchy-summary"><span class="cs-alternate-tree-toggle">▸</span><input class="cs-alternate-tree-check" type="checkbox" disabled aria-label="层次结构显隐"><span class="cs-alternate-tree-icon cs-alternate-tree-icon-hierarchy">▦</span><span class="cs-alternate-hierarchy-name"></span><span class="cs-alternate-hierarchy-count"></span></div><div class="cs-alternate-hierarchy-tree hidden"></div>';
    const name = row.querySelector('.cs-alternate-hierarchy-name');
    name.textContent = item.name || item.hierarchy_gid;
    name.title = name.textContent;
    const count = item.nodes || item.placements ? (item.nodes?.length || 0) + (item.placements?.length || 0) : item.placement_count;
    row.querySelector('.cs-alternate-hierarchy-count').textContent = count == null ? '… 项' : `${count} 项`;
    const select = async () => {
      const workspaceGid = _alternateHierarchyWorkspaceGid;
      const generation = _alternateRefreshGeneration;
      _modelDocumentCollection.selectHierarchy(item.hierarchy_gid);
      const detail = await _invokeCapability('simulation.environment.alternate_hierarchy.get', { hierarchy_gid: item.hierarchy_gid });
      if(workspaceGid!==_alternateHierarchyWorkspaceGid || generation!==_alternateRefreshGeneration) return;
      const next = _modelDocumentCollection.state.hierarchies.map(value => value.hierarchy_gid === item.hierarchy_gid ? { ...value, ...detail } : value);
      _modelDocumentCollection.replaceHierarchies(next); _modelDocumentCollection.selectHierarchy(item.hierarchy_gid);
      _renderAlternateHierarchies(_modelDocumentCollection.state.hierarchies);
      _setTreeCacheStatus(host,{...host._cacheMeta,workspaceGid,kind:'alternate'});
      if(!_alternateProjectionCached) void _eAPI()?.simulationTreeCache?.put(workspaceGid,'alternate',{
        items:_modelDocumentCollection.state.hierarchies,selected_gid:item.hierarchy_gid,
      }).catch(()=>{});
    };
    row.querySelector('.cs-alternate-hierarchy-summary').addEventListener('click', event => {
      if (event.target.closest('input')) return;
      if (!item.nodes) select().catch(error => _cmdShow(error?.message || '层次加载失败', 'err'));
      else {
        const tree = row.querySelector('.cs-alternate-hierarchy-tree');
        const open = tree.classList.toggle('hidden');
        row.querySelector('.cs-alternate-tree-toggle').textContent = open ? '▸' : '▾';
        _modelDocumentCollection.selectHierarchy(item.hierarchy_gid);
        row.classList.add('active');
      }
    });
    row.addEventListener('contextmenu', event => _showAlternateContextMenu(event, [
      { label: '编辑名称', run: () => _renameAlternateHierarchy(item).catch(error => _cmdShow(error?.message || '重命名失败', 'err')) },
      { label: '删除（归档）', danger: true, run: () => _archiveAlternateHierarchy(item).catch(error => _cmdShow(error?.message || '归档失败', 'err')) },
    ]));
    const tree = row.querySelector('.cs-alternate-hierarchy-tree');
    if (item.nodes) {
      const forest = globalThis.AI00ModelDocumentCollection.buildHierarchyForest(item);
      _wireAlternateVisibilityCheck(row.querySelector('.cs-alternate-hierarchy-summary input'), { children: forest });
      tree.replaceChildren(...forest.map(value => _buildAlternateTreeItem(value, item)));
      tree.classList.toggle('hidden', item.hierarchy_gid !== _modelDocumentCollection.state.selectedHierarchyGid);
      row.querySelector('.cs-alternate-tree-toggle').textContent = tree.classList.contains('hidden') ? '▸' : '▾';
    }
    return row;
  }));
}

function _alternateRuntimeCandidates(item) {
  return [item.source_ref?.node_key, item.source_ref?.occurrence_key,
    item.source_ref?.stable_identity, item.source_ref?.projection_identity,
    item.source_ref?.occurrence_id];
}

function _alternateRuntimeKeys(item) {
  const own = item.kind === 'placement'
    ? _alternateRuntimeCandidates(item).find(key => key && _visNodeMap[key])
    : null;
  return [...new Set([...(own ? [own] : []), ...(item.children || []).flatMap(_alternateRuntimeKeys)])];
}

function _alternateVisibilityState(item) {
  const keys = _alternateRuntimeKeys(item);
  const placements = [];
  const visit = value => {
    if (value.kind === 'placement') placements.push(value);
    (value.children || []).forEach(visit);
  };
  visit(item);
  const unmapped = placements.some(value => !_alternateRuntimeCandidates(value).some(key => key && _visNodeMap[key]));
  const leaves = keys.map(key => ({ key, visible: _visNodeMap[key].node.visible, children: [] }));
  if (unmapped) leaves.push({ key: 'unmapped', visible: null, children: [] });
  return { keys, state: globalThis.AI00ModelDocumentCollection.deriveVisibilityState({ children: leaves }) };
}

function _updateAlternateVisibilityControls(controls = _alternateVisibilityChecks) {
  for (const { check, item } of controls) {
    const { state } = _alternateVisibilityState(item);
    check.checked = state.checked;
    check.indeterminate = state.indeterminate;
    check.disabled = _alternateProjectionCached || !_vmConnected || state.disabled || _alternateVisibilityBatchPending;
    check.title = state.disabled ? '显隐状态未知，请从 VisMockup 重新读取结构' : '切换显示/隐藏';
  }
}

function _wireAlternateVisibilityCheck(check, item) {
  _alternateVisibilityChecks.add({ check, item });
  _updateAlternateVisibilityControls([{ check, item }]);
  check.addEventListener('click', async event => {
    event.stopPropagation();
    event.preventDefault();
    const { keys, state } = _alternateVisibilityState(item);
    if (_alternateProjectionCached || state.disabled || !_vmConnected || !keys.length || _alternateVisibilityBatchPending) return;
    const action = state.checked ? 'hide' : 'show';
    _alternateVisibilityBatchPending = true;
    _updateAlternateVisibilityControls();
    try {
      let failed = false;
      for (const key of keys) {
        const result = await _visNodeAction(key, action);
        if (!result?.ok) { failed = true; break; }
      }
      if (failed) {
        let refreshed = false;
        try { refreshed = await _loadVisTree(true); }
        catch (error) { _cmdShow(error?.message || '显隐状态回读失败', 'err'); }
        if (!refreshed) keys.forEach(key => { if (_visNodeMap[key]) _visNodeMap[key].node.visible = null; });
      }
    } finally {
      _alternateVisibilityBatchPending = false;
      _updateAlternateVisibilityControls();
    }
  });
}

function _buildAlternateTreeItem(item, hierarchy) {
  const wrapper = document.createElement('div');
  wrapper.className = `cs-alternate-tree-item cs-alternate-tree-${item.kind}`;
  wrapper.dataset.cacheViewKey = 'ahnode:'+hierarchy.hierarchy_gid+':'+(item.node_gid||item.placement_gid);
  const line = document.createElement('div');
  line.className = 'cs-alternate-tree-line';
  if (item.kind === 'node') line.setAttribute('data-node-gid', item.node_gid);
  const children = document.createElement('div');
  children.className = 'cs-alternate-tree-children hidden';
  let childrenBuilt = false;
  const hasChildren = Boolean(item.children?.length);
  const toggle = document.createElement('button');
  toggle.type = 'button'; toggle.className = 'cs-alternate-tree-toggle'; toggle.textContent = hasChildren ? '▸' : '';
  toggle.disabled = !hasChildren;
  toggle.addEventListener('click', event => {
    event.stopPropagation();
    if (!childrenBuilt) {
      children.replaceChildren(...(item.children || []).map(value => _buildAlternateTreeItem(value, hierarchy)));
      childrenBuilt = true;
    }
    const hidden = children.classList.toggle('hidden');
    toggle.textContent = hidden ? '▸' : '▾';
  });
  const check = document.createElement('input');
  check.type = 'checkbox'; check.className = 'cs-alternate-tree-check';
  _wireAlternateVisibilityCheck(check, item);
  const icon = document.createElement('span');
  const isResource = item.kind === 'placement' && item.source_kind === 'resource';
  icon.className = `cs-alternate-tree-icon ${item.kind === 'node' ? 'cs-alternate-tree-icon-node' : isResource ? 'cs-alternate-tree-icon-resource' : 'cs-alternate-tree-icon-model'}`;
  icon.textContent = item.kind === 'node' ? '◇' : isResource ? '◆' : '▣';
  const name = document.createElement('span'); name.className = 'cs-alternate-tree-name';
  name.textContent = item.name || item.display_name || item.node_gid || item.placement_gid;
  name.title = name.textContent;
  line.append(toggle, check, icon, name);
  if (item.kind === 'node') {
    name.addEventListener('click', () => {
      _alternateCaptureSelection = { workspace_gid: hierarchy.workspace_gid, hierarchy_gid: hierarchy.hierarchy_gid, node_gid: item.node_gid };
      for (const selected of document.querySelectorAll('.cs-alternate-tree-line.active')) selected.classList.remove('active');
      line.classList.add('active');
    });
    line.addEventListener('contextmenu', event => _showAlternateContextMenu(event, [
      { label: '所属线体逆序工序截图', run: () => {
        _alternateCaptureSelection = { workspace_gid: hierarchy.workspace_gid, hierarchy_gid: hierarchy.hierarchy_gid, node_gid: item.node_gid };
        return _openGovernedCapture();
      } },
    ]));
  }
  if (item.kind === 'placement') {
    line.title = '右键删除放置';
    line.addEventListener('contextmenu', event => _showAlternateContextMenu(event, [
      { label: '删除放置', danger: true, run: () => _removePlacement(hierarchy, item).catch(error => _cmdShow(error?.message || '移除失败', 'err')) },
    ]));
  }
  wrapper.append(line, children);
  return wrapper;
}

async function _renameAlternateHierarchy(hierarchy) {
  const name = (await window.AI00Dialogs.prompt('备选层次结构名称', hierarchy.name || ''));
  if (!name?.trim() || name.trim() === hierarchy.name) return;
  await _invokeCapability('simulation.environment.alternate_hierarchy.update', {
    hierarchy_gid: hierarchy.hierarchy_gid, name: name.trim(), expected_row_version: hierarchy.row_version,
    idempotency_key: `hierarchy-rename-${hierarchy.hierarchy_gid}-${Date.now()}`,
  }, { idempotency: true });
  await _refreshAlternateHierarchies();
}

async function _archiveAlternateHierarchy(hierarchy) {
  if (!(await window.AI00Dialogs.confirm(`归档“${hierarchy.name || hierarchy.hierarchy_gid}”？`))) return;
  await _invokeCapability('simulation.environment.alternate_hierarchy.archive', {
    hierarchy_gid: hierarchy.hierarchy_gid, expected_row_version: hierarchy.row_version,
    idempotency_key: `hierarchy-archive-${hierarchy.hierarchy_gid}-${Date.now()}`,
  }, { confirmation: true, idempotency: true });
  await _refreshAlternateHierarchies();
}

async function _removePlacement(hierarchy, placement) {
  if (!(await window.AI00Dialogs.confirm(`从层次结构移除“${placement.display_name || placement.placement_gid}”？`))) return;
  await _invokeCapability('simulation.environment.placement.remove', {
    placement_gid: placement.placement_gid, expected_row_version: hierarchy.row_version,
    idempotency_key: `placement-remove-${placement.placement_gid}-${Date.now()}`,
  }, { confirmation: true, idempotency: true });
  await _refreshAlternateHierarchies();
}

let _alternateRefreshGeneration = 0;
async function _refreshAlternateHierarchies(workspace = window._simulationEnvironmentWorkspace?.store?.state?.workspace, preferredHierarchyGid = null, {useCache=false} = {}) {
  const generation = ++_alternateRefreshGeneration;
  const workspaceGid = workspace?.workspace_gid;
  if (!workspaceGid) { _alternateHierarchyWorkspaceGid = null; _modelDocumentCollection?.replaceHierarchies([]); _renderAlternateHierarchies([]); return; }
  if (_alternateHierarchyWorkspaceGid !== workspaceGid) {
    _modelDocumentCollection?.replaceHierarchies([]);
    _renderAlternateHierarchies([]);
  }
  _alternateHierarchyWorkspaceGid = workspaceGid;
  await _projectionCache().run({workspaceGid,kind:'alternate',useCache,isCurrent:()=>generation === _alternateRefreshGeneration,
    render(data,meta) {
      _alternateProjectionCached = Boolean(meta.cached_at);
      _modelDocumentCollection.replaceHierarchies(data.items);
      const selected = preferredHierarchyGid || data.selected_gid;
      if (selected && data.items.some(item=>item.hierarchy_gid===selected)) _modelDocumentCollection.selectHierarchy(selected);
      _renderAlternateHierarchies(_modelDocumentCollection.state.hierarchies);
      _setTreeCacheStatus($('alternateHierarchyList'),meta);
    },
    async load(previous) {
      const result = await _invokeCapability('simulation.environment.alternate_hierarchy.search', {workspace_gid:workspaceGid});
      const prior = new Map((previous?.items || []).map(item=>[item.hierarchy_gid,item]));
      const items = (result?.items || []).map(item=>prior.get(item.hierarchy_gid)?.row_version === item.row_version
        ? {...prior.get(item.hierarchy_gid),...item} : item);
      const selected = preferredHierarchyGid || previous?.selected_gid || _modelDocumentCollection.state.selectedHierarchyGid;
      if (selected && items.some(item=>item.hierarchy_gid===selected)) {
        const detail = await _invokeCapability('simulation.environment.alternate_hierarchy.get',{hierarchy_gid:selected});
        const index=items.findIndex(item=>item.hierarchy_gid===selected); items[index]={...items[index],...detail};
      }
      return {items,selected_gid:selected};
    },
  });
}

async function _addAlternateHierarchy() {
  const controller = window._simulationEnvironmentWorkspace;
  const workspace = controller?.store?.state?.workspace;
  if (!workspace?.workspace_gid) throw new Error('请先选择仿真环境');
  const name = `ALT Hier #${_modelDocumentCollection.state.hierarchies.length + 1}`;
  await _invokeCapability('simulation.environment.alternate_hierarchy.create', {
    workspace_gid: workspace.workspace_gid, name, expected_row_version: workspace.row_version,
    idempotency_key: `alternate-hierarchy-${workspace.workspace_gid}-${Date.now()}`,
  }, { idempotency: true });
  await controller.store.openWorkspace(workspace.workspace_gid);
  await _refreshAlternateHierarchies(controller.store.state.workspace);
  _cmdShow(`${name} 已创建`, 'ok');
}

async function _placeModelDocument(documentGid, targetNodeGid) {
  const hierarchy = _modelDocumentCollection.state.hierarchies.find(item => item.hierarchy_gid === _modelDocumentCollection.state.selectedHierarchyGid);
  const documentRow = _modelDocumentCollection.state.documents.find(item => item.document_gid === documentGid);
  if(documentRow?.source_kind==='teamcenter_cache_snapshot')throw Error('缓存批次的模型文件和装配位置尚未就绪，暂不能编排');
  if (!hierarchy) throw new Error('请先选择备选层次结构');
  if (!documentRow) throw new Error('model_document_not_found');
  const result = await _invokeCapability('simulation.environment.placement.create', {
    hierarchy_gid: hierarchy.hierarchy_gid, target_node_gid: targetNodeGid, parent_placement_gid: null,
    source_kind: documentRow.media_type.includes('jt') ? 'jt' : 'plmxml',
    source_ref: { document_gid: documentRow.document_gid, content_sha256: documentRow.content_sha256 },
    transform: [1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1], display_name: documentRow.display_name || '',
    expected_row_version: hierarchy.row_version,
    idempotency_key: `placement-${hierarchy.hierarchy_gid}-${targetNodeGid}-${documentGid}-${Date.now()}`,
  }, { idempotency: true });
  _modelDocumentCollection.addPlacement(hierarchy.hierarchy_gid, { ...result, target_node_gid: targetNodeGid,
    source_ref: { document_gid: documentGid }, display_name: documentRow.display_name || '' });
  hierarchy.row_version = result.hierarchy_row_version;
  _renderAlternateHierarchies(_modelDocumentCollection.state.hierarchies);
  _cmdShow(`${documentRow.display_name || documentGid} 已编排到当前仿真树`, 'ok');
}

async function _placeModelNode(source, targetNodeGid) {
  const hierarchy = _modelDocumentCollection.state.hierarchies.find(item => item.hierarchy_gid === _modelDocumentCollection.state.selectedHierarchyGid);
  const documentRow = _modelDocumentCollection.state.documents.find(item => item.document_gid === source.document_gid);
  if(documentRow?.source_kind==='teamcenter_cache_snapshot')throw Error('缓存批次的模型文件和装配位置尚未就绪，暂不能编排');
  if (!hierarchy) throw new Error('请先选择备选层次结构');
  const modelNode = documentRow?.product_tree?.nodes?.find(item => item.node_key === source.node_key);
  if (!modelNode) throw new Error('model_node_not_found');
  const name = modelNode.name || modelNode.node_key;
  const result = await _invokeCapability('simulation.environment.placement.create', {
    hierarchy_gid: hierarchy.hierarchy_gid, target_node_gid: targetNodeGid, parent_placement_gid: null,
    source_kind: documentRow.media_type.includes('jt') ? 'jt' : 'plmxml',
    source_ref: { document_gid: source.document_gid, node_key: modelNode.node_key, occurrence_id: modelNode.occurrence_id || '' },
    transform: [1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1], display_name: name,
    expected_row_version: hierarchy.row_version,
    idempotency_key: `placement-${hierarchy.hierarchy_gid}-${targetNodeGid}-${source.document_gid}-${source.node_key}-${Date.now()}`,
  }, { idempotency: true });
  hierarchy.row_version = result.hierarchy_row_version;
  await _refreshAlternateHierarchies();
  _cmdShow(`${name} 已编排到当前仿真树`, 'ok');
}

async function _placeResource(resource, targetNodeGid) {
  const hierarchy = _modelDocumentCollection.state.hierarchies.find(item => item.hierarchy_gid === _modelDocumentCollection.state.selectedHierarchyGid);
  if (!hierarchy) throw new Error('请先选择备选层次结构');
  const result = await _invokeCapability('simulation.environment.placement.create', {
    hierarchy_gid: hierarchy.hierarchy_gid, target_node_gid: targetNodeGid, parent_placement_gid: null,
    source_kind: 'resource', source_ref: { resource_gid: String(resource.gid), resource_type: String(resource.resource_type) },
    transform: [1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1], display_name: resource.name || resource.code || '',
    expected_row_version: hierarchy.row_version,
    idempotency_key: `resource-placement-${hierarchy.hierarchy_gid}-${targetNodeGid}-${resource.gid}-${Date.now()}`,
  }, { idempotency: true });
  hierarchy.row_version = result.hierarchy_row_version;
  await _refreshAlternateHierarchies();
  _cmdShow(`${resource.name || resource.code || resource.gid} 已编排到当前仿真树`, 'ok');
}

function _renderSimulationResources(items = []) {
  const targets = {
    equipment: $('simulationResourceEquipment'), fixture: $('simulationResourceFixture'),
    tool: $('simulationResourceTools'), socket: $('simulationResourceTools'),
  };
  Object.values(targets).forEach((target, index, values) => {
    if (target && values.indexOf(target) === index) target.replaceChildren();
  });
  items.forEach(item => {
    const target = targets[item.resource_type]; if (!target) return;
    const row = document.createElement('div'); row.className = 'cs-resource-row'; row.draggable = true;
    row.textContent = item.name || item.code || item.gid;
    row.title = `${item.code || ''} · ${item.resource_type}`;
    row.addEventListener('dragstart', event => {
      event.dataTransfer?.setData('application/x-ai00-resource', JSON.stringify({ gid: item.gid, resource_type: item.resource_type, name: item.name, code: item.code }));
      if (event.dataTransfer) event.dataTransfer.effectAllowed = 'copy';
    });
    target.appendChild(row);
  });
  [...new Set(Object.values(targets))].forEach(target => {
    if (target && !target.children.length) target.innerHTML = '<span class="cs-resource-empty">暂无活动资源</span>';
  });
}

async function _refreshSimulationResources(workspace = window._simulationEnvironmentWorkspace?.store?.state?.workspace) {
  const workspaceGid = workspace?.workspace_gid;
  if (!workspaceGid) { _resourceWorkspaceGid = null; _renderSimulationResources([]); return; }
  const results = await Promise.all(['equipment','fixture','tool','socket'].map(resource_type =>
    _invokeCapability('craft.resource_requirement.search', { resource_type, status: 'active', page_size: 200 })));
  _resourceWorkspaceGid = workspaceGid;
  _renderSimulationResources(results.flatMap(result => result?.items || []));
}

async function _openFrozenSimulationEnvironment(record) {
  const workspaceGid = String(record?.workspace_gid || '');
  const versionGid = String(record?.version_gid || '');
  if (!workspaceGid || !versionGid) throw new Error('frozen_workspace_version_not_found');
  await _requireConnectorRuntime();
  const idempotencyKey = `runtime-package-${workspaceGid}-${versionGid}-${Date.now()}`;
  _modelDocumentCollection?.setEnvironmentState('materializing');
  _modelDocumentCollection?.setRuntimeProgress('staging', { workspaceGid, versionGid });
  _cmdShow('正在生成并暂存冻结仿真环境…');
  try {
    _modelDocumentCollection?.setRuntimeProgress('opening', { workspaceGid, versionGid });
    const outcome = await _requestVisMockupCommand(
      'simulation.environment.runtime_package.open.request',
      { workspace_gid: workspaceGid, version_gid: versionGid, idempotency_key: idempotencyKey },
      { confirmation: true, waitAttempts: 3750 },
    );
    _modelDocumentCollection?.setRuntimeProgress('reading_back', { workspaceGid, versionGid });
    const treeResult = outcome?.steps?.at(-1)?.result;
    if (!treeResult?.nodes) throw new Error('runtime_readback_missing');
    _renderVisTreeSnapshot(window.AI00VmSnapshotTree.snapshotToVisTree(treeResult), treeResult.cache_state || 'verified');
    _modelDocumentCollection?.setRuntimeProgress('read_back', { workspaceGid, versionGid });
    _onConnected();
    _cmdShow('冻结仿真环境已打开并完成 VM 回读；语义校验待完成', 'ok');
    return outcome;
  } catch (error) {
    const state = ['outcome_unknown', 'manual_review_required', 'expired'].includes(error?.message)
      ? 'outcome_unknown'
      : 'failed';
    _modelDocumentCollection?.setRuntimeProgress(state, { domainCode: error?.message || state });
    _modelDocumentCollection?.setEnvironmentState(state === 'outcome_unknown' ? 'outcome_unknown' : 'unmaterializable', { domainCode: error?.message || state });
    _cmdShow(`冻结环境重放失败：${error?.message || 'unknown_error'}`, 'err');
    throw error;
  }
}
window._openFrozenSimulationEnvironment = _openFrozenSimulationEnvironment;

let _modelRefreshGeneration = 0;
async function _refreshModelDocuments(workspace = window._simulationEnvironmentWorkspace?.store?.state?.workspace, {useCache=false,allowRebind=false,refreshDocumentGid=null,refreshChildren=false} = {}) {
  const generation = ++_modelRefreshGeneration;
  const workspaceGid = workspace?.workspace_gid;
  if (!workspaceGid) {
    _modelDocumentWorkspaceGid = null;
    _renderModelDocuments([]);
    return;
  }
  if (_modelDocumentWorkspaceGid !== workspaceGid) {
    _modelDocumentCollection?.replace([]);
    _renderModelDocuments([]);
  }
  _modelDocumentWorkspaceGid = workspaceGid;
  const currentTrees = new Map(_modelDocumentCollection.state.documents.map(item => [item.document_gid, item]));
  await _projectionCache().run({workspaceGid,kind:'models',useCache,previewCache:!refreshDocumentGid,preserveFreshItems:true,isCurrent:()=>generation === _modelRefreshGeneration,
  render(data,meta) {
    // A persisted preview must not displace newer trees or their pending page state.
    if(currentTrees.size&&(meta.pending||meta.cacheOnly))return;
    _modelDocumentCollection.replace(data.items);
    _renderModelDocuments(data.items);
    _setTreeCacheStatus($('modelDocumentList'),meta);
  },
  async load(previous) {
  const result = await _invokeCapability('simulation.environment.model_document.search', { workspace_gid: workspaceGid },{version:2});
  if (generation !== _modelRefreshGeneration) return {items:[]};
  const items = result?.items || [];
  const priorTrees = new Map([...(previous?.items||[]).map(item => [item.document_gid, item]), ...currentTrees]);
  items.forEach(item => {
    const prior = priorTrees.get(item.document_gid);
    if(prior?.product_tree_baseline)item.product_tree_baseline=prior.product_tree_baseline;
    if(refreshDocumentGid&&String(item.document_gid)!==refreshDocumentGid){
      if(prior?.source_kind===item.source_kind&&prior?.source_identity_hash===item.source_identity_hash
        &&prior?.content_sha256===item.content_sha256&&prior?.observation_id===item.observation_id
        &&JSON.stringify(prior?.source_selector)===JSON.stringify(item.source_selector))item.product_tree=prior?.product_tree;
      if(Object.values(item.product_tree?.pages||{}).some(page=>page.state==='loading')){
        item.product_tree=JSON.parse(JSON.stringify(item.product_tree));
        for(const page of Object.values(item.product_tree.pages))if(page.state==='loading'){page.state='failed';page.error='读取已中断，请重试';}
      }
      return;
    }
    if (item.source_kind === 'teamcenter_online' && prior && prior.observation_id === item.observation_id && JSON.stringify(prior.source_selector)===JSON.stringify(item.source_selector) && prior.product_tree?.state === 'ready') {
      item.product_tree = prior.product_tree;
    } else if(item.source_kind==='teamcenter_cache_snapshot'&&prior?.source_kind===item.source_kind&&JSON.stringify(prior.cache_binding)===JSON.stringify(item.cache_binding)&&prior.product_tree?.state==='ready'){
      item.product_tree=prior.product_tree;
    } else if (!['live_document','teamcenter_online','teamcenter_cache_snapshot'].includes(item.source_kind) && prior?.content_sha256 === item.content_sha256 && prior?.product_tree?.state === 'ready') {
      item.product_tree = prior.product_tree;
    }
  });
  _modelDocumentCollection.replace(items);
  if (!previous || refreshDocumentGid) {
    _renderModelDocuments(items.map(item => ({ ...item, product_tree_loading: (!refreshDocumentGid || String(item.document_gid) === refreshDocumentGid) && (item.media_type.includes('plmxml') || ['live_document','teamcenter_online','teamcenter_cache_snapshot'].includes(item.source_kind)) && !item.product_tree })));
    _setTreeCacheStatus($('modelDocumentList'), {});
  }
  await Promise.all(items.map(async item => {
    if(refreshDocumentGid&&String(item.document_gid)!==refreshDocumentGid)return;
    if(item.source_kind==='teamcenter_cache_snapshot'){
      try{
        if(!item.cache_binding)throw Error('cache_snapshot_binding_missing');
        if(!item.product_tree||refreshChildren)item.product_tree=window.AI00CacheSnapshotSource.partialTree(item.cache_binding,{workspace_gid:workspaceGid,document_gid:item.document_gid});
        for(const page of Object.values(item.product_tree.pages))if(page.state==='loading'){page.state='failed';page.error='读取已中断，请重试';}
        if(item.product_tree.pages.roots?.state!=='loaded')await window.AI00CacheSnapshotSource.readChildren(_invokeCapability,item.product_tree,null,{isCurrent:()=>generation===_modelRefreshGeneration});
      }catch(error){item.product_tree_error=error.message;}
      return;
    }
    if (item.source_kind === 'live_document') {
      try {
        if (item.role !== 'primary' || !window._readLiveModelProductTree) throw new Error('live_model_tree_unavailable');
        item.product_tree = await window._readLiveModelProductTree(workspaceGid,{allowRebind});
      } catch (error) {
        item.product_tree_error = error?.message || 'live_model_tree_unavailable';
        const prior=priorTrees.get(item.document_gid);
        if(prior?.source_kind===item.source_kind&&prior?.source_identity_hash===item.source_identity_hash)item.product_tree=prior.product_tree;
      }
      return;
    }
    if (item.source_kind === 'teamcenter_online') {
      try {
        const sharedTree=!refreshChildren&&window.AI00ModelCache
          ? await window.AI00ModelCache.readSnapshot(_invokeCapability,workspace.primary_project_gid,item.source_selector,window.AI00TeamcenterOnlineSource.productNode).catch(()=>null) : null;
        if(sharedTree)item.product_tree=sharedTree;
        else if(item.observation_id) item.product_tree = await window.AI00TeamcenterOnlineSource.readSnapshot(_invokeCapability, item.observation_id);
        else {
          item.product_tree = item.product_tree ? JSON.parse(JSON.stringify(item.product_tree)) : window.AI00TeamcenterOnlineSource.partialTree();
          for(const page of Object.values(item.product_tree.pages))if(page.state==='loading'){page.state='failed';page.error='读取已中断，请重试';}
          await window.AI00TeamcenterOnlineSource.readChildren(_requestVisMockupCommand,item,item.product_tree,[],{refresh:refreshChildren,isCurrent:()=>generation===_modelRefreshGeneration});
        }
      } catch (error) { item.product_tree_error = error?.message || 'teamcenter_structure_snapshot_unavailable'; }
      return;
    }
    if (!item.media_type.includes('plmxml') || !item.artifact_ref || item.product_tree) return;
    try {
      item.product_tree = await _readModelDocumentTree(item, items);
    }
    catch (error) { item.product_tree_error = error?.message || 'unknown_error'; }
  }));
  return {items};
  },
  });
}
window._refreshModelDocuments = _refreshModelDocuments;
window._refreshAlternateHierarchies = _refreshAlternateHierarchies;

let _teamcenterSessionStatus = null;
let _teamcenterSessionState = null;
function _getTeamcenterSessionState() {
  if (!_teamcenterSessionState) {
    _teamcenterSessionState=window.AI00TeamcenterSession.createSessionState({api:_eAPI(),onChange:_setTeamcenterSessionButton});
    const refresh=()=>{if(document.visibilityState==='visible')void _refreshTeamcenterSessionButton();};
    document.addEventListener('visibilitychange',refresh);
    window.addEventListener('pagehide',()=>{_teamcenterSessionState.dispose();document.removeEventListener('visibilitychange',refresh);},{once:true});
  }
  return _teamcenterSessionState;
}
const _isTeamcenterSessionReady = value => window.AI00TeamcenterSession?.isReady?.(value) === true;
function _setTeamcenterSessionButton(state, sessionStatus=null, detail='') {
  const button=$('btnTeamcenterSession');if(!button)return;
  const labels={checking:'Teamcenter 检查中', 'signed-out':'Teamcenter 未登录', 'signing-in':'Teamcenter 登录中', ready:'Teamcenter 已登录', error:'Teamcenter 异常'};
  const label=labels[state]||labels.error,username=sessionStatus?.masked_username||'';
  button.dataset.state=state;button.disabled=state==='checking'||state==='signing-in';
  button.querySelector('[data-label]').textContent=state==='ready'&&username?`Teamcenter ${username}`:label;
  button.title=detail||(state==='ready'?`已登录：${username}；点击可退出登录`:label);
  button.setAttribute('aria-label',`Teamcenter 登录状态：${state==='ready'?`已登录 ${username}`:label.replace('Teamcenter ','')}`);
  _teamcenterSessionStatus=state==='ready'?sessionStatus:null;
}

async function _refreshTeamcenterSessionButton() {
  try {return await _getTeamcenterSessionState().refresh();}
  catch {return null;}
}

async function _openTeamcenterSessionControl() {
  _setTeamcenterSessionButton('checking',null,'正在连接本机 Connector…');
  try {
    await _requireConnectorRuntime();
    await _getTeamcenterSessionState().refresh();
  } catch(error) {
    _setTeamcenterSessionButton('error',null,error?.message||'本机 Connector 连接失败');
    throw error;
  }
  if(_isTeamcenterSessionReady(_teamcenterSessionStatus)){
    if(!(await window.AI00Dialogs.confirm(`Teamcenter 当前已登录：${_teamcenterSessionStatus.masked_username}\n是否退出登录？`)))return;
    try{await _getTeamcenterSessionState().logout();window.AI00TeamcenterOnlineSource.clearRevisionRules();}
    catch(error){_setTeamcenterSessionButton('error',null,error?.message||'Teamcenter 退出失败');throw error;}
    return;
  }
  await _teamcenterLoginDialog();
}

function _teamcenterLoginDialog() {
  return new Promise(resolve => {
    _getTeamcenterSessionState();
    const canRemember=['localhost','127.0.0.1'].includes(location.hostname);
    const overlay=document.createElement('div');overlay.className='cs-modal-overlay';
    overlay.innerHTML=`<form class="cs-modal cs-teamcenter-login-dialog"><div class="cs-modal-title">登录 Teamcenter</div>
      <p class="cs-teamcenter-note">${canRemember?'默认只保留到本次运行结束；可选择在本机测试版记住 7 天。':'登录只保留在本机 Connector 当前运行期间，密码不会写入磁盘。'}</p>
      <div class="cs-teamcenter-fields"><div class="cs-field"><label>账号</label><input name="username" autocomplete="username" required maxlength="191"></div><div class="cs-field"><label>密码</label><input name="password" type="password" autocomplete="current-password" required maxlength="1024"></div></div>
      ${canRemember?'<label class="cs-teamcenter-note"><input name="remember" type="checkbox"> 在此 Windows 用户下加密记住登录，重启后自动认证</label>':''}
      <div class="cs-model-document-warning" data-error></div><div class="cs-modal-actions"><button type="button" class="cs-btn" data-cancel>取消</button><button type="submit" class="cs-btn cs-btn-primary">登录</button></div></form>`;
    const form=overlay.querySelector('form'),password=form.elements.password,error=overlay.querySelector('[data-error]');
    let closed=false;
    const close=value=>{if(closed)return;closed=true;password.value='';overlay.remove();if(!value)void _refreshTeamcenterSessionButton();resolve(value);};
    overlay.querySelector('[data-cancel]').onclick=()=>close(null);overlay.addEventListener('click',event=>{if(event.target===overlay)close(null);});
    form.onsubmit=async event=>{event.preventDefault();const submit=form.querySelector('[type=submit]');submit.disabled=true;error.textContent='正在本机认证…';
      try{const status=await _getTeamcenterSessionState().login({endpoint_id:'tc-production',username:form.elements.username.value.trim(),password:password.value,remember:canRemember&&form.elements.remember.checked});window.AI00TeamcenterOnlineSource.clearRevisionRules();password.value='';close(status);
      }catch(caught){password.value='';error.textContent=caught?.message?.includes('teamcenter_session_refresh_failed')?'认证已完成，但会话状态暂未确认，请稍后刷新状态，不必重复登录。':caught?.message||'Teamcenter 登录失败';submit.disabled=false;}};
    document.body.appendChild(overlay);_syncNativeViewportOcclusion();requestAnimationFrame(()=>form.elements.username.focus());
  });
}

async function _requireTeamcenterLogin() {
  await _requireConnectorRuntime(); const api=_eAPI();
  if(typeof api?.teamcenterGetSession!=='function')throw new Error('teamcenter_login_unavailable');
  const current=await _getTeamcenterSessionState().refresh();
  if(_isTeamcenterSessionReady(current))return current;
  const loggedIn=await _teamcenterLoginDialog();
  return _isTeamcenterSessionReady(loggedIn)?loggedIn:null;
}

async function _teamcenterSourceDialog(sessionStatus) {
  const overlay=document.createElement('div');overlay.className='cs-modal-overlay';
  overlay.innerHTML=`<form class="cs-modal cs-teamcenter-source-dialog"><div class="cs-modal-title">选择 Teamcenter 在线数模</div>
    <div class="cs-teamcenter-session"><span data-session-user></span><button type="button" class="cs-btn cs-btn-xs" data-logout>退出登录</button></div>
    <div class="cs-teamcenter-tabs" role="tablist"><button type="button" class="cs-btn active" data-entry="project">选项目</button><button type="button" class="cs-btn" data-entry="search">搜索</button></div>
    <section data-panel="project"><div class="cs-field"><label>项目号</label><input name="projectNumber" placeholder="例如 W10" maxlength="112"><small>系统自动拼接 -ENG00001，版本固定为 00;1</small></div></section>
    <section data-panel="search" hidden><div class="cs-teamcenter-fields"><div class="cs-field"><label>零组件</label><input name="query" placeholder="输入要搜索的零组件 ID" maxlength="128"></div><div class="cs-field"><label>精确版本（可空）</label><input name="searchRevision" maxlength="64"></div></div><small>支持 ID / 名称的精确、前缀和包含匹配；不做错别字或语义搜索。</small></section>
    <div class="cs-teamcenter-fields cs-teamcenter-options"><div class="cs-field"><label>修订规则</label><select name="revisionRule" required><option>Latest Working</option></select></div><div class="cs-field"><label>配置时间</label><input name="configurationDate" type="datetime-local" required></div></div>
    <div class="cs-teamcenter-search-actions"><button type="submit" class="cs-btn cs-btn-primary">查找</button></div>
    <div class="cs-model-document-warning" data-error></div><div class="cs-teamcenter-results" data-results><span>输入条件后查找在线数模</span></div>
    <div class="cs-modal-actions"><button type="button" class="cs-btn" data-cancel>取消</button><button type="button" class="cs-btn cs-btn-primary" data-add disabled>添加到模型文件</button></div></form>`;
  document.body.appendChild(overlay);
  const form=overlay.querySelector('form'),error=overlay.querySelector('[data-error]'),results=overlay.querySelector('[data-results]');
  overlay.querySelector('[data-session-user]').textContent=`已登录：${sessionStatus.masked_username}`;
  form.elements.configurationDate.value=new Date(Date.now()-new Date().getTimezoneOffset()*60000).toISOString().slice(0,16);
  let mode='project',selected=null;
  const close=value=>{overlay.remove();return value;};
  const resultPromise=new Promise(resolve=>{
    overlay.querySelector('[data-cancel]').onclick=()=>resolve(close(null));
    overlay.addEventListener('click',event=>{if(event.target===overlay)resolve(close(null));});
    overlay.querySelector('[data-logout]').onclick=async()=>{await _getTeamcenterSessionState().logout();window.AI00TeamcenterOnlineSource.clearRevisionRules();resolve(close(null));};
    overlay.querySelectorAll('[data-entry]').forEach(button=>button.onclick=()=>{
      mode=button.dataset.entry;selected=null;overlay.querySelectorAll('[data-entry]').forEach(item=>item.classList.toggle('active',item===button));
      overlay.querySelectorAll('[data-panel]').forEach(panel=>panel.hidden=panel.dataset.panel!==mode);
      overlay.querySelector('[data-add]').disabled=true;results.innerHTML='<span>输入条件后查找在线数模</span>';error.textContent='';
    });
    overlay.querySelector('[data-add]').onclick=()=>{if(selected)resolve(close({display_name:selected.display_name,insertion_instance_id:crypto.randomUUID().replaceAll('-',''),source_selector:selected.source_selector}));};
    form.onsubmit=async event=>{event.preventDefault();const submit=form.querySelector('[type=submit]');submit.disabled=true;error.textContent='正在只读查找…';selected=null;
      try{const date=new Date(form.elements.configurationDate.value).toISOString(),rule=form.elements.revisionRule.value;
        const query=mode==='project'?window.AI00TeamcenterSession.projectSearchInput(form.elements.projectNumber.value,rule,date):window.AI00TeamcenterSession.fuzzySearchInput(form.elements.query.value,form.elements.searchRevision.value,rule,date);
        let items=await window.AI00TeamcenterOnlineSource.search(_requestVisMockupCommand,query);
        if(mode==='project')items=items.filter(item=>item.item_id.toLocaleLowerCase()===query.query.toLocaleLowerCase()&&item.revision_id===query.revision_id);
        results.replaceChildren();
        if(!items.length){results.innerHTML='<span>没有匹配的在线数模</span>';error.textContent='';return;}
        items.forEach(item=>{const button=document.createElement('button');button.type='button';button.className='cs-teamcenter-result';
          const title=document.createElement('strong');title.textContent=`${item.item_id} / ${item.revision_id}`;const detail=document.createElement('span');detail.textContent=item.display_name||item.component_type||'';button.append(title,detail);
          button.onclick=()=>{selected=item;results.querySelectorAll('button').forEach(row=>row.classList.toggle('selected',row===button));overlay.querySelector('[data-add]').disabled=false;};results.append(button);});error.textContent=`找到 ${items.length} 个结果，请选择一个`;
      }catch(caught){error.textContent=caught?.message==='teamcenter_project_number_only'?'只需输入项目号，不要输入 -ENG00001':caught?.message||'Teamcenter 查找失败';}
      finally{submit.disabled=false;}};
  });
  const select=form.elements.revisionRule;
  const applyRules=rules=>{const selected=select.value;select.replaceChildren(...rules.map(rule=>{const option=document.createElement('option');option.value=rule;option.textContent=rule;return option;}));select.value=rules.includes(selected)?selected:(rules.includes('Latest Working')?'Latest Working':rules[0]);};
  const cachedRules=window.AI00TeamcenterOnlineSource.cachedRevisionRules();
  if(cachedRules)applyRules(cachedRules);
  else {let rulesStarted=false;const loadRules=async()=>{if(rulesStarted)return;rulesStarted=true;try{applyRules(await window.AI00TeamcenterOnlineSource.revisionRules(_requestVisMockupCommand));}catch(caught){rulesStarted=false;error.textContent=caught?.message||'修订规则读取失败';}};select.addEventListener('pointerdown',loadRules);select.addEventListener('keydown',event=>{if(['ArrowDown','Enter',' '].includes(event.key))loadRules();});}
  form.elements.projectNumber.focus();return resultPromise;
}

async function _openTeamcenterOnlineDocument(document, mode) {
  if(mode==='new'&&String(_pendingTeamcenterOnlineBinding?.documentGid)===String(document?.document_gid))
    return _retryPendingTeamcenterOnlineBinding(document);
  const session=await _requireTeamcenterLogin();
  if(!session)return false;
  _cmdShow(mode==='new'?'正在打开新的 VisMockup 文档…':'正在插入当前 VisMockup 文档…');
  if(mode!=='new'){
    await window.AI00TeamcenterOnlineSource.openOnline(_requestVisMockupCommand,document,mode);
    return true;
  }
  const controller=window._simulationEnvironmentWorkspace,workspace=controller?.store?.state?.workspace;
  if(!workspace?.workspace_gid)throw new Error('请先选择仿真环境');
  const localMode=await window._localViewerInteractionEnabled?.()===true;
  const launch=await window.AI00TeamcenterOnlineSource.openOnline(
    (id,payload,options)=>_requestVisMockupCommand(id,payload,{...options,version:localMode?2:1}),document,mode);
  const launchOperationId=String(launch?.plan_id||'');
  if(!launchOperationId)throw new Error('文档已打开，绑定未完成：launch_operation_identity_missing');
  _pendingTeamcenterOnlineBinding={
    document,documentGid:String(document.document_gid),workspaceGid:String(workspace.workspace_gid),
    expectedWorkspaceRowVersion:Number(workspace.row_version),launchOperationId,
    identityOperationId:null,documentSession:null,localMode,
  };
  if(localMode){
    const step=launch?.steps?.length===1?launch.steps[0]:null;
    const receipt=step?.result;
    if(step?.status!=='succeeded'||receipt?.protocol!=='ai00.viewer.opened-source.v1'||!receipt.document_identity?.document_session)
      throw Error('opened_source_receipt_invalid');
    _pendingTeamcenterOnlineBinding.documentSession=receipt.document_identity.document_session;
  }
  return _retryPendingTeamcenterOnlineBinding(document);
}

function _teamcenterDocumentIdentityReceipt(outcome){
  const step=outcome?.steps?.length===1?outcome.steps[0]:null;
  const operationId=String(outcome?.plan_id||'');
  const documentSession=String(step?.result?.document_session||'');
  if(!operationId||step?.status!=='succeeded'||!documentSession)throw new Error('document_identity_unavailable');
  return {operationId,documentSession};
}

function _teamcenterBindingStillCurrent(pending){
  const workspace=window._simulationEnvironmentWorkspace?.store?.state?.workspace;
  if(String(workspace?.workspace_gid)!==pending.workspaceGid)return false;
  const documents=_modelDocumentCollection?.state?.documents;
  return String(_modelDocumentWorkspaceGid)!==pending.workspaceGid||!Array.isArray(documents)
    ||documents.some(item=>String(item.document_gid)===pending.documentGid
    &&item.source_kind==='teamcenter_online');
}

function _completeLocalViewerPresentation(){
  window._liveDocumentContextUnavailable=false;
  _vmConnected=true;_setVmDocumentReady(true);_setLaunchButton('reconnect');
  _setVmStatus('connected','已内嵌');_notifyNativeViewportBounds();
}

async function _completeTeamcenterOnlineBinding(pending){
  const controller=window._simulationEnvironmentWorkspace,workspace=controller?.store?.state?.workspace;
  if(!_teamcenterBindingStillCurrent(pending))throw new Error('online_binding_environment_changed');
  if(pending.localMode){
    _setVmStatus('connecting','模型已打开，正在完成本地内嵌…');
    const bounds=_nativeViewportBounds();
    if(bounds?.width&&bounds?.height)_eAPI()?.visMockupNativeView?.updateBounds?.(bounds);
    const result=await window._openLocalViewerFromLaunch({workspace_gid:pending.workspaceGid,document_gid:pending.documentGid,
      launch_operation_id:pending.launchOperationId,expected_workspace_row_version:pending.expectedWorkspaceRowVersion,
      idempotency_key:`online-live-bind-${pending.launchOperationId}-${pending.documentGid}`});
    if(!_teamcenterBindingStillCurrent(pending)||!controller.store.applyOpenedDocument(pending.workspaceGid,pending.expectedWorkspaceRowVersion,result)){
      await window._localViewerInteraction?.()?.close();throw new Error('online_binding_environment_changed');
    }
    _completeLocalViewerPresentation();
    if(_pendingTeamcenterOnlineBinding===pending)_pendingTeamcenterOnlineBinding=null;
    return result;
  }
  if(!pending.localMode&&!pending.identityOperationId){
    let lastError;
    for(let attempt=0;attempt<20;attempt++){
      if(!_teamcenterBindingStillCurrent(pending))throw new Error('online_binding_environment_changed');
      try{
        const receipt=_teamcenterDocumentIdentityReceipt(await _requestVisMockupCommand(
          'simulation.vismockup.document.identity.read.request',{}, {confirmation:false}));
        pending.identityOperationId=receipt.operationId;pending.documentSession=receipt.documentSession;break;
      }catch(error){lastError=error;}
      await new Promise(resolve=>setTimeout(resolve,500));
    }
    if(!pending.identityOperationId)throw lastError||new Error('new_document_identity_timeout');
  }
  if(!_teamcenterBindingStillCurrent(pending))throw new Error('online_binding_environment_changed');
  _setVmStatus('connecting','模型已打开，正在内嵌本次文档…');
  const attached=await _attachNativeViewport({openedDocumentSession:pending.documentSession});
  if(attached?.state!=='attached')throw new Error(attached?.error||'native_document_embed_failed');
  if(!_teamcenterBindingStillCurrent(pending))throw new Error('online_binding_environment_changed');
  const idempotencyKey=`online-live-bind-${pending.launchOperationId}-${pending.documentGid}`;
  const result=await _invokeCapability('simulation.environment.online_source.live_document.bind',{
    workspace_gid:pending.workspaceGid,document_gid:pending.documentGid,
    launch_operation_id:pending.launchOperationId,...(pending.localMode?{}:{identity_operation_id:pending.identityOperationId}),
    expected_workspace_row_version:pending.expectedWorkspaceRowVersion,idempotency_key:idempotencyKey,
  },{version:pending.localMode?2:1,confirmation:true,idempotency:true,idempotencyKey,expectedResourceVersion:pending.expectedWorkspaceRowVersion});
  if(!_teamcenterBindingStillCurrent(pending))
    throw new Error('online_binding_environment_changed');
  await controller.store.openWorkspace(pending.workspaceGid);
  if(!_teamcenterBindingStillCurrent(pending))throw new Error('online_binding_environment_changed');
  if(pending.localMode)await window._openLocalViewerInteraction({workspace_gid:pending.workspaceGid,document_gid:pending.documentGid});
  window._liveDocumentContextUnavailable=false;
  _vmConnected=true;_setVmDocumentReady(true);_setLaunchButton('reconnect');
  _setVmStatus('connected','已内嵌');_notifyNativeViewportBounds();
  if(_pendingTeamcenterOnlineBinding===pending)_pendingTeamcenterOnlineBinding=null;
  return result;
}

async function _retryPendingTeamcenterOnlineBinding(document){
  const pending=_pendingTeamcenterOnlineBinding;
  if(!pending||String(pending.documentGid)!==String(document?.document_gid))
    throw new Error('online_document_binding_retry_unavailable');
  try{return await _completeTeamcenterOnlineBinding(pending);}
  catch(error){
    window._liveDocumentContextUnavailable=true;_notifyNativeViewportBounds();
    const message=`文档已打开，绑定未完成：${error?.message||'unknown_error'}；请重试绑定，不要重复打开文档`;
    _setVmStatus('error',message);throw new Error(message);
  }
}

async function _addTeamcenterSource() {
  const controller=window._simulationEnvironmentWorkspace,workspace=controller?.store?.state?.workspace;
  if(!workspace?.workspace_gid)throw new Error('请先选择仿真环境');
  const session=await _requireTeamcenterLogin();if(!session)return;
  const source=await _teamcenterSourceDialog(session);if(!source)return;
  const result=await window.AI00TeamcenterOnlineSource.bindSource({invoke:_invokeCapability,workspace,source});
  _teamcenterInitialExpand.add(String(result.document_gid));
  if(controller.store.state.workspace?.workspace_gid!==workspace.workspace_gid)return;
  await controller.store.openWorkspace(workspace.workspace_gid);await _refreshModelDocuments(controller.store.state.workspace,{refreshDocumentGid:String(result.document_gid)});
  const added=_modelDocumentCollection.state.documents.find(doc=>doc.document_gid===result.document_gid);
  const failed=!added||added.product_tree_error;
  _cmdShow(failed?`${source.display_name} 已登记，结构读取失败，请重试`:`${source.display_name} 已加入模型文件，结构按需读取`,failed?'err':'ok');
}

function _dependencyFilename(value) {
  let text = String(value || '').replaceAll('\\', '/');
  try { text = decodeURIComponent(text); } catch (_) { /* keep the encoded name for a deterministic miss */ }
  return text.split('/').pop().trim().toLocaleLowerCase();
}

function _matchedModelDependencyArtifacts(item, locations, items) {
  return Array.from(locations || [], location => {
    const key = _dependencyFilename(location);
    if (!key) return null;
    const matches = items.filter(candidate => candidate !== item
      && candidate.artifact_ref
      && (candidate.media_type === 'application/plmxml+xml' || candidate.media_type === 'application/vnd.siemens.plmxml+xml')
      && _dependencyFilename(candidate.display_name) === key);
    return matches.length === 1 ? { location, artifact_ref: matches[0].artifact_ref } : null;
  }).filter(Boolean);
}

async function _readModelDocumentTree(item, items) {
  const collection = window.AI00ModelDocumentCollection;
  let tree = await collection.readAllProductTreePages(_invokeCapability, item.artifact_ref, 5000, [], item.document_gid);
  if (tree?.state !== 'dependency_required') return tree;
  const dependencies = _matchedModelDependencyArtifacts(item, tree.dependency_locations, items);
  if (!dependencies.length) return tree;
  return collection.readAllProductTreePages(_invokeCapability, item.artifact_ref, 5000, dependencies, item.document_gid);
}

async function _addModelDocument() {
  const controller = window._simulationEnvironmentWorkspace;
  const workspace = controller?.store?.state?.workspace;
  if (!workspace?.workspace_gid) { _cmdShow('请先选择仿真环境', 'err'); return; }
  const selected = await _modelArtifactFromFile();
  const artifactRef = selected?.artifact_ref;
  if (!artifactRef) throw new Error('artifact_ref_missing');
  const name = selected.name || artifactRef.artifact_id;
  const isPlmxml = artifactRef.media_type === 'application/vnd.siemens.plmxml+xml' || artifactRef.media_type === 'application/plmxml+xml';
  const role = _modelDocumentCollection.state.documents.length ? 'inserted' : 'primary';
  if (role === 'primary' && !isPlmxml) throw new Error('请先添加主 PLMXML 文件');
  const idempotencyKey = `model-document-${workspace.workspace_gid}-${artifactRef.sha256}`.slice(0, 191);
  _modelDocumentCollection.setRuntimeProgress('staging', { name });
  _cmdShow(`正在登记模型文件：${name}`);
  if (isPlmxml) {
    await _insertPlmxmlArtifact({ workspace, artifactRef, name, idempotencyKey });
  } else if (artifactRef.media_type === 'model/jt' || artifactRef.media_type === 'model/vnd.jt') {
    const hash = artifactRef.sha256.replace(/^sha256:/, '');
    await _invokeCapability('simulation.environment.model_document.add', {
      workspace_gid: workspace.workspace_gid,
      expected_row_version: workspace.row_version,
      role,
      display_name: name,
      media_type: artifactRef.media_type,
      artifact_ref: artifactRef,
      source_kind: 'artifact',
      source_identity_hash: `sha256:${hash}`,
      content_sha256: `sha256:${hash}`,
      portability: 'portable',
      idempotency_key: idempotencyKey,
    }, { idempotency: true });
  } else throw new Error('model_document_media_type_invalid');
  await controller.store.openWorkspace(workspace.workspace_gid);
  await Promise.all([_refreshModelDocuments(controller.store.state.workspace), _refreshAlternateHierarchies(controller.store.state.workspace)]);
  _modelDocumentCollection.setRuntimeProgress('idle', { synchronized: false, name });
  _cmdShow(`${name} 已加入仿真环境；点击“同步到 VisMockup”统一更新`, 'ok');
}

function _openPlmxmlInsertDialog(inspection) {
  const overlay = $('plmxmlInsertOverlay');
  const form = $('plmxmlInsertForm');
  const choices = $('plmxmlHierarchyChoices');
  $('plmxmlInsertSummary').textContent = `检测到 ${inspection.hierarchies.length} 个备选层次、${inspection.dependencies.length} 个外部模型依赖。`;
  $('plmxmlDependencyNotice').textContent = inspection.dependencies.length
    ? '本次只导入 PLMXML 结构；外部模型引用会登记为待解析，不需要现在选择文件。' : '该文件没有外部模型依赖。';
  $('plmxmlInsertError').textContent = '';
  choices.replaceChildren(...inspection.hierarchies.map(item => {
    const label = document.createElement('label');
    const input = document.createElement('input'); input.type = 'checkbox'; input.value = item.projection_identity; input.checked = true;
    label.append(input, `${item.name || item.projection_identity}（${item.placement_count} 节点）`); return label;
  }));
  const syncMode = () => {
    const modelOnly = form.elements.plmxmlInsertMode.value === 'model_only';
    choices.disabled = modelOnly;
  };
  form.onchange = syncMode; syncMode();
  overlay.classList.remove('hidden');
  return new Promise(resolve => {
    const close = value => { overlay.classList.add('hidden'); form.onsubmit = null; form.onchange = null; $('plmxmlInsertCancel').onclick = null; resolve(value); };
    $('plmxmlInsertCancel').onclick = () => close(null);
    form.onsubmit = event => {
      event.preventDefault();
      const mode = form.elements.plmxmlInsertMode.value;
      const selected = mode === 'model_only' ? [] : Array.from(choices.querySelectorAll('input:checked')).map(item => item.value);
      if (mode !== 'model_only' && !selected.length) { $('plmxmlInsertError').textContent = '请至少选择一个备选层次，或改选“仅插入模型文件”。'; return; }
      close({ mode, selected_hierarchy_identities: selected });
    };
  });
}

async function _insertPlmxmlArtifact({ workspace, artifactRef, name, idempotencyKey }) {
  const inspection = await _invokeCapability('simulation.plmxml.environment.inspect', { artifact_ref: artifactRef });
  const choice = await _openPlmxmlInsertDialog(inspection);
  if (!choice) throw new Error('native_selection_cancelled');
  return _invokeCapability('simulation.environment.plmxml.insert', {
    workspace_gid: workspace.workspace_gid,
    expected_row_version: workspace.row_version,
    artifact_ref: artifactRef,
    display_name: name,
    mode: choice.mode,
    selected_hierarchy_identities: choice.selected_hierarchy_identities,
    inspection_hash: inspection.inspection_hash,
    idempotency_key: idempotencyKey,
  }, { idempotency: true });
}

async function _saveCurrentEnvironment() {
  const controller = window._simulationEnvironmentWorkspace;
  const workspace = controller?.store?.state?.workspace;
  if (!workspace) throw new Error('workspace_not_selected');
  const result = await _invokeCapability('simulation.environment.version.freeze', {
    workspace_gid: workspace.workspace_gid, expected_row_version: workspace.row_version,
    algorithms: { plmxml: 'environment-codec.v1', manifest: 'simulation-environment.v1' },
    idempotency_key: `save-environment-${workspace.workspace_gid}-${workspace.row_version}`,
  }, { idempotency: true });
  await controller.store.openWorkspace(workspace.workspace_gid);
  _cmdShow(`仿真环境已保存为不可变版本 ${result.version_gid}`, 'ok');
  return result;
}

async function _syncCurrentEnvironment() {
  const controller = window._simulationEnvironmentWorkspace;
  const workspace = controller?.store?.state?.workspace;
  if (!workspace) throw new Error('workspace_not_selected');
  const exported = await _invokeCapability('simulation.plmxml.environment.export', {
    workspace_gid: workspace.workspace_gid,
    idempotency_key: `sync-export-${workspace.workspace_gid}-${workspace.row_version}`,
  }, { idempotency: true });
  await _requireConnectorRuntime();
  await _requestVisMockupCommand('simulation.vismockup.model.open.request', { artifact_ref: exported.artifact_ref }, { confirmation: true });
  _modelDocumentCollection?.setRuntimeProgress('idle', { synchronized: true, semantic_hash: exported.semantic_hash });
  _onConnected(); _cmdShow('当前仿真环境已统一同步到 VisMockup', 'ok');
}

async function _exportCurrentEnvironment() {
  const workspace = window._simulationEnvironmentWorkspace?.store?.state?.workspace;
  if (!workspace) throw new Error('workspace_not_selected');
  const exported = await _invokeCapability('simulation.plmxml.environment.export', {
    workspace_gid: workspace.workspace_gid,
    idempotency_key: `file-export-${workspace.workspace_gid}-${workspace.row_version}`,
  }, { idempotency: true });
  await window.AI00Business.invoke('base.artifact.get', {
    version: 1, payload: { artifact_ref: exported.artifact_ref, name: `${workspace.name || 'environment'}.plmxml` }, native_io: { save: true },
  });
  _cmdShow('PLMXML 已导出', 'ok');
}

function _openCacheSnapshotPicker() {
  const workspace=window._simulationEnvironmentWorkspace?.store?.state?.workspace;
  if(!workspace?.workspace_gid){_cmdShow('请先选择仿真环境','err');return;}
  return window.AI00CacheSnapshotPicker.open({invoke:_invokeCapability,workspace,
    isCurrent:()=>window._simulationEnvironmentWorkspace?.store?.state?.workspace===workspace,
    onAdded:async result=>{
      workspace.row_version=result.workspace_row_version;workspace.cache_revision_hash=result.cache_revision_hash;
      await _refreshModelDocuments(workspace,{refreshDocumentGid:result.document_gid});
      _cmdShow('共用缓存批次已加载，模型树按需读取','ok');
    }}).catch(error=>_cmdShow(error.message,'err'));
}

function _bindEnvironmentActions() {
  const menu = $('environmentInsertMenu');
  $('btnEnvironmentInsert')?.addEventListener('click', event => { event.stopPropagation(); menu?.classList.toggle('hidden'); });
  document.addEventListener('click', event => { if (!event.target.closest('#environmentInsertMenu,#btnEnvironmentInsert')) menu?.classList.add('hidden'); });
  menu?.addEventListener('click', event => {
    const source = event.target.closest('[data-insert-source]')?.dataset.insertSource; if (!source) return;
    menu.classList.add('hidden');
    if (source === 'plmxml' || source === 'jt') _addModelDocument().catch(error => { if (error?.message !== 'native_selection_cancelled') _cmdShow(error?.message || '插入失败', 'err'); });
    else if (source === 'bop') _openBopInsert().catch(error => _cmdShow(error?.message || 'BOP 插入准备失败', 'err'));
    else if(source==='cache_snapshot')void _openCacheSnapshotPicker();
  });
  $('btnEnvironmentSave')?.addEventListener('click', () => _saveCurrentEnvironment().catch(error => _cmdShow(error?.message || '保存失败', 'err')));
  $('btnEnvironmentSync')?.addEventListener('click', () => _syncCurrentEnvironment().catch(error => _cmdShow(error?.message || '同步失败', 'err')));
  $('btnEnvironmentExport')?.addEventListener('click', () => _exportCurrentEnvironment().catch(error => { if (error?.message !== 'native_selection_cancelled') _cmdShow(error?.message || '导出失败', 'err'); }));
}

async function _openBopInsert() {
  const overlay = $('bopInsertOverlay');
  if (overlay.dataset.busy === 'true') { overlay.classList.remove('hidden'); return; }
  const controller = window._simulationEnvironmentWorkspace;
  const workspace = controller?.store?.state?.workspace;
  if (!workspace?.workspace_gid) throw new Error('请先新建或打开个人仿真环境');
  if (!_bopVersions.length) await _loadBopVersions();
  const form = $('bopInsertForm');
  const version = $('bopInsertVersion');
  const line = $('bopInsertLine');
  const depth = $('bopInsertDepth');
  const name = $('bopInsertName');
  const summary = $('bopInsertSummary');
  const error = $('bopInsertError');
  const submit = $('bopInsertSubmit');
  let preview = null;
  let previewPayload = null;
  let inputRevision = 0;
  const requireCurrentEnvironment = () => {
    if (String(controller.store.state.workspace?.workspace_gid) !== String(workspace.workspace_gid)) {
      throw new Error('仿真环境已切换，请关闭后重新打开插入窗口');
    }
  };
  const versionGid = item => String(item.version_gid || item.gid || '');
  version.replaceChildren(new Option('— 选择 BOP 版本 —', ''), ..._bopVersions
    .filter(item => versionGid(item))
    .map(item => new Option(`${item.bop_name || item.name || versionGid(item)}${item.status ? ` [${item.status}]` : ''}`, versionGid(item))));
  if (_bopVersionLoadError && !_bopVersions.length) {
    error.textContent = `BOP 版本读取失败：${_bopVersionLoadError.message || '请重试'}`;
  } else if (!_bopVersions.length) {
    error.textContent = '暂无可用 BOP 版本';
  }
  const resetPreview = () => {
    inputRevision += 1; previewPayload = null;
    preview = null; submit.textContent = '生成预览'; error.textContent = '';
    summary.textContent = '先预览节点、模型引用和资源引用数量，再确认插入。';
  };
  const loadLines = async () => {
    resetPreview();
    line.replaceChildren(new Option('全部线体', ''));
    if (!version.value) return;
    const structure = await _invokeCapability('craft.bop.alt_hierarchy.read', {
      version_gid: version.value,
      node_types: ['line', 'line_process'],
    });
    const lines = (structure?.entries || []).filter(item => ['line', 'line_process'].includes(item.node_type));
    line.append(...lines.map(item => new Option(item.title || item.name || item.gid, String(item.gid))));
    const selected = _bopVersions.find(item => versionGid(item) === version.value);
    name.value = `${selected?.bop_name || selected?.name || 'BOP'} 仿真层次`;
  };
  version.onchange = () => loadLines().catch(caught => { error.textContent = caught?.message || '线体加载失败'; });
  line.onchange = resetPreview; depth.onchange = resetPreview; name.oninput = resetPreview;
  form.onsubmit = async event => {
    event.preventDefault(); error.textContent = '';
    if (submit.disabled) return;
    const revision = inputRevision;
    const payload = previewPayload || { workspace_gid: String(workspace.workspace_gid), version_gid: version.value,
      line_gid: line.value || null, fork_depth: depth.value, hierarchy_name: name.value.trim(),
      expected_row_version: Number(workspace.row_version) };
    if (!payload.version_gid || !payload.hierarchy_name) { error.textContent = '请选择 BOP 版本并填写层次名称'; return; }
    submit.disabled = true;
    overlay.dataset.busy = 'true';
    const controls = [version, line, depth, name];
    controls.forEach(control => { control.disabled = true; });
    const startedAt = Date.now();
    const action = preview ? '正在插入 BOP' : '正在生成预览';
    const showProgress = () => {
      submit.textContent = `${action}… ${Math.floor((Date.now() - startedAt) / 1000)} 秒`;
      summary.textContent = `${action}，请等待。关闭弹窗不会取消已提交的请求；重新打开可查看状态。`;
    };
    showProgress();
    const progressTimer = setInterval(showProgress, 1000);
    try {
      requireCurrentEnvironment();
      if (!preview) {
        // Read the target revision without replacing the user's cached model tree.
        const current = await _invokeCapability('simulation.environment.workspace.get', { workspace_gid: payload.workspace_gid });
        requireCurrentEnvironment();
        if (revision !== inputRevision) return;
        payload.expected_row_version = Number(current.row_version);
        const result = await _invokeCapability('simulation.environment.bop_projection.preview', payload, {
          expectedResourceVersion: payload.expected_row_version,
        });
        requireCurrentEnvironment();
        if (revision !== inputRevision) return;
        preview = result; previewPayload = payload;
        summary.textContent = `将插入 ${preview.node_count} 个工艺节点；分离 ${preview.model_reference_count} 个模型引用、${preview.resource_reference_count} 个资源引用。来源 r${preview.source_revision}。`;
        submit.textContent = '确认插入';
      } else {
        const inserted = await _invokeCapability('simulation.environment.bop_projection.apply', {
          ...payload, plan_hash: preview.plan_hash, idempotency_key: `bop-projection-${workspace.workspace_gid}-${Date.now()}`,
        }, {
          confirmation: true,
          idempotency: true,
          expectedResourceVersion: payload.expected_row_version,
        });
        overlay.classList.add('hidden');
        if (String(controller.store.state.workspace?.workspace_gid) !== payload.workspace_gid) return;
        await controller.store.openWorkspace(workspace.workspace_gid);
        await _refreshAlternateHierarchies(controller.store.state.workspace, inserted.hierarchy_gid);
        _cmdShow(`${payload.hierarchy_name} 已插入`, 'ok');
      }
    } catch (caught) {
      const code = caught?.code || caught?.message;
      if (['version_conflict', 'bop_projection_plan_changed'].includes(code)) {
        resetPreview();
        error.textContent = '仿真环境或 BOP 已更新，旧预览已失效。请重新生成预览，再确认插入。';
      } else error.textContent = caught?.message || 'BOP 插入失败';
    }
    finally {
      clearInterval(progressTimer);
      delete overlay.dataset.busy;
      controls.forEach(control => { control.disabled = false; });
      submit.disabled = false;
      submit.textContent = preview ? '确认插入' : '生成预览';
    }
  };
  $('bopInsertCancel').onclick = () => { if (overlay.dataset.busy !== 'true') resetPreview(); overlay.classList.add('hidden'); };
  submit.disabled = false;
  submit.textContent = '生成预览';
  summary.textContent = '先预览节点、模型引用和资源引用数量，再确认插入。';
  overlay.classList.remove('hidden');
}

function _bindModelDocuments() {
  if (!window.AI00ModelDocumentCollection) return;
  _modelDocumentCollection = window.AI00ModelDocumentCollection.createCollection();
  document.addEventListener('pointerdown', event => {
    if (_alternateContextMenu && !_alternateContextMenu.contains(event.target)) _closeAlternateContextMenu();
  });
  document.addEventListener('keydown', event => { if (event.key === 'Escape') _closeAlternateContextMenu(); });
  window.addEventListener('blur', _closeAlternateContextMenu);
  $('btnAddModelDocument')?.addEventListener('click', () => _addModelDocument().catch(error => {
    if (error?.message !== 'native_selection_cancelled') _cmdShow(error?.message || '模型文件添加失败', 'err');
    _modelDocumentCollection?.setRuntimeProgress('failed', { domainCode: error?.message || 'model_document_add_failed' });
  }));
  $('btnAddTeamcenterSource')?.addEventListener('click', () => _addTeamcenterSource().catch(error => _cmdShow(error?.message || 'Teamcenter 在线模型添加失败','err')));
  $('btnAddCacheSnapshot')?.addEventListener('click', () => {void _openCacheSnapshotPicker();});
  $('btnTeamcenterSession')?.addEventListener('click', () => _openTeamcenterSessionControl().catch(error => _cmdShow(error?.message || 'Teamcenter 登录操作失败','err')));
  void _refreshTeamcenterSessionButton();
  $('btnAddAlternateHierarchy')?.addEventListener('click', () => _addAlternateHierarchy().catch(error => _cmdShow(error?.message || '层次结构创建失败', 'err')));
  const targetTree = $('alternateHierarchyList');
  targetTree?.addEventListener('dragover', event => {
    const target = event.target.closest('[data-node-gid]');
    const types = Array.from(event.dataTransfer?.types || []);
    if (target && (types.includes('application/x-ai00-model-node') || types.includes('application/x-ai00-model-document') || types.includes('application/x-ai00-resource'))) {
      event.preventDefault(); target.classList.add('cs-placement-target');
    }
  });
  targetTree?.addEventListener('dragleave', event => event.target.closest('[data-node-gid]')?.classList.remove('cs-placement-target'));
  targetTree?.addEventListener('drop', event => {
    const target = event.target.closest('[data-node-gid]');
    const documentGid = event.dataTransfer?.getData('application/x-ai00-model-document');
    const modelNodeJson = event.dataTransfer?.getData('application/x-ai00-model-node');
    const resourceJson = event.dataTransfer?.getData('application/x-ai00-resource');
    target?.classList.remove('cs-placement-target');
    if (!target || (!modelNodeJson && !documentGid && !resourceJson)) return;
    event.preventDefault();
    try {
      const action = modelNodeJson ? _placeModelNode(JSON.parse(modelNodeJson), target.dataset.nodeGid)
        : documentGid ? _placeModelDocument(documentGid, target.dataset.nodeGid)
        : _placeResource(JSON.parse(resourceJson), target.dataset.nodeGid);
      action.catch(error => _cmdShow(error?.message || '资源编排失败', 'err'));
    } catch (error) { _cmdShow(error?.message || '资源编排失败', 'err'); }
  });
  const controller = window._simulationEnvironmentWorkspace;
  controller?.store?.subscribe(state => {
    _setViewerEnvironmentLabel(state);
    const gid = state.workspace?.workspace_gid || null;
    if (gid === _modelDocumentWorkspaceGid && gid === _alternateHierarchyWorkspaceGid && gid === _resourceWorkspaceGid) return;
    Promise.all([_refreshModelDocuments(state.workspace,{useCache:true}), _refreshAlternateHierarchies(state.workspace,null,{useCache:true}), _refreshSimulationResources(state.workspace)])
      .then(() => _cmdShow(''))
      .catch(error => _cmdShow(error?.message || '产品结构加载失败', 'err'));
  });
  _setViewerEnvironmentLabel(controller?.store?.state);
  Promise.all([_refreshModelDocuments(undefined,{useCache:true}), _refreshAlternateHierarchies(undefined,null,{useCache:true}), _refreshSimulationResources()]).catch(() => {});
}

function _bindPanelWidthHandles() {
  const shell = document.querySelector('.cs-sim-shell');
  const viewport = $('simulationFuturePanel');
  if (!shell || !viewport) return;
  for (const [handleId, panelId, variable] of [
    ['environmentWidthHandle', 'simulationEnvironmentPanel', '--bop-panel-w'],
    ['modelWidthHandle', 'modelDocumentsPanel', '--model-panel-w'],
  ]) {
    const handle = $(handleId);
    const panel = $(panelId);
    if (!handle || !panel) continue;
    const width = () => panel.getBoundingClientRect().width;
    const update = requested => {
      const maximum = Math.max(180, Math.min(600, width() + viewport.getBoundingClientRect().width - 320));
      const next = Math.round(Math.max(180, Math.min(maximum, requested)));
      shell.style.setProperty(variable, `${next}px`);
      handle.setAttribute('aria-valuenow', String(next));
      handle.setAttribute('aria-valuemax', String(Math.round(maximum)));
      _notifyNativeViewportBounds();
    };
    handle.setAttribute('aria-valuemin', '180');
    handle.setAttribute('aria-valuemax', '600');
    handle.setAttribute('aria-valuenow', String(Math.round(width())));
    handle.addEventListener('pointerdown', event => {
      if (event.button !== 0) return;
      event.preventDefault();
      const startX = event.clientX;
      const startWidth = width();
      handle.setPointerCapture?.(event.pointerId);
      const move = current => update(startWidth + current.clientX - startX);
      const stop = () => {
        handle.removeEventListener('pointermove', move);
        handle.removeEventListener('pointerup', stop);
        handle.removeEventListener('pointercancel', stop);
        handle.removeEventListener('lostpointercapture', stop);
      };
      handle.addEventListener('pointermove', move);
      handle.addEventListener('pointerup', stop);
      handle.addEventListener('pointercancel', stop);
      handle.addEventListener('lostpointercapture', stop);
    });
    handle.addEventListener('keydown', event => {
      if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
      event.preventDefault();
      update(width() + (event.key === 'ArrowRight' ? 24 : -24));
    });
  }
}

function _applyVisTreeOpenDepth() {
  const body = $('visTreeBody');
  if (!body) return;
  const openDepth = Math.max(1, Math.min(5, Number($('vmTreeDepth')?.value || 1)));
  body.querySelectorAll('.cs-vis-section').forEach(section => {
    const children = Array.from(section.children).find(item => item.classList.contains('cs-vis-children'));
    const toggle = section.querySelector('.cs-vis-section-hdr .cs-vis-toggle');
    if (children) children.style.display = '';
    if (toggle) toggle.textContent = '▼';
  });
  body.querySelectorAll('.cs-vis-row').forEach(row => {
    const children = Array.from(row.children).find(item => item.classList.contains('cs-vis-children'));
    if (!children || children.children.length === 0) return;
    const open = Number(row.dataset.depth || 0) < openDepth;
    children.style.display = open ? '' : 'none';
    const toggle = row.querySelector('.cs-vis-node .cs-vis-toggle');
    if (toggle) toggle.textContent = open ? '▼' : '▶';
    const key = row.dataset.key;
    if (key) open ? _visExpandedKeys.add(key) : _visExpandedKeys.delete(key);
  });
}

async function _openPlmxmlTree(file = null) {
  if (!file) {
    $('vmPlmxmlFile')?.click();
    return;
  }
  const loading = $('visTreeLoading');
  loading?.classList.remove('hidden');
  $('visTreeEmpty')?.classList.add('hidden');
  _cmdShow(`正在读取 ${file.name}…`);
  try {
    const text = await file.text();
    const snapshot = window.AI00PlmxmlTreeImport.parsePlmxmlTree(text, { maxNodes: 250000 });
    _renderVisTreeSnapshot(window.AI00VmSnapshotTree.snapshotToVisTree(snapshot), 'manual_plmxml');
    const storedAt = Number.isFinite(file.lastModified) && file.lastModified > 0
      ? new Date(file.lastModified).toLocaleString('zh-CN', { hour12: false }) : '未知时间';
    const sourceBanner = $('plmxmlSourceBanner');
    $('plmxmlProjectCode').textContent = window.AI00VmSnapshotTree.projectNumberFromPlmxmlName(file.name);
    $('plmxmlStoredAt').textContent = storedAt;
    sourceBanner.title = `来源文件：${file.name}`;
    sourceBanner.classList.remove('hidden');
    _cmdShow(`PLMXML 已载入：${snapshot.nodes.length} 个结构节点；实时控制需连接匹配的 VisMockup 模型`, 'ok');
  } catch (error) {
    $('visTreeEmpty').textContent = `PLMXML 读取失败：${error.message || '文件格式不受支持'}`;
    $('visTreeEmpty').classList.remove('hidden');
    _cmdShow($('visTreeEmpty').textContent, 'err');
  } finally {
    loading?.classList.add('hidden');
  }
}

async function _loadVisTree(force = false) {
  if (!_vmConnected) {
    $('visTreeEmpty').textContent = '请先连接 VisMockup';
    $('visTreeEmpty').classList.remove('hidden');
    return false;
  }

  // force=true 时重建 DOM；force=false 且已加载过则跳过（防止重复渲染）
  if (!force && _visTreeLoaded) return true;

  const loadingElement = $('visTreeLoading');
  const timer = window.AI00SimulationEnvironmentWorkspace.createElapsedIndicator(
    $('visTreeLoadingText'), '正在从 VisMockup 同步 VM 结构',
  );
  loadingElement.classList.remove('hidden');
  $('visTreeEmpty').classList.add('hidden');
  // 提示整车数模首次遍历耗时较长
  if (force) {
    const loadingEl = $('visTreeLoading');
    if (loadingEl) loadingEl.title = '整车数模首次遍历可能需要数分钟，请耐心等待';
  }

  let r;
  try {
    const outcome = await _requestVisMockupCommand(
      'simulation.vismockup.tree.read.request', {
        max_depth: VM_FULL_SYNC_DEPTH,
        force_refresh: Boolean(force),
      }, { confirmation: false },
    );
    const treeResult = outcome?.steps?.at(-1)?.result;
    if (!treeResult?.nodes) throw new Error('vismockup_tree_result_invalid');
    _simulationDebug('ui_tree_validated',{node_count:treeResult.nodes.length,cache_state:treeResult.cache_state||'verified',force_refresh:force});
    r = {
      success: true,
      data: {
        tree: window.AI00VmSnapshotTree.snapshotToVisTree(treeResult),
        cacheState: treeResult.cache_state || 'verified',
      },
    };
  } catch (error) {
    r = { success: false, error: error.message || '结构树加载失败', data: {} };
  }
  timer.stop();
  loadingElement.classList.add('hidden');

  // ── DEBUG: 打印原始树数据，排查节点截断问题 ──────────────────────────────────
  console.group('[AI00] get_vis_tree raw response');
  console.log('success:', r?.success, ' cached:', r?.data?.cached);
  if (r?.data?.tree) {
    const t = r.data.tree;
    console.log('virtual_root.name:', t.name, ' children.length:', t.children?.length);
    (t.children || []).forEach((sec, si) => {
      console.log(`  section[${si}] name="${sec.name}" _synthetic=${sec._synthetic} children.length=${sec.children?.length}`);
      (sec.children || []).slice(0, 5).forEach((ch, ci) => {
        console.log(`    child[${ci}] name="${ch.name}" key=${ch.key} nc=${ch.children?.length}`);
      });
      if ((sec.children?.length || 0) > 5)
        console.log(`    ... (${sec.children.length - 5} more not shown)`);
    });
  } else {
    console.log('tree is null/undefined, error:', r?.error);
  }
  console.groupEnd();
  // ────────────────────────────────────────────────────────────────────────────

  // Backend 返回 r.data.tree = av.RootNode（VisMockup 内部虚拟根，不显示）
  // 其 children 是实际的顶层产品组件，支持多个根节点
  if (!r?.success || !r.data?.tree) {
    _cmdShow(`VM 结构同步失败 · ${timer.elapsedSeconds()}s`, 'err');
    $('visTreeEmpty').textContent = r?.error || '加载失败，请确认 VisMockup 已打开文件';
    $('visTreeEmpty').classList.remove('hidden');
    return false;
  }

  _renderVisTreeSnapshot(r.data.tree, r.data.cacheState);
  _cmdShow(`VM 结构同步完成 · ${timer.elapsedSeconds()}s`, 'ok');
  $('plmxmlSourceBanner')?.classList.add('hidden');
  return true;
}

function _renderVisTreeSnapshot(virtualRoot, cacheState = 'verified') {
  _simulationDebug('ui_tree_rendered',{cache_state:cacheState});
  $('visTreeEmpty').classList.add('hidden');
  _visTreeSnapshot = virtualRoot;
  const roots = virtualRoot.children || [];

  if (roots.length === 0 && !virtualRoot.has_more) {
    $('visTreeEmpty').textContent = '结构树为空';
    $('visTreeEmpty').classList.remove('hidden');
    return;
  }

  // 新的完整结果到达前保留上一棵树；成功后再原子替换 DOM。
  $('visTreeBody').innerHTML = '';
  _visNodeMap = {};
  _visExpandedKeys.clear();
  const frag = document.createDocumentFragment();
  roots.forEach(rootNode => frag.appendChild(_buildVisNodeEl(rootNode, 0)));
  // 若 virtualRoot.has_more（深度限制导致根级子节点未完全加载，理论上极少发生）
  if (virtualRoot.has_more) {
    const moreRow = document.createElement('div');
    moreRow.className = 'cs-vis-more-row';
    moreRow.style.paddingLeft = '22px';
    moreRow.textContent = '⋯ 部分根节点未加载，点击强制刷新';
    moreRow.addEventListener('click', () => _loadVisTree(true));
    frag.appendChild(moreRow);
  }
  $('visTreeBody').appendChild(frag);
  _visTreeLoaded = true;
  _updateVisVisibilityControls();
  _updateAlternateVisibilityControls();
  _refreshBopVmBindingDraft();

  // 顶层节点默认展开（模型 section 展开，AH section 视内容而定）
  roots.forEach(rootNode => {
    if (!rootNode._synthetic) return;
    const entry = _visNodeMap[rootNode.name + '__section__'];
    if (!entry) return;
    const row = entry.nodeEl.parentElement;
    if (!row) return;
    const childWrap = row.querySelector('.cs-vis-children');
    const toggle    = entry.nodeEl.querySelector('.cs-vis-toggle');
    if (childWrap && (childWrap.children.length > 0 || rootNode.name === '模型')) {
      childWrap.style.display = '';
      if (toggle) toggle.textContent = '▼';
    }
  });

  if (cacheState === 'verifying') {
    _cmdShow('已显示上次完整结构；点击刷新校验当前模型');
  }
}

/** 构建 AI00 合成分区节点（模型 / 备选层次结构）*/
function _buildVisSectionEl(node) {
  const section = document.createElement('div');
  section.className = 'cs-vis-section';

  // ── 分区标题行 ──
  const hdr = document.createElement('div');
  hdr.className = 'cs-vis-section-hdr';

  const toggle = document.createElement('span');
  toggle.className = 'cs-vis-toggle';
  toggle.textContent = '▶';
  hdr.appendChild(toggle);

  const label = document.createElement('span');
  label.className = 'cs-vis-section-label';
  const icon = document.createElement('span');
  icon.className = `cs-vis-type-icon ${node.name === '备选层次结构' ? 'cs-vis-type-alt' : 'cs-vis-type-model'}`;
  icon.textContent = node.name === '备选层次结构' ? '◇' : '▧';
  hdr.appendChild(icon);
  label.textContent = node.name;
  hdr.appendChild(label);

  // 子节点计数徽标
  const cnt = node.children?.length || 0;
  const badge = document.createElement('span');
  badge.className = 'cs-vis-section-count';
  badge.textContent = cnt > 0 ? cnt : (node.name === '备选层次结构' ? '空' : '0');
  badge.title = cnt > 0 ? `${cnt} 个节点` : (node.name === '备选层次结构' ? '暂无备选层次结构（BOP 数据将在此显示）' : '');
  hdr.appendChild(badge);

  section.appendChild(hdr);

  // ── 子节点容器 ──
  const childWrap = document.createElement('div');
  childWrap.className = 'cs-vis-children';
  childWrap.style.display = 'none';

  if (cnt > 0) {
    node.children.forEach(child => childWrap.appendChild(_buildVisNodeEl(child, 1)));
  } else if (node.name === '备选层次结构') {
    const placeholder = document.createElement('div');
    placeholder.className = 'cs-vis-section-empty';
    placeholder.textContent = '暂无备选层次结构';
    childWrap.appendChild(placeholder);
  }
  section.appendChild(childWrap);

  // ── 折叠 / 展开 ──
  hdr.addEventListener('click', () => {
    const isOpen = childWrap.style.display !== 'none';
    childWrap.style.display = isOpen ? 'none' : '';
    toggle.textContent = isOpen ? '▶' : '▼';
  });

  // 存入 _visNodeMap 以便 default-expand 代码查找
  _visNodeMap[node.name + '__section__'] = { node, nodeEl: hdr, visibilityEl: null };

  return section;
}

/** 构建一个节点 DOM 元素（含子节点容器）*/
function _buildVisNodeEl(node, depth) {
  // 合成分区节点（模型 / 备选层次结构）：渲染为可折叠分区标题
  if (node._synthetic) {
    return _buildVisSectionEl(node);
  }

  const row = document.createElement('div');
  row.className = 'cs-vis-row';
  row.dataset.key   = node.key || '';
  row.dataset.depth = depth;
  if (node.occurrence_gid && /^\d+$/.test(String(node.occurrence_gid))) {
    row.dataset.occurrenceGid = String(node.occurrence_gid);
    row.draggable = true;
  }

  const hasChildren = node.children?.length > 0 || node.has_more;
  const indent = depth * 16 + 6;

  // ── 节点行 ──
  const nodeEl = document.createElement('div');
  nodeEl.className = 'cs-vis-node' + (node.visible === false ? ' cs-vis-hidden' : '');
  nodeEl.style.paddingLeft = indent + 'px';

  // toggle arrow
  const toggle = document.createElement('span');
  toggle.className = 'cs-vis-toggle' + (hasChildren ? '' : ' cs-vis-leaf');
  toggle.textContent = hasChildren ? '▶' : '·';
  nodeEl.appendChild(toggle);

  // VisMockup-style visibility checkbox. It never selects or expands the row.
  const visibilityEl = document.createElement('input');
  visibilityEl.type = 'checkbox';
  visibilityEl.className = 'cs-vis-visibility';
  const visibilityState = globalThis.AI00ModelDocumentCollection?.deriveVisibilityState?.(node)
    || { checked: node.visible === true, indeterminate: false, disabled: !node.key || typeof node.visible !== 'boolean' };
  visibilityEl.checked = visibilityState.checked;
  visibilityEl.indeterminate = visibilityState.indeterminate;
  visibilityEl.disabled = visibilityState.disabled || !_vmConnected;
  visibilityEl.setAttribute('aria-label', `${node.name || '节点'} 显隐`);
  visibilityEl.title = visibilityState.disabled ? '该节点尚未同步或缺少可控映射' : '切换显示/隐藏';
  visibilityEl.addEventListener('click', async e => {
    e.stopPropagation();
    e.preventDefault();
    if (!node.key) return;
    const current = globalThis.AI00ModelDocumentCollection?.deriveVisibilityState?.(node);
    const result = await _visNodeAction(node.key, (current?.checked ?? node.visible === true) ? 'hide' : 'show');
    if (node.children?.length && result?.ok) {
      const refreshed = await _loadVisTree(true);
      if (!refreshed) {
        const markUnknown = value => {
          value.visible = null;
          (value.children || []).forEach(markUnknown);
        };
        markUnknown(node);
      }
    }
    _updateVisVisibilityControls();
  });
  nodeEl.appendChild(visibilityEl);

  const typeIcon = document.createElement('span');
  typeIcon.className = `cs-vis-type-icon ${node.node_type === 'alternate_hierarchy' ? 'cs-vis-type-alt' : 'cs-vis-type-model'}`;
  typeIcon.textContent = node.node_type === 'alternate_hierarchy' ? '◇' : '▧';
  typeIcon.setAttribute('aria-hidden', 'true');
  nodeEl.appendChild(typeIcon);

  // label
  const label = document.createElement('span');
  label.className = 'cs-vis-label';
  label.textContent = node.name;
  label.title = node.catia_name ? `${node.name}\n${node.catia_name}` : node.name;
  nodeEl.appendChild(label);

  // catia occurrence name (secondary line)
  if (node.catia_name) {
    const sub = document.createElement('span');
    sub.className = 'cs-vis-catia';
    sub.textContent = node.catia_name;
    nodeEl.appendChild(sub);
  }

  row.appendChild(nodeEl);

  // ── 子节点容器 ──
  const childWrap = document.createElement('div');
  childWrap.className = 'cs-vis-children';
  childWrap.style.display = 'none';

  // pre-populate already-loaded children
  if (node.children?.length > 0) {
    node.children.forEach(child => childWrap.appendChild(_buildVisNodeEl(child, depth + 1)));
  }
  if (node.has_more) {
    childWrap.appendChild(_makeVisMoreRow(node, depth + 1));
  }
  row.appendChild(childWrap);

  // ── 事件：展开/折叠 ──
  if (hasChildren) {
    toggle.addEventListener('click', e => {
      e.stopPropagation();
      _toggleVisExpand(node, depth, toggle, childWrap);
    });
    nodeEl.addEventListener('dblclick', e => {
      e.stopPropagation();
      _toggleVisExpand(node, depth, toggle, childWrap);
    });
  }

  // ── 事件：单击高亮 ──
  nodeEl.addEventListener('click', () => {
    $('visTreeBody').querySelectorAll('.cs-vis-node.cs-vis-active')
      .forEach(n => n.classList.remove('cs-vis-active'));
    nodeEl.classList.add('cs-vis-active');
    if (node.key) _visNodeAction(node.key, 'highlight');
    _showVisDetail(node);
  });

  // ── 事件：右键菜单 ──
  nodeEl.addEventListener('contextmenu', e => {
    e.preventDefault();
    _showVisCtxMenu(e, node);
  });

  // 存入 map 供后续更新
  if (node.key) _visNodeMap[node.key] = { node, nodeEl, visibilityEl };

  return row;
}

/** 展开 / 折叠一个节点 */
async function _toggleVisExpand(node, depth, toggleEl, childWrap) {
  const isOpen = childWrap.style.display !== 'none';
  if (isOpen) {
    childWrap.style.display = 'none';
    toggleEl.textContent = '▶';
    _visExpandedKeys.delete(node.key);
    return;
  }

  // 展开
  childWrap.style.display = '';
  toggleEl.textContent = '▼';
  _visExpandedKeys.add(node.key);

  // 若子节点尚未加载，通过 bridge 惰性加载
  if (childWrap.children.length === 0 ||
      (childWrap.children.length === 1 && childWrap.firstChild?.classList?.contains('cs-vis-more-row'))) {
    const placeholder = document.createElement('div');
    placeholder.className = 'cs-vis-more-row';
    placeholder.style.paddingLeft = (depth + 1) * 16 + 22 + 'px';
    placeholder.textContent = '加载中…';
    childWrap.innerHTML = '';
    childWrap.appendChild(placeholder);

    const r = await _bridge('vis_mockup', 'get_vis_node_children', { node_key: node.key });
    if (r?.success) {
      _applyVisChildren(node, r.data.children, childWrap, depth + 1);
    } else {
      childWrap.innerHTML = '';
      const err = document.createElement('div');
      err.className = 'cs-vis-more-row';
      err.style.paddingLeft = (depth + 1) * 16 + 22 + 'px';
      err.textContent = '加载失败';
      childWrap.appendChild(err);
    }
  }
}

function _applyVisChildren(node, children, childWrap, depth) {
  node.children = Array.isArray(children) ? children : [];
  node.has_more = false;
  childWrap.innerHTML = '';
  node.children.forEach(child => childWrap.appendChild(_buildVisNodeEl(child, depth)));
}

/** "展开更多" 占位行（depth limit 超出时） */
function _makeVisMoreRow(node, depth) {
  const el = document.createElement('div');
  el.className = 'cs-vis-more-row';
  el.style.paddingLeft = depth * 16 + 22 + 'px';
  el.textContent = '⋯ 点击加载';
  el.addEventListener('click', async () => {
    el.textContent = '加载中…';
    const r = await _bridge('vis_mockup', 'get_vis_node_children', { node_key: node.key });
    if (r?.success) {
      const parent = el.parentElement;
      if (parent) _applyVisChildren(node, r.data.children, parent, depth);
    } else {
      el.textContent = '加载失败，点击重试';
    }
  });
  return el;
}

/** 通过受治理 Connector 执行节点操作，并更新显隐复选框 */
function _updateVisVisibilityControls() {
  if (!_visTreeSnapshot) return;
  const visit = node => {
    const children = node.children || [];
    const counts = children.length
      ? children.map(visit).reduce((total, child) => ({
        visible: total.visible + child.visible,
        hidden: total.hidden + child.hidden,
        unknown: total.unknown + child.unknown,
      }), { visible: 0, hidden: 0, unknown: 0 })
      : { visible: node.visible === true && node.key ? 1 : 0,
          hidden: node.visible === false && node.key ? 1 : 0,
          unknown: node.visible == null && node.key ? 1 : 0 };
    if (node.has_more) counts.unknown++;
    const entry = node.key && _visNodeMap[node.key];
    if (entry?.visibilityEl) {
      entry.visibilityEl.checked = counts.visible > 0 && counts.hidden === 0 && counts.unknown === 0;
      entry.visibilityEl.indeterminate = counts.visible > 0 && counts.hidden > 0 && counts.unknown === 0;
      entry.visibilityEl.disabled = !_vmConnected || counts.unknown > 0 || counts.visible + counts.hidden === 0;
    }
    return counts;
  };
  visit(_visTreeSnapshot);
}

function _runtimeVisNodePath(nodeKey) {
  const path = [];
  const visit = node => {
    if (!node || path.length) return false;
    if (String(node.key || '') === String(nodeKey)) {
      path.push(node.key);
      return true;
    }
    for (const child of node.children || []) {
      if (visit(child)) {
        if (node.key) path.unshift(node.key);
        return true;
      }
    }
    return false;
  };
  visit(_visTreeSnapshot);
  return path.filter(key => String(key).startsWith('tc:'));
}

function _teamcenterLoadedPathForRuntimeNode(nodes, nodeKey) {
  const exact = (Array.isArray(nodes) ? nodes : []).find(node => {
    if (String(node?.node_key || '') === String(nodeKey)) return true;
    if (String(node?.control_key || '') === String(nodeKey)) return true;
    const path = node?.occurrence_path;
    const occurrenceUid = Array.isArray(path) && path.length ? path.at(-1)?.occurrence_uid : '';
    return occurrenceUid && `tc:${occurrenceUid}` === String(nodeKey);
  });
  return Array.isArray(exact?.occurrence_path) ? exact.occurrence_path : null;
}

async function _teamcenterOccurrencePathForRuntimeNode(nodeKey) {
  const documents = _modelDocumentCollection?.state?.documents || [];
  const candidates = [
    ...documents.filter(item => item?.source_kind === 'teamcenter_online' && item?.role === 'primary'),
    ...documents.filter(item => item?.source_kind === 'teamcenter_online' && item?.role !== 'primary'),
  ];
  for (const document of candidates) {
    const tree = document.product_tree;
    let path = window.AI00VmSnapshotTree?.teamcenterOccurrencePathForNode?.(tree?.nodes, nodeKey);
    if (path) return path;
    const runtimePath = _runtimeVisNodePath(nodeKey);
    if (!runtimePath.length || !tree || !Array.isArray(tree.nodes)
        || typeof window.AI00TeamcenterOnlineSource?.readChildren !== 'function') continue;
    let parentPath = [];
    for (const runtimeKey of runtimePath) {
      path = _teamcenterLoadedPathForRuntimeNode(tree.nodes, runtimeKey);
      if (path === null) {
        await window.AI00TeamcenterOnlineSource.readChildren(
          _requestVisMockupCommand, document, tree, parentPath, { isCurrent: () => _vmConnected },
        );
        path = _teamcenterLoadedPathForRuntimeNode(tree.nodes, runtimeKey);
      }
      if (path === null) break;
      parentPath = path;
    }
    path = window.AI00VmSnapshotTree?.teamcenterOccurrencePathForNode?.(tree.nodes, nodeKey);
    if (path) return path;
  }
  return null;
}

async function _visNodeAction(nodeKey, action) {
  if (!nodeKey || !_vmConnected) return { ok: false };
  try {
    const local=window._localViewerInteraction?.();
    let data;
    if(local){
      const document=_modelDocumentCollection?.state?.documents?.find(d=>String(d.document_gid)===local.scope?.document_gid);
      const matches=(document?.product_tree?.nodes||[]).filter(n=>String(n.node_key)===String(nodeKey)||String(n.control_key)===String(nodeKey)
        ||(n.occurrence_path?.length&&`tc:${n.occurrence_path.at(-1).occurrence_uid}`===String(nodeKey)));
      if(matches.length!==1)throw Error('unmapped');
      data=await local.execute({source_nodes:[window.AI00ViewerInteraction.sourceDescriptor(document,matches[0])],action});
    }else{
    const capabilityId = ['show', 'hide', 'toggle_visible', 'isolate'].includes(action)
      ? 'simulation.vismockup.node.visibility.change.request'
      : 'simulation.vismockup.node.selection.change.request';
    const payload = { node_key: nodeKey, action };
    const occurrencePath = await _teamcenterOccurrencePathForRuntimeNode(nodeKey);
    if (occurrencePath) payload.occurrence_path = occurrencePath;
    const outcome = await _requestVisMockupCommand(
      capabilityId, payload, { confirmation: false },
    );
    data = outcome?.steps?.at(-1)?.result || {};
    }
    if (data.visible !== undefined) {
      const entry = _visNodeMap[nodeKey];
      if (entry) {
        const v = data.visible;
        entry.visibilityEl.checked = v;
        entry.visibilityEl.indeterminate = false;
        entry.nodeEl.classList.toggle('cs-vis-hidden', !v);
        entry.node.visible = v;
      }
    }
    _updateVisVisibilityControls();
    _updateAlternateVisibilityControls();
    return { ok: !['show', 'hide'].includes(action) || data.visible === (action === 'show'), visible: data.visible };
  } catch (error) {
    _cmdShow(error?.message || `${action} 失败`, 'err');
    return { ok: false, error };
  }
}

/** 右键上下文菜单 */
function _showVisCtxMenu(e, node) {
  _hideVisCtxMenu();
  const menu = document.createElement('div');
  menu.className = 'cs-ctx-menu';
  _visCtxMenu = menu;

  const items = [
    { label: '高亮',     action: 'highlight' },
    { label: '取消高亮', action: 'unhighlight' },
    { sep: true },
    { label: '显示',     action: 'show' },
    { label: '隐藏',     action: 'hide' },
    { label: '单独显示', action: 'isolate' },
    { sep: true },
    { label: '选中',     action: 'select' },
    { label: '取消选中', action: 'deselect' },
    { sep: true },
    { label: '加载此节点几何…', action: '_load_geometry' },
    { label: '查看元数据…', action: '_metadata' },
  ];

  items.forEach(it => {
    if (it.sep) {
      const sep = document.createElement('div');
      sep.className = 'cs-ctx-sep';
      menu.appendChild(sep);
    } else {
      const btn = document.createElement('div');
      btn.className = 'cs-ctx-item';
      btn.textContent = it.label;
      btn.addEventListener('click', () => {
        _hideVisCtxMenu();
        if (it.action === '_metadata') {
          _showNodeMetadata(node);
        } else if (it.action === '_load_geometry') {
          _loadNodeGeometry(node.key);
        } else if (node.key) {
          _visNodeAction(node.key, it.action);
        }
      });
      menu.appendChild(btn);
    }
  });

  document.body.appendChild(menu);
  const mx = Math.min(e.clientX, window.innerWidth  - menu.offsetWidth  - 8);
  const my = Math.min(e.clientY, window.innerHeight - menu.offsetHeight - 8);
  menu.style.left = mx + 'px';
  menu.style.top  = my + 'px';

  setTimeout(() => document.addEventListener('click', _hideVisCtxMenu, { once: true }), 0);
}

function _hideVisCtxMenu() {
  _visCtxMenu?.remove();
  _visCtxMenu = null;
}

/** 元数据弹窗：加载节点完整信息并分区展示 */
async function _showNodeMetadata(node) {
  if (!node.key) return;
  document.getElementById('visMetaPopup')?.remove();

  const overlay = document.createElement('div');
  overlay.id = 'visMetaPopup';
  overlay.className = 'cs-meta-overlay';
  overlay.innerHTML = `
    <div class="cs-meta-dialog">
      <div class="cs-meta-title">
        <span>${_esc(node.name)}</span>
        <button class="cs-meta-close" title="关闭">✕</button>
      </div>
      ${node.catia_name ? `<div class="cs-meta-catia">${_esc(node.catia_name)}</div>` : ''}
      <div class="cs-meta-body" id="visMetaBody">
        <span style="color:var(--text-muted);font-size:12px">加载中…</span>
      </div>
    </div>`;
  document.body.appendChild(overlay);
  overlay.querySelector('.cs-meta-close').addEventListener('click', () => overlay.remove());
  overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });

  const r = await _bridge('vis_mockup', 'get_node_metadata', { node_key: node.key });
  const body = document.getElementById('visMetaBody');
  if (!body) return;

  if (!r?.success) {
    body.innerHTML = `<span style="color:var(--red)">${_esc(r?.error || '获取失败')}</span>`;
    return;
  }

  const d = r.data;
  const sections = [];

  // ── 固定属性 ──
  const fixedKeys = ['PrintableName','Fullname','DataStoreName','DataStoreLocation','CADID','IsPart','IsLoaded'];
  const fixed = fixedKeys.filter(k => d[k] != null && d[k] !== '').map(k =>
    `<div class="cs-meta-row"><span class="cs-meta-key">${_esc(k)}</span><span class="cs-meta-val">${_esc(String(d[k]))}</span></div>`
  ).join('');
  if (fixed) sections.push(`<div class="cs-meta-section-hdr">节点属性</div>${fixed}`);

  // ── 变换矩阵 ──
  for (const [label, key] of [['全局变换矩阵','GlobalTransform'],['局部变换矩阵','LocalTransform']]) {
    const m = d[key];
    if (!m) continue;
    if (typeof m === 'string') {
      sections.push(`<div class="cs-meta-section-hdr">${label}</div>
        <div class="cs-meta-row"><span class="cs-meta-key">状态</span><span class="cs-meta-val">${_esc(m)}</span></div>`);
    } else if (Array.isArray(m) && m.length >= 12) {
      // 格式化为 4×4 矩阵
      const fmt = n => (typeof n === 'number' ? n.toFixed(6) : String(n)).padStart(14);
      const rows = [0,4,8,12].map(i =>
        `<span class="cs-mat-row">${[0,1,2,3].map(j => fmt(m[i+j])).join('  ')}</span>`
      ).join('\n');
      // 平移向量单独标注
      const tx = m[12], ty = m[13], tz = m[14];
      sections.push(`<div class="cs-meta-section-hdr">${label}</div>
        <div class="cs-meta-matrix">${rows}</div>
        <div class="cs-meta-row" style="margin-top:4px">
          <span class="cs-meta-key">平移 (x,y,z)</span>
          <span class="cs-meta-val">${typeof tx==='number'?tx.toFixed(4):tx},  ${typeof ty==='number'?ty.toFixed(4):ty},  ${typeof tz==='number'?tz.toFixed(4):tz}</span>
        </div>`);
    }
  }

  // ── PLM 元数据（MetaDataProperties）──
  const meta = d['_metadata'] || {};
  const metaKeys = Object.keys(meta).sort((a, b) => {
    const pri = ['catiaoccurrencename','__PLM_INST_UID','__PLM_CLONE_STABLE_INST_UID','__PLM_INST_TH_UID'];
    const ia = pri.indexOf(a), ib = pri.indexOf(b);
    if (ia >= 0 && ib >= 0) return ia - ib;
    if (ia >= 0) return -1;
    if (ib >= 0) return 1;
    return a.localeCompare(b);
  });
  if (metaKeys.length > 0) {
    const rows = metaKeys.map(k =>
      `<div class="cs-meta-row"><span class="cs-meta-key">${_esc(k)}</span><span class="cs-meta-val">${_esc(meta[k])}</span></div>`
    ).join('');
    sections.push(`<div class="cs-meta-section-hdr">MetaDataProperties (${metaKeys.length})</div>${rows}`);
  }

  // ── 几何数据（按需加载，避免自动触发 JT shape 载入）──
  const geoId = `visGeo_${(node.key || 'x').replace(/[^a-z0-9]/gi, '_')}`;
  sections.push(`<div class="cs-meta-section-hdr">几何数据（JT Shape）</div>
    <div id="${geoId}">
      <div class="cs-meta-row" style="gap:8px">
        <button class="cs-btn cs-btn-xs" onclick="window._loadNodeGeoInline('${node.key}','${geoId}')">加载几何数据</button>
        <span style="font-size:11px;color:var(--text-muted)">触发后 VisMockup 将载入该节点 JT shape</span>
      </div>
    </div>`);

  body.innerHTML = sections.length
    ? sections.join('')
    : `<span style="color:var(--text-muted);font-size:12px">暂无可读数据</span>`;
}

/** 全量同步显隐状态（全显/全隐命令后批量更新复选框）*/
function _syncAllVisibility(visible) {
  for (const [key, entry] of Object.entries(_visNodeMap)) {
    if (!entry.visibilityEl) continue;
    entry.visibilityEl.checked = visible;
    entry.visibilityEl.indeterminate = false;
    entry.nodeEl.classList.toggle('cs-vis-hidden', !visible);
    if (entry.node) entry.node.visible = visible;
  }
  _updateVisVisibilityControls();
  _updateAlternateVisibilityControls();
}

// ── utils ─────────────────────────────────────────────────────────────────────

/** 后台触发 catia 全树扫描，静默完成（不阻塞 UI） */
async function _scanCatiaMap() {
  if (!_vmConnected) return;
  const r = await _bridge('vis_mockup', 'scan_vis_catia_map');
  if (r?.success) {
    _catiaScanDone = true;
    _cmdShow(`VM 扫描完成：${r.data.count} 个零件节点`, 'ok');
    _refreshVmMatchCounts();
  }
}

/** 单节点几何加载：显示在 cmdResult 条 */
async function _loadNodeGeometry(nodeKey) {
  if (!nodeKey || !_vmConnected) { _cmdShow('未连接 VisMockup', 'err'); return; }
  _cmdShow('加载节点几何中…');
  const r = await _bridge('vis_mockup', 'get_node_geometry', { node_key: nodeKey });
  if (!r?.success) { _cmdShow(r?.error || '加载失败', 'err'); return; }
  const d = r.data;
  const parts = [];
  if (d.bbox && typeof d.bbox === 'object' && d.bbox.min) {
    const fv = v => Array.isArray(v) ? v.map(n => typeof n === 'number' ? n.toFixed(3) : n).join(', ') : String(v);
    parts.push(`BBox [${fv(d.bbox.min)}]~[${fv(d.bbox.max)}]`);
  }
  if (d.area   != null) parts.push(`面积:${d.area.toFixed(4)}`);
  if (d.volume != null) parts.push(`体积:${d.volume.toFixed(4)}`);
  _cmdShow(parts.join(' | ') || '已加载（无几何数据）', 'ok');
}

/** 元数据弹窗内按需加载几何数据区块 */
window._loadNodeGeoInline = async (nodeKey, sectionId) => {
  const el = document.getElementById(sectionId);
  if (!el) return;
  el.innerHTML = '<div class="cs-meta-row" style="color:var(--text-muted);font-size:12px">加载中…</div>';
  const r = await _bridge('vis_mockup', 'get_node_geometry', { node_key: nodeKey });
  if (!r?.success) {
    el.innerHTML = `<div class="cs-meta-row"><span style="color:var(--red)">${_esc(r?.error || '加载失败')}</span></div>`;
    return;
  }
  const d = r.data;
  const rows = [];
  if (d.bbox && typeof d.bbox === 'object' && d.bbox.min) {
    const fv = v => Array.isArray(v) ? v.map(n => typeof n === 'number' ? n.toFixed(4) : n).join(', ') : String(v);
    rows.push(`<div class="cs-meta-row"><span class="cs-meta-key">BBox Min</span><span class="cs-meta-val">${_esc(fv(d.bbox.min))}</span></div>`);
    rows.push(`<div class="cs-meta-row"><span class="cs-meta-key">BBox Max</span><span class="cs-meta-val">${_esc(fv(d.bbox.max))}</span></div>`);
  } else if (d.bbox) {
    rows.push(`<div class="cs-meta-row"><span class="cs-meta-key">BBox</span><span class="cs-meta-val">${_esc(String(d.bbox))}</span></div>`);
  }
  if (d.area   != null) rows.push(`<div class="cs-meta-row"><span class="cs-meta-key">面积</span><span class="cs-meta-val">${d.area.toFixed(6)}</span></div>`);
  if (d.volume != null) rows.push(`<div class="cs-meta-row"><span class="cs-meta-key">体积</span><span class="cs-meta-val">${d.volume.toFixed(6)}</span></div>`);
  el.innerHTML = rows.length
    ? rows.join('')
    : '<div class="cs-meta-row" style="color:var(--text-muted);font-size:12px">暂无几何数据</div>';
};

function _esc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── AI00 Connector 受治理环境与截图流程 ──────────────────────────────────────
let _governedCapture = null;
let _vmVersioning = null;
let _vmVersioningSnapshotRequest = '';
let _vmManualCapture = false;
let _connectorOnboarding = null;
let _boundConnectorId = '';
let _governedCaptureScopeLineGid = null;
let _governedCaptureProgressCb = null;
let _governedCaptureBopVersionGid = null;
let _governedCaptureReportedOps = new Set();
let _governedCaptureSourceKey = '';
let _alternateCaptureSelection = null;
let _governedCaptureSource = null;
let _governedCaptureSourceLoading = false;

function _renderGovernedCapture(state) {
  const progress = $('connectorProgress');
  const problems = $('connectorProblems');
  if (!progress || !problems) return;
  if (state.bindingDraft) {
    _bopVmBindingDraft = state.bindingDraft;
    const labels = { parts: '零件精确', vpps: 'VPPS 精确', structure_only: '仅结构' };
    const status = $('bindingDraftStatus');
    if (status) {
      status.textContent = `已固化初版：${labels[state.bindingDraft.mode] || state.bindingDraft.mode} · 自动 ${state.bindingDraft.auto_count} · 待复核 ${state.bindingDraft.review_count}`;
      status.dataset.state = state.bindingDraft.review_count ? 'review' : 'ready';
    }
  }
  const issues = state.preflight?.problems || [];
  problems.classList.toggle('hidden', issues.length === 0 && !state.error);
  const errorLabels = {
    simulation_capture_environment_upgrade_required: '截图环境版本较旧，请更新本机 Connector 后重新搭建环境。',
    capture_run_active: '当前任务尚未结束，请勿重复启动或切换线体。',
    capture_target_not_blue_or_occluded: '当前工序未通过蓝色像素验证，未隐藏零件。请检查映射、遮挡及视角。',
    capture_empty_or_clipped_scene: '截图场景为空或被裁切，请检查模型是否加载完成。',
  };
  problems.textContent = state.error
    ? `${state.error.code}: ${errorLabels[state.error.code] || state.error.message}`
    : issues.map(item => `${item.code}（期望 ${item.expected ?? '—'}，实际 ${item.actual ?? '—'}）`).join('\n');
  const run = state.captureRun;
  for (const step of run?.steps || []) {
    if (!step.artifact_attached || _governedCaptureReportedOps.has(step.operation_id)) continue;
    _governedCaptureReportedOps.add(step.operation_id);
    const progressCallback = _governedCaptureProgressCb;
    const bopVersionGid = _governedCaptureBopVersionGid;
    Promise.resolve().then(() => progressCallback?.({
      bop_entry_gid: step.operation_id, bop_version_gid: bopVersionGid,
      title: _bopEntryIndex[step.operation_id]?.title || step.operation_id,
    }, step.artifact_ref)).catch(error => {
      _governedCaptureReportedOps.delete(step.operation_id);
      _showBanner(`截图已关联，但工序卡刷新失败：${error.message}`, 'error');
    });
  }
  if (!run) {
    progress.textContent = state.materializationRun
      ? `环境构建已提交（${state.materializationRun.status}）。构建完成后再次点击“开始截图”；服务端会在完成前拒绝截图。`
      : (state.preflight?.compatible ? 'Connector 预检通过，可以开始。' : '尚未通过 Connector 预检。');
  } else {
    const rows = (run.steps || []).map(step =>
      `${_bopEntryIndex[step.operation_id]?.title || step.operation_id}  ·  ${step.status}  ·  attempt ${step.attempt}`
    );
    progress.textContent = [`运行 ${run.capture_run_id}：${run.status}`, ...rows].join('\n');
  }
  $('connectorStart').disabled = !_governedCapture?.canStartCapture();
  $('connectorCompose').disabled = Boolean(_governedCaptureSourceLoading || !_governedCaptureSource?.execution_plan_ref || state.busy || (run && !['completed', 'failed', 'partial', 'cancelled', 'outcome_unknown'].includes(run.status)));
  $('connectorPreflight').disabled = !state.environmentId;
  $('connectorCancel').disabled = !run || ['completed', 'failed', 'partial', 'cancelled', 'outcome_unknown'].includes(run.status);
}

function _renderConnectorOnboarding(state) {
  const title = $('connectorBindingTitle');
  const detail = $('connectorBindingDetail');
  if (!title || !detail) return;
  const connect = $('connectorConnect');
  const approve = $('connectorApprove');
  const cancel = $('connectorPairCancel');
  connect.classList.toggle('hidden', !['unbound', 'cancelled', 'expired', 'error', 'waiting_for_connector', 'bound'].includes(state.kind));
  connect.textContent = state.kind === 'waiting_for_connector'
    ? '打开 Connector'
    : (state.kind === 'bound' ? '重新连接本机' : '连接本机');
  approve.classList.toggle('hidden', state.kind !== 'awaiting_confirmation');
  cancel.classList.toggle('hidden', !['waiting_for_connector', 'awaiting_confirmation', 'activating'].includes(state.kind));
  const labels = {
    loading: '正在检查本机 Connector…', unbound: '尚未绑定本机 Connector',
    waiting_for_connector: '正在唤起已安装的 Connector…',
    awaiting_confirmation: '请确认这台工作站', activating: '正在安全保存并激活…',
    bound: '本机 Connector 已绑定', cancelled: '连接已取消', expired: '连接请求已过期',
    error: 'Connector 连接失败',
  };
  title.textContent = labels[state.kind] || 'Connector 状态未知';
  detail.textContent = state.kind === 'awaiting_confirmation'
    ? `${state.deviceName || '未知设备'} · ${state.windowsUser || '未知用户'} · ${state.runtimeVersion || '未知版本'}`
    : (state.error?.message || (state.kind === 'bound'
      ? '已自动选择当前账号绑定的 Connector。' : '无需输入配对码或设备 ID。'));
  if (state.kind === 'bound') {
    _boundConnectorId = state.connectorId;
    if (_governedCapture?.state?.environmentId)
      _governedCapture.selectConnector(_boundConnectorId).catch(() => {});
  }
}

async function _openGovernedCapture(lineGid = null, progressCb = null) {
  if (_governedCaptureSourceLoading) return;
  const library = window.SimulationCaptureWorkflow;
  const selected = typeof lineGid === 'string' ? lineGid
    : ($('bopTreeBody')?.querySelector('.cs-bop-node.active')?.closest('.cs-bop-row')?.dataset?.gid || _dpBopSelGid);
  let source;
  if (typeof lineGid !== 'string' && _alternateCaptureSelection) {
    const selection = _alternateCaptureSelection;
    const hierarchy = _modelDocumentCollection?.state.hierarchies.find(item => item.hierarchy_gid === selection.hierarchy_gid);
    if (selection.workspace_gid !== _currentSimulationWorkspace()?.workspace_gid || hierarchy?.hierarchy_gid !== _modelDocumentCollection?.state.selectedHierarchyGid) {
      return _showBanner('仿真环境或备选层次已切换，请重新选择门线', 'error');
    }
    source = library?.resolveHierarchyCaptureSource(hierarchy, selection.node_gid);
    lineGid = source?.line_gid;
  } else {
    lineGid = library?.resolveCaptureLine(_bopEntryIndex, selected);
    source = { version_gid: _selectedBopGid, line_gid: lineGid };
  }
  if (!lineGid) return _showBanner('请先在 BOP 中选择需要逆序截图的线体或其下的工位/工序', 'error');
  const sourceKey = `${source.workspace_gid || 'bop'}:${source.hierarchy_gid || ''}:${source.version_gid}:${lineGid}`;
  if (_governedCaptureSourceKey !== sourceKey) {
    try { _governedCapture?.setEnvironment('', 0); }
    catch (_) { return _showBanner('当前截图尚未结束，请先取消或等待完成再切换线体', 'error'); }
    _governedCaptureSourceKey = sourceKey;
  }
  _governedCaptureScopeLineGid = lineGid;
  _governedCaptureSource = source;
  _governedCaptureProgressCb = typeof progressCb === 'function' ? progressCb : null;
  _governedCaptureBopVersionGid = source.version_gid;
  _governedCaptureReportedOps = new Set();
  $('connectorSource').textContent = `${source.name || '选中线体'} ${lineGid} · BOP ${source.version_gid} · 正在核对已发布执行结构`;
  $('connectorCaptureOverlay').classList.remove('hidden');
  _governedCaptureSourceLoading = true;
  $('connectorCompose').disabled = true;
  try {
    const reference = await library.readCaptureExecutionSource(_invokeCapability, source);
    if (source.workspace_gid && (source.workspace_gid !== _currentSimulationWorkspace()?.workspace_gid
        || source.hierarchy_gid !== _modelDocumentCollection?.state.selectedHierarchyGid)) throw Error('capture_source_changed');
    _governedCaptureSource = { ...source, execution_plan_ref: reference };
    $('connectorSource').textContent = `${source.name || '选中线体'} ${lineGid} · BOP ${reference.version_gid} · revision ${reference.revision} · ${reference.content_hash}`;
  } catch (error) {
    const message = error.code === 'version_not_published' || error.message === 'version_not_published'
      ? '关联 BOP 尚未发布，当前受治理截图仅接受已发布执行结构；尚未截图或回写工序卡。'
      : `无法核对截图源：${error.message}`;
    $('connectorSource').textContent = `${source.name || '选中线体'} ${lineGid} · BOP ${source.version_gid} · ${message}`;
    _showBanner(message, 'error');
  } finally {
    _governedCaptureSourceLoading = false;
    _renderGovernedCapture(_governedCapture.state);
  }
}

function _currentSimulationWorkspace() {
  return window._simulationEnvironmentWorkspace?.store?.state?.workspace || null;
}

function _renderVmVersioning(state) {
  const panel = $('vmDiffPanel'); const summary = $('vmDiffSummary'); const items = $('vmDiffItems');
  if (!panel || !summary || !items) return;
  if (state.error) _showBanner(`版本治理：${state.error.code}`, 'error');
  if (!state.report) return;
  panel.classList.remove('hidden');
  summary.textContent = Object.entries(state.report.summary || {}).map(([key, count]) => `${key} ${count}`).join(' · ') || '无结构变化';
  items.innerHTML = (state.items || []).map(item => {
    const occurrence = item.after_occurrence_gid || item.before_occurrence_gid || '';
    return `<button class="cs-diff-item" data-occurrence-gid="${_esc(occurrence)}"><strong>${_esc(item.change_type)}</strong> · ${_esc(occurrence || '结构级')}</button>`;
  }).join('') || '<div class="cs-bop-empty">无差异项</div>';
}

function _initVmVersioning() {
  if (!window.AI00VmVersioning || !window.AI00Business?.available()) return;
  const authSubject = () => {
    const user = window.parent?._authUser || window._authUser;
    if (user?.gid || user?.user_gid) return user.gid || user.user_gid;
    try { const stored = JSON.parse(localStorage.getItem('ai00_user') || 'null'); return stored?.gid || stored?.user_gid || null; }
    catch (_) { return null; }
  };
  _vmVersioning = window.AI00VmVersioning.createVmVersioningController({
    getAuthSubjectGid: authSubject,
    invoke: (id, payload) => window.AI00Business.invoke(id, { version: 1, payload,
      ...(payload.idempotency_key ? { idempotency_key: payload.idempotency_key } : {}) },
      async () => (await window.AI00Dialogs.confirm(`确认执行 ${id}@1？`))),
    captureSnapshot: async () => {
      if (!_boundConnectorId || !_governedCapture) throw new Error('connector_required');
      const result = await _governedCapture.captureActiveDocument(_boundConnectorId);
      return { snapshot_request_id: result.snapshot_request_id, snapshot_hash: result.snapshot?.snapshot_hash };
    },
    onChange: _renderVmVersioning,
  });
  const updateSwitch = () => {
    const workspace = _currentSimulationWorkspace();
    if ($('vmAutoCompare')) $('vmAutoCompare').checked = Boolean(workspace && _vmVersioning.isAutomaticComparisonEnabled(workspace.workspace_gid));
  };
  $('btnVmCheckpoint')?.addEventListener('click', async () => {
    const workspace = _currentSimulationWorkspace();
    if (!workspace) return _showBanner('请先选择仿真环境', 'error');
    const name = (await window.AI00Dialogs.prompt('快照名称', `手动快照 ${new Date().toLocaleString()}`));
    if (!name) return;
    try { _vmManualCapture = true; await _vmVersioning.createCheckpoint({ workspaceGid: workspace.workspace_gid, name });
      _showBanner('快照已创建', 'success'); }
    catch (error) { _showBanner(`快照失败：${error.code || error.message}`, 'error'); }
    finally { _vmManualCapture = false; }
  });
  $('btnVmCompare')?.addEventListener('click', async () => {
    const workspace = _currentSimulationWorkspace();
    if (!workspace) return _showBanner('请先选择仿真环境', 'error');
    try {
      const page = await _vmVersioning.listCheckpoints(workspace.workspace_gid); const rows = page.items || [];
      if (rows.length < 2) return _showBanner('至少需要两个快照才能对比', 'error');
      await _vmVersioning.compareNow({ beforeCheckpointGid: rows[1].checkpoint_gid, afterCheckpointGid: rows[0].checkpoint_gid });
    } catch (error) { _showBanner(`对比失败：${error.code || error.message}`, 'error'); }
  });
  $('vmAutoCompare')?.addEventListener('change', event => {
    const workspace = _currentSimulationWorkspace();
    if (!workspace) { event.target.checked = false; return _showBanner('请先选择仿真环境', 'error'); }
    _vmVersioning.setAutomaticComparison({ workspaceGid: workspace.workspace_gid, enabled: event.target.checked });
  });
  $('btnCloseVmDiff')?.addEventListener('click', () => $('vmDiffPanel').classList.add('hidden'));
  $('vmDiffItems')?.addEventListener('click', event => {
    const gid = event.target.closest('[data-occurrence-gid]')?.dataset.occurrenceGid;
    const key = Object.keys(_visNodeMap).find(item => String(_visNodeMap[item]?.node?.occurrence_gid || '') === gid);
    if (key) _selectVisTreeNodes([key]);
  });
  document.addEventListener('click', event => { if (event.target.closest('[data-record-gid]')) setTimeout(updateSwitch, 0); });
  updateSwitch();
}

function _initGovernedCapture() {
  const library = window.SimulationCaptureWorkflow;
  if (!library || !window.AI00Business?.available()) return;
  const api = library.createGatewayApi(window.AI00Business.request, {
    approve: async (capabilityId, majorVersion, payload, metadata = {}) => {
      const fields = Object.keys(payload || {}).sort().join('、') || '无';
      const digest = metadata.payloadHash ? `\n负载哈希：${metadata.payloadHash}` : '';
      return (await window.AI00Dialogs.confirm(
        `确认执行受治理能力 ${capabilityId}@${majorVersion}？\n负载字段：${fields}${digest}`,
      ));
    },
  });
  _governedCapture = library.createCaptureWorkflow({
    invoke: (id, payload, options) => api.invoke(id, payload, options),
    onChange: state => {
      _renderGovernedCapture(state);
      const request = state.snapshotRequest;
      const workspace = _currentSimulationWorkspace();
      if (!_vmManualCapture && _vmVersioning && workspace && request?.status === 'completed'
          && request.snapshot_request_id !== _vmVersioningSnapshotRequest) {
        _vmVersioningSnapshotRequest = request.snapshot_request_id;
        _vmVersioning.onFreshSnapshot({ workspaceGid: workspace.workspace_gid,
          snapshot_request_id: request.snapshot_request_id, snapshot_hash: request.snapshot?.snapshot_hash }).catch(() => {});
      }
    },
  });
  const onboardingLibrary = window.SimulationConnectorOnboarding;
  if (onboardingLibrary) {
    const gatewayInvoke = onboardingLibrary.createGatewayInvoker(
      window.AI00Business.request,
      async () => (await window.AI00Dialogs.confirm('确认绑定此 Connector？')),
    );
    _connectorOnboarding = onboardingLibrary.createConnectorOnboarding({
      invoke: gatewayInvoke,
      gatewayUrl: location.origin,
      openProtocol: uri => $('connectorConnect').setAttribute('href', uri),
      onChange: state => {
        _renderConnectorOnboarding(state);
        if (['bound', 'cancelled', 'expired'].includes(state.kind))
          localStorage.removeItem('ai00.connector.bootstrap');
      },
    });
    let restoredBootstrap = false;
    try {
      const saved = JSON.parse(localStorage.getItem('ai00.connector.bootstrap') || 'null');
      if (saved?.bootstrapId) {
        _connectorOnboarding.restore(saved);
        restoredBootstrap = true;
      }
    } catch (_) {}
    $('connectorConnect')?.addEventListener('click', async event => {
      try {
        if (_connectorOnboarding.state.kind === 'waiting_for_connector') {
          return;
        }
        event.preventDefault();
        const safeTicket = await _connectorOnboarding.connect();
        _connectorOnboarding.launch();
        localStorage.setItem('ai00.connector.bootstrap', JSON.stringify(safeTicket));
        _connectorOnboarding.startPolling();
      } catch (_) {}
    });
    $('connectorApprove')?.addEventListener('click', async () => {
      try { await _connectorOnboarding.approve(); _connectorOnboarding.startPolling(); } catch (_) {}
    });
    $('connectorPairCancel')?.addEventListener('click', async () => {
      try { await _connectorOnboarding.cancel(); } catch (_) {}
    });
    _connectorOnboarding.refresh().then(() => {
      // An unbound idle page has nothing to poll. Poll only while resuming a
      // pairing the user explicitly started; otherwise each open tab would
      // hammer the Capability Gateway every 1.5 seconds for two minutes.
      if (restoredBootstrap && _connectorOnboarding.state.kind !== 'bound')
        _connectorOnboarding.startPolling();
    }).catch(() => {});
  }
  $('btnGovernedCapture')?.addEventListener('click', () => _openGovernedCapture());
  $('connectorClose')?.addEventListener('click', () => $('connectorCaptureOverlay').classList.add('hidden'));
  $('connectorCompose')?.addEventListener('click', async () => {
    if (_governedCaptureSourceLoading) return;
    const source = _governedCaptureSource;
    const deviceId = _boundConnectorId;
    if (!source?.execution_plan_ref || !deviceId || !_governedCaptureScopeLineGid) {
      _showBanner('请先核对已发布 BOP，并连接本机 Connector', 'error');
      return;
    }
    _governedCaptureSourceLoading = true;
    $('connectorCompose').disabled = true;
    try {
      if (source.workspace_gid && (source.workspace_gid !== _currentSimulationWorkspace()?.workspace_gid
          || source.hierarchy_gid !== _modelDocumentCollection?.state.selectedHierarchyGid)) throw Error('capture_source_changed');
      const reference = await library.readCaptureExecutionSource(_invokeCapability, source);
      if (JSON.stringify(reference) !== JSON.stringify(source.execution_plan_ref)) throw Error('capture_source_changed');
      const result = await _governedCapture.composeFromActiveDocument({
        name: $('connectorEnvironmentName').value.trim() || '工艺倒序截图环境',
        device_id: deviceId,
        execution_plan_ref: reference,
        capture_profile: { format: 'png', width: 1920, height: 1080, background: 'current' },
        scope: { kind: 'line', gid: _governedCaptureScopeLineGid },
      });
      if (result.status === 'composed') await _governedCapture.selectConnector(deviceId);
    } catch (error) { _showBanner(`截图环境构建失败：${error.message}`, 'error'); }
    finally { _governedCaptureSourceLoading = false; _renderGovernedCapture(_governedCapture.state); }
  });
  $('connectorPreflight')?.addEventListener('click', async () => {
    try { await _governedCapture.selectConnector(_boundConnectorId); } catch (_) {}
  });
  $('connectorStart')?.addEventListener('click', async () => {
    try { await _governedCapture.startCapture(); } catch (_) {}
  });
  $('connectorCancel')?.addEventListener('click', async () => {
    try { await _governedCapture.cancel(); } catch (_) {}
  });
  _renderGovernedCapture(_governedCapture.state);
}

window.addEventListener('message', e => {
  if (e.data?.type === 'theme')
    document.documentElement.setAttribute('data-theme', e.data.theme || 'dark');
  if (e.data?.type === 'workspace:visibility' && (window.parent === window || e.source === window.parent)) {
    _workspacePageVisible = e.data.visible !== false;
    _viewerDocumentManager?.visibilityChanged();
    if (_workspacePageVisible) void _refreshTeamcenterSessionButton();
    _notifyNativeViewportBounds();
  }
});

document.addEventListener('DOMContentLoaded', init);
window.addEventListener('error',event=>_simulationDebug('ui_error',{message:event.message,exception_type:event.error?.name}));
window.addEventListener('unhandledrejection',event=>_simulationDebug('ui_error',{message:event.reason?.message||String(event.reason),exception_type:event.reason?.name}));
