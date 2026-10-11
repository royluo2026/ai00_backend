(function (root, factory) {
  const value = factory();
  if (typeof module === 'object' && module.exports) module.exports = value;
  if (root) root.AI00Marketplace = value;
})(typeof window === 'undefined' ? globalThis : window, function () {
  'use strict';
  const labels = { available: '未安装', disabled: '已停用', enabled: '已启用', upgrading: '更新中', failed: '更新失败', rolled_back: '已回滚', revoked: '已撤销' };
  const actionLabels = { open: '打开插件', install: '安装', enable: '启用', disable: '停用', upgrade: '更新至此版本', finish: '确认更新可用', rollback: '回滚', uninstall: '卸载' };

  function actions(item, canManage, view = 'installed') {
    const result = view === 'installed' && ['enabled', 'rolled_back'].includes(item.state) ? ['open'] : [];
    if (!canManage) return result;
    if (view === 'catalog') {
      if (!item.release_sha256) return [];
      if (item.state === 'available') return ['install'];
      return ['disabled', 'enabled', 'rolled_back'].includes(item.state) && item.version !== item.current_version ? ['upgrade'] : [];
    }
    if (['disabled', 'rolled_back'].includes(item.state)) result.push('enable');
    if (['enabled', 'rolled_back', 'failed'].includes(item.state)) result.push('disable');
    if (item.state === 'upgrading') result.push('finish');
    if (['upgrading', 'failed'].includes(item.state) && item.previous_version) result.push('rollback');
    if (['disabled', 'enabled', 'failed', 'rolled_back', 'revoked'].includes(item.state) && Number.isInteger(item.revision) && item.revision > 0) result.push('uninstall');
    return result;
  }

  function createClient(capabilities) {
    return {
      adminAccess() {
        return capabilities.invoke('base.plugin.marketplace.administration.access.get', {}, { version: 1 });
      },
      releases(status, query, offset = 0) {
        return capabilities.invoke('base.plugin.marketplace.release.search', { ...(status ? { status } : {}), query, offset, limit: 50 }, { version: 1 });
      },
      administer(action, payload) {
        const target = { review: ['release.review', 1], revoke: ['release.revoke', 1], publisher: ['publisher.register', 2], submit: ['release.submit', 1] }[action];
        if (!target) throw new Error('不支持的管理操作');
        return capabilities.invoke(`base.plugin.marketplace.${target[0]}`, payload, { version: target[1], write: true, confirmed: true });
      },
      async access() {
        const profile = await capabilities.call('base.identity.session.profile.get');
        return (profile.permission_ids || []).includes('system.plugin.manage');
      },
      search(view, query, offset) {
        return capabilities.invoke('base.plugin.marketplace.search', { view, query, offset, limit: 50 }, { version: 2 });
      },
      async run(action, item) {
        // Called only after the page's explicit confirmation. The shared client
        // owns the token exchange, major pin and stable idempotency key.
        if (action === 'install') return capabilities.call('base.plugins.install', {
          pluginId: item.plugin_id, releaseVersion: item.version,
          releaseSha256: item.release_sha256, requestedGrants: item.requested_grants,
        }, { confirm: () => true });
        if (action === 'uninstall') {
          if (!Number.isInteger(item.revision) || item.revision < 1) throw new Error('缺少安装版本，请刷新后再操作');
          return capabilities.call('base.plugins.uninstall', {
            pluginId: item.plugin_id, expectedRevision: item.revision,
          }, { confirm: () => true });
        }
        if (!['enable', 'disable', 'upgrade', 'finish', 'rollback'].includes(action)) throw new Error('不支持的插件操作');
        const payload = { plugin_id: item.plugin_id };
        if (action === 'upgrade') Object.assign(payload, { version: item.version, granted_capabilities: item.requested_grants });
        return capabilities.invoke(`plugin.${action === 'finish' ? 'enable' : action}`, payload, { version: 1, write: true, confirmed: true });
      },
    };
  }
  return { labels, actionLabels, actions, createClient };
});
