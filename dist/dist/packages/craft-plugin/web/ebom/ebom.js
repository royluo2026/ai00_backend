/**
 * ebom.js — PBOM 三栏对比页面（重构后，使用 ListDiffShell）
 *
 * 职责：PBOM 专有配置 + VPPS 核对逻辑 + modal 交互
 * 通用 diff 逻辑已提取至 web/components/list_diff_shell.js
 */
'use strict';

/* ── Standalone 窗口模式（?standalone=1&pbom_gid=xxx）────────
 * 作为独立 Electron 窗口打开时，没有 window.parent 可用，
 * 需要自行初始化 _cloudFetch 和 _authUser。
 */
const _urlParams           = new URLSearchParams(location.search);
const _standaloneMode      = _urlParams.get('standalone') === '1';
const _preselectedPbomGid  = _urlParams.get('pbom_gid') || '';
const _autoAction          = _urlParams.get('auto_action') || '';

if (_standaloneMode) {
  // window._cloudFetch 는 preload.js 가 contextBridge 로 이미 주입함（read-only）
  // _authUser 만 별도로 초기화한다
  const _eAPI = window.electronAPI
    || window.top?.electronAPI
    || window.parent?.electronAPI;
  if (_eAPI) {
    _eAPI.authGetState?.().then(s => { window._authUser = s?.user || null; });
  }
}

/* ── helpers ─────────────────────────────────────────────── */
function _cf(path, opts) {
  const fn = window.parent?._cloudFetch || window._cloudFetch;
  if (!fn) return Promise.resolve(null);
  return fn(path, opts).catch(err => { console.warn('[PBOM] fetch error', err); return null; });
}

// localStorage 账号隔离
function _lsk(base) {
  try { const u = window.parent?._authUser || window.top?._authUser || window._authUser; const g = u?.gid || u?.user_gid || ''; return g ? `${g}:${base}` : base; } catch { return base; }
}

function _opt(value, label) {
  const o = document.createElement('option');
  o.value = value; o.textContent = label;
  return o;
}

/* ── Excel 列映射（TC/PLM 导出 19 列 -> DB 字段）──────────── */
const EXCEL_COL_MAP = {
  'Home':           'home',
  'Level':          'level',
  'VPPS':           'vpps',
  'VPPS描述':       'vpps_desc',
  '父级VPPS':       'parent_vpps',
  '父级VPPS名称':   'parent_vpps_name',
  'BOM 行':         'bom_row',
  'BOM行':          'bom_row',
  'BOM行标签':      'bom_row_label',
  'BOM 行标签':     'bom_row_label',
  '零组件 ID':      'component_id',
  '零组件ID':       'component_id',
  '零组件名称':     'name',
  '变量公式':       'variable_formula',
  '扭矩':          'torque',
  '扭矩重要度':     'torque_importance',
  '数量':           'quantity',
  '零组件版本所有权用户': 'ownership_user',
  '零组件类型':     'component_type',
  '零组件版本状态':  'component_version_status',
  '采购状态':       'purchase_status',
  '父级':           'parent_bom_row',
  '配置':           'configuration',
  '父级BOM行':     'parent_bom_row',
  '父级BOM 行':    'parent_bom_row',
  'catiaOccurrenceName': 'catia_occurrence_name',
  'catiaFileName':      'catia_file_name',
  'catiaUUID':          'catia_uuid',
  '默认变换矩阵':       'default_matrix',
  '绝对变换矩阵':       'abs_matrix',
  '相对变换矩阵':       'rel_matrix',
  '限定框':            'local_bbox',
  'ECN编码':           'ecn',
  'FNA':               'fna',
  '几何推测主件':       'geo_main_part',
  '参考主件VPPS描述':   'ref_main_vpps_desc',
  '参考主件vpps':       'ref_main_vpps',
  '主件一致性状态':     'main_part_consistency',
  '推测主件几何依据':   'geo_evidence',
  '零件左右侧':        'lr_side',
  'part_no':        'part_no',
  'name':           'name',
  'quantity':       'quantity',
  'unit':           'unit',
  'material':       'material',
};

