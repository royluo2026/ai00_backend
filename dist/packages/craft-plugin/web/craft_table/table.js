'use strict';

// ─── 列定义（ViewManager 使用）────────────────────────────────
const CRAFT_COLS = [
  { key: 'clone_status',     label: '来源',        type: 'text',    width: 60,  editable: false },
  { key: 'workstation_name', label: '工位',        type: 'text',    width: 100 },
  { key: 'post_name',        label: '岗位',        type: 'text',    width: 100 },
  // V1 /api/bop/operations 写入接口已明确 410，当前表格只允许读取。
  // 待新版 BOP 条目编辑契约覆盖这些字段后，再恢复 editable。
  { key: 'code',             label: '工序编号',    type: 'text',    width: 110, editable: false },
  { key: 'name',             label: '工序名称',    type: 'text',    width: 200, editable: false },
  { key: 'standard_time',    label: '标准工时(s)', type: 'number',  width: 110, editable: false },
  { key: 'importance',       label: '重要度',      type: 'enum',    width: 90,  editable: false, options: [{value:'high',label:'高'},{value:'medium',label:'中'},{value:'low',label:'低'}] },
  { key: 'is_nudd',          label: 'NUDD',        type: 'boolean', width: 70  },
  { key: 'part_bindings',    label: '绑定零件',    type: 'array',   width: 180, editable: false },
  { key: 'tool_requirements',label: '工具要求',    type: 'array',   width: 150, editable: false },
];

// 跳过不作为动态列展示的内部字段
const CRAFT_SKIP_KEYS = new Set([
  'section_gid', 'workstation_gid', 'workstation_code', 'post_gid', 'post_code',
  'std_op_gid', 'clone_source_version', 'drift_fields',
  'created_at', 'updated_at',
]);

// ─── 单元格渲染器（key → HTML string for <td>）──────────────
const CELL = {
  workstation_name: r => `<td>${esc(r.workstation_name || r.workstation_code)}</td>`,
  post_name:        r => `<td>${esc(r.post_name || r.post_code)}</td>`,
  code:             r => `<td class="editable" data-field="code">${esc(r.code)}</td>`,
  name:             r => `<td class="editable" data-field="name">${esc(r.name)}</td>`,
  standard_time:    r => `<td class="editable" data-field="standard_time">${r.standard_time ?? 0}</td>`,
  importance:       r => `<td class="editable ${r.importance === 'critical' ? 'importance-critical' : 'importance-normal'}" data-field="importance">${esc(r.importance)}</td>`,
  is_nudd:          r => `<td>${r.is_nudd ? '<span class="nudd-badge">NUDD</span>' : ''}</td>`,
  part_bindings: r => {
    const chips  = (r.part_bindings || []).map(pb =>
      `<span class="part-chip" title="${esc(pb.ebom_part_no)} v${esc(pb.ebom_part_version)}">${esc(pb.ebom_part_no)}</span>`
    ).join('');
    const btn = `<button class="bind-btn" data-op="${r.gid}" data-sec="${r.section_gid}" data-ws="${r.workstation_gid}" data-post="${r.post_gid}">+ 绑定</button>`;
    return `<td class="parts-cell">${chips}${btn}</td>`;
  },
  tool_requirements: r => {
    const tags = (r.tool_requirements || []).map(t =>
      `<span class="tool-tag">${esc(t.tool_template_gid || '工具')}</span>`
    ).join('');
    return `<td>${tags}</td>`;
  },
};

// ─── 状态 ──────────────────────────────────────────────────
const state = {
  workPlanGid: null,
  sectionGid: null,
  tableRows: [],
  currentOpGid: null,
  currentSectionGid: null,
  currentWsGid: null,
  currentPostGid: null,
  snapshotGid: null,
};

// ViewManager instance（init() 后就绪）
let vm = null;
let _ieMgr = null; // ImportExportManager
let _diffMgr = null; // DiffManager
let _grid = null; // GridEditor

