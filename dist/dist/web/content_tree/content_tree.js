/**
 * content_tree.js — 全局内容树
 *
 * 通信协议：
 *   接收 ct:data  { type:'ct:data', tree }       — 主窗口初始化数据
 *   接收 ct:update-ack                            — 主窗口确认更新
 *   接收 theme-change { theme }                  — 主题变更
 *
 *   发送 ct:ready                                 — DOM 就绪，请求数据
 *   发送 ct:open  { tabId, tabKey?, params? }     — 打开某个内容
 *   发送 ct:update { tree }                       — 树数据变更，请求持久化
 *
 * 条目 schema：
 *   { id, title, icon, tabId, tabKey?, params? }
 *
 * 分组 schema：
 *   { id, title, auto, collapsed, items:[] }
 */

'use strict';

// ── 图标映射 ─────────────────────────────────────────────────────────────────
const ITEM_ICONS = {
  bop_version:    `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>`,
  task_list:      `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>`,
  issue_list:     `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`,
  knowledge_list: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>`,
  rule_list:      `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M14.5 10c-.83 0-1.5-.67-1.5-1.5v-5c0-.83.67-1.5 1.5-1.5s1.5.67 1.5 1.5v5c0 .83-.67 1.5-1.5 1.5z"/><path d="M20.5 10H19V8.5c0-.83.67-1.5 1.5-1.5s1.5.67 1.5 1.5-.67 1.5-1.5 1.5z"/><path d="M9.5 14c.83 0 1.5.67 1.5 1.5v5c0 .83-.67 1.5-1.5 1.5S8 21.33 8 20.5v-5c0-.83.67-1.5 1.5-1.5z"/><path d="M3.5 14H5v1.5c0 .83-.67 1.5-1.5 1.5S2 16.33 2 15.5 2.67 14 3.5 14z"/><path d="M14 14.5c0-.83.67-1.5 1.5-1.5h5c.83 0 1.5.67 1.5 1.5s-.67 1.5-1.5 1.5h-5c-.83 0-1.5-.67-1.5-1.5z"/><path d="M15.5 19H14v1.5c0 .83.67 1.5 1.5 1.5s1.5-.67 1.5-1.5-.67-1.5-1.5-1.5z"/><path d="M10 9.5c0 .83-.67 1.5-1.5 1.5h-5C2.67 11 2 10.33 2 9.5S2.67 8 3.5 8h5c.83 0 1.5.67 1.5 1.5z"/><path d="M8.5 5H10V3.5C10 2.67 9.33 2 8.5 2S7 2.67 7 3.5 7.67 5 8.5 5z"/></svg>`,
  canvas:         `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 9l3 3-3 3M13 15h3"/></svg>`,
  project:        `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/></svg>`,
  workbench:      `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>`,
  default:        `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="10"/></svg>`,
};

function getIcon(icon) {
  return ITEM_ICONS[icon] || ITEM_ICONS.default;
}

// ── 状态 ─────────────────────────────────────────────────────────────────────
let _tree = null;       // { groups: [...] }
let _searchQ = '';
let _ctxTarget = null;  // { type: 'group'|'item', groupId, itemId? }

// ── DOM ──────────────────────────────────────────────────────────────────────
const $tree    = document.getElementById('ct-tree');
const $search  = document.getElementById('ct-search-input');
const $addGrp  = document.getElementById('ct-add-group-btn');
const $ctxMenu = document.getElementById('ct-ctx-menu');
const $addDlg  = document.getElementById('ct-add-dlg');
const $addBody = document.getElementById('ct-add-dlg-body');

// ── 主题 ─────────────────────────────────────────────────────────────────────
function _applyTheme(t) {
  document.documentElement.setAttribute('data-theme', t || 'dark');
}
(function () {
  try {
    const cfg = JSON.parse(localStorage.getItem('ai00:system-config') || '{}');
    _applyTheme(cfg['system.theme'] || 'dark');
  } catch (_) {}
})();