function _mapExcelRow(raw) {
  const out = {};
  for (const [excelKey, dbKey] of Object.entries(EXCEL_COL_MAP)) {
    if (raw[excelKey] !== undefined && raw[excelKey] !== null && raw[excelKey] !== '') {
      out[dbKey] = raw[excelKey];
    }
  }
  for (const k of Object.keys(raw)) {
    if (!out[k] && EXCEL_COL_MAP[k] === undefined) {
      const dbFields = new Set(Object.values(EXCEL_COL_MAP));
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

/* ── PBOM 完整列定义 ────────────────────────────────────── */
const PBOM_FULL_COLS = [
  { key: 'home',                      label: 'Home',         type: 'text', width: 60  },
  { key: 'level',                     label: 'Level',        type: 'number', width: 50 },
  { key: 'vpps',                      label: 'VPPS',         type: 'text', width: 120 },
  { key: 'vpps_desc',                 label: 'VPPS描述',     type: 'text', width: 160 },
  { key: 'parent_vpps',               label: '父级VPPS',     type: 'text', width: 120 },
  { key: 'parent_vpps_name',          label: '父级VPPS名称', type: 'text', width: 160 },
  { key: 'bom_row',                   label: 'BOM 行',       type: 'text', width: 120 },
  { key: 'bom_row_label',             label: 'BOM 行标签',   type: 'text', width: 120 },
  { key: 'component_id',              label: '零组件 ID',    type: 'text', width: 130 },
  { key: 'name',                      label: '零组件名称',   type: 'text', width: 200 },
  { key: 'variable_formula',          label: '变量公式',     type: 'text', width: 100 },
  { key: 'torque',                    label: '扭矩',         type: 'text', width: 80  },
  { key: 'torque_importance',         label: '扭矩重要度',   type: 'text', width: 80  },
  { key: 'quantity',                  label: '数量',         type: 'number', width: 60 },
  { key: 'ownership_user',            label: '所有权用户',   type: 'text', width: 120 },
  { key: 'component_type',            label: '零组件类型',   type: 'text', width: 100 },
  { key: 'component_version_status',  label: '版本状态',     type: 'text', width: 80  },
  { key: 'purchase_status',           label: '采购状态',     type: 'text', width: 80  },
  { key: 'configuration',             label: '配置',         type: 'text', width: 80  },
  { key: 'parent_bom_row',            label: '父级BOM 行',   type: 'text', width: 120 },
  { key: 'part_no',                   label: '零件号',       type: 'text', width: 120 },
  { key: 'unit',                      label: '单位',         type: 'text', width: 50  },
  { key: 'material',                  label: '材料',         type: 'text', width: 100 },
  { key: 'temp_vpps',                 label: '临时VPPS',     type: 'text', width: 120 },
  { key: 'remark',                    label: '备注',         type: 'text', width: 200 },
  // CATIA 实例数据
  { key: 'catia_occurrence_name',     label: 'catiaOccurrenceName', type: 'text', width: 160 },
  { key: 'catia_file_name',           label: 'catiaFileName',       type: 'text', width: 200 },
  { key: 'catia_uuid',                label: 'catiaUUID',           type: 'text', width: 160 },
  // 变换矩阵 & 限定框
  { key: 'default_matrix',            label: '默认变换矩阵',  type: 'text', width: 100 },
  { key: 'abs_matrix',                label: '绝对变换矩阵',  type: 'text', width: 100 },
  { key: 'rel_matrix',                label: '相对变换矩阵',  type: 'text', width: 100 },
  { key: 'local_bbox',                label: '限定框',       type: 'text', width: 120 },
  // ECN / FNA
  { key: 'ecn',                       label: 'ECN编码',      type: 'text', width: 120 },
  { key: 'fna',                       label: 'FNA',          type: 'text', width: 100 },
  // 紧固件主件识别分析结果
  { key: 'geo_main_part',             label: '几何推测主件',  type: 'text', width: 180 },
  { key: 'ref_main_vpps_desc',        label: '参考主件VPPS描述', type: 'text', width: 200 },
  { key: 'ref_main_vpps',             label: '参考主件vpps', type: 'text', width: 140 },
  { key: 'main_part_consistency',     label: '主件一致性状态', type: 'text', width: 160 },
  { key: 'geo_evidence',              label: '推测主件几何依据', type: 'text', width: 180 },
  { key: 'lr_side',                   label: '零件左右侧',   type: 'text', width: 80  },
];

const PBOM_DEFAULT_COLS = ['name','catia_occurrence_name','component_id','quantity','component_type','vpps']
  .map(k => PBOM_FULL_COLS.find(c => c.key === k)).filter(Boolean);

const _DETAIL_KEYS = [
  { key: 'component_id',             label: '零组件 ID' },
  { key: 'part_no',                  label: '零件号' },
  { key: 'name',                     label: '名称' },
  { key: 'vpps',                     label: 'VPPS' },
  { key: 'vpps_desc',                label: 'VPPS描述' },
  { key: 'parent_vpps',              label: '父级VPPS' },
  { key: 'parent_vpps_name',         label: '父级名称' },
  { key: 'level',                    label: '层级' },
  { key: 'quantity',                 label: '数量' },
  { key: 'unit',                     label: '单位' },
  { key: 'component_type',           label: '零组件类型' },
  { key: 'component_version_status', label: '版本状态' },
  { key: 'purchase_status',          label: '采购状态' },
  { key: 'torque',                   label: '扭矩' },
  { key: 'torque_importance',        label: '扭矩重要度' },
  { key: 'ownership_user',           label: '所有权用户' },
  { key: 'variable_formula',         label: '变量公式' },
  { key: 'configuration',            label: '配置' },
  { key: 'bom_row',                  label: 'BOM 行' },
  { key: 'bom_row_label',            label: 'BOM 行标签' },
  { key: 'parent_bom_row',           label: '父级BOM 行' },
  { key: 'home',                     label: 'Home' },
  { key: 'temp_vpps',                label: '临时修正VPPS' },
  { key: 'remark',                   label: '备注' },
  // CATIA 实例数据
  { key: 'catia_occurrence_name',    label: 'catiaOccurrenceName' },
  { key: 'catia_file_name',          label: 'catiaFileName' },
  { key: 'catia_uuid',               label: 'catiaUUID' },
  // 变换矩阵 & 限定框
  { key: 'default_matrix',           label: '默认变换矩阵' },
  { key: 'abs_matrix',               label: '绝对变换矩阵' },
  { key: 'rel_matrix',               label: '相对变换矩阵' },
  { key: 'local_bbox',               label: '限定框' },
  // ECN / FNA
  { key: 'ecn',                      label: 'ECN编码' },
  { key: 'fna',                      label: 'FNA' },
  // 紧固件主件识别分析结果
  { key: 'geo_main_part',            label: '几何推测主件' },
  { key: 'ref_main_vpps_desc',       label: '参考主件VPPS描述' },
  { key: 'ref_main_vpps',            label: '参考主件vpps' },
  { key: 'main_part_consistency',    label: '主件一致性状态' },
  { key: 'geo_evidence',             label: '推测主件几何依据' },
  { key: 'lr_side',                  label: '零件左右侧' },
];

/* ── PBOM 匹配键（temp_vpps 优先）──────────────────────── */
function _matchKey(p) {
  const bom  = (p.bom_row || '').trim();
  const cid  = (p.component_id || '').trim();
  const vpps = (p.temp_vpps || p.vpps || '').trim();
  const pno  = (p.part_no || '').trim();
  if (bom && cid) return `${bom}|${cid}`;
  if (bom)  return bom;
  if (vpps) return vpps;
  if (cid)  return cid;
  if (pno)  return pno;
  return '';
}

const _CMP_FIELDS = [
  'name', 'quantity', 'unit', 'material',
  'component_type', 'component_version_status', 'purchase_status',
  'torque', 'torque_importance', 'variable_formula',
  'vpps_desc', 'parent_vpps', 'parent_vpps_name',
  'ownership_user', 'configuration',
  // 注：bom_row / bom_row_label / parent_bom_row 是位置序号，行删减后会被重新编号，
  // 不参与内容对比，避免把无内容变化的行误报为修改。
];

const _FIELD_LABELS = {
  name: '名称', quantity: '数量', unit: '单位', material: '材料',
  component_type: '类型', component_version_status: '版本状态',
  purchase_status: '采购状态', torque: '扭矩', torque_importance: '扭矩重要度',
  variable_formula: '变量公式', vpps_desc: 'VPPS描述',
  parent_vpps: '父级VPPS', parent_vpps_name: '父级名称',
  bom_row: 'BOM 行', ownership_user: '所有权用户',
  home: 'Home', configuration: '配置', parent_bom_row: '父级BOM 行',
};

/* ── 全局状态 ─────────────────────────────────────────────── */
let _projects  = [];
let _versions  = [];
let _shell     = null;   // ListDiffShell 实例
let _ieMgr     = null;
let _fastenerGroupActive = false;
const _vppsHandling = new Map(); // partGid → { action, manual_vpps, auto_suggested }
let _vppsIgnoredRowGids = new Set(); // 已通过 rule4_bulk_ignore 忽略的 pbom_row_gid 集合（本次 check 缓存）
let _vppsIgnoredOps     = [];        // 已忽略操作详情数组（含 original_value/vpps_desc）

/* ── 数据加载 ─────────────────────────────────────────────── */
async function loadProjects() {
  const res = await _cf('/api/projects');
  _projects = res?.data || [];
  const selProj = document.getElementById('sel-project');
  selProj.innerHTML = '<option value="">全部项目</option>';
  _projects.forEach(p => selProj.appendChild(_opt(p.gid, p.name)));
}

function _autoVersionName(projectGid, suffix) {
  const pname = _projects.find(p => p.gid === projectGid)?.name || '未知项目';
  const now = new Date();
  const pad = n => String(n).padStart(2, '0');
  const stamp = `${now.getFullYear()}${pad(now.getMonth()+1)}${pad(now.getDate())}${pad(now.getHours())}${pad(now.getMinutes())}`;
  return [pname, suffix?.trim(), stamp].filter(Boolean).join('-');
}

async function loadVersions() {
  const projGid = document.getElementById('sel-project').value;
  const path = projGid
    ? `/api/ebom/snapshots?project_gid=${encodeURIComponent(projGid)}`
    : '/api/ebom/snapshots';
  const res = await _cf(path);
  _versions = res?.data || [];
  if (_shell?.getBaseTLS())   _shell.getBaseTLS().refreshItems();
  if (_shell?.getTargetTLS()) _shell.getTargetTLS().refreshItems();
}

async function _loadPbomLists() {
  if (!_versions.length) {
    const projGid = document.getElementById('sel-project').value;
    const path = projGid
      ? `/api/ebom/snapshots?project_gid=${encodeURIComponent(projGid)}`
      : '/api/ebom/snapshots';
    const res = await _cf(path);
    _versions = res?.data || [];
  }
  return _versions.map(v => ({ gid: v.gid, name: v.name || v.version_tag || '未命名' }));
}

async function _loadPbomParts(itemType, listGid) {
  const res = await _cf(`/api/ebom/snapshots/${listGid}/parts`);
  const rows = res?.data || [];
  setTimeout(() => _loadSapIndicators(rows.map(r => r.gid).filter(Boolean)), 0);
  return rows;
}

/* ── 目标版本状态徽章 ────────────────────────────────────── */
const _STATUS_LABEL = { ready: '已就绪', raw: '未就绪', draft: '未就绪' };
const _STATUS_STYLE = {
  ready: 'background:rgba(166,227,161,.2);color:var(--success);border:1px solid rgba(166,227,161,.4)',
  raw:   'background:rgba(249,226,175,.15);color:var(--warning);border:1px solid rgba(249,226,175,.35)',
  draft: 'background:rgba(249,226,175,.15);color:var(--warning);border:1px solid rgba(249,226,175,.35)',
};

async function _updatePbomStatusBadge(versionGid) {
  const area   = document.getElementById('pbom-status-area');
  const badge  = document.getElementById('pbom-status-badge');
  const btn    = document.getElementById('btn-mark-ready');
  if (!area || !badge || !btn || !versionGid) { area && (area.style.display = 'none'); return; }

  const ver = _versions.find(v => v.gid === versionGid);
  const status = ver?.status || 'draft';
  const label  = _STATUS_LABEL[status] || status;
  const style  = _STATUS_STYLE[status] || _STATUS_STYLE.draft;

  badge.textContent = label;
  badge.style.cssText = style;

  if (status === 'ready') {
    btn.textContent = '取消就绪';
    btn.onclick = async () => {
      const res = await _cf(`/api/ebom/snapshots/${versionGid}/status`, {
        method: 'PATCH', body: JSON.stringify({ status: 'raw' }),
      });
      if (res?.success) {
        const v = _versions.find(v2 => v2.gid === versionGid);
        if (v) v.status = 'raw';
        _updatePbomStatusBadge(versionGid);
      }
    };
  } else {
    btn.textContent = '标记为可用';
    btn.onclick = async () => {
      const res = await _cf(`/api/ebom/snapshots/${versionGid}/status`, {
        method: 'PATCH', body: JSON.stringify({ status: 'ready' }),
      });
      if (res?.success) {
        const v = _versions.find(v2 => v2.gid === versionGid);
        if (v) v.status = 'ready';
        _updatePbomStatusBadge(versionGid);
      }
    };
  }
  area.style.display = 'flex';
}

/* ── 自我标注辅助 ─────────────────────────────────────────── */
function _makePinEl(p) {
  const pin = document.createElement('span');
  pin.className = 'sap-row-pin';
  pin.title = '自我标注';
  pin.dataset.gid = p.gid || '';
  pin.innerHTML = '<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="17" x2="12" y2="22"/><path d="M5 17h14v-1.76a2 2 0 00-1.11-1.79l-1.78-.9A2 2 0 0115 10.76V6h1a2 2 0 000-4H8a2 2 0 000 4h1v4.76a2 2 0 01-1.11 1.79l-1.78.9A2 2 0 005 15.24z"/></svg>';
  pin.addEventListener('click', e => {
    e.stopPropagation();
    window.SelfAnnotationPanel?.open(p.gid, p.name || p.vpps || '', e.currentTarget);
  });
  return pin;
}

async function _loadSapIndicators(gids) {
  if (!gids.length) return;
  // 分批，每批 500 条
  for (let i = 0; i < gids.length; i += 500) {
    const chunk = gids.slice(i, i + 500);
    const res = await _cf(`/api/self_ann/batch?gids=${chunk.join(',')}`);
    if (!res) return;
    Object.entries(res).forEach(([gid, info]) => {
      document.querySelectorAll(`.sap-row-pin[data-gid="${gid}"]`).forEach(el => {
        if (info.status) {
          el.dataset.status = info.status;
          el.closest('.part-row')?.classList.add('has-sap-ann');
        } else {
          delete el.dataset.status;
          el.closest('.part-row')?.classList.remove('has-sap-ann');
        }
      });
    });
  }
}

/* ── VPPS 核对表格渲染 ──────────────────────────────────── */
const VCT_COLS = [
  { key: 'name',                  label: '零组件名字',        w: 80  },
  { key: 'catia_occurrence_name', label: 'catia实例名',       w: 80  },
  { key: 'vpps',                  label: 'VPPS',             w: 80  },
  { key: 'vpps_desc',             label: 'VPPS描述',         w: 80  },
  { key: 'parent_bom_row',        label: '父级',             w: 70  },
  { key: 'parent_vpps',           label: '父级VPPS',         w: 110 },
  { key: 'parent_vpps_name',      label: '父级VPPS描述',     w: 100 },
  { key: 'ref_main_vpps',         label: '参考主件VPPS',     w: 110 },
  { key: 'ref_main_vpps_desc',    label: '参考主件VPPS描述', w: 160 },
  { key: 'geo_contact_parts',     label: '几何接触件',       w: 220 },
  { key: 'main_part_consistency', label: '主件一致性',       w: 90  },
  { key: 'lr_side',               label: '左右侧',           w: 55  },
];
const VCT_EXTRA = [
  { key: '_nok',      label: 'NOK',      w: 150 },
  { key: '_handling', label: '处理措施', w: 120 },
  { key: '_manual',   label: '手动VPPS', w: 150 },
];
const VCT_TOTAL_W = VCT_COLS.reduce((s, c) => s + c.w, 0)
                  + VCT_EXTRA.reduce((s, c) => s + c.w, 0);

function _refreshManualCell(cell, handlingKey, err) {
  cell.innerHTML = '';
  const h = _vppsHandling.get(handlingKey) || {};
  if (h.auto_suggested) {
    const badge = document.createElement('span');
    badge.className = 'vct-suggested-badge';
    badge.textContent = '建议';
    cell.appendChild(badge);
  }
  const inp = document.createElement('input');
  inp.type = 'text';
  inp.className = 'vct-manual-inp' + (h.auto_suggested ? ' vct-manual-suggested' : '');
  inp.value = h.manual_vpps || '';
  inp.placeholder = h.action === 'remark' ? '输入备注…' : '手动输入…';
  inp.addEventListener('input', () => {
    const cur = _vppsHandling.get(handlingKey) || {};
    cur.manual_vpps = inp.value;
    if (cur.auto_suggested && inp.value !== (err?.suggestion || '')) {
      cur.auto_suggested = false;
      inp.classList.remove('vct-manual-suggested');
      cell.querySelector('.vct-suggested-badge')?.remove();
    }
    _vppsHandling.set(handlingKey, cur);
  });
  cell.appendChild(inp);
}

function _renderVppsCheckTable(checkResult, targetRows) {
  const targetTLS = _shell?.getTargetTLS();
  if (!targetTLS) return;
  const bodyEl = targetTLS._colBodyEl || targetTLS._mountEl?.querySelector('.col-body');
  if (!bodyEl) return;

  const rowErrorMap = checkResult.rowErrorMap || new Map();
  const TOTAL_SPAN  = VCT_COLS.length + VCT_EXTRA.length;
  const _he = s => String(s || '').replace(/[&<>"']/g,
    c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  // 前 4 列冻结（sticky）：预计算各列的累计 left 偏移
  const STICKY_COLS = 4;
  let _sOff = 0;
  const colLefts = VCT_COLS.map(c => { const l = _sOff; _sOff += c.w; return l; });

  // Pre-scan: count NOK L3 items under each L1/L2 (rows are in tree order)
  const l1NokCounts     = new Map(), l2NokCounts     = new Map();
  const l1IgnoredCounts = new Map(), l2IgnoredCounts = new Map();
  let prescanL1 = null, prescanL2 = null;
  targetRows.forEach(p => {
    const lv = p.level || 3, gid = p.gid || '';
    if      (lv === 1) { prescanL1 = gid; prescanL2 = null; }
    else if (lv === 2) { prescanL2 = gid; }
    else if (lv === 3) {
      const n = (rowErrorMap.get(gid) || []).length;
      if (n) {
        if (prescanL2) l2NokCounts.set(prescanL2, (l2NokCounts.get(prescanL2) || 0) + 1);
        if (prescanL1) l1NokCounts.set(prescanL1, (l1NokCounts.get(prescanL1) || 0) + 1);
      }
      if (!n && _vppsIgnoredRowGids.has(gid)) {
        if (prescanL2) l2IgnoredCounts.set(prescanL2, (l2IgnoredCounts.get(prescanL2) || 0) + 1);
        if (prescanL1) l1IgnoredCounts.set(prescanL1, (l1IgnoredCounts.get(prescanL1) || 0) + 1);
      }
    }
  });

  const outer = document.createElement('div');
  outer.className = 'vct-outer';

  const tbl = document.createElement('table');
  tbl.className = 'vct-table';
  tbl.style.minWidth = `${VCT_TOTAL_W + 4}px`;

  // ── Header ───────────────────────────────────────────────
  const thead = document.createElement('thead');
  const headerRow = document.createElement('tr');
  [...VCT_COLS, ...VCT_EXTRA].forEach((c, colIdx) => {
    const th = document.createElement('th');
    const sticky = colIdx < STICKY_COLS;
    th.className = 'vct-th' + (sticky ? ' vct-th-sticky' : '');
    th.style.width = `${c.w}px`;
    if (sticky) th.style.left = `${colLefts[colIdx]}px`;
    th.textContent = c.label;
    headerRow.appendChild(th);
  });
  thead.appendChild(headerRow);
  tbl.appendChild(thead);

  // ── Body ─────────────────────────────────────────────────
  const tbody = document.createElement('tbody');

  targetRows.forEach((p, idx) => {
    const level = p.level || 3;
    const gid   = p.gid || `row:${idx}`;

    // L1 / L2 → group header row spanning all columns（无 NOK/已忽略子行则跳过）
    if (level === 1 || level === 2) {
      const nokCt     = (level === 1 ? l1NokCounts     : l2NokCounts    ).get(gid) || 0;
      const ignoredCt = (level === 1 ? l1IgnoredCounts : l2IgnoredCounts).get(gid) || 0;
      if (!nokCt && !ignoredCt) return;
      const tr = document.createElement('tr');
      tr.className = level === 1 ? 'vct-group-l1' : 'vct-group-l2';
      const td = document.createElement('td');
      td.colSpan = TOTAL_SPAN;
      td.className = `vct-group-hdr vct-group-hdr-l${level}`;
      td.innerHTML =
        `<span class="vct-group-name">${_he(p.name || p.vpps || '')}</span>` +
        (p.vpps ? ` <span class="vct-group-vpps">${_he(p.vpps)}</span>` : '') +
        (nokCt     ? ` <span class="vct-group-nok-ct">${nokCt}&nbsp;NOK</span>`        : '') +
        (ignoredCt ? ` <span class="vct-group-ignored-ct">${ignoredCt}&nbsp;已忽略</span>` : '');
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }

    // L3: skip rows with no errors AND not ignored
    const rowErrors = rowErrorMap.get(gid) || [];
    const isIgnored = !rowErrors.length && _vppsIgnoredRowGids.has(gid);
    if (!rowErrors.length && !isIgnored) return;

    // ── 已忽略行：单行展示，不走 per-error 循环 ──────────────
    if (isIgnored) {
      const ignoredOp = _vppsIgnoredOps.find(op => op.pbom_row_gid === gid);
      const tr = document.createElement('tr');
      tr.className = 'vct-row-ignored';
      tr.dataset.rowGid = gid;
      VCT_COLS.forEach((c, colIdx) => {
        const td = document.createElement('td');
        const sticky = colIdx < STICKY_COLS;
        td.className = 'vct-td vct-cell-data vct-cell-ignored' + (sticky ? ' vct-td-sticky' : '');
        td.style.width = `${c.w}px`;
        if (sticky) td.style.left = `${colLefts[colIdx]}px`;
        td.textContent = String(p[c.key] || '');
        td.title = td.textContent;
        tr.appendChild(td);
      });
      // NOK cell → 已忽略 badge + reason
      const nokTd = document.createElement('td');
      nokTd.className = 'vct-td vct-cell-nok-single';
      nokTd.style.width = `${VCT_EXTRA[0].w}px`;
      const errDiv = document.createElement('div');
      errDiv.className = 'vct-nok-item';
      const badge = document.createElement('span');
      badge.className = 'vct-nok-badge vct-nok-ignored';
      badge.textContent = '已忽略';
      errDiv.appendChild(badge);
      if (ignoredOp) {
        const reasonSpan = document.createElement('span');
        reasonSpan.className = 'vct-nok-brief';
        const dateStr = ignoredOp.created_at ? ignoredOp.created_at.substring(0, 10) : '—';
        reasonSpan.textContent = `${ignoredOp.actor_name || '未知'} ${dateStr}`;
        reasonSpan.title = `由 ${ignoredOp.actor_name || '未知'} 于 ${dateStr} 忽略`;
        errDiv.appendChild(reasonSpan);
      }
      nokTd.appendChild(errDiv);
      tr.appendChild(nokTd);
      // Handling cell — 撤销忽略按钮
      const handlingTd = document.createElement('td');
      handlingTd.className = 'vct-td vct-cell-handling';
      handlingTd.style.width = `${VCT_EXTRA[1].w}px`;
      if (ignoredOp) {
        const revertBtn = document.createElement('button');
        revertBtn.className = 'vct-revert-btn';
        revertBtn.textContent = '撤销忽略';
        revertBtn.onclick = async () => {
          revertBtn.disabled = true;
          revertBtn.textContent = '撤销中…';
          try {
            const user = window._currentUser || {};
            await _cf(`/api/vpps-operations/${ignoredOp.gid}/revert`, {
              method: 'POST',
              body: JSON.stringify({ reverted_by_gid: user.gid || '', reverted_by_name: user.name || '' }),
            });
            // 直接 rerunCheck，让 API 重新加载已忽略状态，保证本地与服务端一致
            const activeIdx = _shell?._activeCheckIdx ?? -1;
            if (activeIdx >= 0) await _shell.rerunCheck(activeIdx);
          } catch (e) {
            revertBtn.disabled = false;
            revertBtn.textContent = '撤销忽略';
            alert('撤销失败：' + (e?.message || e));
          }
        };
        handlingTd.appendChild(revertBtn);
      }
      tr.appendChild(handlingTd);
      // Manual cell — empty
      const manualTd = document.createElement('td');
      manualTd.className = 'vct-td';
      manualTd.style.width = `${VCT_EXTRA[2].w}px`;
      tr.appendChild(manualTd);
      tbody.appendChild(tr);
      return;
    }

    const nNok = rowErrors.length;
    rowErrors.forEach((err, errIdx) => {
      const handlingKey = `${gid}:${errIdx}`;
      const tr = document.createElement('tr');
      tr.className = 'vct-row-nok';
      tr.dataset.rowGid = gid;

      // Data cells only on first sub-row, spanning all NOK sub-rows
      if (errIdx === 0) {
        // Build field→error map for this row's errors (first error per field wins)
        const fieldErrMap = new Map();
        rowErrors.forEach(e => { if (e.field && !fieldErrMap.has(e.field)) fieldErrMap.set(e.field, e); });

        VCT_COLS.forEach((c, colIdx) => {
          const td = document.createElement('td');
          const sticky = colIdx < STICKY_COLS;
          td.className = 'vct-td vct-cell-data' + (sticky ? ' vct-td-sticky' : '');
          td.style.width = `${c.w}px`;
          if (sticky) td.style.left = `${colLefts[colIdx]}px`;
          if (nNok > 1) td.rowSpan = nNok;
          const val = String(p[c.key] || '');
          const ferr = fieldErrMap.get(c.key);
          if (c.key === 'geo_contact_parts') {
            // 几何接触件：芯片列表，绿=A、紫=B、默认=其余
            const list = p.geo_contact_parts;
            if (Array.isArray(list) && list.length) {
              td.className += ' vct-contact-cell';
              list.forEach(item => {
                const chip = document.createElement('span');
                chip.className = 'vct-contact-chip' +
                  (item.role === 'A' ? ' vct-contact-chip-a' :
                   item.role === 'B' ? ' vct-contact-chip-b' : '');
                // label = catia_occurrence_name（实例唯一），title 附零件名
                chip.textContent = item.label || item.name;
                chip.title = item.label !== item.name
                  ? `${item.label}\n${item.name}` : item.label;
                td.appendChild(chip);
              });
            } else {
              td.textContent = '—';
              td.style.color = 'var(--text-muted)';
            }
          } else if (ferr) {
            // Highlight: current value (wrong) + suggested value (correct)
            td.classList.add('vct-cell-has-err');
            const cur = document.createElement('span');
            cur.className = 'vct-val-current';
            cur.textContent = val || '(空)';
            cur.title = val;
            td.appendChild(cur);
            if (ferr.suggestion) {
              const sug = document.createElement('span');
              sug.className = 'vct-val-suggested';
              sug.textContent = ferr.suggestion;
              sug.title = ferr.suggestion;
              td.appendChild(sug);
            }
          } else {
            td.textContent = val;
            td.title = val;
          }
          tr.appendChild(td);
        });
      }

      // NOK cell — brief badge + short label only
      const nokTd = document.createElement('td');
      nokTd.className = 'vct-td vct-cell-nok-single';
      nokTd.style.width = `${VCT_EXTRA[0].w}px`;
      const errDiv = document.createElement('div');
      errDiv.className = 'vct-nok-item';
      const badge = document.createElement('span');
      badge.className = `vct-nok-badge vct-nok-r${err.rule}`;
      badge.textContent = err.badge || `R${err.rule}`;
      const briefSpan = document.createElement('span');
      briefSpan.className = 'vct-nok-brief';
      briefSpan.textContent = err.brief || err.msg;
      briefSpan.title = err.msg;
      errDiv.appendChild(badge);
      errDiv.appendChild(briefSpan);
      nokTd.appendChild(errDiv);
      tr.appendChild(nokTd);

      // Handling dropdown (per NOK item)
      const handlingTd = document.createElement('td');
      handlingTd.className = 'vct-td vct-cell-handling';
      handlingTd.style.width = `${VCT_EXTRA[1].w}px`;
      const hasAlias = err.actionLabel === '可接受别名' && !!err.onAction;
      const hasSugg  = !!err.suggestion;
      const h = _vppsHandling.get(handlingKey) || {};
      const sel = document.createElement('select');
      sel.className = 'vct-action-sel';
      [['', '—'],
       ...(hasAlias ? [['alias',      '可接受别名'      ]] : []),
       ...(hasSugg  ? [['suggestion', '接受程序修改建议']] : []),
       ['remark', '备注'],
      ].forEach(([val, lbl]) => {
        const o = document.createElement('option');
        o.value = val; o.textContent = lbl;
        sel.appendChild(o);
      });
      sel.value = h.action || '';

      // Manual cell (per NOK item)
      const manualTd = document.createElement('td');
      manualTd.className = 'vct-td vct-cell-manual';
      manualTd.style.width = `${VCT_EXTRA[2].w}px`;
      _refreshManualCell(manualTd, handlingKey, err);

      sel.addEventListener('change', () => {
        const action = sel.value;
        const hCur = { ...(_vppsHandling.get(handlingKey) || {}), action };
        if (action === 'alias') {
          if (err.onAction) err.onAction();
          hCur.auto_suggested = false;
        } else if (action === 'suggestion') {
          if (err.suggestion) { hCur.manual_vpps = err.suggestion; hCur.auto_suggested = true; }
        } else {
          hCur.auto_suggested = false;
        }
        _vppsHandling.set(handlingKey, hCur);
        _refreshManualCell(manualTd, handlingKey, err);
      });
      handlingTd.appendChild(sel);
      tr.appendChild(handlingTd);
      tr.appendChild(manualTd);

      tbody.appendChild(tr);
    });
  });

  tbl.appendChild(tbody);
  outer.appendChild(tbl);
  bodyEl.innerHTML = '';
  bodyEl.appendChild(outer);
}

/* ── VPPS 处理措施队列 ───────────────────────────────────── */
let _vppsPendingActions  = [];
let _vppsOnPendingChange = null; // (count) => void，由 diff shell 注入

function _queueVppsAlias({ vppsPartGid, alias, pbomPartGid }) {
  const key = `alias:${vppsPartGid}:${alias}`;
  if (_vppsPendingActions.find(a => a.key === key)) return; // 防重复
  _vppsPendingActions.push({
    key,
    desc: `别名 "${alias}"`,
    fn: async () => {
      const res = await _cf(`/api/craft_lib/part_names/${vppsPartGid}/accept_alias`, {
        method: 'POST',
        body: JSON.stringify({ alias, pbom_part_gid: pbomPartGid }),
      });
      if (!res?.success) throw new Error(res?.detail || '未知错误');
    },
  });
  _vppsOnPendingChange?.(_vppsPendingActions.length);
}

/* ── VPPS 核对（extraCheck 定义）────────────────────────── */
const vppsCheckDef = {
  label: 'vpps核对',
  title: 'VPPS 核对',
  run: async (targetRows, baseRows) => {
    if (!targetRows.length) {
      return {
        rules: [],
        summary: [{ label: '无数据', count: 0, type: 'same' }],
        errorGroups: [],
        ok: true,
        _noData: true,
      };
    }

    // 加载已忽略的 rule4 行集合（按版本 GID 过滤）
    const _pbomVersionGid = _shell?.getTargetTLS()?.getSelectedList() || '';
    try {
      if (_pbomVersionGid) {
        const ignRes = await _cf(`/api/vpps-operations/rule4-ignores?pbom_version_gid=${encodeURIComponent(_pbomVersionGid)}`);
        _vppsIgnoredRowGids = new Set(ignRes?.ignored_row_gids || []);
        _vppsIgnoredOps     = ignRes?.operations || [];
      } else {
        _vppsIgnoredRowGids = new Set();
        _vppsIgnoredOps     = [];
      }
    } catch (_) {
      _vppsIgnoredRowGids = new Set();
      _vppsIgnoredOps     = [];
    }

    let vppsRef = [];
    try {
      const res = await _cf('/api/craft_lib/part_names');
      vppsRef = res?.data || [];
    } catch (e) {
      return {
        rules: [],
        summary: [{ label: '加载主数据失败', count: 0, type: 'del' }],
        errorGroups: [{ title: '错误', items: [{ msg: e.message, badge: '错误' }] }],
        ok: false,
      };
    }

    const refMap = new Map();
    vppsRef.forEach(r => {
      const v = (r.vpps || '').trim();
      const g = (r.gid || '').trim();
      if (v) refMap.set(v, r);
      if (g && !refMap.has(g)) refMap.set(g, r);
    });

    // aliasMap: 别名字符串 → { vppsPartGid, canonicalVpps }
    const aliasMap = new Map();
    vppsRef.forEach(r => {
      (Array.isArray(r.alias) ? r.alias : []).forEach(a => {
        if (a) aliasMap.set(a.trim(), { vppsPartGid: r.gid, canonicalVpps: (r.vpps || '').trim() });
      });
    });

    const errors = [];
    const aliasMatches = [];
    const rowErrorMap = new Map();
    const _addRowErr = (gid, err) => {
      const k = gid || '';
      if (!rowErrorMap.has(k)) rowErrorMap.set(k, []);
      rowErrorMap.get(k).push(err);
    };

    // 规则1 + 规则3：主数据核对 + 层级前缀（仅检查 level 3 零件）
    const _normVppsDesc = s => {
      s = (s || '').trim();
      const d = s.indexOf('-');
      if (d !== -1) s = s.slice(d + 1);
      return s.replace(/[^\u4e00-\u9fff\u3400-\u4dbf]/g, '');
    };

    targetRows.forEach((p, idx) => {
      if (p.level != null && p.level !== 3) return;   // L1/L2 跳过
      const vpps       = (p.vpps || '').trim();
      const desc       = (p.vpps_desc || '').trim();
      const parentVpps = (p.parent_vpps || '').trim();
      if (!vpps) return;
      const ref = refMap.get(vpps);
      if (!ref) {
        errors.push({ rule: 1, vpps, row: idx + 1, msg: `VPPS "${vpps}" 在主数据中不存在` });
        _addRowErr(p.gid || `row:${idx}`, { rule: 1, badge: '主数据', field: 'vpps',
          brief: '无主数据', msg: `VPPS "${vpps}" 在主数据中不存在` });
      } else if (desc) {
        const refEn = (ref.vpps_description || '').trim();
        const refCn = (ref.vpps_desc_cn || '').trim();
        const descN = _normVppsDesc(desc);
        const refEnN = _normVppsDesc(refEn);
        const refCnN = _normVppsDesc(refCn);
        const matched = (descN && (descN === refEnN || descN === refCnN))
                     || desc === refEn || desc === refCn;
        if (!matched) {
          const aliasHit = aliasMap.get(desc);
          if (aliasHit && aliasHit.canonicalVpps === vpps) {
            aliasMatches.push({ vpps, row: idx + 1, desc });
          } else {
            const expected = refCn || refEn;
            errors.push({
              rule: 1, vpps, row: idx + 1,
              msg: `描述不一致: "${desc}" ≠ 主数据"${expected}"`,
              ...(ref ? {
                actionLabel: '可接受别名',
                onAction: () => _queueVppsAlias({
                  vppsPartGid: ref.gid,
                  alias: desc,
                  pbomPartGid: p.gid || '',
                }),
              } : {}),
            });
            _addRowErr(p.gid || `row:${idx}`, {
              rule: 1, badge: '主数据', field: 'vpps_desc',
              brief: '描述≠主数据',
              msg: `描述不一致: "${desc}" ≠ 主数据"${expected}"`,
              suggestion: expected,
              ...(ref ? {
                actionLabel: '可接受别名',
                onAction: () => _queueVppsAlias({
                  vppsPartGid: ref.gid,
                  alias: desc,
                  pbomPartGid: p.gid || '',
                }),
                _aliasData: { vppsPartGid: ref.gid, alias: desc, pbomPartGid: p.gid || '' },
              } : {}),
            });
          }
        }
      }
      if (parentVpps && vpps) {
        const prefix = parentVpps.replace(/\.+$/, '');
        // 用 prefix+'.' 而非 prefix，避免 "ABC.1" 误放过 "ABC.10.1" 这类同级编号
        if (!vpps.startsWith(prefix + '.') && vpps !== prefix) {
          errors.push({ rule: 3, vpps, row: idx + 1, msg: `层级不匹配: "${vpps}" 不以父级 "${parentVpps}" 开头` });
          _addRowErr(p.gid || `row:${idx}`, { rule: 3, badge: '层级', field: 'vpps',
            brief: '前缀≠父级', msg: `层级不匹配: "${vpps}" 不以父级 "${parentVpps}" 开头` });
        }
      }
    });

    // 规则2：父级一致性（仅检查 level 3 零件）
    const byBomRow = new Map();
    const byGid    = new Map();
    targetRows.forEach(p => {
      if (p.bom_row) byBomRow.set(p.bom_row.trim(), p);
      if (p.gid)     byGid.set(p.gid, p);
    });
    targetRows.forEach((p, idx) => {
      if (p.level != null && p.level !== 3) return;   // L1/L2 跳过
      const parentVpps   = (p.parent_vpps    || '').trim();
      const parentBomRow = (p.parent_bom_row || '').trim();
      const parentGid    = (p.parent_gid     || '').trim();
      if (!parentVpps) return;
      const parentPart = (parentBomRow && byBomRow.get(parentBomRow))
                      || (parentGid    && byGid.get(parentGid))
                      || null;
      if (!parentPart) return;
      const actualVpps = (parentPart.vpps || '').trim();
      if (actualVpps && actualVpps !== parentVpps) {
        const vpps = (p.vpps || p.part_no || '-').trim();
        errors.push({ rule: 2, vpps, row: idx + 1,
          msg: `父级VPPS字段"${parentVpps}" ≠ 父级零件实际VPPS"${actualVpps}"` });
        _addRowErr(p.gid || `row:${idx}`, {
          rule: 2, badge: '父级', field: 'parent_vpps',
          brief: '父级VPPS≠',
          msg: `父级VPPS字段"${parentVpps}" ≠ 父级零件实际VPPS"${actualVpps}"`,
          suggestion: actualVpps,
        });
      }
    });

    // 规则4：紧固件主件一致性（BOM同级过滤 + 几何 + VPPS描述核对）
    const FASTENER_TYPES_R4 = new Set(['标准件', '非标件']);
    const STRUCT_TYPES_R4   = new Set(['零部件']); // 只用叶子级零件；装置是装配体，AABB覆盖全部子件，必然误报

    // ── 几何工具 ─────────────────────────────────────────────────────────────
    function _r4ParseMatrix(s) {
      if (!s || !s.trim()) return null;
      const v = s.trim().split(/\s+/).map(Number);
      if (v.length !== 16 || v.some(isNaN)) return null;
      return v; // row-major flat [16], numpy convention: row @ M
    }
    function _r4ParseBbox(s) {
      if (!s || !s.trim()) return null;
      const v = s.trim().split(',').map(Number);
      if (v.length !== 6 || v.some(isNaN)) return null;
      return v; // [xmin,ymin,zmin,xmax,ymax,zmax]
    }
    function _r4WorldBbox(mat, bbox) {
      const [xmin,ymin,zmin,xmax,ymax,zmax] = bbox;
      const corners = [[xmin,ymin,zmin],[xmax,ymin,zmin],[xmin,ymax,zmin],[xmax,ymax,zmin],
                       [xmin,ymin,zmax],[xmax,ymin,zmax],[xmin,ymax,zmax],[xmax,ymax,zmax]];
      const wxs=[], wys=[], wzs=[];
      for (const [cx,cy,cz] of corners) {
        wxs.push(cx*mat[0] + cy*mat[4] + cz*mat[8]  + mat[12]);
        wys.push(cx*mat[1] + cy*mat[5] + cz*mat[9]  + mat[13]);
        wzs.push(cx*mat[2] + cy*mat[6] + cz*mat[10] + mat[14]);
      }
      return [[Math.min(...wxs),Math.min(...wys),Math.min(...wzs)],
              [Math.max(...wxs),Math.max(...wys),Math.max(...wzs)]];
    }
    function _r4Overlap(mn1, mx1, mn2, mx2) {
      const dx = Math.max(0, Math.min(mx1[0],mx2[0]) - Math.max(mn1[0],mn2[0]));
      const dy = Math.max(0, Math.min(mx1[1],mx2[1]) - Math.max(mn1[1],mn2[1]));
      const dz = Math.max(0, Math.min(mx1[2],mx2[2]) - Math.max(mn1[2],mn2[2]));
      return dx * dy * dz;
    }
    /** 结构件 S 是否完全包住紧固件 F */
    function _r4Contains(fWmin, fWmax, sWmin, sWmax) {
      return sWmin[0] <= fWmin[0] && sWmax[0] >= fWmax[0] &&
             sWmin[1] <= fWmin[1] && sWmax[1] >= fWmax[1] &&
             sWmin[2] <= fWmin[2] && sWmax[2] >= fWmax[2];
    }
    /** 点 pt 是否在 AABB 内部（含边界） */
    function _r4AabbContainsPt(pt, wmin, wmax) {
      return pt[0] >= wmin[0] && pt[0] <= wmax[0] &&
             pt[1] >= wmin[1] && pt[1] <= wmax[1] &&
             pt[2] >= wmin[2] && pt[2] <= wmax[2];
    }
    /** 从 local_bbox 推断轴向本地单位向量：
     *  螺栓（细长）→ 最长维；螺母（扁平）→ 最短维 */
    function _r4InferLocalAxis(bbox, isNut) {
      const dims = [
        { d: bbox[3]-bbox[0], v: [1,0,0] },
        { d: bbox[4]-bbox[1], v: [0,1,0] },
        { d: bbox[5]-bbox[2], v: [0,0,1] },
      ].sort((a, b) => a.d - b.d);
      return isNut ? dims[0].v : dims[2].v; // 螺母取最短，螺栓取最长
    }
    /** 本地方向向量经 abs_matrix 旋转部分变换到世界坐标（不含平移） */
    function _r4RotateDir(mat, dir) {
      const [dx, dy, dz] = dir;
      return [
        dx*mat[0] + dy*mat[4] + dz*mat[8],
        dx*mat[1] + dy*mat[5] + dz*mat[9],
        dx*mat[2] + dy*mat[6] + dz*mat[10],
      ];
    }
    /** 过 origin 沿 dir 的无限直线是否与 AABB 相交（slab 法，双向）
     *  双向：不限制 t 正负，即轴线延长线两侧均检测 */
    function _r4LineHitsAABB(origin, dir, wmin, wmax) {
      let tMin = -Infinity, tMax = Infinity;
      for (let i = 0; i < 3; i++) {
        const d = dir[i];
        if (Math.abs(d) < 1e-9) {
          if (origin[i] < wmin[i] || origin[i] > wmax[i]) return false;
        } else {
          const t1 = (wmin[i] - origin[i]) / d;
          const t2 = (wmax[i] - origin[i]) / d;
          tMin = Math.max(tMin, Math.min(t1, t2));
          tMax = Math.min(tMax, Math.max(t1, t2));
        }
      }
      return tMin <= tMax;
    }
    /** 是否螺母（名称含"螺母"或"NUT"，不区分大小写） */
    function _r4IsNut(part) {
      const n = (part.name || '').toUpperCase();
      return n.includes('螺母') || n.includes('NUT');
    }
    /** 提取 abs_matrix 中本地原点的世界坐标（螺栓/螺母头部位置，row-major mat[12,13,14]） */
    function _r4Origin(mat) { return [mat[12], mat[13], mat[14]]; }
    /** 点到 AABB 表面的有符号距离：内部为负（越小越深），外部为正欧氏距离 */
    function _r4DistToAABB(pt, wmin, wmax) {
      const inside = pt[0] >= wmin[0] && pt[0] <= wmax[0] &&
                     pt[1] >= wmin[1] && pt[1] <= wmax[1] &&
                     pt[2] >= wmin[2] && pt[2] <= wmax[2];
      if (inside) {
        return -Math.min(
          pt[0]-wmin[0], wmax[0]-pt[0],
          pt[1]-wmin[1], wmax[1]-pt[1],
          pt[2]-wmin[2], wmax[2]-pt[2]
        );
      }
      const dx = Math.max(wmin[0]-pt[0], 0, pt[0]-wmax[0]);
      const dy = Math.max(wmin[1]-pt[1], 0, pt[1]-wmax[1]);
      const dz = Math.max(wmin[2]-pt[2], 0, pt[2]-wmax[2]);
      return Math.sqrt(dx*dx + dy*dy + dz*dz);
    }
    /**
     * 综合评分（三信号合成）：
     *   1. 归一化重叠  = overlap / fastener_vol（消除大件偏差）
     *   2. 表面近接分  = sDiag / (sDiag + surfDist×2)（点到AABB表面距离，在面内=0）
     *   3. 三轴对齐分  = max(|dot(localX,dir)|, |dot(localY,dir)|, |dot(localZ,dir)|)
     *                    不假设哪条轴是螺栓轴，取三轴最大值
     */
    function _r4Score(fWmin, fWmax, fMat, sWmin, sWmax) {
      // 紧固件世界中心
      const fCx = (fWmin[0]+fWmax[0])/2, fCy = (fWmin[1]+fWmax[1])/2, fCz = (fWmin[2]+fWmax[2])/2;
      // 紧固件 bbox 体积（归一化用，最小取 1e-9 防除零）
      const fVol = Math.max(1e-9,
        (fWmax[0]-fWmin[0]) * (fWmax[1]-fWmin[1]) * (fWmax[2]-fWmin[2]));
      // 结构件世界中心 & 对角线（参考尺度）
      const sCx = (sWmin[0]+sWmax[0])/2, sCy = (sWmin[1]+sWmax[1])/2, sCz = (sWmin[2]+sWmax[2])/2;
      const sDiag = Math.sqrt(
        Math.pow(sWmax[0]-sWmin[0],2)+Math.pow(sWmax[1]-sWmin[1],2)+Math.pow(sWmax[2]-sWmin[2],2)
      ) || 1;

      // ① 归一化重叠
      const vol = _r4Overlap(fWmin, fWmax, sWmin, sWmax);
      const relOverlap = Math.min(1, vol / fVol);

      // ② 紧固件中心到结构件 AABB 表面距离（内部=0）
      const ex = Math.max(0, sWmin[0]-fCx, fCx-sWmax[0]);
      const ey = Math.max(0, sWmin[1]-fCy, fCy-sWmax[1]);
      const ez = Math.max(0, sWmin[2]-fCz, fCz-sWmax[2]);
      const surfDist  = Math.sqrt(ex*ex + ey*ey + ez*ez);
      const proxScore = sDiag / (sDiag + surfDist * 2);   // ∈ (0,1]

      // ③ 三轴对齐：紧固件局部 XYZ 轴与紧固件→结构件中心方向的最大绝对点积
      let alignScore = 0;
      if (fMat) {
        const ddx = sCx-fCx, ddy = sCy-fCy, ddz = sCz-fCz;
        const dLen = Math.sqrt(ddx*ddx+ddy*ddy+ddz*ddz) || 1;
        const axDot = (ax, ay, az) => {
          const aLen = Math.sqrt(ax*ax+ay*ay+az*az) || 1;
          return Math.abs((ddx*ax + ddy*ay + ddz*az) / (dLen * aLen));
        };
        alignScore = Math.max(
          axDot(fMat[0],fMat[1],fMat[2]),    // 局部 X
          axDot(fMat[4],fMat[5],fMat[6]),    // 局部 Y
          axDot(fMat[8],fMat[9],fMat[10])    // 局部 Z
        );
      }

      // ④ 合成：有实质重叠时重叠主导；无重叠（简化建模）时由近接+对齐接管
      return relOverlap > 0.01
        ? relOverlap * 2.0 + proxScore * 0.6 + alignScore * 0.4
        : proxScore         + alignScore * 0.5;
    }
    // ── VPPS描述解析 ──────────────────────────────────────────────────────────
    // 返回 [aStr, bStr, sep]：sep='到'|'与'|null
    function _r4ExtractAB(vppsDesc) {
      if (!vppsDesc) return [null, null, null];
      const s = vppsDesc.replace(/\(.*?\)/g, '').trim();
      const dash = s.indexOf('-');
      if (dash === -1) return [null, null, null];
      const after = s.slice(dash + 1).trim();
      for (const sep of ['到', '与']) {
        if (after.includes(sep)) {
          const [a,b] = after.split(sep,2);
          return [a.trim(), b.trim(), sep];
        }
      }
      return [after.trim(), null, null];
    }
    // "A与B"时取两者中匹配分更高的（备用，新Rule4各自独立验证，暂不使用）
    function _r4MatchHomeAB(aStr, bStr, sep, candidates) {
      const mA = _r4MatchHome(aStr, candidates);
      if (sep !== '与' || !bStr) return mA;
      const mB = _r4MatchHome(bStr, candidates);
      if (!mA) return mB;
      if (!mB) return mA;
      // 两者都有匹配时取更高分的
      const scA = _r4NameSim(aStr, mA.name||'');
      const scB = _r4NameSim(bStr, mB.name||'');
      return scA >= scB ? mA : mB;
    }
    function _r4ExtractLR(name) {
      if ((name||'').includes('左')) return '左';
      if ((name||'').includes('右')) return '右';
      return '';
    }
    function _r4NameSim(query, partName, threshold=0.60) {
      if (!query || !partName) return 0;
      if (query === partName) return query.length * 10;
      let best = 0;
      for (let i=0; i<query.length; i++)
        for (let j=i+2; j<=query.length; j++) {
          const sub = query.slice(i,j);
          if (partName.includes(sub) && sub.length > best) best = sub.length;
        }
      return (best > 0 && best / partName.length >= threshold) ? best : 0;
    }
    function _r4MatchHome(aStr, candidates) {
      if (!aStr || !candidates.length) return null;
      // "支架"不会被省略：aStr没有"支架"时排除名称含"支架"的件
      const eligible = candidates.filter(c =>
        !(!aStr.includes('支架') && (c.name||'').includes('支架')));
      let best=null, bestSc=0;
      for (const c of eligible) {
        const sc = _r4NameSim(aStr, c.name||'');
        if (sc > bestSc) { bestSc=sc; best=c; }
      }
      return best;
    }

    const rule4Errors = [];
    const r4ContactMap = new Map();
    const rule4NokRowMap = new Map(); // gid → {gid, vpps_desc} 用于忽略按钮

    // 1. 构建索引：结构件一律用 abs_matrix 变换
    //    - _r4ByParentBom：parent_bom_row → entries（BOM 结构决定，始终可信）
    //    - _r4AllStructAABB：全量，供 vpps_desc 名称推测时全局回退
    //    （不建 VPPS 兄弟索引：若 parent_vpps 填错规则2已报NOK，错误父级下的件是噪音；
    //      若填对，BOM 兄弟已覆盖，VPPS 兄弟只会引入其他分总成的件）
    const _r4AllStructAABB = [];
    const _r4ByParentBom   = new Map(); // parent_bom_row → [{part,wmin,wmax}]

    targetRows.forEach(s => {
      if (!STRUCT_TYPES_R4.has((s.component_type||'').trim())) return;
      const mat  = _r4ParseMatrix(s.abs_matrix||'');
      const bbox = _r4ParseBbox(s.local_bbox||'');
      if (!mat || !bbox) return;
      const [wmin, wmax] = _r4WorldBbox(mat, bbox);
      const entry = { part: s, wmin, wmax };
      _r4AllStructAABB.push(entry);
      const pbr = (s.parent_bom_row||'').trim();
      if (pbr) {
        if (!_r4ByParentBom.has(pbr)) _r4ByParentBom.set(pbr, []);
        _r4ByParentBom.get(pbr).push(entry);
      }
    });

    targetRows.forEach((p, idx) => {
      if (!FASTENER_TYPES_R4.has((p.component_type||'').trim())) return;
      if (p.gid && _vppsIgnoredRowGids.has(p.gid)) return; // 已忽略，跳过 rule4 检查
      const [aStr, bStr] = _r4ExtractAB(p.vpps_desc||'');
      if (!aStr) return;

      // 2. 紧固件世界 AABB + 头部原点 + 轴线方向
      const fMat  = _r4ParseMatrix(p.abs_matrix||'');
      const fBbox = _r4ParseBbox(p.local_bbox||'');
      if (!fMat || !fBbox) return;
      const [fWmin, fWmax] = _r4WorldBbox(fMat, fBbox);
      const fOrigin  = _r4Origin(fMat);
      // 螺母扁平 → 轴向是最短维；螺栓细长 → 轴向是最长维；变换到世界坐标
      const isNut    = _r4IsNut(p);
      const localAxis = _r4InferLocalAxis(fBbox, isNut);
      const worldAxis = _r4RotateDir(fMat, localAxis);

      // 3. 候选池：仅 BOM 兄弟（parent_bom_row 相同的结构件）
      //    parent_vpps 若有误规则2已报 NOK，不用 VPPS 兄弟避免引入噪音
      const pbr     = (p.parent_bom_row||'').trim();
      const poolMap = new Map();
      const _addToPool = (entries) => {
        for (const e of (entries||[])) {
          const k = e.part.gid || e.part.name;
          if (k && !poolMap.has(k)) poolMap.set(k, e);
        }
      };
      _addToPool(_r4ByParentBom.get(pbr));

      // 4. vpps描述 A/B 名称推测：先在当前池里找，找不到再全局找
      const localParts  = [...poolMap.values()].map(e => e.part);
      const globalParts = _r4AllStructAABB.map(e => e.part);
      for (const nameStr of [aStr, bStr].filter(Boolean)) {
        let match = _r4MatchHome(nameStr, localParts);
        if (!match) match = _r4MatchHome(nameStr, globalParts);
        if (match) {
          const found = _r4AllStructAABB.find(e => e.part === match);
          if (found) {
            const k = match.gid || match.name;
            if (k && !poolMap.has(k)) poolMap.set(k, found);
          }
        }
      }

      if (!poolMap.size) return;

      // 5. 按重叠体积排序，取 top-2
      // 过滤双条件：
      //   ① 结构件 AABB 不包含头部原点（排除从上方罩住螺栓头的大件）
      //   ② 轴线直线与结构件 AABB 相交（螺栓/螺母轴线必须穿过该件，排除仅 AABB 角落蹭到的件）
      const ranked = [...poolMap.values()]
        .map(e => ({ ...e, vol: _r4Overlap(fWmin, fWmax, e.wmin, e.wmax) }))
        .filter(e => e.vol > 0
          && !_r4AabbContainsPt(fOrigin, e.wmin, e.wmax)
          && _r4LineHitsAABB(fOrigin, worldAxis, e.wmin, e.wmax))
        .sort((a, b) => b.vol - a.vol)
        .slice(0, 2);
      if (!ranked.length) return;

      // 6. 用原点（头部世界坐标）重排 A/B：距原点近的 = 头侧(A)，远的 = 另一侧(B)
      const sortedAB = ranked.slice().sort(
        (a, b) => _r4DistToAABB(fOrigin, a.wmin, a.wmax) - _r4DistToAABB(fOrigin, b.wmin, b.wmax)
      );
      const geoA = sortedAB[0].part;
      const geoB = sortedAB.length > 1 ? sortedAB[1].part : null;
      const gid  = p.gid || `row:${idx}`;

      const displayList = [{ label: geoA.name, name: geoA.name, role: 'A' }];
      if (geoB) displayList.push({ label: geoB.name, name: geoB.name, role: 'B' });
      r4ContactMap.set(gid, displayList);

      // 7. 核对：vpps_desc 里的 A/B 名称是否都出现在几何 top-2 中（不要求位置对应）
      const top2Parts  = sortedAB.map(e => e.part);
      const top2Names  = top2Parts.map(s => `"${s.name}"`).join('/');
      const claimedAll = [aStr, bStr].filter(Boolean);
      for (const nameStr of claimedAll) {
        if (!_r4MatchHome(nameStr, top2Parts)) {
          if (!rule4NokRowMap.has(gid)) {
            rule4NokRowMap.set(gid, { gid, vpps_desc: p.vpps_desc || '',
              vpps: p.vpps || p.name, row: idx + 1, msgs: [] });
          }
          rule4NokRowMap.get(gid).msgs.push(`描述"${nameStr}" 不在几何top2 ${top2Names} 中`);
          rule4Errors.push({ rule: 4, gid, vpps: p.vpps || p.name, row: idx + 1,
            msg: `描述"${nameStr}" 不在几何top2 ${top2Names} 中` });
          _addRowErr(gid, { rule: 4, badge: '主件', field: 'vpps_desc',
            brief: '主件≠', msg: `描述"${nameStr}" 不在几何主件 ${top2Names} 中` });
        }
      }
    });

    // 已忽略的紧固件条目：追加到 rule4Errors，显示忽略原因，方便在主图中查看
    _vppsIgnoredOps.forEach(op => {
      const rowIdx = targetRows.findIndex(p => p.gid === op.pbom_row_gid);
      if (rowIdx < 0) return; // 此版本中已不存在该行，跳过
      const p = targetRows[rowIdx];
      if (!FASTENER_TYPES_R4.has((p.component_type||'').trim())) return;
      const dateStr  = op.created_at ? op.created_at.substring(0, 10) : '—';
      const actor    = op.actor_name || '未知';
      const origDesc = op.original_value || p.vpps_desc || '（无描述）';
      rule4Errors.push({
        rule: 4, vpps: p.vpps || p.name, row: rowIdx + 1,
        msg: `${origDesc} — 由 ${actor} 于 ${dateStr} 忽略`,
        _ignored: true,
      });
    });

    const partsWithVpps = targetRows.filter(p => (p.vpps || '').trim());
    const rule1Errors   = errors.filter(e => e.rule === 1);
    const rule2Errors   = errors.filter(e => e.rule === 2);
    const rule3Errors   = errors.filter(e => e.rule === 3);

    // rule-1 分组重排时保存原始行顺序，用于恢复
    let _r1FilterState = null;

    // ── 批量操作所需数据 ──────────────────────────────────────
    const noDataRows = targetRows.filter((p, idx) => {
      const gid = p.gid || `row:${idx}`;
      return (rowErrorMap.get(gid) || []).some(e => e.rule === 1 && e.brief === '无主数据');
    });

    const aliasErrItems = [];
    rowErrorMap.forEach(errs => {
      errs.forEach(e => { if (e.rule === 1 && e._aliasData) aliasErrItems.push(e._aliasData); });
    });

    const _getPbomMeta = () => {
      const targetGid = _shell?.getTargetTLS()?.getSelectedList();
      const ver = _versions.find(v => v.gid === targetGid);
      return {
        added_by: window._authUser?.name || window._authUser?.gid || '未知',
        project:  ver ? (ver.name || ver.version_tag || targetGid) : 'PBOM',
        added_at: new Date().toISOString(),
      };
    };

    const result = {
      rules: [
        { color: 'var(--danger)',  text: '规则1：主数据核对 — VPPS 须存在于主数据；填写了描述时须与主数据一致' },
        { color: 'var(--primary)', text: '规则2：父级一致性 — 本行 parent_vpps 字段须与父级零件实际 VPPS 一致' },
        { color: 'var(--warning)', text: '规则3：层级前缀核对 — VPPS 须以其父级 VPPS（去掉末尾点）作为前缀' },
        { color: 'var(--warning)', text: '规则4：紧固件主件一致性 — 几何分析识别的主件与VPPS描述中的主件须一致' },
      ],
      summary: [
        { label: '有VPPS',    count: partsWithVpps.length, type: 'same' },
        { label: '主数据异常', count: rule1Errors.length,  type: rule1Errors.length ? 'del' : 'add', rule: 1 },
        { label: '父级不一致', count: rule2Errors.length,  type: rule2Errors.length ? 'del' : 'add', rule: 2 },
        { label: '层级异常',   count: rule3Errors.length,  type: rule3Errors.length ? 'del' : 'add', rule: 3 },
        { label: '主件不一致', count: rule4NokRowMap.size, type: rule4NokRowMap.size ? 'del' : 'add', rule: 4 },
        { label: '别名通过',   count: aliasMatches.length, type: aliasMatches.length ? 'mod' : 'same' },
      ],
      errorGroups: [
        { title: `规则1：主数据核对 (${rule1Errors.length})`,
          items: rule1Errors.map(e => ({ vpps: e.vpps, row: e.row, msg: e.msg, badge: '主数据', onAction: e.onAction, actionLabel: e.actionLabel })) },
        { title: `规则2：父级一致性 (${rule2Errors.length})`,
          items: rule2Errors.map(e => ({ vpps: e.vpps, row: e.row, msg: e.msg, badge: '父级' })) },
        { title: `规则3：层级前缀核对 (${rule3Errors.length})`,
          items: rule3Errors.map(e => ({ vpps: e.vpps, row: e.row, msg: e.msg, badge: '层级' })) },
        { title: `规则4：紧固件主件一致性`,
          items: [...rule4NokRowMap.values()].map(entry => ({
            vpps: entry.vpps, row: entry.row, msg: entry.msgs.join('；'), badge: '主件',
          })) },
        ...(rule4Errors.some(e => e._ignored) ? [{
          title: `规则4：已忽略条目`,
          items: rule4Errors.filter(e => e._ignored).map(e => ({ vpps: e.vpps, row: e.row, msg: e.msg, badge: '已忽略' })),
        }] : []),
        ...(aliasMatches.length ? [{
          title: `别名通过 (${aliasMatches.length}) — 描述与主数据不同但已被接受为合法别名`,
          items: aliasMatches.map(m => ({ vpps: m.vpps, row: m.row, msg: `别名: "${m.desc}"`, badge: '别名' })),
        }] : []),
      ],
      ok: errors.length === 0 && rule4NokRowMap.size === 0,
      rowErrorMap,
      getPendingCount: () => _vppsPendingActions.length,
      onPendingBtnRender: (fn) => { _vppsOnPendingChange = fn; },
      submitPendingActions: async () => {
        const toRun = [..._vppsPendingActions];
        _vppsPendingActions = [];
        _vppsOnPendingChange?.(0);
        let failed = 0;
        for (const a of toRun) {
          try { await a.fn(); }
          catch (e) { failed++; console.error('[vpps] action failed:', a.desc, e); }
        }
        if (failed) alert(`${failed} 条操作执行失败，请查看控制台`);
        const activeIdx = _shell?._activeCheckIdx ?? -1;
        if (activeIdx >= 0) await _shell.rerunCheck(activeIdx);
      },
      rerunCheck: async () => {
        const activeIdx = _shell?._activeCheckIdx ?? -1;
        if (activeIdx >= 0) await _shell.rerunCheck(activeIdx);
      },
      batchAddNoData: noDataRows.length ? {
        count: noDataRows.length,
        existingCount: partsWithVpps.length - noDataRows.length,
        run: async () => {
          const meta    = _getPbomMeta();
          const entries = noDataRows.map(p => ({
            vpps:             (p.vpps      || '').trim(),
            vpps_desc_cn:     (p.vpps_desc || '').trim(),
            vpps_description: (p.vpps_desc || '').trim(),
          }));
          const res = await _cf('/api/craft_lib/part_names/batch_add_from_pbom', {
            method: 'POST', body: JSON.stringify({ entries, meta }),
          });
          if (!res?.success) throw new Error(res?.detail || '批量添加失败');
          return res;
        },
      } : null,
      batchAcceptAliases: aliasErrItems.length ? {
        count: aliasErrItems.length,
        acceptedCount: aliasMatches.length,
        run: async () => {
          const meta  = _getPbomMeta();
          const items = aliasErrItems.map(d => ({
            vpps_part_gid: d.vppsPartGid,
            alias:         d.alias,
            pbom_part_gid: d.pbomPartGid,
          }));
          const res = await _cf('/api/craft_lib/part_names/batch_accept_alias', {
            method: 'POST', body: JSON.stringify({ items, meta }),
          });
          if (!res?.success) throw new Error(res?.detail || '批量别名提交失败');
          return res;
        },
      } : null,
      ignoreRule4: (rule4NokRowMap.size || _vppsIgnoredRowGids.size) ? {
        count:        rule4NokRowMap.size,
        ignoredCount: _vppsIgnoredRowGids.size,
        ignoredItems: _vppsIgnoredOps.map(op => ({
          desc:      op.original_value || '（无描述）',
          actorName: op.actor_name || '',
          createdAt: op.created_at ? op.created_at.substring(0, 10) : '',
          opGid:     op.gid,
        })),
        run: async () => {
          const actor_gid  = window._authUser?.gid  || '';
          const actor_name = window._authUser?.name || '';
          const rows = [...rule4NokRowMap.values()].map(r => ({
            pbom_row_gid:       r.gid,
            original_vpps_desc: r.vpps_desc,
          }));
          const res = await _cf('/api/vpps-operations/rule4-bulk-ignore', {
            method: 'POST',
            body: JSON.stringify({ pbom_version_gid: _pbomVersionGid, rows, actor_gid, actor_name }),
          });
          if (!res?.success) throw new Error(res?.detail || '忽略操作失败');
          const activeIdx = _shell?._activeCheckIdx ?? -1;
          if (activeIdx >= 0) await _shell.rerunCheck(activeIdx);
        },
        revertAll: async () => {
          const ops  = [..._vppsIgnoredOps];
          const user = window._authUser || {};
          let failed = 0;
          for (const op of ops) {
            try {
              const res = await _cf(`/api/vpps-operations/${op.gid}/revert`, {
                method: 'POST',
                body: JSON.stringify({ reverted_by_gid: user.gid || '', reverted_by_name: user.name || '' }),
              });
              if (!res?.success) failed++;
            } catch (_) { failed++; }
          }
          // 不手动清缓存 — 直接 rerunCheck 从 API 拿最新状态，确保本地与服务端一致
          const activeIdx = _shell?._activeCheckIdx ?? -1;
          if (activeIdx >= 0) await _shell.rerunCheck(activeIdx);
          if (failed) alert(`${failed} 条撤销失败，已重新核对，请检查结果`);
        },
      } : null,
      onFilterByRule(rule) {
        const bodyEl = _shell?.getTargetTLS()?._colBodyEl
                    || _shell?.getTargetTLS()?._mountEl?.querySelector('.col-body');
        const tbl = bodyEl?.querySelector('.vct-table');
        if (!tbl) return;
        const tbody = tbl.querySelector('tbody');
        if (!tbody) return;

        // ── 1. 清除上次 rule-1 分组状态 ────────────────────────────
        tbody.querySelectorAll('.vct-subgroup-hdr-row').forEach(r => r.remove());
        if (_r1FilterState) {
          // 恢复原始行顺序（appendChild 将已有子节点移至末尾）
          _r1FilterState.forEach(tr => tbody.appendChild(tr));
          _r1FilterState = null;
        }

        const allDataRows = Array.from(tbody.querySelectorAll('tr[data-row-gid]'));
        const groupRows   = Array.from(tbody.querySelectorAll('.vct-group-l1, .vct-group-l2'));

        // ── 2. 无筛选：全部显示 ─────────────────────────────────────
        if (rule == null) {
          allDataRows.forEach(tr => (tr.style.display = ''));
          groupRows.forEach(tr => (tr.style.display = ''));
          return;
        }

        // ── 3. 收集匹配 gid ─────────────────────────────────────────
        const matchGids = new Set();
        rowErrorMap.forEach((errs, gid) => {
          if (errs.some(e => e.rule === rule)) matchGids.add(gid);
        });
        groupRows.forEach(r => (r.style.display = 'none'));
        allDataRows.forEach(tr => {
          tr.style.display = matchGids.has(tr.dataset.rowGid) ? '' : 'none';
        });

        // ── 4. rule 1 专属：无主数据 / 描述不一致 分组重排 ───────────
        if (rule === 1) {
          const noDataGids  = new Set();
          const descErrGids = new Set();
          rowErrorMap.forEach((errs, gid) => {
            if (!matchGids.has(gid)) return;
            errs.filter(e => e.rule === 1).forEach(e => {
              if (e.brief === '无主数据') noDataGids.add(gid);
              else                        descErrGids.add(gid);
            });
          });

          const noDataRows = allDataRows.filter(tr => noDataGids.has(tr.dataset.rowGid));
          const descRows   = allDataRows.filter(tr => descErrGids.has(tr.dataset.rowGid));

          const _makeSubHdr = (label, count) => {
            const tr = document.createElement('tr');
            tr.className = 'vct-subgroup-hdr-row';
            const td = document.createElement('td');
            td.colSpan = TOTAL_SPAN;
            td.className = 'vct-subgroup-hdr';
            td.innerHTML = `${label}&ensp;<span class="vct-group-nok-ct">${count}&thinsp;项</span>`;
            tr.appendChild(td);
            return tr;
          };

          // 保存当前行顺序（用于恢复），再重排
          _r1FilterState = Array.from(tbody.rows);
          const frag = document.createDocumentFragment();
          if (noDataRows.length) {
            frag.appendChild(_makeSubHdr('无主数据', noDataGids.size));
            noDataRows.forEach(r => frag.appendChild(r));
          }
          if (descRows.length) {
            frag.appendChild(_makeSubHdr('主数据描述不一致', descErrGids.size));
            descRows.forEach(r => frag.appendChild(r));
          }
          tbody.appendChild(frag);
        }
      },
    };
    // 用 refMap 回填 ref_main_vpps_desc / ref_main_vpps
    const enrichedRows = targetRows.map((p, idx) => {
      const gid     = p.gid || `row:${idx}`;
      let patch = {};

      // 先尝试从当前行的 vpps 字段直接查 vpps_parts 记录
      const selfVpps = (p.vpps || '').trim();
      const selfRef  = selfVpps ? refMap.get(selfVpps) : null;

      // ref_main_vpps：优先行自带，否则从 vpps_parts 记录补
      const refVpps = (p.ref_main_vpps || '').trim()
                   || (selfRef ? (selfRef.ref_main_vpps || '').trim() : '');
      if (refVpps && !p.ref_main_vpps) patch.ref_main_vpps = refVpps;

      // ref_main_vpps_desc：优先行自带，否则先从 vpps_parts 记录取，再用 refVpps 二次查描述
      if (!p.ref_main_vpps_desc) {
        const descFromSelf = selfRef ? (selfRef.ref_main_vpps_desc || '').trim() : '';
        if (descFromSelf) {
          patch.ref_main_vpps_desc = descFromSelf;
        } else if (refVpps) {
          const refPart = refMap.get(refVpps);
          if (refPart) patch.ref_main_vpps_desc = refPart.vpps_desc_cn || refPart.vpps_description || '';
        }
      }

      // r4 几何接触件列表（A第一位绿、B第二位紫）
      if (r4ContactMap.has(gid)) patch.geo_contact_parts = r4ContactMap.get(gid);

      return Object.keys(patch).length ? { ...p, ...patch } : p;
    });
    _renderVppsCheckTable(result, enrichedRows);

    // ── 自动将核对结果写回 pbom_versions.meta.vpps_check ──────
    if (_pbomVersionGid) {
      const nokCount = (rule1Errors.length + rule2Errors.length + rule3Errors.length)
        + (result.rule4Nok?.items?.length || 0);
      _cf(`/api/ebom/snapshots/${_pbomVersionGid}/vpps-stats`, {
        method: 'PATCH',
        body: JSON.stringify({
          nok:     nokCount,
          ignored: _vppsIgnoredRowGids.size,
          total:   targetRows.length,
        }),
      }).catch(() => {});   // fire-and-forget，不阻塞 UI
    }

    return result;
  },
};

/* ── 紧固件分组工具栏按钮 ────────────────────────────────── */
function _buildTargetExtraBtns() {
  return [
    {
      html: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M12 2v4m0 12v4m-7.07-3.93l2.83-2.83m8.48-8.48l2.83-2.83M2 12h4m12 0h4m-3.93 7.07l-2.83-2.83M6.76 6.76L3.93 3.93"/></svg><span class="feat-label">紧固件分组</span>',
      title: '紧固件分组（按几何主件实例）',
      active: _fastenerGroupActive,
      onClick: _toggleFastenerGroup,
    },
    {
      html: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg><span class="feat-label">增值工时</span>',
      title: '增值工时',
      onClick: () => alert('增值工时：功能待实现'),
    },
  ];
}

function _toggleFastenerGroup() {
  const tls = _shell?.getTargetTLS();
  if (!tls) return;
  _fastenerGroupActive = !_fastenerGroupActive;
  tls._fieldConfig.groupMode  = _fastenerGroupActive ? 'group' : 'parent';
  tls._fieldConfig.groupField = _fastenerGroupActive ? 'geo_main_part' : (tls._optsGroupField || 'component_type');
  tls._collapseState?.clear();
  tls.vm?.setGroup(_fastenerGroupActive ? 'geo_main_part' : null);
  tls._saveFieldConfig?.();
  tls._renderTree?.();
  tls.updateExtraButtons(_buildTargetExtraBtns());
}

/* ── 零件编辑 modal ──────────────────────────────────────── */
let _editingPartGid = null;

async function confirmPartModal() {
  const part_no    = document.getElementById('inp-part-no').value.trim();
  const name       = document.getElementById('inp-part-name').value.trim();
  const quantity   = parseFloat(document.getElementById('inp-part-qty').value) || 1;
  const unit       = document.getElementById('inp-part-unit').value.trim() || 'pcs';
  const material   = document.getElementById('inp-part-material').value.trim() || null;
  const parent_gid = document.getElementById('inp-part-parent').value.trim() || null;
  const temp_vpps  = document.getElementById('inp-part-temp-vpps').value.trim() || null;
  const remark     = document.getElementById('inp-part-remark').value.trim() || null;
  if (!part_no || !name) { alert('零件号和名称不能为空'); return; }

  const targetTLS = _shell?.getTargetTLS();
  const targetGid = targetTLS ? targetTLS.getSelectedList() : null;
  let res;
  if (_editingPartGid) {
    res = await _cf(`/api/ebom/parts/${_editingPartGid}`, {
      method: 'PATCH',
      body: JSON.stringify({ part_no, name, quantity, unit, material, temp_vpps, remark }),
    });
  } else {
    if (!targetGid) return;
    res = await _cf(`/api/ebom/snapshots/${targetGid}/parts`, {
      method: 'POST',
      body: JSON.stringify({ part_no, name, quantity, unit, material, parent_gid, temp_vpps, remark }),
    });
  }
  if (res?.success) {
    document.getElementById('modal-part').classList.add('hidden');
    if (targetTLS) await targetTLS.refresh();
  } else {
    alert('保存失败');
  }
}

/* ── 初始化 ───────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', async () => {
  // 主题
  try {
    const theme = window.parent?.document?.documentElement?.getAttribute('data-theme') || 'dark';
    document.documentElement.setAttribute('data-theme', theme);
  } catch (_) {}
  window.addEventListener('message', e => {
    if (e.data?.type === 'theme') document.documentElement.setAttribute('data-theme', e.data.theme);
    // 清单树导航：选中指定 PBOM 快照版本
    if (e.data?.type === 'ls:nav' && e.data?.gid) {
      _shell?.getTargetTLS()?.setSelectedList?.(e.data.gid);
    }
  });

  // 项目筛选
  document.getElementById('sel-project').addEventListener('change', loadVersions);

  // ── 新建空白版本 modal ──────────────────────────────────
  const nvProjectSel = document.getElementById('nv-project');
  const nvSuffixInp  = document.getElementById('nv-suffix');
  const nvNameInp    = document.getElementById('nv-name');
  const _updateNvName = () => {
    if (nvProjectSel && nvSuffixInp && nvNameInp)
      nvNameInp.value = _autoVersionName(nvProjectSel.value, nvSuffixInp.value);
  };
  nvProjectSel?.addEventListener('change', _updateNvName);
  nvSuffixInp?.addEventListener('input', _updateNvName);

  document.getElementById('btn-new-blank')?.addEventListener('click', () => {
    nvProjectSel.innerHTML = '<option value="">（无项目）</option>';
    _projects.forEach(p => nvProjectSel.appendChild(_opt(p.gid, p.name)));
    _updateNvName();
    document.getElementById('modal-new-ver').classList.remove('hidden');
  });
  document.getElementById('btn-nv-cancel')?.addEventListener('click', () => {
    document.getElementById('modal-new-ver').classList.add('hidden');
  });
  document.getElementById('btn-nv-confirm')?.addEventListener('click', async () => {
    const name = nvNameInp?.value.trim();
    const projectGid = nvProjectSel?.value || null;
    if (!name) { alert('版本名称不能为空'); return; }
    const res = await _cf('/api/ebom/snapshots', {
      method: 'POST',
      body: JSON.stringify({ name, version_tag: name, project_gid: projectGid, source_type: 'manual' }),
    });
    if (!res?.success) { alert('创建失败'); return; }
    document.getElementById('modal-new-ver').classList.add('hidden');
    await loadVersions();
    const newGid = res.data?.gid;
    if (newGid && _shell?.getTargetTLS()) {
      await _shell.getTargetTLS().setSelectedList(newGid);
      localStorage.setItem(_lsk('pbom:targetGid'), newGid);
    }
  });

  // ── 导入 modal ─────────────────────────────────────────
  const impProjectSel   = document.getElementById('imp-project');
  const impSuffixInp    = document.getElementById('imp-suffix');
  const impVerPreview   = document.getElementById('imp-ver-preview');
  const impVerModeSel   = document.getElementById('imp-ver-mode');
  const impExistingVer  = document.getElementById('imp-existing-ver');
  const impExistingWrap = document.getElementById('imp-existing-wrap');
  const impNewWrap      = document.getElementById('imp-new-wrap');
  const impConfirmBtn   = document.getElementById('btn-imp-confirm');

  const _updateImportPreview = () => {
    if (impProjectSel && impSuffixInp && impVerPreview)
      impVerPreview.value = _autoVersionName(impProjectSel.value, impSuffixInp.value);
  };

  /** 用选中项目过滤版本，填充现有版本下拉 */
  const _refreshExistingVerList = () => {
    if (!impExistingVer) return;
    const projGid = impProjectSel?.value || '';
    const list = projGid
      ? _versions.filter(v => v.project_gid === projGid)
      : _versions;
    impExistingVer.innerHTML = list.length
      ? list.map(v => `<option value="${v.gid}">${v.name || v.version_tag || v.gid}</option>`).join('')
      : '<option value="">（暂无版本）</option>';
  };

  /** 切换新建/现有模式的显示 */
  const _syncImpMode = () => {
    const isNew = impVerModeSel?.value === 'new';
    if (impNewWrap)      impNewWrap.style.display      = isNew ? '' : 'none';
    if (impExistingWrap) impExistingWrap.style.display = isNew ? 'none' : '';
    if (impConfirmBtn)   impConfirmBtn.textContent      = isNew ? '创建版本并继续导入' : '导入到此版本';
    if (!isNew) _refreshExistingVerList();
  };

  impVerModeSel?.addEventListener('change', _syncImpMode);
  impProjectSel?.addEventListener('change', () => { _updateImportPreview(); _refreshExistingVerList(); });
  impSuffixInp?.addEventListener('input', _updateImportPreview);

  // 打开 modal 时同步一次状态
  document.getElementById('btn-import')?.addEventListener('click', () => {
    // 填充项目下拉
    const impProjSel = document.getElementById('imp-project');
    if (impProjSel) {
      impProjSel.innerHTML = '<option value="">（无项目）</option>' +
        _projects.map(p => `<option value="${p.gid}">${p.name}</option>`).join('');
    }
    _updateImportPreview();
    _syncImpMode();
    document.getElementById('modal-import').classList.remove('hidden');
  });

  document.getElementById('btn-imp-cancel')?.addEventListener('click', () => {
    document.getElementById('modal-import').classList.add('hidden');
  });

  document.getElementById('btn-imp-confirm')?.addEventListener('click', async () => {
    const isNew = impVerModeSel?.value !== 'existing';
    document.getElementById('modal-import').classList.add('hidden');

    if (isNew) {
      // 新建版本
      const projectGid = impProjectSel?.value || null;
      const verName    = impVerPreview?.value.trim();
      const sourceType = document.getElementById('imp-source')?.value || 'import';
      if (!verName) { alert('版本名称不能为空'); return; }
      const res = await _cf('/api/ebom/snapshots', {
        method: 'POST',
        body: JSON.stringify({ name: verName, version_tag: verName, project_gid: projectGid, source_type: sourceType }),
      });
      if (!res?.success) { alert('创建版本失败'); return; }
      const newGid = res.data?.gid;
      await loadVersions();
      if (newGid && _shell?.getTargetTLS()) await _shell.getTargetTLS().setSelectedList(newGid);
      localStorage.setItem(_lsk('pbom:targetGid'), newGid);
    } else {
      // 导入到现有版本
      const existGid = impExistingVer?.value;
      if (!existGid) { alert('请选择一个现有版本'); return; }
      if (_shell?.getTargetTLS()) await _shell.getTargetTLS().setSelectedList(existGid);
      localStorage.setItem(_lsk('pbom:targetGid'), existGid);
    }

    _ieMgr.showImport();
  });

  // ── ListDiffShell 初始化 ────────────────────────────────
  _shell = new ListDiffShell({
    mountEl: document.getElementById('diff-shell-root'),
    moduleId: 'pbom',

    baseTlsOpts: {
      title: 'Base PBOM',
      itemTypes: [{ value: 'pbom', label: 'PBOM' }],
      forcedItemType: 'pbom',
      onLoadLists: _loadPbomLists,
      onLoadData:  _loadPbomParts,
      columns:     PBOM_DEFAULT_COLS,
      allColumns:  PBOM_FULL_COLS,
      priorityKeys: ['component_id', 'name', 'component_type'],
      detailMode:  'readonly',
      detailFields: _DETAIL_KEYS,
      groupField:  'component_type',
      moduleId:    'pbom_base',
      rowActions:  _makePinEl,
    },

    targetTlsOpts: {
      title: '目标 PBOM',
      itemTypes: [{ value: 'pbom', label: 'PBOM' }],
      forcedItemType: 'pbom',
      onLoadLists: _loadPbomLists,
      onLoadData:  async (itemType, listGid) => {
        _updatePbomStatusBadge(listGid);
        return _loadPbomParts(itemType, listGid);
      },
      columns:     PBOM_DEFAULT_COLS,
      allColumns:  PBOM_FULL_COLS,
      priorityKeys: ['component_id', 'name', 'component_type'],
      detailMode:  'readonly',
      detailFields: _DETAIL_KEYS,
      groupField:  'component_type',
      moduleId:    'pbom_target',
      extraToolbarBtns: _buildTargetExtraBtns(),
      rowActions:  _makePinEl,
    },

    matchKeyFn:      _matchKey,
    cmpFields:       _CMP_FIELDS,
    fieldLabels:     _FIELD_LABELS,
    treeParentField: 'parent_bom_row',

    resultWidth:     '200px',

    // PBOM 专有 extraCheck：vpps 核对
    extraChecks: [vppsCheckDef],

    // 渲染 vpps 列时追加临时 VPPS badge
    renderVppsCell: (p) => {
      const _esc = s => { if (!s) return ''; const d = document.createElement('div'); d.textContent = s; return d.innerHTML; };
      return `${_esc(p.vpps || '')}${p.temp_vpps ? `<span class="temp-vpps-badge">临时</span>` : ''}`;
    },
  });
  await _shell.init();

  // 自我标注：「已标注」覆层按钮
  document.getElementById('btn-annotated')?.addEventListener('click', () => {
    const toolbar = document.querySelector('.toolbar');
    window.SapAnnotList?.show({
      module:    'ebom',
      title:     'PBOM · 已标注',
      offsetLeft: 0,
      offsetTop:  (toolbar?.offsetHeight ?? 48),
    });
  });

  // 自我标注：保存后更新行指示器
  window.addEventListener('sap-saved', e => {
    const pin = document.querySelector(`.sap-row-pin[data-gid="${e.detail.itemGid}"]`);
    if (pin) {
      if (e.detail.status) {
        pin.dataset.status = e.detail.status;
        pin.closest('.part-row')?.classList.add('has-sap-ann');
      } else {
        delete pin.dataset.status;
        pin.closest('.part-row')?.classList.remove('has-sap-ann');
      }
    }
  });

  // ── 导出结论按钮（由 ListDiffShell 内部已绑定，这里无需重复）──

  // ── 导入导出管理器 ─────────────────────────────────────
  _ieMgr = new ImportExportManager({
    moduleId: 'ebom',
    columns:  PBOM_FULL_COLS,
    colAliasMap: EXCEL_COL_MAP,
    getRows: () => {
      const tRows = _shell.getTargetTLS()?.getRows() || [];
      const bRows = _shell.getBaseTLS()?.getRows() || [];
      return tRows.length ? tRows : bRows;
    },
    onImport: async (rows, _fieldMap, _conflict, signal) => {
      const targetGid = _shell.getTargetTLS()?.getSelectedList();
      if (!targetGid) throw new Error('请先在目标栏选择 PBOM 版本再导入');
      const mapped   = rows.map(r => _mapExcelRow(r));
      const filtered = mapped.filter(r => r.level == null || (r.level > 0 && r.level < 4));
      const skipped  = mapped.length - filtered.length;
      if (skipped) console.log(`[PBOM] 已跳过 ${skipped} 行 (level ≥ 4)`);
      if (!filtered.length) throw new Error('没有可导入的数据行');
      const cf = window.parent?._cloudFetch || window._cloudFetch;
      if (!cf) throw new Error('_cloudFetch 未就绪');
      const BATCH = 100;
      let totalInserted = 0;
      for (let i = 0; i < filtered.length; i += BATCH) {
        if (signal?.aborted) break;
        const chunk = filtered.slice(i, i + BATCH);
        const res = await cf(`/api/ebom/snapshots/${targetGid}/parts/batch`, {
          method: 'POST',
          body: JSON.stringify(chunk),
          signal,
        });
        if (!res?.success) throw new Error(`批量导入失败(${i}~${i+chunk.length}): ${res?.detail || JSON.stringify(res)}`);
        totalInserted += res.data?.inserted || 0;
      }
      if (!signal?.aborted) {
        console.log(`[PBOM] 导入完成, inserted=${totalInserted}`);
        await _shell.getTargetTLS()?.refresh();
      }
    },
  });

  document.getElementById('btn-export')?.addEventListener('click', () => _ieMgr.showExport());

  // ── 零件编辑 modal ──────────────────────────────────────
  document.getElementById('btn-part-cancel').addEventListener('click', () => {
    document.getElementById('modal-part').classList.add('hidden');
  });
  document.getElementById('btn-part-confirm').addEventListener('click', confirmPartModal);

  // ── 加载数据 ────────────────────────────────────────────
  await loadProjects();
  await loadVersions();

  // 恢复上次选择的版本（仅在 init 自动选中的与记录不同时才触发，避免双刷新）
  {
    const savedTarget   = localStorage.getItem(_lsk('pbom:targetGid'));
    const alreadySel    = _shell?.getTargetTLS()?.getSelectedList();
    if (savedTarget && savedTarget !== alreadySel && _versions.some(v => v.gid === savedTarget)) {
      await _shell.getTargetTLS().setSelectedList(savedTarget);
    }
  }

  // ── Standalone 模式：裁剪 UI ────────────────────────────
  if (_standaloneMode) {
    document.title = 'PBOM / VPPS 核对';
    // 隐藏顶部工具栏（导入/导出按钮）
    const toolbar = document.querySelector('.toolbar');
    if (toolbar) { toolbar.style.visibility = 'hidden'; toolbar.style.height = '0'; toolbar.style.overflow = 'hidden'; }

    // 隐藏 Base PBOM 面板和紧邻的分割线
    const baseCol = document.querySelector('.lds-col-base');
    if (baseCol) {
      baseCol.style.display = 'none';
      const divider = baseCol.nextElementSibling;
      if (divider?.classList.contains('lds-divider')) divider.style.display = 'none';
    }

    // 去掉 Target 工具栏里的"对比 base"和"增值工时"按钮
    document.querySelectorAll('.feat-label').forEach(el => {
      const text = el.textContent.trim();
      if (text === '对比base' || text === '增值工时') el.closest('button')?.remove();
    });

    // 自动选中 PBOM 版本
    if (_preselectedPbomGid && _versions.some(v => v.gid === _preselectedPbomGid)) {
      await _shell.getTargetTLS()?.setSelectedList(_preselectedPbomGid);
    }

    // 自动触发导入操作（来自生命周期面板的快捷入口）
    if (_autoAction === 'import') {
      setTimeout(() => document.getElementById('btn-import')?.click(), 300);
    } else if (_autoAction === 'manual') {
      setTimeout(() => {
        const imp = document.getElementById('modal-import');
        const src = document.getElementById('imp-source');
        if (imp && src) { src.value = 'manual'; imp.classList.remove('hidden'); }
      }, 300);
    } else if (_autoAction === 'new_blank') {
      setTimeout(() => document.getElementById('btn-new-blank')?.click(), 300);
    }
  }

  // DataRegistry
  _shell.register('ebom', {
    label: 'PBOM', icon: 'icon-ebom',
    capabilities: ['import_export'],
    pageType: 'pbom_diff', configurable: true,
    getRows: () => {
      const tRows = _shell.getTargetTLS()?.getRows() || [];
      const bRows = _shell.getBaseTLS()?.getRows() || [];
      return tRows.length ? tRows : bRows;
    },
  });
});
