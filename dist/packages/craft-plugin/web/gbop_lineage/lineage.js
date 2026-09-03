'use strict';
/**
 * lineage.js  —  GBOP Lineage Miller Columns 树形视图
 *
 * 依赖：无外部库（纯 vanilla JS）
 * 数据来源：GET /api/gbop/versions/{gid}/entries
 * 列分组依据：树深度（根据 parent_gid 链计算）
 */

// ── 常量 ────────────────────────────────────────────────────────────
const NT_ABBR = {
  version: '版', system: '系', device: '装',
  part: '件', process: '工序', operation: '操作',
};

const NT_LABEL = {
  version:   '版本',
  system:    '系统',
  device:    '装置',
  part:      '零部件',
  process:   '总装工序',
  operation: '总装操作',
};

// ── 统计显示优先级 ─────────────────────────────────────────────────
const STATS_PRIORITY = [
  'process', 'operation', 'part', 'device', 'system', 'version',
];

const _LEVEL_STATS_PRIORITY = {
  system:  ['device', 'part', 'process', 'operation'],
  device:  ['part', 'process', 'operation'],
};
const _PROCESS_STATS_PRIORITY = ['operation', 'part'];
const _OP_STATS_PRIORITY = ['part'];

// ── 状态 ─────────────────────────────────────────────────────────────
const _params   = Object.fromEntries(new URLSearchParams(location.search));
// 向上遍历 frame 链找到 _cloudFetch（可能嵌套多层 iframe：main→knowledgeHub→lineage）
function _cf(method, path, opts = {}) {
  let w = window;
  for (let i = 0; i < 5; i++) {
    if (w._cloudFetch) return w._cloudFetch(path, { ...opts, method });
    if (w.parent && w.parent !== w) w = w.parent; else break;
  }
  throw new Error('cloudFetch not available');
}

async function _invokeCapability(id, payload) {
  const response = await _cf('POST', `/api/v1/capabilities/${id}:invoke`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ version: 1, payload }),
  });
  const result = response?.data;
  if (response?.success !== true || result?.ok !== true) {
    const detail = result?.error || response?.error || {};
    const error = new Error(detail.message || `能力调用失败：${id}@1`);
    error.code = detail.code || 'capability_invocation_failed';
    throw error;
  }
  return result.data;
}
// localStorage 账号隔离
const _USER_GID = (() => {
  try { let w = window; for (let i = 0; i < 5; i++) { if (w._authUser) { const u = w._authUser; return u?.gid || u?.user_gid || ''; } if (w.parent && w.parent !== w) w = w.parent; else break; } return ''; } catch { return ''; }
})();
function _lsk(base) { return _USER_GID ? `${_USER_GID}:${base}` : base; }
let _versionGid = _params.gbop_version_gid || '';
let _versionTag = _params.version_name || _versionGid.slice(-6);

let _rows            = [];      // flat array from API (may span multiple versions)
let _rowByGid        = new Map();
let _childMap        = new Map(); // null → root children
let _statsMap        = new Map(); // gid → {nt: count}
let _collapsed       = new Set(); // gid of nodes whose children are hidden
let _depthByGid      = new Map(); // gid → tree depth (depth 0 = root, root's children = depth 1, etc.)
let _selectedRoots   = new Set(); // 树深度=0 的根节点（仅显示已选根节点的后代）
let _loadedVersionGids = new Set(); // which bop_version GIDs are currently loaded
let _versionTagMap   = new Map();   // version_gid → version_tag (for picker dedup)
let _rootPickerEl    = null;        // the floating version picker DOM element
let _activeGid       = null;
let _dragGid         = null;
let _miller         = null;

// 视图设置（从 localStorage 恢复）
let _typeFilter   = null;    // null = 全部显示, [] = 全不选, ['type1',...] = 筛选
let _maxDepth     = 4;     // 最大树深度（含），默认显示到深度 4（根=0，第1列=深度1）
let _searchText   = '';
let _level1Filter = null; // null = 全部显示, Set() = 全不选, Set([gid,...]) = 筛选（深度=1的节点）
let _colTypeFilters = new Map(); // level → node_type，列内类型二次筛选（点击列头 chip 触发）
let _collapsedCols  = new Set(); // level → 该列折叠隐藏（仅保留窄条）
let _zoomPct        = 100;       // 缩放百分比（50-200）
let _sidebarOpen    = false;     // 右侧边栏展开/折叠
let _sbActiveTab    = 'links';   // 当前边栏页签

let _lvTheme       = localStorage.getItem(_lsk('lv:theme')) || 'dark'; // 'dark' | 'light'

// DiffNavTree 状态
let _dnt = null;

// ── DOM refs ─────────────────────────────────────────────────────────
const $columns    = document.getElementById('lvColumns');
const $wrap       = document.getElementById('lvColumnsWrap');
const $popover    = document.getElementById('lvStatsPopover');
const $ctxMenu    = document.getElementById('lvCtxMenu');
const $toast      = document.getElementById('lvToast');
const $versionLbl = document.getElementById('lvVersionLabel');
const $typeBtn    = document.getElementById('lvTypeFilterBtn');
const $typeDD     = document.getElementById('lvTypeDropdown');
const $maxDepth   = document.getElementById('lvMaxDepth');
const $search     = document.getElementById('lvSearch');
const $l1Btn      = document.getElementById('lvLevel1Btn');
const $l1DD       = document.getElementById('lvLevel1Dropdown');
const $dntWrap    = document.getElementById('lvDntWrap');
const $zoomRange  = document.getElementById('lvZoomRange');
const $zoomPct    = document.getElementById('lvZoomPct');
const $sidebar    = document.getElementById('lvSidebar');
const $sbBody     = document.getElementById('lvSbBody');
const $sbTabs     = document.getElementById('lvSbTabs');
const $sbToggle   = document.getElementById('lvSbToggle');
const $dpPopover  = document.getElementById('lvDetailPopover');
const $dpBody     = document.getElementById('lvDpBody');
const $dpTitle    = document.getElementById('lvDpTitle');
const $dpClose    = document.getElementById('lvDpClose');
const $versionSel = document.getElementById('lvVersionSelect');
const $opPanel    = document.getElementById('lvOverlayPanel');
const $opBody     = document.getElementById('lvOpBody');
const $opTitle    = document.getElementById('lvOpTitle');
const $opClose    = document.getElementById('lvOpClose');
const $opPin      = document.getElementById('lvOpPin');
const $opSbToggle = document.getElementById('lvOpSbToggle');

// ── Toast ─────────────────────────────────────────────────────────────
let _toastTimer = null;
function _toast(msg, type = 'ok', dur = 2500) {
  $toast.textContent = msg;
  $toast.className = `lv-toast ${type}`;
  $toast.style.display = 'block';
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => { $toast.style.display = 'none'; }, dur);
}

// ── 数据层 ────────────────────────────────────────────────────────────

function _flattenMeta(rows) {
  // GBOP 数据规范化：vpps_desc / op_name → title（用于卡片显示）
  return rows.map(r => {
    // 取第一个有值的作为 title
    if (!r.title) r.title = r.vpps_desc || r.op_name || '';
    if (r.meta && typeof r.meta === 'object') {
      if (!r.title && r.meta.title) r.title = r.meta.title;
    } else if (typeof r.meta === 'string') {
      try {
        const m = JSON.parse(r.meta);
        if (!r.title && m.title) r.title = m.title;
      } catch { /* ignore */ }
    }
    return r;
  });
}

function _buildIndexes(rows) {
  _rowByGid.clear();
  _childMap.clear();
  _depthByGid.clear();
  for (const r of rows) {
    _rowByGid.set(r.gid, r);
  }
  for (const r of rows) {
    const pk = r.parent_gid || null;
    if (!_childMap.has(pk)) _childMap.set(pk, []);
    _childMap.get(pk).push(r);
  }
  // sort children by seq_no
  for (const [, arr] of _childMap) {
    arr.sort((a, b) => (a.seq_no ?? 0) - (b.seq_no ?? 0));
  }
  // 预计算每个节点的树深度
  // 根节点（parent_gid === null）深度 = 0
  // 子节点深度 = 父节点深度 + 1
  const _calcDepth = (gid, cache) => {
    if (cache.has(gid)) return cache.get(gid);
    const r = _rowByGid.get(gid);
    if (!r) { cache.set(gid, 0); return 0; }
    if (!r.parent_gid) { cache.set(gid, 0); return 0; }
    const d = _calcDepth(r.parent_gid, cache) + 1;
    cache.set(gid, d);
    return d;
  };
  for (const r of rows) {
    _calcDepth(r.gid, _depthByGid);
  }
}

function _buildStats() {
  _statsMap.clear();
  // bottom-up: process leaves first (sorted by level desc)
  const sorted = [..._rows].sort((a, b) => (b.level ?? 0) - (a.level ?? 0));
  for (const r of sorted) {
    const myStats = {};
    // add self
    if (r.node_type) myStats[r.node_type] = (myStats[r.node_type] || 0) + 1;
    // merge children stats
    const children = _childMap.get(r.gid) || [];
    for (const child of children) {
      const cs = _statsMap.get(child.gid) || {};
      for (const [nt, cnt] of Object.entries(cs)) {
        myStats[nt] = (myStats[nt] || 0) + cnt;
      }
    }
    _statsMap.set(r.gid, myStats);
  }
}

function _getDescendantStats(gid) {
  // return stats of only descendants (exclude self)
  const selfStat = _statsMap.get(gid) || {};
  const self = _rowByGid.get(gid);
  const result = { ...selfStat };
  if (self?.node_type && result[self.node_type] > 0) {
    result[self.node_type]--;
    if (result[self.node_type] === 0) delete result[self.node_type];
  }
  return result;
}

function _initCollapsed() {
  // GBOP：所有 depth=0 节点就是顶级节点，全部选中（不需要根选择栏筛选）
  const level0 = (_childMap.get(null) || []).filter(r => _treeDepth(r) === 0);
  _selectedRoots = new Set(level0.map(r => r.gid));
}

/** 取节点的树深度（根据 parent_gid 链预计算，替代旧的 ai00_level 固定分组） */
function _treeDepth(r) { return _depthByGid.get(r?.gid) ?? 0; }

async function _load() {
  if (!_versionGid) {
    $columns.innerHTML = '<div class="lv-empty">请选择 GBOP 版本</div>';
    return;
  }
  $columns.innerHTML = '<div class="lv-loading"><div class="lv-spinner"></div>加载中…</div>';

  try {
    _loadedVersionGids = new Set([_versionGid]);
    _versionTagMap.set(_versionGid, _versionTag);
    const json = await _invokeCapability('craft.gbop.catalog.read', {
      operation: 'entries.list',
      version_gid: _versionGid,
    });
    _rows = _flattenMeta(json?.items || json?.data || []);
    _buildIndexes(_rows);
    _buildStats();
    _initCollapsed();   // 初始化 _selectedRoots（默认只选第一个树深度=0 根节点）
    _restoreView();     // 从 localStorage 恢复视图（可覆盖 _selectedRoots）
    await _render();
    _loadCloudConfig(); // 异步拉取云端共享布局配置（覆盖本地，team 共享）
    // 若 DiffNavTree 已初始化，同步新数据
    if (_dnt) _dnt.setData(_rows);
  } catch (e) {
    $columns.innerHTML = `<div class="lv-empty">加载失败：${e.message}</div>`;
    _toast('加载失败: ' + e.message, 'error');
  }
}

// ── 版本选择器 ──────────────────────────────────────────────────────────

async function _loadVersionSelect() {
  if (!$versionSel) return;
  try {
    const json = await _invokeCapability('craft.gbop.release.search', {
      include_archived: false,
    });
    const versions = json?.items || [];
    $versionSel.innerHTML = '<option value="">选择版本…</option>';
    for (const v of versions) {
      const opt = document.createElement('option');
      opt.value = v.gid;
      let label = v.name || v.gid.slice(-6);
      if (v.status === 'frozen') label += ' (冻结)';
      opt.textContent = label;
      $versionSel.appendChild(opt);
    }
    // 预选当前版本
    if (_versionGid) {
      $versionSel.value = _versionGid;
    } else if (versions.length > 0) {
      // 无 URL 参数时自动选第一个
      _versionGid = versions[0].gid;
      _versionTag = versions[0].name || versions[0].gid.slice(-6);
      $versionSel.value = _versionGid;
    }
  } catch (e) {
    console.warn('加载版本列表失败:', e);
  }
}

$versionSel?.addEventListener('change', async () => {
  const gid = $versionSel.value;
  if (!gid) return;
  _versionGid = gid;
  const opt = $versionSel.selectedOptions[0];
  _versionTag = opt?.textContent?.replace(/\s*\(冻结\)$/, '') || gid.slice(-6);
  $versionLbl.textContent = `GBOP 树形视图${_versionTag ? ' — ' + _versionTag : ''}`;
  await _load();
});

// ── 渲染层 ────────────────────────────────────────────────────────────

/** 收集 gid 的所有后代 gid（递归） */
function _collectDescendants(gid, set) {
  for (const child of (_childMap.get(gid) || [])) {
    set.add(child.gid);
    _collectDescendants(child.gid, set);
  }
}

