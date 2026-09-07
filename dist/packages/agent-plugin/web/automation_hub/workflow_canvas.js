/**
 * web/automation_hub/workflow_canvas.js
 * WorkflowCanvas — 工作流画布核心类
 *
 * 功能：
 *   - 节点（6种类型）的拖拽创建、移动、删除
 *   - 泳道管理（添加/删除/重命名）
 *   - 连线（control/dataflow）绘制与删除
 *   - Q&A 双列（问题+回答）与节点双向绑定
 *   - 序列化/反序列化 JSON，localStorage 持久化
 *   - 注入文本生成（toInjectText）
 *   - generate_canvas tool 的 fromJSON 接口
 */

/* ── 节点类型定义 ─────────────────────────────────────────────────────────── */
const WFC_NODE_TYPES = {
  // ── 执行者 ──────────────────────────────────────────────────────────────
  agent: {
    label: 'AI Agent', badgeText: 'AGENT', group: '执行者',
    defaultParams: { agent_name: '小柔', note: '' },
  },
  human: {
    label: '邀请人参与', badgeText: 'HUMAN', group: '执行者',
    defaultParams: { assignee: '', task_desc: '' },
  },
  // ── 操作 ────────────────────────────────────────────────────────────────
  tool_read: {
    label: '工具调用（读）', badgeText: 'TOOL·R', group: '操作',
    defaultParams: { tool_name: '', params_hint: '' },
  },
  tool_write: {
    label: '工具调用（写）', badgeText: 'TOOL·W', group: '操作',
    defaultParams: { tool_name: '', confirm_required: 'true' },
  },
  skill_call: {
    label: '技能调用', badgeText: 'SC', group: '操作',
    defaultParams: { skill_gid: '', skill_name: '' },
  },
  fork: {
    label: '并行分流', badgeText: '///', group: '操作',
    defaultParams: { branches: '2', note: '' },
  },
  join: {
    label: '并行合流', badgeText: '\\\\\\', group: '操作',
    defaultParams: { strategy: 'all', note: '' },
  },
  condition: {
    label: '条件判断', badgeText: '?', group: '操作',
    defaultParams: { condition_expr: '', true_branch: '', false_branch: '' },
  },
  // ── 数据 ────────────────────────────────────────────────────────────────
  list: {
    label: '清单/数据源', badgeText: 'LIST', group: '数据',
    defaultParams: { domain: '', list_gid: '', item_query: '' },
  },
  data_db: {
    label: '数据库表', badgeText: 'DB', group: '数据',
    defaultParams: { table: '', db: 'postgres', access: 'read' },
  },
  data_mem: {
    label: '上下文变量', badgeText: 'MEM', group: '数据',
    defaultParams: { var_name: '', scope: 'session' },
  },
  data_file: {
    label: '文件/快照', badgeText: 'FILE', group: '数据',
    defaultParams: { path: '', format: 'json' },
  },
  // ── 兼容旧节点（human_approval / human_task 仍可被反序列化） ─────────────
  human_approval: {
    label: '人工审批', badgeText: '审批', group: '执行者',
    defaultParams: { approver: '', note: '' },
  },
  human_task: {
    label: '人工执行', badgeText: '人工', group: '执行者',
    defaultParams: { assignee: '', task_desc: '' },
  },
  // ── 注入型结果节点（由执行器动态注入，不在 palette 中显示） ──────────────
  result_list: {
    label: '结果列表', badgeText: 'RESULT', group: '执行者',
    defaultParams: { _items: [] },
  },
};

const WFC_PALETTE_GROUPS = [
  { id: '执行者', label: '执行者', types: ['agent', 'human'] },
  { id: '操作',   label: '操作',   types: ['tool_read', 'tool_write', 'skill_call', 'fork', 'join', 'condition'] },
  { id: '数据',   label: '数据',   types: ['list', 'data_db', 'data_mem', 'data_file'] },
];

/* ── WorkflowCanvas 类 ────────────────────────────────────────────────────── */
// localStorage 账号隔离
function _wfcLsk(base) {
  try { const u = window._authUser || window.parent?._authUser || window.top?._authUser; const g = u?.gid || u?.user_gid || ''; return g ? `${g}:${base}` : base; } catch { return base; }
}
class WorkflowCanvas {
  constructor(opts = {}) {
    this._boardEl   = opts.boardEl;
    this._paletteEl = opts.paletteEl;
    this._svgEl     = opts.svgEl;
    this._lanesEl   = opts.lanesEl;
    this._qaQEl     = opts.qaQEl;
    this._qaAEl     = opts.qaAEl;
    this._footerEl  = opts.footerEl;
    this._statsEl   = opts.statsEl;

    this._nodes      = [];      // { id, type, label, laneIdx, step, params, x, y, el }
    this._conns      = [];      // { id, fromId, toId, type, groupEl }
    this._lanes      = [];      // { id, label, el, cellsEl }
    this._questions  = [];      // { id, nodeId, text, answer, qEl, aEl }
    this._steps      = 5;       // 初始步骤列数
    this._stepLabels = [];      // 自定义列标题（空=用「步骤 N」）

    this._hideStepHeaders = false; // 交互模式下隐藏列表头行
    this._hideLaneLabels  = false; // 交互模式下隐藏泳道标签列

    this._selectedNodeId  = null;
    this._connectingFrom  = null; // port drag → { nodeId, portEl }
    this._tempConnEl      = null;
    this._mode            = 'explore';
    this._nextId          = 1;

    this._nodeResults = {};   // nodeId → { status, count?, preview?, error?, ts }

    this._popoverEl    = null;
    this._connCtxEl    = null;
    this._savesOverlay = null;

    // 可选事件回调（供独立画布窗口使用）
    this._onNodeAdded    = opts.onNodeAdded    || null;
    this._onNodeRemoved  = opts.onNodeRemoved  || null;
    this._onNodeSelected = opts.onNodeSelected || null;

    // 人工审批回调：(nodeId, approved, userData) => void
    this._onHumanApprovalAction = opts.onHumanApprovalAction || null;
    // 审批表单选项加载回调：(tool_name, params) => Promise<{options:[{value,label}]}>
    this._fetchApprovalOptions  = opts.fetchApprovalOptions  || null;
  }

  /* ── 初始化 ────────────────────────────────────────────────────────────── */
  init() {
    this._renderPalette();
    this._renderStepHeaders();
    this._addLane('主流程');
    this._bindGlobalEvents();
    // 底部容器：标签栏 + 沙盘
    this._bottomCtxEvents = [];
    this._initBottomTabs();
    this._initSandbox();
  }

  _genId(prefix = 'n') { return `${prefix}${Date.now()}_${this._nextId++}`; }

  /* ── 节点库渲染 ───────────────────────────────────────────────────────── */
  _renderPalette() {
    const pinnedEl = this._paletteEl.querySelector('#wfcPinned') || this._paletteEl;
    const groupsEl = this._paletteEl.querySelector('#wfcGroups') || this._paletteEl;
    pinnedEl.innerHTML = '';
    groupsEl.innerHTML = '';

    // ── 沙盘模式：渲染沙盘节点类型库 ──────────────────────────────────────
    if (this._sandboxMode) {
      const GROUPS = { bop: 'BOP', flow: '流程', misc: '通用' };
      Object.entries(GROUPS).forEach(([groupKey, groupLabel]) => {
        const types = Object.entries(WFC_SANDBOX_NODE_TYPES)
          .filter(([, def]) => def.group === groupKey);
        if (!types.length) return;
        const groupDiv = document.createElement('div');
        groupDiv.className = 'wfc-palette-group';
        const hdr = document.createElement('div');
        hdr.className = 'wfc-palette-group-hdr';
        hdr.innerHTML = `<span class="wfc-pg-arrow">▾</span>${groupLabel}`;
        hdr.addEventListener('click', () => groupDiv.classList.toggle('collapsed'));
        const itemsEl = document.createElement('div');
        itemsEl.className = 'wfc-palette-items';
        types.forEach(([typeId, def]) => {
          const item = document.createElement('div');
          item.className = 'wfc-palette-item';
          item.draggable = true;
          item.dataset.type = typeId;
          item.innerHTML = `<span class="wfc-badge wfc-badge-${typeId}">${def.badge}</span>${def.label}`;
          item.addEventListener('dragstart', e => {
            e.dataTransfer.setData('wfc-sandbox-node-type', typeId);
          });
          item.addEventListener('dblclick', () => {
            const x = 60 + ((this._sandboxNodes || []).length % 5) * 20;
            const y = 60 + ((this._sandboxNodes || []).length % 8) * 40;
            this._addSandboxNode?.(typeId, x, y);
          });
          itemsEl.appendChild(item);
        });
        groupDiv.appendChild(hdr);
        groupDiv.appendChild(itemsEl);
        groupsEl.appendChild(groupDiv);
      });
      // 更新右边栏标题（仅 wfc_window 场景存在此元素）
      const rsTitle = document.getElementById('wfcwRsTitle');
      if (rsTitle) rsTitle.textContent = '沙盘卡片库';
      return;
    }

    // ── 流程图模式：已 pin 的常用节点 + 分组 ──────────────────────────────
    const pinnedKey = _wfcLsk('wfc:pinned');
    const pinned = JSON.parse(localStorage.getItem(pinnedKey) || '[]');

    // 已 pin 的常用节点
    pinned.forEach(typeId => {
      const def = WFC_NODE_TYPES[typeId];
      if (!def) return;
      pinnedEl.appendChild(this._makePaletteItem(typeId, def, true));
    });

    // 分组
    WFC_PALETTE_GROUPS.forEach(group => {
      const groupDiv = document.createElement('div');
      groupDiv.className = 'wfc-palette-group';
      const hdr = document.createElement('div');
      hdr.className = 'wfc-palette-group-hdr';
      hdr.innerHTML = `<span class="wfc-pg-arrow">▾</span>${group.label}`;
      hdr.addEventListener('click', () => groupDiv.classList.toggle('collapsed'));

      const itemsEl = document.createElement('div');
      itemsEl.className = 'wfc-palette-items';

      group.types.forEach(typeId => {
        const def = WFC_NODE_TYPES[typeId];
        if (!def) return;
        itemsEl.appendChild(this._makePaletteItem(typeId, def, false, pinned, pinnedKey));
      });

      groupDiv.appendChild(hdr);
      groupDiv.appendChild(itemsEl);
      groupsEl.appendChild(groupDiv);
    });

    // 更新右边栏标题
    const rsTitle = document.getElementById('wfcwRsTitle');
    if (rsTitle) rsTitle.textContent = '节点库';
  }

  _makePaletteItem(typeId, def, isPinned, pinnedArr, pinnedKey) {
    const item = document.createElement('div');
    item.className = 'wfc-palette-item';
    item.draggable = true;
    item.dataset.type = typeId;
    item.innerHTML = `<span class="wfc-badge wfc-badge-${typeId}">${def.badgeText}</span>${def.label}`;

    // pin/unpin 按钮
    const pinBtn = document.createElement('button');
    pinBtn.className = 'wfc-palette-item-pin';
    pinBtn.title = isPinned ? '取消常用' : '设为常用';
    pinBtn.textContent = isPinned ? '★' : '☆';
    pinBtn.addEventListener('click', e => {
      e.stopPropagation();
      const key = _wfcLsk('wfc:pinned');
      const arr = JSON.parse(localStorage.getItem(key) || '[]');
      const idx = arr.indexOf(typeId);
      if (idx >= 0) arr.splice(idx, 1); else arr.push(typeId);
      localStorage.setItem(key, JSON.stringify(arr));
      this._renderPalette();
    });
    item.appendChild(pinBtn);

    // drag start
    item.addEventListener('dragstart', e => {
      e.dataTransfer.setData('wfc-node-type', typeId);
    });
    return item;
  }

  /* ── 步骤列头 ─────────────────────────────────────────────────────────── */
  _renderStepHeaders() {
    let hdrRow = this._lanesEl.querySelector('.wfc-step-headers');
    if (!hdrRow) {
      hdrRow = document.createElement('div');
      hdrRow.className = 'wfc-step-headers';
      this._lanesEl.insertBefore(hdrRow, this._lanesEl.firstChild);
    }
    // 交互模式：隐藏整行列标题
    if (this._hideStepHeaders) {
      hdrRow.style.display = 'none';
      // 最小宽度仍按列数计算，保持布局稳定
      const stepW = parseFloat(
        getComputedStyle(document.documentElement).getPropertyValue('--canvas-step-w')
      ) || 140;
      this._lanesEl.style.minWidth = (this._steps * stepW) + 'px';
      return;
    }
    hdrRow.style.display = '';
    // 有泳道标签时留 spacer，无泳道标签时跳过 spacer 节省横向空间
    hdrRow.innerHTML = this._hideLaneLabels ? '' : `<div class="wfc-step-hdr-spacer"></div>`;
    for (let i = 1; i <= this._steps; i++) {
      const h = document.createElement('div');
      h.className = 'wfc-step-hdr';
      h.textContent = this._stepLabels[i - 1] || `步骤 ${i}`;
      hdrRow.appendChild(h);
    }
    // + 添加步骤按钮
    const addBtn = document.createElement('div');
    addBtn.className = 'wfc-step-hdr';
    addBtn.style.cssText = 'cursor:pointer;color:var(--accent);border-style:dashed';
    addBtn.textContent = '+ 步骤';
    addBtn.title = '添加步骤列';
    addBtn.addEventListener('click', () => { this._steps++; this._refreshStepsAndLanes(); });
    hdrRow.appendChild(addBtn);

    // 动态更新泳道容器最小宽度，确保所有列可见
    const stepW = parseFloat(
      getComputedStyle(document.documentElement).getPropertyValue('--canvas-step-w')
    ) || 140;
    const spacerW = this._hideLaneLabels ? 0 : 72;
    this._lanesEl.style.minWidth = (spacerW + (this._steps + 1) * stepW) + 'px';
  }

