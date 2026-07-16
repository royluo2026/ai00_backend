'use strict';
/**
 * float_shell.js — 悬浮卡片窗口逻辑
 *
 * 功能：
 *   - 标题栏拖拽（由 OS / -webkit-app-region:drag 处理）
 *   - 配置弹窗：选择卡片模式 + 参数 → 加载 iframe
 *   - 刷新 / 关闭 / 缩为悬浮球
 *   - postMessage 接收来自主窗口或触发卡片的上下文 (cc:params)
 *   - 主题同步
 */

// ── 持久化配置 key ─────────────────────────────────────────────
const LS_KEY = 'float_shell:config';

// 当前卡片配置
let _cfg = null;

// ── 初始化 ────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // 应用主题
  const theme = localStorage.getItem('system.theme') || 'dark';
  document.documentElement.setAttribute('data-theme', theme);

  // 加载已保存配置
  try { _cfg = JSON.parse(localStorage.getItem(LS_KEY)); } catch (_) {}

  // 绑定按钮
  document.getElementById('fsBtnClose').onclick = () =>
    window.electronAPI?.hideFloatShell?.();

  document.getElementById('fsBtnRefresh').onclick = () => {
    const iframe = document.getElementById('fsIframe');
    if (iframe.src) iframe.src = iframe.src;
  };

  document.getElementById('fsBtnOrb').onclick = () =>
    window.electronAPI?.floatShellToOrb?.();

  document.getElementById('fsBtnConfig').onclick = () => _openConfigModal();
  document.getElementById('fsBtnConfigClose').onclick   = () => _closeConfigModal();
  document.getElementById('fsBtnConfigCancel').onclick  = () => _closeConfigModal();
  document.getElementById('fsBtnConfigSave').onclick    = () => _saveConfig();

  // 模式选择 → 显示/隐藏相关字段
  document.getElementById('fsConfigMode').addEventListener('change', _updateConfigForm);

  // 如果已有配置，直接加载（initialSrc URL 参数优先，用于从 hub 弹出裸子页面）
  const _initialSrc = new URLSearchParams(location.search).get('initialSrc');
  if (_initialSrc) {
    // 直接加载裸页面，不经过 container_card 包装
    document.getElementById('fsIframe').src = `../${_initialSrc}`;
  } else if (_cfg) {
    _applyConfig(_cfg);
  }
});

// ── 主题同步 ──────────────────────────────────────────────────
window.addEventListener('message', e => {
  if (e.data?.type === 'theme') {
    document.documentElement.setAttribute('data-theme', e.data.theme);
  }
  // 主窗口推送 cc:params（触发卡片上下文），注入到 iframe
  if (e.data?.type === 'cc:params' && _cfg) {
    const iframe = document.getElementById('fsIframe');
    if (iframe?.contentWindow) {
      iframe.contentWindow.postMessage(e.data, '*');
    }
  }
  // 主窗口推送配置变更
  if (e.data?.type === 'fs:setConfig' && e.data.config) {
    _applyConfig(e.data.config);
  }
});

// ── 配置弹窗 ─────────────────────────────────────────────────

function _openConfigModal() {
  const modal = document.getElementById('fsConfigModal');
  // 填入当前值
  if (_cfg) {
    const setVal = (id, val) => { const el = document.getElementById(id); if (el && val != null) el.value = val; };
    setVal('fsConfigMode',     _cfg.mode      || 'row_detail');
    setVal('fsConfigItemType', _cfg.item_type || 'task');
    setVal('fsConfigGid',      _cfg.gid       || '');
    setVal('fsConfigSource',   _cfg.source    || 'local');
    setVal('fsConfigField',    _cfg.field     || '');
    setVal('fsConfigUrl',      _cfg.url       || '');
    setVal('fsConfigMdPath',   _cfg.md_path   || '');
    setVal('fsConfigTitle',    _cfg.title     || '');
  }
  _updateConfigForm();
  modal.style.display = 'flex';
  setTimeout(() => modal.querySelector('select,input')?.focus?.(), 50);
}

function _closeConfigModal() {
  document.getElementById('fsConfigModal').style.display = 'none';
}

function _updateConfigForm() {
  const mode = document.getElementById('fsConfigMode').value;
  const show = (...ids) => ids.forEach(id => document.getElementById(id) && (document.getElementById(id).style.display = ''));
  const hide = (...ids) => ids.forEach(id => document.getElementById(id) && (document.getElementById(id).style.display = 'none'));

  hide('fsRowParams', 'fsFieldParams', 'fsWebviewParams', 'fsMdParams');

  if (mode === 'row_detail' || mode === 'text_image') {
    show('fsRowParams');
  } else if (mode === 'field_detail') {
    show('fsRowParams', 'fsFieldParams');
  } else if (mode === 'webview') {
    show('fsWebviewParams');
  } else if (mode === 'markdown_file') {
    show('fsMdParams');
  }
}

function _saveConfig() {
  const gv = id => document.getElementById(id)?.value || '';
  const mode = gv('fsConfigMode');
  _cfg = {
    mode,
    item_type: gv('fsConfigItemType'),
    gid:       gv('fsConfigGid') || null,
    source:    gv('fsConfigSource'),
    field:     gv('fsConfigField') || null,
    url:       gv('fsConfigUrl')  || null,
    md_path:   gv('fsConfigMdPath') || null,
    title:     gv('fsConfigTitle') || null,
  };
  localStorage.setItem(LS_KEY, JSON.stringify(_cfg));
  _closeConfigModal();
  _applyConfig(_cfg);
}

// ── 应用配置 → 加载 iframe ─────────────────────────────────────

function _applyConfig(cfg) {
  if (!cfg) return;
  // 更新标题
  const titleEl = document.getElementById('fsTitle');
  if (titleEl) titleEl.textContent = cfg.title || _modeLabel(cfg.mode) || '悬浮卡片';

  const iframe = document.getElementById('fsIframe');
  const empty  = document.getElementById('fsEmpty');

  // 构建 iframe URL
  const params = new URLSearchParams();
  params.set('mode', cfg.mode);
  if (cfg.item_type) params.set('item_type', cfg.item_type);
  if (cfg.gid)       params.set('gid', cfg.gid);
  if (cfg.source)    params.set('source', cfg.source);
  if (cfg.field)     params.set('field', cfg.field);
  if (cfg.url)       params.set('url', encodeURIComponent(cfg.url));
  if (cfg.md_path)   params.set('path', btoa(cfg.md_path));

  const src = '../container_card/index.html?' + params.toString();

  iframe.style.display = '';
  if (empty) empty.style.display = 'none';

  if (iframe.src !== src) iframe.src = src;
}

function _modeLabel(mode) {
  const map = {
    row_detail:    '行详情',
    markdown_file: 'Markdown',
    image_gallery: '图片预览',
    webview:       '网页浏览',
    pdf:           'PDF',
    field_detail:  '字段详情',
    script:        '脚本编辑',
    text_image:    '图文双栏',
  };
  return map[mode] || mode;
}
