'use strict';
/**
 * bop_nav.js — 车型工序导航卡
 *
 * 使用 lineage_view 的 Miller Columns 风格渲染 PBOM × GBOP 匹配关系。
 *
 * 视图结构：
 *   列1 — PBOM 零件（按匹配状态过滤）
 *   列2 — 该零件的 GBOP 匹配操作（点击零件卡后展开）
 *   右侧面板 — 操作选择（radio=主操作，checkbox=附加操作）+ 跳过/确认
 *
 * 数据来源：GET /api/bop/pbom-versions/{gid}/gbop-match-preview
 */

function _cf(method, path, opts = {}) {
  const fn = window.top?._cloudFetch || window.parent?._cloudFetch || window._cloudFetch;
  if (!fn) throw new Error('cloudFetch not available');
  return fn(path, { ...opts, method });
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
function _lsk(base) {
  try { const u = window.parent?._authUser || window.top?._authUser || window._authUser; const g = u?.gid || u?.user_gid || ''; return g ? `${g}:${base}` : base; } catch { return base; }
}

// ── DOM refs ─────────────────────────────────────────────────────
const $columns  = document.getElementById('bnColumns');
const $wrap     = document.getElementById('bnColumnsWrap');
const $toast    = document.getElementById('bnToast');
const $panel    = document.getElementById('bnPanel');
const $panelBody  = document.getElementById('bnPanelBody');
const $panelTitle = document.getElementById('bnPanelTitle');
const $verBtn   = document.getElementById('bnVerBtn');
const $verLabel = document.getElementById('bnVerLabel');
const $verMenu  = document.getElementById('bnVerMenu');
const $submit   = document.getElementById('bnSubmit');
const $search   = document.getElementById('bnSearch');
const $sidebar  = document.getElementById('bnSidebar');
const $sbToggle = document.getElementById('bnSbToggle');

// ── 状态 ─────────────────────────────────────────────────────────
let _projects      = [];
let _pbomByProject = new Map();    // projectGid → [{gid, title, status}]
let _expanded      = new Set();
let _currentGid    = null;         // 当前选中的 PBOM 版本 gid
let _previewData   = [];           // preview rows（flat）
let _rows          = [];           // 展开后的 flat rows（parts + virtual op rows）
let _rowByGid      = new Map();
let _childMap      = new Map();    // parent_gid|null → children[]

// standalone 模式：从 URL 参数获取关联 BOP 版本 GID，用于提交后写回统计
const _urlP = new URLSearchParams(location.search);
const _bopVersionGid = _urlP.get('bop_version_gid') || '';
let _activePartGid        = null;   // 当前选中零件 gid
let _activePartProcessGid = null;  // 零件视图：当前选中的工序 gid
let _filter        = 'all';
let _searchText    = '';
let _pendingChanges = new Map();   // pbom_entry_gid → {action, gbop_entry_gid, extra_entry_gids}
let _assocPanel = null;
let _miller        = null;
let _theme         = localStorage.getItem(_lsk('bn:theme')) || 'dark';

// ── 工序视图状态 ───────────────────────────────────────────────────
let _viewMode          = 'part';          // 'part' | 'process'
let _processHierarchy  = [];              // [{process_entry_gid, title, operations:[{entry_gid, title, parts:[]}]}]
let _activeProcessGid  = null;
let _activeOpGid       = null;

// ── 零件视图5级状态 ────────────────────────────────────────────────
let _activeSystemGid   = null;
let _activeAssemblyGid = null;

// ── 状态标签/样式映射 ─────────────────────────────────────────────
const _ST_LABEL = {
  unmatched:'未匹配', matched_1:'已匹配', matched:'已匹配',
  matched_n:'多匹配', multi:'多匹配',    skipped:'已跳过',
  confirmed:'已确认', pending:'待处理',
};
const _ST_CLS = {
  unmatched:'bn-st-u', matched_1:'bn-st-ok', matched:'bn-st-ok',
  matched_n:'bn-st-m', multi:'bn-st-m',      skipped:'bn-st-s',
  confirmed:'bn-st-c', pending:'bn-st-p',
};

// ── Toast ─────────────────────────────────────────────────────────
let _toastTmr = null;
function _toast(msg, type = 'ok', dur = 2500) {
  $toast.textContent = msg;
  $toast.className = `lv-toast ${type}`;
  $toast.style.display = 'block';
  clearTimeout(_toastTmr);
  _toastTmr = setTimeout(() => { $toast.style.display = 'none'; }, dur);
}

function _esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── 状态计算 ──────────────────────────────────────────────────────
function _effectiveSt(partGid) {
  const p = _pendingChanges.get(partGid);
  if (p) return p.action === 'skip' ? 'skipped' : 'confirmed';
  const r = _rowByGid.get(partGid);
  return r?.confirmed_status || r?.match_status || 'pending';
}

// ── 构建行树 ──────────────────────────────────────────────────────
function _buildRows() {
  _rows = [];
  // Collect all PBOM gids to validate parent references
  const allPbomGids = new Set(_previewData.map(p => p.pbom_entry_gid));
  for (let i = 0; i < _previewData.length; i++) {
    const p = _previewData[i];
    // Use real parent_gid only if parent exists in this dataset
    const realParent = (p.parent_gid && allPbomGids.has(p.parent_gid)) ? p.parent_gid : null;
    _rows.push({
      gid:              p.pbom_entry_gid,
      parent_gid:       realParent,
      node_type:        'pbom_part',
      title:            p.part_title || p.vpps || p.pbom_entry_gid,
      vpps:             p.vpps,
      part_number:      p.part_number,
      level:            p.level ?? 0,
      match_status:     p.match_status,
      confirmed_status: p.confirmed_status,
      gbop_matches:     p.gbop_matches || [],
      sort_order:       i,
      _is_part:         true,
    });
    (p.gbop_matches || []).forEach((op, j) => {
      _rows.push({
        gid:              `${p.pbom_entry_gid}__${op.entry_gid}`,
        parent_gid:       p.pbom_entry_gid,
        node_type:        op.node_type || 'operation',
        title:            op.title || op.entry_gid,
        _op_entry_gid:    op.entry_gid,
        _part_entry_gid:  p.pbom_entry_gid,
        _is_primary_feed: !!op.is_primary_feed,
        _is_op:           true,
        sort_order:       j,
      });
    });
  }
}

function _buildIndexes() {
  _rowByGid.clear();
  _childMap.clear();
  for (const r of _rows) _rowByGid.set(r.gid, r);
  for (const r of _rows) {
    const pk = r.parent_gid || null;
    if (!_childMap.has(pk)) _childMap.set(pk, []);
    _childMap.get(pk).push(r);
  }
  for (const [, arr] of _childMap) arr.sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));
}

// ── 加载数据 ──────────────────────────────────────────────────────
async function _load(pbomGid) {
  if (!pbomGid) return;
  $columns.innerHTML = '<div class="lv-loading"><div class="lv-spinner"></div>加载中…</div>';
  _closePanel();
  _activePartGid = null;
  _activePartProcessGid = null;
  _activeSystemGid = null;
  _activeAssemblyGid = null;
  try {
    const [data] = await Promise.all([
      _invokeCapability('craft.bop.gbop.legacy_read', {
        operation: 'match_preview',
        pbom_gid: pbomGid,
      }),
      _checkAutoLinkState(pbomGid),
      _loadProcessHierarchySilent(pbomGid),
    ]);
    _previewData = data?.data || [];
    _pendingChanges.clear();
    _buildRows();
    _buildIndexes();
    _autoExpand();
    _render();
    _updateSubmit();
  } catch (e) {
    $columns.innerHTML = `<div class="lv-empty">加载失败：${_esc(e.message)}</div>`;
    _toast('加载失败: ' + e.message, 'error');
  }
}