  _refreshStepsAndLanes() {
    this._renderStepHeaders();
    this._lanes.forEach((lane, idx) => this._refreshLaneCells(idx));
    this._redrawConnections();
  }

  /* ── 泳道操作 ─────────────────────────────────────────────────────────── */
  addLane(label = '') { return this._addLane(label); }

  _addLane(label = `泳道 ${this._lanes.length + 1}`) {
    const id = this._genId('lane');
    const laneEl = document.createElement('div');
    laneEl.className = 'wfc-lane';
    laneEl.dataset.laneId = id;

    // 泳道标签
    const labelEl = document.createElement('div');
    labelEl.className = 'wfc-lane-label';
    if (this._hideLaneLabels) labelEl.style.display = 'none';
    const labelInput = document.createElement('textarea');
    labelInput.className = 'wfc-lane-label-input';
    labelInput.value = label;
    labelInput.rows = 2;
    labelInput.addEventListener('change', () => {
      const lane = this._lanes.find(l => l.id === id);
      if (lane) lane.label = labelInput.value;
    });
    labelEl.appendChild(labelInput);
    laneEl.appendChild(labelEl);

    // 单元格区
    const cellsEl = document.createElement('div');
    cellsEl.className = 'wfc-lane-cells';
    laneEl.appendChild(cellsEl);

    // 添加泳道按钮（最后泳道之后）
    const addLaneBtn = this._lanesEl.querySelector('.wfc-add-lane');
    if (addLaneBtn) {
      this._lanesEl.insertBefore(laneEl, addLaneBtn);
    } else {
      this._lanesEl.appendChild(laneEl);
    }

    const laneObj = { id, label, el: laneEl, cellsEl };
    this._lanes.push(laneObj);
    this._refreshLaneCells(this._lanes.length - 1);
    this._updateStats();
    return laneObj;
  }

  _refreshLaneCells(laneIdx) {
    const lane = this._lanes[laneIdx];
    if (!lane) return;
    lane.cellsEl.innerHTML = '';
    for (let s = 1; s <= this._steps; s++) {
      const cell = document.createElement('div');
      cell.className = 'wfc-lane-cell';
      cell.dataset.laneIdx = laneIdx;
      cell.dataset.step = s;

      // Drop target
      cell.addEventListener('dragover', e => {
        e.preventDefault();
        cell.classList.add('drop-active');
      });
      cell.addEventListener('dragleave', () => cell.classList.remove('drop-active'));
      cell.addEventListener('drop', e => {
        e.preventDefault();
        cell.classList.remove('drop-active');
        const typeId = e.dataTransfer.getData('wfc-node-type');
        const nodeId = e.dataTransfer.getData('wfc-move-id');
        if (typeId) {
          const rect = cell.getBoundingClientRect();
          const x = e.clientX - rect.left - 58;
          const y = e.clientY - rect.top - 28;
          const nodeParamsRaw = e.dataTransfer.getData('wfc-node-params');
          let preParams = {};
          try { preParams = nodeParamsRaw ? JSON.parse(nodeParamsRaw) : {}; } catch (_) {}
          this._addNodeToCell(typeId, laneIdx, s, Math.max(2, x), Math.max(2, y), preParams);
        } else if (nodeId) {
          const node = this._nodes.find(n => n.id === nodeId);
          if (node) {
            node.laneIdx = laneIdx;
            node.step = s;
            const rect = cell.getBoundingClientRect();
            node.x = Math.max(2, e.clientX - rect.left - 58);
            node.y = Math.max(2, e.clientY - rect.top - 28);
            cell.appendChild(node.el);
            node.el.style.left = node.x + 'px';
            node.el.style.top  = node.y + 'px';
            this._redrawConnections();
          }
        }
      });
      lane.cellsEl.appendChild(cell);
    }

    // 重新放置该泳道的节点
    this._nodes.filter(n => n.laneIdx === laneIdx).forEach(n => {
      const cell = lane.cellsEl.querySelector(`[data-step="${n.step}"]`);
      if (cell) {
        cell.appendChild(n.el);
        n.el.style.left = n.x + 'px';
        n.el.style.top  = n.y + 'px';
      }
    });
  }

  removeLane(idx) {
    const lane = this._lanes[idx];
    if (!lane || this._lanes.length <= 1) return;
    // 删除该泳道所有节点
    const toRemove = this._nodes.filter(n => n.laneIdx === idx).map(n => n.id);
    toRemove.forEach(id => this.removeNode(id));
    lane.el.remove();
    this._lanes.splice(idx, 1);
    // 修正 laneIdx
    this._nodes.forEach(n => { if (n.laneIdx > idx) n.laneIdx--; });
    this._redrawConnections();
    this._updateStats();
  }

  /* ── 节点操作 ─────────────────────────────────────────────────────────── */
  _addNodeToCell(typeId, laneIdx, step, x = 6, y = 6, preParams = {}) {
    const def = WFC_NODE_TYPES[typeId];
    if (!def) return null;
    const id = this._genId('n');
    const params = Object.assign(JSON.parse(JSON.stringify(def.defaultParams)), preParams);
    // 从 preParams 中提取预填 label（工具名/skill标题）
    const label = preParams.name || preParams.skill_title || def.label;
    const nodeObj = { id, type: typeId, label, laneIdx, step, params, x, y, el: null };
    nodeObj.el = this._buildNodeEl(nodeObj);
    this._nodes.push(nodeObj);

    const lane = this._lanes[laneIdx];
    if (lane) {
      const cell = lane.cellsEl.querySelector(`[data-step="${step}"]`);
      if (cell) {
        cell.appendChild(nodeObj.el);
        nodeObj.el.style.left = x + 'px';
        nodeObj.el.style.top  = y + 'px';
      }
    }
    this._updateStats();
    return nodeObj;
  }

  addNode(type, label, laneIdx = 0, step = 1, params = {}) {
    const def = WFC_NODE_TYPES[type] || {};
    const id = this._genId('n');
    const mergedParams = Object.assign({}, def.defaultParams || {}, params);
    const nodeObj = {
      id, type, label: label || (def.label || type),
      laneIdx, step, params: mergedParams, x: 6, y: 6, el: null,
    };
    nodeObj.el = this._buildNodeEl(nodeObj);
    this._nodes.push(nodeObj);
    this._onNodeAdded?.(nodeObj);

    // 确保有足够泳道和步骤
    while (this._lanes.length <= laneIdx) this._addLane();
    if (step > this._steps) { this._steps = step; this._refreshStepsAndLanes(); }

    const lane = this._lanes[laneIdx];
    if (lane) {
      const cell = lane.cellsEl.querySelector(`[data-step="${step}"]`);
      if (cell) {
        cell.appendChild(nodeObj.el);
        nodeObj.el.style.left = nodeObj.x + 'px';
        nodeObj.el.style.top  = nodeObj.y + 'px';
      }
    }
    this._updateStats();
    return nodeObj;
  }

  _buildNodeEl(nodeObj) {
    const { id, type, label, params } = nodeObj;
    const def = WFC_NODE_TYPES[type] || {};
    const el = document.createElement('div');
    el.className = 'wfc-node';
    el.dataset.nodeId = id;

    // 顶部（徽标+标题+删除）
    const top = document.createElement('div');
    top.className = 'wfc-node-top';
    top.innerHTML = `
      <span class="wfc-badge wfc-badge-${type}">${def.badgeText || type}</span>
      <span class="wfc-node-label">${_escWFC(label)}</span>
      <button class="wfc-node-remove" title="删除节点">
        <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
      </button>`;
    top.querySelector('.wfc-node-remove').addEventListener('click', e => {
      e.stopPropagation();
      this.removeNode(id);
    });
    el.appendChild(top);

    // 参数摘要
    const paramsEl = document.createElement('div');
    paramsEl.className = 'wfc-node-params';
    el.appendChild(paramsEl);
    this._renderNodeParams(nodeObj, paramsEl);

    // Q count badge（有关联问题时显示）
    const qBadge = document.createElement('div');
    qBadge.className = 'wfc-node-q-badge';
    qBadge.style.display = 'none';
    el.appendChild(qBadge);
    nodeObj._qBadge = qBadge;

    // 连线端口（左/右/上/下）
    const portIn = document.createElement('div');
    portIn.className = 'wfc-port wfc-port-in';
    portIn.title = '左侧输入端口';
    const portOut = document.createElement('div');
    portOut.className = 'wfc-port wfc-port-out';
    portOut.title = '右侧输出端口';
    portOut.addEventListener('mousedown', ev => this._startConnect(ev, id, 'out'));
    const portTop = document.createElement('div');
    portTop.className = 'wfc-port wfc-port-top';
    portTop.title = '顶部端口';
    portTop.addEventListener('mousedown', ev => this._startConnect(ev, id, 'top'));
    const portBottom = document.createElement('div');
    portBottom.className = 'wfc-port wfc-port-bottom';
    portBottom.title = '底部端口';
    portBottom.addEventListener('mousedown', ev => this._startConnect(ev, id, 'bottom'));
    el.appendChild(portIn);
    el.appendChild(portOut);
    el.appendChild(portTop);
    el.appendChild(portBottom);
    nodeObj._portIn     = portIn;
    nodeObj._portOut    = portOut;
    nodeObj._portTop    = portTop;
    nodeObj._portBottom = portBottom;

    // 节点拖拽（位置）
    el.addEventListener('mousedown', ev => {
      if (ev.target.classList.contains('wfc-port') ||
          ev.target.classList.contains('wfc-node-remove') ||
          ev.target.closest('button') ||
          ev.target.closest('select') ||
          ev.target.closest('input')) return;
      this._startNodeDrag(ev, nodeObj);
    });

    // 点击选中 + popover（交互节点不弹 popover，避免与表单控件争焦点）
    el.addEventListener('click', ev => {
      if (ev.target.classList.contains('wfc-port') ||
          ev.target.classList.contains('wfc-node-remove')) return;
      this.selectNode(id);
      if (nodeObj.type !== 'human_approval' && nodeObj.type !== 'result_list') {
        this._openNodePopover(nodeObj, el);
      }
    });

    // 右键菜单
    el.addEventListener('contextmenu', ev => {
      ev.preventDefault(); ev.stopPropagation();
      this._showNodeCtxMenu(ev, nodeObj);
    });

    // HTML5 拖拽（跨 cell）
    el.draggable = true;
    el.addEventListener('dragstart', ev => {
      ev.dataTransfer.setData('wfc-move-id', id);
    });

    // 节点执行状态徽标
    const $ns = document.createElement('div');
    $ns.className = 'wfc-node-status';
    $ns.style.display = 'none';
    el.appendChild($ns);

    return el;
  }

  /* ── 节点执行结果状态 ─────────────────────────────────────────────────── */
  setNodeResult(nodeId, result) {
    // result: { status: 'running'|'success'|'error', count?, preview?, error? }
    this._nodeResults[nodeId] = { ...result, ts: Date.now() };
    const node = this._nodes.find(n => n.id === nodeId);
    if (node) this._refreshNodeStatus(node);
  }

  clearNodeResults() {
    this._nodeResults = {};
    this._nodes.forEach(n => this._refreshNodeStatus(n));
  }

  _refreshNodeStatus(node) {
    if (!node.el) return;
    let $s = node.el.querySelector('.wfc-node-status');
    if (!$s) {
      $s = document.createElement('div');
      $s.className = 'wfc-node-status';
      node.el.appendChild($s);
    }
    const r = this._nodeResults[node.id];
    if (!r) { $s.style.display = 'none'; return; }
    $s.style.display = '';
    $s.className = `wfc-node-status wfc-ns-${r.status}`;
    if (r.status === 'running') {
      $s.innerHTML = '<span class="wfc-ns-spin"></span>';
    } else if (r.status === 'success') {
      $s.textContent = r.count != null ? `${r.count}条` : '✓';
    } else if (r.status === 'warning') {
      $s.textContent = r.count != null ? `⚠ ${r.count}` : '⚠';
      $s.title = r.preview || '有警告项';
    } else if (r.status === 'error') {
      $s.textContent = '!'; $s.title = r.error || '出错';
    }

    // 数据节点：在 params 行展示预览
    const DATA_TYPES = new Set(['data_db', 'data_mem', 'list', 'data_file']);
    if (DATA_TYPES.has(node.type)) {
      const $p = node.el.querySelector('.wfc-node-params');
      if ($p) {
        if (r.status === 'success' && r.count != null) {
          $p.dataset.orig = $p.dataset.orig || $p.textContent;
          $p.textContent  = `→ ${r.count} 条`;
          $p.style.color  = 'var(--green, #a6e3a1)';
        } else if (r.status !== 'running') {
          if ($p.dataset.orig) { $p.textContent = $p.dataset.orig; $p.style.color = ''; }
        }
      }
    }
  }

