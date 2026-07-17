/**
 * 工厂资源前端脚本 — ListShell 版
 */
'use strict';

// ── 列定义 ────────────────────────────────────────────────────────────────────
const FR_COLS = [
  { key: 'asset_no',     label: '资产编号', type: 'text', width: 160 },
  { key: 'status',       label: '状态',     type: 'enum', width: 90,  options: [{value:'active',label:'运行中'},{value:'idle',label:'闲置'},{value:'maintenance',label:'维护中'},{value:'retired',label:'已退役'}] },
  { key: 'template_gid', label: '模板GID',  type: 'text', width: 220, editable: false, visible: false },
  { key: '_actions',     label: '操作',     type: 'text', width: 140, alwaysVisible: true, editable: false },
];

// ── 子标签配置 ────────────────────────────────────────────────────────────────
const TAB_CONFIG = {
  tool:      { apiPath: '/api/factory/tools' },
  equipment: { apiPath: '/api/factory/equipments' },
  fixture:   { apiPath: '/api/factory/fixtures' },
};

// ── 状态 ──────────────────────────────────────────────────────────────────────
let _currentTab  = 'tool';
let _assets      = [];
let _currentList = null;
let _allLists    = [];
let _shell       = null;


// ── 操作函数（inline onclick 需要全局暴露）────────────────────────────────────
async function sendMaintenance(gid) {
  const cfg = TAB_CONFIG[_currentTab];
  try { await ListShell._cfSafe(`${cfg.apiPath}/${gid}/maintenance`, { method: 'POST' }); await loadAssets(); }
  catch (e) { alert('送修失败: ' + e.message); }
}

async function returnAsset(gid) {
  const cfg = TAB_CONFIG[_currentTab];
  try { await ListShell._cfSafe(`${cfg.apiPath}/${gid}/return`, { method: 'POST' }); await loadAssets(); }
  catch (e) { alert('归还失败: ' + e.message); }
}

async function scrapAsset(gid) {
  if (!confirm('确认报废该资产？')) return;
  const cfg = TAB_CONFIG[_currentTab];
  try { await ListShell._cfSafe(`${cfg.apiPath}/${gid}/scrap`, { method: 'POST' }); await loadAssets(); }
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
    const url = _currentList ? `${cfg.apiPath}?list_gid=${_currentList}` : cfg.apiPath;
    const res = await ListShell._cfSafe(url);
    _assets = res?.data || [];
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
          await ListShell._cfSafe(cfg.apiPath, { method: 'POST', body: JSON.stringify(r), signal });
        }
        if (!signal?.aborted) await loadAssets();
      }),
    diffManager: ListShell.makeDiffManager('factory_resource', _getViewRows, 'asset_no'),
    rdpSaveOpts: {
      cloudPath: (row) => TAB_CONFIG[_currentTab].apiPath,
    },
    cellRenderer: CELL_RENDERERS,
    onRowsChange: async (newRows) => {
      const cfg = TAB_CONFIG[_currentTab];
      let didSave = false;
      for (const row of newRows) {
        if (row.gid) {
          const orig = _assets.find(a => a.gid === row.gid);
          if (!orig) continue;
          const body = {};
          ['asset_no', 'template_gid'].forEach(k => {
            if (String(row[k] ?? '') !== String(orig[k] ?? '')) body[k] = row[k];
          });
          if (!Object.keys(body).length) continue;
          await ListShell._cfSafe(`${cfg.apiPath}/${row.gid}`, { method: 'PATCH', body: JSON.stringify(body) });
          didSave = true;
        } else if (row.asset_no) {
          await ListShell._cfSafe(cfg.apiPath, {
            method: 'POST',
            body: JSON.stringify({ asset_no: row.asset_no, template_gid: row.template_gid || null }),
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