/** 渲染树深度=0 根节点选择栏 */
function _renderRootBar() {
  $wrap.querySelector('.lv-root-bar')?.remove();

  const bar = document.createElement('div');
  bar.className = 'lv-root-bar';

  const label = document.createElement('span');
  label.className = 'lv-root-bar-label';
  label.textContent = '产品BOP：';
  bar.appendChild(label);

  // 已选根节点各显示一个 chip
  for (const gid of _selectedRoots) {
    const root = _rowByGid.get(gid);
    if (!root) continue;

    const chip = document.createElement('span');
    chip.className = 'lv-root-chip selected';
    chip.dataset.gid = gid;

    const titleSpan = document.createElement('span');
    titleSpan.textContent = root.title || root.bom_row_label || '(未命名)';
    titleSpan.title = root.title || '';
    chip.appendChild(titleSpan);

    // "×" 移除按钮（仅在选了多个时才出现）
    if (_selectedRoots.size > 1) {
      const rmBtn = document.createElement('button');
      rmBtn.className = 'lv-root-chip-rm';
      rmBtn.title = '移除此产品对比';
      rmBtn.innerHTML = '<svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';
      rmBtn.addEventListener('click', e => {
        e.stopPropagation();
        _selectedRoots.delete(gid);
        _renderRootBar();
        _renderColumns();
      });
      chip.appendChild(rmBtn);
    }

    bar.appendChild(chip);
  }

  // "+ 添加对比" 按钮
  const addBtn = document.createElement('button');
  addBtn.className = 'lv-root-chip lv-root-add-btn';
  addBtn.id = 'lvRootAddBtn';
  addBtn.title = '从其他未归档BOP版本添加对比';
  addBtn.innerHTML =
    '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="flex-shrink:0">' +
    '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>' +
    '<span style="margin-left:4px">添加对比</span>';
  addBtn.addEventListener('click', e => {
    e.stopPropagation();
    _toggleRootPicker(addBtn);
  });
  bar.appendChild(addBtn);

  $wrap.insertBefore(bar, $columns);
}

/** 弹出/收起版本选择器 */
async function _toggleRootPicker(anchorBtn) {
  if (_rootPickerEl) {
    _closeRootPicker();
    return;
  }

  const picker = document.createElement('div');
  picker.className = 'lv-root-picker';
  picker.innerHTML = '<div class="lv-root-picker-msg">加载中…</div>';

  const rect = anchorBtn.getBoundingClientRect();
  picker.style.left = rect.left + 'px';
  picker.style.top  = (rect.bottom + 4) + 'px';
  document.body.appendChild(picker);
  _rootPickerEl = picker;

  // 点外侧关闭
  const closeOutside = e => {
    if (!picker.contains(e.target) && e.target !== anchorBtn) _closeRootPicker();
  };
  setTimeout(() => document.addEventListener('click', closeOutside, { once: false }), 0);
  picker._closeHandler = closeOutside;

  try {
    const json = await _invokeCapability('craft.gbop.release.search', {
      include_archived: false,
    });
    const available = (json?.items || []).filter(v => !_loadedVersionGids.has(v.gid));

    picker.innerHTML = '';
    if (available.length === 0) {
      picker.innerHTML = '<div class="lv-root-picker-msg">无其他可用BOP版本</div>';
      return;
    }

    for (const ver of available) {
      const item = document.createElement('div');
      item.className = 'lv-root-picker-item';
      item.textContent = ver.name || ver.gid.slice(-6);
      item.title = ver.name || '';
      item.addEventListener('click', async () => {
        _closeRootPicker();
        await _addVersionRoots(ver.gid, ver.name || ver.gid.slice(-6));
      });
      picker.appendChild(item);
    }
  } catch (e) {
    picker.innerHTML = `<div class="lv-root-picker-msg lv-root-picker-err">加载失败：${e.message}</div>`;
  }
}

function _closeRootPicker() {
  if (!_rootPickerEl) return;
  if (_rootPickerEl._closeHandler) document.removeEventListener('click', _rootPickerEl._closeHandler);
  _rootPickerEl.remove();
  _rootPickerEl = null;
}

/** 加载指定版本的条目并合并到当前视图 */
async function _addVersionRoots(versionGid, versionTag) {
  try {
    const json = await _invokeCapability('craft.gbop.catalog.read', {
      operation: 'entries.list',
      version_gid: versionGid,
    });
    const newRows = _flattenMeta(json?.items || json?.data || []);
    if (newRows.length === 0) { _toast('该版本暂无条目', 'warn'); return; }

    // 合并去重（按 gid）
    const existingGids = new Set(_rows.map(r => r.gid));
    for (const r of newRows) { if (!existingGids.has(r.gid)) _rows.push(r); }

    _loadedVersionGids.add(versionGid);
    _versionTagMap.set(versionGid, versionTag);
    _buildIndexes(_rows);
    _buildStats();

    // 把新版本中树深度=0 的根节点加入已选集合
    for (const r of newRows) {
      if (_treeDepth(r) === 0 && !r.parent_gid) _selectedRoots.add(r.gid);
    }

    await _render();
    _toast(`已添加「${versionTag}」`, 'ok');
  } catch (e) {
    _toast('添加失败: ' + e.message, 'error');
  }
}

function _render() {
  $columns.innerHTML = '';
  // GBOP 不需要根选择栏（depth=0 直接作为第一列显示）
  _renderColumns();
}

/**
 * 收集 lineage 数据引用（保留供 DiffNavTree 等使用）
 */
function _buildLineageData() {
  return {
    rows:         _rows,
    childMap:     _childMap,
    rowByGid:     _rowByGid,
    statsMap:     _statsMap,
    depthByGid:   _depthByGid,
    versionGid:   _versionGid,
    activeGid:    _activeGid,
    typeFilter:   _typeFilter,
    level1Filter: _level1Filter,
    searchText:   _searchText,
    applyActiveState: _applyActiveState,
    openOverlayPanel: _openOverlayPanel,
    refreshOverlayIfPinned: (gid) => { if (_opPinned) _openOverlayPanel(gid); },
    showCtxMenu:      _showCtxMenu,
    showDetailPopover: _openDetailPopover,
    openImageLightbox: _openImageLightbox,
    toast:        _toast,
    reloadData: async () => {
      await _reload();
    },
  };
}

/**
 * 应用本地亮/暗主题（data-lv-theme 属性控制 Catppuccin Latte/Mocha 切换）
 */
function _applyLvTheme() {
  if (_lvTheme === 'light') {
    document.documentElement.setAttribute('data-lv-theme', 'light');
  } else {
    document.documentElement.removeAttribute('data-lv-theme');
  }
  const btn   = document.getElementById('lvThemeToggle');
  const icon  = document.getElementById('lvThemeIcon');
  const label = document.getElementById('lvThemeLabel');
  if (!btn) return;
  const isLight = _lvTheme === 'light';
  btn.title = isLight ? '切换暗色模式' : '切换亮色模式';
  if (label) label.textContent = isLight ? '暗色' : '亮色';
  if (icon) {
    // 亮色时显示月亮，暗色时显示太阳
    icon.innerHTML = isLight
      ? '<path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"/>'
      : '<circle cx="12" cy="12" r="5"/>'
        + '<line x1="12" y1="1" x2="12" y2="3"/>'
        + '<line x1="12" y1="21" x2="12" y2="23"/>'
        + '<line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>'
        + '<line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>'
        + '<line x1="1" y1="12" x2="3" y2="12"/>'
        + '<line x1="21" y1="12" x2="23" y2="12"/>'
        + '<line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>'
        + '<line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>';
  }
}

function _renderColumns() {
  $columns.innerHTML = '';

  // 计算可见 gid 集合：所有已选根节点 + 其后代
  const visibleGids = new Set();
  const hasRoots = _selectedRoots.size > 0;
  if (hasRoots) {
    for (const gid of _selectedRoots) {
      visibleGids.add(gid);  // depth=0 节点自身也要可见
      _collectDescendants(gid, visibleGids);
    }
  } else {
    // 无选中根节点时，所有行可见
    _rows.forEach(r => visibleGids.add(r.gid));
  }

  // 第1级（线体）筛选：若 _level1Filter 有选中项，只显示这些线体及其后代
  const l1AllowedSet = _buildL1AllowedSet();

  // 按树深度分组（GBOP: 从深度=0 开始，depth=0 就是第一列）
  const levelMap = new Map();
  for (const r of _rows) {
    const lv = _treeDepth(r);
    if (!visibleGids.has(r.gid) && hasRoots) continue; // 未选中根节点的后代不显示
    if (l1AllowedSet && !l1AllowedSet.has(r.gid)) continue; // 第1级筛选
    if (lv > _maxDepth) continue;                   // 超出最大深度
    if (!levelMap.has(lv)) levelMap.set(lv, []);
    levelMap.get(lv).push(r);
  }

  if (levelMap.size === 0) {
    $columns.innerHTML = '<div class="lv-empty">暂无节点</div>';
    return;
  }

  const levels = [...levelMap.keys()].sort((a, b) => a - b);
  console.log('DEBUG: level-1 count in levelMap=', levelMap.get(1)?.length, 'total level-1 in _rows=', _rows.filter(r => _treeDepth(r)===1).length);

  for (const lv of levels) {
    const colEl = document.createElement('div');
    colEl.className = 'lv-col';
    colEl.dataset.level = lv;

    // 当前级别所有行（折叠和展开都要用）
    const allRowsAtLevel = levelMap.get(lv);

    // 列折叠判断：折叠时不渲染横排统计 chip，改为竖向窄条
    const isCollapsed = _collapsedCols.has(lv);
    if (isCollapsed) {
      colEl.classList.add('lv-col-collapsed');
      const miniHdr = document.createElement('div');
      miniHdr.className = 'lv-col-header lv-col-collapsed-hdr';
      miniHdr.title = `第 ${lv} 级 — 点击展开`;
      miniHdr.addEventListener('click', () => {
        _collapsedCols.delete(lv);
        _render();
      });
      const lvlSpan = document.createElement('div');
      lvlSpan.className = 'lv-col-collapsed-lvl';
      lvlSpan.textContent = lv;
      miniHdr.appendChild(lvlSpan);
      // 统计 chip 竖向排列
      const allNtCountC = {};
      for (const r of allRowsAtLevel) { if (r.node_type) allNtCountC[r.node_type] = (allNtCountC[r.node_type] || 0) + 1; }
      const allNtEntriesC = Object.entries(allNtCountC).sort((a, b) => b[1] - a[1]);
      for (const [nt, cnt] of allNtEntriesC) {
        const chip = document.createElement('div');
        chip.className = `lv-col-nt-chip lv-nt-${nt} lv-chip-vert`;
        chip.textContent = `${NT_ABBR[nt] || nt}${cnt}`;
        chip.title = `${NT_LABEL[nt] || nt}: ${cnt}`;
        miniHdr.appendChild(chip);
      }
      colEl.appendChild(miniHdr);
      $columns.appendChild(colEl);
      continue;
    }

    // 列头：第 N 级（树深度与显示级别一致，深度 1 = 第1级）+ 按节点类别统计
    const colNtFilter = _colTypeFilters.get(lv);
    let rowsAtLevel = allRowsAtLevel;
    if (colNtFilter) rowsAtLevel = allRowsAtLevel.filter(r => r.node_type === colNtFilter);
    const hdrEl = document.createElement('div');
    hdrEl.className = 'lv-col-header';
    const hdrSpan = document.createElement('span');
    hdrSpan.textContent = `第 ${lv} 级`;
    hdrEl.appendChild(hdrSpan);

    // 按 node_type 统计（用全量数据），被筛掉的变灰
    const allNtCount = {}, filtNtCount = {};
    for (const r of allRowsAtLevel) { if (r.node_type) allNtCount[r.node_type] = (allNtCount[r.node_type] || 0) + 1; }
    if (colNtFilter) {
      for (const r of rowsAtLevel) { if (r.node_type) filtNtCount[r.node_type] = (filtNtCount[r.node_type] || 0) + 1; }
    }
    const allNtEntries = Object.entries(allNtCount).sort((a, b) => b[1] - a[1]);
    for (const [nt, cnt] of allNtEntries) {
      const chip = document.createElement('span');
      const isActive = _colTypeFilters.get(lv) === nt;
      const showCnt = isActive && colNtFilter ? (filtNtCount[nt] || 0) : cnt;
      chip.className = `lv-col-nt-chip lv-nt-${nt}`;
      if (isActive) chip.classList.add('active');
      if (colNtFilter && !isActive) chip.classList.add('muted');
      chip.textContent = `${NT_ABBR[nt] || nt}${showCnt}`;
      chip.title = `${NT_LABEL[nt] || nt}: ${cnt}，点击筛选当前列`;
      chip.dataset.nt = nt;
      chip.dataset.level = lv;
      chip.addEventListener('click', e => {
        e.stopPropagation();
        const lv2 = parseInt(e.currentTarget.dataset.level);
        const nt2 = e.currentTarget.dataset.nt;
        if (_colTypeFilters.get(lv2) === nt2) {
          _colTypeFilters.delete(lv2);
        } else {
          _colTypeFilters.set(lv2, nt2);
        }
        _applyFilters();
      });
      hdrEl.appendChild(chip);
    }

    colEl.appendChild(hdrEl);

    // 列折叠按钮（列头左侧）
    const collapseBtn = document.createElement('span');
    collapseBtn.className = 'lv-col-collapse-btn';
    collapseBtn.title = '折叠此列';
    collapseBtn.innerHTML = '◀';
    collapseBtn.addEventListener('click', e => {
      e.stopPropagation();
      _collapsedCols.add(lv);
      _render();
    });
    hdrEl.insertBefore(collapseBtn, hdrEl.firstChild);

    // 卡片滚动容器（列头固定，卡片区可滚动 + 弹性垫片）
    const bodyEl = document.createElement('div');
    bodyEl.className = 'lv-col-body';

    const parentsSet  = new Set(rowsAtLevel.map(r => r.parent_gid || null));

    for (const parentGid of parentsSet) {
      let children = (_childMap.get(parentGid) || []).filter(r => {
        if (_treeDepth(r) !== lv) return false;
        if (l1AllowedSet && !l1AllowedSet.has(r.gid)) return false;
        return true;
      });
      // 列内类型筛选：若某父级没有匹配的子节点，保留第一个子节点占位（变灰）
      if (colNtFilter) {
        const matched = children.filter(r => r.node_type === colNtFilter);
        if (matched.length === 0 && children.length > 0) {
          // 整个组被筛掉了，在占位卡片上标明不可见
          const placeholder = _renderCard(children[0], true);
          placeholder.style.opacity = '0.15';
          placeholder.style.pointerEvents = 'none';
          bodyEl.appendChild(placeholder);
          continue;
        }
        children = matched;
      }
      if (children.length === 0) continue;

      // 若 parent 被折叠，渲染折叠占位替代 group
      if (_collapsed.has(parentGid) && parentGid !== null) {
        bodyEl.appendChild(_renderCollapseHint(parentGid, children.length));
        continue;
      }

      const groupEl = document.createElement('div');
      groupEl.className = 'lv-group';
      groupEl.dataset.parentGid = parentGid ?? 'null';

      for (const row of children) {
        if (!_passFilter(row)) continue;
        if (_collapsed.has(row.parent_gid)) continue;
        groupEl.appendChild(_renderCard(row));
      }

      if (groupEl.children.length > 0) bodyEl.appendChild(groupEl);
    }

    colEl.appendChild(bodyEl);

    $columns.appendChild(colEl);
  }

  if (_activeGid) _applyActiveState(_activeGid);
}

