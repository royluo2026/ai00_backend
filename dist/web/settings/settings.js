/**
 * 系统设置页脚本 — Electron 模式
 *
 * 注意：settings 页作为独立窗口由 electronAPI.openSettings() 打开。
 *       所有后端数据通过 _backendFetch（REST API）或 electronAPI IPC 获取。
 */

// localStorage 账号隔离（settings 窗口无父框架，user GID 在 _start() 中异步初始化）
let _sUserGid = '';
function _lsk(base) { return _sUserGid ? `${_sUserGid}:${base}` : base; }

// ===================== 主题（独立于 main.js，本页自己管）=====================
const ThemeSync = {
  apply(theme) {
    if (!theme) return;
    document.documentElement.setAttribute('data-theme', theme);
    // 高亮当前主题按钮
    document.querySelectorAll('.theme-option').forEach(el =>
      el.classList.toggle('active', el.dataset.themeVal === theme));
  }
};

// ===================== 左侧导航切换 =====================
function _initNav() {
  document.querySelectorAll('.nav-item[data-panel]').forEach(item => {
    item.addEventListener('click', () => {
      // 切换 nav 高亮
      document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
      item.classList.add('active');
      // 切换面板
      document.querySelectorAll('.settings-panel').forEach(p => p.classList.remove('active'));
      const panel = document.getElementById(`panel-${item.dataset.panel}`);
      if (panel) panel.classList.add('active');
    });
  });
}

// ===================== 安全 API 调用包装（Electron 模式无 pywebview，始终返回 null）=====================
async function _apiCall(_method, ..._args) {
  // 本地 bridge 已移除，此函数保留为占位，调用处逐步迁移到 _backendFetch / electronAPI
  return null;
}

// ===================== 外观/主题面板 =====================
function _initAppearance(config) {
  const theme = config?.theme || localStorage.getItem('system.theme') || 'light';
  ThemeSync.apply(theme);

  document.querySelectorAll('.theme-option').forEach(btn => {
    btn.addEventListener('click', async () => {
      const val = btn.dataset.themeVal;
      ThemeSync.apply(val);
      // 持久化到 localStorage
      localStorage.setItem('system.theme', val);
      // 广播给所有窗口（含主窗口）
      window.electronAPI?.broadcastTheme?.(val);
      // 兼容 iframe 场景
      try { window.parent?.postMessage({ type: 'theme', theme: val }, '*'); } catch(_) {}
    });
  });
}

// ===================== 通用设置面板 =====================
function _initGeneral(config) {
  const sys = config?.system || {};

  _setVal('cfg-language',    sys.language   || 'zh_CN');
  _setVal('cfg-log-level',   sys.log_level  || 'INFO');
  _setChk('cfg-window-max',  !!sys.window_max);
  _setChk('cfg-auto-backup', !!sys.auto_backup);

  // 实时保存
  const bindings = [
    ['cfg-language',    'system.language',   'value'],
    ['cfg-log-level',   'system.log_level',  'value'],
    ['cfg-window-max',  'system.window_max', 'checked'],
    ['cfg-auto-backup', 'system.auto_backup','checked'],
  ];
  bindings.forEach(([id, key, prop]) => {
    document.getElementById(id)?.addEventListener('change', async (e) => {
      const val = prop === 'checked' ? e.target.checked : e.target.value;
      localStorage.setItem(key, typeof val === 'boolean' ? String(val) : val);
    });
  });

  // 后端服务地址
  const backendInput = document.getElementById('cfg-backend-url');
  const backendFb    = document.getElementById('backend-url-feedback');
  // 读取当前配置
  window.electronAPI?.getConfig?.().then(cfg => {
    if (backendInput && cfg?.backendUrl) backendInput.value = cfg.backendUrl;
  });
  document.getElementById('btn-save-backend-url')?.addEventListener('click', async () => {
    const url = backendInput?.value?.trim();
    if (!url) { if (backendFb) backendFb.textContent = '地址不能为空'; return; }
    if (!url.startsWith('http')) { if (backendFb) backendFb.textContent = '地址须以 http:// 或 https:// 开头'; return; }
    // 写入 system.json（通过 IPC）
    const ok = await window.electronAPI?.saveSystemConfig?.({ backend_url: url });
    if (backendFb) backendFb.textContent = '已保存，3秒后重启…';
    setTimeout(() => window.electronAPI?.relaunch?.(), 3000);
  });
}

function _setVal(id, val) {
  const el = document.getElementById(id);
  if (el) el.value = val;
}
function _setChk(id, checked) {
  const el = document.getElementById(id);
  if (el) el.checked = checked;
}