// ── 过滤逻辑 ─────────────────────────────────────────────────────
function _partVisible(row) {
  const st = _effectiveSt(row.gid);
  const q = _searchText.trim().toLowerCase();
  if (q) {
    const txt = `${row.vpps || ''} ${row.title || ''} ${row.part_number || ''}`.toLowerCase();
    if (!txt.includes(q)) return false;
  }
  if (_filter === 'all')       return true;
  if (_filter === 'unmatched') return st === 'unmatched';
  if (_filter === 'matched')   return ['matched_1','matched','confirmed'].includes(st);
  if (_filter === 'multi')     return ['matched_n','multi'].includes(st);
  if (_filter === 'skipped')   return st === 'skipped';
  if (_filter === 'pending')   return !['confirmed','skipped','unmatched'].includes(st);
  return true;
}

// ── 渲染入口（按视图模式分发）────────────────────────────────────
function _render() {
  if (_viewMode === 'process') { _renderProcessView(); _applyBnActiveState(); return; }
  _renderPartView();
  _applyBnActiveState();
}

// ── 零件视图渲染（5 列 Miller：系统 → 装置 → 零件 → 工序 → 操作） ──
function _renderPartView() {
  $columns.innerHTML = '';

  // 根节点 = 无父级的 PBOM 节点
  const systems = (_childMap.get(null) || []).filter(r => r._is_part);
  if (systems.length === 0) {
    $columns.innerHTML = `<div class="lv-empty">${_previewData.length === 0 ? '请先选择 PBOM 版本' : '无搜索结果'}</div>`;
    return;
  }

  // 如果所有根节点都是叶子零件（平铺 PBOM，无层级），退回3列模式
  const anyHasChildren = systems.some(s => (_childMap.get(s.gid) || []).some(r => r._is_part));
  if (!anyHasChildren) {
    _renderPartViewFlat(systems);
    return;
  }

  // ── 列1：系统 ─────────────────────────────────────────────────
  const col1 = _makeCol('系统', systems.length);
  const body1 = col1.querySelector('.lv-col-body');
  for (const sys of systems) body1.appendChild(_makePbomGroupCard(sys, 'system'));
  $columns.appendChild(col1);

  if (!_activeSystemGid || !_rowByGid.has(_activeSystemGid)) return;

  // ── 列2：装置（系统的 PBOM 子节点）────────────────────────────
  const assemblies = (_childMap.get(_activeSystemGid) || []).filter(r => r._is_part);
  const col2 = _makeCol('装置', assemblies.length);
  const body2 = col2.querySelector('.lv-col-body');
  if (assemblies.length === 0) {
    body2.innerHTML = '<div class="lv-empty" style="font-size:12px">无装置</div>';
  } else {
    for (const asm of assemblies) body2.appendChild(_makePbomGroupCard(asm, 'assembly'));
  }
  $columns.appendChild(col2);

  if (!_activeAssemblyGid || !_rowByGid.has(_activeAssemblyGid)) return;

  // ── 列3：零件（装置的子节点，按匹配状态过滤）──────────────────
  const rawParts = (_childMap.get(_activeAssemblyGid) || []).filter(r => r._is_part);
  const parts = rawParts.filter(_partVisible);
  const col3 = _makeCol('零件', parts.length);
  const body3 = col3.querySelector('.lv-col-body');
  if (parts.length === 0 && rawParts.length > 0) {
    body3.innerHTML = '<div class="lv-empty" style="font-size:12px">当前筛选无结果</div>';
  } else if (parts.length === 0) {
    body3.innerHTML = '<div class="lv-empty" style="font-size:12px">无零件</div>';
  } else {
    for (const part of parts) body3.appendChild(_makePartCard(part));
  }
  $columns.appendChild(col3);

  if (!_activePartGid || !_rowByGid.has(_activePartGid)) return;
  const activePart = _rowByGid.get(_activePartGid);

  // ── 列4 & 列5：工序 & 操作 ────────────────────────────────────
  // 已确认绑定 → 只显示绑定工序；未确认 → 浏览所有工序供手动选择
  const partSt   = _effectiveSt(_activePartGid);
  const isBrowse = !['confirmed', 'matched_1', 'matched'].includes(partSt);
  // 已确认：从 process hierarchy 的 op.parts 反查绑定工序（不依赖跨表 GID 匹配）
  const partProcs = isBrowse ? [] : _getConfirmedProcesses(_activePartGid);

  if (!isBrowse) {
    const col4 = _makeCol(`工序 · ${activePart.vpps || activePart.title}`, partProcs.length);
    const body4 = col4.querySelector('.lv-col-body');
    if (partProcs.length === 0) {
      body4.innerHTML = '<div class="lv-empty" style="font-size:12px">工序加载中…</div>';
      $columns.appendChild(col4);
      // 若 hierarchy 尚未加载，触发加载后重渲染
      if (_processHierarchy.length === 0 && _currentGid) {
        _loadProcessHierarchy();
      }
      return;
    }
    for (const { proc, matchingOps } of partProcs) {
      body4.appendChild(_makeProcCardForPart(proc, matchingOps.length, false));
    }
    $columns.appendChild(col4);

    if (!_activePartProcessGid) { return; }
    const matchedEntry = partProcs.find(({ proc }) => proc.process_entry_gid === _activePartProcessGid);
    if (!matchedEntry) return;

    const ops  = matchedEntry.matchingOps;
    const proc = matchedEntry.proc;
    const col5 = _makeCol(`操作 · ${proc.vpps || proc.title}`, ops.length);
    const body5 = col5.querySelector('.lv-col-body');
    for (const op of ops) body5.appendChild(_makeOpCardForPart(op, _activePartGid));
    $columns.appendChild(col5);

  } else {
    const allProcs = _processHierarchy;
    const col4 = _makeCol(
      `选择工序 · ${activePart.vpps || activePart.title}`,
      allProcs.length,
      { searchable: true, placeholder: '搜索工序 VPPS / 标题…' }
    );
    const body4 = col4.querySelector('.lv-col-body');
    if (allProcs.length === 0) {
      body4.innerHTML = '<div class="lv-empty" style="font-size:12px">无工序数据，请先执行 Auto-Link</div>';
    } else {
      for (const proc of allProcs) {
        body4.appendChild(_makeProcCardForPart(proc, (proc.operations || []).length, true));
      }
    }
    $columns.appendChild(col4);

    if (!_activePartProcessGid) { return; }
    const browseProc = _processHierarchy.find(p => p.process_entry_gid === _activePartProcessGid);
    if (!browseProc) return;

    const allOps = browseProc.operations || [];
    const col5 = _makeCol(
      `操作 · ${browseProc.vpps || browseProc.title}`,
      allOps.length,
      { searchable: true, placeholder: '搜索操作…' }
    );
    const body5 = col5.querySelector('.lv-col-body');
    if (allOps.length === 0) {
      body5.innerHTML = '<div class="lv-empty" style="font-size:12px">无操作</div>';
    } else {
      for (const op of allOps) body5.appendChild(_makeOpCardForPart(op, _activePartGid));
    }
    $columns.appendChild(col5);
  }
}

