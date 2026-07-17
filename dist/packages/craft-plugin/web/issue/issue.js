'use strict';

// ── 列定义 ──────────────────────────────────────────────────
const ISSUE_COLS = [
  { key: 'display_id',    label: 'ID',      type: 'text', width: 90,  editable: false },
  { key: 'title',         label: '标题',    type: 'text', width: 280, alwaysVisible: true, required: true },
  { key: 'status',        label: '状态',    type: 'enum', width: 90,
    options: [{ value:'open',label:'待处理'},{ value:'in_progress',label:'处理中'},{ value:'resolved',label:'已解决'},{ value:'closed',label:'已关闭'}] },
  { key: 'severity',      label: '严重度',  type: 'enum', width: 80,
    options: [{ value:'low',label:'低'},{ value:'medium',label:'中'},{ value:'high',label:'高'},{ value:'critical',label:'严重'}] },
  { key: 'bop_entry_gid', label: '关联工序', type: 'text', width: 180, editable: false },
  { key: 'feishu_assignee', label: '@负责人',  type: 'feishu_user',  width: 130, editable: false },
  { key: 'feishu_group',    label: '@飞书群',  type: 'feishu_group', width: 130, editable: false },
  { key: 'description',          label: '问题描述',    type: 'text', multiline: true, width: 200 },
  { key: 'occurrence_root_cause', label: '发生根因',   type: 'text', multiline: true, width: 200 },
  { key: 'escape_root_cause',     label: '流出根因',   type: 'text', multiline: true, width: 200 },
  { key: 'interim_action',        label: '临时措施',   type: 'text', multiline: true, width: 200 },
  { key: 'permanent_action',      label: '永久措施',   type: 'text', multiline: true, width: 200 },
  { key: 'attachments',   label: '附件',    type: 'attachments', width: 120, editable: true },
  { key: 'created_at',    label: '创建时间', type: 'text', width: 110, editable: false },
  { key: '_sap_pin',    label: '',        type: 'text', width: 28,  alwaysVisible: true, editable: false },
  { key: '_actions',      label: '操作',    type: 'text', width: 50,  alwaysVisible: true, editable: false },
];
const ISSUE_SKIP_KEYS = new Set(['gid', 'created_at', 'updated_at', 'user_gid']);

const STATUS_LABEL   = { open:'待处理', in_progress:'处理中', resolved:'已解决', closed:'已关闭' };
const STATUS_COLORS  = { open:'#f9e2af', in_progress:'#89b4fa', resolved:'#a6e3a1', closed:'#6c7086' };
const SEVERITY_LABEL = { low:'低', medium:'中', high:'高', critical:'严重' };
const SEVERITY_COLOR = { low:'rgba(108,112,134,.3)', medium:'rgba(249,226,175,.25)', high:'rgba(235,160,172,.25)', critical:'rgba(243,139,168,.3)' };

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
// BOP 条目标题缓存 { gid → {title, version_tag} }
const _bopCache   = {};

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
      _pendingNavGid = gid;
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

// ── BOP 条目缓存与选择器 ─────────────────────────────────────
async function _prefetchBopLabels(gids) {
  const missing = gids.filter(g => g && !_bopCache[g]);
  if (!missing.length) return;
  try {
    await Promise.all(missing.map(async gid => {
      const res = await ListShell._cf(`/api/bop/entries/${gid}`).catch(() => null);
      if (res?.data) {
        _bopCache[gid] = { title: res.data.title || gid, version_tag: res.data.version_tag || '' };
      }
    }));
  } catch (_) {}
}

let _bopPickerCallback = null;  // (entry) => void

