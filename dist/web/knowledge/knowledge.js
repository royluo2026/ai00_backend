/**
 * 知识库前端脚本 — ListShell 版本
 */
'use strict';

// ── 列定义 ────────────────────────────────────────────────────────────────────
const KNOWLEDGE_COLS = [
  { key: 'display_id',  label: 'ID',      type: 'text',   width: 90,  editable: false },
  { key: 'title',       label: '标题',    type: 'text',   width: 240 },
  { key: 'entry_type',  label: '类型',    type: 'enum',   width: 100, options: [
    { value: 'guide',          label: '操作指南' },
    { value: 'rule_basis',     label: '规则依据' },
    { value: 'sim_spec',       label: '仿真规范' },
    { value: 'lesson_learned', label: '经验教训' },
  ]},
  { key: 'status',      label: '状态',    type: 'enum',   width: 80, options: [
    { value: 'draft',     label: '草稿' },
    { value: 'published', label: '已发布' },
    { value: 'archived',  label: '已归档' },
  ]},
  { key: 'tags',        label: '标签',    type: 'text',   width: 160 },
  { key: 'content_ref', label: '正文文档',type: 'text',   width: 120, editable: false },
  { key: '_actions',    label: '操作',    type: 'text',   width: 100, alwaysVisible: true, editable: false },
];

// ── 状态 ──────────────────────────────────────────────────────────────────────
let _shell       = null;
let _entries     = [];
let _allLists    = [];
let _currentList = null;

// ── 工具 ──────────────────────────────────────────────────────────────────────
const STATUS_MAP = { draft: '草稿', published: '已发布', archived: '已归档' };
const TYPE_MAP   = { guide: '操作指南', rule_basis: '规则依据', sim_spec: '仿真规范', lesson_learned: '经验教训' };

function _openContainerCard(row) {
  const p = window.parent || window;
  const params = { mode: 'row_detail', item_type: 'knowledge', gid: row.gid, source: row._source || 'local' };
  p.TabManager?.open?.('container_card', params);
}

function _openContentDoc(row) {
  if (!row?.content_ref) return;
  let ref = {};
  try { ref = typeof row.content_ref === 'string' ? JSON.parse(row.content_ref) : row.content_ref; } catch (_) {}
  const p = window.parent || window;
  if (ref.type === 'local_md' && ref.ref) {
    p.TabManager?.open?.('container_card', { mode: 'script', path: btoa(ref.ref), lang: 'markdown' });
  } else if (ref.type === 'feishu' && ref.ref) {
    p.TabManager?.open?.('container_card', { mode: 'webview', url: ref.ref });
  }
}

// ── 单元格渲染 ────────────────────────────────────────────────────────────────
const CELL_RENDERER = {
  status: (v) => `<span class="badge badge-${v||'draft'}">${STATUS_MAP[v]||v||'-'}</span>`,
  entry_type: (v) => TYPE_MAP[v] || v || '-',
  tags: (v) => {
    const arr = Array.isArray(v) ? v : (typeof v === 'string' && v ? v.split(',') : []);
    return arr.map(t => `<span class="tag-chip" style="font-size:11px">${t.trim()}</span>`).join(' ');
  },
  content_ref: (v) => {
    let ref = {};
    try { ref = typeof v === 'string' ? JSON.parse(v) : (v || {}); } catch (_) {}
    if (!ref.type || ref.type === 'none') return '<span style="color:var(--text-faint,#6c7086);font-size:11px">未关联</span>';
    const label = ref.type === 'local_md' ? 'MD 文档' : ref.type === 'feishu' ? '飞书文档' : ref.type;
    return `<button class="btn-open-content-ref btn-ghost" style="font-size:11px;padding:2px 6px">
      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:3px;vertical-align:-1px"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>${label}</button>`;
  },
  _actions: (_v, row) => {
    if (!row.gid) return '';
    return `<button class="btn-open-detail btn-ghost" data-gid="${row.gid}" style="font-size:11px;padding:2px 6px">
      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:3px;vertical-align:-1px"><path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>打开</button>`;
  },
};

// ── 上下文菜单 ────────────────────────────────────────────────────────────────
const EXTRA_CTX = (row) => [
  { label: '在新标签中打开详情', action: 'open_detail' },
  ...(row.content_ref && row.content_ref !== '{}' ? [{ label: '打开正文文档', action: 'open_content' }] : []),
];