// ── 平铺 PBOM 退回 3 列模式（零件 → 工序 → 操作）────────────────
function _renderPartViewFlat(parts) {
  const visibleParts = parts.filter(_partVisible);
  const col1 = _makeCol('零件', visibleParts.length);
  const body1 = col1.querySelector('.lv-col-body');
  for (const part of visibleParts) body1.appendChild(_makePartCard(part));
  $columns.appendChild(col1);

  if (!_activePartGid || !_rowByGid.has(_activePartGid)) return;
  const activePart = _rowByGid.get(_activePartGid);

  const partSt    = _effectiveSt(_activePartGid);
  const isBrowse  = !['confirmed', 'matched_1', 'matched'].includes(partSt);
  const partProcs = isBrowse ? [] : _getConfirmedProcesses(_activePartGid);

  if (!isBrowse) {
    const col2 = _makeCol(`工序 · ${activePart.vpps || activePart.title}`, partProcs.length);
    const body2 = col2.querySelector('.lv-col-body');
    if (partProcs.length === 0) {
      body2.innerHTML = '<div class="lv-empty" style="font-size:12px">工序加载中…</div>';
      $columns.appendChild(col2);
      if (_processHierarchy.length === 0 && _currentGid) _loadProcessHierarchy();
      return;
    }
    for (const { proc, matchingOps } of partProcs) {
      body2.appendChild(_makeProcCardForPart(proc, matchingOps.length, false));
    }
    $columns.appendChild(col2);

    if (!_activePartProcessGid) { return; }
    const matchedEntry = partProcs.find(({ proc }) => proc.process_entry_gid === _activePartProcessGid);
    if (!matchedEntry) return;

    const ops  = matchedEntry.matchingOps;
    const proc = matchedEntry.proc;
    const col3 = _makeCol(`操作 · ${proc.vpps || proc.title}`, ops.length);
    const body3 = col3.querySelector('.lv-col-body');
    for (const op of ops) body3.appendChild(_makeOpCardForPart(op, _activePartGid));
    $columns.appendChild(col3);

  } else {
    const allProcs = _processHierarchy;
    const col2 = _makeCol(
      `选择工序 · ${activePart.vpps || activePart.title}`,
      allProcs.length,
      { searchable: true, placeholder: '搜索工序 VPPS / 标题…' }
    );
    const body2 = col2.querySelector('.lv-col-body');
    if (allProcs.length === 0) {
      body2.innerHTML = '<div class="lv-empty" style="font-size:12px">无工序数据</div>';
    } else {
      for (const proc of allProcs) {
        body2.appendChild(_makeProcCardForPart(proc, (proc.operations || []).length, true));
      }
    }
    $columns.appendChild(col2);

    if (!_activePartProcessGid) { return; }
    const browseProc = _processHierarchy.find(p => p.process_entry_gid === _activePartProcessGid);
    if (!browseProc) return;

    const allOps = browseProc.operations || [];
    const col3 = _makeCol(
      `操作 · ${browseProc.vpps || browseProc.title}`,
      allOps.length,
      { searchable: true, placeholder: '搜索操作…' }
    );
    const body3 = col3.querySelector('.lv-col-body');
    if (allOps.length === 0) {
      body3.innerHTML = '<div class="lv-empty" style="font-size:12px">无操作</div>';
    } else {
      for (const op of allOps) body3.appendChild(_makeOpCardForPart(op, _activePartGid));
    }
    $columns.appendChild(col3);
  }
}

// ── 默认展开：首次加载 / 视图切换后自动选中第一个节点 ─────────────
function _autoExpand() {
  if (_viewMode === 'part') {
    const systems = (_childMap.get(null) || []).filter(r => r._is_part);
    const anyHasChildren = systems.some(s => (_childMap.get(s.gid) || []).some(r => r._is_part));
    if (anyHasChildren) {
      // 5 列模式：自动选系统 → 装置
      if (!_activeSystemGid && systems.length > 0) {
        _activeSystemGid = systems[0].gid;
      }
      if (_activeSystemGid && !_activeAssemblyGid) {
        const assemblies = (_childMap.get(_activeSystemGid) || []).filter(r => r._is_part);
        if (assemblies.length > 0) _activeAssemblyGid = assemblies[0].gid;
      }
    } else {
      // 平铺 3 列模式：自动选第一个可见零件
      if (!_activePartGid && systems.length > 0) {
        const visible = systems.filter(_partVisible);
        if (visible.length > 0) _activePartGid = visible[0].gid;
      }
    }
  } else {
    // 工序视图：自动选第一个工序 → 第一个操作
    if (!_activeProcessGid && _processHierarchy.length > 0) {
      _activeProcessGid = _processHierarchy[0].process_entry_gid;
    }
    if (_activeProcessGid && !_activeOpGid) {
      const proc = _processHierarchy.find(p => p.process_entry_gid === _activeProcessGid);
      const ops = proc?.operations || [];
      if (ops.length > 0) _activeOpGid = ops[0].entry_gid;
    }
  }
}

// ── 联动高亮：active-node / active-parent / active-sibling / active-child ──
function _applyBnActiveState() {
  // 清除旧高亮
  $columns.querySelectorAll('.lv-card.active-node,.lv-card.active-parent,.lv-card.active-sibling,.lv-card.active-child')
    .forEach(el => el.classList.remove('active-node', 'active-parent', 'active-sibling', 'active-child'));

  // 当前激活路径（从根到叶，最深的是 active-node）
  const path = _viewMode === 'part'
    ? [_activeSystemGid, _activeAssemblyGid, _activePartGid, _activePartProcessGid].filter(Boolean)
    : [_activeProcessGid, _activeOpGid].filter(Boolean);

  if (!path.length) return;

  const activeGid   = path[path.length - 1];
  const ancestorSet = new Set(path.slice(0, -1));

  const allCols    = [...$columns.querySelectorAll('.lv-col')];
  const activeCard = $columns.querySelector(`.lv-card[data-gid="${CSS.escape(activeGid)}"]`);
  const activeColIdx = activeCard ? allCols.indexOf(activeCard.closest('.lv-col')) : -1;

  $columns.querySelectorAll('.lv-card[data-gid]').forEach(card => {
    const gid = card.dataset.gid;
    if (gid === activeGid) {
      card.classList.add('active-node');
    } else if (ancestorSet.has(gid)) {
      card.classList.add('active-parent');
    } else {
      const colIdx = allCols.indexOf(card.closest('.lv-col'));
      card.classList.add(colIdx > activeColIdx ? 'active-child' : 'active-sibling');
    }
  });

  _scrollToActiveCard(activeGid);
}

// ── 递归获取 PBOM 节点下所有叶子零件 ─────────────────────────────
function _getLeafParts(gid) {
  const children = (_childMap.get(gid) || []).filter(r => r._is_part);
  if (children.length === 0) return [];
  const result = [];
  for (const child of children) {
    const grandchildren = (_childMap.get(child.gid) || []).filter(r => r._is_part);
    if (grandchildren.length === 0) {
      result.push(child);
    } else {
      result.push(..._getLeafParts(child.gid));
    }
  }
  return result;
}

// ── PBOM 分组卡片（系统 / 装置）— lineage 卡片风格 ──────────────
function _makePbomGroupCard(row, nodeType) {
  const card = document.createElement('div');
  card.className = 'lv-card';
  card.dataset.gid = row.gid;

  // 左侧主体
  const main = document.createElement('div');
  main.className = 'lv-card-main';

  const row1 = document.createElement('div');
  row1.className = 'lv-row1';
  const typeLabel = nodeType === 'system' ? '系统' : '装置';
  const typeCls   = nodeType === 'system' ? 'lv-nt-system' : 'lv-nt-assembly';
  const typeSpan  = document.createElement('span');
  typeSpan.className = `lv-type ${typeCls}`;
  typeSpan.textContent = typeLabel;
  row1.appendChild(typeSpan);

  const row2 = document.createElement('div');
  row2.className = 'lv-row2';
  const vpps = row.vpps ? `<span class="bn-vpps">${_esc(row.vpps)}</span> ` : '';
  row2.innerHTML = `<span class="lv-title" title="${_esc(row.title)}">${vpps}${_esc(row.title)}</span>`;

  main.appendChild(row1);
  main.appendChild(row2);
  card.appendChild(main);

  // 右侧统计框
  const leafParts    = _getLeafParts(row.gid);
  const totalCnt     = leafParts.length;
  const unmatchedCnt = leafParts.filter(p => _effectiveSt(p.gid) === 'unmatched').length;
  const confirmedCnt = leafParts.filter(p => ['confirmed','matched_1','matched'].includes(_effectiveSt(p.gid))).length;

  const statsBox = document.createElement('div');
  statsBox.className = 'lv-stats-box';

  const s1 = document.createElement('div');
  s1.className = 'lv-stats-row';
  s1.innerHTML = `<span>零件</span><b>${totalCnt}</b>`;
  statsBox.appendChild(s1);

  if (confirmedCnt > 0) {
    const s2 = document.createElement('div');
    s2.className = 'lv-stats-row';
    s2.style.color = 'var(--green, #a6e3a1)';
    s2.innerHTML = `<span>已匹配</span><b>${confirmedCnt}</b>`;
    statsBox.appendChild(s2);
  }
  if (unmatchedCnt > 0) {
    const s3 = document.createElement('div');
    s3.className = 'lv-stats-row';
    s3.style.color = 'var(--red, #f38ba8)';
    s3.innerHTML = `<span>未匹配</span><b>${unmatchedCnt}</b>`;
    statsBox.appendChild(s3);
  }
  card.appendChild(statsBox);

  // 桥接条
  const bridge = document.createElement('div');
  bridge.className = 'lv-bridge-right has-children';
  card.appendChild(bridge);

  card.addEventListener('click', () => {
    if (nodeType === 'system') {
      _activeSystemGid      = row.gid;
      _activeAssemblyGid    = null;
      _activePartGid        = null;
      _activePartProcessGid = null;
    } else {
      _activeAssemblyGid    = row.gid;
      _activePartGid        = null;
      _activePartProcessGid = null;
    }
    _closePanel();
    _render();
  });
  return card;
}

