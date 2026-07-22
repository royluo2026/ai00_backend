/**
 * 总装智能辅助工艺开发系统(AI00)V1.0 — 主界面协调脚本
 *
 * 此文件是协调入口，各模块已拆分到：
 *   - core/theme_manager.js      ThemeManager
 *   - core/auth_state.js         AuthStateManager
 *   - core/notification_manager.js  NotifManager
 *   - core/cmd_palette.js        CmdPalette
 *   - workspace/tab_manager.js   TabManager
 *   - workspace/nav_manager.js   NavManager
 *
 * 本文件保留：
 *   - dbg            调试日志面板（Ctrl+`，必须最先初始化）
 *   - _ROLE_PERMS / _hasTabPerm / _meetsVisibility（TabManager/NavManager 共用）
 *   - LogPanel       系统日志浮窗
 *   - _showToast     Toast 通知（TabManager/_showAuthRequired 依赖）
 *   - _bindShortcuts / _bindStatusbar / _bindNavSidebar
 *   - _cloudFetch    全局云端 Fetch 工具
 *   - TaskTimeline   状态栏任务时间线
 *   - 全局功能开关缓存 + _loadFeatureFlags
 *   - DOM 就绪初始化
 */

// HTTP 非安全上下文下 navigator.clipboard 为 undefined，用 execCommand 兜底
function _copyText(text) {
  if (navigator.clipboard?.writeText) return navigator.clipboard.writeText(text);
  return new Promise((resolve, reject) => {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.cssText = 'position:fixed;left:-9999px;top:-9999px;opacity:0';
    document.body.appendChild(ta);
    ta.focus(); ta.select();
    try { document.execCommand('copy') ? resolve() : reject(new Error('execCommand failed')); }
    catch (e) { reject(e); }
    finally { document.body.removeChild(ta); }
  });
}

// ===================== 调试面板（最先初始化，供其他模块使用）=====================
const dbg = (() => {
  const MAX = 500;
  const _logs = [];
  let _panel, _body, _visible = false;

  function _init() {
    _panel = document.getElementById('debug-panel');
    _body  = document.getElementById('debug-body');
    if (!_panel || !_body) return;

    // Ctrl+` 开关
    document.addEventListener('keydown', e => {
      if (e.ctrlKey && e.key === '`') { e.preventDefault(); _toggle(); }
    });

    // 拦截 console 输出
    ['log', 'warn', 'error', 'info'].forEach(method => {
      const orig = console[method].bind(console);
      console[method] = (...args) => {
        orig(...args);
        const lvl = method === 'error' ? 'error' : method === 'warn' ? 'warn' : 'ok';
        _push(`[${method.toUpperCase()}] ${args.join(' ')}`, lvl);
      };
    });

    // 全局 JS 错误
    window.addEventListener('error', ev =>
      _push(`❌ JS: ${ev.message} (${ev.filename?.split('/').pop()}:${ev.lineno})`, 'error'));
    window.addEventListener('unhandledrejection', ev =>
      _push(`❌ Promise: ${ev.reason}`, 'error'));

    // 搜索框实时过滤
    const searchInput = document.getElementById('debug-search');
    if (searchInput) {
      searchInput.addEventListener('input', () => _applySearch(searchInput.value));
    }

    // 导出按钮
    const exportBtn = document.getElementById('btn-debug-export');
    if (exportBtn) {
      exportBtn.addEventListener('click', () => {
        const text = _logs.map(l => `${l.ts}  ${l.msg}`).join('\n');
        const blob = new Blob([text], { type: 'text/plain' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `debug-${new Date().toISOString().slice(0,19).replace(/:/g,'-')}.log`;
        a.click();
        URL.revokeObjectURL(a.href);
      });
    }

    // 复制按钮（复制当前可见行）
    const copyBtn = document.getElementById('btn-debug-copy');
    if (copyBtn) {
      copyBtn.addEventListener('click', () => {
        const q = (document.getElementById('debug-search')?.value || '').toLowerCase();
        const visible = _logs.filter(l => !q || `${l.ts}  ${l.msg}`.toLowerCase().includes(q));
        const text = visible.map(l => `${l.ts}  ${l.msg}`).join('\n');
        _copyText(text).then(() => {
          const orig = copyBtn.textContent;
          copyBtn.textContent = '✓';
          setTimeout(() => { copyBtn.textContent = orig; }, 1500);
        }).catch(() => {});
      });
    }

    // 日志 / 网络 / 轨迹 标签切换
    function _switchDbgView(view) {
      const isLog    = view === 'log';
      const isNet    = view === 'net';
      const isCrumbs = view === 'crumbs';
      document.getElementById('debug-body').style.display    = isLog    ? '' : 'none';
      document.getElementById('debug-net').style.display     = isNet    ? '' : 'none';
      document.getElementById('debug-crumbs').style.display  = isCrumbs ? '' : 'none';
      document.getElementById('debug-search').style.display       = isLog ? '' : 'none';
      document.getElementById('btn-debug-export').style.display   = isLog ? '' : 'none';
      document.getElementById('btn-debug-copy').style.display     = isLog ? '' : 'none';
      document.getElementById('btn-dbg-view-log')?.classList.toggle('active', isLog);
      document.getElementById('btn-dbg-view-net')?.classList.toggle('active', isNet);
      document.getElementById('btn-dbg-view-crumbs')?.classList.toggle('active', isCrumbs);
      if (isNet)    _netRender();
      if (isCrumbs) _crumbRender();
    }
    document.getElementById('btn-dbg-view-log')?.addEventListener('click',    () => _switchDbgView('log'));
    document.getElementById('btn-dbg-view-net')?.addEventListener('click',    () => _switchDbgView('net'));
    document.getElementById('btn-dbg-view-crumbs')?.addEventListener('click', () => _switchDbgView('crumbs'));
  }

  function _applySearch(query) {
    if (!_body) return;
    const q = (query || '').toLowerCase();
    for (const el of _body.children) {
      el.style.display = (!q || el.textContent.toLowerCase().includes(q)) ? '' : 'none';
    }
  }

  function _push(msg, type = 'ok') {
    const colors = { ok: '#a6e3a1', warn: '#f9e2af', error: '#f38ba8' };
    const ts = new Date().toTimeString().slice(0, 8);
    const now = Date.now();
    const msgKey = msg.slice(0, 100);

    // 去重：同类型 + 同前缀 + 60s 内 → 折叠计数
    const last = _logs[_logs.length - 1];
    if (last && last.type === type && last.msgKey === msgKey && (now - last.tsMs) < 60000) {
      last.count = (last.count || 1) + 1;
      last.msg = `${msgKey} (×${last.count})`;
      if (_body?.lastElementChild) {
        _body.lastElementChild.textContent = `${last.ts}  ${last.msg}`;
      }
      return;
    }

    // error 时写入轨迹面包屑
    if (type === 'error') {
      _addCrumb('error', msg.slice(0, 80));
    }

    _logs.push({ msg, type, ts, tsMs: now, msgKey });
    if (_logs.length > MAX) _logs.shift();

    if (_body) {
      if (_body.children.length >= MAX) _body.removeChild(_body.firstChild);
      const el = document.createElement('div');
      el.style.color = colors[type] || colors.ok;
      el.textContent = `${ts}  ${msg}`;
      const q = (document.getElementById('debug-search')?.value || '').toLowerCase();
      if (q && !el.textContent.toLowerCase().includes(q)) el.style.display = 'none';
      _body.appendChild(el);
      _body.scrollTop = _body.scrollHeight;
    }
  }

  function _toggle(force) {
    _visible = force !== undefined ? force : !_visible;
    _panel?.classList.toggle('hidden', !_visible);
  }

  // 初始化时机：DOMContentLoaded 或立即
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _init);
  } else {
    _init();
  }

  return {
    log:   m => _push(m, 'ok'),
    warn:  m => _push(m, 'warn'),
    error: m => _push(m, 'error'),
    show:  ()  => _toggle(true),
    hide:  ()  => _toggle(false),
  };
})();

window.dbg = dbg;

// ══════════════════════════════════════════════════════════════
// 后端地址解析（兼容本地开发 + 云端部署）
// 规则：
// 1) Electron 显式配置 backendUrl 优先
// 2) 先识别环境（dev/test/staging/prod）再按环境映射
// 3) 本地开发默认走当前 origin（配合 Vite 代理）
// ══════════════════════════════════════════════════════════════
const _DEFAULT_LOCAL_BACKEND = 'http://127.0.0.1:8080';

function _runtimeConfig() {
  return window.AI00RuntimeConfig || null;
}

function _loadBackendEnvMapAsync() {
  return _runtimeConfig()?.loadBackendEnvMapAsync?.() || Promise.resolve({
    local: _DEFAULT_LOCAL_BACKEND,
    dev: _DEFAULT_LOCAL_BACKEND,
    test: '',
    staging: '',
    prod: '',
  });
}

function _detectRuntimeEnvByHost(host) {
  return _runtimeConfig()?.detectRuntimeEnvByHost?.(host) || 'unknown';
}