// ─── 云端 API 封装 ─────────────────────────────────────────────
async function callBridge(namespace, method, params = {}) {
  try {
    const _cloudFetch = window.parent?._cloudFetch || window._cloudFetch;
    if (!_cloudFetch) {
      console.warn('[table.js] _cloudFetch 未就绪，返回空数据');
      return namespace === 'craft_plan' && method === 'list_work_plans' ? [] : null;
    }
    if (namespace === 'craft_plan') {
      console.warn(`[table.js] V1 craft_plan 已停用: ${method}`);
      return method.startsWith('list_') || method === 'get_table_view' ? [] : null;
    }
    if (namespace === 'std_op') {
      if (method === 'list') {
        const res = await _cloudFetch('/api/std_op/operations?status=active', { method: 'GET' });
        return res?.data || [];
      }
      if (method === 'clone_to_post') {
        console.warn('[table.js] 标准工序克隆到岗位接口已停用');
        return null;
      }
    }
    if (namespace === 'bop') {
      if (method === 'drift_check') {
        return { deprecated: true, message: 'V1 operations drift-check 已废弃，请使用新版 BOP 条目差异能力' };
      }
      if (method === 'reset_fields') {
        return { deprecated: true, message: 'V1 operations reset-fields 已废弃，请使用新版 BOP 条目变更能力' };
      }
    }
    console.warn(`[table.js] 未映射的 bridge 调用: ${namespace}.${method}`);
    return null;
  } catch (e) {
    console.error('[table.js] API 调用失败:', e.message);
    return null;
  }
}

// ─── 主题同步 ──────────────────────────────────────────────────
window.addEventListener('message', (e) => {
  if (e.data?.type === 'theme')
    document.documentElement.setAttribute('data-theme', e.data.theme);
});

// ─── 工艺方案列表 ──────────────────────────────────────────────
async function loadWorkPlans() {
  try {
    const plans = await callBridge('craft_plan', 'list_work_plans', {});
    const sel   = document.getElementById('workPlanSelect');
    sel.innerHTML = '<option value="">— 选择工艺方案 —</option>';
    (plans || []).forEach(wp => {
      const opt   = document.createElement('option');
      opt.value   = wp.gid;
      opt.textContent = wp.name;
      sel.appendChild(opt);
    });
  } catch (e) {
    console.error('[table] loadWorkPlans 失败', e);
  }
}

async function loadSections(workPlanGid) {
  try {
    const sections = await callBridge('craft_plan', 'list_sections', { work_plan_gid: workPlanGid });
    const sel = document.getElementById('sectionSelect');
    sel.innerHTML = '<option value="">— 全部工段 —</option>';
    (sections || []).forEach(sec => {
      const opt = document.createElement('option');
      opt.value = sec.gid;
      opt.textContent = sec.name;
      sel.appendChild(opt);
    });
    sel.disabled = false;
    document.getElementById('btnNewSection').disabled = false;
    document.getElementById('btnAddWs').disabled      = false;
  } catch (e) {
    console.error('[table] loadSections 失败', e);
  }
}

// ─── 表格视图 ──────────────────────────────────────────────────
async function loadTableView(workPlanGid, sectionGid) {
  try {
    const params = { work_plan_gid: workPlanGid };
    if (sectionGid) params.section_gid = sectionGid;
    const rows = await callBridge('craft_plan', 'get_table_view', params);
    state.tableRows = rows || [];
    renderTable(state.tableRows);
  } catch (e) {
    console.error('[table] loadTableView 失败', e);
  }
}

