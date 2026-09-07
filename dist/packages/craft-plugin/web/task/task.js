'use strict';

function _cf(method, path, opts = {}) {
  return ListShell._cf(path, { ...opts, method });
}

// ── 列定义 ──────────────────────────────────────────────────
const TASK_COLS = [
  { key: 'display_id',   label: 'ID',      type: 'text', width: 90,  editable: false },
  { key: 'title',        label: '标题',    type: 'text', width: 240, alwaysVisible: true, required: true },
  { key: 'status',       label: '状态',    type: 'enum', width: 90,  options: [{value:'pending',label:'待处理'},{value:'in_progress',label:'进行中'},{value:'completed',label:'已完成'},{value:'closed',label:'已关闭'}] },
  { key: 'priority',     label: '优先级',  type: 'enum', width: 80,  options: [{value:'low',label:'低'},{value:'normal',label:'普通'},{value:'high',label:'高'},{value:'urgent',label:'紧急'}] },
  { key: 'plan_start',   label: '计划开始', type: 'date', width: 100 },
  { key: 'plan_end',     label: '计划结束', type: 'date', width: 100 },
  { key: 'actual_start', label: '实际开始', type: 'date', width: 100 },
  { key: 'actual_end',   label: '实际结束', type: 'date', width: 100 },
  { key: 'due_date',          label: '截止日期', type: 'date', width: 100 },
  { key: 'feishu_assignee', label: '@负责人', type: 'feishu_user',  width: 130, editable: false },
  { key: 'feishu_group',    label: '@飞书群',  type: 'feishu_group', width: 130, editable: false },
  { key: 'description',     label: '任务描述', type: 'text', multiline: true, width: 200 },
  { key: 'scheduled_date',       label: '排期日期', type: 'date', width: 100 },
  { key: 'scheduled_start_time', label: '开始时间', type: 'text', width: 80  },
  { key: 'time_estimate',        label: '预估时长(分)', type: 'number', width: 90 },
  { key: 'attachments',  label: '附件',    type: 'attachments', width: 120, editable: true },
  { key: 'created_at',   label: '创建时间', type: 'text', width: 110, editable: false },
  { key: '_sap_pin',    label: '',        type: 'text', width: 28,  alwaysVisible: true, editable: false },
  { key: '_actions',     label: '操作',    type: 'text', width: 70,  alwaysVisible: true, editable: false },
];
const TASK_SKIP_KEYS = new Set(['gid', 'created_at', 'updated_at', 'user_gid', 'parent_gid']);

const STATUS_LABEL  = { pending:'待处理', in_progress:'进行中', completed:'已完成', closed:'已关闭' };
const STATUS_COLORS = { pending:'#f9e2af', in_progress:'#89b4fa', completed:'#a6e3a1', closed:'#6c7086' };
const PRI_LABEL     = { low:'低', normal:'普通', high:'高', urgent:'紧急' };
const PRI_COLOR     = { low:'rgba(108,112,134,.3)', normal:'rgba(137,180,250,.2)', high:'rgba(249,226,175,.25)', urgent:'rgba(243,139,168,.3)' };

function _parseJSON(v, def) { if (!v) return def; if (Array.isArray(v)) return v; try { return JSON.parse(v); } catch (_) { return def; } }

// ── 状态 ──────────────────────────────────────────────────────
let _all          = [];
let _followedMap  = new Map();
let _allLists     = [];
let _currentList  = null;
let _initialized  = false;
let _pendingNavGid       = undefined;  // ls:nav 到达时 shell 尚未就绪，暂存 gid
let _pendingHighlightGid = null;        // ls:highlight 暂存：load 完成后滚动高亮
let shell         = null;  // ListShell 实例

window.addEventListener('message', e => {
  // 认证状态变化（登录/登出）时，重新加载清单列表和条目数据
  if (e.data?.type === 'auth-state' && shell) {
    shell.sidebar?.reload?.().then(() => load());
  }
  // 侧边栏清单导航 → 选中指定清单
  if (e.data?.type === 'ls:nav') {
    const gid = e.data.gid ?? null;
    if (shell) {
      shell.sidebar?._select(gid);
    } else {
      _pendingNavGid = gid;  // shell 尚未就绪，等初始化后应用
    }
  }
  // 侧边栏清单导航 → 新建清单
  if (e.data?.type === 'ls:nav:new' && shell) {
    shell.sidebar?._promptNewList?.();
  }
  // 高亮指定条目
  if (e.data?.type === 'ls:highlight') {
    const gid = e.data.gid;
    if (shell && _all.find(r => r.gid === gid)) {
      _highlightRow(gid);
    } else {
      _pendingHighlightGid = gid;
    }
  }
});

