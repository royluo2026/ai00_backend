/**
 * 标准工序库前端脚本 — ListShell 版
 */
'use strict';



function _safe(request) {
  return request.catch(e => { console.warn('[ListShell._cfSafe]', e.message); return null; });
}

// ── 列定义 ────────────────────────────────────────────────────────────────────
const STD_OP_COLS = [
  { key: 'display_id',    label: 'ID',          type: 'text',   width: 90,  editable: false },
  { key: 'code',          label: '工序代码',    type: 'text',   width: 120 },
  { key: 'name',          label: '工序名称',    type: 'text',   width: 220 },
  { key: 'status',        label: '状态',        type: 'enum',   width: 90,
    options: [{value:'draft',label:'草稿'},{value:'active',label:'已发布'},{value:'deprecated',label:'已废弃'}] },
  { key: 'standard_time', label: '标准工时(s)', type: 'number', width: 110 },
  { key: 'importance',    label: '重要性',      type: 'text',   width: 100 },
  { key: 'description',   label: '描述',        type: 'text',   width: 180, visible: false },
  { key: 'component_type', label: '零组件类型', type: 'text',   width: 120 },
  { key: 'bom_row',        label: 'BOM 行',      type: 'text',   width: 100, visible: false },
  { key: 'parent_bom_row', label: '父级',        type: 'text',   width: 100, visible: false },
  { key: 'level',         label: 'Level',       type: 'text',   width: 80,  visible: false },
  { key: 'ai00_level',    label: 'AI00 Level',  type: 'number', width: 90,  visible: false },
  { key: 'vpps_attr',     label: 'VPPS属性',    type: 'text',   width: 100, visible: false },
  { key: 'vpps',          label: 'VPPS',        type: 'text',   width: 120, visible: false },
  { key: 'vpps_desc',     label: 'VPPS描述',    type: 'text',   width: 180, visible: false },
  { key: 'torque_importance', label: '扭矩重要度', type: 'text', width: 100, visible: false },
  { key: 'vehicle_model', label: '车型',        type: 'text',   width: 100, visible: false },
  { key: 'parent_vpps',   label: '父级VPPS',    type: 'text',   width: 120, visible: false },
  { key: 'process_vpps',  label: '工序VPPS',    type: 'text',   width: 120, visible: false },
  { key: 'operation_vpps', label: '操作VPPS',   type: 'text',   width: 120, visible: false },
  { key: 'vpps_part',     label: '零件VPPS',    type: 'text',   width: 120, visible: false },
  { key: 'match_tag',     label: '标记',        type: 'text',   width: 90,  visible: false },
  { key: 'part_feed',     label: '零件投料',    type: 'boolean', width: 90, visible: false },
  { key: '_actions',      label: '操作',        type: 'text',   width: 130, alwaysVisible: true, editable: false },
];

const STD_OP_COL_ALIASES = {
  '工序编码': 'code', '工序编号': 'code',
  '名称': 'name', '零组件名称': 'name',
  '零组件类型': 'component_type',
  'BOM 行': 'bom_row', 'BOM行': 'bom_row',
  '父级': 'parent_bom_row',
  '标准工时': 'standard_time', '标准时间': 'standard_time',
  '重要度': 'importance',
  '说明': 'description', '零组件描述': 'description',
  'Level': 'level', '层级': 'level',
  'ai00_level': 'ai00_level', 'AI00Level': 'ai00_level', 'AI00 Level': 'ai00_level',
  'VPPS': 'vpps', 'VPPS属性': 'vpps_attr',
  'VPPS描述': 'vpps_desc',
  '扭矩重要度': 'torque_importance',
  '车型': 'vehicle_model',
  '父级VPPS': 'parent_vpps',
  '工序VPPS': 'process_vpps',
  '操作VPPS': 'operation_vpps',
  '零件VPPS': 'vpps_part',
  '标记': 'match_tag',
};

function _buildImportBody(row) {
  const body = {
    code: row.code || row.operation_vpps || row.process_vpps || row.vpps || '',
    name: row.name || row.code || row.operation_vpps || row.process_vpps || row.vpps || '',
    standard_time: parseFloat(row.standard_time) || 0,
  };
  if (row.ai00_level !== undefined && row.ai00_level !== null && row.ai00_level !== '') {
    const ai00Level = Number(row.ai00_level);
    if (Number.isFinite(ai00Level)) body.ai00_level = ai00Level;
  }
  for (const key of [
    'importance', 'description', 'level', 'vpps_attr', 'vpps', 'vpps_desc',
    'torque_importance', 'vehicle_model', 'parent_vpps', 'component_type', 'bom_row',
    'parent_bom_row', 'process_vpps', 'operation_vpps', 'vpps_part', 'match_tag',
  ]) {
    if (row[key] !== undefined && row[key] !== null && row[key] !== '') body[key] = row[key];
  }
  if (body.match_tag) body.part_feed = String(body.match_tag).trim().toLowerCase() === 'part_feed';
  return body;
}

