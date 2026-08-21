/**
 * auth_state.js — 认证状态管理
 * 维护 window._authMode / _authUser / _authToken / _authOrgInfo
 * 保证现有 iframe 页面通过 window.parent._authMode 继续可用。
 *
 * 依赖：无（在所有其他模块前加载）
 */
const AuthStateManager = (() => {
  const _subscribers = [];
  const _ROLE_LABELS = Object.freeze({
    super_admin: '超级管理员',
    team_admin: '团队管理员',
    project_admin: '项目管理员',
    member: '成员',
    external: '外部用户',
  });

  // /users/me 的兼容路径返回 { success, data: profile }，而 /auth/me
  // 返回 profile 本身。统一在这里解包，避免子页面看到空 permissions。
  function _mergeUserProfile(user, response) {
    const envelope = response && typeof response === 'object' ? response : {};
    const profile = envelope.data && typeof envelope.data === 'object'
      ? envelope.data
      : envelope;
    const current = user && typeof user === 'object' ? user : {};
    return Object.assign({}, current, profile, {
      permissions: Array.isArray(profile.permissions)
        ? profile.permissions.slice()
        : (Array.isArray(current.permissions) ? current.permissions.slice() : []),
      grants: Array.isArray(profile.grants)
        ? profile.grants.slice()
        : (Array.isArray(current.grants) ? current.grants.slice() : []),
    });
  }

  function _formatUserStatus(user, mode) {
    const current = user && typeof user === 'object' ? user : null;
    if (!current || !mode || mode === 'none') {
      return { authenticated: false, text: '未登录', title: '未登录，尚未完成后端鉴权。' };
    }
    const name = current.name || current.display_name || current.email || current.gid || '当前用户';
    const role = current.org_role || current.system_role || current.role || '';
    const roleText = role ? `${_ROLE_LABELS[role] || role}（${role}）` : '角色待确认';
    const permissionCount = Array.isArray(current.permissions) ? current.permissions.length : 0;
    return {
      authenticated: true,
      text: `${name} · ${roleText}`,
      title: `已通过后端鉴权\n身份：${role || '未返回'}\n有效权限：${permissionCount} 项`,
    };
  }

  function _renderUserStatus(element, user, mode) {
    if (!element) return;
    const status = _formatUserStatus(user, mode);
    element.textContent = status.text;
    element.title = status.title;
    element.dataset.authenticated = status.authenticated ? 'true' : 'false';
  }

  function _publish(state) {
    // 更新全局变量（向后兼容）
    window._authMode    = state.mode    || 'none';
    window._authUser    = state.user    || null;
    window._authToken   = state.token   || '';
    window._authOrgInfo = state.orgInfo || null;

    _subscribers.forEach(fn => { try { fn(state); } catch(e) {} });
  }

  async function init() {
    try {
      if (window.electronAPI?.authGetState) {
        const state = await window.electronAPI.authGetState();
        window._authMode  = state?.mode  || 'none';
        window._authUser  = state?.user  || null;
        window._authToken = state?.token || null;
        // feishu 模式：从 /users/me 补充 grants + org_role
        if (state?.mode === 'feishu' && state?.token && window._authUser) {
          _refreshUserProfile(state.token).catch(() => {});
        }
      } else {
        // 非 Electron 环境（开发调试）：默认完全开放
        window._authMode = 'feishu';
      }
    } catch (_) {
      window._authMode = 'none';
    }
  }

  async function _refreshUserProfile(token) {
    try {
      const config = await window.electronAPI?.getConfig?.().catch(() => null);
      const runtimeBase = window.AI00RuntimeConfig?.getRuntimeBackendBase;
      const explicitBackendUrl = config?.backendUrl || '';
      const backendUrl = runtimeBase
        ? (await runtimeBase(explicitBackendUrl))
        : (
            explicitBackendUrl ||
            window._AI00_BASE ||
            localStorage.getItem('ai00_backend_url') ||
            window.AI00RuntimeConfig?.defaultLocalBackend ||
            ''
          ).replace(/\/$/, '');
      const res = await fetch(`${backendUrl}/users/me`, {
        headers: { 'X-AI00-Token': token },
      });
      if (!res.ok) return;
      const data = await res.json();
      if (data && window._authUser) {
        window._authUser = _mergeUserProfile(window._authUser, data);
        // 已打开的 iframe 可能早于异步 profile 刷新；通知同源页面重新读取。
        window.dispatchEvent(new CustomEvent('ai00-auth-user-updated', {
          detail: window._authUser,
        }));
      }
    } catch (_) {}
  }

  function subscribe(fn) {
    _subscribers.push(fn);
  }

  return {
    init,
    subscribe,
    publish: _publish,
    mergeUserProfile: _mergeUserProfile,
    formatUserStatus: _formatUserStatus,
    renderUserStatus: _renderUserStatus,
  };
})();

window.AuthStateManager = AuthStateManager;