function _inferBackendFromFrontendOrigin(origin = window.location.origin) {
  return _runtimeConfig()?.inferBackendFromFrontendOrigin?.(origin) || Promise.resolve(_DEFAULT_LOCAL_BACKEND);
}

function _getRuntimeBackendBase(configBackendUrl = '') {
  const runtime = _runtimeConfig();
  if (runtime?.getRuntimeBackendBase) return runtime.getRuntimeBackendBase(configBackendUrl);
  const explicit = String(configBackendUrl || '').trim().replace(/\/$/, '');
  return Promise.resolve(explicit || _DEFAULT_LOCAL_BACKEND);
}

function _resolveBackendBase(configBackendUrl = '') {
  return _getRuntimeBackendBase(configBackendUrl);
}


// ── 角色权限表（模块级，TabManager 和 NavManager 共用）──────────────────────
const _ROLE_PERMS = {
  // 新 org_role 3值
  super_admin:    new Set(['project.view','craft.view','rule.view','template.view','knowledge.view','approval.submit','approval.approve','feishu.view','system.user.manage','system.tech_config','system.app_config']),
  member:         new Set(['project.view','craft.view','rule.view','template.view','knowledge.view','approval.submit','feishu.view']),
  external:       new Set(['external.view']),
  // 旧 7 角色别名（过渡期兼容，不报错）
  team_admin:     new Set(['project.view','craft.view','rule.view','template.view','knowledge.view','approval.submit','approval.approve','feishu.view','system.user.manage']),
  project_admin:  new Set(['project.view','craft.view','rule.view','template.view','knowledge.view','approval.submit','approval.approve','feishu.view']),
  rule_admin:     new Set(['project.view','craft.view','rule.view','template.view','knowledge.view','approval.submit','feishu.view']),
  knowledge_admin:new Set(['project.view','craft.view','rule.view','template.view','knowledge.view','approval.submit','feishu.view']),
};

// grant 增量权限（叠加到 org_role 基线）
const _GRANT_PERMS = {
  team_admin:    new Set(['system.app_config','system.user.manage','project.create','project.manage_any','rule.manage','knowledge.manage','template.manage','approval.approve']),
  project_owner: new Set(['project.manage_assigned','craft.write_direct','ebom.import','approval.approve']),
  section_lead:  new Set(['craft.write_direct']),
};

function _hasTabPerm(minPerm) {
  if (!minPerm) return true;
  const user = window._authUser;
  const role = user?.org_role || user?.role || 'member';
  // 基线权限
  if (_ROLE_PERMS[role]?.has(minPerm)) return true;
  // grant 增量权限
  const grants = user?.grants || [];
  for (const g of grants) {
    if (_GRANT_PERMS[g.grant_type]?.has(minPerm)) return true;
  }
  return false;
}

/**
 * 检查当前用户是否持有某种 grant（可选范围过滤）
 * @param {string} grantType - 'team_admin' | 'project_owner' | 'section_lead'
 * @param {string} [scopeGid] - 可选，限定 scope_gid
 */
function _hasGrant(grantType, scopeGid = null) {
  const user = window._authUser;
  if (!user) return false;
  if ((user.org_role || user.role) === 'super_admin') return true;
  const grants = user.grants || [];
  return grants.some(g => {
    if (g.grant_type !== grantType) return false;
    if (scopeGid && g.scope_gid && g.scope_gid !== scopeGid) return false;
    return true;
  });
}

window._hasGrant = _hasGrant;

function _meetsVisibility(level) {
  const user = window._authUser;
  const role = user?.org_role || user?.system_role || user?.role || 'member';
  // org_role 3值模型
  if (level === 'super_admin') return role === 'super_admin';
  if (level === 'team_admin')  return role === 'super_admin' || _hasGrant('team_admin');
  return true; // 'all'
}

/**
 * 4 档角色级别检查（供功能开关 / App面板 / 状态栏使用）
 * all < member < team_admin < super_admin
 */
function _meetsRoleLevel(level) {
  if (!level || level === 'all') return true;
  const user  = window._authUser;
  const role  = user?.org_role || user?.system_role || user?.role || 'external';
  const rank  = { super_admin:4, team_admin:3, project_admin:2, rule_admin:2, knowledge_admin:2, member:1, external:0 };
  const r     = rank[role] ?? 0;
  if (level === 'super_admin') return r >= 4;
  if (level === 'team_admin')  return r >= 3;
  if (level === 'member')      return r >= 1;
  return true;
}
window._meetsRoleLevel = _meetsRoleLevel;