async function _openBopPicker(issueGid, currentEntryGid) {
  const mask = document.getElementById('bopPickerMask');
  const list = document.getElementById('bopPickerList');
  const inp  = document.getElementById('bopPickerSearch');
  mask.classList.add('show');
  list.innerHTML = '<div style="padding:8px;color:var(--text-muted)">加载中…</div>';
  inp.value = '';

  let _allEntries = [];

  async function _doSearch(q) {
    const params = new URLSearchParams({ node_types: 'operation', limit: '200' });
    if (q) params.set('q', q);
    const res = await ListShell._cf(`/api/bop/entries/search?${params}`).catch(() => null);
    _allEntries = res?.data || [];
    _renderBopList(_allEntries);
  }

  function _renderBopList(entries) {
    if (!entries.length) {
      list.innerHTML = '<div style="padding:8px;color:var(--text-muted)">无匹配工序</div>';
      return;
    }
    let lastVer = '';
    list.innerHTML = entries.map(e => {
      let header = '';
      if (e.version_tag !== lastVer) {
        header = `<div class="bop-picker-ver">${ListShell._esc(e.version_tag)}</div>`;
        lastVer = e.version_tag;
      }
      const active = e.gid === currentEntryGid ? ' bop-picker-active' : '';
      return `${header}<div class="bop-picker-item${active}" data-gid="${e.gid}" data-title="${ListShell._esc(e.title)}" data-ver="${ListShell._esc(e.version_tag)}">${ListShell._esc(e.title)}<span class="bop-picker-code">${ListShell._esc(e.bom_row_id||'')}</span></div>`;
    }).join('');
    list.querySelectorAll('.bop-picker-item').forEach(el => {
      el.addEventListener('click', () => {
        const entry = { gid: el.dataset.gid, title: el.dataset.title, version_tag: el.dataset.ver };
        _bopCache[entry.gid] = entry;
        _closeBopPicker();
        _bopPickerCallback?.(entry);
      });
    });
  }

  let _searchTimer;
  inp.oninput = () => {
    clearTimeout(_searchTimer);
    _searchTimer = setTimeout(() => _doSearch(inp.value.trim()), 300);
  };

  document.getElementById('bopPickerClear').onclick = () => {
    _closeBopPicker();
    _bopPickerCallback?.({ gid: null, title: '' });
  };

  await _doSearch('');
}

function _closeBopPicker() {
  document.getElementById('bopPickerMask').classList.remove('show');
}

async function _linkBopEntry(issueRow) {
  _bopPickerCallback = async (entry) => {
    try {
      await ListShell._cf(`/api/issues/${issueRow.gid}`, {
        method: 'PUT',
        body: JSON.stringify({ bop_entry_gid: entry.gid || null }),
      });
      const row = _all.find(r => r.gid === issueRow.gid);
      if (row) row.bop_entry_gid = entry.gid || null;
      shell?.setRows(_all);
    } catch (err) { alert('关联失败：' + err.message); }
  };
  await _openBopPicker(issueRow.gid, issueRow.bop_entry_gid);
}

async function loadFollows() {
  try {
    const res = await ListShell._cf('/api/follows?item_type=issue');
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
      const orig = _all.find(i => i.gid === row.gid);
      if (!orig) continue;
      const editableKeys = ['title', 'status', 'severity', 'attachments'];
      const changed = editableKeys.some(k => String(row[k]||'') !== String(orig[k]||''));
      if (!changed) continue;
      const fields = {};
      for (const k of editableKeys) { if (row[k] !== undefined) fields[k] = row[k]; }
      await ListShell._cf(`/api/issues/${row.gid}`, { method: 'PUT', body: JSON.stringify(fields) })
        .catch(e => console.error('[update issue cloud]', e));
      didSave = true;
    } else if (row.title) {
      const _listGid = ListShell._canonListGid(_currentList);
      await ListShell._cf('/api/issues', { method: 'POST', body: JSON.stringify({
        title: row.title, severity: row.severity || 'low',
        list_gid: _listGid,
        owner_gid: window.top?._authUser?.gid || window._authUser?.gid || '',
      }) }).catch(e => console.error('[add-row issue]', e));
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
    const res = await ListShell._cf(`/api/issues${qs}`).catch(() => null);
    const _toTime = v => {
      if (!v) return 0;
      if (typeof v === 'number') return v;
      const d = new Date(v); return isNaN(d) ? 0 : d.getTime() / 1000;
    };
    let combined = (res?.data || [])
      .filter(i => (_currentList && !isNoList) ? i.list_gid === _currentList : true)
      .map(i => ({...i, _source: 'cloud'}))
      .sort((a,b) => _toTime(b.created_at) - _toTime(a.created_at));
    combined = ListShell.filterByList(combined, _currentList);
    _all = combined;
    await loadFollows();
    // 预加载已关联的 BOP 条目标题
    const linkedGids = [...new Set(_all.map(r => r.bop_entry_gid).filter(Boolean))];
    if (linkedGids.length) await _prefetchBopLabels(linkedGids);
    if (shell) shell.setRows(_all);
    setTimeout(() => _loadSapIndicators(_all.map(r => r.gid).filter(Boolean)), 0);
    // 若有待高亮条目，load 完毕后滚动到该行
    if (_pendingHighlightGid) {
      const g = _pendingHighlightGid;
      _pendingHighlightGid = null;
      _highlightRow(g);
    }
  } catch (e) {
    console.error('加载失败:', e);
  }
}

