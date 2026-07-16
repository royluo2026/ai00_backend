/**
 * run_tests.js — Node.js / jsdom 测试运行器
 * 运行方式: node web/tests/run_tests.js
 */
'use strict';

const { JSDOM } = require('jsdom');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '../..');

// ── 颜色输出 ─────────────────────────────────────────────────────────
const C = {
  reset: '\x1b[0m', bold: '\x1b[1m',
  green: '\x1b[32m', red: '\x1b[31m', yellow: '\x1b[33m',
  cyan: '\x1b[36m', gray: '\x1b[90m', white: '\x1b[37m',
};
const pass = (s) => `${C.green}✓${C.reset} ${s}`;
const fail = (s, d) => `${C.red}✗${C.reset} ${C.bold}${s}${C.reset}${d ? `\n    ${C.red}${d}${C.reset}` : ''}`;
const section = (s) => `\n${C.cyan}▸ ${s}${C.reset}`;

// ── 测试状态 ──────────────────────────────────────────────────────────
let _passed = 0, _failed = 0;

function _assert(name, condition, detail = '') {
  if (condition) { _passed++; console.log(pass(name)); }
  else           { _failed++; console.log(fail(name, detail)); }
}

async function _assertAsync(name, fn) {
  try { await fn(); _passed++; console.log(pass(name)); }
  catch (e) { _failed++; console.log(fail(name, e.message)); }
}

// ── jsdom 环境工厂 ────────────────────────────────────────────────────
function makeEnv(extraHtml = '') {
  const html = `<!DOCTYPE html><html><body>
    <div id="lvVersionSelect"></div>
    <div id="lvVersionMenu"></div>
    <button id="lvNewVersionBtn"></button>
    <span id="lvVersionLabel"></span>
    ${extraHtml}
  </body></html>`;

  const dom = new JSDOM(html, {
    runScripts: 'dangerously',
    resources: 'usable',
    url: 'http://localhost',
  });
  const { window } = dom;

  // jsdom 没有 KeyboardEvent.dispatchEvent 的 bubbles 支持，补丁
  window.confirm = () => true;

  // 通过 <script> 元素注入脚本（与浏览器行为一致：const/class 声明在后续 eval 中可见）
  const load = (filePath) => {
    const code = fs.readFileSync(path.join(ROOT, filePath), 'utf-8');
    const script = window.document.createElement('script');
    script.textContent = code;
    window.document.head.appendChild(script);
  };

  load('web/shared/lv_utils.js');
  load('packages/craft-plugin/web/lineage_view/lineage_version_mgr.js');

  // 辅助：从脚本作用域读取 const/class 声明（不在 window 上，需通过 eval 访问）
  window._get = (name) => window.eval(name);

  // 将 class 构造函数挂到 window，使测试可用 w.ClassName 直接引用
  window.LineageVersionManager = window.eval('LineageVersionManager');

  return window;
}

function makeTabManagerEnv({ authMode = 'feishu', hasCraftPerm = true } = {}) {
  const dom = new JSDOM('<!DOCTYPE html><html><body><div id="ws-content"></div></body></html>', {
    runScripts: 'dangerously',
    resources: 'usable',
    url: 'http://localhost',
  });
  const { window } = dom;

  const calls = [];
  const tabs = new Map();
  let activeTabId = null;

  window.dbg = { log() {}, warn() {} };
  window._authMode = authMode;
  window._hasTabPerm = (perm) => perm === 'craft.view' ? hasCraftPerm : true;
  window._showToast = () => {};
  window.electronAPI = { _isElectron: false, openSettings() {} };
  window.WorkspaceEngine = {
    init(containerId) {
      calls.push({ type: 'init', containerId });
    },
    addTab(tabId, title, src, opts = {}) {
      tabs.set(tabId, { title, src, opts });
      activeTabId = tabId;
      calls.push({ type: 'addTab', tabId, title, src, opts });
    },
    hasTab(tabId) {
      return tabs.has(tabId);
    },
    activateTab(tabId) {
      activeTabId = tabId;
      calls.push({ type: 'activateTab', tabId });
    },
    activeTabId() {
      return activeTabId;
    },
    closeTab() {},
    findTabIdBySrc() { return null; },
    getTabIframe() { return null; },
  };

  const code = fs.readFileSync(path.join(ROOT, 'web/workspace/tab_manager.js'), 'utf-8');
  const script = window.document.createElement('script');
  script.textContent = code;
  window.document.head.appendChild(script);

  window.__tabCalls = calls;
  window.__tabRecords = tabs;
  window.__activeTabId = () => activeTabId;
  return window;
}

function makeCraftHubConfig() {
  const file = fs.readFileSync(path.join(ROOT, 'packages/craft-plugin/web/craft_hub/index.html'), 'utf-8');
  const match = file.match(/tabs:\s*\[(.*?)\]\s*,\s*tabsEl:/s);
  if (!match) throw new Error('未找到 craft_hub tabs 配置');
  return Function(`return [${match[1]}];`)();
}

function readLineageSource() {
  return fs.readFileSync(path.join(ROOT, 'packages/craft-plugin/web/lineage_view/lineage.js'), 'utf-8');
}

function readLineageHtml() {
  return fs.readFileSync(path.join(ROOT, 'packages/craft-plugin/web/lineage_view/index.html'), 'utf-8');
}

function makeLineageDialogEnv() {
  const dom = new JSDOM('<!DOCTYPE html><html><body></body></html>', {
    runScripts: 'dangerously',
    resources: 'usable',
    url: 'http://localhost',
  });
  const { window } = dom;
  window.console = console;
  window.setTimeout = setTimeout;
  window.clearTimeout = clearTimeout;
  window.FileReader = class {};
  window._cloudFetch = async () => ({ data: [] });
  const load = (filePath) => {
    const code = fs.readFileSync(path.join(ROOT, filePath), 'utf-8');
    const script = window.document.createElement('script');
    script.textContent = code;
    window.document.head.appendChild(script);
  };
  load('web/shared/lv_utils.js');
  load('packages/craft-plugin/web/lineage_view/lineage.js');
  window.eval(`
    window.__lineageDialogHooks = {
      openNodeDialog: _openNodeDialog,
      setRowByGid(map) { _rowByGid = map; },
      setChildMap(map) { _childMap = map; },
      setVersionGid(v) { _versionGid = v; },
      setCanEditEntry(fn) { _canEditEntry = fn; }
    };
  `);
  return window;
}

