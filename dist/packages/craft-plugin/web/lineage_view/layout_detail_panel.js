'use strict';
/**
 * layout_detail_panel.js  —  布局视图底部详情面板 v2
 *
 * 七列可调宽布局：节点树 | 属性 | 关系 | 详情 | 规则 | 知识
 * 支持从零建树：空树引导 → 新建线体 → 新建工位 → 逐层新建子节点
 */

function _ldpLsk(base) {
  try { const u = window.parent?._authUser || window.top?._authUser || window._authUser; const g = u?.gid || u?.user_gid || ''; return g ? `${g}:${base}` : base; } catch { return base; }
}

// ── 节点类型颜色——与 lineage.css .lv-nt-* 保持完全一致 ─────────────────────────
// 注意：节点树的圆点优先使用 class="lv-nt-dot lv-nt-{type}" 获取颜色，
// 此表仅作为无法用 CSS 类时的内联颜色兜底（如 SVG、canvas 等场景）。
const NODE_TYPE_DOT = {
  factory_bop:         '#6c8ebf',
  line_process:        '#74c7ec',
  station_process:     '#fab387',
  operator_process:    '#cba6f7',
  man:                 '#9b59b6',
  station_factory:     '#5b8dd9',
  process:             '#89b4fa',
  equipment_factory:   '#94e2d5',
  tool_factory:        '#89dceb',
  equipment_need:      '#74c7ec',
  fixture_factory:     '#d3875a',
  operation:           '#a6adc8',
  issue:               '#6c7086',
  standard_task:       '#2980b9',
  non_standard_task:   '#1a6795',
  contral_plan:        '#8e44ad',
  process_chart:       '#7d3a9e',
  floor_height_factory:'#5dade2',
  knowledge:           '#b4befe',
  rule:                '#fab387',
  part:                '#7f8c8d',
  non_standard_part:   '#6a7778',
  standard_part:       '#95a5a6',
  support_material:    '#bdc3c7',
  tool_need:           '#cba6f7',
  fixture_need:        '#d3875a',
  jack_pos:            '#884ea0',
};

// 支持拖拽换序/换父的节点类型（岗位、工序、操作）
const TREE_DRAGGABLE_TYPES = new Set(['operator_process', 'process', 'operation']);
// 各类型合法父节点类型（工序可挂工位或岗位下，操作只能在工序下）
const TREE_VALID_PARENTS = {
  operator_process: new Set(['station_process']),
  process:          new Set(['operator_process', 'station_process']),
  operation:        new Set(['process']),
};

// ── 关系分组配置 ──────────────────────────────────────────────────────────────
const REL_GROUPS = [
  { key: 'child',   name: '子节点',    ntType: 'process',           linkTypes: null },
  { key: 'pbom',    name: 'PBOM 零件', ntType: 'part',              linkTypes: ['pbom_part'] },
  { key: 'equip',   name: '设备',      ntType: 'equipment_factory', linkTypes: ['physical_equipment', 'project_equipment'] },
  { key: 'tool',    name: '工具',      ntType: 'tool_factory',      linkTypes: ['physical_tool', 'project_tools'] },
  { key: 'fixture', name: '工装',      ntType: 'fixture_factory',   linkTypes: ['physical_fixture', 'project_tooling'] },
  { key: 'issue',   name: '问题',      ntType: 'issue',             linkTypes: ['issue'] },
  { key: 'task',    name: '任务',      ntType: 'standard_task',     linkTypes: ['task_std', 'task_custom'] },
];

// ── 子节点类型映射 ─────────────────────────────────────────────────────────────
const CHILD_TYPE_MAP = {
  null:             { type: 'line_process',     label: '线体', dot: NODE_TYPE_DOT.line_process },
  line_process:     { type: 'station_process',  label: '工位', dot: NODE_TYPE_DOT.station_process },
  station_process:  { type: 'operator_process', label: '岗位', dot: NODE_TYPE_DOT.operator_process },
  operator_process: { type: 'process',          label: '工序', dot: NODE_TYPE_DOT.process },
  process:          { type: 'operation',        label: '操作', dot: NODE_TYPE_DOT.operation },
};

const _INLINE_ADD_DEFAULT_TITLE = {
  line_process:     '新线体',
  station_process:  '新工位',
  operator_process: '新岗位',
  process:          '新工序',
  operation:        '新操作',
};

// ── 详情面板字段模板 ──────────────────────────────────────────────────────────
// 每种 link_type 展示哪些字段（label, key, type, options?）
const DETAIL_FIELDS = {
  physical_tool:     [
    { sec: '基本信息' },
    { k: '型号',    f: 'tool_spec',  t: 'text' },
    { k: '工具类型', f: 'tool_type', t: 'select', opts: 'hand_tool,power_tool,pneumatic,torque_wrench,gauge,other' },
    { k: '资产编号', f: 'asset_no',  t: 'text' },
    { k: '状态',    f: 'status',    t: 'select', opts: 'in_use,maintenance,scrapped' },
    { sec: '维护' },
    { k: '校准周期(天)', f: 'calibration_cycle_days', t: 'number' },
  ],
  project_tools:     [
    { sec: '需求信息' },
    { k: '规格',    f: 'spec',     t: 'text' },
    { k: '数量',    f: 'quantity', t: 'number' },
    { k: '状态',    f: 'status',   t: 'select', opts: 'pending,confirmed,in_use,cancelled' },
    { k: '需校准',  f: 'calibration_req', t: 'select', opts: 'true,false' },
  ],
  physical_fixture:  [
    { sec: '基本信息' },
    { k: '工装类型', f: 'fixture_type', t: 'select', opts: 'jig,fixture,gauge,mold,die,other' },
    { k: '规格',    f: 'fixture_spec', t: 'text' },
    { k: '资产编号', f: 'asset_no',    t: 'text' },
    { k: '状态',    f: 'status',      t: 'select', opts: 'in_use,maintenance,scrapped' },
    { k: '设计图号', f: 'design_no',   t: 'text' },
  ],
  project_tooling:   [
    { sec: '需求信息' },
    { k: '规格',      f: 'spec',            t: 'text' },
    { k: '数量',      f: 'quantity',         t: 'number' },
    { k: '状态',      f: 'status',           t: 'select', opts: 'pending,confirmed,in_use,cancelled' },
    { k: '需专项设计', f: 'design_required',  t: 'select', opts: 'true,false' },
  ],
  physical_equipment: [
    { sec: '基本信息' },
    { k: '型号',    f: 'model_no',      t: 'text' },
    { k: '制造商',  f: 'manufacturer',  t: 'text' },
    { k: '资产编号', f: 'asset_no',     t: 'text' },
    { k: '状态',    f: 'status',        t: 'select', opts: 'in_use,maintenance,scrapped' },
    { sec: '技术参数' },
    { k: '功率(kW)', f: 'power_kw',     t: 'number' },
    { k: '保养周期(天)', f: 'maintenance_cycle_days', t: 'number' },
  ],
  project_equipment: [
    { sec: '需求信息' },
    { k: '规格',    f: 'spec',           t: 'text' },
    { k: '数量',    f: 'quantity',        t: 'number' },
    { k: '状态',    f: 'status',          t: 'select', opts: 'pending,confirmed,in_use,cancelled' },
    { k: '首选型号', f: 'preferred_model', t: 'text' },
    { k: '预算(元)', f: 'budget_cny',     t: 'number' },
  ],
  issue: [
    { sec: '问题信息' },
    { k: '状态',    f: 'status',   t: 'select', opts: 'open,in_progress,resolved,closed' },
    { k: '严重程度', f: 'severity', t: 'select', opts: 'low,medium,high,critical' },
    { k: '报告人',  f: 'owner_name', t: 'text' },
    { sec: '描述' },
    { k: '描述',    f: 'description', t: 'textarea' },
  ],
  task_std: [
    { sec: '任务信息' },
    { k: '状态',    f: 'status',   t: 'select', opts: 'todo,in_progress,done,cancelled' },
    { k: '优先级',  f: 'priority', t: 'select', opts: 'low,medium,high,urgent' },
    { k: '负责人',  f: 'owner_name', t: 'text' },
    { k: '截止日期', f: 'due_date',  t: 'date' },
    { sec: '描述' },
    { k: '描述',    f: 'description', t: 'textarea' },
  ],
  task_custom: [
    { sec: '任务信息' },
    { k: '状态',    f: 'status',   t: 'select', opts: 'todo,in_progress,done,cancelled' },
    { k: '优先级',  f: 'priority', t: 'select', opts: 'low,medium,high,urgent' },
    { k: '负责人',  f: 'owner_name', t: 'text' },
    { k: '截止日期', f: 'due_date',  t: 'date' },
    { sec: '描述' },
    { k: '描述',    f: 'description', t: 'textarea' },
  ],
  usesPart: [
    { sec: '零件信息' },
    { k: '零件号',  f: 'part_no',   t: 'text' },
    { k: '零件名',  f: 'title',     t: 'text' },
    { k: '用量',    f: 'quantity',  t: 'number' },
    { k: 'VPPS',   f: 'vpps',      t: 'text' },
    { k: '组件ID',  f: 'component_id', t: 'text' },
    { sec: '属性' },
    { k: '零组件类型', f: 'component_type', t: 'text' },
    { k: '单位',    f: 'unit',      t: 'text' },
    { k: '材料',    f: 'material',  t: 'text' },
  ],
  pbom_part: [
    { sec: '零件信息' },
    { k: '零件号',  f: 'part_no',   t: 'text' },
    { k: '零件名',  f: 'title',     t: 'text' },
    { k: '用量',    f: 'quantity',  t: 'number' },
    { k: 'VPPS',   f: 'vpps',      t: 'text' },
  ],
};

