/**
 * 工厂资源前端脚本 — ListShell 版
 */
'use strict';

// ── 列定义 ────────────────────────────────────────────────────────────────────
const FR_COLS = [
  { key: 'asset_no',     label: '资产编号', type: 'text', width: 160 },
  { key: 'status',       label: '状态',     type: 'enum', width: 90,  options: [{value:'in_use',label:'在用'},{value:'maintenance',label:'维护中'},{value:'scrapped',label:'已报废'}] },
  { key: 'template_gid', label: '模板GID',  type: 'text', width: 220, editable: false, visible: false },
  { key: '_actions',     label: '操作',     type: 'text', width: 140, alwaysVisible: true, editable: false },
];

// ── 子标签配置 ────────────────────────────────────────────────────────────────
const TAB_CONFIG = {
  tool:      { assetType: 'tool' },
  equipment: { assetType: 'equipment' },
  fixture:   { assetType: 'fixture' },
};

// ── 状态 ──────────────────────────────────────────────────────────────────────
let _currentTab  = 'tool';
let _assets      = [];
let _currentList = null;
let _allLists    = [];
let _shell       = null;

function _cf(method, path, opts = {}) {
  return ListShell._cf(path, { ...opts, method });
}

async function _factoryInvoke(id, payload = {}) {
  const response = await _cf('POST', `/api/v1/capabilities/${id}:invoke`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ version: 1, payload }),
  });
  const envelope = response?.data;
  if (response?.success !== true || envelope?.ok !== true) {
    const detail = envelope?.error || response?.error || {};
    throw new Error(detail.message || `能力调用失败：${id}@1`);
  }
  const value = envelope.data;
  return value?.data !== undefined && Object.keys(value).length === 1 ? value.data : value;
}

function _assetRow(gid) {
  const row = _assets.find(item => item.gid === gid);
  if (!row) throw new Error('资产不存在或已刷新');
  return row;
}

function _normalizeAsset(row) {
  return { ...row, template_gid: row.template_gid ?? row.catalog_gid ?? null };
}

function _assetUpdates(row, orig) {
  const updates = {};
  if (String(row.asset_no ?? '') !== String(orig.asset_no ?? '')) updates.asset_no = row.asset_no;
  if (String(row.template_gid ?? '') !== String(orig.template_gid ?? '')) updates.catalog_gid = row.template_gid || null;
  return updates;
}


// ── 操作函数（inline onclick 需要全局暴露）────────────────────────────────────
async function sendMaintenance(gid) {
  try { const row = _assetRow(gid); await _factoryInvoke('factory.asset.maintenance.start', { gid, expected_version: row.version || 1 }); await loadAssets(); }
  catch (e) { alert('送修失败: ' + e.message); }
}

async function returnAsset(gid) {
  try { const row = _assetRow(gid); await _factoryInvoke('factory.asset.maintenance.complete', { gid, expected_version: row.version || 1 }); await loadAssets(); }
  catch (e) { alert('归还失败: ' + e.message); }
}

async function scrapAsset(gid) {
  if (!confirm('确认报废该资产？')) return;
  try { const row = _assetRow(gid); await _factoryInvoke('factory.asset.scrap', { gid, expected_version: row.version || 1 }); await loadAssets(); }
  catch (e) { alert('报废失败: ' + e.message); }
}

// ── 单元格渲染 ────────────────────────────────────────────────────────────────
const CELL_RENDERERS = {
  status: (val) => {
    const MAP = { in_use: '在用', maintenance: '维护中', scrapped: '已报废', active: '活跃', idle: '闲置', retired: '已退役' };
    return `<span class="badge badge-${val || 'in_use'}">${ListShell._esc(MAP[val] || val || '-')}</span>`;
  },
  asset_type: (val) => val ? `<span class="badge">${ListShell._esc(val)}</span>` : '-',
  _actions: (val, row) => {
    if (!row.gid) return '';
    const st = row.status || 'in_use';
    return `<div style="display:flex;gap:4px">
      ${st === 'in_use'      ? `<button class="btn-warn"      onclick="sendMaintenance('${row.gid}')">送修</button>` : ''}
      ${st === 'maintenance' ? `<button class="btn-ghost"     onclick="returnAsset('${row.gid}')">归还</button>` : ''}
      ${st !== 'scrapped'    ? `<button class="btn-danger-sm" onclick="scrapAsset('${row.gid}')">报废</button>` : ''}
    </div>`;
  },
};