// ─── 克隆状态徽标渲染 ──────────────────────────────────────────
function cloneStatusHtml(row) {
  if (!row.std_op_gid) return '';
  const drift = row.drift_fields || [];
  const stdUpdated = drift.includes('__std_updated');
  const fieldDrift = drift.filter(f => f !== '__std_updated').length > 0;

  if (stdUpdated) {
    return `<span class="clone-badge clone-badge--updated" title="标准工序已升级，建议同步">[S↑]</span>`;
  }
  if (fieldDrift) {
    return `<span class="clone-badge clone-badge--drift" title="字段已偏离标准">[S!]</span>`;
  }
  return `<span class="clone-badge clone-badge--clean" title="克隆自标准，无偏离">[S]</span>`;
}

// ─── 渲染表格 ──────────────────────────────────────────────────
function renderTable(rows) {
  const visCols  = vm ? vm.getVisibleColumns() : CRAFT_COLS;
  const showRows = vm ? vm.applyView(rows) : rows;
  const dataRows = showRows.filter(r => !r._isGroupHeader);
  const allCols  = geMergeCols(visCols, dataRows, CRAFT_SKIP_KEYS);

  if (!_grid) {
    const container = document.getElementById('geContainer');
    _grid = new GridEditor({
      containerEl: container,
      columns: allCols,
      rows: dataRows,
      draggableRows: false,
      readOnly: true,
      cellRenderer: {
        clone_status: (val, row) => cloneStatusHtml(row),
        importance: (val) => {
          const cls = val === 'critical' ? 'importance-critical' : 'importance-normal';
          return `<span class="${cls}">${esc(val || '-')}</span>`;
        },
        is_nudd: (val) => val ? '<span class="nudd-badge">NUDD</span>' : '',
        part_bindings: (val, row) => {
          const chips = (val || []).map(pb =>
            `<span class="part-chip" title="${esc(pb.ebom_part_no)} v${esc(pb.ebom_part_version)}">${esc(pb.ebom_part_no)}</span>`
          ).join('');
          const btn = row.gid
            ? `<button class="bind-btn" onclick="openPartDrawer('${row.gid}','${row.section_gid}','${row.workstation_gid}','${row.post_gid}')">+ 绑定</button>`
            : '';
          return `<span class="parts-cell">${chips}${btn}</span>`;
        },
        tool_requirements: (val) => {
          return (val || []).map(t =>
            `<span class="tool-tag">${esc(t.tool_template_gid || '工具')}</span>`
          ).join('');
        },
      },
      extraContextItems: (row) => {
        if (!row.std_op_gid) return [];
        return [
          { label: '查看与标准差异', icon: svgIcon('compare'), action: () => openDriftDialog(row.gid) },
        ];
      },
      onColsChange: () => {},
    });
  } else {
    const unsaved = _grid.getUnsavedRows();
    _grid.setColumns(allCols);
    _grid.setRows(unsaved.length ? [...dataRows, ...unsaved] : dataRows);
  }
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

// ─── 零件抽屉 ──────────────────────────────────────────────────
function openPartDrawer(opGid, secGid, wsGid, postGid) {
  state.currentOpGid      = opGid;
  state.currentSectionGid = secGid;
  state.currentWsGid      = wsGid;
  state.currentPostGid    = postGid;
  document.getElementById('partDrawer').classList.remove('hidden');
  document.getElementById('partSearchInput').value = '';
  document.getElementById('partList').innerHTML    = '';
}

document.getElementById('btnCloseDrawer').addEventListener('click', () => {
  document.getElementById('partDrawer').classList.add('hidden');
});

document.getElementById('btnSearchPart').addEventListener('click', async () => {
  const kw = document.getElementById('partSearchInput').value.trim();
  if (!kw) return;
  try {
    const params = { keyword: kw };
    if (state.snapshotGid) params.snapshot_gid = state.snapshotGid;
    const parts = await callBridge('ebom', 'search_parts', params);
    renderPartList(parts || []);
  } catch (e) {
    console.error('[table] search_parts 失败', e);
  }
});

document.getElementById('partSearchInput').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') document.getElementById('btnSearchPart').click();
});