// ── 通信 ─────────────────────────────────────────────────────────────────────
window.addEventListener('message', e => {
  const d = e.data;
  if (!d || !d.type) return;
  if (d.type === 'ct:data')     { _tree = d.tree; render(); }
  if (d.type === 'theme-change') { _applyTheme(d.theme); }
  if (d.type === 'theme')        { _applyTheme(d.theme); }
});

function _send(msg) { window.top?.postMessage(msg, '*'); }
function _save()    { _send({ type: 'ct:update', tree: _tree }); }
function _openItem(item) { _send({ type: 'ct:open', tabId: item.tabId, tabKey: item.tabKey, params: item.params }); }

// ── ID 生成 ──────────────────────────────────────────────────────────────────
function _uid() { return 'grp_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6); }
function _itemId() { return 'itm_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6); }

// ── 渲染 ─────────────────────────────────────────────────────────────────────
function render() {
  if (!_tree) {
    $tree.innerHTML = '<div class="ct-empty"><div class="ct-empty-icon"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.3"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg></div><div>加载中…</div></div>';
    return;
  }

  const groups = _tree.groups || [];
  const q = _searchQ.trim().toLowerCase();

  if (!groups.length) {
    $tree.innerHTML = '<div class="ct-empty"><div class="ct-empty-icon"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.3"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg></div><div>暂无分组<br>点击 + 新建分组</div></div>';
    return;
  }

  $tree.innerHTML = '';
  groups.forEach(grp => _renderGroup(grp, q));
}

function _renderGroup(grp, q) {
  const items = (grp.items || []).filter(it =>
    !q || it.title.toLowerCase().includes(q)
  );

  // 搜索时跳过空分组
  if (q && items.length === 0) return;

  const div = document.createElement('div');
  div.className = 'ct-group' + (grp.collapsed && !q ? ' collapsed' : '');
  div.dataset.id = grp.id;

  // ── header ──
  const hdr = document.createElement('div');
  hdr.className = 'ct-group-header';
  hdr.innerHTML = `
    <svg class="ct-group-chevron" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
    <span class="ct-group-title">${_esc(grp.title)}</span>
    ${items.length ? `<span class="ct-group-count">${items.length}</span>` : ''}
    <div class="ct-group-actions">
      ${grp.auto ? '' : `<button class="ct-group-act-btn" data-action="add-item" title="添加内容"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg></button>`}
      ${grp.auto ? '' : `<button class="ct-group-act-btn" data-action="rename" title="重命名"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg></button>`}
    </div>`;

  // 折叠/展开
  hdr.addEventListener('click', e => {
    if (e.target.closest('.ct-group-actions')) return;
    grp.collapsed = !grp.collapsed;
    _save();
    render();
  });

  // 分组操作按钮
  hdr.querySelectorAll('[data-action]').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      const action = btn.dataset.action;
      if (action === 'add-item') _openAddDialog(grp.id);
      if (action === 'rename')   _renameGroup(grp.id);
    });
  });

  // 右键
  hdr.addEventListener('contextmenu', e => {
    e.preventDefault();
    _showCtxMenu(e, { type: 'group', groupId: grp.id });
  });

  div.appendChild(hdr);

  // ── items ──
  const itemsDiv = document.createElement('div');
  itemsDiv.className = 'ct-group-items';
  itemsDiv.dataset.groupId = grp.id;

  if (!items.length && !q) {
    itemsDiv.innerHTML = grp.auto
      ? '<div class="ct-group-empty">暂无最近访问记录</div>'
      : '<div class="ct-group-empty">拖入内容或点击 + 添加</div>';
  } else {
    items.forEach(item => {
      const el = document.createElement('div');
      el.className = 'ct-item';
      el.dataset.itemId = item.id;
      el.innerHTML = `
        <span class="ct-item-icon">${getIcon(item.icon)}</span>
        <span class="ct-item-title" title="${_esc(item.title)}">${_esc(item.title)}</span>
        <button class="ct-item-remove" title="从分组移除"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg></button>`;

      el.addEventListener('click', e => {
        if (e.target.closest('.ct-item-remove')) return;
        _openItem(item);
      });
      el.querySelector('.ct-item-remove').addEventListener('click', e => {
        e.stopPropagation();
        _removeItem(grp.id, item.id);
      });
      el.addEventListener('contextmenu', e => {
        e.preventDefault();
        _showCtxMenu(e, { type: 'item', groupId: grp.id, itemId: item.id });
      });
      itemsDiv.appendChild(el);
    });
  }

  div.appendChild(itemsDiv);
  $tree.appendChild(div);
}

