/**
 * 工艺元素库前端脚本 — ListShell 版
 */
'use strict';

// ── 列定义（覆盖所有子类型的字段） ───────────────────────────────────────────
const ELEM_COLS = [
  { key: 'name',              label: '名称',         type: 'text',   width: 200 },
  { key: 'part_no',           label: '零件号',       type: 'text',   width: 150 },
  { key: 'standard_name',     label: '标准名称',     type: 'text',   width: 200 },
  { key: 'category',          label: '分类',         type: 'text',   width: 120 },
  { key: 'part_category',     label: '零件类别',     type: 'text',   width: 120 },
  { key: 'flex_type',         label: '柔性件判定',   type: 'enum',   width: 100,
    options: [
      { value: '刚性件', label: '刚性件' },
      { value: '半柔性', label: '半柔性' },
      { value: '柔性',   label: '柔性'   },
      { value: '待定',   label: '待定'   },
    ]},
  { key: 'ref_main_vpps',         label: '参考主件vpps',       type: 'text',   width: 180 },
  { key: 'ref_main_vpps_desc',    label: '参考主件vpps描述',   type: 'text',   width: 220 },
  { key: 'ref_install_direction', label: '参考安装方向',       type: 'text',   width: 150 },
  { key: 'ref_static_clearance',  label: '参考静态安全间隙',   type: 'text',   width: 150 },
  { key: 'ref_install_clearance', label: '参考安装过程间隙',   type: 'text',   width: 150 },
  { key: 'status',            label: '状态',         type: 'enum',   width: 80,
    options: [{ value: 'active', label: '有效' }, { value: 'obsolete', label: '已废弃' }] },
  { key: '_sap_pin',          label: '',             type: 'text',   width: 28,  alwaysVisible: true, editable: false },
  { key: '_actions',          label: '操作',         type: 'text',   width: 80,  alwaysVisible: true, editable: false },
];

// ── 子标签配置 ────────────────────────────────────────────────────────────────
const TAB_CONFIG = {
  tool:      { label: '工具模板',   apiPath: '/api/craft_lib/tools',     obsoletePath: '/api/craft_lib/tools',     fields: [{ id:'name', label:'名称' }, { id:'category', label:'分类' }] },
  equipment: { label: '设备模板',   apiPath: '/api/craft_lib/equipments', obsoletePath: '/api/craft_lib/equipments',fields: [{ id:'name', label:'名称' }, { id:'category', label:'分类' }] },
  fixture:   { label: '工装模板',   apiPath: '/api/craft_lib/fixtures',   obsoletePath: '/api/craft_lib/fixtures',  fields: [{ id:'name', label:'名称' }] },
  fastener:  { label: '标准紧固件', apiPath: '/api/craft_lib/fasteners',  obsoletePath: null,                       fields: [{ id:'part_no', label:'零件号' }, { id:'name', label:'名称' }] },
  partname:  { label: '标准零件名', apiPath: '/api/craft_lib/part_names', obsoletePath: null,
                fields: [
                  { id:'standard_name',          label:'标准名称'         },
                  { id:'part_category',           label:'零件类别'         },
                  { id:'flex_type',               label:'柔性件判定'       },
                  { id:'ref_main_vpps',           label:'参考主件vpps'     },
                  { id:'ref_main_vpps_desc',      label:'参考主件vpps描述' },
                  { id:'ref_install_direction',   label:'参考安装方向'     },
                  { id:'ref_static_clearance',    label:'参考静态安全间隙' },
                  { id:'ref_install_clearance',   label:'参考安装过程间隙' },
                ] },
};

// ── 状态 ──────────────────────────────────────────────────────────────────────
let _currentTab  = 'tool';
let _items       = [];
let _currentList = null;
let _allLists    = [];
let _shell       = null;

// ── 废弃操作（inline onclick 需要全局暴露）────────────────────────────────────
async function obsoleteItem(gid) {
  if (!confirm('确认废弃？')) return;
  const cfg = TAB_CONFIG[_currentTab];
  if (!cfg.obsoletePath) { alert('该类型不支持废弃操作'); return; }
  try {
    await ListShell._cfSafe(`${cfg.obsoletePath}/${gid}/obsolete`, { method: 'POST' });
    await loadItems();
  } catch (e) { alert('废弃失败: ' + e.message); }
}