  _renderNodeParams(nodeObj, paramsEl) {
    if (!paramsEl) {
      paramsEl = nodeObj.el?.querySelector('.wfc-node-params');
    }
    if (!paramsEl) return;

    // result_list 节点：渲染结构化列表
    if (nodeObj.type === 'result_list') {
      const items = nodeObj.params?._items || [];
      if (!items.length) {
        paramsEl.innerHTML = '<div class="wfc-rl-empty">（无数据）</div>';
        return;
      }
      paramsEl.innerHTML = `<div class="wfc-rl-list">${
        items.map(it => `<div class="wfc-rl-item wfc-rl-${_escWFC(it.level || 'info')}">
          <span class="wfc-rl-label">${_escWFC(it.label || '')}</span>
          <span class="wfc-rl-desc">${_escWFC(it.desc || '')}</span>
        </div>`).join('')
      }</div>`;
      return;
    }

    // 人工审批节点：有 _pause_token 时渲染审批 UI
    if ((nodeObj.type === 'human_approval' || nodeObj.type === 'human') &&
        nodeObj.params._pause_token) {
      // 已渲染过则只更新 context 文本，不重建
      if (paramsEl.dataset.approvalRendered) return;
      paramsEl.dataset.approvalRendered = '1';
      paramsEl.innerHTML = '';
      this._buildApprovalUI(nodeObj, paramsEl);
      return;
    }

    // 默认：取第一个有意义的参数值作为单行摘要
    const SKIP_DEFAULTS = new Set(['false', 'true', 'read', 'write', 'all', 'postgres', 'session', 'json', '2']);
    const desc = Object.values(nodeObj.params || {})
      .find(v => v && typeof v === 'string' && !SKIP_DEFAULTS.has(v) && !v.startsWith('_')) || '';
    paramsEl.textContent = String(desc).slice(0, 28) || '';
  }

  /* ── 人工审批节点 UI ────────────────────────────────────────────────────── */
  _buildApprovalUI(nodeObj, paramsEl) {
    const p = nodeObj.params;

    // context 摘要
    if (p._context) {
      const note = document.createElement('div');
      note.className = 'wfc-approval-context';
      note.textContent = String(p._context).slice(0, 120);
      paramsEl.appendChild(note);
    }

    // collect_fields 表单
    let collectFields = [];
    try { collectFields = JSON.parse(p._collect_fields || '[]'); } catch (_) {}
    const formEl = collectFields.length ? this._buildApprovalForm(nodeObj, collectFields) : null;
    if (formEl) paramsEl.appendChild(formEl);

    // 确认 / 拒绝 按钮
    const btns = document.createElement('div');
    btns.className = 'wfc-approval-btns';

    const btnOk = document.createElement('button');
    btnOk.className = 'wfc-approval-btn wfc-approval-ok';
    btnOk.innerHTML = '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg> 确认';

    const btnNo = document.createElement('button');
    btnNo.className = 'wfc-approval-btn wfc-approval-reject';
    btnNo.innerHTML = '<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg> 拒绝';

    const fire = (approved) => {
      btns.remove();
      const done = document.createElement('div');
      done.className = 'wfc-approval-done ' + (approved ? 'wfc-approval-done-ok' : 'wfc-approval-done-no');
      done.textContent = approved ? '✓ 已确认' : '✗ 已拒绝';
      paramsEl.appendChild(done);
      // 收集 userData（来自 formEl 中的字段）
      const userData = {};
      if (approved && formEl) {
        formEl.querySelectorAll('[data-field-key]').forEach(el => {
          if (el.tagName === 'SELECT' && el.value) userData[el.dataset.fieldKey] = el.value;
          if (el.tagName === 'INPUT' && el.type === 'radio' && el.checked) userData[el.dataset.fieldKey] = el.value;
        });
        formEl.querySelectorAll('.wfc-approval-checklist[data-type="select_multi"]').forEach(el => {
          const checked = [...el.querySelectorAll('input[type=checkbox]:checked')].map(c => c.value);
          if (checked.length) userData[el.dataset.key] = checked;
        });
      }
      this._onHumanApprovalAction?.(nodeObj.id, approved, userData);
    };

    btnOk.addEventListener('click', e => { e.stopPropagation(); fire(true);  });
    btnNo.addEventListener('click', e => { e.stopPropagation(); fire(false); });
    btns.append(btnOk, btnNo);
    paramsEl.appendChild(btns);
  }

  _buildApprovalForm(nodeObj, fields) {
    const form = document.createElement('div');
    form.className = 'wfc-approval-form';

    fields.forEach(field => {
      const row = document.createElement('div');
      row.className = 'wfc-approval-field';
      if (field.show_when) row.dataset.showWhen = JSON.stringify(field.show_when);

      const lbl = document.createElement('label');
      lbl.className = 'wfc-approval-field-label';
      lbl.textContent = field.label || field.key;
      row.appendChild(lbl);

      if (field.type === 'radio' && Array.isArray(field.options)) {
        const grp = document.createElement('div');
        grp.className = 'wfc-approval-radio-grp';
        field.options.forEach(opt => {
          const lb = document.createElement('label');
          const inp = document.createElement('input');
          inp.type = 'radio'; inp.name = nodeObj.id + '_' + field.key;
          inp.value = opt.value; inp.dataset.fieldKey = field.key;
          if (opt.value === field.default) inp.checked = true;
          inp.addEventListener('change', () => this._updateApprovalFormVisibility(form));
          lb.append(inp, document.createTextNode(' ' + opt.label));
          grp.appendChild(lb);
        });
        row.appendChild(grp);
      } else if (field.type === 'select_multi') {
        const $list = document.createElement('div');
        $list.className = 'wfc-approval-checklist';
        $list.dataset.key = field.key;
        $list.dataset.type = 'select_multi';
        $list.innerHTML = '<div class="wfc-approval-loading">加载中…</div>';
        row.appendChild($list);

        const _fillChecklist = (opts) => {
          $list.innerHTML = (opts || []).map(o =>
            `<label class="wfc-approval-chk-item">` +
            `<input type="checkbox" value="${_escWFC(o.value)}"> ${_escWFC(o.label)}` +
            `</label>`
          ).join('') || '<div class="wfc-approval-loading">（无选项）</div>';
        };

        // 立即加载：优先使用 _resolved_source_param，降级 source_tool
        const resolvedParams = field._resolved_source_param || null;
        if (field.source_tool && this._fetchApprovalOptions && resolvedParams) {
          this._fetchApprovalOptions(field.source_tool, resolvedParams)
            .then(res => _fillChecklist(res.options || []))
            .catch(() => { $list.innerHTML = '<div class="wfc-approval-loading">加载失败</div>'; });
        } else if (field.source_tool && this._fetchApprovalOptions && !field.depends_on) {
          this._fetchApprovalOptions(field.source_tool, {})
            .then(res => _fillChecklist(res.options || []))
            .catch(() => { $list.innerHTML = '<div class="wfc-approval-loading">加载失败</div>'; });
        } else {
          $list.innerHTML = '';
        }
      } else {
        const sel = document.createElement('select');
        sel.className = 'wfc-approval-select';
        sel.dataset.fieldKey = field.key;
        if (field.depends_on) sel.dataset.dependsOn = field.depends_on;
        sel.innerHTML = '<option value="">加载中…</option>';
        row.appendChild(sel);

        // 加载选项：优先使用 _resolved_source_param
        const resolvedParams = field._resolved_source_param || null;
        if (field.source_tool && this._fetchApprovalOptions && resolvedParams) {
          this._fetchApprovalOptions(field.source_tool, resolvedParams).then(res => {
            sel.innerHTML = '<option value="">请选择…</option>' +
              (res.options || []).map(o => `<option value="${_escWFC(o.value)}">${_escWFC(o.label)}</option>`).join('');
          }).catch(() => { sel.innerHTML = '<option value="">加载失败</option>'; });
        } else if (field.source_tool && !field.depends_on && this._fetchApprovalOptions) {
          this._fetchApprovalOptions(field.source_tool, {}).then(res => {
            sel.innerHTML = '<option value="">请选择…</option>' +
              (res.options || []).map(o => `<option value="${_escWFC(o.value)}">${_escWFC(o.label)}</option>`).join('');
          }).catch(() => { sel.innerHTML = '<option value="">加载失败</option>'; });
        } else if (!field.depends_on) {
          sel.innerHTML = '<option value="">请选择…</option>';
        }

        // 级联：当上级改变时刷新
        sel.addEventListener('change', () => {
          const depKey = sel.dataset.fieldKey;
          form.querySelectorAll(`select[data-depends-on="${depKey}"]`).forEach(child => {
            const childField = fields.find(f => f.key === child.dataset.fieldKey);
            if (childField?.source_tool && this._fetchApprovalOptions) {
              child.innerHTML = '<option value="">加载中…</option>';
              const depVals = {};
              depVals[depKey] = sel.value;
              this._fetchApprovalOptions(childField.source_tool, depVals).then(res => {
                child.innerHTML = '<option value="">请选择…</option>' +
                  (res.options || []).map(o => `<option value="${_escWFC(o.value)}">${_escWFC(o.label)}</option>`).join('');
              }).catch(() => { child.innerHTML = '<option value="">加载失败</option>'; });
            }
          });
        });
      }

      form.appendChild(row);
    });

    // 初始化 show_when 可见性
    this._updateApprovalFormVisibility(form);
    return form;
  }

  _updateApprovalFormVisibility(form) {
    // 收集当前 radio 值
    const vals = {};
    form.querySelectorAll('input[type=radio]:checked').forEach(inp => {
      vals[inp.dataset.fieldKey] = inp.value;
    });
    form.querySelectorAll('.wfc-approval-field[data-show-when]').forEach(row => {
      let cond = {};
      try { cond = JSON.parse(row.dataset.showWhen); } catch (_) {}
      const visible = Object.entries(cond).every(([k, v]) => vals[k] === v);
      row.style.display = visible ? '' : 'none';
    });
  }

  removeNode(id) {
    const idx = this._nodes.findIndex(n => n.id === id);
    if (idx < 0) return;
    const node = this._nodes[idx];
    // 删除关联连线
    const connIds = this._conns.filter(c => c.fromId === id || c.toId === id).map(c => c.id);
    connIds.forEach(cid => this.removeConnection(cid));
    // 删除关联问题
    this._questions.filter(q => q.nodeId === id).forEach(q => {
      q.qEl?.remove(); q.aEl?.remove();
    });
    this._questions = this._questions.filter(q => q.nodeId !== id);
    // 取消选中
    if (this._selectedNodeId === id) this._selectedNodeId = null;
    this._onNodeRemoved?.(node);
    node.el?.remove();
    this._nodes.splice(idx, 1);
    this._updateStats();
  }

  selectNode(id) {
    this._nodes.forEach(n => n.el?.classList.remove('selected'));
    this._questions.forEach(q => {
      q.qEl?.classList.remove('active');
      q.aEl?.classList.remove('active');
    });
    this._selectedNodeId = id;
    const node = this._nodes.find(n => n.id === id);
    if (node) node.el?.classList.add('selected');
    // 高亮关联 Q&A
    this._questions.filter(q => q.nodeId === id).forEach(q => {
      q.qEl?.classList.add('active');
      q.aEl?.classList.add('active');
    });
    this._onNodeSelected?.(id, node);
  }

  updateNodeParams(id, params) {
    const node = this._nodes.find(n => n.id === id);
    if (!node) return;
    Object.assign(node.params, params);
    this._renderNodeParams(node);
    // 同步到 Q&A 回答
    this._syncNodeToQa(id);
  }

  /* ── 节点配置 Popover ─────────────────────────────────────────────────── */
  _openNodePopover(nodeObj, anchorEl) {
    this._closePopover();
    const def = WFC_NODE_TYPES[nodeObj.type] || {};
    const pop = document.createElement('div');
    pop.className = 'wfc-popover';
    pop.id = 'wfcNodePopover';

    const title = document.createElement('div');
    title.className = 'wfc-popover-title';
    title.innerHTML = `<span class="wfc-badge wfc-badge-${nodeObj.type}">${def.badgeText || nodeObj.type}</span>${_escWFC(nodeObj.label)}`;
    pop.appendChild(title);

    // 标签名
    const lblRow = document.createElement('div');
    lblRow.className = 'wfc-popover-row';
    lblRow.innerHTML = '<label>节点名称</label>';
    const lblInput = document.createElement('input');
    lblInput.type = 'text'; lblInput.value = nodeObj.label;
    lblRow.appendChild(lblInput);
    pop.appendChild(lblRow);

    // 参数字段
    const paramFields = {};
    Object.entries(nodeObj.params).forEach(([k, v]) => {
      const row = document.createElement('div');
      row.className = 'wfc-popover-row';
      const lbl = document.createElement('label'); lbl.textContent = k;
      const inp = document.createElement('input');
      inp.type = 'text'; inp.value = v;
      paramFields[k] = inp;
      row.appendChild(lbl); row.appendChild(inp);
      pop.appendChild(row);
    });

    // 特殊：list 节点三层选择器
    if (nodeObj.type === 'list') {
      this._buildListPickerRows(pop, nodeObj, paramFields);
    }

    // 底部按钮
    const footer = document.createElement('div');
    footer.className = 'wfc-popover-footer';
    const cancelBtn = document.createElement('button');
    cancelBtn.className = 'wfc-popover-btn wfc-popover-btn-cancel';
    cancelBtn.textContent = '取消';
    cancelBtn.addEventListener('click', () => this._closePopover());
    const saveBtn = document.createElement('button');
    saveBtn.className = 'wfc-popover-btn wfc-popover-btn-save';
    saveBtn.textContent = '确定';
    saveBtn.addEventListener('click', () => {
      nodeObj.label = lblInput.value || nodeObj.label;
      nodeObj.el.querySelector('.wfc-node-label').textContent = nodeObj.label;
      Object.entries(paramFields).forEach(([k, inp]) => {
        nodeObj.params[k] = inp.value;
      });
      this._renderNodeParams(nodeObj);
      this._syncNodeToQa(nodeObj.id);
      this._closePopover();
    });
    footer.appendChild(cancelBtn);
    footer.appendChild(saveBtn);
    pop.appendChild(footer);

    // 定位到节点右侧
    document.body.appendChild(pop);
    this._popoverEl = pop;
    const rect = anchorEl.getBoundingClientRect();
    let left = rect.right + 8;
    let top  = rect.top;
    if (left + 290 > window.innerWidth) left = rect.left - 290 - 8;
    if (top + pop.offsetHeight > window.innerHeight) top = window.innerHeight - pop.offsetHeight - 8;
    pop.style.left = Math.max(4, left) + 'px';
    pop.style.top  = Math.max(4, top)  + 'px';
  }