// ── 获取已确认绑定的工序（从 _processHierarchy 的 op.parts 反查） ──
// 比 _getPartProcesses 更可靠：不依赖 GID 跨表匹配，直接用确认绑定的 pbom_entry_gid
function _getConfirmedProcesses(partGid) {
  const result = [];
  for (const proc of _processHierarchy) {
    const matchingOps = (proc.operations || []).filter(op =>
      (op.parts || []).some(p => p.pbom_entry_gid === partGid)
    );
    if (matchingOps.length > 0) result.push({ proc, matchingOps });
  }
  return result;
}

// ── 获取含指定零件的工序列表（基于 gbop_matches 预匹配，用于浏览模式提示） ──
function _getPartProcesses(partGid) {
  const partRow = _rowByGid.get(partGid);
  if (!partRow) return [];

  // 构建 opGid → proc 反查表（每次调用开销极小）
  const opToProc = new Map();
  const opByGid  = new Map();
  for (const proc of _processHierarchy) {
    for (const op of (proc.operations || [])) {
      opToProc.set(op.entry_gid, proc);
      opByGid.set(op.entry_gid, op);
    }
  }

  // 用 gbop_matches（VPPS 预匹配结果）分组到工序
  const procMap = new Map(); // processGid → { proc, matchingOps: [] }
  for (const match of (partRow.gbop_matches || [])) {
    const proc = opToProc.get(match.entry_gid);
    if (!proc) continue;
    const pgid = proc.process_entry_gid;
    if (!procMap.has(pgid)) procMap.set(pgid, { proc, matchingOps: [] });
    const opFull = opByGid.get(match.entry_gid) || { entry_gid: match.entry_gid, title: match.title, vpps: match.vpps };
    procMap.get(pgid).matchingOps.push(opFull);
  }
  return [...procMap.values()];
}

// ── 通用居中滚动（不依赖 MillerCentering._rowByGid） ─────────────
function _scrollToActiveCard(activeGid) {
  const card = $columns.querySelector(`.lv-card[data-gid="${CSS.escape(activeGid)}"]`);
  if (!card) return;
  requestAnimationFrame(() => {
    const col  = card.closest('.lv-col');
    const body = col?.querySelector('.lv-col-body');
    if (body) {
      const top = card.offsetTop + card.offsetHeight / 2 - body.clientHeight / 2;
      body.scrollTo({ top: Math.max(0, top), behavior: 'smooth' });
    }
    if (col && $wrap) {
      const hTarget = col.offsetLeft + col.offsetWidth / 2 - $wrap.clientWidth / 2;
      $wrap.scrollTo({ left: Math.max(0, hTarget), behavior: 'smooth' });
    }
  });
}

// ── 静默加载工序层级（与 preview 并行） ─────────────────────────
async function _loadProcessHierarchySilent(pbomGid) {
  try {
    const res = await _invokeCapability('craft.gbop.process_hierarchy.read', {
      pbom_version_gid: pbomGid,
    });
    _processHierarchy = res?.data || [];
    _activeProcessGid = null;
    _activeOpGid      = null;
  } catch (_) { /* silent — 工序视图切换时会再次加载 */ }
}

// ── 构建列 DOM（searchable=true 时在 header 下方插入搜索框）────────
function _makeCol(title, count, opts = {}) {
  const col = document.createElement('div');
  col.className = 'lv-col';

  const hdr = document.createElement('div');
  hdr.className = 'lv-col-header';
  hdr.innerHTML = `<span>${_esc(title)}</span><span class="lv-col-count">${count}</span>`;
  col.appendChild(hdr);

  if (opts.searchable) {
    const sw = document.createElement('div');
    sw.className = 'bn-col-search-wrap';
    const inp = document.createElement('input');
    inp.type = 'search';
    inp.className = 'bn-col-search-input';
    inp.placeholder = opts.placeholder || '搜索…';
    sw.appendChild(inp);
    col.appendChild(sw);

    // 实时过滤（仅切换 display，不重建 DOM）
    inp.addEventListener('input', () => {
      const q = inp.value.trim().toLowerCase();
      const countEl = hdr.querySelector('.lv-col-count');
      let visible = 0;
      col.querySelectorAll('.lv-card[data-search]').forEach(card => {
        const show = !q || card.dataset.search.toLowerCase().includes(q);
        card.style.display = show ? '' : 'none';
        if (show) visible++;
      });
      if (countEl) countEl.textContent = visible;
    });
    setTimeout(() => inp.focus(), 60);
  }

  const body = document.createElement('div');
  body.className = 'lv-col-body';
  col.appendChild(body);
  return col;
}

// ── 零件卡片 ─────────────────────────────────────────────────────
function _makePartCard(row) {
  const st = _effectiveSt(row.gid);
  const stCls = _ST_CLS[st] || 'bn-st-p';
  const stLbl = _ST_LABEL[st] || st;
  const p = _pendingChanges.get(row.gid);

  const card = document.createElement('div');
  card.className = 'lv-card';
  card.dataset.gid = row.gid;

  // 行1：类型标签 + 匹配状态徽章
  const row1 = document.createElement('div');
  row1.className = 'lv-row1';
  row1.innerHTML = `
    <span class="lv-type lv-nt-pbom_part">零件</span>
    <span class="bn-badge ${stCls}">${_esc(stLbl)}</span>
    ${p ? '<span class="bn-pending-dot" title="有待提交变更">●</span>' : ''}`;

  // 行2：标题 + part_number
  const row2 = document.createElement('div');
  row2.className = 'lv-row2';
  const vpps = row.vpps ? `<span class="bn-vpps">${_esc(row.vpps)}</span> ` : '';
  row2.innerHTML = `<span class="lv-title" title="${_esc(row.title)}">${vpps}${_esc(row.title)}</span>`;

  if (row.part_number) {
    const row3 = document.createElement('div');
    row3.className = 'lv-row3';
    row3.innerHTML = `<span class="bn-part-num">${_esc(row.part_number)}</span>`;
    card.appendChild(row1);
    card.appendChild(row2);
    card.appendChild(row3);
  } else {
    card.appendChild(row1);
    card.appendChild(row2);
  }

  // 右侧桥接条（同 lineage 卡片，表示有子节点）
  const bridge = document.createElement('div');
  bridge.className = 'lv-bridge-right';
  const hasOps = (row.gbop_matches || []).length > 0;
  if (hasOps) bridge.classList.add('has-children');
  card.appendChild(bridge);

  card.addEventListener('click', () => _selectPart(row.gid));
  return card;
}

