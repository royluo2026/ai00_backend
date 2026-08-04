'use strict';
/**
 * lineage.js  —  BOP Lineage Miller Columns 树形视图
 *
 * 依赖：无外部库（纯 vanilla JS）
 * 数据来源：GET /api/bop/versions/{gid}/entries
 * 列分组依据：树深度（根据 parent_gid 链计算，非固定 ai00_level）
 */

// ── 常量 ────────────────────────────────────────────────────────────
// 对照 docs/bop/db csv ui.xlsx — AI00_Level 列
const NT_ABBR = {
  factory_bop: '厂', line_process: '线', station_process: '工位',
  operator_process: '岗', man: '人', station_factory: '工厂工位',
  equipment_factory: '设', tool_factory: '具↗', equipment_need: '设需',
  fixture_factory: '装↗', process: '工序', operation: '操作',
  issue: '问', standard_task: '任', non_standard_task: '非任',
  contral_plan: '控', process_chart: '卡',
  knowledge: '知', rule: '规',
  part: '件', non_standard_part: '非标', standard_part: '标',
  support_material: '辅', tool_need: '具', fixture_need: '装',
  floor_height_factory: '地高↗', jack_pos: '姿态',
};

// NT_LABEL：对照 docs/bop/db csv ui.xlsx "零组件类型AI_00" 列（lineage 卡片提示 / 筛选下拉显示）
const NT_LABEL = {
  factory_bop:          '总装工厂BOP',    line_process:         '总装线体工艺',
  station_process:      '总装工位工艺',   operator_process:     '岗位',
  man:                  '人',             station_factory:      '工厂工位',
  equipment_factory:    '设备（工厂）',   tool_factory:         '工具（工厂）',
  equipment_need:       '设备（需求）',   fixture_factory:      '工装（工厂）',
  process:              '总装工序',       operation:            '总装操作（Product）',
  issue:                '问题',           standard_task:        '标准任务',
  non_standard_task:    '非标任务',       contral_plan:         '控制计划',
  process_chart:        '工艺卡',         knowledge:            '知识',
  rule:                 '规则',           part:                 '零部件',
  non_standard_part:    '非标件',         standard_part:        '标准件',
  support_material:     '辅料',           tool_need:            '工具（需求）',
  fixture_need:         '工装（需求）',
  floor_height_factory: '地面高度（现有）',
  jack_pos:             '人机姿态',
};

// ── 统计显示优先级（按节点类型分族定制）────────────────────────────
const STATS_PRIORITY = [
  'process', 'operation', 'man', 'part', 'station_factory',
  'equipment_factory', 'equipment_need', 'fixture_factory', 'fixture_need',
  'tool_need', 'tool_factory', 'standard_part', 'non_standard_part',
  'support_material', 'issue', 'standard_task', 'non_standard_task',
  'contral_plan', 'process_chart', 'knowledge', 'rule',
  'station_process', 'operator_process', 'line_process', 'factory_bop',
];

// 按节点类型分族的后代统计优先级（族1：工艺上三层）
const _LEVEL_STATS_PRIORITY = {
  line_process:      ['process', 'operation', 'man', 'station_factory', 'part', 'equipment_factory', 'tool_factory'],
  station_process:   ['process', 'operation', 'man', 'equipment_factory', 'equipment_need', 'part', 'tool_need', 'fixture_need'],
  operator_process:  ['process', 'operation', 'equipment_factory', 'fixture_factory', 'man', 'part', 'tool_need'],
};

// 节点类型语义最小深度（仅当 parent_gid 为 null 时使用）
// factory_bop 是唯一允许 depth=0 的类型（根选择栏）；其他类型 ≥ 1，显示在列视图
const _NODE_MIN_DEPTH = {
  factory_bop:       0,
  line_process:      1,
  station_process:   2,
  operator_process:  3,
  process:           4,
  operation:         5,
};
// 族2：工序节点
const _PROCESS_STATS_PRIORITY = ['operation', 'man', 'equipment_factory', 'equipment_need', 'fixture_factory', 'part', 'tool_need'];
// 族3：操作节点
const _OP_STATS_PRIORITY = ['part', 'standard_task', 'equipment_factory', 'tool_need', 'fixture_need'];

// ── PBOM Excel 列映射（TC/PLM 导出 → DB 字段）───────────────────────
const _PBOM_EXCEL_COL_MAP = {
  'Home': 'home', 'Level': 'level', 'VPPS': 'vpps', 'VPPS描述': 'vpps_desc',
  '父级VPPS': 'parent_vpps', '父级VPPS名称': 'parent_vpps_name',
  'BOM 行': 'bom_row', 'BOM行': 'bom_row', 'BOM行标签': 'bom_row_label', 'BOM 行标签': 'bom_row_label',
  '零组件 ID': 'component_id', '零组件ID': 'component_id', '零组件名称': 'name',
  '变量公式': 'variable_formula', '扭矩': 'torque', '扭矩重要度': 'torque_importance',
  '数量': 'quantity', '零组件版本所有权用户': 'ownership_user',
  '零组件类型': 'component_type', '零组件版本状态': 'component_version_status',
  '采购状态': 'purchase_status', '父级': 'parent_bom_row', '配置': 'configuration',
  '父级BOM行': 'parent_bom_row', '父级BOM 行': 'parent_bom_row',
  'catiaOccurrenceName': 'catia_occurrence_name', 'catiaFileName': 'catia_file_name',
  'catiaUUID': 'catia_uuid', '默认变换矩阵': 'default_matrix', '绝对变换矩阵': 'abs_matrix',
  '相对变换矩阵': 'rel_matrix', '限定框': 'local_bbox', 'ECN编码': 'ecn', 'FNA': 'fna',
  '几何推测主件': 'geo_main_part', '参考主件VPPS描述': 'ref_main_vpps_desc',
  '参考主件vpps': 'ref_main_vpps', '主件一致性状态': 'main_part_consistency',
  '推测主件几何依据': 'geo_evidence', '零件左右侧': 'lr_side',
  'part_no': 'part_no', 'name': 'name', 'quantity': 'quantity', 'unit': 'unit', 'material': 'material',
};
const _PBOM_FULL_COLS = [
  { key: 'name', label: '零组件名称', type: 'text', width: 200 },
  { key: 'part_no', label: '零件号', type: 'text', width: 120 },
  { key: 'vpps', label: 'VPPS', type: 'text', width: 120 },
  { key: 'vpps_desc', label: 'VPPS描述', type: 'text', width: 160 },
  { key: 'parent_vpps', label: '父级VPPS', type: 'text', width: 120 },
  { key: 'bom_row', label: 'BOM 行', type: 'text', width: 120 },
  { key: 'component_id', label: '零组件 ID', type: 'text', width: 130 },
  { key: 'quantity', label: '数量', type: 'number', width: 60 },
  { key: 'unit', label: '单位', type: 'text', width: 50 },
  { key: 'material', label: '材料', type: 'text', width: 100 },
  { key: 'component_type', label: '零组件类型', type: 'text', width: 100 },
  { key: 'level', label: '层级', type: 'number', width: 50 },
];