// ===================== 数据库面板 =====================
function _initDatabase(config) {
  // 本地 SQLite 路径（来自 get_all_settings 初始包）
  const dbPath = config?.system?.local_db_path;
  const pathInput = document.getElementById('local-db-path-input');
  if (pathInput && dbPath) pathInput.value = dbPath;

  // 浏览按钮 —— 使用 Electron saveFileDialog 选择或新建 .db 文件
  document.getElementById('btn-browse-local-db')?.addEventListener('click', async () => {
    const api = window.electronAPI;
    if (!api?.saveFileDialog) return;
    const currentPath = pathInput?.value?.trim() || '';
    const result = await api.saveFileDialog({
      title: '选择或新建本地数据库文件',
      defaultPath: currentPath || undefined,
      filters: [{ name: 'SQLite 数据库', extensions: ['db'] }],
    });
    if (result && pathInput) {
      // 统一用正斜杠，避免 Windows 反斜杠在 SQLite URL 中出错
      pathInput.value = result.replace(/\\/g, '/');
    }
  });

  // 保存本地DB路径
  document.getElementById('btn-save-local-db')?.addEventListener('click', async () => {
    const btn  = document.getElementById('btn-save-local-db');
    const fb   = document.getElementById('local-db-feedback');
    const newPath = pathInput?.value?.trim();
    if (!newPath) { if (fb) { fb.textContent = '路径不能为空'; fb.style.color = 'var(--color-error)'; } return; }
    btn.disabled = true; btn.textContent = '保存中...';
    const r = await _apiCall('call_bridge', 'db', 'set_local_db_path', { path: newPath });
    btn.disabled = false; btn.textContent = '保存路径';
    if (fb) {
      fb.textContent = r?.msg || (r?.success ? '已保存' : '保存失败');
      fb.style.color = r?.success ? 'var(--color-success, #a6e3a1)' : 'var(--color-error, #f38ba8)';
      setTimeout(() => { if (fb) fb.textContent = ''; }, 4000);
    }
  });

  // 测试本地连接
  document.getElementById('btn-test-local-db')?.addEventListener('click', async () => {
    const btn = document.getElementById('btn-test-local-db');
    const res  = document.getElementById('local-db-result');
    btn.disabled = true; btn.textContent = '测试中...';
    const r = await _apiCall('call_bridge', 'db', 'test_connection', { db_type: 'local' });
    btn.disabled = false; btn.textContent = '测试连接';
    if (res) {
      res.textContent = r?.msg || (r?.success ? '连接成功' : '连接失败');
      res.className = 'db-test-result ' + (r?.success ? 'ok' : 'err');
    }
  });

  // 加载云端数据库配置字段（单独请求，不阻塞页面初始化）
  _loadCloudDbConfig();

  // 保存云端数据库配置
  document.getElementById('btn-save-pg')?.addEventListener('click', async () => {
    const password = document.getElementById('pg-password')?.value || '';
    const payload  = {
      host:      document.getElementById('pg-host')?.value?.trim()      || '',
      port:      parseInt(document.getElementById('pg-port')?.value)    || 2883,
      user:      document.getElementById('pg-user')?.value?.trim()      || '',
      password:  password,
      collab_db: document.getElementById('pg-collab-db')?.value?.trim() || '',
      public_db: document.getElementById('pg-public-db')?.value?.trim() || '',
    };
    console.log('[settings.cloud-db.save] payload', {
      ...payload,
      password: payload.password ? `len=${payload.password.length}` : '',
    });
    const r  = await _backendFetch('/admin/cloud-db-config', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    console.log('[settings.cloud-db.save] response', r);
    const fb = document.getElementById('pg-feedback');
    if (fb) {
      fb.textContent = r?.msg || r?.detail || JSON.stringify(r || {}) || (r?.success ? '已保存' : '保存失败');
      fb.style.color = r?.success ? 'var(--color-green, #a6e3a1)' : 'var(--color-red, #f38ba8)';
      setTimeout(() => { if (fb) fb.textContent = ''; }, 5000);
    }
  });

  // 测试云端数据库连接
  document.getElementById('btn-test-pg')?.addEventListener('click', async () => {
    const btn = document.getElementById('btn-test-pg');
    const res  = document.getElementById('pg-result');
    const password = document.getElementById('pg-password')?.value || '';
    const payload = {
      host:      document.getElementById('pg-host')?.value?.trim()      || '',
      port:      parseInt(document.getElementById('pg-port')?.value)    || 2883,
      user:      document.getElementById('pg-user')?.value?.trim()      || '',
      password:  password,
      collab_db: document.getElementById('pg-collab-db')?.value?.trim() || '',
      public_db: document.getElementById('pg-public-db')?.value?.trim() || '',
    };
    console.log('[settings.cloud-db.test] payload', {
      ...payload,
      password: payload.password ? `len=${payload.password.length}` : '',
    });
    btn.disabled = true; btn.textContent = '测试中...';
    const r = await _backendFetch('/admin/cloud-db-config/test', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    console.log('[settings.cloud-db.test] response', r);
    btn.disabled = false; btn.textContent = '测试连接';
    if (res) {
      res.textContent = r?.msg || r?.detail || JSON.stringify(r || {}) || (r?.success ? '连接成功' : '连接失败');
      res.className = 'db-test-result ' + (r?.success ? 'ok' : 'err');
    }
  });
}

async function _loadCloudDbConfig() {
  const r = await _backendFetch('/admin/cloud-db-config');
  if (!r?.success || !r?.data) return;
  const d = r.data;
  const _v = (id, val) => { const el = document.getElementById(id); if (el) el.value = val ?? ''; };
  _v('pg-host',      d.host || 'sam-bdmsdb01-test.chj.cloud');
  _v('pg-port',      d.port || 2883);
  _v('pg-user',      d.user || 'sht_mes_tool@mom#test_bdms01');
  _v('pg-password',  d.password_configured ? '●●●●' : '');
  _v('pg-collab-db', d.collab_db || 'sht_mes_tool');
  _v('pg-public-db', d.public_db || 'sht_mes_tool');
  if (d.local_db_path) {
    const el = document.getElementById('local-db-path-input');
    if (el && !el.value) el.value = d.local_db_path;
  }
}

// ===================== 文件存储面板 =====================
async function _initFileStore() {
  // 本地路径功能在云端模式下不适用，直接禁用相关按钮
  const btn1 = document.getElementById('btn-save-local-store');
  const btn2 = document.getElementById('btn-test-local-store');
  if (btn1) { btn1.disabled = true; btn1.title = '云端模式下不适用'; }
  if (btn2) { btn2.disabled = true; btn2.title = '云端模式下不适用'; }

  // ── 按钮监听器：同步注册，保证用户一进页面就能点 ──────────────────────────

  // 保存 MinIO 配置
  document.getElementById('btn-save-minio')?.addEventListener('click', async () => {
    const btn = document.getElementById('btn-save-minio');
    const fb  = document.getElementById('minio-feedback');
    btn.disabled = true; btn.textContent = '保存中...';
    const payload = {
      endpoint:   document.getElementById('minio-endpoint')?.value?.trim()       || '',
      access_key: document.getElementById('minio-access-key')?.value?.trim()     || '',
      secret_key: document.getElementById('minio-secret-key')?.value             || '',
      bucket:     document.getElementById('minio-public-bucket')?.value?.trim()  || 'ai00',
    };
    const res = await _backendFetch('/api/file-store/config', {
      method: 'POST',
      body:   JSON.stringify(payload),
    });
    btn.disabled = false; btn.textContent = '保存配置';
    if (fb) {
      fb.textContent = res?.msg || (res?.success ? '已保存' : '保存失败');
      fb.style.color = res?.success ? 'var(--color-success,#a6e3a1)' : 'var(--color-error,#f38ba8)';
      setTimeout(() => { if (fb) fb.textContent = ''; }, 4000);
    }
  });

  // 测试 MinIO 连接
  document.getElementById('btn-test-minio')?.addEventListener('click', async () => {
    const btn = document.getElementById('btn-test-minio');
    const res = document.getElementById('minio-result');
    btn.disabled = true; btn.textContent = '测试中...';
    const r = await _backendFetch('/api/file-store/test', { method: 'POST', body: '{}' });
    btn.disabled = false; btn.textContent = '测试连接';
    if (res) {
      res.textContent = r?.msg || (r?.success ? '连接成功 ✓' : '连接失败');
      res.className = 'db-test-result ' + (r?.success ? 'ok' : 'err');
    }
  });

  // 保存 OIS 配置
  document.getElementById('btn-save-ois')?.addEventListener('click', async () => {
    const btn = document.getElementById('btn-save-ois');
    const fb  = document.getElementById('ois-feedback');
    btn.disabled = true; btn.textContent = '保存中...';
    const payload = {
      ois3_url:            document.getElementById('ois-ois3-url')?.value?.trim()       || '',
      identify:            document.getElementById('ois-identify')?.value?.trim()       || '',
      env:                 document.getElementById('ois-env')?.value?.trim()            || '',
      region:              document.getElementById('ois-region')?.value?.trim()         || '',
      licloud_appid:       document.getElementById('ois-licloud-appid')?.value?.trim()  || '',
      idaas_url:           document.getElementById('ois-idaas-url')?.value?.trim()      || '',
      idaas_client_id:     document.getElementById('ois-client-id')?.value?.trim()      || '',
      idaas_client_secret: document.getElementById('ois-client-secret')?.value          || '',
      idaas_service_id:    document.getElementById('ois-service-id')?.value?.trim()     || '',
      public_base_url:     document.getElementById('ois-public-base-url')?.value?.trim() || '',
    };
    const res = await _backendFetch('/api/file-store/ois-config', {
      method: 'POST',
      body:   JSON.stringify(payload),
    });
    btn.disabled = false; btn.textContent = '保存 OIS 配置';
    if (fb) {
      fb.textContent = res?.msg || (res?.success ? '已保存' : '保存失败');
      fb.style.color = res?.success ? 'var(--color-success,#a6e3a1)' : 'var(--color-error,#f38ba8)';
      setTimeout(() => { if (fb) fb.textContent = ''; }, 4000);
    }
  });

  // 测试 OIS 连接
  document.getElementById('btn-test-ois')?.addEventListener('click', async () => {
    const btn = document.getElementById('btn-test-ois');
    const res = document.getElementById('ois-result');
    const fb  = document.getElementById('ois-feedback');
    btn.disabled = true; btn.textContent = '测试中...';
    if (fb) { fb.textContent = '测试中（最长12秒）...'; fb.style.color = 'var(--text-muted)'; }
    let r;
    try {
      const ctrl = new AbortController();
      const tid  = setTimeout(() => ctrl.abort(), 12000);
      r = await _backendFetch('/api/file-store/ois-test', { method: 'POST', body: '{}', signal: ctrl.signal });
      clearTimeout(tid);
    } catch (e) {
      r = { success: false, msg: e.name === 'AbortError' ? '请求超时（>12s），请检查网络' : (e.message || '请求异常') };
    }
    btn.disabled = false; btn.textContent = '测试连接';
    const msg = r?.msg || (r?.success ? '连接成功 ✓' : '连接失败');
    if (fb) {
      fb.textContent = msg;
      fb.style.color = r?.success ? 'var(--color-success,#a6e3a1)' : 'var(--color-error,#f38ba8)';
      setTimeout(() => { if (fb) { fb.textContent = ''; fb.style.color = ''; } }, 10000);
    }
    if (res) {
      const d = r?.debug;
      const debugLines = d ? [
        `[Step1 IdaaS] url: ${d.step1_idaas_url}`,
        `[Step1 IdaaS] result: ${d.step1_idaas_result}`,
        `[Step1 IdaaS] Bearer token sent: ${d.step1_bearer_sent}`,
        `[Step2 STS]   url: ${d.step2_sts_url}`,
        `[Step2 STS]   params: ${JSON.stringify(d.step2_sts_params)}`,
        `[Step2 STS]   headers sent: ${JSON.stringify(d.step2_headers_sent)}`,
        `[Step2 STS]   result: ${d.step2_sts_result}`,
      ].join('\n') : '';
      res.textContent = msg + (debugLines ? '\n\n' + debugLines : '');
      res.className = 'db-test-result ' + (r?.success ? 'ok' : 'err');
    }
  });

  // ── 异步加载：读取已保存的配置填入表单 ────────────────────────────────────
  const r = await _backendFetch('/api/file-store/config');
  if (r?.success && r.is_admin) {
    if (r.endpoint)      _setVal('minio-endpoint',     r.endpoint);
    if (r.bucket)        _setVal('minio-public-bucket', r.bucket);
    if (r.key_preview) {
      const keyEl = document.getElementById('minio-access-key');
      if (keyEl) keyEl.placeholder = r.key_preview + '（留空保留）';
    }
  }
  if (r?.success && r.is_admin && r.ois) {
    const o = r.ois;
    console.log('[file_store] 从 DB 读取 OIS 配置:', JSON.stringify(o));
    _setVal('ois-ois3-url',      o.ois3_url      ?? '');
    _setVal('ois-identify',      o.identify      ?? '');
    _setVal('ois-env',           o.env           ?? '');
    _setVal('ois-region',        o.region        ?? '');
    _setVal('ois-licloud-appid', o.licloud_appid ?? '');
    _setVal('ois-idaas-url',     o.idaas_url     ?? '');
    _setVal('ois-client-id',     o.idaas_client_id  ?? '');
    _setVal('ois-service-id',    o.idaas_service_id ?? '');
    _setVal('ois-public-base-url', o.public_base_url ?? '');
    if (o.secret_preview) {
      const el = document.getElementById('ois-client-secret');
      if (el) el.placeholder = o.secret_preview + '（留空保留）';
    }
  }
}

// ===================== 快捷键面板 =====================
async function _initShortcuts(config) {
  const list  = document.getElementById('shortcut-list');
  const cmds  = config?.commands || [];
  // 从 Electron 读取当前绑定的快捷键
  const shortcuts = (await window.electronAPI?.listShortcuts?.()) || {};
  const keys  = shortcuts.keys || shortcuts || {};

  if (cmds.length === 0) {
    list.innerHTML = '<div class="empty-state">暂无可配置的命令</div>';
    return;
  }

  list.innerHTML = '';
  cmds.forEach(cmd => {
    const currentKey = keys[cmd.id] || '';
    const item = document.createElement('div');
    item.className = 'shortcut-item';
    item.innerHTML =
      `<div class="shortcut-item-info">` +
        `<div class="shortcut-item-name">${cmd.name}</div>` +
        (cmd.desc ? `<div class="shortcut-item-desc">${cmd.desc}</div>` : '') +
      `</div>` +
      `<input type="text" class="shortcut-key-input" ` +
             `data-cmd="${cmd.id}" value="${currentKey}" ` +
             `placeholder="点击录制..." readonly>`;
    list.appendChild(item);
  });

  // 快捷键录制（click → 录制模式 → keydown → 保存）
  list.addEventListener('click', e => {
    const input = e.target.closest('.shortcut-key-input');
    if (!input) return;
    if (input.classList.contains('recording')) return;

    // 进入录制状态
    list.querySelectorAll('.shortcut-key-input.recording').forEach(el => {
      el.classList.remove('recording');
      el.placeholder = '点击录制...';
    });
    input.classList.add('recording');
    input.placeholder = '按下快捷键...';

    const onKey = async (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (e.key === 'Escape') {
        input.classList.remove('recording');
        input.placeholder = '点击录制...';
        document.removeEventListener('keydown', onKey, true);
        return;
      }
      // 构建快捷键字符串
      const parts = [];
      if (e.ctrlKey)  parts.push('Ctrl');
      if (e.altKey)   parts.push('Alt');
      if (e.shiftKey) parts.push('Shift');
      if (e.metaKey)  parts.push('Meta');
      if (!['Control','Alt','Shift','Meta'].includes(e.key)) {
        parts.push(e.key.length === 1 ? e.key.toUpperCase() : e.key);
      }
      const combo = parts.join('+');

      input.value = combo;
      input.classList.remove('recording');
      input.placeholder = '点击录制...';
      document.removeEventListener('keydown', onKey, true);

      // 保存
      if (combo) {
        await window.electronAPI?.bindShortcut?.(input.dataset.cmd, combo);
      }
    };
    document.addEventListener('keydown', onKey, true);
  });

  // 重置全部快捷键
  document.getElementById('btn-reset-shortcuts')?.addEventListener('click', async () => {
    // 逐项解绑（全量重置）
    list.querySelectorAll('.shortcut-key-input').forEach(async el => {
      await window.electronAPI?.unbindShortcut?.(el.dataset.cmd);
      el.value = '';
    });
  });
}

// ===================== 插件市场面板 =====================
// ===================== 插件管理（Phase 7A：Obsidian 风格）=====================
async function _initPluginMarket() {
  await _renderPluginList();

  // 监听注册表更新（enable/disable/install/uninstall 后刷新）
  window.electronAPI?.onPluginRegistryUpdated?.(() => _renderPluginList());

  // ── Tab 切换 ────────────────────────────────────────────────────────────
  document.querySelectorAll('.pm-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      const target = tab.dataset.tab;
      document.querySelectorAll('.pm-tab').forEach(t => {
        t.style.borderBottomColor = 'transparent';
        t.style.color = 'var(--text-muted)';
      });
      tab.style.borderBottomColor = 'var(--color-primary,#89b4fa)';
      tab.style.color = 'var(--text-normal)';
      document.getElementById('pm-pane-installed').style.display = target === 'installed' ? '' : 'none';
      document.getElementById('pm-pane-market').style.display    = target === 'market'    ? '' : 'none';
      if (target === 'market') _initMarketPane();
    });
  });

  // ── 从 URL 安装 ─────────────────────────────────────────────────────────
  const btnInstall = document.getElementById('pm-btn-install-url');
  const urlInput   = document.getElementById('pm-install-url');
  const feedback   = document.getElementById('pm-install-feedback');

  btnInstall?.addEventListener('click', async () => {
    const url = urlInput?.value?.trim();
    if (!url) { _pmFeedback(feedback, '请输入插件 URL', 'error'); return; }
    btnInstall.disabled = true;
    btnInstall.textContent = '安装中...';
    _pmFeedback(feedback, '正在下载并安装...', 'info');

    const res = await window.electronAPI?.installPluginFromUrl?.(url) || { ok: false, error: '不支持' };
    if (res.ok) {
      _pmFeedback(feedback, `✅ 插件「${res.name}」安装成功`, 'success');
      urlInput.value = '';
      await _renderPluginList();
    } else {
      _pmFeedback(feedback, `❌ 安装失败：${res.error}`, 'error');
    }
    btnInstall.disabled = false;
    btnInstall.textContent = '安装';
  });
}