// ── 操作卡片 ─────────────────────────────────────────────────────
function _makeOpCard(row) {
  const partGid = row._part_entry_gid;
  const opGid   = row._op_entry_gid;
  const p = _pendingChanges.get(partGid) || {};
  const isPrimary = p.gbop_entry_gid === opGid && p.action === 'confirm';
  const isExtra   = (p.extra_entry_gids || []).includes(opGid);

  const card = document.createElement('div');
  card.className = 'lv-card bn-op-card'
    + (isPrimary ? ' bn-op-primary' : '')
    + (isExtra   ? ' bn-op-extra'   : '');
  card.dataset.gid = row.gid;
  card.dataset.opGid = opGid;
  card.dataset.partGid = partGid;

  const row1 = document.createElement('div');
  row1.className = 'lv-row1';
  row1.innerHTML = `
    <span class="lv-type lv-nt-${_esc(row.node_type)}">${_esc(row.node_type === 'operation' ? '操作' : row.node_type)}</span>
    ${isPrimary ? '<span class="bn-op-tag bn-op-tag-pri">主</span>'  : ''}
    ${isExtra   ? '<span class="bn-op-tag bn-op-tag-ext">附加</span>' : ''}
    ${row._is_primary_feed ? '<span class="bn-feed-star" title="part_feed 主操作">★</span>' : ''}`;

  const row2 = document.createElement('div');
  row2.className = 'lv-row2';
  row2.innerHTML = `<span class="lv-title" title="${_esc(row.title)}">${_esc(row.title)}</span>`;

  card.appendChild(row1);
  card.appendChild(row2);

  card.addEventListener('click', () => {
    // 打开面板并高亮该操作（用于快速确认）
    if (_activePartGid !== partGid) _selectPart(partGid);
    else _openPanel(partGid);
  });
  return card;
}

// ── 工序卡片（零件视图列2用，browse=true 时加 data-search 供列内搜索）──
function _makeProcCardForPart(proc, opCount, browse) {
  const card = document.createElement('div');
  card.className = 'lv-card';
  card.dataset.gid = proc.process_entry_gid;
  if (browse) card.dataset.search = `${proc.vpps || ''} ${proc.title || ''}`.toLowerCase();

  const row1 = document.createElement('div');
  row1.className = 'lv-row1';
  row1.innerHTML = `<span class="lv-type lv-nt-process">工序</span>`;

  const row2 = document.createElement('div');
  row2.className = 'lv-row2';
  const vpps = proc.vpps ? `<span class="bn-vpps">${_esc(proc.vpps)}</span> ` : '';
  row2.innerHTML = `<span class="lv-title" title="${_esc(proc.title)}">${vpps}${_esc(proc.title)}</span>`;

  card.appendChild(row1);
  card.appendChild(row2);

  const bridge = document.createElement('div');
  bridge.className = 'lv-bridge-right has-children';
  card.appendChild(bridge);

  card.addEventListener('click', () => {
    _activePartProcessGid = proc.process_entry_gid;
    _render();
  });
  return card;
}

// ── 操作卡片（零件视图列3用）────────────────────────────────────
function _makeOpCardForPart(op, partGid) {
  const card = document.createElement('div');
  card.className = 'lv-card';
  card.dataset.gid    = op.entry_gid;
  card.dataset.search = `${op.vpps || ''} ${op.title || ''}`.toLowerCase();

  const row1 = document.createElement('div');
  row1.className = 'lv-row1';
  row1.innerHTML = `<span class="lv-type lv-nt-operation">操作</span>`;

  const row2 = document.createElement('div');
  row2.className = 'lv-row2';
  const vpps = op.vpps ? `<span class="bn-vpps">${_esc(op.vpps)}</span> ` : '';
  row2.innerHTML = `<span class="lv-title" title="${_esc(op.title)}">${vpps}${_esc(op.title)}</span>`;

  card.appendChild(row1);
  card.appendChild(row2);

  card.addEventListener('click', () => _openPanel(partGid));
  return card;
}

// ── 根据 opGid 反查所属工序 ─────────────────────────────────────
function _findProcByOpGid(opGid) {
  for (const proc of _processHierarchy) {
    if ((proc.operations || []).some(op => op.entry_gid === opGid)) return proc;
  }
  return null;
}

// ── 零件选中（只展开列4工序，不开面板，保留系统/装置上下文） ────
function _selectPart(partGid) {
  _activePartGid = partGid;
  _activePartProcessGid = null;
  _closePanel();

  // 已确认绑定：自动定位到绑定工序，省去二次点击
  const partRow = _rowByGid.get(partGid);
  const partSt  = _effectiveSt(partGid);
  const isConfirmed = ['confirmed', 'matched_1', 'matched'].includes(partSt);
  if (isConfirmed) {
    // 优先：本地暂存的确认绑定（pending confirm）
    const pending = _pendingChanges.get(partGid);
    if (pending?.action === 'confirm' && pending.gbop_entry_gid) {
      const proc = _findProcByOpGid(pending.gbop_entry_gid);
      if (proc) _activePartProcessGid = proc.process_entry_gid;
    }
    // 否则：从 hierarchy op.parts 反查（最可靠）
    if (!_activePartProcessGid) {
      const confirmed = _getConfirmedProcesses(partGid);
      if (confirmed.length > 0) _activePartProcessGid = confirmed[0].proc.process_entry_gid;
    }
  }

  _render();
}

// ── 操作选择面板 ──────────────────────────────────────────────────
function _openPanel(partGid) {
  const row = _rowByGid.get(partGid);
  if (!row) return;

  $panelTitle.textContent = `${row.vpps || ''} ${row.title || ''}`.trim();
  $panel.classList.remove('hidden');

  const p = _pendingChanges.get(partGid) || {};
  const curPrimary = p.gbop_entry_gid || null;
  const curExtras  = new Set(p.extra_entry_gids || []);
  const ops = _childMap.get(partGid) || [];

  if (ops.length === 0) {
    $panelBody.innerHTML = `
      <div class="bn-panel-hint">该零件没有匹配到 GBOP 操作</div>
      <div class="bn-panel-status-row">
        <span class="bn-badge ${_ST_CLS[_effectiveSt(partGid)] || ''}">${_ST_LABEL[_effectiveSt(partGid)] || ''}</span>
      </div>`;
    return;
  }

  let html = `<div class="bn-op-list-hdr">
    <span>匹配操作</span>
    <span class="bn-op-legend"><span class="bn-legend-dot pri"></span>radio=主操作&ensp;<span class="bn-legend-dot ext"></span>checkbox=附加</span>
  </div>`;

  for (const op of ops) {
    const opGid = op._op_entry_gid;
    const isMy  = opGid === curPrimary;
    const isExt = curExtras.has(opGid);
    const cls   = isMy ? 'bn-op-item bn-op-item-pri' : isExt ? 'bn-op-item bn-op-item-ext' : 'bn-op-item';
    const feed  = op._is_primary_feed
      ? `<svg class="bn-feed-icon" viewBox="0 0 24 24" width="10" height="10" fill="currentColor"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>`
      : '';
    html += `<div class="${cls}" data-op="${_esc(opGid)}">
      <input type="radio"    class="bn-radio" name="bn_pri" value="${_esc(opGid)}" ${isMy  ? 'checked' : ''} />
      <input type="checkbox" class="bn-chk"   name="bn_ext" value="${_esc(opGid)}" ${isExt ? 'checked' : ''} />
      <div class="bn-op-info">
        <div class="bn-op-title">${feed}${_esc(op.title)}</div>
        <div class="bn-op-meta">${_esc(op.node_type || '')} · …${_esc(opGid.slice(-6))}</div>
      </div>
    </div>`;
  }
  $panelBody.innerHTML = html;

  // radio 互斥
  $panelBody.querySelectorAll('input[name="bn_pri"]').forEach(r => {
    r.addEventListener('change', () => {
      const cb = $panelBody.querySelector(`input[name="bn_ext"][value="${r.value}"]`);
      if (cb?.checked) cb.checked = false;
      _syncPanelStyles();
    });
  });
  $panelBody.querySelectorAll('input[name="bn_chk"], input[name="bn_ext"]').forEach(cb => {
    cb.addEventListener('change', () => {
      if (cb.checked) {
        const r = $panelBody.querySelector(`input[name="bn_pri"][value="${cb.value}"]`);
        if (r?.checked) r.checked = false;
      }
      _syncPanelStyles();
    });
  });
}

