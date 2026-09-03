/**
 * nav_manager.js — 动态左侧导航管理器
 * 依赖：TabManager（window.TabManager）、dbg（window.dbg）
 *       _ROLE_PERMS / _hasTabPerm / _meetsVisibility（定义于 main.js，加载顺序在后）
 *       _showToast（定义于 main.js）
 */
const NavManager = (() => {
  const KEY = 'ui.nav.state';

  const ALL_ITEMS = [
    { id: 'workbench',      title: '工作台',    icon: 'icon-home',         requiresAuth: false },
    { id: 'my_files',       title: '我的文件',  icon: 'icon-files',        requiresAuth: false },
    { id: 'craft_hub',      title: '工艺规划',  icon: 'icon-canvas',       requiresAuth: true,  minPerm: 'craft.view' },
    { id: 'project_hub',    title: '项目管理',  icon: 'icon-project',      requiresAuth: false, minPerm: 'project.view' },
    { id: 'knowledge_hub',  title: '知识库',    icon: 'icon-knowledge',    requiresAuth: false },
    { id: 'automation_hub', title: '自动化与AI', icon: 'icon-robot',        requiresAuth: false },
    { id: 'cad_sim',        title: '数模仿真',  icon: 'icon-cube',         requiresAuth: false },
    { id: 'ontology',       title: '本体编辑器', icon: 'icon-onto',        requiresAuth: true,  minPerm: 'system.tech_config' },
    { id: 'team_space',     title: '团队空间',  icon: 'icon-team',         requiresAuth: true },
    { id: 'admin_hub',      title: '管理中心',  icon: 'icon-org',          requiresAuth: true,  minPerm: 'system.user.manage' },
  ];

  const DEFAULT_VISIBLE = ['workbench', 'my_files', 'craft_hub', 'project_hub', 'knowledge_hub', 'automation_hub', 'cad_sim', 'admin_hub'];

  let _state = null;
  let _ctxTarget = null;

  function _loadState() {
    try {
      const raw = localStorage.getItem(KEY);
      console.log('[Nav] localStorage raw:', raw);
      const s = JSON.parse(raw);
      if (s && Array.isArray(s.visible) && Array.isArray(s.hidden)) {
        const allIds = ALL_ITEMS.map(i => i.id);

        // ── 去重（防止重复点击"+"导致 visible 里出现多个相同 id）──────────
        s.visible = [...new Set(s.visible)];
        s.hidden  = [...new Set(s.hidden)];

        console.log('[Nav] loaded state before heal → visible:', [...s.visible], 'hidden:', [...s.hidden]);

        // 补充新模块：DEFAULT_VISIBLE 里的加到 visible，其余加到 hidden
        const covered = new Set([...s.visible, ...s.hidden]);
        allIds.filter(id => !covered.has(id)).forEach(id => {
          if (DEFAULT_VISIBLE.includes(id)) s.visible.push(id);
          else s.hidden.push(id);
        });
        // DEFAULT_VISIBLE 中若被旧状态放入 hidden，自动迁回 visible
        DEFAULT_VISIBLE.forEach(id => {
          if (s.hidden.includes(id) && !s.visible.includes(id)) {
            console.log('[Nav] auto-healing: moving', id, 'from hidden to visible');
            s.hidden  = s.hidden.filter(x => x !== id);
            s.visible.push(id);
          }
        });
        // 过滤已删除的模块
        s.visible = s.visible.filter(id => allIds.includes(id));
        s.hidden  = s.hidden.filter(id => allIds.includes(id));
        // 强制将已下线模块移出 visible（team_space 已整合入管理中心）
        const RETIRED = ['team_space'];
        RETIRED.forEach(id => {
          if (s.visible.includes(id)) {
            s.visible = s.visible.filter(x => x !== id);
            if (!s.hidden.includes(id)) s.hidden.push(id);
          }
        });
        console.log('[Nav] final state → visible:', [...s.visible], 'hidden:', [...s.hidden]);
        return s;
      }
    } catch(e) { console.warn('[Nav] _loadState error:', e); }
    const allIds = ALL_ITEMS.map(i => i.id);
    const fresh = {
      visible: [...DEFAULT_VISIBLE],
      hidden:  allIds.filter(id => !DEFAULT_VISIBLE.includes(id)),
    };
    console.log('[Nav] fresh state → visible:', [...fresh.visible], 'hidden:', [...fresh.hidden]);
    return fresh;
  }

  function _saveState() {
    localStorage.setItem(KEY, JSON.stringify(_state));
  }

  function _getItem(id) {
    return ALL_ITEMS.find(i => i.id === id);
  }

  function render() {
    const container = document.getElementById('nav-items-top');
    if (!container) return;
    // Nav 模块入口已移至工作台 App 面板，侧边栏不再渲染导航项
    container.innerHTML = '';
  }

  function _showCtxMenu(e, itemId, listType) {
    _ctxTarget = { id: itemId, listType };
    const menu = document.getElementById('nav-ctx-menu');
    if (!menu) return;

    const item = _getItem(itemId);
    const arr  = listType === 'visible' ? _state.visible : _state.hidden;
    const idx  = arr.indexOf(itemId);
    let html = '';

    if (listType === 'visible') {
      const isFirst = idx === 0;
      const isLast  = idx === _state.visible.length - 1;
      html += `<div class="ctx-item${isFirst ? ' disabled' : ''}" data-action="move-up">↑ 上移</div>`;
      html += `<div class="ctx-item${isLast  ? ' disabled' : ''}" data-action="move-down">↓ 下移</div>`;
      html += `<div class="ctx-sep"></div>`;
      html += `<div class="ctx-item" data-action="hide">隐藏「${item.title}」</div>`;
    } else {
      html += `<div class="ctx-item" data-action="show">添加到侧边栏</div>`;
      html += `<div class="ctx-item" data-action="show-top">置顶添加</div>`;
      html += `<div class="ctx-sep"></div>`;
      html += `<div class="ctx-item" data-action="open">打开（不固定）</div>`;
    }

    menu.innerHTML = html;
    menu.querySelectorAll('.ctx-item:not(.disabled)').forEach(el => {
      el.addEventListener('click', () => _execCtxAction(el.dataset.action));
    });

    const mw = 170;
    let x = e.clientX, y = e.clientY;
    if (x + mw > window.innerWidth) x = window.innerWidth - mw - 4;
    if (y + 120 > window.innerHeight) y = window.innerHeight - 130;
    menu.style.left = x + 'px';
    menu.style.top  = y + 'px';
    menu.classList.remove('hidden');

    const closeOnClick = evt => {
      if (!menu.contains(evt.target)) {
        menu.classList.add('hidden');
        document.removeEventListener('mousedown', closeOnClick);
      }
    };
    setTimeout(() => document.addEventListener('mousedown', closeOnClick), 10);
  }

  function _execCtxAction(action) {
    document.getElementById('nav-ctx-menu')?.classList.add('hidden');
    if (!_ctxTarget) return;
    const { id } = _ctxTarget;

    if (action === 'move-up') {
      const arr = _state.visible, i = arr.indexOf(id);
      if (i > 0) [arr[i - 1], arr[i]] = [arr[i], arr[i - 1]];
    } else if (action === 'move-down') {
      const arr = _state.visible, i = arr.indexOf(id);
      if (i < arr.length - 1) [arr[i + 1], arr[i]] = [arr[i], arr[i + 1]];
    } else if (action === 'hide') {
      _state.visible = _state.visible.filter(x => x !== id);
      _state.hidden.push(id);
    } else if (action === 'show') {
      _state.hidden = _state.hidden.filter(x => x !== id);
      _state.visible.push(id);
    } else if (action === 'show-top') {
      _state.hidden = _state.hidden.filter(x => x !== id);
      _state.visible.unshift(id);
    } else if (action === 'open') {
      window.TabManager.open(id);
      return;
    }

    _saveState();
    render();
    _renderMorePanel();
  }

  function _renderMorePanel() {
    const panel = document.getElementById('nav-more-panel');
    if (!panel) return;
    const list = panel.querySelector('.more-panel-list');
    if (!list) return;

    const isUnauth = window._authMode !== 'feishu';
    // 过滤掉当前用户无权访问的项（不应出现在"添加"列表里）
    const visibleHidden = _state.hidden.filter(id => {
      const item = _getItem(id);
      if (!item) return false;
      if (isUnauth && item.requiresAuth) return false;
      if (item.minPerm && !_hasTabPerm(item.minPerm)) return false;
      if (item.grantCheck && !window._hasGrant?.(item.grantCheck)) return false;
      return true;
    });

    if (visibleHidden.length === 0) {
      list.innerHTML = '<div class="more-panel-empty">所有模块均已显示</div>';
      return;
    }

    list.innerHTML = '';
    visibleHidden.forEach(id => {
      const item = _getItem(id);
      if (!item) return;
      const el = document.createElement('div');
      el.className = 'more-panel-item';
      el.innerHTML =
        `<svg class="icon" width="16" height="16"><use href="#${item.icon}"/></svg>` +
        `<span>${item.title}</span>` +
        `<button class="more-panel-add" title="固定到侧边栏">+</button>`;
      el.querySelector('button').addEventListener('click', e => {
        e.stopPropagation();
        console.log('[Nav] more-panel "+" clicked for:', id,
          '| before → visible:', [..._state.visible], 'hidden:', [..._state.hidden]);
        _state.hidden = _state.hidden.filter(x => x !== id);
        _state.visible.push(id);
        console.log('[Nav] after → visible:', [..._state.visible], 'hidden:', [..._state.hidden]);
        _saveState();
        render();
        _renderMorePanel();
      });
      el.addEventListener('click', () => { window.TabManager.open(id); _toggleMorePanel(false); });
      el.addEventListener('contextmenu', e => {
        e.preventDefault();
        _toggleMorePanel(false);
        _showCtxMenu(e, id, 'hidden');
      });
      list.appendChild(el);
    });
  }

  function _toggleMorePanel(force) {
    const panel = document.getElementById('nav-more-panel');
    if (!panel) return;
    const show = force !== undefined ? force : panel.classList.contains('hidden');
    if (show) {
      _renderMorePanel();
      panel.classList.remove('hidden');
      const closeOnClick = evt => {
        const btn = document.getElementById('nav-more-btn');
        if (!panel.contains(evt.target) && !btn?.contains(evt.target)) {
          panel.classList.add('hidden');
          document.removeEventListener('mousedown', closeOnClick);
        }
      };
      setTimeout(() => document.addEventListener('mousedown', closeOnClick), 10);
    } else {
      panel.classList.add('hidden');
    }
  }

  function boot() {
    _state = _loadState();

    // 读取 auth 状态（Electron 模式），决定哪些导航项可见
    _initAuthState().then(() => {
      render();
      _updateAuthBadge();
      // 已登录时直接打开工作台和工艺规划
      if (window._authMode === 'feishu') {
        window.TabManager?.open('workbench');
        window.TabManager?.open('craft_hub');
      }
    });

    // 登录/退出后主进程推送状态，实时刷新导航和 badge
    window.electronAPI?.onAuthStateChanged?.((state) => {
      const prevMode = window._authMode;
      window._authMode  = state?.mode  || 'none';
      window._authUser  = state?.user  || null;
      window._authToken = state?.token || null;
      render();
      _updateAuthBadge();
      // 通知所有 iframe 子页面同步用户状态（角色卡片）
      document.querySelectorAll('iframe').forEach(f => {
        try { f.contentWindow?.postMessage({ type: 'auth-state', user: window._authUser, mode: window._authMode }, '*'); } catch(_) {}
      });
      // 刚登录时自动打开工作台和工艺规划
      if (prevMode !== 'feishu' && state?.mode === 'feishu') {
        window.TabManager?.open('workbench');
        window.TabManager?.open('craft_hub');
      }
    });

    document.getElementById('nav-more-btn')?.addEventListener('click', () => _toggleMorePanel());

    // 固定在底部的设置按钮
    document.querySelector('.nav-item[data-view="settings"]')?.addEventListener('click', () => {
      window.TabManager.open('settings');
    });

    window.dbg?.log('[Nav] 动态导航初始化完成');
  }

  async function _initAuthState() {
    try {
      if (window.electronAPI?.authGetState) {
        const state = await window.electronAPI.authGetState();
        window._authMode  = state?.mode  || 'none';
        window._authUser  = state?.user  || null;
        window._authToken = state?.token || null;
      } else {
        // 非 Electron 环境（开发调试）：默认完全开放
        window._authMode = 'feishu';
      }
    } catch (_) {
      window._authMode = 'none';
    }
  }

  function _updateAuthBadge() {
    const badge = document.getElementById('current-user');
    if (!badge) return;
    const logoutBtn = document.getElementById('btn-statusbar-logout');
    if (window._authMode === 'feishu' && window._authUser?.name) {
      badge.textContent = '当前登录：' + window._authUser.name;
      if (logoutBtn) {
        logoutBtn.style.display = '';
        logoutBtn.onclick = () => {
          if (window.electronAPI?.authLogout) {
            window.electronAPI.authLogout();
          } else if (window.parent?.electronAPI?.authLogout) {
            window.parent.electronAPI.authLogout();
          }
        };
      }
    } else {
      if (logoutBtn) logoutBtn.style.display = 'none';
    }
    // 开发看板按钮仅超管可见
    const trackerBtn = document.getElementById('btn-tracker');
    if (trackerBtn) {
      const _u = window._authUser;
      const _r = _u?.system_role || _u?.org_role || _u?.role || '';
      trackerBtn.style.display = (_r === 'super_admin') ? '' : 'none';
    }
    // AI 助手按钮：飞书登录后可见
    const aiChatBtn = document.getElementById('btn-ai-chat');
    const aiCanvasBtn = document.getElementById('btn-ai-canvas');
    if (aiChatBtn) {
      const hasAccess = window._authMode === 'feishu';
      aiChatBtn.style.display = hasAccess ? '' : 'none';
      if (aiCanvasBtn) aiCanvasBtn.style.display = hasAccess ? '' : 'none';
      if (hasAccess) { _startBalancePolling(); } else { _stopBalancePolling(); }
    }
  }

  // ── AI 余额轮询 ──────────────────────────────────────────
  let _balanceTimer     = null;
  let _balanceTickTimer = null;
  let _lastBalanceTime  = null;
  let _lastBalanceVal   = null;

  function _startBalancePolling() {
    _stopBalancePolling();
  }

  function _stopBalancePolling() {
    clearInterval(_balanceTimer);
    clearInterval(_balanceTickTimer);
    _balanceTimer = _balanceTickTimer = null;
    _lastBalanceTime = _lastBalanceVal = null;
    const el = document.getElementById('ai-balance-display');
    if (el) el.style.display = 'none';
  }

  async function _fetchBalance() {
    return null;
  }

  function _updateBalanceTime() {
    if (_lastBalanceTime != null) _updateBalanceDisplay();
  }

  function _updateBalanceDisplay() {
    const el = document.getElementById('ai-balance-display');
    if (!el || _lastBalanceVal == null) return;
    const mins    = Math.floor((Date.now() - _lastBalanceTime) / 60000);
    const timeStr = mins < 1 ? '刚刚' : `${mins}m前`;
    const rawModel = localStorage.getItem('ai_last_model') || '';
    const modelStr = rawModel
      ? ' · ' + rawModel.replace(/^(anthropic|deepseek|openai|ollama)\//, '')
      : '';
    el.textContent = `¥${_lastBalanceVal.toFixed(2)} · ${timeStr}${modelStr}`;
    el.style.display = '';
    el.className = _lastBalanceVal <= 0 ? 'bal-empty' : _lastBalanceVal < 1 ? 'bal-low' : '';
  }

  // Python 同步后调用：用持久化的状态覆盖当前 state 并重渲染
  function loadFromPython(savedState) {
    try {
      const allIds = ALL_ITEMS.map(i => i.id);
      const s = {
        visible: [...new Set(savedState.visible)].filter(id => allIds.includes(id)),
        hidden:  [...new Set(savedState.hidden  || [])].filter(id => allIds.includes(id)),
      };
      // 补充新模块（savedState 里没有的）
      allIds.filter(id => !s.visible.includes(id) && !s.hidden.includes(id)).forEach(id => {
        if (DEFAULT_VISIBLE.includes(id)) s.visible.push(id);
        else s.hidden.push(id);
      });
      _state = s;
      render();
    } catch(e) { console.warn('[Nav] loadFromPython error:', e); }
  }

  // ── 动态注册（Phase 2）────────────────────────────────────────────────────────
  /**
   * 注册一个导航项（来自插件 manifest）。
   * 若 id 已存在则跳过（硬编码优先，保持向后兼容）。
   */
  function register(item) {
    if (ALL_ITEMS.find(i => i.id === item.id)) return;
    ALL_ITEMS.push(item);
    // 新增 nav 项默认加入 DEFAULT_VISIBLE（除非 requiresAuth 且 hidden）
    if (!DEFAULT_VISIBLE.includes(item.id) && item.id !== 'admin_hub') {
      DEFAULT_VISIBLE.push(item.id);
    }
  }

  /**
   * 从 PluginRegistry payload 批量注册导航项，并刷新渲染。
   */
  async function loadFromRegistry() {
    try {
      const registry = await window.electronAPI?.getPluginRegistry?.();
      if (!registry?.navItems) return;
      let added = 0;
      for (const item of registry.navItems) {
        if (!ALL_ITEMS.find(i => i.id === item.id)) {
          ALL_ITEMS.push(item);
          added++;
        }
      }
      if (added > 0) {
        // 重新计算 _state（补充新 id）
        _state = _loadState();
        render();
        window.dbg?.log(`[Nav] 从 PluginRegistry 注册了 ${added} 个新导航项`);
      }
    } catch (e) {
      console.warn('[Nav] loadFromRegistry 失败:', e);
    }
  }

  return { boot, render, loadFromPython, register, loadFromRegistry };
})();

window.NavManager = NavManager;
