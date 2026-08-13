'use strict';
/**
 * knowledge_hub.js — 知识库 Hub 主控制器
 * 4列布局：Left1(导航树) + Left2(文件列表) + Center(内容) + Right(评论)
 */

// ── 工具 ──────────────────────────────────────────────────────────────────────
function _cf() {
  return window._cloudFetch || window.parent?._cloudFetch || null;
}
// localStorage 账号隔离
function _lsk(base) {
  try { const u = window.parent?._authUser || window._authUser; const g = u?.gid || u?.user_gid || ''; return g ? `${g}:${base}` : base; } catch { return base; }
}
function _isCloud() {
  return (window.parent?._authMode || window._authMode || 'none') === 'feishu';
}
function _authMode() {
  return window.parent?._authMode || window._authMode || 'none';
}
function _esc(s) {
  return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function _fmt(ts) {
  if (!ts) return '';
  try {
    const d = new Date(ts);
    const now = new Date();
    const diff = now - d;
    if (diff < 60000) return '刚刚';
    if (diff < 3600000) return `${Math.floor(diff/60000)}分钟前`;
    if (diff < 86400000) return `${Math.floor(diff/3600000)}小时前`;
    return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
  } catch (_) { return ''; }
}

async function _invokeCapability(capabilityId, payload, confirmationToken) {
  const cf = _cf();
  if (!cf) throw new Error('能力网关不可用');
  const body = { payload: payload || {} };
  if (confirmationToken) body.confirmation_token = confirmationToken;
  const response = await cf(`/api/v1/capabilities/${encodeURIComponent(capabilityId)}:invoke`, {
    method: 'POST', body: JSON.stringify(body), headers: { 'X-AI00-Source': 'web' },
  });
  return response?.data || { data: null, evidence: [] };
}

async function _confirmAndInvokeCapability(capabilityId, payload) {
  const cf = _cf();
  if (!cf) throw new Error('能力网关不可用');
  const confirmed = await cf(`/api/v1/capabilities/${encodeURIComponent(capabilityId)}:confirm`, {
    method: 'POST', body: JSON.stringify({ payload: payload || {} }), headers: { 'X-AI00-Source': 'web' },
  });
  const token = confirmed?.data?.confirmation_token;
  if (!token) throw new Error('未取得操作确认令牌');
  return _invokeCapability(capabilityId, payload, token);
}
// 调用云端 API（替代本地 bridge）
async function _bridge(method, ...args) {
  const cf = _cf();
  if (!cf) throw new Error('cloudFetch not available');
  switch (method) {
    case 'list_folders': {
      const scopeType = args[0] || 'personal';
      return { data: await cf(`/api/knowledge_hub/folders?scope_type=${scopeType}`) };
    }
    case 'list_favorites':
      return { data: await cf('/api/knowledge_hub/favorites') };
    case 'list_recent':
      return { data: await cf(`/api/knowledge_hub/recent?limit=${args[0] || 20}`) };
    case 'list_items': {
      const folderGid = args[0];
      const url = folderGid ? `/api/knowledge_hub/items?folder_gid=${folderGid}` : '/api/knowledge_hub/items';
      return { data: await cf(url) };
    }
    case 'update_item': {
      const { gid, ...fields } = args[0] || {};
      return cf(`/api/knowledge_hub/items/${gid}`, { method: 'PATCH', body: JSON.stringify(fields) });
    }
    case 'delete_item':
      return cf(`/api/knowledge_hub/items/${args[0]}`, { method: 'DELETE' });
    case 'create_folder':
      return { data: await cf('/api/knowledge_hub/folders', { method: 'POST', body: JSON.stringify({ parent_gid: args[0] || null, name: args[1] || '新建文件夹', scope_type: 'personal' }) }) };
    case 'rename_folder':
      return cf(`/api/knowledge_hub/folders/${args[0]}`, { method: 'PATCH', body: JSON.stringify({ name: args[1] }) });
    case 'delete_folder':
      return cf(`/api/knowledge_hub/folders/${args[0]}`, { method: 'DELETE' });
    case 'move_folder':
      return cf(`/api/knowledge_hub/folders/${args[0]}`, { method: 'PATCH', body: JSON.stringify({ parent_gid: args[1] || null }) });
    case 'create_item': {
      const [folderGid, itemType, title, contentBody, contentMd, filePath, url, siteRef, tags] = args;
      return { data: await cf('/api/knowledge_hub/items', { method: 'POST', body: JSON.stringify({ folder_gid: folderGid, item_type: itemType, title, content_body: contentBody, content_md: contentMd, file_path: filePath, url, site_ref: siteRef, tags, scope_type: 'personal' }) }) };
    }
    case 'record_recent':
      return cf(`/api/knowledge_hub/items/${args[0]}/recent`, { method: 'POST' });
    default:
      throw new Error(`Unknown bridge method: ${method}`);
  }
}

// ── 图标 SVG ─────────────────────────────────────────────────────────────────
const ICONS = {
  folder:      `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/></svg>`,
  richtext:    `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>`,
  markdown:    `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="5" width="20" height="14" rx="2"/><path d="M6 15v-6l3 4 3-4v6M17 9l-3 3m0 0l-2-2"/></svg>`,
  pdf:         `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><path d="M9 15h6M9 12h6"/></svg>`,
  weblink:     `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z"/></svg>`,
  site_page:   `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>`,
  spreadsheet: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="1"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="3" y1="15" x2="21" y2="15"/><line x1="12" y1="3" x2="12" y2="21"/></svg>`,
  image:       `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>`,
  star:        `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>`,
  clock:       `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`,
  globe:       `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z"/></svg>`,
  team:        `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/></svg>`,
  user:        `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`,
  chevron:     `<svg class="kh-nav-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="9 18 15 12 9 6"/></svg>`,
  plus:        `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>`,
  comment:     `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>`,
};

// ── 状态 ─────────────────────────────────────────────────────────────────────
let _currentScope     = 'personal';   // personal | public | team | favorites | recent
let _currentTeamGid   = null;
let _currentFolderGid = null;
let _currentItem      = null;
let _personalFolders  = [];           // 本地文件夹列表
let _cloudFolders     = {};           // { scope_key: [] }
let _items            = [];           // 当前 Left2 条目列表
let _searchQuery      = '';
let _groupBy          = 'none';       // none | date | status
let _sortBy           = 'updated';    // updated | created | title
let _openGroups       = {};           // 导航组折叠状态
let _activeNodeKey    = '';           // 当前激活节点 key
let _thread           = null;         // EntryThread 实例
let _migrationSnapshot = null;       // 当前团队的遗留迁移只读状态

// ── DOM 引用 ─────────────────────────────────────────────────────────────────
let _navScroll, _listScroll, _centerBody, _rightBody, _centerTitle;

// ── 初始化 ───────────────────────────────────────────────────────────────────
async function init() {
  if (window._khInited) return;
  window._khInited = true;
  // 恢复列宽
  _restoreWidths();

  _navScroll   = document.getElementById('khNavScroll');
  _listScroll  = document.getElementById('khListScroll');
  _centerBody  = document.getElementById('khCenterBody');
  _rightBody   = document.getElementById('khRightBody');
  _centerTitle = document.getElementById('khCenterTitle');

  // 恢复导航折叠状态
  try { _openGroups = JSON.parse(localStorage.getItem(_lsk('kh:nav-open')) || '{}'); } catch (_) {}

  // 搜索框
  document.getElementById('khSearchInput').addEventListener('input', e => {
    _searchQuery = e.target.value.trim().toLowerCase();
    _renderLeft2();
  });

  // 工具栏按钮
  document.getElementById('khGroupBtn').addEventListener('click', e => {
    _showDropdown(e.target, [
      { label: '不分组',  action: () => { _groupBy = 'none';   _renderLeft2(); } },
      { label: '按日期',  action: () => { _groupBy = 'date';   _renderLeft2(); } },
      { label: '按状态',  action: () => { _groupBy = 'status'; _renderLeft2(); } },
    ]);
  });
  document.getElementById('khSortBtn').addEventListener('click', e => {
    _showDropdown(e.target, [
      { label: '修改日期',  action: () => { _sortBy = 'updated'; _renderLeft2(); } },
      { label: '创建日期',  action: () => { _sortBy = 'created'; _renderLeft2(); } },
      { label: '名称',      action: () => { _sortBy = 'title';   _renderLeft2(); } },
    ]);
  });
  document.getElementById('khAddBtn').addEventListener('click', e => _showAddMenu(e.target));

  // 拖拽分隔条
  _bindDividers();

  // 折叠/展开/Pin 绑定
  _bindCollapseExpand();

  // 加载个人文件夹 + 公共知识库文件夹（并行）
  await Promise.all([
    _loadPersonalFolders(),
    _loadCloudFolders('public', null),
  ]);

  // 渲染 Left1
  _renderLeft1();

  // 默认选中个人知识库根目录
  _selectNode('personal', null);

  // URL 参数：直接打开指定条目（来自工作台文件树点击）
  const _urlItemGid = new URLSearchParams(location.search).get('item_gid');
  if (_urlItemGid) {
    try {
      const cf = _cf();
      if (cf) {
        const item = await cf(`/api/knowledge_hub/items/${_urlItemGid}`);
        if (item?.gid) _openItem(item);
      }
    } catch (_) { /* 静默失败，保持默认视图 */ }
  }

  // 自我标注：保存后更新行指示器
  window.addEventListener('sap-saved', e => {
    document.querySelectorAll(`.sap-row-pin[data-gid="${e.detail.itemGid}"]`).forEach(el => {
      if (e.detail.status) el.dataset.status = e.detail.status;
      else delete el.dataset.status;
    });
  });
}

// ── 列宽持久化 ───────────────────────────────────────────────────────────────
let _left1Collapsed = false;
let _left2Collapsed = false;
let _rightCollapsed = true;   // 默认关闭
let _rightPinned    = false;

function _restoreWidths() {
  try {
    const w = JSON.parse(localStorage.getItem(_lsk('kh:widths')) || 'null');
    if (!w) return;
    if (w.left1) document.getElementById('khLeft1').style.width = w.left1 + 'px';
    if (w.left2) document.getElementById('khLeft2').style.width = w.left2 + 'px';
    if (w.right) document.getElementById('khRight').style.width = w.right + 'px';
  } catch (_) {}
  // 恢复折叠/Pin 状态
  try {
    const c = JSON.parse(localStorage.getItem(_lsk('kh:collapse')) || 'null');
    if (c) {
      _left1Collapsed = !!c.left1;
      _left2Collapsed = !!c.left2;
      _rightCollapsed = c.right !== false;  // 默认关闭
      _rightPinned    = !!c.rightPinned;
    }
  } catch (_) {}
  _applyCollapseState();
}

function _saveWidths() {
  // 只保存非折叠面板的宽度，避免存0
  const w = {};
  const l1 = document.getElementById('khLeft1').offsetWidth;
  const l2 = document.getElementById('khLeft2').offsetWidth;
  const r  = document.getElementById('khRight').offsetWidth;
  if (l1 > 0) w.left1 = l1;
  if (l2 > 0) w.left2 = l2;
  if (r  > 0) w.right = r;
  const prev = JSON.parse(localStorage.getItem(_lsk('kh:widths')) || '{}');
  localStorage.setItem(_lsk('kh:widths'), JSON.stringify({ ...prev, ...w }));
}

function _bindDividers() {
  const dividers = [
    { el: document.getElementById('khDiv1'), target: document.getElementById('khLeft1'), minW: 140, maxW: 320 },
    { el: document.getElementById('khDiv2'), target: document.getElementById('khLeft2'), minW: 160, maxW: 400 },
    { el: document.getElementById('khDiv3'), target: document.getElementById('khRight'),  minW: 200, maxW: 400, right: true },
  ];
  dividers.forEach(({ el, target, minW, maxW, right }) => {
    el.addEventListener('mousedown', e => {
      e.preventDefault();
      el.classList.add('dragging');
      const startX = e.clientX;
      const startW = target.offsetWidth;
      const onMove = ev => {
        const dx = right ? startX - ev.clientX : ev.clientX - startX;
        const w = Math.max(minW, Math.min(maxW, startW + dx));
        target.style.width = w + 'px';
      };
      const onUp = () => {
        el.classList.remove('dragging');
        _saveWidths();
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
      };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    });
  });
}

function _saveCollapseState() {
  localStorage.setItem(_lsk('kh:collapse'), JSON.stringify({
    left1: _left1Collapsed, left2: _left2Collapsed,
    right: _rightCollapsed, rightPinned: _rightPinned,
  }));
}

function _applyCollapseState() {
  const $left1  = document.getElementById('khLeft1');
  const $left2  = document.getElementById('khLeft2');
  const $right  = document.getElementById('khRight');
  const $expL1  = document.getElementById('khExpandLeft1');
  const $expL2  = document.getElementById('khExpandLeft2');
  const $expR   = document.getElementById('khExpandRight');
  const $pinBtn = document.getElementById('khPinRight');

  // Left1
  $left1.classList.toggle('kh-collapsed', _left1Collapsed);
  $expL1.classList.toggle('hidden', !_left1Collapsed);

  // Left2
  $left2.classList.toggle('kh-collapsed', _left2Collapsed);
  $expL2.classList.toggle('hidden', !_left2Collapsed);

  // Right
  $right.classList.toggle('kh-collapsed', _rightCollapsed);
  $expR.classList.toggle('hidden', !_rightCollapsed);

  // Pin 按钮样式
  if ($pinBtn) $pinBtn.classList.toggle('pinned', _rightPinned);
}

function _bindCollapseExpand() {
  // Left1 折叠
  document.getElementById('khCollapseLeft1').addEventListener('click', () => {
    _left1Collapsed = true;
    _applyCollapseState(); _saveCollapseState();
  });
  // Left1 展开
  document.getElementById('khExpandLeft1').addEventListener('click', () => {
    _left1Collapsed = false;
    _applyCollapseState(); _saveCollapseState();
  });

  // Left2 折叠
  document.getElementById('khCollapseLeft2').addEventListener('click', () => {
    _left2Collapsed = true;
    _applyCollapseState(); _saveCollapseState();
  });
  // Left2 展开
  document.getElementById('khExpandLeft2').addEventListener('click', () => {
    _left2Collapsed = false;
    _applyCollapseState(); _saveCollapseState();
  });

  // Right 展开
  document.getElementById('khExpandRight').addEventListener('click', () => {
    _rightCollapsed = false;
    _applyCollapseState(); _saveCollapseState();
  });

  // Right Pin 按钮（toggle pinned，pinned 时不自动关闭）
  document.getElementById('khPinRight').addEventListener('click', () => {
    _rightPinned = !_rightPinned;
    if (_rightPinned && _rightCollapsed) {
      _rightCollapsed = false;
    }
    _applyCollapseState(); _saveCollapseState();
  });

  // Right 关闭按钮
  document.getElementById('khCollapseRight').addEventListener('click', () => {
    _rightCollapsed = true;
    _rightPinned = false;
    _applyCollapseState(); _saveCollapseState();
  });
}

// ── Left1 导航树 ─────────────────────────────────────────────────────────────
async function _loadPersonalFolders() {
  try {
    const res = await _bridge('list_folders', 'personal');
    _personalFolders = res?.data || [];
  } catch (e) {
    console.error('[KH] _loadPersonalFolders: ERROR', e);
    _personalFolders = [];
  }
}

async function _loadCloudFolders(scopeType, teamGid) {
  const key = scopeType === 'team' ? `team:${teamGid}` : 'public';
  if (!_isCloud()) { _cloudFolders[key] = []; return; }
  try {
    const cf = _cf();
    if (!cf) return;
    let url = `/api/knowledge_hub/folders?scope_type=${scopeType}`;
    if (teamGid) url += `&team_gid=${teamGid}`;
    const data = await cf(url);
    _cloudFolders[key] = Array.isArray(data) ? data : [];
  } catch (_) { _cloudFolders[key] = []; }
}

function _renderLeft1() {
  _navScroll.innerHTML = '';

  // 收藏
  _navScroll.appendChild(_makeSpecialNode('favorites', ICONS.star, '收藏'));
  // 最近
  _navScroll.appendChild(_makeSpecialNode('recent', ICONS.clock, '最近文件'));
  // 已标注
  _navScroll.appendChild(_makeSpecialNode('annotated', '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="17" x2="12" y2="22"/><path d="M5 17h14v-1.76a2 2 0 00-1.11-1.79l-1.78-.9A2 2 0 0115 10.76V6h1a2 2 0 000-4H8a2 2 0 000 4h1v4.76a2 2 0 01-1.11 1.79l-1.78.9A2 2 0 005 15.24z"/></svg>', '已标注'));
  _navScroll.appendChild(_makeSpecialNode('workspace', ICONS.team, '团队共创'));
  if (_isCloud() && _canEdit('public')) _navScroll.appendChild(_makeSpecialNode('migration', ICONS.clock, '迁移状态'));

  // 公共知识库
  const pubGroup = _makeNavGroup('public', ICONS.globe, '公共知识库', null,
    _cloudFolders['public'] || []);
  _navScroll.appendChild(pubGroup);

  // 个人知识库
  const personalGroup = _makeNavGroup('personal', ICONS.user, '个人知识库', null,
    _personalFolders);
  _navScroll.appendChild(personalGroup);
}

function _makeSpecialNode(key, iconSvg, label) {
  const el = document.createElement('div');
  el.className = `kh-nav-special${_activeNodeKey === key ? ' active' : ''}`;
  el.innerHTML = `<span class="kh-nav-special-icon">${iconSvg}</span><span>${_esc(label)}</span>`;
  el.addEventListener('click', () => _selectNode(key, null));
  return el;
}

function _makeNavGroup(scopeKey, iconSvg, label, teamGid, folders) {
  const grpKey = teamGid ? `team:${teamGid}` : scopeKey;
  const isOpen = _openGroups[grpKey] !== false;

  const wrap = document.createElement('div');
  wrap.className = 'kh-nav-group';

  const hdr = document.createElement('div');
  hdr.className = `kh-nav-group-hdr${isOpen ? ' open' : ''}`;
  hdr.dataset.key = grpKey;
  hdr.innerHTML = `${ICONS.chevron}
    <span class="kh-nav-group-icon">${iconSvg}</span>
    <span style="flex:1">${_esc(label)}</span>
    <button class="kh-nav-node-add" title="新建文件夹">+</button>`;
  hdr.querySelector('.kh-nav-node-add').addEventListener('click', e => {
    e.stopPropagation();
    _newFolder(null, scopeKey, teamGid);
  });
  hdr.addEventListener('click', () => {
    const open = _openGroups[grpKey] !== false;
    _openGroups[grpKey] = !open;
    localStorage.setItem(_lsk('kh:nav-open'), JSON.stringify(_openGroups));
    hdr.classList.toggle('open', !open);
    body.style.display = !open ? '' : 'none';
    // 点击组头：选择根节点（无文件夹）
    if (!open) _selectNode(scopeKey, null, teamGid);
  });
  // 组头作为「移至根级」drop 目标
  _enableDropTarget(hdr, null, scopeKey, teamGid);

  const body = document.createElement('div');
  body.className = 'kh-nav-group-body';
  body.style.display = isOpen ? '' : 'none';

  _buildFolderNodes(body, folders, null, scopeKey, teamGid, 0);

  wrap.appendChild(hdr);
  wrap.appendChild(body);
  return wrap;
}

function _buildFolderNodes(container, allFolders, parentGid, scopeKey, teamGid, depth) {
  const children = allFolders.filter(f => f.parent_gid === parentGid);
  if (depth === 0) {
    console.log(`[KH-DEBUG] _buildFolderNodes root: allFolders.length=${allFolders.length}, root children=${children.length}`);
    allFolders.forEach(f => console.log(`[KH-DEBUG]   folder: gid=${f.gid} name=${f.name} parent_gid=${JSON.stringify(f.parent_gid)} (type: ${typeof f.parent_gid})`));
  }
  children.forEach(folder => {
    const nodeKey = `folder:${folder.gid}`;
    const node = document.createElement('div');
    node.className = `kh-nav-node${_activeNodeKey === nodeKey ? ' active' : ''}`;
    node.style.paddingLeft = (12 + depth * 12) + 'px';
    node.dataset.folderGid = folder.gid;
    node.innerHTML = `<span class="kh-nav-node-icon">${ICONS.folder}</span>
      <span class="kh-nav-node-label">${_esc(folder.name)}</span>
      <button class="kh-nav-node-add" title="新建子文件夹">+</button>`;
    node.querySelector('.kh-nav-node-add').addEventListener('click', e => {
      e.stopPropagation();
      _newFolder(folder.gid, scopeKey, teamGid);
    });
    node.addEventListener('click', () => _selectNode(scopeKey, folder.gid, teamGid));
    node.addEventListener('contextmenu', e => {
      e.preventDefault();
      _showDropdown({ getBoundingClientRect: () => ({ left: e.clientX, top: e.clientY, width: 0, height: 0 }) }, [
        { label: '重命名', action: () => _renameFolder(folder, scopeKey, teamGid) },
        { label: '新建子文件夹', action: () => _newFolder(folder.gid, scopeKey, teamGid) },
        { sep: true },
        { label: '删除', action: () => _deleteFolder(folder, scopeKey, teamGid) },
      ]);
    });
    _enableFolderDrag(node, folder, scopeKey, teamGid, allFolders);
    _enableDropTarget(node, folder.gid, scopeKey, teamGid);
    container.appendChild(node);
    // 递归子文件夹
    _buildFolderNodes(container, allFolders, folder.gid, scopeKey, teamGid, depth + 1);
  });
}

// ── 选择导航节点 ─────────────────────────────────────────────────────────────
async function _selectNode(scope, folderGid, teamGid) {
  _currentScope     = scope;
  _currentFolderGid = folderGid;
  _currentTeamGid   = teamGid || null;

  // 更新激活状态
  if (scope === 'favorites') _activeNodeKey = 'favorites';
  else if (scope === 'recent') _activeNodeKey = 'recent';
  else if (scope === 'workspace') _activeNodeKey = 'workspace';
  else if (scope === 'migration') _activeNodeKey = 'migration';
  else if (folderGid) _activeNodeKey = `folder:${folderGid}`;
  else _activeNodeKey = scope;

  _renderLeft1();  // 重渲导航树更新高亮

  // 加载文件列表
  await _loadItems();
  _renderLeft2();
}

// ── Left2 文件列表 ────────────────────────────────────────────────────────────
async function _loadItems() {
  _items = [];
  try {
    if (_currentScope === 'migration') {
      const result = await _invokeCapability('knowledge.migration.status', { scan_limit: 10000 });
      _migrationSnapshot = result?.data || null;
      _items = (_migrationSnapshot?.runs || []).map(run => ({ ...run, gid: run.gid, title: 迁移 , _migrationRun: true }));
      return;
    }
    if (_currentScope === 'workspace') {
      if (!_isCloud()) return;
      const result = await _invokeCapability('knowledge.document.search', { query: '', limit: 50 });
      _items = (result?.data?.items || []).map(doc => ({
        ...doc, gid: doc.document_gid, item_type: 'markdown', scope_type: 'team',
        status: doc.state || 'published', updated_at: '', _revisionDocument: true,
      }));
      return;
    }
    if (_currentScope === 'annotated') {
      const cf = _cf();
      if (cf) {
        const anns = (await cf('/api/self_ann/list?module=knowledge_hub').catch(() => null)) || [];
        // 将标注记录映射为 file-row 可渲染的 item 结构
        _items = anns.map(a => ({
          gid:        a.item_gid,
          title:      a.item_title || a.item_gid,
          item_type:  'richtext',
          status:     '',
          updated_at: a.updated_at,
          _annotation: a,
        }));
      }
      return;
    }
    if (_currentScope === 'favorites') {
      if (_isCloud()) {
        const cf = _cf();
        if (cf) _items = (await cf('/api/knowledge_hub/favorites')) || [];
      } else {
        const res = await _bridge('list_favorites');
        _items = res?.data || [];
      }
      return;
    }
    if (_currentScope === 'recent') {
      if (_isCloud()) {
        const cf = _cf();
        if (cf) _items = (await cf('/api/knowledge_hub/recent')) || [];
      } else {
        const res = await _bridge('list_recent', 20);
        _items = res?.data || [];
      }
      return;
    }
    if (_currentScope === 'personal') {
      const res = await _bridge('list_items', _currentFolderGid || null);
      _items = res?.data || [];
    } else {
      // cloud (public / team)
      if (!_isCloud()) { _items = []; return; }
      const cf = _cf();
      if (!cf) return;
      let url = `/api/knowledge_hub/items?scope_type=${_currentScope}`;
      if (_currentFolderGid) url += `&folder_gid=${_currentFolderGid}`;
      if (_currentTeamGid)   url += `&team_gid=${_currentTeamGid}`;
      if (_getAuthRole() === 'super_admin') url += '&show_hidden=true';
      _items = (await cf(url)) || [];
    }
  } catch (_) {}
}

function _renderLeft2() {
  _listScroll.innerHTML = '';
  if (_currentScope === 'migration') {
    _renderMigrationRunList();
    _renderMigrationStatus();
    return;
  }

  let items = _items;

  // 搜索过滤
  if (_searchQuery) {
    items = items.filter(it => it.title?.toLowerCase().includes(_searchQuery));
  }

  // 排序（置顶优先）
  items = [...items].sort((a, b) => {
    // pinned / is_system 置顶
    const pa = (a.is_pinned || a.is_system) ? 1 : 0;
    const pb = (b.is_pinned || b.is_system) ? 1 : 0;
    if (pa !== pb) return pb - pa;
    if (_sortBy === 'title') return (a.title || '').localeCompare(b.title || '');
    if (_sortBy === 'created') return (b.created_at || '') > (a.created_at || '') ? 1 : -1;
    return (b.updated_at || '') > (a.updated_at || '') ? 1 : -1;
  });

  if (!items.length) {
    _listScroll.innerHTML = `<div class="kh-empty-hint">暂无文件<br>点击 + 添加</div>`;
    return;
  }

  // 分组
  if (_groupBy === 'none') {
    items.forEach(it => _listScroll.appendChild(_makeFileRow(it, _currentScope, _currentTeamGid)));
  } else if (_groupBy === 'date') {
    const groups = {};
    items.forEach(it => {
      const key = _dateGroup(it.created_at);
      (groups[key] = groups[key] || []).push(it);
    });
    ['今天', '本周', '更早'].forEach(k => {
      if (!groups[k]?.length) return;
      const lbl = document.createElement('div');
      lbl.className = 'kh-group-label'; lbl.textContent = k;
      _listScroll.appendChild(lbl);
      groups[k].forEach(it => _listScroll.appendChild(_makeFileRow(it, _currentScope, _currentTeamGid)));
    });
  } else if (_groupBy === 'status') {
    const groups = {};
    items.forEach(it => (groups[it.status || 'draft'] = groups[it.status || 'draft'] || []).push(it));
    [['draft','草稿'], ['published','已发布'], ['archived','已归档']].forEach(([k, lbl]) => {
      if (!groups[k]?.length) return;
      const el = document.createElement('div');
      el.className = 'kh-group-label'; el.textContent = lbl;
      _listScroll.appendChild(el);
      groups[k].forEach(it => _listScroll.appendChild(_makeFileRow(it, _currentScope, _currentTeamGid)));
    });
  }

  // 批量拉取自我标注指示器
  _loadSapIndicators(_items.map(it => it.gid).filter(Boolean));
}

// ── 自我标注批量指示器 ─────────────────────────────────────────────────────
async function _loadSapIndicators(gids) {
  if (!gids.length) return;
  const cf = _cf();
  if (!cf) return;
  for (let i = 0; i < gids.length; i += 500) {
    const chunk = gids.slice(i, i + 500);
    const res = await cf(`/api/self_ann/batch?gids=${chunk.join(',')}`).catch(() => null);
    if (!res) return;
    Object.entries(res).forEach(([gid, info]) => {
      document.querySelectorAll(`.sap-row-pin[data-gid="${gid}"]`).forEach(el => {
        if (info.status) el.dataset.status = info.status;
        else delete el.dataset.status;
      });
    });
  }
}

function _dateGroup(ts) {
  if (!ts) return '更早';
  const d = new Date(ts), now = new Date();
  const diff = now - d;
  if (diff < 86400000) return '今天';
  if (diff < 604800000) return '本周';
  return '更早';
}

function _makeFileMeta(item) {
  if (item._annotation) {
    const a = item._annotation;
    const parts = [];
    if (a.self_status) parts.push(`<span class="kh-annot-schedule">${_esc(a.self_status)}</span>`);
    if (a.self_schedule) parts.push(`<span class="kh-annot-schedule">📅 ${_esc(a.self_schedule)}</span>`);
    if (a.self_note) {
      const snip = a.self_note.slice(0, 28) + (a.self_note.length > 28 ? '…' : '');
      parts.push(`<span class="kh-annot-note" title="${a.self_note.replace(/"/g,'&quot;')}">📝 ${_esc(snip)}</span>`);
    }
    return parts.length ? parts.join('') : _fmt(item.updated_at);
  }
  return _fmt(item.updated_at);
}

function _makeFileRow(item, scopeKey, teamGid) {
  const el = document.createElement('div');
  el.className = `kh-file-row${_currentItem?.gid === item.gid ? ' active' : ''}`;
  const iconSvg = ICONS[item.item_type] || ICONS.richtext;
  const statusLabel = { draft: '草稿', published: '已发布', archived: '已归档' }[item.status] || '';
  const statusCls = item.status || 'draft';
  // 系统内置或置顶条目显示 pin 角标
  const pinBadge = (item.is_system || item.is_pinned)
    ? `<span style="font-size:10px;color:var(--accent);margin-left:4px;opacity:.8" title="置顶">
        <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="M16 4l-8 8 2 6 2-2 4 4 2-2-4-4 2-2z"/></svg>
       </span>`
    : '';
  // 隐藏条目角标（仅超管可见）
  const hideBadge = item.is_hidden
    ? `<span style="font-size:10px;color:var(--danger);margin-left:4px;opacity:.7" title="已隐藏（仅超管可见）">
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
       </span>`
    : '';
  el.innerHTML = `
    <span class="kh-file-icon">${iconSvg}</span>
    <div class="kh-file-info">
      <div class="kh-file-title">${window.VisibilitySelector ? VisibilitySelector.renderBadge(
        item.scope_type === 'personal' ? 'private' : (item.scope_type || 'public')
      ) : ''}${_esc(item.title || '未命名')}${pinBadge}${hideBadge}</div>
      <div class="kh-file-meta">${_makeFileMeta(item)}</div>
    </div>
    <span class="kh-file-status ${statusCls}">${_esc(statusLabel)}</span>`;

  // 自我标注 pin 图标
  if (item.gid) {
    const sapPin = document.createElement('span');
    sapPin.className = 'sap-row-pin';
    sapPin.title = '自我标注';
    sapPin.dataset.gid = item.gid;
    sapPin.innerHTML = '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="17" x2="12" y2="22"/><path d="M5 17h14v-1.76a2 2 0 00-1.11-1.79l-1.78-.9A2 2 0 0115 10.76V6h1a2 2 0 000-4H8a2 2 0 000 4h1v4.76a2 2 0 01-1.11 1.79l-1.78.9A2 2 0 005 15.24z"/></svg>';
    sapPin.addEventListener('click', e => {
      e.stopPropagation();
      window.SelfAnnotationPanel?.open(item.gid, item.title || '', e.currentTarget);
    });
    el.appendChild(sapPin);
  }

  el.addEventListener('click', () => _openItem(item));
  if (item._revisionDocument) return el;
  // 右键菜单
  el.addEventListener('contextmenu', e => {
    e.preventDefault();
    const isAdmin = _getAuthRole() === 'super_admin';
    const canDelete = !item.is_system || isAdmin;
    const menuItems = [
      { label: '重命名', action: isAdmin ? () => _renameItem(item) : null },
      { label: '移动到文件夹…', action: isAdmin ? () => _moveItem(item) : null },
      { sep: true },
      { label: '设置可见范围…', action: isAdmin ? () => _setItemVisibility(item) : null },
      { sep: true },
      { label: item.is_pinned ? '取消置顶' : '全局置顶', action: isAdmin ? () => _togglePinItem(item) : null },
      { label: item.is_hidden ? '取消隐藏' : '全局隐藏', action: isAdmin ? () => _toggleHideItem(item) : null },
      { sep: true },
      { label: '删除', action: canDelete ? () => _deleteItem(item) : null },
    ].filter(m => m.sep || m.action);
    if (menuItems.length) {
      _showDropdown(
        { getBoundingClientRect: () => ({ left: e.clientX, top: e.clientY, width: 0, height: 0 }) },
        menuItems
      );
    }
  });
  _enableItemDrag(el, item, scopeKey || _currentScope, teamGid !== undefined ? teamGid : _currentTeamGid);
  return el;
}

// ── 重命名条目（超管） ───────────────────────────────────────────────────────
async function _renameItem(item) {
  const newTitle = await _promptText('重命名', '新名称', item.title || '');
  if (newTitle === null || newTitle === item.title) return;
  try {
    if (_currentScope === 'personal') {
      await _bridge('update_item', { gid: item.gid, title: newTitle });
    } else if (_isCloud()) {
      const cf = _cf();
      if (cf) await cf(`/api/knowledge_hub/items/${item.gid}`, { method: 'PATCH', body: JSON.stringify({ title: newTitle }) });
    }
    item.title = newTitle;
    if (_currentItem?.gid === item.gid) _centerTitle.textContent = newTitle;
    _renderLeft2();
    _showToast('已重命名');
  } catch (e) {
    _showToast('重命名失败：' + (e?.message || e));
  }
}

// ── 移动到文件夹（超管） ─────────────────────────────────────────────────────
async function _moveItem(item) {
  // 获取当前 scope 下的文件夹列表
  let folders = [];
  if (_currentScope === 'personal') {
    folders = _personalFolders;
  } else {
    const key = _currentScope === 'team' ? `team:${_currentTeamGid}` : 'public';
    folders = _cloudFolders[key] || [];
  }
  // 构建选项
  const options = [{ gid: null, name: '（根目录）' }, ...folders.map(f => ({ gid: f.gid, name: f.name }))];
  const fields = [{
    key: 'folder_gid', label: '目标文件夹', type: 'select',
    options: options.map(o => ({ value: o.gid || '', label: o.name })),
  }];
  const res = await _promptForm('移动到文件夹', fields);
  if (!res) return;
  const targetGid = res.folder_gid || null;
  if (targetGid === item.folder_gid) return;
  try {
    if (_currentScope === 'personal') {
      await _bridge('update_item', { gid: item.gid, folder_gid: targetGid });
    } else if (_isCloud()) {
      const cf = _cf();
      if (cf) await cf(`/api/knowledge_hub/items/${item.gid}`, { method: 'PATCH', body: JSON.stringify({ folder_gid: targetGid }) });
    }
    item.folder_gid = targetGid;
    // 如果移出了当前文件夹，从列表移除
    if (_currentFolderGid && targetGid !== _currentFolderGid) {
      _items = _items.filter(i => i.gid !== item.gid);
    }
    _renderLeft2();
    _showToast('已移动');
  } catch (e) {
    _showToast('移动失败：' + (e?.message || e));
  }
}

// ── 设置可见范围 ──────────────────────────────────────────────────────────────
async function _setItemVisibility(item) {
  if (!window.VisibilitySelector) return;
  // 将 knowledge_hub scope_type 映射到 visibility
  const scopeToVis = { personal: 'private', team: 'team', project: 'project', public: 'public' };
  const visToScope = { private: 'personal', team: 'team', project: 'project', public: 'public' };
  const itemForDialog = {
    ...item,
    name:               item.title || item.name,
    visibility:         scopeToVis[item.scope_type] || 'public',
    shared_team_gid:    item.team_gid            || null,
    shared_project_gid: item.shared_project_gid  || null,
  };
  await VisibilitySelector.showDialog(itemForDialog, async (val) => {
    const cf = _cf();
    if (!cf) return;
    await cf(`/api/knowledge_hub/items/${item.gid}`, {
      method: 'PATCH',
      body: JSON.stringify({
        scope_type:         visToScope[val.visibility] || 'public',
        team_gid:           val.shared_team_gid    || null,
        shared_project_gid: val.shared_project_gid || null,
      }),
    });
    item.scope_type         = visToScope[val.visibility] || 'public';
    item.team_gid           = val.shared_team_gid    || null;
    item.shared_project_gid = val.shared_project_gid || null;
    _renderLeft2();
    _showToast('可见范围已更新');
  });
}

// ── 切换置顶（超管） ─────────────────────────────────────────────────────────
async function _togglePinItem(item) {
  const newVal = !item.is_pinned;
  try {
    if (_currentScope === 'personal') {
      await _bridge('update_item', { gid: item.gid, is_pinned: newVal });
    } else if (_isCloud()) {
      const cf = _cf();
      if (cf) await cf(`/api/knowledge_hub/items/${item.gid}`, { method: 'PATCH', body: JSON.stringify({ is_pinned: newVal }) });
    }
    item.is_pinned = newVal;
    _renderLeft2();
    _showToast(newVal ? '已置顶' : '已取消置顶');
  } catch (e) {
    _showToast('操作失败：' + (e?.message || e));
  }
}

// ── 切换隐藏（超管） ─────────────────────────────────────────────────────────
async function _toggleHideItem(item) {
  const newVal = !item.is_hidden;
  const msg = newVal ? '隐藏后非超管将看不到此条目，确定？' : '取消隐藏？';
  if (newVal && !(await _confirmDialog(msg))) return;
  try {
    if (_currentScope === 'personal') {
      await _bridge('update_item', { gid: item.gid, is_hidden: newVal });
    } else if (_isCloud()) {
      const cf = _cf();
      if (cf) await cf(`/api/knowledge_hub/items/${item.gid}`, { method: 'PATCH', body: JSON.stringify({ is_hidden: newVal }) });
    }
    item.is_hidden = newVal;
    _renderLeft2();
    _showToast(newVal ? '已隐藏' : '已取消隐藏');
  } catch (e) {
    _showToast('操作失败：' + (e?.message || e));
  }
}

// ── 删除条目 ──────────────────────────────────────────────────────────────────
async function _deleteItem(item) {
  const ok = await _confirmDialog(`确定要删除「${item.title || '未命名'}」吗？`);
  if (!ok) return;
  try {
    if (_currentScope === 'personal') {
      await _bridge('delete_item', item.gid);
    } else if (_isCloud()) {
      const cf = _cf();
      if (cf) await cf(`/api/knowledge_hub/items/${item.gid}`, { method: 'DELETE' });
    }
    _items = _items.filter(i => i.gid !== item.gid);
    if (_currentItem?.gid === item.gid) {
      _currentItem = null;
      _centerTitle.textContent = '—';
      _centerBody.innerHTML = '';
    }
    _renderLeft2();
  } catch (e) {
    const msg = e?.body?.detail || e?.message || String(e);
    _showToast(msg);
  }
}

// ── 工具：防抖 ────────────────────────────────────────────────────────────────
function _debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

function _renderMigrationRunList() {
  const runs = _migrationSnapshot?.runs || [];
  if (!runs.length) {
    _listScroll.innerHTML = '<div class="kh-empty-hint">暂无迁移执行记录</div>';
    return;
  }
  runs.forEach(run => {
    const row = document.createElement('button');
    row.className = 'kh-migration-run-row';
    row.innerHTML = `<strong>${_esc(run.status || 'unknown')}</strong>` +
      `<span>${_esc(_fmt(run.created_at))} · ${Number(run.copied_count || 0)} 已复制 · ${Number(run.failed_count || 0)} 失败</span>`;
    row.addEventListener('click', () => _renderMigrationStatus(run.gid));
    _listScroll.appendChild(row);
  });
}

async function _renderMigrationStatus(runGid = '') {
  try {
    if (runGid) {
      const result = await _invokeCapability('knowledge.migration.status', { scan_limit: 10000, run_gid: runGid });
      _migrationSnapshot = result?.data || _migrationSnapshot;
    }
    const snapshot = _migrationSnapshot;
    if (!snapshot) return;
    const inv = snapshot.inventory || {};
    _centerTitle.textContent = '遗留知识迁移状态';
    _centerBody.style.cssText = 'overflow:auto;padding:20px;';
    _centerBody.innerHTML = '';
    const header = document.createElement('div');
    header.className = 'kh-migration-header';
    header.innerHTML = `<div><h2>迁移盘点</h2><p>这里只展示状态。实际迁移由部署作业执行，不在网页请求中运行。</p></div>`;
    const refresh = document.createElement('button');
    refresh.className = 'kh-revision-btn';
    refresh.textContent = '刷新';
    refresh.addEventListener('click', async () => {
      const result = await _invokeCapability('knowledge.migration.status', { scan_limit: 10000, ...(runGid ? { run_gid: runGid } : {}) });
      _migrationSnapshot = result?.data || null;
      _listScroll.innerHTML = '';
      _renderMigrationRunList();
      _renderMigrationStatus(runGid);
    });
    header.appendChild(refresh);
    _centerBody.appendChild(header);
    const cards = document.createElement('div');
    cards.className = 'kh-migration-cards';
    const metrics = [
      ['本团队可迁移', inv.eligible], ['已迁移', inv.migrated], ['待迁移', inv.pending],
      ['需人工归属', inv.quarantined], ['其他团队（已排除）', inv.other_tenant], ['已扫描', inv.scanned],
    ];
    metrics.forEach(([label, value]) => {
      const card = document.createElement('div');
      card.innerHTML = `<strong>${Number(value || 0)}</strong><span>${_esc(label)}</span>`;
      cards.appendChild(card);
    });
    _centerBody.appendChild(cards);
    const notice = document.createElement('div');
    notice.className = 'kh-migration-notice';
    notice.textContent = inv.source_retained
      ? '源 content_md 保留；无法确定团队归属的条目不会自动迁移。'
      : '警告：未确认源数据保留策略。';
    _centerBody.appendChild(notice);
    if (inv.scan_truncated) {
      const truncated = document.createElement('div');
      truncated.className = 'kh-migration-warning';
      truncated.textContent = `盘点达到 ${Number(inv.scan_limit || 0)} 条上限，当前数字不是全量结果。`;
      _centerBody.appendChild(truncated);
    }
    if (runGid) {
      const title = document.createElement('h3');
      title.className = 'kh-migration-items-title';
      title.textContent = `作业明细 ${runGid}`;
      _centerBody.appendChild(title);
      const table = document.createElement('div');
      table.className = 'kh-migration-items';
      for (const item of (snapshot.items || [])) {
        const row = document.createElement('div');
        row.innerHTML = `<code>${_esc(item.entry_gid)}</code><strong>${_esc(item.status)}</strong>` +
          `<span>${_esc(item.error_message || String(item.content_sha256 || '').slice(0, 12))}</span>`;
        table.appendChild(row);
      }
      if (!(snapshot.items || []).length) table.innerHTML = '<div class="kh-empty-hint">该作业暂无条目明细</div>';
      _centerBody.appendChild(table);
    }
  } catch (error) {
    _centerBody.innerHTML = `<div style="padding:20px;color:#f38ba8">迁移状态读取失败：${_esc(error?.message || error)}</div>`;
  }
}
async function _createWorkspaceDocument() {
  const title = await _promptText('新建团队共创文档', '标题', '');
  if (!title) return;
  try {
    let spaces = (await _invokeCapability('knowledge.space.list', {}))?.data?.items || [];
    if (!spaces.length) {
      if (!(await _confirmDialog('当前团队还没有共创空间，是否创建默认的“团队知识”空间？'))) return;
      const created = await _confirmAndInvokeCapability('knowledge.space.create', { name: '团队知识', visibility: 'team' });
      spaces = [created.data];
    }
    let space = spaces[0];
    if (spaces.length > 1) {
      const selected = await _promptForm('选择共创空间', [{
        key: 'space_gid', label: '空间', type: 'select',
        options: spaces.map(row => ({ value: row.gid, label: row.name })),
      }]);
      if (!selected) return;
      space = spaces.find(row => String(row.gid) === String(selected.space_gid));
    }
    if (!space) throw new Error('没有可写入的共创空间');
    if (!(await _confirmDialog(`发布团队文档“${title}”的第 1 个版本？`))) return;
    const result = await _confirmAndInvokeCapability('knowledge.document.create', {
      space_gid: space.gid,
      title,
      slug: `doc-${Date.now().toString(36)}`,
      markdown: `# ${title}\n`,
      visibility: 'team',
    });
    await _loadItems();
    _renderLeft2();
    const created = result.data || {};
    const item = {
      ...created, gid: created.document_gid, document_gid: created.document_gid,
      title, item_type: 'markdown', scope_type: 'team', status: 'published',
      _revisionDocument: true,
    };
    await _openItem(item);
    _showToast('团队文档已创建');
  } catch (error) {
    _showToast('创建失败：' + (error?.message || error));
  }
}

async function _renderWorkspaceDocument(item, revisionGid = '') {
  _centerBody.innerHTML = '<div class="kh-empty-hint">正在读取已发布版本…</div>';
  _centerBody.style.cssText = 'display:flex;flex-direction:column;height:100%;overflow:hidden;';
  try {
    const result = await _invokeCapability('knowledge.document.get', {
      document_gid: item.document_gid || item.gid,
      ...(revisionGid ? { revision_gid: revisionGid } : {}),
    });
    const doc = result.data || {};
    const isHistorical = !!revisionGid && String(revisionGid) !== String(item.revision_gid || '');
    let content = doc.markdown || '';
    let editing = false;
    _centerTitle.textContent = doc.title || item.title || '未命名';
    _centerBody.innerHTML = '';

    const toolbar = document.createElement('div');
    toolbar.className = 'kh-revision-toolbar';
    const primary = document.createElement('button');
    primary.className = 'kh-revision-btn primary';
    primary.textContent = isHistorical ? '恢复为新版本' : '编辑';
    const history = document.createElement('button');
    history.className = 'kh-revision-btn';
    history.textContent = '版本历史';
    const access = document.createElement('button');
    access.className = 'kh-revision-btn';
    access.textContent = '访问权限';
    const back = document.createElement('button');
    back.className = 'kh-revision-btn';
    back.textContent = '返回当前版本';
    back.style.display = isHistorical ? '' : 'none';
    const status = document.createElement('span');
    status.className = 'kh-revision-status';
    status.textContent = `版本 ${doc.revision_no || '-'} · ${String(doc.content_sha256 || '').slice(0, 12)}`;
    toolbar.append(primary, history, access, back, status);

    const preview = document.createElement('div');
    preview.className = 'kh-revision-preview';
    const editor = document.createElement('textarea');
    editor.className = 'kh-revision-editor';
    editor.style.display = 'none';
    const renderPreview = () => {
      preview.innerHTML = window.marked ? marked.parse(content) : `<pre>${_esc(content)}</pre>`;
    };
    renderPreview();
    _centerBody.append(toolbar, preview, editor);

    history.addEventListener('click', () => _loadWorkspaceHistory(item));
    access.addEventListener('click', () => _showWorkspaceAcl(item));
    back.addEventListener('click', () => _renderWorkspaceDocument(item));
    primary.addEventListener('click', async () => {
      if (isHistorical) {
        if (!(await _confirmDialog(`把版本 ${doc.revision_no} 的内容恢复为一个新版本？历史不会被覆盖。`))) return;
        try {
          const restored = await _confirmAndInvokeCapability('knowledge.document.rollback', {
            document_gid: item.document_gid || item.gid,
            target_revision_gid: doc.revision_gid,
          });
          item.revision_gid = restored.data?.revision_gid;
          await _renderWorkspaceDocument(item);
          await _loadWorkspaceHistory(item);
          _showToast('已恢复并发布为新版本');
        } catch (error) { _showToast('恢复失败：' + (error?.message || error)); }
        return;
      }
      if (!editing) {
        editing = true;
        editor.value = content;
        preview.style.display = 'none';
        editor.style.display = 'block';
        primary.textContent = '发布新版本';
        editor.focus();
        return;
      }
      const next = editor.value;
      if (!(await _confirmDialog('确认发布新版本？发布后旧版本仍会保留。'))) return;
      status.textContent = '正在发布…';
      try {
        const revised = await _confirmAndInvokeCapability('knowledge.document.revise', {
          document_gid: item.document_gid || item.gid,
          title: doc.title || item.title,
          markdown: next,
        });
        content = next;
        item.revision_gid = revised.data?.revision_gid;
        item.revision_no = revised.data?.revision_no;
        editing = false;
        editor.style.display = 'none';
        preview.style.display = '';
        primary.textContent = '编辑';
        renderPreview();
        status.textContent = `版本 ${revised.data?.revision_no || '-'} · ${String(revised.data?.content_sha256 || '').slice(0, 12)}`;
        _showToast('新版本已发布');
      } catch (error) {
        status.textContent = '发布失败';
        _showToast('发布失败：' + (error?.message || error));
      }
    });
    await _loadWorkspaceHistory(item);
  } catch (error) {
    _centerBody.innerHTML = `<div style="padding:20px;color:#f38ba8">读取失败：${_esc(error?.message || error)}</div>`;
  }
}

async function _loadWorkspaceHistory(item) {
  try {
    const result = await _invokeCapability('knowledge.document.revisions', {
      document_gid: item.document_gid || item.gid, limit: 100,
    });
    const revisions = result.data?.items || [];
    _rightBody.innerHTML = '';
    const header = document.createElement('div');
    header.className = 'kh-revision-history-title';
    header.textContent = `不可变版本历史（${revisions.length}）`;
    _rightBody.appendChild(header);
    revisions.forEach(revision => {
      const row = document.createElement('div');
      row.className = 'kh-revision-history-row';
      const main = document.createElement('button');
      main.className = 'kh-revision-history-main';
      const restored = revision.restored_from_revision_gid ? ' · 恢复版本' : '';
      main.innerHTML = `<strong>版本 ${Number(revision.revision_no) || '-'}</strong>` +
        `<span>${_esc(_fmt(revision.created_at))}${restored}</span>` +
        `<code>${_esc(String(revision.content_sha256 || '').slice(0, 12))}</code>`;
      main.addEventListener('click', () => _renderWorkspaceDocument(item, revision.revision_gid));
      row.appendChild(main);
      if (String(revision.revision_gid) !== String(item.revision_gid || '')) {
        const compare = document.createElement('button');
        compare.className = 'kh-revision-compare';
        compare.textContent = '与当前比较';
        compare.addEventListener('click', () => _showWorkspaceDiff(item, revision.revision_gid));
        row.appendChild(compare);
      }
      _rightBody.appendChild(row);
    });
  } catch (error) {
    _rightBody.innerHTML = `<div class="kh-right-placeholder">版本历史读取失败：${_esc(error?.message || error)}</div>`;
  }
}
async function _showWorkspaceAcl(item) {
  const documentGid = item.document_gid || item.gid;
  try {
    const aclResult = await _invokeCapability('knowledge.document.acl.list', { document_gid: documentGid });
    const authUser = window.parent?._authUser || window._authUser || {};
    const teamGid = authUser.team_id || authUser.team_gid || '';
    const cf = _cf();
    const memberResponse = teamGid && cf ? await cf(`/api/teams/${encodeURIComponent(teamGid)}/members`) : null;
    const members = memberResponse?.data || [];
    const memberMap = new Map(members.map(member => [String(member.gid), member]));
    const overlay = document.createElement('div');
    overlay.className = 'kh-modal-overlay';
    const modal = document.createElement('div');
    modal.className = 'kh-modal kh-acl-modal';
    modal.innerHTML = '<h3>文档访问权限</h3>';
    const list = document.createElement('div');
    list.className = 'kh-acl-list';
    const permissions = { view: '查看', edit: '编辑', admin: '管理' };
    for (const entry of (aclResult.data?.items || [])) {
      const row = document.createElement('div');
      row.className = 'kh-acl-row';
      const member = memberMap.get(String(entry.subject_gid));
      const name = entry.subject_type === 'team' ? '当前团队' : (member?.name || member?.email || entry.subject_gid);
      const label = document.createElement('span');
      label.innerHTML = `<strong>${_esc(name)}</strong><small>${_esc(permissions[entry.permission] || entry.permission)}</small>`;
      row.appendChild(label);
      if (!(entry.subject_type === 'user' && String(entry.subject_gid) === String(authUser.gid || authUser.user_gid || ''))) {
        const remove = document.createElement('button');
        remove.className = 'kh-revision-compare';
        remove.textContent = '撤销';
        remove.addEventListener('click', async () => {
          if (!(await _confirmDialog(`撤销“${name}”的文档权限？`))) return;
          try {
            await _confirmAndInvokeCapability('knowledge.document.acl.revoke', {
              document_gid: documentGid,
              subject_type: entry.subject_type,
              subject_gid: entry.subject_gid,
            });
            row.remove();
            _showToast('权限已撤销');
          } catch (error) { _showToast('撤销失败：' + (error?.message || error)); }
        });
        row.appendChild(remove);
      }
      list.appendChild(row);
    }
    modal.appendChild(list);
    const footer = document.createElement('div');
    footer.className = 'kh-modal-footer';
    const add = document.createElement('button');
    add.className = 'kh-btn-primary';
    add.textContent = '添加成员';
    const close = document.createElement('button');
    close.className = 'kh-btn-ghost';
    close.textContent = '关闭';
    close.addEventListener('click', () => overlay.remove());
    add.addEventListener('click', async () => {
      const existing = new Set((aclResult.data?.items || []).filter(row => row.subject_type === 'user').map(row => String(row.subject_gid)));
      const choices = members.filter(member => !existing.has(String(member.gid)));
      if (!choices.length) { _showToast('没有可添加的团队成员'); return; }
      const selected = await _promptForm('添加文档成员', [
        { key: 'subject_gid', label: '成员', type: 'select', options: choices.map(member => ({ value: member.gid, label: member.name || member.email || member.gid })) },
        { key: 'permission', label: '权限', type: 'select', options: [
          { value: 'view', label: '查看' }, { value: 'edit', label: '编辑' }, { value: 'admin', label: '管理' },
        ] },
      ]);
      if (!selected) return;
      const member = memberMap.get(String(selected.subject_gid));
      if (!(await _confirmDialog(`授予“${member?.name || selected.subject_gid}”${permissions[selected.permission]}权限？`))) return;
      try {
        await _confirmAndInvokeCapability('knowledge.document.acl.grant', {
          document_gid: documentGid,
          subject_type: 'user',
          subject_gid: selected.subject_gid,
          permission: selected.permission,
        });
        overlay.remove();
        await _showWorkspaceAcl(item);
        _showToast('权限已授予');
      } catch (error) { _showToast('授权失败：' + (error?.message || error)); }
    });
    footer.append(close, add);
    modal.appendChild(footer);
    overlay.appendChild(modal);
    overlay.addEventListener('click', event => { if (event.target === overlay) overlay.remove(); });
    document.body.appendChild(overlay);
  } catch (error) {
    _showToast('权限读取失败：' + (error?.message || error));
  }
}
async function _showWorkspaceDiff(item, fromRevisionGid) {
  const currentRevisionGid = item.revision_gid;
  if (!currentRevisionGid) {
    _showToast('当前版本标识缺失，请刷新文档列表');
    return;
  }
  _centerBody.innerHTML = '<div class="kh-empty-hint">正在计算版本差异…</div>';
  try {
    const result = await _invokeCapability('knowledge.document.diff', {
      document_gid: item.document_gid || item.gid,
      from_revision_gid: fromRevisionGid,
      to_revision_gid: currentRevisionGid,
    });
    _centerBody.innerHTML = '';
    _centerBody.style.cssText = 'display:flex;flex-direction:column;height:100%;overflow:hidden;';
    const toolbar = document.createElement('div');
    toolbar.className = 'kh-revision-toolbar';
    const back = document.createElement('button');
    back.className = 'kh-revision-btn';
    back.textContent = '返回当前版本';
    back.addEventListener('click', () => _renderWorkspaceDocument(item));
    const label = document.createElement('span');
    label.className = 'kh-revision-status';
    label.textContent = '历史版本 → 当前版本';
    toolbar.append(back, label);
    const diff = document.createElement('pre');
    diff.className = 'kh-revision-diff';
    diff.textContent = result.data?.diff || '两个版本内容相同';
    _centerBody.append(toolbar, diff);
  } catch (error) {
    _centerBody.innerHTML = `<div style="padding:20px;color:#f38ba8">差异读取失败：${_esc(error?.message || error)}</div>`;
  }
}
// ── Center 内容渲染 ────────────────────────────────────────────────────────────
async function _openItem(item) {
  _currentItem = item;
  _centerTitle.textContent = item.title || '未命名';

  _renderLeft2();
  if (item._revisionDocument) {
    await _renderWorkspaceDocument(item);
    return;
  }
  _recordRecent(item);

  // 清空 center，重置样式
  _centerBody.innerHTML = '';
  _centerBody.style.cssText = '';

  const scope = _currentScope === 'personal' ? 'local' : 'cloud';

  // ── Markdown：自定义内联编辑器（支持编辑+自动保存）────────────────────────
  if (item.item_type === 'markdown') {
    _renderMarkdownCenter(item, scope);
    _loadThread(item);
    return;
  }

  // ── 网络链接（weblink）：直接嵌入 webview ────────────────────────────────
  if (item.item_type === 'weblink') {
    const cm = window.ContainerModes?.['webview'];
    if (cm?.renderFullPage) {
      try {
        _centerBody.style.cssText = 'height:100%;overflow:hidden;';
        cm.renderFullPage(_centerBody, { url: item.url || '' });
      } catch (e) {
        _centerBody.innerHTML = `<div style="padding:16px;color:#f38ba8">渲染失败：${_esc(String(e))}</div>`;
      }
    } else {
      _centerBody.innerHTML = `<div style="padding:16px"><a href="${_esc(item.url)}" style="color:var(--accent)">${_esc(item.url)}</a></div>`;
    }
    _loadThread(item);
    return;
  }

  // ── 本站页面（site_page）：iframe 嵌入内部路径 ────────────────────────────
  if (item.item_type === 'site_page') {
    const ref = typeof item.site_ref === 'string'
      ? JSON.parse(item.site_ref || '{}')
      : (item.site_ref || {});
    const path = ref?.path || item.file_path || '';
    _centerBody.style.cssText = '';
    const iframe = document.createElement('iframe');
    iframe.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;border:none;';
    iframe.src = path ? `../${path}` : 'about:blank';
    _centerBody.appendChild(iframe);
    _loadThread(item);
    return;
  }

  // ── 其他类型：调用 ContainerMode.renderInCard ────────────────────────────
  const modeMap = {
    richtext:    'richtext',
    pdf:         'pdf',
    image:       'image_gallery',
    spreadsheet: 'webview',
  };
  const mode   = modeMap[item.item_type] || 'richtext';
  const params = { item_gid: item.gid, scope, readonly: 'false' };

  const cm = window.ContainerModes?.[mode];
  if (cm) {
    try {
      await cm.renderInCard(_centerBody, params, {});
    } catch (e) {
      _centerBody.innerHTML = `<div style="padding:16px;color:#f38ba8">渲染失败：${_esc(String(e))}</div>`;
    }
  } else {
    _centerBody.innerHTML = `<div style="padding:16px;color:var(--text-muted)">模式 "${_esc(mode)}" 未加载</div>`;
  }

  _loadThread(item);
}

// ── Markdown 内联编辑器（含自动保存）─────────────────────────────────────────
function _renderMarkdownCenter(item, scope) {
  let content = item.content_md || '';
  let isEditing = false;

  _centerBody.style.cssText = 'display:flex;flex-direction:column;height:100%;overflow:hidden;';

  // 工具栏
  const toolbar = document.createElement('div');
  toolbar.style.cssText = 'display:flex;align-items:center;gap:6px;padding:6px 12px;' +
    'border-bottom:1px solid var(--border,#313244);flex-shrink:0;background:var(--bg2,#181825);';
  toolbar.innerHTML =
    `<button id="khMdToggle" style="padding:3px 10px;border:1px solid var(--border,#313244);` +
    `border-radius:4px;background:transparent;color:var(--text,#cdd6f4);font-size:12px;cursor:pointer;">编辑</button>` +
    `<span id="khMdStatus" style="font-size:11px;color:var(--text-muted,#6c7086);margin-left:auto;"></span>`;

  // 预览区
  const previewEl = document.createElement('div');
  previewEl.style.cssText = 'flex:1;overflow-y:auto;padding:20px 28px;font-size:14px;' +
    'line-height:1.8;color:var(--text,#cdd6f4);';

  // 编辑器
  const editorEl = document.createElement('textarea');
  editorEl.style.cssText = 'display:none;flex:1;padding:20px 28px;' +
    'background:var(--bg,#1e1e2e);color:var(--text,#cdd6f4);' +
    'border:none;outline:none;font-family:monospace;font-size:13px;line-height:1.8;resize:none;';

  function _renderPreview() {
    previewEl.innerHTML = window.marked
      ? marked.parse(content)
      : `<pre style="white-space:pre-wrap;word-break:break-word">${_esc(content)}</pre>`;
  }
  _renderPreview();

  _centerBody.appendChild(toolbar);
  _centerBody.appendChild(previewEl);
  _centerBody.appendChild(editorEl);

  const statusEl = toolbar.querySelector('#khMdStatus');
  const toggleBtn = toolbar.querySelector('#khMdToggle');

  const _save = _debounce(async () => {
    const val = editorEl.value;
    statusEl.textContent = '保存中…';
    try {
      if (scope === 'local') {
        await _bridge('update_item', { gid: item.gid, content_md: val });
      } else {
        const cf = _cf();
        if (cf) await cf(`/api/knowledge_hub/items/${item.gid}`, {
          method: 'PATCH', body: JSON.stringify({ content_md: val }),
        });
      }
      item.content_md = val;
      statusEl.textContent = '已保存';
      setTimeout(() => { if (statusEl) statusEl.textContent = ''; }, 2000);
    } catch (_e) { statusEl.textContent = '保存失败'; }
  }, 800);

  editorEl.addEventListener('input', _save);

  toggleBtn.addEventListener('click', () => {
    isEditing = !isEditing;
    toggleBtn.textContent = isEditing ? '预览' : '编辑';
    if (isEditing) {
      editorEl.value = content;
      previewEl.style.display = 'none';
      editorEl.style.display = 'block';
      editorEl.focus();
    } else {
      content = editorEl.value;
      _renderPreview();
      editorEl.style.display = 'none';
      previewEl.style.display = '';
    }
  });
}

function _recordRecent(item) {
  try {
    if (_currentScope === 'personal') {
      _bridge('record_recent', item.gid);
    } else if (_isCloud()) {
      _cf()?.(`/api/knowledge_hub/items/${item.gid}/recent`, { method: 'POST' });
    }
  } catch (_) {}
}

// ── Right 评论区 ──────────────────────────────────────────────────────────────

/** 将 ISO 日期字符串转为 "YYYY年MM月" 分组 key 和显示文本 */
function _monthKey(dateStr) {
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return { key: 'unknown', label: '未知时间' };
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  return { key: `${y}-${m}`, label: `${y}年${m}月` };
}

/** 渲染变更历史列表（按月折叠，最新月展开） */
function _renderHistory(historyEntries) {
  if (!historyEntries.length) {
    return `<div style="padding:12px 16px;font-size:12px;color:var(--text-muted,#6c7086);">暂无变更记录</div>`;
  }

  // 按月分组（已按 created_at DESC 排序）
  const groups = [];
  const groupMap = {};
  for (const e of historyEntries) {
    const { key, label } = _monthKey(e.created_at);
    if (!groupMap[key]) {
      groupMap[key] = { key, label, entries: [] };
      groups.push(groupMap[key]);
    }
    groupMap[key].entries.push(e);
  }

  return groups.map((g, idx) => {
    const isLatest = idx === 0;
    const openAttr = isLatest ? ' open' : '';
    const rows = g.entries.map(e => {
      const d = new Date(e.created_at);
      const timeStr = isNaN(d.getTime()) ? '' :
        `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')} ` +
        `${String(d.getDate()).padStart(2,'0')}日`;
      const who = e.author_name ? _esc(e.author_name) : '未知';
      return `<div style="padding:6px 14px;border-bottom:1px solid var(--border,#313244);font-size:12px;line-height:1.6;">` +
        `<span style="color:var(--text-muted,#6c7086);margin-right:8px;">${timeStr}</span>` +
        `<span style="color:var(--accent,#89b4fa);margin-right:6px;">${who}</span>` +
        `<span style="color:var(--text,#cdd6f4);">${_esc(e.content)}</span></div>`;
    }).join('');
    return `<details${openAttr} style="border-bottom:1px solid var(--border,#313244);">` +
      `<summary style="padding:7px 14px;cursor:pointer;font-size:12px;font-weight:600;` +
      `color:var(--text,#cdd6f4);list-style:none;user-select:none;` +
      `background:var(--bg2,#181825);">` +
      `<span style="margin-right:6px;font-size:10px;">▶</span>${_esc(g.label)} ` +
      `<span style="font-weight:400;color:var(--text-muted,#6c7086);">(${g.entries.length}条)</span></summary>` +
      rows + `</details>`;
  }).join('');
}

function _loadThread(item) {
  if (!_thread) {
    _rightBody.innerHTML = '';
    if (window.EntryThread) {
      _thread = new EntryThread({
        mountEl:        _rightBody,
        mode:           'human',
        entries:        [],
        isCloud:        _isCloud(),
        onChange:       () => {},
        onSave:         async () => {},
        onStatusMsg:    () => {},
      });
    } else {
      _rightBody.innerHTML = `<div class="kh-right-placeholder">选择条目后显示评论</div>`;
    }
  }
  if (_thread) {
    _thread.setEntries([], item.gid);
    // 加载 entries from cloud or local
    _fetchEntries(item);
  }
}

async function _fetchEntries(item) {
  if (!_thread) return;
  try {
    if (_isCloud()) {
      const cf = _cf();
      if (!cf) return;

      // 加载变更历史（section=history）
      const histRes = await cf(`/api/knowledge_hub/items/${item.gid}/history`).catch(() => null);
      const histEntries = histRes?.data || [];

      // 渲染历史区域（header + 折叠列表）
      let histEl = _rightBody.querySelector('.kh-history-section');
      if (!histEl) {
        histEl = document.createElement('div');
        histEl.className = 'kh-history-section';
        histEl.style.cssText = 'flex-shrink:0;border-bottom:2px solid var(--border,#313244);max-height:50%;overflow-y:auto;';
        const header = document.createElement('div');
        header.style.cssText = 'padding:8px 14px;font-size:12px;font-weight:700;' +
          'color:var(--text-muted,#6c7086);background:var(--bg2,#181825);' +
          'border-bottom:1px solid var(--border,#313244);letter-spacing:.04em;';
        header.textContent = '变更历史';
        histEl.appendChild(header);
        const bodyEl = document.createElement('div');
        bodyEl.className = 'kh-history-body';
        histEl.appendChild(bodyEl);
        _rightBody.insertBefore(histEl, _rightBody.firstChild);
      }
      histEl.querySelector('.kh-history-body').innerHTML = _renderHistory(histEntries);

      // 加载评论（section != history）
      const data = await cf(`/api/item-entries/knowledge_item/${item.gid}`);
      const allEntries = Array.isArray(data) ? data : (data?.entries || []);
      const comments = allEntries.filter(e => e.section !== 'history');
      _thread.setEntries(comments, item.gid);
    }
  } catch (_) {}
}

// ── 文件夹 CRUD ───────────────────────────────────────────────────────────────
async function _newFolder(parentGid, scopeKey, teamGid) {
  let newFolder = null;
  try {
    if (scopeKey === 'personal') {
      console.log('[KH-DEBUG] _newFolder: calling create_folder, parentGid=', parentGid);
      const res = await _bridge('create_folder', parentGid, '新建文件夹');
      console.log('[KH-DEBUG] _newFolder: create_folder res =', JSON.stringify(res));
      newFolder = res?.data || null;
      await _loadPersonalFolders();
      console.log('[KH-DEBUG] _newFolder: after reload, _personalFolders =', JSON.stringify(_personalFolders));
    } else if (_isCloud()) {
      const cf = _cf();
      if (cf) {
        newFolder = await cf('/api/knowledge_hub/folders', {
          method: 'POST',
          body: JSON.stringify({ parent_gid: parentGid, scope_type: scopeKey, team_gid: teamGid, name: '新建文件夹' }),
        });
        await _loadCloudFolders(scopeKey, teamGid);
      }
    }
  } catch (_) {}
  if (!newFolder?.gid) return;
  // Ensure parent group is open so the new node is visible
  const grpKey = scopeKey === 'personal' ? 'personal' : (teamGid ? `team:${teamGid}` : scopeKey);
  _openGroups[grpKey] = true;
  localStorage.setItem(_lsk('kh:nav-open'), JSON.stringify(_openGroups));
  _renderLeft1();
  // Find the new node and start inline rename
  const node = document.querySelector(`[data-folder-gid="${newFolder.gid}"]`);
  if (node) _startInlineRename(node, newFolder, scopeKey, teamGid, true);
}

async function _renameFolder(folder, scopeKey, teamGid) {
  const node = document.querySelector(`[data-folder-gid="${folder.gid}"]`);
  if (node) { _startInlineRename(node, folder, scopeKey, teamGid, false); return; }
  // Fallback if node not in DOM (shouldn't happen)
  const name = await _promptText('重命名文件夹', '文件夹名称', folder.name);
  if (!name || name === folder.name) return;
  try {
    if (scopeKey === 'personal') {
      await _bridge('rename_folder', folder.gid, name);
      await _loadPersonalFolders();
    } else if (_isCloud()) {
      const cf = _cf();
      if (cf) await cf(`/api/knowledge_hub/folders/${folder.gid}`, {
        method: 'PATCH', body: JSON.stringify({ name }),
      });
      await _loadCloudFolders(scopeKey, teamGid);
    }
    _renderLeft1();
  } catch (_) {}
}

// 内联重命名：替换 label 为 input，Enter/blur 保存，Escape 取消
function _startInlineRename(node, folder, scopeKey, teamGid, isNew) {
  const labelSpan = node.querySelector('.kh-nav-node-label');
  if (!labelSpan) return;
  const origName = folder.name;
  const inp = document.createElement('input');
  inp.type = 'text';
  inp.className = 'kh-inline-input';
  inp.value = origName;
  labelSpan.replaceWith(inp);
  inp.focus();
  inp.select();

  let committed = false;

  async function commit() {
    if (committed) return;
    committed = true;
    const newName = inp.value.trim();
    if (!newName || newName === origName) {
      if (isNew && !newName) await _doDeleteFolder(folder, scopeKey, teamGid);
      _renderLeft1();
      return;
    }
    try {
      if (scopeKey === 'personal') {
        await _bridge('rename_folder', folder.gid, newName);
        await _loadPersonalFolders();
      } else if (_isCloud()) {
        const cf = _cf();
        if (cf) await cf(`/api/knowledge_hub/folders/${folder.gid}`, {
          method: 'PATCH', body: JSON.stringify({ name: newName }),
        });
        await _loadCloudFolders(scopeKey, teamGid);
      }
    } catch (_) {}
    _renderLeft1();
  }

  async function cancel() {
    if (committed) return;
    committed = true;
    if (isNew) await _doDeleteFolder(folder, scopeKey, teamGid);
    _renderLeft1();
  }

  inp.addEventListener('keydown', e => {
    if (e.key === 'Enter')  { e.preventDefault(); commit(); }
    if (e.key === 'Escape') { e.preventDefault(); cancel(); }
  });
  inp.addEventListener('blur', () => commit());
}

async function _doDeleteFolder(folder, scopeKey, teamGid) {
  try {
    if (scopeKey === 'personal') {
      await _bridge('delete_folder', folder.gid);
      await _loadPersonalFolders();
    } else if (_isCloud()) {
      const cf = _cf();
      if (cf) await cf(`/api/knowledge_hub/folders/${folder.gid}`, { method: 'DELETE' });
      await _loadCloudFolders(scopeKey, teamGid);
    }
  } catch (_) {}
}

async function _deleteFolder(folder, scopeKey, teamGid) {
  const ok = await _confirmDialog(`确定要删除文件夹「${folder.name}」及其所有内容吗？`);
  if (!ok) return;
  await _doDeleteFolder(folder, scopeKey, teamGid);
  if (_currentFolderGid === folder.gid) {
    _currentFolderGid = null;
    await _loadItems();
    _renderLeft2();
  }
  _renderLeft1();
}

// ── 添加文件菜单 ──────────────────────────────────────────────────────────────
function _showAddMenu(anchor) {
  if (_currentScope === 'migration') {
    _showToast('迁移只能由部署作业执行');
    return;
  }
  if (_currentScope === 'workspace') {
    _showDropdown(anchor, [
      { label: '当前区域：团队共创', disabled: true },
      { sep: true },
      { icon: ICONS.markdown, label: '新建团队 Markdown 文档', action: () => _createWorkspaceDocument() },
    ]);
    return;
  }
  const isAdmin = _getAuthRole() === 'super_admin' || _getAuthRole() === 'knowledge_admin';
  const scopeLabel = { personal: '个人（仅自己可见）', public: '公共资料（所有人可见）', team: '团队', favorites: '收藏', recent: '最近', annotated: '标注' }[_currentScope] || _currentScope;
  const items = [
    { label: `当前区域：${scopeLabel}`, disabled: true },
    { sep: true },
    { icon: ICONS.richtext, label: '新建富文本文档', action: () => _createItem('richtext') },
    { icon: ICONS.markdown, label: '新建 Markdown 文档', action: () => _createItem('markdown') },
    { sep: true },
    { icon: ICONS.weblink, label: '添加网络链接', action: () => _createWeblink() },
    { icon: ICONS.pdf, label: '上传 PDF / 文件', action: () => _uploadFile() },
    ...(isAdmin ? [{ icon: ICONS.site_page, label: '添加本站页面（管理员）', action: () => _createSitePage() }] : []),
  ];
  _showDropdown(anchor, items);
}

// ── 拖拽移动 ──────────────────────────────────────────────────────────────────

// 权限：个人知识库所有人可编辑；公共/团队需 knowledge_admin 及以上
function _canEdit(scopeKey) {
  if (scopeKey === 'personal') return true;
  const LEVELS = ['external', 'member', 'knowledge_admin', 'rule_admin', 'project_admin', 'team_admin', 'super_admin'];
  return LEVELS.indexOf(_getAuthRole()) >= LEVELS.indexOf('knowledge_admin');
}

// 检测 targetGid 是否是 movedGid 的后代（防止文件夹拖入自身子树）
function _isFolderDescendant(movedGid, targetGid, allFolders) {
  if (!targetGid || movedGid === targetGid) return true;
  let cur = allFolders.find(f => f.gid === targetGid);
  while (cur) {
    if (cur.parent_gid === movedGid) return true;
    cur = allFolders.find(f => f.gid === cur.parent_gid);
  }
  return false;
}

// 为文件夹节点启用拖拽源
function _enableFolderDrag(node, folder, scopeKey, teamGid, allFolders) {
  if (!_canEdit(scopeKey)) return;
  node.setAttribute('draggable', 'true');
  node.addEventListener('dragstart', e => {
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', '');  // Firefox 兼容（必须设置至少一项）
    e.dataTransfer.setData('application/kh-drag', JSON.stringify({
      type: 'folder', gid: folder.gid, scopeKey, teamGid: teamGid || null,
    }));
    setTimeout(() => node.classList.add('kh-dragging'), 0);
  });
  node.addEventListener('dragend', () => node.classList.remove('kh-dragging'));
}

// 为文件行启用拖拽源
function _enableItemDrag(row, item, scopeKey, teamGid) {
  if (!_canEdit(scopeKey)) return;
  row.setAttribute('draggable', 'true');
  row.addEventListener('dragstart', e => {
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', '');
    e.dataTransfer.setData('application/kh-drag', JSON.stringify({
      type: 'item', gid: item.gid, scopeKey: scopeKey || _currentScope, teamGid: teamGid || null,
    }));
    setTimeout(() => row.classList.add('kh-dragging'), 0);
  });
  row.addEventListener('dragend', () => row.classList.remove('kh-dragging'));
}

// 为元素启用 drop 目标（targetFolderGid=null 表示根级）
function _enableDropTarget(el, targetFolderGid, targetScopeKey, targetTeamGid) {
  el.addEventListener('dragover', e => {
    // 兼容：Chromium 的 types 可能不含自定义 MIME，用 text/plain 作辅助判断
    const hasKhDrag = e.dataTransfer.types.includes('application/kh-drag')
                   || e.dataTransfer.types.includes('text/plain');
    if (!hasKhDrag) return;
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = 'move';
    el.classList.add('kh-drop-over');
  });
  el.addEventListener('dragleave', e => {
    if (!el.contains(e.relatedTarget)) el.classList.remove('kh-drop-over');
  });
  el.addEventListener('drop', e => {
    e.preventDefault();
    e.stopPropagation();
    el.classList.remove('kh-drop-over');
    try {
      const raw = e.dataTransfer.getData('application/kh-drag');
      if (!raw) return;
      const data = JSON.parse(raw);
      _handleDrop(data, targetFolderGid, targetScopeKey, targetTeamGid);
    } catch (_) {}
  });
}

// 执行拖拽落下的移动逻辑
async function _handleDrop(dragData, targetFolderGid, targetScopeKey, targetTeamGid) {
  if (!_canEdit(targetScopeKey)) {
    _showToast('没有权限操作该知识库');
    return;
  }
  if (dragData.scopeKey !== targetScopeKey ||
      (dragData.teamGid || null) !== (targetTeamGid || null)) {
    _showToast('不支持跨知识库移动');
    return;
  }

  if (dragData.type === 'folder') {
    if (dragData.gid === targetFolderGid) return; // 拖到自身
    const allFolders = dragData.scopeKey === 'personal'
      ? _personalFolders
      : (_cloudFolders[dragData.scopeKey === 'team' ? `team:${dragData.teamGid}` : 'public'] || []);
    if (_isFolderDescendant(dragData.gid, targetFolderGid, allFolders)) {
      _showToast('不能将文件夹移到自身或其子文件夹中');
      return;
    }
    // 检查是否已经在目标位置
    const srcFolder = allFolders.find(f => f.gid === dragData.gid);
    if (srcFolder && (srcFolder.parent_gid || null) === (targetFolderGid || null)) return;
    try {
      if (dragData.scopeKey === 'personal') {
        await _bridge('move_folder', dragData.gid, targetFolderGid || null);
        await _loadPersonalFolders();
      } else if (_isCloud()) {
        const cf = _cf();
        if (cf) await cf(`/api/knowledge_hub/folders/${dragData.gid}`, {
          method: 'PATCH',
          body: JSON.stringify({ parent_gid: targetFolderGid || null }),
        });
        await _loadCloudFolders(targetScopeKey, targetTeamGid);
      }
      _renderLeft1();
    } catch (_) {}

  } else if (dragData.type === 'item') {
    // 检查是否已在目标文件夹
    const srcItem = _items.find(it => it.gid === dragData.gid);
    if (srcItem && (srcItem.folder_gid || null) === (targetFolderGid || null)) return;
    try {
      if (dragData.scopeKey === 'personal') {
        await _bridge('update_item', { gid: dragData.gid, folder_gid: targetFolderGid || null });
      } else if (_isCloud()) {
        const cf = _cf();
        if (cf) await cf(`/api/knowledge_hub/items/${dragData.gid}`, {
          method: 'PATCH',
          body: JSON.stringify({ folder_gid: targetFolderGid || null }),
        });
      }
      // 移走后从 Left2 移除（如当前不是目标文件夹视图）
      if (_currentFolderGid !== targetFolderGid) {
        _items = _items.filter(it => it.gid !== dragData.gid);
        _renderLeft2();
      }
    } catch (_) {}
  }
}

function _getAuthRole() {
  try {
    const user = window.parent?._authUser || window._authUser;
    return user?.system_role || user?.role || 'member';
  } catch (_) { return 'member'; }
}

async function _createItem(itemType) {
  const defaultTitle = { richtext: '未命名文档', markdown: '未命名 Markdown', image: '图片集' }[itemType] || '未命名';
  const title = await _promptText('新建文档', '文档标题', defaultTitle);
  if (title === null) return;  // 取消
  // 若在公共/团队区，弹可见范围选择
  if (_currentScope !== 'personal' && window.VisibilitySelector) {
    await _promptVisibilityThenCreate({ item_type: itemType, title: title || defaultTitle });
  } else {
    await _doCreateItem({ item_type: itemType, title: title || defaultTitle });
  }
}

async function _promptVisibilityThenCreate(fields) {
  return new Promise(resolve => {
    const dlg = document.createElement('div');
    dlg.style.cssText = 'position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,.5);display:flex;align-items:center;justify-content:center';
    dlg.innerHTML = `
      <div style="background:var(--bg-secondary,#181825);border:1px solid var(--border-default,#313244);border-radius:10px;padding:20px;width:300px;box-shadow:0 8px 32px rgba(0,0,0,.4)">
        <div style="font-size:13px;font-weight:600;color:var(--text-normal,#cdd6f4);margin-bottom:12px">选择可见范围</div>
        <div id="_khVisMount"></div>
        <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:14px">
          <button id="_khVisCancel" style="padding:4px 12px;border-radius:5px;border:1px solid var(--border-default,#313244);background:transparent;color:var(--text-muted,#a6adc8);cursor:pointer;font-size:12px">取消</button>
          <button id="_khVisOk" style="padding:4px 12px;border-radius:5px;border:none;background:var(--color-accent,#89b4fa);color:var(--bg-primary,#1e1e2e);cursor:pointer;font-size:12px;font-weight:600">创建</button>
        </div>
      </div>`;
    document.body.appendChild(dlg);
    const mount = dlg.querySelector('#_khVisMount');
    // 默认 scope 对应当前浏览区域
    const initVis = _currentScope === 'public' ? 'public' : _currentScope === 'team' ? 'team' : 'public';
    VisibilitySelector.renderWidget(mount, { initialVisibility: initVis }).then(() => {
      dlg.querySelector('#_khVisCancel').onclick = () => { dlg.remove(); resolve(); };
      dlg.querySelector('#_khVisOk').onclick = async () => {
        const val = VisibilitySelector.getValue(mount);
        dlg.remove();
        // 将 visibility 映射为 scope_type
        const scopeMap = { private: 'personal', team: 'team', project: 'project', public: 'public' };
        await _doCreateItem({
          ...fields,
          _visOverride: {
            scope_type:          scopeMap[val.visibility] || 'public',
            team_gid:            val.shared_team_gid    || null,
            shared_project_gid:  val.shared_project_gid || null,
          },
        });
        resolve();
      };
    });
  });
}

async function _createWeblink() {
  const res = await _promptForm('添加网络链接', [
    { key: 'title', label: '标题', placeholder: '链接名称' },
    { key: 'url',   label: 'URL',  placeholder: 'https://...' },
  ]);
  if (!res) return;
  await _doCreateItem({ item_type: 'weblink', title: res.title || res.url, url: res.url });
}

async function _createSitePage() {
  // 可注册的内部页面清单（path 相对于 web/ 目录）
  const PAGE_REGISTRY = [
    { path: 'knowledge_hub/pages/project_info.html', title: '业务基础信息' },
    { path: 'knowledge_hub/pages/gbop_vpps.html', title: 'VPPS 管理' },
    { path: 'knowledge_hub/pages/factory_info.html', title: '现场信息' },
    { path: 'task/index.html', title: '任务清单' },
    { path: 'issue/index.html', title: '问题清单' },
    { path: 'project/project.html', title: '项目管理' },
    { path: 'bop/bop.html', title: 'BOP 工艺清单' },
    { path: 'ebom/ebom.html', title: 'PBOM 清单' },
    { path: 'std_op_lib/std_op_lib.html', title: '标准工序库 (GBOP)' },
    { path: 'craft_element_lib/craft_element_lib.html', title: '工艺元素模板库' },
    { path: 'factory_resource/factory_resource.html', title: '工厂实物资源' },
    { path: 'knowledge/knowledge.html', title: '知识清单' },
    { path: 'rule_mgmt/rule_mgmt.html', title: '规则管理' },
    { path: 'craft_table/index.html', title: '工艺表格' },
    { path: 'lineage_view/index.html', title: 'BOP Lineage 视图' },
    { path: 'gbop/index.html', title: 'GBOP 标准工序' },
    { path: 'gbop_lineage/index.html', title: 'GBOP 树形视图' },
    { path: 'canvas/canvas_shell.html', title: '工艺规划画布' },
    { path: 'flow_canvas/index.html', title: '流程画布' },
    { path: 'org_mgmt/org_mgmt.html', title: '组织管理' },
    { path: 'approval/approval_view.html', title: '审批中心' },
    { path: 'admin/capabilities.html', title: '系统能力清单' },
    { path: 'admin/lists_registry.html', title: '数据清单注册' },
    { path: 'admin/bug_tracker.html', title: '开发沟通看板' },
    { path: 'admin/feature_flags.html', title: '功能开关' },
    { path: 'workbench/workbench.html', title: '工作台' },
    { path: 'data_hub/index.html', title: '数据中心' },
    { path: 'template_hub/index.html', title: '模板中心' },
    { path: 'craft_hub/index.html', title: '工艺中心' },
    { path: 'project_hub/index.html', title: '项目中心' },
    { path: 'project_hub/kanban.html', title: '看板' },
    { path: 'automation_hub/index.html', title: '自动化中心' },
    { path: 'automation_hub/skill_lib.html', title: 'AI 技能库' },
    { path: 'automation_hub/ai_settings.html', title: 'AI 设置' },
    { path: 'admin_hub/index.html', title: '管理中心' },
    { path: 'settings/index.html', title: '设置' },
    { path: 'cad_sim/index.html', title: '数模预览' },
    { path: 'auto_canvas/index.html', title: '自动画布' },
    { path: 'md_workspace/md_workspace.html', title: 'Markdown 工作区' },
  ];

  // 收集已添加的 site_page 路径
  const existingPaths = new Set();
  // 从全部 scope 搜索已存在的 site_page
  try {
    if (_isCloud()) {
      const cf = _cf();
      if (cf) {
        const all = await cf('/api/knowledge_hub/items?scope_type=public&show_hidden=true') || [];
        all.forEach(it => {
          if (it.item_type === 'site_page') {
            const ref = typeof it.site_ref === 'string' ? JSON.parse(it.site_ref || '{}') : (it.site_ref || {});
            if (ref.path) existingPaths.add(ref.path);
          }
        });
      }
    }
  } catch (_) {}
  // 也检查当前已加载的列表
  _items.forEach(it => {
    if (it.item_type === 'site_page') {
      const ref = typeof it.site_ref === 'string' ? JSON.parse(it.site_ref || '{}') : (it.site_ref || {});
      if (ref.path) existingPaths.add(ref.path);
    }
  });

  // 过滤出未添加的页面
  const available = PAGE_REGISTRY.filter(p => !existingPaths.has(p.path));

  // 弹出选择器
  const picked = await _showPagePicker(available);
  if (!picked || !picked.length) return;

  // 批量添加
  for (const page of picked) {
    await _doCreateItem({
      item_type: 'site_page',
      title: page.title,
      site_ref: { path: page.path, label: page.title },
    });
  }
  _showToast(`已添加 ${picked.length} 个页面`);
}

// ── 页面选择器弹窗（多选） ───────────────────────────────────────────────────
function _showPagePicker(pages) {
  return new Promise(resolve => {
    const overlay = document.createElement('div');
    overlay.className = 'kh-modal-overlay';

    const listHtml = pages.length
      ? pages.map((p, i) => `
        <label class="kh-page-pick-item">
          <input type="checkbox" data-idx="${i}">
          <span class="kh-page-pick-title">${_esc(p.title)}</span>
          <span class="kh-page-pick-path">${_esc(p.path)}</span>
        </label>`).join('')
      : '<div style="padding:16px;color:var(--muted);text-align:center">所有页面均已添加</div>';

    overlay.innerHTML = `
      <div class="kh-modal" style="width:500px;max-height:70vh;">
        <h3>添加本站页面</h3>
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
          <span style="font-size:12px;color:var(--muted)">可选 ${pages.length} 个未添加页面</span>
          ${pages.length ? '<button class="kh-btn-ghost" id="khPageSelAll" style="margin-left:auto;font-size:11px;padding:2px 8px;height:24px;">全选</button>' : ''}
        </div>
        <div style="max-height:40vh;overflow-y:auto;border:1px solid var(--border);border-radius:4px;background:var(--bg);">
          ${listHtml}
        </div>
        <div class="kh-modal-footer" style="margin-top:12px;">
          <button class="kh-btn-ghost" id="khPageCancel">取消</button>
          <button class="kh-btn-primary" id="khPageOk"${pages.length ? '' : ' disabled'}>添加所选</button>
        </div>
      </div>`;

    document.body.appendChild(overlay);

    // 全选
    overlay.querySelector('#khPageSelAll')?.addEventListener('click', () => {
      overlay.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.checked = true);
    });

    const collect = () => {
      const result = [];
      overlay.querySelectorAll('input[type="checkbox"]:checked').forEach(cb => {
        const idx = parseInt(cb.dataset.idx);
        if (pages[idx]) result.push(pages[idx]);
      });
      return result;
    };

    overlay.querySelector('#khPageCancel').addEventListener('click', () => { overlay.remove(); resolve(null); });
    overlay.querySelector('#khPageOk').addEventListener('click', () => { overlay.remove(); resolve(collect()); });
    overlay.addEventListener('click', e => { if (e.target === overlay) { overlay.remove(); resolve(null); } });
    overlay.addEventListener('keydown', e => { if (e.key === 'Escape') { overlay.remove(); resolve(null); } });
  });
}