function _renderCard(row) {
  const cardEl = document.createElement('div');
  cardEl.className = 'lv-card';
  cardEl.dataset.gid = row.gid;
  cardEl.draggable = true;

  // 悬浮按钮（延迟到首次 mouseenter 创建，不用在初始渲染中创建 27000 个按钮）
  // 主体
  const mainEl = document.createElement('div');
  mainEl.className = 'lv-card-main';

  const row1El = document.createElement('div');
  row1El.className = 'lv-row1';
  const typeEl = document.createElement('span');
  typeEl.className = `lv-type lv-nt-${row.node_type || 'part'}`;
  typeEl.textContent = NT_ABBR[row.node_type] || row.node_type || '—';
  row1El.appendChild(typeEl);

  if (row.status) {
    const stEl = document.createElement('span');
    stEl.className = `lv-status lv-st-${row.status}`;
    stEl.title = row.status;
    row1El.appendChild(stEl);
  }

  // 挂载状态徽标（创建后先不 appendChild，在 seqEl 之前插入）
  const valid = row.valid_primary_link_count || 0;
  const total = row.primary_link_count || 0;
  let _linkBadge = null;
  if (total > 0) {
    _linkBadge = document.createElement('span');
    if (valid > 0) {
      _linkBadge.className = 'lv-link-badge';
      _linkBadge.textContent = valid;
      _linkBadge.title = `已挂载 ${valid} 个有效实体`;
    } else {
      _linkBadge.className = 'lv-link-badge lv-link-badge-stale';
      _linkBadge.textContent = '⚠';
      _linkBadge.title = `挂载引用已过时（${total} 条），请重跑 Auto-Link 更新`;
    }
  }

  if (_linkBadge) row1El.appendChild(_linkBadge);

  // VPPS 标识（右侧）
  if (row.vpps) {
    const vppsEl = document.createElement('span');
    vppsEl.className = 'lv-vpps-tag';
    vppsEl.textContent = row.vpps;
    vppsEl.title = `VPPS: ${row.vpps}`;
    row1El.appendChild(vppsEl);
  }

  const row2El = document.createElement('div');
  row2El.className = 'lv-row2';
  const titleEl = document.createElement('span');
  titleEl.className = 'lv-title';
  titleEl.title = row.title || '';
  titleEl.textContent = _highlightText(row.title || '(无名称)');
  row2El.appendChild(titleEl);

  mainEl.appendChild(row1El);
  mainEl.appendChild(row2El);
  cardEl.appendChild(mainEl);

  // 统计小框（同步渲染4行，content-visibility 会跳过视口外卡片的绘制）
  const statsBox = _renderStatsBox(row);
  cardEl.appendChild(statsBox);

  // 右侧连接桥
  const bridge = document.createElement('div');
  bridge.className = 'lv-bridge-right';
  cardEl.appendChild(bridge);

  // ⚡ 延迟创建悬浮按钮和统计内容：首次 mouseenter 时一次补全
  cardEl.addEventListener('mouseenter', _lazyHydrateCard, { once: true });

  return cardEl;
}

function _lazyHydrateCard(e) {
  const cardEl = e.currentTarget;
  const gid = cardEl.dataset.gid;
  if (!gid) return;

  // 创建悬浮按钮（统计框已同步渲染，不需要再填充）
  const existingBtns = cardEl.querySelectorAll('.lv-fbtn');
  if (existingBtns.length === 0) {
    const fbTop    = _makeFBtn('＋', 'lv-fbtn-top',    'add_above');
    const fbBottom = _makeFBtn('＋', 'lv-fbtn-bottom', 'add_below');
    const fbRight  = _makeFBtn('→', 'lv-fbtn-right',  'add_child');
    cardEl.insertBefore(fbTop,    cardEl.firstChild);
    cardEl.insertBefore(fbBottom, cardEl.firstChild);
    cardEl.insertBefore(fbRight,  cardEl.firstChild);
  }
}

function _makeFBtn(label, cls, action) {
  const btn = document.createElement('button');
  btn.className = `lv-fbtn ${cls}`;
  btn.textContent = label;
  btn.dataset.action = action;
  btn.addEventListener('click', e => {
    e.stopPropagation();
    const gid = btn.closest('.lv-card')?.dataset.gid;
    if (gid) _handleFBtnAction(action, gid);
  });
  return btn;
}

/**
 * 判断节点属于哪个统计族
 * @param {string} nt - node_type
 * @returns {'level'|'process'|'operation'|'leaf'}
 */
function _getStatsFamily(nt) {
  if (_LEVEL_STATS_PRIORITY[nt]) return 'level';
  if (nt === 'process') return 'process';
  if (nt === 'operation') return 'operation';
  return 'leaf';
}

/**
 * 创建单行统计 DOM
 */
function _makeStatsRow(label, count) {
  const rowEl = document.createElement('div');
  rowEl.className = 'lv-stats-row';
  if (label && count !== undefined) {
    rowEl.innerHTML = `<span class="lv-stats-nt">${label}</span><b>${count}</b>`;
    rowEl.title = `${label}: ${count}`;
  } else {
    rowEl.style.visibility = 'hidden';
    rowEl.innerHTML = '<span class="lv-stats-nt">—</span><b></b>';
    rowEl.title = '';
  }
  return rowEl;
}

/**
 * 缩略图 + 统计混合渲染（族2/3）
 * @param {HTMLElement} box - stats box container
 * @param {object} row - 行数据
 * @param {object} desc - 后代统计
 * @param {string} picField - 缩略图字段名
 * @param {string[]} fallbackPrio - 无缩略图时的统计优先级
 */
function _renderThumbnailStatsBox(box, row, desc, picField, fallbackPrio) {
  const picVal = row[picField];
  const hasPic = picVal && (Array.isArray(picVal) ? picVal.length > 0 : true);

  if (hasPic) {
    // 有图：整框只显示图片，不显示统计行
    const pics = Array.isArray(picVal) ? picVal : [picVal];
    const firstPic = typeof pics[0] === 'string' ? pics[0] : (pics[0]?.url || pics[0]?.src || '');
    const fill = document.createElement('div');
    fill.className = 'lv-stats-thumb-fill';
    fill.title = picField === 'process_flow_pic' ? '工艺流程图' : '工艺卡图片';
    if (firstPic) {
      const img = document.createElement('img');
      img.className = 'lv-thumb-fill';
      img.src = firstPic;
      img.alt = picField;
      img.onerror = function () {
        fill.innerHTML = '';
        fill.appendChild(_makeStatsRow('—'));
      };
      fill.appendChild(img);
    } else {
      fill.appendChild(_makeStatsRow('—'));
    }
    box.appendChild(fill);
  } else {
    // 无缩略图降级为 4 行统计
    _renderRegularStatsRows(box, desc, fallbackPrio);
  }
}

/**
 * 叶子节点渲染（4 行空占位）
 */
function _renderLeafStatsBox(box) {
  for (let i = 0; i < 4; i++) {
    box.appendChild(_makeStatsRow(null));
  }
}

/**
 * 4 行统计渲染
 */
function _renderRegularStatsRows(box, desc, priority) {
  const top4 = desc && Object.keys(desc).length > 0
    ? _getTop4Stats(desc, priority)
    : [];
  for (let i = 0; i < 4; i++) {
    const s = top4[i];
    const label = s ? NT_ABBR[s[0]] || s[0] : null;
    const cnt = s ? s[1] : undefined;
    box.appendChild(_makeStatsRow(label, cnt));
  }
}

function _renderStatsBox(row) {
  const box = document.createElement('div');
  box.className = 'lv-stats-box';
  box.dataset.statsGid = row.gid;

  const desc = _getDescendantStats(row.gid);
  const nt = row.node_type;
  const family = _getStatsFamily(nt);

  if (family === 'level') {
    _renderRegularStatsRows(box, desc, _LEVEL_STATS_PRIORITY[nt]);
  } else if (family === 'process') {
    _renderThumbnailStatsBox(box, row, desc, 'process_flow_pic', _PROCESS_STATS_PRIORITY);
  } else if (family === 'operation') {
    _renderThumbnailStatsBox(box, row, desc, 'process_chart_pic', _OP_STATS_PRIORITY);
  } else {
    _renderLeafStatsBox(box);
  }

  return box;
}

/**
 * 按优先级取前 N 个有后代的统计项
 * @param {object} desc - 后代统计 {nt: count}
 * @param {string[]} priority - 优先级顺序
 * @param {number} [limit=4] - 取前几个
 */
function _getTop4Stats(desc, priority, limit) {
  limit = limit || 4;
  const prio = priority || STATS_PRIORITY;
  const byPrio = prio
    .filter(nt => desc[nt])
    .map(nt => [nt, desc[nt]]);
  const others = Object.entries(desc)
    .filter(([nt]) => !prio.includes(nt))
    .sort((a, b) => b[1] - a[1]);
  return [...byPrio, ...others].slice(0, limit);
}

function _renderCollapseHint(parentGid, count) {
  const hint = document.createElement('div');
  hint.className = 'lv-collapse-hint';
  hint.dataset.expandGid = parentGid;
  hint.textContent = `▶ ${count} 个子节点`;
  hint.addEventListener('click', () => {
    _collapsed.delete(parentGid);
    _render();
  });
  return hint;
}

function _renderCollapsedHints() {
  // For each collapsed gid, ensure the next column shows a hint
  // This is handled inline in _render() per level
}

// ── 右侧边栏 ──────────────────────────────────────────────────────────

function _toggleSidebar() {
  _sidebarOpen = !_sidebarOpen;
  $sidebar.classList.toggle('lv-sidebar-open', _sidebarOpen);
  $sidebar.classList.toggle('collapsed', !_sidebarOpen);
  document.documentElement.style.setProperty('--sb-width', _sidebarOpen ? '320px' : '0px');
  $sbToggle.innerHTML = _sidebarOpen ? '▶' : '◀';
  $sbToggle.title = _sidebarOpen ? '折叠边栏' : '展开边栏';
}

function _switchSbTab(tab) {
  _sbActiveTab = tab;
  $sbTabs.querySelectorAll('.lv-sb-tab').forEach(el => el.classList.toggle('active', el.dataset.tab === tab));
  _renderSidebarContent();
}

function _renderSidebarContent() {
  const isPbom = _sbActiveTab === 'pbom';
  $sbBody.style.display  = isPbom ? 'none' : '';
  if ($dntWrap) $dntWrap.style.display = isPbom ? 'flex' : 'none';

  if (_sbActiveTab === 'links') {
    $sbBody.innerHTML = '';
    if (!_activeGid) {
      $sbBody.innerHTML = '<div class="lv-sb-empty">点击卡片查看关联</div>';
      return;
    }
    const children = _childMap.get(_activeGid) || [];
    if (children.length === 0) {
      $sbBody.innerHTML = '<div class="lv-sb-empty">此节点暂无关联</div>';
      return;
    }
    const container = document.createElement('div');
    container.className = 'lv-sb-children';
    for (const child of children.slice(0, 20)) {
      const item = document.createElement('div');
      item.className = 'lv-sb-link-item';
      const dot = document.createElement('span');
      dot.className = `lv-nt-dot lv-nt-${child.node_type || 'part'}`;
      item.appendChild(dot);
      const label = document.createElement('span');
      label.textContent = `${NT_ABBR[child.node_type] || child.node_type} ${child.title || '(无名称)'}`;
      label.style.flex = '1';
      item.appendChild(label);
      container.appendChild(item);
    }
    $sbBody.appendChild(container);
  } else if (_sbActiveTab === 'pbom') {
    _ensureDnt();
    if (_dnt) _dnt.setActiveNode(_activeGid);
  }
}

/** 懒初始化 DiffNavTree（PBOM tab 首次打开时创建） */
function _ensureDnt() {
  if (_dnt) {
    _dnt.setData(_rows);
    return;
  }
  if (!window.DiffNavTree || !$dntWrap) return;
  _dnt = new DiffNavTree({
    mountEl:      $dntWrap,
    title:        'PBOM 对比',
    idField:      'gid',
    labelField:   'title',
    parentField:  'parent_gid',
    typeField:    'node_type',
    vppsField:    'vpps',
    compareFields: [
      { key: 'title',     label: '名称' },
      { key: 'node_type', label: '类型' },
    ],
    typeAbbr:     NT_ABBR,
    defaultExpandDepth: 1,
    onActivate: (gid, row) => {
      // PBOM 树节点激活 → 通过 vpps 找 BOP 对应节点
      const bopRow = row.vpps
        ? [..._rowByGid.values()].find(r => r.vpps && r.vpps === row.vpps)
        : _rowByGid.get(gid);
      if (bopRow) {
        _applyActiveState(bopRow.gid);
      }
    },
    onCompareRequest: async () => {
      try {
        const res = await _invokeCapability('craft.bop.linked_parts.get', {
          version_gid: _versionGid,
        });
        _dnt.setCompareData(res?.legacy_items || res?.items || [], {
          primaryLabel:   'PBOM',
          secondaryLabel: 'BOP已挂载',
        });
      } catch (e) {
        _toast('PBOM 比对数据加载失败：' + e.message, 'error');
      }
    },
  });
  _dnt.setData(_rows);
}