  _buildListPickerRows(pop, nodeObj, paramFields) {
    // 搜索清单
    const searchInput = paramFields['list_gid'];
    if (!searchInput) return;
    const results = document.createElement('div');
    results.className = 'wfc-lp-results hidden';
    searchInput.parentNode.insertBefore(results, searchInput.nextSibling);

    let _debounceT = null;
    searchInput.addEventListener('input', () => {
      clearTimeout(_debounceT);
      _debounceT = setTimeout(async () => {
        const kw = searchInput.value.trim();
        if (!kw || kw.length < 1) { results.classList.add('hidden'); return; }
        try {
          const r = await window.call_bridge?.('project', 'list_lists', { keyword: kw });
          const lists = r?.lists || [];
          results.innerHTML = '';
          lists.slice(0, 8).forEach(l => {
            const item = document.createElement('div');
            item.className = 'wfc-lp-result-item';
            item.textContent = l.title || l.name || l.gid;
            item.addEventListener('click', () => {
              searchInput.value = l.gid;
              if (paramFields['domain']) paramFields['domain'].value = l.item_type || '';
              results.classList.add('hidden');
            });
            results.appendChild(item);
          });
          results.classList.toggle('hidden', lists.length === 0);
        } catch (_) { results.classList.add('hidden'); }
      }, 300);
    });
  }

  _closePopover() {
    this._popoverEl?.remove();
    this._popoverEl = null;
  }

  /* ── 连线操作 ─────────────────────────────────────────────────────────── */
  addConnection(fromId, toId, type = 'dataflow', fromPort, toPort) {
    if (this._conns.find(c => c.fromId === fromId && c.toId === toId)) return null;
    const id = this._genId('c');
    const connObj = { id, fromId, toId, type, fromPort, toPort, groupEl: null };
    this._conns.push(connObj);
    this._drawConnection(connObj);
    this._updateStats();
    return connObj;
  }

  removeConnection(id) {
    const idx = this._conns.findIndex(c => c.id === id);
    if (idx < 0) return;
    this._conns[idx].groupEl?.remove();
    this._conns.splice(idx, 1);
    this._updateStats();
  }

  _getNodePortCenter(nodeId, port = 'out') {
    const node = this._nodes.find(n => n.id === nodeId);
    if (!node?.el) return null;
    const portEl = { out: node._portOut, in: node._portIn, top: node._portTop, bottom: node._portBottom }[port] || node._portOut;
    if (!portEl) return null;
    const svgRect = this._svgEl.getBoundingClientRect();
    const portRect = portEl.getBoundingClientRect();
    return {
      x: portRect.left + portRect.width / 2  - svgRect.left,
      y: portRect.top  + portRect.height / 2 - svgRect.top,
    };
  }

  _drawConnection(connObj) {
    connObj.groupEl?.remove();

    // 自动按泳道层级决定端口方向（未指定时）
    let fromPort = connObj.fromPort || null;
    let toPort   = connObj.toPort   || null;
    if (!fromPort || !toPort) {
      const fn = this._nodes.find(n => n.id === connObj.fromId);
      const tn = this._nodes.find(n => n.id === connObj.toId);
      if (fn && tn && fn.laneIdx !== tn.laneIdx) {
        fromPort = fn.laneIdx < tn.laneIdx ? 'bottom' : 'top';
        toPort   = fn.laneIdx < tn.laneIdx ? 'top'    : 'bottom';
      } else {
        fromPort = 'out'; toPort = 'in';
      }
    }

    const from = this._getNodePortCenter(connObj.fromId, fromPort);
    const to   = this._getNodePortCenter(connObj.toId,   toPort);
    if (!from || !to) return;

    // 贝塞尔路径：竖向端口用纵向控制点，横向端口用横向控制点
    const isVertical = (fromPort === 'top' || fromPort === 'bottom');
    let d;
    if (isVertical) {
      const dy = (to.y - from.y) * 0.5;
      d = `M${from.x},${from.y} C${from.x},${from.y + dy} ${to.x},${to.y - dy} ${to.x},${to.y}`;
    } else {
      const dx = (to.x - from.x) * 0.5;
      d = `M${from.x},${from.y} C${from.x + dx},${from.y} ${to.x - dx},${to.y} ${to.x},${to.y}`;
    }

    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.dataset.connId = connObj.id;

    // 点击检测宽路径
    const hit = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    hit.setAttribute('d', d);
    hit.setAttribute('class', 'wfc-conn-hit');
    hit.addEventListener('contextmenu', ev => {
      ev.preventDefault(); ev.stopPropagation();
      this._showConnCtxMenu(ev, connObj);
    });
    hit.addEventListener('click', ev => {
      ev.stopPropagation();
      this._showConnCtxMenu(ev, connObj);
    });

    // 实际可见路径
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', d);
    path.setAttribute('class',
      connObj.type === 'dataflow' ? 'wfc-conn-dataflow' : 'wfc-conn-control');

    // 箭头
    const arrowClass = connObj.type === 'dataflow' ? 'wfc-conn-arrow-green' : 'wfc-conn-arrow-control';
    const arrow = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    const ang   = Math.atan2(to.y - from.y, to.x - from.x);
    const len = 6;
    const pts  = [
      [to.x, to.y],
      [to.x - len * Math.cos(ang - 0.4), to.y - len * Math.sin(ang - 0.4)],
      [to.x - len * Math.cos(ang + 0.4), to.y - len * Math.sin(ang + 0.4)],
    ].map(p => p.join(',')).join(' ');
    arrow.setAttribute('points', pts);
    arrow.setAttribute('class', arrowClass);

    g.appendChild(hit);
    g.appendChild(path);
    g.appendChild(arrow);
    this._svgEl.appendChild(g);
    connObj.groupEl = g;
  }

  _redrawConnections() {
    this._conns.forEach(c => this._drawConnection(c));
  }

  /* ── 连线右键菜单 ─────────────────────────────────────────────────────── */
  _showConnCtxMenu(ev, connObj) {
    this._closeConnCtx();
    const menu = document.createElement('div');
    menu.className = 'wfc-conn-ctx';

    const typeLabel   = connObj.type === 'dataflow' ? '数据流（绿色动线）' : '命令流（灰色实线）';
    const switchType  = connObj.type === 'dataflow' ? 'control' : 'dataflow';
    const switchLabel = switchType  === 'dataflow'  ? '切换为数据流' : '切换为命令流';

    [{text: `当前：${typeLabel}`, cls: '', fn: null},
     {text: switchLabel, cls: '', fn: () => { connObj.type = switchType; this._drawConnection(connObj); }},
     {text: '删除连线', cls: 'danger', fn: () => this.removeConnection(connObj.id)},
    ].forEach(item => {
      const el = document.createElement('div');
      el.className = 'wfc-conn-ctx-item' + (item.cls ? ' ' + item.cls : '');
      el.textContent = item.text;
      if (item.fn) el.addEventListener('click', () => { item.fn(); this._closeConnCtx(); });
      else el.style.cursor = 'default';
      menu.appendChild(el);
    });

    menu.style.left = ev.clientX + 4 + 'px';
    menu.style.top  = ev.clientY + 4 + 'px';
    document.body.appendChild(menu);
    this._connCtxEl = menu;
  }

  _closeConnCtx() { this._connCtxEl?.remove(); this._connCtxEl = null; }

  /* ── 节点右键菜单 ─────────────────────────────────────────────────────── */
  _showNodeCtxMenu(ev, nodeObj) {
    this._closeNodeCtx();
    const menu = document.createElement('div');
    menu.className = 'wfc-conn-ctx';
    menu.id = 'wfcNodeCtxMenu';

    const items = [
      { text: '编辑节点', fn: () => this._openNodePopover(nodeObj, nodeObj.el) },
      { text: '删除节点', cls: 'danger', fn: () => this.removeNode(nodeObj.id) },
    ];

    if (nodeObj.type === 'skill_call') {
      items.splice(1, 0, { text: '展开编辑', fn: () => this._expandSkillCallNode(nodeObj) });
    }

    items.forEach(item => {
      const el = document.createElement('div');
      el.className = 'wfc-conn-ctx-item' + (item.cls ? ' ' + item.cls : '');
      el.textContent = item.text;
      el.addEventListener('click', () => { item.fn(); this._closeNodeCtx(); });
      menu.appendChild(el);
    });

    menu.style.left = ev.clientX + 4 + 'px';
    menu.style.top  = ev.clientY + 4 + 'px';
    document.body.appendChild(menu);
    this._nodeCtxEl = menu;
  }

  _closeNodeCtx() { this._nodeCtxEl?.remove(); this._nodeCtxEl = null; }

  async _expandSkillCallNode(nodeObj) {
    const skillGid = nodeObj.params?.skill_gid;
    if (!skillGid) {
      alert('该 skill_call 节点未配置 skill_gid，无法展开');
      return;
    }
    let skill = null;
    try {
      skill = await window.call_bridge?.('skill', 'get_skill', { gid: skillGid });
    } catch (_) {}
    if (!skill) { alert('未找到对应 Skill'); return; }

    let canvasData = null;
    try {
      const content = typeof skill.content === 'string'
        ? JSON.parse(skill.content) : (skill.content || {});
      if (content.canvas) {
        canvasData = typeof content.canvas === 'string'
          ? JSON.parse(content.canvas) : content.canvas;
      }
    } catch (_) {}

    if (!canvasData || !(canvasData.nodes || []).length) {
      alert('该 Skill 没有预定义画布，无法展开');
      return;
    }

    const { laneIdx, step } = nodeObj;
    const insertStep = step + 1;

    // 腾出位置：将后续节点 step +len
    const skillNodes = canvasData.nodes || [];
    const stepsNeeded = skillNodes.reduce((m, n) => Math.max(m, n.step || 1), 1);
    this._nodes.forEach(n => {
      if (n.laneIdx === laneIdx && n.step >= insertStep) n.step += stepsNeeded;
    });
    if (insertStep + stepsNeeded - 1 > this._steps) {
      this._steps = insertStep + stepsNeeded - 1;
    }
    this._refreshStepsAndLanes();

    // 插入 skill 内部节点
    skillNodes.forEach(n => {
      this.addNode(n.type, n.label, laneIdx, insertStep + (n.step || 1) - 1, n.params || {});
    });

    // 删除原 skill_call 节点
    this.removeNode(nodeObj.id);
  }

