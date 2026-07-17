/**
 * my_files.js — 我的文件 主逻辑
 * 左侧：文件浏览器（分组/排序/搜索/收藏/关注）
 * 右侧：详情查看器（按 file_type 派发渲染引擎）
 */

/* ── 常量 ─────────────────────────────────────────── */

const LS_SIDEBAR_W  = 'mf:sidebar-w';
const LS_FAVORITES  = 'mf:favorites';
const LS_GROUP_BY   = 'mf:group-by';
const LS_SORT_BY    = 'mf:sort-by';

// 用当前登录用户 GID 作为 localStorage key 前缀，防止同机不同账户状态串用
const _MF_USER_GID = (() => {
  try { const u = window.parent?._authUser; return u?.gid || u?.user_gid || ''; } catch { return ''; }
})();
function _lsk(base) { return _MF_USER_GID ? `${_MF_USER_GID}:${base}` : base; }

const FILE_TYPE_META = {
  list_task:       { label: '任务清单',   domain: 'project', icon: 'task' },
  list_issue:      { label: '问题清单',   domain: 'project', icon: 'issue' },
  list_knowledge:  { label: '知识清单',   domain: 'knowledge', icon: 'knowledge' },
  list_rule:       { label: '规则清单',   domain: 'knowledge', icon: 'rule' },
  bop_version:     { label: 'BOP版本',    domain: 'craft',   icon: 'bop' },
  pbom:            { label: 'PBOM版本',   domain: 'craft',   icon: 'pbom' },
  doc_md:          { label: 'MD文档',     domain: 'knowledge', icon: 'md' },
  doc_richtext:    { label: '富文本文档', domain: 'knowledge', icon: 'richtext' },
  doc_url:         { label: '网页文件',   domain: 'knowledge', icon: 'url' },
  doc_weblink:     { label: '网络链接',   domain: 'knowledge', icon: 'weblink' },
  doc_site_page:   { label: '本站页面',   domain: 'knowledge', icon: 'site_page' },
  doc_pdf:         { label: 'PDF文件',    domain: 'knowledge', icon: 'pdf' },
  doc_image:       { label: '图片',       domain: 'knowledge', icon: 'image' },
  doc_spreadsheet: { label: '表格文件',   domain: 'knowledge', icon: 'spreadsheet' },
};

const DOMAIN_META = {
  craft:     { label: '工艺规划' },
  project:   { label: '项目管理' },
  knowledge: { label: '知识库' },
};

/* ── SVG 图标（按 icon key）─────────────────────────── */
function _typeIconSvg(iconKey) {
  const icons = {
    task:      '<polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/>',
    issue:     '<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>',
    knowledge: '<path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/>',
    rule:      '<path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z"/>',
    bop:       '<path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/>',
    pbom:      '<rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/>',
    md:        '<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="13" x2="15" y2="13"/><line x1="9" y1="17" x2="15" y2="17"/>',
    richtext:  '<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="9" y1="13" x2="15" y2="13"/>',
    url:       '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z"/>',
    pdf:        '<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><path d="M9 13h1.5a1.5 1.5 0 000-3H9v6"/>',
    image:      '<rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/>',
    spreadsheet:'<rect x="3" y="3" width="18" height="18" rx="1"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="3" y1="15" x2="21" y2="15"/><line x1="12" y1="3" x2="12" y2="21"/>',
    weblink:    '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z"/>',
    site_page:  '<rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/>',
  };
  const d = icons[iconKey] || icons.md;
  return `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${d}</svg>`;
}

/* ── 收藏 / 关注（localStorage）─────────────────────── */
function _loadFavorites() {
  try { return JSON.parse(localStorage.getItem(_lsk(LS_FAVORITES)) || '[]'); } catch { return []; }
}
function _saveFavorites(favs) {
  localStorage.setItem(_lsk(LS_FAVORITES), JSON.stringify(favs));
}
function _isFavorited(gid) {
  return _loadFavorites().some(f => f.gid === gid);
}
function _toggleFavorite(file) {
  let favs = _loadFavorites();
  if (favs.some(f => f.gid === file.gid)) {
    favs = favs.filter(f => f.gid !== file.gid);
  } else {
    favs.unshift({ gid: file.gid, file_type: file.file_type, title: file.title });
  }
  _saveFavorites(favs);
}

/* ── cloudFetch helper ───────────────────────────────── */
function _cf(path, opts) {
  const fn = window.parent?._cloudFetch || window._cloudFetch;
  if (!fn) return Promise.reject(new Error('_cloudFetch not available'));
  return fn(path, opts);
}

/* ── 时间分组辅助 ────────────────────────────────────── */
function _timeGroup(dateStr) {
  if (!dateStr) return '更早';
  const d = new Date(dateStr);
  const now = new Date();
  const diffMs = now - d;
  const diffDays = diffMs / 86400000;
  if (diffDays < 1)  return '今天';
  if (diffDays < 7)  return '本周';
  if (diffDays < 30) return '本月';
  return '更早';
}

/* ── 状态 ────────────────────────────────────────────── */
let _allFiles  = [];      // FileItem[]
let _activeGid = null;    // 当前选中文件的 gid
let _collapsed = {};      // 分组折叠状态 { groupKey: bool }

