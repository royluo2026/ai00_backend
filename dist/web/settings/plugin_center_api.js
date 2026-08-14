(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.AI00PluginCenterApi = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';

  function errorText(result, fallback = '操作失败') {
    const detail = result?.detail || result?.error || result?.msg;
    if (typeof detail === 'string') return detail;
    return detail?.message || detail?.code || fallback;
  }

  function dataOf(result) {
    if (!result || result.success === false) throw new Error(errorText(result));
    if (result.success === true && Object.prototype.hasOwnProperty.call(result, 'data')) return result.data;
    return result;
  }

  function createPluginCenterApi({ backendFetch }) {
    if (typeof backendFetch !== 'function') throw new TypeError('backendFetch is required');
    const request = async (path, options) => dataOf(await backendFetch(path, options));

    return {
      async access() {
        const profile = await request('/auth/me');
        const value = profile?.data && !profile.permissions ? profile.data : profile;
        const permissions = Array.isArray(value?.permissions) ? value.permissions : [];
        return { profile: value || {}, canManage: permissions.includes('system.plugin.manage') };
      },
      async loadAll(month) {
        const [catalog, installed, usage] = await Promise.all([
          request('/api/v1/plugin-marketplace/catalog'),
          request('/api/v1/plugin-marketplace/installations'),
          request(`/api/v1/plugin-marketplace/usage/months/${encodeURIComponent(month)}`),
        ]);
        return { catalog: catalog || [], installed: installed || [], metrics: usage?.items || [] };
      },
      events(pluginId) {
        return request(`/api/v1/plugin-marketplace/installations/${encodeURIComponent(pluginId)}/events?limit=100`);
      },
      releases(status = 'submitted') {
        return request(`/api/v1/plugin-marketplace/releases?status=${encodeURIComponent(status)}`);
      },
      review(pluginId, version, approved, note) {
        return request(`/api/v1/plugin-marketplace/releases/${encodeURIComponent(pluginId)}/${encodeURIComponent(version)}/review`, {
          method: 'POST', body: JSON.stringify({ approved, note }),
        });
      },
      closeMonth(month) {
        return request(`/api/v1/plugin-marketplace/usage/months/${encodeURIComponent(month)}/close`, { method: 'POST', body: '{}' });
      },
      finishUpgrade(pluginId, healthy) {
        return request(`/api/v1/plugin-marketplace/installations/${encodeURIComponent(pluginId)}/upgrade-health`, {
          method: 'POST', body: JSON.stringify({ healthy: Boolean(healthy) }),
        });
      },
      async invokeLifecycle(capabilityId, payload) {
        const headers = { 'X-AI00-Source': 'web' };
        const confirmed = await request(`/api/v1/capabilities/${encodeURIComponent(capabilityId)}:confirm`, {
          method: 'POST', headers, body: JSON.stringify({ payload }),
        });
        return request(`/api/v1/capabilities/${encodeURIComponent(capabilityId)}:invoke`, {
          method: 'POST', headers,
          body: JSON.stringify({ payload, confirmation_token: confirmed?.confirmation_token }),
        });
      },
    };
  }

  return { createPluginCenterApi, errorText };
});