function _highlightText(text) {
  if (!_searchText) return text;
  const idx = text.toLowerCase().indexOf(_searchText.toLowerCase());
  if (idx === -1) return text;
  return text.slice(0, idx)
    + `<mark class="lv-highlight">${text.slice(idx, idx + _searchText.length)}</mark>`
    + text.slice(idx + _searchText.length);
}

function _passFilter(row) {
  // type filter: null = 全部显示, [] = 全不选（阻断）, [...types] = 筛选
  if (_typeFilter !== null && _typeFilter.length === 0) return false;
  if (_typeFilter !== null && _typeFilter.length > 0 && !_typeFilter.includes(row.node_type)) return false;
  // search
  if (_searchText && !(row.title || '').toLowerCase().includes(_searchText.toLowerCase())) return false;
  return true;
}

/**
 * 第1级（线体）筛选：若 _level1Filter 不是 null（有设置），返回允许显示的 gid 集合。
 * _level1Filter === null = 全部显示
 * _level1Filter = Set() = 全不选（阻断）
 * _level1Filter = Set([...gids]) = 筛选
 */
function _buildL1AllowedSet() {
  if (_level1Filter === null) return null;
  const allowed = new Set();
  if (_level1Filter.size === 0) return allowed; // 空 Set = 全不选，阻断
  for (const l1gid of _level1Filter) {
    allowed.add(l1gid);
    _collectDescendants(l1gid, allowed);
  }
  return allowed;
}

/**
 * 构建第1级筛选下拉
 * _level1Filter: null = 全部, Set = 已筛选（空Set=全不选）
 */
function _buildLevel1Dropdown() {
  $l1DD.innerHTML = '';

  // GBOP：顶级节点在 depth=0（不同于 BOP 的 depth=1）
  const l1Nodes = _rows.filter(r => _treeDepth(r) === 0);

  if (l1Nodes.length === 0) {
    const msg = document.createElement('div');
    msg.className = 'lv-root-picker-msg';
    msg.textContent = '暂无顶级节点';
    $l1DD.appendChild(msg);
    return;
  }

  const isAll = _level1Filter === null; // 全部显示模式

  // "全部" 选项
  const allItem = document.createElement('label');
  allItem.className = 'lv-dd-item';
  const allCb = document.createElement('input');
  allCb.type = 'checkbox';
  allCb.checked = isAll;
  allCb.dataset.allL1 = '1';
  const allDot = document.createElement('span');
  allDot.className = 'lv-nt-dot';
  allDot.style.background = '#82b366';
  allItem.appendChild(allCb);
  allItem.appendChild(allDot);
  allItem.appendChild(document.createTextNode('全部系统'));
  $l1DD.appendChild(allItem);

  // "全不选" 选项
  const noneItem = document.createElement('label');
  noneItem.className = 'lv-dd-item';
  const noneCb = document.createElement('input');
  noneCb.type = 'checkbox';
  noneCb.checked = false;
  noneCb.dataset.noneL1 = '1';
  const noneDot = document.createElement('span');
  noneDot.className = 'lv-nt-dot';
  noneDot.style.background = '#585b70';
  noneItem.appendChild(noneCb);
  noneItem.appendChild(noneDot);
  noneItem.appendChild(document.createTextNode('全不选'));
  $l1DD.appendChild(noneItem);

  for (const row of l1Nodes) {
    const item = document.createElement('label');
    item.className = 'lv-dd-item';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.value = row.gid;
    cb.checked = isAll || (_level1Filter && _level1Filter.has(row.gid));
    const dot = document.createElement('span');
    dot.className = 'lv-nt-dot lv-nt-line_process';
    item.appendChild(cb);
    item.appendChild(dot);
    item.appendChild(document.createTextNode(row.title || '(未命名)'));
    $l1DD.appendChild(item);
  }

  // 所有复选框 change → 重新计算 _level1Filter
  const _recalc = () => {
    const checked = [...$l1DD.querySelectorAll('input[type=checkbox]:not([data-all-l1]):not([data-none-l1])')]
      .filter(c => c.checked).map(c => c.value);
    console.log('DEBUG _recalc: checked=', checked, 'l1Nodes.length=', l1Nodes.length);
    if (checked.length === l1Nodes.length) {
      _level1Filter = null; // 全选 = null（全部显示）
    } else {
      _level1Filter = new Set(checked);
    }
    console.log('DEBUG _recalc result: _level1Filter=', _level1Filter);
    allCb.checked = _level1Filter === null;
    noneCb.checked = _level1Filter !== null && _level1Filter.size === 0;
    _applyFilters();
  };

  $l1DD.querySelectorAll('input[type=checkbox]:not([data-all-l1]):not([data-none-l1])').forEach(cb => {
    cb.addEventListener('change', _recalc);
  });

  allCb.addEventListener('change', () => {
    if (allCb.checked) {
      _level1Filter = null;
      $l1DD.querySelectorAll('input[type=checkbox]:not([data-all-l1]):not([data-none-l1])').forEach(c => { c.checked = true; });
      noneCb.checked = false;
      _applyFilters();
    }
  });

  noneCb.addEventListener('change', () => {
    if (noneCb.checked) {
      _level1Filter = new Set();
      $l1DD.querySelectorAll('input[type=checkbox]:not([data-all-l1]):not([data-none-l1])').forEach(c => { c.checked = false; });
      allCb.checked = false;
      _applyFilters();
    }
  });
}

// ── 三态激活 ─────────────────────────────────────────────────────────

function _applyActiveState(activeGid) {
  _activeGid = activeGid;
  const activeRow = _rowByGid.get(activeGid);
  if (!activeRow) return;

  // collect ancestors
  const ancestors = new Set();
  let cur = activeRow;
  while (cur?.parent_gid) {
    ancestors.add(cur.parent_gid);
    cur = _rowByGid.get(cur.parent_gid);
  }

  // siblings (same parent, different gid)
  const siblings = new Set(
    (_childMap.get(activeRow.parent_gid || null) || [])
      .filter(r => r.gid !== activeGid)
      .map(r => r.gid)
  );

  // direct children (1 level)
  const children = new Set(
    (_childMap.get(activeGid) || []).map(r => r.gid)
  );

  // descendants — all levels (full recursion)
  const descendants = new Set();
  _collectDescendants(activeGid, descendants);

  // ⚡ 只清除当前有高亮的卡片，避免遍历全部 9000 张
  $columns.querySelectorAll('.lv-card.active-node, .lv-card.active-parent, .lv-card.active-sibling, .lv-card.active-child')
    .forEach(el => el.classList.remove('active-node', 'active-parent', 'active-sibling', 'active-child'));

  // 用直接 gid 选择器精准设置高亮
  const _set = (set, cls) => {
    for (const gid of set) {
      const el = $columns.querySelector(`.lv-card[data-gid="${gid}"]`);
      if (el) el.classList.add(cls);
    }
  };
  _set(new Set([activeGid]), 'active-node');
  _set(ancestors, 'active-parent');
  _set(siblings, 'active-sibling');
  _set(children, 'active-child');
  _set(descendants, 'active-child');

  // group highlight（遍历只针对当前列可见的 group，已由 content-visibility 消减）
  $columns.querySelectorAll('.lv-group.group-has-active-node, .lv-group.group-has-active-child')
    .forEach(g => g.classList.remove('group-has-active-node', 'group-has-active-child'));
  const activeParentGid = activeRow.parent_gid || 'null';
  const activeGidStr = activeGid;
  const parentGroup = $columns.querySelector(`.lv-group[data-parent-gid="${activeParentGid}"]`);
  if (parentGroup) parentGroup.classList.add('group-has-active-node');
  const childGroup = $columns.querySelector(`.lv-group[data-parent-gid="${activeGidStr}"]`);
  if (childGroup) childGroup.classList.add('group-has-active-child');

  // scroll active card into view (Miller Columns centered scrolling)
  if (_miller) _miller.centerOnCard(activeGid);

  // BOP 节点激活 → 同步 PBOM 树（若当前显示 PBOM tab）
  if (_sbActiveTab === 'pbom' && _dnt) {
    _dnt.setActiveNode(activeGid);
  }

  // 更新右侧边栏内容
  _renderSidebarContent();
}

// ── 过滤应用 ─────────────────────────────────────────────────────────

function _applyFilters() {
  _render();
  if (_activeGid) _applyActiveState(_activeGid);
}

// ── 拖拽 ─────────────────────────────────────────────────────────────

function _getDropPosition(e, cardEl) {
  const rect = cardEl.getBoundingClientRect();
  const relY = e.clientY - rect.top;
  const relX = e.clientX - rect.left;
  const h = rect.height;
  const w = rect.width;
  if (relY < h * 0.25) return 'up';
  if (relY > h * 0.75) return 'down';
  if (relX > w * 0.75) return 'right';
  return null;
}

function _clearDropClasses() {
  document.querySelectorAll('.lv-card.drop-above,.lv-card.drop-below,.lv-card.drop-under')
    .forEach(el => el.classList.remove('drop-above', 'drop-below', 'drop-under'));
}

async function _patchEntry(gid, body) {
  await _invokeCapability('craft.gbop.entity.change.apply', {
    operation: 'entry.update',
    gid,
    updates: body,
  });
}

// ── 内联改名 ─────────────────────────────────────────────────────────

function _startInlineRename(cardEl) {
  const gid      = cardEl.dataset.gid;
  const titleEl  = cardEl.querySelector('.lv-title');
  const row      = _rowByGid.get(gid);
  if (!titleEl || !row) return;

  const input = document.createElement('input');
  input.className = 'lv-inline-input';
  input.value = row.title || '';
  titleEl.replaceWith(input);
  input.focus();
  input.select();

  const commit = async () => {
    const newTitle = input.value.trim();
    if (!newTitle || newTitle === row.title) {
      input.replaceWith(titleEl);
      return;
    }
    try {
      await _patchEntry(gid, { vpps_desc: newTitle });
      row.title = newTitle;
      row.vpps_desc = newTitle;
      titleEl.textContent = newTitle;
      input.replaceWith(titleEl);
      _toast('已保存', 'ok', 1500);
    } catch (e) {
      input.replaceWith(titleEl);
      _toast('保存失败: ' + e.message, 'error');
    }
  };

  input.addEventListener('blur',    commit);
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter')  { e.preventDefault(); commit(); }
    if (e.key === 'Escape') { input.replaceWith(titleEl); }
  });
}

// ── 节点类型配置（新建弹窗，operation 优先顺序）──────────────────────

// 类型顺序：从操作（叶子）到线体（根），资源类，最后工作项/零件
const _ORDERED_NODE_TYPES = [
  ['system',    '系统 (L1)'],
  ['device',    '装置 (L2)'],
  ['part',      '零部件 (L3)'],
  ['process',   '总装工序 (L4)'],
  ['operation', '总装操作 (L5)'],
];

// 建议子节点类型映射（根据父节点类型）
const _CHILD_TYPE_MAP = {
  version:  'system',
  system:   'device',
  device:   'part',
  part:     'process',
  process:  'operation',
};

// 各类型的表单字段定义
// type: 'text' | 'number' | 'select' | 'pics'
const _NODE_FIELDS = {
  version:          [{ id:'vpps_desc', label:'版本名称', type:'text', required:true },
                     { id:'seq_no', label:'序号', type:'number' }],
  system:           [{ id:'vpps_desc', label:'系统名称', type:'text', required:true },
                     { id:'vpps', label:'VPPS编码', type:'text' },
                     { id:'seq_no', label:'序号', type:'number' }],
  device:           [{ id:'vpps_desc', label:'装置名称', type:'text', required:true },
                     { id:'vpps', label:'VPPS编码', type:'text' },
                     { id:'seq_no', label:'序号', type:'number' }],
  part:             [{ id:'vpps_desc', label:'零部件名称', type:'text', required:true },
                     { id:'vpps', label:'VPPS编码', type:'text' },
                     { id:'importance', label:'重要度', type:'text' },
                     { id:'seq_no', label:'序号', type:'number' }],
  process:          [{ id:'vpps_desc', label:'工序名称', type:'text', required:true },
                     { id:'op_code', label:'工序编码', type:'text' },
                     { id:'op_name', label:'工序全称', type:'text' },
                     { id:'standard_time', label:'标准工时', type:'number' },
                     { id:'description', label:'描述', type:'text' },
                     { id:'seq_no', label:'序号', type:'number' }],
  operation:        [{ id:'vpps_desc', label:'操作名称', type:'text', required:true },
                     { id:'op_code', label:'操作编码', type:'text' },
                     { id:'op_name', label:'操作全称', type:'text' },
                     { id:'standard_time', label:'标准工时', type:'number' },
                     { id:'description', label:'描述', type:'text' },
                     { id:'seq_no', label:'序号', type:'number' }],
};

/**
 * 上传图片到 /api/gbop/pics/upload，返回 URL
 * file: File 对象
 */