  /* ── 连线端口拖拽 ─────────────────────────────────────────────────────── */
  _startConnect(ev, fromId, fromPort = 'out') {
    ev.preventDefault(); ev.stopPropagation();
    this._connectingFrom = fromId;

    const svg = this._svgEl;
    const svgRect = svg.getBoundingClientRect();

    // 临时连线
    const temp = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    temp.setAttribute('class', 'wfc-temp-conn');
    svg.appendChild(temp);
    this._tempConnEl = temp;

    const from = this._getNodePortCenter(fromId, fromPort);
    const isVertical = (fromPort === 'top' || fromPort === 'bottom');

    const onMove = e => {
      if (!from) return;
      const mx = e.clientX - svgRect.left;
      const my = e.clientY - svgRect.top;
      let d;
      if (isVertical) {
        const dy = (my - from.y) * 0.5;
        d = `M${from.x},${from.y} C${from.x},${from.y + dy} ${mx},${my - dy} ${mx},${my}`;
      } else {
        const dx = (mx - from.x) * 0.5;
        d = `M${from.x},${from.y} C${from.x + dx},${from.y} ${mx - dx},${my} ${mx},${my}`;
      }
      temp.setAttribute('d', d);
    };

    const onUp = e => {
      temp.remove(); this._tempConnEl = null;
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);

      // 接受 in / top / bottom 作为落点端口
      const el = document.elementFromPoint(e.clientX, e.clientY);
      const targetPortEl = el?.closest('.wfc-port-in, .wfc-port-top, .wfc-port-bottom');
      if (targetPortEl) {
        const targetNodeEl = targetPortEl.closest('.wfc-node');
        const toId = targetNodeEl?.dataset.nodeId;
        let toPort = 'in';
        if (targetPortEl.classList.contains('wfc-port-top'))    toPort = 'top';
        if (targetPortEl.classList.contains('wfc-port-bottom')) toPort = 'bottom';
        if (toId && toId !== fromId) {
          this.addConnection(fromId, toId, 'control', fromPort, toPort);
        }
      }
      this._connectingFrom = null;
    };

    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  }

  /* ── 节点位置拖拽（in cell） ──────────────────────────────────────────── */
  _startNodeDrag(ev, nodeObj) {
    ev.preventDefault();
    const startX = ev.clientX - nodeObj.x;
    const startY = ev.clientY - nodeObj.y;

    const onMove = e => {
      nodeObj.x = e.clientX - startX;
      nodeObj.y = e.clientY - startY;
      nodeObj.el.style.left = nodeObj.x + 'px';
      nodeObj.el.style.top  = nodeObj.y + 'px';
      this._redrawConnections();
    };
    const onUp = () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  }

  /* ── Q&A 操作 ─────────────────────────────────────────────────────────── */
  addQuestion(nodeId, text, answer = '') {
    const id = this._genId('q');

    // 问题列
    const qCard = document.createElement('div');
    qCard.className = 'wfc-qa-card linked';
    qCard.dataset.qId = id;
    qCard.innerHTML = `<div class="wfc-qcard-node">${_escWFC(this._nodes.find(n=>n.id===nodeId)?.label||'')}</div>
                       <div class="wfc-qcard-text">${_escWFC(text)}</div>`;
    qCard.addEventListener('click', () => this.selectNode(nodeId));
    if (this._qaQEl) this._qaQEl.appendChild(qCard);

    // 回答列
    const aCard = document.createElement('div');
    aCard.className = 'wfc-qa-card linked';
    aCard.dataset.qId = id;
    const textarea = document.createElement('textarea');
    textarea.className = 'wfc-qa-answer';
    textarea.placeholder = '填写回答…';
    textarea.value = answer;
    textarea.rows = 2;
    textarea.addEventListener('input', () => this._syncQaToNode(id));
    aCard.appendChild(textarea);
    if (this._qaAEl) this._qaAEl.appendChild(aCard);

    const qObj = { id, nodeId, text, answer, qEl: qCard, aEl: aCard, _textarea: textarea };
    this._questions.push(qObj);
    this._updateNodeQBadge(nodeId);
    return qObj;
  }

  updateAnswer(qId, answer) {
    const q = this._questions.find(q => q.id === qId);
    if (!q) return;
    q.answer = answer;
    if (q._textarea) q._textarea.value = answer;
    this._syncQaToNode(q.nodeId);
  }

  _syncQaToNode(qId) {
    const q = this._questions.find(q => q.id === qId);
    if (!q) return;
    q.answer = q._textarea?.value || '';
    // 把回答写入节点 params（以 question text 的前20字为 key）
    const node = this._nodes.find(n => n.id === q.nodeId);
    if (!node) return;
    const key = 'q_' + q.text.slice(0, 16).replace(/\s+/g, '_');
    node.params[key] = q.answer;
    this._renderNodeParams(node);
  }

  _syncNodeToQa(nodeId) {
    // 将节点参数变化同步到关联 Q&A 回答
    const node = this._nodes.find(n => n.id === nodeId);
    if (!node) return;
    this._questions.filter(q => q.nodeId === nodeId).forEach(q => {
      const key = 'q_' + q.text.slice(0, 16).replace(/\s+/g, '_');
      if (node.params[key] !== undefined && q._textarea) {
        q._textarea.value = node.params[key];
        q.answer = node.params[key];
      }
    });
  }

  _updateNodeQBadge(nodeId) {
    const node = this._nodes.find(n => n.id === nodeId);
    if (!node?._qBadge) return;
    const count = this._questions.filter(q => q.nodeId === nodeId).length;
    node._qBadge.style.display = count > 0 ? '' : 'none';
    node._qBadge.textContent = count;
  }

  /* ── 全局事件 ─────────────────────────────────────────────────────────── */
  _bindGlobalEvents() {
    // 关闭 popover / ctx menu 点击空白
    document.addEventListener('click', e => {
      if (this._popoverEl && !this._popoverEl.contains(e.target)) {
        const isNode = e.target.closest('.wfc-node');
        if (!isNode) this._closePopover();
      }
      if (this._connCtxEl && !this._connCtxEl.contains(e.target)) this._closeConnCtx();
      if (this._nodeCtxEl && !this._nodeCtxEl.contains(e.target)) this._closeNodeCtx();
      if (this._savesOverlay && !e.target.closest('.wfc-saves-modal')) {
        // 不关闭 — 用关闭按钮
      }
    });
  }

  /* ── 状态栏 ───────────────────────────────────────────────────────────── */
  _updateStats() {
    if (!this._statsEl) return;
    this._statsEl.textContent = `${this._nodes.length} 节点 · ${this._conns.length} 连线`;
    // 有节点时隐藏空状态提示覆盖层（wfc_window 专用，其他页面无此元素）
    const emptyEl = document.getElementById('wfcwCanvasEmpty');
    if (emptyEl) emptyEl.classList.toggle('hidden', this._nodes.length > 0);
  }

  /* ── 序列化 ───────────────────────────────────────────────────────────── */
  toJSON() {
    return {
      title: '工作流画布',
      lanes: this._lanes.map(l => ({ id: l.id, label: l.label })),
      steps: this._steps,
      step_labels: this._stepLabels.slice(),
      nodes: this._nodes.map(n => ({
        id: n.id, type: n.type, label: n.label,
        lane_id: this._lanes[n.laneIdx]?.id,
        laneIdx: n.laneIdx, step: n.step,
        params: n.params, x: n.x, y: n.y,
      })),
      connections: this._conns.map(c => ({
        id: c.id, from: c.fromId, to: c.toId, type: c.type,
        fromPort: c.fromPort, toPort: c.toPort,
      })),
      questions: this._questions.map(q => ({
        id: q.id, nodeId: q.nodeId, text: q.text, answer: q.answer,
      })),
    };
  }

  fromJSON(data) {
    this._clear();
    if (!data) return;
    // 步骤列：优先用 step_labels 数组，其次 steps 数值，否则保持默认
    if (Array.isArray(data.step_labels) && data.step_labels.length) {
      this._stepLabels = data.step_labels.slice();
      this._steps = this._stepLabels.length;
    } else if (data.steps) {
      this._steps = data.steps;
      this._stepLabels = [];
    }

    // 泳道
    (data.lanes || []).forEach(l => {
      const lane = this._addLane(l.label || '');
      lane.id = l.id; // 覆盖 id
      lane.el.dataset.laneId = l.id;
    });
    if (this._lanes.length === 0) this._addLane('主流程');

    this._renderStepHeaders();
    this._lanes.forEach((_, idx) => this._refreshLaneCells(idx));

    // 节点 — 先建立 laneIdx 映射
    const laneIdxMap = {};
    this._lanes.forEach((l, i) => { laneIdxMap[l.id] = i; });

    (data.nodes || []).forEach(n => {
      const laneIdx = n.laneIdx !== undefined ? n.laneIdx
                    : (laneIdxMap[n.lane_id] ?? 0);
      const nodeObj = this.addNode(n.type, n.label, laneIdx, n.step || 1, n.params || {});
      if (nodeObj) {
        nodeObj.id = n.id;
        nodeObj.el.dataset.nodeId = n.id;
        if (n.x !== undefined) { nodeObj.x = n.x; nodeObj.el.style.left = n.x + 'px'; }
        if (n.y !== undefined) { nodeObj.y = n.y; nodeObj.el.style.top  = n.y + 'px'; }
      }
    });

    // 连线
    setTimeout(() => {
      (data.connections || []).forEach(c => {
        const connObj = this.addConnection(c.from, c.to,
          c.type === 'dependency' ? 'control' : (c.type || 'control'),
          c.fromPort, c.toPort);
        if (connObj) connObj.id = c.id;
      });
      // Q&A
      (data.questions || []).forEach(q => {
        this.addQuestion(q.nodeId, q.text, q.answer || '');
      });
    }, 50);
  }

  _clear() {
    [...this._nodes].forEach(n => this.removeNode(n.id));
    this._conns = [];
    this._questions = [];
    this._svgEl.innerHTML = '';
    // 清除泳道（保留 step-headers 和 add-lane-btn）
    const toRemove = this._lanesEl.querySelectorAll('.wfc-lane');
    toRemove.forEach(el => el.remove());
    this._lanes = [];
    this._qaQEl?.querySelectorAll('.wfc-qa-card').forEach(e => e.remove());
    this._qaAEl?.querySelectorAll('.wfc-qa-card, .wfc-qa-answer').forEach(e => e.remove());
    this._steps = 5;
    this._stepLabels = [];
    this._hideStepHeaders = false;
    this._hideLaneLabels  = false;
    this._lanesEl.classList.remove('wfc-interaction-mode');
    this._lanesEl.style.removeProperty('--canvas-step-w');
    this._lanesEl.style.removeProperty('--canvas-lane-h');
    this._updateStats();
  }

  /**
   * 为交互画布清空并配置布局（每个人工审批步骤切换时调用）。
   * layout: { column_labels: string[] | null, hide_lane_labels: boolean }
   *   column_labels: 有值 → 按标题显示多列；null/空 → 单列且隐藏横轴标题行
   *   hide_lane_labels: true（默认）→ 隐藏纵轴泳道标签列
   */
  clearForInteraction(layout = {}) {
    this._clear();
    const columns = layout?.column_labels;
    const hasColumns = Array.isArray(columns) && columns.length > 0;
    if (hasColumns) {
      this._steps      = columns.length;
      this._stepLabels = columns.slice();
      this._hideStepHeaders = false;
    } else {
      this._steps      = 1;
      this._stepLabels = [];
      this._hideStepHeaders = true;
    }
    // hide_lane_labels 默认 true（交互画布一般不需要泳道标签）
    this._hideLaneLabels = layout?.hide_lane_labels !== false;

    // 应用自定义列宽 / 行高
    this._lanesEl.classList.add('wfc-interaction-mode');
    if (layout?.column_width) {
      this._lanesEl.style.setProperty('--canvas-step-w', layout.column_width + 'px');
    }
    if (layout?.lane_height) {
      this._lanesEl.style.setProperty('--canvas-lane-h', layout.lane_height + 'px');
    }

    this._refreshStepsAndLanes();
  }

  /* ── 注入文本 ─────────────────────────────────────────────────────────── */
  toInjectText() {
    const lines = ['[工作流画布]'];
    this._lanes.forEach((lane, laneIdx) => {
      const laneNodes = this._nodes
        .filter(n => n.laneIdx === laneIdx)
        .sort((a, b) => a.step - b.step);
      if (laneNodes.length === 0) return;
      const nodeDescs = laneNodes.map(n => {
        const pStr = Object.entries(n.params || {})
          .filter(([, v]) => v)
          .map(([k, v]) => `${k}=${v}`)
          .join(', ');
        return `${n.label}${pStr ? `(${pStr})` : ''}`;
      });
      lines.push(`${lane.label}（${laneIdx+1}）：${nodeDescs.join(' → ')}`);
    });

    if (this._conns.length > 0) {
      lines.push('数据流/依赖：');
      this._conns.forEach(c => {
        const from = this._nodes.find(n => n.id === c.fromId);
        const to   = this._nodes.find(n => n.id === c.toId);
        if (from && to) {
          const typeStr = c.type === 'dataflow' ? '⟿（数据）' : '→（命令）';
          lines.push(`  ${from.label} ${typeStr} ${to.label}`);
        }
      });
    }

    const unanswered = this._questions.filter(q => !q.answer);
    if (unanswered.length > 0) {
      lines.push('待确认参数：');
      unanswered.forEach((q, i) => {
        lines.push(`  Q${i+1}（${this._nodes.find(n=>n.id===q.nodeId)?.label||''}）：${q.text}`);
      });
    }

    const answered = this._questions.filter(q => q.answer);
    if (answered.length > 0) {
      lines.push('已确认参数：');
      answered.forEach((q, i) => {
        lines.push(`  ${this._nodes.find(n=>n.id===q.nodeId)?.label||''}/${q.text}：${q.answer}`);
      });
    }

    lines.push('请按此工作流逐步执行，每步完成后反馈进度。');
    return lines.join('\n');
  }

  /* ── 持久化（云端 REST API） ─────────────────────────────────────────── */

  _cf() { return window.top?._cloudFetch || window._cloudFetch || null; }

  /** 保存画布到云端 DB。ownerGid 由调用方传入。*/
  async save(title, ownerGid = '', existingGid = null) {
    const _cloudFetch = this._cf();
    if (!_cloudFetch) { console.error('[WFC] _cloudFetch 未就绪'); return null; }
    const data = this.toJSON();
    data.title = title || data.title;
    try {
      const res = await _cloudFetch('/api/canvases', {
        method: 'POST',
        body: JSON.stringify({
          owner_gid: ownerGid,
          title: title || '未命名画布',
          data,
          gid: existingGid || null,
          is_shared: false,
        }),
      });
      return res; // { gid, title, updated_at }
    } catch (e) {
      console.error('[WFC] save_canvas failed', e);
      return null;
    }
  }

  /** 从云端 DB 加载指定 gid 的画布。*/
  async load(gid) {
    const _cloudFetch = this._cf();
    if (!_cloudFetch) return null;
    try {
      const res = await _cloudFetch(`/api/canvases/${gid}`, { method: 'GET' });
      if (res?.data) this.fromJSON(res.data);
      return res;
    } catch (e) {
      console.error('[WFC] load_canvas failed', e);
      return null;
    }
  }

  /** 列出当前用户的画布存档。*/
  async listSaves(ownerGid = '') {
    const _cloudFetch = this._cf();
    if (!_cloudFetch) return [];
    try {
      const res = await _cloudFetch('/api/canvases', { method: 'GET' });
      return res?.canvases || [];
    } catch (e) {
      console.error('[WFC] list_canvases failed', e);
      return [];
    }
  }

  /** 删除指定 gid 的存档。*/
  async deleteSave(gid) {
    const _cloudFetch = this._cf();
    if (!_cloudFetch) return null;
    try {
      return await _cloudFetch(`/api/canvases/${gid}`, { method: 'DELETE' });
    } catch (e) {
      console.error('[WFC] delete_canvas failed', e);
      return null;
    }
  }

  /** 切换共享状态。*/
  async toggleShared(gid, isShared) {
    const _cloudFetch = this._cf();
    if (!_cloudFetch) return null;
    try {
      return await _cloudFetch(`/api/canvases/${gid}/shared`, {
        method: 'PATCH',
        body: JSON.stringify({ is_shared: isShared }),
      });
    } catch (e) {
      console.error('[WFC] toggle_shared failed', e);
      return null;
    }
  }
}