/* ── 数据加载 ────────────────────────────────────────── */
async function _loadFiles() {
  const listEl = document.getElementById('mfFileList');
  listEl.innerHTML = '<div class="mf-loading">加载中…</div>';

  try {
    const [listsRes, bopRes, knowledgeRes] = await Promise.allSettled([
      _cf('/api/lists'),
      _cf('/api/bop/versions'),
      _cf('/api/knowledge_hub/items'),
    ]);

    const files = [];

    // ── lists → list_task / list_issue / list_knowledge / list_rule
    if (listsRes.status === 'fulfilled') {
      const rows = listsRes.value?.lists || listsRes.value?.data || listsRes.value || [];
      for (const r of rows) {
        const itype = r.item_type || 'task';
        const fileType = `list_${itype}`;
        if (!FILE_TYPE_META[fileType]) continue;
        files.push({
          file_type:   fileType,
          gid:         r.gid,
          title:       r.name || r.title || '(无标题)',
          domain:      FILE_TYPE_META[fileType].domain,
          updated_at:  r.updated_at || r.created_at || null,
          meta:        r,
        });
      }
    }

    // ── bop/versions → bop_version
    if (bopRes.status === 'fulfilled') {
      const rows = bopRes.value?.versions || bopRes.value?.data || bopRes.value || [];
      for (const r of rows) {
        files.push({
          file_type:   'bop_version',
          gid:         r.gid,
          title:       r.bop_name || r.name || r.version_name || '(无标题)',
          domain:      'craft',
          updated_at:  r.updated_at || null,
          meta:        r,
        });
      }
    }

    // ── knowledge_hub/items → doc_md / doc_richtext / doc_url / doc_pdf
    if (knowledgeRes.status === 'fulfilled') {
      const rows = knowledgeRes.value?.items || knowledgeRes.value?.data || knowledgeRes.value || [];
      for (const r of rows) {
        const typeMap = {
          markdown: 'doc_md', md: 'doc_md',
          richtext: 'doc_richtext',
          url: 'doc_url',
          weblink: 'doc_weblink',
          site_page: 'doc_site_page',
          pdf: 'doc_pdf',
          image: 'doc_image',
          spreadsheet: 'doc_spreadsheet',
        };
        const fileType = typeMap[r.item_type] || 'doc_richtext';
        files.push({
          file_type:   fileType,
          gid:         r.gid,
          title:       r.title || r.name || '(无标题)',
          domain:      'knowledge',
          updated_at:  r.updated_at || null,
          meta:        r,
        });
      }
    }

    _allFiles = files;
    _renderList();
  } catch (err) {
    listEl.innerHTML = `<div class="mf-empty">加载失败：${err.message}</div>`;
  }
}

/* ── 渲染文件列表 ─────────────────────────────────────── */
function _renderList() {
  const listEl = document.getElementById('mfFileList');
  const groupBy = document.getElementById('mfGroupBy')?.value || 'domain';
  const sortBy  = document.getElementById('mfSortBy')?.value  || 'updated_at';
  const q       = (document.getElementById('mfSearch')?.value || '').toLowerCase().trim();

  // 过滤
  let files = _allFiles.filter(f => !q || f.title.toLowerCase().includes(q));

  // 排序
  files.sort((a, b) => {
    if (sortBy === 'title') return a.title.localeCompare(b.title, 'zh-CN');
    const ta = a.updated_at ? new Date(a.updated_at).getTime() : 0;
    const tb = b.updated_at ? new Date(b.updated_at).getTime() : 0;
    return tb - ta;
  });

  if (files.length === 0) {
    listEl.innerHTML = '<div class="mf-empty">暂无文件</div>';
    return;
  }

  // 分组
  const groups = new Map();
  for (const f of files) {
    let key;
    if (groupBy === 'domain') {
      key = f.domain || 'other';
    } else if (groupBy === 'type') {
      key = f.file_type;
    } else {
      key = _timeGroup(f.updated_at);
    }
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(f);
  }

  // 排序分组 key（域：按预设顺序；时间：今天/本周/本月/更早；类型：按 label）
  const domainOrder = ['craft', 'project', 'knowledge', 'other'];
  const timeOrder   = ['今天', '本周', '本月', '更早'];
  let sortedKeys;
  if (groupBy === 'domain') {
    sortedKeys = [...groups.keys()].sort((a, b) => {
      const ia = domainOrder.indexOf(a), ib = domainOrder.indexOf(b);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
    });
  } else if (groupBy === 'time') {
    sortedKeys = [...groups.keys()].sort((a, b) => {
      return timeOrder.indexOf(a) - timeOrder.indexOf(b);
    });
  } else {
    sortedKeys = [...groups.keys()].sort();
  }

  const frag = document.createDocumentFragment();

  for (const key of sortedKeys) {
    const items = groups.get(key);
    let groupLabel = key;
    if (groupBy === 'domain') groupLabel = DOMAIN_META[key]?.label || key;
    if (groupBy === 'type')   groupLabel = FILE_TYPE_META[key]?.label || key;

    // 分组标题
    const collapsed = !!_collapsed[key];
    const hdr = document.createElement('div');
    hdr.className = 'mf-group-header' + (collapsed ? ' collapsed' : '');
    hdr.dataset.group = key;
    hdr.innerHTML = `<svg viewBox="0 0 10 10" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><polyline points="2,3 5,7 8,3"/></svg>${groupLabel} <span style="color:var(--text-faint,#585b70);font-weight:400;margin-left:2px">(${items.length})</span>`;
    hdr.addEventListener('click', () => {
      _collapsed[key] = !_collapsed[key];
      _renderList();
    });
    frag.appendChild(hdr);

    const body = document.createElement('div');
    body.className = 'mf-group-body' + (collapsed ? ' collapsed' : '');

    for (const file of items) {
      body.appendChild(_buildFileRow(file));
    }
    frag.appendChild(body);
  }

  listEl.innerHTML = '';
  listEl.appendChild(frag);
}