async function _uploadBopPic(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = reject;
    reader.onload = async ev => {
      const dataUrl = ev.target.result;
      const comma   = dataUrl.indexOf(',');
      const mime    = dataUrl.slice(5, dataUrl.indexOf(';'));
      const b64     = dataUrl.slice(comma + 1);
      try {
        const response = await _invokeCapability('craft.bop.picture.upload', {
          filename: file.name,
          mime,
          data_b64: b64,
        });
        const res = response?.data || response;
        if (!res?.url) throw new Error('上传失败：无返回 URL');
        // 转为绝对 URL，确保 img.src 在 iframe 中可访问
        if (res.url.startsWith('http')) { resolve(res.url); return; }
        const cfg  = await (window.parent?.electronAPI?.getConfig?.() || window.electronAPI?.getConfig?.() || Promise.resolve({}));
        const runtimeBase = await window.AI00RuntimeConfig?.getRuntimeBackendBase?.(cfg?.backendUrl || '')
        const base = (runtimeBase || cfg?.backendUrl || '').replace(/\/$/, '');
        resolve(base + res.url);
      } catch (e) { reject(e); }
    };
    reader.readAsDataURL(file);
  });
}

/**
 * 渲染图片管理区 DOM（新建弹窗 & 详情面板共用）
 * container: 挂载目标 el
 * urls: string[] 当前已有图片 URL
 * max: 最大数量
 * onChange: (urls) => void
 */
function _renderPicArea(container, urls, max, onChange) {
  container.innerHTML = '';
  const area = document.createElement('div');
  area.className = 'lv-pic-area';

  function refresh(list) {
    area.innerHTML = '';
    list.forEach((url, i) => {
      const thumb = document.createElement('div');
      thumb.className = 'lv-pic-thumb';
      thumb.innerHTML = `<img src="${url}" title="点击全屏预览"><button class="lv-pic-del" title="删除">×</button>`;
      thumb.querySelector('img').addEventListener('click', () => {
        const win = window.open(); win.document.write(`<body style="margin:0;background:#000"><img src="${url}" style="max-width:100vw;max-height:100vh;object-fit:contain;display:block;margin:auto"></body>`);
      });
      thumb.querySelector('.lv-pic-del').addEventListener('click', () => {
        list.splice(i, 1);
        onChange([...list]);
        refresh(list);
      });
      area.appendChild(thumb);
    });

    if (list.length < max) {
      const addLabel = document.createElement('label');
      addLabel.className = 'lv-pic-add';
      addLabel.title = '选择图片';
      addLabel.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg><span>添加图片</span>`;
      const fileInput = document.createElement('input');
      fileInput.type = 'file';
      fileInput.accept = 'image/*';
      fileInput.multiple = true;
      fileInput.style.display = 'none';
      fileInput.addEventListener('change', async () => {
        const files = Array.from(fileInput.files).slice(0, max - list.length);
        if (!files.length) return;
        const status = document.createElement('span');
        status.className = 'lv-pic-uploading';
        status.textContent = '上传中…';
        area.appendChild(status);
        try {
          for (const f of files) {
            if (list.length >= max) break;
            const url = await _uploadBopPic(f);
            list.push(url);
          }
          onChange([...list]);
          refresh(list);
        } catch (e) {
          status.remove();
          _toast('图片上传失败: ' + e.message, 'error');
        }
        fileInput.value = '';
      });
      addLabel.appendChild(fileInput);
      area.appendChild(addLabel);
    }
  }

  refresh([...urls]);
  container.appendChild(area);
}

// ── 内联对話框（Electron 兼容，替代 prompt/confirm）─────────────────
// _promptText / _confirmDialog 已提取至 web/shared/lv_utils.js

// ── 新建节点（富弹窗）────────────────────────────────────────────────

/**
 * 打开节点新建对话框
 * action: 'add_above' | 'add_below' | 'add_child' | 'add_new'
 * refGid: 参考节点 GID（null 时为工具栏新建）
 */
async function _openNodeDialog(action, refGid) {
  const refRow = refGid ? _rowByGid.get(refGid) : null;

  // 确定默认类型
  let defaultType;
  if (action === 'add_above' || action === 'add_below') {
    defaultType = refRow?.node_type || 'operation';
  } else if (action === 'add_child') {
    defaultType = _CHILD_TYPE_MAP[refRow?.node_type] || 'operation';
  } else {
    // 工具栏新建：根据当前选中节点推断
    const activeRow = _activeGid ? _rowByGid.get(_activeGid) : null;
    defaultType = _CHILD_TYPE_MAP[activeRow?.node_type] || 'line_process';
  }

  return new Promise(resolve => {
    const overlay = document.createElement('div');
    overlay.className = 'lv-dialog-overlay';
    const typeOpts = _ORDERED_NODE_TYPES.map(([v, l]) =>
      `<option value="${v}"${v === defaultType ? ' selected' : ''}>${l}</option>`).join('');
    overlay.innerHTML = `<div class="lv-dialog-box lv-ndlg-box">
      <div class="lv-ndlg-hdr">
        <span class="lv-ndlg-hdr-title">新建节点</span>
        <select class="lv-dialog-select lv-ndlg-type-sel" id="_ndlgType">${typeOpts}</select>
      </div>
      <div class="lv-ndlg-fields" id="_ndlgFields"></div>
      <div class="lv-dialog-btns">
        <button class="lv-btn lv-btn-sm" id="_ndlgCancel">取消</button>
        <button class="lv-btn lv-btn-sm" id="_ndlgOk"
          style="border-color:var(--blue,#89b4fa);color:var(--blue,#89b4fa)">创建</button>
      </div>
    </div>`;
    document.body.appendChild(overlay);

    const typeSelect  = overlay.querySelector('#_ndlgType');
    const fieldsWrap  = overlay.querySelector('#_ndlgFields');
    // pending pic lists keyed by picField
    const _pendingPics = {};

    function renderFields() {
      const type   = typeSelect.value;
      const defs   = _NODE_FIELDS[type] || [{ id:'title', label:'名称', type:'text', required:true }];
      fieldsWrap.innerHTML = '';
      for (const def of defs) {
        const wrap = document.createElement('div');
        wrap.className = 'lv-ndlg-field';
        if (def.type === 'text' || def.type === 'number') {
          wrap.innerHTML = `<label>${def.label || def.id}</label>
            <input class="lv-dialog-input" id="_ndlgF_${def.id}" type="${def.type}"
              placeholder="${def.required ? '必填' : '可选'}">`;
        } else if (def.type === 'select') {
          const opts = def.options.map(([v,l]) => `<option value="${v}">${l}</option>`).join('');
          wrap.innerHTML = `<label>${def.label}</label>
            <select class="lv-dialog-select" id="_ndlgF_${def.id}">${opts}</select>`;
        } else if (def.type === 'pics') {
          wrap.innerHTML = `<label>${def.label}</label>`;
          const picContainer = document.createElement('div');
          if (!_pendingPics[def.picField]) _pendingPics[def.picField] = [];
          _renderPicArea(picContainer, _pendingPics[def.picField], def.max,
            urls => { _pendingPics[def.picField] = urls; });
          wrap.appendChild(picContainer);
        }
        fieldsWrap.appendChild(wrap);
      }
      // 自动聚焦标题
      const titleInput = fieldsWrap.querySelector('#_ndlgF_title');
      if (titleInput) setTimeout(() => titleInput.focus(), 0);
    }

    typeSelect.addEventListener('change', renderFields);
    renderFields();

    function done(val) { overlay.remove(); resolve(val); }

    overlay.querySelector('#_ndlgOk').addEventListener('click', () => {
      const type  = typeSelect.value;
      const defs  = _NODE_FIELDS[type] || [];
      const titleInput = fieldsWrap.querySelector('#_ndlgF_title');
      const title = titleInput?.value.trim();
      if (!title) { titleInput?.focus(); return; }

      const data = { nodeType: type, title };
      for (const def of defs) {
        if (def.type === 'text' || def.type === 'number') {
          const el = fieldsWrap.querySelector(`#_ndlgF_${def.id}`);
          if (el && el.value.trim()) data[def.id] = def.type === 'number' ? Number(el.value) : el.value.trim();
        } else if (def.type === 'select') {
          const el = fieldsWrap.querySelector(`#_ndlgF_${def.id}`);
          if (el && el.value) data[def.id] = el.value;
        } else if (def.type === 'pics') {
          const pics = _pendingPics[def.picField] || [];
          if (pics.length) data[def.picField] = pics;
        }
      }
      // 侧别：拼入标题后缀
      if (data.side) {
        data.title = data.title.replace(/[-_][LRM]$/i, '') + '-' + data.side;
        delete data.side;
      }
      done(data);
    });

    overlay.querySelector('#_ndlgCancel').addEventListener('click', () => done(null));
    overlay.addEventListener('keydown', e => {
      if (e.key === 'Escape') done(null);
      // Enter 只在输入框内按下时触发（防止图片操作中意外触发）
      if (e.key === 'Enter' && e.target.tagName === 'INPUT' && e.target.type !== 'file') {
        overlay.querySelector('#_ndlgOk').click();
      }
    });
    overlay.addEventListener('click', e => { if (e.target === overlay) done(null); });
  });
}

async function _createNodeFromDialog(action, refGid) {
  const refRow = refGid ? _rowByGid.get(refGid) : null;
  const data   = await _openNodeDialog(action, refGid);
  if (!data) return;

  const { nodeType, title, bom_row_id, seq_no, op_code, op_name, standard_time,
          description, process_flow_pic, process_chart_pic } = data;

  let parentGid, seqNo;
  if (action === 'add_above') {
    parentGid = refRow?.parent_gid || null;
    seqNo     = (refRow?.seq_no ?? 0) - 0.5;
  } else if (action === 'add_below') {
    parentGid = refRow?.parent_gid || null;
    seqNo     = (refRow?.seq_no ?? 0) + 0.5;
  } else if (action === 'add_child') {
    parentGid = refGid;
    seqNo     = seq_no ?? 0;
  } else {
    // add_new（工具栏）
    parentGid = _activeGid || null;
    seqNo     = seq_no ?? 0;
  }

  try {
    _toast('创建中…', 'ok', 600);

    // L4（process）和 L5（operation）走独立实体 API（一键模式）
    if (nodeType === 'process') {
      const body = {
        version_gid:      _versionGid,
        parent_entry_gid: parentGid,
        vpps_desc:        title,
        seq_no:           seqNo,
        op_code:          op_code || '',
        op_name:          op_name || '',
        standard_time:    standard_time ?? null,
        description:      description || '',
      };
      if (bom_row_id) body.vpps = bom_row_id;
      await _invokeCapability('craft.gbop.entity.change.apply', {
        operation: 'process.create',
        ...body,
      });
    } else if (nodeType === 'operation') {
      const body = {
        version_gid:      _versionGid,
        parent_entry_gid: parentGid,
        vpps_desc:        title,
        seq_no:           seqNo,
        op_code:          op_code || '',
        op_name:          op_name || '',
        standard_time:    standard_time ?? null,
        description:      description || '',
      };
      if (bom_row_id) body.vpps = bom_row_id;
      // 如果父节点是 process 类型的 entry，找到其关联的 process 实体 gid
      if (parentGid) {
        const parentRow = _rowByGid.get(parentGid);
        if (parentRow?.node_type === 'process' && parentRow.links?.length) {
          const procLink = parentRow.links.find(l => l.link_type === 'gbop_process' && l.is_primary);
          if (procLink) body.process_gid = procLink.ref_gid;
        }
      }
      await _invokeCapability('craft.gbop.entity.change.apply', {
        operation: 'operation.create',
        ...body,
      });
    } else {
      // 其他节点类型走通用 entry API
      const body = {
        version_gid: _versionGid,
        parent_gid:  parentGid,
        node_type:       nodeType,
        vpps_desc:       title,
        seq_no:          seqNo,
      };
      if (bom_row_id) body.vpps = bom_row_id;
      const resp = await _invokeCapability('craft.gbop.entity.change.apply', {
        operation: 'entry.create',
        ...body,
      });
      const newGid = resp?.data?.gid;
      // 上传图片（如有）
      if (newGid && (process_flow_pic?.length || process_chart_pic?.length)) {
        const picPatch = {};
        if (process_flow_pic?.length)  picPatch.process_flow_pic  = process_flow_pic;
        if (process_chart_pic?.length) picPatch.process_chart_pic = process_chart_pic;
        await _invokeCapability('craft.gbop.entity.change.apply', {
          operation: 'entry.update',
          gid: newGid,
          updates: picPatch,
        });
      }
    }

    await _reload();
    _toast('节点已创建', 'ok');
  } catch (e) {
    _toast('创建失败: ' + e.message, 'error');
  }
}

async function _handleFBtnAction(action, refGid) {
  await _createNodeFromDialog(action, refGid);
}

async function _deleteEntry(gid) {
  const row = _rowByGid.get(gid);
  if (!row) return;
  const ok = await _confirmDialog(`确认删除「${row.title || '(无名称)'}」？此操作不可恢复。`);
  if (!ok) return;
  try {
    await _invokeCapability('craft.gbop.entity.change.apply', {
      operation: 'entry.delete',
      gid,
    });
    if (_activeGid === gid) _activeGid = null;
    await _reload();
    _toast('已删除', 'ok');
  } catch (e) {
    _toast('删除失败: ' + e.message, 'error');
  }
}

// ── 详情浮动弹窗 ──────────────────────────────────────────────────────

let _detailGid = null;