function renderPartList(parts) {
  const list = document.getElementById('partList');
  list.innerHTML = '';
  if (!parts.length) {
    list.innerHTML = '<div style="padding:16px;color:var(--app-text-secondary);text-align:center">未找到零件</div>';
    return;
  }
  parts.forEach(p => {
    const div = document.createElement('div');
    div.className = 'part-item';
    div.innerHTML = `
      <div class="part-no">${esc(p.part_no)} <span style="font-weight:400;color:var(--app-text-secondary)">v${esc(p.part_version)}</span></div>
      <div class="part-name">${esc(p.ebom_part_name || p.common_part_name)}</div>
      ${p.is_fastener ? '<span class="part-fastener">紧固件</span>' : ''}
    `;
    div.addEventListener('click', () => bindPart(p));
    list.appendChild(div);
  });
}

async function bindPart(partEntry) {
  if (!state.currentOpGid) return;
  try {
    await callBridge('craft_plan', 'bind_part', {
      section_gid: state.currentSectionGid,
      workstation_gid: state.currentWsGid,
      post_gid: state.currentPostGid,
      operation_gid: state.currentOpGid,
      part_no: partEntry.part_no,
      part_version: partEntry.part_version,
      snapshot_gid: partEntry.snapshot_gid || state.snapshotGid || '',
      part_snapshot: {
        ebom_part_name: partEntry.ebom_part_name,
        common_part_name: partEntry.common_part_name,
      },
    });
    document.getElementById('partDrawer').classList.add('hidden');
    await loadTableView(state.workPlanGid, state.sectionGid);
  } catch (e) {
    console.error('[table] bind_part 失败', e);
    alert('绑定零件失败：' + (e.message || e));
  }
}

// ─── 新建工艺方案 ────────────────────────────────────────────────
document.getElementById('btnNewWorkPlan').addEventListener('click', () => {
  document.getElementById('wpName').value       = '';
  document.getElementById('wpProjectGid').value = '';
  document.getElementById('dialogWorkPlan').classList.remove('hidden');
});
document.getElementById('btnCancelWp').addEventListener('click', () => {
  document.getElementById('dialogWorkPlan').classList.add('hidden');
});
document.getElementById('btnConfirmWp').addEventListener('click', async () => {
  const name = document.getElementById('wpName').value.trim();
  if (!name) { alert('请输入方案名称'); return; }
  const projectGid = document.getElementById('wpProjectGid').value.trim();
  try {
    await callBridge('craft_plan', 'create_work_plan', { name, project_gid: projectGid });
    document.getElementById('dialogWorkPlan').classList.add('hidden');
    await loadWorkPlans();
  } catch (e) { alert('创建失败：' + (e.message || e)); }
});

// ─── 新建工段 ────────────────────────────────────────────────────
document.getElementById('btnNewSection').addEventListener('click', () => {
  document.getElementById('secName').value = '';
  document.getElementById('dialogSection').classList.remove('hidden');
});
document.getElementById('btnCancelSec').addEventListener('click', () => {
  document.getElementById('dialogSection').classList.add('hidden');
});
document.getElementById('btnConfirmSec').addEventListener('click', async () => {
  const name = document.getElementById('secName').value.trim();
  if (!name) { alert('请输入工段名称'); return; }
  try {
    await callBridge('craft_plan', 'create_section', {
      work_plan_gid: state.workPlanGid, name,
    });
    document.getElementById('dialogSection').classList.add('hidden');
    await loadSections(state.workPlanGid);
  } catch (e) { alert('创建失败：' + (e.message || e)); }
});

// ─── 通用添加对话框 ──────────────────────────────────────────────
let _addMode = null;