/* ── 构建单行 ─────────────────────────────────────────── */
function _buildFileRow(file) {
  const meta = FILE_TYPE_META[file.file_type] || {};
  const isActive = file.gid === _activeGid;
  const isFav = _isFavorited(file.gid);

  const row = document.createElement('div');
  row.className = 'mf-file-row' + (isActive ? ' active' : '');
  row.dataset.gid  = file.gid;
  row.dataset.type = file.file_type;
  row.title = file.title;

  row.innerHTML = `
    <span class="mf-file-icon">${_typeIconSvg(meta.icon || 'md')}</span>
    ${window.VisibilitySelector ? VisibilitySelector.renderBadge(file.visibility || file.scope_type || 'team') : ''}
    <span class="mf-file-name">${_escHtml(file.title)}</span>
    <span class="mf-file-actions">
      <button class="mf-fav-btn${isFav ? ' active' : ''}" title="${isFav ? '取消收藏' : '收藏'}">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="${isFav ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="1.8">
          <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
        </svg>
      </button>
    </span>`;

  // 点击行 → 打开文件
  row.addEventListener('click', e => {
    if (e.target.closest('.mf-file-actions')) return;
    _openFile(file);
  });

  // 收藏按钮
  row.querySelector('.mf-fav-btn').addEventListener('click', e => {
    e.stopPropagation();
    _toggleFavorite(file);
    _renderList();
  });

  return row;
}

function _escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// 将平铺文件夹数组构建为带缩进的 <option> 字符串（树形 DFS，含个人及子文件夹）
function _buildFolderOptions(folders) {
  const childMap = {};
  const roots = [];
  for (const f of folders) {
    if (f.parent_gid) {
      (childMap[f.parent_gid] = childMap[f.parent_gid] || []).push(f);
    } else {
      roots.push(f);
    }
  }
  const sort = arr => arr.slice().sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || (a.name || '').localeCompare(b.name || ''));
  let html = '<option value="">— 根目录 —</option>';
  function walk(node, depth) {
    const pad = '\u00a0\u00a0'.repeat(depth);
    html += `<option value="${node.gid}">${pad}${_escHtml(node.name)}</option>`;
    for (const child of sort(childMap[node.gid] || [])) walk(child, depth + 1);
  }
  for (const root of sort(roots)) walk(root, 0);
  return html;
}

/* ── 渲染引擎派发 ─────────────────────────────────────── */

// 每种文件类型对应的渲染函数
const VIEWER_RENDERERS = {
  list_task:       f => _renderTreeList(f, 'task'),
  list_issue:      f => _renderTreeList(f, 'issue'),
  list_knowledge:  f => _renderTreeList(f, 'knowledge'),
  list_rule:       f => _renderTreeList(f, 'rule'),
  bop_version:     f => _renderIframe(f, `../lineage_view/index.html?version_gid=${f.gid}`),
  pbom:            f => _renderIframe(f, `../ebom/ebom.html?pbom_gid=${f.gid}`),
  doc_md:          f => _renderContainerCard(f, 'markdown'),
  doc_richtext:    f => _renderContainerCard(f, 'richtext'),
  doc_url:         f => _renderContainerCard(f, 'webview', { url: f.meta?.url }),
  doc_weblink:     f => _renderContainerCard(f, 'webview', { url: f.meta?.url }),
  doc_site_page:   f => {
    const ref = typeof f.meta?.site_ref === 'string'
      ? JSON.parse(f.meta?.site_ref || '{}') : (f.meta?.site_ref || {});
    const path = ref?.path || f.meta?.file_path || '';
    _renderIframe(f, path ? `../${path}` : 'about:blank');
  },
  doc_pdf:         f => _renderContainerCard(f, 'pdf', { path: f.meta?.file_path }),
  doc_image:       f => _renderContainerCard(f, 'image_gallery'),
  doc_spreadsheet: f => _renderContainerCard(f, 'webview'),
};

function _openFile(file) {
  _activeGid = file.gid;
  _renderList(); // 更新选中高亮

  const renderer = VIEWER_RENDERERS[file.file_type];
  if (renderer) {
    renderer(file);
  } else {
    _showViewerEmpty('不支持的文件类型：' + file.file_type);
  }
}

function _renderTreeList(file, itemType) {
  const pageMap = {
    task:      '../task/index.html',
    issue:     '../issue/index.html',
    knowledge: '../knowledge/knowledge.html',
    rule:      '../rule_mgmt/rule_mgmt.html',
  };
  const src = `${pageMap[itemType]}?list_gid=${file.gid}`;
  _setViewerIframe(file, src);
}

function _renderIframe(file, src) {
  _setViewerIframe(file, src);
}

function _renderContainerCard(file, mode, extra = {}) {
  let src = `../container_card/index.html?mode=${mode}`;
  if (file.gid) src += `&item_gid=${file.gid}`;
  if (extra.url)  src += `&url=${encodeURIComponent(extra.url)}`;
  if (extra.path) src += `&path=${encodeURIComponent(extra.path)}`;
  _setViewerIframe(file, src);
}

function _setViewerIframe(file, src) {
  const viewer = document.getElementById('mfViewer');
  const meta   = FILE_TYPE_META[file.file_type] || {};

  // 构建头栏 + iframe
  viewer.innerHTML = `
    <div class="mf-viewer-hdr">
      <span class="mf-viewer-hdr-type">${meta.label || file.file_type}</span>
      <span class="mf-viewer-hdr-title">${_escHtml(file.title)}</span>
    </div>
    <iframe src="${src}" allowfullscreen></iframe>`;

  // 将主题同步给 iframe
  const iframe = viewer.querySelector('iframe');
  iframe.addEventListener('load', () => {
    const theme = document.documentElement.dataset.theme || document.body.dataset.theme || 'dark';
    try {
      iframe.contentWindow.postMessage({ type: 'theme', theme }, '*');
    } catch (_) {}
  });
}