// ── 状态 ──────────────────────────────────────────────────────────────────────
let _ops         = [];
let _shell       = null;
let _allLists    = [];
let _currentList = null;

// ── 容器卡片 ──────────────────────────────────────────────────────────────────
function _openContainerCard(row) {
  const p = window.parent || window;
  p.TabManager?.open?.('container_card', {
    mode: 'row_detail', item_type: 'std_op', gid: row.gid, source: 'cloud',
  });
}

// ── 操作函数（inline onclick 需要全局暴露）────────────────────────────────────
async function publishOp(gid) {
  try {
    await _safe((async (body,path,query) => { const result = await window.AI00Business.invoke("craft.standard_operation.change.apply", {version:1,payload:Object.fromEntries(Object.entries({operation:"publish",gid:path.gid}).filter(([,v])=>v!=null))}); return result; })({},{"gid":decodeURIComponent(String(gid))},new URLSearchParams()));
    await loadOps();
  } catch (e) { (await window.AI00Dialogs.alert('发布失败: ' + e.message)); }
}

async function deprecateOp(gid) {
  if (!(await window.AI00Dialogs.confirm('确认废弃该工序？'))) return;
  try {
    await _safe((async (body,path,query) => { const result = await window.AI00Business.invoke("craft.standard_operation.change.apply", {version:1,payload:Object.fromEntries(Object.entries({operation:"deprecate",gid:path.gid}).filter(([,v])=>v!=null))}); return result; })({},{"gid":decodeURIComponent(String(gid))},new URLSearchParams()));
    await loadOps();
  } catch (e) { (await window.AI00Dialogs.alert('废弃失败: ' + e.message)); }
}

// ── 单元格渲染 ────────────────────────────────────────────────────────────────
const CELL_RENDERERS = {
  status: (val) => {
    const MAP = { draft: '草稿', active: '已发布', deprecated: '已废弃' };
    const CLS = { draft: 'badge-draft', active: 'badge-active', deprecated: 'badge-deprecated' };
    return `<span class="badge ${CLS[val] || ''}">${MAP[val] || val || '-'}</span>`;
  },
  _actions: (val, row) => {
    if (!row.gid) return '';
    const btns = [];
    if (row.status === 'draft')   btns.push(`<button class="btn-ghost btn-sm" onclick="publishOp('${row.gid}')">发布</button>`);
    if (row.status === 'active')  btns.push(`<button class="btn-danger btn-sm" onclick="deprecateOp('${row.gid}')">废弃</button>`);
    return `<div style="display:flex;gap:4px">${btns.join('')}</div>`;
  },
};

// ── 上下文菜单 ────────────────────────────────────────────────────────────────
const EXTRA_CTX = (row) => [
  { label: '在新标签中打开详情', action: 'open_detail' },
];

// ── 加载数据 ──────────────────────────────────────────────────────────────────
const loadOps = ListShell.buildLoadHandler({
  bridgeNs:         null,                       // cloud-only
  cloudRequest:     (query) => _safe((async (body,path,query) => { const result = await window.AI00Business.invoke("craft.standard_operation.read", {version:1,payload:Object.fromEntries(Object.entries({operation:"list",status:(query.has("status")?query.get("status"):null)}).filter(([,v])=>v!=null))}); return result; })({},{},new URLSearchParams((`/api/std_op/operations?${query}`).split("?")[1]||""))),
  getCurrentList:   () => _currentList,
  getAllLists:       () => _allLists,
  getShell:         () => _shell,
  setData:          (rows) => { _ops = rows; },
});

// ── 视图行（视图过滤/排序后的数据，供 IE/Diff 使用）────────────────────────
const _getViewRows = () => (_shell && _shell.vm ? _shell.vm.applyView(_ops) : _ops).filter(r => !r._isGroupHeader);