function makeLayoutDetailPanelEnv() {
  const dom = new JSDOM(`<!DOCTYPE html><html><body>
    <div id="llDetailPanel">
      <div id="llDpResizeHandle"></div>
      <div id="llDpHandleBar"></div>
      <div id="llDpTree"></div>
      <div id="llDpTreeBody"></div>
      <div id="llDpVerSlot"></div>
      <div id="llDpLineSlot"></div>
      <input id="llDpSearchInp">
      <div id="llDpProps"><div id="llDpPropsBody"></div></div>
      <div id="llDpRels"><div id="llDpRelsBody"></div></div>
      <div id="llDpDetail"><div id="llDpDetailBody"></div></div>
      <div id="llDpKnow"><div id="llDpKnowBody"></div></div>
      <button id="llDpKnowAdd"></button>
    </div>
    <button id="lvDetailPanelToggle"></button>
  </body></html>`, {
    runScripts: 'dangerously',
    resources: 'usable',
    url: 'http://localhost',
  });
  const { window } = dom;
  window.console = console;
  window.requestAnimationFrame = (cb) => setTimeout(cb, 0);
  window.cancelAnimationFrame = (id) => clearTimeout(id);
  const code = fs.readFileSync(path.join(ROOT, 'packages/craft-plugin/web/lineage_view/layout_detail_panel.js'), 'utf-8');
  const script = window.document.createElement('script');
  script.textContent = `${code}\nwindow.LayoutDetailPanel = LayoutDetailPanel;`;
  window.document.head.appendChild(script);
  return window;
}

function makeLayoutModeEnv() {
  const dom = new JSDOM(`<!DOCTYPE html><html><body>
    <div id="lvLayoutCanvas">
      <div id="llViewport"></div>
      <div id="llWorld"></div>
      <div id="llZoomPct"></div>
      <div id="llMinimap" class="collapsed"><button id="llMinimapToggle"></button><div id="llMinimapBody"></div></div>
    </div>
  </body></html>`, {
    runScripts: 'dangerously',
    resources: 'usable',
    url: 'http://localhost',
  });
  const { window } = dom;
  window.console = console;
  window._cf = async () => ({ data: {} });
  const code = fs.readFileSync(path.join(ROOT, 'packages/craft-plugin/web/lineage_view/layout_mode.js'), 'utf-8');
  const script = window.document.createElement('script');
  script.textContent = `${code}\nwindow.LayoutMode = LayoutMode;`;
  window.document.head.appendChild(script);
  return window;
}

function makeSettingsEnv() {
  const html = `<!DOCTYPE html><html><body>
    <div class="settings-nav"><div class="nav-item active" data-panel="appearance"></div></div>
    <div id="panel-appearance" class="settings-panel active"></div>
    <div id="panel-database" class="settings-panel"></div>
    <div id="panel-file-store" class="settings-panel"></div>
    <div id="panel-feishu" class="settings-panel"></div>
    <div id="panel-plugin-market" class="settings-panel"></div>
    <div id="panel-user-management" class="settings-panel"></div>
    <div id="panel-feature-flags" class="settings-panel"></div>
    <div id="panel-notif-prefs" class="settings-panel"></div>
    <div id="panel-list-defaults" class="settings-panel"></div>
    <div id="panel-about" class="settings-panel"></div>
    <div id="panel-follows-cleanup" class="settings-panel"></div>
    <div id="shortcut-list"></div><button id="btn-reset-shortcuts"></button>
    <select id="cfg-language"><option value="zh_CN">zh_CN</option></select><select id="cfg-log-level"><option value="INFO">INFO</option></select><input id="cfg-window-max" type="checkbox"><input id="cfg-auto-backup" type="checkbox"><input id="cfg-backend-url"><div id="backend-url-feedback"></div><button id="btn-save-backend-url"></button>
    <input id="local-db-path-input"><button id="btn-browse-local-db"></button><button id="btn-save-local-db"></button><button id="btn-test-local-db"></button><div id="local-db-feedback"></div><div id="local-db-result"></div>
    <input id="pg-host"><input id="pg-port"><input id="pg-user"><input id="pg-password"><input id="pg-collab-db"><input id="pg-public-db"><button id="btn-save-pg"></button><button id="btn-test-pg"></button><div id="pg-feedback"></div><div id="pg-result"></div>
    <button id="btn-save-minio"></button><button id="btn-test-minio"></button><div id="minio-feedback"></div><div id="minio-result"></div>
    <button id="btn-save-ois"></button><button id="btn-test-ois"></button><div id="ois-feedback"></div><div id="ois-result"></div>
    <input id="feishu-app-id"><input id="feishu-app-secret"><button id="btn-save-feishu-creds"></button><div id="feishu-creds-feedback"></div><div id="feishu-user-name"></div><div id="feishu-user-email"></div><img id="feishu-avatar"><div id="feishu-avatar-placeholder"></div><button id="btn-feishu-login"></button><button id="btn-feishu-logout"></button><div id="feishu-login-feedback"></div>
    <div id="pm-installed-list"></div><div id="pm-pane-installed"></div><div id="pm-pane-market"></div><input id="pm-install-url"><button id="pm-btn-install-url"></button><div id="pm-install-feedback"></div><input id="pm-registry-url"><button id="pm-btn-refresh-market"></button><input id="pm-market-search"><div id="pm-market-list"></div>
    <div id="installed-plugin-nav"></div><div id="installed-plugin-panels"></div>
    <div id="ff-official-plugins"></div><div id="ff-feedback"></div>
    <div id="user-list-container"></div><input id="user-search-input"><button id="btn-refresh-users"></button>
    <input id="fc-rule-task" type="checkbox"><input id="fc-rule-issue" type="checkbox"><input id="fc-rule-knowledge-days"><button id="fc-btn-run"></button><div id="fc-result"></div>
    <select id="cfg-list-row-action"><option value="sidebar">sidebar</option><option value="overlay">overlay</option></select><div id="list-defaults-feedback"></div>
    <div id="about-version"></div><button id="btn-uninstall-app"></button><div id="uninstall-feedback"></div>
  </body></html>`;

  const dom = new JSDOM(html, {
    runScripts: 'dangerously',
    resources: 'usable',
    url: 'http://localhost/web/settings/index.html',
  });
  const { window } = dom;
  const calls = [];

  window.fetch = async () => ({ ok: true, status: 200, json: async () => ({}) });
  window.console = console;
  window.localStorage.clear();
  window.parent = window;
  window.top = window;
  window.confirm = () => true;
  window.AI00RuntimeConfig = { getRuntimeBackendBase: async () => 'http://127.0.0.1:8081' };
  window.electronAPI = {
    getConfig: async () => ({ backendUrl: 'http://127.0.0.1:8081', version: 'test' }),
    authGetState: async () => ({ mode: 'feishu', token: 'a.b.c', user: { gid: 'u1', system_role: 'super_admin', org_role: 'super_admin' } }),
    listShortcuts: async () => ({ keys: {} }),
    onAuthStateChanged() {},
    onThemeChanged() {},
    broadcastTheme() {},
    getAppVersion: async () => 'test',
    getPluginRegistry: async () => ({ plugins: [] }),
    listInstalledPlugins: async () => [],
    onPluginRegistryUpdated() {},
  };

  const script = fs.readFileSync(path.join(ROOT, 'web/settings/settings.js'), 'utf-8');
  window.eval(`${script}\nwindow.__settingsTestHooks = {\n  _start,\n  _backendFetch,\n  _initDatabase,\n  _initFileStore,\n  _initFeishu,\n  _initPluginMarket,\n  _initInstalledPlugins,\n  _initFeatureFlags,\n  _initNotifPrefs,\n  _initUserManagement,\n  _initFollowsCleanup\n};`);

  const hooks = window.__settingsTestHooks;
  const originalBackendFetch = hooks._backendFetch;
  hooks._backendFetch = async (path, opts = {}) => {
    calls.push({ path, method: opts.method || 'GET' });
    return originalBackendFetch(path, opts);
  };
  window.eval('_backendFetch = window.__settingsTestHooks._backendFetch;');

  return { window, calls, hooks };
}