async function _uploadFile() {
  const eAPI = window.electronAPI || window.top?.electronAPI || window.parent?.electronAPI;
  if (!eAPI?.showOpenDialog) {
    _showToast('当前环境不支持文件选择');
    return;
  }
  const result = await eAPI.showOpenDialog({
    properties: ['openFile'],
    filters: [{ name: '支持的文件', extensions: ['pdf', 'md', 'csv', 'xlsx', 'png', 'jpg', 'jpeg', 'gif'] }],
  });
  if (result.canceled || !result.filePaths?.length) return;
  const filePath = result.filePaths[0];
  const ext = filePath.split('.').pop().toLowerCase();
  const typeMap = { pdf: 'pdf', md: 'markdown', csv: 'spreadsheet', xlsx: 'spreadsheet',
                    png: 'image', jpg: 'image', jpeg: 'image', gif: 'image' };
  const itemType = typeMap[ext] || 'pdf';
  const title = filePath.split(/[\\/]/).pop();
  await _doCreateItem({ item_type: itemType, title, file_path: filePath });
}

async function _doCreateItem(fields) {
  const scope = _currentScope;
  const extra = { folder_gid: _currentFolderGid || null };
  // _visOverride: 由 _promptVisibilityThenCreate 传入，覆盖 scope_type/team_gid/shared_project_gid
  const visOverride = fields._visOverride || null;
  const { _visOverride: _ignored, ...cleanFields } = fields;
  try {
    let item;
    if (scope === 'personal' && !visOverride) {
      const res = await _bridge('create_item',
        extra.folder_gid, cleanFields.item_type, cleanFields.title,
        cleanFields.content_body || null, cleanFields.content_md || '',
        cleanFields.file_path || '', cleanFields.url || '', cleanFields.site_ref || null,
        cleanFields.tags || [], '');
      item = res?.data;
    } else if (_isCloud()) {
      const cf = _cf();
      if (!cf) return;
      const body = {
        ...extra,
        scope_type: visOverride?.scope_type || scope,
        team_gid:   visOverride?.team_gid   || _currentTeamGid,
        ...cleanFields,
      };
      if (visOverride?.shared_project_gid) body.shared_project_gid = visOverride.shared_project_gid;
      item = await cf('/api/knowledge_hub/items', { method: 'POST', body: JSON.stringify(body) });
    }
    if (item) {
      _items.unshift(item);
      _renderLeft2();
      _openItem(item);
    }
  } catch (_) {}
}

