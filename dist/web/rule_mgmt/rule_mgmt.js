/**
 * 规则管理脚本 — ListShell 版本
 * 行点击→新 Tab container_card (row_detail)
 * 状态操作在 _actions 列内联处理
 */
'use strict';

// ── 列定义 ────────────────────────────────────────────────────────────────────
const RULE_COLS = [
  { key: 'display_id',        label: 'ID',        type: 'text',   width: 90,  editable: false },
  { key: 'name',              label: '规则名称',  type: 'text',   width: 220 },
  { key: 'code',              label: '规则编号',  type: 'text',   width: 120 },
  { key: 'rule_type',         label: '类型',      type: 'enum',   width: 100, options: [
    { value: 'other',       label: '其他' },
    { value: 'sequence',    label: '顺序约束' },
    { value: 'constraint',  label: '工艺约束' },
    { value: 'time_limit',  label: '时限约束' },
  ]},
  { key: 'enforcement_level', label: '执行级别',  type: 'enum',   width: 90, options: [
    { value: 'advisory',  label: '建议' },
    { value: 'mandatory', label: '强制' },
  ]},
  { key: 'status',            label: '状态',      type: 'enum',   width: 80, options: [
    { value: 'draft',     label: '草稿' },
    { value: 'active',    label: '激活' },
    { value: 'suspended', label: '暂停' },
    { value: 'obsolete',  label: '废弃' },
  ]},
  { key: 'deviation_count',   label: '背离数',    type: 'number', width: 70 },
  { key: 'expression',        label: 'CEL 表达式', type: 'text',   width: 240, editable: true },
  { key: 'context_class_gid', label: '绑定类',    type: 'text',   width: 130, editable: false },
  { key: '_actions',          label: '操作',      type: 'text',   width: 160, alwaysVisible: true, editable: false },
];

// ── 状态标签 ──────────────────────────────────────────────────────────────────
const STATUS_BADGE  = { draft: 'badge-draft', active: 'badge-active', suspended: 'badge-suspended', obsolete: 'badge-obsolete' };
const STATUS_LABEL  = { draft: '草稿', active: '激活', suspended: '暂停', obsolete: '废弃' };

// ── 全局状态 ──────────────────────────────────────────────────────────────────
let _shell       = null;
let _rules       = [];
let _allLists    = [];
let _currentList = null;
let _devRuleGid  = null;
let _ontoClasses = [];   // { gid, name, label_zh }

// 加载本体类列表（用于绑定类显示和选择）
async function _loadOntoClasses() {
  try {
    const resp = await ListShell._cf('/api/ontology/classes');
    _ontoClasses = _flattenOnto(resp.data || []);
    // 刷新渲染（让 context_class_gid 列显示中文名）
    if (_shell) _shell.setRows(_rules);
  } catch { /* 本体未就绪，静默 */ }
}

function _flattenOnto(nodes, result = []) {
  for (const n of nodes) {
    result.push({ gid: n.gid, name: n.name, label_zh: n.label_zh || n.name });
    _flattenOnto(n.children || [], result);
  }
  return result;
}

function _ontoLabel(gid) {
  if (!gid) return '-';
  const c = _ontoClasses.find(c => c.gid === gid);
  return c ? `${c.label_zh}` : gid.slice(0, 8) + '…';
}

// ── 容器卡片 Tab ──────────────────────────────────────────────────────────────
function _openRuleDetail(row) {
  const p = window.parent || window;
  p.TabManager?.open?.('container_card', { mode: 'row_detail', item_type: 'rule', gid: row.gid, source: row._source || 'local' });
}

function _openRuleDef(row) {
  const p = window.parent || window;
  p.TabManager?.open?.('container_card', { mode: 'field_detail', item_type: 'rule', gid: row.gid, field: 'rule_definition', source: row._source || 'local' });
}