// ── 自我标注批量指示器 ─────────────────────────────────────────
async function _loadSapIndicators(gids) {
  if (!gids.length) return;
  for (let i = 0; i < gids.length; i += 500) {
    const chunk = gids.slice(i, i + 500);
    const res = await ListShell._cf(`/api/self_ann/batch?gids=${chunk.join(',')}`).catch(() => null);
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
  shell = new ListShell({
    mountEl:      document.getElementById('appRoot'),
    itemType:     'issue',
    moduleId:     'issue_list',
    columns:      ISSUE_COLS,
    title:        '问题管理',
    titleIcon:    '#icon-alert-circle',
    newLabel:     '新建条目',
    importExport: ListShell.makeImportExport('issue',
      () => (shell && shell.vm ? shell.vm.applyView(_all) : _all).filter(r => !r._isGroupHeader),
      async (rows, _fm, _c, signal) => {
        for (const r of rows) {
          if (signal?.aborted) break;
          await ListShell._cf('/api/issues', { method: 'POST', body: JSON.stringify({
            title: r.title || '导入问题',
            severity: r.severity || 'low',
            list_gid: shell?.currentListGid || null,
            owner_gid: window.top?._authUser?.gid || window._authUser?.gid || '',
          }), signal }).catch(e => console.error('[import issue]', e));
        }
        if (!signal?.aborted) await load();
      }),
    diffManager: ListShell.makeDiffManager('issue',
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
        return `<span class="issue-dot" style="background:${color}"></span>${ListShell._esc(val || '')}`;
      },
      status: (val) => {
        const color = STATUS_COLORS[val] || '#6c7086';
        return `<span class="status-badge" style="background:${color}22;color:${color}">${ListShell._esc(STATUS_LABEL[val]||val||'-')}</span>`;
      },
      severity: (val) => {
        if (!val) return '-';
        const bg = SEVERITY_COLOR[val] || 'transparent';
        return `<span class="sev-badge" style="background:${bg}">${ListShell._esc(SEVERITY_LABEL[val]||val)}</span>`;
      },
      share_scope: (val) => ListShell._esc(val || '-'),
      bop_entry_gid: (val, row) => {
        if (!val) return `<button class="btn-bop-link" data-gid="${row.gid||''}">+ 关联工序</button>`;
        const cached = _bopCache[val];
        const label = cached ? ListShell._esc(cached.title) : ListShell._esc(val);
        return `<span class="bop-entry-tag">${label}</span><button class="btn-bop-link btn-bop-edit" data-gid="${row.gid||''}" title="更换工序">…</button>`;
      },
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
        if (row._source !== 'cloud') return '';
        const followed = _followedMap.has(row.gid);
        return SubscribeButton.html(row.gid, followed, row.title, 'issue');
      },
    },
    onRowsChange:      _onRowsChange,
    onListsChange: (lists) => { _allLists = lists; },
    onSelect:      (gid) => { _currentList = gid; load(); },
    initListGid:   null,
  });
  await shell.init();

  // ── 分享到飞书群按钮 ──────────────────────────────────────────
  _addShareBtn();

  // 若初始化前已收到 ls:nav 消息，立即应用
  if (_pendingNavGid !== undefined) {
    shell.sidebar?._select(_pendingNavGid);
    _pendingNavGid = undefined;
  }


  if (window.FeishuMentionChip) FeishuMentionChip.bindClickDelegate(shell.grid._el);
  shell.grid._el.addEventListener('click', ev => {
    // FeishuMentionChip pick/edit buttons
    const fmBtn = ev.target.closest('.fm-pick-btn, .fm-edit-btn');
    if (fmBtn) {
      ev.stopPropagation();
      const gid   = fmBtn.dataset.gid;
      const field = fmBtn.dataset.field;
      const row   = _all.find(i => i.gid === gid);
      if (!row || !window.FeishuMentionChip) return;
      FeishuMentionChip.openPicker({
        mode: field === 'feishu_assignee' ? 'user' : 'group',
        onSelect: async (result) => {
          const patch = result.type === 'user'
            ? { feishu_assignee_open_id: result.open_id, feishu_assignee_name: result.name }
            : { feishu_group_chat_id: result.chat_id, feishu_group_name: result.name };
          await ListShell._cf(`/api/issues/${gid}`, { method: 'PUT', body: JSON.stringify(patch) })
            .catch(e => console.error('[fm patch issue]', e));
          Object.assign(row, patch);
          shell.setRows(_all);
        },
        onClear: async () => {
          const patch = field === 'feishu_assignee'
            ? { feishu_assignee_open_id: null, feishu_assignee_name: null }
            : { feishu_group_chat_id: null, feishu_group_name: null };
          await ListShell._cf(`/api/issues/${gid}`, { method: 'PUT', body: JSON.stringify(patch) })
            .catch(e => console.error('[fm clear issue]', e));
          Object.assign(row, patch);
          shell.setRows(_all);
        },
      });
      return;
    }
    const bopBtn = ev.target.closest('.btn-bop-link');
    if (bopBtn) {
      ev.stopPropagation();
      const row = _all.find(i => i.gid === bopBtn.dataset.gid);
      if (row) _linkBopEntry(row);
      return;
    }
    const sub = ev.target.closest('.sub-btn');
    if (!sub) return;
    ev.stopPropagation();
    const gid   = sub.dataset.gid;
    const row   = _all.find(i => i.gid === gid) || {};
    const state = _followedMap.get(gid) || { gid: null, conditions: [] };
    SubscribeButton.open(sub, {
      itemType: 'issue', itemGid: gid, itemTitle: row.title || gid,
      followed: _followedMap.has(gid),
      followGid: state.gid,
      conditions: state.conditions,
      cf: _cf,
      onSave: (newState) => {
        if (newState.followed) {
          _followedMap.set(gid, { gid: newState.followGid, conditions: newState.conditions });
        } else {
          _followedMap.delete(gid);
        }
        if (shell) shell.setRows(_all);
      },
    });
  });

  document.getElementById('bopPickerCancel')?.addEventListener('click', _closeBopPicker);
  document.getElementById('bopPickerMask')?.addEventListener('click', e => {
    if (e.target === e.currentTarget) _closeBopPicker();
  });

  await load();

  // 自我标注：保存后更新行指示器
  window.addEventListener('sap-saved', e => {
    document.querySelectorAll(`.sap-row-pin[data-gid="${e.detail.itemGid}"]`).forEach(el => {
      if (e.detail.status) el.dataset.status = e.detail.status;
      else delete el.dataset.status;
    });
  });

  // ── DataRegistry 注册 ──────────────────────────────────
  window.DataRegistry?.register('issue', {
    label: '问题管理', icon: 'icon-alert-circle',
    capabilities: ['local_sqlite', 'cloud_pg', 'data_promotion', 'at_mention', 'subscribe', 'grid_editor', 'view_manager', 'diff_manager'],
    getRows: () => _all,
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}

// ── 分享到飞书群 ───────────────────────────────────────────────

function _addShareBtn() {
  const toolbar = document.querySelector('#vmToolbar');
  if (!toolbar) return;
  const btn = document.createElement('button');
  btn.className = 'ls-btn ls-btn-secondary';
  btn.title = '分享到飞书群';
  btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg> 分享`;
  btn.addEventListener('click', _openShareModal);
  toolbar.appendChild(btn);
}

let _shareModal = null;
let _shareSearchTimer = null;
let _selectedChat = null;

function _openShareModal() {
  if (_shareModal) { _shareModal.remove(); _shareModal = null; }

  const listGid = shell?.currentListGid || '';
  const sidebar = shell?.sidebar;
  const listObj = sidebar?._lists?.find(l => l.gid === sidebar._selected);
  const listName = listObj?.name || '问题清单';
  const origin = window.location.origin || '';
  const shareUrl = `${origin}/share/issues?list_gid=${encodeURIComponent(listGid)}&list_name=${encodeURIComponent(listName)}`;

  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.style.cssText = 'position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,0.55);display:flex;align-items:center;justify-content:center';
  overlay.innerHTML = `
    <div class="modal-box" style="background:var(--bg-secondary,#181825);border:1px solid var(--border-default,#313244);border-radius:12px;padding:24px;min-width:400px;max-width:520px;box-shadow:0 8px 32px rgba(0,0,0,0.4)">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
        <h3 style="font-size:15px;font-weight:600;color:var(--text-primary,#cdd6f4)">分享到飞书群</h3>
        <button id="shareModalClose" style="background:none;border:none;cursor:pointer;color:var(--text-muted,#6c7086);font-size:18px;line-height:1">×</button>
      </div>
      <div style="margin-bottom:14px">
        <div style="font-size:12px;color:var(--text-muted,#6c7086);margin-bottom:4px">Web 链接（未安装 App 可访问）</div>
        <div style="display:flex;gap:6px">
          <input id="shareUrlInput" readonly value="${shareUrl}" style="flex:1;padding:6px 8px;border-radius:6px;border:1px solid var(--border-default,#313244);background:var(--bg-primary,#1e1e2e);color:var(--text-primary,#cdd6f4);font-size:12px;font-family:monospace">
          <button id="shareCopyBtn" class="ls-btn ls-btn-secondary" style="white-space:nowrap">复制</button>
        </div>
      </div>
      <div style="margin-bottom:6px">
        <div style="font-size:12px;color:var(--text-muted,#6c7086);margin-bottom:4px">选择飞书群</div>
        <input id="shareChatSearch" placeholder="搜索群名称…" autocomplete="off"
          style="width:100%;padding:7px 10px;border-radius:6px;border:1px solid var(--border-default,#313244);background:var(--bg-primary,#1e1e2e);color:var(--text-primary,#cdd6f4);font-size:13px;outline:none">
        <div id="shareChatDropdown" style="position:relative">
          <div id="shareChatList" style="display:none;position:absolute;top:2px;left:0;right:0;max-height:180px;overflow-y:auto;background:var(--bg-secondary,#181825);border:1px solid var(--border-default,#313244);border-radius:6px;z-index:10"></div>
        </div>
      </div>
      <div id="shareSelectedChat" style="display:none;margin-top:8px;padding:6px 10px;background:var(--bg-primary,#1e1e2e);border-radius:6px;font-size:13px;color:var(--text-primary,#cdd6f4)"></div>
      <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:18px">
        <button id="shareModalCancel" class="ls-btn ls-btn-secondary">取消</button>
        <button id="shareModalSend" class="ls-btn ls-btn-primary" disabled>发送到群</button>
      </div>
    </div>
  `;

  document.body.appendChild(overlay);
  _shareModal = overlay;
  _selectedChat = null;

  overlay.querySelector('#shareModalClose').onclick = _closeShareModal;
  overlay.querySelector('#shareModalCancel').onclick = _closeShareModal;
  overlay.addEventListener('click', e => { if (e.target === overlay) _closeShareModal(); });

  overlay.querySelector('#shareCopyBtn').onclick = () => {
    navigator.clipboard?.writeText(shareUrl).catch(() => {
      overlay.querySelector('#shareUrlInput').select();
      document.execCommand('copy');
    });
    const btn = overlay.querySelector('#shareCopyBtn');
    btn.textContent = '已复制';
    setTimeout(() => { btn.textContent = '复制'; }, 1500);
  };

  const searchInp = overlay.querySelector('#shareChatSearch');
  searchInp.addEventListener('input', () => {
    clearTimeout(_shareSearchTimer);
    _shareSearchTimer = setTimeout(() => _searchChats(searchInp.value.trim(), overlay), 400);
  });

  overlay.querySelector('#shareModalSend').onclick = () => _doShare(listName, shareUrl, overlay);
}

async function _searchChats(q, overlay) {
  const list = overlay.querySelector('#shareChatList');
  if (!q) { list.style.display = 'none'; return; }
  list.style.display = 'block';
  list.innerHTML = '<div style="padding:8px;color:var(--text-muted,#6c7086)">搜索中…</div>';
  try {
    const res = await ListShell._cf(`/feishu/search/chats?q=${encodeURIComponent(q)}&limit=8`);
    const chats = res?.data || [];
    if (!chats.length) {
      list.innerHTML = '<div style="padding:8px;color:var(--text-muted,#6c7086)">无匹配群聊</div>';
      return;
    }
    list.innerHTML = chats.map(c => `
      <div class="share-chat-item" data-chat-id="${c.chat_id||c.id||''}" data-chat-name="${(c.name||'').replace(/"/g,'&quot;')}"
        style="padding:8px 10px;cursor:pointer;border-bottom:1px solid var(--border-default,#313244)">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px;opacity:.6"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
        ${c.name||c.chat_id||''}
      </div>
    `).join('');
    list.querySelectorAll('.share-chat-item').forEach(el => {
      el.addEventListener('mouseenter', () => { el.style.background = 'var(--bg-primary,#1e1e2e)'; });
      el.addEventListener('mouseleave', () => { el.style.background = ''; });
      el.addEventListener('click', () => {
        _selectedChat = { chat_id: el.dataset.chatId, name: el.dataset.chatName };
        overlay.querySelector('#shareChatSearch').value = _selectedChat.name;
        list.style.display = 'none';
        const sel = overlay.querySelector('#shareSelectedChat');
        sel.style.display = 'block';
        sel.textContent = '已选择：' + _selectedChat.name;
        overlay.querySelector('#shareModalSend').disabled = false;
      });
    });
  } catch (e) {
    list.innerHTML = `<div style="padding:8px;color:var(--text-muted,#6c7086)">搜索失败</div>`;
  }
}

async function _doShare(listName, shareUrl, overlay) {
  if (!_selectedChat) return;
  const sendBtn = overlay.querySelector('#shareModalSend');
  sendBtn.disabled = true;
  sendBtn.textContent = '发送中…';
  try {
    await ListShell._cf('/feishu/chat-message/share-list', {
      method: 'POST',
      body: JSON.stringify({ chat_id: _selectedChat.chat_id, list_name: listName, share_url: shareUrl }),
    });
    sendBtn.textContent = '已发送';
    setTimeout(_closeShareModal, 800);
  } catch (e) {
    sendBtn.disabled = false;
    sendBtn.textContent = '发送到群';
    alert('发送失败：' + e.message);
  }
}

function _closeShareModal() {
  _shareModal?.remove();
  _shareModal = null;
  clearTimeout(_shareSearchTimer);
}