// ── 下拉菜单 ──────────────────────────────────────────────────────────────────
let _activeDropdown = null;

function _showDropdown(anchor, menuItems) {
  _closeDropdown();
  const menu = document.createElement('div');
  menu.className = 'kh-dropdown';
  const rect = anchor.getBoundingClientRect?.() || { left: 0, top: 0, width: 0, height: 0 };
  menu.style.left = rect.left + 'px';
  menu.style.top  = (rect.top + rect.height + 4) + 'px';

  menuItems.forEach(item => {
    if (item.sep) {
      const sep = document.createElement('div');
      sep.className = 'kh-dropdown-sep';
      menu.appendChild(sep);
      return;
    }
    const el = document.createElement('div');
    if (item.disabled) {
      el.className = 'kh-dropdown-hint';
      el.textContent = item.label;
      menu.appendChild(el);
      return;
    }
    el.className = 'kh-dropdown-item';
    el.innerHTML = `${item.icon || ''}<span>${_esc(item.label)}</span>`;
    el.addEventListener('click', () => { _closeDropdown(); item.action?.(); });
    menu.appendChild(el);
  });

  document.body.appendChild(menu);
  _activeDropdown = menu;
  requestAnimationFrame(() => {
    document.addEventListener('click', _closeDropdown, { once: true });
  });
}