// ── 市场浏览面板 ──────────────────────────────────────────────────────────

const PM_REGISTRY_LS_KEY = 'pm.registryUrl';

let _marketData = null;   // 缓存拉取的市场数据

async function _initMarketPane() {
  const urlInput  = document.getElementById('pm-registry-url');
  const btnRefresh = document.getElementById('pm-btn-refresh-market');
  const searchInput = document.getElementById('pm-market-search');

  // 恢复上次用的 URL
  if (urlInput && !urlInput.value) {
    urlInput.value = localStorage.getItem(PM_REGISTRY_LS_KEY) || '';
  }

  // 刷新按钮
  btnRefresh?.addEventListener('click', async () => {
    const url = urlInput?.value?.trim();
    if (!url) { _pmRenderMarketList([], '请输入注册表地址'); return; }
    localStorage.setItem(PM_REGISTRY_LS_KEY, url);
    await _pmLoadMarket(url);
  });

  // 搜索过滤
  searchInput?.addEventListener('input', () => {
    if (!_marketData) return;
    const q = searchInput.value.trim().toLowerCase();
    const filtered = q
      ? _marketData.plugins.filter(p =>
          p.name?.toLowerCase().includes(q) ||
          p.description?.toLowerCase().includes(q) ||
          p.author?.toLowerCase().includes(q) ||
          p.tags?.some(t => t.toLowerCase().includes(q)))
      : _marketData.plugins;
    _pmRenderMarketList(filtered);
  });

  // 如果已有缓存 URL，自动加载
  const savedUrl = urlInput?.value?.trim();
  if (savedUrl) await _pmLoadMarket(savedUrl);
}

async function _pmLoadMarket(url) {
  const listEl = document.getElementById('pm-market-list');
  if (listEl) listEl.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-muted)">加载中...</div>';

  const result = await window.electronAPI?.fetchPluginMarket?.(url);
  if (!result || result.error) {
    _pmRenderMarketList([], result?.error || '加载失败，请检查 URL 是否可访问');
    return;
  }
  _marketData = result;
  _pmRenderMarketList(result.plugins);
}