// ── 行变更处理 ────────────────────────────────────────────────────────────────
const _onRowsChange = ListShell.buildRowsChangeHandler({
  editableKeys:     ['code', 'name', 'standard_time', 'importance'],
  primaryKey:       'code',
  cloudUpdate:      (gid, body) => (async (body,path,query) => { const result = await window.AI00Business.invoke("craft.standard_operation.change.apply", {version:1,payload:Object.fromEntries(Object.entries({operation:"update",gid:path.gid,record:Object.fromEntries(Object.entries({...{"name":null,"standard_time":null,"importance":null,"description":null,"level":null,"ai00_level":null,"vpps_attr":null,"vpps":null,"vpps_desc":null,"torque_importance":null,"vehicle_model":null,"parent_vpps":null,"component_type":null,"bom_row":null,"parent_bom_row":null,"process_vpps":null,"operation_vpps":null,"vpps_part":null,"match_tag":null,"part_feed":null,"steps":null,"required_tools":null,"parameters":null},...body}).filter(([,v])=>v!=null))}).filter(([,v])=>v!=null))}); return result; })(body,{"gid":decodeURIComponent(String(gid))},new URLSearchParams()),
  cloudCreate:      (body) => (async (body,path,query) => { const result = await window.AI00Business.invoke("craft.standard_operation.change.apply", {version:1,payload:Object.fromEntries(Object.entries({operation:"create",record:Object.fromEntries(Object.entries({...{"standard_time":0,"importance":null,"description":"","level":"","ai00_level":null,"vpps_attr":"","vpps":null,"vpps_desc":"","torque_importance":"","vehicle_model":"","parent_vpps":"","component_type":"","bom_row":"","parent_bom_row":"","process_vpps":"","operation_vpps":"","vpps_part":"","match_tag":"","part_feed":false,"steps":[],"required_tools":[],"parameters":{}},...body}).filter(([,v])=>v!=null))}).filter(([,v])=>v!=null))}); return result; })(body,{},new URLSearchParams()),
  bridgeNs:         null,           // cloud-only
  buildCreateBody:  (row) => ({
    code: row.code, name: row.name || row.code,
    standard_time: parseFloat(row.standard_time) || 0,
  }),
  getData:          () => _ops,
  getCurrentList:   () => _currentList,
  getAllLists:       () => _allLists,
  getShell:         () => _shell,
  load:             () => loadOps(),
});

// ── 初始化 ────────────────────────────────────────────────────────────────────
async function init() {
  _shell = new ListShell({
    mountEl:           document.getElementById('appRoot'),
    itemType:          'std_op',
    moduleId:          'std_op_lib',
    columns:           STD_OP_COLS,
    title:             '标准工序库 (GBOP)',
    titleIcon:         '#icon-book-open',
    newLabel:          '新建条目',
    cellRenderer:      CELL_RENDERERS,
    onListsChange:     (lists) => { _allLists = lists; },
    onSelect:          (gid)   => { _currentList = gid; loadOps(); },
    initListGid:       null,
    rdpSaveOpts:       { savePatch: (row, patch) => (async (body,path,query) => { const result = await window.AI00Business.invoke("craft.standard_operation.change.apply", {version:1,payload:Object.fromEntries(Object.entries({operation:"update",gid:path.gid,record:Object.fromEntries(Object.entries({...{"name":null,"standard_time":null,"importance":null,"description":null,"level":null,"ai00_level":null,"vpps_attr":null,"vpps":null,"vpps_desc":null,"torque_importance":null,"vehicle_model":null,"parent_vpps":null,"component_type":null,"bom_row":null,"parent_bom_row":null,"process_vpps":null,"operation_vpps":null,"vpps_part":null,"match_tag":null,"part_feed":null,"steps":null,"required_tools":null,"parameters":null},...body}).filter(([,v])=>v!=null))}).filter(([,v])=>v!=null))}); return result; })(patch,{"gid":decodeURIComponent(String(row.gid))},new URLSearchParams()) },
    rowClass:          (row)   => row._source === 'cloud' ? 'ge-row-cloud' : '',
    extraContextItems: EXTRA_CTX,
    onContextAction:   (action, row) => {
      if (action === 'open_detail') _openContainerCard(row);
    },
    importExport: ListShell.makeImportExport('std_op_lib', _getViewRows, async (rows, _fm, _c, signal) => {
        for (const r of rows) {
          if (signal?.aborted) break;
          if (!r.name && !r.code) continue;
          await _safe((async (body,path,query) => { const result = await window.AI00Business.invoke("craft.standard_operation.change.apply", {version:1,payload:Object.fromEntries(Object.entries({operation:"create",record:Object.fromEntries(Object.entries({...{"standard_time":0,"importance":null,"description":"","level":"","ai00_level":null,"vpps_attr":"","vpps":null,"vpps_desc":"","torque_importance":"","vehicle_model":"","parent_vpps":"","component_type":"","bom_row":"","parent_bom_row":"","process_vpps":"","operation_vpps":"","vpps_part":"","match_tag":"","part_feed":false,"steps":[],"required_tools":[],"parameters":{}},...body}).filter(([,v])=>v!=null))}).filter(([,v])=>v!=null))}); return result; })(_buildImportBody(r),{},new URLSearchParams()));
        }
        if (!signal?.aborted) await loadOps();
      }, STD_OP_COL_ALIASES),
    diffManager: ListShell.makeDiffManager('std_op_lib', _getViewRows, 'code'),
    onRowsChange: _onRowsChange,
  });
  await _shell.init();

  // 主题同步由 list_shell.js 的 _lsInitTheme() IIFE 统一处理

  await loadOps();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