function _mapPbomExcelRow(raw) {
  const out = {};
  for (const [excelKey, dbKey] of Object.entries(_PBOM_EXCEL_COL_MAP)) {
    if (raw[excelKey] !== undefined && raw[excelKey] !== null && raw[excelKey] !== '') {
      out[dbKey] = raw[excelKey];
    }
  }
  for (const k of Object.keys(raw)) {
    if (!out[k] && _PBOM_EXCEL_COL_MAP[k] === undefined) {
      const dbFields = new Set(Object.values(_PBOM_EXCEL_COL_MAP));
      if (dbFields.has(k)) out[k] = raw[k];
    }
  }
  if (!out.part_no && out.component_id) out.part_no = out.component_id;
  if (out.quantity !== undefined) out.quantity = parseFloat(out.quantity) || 1;
  if (out.level !== undefined) { const _lv = parseInt(out.level); out.level = isNaN(_lv) ? null : _lv; }
  if (out.home) {
    let h = (out.home + '').trim();
    const m = h.match(/^=HYPERLINK\s*\(\s*"[^"]*"\s*,\s*"([^"]*)"\s*\)/i);
    if (m) h = m[1];
    if (/^https?:\/\//i.test(h)) h = '';
    out.home = h;
  }
  if (!out.unit) out.unit = 'pcs';
  if (!out.name) out.name = '';
  if (!out.part_no) out.part_no = '';
  return out;
}

// ── 状态 ─────────────────────────────────────────────────────────────
const _params   = Object.fromEntries(new URLSearchParams(location.search));
function _cf(path, opts) {
  const fn = window.top?._cloudFetch || window.parent?._cloudFetch || window._cloudFetch;
  if (!fn) throw new Error('cloudFetch not available');
  return fn(path, opts);
}
// localStorage 账号隔离
const _USER_GID = (() => {
  try { const u = window.parent?._authUser || window.top?._authUser || window._authUser; return u?.gid || u?.user_gid || ''; } catch { return ''; }
})();
function _lsk(base) { return _USER_GID ? `${_USER_GID}:${base}` : base; }
let _versionGid = _params.bop_version_gid || localStorage.getItem(_lsk('lv:lastVersionGid')) || '';
const _versionTag = _params.version_tag || _versionGid.slice(-6);

let _rows            = [];      // flat array from API (may span multiple versions)
let _rowByGid        = new Map();
let _childMap        = new Map(); // null → root children
let _statsMap        = new Map(); // gid → {nt: count}
let _collapsed       = new Set(); // gid of nodes whose children are hidden
let _depthByGid      = new Map(); // gid → tree depth (depth 0 = root, root's children = depth 1, etc.)
let _selectedRoots   = new Set(); // 树深度=0 的根节点（仅显示已选根节点的后代）
let _loadedVersionGids = new Set(); // which bop_version GIDs are currently loaded
let _lineGrantSet    = new Set();    // line_process gids the current user can edit
let _lineReadOnly    = false;        // true when user is limited to some lines
let _versionTagMap   = new Map();   // version_gid → version_tag (for picker dedup)
let _rootPickerEl    = null;        // the floating version picker DOM element
let _activeGid       = null;
let _dragGid         = null;
let _miller         = null;

// 视图设置（从 localStorage 恢复）
let _typeFilter   = null;    // null = 全部显示, [] = 全不选, ['type1',...] = 筛选
let _maxDepth     = 6;     // 最大树深度（含），默认显示到深度 6（根=0，第1列=深度1；part节点在深度5）
let _searchText   = '';
let _level1Filter = null; // null = 全部显示, Set() = 全不选, Set([gid,...]) = 筛选（深度=1的节点）
let _colTypeFilters = new Map(); // level → node_type，列内类型二次筛选（点击列头 chip 触发）
let _collapsedCols  = new Set(); // level → 该列折叠隐藏（仅保留窄条）
let _zoomPct        = 100;       // 缩放百分比（50-200）
let _sidebarOpen    = false;     // 右侧边栏展开/折叠（默认关闭）
let _toolbarOpen    = true;      // 工具栏显示/隐藏（默认展开，由 FAB 切换）

// 暂存箱 + 关联面板
let _stagingPanel   = null;     // StagingPanel 实例
let _assocPanel     = null;     // AssocPanel 实例
let _layoutDetailPanel = null;  // LayoutDetailPanel 实例

// 布局模式状态
let _viewMode = localStorage.getItem(_lsk('lv:viewMode')) || 'layout'; // 'columns' | 'layout'
// 兼容旧版本 'compact' 值（精简视图已移除），统一映射为 'layout'
if (_viewMode === 'compact') { _viewMode = 'layout'; localStorage.setItem(_lsk('lv:viewMode'), 'layout'); }
let _layoutMode    = null;       // LayoutMode 实例（单例）
let _layoutEditMode = false;
let _pendingLayoutPan  = null;   // session 恢复时暂存，布局初始化后应用
let _pendingLayoutZoom = null;
let _lvThemeLayout  = localStorage.getItem(_lsk('lv:theme:layout'))  || 'light'; // 布局视图主题
let _lvThemeColumns = localStorage.getItem(_lsk('lv:theme:columns')) || 'dark';  // 列视图主题
let _stagingCollapsed = localStorage.getItem(_lsk('lv:stagingCollapsed')) === 'true';
let _versionStatus = 'active';  // 'active' | 'baseline' | 'M' | 'archived'

// ── 多项目对比（布局视图专用）────────────────────────────────────
// 每项 { versionGid, versionTag, bopName, color, label }
let _projectVersions = [];
// 固定4色调色板（A=蓝，B=绿，C=橙，D=紫）
const _PROJECT_COLORS = ['#1e66f5', '#40a02b', '#df8e1d', '#8839ef'];

// ── 版本管理器（LineageVersionManager 实例，在 init() 中创建）──────
let _verMgr = null;
let _lifecyclePanel = null;  // BopLifecyclePanel 实例

// ── PBOM 导入状态 ──────────────────────────────────────────────────
let _pbomIeMgr      = null;     // ImportExportManager 实例
let _pbomProjects   = [];       // 项目列表
let _pbomVersions   = [];       // PBOM 版本列表
let _pbomTargetGid  = null;     // 导入目标版本 gid

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
const $dntWrap    = null;  // removed: DiffNavTree moved to AssocPanel
const $zoomRange  = document.getElementById('lvZoomRange');
const $zoomPct    = document.getElementById('lvZoomPct');
const $sidebar    = document.getElementById('lvSidebar');
const $sbToggle   = document.getElementById('lvSbToggle');
const $stagingBody  = document.getElementById('llDsBody');
const $stagingCount = document.getElementById('llDsCount');
const $stagingAdd   = document.getElementById('llDsAdd');
const $assocTabs    = document.getElementById('lvAssocTabs');
const $assocBody    = document.getElementById('lvAssocBody');
const $panelDivider = document.getElementById('lvPanelDivider');
const $staging      = document.getElementById('llDpStagingWrap');
const $stagingCollapse = null; // 暂存箱折叠改为水平模式，由 LayoutDetailPanel 管理
const $dpPopover  = document.getElementById('lvDetailPopover');
const $dpBody     = document.getElementById('lvDpBody');
const $dpTitle    = document.getElementById('lvDpTitle');
const $dpClose    = document.getElementById('lvDpClose');
// 阻止弹窗内的滚轮事件穿透到下方画布
$dpPopover.addEventListener('wheel', e => { e.stopPropagation(); }, { passive: true });
const $opPanel    = document.getElementById('lvOverlayPanel');
const $opBody     = document.getElementById('lvOpBody');
const $opTitle    = document.getElementById('lvOpTitle');
const $opClose    = document.getElementById('lvOpClose');
const $opPin      = document.getElementById('lvOpPin');
const $versionStatus = document.getElementById('lvVersionStatus');
const $frozenBar     = document.getElementById('lvFrozenBar');
const $frozenBarText = document.getElementById('lvFrozenBarText');
const $addNodeBtn    = document.getElementById('lvAddNode');

// ── 版本选择器 DOM refs ────────────────────────────────────────────
// ── 布局模式 DOM ──────────────────────────────────────────────────
const $layoutCanvas  = document.getElementById('lvLayoutCanvas');
const $layoutEditBtn   = document.getElementById('lvLayoutEditBtn');
const $layoutFitBtn    = document.getElementById('lvLayoutFitBtn');
const $importPbomBtn   = document.getElementById('lvImportPbomBtn');
const $importTcBtn     = document.getElementById('lvImportTcBtn');
const $arrangeMode     = null; // 已移除
const $arrangeModeWrap = null; // 已移除

// ── Toast ─────────────────────────────────────────────────────────────
let _toastTimer = null;
function _toast(msg, type = 'ok', dur = 2500) {
  $toast.textContent = msg;
  $toast.className = `lv-toast ${type}`;
  $toast.style.display = 'block';
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => { $toast.style.display = 'none'; }, dur);
}

// ── PBOM 导入 ─────────────────────────────────────────────────────────
function _pbomAutoVerName(projectGid, suffix) {
  const pname = _pbomProjects.find(p => p.gid === projectGid)?.name || '未知项目';
  const now = new Date();
  const pad = n => String(n).padStart(2, '0');
  const stamp = `${now.getFullYear()}${pad(now.getMonth()+1)}${pad(now.getDate())}${pad(now.getHours())}${pad(now.getMinutes())}`;
  return [pname, suffix?.trim(), stamp].filter(Boolean).join('-');
}

async function _loadPbomProjects() {
  try {
    const res = await _cf('/api/projects');
    _pbomProjects = res?.data || [];
  } catch (_) { _pbomProjects = []; }
}

async function _loadPbomVersions(projectGid) {
  try {
    const path = projectGid
      ? `/api/ebom/snapshots?project_gid=${encodeURIComponent(projectGid)}`
      : '/api/ebom/snapshots';
    const res = await _cf(path);
    _pbomVersions = res?.data || [];
  } catch (_) { _pbomVersions = []; }
}

function _openPbomImportModal() {
  const modal   = document.getElementById('lv-modal-import-pbom');
  const projSel = document.getElementById('lv-pbom-project');
  const suffix  = document.getElementById('lv-pbom-suffix');
  const preview = document.getElementById('lv-pbom-ver-preview');
  const verMode = document.getElementById('lv-pbom-ver-mode');
  const existSel = document.getElementById('lv-pbom-existing-ver');
  const existWrap = document.getElementById('lv-pbom-existing-wrap');
  const newWrap   = document.getElementById('lv-pbom-new-wrap');
  const confirmBtn = document.getElementById('lv-pbom-confirm');

  // 填充项目下拉
  if (projSel) {
    projSel.innerHTML = '<option value="">（无项目）</option>' +
      _pbomProjects.map(p => `<option value="${p.gid}">${p.name}</option>`).join('');
  }

  const _syncMode = () => {
    const isNew = verMode?.value !== 'existing';
    if (newWrap) newWrap.style.display = isNew ? '' : 'none';
    if (existWrap) existWrap.style.display = isNew ? 'none' : '';
    if (confirmBtn) confirmBtn.textContent = isNew ? '创建版本并继续导入' : '导入到此版本';
    if (!isNew) {
      // 刷新现有版本列表
      const pgid = projSel?.value || '';
      const list = pgid ? _pbomVersions.filter(v => v.project_gid === pgid) : _pbomVersions;
      if (existSel) {
        existSel.innerHTML = list.length
          ? list.map(v => `<option value="${v.gid}">${v.name || v.version_tag || v.gid}</option>`).join('')
          : '<option value="">（暂无版本）</option>';
      }
    }
  };

  const _updatePreview = () => {
    if (projSel && suffix && preview) {
      preview.value = _pbomAutoVerName(projSel.value, suffix.value);
    }
  };

  _updatePreview();
  _syncMode();

  // 事件绑定（用 oninput/onchange 属性避免重复绑定）
  projSel.onchange = () => { _updatePreview(); _syncMode(); };
  suffix.oninput = _updatePreview;
  verMode.onchange = _syncMode;

  modal?.classList.remove('hidden');
}

async function _handlePbomImportConfirm() {
  const modal     = document.getElementById('lv-modal-import-pbom');
  const isNew     = document.getElementById('lv-pbom-ver-mode')?.value !== 'existing';
  const sourceType = document.getElementById('lv-pbom-source')?.value || 'import';

  modal?.classList.add('hidden');

  if (isNew) {
    const projGid = document.getElementById('lv-pbom-project')?.value || null;
    const verName = document.getElementById('lv-pbom-ver-preview')?.value.trim();
    if (!verName) { _toast('版本名称不能为空', 'warn'); return; }
    try {
      const res = await _cf('/api/ebom/snapshots', {
        method: 'POST',
        body: JSON.stringify({ name: verName, version_tag: verName, project_gid: projGid, source_type: sourceType }),
      });
      if (!res?.success) { _toast('创建版本失败', 'error'); return; }
      _pbomTargetGid = res.data?.gid;
      _toast('版本已创建，请继续导入', 'ok');
    } catch (e) {
      _toast('创建版本失败: ' + (e.message || '未知错误'), 'error');
      return;
    }
  } else {
    const existGid = document.getElementById('lv-pbom-existing-ver')?.value;
    if (!existGid) { _toast('请选择一个现有版本', 'warn'); return; }
    _pbomTargetGid = existGid;
  }

  // 启动 ImportExportManager 导入向导
  if (_pbomIeMgr) _pbomIeMgr.showImport();
}

function _setupPbomImportModal() {
  document.getElementById('lv-pbom-cancel')?.addEventListener('click', () => {
    document.getElementById('lv-modal-import-pbom')?.classList.add('hidden');
  });
  document.getElementById('lv-pbom-confirm')?.addEventListener('click', _handlePbomImportConfirm);
}

// ── 版本状态 UI ───────────────────────────────────────────────────────
// _STATUS_COLORS 定义在 lineage_version_mgr.js（必须先加载）

function _isVersionEditable() { return _versionStatus === 'active'; }

function _getLineAncestorGid(gid) {
  let row = _rowByGid.get(gid);
  while (row) {
    if (row.node_type === 'line_process') return row.gid;
    row = row.parent_gid ? _rowByGid.get(row.parent_gid) : null;
  }
  return null;
}

function _canEditEntry(gid) {
  if (!_isVersionEditable()) return false;
  if (!_lineReadOnly) return true;
  const lineGid = _getLineAncestorGid(gid);
  return lineGid ? _lineGrantSet.has(lineGid) : true;
}

function _updateVersionStatusUI() {
  const info = _STATUS_COLORS[_versionStatus];
  if (!info) return;

  // 状态徽章
  if ($versionStatus) {
    $versionStatus.textContent = info.label;
    $versionStatus.style.background = info.bg;
    $versionStatus.style.display = _versionStatus === 'active' ? 'none' : 'inline-block';
  }

  // 冻结通知条
  if ($frozenBar && $frozenBarText) {
    if (!_isVersionEditable()) {
      $frozenBarText.textContent = `此版本为「${info.label}」状态，不可编辑`;
      $frozenBar.style.display = '';
    } else {
      $frozenBar.style.display = 'none';
    }
  }

  // 新建节点按钮
  if ($addNodeBtn) {
    $addNodeBtn.style.display = _isVersionEditable() ? '' : 'none';
  }

  // 布局编辑按钮
  if ($layoutEditBtn) {
    if (!_isVersionEditable()) {
      $layoutEditBtn.disabled = true;
      $layoutEditBtn.title = '版本非活动状态，无法编辑';
      $layoutEditBtn.classList.add('disabled');
      _layoutEditMode = false;
      $layoutEditBtn.classList.remove('active');
      if (_layoutMode) _layoutMode.setEditMode(false);
    } else {
      $layoutEditBtn.disabled = false;
      $layoutEditBtn.title = '编辑模式';
      $layoutEditBtn.classList.remove('disabled');
    }
  }
}

// ── 数据层 ────────────────────────────────────────────────────────────

async function _loadLineGrants() {
  _lineGrantSet.clear();
  _lineReadOnly = false;
  try {
    const me = await _cf('/api/users/me');
    const verJson = await _cf(`/api/bop/versions/${_versionGid}`);
    const projectGid = verJson?.data?.project_gid || '';
    const orgRole = me?.data?.org_role || me?.data?.system_role || me?.org_role || me?.system_role || '';
    // 所有组织成员均可编辑全部线体，不再加载线体范围限制。
    if (orgRole === 'super_admin' || orgRole === 'member' || orgRole === 'team_admin' || orgRole === 'project_admin') return;
    if (!projectGid) return;
    const permJson = await _cf(`/api/projects/${encodeURIComponent(projectGid)}/line-permissions`).catch(() => null);
    const editable = permJson?.data?.editable_line_gids || [];
    if (editable.length) {
      _lineReadOnly = true;
      editable.forEach(gid => _lineGrantSet.add(gid));
    }
  } catch (_) {}
}

function _flattenMeta(rows) {
  // 兼容旧数据：将 meta.title 提升到顶层，但保留 meta 供属性面板读取
  return rows.map(r => {
    if (r.meta && typeof r.meta === 'object') {
      if (!r.title && r.meta.title) r.title = r.meta.title;
    } else if (typeof r.meta === 'string') {
      try {
        const m = JSON.parse(r.meta);
        r.meta = m;
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
  // sort children by sort_order
  for (const [, arr] of _childMap) {
    arr.sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));
  }
  // 预计算每个节点的树深度
  // 根节点（parent_gid === null）深度 = 0，但受节点类型语义最小深度约束
  // 例如 line_process 最小深度 = 1，即使 parent_gid 为 null 也出现在第1列
  const _calcDepth = (gid, cache) => {
    if (cache.has(gid)) return cache.get(gid);
    const r = _rowByGid.get(gid);
    if (!r) { cache.set(gid, 0); return 0; }
    if (!r.parent_gid) {
      // 无父节点时：factory_bop 才是合法的深度0根节点；
      // 其余类型（包括孤儿节点）优先用 _NODE_MIN_DEPTH，
      // 再用 ai00_level 字段（最小取1，确保不会出现在根选择器中）
      if (r.node_type === 'factory_bop') { cache.set(gid, 0); return 0; }
      const minD = _NODE_MIN_DEPTH[r.node_type];
      const d = minD !== undefined ? minD : Math.max((r.ai00_level ?? 1), 1);
      cache.set(gid, d); return d;
    }
    // 有父节点：正常按父链计算，不施加语义下限
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
  // 默认只选当前版本的第一个树深度=0 根节点（不全选）
  const level0 = (_childMap.get(null) || []).filter(r => _treeDepth(r) === 0);
  _selectedRoots = level0.length > 0 ? new Set([level0[0].gid]) : new Set();
}

/** 取节点的树深度（根据 parent_gid 链预计算，替代旧的 ai00_level 固定分组） */
function _treeDepth(r) { return _depthByGid.get(r?.gid) ?? 0; }

async function _load() {
  if (!_versionGid) {
    // 显示空画布，画布内提示
    $columns.style.display = 'none';
    $layoutCanvas.style.display = '';
    _syncLayoutUI();
    document.getElementById('lvLoadingOverlay')?.classList.add('hidden');
    // 提示不遮挡工具栏：渲染到画布区域
    const cv = document.getElementById('lvLayoutCanvas');
    if (cv) {
      let hint = cv.querySelector('.lv-empty-hint-overlay');
      if (!hint) {
        hint = document.createElement('div');
        hint.className = 'lv-empty-hint-overlay';
        hint.style.cssText = 'position:absolute;inset:0;display:flex;align-items:center;justify-content:center;background:var(--base,#eff1f5);z-index:5;pointer-events:none';
        cv.style.position = 'relative';
        cv.appendChild(hint);
      }
      hint.innerHTML = '<div style="text-align:center;color:var(--subtext0,#6c6f85);font-size:14px;line-height:2"><div style="font-size:40px;margin-bottom:8px;opacity:.3">📋</div><div style="font-weight:600;color:var(--text,#4c4f69)">请在上方工具栏选择 BOP 版本</div></div>';
    }
    return;
  }
  document.querySelector('.lv-empty-hint-overlay')?.remove();
  $columns.innerHTML = '<div class="lv-loading"><div class="lv-spinner"></div>加载中…</div>';

  try {
    await _loadLineGrants();
    _loadedVersionGids = new Set([_versionGid]);
    _versionTagMap.set(_versionGid, _versionTag);

    // 并行加载版本信息和条目数据
    const [verJson, entryJson] = await Promise.all([
      _cf(`/api/bop/versions/${_versionGid}`),
      _cf(`/api/bop/versions/${_versionGid}/entries`),
    ]);

    // 设置版本状态
    if (verJson.data) {
      _versionStatus = verJson.data.status || 'active';
      if (_verMgr) _verMgr.currentVersionStatus = _versionStatus;
    }
    _updateVersionStatusUI();

    _rows = _flattenMeta(entryJson.data || []);
    _buildIndexes(_rows);
    _buildStats();
    _initCollapsed();   // 初始化 _selectedRoots（默认只选第一个树深度=0 根节点）
    _restoreView();     // 从 localStorage 恢复视图（可覆盖 _selectedRoots）
    _render();
    _loadCloudConfig(); // 异步拉取云端共享布局配置（覆盖本地，team 共享）
  } catch (e) {
    $columns.innerHTML = `<div class="lv-empty">加载失败：${e.message}</div>`;
    _toast('加载失败: ' + e.message, 'error');
    _syncLayoutUI();
    document.getElementById('lvLoadingOverlay')?.classList.add('hidden');
    // 若是从 localStorage 恢复的版本加载失败，清除记录避免下次重复失败
    if (!_params.bop_version_gid && localStorage.getItem(_lsk('lv:lastVersionGid')) === _versionGid) {
      localStorage.removeItem(_lsk('lv:lastVersionGid'));
    }
  }
}

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
    const verBopName = (_verMgr?.allVersions || []).find(v => v.gid === _versionGid)?.bop_name || '';
    titleSpan.textContent = root.title || root.bom_row_label || verBopName || _versionTag || '(未命名)';
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
    const json = await _cf('/api/bop/versions');
    const available = (json.data || []).filter(v => !_loadedVersionGids.has(v.gid));

    picker.innerHTML = '';
    if (available.length === 0) {
      picker.innerHTML = '<div class="lv-root-picker-msg">无其他可用BOP版本</div>';
      return;
    }

    for (const ver of available) {
      const item = document.createElement('div');
      item.className = 'lv-root-picker-item';
      item.textContent = ver.version_tag || ver.gid.slice(-6);
      item.title = ver.version_tag || '';
      item.addEventListener('click', async () => {
        _closeRootPicker();
        await _addVersionRoots(ver.gid, ver.version_tag || ver.gid.slice(-6));
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
    const json = await _cf(`/api/bop/versions/${versionGid}/entries`);
    const newRows = _flattenMeta(json.data || []);
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

    _render();
    _toast(`已添加「${versionTag}」`, 'ok');
  } catch (e) {
    _toast('添加失败: ' + e.message, 'error');
  }
}

// ── 多项目对比（布局视图专用）─────────────────────────────────────────────

/**
 * 初始化对比按钮点击事件（在 init() 中调用一次）
 */
function _initCompareBtn() {
  const $btn  = document.getElementById('lvCompareBtn');
  const $menu = document.getElementById('lvCompareMenu');
  if (!$btn || !$menu) return;

  $btn.addEventListener('click', (e) => {
    e.stopPropagation();
    const isOpen = $menu.style.display !== 'none';
    if (isOpen) { $menu.style.display = 'none'; return; }
    _buildCompareMenu($menu);
    $menu.style.display = '';
  });

  document.addEventListener('click', () => { $menu.style.display = 'none'; });
}

/**
 * 构建对比版本下拉菜单，只列出同一工厂的其他版本
 */
async function _buildCompareMenu($menu) {
  $menu.innerHTML = '<div class="lv-compare-menu-empty">加载中…</div>';

  try {
    // 获取当前版本的工厂 GID
    const curVer = (_verMgr?.allVersions || []).find(v => v.gid === _versionGid);
    const factoryGid = curVer?.factory_gid;
    if (!factoryGid) {
      $menu.innerHTML = '<div class="lv-compare-menu-empty">无法获取工厂信息</div>';
      return;
    }

    // 拉取同一工厂下所有 active / baseline / M 版本
    const res = await _cf(`/api/bop/versions?factory_gid=${factoryGid}&include_archived=false`);
    const versions = (res.data || []).filter(v =>
      v.gid !== _versionGid &&            // 排除当前版本
      !v.archived_at &&                    // 排除归档
      v.version_type !== 'template'        // 排除模板
    );

    $menu.innerHTML = '';

    if (versions.length === 0) {
      $menu.innerHTML = '<div class="lv-compare-menu-empty">同一工厂下无其他版本</div>';
      return;
    }

    // 主版本（固定 A，蓝色）
    const primaryItem = document.createElement('div');
    primaryItem.className = 'lv-compare-menu-item active';
    const primaryLabel = document.createElement('span');
    primaryLabel.textContent = (curVer?.bop_name || '当前版本') + ' · ' + (curVer?.version_tag || '主');
    const primaryDot = document.createElement('span');
    primaryDot.className = 'lv-compare-dot';
    primaryDot.style.background = _PROJECT_COLORS[0];
    primaryItem.appendChild(primaryDot);
    primaryItem.appendChild(primaryLabel);
    $menu.appendChild(primaryItem);

    const divider = document.createElement('div');
    divider.style.cssText = 'border-top:1px solid var(--surface1,#313244);margin:4px 0';
    $menu.appendChild(divider);

    // 可选的对比版本
    for (const ver of versions) {
      const isActive = _projectVersions.some(p => p.versionGid === ver.gid);
      const projIdx  = _projectVersions.findIndex(p => p.versionGid === ver.gid);
      const colorIdx = isActive ? projIdx : _projectVersions.length;

      const item = document.createElement('div');
      item.className = 'lv-compare-menu-item' + (isActive ? ' active' : '');

      const dot = document.createElement('span');
      dot.className = 'lv-compare-dot';
      dot.style.background = isActive ? (_PROJECT_COLORS[colorIdx] || '#888') : 'transparent';
      dot.style.border = isActive ? 'none' : '1px dashed var(--overlay0,#6c7086)';

      const label = document.createElement('span');
      label.style.flex = '1';
      label.textContent = (ver.bop_name || '未命名') + ' · ' + (ver.version_tag || ver.gid.slice(-6));

      const action = document.createElement('span');
      action.style.cssText = 'font-size:9px;color:var(--subtext0,#a6adc8)';
      action.textContent = isActive ? '移除' : '添加';

      item.appendChild(dot);
      item.appendChild(label);
      item.appendChild(action);

      item.addEventListener('click', async (e) => {
        e.stopPropagation();
        if (isActive) {
          await _removeCompareVersion(ver.gid);
        } else {
          if (_projectVersions.length >= 3) {
            _toast('最多对比 3 个项目（含主版本）', 'warn');
            return;
          }
          await _addCompareVersion(ver);
        }
        document.getElementById('lvCompareMenu').style.display = 'none';
      });

      $menu.appendChild(item);
    }
  } catch (e) {
    $menu.innerHTML = `<div class="lv-compare-menu-empty">加载失败: ${e.message}</div>`;
  }
}

/**
 * 添加对比版本
 */
async function _addCompareVersion(ver) {
  try {
    await _addVersionRoots(ver.gid, ver.version_tag || ver.gid.slice(-6));
    _projectVersions.push({
      versionGid: ver.gid,
      versionTag: ver.version_tag || ver.gid.slice(-6),
      bopName:    ver.bop_name || '',
    });
    _render();
    _toast(`已添加对比版本「${ver.bop_name || ver.version_tag}」`, 'ok');
  } catch (e) {
    _toast('添加对比版本失败: ' + e.message, 'error');
  }
}

/**
 * 移除对比版本并重新加载主版本数据
 */
async function _removeCompareVersion(versionGid) {
  _projectVersions = _projectVersions.filter(p => p.versionGid !== versionGid);
  // 移除该版本的条目，保留其他版本
  _rows = _rows.filter(r => r.version_gid !== versionGid);
  _loadedVersionGids.delete(versionGid);
  _buildIndexes(_rows);
  _buildStats();
  _render();
  _toast('已移除对比版本', 'ok');
}

/**
 * 清空所有对比版本（切回单项目模式）
 */
function _clearCompareVersions() {
  if (_projectVersions.length === 0) return;
  const extraGids = _projectVersions.map(p => p.versionGid);
  _projectVersions = [];
  _rows = _rows.filter(r => !extraGids.includes(r.version_gid));
  for (const g of extraGids) _loadedVersionGids.delete(g);
  _buildIndexes(_rows);
  _buildStats();
  if (_viewMode === 'layout') _render();
}


function _render() {
  // 安全网：无论 render 是否成功，隐藏加载覆盖层
  try { _renderImpl(); } catch (e) {
    console.error('[lineage] render error:', e);
    document.getElementById('lvLoadingOverlay')?.classList.add('hidden');
  }
}
function _renderImpl() {
  // 隐藏加载覆盖层 + 清除空状态提示
  document.getElementById('lvLoadingOverlay')?.classList.add('hidden');
  document.querySelector('.lv-empty-hint-overlay')?.remove();
  if (_viewMode === 'columns') {
    $columns.style.display = '';
    $layoutCanvas.style.display = 'none';
    $columns.innerHTML = '';
    _renderRootBar();
    _renderColumns();
  } else {
    $columns.style.display = 'none';
    $layoutCanvas.style.display = '';
    // 初始化 LayoutMode 单例
    if (!_layoutMode) {
      _layoutMode = new LayoutMode(document.getElementById('lvLayoutCanvas'));
      if (_stagingPanel) _stagingPanel.setLayoutMode(_layoutMode);
    }
    const data = _buildLineageData();
    _layoutMode.render(data);
    // session 恢复：应用刷新前的平移/缩放
    if (_pendingLayoutPan != null) {
      _layoutMode._panX = _pendingLayoutPan.x;
      _layoutMode._panY = _pendingLayoutPan.y;
      if (_pendingLayoutZoom != null) _layoutMode._zoom = _pendingLayoutZoom;
      _layoutMode._setTransform();
      _layoutMode._syncMinimapViewport();
      _pendingLayoutPan = null;
      _pendingLayoutZoom = null;
    }
    // 同步数据引用到底部详情面板
    if (_layoutDetailPanel) _layoutDetailPanel.updateData(data);
    // 同步编辑模式状态到 LayoutMode
    _layoutMode.setEditMode(_layoutEditMode);
  }
  _syncLayoutUI();
}

/**
 * 收集 lineage 数据引用供 layout_mode.js 使用
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
    showEntityDetailPopover: _openEntityDetailPopover,
    openImageLightbox: _openImageLightbox,
    openParentPicker:  _openParentPicker,
    toast:        _toast,
    cf:           _cf,
    stagingPanel: _stagingPanel,
    assocPanel:   _assocPanel,
    layoutDetailPanel: _layoutDetailPanel,
    versionStatus: _versionStatus,
    isEditable:    _isVersionEditable(),
    lineGrantSet:  _lineGrantSet,
    lineReadOnly:  _lineReadOnly,
    collectLinkAlerts: _collectLinkAlerts,
    renderLinkAlerts:  _renderLinkAlerts,
    runAutoLink:       _runAutoLink,
    renderPicArea:     _renderPicArea,
    patchEntry:        _patchEntry,
    startInlineRename: _startInlineRename,
    preserveView: () => { if (_viewMode === 'layout' && _layoutMode) _layoutMode._preserveView = true; },
    onLineFilterChange: (newFilter) => {
      _level1Filter = newFilter;
      // 若工具栏下拉已打开，同步刷新其勾选状态
      if ($l1DD.style.display !== 'none') _buildLevel1Dropdown();
      _applyFilters();
    },
    reloadData: async () => {
      if (_viewMode === 'layout' && _layoutMode) _layoutMode._preserveView = true;
      await _reload();
    },
    // 多项目对比
    projectVersions: _projectVersions,
    projectColors: new Map(_projectVersions.map((p, i) => [p.versionGid, { color: _PROJECT_COLORS[i] || '#888', label: String.fromCharCode(65 + i) }])),
  };
}

/**
 * 同步布局模式相关 UI（工具栏按钮显示/隐藏、分段开关激活状态）
 */
function _normalizePicItems(items) {
  const out = [];
  for (const item of items || []) {
    if (item && typeof item === 'object' && !Array.isArray(item)) {
      const pic = {
        url: String(item.url || '').trim(),
        object_key: String(item.object_key || '').trim(),
        storage: String(item.storage || '').trim(),
      };
      if (pic.url || pic.object_key) out.push(pic);
    } else if (typeof item === 'string') {
      const url = item.trim();
      if (url) out.push({ url, object_key: '', storage: '' });
    }
  }
  return out;
}

async function _resolvePicItem(pic) {
  if (!pic) return null;
  const normalized = typeof pic === 'string'
    ? { url: pic, object_key: '', storage: '' }
    : {
        url: String(pic.url || '').trim(),
        object_key: String(pic.object_key || '').trim(),
        storage: String(pic.storage || '').trim(),
      };
  if (normalized.storage === 'ois' && normalized.object_key) {
    try {
      const resolved = await _cf('/api/uploads/ois/resolve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ object_key: normalized.object_key }),
      });
      if (resolved?.url) return { ...normalized, url: resolved.url };
    } catch (_) {}
  }
  if (normalized.url) {
    const abs = window.AI00RuntimeConfig?.toAbsoluteBackendUrl?.(normalized.url) || normalized.url;
    return { ...normalized, url: abs };
  }
  return normalized.object_key ? normalized : null;
}

async function _resolvePicItems(items) {
  const resolved = [];
  for (const item of _normalizePicItems(items)) {
    const pic = await _resolvePicItem(item);
    if (pic) resolved.push(pic);
  }
  return resolved;
}

function _syncLayoutUI() {
  const isLayout = _viewMode === 'layout';
  // 不在这里显隐画布，让 _render() 控制时机，避免闪烁

  // 更新分段切换按钮激活状态
  document.querySelectorAll('.lv-vtog-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.mode === _viewMode);
  });

  // 布局模式下显示适应全局按钮和编辑按钮
  if ($layoutEditBtn) $layoutEditBtn.style.display = isLayout ? '' : 'none';
  $layoutFitBtn.style.display = isLayout ? '' : 'none';
  if ($importTcBtn) $importTcBtn.style.display = isLayout ? '' : 'none';
  const $layoutSep = document.getElementById('lvLayoutSep');
  if ($layoutSep) $layoutSep.style.display = isLayout ? '' : 'none';
  // 确保编辑按钮 active 类与状态同步
  if ($layoutEditBtn) $layoutEditBtn.classList.toggle('active', isLayout && _layoutEditMode);

  // 列视图专用控件：布局模式下隐藏
  const columnsOnlyControls = [
    document.getElementById('lvAddNode'),
    document.getElementById('lvMaxDepthWrap'),
    document.getElementById('lvExpandAll'),
    document.getElementById('lvCollapseAll'),
    document.getElementById('lvZoomWrap'),
    document.getElementById('lvColumnsSep'),
  ];
  for (const el of columnsOnlyControls) {
    if (el) el.style.display = isLayout ? 'none' : '';
  }

  // 切到列视图时关闭底部详情面板（不标记 userClosed）
  if (!isLayout && _layoutDetailPanel) {
    if (typeof _layoutDetailPanel.dismiss === 'function') _layoutDetailPanel.dismiss();
  }

  // 布局视图下隐藏右侧 assoc_panel（功能已集成到底部七列面板）
  // 列视图下恢复显示
  const $assocPanel = document.getElementById('lvAssoc');
  if ($assocPanel) $assocPanel.style.display = isLayout ? 'none' : '';
  const $rulePanel = document.getElementById('lvRulePanel');
  if ($rulePanel) $rulePanel.style.display = isLayout ? 'none' : '';
  const $refPanel  = document.getElementById('lvRefPanel');
  if ($refPanel) $refPanel.style.display = isLayout ? 'none' : '';
  const $lcTop = document.getElementById('lvLifecycleTop');
  const $lcAction = document.getElementById('lvLifecycleAction');
  if ($lcTop) $lcTop.style.display = isLayout ? '' : 'none';
  if ($lcAction) $lcAction.style.display = isLayout ? '' : 'none';
  const $historySidePanel = document.getElementById('lvHistorySidePanel');
  if ($historySidePanel) $historySidePanel.style.display = isLayout ? '' : 'none';

  // 布局视图下显示"对比项目"按钮，切到列视图时隐藏并清空对比状态
  const $compareWrap = document.getElementById('lvCompareWrap');
  if ($compareWrap) $compareWrap.style.display = isLayout ? '' : 'none';
  if (!isLayout && _projectVersions.length > 1) {
    _clearCompareVersions();
  }

  if (isLayout && _lifecyclePanel && _versionGid) {
    _lifecyclePanel.refresh();
  }
}

/**
 * 应用本地亮/暗主题（data-lv-theme 属性控制 Catppuccin Latte/Mocha 切换）
 */
function _applyLvTheme() {
  const theme = _viewMode === 'layout' ? _lvThemeLayout : _lvThemeColumns;
  if (theme === 'light') {
    document.documentElement.setAttribute('data-lv-theme', 'light');
  } else {
    document.documentElement.removeAttribute('data-lv-theme');
  }
  const btn   = document.getElementById('lvThemeToggle');
  const icon  = document.getElementById('lvThemeIcon');
  const label = document.getElementById('lvThemeLabel');
  if (!btn) return;
  const isLight = theme === 'light';
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

  // 计算可见 gid 集合：所有已选树深度=0 根节点的后代
  const visibleGids = new Set();
  const hasRoots = (_childMap.get(null) || []).some(r => _treeDepth(r) === 0);
  if (hasRoots) {
    for (const gid of _selectedRoots) _collectDescendants(gid, visibleGids);
  } else {
    // 无深度=0 节点时，所有行可见
    _rows.forEach(r => visibleGids.add(r.gid));
  }

  // 第1级（线体）筛选：若 _level1Filter 有选中项，只显示这些线体及其后代
  const l1AllowedSet = _buildL1AllowedSet();

  // 按树深度分组（跳过深度=0，从 1 开始作为第一列）
  const levelMap = new Map();
  for (const r of _rows) {
    const lv = _treeDepth(r);
    if (lv === 0) continue;                          // 深度=0 节点在根选择栏显示，不作卡片
    if (hasRoots && !visibleGids.has(r.gid)) continue; // 未选中根节点的后代不显示
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
  typeEl.className = `lv-type lv-nt-${row.node_type || 'unknown'}`;
  typeEl.textContent = NT_ABBR[row.node_type] || row.node_type || '?';
  row1El.appendChild(typeEl);

  if (row.status) {
    const stEl = document.createElement('span');
    stEl.className = `lv-status lv-st-${row.status}`;
    stEl.title = row.status;
    row1El.appendChild(stEl);
  }

  // link_status 4 态徽标
  const linkStatus = row.link_status || 'none';
  if (linkStatus === 'linked') {
    const badge = document.createElement('span');
    badge.className = 'lv-link-badge lv-ls-linked';
    badge.textContent = row.valid_primary_link_count || '✓';
    badge.title = `已关联 ${row.valid_primary_link_count || 0} 个有效实体`;
    row1El.appendChild(badge);
  } else if (linkStatus === 'stale') {
    const badge = document.createElement('span');
    badge.className = 'lv-link-badge lv-ls-stale';
    badge.textContent = '⚠';
    badge.title = '关联目标已失效，需修复';
    row1El.appendChild(badge);
  } else if (linkStatus === 'missing') {
    const badge = document.createElement('span');
    badge.className = 'lv-link-badge lv-ls-missing';
    badge.title = '缺少主关联，需要 Auto-Link 或手动关联';
    row1El.appendChild(badge);
  } else if (linkStatus === 'none') {
    const badge = document.createElement('span');
    badge.className = 'lv-link-badge lv-ls-none';
    badge.title = '未关联';
    row1El.appendChild(badge);
  }

  const seqEl = document.createElement('span');
  seqEl.style.cssText = 'font-size:10px;color:var(--subtext0,#a6adc8);margin-left:auto;white-space:nowrap';
  seqEl.textContent = row.bom_row_id || '';
  seqEl.title = row.bom_row_id ? `零组件ID: ${row.bom_row_id}` : '';

  // 跟踪关联徽标（问题/任务等 is_primary=false 的关联数量）
  const trackCnt = row.tracking_link_count || 0;
  if (trackCnt > 0) {
    const trackBadge = document.createElement('span');
    trackBadge.className = 'lv-link-badge lv-link-badge-track';
    trackBadge.textContent = trackCnt;
    trackBadge.title = `${trackCnt} 个跟踪关联（问题/任务等）`;
    row1El.appendChild(trackBadge);
  }

  row1El.appendChild(seqEl);

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
    const _abs = s => window.AI00RuntimeConfig?.toAbsoluteBackendUrl?.(typeof s === 'string' ? s : '') || s;
    const firstPic = _abs(typeof pics[0] === 'string' ? pics[0] : (pics[0]?.url || pics[0]?.src || ''));
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

/**
 * 收集工序节点自身及其直接 operation 子节点的 process_flow_pic 第一张图
 */
function _collectProcessPics(gid) {
  const _abs = s => window.AI00RuntimeConfig?.toAbsoluteBackendUrl?.(typeof s === 'string' ? s : '') || s;
  const pics = [];
  const _addFirst = r => {
    const v = r?.process_flow_pic;
    const raw = Array.isArray(v) ? v[0] : (typeof v === 'string' ? v : null);
    const s = _abs(typeof raw === 'string' ? raw : (raw?.url || raw?.src || ''));
    if (s) pics.push(s);
  };
  _addFirst(_rowByGid.get(gid));
  for (const child of (_childMap.get(gid) || [])) {
    if (child.node_type === 'operation') _addFirst(child);
  }
  return pics;
}

/**
 * 工序节点统计框：取自身或子 operation 第一张 process_flow_pic 做单图填充
 * 点击后灯箱展示全部图（由 layout_mode.js click handler 收集）
 */
function _renderProcessCollageBox(box, gid, desc) {
  const pics = _collectProcessPics(gid);
  if (!pics.length) {
    _renderRegularStatsRows(box, desc, _PROCESS_STATS_PRIORITY);
    return;
  }
  const fill = document.createElement('div');
  fill.className = 'lv-stats-thumb-fill';
  fill.title = '工艺流程图（点击灯箱）';
  const img = document.createElement('img');
  img.className = 'lv-thumb-fill';
  img.src = pics[0];
  img.alt = 'process_flow_pic';
  img.onerror = function () {
    fill.innerHTML = '';
    fill.appendChild(_makeStatsRow('—'));
  };
  fill.appendChild(img);
  box.appendChild(fill);
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
    _renderProcessCollageBox(box, row.gid, desc);
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
  $sbToggle.innerHTML = _sidebarOpen ? '&#x25B6;' : '&#x25C0;';
  $sbToggle.title = _sidebarOpen ? '折叠边栏' : '展开边栏';
}

// ── 工具栏 FAB 切换 ───────────────────────────────────────────────────
function _toggleToolbar() {
  _toolbarOpen = !_toolbarOpen;
  const tb = document.getElementById('lvToolbar');
  const fab = document.getElementById('lvToolbarFab');
  if (tb) tb.classList.toggle('lv-tb-hidden', !_toolbarOpen);
  if (fab) fab.classList.toggle('lv-fab-active', _toolbarOpen);
  try { localStorage.setItem(_lsk('lv:toolbarOpen'), _toolbarOpen ? '1' : '0'); } catch (_) {}
}

/** 暂存箱折叠/展开（现在由 layout_detail_panel.js 的 stgToggle 管理水平折叠） */
function _applyStagingCollapse() {
  // 暂存箱水平折叠现在由 LayoutDetailPanel 控制，此处仅同步计数高亮
  if (!$stagingCount) return;
  $stagingCount.classList.toggle('highlight', parseInt($stagingCount.textContent) > 0);
}

/** 初始化暂存箱 + 关联面板（在 init 中调用） */
function _initSidebarPanels() {
  // 暂存箱 DOM 已移除（七列面板重构），跳过初始化
  if ($stagingBody) {
    _stagingPanel = new StagingPanel({
    bodyEl:     $stagingBody,
    countEl:    $stagingCount,
    versionGid: _versionGid,
    cf:         _cf,
    toast:      _toast,
    onPromote:  async () => { await _reload(); if (_assocPanel) _assocPanel.refresh(); },
    onDemote:   async () => { await _reload(); if (_assocPanel) _assocPanel.refresh(); },
    onDblClick: (item) => _openStagingOverlay(item),
    onCountChange: (count) => {
      $stagingCount.classList.toggle('highlight', count > 0);
    },
    showDetailPopover: _openDetailPopover,
  });

  // "+" 新建暂存项
  if ($stagingAdd) {
    $stagingAdd.addEventListener('click', async () => {
      const result = await _promptText('新建暂存项');
      if (result && result.title) {
        _stagingPanel.createManual(result.title, result.nodeType || 'process');
      }
    });
  }

  // 暂存箱折叠/展开（水平折叠现在由 LayoutDetailPanel 管理）
  _applyStagingCollapse();
  } // end if ($stagingBody)

  // 关联面板
  _assocPanel = new AssocPanel({
    tabsEl:     $assocTabs,
    bodyEl:     $assocBody,
    versionGid: _versionGid,
    cf:         _cf,
    toast:      _toast,
    onActionComplete: () => _reload(),
    applyActiveState: _applyActiveState,
    // Demo 动画回调
    getBopLinkedNodes: () => {
      const types = new Set(['process', 'operation', 'part']);
      const linked = _rows.filter(r => types.has(r.node_type) && r.vpps);
      // 找工位祖先的 sort_order
      const stationOrder = (row) => {
        let cur = row;
        for (let i = 0; i < 6 && cur; i++) {
          if (cur.node_type === 'station_process') return cur.sort_order ?? 999;
          cur = _rowByGid.get(cur.parent_gid);
        }
        return 999;
      };
      linked.sort((a, b) => {
        const ao = stationOrder(a), bo = stationOrder(b);
        return ao !== bo ? ao - bo : (a.sort_order ?? 0) - (b.sort_order ?? 0);
      });
      return linked;
    },
    demoHideNodes: (gids) => {
      const s = new Set(gids);
      document.querySelectorAll('#lvColumns .lv-card[data-gid], #llWorld .ll-ring-card[data-gid]').forEach(c => {
        if (s.has(c.dataset.gid)) { c.classList.add('lv-demo-pending'); c.classList.remove('lv-demo-reveal'); }
      });
    },
    demoRevealNode: (gid) => {
      let found = false;
      document.querySelectorAll(`#lvColumns .lv-card[data-gid="${gid}"], #llWorld .ll-ring-card[data-gid="${gid}"]`).forEach(c => {
        c.classList.remove('lv-demo-pending'); c.classList.add('lv-demo-reveal'); found = true;
      });
      return found;
    },
    demoCleanup: () => {
      document.querySelectorAll(
        '#lvColumns .lv-demo-pending, #lvColumns .lv-demo-reveal, #llWorld .lv-demo-pending, #llWorld .lv-demo-reveal'
      ).forEach(el => el.classList.remove('lv-demo-pending', 'lv-demo-reveal'));
    },
    demoSetupView: (stationGid) => {
      if (!_layoutMode) return;
      const newZoom = 0.61;
      _layoutMode._zoom = newZoom;
      if (stationGid) {
        const el = _layoutMode._world?.querySelector(`.ll-station-card[data-gid="${stationGid}"]`);
        if (el) {
          const cx = (parseFloat(el.style.left) || 0) + (el.offsetWidth || 0) / 2;
          const cy = (parseFloat(el.style.top) || 0) + (el.offsetHeight || 0) / 2;
          const vw = _layoutMode._viewport.clientWidth;
          const vh = _layoutMode._viewport.clientHeight;
          _layoutMode._panX = vw / 2 - cx * newZoom;
          _layoutMode._panY = vh / 2 - cy * newZoom - 120;
        }
      }
      _layoutMode._setTransform();
      _layoutMode._syncZoomDependent?.();
      _layoutMode._updateZoomLabel?.();
      _layoutMode._syncMinimapViewport?.();
    },
    demoPanToStation: (stationGid) => {
      if (!_layoutMode) return;
      const el = _layoutMode._world?.querySelector(`.ll-station-card[data-gid="${stationGid}"]`);
      if (!el) return;
      const cx = (parseFloat(el.style.left) || 0) + (el.offsetWidth || 0) / 2;
      // 只做水平平移，Y 轴保持不动
      const zoom = _layoutMode._zoom;
      const vw = _layoutMode._viewport.clientWidth;
      const targetPanX = vw / 2 - cx * zoom;
      const startPanX = _layoutMode._panX;
      if (Math.abs(targetPanX - startPanX) < 2) return; // 无需移动
      const dur = 600;
      const t0 = performance.now();
      const tick = (now) => {
        const t = Math.min((now - t0) / dur, 1);
        const ease = t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
        _layoutMode._panX = startPanX + (targetPanX - startPanX) * ease;
        _layoutMode._setTransform();
        if (t < 1) requestAnimationFrame(tick);
        else _layoutMode._syncMinimapViewport?.();
      };
      requestAnimationFrame(tick);
    },
    onEntityClick: (bopEntryGid, anchorEl) => {
      // 直接跳转到被关联的 bop_entry 卡片
      if (_viewMode === 'layout' && _layoutMode) {
        _layoutMode.highlightNode(bopEntryGid);
        _layoutMode.scrollToNode(bopEntryGid);
      } else {
        _applyActiveState(bopEntryGid);
      }
      // 底部详情面板也导航到该卡片
      if (_layoutDetailPanel) _layoutDetailPanel.open(bopEntryGid);
    },
    resolveStation: (bopEntryGid) => {
      // 返回被关联 bop_entry 自身的名称
      const row = _rowByGid.get(bopEntryGid);
      return row ? (row.title || row.vpps || bopEntryGid) : null;
    },
    showDetailPopover: _openDetailPopover,
    showEntityDetailPopover: _openEntityDetailPopover,
  });
  // _initPanelDivider(); // 已移除

  // 加载暂存数据
  if (_stagingPanel) _stagingPanel.load();
}

/** 分割条拖拽逻辑（已废用：分割条现为纯视觉分隔，不再拖拽调整） */
function _initPanelDivider() {
  // No-op — sidebar panel divider is now a static separator between cpanels and assoc panel
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

  // 收集所有 line_process 节点（不依赖树深度，避免无 factory_bop 根时误匹配工位）
  const l1Nodes = _rows.filter(r => r.node_type === 'line_process');

  if (l1Nodes.length === 0) {
    const msg = document.createElement('div');
    msg.className = 'lv-root-picker-msg';
    msg.textContent = '暂无第1级节点';
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
  allItem.appendChild(document.createTextNode('全部线体'));
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
    if (checked.length === l1Nodes.length) {
      _level1Filter = null; // 全选 = null（全部显示）
    } else {
      _level1Filter = new Set(checked);
    }
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

  // 同步关联面板高亮
  if (_assocPanel) _assocPanel.highlightLinkedEntity(activeGid);

  if (_viewMode === 'layout' && _lifecyclePanel) {
    _lifecyclePanel.setActiveEntry(activeGid);
    let lineCursor = activeRow;
    while (lineCursor?.parent_gid) {
      lineCursor = _rowByGid.get(lineCursor.parent_gid);
    }
    if (lineCursor?.node_type === 'line_process') {
      _lifecyclePanel.setActiveLine(lineCursor.gid);
    }
  }
}

// ── 过滤应用 ─────────────────────────────────────────────────────────

function _canEditCurrentLine() {
  if (!_lineReadOnly) return true;
  if (!_activeGid) return false;
  let lineCursor = _rowByGid.get(_activeGid);
  while (lineCursor?.parent_gid) {
    lineCursor = _rowByGid.get(lineCursor.parent_gid);
  }
  if (!lineCursor || lineCursor.node_type !== 'line_process') return false;
  return _lineGrantSet.has(lineCursor.gid);
}

function _applyFilters() {
  if (_viewMode === 'layout' && _layoutMode) {
    _layoutMode._preserveView = true;
  }
  _render();
  if (_activeGid) _applyActiveState(_activeGid);
  // 筛选变更后自动持久化到 localStorage（无需手动"保存视图"）
  _autoSaveFilters();
}

function _autoSaveFilters() {
  try {
    const state = {
      typeFilter:   _typeFilter,
      level1Filter: _level1Filter === null ? null : [..._level1Filter],
    };
    localStorage.setItem(_lsk('lv:filters'), JSON.stringify(state));
  } catch {}
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
  if (!_canEditEntry(gid)) {
    throw new Error('当前线体无编辑权限（只读）');
  }
  await _cf(`/api/bop/entries/${gid}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

/**
 * 通用"父级/目标节点选择器"对话框。
 * @param {Object} opts
 * @param {string}      opts.title       - 对话框标题
 * @param {string|null} opts.excludeGid  - 排除的 gid（防止选自身及其后代）
 * @param {string|null} opts.defaultType - 默认筛选类型
 * @returns {Promise<{gid,title,node_type}|null>}
 */
async function _openParentPicker(opts = {}) {
  return new Promise(resolve => {
    // overlay
    const overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:10000;display:flex;align-items:center;justify-content:center';

    const dlg = document.createElement('div');
    dlg.className = 'lv-pp-dialog';
    dlg.innerHTML = `
      <div class="lv-pp-title">${opts.title || '选择目标节点'}</div>
      <div class="lv-pp-row">
        <label>类型:</label>
        <select class="lv-pp-type-sel"></select>
      </div>
      <div class="lv-pp-row">
        <label>搜索:</label>
        <input type="search" class="lv-pp-search" placeholder="输入关键字…">
      </div>
      <div class="lv-pp-results"></div>
      <div class="lv-pp-actions">
        <button class="lv-btn lv-pp-cancel">取消</button>
        <button class="lv-btn lv-pp-ok" disabled>确定</button>
      </div>`;
    overlay.appendChild(dlg);

    const typeSel = dlg.querySelector('.lv-pp-type-sel');
    const searchInput = dlg.querySelector('.lv-pp-search');
    const resultEl = dlg.querySelector('.lv-pp-results');
    const okBtn = dlg.querySelector('.lv-pp-ok');
    const cancelBtn = dlg.querySelector('.lv-pp-cancel');

    // 类型下拉
    const allOpt = document.createElement('option');
    allOpt.value = ''; allOpt.textContent = '全部类型';
    typeSel.appendChild(allOpt);
    for (const [val, label] of _ORDERED_NODE_TYPES) {
      const o = document.createElement('option');
      o.value = val; o.textContent = label;
      if (val === opts.defaultType) o.selected = true;
      typeSel.appendChild(o);
    }

    let selectedGid = null;

    // 排除集合（excludeGid 及其后代）
    const excludeSet = new Set();
    if (opts.excludeGid) {
      const buildExclude = gid => {
        excludeSet.add(gid);
        const children = _childMap.get(gid) || [];
        for (const c of children) buildExclude(c.gid);
      };
      buildExclude(opts.excludeGid);
    }

    function doSearch() {
      const q = searchInput.value.trim().toLowerCase();
      const ntFilter = typeSel.value;
      const results = [];
      for (const [gid, row] of _rowByGid) {
        if (excludeSet.has(gid)) continue;
        if (ntFilter && row.node_type !== ntFilter) continue;
        if (q) {
          const haystack = ((row.title || '') + ' ' + (row.vpps || '') + ' ' + (row.bom_row_id || '')).toLowerCase();
          if (!haystack.includes(q)) continue;
        }
        results.push(row);
        if (results.length >= 50) break;
      }
      renderResults(results);
    }

    function renderResults(results) {
      resultEl.innerHTML = '';
      selectedGid = null;
      okBtn.disabled = true;
      if (results.length === 0) {
        resultEl.innerHTML = '<div class="lv-pp-empty">无匹配结果</div>';
        return;
      }
      for (const row of results) {
        const item = document.createElement('div');
        item.className = 'lv-pp-result-item';
        item.dataset.gid = row.gid;

        const ntColor = _getNtColor(row.node_type);
        const ntLabel = NT_ABBR[row.node_type] || row.node_type || '—';
        item.innerHTML = `<span class="lv-pp-dot" style="background:${ntColor}"></span>`
          + `<span class="lv-pp-item-title">${_esc(row.title || '(无名称)')}</span>`
          + (row.vpps ? `<span class="lv-pp-item-vpps">${_esc(row.vpps)}</span>` : '')
          + `<span class="lv-pp-item-nt">${_esc(ntLabel)}</span>`;

        item.addEventListener('click', () => {
          resultEl.querySelectorAll('.lv-pp-result-item.selected').forEach(el => el.classList.remove('selected'));
          item.classList.add('selected');
          selectedGid = row.gid;
          okBtn.disabled = false;
        });
        item.addEventListener('dblclick', () => {
          cleanup();
          resolve({ gid: row.gid, title: row.title, node_type: row.node_type });
        });
        resultEl.appendChild(item);
      }
    }

    let debounceTimer = null;
    searchInput.addEventListener('input', () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(doSearch, 200);
    });
    typeSel.addEventListener('change', doSearch);

    okBtn.addEventListener('click', () => {
      if (!selectedGid) return;
      const row = _rowByGid.get(selectedGid);
      cleanup();
      resolve(row ? { gid: row.gid, title: row.title, node_type: row.node_type } : null);
    });

    cancelBtn.addEventListener('click', () => { cleanup(); resolve(null); });
    overlay.addEventListener('click', e => { if (e.target === overlay) { cleanup(); resolve(null); } });
    document.addEventListener('keydown', onKey);
    function onKey(e) { if (e.key === 'Escape') { cleanup(); resolve(null); } }
    function cleanup() { document.removeEventListener('keydown', onKey); overlay.remove(); }

    document.body.appendChild(overlay);
    searchInput.focus();
    doSearch(); // 初始渲染
  });
}

// 辅助：NT 颜色（供 _openParentPicker 使用）
function _getNtColor(nt) {
  // 与 lineage.css .lv-nt-* 保持完全一致
  const colors = {
    factory_bop:         '#6c8ebf',
    line_process:        '#74c7ec',
    station_process:     '#fab387',
    operator_process:    '#cba6f7',
    man:                 '#9b59b6',
    station_factory:     '#5b8dd9',
    process:             '#89b4fa',
    equipment_factory:   '#94e2d5',
    tool_factory:        '#89dceb',
    equipment_need:      '#74c7ec',
    fixture_factory:     '#d3875a',
    operation:           '#a6adc8',
    issue:               '#6c7086',
    standard_task:       '#2980b9',
    non_standard_task:   '#1a6795',
    contral_plan:        '#8e44ad',
    process_chart:       '#7d3a9e',
    floor_height_factory:'#5dade2',
    knowledge:           '#b4befe',
    rule:                '#fab387',
    part:                '#7f8c8d',
    non_standard_part:   '#6a7778',
    standard_part:       '#95a5a6',
    support_material:    '#bdc3c7',
    tool_need:           '#cba6f7',
    fixture_need:        '#d3875a',
    jack_pos:            '#884ea0',
  };
  return colors[nt] || '#7c7f93';
}

function _esc(s) {
  if (!s) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ── 内联改名 ─────────────────────────────────────────────────────────

function _startInlineRename(cardEl) {
  const gid      = cardEl.dataset.gid;
  // 支持列视图（.lv-title）和布局视图工位卡片（.ll-station-title）
  const titleEl  = cardEl.querySelector('.lv-title') || cardEl.querySelector('.ll-station-title');
  const row      = _rowByGid.get(gid);
  if (!titleEl || !row) return;

  let _committed = false;

  const input = document.createElement('input');
  input.className = 'lv-inline-input';
  input.value = row.title || '';
  titleEl.replaceWith(input);
  input.focus();
  input.select();

  // 安全恢复：若 input 已被从 DOM 移除（如外部重渲染），直接放弃
  const _safeRestore = () => {
    if (_committed) return;
    _committed = true;
    try {
      if (input.isConnected) input.replaceWith(titleEl);
    } catch (_) { /* 外部 re-render 已移除 DOM，忽略 */ }
  };

  const commit = async () => {
    if (_committed) return;
    _committed = true;
    const newTitle = input.value.trim();
    if (!newTitle || newTitle === row.title) {
      _safeRestore();
      return;
    }
    try {
      await _patchEntry(gid, { title: newTitle });
      row.title = newTitle;
      titleEl.textContent = newTitle;
      try {
        if (input.isConnected) input.replaceWith(titleEl);
      } catch (_) { /* DOM 可能在 _patchEntry 期间被重新渲染，忽略 */ }
      _toast('已保存', 'ok', 1500);
      // 同步主视图其他同 gid 卡片（布局视图工位/环形卡片）
      document.querySelectorAll(`[data-gid="${gid}"] .lv-title, [data-gid="${gid}"] .ll-station-title`)
        .forEach(el => { if (el !== titleEl && !el.matches('input')) el.textContent = newTitle; });
      // 同步详情面板 title 输入框
      if (_layoutDetailPanel?._currentGid === gid) {
        const inp = _layoutDetailPanel._propsBody?.querySelector('#llPropsTitleInp');
        if (inp) inp.value = newTitle;
      }
    } catch (e) {
      _safeRestore();
      _toast('保存失败: ' + e.message, 'error');
    }
  };

  input.addEventListener('blur',    commit);
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter')  { e.preventDefault(); commit(); }
    if (e.key === 'Escape') { _safeRestore(); }
  });
}

// ── 节点类型配置（新建弹窗，operation 优先顺序）──────────────────────

// 类型顺序：从操作（叶子）到线体（根），资源类，最后工作项/零件
const _ORDERED_NODE_TYPES = [
  ['operation',        '总装操作'],
  ['process',          '总装工序'],
  ['operator_process', '岗位'],
  ['station_process',  '总装工位工艺'],
  ['line_process',     '总装线体工艺'],
  ['man',              '人'],
  ['station_factory',  '工厂工位'],
  ['equipment_factory','设备(工厂)'],
  ['tool_factory',     '工具(工厂)'],
  ['fixture_factory',  '工装(工厂)'],
  ['equipment_need',   '设备(需求)'],
  ['tool_need',        '工具(需求)'],
  ['fixture_need',     '工装(需求)'],
  ['part',             '零部件'],
  ['knowledge',        '知识'],
  ['rule',             '规则'],
  ['issue',            '问题'],
  ['standard_task',    '标准任务'],
];

// 建议子节点类型映射（根据父节点类型）
const _CHILD_TYPE_MAP = {
  factory_bop:      'line_process',
  line_process:     'station_process',
  station_process:  'operator_process',
  operator_process: 'process',
  process:          'operation',
};

// 变更父级时的预设父节点类型（_CHILD_TYPE_MAP 的反向）
const _PARENT_TYPE_MAP = {
  line_process:     'factory_bop',
  station_process:  'line_process',
  operator_process: 'station_process',
  process:          'operator_process',
  operation:        'process',
};

// 各类型的表单字段定义
// type: 'text' | 'number' | 'select' | 'pics'
const _NODE_FIELDS = {
  operation:        [{ id:'title', label:'名称', type:'text', required:true },
                     { id:'pic_flow',  label:'工艺流程图（最多15张）', type:'pics', picField:'process_flow_pic',  max:15 },
                     { id:'pic_chart', label:'工艺卡图片（最多15张）', type:'pics', picField:'process_chart_pic', max:15 }],
  process:          [{ id:'title', label:'名称', type:'text', required:true },
                     { id:'pic_flow',  label:'工艺流程图（最多15张）', type:'pics', picField:'process_flow_pic',  max:15 },
                     { id:'pic_chart', label:'工艺卡图片（最多15张）', type:'pics', picField:'process_chart_pic', max:15 }],
  operator_process: [{ id:'title', label:'名称', type:'text', required:true },
                     { id:'position', label:'位置（A-F 可选）', type:'select',
                       options:[['','无'],['A','A'],['B','B'],['C','C'],['D','D'],['E','E'],['F','F']] }],
  station_process:  [{ id:'title', label:'名称', type:'text', required:true },
                     { id:'side', label:'侧别', type:'select',
                       options:[['','无'],['L','左 L'],['R','右 R'],['M','中 M']] }],
  line_process:     [{ id:'title', label:'名称', type:'text', required:true }],
  man:              [{ id:'title', label:'名称', type:'text', required:true }],
  station_factory:  [{ id:'title', label:'名称', type:'text', required:true }],
  equipment_factory:[{ id:'title', label:'名称', type:'text', required:true }],
  tool_factory:     [{ id:'title', label:'名称', type:'text', required:true }],
  fixture_factory:  [{ id:'title', label:'名称', type:'text', required:true }],
  equipment_need:   [{ id:'title', label:'名称', type:'text', required:true }],
  tool_need:        [{ id:'title', label:'名称', type:'text', required:true }],
  fixture_need:     [{ id:'title', label:'名称', type:'text', required:true }],
  part:             [{ id:'title', label:'名称', type:'text', required:true },
                     { id:'bom_row_id', label:'物料编号', type:'text' }],
  knowledge:        [{ id:'title', label:'名称', type:'text', required:true }],
  rule:             [{ id:'title', label:'名称', type:'text', required:true }],
  issue:            [{ id:'title', label:'名称', type:'text', required:true }],
  standard_task:    [{ id:'title', label:'名称', type:'text', required:true }],
};

/**
 * 上传图片到 /api/bop/pics/upload，返回 URL
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
        const res = await _cf('/api/bop/pics/upload', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ filename: file.name, mime, data_b64: b64 }),
        });
        if (!res?.url) throw new Error('上传失败：无返回 URL');
        resolve({
          url: res.url,
          object_key: res.object_key || '',
          storage: res.storage || '',
        });
      } catch (e) { reject(e); }
    };
    reader.readAsDataURL(file);
  });
}

/**
 * 渲染图片管理区 DOM（新建弹窗 & 详情面板共用）
 * container: 挂载目标 el
 * urls: {url, object_key, storage}[] 当前已有图片
 * max: 最大数量
 * onChange: (items) => void
 */
function _renderPicArea(container, urls, max, onChange) {
  container.innerHTML = '';
  const area = document.createElement('div');
  area.className = 'lv-pic-area';

  async function refresh(items) {
    area.innerHTML = '';
    const resolved = await _resolvePicItems(items);
    resolved.forEach((pic, i) => {
      const thumb = document.createElement('div');
      thumb.className = 'lv-pic-thumb';
      thumb.innerHTML = `<img src="${pic.url || ''}" title="点击全屏预览"><button class="lv-pic-del" title="删除">×</button>`;
      thumb.querySelector('img').addEventListener('click', () => {
        if (!pic.url) return;
        const win = window.open();
        win.document.write(`<body style="margin:0;background:#000"><img src="${pic.url}" style="max-width:100vw;max-height:100vh;object-fit:contain;display:block;margin:auto"></body>`);
      });
      thumb.querySelector('.lv-pic-del').addEventListener('click', () => {
        items.splice(i, 1);
        onChange([...items]);
        refresh(items);
      });
      area.appendChild(thumb);
    });

    if (items.length < max) {
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
        const files = Array.from(fileInput.files).slice(0, max - items.length);
        if (!files.length) return;
        const status = document.createElement('span');
        status.className = 'lv-pic-uploading';
        status.textContent = '上传中…';
        area.appendChild(status);
        try {
          for (const f of files) {
            if (items.length >= max) break;
            const pic = await _uploadBopPic(f);
            items.push(pic);
          }
          onChange([...items]);
          refresh(items);
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

  refresh(_normalizePicItems(urls));
  container.appendChild(area);
}

// ── 内联对话框（Electron 兼容，替代 prompt/confirm）─────────────────
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
      const type = typeSelect.value;
      fieldsWrap.innerHTML = '';

      // ── station_process 自动命名（父节点为 line_process 时）─────────
      const isAutoStation = type === 'station_process' &&
                            action === 'add_child' &&
                            refRow?.node_type === 'line_process';
      if (isAutoStation) {
        fieldsWrap.innerHTML = `
          <div class="lv-ndlg-field">
            <label>线体</label>
            <input class="lv-dialog-input" value="${_escHtml(refRow.title || '')}"
                   disabled style="opacity:.5;cursor:default">
          </div>
          <div class="lv-ndlg-field">
            <label>侧别（可选）</label>
            <select class="lv-dialog-select" id="_ndlgStSide">
              <option value="">无</option>
              <option value="L">左 L</option>
              <option value="R">右 R</option>
              <option value="M">中 M</option>
            </select>
          </div>
          <div class="lv-ndlg-field">
            <label>名称预览</label>
            <div id="_ndlgStPreview" style="padding:4px 8px;border-radius:4px;font-size:12px;
                 background:var(--surface1,#45475a);color:var(--subtext0,#a6adc8)">自动按当前线体末尾排序</div>
          </div>`;
        const sideSelect = fieldsWrap.querySelector('#_ndlgStSide');
        const preview    = fieldsWrap.querySelector('#_ndlgStPreview');
        const _upd = () => {
          const side = sideSelect.value;
          preview.textContent = (refRow.title || '') + (side || '') + '（自动排序）';
          preview.style.color = 'var(--blue,#89b4fa)';
        };
        sideSelect.addEventListener('change', _upd);
        _upd();
        return;
      }

      // ── 通用字段渲染 ────────────────────────────────────────────────
      const defs = _NODE_FIELDS[type] || [{ id:'title', label:'名称', type:'text', required:true }];
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

      // station_process 自动命名模式
      if (type === 'station_process' && action === 'add_child' && refRow?.node_type === 'line_process') {
        const sideSelect = fieldsWrap.querySelector('#_ndlgStSide');
        const side = sideSelect?.value || '';
        const title = (refRow.title || '') + (side || '');
        done({ nodeType: type, title });
        return;
      }

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
          if (el && el.value) {
            if (def.id.startsWith('meta_')) {
              // meta_ 前缀字段存入 data.meta 对象
              if (!data.meta) data.meta = {};
              data.meta[def.id.slice(5)] = el.value;
            } else {
              data[def.id] = el.value;
            }
          }
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
  if (refGid && !_canEditEntry(refGid)) {
    _toast('当前线体无编辑权限（只读）', 'warn');
    return;
  }
  const refRow = refGid ? _rowByGid.get(refGid) : null;
  const data   = await _openNodeDialog(action, refGid);
  if (!data) return;

  const { nodeType, title, bom_row_id, seq_no, position, meta,
          process_flow_pic, process_chart_pic } = data;

  let parentGid, seqNo;
  if (action === 'add_above') {
    parentGid = refRow?.parent_gid || null;
    const siblings = (_childMap.get(parentGid) || [])
      .filter(r => !r.is_deleted)
      .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));
    const idx  = siblings.findIndex(r => r.gid === refGid);
    const prev = siblings[idx - 1];
    const cur  = refRow?.sort_order ?? 0;
    if (!prev) {
      seqNo = cur - 1;
    } else if ((prev.sort_order ?? 0) === cur) {
      // 相邻节点 sort_order 相同，用索引偏移保证唯一性
      seqNo = cur - 1 + idx * 0.001;
    } else {
      seqNo = ((prev.sort_order ?? 0) + cur) / 2;
    }
  } else if (action === 'add_below') {
    parentGid = refRow?.parent_gid || null;
    const siblings = (_childMap.get(parentGid) || [])
      .filter(r => !r.is_deleted)
      .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));
    const idx  = siblings.findIndex(r => r.gid === refGid);
    const next = siblings[idx + 1];
    const cur  = refRow?.sort_order ?? 0;
    if (!next) {
      seqNo = cur + 1;
    } else if ((next.sort_order ?? 0) === cur) {
      // 相邻节点 sort_order 相同，用索引偏移保证唯一性
      seqNo = cur + 1 - (siblings.length - idx) * 0.001;
    } else {
      seqNo = (cur + (next.sort_order ?? 0)) / 2;
    }
  } else if (action === 'add_child') {
    parentGid = refGid;
    // 自动排在现有子节点末尾，避免所有子节点都堆在 sort_order=0
    const existingChildren = (_childMap.get(refGid) || []).filter(r => !r.is_deleted);
    const maxSort = existingChildren.reduce((m, r) => Math.max(m, r.sort_order ?? 0), 0);
    seqNo = seq_no ?? (maxSort + 1);
  } else {
    // add_new（工具栏）
    parentGid = _activeGid || null;
    seqNo     = seq_no ?? 0;
  }

  const body = {
    version_gid:     _versionGid,
    parent_gid:      parentGid,
    node_type:       nodeType,
    title,
    sort_order:      seqNo,
  };
  if (bom_row_id) body.bom_row_id = bom_row_id;
  if (position)   body.position   = position;
  if (meta && Object.keys(meta).length) body.meta = meta;

  try {
    _toast('创建中…', 'ok', 600);
    const resp = await _cf('/api/bop/entries', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const newGid = resp?.data?.gid;
    // 上传图片（如有）
    if (newGid && (process_flow_pic?.length || process_chart_pic?.length)) {
      const picPatch = {};
      if (process_flow_pic?.length)  picPatch.process_flow_pic  = process_flow_pic;
      if (process_chart_pic?.length) picPatch.process_chart_pic = process_chart_pic;
      await _cf(`/api/bop/entries/${newGid}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(picPatch),
      });
    }
    if (_viewMode === 'layout' && _layoutMode) _layoutMode._preserveView = true;
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
  if (!_canEditEntry(gid)) {
    _toast('当前线体无编辑权限（只读）', 'warn');
    return;
  }
  const row = _rowByGid.get(gid);
  if (!row) return;
  const ok = await _confirmDialog(`确认删除「${row.title || '(无名称)'}」？此操作不可恢复。`);
  if (!ok) return;
  try {
    await _cf(`/api/bop/entries/${gid}`, { method: 'DELETE' });
    if (_activeGid === gid) _activeGid = null;
    if (_viewMode === 'layout' && _layoutMode) _layoutMode._preserveView = true;
    await _reload();
    _toast('已删除', 'ok');
  } catch (e) {
    _toast('删除失败: ' + e.message, 'error');
  }
}

// ── 详情浮动弹窗 ──────────────────────────────────────────────────────

let _detailGid = null;

function _openDetailPopover(gid, anchorOrPos) {
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
      const nt = child.node_type || 'unknown';
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

  // 定位：锚定在锚点右侧或鼠标位置，超出底部时上移
  let anchorLeft, anchorTop;
  if (anchorOrPos instanceof HTMLElement) {
    const rect = anchorOrPos.getBoundingClientRect();
    anchorLeft = rect.right + 6;
    anchorTop  = rect.top;
  } else {
    anchorLeft = (anchorOrPos?.x ?? 0) + 4;
    anchorTop  = anchorOrPos?.y ?? 0;
  }
  $dpPopover.style.left = Math.min(anchorLeft, window.innerWidth - 280) + 'px';
  $dpPopover.style.top  = '0px';
  $dpPopover.style.display = 'block';
  // 测量实际高度后做底部溢出修正
  const pH = $dpPopover.offsetHeight;
  const maxTop   = window.innerHeight - pH - 8;
  $dpPopover.style.top = Math.max(8, Math.min(anchorTop, maxTop)) + 'px';
}

/** 打开关联实体详情弹窗（外部实体表字段，可编辑/删除关联） */
async function _openEntityDetailPopover(linkType, refGid, pos, linkGid) {
  if (!linkType || !refGid) return;
  const LINK_TYPE_LABELS = {
    asm_line_process: '线体工艺', asm_station_process: '工位工艺',
    asm_operator_process: '岗位工艺', asm_operation: '操作/工步',
    physical_station: '物理工位', physical_equipment: '物理设备',
    physical_tool: '物理工具', physical_fixture: '物理工装',
    project_equipment: '设备需求', project_tooling: '工装需求',
    project_tools: '工具需求', project_roles: '角色需求',
    issue: '问题', task_std: '标准任务', task_custom: '自定义任务',
    knowledge: '知识', rule_std: '标准规则', rule_custom: '自定义规则',
    pbom_part: '零件', floor_height: '地面高度',
    control_plan: '控制计划', process_chart: '工艺卡', jack_pos: '人机姿态',
  };
  // 不在弹窗中显示 / 不可编辑的字段
  const HIDE_KEYS = new Set(['_link_type', '_table', 'deleted_at', 'created_by', 'updated_by']);
  const READONLY_KEYS = new Set(['gid', 'created_at', 'updated_at', 'bop_version_gid', 'project_gid', 'version_gid']);

  $dpTitle.textContent = `${LINK_TYPE_LABELS[linkType] || linkType} 详情`;
  $dpBody.innerHTML = '<div style="padding:12px;color:var(--overlay0,#6c7086);font-size:11px">加载中…</div>';

  // 先显示弹窗
  const anchorLeft = (pos?.x ?? 0) + 4;
  const anchorTop  = pos?.y ?? 0;
  $dpPopover.style.left = Math.min(anchorLeft, window.innerWidth - 280) + 'px';
  $dpPopover.style.top  = anchorTop + 'px';
  $dpPopover.style.display = 'block';

  let entityData = null;
  try {
    const res = await _cf(`/api/bop/entity-detail?link_type=${encodeURIComponent(linkType)}&ref_gid=${encodeURIComponent(refGid)}`);
    entityData = res.data;
    if (!entityData) { $dpBody.innerHTML = '<div style="padding:12px;color:var(--red,#f38ba8)">实体不存在</div>'; return; }
  } catch (ex) {
    $dpBody.innerHTML = `<div style="padding:12px;color:var(--red,#f38ba8)">加载失败: ${_escHtml(ex.message)}</div>`;
    return;
  }

  const editable = _isVersionEditable();
  const origSnapshot = {};  // 加载时快照，保存按钮用它做对比
  for (const [k, v] of Object.entries(entityData)) origSnapshot[k] = v;
  const body = [];

  // ── 标题区 ──
  const nameField = entityData.title || entityData.name || entityData.part_name || entityData.step_name || '';
  if (nameField) {
    body.push(`<div style="font-size:13px;font-weight:600;color:var(--text,#cdd6f4);margin-bottom:6px;padding:0 2px">${_escHtml(nameField)}</div>`);
  }

  body.push('<div class="lv-det-sep"></div>');

  // ── 字段列表 ──
  body.push('<div class="lv-det-section">');
  for (const [key, val] of Object.entries(entityData)) {
    if (HIDE_KEYS.has(key)) continue;
    if (val === null || val === undefined || val === '') continue;
    const isObj = typeof val === 'object';
    const isRo  = READONLY_KEYS.has(key) || isObj;
    if (editable && !isRo) {
      body.push(`<div class="lv-det-field"><label>${_escHtml(key)}</label>`);
      body.push(`<input type="text" class="lv-entity-input" data-field="${_escHtml(key)}" value="${_escHtml(String(val))}" style="flex:1;background:var(--surface1,#45475a);border:1px solid var(--surface2,#585b70);border-radius:4px;color:var(--text,#cdd6f4);padding:2px 5px;font-size:11px;outline:none">`);
      body.push('</div>');
    } else {
      let displayVal;
      if (isObj) {
        displayVal = JSON.stringify(val, null, 1);
        if (displayVal.length > 200) displayVal = displayVal.slice(0, 200) + '…';
        displayVal = _escHtml(displayVal);
      } else {
        displayVal = _escHtml(String(val));
      }
      body.push(`<div class="lv-det-field"><label>${_escHtml(key)}</label><span class="lv-det-val">${displayVal}</span></div>`);
    }
  }
  body.push('</div>');

  // ── 操作按钮区 ──
  if (editable) {
    body.push('<div class="lv-det-sep"></div>');
    body.push('<div style="display:flex;gap:6px;justify-content:flex-end;padding:2px 0">');
    body.push('<button class="lv-entity-save" style="font-size:11px;padding:3px 10px;border:none;border-radius:4px;background:var(--blue,#89b4fa);color:#1e1e2e;cursor:pointer">保存</button>');
    if (linkGid) {
      body.push('<button class="lv-entity-unlink" style="font-size:11px;padding:3px 10px;border:1px solid var(--red,#f38ba8);border-radius:4px;background:transparent;color:var(--red,#f38ba8);cursor:pointer">删除关联</button>');
    }
    body.push('</div>');
  }

  $dpBody.innerHTML = body.join('');

  // ── 刷新关联面板 + 底部详情链接区 ──
  const _refreshAfterEntityEdit = () => {
    if (_assocPanel) _assocPanel.refresh();
    if (_layoutDetailPanel) {
      const sel = _layoutDetailPanel._selectedGid;
      if (sel) _layoutDetailPanel.refresh();
    }
  };

  // ── 保存：收集所有 input 与加载时快照对比 → PATCH ──
  const saveBtn = $dpBody.querySelector('.lv-entity-save');
  if (saveBtn) {
    saveBtn.addEventListener('click', async () => {
      const inputs = $dpBody.querySelectorAll('.lv-entity-input');
      const changed = {};
      for (const inp of inputs) {
        const field = inp.dataset.field;
        if (inp.value !== String(origSnapshot[field] ?? '')) changed[field] = inp.value;
      }
      if (Object.keys(changed).length === 0) { _toast('无变更', 'ok', 1200); return; }
      try {
        await _cf('/api/bop/entity-detail', {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ link_type: linkType, ref_gid: refGid, fields: changed }),
        });
        for (const [k, v] of Object.entries(changed)) { entityData[k] = v; origSnapshot[k] = v; }
        _toast('已保存', 'ok', 1500);
        _refreshAfterEntityEdit();
      } catch (ex) {
        _toast('保存失败: ' + ex.message, 'error');
      }
    });
  }

  // ── 删除关联 ──
  const unlinkBtn = $dpBody.querySelector('.lv-entity-unlink');
  if (unlinkBtn && linkGid) {
    unlinkBtn.addEventListener('click', async () => {
      try {
        await _cf(`/api/bop/entry-links/${linkGid}`, { method: 'DELETE' });
        _toast('已删除关联', 'ok', 1500);
        _closeDetailPopover();
        _refreshAfterEntityEdit();
        await _reload();
      } catch (ex) {
        _toast('删除关联失败: ' + ex.message, 'error');
      }
    });
  }

  // ── input blur 自动保存单字段 ──
  if (editable) {
    $dpBody.querySelectorAll('.lv-entity-input').forEach(inp => {
      inp.addEventListener('blur', async () => {
        const field = inp.dataset.field;
        if (inp.value === String(entityData[field] ?? '')) return;
        try {
          await _cf('/api/bop/entity-detail', {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ link_type: linkType, ref_gid: refGid, fields: { [field]: inp.value } }),
          });
          entityData[field] = inp.value;
          origSnapshot[field] = inp.value;
          inp.style.borderColor = 'var(--green, #a6e3a1)';
          setTimeout(() => { inp.style.borderColor = ''; }, 800);
          _refreshAfterEntityEdit();
        } catch (ex) {
          inp.style.borderColor = 'var(--red, #f38ba8)';
          _toast('保存失败: ' + ex.message, 'error');
        }
      });
      inp.addEventListener('keydown', e => {
        if (e.key === 'Enter') { e.preventDefault(); inp.blur(); }
      });
    });
  }

  // 重新定位（内容加载后高度变化）
  const pH = $dpPopover.offsetHeight;
  const maxTop = window.innerHeight - pH - 8;
  $dpPopover.style.top = Math.max(8, Math.min(anchorTop, maxTop)) + 'px';
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
    </div>
`);
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
    ['版本标签', row.version_tag || '—'],
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
      const nt = child.node_type || 'unknown';
      body.push(`<div class="lv-op-child-item" data-gid="${child.gid}">`);
      body.push(`<span class="lv-type lv-nt-${nt}" style="font-size:9px;padding:0 3px">${NT_ABBR[nt] || nt}</span>`);
      body.push(`<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${_escHtml(child.title || '(无名称)')}</span>`);
      body.push('</div>');
    }
    body.push('</div>');
  }

  // ── 关联条目（占位） ──
  body.push('<div class="lv-op-sep"></div>');
  body.push('<div class="lv-op-section">');
  body.push('<div style="font-size:11px;font-weight:600;color:var(--subtext0,#a6adc8);margin-bottom:4px">关联</div>');
  body.push('<div class="lv-op-link-placeholder">关联条目将在后续版本中显示</div>');
  body.push('</div>');

  $opBody.innerHTML = body.join('');

  // 图片管理区初始化（process / operation 两行）
  if (family === 'process' || family === 'operation') {
    const initPicSection = (containerId, picField) => {
      const picsContainer = document.getElementById(containerId);
      if (!picsContainer) return;
      const rawVal   = row[picField];
      const initItems = _normalizePicItems(Array.isArray(rawVal) ? rawVal : (rawVal ? [rawVal] : []));
      let currentItems = [...initItems];
      _renderPicArea(picsContainer, currentItems, 3, async items => {
        currentItems = items;
        try {
          await _cf(`/api/bop/entries/${gid}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ [picField]: items }),
          });
          const r = _rowByGid.get(gid);
          if (r) r[picField] = items;
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
      if (titleEl) payload.title = titleEl.value.trim();
      if (vppsEl)  payload.vpps  = vppsEl.value.trim();
      if (typeEl)  payload.node_type = typeEl.value;
      try {
        await _cf(`/api/bop/entries/${gid}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        _toast('保存成功', 'ok', 1500);
        if (_viewMode === 'layout' && _layoutMode) _layoutMode._preserveView = true;
        await _reload();
      } catch (e) {
        _toast('保存失败: ' + e.message, 'error');
      }
    });
  }

  // 显示面板（先移除 hidden class）
  $opPanel.classList.remove('hidden');
}

function _closeOverlayPanel() {
  if (_opPinned) return; // pin 住时禁止关闭
  $opPanel.classList.add('hidden');
  _opGid = null;
}

/**
 * 暂存箱卡片双击 → 打开详情面板（简化版）
 * 如果有 original_entry_gid 且该 entry 在 _rowByGid 中，则复用标准详情面板。
 * 否则显示暂存项的基本信息 + 可编辑字段。
 */
function _openStagingOverlay(item) {
  // 优先尝试原始 entry（demote 的暂存项保留了 original_entry_gid）
  if (item.original_entry_gid && _rowByGid.has(item.original_entry_gid)) {
    _openOverlayPanel(item.original_entry_gid);
    return;
  }

  _opGid = 'staging:' + item.gid;
  $opPin.classList.toggle('active', _opPinned);
  $opTitle.textContent = item.title || '(未命名)';

  const ntLabel = NT_LABEL[item.node_type] || item.node_type || '—';
  const sourceLabel = item.source_type ? ({
    bop_entry: '主视图降级', pbom: 'PBOM', issue: '问题',
    task: '任务', tool: '工具', gbop: 'GBOP',
  }[item.source_type] || item.source_type) : '手动创建';

  const body = [];

  // 基本信息
  body.push('<div class="lv-op-section">');
  body.push(`<div class="lv-det-field"><label>节点类型</label><span class="lv-det-val lv-nt-badge lv-nt-${item.node_type || 'process'}">${_escHtml(ntLabel)}</span></div>`);
  body.push(`<div class="lv-det-field"><label>来源</label><span class="lv-det-val">${_escHtml(sourceLabel)}</span></div>`);
  if (item.child_count > 0) {
    body.push(`<div class="lv-det-field"><label>子节点</label><span class="lv-det-val">${item.child_count} 个</span></div>`);
  }
  if (item.source_ref_gid) {
    body.push(`<div class="lv-det-field"><label>来源引用</label><span class="lv-det-val lv-det-mono">${_escHtml(item.source_ref_gid)}</span></div>`);
  }
  if (item.original_entry_gid) {
    body.push(`<div class="lv-det-field"><label>原始节点</label><span class="lv-det-val lv-det-mono">${_escHtml(item.original_entry_gid)}</span></div>`);
  }
  body.push('</div>');

  // 编辑区
  body.push('<div class="lv-op-sep"></div>');
  body.push('<div class="lv-op-section lv-op-edit-section">');
  body.push(`<div class="lv-op-field">
    <label>标题</label>
    <input id="lvOpStgTitle" value="${_escHtml(item.title || '')}">
  </div>`);
  body.push(`<div class="lv-op-field">
    <label>类型</label>
    <select id="lvOpStgNodeType">
      ${Object.entries(NT_LABEL).map(([k, v]) =>
        `<option value="${k}"${k === item.node_type ? ' selected' : ''}>${v}</option>`
      ).join('')}
    </select>
  </div>`);
  body.push(`<div style="margin-top:8px;text-align:right">
    <button class="lv-op-save-btn" id="lvOpStgSave">保存</button>
  </div>`);
  body.push('</div>');

  $opBody.innerHTML = body.join('');

  // 保存按钮
  document.getElementById('lvOpStgSave')?.addEventListener('click', async () => {
    const newTitle = document.getElementById('lvOpStgTitle')?.value?.trim();
    const newType  = document.getElementById('lvOpStgNodeType')?.value;
    if (!newTitle) { _toast('标题不能为空', 'error'); return; }
    try {
      // 暂存项没有独立 PATCH 接口，用 DELETE + POST 重建
      // 或者直接在后端扩展一个 PATCH。这里先用简单方案：
      // 调用后端 PATCH（如果存在），否则 toast 提示
      await _cf(`/api/bop/staging/${item.gid}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: newTitle, node_type: newType }),
      });
      _toast('已保存', 'ok', 1500);
      item.title = newTitle;
      item.node_type = newType;
      $opTitle.textContent = newTitle;
      if (_stagingPanel) _stagingPanel.load();
    } catch (e) {
      _toast('保存失败: ' + e.message, 'error');
    }
  });

  $opPanel.classList.remove('hidden');
}