function _pmRenderMarketList(plugins, errorMsg) {
  const listEl = document.getElementById('pm-market-list');
  if (!listEl) return;

  if (errorMsg) {
    listEl.innerHTML = `<div style="padding:20px;text-align:center;color:var(--color-error,#f38ba8);font-size:13px">⚠ ${errorMsg}</div>`;
    return;
  }
  if (!plugins.length) {
    listEl.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-muted);font-size:13px">没有找到插件</div>';
    return;
  }

  listEl.innerHTML = '';
  plugins.forEach(plugin => {
    const card = document.createElement('div');
    card.style.cssText = 'padding:12px 14px;border-radius:8px;background:var(--bg-secondary,#252535);display:flex;gap:12px;align-items:flex-start;';

    const installBtnHtml = plugin.installed
      ? `<button disabled style="padding:5px 12px;font-size:12px;border-radius:6px;border:none;background:var(--bg-tertiary);color:var(--text-muted);white-space:nowrap;">已安装</button>`
      : plugin.download_url
        ? `<button class="btn-primary pm-btn-market-install" data-id="${plugin.plugin_id}" data-url="${plugin.download_url}" data-name="${plugin.name}"
               style="padding:5px 12px;font-size:12px;white-space:nowrap;">安装</button>`
        : `<button disabled style="padding:5px 12px;font-size:12px;border-radius:6px;border:none;background:var(--bg-tertiary);color:var(--text-muted);white-space:nowrap;">暂无下载</button>`;

    card.innerHTML = `
      <div style="flex:1;min-width:0;">
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
          <span style="font-size:14px;font-weight:500;color:var(--text-normal);">${plugin.name}</span>
          <span style="font-size:11px;color:var(--text-muted);">v${plugin.version}</span>
          ${plugin.author ? `<span style="font-size:11px;color:var(--text-faint,#6c7086);">by ${plugin.author}</span>` : ''}
          ${(plugin.tags || []).map(t => `<span style="font-size:10px;padding:1px 6px;border-radius:10px;background:var(--bg-tertiary);color:var(--text-muted);">${t}</span>`).join('')}
        </div>
        ${plugin.description ? `<div style="font-size:12px;color:var(--text-muted);margin-top:4px;line-height:1.5;">${plugin.description}</div>` : ''}
        <div id="pm-market-fb-${plugin.plugin_id.replace(/\./g, '-')}" style="font-size:11px;margin-top:4px;min-height:14px;"></div>
      </div>
      <div style="flex-shrink:0;">${installBtnHtml}</div>
    `;

    // 安装按钮事件
    card.querySelector('.pm-btn-market-install')?.addEventListener('click', async (e) => {
      const btn = e.currentTarget;
      const fbId = `pm-market-fb-${btn.dataset.id.replace(/\./g, '-')}`;
      const fbEl = document.getElementById(fbId);
      btn.disabled = true; btn.textContent = '安装中...';
      _pmFeedback(fbEl, '正在下载...', 'info');

      const res = await window.electronAPI?.installPluginFromUrl?.(btn.dataset.url) || { ok: false, error: '不支持' };
      if (res.ok) {
        btn.textContent = '已安装';
        _pmFeedback(fbEl, '✅ 安装成功', 'success');
        await _renderPluginList();
        // 刷新市场列表中的安装状态
        if (_marketData) {
          const p = _marketData.plugins.find(x => x.plugin_id === btn.dataset.id);
          if (p) p.installed = true;
          const q = document.getElementById('pm-market-search')?.value?.trim().toLowerCase() || '';
          const filtered = q ? _marketData.plugins.filter(p =>
            p.name?.toLowerCase().includes(q) || p.description?.toLowerCase().includes(q)) : _marketData.plugins;
          _pmRenderMarketList(filtered);
        }
      } else {
        btn.disabled = false; btn.textContent = '安装';
        _pmFeedback(fbEl, `❌ ${res.error}`, 'error');
      }
    });

    listEl.appendChild(card);
  });
}


function _pmFeedback(el, msg, type) {
  if (!el) return;
  el.textContent = msg;
  const colors = { success: 'var(--color-success,#a6e3a1)', error: 'var(--color-error,#f38ba8)', info: 'var(--text-muted,#a6adc8)' };
  el.style.color = colors[type] || colors.info;
}

async function _renderPluginList() {
  const container = document.getElementById('pm-installed-list');
  if (!container) return;

  let registry = null;
  try {
    registry = await window.electronAPI?.getPluginRegistry?.();
  } catch (_) {}

  // showInUI=false 的插件（如 official.core 基座）不在此界面显示
  const plugins = (registry?.plugins || []).filter(p => p.showInUI !== false);
  if (!plugins.length) {
    container.innerHTML = '<div style="padding:16px;text-align:center;color:var(--text-muted)">暂无插件</div>';
    return;
  }

  container.innerHTML = '';

  // 分组：官方内置模块（只展示，不可关闭）/ 用户安装（可管理）
  const groups = [
    {
      label: '官方模块',
      desc: '系统内置模块，随应用更新，不可单独关闭',
      items: plugins.filter(p => p.source === 'builtin'),
    },
    {
      label: '用户安装的插件',
      desc: '你从外部安装的第三方插件，可启用/禁用/卸载',
      items: plugins.filter(p => p.source === 'user'),
    },
  ].filter(g => g.items.length > 0);

  groups.forEach(group => {
    const hdr = document.createElement('div');
    hdr.style.cssText = 'padding:12px 0 4px;';
    hdr.innerHTML = `<div style="font-size:11px;font-weight:600;color:var(--text-muted);letter-spacing:.05em;text-transform:uppercase;">${group.label}</div>
      ${group.desc ? `<div style="font-size:11px;color:var(--text-faint,#6c7086);margin-top:2px;">${group.desc}</div>` : ''}`;
    container.appendChild(hdr);

    group.items.forEach(plugin => {
      const row = document.createElement('div');
      row.style.cssText = 'display:flex;align-items:center;padding:10px 12px;border-radius:8px;background:var(--bg-secondary,#252535);margin-bottom:4px;gap:12px;';

      // 开关（只有 canDisable=true 的才可交互）
      const toggleId = `pm-toggle-${plugin.plugin_id.replace(/\./g, '-')}`;
      row.innerHTML = `
        <label class="toggle-switch" style="flex-shrink:0;" title="${plugin.enabled ? '点击禁用' : '点击启用'}">
          <input type="checkbox" id="${toggleId}" ${plugin.enabled ? 'checked' : ''} ${!plugin.canDisable ? 'disabled' : ''}>
          <span class="toggle-slider"></span>
        </label>
        <div style="flex:1;min-width:0;">
          <div style="display:flex;align-items:center;gap:8px;">
            <span style="font-size:13px;font-weight:500;color:var(--text-normal);">${plugin.name}</span>
            <span style="font-size:11px;color:var(--text-muted);">v${plugin.version}</span>
            ${plugin.author ? `<span style="font-size:11px;color:var(--text-faint,#6c7086)">by ${plugin.author}</span>` : ''}
          </div>
          ${plugin.description ? `<div style="font-size:12px;color:var(--text-muted);margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${plugin.description}</div>` : ''}
          <div id="pm-row-fb-${plugin.plugin_id.replace(/\./g, '-')}" style="font-size:11px;min-height:14px;margin-top:2px;"></div>
        </div>
        ${plugin.canUninstall ? `<button class="btn-secondary" data-uninstall="${plugin.plugin_id}" style="font-size:12px;padding:4px 10px;white-space:nowrap;flex-shrink:0;">卸载</button>` : ''}
      `;

      // Toggle enable/disable
      const toggle = row.querySelector(`#${toggleId}`);
      toggle?.addEventListener('change', async (e) => {
        const enabled = e.target.checked;
        toggle.disabled = true;
        const fbEl = row.querySelector(`#pm-row-fb-${plugin.plugin_id.replace(/\./g, '-')}`);
        const res = await window.electronAPI?.setPluginEnabled?.(plugin.plugin_id, enabled) || { ok: true };
        toggle.disabled = !plugin.canDisable;
        if (fbEl) {
          fbEl.textContent = enabled ? '✓ 已启用（重启后完全生效）' : '已禁用';
          fbEl.style.color = enabled ? 'var(--color-success,#a6e3a1)' : 'var(--text-muted)';
          setTimeout(() => { if (fbEl) fbEl.textContent = ''; }, 3000);
        }
      });

      // 卸载按钮
      row.querySelector('[data-uninstall]')?.addEventListener('click', async (e) => {
        const btn = e.currentTarget;
        if (!confirm(`确定卸载插件「${plugin.name}」？此操作无法撤销。`)) return;
        btn.disabled = true; btn.textContent = '卸载中...';
        const res = await window.electronAPI?.uninstallUserPlugin?.(plugin.plugin_id) || { ok: false, error: '不支持' };
        if (res.ok) {
          row.style.opacity = '0.5';
          btn.textContent = '已卸载';
          await _renderPluginList();
        } else {
          btn.disabled = false; btn.textContent = '卸载';
          const fbEl = row.querySelector(`#pm-row-fb-${plugin.plugin_id.replace(/\./g, '-')}`);
          if (fbEl) { fbEl.textContent = `卸载失败: ${res.error}`; fbEl.style.color = 'var(--color-error,#f38ba8)'; }
        }
      });

      container.appendChild(row);
    });
  });
}


// ===================== 已安装插件设置（动态注入）=====================
async function _initInstalledPlugins() {
  let plugins = [];
  if (window.electronAPI?.listInstalledPlugins) {
    plugins = (await window.electronAPI.listInstalledPlugins()) || [];
  } else {
    plugins = await _apiCall('get_installed_plugins') || [];
  }
  if (!plugins.length) return;

  // 官方插件：个人开关存 localStorage（仅影响自己）
  const officialSync = plugins.filter(p => p.plugin_source === 'official' || p.category === 'official');
  for (const plugin of officialSync) {
    const lsKey = _lsk(`user.plugin.enabled.${plugin.plugin_id}`);
    // localStorage 已有值则跳过（无需从后端同步）
    if (localStorage.getItem(lsKey) === null) {
      localStorage.setItem(lsKey, 'true');
    }
  }

  const navEl    = document.getElementById('installed-plugin-nav');
  const panelsEl = document.getElementById('installed-plugin-panels');

  const official   = plugins.filter(p => p.plugin_source === 'official'    || p.category === 'official');
  const thirdParty = plugins.filter(p => p.plugin_source === 'third_party' || p.category === 'third_party' || (!p.plugin_source && !p.category));

  // ── 官方插件组 ──
  if (official.length) {
    _appendNavSection(navEl, '官方插件');
    for (const plugin of official) {
      await _buildPluginNavAndPanel(plugin, navEl, panelsEl, 'official');
    }
  }

  // ── 第三方插件组（仅 has_settings 的显示设置面板）──
  const thirdWithSettings = thirdParty.filter(p => p.has_settings);
  if (thirdWithSettings.length) {
    _appendNavSection(navEl, '第三方插件');
    for (const plugin of thirdWithSettings) {
      await _buildPluginNavAndPanel(plugin, navEl, panelsEl, 'third_party');
    }
  }
}