function showAddDialog(mode) {
  _addMode = mode;
  const titles = { ws: '添加工位', post: '添加岗位', op: '添加工序' };
  document.getElementById('dialogAddTitle').textContent = titles[mode];
  const fields = document.getElementById('dialogAddFields');
  if (mode === 'ws') {
    fields.innerHTML = `
      <label>工位编号<input id="add_code" class="dialog-input" placeholder="如：WS01"></label>
      <label>工位名称<input id="add_name" class="dialog-input" placeholder="如：涂胶工位"></label>
    `;
  } else if (mode === 'post') {
    fields.innerHTML = `
      <label>岗位编号<input id="add_code" class="dialog-input" placeholder="如：P01"></label>
      <label>岗位名称<input id="add_name" class="dialog-input"></label>
      <label>工位GID（可选）<input id="add_ws" class="dialog-input" placeholder="留空自动选首个工位"></label>
    `;
  } else {
    fields.innerHTML = `
      <label>工序编号<input id="add_code" class="dialog-input" placeholder="如：OP001"></label>
      <label>工序名称<input id="add_name" class="dialog-input"></label>
      <label>标准工时(s)<input id="add_time" type="number" class="dialog-input" placeholder="0" min="0"></label>
      <label>工位GID（可选）<input id="add_ws" class="dialog-input"></label>
      <label>岗位GID（可选）<input id="add_post" class="dialog-input"></label>
    `;
  }
  document.getElementById('dialogAdd').classList.remove('hidden');
}

document.getElementById('btnAddWs').addEventListener('click', () => showAddDialog('ws'));
document.getElementById('btnAddPost').addEventListener('click', () => showAddDialog('post'));
document.getElementById('btnAddOp').addEventListener('click',  () => showAddDialog('op'));

document.getElementById('btnCancelAdd').addEventListener('click', () => {
  document.getElementById('dialogAdd').classList.add('hidden');
});

document.getElementById('btnConfirmAdd').addEventListener('click', async () => {
  const secGid = state.sectionGid;
  if (!secGid) { alert('请先选择工段'); return; }
  const code = document.getElementById('add_code')?.value.trim();
  const name = document.getElementById('add_name')?.value.trim();
  if (!code || !name) { alert('编号和名称不能为空'); return; }
  try {
    if (_addMode === 'ws') {
      await callBridge('craft_plan', 'add_workstation', { section_gid: secGid, code, name });
    } else if (_addMode === 'post') {
      const wsGid = document.getElementById('add_ws')?.value.trim() || _firstWsGid();
      await callBridge('craft_plan', 'add_post', { section_gid: secGid, workstation_gid: wsGid, code, name });
    } else {
      const wsGid  = document.getElementById('add_ws')?.value.trim() || _firstWsGid();
      const postGid = document.getElementById('add_post')?.value.trim() || _firstPostGid(wsGid);
      const st     = parseFloat(document.getElementById('add_time')?.value) || 0;
      await callBridge('craft_plan', 'add_operation', {
        section_gid: secGid, workstation_gid: wsGid, post_gid: postGid,
        code, name, standard_time: st,
      });
    }
    document.getElementById('dialogAdd').classList.add('hidden');
    await loadTableView(state.workPlanGid, state.sectionGid);
    document.getElementById('btnAddPost').disabled = false;
    document.getElementById('btnAddOp').disabled   = false;
  } catch (e) {
    alert('操作失败：' + (e.message || e));
  }
});

function _firstWsGid()       { return state.tableRows[0]?.workstation_gid || ''; }
function _firstPostGid(wsGid){ return state.tableRows.find(r => r.workstation_gid === wsGid)?.post_gid || ''; }

// ─── Select 事件 ──────────────────────────────────────────────
document.getElementById('workPlanSelect').addEventListener('change', async (e) => {
  const gid = e.target.value;
  state.workPlanGid = gid || null;
  state.sectionGid  = null;
  const secSel = document.getElementById('sectionSelect');
  secSel.innerHTML = '<option value="">— 全部工段 —</option>';
  secSel.disabled = !gid;
  document.getElementById('btnNewSection').disabled = !gid;
  document.getElementById('btnAddWs').disabled      = !gid;
  document.getElementById('btnAddPost').disabled    = true;
  document.getElementById('btnAddOp').disabled      = true;
  if (gid) {
    await loadSections(gid);
    await loadTableView(gid, null);
  } else {
    state.tableRows = [];
    renderTable([]);
  }
});

