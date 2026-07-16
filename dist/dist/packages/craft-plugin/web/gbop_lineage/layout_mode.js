'use strict';
/**
 * layout_mode.js  —  BOP Lineage 布局模式（Layout Mode）
 *
 * 在 Miller Columns 树形视图之外提供画布方式的物理布局可视化。
 * 线框-工位-线性层渲染（人/岗→设备/工具→工序，从工位中心往上排列），
 *
 * 依赖：无外部库（纯 vanilla JS）
 * 数据来源：通过 _buildLineageData() 从 lineage.js 共享的数据引用
 */

// ── 常量 ────────────────────────────────────────────────────────────
const LL_STATION_W = 220;   // 工位卡片宽度
const LL_STATION_H = 70;    // 工位卡片高度
const LL_COMPACT_W = 180;   // 紧凑型卡片宽度
const LL_COMPACT_H = 28;    // 紧凑型卡片高度
const LL_RING_CARD_W = 220; // 线性卡片宽度（与工位卡片等宽）
const LL_RING_CARD_H = 56;  // 线性卡片高度（2行内容 + 统计框，与列视图卡片一致）
const LL_LINE_GAP_X = 50;   // 线框间水平间距
const LL_LINE_GAP_Y = 160;  // 线框间垂直间距（增大给子卡片留空间）
const LL_STATION_GAP = 20;  // 工位间间距
const LL_LINE_PAD = 32;     // 线框内边距
const LL_LAYER_GAP = 20;    // 层间垂直间距
const LL_LAYER_CARD_GAP = 12; // 层内卡片水平间距
const LL_CHILD_PAD = 160;   // 子卡片展开预留空间（足够容纳3层卡片）
const LL_OP_GROUP_PAD = 7;    // 岗位分组框内边距
const LL_MIN_ZOOM = 0.10;
const LL_MAX_ZOOM = 3.0;
const LL_LOD_THRESHOLD = 0.15; // 低于此缩放比率进入 LOD 模式：隐藏细节，只显示线体名称
const LL_ESTIMATED_LINE_H = 660; // _buildLines 中无缓存时的估算线框高度（两行+车图区域+子卡片空间）
const LL_LAYOUT_VERSION = 5; // 递增以清除旧 localStorage 缓存（v5: 车俯视图区域）
const LL_CAR_AREA_H = 140;   // L/R 行间距（容纳车俯视图及岗位占位）
const LL_CAR_W = 180;         // 车俯视图 SVG 宽度
const LL_CAR_H = 76;          // 车俯视图 SVG 高度
const LL_OP_SLOT_W = 22;      // 岗位编号占位框宽度
const LL_OP_SLOT_H = 20;      // 岗位编号占位框高度

// 层分组：站内层（人/岗）、设备工具层、工序层（从工位中心往上排列）
const LAYER_INNER_TYPES = ['operator_process', 'man'];
const LAYER_MIDDLE_TYPES = ['equipment_factory', 'equipment_need', 'tool_factory', 'fixture_factory', 'tool_need', 'fixture_need'];
const LAYER_OUTER_TYPES = ['process'];

// 在画布隐藏的节点类型（通过右侧面板查看）
const HIDDEN_TYPES = ['part', 'non_standard_part', 'standard_part', 'support_material',
  'knowledge', 'rule', 'issue', 'standard_task', 'non_standard_task',
  'contral_plan', 'process_chart', 'operation', 'floor_height_factory', 'jack_pos'];