function _appendNavSection(navEl, label) {
  if (!navEl) return;
  const div = document.createElement('div');
  div.className = 'nav-divider';
  navEl.appendChild(div);
  const lbl = document.createElement('div');
  lbl.className = 'nav-group-label';
  lbl.textContent = label;
  navEl.appendChild(lbl);
}

async function _buildPluginNavAndPanel(plugin, navEl, panelsEl, sourceType) {
  const panelId = `plugin-${plugin.plugin_id}`;

  // 左侧 nav 项
  const navItem = document.createElement('div');
  navItem.className = 'nav-item';
  navItem.dataset.panel = panelId;
  navItem.textContent = plugin.name;
  navEl?.appendChild(navItem);
  navItem.addEventListener('click', () => {
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    navItem.classList.add('active');
    document.querySelectorAll('.settings-panel').forEach(p => p.classList.remove('active'));
    document.getElementById(`panel-${panelId}`)?.classList.add('active');
  });

  // 右侧面板
  const panelEl = document.createElement('div');
  panelEl.className = 'settings-panel';
  panelEl.id = `panel-${panelId}`;

  // 官方插件：个人开关（存 localStorage，仅影响自己）
  let personalToggleHtml = '';
  if (sourceType === 'official') {
    const lsKey    = _lsk(`user.plugin.enabled.${plugin.plugin_id}`);
    const isPersonalOn = localStorage.getItem(lsKey) !== 'false';
    personalToggleHtml =
      `<div class="setting-group">` +
        `<div class="setting-group-title">个人设置</div>` +
        `<div class="setting-item">` +
          `<div class="setting-item-info">` +
            `<div class="setting-item-label">为我启用</div>` +
            `<div class="setting-item-desc">仅影响你自己，不影响其他用户。超管可全局禁用。</div>` +
          `</div>` +
          `<label class="toggle-switch">` +
            `<input type="checkbox" ${isPersonalOn ? 'checked' : ''} ` +
                   `data-personal-plugin="${plugin.plugin_id}">` +
            `<span class="toggle-slider"></span>` +
          `</label>` +
        `</div>` +
      `</div>`;
    // 灰化未启用插件的 nav 项
    if (!isPersonalOn) navItem.style.opacity = '0.45';
  }

  panelEl.innerHTML =
    `<div class="panel-title">${plugin.name}</div>` +
    personalToggleHtml +
    `<div class="setting-group" id="pset-${plugin.plugin_id}">` +
      `<div class="empty-state">${plugin.has_settings ? '加载中...' : '该插件无可配置项'}</div>` +
    `</div>`;
  panelsEl?.appendChild(panelEl);

  // 绑定个人开关事件
  if (sourceType === 'official') {
    panelEl.querySelector(`[data-personal-plugin="${plugin.plugin_id}"]`)
      ?.addEventListener('change', e => {
        const lsKey = _lsk(`user.plugin.enabled.${plugin.plugin_id}`);
        localStorage.setItem(lsKey, e.target.checked);
        navItem.style.opacity = e.target.checked ? '' : '0.45';
      });
  }

  // 加载插件配置项（仅 has_settings 的插件）
  if (!plugin.has_settings) return;
  const items = await _apiCall('get_plugin_settings_data', plugin.plugin_id) || [];
  const pset = document.getElementById(`pset-${plugin.plugin_id}`);
  if (!pset) return;
  if (!items.length) { pset.innerHTML = '<div class="empty-state">该插件无可配置项</div>'; return; }

  pset.innerHTML = '';
  items.forEach(item => {
    const row = document.createElement('div');
    row.className = 'setting-item';
    row.innerHTML =
      `<div class="setting-item-info"><div class="setting-item-label">${item.label}</div>` +
      (item.desc ? `<div class="setting-item-desc">${item.desc}</div>` : '') +
      `</div>` +
      (item.type === 'checkbox'
        ? `<label class="setting-toggle"><input type="checkbox" ${item.value ? 'checked' : ''} data-plugin="${plugin.plugin_id}" data-key="${item.key}" class="plugin-cfg"><span class="toggle-track"></span></label>`
        : `<input type="text" class="setting-input plugin-cfg" value="${item.value || ''}" data-plugin="${plugin.plugin_id}" data-key="${item.key}">`);
    pset.appendChild(row);
  });

  pset.addEventListener('change', async e => {
    const el = e.target.closest('.plugin-cfg');
    if (!el) return;
    const val = el.type === 'checkbox' ? el.checked : el.value;
    await _apiCall('save_plugin_config', el.dataset.plugin, el.dataset.key, val);
  });
}

// ===================== 飞书集成面板 =====================
async function _initFeishu() {
  // --- 读取当前 app_id（判断凭证是否已配置，同时填入输入框）---
  const appIdRes = await _backendFetch('/admin/config/FEISHU_APP_ID');
  const appId    = appIdRes?.data?.value || '';
  const hasCreds = !!appId;

  // 填入 App ID（Secret 不回显，仅显示占位符）
  const appIdInput = document.getElementById('feishu-app-id');
  if (appIdInput && appId) appIdInput.value = appId;

  // --- 凭证保存 ---
  const btnSave  = document.getElementById('btn-save-feishu-creds');
  const feedback = document.getElementById('feishu-creds-feedback');

  btnSave?.addEventListener('click', async () => {
    const id     = document.getElementById('feishu-app-id')?.value.trim()     || '';
    const secret = document.getElementById('feishu-app-secret')?.value.trim() || '';
    if (!id) { _showFeedback(feedback, '请填写 App ID', true); return; }

    btnSave.disabled = true;
    btnSave.textContent = '保存中...';
    // 分两次写入：App ID 和 App Secret
    const r1 = await _backendFetch('/admin/config/FEISHU_APP_ID', {
      method: 'PUT', body: JSON.stringify({ value: id, description: '飞书应用 ID' }),
    });
    const r2 = secret ? await _backendFetch('/admin/config/FEISHU_APP_SECRET', {
      method: 'PUT', body: JSON.stringify({ value: secret, description: '飞书应用 Secret' }),
    }) : { success: true };
    btnSave.disabled = false;
    btnSave.textContent = '保存凭证';

    if (r1?.success && r2?.success) {
      _showFeedback(feedback, '已保存');
      document.getElementById('feishu-app-secret').value = '';
    } else {
      _showFeedback(feedback, r1?.msg || r2?.msg || '保存失败', true);
    }
  });

  // --- 登录状态刷新 ---
  await _refreshFeishuStatus(hasCreds);

  // --- 登录按钮 ---
  document.getElementById('btn-feishu-login')?.addEventListener('click', async () => {
    const fb = document.getElementById('feishu-login-feedback');
    _showFeedback(fb, '正在打开飞书扫码登录页...');
    const result = await window.electronAPI?.authFeishuLogin?.();
    if (result?.ok) {
      _showFeedback(fb, `欢迎，${result.state?.user?.name || ''}`);
      await _refreshFeishuStatus();
    } else {
      _showFeedback(fb, result?.error || '登录失败，请重试', true);
    }
  });

  // --- 退出登录 ---
  document.getElementById('btn-feishu-logout')?.addEventListener('click', async () => {
    await window.electronAPI?.authLogout?.();
    _showFeedback(document.getElementById('feishu-login-feedback'), '已退出登录');
    await _refreshFeishuStatus();
  });
}

async function _refreshFeishuStatus(_hasCreds) {
  // 新架构：auth 由 Electron 主进程管理，直接读 authGetState
  const state = (await window.electronAPI?.authGetState?.()) || {};
  const loggedIn = state.mode === 'feishu';
  const user     = state.user || {};

  const nameEl      = document.getElementById('feishu-user-name');
  const emailEl     = document.getElementById('feishu-user-email');
  const avatarImg   = document.getElementById('feishu-avatar');
  const placeholder = document.getElementById('feishu-avatar-placeholder');
  const btnLogin    = document.getElementById('btn-feishu-login');
  const btnLogout   = document.getElementById('btn-feishu-logout');

  if (loggedIn) {
    if (nameEl)  nameEl.textContent  = user.name  || '已登录';
    if (emailEl) emailEl.textContent = user.email || '';
    if (user.avatar_url && avatarImg) {
      avatarImg.src = user.avatar_url;
      avatarImg.style.display = 'block';
      if (placeholder) placeholder.style.display = 'none';
    } else if (placeholder) {
      placeholder.style.display = '';
      placeholder.textContent = (user.name || '?')[0].toUpperCase();
    }
    if (btnLogin)  btnLogin.style.display  = 'none';
    if (btnLogout) btnLogout.style.display = '';
  } else {
    if (nameEl)      nameEl.textContent      = '未登录';
    if (emailEl)     emailEl.textContent     = '';
    if (avatarImg)   avatarImg.style.display = 'none';
    if (placeholder) { placeholder.style.display = ''; placeholder.textContent = '?'; }
    if (btnLogin)    btnLogin.style.display    = '';
    if (btnLogout)   btnLogout.style.display   = 'none';
  }
}

