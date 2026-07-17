/**
 * auth_state.js — 认证状态管理
 * 维护 window._authMode / _authUser / _authToken / _authOrgInfo
 * 保证现有 iframe 页面通过 window.parent._authMode 继续可用。
 *
 * 依赖：无（在所有其他模块前加载）
 */
const AuthStateManager = (() => {
  const _subscribers = [];

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
        window._authUser.grants   = data.grants   || [];
        window._authUser.org_role = data.org_role || window._authUser.org_role;
      }
    } catch (_) {}
  }

  function subscribe(fn) {
    _subscribers.push(fn);
  }

  return { init, subscribe, publish: _publish };
})();

window.AuthStateManager = AuthStateManager;


