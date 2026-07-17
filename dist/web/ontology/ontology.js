/**
 * web/ontology/ontology.js  —  本体编辑器
 *
 * 布局：左侧全树（按域分组 + ┣╸ 连接线）| 右侧：详情面板 + 关系图谱
 */
'use strict';

// ── 状态 ──────────────────────────────────────────────────────────────────────
let _allClasses  = [];
let _selectedGid = null;
let _fullData    = null;
let _activeTab   = 'annotation';
let _graph       = null;   // OntoGraph 实例
const _collapsed = new Set(); // 已折叠的 gid
let _schemaDiff  = null;   // schema-diff 缓存 {prop_gid → sync_status}

// ── 工具 ──────────────────────────────────────────────────────────────────────
const _cf = (path, opts) => {
  const fn = window.top?._cloudFetch || window.parent?._cloudFetch || window._cloudFetch;
  if (!fn) throw new TypeError('_cloudFetch 未就绪');
  return fn(path, opts);
};

const _he = s => String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');

function _flattenTree(nodes, result = []) {
  for (const n of nodes) {
    const children = n.children || [];
    const flat = { ...n }; delete flat.children;
    result.push(flat);
    _flattenTree(children, result);
  }
  return result;
}

function _showToast(msg, type = 'info') {
  const d = document.createElement('div');
  d.className = `onto-toast onto-toast-${type}`;
  d.textContent = msg;
  document.body.appendChild(d);
  setTimeout(() => d.remove(), 2800);
}

async function _confirm(msg) {
  return new Promise(resolve => {
    const ov = document.createElement('div');
    ov.className = 'onto-modal-overlay';
    ov.innerHTML = `<div class="onto-modal" style="max-width:340px">
      <div class="onto-modal-title" style="font-size:13px;white-space:pre-wrap">${msg.replace(/</g,'&lt;')}</div>
      <div class="onto-modal-actions">
        <button class="onto-btn" id="_cfNo">取消</button>
        <button class="onto-btn onto-btn-primary" id="_cfYes">确认</button>
      </div></div>`;
    document.body.appendChild(ov);
    ov.querySelector('#_cfYes').addEventListener('click', () => { ov.remove(); resolve(true); });
    ov.querySelector('#_cfNo').addEventListener('click',  () => { ov.remove(); resolve(false); });
  });
}

async function _prompt(msg, def = '') {
  return new Promise(resolve => {
    const ov = document.createElement('div');
    ov.className = 'onto-modal-overlay';
    ov.innerHTML = `<div class="onto-modal" style="max-width:360px">
      <div class="onto-modal-title" style="font-size:13px;white-space:pre-wrap">${msg.replace(/</g,'&lt;')}</div>
      <input class="onto-input" id="_prInput" value="${(def||'').replace(/"/g,'&quot;')}" style="margin-bottom:12px">
      <div class="onto-modal-actions">
        <button class="onto-btn" id="_prNo">取消</button>
        <button class="onto-btn onto-btn-primary" id="_prOk">确定</button>
      </div></div>`;
    document.body.appendChild(ov);
    const inp = ov.querySelector('#_prInput');
    inp.focus(); inp.select();
    const ok = () => { const v = inp.value; ov.remove(); resolve(v); };
    const no = () => { ov.remove(); resolve(null); };
    ov.querySelector('#_prOk').addEventListener('click', ok);
    ov.querySelector('#_prNo').addEventListener('click', no);
    inp.addEventListener('keydown', e => { if (e.key === 'Enter') ok(); else if (e.key === 'Escape') no(); });
  });
}


// 祖先链：[当前, 父, 祖父, …]
function _ancestors(gid) {
  const path = [];
  let cur = gid;
  const seen = new Set();
  while (cur && !seen.has(cur)) {
    seen.add(cur);
    const node = _allClasses.find(c => c.gid === cur);
    if (!node) break;
    path.push(node);
    cur = node.parent_gid;
  }
  return path.reverse(); // 根在前
}

// ── 初始化 ────────────────────────────────────────────────────────────────────
async function _init() {
  const appRoot = document.getElementById('appRoot');
  appRoot.innerHTML = `
    <div class="onto-layout">
      <div class="onto-left" id="ontoLeft">
        <div class="onto-left-header">
          <span class="onto-left-title">本体类层级</span>
          <div class="onto-left-actions">
            <button class="onto-hdr-btn" id="ontoCollapseAllBtn" title="全部折叠">
              <svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 4h12M2 8h8M2 12h5"/><path d="M13 9l-2 2 2 2"/></svg>
            </button>
            <button class="onto-hdr-btn" id="ontoExpandAllBtn" title="全部展开">
              <svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 4h12M2 8h8M2 12h5"/><path d="M11 9l2 2-2 2"/></svg>
            </button>
            <button class="onto-hdr-btn" id="ontoSeedBtn">Seed</button>
            <button class="onto-hdr-btn" id="ontoBindTableBtn" title="查看并绑定未绑定实体表的类">🔗 绑定实体表</button>
            <button class="onto-hdr-btn onto-hdr-btn-primary" id="ontoNewRootBtn">+ 根类</button>
          </div>
        </div>
        <div class="onto-left-tree" id="ontoTree"></div>
      </div>
      <div class="onto-right" id="ontoRight">
        <div class="onto-detail-col" id="ontoDetailCol">
          <div class="onto-detail-empty" id="ontoDetailEmpty">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
              <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
            </svg>
            <p>选择左侧类查看详情</p>
          </div>
          <div class="onto-detail-body" id="ontoDetailBody" style="display:none">
            <div class="onto-detail-header" id="ontoDetailHeader"></div>
            <div class="onto-tab-bar" id="ontoTabBar">
              <button class="onto-tab-btn active" data-tab="annotation">标注</button>
              <button class="onto-tab-btn" data-tab="data_props">属性</button>
              <button class="onto-tab-btn" data-tab="obj_props">关系</button>
              <button class="onto-tab-btn" data-tab="individuals">实例</button>
              <button class="onto-tab-btn" data-tab="rules">规则</button>
            </div>
            <div class="onto-tab-content">
              <div class="onto-tab-pane active" id="ontoTab-annotation"></div>
              <div class="onto-tab-pane" id="ontoTab-data_props"></div>
              <div class="onto-tab-pane" id="ontoTab-obj_props"></div>
              <div class="onto-tab-pane" id="ontoTab-individuals"></div>
              <div class="onto-tab-pane" id="ontoTab-rules"></div>
            </div>
          </div>
        </div>
        <div class="onto-graph-col" id="ontoGraphCol">
          <div class="onto-graph-resizer" id="ontoGraphResizer"></div>
          <div class="onto-graph-header">
            <span class="onto-graph-title">本体图谱</span>
            <div class="onto-graph-hint">滚轮缩放 · 拖拽节点 · 双击重置</div>
          </div>
          <div class="onto-graph-canvas-wrap">
            <canvas id="ontoGraphCanvas"></canvas>
          </div>
        </div>
      </div>
    </div>`;

  document.getElementById('ontoSeedBtn').addEventListener('click', _runSeed);
  document.getElementById('ontoNewRootBtn').addEventListener('click', () => _createChildClass(null));
  document.getElementById('ontoBindTableBtn').addEventListener('click', _showBindTableModal);
  document.getElementById('ontoCollapseAllBtn').addEventListener('click', () => {
    _allClasses.filter(c => _allClasses.some(ch => ch.parent_gid === c.gid))
               .forEach(c => _collapsed.add(c.gid));
    _renderTree();
  });
  document.getElementById('ontoExpandAllBtn').addEventListener('click', () => {
    _collapsed.clear();
    _renderTree();
  });
  document.getElementById('ontoTabBar').addEventListener('click', e => {
    const btn = e.target.closest('.onto-tab-btn');
    if (btn) _setTab(btn.dataset.tab);
  });

  // 外部数据源跳转按钮（顶部操作区）
  const extDsBtn = document.createElement('button');
  extDsBtn.className = 'onto-hdr-btn';
  extDsBtn.textContent = '外部数据源';
  extDsBtn.title = '跳转到外部数据源，查看/配置当前类的字段映射';
  extDsBtn.addEventListener('click', () => {
    const p = window.top || window.parent || window;
    const params = _selectedGid ? { filter_class_gid: _selectedGid } : {};
    p.TabManager?.open?.('ext_datasource', params);
  });
  document.getElementById('ontoLeft').querySelector('.onto-left-actions').appendChild(extDsBtn);

    // 初始化图谱
    const canvas = document.getElementById('ontoGraphCanvas');
  const wrap   = canvas.parentElement;
  canvas.width  = wrap.clientWidth  || 400;
  canvas.height = wrap.clientHeight || 400;
  _graph = new OntoGraph(canvas, gid => {
    const cls = _allClasses.find(c => c.gid === gid);
    if (cls) _openClassDetail(cls);
  });

  // 图谱面板左侧拖拽调整宽度
  const resizer  = document.getElementById('ontoGraphResizer');
  const graphCol = document.getElementById('ontoGraphCol');
  let _resizing  = false, _startX = 0, _startW = 0;
  resizer.addEventListener('mousedown', e => {
    _resizing = true;
    _startX   = e.clientX;
    _startW   = graphCol.offsetWidth;
    resizer.classList.add('dragging');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  });
  document.addEventListener('mousemove', e => {
    if (!_resizing) return;
    const delta  = _startX - e.clientX;   // 向左拖 → 变宽
    const newW   = Math.max(160, Math.min(window.innerWidth * 0.7, _startW + delta));
    graphCol.style.width = newW + 'px';
  });
  document.addEventListener('mouseup', () => {
    if (!_resizing) return;
    _resizing = false;
    resizer.classList.remove('dragging');
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  });

  await _loadAndRender();
}

async function _loadAndRender() {
  try {
    const resp = await _cf('/api/ontology/classes');
    _allClasses = _flattenTree(resp.data || []);
  } catch (e) {
    _allClasses = [];
    if (String(e).includes('onto_classes') || (e && e.status === 404)) {
      _showToast('请先执行建表 SQL，再点击 Seed', 'error');
    }
  }
  _renderTree();
  _refreshGraph();
}

async function _refreshGraph() {
  if (!_graph) return;
  try {
    const resp = await _cf('/api/ontology/graph');
    _graph.setData(resp.classes || [], resp.relations || []);
    if (_selectedGid) _graph.setSelected(_selectedGid);
  } catch { /* graph unavailable, silent */ }
}

