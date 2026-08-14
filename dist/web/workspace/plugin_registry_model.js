(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.PluginRegistryModel = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';

  function appItems(registry) {
    const seen = new Set();
    const result = [];
    for (const source of registry?.navItems || []) {
      const id = String(source?.id || '').trim();
      const title = String(source?.title || '').trim();
      if (!id || !title || seen.has(id)) continue;
      seen.add(id);
      result.push({
        id,
        title,
        icon: String(source.icon || 'icon-plugin'),
        requiresAuth: source.requiresAuth !== false,
        minPerm: source.minPerm || null,
        grantCheck: source.grantCheck || null,
        _pluginId: source._pluginId || null,
      });
    }
    return result;
  }

  return { appItems };
});