// ── 工具函数 ──────────────────────────────────────────────────────────────────
function _he(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function _statusBadgeClass(status) {
  const m = { 'open': 'b-r', 'in_progress': 'b-b', 'resolved': 'b-g', 'done': 'b-g',
    'todo': 'b-0', 'cancelled': 'b-0', 'pending': 'b-y', 'confirmed': 'b-b',
    'in_use': 'b-g', 'maintenance': 'b-y', 'scrapped': 'b-r',
    '进行中': 'b-b', '待开始': 'b-0', '逾期': 'b-y', '已完成': 'b-g',
  };
  return m[status] || 'b-0';
}

// ── 主类 ──────────────────────────────────────────────────────────────────────
class LayoutDetailPanel {
  /**
   * @param {Object} opts
   * @param {HTMLElement} opts.containerEl    - #llDetailPanel
   * @param {Function}    opts.cf             - _cloudFetch(path, opts?)
   * @param {Function}    opts.toast          - (msg, type) => void
   * @param {Function}    opts.patchEntry     - (gid, body) => Promise
   * @param {Function}    opts.reloadData     - async () => void
   * @param {Function}    opts.getLineageData - () => { rowByGid, childMap, statsMap, versionGid }
   * @param {Function}    opts.onNodeActivate - (gid) => void  节点树点击时通知主视图高亮定位
   */
  constructor({ containerEl, cf, toast, patchEntry, reloadData, preserveLayoutView, getLineageData, onNodeActivate, getVersionInfo, onVersionChange }) {
    this._el = containerEl;
    this._cf = cf;
    this._toast = toast;
    this._patchEntry = patchEntry;
    this._reloadData = reloadData;
    this._preserveLayoutView = preserveLayoutView || (() => {});
    this._getLineageData = getLineageData || (() => null);
    this._onNodeActivate  = onNodeActivate  || null;
    this._getVersionInfo  = getVersionInfo  || null;
    this._onVersionChange = onVersionChange || null;

    this._isOpen = false;
    this._userClosed = false;
    this._currentGid = null;
    this._currentRow = null;
    this._treeRootGid = null;   // 节点树显示的根
    this._treeDragPending = null; // mousedown 后待确认的拖拽 { gid, nodeType, parentGid, el, startX, startY }
    this._treeDragState   = null; // 拖拽激活后 { ...pending, ghost, currentTarget, currentAction }
    this._currentRelGroups = []; // 本体驱动关系分组，_renderRels 填充
    this._treeExpanded = new Set();
    this._lastVersionGid = null; // 上次渲染时的版本 gid，用于检测版本切换
    this._relLinks = [];        // 当前节点的所有关系链接
    this._selectedRel = null;   // 当前选中的关系项 { link, source_entry_gid, source_entry_title }
    this._detMode = 'empty';       // 'empty' | 'view' | 'add'
    this._addType = null;          // 添加模式的类型 key
    this._inlineAddPending = null; // { parentGid, childType } 内联添加待定状态
    this._renderTreeRaf = null;    // RAF handle for updateData 合批

    // DOM refs
    this._resizeHandle  = this._el.querySelector('#llDpResizeHandle');
    this._handleBar     = this._el.querySelector('#llDpHandleBar');
    this._toolbarToggle = document.getElementById('lvDetailPanelToggle');
    this._colTree      = this._el.querySelector('#llDpTree');
    this._treeBody     = this._el.querySelector('#llDpTreeBody');
    this._verSlot      = this._el.querySelector('#llDpVerSlot');
    this._lineSlot     = this._el.querySelector('#llDpLineSlot');
    this._searchInp    = this._el.querySelector('#llDpSearchInp');
    this._searchQuery  = '';    // 当前搜索词
    this._extraVersionData = new Map();  // gid → { rows, rowByGid, childMap }
    this._colProps     = this._el.querySelector('#llDpProps');
    this._propsBody    = this._el.querySelector('#llDpPropsBody');
    this._colRels      = this._el.querySelector('#llDpRels');
    this._relsBody     = this._el.querySelector('#llDpRelsBody');
    this._detDrawer      = document.getElementById('llDetDrawer');
    this._detDrawerBody  = document.getElementById('llDetDrawerBody');
    this._detDrawerTitle = document.getElementById('llDetDrawerTitle');
    this._detPinned      = false;
    this._colRules     = this._el.querySelector('#llDpRules');
    this._rulesBody    = this._el.querySelector('#llDpRulesBody');
    this._colKnow      = this._el.querySelector('#llDpKnow');
    this._knowBody     = this._el.querySelector('#llDpKnowBody');
    this._knowAddBtn   = this._el.querySelector('#llDpKnowAdd');

    // 面板 toggle
    const panelToggle = this._el.querySelector('#llDpPanelToggle');
    if (panelToggle) panelToggle.addEventListener('click', () => this.toggle());
    if (this._toolbarToggle) this._toolbarToggle.addEventListener('click', () => this.toggle());
    // 抽屉按钮
    document.getElementById('llDetDrawerClose')?.addEventListener('click', () => this._closeDetDrawer());
    document.getElementById('llDetDrawerCancel')?.addEventListener('click', () => this._closeDetDrawer());
    document.getElementById('llDetDrawerPin')?.addEventListener('click', () => {
      this._detPinned = !this._detPinned;
      document.getElementById('llDetDrawerPin').classList.toggle('active', this._detPinned);
    });
    // 垂直分割条拖拽
    const vDiv = this._el.querySelector('#llDpVDivider');
    if (vDiv) {
      let dragging = false, startY = 0, startH = 0;
      vDiv.addEventListener('mousedown', e => {
        dragging = true; startY = e.clientY;
        const treeCol = this._el.querySelector('#llDpTree');
        startH = treeCol ? treeCol.offsetHeight : 300;
        vDiv.classList.add('active');
        e.preventDefault();
      });
      document.addEventListener('mousemove', e => {
        if (!dragging) return;
        const newH = Math.max(120, startH + (e.clientY - startY));
        document.documentElement.style.setProperty('--ll-tree-h', newH + 'px');
      });
      document.addEventListener('mouseup', () => {
        if (dragging) {
          dragging = false; vDiv.classList.remove('active');
          try { localStorage.setItem('ll:treeH', document.documentElement.style.getPropertyValue('--ll-tree-h')); } catch {}
        }
      });
    }
    // 恢复上次的树高度
    const savedH = localStorage.getItem('ll:treeH');
    if (savedH) document.documentElement.style.setProperty('--ll-tree-h', savedH);

    // ESC 关闭抽屉
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') this._closeDetDrawer();
    });

    // 树内搜索框
    if (this._searchInp) {
      this._searchInp.addEventListener('input', () => {
        this._searchQuery = this._searchInp.value.trim();
        this._renderTree(this._currentGid);
      });
      this._searchInp.addEventListener('keydown', e => {
        if (e.key === 'Escape') { this._searchInp.value = ''; this._searchQuery = ''; this._renderTree(this._currentGid); }
      });
    }
    this._bindResizeHandle();
    this._bindHandleBar();
    this._setupTreeDragOnce();
  }

  // ── 公开 API ──────────────────────────────────────────────────────────────

  open(gid) {
    const data = this._getLineageData();
    if (!data) return;
    const row = data.rowByGid.get(gid);
    if (!row) return;
    // 用户主动折叠面板后，不自动弹开（同右侧边栏逻辑）
    if (!this._isOpen && this._userClosed) {
      this._currentGid = gid;
      this._currentRow = row;
      return;
    }
    this._currentGid = gid;
    this._currentRow = row;

    // 记录当前版本，避免 updateData 误判为版本切换（_lastVersionGid 初始为 null）
    const verInfo = this._getVersionInfo ? this._getVersionInfo() : null;
    if (verInfo?.currentGid) this._lastVersionGid = verInfo.currentGid;

    // 根节点始终是线体
    const lineGid = this._findAncestorOfType(gid, 'line_process', data.rowByGid);
    this._treeRootGid = lineGid || gid;

    // 展开从根到目标节点的全部祖先
    let cur = data.rowByGid.get(gid);
    while (cur) {
      this._treeExpanded.add(cur.gid);
      cur = cur.parent_gid ? data.rowByGid.get(cur.parent_gid) : null;
    }

    this._show();
    // inline add 进行中时，open() 只更新右侧属性，不重渲染树（避免销毁输入框）
    if (this._inlineAddPending) {
      this._renderProps(gid, row);
      return;
    }
    this._renderAll(gid, row);
  }

  /** 判断一行是否匹配搜索词（检查 title/vpps/bom_row_id 和 entity_data 里的关键字段） */
  _matchesSearch(row, q) {
    if (!q) return false;
    const check = s => s && String(s).toLowerCase().includes(q);
    if (check(row.title))      return true;
    if (check(row.vpps))       return true;
    if (check(row.vpps_desc))  return true;
    if (check(row.bom_row_id)) return true;
    const ed = row.entity_data;
    if (ed) {
      for (const f of ['part_no', 'name', 'title', 'vpps', 'process_code', 'code', 'operator_code']) {
        if (check(ed[f])) return true;
      }
    }
    return false;
  }

  /** 搜索结果树：匹配节点 + 所有祖先，以树形展示，匹配节点高亮 */
  _buildSearchResultHtml(q, data, visTypes, activeGid) {
    const rowByGid = data.rowByGid;
    const childMap = data.childMap;

    const matched = new Set();
    for (const [gid, row] of rowByGid) {
      if (!row.is_deleted && this._matchesSearch(row, q)) matched.add(gid);
    }
    if (!matched.size) {
      return `<div style="padding:12px 8px;font-size:11px;color:var(--subtext0,#a6adc8);text-align:center">未找到「${_he(q)}」</div>`;
    }

    // 收集匹配节点 + 所有祖先
    const toShow = new Set();
    for (const gid of matched) {
      let cur = rowByGid.get(gid);
      while (cur) { toShow.add(cur.gid); cur = cur.parent_gid ? rowByGid.get(cur.parent_gid) : null; }
    }

    // 递归渲染
    const renderNode = (gid, depth) => {
      const row = rowByGid.get(gid);
      if (!row || row.is_deleted || !toShow.has(gid)) return '';
      const indent = depth * 14;
      const isMatch  = matched.has(gid);
      const isActive = gid === activeGid;

      // 标题高亮
      let labelHtml = _he(row.title || row.gid);
      if (isMatch && row.title) {
        const lo = row.title.toLowerCase();
        const idx = lo.indexOf(q);
        if (idx >= 0) {
          labelHtml = _he(row.title.slice(0, idx))
            + `<mark style="background:var(--yellow,#f9e2af);color:var(--base,#1e1e2e);border-radius:2px;padding:0 1px">${_he(row.title.slice(idx, idx + q.length))}</mark>`
            + _he(row.title.slice(idx + q.length));
        }
      }

      // 匹配行额外字段（vpps / 零件号等）
      let extraHtml = '';
      if (isMatch) {
        const extras = [];
        if (row.vpps) extras.push(_he(row.vpps));
        if (row.bom_row_id) extras.push(_he(row.bom_row_id));
        const ed = row.entity_data;
        if (ed?.part_no) extras.push(_he(ed.part_no));
        if (ed?.name && ed.name !== row.title) extras.push(_he(ed.name));
        if (ed?.process_code && ed.process_code !== row.vpps) extras.push(_he(ed.process_code));
        if (extras.length) extraHtml = ` <span style="font-size:9px;color:var(--subtext0,#a6adc8)">${extras.join(' · ')}</span>`;
      }

      const kids = (childMap.get(gid) || []).filter(r => !r.is_deleted && toShow.has(r.gid));
      let html = `
        <div class="ll-tn${isActive ? ' ll-tn-active' : ''}${isMatch ? ' ll-tn-search-hit' : ''}"
             data-gid="${_he(gid)}"
             style="padding-left:${indent + 4}px${isMatch ? ';background:rgba(203,166,247,0.1)' : ''}">
          <span class="ll-tn-tog-btn" data-gid="${_he(gid)}"
                style="font-size:9px;color:var(--overlay1);width:11px;text-align:center;flex-shrink:0;cursor:pointer">
            ${kids.length ? '▼' : '·'}
          </span>
          <span class="lv-nt-dot lv-nt-${_he(row.node_type)}"></span>
          <span class="ll-tn-lbl">${labelHtml}${extraHtml}</span>
        </div>`;
      for (const kid of kids) html += renderNode(kid.gid, depth + 1);
      return html;
    };

    // 找根节点（parent 不在 toShow 里）
    const roots = [...toShow]
      .filter(gid => { const r = rowByGid.get(gid); return !r?.parent_gid || !toShow.has(r.parent_gid); })
      .map(gid => rowByGid.get(gid)).filter(Boolean)
      .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));

    let html = `<div style="padding:4px 6px 2px;font-size:9px;color:var(--subtext0,#a6adc8)">找到 ${matched.size} 个匹配项</div>`;
    for (const root of roots) html += renderNode(root.gid, 0);
    return html;
  }

  /** 向上找第一个指定 node_type 的祖先（包含自身），返回其 gid 或 null */
  _findAncestorOfType(gid, nodeType, rowByGid) {
    let cur = rowByGid.get(gid);
    while (cur) {
      if (cur.node_type === nodeType) return cur.gid;
      cur = cur.parent_gid ? rowByGid.get(cur.parent_gid) : null;
    }
    return null;
  }

  /** 向上找 station_process 祖先 gid（用于树高亮） */
  _findStationAncestor(gid, rowByGid) {
    return this._findAncestorOfType(gid, 'station_process', rowByGid);
  }

  _renderTree(activeGid) {
    const data = this._getLineageData();
    if (!data) { this._renderEmptyTree(); return; }

    const allRows = Array.from(data.rowByGid.values()).filter(r => !r.is_deleted);
    if (!allRows.length) { this._renderEmptyTree(); return; }

    const allLines = allRows.filter(r => r.node_type === 'line_process');

    if (!this._treeRootGid || data.rowByGid.get(this._treeRootGid)?.node_type !== 'line_process') {
      this._treeRootGid = allLines[0]?.gid || allRows[0]?.gid;
    }
    const rootRow = data.rowByGid.get(this._treeRootGid);
    if (!rootRow) return;

    const activeStationGid = activeGid ? this._findStationAncestor(activeGid, data.rowByGid) : null;

    // ── 版本槽位（持久化 picker，与主工具栏同步）──────────────────
    const verInfo = this._getVersionInfo ? this._getVersionInfo() : null;
    const verName = verInfo?.currentName || 'BOP版本';
    const versions = verInfo?.versions || [];

    if (this._verSlot) {
      // 只更新槽位按钮文字，picker 复用或首次创建
      const existingBar = this._verSlot.querySelector('#llTreeVerBar');
      if (!existingBar) {
        this._verSlot.innerHTML = `
          <div class="ll-tree-ver-bar" id="llTreeVerBar">
            <span class="ll-tree-ver-icon">☰</span>
            <span class="ll-tree-ver-name" id="llTreeVerName">${_he(verName)}</span>
            ${versions.length > 0 ? '<span class="ll-tree-root-arr">▾</span>' : ''}
          </div>`;
        this._buildVerPicker(versions, verInfo);
      } else {
        // 只更新名称，不重建 picker
        const nameEl = existingBar.querySelector('#llTreeVerName');
        if (nameEl) nameEl.textContent = verName;
        // 更新 picker 内的选中状态
        this._refreshVerPickerSelection(verInfo?.currentGid);
      }
    }


    // ── 工位子树（读主界面筛选状态，写入可滚动的 _treeBody）──────────
    const mainTypeFilter   = data.typeFilter;
    const mainLevel1Filter = data.level1Filter;

    const visTypes = mainTypeFilter && mainTypeFilter.length
      ? new Set(mainTypeFilter)
      : new Set(['line_process', 'station_process', 'operator_process', 'process', 'operation']);

    const visibleLines = allLines.filter(l =>
      !mainLevel1Filter || mainLevel1Filter.size === 0 || mainLevel1Filter.has(l.gid)
    );
    const needVirtualRoot = visibleLines.length > 1;

    // ── 线体槽位（单线体时显示名称，多线体时隐藏）──────────────────────
    if (this._lineSlot) {
      if (visibleLines.length === 1 && !needVirtualRoot) {
        this._lineSlot.style.display = '';
        const _editable = this._isEditable();
        this._lineSlot.innerHTML = `
          <div class="ll-tree-root-bar" id="llTreeLineBar">
            <span class="ll-tn-tog-btn" data-gid="${_he(rootRow.gid)}" style="font-size:9px;color:var(--overlay1);width:11px;text-align:center;flex-shrink:0;cursor:pointer">
              ${this._treeExpanded.has(rootRow.gid) ? '▼' : '▶'}
            </span>
            <span class="lv-nt-dot lv-nt-line_process"></span>
            <span class="ll-tree-root-name">${_he(rootRow.title || rootRow.gid)}</span>
            ${_editable ? `<span class="ll-tn-add-btn" data-parent-gid="${_he(rootRow.gid)}" data-child-type="station_process" title="添加工位">+</span>` : ''}
          </div>`;
      } else {
        this._lineSlot.style.display = 'none';
        this._lineSlot.innerHTML = '';
      }
    }

    let html = '';

    if (needVirtualRoot) {
      // 多线体：lineSlot 隐藏，treeBody 渲染所有可见线体
      if (this._lineSlot) this._lineSlot.style.display = 'none';
      for (const line of visibleLines) {
        if (!visTypes.has('line_process') && !visTypes.has('station_process')) continue;
        const lineExpanded = this._treeExpanded.has(line.gid);
        html += `<div class="ll-tn ll-tn-line" data-gid="${_he(line.gid)}" style="padding-left:4px">
          <span class="ll-tn-tog-btn" data-gid="${_he(line.gid)}" style="font-size:9px;color:var(--overlay1);width:11px;text-align:center;flex-shrink:0;cursor:pointer">${lineExpanded?'▼':'▶'}</span>
          <span class="lv-nt-dot lv-nt-line_process"></span>
          <span class="ll-tn-lbl">${_he(line.title||line.gid)}</span>
          ${this._isEditable() ? `<span class="ll-tn-add-btn" data-parent-gid="${_he(line.gid)}" data-child-type="station_process" title="添加工位">+</span>` : ''}
        </div>`;
        if (lineExpanded) {
          html += this._renderStationsForLine(line.gid, data.childMap, data.rowByGid, activeGid, activeStationGid, visTypes, 16);
        }
      }
    } else {
      // 单线体：lineSlot 正常显示，treeBody 只放工位子树
      if (this._lineSlot) this._lineSlot.style.display = '';
      if (visibleLines.length === 1 || rootRow) {
        const lineGid = visibleLines[0]?.gid || rootRow.gid;
        html += this._renderStationsForLine(lineGid, data.childMap, data.rowByGid, activeGid, activeStationGid, visTypes, 16);
      }
    }

    this._treeBody.innerHTML = html;

    // ── 搜索模式：覆盖 treeBody 显示搜索结果 ──────────────────────
    const q = (this._searchQuery || '').toLowerCase();
    if (q) {
      this._treeBody.innerHTML = this._buildSearchResultHtml(q, data, visTypes, activeGid);
    }

    // ── BOP 版本下拉（从 _verSlot 查）──
    const verBar = this._verSlot?.querySelector('#llTreeVerBar');
    const verDd  = this._verSlot?.querySelector('#llTreeVerDd');
    if (verBar && verDd) {
      verBar.addEventListener('click', e => {
        if (e.target.closest('.ll-tree-ver-opt')) return;
        verDd.classList.toggle('open');
      });
      verDd.querySelectorAll('.ll-tree-ver-opt').forEach(opt => {
        opt.addEventListener('click', e => {
          e.stopPropagation();
          verDd.classList.remove('open');
          if (this._onVersionChange) this._onVersionChange(opt.dataset.gid);
        });
      });
      document.addEventListener('click', e => {
        if (!e.target.closest('#llTreeVerBar')) verDd?.classList.remove('open');
      }, { once: true });
    }



    // ── 线体行 toggle（在 _lineSlot 里）──
    this._lineSlot?.querySelectorAll('.ll-tn-tog-btn').forEach(btn => {
      btn.addEventListener('click', e => {
        e.stopPropagation();
        const gid = btn.dataset.gid;
        if (this._treeExpanded.has(gid)) this._treeExpanded.delete(gid);
        else this._treeExpanded.add(gid);
        this._renderTree(this._currentGid);
      });
    });

    // ── 线体行点击（整行）──
    this._lineSlot?.querySelectorAll('.ll-tree-root-bar').forEach(bar => {
      bar.addEventListener('click', e => {
        if (e.target.closest('.ll-tn-tog-btn')) return;
        const gid = rootRow.gid;
        const row = data.rowByGid.get(gid);
        if (!row) return;
        this._currentGid = gid; this._currentRow = row;
        this._renderTree(gid);
        this._renderProps(gid, row);
        this._renderRels(gid);
        this._renderRules(gid, row);
        this._renderKnowledge(gid);
        this._renderDetailEmpty();
        if (this._onNodeActivate) this._onNodeActivate(gid);
      });
    });

    // ── toggle 折叠展开（_treeBody 内的工位/工序）──
    this._treeBody.querySelectorAll('.ll-tn-tog-btn').forEach(btn => {
      btn.addEventListener('click', e => {
        e.stopPropagation();
        if (this._inlineAddPending) return; // inline add 进行中，不触发重渲染
        const gid = btn.dataset.gid;
        if (this._treeExpanded.has(gid)) this._treeExpanded.delete(gid);
        else this._treeExpanded.add(gid);
        this._renderTree(this._currentGid);
      });
    });

    // ── 树节点点击 ──
    this._treeBody.querySelectorAll('.ll-tn').forEach(tn => {
      tn.addEventListener('click', e => {
        e.stopPropagation();
        const gid = tn.dataset.gid;
        if (!gid) return;
        const row = data.rowByGid.get(gid);
        if (!row) return;
        this._currentGid = gid;
        this._currentRow = row;
        if (!this._inlineAddPending) { // inline add 进行中，不触发树重渲染
          this._treeExpanded.add(gid);
          this._renderTree(gid);
        }
        this._renderProps(gid, row);
        this._renderRels(gid);
        this._renderRules(gid, row);
        this._renderKnowledge(gid);
        this._renderDetailEmpty();
        if (this._onNodeActivate) this._onNodeActivate(gid);
      });

      // 右键菜单：与主界面卡片右键行为一致
      tn.addEventListener('contextmenu', e => {
        e.preventDefault();
        e.stopPropagation();
        const gid = tn.dataset.gid;
        if (!gid) return;
        if (typeof _showCtxMenu === 'function') {
          _showCtxMenu(e.clientX, e.clientY, gid);
        }
      });
    });

    // ── 折叠全部 ──
    this._el.querySelector('#llDpTreeCollapse')?.addEventListener('click', () => {
      this._treeExpanded.clear();
      this._renderTree(this._currentGid);
    });

    // ── + 按钮：hover 显示，点击触发内联添加 ──
    const bindAddBtns = (root) => {
      root?.querySelectorAll('.ll-tn-add-btn').forEach(btn => {
        btn.addEventListener('click', e => {
          e.stopPropagation();
          this._triggerInlineAdd(btn.dataset.parentGid, btn.dataset.childType);
        });
      });
    };
    bindAddBtns(this._treeBody);
    bindAddBtns(this._lineSlot);

    // ── 内联添加输入框 ──
    const inp = this._treeBody?.querySelector('.ll-tn-inline-add-inp');
    if (inp) {
      let _done = false;
      const commit = async () => {
        if (_done) return; _done = true;
        await this._commitInlineAdd(inp.value.trim());
      };
      const cancel = () => {
        if (_done) return; _done = true;
        this._inlineAddPending = null;
        this._renderTree(this._currentGid);
      };
      setTimeout(() => { inp.focus(); inp.select(); }, 0);
      inp.addEventListener('keydown', e => {
        if (e.key === 'Enter') { e.preventDefault(); commit(); }
        else if (e.key === 'Escape') cancel();
      });
      // blur：有内容则提交，空内容则取消
      inp.addEventListener('blur', () => setTimeout(() => {
        if (!_done) { if (inp.value.trim()) commit(); else cancel(); }
      }, 150));
    }

    // ── 滚动高亮节点到视图中央 ──
    requestAnimationFrame(() => {
      const active = this._treeBody.querySelector('.ll-tn-active');
      if (active) active.scrollIntoView({ block: 'center', behavior: 'smooth' });
    });

    // 每次重渲染后直接绑 dragstart 到可拖拽节点
    this._rebindTreeDragStart();
  }

  // ── 内联添加：触发 + 构建 + 提交 ─────────────────────────────────────────────

  _isEditable() {
    return this._getLineageData()?.isEditable !== false;
  }

  _triggerInlineAdd(parentGid, childType) {
    if (!parentGid || !childType) return;
    this._inlineAddPending = { parentGid, childType };
    const data = this._getLineageData();
    if (data) {
      let cur = data.rowByGid.get(parentGid);
      if (cur) {
        while (cur) {
          this._treeExpanded.add(cur.gid);
          cur = cur.parent_gid ? data.rowByGid.get(cur.parent_gid) : null;
        }
      } else {
        this._treeExpanded.add(parentGid);
      }
    } else {
      this._treeExpanded.add(parentGid);
    }
    this._renderTree(this._currentGid);
  }

  _buildInlineAddRow(indent, childType) {
    const defaultTitle = _INLINE_ADD_DEFAULT_TITLE[childType] || '新节点';
    return `<div class="ll-tn-inline-add" style="padding-left:${indent}px">
      <span style="width:11px;flex-shrink:0"></span>
      <span class="lv-nt-dot lv-nt-${_he(childType)}"></span>
      <input class="ll-tn-inline-add-inp" type="text" value="${_he(defaultTitle)}" placeholder="${_he(defaultTitle)}">
    </div>`;
  }

  async _commitInlineAdd(title) {
    const pending = this._inlineAddPending;
    if (!pending) return;
    this._inlineAddPending = null;
    if (!title) { this._renderTree(this._currentGid); return; }
    const data = this._getLineageData();
    const existingChildren = (data?.childMap.get(pending.parentGid) || []).filter(r => !r.is_deleted);
    const maxSort = existingChildren.reduce((m, r) => Math.max(m, r.sort_order ?? 0), 0);
    const body = {
      version_gid: data?.versionGid,
      parent_gid:  pending.parentGid,
      node_type:   pending.childType,
      title,
      sort_order:  maxSort + 1,
    };
    try {
      await this._cf('/api/bop/entries', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      this._toast?.('节点已创建', 'ok');
      await this._reloadData();
    } catch (e) {
      this._toast?.('创建失败: ' + e.message, 'error');
      this._renderTree(this._currentGid);
    }
  }

  openEmpty() {
    this._currentGid = null;
    this._currentRow = null;
    this._show();
    this._renderEmptyTree();
    this._propsBody.innerHTML = '';
    this._relsBody.innerHTML = '';
    this._rulesBody.innerHTML = '';
    this._knowBody.innerHTML = '';
    this._renderDetailEmpty();
  }

  close(keepUserFlag) {
    this._isOpen = false;
    if (!keepUserFlag) this._userClosed = true;
    this._el.classList.remove('open');
  }

  toggle() {
    if (this._isOpen) this.close(false);
    else { this._userClosed = false; if (this._currentGid) this.open(this._currentGid); else this._show(); }
  }

  refresh() {
    if (this._currentGid) this.open(this._currentGid);
  }

  /** 提供给 lineage.js 注入 _data 引用（向后兼容旧接口） */
  set data(d) { this._legacyData = d; }

  // ── 内部：显示/隐藏 ───────────────────────────────────────────────────────

  _show() {
    this._isOpen = true;
    this._userClosed = false;
    this._el.classList.add('open');
    // 无节点时渲染空树
    if (!this._currentGid) this._renderEmptyTree();
  }

  _openDetDrawer() {
    this._detDrawer?.classList.add('open');
    document.getElementById('llDetDrawerSave').style.display = '';
    document.getElementById('llDetDrawerUnlink').style.display = '';
  }

  _closeDetDrawer(force) {
    if (this._detPinned && !force) return;
    this._detDrawer?.classList.remove('open');
    this._detPinned = false;
    document.getElementById('llDetDrawerPin')?.classList.remove('active');
  }

  _renderAll(gid, row) {
    this._renderTree(gid);
    this._renderProps(gid, row);
    this._renderDetailEmpty();
  }

  // ── 列0：节点树 ───────────────────────────────────────────────────────────

  _renderEmptyTree() {
    this._treeBody.innerHTML = `
      <div class="ll-tree-empty">
        <div class="ll-tree-empty-hint">这个 BOP 还没有内容</div>
        <button class="ll-tree-empty-btn" id="llDpNewLineBtn">＋ 新建线体</button>
      </div>`;
    this._treeBody.querySelector('#llDpNewLineBtn')?.addEventListener('click', () => {
      this._openAddDetail('child', null, 'line_process', '线体');
    });
  }

  /** 渲染线体下的工位子树，应用节点类型过滤 */
  // ── 节点树拖拽（自定义 mouse 拖拽，与 layout_mode.js 同方案）────────────────

  _setupTreeDragOnce() {
    const clearFeedback = () => {
      const body = this._treeBody;
      if (!body) return;
      body.querySelectorAll('[data-drop-pos]').forEach(el => delete el.dataset.dropPos);
      body.querySelectorAll('.ll-tn-drop-reparent').forEach(el => el.classList.remove('ll-tn-drop-reparent'));
    };

    document.addEventListener('mousemove', e => {
      const pending = this._treeDragPending;
      if (pending) {
        if (Math.abs(e.clientX - pending.startX) > 5 || Math.abs(e.clientY - pending.startY) > 5) {
          // 激活拖拽：创建跟手 ghost
          const ghost = document.createElement('div');
          ghost.className = 'll-tn-ghost';
          ghost.textContent = pending.el.querySelector('.ll-tn-lbl')?.textContent || '';
          ghost.style.cssText = `position:fixed;pointer-events:none;z-index:9999;padding:2px 10px;` +
            `font-size:11px;border-radius:4px;background:var(--blue,#89b4fa);` +
            `color:var(--base,#1e1e2e);left:${e.clientX+14}px;top:${e.clientY-8}px;white-space:nowrap;`;
          document.body.appendChild(ghost);
          pending.el.classList.add('ll-tn-dragging');
          this._treeDragState   = { ...pending, ghost, currentTarget: null, currentAction: null };
          this._treeDragPending = null;
        }
        return;
      }

      const drag = this._treeDragState;
      if (!drag) return;

      drag.ghost.style.left = (e.clientX + 14) + 'px';
      drag.ghost.style.top  = (e.clientY - 8)  + 'px';

      // 临时隐藏 ghost 才能用 elementFromPoint 找到下面的元素
      drag.ghost.style.display = 'none';
      const el = document.elementFromPoint(e.clientX, e.clientY);
      drag.ghost.style.display = '';

      clearFeedback();
      drag.currentTarget = null;
      drag.currentAction = null;
      const tn = el?.closest?.('.ll-tn[data-gid]');
      if (!tn || tn.dataset.gid === drag.gid) return;

      const targetType      = tn.dataset.nodeType;
      const targetParentGid = tn.dataset.parentGid;
      const isSibling       = targetType === drag.nodeType && targetParentGid === drag.parentGid;
      const isValidParent   = (TREE_VALID_PARENTS[drag.nodeType] || new Set()).has(targetType);

      if (isSibling) {
        const rect   = tn.getBoundingClientRect();
        const action = (e.clientY - rect.top) < rect.height / 2 ? 'before' : 'after';
        tn.dataset.dropPos   = action;
        drag.currentTarget   = tn.dataset.gid;
        drag.currentAction   = action;
      } else if (isValidParent) {
        tn.classList.add('ll-tn-drop-reparent');
        drag.currentTarget = tn.dataset.gid;
        drag.currentAction = 'into';
      }
    });

    document.addEventListener('mouseup', e => {
      if (e.button !== 0) return;

      // pending：没达到移动阈值，视为普通点击
      if (this._treeDragPending) {
        const gid = this._treeDragPending.el.dataset.gid;
        this._treeDragPending = null;
        this._handleTreeNodeClick(gid);
        return;
      }

      const drag = this._treeDragState;
      if (!drag) return;
      clearFeedback();
      drag.ghost.remove();
      drag.el.classList.remove('ll-tn-dragging');
      this._treeDragState = null;
      if (drag.currentTarget && drag.currentAction) {
        this._commitTreeDrop(drag.gid, drag.currentTarget, drag.currentAction);
      }
    });
  }

  // 每次 _renderTree 后调用，给可拖拽节点绑 mousedown
  _rebindTreeDragStart() {
    const body = this._treeBody;
    if (!body) return;
    body.querySelectorAll('.ll-tn[data-draggable="1"]').forEach(tn => {
      tn.addEventListener('mousedown', e => {
        if (e.button !== 0) return;
        if (e.target.closest('.ll-tn-add-btn')) return; // + 按钮不拦截，让 click 正常触发
        e.preventDefault(); // 阻止文本选中 & 默认 click 序列
        this._treeDragPending = {
          gid: tn.dataset.gid, nodeType: tn.dataset.nodeType, parentGid: tn.dataset.parentGid,
          startX: e.clientX, startY: e.clientY, el: tn,
        };
      });
    });
  }

  // 无拖拽时的点击选中逻辑（替代被 preventDefault 阻断的 click）
  _handleTreeNodeClick(gid) {
    const data = this._getLineageData();
    if (!data) return;
    const row = data.rowByGid.get(gid);
    if (!row) return;
    this._currentGid = gid;
    this._currentRow = row;
    this._treeExpanded.add(gid);
    this._renderTree(gid);
    this._renderProps(gid, row);
    this._renderDetailEmpty();
    if (this._onNodeActivate) this._onNodeActivate(gid);
  }

  async _commitTreeDrop(dragGid, targetGid, action) {
    const data = this._getLineageData();
    if (!data) return;
    const dragRow   = data.rowByGid.get(dragGid);
    const targetRow = data.rowByGid.get(targetGid);
    if (!dragRow || !targetRow) return;

    const newParentGid = action === 'into' ? targetGid : targetRow.parent_gid;
    const oldParentGid = dragRow.parent_gid;
    const newParentType = action === 'into' ? targetRow.node_type : data.rowByGid.get(newParentGid)?.node_type;
    if (!(TREE_VALID_PARENTS[dragRow.node_type] || new Set()).has(newParentType)) return;

    try {
      // Step 1: 换父
      if (oldParentGid !== newParentGid) {
        await this._cf(`/api/bop/entries/${encodeURIComponent(dragGid)}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ parent_gid: newParentGid }),
        });
      }
      // Step 2: 重排序（仅 before/after 时）
      if (action !== 'into') {
        const siblings = (data.childMap.get(newParentGid) || [])
          .filter(r => r.node_type === dragRow.node_type && r.gid !== dragGid)
          .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));
        const targetIdx = siblings.findIndex(r => r.gid === targetGid);
        siblings.splice(action === 'after' ? targetIdx + 1 : targetIdx, 0, dragRow);
        const patches = siblings
          .map((r, i) => ({ gid: r.gid, newSeq: i + 1, oldSeq: r.sort_order }))
          .filter(p => p.newSeq !== p.oldSeq || p.gid === dragGid);
        await Promise.all(patches.map(p =>
          this._cf(`/api/bop/entries/${encodeURIComponent(p.gid)}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sort_order: p.newSeq }),
          })
        ));
      }
      await this._reloadData();
    } catch (err) {
      this._toast?.('操作失败：' + (err.message || err), 'error');
    }
  }

  _renderStationsForLine(lineGid, childMap, rowByGid, activeGid, activeStationGid, visTypes, indent) {
    let html = '';
    const stations = (childMap.get(lineGid) || []).filter(r => !r.is_deleted && visTypes.has(r.node_type));
    const isEditable = this._isEditable();
    for (const sta of stations) {
      const isActiveStation = sta.gid === activeStationGid;
      const staExpanded = this._treeExpanded.has(sta.gid);
      const staChildren = (childMap.get(sta.gid) || []).filter(r => !r.is_deleted && visTypes.has(r.node_type));
      const staChildType = CHILD_TYPE_MAP[sta.node_type]?.type;
      html += `<div class="${isActiveStation ? 'll-tn-station-wrap' : ''}">`;
      html += `<div class="ll-tn${sta.gid === activeGid ? ' ll-tn-active' : ''}" data-gid="${_he(sta.gid)}"
        data-node-type="${_he(sta.node_type)}" data-parent-gid="${_he(lineGid)}"
        style="padding-left:${indent}px">
        <span class="ll-tn-tog-btn" data-gid="${_he(sta.gid)}" style="font-size:9px;color:var(--overlay1);width:11px;text-align:center;flex-shrink:0;cursor:pointer">
          ${staChildren.length ? (staExpanded ? '▼' : '▶') : '·'}
        </span>
        <span class="lv-nt-dot lv-nt-${_he(sta.node_type)}"></span>
        <span class="ll-tn-lbl">${_he(sta.title||sta.gid)}</span>
        ${isEditable && staChildType ? `<span class="ll-tn-add-btn" data-parent-gid="${_he(sta.gid)}" data-child-type="${_he(staChildType)}" title="添加${CHILD_TYPE_MAP[sta.node_type]?.label || '子节点'}">+</span>` : ''}
      </div>`;
      if (staExpanded) {
        html += this._renderTreeNodesFiltered(sta.gid, childMap, rowByGid, activeGid, indent / 16 + 1, visTypes);
      }
      html += `</div>`;
    }
    // 内联添加行（line 的子节点）
    if (this._inlineAddPending?.parentGid === lineGid) {
      html += this._buildInlineAddRow(indent, this._inlineAddPending.childType);
    }
    return html;
  }

    _renderTreeNodes(parentGid, childMap, rowByGid, activeGid, depth) {
    const children = (childMap.get(parentGid) || []).filter(r => !r.is_deleted);
    if (!children.length) return '';
    let html = '';
    const indent = depth * 16;
    for (const row of children) {
      const hasChildren = (childMap.get(row.gid) || []).filter(r => !r.is_deleted).length > 0;
      const isExpanded = this._treeExpanded.has(row.gid);
      const isActive = row.gid === activeGid;
      const dot = NODE_TYPE_DOT[row.node_type] || '#6c7086';
      const isDraggable = TREE_DRAGGABLE_TYPES.has(row.node_type);
      html += `
        <div class="ll-tn${isActive ? ' ll-tn-active' : ''}" data-gid="${_he(row.gid)}"
          data-node-type="${_he(row.node_type)}" data-parent-gid="${_he(parentGid)}"
          ${isDraggable ? 'data-draggable="1"' : ''}
          style="padding-left:${indent + 4}px">
          <span class="ll-tn-tog-btn" data-gid="${_he(row.gid)}" style="font-size:9px;color:var(--overlay1);width:11px;text-align:center;flex-shrink:0;cursor:pointer">
            ${hasChildren ? (isExpanded ? '▼' : '▶') : '·'}
          </span>
          <span class="lv-nt-dot lv-nt-${_he(row.node_type)}"></span>
          <span class="ll-tn-lbl">${_he(row.title || row.gid)}</span>
        </div>`;
      if (isExpanded) {
        html += this._renderTreeNodes(row.gid, childMap, rowByGid, activeGid, depth + 1);
      }
    }
    return html;
  }

  _renderTreeNodesFiltered(parentGid, childMap, rowByGid, activeGid, depth, visTypes) {
    const children = (childMap.get(parentGid) || []).filter(r => !r.is_deleted && visTypes.has(r.node_type));
    const hasPendingAdd = this._inlineAddPending?.parentGid === parentGid;
    if (!children.length && !hasPendingAdd) return '';
    let html = '';
    const indent = depth * 16;
    const isEditable = this._isEditable();
    for (const row of children) {
      const hasChildren = (childMap.get(row.gid) || []).filter(r => !r.is_deleted && visTypes.has(r.node_type)).length > 0;
      const isExpanded = this._treeExpanded.has(row.gid);
      const isActive = row.gid === activeGid;
      const isDraggable = TREE_DRAGGABLE_TYPES.has(row.node_type);
      const childType = CHILD_TYPE_MAP[row.node_type]?.type;
      html += `
        <div class="ll-tn${isActive ? ' ll-tn-active' : ''}" data-gid="${_he(row.gid)}"
          data-node-type="${_he(row.node_type)}" data-parent-gid="${_he(parentGid)}"
          ${isDraggable ? 'data-draggable="1"' : ''}
          style="padding-left:${indent + 4}px">
          <span class="ll-tn-tog-btn" data-gid="${_he(row.gid)}" style="font-size:9px;color:var(--overlay1);width:11px;text-align:center;flex-shrink:0;cursor:pointer">
            ${hasChildren ? (isExpanded ? '▼' : '▶') : '·'}
          </span>
          <span class="lv-nt-dot lv-nt-${_he(row.node_type)}"></span>
          <span class="ll-tn-lbl">${_he(row.title || row.gid)}</span>
          ${isEditable && childType ? `<span class="ll-tn-add-btn" data-parent-gid="${_he(row.gid)}" data-child-type="${_he(childType)}" title="添加${CHILD_TYPE_MAP[row.node_type]?.label || '子节点'}">+</span>` : ''}
        </div>`;
      if (isExpanded) {
        html += this._renderTreeNodesFiltered(row.gid, childMap, rowByGid, activeGid, depth + 1, visTypes);
      }
    }
    if (hasPendingAdd) {
      html += this._buildInlineAddRow(indent + 4, this._inlineAddPending.childType);
    }
    return html;
  }

  // ── 列1：属性 ─────────────────────────────────────────────────────────────

  _renderProps(gid, row) {
    const data = this._getLineageData();
    const parentRow = row.parent_gid ? data?.rowByGid.get(row.parent_gid) : null;
    const nodeTypeLabel = row.node_type || '';
    const lineGrantSet = data?.lineGrantSet || new Set();
    const lineReadOnly = !!data?.lineReadOnly;
    const currentLineGid = this._findAncestorOfType(gid, 'line_process', data?.rowByGid) || (row.node_type === 'line_process' ? row.gid : null);
    const canEditCurrentLine = !lineReadOnly || !currentLineGid || lineGrantSet.has(currentLineGid);

    let html = `
      <div class="ll-props-node-hdr">
        <div class="ll-props-title-row">
          <span class="ll-props-nt">${_he(nodeTypeLabel)}</span>
          <input class="ll-props-title-inp" id="llPropsTitleInp"
                 value="${_he(row.title || '')}" placeholder="标题…">
        </div>
        <div class="ll-props-parent">
          <span class="ll-props-parent-lbl">父级</span>
          <span class="ll-props-parent-val">${_he(parentRow?.title || '（无）')}</span>
        </div>
      </div>
      ${canEditCurrentLine ? '' : '<div class="ll-props-sec" style="color:var(--yellow,#f9e2af)">当前线体为只读，复制相关操作仍可用</div>'}
      <div class="ll-props-sec">属性</div>
      <div id="llPropsOntoArea"><div style="color:var(--surface2);font-size:11px;padding:8px 4px">加载中…</div></div>
      <div class="ll-props-sec">关系</div>
      <div id="llPropsRelsArea"><div style="color:var(--surface2);font-size:11px;padding:8px 4px">加载中…</div></div>`;

    this._propsBody.innerHTML = html;

    // 标题保存
    const titleInp = this._propsBody.querySelector('#llPropsTitleInp');
    if (!canEditCurrentLine && titleInp) titleInp.disabled = true;
    const saveTitleFn = async () => {
      const newTitle = titleInp.value.trim();
      if (!newTitle || newTitle === row.title) return;
      try {
        await this._patchEntry(gid, { title: newTitle });
        row.title = newTitle;
        this._renderTree(this._currentGid);
        // 同步主视图所有同 gid 的 title 元素
        document.querySelectorAll(`[data-gid="${gid}"] .lv-title, [data-gid="${gid}"] .ll-station-title`)
          .forEach(el => { if (!el.matches('input')) el.textContent = newTitle; });
      } catch (e) {
        this._toast?.('保存失败: ' + (e?.message || e), 'error');
        titleInp.value = row.title || '';
      }
    };
    titleInp?.addEventListener('blur', saveTitleFn);
    titleInp?.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); titleInp.blur(); } });

    // 加载本体属性
    this._loadOntoProps(gid, row);
    this._relsBody = this._propsBody.querySelector('#llPropsRelsArea');
    this._renderRels(gid, this._relsBody);
  }


  async _computeDerivedProp(gid, p) {
    const cfg = typeof p.field_config === 'string'
      ? JSON.parse(p.field_config)
      : (p.field_config || {});

    // 公式模式
    if (cfg.expr) return this._evalDerivedExpr(gid, cfg.expr);

    // 简单聚合模式
    const { aggregate, child_node_type, child_property } = cfg;
    if (!aggregate || !child_node_type) return null;

    const data = this._getLineageData();
    const allChildren = Array.from(data?.childMap?.get(gid) || []);
    const children = allChildren.filter(c => c.node_type === child_node_type);
    if (!children.length) return aggregate === 'COUNT' ? 0 : null;
    if (aggregate === 'COUNT') return children.length;
    if (!child_property) return null;

    const values = await this._fetchChildPropValues(children, child_property);
    if (!values.length) return null;
    switch (aggregate) {
      case 'SUM': return Math.round(values.reduce((a, b) => a + b, 0) * 100) / 100;
      case 'AVG': return Math.round(values.reduce((a, b) => a + b, 0) / values.length * 100) / 100;
      case 'MAX': return Math.max(...values);
      case 'MIN': return Math.min(...values);
      default:    return null;
    }
  }

  /** 获取子节点的某个属性值（优先实体表 entity_data，其次 entity-props API，最后兜底 meta） */
  async _fetchChildPropValues(children, propName) {
    // 第一优先：entity_data（实体表列值，SQL JOIN 已带入）
    let values = children
      .map(c => {
        const ed = c.entity_data;
        if (ed && typeof ed === 'object' && ed[propName] != null) return Number(ed[propName]);
        return NaN;
      })
      .filter(v => !isNaN(v));
    // 第二优先：entity-props API
    if (!values.length) {
      const results = await Promise.all(
        children.map(c =>
          this._cf(`/api/bop/entries/${encodeURIComponent(c.gid)}/entity-props`)
            .then(r => r?.data?.[propName])
            .catch(() => null)
        )
      );
      values = results.filter(v => v != null).map(Number).filter(v => !isNaN(v));
    }
    // 最后兜底：meta
    if (!values.length) {
      values = children
        .map(c => {
          const meta = (c.meta && typeof c.meta === 'object') ? c.meta : {};
          const v = meta[propName];
          return v != null ? Number(v) : NaN;
        })
        .filter(v => !isNaN(v));
    }
    return values;
  }

  /** 解析并执行派生公式 */
  async _evalDerivedExpr(gid, expr) {
    const data = this._getLineageData();
    const allChildren = Array.from(data?.childMap?.get(gid) || []);

    // 先收集所有聚合调用并异步求值
    const aggRe = /\b(SUM|COUNT|AVG|MAX|MIN)\s*\(\s*(\w+)\s*\)/gi;
    const pending = [];  // { idx, func, prop }
    let m;
    while ((m = aggRe.exec(expr)) !== null) {
      pending.push({ idx: pending.length, func: m[1].toUpperCase(), prop: m[2] });
    }

    // 并行求所有聚合值
    const aggResults = await Promise.all(pending.map(async p => {
      if (p.func === 'COUNT') return { idx: p.idx, val: allChildren.length };
      const values = await this._fetchChildPropValues(allChildren, p.prop);
      if (!values.length) return { idx: p.idx, val: 0 };
      switch (p.func) {
        case 'SUM': return { idx: p.idx, val: values.reduce((a,b)=>a+b,0) };
        case 'AVG': return { idx: p.idx, val: values.reduce((a,b)=>a+b,0) / values.length };
        case 'MAX': return { idx: p.idx, val: Math.max(...values) };
        case 'MIN': return { idx: p.idx, val: Math.min(...values) };
        default: return { idx: p.idx, val: 0 };
      }
    }));

    // 替换所有聚合调用为计算结果
    const resultMap = new Map(aggResults.map(r => [r.idx, r.val]));
    aggRe.lastIndex = 0;
    let ri = 0;
    const expression = expr.replace(aggRe, () => String(resultMap.get(ri++) ?? 0));

    // 安全求值
    const safe = expression.replace(/[^0-9+\-*/().\s]/g, '');
    if (!safe.trim()) return null;
    try {
      const result = Function('"use strict"; return (' + safe + ')')();
      return typeof result === 'number' ? Math.round(result * 100) / 100 : null;
    } catch { return null; }
  }

  async _loadOntoProps(gid, row) {
    const area = this._propsBody.querySelector('#llPropsOntoArea');
    if (!area) return;
    const data = this._getLineageData();
    const lineGrantSet = data?.lineGrantSet || new Set();
    const lineReadOnly = !!data?.lineReadOnly;
    const currentLineGid = this._findAncestorOfType(gid, 'line_process', data?.rowByGid) || (row?.node_type === 'line_process' ? row.gid : null);
    const canEditCurrentLine = !lineReadOnly || !currentLineGid || lineGrantSet.has(currentLineGid);
    try {
      const nodeType = row.node_type;
      const schemaResp = await this._cf(`/api/ontology/schema/${encodeURIComponent(nodeType)}`);
      const props = (schemaResp?.properties || [])
        .filter(p => p.prop_kind === 'data' && Boolean(p.show_in_detail) !== false)
        .sort((a, b) => (a.sort_order ?? 99) - (b.sort_order ?? 99));

      // 收集 show_in_detail=false 的关系 link_type，_renderRels 据此隐藏对应分组
      this._hiddenLinkTypes = new Set(
        (schemaResp?.relations || [])
          .filter(r => r.show_in_detail === false)
          .map(r => r.link_type_binding)
      );

      if (!props.length) { area.innerHTML = '<div style="color:var(--surface2);font-size:11px;padding:4px">暂无本体属性</div>'; return; }

      const entityProps = props.filter(p => p.storage_hint === 'entity_table');
      const metaProps   = props.filter(p => p.storage_hint !== 'entity_table');

      let entityVals = {};
      if (entityProps.length) {
        try {
          const er = await this._cf(`/api/bop/entries/${encodeURIComponent(gid)}/entity-props`);
          entityVals = er?.data || {};
        } catch {}
      }
      const metaVals = (typeof row.meta === 'object' && row.meta) ? row.meta : {};

      // 保持本体 sort_order 顺序，标记来源
      const allProps = props.map(p => ({
        ...p,
        _src: p.storage_hint === 'derived' ? 'derived'
              : p.storage_hint === 'entity_table' ? 'entity'
              : 'meta',
      }));

      // 预计算所有派生属性值
      const derivedVals = {};
      await Promise.all(
        allProps.filter(p => p._src === 'derived').map(async p => {
          derivedVals[p.name] = await this._computeDerivedProp(gid, p);
        })
      );

      let html = '';
      for (const p of allProps) {
        // 派生属性：只读显示 + 公式说明
        if (p._src === 'derived') {
          const dVal = derivedVals[p.name];
          const cfg = typeof p.field_config === 'string' ? JSON.parse(p.field_config) : (p.field_config || {});
          const formula = cfg.expr
            ? cfg.expr
            : `${cfg.aggregate || ''}(${cfg.child_node_type || ''}.${cfg.child_property || ''})`;
          html += `<div class="ll-props-row">
            <span class="ll-props-key" title="${_he(p.description)}">${_he(p.label_zh || p.name)}</span>
            <div class="ll-props-val ll-props-derived-wrap">
              <span class="ll-props-derived-val">${dVal != null ? dVal : '—'}</span>
              <span class="ll-props-derived-badge" title="${_he(formula)}">∑ ${_he(formula)}</span>
            </div>
          </div>`;
          continue;
        }
        // entity_table 属性只从实体表读取，meta 属性从 bop_entries.meta 读取
        const val = p._src === 'entity'
          ? (entityVals[p.name] ?? '')
          : (metaVals[p.name] ?? '');
        const reqClass = p.required ? ' req' : '';
        let inputHtml = '';
        if (p.data_type === 'enum' && p.enum_values?.length) {
          const opts = (typeof p.enum_values === 'string' ? JSON.parse(p.enum_values) : p.enum_values)
            .map(v => `<option value="${_he(v)}"${String(val) === String(v) ? ' selected' : ''}>${_he(v)}</option>`)
            .join('');
          inputHtml = `<select class="ll-props-sel" data-prop="${_he(p.name)}" data-src="${p._src}">${opts}</select>`;
        } else if (p.data_type === 'boolean') {
          inputHtml = `<select class="ll-props-sel" data-prop="${_he(p.name)}" data-src="${p._src}">
            <option value=""${!val ? ' selected' : ''}>—</option>
            <option value="true"${val === true || val === 'true' ? ' selected' : ''}>是</option>
            <option value="false"${val === false || val === 'false' ? ' selected' : ''}>否</option>
          </select>`;
        } else {
          inputHtml = `<input class="ll-props-inp${reqClass}" data-prop="${_he(p.name)}" data-src="${p._src}"
            data-dtype="${_he(p.data_type || 'string')}"
            value="${_he(val)}" placeholder="${_he(p.description || p.label_zh || p.name)}">`;
        }
        html += `<div class="ll-props-row"><span class="ll-props-key" title="${_he(p.description)}">${_he(p.label_zh || p.name)}</span><div class="ll-props-val">${inputHtml}</div></div>`;
      }
      area.innerHTML = html;

      if (!canEditCurrentLine) {
        area.querySelectorAll('.ll-props-inp, .ll-props-sel').forEach(inp => { inp.disabled = true; });
      }

      // 保存逻辑
      area.querySelectorAll('.ll-props-inp, .ll-props-sel').forEach(inp => {
        const save = async () => {
          const propName = inp.dataset.prop;
          const src = inp.dataset.src;
          const dtype = inp.dataset.dtype || 'string';
          let val = inp.value;
          if (val === '' || val == null) val = null;
          else if (dtype === 'integer') { val = parseInt(val, 10); if (isNaN(val)) return; }
          else if (dtype === 'float')   { val = parseFloat(val);   if (isNaN(val)) return; }
          else if (dtype === 'boolean') { val = val === 'true' ? true : val === 'false' ? false : null; }

          try {
            // 统一走 entity-props PATCH（后端自动路由到实体表列/ext/bop_entries.meta）
            await this._cf(`/api/bop/entries/${encodeURIComponent(gid)}/entity-props`, {
              method: 'PATCH', body: JSON.stringify({ [propName]: val }),
            });
            if (src === 'entity') {
              entityVals[propName] = val;
              // 同步更新 row.entity_data，使布局卡片立即显示新值
              if (row.entity_data && typeof row.entity_data === 'object') {
                row.entity_data[propName] = val;
              }
            } else {
              metaVals[propName] = val;
            }
          } catch (e) {
            this._toast?.('保存失败: ' + (e?.message || e), 'error');
          }
          // 保存后立即刷新属性面板 + 布局卡片（保持画面焦点不变）
          this._renderProps(gid, data.rowByGid.get(gid) || row);
          this._preserveLayoutView();
          this._reloadData?.();
        };
        inp.addEventListener('blur', save);
        inp.addEventListener('change', save);
        inp.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); save(); } });
      });

    } catch (e) {
      area.innerHTML = `<div style="color:var(--red);font-size:11px;padding:4px">属性加载失败</div>`;
    }
  }

  // ── 列2：关系 ─────────────────────────────────────────────────────────────

  async _renderRels(gid) {
    const mountEl = this._relsBody;
    if (!mountEl) return;
    mountEl.innerHTML = '<div style="color:var(--surface2);font-size:11px;padding:8px">加载中…</div>';
    const data = this._getLineageData();
    const lineGrantSet = data?.lineGrantSet || new Set();
    const lineReadOnly = !!data?.lineReadOnly;
    const row = data?.rowByGid?.get(gid);
    const currentLineGid = this._findAncestorOfType(gid, 'line_process', data?.rowByGid) || (row?.node_type === 'line_process' ? row.gid : null);
    const canEditCurrentLine = !lineReadOnly || !currentLineGid || lineGrantSet.has(currentLineGid);
    const hasChildren = data ? (data.childMap.get(gid) || []).filter(r => !r.is_deleted).length > 0 : false;

    let links = [];
    try {
      const resp = await this._cf(
        `/api/bop/entry-links?entry_gid=${encodeURIComponent(gid)}${hasChildren ? '&recursive=true' : ''}`
      );
      links = resp?.data || [];
    } catch {}
    this._relLinks = links;

    // 子节点从 childMap 取
    const childRows = data ? (data.childMap.get(gid) || []).filter(r => !r.is_deleted) : [];

    let html = '';
    for (const grp of REL_GROUPS) {
      // 本体关系 show_in_detail=false 时跳过整组
      if (grp.linkTypes && this._hiddenLinkTypes?.size && grp.linkTypes.every(lt => this._hiddenLinkTypes.has(lt))) {
        continue;
      }
      let items = [];
      if (grp.key === 'child') {
        items = childRows.map(r => ({
          _key: 'child', _title: r.title || r.gid, _badge: r.node_type,
          _ntType: r.node_type || 'process',
          _row: r, _sourceGid: gid, _sourceTitle: null,
          link: { link_type: 'child', entity_gid: r.gid }, source_entry_gid: gid, source_entry_title: null,
        }));
      } else {
        items = links
          .filter(l => grp.linkTypes.includes(l.link_type))
          .map(l => ({
            _key: grp.key, _title: l.entity_title || l.entity_gid, _badge: l.link_type,
            _ntType: grp.ntType, link: l,
            source_entry_gid: l.source_entry_gid || gid,
            source_entry_title: l.source_entry_title,
          }));
      }

      const isOpen = !items.length ? false : true;
      html += `
        <div class="ll-rg">
          <div class="ll-rg-hdr" data-key="${_he(grp.key)}">
            <span class="ll-rg-tog">${isOpen ? '▼' : '▶'}</span>
            <span class="lv-nt-dot lv-nt-${_he(grp.ntType)}"></span>
            <span class="ll-rg-name">${_he(grp.name)}</span>
            <span class="ll-rg-cnt">${items.length}</span>
            <button class="ll-rg-add" data-key="${_he(grp.key)}" title="添加${_he(grp.name)}"${canEditCurrentLine ? '' : ' disabled style="opacity:.45;cursor:not-allowed"'}>＋</button>
          </div>
          <div class="ll-rg-items${isOpen ? ' open' : ''}">
            ${items.length ? items.map((item, idx) => {
              const fromOther = item.source_entry_gid && item.source_entry_gid !== gid;
              return `
                <div class="ll-ri" data-key="${_he(grp.key)}" data-idx="${idx}">
                  <span class="lv-nt-dot lv-nt-${_he(item._ntType || 'process')}"></span>
                  <span class="ll-ri-title">${_he(item._title || item.link?.entity_gid || '—')}</span>
                  <span class="ll-ri-badge ${_statusBadgeClass(item._badge)}">${_he(item._badge || '')}</span>
                </div>
                ${fromOther ? `<div class="ll-ri-src" data-src-gid="${_he(item.source_entry_gid)}">来自：${_he(item.source_entry_title || item.source_entry_gid)}</div>` : ''}`;
            }).join('') : `<div class="ll-rg-empty">暂无关联，点击 ＋ 添加</div>`}
          </div>
        </div>`;
    }

    // ── 从本体 schema 加载自定义关系（有 link_type_binding 且 show_in_detail 非 false）──
    let ontoRelTypes = [];
    try {
      const schemaResp = await this._cf(`/api/ontology/schema/${encodeURIComponent(row.node_type)}`);
      ontoRelTypes = (schemaResp?.relations || []).filter(r => r.link_type_binding && r.show_in_detail !== false);
    } catch (_) {}

    // ── 动态关系组：收集未被 REL_GROUPS 覆盖的 link_type ──
    const knownLinkTypes = new Set();
    REL_GROUPS.forEach(g => { if (g.linkTypes) g.linkTypes.forEach(lt => knownLinkTypes.add(lt)); });
    const dynamicLinks = links.filter(l => !knownLinkTypes.has(l.link_type) && l.link_type !== 'child');
    // 补入本体中定义但尚无实际链接的关系（显示空组 + ＋ 按钮）
    ontoRelTypes.forEach(r => {
      if (!knownLinkTypes.has(r.link_type_binding) && !dynamicLinks.some(l => l.link_type === r.link_type_binding)) {
        dynamicLinks.push({ link_type: r.link_type_binding, entity_gid: '', entity_title: '', _placeholder: true });
      }
    });
    if (dynamicLinks.length) {
      const byType = {};
      dynamicLinks.forEach(l => {
        const lt = l.link_type || 'other';
        if (!byType[lt]) byType[lt] = [];
        byType[lt].push(l);
      });
      for (const [lt, ltLinks] of Object.entries(byType)) {
        const items = ltLinks.map(l => ({
          _key: 'link:' + lt, _title: l.entity_title || l.entity_gid, _badge: lt,
          _ntType: 'process', link: l,
          source_entry_gid: l.source_entry_gid || gid,
          source_entry_title: l.source_entry_title,
        }));
        const isPlaceholder = ltLinks.length === 1 && ltLinks[0]._placeholder;
        html += `
          <div class="ll-rg">
            <div class="ll-rg-hdr" data-key="link:${_he(lt)}">
              <span class="ll-rg-tog">▼</span>
              <span class="lv-nt-dot lv-nt-process"></span>
              <span class="ll-rg-name">${_he(lt)}</span>
              <span class="ll-rg-cnt">${isPlaceholder ? 0 : items.length}</span>
              <button class="ll-rg-add" data-key="link:${_he(lt)}" title="添加${_he(lt)}"${canEditCurrentLine ? '' : ' disabled style="opacity:.45;cursor:not-allowed"'}>＋</button>
            </div>
            <div class="ll-rg-items open">
              ${isPlaceholder
                ? '<div class="ll-rg-empty">暂无关联，点击 ＋ 添加</div>'
                : items.map((item, idx) => `
                <div class="ll-ri" data-key="link:${_he(lt)}" data-idx="${idx}">
                  <span class="lv-nt-dot lv-nt-${_he(item._ntType || 'process')}"></span>
                  <span class="ll-ri-title">${_he(item._title || item.link?.entity_gid || '—')}</span>
                  <span class="ll-ri-badge">${_he(item._badge || '')}</span>
                </div>`).join('')}
            </div>
          </div>`;
      }
    }

    mountEl.innerHTML = html;

    // 分组折叠
    mountEl.querySelectorAll('.ll-rg-hdr').forEach(hdr => {
      hdr.addEventListener('click', e => {
        if (e.target.classList.contains('ll-rg-add')) return;
        const wrap = hdr.nextElementSibling;
        const open = wrap.classList.contains('open');
        wrap.classList.toggle('open', !open);
        hdr.querySelector('.ll-rg-tog').textContent = !open ? '▼' : '▶';
      });
    });

    // 关系行点击 → 详情面板
    mountEl.querySelectorAll('.ll-ri').forEach(ri => {
      ri.addEventListener('click', () => {
        mountEl.querySelectorAll('.ll-ri').forEach(r => r.classList.remove('sel'));
        ri.classList.add('sel');
        const key = ri.dataset.key;
        const idx = parseInt(ri.dataset.idx);
        const grp = REL_GROUPS.find(g => g.key === key);

        if (key === 'child') {
          const childItems = childRows.map(r => ({
            _key: 'child', _title: r.title || r.gid, _row: r,
            source_entry_gid: gid, source_entry_title: null, link: { link_type: 'child', entity_gid: r.gid },
          }));
          this._openViewDetail(childItems[idx], gid);
        } else if (grp) {
          const grpLinks = links.filter(l => grp.linkTypes.includes(l.link_type))
            .map(l => ({ _key: key, _title: l.entity_title || l.entity_gid, link: l,
              source_entry_gid: l.source_entry_gid || gid, source_entry_title: l.source_entry_title }));
          this._openViewDetail(grpLinks[idx], gid);
        } else if (key.startsWith('link:')) {
          // 动态关系（本体自定义 link_type）
          const linkType = key.slice(5);
          const dynLinks = links.filter(l => l.link_type === linkType)
            .map(l => ({ _key: key, _title: l.entity_title || l.entity_gid, link: l,
              source_entry_gid: l.source_entry_gid || gid, source_entry_title: l.source_entry_title }));
          if (dynLinks[idx]) this._openViewDetail(dynLinks[idx], gid);
        }
      });
    });

    // 来源行点击 → 跳转子节点
    this._relsBody.querySelectorAll('.ll-ri-src').forEach(src => {
      src.addEventListener('click', () => {
        const srcGid = src.dataset.srcGid;
        if (srcGid) this.open(srcGid);
      });
    });

    // ＋ 按钮 → 添加模式
    this._relsBody.querySelectorAll('.ll-rg-add').forEach(btn => {
      btn.addEventListener('click', e => {
        e.stopPropagation();
        if (!canEditCurrentLine) {
          this._toast?.('当前线体无编辑权限（只读）', 'warn');
          return;
        }
        const key = btn.dataset.key;
        const grp = REL_GROUPS.find(g => g.key === key);
        if (grp) {
          const row = this._currentRow;
          if (key === 'child') {
            const childInfo = CHILD_TYPE_MAP[row?.node_type || null];
            this._openAddDetail(key, gid, childInfo?.type, childInfo?.label || '子节点');
          } else {
            this._openAddDetail(key, gid, grp.linkTypes?.[0], grp.name);
          }
        } else if (key.startsWith('link:')) {
          // 本体自定义关系：link_type = key 去掉 "link:" 前缀
          this._openAddDetail(key, gid, key.slice(5), key.slice(5));
        }
      });
    });
  }

  // ── 列3：详情面板 ─────────────────────────────────────────────────────────

  _renderDetailEmpty() {
    this._closeDetDrawer();
    this._detMode = 'empty';
    this._addType = null;
  }

  async _openViewDetail(item, currentGid) {
    this._selectedRel = item;
    this._detMode = 'view';

    const fromOther = item.source_entry_gid && item.source_entry_gid !== currentGid;
    const linkType  = item.link?.link_type;
    const entityGid = item.link?.entity_gid;
    const grp       = REL_GROUPS.find(g => g._key === item._key || g.key === item._key);

    // 加载实体字段值
    let entityData = {};
    if (linkType && linkType !== 'child' && entityGid) {
      try {
        const resp = await this._cf(`/api/bop/entity-detail?link_type=${encodeURIComponent(linkType)}&ref_gid=${encodeURIComponent(entityGid)}`);
        entityData = resp?.data || {};
      } catch {}
    } else if (linkType === 'child' && entityGid) {
      // 子节点 → 从 lineage data 读
      const data = this._getLineageData();
      const row = data?.rowByGid.get(entityGid);
      if (row) entityData = { title: row.title, node_type: row.node_type, vpps: row.vpps, ...row.meta };
    }

    const fieldCfg = DETAIL_FIELDS[linkType] || [];
    const data = this._getLineageData();
    const lineGrantSet = data?.lineGrantSet || new Set();
    const lineReadOnly = !!data?.lineReadOnly;
    const currentLineGid = this._findAncestorOfType(currentGid, 'line_process', data?.rowByGid) || (data?.rowByGid?.get(currentGid)?.node_type === 'line_process' ? currentGid : null);
    const canEditCurrentLine = !lineReadOnly || !currentLineGid || lineGrantSet.has(currentLineGid);
    let fieldsHtml = '';
    if (fieldCfg.length) {
      for (const f of fieldCfg) {
        if (f.sec !== undefined) {
          fieldsHtml += `<div class="ll-det-sec">${_he(f.sec)}</div>`;
          continue;
        }
        const val = entityData[f.f] ?? '';
        let inputHtml = '';
        if (f.t === 'select' && f.opts) {
          const opts = f.opts.split(',').map(v => `<option value="${_he(v)}"${String(val) === v ? ' selected' : ''}>${_he(v)}</option>`).join('');
          inputHtml = `<select class="ll-df-sel" data-field="${_he(f.f)}">${opts}</select>`;
        } else if (f.t === 'textarea') {
          inputHtml = `<textarea class="ll-df-ta" data-field="${_he(f.f)}" rows="3">${_he(val)}</textarea>`;
        } else {
          inputHtml = `<input class="ll-df-inp" data-field="${_he(f.f)}" type="${_he(f.t || 'text')}" value="${_he(val)}">`;
        }
        fieldsHtml += `<div class="ll-df"><span class="ll-df-k">${_he(f.k)}</span><div class="ll-df-v">${inputHtml}</div></div>`;
      }
    } else if (linkType === 'child') {
      // 子节点用本体属性
      fieldsHtml = '<div style="color:var(--surface2);font-size:11px;padding:4px">点击保存后可在属性列编辑本体属性</div>';
    } else {
      fieldsHtml = `<div style="padding:8px;font-size:11px;color:var(--surface2)">暂无可编辑字段</div>`;
    }

    const badgeBg = { child: 'rgba(116,199,236,.12)', issue: 'rgba(243,139,168,.12)', task_std: 'rgba(137,180,250,.1)', task_custom: 'rgba(137,180,250,.1)', pbom_part: 'rgba(137,220,235,.12)' };
    const badgeFg = { child: 'var(--sapphire)', issue: 'var(--red)', task_std: 'var(--blue)', task_custom: 'var(--blue)', pbom_part: 'var(--teal)' };
    const bg = grp ? '' : (badgeBg[linkType] || 'rgba(108,112,134,.12)');
    const fg = grp ? '' : (badgeFg[linkType] || 'var(--subtext0)');
    const typeName = grp ? grp.name : (linkType || '实体');

    this._detDrawerBody.innerHTML = `
      <div class="ll-det-view" style="display:flex;flex-direction:column;height:100%">
        <div class="ll-det-hdr">
          <div class="ll-det-type-row">
            <span class="ll-det-type-badge" style="background:${_he(bg)};color:${_he(fg)}">${_he(typeName)}</span>
            <input class="ll-det-title-inp" id="llDetTitleInp" value="${_he(item._title || entityData.title || '')}">
            <button class="ll-dp-hdr-btn" id="llDetClose">✕</button>
          </div>
          ${fromOther ? `<div class="ll-det-source-tag">来自节点：<a id="llDetSrcLink" data-gid="${_he(item.source_entry_gid)}">${_he(item.source_entry_title || item.source_entry_gid)}</a></div>` : ''}
        </div>
        <div class="ll-det-fields">${fieldsHtml}</div>
        <div class="ll-det-actions">
          ${linkType !== 'child' ? `<button class="ll-det-btn ll-det-btn-danger" id="llDetUnlink"${canEditCurrentLine ? '' : ' disabled style="opacity:.45;cursor:not-allowed"'}>解除关联</button>` : ''}
          <button class="ll-det-btn ll-det-btn-ghost" id="llDetCancel">取消</button>
          <button class="ll-det-btn ll-det-btn-primary" id="llDetSave"${canEditCurrentLine ? '' : ' disabled style="opacity:.45;cursor:not-allowed"'}>保存</button>
        </div>
      </div>`;

    this._openDetDrawer();

    // 关闭

    // 来源跳转
    this._detDrawerBody.querySelector('#llDetSrcLink')?.addEventListener('click', e => {
      const srcGid = e.target.dataset.gid;
      if (srcGid) this.open(srcGid);
    });

    // 保存
    this._detDrawerBody.querySelector('#llDetSave')?.addEventListener('click', async () => {
      if (!canEditCurrentLine) {
        this._toast?.('当前线体无编辑权限（只读）', 'warn');
        return;
      }
      const fields = {};
      this._detDrawerBody.querySelectorAll('[data-field]').forEach(el => {
        fields[el.dataset.field] = el.value || null;
      });
      try {
        if (linkType !== 'child') {
          await this._cf('/api/bop/entity-detail', {
            method: 'PATCH',
            body: JSON.stringify({ link_type: linkType, ref_gid: entityGid, fields }),
          });
        } else if (entityGid) {
          const newTitle = this._detDrawerBody.querySelector('#llDetTitleInp')?.value?.trim();
          if (newTitle) {
            await this._patchEntry(entityGid, { title: newTitle });
            const data = this._getLineageData();
            const r = data?.rowByGid.get(entityGid);
            if (r) r.title = newTitle;
          }
        }
        this._toast?.('已保存', 'ok', 1200);
        await this._renderRels(this._currentGid);
      } catch (e) {
        this._toast?.('保存失败: ' + (e?.message || e), 'error');
      }
    });

    // 解除关联
    this._detDrawerBody.querySelector('#llDetUnlink')?.addEventListener('click', async () => {
      if (!canEditCurrentLine) {
        this._toast?.('当前线体无编辑权限（只读）', 'warn');
        return;
      }
      if (!item.link?.gid) return;
      try {
        await this._cf(`/api/bop/entry-links/${encodeURIComponent(item.link.gid)}`, { method: 'DELETE' });
        this._renderDetailEmpty();
        await this._renderRels(this._currentGid);
      } catch (e) {
        this._toast?.('解除失败: ' + (e?.message || e), 'error');
      }
    });
  }

  async _openAddDetail(key, parentGid, nodeType, typeLabel) {
    this._detMode = 'add';
    this._addType = key;

    const grp = REL_GROUPS.find(g => g.key === key);
    const dot = grp?.dot || '#89b4fa';

    const isResourceGroup = key === 'equip' || key === 'tool' || key === 'fixture' || [
      'physical_equipment', 'project_equipment', 'needsEquipment',
      'physical_tool', 'project_tools', 'needsTool',
      'physical_fixture', 'project_tooling', 'needsFixture',
    ].includes(nodeType || '');
    let selLinkType = nodeType || '';

    // 加载候选：按关系类型走对应数据源
    let candidates = [];
    let candSrcLabel = 'GBOP';
    const verInfo = this._getVersionInfo ? this._getVersionInfo() : null;
    const _nt = nodeType || '';

    // ── PBOM 版本选择（仅 pbom 类型） ──
    let pbomVersions = [];
    let selectedPbomGid = null;
    let isPbomType = key === 'pbom' || ['pbom_part', 'usesPart', 'part', 'non_standard_part', 'standard_part', 'support_material'].includes(_nt);

    try {
      if (isPbomType) {
        // 加载 PBOM 版本列表
        const verResp = await this._cf('/api/ebom/snapshots?limit=50');
        pbomVersions = verResp?.data || (Array.isArray(verResp) ? verResp : []);
        selectedPbomGid = verInfo?.pbomVersionGid || pbomVersions[0]?.gid || null;
        candSrcLabel = 'PBOM';
        // 加载默认版本下的零件
        if (selectedPbomGid) {
          const partResp = await this._cf(`/api/ebom/snapshots/${selectedPbomGid}/parts`);
          const parts = partResp?.data || [];
          candidates = parts.map(r => ({
            gid: r.gid,
            title: r.part_no || r.name || r.gid,
            part_no: r.part_no || '',
            name: r.name || '',
            vpps: r.vpps || '',
            component_id: r.component_id || '',
            component_type: r.component_type || '',
            quantity: r.quantity || 1,
            unit: r.unit || 'pcs',
          }));
        }
      } else if (key === 'equip' || ['physical_equipment', 'project_equipment', 'needsEquipment'].includes(_nt)) {
        const fgid = verInfo?.factoryGid;
        const url = fgid ? `/api/bop/factory/equipments?factory_gid=${encodeURIComponent(fgid)}&limit=20` : `/api/bop/factory/equipments?limit=20`;
        const resp = await this._cf(url); candidates = resp?.data || []; candSrcLabel = '设备库';
      } else if (key === 'tool' || ['physical_tool', 'project_tools', 'needsTool'].includes(_nt)) {
        const resp = await this._cf(`/api/bop/factory/tools?limit=20`);
        candidates = resp?.data || []; candSrcLabel = '工具库';
      } else if (key === 'fixture' || ['physical_fixture', 'project_tooling', 'needsFixture'].includes(_nt)) {
        const resp = await this._cf(`/api/bop/factory/fixtures?limit=20`);
        candidates = resp?.data || []; candSrcLabel = '工装库';
      } else if (key === 'issue' || _nt === 'issue') {
        const pgid = verInfo?.projectGid;
        const resp = await this._cf(pgid ? `/api/issues?project_gid=${encodeURIComponent(pgid)}&page_size=20` : `/api/issues?page_size=20`);
        candidates = (resp?.data || []).map(r => ({ gid: r.gid, title: r.title })); candSrcLabel = '问题清单';
      } else if (key === 'task' || ['task_std', 'task_custom'].includes(_nt)) {
        const pgid = verInfo?.projectGid;
        const resp = await this._cf(pgid ? `/api/tasks?project_gid=${encodeURIComponent(pgid)}&page_size=20` : `/api/tasks?page_size=20`);
        candidates = (resp?.data || []).map(r => ({ gid: r.gid, title: r.title })); candSrcLabel = '任务清单';
      } else if (['knowledge', 'rule_std', 'rule_custom'].includes(_nt)) {
        const resp = await this._cf(`/api/knowledge_entries?limit=20`);
        candidates = (resp?.data || []).map(r => ({ gid: r.gid, title: r.title })); candSrcLabel = '知识库';
      } else {
        const searchType = _nt || 'process';
        const resp = await this._cf(`/api/gbop/entries?node_type=${encodeURIComponent(searchType)}&limit=10`);
        candidates = resp?.data || []; candSrcLabel = 'GBOP';
      }
    } catch (e) { console.warn('[DetailPanel] 加载候选失败:', e); }

    // ── 候选列表 HTML ──
    const _buildCandList = () => {
      let html;
      if (candidates.length > 0) {
        html = candidates.map(c => `
          <div class="ll-det-sr-item" data-gid="${_he(c.gid)}"
               data-title="${_he(c.title || c.name || '')}"
               data-part_no="${_he(c.part_no || '')}"
               data-name="${_he(c.name || '')}"
               data-vpps="${_he(c.vpps || '')}"
               data-component_id="${_he(c.component_id || '')}">
            <span class="lv-nt-dot lv-nt-${_he(grp?.ntType || 'part')}"></span>
            <div class="ll-det-sr-info">
              <span class="ll-det-sr-name">${_he(c.part_no || c.title || c.name || c.gid)}</span>
              ${c.name ? `<span class="ll-det-sr-sub">${_he(c.name)}</span>` : ''}
            </div>
            ${c.vpps ? `<span class="ll-det-sr-tag">${_he(c.vpps)}</span>` : ''}
            <span class="ll-det-sr-src">${_he(candSrcLabel)}</span>
          </div>`).join('');
      } else {
        html = `<div style="color:var(--surface2);font-size:11px;padding:8px 10px">暂无数据</div>`;
      }
      return html;
    };

    // ── PBOM 版本选择器 HTML ──
    const verSelHtml = isPbomType && pbomVersions.length > 0 ? `
      <div class="ll-det-ver-sel" style="padding:0 0 8px">
        <label style="font-size:11px;color:var(--surface2);display:flex;align-items:center;gap:6px">
          PBOM 版本
          <select id="llPbomVerSel" style="flex:1;background:var(--base,#1e1e2e);color:var(--text,#cdd6f4);
            border:1px solid var(--surface1,#45475a);border-radius:4px;padding:3px 6px;font-size:11px;max-width:100%">
            ${pbomVersions.map(v => `<option value="${_he(v.gid)}" ${v.gid === selectedPbomGid ? 'selected' : ''}>${_he(v.name || v.version_tag || v.gid)}</option>`).join('')}
          </select>
        </label>
      </div>` : '';

    const candHtml = _buildCandList();

    this._detDrawerBody.innerHTML = `
      <div class="ll-det-add" style="display:flex;flex-direction:column;height:100%">
        <div class="ll-det-add-hdr">
          <div class="ll-det-add-type-row">
            <span class="ll-det-type-badge" style="background:rgba(137,180,250,.1);color:var(--blue)">添加${_he(typeLabel)}</span>
            <button class="ll-dp-hdr-btn" id="llAddClose" style="margin-left:auto">✕</button>
          </div>
          ${verSelHtml}
          ${isResourceGroup ? `
          <div style="display:flex;align-items:center;gap:6px;padding:0 0 6px">
            <span style="font-size:10px;color:var(--subtext0,#a6adc8)">类型</span>
            <select id="llAddLinkTypeSel" style="flex:1;background:var(--base,#1e1e2e);color:var(--text,#cdd6f4);
              border:1px solid var(--surface1,#45475a);border-radius:4px;padding:3px 6px;font-size:11px">
              ${(grp?.linkTypes || []).map(lt => {
                const labels = { physical_equipment:'实物设备', project_equipment:'需求设备',
                  physical_tool:'实物工具', project_tools:'需求工具',
                  physical_fixture:'实物工装', project_tooling:'需求工装' };
                return `<option value="${_he(lt)}"${lt === (selLinkType || grp.linkTypes[0]) ? ' selected' : ''}>${_he(labels[lt] || lt)}</option>`;
              }).join('')}
            </select>
          </div>` : ''}
          <div class="ll-det-search">
            <span style="font-size:11px;color:var(--overlay1)">⌕</span>
            <input id="llAddSearchInp" placeholder="搜索零件号 / 名称 / VPPS…">
          </div>
        </div>
        <div class="ll-det-sr-results" id="llAddCands">
          ${candHtml}
        </div>
        <div class="ll-det-actions">
          <button class="ll-det-btn ll-det-btn-ghost" id="llAddCancel">取消</button>
          <button class="ll-det-btn ll-det-btn-primary" id="llAddConfirm">确认关联</button>
        </div>
      </div>`;

    this._openDetDrawer();

    // 关闭/取消

    // ── PBOM 版本切换 → 重新加载零件 ──
    const verSel = this._detDrawerBody.querySelector('#llPbomVerSel');
    if (verSel) {
      verSel.addEventListener('change', async () => {
        const newGid = verSel.value;
        if (!newGid) return;
        selectedPbomGid = newGid;
        const candsEl = this._detDrawerBody.querySelector('#llAddCands');
        candsEl.innerHTML = '<div style="color:var(--surface2);font-size:11px;padding:8px 10px">加载中…</div>';
        try {
          const partResp = await this._cf(`/api/ebom/snapshots/${newGid}/parts`);
          const parts = partResp?.data || [];
          candidates = parts.map(r => ({
            gid: r.gid,
            title: r.part_no || r.name || r.gid,
            part_no: r.part_no || '',
            name: r.name || '',
            vpps: r.vpps || '',
            component_id: r.component_id || '',
            component_type: r.component_type || '',
            quantity: r.quantity || 1,
            unit: r.unit || 'pcs',
          }));
          candsEl.innerHTML = _buildCandList();
          // 重新绑定点击事件
          _bindCandClicks();
        } catch (e) {
          candsEl.innerHTML = '<div style="color:#f38ba8;font-size:11px;padding:8px 10px">加载失败</div>';
        }
      });
    }

    // ── 类型切换（实物/需求）──
    const typeSel = this._detDrawerBody.querySelector('#llAddLinkTypeSel');
    typeSel?.addEventListener('change', () => {
      selLinkType = typeSel.value;
    });

    // ── 搜索（客户端过滤，按零件号/名称/VPPS/组件ID） ──
    const searchInp = this._detDrawerBody.querySelector('#llAddSearchInp');
    searchInp?.addEventListener('input', () => {
      const q = searchInp.value.trim().toLowerCase();
      this._detDrawerBody.querySelectorAll('.ll-det-sr-item').forEach(item => {
        const fields = [
          item.dataset.title || '',
          item.dataset.part_no || '',
          item.dataset.name || '',
          item.dataset.vpps || '',
          item.dataset.component_id || '',
        ];
        item.style.display = (!q || fields.some(f => f.toLowerCase().includes(q))) ? '' : 'none';
      });
    });
    searchInp?.focus();

    // ── 选择候选 ──
    const _bindCandClicks = () => {
      this._detDrawerBody.querySelectorAll('.ll-det-sr-item').forEach(item => {
        item.addEventListener('click', () => {
          this._detDrawerBody.querySelectorAll('.ll-det-sr-item').forEach(i => i.classList.remove('sel'));
          item.classList.add('sel');
        });
      });
    };
    _bindCandClicks();

    // ── 确认添加 ──
    this._detDrawerBody.querySelector('#llAddConfirm')?.addEventListener('click', async () => {
      const sel = this._detDrawerBody.querySelector('.ll-det-sr-item.sel');
      if (!sel) { this._toast?.('请先选择一个候选零件', 'warn'); return; }
      const entityGid = sel.dataset.gid;

      const data = this._getLineageData();
      const versionGid = data?.versionGid;
      if (!versionGid) { this._toast?.('无法获取版本信息', 'error'); return; }

      try {
        if (key === 'child') {
          // 创建子节点
          const title = sel.dataset.title;
          const childCount = (data.childMap.get(parentGid) || []).length;
          await this._cf('/api/bop/entries', {
            method: 'POST',
            body: JSON.stringify({
              version_gid: versionGid,
              parent_gid: parentGid,
              node_type: nodeType,
              title,
              seq_no: (childCount + 1) * 10,
            }),
          });
          await this._reloadData();
          const newData = this._getLineageData();
          const children = newData?.childMap.get(parentGid) || [];
          const newChild = children.find(r => r.title === title);
          if (newChild) this.open(newChild.gid);
          else this.refresh();
          this._toast?.('已添加', 'ok', 1200);
        } else if (isPbomType) {
          // 创建 PBOM 零件关联
          await this._cf('/api/bop/entry-links', {
            method: 'POST',
            body: JSON.stringify({
              entry_gid: parentGid,
              link_type: 'pbom_part',
              entity_gid: entityGid,
              is_primary: true,
            }),
          });
          await this._reloadData();
          this.refresh();
          this._toast?.('已关联 PBOM 零件', 'ok', 1200);
        } else if (key === 'issue' || key === 'task') {
          this._toast?.('关联已有实体请从右侧关联面板选择', 'info');
          return;
        } else if (key === 'equip' || key === 'tool' || key === 'fixture' || isResourceGroup) {
          // 创建实物/需求关联（nodeType 已在 type 选择器中确定）
          const linkType = selLinkType || nodeType || '';
          await this._cf('/api/bop/entry-links', {
            method: 'POST',
            body: JSON.stringify({
              entry_gid: parentGid,
              link_type: linkType,
              entity_gid: entityGid,
              is_primary: false,
            }),
          });
          await this._reloadData();
          this.refresh();
          this._closeDetDrawer();
          this._toast?.('已关联', 'ok', 1200);
        } else if (key.startsWith('link:')) {
          // 本体自定义关系：从 schema 解析真实 link_type_binding
          const relName = key.slice(5);
          let linkType = relName;
          try {
            const schema = await this._cf(`/api/ontology/schema/${encodeURIComponent(nodeType)}`);
            const rel = (schema?.relations || []).find(r => r.name === relName);
            if (rel?.link_type_binding) linkType = rel.link_type_binding;
          } catch {}
          await this._cf('/api/bop/entry-links', {
            method: 'POST',
            body: JSON.stringify({
              entry_gid: parentGid,
              link_type: linkType,
              entity_gid: entityGid,
              is_primary: false,
            }),
          });
          await this._reloadData();
          this.refresh();
          this._toast?.('已关联', 'ok', 1200);
        } else {
          // 默认：创建 entry_link
          await this._cf('/api/bop/entry-links', {
            method: 'POST',
            body: JSON.stringify({
              entry_gid: parentGid,
              link_type: typeLabel,
              entity_gid: entityGid,
              is_primary: false,
            }),
          });
          await this._reloadData();
          this.refresh();
          this._toast?.('已关联', 'ok', 1200);
        }
      } catch (e) {
        this._toast?.('添加失败: ' + (e?.message || e), 'error');
      }
    });
  }

  // ── 列4：规则 ─────────────────────────────────────────────────────────────

  async _renderRules(gid, row) {
    if (!this._rulesBody) return;
    this._rulesBody.innerHTML = '<div style="color:var(--surface2);font-size:11px;padding:4px">加载中…</div>';
    if (!row?.node_type) { this._rulesBody.innerHTML = ''; return; }
    try {
      const schema = await this._cf(`/api/ontology/schema/${encodeURIComponent(row.node_type)}`);
      const rules = schema?.rules || [];
      if (!rules.length) {
        this._rulesBody.innerHTML = '<div style="color:var(--surface2);font-size:11px;padding:4px">暂无规则</div>';
        return;
      }
      // 运行规则检查
      let violations = [];
      try {
        const chk = await this._cf(`/api/rule-engine/check-entry?entry_gid=${encodeURIComponent(gid)}`);
        violations = chk?.data || [];
      } catch {}

      const violMap = new Map(violations.map(v => [v.rule_gid, v]));
      let html = '';
      for (const rule of rules) {
        const viol = violMap.get(rule.gid);
        const cls = viol ? (viol.result === 'fail' ? 'll-rule-fail' : 'll-rule-warn') : 'll-rule-pass';
        const ico = viol ? (viol.result === 'fail' ? '✗' : '⚠') : '✓';
        const lv  = rule.enforcement_level === 'mandatory' ? 'll-rule-lv-m' : 'll-rule-lv-a';
        const lvLabel = rule.enforcement_level === 'mandatory' ? '必须' : '建议';
        html += `
          <div class="ll-rule ${cls}">
            <div class="ll-rule-hdr">
              <span style="font-size:11px">${ico}</span>
              <span class="ll-rule-lv ${lv}">${lvLabel}</span>
              <span class="ll-rule-name">${_he(rule.name)}</span>
            </div>
            ${viol ? `<div class="ll-rule-msg">${_he(viol.message || '')}</div>` : ''}
          </div>`;
      }
      this._rulesBody.innerHTML = html;
    } catch {
      this._rulesBody.innerHTML = '<div style="color:var(--surface2);font-size:11px;padding:4px">规则加载失败</div>';
    }
  }

  // ── 列5：知识 ─────────────────────────────────────────────────────────────

  async _renderKnowledge(gid) {
    this._knowBody.innerHTML = '';
    try {
      const resp = await this._cf(
        `/api/bop/entry-links?entry_gid=${encodeURIComponent(gid)}`
      );
      const knowLinks = (resp?.data || []).filter(l => l.link_type === 'knowledge' || l.link_type === 'rule_std' || l.link_type === 'rule_custom');
      if (!knowLinks.length) {
        this._knowBody.innerHTML = '<div style="color:var(--surface2);font-size:11px;padding:4px">暂无关联知识</div>';
      } else {
        let html = '';
        for (const l of knowLinks) {
          const title = l.entity_title || l.entity_gid;
          const typeLabel = l.link_type === 'knowledge' ? '知识' : '规则';
          html += `
            <div class="ll-kn" data-link-gid="${_he(l.gid)}">
              <div class="ll-kn-top">
                <span class="ll-kn-dot"></span>
                <span class="ll-kn-title">${_he(title)}</span>
                <span class="ll-kn-type">${typeLabel}</span>
              </div>
            </div>`;
        }
        this._knowBody.innerHTML = html;
      }
    } catch {
      this._knowBody.innerHTML = '<div style="color:var(--surface2);font-size:11px;padding:4px">知识加载失败</div>';
    }

    this._knowAddBtn?.addEventListener('click', () => {
      this._toast?.('请从知识管理页搜索并关联', 'info');
    });
  }

  // ── 列宽 resize ───────────────────────────────────────────────────────────

  _initColumnResizers() {
    const el = this._el;
    el.querySelectorAll('.ll-dp-col-divider').forEach(divider => {
      const leftId = divider.dataset.left;
      if (!leftId) return;
      const leftCol = el.querySelector('#' + leftId);
      if (!leftCol) return;
      let startX, startW;
      divider.addEventListener('mousedown', e => {
        startX = e.clientX;
        startW = leftCol.offsetWidth;
        divider.classList.add('dragging');
        const onMove = ev => {
          const newW = Math.max(60, startW + ev.clientX - startX);
          leftCol.style.width = newW + 'px';
        };
        const onUp = () => {
          divider.classList.remove('dragging');
          this._saveWidths();
          document.removeEventListener('mousemove', onMove);
          document.removeEventListener('mouseup', onUp);
        };
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
        e.preventDefault();
      });
    });
  }

  _saveWidths() {
    const ids = ['llDpTree', 'llDpProps'];
    const w = {};
    ids.forEach(id => {
      const el = document.getElementById(id);
      if (el) w[id] = el.offsetWidth;
    });
    try { localStorage.setItem(_ldpLsk('lv:dpColWidths'), JSON.stringify(w)); } catch {}
  }

  _restoreWidths() {
    try {
      const saved = JSON.parse(localStorage.getItem(_ldpLsk('lv:dpColWidths')) || '{}');
      Object.entries(saved).forEach(([id, w]) => {
        const el = document.getElementById(id);
        if (el && w > 60) el.style.width = w + 'px';
      });
    } catch {}
  }

  // ── 垂直高度 resize ───────────────────────────────────────────────────────

  _bindResizeHandle() {
    if (!this._resizeHandle) return;
    const saved = localStorage.getItem(_ldpLsk('lv:dpHeight'));
    if (saved) this._el.style.setProperty('--ll-dp-height', saved + 'px');

    let startY, startH;
    this._resizeHandle.addEventListener('mousedown', e => {
      startY = e.clientY;
      startH = this._el.offsetHeight;
      const onMove = ev => {
        const newH = Math.max(180, startH - (ev.clientY - startY));
        this._el.style.setProperty('--ll-dp-height', newH + 'px');
      };
      const onUp = () => {
        const h = parseInt(getComputedStyle(this._el).getPropertyValue('--ll-dp-height'));
        if (h) try { localStorage.setItem(_ldpLsk('lv:dpHeight'), String(h)); } catch {}
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
      };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
      e.preventDefault();
    });
  }

  /** 首次创建版本 picker（body 级，fixed 定位，避免被 overflow:hidden 截断） */
  _buildVerPicker(versions, verInfo) {
    // 清除旧的 picker（防止重复）
    document.getElementById('llTreeVerPickerBody')?.remove();

    const picker = document.createElement('div');
    picker.id = 'llTreeVerPickerBody';
    picker.className = 'll-tree-ver-picker';
    picker.style.display = 'none';
    picker.innerHTML = `
      <div class="ll-tvp-toolbar">
        <div class="ll-tvp-search-wrap">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="flex-shrink:0;opacity:.5">
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <input class="ll-tvp-search-inp" id="llTreeVerSearchInp" placeholder="搜索版本…">
        </div>
        <button class="ll-tvp-arc-btn" id="llTreeVerArcBtn" title="显示已归档">
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5"/>
          </svg>
        </button>
      </div>
      <div class="ll-tvp-list" id="llTreeVerListBody"></div>`;
    document.body.appendChild(picker);

    let showArchived = false;
    let curVerGid = verInfo?.currentGid || '';

    const renderList = (q = '') => {
      const list = picker.querySelector('#llTreeVerListBody');
      if (!list) return;
      list.innerHTML = '';
      const lq = q.trim().toLowerCase();
      // 按 bop_name 分组
      const gmap = new Map();
      versions.forEach(v => {
        const key = v.name?.split(' · ')[0] || '未命名';
        if (!gmap.has(key)) gmap.set(key, []);
        gmap.get(key).push(v);
      });
      let hasAny = false;
      for (const [grp, vers] of gmap) {
        const show = vers.filter(v =>
          (showArchived || !v.archived) &&
          (!lq || v.name?.toLowerCase().includes(lq) || grp.toLowerCase().includes(lq))
        );
        if (!show.length) continue;
        hasAny = true;
        const hdr = document.createElement('div');
        hdr.className = 'll-tvp-group-hdr';
        hdr.textContent = grp;
        list.appendChild(hdr);
        show.forEach(v => {
          const tag = v.name?.split(' · ').slice(1).join(' · ') || v.gid?.slice(-6) || '';
          const item = document.createElement('div');
          item.className = 'll-tvp-item' + (v.gid === curVerGid ? ' active' : '');
          item.dataset.verGid = v.gid;
          item.innerHTML = `
            <span class="ll-tvp-dot ll-ver-${_he(v.status || 'active')}"></span>
            <span class="ll-tvp-tag">${_he(tag)}</span>
            <span class="ll-tvp-status">${_he(v.status || 'active')}</span>`;
          item.addEventListener('click', e => {
            e.stopPropagation();
            picker.style.display = 'none';
            curVerGid = v.gid;
            // 同步主工具栏
            if (this._onVersionChange) this._onVersionChange(v.gid);
          });
          list.appendChild(item);
        });
      }
      if (!hasAny) {
        const empty = document.createElement('div');
        empty.className = 'll-tvp-empty';
        empty.textContent = lq ? '无匹配' : '暂无版本';
        list.appendChild(empty);
      }
    };

    // 归档开关
    picker.querySelector('#llTreeVerArcBtn')?.addEventListener('click', e => {
      e.stopPropagation();
      showArchived = !showArchived;
      picker.querySelector('#llTreeVerArcBtn').classList.toggle('active', showArchived);
      renderList(picker.querySelector('#llTreeVerSearchInp')?.value || '');
    });

    // 搜索
    picker.querySelector('#llTreeVerSearchInp')?.addEventListener('input', e => {
      e.stopPropagation();
      renderList(e.target.value);
    });
    picker.querySelector('#llTreeVerSearchInp')?.addEventListener('click', e => e.stopPropagation());

    // 点击外部关闭
    document.addEventListener('click', e => {
      if (picker.style.display === 'none') return;
      const bar = document.getElementById('llTreeVerBar');
      if (!bar?.contains(e.target) && !picker.contains(e.target)) {
        picker.style.display = 'none';
      }
    });

    // 槽位按钮点击展开/收起
    const verBar = document.getElementById('llTreeVerBar');
    verBar?.addEventListener('click', e => {
      e.stopPropagation();
      const isOpen = picker.style.display !== 'none';
      if (isOpen) {
        picker.style.display = 'none';
      } else {
        const rect = verBar.getBoundingClientRect();
        picker.style.position = 'fixed';
        picker.style.top  = (rect.bottom + 2) + 'px';
        picker.style.left = rect.left + 'px';
        picker.style.width = Math.max(rect.width, 240) + 'px';
        picker.style.display = 'block';
        const inp = picker.querySelector('#llTreeVerSearchInp');
        if (inp) { inp.value = ''; renderList(''); setTimeout(() => inp.focus(), 30); }
      }
    });
  }

  /** 当主工具栏切换版本后，同步更新 picker 内的选中高亮 */
  _refreshVerPickerSelection(currentGid) {
    const picker = document.getElementById('llTreeVerPickerBody');
    if (!picker) return;
    picker.querySelectorAll('.ll-tvp-item').forEach(item => {
      item.classList.toggle('active', item.dataset.verGid === currentGid);
    });
  }

    _bindHandleBar() {
    const _toggle = () => {
      if (this._isOpen) {
        this._isOpen = false;
        this._el.classList.remove('open');
        this._toolbarToggle?.classList.remove('active');
      } else {
        this._isOpen = true;
        this._userClosed = false;
        this._el.classList.add('open');
        this._toolbarToggle?.classList.add('active');
        if (this._currentGid) this.refresh();
      }
    };
    this._handleBar?.addEventListener('click', _toggle);
    this._toolbarToggle?.addEventListener('click', _toggle);
  }


  // ── 列0：节点树 ───────────────────────────────────────────────────────────

  _renderEmptyTree() {
    this._treeBody.innerHTML = `
      <div class="ll-tree-empty">
        <div class="ll-tree-empty-hint">这个 BOP 还没有内容</div>
        <button class="ll-tree-empty-btn" id="llDpNewLineBtn">＋ 新建线体</button>
      </div>`;
    this._treeBody.querySelector('#llDpNewLineBtn')?.addEventListener('click', () => {
      this._openAddDetail('child', null, 'line_process', '线体');
    });
  }

  /** 渲染线体下的工位，在工位下按版本分叉展示（station 共用，operator_process 往下版本相关） */
  _renderStationsWithVersions(lineGid, data, extraVers, verInfo, activeGid, activeStationGid, visTypes) {
    if (!visTypes.has('station_process') && !visTypes.has('line_process')) return '';
    let html = '';
    const stations = (data.childMap.get(lineGid) || []).filter(r => !r.is_deleted && visTypes.has(r.node_type));
    for (const sta of stations) {
      const isActiveStation = sta.gid === activeStationGid;
      const staExpanded = this._treeExpanded.has(sta.gid);
      const staChildren = (data.childMap.get(sta.gid) || []).filter(r => !r.is_deleted && visTypes.has(r.node_type));
      const staColor = NODE_TYPE_DOT[sta.node_type] || '#6c7086';
      html += `<div class="${isActiveStation ? 'll-tn-station-wrap' : ''}">`;
      html += `<div class="ll-tn${sta.gid === activeGid ? ' ll-tn-active' : ''}" data-gid="${_he(sta.gid)}" style="padding-left:16px">
        <span class="ll-tn-tog-btn" data-gid="${_he(sta.gid)}" style="font-size:9px;color:var(--overlay1);width:11px;text-align:center;flex-shrink:0;cursor:pointer">
          ${staChildren.length || extraVers.length ? (staExpanded ? '▼' : '▶') : '·'}
        </span>
        <span class="lv-nt-dot lv-nt-${_he(sta.node_type)}"></span>
        <span class="ll-tn-lbl">${_he(sta.title||sta.gid)}</span>
      </div>`;
      if (staExpanded) {
        // 当前版本的工序/工步（过滤掉 operator_process 以上的）
        if (visTypes.has('process') || visTypes.has('operation')) {
          html += this._renderTreeNodesFiltered(sta.gid, data.childMap, data.rowByGid, activeGid, 2, visTypes);
        }
        // 额外版本在工位下按版本分叉（operator_process 往下）
        for (const verGid of extraVers) {
          const extraData = this._extraVersionData.get(verGid);
          if (!extraData) continue;
          const verName = verInfo?.versions?.find(v => v.gid === verGid)?.name || verGid.slice(-6);
          // 找对应工位（按 vpps 匹配，找不到则按 title 匹配）
          let extraSta = sta.vpps
            ? Array.from(extraData.rowByGid.values()).find(r => r.vpps === sta.vpps && r.node_type === 'station_process')
            : null;
          if (!extraSta) extraSta = Array.from(extraData.rowByGid.values()).find(r => r.title === sta.title && r.node_type === 'station_process');
          if (extraSta) {
            const extraStaChildren = (extraData.childMap.get(extraSta.gid) || []).filter(r => !r.is_deleted && visTypes.has(r.node_type));
            if (extraStaChildren.length) {
              html += `<div class="ll-tn-ver-divider"><span>${_he(verName)}</span></div>`;
              html += this._renderTreeNodesFiltered(extraSta.gid, extraData.childMap, extraData.rowByGid, null, 2, visTypes);
            }
          }
        }
      }
      html += `</div>`;
    }
    return html;
  }

  /** 渲染来自额外版本数据的工位子树（纯数据版本，不含版本合并） */
  _renderStationsFromData(lineGid, extraData, activeGid, activeStationGid, visTypes, indent) {
    let html = '';
    const stations = (extraData.childMap.get(lineGid) || []).filter(r => !r.is_deleted && visTypes.has(r.node_type));
    for (const sta of stations) {
      const staExpanded = this._treeExpanded.has(sta.gid);
      const staChildren = (extraData.childMap.get(sta.gid) || []).filter(r => !r.is_deleted && visTypes.has(r.node_type));
      const staColor = NODE_TYPE_DOT[sta.node_type] || '#6c7086';
      html += `<div class="ll-tn${sta.gid === activeGid ? ' ll-tn-active' : ''}" data-gid="${_he(sta.gid)}"
        data-node-type="${_he(sta.node_type)}" data-parent-gid="${_he(lineGid)}"
        style="padding-left:${indent}px">
        <span class="ll-tn-tog-btn" data-gid="${_he(sta.gid)}" style="font-size:9px;color:var(--overlay1);width:11px;text-align:center;flex-shrink:0;cursor:pointer">
          ${staChildren.length ? (staExpanded ? '▼' : '▶') : '·'}
        </span>
        <span class="lv-nt-dot lv-nt-${_he(sta.node_type)}"></span>
        <span class="ll-tn-lbl">${_he(sta.title||sta.gid)}</span>
      </div>`;
      if (staExpanded) {
        html += this._renderTreeNodesFiltered(sta.gid, extraData.childMap, extraData.rowByGid, activeGid, indent / 16 + 1, visTypes);
      }
    }
    return html;
  }

    _renderTreeNodes(parentGid, childMap, rowByGid, activeGid, depth) {
    const children = (childMap.get(parentGid) || []).filter(r => !r.is_deleted);
    if (!children.length) return '';
    let html = '';
    const indent = depth * 16;
    for (const row of children) {
      const hasChildren = (childMap.get(row.gid) || []).filter(r => !r.is_deleted).length > 0;
      const isExpanded = this._treeExpanded.has(row.gid);
      const isActive = row.gid === activeGid;
      const dot = NODE_TYPE_DOT[row.node_type] || '#6c7086';
      const isDraggable = TREE_DRAGGABLE_TYPES.has(row.node_type);
      html += `
        <div class="ll-tn${isActive ? ' ll-tn-active' : ''}" data-gid="${_he(row.gid)}"
          data-node-type="${_he(row.node_type)}" data-parent-gid="${_he(parentGid)}"
          ${isDraggable ? 'data-draggable="1"' : ''}
          style="padding-left:${indent + 4}px">
          <span class="ll-tn-tog-btn" data-gid="${_he(row.gid)}" style="font-size:9px;color:var(--overlay1);width:11px;text-align:center;flex-shrink:0;cursor:pointer">
            ${hasChildren ? (isExpanded ? '▼' : '▶') : '·'}
          </span>
          <span class="lv-nt-dot lv-nt-${_he(row.node_type)}"></span>
          <span class="ll-tn-lbl">${_he(row.title || row.gid)}</span>
        </div>`;
      if (isExpanded) {
        html += this._renderTreeNodes(row.gid, childMap, rowByGid, activeGid, depth + 1);
      }
    }
    return html;
  }

  _renderTreeNodesFiltered(parentGid, childMap, rowByGid, activeGid, depth, visTypes) {
    const children = (childMap.get(parentGid) || []).filter(r => !r.is_deleted && visTypes.has(r.node_type));
    const hasPendingAdd = this._inlineAddPending?.parentGid === parentGid;
    if (!children.length && !hasPendingAdd) return '';
    let html = '';
    const indent = depth * 16;
    const isEditable = this._isEditable();
    for (const row of children) {
      const hasChildren = (childMap.get(row.gid) || []).filter(r => !r.is_deleted && visTypes.has(r.node_type)).length > 0;
      const isExpanded = this._treeExpanded.has(row.gid);
      const isActive = row.gid === activeGid;
      const isDraggable = TREE_DRAGGABLE_TYPES.has(row.node_type);
      const childType = CHILD_TYPE_MAP[row.node_type]?.type;
      html += `
        <div class="ll-tn${isActive ? ' ll-tn-active' : ''}" data-gid="${_he(row.gid)}"
          data-node-type="${_he(row.node_type)}" data-parent-gid="${_he(parentGid)}"
          ${isDraggable ? 'data-draggable="1"' : ''}
          style="padding-left:${indent + 4}px">
          <span class="ll-tn-tog-btn" data-gid="${_he(row.gid)}" style="font-size:9px;color:var(--overlay1);width:11px;text-align:center;flex-shrink:0;cursor:pointer">
            ${hasChildren ? (isExpanded ? '▼' : '▶') : '·'}
          </span>
          <span class="lv-nt-dot lv-nt-${_he(row.node_type)}"></span>
          <span class="ll-tn-lbl">${_he(row.title || row.gid)}</span>
          ${isEditable && childType ? `<span class="ll-tn-add-btn" data-parent-gid="${_he(row.gid)}" data-child-type="${_he(childType)}" title="添加${CHILD_TYPE_MAP[row.node_type]?.label || '子节点'}">+</span>` : ''}
        </div>`;
      if (isExpanded) {
        html += this._renderTreeNodesFiltered(row.gid, childMap, rowByGid, activeGid, depth + 1, visTypes);
      }
    }
    if (hasPendingAdd) {
      html += this._buildInlineAddRow(indent + 4, this._inlineAddPending.childType);
    }
    return html;
  }

  // ── 列1：属性 ─────────────────────────────────────────────────────────────

  _renderProps(gid, row) {
    const data = this._getLineageData();
    const parentRow = row.parent_gid ? data?.rowByGid.get(row.parent_gid) : null;
    const nodeTypeLabel = row.node_type || '';
    const lineGrantSet = data?.lineGrantSet || new Set();
    const lineReadOnly = !!data?.lineReadOnly;
    const currentLineGid = this._findAncestorOfType(gid, 'line_process', data?.rowByGid) || (row.node_type === 'line_process' ? row.gid : null);
    const canEditCurrentLine = !lineReadOnly || !currentLineGid || lineGrantSet.has(currentLineGid);

    let html = `
      <div class="ll-props-node-hdr">
        <div class="ll-props-title-row">
          <span class="ll-props-nt">${_he(nodeTypeLabel)}</span>
          <input class="ll-props-title-inp" id="llPropsTitleInp"
                 value="${_he(row.title || '')}" placeholder="标题…">
        </div>
        <div class="ll-props-parent">
          <span class="ll-props-parent-lbl">父级</span>
          <span class="ll-props-parent-val">${_he(parentRow?.title || '（无）')}</span>
        </div>
      </div>
      ${canEditCurrentLine ? '' : '<div class="ll-props-sec" style="color:var(--yellow,#f9e2af)">当前线体为只读，复制相关操作仍可用</div>'}
      <div class="ll-props-sec">属性</div>
      <div id="llPropsOntoArea"><div style="color:var(--surface2);font-size:11px;padding:8px 4px">加载中…</div></div>
      <div class="ll-props-sec">关系</div>
      <div id="llPropsRelsArea"><div style="color:var(--surface2);font-size:11px;padding:8px 4px">加载中…</div></div>`;

    this._propsBody.innerHTML = html;

    // 标题保存
    const titleInp = this._propsBody.querySelector('#llPropsTitleInp');
    if (!canEditCurrentLine && titleInp) titleInp.disabled = true;
    const saveTitleFn = async () => {
      const newTitle = titleInp.value.trim();
      if (!newTitle || newTitle === row.title) return;
      try {
        await this._patchEntry(gid, { title: newTitle });
        row.title = newTitle;
        this._renderTree(this._currentGid);
        // 同步主视图所有同 gid 的 title 元素
        document.querySelectorAll(`[data-gid="${gid}"] .lv-title, [data-gid="${gid}"] .ll-station-title`)
          .forEach(el => { if (!el.matches('input')) el.textContent = newTitle; });
      } catch (e) {
        this._toast?.('保存失败: ' + (e?.message || e), 'error');
        titleInp.value = row.title || '';
      }
    };
    titleInp?.addEventListener('blur', saveTitleFn);
    titleInp?.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); titleInp.blur(); } });

    // 加载本体属性
    this._loadOntoProps(gid, row);
    this._relsBody = this._propsBody.querySelector('#llPropsRelsArea');
    this._renderRels(gid, this._relsBody);
  }

  async _loadOntoProps(gid, row) {
    const area = this._propsBody.querySelector('#llPropsOntoArea');
    if (!area) return;
    const data = this._getLineageData();
    const lineGrantSet = data?.lineGrantSet || new Set();
    const lineReadOnly = !!data?.lineReadOnly;
    const currentLineGid = this._findAncestorOfType(gid, 'line_process', data?.rowByGid) || (row?.node_type === 'line_process' ? row.gid : null);
    const canEditCurrentLine = !lineReadOnly || !currentLineGid || lineGrantSet.has(currentLineGid);
    try {
      const nodeType = row.node_type;
      const schemaResp = await this._cf(`/api/ontology/schema/${encodeURIComponent(nodeType)}`);
      const props = (schemaResp?.properties || [])
        .filter(p => p.prop_kind === 'data' && Boolean(p.show_in_detail) !== false)
        .sort((a, b) => (a.sort_order ?? 99) - (b.sort_order ?? 99));

      // 收集 show_in_detail=false 的关系 link_type，_renderRels 据此隐藏对应分组
      this._hiddenLinkTypes = new Set(
        (schemaResp?.relations || [])
          .filter(r => r.show_in_detail === false)
          .map(r => r.link_type_binding)
      );

      if (!props.length) { area.innerHTML = '<div style="color:var(--surface2);font-size:11px;padding:4px">暂无本体属性</div>'; return; }

      const entityProps = props.filter(p => p.storage_hint === 'entity_table');
      const metaProps   = props.filter(p => p.storage_hint !== 'entity_table');

      let entityVals = {};
      if (entityProps.length) {
        try {
          const er = await this._cf(`/api/bop/entries/${encodeURIComponent(gid)}/entity-props`);
          entityVals = er?.data || {};
        } catch {}
      }
      const metaVals = (typeof row.meta === 'object' && row.meta) ? row.meta : {};

      // 保持本体 sort_order 顺序，标记来源
      const allProps = props.map(p => ({
        ...p,
        _src: p.storage_hint === 'derived' ? 'derived'
              : p.storage_hint === 'entity_table' ? 'entity'
              : 'meta',
      }));

      // 预计算所有派生属性值
      const derivedVals = {};
      await Promise.all(
        allProps.filter(p => p._src === 'derived').map(async p => {
          derivedVals[p.name] = await this._computeDerivedProp(gid, p);
        })
      );

      let html = '';
      for (const p of allProps) {
        // 派生属性：只读显示 + 公式说明
        if (p._src === 'derived') {
          const dVal = derivedVals[p.name];
          const cfg = typeof p.field_config === 'string' ? JSON.parse(p.field_config) : (p.field_config || {});
          const formula = cfg.expr
            ? cfg.expr
            : `${cfg.aggregate || ''}(${cfg.child_node_type || ''}.${cfg.child_property || ''})`;
          html += `<div class="ll-props-row">
            <span class="ll-props-key" title="${_he(p.description)}">${_he(p.label_zh || p.name)}</span>
            <div class="ll-props-val ll-props-derived-wrap">
              <span class="ll-props-derived-val">${dVal != null ? dVal : '—'}</span>
              <span class="ll-props-derived-badge" title="${_he(formula)}">∑ ${_he(formula)}</span>
            </div>
          </div>`;
          continue;
        }
        // entity_table 属性只从实体表读取，meta 属性从 bop_entries.meta 读取
        const val = p._src === 'entity'
          ? (entityVals[p.name] ?? '')
          : (metaVals[p.name] ?? '');
        const reqClass = p.required ? ' req' : '';
        let inputHtml = '';
        if (p.data_type === 'enum' && p.enum_values?.length) {
          const opts = (typeof p.enum_values === 'string' ? JSON.parse(p.enum_values) : p.enum_values)
            .map(v => `<option value="${_he(v)}"${String(val) === String(v) ? ' selected' : ''}>${_he(v)}</option>`)
            .join('');
          inputHtml = `<select class="ll-props-sel" data-prop="${_he(p.name)}" data-src="${p._src}">${opts}</select>`;
        } else if (p.data_type === 'boolean') {
          inputHtml = `<select class="ll-props-sel" data-prop="${_he(p.name)}" data-src="${p._src}">
            <option value=""${!val ? ' selected' : ''}>—</option>
            <option value="true"${val === true || val === 'true' ? ' selected' : ''}>是</option>
            <option value="false"${val === false || val === 'false' ? ' selected' : ''}>否</option>
          </select>`;
        } else {
          inputHtml = `<input class="ll-props-inp${reqClass}" data-prop="${_he(p.name)}" data-src="${p._src}"
            data-dtype="${_he(p.data_type || 'string')}"
            value="${_he(val)}" placeholder="${_he(p.description || p.label_zh || p.name)}">`;
        }
        html += `<div class="ll-props-row"><span class="ll-props-key" title="${_he(p.description)}">${_he(p.label_zh || p.name)}</span><div class="ll-props-val">${inputHtml}</div></div>`;
      }
      area.innerHTML = html;

      if (!canEditCurrentLine) {
        area.querySelectorAll('.ll-props-inp, .ll-props-sel').forEach(inp => { inp.disabled = true; });
      }

      // 保存逻辑
      area.querySelectorAll('.ll-props-inp, .ll-props-sel').forEach(inp => {
        const save = async () => {
          const propName = inp.dataset.prop;
          const src = inp.dataset.src;
          const dtype = inp.dataset.dtype || 'string';
          let val = inp.value;
          if (val === '' || val == null) val = null;
          else if (dtype === 'integer') { val = parseInt(val, 10); if (isNaN(val)) return; }
          else if (dtype === 'float')   { val = parseFloat(val);   if (isNaN(val)) return; }
          else if (dtype === 'boolean') { val = val === 'true' ? true : val === 'false' ? false : null; }

          try {
            // 统一走 entity-props PATCH（后端自动路由到实体表列/ext/bop_entries.meta）
            await this._cf(`/api/bop/entries/${encodeURIComponent(gid)}/entity-props`, {
              method: 'PATCH', body: JSON.stringify({ [propName]: val }),
            });
            if (src === 'entity') {
              entityVals[propName] = val;
              // 同步更新 row.entity_data，使布局卡片立即显示新值
              if (row.entity_data && typeof row.entity_data === 'object') {
                row.entity_data[propName] = val;
              }
            } else {
              metaVals[propName] = val;
            }
          } catch (e) {
            this._toast?.('保存失败: ' + (e?.message || e), 'error');
          }
          // 保存后立即刷新属性面板 + 布局卡片（保持画面焦点不变）
          this._renderProps(gid, data.rowByGid.get(gid) || row);
          this._preserveLayoutView();
          this._reloadData?.();
        };
        inp.addEventListener('blur', save);
        inp.addEventListener('change', save);
        inp.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); save(); } });
      });

    } catch (e) {
      area.innerHTML = `<div style="color:var(--red);font-size:11px;padding:4px">属性加载失败</div>`;
    }
  }

  // ── 列2：关系 ─────────────────────────────────────────────────────────────

  async _renderRels(gid) {
    this._relsBody.innerHTML = '<div style="color:var(--surface2);font-size:11px;padding:8px">加载中…</div>';
    const data = this._getLineageData();
    const lineGrantSet = data?.lineGrantSet || new Set();
    const lineReadOnly = !!data?.lineReadOnly;
    const row = data?.rowByGid?.get(gid);
    const currentLineGid = this._findAncestorOfType(gid, 'line_process', data?.rowByGid) || (row?.node_type === 'line_process' ? row.gid : null);
    const canEditCurrentLine = !lineReadOnly || !currentLineGid || lineGrantSet.has(currentLineGid);
    const hasChildren = data ? (data.childMap.get(gid) || []).filter(r => !r.is_deleted).length > 0 : false;

    let links = [];
    try {
      const resp = await this._cf(
        `/api/bop/entry-links?entry_gid=${encodeURIComponent(gid)}${hasChildren ? '&recursive=true' : ''}`
      );
      links = resp?.data || [];
    } catch {}
    this._relLinks = links;

    // 子节点从 childMap 取
    const childRows = data ? (data.childMap.get(gid) || []).filter(r => !r.is_deleted) : [];

    let html = '';
    for (const grp of REL_GROUPS) {
      // 本体关系 show_in_detail=false 时跳过整组
      if (grp.linkTypes && this._hiddenLinkTypes?.size && grp.linkTypes.every(lt => this._hiddenLinkTypes.has(lt))) {
        continue;
      }
      let items = [];
      if (grp.key === 'child') {
        items = childRows.map(r => ({
          _key: 'child', _title: r.title || r.gid, _badge: r.node_type,
          _ntType: r.node_type || 'process',
          _row: r, _sourceGid: gid, _sourceTitle: null,
          link: { link_type: 'child', entity_gid: r.gid }, source_entry_gid: gid, source_entry_title: null,
        }));
      } else {
        items = links
          .filter(l => grp.linkTypes.includes(l.link_type))
          .map(l => ({
            _key: grp.key, _title: l.entity_title || l.entity_gid, _badge: l.link_type,
            _ntType: grp.ntType, link: l,
            source_entry_gid: l.source_entry_gid || gid,
            source_entry_title: l.source_entry_title,
          }));
      }

      const isOpen = !items.length ? false : true;
      html += `
        <div class="ll-rg">
          <div class="ll-rg-hdr" data-key="${_he(grp.key)}">
            <span class="ll-rg-tog">${isOpen ? '▼' : '▶'}</span>
            <span class="lv-nt-dot lv-nt-${_he(grp.ntType)}"></span>
            <span class="ll-rg-name">${_he(grp.name)}</span>
            <span class="ll-rg-cnt">${items.length}</span>
            <button class="ll-rg-add" data-key="${_he(grp.key)}" title="添加${_he(grp.name)}"${canEditCurrentLine ? '' : ' disabled style="opacity:.45;cursor:not-allowed"'}>＋</button>
          </div>
          <div class="ll-rg-items${isOpen ? ' open' : ''}">
            ${items.length ? items.map((item, idx) => {
              const fromOther = item.source_entry_gid && item.source_entry_gid !== gid;
              return `
                <div class="ll-ri" data-key="${_he(grp.key)}" data-idx="${idx}">
                  <span class="lv-nt-dot lv-nt-${_he(item._ntType || 'process')}"></span>
                  <span class="ll-ri-title">${_he(item._title || item.link?.entity_gid || '—')}</span>
                  <span class="ll-ri-badge ${_statusBadgeClass(item._badge)}">${_he(item._badge || '')}</span>
                </div>
                ${fromOther ? `<div class="ll-ri-src" data-src-gid="${_he(item.source_entry_gid)}">来自：${_he(item.source_entry_title || item.source_entry_gid)}</div>` : ''}`;
            }).join('') : `<div class="ll-rg-empty">暂无关联，点击 ＋ 添加</div>`}
          </div>
        </div>`;
    }

    // ── 从本体 schema 加载自定义关系（有 link_type_binding 且 show_in_detail 非 false）──
    let ontoRelTypes = [];
    try {
      const schemaResp = await this._cf(`/api/ontology/schema/${encodeURIComponent(row.node_type)}`);
      ontoRelTypes = (schemaResp?.relations || []).filter(r => r.link_type_binding && r.show_in_detail !== false);
    } catch (_) {}

    // ── 动态关系组：收集未被 REL_GROUPS 覆盖的 link_type ──
    const knownLinkTypes = new Set();
    REL_GROUPS.forEach(g => { if (g.linkTypes) g.linkTypes.forEach(lt => knownLinkTypes.add(lt)); });
    const dynamicLinks = links.filter(l => !knownLinkTypes.has(l.link_type) && l.link_type !== 'child');
    // 补入本体中定义但尚无实际链接的关系（显示空组 + ＋ 按钮）
    ontoRelTypes.forEach(r => {
      if (!knownLinkTypes.has(r.link_type_binding) && !dynamicLinks.some(l => l.link_type === r.link_type_binding)) {
        dynamicLinks.push({ link_type: r.link_type_binding, entity_gid: '', entity_title: '', _placeholder: true });
      }
    });
    if (dynamicLinks.length) {
      const byType = {};
      dynamicLinks.forEach(l => {
        const lt = l.link_type || 'other';
        if (!byType[lt]) byType[lt] = [];
        byType[lt].push(l);
      });
      for (const [lt, ltLinks] of Object.entries(byType)) {
        const items = ltLinks.map(l => ({
          _key: 'link:' + lt, _title: l.entity_title || l.entity_gid, _badge: lt,
          _ntType: 'process', link: l,
          source_entry_gid: l.source_entry_gid || gid,
          source_entry_title: l.source_entry_title,
        }));
        const isPlaceholder = ltLinks.length === 1 && ltLinks[0]._placeholder;
        html += `
          <div class="ll-rg">
            <div class="ll-rg-hdr" data-key="link:${_he(lt)}">
              <span class="ll-rg-tog">▼</span>
              <span class="lv-nt-dot lv-nt-process"></span>
              <span class="ll-rg-name">${_he(lt)}</span>
              <span class="ll-rg-cnt">${isPlaceholder ? 0 : items.length}</span>
              <button class="ll-rg-add" data-key="link:${_he(lt)}" title="添加${_he(lt)}"${canEditCurrentLine ? '' : ' disabled style="opacity:.45;cursor:not-allowed"'}>＋</button>
            </div>
            <div class="ll-rg-items open">
              ${isPlaceholder
                ? '<div class="ll-rg-empty">暂无关联，点击 ＋ 添加</div>'
                : items.map((item, idx) => `
                <div class="ll-ri" data-key="link:${_he(lt)}" data-idx="${idx}">
                  <span class="lv-nt-dot lv-nt-${_he(item._ntType || 'process')}"></span>
                  <span class="ll-ri-title">${_he(item._title || item.link?.entity_gid || '—')}</span>
                  <span class="ll-ri-badge">${_he(item._badge || '')}</span>
                </div>`).join('')}
            </div>
          </div>`;
      }
    }

    mountEl.innerHTML = html;

    // 分组折叠
    mountEl.querySelectorAll('.ll-rg-hdr').forEach(hdr => {
      hdr.addEventListener('click', e => {
        if (e.target.classList.contains('ll-rg-add')) return;
        const wrap = hdr.nextElementSibling;
        const open = wrap.classList.contains('open');
        wrap.classList.toggle('open', !open);
        hdr.querySelector('.ll-rg-tog').textContent = !open ? '▼' : '▶';
      });
    });

    // 关系行点击 → 详情面板
    mountEl.querySelectorAll('.ll-ri').forEach(ri => {
      ri.addEventListener('click', () => {
        mountEl.querySelectorAll('.ll-ri').forEach(r => r.classList.remove('sel'));
        ri.classList.add('sel');
        const key = ri.dataset.key;
        const idx = parseInt(ri.dataset.idx);
        const grp = REL_GROUPS.find(g => g.key === key);

        if (key === 'child') {
          const childItems = childRows.map(r => ({
            _key: 'child', _title: r.title || r.gid, _row: r,
            source_entry_gid: gid, source_entry_title: null, link: { link_type: 'child', entity_gid: r.gid },
          }));
          this._openViewDetail(childItems[idx], gid);
        } else if (grp) {
          const grpLinks = links.filter(l => grp.linkTypes.includes(l.link_type))
            .map(l => ({ _key: key, _title: l.entity_title || l.entity_gid, link: l,
              source_entry_gid: l.source_entry_gid || gid, source_entry_title: l.source_entry_title }));
          this._openViewDetail(grpLinks[idx], gid);
        } else if (key.startsWith('link:')) {
          // 动态关系（本体自定义 link_type）
          const linkType = key.slice(5);
          const dynLinks = links.filter(l => l.link_type === linkType)
            .map(l => ({ _key: key, _title: l.entity_title || l.entity_gid, link: l,
              source_entry_gid: l.source_entry_gid || gid, source_entry_title: l.source_entry_title }));
          if (dynLinks[idx]) this._openViewDetail(dynLinks[idx], gid);
        }
      });
    });

    // 来源行点击 → 跳转子节点
    this._relsBody.querySelectorAll('.ll-ri-src').forEach(src => {
      src.addEventListener('click', () => {
        const srcGid = src.dataset.srcGid;
        if (srcGid) this.open(srcGid);
      });
    });

    // ＋ 按钮 → 添加模式
    this._relsBody.querySelectorAll('.ll-rg-add').forEach(btn => {
      btn.addEventListener('click', e => {
        e.stopPropagation();
        if (!canEditCurrentLine) {
          this._toast?.('当前线体无编辑权限（只读）', 'warn');
          return;
        }
        const key = btn.dataset.key;
        const grp = REL_GROUPS.find(g => g.key === key);
        if (grp) {
          const row = this._currentRow;
          if (key === 'child') {
            const childInfo = CHILD_TYPE_MAP[row?.node_type || null];
            this._openAddDetail(key, gid, childInfo?.type, childInfo?.label || '子节点');
          } else {
            this._openAddDetail(key, gid, grp.linkTypes?.[0], grp.name);
          }
        } else if (key.startsWith('link:')) {
          // 本体自定义关系：link_type = key 去掉 "link:" 前缀
          this._openAddDetail(key, gid, key.slice(5), key.slice(5));
        }
      });
    });
  }

  // ── 列3：详情面板 ─────────────────────────────────────────────────────────

  _renderDetailEmpty() {
    this._closeDetDrawer();
    this._detMode = 'empty';
    this._addType = null;
  }

  async _openViewDetail(item, currentGid) {
    this._selectedRel = item;
    this._detMode = 'view';

    const fromOther = item.source_entry_gid && item.source_entry_gid !== currentGid;
    const linkType  = item.link?.link_type;
    const entityGid = item.link?.entity_gid;
    const grp       = REL_GROUPS.find(g => g._key === item._key || g.key === item._key);

    // 加载实体字段值
    let entityData = {};
    if (linkType && linkType !== 'child' && entityGid) {
      try {
        const resp = await this._cf(`/api/bop/entity-detail?link_type=${encodeURIComponent(linkType)}&ref_gid=${encodeURIComponent(entityGid)}`);
        entityData = resp?.data || {};
      } catch {}
    } else if (linkType === 'child' && entityGid) {
      // 子节点 → 从 lineage data 读
      const data = this._getLineageData();
      const row = data?.rowByGid.get(entityGid);
      if (row) entityData = { title: row.title, node_type: row.node_type, vpps: row.vpps, ...row.meta };
    }

    const fieldCfg = DETAIL_FIELDS[linkType] || [];
    const data = this._getLineageData();
    const lineGrantSet = data?.lineGrantSet || new Set();
    const lineReadOnly = !!data?.lineReadOnly;
    const currentLineGid = this._findAncestorOfType(currentGid, 'line_process', data?.rowByGid) || (data?.rowByGid?.get(currentGid)?.node_type === 'line_process' ? currentGid : null);
    const canEditCurrentLine = !lineReadOnly || !currentLineGid || lineGrantSet.has(currentLineGid);
    let fieldsHtml = '';
    if (fieldCfg.length) {
      for (const f of fieldCfg) {
        if (f.sec !== undefined) {
          fieldsHtml += `<div class="ll-det-sec">${_he(f.sec)}</div>`;
          continue;
        }
        const val = entityData[f.f] ?? '';
        let inputHtml = '';
        if (f.t === 'select' && f.opts) {
          const opts = f.opts.split(',').map(v => `<option value="${_he(v)}"${String(val) === v ? ' selected' : ''}>${_he(v)}</option>`).join('');
          inputHtml = `<select class="ll-df-sel" data-field="${_he(f.f)}">${opts}</select>`;
        } else if (f.t === 'textarea') {
          inputHtml = `<textarea class="ll-df-ta" data-field="${_he(f.f)}" rows="3">${_he(val)}</textarea>`;
        } else {
          inputHtml = `<input class="ll-df-inp" data-field="${_he(f.f)}" type="${_he(f.t || 'text')}" value="${_he(val)}">`;
        }
        fieldsHtml += `<div class="ll-df"><span class="ll-df-k">${_he(f.k)}</span><div class="ll-df-v">${inputHtml}</div></div>`;
      }
    } else if (linkType === 'child') {
      // 子节点用本体属性
      fieldsHtml = '<div style="color:var(--surface2);font-size:11px;padding:4px">点击保存后可在属性列编辑本体属性</div>';
    } else {
      fieldsHtml = `<div style="padding:8px;font-size:11px;color:var(--surface2)">暂无可编辑字段</div>`;
    }

    const badgeBg = { child: 'rgba(116,199,236,.12)', issue: 'rgba(243,139,168,.12)', task_std: 'rgba(137,180,250,.1)', task_custom: 'rgba(137,180,250,.1)', pbom_part: 'rgba(137,220,235,.12)' };
    const badgeFg = { child: 'var(--sapphire)', issue: 'var(--red)', task_std: 'var(--blue)', task_custom: 'var(--blue)', pbom_part: 'var(--teal)' };
    const bg = grp ? '' : (badgeBg[linkType] || 'rgba(108,112,134,.12)');
    const fg = grp ? '' : (badgeFg[linkType] || 'var(--subtext0)');
    const typeName = grp ? grp.name : (linkType || '实体');

    this._detDrawerBody.innerHTML = `
      <div class="ll-det-view" style="display:flex;flex-direction:column;height:100%">
        <div class="ll-det-hdr">
          <div class="ll-det-type-row">
            <span class="ll-det-type-badge" style="background:${_he(bg)};color:${_he(fg)}">${_he(typeName)}</span>
            <input class="ll-det-title-inp" id="llDetTitleInp" value="${_he(item._title || entityData.title || '')}">
            <button class="ll-dp-hdr-btn" id="llDetClose">✕</button>
          </div>
          ${fromOther ? `<div class="ll-det-source-tag">来自节点：<a id="llDetSrcLink" data-gid="${_he(item.source_entry_gid)}">${_he(item.source_entry_title || item.source_entry_gid)}</a></div>` : ''}
        </div>
        <div class="ll-det-fields">${fieldsHtml}</div>
        <div class="ll-det-actions">
          ${linkType !== 'child' ? `<button class="ll-det-btn ll-det-btn-danger" id="llDetUnlink"${canEditCurrentLine ? '' : ' disabled style="opacity:.45;cursor:not-allowed"'}>解除关联</button>` : ''}
          <button class="ll-det-btn ll-det-btn-ghost" id="llDetCancel">取消</button>
          <button class="ll-det-btn ll-det-btn-primary" id="llDetSave"${canEditCurrentLine ? '' : ' disabled style="opacity:.45;cursor:not-allowed"'}>保存</button>
        </div>
      </div>`;

    this._openDetDrawer();

    // 关闭

    // 来源跳转
    this._detDrawerBody.querySelector('#llDetSrcLink')?.addEventListener('click', e => {
      const srcGid = e.target.dataset.gid;
      if (srcGid) this.open(srcGid);
    });

    // 保存
    this._detDrawerBody.querySelector('#llDetSave')?.addEventListener('click', async () => {
      if (!canEditCurrentLine) {
        this._toast?.('当前线体无编辑权限（只读）', 'warn');
        return;
      }
      const fields = {};
      this._detDrawerBody.querySelectorAll('[data-field]').forEach(el => {
        fields[el.dataset.field] = el.value || null;
      });
      try {
        if (linkType !== 'child') {
          await this._cf('/api/bop/entity-detail', {
            method: 'PATCH',
            body: JSON.stringify({ link_type: linkType, ref_gid: entityGid, fields }),
          });
        } else if (entityGid) {
          const newTitle = this._detDrawerBody.querySelector('#llDetTitleInp')?.value?.trim();
          if (newTitle) {
            await this._patchEntry(entityGid, { title: newTitle });
            const data = this._getLineageData();
            const r = data?.rowByGid.get(entityGid);
            if (r) r.title = newTitle;
          }
        }
        this._toast?.('已保存', 'ok', 1200);
        await this._renderRels(this._currentGid);
      } catch (e) {
        this._toast?.('保存失败: ' + (e?.message || e), 'error');
      }
    });

    // 解除关联
    this._detDrawerBody.querySelector('#llDetUnlink')?.addEventListener('click', async () => {
      if (!canEditCurrentLine) {
        this._toast?.('当前线体无编辑权限（只读）', 'warn');
        return;
      }
      if (!item.link?.gid) return;
      try {
        await this._cf(`/api/bop/entry-links/${encodeURIComponent(item.link.gid)}`, { method: 'DELETE' });
        this._renderDetailEmpty();
        await this._renderRels(this._currentGid);
      } catch (e) {
        this._toast?.('解除失败: ' + (e?.message || e), 'error');
      }
    });
  }

  async _openAddDetail(key, parentGid, nodeType, typeLabel) {
    this._detMode = 'add';
    this._addType = key;

    const grp = REL_GROUPS.find(g => g.key === key);
    const dot = grp?.dot || '#89b4fa';

    const isResourceGroup = key === 'equip' || key === 'tool' || key === 'fixture' || [
      'physical_equipment', 'project_equipment', 'needsEquipment',
      'physical_tool', 'project_tools', 'needsTool',
      'physical_fixture', 'project_tooling', 'needsFixture',
    ].includes(nodeType || '');
    let selLinkType = nodeType || '';

    // 加载候选：按关系类型走对应数据源
    let candidates = [];
    let candSrcLabel = 'GBOP';
    const verInfo = this._getVersionInfo ? this._getVersionInfo() : null;
    const _nt = nodeType || '';

    // ── PBOM 版本选择（仅 pbom 类型） ──
    let pbomVersions = [];
    let selectedPbomGid = null;
    let isPbomType = key === 'pbom' || ['pbom_part', 'usesPart', 'part', 'non_standard_part', 'standard_part', 'support_material'].includes(_nt);

    try {
      if (isPbomType) {
        // 加载 PBOM 版本列表
        const verResp = await this._cf('/api/ebom/snapshots?limit=50');
        pbomVersions = verResp?.data || (Array.isArray(verResp) ? verResp : []);
        selectedPbomGid = verInfo?.pbomVersionGid || pbomVersions[0]?.gid || null;
        candSrcLabel = 'PBOM';
        // 加载默认版本下的零件
        if (selectedPbomGid) {
          const partResp = await this._cf(`/api/ebom/snapshots/${selectedPbomGid}/parts`);
          const parts = partResp?.data || [];
          candidates = parts.map(r => ({
            gid: r.gid,
            title: r.part_no || r.name || r.gid,
            part_no: r.part_no || '',
            name: r.name || '',
            vpps: r.vpps || '',
            component_id: r.component_id || '',
            component_type: r.component_type || '',
            quantity: r.quantity || 1,
            unit: r.unit || 'pcs',
          }));
        }
      } else if (key === 'equip' || ['physical_equipment', 'project_equipment', 'needsEquipment'].includes(_nt)) {
        const fgid = verInfo?.factoryGid;
        const url = fgid ? `/api/bop/factory/equipments?factory_gid=${encodeURIComponent(fgid)}&limit=20` : `/api/bop/factory/equipments?limit=20`;
        const resp = await this._cf(url); candidates = resp?.data || []; candSrcLabel = '设备库';
      } else if (key === 'tool' || ['physical_tool', 'project_tools', 'needsTool'].includes(_nt)) {
        const resp = await this._cf(`/api/bop/factory/tools?limit=20`);
        candidates = resp?.data || []; candSrcLabel = '工具库';
      } else if (key === 'fixture' || ['physical_fixture', 'project_tooling', 'needsFixture'].includes(_nt)) {
        const resp = await this._cf(`/api/bop/factory/fixtures?limit=20`);
        candidates = resp?.data || []; candSrcLabel = '工装库';
      } else if (key === 'issue' || _nt === 'issue') {
        const pgid = verInfo?.projectGid;
        const resp = await this._cf(pgid ? `/api/issues?project_gid=${encodeURIComponent(pgid)}&page_size=20` : `/api/issues?page_size=20`);
        candidates = (resp?.data || []).map(r => ({ gid: r.gid, title: r.title })); candSrcLabel = '问题清单';
      } else if (key === 'task' || ['task_std', 'task_custom'].includes(_nt)) {
        const pgid = verInfo?.projectGid;
        const resp = await this._cf(pgid ? `/api/tasks?project_gid=${encodeURIComponent(pgid)}&page_size=20` : `/api/tasks?page_size=20`);
        candidates = (resp?.data || []).map(r => ({ gid: r.gid, title: r.title })); candSrcLabel = '任务清单';
      } else if (['knowledge', 'rule_std', 'rule_custom'].includes(_nt)) {
        const resp = await this._cf(`/api/knowledge_entries?limit=20`);
        candidates = (resp?.data || []).map(r => ({ gid: r.gid, title: r.title })); candSrcLabel = '知识库';
      } else {
        const searchType = _nt || 'process';
        const resp = await this._cf(`/api/gbop/entries?node_type=${encodeURIComponent(searchType)}&limit=10`);
        candidates = resp?.data || []; candSrcLabel = 'GBOP';
      }
    } catch (e) { console.warn('[DetailPanel] 加载候选失败:', e); }

    // ── 候选列表 HTML ──
    const _buildCandList = () => {
      let html;
      if (candidates.length > 0) {
        html = candidates.map(c => `
          <div class="ll-det-sr-item" data-gid="${_he(c.gid)}"
               data-title="${_he(c.title || c.name || '')}"
               data-part_no="${_he(c.part_no || '')}"
               data-name="${_he(c.name || '')}"
               data-vpps="${_he(c.vpps || '')}"
               data-component_id="${_he(c.component_id || '')}">
            <span class="lv-nt-dot lv-nt-${_he(grp?.ntType || 'part')}"></span>
            <div class="ll-det-sr-info">
              <span class="ll-det-sr-name">${_he(c.part_no || c.title || c.name || c.gid)}</span>
              ${c.name ? `<span class="ll-det-sr-sub">${_he(c.name)}</span>` : ''}
            </div>
            ${c.vpps ? `<span class="ll-det-sr-tag">${_he(c.vpps)}</span>` : ''}
            <span class="ll-det-sr-src">${_he(candSrcLabel)}</span>
          </div>`).join('');
      } else {
        html = `<div style="color:var(--surface2);font-size:11px;padding:8px 10px">暂无数据</div>`;
      }
      return html;
    };

    // ── PBOM 版本选择器 HTML ──
    const verSelHtml = isPbomType && pbomVersions.length > 0 ? `
      <div class="ll-det-ver-sel" style="padding:0 0 8px">
        <label style="font-size:11px;color:var(--surface2);display:flex;align-items:center;gap:6px">
          PBOM 版本
          <select id="llPbomVerSel" style="flex:1;background:var(--base,#1e1e2e);color:var(--text,#cdd6f4);
            border:1px solid var(--surface1,#45475a);border-radius:4px;padding:3px 6px;font-size:11px;max-width:100%">
            ${pbomVersions.map(v => `<option value="${_he(v.gid)}" ${v.gid === selectedPbomGid ? 'selected' : ''}>${_he(v.name || v.version_tag || v.gid)}</option>`).join('')}
          </select>
        </label>
      </div>` : '';

    const candHtml = _buildCandList();

    this._detDrawerBody.innerHTML = `
      <div class="ll-det-add" style="display:flex;flex-direction:column;height:100%">
        <div class="ll-det-add-hdr">
          <div class="ll-det-add-type-row">
            <span class="ll-det-type-badge" style="background:rgba(137,180,250,.1);color:var(--blue)">添加${_he(typeLabel)}</span>
            <button class="ll-dp-hdr-btn" id="llAddClose" style="margin-left:auto">✕</button>
          </div>
          ${verSelHtml}
          ${isResourceGroup ? `
          <div style="display:flex;align-items:center;gap:6px;padding:0 0 6px">
            <span style="font-size:10px;color:var(--subtext0,#a6adc8)">类型</span>
            <select id="llAddLinkTypeSel" style="flex:1;background:var(--base,#1e1e2e);color:var(--text,#cdd6f4);
              border:1px solid var(--surface1,#45475a);border-radius:4px;padding:3px 6px;font-size:11px">
              ${(grp?.linkTypes || []).map(lt => {
                const labels = { physical_equipment:'实物设备', project_equipment:'需求设备',
                  physical_tool:'实物工具', project_tools:'需求工具',
                  physical_fixture:'实物工装', project_tooling:'需求工装' };
                return `<option value="${_he(lt)}"${lt === (selLinkType || grp.linkTypes[0]) ? ' selected' : ''}>${_he(labels[lt] || lt)}</option>`;
              }).join('')}
            </select>
          </div>` : ''}
          <div class="ll-det-search">
            <span style="font-size:11px;color:var(--overlay1)">⌕</span>
            <input id="llAddSearchInp" placeholder="搜索零件号 / 名称 / VPPS…">
          </div>
        </div>
        <div class="ll-det-sr-results" id="llAddCands">
          ${candHtml}
        </div>
        <div class="ll-det-actions">
          <button class="ll-det-btn ll-det-btn-ghost" id="llAddCancel">取消</button>
          <button class="ll-det-btn ll-det-btn-primary" id="llAddConfirm">确认关联</button>
        </div>
      </div>`;

    this._openDetDrawer();

    // 关闭/取消

    // ── PBOM 版本切换 → 重新加载零件 ──
    const verSel = this._detDrawerBody.querySelector('#llPbomVerSel');
    if (verSel) {
      verSel.addEventListener('change', async () => {
        const newGid = verSel.value;
        if (!newGid) return;
        selectedPbomGid = newGid;
        const candsEl = this._detDrawerBody.querySelector('#llAddCands');
        candsEl.innerHTML = '<div style="color:var(--surface2);font-size:11px;padding:8px 10px">加载中…</div>';
        try {
          const partResp = await this._cf(`/api/ebom/snapshots/${newGid}/parts`);
          const parts = partResp?.data || [];
          candidates = parts.map(r => ({
            gid: r.gid,
            title: r.part_no || r.name || r.gid,
            part_no: r.part_no || '',
            name: r.name || '',
            vpps: r.vpps || '',
            component_id: r.component_id || '',
            component_type: r.component_type || '',
            quantity: r.quantity || 1,
            unit: r.unit || 'pcs',
          }));
          candsEl.innerHTML = _buildCandList();
          // 重新绑定点击事件
          _bindCandClicks();
        } catch (e) {
          candsEl.innerHTML = '<div style="color:#f38ba8;font-size:11px;padding:8px 10px">加载失败</div>';
        }
      });
    }

    // ── 类型切换（实物/需求）──
    const typeSel = this._detDrawerBody.querySelector('#llAddLinkTypeSel');
    typeSel?.addEventListener('change', () => {
      selLinkType = typeSel.value;
    });

    // ── 搜索（客户端过滤，按零件号/名称/VPPS/组件ID） ──
    const searchInp = this._detDrawerBody.querySelector('#llAddSearchInp');
    searchInp?.addEventListener('input', () => {
      const q = searchInp.value.trim().toLowerCase();
      this._detDrawerBody.querySelectorAll('.ll-det-sr-item').forEach(item => {
        const fields = [
          item.dataset.title || '',
          item.dataset.part_no || '',
          item.dataset.name || '',
          item.dataset.vpps || '',
          item.dataset.component_id || '',
        ];
        item.style.display = (!q || fields.some(f => f.toLowerCase().includes(q))) ? '' : 'none';
      });
    });
    searchInp?.focus();

    // ── 选择候选 ──
    const _bindCandClicks = () => {
      this._detDrawerBody.querySelectorAll('.ll-det-sr-item').forEach(item => {
        item.addEventListener('click', () => {
          this._detDrawerBody.querySelectorAll('.ll-det-sr-item').forEach(i => i.classList.remove('sel'));
          item.classList.add('sel');
        });
      });
    };
    _bindCandClicks();

    // ── 确认添加 ──
    this._detDrawerBody.querySelector('#llAddConfirm')?.addEventListener('click', async () => {
      const sel = this._detDrawerBody.querySelector('.ll-det-sr-item.sel');
      if (!sel) { this._toast?.('请先选择一个候选零件', 'warn'); return; }
      const entityGid = sel.dataset.gid;

      const data = this._getLineageData();
      const versionGid = data?.versionGid;
      if (!versionGid) { this._toast?.('无法获取版本信息', 'error'); return; }

      try {
        if (key === 'child') {
          // 创建子节点
          const title = sel.dataset.title;
          const childCount = (data.childMap.get(parentGid) || []).length;
          await this._cf('/api/bop/entries', {
            method: 'POST',
            body: JSON.stringify({
              version_gid: versionGid,
              parent_gid: parentGid,
              node_type: nodeType,
              title,
              seq_no: (childCount + 1) * 10,
            }),
          });
          await this._reloadData();
          const newData = this._getLineageData();
          const children = newData?.childMap.get(parentGid) || [];
          const newChild = children.find(r => r.title === title);
          if (newChild) this.open(newChild.gid);
          else this.refresh();
          this._toast?.('已添加', 'ok', 1200);
        } else if (isPbomType) {
          // 创建 PBOM 零件关联
          await this._cf('/api/bop/entry-links', {
            method: 'POST',
            body: JSON.stringify({
              entry_gid: parentGid,
              link_type: 'pbom_part',
              entity_gid: entityGid,
              is_primary: true,
            }),
          });
          await this._reloadData();
          this.refresh();
          this._toast?.('已关联 PBOM 零件', 'ok', 1200);
        } else if (key === 'issue' || key === 'task') {
          this._toast?.('关联已有实体请从右侧关联面板选择', 'info');
          return;
        } else if (key === 'equip' || key === 'tool' || key === 'fixture' || isResourceGroup) {
          // 创建实物/需求关联（nodeType 已在 type 选择器中确定）
          const linkType = selLinkType || nodeType || '';
          await this._cf('/api/bop/entry-links', {
            method: 'POST',
            body: JSON.stringify({
              entry_gid: parentGid,
              link_type: linkType,
              entity_gid: entityGid,
              is_primary: false,
            }),
          });
          await this._reloadData();
          this.refresh();
          this._closeDetDrawer();
          this._toast?.('已关联', 'ok', 1200);
        } else if (key.startsWith('link:')) {
          // 本体自定义关系：从 schema 解析真实 link_type_binding
          const relName = key.slice(5);
          let linkType = relName;
          try {
            const schema = await this._cf(`/api/ontology/schema/${encodeURIComponent(nodeType)}`);
            const rel = (schema?.relations || []).find(r => r.name === relName);
            if (rel?.link_type_binding) linkType = rel.link_type_binding;
          } catch {}
          await this._cf('/api/bop/entry-links', {
            method: 'POST',
            body: JSON.stringify({
              entry_gid: parentGid,
              link_type: linkType,
              entity_gid: entityGid,
              is_primary: false,
            }),
          });
          await this._reloadData();
          this.refresh();
          this._toast?.('已关联', 'ok', 1200);
        } else {
          // 默认：创建 entry_link
          await this._cf('/api/bop/entry-links', {
            method: 'POST',
            body: JSON.stringify({
              entry_gid: parentGid,
              link_type: typeLabel,
              entity_gid: entityGid,
              is_primary: false,
            }),
          });
          await this._reloadData();
          this.refresh();
          this._toast?.('已关联', 'ok', 1200);
        }
      } catch (e) {
        this._toast?.('添加失败: ' + (e?.message || e), 'error');
      }
    });
  }

  // ── 列4：规则 ─────────────────────────────────────────────────────────────

  async _renderRules(gid, row) {
    if (!this._rulesBody) return;
    this._rulesBody.innerHTML = '<div style="color:var(--surface2);font-size:11px;padding:4px">加载中…</div>';
    if (!row?.node_type) { this._rulesBody.innerHTML = ''; return; }
    try {
      const schema = await this._cf(`/api/ontology/schema/${encodeURIComponent(row.node_type)}`);
      const rules = schema?.rules || [];
      if (!rules.length) {
        this._rulesBody.innerHTML = '<div style="color:var(--surface2);font-size:11px;padding:4px">暂无规则</div>';
        return;
      }
      // 运行规则检查
      let violations = [];
      try {
        const chk = await this._cf(`/api/rule-engine/check-entry?entry_gid=${encodeURIComponent(gid)}`);
        violations = chk?.data || [];
      } catch {}

      const violMap = new Map(violations.map(v => [v.rule_gid, v]));
      let html = '';
      for (const rule of rules) {
        const viol = violMap.get(rule.gid);
        const cls = viol ? (viol.result === 'fail' ? 'll-rule-fail' : 'll-rule-warn') : 'll-rule-pass';
        const ico = viol ? (viol.result === 'fail' ? '✗' : '⚠') : '✓';
        const lv  = rule.enforcement_level === 'mandatory' ? 'll-rule-lv-m' : 'll-rule-lv-a';
        const lvLabel = rule.enforcement_level === 'mandatory' ? '必须' : '建议';
        html += `
          <div class="ll-rule ${cls}">
            <div class="ll-rule-hdr">
              <span style="font-size:11px">${ico}</span>
              <span class="ll-rule-lv ${lv}">${lvLabel}</span>
              <span class="ll-rule-name">${_he(rule.name)}</span>
            </div>
            ${viol ? `<div class="ll-rule-msg">${_he(viol.message || '')}</div>` : ''}
          </div>`;
      }
      this._rulesBody.innerHTML = html;
    } catch {
      this._rulesBody.innerHTML = '<div style="color:var(--surface2);font-size:11px;padding:4px">规则加载失败</div>';
    }
  }

  // ── 列5：知识 ─────────────────────────────────────────────────────────────

  async _renderKnowledge(gid) {
    this._knowBody.innerHTML = '';
    try {
      const resp = await this._cf(
        `/api/bop/entry-links?entry_gid=${encodeURIComponent(gid)}`
      );
      const knowLinks = (resp?.data || []).filter(l => l.link_type === 'knowledge' || l.link_type === 'rule_std' || l.link_type === 'rule_custom');
      if (!knowLinks.length) {
        this._knowBody.innerHTML = '<div style="color:var(--surface2);font-size:11px;padding:4px">暂无关联知识</div>';
      } else {
        let html = '';
        for (const l of knowLinks) {
          const title = l.entity_title || l.entity_gid;
          const typeLabel = l.link_type === 'knowledge' ? '知识' : '规则';
          html += `
            <div class="ll-kn" data-link-gid="${_he(l.gid)}">
              <div class="ll-kn-top">
                <span class="ll-kn-dot"></span>
                <span class="ll-kn-title">${_he(title)}</span>
                <span class="ll-kn-type">${typeLabel}</span>
              </div>
            </div>`;
        }
        this._knowBody.innerHTML = html;
      }
    } catch {
      this._knowBody.innerHTML = '<div style="color:var(--surface2);font-size:11px;padding:4px">知识加载失败</div>';
    }

    this._knowAddBtn?.addEventListener('click', () => {
      this._toast?.('请从知识管理页搜索并关联', 'info');
    });
  }

  // ── 列宽 resize ───────────────────────────────────────────────────────────

  _initColumnResizers() {
    const el = this._el;
    el.querySelectorAll('.ll-dp-col-divider').forEach(divider => {
      const leftId = divider.dataset.left;
      if (!leftId) return;
      const leftCol = el.querySelector('#' + leftId);
      if (!leftCol) return;
      let startX, startW;
      divider.addEventListener('mousedown', e => {
        startX = e.clientX;
        startW = leftCol.offsetWidth;
        divider.classList.add('dragging');
        const onMove = ev => {
          const newW = Math.max(60, startW + ev.clientX - startX);
          leftCol.style.width = newW + 'px';
        };
        const onUp = () => {
          divider.classList.remove('dragging');
          this._saveWidths();
          document.removeEventListener('mousemove', onMove);
          document.removeEventListener('mouseup', onUp);
        };
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
        e.preventDefault();
      });
    });
  }

  _saveWidths() {
    const ids = ['llDpTree', 'llDpProps'];
    const w = {};
    ids.forEach(id => {
      const el = document.getElementById(id);
      if (el) w[id] = el.offsetWidth;
    });
    try { localStorage.setItem(_ldpLsk('lv:dpColWidths'), JSON.stringify(w)); } catch {}
  }

  _restoreWidths() {
    try {
      const saved = JSON.parse(localStorage.getItem(_ldpLsk('lv:dpColWidths')) || '{}');
      Object.entries(saved).forEach(([id, w]) => {
        const el = document.getElementById(id);
        if (el && w > 60) el.style.width = w + 'px';
      });
    } catch {}
  }

  // ── 垂直高度 resize ───────────────────────────────────────────────────────

  _bindResizeHandle() {
    if (!this._resizeHandle) return;
    const saved = localStorage.getItem(_ldpLsk('lv:dpHeight'));
    if (saved) this._el.style.setProperty('--ll-dp-height', saved + 'px');

    let startY, startH;
    this._resizeHandle.addEventListener('mousedown', e => {
      startY = e.clientY;
      startH = this._el.offsetHeight;
      const onMove = ev => {
        const newH = Math.max(180, startH - (ev.clientY - startY));
        this._el.style.setProperty('--ll-dp-height', newH + 'px');
      };
      const onUp = () => {
        const h = parseInt(getComputedStyle(this._el).getPropertyValue('--ll-dp-height'));
        if (h) try { localStorage.setItem(_ldpLsk('lv:dpHeight'), String(h)); } catch {}
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
      };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
      e.preventDefault();
    });
  }

  _bindHandleBar() {
    const _toggle = () => {
      if (this._isOpen) {
        this._isOpen = false;
        this._el.classList.remove('open');
        this._toolbarToggle?.classList.remove('active');
      } else {
        this._isOpen = true;
        this._userClosed = false;
        this._el.classList.add('open');
        this._toolbarToggle?.classList.add('active');
        if (this._currentGid) this.refresh();
      }
    };
    this._handleBar?.addEventListener('click', _toggle);
    this._toolbarToggle?.addEventListener('click', _toggle);

    // ✕ 关闭按钮
    this._el.querySelector('#llDpClose')?.addEventListener('click', () => {
      this._isOpen = false;
      this._userClosed = true;
      this._el.classList.remove('open');
      this._toolbarToggle?.classList.remove('active');
    });

  }

  _defaultTreeSettings() {
    return {
      selectedVersionGids: [],   // 选中版本 gid 数组（空 = 仅当前版本）
      selectedLineGids: null,    // null = 全部线体；数组 = 指定线体
      visibleNodeTypes: ['line_process', 'station_process', 'process', 'operation'],
    };
  }

  _loadTreeSettings() {
    try {
      const raw = localStorage.getItem(_ldpLsk('lv:treeSettings'));
      return raw ? { ...this._defaultTreeSettings(), ...JSON.parse(raw) } : this._defaultTreeSettings();
    } catch { return this._defaultTreeSettings(); }
  }

  _saveTreeSettings() {
    try { localStorage.setItem(_ldpLsk('lv:treeSettings'), JSON.stringify(this._treeSettings)); } catch {}
  }

  _renderSettingsPanel() {
    if (!this._settingsPanel) return;
    const verInfo = this._getVersionInfo ? this._getVersionInfo() : null;
    const versions = verInfo?.versions || [];
    const data = this._getLineageData();
    const allLines = data ? Array.from(data.rowByGid.values()).filter(r => r.node_type === 'line_process' && !r.is_deleted) : [];

    // 按 bop_name 分组版本
    const groups = new Map();
    versions.forEach(v => {
      const g = v.bop_name || '默认';
      if (!groups.has(g)) groups.set(g, []);
      groups.get(g).push(v);
    });

    const sel = this._treeSettings;
    const selVers = new Set(sel.selectedVersionGids);
    const selLines = sel.selectedLineGids ? new Set(sel.selectedLineGids) : null;
    const selTypes = new Set(sel.visibleNodeTypes);
    const curVerGid = verInfo?.currentGid || '';

    const NODE_TYPE_OPTIONS = [
      { type: 'line_process',    label: '线体' },
      { type: 'station_process', label: '工位' },
      { type: 'process',         label: '工序' },
      { type: 'operation',       label: '工步' },
    ];

    let html = `
      <div class="ll-ts-hdr">
        <span class="ll-ts-title">节点树设置</span>
        <button class="ll-ts-close" id="llTsClose">✕</button>
      </div>
      <div class="ll-ts-body">`;

    // 版本
    html += `<div class="ll-ts-section">
      <div class="ll-ts-sec-label">显示版本</div>`;
    for (const [grpName, vers] of groups) {
      if (vers.length > 1) html += `<div class="ll-ts-grp-label">${_he(grpName)}</div>`;
      vers.forEach(v => {
        const isCur = v.gid === curVerGid;
        const chk = isCur || selVers.has(v.gid);
        html += `<label class="ll-ts-item">
          <input type="checkbox" data-ver-gid="${_he(v.gid)}" ${chk ? 'checked' : ''} ${isCur ? 'disabled' : ''}>
          <span class="ll-ts-ver-dot ll-ver-${_he(v.status || 'active')}"></span>
          <span>${_he(v.name)}${isCur ? ' <em>(当前)</em>' : ''}</span>
        </label>`;
      });
    }
    html += `</div>`;

    // 线体（含全选/全不选）
    if (allLines.length > 0) {
      html += `<div class="ll-ts-section">
        <div class="ll-ts-sec-label" style="display:flex;align-items:center;gap:6px">
          显示线体
          <button class="ll-ts-mini-btn" id="llTsLineAll">全选</button>
          <button class="ll-ts-mini-btn" id="llTsLineNone">全不选</button>
        </div>`;
      allLines.forEach(l => {
        const chk = !selLines || selLines.has(l.gid);
        html += `<label class="ll-ts-item">
          <input type="checkbox" class="ll-ts-line-chk" data-line-gid="${_he(l.gid)}" ${chk ? 'checked' : ''}>
          <span class="lv-nt-dot lv-nt-line_process"></span>
          <span>${_he(l.title || l.gid)}</span>
        </label>`;
      });
      html += `</div>`;
    }

    // 节点类型
    html += `<div class="ll-ts-section">
      <div class="ll-ts-sec-label">显示节点类型</div>`;
    NODE_TYPE_OPTIONS.forEach(o => {
      html += `<label class="ll-ts-item">
        <input type="checkbox" data-node-type="${_he(o.type)}" ${selTypes.has(o.type) ? 'checked' : ''}>
        <span class="lv-nt-dot" style="background:${_he(NODE_TYPE_DOT[o.type]||'#6c7086')}"></span>
        <span>${_he(o.label)}</span>
      </label>`;
    });
    html += `</div>`;

    html += `<div class="ll-ts-actions">
        <button class="ll-ts-btn ll-ts-btn-primary" id="llTsApply">应用</button>
      </div>
    </div>`;

    this._settingsPanel.innerHTML = html;

    // 关闭
    this._settingsPanel.querySelector('#llTsClose')?.addEventListener('click', () => {
      this._settingsPanel.style.display = 'none';
    });

    // 线体全选/全不选
    this._settingsPanel.querySelector('#llTsLineAll')?.addEventListener('click', () => {
      this._settingsPanel.querySelectorAll('.ll-ts-line-chk').forEach(cb => cb.checked = true);
    });
    this._settingsPanel.querySelector('#llTsLineNone')?.addEventListener('click', () => {
      this._settingsPanel.querySelectorAll('.ll-ts-line-chk').forEach(cb => cb.checked = false);
    });

    // 应用
    this._settingsPanel.querySelector('#llTsApply')?.addEventListener('click', async () => {
      const newVers = [];
      this._settingsPanel.querySelectorAll('[data-ver-gid]:not(:disabled):checked').forEach(cb => newVers.push(cb.dataset.verGid));

      const lineChecks = [...this._settingsPanel.querySelectorAll('[data-line-gid]')];
      const checkedLines = lineChecks.filter(cb => cb.checked).map(cb => cb.dataset.lineGid);
      const newLines = (checkedLines.length === lineChecks.length || lineChecks.length === 0) ? null : checkedLines;

      const newTypes = [];
      this._settingsPanel.querySelectorAll('[data-node-type]:checked').forEach(cb => newTypes.push(cb.dataset.nodeType));

      this._treeSettings.selectedVersionGids = newVers;
      this._treeSettings.selectedLineGids    = newLines;
      this._treeSettings.visibleNodeTypes    = newTypes;
      this._saveTreeSettings();

      await this._loadExtraVersions(newVers);
      this._settingsPanel.style.display = 'none';
      this._renderTree(this._currentGid);
    });
  }

  async _loadExtraVersions(versionGids) {
    for (const gid of versionGids) {
      if (this._extraVersionData.has(gid)) continue;
      try {
        const resp = await this._cf(`/api/bop/versions/${encodeURIComponent(gid)}/entries`);
        const rawRows = resp?.data || [];
        const rowByGid = new Map(rawRows.map(r => [r.gid, r]));
        const childMap = new Map();
        rawRows.forEach(r => {
          const pk = r.parent_gid || null;
          if (!childMap.has(pk)) childMap.set(pk, []);
          childMap.get(pk).push(r);
        });
        this._extraVersionData.set(gid, { rowByGid, childMap, versionGid: gid });
      } catch {}
    }
  }

  _bindEvents() {} // 向后兼容，无操作

  // ── 向后兼容旧接口 ────────────────────────────────────────────────────────

  /** lineage.js 调用：数据刷新后同步面板（若当前有打开的节点则刷新显示） */
  updateData(data) {
    if (!this._isOpen) return;
    const newData = this._getLineageData();
    const verInfo = this._getVersionInfo ? this._getVersionInfo() : null;

    // 先无条件更新 _lastVersionGid，用 prevVer 判断是否真正切换了版本
    // 修复：_lastVersionGid 初始为 null，open() 之后第一次 updateData 会误判为版本切换
    const prevVer = this._lastVersionGid;
    if (verInfo?.currentGid) this._lastVersionGid = verInfo.currentGid;
    const versionChanged = !!prevVer && !!verInfo?.currentGid && prevVer !== verInfo.currentGid;

    // 版本变更：重置选中节点，刷新版本 picker，重绘整棵树
    if (versionChanged) {
      this._treeRootGid = null;   // 重置为新版本第一条线体
      this._currentGid  = null;
      this._currentRow  = null;
      this._treeExpanded.clear();
      // 刷新 picker 中的版本列表和选中态
      this._rebuildVerPicker();
      // 重绘树（空选中态）
      if (this._verSlot || this._lineSlot || this._treeBody) {
        this._renderTree(null);
        this._propsBody.innerHTML = '';
        this._relsBody.innerHTML  = '';
        this._rulesBody.innerHTML = '';
        this._knowBody.innerHTML  = '';
        this._renderDetailEmpty();
      }
      return;
    }

    // 版本未变：刷新树（inline add 进行中时跳过，避免覆盖输入框）
    if (!this._inlineAddPending) {
      // RAF 合批：多次 updateData 调用合并为一次渲染，避免 DOM 高频重建
      if (this._renderTreeRaf) cancelAnimationFrame(this._renderTreeRaf);
      const snapGid = this._currentGid;
      this._renderTreeRaf = requestAnimationFrame(() => {
        this._renderTreeRaf = null;
        if (!this._inlineAddPending) this._renderTree(snapGid || null);
      });
    }
    if (this._currentGid) {
      const row = newData?.rowByGid?.get(this._currentGid);
      if (row) {
        this._currentRow = row;
        this._renderRels(this._currentGid);
        this._renderRules(this._currentGid, row);
      }
    }

    // 同步 picker 选中高亮
    if (verInfo?.currentGid) this._refreshVerPickerSelection(verInfo.currentGid);
  }

  /** 版本切换后重建 picker（更新版本列表 + 当前选中） */
  _rebuildVerPicker() {
    const verInfo  = this._getVersionInfo ? this._getVersionInfo() : null;
    const versions = verInfo?.versions || [];
    // 销毁旧 picker，重建
    document.getElementById('llTreeVerPickerBody')?.remove();
    // 重建 verSlot HTML
    if (this._verSlot) {
      const verName = verInfo?.currentName || 'BOP版本';
      this._verSlot.innerHTML = `
        <div class="ll-tree-ver-bar" id="llTreeVerBar">
          <span class="ll-tree-ver-icon">☰</span>
          <span class="ll-tree-ver-name" id="llTreeVerName">${_he(verName)}</span>
          ${versions.length > 0 ? '<span class="ll-tree-root-arr">▾</span>' : ''}
        </div>`;
      this._buildVerPicker(versions, verInfo);
    }
  }

  /** lineage.js 调用：关闭面板但不标记 userClosed（视图切换时调用） */
  dismiss() {
    this._isOpen = false;
    this._el.classList.remove('open');
  }

  /** lineage.js 调用：强制刷新当前选中节点的详情区（兼容旧版 _renderDetail(sel) 调用） */
  get _selectedGid() { return this._currentGid; }

  // ── 下属实体统计（最终生效版本） ─────────────────────────────────────────────

  static get _STATS_CATEGORY_MAP() {
    return {
      physical_equipment: { label: '设备', ntType: 'equipment_factory' },
      project_equipment:  { label: '设备', ntType: 'equipment_factory' },
      physical_tool:      { label: '工具', ntType: 'tool_factory' },
      project_tools:      { label: '工具', ntType: 'tool_factory' },
      physical_fixture:   { label: '工装', ntType: 'fixture_factory' },
      project_tooling:    { label: '工装', ntType: 'fixture_factory' },
      pbom_part:          { label: '零件', ntType: 'non_standard_part' },
      issue:              { label: '问题', ntType: 'issue' },
      task_std:           { label: '任务', ntType: 'standard_task' },
      task_custom:        { label: '任务', ntType: 'standard_task' },
      knowledge:          { label: '知识', ntType: 'knowledge' },
      rule_std:           { label: '规则', ntType: 'craft_rules' },
      rule_custom:        { label: '规则', ntType: 'craft_rules' },
    };
  }

  async _renderStats(gid) {
    const area = this._propsBody?.querySelector('#llPropsStatsArea');
    if (!area) return;
    try {
      const data = this._getLineageData();
      const groups = {};

      // ── 1. 结构后代：从 childMap 递归统计 ────────────────────────────────
      const STRUCT_MAP = {
        station_process:  { label: '工位', ntType: 'station_process' },
        operator_process: { label: '岗位', ntType: 'operator_process' },
        process:          { label: '工序', ntType: 'process' },
        operation:        { label: '操作', ntType: 'operation' },
      };
      if (data?.childMap) {
        const walk = (parentGid) => {
          for (const r of (data.childMap.get(parentGid) || [])) {
            if (r.is_deleted) continue;
            const cat = STRUCT_MAP[r.node_type];
            if (cat) {
              if (!groups[cat.label]) groups[cat.label] = { ntType: cat.ntType, items: [], isStruct: true };
              groups[cat.label].items.push({ title: r.title || r.gid, gid: r.gid });
            }
            walk(r.gid);
          }
        };
        walk(gid);
      }

      // ── 2. 关联实体：从 entry-links recursive 拿 ─────────────────────────
      const catMap = LayoutDetailPanel._STATS_CATEGORY_MAP;
      try {
        const resp = await this._cf(`/api/bop/entry-links?entry_gid=${encodeURIComponent(gid)}&recursive=true`);
        for (const l of (resp?.data || [])) {
          const cat = catMap[l.link_type];
          if (!cat) continue;
          if (!groups[cat.label]) groups[cat.label] = { ntType: cat.ntType, items: [], isStruct: false };
          groups[cat.label].items.push(l);
        }
      } catch {}

      const keys = Object.keys(groups);
      if (!keys.length) { area.innerHTML = ''; return; }

      // ── 3. 渲染 ───────────────────────────────────────────────────────────
      let html = '<div class="ll-props-sec">下属统计</div>';
      for (const label of keys) {
        const { ntType, items, isStruct } = groups[label];
        html += `<div class="ll-stats-grp">
          <div class="ll-stats-hdr">
            <span class="ll-stats-tog">▶</span>
            <span class="lv-nt-dot lv-nt-${_he(ntType)}"></span>
            <span class="ll-stats-name">${_he(label)}</span>
            <span class="ll-stats-cnt">${items.length}</span>
          </div>
          <div class="ll-stats-items">
            ${items.map(item => {
              if (isStruct) {
                return `<div class="ll-stats-item ll-stats-item-nav" data-nav-gid="${_he(item.gid)}">
                  <span class="ll-stats-item-title">${_he(item.title)}</span>
                </div>`;
              }
              const l = item;
              const fromOther = l.source_entry_gid && l.source_entry_gid !== gid;
              // 零件：优先展示零件号+零件名，不显示 gid
              let displayTitle;
              if (l.link_type === 'pbom_part') {
                const parts = [l.entity_vpps || l.entity_part_no, l.entity_title].filter(Boolean);
                displayTitle = parts.join(' · ') || l.entity_gid;
              } else {
                displayTitle = l.entity_title || l.entity_gid || '—';
              }
              return `<div class="ll-stats-item">
                <span class="ll-stats-item-title">${_he(displayTitle)}</span>
                ${fromOther ? `<span class="ll-stats-item-src" data-src-gid="${_he(l.source_entry_gid)}">← ${_he(l.source_entry_title || l.source_entry_gid)}</span>` : ''}
              </div>`;
            }).join('')}
          </div>
        </div>`;
      }
      area.innerHTML = html;

      area.querySelectorAll('.ll-stats-hdr').forEach(hdr => {
        hdr.addEventListener('click', () => {
          const open = hdr.nextElementSibling.classList.toggle('open');
          hdr.querySelector('.ll-stats-tog').textContent = open ? '▼' : '▶';
        });
      });
      // 结构节点行点击 → 打开那个节点详情
      area.querySelectorAll('.ll-stats-item-nav').forEach(el => {
        el.addEventListener('click', () => {
          const navGid = el.dataset.navGid;
          if (navGid) { this.open(navGid); if (this._onNodeActivate) this._onNodeActivate(navGid); }
        });
      });
      // 关联实体的来源节点点击
      area.querySelectorAll('.ll-stats-item-src').forEach(el => {
        el.addEventListener('click', e => {
          e.stopPropagation();
          const srcGid = el.dataset.srcGid;
          if (srcGid) { this.open(srcGid); if (this._onNodeActivate) this._onNodeActivate(srcGid); }
        });
      });
    } catch { area.innerHTML = ''; }
  }

  // ── 列2：关系（本体驱动，最终生效版本） ─────────────────────────────────────

  async _renderRels(gid, mountEl = this._relsBody) {
    if (!mountEl) return;
    mountEl.innerHTML = '<div style="color:var(--surface2);font-size:11px;padding:8px">加载中…</div>';
    const data = this._getLineageData();
    const lineGrantSet = data?.lineGrantSet || new Set();
    const lineReadOnly = !!data?.lineReadOnly;
    const row = data?.rowByGid?.get(gid);
    const currentLineGid = this._findAncestorOfType(gid, 'line_process', data?.rowByGid) || (row?.node_type === 'line_process' ? row.gid : null);
    const canEditCurrentLine = !lineReadOnly || !currentLineGid || lineGrantSet.has(currentLineGid);
    const hasChildren = data ? (data.childMap.get(gid) || []).filter(r => !r.is_deleted).length > 0 : false;

    let links = [];
    try {
      const resp = await this._cf(
        `/api/bop/entry-links?entry_gid=${encodeURIComponent(gid)}${hasChildren ? '&recursive=true' : ''}`
      );
      links = resp?.data || [];
    } catch {}
    this._relLinks = links;

    const childRows = data ? (data.childMap.get(gid) || []).filter(r => !r.is_deleted) : [];

    // 每次切换节点都重新加载本体 schema（不同 node_type 有不同关系定义）
    if (row?.node_type) {
      try {
        const schemaResp = await this._cf(`/api/ontology/schema/${encodeURIComponent(row.node_type)}`);
        this._hiddenLinkTypes = new Set(
          (schemaResp?.relations || [])
            .filter(r => r.show_in_detail === false)
            .map(r => r.link_type_binding)
        );
        this._relationConfigByLinkType = new Map(
          (schemaResp?.relations || [])
            .filter(r => r.link_type_binding)
            .map(r => [r.link_type_binding, r])
        );
      } catch {}
    }

    const relationConfigs = Array.from(this._relationConfigByLinkType?.values() || [])
      .filter(r => r.link_type_binding && r.show_in_detail !== false)
      .sort((a, b) => (a.sort_order ?? 99) - (b.sort_order ?? 99) || String(a.label_zh || a.name || '').localeCompare(String(b.label_zh || b.name || '')));

    const groups = [
      { key: 'child', name: '子节点', ntType: 'process', linkTypes: null, linkType: null },
      ...relationConfigs.map(r => ({
        key: `link:${r.link_type_binding}`,
        name: r.label_zh || r.name || r.link_type_binding,
        ntType: r.range_node_type || 'process',
        linkTypes: [r.link_type_binding],
        linkType: r.link_type_binding,
        relation: r,
      })),
    ];
    this._currentRelGroups = groups;

    let html = '';
    for (const grp of groups) {
      let items = [];
      if (grp.key === 'child') {
        items = childRows.map(r => ({
          _key: 'child', _title: r.title || r.gid, _badge: r.node_type,
          _ntType: r.node_type || 'process',
          _row: r, _sourceGid: gid, _sourceTitle: null,
          link: { link_type: 'child', entity_gid: r.gid }, source_entry_gid: gid, source_entry_title: null,
        }));
      } else {
        items = links
          .filter(l => grp.linkTypes.includes(l.link_type))
          .map(l => ({
            _key: grp.key, _title: l.entity_title || l.entity_gid, _badge: l.link_type,
            _ntType: grp.ntType, link: l,
            source_entry_gid: l.source_entry_gid || gid,
            source_entry_title: l.source_entry_title,
          }));
      }

      const isOpen = !items.length ? false : true;
      const addSupported = grp.key === 'child' || !!grp.linkType;
      html += `
        <div class="ll-rg">
          <div class="ll-rg-hdr" data-key="${_he(grp.key)}">
            <span class="ll-rg-tog">${isOpen ? '▼' : '▶'}</span>
            <span class="lv-nt-dot lv-nt-${_he(grp.ntType)}"></span>
            <span class="ll-rg-name">${_he(grp.name)}</span>
            <span class="ll-rg-cnt">${items.length}</span>
            <button class="ll-rg-add" data-key="${_he(grp.key)}" title="${_he(addSupported ? `添加${grp.name}` : `${grp.name} 暂不支持在此处新增`)}"${canEditCurrentLine && addSupported ? '' : ' disabled style="opacity:.45;cursor:not-allowed"'}>＋</button>
          </div>
          <div class="ll-rg-items${isOpen ? ' open' : ''}">
            ${items.length ? items.map((item, idx) => {
              const fromOther = item.source_entry_gid && item.source_entry_gid !== gid;
              return `
                <div class="ll-ri" data-key="${_he(grp.key)}" data-idx="${idx}">
                  <span class="lv-nt-dot lv-nt-${_he(item._ntType || 'process')}"></span>
                  <span class="ll-ri-title">${_he(item._title || item.link?.entity_gid || '—')}</span>
                  <span class="ll-ri-badge ${_statusBadgeClass(item._badge)}">${_he(item._badge || '')}</span>
                </div>
                ${fromOther ? `<div class="ll-ri-src" data-src-gid="${_he(item.source_entry_gid)}">来自：${_he(item.source_entry_title || item.source_entry_gid)}</div>` : ''}`;
            }).join('') : `<div class="ll-rg-empty">暂无关联${grp.key === 'child' ? '，点击 ＋ 添加' : ''}</div>`}
          </div>
        </div>`;
    }
    mountEl.innerHTML = html;

    mountEl.querySelectorAll('.ll-rg-hdr').forEach(hdr => {
      hdr.addEventListener('click', e => {
        if (e.target.classList.contains('ll-rg-add')) return;
        const wrap = hdr.nextElementSibling;
        const open = wrap.classList.contains('open');
        wrap.classList.toggle('open', !open);
        hdr.querySelector('.ll-rg-tog').textContent = !open ? '▼' : '▶';
      });
    });

    mountEl.querySelectorAll('.ll-ri').forEach(ri => {
      ri.addEventListener('click', () => {
        mountEl.querySelectorAll('.ll-ri').forEach(r => r.classList.remove('sel'));
        ri.classList.add('sel');
        const key = ri.dataset.key;
        const idx = parseInt(ri.dataset.idx);
        const grp = groups.find(g => g.key === key);
        if (!grp) return;

        if (key === 'child') {
          const childItems = childRows.map(r => ({
            _key: 'child', _title: r.title || r.gid, _row: r,
            source_entry_gid: gid, source_entry_title: null, link: { link_type: 'child', entity_gid: r.gid },
          }));
          this._openViewDetail(childItems[idx], gid);
        } else {
          const grpLinks = links.filter(l => grp.linkTypes.includes(l.link_type))
            .map(l => ({ _key: key, _title: l.entity_title || l.entity_gid, link: l,
              source_entry_gid: l.source_entry_gid || gid, source_entry_title: l.source_entry_title }));
          this._openViewDetail(grpLinks[idx], gid);
        }
      });
    });

    mountEl.querySelectorAll('.ll-ri-src').forEach(src => {
      src.addEventListener('click', () => {
        const srcGid = src.dataset.srcGid;
        if (srcGid) this.open(srcGid);
      });
    });

    mountEl.querySelectorAll('.ll-rg-add').forEach(btn => {
      btn.addEventListener('click', e => {
        e.stopPropagation();
        if (btn.disabled) return;
        if (!canEditCurrentLine) {
          this._toast?.('当前线体无编辑权限（只读）', 'warn');
          return;
        }
        const key = btn.dataset.key;
        const grp = groups.find(g => g.key === key);
        if (!grp) return;
        const currentRow = this._currentRow;
        if (key === 'child') {
          const childInfo = CHILD_TYPE_MAP[currentRow?.node_type || null];
          this._openAddDetail(key, gid, childInfo?.type, childInfo?.label || '子节点');
        } else {
          this._openAddDetail(key, gid, grp.linkType, grp.name);
        }
      });
    });
  }
}