// _escHtml, _promptText, _confirmDialog, _openImageLightbox 已提取至 web/shared/lv_utils.js

let _ctxGid = null;

function _showCtxMenu(x, y, gid) {
  _ctxGid = gid;
  // 根据版本状态隐藏编辑相关选项
  const editable = _isVersionEditable();
  $ctxMenu.querySelectorAll('.lv-ctx-item').forEach(item => {
    const action = item.dataset.action;
    if (action === 'add_child' || action === 'rename' || action === 'delete' || action === 'reparent') {
      item.style.display = editable ? '' : 'none';
    }
  });
  // 隐藏多余的分隔线（编辑选项全隐藏时）
  $ctxMenu.querySelectorAll('.lv-ctx-sep').forEach(sep => {
    sep.style.display = editable ? '' : 'none';
  });
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
function _ssKey() { return `lv:session:${_versionGid}`; }

/** 将当前工作状态写入 sessionStorage（F5 刷新恢复用） */
function _saveSession() {
  try {
    const view = {
      typeFilter:    _typeFilter,
      maxDepth:      _maxDepth,
      collapsed:     [..._collapsed],
      selectedRoots: [..._selectedRoots],
      level1Filter:  _level1Filter === null ? null : [..._level1Filter],
      zoomPct:       _zoomPct,
      viewMode:      _viewMode,
    };
    // 布局视图的平移/缩放
    if (_layoutMode) {
      view.layoutPan  = { x: _layoutMode._panX, y: _layoutMode._panY };
      view.layoutZoom = _layoutMode._zoom;
    }
    sessionStorage.setItem(_ssKey(), JSON.stringify(view));
  } catch { /* quota exceeded etc. */ }
}

// 页面关闭/刷新前自动保存工作状态
window.addEventListener('beforeunload', _saveSession);
// visibilitychange 兜底（移动端/切 tab 时 beforeunload 可能不触发）
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') _saveSession();
});
function _isCloud() {
  return (window.parent?._authMode || window._authMode || 'local') === 'feishu';
}
function _layoutConfigUrl() { return `/api/bop/versions/${_versionGid}/layout-config`; }