// ── 单元格渲染 ────────────────────────────────────────────────────────────────
const CELL_RENDERER = {
  status: (v) => `<span class="badge ${STATUS_BADGE[v]||''}">${STATUS_LABEL[v]||v||'-'}</span>`,
  enforcement_level: (v) => v === 'mandatory'
    ? '<span style="color:var(--danger,#f38ba8);font-weight:600">强制</span>'
    : '<span style="color:var(--text-muted,#a6adc8)">建议</span>',
  rule_type: (v) => ({ other:'其他', sequence:'顺序约束', constraint:'工艺约束', time_limit:'时限约束' }[v] || v || '-'),
  expression: (v) => v
    ? `<code style="font-size:11px;background:var(--bg2,#313244);border-radius:3px;padding:1px 5px;max-width:220px;display:inline-block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;vertical-align:middle" title="${v}">${v}</code>`
    : '<span style="color:var(--text-muted,#a6adc8)">-</span>',
  context_class_gid: (v) => v
    ? `<span style="background:var(--bg2,#313244);border-radius:3px;padding:1px 6px;font-size:11px;cursor:default" title="${v}">${_ontoLabel(v)}</span>`
    : '<span style="color:var(--text-muted,#a6adc8);font-size:11px">未绑定</span>',
  _actions: (_v, row) => {
    if (!row.gid) return '';
    const st = row.status || 'draft';
    const activateBtn  = st === 'draft' || st === 'suspended'
      ? `<button class="btn-rule-action btn-ok-sm" data-gid="${row.gid}" data-action="activate" style="font-size:11px;padding:2px 6px">激活</button>` : '';
    const suspendBtn   = st === 'active'
      ? `<button class="btn-rule-action btn-warn-sm" data-gid="${row.gid}" data-action="suspend" style="font-size:11px;padding:2px 6px">暂停</button>` : '';
    const devBtn       = `<button class="btn-rule-dev" data-gid="${row.gid}" style="font-size:11px;padding:2px 6px;background:transparent;border:1px solid var(--border,#313244);border-radius:4px;cursor:pointer;color:var(--text-muted,#a6adc8)">+背离</button>`;
    const openBtn      = `<button class="btn-rule-open" data-gid="${row.gid}" style="font-size:11px;padding:2px 6px;background:transparent;border:1px solid var(--border,#313244);border-radius:4px;cursor:pointer;color:var(--text,#cdd6f4)">详情</button>`;
    return `<div style="display:flex;gap:4px;align-items:center">${activateBtn}${suspendBtn}${devBtn}${openBtn}</div>`;
  },
};

// ── 数据加载 ──────────────────────────────────────────────────────────────────
const load = ListShell.buildLoadHandler({
  bridgeNs:         'rule',
  bridgeListMethod: 'list_rules',
  cloudPath:        '/api/rules',
  getCurrentList:   () => _currentList,
  getAllLists:       () => _allLists,
  getShell:         () => _shell,
  setData:          (rows) => { _rules = rows; },
});

// ── 行变更处理 ────────────────────────────────────────────────────────────────
const _onRowsChange = ListShell.buildRowsChangeHandler({
  editableKeys:       ['code', 'name', 'rule_type', 'enforcement_level', 'expression', 'context_class_gid'],
  primaryKey:         'name',
  cloudUpdatePath:    (gid) => `/api/rules/${gid}`,
  cloudCreatePath:    '/api/rules',
  bridgeNs:           'rule',
  bridgeUpdateMethod: 'update_rule',
  bridgeCreateMethod: 'create_rule',
  buildCreateBody:    (row, canonGid) => ({
    code:              row.code || '',
    name:              row.name,
    rule_type:         row.rule_type || 'other',
    enforcement_level: row.enforcement_level || 'advisory',
    list_gid:          canonGid,
  }),
  getData:        () => _rules,
  getCurrentList: () => _currentList,
  getAllLists:     () => _allLists,
  getShell:       () => _shell,
  load,
});

// ── 状态操作 ──────────────────────────────────────────────────────────────────
async function _ruleAction(gid, action) {
  const rule = _rules.find(r => r.gid === gid);
  if (!rule) return;
  try {
    await ListShell._cf(`/api/rules/${gid}/${action}`, { method: 'POST' });
    await load();
  } catch (err) { alert('操作失败：' + err.message); }
}

