(function (root, factory) {
  const exports = factory();
  if (typeof module === 'object' && module.exports) module.exports = exports;
  if (root) root.OrchestrationBootstrap = exports;
  if (typeof module !== 'object' && root?.document) {
    root.addEventListener('DOMContentLoaded', async () => {
      const mount = root.document.getElementById('orchestrationApp');
      const source = new URLSearchParams(root.location.search).get('source');
      if (!mount) return;
      try {
        if (source === 'governed') await exports.waitForGovernedScope(root);
        await exports.bootstrapOrchestrationCenter(mount, {
          source,
          app: root.OrchestrationCenterApp,
          loadGovernedState: root.loadGovernedOrchestrationState,
        });
      } catch (error) {
        mount.textContent = error.message;
        mount.dataset.bootstrapError = 'true';
      }
    });
  }
})(typeof window !== 'undefined' ? window : globalThis, function () {
  async function bootstrapOrchestrationCenter(container, options = {}) {
    const { source, app, loadGovernedState } = options;
    if (!app?.mountApp) throw new Error('orchestration application is unavailable');
    if (source === 'demo') {
      if (globalThis.__AI00_PRODUCTION_BUILD__ === true) {
        throw new Error('生产构建不允许演示数据入口');
      }
      const localHost = /^(localhost|127\.0\.0\.1)$/.test(String(globalThis.location?.hostname || ''));
      if (!localHost || globalThis.__AI00_DEMO_MODE__ !== true) {
        throw new Error('演示数据仅可在显式本地开发模式启用');
      }
      return app.mountApp(container, app.createDemoState(), { demo: true });
    }
    if (source === 'governed' && typeof loadGovernedState === 'function') {
      return app.mountApp(container, await loadGovernedState(), { demo: false, readOnly: true });
    }
    if (source === 'governed') throw new Error('governed orchestration read is unavailable');
    throw new Error('orchestration source must be explicit');
  }

  function waitForGovernedScope(root) {
    if (root.__AI00_ORCHESTRATION_SCOPE__ || root.parent?.__AI00_ORCHESTRATION_SCOPE__) return Promise.resolve();
    return new Promise((resolve, reject) => {
      const timer = root.setTimeout(() => {
        root.removeEventListener('message', onMessage);
        reject(new Error('编排中心未收到受治理的项目作用域'));
      }, 10000);
      function onMessage(event) {
        if (event.origin && root.location?.origin && event.origin !== root.location.origin) return;
        if (event.source && event.source !== root.parent) return;
        if (event.data?.type !== 'orchestration-scope' || !event.data.scope) return;
        root.__AI00_ORCHESTRATION_SCOPE__ = event.data.scope;
        root.clearTimeout(timer);
        root.removeEventListener('message', onMessage);
        resolve();
      }
      root.addEventListener('message', onMessage);
    });
  }

  return { bootstrapOrchestrationCenter, waitForGovernedScope };
});