async function _saveView() {
  const view = {
    typeFilter:    _typeFilter,
    maxDepth:      _maxDepth,
    collapsed:     [..._collapsed],
    selectedRoots: [..._selectedRoots],
    level1Filter:  _level1Filter === null ? null : [..._level1Filter],
    zoomPct:       _zoomPct,
    viewMode:      _viewMode,
  };
  // 布局视图的平移/缩放也保存
  if (_layoutMode) {
    view.layoutPan  = { x: _layoutMode._panX, y: _layoutMode._panY };
    view.layoutZoom = _layoutMode._zoom;
  }
  // 同时写入 localStorage（持久）和 sessionStorage（本次 session reload 用）
  localStorage.setItem(_lsKey(), JSON.stringify(view));
  sessionStorage.setItem(_ssKey(), JSON.stringify(view));

  // 云端共享（飞书模式）
  if (!_isCloud() || !_versionGid) {
    _toast('视图已保存（本地）', 'ok', 1500);
    return;
  }
  try {
    const layoutCfg = _layoutMode ? _layoutMode.getConfig() : null;
    await _cf(_layoutConfigUrl(), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ config: { lineage_view: view, layout: layoutCfg } }),
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
    const res = await _cf(_layoutConfigUrl());
    const cloudCfg = res?.config;
    if (!cloudCfg) return;

    // 将云端视图设置同步写回 localStorage（下次打开可立即生效）
    const view = cloudCfg.lineage_view;
    if (view) {
      const local = JSON.parse(localStorage.getItem(_lsKey()) || '{}');
      localStorage.setItem(_lsKey(), JSON.stringify({ ...local, ...view }));
    }

    // 若云端视图模式与当前不同，重新渲染
    if (view?.viewMode && (view.viewMode === 'layout' || view.viewMode === 'columns')
        && view.viewMode !== _viewMode) {
      _viewMode = view.viewMode;
      _render();
      if (_activeGid) _applyActiveState(_activeGid);
      // render 内部会再次进入布局模式并 applyConfig（下面的分支）
      return;
    }

    // 应用布局位置到已存在的 LayoutMode 实例
    if (_layoutMode && cloudCfg.layout) {
      _layoutMode.applyConfig(cloudCfg.layout);
    }
  } catch { /* 网络失败静默忽略，本地数据继续使用 */ }
}