function _showFeedback(el, msg, isError = false) {
  if (!el) return;
  el.textContent = msg;
  el.style.color = isError ? 'var(--color-red)' : 'var(--color-green)';
  clearTimeout(el._timer);
  el._timer = setTimeout(() => { el.textContent = ''; }, 3000);
}

// ===================== 入口 =====================
async function _start() {
  // 从 Electron 获取应用配置（backendUrl, version 等），无需 Python bridge
  const appConfig = (await window.electronAPI?.getConfig?.()) || {};
  const config = { system: {}, ...appConfig };

  // 缓存当前用户 GID 供 _lsk() 使用（优先读父窗口的已认证用户）
  const _parentUser = window.parent?._authUser || window.top?._authUser;
  if (_parentUser?.gid) {
    _sUserGid = _parentUser.gid;
  } else {
    const _authState = (await window.electronAPI?.authGetState?.()) || {};
    _sUserGid = _authState.user?.gid || _authState.user?.user_gid || '';
  }

  // 同步主题：优先 localStorage，最后默认 light
  const theme = localStorage.getItem('system.theme') || 'light';
  ThemeSync.apply(theme);
  localStorage.setItem('system.theme', theme);

  _initNav();
  _initAppearance(config);
  _initGeneral(config);
  _initDatabase(config);
  await _initShortcuts(config);
  await _initFileStore();
  _initListDefaults();
  _initAboutPanel();
  // 权限门控：最后执行，确保所有面板已渲染
  await _applyPermissions();
}

// 启动时机：DOMContentLoaded（Electron 模式，无需等 pywebviewready）
document.addEventListener('DOMContentLoaded', () => {
  _initNav();  // 导航可以立即绑定

  // 先用 localStorage 主题显示页面，避免闪烁
  const localTheme = localStorage.getItem('system.theme') || 'light';
  ThemeSync.apply(localTheme);

  _start();

  // 登录/退出后主进程广播状态，刷新飞书账号面板
  window.electronAPI?.onAuthStateChanged?.(() => _refreshFeishuStatus());
  // 跨窗口主题同步（主窗口或其他页面改主题后同步到设置窗口）
  window.electronAPI?.onThemeChanged?.((theme) => {
    ThemeSync.apply(theme);
    localStorage.setItem('system.theme', theme);
  });
});

// 监听父窗口广播的主题变化（iframe 场景）
window.addEventListener('message', e => {
  if (e.data?.type === 'theme') ThemeSync.apply(e.data.theme);
});

// ===================== 权限门控 =====================
/**
 * 根据当前登录用户的系统角色，动态 show/hide 导航项和面板。
 * 规则：
 *   1. 有 data-perm-role="X" 属性的导航项/面板，仅当用户角色在 X 及以上时显示
 *   2. 飞书"应用凭证"分区（.feishu-admin-section）仅 super_admin / team_admin 可见
 *   3. 数据库面板（panel-database）仅 super_admin 可见
 *
 * 注意：在 Electron 模式下通过 electronAPI.authGetState() 读取角色。
 */

// 与 app/domain/user_permission/roles.py SETTINGS_VISIBILITY 保持同步
const _SETTINGS_VISIBILITY = {
  super_admin:     ['appearance','shortcuts','general','database','file-store','feishu','plugin-market','follows-cleanup','notif-prefs','user-management','feature-flags','list-defaults'],
  team_admin:      ['appearance','shortcuts','general','file-store','feishu','plugin-market','follows-cleanup','notif-prefs','user-management','list-defaults'],
  project_admin:   ['appearance','shortcuts','general','feishu','plugin-market','follows-cleanup','notif-prefs','list-defaults'],
  rule_admin:      ['appearance','shortcuts','general','feishu','plugin-market','follows-cleanup','notif-prefs','list-defaults'],
  knowledge_admin: ['appearance','shortcuts','general','feishu','plugin-market','follows-cleanup','notif-prefs','list-defaults'],
  member:          ['appearance','shortcuts','general','feishu','plugin-market','follows-cleanup','notif-prefs','list-defaults'],
  external:        ['appearance'],
};

async function _applyPermissions() {
  let role = 'member';
  // 优先读父窗口（主页面）的 _authUser，它在 onAuthStateChanged 时由 /auth/me 更新
  const parentUser = window.parent?._authUser || window.top?._authUser;
  if (parentUser) {
    role = parentUser.system_role || parentUser.org_role || parentUser.role || 'member';
  } else if (window.electronAPI?.authGetState) {
    // 降级：读 localStorage（可能滞后，但总比 member 好）
    const state = (await window.electronAPI.authGetState()) || {};
    if (state.mode === 'feishu' && state.user) {
      role = state.user.system_role || state.user.org_role || state.user.role || 'member';
    }
  }
  const visiblePanels = _SETTINGS_VISIBILITY[role] || _SETTINGS_VISIBILITY.member;
  _applyPanelVisibility(visiblePanels, role);
}

function _applyPanelVisibility(visiblePanels, role = 'member') {
  // 1. 隐藏无权限的导航项（跳过动态注入的插件项，它们以 plugin- 开头）
  document.querySelectorAll('.nav-item[data-panel]').forEach(item => {
    const panelId = item.dataset.panel;
    if (panelId.startsWith('plugin-')) return;
    if (!visiblePanels.includes(panelId)) {
      item.style.display = 'none';
    }
  });

  // 2. 隐藏无权限的面板（跳过插件面板）
  document.querySelectorAll('.settings-panel[id]').forEach(panel => {
    const panelId = panel.id.replace('panel-', '');
    if (panelId.startsWith('plugin-')) return;
    if (!visiblePanels.includes(panelId)) {
      panel.style.display = 'none';
    }
  });

  // 4. 插件系统全局开关 — 超管关闭后，非超管用户隐藏插件市场和第三方插件区
  const isSuperAdmin = visiblePanels.includes('feature-flags');
  if (!isSuperAdmin) {
    const flags = _cachedFeatureFlags || {};
    if (flags.plugin_system === false) {
      // 隐藏插件市场 nav 和面板
      document.querySelector('.nav-item[data-panel="plugin-market"]')
        ?.style.setProperty('display', 'none');
      document.getElementById('panel-plugin-market')
        ?.style.setProperty('display', 'none');

      // 隐藏 installed-plugin-nav 中属于"第三方插件"的部分（官方插件区保留）
      const navContainer = document.getElementById('installed-plugin-nav');
      if (navContainer) {
        let inThirdParty = false;
        Array.from(navContainer.children).forEach(el => {
          if (el.classList.contains('nav-group-label')) {
            inThirdParty = el.textContent.trim() === '第三方插件';
          }
          if (inThirdParty) el.style.display = 'none';
        });
      }
    }
  }

  // 5. 功能开关：管理员可在功能开关管理中心进一步限制设置面板可见性
  //    feature flag key: settings_panel_{panelId，-替换为_}
  //    值结构: { visibility: 'all'|'member'|'team_admin'|'super_admin' }
  {
    const featureFlags = _cachedFeatureFlags || {};
    const ROLE_RANK = { external: 0, member: 1, knowledge_admin: 2, rule_admin: 2, project_admin: 2, team_admin: 3, super_admin: 4 };
    const VIS_RANK  = { all: 0, member: 1, team_admin: 3, super_admin: 4 };
    const userRank  = ROLE_RANK[role] ?? 1;

    document.querySelectorAll('.settings-panel[id], .nav-item[data-panel]').forEach(el => {
      const panelId = el.id ? el.id.replace('panel-', '') : el.dataset.panel;
      if (!panelId || panelId.startsWith('plugin-')) return;
      const flagKey  = 'settings_panel_' + panelId.replace(/-/g, '_');
      const flagEntry = featureFlags[flagKey];
      if (!flagEntry) return;
      const required    = flagEntry.visibility || 'all';
      const requiredRank = VIS_RANK[required] ?? 0;
      if (userRank < requiredRank) el.style.display = 'none';
    });
  }

  // 6. 确保当前激活的面板是有权限且可见的面板
  const firstVisible = visiblePanels[0] || 'appearance';
  const activeNav = document.querySelector('.nav-item.active');
  if (activeNav) {
    const activePanelId = activeNav.dataset.panel;
    const activePanel = document.getElementById('panel-' + activePanelId);
    const isHidden = !visiblePanels.includes(activePanelId) || activePanel?.style.display === 'none';
    if (isHidden && !activePanelId?.startsWith('plugin-')) {
      const newNavItem = document.querySelector(`.nav-item[data-panel="${firstVisible}"]`);
      if (newNavItem) newNavItem.click();
    }
  }
}

// ===================== 用户管理面板 =====================
const ROLE_LABELS = {
  super_admin: '超级管理员', team_admin: '团队管理员',
  project_admin: '项目管理员', rule_admin: '规则管理员',
  knowledge_admin: '知识库管理员',
  member: '普通用户', external: '外部用户',
};
const EXT_LABELS = {
  outsource: '外包', rd: '研发人员', factory: '基地生产人员', supplier: '供应商人员',
};