const LogPanel = (() => {
  let _allLines = [];
  let _autoRefreshTimer = null;

  function show() {
    document.getElementById('log-panel')?.classList.remove('hidden');
    refresh();
    // 面板打开时每 30s 自动刷新
    if (!_autoRefreshTimer) {
      _autoRefreshTimer = setInterval(refresh, 30_000);
    }
  }

  function hide() {
    document.getElementById('log-panel')?.classList.add('hidden');
    clearInterval(_autoRefreshTimer);
    _autoRefreshTimer = null;
  }

  async function refresh() {
    try {
      const lines = [];

      // 1. 后端服务日志（/admin/debug-logs）
      if (window._cloudFetch) {
        const res = await window._cloudFetch('/admin/debug-logs?limit=200').catch(() => null);
        if (res?.data) lines.push(...res.data.map(l => '[Backend] ' + l));
      }

      // 2. 主进程日志（IPC win:get-main-log）
      if (window.electronAPI?.getMainLog) {
        const r = await window.electronAPI.getMainLog().catch(() => null);
        if (r?.data) lines.push(...r.data.map(l => '[Electron] ' + l));
      }

      if (lines.length) {
        _allLines = lines;
        _render();
      }
    } catch(e) {
      dbg.warn('[Log] 刷新失败: ' + e);
    }
  }

  function _render() {
    const filter = document.getElementById('log-level-filter')?.value || 'all';
    const body   = document.getElementById('log-body');
    if (!body) return;

    const lines = filter === 'all'
      ? _allLines
      : _allLines.filter(l => l.toUpperCase().includes(filter.toUpperCase()));

    body.innerHTML = lines.map(l => {
      const color = l.includes('ERROR')   ? '#f38ba8' :
                    l.includes('WARNING') || l.includes('WARN') ? '#f9e2af' : '#a6e3a1';
      return `<div style="color:${color};padding:1px 0;border-bottom:1px solid rgba(255,255,255,0.05);font-size:12px;">${_esc(l)}</div>`;
    }).join('');
    body.scrollTop = body.scrollHeight;
  }

  function _esc(s) {
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  function init() {
    document.getElementById('log-level-filter')
            ?.addEventListener('change', _render);
    document.getElementById('btn-refresh-log')
            ?.addEventListener('click', refresh);
    document.getElementById('btn-log-copy')
            ?.addEventListener('click', () => {
      const text = _allLines.join('\n');
      navigator.clipboard.writeText(text).then(() => {
        const btn = document.getElementById('btn-log-copy');
        if (!btn) return;
        const orig = btn.textContent;
        btn.textContent = '✓';
        setTimeout(() => { btn.textContent = orig; }, 1500);
      }).catch(() => {});
    });
  }

  return { show, hide, refresh, init };
})();

window.LogPanel = LogPanel;


// ===================== 全局快捷键 =====================
function _bindShortcuts() {
  document.addEventListener('keydown', e => {
    if (e.ctrlKey && e.key === 'o')  { e.preventDefault(); GlobalSearch.show(); }
    if (e.ctrlKey && e.key === 'p')  { e.preventDefault(); CmdPalette.show(); }
    if (e.ctrlKey && e.key === ',')  { e.preventDefault(); TabManager.open('settings'); }
    if (e.key === 'Escape' &&
        !document.getElementById('cmd-overlay').classList.contains('hidden')) {
      CmdPalette.hide();
    }
    if (e.key === 'Escape' &&
        !document.getElementById('gs-overlay')?.classList.contains('hidden')) {
      GlobalSearch.hide();
    }
  });

  // Ctrl+Tab / Ctrl+1~9：由 Electron before-input-event 拦截后通过 IPC 分发
  window.electronAPI?.onTabShortcut?.((data) => {
    if (data.action === 'cycle') WorkspaceEngine.switchTabByOffset(data.shift ? -1 : 1);
    if (data.action === 'index') WorkspaceEngine.switchTabByIndex(data.n);
  });
  // Ctrl+O IPC 路径（重启 Electron 后生效，补充 globalShortcut 穿透）
  window.electronAPI?.onGlobalSearchShow?.(() => GlobalSearch.show());
}


// ===================== 左侧导航点击（仅处理静态的设置项）=====================
function _bindNavSidebar() {
  // 动态 nav 项由 NavManager.boot() 绑定；sidebar 切换按钮已在 workspace.js tab bar 里注册
}


// ===================== 状态栏按钮 =====================
function _bindStatusbar() {
  document.getElementById('btn-debug')?.addEventListener('click', () =>
    document.getElementById('debug-panel').classList.toggle('hidden'));

  document.getElementById('btn-log')?.addEventListener('click', () => {
    const panel = document.getElementById('log-panel');
    panel.classList.toggle('hidden');
    if (!panel.classList.contains('hidden')) LogPanel.refresh();
  });

  document.getElementById('btn-cmd-palette')?.addEventListener('click', () =>
    CmdPalette.show());

  document.getElementById('btn-notif')?.addEventListener('click', () => {
    const panel = document.getElementById('notif-panel');
    const isHidden = panel.classList.contains('hidden');
    panel.classList.toggle('hidden');
    if (isHidden) NotifManager.loadPanel();
  });

  document.getElementById('btn-notif-read-all')?.addEventListener('click', async () => {
    await NotifManager.readAll();
    NotifManager.loadPanel();
  });
}


// ===================== DOM 就绪：初始化所有模块 =====================
document.addEventListener('DOMContentLoaded', () => {
  // 将 backendUrl 写入 localStorage，供 iframe 及所有子页面使用
  // 网页版：electronAPI.getConfig() 由 web_compat.js polyfill 提供，
  //         返回 window.location.origin，无需手动配置。
  window.electronAPI?.getConfig?.().then(async cfg => {
    const url = await _getRuntimeBackendBase(cfg?.backendUrl || '');
    if (window.AI00RuntimeConfig?.storeBackendBase) {
      window.AI00RuntimeConfig.storeBackendBase(url);
    } else {
      window._AI00_BASE = url;
      localStorage.setItem('ai00_backend_url', url);
    }
  }).catch(async () => {
    const inferred = await _getRuntimeBackendBase('');
    if (window.AI00RuntimeConfig?.storeBackendBase) {
      window.AI00RuntimeConfig.storeBackendBase(inferred);
    } else {
      window._AI00_BASE = inferred;
      localStorage.setItem('ai00_backend_url', inferred);
    }
  });
  ThemeManager.init();
  // 立即从 localStorage 读取认证状态，避免状态栏短暂显示"未登录"
  // AuthStateManager.init() 是异步的但基于 localStorage，几乎瞬间完成
  AuthStateManager.init().then(() => {
    _applyStatusbarFlags();
    NavManager.render();
  }).catch(() => {});
  TabManager.boot();
  NavManager.boot();
  CmdPalette.init();
  GlobalSearch.init();
  LogPanel.init();
  _bindNavSidebar();
  _bindShortcuts();
  _bindStatusbar();
  _applyStatusbarFlags();   // 用初始默认值先遮住无权限按钮
  // Phase 2：从 PluginRegistry 动态加载 Tab/Nav（补充 manifest 中声明的、硬编码中未包含的条目）
  Promise.all([
    TabManager.loadFromRegistry(),
    NavManager.loadFromRegistry(),
  ]).catch(e => console.warn('[Main] PluginRegistry 加载失败:', e));
  // 飞书模式下启动通知轮询（auth 状态就绪后触发）
  window.electronAPI?.onAuthStateChanged?.((state) => {
    // 更新全局 auth 状态（账户切换时确保 _authUser/_authMode 是最新值）
    window._authMode  = state?.mode  || 'none';
    window._authUser  = state?.user  || null;
    window._authToken = state?.token || '';
    _addCrumb('auth', `登录状态: ${window._authMode}`);
    if (state?.mode === 'feishu') {
      NotifManager.startPolling();
      TaskTimeline.refresh();   // auth 就绪后立即加载日程，无需等待定时器
      _startHealthCheck();
    } else {
      _stopHealthCheck();
    }
    // 关闭当前用户无权访问的已打开 Tab（账户切换时生效）
    TabManager.closeUnauthorizedTabs();
    NavManager.render();          // 重新渲染导航（可见性可能因角色变化）
    _applyStatusbarFlags();       // 角色确认后重新计算可见/可用
    // 工作台及所有已打开 Tab 的 iframe 重载：确保面板数据随新用户刷新
    // （工作台有 localStorage 前缀依赖，必须完整重载；其他 Tab 也可能有缓存数据）
    WorkspaceEngine.reloadAllTabs();
  });
  // 跨窗口主题同步（设置窗口改主题后广播到主窗口）
  window.electronAPI?.onThemeChanged?.((theme) => ThemeManager.applyTheme(theme));

  // AI 弹出窗口 navigate_to_page 工具 → 主窗口打开对应页面
  window.electronAPI?.onAiNavigate?.((opts) => {
    if (opts?.viewId) TabManager.open(opts.viewId, opts.params || {});
  });

  // 深链接处理：ai00://list/{token} → 解析 token → 打开或申请权限
  window.electronAPI?.onDeepLink?.((url) => {
    _handleDeepLink(url);
  });

  // Hub iframe 弹出：tab:open → 新 Tab（保留 hub 导航）；float:open → 悬浮窗（裸页面）
  window.addEventListener('message', e => {
    // ── iframe 子页面错误气泡 ──────────────────────────────────────────
    if (e.data?.type === 'iframe:error') {
      dbg.error(`[iframe:${e.data.src || '?'}] ${e.data.msg}${e.data.stack ? '\n' + e.data.stack.split('\n')[0] : ''}`);
    }

    if (e.data?.type === 'tab:open' && e.data.id) {
      const { id, tabKey, params } = e.data;
      TabManager.open(id, params || (tabKey ? { tabKey } : {}));
    }
    if (e.data?.type === 'float:open' && e.data.webSrc) {
      window.electronAPI?.showFloatShell?.({ initialSrc: e.data.webSrc });
    }
    // 网页版：弹窗型页面（settings / AI 对话等）以覆盖层显示
    if (e.data?.type === 'open-overlay' && e.data.src) {
      _openOverlay(e.data.src, e.data.title || '');
    }
  });

  // 网页版覆盖层（替代 Electron 独立窗口）：在主页面上显示 iframe 全屏遮罩
  window._openOverlay = function(src, title = '') {
    const existing = document.getElementById('_web_overlay');
    if (existing) existing.remove();

    const overlay = document.createElement('div');
    overlay.id = '_web_overlay';
    overlay.style.cssText = [
      'position:fixed;inset:0;z-index:9999',
      'background:rgba(0,0,0,.55)',
      'display:flex;align-items:center;justify-content:center',
    ].join(';');

    const box = document.createElement('div');
    box.style.cssText = [
      'position:relative;width:880px;max-width:96vw',
      'height:80vh;max-height:720px',
      'background:var(--bg-base,#1e1e2e)',
      'border-radius:10px;overflow:hidden',
      'box-shadow:0 24px 80px rgba(0,0,0,.6)',
      'display:flex;flex-direction:column',
    ].join(';');

    // 标题栏
    const titleBar = document.createElement('div');
    titleBar.style.cssText = 'display:flex;align-items:center;justify-content:space-between;padding:0 16px;height:40px;border-bottom:1px solid var(--border-subtle,#333);flex-shrink:0';
    titleBar.innerHTML = `<span style="font-size:13px;font-weight:600;color:var(--text-normal,#ccc)">${title || src.split('/').pop()}</span>`;
    const closeBtn = document.createElement('button');
    closeBtn.textContent = '✕';
    closeBtn.style.cssText = 'background:none;border:none;color:var(--text-muted,#888);font-size:14px;cursor:pointer;padding:4px 8px;border-radius:4px';
    closeBtn.onclick = () => overlay.remove();
    titleBar.appendChild(closeBtn);
    box.appendChild(titleBar);

    // iframe 内容
    const iframe = document.createElement('iframe');
    iframe.src = src;
    iframe.style.cssText = 'flex:1;border:none;width:100%;height:0';
    iframe.allow = 'clipboard-read;clipboard-write';
    box.appendChild(iframe);

    overlay.appendChild(box);
    // 点遮罩关闭
    overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });
    document.body.appendChild(overlay);
  };

  dbg.log('✅ 主界面初始化完成');
  if (window.electronAPI) _initUpdateBanner();
});


// ── 深链接处理 ─────────────────────────────────────────────────────────────────
async function _handleDeepLink(url) {
  if (!url) return;
  try {
    const u = new URL(url);
    // ai00://issues?list_gid=xxx — 分享页跳转
    if (u.hostname === 'issues') {
      if (window._authMode !== 'feishu') return;
      const listGid = u.searchParams.get('list_gid');
      TabManager.open('issue', listGid ? { list_gid: listGid } : {});
      return;
    }
    // ai00://share/{token}
    const match = url.match(/^ai00:\/\/share\/([A-Za-z0-9_-]+)/);
    if (!match) return;
    const token = match[1];
    if (window._authMode !== 'feishu') return;
    const data = await window._cloudFetch(`/api/share-links/${token}`);
    if (data.current_permission && data.current_permission !== 'none') {
      // 有权限直接打开
      if (data.target_type === 'list') {
        TabManager.open('task', { list_gid: data.target_gid });
      }
    } else if (data.can_request) {
      // 无权限 → 弹申请弹窗
      _showPermissionRequestDialog(token, data.display_name || data.target_gid);
    }
  } catch (e) {
    dbg.warn('[DeepLink] 处理失败: ' + e.message);
  }
}