function _restoreView() {
  // 优先从 sessionStorage 恢复（F5 刷新 / 页面内操作导致的 reload）
  // 没有 session 数据时才从 localStorage 恢复（关掉 tab 重新进入）
  let view = null;
  try {
    const ss = sessionStorage.getItem(_ssKey());
    if (ss) {
      view = JSON.parse(ss);
      view._fromSession = true;
    }
  } catch { /* ignore */ }

  if (!view) {
    try {
      const ls = localStorage.getItem(_lsKey());
      if (ls) view = JSON.parse(ls);
    } catch { /* ignore */ }
  }

  if (!view) {
    // 没有完整视图存档时，尝试恢复独立的筛选状态
    try {
      const fs = localStorage.getItem(_lsk('lv:filters'));
      if (fs) {
        const f = JSON.parse(fs);
        const rawTF = f.typeFilter;
        _typeFilter = (Array.isArray(rawTF) && rawTF.length > 0) ? rawTF : null;
        const rawL1 = f.level1Filter;
        _level1Filter = (Array.isArray(rawL1) && rawL1.length > 0) ? new Set(rawL1) : null;
      }
    } catch {}
    return;
  }

  const rawTF = view.typeFilter;
  _typeFilter = (Array.isArray(rawTF) && rawTF.length > 0) ? rawTF : null;
  _maxDepth   = view.maxDepth ?? 6;
  $maxDepth.value = String(_maxDepth);
  _collapsed  = new Set(view.collapsed || []);
  const rawL1 = view.level1Filter;
  _level1Filter = (Array.isArray(rawL1) && rawL1.length > 0) ? new Set(rawL1) : null;
  if (view.selectedRoots?.length) {
    // 只恢复当前数据中仍然存在的根节点 gid（导入后 gid 全部更新，旧 gid 失效会导致列视图空白）
    const validRoots = view.selectedRoots.filter(gid => _rowByGid.has(gid));
    if (validRoots.length) _selectedRoots = new Set(validRoots);
    // 若全部失效（如导入后新 gid），保留 _initCollapsed() 的结果
  }
  if (view.zoomPct) {
    _zoomPct = view.zoomPct;
    $zoomRange.value = _zoomPct;
    $zoomPct.textContent = _zoomPct + '%';
  }
  if (view.viewMode === 'layout' || view.viewMode === 'columns') {
    _viewMode = view.viewMode;
  }
  // 布局视图平移/缩放（仅 session 恢复时）
  if (view._fromSession && view.layoutPan != null) {
    _pendingLayoutPan  = view.layoutPan;
    _pendingLayoutZoom = view.layoutZoom;
  }
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

// ── link alerts helpers ────────────────────────────────────────────────

function _collectLinkAlerts() {
  const alerts = [];
  for (const [gid, row] of _rowByGid) {
    if (row.link_status === 'stale') {
      alerts.push({
        type: 'stale', severity: 'warn',
        entryGid: gid, title: row.title, nodeType: row.node_type,
        message: `"${row.title || gid}" 的主关联目标已失效`,
      });
    }
  }
  return alerts;
}

function _renderLinkAlerts(alerts, extraAlerts) {
  const body    = document.getElementById('lvRuleBody');
  const summary = document.getElementById('lvRuleSummary');
  if (!body) return;

  const all = [...(alerts || []), ...(extraAlerts || [])];
  body.innerHTML = '';

  if (all.length === 0) {
    if (summary) { summary.textContent = '正常'; summary.classList.remove('has-warn'); }
    const empty = document.createElement('div');
    empty.className = 'lv-cpanel-empty';
    empty.textContent = '暂无提示';
    body.appendChild(empty);
    return;
  }

  const staleCount  = all.filter(a => a.type === 'stale').length;
  const warnAlerts  = all.filter(a => a.type === 'auto_link_warn');
  const ruleAlerts  = all.filter(a => a.type === 'rule');
  const totalWarn   = staleCount + warnAlerts.length + ruleAlerts.filter(r => r.severity !== 'info').length;
  const totalInfo   = ruleAlerts.filter(r => r.severity === 'info').length;

  if (summary) {
    const parts = [];
    if (totalWarn > 0) parts.push(`${totalWarn} 警告`);
    if (totalInfo > 0) parts.push(`${totalInfo} 提示`);
    summary.textContent = parts.join(' · ') || '正常';
    summary.classList.toggle('has-warn', totalWarn > 0);
  }

  if (staleCount > 0) {
    const row = document.createElement('div');
    row.className = 'lv-cpanel-item lv-cpanel-warn';
    row.innerHTML = `<span class="lv-cpanel-icon">⚠</span>`
      + `<span class="lv-cpanel-text">${staleCount} 个节点关联已失效，建议修复</span>`
      + `<button class="lv-cpanel-action" data-action="repair">修复</button>`;
    body.appendChild(row);
  }

  for (const a of warnAlerts) {
    const row = document.createElement('div');
    row.className = 'lv-cpanel-item lv-cpanel-warn';
    row.innerHTML = `<span class="lv-cpanel-icon">⚠</span>`
      + `<span class="lv-cpanel-text">${a.message}</span>`;
    body.appendChild(row);
  }

  if (ruleAlerts.length > 0) {
    const hdr = document.createElement('div');
    hdr.className = 'lv-cpanel-section-hdr';
    hdr.textContent = '规则校验';
    body.appendChild(hdr);
    for (const a of ruleAlerts) {
      const row = document.createElement('div');
      row.className = `lv-cpanel-item lv-cpanel-${a.severity === 'info' ? 'info' : 'warn'}`;
      row.innerHTML = `<span class="lv-cpanel-icon">${a.severity === 'error' ? '✕' : a.severity === 'info' ? 'i' : '!'}</span>`
        + `<span class="lv-cpanel-text">[${a.ruleName}] ${a.message}</span>`;
      if (a.suggestion) {
        row.innerHTML += `<button class="lv-cpanel-action" data-action="apply-suggestion"
          data-suggestion='${JSON.stringify(a.suggestion)}'>应用建议</button>`;
      }
      body.appendChild(row);
    }
  }

  // 按钮事件（事件委托）
  body.addEventListener('click', async e => {
    const btn = e.target.closest('.lv-cpanel-action');
    if (!btn) return;
    const action = btn.dataset.action;
    if (action === 'repair') {
      await _runAutoLink({ mode: 'repair', step: 'all' });
    } else if (action === 'auto-link') {
      await _runAutoLink({ mode: 'incremental', step: 'all' });
    }
  }, { once: true });
}

async function _runAutoLink(opts = {}) {
  if (!_versionGid) return;
  const mode = opts.mode || 'incremental';
  const step = opts.step || 'all';
  try {
    _toast(`正在执行 Auto-Link (${mode})…`, 'ok', 2000);
    const res = await _cf(`/api/bop/versions/${_versionGid}/auto-link`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode, step }),
    });
    const stats = res.data?.stats || {};
    const warns = (res.data?.items || []).filter(i => i.status === 'warn');
    _toast(
      `Auto-Link 完成：新建/匹配 ${stats.ok || 0} 条，跳过 ${stats.skip || 0} 条，警告 ${stats.warn || 0} 条`,
      stats.error > 0 ? 'error' : 'ok',
      3500,
    );
    await _reload();
    // 将 warn 条目也追加到 alert 面板
    const extraAlerts = warns.map(w => ({
      type: 'auto_link_warn', severity: 'warn',
      entryGid: w.entry_gid, message: w.message,
    }));
    _renderLinkAlerts(_collectLinkAlerts(), extraAlerts);
  } catch (err) {
    _toast('Auto-Link 失败: ' + err.message, 'error');
  }
}

