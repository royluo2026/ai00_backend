// ── 常量 ────────────────────────────────────────────────────────
// 节点类型 AI_00 显示名：对照 docs/bop/db csv ui.xlsx "零组件类型AI_00" 列
// 注意：CSV 导入映射用 _TC_TYPE_MAP（对照"零组件类型"列），本表仅用于 UI 显示
const NODE_TYPE_LABELS = {
  factory_bop:          '总装工厂BOP',
  line_process:         '总装线体工艺',
  station_process:      '总装工位工艺',
  operator_process:     '总装岗位工艺',
  man:                  '人',
  station_factory:      '工厂工位',
  equipment_factory:    '设备（工厂）',
  tool_factory:         '工具（工厂）',
  equipment_need:       '设备（需求）',
  fixture_factory:      '工装（工厂）',
  process:              '总装工序',
  operation:            '总装操作（Product）',
  issue:                '问题',
  standard_task:        '标准任务',
  non_standard_task:    '非标任务',
  contral_plan:         '控制计划',
  process_chart:        '工艺卡',
  knowledge:            '知识',
  rule:                 '规则',
  part:                 '零部件',
  non_standard_part:    '非标件',
  standard_part:        '标准件',
  support_material:     '辅料',
  tool_need:            '工具（需求）',
  fixture_need:         '工装（需求）',
  floor_height_factory: '地面高度（现有）',
  jack_pos:             '人机姿态',
};
const MATURITY_LABELS = { concept: '概念', planned: '计划', released: '发布', frozen: '冻结' };

// ── BOP 列定义 ───────────────────────────────────────────────────
const BOP_COLUMNS = [
  // ── 默认显示（核心列）──────────────────────────────────────
  { key: 'node_type',        label: '零组件类型AI00', width: 130, type: 'text', visible: true  },
  { key: 'ai00_level',       label: 'AI00Level',       width: 60,  type: 'number', visible: true  },
  { key: 'title',            label: '零件组件名称',    flex:  4,   type: 'text',  visible: true  },
  { key: 'bom_row_id',       label: 'bom_row_id',      width: 120, type: 'text',  visible: true  },
  { key: 'bom_row_owner',    label: 'bom_row_owner',   width: 130, type: 'text',  visible: true  },
  { key: 'vpps',             label: 'vpps',            width: 140, type: 'text',  visible: true  },
  { key: 'vpps_desc',        label: 'vpps描述',        width: 180, type: 'text',  visible: true  },
  { key: 'bom_row_label',    label: 'BOM行',           width: 220, type: 'text',  visible: true  },
  { key: 'parent_bop_label', label: '父级',            width: 220, type: 'text',  visible: true  },

  // ── 其他列 ────────────────────────────────────────────────
  { key: '_tc_type',         label: '零组件类型TC',    width: 130, type: 'text', visible: true  },
  { key: 'level',            label: 'Level',           width: 60,  type: 'number', visible: true  },
  { key: 'seq_no',           label: 'BOP序号',         width: 70,  type: 'number', visible: true  },
  { key: '_actions',         label: '',                width: 145, visible: true, alwaysVisible: true },

  // ── 管理字段 ─────────────────────────────────────────────────
  { key: 'gbop_source_gid',    label: 'GBOP溯源',    width: 130, type: 'text', visible: false },
  { key: 'history_source_gid', label: '工序来源溯源',width: 130, type: 'text', visible: false },
  { key: 'owner_gid',  label: '负责人GID', width: 110, type: 'text',     visible: false },
  { key: 'created_by', label: '创建人',    width: 90,  type: 'text',     visible: false },
  { key: 'created_at', label: '创建时间',  width: 140, type: 'datetime', visible: false },
  { key: 'updated_at', label: '更新时间',  width: 140, type: 'datetime', visible: false },
];

const BOP_CELL_RENDERER = {
  node_type: (val) => {
    const label = NODE_TYPE_LABELS[val] || val || '—';
    return `<span class="bop-nt-badge bop-nt-${val}">${label}</span>`;
  },
  _tc_type: (val, row) => {
    // 优先从 row.meta.tc_type 取 TC 原始类型名
    let tc = '';
    if (row.meta && typeof row.meta === 'string') { try { tc = JSON.parse(row.meta).tc_type || ''; } catch(_) {} }
    else if (row.meta && typeof row.meta === 'object') { tc = row.meta.tc_type || ''; }
    return tc ? ListShell._esc(tc) : '—';
  },
  _actions: (_, row) =>
    `<span class="bop-row-actions">
       <button class="btn-xs btn-ghost" data-act="edit"  data-gid="${row.gid}">编辑</button>
       <button class="btn-xs btn-ghost" data-act="child" data-gid="${row.gid}">+子</button>
       <button class="btn-xs btn-ghost" style="color:var(--danger)" data-act="del" data-gid="${row.gid}">删除</button>
     </span>`,
};

/** 兼容旧数据：若行仍含 meta JSONB，将 title 提升到顶层 */

// ── State ────────────────────────────────────────────────────────
let _shell = null;
let _currentVersion = null;
let _parsedTcRows = [];
let _bopVersions  = [];               // 所有版本（含归档）
let _bopFamilyCollapsed = new Set();  // 折叠的版本族 family_gid
let _bopArcOpen   = false;            // 已归档区是否展开

// ── Helpers ──────────────────────────────────────────────────────

function openModal(id)  { document.getElementById(id)?.classList.remove('hidden'); }
function closeModal(id) { document.getElementById(id)?.classList.add('hidden'); }