// ── 右键菜单 ─────────────────────────────────────────────────────────────────
function _showCtxMenu(e, target) {
  _ctxTarget = target;
  let html = '';
  if (target.type === 'group') {
    const grp = _findGroup(target.groupId);
    if (!grp) return;
    if (!grp.auto) {
      html += `<div class="ct-ctx-item" data-action="add-item">添加内容…</div>`;
      html += `<div class="ct-ctx-item" data-action="rename">重命名分组</div>`;
      html += `<div class="ct-ctx-sep"></div>`;
      html += `<div class="ct-ctx-item" data-action="move-up">↑ 上移分组</div>`;
      html += `<div class="ct-ctx-item" data-action="move-down">↓ 下移分组</div>`;
      html += `<div class="ct-ctx-sep"></div>`;
      html += `<div class="ct-ctx-item danger" data-action="delete-group">删除分组</div>`;
    } else {
      html += `<div class="ct-ctx-item" data-action="clear-recent">清空最近记录</div>`;
    }
  } else {
    html += `<div class="ct-ctx-item" data-action="open-item">打开</div>`;
    html += `<div class="ct-ctx-sep"></div>`;
    html += `<div class="ct-ctx-item" data-action="move-item-up">↑ 上移</div>`;
    html += `<div class="ct-ctx-item" data-action="move-item-down">↓ 下移</div>`;
    html += `<div class="ct-ctx-sep"></div>`;
    html += `<div class="ct-ctx-item danger" data-action="remove-item">从分组移除</div>`;
  }

  $ctxMenu.innerHTML = html;
  $ctxMenu.querySelectorAll('.ct-ctx-item').forEach(el => {
    el.addEventListener('click', () => { _execCtxAction(el.dataset.action); _hideCtxMenu(); });
  });

  let x = e.clientX, y = e.clientY;
  if (x + 160 > window.innerWidth)  x = window.innerWidth - 165;
  if (y + 150 > window.innerHeight) y = window.innerHeight - 155;
  $ctxMenu.style.left = x + 'px';
  $ctxMenu.style.top  = y + 'px';
  $ctxMenu.classList.remove('hidden');

  setTimeout(() => {
    document.addEventListener('mousedown', _onCtxOutside, { once: true });
  }, 10);
}

function _onCtxOutside(e) {
  if (!$ctxMenu.contains(e.target)) _hideCtxMenu();
}
function _hideCtxMenu() { $ctxMenu.classList.add('hidden'); }

function _execCtxAction(action) {
  if (!_ctxTarget) return;
  const { groupId, itemId } = _ctxTarget;

  if (action === 'add-item')      { _openAddDialog(groupId); return; }
  if (action === 'rename')        { _renameGroup(groupId); return; }
  if (action === 'delete-group')  { _deleteGroup(groupId); return; }
  if (action === 'clear-recent')  { _clearRecent(); return; }
  if (action === 'open-item') {
    const grp = _findGroup(groupId);
    const item = grp?.items.find(i => i.id === itemId);
    if (item) _openItem(item);
    return;
  }
  if (action === 'remove-item')   { _removeItem(groupId, itemId); return; }
  if (action === 'move-up')       { _moveGroup(groupId, -1); return; }
  if (action === 'move-down')     { _moveGroup(groupId, +1); return; }
  if (action === 'move-item-up')  { _moveItem(groupId, itemId, -1); return; }
  if (action === 'move-item-down'){ _moveItem(groupId, itemId, +1); return; }
}

