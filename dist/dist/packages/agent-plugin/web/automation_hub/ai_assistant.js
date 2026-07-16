/**
 * web/automation_hub/ai_assistant.js
 * AI 工艺助手对话界面逻辑
 */
(function () {
  'use strict';

  // ── 运行模式：popup 窗口（无父框架）vs 内嵌 iframe ──────────────────────
  const _IS_POPUP = window.parent === window;

  // ── localStorage 账号隔离 ─────────────────────────────────────────────────
  function _lsk(base) {
    try { const u = window._authUser || window.parent?._authUser || window.top?._authUser; const g = u?.gid || u?.user_gid || ''; return g ? `${g}:${base}` : base; } catch { return base; }
  }

  // ── 状态 ──────────────────────────────────────────────────────────────────
  let _sessionGid = null;
  let _sending = false;
  let _aborted = false;
  let _pendingConfirm = null;   // { confirm_token, tool_name, tool_use_id, inputs, preview }
  let _sessions = [];

  // Orchestrator 模式：'auto' | 'on' | 'off'
  let _orchestratorMode = 'auto';
  // 活跃 Agent 列表（当前会话）
  let _activeAgents = [];

  // 语音输入状态
  let _recognition = null;
  let _recognizing = false;

  // popup 模式下本地存储 auth 状态
  let _authUser  = null;
  let _authMode  = 'local';
  let _authToken = '';

  // 侧边栏状态栏
  let _sbBalTimer     = null;
  let _sbBalTickTimer = null;
  let _sbLastBalTime  = null;
  let _sbLastBalVal   = null;

  // 用量统计（localStorage）
  function _sbDayKey()  { return _lsk('ai_cost_' + new Date().toISOString().slice(0, 10)); }
  function _sbWeekKey() {
    const d = new Date();
    const jan1 = new Date(d.getFullYear(), 0, 1);
    const week = Math.ceil(((d - jan1) / 86400000 + jan1.getDay() + 1) / 7);
    return _lsk(`ai_cost_w_${d.getFullYear()}_${String(week).padStart(2, '0')}`);
  }

  // ── DOM refs ───────────────────────────────────────────────────────────────
  const $messages    = document.getElementById('aiMessages');
  const $empty       = document.getElementById('aiEmpty');
  const $input       = document.getElementById('aiInput');
  const $sendBtn     = document.getElementById('aiSendBtn');
  const $micBtn      = document.getElementById('aiMicBtn');
  const $newBtn      = document.getElementById('aiNewBtn');
  const $sessionList = document.getElementById('aiSessionList');
  const $toolCards   = document.getElementById('aiToolCards');
  const $toolEmpty   = document.getElementById('aiToolEmpty');
  const $sbBal          = document.getElementById('aiSbBal');
  const $sbRefreshTime  = document.getElementById('aiSbRefreshTime');
  const $sbUsage        = document.getElementById('aiSbUsage');
  const $sbUsageSep     = document.getElementById('aiSbUsageSep1');
  const $sbModel        = document.getElementById('aiSbModel');
  const $sbIter         = document.getElementById('aiSbIter');
  const $sbChatBtn      = document.getElementById('aiSbChatBtn');
  const $sbCanvasBtn    = document.getElementById('aiSbCanvasBtn');
  const $sidebar     = document.getElementById('aiSidebar');
  const $toolsPanel  = document.getElementById('aiToolsPanel');
  const $detailOverlay = document.getElementById('aiToolDetail');
  const $detailTitle   = document.getElementById('aiDetailTitle');
  const $detailBody    = document.getElementById('aiDetailBody');
  const $tlOverlay     = document.getElementById('aiToolListOverlay');
  const $tlBody        = document.getElementById('aiTlBody');
  const $tlTotal       = document.getElementById('aiTlTotal');

  // 协作面板 DOM refs
  const $collabSection  = document.getElementById('aiCollabSection');
  const $collabToggle   = document.getElementById('aiCollabToggle');
  const $collabBadge    = document.getElementById('aiCollabBadge');
  const $modeToggle     = document.getElementById('aiModeToggle');
  const $agentTree      = document.getElementById('aiAgentTree');
  const $orchPhase      = document.getElementById('aiOrchPhase');
  const $agentDetailOverlay = document.getElementById('aiAgentDetailOverlay');
  const $agentDetailTitle   = document.getElementById('aiAgentDetailTitle');
  const $agentDetailBody    = document.getElementById('aiAgentDetailBody');

  // 画布面板 DOM refs
  const $canvasPanel  = document.getElementById('aiCanvasPanel');
  const $canvasToggle = document.getElementById('aiCanvasToggle');
  const $canvasBody   = document.getElementById('aiCanvasBody');

  // WorkflowCanvas 实例（懒初始化）
  let _wfCanvas = null;

  // Agent 上下文开关状态
  let _wfcCtxOn = localStorage.getItem(_lsk('wfc:context-on')) === 'true';

  // ── 权限门控 ───────────────────────────────────────────────────────────────

  function _isSuperAdmin() {
    try {
      const user = window._authUser || window.parent?._authUser || window.top?._authUser;
      const role = user?.system_role || user?.org_role || user?.role || '';
      return role === 'super_admin';
    } catch (_) { return false; }
  }

  function _hasAiAccess() {
    try {
      const mode = window._authMode || window.parent?._authMode || window.top?._authMode || 'none';
      if (mode !== 'feishu') return false;
      const user = window._authUser || window.parent?._authUser || window.top?._authUser;
      if (!user) return true; // 已登录但用户信息未加载，放行（后端鉴权）
      const role = user?.system_role || user?.org_role || user?.role || '';
      return role !== 'external';
    } catch (_) { return false; }
  }

  function _showPermDenied() {
    document.querySelector('.ai-shell').innerHTML = `
      <div style="flex:1;display:flex;flex-direction:column;align-items:center;
                  justify-content:center;gap:14px;color:var(--text-muted);">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="1" style="opacity:.3">
          <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
          <path d="M7 11V7a5 5 0 0110 0v4"/>
        </svg>
        <div style="font-size:16px;font-weight:500;color:var(--text);">需要登录后使用</div>
        <div style="font-size:12px;">AI 助手需要 member 及以上角色，external 用户无权访问</div>
      </div>`;
  }

  // ── 初始化 ─────────────────────────────────────────────────────────────────
  async function init() {
    if (_IS_POPUP) {
      // 弹出窗口：直接从 Electron 读取 auth 状态，无权限门控
      try {
        const state = await window.electronAPI?.authGetState?.();
        if (state) { _authUser = state.user || null; _authMode = state.mode || 'none'; _authToken = state.token || ''; }
      } catch (_) {}
      window.electronAPI?.onAuthStateChanged?.((_, state) => {
        _authUser = state?.user || null; _authMode = state?.mode || 'none'; _authToken = state?.token || '';
      });
    } else {
      // 内嵌 iframe：等父框架 bridgeAuth 完成，检查 member 权限
      await new Promise(r => setTimeout(r, 100));
      if (!_hasAiAccess()) { _showPermDenied(); return; }
    }
    await loadSessions();
    bindEvents();
    // 侧边栏状态栏：读取初始模型 + 启动余额轮询
    try {
      const cfg = await _cf('GET', '/api/ai/admin-config');
      if (cfg?.model) _sbSetModel(cfg.model);
    } catch (_) {}
    _sbStartBalPolling();
    // 状态栏入口按钮
    $sbChatBtn?.addEventListener('click', () => {
      // 聚焦到聊天输入框
      document.getElementById('aiInput')?.focus();
      $sbChatBtn.classList.add('active');
      $sbCanvasBtn?.classList.remove('active');
    });
    $sbCanvasBtn?.addEventListener('click', () => {
      window.electronAPI?.openWfcWindow?.();
      $sbCanvasBtn.classList.add('active');
      setTimeout(() => $sbCanvasBtn.classList.remove('active'), 600);
    });
    // 加载 Skills
    _loadSkills();
    // 初始化画布上下文开关按钮状态
    _updateWfcCtxBtn();
    // 初始化话题讨论面板
    _initDiscussionPanel();
  }

  function bindEvents() {
    $newBtn.addEventListener('click', newSession);
    $sendBtn.addEventListener('click', () => {
      if (_sending) {
        // 点击停止
        _aborted = true;
        _sending = false;
        _setSendBtnStopping(false);
      } else {
        submitMessage();
      }
    });
    $input.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        submitMessage();
      }
    });
    $input.addEventListener('input', autoResizeInput);

    // 麦克风按钮
    if ($micBtn) $micBtn.addEventListener('click', _toggleMic);
    _initSpeech();

    // 侧边栏折叠
    document.getElementById('aiSidebarToggle').addEventListener('click', toggleSidebar);
    // 工具面板折叠
    document.getElementById('aiToolsToggle').addEventListener('click', toggleToolsPanel);
    // 工具列表弹窗
    document.getElementById('aiToolListBtn').addEventListener('click', openToolList);
    document.getElementById('aiToolListClose').addEventListener('click', closeToolList);
    $tlOverlay.addEventListener('click', e => { if (e.target === $tlOverlay) closeToolList(); });
    // 详情弹窗关闭
    document.getElementById('aiDetailClose').addEventListener('click', closeToolDetail);
    $detailOverlay.addEventListener('click', e => { if (e.target === $detailOverlay) closeToolDetail(); });

    // 飞书深链 / 外部链接拦截：用 Electron openExternal 打开，避免在 webview 内导航
    $messages.addEventListener('click', e => {
      const a = e.target.closest('a[href]');
      if (!a) return;
      const href = a.getAttribute('href');
      if (href && (href.startsWith('https://') || href.startsWith('http://'))) {
        e.preventDefault();
        window.electronAPI?.openExternal?.(href);
      }
    });

    // 协作面板折叠/展开
    if ($collabToggle) $collabToggle.addEventListener('click', _toggleCollabPanel);
    // 模式切换按钮（三态循环）
    if ($modeToggle) $modeToggle.addEventListener('click', _toggleOrchestratorMode);
    // Agent 详情弹窗关闭
    if ($agentDetailOverlay) {
      document.getElementById('aiAgentDetailClose')?.addEventListener('click', _closeAgentDetail);
      $agentDetailOverlay.addEventListener('click', e => {
        if (e.target === $agentDetailOverlay) _closeAgentDetail();
      });
    }
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') {
        closeToolDetail(); closeToolList(); _closeAgentDetail();
        _hideSkillDrop();
        document.getElementById('aiSkillVarOverlay')?.classList.add('hidden');
      }
    });

    // 画布面板
    if ($canvasToggle) $canvasToggle.addEventListener('click', _toggleCanvasPanel);
    document.getElementById('wfcCtxToggle')?.addEventListener('click', _toggleWfcCtx);
    document.getElementById('wfcInjectBtn')?.addEventListener('click', _injectCanvasToInput);
    document.getElementById('wfcClearBtn')?.addEventListener('click', () => {
      if (_wfCanvas) _wfCanvas._clear();
    });
    document.getElementById('wfcSaveBtn')?.addEventListener('click', _wfcSave);
    document.getElementById('wfcLoadBtn')?.addEventListener('click', _wfcLoad);
    document.getElementById('wfcToSkillBtn')?.addEventListener('click', _wfcToSkill);
    document.getElementById('wfcModeBtn')?.addEventListener('click', _toggleWfcMode);
    // 添加泳道按钮（动态插入）
    setTimeout(() => {
      const addLaneBtn = document.querySelector('.wfc-add-lane');
      if (addLaneBtn) addLaneBtn.addEventListener('click', () => _wfCanvas?.addLane());
    }, 200);

    // Skill @触发
    $input.addEventListener('input', _checkSkillTrigger);
    $input.addEventListener('keydown', _handleSkillDropKeys);

    // Skill 面板刷新
    document.getElementById('aiSkillPanelRefresh')?.addEventListener('click', _loadSkills);

    // Skill 变量 modal
    document.getElementById('aiSkillVarClose')?.addEventListener('click', _closeSkillVarModal);
    document.getElementById('aiSkillVarCancel')?.addEventListener('click', _closeSkillVarModal);
    document.getElementById('aiSkillVarConfirm')?.addEventListener('click', _confirmSkillVars);
    document.getElementById('aiSkillVarOverlay')?.addEventListener('click', e => {
      if (e.target === document.getElementById('aiSkillVarOverlay')) _closeSkillVarModal();
    });
  }

  function autoResizeInput() {
    $input.style.height = 'auto';
    $input.style.height = Math.min($input.scrollHeight, 120) + 'px';
  }

  // ── 会话管理 ──────────────────────────────────────────────────────────────

  async function loadSessions() {
    try {
      const userGid = _getUserGid();
      const _sessRes = await _cf('GET', '/api/ai/sessions');
      _sessions = _sessRes?.sessions || [];
      renderSessionList();
      // 若当前无活跃会话，自动恢复最近一条
      if (!_sessionGid && _sessions && _sessions.length > 0) {
        await openSession(_sessions[0].gid);
      }
    } catch (e) {
      console.warn('[AiAssistant] loadSessions 失败:', e);
    }
  }

  function renderSessionList() {
    $sessionList.innerHTML = '';
    if (!_sessions || !_sessions.length) {
      const empty = document.createElement('div');
      empty.style.cssText = 'padding:12px;color:var(--text-muted);font-size:12px;text-align:center;';
      empty.textContent = '暂无历史对话';
      $sessionList.appendChild(empty);
      return;
    }
    _sessions.forEach(sess => {
      const item = document.createElement('div');
      item.className = 'ai-session-item' + (sess.gid === _sessionGid ? ' active' : '');
      item.dataset.gid = sess.gid;
      item.innerHTML = `
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;opacity:.5">
          <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
        </svg>
        <span class="ai-session-item-title">${_esc(sess.title || '新对话')}</span>
        <button class="ai-session-del" data-gid="${sess.gid}" title="删除">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>`;
      item.addEventListener('click', e => {
        if (e.target.closest('.ai-session-del')) return;
        openSession(sess.gid);
      });
      item.querySelector('.ai-session-del').addEventListener('click', e => {
        e.stopPropagation();
        deleteSession(sess.gid);
      });
      $sessionList.appendChild(item);
    });
  }

  function newSession() {
    _sessionGid = null;
    _pendingConfirm = null;
    _activeAgents = [];
    clearMessages();
    clearToolCards();
    if ($agentTree) $agentTree.innerHTML = '<div class="ai-agent-tree-empty">无活跃 Agent</div>';
    if ($collabBadge) $collabBadge.classList.add('hidden');
    $input.value = '';
    $input.style.height = '';
    _updateActiveSession();
  }

  async function openSession(gid) {
    _sessionGid = gid;
    _pendingConfirm = null;
    _activeAgents = [];
    clearMessages();
    clearToolCards();
    if ($agentTree) $agentTree.innerHTML = '<div class="ai-agent-tree-empty">无活跃 Agent</div>';
    if ($collabBadge) $collabBadge.classList.add('hidden');
    _updateActiveSession();
    try {
      const _sessDetail = await _cf('GET', `/api/ai/sessions/${gid}`);
      restoreTurns(_sessDetail?.turns);
    } catch (e) {
      console.warn('[AiAssistant] openSession 失败:', e);
    }
  }

  async function deleteSession(gid) {
    try {
      await _cf('DELETE', `/api/ai/sessions/${gid}`);
      if (_sessionGid === gid) newSession();
      await loadSessions();
    } catch (e) {
      console.warn('[AiAssistant] deleteSession 失败:', e);
    }
  }

  function restoreTurns(turns) {
    if (!turns || !turns.length) return;
    turns.forEach(turn => {
      if (turn.role === 'user') {
        appendBubble('user', turn.content);
      } else if (turn.role === 'assistant') {
        appendBubble('assistant', turn.content);
      } else if (turn.role === 'summary') {
        // 上下文压缩摘要：用灰色系统提示气泡显示
        appendBubble('system', '📋 ' + turn.content);
      } else if (turn.role === 'tool_result' && turn.tool_calls?.length) {
        turn.tool_calls.forEach(tc => appendToolCard(tc));
      } else if (turn.role === 'agent_result' && turn.tool_calls?.length) {
        // 恢复 Orchestrator 协作面板历史
        const orchTc = turn.tool_calls.find(tc => tc.name === 'orchestrator_summary');
        if (orchTc?.input?.agents?.length) {
          _activeAgents = orchTc.input.agents;
          renderAgentTree(orchTc.input.agents);
          // 展开协作面板（但不自动折叠）
          if ($collabSection) $collabSection.classList.remove('collapsed');
        }
        if (turn.content) appendBubble('assistant', turn.content);
      }
    });
  }

  function _updateActiveSession() {
    $sessionList.querySelectorAll('.ai-session-item').forEach(el => {
      el.classList.toggle('active', el.dataset.gid === _sessionGid);
    });
  }

  // ── 协作面板（Orchestrator）────────────────────────────────────────────────

  function _toggleCollabPanel() {
    if ($collabSection) $collabSection.classList.toggle('collapsed');
  }

  function _toggleOrchestratorMode() {
    const modes = ['auto', 'on', 'off'];
    const labels = { auto: '自动', on: '开启', off: '关闭' };
    const idx = modes.indexOf(_orchestratorMode);
    _orchestratorMode = modes[(idx + 1) % modes.length];
    if ($modeToggle) {
      $modeToggle.dataset.mode = _orchestratorMode;
      $modeToggle.textContent = labels[_orchestratorMode];
    }
  }

  /**
   * 渲染 Agent 树节点列表。
   * agents: [{agent_id, agent_type, status, instruction, output?}]
   */
  function renderAgentTree(agents) {
    if (!$agentTree) return;
    if (!agents || !agents.length) {
      $agentTree.innerHTML = '<div class="ai-agent-tree-empty">无活跃 Agent</div>';
      if ($collabBadge) $collabBadge.classList.add('hidden');
      if ($orchPhase) $orchPhase.classList.add('hidden');
      return;
    }

    const runningCount = agents.filter(a => a.status === 'running').length;
    const doneCount    = agents.filter(a => a.status === 'done' || a.status === 'error').length;
    if ($collabBadge) {
      if (runningCount > 0) {
        $collabBadge.textContent = runningCount;
        $collabBadge.classList.remove('hidden');
      } else {
        $collabBadge.classList.add('hidden');
      }
    }

    // 根据 agent 状态推断当前阶段
    if ($orchPhase) {
      $orchPhase.classList.remove('hidden');
      const allDone = doneCount === agents.length;
      const anyRun  = runningCount > 0;
      const phase   = allDone ? 3 : anyRun ? 2 : 1;
      $orchPhase.querySelectorAll('.ai-orch-step').forEach(el => {
        const s = parseInt(el.dataset.step);
        el.className = 'ai-orch-step' + (s < phase ? ' done' : s === phase ? ' active' : '');
      });
    }

    const _statusIcon = (status) => {
      if (status === 'done') return `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>`;
      if (status === 'running') return `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>`;
      if (status === 'error') return `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`;
      // pending
      return `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/></svg>`;
    };

    const _typeIcon = (type) => {
      if (type === 'researcher')
        return `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>`;
      if (type === 'writer')
        return `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>`;
      if (type === 'analyst')
        return `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>`;
      // generic agent
      return `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="8" r="4"/><path d="M8 12v1a4 4 0 008 0v-1"/></svg>`;
    };

    $agentTree.innerHTML = agents.map(agent => `
      <div class="ai-agent-node" data-status="${_esc(agent.status)}" data-id="${_esc(agent.agent_id)}">
        <div class="ai-agent-node-top">
          <span class="ai-agent-icon">${_statusIcon(agent.status)}</span>
          <span class="ai-agent-type-icon">${_typeIcon(agent.agent_type)}</span>
          <span class="ai-agent-type">${_esc(agent.agent_type)}</span>
        </div>
        <div class="ai-agent-instruction">${_esc((agent.instruction || '').slice(0, 60))}</div>
      </div>
    `).join('');

    $agentTree.querySelectorAll('.ai-agent-node').forEach(node => {
      const agentId = node.dataset.id;
      node.addEventListener('click', () => {
        const agent = agents.find(a => a.agent_id === agentId);
        if (agent) _showAgentDetail(agent);
      });
    });
  }

  function _showAgentDetail(agent) {
    if (!$agentDetailOverlay || !$agentDetailTitle || !$agentDetailBody) return;
    $agentDetailTitle.textContent = `[${agent.agent_type}] ${agent.agent_id}`;
    $agentDetailBody.innerHTML = `
      <div>
        <div class="ai-agent-detail-label">任务指令</div>
        <div class="ai-agent-detail-text">${_esc(agent.instruction || '')}</div>
      </div>
      ${agent.output ? `
      <div>
        <div class="ai-agent-detail-label">执行结果</div>
        <div class="ai-agent-detail-output">${_esc(agent.output)}</div>
      </div>` : ''}
      ${agent.error ? `
      <div>
        <div class="ai-agent-detail-label" style="color:var(--danger)">错误信息</div>
        <div class="ai-agent-detail-text" style="color:var(--danger)">${_esc(agent.error)}</div>
      </div>` : ''}`;
    $agentDetailOverlay.classList.remove('hidden');
  }

  function _closeAgentDetail() {
    if ($agentDetailOverlay) $agentDetailOverlay.classList.add('hidden');
  }

  /** 有活跃 Agent 时自动展开协作面板，完成后 3s 折叠 */
  function _autoExpandCollab() {
    if (!$collabSection) return;
    $collabSection.classList.remove('collapsed');
    const allDone = _activeAgents.every(a => a.status === 'done' || a.status === 'error');
    if (allDone) {
      setTimeout(() => {
        if ($collabSection) $collabSection.classList.add('collapsed');
      }, 3000);
    }
  }

  // ── 发送消息 ───────────────────────────────────────────────────────────────

  async function submitMessage() {
    const text = $input.value.trim();
    if (!text || _sending) return;

    _sending = true;
    _aborted = false;
    _pendingConfirm = null;
    _setSendBtnStopping(true);

    $input.value = '';
    $input.style.height = '';
    hideEmpty();
    appendBubble('user', text);
    clearToolCards();

    // 打字指示
    const typingEl = appendTyping();

    try {
      const res = await _cf('POST', '/api/ai/chat', {
        message: text,
        session_id: _sessionGid || null,
        auth_token: _getAuthToken(),
        context: await _getContext(),
      });

      removeTyping(typingEl);

      // 用户已中止
      if (_aborted) {
        _sending = false;
        _setSendBtnStopping(false);
        return;
      }

      // 请求失败
      if (res?.error) {
        appendBubble('system', `❌ 请求失败：${res.error}`);
        _sending = false;
        _setSendBtnStopping(false);
        return;
      }

      // 更新 session gid
      if (res.session_id) {
        const isNew = !_sessionGid;
        _sessionGid = res.session_id;
        _updateActiveSession();
        if (isNew) await loadSessions();
      }

      // 渲染工具调用
      if (res.tool_calls?.length) {
        res.tool_calls.forEach(tc => appendToolCard(tc));
      }

      // 渲染 Orchestrator Agent 树
      if (res.orchestrator && res.agents?.length) {
        _activeAgents = res.agents;
        renderAgentTree(res.agents);
        _autoExpandCollab();
      }

      // 更新侧边栏状态栏
      if (res.model) _sbSetModel(res.model);
      if (res.iter_count !== undefined) _sbSetIter(res.iter_count);
      if (res.total_tokens) _sbTrackUsage(res.total_tokens, res.model);

      if (res.pending_confirm) {
        _pendingConfirm = res.pending_confirm;
        if (res.answer) appendBubble('assistant', res.answer);
        appendConfirmCard(res.pending_confirm);
      } else {
        if (res.answer) appendBubble('assistant', res.answer);
      }

    } catch (e) {
      removeTyping(typingEl);
      if (!_aborted) appendBubble('system', `❌ 请求失败：${e}`);
    }

    _sending = false;
    _setSendBtnStopping(false);
  }

  // ── 确认操作 ───────────────────────────────────────────────────────────────

  async function confirmAction(token, toolName, toolUseId, inputs, cardEl) {
    if (_sending) return;
    _sending = true;
    _aborted = false;
    _setSendBtnStopping(true);
    cardEl.querySelector('.ai-confirm-btn.ok').disabled = true;
    cardEl.querySelector('.ai-confirm-btn.cancel').disabled = true;

    const typingEl = appendTyping();

    try {
      const res = await _cf('POST', '/api/ai/confirm/sync', {
        session_gid: _sessionGid,
        confirm_token: token,
        tool_name: toolName,
        tool_use_id: toolUseId,
        auth_token: _getAuthToken(),
      });

      removeTyping(typingEl);
      if (res?.error) {
        appendBubble('system', `❌ 执行失败：${res.error}`);
        _sending = false; _setSendBtnStopping(false); return;
      }
      cardEl.remove();
      _pendingConfirm = null;

      if (res.tool_calls?.length) {
        res.tool_calls.forEach(tc => appendToolCard({ ...tc, confirmed: true }));
      }
      // 更新侧边栏状态栏
      if (res.model) _sbSetModel(res.model);
      if (res.iter_count !== undefined) _sbSetIter(res.iter_count);
      if (res.total_tokens) _sbTrackUsage(res.total_tokens, res.model);
      if (res.pending_confirm) {
        _pendingConfirm = res.pending_confirm;
        if (res.answer) appendBubble('assistant', res.answer);
        appendConfirmCard(res.pending_confirm);
      } else {
        if (res.answer) appendBubble('assistant', res.answer);
      }

    } catch (e) {
      removeTyping(typingEl);
      appendBubble('system', `❌ 确认执行失败：${e}`);
    }

    _sending = false;
    _setSendBtnStopping(false);
  }

  function cancelConfirm(cardEl) {
    cardEl.remove();
    _pendingConfirm = null;
    appendBubble('system', '已取消该操作');
  }

  // ── DOM 操作 ───────────────────────────────────────────────────────────────

  function hideEmpty() {
    if ($empty) $empty.style.display = 'none';
  }

  function clearMessages() {
    const empties = $messages.querySelectorAll('.ai-empty');
    $messages.innerHTML = '';
    empties.forEach(el => $messages.appendChild(el));
    if ($empty) $empty.style.display = '';
  }

  function clearToolCards() {
    $toolCards.innerHTML = '';
    if ($toolEmpty) {
      $toolEmpty.style.display = '';
      $toolCards.appendChild($toolEmpty);
    }
  }

  function appendBubble(role, text) {
    hideEmpty();
    const avatarUrl = role === 'user' ? _getAvatarUrl() : '';
    const avatarHtml = avatarUrl
      ? `<img class="ai-avatar-img" src="${avatarUrl}" alt="">`
      : (role === 'user' ? 'U' : role === 'assistant' ? '柔' : '⚙');
    const div = document.createElement('div');
    div.className = `ai-bubble ${role}`;
    let contentHtml;
    if (role === 'assistant' && typeof marked !== 'undefined') {
      contentHtml = marked.parse(text || '');
    } else {
      contentHtml = `<span>${_esc(text)}</span>`;
    }
    div.innerHTML = `
      <div class="ai-avatar">${avatarHtml}</div>
      <div class="ai-bubble-content ai-md">${contentHtml}</div>`;
    // assistant 气泡：操作按钮（复制 MD + 引用）
    if (role === 'assistant') {
      const actions = document.createElement('div');
      actions.className = 'ai-bubble-actions';
      actions.innerHTML = `
        <button class="ai-bubble-act-btn" data-act="copy" title="复制为 Markdown">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
            <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>
          </svg>
        </button>
        <button class="ai-bubble-act-btn" data-act="quote" title="引用到输入框">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M3 21c3 0 7-1 7-8V5c0-1.25-.756-2.017-2-2H4c-1.25 0-2 .75-2 2v3c0 1.25.75 2 2 2h3c0 0 0 1 0 2a2 2 0 01-2 2H3"/>
            <path d="M15 21c3 0 7-1 7-8V5c0-1.25-.756-2.017-2-2h-4c-1.25 0-2 .75-2 2v3c0 1.25.75 2 2 2h3c0 0 0 1 0 2a2 2 0 01-2 2h-2"/>
          </svg>
        </button>`;
      actions.addEventListener('click', e => {
        const btn = e.target.closest('[data-act]');
        if (!btn) return;
        if (btn.dataset.act === 'copy') _copyBubbleMd(text, btn);
        if (btn.dataset.act === 'quote') _quoteBubble(text);
      });
      div.appendChild(actions);
    }
    $messages.appendChild(div);
    $messages.scrollTop = $messages.scrollHeight;
    return div;
  }

  function appendTyping() {
    hideEmpty();
    const wrap = document.createElement('div');
    wrap.className = 'ai-bubble assistant ai-thinking-bubble';
    wrap.innerHTML = `
      <div class="ai-avatar ai-avatar-thinking">柔</div>
      <div class="ai-bubble-content ai-thinking-content">
        <span class="ai-thinking-icon">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="ai-thinking-spin">
            <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
          </svg>
        </span>
        <span class="ai-thinking-label">正在思考</span><span class="ai-thinking-dots"><span>.</span><span>.</span><span>.</span></span>
        <span class="ai-thinking-timer">0s</span>
      </div>`;
    $messages.appendChild(wrap);
    $messages.scrollTop = $messages.scrollHeight;
    // 启动计时器
    const timerEl = wrap.querySelector('.ai-thinking-timer');
    const start = Date.now();
    wrap._timerInterval = setInterval(() => {
      const s = Math.floor((Date.now() - start) / 1000);
      if (timerEl) timerEl.textContent = `${s}s`;
    }, 1000);
    return wrap;
  }

  function removeTyping(el) {
    if (el) {
      if (el._timerInterval) clearInterval(el._timerInterval);
      if (el.parentNode) el.remove();
    }
  }

  function appendConfirmCard(pending) {
    hideEmpty();
    const div = document.createElement('div');
    div.className = 'ai-confirm-card';
    div.innerHTML = `
      <div class="ai-confirm-title">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
          <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
        </svg>
        操作需要确认
      </div>
      <div class="ai-confirm-preview">${_esc(pending.preview)}</div>
      <div class="ai-confirm-btns">
        <button class="ai-confirm-btn ok">确认执行</button>
        <button class="ai-confirm-btn cancel">取消</button>
      </div>`;
    div.querySelector('.ok').addEventListener('click', () =>
      confirmAction(pending.confirm_token, pending.tool_name,
                    pending.tool_use_id, pending.inputs, div));
    div.querySelector('.cancel').addEventListener('click', () => cancelConfirm(div));
    $messages.appendChild(div);
    $messages.scrollTop = $messages.scrollHeight;
    return div;
  }

  function appendToolCard(tc) {
    // generate_canvas 工具特殊处理：自动展开画布
    if (_handleCanvasTool(tc)) {
      // 仍在工具面板渲染一个卡片（继续往下执行）
    }

    // navigate_to_page 工具：通知主窗口打开页面
    if (_handleNavigateTool(tc)) {
      // 仍在工具面板渲染一个卡片（继续往下执行）
    }

    // open_in_container 工具：在底部容器新增 iframe 标签页
    if (_handleOpenContainerTool(tc)) {
      // 仍在工具面板渲染一个卡片（继续往下执行）
    }

    // create_discussion_topic 工具：自动导入话题到侧边栏 + 同步到 WFC 窗口
    if (tc.name === 'create_discussion_topic') {
      const result = tc.result || {};
      if (result.status === 'topic_created' && result.topic) {
        _importTopic(result.topic);
        // 同步推送到 WFC 窗口（若已打开）
        window.electronAPI?.wfcPushTopic?.(result.topic);
        // 画布侧边栏已接管话题展示，折叠 AI 对话侧边栏的话题区
        document.getElementById('aiDiscWrap')?.classList.add('disc-collapsed');
      }
    }

    if ($toolEmpty) $toolEmpty.style.display = 'none';

    const isWrite = [
      'create_task','update_task_status','create_issue',
      'update_issue_status','create_approval_order'
    ].includes(tc.name);
    const isConfirmed = tc.confirmed;
    const nameClass = isConfirmed ? 'confirmed' : isWrite ? 'write' : '';

    const card = document.createElement('div');
    card.className = 'ai-tool-card';
    card.title = '点击查看详情';
    card.innerHTML = `
      <div class="ai-tool-name ${nameClass}">
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
        </svg>
        ${_esc(tc.name)}${isConfirmed ? ' ✓' : ''}
      </div>
      <div class="ai-tool-section-label">输入</div>
      <div class="ai-tool-json">${_esc(_summarizeResult(tc.input || {}))}</div>
      ${tc.result !== undefined ? `
        <div class="ai-tool-section-label">结果</div>
        <div class="ai-tool-json">${_esc(_summarizeResult(tc.result))}</div>
      ` : ''}`;
    card.addEventListener('click', () => showToolDetail(tc));
    $toolCards.appendChild(card);
  }

  function _summarizeResult(result) {
    const str = JSON.stringify(result, null, 2);
    return str.length > 300 ? str.slice(0, 300) + '\n…（已截断）' : str;
  }

  function toggleSidebar() {
    const collapsed = $sidebar.classList.toggle('collapsed');
    const btn = document.getElementById('aiSidebarToggle');
    // 箭头：展开态朝左（折叠），折叠态朝右（展开）
    btn.innerHTML = collapsed
      ? `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>`
      : `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>`;
  }

  function toggleToolsPanel() {
    const collapsed = $toolsPanel.classList.toggle('collapsed');
    const btn = document.getElementById('aiToolsToggle');
    // 箭头：展开态朝右（折叠），折叠态朝左（展开）
    btn.innerHTML = collapsed
      ? `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>`
      : `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>`;
  }

  function showToolDetail(tc) {
    $detailTitle.textContent = tc.name || 'tool';
    $detailBody.innerHTML = `
      <div>
        <div class="ai-detail-section-label">输入参数</div>
        <div class="ai-detail-json">${_esc(JSON.stringify(tc.input || {}, null, 2))}</div>
      </div>
      ${tc.result !== undefined ? `
      <div>
        <div class="ai-detail-section-label">执行结果</div>
        <div class="ai-detail-json">${_esc(JSON.stringify(tc.result, null, 2))}</div>
      </div>` : ''}`;
    $detailOverlay.classList.remove('hidden');
  }

  function closeToolDetail() {
    $detailOverlay.classList.add('hidden');
  }

  // ── 工具注册表弹窗 ─────────────────────────────────────────────────────────

  const _TL_GROUPS = [
    { key: 'read',             label: '只读工具',        badgeText: '直接执行', badgeClass: 'ok'   },
    { key: 'write_confirm',    label: '写工具 — 需确认', badgeText: '执行前确认', badgeClass: 'warn' },
    { key: 'write_no_confirm', label: '写工具 — 免确认', badgeText: '直接执行', badgeClass: 'ok'   },
    { key: 'system',           label: '系统感知工具',    badgeText: '直接执行', badgeClass: 'sys'  },
  ];

  async function openToolList() {
    $tlOverlay.classList.remove('hidden');
    $tlBody.innerHTML = '<div class="ai-tl-loading">加载中…</div>';
    if ($tlTotal) $tlTotal.textContent = '';

    let data;
    try {
      data = await _cf('GET', '/api/ai/tools');
    } catch (e) {
      $tlBody.innerHTML = `<div class="ai-tl-loading" style="color:var(--red)">加载失败：${_esc(String(e))}</div>`;
      return;
    }

    if ($tlTotal) $tlTotal.textContent = `共 ${data.total} 个`;

    let html = '';
    for (const g of _TL_GROUPS) {
      const tools = data[g.key] || [];
      if (!tools.length) continue;
      html += `<div class="ai-tl-group">
        <div class="ai-tl-group-hdr">
          ${_esc(g.label)}
          <span class="ai-tl-count">${tools.length}</span>
          <span class="ai-tl-gbadge ${g.badgeClass}">${_esc(g.badgeText)}</span>
        </div>
        ${tools.map(t => `
          <div class="ai-tl-row">
            <div class="ai-tl-name">${_esc(t.name)}</div>
            <div class="ai-tl-desc">${_esc(t.description)}</div>
            ${t.params.length ? `<div class="ai-tl-params">${
              t.params.map(p => `<span class="ai-tl-param">${_esc(p)}</span>`).join('')
            }</div>` : ''}
          </div>`).join('')}
      </div>`;
    }
    $tlBody.innerHTML = html;
  }

  function closeToolList() {
    $tlOverlay.classList.add('hidden');
  }

  // ── 侧边栏状态栏辅助 ──────────────────────────────────────────────────────

  function _sbStartBalPolling() {
    clearInterval(_sbBalTimer);
    clearInterval(_sbBalTickTimer);
    _sbFetchBalance();
    _sbBalTimer     = setInterval(_sbFetchBalance,  5 * 60 * 1000);
    _sbBalTickTimer = setInterval(_sbTickBalTime,   60 * 1000);
    // 点击余额强制刷新
    if ($sbBal && !$sbBal._clickBound) {
      $sbBal._clickBound = true;
      $sbBal.addEventListener('click', () => {
        $sbBal.style.opacity = '.5';
        _sbFetchBalance().finally(() => { $sbBal.style.opacity = ''; });
      });
    }
    _sbRenderUsage();
  }

  async function _sbFetchBalance() {
    try {
      const res = await _cf('GET', '/api/ai/balance').catch(() => null);
      if (res && res.supported) {
        _sbLastBalVal  = parseFloat(res.balance);
        _sbLastBalTime = Date.now();
        _sbRenderBal();
      }
    } catch (_) {}
  }

  function _sbTickBalTime() {
    if (_sbLastBalTime != null) _sbRenderBal();
  }

  function _sbRenderBal() {
    if (!$sbBal || _sbLastBalVal == null) return;
    const mins = Math.floor((Date.now() - _sbLastBalTime) / 60000);
    $sbBal.textContent = `¥${_sbLastBalVal.toFixed(2)}`;
    $sbBal.title = '点击刷新余额';
    $sbBal.className = 'ai-sb-bal' +
      (_sbLastBalVal <= 0 ? ' bal-empty' : _sbLastBalVal < 1 ? ' bal-low' : '');
    // 内联刷新时间
    if ($sbRefreshTime) {
      $sbRefreshTime.textContent = mins < 1 ? '刚刚' : `${mins}m前`;
    }
  }

  /** 估算每 1K token 的 CNY 成本 */
  function _sbCostPerKToken(model) {
    const m = (model || '').toLowerCase();
    if (m.includes('deepseek'))    return 0.002;
    if (m.includes('anthropic') || m.includes('claude'))  return 0.05;
    if (m.includes('openai') || m.includes('gpt'))        return 0.03;
    return 0.01;
  }

  /** 记录一次消耗到 localStorage */
  function _sbTrackUsage(totalTokens, model) {
    if (!totalTokens || totalTokens <= 0) return;
    const cost = (totalTokens / 1000) * _sbCostPerKToken(model);
    const dk = _sbDayKey();
    const wk = _sbWeekKey();
    try {
      localStorage.setItem(dk, ((parseFloat(localStorage.getItem(dk)) || 0) + cost).toFixed(4));
      localStorage.setItem(wk, ((parseFloat(localStorage.getItem(wk)) || 0) + cost).toFixed(4));
    } catch (_) {}
    _sbRenderUsage();
  }

  function _sbRenderUsage() {
    if (!$sbUsage) return;
    try {
      const todayCost = parseFloat(localStorage.getItem(_sbDayKey())) || 0;
      const weekCost  = parseFloat(localStorage.getItem(_sbWeekKey())) || 0;
      if (todayCost <= 0 && weekCost <= 0) {
        $sbUsage.textContent = '';
        if ($sbUsageSep) $sbUsageSep.classList.add('hidden');
        return;
      }
      $sbUsage.textContent = `今日¥${todayCost.toFixed(3)} · 本周¥${weekCost.toFixed(3)}`;
      if ($sbUsageSep) $sbUsageSep.classList.remove('hidden');
    } catch (_) {}
  }

  function _sbSetModel(model) {
    if (!$sbModel) return;
    const short = model.replace(/^(anthropic|deepseek|openai|ollama)\//, '');
    $sbModel.textContent = short;
    $sbModel.title = model;
    try { localStorage.setItem(_lsk('ai_last_model'), model); } catch (_) {}
  }

  function _sbSetIter(count) {
    if ($sbIter) $sbIter.textContent = `${count}轮`;
  }

  // ── 工具函数 ───────────────────────────────────────────────────────────────

  // ── 语音输入 ─────────────────────────────────────────────────────────────
  function _initSpeech() {
    if (!$micBtn) return;
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      $micBtn.classList.add('unsupported');
      $micBtn.title = '当前环境不支持语音输入';
      return;
    }
    _recognition = new SR();
    _recognition.lang = 'zh-CN';
    _recognition.continuous = false;      // 停顿后自动结束
    _recognition.interimResults = true;

    _recognition.onresult = e => {
      let interim = '';
      let final = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) final += t;
        else interim += t;
      }
      if (final) {
        $input.value = ($input.value + final).trimStart();
        autoResizeInput();
      } else if (interim) {
        $input.placeholder = interim + '…';
      }
    };

    _recognition.onend = () => {
      _recognizing = false;
      $input.placeholder = '输入消息，Enter 发送，Shift+Enter 换行…';
      if ($micBtn) {
        $micBtn.classList.remove('recording');
        $micBtn.title = '语音输入';
      }
      // 不调 focus()，不抢输入框焦点
    };

    _recognition.onerror = e => {
      _recognizing = false;
      if ($micBtn) $micBtn.classList.remove('recording');
      $input.placeholder = '输入消息，Enter 发送，Shift+Enter 换行…';
      if (e.error !== 'no-speech' && e.error !== 'aborted') {
        console.warn('[AiAssistant] 语音识别错误:', e.error);
      }
    };
  }

  function _toggleMic() {
    if (!_recognition) return;
    if (_recognizing) {
      _recognition.stop();
      return;
    }
    try {
      _recognition.start();
      _recognizing = true;
      $micBtn.classList.add('recording');
      $micBtn.title = '识别中，点击停止';
    } catch (e) {
      console.warn('[AiAssistant] 语音启动失败:', e);
    }
  }

  function _setSendBtnStopping(stopping) {
    if (stopping) {
      $sendBtn.disabled = false;
      $sendBtn.classList.add('stopping');
      $sendBtn.title = '停止';
      $sendBtn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><rect x="4" y="4" width="16" height="16" rx="2"/></svg>`;
    } else {
      $sendBtn.classList.remove('stopping');
      $sendBtn.title = '发送';
      $sendBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>`;
    }
  }

  function _copyBubbleMd(text, btn) {
    navigator.clipboard.writeText(text || '').then(() => {
      btn.classList.add('copied');
      const prev = btn.innerHTML;
      btn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>`;
      setTimeout(() => { btn.classList.remove('copied'); btn.innerHTML = prev; }, 1500);
    }).catch(() => {
      // 降级：创建临时 textarea
      const ta = document.createElement('textarea');
      ta.value = text || '';
      ta.style.cssText = 'position:fixed;top:-9999px;left:-9999px;opacity:0;';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      ta.remove();
    });
  }

  function _quoteBubble(text) {
    if (!text) return;
    // 取前 3 行或 200 字符，加引用前缀
    const lines = text.split('\n').slice(0, 3);
    let excerpt = lines.join('\n');
    if (excerpt.length > 200) excerpt = excerpt.slice(0, 200) + '…';
    const quoted = excerpt.split('\n').map(l => `> ${l}`).join('\n');
    const cur = $input.value;
    $input.value = cur ? `${quoted}\n\n${cur}` : `${quoted}\n\n`;
    $input.focus();
    // 触发高度自适应
    $input.dispatchEvent(new Event('input'));
    $input.scrollTop = $input.scrollHeight;
  }

  function _esc(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function _getAvatarUrl() {
    if (_IS_POPUP) return _authUser?.avatar_url || '';
    try { return window.top?._authUser?.avatar_url || window.parent?._authUser?.avatar_url || ''; }
    catch (_) { return ''; }
  }

  function _cf(method, path, body) {
    const fn = window._cloudFetch || window.top?._cloudFetch || window.parent?._cloudFetch;
    if (!fn) return Promise.reject(new Error('_cloudFetch 未就绪'));
    if (method === 'GET') return fn(path);
    const opts = { method };
    if (body !== undefined) opts.body = JSON.stringify(body);
    return fn(path, opts);
  }

  function _getUserGid() {
    if (_IS_POPUP) return _authUser?.gid || '';
    try { return window.top?._authUser?.gid || window.parent?._authUser?.gid || ''; }
    catch (_) { return ''; }
  }

  function _getAuthMode() {
    if (_IS_POPUP) return _authMode || 'local';
    try { return window.top?._authMode || window.parent?._authMode || 'local'; }
    catch (_) { return 'local'; }
  }

  function _getAuthToken() {
    if (_IS_POPUP) return _authToken || '';
    try { return window.top?._authToken || window.parent?._authToken || ''; }
    catch (_) { return ''; }
  }

  async function _getContext() {
    try {
      const top = window.top || window.parent;
      const ctx = {
        current_page: top?._currentTabKey || '',
        project_name: top?._currentProjectName || '',
      };
      // 画布上下文注入（仅当开关打开且画布有节点时）
      if (_wfcCtxOn && _wfCanvas && _wfCanvas._nodes.length > 0) {
        ctx.canvas_context = _wfCanvas.toInjectText();
      }
      // 底部容器上下文（沙盘节点 + iframe 操作事件）
      if (_wfcCtxOn && _wfCanvas) {
        const bottomCtx = _wfCanvas.getBottomContext?.();
        if (bottomCtx) ctx.bottom_context = bottomCtx;
      }
      // 读取 WFC 独立窗口画布状态
      if (_wfcCtxOn) {
        try {
          const wfcState = await window.electronAPI?.wfcGetCachedState?.();
          if (wfcState) ctx.canvas_context = wfcState;
        } catch (_) {}
      }
      return ctx;
    } catch (_) { return {}; }
  }

  // ── Skills ─────────────────────────────────────────────────────────────────

  let _skills = [];
  let _skillDropIdx = -1;
  let _skillDropFiltered = [];
  let _pendingSkill = null;    // { skill, content } 等待变量填写

  async function _loadSkills() {
    try {
      const skillRes = await _cf('GET', `/api/skills?scope_filter=all`);
      const list = Array.isArray(skillRes) ? skillRes : (skillRes?.skills || []);
      _skills = Array.isArray(list) ? list : [];
    } catch (_) {
      _skills = [];
    }
    _renderSkillPanel();
  }

  function _renderSkillPanel() {
    const $cards = document.getElementById('aiSkillCards');
    const $empty = document.getElementById('aiSkillEmpty');
    if (!$cards) return;

    const pinned = _skills.filter(s => s.status === 'active' && (s.is_pinned || s.scope === 'global')).slice(0, 8);
    const rest = _skills.filter(s => s.status === 'active' && !pinned.includes(s)).slice(0, Math.max(0, 8 - pinned.length));
    const visible = [...pinned, ...rest].slice(0, 8);

    if (!visible.length) {
      $cards.innerHTML = '';
      if ($empty) $empty.style.display = '';
      return;
    }
    if ($empty) $empty.style.display = 'none';
    $cards.innerHTML = visible.map(s => {
      const iconSvg = s.icon ? `<span class="ai-skill-card-icon">${_esc(s.icon)}</span>`
        : `<span class="ai-skill-card-icon ${s.skill_type || ''}">${_skillTypeIcon(s.skill_type)}</span>`;
      return `<div class="ai-skill-card" data-gid="${s.gid}" title="${_esc(s.description || s.title)}">
        ${iconSvg}
        <span class="ai-skill-card-name">${_esc(s.title)}</span>
      </div>`;
    }).join('');

    $cards.querySelectorAll('.ai-skill-card').forEach(el => {
      el.addEventListener('click', () => {
        const gid = el.dataset.gid;
        const skill = _skills.find(s => s.gid === gid);
        if (skill) _activateSkillCard(skill);
      });
    });
  }

  function _skillTypeIcon(type) {
    if (type === 'prompt')
      return `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>`;
    if (type === 'tool')
      return `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.7 6.3a1 1 0 010 1.4l-8 8a1 1 0 01-1.4 0l-2-2a1 1 0 010-1.4l8-8a1 1 0 011.4 0l2 2z"/><path d="M20 2l-2 2 2 2 2-2z"/></svg>`;
    if (type === 'flow')
      return `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polygon points="10 8 16 12 10 16 10 8"/></svg>`;
    return `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="4"/></svg>`;
  }

  // @触发选择器
  function _checkSkillTrigger() {
    const val  = $input.value;
    const pos  = $input.selectionStart;
    // 找光标左侧最近的 @
    const chunk = val.slice(0, pos);
    const atIdx = chunk.lastIndexOf('@');
    if (atIdx < 0) { _hideSkillDrop(); return; }
    // @ 后面必须没有空格
    const query = chunk.slice(atIdx + 1);
    if (query.includes(' ') || query.includes('\n')) { _hideSkillDrop(); return; }

    const q = query.toLowerCase();
    _skillDropFiltered = _skills.filter(s =>
      s.status === 'active' &&
      (s.name.toLowerCase().includes(q) || s.title.includes(query))
    ).slice(0, 8);

    if (!_skillDropFiltered.length) { _hideSkillDrop(); return; }
    _skillDropIdx = 0;
    _showSkillDrop();
  }

  function _showSkillDrop() {
    const $drop = document.getElementById('aiSkillDrop');
    if (!$drop) return;
    _skillDropIdx = Math.max(0, Math.min(_skillDropIdx, _skillDropFiltered.length - 1));
    $drop.innerHTML = _skillDropFiltered.map((s, i) => {
      const icon = s.icon || _skillTypeIcon(s.skill_type);
      return `<div class="ai-skill-drop-item${i === _skillDropIdx ? ' active' : ''}" data-idx="${i}">
        <span class="ai-skill-drop-badge ${s.skill_type}">${s.skill_type}</span>
        <span class="ai-skill-drop-name">@${_esc(s.name)}</span>
        <span class="ai-skill-drop-title">${_esc(s.title)}</span>
      </div>`;
    }).join('');
    $drop.classList.remove('hidden');

    $drop.querySelectorAll('.ai-skill-drop-item').forEach(el => {
      el.addEventListener('mousedown', e => {
        e.preventDefault();
        const idx = parseInt(el.dataset.idx);
        _skillDropIdx = idx;
        _selectSkill(_skillDropFiltered[idx]);
      });
    });
  }

  function _hideSkillDrop() {
    document.getElementById('aiSkillDrop')?.classList.add('hidden');
    _skillDropFiltered = [];
    _skillDropIdx = -1;
  }

  function _handleSkillDropKeys(e) {
    const $drop = document.getElementById('aiSkillDrop');
    if (!$drop || $drop.classList.contains('hidden')) return;
    if (!_skillDropFiltered.length) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      _skillDropIdx = (_skillDropIdx + 1) % _skillDropFiltered.length;
      _showSkillDrop();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      _skillDropIdx = (_skillDropIdx - 1 + _skillDropFiltered.length) % _skillDropFiltered.length;
      _showSkillDrop();
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (_skillDropFiltered[_skillDropIdx]) {
        _selectSkill(_skillDropFiltered[_skillDropIdx]);
      }
    } else if (e.key === 'Escape') {
      _hideSkillDrop();
    }
  }

  function _selectSkill(skill) {
    _hideSkillDrop();
    _activateSkillCard(skill, true /* fromAtTrigger */);
  }

  function _activateSkillCard(skill, fromAtTrigger = false) {
    let content = {};
    try { content = JSON.parse(skill.content || '{}'); } catch (_) {}

    if (skill.skill_type === 'prompt') {
      const vars = content.variables || [];
      if (vars.length > 0) {
        // 弹出变量填写 modal
        _pendingSkill = { skill, content, fromAtTrigger };
        _openSkillVarModal(skill, vars);
      } else {
        // 直接展开模板
        const text = content.template || '';
        _insertSkillText(text, skill, fromAtTrigger);
      }
    } else if (skill.skill_type === 'tool') {
      _insertSkillText(`请使用工具 @${skill.name} 完成：`, skill, fromAtTrigger);
    } else if (skill.skill_type === 'flow') {
      _insertSkillText(`请触发工作流「${skill.title}」`, skill, fromAtTrigger);
    }
  }

  function _insertSkillText(text, skill, fromAtTrigger) {
    if (fromAtTrigger) {
      // 替换 @name 部分
      const val = $input.value;
      const pos = $input.selectionStart;
      const chunk = val.slice(0, pos);
      const atIdx = chunk.lastIndexOf('@');
      if (atIdx >= 0) {
        $input.value = val.slice(0, atIdx) + text + val.slice(pos);
        const newPos = atIdx + text.length;
        $input.setSelectionRange(newPos, newPos);
      } else {
        $input.value = text;
      }
    } else {
      // 追加到输入框末尾
      const sep = $input.value ? '\n' : '';
      $input.value = $input.value + sep + text;
    }
    autoResizeInput();
    $input.focus();
  }

  // 变量 modal
  function _openSkillVarModal(skill, vars) {
    const $overlay = document.getElementById('aiSkillVarOverlay');
    const $title   = document.getElementById('aiSkillVarTitle');
    const $body    = document.getElementById('aiSkillVarBody');
    if (!$overlay) return;

    $title.textContent = `填写 Skill 变量 — ${skill.title}`;
    $body.innerHTML = vars.map(v => `
      <div class="ai-skill-var-field">
        <label>${_esc(v.label || v.name)}${v.required ? ' *' : ''}</label>
        <input type="text" data-var="${_esc(v.name)}"
               value="${_esc(v.default || '')}"
               placeholder="${_esc(v.label || v.name)}" />
      </div>`).join('');
    $overlay.classList.remove('hidden');
    // 聚焦第一个输入框
    setTimeout(() => $body.querySelector('input')?.focus(), 50);
  }

  function _closeSkillVarModal() {
    document.getElementById('aiSkillVarOverlay')?.classList.add('hidden');
    _pendingSkill = null;
  }

  function _confirmSkillVars() {
    if (!_pendingSkill) { _closeSkillVarModal(); return; }
    const { skill, content, fromAtTrigger } = _pendingSkill;

    // 收集变量值
    const vars = {};
    document.querySelectorAll('#aiSkillVarBody input[data-var]').forEach(inp => {
      vars[inp.dataset.var] = inp.value;
    });

    // 渲染模板
    let tpl = content.template || '';
    for (const [k, v] of Object.entries(vars)) {
      tpl = tpl.replaceAll(`{{${k}}}`, v);
    }
    _closeSkillVarModal();
    _insertSkillText(tpl, skill, fromAtTrigger);
  }

  // ── 画布面板 ───────────────────────────────────────────────────────────────

  function _ensureWfCanvas() {
    if (_wfCanvas) return;
    if (!window.WorkflowCanvas) return;
    _wfCanvas = new WorkflowCanvas({
      boardEl:  document.getElementById('wfcBoard'),
      paletteEl: document.getElementById('wfcPalette'),
      svgEl:    document.getElementById('wfcSvg'),
      lanesEl:  document.getElementById('wfcLanes'),
      qaQEl:    document.getElementById('wfcQCol'),
      qaAEl:    document.getElementById('wfcACol'),
      footerEl: document.getElementById('wfcFooter'),
      statsEl:  document.getElementById('wfcStats'),
    });
    _wfCanvas.init();
    // 全局暴露，供 postMessage 处理器调用 _recordCtxEvent
    window._wfc = _wfCanvas;

    // 添加泳道按钮
    const lanesEl = document.getElementById('wfcLanes');
    if (lanesEl) {
      const addBtn = document.createElement('button');
      addBtn.className = 'wfc-add-lane';
      addBtn.innerHTML = `<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg> 添加泳道`;
      addBtn.addEventListener('click', () => _wfCanvas.addLane());
      lanesEl.appendChild(addBtn);
    }
  }

  function _toggleWfcCtx() {
    _wfcCtxOn = !_wfcCtxOn;
    localStorage.setItem(_lsk('wfc:context-on'), String(_wfcCtxOn));
    _updateWfcCtxBtn();
  }

  function _updateWfcCtxBtn() {
    const btn   = document.getElementById('wfcCtxToggle');
    const label = document.getElementById('wfcCtxLabel');
    if (!btn) return;
    if (_wfcCtxOn) {
      btn.classList.add('ctx-on');
      if (label) label.textContent = '上下文 开';
      btn.title = '已开启：每次发送消息自动注入画布上下文（点击关闭）';
    } else {
      btn.classList.remove('ctx-on');
      if (label) label.textContent = '上下文 关';
      btn.title = '已关闭：Agent 不自动读取画布，节省 token（点击开启）';
    }
  }

  function _openCanvasPanel() {
    if (!$canvasPanel || !$canvasPanel.classList.contains('collapsed')) return;
    $canvasPanel.classList.remove('collapsed');
    _ensureWfCanvas();
    // 展开时拓宽窗口（popup 模式调自身，否则调主窗口）
    const currentW = window.outerWidth || 1200;
    if (_IS_POPUP) {
      window.electronAPI?.resizeSelf?.(currentW + 460);
    } else {
      window.electronAPI?.setMainWidth?.(currentW + 460);
    }
    // 重绘连线（面板展开后位置有变）
    setTimeout(() => _wfCanvas?._redrawConnections(), 200);
  }

  function _closeCanvasPanel() {
    if (!$canvasPanel || $canvasPanel.classList.contains('collapsed')) return;
    $canvasPanel.classList.add('collapsed');
    const currentW = window.outerWidth || 1200;
    if (_IS_POPUP) {
      window.electronAPI?.resizeSelf?.(Math.max(620, currentW - 460));
    } else {
      window.electronAPI?.setMainWidth?.(Math.max(900, currentW - 460));
    }
  }

  function _toggleCanvasPanel() {
    // 优先打开独立 WFC 窗口；不在 Electron 环境时降级到内嵌面板
    if (window.electronAPI?.openWfcWindow) {
      window.electronAPI.openWfcWindow();
    } else if ($canvasPanel?.classList.contains('collapsed')) {
      _openCanvasPanel();
    } else {
      _closeCanvasPanel();
    }
  }

  function _injectCanvasToInput() {
    if (!_wfCanvas) return;
    const text = _wfCanvas.toInjectText();
    if (!text || !$input) return;
    $input.value = ($input.value ? $input.value + '\n\n' : '') + text;
    $input.focus();
    autoResizeInput();
  }

  function _toggleWfcMode() {
    const btn = document.getElementById('wfcModeBtn');
    if (!btn) return;
    const cur = btn.dataset.mode;
    const next = cur === 'explore' ? 'execute' : 'explore';
    btn.dataset.mode = next;
    btn.textContent = next === 'execute' ? '执行模式' : '探索模式';
    if (_wfCanvas) _wfCanvas._mode = next;
  }

  function _wfcSave() {
    if (!_wfCanvas) return;
    const name = prompt('保存为（名称）：', '画布 ' + new Date().toLocaleString('zh-CN', {hour:'2-digit', minute:'2-digit'}));
    if (!name) return;
    const ownerGid = _getUserGid() || 'local';
    _wfCanvas.save(name, ownerGid).then(res => {
      if (res?.gid) {
        _wfCanvas._savedGid = res.gid; // 记住 gid 供后续覆盖保存
      }
    });
  }

  async function _wfcLoad() {
    if (!_wfCanvas) { _ensureWfCanvas(); }
    const ownerGid = _getUserGid() || 'local';
    const saves = await _wfCanvas.listSaves(ownerGid);
    if (saves.length === 0) { alert('暂无保存的画布'); return; }
    _showWfcSavesModal(saves, ownerGid);
  }

  function _showWfcSavesModal(saves, ownerGid) {
    let overlay = document.getElementById('wfcSavesOverlay');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.className = 'wfc-saves-overlay';
      overlay.id = 'wfcSavesOverlay';
      overlay.innerHTML = `
        <div class="wfc-saves-modal">
          <div class="wfc-saves-title">加载画布</div>
          <div class="wfc-saves-list" id="wfcSavesList"></div>
          <div class="wfc-saves-footer">
            <button class="wfc-saves-close" id="wfcSavesClose">关闭</button>
          </div>
        </div>`;
      document.body.appendChild(overlay);
      document.getElementById('wfcSavesClose')?.addEventListener('click', () => {
        overlay.classList.add('hidden');
      });
    }
    const list = document.getElementById('wfcSavesList');
    list.innerHTML = '';
    saves.forEach(s => {
      const item = document.createElement('div');
      item.className = 'wfc-saves-item';
      const sharedTag = s.is_shared
        ? `<span style="font-size:9px;color:var(--green);margin-left:4px">共享</span>` : '';
      item.innerHTML = `
        <span class="wfc-saves-item-name">${s.title}${sharedTag}</span>
        <span style="font-size:10px;color:var(--text-muted)">${(s.updated_at||'').slice(0,16)}</span>
        <button class="wfc-saves-item-del" title="删除">×</button>`;
      item.querySelector('.wfc-saves-item-del').addEventListener('click', async e => {
        e.stopPropagation();
        await _wfCanvas.deleteSave(s.gid);
        const updated = await _wfCanvas.listSaves(ownerGid);
        _showWfcSavesModal(updated, ownerGid);
      });
      item.addEventListener('click', () => {
        _wfCanvas.load(s.gid);
        _wfCanvas._savedGid = s.gid;
        overlay.classList.add('hidden');
      });
      list.appendChild(item);
    });
    overlay.classList.remove('hidden');
  }

  function _wfcToSkill() {
    if (!_wfCanvas) return;
    const json = JSON.stringify(_wfCanvas.toJSON(), null, 2);
    const text = `请根据以下工作流画布 JSON，生成一个 Skill 定义（包含名称、描述、执行步骤）：\n\`\`\`json\n${json}\n\`\`\`\n生成后请以 JSON 格式返回 Skill 定义。`;
    if ($input) {
      $input.value = text;
      $input.focus();
      autoResizeInput();
    }
  }

  // ── 工具结果处理（generate_canvas） ──────────────────────────────────────
  function _handleCanvasTool(tc) {
    if (tc.name !== 'generate_canvas') return false;
    const result = tc.result;
    if (result?.status === 'canvas_generated' && result?.canvas) {
      if (window.electronAPI?.wfcOpenWithData) {
        // 发送到独立 WFC 窗口
        window.electronAPI.wfcOpenWithData(result.canvas);
      } else {
        // 降级：内嵌画布面板
        _ensureWfCanvas();
        _wfCanvas.fromJSON(result.canvas);
        _openCanvasPanel();
      }
    }
    return true;
  }

  // ── 工具结果处理（navigate_to_page） ────────────────────────────────────
  function _handleNavigateTool(tc) {
    if (tc.name !== 'navigate_to_page') return false;
    const r = tc.result;
    if (r?.status === 'navigate' && r.view_id) {
      if (_IS_POPUP) {
        window.electronAPI?.navigateMain?.({ viewId: r.view_id, params: r.params || {} });
      } else {
        window.parent?.postMessage({ type: 'ai:navigate', viewId: r.view_id, params: r.params || {} }, '*');
      }
    }
    return true;
  }

  // ── 工具结果处理（open_in_container） ──────────────────────────────────
  function _handleOpenContainerTool(tc) {
    if (tc.name !== 'open_in_container') return false;
    const r = tc.result;
    if (r?.status === 'open_container_tab' && r.tab_id && r.url) {
      // 优先：在本窗口底部容器中打开（ai_chat 弹出版）
      if (_wfCanvas) {
        _wfCanvas.addBottomTab(r.tab_id, r.title || r.page_id, 'local', { url: r.url });
        _openCanvasPanel?.();
      }
      // 同时：推送到独立 WFC 窗口（如已打开）
      window.electronAPI?.wfcAddBottomTab?.({ tabId: r.tab_id, title: r.title || r.page_id, url: r.url });
    }
    return true;
  }

  // ── 话题讨论区（WFC 沙盘配套） ─────────────────────────────────────────────
  // Topic: { id, title, status:'open'|'resolved', createdBy:'ai'|'user', collapsed, questions:Question[] }
  // Question: { id, topicId, parentId, text, options:Option[], selectedOptionIds:string[], freeText, status }
  // Option: { id, text, createdBy:'ai'|'user' }
  let _topics = [];

  const _genTopicId = (p = 'e') => p + Date.now() + '_' + Math.random().toString(36).slice(2, 7);

  function _createTopic(title, createdBy = 'user') {
    const topic = { id: _genTopicId('t'), title, status: 'open', createdBy, collapsed: false, questions: [] };
    _topics.push(topic);
    _renderTopics();
    return topic;
  }

  function _addQuestion(topicId, text, parentId = null) {
    const topic = _topics.find(t => t.id === topicId);
    if (!topic || !text.trim()) return null;
    const q = { id: _genTopicId('q'), topicId, parentId: parentId || null, text: text.trim(),
                 options: [], selectedOptionIds: [], freeText: '', status: 'open' };
    topic.questions.push(q);
    _renderTopics();
    return q;
  }

  function _addOption(topicId, questionId, text, createdBy = 'user') {
    const topic = _topics.find(t => t.id === topicId);
    if (!topic) return null;
    const q = topic.questions.find(q => q.id === questionId);
    if (!q) return null;
    const opt = { id: _genTopicId('o'), text, createdBy };
    q.options.push(opt);
    _renderTopics();
    return opt;
  }

  function _toggleOption(topicId, questionId, optionId) {
    const topic = _topics.find(t => t.id === topicId);
    if (!topic) return;
    const q = topic.questions.find(q => q.id === questionId);
    if (!q) return;
    const idx = q.selectedOptionIds.indexOf(optionId);
    if (idx >= 0) q.selectedOptionIds.splice(idx, 1);
    else q.selectedOptionIds.push(optionId);
    _renderTopics();
  }

  function _setFreeText(topicId, questionId, text) {
    const topic = _topics.find(t => t.id === topicId);
    if (!topic) return;
    const q = topic.questions.find(q => q.id === questionId);
    if (q) q.freeText = text;
  }

  function _resolveQuestion(topicId, questionId) {
    const topic = _topics.find(t => t.id === topicId);
    if (!topic) return;
    const q = topic.questions.find(q => q.id === questionId);
    if (q) q.status = q.status === 'resolved' ? 'open' : 'resolved';
    _renderTopics();
  }

  function _resolveTopic(topicId) {
    const topic = _topics.find(t => t.id === topicId);
    if (topic) topic.status = topic.status === 'resolved' ? 'open' : 'resolved';
    _renderTopics();
  }

  function _deleteTopic(topicId) {
    _topics = _topics.filter(t => t.id !== topicId);
    _renderTopics();
  }

  function _deleteQuestion(topicId, questionId) {
    const topic = _topics.find(t => t.id === topicId);
    if (!topic) return;
    const toRemove = new Set([questionId]);
    let changed = true;
    while (changed) {
      changed = false;
      topic.questions.forEach(q => {
        if (q.parentId && toRemove.has(q.parentId) && !toRemove.has(q.id)) {
          toRemove.add(q.id); changed = true;
        }
      });
    }
    topic.questions = topic.questions.filter(q => !toRemove.has(q.id));
    _renderTopics();
  }

  // 从 AI 导入话题结构
  function _importTopic(data) {
    const topic = _createTopic(data.title || '新话题', 'ai');
    const qIdMap = {};
    (data.questions || []).forEach(qData => {
      const realParentId = qData.parentId ? qIdMap[qData.parentId] : null;
      const q = _addQuestion(topic.id, qData.text, realParentId);
      if (q) {
        qIdMap[qData.id] = q.id;
        (qData.options || []).forEach(opt => _addOption(topic.id, q.id, opt.text, 'ai'));
      }
    });
    setTimeout(() => {
      document.getElementById('topic_disc_' + topic.id)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }, 50);
  }

  // ── 话题渲染层 ─────────────────────────────────────────────────────────────
  function _esc(s) {
    return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;')
      .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  function _renderTopics() {
    const $t = document.getElementById('aiTopics');
    if (!$t) return;
    $t.innerHTML = '';
    if (_topics.length === 0) {
      const empty = document.createElement('div');
      empty.style.cssText = 'padding:12px 8px;text-align:center;color:var(--text-muted);font-size:11px;line-height:1.6;';
      empty.textContent = '点击 + 新建话题，或让小柔自动创建结构化讨论';
      $t.appendChild(empty);
      return;
    }
    _topics.forEach(topic => $t.appendChild(_buildTopicEl(topic)));
  }

  function _buildTopicEl(topic) {
    const el = document.createElement('div');
    el.className = 'ai-topic' + (topic.collapsed ? ' collapsed' : '');
    el.id = 'topic_disc_' + topic.id;

    const hdr = document.createElement('div');
    hdr.className = 'ai-topic-hdr';
    hdr.innerHTML = `
      <span class="ai-topic-arrow">▾</span>
      <span class="ai-topic-title" title="${_esc(topic.title)}">${_esc(topic.title)}</span>
      <span class="ai-topic-status ${topic.status}">${topic.status === 'resolved' ? '已解决' : '进行中'}</span>
      <button class="ai-topic-act-btn" data-act="resolve" title="${topic.status === 'resolved' ? '重新打开' : '标记解决'}">✓</button>
      <button class="ai-topic-act-btn danger" data-act="delete" title="删除话题">×</button>`;
    hdr.addEventListener('click', e => {
      const act = e.target.closest('[data-act]')?.dataset.act;
      if (act === 'resolve') { e.stopPropagation(); _resolveTopic(topic.id); return; }
      if (act === 'delete')  { e.stopPropagation(); if (confirm('删除此话题？')) _deleteTopic(topic.id); return; }
      topic.collapsed = !topic.collapsed;
      el.classList.toggle('collapsed', topic.collapsed);
    });
    const titleSpan = hdr.querySelector('.ai-topic-title');
    titleSpan.addEventListener('dblclick', e => {
      e.stopPropagation();
      const input = document.createElement('input');
      input.value = topic.title;
      input.style.cssText = 'flex:1;background:var(--bg3);border:1px solid var(--accent);color:var(--text);font-size:11px;font-weight:600;border-radius:3px;padding:0 4px;outline:none;width:100%;';
      titleSpan.replaceWith(input);
      input.focus(); input.select();
      const commit = () => { topic.title = input.value.trim() || topic.title; _renderTopics(); };
      input.addEventListener('blur', commit);
      input.addEventListener('keydown', e2 => {
        if (e2.key === 'Enter') { e2.preventDefault(); commit(); }
        if (e2.key === 'Escape') _renderTopics();
      });
    });
    el.appendChild(hdr);

    const body = document.createElement('div');
    body.className = 'ai-topic-body';
    topic.questions.filter(q => !q.parentId).forEach(q => body.appendChild(_buildQuestionEl(q, topic, 0)));
    const addBtn = document.createElement('button');
    addBtn.className = 'ai-topic-add-q';
    addBtn.textContent = '+ 添加问题';
    addBtn.addEventListener('click', () => {
      const text = prompt('输入问题：');
      if (text?.trim()) _addQuestion(topic.id, text.trim(), null);
    });
    body.appendChild(addBtn);
    el.appendChild(body);
    return el;
  }

  function _buildQuestionEl(q, topic, depth) {
    const el = document.createElement('div');
    el.className = `ai-question depth-${depth}` + (q.status === 'resolved' ? ' resolved' : '');
    const qText = document.createElement('div');
    qText.className = 'ai-q-text';
    qText.textContent = q.text;
    el.appendChild(qText);

    if (q.options.length > 0) {
      const optWrap = document.createElement('div');
      optWrap.className = 'ai-q-options';
      q.options.forEach(opt => {
        const chip = document.createElement('button');
        chip.className = 'ai-opt-chip' + (opt.createdBy === 'ai' ? ' ai' : '') +
          (q.selectedOptionIds.includes(opt.id) ? ' selected' : '');
        chip.textContent = opt.text;
        chip.addEventListener('click', () => _toggleOption(topic.id, q.id, opt.id));
        optWrap.appendChild(chip);
      });
      const addOpt = document.createElement('button');
      addOpt.className = 'ai-opt-chip';
      addOpt.style.cssText = 'border-style:dashed;opacity:.6;';
      addOpt.textContent = '+ 选项';
      addOpt.addEventListener('click', () => {
        const text = prompt('输入选项文本：');
        if (text?.trim()) _addOption(topic.id, q.id, text.trim(), 'user');
      });
      optWrap.appendChild(addOpt);
      el.appendChild(optWrap);
    }

    const ft = document.createElement('textarea');
    ft.className = 'ai-q-freetext' + (q.freeText ? ' has-value' : '');
    ft.placeholder = '补充说明…';
    ft.value = q.freeText || '';
    ft.rows = 1;
    ft.addEventListener('input', () => {
      _setFreeText(topic.id, q.id, ft.value);
      ft.classList.toggle('has-value', ft.value.trim().length > 0);
      ft.style.height = 'auto';
      ft.style.height = Math.min(60, ft.scrollHeight) + 'px';
    });
    el.appendChild(ft);

    const actions = document.createElement('div');
    actions.className = 'ai-q-actions';
    [
      ['回复', () => {
        const text = prompt('输入子问题：');
        if (text?.trim()) _addQuestion(topic.id, text.trim(), q.id);
      }, false],
      [q.status === 'resolved' ? '重开' : '✓解决', () => _resolveQuestion(topic.id, q.id), false],
      ['删除', () => { if (confirm('删除此问题？')) _deleteQuestion(topic.id, q.id); }, true],
    ].forEach(([label, fn, isDanger]) => {
      const b = document.createElement('button');
      b.className = 'ai-q-act-btn' + (isDanger ? ' danger' : '');
      b.textContent = label;
      b.addEventListener('click', fn);
      actions.appendChild(b);
    });
    el.appendChild(actions);

    const children = topic.questions.filter(cq => cq.parentId === q.id);
    if (children.length > 0) {
      const childWrap = document.createElement('div');
      childWrap.className = 'ai-q-children';
      children.forEach(child => childWrap.appendChild(_buildQuestionEl(child, topic, Math.min(depth + 1, 2))));
      el.appendChild(childWrap);
    }
    return el;
  }

  // ── 话题序列化 + 整理到画布 ────────────────────────────────────────────────
  function _serializeTopicsForChat() {
    if (_topics.length === 0) return null;
    return _topics.map(topic => {
      let s = `[话题: ${topic.title}${topic.status === 'resolved' ? ' ✓' : ''}]`;
      topic.questions.filter(q => !q.parentId).forEach((q, i) => {
        s += '\n' + _serializeQuestion(q, topic, `Q${i + 1}`);
      });
      return s;
    }).join('\n\n');
  }

  function _serializeQuestion(q, topic, prefix) {
    const selTxts = q.options.filter(o => q.selectedOptionIds.includes(o.id)).map(o => o.text);
    let s = `${prefix}: ${q.text}`;
    if (selTxts.length > 0) s += ` → 选择: ${selTxts.join(', ')}`;
    if (q.freeText) s += ` + 备注: ${q.freeText}`;
    if (q.status === 'resolved') s += ' [已解决]';
    topic.questions.filter(cq => cq.parentId === q.id).forEach((child, ci) => {
      s += '\n  ' + _serializeQuestion(child, topic, `${prefix}.${ci + 1}`);
    });
    return s;
  }

  function _organizeToCanvas() {
    const summary = _serializeTopicsForChat();
    if (!summary) { return; }
    if ($input) {
      $input.value = `请根据以下讨论结果，调用 generate_canvas 工具生成工作流画布：\n\n${summary}`;
      autoResizeInput();
      $input.focus();
    }
  }

  // ── 导出 Markdown ──────────────────────────────────────────────────────────
  async function _discExportSession() {
    const now = new Date().toLocaleString('zh-CN', { hour12: false });
    let md = `# 话题讨论记录\n\n> 导出时间：${now}\n\n`;
    if (_topics.length === 0) { md += '（暂无话题）\n'; }
    else {
      _topics.forEach(topic => {
        md += `## 话题：${topic.title}${topic.status === 'resolved' ? ' ✓' : ''}\n\n`;
        topic.questions.filter(q => !q.parentId).forEach((q, i) => {
          md += _questionToMd(q, topic, `Q${i + 1}`, 0);
        });
        md += '\n---\n\n';
      });
    }
    try {
      const defaultName = `话题讨论_${new Date().toISOString().slice(0, 10)}.md`;
      const path = await window.electronAPI?.saveMdDialog?.(defaultName);
      if (!path) return;
      await window.electronAPI?.writeTextFile?.(path, md);
    } catch (_) {}
  }

  function _questionToMd(q, topic, prefix, indent) {
    const pad = '  '.repeat(indent);
    let s = `${pad}**${prefix}: ${q.text}**\n`;
    q.options.forEach(opt => {
      s += `${pad}- [${q.selectedOptionIds.includes(opt.id) ? 'x' : ' '}] ${opt.text}\n`;
    });
    if (q.freeText) s += `${pad}- 补充：${q.freeText}\n`;
    if (q.status === 'resolved') s += `${pad}- 状态：已解决 ✓\n`;
    s += '\n';
    topic.questions.filter(cq => cq.parentId === q.id).forEach((child, ci) => {
      s += _questionToMd(child, topic, `${prefix}.${ci + 1}`, indent + 1);
    });
    return s;
  }

  // ── 话题按钮绑定（在 init 时调用） ─────────────────────────────────────────
  function _initDiscussionPanel() {
    document.getElementById('aiDiscOrganizeBtn')?.addEventListener('click', _organizeToCanvas);
    document.getElementById('aiDiscAddBtn')?.addEventListener('click', () => {
      const title = prompt('话题标题：');
      if (title?.trim()) _createTopic(title.trim(), 'user');
    });
    document.getElementById('aiDiscExportBtn')?.addEventListener('click', _discExportSession);
    // 点击话题讨论标题行：折叠 ↔ 展开
    document.getElementById('aiDiscWrap')?.querySelector('.ai-disc-hdr')
      ?.addEventListener('click', (e) => {
        if (e.target.closest('button')) return; // 不拦截按钮点击
        document.getElementById('aiDiscWrap')?.classList.toggle('disc-collapsed');
      });
    _renderTopics();

    // 监听 WFC 注入文本到输入框
    if (_IS_POPUP) {
      window.electronAPI?.onWfcInjectText?.((text) => {
        if ($input) {
          $input.value = text;
          autoResizeInput();
          $input.focus();
        }
      });
    }
  }

  // ── 启动 ───────────────────────────────────────────────────────────────────
  init();

})();