/* ── 沙盘节点类型定义 ──────────────────────────────────────────────────────── */
const WFC_SANDBOX_NODE_TYPES = {
  bop_node:    { label: 'BOP 节点',  badge: 'BOP',      group: 'bop' },
  bop_line:    { label: '线体',      badge: 'LINE',      group: 'bop' },
  bop_station: { label: 'BOP 工位',  badge: 'STATION',   group: 'bop' },
  bop_op:      { label: 'BOP 工序',  badge: 'OP',        group: 'bop' },
  process:     { label: '流程步骤',  badge: 'PROCESS',   group: 'flow' },
  decision:    { label: '判断分支',  badge: 'DECISION',  group: 'flow' },
  data:        { label: '数据/清单', badge: 'DATA',      group: 'flow' },
  text:        { label: '说明文本',  badge: 'TEXT',      group: 'misc' },
  metric:      { label: '指标',      badge: 'METRIC',    group: 'misc' },
  resource:    { label: '资源',      badge: 'RESOURCE',  group: 'misc' },
  link:        { label: '引用链接',  badge: 'LINK',      group: 'misc' },
  note:        { label: '便签',      badge: 'NOTE',      group: 'misc' },
  container:   { label: '容器卡片',  badge: 'CC',        group: 'misc' },
  // ── UI 原语（AI 沙盘专用）──────────────────────────────────────────────
  ui_select:      { label: '单选/多选', badge: 'SELECT',   group: 'ui' },
  ui_form:        { label: '表单',      badge: 'FORM',     group: 'ui' },
  ui_button_group:{ label: '按钮组',   badge: 'BTNS',     group: 'ui' },
  ui_table:       { label: '数据表格', badge: 'TABLE',    group: 'ui' },
  ui_text:        { label: '文本展示', badge: 'TEXT·UI',  group: 'ui' },
  ui_metric:      { label: 'KPI 指标', badge: 'METRIC·UI',group: 'ui' },
  ui_confirm:     { label: '确认卡',   badge: 'CONFIRM',  group: 'ui' },
  ui_checklist:   { label: '勾选清单', badge: 'CHECK',    group: 'ui' },
  ui_badge_group: { label: '状态标签', badge: 'BADGES',   group: 'ui' },
  ui_section:     { label: '分组框',   badge: 'SECTION',  group: 'ui' },
  ui_result:      { label: '查询结果', badge: 'RESULT',   group: 'ui' },
};

