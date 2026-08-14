(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.AI00PluginCenterModel = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';

  function actionsForInstallation(item, canManage) {
    if (!canManage || !item) return [];
    const actions = [];
    if (['disabled', 'failed', 'rolled_back'].includes(item.state)) actions.push('enable');
    if (['enabled', 'rolled_back'].includes(item.state)) actions.push('disable');
    if (['disabled', 'revoked'].includes(item.state)) actions.push('uninstall');
    if (item.state === 'upgrading') actions.push('upgrade.finish');
    if (['upgrading', 'failed'].includes(item.state) && item.previous_version) actions.push('rollback');
    return actions;
  }

  function reduceLoad(previous, result) {
    const current = previous || { catalog: [], installed: [], metrics: [], error: null, loading: false };
    if (!result || !result.ok) {
      return { ...current, loading: false, error: result?.error || '加载失败' };
    }
    return {
      ...current,
      catalog: Array.isArray(result.catalog) ? result.catalog : [],
      installed: Array.isArray(result.installed) ? result.installed : [],
      metrics: Array.isArray(result.metrics) ? result.metrics : [],
      error: null,
      loading: false,
    };
  }

  function filterPlugins(items, filters) {
    const query = String(filters?.query || '').trim().toLowerCase();
    const state = String(filters?.state || '').trim();
    return (items || []).filter(item => {
      const haystack = `${item.name || ''} ${item.plugin_id || ''} ${item.description || ''}`.toLowerCase();
      return (!query || haystack.includes(query)) && (!state || item.state === state);
    });
  }

  function latestCatalog(items) {
    const byPlugin = new Map();
    for (const item of items || []) if (!byPlugin.has(item.plugin_id)) byPlugin.set(item.plugin_id, item);
    return [...byPlugin.values()];
  }

  return { actionsForInstallation, reduceLoad, filterPlugins, latestCatalog };
});