function _showViewerEmpty(msg) {
  const viewer = document.getElementById('mfViewer');
  viewer.innerHTML = `<div class="mf-viewer-empty"><span>${_escHtml(msg)}</span></div>`;
}

/* ── 可拖拽分割条 ─────────────────────────────────────── */
function _initSplitter() {
  const splitter = document.getElementById('mfSplitter');
  const sidebar  = document.getElementById('mfSidebar');
  if (!splitter || !sidebar) return;

  // 恢复保存的宽度
  const saved = parseInt(localStorage.getItem(_lsk(LS_SIDEBAR_W)) || '260', 10);
  sidebar.style.width = Math.max(180, Math.min(480, saved)) + 'px';

  let dragging = false, startX = 0, startW = 0;

  splitter.addEventListener('mousedown', e => {
    dragging = true;
    startX = e.clientX;
    startW = sidebar.offsetWidth;
    splitter.classList.add('dragging');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    e.preventDefault();
  });

  document.addEventListener('mousemove', e => {
    if (!dragging) return;
    const newW = Math.max(180, Math.min(480, startW + e.clientX - startX));
    sidebar.style.width = newW + 'px';
  });

  document.addEventListener('mouseup', () => {
    if (!dragging) return;
    dragging = false;
    splitter.classList.remove('dragging');
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
    localStorage.setItem(_lsk(LS_SIDEBAR_W), String(sidebar.offsetWidth));
  });

  // 双击重置 260px
  splitter.addEventListener('dblclick', () => {
    sidebar.style.width = '260px';
    localStorage.setItem(_lsk(LS_SIDEBAR_W), '260');
  });
}