// ── 加载数据 ──────────────────────────────────────────────────────────────────
async function loadAssets() {
  const cfg = TAB_CONFIG[_currentTab];
  try {
    const res = await _factoryInvoke('factory.asset.search', { asset_type: cfg.assetType, limit: 500 });
    _assets = (Array.isArray(res) ? res : (res?.items || res?.data || [])).map(_normalizeAsset);
  } catch (e) {
    _assets = [];
    console.warn('[factory_resource] 加载失败:', e.message);
  }
  _shell?.setRows(_assets);
}

// ── 视图行（视图过滤/排序后的数据，供 IE/Diff 使用）────────────────────────
const _getViewRows = () => (_shell?.grid?.getRows() || []).filter(r => !r._isGroupHeader);

// ── 初始化 ────────────────────────────────────────────────────────────────────
async function init() {
  _shell = new ListShell({
    mountEl:      document.getElementById('appRoot'),
    itemType:     'factory_resource',
    moduleId:     'factory_resource',
    columns:      FR_COLS,
    onListsChange: (lists) => { _allLists = lists; },
    onSelect:      (gid)   => { _currentList = gid; loadAssets(); },
    title:        '工厂实物资源',
    titleIcon:    '#icon-factory',
    newLabel:     '新建条目',
    importExport: ListShell.makeImportExport('factory_resource', _getViewRows, async (rows, _fm, _c, signal) => {
        const cfg = TAB_CONFIG[_currentTab];
        for (const r of rows) {
          if (signal?.aborted) break;
          if (!r.asset_no) continue;
          await _factoryInvoke('factory.asset.register', {
            asset_no: r.asset_no,
            asset_type: cfg.assetType,
            catalog_gid: r.template_gid || r.catalog_gid || null,
          });
        }
        if (!signal?.aborted) await loadAssets();
      }),
    diffManager: ListShell.makeDiffManager('factory_resource', _getViewRows, 'asset_no'),
    rdpSaveOpts: {
      savePatch: async (row, patch) => {
        const updates = {};
        if (patch.asset_no !== undefined) updates.asset_no = patch.asset_no;
        if (Object.keys(updates).length) {
          const saved = await _factoryInvoke('factory.asset.update', {
            gid: row.gid,
            expected_version: row.version || 1,
            updates,
          });
          if (saved?.version) row.version = saved.version;
        }
      },
    },
    cellRenderer: CELL_RENDERERS,
    onRowsChange: async (newRows) => {
      const cfg = TAB_CONFIG[_currentTab];
      let didSave = false;
      for (const row of newRows) {
        if (row.gid) {
          const orig = _assets.find(a => a.gid === row.gid);
          if (!orig) continue;
          const updates = _assetUpdates(row, orig);
          if (!Object.keys(updates).length) continue;
          await _factoryInvoke('factory.asset.update', { gid: row.gid, expected_version: orig.version || 1, updates });
          didSave = true;
        } else if (row.asset_no) {
          await _factoryInvoke('factory.asset.register', {
            asset_no: row.asset_no,
            asset_type: cfg.assetType,
            catalog_gid: row.template_gid || null,
          });
          didSave = true;
        }
      }
      if (didSave) await loadAssets();
    },
  });
  await _shell.init();

  // 左侧资源类型侧边栏切换
  document.querySelectorAll('.fr-type-item').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.fr-type-item').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      _currentTab = btn.dataset.tab;
      _shell.rdp?.close?.();
      loadAssets();
    });
  });

  // 导入导出和对比由 ListShell 内置工具栏管理（_shell.ieMgr / _shell.diffMgr）

  // 主题同步由 list_shell.js 的 _lsInitTheme() IIFE 统一处理

  await loadAssets();

  window.DataRegistry?.register('factory_resource', {
    label: '工厂资源', icon: 'icon-factory',
    capabilities: ['grid_editor', 'view_manager', 'import_export', 'diff_manager'],
    getRows: () => _assets || [],
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