function _openDetailPopover(gid, anchorEl) {
  const row = _rowByGid.get(gid);
  if (!row) return;
  _detailGid = gid;
  $dpTitle.textContent = `${row.title || '(无名称)'}`;
  const body = [];

  // ── 统计信息（原 stats popover 内容） ──
  const nt = row.node_type;
  const family = _getStatsFamily(nt);
  const desc = _getDescendantStats(gid);

  // 缩略图（process / operation 优先显示）
  if (family === 'process' || family === 'operation') {
    const picField = family === 'process' ? 'process_flow_pic' : 'process_chart_pic';
    const picVal = row[picField];
    const hasPic = picVal && (Array.isArray(picVal) ? picVal.length > 0 : true);
    if (hasPic) {
      const pics = Array.isArray(picVal) ? picVal : [picVal];
      const firstPic = typeof pics[0] === 'string' ? pics[0] : (pics[0]?.url || pics[0]?.src || '');
      if (firstPic) {
        body.push('<div class="lv-det-section">');
        body.push(`<div style="font-size:11px;font-weight:600;color:var(--subtext0,#a6adc8);margin-bottom:4px">${family === 'process' ? '工艺流程图' : '工艺卡图片'}</div>`);
        body.push(`<div style="text-align:center;padding:4px 0"><img src="${_escHtml(firstPic)}" style="max-width:100%;max-height:160px;object-fit:contain;border-radius:4px;cursor:pointer" onclick="window.open('${_escHtml(firstPic)}','_blank')" onerror="this.style.display='none'"></div>`);
        body.push('</div>');
      }
    }
  }

  const entries = Object.entries(desc).sort((a, b) => b[1] - a[1]);
  if (entries.length > 0 || family === 'leaf') {
    body.push('<div class="lv-det-section">');
    if (family === 'level') {
      const prio = _LEVEL_STATS_PRIORITY[nt] || STATS_PRIORITY;
      const byPrio = prio.filter(n => desc[n]).map(n => [n, desc[n]]);
      const others = Object.entries(desc).filter(([n]) => !prio.includes(n)).sort((a, b) => b[1] - a[1]);
      const sorted = [...byPrio, ...others];
      for (const [n, cnt] of sorted) {
        body.push(`<div class="lv-det-field"><label>${NT_LABEL[n] || n}</label><span class="lv-det-val"><b>${cnt}</b></span></div>`);
      }
    } else if (family === 'leaf') {
      body.push('<div style="font-size:12px;color:var(--overlay0,#6c7086);text-align:center;padding:4px 0">无后代节点</div>');
    } else {
      for (const [ntKey, cnt] of entries) {
        body.push(`<div class="lv-det-field"><label>${NT_LABEL[ntKey] || ntKey}</label><span class="lv-det-val"><b>${cnt}</b></span></div>`);
      }
    }
    body.push('</div>');
  }

  // ── 基本信息 ──
  body.push('<div class="lv-det-sep"></div>');
  body.push('<div class="lv-det-section">');
  const fields = [
    ['类型', NT_LABEL[row.node_type] || row.node_type || '—'],
    ['深度', _treeDepth(row)],
    ['零组件ID', row.bom_row_id || '—'],
    ['VPPS', row.vpps || '—'],
    ['状态', row.status || '—'],
  ];
  for (const [label, val] of fields) {
    body.push(`<div class="lv-det-field"><label>${label}</label><span class="lv-det-val">${val}</span></div>`);
  }
  body.push('</div>');

  // ── 编辑区 ──
  body.push('<div class="lv-det-sep"></div>');
  body.push('<div class="lv-det-section lv-det-edit-section">');
  body.push(`<div class="lv-det-field"><label>标题</label><input type="text" id="lvDpTitleInput" value="${_escHtml(row.title || '')}"></div>`);
  body.push(`<div class="lv-det-field"><label>VPPS</label><input type="text" id="lvDpVppsInput" value="${_escHtml(row.vpps || '')}"></div>`);
  body.push('</div>');

  // ── 子节点快速跳转（前 10 个） ──
  const children = _childMap.get(gid) || [];
  if (children.length > 0) {
    body.push('<div class="lv-det-sep"></div>');
    body.push('<div class="lv-det-section">');
    body.push(`<div style="font-size:11px;color:var(--subtext0,#a6adc8);margin-bottom:4px">子节点（${children.length}）</div>`);
    for (const child of children.slice(0, 10)) {
      const nt = child.node_type || 'part';
      body.push(`<div class="lv-det-clickable" data-gid="${child.gid}" style="display:flex;align-items:center;gap:4px;padding:2px 0;cursor:pointer;font-size:12px;color:var(--text,#cdd6f4)">`);
      body.push(`<span class="lv-type lv-nt-${nt}" style="font-size:9px;padding:0 3px">${NT_ABBR[nt] || nt}</span>`);
      body.push(`<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${child.title || '(无名称)'}</span>`);
      body.push('</div>');
    }
    body.push('</div>');
  }

  $dpBody.innerHTML = body.join('');

  // 子节点点击跳转
  $dpBody.querySelectorAll('.lv-det-clickable').forEach(el => {
    el.addEventListener('click', e => {
      const cgid = e.currentTarget.dataset.gid;
      if (cgid) {
        _closeDetailPopover();
        _applyActiveState(cgid);
      }
    });
  });

  // 定位：与统计 popover 相同，锚定在卡片统计框右侧
  const rect = anchorEl.getBoundingClientRect();
  $dpPopover.style.left = Math.min(rect.right + 6, window.innerWidth - 280) + 'px';
  $dpPopover.style.top  = rect.top + 'px';
  $dpPopover.style.display = 'block';
}

function _closeDetailPopover() {
  $dpPopover.style.display = 'none';
  _detailGid = null;
}

// ── 覆盖面板（方案A）─────────────────────────────────────────────────

let _opGid = null;
let _opPinned = false;

function _openOverlayPanel(gid) {
  const row = _rowByGid.get(gid);
  if (!row) return;
  _opGid = gid;
  // pin 状态由 pin 按钮独立控制，不影响面板内容刷新
  $opPin.classList.toggle('active', _opPinned);
  $opTitle.textContent = `${row.title || '(无名称)'}`;
  const body = [];

  // ── 统计信息 ──
  const nt = row.node_type;
  const family = _getStatsFamily(nt);
  const desc = _getDescendantStats(gid);

  // 图片区（process / operation 显示两行）
  if (family === 'process' || family === 'operation') {
    body.push(`<div class="lv-op-section lv-op-pics-section">
      <div class="lv-op-pics-label">工艺流程图</div>
      <div id="lvOpPicsContainerFlow"></div>
    </div>
    <div class="lv-op-section lv-op-pics-section lv-op-pics-section-2nd">
      <div class="lv-op-pics-label">工艺卡图片</div>
      <div id="lvOpPicsContainerChart"></div>
    </div>`);
    body.push('<div class="lv-op-sep"></div>');
  }

  const entries = Object.entries(desc).sort((a, b) => b[1] - a[1]);
  if (entries.length > 0 || family === 'leaf') {
    body.push('<div class="lv-op-section">');
    body.push('<div style="font-size:11px;font-weight:600;color:var(--subtext0,#a6adc8);margin-bottom:4px">后代统计</div>');
    if (family === 'level') {
      // 使用分族优先级排序
      const prio = _LEVEL_STATS_PRIORITY[nt] || STATS_PRIORITY;
      const byPrio = prio.filter(n => desc[n]).map(n => [n, desc[n]]);
      const others = Object.entries(desc).filter(([n]) => !prio.includes(n)).sort((a, b) => b[1] - a[1]);
      const sorted = [...byPrio, ...others];
      for (const [n, cnt] of sorted) {
        body.push(`<div class="lv-op-field"><label>${NT_LABEL[n] || n}</label><span class="lv-op-val"><b>${cnt}</b></span></div>`);
      }
    } else if (family === 'leaf') {
      body.push('<div style="font-size:12px;color:var(--overlay0,#6c7086);text-align:center;padding:4px 0">无后代节点</div>');
    } else {
      for (const [ntKey, cnt] of entries) {
        body.push(`<div class="lv-op-field"><label>${NT_LABEL[ntKey] || ntKey}</label><span class="lv-op-val"><b>${cnt}</b></span></div>`);
      }
    }
    body.push('</div>');
    body.push('<div class="lv-op-sep"></div>');
  }

  // ── 基本信息 ──
  body.push('<div class="lv-op-section">');
  body.push('<div style="font-size:11px;font-weight:600;color:var(--subtext0,#a6adc8);margin-bottom:4px">基本信息</div>');
  const fields = [
    ['类型', NT_LABEL[row.node_type] || row.node_type || '—'],
    ['深度', String(_treeDepth(row))],
    ['零组件ID', row.bom_row_id || '—'],
    ['VPPS', row.vpps || '—'],
    ['状态', row.status || '—'],
    ['版本名称', row.name || row.vpps_desc || '—'],
  ];
  for (const [label, val] of fields) {
    body.push(`<div class="lv-op-field"><label>${label}</label><span class="lv-op-val">${_escHtml(val)}</span></div>`);
  }
  body.push('</div>');

  // ── 编辑区 ──
  body.push('<div class="lv-op-sep"></div>');
  body.push('<div class="lv-op-section lv-op-edit-section">');
  body.push('<div style="font-size:11px;font-weight:600;color:var(--subtext0,#a6adc8);margin-bottom:6px">编辑</div>');
  body.push(`<div class="lv-op-field"><label>标题</label><input type="text" id="lvOpTitleInput" value="${_escHtml(row.title || '')}"></div>`);
  body.push(`<div class="lv-op-field"><label>VPPS</label><input type="text" id="lvOpVppsInput" value="${_escHtml(row.vpps || '')}"></div>`);
  body.push(`<div class="lv-op-field"><label>类型</label><select id="lvOpTypeSelect">`);
  // 所有可用类型
  const allTypes = [...new Set(_rows.map(r => r.node_type).filter(Boolean))].sort();
  for (const nt of allTypes) {
    const sel = nt === row.node_type ? ' selected' : '';
    body.push(`<option value="${nt}"${sel}>${NT_LABEL[nt] || nt}</option>`);
  }
  body.push('</select></div>');
  body.push(`<button class="lv-op-save-btn" id="lvOpSaveBtn">保存</button>`);
  body.push('</div>');

  // ── 子节点快速跳转 ──
  const children = _childMap.get(gid) || [];
  if (children.length > 0) {
    body.push('<div class="lv-op-sep"></div>');
    body.push('<div class="lv-op-section">');
    body.push(`<div style="font-size:11px;font-weight:600;color:var(--subtext0,#a6adc8);margin-bottom:4px">子节点（${children.length}）</div>`);
    for (const child of children) {
      const nt = child.node_type || 'part';
      body.push(`<div class="lv-op-child-item" data-gid="${child.gid}">`);
      body.push(`<span class="lv-type lv-nt-${nt}" style="font-size:9px;padding:0 3px">${NT_ABBR[nt] || nt}</span>`);
      body.push(`<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${_escHtml(child.title || '(无名称)')}</span>`);
      body.push('</div>');
    }
    body.push('</div>');
  }

  // ── 关联实体详情（process/operation）──
  const rowLinks = row.links || [];
  const primaryLink = rowLinks.find(l => l.is_primary);
  if (primaryLink && (primaryLink.link_type === 'gbop_process' || primaryLink.link_type === 'gbop_operation')) {
    body.push('<div class="lv-op-sep"></div>');
    body.push('<div class="lv-op-section" id="lvOpEntitySection">');
    body.push('<div style="font-size:11px;font-weight:600;color:var(--subtext0,#a6adc8);margin-bottom:4px">'
      + (primaryLink.link_type === 'gbop_process' ? '工艺卡片详情' : '操作卡片详情') + '</div>');
    body.push('<div style="font-size:12px;color:var(--overlay0,#6c7086);text-align:center;padding:8px 0" id="lvOpEntityLoading">加载中…</div>');
    body.push('</div>');
  } else if (rowLinks.length > 0) {
    body.push('<div class="lv-op-sep"></div>');
    body.push('<div class="lv-op-section">');
    body.push('<div style="font-size:11px;font-weight:600;color:var(--subtext0,#a6adc8);margin-bottom:4px">关联</div>');
    for (const lk of rowLinks) {
      body.push(`<div class="lv-op-field"><label>${lk.link_type}</label><span class="lv-op-val">${lk.ref_gid?.slice(-8) || '—'}</span></div>`);
    }
    body.push('</div>');
  } else {
    body.push('<div class="lv-op-sep"></div>');
    body.push('<div class="lv-op-section">');
    body.push('<div style="font-size:11px;font-weight:600;color:var(--subtext0,#a6adc8);margin-bottom:4px">关联</div>');
    body.push('<div class="lv-op-link-placeholder">无关联实体</div>');
    body.push('</div>');
  }

  $opBody.innerHTML = body.join('');

  // 图片管理区初始化（process / operation 两行）
  if (family === 'process' || family === 'operation') {
    const initPicSection = (containerId, picField) => {
      const picsContainer = document.getElementById(containerId);
      if (!picsContainer) return;
      const rawVal   = row[picField];
      const initUrls = Array.isArray(rawVal) ? rawVal.filter(u => typeof u === 'string')
        : (typeof rawVal === 'string' && rawVal ? [rawVal] : []);
      let currentUrls = [...initUrls];
      _renderPicArea(picsContainer, currentUrls, 3, async urls => {
        currentUrls = urls;
        try {
          await _invokeCapability('craft.gbop.entity.change.apply', {
            operation: 'entry.update',
            gid,
            updates: { [picField]: urls },
          });
          const r = _rowByGid.get(gid);
          if (r) r[picField] = urls;
          _toast('图片已保存', 'ok', 1200);
        } catch (e) {
          _toast('保存失败: ' + e.message, 'error');
        }
      });
    };
    initPicSection('lvOpPicsContainerFlow',  'process_flow_pic');
    initPicSection('lvOpPicsContainerChart', 'process_chart_pic');
  }

  // 子节点点击跳转
  $opBody.querySelectorAll('.lv-op-child-item').forEach(el => {
    el.addEventListener('click', e => {
      const cgid = e.currentTarget.dataset.gid;
      if (cgid) {
        _closeOverlayPanel();
        _applyActiveState(cgid);
      }
    });
  });

  // 保存按钮
  const saveBtn = document.getElementById('lvOpSaveBtn');
  if (saveBtn) {
    saveBtn.addEventListener('click', async () => {
      const titleEl = document.getElementById('lvOpTitleInput');
      const vppsEl  = document.getElementById('lvOpVppsInput');
      const typeEl  = document.getElementById('lvOpTypeSelect');
      const payload = {};
      if (titleEl) payload.vpps_desc = titleEl.value.trim();
      if (vppsEl)  payload.vpps  = vppsEl.value.trim();
      if (typeEl)  payload.node_type = typeEl.value;
      try {
        await _invokeCapability('craft.gbop.entity.change.apply', {
          operation: 'entry.update',
          gid,
          updates: payload,
        });
        _toast('保存成功', 'ok', 1500);
        await _reload();
      } catch (e) {
        _toast('保存失败: ' + e.message, 'error');
      }
    });
  }

  // 显示面板（先移除 hidden class）
  $opPanel.classList.remove('hidden');

  // ── 异步加载关联实体详情 ──
  if (primaryLink && (primaryLink.link_type === 'gbop_process' || primaryLink.link_type === 'gbop_operation')) {
    const entitySection = document.getElementById('lvOpEntitySection');
    const loadingEl = document.getElementById('lvOpEntityLoading');
    const isProc = primaryLink.link_type === 'gbop_process';
    // 尝试从版本列表加载（因为没有单个获取端点，从列表中查找）
    const catalogOperation = isProc ? 'processes.list' : 'operations.list';

    _invokeCapability('craft.gbop.catalog.read', {
      operation: catalogOperation,
      version_gid: _versionGid,
    }).then(resp => {
      if (_opGid !== gid) return; // 面板已切换
      const entities = resp?.items || resp?.data || [];
      const entity = entities.find(e => e.gid === primaryLink.ref_gid);
      if (!entity) {
        if (loadingEl) loadingEl.textContent = '关联实体未找到';
        return;
      }
      // 渲染实体字段
      const detailFields = [
        ['工序编码', entity.op_code],
        ['工序全称', entity.op_name],
        ['标准工时', entity.standard_time != null ? String(entity.standard_time) : null],
        ['描述', entity.description],
        ['重要度', entity.importance],
        ['扭矩重要度', entity.torque_importance],
        ['状态', entity.status],
      ].filter(([, v]) => v != null && v !== '');

      let html = '';
      for (const [label, val] of detailFields) {
        html += `<div class="lv-op-field"><label>${label}</label><span class="lv-op-val">${_escHtml(val)}</span></div>`;
      }
      // steps
      if (entity.steps && Array.isArray(entity.steps) && entity.steps.length > 0) {
        html += `<div class="lv-op-field"><label>工步 (${entity.steps.length})</label><span class="lv-op-val">${entity.steps.map((s, i) => `${i+1}. ${_escHtml(typeof s === 'string' ? s : (s.name || s.desc || JSON.stringify(s)))}`).join('<br>')}</span></div>`;
      }
      // required_tools
      if (entity.required_tools && Array.isArray(entity.required_tools) && entity.required_tools.length > 0) {
        html += `<div class="lv-op-field"><label>所需工具 (${entity.required_tools.length})</label><span class="lv-op-val">${entity.required_tools.map(t => _escHtml(typeof t === 'string' ? t : (t.name || JSON.stringify(t)))).join(', ')}</span></div>`;
      }

      // 编辑按钮
      const entityGid = entity.gid;
      html += `<button class="lv-op-save-btn" id="lvOpEntityEditBtn" style="margin-top:6px">编辑实体详情</button>`;

      if (entitySection) {
        // 保留标题，替换 loading
        if (loadingEl) loadingEl.remove();
        const detailDiv = document.createElement('div');
        detailDiv.innerHTML = html;
        entitySection.appendChild(detailDiv);

        // 编辑按钮 → 弹出编辑 overlay
        const editBtn = document.getElementById('lvOpEntityEditBtn');
        if (editBtn) {
          editBtn.addEventListener('click', () => _openEntityEditDialog(entity, isProc));
        }
      }
    }).catch(err => {
      if (loadingEl) loadingEl.textContent = '加载失败: ' + err.message;
    });
  }
}