/* ── 工具栏事件 ───────────────────────────────────────── */
function _initToolbar() {
  const groupEl = document.getElementById('mfGroupBy');
  const sortEl  = document.getElementById('mfSortBy');
  const searchEl = document.getElementById('mfSearch');

  // 恢复 localStorage 偏好
  const savedGroup = localStorage.getItem(_lsk(LS_GROUP_BY));
  const savedSort  = localStorage.getItem(_lsk(LS_SORT_BY));
  if (savedGroup && groupEl) groupEl.value = savedGroup;
  if (savedSort  && sortEl)  sortEl.value  = savedSort;

  groupEl?.addEventListener('change', () => {
    localStorage.setItem(_lsk(LS_GROUP_BY), groupEl.value);
    _renderList();
  });

  sortEl?.addEventListener('change', () => {
    localStorage.setItem(_lsk(LS_SORT_BY), sortEl.value);
    _renderList();
  });

  let _searchTimer = null;
  searchEl?.addEventListener('input', () => {
    clearTimeout(_searchTimer);
    _searchTimer = setTimeout(() => _renderList(), 150);
  });

  // ── ＋ 按钮：显示/隐藏 type picker
  const btnNew = document.getElementById('mfBtnNew');
  btnNew?.addEventListener('click', e => {
    const picker = document.getElementById('mfTypePicker');
    picker.hidden = !picker.hidden;
    if (!picker.hidden) {
      const r = btnNew.getBoundingClientRect();
      picker.style.top  = (r.bottom + 4) + 'px';
      picker.style.left = Math.max(4, r.right - 180) + 'px';
    }
    e.stopPropagation();
  });

  // click-outside 关闭 popover
  document.addEventListener('click', () => {
    const picker = document.getElementById('mfTypePicker');
    if (picker) picker.hidden = true;
  });

  // modal 关闭
  document.getElementById('mfModalClose')?.addEventListener('click', _closeModal);
  document.getElementById('mfModalCancel')?.addEventListener('click', _closeModal);
  document.getElementById('mfModalOverlay')?.addEventListener('click', e => {
    if (e.target.id === 'mfModalOverlay') _closeModal();
  });
  document.getElementById('mfModalSubmit')?.addEventListener('click', _handleSubmit);

  // 可见范围按钮组（事件委托）
  document.addEventListener('click', e => {
    const btn = e.target.closest('.mf-scope-btn');
    if (!btn) return;
    const group = btn.closest('.mf-scope-btns');
    if (!group) return;
    group.querySelectorAll('.mf-scope-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const body = document.getElementById('mfModalBody');
    const hiddenVis = body?.querySelector('#mfFormVisibility');
    const hiddenScope = body?.querySelector('#mfFormScopeType');
    if (hiddenVis) hiddenVis.value = btn.dataset.value;
    if (hiddenScope) hiddenScope.value = btn.dataset.value;
    // 项目可见范围：展示/隐藏项目选择器
    const projectRow = body?.querySelector('#mfFormProjectRow');
    if (projectRow) projectRow.style.display = btn.dataset.value === 'project' ? '' : 'none';
  });

  // 渲染 type picker（只需一次）
  _renderTypePicker();
}

/* ── 新建文件常量 ────────────────────────────────────── */
const COLOR_PRESETS = ['#5b8dee', '#22c55e', '#ef4444', '#f97316', '#8b5cf6', '#6b7280'];

const TYPE_BY_DOMAIN = {
  craft:     ['bop_version', 'pbom'],
  project:   ['list_task', 'list_issue'],
  knowledge: ['list_knowledge', 'list_rule', 'doc_md', 'doc_richtext', 'doc_url', 'doc_pdf'],
};

/* ── Type Picker ─────────────────────────────────────── */
function _renderTypePicker() {
  const el = document.getElementById('mfTypePicker');
  if (!el) return;
  let html = '';
  for (const [domain, types] of Object.entries(TYPE_BY_DOMAIN)) {
    html += `<div class="mf-tp-label">${DOMAIN_META[domain].label}</div>`;
    for (const ft of types) {
      const meta = FILE_TYPE_META[ft];
      html += `<button class="mf-tp-item" data-type="${ft}">
        <span class="mf-tp-icon">${_typeIconSvg(meta.icon)}</span>
        <span>${meta.label}</span>
      </button>`;
    }
  }
  el.innerHTML = html;
  el.addEventListener('click', e => {
    const btn = e.target.closest('.mf-tp-item');
    if (!btn) return;
    e.stopPropagation();
    el.hidden = true;
    _openCreateModal(btn.dataset.type);
  });
}

/* ── Modal 开关 ──────────────────────────────────────── */
let _currentCreateType = null;

function _closeModal() {
  document.getElementById('mfModalOverlay').hidden = true;
  _currentCreateType = null;
}

async function _openCreateModal(fileType) {
  _currentCreateType = fileType;
  const meta = FILE_TYPE_META[fileType] || {};

  document.getElementById('mfModalIcon').innerHTML = _typeIconSvg(meta.icon || 'md');
  document.getElementById('mfModalTitle').textContent = '新建 ' + (meta.label || fileType);
  document.getElementById('mfModalBody').innerHTML = _buildForm(fileType);
  document.getElementById('mfModalOverlay').hidden = false;
  document.getElementById('mfModalSubmit').disabled = false;
  document.getElementById('mfModalSubmit').textContent = '创建';

  // ── 模式切换 tab（BOP/PBOM）
  document.querySelectorAll('.mf-mode-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      const container = tab.closest('.mf-mode-tabs');
      container.querySelectorAll('.mf-mode-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      const prefix = fileType === 'bop_version' ? 'mfBopPanel' : 'mfPbomPanel';
      document.querySelectorAll('[id^="' + prefix + '"]').forEach(p => { p.hidden = true; });
      const modeKey = tab.dataset.mode;
      const panelId = prefix + modeKey.charAt(0).toUpperCase() + modeKey.slice(1);
      const panel = document.getElementById(panelId);
      if (panel) panel.hidden = false;
    });
  });

  // ── 异步加载下拉数据（并发）
  const needProjects = fileType.startsWith('list_') || fileType === 'bop_version';
  const needFolders  = fileType.startsWith('doc_');
  const needVersions = fileType === 'bop_version';

  const [projRes, folderRes, verRes] = await Promise.allSettled([
    needProjects ? _cf('/api/projects') : Promise.resolve(null),
    needFolders  ? _cf('/api/knowledge_hub/folders') : Promise.resolve(null),
    needVersions ? _cf('/api/bop/versions') : Promise.resolve(null),
  ]);

  if (needProjects && projRes.status === 'fulfilled') {
    const projects = projRes.value?.data || projRes.value?.projects || projRes.value || [];
    const arr = Array.isArray(projects) ? projects : [];
    const opts = '<option value="">— 不关联项目 —</option>' +
      arr.map(p => `<option value="${p.gid}">${_escHtml(p.name)}</option>`).join('');
    document.querySelectorAll('.mf-proj-select').forEach(sel => { sel.innerHTML = opts; });
  }

  if (needFolders && folderRes.status === 'fulfilled') {
    const folders = folderRes.value?.data || folderRes.value?.folders || folderRes.value || [];
    const arr = Array.isArray(folders) ? folders : [];
    document.querySelectorAll('.mf-folder-select').forEach(sel => { sel.innerHTML = _buildFolderOptions(arr); });
  }

  if (needVersions && verRes.status === 'fulfilled') {
    const versions = verRes.value?.data || verRes.value?.versions || verRes.value || [];
    const arr = Array.isArray(versions) ? versions : [];
    const opts = '<option value="">— 选择源版本 —</option>' +
      arr.map(v => `<option value="${v.gid}">${_escHtml((v.bop_name || '') + ' ' + (v.version_tag || ''))}</option>`).join('');
    ['mfFormForkSrc', 'mfFormSmartSrc'].forEach(selId => {
      const sel = document.getElementById(selId);
      if (sel) sel.innerHTML = opts;
    });
  }

  // PBOM "前往EBOM"
  document.getElementById('mfPbomGotoEbom')?.addEventListener('click', () => {
    _closeModal();
    window.parent?.postMessage({ type: 'nav:open', tabId: 'ebom' }, '*');
  });

  // PDF 文件选择（Electron dialog）
  document.getElementById('mfFormFilePickBtn')?.addEventListener('click', async () => {
    let path = null;
    if (window.parent?.electronAPI?.showOpenDialog) {
      const result = await window.parent.electronAPI.showOpenDialog({
        properties: ['openFile'], filters: [{ name: 'PDF', extensions: ['pdf'] }],
      });
      path = result?.filePaths?.[0];
    }
    if (path) document.getElementById('mfFormFilePath').value = path;
  });

  // 颜色选择器
  document.getElementById('mfColorPicker')?.addEventListener('click', e => {
    const swatch = e.target.closest('.mf-color-swatch');
    if (!swatch) return;
    document.querySelectorAll('.mf-color-swatch').forEach(s => s.classList.remove('selected'));
    swatch.classList.add('selected');
    const colorInput = document.getElementById('mfFormColor');
    const nativeInput = document.getElementById('mfColorNative');
    if (colorInput) colorInput.value = swatch.dataset.color;
    if (nativeInput) nativeInput.value = swatch.dataset.color;
  });
  document.getElementById('mfColorNative')?.addEventListener('input', e => {
    document.querySelectorAll('.mf-color-swatch').forEach(s => s.classList.remove('selected'));
    const colorInput = document.getElementById('mfFormColor');
    if (colorInput) colorInput.value = e.target.value;
  });

  // 聚焦第一个 input
  setTimeout(() => document.querySelector('#mfModalBody input:not([type="hidden"]):not([type="color"])')?.focus(), 50);

  // 初始化 VisibilitySelector（清单 or 文档）
  if (window.VisibilitySelector) {
    const listMount = document.getElementById('mfVisMount_list');
    const docMount  = document.getElementById('mfVisMount_doc');
    if (listMount) VisibilitySelector.renderWidget(listMount, { initialVisibility: 'team', onChange: () => {
      const val = VisibilitySelector.getValue(listMount);
      const hid = document.getElementById('mfFormVisibility');
      if (hid) hid.value = val.visibility;
      listMount._vsTeamGid    = val.shared_team_gid;
      listMount._vsProjGid    = val.shared_project_gid;
    }});
    if (docMount)  VisibilitySelector.renderWidget(docMount,  { initialVisibility: 'public', onChange: () => {
      const val = VisibilitySelector.getValue(docMount);
      const hid = document.getElementById('mfFormScopeType');
      if (hid) hid.value = val.visibility === 'private' ? 'personal' : val.visibility;
      docMount._vsTeamGid  = val.shared_team_gid;
      docMount._vsProjGid  = val.shared_project_gid;
    }});
  }
}