function _closeDropdown() {
  if (_activeDropdown) { _activeDropdown.remove(); _activeDropdown = null; }
}

// ── 对话框工具 ────────────────────────────────────────────────────────────────
function _promptText(title, label, defaultVal) {
  return new Promise(resolve => {
    const overlay = document.createElement('div');
    overlay.className = 'kh-modal-overlay';
    overlay.innerHTML = `
      <div class="kh-modal">
        <h3>${_esc(title)}</h3>
        <div class="kh-modal-row">
          <label>${_esc(label)}</label>
          <input id="khPromptInput" type="text" value="${_esc(defaultVal || '')}" />
        </div>
        <div class="kh-modal-footer">
          <button class="kh-btn-ghost" id="khPromptCancel">取消</button>
          <button class="kh-btn-primary" id="khPromptOk">确定</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    const input = overlay.querySelector('#khPromptInput');
    input.select(); input.focus();
    overlay.querySelector('#khPromptCancel').addEventListener('click', () => { overlay.remove(); resolve(null); });
    overlay.querySelector('#khPromptOk').addEventListener('click', () => { overlay.remove(); resolve(input.value.trim()); });
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter') { overlay.remove(); resolve(input.value.trim()); }
      if (e.key === 'Escape') { overlay.remove(); resolve(null); }
    });
  });
}

function _promptForm(title, fields) {
  return new Promise(resolve => {
    const overlay = document.createElement('div');
    overlay.className = 'kh-modal-overlay';
    const rows = fields.map(f => {
      if (f.type === 'select' && f.options) {
        const opts = f.options.map(o => `<option value="${_esc(o.value)}">${_esc(o.label)}</option>`).join('');
        return `<div class="kh-modal-row"><label>${_esc(f.label)}</label>
         <select data-key="${_esc(f.key)}" style="height:30px;padding:0 8px;background:var(--bg);border:1px solid var(--border);border-radius:4px;color:var(--text);font-size:13px;">${opts}</select></div>`;
      }
      return `<div class="kh-modal-row"><label>${_esc(f.label)}</label>
       <input data-key="${_esc(f.key)}" type="text" placeholder="${_esc(f.placeholder || '')}"></div>`;
    }).join('');
    overlay.innerHTML = `
      <div class="kh-modal">
        <h3>${_esc(title)}</h3>
        ${rows}
        <div class="kh-modal-footer">
          <button class="kh-btn-ghost" id="khFormCancel">取消</button>
          <button class="kh-btn-primary" id="khFormOk">确定</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    const firstInput = overlay.querySelector('input, select');
    if (firstInput) firstInput.focus();
    const collect = () => {
      const res = {};
      overlay.querySelectorAll('[data-key]').forEach(el => res[el.dataset.key] = el.value.trim());
      return res;
    };
    overlay.querySelector('#khFormCancel').addEventListener('click', () => { overlay.remove(); resolve(null); });
    overlay.querySelector('#khFormOk').addEventListener('click', () => { overlay.remove(); resolve(collect()); });
    overlay.addEventListener('keydown', e => {
      if (e.key === 'Enter') { overlay.remove(); resolve(collect()); }
      if (e.key === 'Escape') { overlay.remove(); resolve(null); }
    });
  });
}