function _closeOverlayPanel() {
  if (_opPinned) return; // pin 住时禁止关闭
  $opPanel.classList.add('hidden');
  _opGid = null;
}

/**
 * 弹出编辑实体详情的 overlay 对话框（process / operation）
 */
async function _openEntityEditDialog(entity, isProcess) {
  const fieldDefs = [
    { id: 'op_code',           label: isProcess ? '工序编码' : '操作编码', type: 'text' },
    { id: 'op_name',           label: isProcess ? '工序全称' : '操作全称', type: 'text' },
    { id: 'standard_time',     label: '标准工时', type: 'number' },
    { id: 'description',       label: '描述',     type: 'text' },
    { id: 'importance',        label: '重要度',   type: 'text' },
    { id: 'torque_importance', label: '扭矩重要度', type: 'text' },
  ];

  return new Promise(resolve => {
    const overlay = document.createElement('div');
    overlay.className = 'lv-dialog-overlay';
    let fieldsHtml = '';
    for (const def of fieldDefs) {
      const val = entity[def.id] ?? '';
      fieldsHtml += `<div class="lv-ndlg-field">
        <label>${def.label}</label>
        <input class="lv-dialog-input" id="_entityF_${def.id}" type="${def.type}" value="${_escHtml(String(val))}">
      </div>`;
    }
    overlay.innerHTML = `<div class="lv-dialog-box lv-ndlg-box">
      <div class="lv-ndlg-hdr">
        <span class="lv-ndlg-hdr-title">编辑${isProcess ? '工艺' : '操作'}卡片</span>
      </div>
      <div class="lv-ndlg-fields">${fieldsHtml}</div>
      <div class="lv-dialog-btns">
        <button class="lv-btn lv-btn-sm" id="_entityCancel">取消</button>
        <button class="lv-btn lv-btn-sm" id="_entityOk"
          style="border-color:var(--blue,#89b4fa);color:var(--blue,#89b4fa)">保存</button>
      </div>
    </div>`;
    document.body.appendChild(overlay);

    function done(val) { overlay.remove(); resolve(val); }

    overlay.querySelector('#_entityOk').addEventListener('click', async () => {
      const payload = {};
      for (const def of fieldDefs) {
        const el = overlay.querySelector(`#_entityF_${def.id}`);
        if (!el) continue;
        const raw = el.value.trim();
        if (def.type === 'number') {
          if (raw !== '') payload[def.id] = Number(raw);
        } else {
          payload[def.id] = raw;
        }
      }
      try {
        await _invokeCapability('craft.gbop.entity.change.apply', {
          operation: isProcess ? 'process.update' : 'operation.update',
          gid: entity.gid,
          updates: payload,
        });
        _toast('实体已保存', 'ok', 1500);
        // 刷新 overlay panel
        if (_opGid) _openOverlayPanel(_opGid);
        done(true);
      } catch (e) {
        _toast('保存失败: ' + e.message, 'error');
        done(false);
      }
    });

    overlay.querySelector('#_entityCancel').addEventListener('click', () => done(null));
    overlay.addEventListener('keydown', e => {
      if (e.key === 'Escape') done(null);
      if (e.key === 'Enter' && e.ctrlKey) overlay.querySelector('#_entityOk').click();
    });
    overlay.addEventListener('click', e => { if (e.target === overlay) done(null); });
  });
}

// _escHtml, _openImageLightbox 已提取至 web/shared/lv_utils.js

let _ctxGid = null;

function _showCtxMenu(x, y, gid) {
  _ctxGid = gid;
  $ctxMenu.style.left = x + 'px';
  $ctxMenu.style.top  = y + 'px';
  $ctxMenu.style.display = 'block';
}
function _hideCtxMenu() {
  $ctxMenu.style.display = 'none';
  _ctxGid = null;
}

// ── 工具栏 — 类型筛选下拉 ─────────────────────────────────────────

function _buildTypeDropdown() {
  $typeDD.innerHTML = '';
  const allTypes = [...new Set(_rows.map(r => r.node_type).filter(Boolean))];

  const isAll = _typeFilter === null;

  // 全部
  const allItem = document.createElement('label');
  allItem.className = 'lv-dd-item';
  const allCb = document.createElement('input');
  allCb.type = 'checkbox';
  allCb.checked = isAll;
  allCb.dataset.allTypes = '1';
  const allDot = document.createElement('span');
  allDot.className = 'lv-nt-dot';
  allDot.style.background = '#a6adc8';
  allItem.appendChild(allCb);
  allItem.appendChild(allDot);
  allItem.appendChild(document.createTextNode('全部'));
  $typeDD.appendChild(allItem);

  // 全不选
  const noneItem = document.createElement('label');
  noneItem.className = 'lv-dd-item';
  const noneCb = document.createElement('input');
  noneCb.type = 'checkbox';
  noneCb.checked = false;
  noneCb.dataset.noneTypes = '1';
  const noneDot = document.createElement('span');
  noneDot.className = 'lv-nt-dot';
  noneDot.style.background = '#585b70';
  noneItem.appendChild(noneCb);
  noneItem.appendChild(noneDot);
  noneItem.appendChild(document.createTextNode('全不选'));
  $typeDD.appendChild(noneItem);

  for (const nt of allTypes) {
    const item = document.createElement('label');
    item.className = 'lv-dd-item';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.value = nt;
    cb.checked = isAll || (_typeFilter && _typeFilter.includes(nt));
    const dot = document.createElement('span');
    dot.className = `lv-nt-dot lv-nt-${nt}`;
    dot.style.cssText = _getDotStyle(nt);
    item.appendChild(cb);
    item.appendChild(dot);
    item.appendChild(document.createTextNode(NT_LABEL[nt] || nt));
    $typeDD.appendChild(item);
  }

  const _recalc = () => {
    const checked = [...$typeDD.querySelectorAll('input[type=checkbox]:not([data-all-types]):not([data-none-types])')]
      .filter(c => c.checked).map(c => c.value);
    if (checked.length === allTypes.length) {
      _typeFilter = null; // 全选 = 全部显示
    } else {
      _typeFilter = checked;
    }
    allCb.checked = _typeFilter === null;
    noneCb.checked = _typeFilter !== null && _typeFilter.length === 0;
    _applyFilters();
  };

  $typeDD.querySelectorAll('input[type=checkbox]:not([data-all-types]):not([data-none-types])').forEach(cb => {
    cb.addEventListener('change', _recalc);
  });

  allCb.addEventListener('change', () => {
    if (allCb.checked) {
      _typeFilter = null;
      $typeDD.querySelectorAll('input[type=checkbox]:not([data-all-types]):not([data-none-types])').forEach(c => { c.checked = true; });
      noneCb.checked = false;
      _applyFilters();
    }
  });

  noneCb.addEventListener('change', () => {
    if (noneCb.checked) {
      _typeFilter = [];
      $typeDD.querySelectorAll('input[type=checkbox]:not([data-all-types]):not([data-none-types])').forEach(c => { c.checked = false; });
      allCb.checked = false;
      _applyFilters();
    }
  });
}

function _getDotStyle(nt) {
  const colors = {
    factory_bop:'#6c8ebf', line_process:'#82b366', station_process:'#d6a520',
    station_ref:'#b8932a', operation:'#ae4132', step:'#e07a5f',
    role_req:'#9b59b6', role_ref:'#7d3a9e', equipment_req:'#1abc9c',
    equipment_ref:'#138a72', tooling_req:'#e67e22', tooling_ref:'#c46a1a',
    tool_req:'#f39c12', tool_ref:'#c87f0a', part:'#7f8c8d',
    std_fastener:'#95a5a6', test_case:'#2980b9',
  };
  return `background:${colors[nt] || '#888'}`;
}

// ── 保存/恢复视图 ────────────────────────────────────────────────────

function _lsKey() { return _lsk(`lv:view:${_versionGid}`); }
function _isCloud() {
  return (window.parent?._authMode || window._authMode || 'local') === 'feishu';
}
async function _saveView() {
  const view = {
    typeFilter:    _typeFilter,
    maxDepth:      _maxDepth,
    collapsed:     [..._collapsed],
    selectedRoots: [..._selectedRoots],
    level1Filter:  _level1Filter === null ? null : [..._level1Filter],
    zoomPct:       _zoomPct,
  };
  // 始终写本地
  localStorage.setItem(_lsKey(), JSON.stringify(view));

  // 云端共享（飞书模式）
  if (!_isCloud() || !_versionGid) {
    _toast('视图已保存（本地）', 'ok', 1500);
    return;
  }
  try {
    await _invokeCapability('craft.bop.version.layout.change.apply', {
      version_gid: _versionGid,
      config: { lineage_view: view },
    });
    _toast('视图已同步到云端', 'ok', 2000);
  } catch {
    _toast('云端保存失败，已保存到本地', 'warn', 2500);
  }
}

/**
 * 异步从云端加载共享布局配置，并覆盖本地状态
 * - 仅在飞书模式下生效
 * - 成功后将云端数据同步回 localStorage（本地缓存）
 */
async function _loadCloudConfig() {
  if (!_isCloud() || !_versionGid) return;
  try {
    const res = await _invokeCapability('craft.bop.version.legacy_read', {
      operation: 'layout_config', version_gid: _versionGid,
    });
    const cloudCfg = res?.config || res?.data?.config;
    if (!cloudCfg) return;

    // 将云端视图设置同步写回 localStorage（下次打开可立即生效）
    const view = cloudCfg.lineage_view;
    if (view) {
      const local = JSON.parse(localStorage.getItem(_lsKey()) || '{}');
      localStorage.setItem(_lsKey(), JSON.stringify({ ...local, ...view }));
    }
  } catch { /* 网络失败静默忽略，本地数据继续使用 */ }
}