/* ── 表单构建器 ──────────────────────────────────────── */
function _buildForm(fileType) {
  if (fileType.startsWith('list_')) return _buildFormList(fileType.replace('list_', ''));
  if (fileType === 'bop_version')  return _buildFormBop();
  if (fileType === 'pbom')         return _buildFormPbom();
  if (fileType.startsWith('doc_')) return _buildFormDoc(fileType);
  return '<p>不支持的类型</p>';
}

function _buildFormList(itemType) {
  const colorSwatches = COLOR_PRESETS.map((c, i) =>
    `<span class="mf-color-swatch${i === 0 ? ' selected' : ''}" data-color="${c}" style="background:${c}" title="${c}"></span>`
  ).join('');
  const hasProject = (itemType === 'task' || itemType === 'issue');
  const projRow = `
    <div id="mfFormProjectRow" style="display:none">
      <label class="mf-form-label" style="margin-top:12px">关联项目 <span style="color:#ef4444">*</span></label>
      <select class="mf-form-input mf-proj-select" id="mfFormProject">
        <option value="">— 加载中… —</option>
      </select>
    </div>`;
  return `
    <label class="mf-form-label">清单名称 <span style="color:#ef4444">*</span></label>
    <input class="mf-form-input" id="mfFormName" type="text" placeholder="输入清单名称…" autocomplete="off">
    <label class="mf-form-label" style="margin-top:12px">颜色</label>
    <div class="mf-color-picker" id="mfColorPicker">
      ${colorSwatches}
      <input class="mf-color-native" id="mfColorNative" type="color" value="${COLOR_PRESETS[0]}" title="自定义颜色">
    </div>
    <input type="hidden" id="mfFormColor" value="${COLOR_PRESETS[0]}">
    ${projRow}
    <label class="mf-form-label" style="margin-top:12px">可见范围</label>
    <div id="mfVisMount_list"></div>
    <input type="hidden" id="mfFormVisibility" value="team">`;
}

function _buildFormBop() {
  return `
    <div class="mf-mode-tabs" id="mfBopModeTabs">
      <button class="mf-mode-tab active" data-mode="blank">空白新建</button>
      <button class="mf-mode-tab" data-mode="fork">Fork 现有版本</button>
      <button class="mf-mode-tab" data-mode="smart">Smart Fork</button>
    </div>
    <div class="mf-mode-panel" id="mfBopPanelBlank">
      <label class="mf-form-label">版本标签 <span style="color:#ef4444">*</span></label>
      <input class="mf-form-input" id="mfFormVersionTag" type="text" placeholder="例：V1.0" autocomplete="off">
      <label class="mf-form-label" style="margin-top:12px">BOP 名称</label>
      <input class="mf-form-input" id="mfFormBopName" type="text" placeholder="例：X11总装整车BOP（可选）" autocomplete="off">
      <label class="mf-form-label" style="margin-top:12px">关联项目（可选）</label>
      <select class="mf-form-input mf-proj-select" id="mfFormBopProject">
        <option value="">— 加载中… —</option>
      </select>
      <label class="mf-form-label" style="margin-top:12px">节拍时间（秒）</label>
      <input class="mf-form-input" id="mfFormTaktTime" type="number" value="60" min="1">
    </div>
    <div class="mf-mode-panel" id="mfBopPanelFork" hidden>
      <label class="mf-form-label">源版本 <span style="color:#ef4444">*</span></label>
      <select class="mf-form-input" id="mfFormForkSrc">
        <option value="">— 加载中… —</option>
      </select>
      <label class="mf-form-label" style="margin-top:12px">新版本标签 <span style="color:#ef4444">*</span></label>
      <input class="mf-form-input" id="mfFormForkTag" type="text" placeholder="例：V2.0" autocomplete="off">
      <label class="mf-form-label" style="margin-top:12px">新 BOP 名称（可选）</label>
      <input class="mf-form-input" id="mfFormForkBopName" type="text" placeholder="留空则继承源版本名称">
      <label class="mf-form-label" style="margin-top:12px">变更说明（可选）</label>
      <input class="mf-form-input" id="mfFormForkNote" type="text" placeholder="简要说明变更原因">
    </div>
    <div class="mf-mode-panel" id="mfBopPanelSmart" hidden>
      <label class="mf-form-label">源版本 <span style="color:#ef4444">*</span></label>
      <select class="mf-form-input" id="mfFormSmartSrc">
        <option value="">— 加载中… —</option>
      </select>
      <label class="mf-form-label" style="margin-top:12px">创建模式 <span style="color:#ef4444">*</span></label>
      <select class="mf-form-input" id="mfFormSmartMode">
        <option value="minor_facelift">小改款（保留结构，替换变更零件工序）</option>
        <option value="new_model">新车型（仅保留线体/工位框架）</option>
      </select>
      <label class="mf-form-label" style="margin-top:12px">新版本标签 <span style="color:#ef4444">*</span></label>
      <input class="mf-form-input" id="mfFormSmartTag" type="text" placeholder="例：V3.0_NewModel" autocomplete="off">
    </div>`;
}