function _confirmDialog(msg) {
  return new Promise(resolve => {
    const overlay = document.createElement('div');
    overlay.className = 'kh-modal-overlay';
    overlay.innerHTML = `
      <div class="kh-modal">
        <h3>确认</h3>
        <p style="font-size:13px;color:var(--text);margin-bottom:16px">${_esc(msg)}</p>
        <div class="kh-modal-footer">
          <button class="kh-btn-ghost" id="khConfirmNo">取消</button>
          <button class="kh-btn-primary" style="background:#f38ba8;color:#1e1e2e" id="khConfirmYes">确定</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    overlay.querySelector('#khConfirmNo').addEventListener('click', () => { overlay.remove(); resolve(false); });
    overlay.querySelector('#khConfirmYes').addEventListener('click', () => { overlay.remove(); resolve(true); });
  });
}

function _showToast(msg) {
  const el = document.createElement('div');
  el.style.cssText = 'position:fixed;bottom:20px;left:50%;transform:translateX(-50%);' +
    'background:var(--bg2,#181825);border:1px solid var(--border,#313244);' +
    'color:var(--text,#cdd6f4);padding:8px 16px;border-radius:6px;font-size:12px;z-index:99999;';
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 2000);
}

// ── 主题 ─────────────────────────────────────────────────────────────────────
function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme || 'dark');
}

// 暴露给外部
window._khApplyTheme = applyTheme;

// ── 启动 ──────────────────────────────────────────────────────────────────────
(function _start() {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
})();
window.addEventListener('message', e => {
  if (e.data?.type === 'theme') applyTheme(e.data.theme);
});
try { applyTheme(window.parent?.document?.documentElement?.getAttribute('data-theme') || 'dark'); } catch (_) {}