async function loadFollows() {
  try {
    const res = await _cf('GET', '/api/follows?item_type=task');
    _followedMap.clear();
    for (const f of (res?.data || [])) {
      _followedMap.set(f.item_gid, { gid: f.gid, conditions: f.notify_on || [] });
    }
  } catch (_) {}
}

// ── onRowsChange 回调 ─────────────────────────────────────────
async function _onRowsChange(newRows) {
  let didSave = false;
  for (const row of newRows) {
    if (row.gid) {
      const orig = _all.find(t => t.gid === row.gid);
      if (!orig) continue;
      const editableKeys = ['title', 'status', 'priority', 'plan_start', 'plan_end', 'actual_start', 'actual_end', 'due_date', 'scheduled_date', 'scheduled_start_time', 'time_estimate', 'attachments'];
      const changed = editableKeys.some(k => String(row[k]||'') !== String(orig[k]||''));
      if (!changed) continue;
      const fields = {};
      for (const k of editableKeys) { if (row[k] !== undefined) fields[k] = row[k]; }
      await _cf('PUT', `/api/tasks/${row.gid}`, { method: 'PUT', body: JSON.stringify(fields) })
        .catch(e => console.error('[update task cloud]', e));
      didSave = true;
    } else if (row.title) {
      const _listGid = ListShell._canonListGid(_currentList);
      await _cf('POST', '/api/tasks', { method: 'POST', body: JSON.stringify({
        title: row.title, priority: row.priority || 'normal',
        list_gid: _listGid,
        owner_gid: window.top?._authUser?.gid || window._authUser?.gid || '',
      }) }).catch(e => console.error('[add-row task]', e));
      didSave = true;
    }
  }
  if (didSave) {
    if (shell && shell.grid) shell.grid.setRows(shell.grid.getRows().filter(r => r.gid));
    await load();
  }
}

function _highlightRow(gid) {
  setTimeout(() => {
    const rowEl = shell?.grid?._el?.querySelector?.(`[data-gid="${CSS.escape(gid)}"]`);
    if (!rowEl) return;
    rowEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
    rowEl.style.transition = 'background 0.1s';
    rowEl.style.background = 'var(--color-accent-subtle, rgba(137,180,250,.25))';
    setTimeout(() => { rowEl.style.background = ''; setTimeout(() => { rowEl.style.transition = ''; }, 500); }, 2000);
  }, 80);
}

async function load() {
  const isNoList = _currentList === ListShell.NO_LIST;
  try {
    const qs = (_currentList && !isNoList) ? `?list_gid=${_currentList}` : '';
    const res = await _cf('GET', '/api/tasks' + qs).catch(() => null);
    const _toTime = v => {
      if (!v) return 0;
      if (typeof v === 'number') return v;
      const d = new Date(v); return isNaN(d) ? 0 : d.getTime() / 1000;
    };
    let combined = (res?.data || [])
      .filter(t => (_currentList && !isNoList) ? t.list_gid === _currentList : true)
      .map(t => ({...t, _source: 'cloud'}))
      .sort((a,b) => _toTime(b.created_at) - _toTime(a.created_at));
    combined = ListShell.filterByList(combined, _currentList);
    _all = combined;
    await loadFollows();
    if (shell) shell.setRows(_all);
    // 若有待高亮条目，load 完毕后滚动到该行
    if (_pendingHighlightGid) {
      const g = _pendingHighlightGid;
      _pendingHighlightGid = null;
      _highlightRow(g);
    }
    setTimeout(() => _loadSapIndicators(_all.map(r => r.gid).filter(Boolean)), 0);
  } catch (e) {
    console.error('加载失败:', e);
  }
}

// ── 自我标注批量指示器 ─────────────────────────────────────────
async function _loadSapIndicators(gids) {
  if (!gids.length) return;
  for (let i = 0; i < gids.length; i += 500) {
    const chunk = gids.slice(i, i + 500);
    const res = await (window.top?.AI00ExistingCapabilityClient || window.AI00ExistingCapabilityClient)
      .call('base.annotations.batch', { gids: chunk }).catch(() => null);
    if (!res) return;
    Object.entries(res).forEach(([gid, info]) => {
      document.querySelectorAll(`.sap-row-pin[data-gid="${gid}"]`).forEach(el => {
        if (info.status) el.dataset.status = info.status;
        else delete el.dataset.status;
      });
    });
  }
}