function _buildFormPbom() {
  return `
    <div class="mf-mode-tabs" id="mfPbomModeTabs">
      <button class="mf-mode-tab active" data-mode="blank">空白新建</button>
      <button class="mf-mode-tab" data-mode="import">Excel 导入</button>
    </div>
    <div class="mf-mode-panel" id="mfPbomPanelBlank">
      <label class="mf-form-label">版本名称 <span style="color:#ef4444">*</span></label>
      <input class="mf-form-input" id="mfFormPbomName" type="text" placeholder="例：X11-PBOM-V1" autocomplete="off">
    </div>
    <div class="mf-mode-panel" id="mfPbomPanelImport" hidden>
      <div style="padding:12px 0; color:var(--text-muted); font-size:12.5px; line-height:1.6">
        Excel 导入需要进行列字段映射，流程较复杂。<br>
        点击下方按钮前往 EBOM 页面完成导入。
      </div>
      <button class="mf-btn-secondary" id="mfPbomGotoEbom" style="width:100%;margin-top:4px">
        前往 EBOM 页面导入 →
      </button>
    </div>`;
}

function _buildFormDoc(fileType) {
  let extra = '';
  if (fileType === 'doc_url') {
    extra = `
      <label class="mf-form-label" style="margin-top:12px">URL <span style="color:#ef4444">*</span></label>
      <input class="mf-form-input" id="mfFormUrl" type="url" placeholder="https://…">
      <p style="margin:4px 0 0;font-size:11px;color:var(--text-faint)">标题留空时自动使用网页域名</p>`;
  } else if (fileType === 'doc_pdf') {
    extra = `
      <label class="mf-form-label" style="margin-top:12px">文件路径 <span style="color:#ef4444">*</span></label>
      <div style="display:flex;gap:6px">
        <input class="mf-form-input" id="mfFormFilePath" type="text" placeholder="选择本地 PDF 文件…" readonly style="flex:1">
        <button class="mf-btn-secondary" id="mfFormFilePickBtn" style="flex-shrink:0;padding:4px 10px">选择…</button>
      </div>`;
  } else if (fileType === 'doc_md') {
    extra = `
      <label class="mf-form-label" style="margin-top:12px">初始内容（可选）</label>
      <textarea class="mf-form-input mf-form-textarea" id="mfFormContent" placeholder="支持 Markdown…" rows="4"></textarea>`;
  }
  const isUrl = fileType === 'doc_url';
  const titleLabel = isUrl ? '标题（可选）' : '标题 <span style="color:#ef4444">*</span>';
  return `
    <label class="mf-form-label">${titleLabel}</label>
    <input class="mf-form-input" id="mfFormTitle" type="text" placeholder="输入文档标题…" autocomplete="off">
    ${extra}
    <label class="mf-form-label" style="margin-top:12px">文件夹（可选）</label>
    <select class="mf-form-input mf-folder-select" id="mfFormFolder">
      <option value="">— 加载中… —</option>
    </select>
    <label class="mf-form-label" style="margin-top:12px">可见范围</label>
    <div id="mfVisMount_doc"></div>
    <input type="hidden" id="mfFormScopeType" value="public">`;
}

/* ── 提交处理 ────────────────────────────────────────── */
async function _handleSubmit() {
  const submitBtn = document.getElementById('mfModalSubmit');
  submitBtn.disabled = true;
  submitBtn.textContent = '创建中…';
  try {
    const newFile = await _doCreate(_currentCreateType);
    if (newFile) {
      _closeModal();
      await _loadFiles();
      const found = _allFiles.find(f => f.gid === newFile.gid);
      if (found) _openFile(found);
    }
  } catch (err) {
    _showToast('创建失败：' + (err.message || '未知错误'), 'error');
    submitBtn.disabled = false;
    submitBtn.textContent = '创建';
  }
}