class LayoutMode {
  /**
   * @param {HTMLElement} containerEl - #lvLayoutCanvas 元素
   */
  constructor(containerEl) {
    this._container = containerEl;
    this._viewport  = containerEl.querySelector('#llViewport');
    this._world     = containerEl.querySelector('#llWorld');

    // 变换状态
    this._zoom = 1;
    this._panX = 40;
    this._panY = 40;

    // 数据引用（来自 lineage.js）
    this._data = null;

    // 当前过滤后的线体列表（_buildLines 填充，_renderLineNav 消费）
    this._filteredLines = [];

    // 位置缓存
    this._linePositions    = new Map();  // lineGid → {x, y, w, h}
    this._stationPositions = new Map();  // stationGid → {x, y}

    // 车流方向（lineGid → 'right'|'left'），默认 'right'
    this._lineFlowDirs = new Map();

    // 车俯视图区域信息（lineGid → { topY, lineW, flowDir }），由 _layoutLineStations 填充
    this._lineCarAreas = new Map();

    // 工位展开方向（stationGid → 'up'|'down'），由 _layoutLineStations 根据 flowDir 填充
    this._stationDirection = new Map();

    // 编辑状态
    this._editMode = false;

    // 位置拖拽状态（编辑模式用）
    this._dragState = null; // { type, gid, startX, startY, origX, origY }
    this._spaceDown = false;

    // 重挂拖拽状态（operator_process / process 换父节点）
    this._reparentPending = null; // { el, row, startX, startY }
    this._reparentDrag    = null; // { row, ghostEl, validTargets, hoveredGid }
    this._preserveView    = false; // true 时 render() 跳过 _fitToScreen

    // 选中节点
    this._activeGid = null;

    // 缩放控件引用
    this._zoomPctEl = containerEl.querySelector('#llZoomPct');

    // 缩略图
    this._minimap = containerEl.querySelector('#llMinimap');
    this._minimapBody = containerEl.querySelector('#llMinimapBody');
    this._mmScale = null;
    this._mmMinX = 0;
    this._mmMinY = 0;
    this._mmOffX = 0;
    this._mmOffY = 0;

    // 折叠按钮 — 默认折叠
    const toggleBtn = containerEl.querySelector('#llMinimapToggle');
    if (toggleBtn) {
      toggleBtn.textContent = '+';
      this._minimap.classList.add('collapsed');
      toggleBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        this._toggleMinimap();
      });
    }

    this._bindEvents();
    this._bindZoomControls();
  }

  // ══════════════════════════════════════════════════════════════════
  // 公共 API
  // ══════════════════════════════════════════════════════════════════

  /**
   * 主入口：使用 lineage 数据渲染画布
   * @param {object} data - _buildLineageData() 返回的数据引用
   */
  render(data) {
    if (!data) return;
    this._data = data;
    this._world.innerHTML = '';

    // render 时先禁用编辑模式，避免新建元素被错误标记为 ll-draggable
    this._editMode = false;

    // 恢复 localStorage 位置
    this._loadPositions();

    // 构建线框
    this._buildLines();

    // 为每条线计算工位布局
    this._layoutAllStations();

    // 渲染所有卡片（工位 + 同心环）
    this._renderAllCards();

    // 根据内容动态设置世界尺寸（确保背景网点覆盖可视区域）
    this._updateWorldSize();

    // 自动适配到视口：让所有元素在初始视图内完整可见
    if (this._preserveView) {
      this._preserveView = false;
      this._setTransform(); // 保持当前 zoom/pan，只重新应用变换
    } else {
      this._fitToScreen();
    }

    // 恢复选中
    if (this._activeGid) this.highlightNode(this._activeGid);

    // 渲染缩略图
    this._renderMinimap();
    // 渲染线体导航列表
    this._renderLineNav();
  }

  /**
   * 公共 API：适应全局 —— 缩放和平移使所有线框在视口内完整可见
   */
  fitToScreen() {
    this._fitToScreen();
    this._syncMinimapViewport();
  }

  /**
   * 切换编辑模式
   */
  setEditMode(enabled) {
    this._editMode = enabled;
    this._world.querySelectorAll('.ll-line-box').forEach(el => {
      el.classList.toggle('ll-draggable', enabled);
      // 更新车流箭头可点击状态
      const gid = el.dataset.gid;
      if (gid) this._renderLineFlowArrows(gid, el);
    });
    this._world.querySelectorAll('.ll-ring-card, .ll-station-card').forEach(el => {
      el.classList.toggle('ll-draggable', enabled);
    });
  }

  /**
   * 高亮指定节点（更新三态样式）
   */
  highlightNode(gid) {
    this._activeGid = gid;
    // 清除所有高亮
    this._world.querySelectorAll('.active-node, .active-parent, .active-sibling, .active-child')
      .forEach(el => el.classList.remove('active-node', 'active-parent', 'active-sibling', 'active-child'));

    if (!gid || !this._data) return;

    // 布局视图只做两态：自身蓝框 + 直接子节点淡蓝框
    const el = this._world.querySelector(`[data-gid="${gid}"]`);
    if (el) el.classList.add('active-node');

    const children = this._data.childMap.get(gid) || [];
    for (const child of children) {
      const childEl = this._world.querySelector(`[data-gid="${child.gid}"]`);
      if (childEl) childEl.classList.add('active-child');
    }

    // 点击卡片时同步更新当前线体标签和导航
    const lineRow = this._getLineForGid(gid);
    if (lineRow) this._setActiveLineGid(lineRow.gid);
  }

  /** 向上遍历父链，找到最近的 line_process 祖先 */
  _getLineForGid(gid) {
    const rowByGid = this._data?.rowByGid;
    if (!rowByGid) return null;
    let row = rowByGid.get(gid);
    while (row) {
      if (row.node_type === 'line_process') return row;
      if (!row.parent_bop_gid) return null;
      row = rowByGid.get(row.parent_bop_gid);
    }
    return null;
  }

  /** 根据视口中心坐标，找最近的线体（含命中优先） */
  _updateCurrentLineByViewport() {
    const lines = this._filteredLines;
    if (!lines || !lines.length) return;
    const vw = this._viewport.clientWidth;
    const vh = this._viewport.clientHeight;
    const wcX = (vw / 2 - this._panX) / this._zoom;
    const wcY = (vh / 2 - this._panY) / this._zoom;
    let bestLine = null;
    let bestDist = Infinity;
    for (const line of lines) {
      const pos = this._linePositions.get(line.gid);
      if (!pos) continue;
      // 视口中心落在线框内：直接命中
      if (wcX >= pos.x && wcX <= pos.x + pos.w && wcY >= pos.y && wcY <= pos.y + pos.h) {
        bestLine = line;
        break;
      }
      // 否则取中心距离最近的
      const dist = Math.hypot(wcX - (pos.x + pos.w / 2), wcY - (pos.y + pos.h / 2));
      if (dist < bestDist) { bestDist = dist; bestLine = line; }
    }
    if (bestLine) this._setActiveLineGid(bestLine.gid);
  }

  /** 同步更新标签文字和左侧导航激活项 */
  _setActiveLineGid(lineGid) {
    const line = (this._filteredLines || []).find(l => l.gid === lineGid);
    this._setCurrentLineLabel(line?.title || '');
    const navBody = document.getElementById('llLineNavBody');
    if (navBody) {
      navBody.querySelectorAll('.ll-line-nav-item').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.lineGid === lineGid);
      });
    }
  }

  // ══════════════════════════════════════════════════════════════════
  // 画布布局 — 线框
  // ══════════════════════════════════════════════════════════════════

  /** 类型筛选：是否显示该 row（null=全部，[]=全不选，[...]=白名单） */
  _passTypeFilter(row) {
    const tf = this._data?.typeFilter;
    if (tf === null || tf === undefined) return true;
    if (tf.length === 0) return false;
    return tf.includes(row.node_type);
  }

  /** 搜索高亮：返回带 <mark> 的 HTML 字符串，或 null（不匹配/无关键词） */
  _highlightTitle(title) {
    const st = this._data?.searchText;
    if (!st) return null;
    const idx = (title || '').toLowerCase().indexOf(st.toLowerCase());
    if (idx === -1) return null;
    return title.slice(0, idx)
      + `<mark class="lv-highlight">${title.slice(idx, idx + st.length)}</mark>`
      + title.slice(idx + st.length);
  }

  _buildLines() {
    // 查找所有 line_process 节点: 直接从所有行中搜索
    const lines = [];
    for (const r of this._data.rows) {
      if (r.node_type === 'line_process') lines.push(r);
    }

    // 应用线体筛选（level1Filter：null=全部，Set=只显示指定 gid）
    const l1Filter = this._data.level1Filter;
    const filteredLines = l1Filter === null ? lines :
      lines.filter(r => l1Filter.has(r.gid));

    // 保存供 _renderLineNav 使用
    this._filteredLines = filteredLines;

    if (filteredLines.length === 0) {
      this._world.innerHTML = '<div style="padding:40px;color:var(--overlay0,#6c7086);font-size:14px">无线体数据</div>';
      return;
    }

    // 恢复已有位置或自动排列
    let autoY = LL_LINE_PAD;
    for (const line of filteredLines) {
      const gid = line.gid;
      let pos = this._linePositions.get(gid);
      if (!pos) {
        // 先计算预估尺寸，后续 _layoutLineStations 会更新
        const stations = this._data.childMap.get(gid) || [];
        const estimatedW = Math.max(300, stations.length * (LL_STATION_W + LL_STATION_GAP) + LL_LINE_PAD * 2);
        const estimatedH = LL_ESTIMATED_LINE_H;
        pos = { x: LL_LINE_PAD, y: autoY, w: estimatedW, h: estimatedH };
        this._linePositions.set(gid, pos);
        autoY += estimatedH + LL_LINE_GAP_Y;
      }

      const box = document.createElement('div');
      box.className = 'll-line-box' + (this._editMode ? ' ll-draggable' : '');
      box.dataset.gid = gid;
      box.style.left = pos.x + 'px';
      box.style.top = pos.y + 'px';
      box.style.width = pos.w + 'px';
      box.style.height = pos.h + 'px';

      const title = document.createElement('div');
      title.className = 'll-line-title';
      title.textContent = line.title || '(未命名线体)';
      box.appendChild(title);

      // 线内布局容器
      const layoutDiv = document.createElement('div');
      layoutDiv.className = 'll-line-layout';
      layoutDiv.id = 'llLineLayout_' + gid;
      box.appendChild(layoutDiv);

      this._world.appendChild(box);
    }
  }

  // ══════════════════════════════════════════════════════════════════
  // 工位布局
  // ══════════════════════════════════════════════════════════════════

  _layoutAllStations() {
    const lines = this._world.querySelectorAll('.ll-line-box');
    for (const lineEl of lines) {
      const gid = lineEl.dataset.gid;
      this._layoutLineStations(gid);
    }

    // 重新堆叠线框位置，确保互不重叠
    let autoY = LL_LINE_PAD;
    for (const lineEl of lines) {
      const gid = lineEl.dataset.gid;
      const pos = this._linePositions.get(gid);
      if (!pos) continue;
      pos.y = autoY;
      lineEl.style.top = autoY + 'px';
      autoY += pos.h + LL_LINE_GAP_Y;
    }
  }

  /**
   * 为单条线计算工位布局
   */
  _layoutLineStations(lineGid) {
    const stations = this._data.childMap.get(lineGid) || [];
    const linePos = this._linePositions.get(lineGid);
    if (!linePos) return;

    const flowDir = this._lineFlowDirs.get(lineGid) || 'right';
    const isAsc = flowDir === 'right'; // 车流向右：seq_no 左→右递增；向左：递减

    // ── Step 1: 按后缀分类 ──────────────────────────────────────
    const explicitL = [], explicitR = [], explicitM = [], none = [];
    for (const s of stations) {
      const side = this._parseLRMSuffix(s.title);
      if (side === 'L')      { explicitL.push(s); s._effectiveSide = 'L'; }
      else if (side === 'R') { explicitR.push(s); s._effectiveSide = 'R'; }
      else if (side === 'M') { explicitM.push(s); s._effectiveSide = 'M'; }
      else                   { none.push(s); }
    }

    // ── Step 2: 各组按 seq_no 排序 ──────────────────────────────
    const sortFn = isAsc
      ? (a, b) => (a.seq_no ?? 0) - (b.seq_no ?? 0)
      : (a, b) => (b.seq_no ?? 0) - (a.seq_no ?? 0);
    explicitL.sort(sortFn);
    explicitR.sort(sortFn);
    explicitM.sort(sortFn);
    none.sort(sortFn);

    // ── Step 3: 构建列列表 ──────────────────────────────────────
    // 每列：{ top: L/M 工位, bottom: R 工位|null }
    // 列顺序：L/配对列 → M 列 → 未配对 R 列
    const columns = [];
    const usedExplicitR = new Set();

    // 3a: 显式 L 与 R 配对
    // 策略：先尝试按 seq_no 精确匹配；若均无法匹配（seq_no 相同或全为 null），
    //       则改用按排序后的位置索引配对（L[i] ↔ R[i]），避免所有 R 堆到末尾
    let seqNoMatchCount = 0;
    for (const l of explicitL) {
      if (explicitR.some(r => !usedExplicitR.has(r.gid) && r.seq_no != null && l.seq_no != null && r.seq_no === l.seq_no)) {
        seqNoMatchCount++;
      }
    }
    const useIndexPairing = seqNoMatchCount === 0; // 无 seq_no 匹配时改用索引配对

    for (let i = 0; i < explicitL.length; i++) {
      const l = explicitL[i];
      let match;
      if (!useIndexPairing) {
        match = explicitR.find(r => !usedExplicitR.has(r.gid) && r.seq_no === l.seq_no);
      } else {
        // 索引配对：L[i] 对应 R[i]（两者均按 seq_no 同向排序，位置对应）
        const unusedR = explicitR.filter(r => !usedExplicitR.has(r.gid));
        match = unusedR[0];
      }
      if (match) {
        usedExplicitR.add(match.gid);
        columns.push({ top: l, bottom: match });
      } else {
        columns.push({ top: l, bottom: null });
      }
    }

    // 3b: 无后缀工位 → 连续配对：(0,1)→(L,R), (2,3)→(L,R), ...
    for (let i = 0; i < none.length; i++) {
      const s = none[i];
      if (i % 2 === 0) {
        s._effectiveSide = 'L';
        const next = none[i + 1];
        if (next) {
          next._effectiveSide = 'R';
          columns.push({ top: s, bottom: next });
        } else {
          // 最后一个落单 → solo L
          columns.push({ top: s, bottom: null });
        }
      }
    }

    // 3c: M 工位 → 单独列（top 行，无 bottom）
    for (const m of explicitM) {
      columns.push({ top: m, bottom: null });
    }

    // 3d: 未配对的显式 R → 单独列（仅 bottom 行）
    for (const r of explicitR) {
      if (!usedExplicitR.has(r.gid)) {
        columns.push({ top: null, bottom: r });
      }
    }

    // ── Step 4: 线框尺寸 ────────────────────────────────────────
    // 计算纵向子卡片空间：遍历所有工位，计算内外两层纵向堆叠的最大总高度
    let maxChildVert = LL_CHILD_PAD;
    for (const s of stations) {
      const kids        = this._data.childMap.get(s.gid) || [];
      const operators   = kids.filter(r => r.node_type === 'operator_process');
      const manCards    = kids.filter(r => r.node_type === 'man');
      const directProcs = kids.filter(r => r.node_type === 'process');
      let totalH = 0, groupCount = 0;
      if (manCards.length) {
        totalH += manCards.length * LL_RING_CARD_H + (manCards.length - 1) * LL_LAYER_CARD_GAP;
        groupCount++;
      }
      for (const op of operators) {
        const opProcs = (this._data.childMap.get(op.gid) || []).filter(r => r.node_type === 'process');
        const n = 1 + opProcs.length;
        totalH += n * LL_RING_CARD_H + (n - 1) * LL_LAYER_CARD_GAP;
        groupCount++;
      }
      if (directProcs.length) {
        totalH += directProcs.length * LL_RING_CARD_H + (directProcs.length - 1) * LL_LAYER_CARD_GAP;
        groupCount++;
      }
      if (totalH > 0) totalH += groupCount * LL_LAYER_GAP;
      maxChildVert = Math.max(maxChildVert, totalH);
    }
    const childSpace = maxChildVert;
    const lineH = childSpace + LL_LINE_PAD + LL_STATION_H + LL_CAR_AREA_H + LL_STATION_H + LL_LINE_PAD + childSpace;

    const totalCols = Math.max(columns.length, 1);
    const lineW = totalCols * LL_STATION_W + (totalCols - 1) * LL_STATION_GAP + LL_LINE_PAD * 2;
    linePos.w = lineW;
    linePos.h = Math.max(lineH, linePos.h || 200);

    // 更新线框 DOM 尺寸
    const lineEl = this._world.querySelector(`.ll-line-box[data-gid="${lineGid}"]`);
    if (lineEl) {
      lineEl.style.width = linePos.w + 'px';
      lineEl.style.height = linePos.h + 'px';
    }

    // ── Step 5: 放置工位 + 记录展开方向 ──────────────────────────
    // columns[i].top = L/M/none-even（默认上行），.bottom = R/none-odd（默认下行）
    // flowDir='right': col.top → topY(向上展开)，col.bottom → bottomY(向下展开)
    // flowDir='left':  col.top → bottomY(向下展开)，col.bottom → topY(向上展开)
    // 即：L 在下行、R 在上行，从车流方向看序号递增
    const topY    = childSpace + LL_LINE_PAD;
    const bottomY = childSpace + LL_LINE_PAD + LL_STATION_H + LL_CAR_AREA_H;

    // 存储车俯视图区域信息，供 _renderLineCarArea 使用
    this._lineCarAreas.set(lineGid, { topY, flowDir, columns });

    for (let i = 0; i < columns.length; i++) {
      const col = columns[i];
      const cx = LL_LINE_PAD + i * (LL_STATION_W + LL_STATION_GAP) + LL_STATION_W / 2;

      // 根据 flowDir 决定 col.top 和 col.bottom 对应的 Y 行
      const topSlotY    = flowDir === 'right' ? topY    : bottomY;
      const bottomSlotY = flowDir === 'right' ? bottomY : topY;
      const topSlotDir    = flowDir === 'right' ? 'up'   : 'down';
      const bottomSlotDir = flowDir === 'right' ? 'down' : 'up';

      if (col.top) {
        this._stationPositions.set(col.top.gid, { x: cx - LL_STATION_W / 2, y: topSlotY });
        this._stationDirection.set(col.top.gid, topSlotDir);
      }
      if (col.bottom) {
        this._stationPositions.set(col.bottom.gid, { x: cx - LL_STATION_W / 2, y: bottomSlotY });
        this._stationDirection.set(col.bottom.gid, bottomSlotDir);
      }
    }

  }

  // ══════════════════════════════════════════════════════════════════
  // 卡片渲染
  // ══════════════════════════════════════════════════════════════════

  _renderAllCards() {
    const lines = this._world.querySelectorAll('.ll-line-box');
    for (const lineEl of lines) {
      const layoutEl = lineEl.querySelector('.ll-line-layout');
      if (!layoutEl) continue;
      layoutEl.innerHTML = '';

      const lineGid = lineEl.dataset.gid;
      const stations = this._data.childMap.get(lineGid) || [];

      if (stations.length === 0) {
        layoutEl.innerHTML = '<div class="ll-line-empty">无工位</div>';
        continue;
      }

      for (const station of stations) {
        const pos = this._stationPositions.get(station.gid);
        if (!pos) continue;

        const direction = this._stationDirection.get(station.gid) || 'up';
        const card = this._createStationCard(station, direction);
        card.style.left = pos.x + 'px';
        card.style.top = pos.y + 'px';
        layoutEl.appendChild(card);

        this._renderStationChildren(station.gid, layoutEl, pos.x, pos.y, direction);
      }

      const carAreaInfo = this._lineCarAreas.get(lineGid);
      if (carAreaInfo) this._renderLineCarArea(layoutEl, carAreaInfo);
      this._renderLineFlowArrows(lineGid, lineEl);
    }
  }

  /**
   * 渲染工位子节点 — 从工位框边沿向外逐层展开
   *
   * L/M/none（direction=up）: 子卡片从框上边沿往上展开
   *   - 内层（人/岗）紧贴上边沿
   *   - 中层（设备/工具）往上偏移
   *   - 外层（工序）再往上偏移
   *
   * R（direction=down）: 子卡片从框下边沿往下展开
   *   - 内层（人/岗）紧贴下边沿
   *   - 中层（设备/工具）往下偏移
   *   - 外层（工序）再往下偏移
   */
  _renderStationChildren(stationGid, parentEl, sx, sy, direction) {
    const children = this._data.childMap.get(stationGid) || [];
    if (children.length === 0) return 0;

    const isDown = direction === 'down';
    const cardX  = sx + (LL_STATION_W - LL_RING_CARD_W) / 2;
    let Y = isDown ? sy + LL_STATION_H + LL_LAYER_GAP : sy - LL_LAYER_GAP;

    // 放置一张卡片，返回 {top, bottom}
    const place = (el, h) => {
      const top = isDown ? Y : Y - h;
      el.style.position = 'absolute';
      el.style.left   = cardX + 'px';
      el.style.top    = top + 'px';
      el.style.width  = LL_RING_CARD_W + 'px';
      el.style.height = h + 'px';
      parentEl.appendChild(el);
      Y += isDown ? h + LL_LAYER_CARD_GAP : -(h + LL_LAYER_CARD_GAP);
      return { top, bottom: top + h };
    };

    const addGap = () => {
      Y += isDown ? LL_LAYER_GAP - LL_LAYER_CARD_GAP : -(LL_LAYER_GAP - LL_LAYER_CARD_GAP);
    };

    const operators       = children.filter(r => r.node_type === 'operator_process' && this._passTypeFilter(r));
    const manCards        = children.filter(r => r.node_type === 'man' && this._passTypeFilter(r));
    const directProcesses = children.filter(r => r.node_type === 'process' && this._passTypeFilter(r));

    const framesToDraw = []; // { bounds, opGid }

    // 1. 人员卡片
    for (const man of manCards) place(this._createRingCard(man), LL_RING_CARD_H);
    if (manCards.length > 0 && (operators.length > 0 || directProcesses.length > 0)) addGap();

    // 2. 岗位分组（岗位 + 其工序子节点）
    for (let oi = 0; oi < operators.length; oi++) {
      const op         = operators[oi];
      const opProcesses = (this._data.childMap.get(op.gid) || []).filter(r => r.node_type === 'process' && this._passTypeFilter(r));
      const groupBounds = [];

      // 无论向上/向下：岗位靠近工位（先放），工序向外延伸（后放）
      groupBounds.push(place(this._createRingCard(op), LL_RING_CARD_H));
      for (const proc of opProcesses) groupBounds.push(place(this._createRingCard(proc), LL_RING_CARD_H));

      if (opProcesses.length > 0) framesToDraw.push({ bounds: groupBounds, opGid: op.gid });
      if (oi < operators.length - 1) addGap();
    }

    // 3. 直挂工位的工序（无岗位中间层）
    if (directProcesses.length > 0) {
      if (operators.length > 0 || manCards.length > 0) addGap();
      for (const proc of directProcesses) place(this._createRingCard(proc), LL_RING_CARD_H);
    }

    // 4. 绘制岗位分组框（插入所有卡片之前，以便 z-index 在卡片下方）
    const pad = LL_OP_GROUP_PAD;
    for (const { bounds, opGid } of framesToDraw) {
      const fTop    = Math.min(...bounds.map(b => b.top))    - pad;
      const fBottom = Math.max(...bounds.map(b => b.bottom)) + pad;
      const frame   = document.createElement('div');
      frame.className      = 'll-op-group-frame';
      frame.dataset.opGid  = opGid;
      frame.style.left     = (cardX - pad) + 'px';
      frame.style.top      = fTop + 'px';
      frame.style.width    = (LL_RING_CARD_W + 2 * pad) + 'px';
      frame.style.height   = (fBottom - fTop) + 'px';
      parentEl.insertBefore(frame, parentEl.firstChild);
    }

    return children.length;
  }

  /**
   * 创建工位中心卡片 — 按侧边分包，L/R/M/none 各有独立构建方法
   */
  _createStationCard(row, direction = 'up') {
    const card = document.createElement('div');
    const side = row._effectiveSide || this._parseLRMSuffix(row.title);
    const sideCls = side ? ' station-side-' + side : ' station-side-none';
    const editable = this._editMode ? ' ll-draggable' : '';

    card.className = 'll-station-card' + sideCls + editable;
    card.dataset.gid = row.gid;
    card.style.width = LL_STATION_W + 'px';
    card.style.height = LL_STATION_H + 'px';

    this._buildStationContent(card, row, side, direction);
    return card;
  }

  /**
   * 统一工位内容构建（替代旧的 L/R/M/Default 四个方法）
   * 徽标位置由 direction 决定，与 L/R/M 值无关
   */
  _buildStationContent(card, row, side, direction) {
    // 主内容区（左侧，flex:1）
    const mainWrap = document.createElement('div');
    mainWrap.className = 'll-station-main';

    const titleDiv = document.createElement('div');
    titleDiv.className = 'll-station-title';
    const stationTitleHL = this._highlightTitle(row.title || '');
    if (stationTitleHL) {
      titleDiv.innerHTML = stationTitleHL;
      card.classList.add('ll-search-hit');
    } else {
      titleDiv.textContent = row.title || '(未命名)';
    }
    mainWrap.appendChild(titleDiv);

    const subDiv = document.createElement('div');
    subDiv.className = 'll-station-sub';
    subDiv.textContent = (NT_ABBR[row.node_type] || row.node_type) + ' | ' + (row.seq_no ?? '—');
    mainWrap.appendChild(subDiv);

    card.appendChild(mainWrap);

    // 右侧设备/工具统计
    const equipCount = this._collectDeepByTypes(row.gid, ['equipment_factory', 'equipment_need']).length;
    const toolCount  = this._collectDeepByTypes(row.gid, ['tool_factory', 'tool_need', 'fixture_factory', 'fixture_need']).length;
    if (equipCount > 0 || toolCount > 0) {
      const statsWrap = document.createElement('div');
      statsWrap.className = 'll-station-stats';
      if (equipCount > 0) {
        const eq = document.createElement('div');
        eq.className = 'll-station-stat-row';
        eq.textContent = '设备 ' + equipCount;
        statsWrap.appendChild(eq);
      }
      if (toolCount > 0) {
        const tl = document.createElement('div');
        tl.className = 'll-station-stat-row';
        tl.textContent = '工具 ' + toolCount;
        statsWrap.appendChild(tl);
      }
      card.appendChild(statsWrap);
    }

    // 徽标：direction='up'（上展开）→ 左下角；direction='down'（下展开）→ 左上角
    if (side) {
      const lrm = document.createElement('div');
      lrm.className = 'll-station-lrm lrm-' + side + (direction === 'down' ? ' lrm-pos-top' : ' lrm-pos-bottom');
      lrm.textContent = side;
      card.appendChild(lrm);
    }
  }

  /**
   * 创建工位子卡片 — 复用列视图卡片结构（lv-card-main + lv-stats-box）
   */
  _createRingCard(row) {
    const el = document.createElement('div');
    el.className = 'll-ring-card' + (this._editMode ? ' ll-draggable' : '');
    el.dataset.gid = row.gid;
    // 复用列视图卡片的 flex 横向布局；覆盖 .ll-ring-card 的默认 padding（由 lv-card-main 接管）
    el.style.cssText = 'display:flex;align-items:stretch;padding:0;overflow:hidden';

    // 主内容区 — 与列视图 _renderCard 保持一致
    const mainEl = document.createElement('div');
    mainEl.className = 'lv-card-main';

    // 行1：类型标签 + 挂载徽标 + 右侧编码
    const row1El = document.createElement('div');
    row1El.className = 'lv-row1';
    const typeEl = document.createElement('span');
    typeEl.className = 'lv-type lv-nt-' + (row.node_type || 'part');
    typeEl.textContent = NT_ABBR[row.node_type] || row.node_type || '—';
    row1El.appendChild(typeEl);

    // 挂载状态徽标
    const _valid = row.valid_primary_link_count || 0;
    const _total = row.primary_link_count || 0;
    if (_total > 0) {
      const lb = document.createElement('span');
      if (_valid > 0) {
        lb.className = 'lv-link-badge';
        lb.textContent = _valid;
        lb.title = `已挂载 ${_valid} 个有效实体`;
      } else {
        lb.className = 'lv-link-badge lv-link-badge-stale';
        lb.textContent = '⚠';
        lb.title = `挂载引用已过时（${_total} 条），请重跑 Auto-Link 更新`;
      }
      row1El.appendChild(lb);
    }

    if (row.bom_row_id) {
      const seqEl = document.createElement('span');
      seqEl.style.cssText = 'font-size:10px;color:var(--subtext0,#a6adc8);margin-left:auto;white-space:nowrap';
      seqEl.textContent = row.bom_row_id;
      row1El.appendChild(seqEl);
    }

    // 行2：标题
    const row2El = document.createElement('div');
    row2El.className = 'lv-row2';
    const titleEl = document.createElement('span');
    titleEl.className = 'lv-title';
    titleEl.title = row.title || '';
    const titleHL = this._highlightTitle(row.title || '');
    if (titleHL) {
      titleEl.innerHTML = titleHL;
      el.classList.add('ll-search-hit');
    } else {
      titleEl.textContent = row.title || '(无名称)';
    }
    row2El.appendChild(titleEl);

    mainEl.appendChild(row1El);
    mainEl.appendChild(row2El);
    el.appendChild(mainEl);

    // 右侧统计框 — 复用列视图全局函数
    el.appendChild(_renderStatsBox(row));

    return el;
  }

  /**
   * 创建紧凑型卡片（设备/工具）— 与列视图卡片风格一致
   */
  _createCompactCard(row) {
    const el = document.createElement('div');
    el.className = 'll-ring-card' + (this._editMode ? ' ll-draggable' : '');
    el.dataset.gid = row.gid;

    const row1 = document.createElement('div');
    row1.style.cssText = 'display:flex;align-items:center;gap:4px;width:100%;overflow:hidden';
    const typeEl = document.createElement('span');
    typeEl.className = 'lv-type lv-nt-' + (row.node_type || 'part');
    typeEl.textContent = NT_ABBR[row.node_type] || row.node_type;
    row1.appendChild(typeEl);

    // 挂载状态徽标（紧凑版）
    const _cValid = row.valid_primary_link_count || 0;
    const _cTotal = row.primary_link_count || 0;
    if (_cTotal > 0) {
      const clb = document.createElement('span');
      if (_cValid > 0) {
        clb.className = 'lv-link-badge';
        clb.textContent = _cValid;
        clb.title = `已挂载 ${_cValid} 个有效实体`;
      } else {
        clb.className = 'lv-link-badge lv-link-badge-stale';
        clb.textContent = '⚠';
        clb.title = `挂载引用已过时（${_cTotal} 条），请重跑 Auto-Link 更新`;
      }
      row1.appendChild(clb);
    }

    const titleEl = document.createElement('span');
    titleEl.style.cssText = 'font-size:11px;color:var(--text,#cdd6f4);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1';
    titleEl.textContent = row.title || '';
    row1.appendChild(titleEl);
    el.appendChild(row1);
    return el;
  }

  // ══════════════════════════════════════════════════════════════════
  // 工具方法
  // ══════════════════════════════════════════════════════════════════

  /**
   * 在线体框的左右两侧渲染车流方向箭头
   * - 编辑模式下可点击切换方向
   * - 基于 direction 定位，与 L/R/M 值无关
   */
  _renderLineFlowArrows(lineGid, lineEl) {
    lineEl.querySelectorAll('.ll-flow-arrow').forEach(el => el.remove());

    const flowDir = this._lineFlowDirs.get(lineGid) || 'right';
    const symbol  = flowDir === 'right' ? '→' : '←';
    const tip     = flowDir === 'right' ? '车流向右（点击切换）' : '车流向左（点击切换）';

    ['start', 'end'].forEach(pos => {
      const btn = document.createElement('div');
      btn.className = 'll-flow-arrow ll-flow-arrow-' + pos;
      btn.textContent = symbol;
      btn.title = this._editMode ? tip : (flowDir === 'right' ? '车流向右' : '车流向左');
      if (this._editMode) {
        btn.classList.add('ll-flow-arrow-editable');
        btn.addEventListener('click', e => {
          e.stopPropagation();
          this._toggleFlowDir(lineGid);
        });
      }
      lineEl.appendChild(btn);
    });
  }

  /**
   * 切换指定线体的车流方向，并重新布局 + 重绘
   */
  _toggleFlowDir(lineGid) {
    const cur = this._lineFlowDirs.get(lineGid) || 'right';
    const next = cur === 'right' ? 'left' : 'right';
    this._lineFlowDirs.set(lineGid, next);
    this._saveFlowDirs();
    this._layoutLineStations(lineGid);
    this._renderAllCards();
    this._updateMinimap();
  }

  /**
   * 在 L/R 工位行之间，为每列渲染一个方向箭头 + 6 个岗位编号占位
   * @param {HTMLElement} layoutEl
   * @param {{ topY:number, flowDir:string, columns:Array }} info
   */
  _renderLineCarArea(layoutEl, { topY, flowDir, columns }) {
    const carAreaTop = topY + LL_STATION_H;
    const midY = carAreaTop + Math.round(LL_CAR_AREA_H / 2);
    const arrowW = 72, arrowH = 48;
    const isRight = flowDir === 'right';

    for (let i = 0; i < columns.length; i++) {
      const cx = LL_LINE_PAD + i * (LL_STATION_W + LL_STATION_GAP) + Math.round(LL_STATION_W / 2);

      // 方向箭头（始终朝右的 SVG，向左时 scaleX(-1)）
      const arrowWrap = document.createElement('div');
      arrowWrap.className = 'll-car-wrap';
      arrowWrap.style.left   = (cx - Math.round(arrowW / 2)) + 'px';
      arrowWrap.style.top    = (midY - Math.round(arrowH / 2)) + 'px';
      arrowWrap.style.width  = arrowW + 'px';
      arrowWrap.style.height = arrowH + 'px';
      if (!isRight) arrowWrap.style.transform = 'scaleX(-1)';
      arrowWrap.innerHTML = this._getArrowSVG();
      layoutEl.appendChild(arrowWrap);

      // 6 个岗位编号占位（前/后随 flowDir 换边；左/右侧上下固定）
      // dx/dy 相对于列中心 (cx, midY)
      const slotDefs = [
        { n: 'A', dx: isRight ?  41 : -63,   dy: -10 },  // 前
        { n: 'B', dx: isRight ?   5 : -27,   dy: -49 },  // 左前（上行近前端）
        { n: 'C', dx: isRight ? -27 :   5,   dy: -49 },  // 左后（上行近后端）
        { n: 'D', dx: isRight ?   5 : -27,   dy:  29 },  // 右前（下行近前端）
        { n: 'E', dx: isRight ? -27 :   5,   dy:  29 },  // 右后（下行近后端）
        { n: 'F', dx: isRight ? -63 :  41,   dy: -10 },  // 后
      ];
      for (const { n, dx, dy } of slotDefs) {
        const slot = document.createElement('div');
        slot.className = 'll-op-slot';
        slot.style.left = (cx + dx) + 'px';
        slot.style.top  = (midY + dy) + 'px';
        slot.textContent = n;
        layoutEl.appendChild(slot);
      }
    }
  }

  /**
   * 返回右向填充箭头 SVG（flowDir='left' 时容器 scaleX(-1) 翻转）
   */
  _getArrowSVG() {
    return `<svg width="72" height="48" viewBox="0 0 72 48" xmlns="http://www.w3.org/2000/svg">
      <path d="M4 18 H48 L48 8 L68 24 L48 40 L48 30 H4 Z"
        fill="rgba(137,180,250,0.38)" stroke="rgba(137,180,250,0.62)" stroke-width="1.5"
        stroke-linejoin="round"/>
    </svg>`;
  }

  /**
   * 持久化所有线体的车流方向到 localStorage
   */
  _saveFlowDirs() {
    try {
      const existing = JSON.parse(localStorage.getItem(this._lsKey()) || '{}');
      existing.layoutVersion = LL_LAYOUT_VERSION;
      const data = {};
      for (const [gid, dir] of this._lineFlowDirs) data[gid] = dir;
      existing.flowDirs = data;
      localStorage.setItem(this._lsKey(), JSON.stringify(existing));
    } catch { /* ignore */ }
  }

  /**
   * 从 stationGid 的整棵子树中深度收集指定类型的节点（BFS，去重）
   */
  _collectDeepByTypes(stationGid, types) {
    const result = [];
    const seen = new Set();
    const queue = [stationGid];
    while (queue.length > 0) {
      const gid = queue.shift();
      const kids = this._data.childMap.get(gid) || [];
      for (const kid of kids) {
        if (seen.has(kid.gid)) continue;
        seen.add(kid.gid);
        if (types.includes(kid.node_type)) {
          result.push(kid);
        }
        queue.push(kid.gid);
      }
    }
    return result;
  }

  /**
   * 从标题解析 L/R/M 后缀
   */
  _parseLRMSuffix(title) {
    // 匹配末尾的 L/R/M，前面可以是 -/_（显式分隔符）或数字（如"工位01L"）
    const m = title?.match(/(?:[-_]|\d)([LRM])$/i);
    return m ? m[1].toUpperCase() : null;
  }

  // ══════════════════════════════════════════════════════════════════
  // 变换系统
  // ══════════════════════════════════════════════════════════════════

  _setTransform() {
    this._world.style.transform = `translate(${this._panX}px, ${this._panY}px) scale(${this._zoom})`;
    this._updateCurrentLineByViewport();
  }

  /**
   * 仅在缩放变化时更新 CSS 变量和 LOD（比 _setTransform 开销大，不与平移耦合）
   */
  _syncZoomDependent() {
    this._world.style.setProperty('--ll-zoom', this._zoom);
    this._updateLOD();
  }

  _updateLOD() {
    const isLOD = this._zoom < LL_LOD_THRESHOLD;
    this._world.classList.toggle('ll-lod', isLOD);
  }

  _zoomAt(factor, vpX, vpY) {
    const newZoom = Math.max(LL_MIN_ZOOM, Math.min(LL_MAX_ZOOM, this._zoom * factor));
    const worldX = (vpX - this._panX) / this._zoom;
    const worldY = (vpY - this._panY) / this._zoom;
    this._zoom = newZoom;
    this._panX = vpX - worldX * newZoom;
    this._panY = vpY - worldY * newZoom;
    this._setTransform();
    this._syncZoomDependent();
    this._updateZoomLabel();
    this._syncMinimapViewport();
  }

  _screenToWorld(clientX, clientY) {
    const vr = this._viewport.getBoundingClientRect();
    return {
      x: (clientX - vr.left - this._panX) / this._zoom,
      y: (clientY - vr.top - this._panY) / this._zoom,
    };
  }

  _updateZoomLabel() {
    if (this._zoomPctEl) {
      this._zoomPctEl.textContent = Math.round(this._zoom * 100) + '%';
    }
  }

  /**
   * 根据所有线框及其子卡片计算世界尺寸，确保背景网点覆盖所有元素
   */
  _updateWorldSize() {
    // 计算所有内容元素的边界框
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    const allEls = this._world.querySelectorAll('.ll-line-box, .ll-station-card, .ll-ring-card');
    for (const el of allEls) {
      const x = parseFloat(el.style.left) || 0;
      const y = parseFloat(el.style.top) || 0;
      const w = parseFloat(el.style.width) || 100;
      const h = parseFloat(el.style.height) || 50;
      minX = Math.min(minX, x);
      minY = Math.min(minY, y);
      maxX = Math.max(maxX, x + w);
      maxY = Math.max(maxY, y + h);
    }
    if (minX === Infinity) return;
    // 外扩 padding 确保四边留白
    const pad = 200;
    this._world.style.minWidth  = (maxX + pad) + 'px';
    this._world.style.minHeight = (maxY + pad) + 'px';
  }

  /**
   * 自动适配：缩放并平移，让所有线框在视口内完整可见
   * (100% 即恰好全都看到)
   */
  _fitToScreen() {
    const lines = this._world.querySelectorAll('.ll-line-box');
    if (lines.length === 0) return;

    // 计算所有线框的世界坐标包围盒
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const el of lines) {
      const x = parseFloat(el.style.left) || 0;
      const y = parseFloat(el.style.top) || 0;
      const w = parseFloat(el.style.width) || 300;
      const h = parseFloat(el.style.height) || 200;
      minX = Math.min(minX, x);
      minY = Math.min(minY, y);
      maxX = Math.max(maxX, x + w);
      maxY = Math.max(maxY, y + h);
    }

    if (minX === Infinity) return;

    const contentW = maxX - minX;
    const contentH = maxY - minY;
    const pad = LL_LINE_PAD * 2; // 两边留白
    const vpW = this._viewport.clientWidth;
    const vpH = this._viewport.clientHeight;

    // 计算缩放使内容恰好填满视口（留边距 pad）
    const scaleX = (vpW - pad) / contentW;
    const scaleY = (vpH - pad) / contentH;
    let zoom = Math.min(scaleX, scaleY);

    // 限制最小缩放避免太大或太小
    zoom = Math.min(zoom, 1);
    zoom = Math.max(zoom, LL_MIN_ZOOM);

    // 居中平移
    const cx = minX + contentW / 2;
    const cy = minY + contentH / 2;
    this._zoom = zoom;
    this._panX = vpW / 2 - cx * zoom;
    this._panY = vpH / 2 - cy * zoom;
    this._setTransform();
    this._syncZoomDependent();
    this._updateZoomLabel();
  }

  // ══════════════════════════════════════════════════════════════════
  // 事件绑定
  // ══════════════════════════════════════════════════════════════════

  _bindEvents() {
    const vp = this._viewport;

    // ── 鼠标滚轮：Shift+滚轮=水平平移，普通滚轮=缩放 ──
    vp.addEventListener('wheel', e => {
      e.preventDefault();
      if (e.shiftKey) {
        // Shift+滚轮：水平平移
        const delta = e.deltaY !== 0 ? e.deltaY : e.deltaX;
        this._panX -= delta;
        this._setTransform();
        this._syncMinimapViewport();
      } else {
        const factor = e.deltaY < 0 ? 1.1 : 0.9;
        this._zoomAt(factor, e.clientX, e.clientY);
      }
    }, { passive: false });

    // ── 中键平移 ──
    vp.addEventListener('mousedown', e => {
      if (e.button === 1) {
        e.preventDefault();
        this._startPan(e.clientX, e.clientY);
      }
    });

    // ── 空格+左键平移 ──
    document.addEventListener('keydown', e => {
      if (e.code === 'Space') {
        this._spaceDown = true;
        e.preventDefault();
      }
    });
    document.addEventListener('keyup', e => {
      if (e.code === 'Space') {
        this._spaceDown = false;
      }
    });

    vp.addEventListener('mousedown', e => {
      if (e.button === 0 && this._spaceDown) {
        e.preventDefault();
        this._startPan(e.clientX, e.clientY);
        return;
      }

      // 重挂拖拽：岗位/工序卡片（非编辑模式）
      if (e.button === 0 && !this._editMode) {
        const ringCard = e.target.closest('.ll-ring-card');
        if (ringCard) {
          const gid = ringCard.dataset.gid;
          const row = this._data?.rowByGid.get(gid);
          if (row && (row.node_type === 'operator_process' || row.node_type === 'process')) {
            e.preventDefault();
            this._reparentPending = { el: ringCard, row, startX: e.clientX, startY: e.clientY };
            return;
          }
        }
      }

      // 卡片点击（高亮）
      const card = e.target.closest('[data-gid]');
      if (card && !e.target.closest('.ll-draggable')) {
        const gid = card.dataset.gid;
        if (this._data) {
          this.highlightNode(gid);
          if (this._data.applyActiveState) this._data.applyActiveState(gid);
          this._data.refreshOverlayIfPinned?.(gid);
        }
        return;
      }

      // 编辑拖拽
      if (this._editMode) {
        const lineBox = e.target.closest('.ll-line-box.ll-draggable');
        if (lineBox) {
          e.preventDefault();
          this._startDrag('line', lineBox.dataset.gid, e.clientX, e.clientY);
          return;
        }
        const ringCard = e.target.closest('.ll-ring-card.ll-draggable, .ll-station-card.ll-draggable');
        if (ringCard) {
          e.preventDefault();
          this._startDrag('card', ringCard.dataset.gid, e.clientX, e.clientY);
          return;
        }
      }
    });

    // ── 鼠标移动（平移/拖拽/重挂） ──
    vp.addEventListener('mousemove', e => {
      if (this._panState) {
        const dx = e.clientX - this._panState.startX;
        const dy = e.clientY - this._panState.startY;
        this._panX = this._panState.origPanX + dx;
        this._panY = this._panState.origPanY + dy;
        this._setTransform();
        // 平移期间防抖：不每帧更新缩略图视口
        return;
      }
      if (this._dragState) {
        this._onDragMove(e.clientX, e.clientY);
        return;
      }
      // 重挂拖拽：超过阈值后激活
      if (this._reparentPending) {
        const dx = e.clientX - this._reparentPending.startX;
        const dy = e.clientY - this._reparentPending.startY;
        if (Math.abs(dx) > 5 || Math.abs(dy) > 5) {
          this._activateReparentDrag(this._reparentPending);
          this._reparentPending = null;
        }
        return;
      }
      if (this._reparentDrag) {
        this._onReparentDragMove(e);
      }
    });

    // ── 鼠标释放 ──
    vp.addEventListener('mouseup', e => {
      if (this._panState) {
        this._panState = null;
        vp.style.cursor = '';
      }
      if (this._dragState) {
        this._onDragEnd();
      }
      // 重挂：pending → 视为点击
      if (this._reparentPending) {
        const { row } = this._reparentPending;
        this._reparentPending = null;
        this.highlightNode(row.gid);
        if (this._data?.applyActiveState) this._data.applyActiveState(row.gid);
        return;
      }
      // 重挂：active → 提交
      if (this._reparentDrag) {
        this._commitReparent();
      }
    });

    // ── 鼠标离开画布 ──
    vp.addEventListener('mouseleave', () => {
      if (this._panState) {
        this._panState = null;
        vp.style.cursor = '';
      }
      if (this._reparentDrag) {
        this._cancelReparentDrag();
      }
      this._reparentPending = null;
    });

    // ── 双击卡片主体区打开覆盖面板（排除统计区） ──
    vp.addEventListener('dblclick', e => {
      if (e.target.closest('.lv-stats-box')) return;
      const card = e.target.closest('[data-gid]');
      if (card && this._data && this._data.openOverlayPanel) {
        this._data.openOverlayPanel(card.dataset.gid);
      }
    });

    // ── 统计区点击：有图片→灯箱预览；无图→统计浮框 ──
    vp.addEventListener('click', e => {
      const box = e.target.closest('.lv-stats-box');
      if (!box) return;
      e.stopPropagation();
      const gid = box.dataset.statsGid;
      if (box.querySelector('.lv-stats-thumb-fill')) {
        const row = this._data?.rowByGid.get(gid);
        const pics = [];
        for (const field of ['process_flow_pic', 'process_chart_pic']) {
          const val = row?.[field];
          if (Array.isArray(val)) val.forEach(p => { const s = typeof p === 'string' ? p : (p?.url || p?.src || ''); if (s) pics.push(s); });
          else if (typeof val === 'string' && val) pics.push(val);
        }
        if (pics.length && this._data?.openImageLightbox) this._data.openImageLightbox(pics);
      } else {
        if (this._data?.showDetailPopover) this._data.showDetailPopover(gid, box);
      }
    });

    // ── 右键卡片弹出菜单 ──
    vp.addEventListener('contextmenu', e => {
      const card = e.target.closest('[data-gid]');
      if (!card) return;
      e.preventDefault();
      const gid = card.dataset.gid;
      this.highlightNode(gid);
      if (this._data && this._data.showCtxMenu) {
        this._data.showCtxMenu(e.clientX, e.clientY, gid);
      }
    });
  }

  /**
   * 绑定画布内缩放按钮
   */
  _bindZoomControls() {
    const zoomIn = this._container.querySelector('#llZoomIn');
    const zoomOut = this._container.querySelector('#llZoomOut');
    if (zoomIn) {
      zoomIn.addEventListener('click', () => {
        const vpRect = this._viewport.getBoundingClientRect();
        this._zoomAt(1.3, vpRect.left + vpRect.width / 2, vpRect.top + vpRect.height / 2);
      });
    }
    if (zoomOut) {
      zoomOut.addEventListener('click', () => {
        const vpRect = this._viewport.getBoundingClientRect();
        this._zoomAt(0.77, vpRect.left + vpRect.width / 2, vpRect.top + vpRect.height / 2);
      });
    }
  }

  // ── 平移 ──

  _startPan(clientX, clientY) {
    this._panState = {
      startX: clientX,
      startY: clientY,
      origPanX: this._panX,
      origPanY: this._panY,
    };
    this._viewport.style.cursor = 'grabbing';
  }

  // ── 拖拽 ──

  _startDrag(type, gid, clientX, clientY) {
    if (type === 'line') {
      const linePos = this._linePositions.get(gid);
      if (!linePos) return;
      this._dragState = {
        type,
        gid,
        startX: clientX,
        startY: clientY,
        origX: linePos.x,
        origY: linePos.y,
      };
    } else {
      const el = this._world.querySelector(`[data-gid="${gid}"]`);
      if (!el) return;
      this._dragState = {
        type,
        gid,
        el,
        startX: clientX,
        startY: clientY,
        origX: parseFloat(el.style.left) || 0,
        origY: parseFloat(el.style.top) || 0,
      };
    }
  }

  _onDragMove(clientX, clientY) {
    const ds = this._dragState;
    if (!ds) return;

    const world = this._screenToWorld(clientX, clientY);
    const startWorld = this._screenToWorld(ds.startX, ds.startY);
    const dx = world.x - startWorld.x;
    const dy = world.y - startWorld.y;

    if (ds.type === 'line') {
      const pos = this._linePositions.get(ds.gid);
      if (!pos) return;
      pos.x = ds.origX + dx;
      pos.y = ds.origY + dy;
      const el = this._world.querySelector(`.ll-line-box[data-gid="${ds.gid}"]`);
      if (el) {
        el.style.left = pos.x + 'px';
        el.style.top = pos.y + 'px';
      }
    } else if (ds.type === 'card') {
      const newX = ds.origX + dx;
      const newY = ds.origY + dy;
      ds.el.style.left = newX + 'px';
      ds.el.style.top = newY + 'px';
    }
  }

  _onDragEnd() {
    if (!this._dragState) return;

    const ds = this._dragState;
    if (ds.type === 'line') {
      // 保存线框位置
      this._saveLinePositions();
    } else if (ds.type === 'card') {
      // 如果是工位卡片，更新 stationPositions
      const stationEl = ds.el.closest('.ll-station-card');
      if (stationEl) {
        const gid = stationEl.dataset.gid;
        if (gid) {
          this._stationPositions.set(gid, {
            x: parseFloat(stationEl.style.left),
            y: parseFloat(stationEl.style.top),
          });
          this._saveStationPositions();
        }
      }
    }

    this._dragState = null;

    // 拖拽后更新缩略图（重新计算全部）
    this._renderMinimap();
  }

  // ══════════════════════════════════════════════════════════════════
  // 线体导航列表
  // ══════════════════════════════════════════════════════════════════

  _renderLineNav() {
    const navBody = document.getElementById('llLineNavBody');
    if (!navBody) return;
    navBody.innerHTML = '';

    const lines = this._filteredLines || [];
    lines.forEach((line, idx) => {
      const btn = document.createElement('button');
      btn.className = 'll-line-nav-item' + (idx === 0 ? ' active' : '');
      btn.dataset.lineGid = line.gid;
      btn.title = line.title || '';
      btn.textContent = line.title || '(未命名线体)';
      btn.addEventListener('click', () => {
        this._scrollToLine(line.gid);
        this._setActiveLineGid(line.gid);
      });
      navBody.appendChild(btn);
    });

    // 初始标签显示第一条线体
    if (lines.length > 0) this._setActiveLineGid(lines[0].gid);
    else this._setCurrentLineLabel('');
  }

  _setCurrentLineLabel(title) {
    const el = document.getElementById('llCurrentLineLabel');
    if (el) el.textContent = title || '';
  }

  /**
   * 将画布视口平移到指定线框中央（保持当前缩放）
   */
  _scrollToLine(lineGid) {
    const pos = this._linePositions.get(lineGid);
    if (!pos) return;
    const vw = this._viewport.clientWidth;
    const vh = this._viewport.clientHeight;
    const lineCX = pos.x + pos.w / 2;
    const lineCY = pos.y + pos.h / 2;
    this._panX = vw / 2 - lineCX * this._zoom;
    this._panY = vh / 2 - lineCY * this._zoom;
    this._setTransform();
    this._syncMinimapViewport();
  }

  // ══════════════════════════════════════════════════════════════════
  // 缩略图导航
  // ══════════════════════════════════════════════════════════════════

  _renderMinimap() {
    if (!this._minimapBody) return;
    if (this._minimap?.classList.contains('collapsed')) return; // 折叠时不渲染
    this._minimapBody.innerHTML = '';
    this._updateMinimap();
  }

  _toggleMinimap() {
    if (!this._minimap) return;
    const collapsed = this._minimap.classList.toggle('collapsed');
    const btn = this._minimap.querySelector('#llMinimapToggle');
    if (btn) btn.textContent = collapsed ? '+' : '−';
    if (!collapsed) {
      this._renderMinimap();
      this._syncMinimapViewport();
    }
  }

  _updateMinimap() {
    const body = this._minimapBody;
    if (!body) return;

    const lines = this._world.querySelectorAll('.ll-line-box');
    if (lines.length === 0) { body.innerHTML = ''; return; }

    // 计算所有线框的世界坐标包围盒
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    const rects = [];
    for (const el of lines) {
      const lx = parseFloat(el.style.left) || 0;
      const ly = parseFloat(el.style.top) || 0;
      const w = parseFloat(el.style.width) || 300;
      const h = parseFloat(el.style.height) || 200;
      const title = el.querySelector('.ll-line-title')?.textContent || '';
      minX = Math.min(minX, lx);
      minY = Math.min(minY, ly);
      maxX = Math.max(maxX, lx + w);
      maxY = Math.max(maxY, ly + h);
      rects.push({ gid: el.dataset.gid, lx, ly, w, h, title });
    }

    if (minX === Infinity) return;

    const contentW = maxX - minX;
    const contentH = maxY - minY;

    // 缩略图可用尺寸（body 容器尺寸，留 padding）
    const pad = 8;
    const availW = (body.clientWidth || 264) - pad * 2;
    const availH = (body.clientHeight || 340) - pad * 2;

    // 计算缩放：填满可用区域，但不超过 0.35 以免太大
    const mapScale = Math.min(availW / contentW, availH / contentH, 0.35);

    const mapW = contentW * mapScale;
    const mapH = contentH * mapScale;
    // 居中偏移
    const offX = pad + (availW - mapW) / 2;
    const offY = pad + (availH - mapH) / 2;

    body.innerHTML = '';
    body.style.position = 'relative';

    // 设置 body 尺寸，使 scroll 正确
    const totalW = pad * 2 + mapW;
    const totalH = pad * 2 + mapH;
    body.style.width = totalW + 'px';
    body.style.minHeight = totalH + 'px';

    // 保存缩略图参数供 _syncMinimapViewport 使用
    this._mmScale = mapScale;
    this._mmMinX = minX;
    this._mmMinY = minY;
    this._mmOffX = offX;
    this._mmOffY = offY;

    // 绘制每个线框的缩略矩形
    for (const r of rects) {
      const x = offX + (r.lx - minX) * mapScale;
      const y = offY + (r.ly - minY) * mapScale;
      const w = Math.max(r.w * mapScale, 10);
      const h = Math.max(r.h * mapScale, 6);

      const rect = document.createElement('div');
      rect.className = 'll-minimap-rect';
      rect.dataset.gid = r.gid;
      rect.style.left = x + 'px';
      rect.style.top = y + 'px';
      rect.style.width = w + 'px';
      rect.style.height = h + 'px';

      if (r.gid && this._activeGid === r.gid) rect.classList.add('active');

      if (w > 30 && h > 12) {
        const label = document.createElement('div');
        label.className = 'll-minimap-rect-label';
        label.textContent = r.title;
        rect.appendChild(label);
      }

      rect.addEventListener('click', (e) => {
        e.stopPropagation();
        this._focusLine(r.gid, r.lx, r.ly, r.w, r.h);
      });

      body.appendChild(rect);
    }

    // 显示当前视口范围指示
    this._syncMinimapViewport();
  }

  _syncMinimapViewport() {
    const body = this._minimapBody;
    if (!body) return;

    const mapScale = this._mmScale;
    const minX = this._mmMinX;
    const minY = this._mmMinY;
    const offX = this._mmOffX;
    const offY = this._mmOffY;
    if (mapScale == null) return;

    // 移除旧指示
    const old = body.querySelector('.ll-minimap-viewport');
    if (old) old.remove();

    // 计算视口世界坐标
    const vr = this._viewport.getBoundingClientRect();
    const worldTL = this._screenToWorld(vr.left, vr.top);
    const worldBR = this._screenToWorld(vr.right, vr.bottom);
    const vpW = worldBR.x - worldTL.x;
    const vpH = worldBR.y - worldTL.y;

    const el = document.createElement('div');
    el.className = 'll-minimap-viewport';
    el.style.left   = (offX + (worldTL.x - minX) * mapScale) + 'px';
    el.style.top    = (offY + (worldTL.y - minY) * mapScale) + 'px';
    el.style.width  = Math.max(vpW * mapScale, 4) + 'px';
    el.style.height = Math.max(vpH * mapScale, 4) + 'px';
    body.appendChild(el);
  }

  _focusLine(gid, lx, ly, w, h) {
    // 缩放并平移到使目标线框居中
    const vpW = this._viewport.clientWidth;
    const vpH = this._viewport.clientHeight;
    const targetZoom = 0.5; // 50% 缩放
    const cx = lx + w / 2;
    const cy = ly + h / 2;
    this._zoom = targetZoom;
    this._panX = vpW / 2 - cx * targetZoom;
    this._panY = vpH / 2 - cy * targetZoom;
    this._setTransform();
    this._updateZoomLabel();

    // 高亮该线框
    this._world.querySelectorAll('.ll-line-box.ll-line-selected').forEach(e => e.classList.remove('ll-line-selected'));
    const lineEl = this._world.querySelector(`.ll-line-box[data-gid="${gid}"]`);
    if (lineEl) lineEl.classList.add('ll-line-selected');

    // 更新缩略图高亮
    if (this._minimapBody) {
      this._minimapBody.querySelectorAll('.active').forEach(e => e.classList.remove('active'));
      const rect = this._minimapBody.querySelector(`.ll-minimap-rect[data-gid="${gid}"]`);
      if (rect) rect.classList.add('active');
    }

    this._syncMinimapViewport();
  }

  // ══════════════════════════════════════════════════════════════════
  // 持久化
  // ══════════════════════════════════════════════════════════════════

  _lsKey() { return 'lv:layout:' + (this._data?.versionGid || 'default'); }

  /**
   * 返回当前完整布局配置（用于云端持久化 / 团队共享）
   */
  getConfig() {
    const linePositions = {}, stationPositions = {}, flowDirs = {};
    for (const [g, p] of this._linePositions)    linePositions[g]    = p;
    for (const [g, p] of this._stationPositions) stationPositions[g] = p;
    for (const [g, d] of this._lineFlowDirs)     flowDirs[g]         = d;
    return { linePositions, stationPositions, flowDirs, layoutVersion: LL_LAYOUT_VERSION };
  }

  /**
   * 应用来自云端的布局配置并重新渲染
   * @returns {boolean} 是否成功应用（layoutVersion 不匹配时返回 false）
   */
  applyConfig(cfg) {
    if (!cfg || cfg.layoutVersion !== LL_LAYOUT_VERSION) return false;
    if (cfg.linePositions) {
      this._linePositions.clear();
      for (const [g, p] of Object.entries(cfg.linePositions)) this._linePositions.set(g, p);
    }
    if (cfg.stationPositions) {
      this._stationPositions.clear();
      for (const [g, p] of Object.entries(cfg.stationPositions)) this._stationPositions.set(g, p);
    }
    if (cfg.flowDirs) {
      this._lineFlowDirs.clear();
      for (const [g, d] of Object.entries(cfg.flowDirs)) this._lineFlowDirs.set(g, d);
    }
    if (this._data) {
      this._layoutAllStations();
      this._renderAllCards();
      this._updateMinimap();
    }
    return true;
  }

  // ── 重挂拖拽方法 ──────────────────────────────────────────────────

  _activateReparentDrag({ el, row, startX, startY }) {
    // 收集有效落点：父级换挂（parent）+ 同类型排位（sibling，含跨父）
    const nodeType   = row.node_type;
    const validTypes = nodeType === 'operator_process'
      ? ['station_process']
      : ['operator_process', 'station_process']; // process 可挂岗位或工位

    const validTargets = [];
    this._world.querySelectorAll('[data-gid]').forEach(targetEl => {
      const gid = targetEl.dataset.gid;
      if (gid === row.gid) return;
      const targetRow = this._data?.rowByGid.get(gid);
      if (!targetRow) return;

      if (validTypes.includes(targetRow.node_type)) {
        // 父级换挂目标（蓝色）
        targetEl.classList.add('ll-drop-target');
        validTargets.push({ gid, el: targetEl, kind: 'parent' });
      } else if (targetRow.node_type === nodeType) {
        // 同类型目标（橙色）：同父 → 排序，跨父 → 换挂后插到目标后面
        targetEl.classList.add('ll-reorder-target');
        validTargets.push({ gid, el: targetEl, kind: 'sibling' });
      }
    });

    // Ghost 卡片（跟随鼠标，fixed 定位，不在 world 变换内）
    const ghost = document.createElement('div');
    ghost.className    = 'll-reparent-ghost';
    ghost.style.width  = LL_RING_CARD_W + 'px';
    ghost.style.height = LL_RING_CARD_H + 'px';
    ghost.innerHTML    = el.innerHTML;
    ghost.style.left   = (startX - LL_RING_CARD_W / 2) + 'px';
    ghost.style.top    = (startY - LL_RING_CARD_H / 2) + 'px';
    document.body.appendChild(ghost);

    this._reparentDrag = { row, ghostEl: ghost, validTargets, hoveredGid: null, hoveredKind: null };
  }

  _onReparentDragMove(e) {
    const drag = this._reparentDrag;
    drag.ghostEl.style.left = (e.clientX - LL_RING_CARD_W / 2) + 'px';
    drag.ghostEl.style.top  = (e.clientY - LL_RING_CARD_H / 2) + 'px';

    let hoveredGid = null, hoveredKind = null;
    for (const { gid, el, kind } of drag.validTargets) {
      const r = el.getBoundingClientRect();
      if (e.clientX >= r.left && e.clientX <= r.right &&
          e.clientY >= r.top  && e.clientY <= r.bottom) {
        hoveredGid = gid; hoveredKind = kind;
        break;
      }
    }

    if (hoveredGid !== drag.hoveredGid) {
      for (const t of drag.validTargets) {
        t.el.classList.remove('ll-drop-target-hovered', 'll-reorder-target-hovered');
      }
      if (hoveredGid) {
        const t = drag.validTargets.find(t => t.gid === hoveredGid);
        if (t) {
          t.el.classList.add(hoveredKind === 'sibling'
            ? 'll-reorder-target-hovered' : 'll-drop-target-hovered');
        }
      }
      drag.hoveredGid  = hoveredGid;
      drag.hoveredKind = hoveredKind;
    }
  }

  _cancelReparentDrag() {
    const drag = this._reparentDrag;
    if (!drag) return;
    drag.ghostEl.remove();
    for (const t of drag.validTargets) {
      t.el.classList.remove(
        'll-drop-target', 'll-drop-target-hovered',
        'll-reorder-target', 'll-reorder-target-hovered'
      );
    }
    this._reparentDrag = null;
  }

  async _commitReparent() {
    const drag = this._reparentDrag;
    this._reparentDrag = null;
    drag.ghostEl.remove();
    for (const t of drag.validTargets) {
      t.el.classList.remove(
        'll-drop-target', 'll-drop-target-hovered',
        'll-reorder-target', 'll-reorder-target-hovered'
      );
    }

    const targetGid = drag.hoveredGid;
    if (!targetGid) return; // 拖到空白处 → 取消

    if (drag.hoveredKind === 'sibling') {
      await this._commitPositionAfter(drag);
    } else {
      await this._commitParentChange(drag);
    }
  }

  async _commitParentChange(drag) {
    try {
      await _cf(`/api/bop/entries/${drag.row.gid}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ parent_bop_gid: drag.hoveredGid }),
      });
      this._preserveView = true;
      if (this._data?.reloadData) await this._data.reloadData();
    } catch (err) {
      if (this._data?.toast) this._data.toast('移动失败: ' + err.message, 'error');
      else console.error('[LayoutMode] _commitParentChange error:', err);
    }
  }

  // 统一排位：同父 → 仅排序；跨父 → 先换挂再插到目标后面
  async _commitPositionAfter(drag) {
    const targetRow  = this._data?.rowByGid.get(drag.hoveredGid);
    if (!targetRow) return;

    const nodeType   = drag.row.node_type;
    const dragParent = drag.row.parent_bop_gid || null;
    const destParent = targetRow.parent_bop_gid || null;

    try {
      // Step 1：跨父时先换挂
      if (dragParent !== destParent) {
        await _cf(`/api/bop/entries/${drag.row.gid}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ parent_bop_gid: targetRow.parent_bop_gid }),
        });
      }

      // Step 2：在目标父级的同类子节点中计算新顺序
      // childMap 尚未刷新，跨父时手动排除拖拽行，再追加到末尾
      const destSiblings = (this._data?.childMap.get(destParent) || [])
        .filter(r => r.node_type === nodeType && r.gid !== drag.row.gid)
        .sort((a, b) => (a.seq_no ?? 0) - (b.seq_no ?? 0));

      // 插到目标后面
      const targetIdx = destSiblings.findIndex(r => r.gid === drag.hoveredGid);
      destSiblings.splice(targetIdx + 1, 0, drag.row);

      // 只 PATCH 序号变化的行（拖拽行强制包含，以便在跨父时也写入新 seq_no）
      const patches = destSiblings
        .map((r, i) => ({ gid: r.gid, newSeq: i + 1, oldSeq: r.seq_no }))
        .filter(p => p.newSeq !== p.oldSeq || p.gid === drag.row.gid);

      if (patches.length) {
        await Promise.all(patches.map(p =>
          _cf(`/api/bop/entries/${p.gid}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ seq_no: p.newSeq }),
          })
        ));
      }

      this._preserveView = true;
      if (this._data?.reloadData) await this._data.reloadData();
    } catch (err) {
      if (this._data?.toast) this._data.toast('操作失败: ' + err.message, 'error');
      else console.error('[LayoutMode] _commitPositionAfter error:', err);
    }
  }

  _saveLinePositions() {
    const data = {};
    for (const [gid, pos] of this._linePositions) {
      data[gid] = pos;
    }
    try {
      const existing = JSON.parse(localStorage.getItem(this._lsKey()) || '{}');
      existing.layoutVersion = LL_LAYOUT_VERSION;
      existing.linePositions = data;
      localStorage.setItem(this._lsKey(), JSON.stringify(existing));
    } catch { /* ignore */ }
  }

  _saveStationPositions() {
    const data = {};
    for (const [gid, pos] of this._stationPositions) {
      data[gid] = pos;
    }
    try {
      const existing = JSON.parse(localStorage.getItem(this._lsKey()) || '{}');
      existing.layoutVersion = LL_LAYOUT_VERSION;
      existing.stationPositions = data;
      localStorage.setItem(this._lsKey(), JSON.stringify(existing));
    } catch { /* ignore */ }
  }

  _loadPositions() {
    try {
      const raw = localStorage.getItem(this._lsKey());
      if (!raw) return;
      const data = JSON.parse(raw);
      // 布局版本变化时丢弃旧缓存
      if (data.layoutVersion !== LL_LAYOUT_VERSION) {
        localStorage.removeItem(this._lsKey());
        return;
      }
      if (data.linePositions) {
        for (const [gid, pos] of Object.entries(data.linePositions)) {
          this._linePositions.set(gid, pos);
        }
      }
      if (data.stationPositions) {
        for (const [gid, pos] of Object.entries(data.stationPositions)) {
          this._stationPositions.set(gid, pos);
        }
      }
      if (data.flowDirs) {
        for (const [gid, dir] of Object.entries(data.flowDirs)) {
          this._lineFlowDirs.set(gid, dir);
        }
      }
    } catch { /* ignore */ }
  }
}

// 导出
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { LayoutMode };
}

// 暴露一个清除 localStorage 布局缓存的全局方法
window._clearLayoutCache = function(versionGid) {
  const key = 'lv:layout:' + (versionGid || 'default');
  localStorage.removeItem(key);
};