function _toast(msg, type = 'info') {
  const el = document.createElement('div');
  el.className = `bop-toast bop-toast-${type}`;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

function _flattenMeta(rows) {
  for (const row of rows) {
    const m = row.meta;
    if (m && typeof m === 'object') {
      if (!row.title && m.title) row.title = m.title;
      // 保留 meta 供 _tc_type 等渲染器使用
    }
  }
  return rows;
}

// ── 加载条目 ─────────────────────────────────────────────────────
async function load() {
  if (!_currentVersion) return;
  try {
    const json = await ListShell._cf(`/api/bop/versions/${_currentVersion}/entries`);
    _shell.setRows(_flattenMeta(json.data || []));
  } catch (e) { _toast('加载失败: ' + e.message, 'error'); }
}

// ── ListShell 初始化 ─────────────────────────────────────────────
function _initShell() {
  _shell = new ListShell({
    mountEl:    document.getElementById('appRoot'),
    itemType:   'bop_version',
    moduleId:   'bop',
    columns:    BOP_COLUMNS,
    cellRenderer: BOP_CELL_RENDERER,

    title:     'BOP 工艺清单',
    titleIcon: '#icon-factory',
    newLabel:  '新建条目',

    extraToolbarBtns: [
      { id: 'btn-import-tc',    label: 'TC CSV 导入', btnStyle: 'ie', sepBefore: true,
        icon: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:4px"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>',
        onClick: () => openModal('modal-import-tc') },
      { id: 'btn-auto-link',    label: '建立实体关联', btnStyle: 'ie',
        icon: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:4px"><path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71"/></svg>',
        onClick: () => _openAutoLinkModal() },
      { id: 'btn-import-bop',   label: 'BOP Fork', btnStyle: 'ie',
        icon: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:4px"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>',
        onClick: () => _openForkModal() },
      { id: 'btn-import-gbop',  label: '从GBOP导入', btnStyle: 'ie',
        icon: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:4px"><polyline points="8 17 12 21 16 17"/><line x1="12" y1="3" x2="12" y2="21"/></svg>',
        onClick: () => _openImportGbopModal() },
      { id: 'btn-expand-all',   label: '展开', btnStyle: 'ie', sepBefore: true,
        icon: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:4px"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg>',
        onClick: () => _shell?._tree?.expandAll?.() },
      { id: 'btn-collapse-all', label: '折叠', btnStyle: 'ie',
        icon: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:4px"><polyline points="4 14 10 14 10 20"/><polyline points="20 10 14 10 14 4"/><line x1="10" y1="14" x2="3" y2="21"/><line x1="21" y1="3" x2="14" y2="10"/></svg>',
        onClick: () => _shell?._tree?.collapseAll?.() },
      { id: 'btn-lineage-view', label: '树形视图', btnStyle: 'ie', sepBefore: true,
        icon: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:4px"><rect x="2" y="9" width="4" height="6" rx="1"/><rect x="10" y="4" width="4" height="6" rx="1"/><rect x="10" y="14" width="4" height="6" rx="1"/><rect x="18" y="6" width="4" height="4" rx="1"/><rect x="18" y="14" width="4" height="4" rx="1"/><line x1="6" y1="12" x2="10" y2="7"/><line x1="6" y1="12" x2="10" y2="17"/><line x1="14" y1="7" x2="18" y2="8"/><line x1="14" y1="17" x2="18" y2="16"/></svg>',
        onClick: () => {
          if (!_currentVersion) { _toast('请先选择 BOP 版本', 'warn'); return; }
          const sel = _shell?.sidebar?._lists?.find(v => v.gid === _currentVersion);
          const tag = sel?.name || sel?.version_tag || _currentVersion;
          window.top.postMessage({
            type: 'tab:open',
            id: 'bop_lineage',
            params: { bop_version_gid: _currentVersion, version_tag: tag },
          }, '*');
        }},
    ],
    sidebarExtraItemHtml: (ver) =>
      `<span class="bop-mat-tag bop-mat-${ver.maturity}">${MATURITY_LABELS[ver.maturity] ?? ver.maturity ?? ''}</span>
       <span class="bop-takt-tag">${ver.takt_time ?? 60}s</span>`,

    sidebarOnCreate: () => _openNewVersionModal(),
    sidebarDisableInlineRename: true,
    sidebarOnContextMenu: (x, y, ver) => _showVerCtxMenu(x, y, ver),

    onSelect: (gid) => { _currentVersion = gid; load(); },

    onRowsChange: async (rows, extra) => {
      const { changedRow, action } = extra || {};
      if (action === 'edit' && changedRow?.gid) {
        const { gid, node_type, title, seq_no } = changedRow;
        try {
          await ListShell._cf(`/api/bop/entries/${gid}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ node_type, title, seq_no }),
          });
          await load();
        } catch (e) { _toast('保存失败: ' + e.message, 'error'); }
      } else if (!changedRow?.gid && changedRow?.title) {
        if (!_currentVersion) { _toast('请先选择 BOP 版本', 'warn'); return; }
        try {
          await ListShell._cf('/api/bop/entries', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ bop_version_gid: _currentVersion, node_type: 'operation', title: changedRow.title }),
          });
          await load();
        } catch (e) { _toast('创建失败: ' + e.message, 'error'); }
      }
    },

    enablePagination: true,
    pageSize: 200,

    extraContextItems: () => [
      { label: '添加子节点', action: 'add_child' },
      { label: '编辑节点',   action: 'edit' },
      { label: '删除节点',   action: 'del', danger: true },
    ],
    onContextAction: (action, row) => {
      if (action === 'add_child') _openAddChildModal(row.gid);
      if (action === 'edit')      _openEditModal(row);
      if (action === 'del')       _deleteEntry(row.gid);
    },
  });
}

// ── 刷新侧边栏 ───────────────────────────────────────────────────
async function _refreshSidebar() {
  await _loadBopVersions();
  _shell?.sidebar?._renderItems();
}

// ── BOP 版本侧边栏（自定义分组渲染）────────────────────────────
async function _loadBopVersions() {
  try {
    const json = await ListShell._cf('/api/bop/versions?include_archived=true');
    _bopVersions = json.data || [];
  } catch (e) {
    console.warn('[BOP] 加载版本列表失败:', e);
  }
}

function _renderBopSidebar(scrollEl) {
  scrollEl.innerHTML = '';

  // 按 version_family_gid 分组
  const familyMap = new Map(); // family_gid → { bop_name, archived: bool, versions: [] }
  for (const ver of _bopVersions) {
    const fgid = ver.version_family_gid || ver.gid;
    if (!familyMap.has(fgid)) {
      familyMap.set(fgid, {
        bop_name: ver.bop_name || '未命名BOP',
        archived: !!ver.archived_at,
        versions: [],
      });
    }
    const fam = familyMap.get(fgid);
    fam.versions.push(ver);
    // 如果族内任何版本未归档，则族不归档
    if (!ver.archived_at) fam.archived = false;
  }

  const active   = [...familyMap.entries()].filter(([, f]) => !f.archived);
  const archived = [...familyMap.entries()].filter(([, f]) =>  f.archived);

  // 渲染活动族
  for (const [fgid, fam] of active) {
    _renderFamilyGroup(scrollEl, fgid, fam, false);
  }

  // 已归档区
  if (archived.length) {
    const arcHdr = document.createElement('div');
    arcHdr.className = 'bop-arc-section-hdr';
    arcHdr.innerHTML = `
      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
           style="transition:transform .15s;transform:${_bopArcOpen ? 'rotate(90deg)' : ''}">
        <polyline points="9 18 15 12 9 6"/>
      </svg>
      <span>已归档 (${archived.length})</span>`;
    arcHdr.addEventListener('click', () => {
      _bopArcOpen = !_bopArcOpen;
      _shell?.sidebar?._renderItems();
    });
    scrollEl.appendChild(arcHdr);
    if (_bopArcOpen) {
      for (const [fgid, fam] of archived) {
        _renderFamilyGroup(scrollEl, fgid, fam, true);
      }
    }
  }
}

function _renderFamilyGroup(scrollEl, fgid, fam, isArchived) {
  const collapsed = _bopFamilyCollapsed.has(fgid);

  // Group header
  const hdr = document.createElement('div');
  hdr.className = 'bop-fam-hdr';
  hdr.dataset.familyGid = fgid;
  hdr.innerHTML = `
    <svg class="bop-fam-arrow${collapsed ? '' : ' open'}" width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
      <polyline points="9 18 15 12 9 6"/>
    </svg>
    <span class="bop-fam-name">${fam.bop_name}</span>
    <button class="bop-fam-arc-btn" title="${isArchived ? '解除归档' : '归档此BOP'}" data-family-gid="${fgid}" data-archived="${isArchived}">
      ${isArchived
        ? '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg>'
        : '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5"/><line x1="10" y1="12" x2="14" y2="12"/></svg>'
      }
    </button>`;

  // Toggle collapse on header click (not on button)
  hdr.addEventListener('click', e => {
    if (e.target.closest('.bop-fam-arc-btn')) return;
    if (_bopFamilyCollapsed.has(fgid)) _bopFamilyCollapsed.delete(fgid);
    else _bopFamilyCollapsed.add(fgid);
    _shell?.sidebar?._renderItems();
  });

  // Archive / unarchive button
  hdr.querySelector('.bop-fam-arc-btn').addEventListener('click', async e => {
    e.stopPropagation();
    if (isArchived) await _unarchiveFamily(fgid);
    else await _archiveFamily(fgid);
  });

  scrollEl.appendChild(hdr);

  if (collapsed) return;

  // Version items
  for (const ver of fam.versions) {
    const item = document.createElement('div');
    item.className = 'bop-ver-item' + (ver.gid === _currentVersion ? ' active' : '');
    item.dataset.gid = ver.gid;

    const isFrozen = !!ver.frozen_at;
    const statusLabel = isFrozen ? '冻结' : (ver.status === 'draft' ? '草稿' : (ver.status || ''));
    const statusCls   = isFrozen ? 'frozen' : 'draft';

    item.innerHTML = `
      <span class="bop-ver-dot ${isFrozen ? 'frozen' : ''}"></span>
      <span class="bop-ver-tag-text">${ver.version_tag}</span>
      <span class="bop-ver-status bop-vs-${statusCls}">${statusLabel}</span>
      <span class="bop-ver-takt">${ver.takt_time ?? 60}s</span>
      <button class="bop-ver-ctx-btn" title="更多操作" data-gid="${ver.gid}">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/></svg>
      </button>`;

    // Click to select version
    item.addEventListener('click', e => {
      if (e.target.closest('.bop-ver-ctx-btn')) return;
      _shell?.sidebar?._onSelect(ver.gid);
      _shell?.sidebar?._renderItems();
    });

    // Context menu button
    item.querySelector('.bop-ver-ctx-btn').addEventListener('click', e => {
      e.stopPropagation();
      _showVerCtxMenu(e.clientX, e.clientY, ver, fgid, fam.bop_name);
    });

    scrollEl.appendChild(item);
  }
}

// ── 版本右键/更多菜单 ────────────────────────────────────────────
function _showVerCtxMenu(x, y, ver, familyGid, familyName) {
  document.querySelectorAll('.ls-ctx-menu').forEach(m => m.remove());
  const menu = document.createElement('div');
  menu.className = 'ls-ctx-menu';
  const add = (text, cls, fn) => {
    const el = document.createElement('div');
    el.className = 'ls-ctx-item' + (cls ? ` ${cls}` : '');
    el.textContent = text;
    el.addEventListener('click', () => { menu.remove(); fn(); });
    menu.appendChild(el);
  };
  const sep = () => { const d = document.createElement('div'); d.className = 'ls-ctx-sep'; menu.appendChild(d); };

  add('编辑版本属性', '', () => _openEditVersionModal(ver));
  if (!ver.frozen_at) {
    add('冻结此版本', '', () => _freezeVersion(ver));
  }
  sep();
  add(`在「${familyName}」新建版本`, '', () => _openNewVersionInFamily(familyGid, familyName, ver));
  sep();
  add('删除版本', 'danger', () => _deleteVersion(ver));
  sep();
  if (_isSuperAdmin()) {
    add('【超管】清空所有条目（软删）', 'warn', () => _purgeVersionEntries(ver, 'soft'));
    add('【超管】清空所有条目（硬删）', 'danger', () => _purgeVersionEntries(ver, 'hard'));
  }

  menu.style.left = x + 'px';
  menu.style.top  = y + 'px';
  document.body.appendChild(menu);
  const close = e => {
    if (!menu.contains(e.target)) { menu.remove(); document.removeEventListener('click', close); }
  };
  setTimeout(() => document.addEventListener('click', close), 10);
}

async function _freezeVersion(ver) {
  if (!confirm(`确认冻结版本「${ver.version_tag}」？冻结后不可编辑。`)) return;
  try {
    await ListShell._cf(`/api/bop/versions/${ver.gid}/freeze`, { method: 'POST' });
    await _refreshSidebar();
    _toast(`版本「${ver.version_tag}」已冻结`, 'success');
  } catch (e) { _toast('冻结失败: ' + e.message, 'error'); }
}

async function _archiveFamily(familyGid) {
  if (!confirm('确认归档此 BOP 的所有版本？归档后不再显示在主列表中，可在已归档区恢复。')) return;
  try {
    await ListShell._cf(`/api/bop/version-families/${familyGid}/archive`, { method: 'POST' });
    if (_bopVersions.find(v => (v.version_family_gid || v.gid) === familyGid && v.gid === _currentVersion)) {
      _currentVersion = null;
      _shell?.setRows([]);
    }
    _bopArcOpen = true;
    await _refreshSidebar();
    _toast('已归档', 'success');
  } catch (e) { _toast('归档失败: ' + e.message, 'error'); }
}

async function _unarchiveFamily(familyGid) {
  try {
    await ListShell._cf(`/api/bop/version-families/${familyGid}/archive`, { method: 'DELETE' });
    await _refreshSidebar();
    _toast('已恢复', 'success');
  } catch (e) { _toast('恢复失败: ' + e.message, 'error'); }
}

// ── 新建版本 Modal 初始化 ─────────────────────────────────────────
let _projectsForModal = [];
let _factoriesForModal = [];

async function _openNewVersionModal(prefillFamilyGid = null, prefillProjectGid = null) {
  // 加载项目列表（缓存）
  if (_projectsForModal.length === 0) {
    try {
      const res = await ListShell._cf('/api/projects?limit=200');
      _projectsForModal = (res.data || []).filter(p => !p.is_deleted && p.project_type !== 'gbop');
    } catch (_) { _projectsForModal = []; }
  }
  // 加载工厂列表（缓存）
  if (_factoriesForModal.length === 0) {
    try {
      const res = await ListShell._cf('/api/bop/factories');
      _factoriesForModal = res.data || [];
    } catch (_) { _factoriesForModal = []; }
  }

  // 填充项目下拉
  const projSel = document.getElementById('inp-ver-project');
  projSel.innerHTML = '<option value="">— 请选择项目 —</option>';
  for (const p of _projectsForModal) {
    const opt = document.createElement('option');
    opt.value = p.gid;
    opt.dataset.factoryGid   = p.factory_gid || '';
    opt.dataset.projectName  = p.name || p.gid;
    opt.dataset.jph          = p.jph != null ? p.jph : '';
    const fac = _factoriesForModal.find(f => f.gid === p.factory_gid);
    opt.dataset.factoryName  = fac ? (fac.name || fac.gid) : '';
    opt.textContent = p.name || p.gid;
    projSel.appendChild(opt);
  }

  // 清空字段
  document.getElementById('inp-ver-tag').value           = '';
  document.getElementById('inp-ver-bop-suffix').value    = '';
  document.getElementById('inp-ver-factory').value       = '';
  document.getElementById('inp-ver-factory-display').value = '';
  document.getElementById('inp-ver-bop-name').value      = '';
  document.getElementById('inp-ver-takt').value          = '';

  // 族 GID（在族内新建版本时传入）
  const familyGidEl  = document.getElementById('inp-ver-family-gid');
  const familyHintEl = document.getElementById('inp-ver-family-hint');
  const suffixEl     = document.getElementById('inp-ver-bop-suffix');
  if (prefillFamilyGid) {
    familyGidEl.value = prefillFamilyGid;
    familyHintEl.classList.remove('hidden');
    suffixEl.disabled = true;
  } else {
    familyGidEl.value = '';
    familyHintEl.classList.add('hidden');
    suffixEl.disabled = false;
  }

  // 预选项目（在族内新建版本时继承项目）
  if (prefillProjectGid) {
    projSel.value = prefillProjectGid;
    projSel.dispatchEvent(new Event('change'));
  } else {
    _updateBopNamePreview();
    _refreshPbomVersionList('');
  }

  openModal('modal-new-version');
}

function _updateBopNamePreview() {
  const projSel    = document.getElementById('inp-ver-project');
  const tag        = (document.getElementById('inp-ver-tag').value       || '').trim();
  const suffix     = (document.getElementById('inp-ver-bop-suffix').value || '').trim();
  const familyGid  = document.getElementById('inp-ver-family-gid').value.trim();
  const previewEl  = document.getElementById('inp-ver-bop-preview-text');
  const hiddenName = document.getElementById('inp-ver-bop-name');

  if (familyGid) {
    previewEl.textContent = '（继承版本族名称，无需生成）';
    hiddenName.value = '';
    return;
  }

  const selectedOpt = projSel?.options[projSel.selectedIndex];
  const projName    = selectedOpt?.dataset?.projectName || '';

  if (!projName) {
    previewEl.textContent = '请先选择项目';
    hiddenName.value = '';
    return;
  }

  const now = new Date();
  const dateStr = now.getFullYear().toString()
    + String(now.getMonth() + 1).padStart(2, '0')
    + String(now.getDate()).padStart(2, '0');

  const parts = [projName];
  if (tag)    parts.push(tag);
  parts.push(dateStr);
  if (suffix) parts.push(suffix);

  const name = parts.join(' · ');
  previewEl.textContent = name;
  hiddenName.value = name;
}

function _openNewVersionInFamily(familyGid, familyName, baseVer) {
  _openNewVersionModal(familyGid, baseVer?.project_gid || null);
}

// ── 新建版本 ─────────────────────────────────────────────────────
async function _refreshPbomVersionList(projectGid) {
  const sel  = document.getElementById('inp-ver-pbom');
  const hint = document.getElementById('inp-ver-pbom-hint');
  if (!sel) return;
  sel.innerHTML = '<option value="">— 加载中… —</option>';
  if (!projectGid) {
    sel.innerHTML = '<option value="">— 请先选择项目 —</option>';
    if (hint) hint.style.display = 'none';
    return;
  }
  try {
    const res = await ListShell._cf(`/api/bop/pbom-versions?project_gid=${encodeURIComponent(projectGid)}`);
    const versions = res?.data || [];
    if (!versions.length) {
      sel.innerHTML = '<option value="">（无已就绪 PBOM 版本）</option>';
      if (hint) hint.style.display = '';
    } else {
      sel.innerHTML = '<option value="">— 请选择 PBOM 版本 —</option>';
      versions.forEach(v => {
        const opt = document.createElement('option');
        opt.value = v.gid;
        opt.textContent = v.title || v.gid;
        sel.appendChild(opt);
      });
      if (hint) hint.style.display = 'none';
    }
  } catch {
    sel.innerHTML = '<option value="">（加载失败）</option>';
  }
}

async function _createVersion() {
  const tag       = document.getElementById('inp-ver-tag').value.trim();
  const bopName   = document.getElementById('inp-ver-bop-name').value.trim();
  const familyGid = document.getElementById('inp-ver-family-gid').value.trim() || null;
  const takt      = document.getElementById('inp-ver-takt').value !== '' ? parseFloat(document.getElementById('inp-ver-takt').value) : null;
  const project   = document.getElementById('inp-ver-project').value.trim() || null;
  const factory   = document.getElementById('inp-ver-factory').value.trim() || null;
  const pbomGid   = document.getElementById('inp-ver-pbom')?.value.trim() || null;
  if (!project)  { _toast('请先选择所属项目', 'warn'); return; }
  if (!tag)      { _toast('版本标签不能为空', 'warn'); return; }
  if (!bopName)  { _toast('BOP名称生成失败，请检查项目和版本标签', 'warn'); return; }
  try {
    await ListShell._cf('/api/bop/versions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        version_tag: tag, bop_name: bopName, version_family_gid: familyGid,
        status: 'active', takt_time: takt, project_gid: project, factory_gid: factory,
        pbom_version_gid: pbomGid,
      }),
    });
    // Reset modal
    closeModal('modal-new-version');
    document.getElementById('inp-ver-tag').value = '';
    document.getElementById('inp-ver-bop-suffix').value = '';
    document.getElementById('inp-ver-bop-name').value = '';
    document.getElementById('inp-ver-factory-display').value = '';
    document.getElementById('inp-ver-factory').value = '';
    document.getElementById('inp-ver-project').value = '';
    document.getElementById('inp-ver-family-gid').value = '';
    document.getElementById('inp-ver-family-hint').classList.add('hidden');
    document.getElementById('inp-ver-bop-preview-text').textContent = '请先选择项目';
    const pbomSel = document.getElementById('inp-ver-pbom');
    if (pbomSel) pbomSel.innerHTML = '<option value="">— 请先选择项目 —</option>';
    await _refreshSidebar();
    _toast('版本创建成功', 'success');
  } catch (e) { _toast('创建失败: ' + e.message, 'error'); }
}

// ── 编辑版本属性 ─────────────────────────────────────────────────
function _openEditVersionModal(ver) {
  document.getElementById('inp-editver-gid').value      = ver.gid;
  document.getElementById('inp-editver-bop-name').value = ver.bop_name || '';
  document.getElementById('inp-editver-tag').value      = ver.name || ver.version_tag || '';
  document.getElementById('inp-editver-maturity').value = ver.maturity || 'concept';
  document.getElementById('inp-editver-takt').value     = ver.takt_time ?? 60;
  document.getElementById('inp-editver-status').value   = ver.status || 'draft';
  openModal('modal-edit-version');
}

async function _saveEditVersion() {
  const gid      = document.getElementById('inp-editver-gid').value;
  const bopName  = document.getElementById('inp-editver-bop-name').value.trim();
  const tag      = document.getElementById('inp-editver-tag').value.trim();
  const maturity = document.getElementById('inp-editver-maturity').value;
  const takt     = parseFloat(document.getElementById('inp-editver-takt').value) || 60;
  const status   = document.getElementById('inp-editver-status').value;
  if (!tag) { _toast('版本标签不能为空', 'warn'); return; }
  try {
    await ListShell._cf(`/api/bop/versions/${gid}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ version_tag: tag, bop_name: bopName, maturity, takt_time: takt, status }),
    });
    closeModal('modal-edit-version');
    await _refreshSidebar();
    _toast('版本属性已保存', 'success');
  } catch (e) { _toast('保存失败: ' + e.message, 'error'); }
}

// ── 删除版本 ─────────────────────────────────────────────────────
function _isSuperAdmin() {
  const user = window.parent?._authUser || window._authUser;
  return (user?.role || user?.system_role) === 'super_admin';
}

async function _purgeVersionEntries(ver, mode) {
  const modeLabel = mode === 'hard' ? '硬删（永久，不可恢复）' : '软删（可通过数据库恢复）';
  if (!confirm(`确认对版本「${ver.version_tag}」执行 ${modeLabel}？\n将清空全部条目及关联实体记录。`)) return;
  if (mode === 'hard' && !confirm('⚠️ 再次确认：硬删将永久清除所有数据，是否继续？')) return;
  try {
    const res = await ListShell._cf(`/api/bop/versions/${ver.gid}/purge-entries`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode }),
    });
    const c = res.counts || {};
    const entityTotal = Object.values(c.entities || {}).reduce((a, b) => a + b, 0);
    _toast(`清空完成：${c.entries || 0} 条条目 / ${c.links || 0} 个关联 / ${entityTotal} 条实体`, 'success');
    if (_currentVersion === ver.gid) _shell?.setRows([]);
  } catch (e) { _toast('清空失败: ' + e.message, 'error'); }
}