// ── 拖放操作串行队列（避免并发 PATCH 乱序）────────────────────────────────
let _moveQueue = Promise.resolve();

function _localMoveApply(gid, patchBody) {
  const row = _rowByGid.get(gid);
  if (!row) return;
  if (patchBody.parent_gid !== undefined) row.parent_gid = patchBody.parent_gid;
  if (patchBody.sort_order !== undefined) row.sort_order = patchBody.sort_order;
  // 对同父级兄弟整数化 sort_order，避免浮点累积
  const siblings = _rows.filter(r => r.parent_gid === row.parent_gid);
  siblings.sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));
  siblings.forEach((r, i) => { r.sort_order = i; });
  _buildIndexes(_rows);
  _buildStats();
  _render();
  if (_activeGid) _applyActiveState(_activeGid);
}

// ── reload helper ─────────────────────────────────────────────────────

// 新建空白线体（工具栏按钮 + 生命周期面板按钮共用）
async function _addBlankLine() {
  if (!_versionGid) { _toast('请先选择 BOP 版本', 'warn'); return; }
  if (!_isVersionEditable()) { _toast('当前版本已冻结，无法编辑', 'warn'); return; }
  const result = await _promptText('请输入线体名称');
  if (!result?.title) return;
  try {
    const maxSort = _rows.filter(r => r.node_type === 'line_process')
      .reduce((m, r) => Math.max(m, r.sort_order ?? 0), 0);
    await _cf('/api/bop/entries', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        version_gid: _versionGid,
        parent_gid:  null,
        node_type:   'line_process',
        title:       result.title,
        sort_order:  maxSort + 1,
      }),
    });
    await _load();
    _toast(`线体「${result.title}」已创建`, 'ok');
  } catch (e) {
    _toast('创建失败: ' + e.message, 'error');
  }
}