document.getElementById('sectionSelect').addEventListener('change', async (e) => {
  const gid = e.target.value;
  state.sectionGid = gid || null;
  document.getElementById('btnAddPost').disabled    = !gid;
  document.getElementById('btnAddOp').disabled      = !gid;
  document.getElementById('btnAddFromStd').disabled = !gid;
  if (state.workPlanGid) await loadTableView(state.workPlanGid, gid || null);
});

// ─── 初始化 ────────────────────────────────────────────────────
async function init() {
  // 初始化 ViewManager
  vm = new ViewManager({
    moduleId:  'craft_table',
    columns:   CRAFT_COLS,
    toolbarEl: document.getElementById('vmToolbar'),
    onChange:  () => {
      if (state.tableRows.length >= 0) renderTable(state.tableRows);
    },
  });
  await vm.init();

  // ── 导入导出 ────────────────────────────────────────────────────────────────
  _ieMgr = new ImportExportManager({
    moduleId: 'craft_table',
    columns:  CRAFT_COLS,
    getRows:  () => (vm ? vm.applyView(state.tableRows) : state.tableRows).filter(r => !r._isGroupHeader),
    onImport: async (rows, _fieldMap, _conflict, signal) => {
      throw new Error('V1 工段工序导入已停用，不支持导入');
    },
  });
  const btnImport = document.getElementById('btnImport');
  const btnExport = document.getElementById('btnExport');
  btnImport?.addEventListener('click', () => _ieMgr.showImport());
  btnExport?.addEventListener('click', () => _ieMgr.showExport());

  // ── 对比 ────────────────────────────────────────────────────────────────────
  _diffMgr = new DiffManager({
    moduleId:        'craft_table',
    columns:         CRAFT_COLS,
    defaultMatchKey: 'code',
    loaders: [
      {
        id:       'section',
        label:    '工段（工艺方案）',
        loadList: async () => {
          return [];
        },
        loadRows: async (gid) => {
          return [];
        },
      },
      dmCurrentLoader('当前视图', () => (vm ? vm.applyView(state.tableRows) : state.tableRows).filter(r => !r._isGroupHeader)),
      dmExcelLoader(),
    ],
  });
  const btnDiff = document.getElementById('btnDiff');
  btnDiff?.addEventListener('click', () => _diffMgr.showDiff());

  // ── 从标准库添加工序 ──────────────────────────────────────────
  document.getElementById('btnAddFromStd').addEventListener('click', openStdOpDialog);
  document.getElementById('btnCancelStdOp').addEventListener('click', () => {
    document.getElementById('dialogStdOp').classList.add('hidden');
  });
  document.getElementById('btnConfirmStdOp').addEventListener('click', confirmCloneStdOp);
  document.getElementById('stdOpSearch').addEventListener('input', filterStdOpList);

  // ── Drift 弹窗 ────────────────────────────────────────────────
  document.getElementById('btnCancelDrift').addEventListener('click', () => {
    document.getElementById('dialogDrift').classList.add('hidden');
  });
  document.getElementById('btnResetDrift').addEventListener('click', confirmResetDriftFields);

  await loadWorkPlans();

  // ── DataRegistry 注册 ───────────────────────────────────
  window.DataRegistry?.register('craft_table', {
    label: '工艺表格', icon: 'icon-table',
    capabilities: ['grid_editor', 'view_manager', 'import_export', 'diff_manager', 'clone_drift', 'std_op_drift', 'bop_five_layer'],
    getRows: () => window._craftRows || [],
  });
}

window.addEventListener('DOMContentLoaded', () => setTimeout(init, 100));