function _syncPanelStyles() {
  const pri = $panelBody.querySelector('input[name="bn_pri"]:checked')?.value || null;
  const ext = new Set([...$panelBody.querySelectorAll('input[name="bn_ext"]:checked')].map(c => c.value));
  $panelBody.querySelectorAll('.bn-op-item').forEach(el => {
    const g = el.dataset.op;
    el.classList.remove('bn-op-item-pri','bn-op-item-ext');
    if (g === pri)      el.classList.add('bn-op-item-pri');
    else if (ext.has(g)) el.classList.add('bn-op-item-ext');
  });
}

function _getPanelSelection() {
  return {
    gbop_entry_gid:   $panelBody.querySelector('input[name="bn_pri"]:checked')?.value || null,
    extra_entry_gids: [...$panelBody.querySelectorAll('input[name="bn_ext"]:checked')].map(e => e.value),
  };
}

function _closePanel() {
  $panel.classList.add('hidden');
}

// ── 提交 ─────────────────────────────────────────────────────────
async function _submit() {
  if (!_currentGid || !_pendingChanges.size) return;
  const matches = [..._pendingChanges.entries()].map(([pbom_entry_gid, v]) => ({
    pbom_entry_gid,
    gbop_entry_gid:   v.gbop_entry_gid || '',
    action:           v.action,
    extra_entry_gids: v.extra_entry_gids || [],
  }));
  try {
    $submit.disabled = true;
    $submit.textContent = '提交中…';
    await _invokeCapability('craft.bop.gbop.change.apply', {
      operation: 'match_confirm',
      pbom_gid: _currentGid,
      matches,
    });
    _pendingChanges.clear();
    _toast('提交成功', 'ok');
    await _load(_currentGid);

    // 写回统计到 BOP version meta（供生命周期面板展示）
    if (_bopVersionGid && _currentGid) {
      try {
        const data = _previewData || [];
        const total     = data.filter(p => !p._isVirtualOp).length;
        const confirmed = data.filter(p => !p._isVirtualOp && ['confirmed','matched_1','matched'].includes(_effectiveSt(p.gid))).length;
        const skipped   = data.filter(p => !p._isVirtualOp && _effectiveSt(p.gid) === 'skipped').length;
        await _invokeCapability('craft.bop.lifecycle.change.apply', {
          operation: 'vehicle_ops_stats.update',
          version_gid: _bopVersionGid,
          confirmed,
          skipped,
          total,
        });
      } catch (_) {}  // fire-and-forget
    }
  } catch (e) {
    _toast('提交失败：' + e.message, 'error');
  } finally {
    $submit.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg> 提交`;
    _updateSubmit();
  }
}

function _updateSubmit() {
  $submit.disabled = _pendingChanges.size === 0;
}

// ── 版本选择器 dropdown ───────────────────────────────────────────
let _verMenuOpen = false;

function _toggleVerMenu() {
  _verMenuOpen = !_verMenuOpen;
  $verMenu.style.display = _verMenuOpen ? 'block' : 'none';
  if (_verMenuOpen) _renderVerMenu();
}

function _closeVerMenu() {
  _verMenuOpen = false;
  $verMenu.style.display = 'none';
}

function _renderVerMenu() {
  $verMenu.innerHTML = '';

  if (_projects.length === 0) {
    $verMenu.innerHTML = '<div class="lv-vp-empty">暂无项目</div>';
    return;
  }

  for (const proj of _projects) {
    const isExpanded = _expanded.has(proj.gid);
    const versions   = _pbomByProject.get(proj.gid) || [];

    const hdr = document.createElement('div');
    hdr.className = 'lv-vp-group-hdr';
    hdr.innerHTML = `
      <svg style="flex-shrink:0;transition:transform .15s;transform:${isExpanded ? 'rotate(90deg)' : ''}"
           width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <polyline points="9 18 15 12 9 6"/>
      </svg>
      <span>${_esc(proj.name || proj.gid)}</span>`;

    hdr.addEventListener('click', async () => {
      if (!_expanded.has(proj.gid)) {
        _expanded.add(proj.gid);
        if (!_pbomByProject.has(proj.gid)) {
          try {
            const d = await _invokeCapability('craft.pbom.version.search', {
              project_ref: proj.gid,
              limit: 200,
            });
            _pbomByProject.set(proj.gid, d?.items || []);
          } catch { _pbomByProject.set(proj.gid, []); }
        }
      } else {
        _expanded.delete(proj.gid);
      }
      _renderVerMenu();
    });
    $verMenu.appendChild(hdr);

    if (!isExpanded) continue;

    const vers = _pbomByProject.get(proj.gid) || [];
    if (vers.length === 0) {
      const empty = document.createElement('div');
      empty.className = 'lv-vp-item';
      empty.style.opacity = '.5';
      empty.textContent = '暂无 PBOM 版本';
      $verMenu.appendChild(empty);
      continue;
    }

    for (const ver of vers) {
      const item = document.createElement('div');
      item.className = 'lv-vp-item' + (ver.gid === _currentGid ? ' active' : '');
      item.innerHTML = `
        <span class="lv-vp-item-dot"></span>
        <span>${_esc(ver.title || ver.gid)}</span>
        ${ver.status ? `<span style="font-size:10px;opacity:.55;margin-left:auto">${_esc(ver.status)}</span>` : ''}`;
      item.addEventListener('click', () => {
        _currentGid = ver.gid;
        $verLabel.textContent = ver.title || ver.gid;
        _closeVerMenu();
        localStorage.setItem(_lsk('bn:lastPbomGid'), ver.gid);
        if (_assocPanel) _assocPanel.setVersionGid(ver.gid);
        _load(ver.gid);
      });
      $verMenu.appendChild(item);
    }
  }
}

// ── 主题 ─────────────────────────────────────────────────────────
function _applyTheme() {
  if (_theme === 'light') {
    document.documentElement.setAttribute('data-lv-theme', 'light');
    document.getElementById('bnThemeLabel').textContent = '暗色';
  } else {
    document.documentElement.removeAttribute('data-lv-theme');
    document.getElementById('bnThemeLabel').textContent = '亮色';
  }
}

// ── 初始化 ────────────────────────────────────────────────────────
(async function init() {
  _applyTheme();

  // 加载项目列表
  try {
    const d = await _invokeCapability('project.project.read.atomic.projects_search', {
      limit: 200,
    });
    _projects = (d?.data || d || []).filter(p => !p.is_deleted && p.project_type !== 'gbop');
  } catch (e) { console.warn('[BopNav] 加载项目失败:', e); }

  // 初始化 MillerCentering
  _miller = new MillerCentering({
    scrollContainer: $wrap,
    getCardByGid:    (gid) => $columns.querySelector(`.lv-card[data-gid="${CSS.escape(gid)}"]`),
    childMap:        _childMap,
    rowByGid:        _rowByGid,
    depthByGid:      new Map(),
  });

  // URL 参数自动展开项目 / 恢复上次版本
  const params = Object.fromEntries(new URLSearchParams(location.search));
  if (params.project_gid) _expanded.add(params.project_gid);

  const lastGid = params.pbom_version_gid || localStorage.getItem(_lsk('bn:lastPbomGid'));
  if (lastGid) {
    _currentGid = lastGid;
    $verLabel.textContent = lastGid;
    _load(lastGid);
  } else {
    $columns.innerHTML = '<div class="lv-empty">请在左上角选择 PBOM 版本</div>';
  }

  // ── 事件绑定 ──────────────────────────────────────────────────

  // 版本下拉
  $verBtn.addEventListener('click', (e) => { e.stopPropagation(); _toggleVerMenu(); });
  document.addEventListener('click', (e) => {
    if (_verMenuOpen && !$verBtn.closest('.lv-vp-select-wrap').contains(e.target)) _closeVerMenu();
  });

  // 状态过滤 tabs
  document.getElementById('bnFilterTabs').addEventListener('click', e => {
    const btn = e.target.closest('.bn-ftab');
    if (!btn) return;
    _filter = btn.dataset.f;
    document.querySelectorAll('.bn-ftab').forEach(b => b.classList.toggle('active', b === btn));
    _render();
  });

  // 搜索
  $search.addEventListener('input', () => {
    _searchText = $search.value;
    _render();
  });

  // 提交
  $submit.addEventListener('click', _submit);

  // 刷新
  document.getElementById('bnRefresh').addEventListener('click', () => {
    if (_currentGid) _load(_currentGid);
  });

  // 面板关闭
  document.getElementById('bnPanelClose').addEventListener('click', _closePanel);

  // 跳过
  document.getElementById('bnBtnSkip').addEventListener('click', () => {
    if (!_activePartGid) return;
    _pendingChanges.set(_activePartGid, { action: 'skip', gbop_entry_gid: '', extra_entry_gids: [] });
    _updateSubmit();
    _closePanel();
    _render();
    _toast('已标记为跳过', 'ok');
  });

  // 确认
  document.getElementById('bnBtnConfirm').addEventListener('click', () => {
    if (!_activePartGid) return;
    const { gbop_entry_gid, extra_entry_gids } = _getPanelSelection();
    if (!gbop_entry_gid) { _toast('请先选择主操作（radio）', 'warn'); return; }
    _pendingChanges.set(_activePartGid, { action: 'confirm', gbop_entry_gid, extra_entry_gids });
    _updateSubmit();
    _closePanel();
    _render();
    _toast('已暂存，点提交生效', 'ok');
  });

  // 主题
  document.getElementById('bnTheme').addEventListener('click', () => {
    _theme = _theme === 'light' ? 'dark' : 'light';
    localStorage.setItem(_lsk('bn:theme'), _theme);
    _applyTheme();
  });

  // ── 右侧边栏 ────────────────────────────────────────────────
  _initSidebar();
})();

// ── Auto-Link 状态同步（全局，_load 也能调用） ────────────────────
function _syncAutoLinkState(hasPending) {
  const btnAL = document.getElementById('bnAutoLink');
  const btnConfirm = document.getElementById('bnAutoLinkConfirm');
  if (!btnAL || !btnConfirm) return;
  btnAL.disabled = hasPending;
  btnConfirm.style.display = hasPending ? '' : 'none';
}

async function _checkAutoLinkState(pbomGid) {
  if (!pbomGid) return;
  try {
    const res = await _invokeCapability('craft.gbop.navigation.read', {
      operation: 'auto_link_status',
      pbom_version_gid: pbomGid,
    });
    const d = res.data || {};
    _syncAutoLinkState((d.pending_count || 0) > 0);
  } catch (_) { /* 静默失败，不影响主流程 */ }
}
  document.getElementById('bnAutoLink').addEventListener('click', async () => {
    if (!_currentGid) { _toast('请先选择 PBOM 版本', 'warn'); return; }
    const btn = document.getElementById('bnAutoLink');
    btn.disabled = true;
    btn.textContent = '匹配中…';
    try {
      const res = await _invokeCapability('craft.gbop.navigation.change.apply', {
        operation: 'auto_link',
        pbom_version_gid: _currentGid,
      });
      const d = res.data || {};
      _toast(`Auto-Link 完成：${d.parts_matched || 0} 零件已匹配，绑定 ${d.bound || 0} 条，请确认后提交`, 'ok', 5000);
      _syncAutoLinkState(true);
      if (_viewMode === 'process') await _loadProcessHierarchy();
      else await _load(_currentGid);
    } catch (e) {
      _toast('Auto-Link 失败：' + e.message, 'error');
      btn.disabled = false;
    } finally {
      btn.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71"/>
        <path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71"/>
      </svg> Auto-Link`;
    }
  });

  // 确认绑定
  document.getElementById('bnAutoLinkConfirm').addEventListener('click', async () => {
    if (!_currentGid) return;
    const btn = document.getElementById('bnAutoLinkConfirm');
    btn.disabled = true;
    btn.textContent = '提交中…';
    try {
      const res = await _invokeCapability('craft.gbop.navigation.change.apply', {
        operation: 'confirm',
        pbom_version_gid: _currentGid,
      });
      const d = res.data || res || {};
      _toast(`已确认 ${d.confirmed || 0} 条 Auto-Link 绑定`, 'ok');
      _syncAutoLinkState(false);
      if (_viewMode === 'process') await _loadProcessHierarchy();
      else await _load(_currentGid);
    } catch (e) {
      _toast('确认失败：' + e.message, 'error');
    } finally {
      btn.disabled = false;
      btn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg> 确认绑定`;
    }
  });

  // 视图切换
  document.getElementById('bnViewToggle').addEventListener('click', async e => {
    const btn = e.target.closest('.bn-vtab');
    if (!btn) return;
    const v = btn.dataset.v;
    if (v === _viewMode) return;
    _viewMode = v;
    document.querySelectorAll('.bn-vtab').forEach(b => b.classList.toggle('active', b === btn));
    if (v === 'process') {
      if (_assocPanel) _assocPanel.setExclusiveTab('pbom_nav');
      if (_processHierarchy.length === 0 && _currentGid) {
        await _loadProcessHierarchy();
      } else {
        _autoExpand();
        _renderProcessView();
        _applyBnActiveState();
      }
    } else {
      if (_assocPanel) _assocPanel.setExclusiveTab('gbop_nav');
      _autoExpand();
      _render();
    }
  });

// ── 右侧边栏初始化 ────────────────────────────────────────────────
function _initSidebar() {
  // 恢复折叠状态
  if (localStorage.getItem(_lsk('bn:sbOpen')) === 'false') {
    $sidebar.classList.add('collapsed');
    $sbToggle.textContent = '◀';
  }

  // 折叠按钮
  $sbToggle.addEventListener('click', () => {
    const isCollapsed = $sidebar.classList.toggle('collapsed');
    $sbToggle.textContent = isCollapsed ? '◀' : '▶';
    localStorage.setItem(_lsk('bn:sbOpen'), String(!isCollapsed));
  });

  // 规则判定 / 参考信息 折叠面板 toggle
  _initCpanelToggle('bnRuleToggle', 'bnRulePanel');
  _initCpanelToggle('bnRefToggle',  'bnRefPanel');

  // 初始化关联面板，tab 由视图切换动态设置（零件视图=gbop_nav，工序视图=pbom_nav）
  const tabKey = _lsk('lv:assocTabs:bn_nav');
  // 清除旧的持久化 tab 配置，避免错误状态残留
  localStorage.setItem(tabKey, JSON.stringify([{ listType: 'gbop_nav', label: 'GBOP' }]));
  _assocPanel = new AssocPanel({
    tabsEl:    document.getElementById('bnAssocTabs'),
    bodyEl:    document.getElementById('bnAssocBody'),
    versionGid: _currentGid || 'bn_nav',
    cf:        _cf,
    toast:     _toast,
  });
}

function _initCpanelToggle(toggleId, panelId) {
  const btn   = document.getElementById(toggleId);
  const panel = document.getElementById(panelId);
  if (!btn || !panel) return;
  btn.addEventListener('click', () => {
    panel.classList.toggle('collapsed');
  });
}

// ══════════════════════════════════════════════════════════════════
// 工序视图（3 级 Miller Columns）
// ══════════════════════════════════════════════════════════════════

// ── 加载 process-hierarchy 数据 ─────────────────────────────────
async function _loadProcessHierarchy() {
  if (!_currentGid) return;
  $columns.innerHTML = '<div class="lv-loading"><div class="lv-spinner"></div>加载工序层级…</div>';
  try {
    const res = await _invokeCapability('craft.gbop.process_hierarchy.read', {
      pbom_version_gid: _currentGid,
    });
    _processHierarchy = res?.data || [];
    _activeProcessGid = null;
    _activeOpGid      = null;
    _autoExpand();
    _renderProcessView();
    _applyBnActiveState();
  } catch (e) {
    $columns.innerHTML = `<div class="lv-empty">加载工序层级失败：${_esc(e.message)}</div>`;
    _toast('加载失败: ' + e.message, 'error');
  }
}

// ── 渲染：3列 Miller Columns（工序 → 操作 → 零件）────────────────
function _renderProcessView() {
  $columns.innerHTML = '';

  if (_processHierarchy.length === 0) {
    $columns.innerHTML = '<div class="lv-empty">暂无工序数据，请先点击 Auto-Link</div>';
    return;
  }

  // ── 列1：工序 ────────────────────────────────────────────────────
  const col1 = _makeCol('工序', _processHierarchy.length);
  const body1 = col1.querySelector('.lv-col-body');
  for (const proc of _processHierarchy) {
    body1.appendChild(_makeProcCard(proc));
  }
  $columns.appendChild(col1);

  if (!_activeProcessGid) return;
  const activeProc = _processHierarchy.find(p => p.process_entry_gid === _activeProcessGid);
  if (!activeProc) return;

  // ── 列2：操作 ────────────────────────────────────────────────────
  const ops = activeProc.operations || [];
  const col2 = _makeCol(`操作 · ${activeProc.vpps || activeProc.title}`, ops.length);
  const body2 = col2.querySelector('.lv-col-body');
  if (ops.length === 0) {
    body2.innerHTML = '<div class="lv-empty" style="font-size:12px">无操作</div>';
  } else {
    for (const op of ops) body2.appendChild(_makeOpCard2(op));
  }
  $columns.appendChild(col2);

  if (!_activeOpGid) return;
  const activeOp = ops.find(o => o.entry_gid === _activeOpGid);
  if (!activeOp) return;

  // ── 列3：零件 ────────────────────────────────────────────────────
  const parts = activeOp.parts || [];
  const col3 = _makeCol(`零件 · ${activeOp.vpps || activeOp.title}`, parts.length);
  const body3 = col3.querySelector('.lv-col-body');
  if (parts.length === 0) {
    body3.innerHTML = '<div class="lv-empty" style="font-size:12px">无零件</div>';
  } else {
    for (const part of parts) body3.appendChild(_makePartCard2(part));
  }
  $columns.appendChild(col3);
}

// ── 工序卡片 ─────────────────────────────────────────────────────
function _makeProcCard(proc) {
  const card = document.createElement('div');
  card.className = 'lv-card';
  card.dataset.gid = proc.process_entry_gid;

  const main = document.createElement('div');
  main.className = 'lv-card-main';

  const row1 = document.createElement('div');
  row1.className = 'lv-row1';
  row1.innerHTML = `<span class="lv-type lv-nt-process">工序</span>`;

  const row2 = document.createElement('div');
  row2.className = 'lv-row2';
  const vpps = proc.vpps ? `<span class="bn-vpps">${_esc(proc.vpps)}</span> ` : '';
  row2.innerHTML = `<span class="lv-title" title="${_esc(proc.title)}">${vpps}${_esc(proc.title)}</span>`;

  main.appendChild(row1);
  main.appendChild(row2);
  card.appendChild(main);

  const stats = document.createElement('div');
  stats.className = 'lv-stats-box';
  stats.innerHTML = `
    <div class="lv-stats-row"><span class="lv-stats-nt">操</span><b>${proc.op_count}</b></div>
    <div class="lv-stats-row"><span class="lv-stats-nt">件</span><b>${proc.part_count}</b></div>
    <div class="lv-stats-row" style="visibility:hidden"><span>—</span><b></b></div>
    <div class="lv-stats-row" style="visibility:hidden"><span>—</span><b></b></div>`;
  card.appendChild(stats);

  // 右侧桥接条（有子操作时显示）
  const bridge = document.createElement('div');
  bridge.className = 'lv-bridge-right' + (proc.op_count > 0 ? ' has-children' : '');
  card.appendChild(bridge);

  card.addEventListener('click', () => {
    _activeProcessGid = proc.process_entry_gid;
    _activeOpGid = null;
    _renderProcessView();
    _applyBnActiveState();
  });
  return card;
}

// ── 操作卡片（工序视图用）────────────────────────────────────────
function _makeOpCard2(op) {
  const card = document.createElement('div');
  card.className = 'lv-card';
  card.dataset.gid = op.entry_gid;

  const main = document.createElement('div');
  main.className = 'lv-card-main';

  const row1 = document.createElement('div');
  row1.className = 'lv-row1';
  row1.innerHTML = `<span class="lv-type lv-nt-operation">操作</span>`;

  const row2 = document.createElement('div');
  row2.className = 'lv-row2';
  const vpps = op.vpps ? `<span class="bn-vpps">${_esc(op.vpps)}</span> ` : '';
  row2.innerHTML = `<span class="lv-title" title="${_esc(op.title)}">${vpps}${_esc(op.title)}</span>`;

  main.appendChild(row1);
  main.appendChild(row2);
  card.appendChild(main);

  const stats = document.createElement('div');
  stats.className = 'lv-stats-box';
  const partCount = (op.parts || []).length;
  stats.innerHTML = `
    <div class="lv-stats-row"><span class="lv-stats-nt">件</span><b>${partCount}</b></div>
    <div class="lv-stats-row" style="visibility:hidden"><span>—</span><b></b></div>
    <div class="lv-stats-row" style="visibility:hidden"><span>—</span><b></b></div>
    <div class="lv-stats-row" style="visibility:hidden"><span>—</span><b></b></div>`;
  card.appendChild(stats);

  // 右侧桥接条（有零件时显示）
  const bridge = document.createElement('div');
  bridge.className = 'lv-bridge-right' + (partCount > 0 ? ' has-children' : '');
  card.appendChild(bridge);

  card.addEventListener('click', () => {
    _activeOpGid = op.entry_gid;
    _renderProcessView();
    _applyBnActiveState();
  });
  return card;
}

// ── 零件卡片（工序视图用）────────────────────────────────────────
function _makePartCard2(part) {
  const stCls = part.confirmed ? 'bn-st-c' : 'bn-st-p';
  const stLbl = part.confirmed ? '已确认' : '待确认';
  const card  = document.createElement('div');
  card.className = 'lv-card';
  card.dataset.gid = part.pbom_entry_gid;

  const main = document.createElement('div');
  main.className = 'lv-card-main';

  const row1 = document.createElement('div');
  row1.className = 'lv-row1';
  row1.innerHTML = `
    <span class="lv-type lv-nt-pbom_part">零件</span>
    <span class="bn-badge ${stCls}" style="margin-left:auto">${stLbl}</span>`;

  const row2 = document.createElement('div');
  row2.className = 'lv-row2';
  const vpps = part.vpps ? `<span class="bn-vpps">${_esc(part.vpps)}</span> ` : '';
  row2.innerHTML = `<span class="lv-title" title="${_esc(part.title)}">${vpps}${_esc(part.title)}</span>`;

  main.appendChild(row1);
  main.appendChild(row2);

  if (part.part_no) {
    const row3 = document.createElement('div');
    row3.className = 'lv-row3';
    row3.innerHTML = `<span class="bn-part-num">${_esc(part.part_no)}</span>`;
    main.appendChild(row3);
  }
  card.appendChild(main);

  const stats = document.createElement('div');
  stats.className = 'lv-stats-box';
  stats.innerHTML = `
    <div class="lv-stats-row" style="visibility:hidden"><span>—</span><b></b></div>
    <div class="lv-stats-row" style="visibility:hidden"><span>—</span><b></b></div>
    <div class="lv-stats-row" style="visibility:hidden"><span>—</span><b></b></div>
    <div class="lv-stats-row" style="visibility:hidden"><span>—</span><b></b></div>`;
  card.appendChild(stats);
  return card;
}