// 直接调 backend FastAPI，带 JWT。比走 Python bridge 更可靠（用户数据在 PG）。
async function _backendFetch(path, opts = {}) {
  const config = (await window.electronAPI?.getConfig?.()) || {};
  const state  = (await window.electronAPI?.authGetState?.()) || {};
  const runtimeBase = await window.AI00RuntimeConfig?.getRuntimeBackendBase?.(config?.backendUrl || '')
  const baseUrl = (runtimeBase || config.backendUrl || '').replace(/\/$/, '');

  const stateToken = typeof state.token === 'string' ? state.token.trim() : '';
  const localToken = (localStorage.getItem('ai00_token') || '').trim();
  const isJwtLike = (token) => typeof token === 'string' && token.split('.').length === 3;
  const token = isJwtLike(stateToken) ? stateToken : (isJwtLike(localToken) ? localToken : stateToken || localToken || '');
  const tokenSource = isJwtLike(stateToken) ? 'authGetState' : (isJwtLike(localToken) ? 'localStorage' : (stateToken ? 'authGetState-invalid' : (localToken ? 'localStorage-invalid' : 'none')));

  console.log('[settings._backendFetch]', opts.method || 'GET', path, 'token:', token ? `有(${tokenSource})` : '无', 'baseUrl:', baseUrl);

  if (!token) return { success: false, msg: '未登录或 token 为空' };

  try {
    const res = await fetch(`${baseUrl}${path}`, {
      ...opts,
      headers: {
        'Content-Type': 'application/json',
        'X-AI00-Token': token,
        ...(opts.headers || {}),
      },
    });
    const data = await res.json().catch(() => ({}));
    console.log('[settings._backendFetch] 响应', res.status, data);
    if (!res.ok) return { success: false, msg: data.detail || data.msg || `HTTP ${res.status}`, detail: data.detail || '', status: res.status };
    return { success: true, ...data };
  } catch (e) {
    console.error('[settings._backendFetch] 异常', e);
    return { success: false, msg: e.message };
  }
}

async function _initUserManagement() {
  const container = document.getElementById('user-list-container');
  const searchInput = document.getElementById('user-search-input');
  const refreshBtn = document.getElementById('btn-refresh-users');
  if (!container) return;

  let _allUsers = [];

  async function _loadUsers() {
    container.innerHTML = '<div class="empty-state">加载中...</div>';
    const res = await _backendFetch('/users/');
    if (!res.success) {
      container.innerHTML = `<div class="empty-state">${res.msg || '权限不足'}</div>`;
      return;
    }
    _allUsers = res.data || [];
    _renderUsers(_allUsers);
  }

  function _renderUsers(users) {
    if (!users.length) {
      container.innerHTML = '<div class="empty-state">暂无用户</div>';
      return;
    }
    container.innerHTML = users.map(u => {
      const avatar = u.avatar_url
        ? `<img src="${u.avatar_url}" style="width:28px;height:28px;border-radius:50%;object-fit:cover;">`
        : `<div style="width:28px;height:28px;border-radius:50%;background:var(--bg-tertiary);display:flex;align-items:center;justify-content:center;font-size:13px;">${(u.name||'?')[0]}</div>`;
      const roleOptions = Object.entries(ROLE_LABELS)
        .map(([v, l]) => `<option value="${v}"${u.system_role===v?' selected':''}>${l}</option>`)
        .join('');
      const extOptions = u.system_role === 'external'
        ? `<select class="setting-select" style="width:110px;margin-left:6px;" data-user-gid="${u.gid}" data-field="ext_subtype">
            ${Object.entries(EXT_LABELS).map(([v,l])=>`<option value="${v}"${u.external_subtype===v?' selected':''}>${l}</option>`).join('')}
           </select>`
        : '';
      return `
        <div class="setting-item" style="padding:8px 0;" data-user-gid="${u.gid}">
          <div style="display:flex;align-items:center;gap:10px;flex:1;">
            ${avatar}
            <div>
              <div style="font-size:13px;font-weight:500;">${u.name || '(未命名)'}</div>
              <div style="font-size:11px;color:var(--text-muted);">${u.email || ''}</div>
            </div>
          </div>
          <div style="display:flex;align-items:center;gap:6px;">
            <select class="setting-select" style="width:130px;" data-user-gid="${u.gid}" data-field="role">
              ${roleOptions}
            </select>
            ${extOptions}
            <button class="btn-primary" style="padding:4px 10px;font-size:12px;"
                    onclick="_saveUserRole('${u.gid}', this)">保存</button>
          </div>
        </div>`;
    }).join('');
  }

  if (searchInput) {
    searchInput.addEventListener('input', () => {
      const kw = searchInput.value.trim().toLowerCase();
      const filtered = kw
        ? _allUsers.filter(u => u.name?.toLowerCase().includes(kw) || u.email?.toLowerCase().includes(kw))
        : _allUsers;
      _renderUsers(filtered);
    });
  }

  if (refreshBtn) refreshBtn.addEventListener('click', _loadUsers);

  await _loadUsers();
}

// ===================== 关注清理面板 =====================
function _initFollowsCleanup() {
  const KEY_TASK  = _lsk('fc.rule.task');
  const KEY_ISSUE = _lsk('fc.rule.issue');
  const KEY_KDAYS = _lsk('fc.rule.knowledge_days');

  const taskToggle  = document.getElementById('fc-rule-task');
  const issueToggle = document.getElementById('fc-rule-issue');
  const kDaysInput  = document.getElementById('fc-rule-knowledge-days');
  const runBtn      = document.getElementById('fc-btn-run');
  const resultEl    = document.getElementById('fc-result');

  // 从 localStorage 恢复规则（默认 checked=true）
  if (taskToggle)  taskToggle.checked  = localStorage.getItem(KEY_TASK)  !== 'false';
  if (issueToggle) issueToggle.checked = localStorage.getItem(KEY_ISSUE) !== 'false';
  if (kDaysInput && localStorage.getItem(KEY_KDAYS) !== null) {
    kDaysInput.value = localStorage.getItem(KEY_KDAYS);
  }

  // 实时持久化规则
  taskToggle?.addEventListener('change',  () => localStorage.setItem(KEY_TASK,  taskToggle.checked));
  issueToggle?.addEventListener('change', () => localStorage.setItem(KEY_ISSUE, issueToggle.checked));
  kDaysInput?.addEventListener('input',   () => localStorage.setItem(KEY_KDAYS, kDaysInput.value));

  // 立即清理
  runBtn?.addEventListener('click', async () => {
    const state = (await window.electronAPI?.authGetState?.()) || {};
    if (state.mode !== 'feishu') {
      if (resultEl) { resultEl.textContent = '仅飞书登录模式下可执行清理'; resultEl.style.color = 'var(--text-muted,#a6adc8)'; }
      return;
    }

    runBtn.disabled = true;
    runBtn.textContent = '清理中...';
    if (resultEl) { resultEl.textContent = ''; }

    try {
      const cleanTask  = taskToggle?.checked  ?? true;
      const cleanIssue = issueToggle?.checked ?? true;
      const kDays      = parseInt(kDaysInput?.value) || 0;

      // 拉取当前用户所有关注
      const res     = await _backendFetch('/api/follows');
      const follows = res?.data || [];

      const toDelete = [];

      for (const f of follows) {
        const { gid: followGid, item_type, item_gid, created_at } = f;

        if (item_type === 'task' && cleanTask) {
          const r      = await _backendFetch(`/api/tasks/${item_gid}`);
          const status = r?.data?.status || r?.status || '';
          if (['completed', 'closed'].includes(status)) toDelete.push(followGid);

        } else if (item_type === 'issue' && cleanIssue) {
          const r      = await _backendFetch(`/api/issues/${item_gid}`);
          const status = r?.data?.status || r?.status || '';
          if (['resolved', 'closed'].includes(status)) toDelete.push(followGid);

        } else if (item_type === 'knowledge' && kDays > 0 && created_at) {
          const ageDays = (Date.now() - new Date(created_at).getTime()) / 86_400_000;
          if (ageDays > kDays) toDelete.push(followGid);
        }
      }

      // 批量删除
      for (const fGid of toDelete) {
        await _backendFetch(`/api/follows/${fGid}`, { method: 'DELETE' });
      }

      if (resultEl) {
        const n = toDelete.length;
        resultEl.textContent  = n > 0 ? `已取消关注 ${n} 项` : '没有需要清理的关注项';
        resultEl.style.color  = n > 0 ? 'var(--color-green,#a6e3a1)' : 'var(--text-muted,#a6adc8)';
      }
    } catch (err) {
      if (resultEl) {
        resultEl.textContent = '清理失败: ' + err.message;
        resultEl.style.color = 'var(--color-red,#f38ba8)';
      }
    } finally {
      runBtn.disabled    = false;
      runBtn.textContent = '立即清理';
    }
  });
}