/* ── WorkflowCanvas 沙盘扩展（混入到原型） ─────────────────────────────────── */
Object.assign(WorkflowCanvas.prototype, {

  /* 切换沙盘/流程图模式（兼容旧调用；沙盘现已固定在底部容器中） */
  setSandboxMode(enable) {
    if (enable) this._initSandbox();
  },

  /* 初始化沙盘状态（惰性） */
  _initSandbox() {
    if (this._sandboxInited) return;
    this._sandboxInited = true;
    this._sandboxNodes = this._sandboxNodes || [];
    this._sandboxConns = this._sandboxConns || [];
    this._sbTransform  = { x: 0, y: 0, scale: 1 };

    // 绑定事件
    const vp    = document.getElementById('wfcwSandboxVp');
    const world = document.getElementById('wfcwSandboxWorld');
    if (!vp || !world) return;

    this._sbVp    = vp;
    this._sbWorld = world;
    this._sbSvg   = document.getElementById('wfcwSandboxSvg');

    // 缩放控件
    document.getElementById('wfcwZoomIn')?.addEventListener('click', () => this._sbZoomBy(1.2));
    document.getElementById('wfcwZoomOut')?.addEventListener('click', () => this._sbZoomBy(1/1.2));
    document.getElementById('wfcwZoomFit')?.addEventListener('click', () => this._sbZoomFit());

    // 滚轮缩放
    vp.addEventListener('wheel', e => {
      e.preventDefault();
      const factor = e.deltaY < 0 ? 1.1 : 1 / 1.1;
      const rect = vp.getBoundingClientRect();
      const mx   = e.clientX - rect.left;
      const my   = e.clientY - rect.top;
      this._sbZoomAtPoint(factor, mx, my);
    }, { passive: false });

    // 中键/Space 平移
    let _panning = false, _panStart = null;
    vp.addEventListener('mousedown', e => {
      if (e.button === 1 || this._sbSpaceDown) {
        _panning = true;
        _panStart = { x: e.clientX - this._sbTransform.x, y: e.clientY - this._sbTransform.y };
        vp.classList.add('panning');
        e.preventDefault();
      }
    });
    window.addEventListener('mousemove', e => {
      if (!_panning) return;
      this._sbTransform.x = e.clientX - _panStart.x;
      this._sbTransform.y = e.clientY - _panStart.y;
      this._sbApplyTransform();
    });
    window.addEventListener('mouseup', () => {
      _panning = false;
      vp.classList.remove('panning');
    });

    document.addEventListener('keydown', e => { if (e.code === 'Space') this._sbSpaceDown = true; });
    document.addEventListener('keyup',   e => { if (e.code === 'Space') this._sbSpaceDown = false; });

    // 节点库（沙盘分支）在 _renderPalette 中处理
    this._renderPalette?.();
    this._sbRender();
  },

  _sbApplyTransform() {
    const { x, y, scale } = this._sbTransform;
    if (this._sbWorld) this._sbWorld.style.transform = `translate(${x}px,${y}px) scale(${scale})`;
    const label = document.getElementById('wfcwZoomLabel');
    if (label) label.textContent = Math.round(scale * 100) + '%';
  },

  _sbZoomBy(factor) {
    if (!this._sbVp) return;
    const rect = this._sbVp.getBoundingClientRect();
    this._sbZoomAtPoint(factor, rect.width / 2, rect.height / 2);
  },

  _sbZoomAtPoint(factor, mx, my) {
    const t = this._sbTransform;
    const newScale = Math.max(0.2, Math.min(3, t.scale * factor));
    const r = newScale / t.scale;
    t.x = mx - r * (mx - t.x);
    t.y = my - r * (my - t.y);
    t.scale = newScale;
    this._sbApplyTransform();
  },

  _sbZoomFit() {
    const nodes = this._sandboxNodes || [];
    if (nodes.length === 0) { this._sbTransform = { x: 40, y: 40, scale: 1 }; this._sbApplyTransform(); return; }
    const xs = nodes.map(n => n.x), ys = nodes.map(n => n.y);
    const minX = Math.min(...xs), minY = Math.min(...ys);
    const maxX = Math.max(...xs) + 200, maxY = Math.max(...ys) + 120;
    const vp = this._sbVp;
    if (!vp) return;
    const vpW = vp.clientWidth, vpH = vp.clientHeight;
    const scaleX = vpW  / (maxX - minX + 80);
    const scaleY = vpH  / (maxY - minY + 80);
    const scale  = Math.max(0.2, Math.min(1.5, Math.min(scaleX, scaleY)));
    this._sbTransform = {
      x: (vpW - (maxX - minX) * scale) / 2 - minX * scale,
      y: (vpH - (maxY - minY) * scale) / 2 - minY * scale,
      scale,
    };
    this._sbApplyTransform();
  },

  /* 添加沙盘节点 */
  addSandboxNode(type, label, params = {}, x, y) {
    if (!this._sandboxNodes) this._sandboxNodes = [];
    const id = 'sn_' + Date.now() + '_' + Math.random().toString(36).slice(2, 5);
    const vp = this._sbVp;
    if (x === undefined) {
      x = vp ? (vp.clientWidth / 2 - this._sbTransform.x) / this._sbTransform.scale - 60 : 100;
    }
    if (y === undefined) {
      y = vp ? (vp.clientHeight / 2 - this._sbTransform.y) / this._sbTransform.scale - 40 : 100;
    }
    const node = { id, type, label, params, x, y };
    this._sandboxNodes.push(node);
    this._sbRender();
    return node;
  },

  clearSandbox() {
    this._sandboxNodes = [];
    this._sandboxConns = [];
    this._sbRender();
  },

  /* 渲染沙盘：有 rows/cols 走 grid 模式，否则走自由白板模式 */
  _sbRender() {
    if (!this._sbWorld) return;
    [...this._sbWorld.children].forEach(el => {
      if (el !== this._sbSvg) el.remove();
    });
    const hasGrid = (this._sandboxRows?.length || this._sandboxCols?.length);
    // grid 模式去掉点阵背景；白板模式恢复
    this._sbVp?.classList.toggle('wfc-sbg-mode', !!hasGrid);
    if (hasGrid) {
      this._sbRenderGrid();
    } else {
      (this._sandboxNodes || []).forEach(node => {
        const el = this._buildSandboxNodeEl(node);
        this._sbWorld.appendChild(el);
      });
    }
    this._sbUpdateStats();
  },

  /* grid 模式渲染：完全复用流程画布泳道 DOM（wfc-step-headers + wfc-lane + wfc-lane-cell） */
  _sbRenderGrid() {
    const rows  = this._sandboxRows || [];
    const cols  = this._sandboxCols || [];
    const nodes = this._sandboxNodes || [];

    const effectiveCols = cols.length ? cols : [{ id: '_default', label: '内容' }];
    const effectiveRows = rows.length ? rows : [{ id: '_default', label: '内容' }];

    // 容器
    const wrap = document.createElement('div');
    wrap.className = 'wfc-sbg-wrap';

    // 列标题行（复用 wfc-step-headers 样式）
    const hdrRow = document.createElement('div');
    hdrRow.className = 'wfc-step-headers';
    const spacer = document.createElement('div');
    spacer.className = 'wfc-step-hdr-spacer';
    hdrRow.appendChild(spacer);
    effectiveCols.forEach(col => {
      const hdr = document.createElement('div');
      hdr.className = 'wfc-step-hdr wfc-sbg-col-hdr';
      hdr.textContent = col.label || col.id;
      hdrRow.appendChild(hdr);
    });
    wrap.appendChild(hdrRow);

    // 各行（复用 wfc-lane）
    effectiveRows.forEach(row => {
      const laneEl = document.createElement('div');
      laneEl.className = 'wfc-lane';

      // 行标题（复用 wfc-lane-label，只读）
      const labelEl = document.createElement('div');
      labelEl.className = 'wfc-lane-label';
      const txt = document.createElement('div');
      txt.className = 'wfc-lane-label-input';
      txt.style.cssText = 'pointer-events:none;';
      txt.textContent = row.label || row.id;
      labelEl.appendChild(txt);
      laneEl.appendChild(labelEl);

      // 单元格行
      const cellsEl = document.createElement('div');
      cellsEl.className = 'wfc-lane-cells';

      effectiveCols.forEach(col => {
        const cell = document.createElement('div');
        cell.className = 'wfc-lane-cell wfc-sbg-cell';
        cell.dataset.row = row.id;
        cell.dataset.col = col.id;

        const cellNodes = nodes.filter(n =>
          (n.row_id === row.id || row.id === '_default') &&
          (n.col_id === col.id || col.id === '_default')
        );
        cellNodes.forEach(node => {
          const el = this._buildSandboxNodeEl(node, true);
          cell.appendChild(el);
        });

        cellsEl.appendChild(cell);
      });

      laneEl.appendChild(cellsEl);
      wrap.appendChild(laneEl);
    });

    this._sbWorld.appendChild(wrap);
  },

  _buildSandboxNodeEl(node, gridMode = false) {
    const def   = WFC_SANDBOX_NODE_TYPES[node.type] || { label: node.type, badge: '?', group: '' };
    const el    = document.createElement('div');
    el.className = 'wfc-sc' + (gridMode ? ' wfc-sc-grid' : '');
    el.dataset.id   = node.id;
    el.dataset.type = node.type;
    if (!gridMode) el.style.cssText = `left:${node.x}px; top:${node.y}px;`;

    const hdr = document.createElement('div');
    hdr.className = 'wfc-sc-hdr';
    hdr.innerHTML = `
      <span class="wfc-sc-badge wfc-badge-${_escWFC(node.type)}">${_escWFC(def.badge)}</span>
      <span class="wfc-sc-label" title="${_escWFC(node.label)}">${_escWFC(node.label)}</span>
      ${node.type === 'container' ? '<button class="wfc-sc-cc-cfg-btn" title="配置内容">⚙</button>' : ''}
      <button class="wfc-sc-del" title="删除">×</button>`;
    hdr.querySelector('.wfc-sc-del').addEventListener('click', e => {
      e.stopPropagation();
      this._sandboxNodes = (this._sandboxNodes || []).filter(n => n.id !== node.id);
      this._sbRender();
    });
    if (node.type === 'container') {
      hdr.querySelector('.wfc-sc-cc-cfg-btn')?.addEventListener('click', e => {
        e.stopPropagation();
        el.dispatchEvent(new CustomEvent('wfc:container-config', { bubbles: true, detail: { node } }));
      });
    }
    el.appendChild(hdr);

    // 正文参数
    const body = document.createElement('div');
    body.className = 'wfc-sc-body';

    if (node.type === 'bop_line') {
      el.classList.add('wfc-sc-bop-line');
      el.style.width  = (node.params?.w  || 900) + 'px';
      el.style.height = (node.params?.h  || 400) + 'px';
      hdr.textContent = node.params?.label || node.params?.title || node.label || '线体';
      hdr.className = 'wfc-sc-bop-line-hdr';
      body.remove();
      return el;
    }

    if (node.type === 'bop_station') {
      const p2 = node.params || {};
      const side = (p2.side || '').toUpperCase();
      const sideClass = side === 'L' ? 'bop-side-l'
                      : side === 'R' ? 'bop-side-r'
                      : side === 'M' ? 'bop-side-m' : '';
      el.classList.add('wfc-sc-bop-station');
      if (sideClass) el.classList.add(sideClass);
      hdr.innerHTML = `<span class="wfc-sc-bop-side-badge">${_escWFC(side||'?')}</span>
                       <span class="wfc-sc-bop-station-title">${_escWFC(p2.title||p2.label||node.label||'工位')}</span>`;
      body.innerHTML = p2.seq_no ? `<span class="wfc-sc-bop-seq">#${_escWFC(String(p2.seq_no))}</span>` : '';
      el.appendChild(body);
      return el;
    }

    if (node.type === 'bop_op') {
      const p3 = node.params || {};
      el.classList.add('wfc-sc-bop-op');
      const vpps  = p3.vpps  ? `<span class="wfc-sc-bop-vpps">${_escWFC(p3.vpps)}</span>` : '';
      const links = (p3.link_count > 0)
          ? `<span class="wfc-sc-bop-link-badge">${_escWFC(String(p3.link_count))}</span>` : '';
      hdr.innerHTML = `<span class="wfc-sc-bop-op-type">${_escWFC(p3.node_type_label||'工序')}</span>${links}`;
      body.innerHTML = `${vpps}<span class="wfc-sc-bop-op-title">${_escWFC(p3.title||node.label||'')}</span>`;
      el.appendChild(body);
      return el;
    }

    if (node.type === 'container') {
      // 容器卡片：显示模式标签 + 查看按钮
      const _CC_LABELS = { row_detail:'行详情', markdown:'MD 文档', webview:'网页预览',
        pdf:'PDF', image_gallery:'图片集', richtext:'富文本' };
      const modeLabel = _CC_LABELS[(node.params || {}).mode] || (node.params || {}).mode || '未配置';
      const chip = document.createElement('span');
      chip.className = 'wfc-sc-cc-chip';
      chip.textContent = modeLabel;
      body.appendChild(chip);
      const openBtn = document.createElement('button');
      openBtn.className = 'wfc-sc-cc-open-btn';
      openBtn.textContent = '查看内容 →';
      openBtn.addEventListener('click', e => {
        e.stopPropagation();
        el.dispatchEvent(new CustomEvent('wfc:container-open', { bubbles: true, detail: { node } }));
      });
      body.appendChild(openBtn);
    } else if (node.type && node.type.startsWith('ui_')) {
      // ── UI 原语渲染分支 ──────────────────────────────────────────────────
      const p = node.params || {};
      const _inject = (text) => {
        if (!text) return;
        (window.injectToAI || window.top?.injectToAI)?.(text);
      };

      if (node.type === 'ui_select') {
        // 单选/多选按钮组
        if (p.question) {
          const q = document.createElement('div');
          q.className = 'wfc-ui-question';
          q.textContent = p.question;
          body.appendChild(q);
        }
        const opts = document.createElement('div');
        opts.className = 'wfc-ui-opts';
        const options = Array.isArray(p.options) ? p.options : [];
        const isMulti = !!p.multi;
        const selected = new Set();
        options.forEach(opt => {
          const btn = document.createElement('button');
          btn.className = 'wfc-ui-opt';
          btn.textContent = opt;
          btn.addEventListener('click', e => {
            e.stopPropagation();
            if (isMulti) {
              btn.classList.toggle('selected');
              if (selected.has(opt)) selected.delete(opt); else selected.add(opt);
            } else {
              opts.querySelectorAll('.wfc-ui-opt').forEach(b => b.classList.remove('selected'));
              btn.classList.add('selected');
              _inject('选择了：' + opt);
            }
          });
          opts.appendChild(btn);
        });
        body.appendChild(opts);
        if (isMulti) {
          const submitBtn = document.createElement('button');
          submitBtn.className = 'wfc-ui-submit';
          submitBtn.textContent = '确认选择';
          submitBtn.addEventListener('click', e => {
            e.stopPropagation();
            if (selected.size > 0) _inject('选择了：' + [...selected].join(', '));
          });
          body.appendChild(submitBtn);
        }

      } else if (node.type === 'ui_form') {
        // 多字段表单
        const fields = Array.isArray(p.fields) ? p.fields : [];
        const inputMap = {};
        fields.forEach(f => {
          const row = document.createElement('div');
          row.className = 'wfc-ui-form-row';
          const lbl = document.createElement('label');
          lbl.className = 'wfc-ui-form-label';
          lbl.textContent = f.label || f.key;
          row.appendChild(lbl);
          let inp;
          if (f.type === 'select') {
            inp = document.createElement('select');
            inp.className = 'wfc-ui-form-input';
            (f.options || []).forEach(o => {
              const opt = document.createElement('option');
              opt.value = o; opt.textContent = o;
              inp.appendChild(opt);
            });
          } else {
            inp = document.createElement('input');
            inp.className = 'wfc-ui-form-input';
            inp.type = f.type === 'date' ? 'date' : 'text';
            inp.placeholder = f.placeholder || '';
          }
          inputMap[f.key] = inp;
          row.appendChild(inp);
          body.appendChild(row);
        });
        const submitBtn = document.createElement('button');
        submitBtn.className = 'wfc-ui-submit';
        submitBtn.textContent = p.submit_label || '提交';
        submitBtn.addEventListener('click', e => {
          e.stopPropagation();
          const parts = fields.map(f => `${f.key}=${(inputMap[f.key]?.value || '')}`);
          _inject('表单提交：' + parts.join('，'));
        });
        body.appendChild(submitBtn);

      } else if (node.type === 'ui_button_group') {
        // 操作按钮组
        const btns = document.createElement('div');
        btns.className = 'wfc-ui-btns';
        (p.buttons || []).forEach(btn => {
          const b = document.createElement('button');
          b.className = 'wfc-ui-opt' + (btn.style === 'primary' ? ' primary' : btn.style === 'danger' ? ' danger' : '');
          b.textContent = btn.label || btn.value || '';
          b.addEventListener('click', e => { e.stopPropagation(); _inject('操作：' + (btn.value || btn.label)); });
          btns.appendChild(b);
        });
        body.appendChild(btns);

      } else if (node.type === 'ui_table') {
        // 数据表格
        const table = document.createElement('table');
        table.className = 'wfc-ui-table';
        const cols = Array.isArray(p.columns) ? p.columns : [];
        const rows = Array.isArray(p.rows) ? p.rows : [];
        const thead = document.createElement('thead');
        const hrow = document.createElement('tr');
        cols.forEach(c => { const th = document.createElement('th'); th.textContent = c; hrow.appendChild(th); });
        thead.appendChild(hrow);
        table.appendChild(thead);
        const tbody = document.createElement('tbody');
        rows.forEach(row => {
          const tr = document.createElement('tr');
          if (p.selectable) {
            tr.style.cursor = 'pointer';
            tr.addEventListener('click', e => {
              e.stopPropagation();
              _inject('选择行：' + (Array.isArray(row) ? row.join(', ') : String(row)));
            });
          }
          (Array.isArray(row) ? row : [row]).forEach(cell => {
            const td = document.createElement('td');
            td.textContent = String(cell ?? '');
            tr.appendChild(td);
          });
          tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        const wrap = document.createElement('div');
        wrap.style.cssText = 'overflow:auto;max-height:160px;';
        wrap.appendChild(table);
        body.appendChild(wrap);

      } else if (node.type === 'ui_text') {
        // 文本展示（简单 Markdown）
        const content = String(p.content || '');
        const div = document.createElement('div');
        div.className = 'wfc-ui-text-content';
        const sizeMap = { sm: '10px', md: '11px', lg: '13px' };
        div.style.fontSize = sizeMap[p.size] || '11px';
        // 基础 Markdown 处理
        let html = _escWFC(content)
          .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
          .replace(/^## (.+)$/gm, '<div style="font-weight:700;font-size:12px;margin:4px 0 2px">$1</div>')
          .replace(/^# (.+)$/gm, '<div style="font-weight:700;font-size:13px;margin:4px 0 2px">$1</div>')
          .replace(/\n\n/g, '<br><br>')
          .replace(/\n/g, '<br>');
        div.innerHTML = html;
        body.appendChild(div);

      } else if (node.type === 'ui_metric') {
        // KPI 指标卡
        const valEl = document.createElement('div');
        valEl.className = 'wfc-ui-metric-val';
        valEl.textContent = String(p.value ?? '—') + (p.unit ? ' ' + p.unit : '');
        body.appendChild(valEl);
        if (p.label) {
          const lbl = document.createElement('div');
          lbl.className = 'wfc-ui-metric-lbl';
          lbl.textContent = p.label;
          body.appendChild(lbl);
        }
        if (p.trend) {
          const trendEl = document.createElement('div');
          trendEl.className = 'wfc-ui-metric-trend';
          const trendMap = { up: '↑', down: '↓', flat: '→' };
          const colorMap = { up: 'var(--green)', down: 'var(--red)', flat: 'var(--text-muted)' };
          trendEl.textContent = trendMap[p.trend] || '';
          trendEl.style.color = colorMap[p.trend] || '';
          body.appendChild(trendEl);
        }

      } else if (node.type === 'ui_confirm') {
        // 确认卡
        if (p.question) {
          const q = document.createElement('div');
          q.className = 'wfc-ui-question';
          q.textContent = p.question;
          body.appendChild(q);
        }
        const btns = document.createElement('div');
        btns.className = 'wfc-ui-btns';
        const yesBtn = document.createElement('button');
        yesBtn.className = 'wfc-ui-opt primary';
        yesBtn.textContent = p.yes_label || '是';
        yesBtn.addEventListener('click', e => { e.stopPropagation(); _inject('确认：是'); });
        const noBtn = document.createElement('button');
        noBtn.className = 'wfc-ui-opt';
        noBtn.textContent = p.no_label || '否';
        noBtn.addEventListener('click', e => { e.stopPropagation(); _inject('确认：否'); });
        btns.appendChild(yesBtn);
        btns.appendChild(noBtn);
        body.appendChild(btns);

      } else if (node.type === 'ui_checklist') {
        // ── NOK 模式（只读状态色清单）────────────────────────────────────
        if (p.mode === 'nok') {
          const items = p.items || [];
          let rows = items.map(it => {
            const lvl = it.level || 'ok';
            return `<div class="wfc-cl-nok-row wfc-cl-nok-${_escWFC(lvl)}">
                <span class="wfc-cl-nok-dot"></span>
                <div class="wfc-cl-nok-text">
                    <div class="wfc-cl-nok-label">${_escWFC(it.label||'')}</div>
                    ${it.desc ? `<div class="wfc-cl-nok-desc">${_escWFC(it.desc)}</div>` : ''}
                </div>
            </div>`;
          }).join('');
          if (!items.length) rows = `<div class="wfc-cl-nok-empty">无不合格项 ✓</div>`;
          body.innerHTML = `<div class="wfc-cl-nok-list">${rows}</div>`;
          el.appendChild(body);
          return el;
        }
        // 勾选清单（原有逻辑）
        if (p.title) {
          const t = document.createElement('div');
          t.className = 'wfc-ui-question';
          t.textContent = p.title;
          body.appendChild(t);
        }
        const items = Array.isArray(p.items) ? p.items : [];
        const checkMap = {};
        items.forEach(item => {
          const row = document.createElement('label');
          row.className = 'wfc-ui-check-row';
          const cb = document.createElement('input');
          cb.type = 'checkbox';
          cb.className = 'wfc-ui-checkbox';
          checkMap[item.id] = cb;
          row.appendChild(cb);
          const span = document.createElement('span');
          span.textContent = item.label;
          row.appendChild(span);
          body.appendChild(row);
        });
        const doneBtn = document.createElement('button');
        doneBtn.className = 'wfc-ui-submit';
        doneBtn.textContent = '完成';
        doneBtn.addEventListener('click', e => {
          e.stopPropagation();
          const checked = items.filter(it => checkMap[it.id]?.checked);
          if (checked.length > 0) {
            _inject('已勾选：' + checked.map(it => it.label + ' ✓').join('，') + `，共 ${checked.length} 项`);
          }
        });
        body.appendChild(doneBtn);

      } else if (node.type === 'ui_badge_group') {
        // 状态标签组（仅展示）
        const wrap = document.createElement('div');
        wrap.className = 'wfc-ui-badge-wrap';
        (p.items || []).forEach(it => {
          const badge = document.createElement('span');
          badge.className = 'wfc-ui-badge wfc-ui-badge-' + (it.status || 'default');
          badge.textContent = it.label || '';
          wrap.appendChild(badge);
        });
        body.appendChild(wrap);

      } else if (node.type === 'ui_section') {
        // 分组框（仅展示，背景色区域）
        const lbl = document.createElement('div');
        lbl.className = 'wfc-ui-section-label';
        lbl.textContent = (node.label || '').toUpperCase();
        body.appendChild(lbl);

      } else if (node.type === 'ui_result') {
        // 查询结果卡
        if (p.query) {
          const q = document.createElement('div');
          q.className = 'wfc-ui-question';
          q.textContent = p.query;
          body.appendChild(q);
        }
        const data = p.data;
        const fmt = p.format || 'list';
        if (Array.isArray(data)) {
          data.slice(0, 8).forEach(item => {
            const row = document.createElement('div');
            row.className = 'wfc-sc-param';
            if (typeof item === 'object' && item !== null) {
              const vals = Object.values(item);
              row.innerHTML = `<span class="wfc-sc-param-val">${_escWFC(String(vals[0] ?? ''))}</span>`;
              if (vals[1] !== undefined) {
                row.innerHTML += `<span class="wfc-sc-param-key" style="margin-left:4px">${_escWFC(String(vals[1]))}</span>`;
              }
            } else {
              row.innerHTML = `<span class="wfc-sc-param-val">${_escWFC(String(item))}</span>`;
            }
            body.appendChild(row);
          });
        } else if (data && typeof data === 'object') {
          Object.entries(data).slice(0, 8).forEach(([k, v]) => {
            const row = document.createElement('div');
            row.className = 'wfc-sc-param';
            row.innerHTML = `<span class="wfc-sc-param-key">${_escWFC(k)}:</span><span class="wfc-sc-param-val">${_escWFC(String(v))}</span>`;
            body.appendChild(row);
          });
        }
      }
    } else {
      const _renderBody = () => {
        body.innerHTML = '';
        const paramKeys = Object.keys(node.params || {});
        const visibleKeys = paramKeys.filter(k => node.params[k]);
        if (visibleKeys.length > 0) {
          visibleKeys.slice(0, 6).forEach(k => {
            const row = document.createElement('div');
            row.className = 'wfc-sc-param';
            const _pv = node.params[k];
            const _pvStr = (_pv !== null && typeof _pv === 'object') ? JSON.stringify(_pv) : String(_pv);
            row.innerHTML = `<span class="wfc-sc-param-key">${_escWFC(k)}:</span><span class="wfc-sc-param-val">${_escWFC(_pvStr.slice(0, 80))}</span>`;
            body.appendChild(row);
          });
        } else {
          const p = document.createElement('p');
          p.textContent = def.label;
          body.appendChild(p);
        }
        const hint = document.createElement('div');
        hint.className = 'wfc-sc-edit-hint';
        hint.textContent = '双击编辑';
        body.appendChild(hint);
      };
      _renderBody();

      // 双击进入编辑模式
      body.addEventListener('dblclick', e => {
        e.stopPropagation();
        body.innerHTML = '';
        body.classList.add('editing');

        // 标题编辑
        const labelRow = document.createElement('div');
        labelRow.className = 'wfc-sc-edit-row';
        labelRow.innerHTML = `<label class="wfc-sc-edit-key">标题</label>`;
        const labelInput = document.createElement('input');
        labelInput.className = 'wfc-sc-edit-val';
        labelInput.value = node.label || '';
        labelRow.appendChild(labelInput);
        body.appendChild(labelRow);

        // params 编辑
        const allKeys = Object.keys(node.params || {});
        const inputMap = {};
        allKeys.forEach(k => {
          const paramRow = document.createElement('div');
          paramRow.className = 'wfc-sc-edit-row';
          paramRow.innerHTML = `<label class="wfc-sc-edit-key">${_escWFC(k)}</label>`;
          const inp = document.createElement('input');
          inp.className = 'wfc-sc-edit-val';
          const _pv = node.params[k];
          inp.value = (_pv !== null && typeof _pv === 'object') ? JSON.stringify(_pv) : String(_pv || '');
          inputMap[k] = inp;
          paramRow.appendChild(inp);
          body.appendChild(paramRow);
        });

        // 操作按钮行
        const btnRow = document.createElement('div');
        btnRow.className = 'wfc-sc-edit-btns';
        const saveBtn = document.createElement('button');
        saveBtn.className = 'wfc-sc-edit-save';
        saveBtn.textContent = '保存';
        const cancelBtn = document.createElement('button');
        cancelBtn.className = 'wfc-sc-edit-cancel';
        cancelBtn.textContent = '取消';
        btnRow.appendChild(saveBtn);
        btnRow.appendChild(cancelBtn);
        body.appendChild(btnRow);

        labelInput.focus();

        const doSave = () => {
          node.label = labelInput.value.trim() || node.label;
          // update label in header
          const labelEl = el.querySelector('.wfc-sc-label');
          if (labelEl) { labelEl.textContent = node.label; labelEl.title = node.label; }
          allKeys.forEach(k => {
            const rawVal = inputMap[k].value;
            try { node.params[k] = JSON.parse(rawVal); } catch (_) { node.params[k] = rawVal; }
          });
          body.classList.remove('editing');
          _renderBody();
        };
        const doCancel = () => { body.classList.remove('editing'); _renderBody(); };

        saveBtn.addEventListener('click', e => { e.stopPropagation(); doSave(); });
        cancelBtn.addEventListener('click', e => { e.stopPropagation(); doCancel(); });
        labelInput.addEventListener('keydown', e => { if (e.key === 'Enter') doSave(); if (e.key === 'Escape') doCancel(); });
      });
    }
    el.appendChild(body);

    // 拖拽移动（grid 模式禁用）
    if (!gridMode) {
    let dragging = false, dragOff = { x: 0, y: 0 };
    el.addEventListener('mousedown', e => {
      if (e.target.classList.contains('wfc-sc-del') || e.button !== 0) return;
      dragging = true;
      dragOff.x = (e.clientX - this._sbTransform.x) / this._sbTransform.scale - node.x;
      dragOff.y = (e.clientY - this._sbTransform.y) / this._sbTransform.scale - node.y;
      el.style.zIndex = '10';
      e.preventDefault();
    });
    window.addEventListener('mousemove', e => {
      if (!dragging) return;
      node.x = Math.round((e.clientX - this._sbTransform.x) / this._sbTransform.scale - dragOff.x);
      node.y = Math.round((e.clientY - this._sbTransform.y) / this._sbTransform.scale - dragOff.y);
      el.style.left = node.x + 'px';
      el.style.top  = node.y + 'px';
    });
    window.addEventListener('mouseup', () => {
      if (dragging) { dragging = false; el.style.zIndex = ''; }
    });
    } // end if (!gridMode)

    return el;
  },

  _sbUpdateStats() {
    const statsEl = this._statsEl || document.getElementById('wfcwStats');
    if (!statsEl) return;
    const n = (this._sandboxNodes || []).length;
    const c = (this._sandboxConns || []).length;
    statsEl.textContent = `${n} 节点 · ${c} 连线`;
  },

  /* toJSON / fromJSON 沙盘分支 */
  _toJSONSandbox() {
    return {
      canvas_mode: 'sandbox',
      title: '沙盘画布',
      sandbox_nodes: (this._sandboxNodes || []).map(n => ({ ...n })),
      sandbox_conns: (this._sandboxConns || []).map(c => ({ ...c })),
    };
  },

  _fromJSONSandbox(data) {
    this._sandboxRows  = (data.rows  || []).map(r => ({ ...r }));
    this._sandboxCols  = (data.cols  || []).map(c => ({ ...c }));
    // 兼容 AI 生成的 nodes（非 sandbox_nodes）字段名
    this._sandboxNodes = (data.sandbox_nodes || data.nodes || []).map(n => ({ ...n }));
    this._sandboxConns = (data.sandbox_conns || []).map(c => ({ ...c }));
    this._sbRender();
    // grid 模式不需要缩放适配（表格本身有滚动）
    if (!this._sandboxRows.length && !this._sandboxCols.length) this._sbZoomFit();
  },

  /* ── 底部容器管理 ──────────────────────────────────────────────────────── */

  _initBottomTabs() {
    const tabbar = document.getElementById('wfcBcTabbar');
    if (!tabbar) return;

    // Tab 点击（事件委托）
    tabbar.addEventListener('click', e => {
      const addBtn = e.target.closest('#wfcBcAdd');
      if (addBtn) { this._promptAddTab(); return; }
      const tab = e.target.closest('.wfc-bc-tab[data-tab]');
      if (!tab) return;
      const closeBtn = e.target.closest('.wfc-bc-tab-close');
      if (closeBtn) { this.removeBottomTab(closeBtn.dataset.close); return; }
      this._activateBottomTab(tab.dataset.tab);
    });

    // 沙盘 VP 拖拽放置（接收节点库的 sandbox-node-type）
    const sandboxVp = document.getElementById('wfcwSandboxVp');
    if (sandboxVp) {
      sandboxVp.addEventListener('dragover', e => e.preventDefault());
      sandboxVp.addEventListener('drop', e => {
        const type = e.dataTransfer.getData('wfc-sandbox-node-type');
        if (!type) return;
        e.preventDefault();
        const rect = sandboxVp.getBoundingClientRect();
        const t    = this._sbTransform || { x: 0, y: 0, scale: 1 };
        const wx   = (e.clientX - rect.left  - t.x) / t.scale;
        const wy   = (e.clientY - rect.top   - t.y) / t.scale;
        this.addSandboxNode(type, WFC_SANDBOX_NODE_TYPES[type]?.label || type, {}, wx, wy);
      });
    }
  },

  _activateBottomTab(tabId) {
    document.querySelectorAll('#wfcBcTabbar .wfc-bc-tab').forEach(t =>
      t.classList.toggle('active', t.dataset.tab === tabId));
    document.querySelectorAll('#wfcBcPanes .wfc-bc-pane').forEach(p =>
      p.classList.toggle('active', p.dataset.tab === tabId));
  },

  /* 动态添加标签页（供 AI 或外部调用） */
  addBottomTab(id, title, type, params = {}) {
    const tabbar = document.getElementById('wfcBcTabbar');
    const panes  = document.getElementById('wfcBcPanes');
    if (!tabbar || !panes) return;

    // 去重
    this.removeBottomTab(id);

    // 创建标签按钮（带 × 关闭）
    const tab = document.createElement('button');
    tab.className = 'wfc-bc-tab';
    tab.dataset.tab = id;
    tab.innerHTML = `${_escWFC(title)} <span class="wfc-bc-tab-close" data-close="${id}">×</span>`;
    // 插入到 + 按钮之前
    const addBtn = document.getElementById('wfcBcAdd');
    tabbar.insertBefore(tab, addBtn);

    // 创建面板
    const pane = document.createElement('div');
    pane.className = 'wfc-bc-pane';
    pane.dataset.tab = id;
    if (type === 'url' || type === 'local') {
      const iframe = document.createElement('iframe');
      iframe.className = 'wfc-bc-pane-iframe';
      iframe.src = params.url || '';
      iframe.allow = 'clipboard-read; clipboard-write';
      pane.appendChild(iframe);
    }
    panes.appendChild(pane);

    this._activateBottomTab(id);
  },

  removeBottomTab(id) {
    document.querySelector(`#wfcBcTabbar .wfc-bc-tab[data-tab="${id}"]`)?.remove();
    document.querySelector(`#wfcBcPanes .wfc-bc-pane[data-tab="${id}"]`)?.remove();
    // 如果已无 active 面板，切回沙盘
    if (!document.querySelector('#wfcBcPanes .wfc-bc-pane.active')) {
      this._activateBottomTab('sandbox');
    }
  },

  /* 获取底部容器上下文摘要（供 AI 注入对话） */
  getBottomContext() {
    const parts = [];
    if (this._sandboxNodes?.length) {
      parts.push(`### 沙盘节点 (${this._sandboxNodes.length})\n` +
        this._sandboxNodes.map(n => `- [${n.type}] ${n.label}`).join('\n'));
    }
    if (this._bottomCtxEvents?.length) {
      const recent = this._bottomCtxEvents.slice(-10);
      parts.push(`### 底部容器操作 (最近 ${recent.length} 条)\n` +
        recent.map(ev => {
          if (ev.type === 'ai_ctx_state') return `- 状态: ${JSON.stringify(ev.state || {})}`;
          return `- ${ev.action || '操作'}: ${ev.label || ev.target || JSON.stringify(ev)}`;
        }).join('\n'));
    }
    return parts.join('\n\n') || '';
  },

  /* 记录来自 iframe 的上下文事件 */
  _recordCtxEvent(event) {
    if (!this._bottomCtxEvents) this._bottomCtxEvents = [];
    this._bottomCtxEvents.push(event);
    if (this._bottomCtxEvents.length > 20) this._bottomCtxEvents.shift();
    document.dispatchEvent(new CustomEvent('wfc:ctx_event', { detail: event }));
  },

  /* 弹出输入框添加 iframe 标签页 */
  _promptAddTab() {
    const title = prompt('标签页标题：');
    if (!title) return;
    const url = prompt('页面路径或 URL（如 ../lineage_view/index.html）：');
    if (!url) return;
    const id = 'bc_' + Date.now();
    this.addBottomTab(id, title, url.startsWith('http') ? 'url' : 'local', { url });
  },

});

/* 补丁：toJSON / fromJSON 在沙盘模式下切换分支 */
const _origToJSON = WorkflowCanvas.prototype.toJSON;
WorkflowCanvas.prototype.toJSON = function() {
  if (this._sandboxMode) return this._toJSONSandbox();
  return _origToJSON.call(this);
};

const _origFromJSON = WorkflowCanvas.prototype.fromJSON;
WorkflowCanvas.prototype.fromJSON = function(data) {
  if (!data) return;
  if (data.canvas_mode === 'sandbox') {
    this._fromJSONSandbox(data);
  } else {
    _origFromJSON.call(this, data);
  }
};

/* ── 工具函数 ─────────────────────────────────────────────────────────────── */
function _escWFC(str) {
  return String(str || '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// 全局暴露
window.WorkflowCanvas = WorkflowCanvas;
