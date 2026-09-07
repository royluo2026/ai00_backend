/**
 * web/core/web_compat.js
 * 浏览器环境下的 electronAPI polyfill。
 * 在 Electron 已注入 window.electronAPI 时完全跳过，保持桌面版行为不变。
 * 在纯浏览器访问时设置 window.electronAPI，让现有的 electronAPI?.method() 调用
 * 透明接管，无需修改各业务模块。
 */
(function () {
  if (window.electronAPI) return;   // Electron 环境已注入，直接退出

  const DEFAULT_LOCAL_BACKEND = 'http://127.0.0.1:8080';
  const _BACKEND_ENV_CONFIG_URL = '/web/runtime-env.json';
  let _backendEnvMapPromise = null;

  function _normalizeBaseUrl(value, fallback = '') {
    const raw = String(value || '').trim();
    return (raw || fallback || '').replace(/\/$/, '');
  }

  async function _loadBackendEnvMapAsync() {
    const fallback = {
      local: DEFAULT_LOCAL_BACKEND,
      test: '',
      staging: '',
      prod: '',
    };
    if (_backendEnvMapPromise) return _backendEnvMapPromise;

    _backendEnvMapPromise = (async () => {
      let fileMap = {};

      try {
        const res = await fetch(_BACKEND_ENV_CONFIG_URL, { cache: 'no-store' });
        if (res.ok) {
          const json = await res.json();
          if (json?.backendByEnv && typeof json.backendByEnv === 'object') {
            fileMap = json.backendByEnv;
          }
        }
      } catch {}

      const injectedMap =
        window.__AI00_BACKEND_BY_ENV && typeof window.__AI00_BACKEND_BY_ENV === 'object'
          ? window.__AI00_BACKEND_BY_ENV
          : {};

      let localMap = {};
      try {
        const raw = localStorage.getItem('ai00_backend_by_env') || '';
        if (raw) {
          const parsed = JSON.parse(raw);
          if (parsed && typeof parsed === 'object') localMap = parsed;
        }
      } catch {}

      return { ...fallback, ...fileMap, ...injectedMap, ...localMap };
    })();

    return _backendEnvMapPromise;
  }

  function _detectRuntimeEnvByHost(host) {
    const h = String(host || '').toLowerCase();
    if (h === 'localhost' || h === '127.0.0.1') return 'local';
    const m = h.match(/^[a-z0-9-]+-web(?:-([a-z0-9-]+))?\.chehejia\.com$/);
    if (!m) return 'unknown';
    return m[1] || 'prod';
  }

  function _isViteDevServerLocation(locationObj = window.location) {
    const host = String(locationObj?.hostname || '').toLowerCase();
    const port = String(locationObj?.port || '');
    return (host === '127.0.0.1' || host === 'localhost') && port === '5173';
  }

  async function _inferBackendFromFrontendOrigin(origin = window.location.origin) {
    let u;
    try {
      u = new URL(origin);
    } catch {
      return DEFAULT_LOCAL_BACKEND;
    }

    const host = (u.hostname || '').toLowerCase();
    const env = _detectRuntimeEnvByHost(host);

    if (env === 'local') {
      if (_isViteDevServerLocation(u)) {
        return '';
      }
      if (u.port && !['80', '443', '8080'].includes(u.port)) {
        return `${u.protocol}//${u.host}`;
      }
      return DEFAULT_LOCAL_BACKEND;
    }

    const envMap = await _loadBackendEnvMapAsync();
    const mappedByEnv = _normalizeBaseUrl(envMap[env]);
    if (mappedByEnv) return mappedByEnv;

    if (host.endsWith('.chehejia.com') && host.includes('-web')) {
      return `${u.protocol}//${host.replace('-web', '-backend')}`;
    }

    return `${u.protocol}//${u.host}`;
  }

  function _getStoredBackendBase() {
    return _normalizeBaseUrl(localStorage.getItem('ai00_backend_url') || '')
  }

  async function _getRuntimeBackendBase(configBackendUrl = '') {
    const explicit = _normalizeBaseUrl(configBackendUrl)
    if (explicit) return explicit

    const inferred = await _inferBackendFromFrontendOrigin(window.location.origin)
    if (inferred === '') return ''

    const stored = _getStoredBackendBase()
    if (stored) return stored

    return _normalizeBaseUrl(inferred, DEFAULT_LOCAL_BACKEND)
  }

  async function _resolveBackendBase(configBackendUrl = '') {
    return _getRuntimeBackendBase(configBackendUrl)
  }

  function _storeBackendBase(base) {
    const normalized = _normalizeBaseUrl(base, DEFAULT_LOCAL_BACKEND);
    window._AI00_BASE = normalized;
    if (normalized) localStorage.setItem('ai00_backend_url', normalized);
    else localStorage.removeItem('ai00_backend_url');
    return normalized;
  }

  function _toAbsoluteBackendUrl(url) {
    if (!(typeof url === 'string' && url.startsWith('/'))) return url
    const base = _getStoredBackendBase() || window._AI00_BASE || ''
    return `${base}${url}`
  }

  window.AI00RuntimeConfig = {
    defaultLocalBackend: DEFAULT_LOCAL_BACKEND,
    loadBackendEnvMapAsync: _loadBackendEnvMapAsync,
    detectRuntimeEnvByHost: _detectRuntimeEnvByHost,
    inferBackendFromFrontendOrigin: _inferBackendFromFrontendOrigin,
    isViteDevServerLocation: _isViteDevServerLocation,
    getStoredBackendBase: _getStoredBackendBase,
    getRuntimeBackendBase: _getRuntimeBackendBase,
    resolveBackendBase: _resolveBackendBase,
    storeBackendBase: _storeBackendBase,
    toAbsoluteBackendUrl: _toAbsoluteBackendUrl,
  };

  async function _backendUrl(path) {
    const base = await _getRuntimeBackendBase('');
    const p = String(path || '').startsWith('/') ? path : `/${path}`;
    return `${base}${p}`;
  }

  async function _cf(method, path, opts = {}) {
    return fetch(await _backendUrl(path), { ...opts, method });
  }

  // ── 飞书 OAuth Web 流程（开新标签 + 轮询 JWT）───────────────────────────
  async function _webFeishuLogin() {
    let r;
    try {
      const loginUrl = await _backendUrl('/auth/feishu/login-url');
      r = await fetch(loginUrl).then(res => res.json());
    } catch (e) {
      console.error('[web_compat] 获取登录 URL 失败', e);
      return { success: false };
    }

    const popup = window.open(r?.login_url, '_blank', 'width=640,height=720');
    if (!r?.login_url) {
      console.error('[web_compat] 获取登录 URL 失败，服务器返回:', r);
      return { success: false, error: '获取登录地址失败，请检查服务器配置' };
    }
    if (!popup) {
      // 弹窗被浏览器拦截时，给用户一个可点击的链接
      const a = document.createElement('a');
      a.href = r.login_url;
      a.target = '_blank';
      a.textContent = '点击此处打开飞书授权页';
      a.style.cssText = 'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);' +
        'z-index:99999;padding:16px 24px;background:#1e66f5;color:#fff;border-radius:8px;' +
        'font-size:15px;text-decoration:none;box-shadow:0 4px 20px rgba(0,0,0,.3)';
      document.body.appendChild(a);
      setTimeout(() => a.remove(), 60000);
    }

    // 轮询后端（2 秒/次，最多 5 分钟）
    for (let i = 0; i < 150; i++) {
      await new Promise(res => setTimeout(res, 2000));
      let p;
      try {
        const pollUrl = await _backendUrl(`/auth/feishu/poll/${r.state}`);
        p = await fetch(pollUrl).then(res => res.json());
      } catch (_) { continue; }

      if (p.status === 'ok' && p.token) {
        localStorage.setItem('ai00_token', p.token);
        localStorage.setItem('ai00_user', JSON.stringify(p.user || null));
        popup?.close();
        window.dispatchEvent(new CustomEvent('ai00:auth-changed', {
          detail: { mode: 'feishu', token: p.token, user: p.user },
        }));
        return { success: true, token: p.token, user: p.user };
      }
      if (p.status === 'error' || p.status === 'expired') break;
    }
    popup?.close();
    return { success: false };
  }

  // ── polyfill 主体 ───────────────────────────────────────────────────────
  window.electronAPI = {
    _isElectron: false,

    // ── 认证 ──────────────────────────────────────────────────────────────
    authGetState() {
      const token = localStorage.getItem('ai00_token') || '';
      let user = null;
      try { user = JSON.parse(localStorage.getItem('ai00_user') || 'null'); } catch (_) {}
      return Promise.resolve({
        mode:  token ? 'feishu' : 'none',
        token,
        user,
      });
    },

    authFeishuLogin: () => _webFeishuLogin(),

    async authLogout() {
      const token = localStorage.getItem('ai00_token') || '';
      const logoutUrl = await _backendUrl('/auth/logout');
      await fetch(logoutUrl, {
        method:  'POST',
        headers: { 'X-AI00-Token': token },
      }).catch(() => {});
      localStorage.removeItem('ai00_token');
      localStorage.removeItem('ai00_user');
      window.dispatchEvent(new CustomEvent('ai00:auth-changed', {
        detail: { mode: 'none', token: '', user: null },
      }));
    },

    onAuthStateChanged(cb) {
      window.addEventListener('ai00:auth-changed', e => cb(e.detail));
    },

    // ── 配置 ──────────────────────────────────────────────────────────────
    async getConfig() {
      const ver = document.querySelector('meta[name=app-version]')?.content || '';
      return Promise.resolve({
        backendUrl: await _getRuntimeBackendBase(''),
        version:    ver,
      });
    },

    // ── 外部链接 ───────────────────────────────────────────────────────────
    openExternal(url)      { window.open(url, '_blank', 'noopener,noreferrer'); },
    openFeishuLink(url)    { window.open(url, '_blank', 'noopener,noreferrer'); },
    shellOpenExternal(url) { window.open(url, '_blank', 'noopener,noreferrer'); },

    // ── 主题广播 ───────────────────────────────────────────────────────────
    onThemeChanged(cb) {
      window.addEventListener('ai00:theme-changed', e => cb(e.detail));
    },
    broadcastTheme(theme) {
      localStorage.setItem('system.theme', theme);
      window.dispatchEvent(new CustomEvent('ai00:theme-changed', { detail: theme }));
    },

    // ── 插件管理（走后端 API）─────────────────────────────────────────────
    listInstalledPlugins() {
      const token = localStorage.getItem('ai00_token') || '';
      return (window.top?.AI00ExistingCapabilityClient || window.AI00ExistingCapabilityClient)
        .call('base.plugins.list').then(r => r.installations || []).catch(() => []);
    },
    // Browser installs are signed marketplace identities only; URLs never reach an adapter.
    installPluginRelease(release) {
      const client = window.top?.AI00ExistingCapabilityClient || window.AI00ExistingCapabilityClient;
      if (!release || typeof release !== 'object' || !client) {
        return Promise.resolve({ ok: false, error: '需要已签名的市场发布信息' });
      }
      return client.call('base.plugins.install', {
        pluginId: release.plugin_id,
        releaseVersion: release.release_version || release.version,
        releaseSha256: release.release_sha256 || release.sha256,
        requestedGrants: release.requested_grants || release.grants,
      }, { confirm: () => window.confirm(`确认安装已签名插件「${release.plugin_id}」？`) })
        .then(data => ({ ok: true, ...data }))
        .catch(error => ({ ok: false, error: error?.message || String(error) }));
    },
    installPluginFromUrl() {
      return Promise.resolve({ ok: false, error: '浏览器版只接受已签名的市场发布，不支持 URL 安装' });
    },
    uninstallUserPlugin(installation) {
      const client = window.top?.AI00ExistingCapabilityClient || window.AI00ExistingCapabilityClient;
      if (!installation || typeof installation !== 'object' || !Number.isInteger(installation.revision) || !client) {
        return Promise.resolve({ ok: false, error: '卸载需要当前安装 revision' });
      }
      return client.call('base.plugins.uninstall', {
        pluginId: installation.plugin_id,
        expectedRevision: installation.revision,
      }, { confirm: () => window.confirm(`确认卸载插件「${installation.plugin_id}」？其租户数据将被保留。`) })
        .then(data => ({ ok: true, ...data }))
        .catch(error => ({ ok: false, error: error?.message || String(error) }));
    },
    onPluginRegistryUpdated() {},   // 静默：网页版靠轮询

    // ── 插件注册表（从后端 /admin/plugin-registry 获取）──────────────────
    getPluginRegistry() {
      return _backendUrl('/admin/plugin-registry').then(url => fetch(url))
        .then(r => r.ok ? r.json() : null)
        .catch(() => null);
    },

    // ── 自动更新（网页版无需，静默）───────────────────────────────────────
    onUpdateAvailable(_cb)  {},
    onUpdateProgress(_cb)   {},
    onUpdateDownloaded(_cb) {},
    installUpdate()          {},
    checkForUpdate()         { return Promise.resolve(null); },
    getAppVersion()          {
      return Promise.resolve(
        document.querySelector('meta[name=app-version]')?.content || ''
      );
    },

    // ── 窗口控制（浏览器无对应能力，静默）───────────────────────────────
    minimize()          {},
    maximize()          {},
    close()             {},
    showFloatBall()     {},
    hideSidebar()       {},
    openSettings()      {},
    openDebugLog()      {},

    // ── 日志（浏览器无主进程日志）─────────────────────────────────────────
    getMainLog()        { return Promise.resolve(null); },

    // ── 文件操作（浏览器版静默降级；附件由专用上传组件处理）
    openFileDialog(_filters, _opts) { return Promise.resolve(null); },
    showOpenDialog(_opts)           { return Promise.resolve(null); },
    readTextFile(_path)             { return Promise.resolve(null); },
    writeTextFile(_path, _content)  { return Promise.resolve({ success: false }); },
    readFileBase64(_path)           { return Promise.resolve(null); },
    saveScreenshot(_url, _id)       { return Promise.resolve({ success: false }); },
    copyToAttachments(_opts)        { return Promise.resolve(null); },

    // ── AI / 工作流窗口（静默）───────────────────────────────────────────
    openAiChatWindow()      {},
    openWfcWindow()         {},
    wfcOpenWithData(_data)  {},

    // ── 应用卸载（网页版无意义）──────────────────────────────────────────
    uninstallApp() {},
  };

  // 首次加载：验证 token，决定是否显示主页或跳转登录页
  const _tok = localStorage.getItem('ai00_token');
  const _onLoginPage = window.location.pathname.includes('/login');

  if (_onLoginPage) {
    // 登录页本身不做 token 检查，直接显示
  } else if (_tok) {
    // 有 token：先向服务器验证是否有效
    _backendUrl('/auth/me').then(url => fetch(url, { headers: { 'X-AI00-Token': _tok } }))
      .then(r => {
        if (r.ok) {
          return r.json().then(userData => {
            // 把服务器返回的用户信息存入 localStorage，供 authGetState 使用
            if (userData && userData.gid) {
              localStorage.setItem('ai00_user', JSON.stringify(userData));
            }
            document.getElementById('_auth_gate')?.remove();
            window.dispatchEvent(new CustomEvent('ai00:auth-changed', {
              detail: { mode: 'feishu', token: _tok, user: userData || null },
            }));
          });
        } else if (r.status === 401) {
          // 只有 401 才说明 token 真的失效，清除并跳登录
          localStorage.removeItem('ai00_token');
          localStorage.removeItem('ai00_user');
          window.location.href = '/web/login/index.html';
        } else {
          // 500 等服务器错误：token 可能仍有效，不删除，直接显示页面
          document.getElementById('_auth_gate')?.remove();
          let _u = null;
          try { _u = JSON.parse(localStorage.getItem('ai00_user') || 'null'); } catch (_) {}
          window.dispatchEvent(new CustomEvent('ai00:auth-changed', {
            detail: { mode: 'feishu', token: _tok, user: _u },
          }));
        }
      })
      .catch(() => {
        // 网络错误：服务器不可达时仍解除隐藏（离线容错）
        document.getElementById('_auth_gate')?.remove();
        let _u = null;
        try { _u = JSON.parse(localStorage.getItem('ai00_user') || 'null'); } catch (_) {}
        window.dispatchEvent(new CustomEvent('ai00:auth-changed', {
          detail: { mode: 'feishu', token: _tok, user: _u },
        }));
      });
  } else {
    // 没有 token：仅顶层页面跳登录；iframe 子页面不重定向
    if (window.top === window) {
      window.location.href = '/web/login/index.html';
    }
  }
})();