// ── 初始化 ────────────────────────────────────────────────────
async function init() {
  if (_initialized) return;
  _initialized = true;

  // ── ListShell ────────────────────────────────────────────────
  let _tplPickFn = null;
  shell = new ListShell({
    mountEl:      document.getElementById('appRoot'),
    itemType:     'task',
    moduleId:     'task_list',
    columns:      TASK_COLS,
    title:        '任务管理',
    titleIcon:    '#icon-check-circle',
    newLabel:     '新建条目',
    extraToolbarBtns: [
      { id: 'btn-from-template', label: '从模板', visible: false, onClick: () => _tplPickFn?.() },
      { id: 'btn-canvas-view',   label: '画布视图', onClick: () => {
          const listGid = shell?.currentListGid;
          const tm = window.top?.TabManager || window.parent?.TabManager;
          if (tm) {
            tm.open('task_canvas', listGid ? { list_gid: listGid } : {});
          }
        }
      },
    ],
    importExport: ListShell.makeImportExport('task',
      () => (shell && shell.vm ? shell.vm.applyView(_all) : _all).filter(r => !r._isGroupHeader),
      async (rows, _fm, _c, signal) => {
        for (const r of rows) {
          if (signal?.aborted) break;
          await _cf('POST', '/api/tasks', { method: 'POST', body: JSON.stringify({
            title: r.title || '导入任务',
            priority: r.priority || 'normal',
            list_gid: shell?.currentListGid || null,
            owner_gid: window.top?._authUser?.gid || window._authUser?.gid || '',
          }), signal }).catch(e => console.error('[import task]', e));
        }
        if (!signal?.aborted) await load();
      }),
    diffManager: ListShell.makeDiffManager('task',
      () => (shell && shell.vm ? shell.vm.applyView(_all) : _all).filter(r => !r._isGroupHeader),
      'title'),
    rowClass:     (row) => row._source === 'cloud' ? 'ge-row-cloud' : 'ge-row-local',
    cellRenderer: {
      _sap_pin: (val, row) => {
        if (!row.gid) return '';
        const g = row.gid;
        const n = (row.title || '').replace(/'/g, "\\'");
        return `<span class="sap-row-pin" data-gid="${g}" title="自我标注" onclick="event.stopPropagation();window.SelfAnnotationPanel?.open('${g}','${n}',event.currentTarget)"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="17" x2="12" y2="22"/><path d="M5 17h14v-1.76a2 2 0 00-1.11-1.79l-1.78-.9A2 2 0 0115 10.76V6h1a2 2 0 000-4H8a2 2 0 000 4h1v4.76a2 2 0 01-1.11 1.79l-1.78.9A2 2 0 005 15.24z"/></svg></span>`;
      },
      title: (val, row) => {
        const color = STATUS_COLORS[row.status] || '#6c7086';
        return `<span class="task-dot" style="background:${color}"></span>${ListShell._esc(val || '')}`;
      },
      status: (val) => {
        const color = STATUS_COLORS[val] || '#6c7086';
        return `<span class="status-badge" style="background:${color}22;color:${color}">${ListShell._esc(STATUS_LABEL[val]||val||'-')}</span>`;
      },
      priority: (val) => {
        if (!val) return '-';
        const bg = PRI_COLOR[val] || 'transparent';
        return `<span class="pri-badge" style="background:${bg}">${ListShell._esc(PRI_LABEL[val]||val)}</span>`;
      },
      share_scope: (val) => ListShell._esc(val || '-'),
      created_at:  (val) => val ? String(val).slice(0,10) : '-',
      attachments: (val) => AttachmentsWidget?.renderCell(val) ?? '',
      feishu_assignee: (val, row) => {
        if (!window.FeishuMentionChip) return '';
        if (row.feishu_assignee_open_id) {
          return FeishuMentionChip.renderUser(row.feishu_assignee_open_id, row.feishu_assignee_name || '', row.feishu_assignee_avatar_url || null)
            + `<button class="fm-edit-btn" data-gid="${row.gid}" data-field="feishu_assignee" title="更换">✎</button>`;
        }
        return `<button class="fm-pick-btn" data-gid="${row.gid}" data-field="feishu_assignee">+负责人</button>`;
      },
      feishu_group: (val, row) => {
        if (!window.FeishuMentionChip) return '';
        if (row.feishu_group_chat_id) {
          return FeishuMentionChip.renderGroup(row.feishu_group_chat_id, row.feishu_group_name || '')
            + `<button class="fm-edit-btn" data-gid="${row.gid}" data-field="feishu_group" title="更换">✎</button>`;
        }
        return `<button class="fm-pick-btn" data-gid="${row.gid}" data-field="feishu_group">+群聊</button>`;
      },
      _actions: (val, row) => {
        if (!row.gid) return '';
        const followed = _followedMap.has(row.gid);
        const subBtn = row._source === 'cloud' ? SubscribeButton.html(row.gid, followed, row.title, 'task') : '';
        return `<div class="cell-actions">${subBtn}<button class="btn-done" data-gid="${row.gid}" title="标为完成">✓</button></div>`;
      },
    },
    onRowsChange:      _onRowsChange,
    ganttFields:   { startField: 'plan_start', endField: 'plan_end' },
    onListsChange: (lists) => { _allLists = lists; },
    onSelect:      (gid) => { _currentList = gid; load(); },
    initListGid:   null,
  });
  await shell.init();

  // 若初始化前已收到 ls:nav 消息，立即应用
  if (_pendingNavGid !== undefined) {
    shell.sidebar?._select(_pendingNavGid);
    _pendingNavGid = undefined;
  }
  // 绑定操作按钮事件（委托到 GridEditor 容器）
  if (window.FeishuMentionChip) FeishuMentionChip.bindClickDelegate(shell.grid._el);
  shell.grid._el.addEventListener('click', async ev => {
    // FeishuMentionChip pick/edit buttons
    const fmBtn = ev.target.closest('.fm-pick-btn, .fm-edit-btn');
    if (fmBtn) {
      ev.stopPropagation();
      const gid   = fmBtn.dataset.gid;
      const field = fmBtn.dataset.field;
      const row   = _all.find(t => t.gid === gid);
      if (!row || !window.FeishuMentionChip) return;
      FeishuMentionChip.openPicker({
        mode: field === 'feishu_assignee' ? 'user' : 'group',
        onSelect: async (result) => {
          const patch = result.type === 'user'
            ? { feishu_assignee_open_id: result.open_id, feishu_assignee_name: result.name, feishu_assignee_avatar_url: result.avatar_url || '' }
            : { feishu_group_chat_id: result.chat_id, feishu_group_name: result.name };
          await _cf('PUT', `/api/tasks/${gid}`, { method: 'PUT', body: JSON.stringify(patch) })
            .catch(e => console.error('[fm patch task]', e));
          Object.assign(row, patch);
          shell.setRows(_all);
        },
        onClear: async () => {
          const patch = field === 'feishu_assignee'
            ? { feishu_assignee_open_id: null, feishu_assignee_name: null }
            : { feishu_group_chat_id: null, feishu_group_name: null };
          await _cf('PUT', `/api/tasks/${gid}`, { method: 'PUT', body: JSON.stringify(patch) })
            .catch(e => console.error('[fm clear task]', e));
          Object.assign(row, patch);
          shell.setRows(_all);
        },
      });
      return;
    }
    const done   = ev.target.closest('.btn-done');
    const sub    = ev.target.closest('.sub-btn');
    if (done) {
      ev.stopPropagation();
      const gid = done.dataset.gid;
      const row = _all.find(t => t.gid === gid);
      if (!row) return;
      await _cf('PUT', `/api/tasks/${gid}`, { method: 'PUT', body: JSON.stringify({ status: 'completed' }) });
      load();
    } else if (sub) {
      ev.stopPropagation();
      const gid   = sub.dataset.gid;
      const row   = _all.find(t => t.gid === gid) || {};
      const state = _followedMap.get(gid) || { gid: null, conditions: [] };
      SubscribeButton.open(sub, {
        itemType: 'task', itemGid: gid, itemTitle: row.title || gid,
        followed: _followedMap.has(gid),
        followGid: state.gid,
        conditions: state.conditions,
        cf: ListShell._cf,
        onSave: (newState) => {
          if (newState.followed) {
            _followedMap.set(gid, { gid: newState.followGid, conditions: newState.conditions });
          } else {
            _followedMap.delete(gid);
          }
          if (shell) shell.setRows(_all);
        },
      });
    }
  });

  // 从模板按钮始终可见（云端模式）
  const tplBtn = shell.getExtraBtn('btn-from-template');
  if (tplBtn) tplBtn.style.display = '';

  let _tplList = [];
  let _tplSelected = null;
  let _userList = [];

  async function _openTplPick() {
    document.getElementById('tplPickMask').classList.add('show');
    document.getElementById('tplPickNext').disabled = true;
    document.getElementById('tplPickHint').textContent = '正在加载…';
    document.getElementById('tplPickList').innerHTML = '';
    _tplSelected = null;
    try {
      const res = await _cf('GET', '/api/task-templates');
      _tplList = res?.data || [];
      _renderTplList();
    } catch (e) {
      document.getElementById('tplPickHint').textContent = '加载失败：' + e.message;
    }
  }

  function _renderTplList() {
    const list = document.getElementById('tplPickList');
    const hint = document.getElementById('tplPickHint');
    if (!_tplList.length) { hint.textContent = '暂无可用模板'; return; }
    hint.textContent = `共 ${_tplList.length} 个模板，点击选择`;
    list.innerHTML = _tplList.map(t => `
      <div class="tpl-list-item" data-gid="${ListShell._esc(t.gid)}">
        <div class="tpl-name">${ListShell._esc(t.name)}</div>
        <div class="tpl-meta">${t.description ? ListShell._esc(t.description) : '暂无描述'}</div>
      </div>
    `).join('');
    list.querySelectorAll('.tpl-list-item').forEach(el => {
      el.addEventListener('click', () => {
        list.querySelectorAll('.tpl-list-item').forEach(x => x.classList.remove('selected'));
        el.classList.add('selected');
        document.getElementById('tplPickNext').disabled = false;
      });
    });
  }

  async function _tplPickNext() {
    const sel = document.getElementById('tplPickList').querySelector('.tpl-list-item.selected');
    if (!sel) return;
    const gid = sel.dataset.gid;
    document.getElementById('tplPickNext').disabled = true;
    try {
      const res = await _cf('GET', `/api/task-templates/${gid}`);
      _tplSelected = res?.data;
      if (!_userList.length) {
        const ur = await (window.top?.AI00ExistingCapabilityClient || window.AI00ExistingCapabilityClient)
          .call('base.users.list').catch(() => null);
        _userList = ur?.data || [];
      }
      _closeTplPick(false);
      _openTplInst();
    } catch (e) {
      alert('加载模板详情失败：' + e.message);
      document.getElementById('tplPickNext').disabled = false;
    }
  }

  function _closeTplPick(clearSel = true) {
    document.getElementById('tplPickMask').classList.remove('show');
    if (clearSel) _tplSelected = null;
  }

  _tplPickFn = _openTplPick;
  document.getElementById('tplPickCancel')?.addEventListener('click', () => _closeTplPick(true));
  document.getElementById('tplPickNext')?.addEventListener('click', _tplPickNext);
  document.getElementById('tplPickMask')?.addEventListener('click', e => {
    if (e.target === e.currentTarget) _closeTplPick(true);
  });

  function _openTplInst() {
    if (!_tplSelected) return;
    const tpl = _tplSelected;
    document.getElementById('tplInstTitle').textContent = `实例化：${tpl.name}`;
    document.getElementById('tplInstMask').classList.add('show');

    const varSet = new Set();
    const roleSet = new Set();
    for (const item of tpl.items || []) {
      const matches = [...(item.title_pattern || '').matchAll(/\{\{(.+?)\}\}/g)];
      matches.forEach(m => varSet.add(m[1].trim()));
      if (item.assignee_role) roleSet.add(item.assignee_role);
    }

    const form = document.getElementById('tplInstForm');
    const today = new Date().toISOString().slice(0,10);
    const inputStyle = 'width:100%;box-sizing:border-box;padding:6px 10px;margin-top:2px;background:var(--bg-secondary,#181825);border:1px solid var(--border-default,#313244);border-radius:6px;color:var(--text-normal,#cdd6f4);font-size:12px;outline:none';
    let html = `
      <label class="inst-field-label">关联项目 GID（可留空）
        <input id="tplInstProjectGid" style="${inputStyle}" placeholder="project_gid">
      </label>
      <label class="inst-field-label">任务起始日期
        <input id="tplInstStartDate" type="date" value="${today}" style="${inputStyle}">
      </label>
    `;

    if (varSet.size) {
      html += `<div class="inst-section-title">标题变量</div>`;
      for (const v of varSet) {
        html += `<label class="inst-field-label">{{${ListShell._esc(v)}}}
          <input id="tplVar_${ListShell._esc(v)}" data-var="${ListShell._esc(v)}" style="${inputStyle}" placeholder="${ListShell._esc(v)}">
        </label>`;
      }
    }

    if (roleSet.size) {
      html += `<div class="inst-section-title">角色分配（可选）</div>`;
      const userOpts = _userList.map(u =>
        `<option value="${ListShell._esc(u.gid)}">${ListShell._esc(u.name || u.email || u.gid)}</option>`
      ).join('');
      const selStyle = 'width:100%;box-sizing:border-box;padding:6px 8px;margin-top:2px;background:var(--bg-secondary,#181825);border:1px solid var(--border-default,#313244);border-radius:6px;color:var(--text-normal,#cdd6f4);font-size:12px;outline:none';
      for (const r of roleSet) {
        html += `<label class="inst-field-label">${ListShell._esc(r)}
          <select id="tplRole_${ListShell._esc(r)}" data-role="${ListShell._esc(r)}" style="${selStyle}">
            <option value="">— 不分配 —</option>
            ${userOpts}
          </select>
        </label>`;
      }
    }

    form.innerHTML = html;
  }

  function _closeTplInst() {
    document.getElementById('tplInstMask').classList.remove('show');
  }

  async function _submitTplInst() {
    if (!_tplSelected) return;
    const projectGid = document.getElementById('tplInstProjectGid')?.value.trim() || '';
    const startDate  = document.getElementById('tplInstStartDate')?.value || new Date().toISOString().slice(0,10);

    const titleVars = {};
    document.getElementById('tplInstForm').querySelectorAll('[data-var]').forEach(el => {
      if (el.value.trim()) titleVars[el.dataset.var] = el.value.trim();
    });

    const assigneeMap = {};
    document.getElementById('tplInstForm').querySelectorAll('[data-role]').forEach(el => {
      if (el.value) assigneeMap[el.dataset.role] = el.value;
    });

    document.getElementById('tplInstConfirm').disabled = true;
    try {
      const res = await _cf('POST', `/api/task-templates/${_tplSelected.gid}/instantiate`, {
        method: 'POST',
        body: JSON.stringify({
          project_gid:  projectGid || null,
          start_date:   startDate,
          title_vars:   titleVars,
          assignee_map: assigneeMap,
        }),
      });
      const count = res?.count ?? 0;
      _closeTplInst();
      _tplSelected = null;
      await load();
      const hint = document.createElement('div');
      hint.style.cssText = 'position:fixed;top:20px;right:24px;z-index:9999;background:var(--color-accent,#89b4fa);color:var(--bg-primary,#1e1e2e);padding:8px 18px;border-radius:8px;font-size:13px;font-weight:500;box-shadow:0 4px 16px rgba(0,0,0,.3)';
      hint.textContent = `已创建 ${count} 个任务`;
      document.body.appendChild(hint);
      setTimeout(() => hint.remove(), 2500);
    } catch (err) {
      console.error('[tpl instantiate]', err);
      alert('创建失败：' + err.message);
    } finally {
      document.getElementById('tplInstConfirm').disabled = false;
    }
  }

  document.getElementById('tplInstCancel')?.addEventListener('click', _closeTplInst);
  document.getElementById('tplInstBack')?.addEventListener('click', () => { _closeTplInst(); _openTplPick(); });
  document.getElementById('tplInstMask')?.addEventListener('click', e => {
    if (e.target === e.currentTarget) _closeTplInst();
  });
  document.getElementById('tplInstConfirm')?.addEventListener('click', _submitTplInst);

  await load();

  // 自我标注：保存后更新行指示器
  window.addEventListener('sap-saved', e => {
    document.querySelectorAll(`.sap-row-pin[data-gid="${e.detail.itemGid}"]`).forEach(el => {
      if (e.detail.status) el.dataset.status = e.detail.status;
      else delete el.dataset.status;
    });
  });

  // ── DataRegistry 注册 ──────────────────────────────────
  window.DataRegistry?.register('task', {
    label: '任务管理', icon: 'icon-check-circle',
    capabilities: ['local_sqlite', 'cloud_pg', 'data_promotion', 'at_mention', 'subscribe', 'task_template_inst', 'grid_editor', 'view_manager', 'diff_manager'],
    getRows: () => _all,
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