// ── 左侧树渲染 ─────────────────────────────────────────────────────────────────
function _renderTree() {
  const container = document.getElementById('ontoTree');
  if (!container) return;

  const roots = _allClasses
    .filter(c => !c.parent_gid)
    .sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
  if (!roots.length) {
    container.innerHTML = '<div class="onto-tree-empty">暂无数据，请点击 Seed 初始化</div>';
    return;
  }

  let html = '';
  for (const root of roots) html += _renderNode(root, true);
  container.innerHTML = html;

  // 仅在首次渲染时绑定（container 元素不重建，只重置 innerHTML）
  if (!container._ontoBound) {
    container._ontoBound = true;

    container.addEventListener('click', e => {
      // 折叠箭头优先处理，不触发详情面板
      const toggle = e.target.closest('.onto-tl-toggle');
      if (toggle) {
        const group = toggle.closest('.onto-group');
        if (!group) return;
        const gid = group.dataset.gid;
        if (_collapsed.has(gid)) {
          _collapsed.delete(gid);
          group.classList.remove('onto-group-collapsed');
          toggle.title = '折叠';
        } else {
          _collapsed.add(gid);
          group.classList.add('onto-group-collapsed');
          toggle.title = '展开';
        }
        return;
      }
      const node = e.target.closest('.onto-tree-node');
      if (!node) return;
      const cls = _allClasses.find(c => c.gid === node.dataset.gid);
      if (cls) _openClassDetail(cls);
    });
    container.addEventListener('contextmenu', e => {
      const node = e.target.closest('.onto-tree-node');
      if (!node) return;
      e.preventDefault();
      const cls = _allClasses.find(c => c.gid === node.dataset.gid);
      if (cls) _showCtxMenu(e.clientX, e.clientY, cls);
    });

    _bindTreeDrag(container);
  }
}

function _renderNode(node, isRoot) {
  const children = _allClasses
    .filter(c => c.parent_gid === node.gid)
    .sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
  const isSelected  = node.gid === _selectedGid;
  const isCollapsed = _collapsed.has(node.gid);
  const color = node.color || '#6b7280';
  const abstractBadge = node.is_abstract ? '<span class="onto-abstract-badge">抽象</span>' : '';
  const rootCls      = isRoot ? ' onto-tree-root' : '';
  const selCls       = isSelected ? ' selected' : '';
  const collapsedCls = isCollapsed ? ' onto-group-collapsed' : '';
  const parentAttr   = node.parent_gid ? `data-parent-gid="${_he(node.parent_gid)}"` : '';

  // 有子节点显示折叠箭头，无子节点用占位保持对齐
  const toggleEl = children.length
    ? `<span class="onto-tl-toggle" title="${isCollapsed ? '展开' : '折叠'}"></span>`
    : `<span class="onto-tl-placeholder"></span>`;

  let html = `<div class="onto-group${collapsedCls}" draggable="true" data-gid="${_he(node.gid)}" ${parentAttr}>`;
  html += `<div class="onto-tree-node${rootCls}${selCls}" data-gid="${_he(node.gid)}">
      ${toggleEl}
      <span class="onto-tree-dot" style="background:${_he(color)}"></span>
      <span class="onto-tree-label">${_he(node.label_zh || node.name)}</span>
      ${abstractBadge}
    </div>`;

  if (children.length) {
    html += `<div class="onto-group-children" data-parent-gid="${_he(node.gid)}">`;
    for (const child of children) html += _renderNode(child, false);
    html += `</div>`;
  }
  html += `</div>`;
  return html;
}

// ── 内联 toggle（属性/关系 show_in_detail 直接点击）──────────────────────────
function _bindInlineToggles(pane) {
  pane.querySelectorAll('.onto-inline-toggle').forEach(cb => {
    cb.addEventListener('change', async () => {
      const gid   = cb.dataset.gid;
      const field = cb.dataset.field;
      const api   = cb.dataset.api; // 'properties' | 'relations'
      const val   = cb.checked;
      try {
        await _cf(`/api/ontology/${api}/${gid}`, {
          method: 'PATCH',
          body: JSON.stringify({ [field]: val }),
        });
        _fullData = null;
      } catch (e) {
        cb.checked = !val; // 回滚
        _showToast('保存失败：' + e, 'error');
      }
    });
    // 阻止点击 checkbox 触发行拖拽
    cb.addEventListener('mousedown', e => e.stopPropagation());
  });
}

// ── 表格行拖拽排序（属性/关系共用）────────────────────────────────────────────
function _bindTableRowDrag(tbody, patchUrl, onDone) {
  let dragGid = null;

  const rows = () => Array.from(tbody.querySelectorAll('tr[data-gid]'));

  tbody.addEventListener('dragstart', e => {
    const tr = e.target.closest('tr[data-gid]');
    if (!tr) return;
    dragGid = tr.dataset.gid;
    e.dataTransfer.effectAllowed = 'move';
    setTimeout(() => tr.classList.add('onto-row-dragging'), 0);
  });

  tbody.addEventListener('dragend', () => {
    tbody.querySelectorAll('.onto-row-dragging, .onto-row-drop-before, .onto-row-drop-after')
      .forEach(el => el.classList.remove('onto-row-dragging', 'onto-row-drop-before', 'onto-row-drop-after'));
    dragGid = null;
  });

  tbody.addEventListener('dragover', e => {
    e.preventDefault();
    const tr = e.target.closest('tr[data-gid]');
    if (!tr || tr.dataset.gid === dragGid) return;
    tbody.querySelectorAll('.onto-row-drop-before, .onto-row-drop-after')
      .forEach(el => el.classList.remove('onto-row-drop-before', 'onto-row-drop-after'));
    const rect = tr.getBoundingClientRect();
    tr.classList.add(e.clientY < rect.top + rect.height / 2 ? 'onto-row-drop-before' : 'onto-row-drop-after');
  });

  tbody.addEventListener('dragleave', e => {
    const tr = e.target.closest('tr[data-gid]');
    if (tr) tr.classList.remove('onto-row-drop-before', 'onto-row-drop-after');
  });

  tbody.addEventListener('drop', async e => {
    e.preventDefault();
    const targetTr = e.target.closest('tr[data-gid]');
    if (!targetTr || targetTr.dataset.gid === dragGid) return;
    const isBefore = targetTr.classList.contains('onto-row-drop-before');
    tbody.querySelectorAll('.onto-row-drop-before, .onto-row-drop-after')
      .forEach(el => el.classList.remove('onto-row-drop-before', 'onto-row-drop-after'));

    const newOrder = rows().map(r => r.dataset.gid);
    const fromIdx = newOrder.indexOf(dragGid);
    newOrder.splice(fromIdx, 1);
    let toIdx = newOrder.indexOf(targetTr.dataset.gid);
    if (!isBefore) toIdx += 1;
    newOrder.splice(toIdx, 0, dragGid);

    await Promise.all(newOrder.map((gid, i) =>
      _cf(patchUrl(gid), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sort_order: (i + 1) * 10 }),
      }).catch(() => null)
    ));
    if (onDone) onDone();
  });
}

// ── 拖拽排序 ──────────────────────────────────────────────────────────────────
let _dragGid = null;
let _dragParentGid = null;