function _restoreView() {
  try {
    const raw = localStorage.getItem(_lsKey());
    if (!raw) return;
    const view = JSON.parse(raw);
    // 兼容旧数据：旧版 typeFilter=[] 表示"全部显示"，新版 [] 表示"全不选"
    // 旧数据 []、undefined、null 统一转 null（全部显示）
    const rawTF = view.typeFilter;
    _typeFilter = (Array.isArray(rawTF) && rawTF.length > 0) ? rawTF : null;
    _maxDepth   = view.maxDepth ?? 3;
    $maxDepth.value = String(_maxDepth);
    _collapsed  = new Set(view.collapsed || []);
    // 同理兼容旧版 level1Filter
    const rawL1 = view.level1Filter;
    _level1Filter = (Array.isArray(rawL1) && rawL1.length > 0) ? new Set(rawL1) : null;
    if (view.selectedRoots?.length) {
      _selectedRoots = new Set(view.selectedRoots);
    }
    if (view.zoomPct) {
      _zoomPct = view.zoomPct;
      $zoomRange.value = _zoomPct;
      $zoomPct.textContent = _zoomPct + '%';
    }
  } catch { /* ignore */ }
}

// ── 统计 Popover ──────────────────────────────────────────────────────

function _showStatsPopover(gid, anchorEl) {
  const desc = _getDescendantStats(gid);
  const entries = Object.entries(desc).sort((a, b) => b[1] - a[1]);

  if (entries.length === 0) return;

  const row = _rowByGid.get(gid);
  let html = `<h4>${row?.title || '统计'} — 全量后代</h4>`;
  for (const [nt, cnt] of entries) {
    html += `<div class="lv-pop-row"><span>${NT_LABEL[nt] || nt}</span><b>${cnt}</b></div>`;
  }
  $popover.innerHTML = html;

  const rect = anchorEl.getBoundingClientRect();
  $popover.style.left = Math.min(rect.right + 6, window.innerWidth - 180) + 'px';
  $popover.style.top  = rect.top + 'px';
  $popover.style.display = 'block';
}

function _hideStatsPopover() {
  $popover.style.display = 'none';
}

// ── reload helper ─────────────────────────────────────────────────────

async function _reload() {
  _closeOverlayPanel(); // 刷新时关闭覆盖面板
  try {
    let allRows = [];
    for (const vGid of _loadedVersionGids) {
      const json = await _invokeCapability('craft.gbop.catalog.read', {
        operation: 'entries.list',
        version_gid: vGid,
      });
      allRows = allRows.concat(_flattenMeta(json?.items || json?.data || []));
    }
    _rows = allRows;
    _buildIndexes(_rows);
    _buildStats();
    await _render();
    if (_dnt) _dnt.setData(_rows);
    if (_activeGid) {
      _applyActiveState(_activeGid);
    }
  } catch (e) {
    _toast('刷新失败: ' + e.message, 'error');
  }
}

// ── 事件绑定 ─────────────────────────────────────────────────────────

function _bindEvents() {

  // ── 列区域事件委托 ──
  $columns.addEventListener('click', e => {
    const card = e.target.closest('.lv-card');
    if (!card) return;
    if (e.target.closest('.lv-fbtn')) return;
    if (e.target.closest('.lv-stats-box')) return;
    const gid = card.dataset.gid;
    _applyActiveState(gid);
    _hideCtxMenu();
    _closeDetailPopover();
    // pin 住时更新覆盖面板内容，不关闭；未 pin 时关闭
    if (_opPinned) {
      _openOverlayPanel(gid);
    } else {
      _closeOverlayPanel();
    }
  });

  $columns.addEventListener('dblclick', e => {
    if (e.target.closest('.lv-stats-box') || e.target.closest('.lv-fbtn')) return;
    const card = e.target.closest('.lv-card');
    if (card) _openOverlayPanel(card.dataset.gid);
  });

  $columns.addEventListener('contextmenu', e => {
    const card = e.target.closest('.lv-card');
    if (!card) return;
    e.preventDefault();
    _showCtxMenu(e.clientX, e.clientY, card.dataset.gid);
  });

  $columns.addEventListener('click', e => {
    const box = e.target.closest('.lv-stats-box');
    if (!box) return;
    e.stopPropagation();
    const gid = box.dataset.statsGid;
    const thumbEl = box.querySelector('.lv-stats-thumb-fill');
    if (thumbEl) {
      // 有缩略图 → 灯箱预览，取该行所有图片
      const row = _rowByGid.get(gid);
      const pics = [];
      for (const field of ['process_flow_pic', 'process_chart_pic']) {
        const val = row?.[field];
        if (Array.isArray(val)) val.forEach(p => { const s = typeof p === 'string' ? p : (p?.url || p?.src || ''); if (s) pics.push(s); });
        else if (typeof val === 'string' && val) pics.push(val);
      }
      if (pics.length) _openImageLightbox(pics);
    } else {
      if ($dpPopover.style.display !== 'none' && _detailGid === gid) {
        _closeDetailPopover();
      } else {
        _openDetailPopover(gid, box);
      }
    }
  });

  // ── 右键菜单 ──
  $ctxMenu.addEventListener('click', e => {
    const item = e.target.closest('.lv-ctx-item');
    if (!item || !_ctxGid) return;
    const action = item.dataset.action;
    const gid    = _ctxGid;
    _hideCtxMenu();
    if (action === 'rename') {
      const card = document.querySelector(`.lv-card[data-gid="${gid}"]`);
      if (card) _startInlineRename(card);
    } else if (action === 'add_child') {
      _handleFBtnAction('add_child', gid);
    } else if (action === 'delete') {
      _deleteEntry(gid);
    } else if (action === 'open_detail') {
      const row = _rowByGid.get(gid);
      if (row) {
        window.top.postMessage({
          type: 'tab:open',
          id: 'container_card',
          params: { mode: 'row_detail', item_type: 'bop_entry', gid, source: 'cloud' },
        }, '*');
      }
    } else if (action === 'detail_modal') {
      _openOverlayPanel(gid);
    }
  });

  // 点外侧关闭菜单和 popover
  document.addEventListener('click', e => {
    if (!$ctxMenu.contains(e.target)) _hideCtxMenu();
    if (!$dpPopover.contains(e.target) && !e.target.closest('.lv-stats-box')) _closeDetailPopover();
    if (!$typeDD.contains(e.target) && !$typeBtn.contains(e.target)) {
      $typeDD.style.display = 'none';
    }
    if (!$l1DD.contains(e.target) && !$l1Btn.contains(e.target)) {
      $l1DD.style.display = 'none';
    }
    // 点击列区域（不在覆盖面板内）→ 关闭覆盖面板
    if ($columns.contains(e.target) && !e.target.closest('.lv-overlay-panel')) {
      if (_opPinned) {
        // pin 住时：如果点击的是卡片，更新面板内容
        const card = e.target.closest('.lv-card');
        if (card && card.dataset.gid && card.dataset.gid !== _opGid) {
          _openOverlayPanel(card.dataset.gid);
        }
      } else {
        _closeOverlayPanel();
      }
    }
  });

  // ── 覆盖面板关闭 ──
  $opClose.addEventListener('click', () => {
    _opPinned = false;
    _closeOverlayPanel();
  });

  // ── 覆盖面板 pin 按钮 ──
  $opPin.addEventListener('click', () => {
    _opPinned = !_opPinned;
    $opPin.classList.toggle('active', _opPinned);
  });

  // ── 覆盖面板内联边栏切换 ──
  $opSbToggle.addEventListener('click', () => {
    _toggleSidebar();
  });

  // ── 工具栏 ──
  document.getElementById('lvAddNode').addEventListener('click', () => {
    _createNodeFromDialog('add_new', null);
  });

  document.getElementById('lvExpandAll').addEventListener('click', () => {    _collapsed.clear();
    _render();
    _toast('已展开全部', 'ok', 1200);
  });

  document.getElementById('lvCollapseAll').addEventListener('click', () => {
    for (const r of _rows) {
      if ((_childMap.get(r.gid) || []).length > 0) _collapsed.add(r.gid);
    }
    _render();
    _toast('已折叠全部', 'ok', 1200);
  });

  document.getElementById('lvSaveView').addEventListener('click', _saveView);

  document.getElementById('lvRefresh').addEventListener('click', _reload);

  // 跳转到清单视图页面
  document.getElementById('lvGoList')?.addEventListener('click', () => {
    window.top.postMessage({ type: 'tab:open', id: 'gbop' }, '*');
  });

  document.getElementById('lvThemeToggle').addEventListener('click', () => {
    _lvTheme = _lvTheme === 'light' ? 'dark' : 'light';
    localStorage.setItem(_lsk('lv:theme'), _lvTheme);
    _applyLvTheme();
  });

  // ── 缩放滑块 ──
  $zoomRange.addEventListener('input', () => {
    _zoomPct = parseInt($zoomRange.value);
    $zoomPct.textContent = _zoomPct + '%';
    document.documentElement.style.setProperty('--lv-scale', _zoomPct / 100);
  });

  // ── 边栏切换 ──
  $sbToggle.addEventListener('click', _toggleSidebar);

  // ── 边栏页签 ──
  $sbTabs.addEventListener('click', e => {
    const tab = e.target.closest('.lv-sb-tab');
    if (tab) _switchSbTab(tab.dataset.tab);
  });

  $typeBtn.addEventListener('click', e => {
    e.stopPropagation();
    const shown = $typeDD.style.display !== 'none';
    $typeDD.style.display = shown ? 'none' : 'block';
    if (!shown) _buildTypeDropdown();
  });

  // ── 第1级（线体）筛选 ──
  $l1Btn.addEventListener('click', e => {
    e.stopPropagation();
    const shown = $l1DD.style.display !== 'none';
    $l1DD.style.display = shown ? 'none' : 'block';
    if (!shown) _buildLevel1Dropdown();
  });

  $maxDepth.addEventListener('change', () => {
    _maxDepth = parseInt($maxDepth.value) || 3;
    _render();
  });

  // ⚡ 搜索 debounce
  let _searchTimer = null;
  $search.addEventListener('input', () => {
    clearTimeout(_searchTimer);
    _searchTimer = setTimeout(() => {
      _searchText = $search.value.trim();
      _applyFilters();
    }, 150);
});

  // ── 拖拽 ──
  $columns.addEventListener('dragstart', e => {
    const card = e.target.closest('.lv-card');
    if (!card) return;
    _dragGid = card.dataset.gid;
    card.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', _dragGid);
  });

  $columns.addEventListener('dragend', () => {
    document.querySelectorAll('.lv-card.dragging').forEach(el => el.classList.remove('dragging'));
    _clearDropClasses();
    _dragGid = null;
  });

  $columns.addEventListener('dragover', e => {
    if (!_dragGid) return;
    const card = e.target.closest('.lv-card');
    if (!card || card.dataset.gid === _dragGid) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    _clearDropClasses();
    const pos = _getDropPosition(e, card);
    if (pos === 'up')    card.classList.add('drop-above');
    if (pos === 'down')  card.classList.add('drop-below');
    if (pos === 'right') card.classList.add('drop-under');
  });

  $columns.addEventListener('dragleave', e => {
    if (!e.target.closest('.lv-card')) _clearDropClasses();
  });

  $columns.addEventListener('drop', async e => {
    e.preventDefault();
    _clearDropClasses();
    if (!_dragGid) return;
    const card = e.target.closest('.lv-card');
    if (!card || card.dataset.gid === _dragGid) return;

    const targetGid = card.dataset.gid;
    const targetRow = _rowByGid.get(targetGid);
    const dragRow   = _rowByGid.get(_dragGid);
    if (!targetRow || !dragRow) return;

    const pos = _getDropPosition(e, card);
    if (!pos) return;

    let patchBody;
    if (pos === 'up') {
      patchBody = { parent_gid: targetRow.parent_gid, seq_no: (targetRow.seq_no ?? 0) - 0.5 };
    } else if (pos === 'down') {
      patchBody = { parent_gid: targetRow.parent_gid, seq_no: (targetRow.seq_no ?? 0) + 0.5 };
    } else {
      patchBody = { parent_gid: targetGid, seq_no: 0 };
    }

    try {
      await _patchEntry(_dragGid, patchBody);
      await _reload();
      _toast('移动成功', 'ok');
    } catch (ex) {
      _toast('移动失败: ' + ex.message, 'error');
    }
    _dragGid = null;
  });
}

// ── 初始化 ────────────────────────────────────────────────────────────
let _popoverGid = null;

async function init() {
  // 初始化 MillerCentering
  _miller = new MillerCentering({
    scrollContainer: $wrap,
    getColByLevel:   (lv) => document.querySelector(`.lv-col[data-level="${lv}"]`),
    getCardByGid:    (gid) => document.querySelector(`.lv-card[data-gid="${gid}"]`),
    childMap:        _childMap,
    rowByGid:        _rowByGid,
    depthByGid:      _depthByGid,
  });

  // 恢复视图设置
  _restoreView();
  $maxDepth.value = String(_maxDepth);

  // 应用本地亮/暗主题
  _applyLvTheme();

  // 应用缩放值
  $zoomRange.value = _zoomPct;
  $zoomPct.textContent = _zoomPct + '%';
  document.documentElement.style.setProperty('--lv-scale', _zoomPct / 100);

  // 初始化边栏宽度 CSS 变量
  document.documentElement.style.setProperty('--sb-width', _sidebarOpen ? '320px' : '0px');

  // 绑定事件
  _bindEvents();

  // 加载版本列表到下拉选择器（可能自动选中第一个版本）
  await _loadVersionSelect();

  // 更新标题（_loadVersionSelect 可能已更新 _versionTag）
  $versionLbl.textContent = `GBOP 树形视图${_versionTag ? ' — ' + _versionTag : ''}`;

  // 加载数据
  await _load();
}

// 主题同步（从父窗口继承）
(function _syncTheme() {
  const parentTheme = window.parent?.document?.documentElement?.dataset?.theme;
  if (parentTheme) document.documentElement.dataset.theme = parentTheme;
  window.addEventListener('message', e => {
    if (e.data?.type === 'theme-change') {
      document.documentElement.dataset.theme = e.data.theme;
    }
  });
})();

document.addEventListener('DOMContentLoaded', init);
