// ── GBOP 节点类型 ─────────────────────────────────────────────────
const GBOP_NODE_TYPES = {
  version:   '版本',
  system:    '系统',
  device:    '装置',
  part:      '零部件',
  process:   '总装工序',
  operation: '总装操作',
};

// ── 列定义 ────────────────────────────────────────────────────────
const GBOP_COLUMNS = [
  { key: 'node_type',         label: '节点类型',     width: 100, type: 'text',     visible: true },
  { key: 'level',             label: 'Level',        width: 50,  type: 'number',   visible: true },
  { key: 'vpps',              label: 'VPPS',         width: 130, type: 'text',     visible: true },
  { key: 'vpps_desc',         label: 'VPPS描述',     flex: 3,    type: 'text',     visible: true },
  { key: 'vpps_attr',         label: 'VPPS属性',     width: 100, type: 'text',     visible: true },
  { key: 'importance',        label: '重要度',       width: 80,  type: 'text',     visible: true },
  { key: 'torque_importance', label: '扭矩重要度',   width: 90,  type: 'text',     visible: true },
  { key: 'vehicle_model',     label: '车型',         width: 80,  type: 'text',     visible: true },
  { key: 'parent_vpps',       label: '父级VPPS',     width: 120, type: 'text',     visible: true },
  { key: 'status',            label: '状态',         width: 70,  type: 'text',     visible: true },
  { key: 'seq_no',            label: '序号',         width: 60,  type: 'number',   visible: true },
  { key: '_actions',           label: '',             width: 145, visible: true, alwaysVisible: true },
  { key: 'created_by',        label: '创建人',       width: 90,  type: 'text',     visible: false },
  { key: 'created_at',        label: '创建时间',     width: 140, type: 'datetime', visible: false },
  { key: 'updated_at',        label: '更新时间',     width: 140, type: 'datetime', visible: false },
];

const GBOP_CELL_RENDERER = {
  node_type: (val) => {
    const label = GBOP_NODE_TYPES[val] || val || '—';
    return `<span class="gbop-nt-badge gbop-nt-${val}">${label}</span>`;
  },
  _actions: (_, row) =>
    `<span class="gbop-row-actions">
       <button class="btn-xs btn-ghost" data-act="edit"  data-gid="${row.gid}">编辑</button>
       <button class="btn-xs btn-ghost" data-act="child" data-gid="${row.gid}">+子</button>
       <button class="btn-xs btn-ghost" style="color:var(--danger)" data-act="del" data-gid="${row.gid}">删除</button>
     </span>`,
};

// ── State ─────────────────────────────────────────────────────────
let _shell = null;
let _currentVersion = null;
let _gbopVersions = [];
let _familyCollapsed = new Set();
let _arcOpen = false;

// ── Helpers ────────────────────────────────────────────────────────
function openModal(id)  { document.getElementById(id)?.classList.remove('hidden'); }
function closeModal(id) { document.getElementById(id)?.classList.add('hidden'); }

function _toast(msg, type = 'info') {
  const el = document.createElement('div');
  el.className = `gbop-toast gbop-toast-${type}`;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), 3000);
}

// ── 加载条目 ─────────────────────────────────────────────────────
async function load() {
  if (!_currentVersion) return;
  try {
    const json = await ListShell._cf(`/api/gbop/versions/${_currentVersion}/entries`);
    _shell.setRows(json.data || []);
  } catch (e) { _toast('加载失败: ' + e.message, 'error'); }
}