// ── 规则检验 ──────────────────────────────────────────────────────────────────
async function _runRuleCheck(row) {
  const contextStr = prompt(`输入 JSON context 测试规则「${row.name}」\n示例：{"torque": 12.0, "std_time": 60}`, '{}');
  if (contextStr === null) return;
  let context;
  try { context = JSON.parse(contextStr); } catch { alert('JSON 格式错误，请检查输入'); return; }
  try {
    const resp = await ListShell._cf('/api/rule-engine/check', {
      method: 'POST',
      body: JSON.stringify({ rule_gid: row.gid, context }),
    });
    alert(`规则：${row.name}\n结果：${(resp.result || '').toUpperCase()}${resp.message ? '\n详情：' + resp.message : ''}`);
  } catch (e) {
    alert('检验请求失败：' + e);
  }
}

// ── 背离记录 ──────────────────────────────────────────────────────────────────
function showDeviationModal(gid) {
  _devRuleGid = gid;
  document.getElementById('dev-work-plan').value = '';
  document.getElementById('dev-operation').value  = '';
  document.getElementById('dev-reason').value     = '';
  document.getElementById('modal-deviation').style.display = 'flex';
}

function hideDeviationModal() {
  document.getElementById('modal-deviation').style.display = 'none';
  _devRuleGid = null;
}

async function saveDeviation() {
  if (!_devRuleGid) return;
  const workPlan  = document.getElementById('dev-work-plan').value.trim();
  const operation = document.getElementById('dev-operation').value.trim();
  const reason    = document.getElementById('dev-reason').value.trim();
  try {
    const res = await ListShell._cf(`/api/rules/${_devRuleGid}/deviations`, {
      method: 'POST',
      body: JSON.stringify({ work_plan_gid: workPlan, operation_gid: operation, deviation_reason: reason }),
    });
    hideDeviationModal();
    if (res?.data?.requires_approval) alert('该背离需要审批，已标记！');
    await load();
  } catch (err) { alert('保存失败：' + err.message); }
}

// ── 视图行（视图过滤/排序后的数据，供 IE/Diff 使用）────────────────────────
const _getViewRows = () => (_shell && _shell.vm ? _shell.vm.applyView(_rules) : _rules).filter(r => !r._isGroupHeader);

