/**
 * tab_manager.js — Tab 多页面管理器（委托给 WorkspaceEngine）
 * 依赖：WorkspaceEngine（workspace.js）、dbg（main.js dbg）
 *       _ROLE_PERMS / _hasTabPerm（定义于 main.js）
 *       _showToast / _showAuthRequired（定义于 main.js）
 */
const TabManager = (() => {
  /**
   * 视图定义：viewId → { title, src, requiresAuth?, minPerm? }
   * requiresAuth: true 表示需要飞书登录才可访问（本地模式下隐藏）
   * minPerm: 需要拥有此权限点才可看到/打开此 Tab；null 表示无权限限制
   */
  const TAB_DEFS = {
    workbench:        { title: '工作台',    src: 'workbench/workbench.html',                         minPerm: null },
    my_files:         { title: '我的文件',  src: 'my_files/index.html',                               minPerm: null },
    craft_hub:        {
      title: '工艺规划',
      src: '../packages/craft-plugin/web/craft_hub/index.html',
      requiresAuth: true,
      minPerm: 'craft.view',
    },
    project_hub:      {
      title: '项目管理',
      src: '../packages/craft-plugin/web/project_hub/index.html',
      minPerm: 'project.view',
    },
    automation_hub:   {
      title: '自动化与AI',
      src: '../packages/agent-plugin/web/automation_hub/index.html',
      minPerm: null,
    },
    ai_chat:          {
      title: 'AI 对话',
      src: '../packages/agent-plugin/web/ai_chat/index.html',
      minPerm: null,
    },
    wfc_canvas:       {
      title: 'AI 画布',
      src: '../packages/agent-plugin/web/wfc_window/index.html',
      minPerm: null,
    },
    cad_sim:          {
      title: '数模仿真',
      src: '../packages/sim-plugin/web/cad_sim/index.html',
      minPerm: null,
    },
    // 模块 Hub — 二级横排页签入口
    admin_hub:        { title: '管理中心',  src: 'admin_hub/index.html',      requiresAuth: true,   minPerm: 'system.user.manage' },
    team_space:       { title: '团队空间',  src: 'team_space/index.html',     requiresAuth: true,   minPerm: null },
    knowledge_hub:    { title: '知识库',    src: 'knowledge_hub/index.html',  requiresAuth: false,  minPerm: null },
    // automation_hub / cad_sim / ai_chat / wfc_canvas 来自插件，不硬编码，由 loadFromRegistry() 注册
    settings:         { title: '设置',      src: 'settings/index.html',                              minPerm: null },
    // 保留（在各 hub 内以 iframe 加载，主导航已隐藏）
    knowledge:        { title: '知识库',    src: 'knowledge/knowledge.html',  requiresAuth: true,    minPerm: 'knowledge.view', hidden: true },
    rule:             { title: '规则管理',  src: 'rule_mgmt/rule_mgmt.html',  minPerm: 'rule.view',  hidden: true },
    'md-workspace':   { title: 'MD 文档',   src: 'md_workspace/md_workspace.html',  hidden: true,   minPerm: null },
    sys_capabilities:  { title: '系统能力',  src: 'admin/capabilities.html',    requiresAuth: true,    minPerm: 'system.user.manage', hidden: true },
    sys_lists:         { title: '清单注册',  src: 'admin/lists_registry.html',  requiresAuth: true,    minPerm: 'system.user.manage', hidden: true },
    sys_feature_flags: { title: '功能开关',  src: 'admin/feature_flags.html',   requiresAuth: true,    minPerm: 'system.user.manage', hidden: true },
    sys_ai_audit:      { title: 'AI 审计',   src: 'admin/ai_audit.html',        requiresAuth: true,    minPerm: 'system.user.manage', hidden: true },
    // 任务画布视图（画布视图 = 任务系统第三种视图）
    task_canvas:      { title: '任务规划',   src: 'admin/task_planning.html',  hidden: true,           minPerm: 'project.view' },
    // 流程编辑器（v1.0，Drawflow 版，Phase 1-B 后废弃）
    canvas_shell:     { title: '画布',        src: 'canvas/canvas_shell.html', hidden: true,           minPerm: null },
    // 容器卡片全屏页（Phase 2）
    container_card:   { title: '内容详情',    src: 'container_card/index.html', hidden: true,          minPerm: null },
    handbook:         { title: '帮助手册',    src: 'handbook/index.html',         hidden: true, minPerm: null },
    ext_datasource:   { title: '外部数据源', src: 'ext_datasource/index.html',   hidden: true, minPerm: 'system.tech_config', requiresAuth: true },
    // BOP 工艺清单
    ontology:         { title: '本体编辑器',   src: 'ontology/index.html',       requiresAuth: true,    minPerm: 'knowledge.view', hidden: true },
  };

  // ── 动态注册（Phase 2）：供 PluginRegistry 追加/覆盖 Tab 定义 ─────────────────
  /**
   * 注册一个 Tab 定义（来自插件 manifest）。
   * 若 id 已存在则跳过（内置硬编码优先，保持向后兼容）。
   */
  function registerTab(id, def) {
    if (TAB_DEFS[id]) return; // 硬编码已有，跳过
    TAB_DEFS[id] = def;
  }

  /**
   * 从 PluginRegistry payload 批量注册 Tab。
   * 由 main.js 在 DOMContentLoaded 后调用。
   */
  async function loadFromRegistry() {
    try {
      const registry = await window.electronAPI?.getPluginRegistry?.();
      if (!registry?.tabDefs) return;
      let added = 0;
      for (const [id, def] of Object.entries(registry.tabDefs)) {
        // 插件定义优先覆盖 src=null 的占位条目；若已有真实 src 则不覆盖
        if (!TAB_DEFS[id] || !TAB_DEFS[id].src) { TAB_DEFS[id] = def; added++; }
      }
      if (added > 0) window.dbg?.log(`[Tab] 从 PluginRegistry 注册了 ${added} 个新 Tab`);
    } catch (e) {
      console.warn('[Tab] loadFromRegistry 失败:', e);
    }
  }

  const WELCOME_HTML = `
    <div class="welcome-screen">
      <div class="welcome-logo">
        <svg viewBox="0 0 48 48" fill="none" style="width:72px;height:72px;color:var(--color-primary)">
          <rect width="48" height="48" rx="12" fill="currentColor" opacity="0.15"/>
          <path d="M12 36 L24 12 L36 36" stroke="currentColor" stroke-width="3"
                stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M16 28 L32 28" stroke="currentColor" stroke-width="3" stroke-linecap="round"/>
          <circle cx="24" cy="12" r="3" fill="currentColor"/>
        </svg>
      </div>
      <h1>总装智能辅助工艺开发系统(AI00)V1.0</h1>
      <p>选择左侧功能模块，或使用 <kbd>Ctrl+P</kbd> 打开命令面板</p>
      <div class="quick-actions">
        <button class="quick-btn" onclick="TabManager.open('workbench')">
          <svg class="icon" width="16" height="16"><use href="#icon-home"/></svg> 工作台
        </button>
        <button class="quick-btn" onclick="TabManager.open('craft_hub')">
          <svg class="icon" width="16" height="16"><use href="#icon-canvas"/></svg> 工艺规划
        </button>
        <button class="quick-btn" onclick="TabManager.open('project_hub')">
          <svg class="icon" width="16" height="16"><use href="#icon-project"/></svg> 项目管理
        </button>
      </div>
    </div>`;

  /** 初始化 WorkspaceEngine 并注入欢迎 Tab */
  function boot() {
    WorkspaceEngine.init('ws-content');

    const canOpenCraftHub = window._authMode === 'feishu' && _hasTabPerm('craft.view');
    if (canOpenCraftHub) {
      open('craft_hub');
      open('workbench');
      activate('craft_hub');
    } else {
      WorkspaceEngine.addTab('welcome', '✦ 欢迎', null, { closeable: false, html: WELCOME_HTML });
    }

    window.dbg?.log('[Tab] WorkspaceEngine 初始化完成');
  }

  /** 打开一个视图 Tab，已存在则切换，设置页特殊处理 */
  function open(viewId, params = {}) {
    if (viewId === 'settings') {
      window.electronAPI?.openSettings?.();
      return;
    }

    const def = TAB_DEFS[viewId];

    // 未登录拦截
    if (def?.requiresAuth && window._authMode !== 'feishu') {
      _showAuthRequired(def.title);
      return;
    }

    // 权限检查
    if (def?.minPerm && !_hasTabPerm(def.minPerm)) {
      _showAuthRequired(def.title);
      return;
    }

    // grant 检查
    if (def?.grantCheck && !window._hasGrant?.(def.grantCheck)) {
      _showAuthRequired(def.title);
      return;
    }

    // 带参数时每次创建新 Tab（flow_canvas 等），否则直接切换已有 Tab
    const hasParams = Object.keys(params).length > 0;

    if (!hasParams && WorkspaceEngine.hasTab(viewId)) {
      WorkspaceEngine.activateTab(viewId);
      return;
    }

    // container_card webview：相同 URL 直接复用已有 Tab，不重新加载
    if (viewId === 'container_card' && params.mode === 'webview' && params.url) {
      const existing = WorkspaceEngine.findTabIdBySrc?.(encodeURIComponent(params.url));
      if (existing) {
        WorkspaceEngine.activateTab(existing);
        return;
      }
    }

    if (!def) { window.dbg?.warn(`[Tab] 未知视图: ${viewId}`); return; }

    // 若 src 存在，将 params 追加为 query string
    let src = def.src || null;
    if (src && hasParams) {
      const qs = new URLSearchParams(params).toString();
      src = `${src}?${qs}`;
    }

    const html = src ? null :
      `<div class="welcome-screen">
         <p style="color:var(--text-muted);font-size:16px;">${def.title} — 功能规划中...</p>
         <p style="color:var(--text-faint);font-size:13px;">此功能将在后续版本中实现</p>
       </div>`;

    // 带参数时用唯一 tabId（避免同时打开多个同类 tab 时冲突）
    const tabId = hasParams ? `${viewId}_${Date.now()}` : viewId;
    const isPermanent = viewId === 'workbench' || viewId === 'craft_hub';
    WorkspaceEngine.addTab(tabId, def.title, src, { html, closeable: !isPermanent });
    window.dbg?.log(`[Tab] 打开: ${def.title}${hasParams ? ' (带参数)' : ''}`);

    // container_card：通过 postMessage 传递完整 params（避免 URL 长度限制）
    if (viewId === 'container_card' && hasParams) {
      // 等 iframe 加载完毕再发送 params（viewer.js 会读取 window._ccParams）
      const sendParams = () => {
        const iframe = WorkspaceEngine.getTabIframe?.(tabId);
        if (iframe?.contentWindow) {
          iframe.contentWindow.postMessage({ type: 'cc:params', params, tabId }, '*');
        }
      };
      // 先等 100ms 让 iframe 创建，再监听 load 事件
      setTimeout(() => {
        const iframe = WorkspaceEngine.getTabIframe?.(tabId);
        if (!iframe) { setTimeout(sendParams, 500); return; }
        if (iframe.contentDocument?.readyState === 'complete') {
          sendParams();
        } else {
          iframe.addEventListener('load', sendParams, { once: true });
        }
      }, 100);
    }
  }

  /** 关闭一个 Tab */
  function close(viewId) {
    WorkspaceEngine.closeTab(viewId);
    window.dbg?.log(`[Tab] 关闭: ${viewId}`);
  }

  /** 切换到指定 Tab（外部调用，不常用）*/
  function activate(viewId) {
    WorkspaceEngine.activateTab(viewId);
  }

  function _showAuthRequired(title) {
    _showToast(`「${title}」需要飞书登录后才能使用`, 'warning', 3500);
    window.dbg?.warn(`[Tab] 本地模式无权访问: ${title}`);
  }

  /**
   * 关闭当前用户无权访问的所有已打开 Tab。
   * 在账户切换（onAuthStateChanged）时调用，确保低权限账户不能保留高权限 Tab。
   */
  function closeUnauthorizedTabs() {
    Object.keys(TAB_DEFS).forEach(viewId => {
      if (!WorkspaceEngine.hasTab(viewId)) return;
      const def = TAB_DEFS[viewId];
      // 需要飞书登录但当前未登录
      if (def.requiresAuth && window._authMode !== 'feishu') {
        close(viewId);
        return;
      }
      // 权限不足
      if (def.minPerm && !_hasTabPerm(def.minPerm)) {
        close(viewId);
      }
    });
  }

  return { open, close, activate, boot, closeUnauthorizedTabs, registerTab, loadFromRegistry, activeId: () => WorkspaceEngine.activeTabId() };
})();

window.TabManager = TabManager;