async function _reload() {
  _closeOverlayPanel();
  try {
    // 刷新版本状态
    if (_versionGid) {
      try {
        const verJson = await _cf(`/api/bop/versions/${_versionGid}`);
        if (verJson.data) {
          _versionStatus = verJson.data.status || 'active';
          if (_verMgr) _verMgr.currentVersionStatus = _versionStatus;
          _updateVersionStatusUI();
        }
      } catch { /* ignore version fetch failure */ }
    }

    let allRows = [];
    for (const vGid of _loadedVersionGids) {
      const json = await _cf(`/api/bop/versions/${vGid}/entries`);
      allRows = allRows.concat(_flattenMeta(json.data || []));
    }
    _rows = allRows;
    _buildIndexes(_rows);
    _buildStats();
    _render();
    _renderLinkAlerts(_collectLinkAlerts());
    // 刷新后更新底部详情面板数据
    if (_layoutDetailPanel) _layoutDetailPanel.updateData(_buildLineageData());
    if (_activeGid) {
      if (_viewMode === 'layout' && _layoutMode) {
        _layoutMode.highlightNode(_activeGid);
      } else {
        _applyActiveState(_activeGid);
      }
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
  $ctxMenu.addEventListener('click', async e => {
    const item = e.target.closest('.lv-ctx-item');
    if (!item || !_ctxGid) return;
    const action = item.dataset.action;
    const gid    = _ctxGid;
    _hideCtxMenu();
    if (action === 'rename') {
      // 布局视图卡片在 #llWorld，列视图卡片用 .lv-card
      const card = document.querySelector(`.lv-card[data-gid="${gid}"]`)
                || document.querySelector(`#llWorld [data-gid="${gid}"]`);
      if (card) _startInlineRename(card);
    } else if (action === 'add_child') {
      _handleFBtnAction('add_child', gid);
    } else if (action === 'delete') {
      _deleteEntry(gid);
    } else if (action === 'reparent') {
      const row = _rowByGid.get(gid);
      if (!row) return;
      const picked = await _openParentPicker({
        title: '变更父级',
        excludeGid: gid,
        defaultType: _PARENT_TYPE_MAP[row.node_type] || null,
      });
      if (!picked) return;
      if (!_canEditEntry(gid)) {
        _toast('当前线体无编辑权限（只读）', 'warn');
        return;
      }
      try {
        if (_viewMode === 'layout' && _layoutMode) _layoutMode._preserveView = true;
        await _patchEntry(gid, { parent_gid: picked.gid, sort_order: 0 });
        await _reload();
        _toast('父级已变更', 'ok');
      } catch (ex) {
        _toast('变更失败: ' + ex.message, 'error');
      }
    } else if (action === 'detail_modal') {
      if (_viewMode === 'layout' && _layoutDetailPanel) {
        _layoutDetailPanel.open(gid);
      } else {
        _openOverlayPanel(gid);
      }
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

  document.getElementById('lvRefresh')?.addEventListener('click', _reload);

  // ── 新建空白线体按钮 ──
  document.getElementById('lvAddLineBtn')?.addEventListener('click', () => _addBlankLine());

  // ── Auto-Link 下拉按钮 ──
  const $autoLinkBtn = document.getElementById('lvAutoLinkBtn');
  const $autoLinkMenu = document.getElementById('lvAutoLinkMenu');
  if ($autoLinkBtn && $autoLinkMenu) {
    $autoLinkBtn.addEventListener('click', e => {
      e.stopPropagation();
      const shown = $autoLinkMenu.style.display !== 'none';
      $autoLinkMenu.style.display = shown ? 'none' : 'block';
    });
    $autoLinkMenu.addEventListener('click', e => {
      const item = e.target.closest('[data-action]');
      if (!item) return;
      $autoLinkMenu.style.display = 'none';
      const action = item.dataset.action;
      if (action === 'al-incremental') {
        _runAutoLink({ mode: 'incremental', step: 'all' });
      } else if (action === 'al-repair') {
        _runAutoLink({ mode: 'repair', step: 'all' });
      }
    });
    document.addEventListener('click', e => {
      if (!$autoLinkBtn.contains(e.target) && !$autoLinkMenu.contains(e.target)) {
        $autoLinkMenu.style.display = 'none';
      }
    });
  }

  // ── 规则判定 / 参考信息 折叠按钮 ──
  ['lvRulePanel', 'lvRefPanel'].forEach(panelId => {
    const panel  = document.getElementById(panelId);
    const toggle = panel?.querySelector('.lv-cpanel-toggle');
    const hdr    = panel?.querySelector('.lv-cpanel-hdr');
    if (!panel) return;
    const lsKey  = _lsk(`lv:${panelId}Collapsed`);
    if (localStorage.getItem(lsKey) === 'true') panel.classList.add('collapsed');
    const toggleFn = () => {
      panel.classList.toggle('collapsed');
      localStorage.setItem(lsKey, panel.classList.contains('collapsed'));
    };
    if (toggle) toggle.addEventListener('click', e => { e.stopPropagation(); toggleFn(); });
    if (hdr)    hdr.addEventListener('click', toggleFn);
  });

  document.getElementById('lvThemeToggle')?.addEventListener('click', () => {
    if (_viewMode === 'layout') {
      _lvThemeLayout = _lvThemeLayout === 'light' ? 'dark' : 'light';
      localStorage.setItem(_lsk('lv:theme:layout'), _lvThemeLayout);
    } else {
      _lvThemeColumns = _lvThemeColumns === 'light' ? 'dark' : 'light';
      localStorage.setItem(_lsk('lv:theme:columns'), _lvThemeColumns);
    }
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

  // ── 工具栏 FAB ──
  const $fab = document.getElementById('lvToolbarFab');
  if ($fab) $fab.addEventListener('click', _toggleToolbar);

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
    e.dataTransfer.setData('application/x-bop-entry', _dragGid);
  });

  $columns.addEventListener('dragend', () => {
    document.querySelectorAll('.lv-card.dragging').forEach(el => el.classList.remove('dragging'));
    _clearDropClasses();
    _dragGid = null;
  });

  $columns.addEventListener('dragover', e => {
    const card = e.target.closest('.lv-card');
    if (!card) return;
    // Accept: own cards (reparent), staging items, assoc items
    const hasBop     = _dragGid;
    const hasStaging = e.dataTransfer.types.includes('application/x-staging-item');
    const hasAssoc   = e.dataTransfer.types.includes('application/x-assoc-item');
    if (!hasBop && !hasStaging && !hasAssoc) return;
    if (hasBop && card.dataset.gid === _dragGid) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    _clearDropClasses();
    if (hasBop) {
      const pos = _getDropPosition(e, card);
      if (pos === 'up')    card.classList.add('drop-above');
      if (pos === 'down')  card.classList.add('drop-below');
      if (pos === 'right') card.classList.add('drop-under');
    } else {
      // For staging/assoc, always drop as child
      card.classList.add('drop-under');
    }
  });

  $columns.addEventListener('dragleave', e => {
    if (!e.target.closest('.lv-card')) _clearDropClasses();
  });

  $columns.addEventListener('drop', async e => {
    e.preventDefault();
    _clearDropClasses();
    const card = e.target.closest('.lv-card');
    if (!card) return;
    const targetGid = card.dataset.gid;
    const targetRow = _rowByGid.get(targetGid);
    if (!targetRow) return;

    // ── Source: Staging item → promote ──
    const stagingData = e.dataTransfer.getData('application/x-staging-item');
    if (stagingData && _stagingPanel) {
      try {
        const info = JSON.parse(stagingData);
        await _stagingPanel.promoteItem(info.stagingGid, targetGid, (targetRow.sort_order ?? 0) + 0.5);
      } catch (ex) {
        _toast('恢复失败: ' + ex.message, 'error');
      }
      return;
    }

    // ── Source: Assoc item → create link on target (不创建子节点) ──
    const assocData = e.dataTransfer.getData('application/x-assoc-item');
    if (assocData) {
      try {
        const info = JSON.parse(assocData);
        if (!info.refGid || !info.linkType) throw new Error('缺少关联信息');
        await _cf('/api/bop/entry-links', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            bop_entry_gid: targetGid,
            link_type:     info.linkType,
            ref_gid:       info.refGid,
            is_primary:    info.isPrimary ?? false,
          }),
        });
        _toast('已创建关联', 'ok');
        await _reload();
        if (_assocPanel) _assocPanel.refresh();
      } catch (ex) {
        _toast('关联失败: ' + ex.message, 'error');
      }
      return;
    }

    // ── Source: Own bop_entry card → reparent ──
    if (!_dragGid || targetGid === _dragGid) return;
    const dragRow = _rowByGid.get(_dragGid);
    if (!dragRow) return;

    const pos = _getDropPosition(e, card);
    if (!pos) return;

    let patchBody;
    if (pos === 'up') {
      patchBody = { parent_gid: targetRow.parent_gid, sort_order: (targetRow.sort_order ?? 0) - 0.5 };
    } else if (pos === 'down') {
      patchBody = { parent_gid: targetRow.parent_gid, sort_order: (targetRow.sort_order ?? 0) + 0.5 };
    } else {
      patchBody = { parent_gid: targetGid, sort_order: 0 };
    }

    try {
      // 1. 立刻本地更新 + 重渲（用户无感知延迟）
      const savedGid = _dragGid;
      _localMoveApply(savedGid, patchBody);

      // 2. 串行队列：等上一个 PATCH 完成再发下一个，保证服务端顺序正确
      _moveQueue = _moveQueue.then(async () => {
        try {
          await _patchEntry(savedGid, patchBody);
          // 成功后只轻量同步这一行的最新数据，不做全量 reload
          _cf(`/api/bop/entries/${savedGid}`).then(res => {
            if (res?.data) {
              const srv = res.data;
              const local = _rowByGid.get(savedGid);
              if (local) {
                local.sort_order = srv.sort_order ?? local.sort_order;
                local.parent_gid = srv.parent_gid ?? local.parent_gid;
              }
            }
          }).catch(() => {});
        } catch (ex) {
          _toast('移动失败，正在恢复: ' + ex.message, 'error');
          await _reload(); // 仅在持久化失败时全量回滚
        }
      });
    } catch (ex) {
      _toast('移动失败: ' + ex.message, 'error');
    }
    _dragGid = null;
  });

  // ── 视图模式切换（分段开关） ──
  document.getElementById('lvViewToggle').addEventListener('click', e => {
    const btn = e.target.closest('.lv-vtog-btn');
    if (!btn) return;
    const mode = btn.dataset.mode;
    if (mode === _viewMode) return;
    _viewMode = mode;
    localStorage.setItem(_lsk('lv:viewMode'), _viewMode);
    if (_viewMode === 'columns') {
      _layoutEditMode = false;
      if (_layoutMode) _layoutMode.setEditMode(false);
      if ($layoutEditBtn) $layoutEditBtn.classList.remove('active');
    }
    _render();
    _applyLvTheme();
    if (_activeGid) _applyActiveState(_activeGid);
  });

  // ── 编辑模式切换（布局模式下） ──
  $layoutEditBtn?.addEventListener('click', () => {
    _layoutEditMode = !_layoutEditMode;
    if ($layoutEditBtn) $layoutEditBtn.classList.toggle('active', _layoutEditMode);
    if (_layoutMode) _layoutMode.setEditMode(_layoutEditMode);
  });

  // ── 适应全局（布局模式下） ──
  $layoutFitBtn.addEventListener('click', () => {
    if (_layoutMode) {
      _layoutMode.fitToScreen();
    }
  });

  // ── 导入 PBOM ──
  $importPbomBtn?.addEventListener('click', async () => {
    if (!_pbomProjects.length) await _loadPbomProjects();
    await _loadPbomVersions();
    _openPbomImportModal();
  });

  // ── 导入 TC（Layout 工具栏，使用 lineage 的正确 mapping）──
  $importTcBtn?.addEventListener('click', () => {
    if (_verMgr?.openImportTcModal) {
      _verMgr.openImportTcModal();
    } else {
      _toast('版本管理器未就绪', 'warn');
    }
  });
}

// ── 初始化 ────────────────────────────────────────────────────────────

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
  // 立即同步工具栏控件显隐（_viewMode 可能已被 _restoreView() 改变）
  _syncLayoutUI();

  // 应用本地亮/暗主题
  _applyLvTheme();

  // 应用缩放值
  $zoomRange.value = _zoomPct;
  $zoomPct.textContent = _zoomPct + '%';
  document.documentElement.style.setProperty('--lv-scale', _zoomPct / 100);

  // 初始化边栏宽度 CSS 变量（默认关闭）
  $sidebar.classList.remove('lv-sidebar-open');
  $sidebar.classList.add('collapsed');
  document.documentElement.style.setProperty('--sb-width', '0px');
  $sbToggle.innerHTML = '&#x25C0;';
  $sbToggle.title = '展开边栏';

  // 恢复工具栏状态（默认隐藏）
  _toolbarOpen = localStorage.getItem(_lsk('lv:toolbarOpen')) === '1';
  const _tbEl = document.getElementById('lvToolbar');
  const _fabEl = document.getElementById('lvToolbarFab');
  if (_tbEl) _tbEl.classList.toggle('lv-tb-hidden', !_toolbarOpen);
  if (_fabEl) _fabEl.classList.toggle('lv-fab-active', _toolbarOpen);

  // 绑定事件
  _bindEvents();

  // 初始化暂存箱 + 关联面板
  _initSidebarPanels();

  // 初始化布局视图底部详情面板（v2：七列可调宽）
  const dpEl = document.getElementById('llDetailPanel');
  if (dpEl) {
    _layoutDetailPanel = new LayoutDetailPanel({
      containerEl: dpEl,
      cf: _cf,
      toast: _toast,
      patchEntry: _patchEntry,
      reloadData: _reload,
      preserveLayoutView: () => { if (_viewMode === 'layout' && _layoutMode) _layoutMode._preserveView = true; },
      getLineageData: () => _buildLineageData ? _buildLineageData() : null,
      getVersionInfo: () => {
        const all = _verMgr?.allVersions || [];
        const cur = all.find(v => v.gid === _versionGid);
        // 显示格式：族群名 · 版本号（如 "W04-2025 · v1"）
        const _verLabel = (v) => v
          ? `${v.bop_name || '未命名'} · ${v.version_tag || v.gid.slice(-6)}`
          : _versionGid.slice(-6);
        return {
          currentGid:       _versionGid,
          currentName:      _verLabel(cur),
          pbomVersionGid:   cur?.pbom_version_gid || null,
          projectGid:       cur?.project_gid      || null,
          factoryGid:       cur?.factory_gid      || null,
          versions: all.filter(v => !v.archived_at && v.version_type !== 'template').map(v => ({
            gid:    v.gid,
            name:   _verLabel(v),
            status: v.status,
          })),
        };
      },
      onVersionChange: (gid) => {
        if (_verMgr && typeof _verMgr.selectVersion === 'function') {
          _verMgr.selectVersion(gid);
        } else {
          // 兜底：直接切换
          _versionGid = gid;
          if (_assocPanel) _assocPanel.setVersionGid(gid);
          _load();
        }
      },
      onNodeActivate: (gid) => {
        if (_viewMode === 'layout' && _layoutMode) {
          // 若节点是隐藏类型（零件/操作等），尝试跳转到其父节点
          const row = _rowByGid.get(gid);
          let targetGid = gid;
          const hiddenSet = typeof HIDDEN_TYPES !== 'undefined' ? new Set(HIDDEN_TYPES) : new Set();
          if (row && hiddenSet.has(row.node_type)) {
            targetGid = row.parent_gid || gid;
          }
          _layoutMode.highlightNode(targetGid);
          if (typeof _layoutMode.scrollToNode === 'function') _layoutMode.scrollToNode(targetGid);
        } else {
          _applyActiveState(gid);
        }
      },
    });
  }

  // 初始化版本管理器（LineageVersionManager）
  _verMgr = new LineageVersionManager({
    cf: _cf,
    toast: _toast,
    onVersionSelected: (gid, tag) => {
      _versionGid = gid;
      try { localStorage.setItem(_lsk('lv:lastVersionGid'), gid); } catch {}
      if (_assocPanel) _assocPanel.setVersionGid(gid);
      if (_lifecyclePanel) _lifecyclePanel.setVersionGid(gid);
      _load();
    },
    onStatusChange: (status) => {
      _versionStatus = status;
      _updateVersionStatusUI();
    },
    onReloadNeeded: () => _load(),
    onNewBtnClick: () => {
      // 展开侧边栏（如果已折叠）
      if (!_sidebarOpen) _toggleSidebar();
      // 切换到布局视图（生命周期面板在布局视图）
      if (_viewMode !== 'layout') {
        _viewMode = 'layout';
        localStorage.setItem(_lsk('lv:viewMode'), _viewMode);
        _syncLayoutUI();
        if (_layoutMode) _layoutMode.activate?.();
      }
      // 进入新建模式
      if (_lifecyclePanel) _lifecyclePanel.enterCreationMode();
    },
  });
  await _verMgr.loadVersions();
  _verMgr.initPicker(_versionGid, _versionTag);

  // 无任何 BOP 版本 → 画布内提示
  if ((!_versionGid || _versionGid === '') && (!_verMgr.allVersions || _verMgr.allVersions.length === 0)) {
    _versionGid = '';
    $layoutCanvas.style.display = '';
    $columns.style.display = 'none';
    _syncLayoutUI();
    document.getElementById('lvLoadingOverlay')?.classList.add('hidden');
    const cv = document.getElementById('lvLayoutCanvas');
    if (cv) {
      let hint = cv.querySelector('.lv-empty-hint-overlay');
      if (!hint) {
        hint = document.createElement('div');
        hint.className = 'lv-empty-hint-overlay';
        hint.style.cssText = 'position:absolute;inset:0;display:flex;align-items:center;justify-content:center;background:var(--base,#eff1f5);z-index:5;pointer-events:none';
        cv.style.position = 'relative';
        cv.appendChild(hint);
      }
      hint.innerHTML = `<div style="text-align:center;color:var(--subtext0,#6c6f85);font-size:14px;line-height:2"><div style="font-size:48px;margin-bottom:12px;opacity:.3">📋</div><div style="font-weight:600;color:var(--text,#4c4f69)">暂无 BOP 版本</div><div style="font-size:12px">你尚未被加入任何项目，请联系管理员</div><div style="font-size:12px">将你添加为项目成员并分配 BOP 版本</div></div>`;
    }
    return;
  }

  // 初始化多项目对比按钮（主版本始终为 projectVersions[0]）
  const _curVer = (_verMgr.allVersions || []).find(v => v.gid === _versionGid);
  _projectVersions = [{
    versionGid: _versionGid,
    versionTag: _versionTag,
    bopName:    _curVer?.bop_name || '',
  }];
  _initCompareBtn();

  // 初始化生命周期面板
  _lifecyclePanel = new BopLifecyclePanel({
    cf:         _cf,
    toast:      _toast,
    versionGid: _versionGid,
    mountEl:    document.getElementById('lvLifecycleTop'),
    actionEl:   document.getElementById('lvLifecycleAction'),
    onBopTreeChange: () => {
      if (_viewMode === 'layout' && _layoutMode) _layoutMode._preserveView = true;
      _reload();
    },
  });
  if (_viewMode === 'layout' && _versionGid) await _lifecyclePanel.init();

  // 初始化 PBOM 导入 modal
  _setupPbomImportModal();
  _pbomIeMgr = new ImportExportManager({
    moduleId: 'lineage_pbom',
    columns:  _PBOM_FULL_COLS,
    colAliasMap: _PBOM_EXCEL_COL_MAP,
    getRows: () => [],
    onImport: async (rows, _fieldMap, _conflict, signal) => {
      if (!_pbomTargetGid) throw new Error('请先选择或创建 PBOM 版本');
      const mapped   = rows.map(r => _mapPbomExcelRow(r));
      const filtered = mapped.filter(r => r.level == null || (r.level > 0 && r.level < 4));
      const skipped  = mapped.length - filtered.length;
      if (skipped) console.log(`[PBOM] 已跳过 ${skipped} 行 (level ≥ 4)`);
      if (!filtered.length) throw new Error('没有可导入的数据行');
      const BATCH = 100;
      let totalInserted = 0;
      for (let i = 0; i < filtered.length; i += BATCH) {
        if (signal?.aborted) break;
        const chunk = filtered.slice(i, i + BATCH);
        const res = await _cf(`/api/ebom/snapshots/${_pbomTargetGid}/parts/batch`, {
          method: 'POST',
          body: JSON.stringify(chunk),
          signal,
        });
        if (!res?.success) throw new Error(`批量导入失败(${i}~${i+chunk.length}): ${res?.detail || JSON.stringify(res)}`);
        totalInserted += res.data?.inserted || 0;
      }
      if (!signal?.aborted) {
        console.log(`[PBOM] 导入完成, inserted=${totalInserted}`);
        _toast(`PBOM 导入完成，共 ${totalInserted} 条`, 'ok');
      }
    },
  });

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
    // 清单树导航：切换到指定 BOP 版本
    if (e.data?.type === 'ls:nav' && e.data?.gid) {
      const targetGid = e.data.gid;
      if (targetGid !== _versionGid) {
        _versionGid = targetGid;
        localStorage.setItem(_lsk('lv:lastVersionGid'), targetGid);
        if (_assocPanel) _assocPanel.setVersionGid(targetGid);
        if (_verMgr) _verMgr.currentVersionGid = targetGid;
        _load();
      }
    }
  });
})();

document.addEventListener('DOMContentLoaded', init);