// ── 分组操作 ─────────────────────────────────────────────────────────────────
function _findGroup(id) { return _tree?.groups.find(g => g.id === id); }

function _renameGroup(id) {
  const grp = _findGroup(id);
  if (!grp) return;
  const hdr = $tree.querySelector(`.ct-group[data-id="${id}"] .ct-group-title`);
  if (!hdr) return;
  const input = document.createElement('input');
  input.className = 'ct-group-name-input';
  input.value = grp.title;
  hdr.replaceWith(input);
  input.focus();
  input.select();
  const done = () => {
    const v = input.value.trim();
    if (v) { grp.title = v; _save(); }
    render();
  };
  input.addEventListener('blur', done);
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter') { input.blur(); }
    if (e.key === 'Escape') { render(); }
  });
}

function _deleteGroup(id) {
  const idx = _tree.groups.findIndex(g => g.id === id);
  if (idx < 0) return;
  _tree.groups.splice(idx, 1);
  _save();
  render();
}

function _clearRecent() {
  const grp = _tree.groups.find(g => g.auto);
  if (grp) { grp.items = []; _save(); render(); }
}

function _moveGroup(id, delta) {
  const arr = _tree.groups;
  const idx = arr.findIndex(g => g.id === id);
  const to = idx + delta;
  if (to < 0 || to >= arr.length) return;
  [arr[idx], arr[to]] = [arr[to], arr[idx]];
  _save();
  render();
}

function _addNewGroup() {
  if (!_tree) return;
  const grp = { id: _uid(), title: '新分组', auto: false, collapsed: false, items: [] };
  _tree.groups.push(grp);
  _save();
  render();
  // 立即进入重命名
  setTimeout(() => _renameGroup(grp.id), 50);
}

// ── 条目操作 ─────────────────────────────────────────────────────────────────
function _removeItem(groupId, itemId) {
  const grp = _findGroup(groupId);
  if (!grp) return;
  grp.items = grp.items.filter(i => i.id !== itemId);
  _save();
  render();
}

function _moveItem(groupId, itemId, delta) {
  const grp = _findGroup(groupId);
  if (!grp) return;
  const idx = grp.items.findIndex(i => i.id === itemId);
  const to = idx + delta;
  if (to < 0 || to >= grp.items.length) return;
  [grp.items[idx], grp.items[to]] = [grp.items[to], grp.items[idx]];
  _save();
  render();
}

/**
 * 外部通过 ct:pin 调用此函数（由 main.js 转发）
 * item = { title, icon, tabId, tabKey?, params? }
 */
function pinItem(item, groupId) {
  if (!_tree) return;
  const grp = groupId
    ? _findGroup(groupId)
    : _tree.groups.find(g => !g.auto);

  // 无可用分组则新建一个
  const target = grp || { id: _uid(), title: '我的收藏', auto: false, collapsed: false, items: [] };
  if (!grp) _tree.groups.push(target);

  // 去重（同 tabId+tabKey+params key）
  const key = JSON.stringify({ tabId: item.tabId, tabKey: item.tabKey, params: item.params });
  if (!target.items.some(i => JSON.stringify({ tabId: i.tabId, tabKey: i.tabKey, params: i.params }) === key)) {
    target.items.push({ id: _itemId(), ...item });
  }
  _save();
  render();
}

/** 最近访问记录（由 main.js 在 TabManager 打开时推入）*/
function pushRecent(item) {
  if (!_tree) return;
  let recentGrp = _tree.groups.find(g => g.auto);
  if (!recentGrp) return;

  const key = JSON.stringify({ tabId: item.tabId, tabKey: item.tabKey, params: item.params });
  recentGrp.items = recentGrp.items.filter(
    i => JSON.stringify({ tabId: i.tabId, tabKey: i.tabKey, params: i.params }) !== key
  );
  recentGrp.items.unshift({ id: _itemId(), ...item });
  if (recentGrp.items.length > 20) recentGrp.items.length = 20;
  _save();
  render();
}