function makeLifecyclePanelEnv() {
  const dom = new JSDOM('<!DOCTYPE html><html><body><div id="mount"></div><div id="action"></div><input id="lv-tc-ver-name"><input id="lv-inp-tc-file"><div id="lv-tc-s1-status"></div><button id="lv-tc-next"></button><button id="lv-tc-confirm"></button><div id="lv-modal-import-tc" class="hidden"></div></body></html>', {
    runScripts: 'dangerously',
    resources: 'usable',
    url: 'http://localhost',
  });
  const { window } = dom;
  window.console = console;
  window.confirm = () => true;
  const code = fs.readFileSync(path.join(ROOT, 'packages/craft-plugin/web/lineage_view/lifecycle_panel.js'), 'utf-8');
  const script = window.document.createElement('script');
  script.textContent = `${code}\nwindow.BopLifecyclePanel = BopLifecyclePanel;`;
  window.document.head.appendChild(script);
  return window;
}

// ════════════════════════════════════════════════════════════════════
// 测试套件
// ════════════════════════════════════════════════════════════════════

async function runTests() {

  // ── 1. _escHtml ───────────────────────────────────────────────────
  console.log(section('lv_utils: _escHtml'));
  const w1 = makeEnv();
  const { _escHtml } = w1;

  _assert('函数存在', typeof _escHtml === 'function');
  _assert('转义 <', _escHtml('<div>') === '&lt;div&gt;');
  _assert('转义 >', _escHtml('a>b') === 'a&gt;b');
  _assert('转义 &', _escHtml('a&b') === 'a&amp;b');
  _assert('转义 "', _escHtml('"hi"') === '&quot;hi&quot;');
  _assert('不转义单引号', _escHtml("it's") === "it's");
  _assert('数字输入', _escHtml(42) === '42');
  _assert('空字符串', _escHtml('') === '');
  _assert('无需转义时不变', _escHtml('hello world') === 'hello world');
  _assert('复合：<a href="x&y">', _escHtml('<a href="x&y">') === '&lt;a href=&quot;x&amp;y&quot;&gt;');
  _assert('null 转字符串', _escHtml(null) === 'null');

  // ── 2. _promptText ────────────────────────────────────────────────
  console.log(section('lv_utils: _promptText'));
  // 每个对话框测试用独立 window，避免残留 DOM 互相干扰
  {
    const w = makeEnv();
    _assert('函数存在', typeof w._promptText === 'function');
    _assert('返回 Promise', w._promptText('x') instanceof w.Promise);
    w.document.querySelectorAll('.lv-dialog-overlay').forEach(el => el.remove());
  }

  await _assertAsync('确认：返回 {title, nodeType:null}', async () => {
    const w = makeEnv();
    const p = w._promptText('请输入');
    const overlay = w.document.querySelector('.lv-dialog-overlay');
    if (!overlay) throw new Error('未找到 .lv-dialog-overlay');
    const input = overlay.querySelector('#_dlgInput');
    if (!input) throw new Error('未找到 #_dlgInput');
    if (!overlay.textContent.includes('请输入')) throw new Error('消息文本缺失');
    input.value = '新节点';
    overlay.querySelector('#_dlgOk').click();
    const r = await p;
    if (!r || r.title !== '新节点') throw new Error('title 错误: ' + JSON.stringify(r));
    if (r.nodeType !== null) throw new Error('nodeType 应为 null: ' + r.nodeType);
  });

  await _assertAsync('取消按钮返回 null', async () => {
    const w = makeEnv();
    const p = w._promptText('取消测试');
    w.document.querySelector('#_dlgCancel').click();
    const r = await p;
    if (r !== null) throw new Error('应返回 null: ' + JSON.stringify(r));
  });

  await _assertAsync('空标题点确认不关闭对话框', async () => {
    const w = makeEnv();
    const p = w._promptText('空标题');
    const input = w.document.querySelector('#_dlgInput');
    input.value = '';
    w.document.querySelector('#_dlgOk').click();
    if (!w.document.querySelector('.lv-dialog-overlay'))
      throw new Error('对话框不应关闭');
    // 补充有效输入后关闭
    input.value = '有效';
    w.document.querySelector('#_dlgOk').click();
    await p;
  });

  await _assertAsync('ESC 键返回 null', async () => {
    const w = makeEnv();
    const p = w._promptText('ESC 测试');
    const overlay = w.document.querySelector('.lv-dialog-overlay');
    overlay.dispatchEvent(new w.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    const r = await p;
    if (r !== null) throw new Error('应返回 null: ' + JSON.stringify(r));
  });

  await _assertAsync('Enter 键确认（有文本）', async () => {
    const w = makeEnv();
    const p = w._promptText('Enter 测试');
    const overlay = w.document.querySelector('.lv-dialog-overlay');
    const input = overlay.querySelector('#_dlgInput');
    input.value = 'Enter节点';
    overlay.dispatchEvent(new w.KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    const r = await p;
    if (!r || r.title !== 'Enter节点') throw new Error('title 错误: ' + JSON.stringify(r));
  });

  await _assertAsync('nodeTypes 参数：显示 select，返回选中 nodeType', async () => {
    const w = makeEnv();
    const types = [['line_process', '线体工艺'], ['station_process', '工位工艺']];
    const p = w._promptText('选择', { nodeTypes: types });
    const select = w.document.querySelector('#_dlgNodeType');
    if (!select) throw new Error('应出现 #_dlgNodeType select');
    if (select.options.length !== 2) throw new Error('选项数错误: ' + select.options.length);
    w.document.querySelector('#_dlgInput').value = '测试';
    select.value = 'station_process';
    w.document.querySelector('#_dlgOk').click();
    const r = await p;
    if (r.nodeType !== 'station_process') throw new Error('nodeType 错误: ' + r.nodeType);
  });

  // ── 3. _confirmDialog ─────────────────────────────────────────────
  console.log(section('lv_utils: _confirmDialog'));
  {
    const w = makeEnv();
    _assert('函数存在', typeof w._confirmDialog === 'function');
  }

  await _assertAsync('确认返回 true', async () => {
    const w = makeEnv();
    const p = w._confirmDialog('确定删除？');
    const overlay = w.document.querySelector('.lv-dialog-overlay');
    if (!overlay) throw new Error('未找到 overlay');
    if (!overlay.textContent.includes('确定删除')) throw new Error('消息文本缺失');
    overlay.querySelector('#_dlgOk').click();
    const r = await p;
    if (r !== true) throw new Error('应返回 true: ' + r);
  });

  await _assertAsync('取消返回 false', async () => {
    const w = makeEnv();
    const p = w._confirmDialog('测试');
    w.document.querySelector('#_dlgCancel').click();
    const r = await p;
    if (r !== false) throw new Error('应返回 false: ' + r);
  });

  await _assertAsync('ESC 键返回 false', async () => {
    const w = makeEnv();
    const p = w._confirmDialog('ESC');
    const overlay = w.document.querySelector('.lv-dialog-overlay');
    overlay.dispatchEvent(new w.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    const r = await p;
    if (r !== false) throw new Error('应返回 false: ' + r);
  });

  await _assertAsync('Enter 键返回 true', async () => {
    const w = makeEnv();
    const p = w._confirmDialog('Enter');
    const overlay = w.document.querySelector('.lv-dialog-overlay');
    overlay.dispatchEvent(new w.KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    const r = await p;
    if (r !== true) throw new Error('应返回 true: ' + r);
  });

  // ── 4. _openImageLightbox ─────────────────────────────────────────
  console.log(section('lv_utils: _openImageLightbox'));
  {
    const w = makeEnv();
    _assert('函数存在', typeof w._openImageLightbox === 'function');
    _assert('空数组不抛出', (() => { try { w._openImageLightbox([]); return true; } catch { return false; } })());
    _assert('null 不抛出', (() => { try { w._openImageLightbox(null); return true; } catch { return false; } })());
  }

  const PX = 'data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7';

  _assert('单图：创建 overlay', (() => {
    const w = makeEnv();
    w._openImageLightbox([PX]);
    return !!w.document.body.querySelector('div[style*="99999"]');
  })());

  _assert('单图：overlay 含 img 并含 src', (() => {
    const w = makeEnv();
    w._openImageLightbox([PX]);
    const img = w.document.body.querySelector('div[style*="99999"] img');
    return !!img && img.src === PX;
  })());

  _assert('多图：grid container 含3个子项', (() => {
    const w = makeEnv();
    w._openImageLightbox([PX, PX, PX]);
    const overlay = w.document.body.querySelector('div[style*="99999"]');
    const grid = overlay?.querySelector('div[style*="flex-wrap"]');
    return !!grid && grid.children.length === 3;
  })());

  // ── 5. _STATUS_COLORS ─────────────────────────────────────────────
  console.log(section('lineage_version_mgr: 全局常量'));
  const wC = makeEnv();
  const SC = wC._get('_STATUS_COLORS');
  const TCT = wC._get('_TC_TYPE_MAP');
  const TCC = wC._get('_TC_COL_MAP');
  const TCD = wC._get('_TC_FIELD_DEFS');
  _assert('_STATUS_COLORS 存在', typeof SC === 'object' && SC !== null);
  _assert('active.label = "活动"', SC?.active?.label === '活动');
  _assert('active.bg = "#40a02b"', SC?.active?.bg === '#40a02b');
  _assert('baseline.label = "基线"', SC?.baseline?.label === '基线');
  _assert('M.label = "发布"', SC?.M?.label === '发布');
  _assert('archived.label = "归档"', SC?.archived?.label === '归档');
  _assert('共4种状态', Object.keys(SC).length === 4);

  _assert('_TC_TYPE_MAP 存在', typeof TCT === 'object');
  _assert('Line Process → line_process', TCT['Line Process'] === 'line_process');
  _assert('Station Process → station_process', TCT['Station Process'] === 'station_process');
  _assert('Operator Process → operator_process', TCT['Operator Process'] === 'operator_process');
  _assert('Process → process', TCT['Process'] === 'process');
  _assert('Operation → operation', TCT['Operation'] === 'operation');
  _assert('中文"工位" → station_process', TCT['工位'] === 'station_process');
  _assert('中文"工序" → process', TCT['工序'] === 'process');

  _assert('_TC_COL_MAP 存在', typeof TCC === 'object');
  _assert('Level → _level', TCC['Level'] === '_level');
  _assert('Name → title', TCC['Name'] === 'title');
  _assert('VPPS → vpps', TCC['VPPS'] === 'vpps');

  _assert('_TC_FIELD_DEFS 是数组', Array.isArray(TCD));
  _assert('title 字段必填', TCD?.some(f => f.key === 'title' && f.required));
  _assert('_level 字段必填', TCD?.some(f => f.key === '_level' && f.required));

  // ── 6. LineageVersionManager 构造 ────────────────────────────────
  console.log(section('LineageVersionManager: 构造与初始状态'));
  const w6 = makeEnv();
  const mockCf = async () => ({ data: [] });
  const mockToast = () => {};
  const mgr = new w6.LineageVersionManager({
    cf: mockCf, toast: mockToast,
    onVersionSelected: () => {}, onStatusChange: () => {}, onReloadNeeded: () => {},
  });

  _assert('instanceof 正确', mgr instanceof w6.LineageVersionManager);
  _assert('allVersions 初始为空数组', Array.isArray(mgr.allVersions) && mgr.allVersions.length === 0);
  _assert('currentVersionGid 初始为 null', mgr.currentVersionGid === null);
  _assert('currentVersionStatus 初始为 "active"', mgr.currentVersionStatus === 'active');

  // ── 7. 公开方法存在性 ─────────────────────────────────────────────
  console.log(section('LineageVersionManager: 公开方法'));
  const methods = [
    'loadVersions','renderMenu','toggleMenu','selectVersion','initPicker',
    'freeze','unfreeze','publish','archiveFamily','unarchiveFamily',
    'openForkModal','openCreateModal','openImportTcModal','openImportGbopModal',
  ];
  for (const m of methods) {
    _assert(`${m}() 存在`, typeof mgr[m] === 'function');
  }

  // ── 8. loadVersions ───────────────────────────────────────────────
  console.log(section('LineageVersionManager: loadVersions'));
  const VERSIONS = [
    { gid: 'v001', bop_name: 'TestBOP', version_tag: 'v1', status: 'active',
      version_family_gid: 'f001', archived_at: null, frozen_at: null },
    { gid: 'v002', bop_name: 'TestBOP', version_tag: 'v2', status: 'baseline',
      version_family_gid: 'f001', archived_at: null, frozen_at: '2026-01-01' },
  ];
  const wLoad = makeEnv();
  const mgrLoad = new wLoad.LineageVersionManager({
    cf: async () => ({ data: VERSIONS }), toast: mockToast,
    onVersionSelected: () => {}, onStatusChange: () => {}, onReloadNeeded: () => {},
  });
  await mgrLoad.loadVersions();
  _assert('allVersions 填充 2 项', mgrLoad.allVersions.length === 2);
  _assert('allVersions[0].gid = v001', mgrLoad.allVersions[0].gid === 'v001');

  // API 失败：不抛出，而是 toast error
  const toastCalls = [];
  const wFail = makeEnv();
  const mgrFail = new wFail.LineageVersionManager({
    cf: async () => { throw new Error('网络错误'); },
    toast: (msg, type) => toastCalls.push({ msg, type }),
    onVersionSelected: () => {}, onStatusChange: () => {}, onReloadNeeded: () => {},
  });
  await mgrFail.loadVersions();
  _assert('API 失败时 toast error（不抛出）', toastCalls.some(t => t.type === 'error'));

  // ── 9. selectVersion ──────────────────────────────────────────────
  console.log(section('LineageVersionManager: selectVersion'));
  const selectedEvts = [];
  const wSel = makeEnv();
  const mgrSel = new wSel.LineageVersionManager({
    cf: mockCf, toast: mockToast,
    onVersionSelected: (gid, tag) => selectedEvts.push({ gid, tag }),
    onStatusChange: () => {}, onReloadNeeded: () => {},
  });
  mgrSel.selectVersion('v001', 'v1');
  _assert('currentVersionGid 更新', mgrSel.currentVersionGid === 'v001');
  _assert('onVersionSelected 回调触发', selectedEvts.length === 1);
  _assert('回调携带正确 gid', selectedEvts[0].gid === 'v001');
  _assert('回调携带正确 tag', selectedEvts[0].tag === 'v1');

  // ── 10. 生命周期 API ──────────────────────────────────────────────
  console.log(section('LineageVersionManager: 生命周期 API'));

  // freeze
  const freezeCalls = [], statusChanges = [];
  const wFreeze = makeEnv();
  const mgrFreeze = new wFreeze.LineageVersionManager({
    cf: async (url, opts) => { freezeCalls.push({ url, opts }); return { data: { status: 'baseline' } }; },
    toast: mockToast,
    onVersionSelected: () => {},
    onStatusChange: s => statusChanges.push(s),
    onReloadNeeded: () => {},
  });
  mgrFreeze.currentVersionGid = 'v001';
  await mgrFreeze.freeze('v001');
  _assert('freeze: URL 正确', freezeCalls.some(c => c.url === '/api/bop/versions/v001/freeze'));
  _assert('freeze: method=POST', freezeCalls.some(c => c.opts?.method === 'POST'));
  _assert('freeze: status → baseline', mgrFreeze.currentVersionStatus === 'baseline');
  _assert('freeze: onStatusChange("baseline") 触发', statusChanges.includes('baseline'));

  // unfreeze
  const unfreezeCalls = [];
  const wUnfreeze = makeEnv();
  const mgrUnfreeze = new wUnfreeze.LineageVersionManager({
    cf: async (url, opts) => { unfreezeCalls.push({ url, opts }); return { data: { status: 'active' } }; },
    toast: mockToast, onVersionSelected: () => {}, onStatusChange: () => {}, onReloadNeeded: () => {},
  });
  mgrUnfreeze.currentVersionGid = 'v001';
  await mgrUnfreeze.unfreeze('v001');
  _assert('unfreeze: URL 正确', unfreezeCalls.some(c => c.url === '/api/bop/versions/v001/unfreeze'));
  _assert('unfreeze: method=POST', unfreezeCalls.some(c => c.opts?.method === 'POST'));
  _assert('unfreeze: status → active', mgrUnfreeze.currentVersionStatus === 'active');

  // publish
  const publishCalls = [];
  const wPublish = makeEnv();
  const mgrPublish = new wPublish.LineageVersionManager({
    cf: async (url, opts) => { publishCalls.push({ url, opts }); return { data: { status: 'M' } }; },
    toast: mockToast, onVersionSelected: () => {}, onStatusChange: () => {}, onReloadNeeded: () => {},
  });
  mgrPublish.currentVersionGid = 'v001';
  await mgrPublish.publish('v001');
  _assert('publish: URL 正确', publishCalls.some(c => c.url === '/api/bop/versions/v001/publish'));
  _assert('publish: method=POST', publishCalls.some(c => c.opts?.method === 'POST'));
  _assert('publish: status → M', mgrPublish.currentVersionStatus === 'M');

  // ── 11. archiveFamily / unarchiveFamily ───────────────────────────
  console.log(section('LineageVersionManager: archiveFamily / unarchiveFamily'));

  const archiveCalls = [];
  const wArchive = makeEnv();
  wArchive.confirm = () => true;
  const mgrArchive = new wArchive.LineageVersionManager({
    cf: async (url, opts) => { archiveCalls.push({ url, opts }); return {}; },
    toast: mockToast, onVersionSelected: () => {}, onStatusChange: () => {}, onReloadNeeded: () => {},
  });
  await mgrArchive.archiveFamily('f001');
  _assert('archiveFamily: URL 正确', archiveCalls.some(c => c.url === '/api/bop/version-families/f001/archive'));
  _assert('archiveFamily: method=POST', archiveCalls.some(c => c.opts?.method === 'POST'));

  // 用户取消确认 → 不发请求
  const archiveCancelCalls = [];
  const wArchiveNo = makeEnv();
  wArchiveNo.confirm = () => false;
  const mgrArchiveNo = new wArchiveNo.LineageVersionManager({
    cf: async (url) => { archiveCancelCalls.push(url); return {}; },
    toast: mockToast, onVersionSelected: () => {}, onStatusChange: () => {}, onReloadNeeded: () => {},
  });
  await mgrArchiveNo.archiveFamily('f001');
  _assert('archiveFamily 取消后不发 API', archiveCancelCalls.length === 0);

  const unarchiveCalls = [];
  const wUnarchive = makeEnv();
  const mgrUnarchive = new wUnarchive.LineageVersionManager({
    cf: async (url, opts) => { unarchiveCalls.push({ url, opts }); return {}; },
    toast: mockToast, onVersionSelected: () => {}, onStatusChange: () => {}, onReloadNeeded: () => {},
  });
  await mgrUnarchive.unarchiveFamily('f001');
  _assert('unarchiveFamily: URL 正确', unarchiveCalls.some(c => c.url === '/api/bop/version-families/f001/archive'));
  _assert('unarchiveFamily: method=DELETE', unarchiveCalls.some(c => c.opts?.method === 'DELETE'));

  // ── 12. renderMenu DOM 输出 ───────────────────────────────────────
  console.log(section('LineageVersionManager: renderMenu'));

  const wMenu = makeEnv();
  const mgrMenu = new wMenu.LineageVersionManager({
    cf: async () => ({ data: VERSIONS }), toast: mockToast,
    onVersionSelected: () => {}, onStatusChange: () => {}, onReloadNeeded: () => {},
  });
  await mgrMenu.loadVersions();
  mgrMenu.renderMenu();
  const $menu = wMenu.document.getElementById('lvVersionMenu');
  _assert('填充 lvVersionMenu', $menu.innerHTML.trim() !== '');
  _assert('包含 .lv-vp-fam-hdr', !!$menu.querySelector('.lv-vp-fam-hdr'));
  _assert('版本项数量 = 2', $menu.querySelectorAll('.lv-vp-ver-item').length === 2);
  _assert('v1 tag 出现', $menu.textContent.includes('v1'));
  _assert('baseline 状态标签出现', $menu.textContent.includes('基线'));

  // 空版本
  const wEmpty = makeEnv();
  const mgrEmpty = new wEmpty.LineageVersionManager({
    cf: async () => ({ data: [] }), toast: mockToast,
    onVersionSelected: () => {}, onStatusChange: () => {}, onReloadNeeded: () => {},
  });
  await mgrEmpty.loadVersions();
  mgrEmpty.renderMenu();
  _assert('空版本时显示"暂无版本"', wEmpty.document.getElementById('lvVersionMenu').textContent.includes('暂无版本'));

  // ── 13. onReloadNeeded 默认 no-op ─────────────────────────────────
  console.log(section('LineageVersionManager: 依赖注入防御性'));

  _assert('省略 onReloadNeeded 不抛', (() => {
    try {
      const wD = makeEnv();
      const m = new wD.LineageVersionManager({
        cf: mockCf, toast: mockToast,
        onVersionSelected: () => {}, onStatusChange: () => {},
      });
      m._onReloadNeeded();
      return true;
    } catch { return false; }
  })());

  // ── 14. TabManager craft_hub startup fallback ─────────────────────
  console.log(section('TabManager: craft_hub startup fallback'));

  await _assertAsync('启动时为 craft 用户先打开工艺规划并最终激活它', async () => {
    const w = makeTabManagerEnv({ authMode: 'feishu', hasCraftPerm: true });
    w.TabManager.boot();
    const calls = w.__tabCalls;
    const addTabCalls = calls.filter(c => c.type === 'addTab');
    if (addTabCalls.length !== 2) throw new Error('应新增 2 个默认 tab，实际: ' + addTabCalls.length);
    if (addTabCalls[0].tabId !== 'craft_hub') throw new Error('第一个 tab 应为 craft_hub: ' + addTabCalls[0].tabId);
    if (addTabCalls[1].tabId !== 'workbench') throw new Error('第二个 tab 应为 workbench: ' + addTabCalls[1].tabId);
    const craft = w.__tabRecords.get('craft_hub');
    if (!craft) throw new Error('未记录 craft_hub tab');
    if (craft.src !== '../packages/craft-plugin/web/craft_hub/index.html') {
      throw new Error('craft_hub src 未指向插件页面: ' + craft.src);
    }
    const activateCalls = calls.filter(c => c.type === 'activateTab');
    if (!activateCalls.some(c => c.tabId === 'craft_hub')) throw new Error('未重新激活 craft_hub');
    if (w.__activeTabId() !== 'craft_hub') throw new Error('最终激活 tab 应为 craft_hub: ' + w.__activeTabId());
  });

  await _assertAsync('无工艺权限时启动回退 welcome', async () => {
    const w = makeTabManagerEnv({ authMode: 'none', hasCraftPerm: false });
    w.TabManager.boot();
    const addTabCalls = w.__tabCalls.filter(c => c.type === 'addTab');
    if (addTabCalls.length !== 1) throw new Error('应只新增 welcome tab，实际: ' + addTabCalls.length);
    if (addTabCalls[0].tabId !== 'welcome') throw new Error('应回退到 welcome: ' + addTabCalls[0].tabId);
    if (w.__tabCalls.some(c => c.tabId === 'craft_hub')) throw new Error('无权限时不应打开 craft_hub');
  });

  await _assertAsync('工艺规划 tab 定义存在插件 fallback 路径', async () => {
    const w = makeTabManagerEnv({ authMode: 'feishu', hasCraftPerm: true });
    w.TabManager.open('craft_hub');
    const craft = w.__tabRecords.get('craft_hub');
    if (!craft) throw new Error('open(craft_hub) 未创建 tab');
    if (!String(craft.src || '').includes('../packages/craft-plugin/web/craft_hub/index.html')) {
      throw new Error('craft_hub 未使用插件 fallback 路径: ' + craft.src);
    }
  });

  // ── 15. craft_hub tab visibility + lineage toolbar default state ─────
  console.log(section('craft_hub: visible tabs and lineage toolbar default'));

  await _assertAsync('craft_hub 仅保留工艺流程图和工艺交付物', async () => {
    const tabs = makeCraftHubConfig();
    const keys = tabs.map(t => t.key);
    if (keys.includes('pbom')) throw new Error('pbom 不应继续显示');
    if (keys.includes('bop_nav')) throw new Error('bop_nav 不应继续显示');
    if (!keys.includes('bop_lineage')) throw new Error('缺少 bop_lineage');
    if (!keys.includes('deliverables')) throw new Error('缺少 deliverables');
    if (keys.length !== 2) throw new Error('可见 tab 数量应为 2，实际: ' + keys.length);
  });

  await _assertAsync('lineage 工具栏默认展开', async () => {
    const src = readLineageSource();
    if (!src.includes('let _toolbarOpen    = true;')) {
      throw new Error('lineage.js 未将 _toolbarOpen 默认设为 true');
    }
  });

  await _assertAsync('lineage 页面初始 toolbar 不带隐藏类', async () => {
    const html = readLineageHtml();
    if (!html.includes('class="lv-toolbar" id="lvToolbar"')) {
      throw new Error('未找到默认展开的 toolbar 标记');
    }
    if (html.includes('class="lv-toolbar lv-tb-hidden" id="lvToolbar"')) {
      throw new Error('toolbar 仍然默认隐藏');
    }
  });

  // ── 16. plugin-backed app entry fallbacks ──────────────────────────
  console.log(section('TabManager: plugin-backed app entry fallbacks'));

  await _assertAsync('project_hub fallback 可直接打开', async () => {
    const w = makeTabManagerEnv({ authMode: 'feishu', hasCraftPerm: true });
    w.TabManager.open('project_hub');
    const tab = w.__tabRecords.get('project_hub');
    if (!tab) throw new Error('project_hub 未创建 tab');
    if (!String(tab.src || '').includes('../packages/craft-plugin/web/project_hub/index.html')) {
      throw new Error('project_hub fallback 路径错误: ' + tab.src);
    }
  });

  await _assertAsync('automation_hub fallback 可直接打开', async () => {
    const w = makeTabManagerEnv({ authMode: 'feishu', hasCraftPerm: true });
    w.TabManager.open('automation_hub');
    const tab = w.__tabRecords.get('automation_hub');
    if (!tab) throw new Error('automation_hub 未创建 tab');
    if (!String(tab.src || '').includes('../packages/agent-plugin/web/automation_hub/index.html')) {
      throw new Error('automation_hub fallback 路径错误: ' + tab.src);
    }
  });

  await _assertAsync('ai_chat fallback 可直接打开', async () => {
    const w = makeTabManagerEnv({ authMode: 'feishu', hasCraftPerm: true });
    w.TabManager.open('ai_chat');
    const tab = w.__tabRecords.get('ai_chat');
    if (!tab) throw new Error('ai_chat 未创建 tab');
    if (!String(tab.src || '').includes('../packages/agent-plugin/web/ai_chat/index.html')) {
      throw new Error('ai_chat fallback 路径错误: ' + tab.src);
    }
  });

  await _assertAsync('wfc_canvas fallback 可直接打开', async () => {
    const w = makeTabManagerEnv({ authMode: 'feishu', hasCraftPerm: true });
    w.TabManager.open('wfc_canvas');
    const tab = w.__tabRecords.get('wfc_canvas');
    if (!tab) throw new Error('wfc_canvas 未创建 tab');
    if (!String(tab.src || '').includes('../packages/agent-plugin/web/wfc_window/index.html')) {
      throw new Error('wfc_canvas fallback 路径错误: ' + tab.src);
    }
  });

  await _assertAsync('settings 启动时仅自动初始化数据库相关分区', async () => {
    const { hooks, calls } = makeSettingsEnv();
    await hooks._start();
    const paths = calls.map(c => c.path);
    if (!paths.includes('/admin/cloud-db-config')) {
      throw new Error('缺少数据库配置读取请求: ' + JSON.stringify(paths));
    }
    const forbidden = [
      '/admin/config/FEISHU_APP_ID',
      '/admin/config/feature_flags',
      '/users/',
      '/api/notifications/prefs',
      '/api/follows',
    ].filter(path => paths.includes(path));
    if (forbidden.length) {
      throw new Error('不应在启动时触发 DB 依赖接口: ' + forbidden.join(', '));
    }
  });

  await _assertAsync('AttachmentsWidget 云端 OIS 上传后解析签名地址', async () => {
    const dom = new JSDOM('<!DOCTYPE html><html><body><div id="mount"></div></body></html>', {
      runScripts: 'dangerously',
      resources: 'usable',
      url: 'http://localhost',
    });
    const { window } = dom;
    window.console = console;
    window._cloudFetch = async (path, opts = {}) => {
      if (path === '/api/uploads') {
        return { url: 'https://cdn.example.com/ois/uploads/raw.png', storage: 'ois', object_key: 'vb-prefix/uploads/raw.png' };
      }
      if (path === '/api/uploads/ois/resolve') {
        const body = JSON.parse(opts.body || '{}');
        if (body.object_key !== 'vb-prefix/uploads/raw.png') throw new Error('object_key 未透传');
        return { url: 'https://signed.example.com/image.png?token=123' };
      }
      throw new Error('unexpected path ' + path);
    };
    window.AI00RuntimeConfig = { toAbsoluteBackendUrl: (url) => url };
    window.URL.createObjectURL = () => 'blob:test';
    window.URL.revokeObjectURL = () => {};
    window.alert = () => {};
    window.FileReader = class {
      readAsDataURL() {
        this.result = 'data:image/png;base64,AAAA';
        this.onload?.();
      }
    };
    window.Image = class {
      set src(_value) {
        this.width = 10;
        this.height = 10;
        this.onload?.();
      }
    };
    const originalCreateElement = window.document.createElement.bind(window.document);
    window.document.createElement = function(tagName) {
      const el = originalCreateElement(tagName);
      if (String(tagName).toLowerCase() === 'canvas') {
        el.getContext = () => ({ drawImage() {} });
        el.toDataURL = () => 'data:image/png;base64,BBBB';
      }
      return el;
    };
    const code = fs.readFileSync(path.join(ROOT, 'web/components/attachments_widget.js'), 'utf-8');
    const script = window.document.createElement('script');
    script.textContent = `${code}\nwindow.AttachmentsWidget = AttachmentsWidget;`;
    window.document.head.appendChild(script);
    const widget = new window.AttachmentsWidget({
      el: window.document.getElementById('mount'),
      attachments: [],
      isCloud: true,
      itemType: 'task',
      itemGid: 'gid-1',
      onSave() {},
      readonly: false,
    });
    const file = new window.File(['raw'], 'demo.png', { type: 'image/png' });
    const originalBodyAppend = window.document.body.appendChild.bind(window.document.body);
    window.document.body.appendChild = function(node) {
      const result = originalBodyAppend(node);
      if (node.tagName === 'INPUT' && node.type === 'file') {
        Object.defineProperty(node, 'files', { value: [file], configurable: true });
        setTimeout(() => node.dispatchEvent(new window.Event('change')) , 0);
      }
      return result;
    };
    widget._uploadCloud();
    await new Promise(resolve => setTimeout(resolve, 20));
    if (widget._list.length !== 1) throw new Error('附件未写入');
    if (widget._list[0].url !== 'https://signed.example.com/image.png?token=123') {
      throw new Error('未使用签名地址: ' + widget._list[0].url);
    }
    if (widget._list[0].object_key !== 'vb-prefix/uploads/raw.png') {
      throw new Error('object_key 未保留: ' + widget._list[0].object_key);
    }
  });

  await _assertAsync('TC 导入路线创建版本后自动打开 Excel 导入步骤', async () => {
    const w = makeLifecyclePanelEnv();
    let opened = 0;
    w._verMgr = {
      loadVersions: async () => {},
      selectVersion() {},
      openImportTcModal() { opened += 1; },
    };
    const panel = new w.BopLifecyclePanel({
      cf: async (path, opts = {}) => {
        if (path === '/api/bop/versions?include_archived=true') return { data: [] };
        if (path === '/api/bop/versions') return { data: { gid: 'new-ver-gid' } };
        if (path === '/api/bop/versions/new-ver-gid/lifecycle/init-state') return { success: true };
        throw new Error('unexpected path ' + path);
      },
      toast() {},
      versionGid: null,
      mountEl: w.document.getElementById('mount'),
      actionEl: w.document.getElementById('action'),
    });
    panel._projectsCache = [{ gid: 'proj-1', name: '项目A', factory_gid: 'fac-1' }];
    panel._factoriesCache = [{ gid: 'fac-1', name: '工厂A' }];
    panel._allVersionsCache = [];
    await panel._showTcImportFlow();
    const projSel = panel._actionEl.querySelector('select');
    projSel.value = 'proj-1';
    projSel.dispatchEvent(new w.Event('change'));
    const stageSel = panel._actionEl.querySelectorAll('select')[2];
    stageSel.value = 'TG0';
    stageSel.dispatchEvent(new w.Event('change'));
    const createBtn = [...panel._actionEl.querySelectorAll('button')].find(btn => btn.textContent.includes('创建版本并开始导入'));
    await createBtn.click();
    await new Promise(resolve => setTimeout(resolve, 0));
    if (opened !== 1) throw new Error('未自动打开 Excel 导入步骤');
  });

  await _assertAsync('lineage 新建节点配置不再包含序号字段', async () => {
    const src = readLineageSource();
    const fieldsBlock = src.match(/const _NODE_FIELDS = \{[\s\S]*?^\};/m)?.[0] || '';
    if (!fieldsBlock) throw new Error('未找到 _NODE_FIELDS 定义');
    if (fieldsBlock.includes("id:'seq_no'")) throw new Error('新建节点字段定义仍包含 seq_no');
  });

  await _assertAsync('lineage 工位新建弹窗不再渲染序号选择', async () => {
    const src = readLineageSource();
    if (src.includes('_ndlgStSeq')) throw new Error('工位新建弹窗仍包含序号选择');
    if (src.includes('请填写序号')) throw new Error('工位新建弹窗仍提示填写序号');
  });

  await _assertAsync('layout_detail_panel 属性区可正常渲染本体字段', async () => {
    const w = makeLayoutDetailPanelEnv();
    const panel = new w.LayoutDetailPanel({
      containerEl: w.document.getElementById('llDetailPanel'),
      cf: async (url) => {
        if (url === '/api/ontology/schema/process') {
          return { properties: [{ name: 'cycle_time', label_zh: '节拍', prop_kind: 'data', show_in_detail: true, storage_hint: 'meta', data_type: 'string' }] };
        }
        if (url.startsWith('/api/bop/entry-links?')) return { data: [] };
        throw new Error('unexpected path ' + url);
      },
      toast() {},
      patchEntry: async () => {},
      reloadData: async () => {},
      getLineageData: () => ({
        childMap: new Map([['gid-1', []]]),
        rowByGid: new Map([['gid-1', { gid: 'gid-1', node_type: 'process', parent_gid: 'line-1', meta: { cycle_time: '12' } }], ['line-1', { gid: 'line-1', node_type: 'line_process', parent_gid: null }]]),
        lineGrantSet: new Set(['line-1']),
        lineReadOnly: true,
      }),
      onNodeActivate() {},
      getVersionInfo: () => null,
      onVersionChange() {},
    });
    panel._renderProps('gid-1', { gid: 'gid-1', node_type: 'process', parent_gid: 'line-1', meta: { cycle_time: '12' } });
    await new Promise(resolve => setTimeout(resolve, 0));
    const area = panel._propsBody.querySelector('#llPropsOntoArea');
    if (!area) throw new Error('未渲染属性区');
    if (area.textContent.includes('属性加载失败')) throw new Error('属性区仍然加载失败');
    if (!area.textContent.includes('节拍')) throw new Error('未渲染本体字段');
  });

  await _assertAsync('layout_detail_panel 关系区渲染不再引用未定义的 canEditCurrentLine', async () => {
    const w = makeLayoutDetailPanelEnv();
    const panel = new w.LayoutDetailPanel({
      containerEl: w.document.getElementById('llDetailPanel'),
      cf: async (url) => {
        if (url.startsWith('/api/bop/entry-links?')) return { data: [] };
        throw new Error('unexpected path ' + url);
      },
      toast() {},
      patchEntry: async () => {},
      reloadData: async () => {},
      getLineageData: () => ({
        childMap: new Map([['gid-1', []]]),
        rowByGid: new Map([['gid-1', { gid: 'gid-1', node_type: 'process', parent_gid: 'line-1' }], ['line-1', { gid: 'line-1', node_type: 'line_process', parent_gid: null }]]),
        lineGrantSet: new Set(),
        lineReadOnly: true,
      }),
      onNodeActivate() {},
      getVersionInfo: () => null,
      onVersionChange() {},
    });
    await panel._renderRels('gid-1', w.document.getElementById('llDpRelsBody'));
    const addBtn = w.document.querySelector('.ll-rg-add');
    if (!addBtn) throw new Error('关系区未渲染添加按钮');
    if (!addBtn.disabled) throw new Error('只读线体下添加按钮应为 disabled');
  });

  await _assertAsync('layout_detail_panel 缺少规则列容器时跳过规则渲染', async () => {
    const w = makeLayoutDetailPanelEnv();
    const panel = new w.LayoutDetailPanel({
      containerEl: w.document.getElementById('llDetailPanel'),
      cf: async () => ({ rules: [] }),
      toast() {},
      patchEntry: async () => {},
      reloadData: async () => {},
      getLineageData: () => null,
      onNodeActivate() {},
      getVersionInfo: () => null,
      onVersionChange() {},
    });
    panel._rulesBody = null;
    await panel._renderRules('gid-1', { node_type: 'process' });
  });

  await _assertAsync('layout_mode 只读线体下复制粘贴仍走创建接口', async () => {
    const w = makeLayoutModeEnv();
    const container = w.document.getElementById('lvLayoutCanvas');
    const mode = new w.LayoutMode(container);
    const calls = [];
    mode._data = {
      versionGid: 'ver-1',
      rowByGid: new Map([
        ['process-1', { gid: 'process-1', node_type: 'process', title: '工序A', version_gid: 'ver-1' }],
        ['station-1', { gid: 'station-1', node_type: 'station_process', title: '工位A', version_gid: 'ver-1' }],
      ]),
      lineReadOnly: true,
      lineGrantSet: new Set(),
      toast() {},
      reloadData() {},
      cf: async (url, opts = {}) => {
        calls.push({ url, opts });
        return { data: { gid: 'new-entry' } };
      },
    };
    mode._activeGid = 'process-1';
    const srcEl = w.document.createElement('div');
    srcEl.className = 'll-ring-card';
    srcEl.dataset.gid = 'process-1';
    mode._world.appendChild(srcEl);
    w.document.dispatchEvent(new w.KeyboardEvent('keydown', { key: 'c', ctrlKey: true, bubbles: true }));
    mode._activeGid = 'station-1';
    w.document.dispatchEvent(new w.KeyboardEvent('keydown', { key: 'v', ctrlKey: true, bubbles: true }));
    await new Promise(resolve => setTimeout(resolve, 0));
    if (calls.length !== 1) throw new Error('复制粘贴未触发创建接口');
    if (calls[0].url !== '/api/bop/entries') throw new Error('创建接口错误: ' + calls[0].url);
    const body = JSON.parse(calls[0].opts.body || '{}');
    if (body.parent_gid !== 'station-1') throw new Error('parent_gid 未指向目标工位: ' + body.parent_gid);
    if (body.node_type !== 'process') throw new Error('复制节点类型错误: ' + body.node_type);
  });

  // ── 汇总 ─────────────────────────────────────────────────────────
  const total = _passed + _failed;
  console.log(`\n${C.bold}${'─'.repeat(50)}${C.reset}`);
  if (_failed === 0) {
    console.log(`${C.green}${C.bold}✅ 全部通过 ${_passed}/${total}${C.reset}`);
  } else {
    console.log(`${C.red}${C.bold}❌ ${_failed} 失败，${_passed} 通过，共 ${total}${C.reset}`);
    process.exitCode = 1;
  }
}

runTests().catch(err => {
  console.error(`${C.red}运行器内部错误: ${err.message}${C.reset}`);
  console.error(err.stack);
  process.exitCode = 1;
});