// ── 数据加载 ──────────────────────────────────────────────────────────────────
const load = ListShell.buildLoadHandler({
  bridgeNs:         'knowledge',
  bridgeListMethod: 'list_entries',
  cloudPath:        '/api/knowledge_entries',
  getCurrentList:   () => _currentList,
  getAllLists:       () => _allLists,
  getShell:         () => _shell,
  setData:          (rows) => { _entries = rows; },
});

// ── 行变更处理 ────────────────────────────────────────────────────────────────
const _onRowsChange = ListShell.buildRowsChangeHandler({
  editableKeys:       ['title', 'entry_type', 'status', 'tags'],
  primaryKey:         'title',
  cloudUpdatePath:    (gid) => `/api/knowledge_entries/${gid}`,
  cloudCreatePath:    '/api/knowledge_entries',
  bridgeNs:           'knowledge',
  bridgeUpdateMethod: 'update_entry',
  bridgeCreateMethod: 'create_entry',
  buildCreateBody:    (row, canonGid) => ({
    title:      row.title,
    entry_type: row.entry_type || 'guide',
    list_gid:   canonGid,
  }),
  getData:        () => _entries,
  getCurrentList: () => _currentList,
  getAllLists:     () => _allLists,
  getShell:       () => _shell,
  load,
});

// ── 视图行（视图过滤/排序后的数据，供 IE/Diff 使用）────────────────────────
const _getViewRows = () => (_shell && _shell.vm ? _shell.vm.applyView(_entries) : _entries).filter(r => !r._isGroupHeader);

// ── 初始化 ────────────────────────────────────────────────────────────────────
async function init() {
  _shell = new ListShell({
    mountEl:           document.getElementById('appRoot'),
    itemType:          'knowledge',
    moduleId:          'knowledge',
    columns:           KNOWLEDGE_COLS,
    title:             '知识清单',
    titleIcon:         '#icon-knowledge',
    newLabel:          '新建条目',
    cellRenderer:      CELL_RENDERER,
    onRowsChange:      _onRowsChange,
    extraContextItems: EXTRA_CTX,
    onContextAction:   (action, row) => {
      if (action === 'open_detail') _openContainerCard(row);
      if (action === 'open_content') _openContentDoc(row);
    },
    rowClass: (row) => row._source === 'cloud' ? 'ge-row-cloud' : 'ge-row-local',
    onListsChange: (lists) => { _allLists = lists; },
    onSelect:      (gid) => { _currentList = gid; load(); },
    initListGid:   null,
    rdpSaveOpts:   { bridgeNs: 'knowledge', bridgeMethod: 'update_entry', cloudPath: '/api/knowledge_entries' },
    importExport: ListShell.makeImportExport('knowledge', _getViewRows, async (rows, _fm, _c, signal) => {
        for (const r of rows) {
          if (signal?.aborted) break;
          if (!r.title) continue;
          await ListShell._cf('/api/knowledge_entries', {
            method: 'POST',
            body: JSON.stringify({ title: r.title, entry_type: r.entry_type || 'guide', list_gid: _currentList || null }),
            signal,
          }).catch(e => console.error('[import knowledge]', e));
        }
        if (!signal?.aborted) await load();
      }),
    diffManager: ListShell.makeDiffManager('knowledge', _getViewRows, 'title'),
  });
  await _shell.init();

  // 按钮事件委托（grid 内的 btn-open-content-ref / btn-open-detail）
  _shell.grid._el.addEventListener('click', (ev) => {
    const contentBtn = ev.target.closest('.btn-open-content-ref');
    if (contentBtn) {
      const tr = contentBtn.closest('tr');
      const gid = tr?.dataset?.gid;
      const row = _entries.find(e => e.gid === gid);
      if (row) _openContentDoc(row);
      return;
    }
    const detailBtn = ev.target.closest('.btn-open-detail');
    if (detailBtn) {
      const row = _entries.find(e => e.gid === detailBtn.dataset.gid);
      if (row) _openContainerCard(row);
    }
  });

  // 主题同步由 list_shell.js 的 _lsInitTheme() IIFE 统一处理

  await load();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