// ===================== 通知设置面板 =====================
async function _initNotifPrefs() {
  // 仅飞书模式有效
  const state = (await window.electronAPI?.authGetState?.()) || {};
  if (state.mode !== 'feishu') {
    const panel = document.getElementById('panel-notif-prefs');
    if (panel) {
      const desc = panel.querySelector('.panel-desc');
      if (desc) desc.textContent = '通知设置仅在飞书登录模式下生效。';
      panel.querySelectorAll('.np-toggle').forEach(cb => { cb.disabled = true; });
    }
    return;
  }

  const res   = await _backendFetch('/api/notifications/prefs');
  const prefs = res?.data || {};

  document.querySelectorAll('.np-toggle').forEach(checkbox => {
    const type = checkbox.dataset.notifType;
    // 默认 true
    checkbox.checked = prefs[type] !== false;

    checkbox.addEventListener('change', async () => {
      checkbox.disabled = true;
      const patch = { [type]: checkbox.checked };
      const r = await _backendFetch('/api/notifications/prefs', {
        method: 'PATCH',
        body: JSON.stringify(patch),
      });
      checkbox.disabled = false;
      const fb = document.getElementById('np-feedback');
      if (fb) {
        fb.textContent = r?.success ? '已保存' : (r?.msg || '保存失败');
        fb.style.color = r?.success ? 'var(--color-green,#a6e3a1)' : 'var(--color-red,#f38ba8)';
        clearTimeout(fb._t);
        fb._t = setTimeout(() => { fb.textContent = ''; }, 2500);
      }
    });
  });
}

// ===================== 清单设置面板 =====================
function _initListDefaults() {
  const select = document.getElementById('cfg-list-row-action');
  if (!select) return;

  // 加载当前设置：优先从 localStorage 读（速度快），初始值 sidebar
  const saved = localStorage.getItem(_lsk('list.row_click_action'));
  if (saved === 'overlay') select.value = 'overlay';
  else select.value = 'sidebar';

  select.addEventListener('change', async () => {
    const val = select.value;
    // 持久化到 localStorage（ListShell 快速读取）
    localStorage.setItem(_lsk('list.row_click_action'), val);
    const fb = document.getElementById('list-defaults-feedback');
    if (fb) {
      fb.textContent = '已保存';
      clearTimeout(fb._t);
      fb._t = setTimeout(() => { fb.textContent = ''; }, 2000);
    }
  });
}

// ===================== 关于 / 卸载面板 =====================
function _initAboutPanel() {
  // 显示版本号
  const verEl = document.getElementById('about-version');
  if (verEl) {
    (window.electronAPI?.getAppVersion?.() || Promise.resolve(null))
      .then(v => { if (verEl) verEl.textContent = v ? `v${v}` : '(开发模式)'; });
  }

  // 卸载按钮
  const btn = document.getElementById('btn-uninstall-app');
  const fb  = document.getElementById('uninstall-feedback');
  if (!btn) return;

  btn.addEventListener('click', async () => {
    const confirmed = await _confirmDialog(
      '确定要卸载 AI00工艺系统吗？\n\n卸载后应用将从本机移除，云端数据不受影响。'
    );
    if (!confirmed) return;

    if (!window.electronAPI?.uninstallApp) {
      if (fb) fb.textContent = '当前环境不支持自动卸载，请在"控制面板 → 程序和功能"中手动卸载。';
      return;
    }

    btn.disabled = true;
    btn.textContent = '正在启动卸载程序…';
    const res = await window.electronAPI.uninstallApp();
    if (res?.success) {
      if (fb) { fb.style.color = 'var(--color-success,#a6e3a1)'; fb.textContent = '卸载程序已启动，应用即将关闭。'; }
    } else {
      btn.disabled = false;
      btn.textContent = '卸载应用…';
      if (fb) fb.textContent = res?.error || '未找到卸载程序，请在"控制面板 → 程序和功能"中手动卸载。';
    }
  });
}

// ===================== 功能开关面板（超管专用） =====================
const _FF_LABELS = {
  rule_engine:   '规则引擎',
  ai_assistant:  'AI 辅助',
  knowledge:     '知识库',
  follows:       '关注功能',
  plugin_system: '插件系统',
};

// 功能开关缓存（供 _applyPermissions 复用，避免重复 bridge 调用）
let _cachedFeatureFlags = null;

async function _initFeatureFlags() {
  // 从后端读取功能开关（存储在 admin/config feature_flags 条目中）
  let flags = {};
  const res = await _backendFetch('/admin/config/feature_flags');
  if (res?.success && res?.data?.value) {
    try { flags = JSON.parse(res.data.value); } catch (_) {}
  }
  _cachedFeatureFlags = flags;  // 缓存供 _applyPermissions 使用

  document.querySelectorAll('[data-flag-key]').forEach(checkbox => {
    const key = checkbox.dataset.flagKey;
    checkbox.checked = flags[key] !== false;

    checkbox.addEventListener('change', async () => {
      checkbox.disabled = true;
      const updated = { ...(_cachedFeatureFlags || {}), [key]: checkbox.checked };
      const r = await _backendFetch('/admin/config/feature_flags', {
        method: 'PUT',
        body: JSON.stringify({ value: JSON.stringify(updated), description: '功能开关' }),
      });
      _cachedFeatureFlags = updated;
      checkbox.disabled = false;
      const fb = document.getElementById('ff-feedback');
      if (fb) {
        const label = _FF_LABELS[key] || key;
        fb.textContent = r?.success
          ? `${label} 已${checkbox.checked ? '开启' : '关闭'}`
          : (r?.msg || '保存失败');
        fb.style.color = r?.success ? 'var(--color-green,#a6e3a1)' : 'var(--color-red,#f38ba8)';
        clearTimeout(fb._t);
        fb._t = setTimeout(() => { fb.textContent = ''; }, 3000);
      }
      try { window.parent?.postMessage?.({ type: 'feature-flags-changed' }, '*'); } catch (_) {}
    });
  });

  // 官方插件单独开关（动态渲染）
  const container = document.getElementById('ff-official-plugins');
  if (!container) return;

  let plugins = [];
  if (window.electronAPI?.listInstalledPlugins) {
    plugins = (await window.electronAPI.listInstalledPlugins()) || [];
  }
  const officialPlugins = plugins.filter(p => p.plugin_source === 'official' || p.category === 'official');
  if (!officialPlugins.length) return;

  const header = document.createElement('div');
  header.className = 'setting-group-title';
  header.style.marginTop = '12px';
  header.textContent = '官方插件';
  container.appendChild(header);

  for (const plugin of officialPlugins) {
    const flagKey = `plugin_official_${plugin.plugin_id}`;
    const row = document.createElement('div');
    row.className = 'setting-item';
    row.innerHTML =
      `<div class="setting-item-info">` +
        `<div class="setting-item-label">${plugin.name}</div>` +
        `<div class="setting-item-desc">${plugin.description || ''}</div>` +
      `</div>` +
      `<label class="toggle-switch">` +
        `<input type="checkbox" data-flag-key="${flagKey}" ${flags[flagKey] !== false ? 'checked' : ''}>` +
        `<span class="toggle-slider"></span>` +
      `</label>`;
    container.appendChild(row);

    const checkbox = row.querySelector('input[type="checkbox"]');
    checkbox.addEventListener('change', async () => {
      checkbox.disabled = true;
      const updated = { ...(_cachedFeatureFlags || {}), [flagKey]: checkbox.checked };
      const r = await _backendFetch('/admin/config/feature_flags', {
        method: 'PUT',
        body: JSON.stringify({ value: JSON.stringify(updated), description: '功能开关' }),
      });
      _cachedFeatureFlags = updated;
      checkbox.disabled = false;
      const fb = document.getElementById('ff-feedback');
      if (fb) {
        fb.textContent = r?.success
          ? `${plugin.name} 已${checkbox.checked ? '启用' : '禁用'}`
          : (r?.msg || '保存失败');
        fb.style.color = r?.success ? 'var(--color-green,#a6e3a1)' : 'var(--color-red,#f38ba8)';
        clearTimeout(fb._t);
        fb._t = setTimeout(() => { fb.textContent = ''; }, 3000);
      }
      try { window.parent?.postMessage?.({ type: 'feature-flags-changed' }, '*'); } catch (_) {}
    });
  }
}

async function _saveUserRole(userGid, btn) {
  const row     = btn.closest('[data-user-gid]');
  const newRole = row.querySelector('[data-field="role"]')?.value || 'member';
  const extSub  = (newRole === 'external' && row.querySelector('[data-field="ext_subtype"]'))
    ? row.querySelector('[data-field="ext_subtype"]').value : null;

  btn.disabled = true;
  btn.textContent = '保存中…';

  const res = await _backendFetch(`/users/${userGid}/role`, {
    method: 'PATCH',
    body: JSON.stringify({ new_role: newRole, external_subtype: extSub }),
  });

  if (res.success) {
    btn.textContent = '✓ 已保存';
    setTimeout(() => { btn.disabled = false; btn.textContent = '保存'; }, 1500);
  } else {
    btn.textContent = '✗ 失败';
    console.warn('[Settings] assign_role 失败:', res.msg);
    setTimeout(() => { btn.disabled = false; btn.textContent = '保存'; }, 2000);
  }
}