async function _deleteVersion(ver) {
  if (!confirm(`确认删除版本「${ver.name || ver.version_tag}」？此操作不可恢复。`)) return;
  try {
    await ListShell._cf(`/api/lists/${ver.gid}`, { method: 'DELETE' });
    if (_currentVersion === ver.gid) { _currentVersion = null; _shell.setRows([]); }
    await _refreshSidebar();
    _toast('版本已删除', 'success');
  } catch (e) { _toast('删除失败: ' + e.message, 'error'); }
}

// ── 新建根节点 ───────────────────────────────────────────────────
async function _createRoot() {
  if (!_currentVersion) { _toast('请先选择 BOP 版本', 'warn'); return; }
  const _frozenVerR = _bopVersions.find(v => v.gid === _currentVersion);
  if (_frozenVerR?.frozen_at) { _toast('版本已冻结，不允许修改', 'warn'); return; }
  const node_type = document.getElementById('inp-root-type').value;
  const title     = document.getElementById('inp-root-title').value.trim();
  const seq_no    = parseInt(document.getElementById('inp-root-seq').value) || 0;
  if (!title) { _toast('名称不能为空', 'warn'); return; }
  try {
    await ListShell._cf('/api/bop/entries', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bop_version_gid: _currentVersion, node_type, title, seq_no }),
    });
    closeModal('modal-new-root');
    document.getElementById('inp-root-title').value = '';
    await load();
    _toast('根节点创建成功', 'success');
  } catch (e) { _toast('创建失败: ' + e.message, 'error'); }
}