// ── ListShell 初始化 ──────────────────────────────────────────────
function _initShell() {
  _shell = new ListShell({
    mountEl:    document.getElementById('appRoot'),
    itemType:   'gbop_version',
    moduleId:   'gbop',
    columns:    GBOP_COLUMNS,
    cellRenderer: GBOP_CELL_RENDERER,

    title:     'GBOP 标准工序',
    titleIcon: '#icon-factory',
    newLabel:  '新建节点',
    onNew:     () => {
      if (!_currentVersion) { _toast('请先选择版本', 'warn'); return; }
      _openNewEntryModal();
    },

    extraToolbarBtns: [
      { id: 'btn-import-vpps', label: '从VPPS零件导入', btnStyle: 'ie', sepBefore: true,
        icon: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:4px"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>',
        onClick: () => { if (!_currentVersion) { _toast('请先选择版本', 'warn'); return; } openModal('modal-import-vpps'); } },
      { id: 'btn-import-tc-excel', label: '从TC Excel导入', btnStyle: 'ie',
        icon: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:4px"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/></svg>',
        onClick: () => {
          if (!_currentVersion) { _toast('请先选择版本', 'warn'); return; }
          document.getElementById('inp-tc-excel-file').value = '';
          document.getElementById('tc-excel-result').textContent = '';
          openModal('modal-import-tc-excel');
        } },
      { id: 'btn-lineage-view', label: '树形视图', btnStyle: 'ie', sepBefore: true,
        icon: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:4px"><rect x="2" y="9" width="4" height="6" rx="1"/><rect x="10" y="4" width="4" height="6" rx="1"/><rect x="10" y="14" width="4" height="6" rx="1"/><rect x="18" y="6" width="4" height="4" rx="1"/><rect x="18" y="14" width="4" height="4" rx="1"/><line x1="6" y1="12" x2="10" y2="7"/><line x1="6" y1="12" x2="10" y2="17"/><line x1="14" y1="7" x2="18" y2="8"/><line x1="14" y1="17" x2="18" y2="16"/></svg>',
        onClick: () => {
          if (!_currentVersion) { _toast('请先选择版本', 'warn'); return; }
          const sel = _gbopVersions.find(v => v.gid === _currentVersion);
          window.top.postMessage({
            type: 'tab:open',
            id: 'gbop_lineage',
            params: { gbop_version_gid: _currentVersion, version_name: sel?.name || '' },
          }, '*');
        }},
    ],

    sidebarOnCreate: () => openModal('modal-new-version'),
    sidebarDisableInlineRename: true,
    sidebarOnContextMenu: (x, y, ver) => _showVerCtxMenu(x, y, ver),

    onSelect: (gid) => { _currentVersion = gid; load(); },

    onRowsChange: async (rows, extra) => {
      const { changedRow, action } = extra || {};
      if (action === 'edit' && changedRow?.gid) {
        try {
          await ListShell._cf(`/api/gbop/entries/${changedRow.gid}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(changedRow),
          });
          await load();
        } catch (e) { _toast('保存失败: ' + e.message, 'error'); }
      } else if (!changedRow?.gid && changedRow?.vpps_desc) {
        if (!_currentVersion) { _toast('请先选择版本', 'warn'); return; }
        try {
          // 默认创建为通用 entry（非 process/operation）
          await ListShell._cf('/api/gbop/entries', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ version_gid: _currentVersion, node_type: 'part', vpps_desc: changedRow.vpps_desc }),
          });
          await load();
        } catch (e) { _toast('创建失败: ' + e.message, 'error'); }
      }
    },

    enablePagination: true,
    pageSize: 200,

    extraContextItems: () => [
      { label: '添加子节点', action: 'add_child' },
      { label: '编辑节点',   action: 'edit' },
      { label: '删除节点',   action: 'del', danger: true },
    ],
    onContextAction: (action, row) => {
      if (action === 'add_child') _openNewEntryModal(row.gid);
      if (action === 'edit')      _openEditEntryModal(row);
      if (action === 'del')       _deleteEntry(row.gid);
    },
  });
}

// ── 版本侧边栏（自定义分组渲染）──────────────────────────────────
async function _loadVersions() {
  try {
    const json = await ListShell._cf('/api/gbop/versions?include_archived=true');
    _gbopVersions = json.data || [];
  } catch (e) { console.warn('[GBOP] 加载版本失败:', e); }
}

function _renderGbopSidebar(scrollEl) {
  scrollEl.innerHTML = '';

  const familyMap = new Map();
  for (const ver of _gbopVersions) {
    const fgid = ver.version_family_gid || ver.gid;
    if (!familyMap.has(fgid)) {
      familyMap.set(fgid, { name: ver.name || '未命名GBOP', archived: !!ver.archived_at, versions: [] });
    }
    const fam = familyMap.get(fgid);
    fam.versions.push(ver);
    if (!ver.archived_at) fam.archived = false;
  }

  const active   = [...familyMap.entries()].filter(([, f]) => !f.archived);
  const archived = [...familyMap.entries()].filter(([, f]) =>  f.archived);

  for (const [fgid, fam] of active) _renderFamilyGroup(scrollEl, fgid, fam, false);

  if (archived.length) {
    const arcHdr = document.createElement('div');
    arcHdr.className = 'gbop-arc-section-hdr';
    arcHdr.innerHTML = `
      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
           style="transition:transform .15s;transform:${_arcOpen ? 'rotate(90deg)' : ''}">
        <polyline points="9 18 15 12 9 6"/>
      </svg>
      <span>已归档 (${archived.length})</span>`;
    arcHdr.addEventListener('click', () => { _arcOpen = !_arcOpen; _shell?.sidebar?._renderItems(); });
    scrollEl.appendChild(arcHdr);
    if (_arcOpen) {
      for (const [fgid, fam] of archived) _renderFamilyGroup(scrollEl, fgid, fam, true);
    }
  }
}

function _renderFamilyGroup(scrollEl, fgid, fam, isArchived) {
  const collapsed = _familyCollapsed.has(fgid);

  const hdr = document.createElement('div');
  hdr.className = 'gbop-fam-hdr';
  hdr.innerHTML = `
    <svg class="gbop-fam-arrow${collapsed ? '' : ' open'}" width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
      <polyline points="9 18 15 12 9 6"/>
    </svg>
    <span class="gbop-fam-name">${ListShell._esc(fam.name)}</span>
    <button class="gbop-fam-arc-btn" title="${isArchived ? '解除归档' : '归档'}">
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        ${isArchived
          ? '<polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1014.85-3.36L23 1"/>'
          : '<path d="M21 8v13H3V8"/><path d="M1 3h22v5H1z"/><path d="M10 12h4"/>'}
      </svg>
    </button>`;

  hdr.addEventListener('click', (e) => {
    if (e.target.closest('.gbop-fam-arc-btn')) return;
    if (_familyCollapsed.has(fgid)) _familyCollapsed.delete(fgid); else _familyCollapsed.add(fgid);
    _shell?.sidebar?._renderItems();
  });

  hdr.querySelector('.gbop-fam-arc-btn').addEventListener('click', async (e) => {
    e.stopPropagation();
    try {
      if (isArchived) {
        await ListShell._cf(`/api/gbop/version-families/${fgid}/archive`, { method: 'DELETE' });
      } else {
        await ListShell._cf(`/api/gbop/version-families/${fgid}/archive`, { method: 'POST' });
      }
      await _refreshSidebar();
    } catch (err) { _toast('操作失败: ' + err.message, 'error'); }
  });

  scrollEl.appendChild(hdr);
  if (collapsed) return;

  for (const ver of fam.versions) {
    const item = document.createElement('div');
    item.className = 'gbop-ver-item' + (ver.gid === _currentVersion ? ' active' : '');
    item.dataset.gid = ver.gid;

    const isFrozen = !!ver.frozen_at;
    const statusLabel = isFrozen ? '冻结' : (ver.status === 'draft' ? '草稿' : ver.status === 'active' ? '激活' : '');

    item.innerHTML = `
      <span class="gbop-ver-dot ${isFrozen ? 'frozen' : ''}"></span>
      <span class="gbop-ver-name">${ListShell._esc(ver.name || '未命名')}</span>
      ${statusLabel ? `<span class="gbop-ver-status gbop-vs-${isFrozen ? 'frozen' : ver.status}">${statusLabel}</span>` : ''}
      <button class="gbop-ver-ctx-btn" title="更多操作">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="5" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="12" cy="19" r="1"/>
        </svg>
      </button>`;

    item.addEventListener('click', (e) => {
      if (e.target.closest('.gbop-ver-ctx-btn')) return;
      _shell?.sidebar?._onSelect(ver.gid);
      _shell?.sidebar?._renderItems();
    });

    item.querySelector('.gbop-ver-ctx-btn').addEventListener('click', (e) => {
      e.stopPropagation();
      _showVerCtxMenu(e.clientX, e.clientY, ver);
    });

    scrollEl.appendChild(item);
  }
}

// ── 版本右键菜单 ─────────────────────────────────────────────────
function _showVerCtxMenu(x, y, ver) {
  // 移除旧菜单
  document.querySelectorAll('.gbop-ctx-menu').forEach(el => el.remove());

  const menu = document.createElement('div');
  menu.className = 'gbop-ctx-menu';
  menu.style.cssText = `position:fixed;left:${x}px;top:${y}px;z-index:9999`;

  const items = [
    { label: '编辑属性', action: () => _openEditVersionModal(ver) },
    { label: '新增版本到此族', action: () => _openNewVersionInFamily(ver) },
    { label: 'Fork', action: () => _openForkModal(ver) },
    ver.frozen_at ? null : { label: '冻结', action: () => _freezeVersion(ver.gid) },
  ].filter(Boolean);

  for (const it of items) {
    const btn = document.createElement('button');
    btn.textContent = it.label;
    btn.addEventListener('click', () => { menu.remove(); it.action(); });
    menu.appendChild(btn);
  }

  document.body.appendChild(menu);
  const close = (e) => { if (!menu.contains(e.target)) { menu.remove(); document.removeEventListener('click', close, true); } };
  setTimeout(() => document.addEventListener('click', close, true), 0);
}

// ── 版本操作 ──────────────────────────────────────────────────────
async function _freezeVersion(gid) {
  try {
    await ListShell._cf(`/api/gbop/versions/${gid}/freeze`, { method: 'POST' });
    _toast('版本已冻结', 'success');
    await _refreshSidebar();
  } catch (e) { _toast('冻结失败: ' + e.message, 'error'); }
}

function _openEditVersionModal(ver) {
  document.getElementById('inp-editver-gid').value = ver.gid;
  document.getElementById('inp-editver-name').value = ver.name || '';
  document.getElementById('inp-editver-vehicle').value = ver.vehicle_model || '';
  document.getElementById('inp-editver-status').value = ver.status || 'draft';
  openModal('modal-edit-version');
}

function _openNewVersionInFamily(ver) {
  document.getElementById('inp-ver-family-gid').value = ver.version_family_gid || ver.gid;
  document.getElementById('inp-ver-name').value = ver.name || '';
  document.getElementById('inp-ver-name').disabled = true;
  document.getElementById('inp-ver-family-hint').classList.remove('hidden');
  openModal('modal-new-version');
}

function _openForkModal(ver) {
  // 填充 family 选择器
  const forkFamilySel = document.getElementById('inp-fork-family');
  const families = new Map();
  for (const v of _gbopVersions) {
    const fgid = v.version_family_gid || v.gid;
    if (!families.has(fgid)) families.set(fgid, v.name || '未命名');
  }
  forkFamilySel.innerHTML = '<option value="">-- 继承来源版本族 --</option>';
  for (const [fgid, name] of families) {
    forkFamilySel.innerHTML += `<option value="${fgid}">${ListShell._esc(name)}</option>`;
  }
  document.getElementById('modal-fork').dataset.sourceGid = ver.gid;
  openModal('modal-fork');
}

// ── 节点操作 ──────────────────────────────────────────────────────
function _openNewEntryModal(parentGid = null) {
  const modal = document.getElementById('modal-new-entry');
  delete modal.dataset.editGid;
  document.querySelector('#modal-new-entry .modal-title').textContent = '新建节点';
  document.getElementById('inp-entry-parent-gid').value = parentGid || '';
  document.getElementById('inp-entry-type').value = 'process';
  document.getElementById('inp-entry-name').value = '';
  document.getElementById('inp-entry-vpps').value = '';
  document.getElementById('inp-entry-vpps-desc').value = '';
  document.getElementById('inp-entry-seq').value = '0';
  openModal('modal-new-entry');
}

function _openEditEntryModal(row) {
  // 复用新建 modal，标记 gid
  document.getElementById('modal-new-entry').dataset.editGid = row.gid;
  document.getElementById('inp-entry-parent-gid').value = row.parent_gid || '';
  document.getElementById('inp-entry-type').value = row.node_type || 'process';
  document.getElementById('inp-entry-name').value = row.vpps_desc || '';
  document.getElementById('inp-entry-vpps').value = row.vpps || '';
  document.getElementById('inp-entry-vpps-desc').value = row.vpps_desc || '';
  document.getElementById('inp-entry-seq').value = row.seq_no ?? 0;
  document.querySelector('#modal-new-entry .modal-title').textContent = '编辑节点';
  openModal('modal-new-entry');
}

async function _deleteEntry(gid) {
  if (!confirm('确定删除此节点及其所有子节点？')) return;
  try {
    await ListShell._cf(`/api/gbop/entries/${gid}`, { method: 'DELETE' });
    await load();
    _toast('已删除', 'success');
  } catch (e) { _toast('删除失败: ' + e.message, 'error'); }
}

// ── 刷新侧边栏 ──────────────────────────────────────────────────
async function _refreshSidebar() {
  await _loadVersions();
  _shell?.sidebar?._renderItems();
}

// ── 事件绑定 ──────────────────────────────────────────────────────
function _bindEvents() {
  // 新建版本
  document.getElementById('btn-confirm-new-version')?.addEventListener('click', async () => {
    const name = document.getElementById('inp-ver-name').value.trim();
    const vehicle = document.getElementById('inp-ver-vehicle').value.trim();
    const familyGid = document.getElementById('inp-ver-family-gid').value || null;
    if (!name) { _toast('请输入名称', 'warn'); return; }
    try {
      await ListShell._cf('/api/gbop/versions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, vehicle_model: vehicle, version_family_gid: familyGid }),
      });
      closeModal('modal-new-version');
      document.getElementById('inp-ver-name').disabled = false;
      document.getElementById('inp-ver-family-hint').classList.add('hidden');
      document.getElementById('inp-ver-family-gid').value = '';
      await _refreshSidebar();
      _toast('版本创建成功', 'success');
    } catch (e) { _toast('创建失败: ' + e.message, 'error'); }
  });

  // 编辑版本
  document.getElementById('btn-confirm-edit-version')?.addEventListener('click', async () => {
    const gid = document.getElementById('inp-editver-gid').value;
    const name = document.getElementById('inp-editver-name').value.trim();
    const vehicle = document.getElementById('inp-editver-vehicle').value.trim();
    const status = document.getElementById('inp-editver-status').value;
    try {
      await ListShell._cf(`/api/gbop/versions/${gid}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, vehicle_model: vehicle, status }),
      });
      closeModal('modal-edit-version');
      await _refreshSidebar();
      _toast('已保存', 'success');
    } catch (e) { _toast('保存失败: ' + e.message, 'error'); }
  });

  // 导入 VPPS 零件
  document.getElementById('btn-confirm-import-vpps')?.addEventListener('click', async () => {
    const levels = [];
    if (document.getElementById('inp-import-l1').checked) levels.push(1);
    if (document.getElementById('inp-import-l2').checked) levels.push(2);
    if (document.getElementById('inp-import-l3').checked) levels.push(3);
    if (!levels.length) { _toast('请至少选择一个层级', 'warn'); return; }
    try {
      const res = await ListShell._cf(`/api/gbop/versions/${_currentVersion}/import-vpps-parts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ levels }),
      });
      closeModal('modal-import-vpps');
      await load();
      _toast(`导入 ${res.data?.created_count || 0} 个节点`, 'success');
    } catch (e) { _toast('导入失败: ' + e.message, 'error'); }
  });

  // 从 TC Excel 导入工序/操作
  document.getElementById('btn-confirm-import-tc-excel')?.addEventListener('click', async () => {
    const fileInput = document.getElementById('inp-tc-excel-file');
    const resultEl  = document.getElementById('tc-excel-result');
    const file = fileInput.files?.[0];
    if (!file) { _toast('请先选择 Excel 文件', 'warn'); return; }
    const btn = document.getElementById('btn-confirm-import-tc-excel');
    btn.disabled = true;
    btn.textContent = '导入中…';
    resultEl.textContent = '';
    try {
      const fd = new FormData();
      fd.append('file', file);
      const res = await ListShell._cfUpload(
        `/api/gbop/versions/${_currentVersion}/import-tc-excel`,
        fd
      );
      const d = res.data || {};
      resultEl.textContent = `工序 +${d.processes_created ?? 0}  操作 +${d.operations_created ?? 0}  节点 +${d.entries_created ?? 0}  链接 +${d.links_created ?? 0}`;
      closeModal('modal-import-tc-excel');
      await load();
      _toast(`导入完成：工序 ${d.processes_created ?? 0}，操作 ${d.operations_created ?? 0}，节点 ${d.entries_created ?? 0}，链接 ${d.links_created ?? 0}`, 'success');
    } catch (e) {
      resultEl.textContent = '导入失败：' + e.message;
      _toast('导入失败: ' + e.message, 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = '导入';
    }
  });

  // 新建/编辑节点
  document.getElementById('btn-confirm-new-entry')?.addEventListener('click', async () => {
    const modal = document.getElementById('modal-new-entry');
    const editGid = modal.dataset.editGid;
    const parentGid = document.getElementById('inp-entry-parent-gid').value || null;
    const node_type = document.getElementById('inp-entry-type').value;
    const vpps_desc = document.getElementById('inp-entry-name').value.trim();
    const vpps = document.getElementById('inp-entry-vpps').value.trim() || null;
    const vppsDescField = document.getElementById('inp-entry-vpps-desc').value.trim();
    const seq_no = parseFloat(document.getElementById('inp-entry-seq').value) || 0;

    if (!vpps_desc) { _toast('请输入名称', 'warn'); return; }

    try {
      if (editGid) {
        await ListShell._cf(`/api/gbop/entries/${editGid}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ node_type, vpps_desc, vpps, seq_no }),
        });
      } else {
        await ListShell._cf('/api/gbop/entries', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ version_gid: _currentVersion, parent_gid: parentGid, node_type, vpps_desc, vpps, seq_no }),
        });
      }
      closeModal('modal-new-entry');
      delete modal.dataset.editGid;
      document.querySelector('#modal-new-entry .modal-title').textContent = '新建节点';
      await load();
      _toast(editGid ? '已更新' : '已创建', 'success');
    } catch (e) { _toast('操作失败: ' + e.message, 'error'); }
  });

  // Fork
  document.getElementById('btn-confirm-fork')?.addEventListener('click', async () => {
    const modal = document.getElementById('modal-fork');
    const sourceGid = modal.dataset.sourceGid;
    const name = document.getElementById('inp-fork-name').value.trim() || null;
    const familyGid = document.getElementById('inp-fork-family').value || null;
    try {
      await ListShell._cf(`/api/gbop/versions/${sourceGid}/fork`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_name: name, target_version_family_gid: familyGid }),
      });
      closeModal('modal-fork');
      await _refreshSidebar();
      _toast('Fork 成功', 'success');
    } catch (e) { _toast('Fork 失败: ' + e.message, 'error'); }
  });

  // 关闭 modal 通用处理
  document.querySelectorAll('[data-close-modal]').forEach(btn => {
    btn.addEventListener('click', () => {
      const id = btn.dataset.closeModal;
      closeModal(id);
      if (id === 'modal-new-version') {
        document.getElementById('inp-ver-name').disabled = false;
        document.getElementById('inp-ver-family-hint').classList.add('hidden');
        document.getElementById('inp-ver-family-gid').value = '';
      }
      if (id === 'modal-new-entry') {
        delete document.getElementById('modal-new-entry').dataset.editGid;
        document.querySelector('#modal-new-entry .modal-title').textContent = '新建节点';
      }
    });
  });

  // 表格内按钮委托
  document.getElementById('appRoot')?.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-act]');
    if (!btn) return;
    const act = btn.dataset.act;
    const gid = btn.dataset.gid;
    const rows = _shell?.getGridRows?.() || [];
    const row = rows.find(r => r.gid === gid);
    if (!row) return;
    if (act === 'edit')  _openEditEntryModal(row);
    if (act === 'child') _openNewEntryModal(gid);
    if (act === 'del')   _deleteEntry(gid);
  });
}

// ── 初始化 ────────────────────────────────────────────────────────
(async function init() {
  _initShell();
  await _loadVersions();
  await _shell.init();
  _bindEvents();

  // 注册自定义侧边栏渲染（与 BOP 一致：先加载版本数据，再 init shell，最后安装 customRender）
  if (_shell?.sidebar) {
    _shell.sidebar._customRender = _renderGbopSidebar;
    _shell.sidebar._renderItems();
  }
})();