// ── 单元格渲染 ────────────────────────────────────────────────────────────────
const CELL_RENDERERS = {
  _sap_pin: (val, row) => {
    if (!row.gid) return '';
    const g = row.gid;
    const n = (row.name || row.vpps_description || '').replace(/'/g, "\\'");
    return `<span class="sap-row-pin" data-gid="${g}" title="自我标注" onclick="event.stopPropagation();window.SelfAnnotationPanel?.open('${g}','${n}',event.currentTarget)"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="17" x2="12" y2="22"/><path d="M5 17h14v-1.76a2 2 0 00-1.11-1.79l-1.78-.9A2 2 0 0115 10.76V6h1a2 2 0 000-4H8a2 2 0 000 4h1v4.76a2 2 0 01-1.11 1.79l-1.78.9A2 2 0 005 15.24z"/></svg></span>`;
  },
  status: (val) => {
    const MAP = { active: '有效', obsolete: '已废弃' };
    const label = MAP[val] || val || '';
    return val ? `<span class="badge badge-${val}">${ListShell._esc(label)}</span>` : '';
  },
  _actions: (val, row) => {
    if (!row.gid) return '';
    const cfg = TAB_CONFIG[_currentTab];
    if (cfg.obsoletePath && row.status !== 'obsolete') {
      return `<button class="btn-danger-sm" onclick="obsoleteItem('${row.gid}')">废弃</button>`;
    }
    return '';
  },
};

// ── 自我标注批量指示器 ────────────────────────────────────────────────────────
async function _loadSapIndicators(gids) {
  if (!gids.length) return;
  for (let i = 0; i < gids.length; i += 500) {
    const chunk = gids.slice(i, i + 500);
    const res = await ListShell._cfSafe(`/api/self_ann/batch?gids=${chunk.join(',')}`);
    if (!res) return;
    Object.entries(res).forEach(([gid, info]) => {
      document.querySelectorAll(`.sap-row-pin[data-gid="${gid}"]`).forEach(el => {
        if (info.status) el.dataset.status = info.status;
        else delete el.dataset.status;
      });
    });
  }
}

// ── 加载数据 ──────────────────────────────────────────────────────────────────
async function loadItems() {
  const cfg = TAB_CONFIG[_currentTab];
  try {
    const url = _currentList ? `${cfg.apiPath}?list_gid=${_currentList}` : cfg.apiPath;
    const res = await ListShell._cfSafe(url);
    _items = res?.data || [];
  } catch (e) { _items = []; }
  _shell?.setRows(_items);
  setTimeout(() => _loadSapIndicators(_items.map(r => r.gid).filter(Boolean)), 0);
}

// ── 视图行（视图过滤/排序后的数据，供 IE/Diff 使用）────────────────────────
const _getViewRows = () => (_shell && _shell.vm ? _shell.vm.applyView(_items) : _items).filter(r => !r._isGroupHeader);

// ── 初始化 ────────────────────────────────────────────────────────────────────
async function init() {
  _shell = new ListShell({
    mountEl:      document.getElementById('appRoot'),
    itemType:     'craft_element',
    moduleId:     'craft_element_lib',
    columns:      ELEM_COLS,
    onListsChange: (lists) => { _allLists = lists; },
    onSelect:      (gid)   => { _currentList = gid; loadItems(); },
    title:        '工艺元素模板',
    titleIcon:    '#icon-tool',
    newLabel:     '新建条目',
    cellRenderer: CELL_RENDERERS,
    importExport: ListShell.makeImportExport('craft_element_lib', _getViewRows, async (rows, _fm, _c, signal) => {
        const cfg = TAB_CONFIG[_currentTab];
        for (const r of rows) {
          if (signal?.aborted) break;
          const firstVal = r[cfg.fields[0]?.id];
          if (!firstVal) continue;
          const body = {};
          cfg.fields.forEach(f => { if (r[f.id]) body[f.id] = r[f.id]; });
          await ListShell._cfSafe(cfg.apiPath, { method: 'POST', body: JSON.stringify(body), signal }).catch(e => console.error('[import craft_element]', e));
        }
        if (!signal?.aborted) await loadItems();
      }),
    diffManager: ListShell.makeDiffManager('craft_element_lib', _getViewRows, 'name'),
    rdpSaveOpts: {
      cloudPath: (row) => TAB_CONFIG[_currentTab].apiPath,
    },
    onRowsChange: async (newRows) => {
      const cfg = TAB_CONFIG[_currentTab];
      let didSave = false;
      for (const row of newRows) {
        if (!row.gid) {
          // 新行：用主字段判断是否有值
          const firstVal = row[cfg.fields[0]?.id];
          if (!firstVal) continue;
          const body = {};
          cfg.fields.forEach(f => { if (row[f.id]) body[f.id] = row[f.id]; });
          await ListShell._cfSafe(cfg.apiPath, { method: 'POST', body: JSON.stringify(body) });
          didSave = true;
        } else {
          // 已有记录：PATCH 变化字段
          const orig = _items.find(i => i.gid === row.gid);
          if (!orig) continue;
          const body = {};
          cfg.fields.forEach(f => {
            if (String(row[f.id] ?? '') !== String(orig[f.id] ?? '')) body[f.id] = row[f.id];
          });
          if (!Object.keys(body).length) continue;
          await ListShell._cfSafe(`${cfg.apiPath}/${row.gid}`, { method: 'PATCH', body: JSON.stringify(body) });
          didSave = true;
        }
      }
      if (didSave) await loadItems();
    },
  });
  await _shell.init();

  // 子标签页切换
  document.querySelectorAll('.sub-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.sub-tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      _currentTab = btn.dataset.tab;
      _shell.rdp?.close?.();

      if (_currentTab === 'annotated') {
        // 显示「已标注」覆层，不走 loadItems
        const sidebar = document.getElementById('elem-type-sidebar');
        window.SapAnnotList?.show({
          module:     'craft_element_lib',
          title:      '工艺元素库 · 已标注',
          offsetLeft: (sidebar?.offsetWidth ?? 120),
          offsetTop:  0,
        });
        return;
      }
      // 切换普通标签时隐藏覆层
      window.SapAnnotList?.hide();
      loadItems();
    });
  });

  await loadItems();

  // 自我标注：保存后更新行指示器
  window.addEventListener('sap-saved', e => {
    document.querySelectorAll(`.sap-row-pin[data-gid="${e.detail.itemGid}"]`).forEach(el => {
      if (e.detail.status) el.dataset.status = e.detail.status;
      else delete el.dataset.status;
    });
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