function _showPermissionRequestDialog(token, displayName) {
  document.getElementById('_perm-req-dialog')?.remove();
  const dlg = document.createElement('div');
  dlg.id = '_perm-req-dialog';
  dlg.style.cssText = 'position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,0.55);display:flex;align-items:center;justify-content:center';
  dlg.innerHTML = `
    <div style="background:var(--bg-secondary,#181825);border:1px solid var(--border-default,#313244);border-radius:12px;padding:24px;min-width:340px;max-width:480px;box-shadow:0 8px 32px rgba(0,0,0,0.4)">
      <h3 style="margin:0 0 8px;font-size:15px;color:var(--text-normal,#cdd6f4)">访问权限申请</h3>
      <p style="margin:0 0 14px;font-size:13px;color:var(--text-muted,#a6adc8)">您没有访问 <b>${displayName}</b> 的权限，是否向 Owner 申请访问？</p>
      <div style="margin-bottom:14px">
        <label style="font-size:12px;color:var(--text-muted,#a6adc8)">申请理由（可选）</label>
        <textarea id="_prd-message" rows="2" style="width:100%;margin-top:4px;padding:6px 8px;background:var(--bg-primary,#1e1e2e);border:1px solid var(--border-default,#313244);border-radius:6px;color:var(--text-normal,#cdd6f4);font-size:13px;resize:none;box-sizing:border-box"></textarea>
      </div>
      <div style="display:flex;gap:10px;justify-content:flex-end">
        <button id="_prd-cancel" style="padding:6px 14px;background:transparent;border:1px solid var(--border-default,#313244);color:var(--text-muted,#a6adc8);border-radius:6px;cursor:pointer;font-size:13px">取消</button>
        <button id="_prd-submit" style="padding:6px 14px;background:var(--color-accent,#89b4fa);color:var(--bg-primary,#1e1e2e);border:none;border-radius:6px;cursor:pointer;font-size:13px;font-weight:500">申请访问</button>
      </div>
    </div>
  `;
  document.body.appendChild(dlg);
  dlg.querySelector('#_prd-cancel').onclick = () => dlg.remove();
  dlg.querySelector('#_prd-submit').onclick = async () => {
    const btn = dlg.querySelector('#_prd-submit');
    const message = dlg.querySelector('#_prd-message').value.trim();
    btn.disabled = true; btn.textContent = '提交中...';
    try {
      await window._cloudFetch('/api/permission-requests', {
        method: 'POST',
        body: JSON.stringify({ target_type: 'list', target_gid: token, message }),
      });
      _showToast('申请已发送，等待 Owner 审批', 'success');
      dlg.remove();
    } catch (e) {
      _showToast('提交失败：' + e.message, 'error');
      btn.disabled = false; btn.textContent = '申请访问';
    }
  };
}


// ===================== 全局功能开关缓存 =====================
// 静态默认值：DB 未覆盖前生效，防止按钮在权限加载完成前闪现
window._featureFlags = {
  rule_engine: true, ai_assistant: true,
  // 状态栏：默认值（DB 加载后会被覆盖）
  sb_ai_chat:       { visibility: 'member', availability: 'all' },
  sb_ai_canvas:     { visibility: 'member', availability: 'all' },
  sb_tracker:       { visibility: 'super_admin', availability: 'all' },
  sb_debug:         { visibility: 'super_admin', availability: 'all' },
  sb_schedule:      { visibility: 'all',          availability: 'all' },
  sb_task_planning: { visibility: 'all',         availability: 'all' },
  sb_notif:         { visibility: 'all',         availability: 'all' },
  sb_log:           { visibility: 'all',         availability: 'all' },
  sb_ai_balance:    { visibility: 'super_admin', availability: 'all' },
};

/**
 * 根据 feature_flags 和当前用户角色，设置状态栏右侧各按钮的可见性/可用性。
 * 在 DOMContentLoaded、_loadFeatureFlags 完成、onAuthStateChanged 三处调用。
 */
function _applyStatusbarFlags() {
  const flags = window._featureFlags || {};
  const SB_MAP = [
    { flag: 'sb_schedule',      id: 'sb-schedule-bar'   },
    { flag: 'sb_ai_chat',       id: 'btn-ai-chat'       },
    { flag: 'sb_ai_canvas',     id: 'btn-ai-canvas'     },
    { flag: 'sb_tracker',       id: 'btn-tracker'       },
    { flag: 'sb_task_planning', id: 'btn-task-planning' },
    { flag: 'sb_notif',         id: 'btn-notif'         },
    { flag: 'sb_log',           id: 'btn-log'           },
    { flag: 'sb_debug',         id: 'btn-debug'         },
    { flag: 'sb_ai_balance',    id: 'ai-balance-display'},
  ];
  for (const { flag, id } of SB_MAP) {
    const el = document.getElementById(id);
    if (!el) continue;
    const ff    = flags[flag] || {};
    const vis   = ff.visibility   ?? 'all';
    const avail = ff.availability ?? 'all';
    const canSee = _meetsRoleLevel(vis);
    const canUse = _meetsRoleLevel(avail);
    el.classList.toggle('sb-ff-hidden',   !canSee);
    el.classList.toggle('sb-ff-disabled',  canSee && !canUse);
    if (el.tagName === 'BUTTON') {
      if (canSee && !canUse) el.setAttribute('disabled', '');
      else                   el.removeAttribute('disabled');
    }
  }
}

async function _loadFeatureFlags() {
  try {
    if (window._cloudFetch) {
      const res = await window._cloudFetch('/admin/config/feature_flags');
      if (res?.data?.value) {
        const parsed = JSON.parse(res.data.value);
        Object.assign(window._featureFlags, parsed);
      }
    }
  } catch(e) {
    dbg.warn('[FeatureFlags] 加载失败(cloud): ' + e);
  }
  // sb_schedule 始终对成员及以上可见（防止旧 DB 值覆盖）
  if (!window._featureFlags.sb_schedule ||
      window._featureFlags.sb_schedule?.visibility === 'super_admin' ||
      window._featureFlags.sb_schedule?.visibility === 'team_admin') {
    window._featureFlags.sb_schedule = { visibility: 'all', availability: 'all' };
  }

  // 加载完后重新渲染导航（应用可见性）
  NavManager.render();
  _applyStatusbarFlags();
  // 广播给所有 iframe（workbench App 面板等）
  document.querySelectorAll('iframe').forEach(f => {
    try { f.contentWindow?.postMessage({ type: 'feature-flags-changed' }, '*'); } catch(_) {}
  });
}

// ── 网络请求日志 ──────────────────────────────────────────────────────────────
const _netLog = [];
const _NET_MAX = 100;

function _netPush(entry) {
  // entry: { reqId, method, path, status, ms, ok, err? }
  entry.ts = new Date().toTimeString().slice(0, 8);
  _netLog.push(entry);
  if (_netLog.length > _NET_MAX) _netLog.shift();
  _netRender();
}

function _netRender() {
  const el = document.getElementById('debug-net');
  if (!el || el.style.display === 'none') return;
  el.innerHTML = [..._netLog].reverse().map(e => {
    const color = !e.ok ? '#f38ba8' : e.ms > 2000 ? '#f9e2af' : '#a6e3a1';
    const bars = Math.min(20, Math.ceil(e.ms / 100));
    const bar = '█'.repeat(bars);
    const method = (e.method || 'GET').padEnd(5);
    const path   = (e.path || '').slice(0, 28).padEnd(28);
    const status = String(e.status || 'ERR').padStart(3);
    const ms     = String(e.ms).padStart(5);
    return `<div style="color:${color};padding:1px 0;border-bottom:1px solid rgba(255,255,255,0.05);white-space:nowrap;overflow:hidden;"
                 title="reqId: ${e.reqId}${e.err ? '\n' + e.err : ''}"
            >${e.ts} ${method} ${path} ${status} ${ms}ms ${bar}</div>`;
  }).join('');
}
window._netRender = _netRender;

// ── 面包屑轨迹 ─────────────────────────────────────────────────────────────
const _crumbs = [];
const _CRUMB_MAX = 50;

function _addCrumb(category, msg) {
  const ts = new Date().toTimeString().slice(0, 8);
  _crumbs.push({ ts, category, msg });
  if (_crumbs.length > _CRUMB_MAX) _crumbs.shift();
  _crumbRender();
}

function _crumbRender() {
  const el = document.getElementById('debug-crumbs');
  if (!el || el.style.display === 'none') return;
  const catColors = { nav:'#89b4fa', api:'#a6e3a1', auth:'#cba6f7', error:'#f38ba8', ui:'#f9e2af' };
  el.innerHTML = [..._crumbs].reverse().map(c => {
    const color = catColors[c.category] || '#cdd6f4';
    const cat = c.category.padEnd(5).toUpperCase();
    return `<div style="color:${color};padding:1px 0;border-bottom:1px solid rgba(255,255,255,0.05);white-space:nowrap;overflow:hidden;">` +
           `${c.ts} [${cat}] ${c.msg}</div>`;
  }).join('');
}
window._addCrumb = _addCrumb;

// ── 后端健康检查心跳 ─────────────────────────────────────────────────────────
let _healthCheckTimer = null;