// ══════════════════════════════════════════════════════════════
// 从标准库添加工序
// ══════════════════════════════════════════════════════════════

let _stdOpAll = [];   // 完整标准工序列表缓存
let _stdOpSel = null; // 当前选中的标准工序

async function openStdOpDialog() {
  if (!state.sectionGid) { alert('请先选择工段'); return; }
  _stdOpSel = null;
  document.getElementById('stdOpSearch').value = '';
  document.getElementById('stdOpSelected').textContent = '';
  document.getElementById('btnConfirmStdOp').disabled = true;
  document.getElementById('dialogStdOp').classList.remove('hidden');

  const list = document.getElementById('stdOpList');
  list.innerHTML = '<div style="padding:12px;color:var(--app-text-secondary,#888)">加载中…</div>';

  _stdOpAll = await callBridge('std_op', 'list', {}) || [];
  renderStdOpList(_stdOpAll);
}

function renderStdOpList(items) {
  const list = document.getElementById('stdOpList');
  if (!items.length) {
    list.innerHTML = '<div style="padding:12px;color:var(--app-text-secondary,#888)">无已发布标准工序</div>';
    return;
  }
  list.innerHTML = items.map(op => `
    <div class="std-op-item" data-gid="${esc(op.gid)}"
         style="padding:8px 12px;cursor:pointer;border-bottom:1px solid var(--app-border-light,rgba(0,0,0,.06));display:flex;align-items:center;gap:8px">
      <span style="color:var(--app-text-secondary,#888);font-size:11px;width:70px;flex-shrink:0">${esc(op.code)}</span>
      <span style="flex:1">${esc(op.name)}</span>
      <span style="font-size:11px;color:var(--app-text-secondary,#888)">${op.standard_time ?? 0}s</span>
      ${op.importance ? `<span class="importance-${op.importance === 'high' ? 'critical' : 'normal'}" style="font-size:11px">${esc(op.importance)}</span>` : ''}
    </div>
  `).join('');

  list.querySelectorAll('.std-op-item').forEach(el => {
    el.addEventListener('click', () => {
      list.querySelectorAll('.std-op-item').forEach(e => e.style.background = '');
      el.style.background = 'var(--app-bg-hover,rgba(0,0,0,.04))';
      _stdOpSel = _stdOpAll.find(o => o.gid === el.dataset.gid);
      document.getElementById('stdOpSelected').textContent =
        _stdOpSel ? `已选：${_stdOpSel.code}  ${_stdOpSel.name}` : '';
      document.getElementById('btnConfirmStdOp').disabled = !_stdOpSel;
    });
  });
}

function filterStdOpList() {
  const q = document.getElementById('stdOpSearch').value.trim().toLowerCase();
  const filtered = q
    ? _stdOpAll.filter(o => o.name.toLowerCase().includes(q) || o.code.toLowerCase().includes(q))
    : _stdOpAll;
  renderStdOpList(filtered);
}

async function confirmCloneStdOp() {
  if (!_stdOpSel || !state.sectionGid) return;
  const postGid = _firstPostGid(_firstWsGid());
  if (!postGid) { alert('当前工段无岗位，请先添加岗位'); return; }

  const result = await callBridge('std_op', 'clone_to_post', {
    std_op_gid: _stdOpSel.gid,
    post_gid: postGid,
    seq_no: state.tableRows.length,
  });
  document.getElementById('dialogStdOp').classList.add('hidden');
  if (result?.gid) {
    await loadTableView(state.workPlanGid, state.sectionGid);
  } else {
    alert('克隆失败，请检查控制台');
  }
}


// ══════════════════════════════════════════════════════════════
// Drift 差异查看 & 重置
// ══════════════════════════════════════════════════════════════

let _driftOpGid = null;
let _driftData  = null;

