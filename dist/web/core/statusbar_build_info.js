(function () {
  const buildInfoNode = document.getElementById('sb-build-info');
  const versionNode = document.getElementById('sb-program-version');
  const environmentNode = document.getElementById('sb-runtime-environment');
  if (!buildInfoNode || !versionNode || !environmentNode) return;

  const frontendVersion = document.querySelector('meta[name="app-version"]')?.content?.trim() || '';
  let backendVersion = '';
  let programVersion = '';
  let activeBackendUrl = '';
  const databaseNode = document.getElementById('data-environment-badge');
  const databaseLabels = { test_: '测试数据库', pp_: '预生产数据库', '': '生产数据库' };
  async function refreshDatabase() {
    if (!databaseNode) return;
    try {
      let state;
      if (window.electronAPI?.getDataEnvironment) {
        state = await window.electronAPI.getDataEnvironment();
      } else if (window.electronAPI && window.AI00Business?.invoke) {
        state = await window.AI00Business.invoke('base.runtime.data_environment.active.get', { version: 1, payload: {} });
      } else {
        const response = await fetch(`${activeBackendUrl.replace(/\/$/, '')}/api/runtime/data-environment`, { cache: 'no-store' });
        if (!response.ok) throw Error('environment_read_failed');
        state = await response.json();
      }
      if (typeof state.prefix !== 'string' || !Object.hasOwn(databaseLabels, state.prefix)) throw Error('invalid_environment');
      databaseNode.textContent = databaseLabels[state.prefix];
      databaseNode.dataset.prefix = state.prefix;
      databaseNode.title = `当前后端实际表前缀：${state.prefix || '无前缀'}`;
    } catch (_) {
      databaseNode.textContent = '数据库状态未知';
      delete databaseNode.dataset.prefix;
      databaseNode.title = '无法读取当前后端数据库环境';
    }
  }
  const versionPattern = /^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/;
  const productionBackend = 'https://workmanship-backend.chehejia.com';
  versionNode.textContent = '整体版本未标记';

  function updateTooltip() {
    buildInfoNode.title = [
      `整体版本：${programVersion ? `v${programVersion}` : '未标记'}`,
      `前端版本：${versionPattern.test(frontendVersion) ? `v${frontendVersion}` : '未知'}`,
      `后端版本：${backendVersion ? `v${backendVersion}` : '未标记'}`,
      `运行环境：${environmentNode.textContent}`,
      `后端地址：${activeBackendUrl || (window.AI00RuntimeConfig?.isViteDevServerLocation?.()
        ? '本机开发代理（由 Vite 配置目标）' : '未取得')}`,
    ].join('\n');
  }
  updateTooltip();

  async function environmentFor(backendUrl) {
    if (!backendUrl) {
      return window.AI00RuntimeConfig?.isViteDevServerLocation?.()
        ? '本机' : '后端地址未配置';
    }
    let url;
    try {
      url = new URL(backendUrl);
    } catch {
      return '后端地址无效';
    }
    const host = url.hostname.toLowerCase();
    if (host === 'localhost' || host === '127.0.0.1') return '本机';
    if (url.href.replace(/\/$/, '') === productionBackend) return '生产环境';
    return host;
  }

  Promise.resolve().then(async () => {
    if (window.electronAPI && typeof window.electronAPI.getConfig !== 'function') {
      environmentNode.textContent = '桌面配置未加载';
      updateTooltip();
      return;
    }
    const config = await window.electronAPI?.getConfig?.();
    const backendUrl = await window.AI00RuntimeConfig?.getRuntimeBackendBase?.(config?.backendUrl || '')
      ?? config?.backendUrl;
    activeBackendUrl = String(backendUrl || '');
    environmentNode.textContent = await environmentFor(backendUrl);
    updateTooltip();
    const versionRequest = fetch(`${String(backendUrl || '').replace(/\/$/, '')}/api/system/version`, { cache: 'no-store' });
    void refreshDatabase();
    setInterval(refreshDatabase, 15000);
    const response = await versionRequest;
    if (!response.ok) return;
    const release = await response.json();
    backendVersion = versionPattern.test(release?.backendVersion) ? release.backendVersion : '';
    const clientType = window.electronAPI ? config?.clientType : 'browser';
    if (backendVersion && versionPattern.test(frontendVersion) && ['browser', 'desktop'].includes(clientType)
        && release.frontendVersions?.[clientType] === frontendVersion
        && versionPattern.test(release.programVersion)) {
      programVersion = release.programVersion;
    }
    versionNode.textContent = programVersion ? `整体 v${programVersion}` : '整体版本未标记';
    updateTooltip();
  }).catch(() => {
    if (environmentNode.textContent === '环境识别中') environmentNode.textContent = '后端地址未配置';
    updateTooltip();
  });
})();