async function _runHealthCheck() {
  const dot = document.getElementById('health-dot');
  if (!dot || !window._cloudFetch) return;
  try {
    const r = await window._cloudFetch('/health');
    const ok = r?.status === 'ok';
    dot.style.background = ok ? '#a6e3a1' : '#f9e2af';
    dot.title = ok
      ? `后端正常 | DB: ${r.db} | 连接池: ${JSON.stringify(r.pool)} | 运行: ${r.uptime_s}s`
      : `后端降级 | ${JSON.stringify(r)}`;
    if (!ok) dbg.warn('[Health] degraded: ' + JSON.stringify(r));
    else dbg.log('[Health] ok uptime=' + r.uptime_s + 's');
  } catch (e) {
    if (dot) { dot.style.background = '#f38ba8'; dot.title = '后端无响应: ' + e.message; }
    dbg.error('[Health] 无法连接后端: ' + e.message);
  }
}

function _startHealthCheck() {
  _runHealthCheck();
  if (_healthCheckTimer) clearInterval(_healthCheckTimer);
  _healthCheckTimer = setInterval(_runHealthCheck, 30_000);
}

function _stopHealthCheck() {
  clearInterval(_healthCheckTimer);
  _healthCheckTimer = null;
  const dot = document.getElementById('health-dot');
  if (dot) { dot.style.background = '#555'; dot.title = '后端健康状态（未登录）'; }
}

// 监听设置窗口发出的功能开关变更消息
window.addEventListener('message', e => {
  if (e.data?.type === 'feature-flags-changed') _loadFeatureFlags();
  // ── 容器卡片关闭 Tab ────────────────────────────────────────────
  if (e.data?.type === 'cc:close-tab' && e.data.tabId) {
    WorkspaceEngine?.closeTab?.(e.data.tabId);
    // 关闭后落到欢迎页时，自动跳到工作台
    if (!WorkspaceEngine?.activeTabId?.() || WorkspaceEngine.activeTabId() === 'welcome') {
      TabManager?.open('workbench');
    }
  }

  // ── DataRegistry 中继（模块 iframe → 父窗口 → 工作台 iframe）──
  if (e.data?.type === 'dr:register') {
    window._drRegistry = window._drRegistry || {};
    window._drRegistry[e.data.moduleId] = e.data.spec;
    // relay to all iframes (workbench will pick it up)
    document.querySelectorAll('iframe').forEach(f => {
      try { f.contentWindow?.postMessage(e.data, '*'); } catch (_) {}
    });
  }
  if (e.data?.type === 'dr:get-all') {
    try {
      e.source?.postMessage({ type: 'dr:all', registry: window._drRegistry || {} }, '*');
    } catch (_) {}
  }

  // ── 清单导航（工作区左侧边栏 ↔ 任务/问题页面）─────────────────────
  const _lnState = (window._listNavState || (window._listNavState = {}));

  // task/issue 页通知：激活对应清单导航 leaf，并同步当前选中 gid
  if (e.data?.type === 'ls:nav:activate') {
    const { itemType, gid } = e.data;
    if (!_lnState[itemType]) _lnState[itemType] = {};
    _lnState[itemType].selectedGid = gid === undefined ? null : gid;
  }

  // list_nav.html leaf 已就绪，回传当前选中 gid
  if (e.data?.type === 'ls:nav:ready') {
    const { itemType } = e.data;
    if (!_lnState[itemType]) _lnState[itemType] = {};
    _lnState[itemType].win = e.source;
    const gid = _lnState[itemType]?.selectedGid ?? null;
    try { e.source?.postMessage({ type: 'ls:nav:sync', gid }, '*'); } catch (_) {}
  }

  // list_nav.html 用户点击了某个清单 → 转发给对应模块 iframe
  if (e.data?.type === 'ls:nav') {
    const { itemType, gid } = e.data;
    if (!_lnState[itemType]) _lnState[itemType] = {};
    _lnState[itemType].selectedGid = gid === undefined ? null : gid;
    let iframe = WorkspaceEngine?.getTabIframe?.(itemType);
    if (iframe) {
      try { iframe.contentWindow?.postMessage({ type: 'ls:nav', gid }, '*'); } catch (_) {}
    } else {
      // Tab 未打开，先打开再发送
      window.TabManager?.open(itemType);
      let attempts = 0;
      const _retry = setInterval(() => {
        iframe = WorkspaceEngine?.getTabIframe?.(itemType);
        if (iframe || ++attempts > 15) {
          clearInterval(_retry);
          try { iframe?.contentWindow?.postMessage({ type: 'ls:nav', gid }, '*'); } catch (_) {}
        }
      }, 200);
    }
  }

  // list_nav.html "新建清单" 按钮 → 转发给模块 iframe
  if (e.data?.type === 'ls:nav:new') {
    const { itemType } = e.data;
    const iframe = WorkspaceEngine?.getTabIframe?.(itemType);
    try { iframe?.contentWindow?.postMessage({ type: 'ls:nav:new' }, '*'); } catch (_) {}
  }

  // 工作台 → 高亮指定条目（ls:highlight）
  if (e.data?.type === 'ls:highlight') {
    const { itemType, gid } = e.data;
    let iframe = WorkspaceEngine?.getTabIframe?.(itemType);
    const _send = () => {
      try { iframe?.contentWindow?.postMessage({ type: 'ls:highlight', gid }, '*'); } catch (_) {}
    };
    if (iframe) {
      _send();
    } else {
      let attempts = 0;
      const _retry = setInterval(() => {
        iframe = WorkspaceEngine?.getTabIframe?.(itemType);
        if (iframe || ++attempts > 20) { clearInterval(_retry); _send(); }
      }, 200);
    }
  }

  // ── 内容树 ────────────────────────────────────────────────────────────
  // content_tree iframe 就绪：发送当前树数据
  if (e.data?.type === 'ct:ready') {
    ContentTreeManager._onLeafReady(e.source);
  }
  // content_tree iframe 更新了树：持久化
  if (e.data?.type === 'ct:update' && e.data.tree) {
    ContentTreeManager._onTreeUpdate(e.data.tree);
  }
  // content_tree iframe 请求打开内容
  if (e.data?.type === 'ct:open' && e.data.tabId) {
    ContentTreeManager._openContent(e.data);
  }
  // 任意子 iframe 通过 ct:pin 固定一个条目
  if (e.data?.type === 'ct:pin' && e.data.item) {
    ContentTreeManager.pinItem(e.data.item, e.data.groupId);
  }
});

// ── 快速清单（侧边栏已移除，该功能暂停）
window._addQuickListLeaf = function () {};

