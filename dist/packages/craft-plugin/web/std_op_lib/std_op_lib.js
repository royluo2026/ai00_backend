/**
 * 标准工序库前端脚本 — ListShell 版
 */
'use strict';

// ── 列定义 ────────────────────────────────────────────────────────────────────
const STD_OP_COLS = [
  { key: 'display_id',    label: 'ID',          type: 'text',   width: 90,  editable: false },
  { key: 'code',          label: '工序代码',    type: 'text',   width: 120 },
  { key: 'name',          label: '工序名称',    type: 'text',   width: 220 },
  { key: 'status',        label: '状态',        type: 'enum',   width: 90,
    options: [{value:'draft',label:'草稿'},{value:'active',label:'已发布'},{value:'deprecated',label:'已废弃'}] },
  { key: 'standard_time', label: '标准工时(s)', type: 'number', width: 110 },
  { key: 'importance',    label: '重要性',      type: 'text',   width: 100 },
  { key: '_actions',      label: '操作',        type: 'text',   width: 130, alwaysVisible: true, editable: false },
];

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
    await ListShell._cfSafe(`/api/std_op/operations/${gid}/publish`, { method: 'POST' });
    await loadOps();
  } catch (e) { alert('发布失败: ' + e.message); }
}

async function deprecateOp(gid) {
  if (!confirm('确认废弃该工序？')) return;
  try {
    await ListShell._cfSafe(`/api/std_op/operations/${gid}/deprecate`, { method: 'POST' });
    await loadOps();
  } catch (e) { alert('废弃失败: ' + e.message); }
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
  cloudPath:        '/api/std_op/operations',
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
  cloudUpdatePath:  (gid) => `/api/std_op/operations/${gid}`,
  cloudCreatePath:  '/api/std_op/operations',
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
    title:             '标准工序库',
    titleIcon:         '#icon-book-open',
    newLabel:          '新建条目',
    cellRenderer:      CELL_RENDERERS,
    onListsChange:     (lists) => { _allLists = lists; },
    onSelect:          (gid)   => { _currentList = gid; loadOps(); },
    initListGid:       null,
    rdpSaveOpts:       { cloudPath: '/api/std_op/operations' },  // cloud-only module
    rowClass:          (row)   => row._source === 'cloud' ? 'ge-row-cloud' : '',
    extraContextItems: EXTRA_CTX,
    onContextAction:   (action, row) => {
      if (action === 'open_detail') _openContainerCard(row);
    },
    importExport: ListShell.makeImportExport('std_op_lib', _getViewRows, async (rows, _fm, _c, signal) => {
        for (const r of rows) {
          if (signal?.aborted) break;
          if (!r.name && !r.code) continue;
          await ListShell._cfSafe('/api/std_op/operations', {
            method: 'POST',
            body: JSON.stringify({ code: r.code || '', name: r.name || r.code || '', standard_time: parseFloat(r.standard_time) || 0 }),
            signal,
          }).catch(e => console.error('[import std_op]', e));
        }
        if (!signal?.aborted) await loadOps();
      }),
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