// ── 添加子节点 ───────────────────────────────────────────────────
function _openAddChildModal(parentGid) {
  document.getElementById('inp-child-parent-gid').value = parentGid;
  document.getElementById('inp-child-title').value      = '';
  document.getElementById('inp-child-vpps-desc').value   = '';
  document.getElementById('inp-child-seq').value        = '0';
  openModal('modal-add-child');
}

async function _createChild() {
  if (!_currentVersion) return;
  const _frozenVer = _bopVersions.find(v => v.gid === _currentVersion);
  if (_frozenVer?.frozen_at) { _toast('版本已冻结，不允许修改', 'warn'); return; }
  const parentGid = document.getElementById('inp-child-parent-gid').value;
  const node_type = document.getElementById('inp-child-type').value;
  const title     = document.getElementById('inp-child-title').value.trim();
  const vpps      = document.getElementById('inp-child-vpps').value.trim() || undefined;
  const vpps_desc = document.getElementById('inp-child-vpps-desc').value.trim() || undefined;
  const seq_no    = parseInt(document.getElementById('inp-child-seq').value) || 0;
  if (!title) { _toast('名称不能为空', 'warn'); return; }
  try {
    await ListShell._cf('/api/bop/entries', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bop_version_gid: _currentVersion, parent_bop_gid: parentGid,
                             node_type, title, vpps, vpps_desc, seq_no }),
    });
    closeModal('modal-add-child');
    await load();
    _toast('子节点创建成功', 'success');
  } catch (e) { _toast('创建失败: ' + e.message, 'error'); }
}

// ── 编辑节点 ─────────────────────────────────────────────────────
function _openEditModal(row) {
  document.getElementById('inp-edit-gid').value       = row.gid;
  document.getElementById('inp-edit-type').value      = row.node_type || 'operation';
  document.getElementById('inp-edit-title').value     = row.title || '';
  document.getElementById('inp-edit-vpps').value      = row.vpps || '';
  document.getElementById('inp-edit-vpps-desc').value = row.vpps_desc || '';
  document.getElementById('inp-edit-seq').value       = row.seq_no ?? 0;
  openModal('modal-edit-entry');
}