// ── 通知 Toast ──────────────────────────────────────────────────────
function _showToast(msg, level = 'info', duration = 4000) {
  const existing = document.getElementById('ai00-toast-container');
  const container = existing || (() => {
    const el = document.createElement('div');
    el.id = 'ai00-toast-container';
    el.style.cssText = 'position:fixed;bottom:64px;right:20px;z-index:9999;display:flex;flex-direction:column-reverse;gap:8px;pointer-events:none;';
    document.body.appendChild(el);
    return el;
  })();

  const toast = document.createElement('div');
  const colors = { info: '#3d84f7', success: '#40c057', warning: '#fab005', error: '#fa5252' };
  toast.style.cssText = `
    background: var(--bg-float, #2a2a40);
    border-left: 3px solid ${colors[level] || colors.info};
    color: var(--text-normal, #ddd);
    padding: 8px 14px;
    border-radius: 4px;
    font-size: 13px;
    max-width: 320px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.4);
    pointer-events: auto;
    opacity: 1;
    transition: opacity 0.3s;
  `;
  toast.textContent = msg;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// ── 数据库模式指示器（状态栏 #db-mode-indicator）──────────────────
function _updateDbMode(mode) {
  const el = document.getElementById('db-mode-indicator');
  if (!el) return;
  const labels = { local: '本地', cloud: '云端', syncing: '同步中' };
  el.textContent = labels[mode] || mode;
  el.className = `db-mode-${mode}`;
}

// 监听 Python → 前端推送的 WS 事件（由 bridge.js 自动建立连接）
window.addEventListener('ai00:notification', e => {
  const { message, level } = e.detail || {};
  if (message) _showToast(message, level || 'info');
});

window.addEventListener('ai00:db_mode_changed', e => {
  _updateDbMode(e.detail?.mode || 'local');
});

window.addEventListener('ai00:sync_status', e => {
  const { status, message } = e.detail || {};
  if (status === 'syncing') _updateDbMode('syncing');
  else if (status === 'done') _updateDbMode(e.detail?.mode || 'local');
  if (message) _showToast(message, status === 'error' ? 'error' : 'info', 3000);
});

window.addEventListener('ai00:log', e => {
  // 同步日志到调试面板
  const { level, message } = e.detail || {};
  if (level && message) dbg.log(`[${level}] ${message}`);
});

// Electron 原生 IPC：db 模式由 tray 右键菜单切换时推送
window.electronAPI?.onDbModeChanged?.(mode => _updateDbMode(mode));


// ══════════════════════════════════════════════════════════════
// 全局云端 Fetch 工具（直接调用 backend:8080，携带 JWT）
// 用法：await window._cloudFetch('/api/projects', { method: 'POST', body: JSON.stringify({...}) })
// ══════════════════════════════════════════════════════════════

// 工序截图进度（供 cad_sim / assoc_panel 跨 iframe 更新状态栏绿色文字）
window._showCaptureProgress = function(msg) {
  const el = document.getElementById('capture-progress-msg');
  if (!el) return;
  clearTimeout(el._hideTimer);
  if (msg) {
    el.textContent = msg;
    el.style.display = '';
    el._hideTimer = setTimeout(() => { el.style.display = 'none'; el.textContent = ''; }, 8000);
  } else {
    el.style.display = 'none';
    el.textContent = '';
  }
};

window._cloudFetch = async function(path, opts = {}) {
  const config = (await window.electronAPI?.getConfig?.()) || {};
  const state  = (await window.electronAPI?.authGetState?.()) || {};
  const baseUrl = await _getRuntimeBackendBase(config.backendUrl || '');
  const token = state.token || '';
  const isFormData = typeof opts.body?.append === 'function';
  const reqId = Math.random().toString(36).slice(2, 9);
  const t0 = performance.now();
  const method = opts.method || 'GET';
  _addCrumb('api', `${method} ${path}`);
  let res;
  try {
    res = await fetch(`${baseUrl}${path}`, {
      ...opts,
      headers: {
        ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
        ...(token ? { 'X-AI00-Token': token } : {}),
        'X-Request-ID': reqId,
        ...(opts.headers || {}),
      },
    });
  } catch (networkErr) {
    const ms = Math.round(performance.now() - t0);
    dbg.error(`[API ${reqId}] 网络错误 ${method} ${path} ${ms}ms: ${networkErr.message}`);
    _netPush({ reqId, method, path, status: 0, ms, ok: false, err: networkErr.message });
    throw networkErr;
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    const detail = err.detail;
    const msg = typeof detail === 'string' ? detail
      : Array.isArray(detail) ? detail.map(e => e.msg || JSON.stringify(e)).join('; ')
      : detail ? JSON.stringify(detail) : `HTTP ${res.status}`;
    const ms = Math.round(performance.now() - t0);
    if (res.status >= 500) {
      dbg.error(`[API ${reqId}] ${method} ${path} → ${res.status} ${ms}ms: ${msg}`);
    } else if (res.status >= 400 && res.status !== 401 && res.status !== 403) {
      dbg.warn(`[API ${reqId}] ${method} ${path} → ${res.status} ${ms}ms: ${msg}`);
    }
    _netPush({ reqId, method, path, status: res.status, ms, ok: false, err: msg });
    // token 失效，跳登录页（网页版）
    if (res.status === 401 && window.electronAPI?._isElectron === false) {
      localStorage.removeItem('ai00_token');
      localStorage.removeItem('ai00_user');
      window.location.href = '/web/login/';
    }
    throw new Error(msg);
  }
  if (res.status === 204 || res.headers.get('content-length') === '0') {
    const ms = Math.round(performance.now() - t0);
    if (ms > 2000) dbg.warn(`[API ${reqId}] 🐢 慢请求 ${method} ${path} ${ms}ms`);
    _netPush({ reqId, method, path, status: res.status, ms, ok: true });
    return null;
  }
  const ms = Math.round(performance.now() - t0);
  if (ms > 2000) dbg.warn(`[API ${reqId}] 🐢 慢请求 ${method} ${path} ${ms}ms`);
  _netPush({ reqId, method, path, status: res.status, ms, ok: true });
  return res.json();
};


// ══════════════════════════════════════════════════════════════
// TaskTimeline — 状态栏中央任务时间线
// ══════════════════════════════════════════════════════════════

function _ttTodayStr() {
  return new Date().toISOString().slice(0, 10);
}
function _ttAddDays(dateStr, n) {
  const d = new Date(dateStr + 'T00:00:00');
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}
function _ttNextMonday() {
  const d = new Date(), day = d.getDay();
  d.setDate(d.getDate() + (day === 0 ? 1 : 8 - day));
  return d.toISOString().slice(0, 10);
}
function _ttMinToHHMM(min) {
  return `${String(Math.floor(min / 60)).padStart(2,'0')}:${String(min % 60).padStart(2,'0')}`;
}
function _ttEsc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

const TaskTimeline = {
  _tasks: [],        // today + future scheduled tasks
  _overdueTasks: [], // past/today overdue tasks
  _calEvents: [],    // today's feishu calendar events
  _timer: null,

  async init() {
    await this.refresh();
    this._scheduleNextTick();
    document.getElementById('sb-overdue-btn')?.addEventListener('click', (e) => {
      e.stopPropagation();
      this._toggleOverduePanel();
    });
  },

  async refresh() {
    await this._loadAll();
    this._render();
  },

  async _loadAll() {
    if (window._authMode !== 'feishu') {
      this._tasks = []; this._overdueTasks = []; this._calEvents = []; return;
    }
    const today = _ttTodayStr();
    const from30 = _ttAddDays(today, -30);

    // 飞书日历：仅当面板1设置中包含 'feishu' 时才拉取
    const _p1Settings = (() => {
      try { return JSON.parse(localStorage.getItem('wb:p1-settings') || 'null') || {}; } catch { return {}; }
    })();
    const _p1Src = _p1Settings.sources || null;
    const _feishuEnabled = !_p1Src || _p1Src.includes('feishu');
    const _taskEnabled   = !_p1Src || _p1Src.includes('task');

    // 并行拉取任务 + 飞书日历
    const [taskRes, calRes] = await Promise.allSettled([
      _taskEnabled ? window._cloudFetch(`/api/tasks?scheduled_date_from=${from30}&page_size=300`) : Promise.resolve({ data: [] }),
      _feishuEnabled ? window._cloudFetch('/feishu/calendar/today') : Promise.resolve({ data: [] }),
    ]);

    const all = taskRes.status === 'fulfilled' ? (taskRes.value?.data || []) : [];

    // 面板1清单过滤：若用户选择了特定清单，则只保留属于这些清单的任务
    const _taskListFilter = (() => {
      const lf = _p1Settings.listFilter?.task;
      return Array.isArray(lf) && lf.length > 0 ? new Set(lf) : null;
    })();
    const _matchesTaskFilter = (t) => !_taskListFilter || _taskListFilter.has(t.list_gid);

    const now = new Date();
    const nowMin = now.getHours() * 60 + now.getMinutes();
    const doneSt = new Set(['done', 'completed', 'closed', 'cancelled']);

    this._tasks = all.filter(t => t.scheduled_date >= today && _matchesTaskFilter(t));
    this._overdueTasks = all.filter(t => {
      if (doneSt.has(t.status) || !t.scheduled_date || !_matchesTaskFilter(t)) return false;
      if (t.scheduled_date < today) return true;
      if (t.scheduled_date === today && t.scheduled_start_time) {
        const [h, m] = t.scheduled_start_time.split(':').map(Number);
        return (h * 60 + m + (t.time_estimate || 30)) < nowMin;
      }
      return false;
    });

    // 飞书日历：排除已拒绝（decline）、忽略和全天事件
    const calRaw = calRes.status === 'fulfilled' ? (calRes.value?.data || []) : [];
    const _ignored = new Set(JSON.parse(localStorage.getItem('wb:cal-ignored') || '[]'));
    this._calEvents = calRaw.filter(e =>
      e.rsvp !== 'decline' && e.start !== '全天' && !_ignored.has(e.event_id)
    );
  },

  _computeCurrentAndNext() {
    const now = new Date();
    const nowMin = now.getHours() * 60 + now.getMinutes();
    const today = _ttTodayStr();

    // 今日任务
    const taskMapped = this._tasks
      .filter(t => t.scheduled_date === today && t.scheduled_start_time)
      .map(t => {
        const [h, m] = t.scheduled_start_time.split(':').map(Number);
        const start = h * 60 + m;
        return { ...t, _type: 'task', startMin: start, endMin: start + (t.time_estimate || 30) };
      });

    // 飞书日历事件（已是今日，过滤掉纯小时无效格式）
    const calMapped = this._calEvents
      .filter(e => /^\d{2}:\d{2}$/.test(e.start) && /^\d{2}:\d{2}$/.test(e.end))
      .map(e => {
        const [sh, sm] = e.start.split(':').map(Number);
        const [eh, em] = e.end.split(':').map(Number);
        return { ...e, _type: 'cal', _title: e.summary || '(无标题)',
                 startMin: sh * 60 + sm, endMin: eh * 60 + em };
      });

    const all = [...taskMapped, ...calMapped].sort((a, b) => a.startMin - b.startMin);
    const current = all.filter(t => t.startMin <= nowMin && nowMin < t.endMin);
    const next = all.find(t => t.startMin > nowMin)
              || this._tasks.find(t => t.scheduled_date > today && t.scheduled_start_time);
    return { current, next };
  },

  _render() {
    // 清空旧版 center 区域
    const centerEl = document.getElementById('statusbar-center');
    if (centerEl) centerEl.innerHTML = '';

    const bar    = document.getElementById('sb-schedule-bar');
    const infoEl = document.getElementById('sb-schedule-info');
    if (!bar || !infoEl) return;

    const { current, next } = this._computeCurrentAndNext();
    const hasContent = current.length || next || this._overdueTasks.length;
    // 只在 feishu 模式 + 有内容时展示；功能开关可见性由 _applyStatusbarFlags 的 sb-ff-hidden class 控制
    if (window._authMode === 'feishu') {
      bar.style.display = hasContent ? '' : 'none';
    } else {
      bar.style.display = 'none';
    }

    // 逾期徽标
    const overdueBtn   = document.getElementById('sb-overdue-btn');
    const overdueCount = document.getElementById('sb-overdue-count');
    if (overdueBtn && overdueCount) {
      const n = this._overdueTasks.length;
      overdueBtn.style.display = n ? '' : 'none';
      overdueCount.textContent = n;
    }

    // 当前 + 下一个
    if (!current.length && !next) { infoEl.innerHTML = ''; return; }

    // 标题提取（任务用 title，日历用 summary）
    const _itemTitle  = it => it._type === 'cal' ? (it.summary || '(无标题)') : (it.title || '');
    // 日历图标 SVG（小）
    const _calIcon = `<svg class="sb-cal-icon" width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="1" y="3" width="14" height="12" rx="1.5"/><line x1="5" y1="1" x2="5" y2="5"/><line x1="11" y1="1" x2="11" y2="5"/><line x1="1" y1="7" x2="15" y2="7"/></svg>`;

    let html = '';
    if (current.length) {
      const it = current[0];
      const isCal = it._type === 'cal';
      const extra = current.length > 1
        ? ` <span class="sb-task-sep">+${current.length - 1}</span>` : '';
      html += `<span class="sb-task-current${isCal ? ' sb-task-cal' : ''}" data-gid="${it.event_id || it.gid || ''}"
               title="${_ttEsc(_itemTitle(it))}">${isCal ? _calIcon : ''}${_ttEsc(_itemTitle(it))} · ~${_ttMinToHHMM(it.endMin)}</span>${extra}`;
    } else {
      html += `<span class="sb-task-idle">空闲</span>`;
    }
    if (next) {
      const isCal = next._type === 'cal';
      const timeLabel = isCal
        ? next.start.slice(0, 5)
        : (next.scheduled_start_time
            ? (next.scheduled_date === _ttTodayStr()
                ? next.scheduled_start_time.slice(0, 5)
                : next.scheduled_date.slice(5) + ' ' + next.scheduled_start_time.slice(0, 5))
            : next.scheduled_date);
      html += `<span class="sb-task-sep">·</span>
               <span class="sb-task-next${isCal ? ' sb-task-cal' : ''}" title="${_ttEsc(_itemTitle(next))}">${isCal ? _calIcon : ''}↓ ${_ttEsc(_itemTitle(next))} ${timeLabel}</span>`;
    }
    infoEl.innerHTML = html;
    infoEl.oncontextmenu = (e) => {
      e.preventDefault();
      // 飞书日历条目不显示 popover
      if (e.target.closest('.sb-task-cal')) return;
      const gid = e.target.closest('[data-gid]')?.dataset.gid || current[0]?.gid;
      const task = gid ? (this._tasks.find(t => t.gid === gid) || current[0]) : null;
      if (!task || task._type === 'cal') return;
      this._showCtxMenu(e, task, current.filter(c => c._type === 'task'));
    };
  },

  // ── 逾期面板 ───────────────────────────────────────────────────────────────
  _toggleOverduePanel() {
    const existing = document.getElementById('sb-overdue-panel');
    if (existing) { existing.remove(); return; }
    this._showOverduePanel();
  },

  _showOverduePanel() {
    document.getElementById('sb-overdue-panel')?.remove();
    const tasks = this._overdueTasks;

    const panel = document.createElement('div');
    panel.id = 'sb-overdue-panel';
    panel.className = 'sb-overdue-panel';

    if (!tasks.length) {
      panel.innerHTML = `<div class="sb-op-empty">暂无逾期任务</div>`;
    } else {
      const items = tasks.map(t => {
        const dateLabel = t.scheduled_date < _ttTodayStr()
          ? t.scheduled_date.slice(5)
          : (t.scheduled_start_time ? t.scheduled_start_time.slice(0, 5) : '今天');
        return `<div class="sb-op-item" data-gid="${t.gid}">
          <span class="sb-op-dot"></span>
          <span class="sb-op-title" title="${_ttEsc(t.title)}">${_ttEsc(t.title)}</span>
          <span class="sb-op-date">${dateLabel}</span>
          <button class="sb-op-act" data-act="today" data-gid="${t.gid}" title="推到今天">今天</button>
          <button class="sb-op-act" data-act="tomorrow" data-gid="${t.gid}" title="推到明天">明天</button>
        </div>`;
      }).join('');
      panel.innerHTML = `
        <div class="sb-op-hdr">
          <span>逾期任务 · ${tasks.length} 项</span>
          <button class="sb-op-close" id="sbOpClose">
            <svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="2" y1="2" x2="14" y2="14"/><line x1="14" y1="2" x2="2" y2="14"/></svg>
          </button>
        </div>
        <div class="sb-op-list">${items}</div>`;
    }

    // 定位到状态栏上方、逾期按钮右端对齐
    const btnRect = document.getElementById('sb-overdue-btn')?.getBoundingClientRect();
    document.body.appendChild(panel);
    const panelW = panel.offsetWidth || 320;
    const sbH = document.getElementById('statusbar')?.offsetHeight || 26;
    panel.style.bottom = (sbH + 4) + 'px';
    panel.style.left   = btnRect
      ? Math.max(8, Math.min(btnRect.left, window.innerWidth - panelW - 8)) + 'px'
      : '8px';

    panel.querySelector('#sbOpClose')?.addEventListener('click', () => panel.remove());

    panel.addEventListener('click', async (e) => {
      const btn = e.target.closest('.sb-op-act');
      if (!btn) return;
      const { act, gid } = btn.dataset;
      const task = tasks.find(t => t.gid === gid);
      if (!task) return;
      const today = _ttTodayStr();
      if (act === 'today')    await this._reschedule(task, today, task.scheduled_start_time || '09:00');
      if (act === 'tomorrow') await this._reschedule(task, _ttAddDays(today, 1), task.scheduled_start_time || '09:00');
      panel.remove();
    });

    // 点击外部关闭
    setTimeout(() => {
      document.addEventListener('mousedown', function h(ev) {
        const btn = document.getElementById('sb-overdue-btn');
        if (!panel.contains(ev.target) && ev.target !== btn && !btn?.contains(ev.target)) {
          panel.remove();
          document.removeEventListener('mousedown', h);
        }
      });
    }, 0);
  },

  _showCtxMenu(e, task, current) {
    document.querySelector('.sb-ctx-menu')?.remove();
    const menu = document.createElement('div');
    menu.className = 'sb-ctx-menu';

    const items = [
      { label: '延长 30 分钟',   fn: () => this._extend(task, 30) },
      { label: '延长 1 小时',    fn: () => this._extend(task, 60) },
      { sep: true },
      { label: '推到下午 13:00', fn: () => this._reschedule(task, null, '13:00') },
      { label: '推到明天',       fn: () => this._reschedule(task, _ttAddDays(task.scheduled_date, 1), task.scheduled_start_time) },
      { label: '推到下周一',     fn: () => this._reschedule(task, _ttNextMonday(), '09:00') },
      { sep: true },
      { sub: '更改状态' },
      { label: '▷ 进行中',      fn: () => this._save(task.gid, { status: 'in_progress' }) },
      { label: '✓ 已完成',      fn: () => this._save(task.gid, { status: 'completed' }) },
      { label: '⊘ 阻塞',        fn: () => this._save(task.gid, { status: 'blocked' }) },
      { sep: true },
      { label: '查看沟通',       fn: () => this._openEntries(task) },
    ];

    menu.innerHTML = items.map(it =>
      it.sep ? `<div class="sb-ctx-sep"></div>` :
      it.sub ? `<div class="sb-ctx-sub">${it.sub}</div>` :
               `<div class="sb-ctx-item">${_ttEsc(it.label)}</div>`
    ).join('');

    let actionIdx = 0;
    menu.querySelectorAll('.sb-ctx-item').forEach(el => {
      while (items[actionIdx]?.sep || items[actionIdx]?.sub) actionIdx++;
      const fn = items[actionIdx++]?.fn;
      if (fn) el.addEventListener('click', () => { menu.remove(); fn(); });
    });

    const pw = 170;
    // 先 append 再测量实际高度，确保定位准确
    document.body.appendChild(menu);
    const ph = menu.offsetHeight || 200;
    const left = Math.max(8, Math.min(e.clientX, window.innerWidth - pw - 8));
    // 状态栏在最底部，始终向上弹出，并防止超出视口顶部
    const top  = Math.max(8, e.clientY - ph - 6);
    menu.style.left = left + 'px';
    menu.style.top  = top  + 'px';
    setTimeout(() => document.addEventListener('mousedown', function h(ev) {
      if (!menu.contains(ev.target)) { menu.remove(); document.removeEventListener('mousedown', h); }
    }), 0);
  },

  async _extend(task, mins) {
    await this._save(task.gid, { time_estimate: (task.time_estimate || 30) + mins });
  },

  async _reschedule(task, date, time) {
    const upd = {};
    if (date !== null) upd.scheduled_date = date;
    if (time)          upd.scheduled_start_time = time;
    await this._save(task.gid, upd);
  },

  async _save(gid, fields) {
    try {
      await window._cloudFetch(`/api/tasks/${gid}`, {
        method: 'PUT', body: JSON.stringify({ gid, ...fields }),
      });
      await this.refresh();
    } catch (err) { console.error('[TaskTimeline] save:', err); }
  },

  async _openEntries(task) {
    let entries = [];
    try {
      const r = await window._cloudFetch(`/api/tasks/${task.gid}/entries`);
      entries = r?.data || [];
    } catch (_) {}

    const overlay = document.createElement('div');
    overlay.className = 'sb-entries-overlay';
    overlay.innerHTML = `
      <div class="sb-entries-modal">
        <div class="sb-entries-hdr">
          <span>${_ttEsc(task.title)}</span>
          <button class="float-close" id="sbEClose">✕</button>
        </div>
        <div class="sb-entries-body" id="sbEBody"></div>
        <div class="sb-entries-footer">
          <button class="status-btn" id="sbESave">保存</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    overlay.querySelector('#sbEClose').onclick = () => overlay.remove();
    overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });

    const bodyEl = overlay.querySelector('#sbEBody');
    if (typeof EntryThread !== 'undefined') {
      const user = window._authUser || {};
      const thread = new EntryThread({
        mountEl: bodyEl, mode: 'human', entries,
        issueId: task.gid,
        currentUserGid:  user.gid  || '',
        currentUserName: user.name || '我',
        isCloud: true,
        onChange: () => {},
        onSave: async (updated) => {
          try {
            await window._cloudFetch(`/api/tasks/${task.gid}/entries`,
              { method: 'PUT', body: JSON.stringify(updated) });
          } catch (_) {}
        },
      });
      thread.render?.() || thread._render?.();
      overlay.querySelector('#sbESave').onclick = async () => {
        thread.collectTexts?.();
        await thread._onSave?.(thread.getEntries?.());
        overlay.remove();
      };
    } else {
      bodyEl.innerHTML = '<div style="padding:16px;color:#888">请先打开任务清单以加载 EntryThread 组件</div>';
      overlay.querySelector('#sbESave').onclick = () => overlay.remove();
    }
  },

  _scheduleNextTick() {
    const now = new Date();
    const msToNextMin = (60 - now.getSeconds()) * 1000 - now.getMilliseconds();
    this._timer = setTimeout(() => {
      this.refresh();
      this._timer = setInterval(() => this.refresh(), 60_000);
    }, msToNextMin);
  },
};

// 启动（等待 auth 初始化完成后）
setTimeout(() => TaskTimeline.init(), 1800);
window.TaskTimeline = TaskTimeline;  // 外部可调用 refresh()


// ══════════════════════════════════════════════════════════════
// ContentTreeManager — 全局内容树（左侧边栏 leaf）
// ══════════════════════════════════════════════════════════════
const ContentTreeManager = (() => {
  const LS_KEY = 'ct:tree';
  const LEAF_SRC = 'content_tree/index.html';
  let _leafWin = null;    // content_tree iframe 的 contentWindow
  let _tree    = null;    // 当前树数据

  function _defaultTree() {
    return {
      groups: [
        { id: 'recent',      title: '最近访问', auto: true,  collapsed: false, items: [] },
        { id: 'grp_default', title: '我的收藏', auto: false, collapsed: false, items: [] },
      ],
    };
  }

  function _load() {
    try {
      const raw = localStorage.getItem(LS_KEY);
      if (raw) {
        const t = JSON.parse(raw);
        if (t?.groups) return t;
      }
    } catch (_) {}
    return _defaultTree();
  }

  function _save(tree) {
    _tree = tree;
    localStorage.setItem(LS_KEY, JSON.stringify(tree));
  }

  function _sendToLeaf(msg) {
    if (!_leafWin) return;
    try { _leafWin.postMessage(msg, '*'); } catch (_) {}
  }

  function _onLeafReady(win) {
    _leafWin = win;
    if (!_tree) _tree = _load();
    _sendToLeaf({ type: 'ct:data', tree: _tree });
    // 同步主题
    const theme = document.documentElement.dataset.theme || 'dark';
    _sendToLeaf({ type: 'theme', theme });
  }

  function _onTreeUpdate(tree) {
    _save(tree);
  }

  function _openContent({ tabId, tabKey, params }) {
    if (!tabId) return;
    // 若有 tabKey（hub 子页签），先设置激活
    if (tabKey) {
      try { localStorage.setItem(`hub:${tabId}:active`, tabKey); } catch (_) {}
    }
    window.TabManager?.open(tabId, params || {});
    // 若 hub 已在当前 Tab，通过 postMessage 激活子页签
    if (tabKey) {
      setTimeout(() => {
        const iframe = window.WorkspaceEngine?.getTabIframe?.(tabId);
        try { iframe?.contentWindow?.postMessage({ type: 'hub:activate', key: tabKey }, '*'); } catch (_) {}
      }, 150);
    }
  }

  function pinItem(item, groupId) {
    if (!_tree) _tree = _load();
    const grp = groupId
      ? _tree.groups.find(g => g.id === groupId)
      : _tree.groups.find(g => !g.auto);
    const target = grp || (() => {
      const ng = { id: 'grp_' + Date.now().toString(36), title: '我的收藏', auto: false, collapsed: false, items: [] };
      _tree.groups.push(ng);
      return ng;
    })();
    const key = JSON.stringify({ tabId: item.tabId, tabKey: item.tabKey, params: item.params });
    if (!target.items.some(i => JSON.stringify({ tabId: i.tabId, tabKey: i.tabKey, params: i.params }) === key)) {
      target.items.push({ id: 'itm_' + Date.now().toString(36), ...item });
    }
    _save(_tree);
    _sendToLeaf({ type: 'ct:data', tree: _tree });
    _showToast(`已固定"${item.title}"到内容树`, 'success', 2500);
  }

  function toggle() {
    // 侧边栏已移除，内容树 toggle 暂停
  }

  // 主题变更时同步给 leaf
  window.addEventListener('message', e => {
    if (e.data?.type === 'theme-change') {
      _sendToLeaf({ type: 'theme', theme: e.data.theme });
    }
  });

  // 绑定导航按钮
  document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('nav-content-tree-btn')?.addEventListener('click', toggle);
  });

  return { toggle, pinItem, _onLeafReady, _onTreeUpdate, _openContent };
})();

window.ContentTreeManager = ContentTreeManager;

// ══════════════════════════════════════════════════════════════
// 更新通知横幅（electron-updater 事件）
// ══════════════════════════════════════════════════════════════
function _initUpdateBanner() {
  if (!window.electronAPI?.onUpdateAvailable) return;

  const el = document.createElement('div');
  el.id = 'ai00-update-banner';
  el.className = 'ai00-upd-banner hidden';
  el.innerHTML = `
    <svg class="ai00-upd-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <polyline points="8 17 12 21 16 17"></polyline>
      <line x1="12" y1="3" x2="12" y2="21"></line>
    </svg>
    <span class="ai00-upd-msg" id="ai00-upd-msg"></span>
    <div class="ai00-upd-track" id="ai00-upd-track">
      <div class="ai00-upd-fill" id="ai00-upd-fill"></div>
    </div>
    <button class="ai00-upd-btn hidden" id="ai00-upd-btn">重启安装</button>
    <button class="ai00-upd-close" id="ai00-upd-close">✕</button>`;
  document.body.prepend(el);

  window.electronAPI.onUpdateAvailable(({ version }) => {
    el.classList.remove('hidden', 'ai00-upd-ready');
    document.body.style.paddingTop = '36px';
    document.getElementById('ai00-upd-msg').textContent = `发现新版本 v${version}，正在后台下载…`;
    document.getElementById('ai00-upd-track').style.display = '';
  });
  window.electronAPI.onUpdateProgress(({ percent }) => {
    const pct = Math.round(percent);
    document.getElementById('ai00-upd-fill').style.width = pct + '%';
    document.getElementById('ai00-upd-msg').textContent = `正在下载新版本… ${pct}%`;
  });
  window.electronAPI.onUpdateDownloaded(({ version }) => {
    el.classList.add('ai00-upd-ready');
    document.getElementById('ai00-upd-msg').textContent = `新版本 v${version} 已就绪`;
    document.getElementById('ai00-upd-track').style.display = 'none';
    document.getElementById('ai00-upd-btn').classList.remove('hidden');
  });
  document.getElementById('ai00-upd-btn')
    .addEventListener('click', () => window.electronAPI.installUpdate?.());
  document.getElementById('ai00-upd-close')
    .addEventListener('click', () => {
      el.classList.add('hidden');
      document.body.style.paddingTop = '';
    });
}