// ── 添加内容对话框 ────────────────────────────────────────────────────────────
// 显示所有可添加的内容类型，供用户手动选择
const ADDABLE_ITEMS = [
  { section: '工艺规划',  items: [
    { title: 'BOP 工艺版本',     icon: 'bop_version',    tabId: 'craft_hub',       tabKey: 'bop_lineage',  hint: '需选择版本' },
    { title: 'PBOM 清单',        icon: 'bop_version',    tabId: 'craft_hub',       tabKey: 'pbom',         hint: '' },
    { title: 'BOP 工艺导航',     icon: 'bop_version',    tabId: 'craft_hub',       tabKey: 'bop_nav',      hint: '' },
  ]},
  { section: '任务与问题', items: [
    { title: '任务清单',         icon: 'task_list',      tabId: 'task',            hint: '打开任务模块' },
    { title: '问题清单',         icon: 'issue_list',     tabId: 'issue',           hint: '打开问题模块' },
  ]},
  { section: '知识与规则', items: [
    { title: '知识库',           icon: 'knowledge_list', tabId: 'knowledge_hub',   hint: '' },
    { title: '规则管理',         icon: 'rule_list',      tabId: 'automation_hub',  tabKey: 'rule', hint: '' },
  ]},
  { section: '项目与工作台', items: [
    { title: '项目管理',         icon: 'project',        tabId: 'project_hub',     hint: '' },
    { title: '个人工作台',       icon: 'workbench',      tabId: 'workbench',       hint: '' },
  ]},
];

let _addTargetGroupId = null;

function _openAddDialog(groupId) {
  _addTargetGroupId = groupId;
  $addBody.innerHTML = '';

  ADDABLE_ITEMS.forEach(section => {
    const secTitle = document.createElement('div');
    secTitle.className = 'ct-add-section-title';
    secTitle.textContent = section.section;
    $addBody.appendChild(secTitle);

    section.items.forEach(proto => {
      const el = document.createElement('div');
      el.className = 'ct-add-item';
      el.innerHTML = `
        <span>${getIcon(proto.icon)}</span>
        <span style="flex:1">${_esc(proto.title)}</span>
        ${proto.hint ? `<span class="ct-add-item-sub">${_esc(proto.hint)}</span>` : ''}`;
      el.addEventListener('click', () => {
        _closeAddDialog();
        const item = {
          title:  proto.title,
          icon:   proto.icon,
          tabId:  proto.tabId,
          tabKey: proto.tabKey || undefined,
          params: undefined,
        };
        pinItem(item, _addTargetGroupId);
      });
      $addBody.appendChild(el);
    });
  });

  $addDlg.classList.remove('hidden');
}

function _closeAddDialog() { $addDlg.classList.add('hidden'); }

// ── 搜索 ─────────────────────────────────────────────────────────────────────
$search.addEventListener('input', () => {
  _searchQ = $search.value;
  render();
});

// ── 新建分组按钮 ──────────────────────────────────────────────────────────────
$addGrp.addEventListener('click', _addNewGroup);

// ── 对话框关闭 ────────────────────────────────────────────────────────────────
document.getElementById('ct-add-dlg-close').addEventListener('click', _closeAddDialog);
$addDlg.addEventListener('click', e => { if (e.target === $addDlg) _closeAddDialog(); });

// ── 工具函数 ──────────────────────────────────────────────────────────────────
function _esc(s) {
  return String(s ?? '').replace(/[&<>\"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
  );
}

// ── 暴露给 index.html 调用 ────────────────────────────────────────────────────
window.ContentTree = { pinItem, pushRecent, render };

// ── 初始化：通知主窗口已就绪 ──────────────────────────────────────────────────
window._send = _send;   // 供 index.html 中 onload 调用