async function _doCreate(fileType) {
  if (fileType.startsWith('list_')) {
    const name       = document.getElementById('mfFormName')?.value?.trim();
    const color      = document.getElementById('mfFormColor')?.value || '#5b8dee';
    const visibility = document.getElementById('mfFormVisibility')?.value || 'team';
    const projectGid = document.getElementById('mfFormProject')?.value || null;
    if (!name) { _showToast('请输入清单名称'); return null; }
    if (visibility === 'project' && !projectGid) { _showToast('请选择关联项目'); return null; }
    const itemType = fileType.replace('list_', '');
    const uid = window.parent?._authUser?.gid || '';
    const listMount = document.getElementById('mfVisMount_list');
    const sharedTeamGid = listMount?._vsTeamGid || null;
    const body = {
      name, color, item_type: itemType, visibility,
      storage_scope: 'cloud', owner_type: 'user', owner_gid: uid,
    };
    if (projectGid)    body.project_gid     = projectGid;
    if (sharedTeamGid) body.shared_team_gid = sharedTeamGid;
    const res = await _cf('/api/lists', { method: 'POST', body: JSON.stringify(body) });
    return { gid: res?.data?.gid || res?.gid, file_type: fileType };
  }

  if (fileType === 'bop_version') {
    const mode = document.querySelector('#mfBopModeTabs .mf-mode-tab.active')?.dataset.mode || 'blank';
    if (mode === 'blank') {
      const versionTag = document.getElementById('mfFormVersionTag')?.value?.trim();
      const bopName    = document.getElementById('mfFormBopName')?.value?.trim() || '';
      const projectGid = document.getElementById('mfFormBopProject')?.value || null;
      const taktTime   = parseFloat(document.getElementById('mfFormTaktTime')?.value) || 60;
      if (!versionTag) { _showToast('请填写版本标签'); return null; }
      const body = { version_tag: versionTag, bop_name: bopName, takt_time: taktTime };
      if (projectGid) body.project_gid = projectGid;
      const res = await _cf('/api/bop/versions', { method: 'POST', body: JSON.stringify(body) });
      return { gid: res?.data?.gid || res?.gid, file_type: fileType };
    }
    if (mode === 'fork') {
      const srcGid = document.getElementById('mfFormForkSrc')?.value;
      const tag    = document.getElementById('mfFormForkTag')?.value?.trim();
      const note   = document.getElementById('mfFormForkNote')?.value?.trim() || null;
      const bName  = document.getElementById('mfFormForkBopName')?.value?.trim() || '';
      if (!srcGid || !tag) { _showToast('请选择源版本并填写新版本标签'); return null; }
      const res = await _cf(`/api/bop/versions/${srcGid}/fork`, { method: 'POST', body: JSON.stringify({
        target_version_tag: tag, target_bop_name: bName, change_note: note,
      }) });
      return { gid: res?.data?.gid || res?.gid, file_type: fileType };
    }
    if (mode === 'smart') {
      const srcGid = document.getElementById('mfFormSmartSrc')?.value;
      const m      = document.getElementById('mfFormSmartMode')?.value;
      const tag    = document.getElementById('mfFormSmartTag')?.value?.trim();
      if (!srcGid || !tag) { _showToast('请选择源版本并填写新版本标签'); return null; }
      const res = await _cf(`/api/bop/versions/${srcGid}/smart-fork`, { method: 'POST', body: JSON.stringify({
        mode: m, target_version_tag: tag,
      }) });
      return { gid: res?.data?.gid || res?.gid, file_type: fileType };
    }
  }

  if (fileType === 'pbom') {
    const mode = document.querySelector('#mfPbomModeTabs .mf-mode-tab.active')?.dataset.mode || 'blank';
    if (mode === 'import') return null;
    const name = document.getElementById('mfFormPbomName')?.value?.trim();
    if (!name) { _showToast('请填写版本名称'); return null; }
    const res = await _cf('/api/ebom/snapshots', { method: 'POST', body: JSON.stringify({
      name, version_tag: name, source_type: 'manual',
    }) });
    return { gid: res?.data?.gid || res?.gid, file_type: fileType };
  }

  if (fileType.startsWith('doc_')) {
    const docTypeMap = { doc_md: 'markdown', doc_richtext: 'richtext', doc_url: 'weblink', doc_pdf: 'pdf' };
    const itemType  = docTypeMap[fileType];
    const scopeType = document.getElementById('mfFormScopeType')?.value || 'public';
    const folderGid = document.getElementById('mfFormFolder')?.value || null;

    let title = document.getElementById('mfFormTitle')?.value?.trim() || '';
    const body = { item_type: itemType, scope_type: scopeType };
    if (folderGid) body.folder_gid = folderGid;

    if (fileType === 'doc_url') {
      const url = document.getElementById('mfFormUrl')?.value?.trim() || '';
      if (!url) { _showToast('请输入 URL'); return null; }
      body.url = url;
      if (!title) {
        try { title = new URL(url).hostname; } catch { title = url.slice(0, 40); }
      }
    } else if (fileType === 'doc_pdf') {
      const filePath = document.getElementById('mfFormFilePath')?.value?.trim() || '';
      if (!filePath) { _showToast('请选择 PDF 文件'); return null; }
      if (!title) { _showToast('请输入标题'); return null; }
      body.file_path = filePath;
    } else if (fileType === 'doc_md') {
      if (!title) { _showToast('请输入标题'); return null; }
      body.content_md = document.getElementById('mfFormContent')?.value || '';
    } else {
      if (!title) { _showToast('请输入标题'); return null; }
    }

    body.title = title || '未命名';
    const res = await _cf('/api/knowledge_hub/items', { method: 'POST', body: JSON.stringify(body) });
    return { gid: res?.gid || res?.data?.gid, file_type: fileType };
  }

  return null;
}

/* ── Toast ───────────────────────────────────────────── */
function _showToast(msg, type = 'info') {
  const t = Object.assign(document.createElement('div'), {
    className: 'mf-toast' + (type === 'error' ? ' error' : ''),
    textContent: msg,
  });
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3000);
}

/* ── 主题同步 ─────────────────────────────────────────── */
function _initTheme() {
  // 从父窗口继承主题
  const applyTheme = (theme) => {
    document.documentElement.dataset.theme = theme;
    document.body.dataset.theme = theme;
  };

  // 读取父窗口主题
  try {
    const parentTheme = window.parent?.document?.documentElement?.dataset?.theme
      || window.parent?.document?.body?.dataset?.theme
      || 'light';
    applyTheme(parentTheme);
  } catch (_) {
    applyTheme('light');
  }

  // 监听主题变更消息
  window.addEventListener('message', e => {
    if (e.data?.type === 'theme' && e.data.theme) {
      applyTheme(e.data.theme);
    }
  });
}

/* ── 启动 ─────────────────────────────────────────────── */
function _init() {
  _initTheme();
  _initSplitter();
  _initToolbar();
  _loadFiles();
}

// 等 DOM 加载完成后启动
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', _init);
} else {
  _init();
}