// ── 初始化 ────────────────────────────────────────────────────────────────────
async function init() {
  _shell = new ListShell({
    mountEl:      document.getElementById('appRoot'),
    itemType:     'rule',
    moduleId:     'rule_mgmt',
    columns:      RULE_COLS,
    title:        '规则管理',
    titleIcon:    '#icon-shield',
    newLabel:     '新建条目',
    cellRenderer: CELL_RENDERER,
    onRowsChange: _onRowsChange,
    extraContextItems: (row) => [
      { label: '在新标签中打开详情', action: 'open_detail' },
      { label: '打开规则定义字段', action: 'open_def' },
      { label: '绑定本体类…', action: 'bind_class' },
      { label: '记录背离', action: 'add_deviation' },
      { label: '运行规则检验…', action: 'run_rule_check' },
    ],
    onContextAction: (action, row) => {
      if (action === 'open_detail')   _openRuleDetail(row);
      if (action === 'open_def')      _openRuleDef(row);
      if (action === 'bind_class')    row.gid && _showBindClassModal(row);
      if (action === 'add_deviation') row.gid && showDeviationModal(row.gid);
      if (action === 'run_rule_check') row.gid && _runRuleCheck(row);
    },
    rowClass: (row) => row._source === 'cloud' ? 'ge-row-cloud' : 'ge-row-local',
    onListsChange: (lists) => { _allLists = lists; },
    onSelect:   (gid) => { _currentList = gid; load(); },
    rdpSaveOpts: { bridgeNs: 'rule', bridgeMethod: 'update_rule', cloudPath: '/api/rules' },
    importExport: ListShell.makeImportExport('rule_mgmt', _getViewRows, async (rows, _fm, _c, signal) => {
        for (const r of rows) {
          if (signal?.aborted) break;
          if (!r.name) continue;
          await ListShell._cf('/api/rules', {
            method: 'POST',
            body: JSON.stringify({ name: r.name, code: r.code || '', rule_type: r.rule_type || 'other', enforcement_level: r.enforcement_level || 'advisory', list_gid: _currentList || null }),
            signal,
          }).catch(e => console.error('[import rule]', e));
        }
        if (!signal?.aborted) await load();
      }),
    diffManager: ListShell.makeDiffManager('rule_mgmt', _getViewRows, 'name'),
  });
  await _shell.init();
  _loadOntoClasses();

  // 按钮事件委托（_actions 列内的按钮）
  _shell.grid._el.addEventListener('click', async (ev) => {
    const actionBtn = ev.target.closest('.btn-rule-action');
    if (actionBtn) { ev.stopPropagation(); await _ruleAction(actionBtn.dataset.gid, actionBtn.dataset.action); return; }
    const devBtn = ev.target.closest('.btn-rule-dev');
    if (devBtn) { ev.stopPropagation(); showDeviationModal(devBtn.dataset.gid); return; }
    const openBtn = ev.target.closest('.btn-rule-open');
    if (openBtn) {
      ev.stopPropagation();
      const row = _rules.find(r => r.gid === openBtn.dataset.gid);
      if (row) _openRuleDetail(row);
    }
  });

  // 背离弹窗按钮
  document.getElementById('btn-close-dev-modal').addEventListener('click', hideDeviationModal);
  document.getElementById('btn-cancel-dev-modal').addEventListener('click', hideDeviationModal);
  document.getElementById('btn-save-deviation').addEventListener('click', saveDeviation);

  // 主题同步由 list_shell.js 的 _lsInitTheme() IIFE 统一处理

  await load();
}

// ── 绑定本体类 ────────────────────────────────────────────────────────────────
function _showBindClassModal(row) {
  const existing = row.context_class_gid || '';
  const opts = _ontoClasses.map(c =>
    `<option value="${c.gid}" ${c.gid === existing ? 'selected' : ''}>${c.label_zh}（${c.name}）</option>`
  ).join('');

  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center;z-index:9999';
  overlay.innerHTML = `
    <div style="background:var(--bg,#1e1e2e);border:1px solid var(--border,#313244);border-radius:8px;padding:20px 24px;min-width:340px;display:flex;flex-direction:column;gap:12px;box-shadow:0 8px 32px rgba(0,0,0,.3)">
      <div style="font-size:15px;font-weight:600;color:var(--text,#cdd6f4)">绑定本体类</div>
      <div style="font-size:12px;color:var(--text-muted,#a6adc8)">规则：${row.name}</div>
      <select id="_bindClassSel" style="background:var(--bg2,#313244);border:1px solid var(--border,#313244);border-radius:5px;color:var(--text,#cdd6f4);padding:6px 8px;font-size:13px;width:100%">
        <option value="">— 不绑定 —</option>${opts}
      </select>
      <div style="display:flex;justify-content:flex-end;gap:8px">
        <button id="_bindClassCancel" style="background:var(--bg2,#313244);border:1px solid var(--border,#313244);border-radius:5px;color:var(--text,#cdd6f4);padding:6px 14px;cursor:pointer">取消</button>
        <button id="_bindClassSave" style="background:var(--primary,#89b4fa);border:none;border-radius:5px;color:#1e1e2e;padding:6px 14px;cursor:pointer;font-weight:600">保存</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);

  overlay.querySelector('#_bindClassCancel').addEventListener('click', () => overlay.remove());
  overlay.querySelector('#_bindClassSave').addEventListener('click', async () => {
    const val = overlay.querySelector('#_bindClassSel').value || null;
    try {
      await ListShell._cf(`/api/rules/${row.gid}`, {
        method: 'PATCH',
        body: JSON.stringify({ context_class_gid: val }),
      });
      row.context_class_gid = val;
      _shell.setRows(_rules);
      overlay.remove();
    } catch (e) { alert('保存失败：' + e); }
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