async function _saveEditEntry() {
  const gid = document.getElementById('inp-edit-gid').value;
  if (!gid) return;
  const _frozenVerE = _bopVersions.find(v => v.gid === _currentVersion);
  if (_frozenVerE?.frozen_at) { _toast('版本已冻结，不允许修改', 'warn'); return; }
  const title      = document.getElementById('inp-edit-title').value.trim();
  const node_type  = document.getElementById('inp-edit-type').value;
  const vpps       = document.getElementById('inp-edit-vpps').value.trim() || undefined;
  const vpps_desc  = document.getElementById('inp-edit-vpps-desc').value.trim() || undefined;
  const seq_no     = parseInt(document.getElementById('inp-edit-seq').value) || 0;
  if (!title) { _toast('名称不能为空', 'warn'); return; }
  try {
    await ListShell._cf(`/api/bop/entries/${gid}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ node_type, title, vpps, vpps_desc, seq_no }),
    });
    closeModal('modal-edit-entry');
    await load();
    _toast('已保存', 'success');
  } catch (e) { _toast('保存失败: ' + e.message, 'error'); }
}

// ── 删除节点 ─────────────────────────────────────────────────────
async function _deleteEntry(gid) {
  if (!confirm('确定删除该节点？其子节点的父级引用将变为空。')) return;
  const _frozenVerD = _bopVersions.find(v => v.gid === _currentVersion);
  if (_frozenVerD?.frozen_at) { _toast('版本已冻结，不允许删除', 'warn'); return; }
  try {
    await ListShell._cf(`/api/bop/entries/${gid}`, { method: 'DELETE' });
    await load();
    _toast('已删除', 'success');
  } catch (e) { _toast('删除失败: ' + e.message, 'error'); }
}

// ── TC CSV 导入 ──────────────────────────────────────────────────
// TC CSV 列定义（0-indexed）：
// ── 零组件类型对照表（CSV中文名 → DB node_type，参考 docs/bop/db csv ui.xlsx）──
// 级别参考（AI00_Level）：
//   0: factory_bop            总装工厂BOP
//   1: line_process            总装线体工艺
//   2: station_process         总装工位工艺
//   3: operator_process        总装岗位工艺
//   4: man / station_factory / process
//   5: equipment_factory / tool_factory / equipment_need / fixture_factory
//      operation / issue / standard_task / non_standard_task / contral_plan / process_chart
//   6: part / non_standard_part / standard_part / support_material / tool_need / fixture_need
const _TC_TYPE_MAP = {
  '总装工厂BOP':        'factory_bop',
  '总装产品BOP':        'factory_bop',
  '总装产品bop':        'factory_bop',
  '总装BOP':           'factory_bop',
  '工厂BOP':           'factory_bop',
  '产品BOP':           'factory_bop',
  'BOP':               'factory_bop',
  '总装线体工艺':        'line_process',
  '产线工艺':           'line_process',
  '总装工位工艺':        'station_process',
  '工位工艺':           'station_process',
  '总装岗位工艺':        'operator_process',
  '人':                'man',
  '工位':              'station_factory',
  '设备':              'equipment_need',
  '设备（现有）':        'equipment_factory',
  '设备（需求）':        'equipment_need',
  '设备需求':           'equipment_need',
  '工具（现有）':        'tool_factory',
  '工具':              'tool_need',
  '工具（需求）':        'tool_need',
  '工装（现有）':        'fixture_factory',
  '工装':              'fixture_need',
  '工装（需求）':        'fixture_need',
  '总装工序':           'process',
  '工序':              'process',
  '总装操作（Product）': 'operation',  // 全角括号
  '总装操作(Product)':  'operation',  // 半角括号
  '总装操作（product）': 'operation', // 全角小写
  '总装操作(product)':  'operation',  // 半角小写
  '总装操作':           'operation',  // 无括号
  '问题':              'issue',
  '标准任务':           'standard_task',
  '非标任务':           'non_standard_task',
  '控制计划':           'contral_plan',
  '工艺卡':             'process_chart',
  '零部件':             'part',
  '非标件':             'non_standard_part',
  '标准件':             'standard_part',
  '辅料':              'support_material',
  '地面高度(现有）':    'floor_height_factory',
  '人机姿态':          'jack_pos',
};

// AI00 逻辑分级（node_type → ai00_level，与后端 _AI00_LEVEL 保持一致）
const _AI00_LEVEL_MAP = {
  factory_bop: 0,
  line_process: 1, station_process: 2, operator_process: 3,
  man: 4, station_factory: 4, process: 4,
  equipment_factory: 5, tool_factory: 5, equipment_need: 5, fixture_factory: 5,
  operation: 5, issue: 5, standard_task: 5, non_standard_task: 5,
  contral_plan: 5, process_chart: 5, knowledge: 5, rule: 5,
  floor_height_factory: 5,
  part: 6, non_standard_part: 6, standard_part: 6,
  support_material: 6, tool_need: 6, fixture_need: 6,
  jack_pos: 6,
};

//  0=Level,  1=BOM行,      2=零组件类型,  3=零组件描述,  4=零组件ID,
//  5=零组件名称, 6=父级,   7=用户,        8=VPPS,        9=VPPS(零件),
//  10=VPPS描述,  11=父级VPPS, 12=上级模块描述, 13=数量,  14=扭矩, 15=等级
//  meta 中存储无独立 DB 列的 CSⅤ 原始列（csv_* 前缀），前端 UI 通过列视图查看
function _parseCsvLine(line) {
  // 正确处理双引号包裹的 CSV 字段（含逗号或换行的情况）
  const cols = [];
  let current = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      // 双引号转义："" → "
      if (inQuotes && i + 1 < line.length && line[i + 1] === '"') {
        current += '"';
        i++;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (ch === ',' && !inQuotes) {
      cols.push(current.trim());
      current = '';
    } else {
      current += ch;
    }
  }
  cols.push(current.trim());
  return cols;
}

function _parseTcCsv(text) {
  // 先处理引号内换行：逐字符扫描，引号内的换行符替换为空格
  let cleaned = '';
  let inQ = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (ch === '"') {
      inQ = !inQ;
      cleaned += ch;
    } else if ((ch === '\n' || ch === '\r') && inQ) {
      cleaned += ' ';  // 引号内的换行替换为空格
    } else {
      cleaned += ch;
    }
  }

  const lines = cleaned.split(/\r?\n/).filter(l => l.trim());
  if (!lines.length) return [];
  // 首行含非数字开头则为表头，跳过
  const dataLines = lines[0].match(/^\D/) ? lines.slice(1) : lines;
  const totalRaw = dataLines.length;
  // 过滤统计
  const _stats = { pfmea: 0, empty: 0, unknown: 0, unknownTypes: {} };

  const result = dataLines.map((line, i) => {
    const cols = _parseCsvLine(line);
    const lvRaw = parseInt(cols[0]);
    const lv    = isNaN(lvRaw) ? 0 : lvRaw;

    // CSV 列映射（对照 docs/bop/db csv ui.xlsx DB sheet）：
    // col[0] = Level
    // col[1] = BOM行（完整引用，如 AS-000477735/01;1-X11-BOP (视图)）
    // col[2] = 零组件类型（TC原始类型名）
    // col[3] = 零组件ID（如 AS-000477735）
    // col[4] = 零组件名称（title）
    // col[5] = 父级（父节点 BOM行，匹配同批 col[1] 确定 parent_bop_gid）
    // col[6] = 零组件版本所有权用户
    // col[8] = VPPS
    // col[10] = VPPS 描述
    const tcType = (cols[2] || '').trim();
    const title  = (cols[4] || '').trim();

    // ── 自动过滤 ────────────────────────────────────────────────
    if (tcType.includes('PFMEA') || title.includes('PFMEA')) { _stats.pfmea++; return null; }
    if (lv > 0 && !((cols[1] || '').trim()) && !title)       { _stats.empty++; return null; }

    const node_type = _TC_TYPE_MAP[tcType] || '';
    if (!node_type) {
      _stats.unknown++;
      if (tcType) _stats.unknownTypes[tcType] = (_stats.unknownTypes[tcType] || 0) + 1;
      return null;
    }

    const bom_row_label    = (cols[1] || '').trim() || null;
    const bom_row_id       = (cols[3] || '').trim() || null;
    const parent_bop_label = (cols[5] || '').trim() || null;
    const bom_row_owner    = (cols[6] || '').trim() || null;
    const vpps             = (cols[8] || '').trim() || null;
    const vpps_desc        = (cols[10] || '').trim() || null;
    const ai00_level       = _AI00_LEVEL_MAP[node_type] ?? null;

    const meta = { tc_type: tcType || '' };
    const mappedCols = new Set([0, 1, 2, 3, 4, 5, 6, 8, 10]);
    for (let ci = 0; ci < cols.length; ci++) {
      if (mappedCols.has(ci)) continue;
      const v = (cols[ci] || '').trim();
      if (v) meta[`csv_col${ci}`] = v;
    }

    return {
      _level: lv, node_type, ai00_level, meta: JSON.stringify(meta),
      title: title || `节点${i + 1}`,
      bom_row_id, bom_row_label, bom_row_owner, parent_bop_label,
      vpps, vpps_desc,
      seq_no: i,
    };
  }).filter(Boolean);
  result._skipped = totalRaw - result.length;
  result._stats   = _stats;
  return result;
}

function _renderTcPreview(rows) {
  const preview = document.getElementById('tc-preview');
  const tableEl = document.getElementById('tc-preview-table');
  const countEl = document.getElementById('tc-preview-count');
  if (!rows.length) { preview.classList.add('hidden'); return; }
  tableEl.innerHTML = `<table class="bop-preview-table">
    <thead><tr><th>层级</th><th>类型</th><th>BOM行标签</th><th>名称</th><th>零件号</th></tr></thead>
    <tbody>${rows.slice(0, 20).map(r =>
      `<tr><td>${r._level}</td><td>${NODE_TYPE_LABELS[r.node_type] || r.node_type}</td><td>${ListShell._esc(r.bom_row_label || '')}</td><td>${ListShell._esc(r.title)}</td><td>${ListShell._esc(r.bom_row_id || '')}</td></tr>`
    ).join('')}</tbody></table>`;

  const s = rows._stats || {};
  const skipped = rows._skipped || 0;
  let detail = `共 ${rows.length} 行，已跳过 ${skipped} 行`;
  if (s.pfmea)   detail += `（PFMEA: ${s.pfmea}）`;
  if (s.empty)   detail += `（空行: ${s.empty}）`;
  if (s.unknown) {
    const topTypes = Object.entries(s.unknownTypes || {})
      .sort((a, b) => b[1] - a[1]).slice(0, 5)
      .map(([t, n]) => `"${t}"×${n}`).join('、');
    detail += `（未识别类型: ${s.unknown} 行，前5类：${topTypes}）`;
  }
  countEl.textContent = detail;
  preview.classList.remove('hidden');
  document.getElementById('btn-confirm-import-tc').disabled = false;
}

async function _importTc() {
  if (!_currentVersion) { _toast('请先在左侧列表选择一个 BOP 版本', 'warn'); return; }
  if (!_parsedTcRows.length) { _toast('请先选择 CSV 文件', 'warn'); return; }
  try {
    const json = await ListShell._cf(`/api/bop/versions/${_currentVersion}/import-tc`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rows: _parsedTcRows }),
    });
    closeModal('modal-import-tc');
    await load();
    const skipMsg = json.skipped ? `，跳过重复 ${json.skipped} 行` : '';
    _toast(`导入成功，共 ${json.count} 个节点${skipMsg}`, 'success');
  } catch (e) { _toast('导入失败: ' + e.message, 'error'); }
}

// ── BOP Fork ─────────────────────────────────────────────────────

// 系统预设（前端内置，不存 DB）
const _FORK_SYSTEM_PRESETS = {
  __new_model: {
    name: '新车型衍生',
    include_node_types: null,
    field_rules: { title: 'inherit', vpps: 'inherit', bom_row_id: 'reset', bom_row_label: 'reset', bom_row_owner: 'reset', owner_gid: 'reset', gbop_source_gid: 'reset' },
    meta_key_rules: {},
  },
  __iteration: {
    name: '版本迭代',
    include_node_types: null,
    field_rules: {},   // 全部默认 inherit
    meta_key_rules: {},
  },
  __structure: {
    name: '结构复制',
    include_node_types: null,
    field_rules: { title: 'inherit', vpps: 'inherit', bom_row_id: 'reset', bom_row_label: 'reset', bom_row_owner: 'reset', owner_gid: 'reset', gbop_source_gid: 'reset', meta: 'reset' },
    meta_key_rules: { '*': 'reset' },
  },
  __full_clone: {
    name: '完整克隆',
    include_node_types: null,
    field_rules: {},
    meta_key_rules: {},
  },
};

// 用户可控字段（标签映射）
const _FORK_FIELD_LABELS = {
  title:             '名称 (title)',
  vpps:              'VPPS 壳',
  bom_row_id:        'BOM行ID',
  bom_row_label:     'BOM行标签',
  bom_row_owner:     'BOM所有者',
  parent_bop_label:  '父节点标签',
  owner_gid:         '负责人',
  gbop_source_gid:   'GBOP来源',
  meta:              'Meta扩展字段',
};

// 常用 node_type 列表（勾选过滤用）
const _FORK_NODE_TYPES = [
  'factory_bop', 'line_process', 'station_process', 'operator_process',
  'man', 'station_factory', 'process',
  'equipment_factory', 'tool_factory', 'fixture_factory',
  'equipment_need', 'tool_need', 'fixture_need',
  'operation', 'issue', 'standard_task', 'non_standard_task',
  'contral_plan', 'process_chart', 'knowledge', 'rule',
  'floor_height_factory', 'jack_pos',
  'part', 'non_standard_part', 'standard_part', 'support_material',
];

let _forkCustomPresets = [];   // DB 自定义预设缓存
let _forkSelectedPresetGid = null;  // 当前选中的自定义预设 gid

function _buildForkFieldRulesUI() {
  const container = document.getElementById('fork-field-rules');
  container.innerHTML = '';
  Object.entries(_FORK_FIELD_LABELS).forEach(([field, label]) => {
    const row = document.createElement('div');
    row.className = 'fork-field-row';
    row.innerHTML = `<span>${label}</span>
      <select data-fork-field="${field}">
        <option value="inherit">inherit</option>
        <option value="reset">reset</option>
      </select>`;
    container.appendChild(row);
  });
}

function _buildForkNodeTypesUI() {
  const container = document.getElementById('fork-node-types');
  container.innerHTML = '';
  _FORK_NODE_TYPES.forEach(nt => {
    const chip = document.createElement('span');
    chip.className = 'fork-nt-chip';
    chip.dataset.nt = nt;
    chip.textContent = NODE_TYPE_LABELS[nt] || nt;
    chip.addEventListener('click', () => chip.classList.toggle('active'));
    container.appendChild(chip);
  });
}

function _getForkConfig() {
  // 节点类型过滤
  const activeNts = [...document.querySelectorAll('.fork-nt-chip.active')].map(c => c.dataset.nt);
  const includeNodeTypes = activeNts.length > 0 ? activeNts : null;

  // 字段规则
  const fieldRules = {};
  document.querySelectorAll('[data-fork-field]').forEach(sel => {
    if (sel.value === 'reset') fieldRules[sel.dataset.forkField] = 'reset';
    // inherit 是默认，不需要显式写
  });

  return { includeNodeTypes, fieldRules };
}

function _applyForkPreset(preset) {
  // 字段规则
  document.querySelectorAll('[data-fork-field]').forEach(sel => {
    const rule = (preset.field_rules || {})[sel.dataset.forkField];
    sel.value = rule || 'inherit';
  });
  // 节点类型
  document.querySelectorAll('.fork-nt-chip').forEach(chip => {
    const nts = preset.include_node_types;
    if (nts && nts.length > 0) {
      chip.classList.toggle('active', nts.includes(chip.dataset.nt));
    } else {
      chip.classList.remove('active');
    }
  });
}

async function _openForkModal() {
  if (!_currentVersion) { _toast('请先选择目标 BOP 版本', 'warn'); return; }

  // 填充来源版本选择
  const srcSel = document.getElementById('inp-fork-src-version');
  srcSel.innerHTML = '<option value="">-- 选择来源 BOP 版本 --</option>';
  // 填充版本族选择
  const famSel = document.getElementById('inp-fork-family');
  famSel.innerHTML = '<option value="">-- 自成新版本族 --</option>';
  // 重置表单
  document.getElementById('inp-fork-tag').value = '';
  document.getElementById('inp-fork-bop-name').value = '';
  document.getElementById('inp-fork-change-note').value = '';
  document.getElementById('inp-fork-preset').value = '';
  _forkSelectedPresetGid = null;
  document.getElementById('btn-fork-delete-preset').style.display = 'none';

  try {
    const json = await ListShell._cf('/api/bop/versions');
    const vers = json.data || [];
    vers.forEach(v => {
      const opt = document.createElement('option');
      opt.value = v.gid;
      opt.textContent = `${v.bop_name || v.version_tag} · ${v.version_tag} (${MATURITY_LABELS[v.maturity] || v.maturity})`;
      srcSel.appendChild(opt);
    });
    // 版本族（以 version_family_gid 为键，取第一个 bop_name）
    const families = {};
    vers.forEach(v => {
      const fgid = v.version_family_gid || v.gid;
      if (!families[fgid]) families[fgid] = v.bop_name || v.version_tag;
    });
    Object.entries(families).forEach(([fgid, fname]) => {
      const opt = document.createElement('option');
      opt.value = fgid;
      opt.textContent = fname;
      famSel.appendChild(opt);
    });
  } catch (_) {}

  // 加载自定义预设
  try {
    const json = await ListShell._cf('/api/bop/fork-presets');
    _forkCustomPresets = json.data || [];
    _refreshForkPresetList();
  } catch (_) { _forkCustomPresets = []; }

  // 构建字段规则 UI
  _buildForkFieldRulesUI();
  _buildForkNodeTypesUI();

  // 预设切换监听
  const presetSel = document.getElementById('inp-fork-preset');
  presetSel.onchange = () => {
    const val = presetSel.value;
    document.getElementById('btn-fork-delete-preset').style.display = 'none';
    _forkSelectedPresetGid = null;
    if (!val) return;
    if (_FORK_SYSTEM_PRESETS[val]) {
      _applyForkPreset(_FORK_SYSTEM_PRESETS[val]);
    } else {
      // 自定义预设
      const preset = _forkCustomPresets.find(p => p.gid === val);
      if (preset) {
        _forkSelectedPresetGid = preset.gid;
        document.getElementById('btn-fork-delete-preset').style.display = '';
        _applyForkPreset(preset);
      }
    }
  };

  openModal('modal-fork-bop');
}

function _refreshForkPresetList() {
  const group = document.getElementById('fork-preset-custom-group');
  group.innerHTML = '';
  _forkCustomPresets.forEach(p => {
    const opt = document.createElement('option');
    opt.value = p.gid;
    opt.textContent = p.name;
    group.appendChild(opt);
  });
}

async function _saveForkPreset() {
  const { includeNodeTypes, fieldRules } = _getForkConfig();
  const name = prompt('预设名称：');
  if (!name) return;
  try {
    const body = { name, include_node_types: includeNodeTypes, field_rules: fieldRules, meta_key_rules: {} };
    const json = await ListShell._cf('/api/bop/fork-presets', { method: 'POST', body: JSON.stringify(body) });
    _forkCustomPresets.push(json.data);
    _refreshForkPresetList();
    // 选中新保存的预设
    document.getElementById('inp-fork-preset').value = json.data.gid;
    _forkSelectedPresetGid = json.data.gid;
    document.getElementById('btn-fork-delete-preset').style.display = '';
    _toast('预设已保存', 'success');
  } catch (e) { _toast('保存失败: ' + e.message, 'error'); }
}

async function _deleteForkPreset() {
  if (!_forkSelectedPresetGid) return;
  if (!confirm('确认删除此预设？')) return;
  try {
    await ListShell._cf(`/api/bop/fork-presets/${_forkSelectedPresetGid}`, { method: 'DELETE' });
    _forkCustomPresets = _forkCustomPresets.filter(p => p.gid !== _forkSelectedPresetGid);
    _forkSelectedPresetGid = null;
    _refreshForkPresetList();
    document.getElementById('inp-fork-preset').value = '';
    document.getElementById('btn-fork-delete-preset').style.display = 'none';
    _toast('预设已删除', 'success');
  } catch (e) { _toast('删除失败: ' + e.message, 'error'); }
}

async function _executeFork() {
  const srcGid  = document.getElementById('inp-fork-src-version').value;
  const tag     = document.getElementById('inp-fork-tag').value.trim();
  if (!srcGid)  { _toast('请选择来源版本', 'warn'); return; }
  if (!tag)     { _toast('请填写版本标签', 'warn'); return; }

  const { includeNodeTypes, fieldRules } = _getForkConfig();
  const body = {
    target_version_tag:       tag,
    target_bop_name:          document.getElementById('inp-fork-bop-name').value.trim(),
    target_version_family_gid: document.getElementById('inp-fork-family').value || null,
    change_note:              document.getElementById('inp-fork-change-note').value.trim() || null,
    include_node_types:       includeNodeTypes,
    field_rules:              fieldRules,
    meta_key_rules:           {},
  };
  try {
    const json = await ListShell._cf(`/api/bop/versions/${srcGid}/fork`, {
      method: 'POST', body: JSON.stringify(body)
    });
    closeModal('modal-fork-bop');
    await _refreshSidebar();
    // 自动切换到新版本
    if (json.data?.gid) { _currentVersion = json.data.gid; await load(); }
    _toast(`Fork 成功，新版本 ${tag}，共 ${json.entries_count} 个节点`, 'success');
  } catch (e) { _toast('Fork 失败: ' + e.message, 'error'); }
}

async function _loadAlPreview() {
  if (!_currentVersion) { _toast('请先选择 BOP 版本', 'warn'); return; }
  try {
    const json = await ListShell._cf(`/api/bop/versions/${_currentVersion}/auto-link-preview`);
    const data = json.data || {};
    const items = data.items || [];
    _renderAlItems(items, { ok: data.pending, skip: data.skip, warn: data.warn, error: 0 });
    _toast(`预览完成：待处理 ${data.pending ?? 0}，跳过 ${data.skip ?? 0}，警告 ${data.warn ?? 0}`, 'info');
  } catch (e) { _toast('预览失败: ' + e.message, 'error'); }
}

// ── Auto-Link 分步弹窗 ──────────────────────────────────────────

function _renderAlItems(items, summary) {
  const tbody = document.getElementById('al-items-tbody');
  const iconSvgs = {
    ok: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--success)" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>',
    skip: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" stroke-width="2"><line x1="5" y1="5" x2="19" y2="19"/></svg>',
    warn: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--warning)" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
    error: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--danger)" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
    pending: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
  };
  tbody.innerHTML = items.map((it, i) => {
    const svg = iconSvgs[it.status] || iconSvgs.error;
    return `<tr>
      <td style="padding:3px 6px">${it.seq_no ?? i + 1}</td>
      <td style="padding:3px 6px"><span class="bop-nt-badge bop-nt-${it.node_type}">${NODE_TYPE_LABELS[it.node_type] || it.node_type}</span></td>
      <td style="padding:3px 6px">${it.title || '—'}</td>
      <td style="padding:3px 6px;font-family:monospace;font-size:11px">${it.bom_row_id || '—'}</td>
      <td style="padding:3px 6px">${svg}</td>
      <td style="padding:3px 6px;color:var(--text-muted)">${it.message || ''}</td>
    </tr>`;
  }).join('');

  // 汇总
  const sumEl = document.getElementById('al-summary');
  sumEl.classList.remove('hidden');
  sumEl.innerHTML = `
    <span class="al-summary-item al-ok"><span class="num">${summary.ok || 0}</span> 成功</span>
    <span class="al-summary-item al-skip"><span class="num">${summary.skip || 0}</span> 跳过</span>
    <span class="al-summary-item al-warn"><span class="num">${summary.warn || 0}</span> 警告</span>
    <span class="al-summary-item al-error"><span class="num">${summary.error || 0}</span> 错误</span>
    <span style="color:var(--text-muted)">| 总计 ${items.length} 条</span>
  `;
  document.getElementById('al-items-wrap').classList.remove('hidden');
}

async function _openAutoLinkModal() {
  if (!_currentVersion) { _toast('请先选择 BOP 版本', 'warn'); return; }

  // 重置状态
  document.getElementById('al-summary').classList.add('hidden');
  document.getElementById('al-summary').innerHTML = '';
  document.getElementById('al-items-wrap').classList.add('hidden');
  document.getElementById('al-items-tbody').innerHTML = '';

  openModal('modal-auto-link');

  // 自动拉取预览
  try {
    const json = await ListShell._cf(`/api/bop/versions/${_currentVersion}/auto-link-preview`);
    const data = json.data || {};
    const items = data.items || [];
    _renderAlItems(items, { ok: data.pending, skip: data.skip, warn: data.warn, error: 0 });
  } catch (_) { /* 预览失败不阻塞 */ }
}

async function _runAlStep(step) {
  if (!_currentVersion) { _toast('请先选择 BOP 版本', 'warn'); return; }
  const label = step === 'A' ? 'Step A' : step === 'B' ? 'Step B' : '全部';
  try {
    const json = await ListShell._cf(`/api/bop/versions/${_currentVersion}/auto-link`, {
      method: 'POST',
      body: JSON.stringify({ step }),
    });
    const data = json.data || {};
    const items = data.items || [];
    const stats = data.stats || {};
    _renderAlItems(items, stats);
    _toast(`${label} 执行完成：成功 ${stats.ok ?? 0}，警告 ${stats.warn ?? 0}，错误 ${stats.error ?? 0}`, 'success');
    await load();
  } catch (e) { _toast(`${label} 执行失败: ` + e.message, 'error'); }
}

// ── GBOP 导入 ────────────────────────────────────────────────────
async function _openImportGbopModal() {
  if (!_currentVersion) { _toast('请先选择目标 BOP 版本', 'warn'); return; }
  const sel = document.getElementById('inp-copy-gbop-version');
  sel.innerHTML = '<option value="">-- 选择 GBOP 版本 --</option>';
  try {
    const json = await ListShell._cf('/api/bop/versions');
    (json.data || []).forEach(v => {
      if (v.gid === _currentVersion) return;
      const opt = document.createElement('option');
      opt.value = v.gid;
      opt.textContent = `${v.version_tag} (${MATURITY_LABELS[v.maturity] || v.maturity})`;
      sel.appendChild(opt);
    });
  } catch (_) {}
  openModal('modal-import-gbop');
}

async function _importGbop() {
  const srcGid = document.getElementById('inp-copy-gbop-version').value;
  if (!_currentVersion || !srcGid) { _toast('请选择 GBOP 版本', 'warn'); return; }
  try {
    const json = await ListShell._cf(`/api/bop/versions/${_currentVersion}/copy-from-gbop/${srcGid}`, { method: 'POST' });
    closeModal('modal-import-gbop');
    await load();
    _toast(`GBOP 导入成功，共 ${json.count} 个节点`, 'success');
  } catch (e) { _toast('导入失败: ' + e.message, 'error'); }
}

// ── DOMContentLoaded ─────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  document.querySelectorAll('[data-close-modal]').forEach(btn =>
    btn.addEventListener('click', () => closeModal(btn.dataset.closeModal))
  );
  document.querySelectorAll('.modal-overlay').forEach(overlay =>
    overlay.addEventListener('click', e => { if (e.target === overlay) closeModal(overlay.id); })
  );

  document.getElementById('btn-confirm-new-version').onclick   = _createVersion;
  document.getElementById('btn-confirm-edit-version').onclick  = _saveEditVersion;

  // 新建版本 modal：项目/标签/后缀 联动更新 BOP 名称预览
  document.getElementById('inp-ver-project').addEventListener('change', () => {
    const projSel = document.getElementById('inp-ver-project');
    const opt = projSel.options[projSel.selectedIndex];
    document.getElementById('inp-ver-factory-display').value = opt?.dataset.factoryName || '';
    document.getElementById('inp-ver-factory').value         = opt?.dataset.factoryGid  || '';
    document.getElementById('inp-ver-takt').value            = opt?.dataset.jph         || '';
    _updateBopNamePreview();
    _refreshPbomVersionList(projSel.value);
  });
  document.getElementById('inp-ver-tag').addEventListener('input', _updateBopNamePreview);
  document.getElementById('inp-ver-bop-suffix').addEventListener('input', _updateBopNamePreview);
  document.getElementById('btn-confirm-new-root').onclick      = _createRoot;
  document.getElementById('btn-confirm-add-child').onclick     = _createChild;
  document.getElementById('btn-confirm-edit-entry').onclick    = _saveEditEntry;
  document.getElementById('btn-confirm-fork-bop').onclick      = _executeFork;
  document.getElementById('btn-confirm-import-gbop').onclick   = _importGbop;
  document.getElementById('btn-fork-save-preset').addEventListener('click', _saveForkPreset);
  document.getElementById('btn-fork-delete-preset').addEventListener('click', _deleteForkPreset);
  document.getElementById('btn-al-preview').addEventListener('click', _loadAlPreview);
  document.getElementById('btn-al-step-a').addEventListener('click', () => _runAlStep('A'));
  document.getElementById('btn-al-step-b').addEventListener('click', () => _runAlStep('B'));

  document.getElementById('inp-tc-file').addEventListener('change', e => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = ev => { _parsedTcRows = _parseTcCsv(ev.target.result); _renderTcPreview(_parsedTcRows); };
    reader.readAsText(file, 'UTF-8');
  });
  document.getElementById('btn-confirm-import-tc').onclick = _importTc;

  // 行内操作按钮委托
  document.getElementById('appRoot').addEventListener('click', e => {
    const btn = e.target.closest('[data-act]');
    if (!btn) return;
    e.stopPropagation();
    const gid = btn.dataset.gid;
    const act = btn.dataset.act;
    const allRows = [...(_shell?.grid?.getRows() || []), ...(_shell?._tree?._allRows || [])];
    const row = allRows.find(r => r.gid === gid);
    if (!row && act !== 'del') return;
    if (act === 'edit')  _openEditModal(row);
    if (act === 'child') _openAddChildModal(gid);
    if (act === 'del')   _deleteEntry(gid);
  });

  _initShell();
  await _loadBopVersions();
  await _shell.init();
  // 安装自定义版本分组侧边栏
  if (_shell.sidebar) {
    _shell.sidebar._customRender = _renderBopSidebar;
    _shell.sidebar._renderItems();
  }

  // 注入 BOP 版本族侧边栏样式
  const bopSidebarStyle = document.createElement('style');
  bopSidebarStyle.textContent = `
    .bop-fam-hdr {
      display: flex; align-items: center; gap: 5px;
      padding: 6px 8px 4px;
      cursor: pointer; user-select: none;
      color: var(--text-muted, #a6adc8);
      font-size: 11px; font-weight: 600;
      letter-spacing: .03em;
    }
    .bop-fam-hdr:hover { color: var(--text-normal, #cdd6f4); }
    .bop-fam-arrow { flex-shrink: 0; transition: transform .15s; }
    .bop-fam-arrow.open { transform: rotate(90deg); }
    .bop-fam-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .bop-fam-arc-btn {
      flex-shrink: 0; background: none; border: none; cursor: pointer;
      color: var(--text-faint, #6c7086); padding: 2px 3px; border-radius: 3px;
      opacity: 0; transition: opacity .12s;
    }
    .bop-fam-hdr:hover .bop-fam-arc-btn { opacity: 1; }
    .bop-fam-arc-btn:hover { color: var(--text-muted, #a6adc8); background: rgba(255,255,255,.06); }
    .bop-ver-item {
      display: flex; align-items: center; gap: 4px;
      padding: 4px 8px 4px 20px;
      cursor: pointer; border-radius: 5px;
      font-size: 12px; color: var(--text-muted, #a6adc8);
    }
    .bop-ver-item:hover { background: rgba(255,255,255,.05); }
    .bop-ver-item.active { background: rgba(137,180,250,.12); color: var(--color-accent, #89b4fa); }
    [data-theme="light"] .bop-ver-item:hover { background: rgba(0,0,0,.04); }
    [data-theme="light"] .bop-ver-item.active { background: rgba(30,102,245,.08); }
    .bop-ver-dot {
      width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0;
      background: var(--text-faint, #6c7086);
    }
    .bop-ver-dot.frozen { background: #89dceb; }
    .bop-ver-tag-text { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .bop-ver-status {
      font-size: 10px; padding: 1px 5px; border-radius: 3px; flex-shrink: 0;
    }
    .bop-vs-draft  { background: rgba(108,112,134,.2); color: var(--text-faint, #6c7086); }
    .bop-vs-frozen { background: rgba(137,220,235,.15); color: #89dceb; }
    .bop-ver-takt  { font-size: 10px; color: var(--text-faint, #6c7086); flex-shrink: 0; }
    .bop-ver-ctx-btn {
      flex-shrink: 0; background: none; border: none; cursor: pointer;
      color: var(--text-faint, #6c7086); padding: 1px 3px; border-radius: 3px;
      opacity: 0; transition: opacity .12s;
    }
    .bop-ver-item:hover .bop-ver-ctx-btn, .bop-ver-item.active .bop-ver-ctx-btn { opacity: 1; }
    .bop-ver-ctx-btn:hover { color: var(--text-normal, #cdd6f4); background: rgba(255,255,255,.06); }
    .bop-arc-section-hdr {
      display: flex; align-items: center; gap: 5px;
      padding: 8px 8px 4px; margin-top: 4px;
      cursor: pointer; user-select: none;
      color: var(--text-faint, #6c7086); font-size: 11px;
      border-top: 1px solid var(--border-default, #313244);
    }
    .bop-arc-section-hdr:hover { color: var(--text-muted, #a6adc8); }
  `;
  document.head.appendChild(bopSidebarStyle);
});