async function openDriftDialog(opGid) {
  _driftOpGid = opGid;
  _driftData  = null;
  document.getElementById('driftContent').innerHTML =
    '<div style="padding:16px;color:var(--app-text-secondary,#888)">检查中…</div>';
  document.getElementById('btnResetDrift').disabled = true;
  document.getElementById('dialogDrift').classList.remove('hidden');

  const data = await callBridge('bop', 'drift_check', { op_gid: opGid });
  _driftData = data;

  if (data?.deprecated) {
    document.getElementById('driftContent').innerHTML =
      `<p style="padding:12px;color:var(--app-text-secondary,#888)">${esc(data.message)}</p>`;
    return;
  }

  if (!data || !data.has_source) {
    document.getElementById('driftContent').innerHTML =
      '<p style="padding:12px;color:var(--app-text-secondary,#888)">此工序无标准来源</p>';
    return;
  }
  if (data.source_deleted) {
    document.getElementById('driftContent').innerHTML =
      '<p style="padding:12px;color:var(--app-danger,#e53e3e)">克隆来源的标准工序已被删除</p>';
    return;
  }

  let html = '';
  if (data.std_updated) {
    html += `<div style="padding:8px 12px;background:color-mix(in srgb,var(--app-accent,#1e66f5) 10%,transparent);border-radius:6px;margin-bottom:10px;font-size:13px">
      标准工序已升级至版本 <strong>v${data.std_current_version}</strong>（克隆时为 v${data.clone_source_version ?? '?'}），建议检查并同步
    </div>`;
  }

  if (!data.has_drift && !data.std_updated) {
    html += '<p style="padding:12px;color:var(--app-text-secondary,#888)">无偏离，与标准完全一致</p>';
  } else if (data.field_diffs && data.field_diffs.length) {
    html += '<table style="width:100%;border-collapse:collapse;font-size:13px">';
    html += '<tr style="background:var(--app-bg-secondary,#f5f5f5);font-weight:600">' +
            '<th style="padding:7px 10px;text-align:left">字段</th>' +
            '<th style="padding:7px 10px;text-align:left">当前值</th>' +
            '<th style="padding:7px 10px;text-align:left">标准值</th>' +
            '<th style="padding:7px 10px;text-align:center">重置</th></tr>';
    data.field_diffs.forEach(d => {
      html += `<tr style="border-top:1px solid var(--app-border-light,rgba(0,0,0,.06))">
        <td style="padding:7px 10px">${esc(d.label)}</td>
        <td style="padding:7px 10px;color:var(--app-danger,#e53e3e)">${esc(String(d.current ?? ''))}</td>
        <td style="padding:7px 10px;color:var(--app-success,#40a02b)">${esc(String(d.standard ?? ''))}</td>
        <td style="padding:7px 10px;text-align:center">
          <input type="checkbox" class="drift-field-cb" data-field="${esc(d.field)}" style="cursor:pointer">
        </td>
      </tr>`;
    });
    html += '</table>';
    document.getElementById('btnResetDrift').disabled = false;
  }

  document.getElementById('driftContent').innerHTML = html;

  // 监听 checkbox 启用重置按钮
  document.getElementById('driftContent').querySelectorAll('.drift-field-cb').forEach(cb => {
    cb.addEventListener('change', () => {
      const anyChecked = document.getElementById('driftContent').querySelectorAll('.drift-field-cb:checked').length > 0;
      document.getElementById('btnResetDrift').disabled = !anyChecked;
    });
  });
}

async function confirmResetDriftFields() {
  if (!_driftOpGid) return;
  const checked = [...document.getElementById('driftContent').querySelectorAll('.drift-field-cb:checked')];
  const fields = checked.map(cb => cb.dataset.field);
  if (!fields.length) return;

  const result = await callBridge('bop', 'reset_fields', { op_gid: _driftOpGid, fields });
  if (result?.deprecated) {
    alert(result.message);
    return;
  }
  document.getElementById('dialogDrift').classList.add('hidden');
  await loadTableView(state.workPlanGid, state.sectionGid);
}