function _bindTreeDrag(container) {
  container.addEventListener('dragstart', e => {
    const group = e.target.closest('.onto-group');
    if (!group) return;
    _dragGid = group.dataset.gid;
    _dragParentGid = group.dataset.parentGid || null;
    e.dataTransfer.effectAllowed = 'move';
    setTimeout(() => group.classList.add('onto-group-dragging'), 0);
  });

  container.addEventListener('dragend', () => {
    container.querySelectorAll('.onto-group-dragging,.onto-drop-before,.onto-drop-after')
      .forEach(el => el.classList.remove('onto-group-dragging', 'onto-drop-before', 'onto-drop-after'));
    _dragGid = null;
    _dragParentGid = null;
  });

  container.addEventListener('dragover', e => {
    e.preventDefault();
    const group = e.target.closest('.onto-group');
    if (!group || group.dataset.gid === _dragGid) return;
    if ((group.dataset.parentGid || null) !== _dragParentGid) return;
    e.dataTransfer.dropEffect = 'move';
    container.querySelectorAll('.onto-drop-before,.onto-drop-after')
      .forEach(el => el.classList.remove('onto-drop-before', 'onto-drop-after'));
    const nodeEl = group.querySelector(':scope > .onto-tree-node');
    const mid = nodeEl.getBoundingClientRect().top + nodeEl.getBoundingClientRect().height / 2;
    group.classList.add(e.clientY < mid ? 'onto-drop-before' : 'onto-drop-after');
  });

  container.addEventListener('dragleave', e => {
    const group = e.target.closest('.onto-group');
    if (group) group.classList.remove('onto-drop-before', 'onto-drop-after');
  });

  container.addEventListener('drop', async e => {
    e.preventDefault();
    const targetGroup = e.target.closest('.onto-group');
    if (!targetGroup || targetGroup.dataset.gid === _dragGid) return;
    if ((targetGroup.dataset.parentGid || null) !== _dragParentGid) return;

    const isBefore = targetGroup.classList.contains('onto-drop-before');
    container.querySelectorAll('.onto-drop-before,.onto-drop-after')
      .forEach(el => el.classList.remove('onto-drop-before', 'onto-drop-after'));

    // 从 DOM 里读兄弟节点顺序
    const parentEl = targetGroup.parentElement;
    const siblings = Array.from(parentEl.querySelectorAll(':scope > .onto-group'));
    const newOrder = siblings.map(s => s.dataset.gid);

    // 移动 dragGid 到目标位置
    const fromIdx = newOrder.indexOf(_dragGid);
    newOrder.splice(fromIdx, 1);
    let toIdx = newOrder.indexOf(targetGroup.dataset.gid);
    if (!isBefore) toIdx += 1;
    newOrder.splice(toIdx, 0, _dragGid);

    // 批量 PATCH 有变化的 sort_order（步长 10）
    const patches = [];
    newOrder.forEach((gid, i) => {
      const newSort = (i + 1) * 10;
      const cls = _allClasses.find(c => c.gid === gid);
      if (cls && cls.sort_order !== newSort) {
        cls.sort_order = newSort;
        patches.push(_cf(`/api/ontology/classes/${gid}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ sort_order: newSort }),
        }).catch(() => null));
      }
    });
    await Promise.all(patches);
    _renderTree();
  });
}

// ── 右键菜单 ──────────────────────────────────────────────────────────────────
let _ctxMenu = null;
function _showCtxMenu(x, y, cls) {
  _closeCtxMenu();
  const menu = document.createElement('div');
  menu.className = 'onto-ctx-menu';
  menu.style.cssText = `position:fixed;left:${x}px;top:${y}px;z-index:9999`;
  menu.innerHTML = `
    <div class="onto-ctx-item" data-action="new_child">新建子类</div>
    <div class="onto-ctx-item" data-action="reparent">变更父类</div>
    <div class="onto-ctx-sep"></div>
    <div class="onto-ctx-item onto-ctx-danger" data-action="delete">删除类</div>`;
  document.body.appendChild(menu);
  _ctxMenu = menu;
  menu.addEventListener('click', e => {
    const item = e.target.closest('.onto-ctx-item');
    if (!item) return;
    _closeCtxMenu();
    if (item.dataset.action === 'new_child') _createChildClass(cls);
    if (item.dataset.action === 'reparent')  _reparentClass(cls);
    if (item.dataset.action === 'delete')    _deleteClass(cls);
  });
}
function _closeCtxMenu() {
  if (_ctxMenu) { _ctxMenu.remove(); _ctxMenu = null; }
}
document.addEventListener('click', _closeCtxMenu);

// ── 详情面板 ──────────────────────────────────────────────────────────────────
async function _openClassDetail(cls) {
  _selectedGid = cls.gid;
  _renderTree();
  if (_graph) _graph.setSelected(cls.gid);

  document.getElementById('ontoDetailEmpty').style.display = 'none';
  document.getElementById('ontoDetailBody').style.display  = 'flex';

  // 继承路径
  const path = _ancestors(cls.gid);
  const breadcrumb = ['Thing', ...path.map(c => _he(c.label_zh || c.name))];
  const breadcrumbHtml = breadcrumb.map((seg, i) =>
    i < breadcrumb.length - 1
      ? `<span class="onto-bc-seg">${seg}</span><span class="onto-bc-sep">›</span>`
      : `<span class="onto-bc-cur">${seg}</span>`
  ).join('');

  const parent = cls.parent_gid ? _allClasses.find(c => c.gid === cls.parent_gid) : null;
  const abstractBadge = cls.is_abstract ? '<span class="onto-abstract-badge">抽象</span>' : '';

  document.getElementById('ontoDetailHeader').innerHTML = `
    <div class="onto-dh-top">
      <span class="onto-dh-dot" style="background:${_he(cls.color || '#6b7280')}"></span>
      <span class="onto-dh-name">${_he(cls.label_zh || cls.name)}</span>
      <span class="onto-dh-code">${_he(cls.name)}</span>
      ${abstractBadge}
      ${parent ? `<span class="onto-dh-parent">父类：${_he(parent.label_zh || parent.name)}</span>` : ''}
    </div>
    <div class="onto-dh-breadcrumb">${breadcrumbHtml}</div>`;

  _fullData    = null;
  _schemaDiff  = null;  // 切换类时清除 schema-diff 缓存
  _resetTabBadges();
  await _renderActiveTab();
  _loadTabCounts();
}

function _resetTabBadges() {
  document.querySelectorAll('.onto-tab-btn').forEach(b => {
    b.querySelector('.onto-tab-badge')?.remove();
  });
}

async function _loadTabCounts() {
  if (!_selectedGid) return;
  try {
    if (!_fullData) {
      const resp = await _cf(`/api/ontology/classes/${_selectedGid}/full`);
      _fullData = resp.data;
    }
    const counts = {
      data_props:  (_fullData.properties  || []).filter(p => p.prop_kind === 'data' && p.class_gid === _selectedGid).length,
      obj_props:   (_fullData.relations   || []).length,
      rules:       (_fullData.rules       || []).length,
    };
    for (const [tab, count] of Object.entries(counts)) {
      if (!count) continue;
      const btn = document.querySelector(`.onto-tab-btn[data-tab="${tab}"]`);
      if (btn && !btn.querySelector('.onto-tab-badge')) {
        const badge = document.createElement('span');
        badge.className = 'onto-tab-badge';
        badge.textContent = count;
        btn.appendChild(badge);
      }
    }
  } catch { /* silent */ }
}

function _setTab(tab) {
  _activeTab = tab;
  document.querySelectorAll('.onto-tab-btn').forEach(b  => b.classList.toggle('active', b.dataset.tab === tab));
  document.querySelectorAll('.onto-tab-pane').forEach(p => p.classList.toggle('active', p.id === `ontoTab-${tab}`));
  _renderActiveTab();
}

async function _renderActiveTab() {
  if (!_selectedGid) return;
  if (!_fullData) {
    try {
      const resp = await _cf(`/api/ontology/classes/${_selectedGid}/full`);
      _fullData = resp.data;
    } catch { _showToast('加载详情失败', 'error'); return; }
  }
  // 懒加载 schema-diff（第一次打开属性 tab 时缓存）
  if (_activeTab === 'data_props' && !_schemaDiff) {
    try {
      const dr = await _cf('/api/ontology/schema-diff');
      _schemaDiff = {};
      (dr.data || []).forEach(r => { _schemaDiff[r.gid] = r.sync_status; });
    } catch { _schemaDiff = {}; }
  }
  const pane = document.getElementById(`ontoTab-${_activeTab}`);
  if (!pane) return;
  ({ annotation: _renderAnnotation, data_props: _renderDataProps,
     obj_props: _renderObjProps, individuals: _renderIndividuals,
     rules: _renderRules })[_activeTab]?.(pane);
}

// ── Tab 1：标注 ───────────────────────────────────────────────────────────────
function _renderAnnotation(pane) {
  const d = _fullData;
  pane.innerHTML = `
    <div class="onto-form">
      <div class="onto-form-row">
        <label>类名（标识符）</label>
        <input class="onto-input" id="annName" value="${_he(d.name)}">
      </div>
      <div class="onto-form-row">
        <label>中文名称</label>
        <input class="onto-input" id="annLabelZh" value="${_he(d.label_zh)}">
      </div>
      <div class="onto-form-row">
        <label>英文名称</label>
        <input class="onto-input" id="annLabelEn" value="${_he(d.label_en)}" placeholder="English label">
      </div>
      <div class="onto-form-row">
        <label>描述</label>
        <textarea class="onto-input" id="annDesc" rows="3">${_he(d.description)}</textarea>
      </div>
      <div class="onto-form-row">
        <label>绑定 node_type</label>
        <select class="onto-input" id="annBinding">
          <option value="">— 无绑定 —</option>
        </select>
        <input class="onto-input" id="annBindingCustom" placeholder="输入自定义 node_type"
               style="display:none;margin-top:4px">
      </div>
      <div class="onto-form-row">
        <label>实体表</label>
        <select class="onto-input" id="annEntityTable">
          <option value="">— 未绑定 —</option>
        </select>
        <div style="font-size:10px;color:var(--onto-text3);margin-top:2px">格式：schema.table_name，绑定后可在属性页同步字段</div>
      </div>
      <div class="onto-form-row onto-form-row-inline">
        <label>颜色</label>
        <input class="onto-input onto-color-input" id="annColor" type="color" value="${d.color || '#6b7280'}">
      </div>
      <div class="onto-form-row onto-form-row-inline">
        <label>抽象类</label>
        <label class="onto-checkbox-label">
          <input type="checkbox" id="annAbstract" ${d.is_abstract ? 'checked' : ''}>
          <span>不能作为 BOP 节点实例</span>
        </label>
      </div>
      <div class="onto-form-actions">
        <button class="onto-btn onto-btn-primary" id="annSaveBtn">保存</button>
      </div>
    </div>`;
  document.getElementById('annSaveBtn').addEventListener('click', _saveAnnotation);
  _loadDbTablesInto('annEntityTable', d.entity_table || '');
  _loadNodeTypeSuggestionsInto('annBinding', d.node_type_binding || '');
  // 选"手动输入"时显示文本框
  document.getElementById('annBinding')?.addEventListener('change', e => {
    const custom = document.getElementById('annBindingCustom');
    if (custom) custom.style.display = e.target.value === '__custom__' ? 'block' : 'none';
  });
}

async function _saveAnnotation() {
  const payload = {
    name:              document.getElementById('annName').value.trim(),
    label_zh:          document.getElementById('annLabelZh').value.trim(),
    label_en:          document.getElementById('annLabelEn').value.trim(),
    description:       document.getElementById('annDesc').value.trim(),
    node_type_binding: (() => {
      const sel = document.getElementById('annBinding');
      if (sel?.value === '__custom__') return document.getElementById('annBindingCustom')?.value.trim() || null;
      return sel?.value.trim() || null;
    })(),
    entity_table:      document.getElementById('annEntityTable').value.trim() || null,
    color:             document.getElementById('annColor').value,
    is_abstract:       document.getElementById('annAbstract').checked,
  };
  try {
    await _cf(`/api/ontology/classes/${_selectedGid}`, { method: 'PATCH', body: JSON.stringify(payload) });
    const idx = _allClasses.findIndex(c => c.gid === _selectedGid);
    if (idx >= 0) Object.assign(_allClasses[idx], payload);
    _fullData = { ..._fullData, ...payload };
    _renderTree();
    const cls = _allClasses.find(c => c.gid === _selectedGid);
    if (cls) _openClassDetail(cls);
    _showToast('已保存', 'success');
  } catch (e) { _showToast('保存失败：' + e, 'error'); }
}

// ── Tab 2：数据属性 ────────────────────────────────────────────────────────────
function _renderDataProps(pane) {
  const own = (_fullData.properties || []).filter(p => p.prop_kind === 'data' && p.class_gid === _selectedGid);
  const inh = (_fullData.properties || []).filter(p => p.prop_kind === 'data' && p.class_gid !== _selectedGid);
  const cls = _fullData || {};
  const entityTableInfo = cls.entity_table
    ? `<span class="onto-entity-table-tag">实体表：<code>${_he(cls.entity_table)}</code></span>` : '';

  const _storageLabel = (hint, fieldCfg) => ({
    'entity_table': '<span class="onto-storage-badge onto-storage-entity">实体</span>',
    'meta':         '<span class="onto-storage-badge onto-storage-meta">meta</span>',
    'derived':      `<span class="onto-storage-badge onto-storage-derived" title="${
        fieldCfg ? `${fieldCfg.aggregate||''}(${fieldCfg.child_node_type||''}.${fieldCfg.child_property||''})` : '派生'
    }">∑派生</span>`,
  }[hint] || `<span class="onto-storage-badge onto-storage-meta">${hint||'meta'}</span>`);

  const _syncLabel = (propGid, hint) => {
    if (hint !== 'entity_table' || !_schemaDiff) return '';
    const status = _schemaDiff[propGid];
    if (status === 'column') return '<span class="onto-sync-badge onto-sync-col">已建列</span>';
    if (status === 'ext')    return '<span class="onto-sync-badge onto-sync-ext">ext</span>';
    return '';
  };

  pane.innerHTML = `
    <div class="onto-section-toolbar">
      ${entityTableInfo}
      ${cls.entity_table ? `<button class="onto-btn onto-btn-sm" id="syncFromTableBtn" title="从 ${cls.entity_table} 同步未导入的列">⬇ 同步表字段</button>` : ''}
      <button class="onto-btn onto-btn-sm onto-btn-primary" id="addPropBtn">+ 添加属性</button>
    </div>
    <table class="onto-table">
      <thead><tr><th style="width:20px"></th><th>属性名</th><th>中文名</th><th>类型</th><th>必填</th><th>存储</th><th>DB列</th><th>范围</th><th>描述</th><th title="拖拽行可调整详情面板显示顺序">顺序</th><th>详情</th><th></th></tr></thead>
      <tbody>
        ${own.length ? own.map(p => `
          <tr draggable="true" data-gid="${_he(p.gid)}">
            <td class="onto-drag-cell">⠿</td>
            <td><code>${_he(p.name)}</code>${p.mapped_column ? `<span class="onto-mapped-col">→${_he(p.mapped_column)}</span>` : ''}</td>
            <td>${_he(p.label_zh)}</td>
            <td><span class="onto-type-badge">${_he(p.data_type || '-')}</span></td>
            <td>${p.required ? '<span class="onto-req-dot"></span>' : ''}</td>
            <td>${_storageLabel(p.storage_hint, p.field_config)}</td>
            <td>${_syncLabel(p.gid, p.storage_hint)}</td>
            <td class="onto-num">${p.min_val ?? '-'} ~ ${p.max_val ?? '-'}</td>
            <td class="onto-desc-cell">${_he(p.description)}</td>
            <td class="onto-num" style="color:var(--onto-text3);font-size:11px">${p.sort_order ?? '-'}</td>
            <td style="text-align:center"><input type="checkbox" class="onto-inline-toggle" data-gid="${_he(p.gid)}" data-field="show_in_detail" data-api="properties" title="在详情面板显示"${p.show_in_detail !== false ? ' checked' : ''}></td>
            <td style="white-space:nowrap">
              <button class="onto-icon-btn edit-prop-btn" data-gid="${_he(p.gid)}" title="编辑">✎</button>
              <button class="onto-icon-btn del-prop-btn" data-gid="${_he(p.gid)}" title="删除">✕</button>
            </td>
          </tr>`).join('') : `<tr><td colspan="11" class="onto-empty-cell">暂无数据属性</td></tr>`}
      </tbody>
    </table>
    ${inh.length ? `
      <div class="onto-inherited-section">
        <div class="onto-inherited-label">继承属性</div>
        ${inh.map(p => `
          <div class="onto-inherited-row">
            <code>${_he(p.name)}</code>
            <span>${_he(p.label_zh)}</span>
            <span class="onto-type-badge">${_he(p.data_type || '-')}</span>
            ${_storageLabel(p.storage_hint, p.field_config)}
            ${_syncLabel(p.gid, p.storage_hint)}
            <span class="onto-inherited-from">继承自 ${_he(p.class_label || p.class_gid)}</span>
          </div>`).join('')}
      </div>` : ''}`;
  document.getElementById('addPropBtn').addEventListener('click', _showAddPropModal);
  document.getElementById('syncFromTableBtn')?.addEventListener('click', async () => {
    if (!await _confirm(`从「${cls.entity_table}」同步未导入的列？\n（已存在属性和基础设施列会自动跳过）`)) return;
    try {
      const r = await _cf(`/api/ontology/classes/${_selectedGid}/sync-from-table`, { method: 'POST' });
      _fullData = null; _schemaDiff = null; await _renderActiveTab(); _loadTabCounts();
      const relMsg = r.added_relations?.length ? `，新增 ${r.added_relations.length} 个关系` : '';
      _showToast(`同步完成：新增 ${r.total_added} 个属性${relMsg}，跳过 ${r.skipped_exists.length} 个已存在，跳过 ${r.skipped_infra.length} 个基础设施列`, 'success');
    } catch (e) { _showToast('同步失败：' + e, 'error'); }
  });
  pane.querySelectorAll('.edit-prop-btn').forEach(btn => {
    const propGid = btn.dataset.gid;
    const prop = own.find(p => p.gid === propGid);
    if (prop) btn.addEventListener('click', () => _showEditPropModal(prop));
  });
  pane.querySelectorAll('.del-prop-btn').forEach(btn =>
    btn.addEventListener('click', () => _deleteProperty(btn.dataset.gid)));
  _bindInlineToggles(pane);

  const propTbody = pane.querySelector('.onto-table tbody');
  if (propTbody) {
    _bindTableRowDrag(propTbody,
      gid => `/api/ontology/properties/${gid}`,
      () => { _fullData = null; _renderActiveTab(); }
    );
  }

  _renderCardinalityAxioms(pane, _selectedGid);
}

function _showAddPropModal() {
  const overlay = document.createElement('div');
  overlay.className = 'onto-modal-overlay';
  overlay.innerHTML = `
    <div class="onto-modal">
      <div class="onto-modal-title">添加数据属性</div>
      <div class="onto-form-row"><label>属性名</label><input class="onto-input" id="nPropName" placeholder="torque"></div>
      <div class="onto-form-row"><label>中文名</label><input class="onto-input" id="nPropLabel" placeholder="力矩值"></div>
      <div class="onto-form-row"><label>类型</label>
        <select class="onto-input" id="nPropType">
          <option value="string">string</option><option value="integer">integer</option>
          <option value="float">float</option><option value="boolean">boolean</option>
          <option value="date">date</option><option value="enum">enum</option>
        </select>
      </div>
      <div class="onto-form-row" id="nEnumValuesRow" style="display:none"><label>选项值（逗号分隔）</label>
        <input class="onto-input" id="nPropEnumValues" placeholder="选项A,选项B,选项C">
      </div>
      <div class="onto-form-row onto-form-row-inline"><label>必填</label>
        <label class="onto-checkbox-label"><input type="checkbox" id="nPropReq"><span>必填</span></label>
      </div>
      <div class="onto-form-row"><label>最小值</label><input class="onto-input" id="nPropMin" type="number" placeholder="可选"></div>
      <div class="onto-form-row"><label>最大值</label><input class="onto-input" id="nPropMax" type="number" placeholder="可选"></div>
      <div class="onto-form-row"><label>描述</label><input class="onto-input" id="nPropDesc" placeholder="可选"></div>
      <div class="onto-form-row"><label>DB列名</label><input class="onto-input" id="nPropMappedCol" placeholder="留空则与属性名相同"></div>
      <div class="onto-form-row"><label>存储方式</label>
        <select class="onto-input" id="nPropStorageHint">
          <option value="">自动（根据实体表）</option>
          <option value="meta">meta（JSONB 扩展字段）</option>
          <option value="entity_table">实体表列（需 DB 建列）</option>
          <option value="derived">派生（聚合计算，只读）</option>
        </select>
      </div>
      <div id="nDerivedSection" style="display:none;border:1px solid var(--onto-border);border-radius:5px;padding:10px;margin-top:4px">
        <div style="font-size:11px;color:var(--onto-text3);margin-bottom:8px">派生属性从子节点计算得出，显示时只读</div>
        <div class="onto-form-row"><label>运算模式</label>
          <select class="onto-input" id="nDerivMode">
            <option value="simple">简单聚合</option>
            <option value="formula">自定义公式</option>
          </select>
        </div>
        <div id="nDerivSimple">
          <div class="onto-form-row"><label>聚合函数</label>
            <select class="onto-input" id="nAggFunc">
              <option value="SUM">SUM（求和）</option>
              <option value="COUNT">COUNT（计数）</option>
              <option value="AVG">AVG（平均）</option>
              <option value="MAX">MAX（最大）</option>
              <option value="MIN">MIN（最小）</option>
            </select>
          </div>
          <div class="onto-form-row"><label>子节点类型</label>
            <select class="onto-input" id="nChildNodeType">
              <option value="">— 选择子节点类型 —</option>
              ${_allClasses.filter(c => c.node_type_binding)
                .sort((a,b) => (a.label_zh||a.name||'').localeCompare(b.label_zh||b.name||''))
                .map(c => `<option value="${_he(c.node_type_binding)}">${_he(c.label_zh||c.name)} (${_he(c.node_type_binding)})</option>`).join('')}
            </select>
          </div>
          <div class="onto-form-row"><label>子节点属性名</label>
            <input class="onto-input" id="nChildProperty" placeholder="如 vd_time、headcount">
          </div>
        </div>
        <div id="nDerivFormula" style="display:none">
          <div class="onto-form-row"><label>公式</label>
            <textarea class="onto-input" id="nDerivExpr" rows="3" style="resize:vertical;font-family:monospace;font-size:11px"
              placeholder="SUM(vd_time) / COUNT(operation)
支持: SUM(prop) COUNT(prop) AVG(prop) MAX(prop) MIN(prop) + - * / ( )"></textarea>
            <div style="font-size:10px;color:var(--onto-text3);margin-top:2px">
              公式可引用子节点属性（如 vd_time），用聚合函数包裹。<br>
              示例: SUM(vd_time) / COUNT(operation) — 平均工时
            </div>
          </div>
        </div>
      </div>
      <div class="onto-form-row onto-form-row-inline">
        <label>详情面板显示</label>
        <label class="onto-checkbox-label"><input type="checkbox" id="nPropShowDetail" checked><span>在工艺流程图详情面板中显示</span></label>
      </div>
      <div class="onto-form-row"><label>详情顺序</label><input class="onto-input" id="nPropDetailOrder" type="number" value="99" placeholder="99"></div>
      <div class="onto-modal-actions">
        <button class="onto-btn" id="cancelPropBtn">取消</button>
        <button class="onto-btn onto-btn-primary" id="savePropBtn">添加</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);
  overlay.querySelector('#nPropType').addEventListener('change', e => {
    overlay.querySelector('#nEnumValuesRow').style.display = e.target.value === 'enum' ? 'block' : 'none';
  });
  overlay.querySelector('#nPropStorageHint').addEventListener('change', e => {
    const sec = overlay.querySelector('#nDerivedSection');
    sec.style.display = e.target.value === 'derived' ? 'block' : 'none';
  });
  overlay.querySelector('#nDerivMode')?.addEventListener('change', e => {
    overlay.querySelector('#nDerivSimple').style.display = e.target.value === 'simple' ? 'block' : 'none';
    overlay.querySelector('#nDerivFormula').style.display = e.target.value === 'formula' ? 'block' : 'none';
  });
  overlay.querySelector('#cancelPropBtn').addEventListener('click', () => overlay.remove());
  overlay.querySelector('#savePropBtn').addEventListener('click', async () => {
    const name = overlay.querySelector('#nPropName').value.trim();
    if (!name) { _showToast('属性名不能为空', 'warn'); return; }
    const minV = overlay.querySelector('#nPropMin').value;
    const maxV = overlay.querySelector('#nPropMax').value;
    const storageHint = overlay.querySelector('#nPropStorageHint').value || null;
    const isDerived = storageHint === 'derived';
    let fieldConfig = {};
    if (isDerived) {
      const mode = overlay.querySelector('#nDerivMode')?.value || 'simple';
      if (mode === 'formula') {
        fieldConfig = { expr: overlay.querySelector('#nDerivExpr')?.value.trim() || '' };
      } else {
        fieldConfig = {
          aggregate:       overlay.querySelector('#nAggFunc')?.value || 'SUM',
          child_node_type: overlay.querySelector('#nChildNodeType')?.value || '',
          child_property:  overlay.querySelector('#nChildProperty')?.value.trim() || '',
        };
      }
    }
    const enumValsRaw = overlay.querySelector('#nPropEnumValues')?.value.trim() || '';
    const enumVals = enumValsRaw ? enumValsRaw.split(',').map(s => s.trim()).filter(Boolean) : [];
    try {
      await _cf('/api/ontology/properties', { method: 'POST', body: JSON.stringify({
        class_gid: _selectedGid, name, label_zh: overlay.querySelector('#nPropLabel').value.trim(),
        prop_kind: 'data', data_type: overlay.querySelector('#nPropType').value,
        enum_values: enumVals,
        required: overlay.querySelector('#nPropReq').checked,
        min_val: minV ? parseFloat(minV) : null, max_val: maxV ? parseFloat(maxV) : null,
        description: overlay.querySelector('#nPropDesc').value.trim(),
        mapped_column: overlay.querySelector('#nPropMappedCol').value.trim() || null,
        storage_hint: storageHint || null,
        field_config: fieldConfig,
        show_in_detail: overlay.querySelector('#nPropShowDetail').checked,
        detail_order:   parseInt(overlay.querySelector('#nPropDetailOrder').value) || 99,
      })});
      overlay.remove(); _fullData = null; await _renderActiveTab(); _showToast('属性已添加', 'success');
    } catch (e) { _showToast('添加失败：' + e, 'error'); }
  });
}

function _showEditPropModal(prop) {
  const syncStatus   = _schemaDiff?.[prop.gid];          // 'column' | 'ext' | undefined
  const hasRealCol   = prop.storage_hint === 'entity_table' && syncStatus === 'column';
  const hasExtCol    = prop.storage_hint === 'entity_table' && syncStatus === 'ext';
  const inDb         = hasRealCol || hasExtCol;

  // 如果已建真实列，生成修改类型 / 改名所需的 SQL 提示
  const alterTypeSql = hasRealCol
    ? `ALTER TABLE ... ALTER COLUMN ${prop.mapped_column || prop.name} TYPE <new_type>;`
    : '';
  const alterNameSql = hasRealCol
    ? `ALTER TABLE ... RENAME COLUMN ${prop.mapped_column || prop.name} TO <new_name>;`
    : '';

  const dbWarning = hasRealCol
    ? `<div style="background:rgba(249,226,175,0.12);border:1px solid rgba(249,226,175,0.4);
           border-radius:5px;padding:8px 10px;margin-bottom:10px;font-size:11px;color:#f9e2af">
         ⚠ 此属性已在实体表中建列（<code>${prop.mapped_column || prop.name}</code>）。
         修改<strong>类型</strong>或<strong>列名</strong>需在 DBeaver 手动执行 DDL：<br>
         <code style="display:block;margin-top:4px;font-size:10px;user-select:all">${alterTypeSql}</code>
       </div>`
    : hasExtCol
    ? `<div style="background:rgba(137,180,250,0.1);border:1px solid rgba(137,180,250,0.3);
           border-radius:5px;padding:8px 10px;margin-bottom:10px;font-size:11px;color:#89b4fa">
         ℹ 此属性当前存储在 ext JSONB。可点击「升级为实列」将其提升为独立 DB 列。
       </div>`
    : '';

  const overlay = document.createElement('div');
  overlay.className = 'onto-modal-overlay';
  overlay.innerHTML = `
    <div class="onto-modal">
      <div class="onto-modal-title">编辑属性 <code>${_he(prop.name)}</code></div>
      ${dbWarning}
      <div class="onto-form-row"><label>中文名</label><input class="onto-input" id="ePropLabel" value="${_he(prop.label_zh||'')}"></div>
      <div class="onto-form-row"><label>类型${hasRealCol ? ' ⚠' : ''}</label>
        <select class="onto-input" id="ePropType"${hasRealCol ? ' style="border-color:rgba(249,226,175,0.6)"' : ''}>
          ${['string','integer','float','boolean','date','enum'].map(t =>
            `<option value="${t}"${prop.data_type===t?' selected':''}>${t}</option>`).join('')}
        </select>
        ${hasRealCol ? `<div style="font-size:10px;color:#f9e2af;margin-top:2px">修改类型需手动执行 DDL</div>` : ''}
      </div>
      <div class="onto-form-row" id="eEnumValuesRow" style="display:${prop.data_type==='enum'?'block':'none'}"><label>选项值（逗号分隔）</label>
        <input class="onto-input" id="ePropEnumValues" value="${_he(_normEnum(prop.enum_values).join(','))}" placeholder="选项A,选项B,选项C">
      </div>
      <div class="onto-form-row onto-form-row-inline"><label>必填</label>
        <label class="onto-checkbox-label"><input type="checkbox" id="ePropReq"${prop.required?' checked':''}><span>必填</span></label>
      </div>
      <div class="onto-form-row"><label>最小值</label><input class="onto-input" id="ePropMin" type="number" value="${prop.min_val??''}"></div>
      <div class="onto-form-row"><label>最大值</label><input class="onto-input" id="ePropMax" type="number" value="${prop.max_val??''}"></div>
      <div class="onto-form-row"><label>描述</label><input class="onto-input" id="ePropDesc" value="${_he(prop.description||'')}"></div>
      <div class="onto-form-row"><label>DB列名${hasRealCol ? ' ⚠' : ''}</label>
        <input class="onto-input" id="ePropMappedCol" value="${_he(prop.mapped_column||'')}"
               ${hasRealCol ? 'style="border-color:rgba(249,226,175,0.6)"' : ''}>
        ${hasRealCol ? `<div style="font-size:10px;color:#f9e2af;margin-top:2px">改列名需手动 RENAME COLUMN</div>` : ''}
      </div>
      <div class="onto-form-row"><label>存储方式</label>
        <select class="onto-input" id="ePropStorageHint">
          <option value="meta"${prop.storage_hint==='meta'?' selected':''}>meta</option>
          <option value="entity_table"${prop.storage_hint==='entity_table'?' selected':''}>实体表列</option>
          <option value="derived"${prop.storage_hint==='derived'?' selected':''}>派生（只读）</option>
        </select>
      </div>
      <div id="eDerivedSection" style="display:${prop.storage_hint==='derived'?'block':'none'};border:1px solid var(--onto-border);border-radius:5px;padding:10px;margin-top:4px">
        <div style="font-size:11px;color:var(--onto-text3);margin-bottom:8px">派生属性从子节点计算得出，显示时只读</div>
        <div class="onto-form-row"><label>运算模式</label>
          <select class="onto-input" id="eDerivMode">
            <option value="simple"${!prop.field_config?.expr?' selected':''}>简单聚合</option>
            <option value="formula"${prop.field_config?.expr?' selected':''}>自定义公式</option>
          </select>
        </div>
        <div id="eDerivSimple" style="display:${!prop.field_config?.expr?'block':'none'}">
          <div class="onto-form-row"><label>聚合函数</label>
            <select class="onto-input" id="eAggFunc">
              ${['SUM','COUNT','AVG','MAX','MIN'].map(v =>
                `<option value="${v}"${(prop.field_config?.aggregate||'SUM')===v?' selected':''}>${v}</option>`
              ).join('')}
            </select>
          </div>
          <div class="onto-form-row"><label>子节点类型</label>
            <input class="onto-input" id="eChildNodeType" value="${_he(prop.field_config?.child_node_type||'')}" placeholder="如 operation">
          </div>
          <div class="onto-form-row"><label>子节点属性名</label>
            <input class="onto-input" id="eChildProperty" value="${_he(prop.field_config?.child_property||'')}" placeholder="如 vd_time">
          </div>
        </div>
        <div id="eDerivFormula" style="display:${prop.field_config?.expr?'block':'none'}">
          <div class="onto-form-row"><label>公式</label>
            <textarea class="onto-input" id="eDerivExpr" rows="3" style="resize:vertical;font-family:monospace;font-size:11px"
              placeholder="SUM(vd_time) / COUNT(operation)">${_he(prop.field_config?.expr||'')}</textarea>
          </div>
        </div>
      </div>
      <div class="onto-form-row onto-form-row-inline">
        <label>详情面板显示</label>
        <label class="onto-checkbox-label"><input type="checkbox" id="ePropShowDetail"${prop.show_in_detail !== false ? ' checked' : ''}><span>在工艺流程图详情面板中显示</span></label>
      </div>
      <div class="onto-form-row"><label>详情顺序</label><input class="onto-input" id="ePropDetailOrder" type="number" value="${prop.detail_order ?? 99}"></div>
      <div class="onto-modal-actions">
        ${hasExtCol ? `<button class="onto-btn" id="promoteColBtn">升级为实列</button>` : ''}
        <button class="onto-btn" id="cancelEditPropBtn">取消</button>
        <button class="onto-btn onto-btn-primary" id="saveEditPropBtn">保存元数据</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);
  overlay.querySelector('#ePropType').addEventListener('change', e => {
    overlay.querySelector('#eEnumValuesRow').style.display = e.target.value === 'enum' ? 'block' : 'none';
  });
  overlay.querySelector('#ePropStorageHint').addEventListener('change', e => {
    overlay.querySelector('#eDerivedSection').style.display = e.target.value === 'derived' ? 'block' : 'none';
  });
  overlay.querySelector('#eDerivMode')?.addEventListener('change', e => {
    overlay.querySelector('#eDerivSimple').style.display = e.target.value === 'simple' ? 'block' : 'none';
    overlay.querySelector('#eDerivFormula').style.display = e.target.value === 'formula' ? 'block' : 'none';
  });
  overlay.querySelector('#cancelEditPropBtn').addEventListener('click', () => overlay.remove());
  // 升级为实列按钮（仅 ext 状态可见）
  overlay.querySelector('#promoteColBtn')?.addEventListener('click', async () => {
    if (!await _confirm(`确认将「${prop.name}」从 ext JSONB 升级为独立 DB 列？此操作会执行 ALTER TABLE。`)) return;
    try {
      await _cf(`/api/ontology/properties/${prop.gid}/promote`, { method: 'POST' });
      overlay.remove(); _fullData = null; _schemaDiff = null; await _renderActiveTab();
      _showToast('已升级为实列', 'success');
    } catch (e) { _showToast('升级失败：' + e, 'error'); }
  });
  overlay.querySelector('#saveEditPropBtn').addEventListener('click', async () => {
    const minV = overlay.querySelector('#ePropMin').value;
    const maxV = overlay.querySelector('#ePropMax').value;
    const eStorageHint = overlay.querySelector('#ePropStorageHint').value;
    const isDerived = eStorageHint === 'derived';
    let eFieldConfig = {};
    if (isDerived) {
      const mode = overlay.querySelector('#eDerivMode')?.value || 'simple';
      if (mode === 'formula') {
        eFieldConfig = { expr: overlay.querySelector('#eDerivExpr')?.value.trim() || '' };
      } else {
        eFieldConfig = {
          aggregate:       overlay.querySelector('#eAggFunc')?.value || 'SUM',
          child_node_type: overlay.querySelector('#eChildNodeType')?.value.trim() || '',
          child_property:  overlay.querySelector('#eChildProperty')?.value.trim() || '',
        };
      }
    }
    const enumValsRaw = overlay.querySelector('#ePropEnumValues')?.value.trim() || '';
    const enumVals = enumValsRaw ? enumValsRaw.split(',').map(s => s.trim()).filter(Boolean) : [];
    try {
      await _cf(`/api/ontology/properties/${prop.gid}`, { method: 'PATCH', body: JSON.stringify({
        label_zh:      overlay.querySelector('#ePropLabel').value.trim(),
        data_type:     overlay.querySelector('#ePropType').value,
        enum_values:   enumVals,
        required:      overlay.querySelector('#ePropReq').checked,
        min_val:       minV ? parseFloat(minV) : null,
        max_val:       maxV ? parseFloat(maxV) : null,
        description:   overlay.querySelector('#ePropDesc').value.trim(),
        mapped_column: overlay.querySelector('#ePropMappedCol').value.trim() || null,
        storage_hint:  eStorageHint,
        field_config:  eFieldConfig,
        show_in_detail: overlay.querySelector('#ePropShowDetail').checked,
        detail_order:   parseInt(overlay.querySelector('#ePropDetailOrder').value) || 99,
      })});
      overlay.remove(); _fullData = null; await _renderActiveTab(); _showToast('属性已更新', 'success');
    } catch (e) { _showToast('保存失败：' + e, 'error'); }
  });
}

async function _deleteProperty(propGid) {
  if (!await _confirm('确认删除此属性？')) return;
  try {
    await _cf(`/api/ontology/properties/${propGid}`, { method: 'DELETE' });
    _fullData = null; await _renderActiveTab(); _showToast('已删除', 'success');
  } catch (e) { _showToast('删除失败：' + e, 'error'); }
}

// ── Tab 3：对象属性 ────────────────────────────────────────────────────────────
function _renderObjProps(pane) {
  const rels = (_fullData.relations || [])
    .sort((a, b) => (a.sort_order ?? 99) - (b.sort_order ?? 99) || (a.label_zh||'').localeCompare(b.label_zh||''));
  pane.innerHTML = `
    <div class="onto-section-toolbar">
      <button class="onto-btn onto-btn-sm onto-btn-primary" id="addRelBtn">+ 添加关系</button>
    </div>
    ${rels.length ? `
      <table class="onto-table">
        <thead><tr><th style="width:20px"></th><th>关系名</th><th>中文名</th><th>值域类</th><th>函数型</th><th title="拖拽行可调整详情面板显示顺序">顺序</th><th>详情</th><th></th></tr></thead>
        <tbody>${rels.map(r => `
          <tr draggable="true" data-gid="${_he(r.gid)}">
            <td class="onto-drag-cell">⠿</td>
            <td><code>${_he(r.name)}</code></td>
            <td>${_he(r.label_zh)}</td>
            <td>${_he(_allClasses.find(c => c.gid === r.range_class_gid)?.label_zh || r.range_class_gid || '-')}</td>
            <td>${r.is_functional ? '是' : '否'}</td>
            <td class="onto-num" style="color:var(--onto-text3);font-size:11px">${r.sort_order ?? '-'}</td>
            <td style="text-align:center"><input type="checkbox" class="onto-inline-toggle" data-gid="${_he(r.gid)}" data-field="show_in_detail" data-api="relations" title="在详情面板显示"${r.show_in_detail !== false ? ' checked' : ''}></td>
            <td style="white-space:nowrap">
              <button class="onto-icon-btn edit-rel-btn" data-gid="${_he(r.gid)}" title="编辑">✎</button>
              <button class="onto-icon-btn del-rel-btn" data-gid="${_he(r.gid)}" title="删除">✕</button>
            </td>
          </tr>`).join('')}
        </tbody>
      </table>` : '<p class="onto-empty-hint">暂无对象属性</p>'}`;
  document.getElementById('addRelBtn').addEventListener('click', _showAddRelModal);
  pane.querySelectorAll('.edit-rel-btn').forEach(btn => {
    const rel = rels.find(r => r.gid === btn.dataset.gid);
    if (rel) btn.addEventListener('click', () => _showAddRelModal(rel));
  });
  pane.querySelectorAll('.del-rel-btn').forEach(btn => btn.addEventListener('click', async () => {
    if (!await _confirm('确认删除此关系？')) return;
    try {
      await _cf(`/api/ontology/relations/${btn.dataset.gid}`, { method: 'DELETE' });
      _fullData = null; await _renderActiveTab(); _showToast('已删除', 'success');
    } catch (e) { _showToast('删除失败：' + e, 'error'); }
  }));
  _bindInlineToggles(pane);

  const relTbody = pane.querySelector('.onto-table tbody');
  if (relTbody) {
    _bindTableRowDrag(relTbody,
      gid => `/api/ontology/relations/${gid}`,
      () => { _fullData = null; _renderActiveTab(); }
    );
  }
}

function _showAddRelModal(editRel = null) {
  const _PRESET_RELS = [
    { name: 'usesPart',            label_zh: '装配零件',     rangeHint: 'PartLeaf' },
    { name: 'hasEquipment',        label_zh: '使用设备',     rangeHint: 'physical_equipment' },
    { name: 'hasTool',             label_zh: '使用工具',     rangeHint: 'physical_tool' },
    { name: 'hasFixture',          label_zh: '使用工装',     rangeHint: 'physical_fixture' },
    { name: 'hasPhysicalStation',  label_zh: '关联实物工位', rangeHint: 'physical_station' },
    { name: 'needsEquipment',      label_zh: '需求设备',     rangeHint: 'project_equipment' },
    { name: 'needsTool',           label_zh: '需求工具',     rangeHint: 'project_tools' },
    { name: 'needsFixture',        label_zh: '需求工装',     rangeHint: 'project_tooling' },
    { name: 'needsRole',           label_zh: '需求岗位',     rangeHint: 'project_roles' },
    { name: 'precedes',            label_zh: '紧前于',       rangeHint: null },
    { name: 'follows',             label_zh: '紧后于',       rangeHint: null },
    { name: 'isPartOf',            label_zh: '属于',         rangeHint: null },
    { name: 'references',          label_zh: '引用',         rangeHint: null },
    { name: 'sourceFrom',          label_zh: '来源于',       rangeHint: null },
  ];

  const presetOpts = _PRESET_RELS.map(r =>
    `<option value="${_he(r.name)}" data-label="${_he(r.label_zh)}" data-range-hint="${_he(r.rangeHint||'')}">${_he(r.name)} — ${_he(r.label_zh)}</option>`
  ).join('');

  const classOpts = `<option value="">（不限）</option>` +
    _allClasses.map(c => `<option value="${_he(c.gid)}" data-node-type="${_he(c.node_type_binding||'')}">${_he(c.label_zh || c.name)}</option>`).join('');

  const overlay = document.createElement('div');
  overlay.className = 'onto-modal-overlay';
  overlay.innerHTML = `
    <div class="onto-modal">
      <div class="onto-modal-title">${editRel ? '编辑对象属性（关系）' : '添加对象属性（关系）'}</div>
      <div class="onto-form-row">
        <label>关系类型</label>
        <select class="onto-input" id="nRelName">
          <option value="">— 选择常用关系 —</option>
          ${presetOpts}
          ${editRel ? `<option value="${_he(editRel.name)}" selected>${_he(editRel.name)}</option>` : ''}
        </select>
      </div>
      <div class="onto-form-row"><label>中文名</label>
        <input class="onto-input" id="nRelLabel" value="${_he(editRel?.label_zh||'')}" placeholder="选择上方关系后自动填入，可修改">
      </div>
      <div class="onto-form-row"><label>值域类（指向哪个类）</label>
        <select class="onto-input" id="nRelRange">${classOpts}</select>
      </div>
      <div class="onto-form-row onto-form-row-inline"><label>函数型</label>
        <label class="onto-checkbox-label"><input type="checkbox" id="nRelFunc"${editRel?.is_functional?' checked':''}><span>每实例至多一个值</span></label>
      </div>
      <div class="onto-form-row onto-form-row-inline"><label>详情面板显示</label>
        <label class="onto-checkbox-label"><input type="checkbox" id="nRelShowDetail"${editRel?.show_in_detail !== false ? ' checked' : ''}><span>在工艺流程图详情面板中显示</span></label>
      </div>
      <div class="onto-modal-actions">
        <button class="onto-btn" id="cancelRelBtn">取消</button>
        <button class="onto-btn onto-btn-primary" id="saveRelBtn">${editRel ? '更新' : '添加'}</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);
  // 预填值域类
  if (editRel?.range_class_gid) {
    overlay.querySelector('#nRelRange').value = editRel.range_class_gid;
  }

  // 选关系后自动填中文名 + 推荐值域类
  overlay.querySelector('#nRelName').addEventListener('change', function () {
    const opt = this.options[this.selectedIndex];
    const labelZh  = opt.dataset.label || '';
    const rangeHint = opt.dataset.rangeHint || '';
    overlay.querySelector('#nRelLabel').value = labelZh;
    if (rangeHint) {
      const rangeSelect = overlay.querySelector('#nRelRange');
      for (const o of rangeSelect.options) {
        if (o.dataset.nodeType === rangeHint) { rangeSelect.value = o.value; break; }
      }
    }
  });

  overlay.querySelector('#cancelRelBtn').addEventListener('click', () => overlay.remove());
  overlay.querySelector('#saveRelBtn').addEventListener('click', async () => {
    const name = overlay.querySelector('#nRelName').value.trim();
    if (!name) { _showToast('请选择关系类型', 'warn'); return; }
    try {
      // 编辑模式：先删除原有再新建
      if (editRel) {
        await _cf(`/api/ontology/relations/${editRel.gid}`, { method: 'DELETE' });
      }
      await _cf('/api/ontology/relations', { method: 'POST', body: JSON.stringify({
        name, label_zh: overlay.querySelector('#nRelLabel').value.trim(),
        domain_class_gid: _selectedGid,
        range_class_gid: overlay.querySelector('#nRelRange').value || null,
        is_functional: overlay.querySelector('#nRelFunc').checked,
        show_in_detail: overlay.querySelector('#nRelShowDetail').checked,
        link_type_binding: name,  // name 即 link_type，用于详情面板匹配
      })});
      overlay.remove(); _fullData = null; await _renderActiveTab();
      _showToast(editRel ? '已更新' : '已添加', 'success');
      _refreshGraph();
    } catch (e) { _showToast((editRel?'更新':'添加')+'失败：' + e, 'error'); }
  });
}

// ── Tab 4：实例 ───────────────────────────────────────────────────────────────
async function _renderIndividuals(pane) {
  const hasEntityTable  = !!_fullData.entity_table;
  const hasNodeType     = !!_fullData.node_type_binding;
  if (!hasEntityTable && !hasNodeType) {
    pane.innerHTML = '<p class="onto-empty-hint">该类未绑定实体表或 node_type，无法查询实例</p>';
    return;
  }
  pane.innerHTML = '<p class="onto-empty-hint">加载中…</p>';
  try {
    const resp = await _cf(`/api/ontology/classes/${_selectedGid}/individuals?limit=20`);
    const rows   = resp.data || [];
    const source = resp.source;
    const hint   = source === 'entity_table'
      ? `来自 <code>${_he(resp.entity_table)}</code>`
      : `来自 bop_entries（node_type = <code>${_he(resp.node_type_binding)}</code>）`;

    if (!rows.length) {
      pane.innerHTML = `<p class="onto-empty-hint">暂无实例数据（${hint.replace(/<[^>]+>/g,'')}）</p>`;
      return;
    }

    const cols = Object.keys(rows[0]);
    pane.innerHTML = `
      <div class="onto-individuals-hint">最近 ${rows.length} 条 · ${hint}</div>
      <table class="onto-table">
        <thead><tr>${cols.map(c => `<th>${_he(c)}</th>`).join('')}</tr></thead>
        <tbody>${rows.map(r => `
          <tr>${cols.map(c => `<td>${_he(r[c] ?? '-')}</td>`).join('')}</tr>`).join('')}
        </tbody>
      </table>`;
  } catch (e) { pane.innerHTML = '<p class="onto-empty-hint">加载实例失败</p>'; }
}

// ── Tab 5：规则 ───────────────────────────────────────────────────────────────
function _renderRules(pane) {
  const rules = _fullData.rules || [];
  pane.innerHTML = `
    <div class="onto-section-toolbar">
      <button class="onto-btn onto-btn-sm" id="openRuleMgmtBtn">在规则管理页编辑</button>
      <button class="onto-btn onto-btn-sm onto-btn-primary" id="addRuleBtn">+ 新增规则</button>
    </div>
    <div class="onto-rule-hint">
      以下规则在保存节点属性时自动执行。<strong>mandatory</strong> 级别规则失败将阻止保存；<strong>advisory</strong> 级别规则失败仅警告。
    </div>
    ${rules.length ? `
      <table class="onto-table">
        <thead><tr><th>规则名</th><th>级别</th><th>状态</th><th>CEL 表达式</th><th>操作</th></tr></thead>
        <tbody>${rules.map(r => `
          <tr>
            <td>${_he(r.name)}</td>
            <td><span class="onto-type-badge onto-enf-${_he(r.enforcement_level)}">${_he(r.enforcement_level)}</span></td>
            <td><span class="onto-status-badge onto-status-${_he(r.status)}">${_he(r.status)}</span></td>
            <td><code class="onto-cel-expr">${_he(r.expression||'-')}</code></td>
            <td style="white-space:nowrap">
              <button class="onto-btn onto-btn-sm edit-rule-btn" data-gid="${_he(r.gid)}" title="编辑">编辑</button>
              <button class="onto-btn onto-btn-sm run-rule-btn" data-gid="${_he(r.gid)}" data-name="${_he(r.name)}">运行</button>
            </td>
          </tr>`).join('')}
        </tbody>
      </table>` : '<p class="onto-empty-hint">该类暂无关联 CEL 规则。<br>点击「新增规则」或在规则管理页将规则绑定到此类。</p>'}`;
  document.getElementById('openRuleMgmtBtn')?.addEventListener('click', () =>
    window.parent?.TabManager?.open('rule'));
  document.getElementById('addRuleBtn')?.addEventListener('click', () => _showEditRuleModal(null));
  pane.querySelectorAll('.edit-rule-btn').forEach(btn => {
    const rule = rules.find(r => r.gid === btn.dataset.gid);
    if (rule) btn.addEventListener('click', () => _showEditRuleModal(rule));
  });
  pane.querySelectorAll('.run-rule-btn').forEach(btn =>
    btn.addEventListener('click', () => _runRuleCheck(btn.dataset.gid, btn.dataset.name)));
}

function _showEditRuleModal(rule) {
  const isNew = !rule;
  const overlay = document.createElement('div');
  overlay.className = 'onto-modal-overlay';
  overlay.innerHTML = `
    <div class="onto-modal">
      <div class="onto-modal-title">${isNew ? '新增规则' : '编辑规则'}</div>
      <div class="onto-form-row"><label>规则名</label>
        <input class="onto-input" id="eRuleName" value="${_he(rule?.name||'')}" placeholder="rule_name">
      </div>
      <div class="onto-form-row"><label>级别</label>
        <select class="onto-input" id="eRuleLevel">
          ${['advisory','mandatory'].map(l =>
            `<option value="${l}"${(rule?.enforcement_level||'advisory')===l?' selected':''}>${l}</option>`).join('')}
        </select>
      </div>
      <div class="onto-form-row"><label>状态</label>
        <select class="onto-input" id="eRuleStatus">
          ${['active','inactive','draft'].map(s =>
            `<option value="${s}"${(rule?.status||'active')===s?' selected':''}>${s}</option>`).join('')}
        </select>
      </div>
      <div class="onto-form-row"><label>CEL 表达式</label>
        <textarea class="onto-input" id="eRuleExpr" rows="3" style="resize:vertical;font-family:monospace">${_he(rule?.expression||'')}</textarea>
      </div>
      <div class="onto-modal-actions">
        <button class="onto-btn" id="cancelRuleBtn">取消</button>
        <button class="onto-btn onto-btn-primary" id="saveRuleBtn">${isNew ? '创建' : '保存'}</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);
  overlay.querySelector('#cancelRuleBtn').addEventListener('click', () => overlay.remove());
  overlay.querySelector('#saveRuleBtn').addEventListener('click', async () => {
    const name       = overlay.querySelector('#eRuleName').value.trim();
    const level      = overlay.querySelector('#eRuleLevel').value;
    const status     = overlay.querySelector('#eRuleStatus').value;
    const expression = overlay.querySelector('#eRuleExpr').value.trim();
    if (!name) { _showToast('规则名不能为空', 'warn'); return; }
    try {
      if (isNew) {
        await _cf('/api/rules', { method: 'POST', body: JSON.stringify({
          name, enforcement_level: level, status, expression,
          context_class_gid: _selectedGid,
        })});
        _showToast('规则已创建', 'success');
      } else {
        await _cf(`/api/rules/${rule.gid}`, { method: 'PATCH', body: JSON.stringify({
          name, enforcement_level: level, status, expression,
        })});
        _showToast('规则已更新', 'success');
      }
      overlay.remove(); _fullData = null; await _renderActiveTab();
    } catch (e) { _showToast('操作失败：' + e, 'error'); }
  });
}

async function _runRuleCheck(ruleGid, ruleName) {
  const ctx = await _prompt(`输入 JSON context 测试「${ruleName}」：`, '{}');
  if (ctx === null) return;
  let context;
  try { context = JSON.parse(ctx); } catch { _showToast('JSON 格式错误', 'error'); return; }
  try {
    const resp = await _cf('/api/rule-engine/check', { method: 'POST', body: JSON.stringify({ rule_gid: ruleGid, context }) });
    const r = resp.result;
    _showToast(`结果：${r.toUpperCase()}${resp.message ? ' — ' + resp.message : ''}`,
      r === 'pass' ? 'success' : r === 'fail' ? 'error' : 'warn');
  } catch (e) { _showToast('运行失败：' + e, 'error'); }
}

// ── 类 CRUD ───────────────────────────────────────────────────────────────────
async function _createChildClass(parent) {
  const labelZh = await _prompt('新类的中文名称：');
  if (!labelZh) return;
  const name = await _prompt('标识符（英文/下划线）：', labelZh.toLowerCase().replace(/\s+/g,'_').replace(/[^\w]/g,''));
  if (!name) return;
  try {
    await _cf('/api/ontology/classes', { method: 'POST', body: JSON.stringify({
      name, label_zh: labelZh, parent_gid: parent?.gid || null, sort_order: 0,
    })});
    await _loadAndRender();
    _showToast('类已创建', 'success');
  } catch (e) { _showToast('创建失败：' + e, 'error'); }
}

async function _reparentClass(cls) {
  const opts = _allClasses.filter(c => c.gid !== cls.gid)
    .map(c => `${c.label_zh || c.name} (${c.name})`).join('\n');
  const choice = await _prompt(`将「${cls.label_zh||cls.name}」移动到哪个父类？\n（留空=根类）\n${opts}`);
  if (choice === null) return;
  const target = _allClasses.find(c => c.label_zh === choice.trim() || c.name === choice.trim());
  try {
    await _cf(`/api/ontology/classes/${cls.gid}`, { method: 'PATCH',
      body: JSON.stringify({ parent_gid: target?.gid || null }) });
    await _loadAndRender();
    _showToast('父类已变更', 'success');
  } catch (e) { _showToast('变更失败：' + e, 'error'); }
}

async function _deleteClass(cls) {
  if (!await _confirm(`确认删除「${cls.label_zh||cls.name}」？\n（需先删除所有子类和关联规则）`)) return;
  try {
    await _cf(`/api/ontology/classes/${cls.gid}`, { method: 'DELETE' });
    if (_selectedGid === cls.gid) {
      _selectedGid = null; _fullData = null;
      document.getElementById('ontoDetailEmpty').style.display = '';
      document.getElementById('ontoDetailBody').style.display  = 'none';
    }
    await _loadAndRender();
    _showToast('类已删除', 'success');
  } catch (e) { _showToast('删除失败：' + e, 'error'); }
}

// ── Seed ──────────────────────────────────────────────────────────────────────
async function _runSeed() {
  if (!await _confirm('将从 BOP node_types 预填初始类（幂等）。确认？')) return;
  try {
    const resp = await _cf('/api/ontology/seed', { method: 'POST' });
    await _loadAndRender();
    _showToast(resp.message || 'Seed 完成', 'success');
  } catch (e) { _showToast('Seed 失败：' + e, 'error'); }
}

document.addEventListener('DOMContentLoaded', _init);

async function _renderCardinalityAxioms(pane, classGid) {
  let sec = pane.querySelector('#ontoAxiomsSection');
  if (!sec) {
    sec = document.createElement('div');
    sec.id = 'ontoAxiomsSection';
    sec.style.marginTop = '16px';
    pane.appendChild(sec);
  }
  let axioms = [];
  try {
    const res = await _cf(`/api/ontology/classes/${classGid}/axioms`);
    axioms = res.data || [];
  } catch (_) {}

  const childCls = _allClasses.filter(c => c.parent_gid === classGid && c.node_type_binding);
  sec.innerHTML = `
    <div class="onto-section-toolbar" style="margin-top:8px">
      <span style="font-size:11px;color:var(--subtext0,#a6adc8)">基数约束（子节点数量限制）</span>
      <button class="onto-btn onto-btn-sm onto-btn-primary" id="addAxiomBtn">+ 添加</button>
    </div>
    ${axioms.length ? `
      <table class="onto-table">
        <thead><tr><th>约束类型</th><th>子节点类</th><th>数量</th><th></th></tr></thead>
        <tbody>${axioms.map(ax => `
          <tr>
            <td><span class="onto-type-badge">${_he(ax.axiom_type)}</span></td>
            <td>${_he(ax.prop_label || ax.child_nt || ax.target_gid || '-')}</td>
            <td><strong>${_he(ax.expression || '-')}</strong></td>
            <td><button class="onto-icon-btn del-axiom-btn" data-gid="${_he(ax.gid)}">✕</button></td>
          </tr>`).join('')}
        </tbody>
      </table>` : '<p class="onto-empty-hint" style="font-size:11px">暂无基数约束</p>'}`;

  sec.querySelector('#addAxiomBtn')?.addEventListener('click', () =>
    _showAddAxiomModal(classGid, childCls));
  sec.querySelectorAll('.del-axiom-btn').forEach(btn =>
    btn.addEventListener('click', async () => {
      if (!await _confirm('确认删除此基数约束？')) return;
      try {
        await _cf(`/api/ontology/axioms/${btn.dataset.gid}`, { method: 'DELETE' });
        _fullData = null; await _renderActiveTab(); _showToast('已删除', 'success');
      } catch(e) { _showToast('删除失败：' + e, 'error'); }
    }));
}

function _showAddAxiomModal(classGid, childClasses) {
  const overlay = document.createElement('div');
  overlay.className = 'onto-modal-overlay';
  const classOpts = childClasses.map(c =>
    `<option value="${_he(c.gid)}" data-nt="${_he(c.node_type_binding||'')}">` +
    `${_he(c.label_zh || c.name)} (${_he(c.node_type_binding || '')})</option>`).join('');
  overlay.innerHTML = `
    <div class="onto-modal">
      <div class="onto-modal-title">添加基数约束</div>
      <div class="onto-form-row"><label>约束类型 *</label>
        <select class="onto-input" id="axType">
          <option value="minCardinality">minCardinality（至少 N 个）</option>
          <option value="maxCardinality">maxCardinality（最多 N 个）</option>
          <option value="exactCardinality">exactCardinality（恰好 N 个）</option>
        </select>
      </div>
      <div class="onto-form-row"><label>子节点类 *</label>
        <select class="onto-input" id="axTarget">
          <option value="">— 选择子节点类 —</option>${classOpts}
        </select>
      </div>
      <div class="onto-form-row"><label>数量 N *</label>
        <input class="onto-input" id="axExpr" type="number" min="0" placeholder="如：1">
      </div>
      <div class="onto-modal-actions">
        <button class="onto-btn" id="cancelAxBtn">取消</button>
        <button class="onto-btn onto-btn-primary" id="saveAxBtn">添加</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);
  overlay.querySelector('#cancelAxBtn').addEventListener('click', () => overlay.remove());
  overlay.querySelector('#saveAxBtn').addEventListener('click', async () => {
    const axiomType = overlay.querySelector('#axType').value;
    const targetGid = overlay.querySelector('#axTarget').value;
    const expression = overlay.querySelector('#axExpr').value.trim();
    if (!targetGid || !expression) { _showToast('请填写完整', 'warn'); return; }
    try {
      await _cf('/api/ontology/axioms', { method: 'POST', body: JSON.stringify({
        class_gid: classGid, axiom_type: axiomType,
        target_gid: targetGid, expression,
      })});
      overlay.remove(); _fullData = null; await _renderActiveTab(); _showToast('约束已添加', 'success');
    } catch(e) { _showToast('添加失败：' + e, 'error'); }
  });
}

// ── DB 表列表加载（供 select 使用，模块级缓存）──────────────────────────────
let _dbTablesCache = null;

async function _getDbTables() {
  if (_dbTablesCache) return _dbTablesCache;
  try {
    const r = await _cf('/api/ontology/db-tables');
    _dbTablesCache = r.data || [];
  } catch { _dbTablesCache = []; }
  return _dbTablesCache;
}

async function _loadDbTablesInto(selectId, currentVal) {
  const sel = document.getElementById(selectId);
  if (!sel) return;
  const tables = await _getDbTables();
  const opts = tables.map(t =>
    `<option value="${_he(t)}"${t === currentVal ? ' selected' : ''}>${_he(t)}</option>`
  ).join('');
  sel.innerHTML = `<option value="">— 未绑定 —</option>${opts}`;
  if (currentVal) sel.value = currentVal;
}

// ── 绑定实体表弹窗 ─────────────────────────────────────────────────────────
async function _showBindTableModal() {
  const overlay = document.createElement('div');
  overlay.className = 'onto-modal-overlay';
  overlay.innerHTML = `<div class="onto-modal" style="max-width:680px;max-height:80vh;display:flex;flex-direction:column">
    <div class="onto-modal-title">绑定实体表</div>
    <div style="font-size:11px;color:var(--onto-text3);margin-bottom:10px">
      未绑定实体表的类（含有 node_type_binding 的具体类优先关注）
    </div>
    <div id="bindTableBody" style="flex:1;overflow-y:auto;min-height:200px">
      <div style="color:var(--onto-text3);font-size:11px;padding:12px">加载中…</div>
    </div>
    <div class="onto-modal-actions" style="margin-top:12px">
      <button class="onto-btn" id="bindTableCancel">关闭</button>
      <button class="onto-btn onto-btn-primary" id="bindTableSave">保存所有更改</button>
    </div>
  </div>`;
  document.body.appendChild(overlay);
  overlay.querySelector('#bindTableCancel').addEventListener('click', () => overlay.remove());

  // 并行加载：类列表 + DB 表列表
  const [classResp, tables] = await Promise.all([
    _cf('/api/ontology/unbound-classes').catch(() => ({ data: [] })),
    _getDbTables(),
  ]);
  const classes = classResp.data || [];
  const tableOpts = tables.map(t => `<option value="${_he(t)}">${_he(t)}</option>`).join('');

  const body = overlay.querySelector('#bindTableBody');
  if (!classes.length) {
    body.innerHTML = '<div style="color:var(--onto-text3);font-size:11px;padding:12px">所有类均已绑定实体表</div>';
    return;
  }

  body.innerHTML = `<table style="width:100%;border-collapse:collapse;font-size:12px">
    <thead><tr style="background:var(--onto-bg2)">
      <th style="padding:6px 10px;text-align:left;font-weight:600;color:var(--onto-text3)">类</th>
      <th style="padding:6px 10px;text-align:left;font-weight:600;color:var(--onto-text3)">node_type</th>
      <th style="padding:6px 10px;text-align:left;font-weight:600;color:var(--onto-text3)">当前实体表</th>
      <th style="padding:6px 10px;text-align:left;font-weight:600;color:var(--onto-text3)">选择绑定</th>
    </tr></thead>
    <tbody>
      ${classes.map(c => `
        <tr style="border-bottom:1px solid var(--onto-border)" data-gid="${_he(c.gid)}">
          <td style="padding:6px 10px">${_he(c.label_zh || c.name)}</td>
          <td style="padding:6px 10px;color:var(--onto-text3);font-size:11px">
            ${c.node_type_binding ? `<code>${_he(c.node_type_binding)}</code>` : '<span style="opacity:.4">—</span>'}
          </td>
          <td style="padding:6px 10px;font-size:11px;color:${c.entity_table ? 'var(--onto-accent)' : 'var(--onto-text4)'}">
            ${c.entity_table ? _he(c.entity_table) : '未绑定'}
          </td>
          <td style="padding:6px 10px">
            <select class="onto-input bind-table-sel" data-gid="${_he(c.gid)}" style="width:100%;font-size:11px">
              <option value="">— 不变 / 清除 —</option>
              ${tableOpts}
            </select>
          </td>
        </tr>`).join('')}
    </tbody>
  </table>`;

  // 预选当前已有的值
  classes.forEach(c => {
    if (c.entity_table) {
      const sel = body.querySelector(`select[data-gid="${c.gid}"]`);
      if (sel) sel.value = c.entity_table;
    }
  });

  overlay.querySelector('#bindTableSave').addEventListener('click', async () => {
    const sels = body.querySelectorAll('.bind-table-sel');
    const patches = [];
    sels.forEach(sel => {
      const gid = sel.dataset.gid;
      const orig = classes.find(c => c.gid === gid)?.entity_table || '';
      const newVal = sel.value;
      if (newVal !== orig) {
        patches.push(
          _cf(`/api/ontology/classes/${gid}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ entity_table: newVal || null }),
          }).catch(() => null)
        );
        // 同步更新 _allClasses 本地缓存
        const cls = _allClasses.find(c => c.gid === gid);
        if (cls) cls.entity_table = newVal || null;
      }
    });
    if (!patches.length) { _showToast('无变更', 'info'); overlay.remove(); return; }
    await Promise.all(patches);
    _dbTablesCache = null;
    overlay.remove();
    _fullData = null;
    await _loadAndRender();
    _showToast(`已保存 ${patches.length} 处绑定`, 'success');
  });
}

async function _loadNodeTypeSuggestionsInto(selectId, currentVal) {
  const sel = document.getElementById(selectId);
  if (!sel) return;
  try {
    const r = await _cf('/api/ontology/node-type-suggestions');
    const vals = r.data || [];
    const isCustom = currentVal && !vals.includes(currentVal);
    if (isCustom) vals.push(currentVal);
    sel.innerHTML =
      `<option value="">— 无绑定 —</option>` +
      vals.map(v => `<option value="${_he(v)}"${v === currentVal ? ' selected' : ''}>${_he(v)}</option>`).join('') +
      `<option value="__custom__"${isCustom ? '' : ''}>✏ 手动输入…</option>`;
    // 如果是自定义值，显示文本框并填入
    const custom = document.getElementById('annBindingCustom');
    if (custom && isCustom) {
      sel.value = '__custom__';
      custom.style.display = 'block';
      custom.value = currentVal;
    }
  } catch {}
}

// ── helper: 确保 enum_values 始终是数组 ──
function _normEnum(v) {
  if (Array.isArray(v)) return v;
  if (typeof v === 'string') {
    try { const p = JSON.parse(v); return Array.isArray(p) ? p : [v]; } catch { return v ? [v] : []; }
  }
  return [];
}
