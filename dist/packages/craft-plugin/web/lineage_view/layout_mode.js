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
const LL_STATION_H = 36;    // 工位卡片高度
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
    this._allLines      = [];    // 完整线体列表（picker 用）
    this._filteredLines = [];
    this._wheelIdx = 0;   // 滚轮当前聚焦的线体索引

    // 位置缓存
    this._linePositions    = new Map();  // lineGid → {x, y, w, h}
    this._stationPositions = new Map();  // stationGid → {x, y}

    // 车流方向（lineGid → 'right'|'left'），默认 'right'
    this._lineFlowDirs = new Map();

    // 车俯视图区域信息（lineGid → { topY, lineW, flowDir }），由 _layoutLineStations 填充
    this._lineCarAreas = new Map();

    // 工位展开方向（stationGid → 'up'|'down'），由 _layoutLineStations 根据 flowDir 填充
    this._stationDirection = new Map();

    // 岗位位置高亮状态
    this._activePosition     = null;  // 当前高亮的位置字母 (A-F)
    this._activePositionLine = null;  // 对应的 lineGid

    // 编辑状态
    this._editMode = false;

    // 位置拖拽状态（编辑模式用）
    this._dragState = null; // { type, gid, startX, startY, origX, origY }
    this._spaceDown = false;

    // 重挂拖拽状态（operator_process / process 换父节点）
    this._reparentPending = null; // { el, row, startX, startY }
    this._reparentDrag    = null; // { row, ghostEl, validTargets, hoveredGid }
    this._demotePending   = null; // { el, row, startX, startY }
    this._demoteDrag      = null; // { row, ghostEl }
    this._preserveView    = false; // true 时 render() 跳过 _fitToScreen
    this._html5DragHovered = null; // HTML5 拖拽高亮的卡片元素
    this._stagingDrag     = null; // { info, ghostEl, validTargets, hoveredGid }

    // 虚拟渲染：记录已渲染卡片的线体 gid，避免重复渲染
    this._renderedLineGids = new Set();
    this._vrTimer = null; // 防抖定时器

    // 工序卡片复制粘贴（Ctrl+C / Ctrl+V）
    this._clipboard = null;  // { row } — 已复制的工序行

    // 多项目对比（方案三）
    this._multiMode  = false;
    this._mergeData  = null;  // { secondaryLineGids: Set, mergedLineMap: Map<canonicalGid, mergedStation[]> }

    // 边缘自动滚动（拖拽时）
    this._edgeMouseClient = { x: 0, y: 0 };
    this._edgeScrollRaf   = null;

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
   * Release version-scoped DOM, projection and interaction state before a
   * version switch or refresh. The LayoutMode instance and its event wiring
   * remain reusable for the next bounded projection.
   */
  destroyHeavyState() {
    if (this._vrTimer !== null) clearTimeout(this._vrTimer);
    this._vrTimer = null;
    if (this._edgeScrollRaf !== null && typeof cancelAnimationFrame === 'function') {
      cancelAnimationFrame(this._edgeScrollRaf);
    }
    this._edgeScrollRaf = null;
    if (this._world) this._world.innerHTML = '';
    if (this._minimapBody) this._minimapBody.innerHTML = '';

    this._data = null;
    this._allLines = [];
    this._filteredLines = [];
    this._linePositions.clear();
    this._stationPositions.clear();
    this._lineCarAreas.clear();
    this._stationDirection.clear();
    this._renderedLineGids.clear();
    this._mergeData = null;
    this._multiMode = false;
    this._activeGid = null;
    this._activePosition = null;
    this._activePositionLine = null;
    this._dragState = null;
    this._reparentPending = null;
    this._reparentDrag = null;
    this._demotePending = null;
    this._demoteDrag = null;
    this._html5DragHovered = null;
    this._stagingDrag = null;
    this._edgeMouseClient = { x: 0, y: 0 };
    this._preserveView = false;
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

    // 确保该节点所在线体已渲染（平移跳转场景：先 panTo 后 highlightNode）
    const lineRow = this._getLineForGid(gid);
    if (lineRow && !this._renderedLineGids.has(lineRow.gid)) {
      this._renderLineCards(lineRow.gid);
    }

    // 布局视图只做两态：自身蓝框 + 直接子节点淡蓝框
    const el = this._world.querySelector(`[data-gid="${gid}"]`);
    if (el) el.classList.add('active-node');

    const children = this._data.childMap.get(gid) || [];
    for (const child of children) {
      const childEl = this._world.querySelector(`[data-gid="${child.gid}"]`);
      if (childEl) childEl.classList.add('active-child');
    }

    // 点击卡片时同步更新当前线体标签和导航
    if (lineRow) this._setActiveLineGid(lineRow.gid);
  }

  /** 向上遍历父链，找到最近的线体祖先（line_process 或 _filteredLines 中的节点） */
  _getLineForGid(gid) {
    const rowByGid = this._data?.rowByGid;
    if (!rowByGid) return null;
    // 构建线体 gid 集合（兼容 fallback 模式）
    const lineGids = new Set((this._filteredLines || []).map(r => r.gid));
    let row = rowByGid.get(gid);
    while (row) {
      if (row.node_type === 'line_process' || lineGids.has(row.gid)) return row;
      if (!row.parent_gid) return null;
      row = rowByGid.get(row.parent_gid);
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

  /** 同步更新滚轮焦点到指定线体（由平移自动检测调用） */
  _setActiveLineGid(lineGid) {
    const idx = (this._filteredLines || []).findIndex(l => l.gid === lineGid);
    if (idx >= 0) this._wheelIdx = idx;
    this._updateWheelDisplay();
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
    let lines = [];
    for (const r of this._data.rows) {
      if (r.node_type === 'line_process') lines.push(r);
    }

    // debug: 显示完整 node_type 分布
    const ntDist = {};
    for (const r of this._data.rows) {
      const nt = r.node_type || '(empty)';
      ntDist[nt] = (ntDist[nt] || 0) + 1;
    }
    console.log('[LayoutMode._buildLines] total rows:', this._data.rows.length,
      '| line_process count:', lines.length,
      '| node_type distribution:', JSON.stringify(ntDist));

    // 若找不到 line_process 节点，自动降级：用 depth-1 节点（工厂BOP直接子节点）作为线体
    if (lines.length === 0 && this._data.rows.length > 0) {
      const depthByGid = this._data.depthByGid;
      // 先尝试 factory_bop 的子节点（depth=1）
      const depth1 = this._data.rows.filter(r => (depthByGid.get(r.gid) ?? 0) === 1);
      if (depth1.length > 0) {
        lines = depth1;
        console.log('[LayoutMode._buildLines] fallback to depth-1 nodes as lines:', depth1.length,
          '| types:', [...new Set(depth1.map(r => r.node_type))]);
      } else {
        // 再退而用 depth-0（根节点）
        const depth0 = this._data.rows.filter(r => (depthByGid.get(r.gid) ?? 0) === 0);
        lines = depth0;
        console.log('[LayoutMode._buildLines] fallback to depth-0 nodes as lines:', depth0.length);
      }
    }

    // 保存完整线体列表（右键多选菜单用）
    this._allLines = lines.slice();

    // 应用工具栏线体筛选（level1Filter：null=全部，Set=只显示指定 gid）
    const l1Filter = this._data.level1Filter;
    let filteredLines = l1Filter === null ? lines :
      lines.filter(r => l1Filter.has(r.gid));

    // 多项目对比：构建合并数据，过滤掉 secondary 线体
    if (this._data.projectVersions && this._data.projectVersions.length > 1) {
      this._buildMergeData(this._data.projectVersions, this._data.projectColors, filteredLines);
      this._multiMode = true;
      filteredLines = filteredLines.filter(l => !this._mergeData.secondaryLineGids.has(l.gid));
    } else {
      this._multiMode = false;
      this._mergeData = null;
    }

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
      // 多项目模式：跳过 secondary 线体（它们被合并进 canonical 线体）
      if (this._multiMode && this._mergeData?.secondaryLineGids.has(gid)) continue;
      this._layoutLineStations(gid);
    }

    // 重新堆叠线框位置，确保互不重叠
    let autoY = LL_LINE_PAD;
    for (const lineEl of lines) {
      const gid = lineEl.dataset.gid;
      if (this._multiMode && this._mergeData?.secondaryLineGids.has(gid)) continue;
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
    // 多项目模式：使用合并工位数据
    if (this._multiMode && this._mergeData?.mergedLineMap.has(lineGid)) {
      this._layoutMergedLineStations(lineGid);
      return;
    }

    const stations = this._data.childMap.get(lineGid) || [];
    const linePos = this._linePositions.get(lineGid);
    if (!linePos) return;

    const flowDir = this._lineFlowDirs.get(lineGid) || 'right';
    const isAsc = flowDir === 'right'; // 车流向右：seq_no 左→右递增；向左：递减

    // ── Step 1: 解析工位编号和侧别 ──────────────────────────────────
    for (const s of stations) {
      s._effectiveSide = this._parseLRMSuffix(s.title) || 'none';
      const titleNum = parseInt(s.title?.match(/(\d+)/)?.[1]) || 0;
      const sortNum  = (s.sort_order != null && s.sort_order > 0) ? s.sort_order : titleNum;
      // 分组键：优先用标题数字，确保同编号 L/R 归同列（sort_order 因侧别不同可能各异）
      s._stationNum   = titleNum > 0 ? titleNum : sortNum;
      s._stationOrder = sortNum; // 列间排序用
    }

    // ── Step 2: 按工位编号分组 ──────────────────────────────────────
    // numMap: stationNum → { L, R, M, none[] }
    const numMap = new Map();
    for (const s of stations) {
      const num = s._stationNum;
      if (!numMap.has(num)) numMap.set(num, { L: null, R: null, M: null, none: [] });
      const g = numMap.get(num);
      if      (s._effectiveSide === 'L') g.L = s;
      else if (s._effectiveSide === 'R') g.R = s;
      else if (s._effectiveSide === 'M') g.M = s;
      else                               g.none.push(s);
    }

    // ── Step 3: 按编号顺序构建列列表 ────────────────────────────────
    // 各组的排序代表值 = 组内工位 _stationOrder 的最小值
    const groupOrd = num => {
      const g = numMap.get(num);
      const all = [g.L, g.R, g.M, ...g.none].filter(Boolean);
      return all.length ? Math.min(...all.map(s => s._stationOrder)) : num;
    };
    const sortedNums = [...numMap.keys()].sort((a, b) => isAsc ? groupOrd(a) - groupOrd(b) : groupOrd(b) - groupOrd(a));
    const columns = [];

    for (const num of sortedNums) {
      const g = numMap.get(num);
      // L/R 对称：同编号 L 在上行，R 在下行；缺哪侧就留 null（空位）
      if (g.L !== null || g.R !== null) {
        columns.push({ top: g.L, bottom: g.R });
      }
      // M 工位单独占一列
      if (g.M) {
        columns.push({ top: g.M, bottom: null });
      }
      // 无后缀工位：相邻两两配对 (even=L, odd=R)
      for (let i = 0; i < g.none.length; i++) {
        const s = g.none[i];
        if (i % 2 === 0) {
          s._effectiveSide = 'L';
          const next = g.none[i + 1];
          if (next) { next._effectiveSide = 'R'; columns.push({ top: s, bottom: next }); i++; }
          else       { columns.push({ top: s, bottom: null }); }
        }
      }
    }

    // 计算纵向子卡片空间；「人」元素在布局视图不显示，无最小兜底，真实收缩
    let maxChildVert = LL_CHILD_PAD;
    for (const s of stations) {
      const kids        = this._data.childMap.get(s.gid) || [];
      const operators   = kids.filter(r => r.node_type === 'operator_process');
      const manCards    = []; // 布局视图不显示「人」元素
      const directProcs = kids.filter(r => r.node_type === 'process');
      let totalH = 0, groupCount = 0;
      if (manCards.length) {
        totalH += manCards.length * LL_RING_CARD_H + (manCards.length - 1) * LL_LAYER_CARD_GAP;
        groupCount++;
      }
      for (const op of operators) {
        const opProcs = (this._data.childMap.get(op.gid) || []).filter(r => r.node_type === 'process');
        // 岗位卡片用正常高度，工序卡片用正常高度
        const opH = LL_RING_CARD_H + LL_LAYER_CARD_GAP + opProcs.length * (LL_RING_CARD_H + LL_LAYER_CARD_GAP);
        totalH += opH > 0 ? opH - LL_LAYER_CARD_GAP : LL_RING_CARD_H;
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
    this._lineCarAreas.set(lineGid, { topY, flowDir, columns, lineGid });

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
    this._renderedLineGids.clear();
    // 清除所有 layout 的渲染标记（流向切换/位置加载等场景需要重渲染）
    this._world.querySelectorAll('.ll-line-layout[data-rendered]').forEach(el => {
      el.removeAttribute('data-rendered');
      el.innerHTML = '';
    });
    // 只渲染视野内（+1个视口高度缓冲区）的线体；其余待平移时按需渲染
    for (const line of this._filteredLines) {
      if (this._isLineVisible(line.gid, this._viewport.clientHeight)) {
        this._renderLineCards(line.gid);
      }
    }
  }

  /**
   * 检查并渲染新进入视野的线体（平移/缩放停止后调用）
   */
  _checkVirtualRender() {
    if (!this._data || !this._filteredLines.length) return;
    const buffer = this._viewport.clientHeight;
    let anyNew = false;
    for (const line of this._filteredLines) {
      if (this._renderedLineGids.has(line.gid)) continue;
      if (!this._isLineVisible(line.gid, buffer)) continue;
      this._renderLineCards(line.gid);
      anyNew = true;
    }
    if (anyNew) this._updateMinimap();
  }

  /**
   * 判断指定线体是否在当前视口范围内（含 bufferPx 缓冲）
   */
  _isLineVisible(lineGid, bufferPx = 0) {
    const pos = this._linePositions.get(lineGid);
    if (!pos) return false;
    const vw = this._viewport.clientWidth;
    const vh = this._viewport.clientHeight;
    // 视口四角换算到世界坐标（含缓冲）
    const buf = bufferPx / this._zoom;
    const wxMin = (-this._panX) / this._zoom - buf;
    const wyMin = (-this._panY) / this._zoom - buf;
    const wxMax = (vw - this._panX) / this._zoom + buf;
    const wyMax = (vh - this._panY) / this._zoom + buf;
    return pos.x < wxMax && pos.x + pos.w > wxMin &&
           pos.y < wyMax && pos.y + pos.h > wyMin;
  }

  /**
   * 渲染单条线体内的所有卡片（工位 + 子节点层）
   */
  _renderLineCards(lineGid) {
    const lineEl = this._world.querySelector(`.ll-line-box[data-gid="${lineGid}"]`);
    if (!lineEl) return;
    const layoutEl = lineEl.querySelector('.ll-line-layout');
    if (!layoutEl || layoutEl.dataset.rendered === '1') return;

    layoutEl.dataset.rendered = '1';

    // 多项目模式：使用合并工位渲染
    if (this._multiMode && this._mergeData?.mergedLineMap.has(lineGid)) {
      const mergedStations = this._mergeData.mergedLineMap.get(lineGid);
      if (mergedStations.length === 0) {
        layoutEl.innerHTML = '<div class="ll-line-empty">无工位</div>';
      } else {
        for (const ms of mergedStations) {
          const canonicalGid = ms.items[0].row.gid;
          const pos = this._stationPositions.get(canonicalGid);
          if (!pos) continue;
          const direction = this._stationDirection.get(canonicalGid) || 'up';
          const card = this._createMergedStationCard(ms, direction);
          card.style.left = pos.x + 'px';
          card.style.top  = pos.y + 'px';
          layoutEl.appendChild(card);
          this._renderMergedStationChildren(ms, layoutEl, pos.x, pos.y, direction);
        }
        const carAreaInfo = this._lineCarAreas.get(lineGid);
        if (carAreaInfo) this._renderMergedLineCarArea(layoutEl, carAreaInfo, this._mergeData.mergedLineMap.get(lineGid));
        this._renderLineFlowArrows(lineGid, lineEl);
      }
      this._renderedLineGids.add(lineGid);
      return;
    }

    const stations = this._data.childMap.get(lineGid) || [];

    if (stations.length === 0) {
      layoutEl.innerHTML = '<div class="ll-line-empty">无工位</div>';
    } else {
      for (const station of stations) {
        const pos = this._stationPositions.get(station.gid);
        if (!pos) continue;
        const direction = this._stationDirection.get(station.gid) || 'up';
        const card = this._createStationCard(station, direction);
        card.style.left = pos.x + 'px';
        card.style.top = pos.y + 'px';
        layoutEl.appendChild(card);
        this._renderStationChildren(station.gid, layoutEl, pos.x, pos.y, direction);
        this._renderStationToolBox(station.gid, layoutEl, pos.x, pos.y, direction);
      }
      const carAreaInfo = this._lineCarAreas.get(lineGid);
      if (carAreaInfo) this._renderLineCarArea(layoutEl, carAreaInfo);
      this._renderLineFlowArrows(lineGid, lineEl);
    }

    this._renderedLineGids.add(lineGid);
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
    // 资源框固定高度（3行），工序卡片需要避开它
    const _TOOL_BOX_H = 5 * 2 + 3 * 14 + 2 * 2 + 4;  // BOX_PAD*2 + 3*ROW_H + gaps + GAP
    const _hasTools = this._collectDeepByTypes(stationGid,
      ['equipment_factory','equipment_need','tool_factory','tool_need','fixture_factory','fixture_need']).length > 0;

    let Y = isDown
      ? sy + LL_STATION_H + LL_LAYER_GAP + (_hasTools ? _TOOL_BOX_H : 0)
      : sy - LL_LAYER_GAP - (_hasTools ? _TOOL_BOX_H : 0);

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
    const manCards        = []; // 布局视图不显示「人」元素
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
   * 渲染工位设备/工具/工装清单框
   * L 工位（direction='up'）→ 框在工位上方
   * R 工位（direction='down'）→ 框在工位下方
   */
  _renderStationToolBox(stationGid, parentEl, sx, sy, direction) {
    if (direction !== 'up' && direction !== 'down') return;

    // 收集本工位子树里所有设备 / 工具 / 工装节点
    const equipmentTypes = ['equipment_factory', 'equipment_need'];
    const toolTypes    = ['tool_factory', 'tool_need'];
    const fixtureTypes = ['fixture_factory', 'fixture_need'];
    const allNodes = this._collectDeepByTypes(stationGid, [...equipmentTypes, ...toolTypes, ...fixtureTypes]);
    if (allNodes.length === 0) return;

    // 按 title（型号）分组统计
    const counts = new Map();  // 类型 + title → { count, resourceType }
    for (const n of allNodes) {
      const label = n.entity_data?.model_no || n.entity_data?.preferred_model
        || n.entity_data?.tool_spec || n.entity_data?.fixture_spec
        || n.entity_data?.spec || n.title || '(未命名)';
      const resourceType = equipmentTypes.includes(n.node_type)
        ? 'equipment'
        : (fixtureTypes.includes(n.node_type) ? 'fixture' : 'tool');
      const key = resourceType + ':' + label;
      if (!counts.has(key)) counts.set(key, { label, count: 0, resourceType });
      counts.get(key).count++;
    }

    const BOX_PAD = 5, ROW_H = 14, FIXED_ROWS = 3, GAP = 4;
    const boxH = BOX_PAD * 2 + FIXED_ROWS * ROW_H + (FIXED_ROWS - 1) * 2;  // 固定3行高度

    const rows = [...counts.values()].slice(0, FIXED_ROWS);

    const box = document.createElement('div');
    box.style.cssText = [
      `position:absolute;left:${sx}px`,
      `width:${LL_STATION_W}px`,
      `height:${boxH}px`,
      'overflow:hidden',
      'background:var(--surface0,#313244)',
      'border:1px solid var(--surface2,#585b70)',
      'border-radius:4px',
      `padding:${BOX_PAD}px 6px`,
      'box-sizing:border-box',
      'z-index:3',
    ].join(';');

    // 放在工位上方（L）或下方（R）
    if (direction === 'up') {
      box.style.top = (sy - boxH - GAP) + 'px';
    } else {
      box.style.top = (sy + LL_STATION_H + GAP) + 'px';
    }

    for (const { label, count, resourceType } of rows) {
      const row = document.createElement('div');
      row.style.cssText = 'display:flex;align-items:center;gap:4px;height:14px;overflow:hidden';

      const typeBadge = document.createElement('span');
      const badgeColors = { equipment: '#94e2d5', fixture: '#d3875a', tool: '#89dceb' };
      const badgeLabels = { equipment: '设', fixture: '装', tool: '具' };
      typeBadge.style.cssText = [
        `background:${badgeColors[resourceType]}`,
        'color:#1e1e2e;font-size:8px;font-weight:700',
        'padding:0 3px;border-radius:2px;flex-shrink:0;line-height:14px',
      ].join(';');
      typeBadge.textContent = badgeLabels[resourceType];

      const nameEl = document.createElement('span');
      nameEl.style.cssText = 'flex:1;font-size:9px;color:var(--text,#cdd6f4);overflow:hidden;text-overflow:ellipsis;white-space:nowrap';
      nameEl.textContent = label;

      const cntEl = document.createElement('span');
      cntEl.style.cssText = 'font-size:9px;color:var(--subtext0,#a6adc8);flex-shrink:0';
      cntEl.textContent = 'x' + count;

      row.appendChild(typeBadge);
      row.appendChild(nameEl);
      row.appendChild(cntEl);
      box.appendChild(row);
    }

    if (counts.size > FIXED_ROWS) {
      const more = document.createElement('div');
      more.style.cssText = 'font-size:9px;color:var(--overlay0,#6c7086);margin-top:2px';
      more.textContent = `…还有 ${counts.size - FIXED_ROWS} 项`;
      box.appendChild(more);
    }

    parentEl.appendChild(box);
  }

  _buildStationContent(card, row, side, direction) {
    // ── 单行布局：[LR徽标]  [工位名称 flex:1]  [工位高度/NA] ────────────

    const mainRow = document.createElement('div');
    mainRow.style.cssText = 'display:flex;align-items:center;gap:5px;width:100%;overflow:hidden';

    // L/R/M 徽标（内联，不再浮动）
    if (side) {
      const lrm = document.createElement('div');
      const sideColors = { L: '#89b4fa', R: '#f38ba8', M: '#94e2d5' };
      lrm.style.cssText = [
        `background:${sideColors[side] || '#6c7086'}`,
        'color:#1e1e2e;font-size:9px;font-weight:700',
        'padding:1px 4px;border-radius:3px;flex-shrink:0',
        'line-height:1.4',
      ].join(';');
      lrm.textContent = side;
      mainRow.appendChild(lrm);
    }

    // 工位名称（flex:1，截断）
    const titleDiv = document.createElement('div');
    titleDiv.className = 'lv-title';
    titleDiv.dataset.inlineTitle = '1';
    titleDiv.style.cssText = 'flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px;font-weight:600;color:var(--text,#cdd6f4)';
    const stationTitleHL = this._highlightTitle(row.title || '');
    if (stationTitleHL) {
      titleDiv.innerHTML = stationTitleHL;
      card.classList.add('ll-search-hit');
    } else {
      titleDiv.textContent = row.title || '(未命名)';
    }
    mainRow.appendChild(titleDiv);

    // 工位高度（最右侧） — 仅从实体表 entity_data 读取
    const heightVal = row.entity_data?.height_mm
      ?? row.entity_data?.height
      ?? null;
    const heightEl = document.createElement('div');
    heightEl.style.cssText = 'flex-shrink:0;font-size:10px;color:var(--subtext0,#a6adc8);text-align:right;white-space:nowrap';
    heightEl.textContent = heightVal != null ? '高度：' + String(heightVal) + 'mm' : '高度：NA';
    heightEl.title = '工位高度';
    mainRow.appendChild(heightEl);

    card.appendChild(mainRow);

    // 悬浮 + 按钮：下侧添加岗位；右侧新建兄弟工位
    card.appendChild(this._makeLayoutFBtn('lv-fbtn-bottom', 'add_child', row.gid));
    card.appendChild(this._makeAddSiblingBtn(row));
  }

  /**
   * 解析工位标题，返回 { prefix, num, side, sep }
   * 支持：W04-010-L / 前内饰一线01L / W04-010 / 前内饰一线01
   */
  _parseStationTitle(title) {
    if (!title) return null;
    // 带分隔符 + 侧别：W04-010-L
    let m = title.match(/^(.*?)([-_])(\d+)([-_])([LRM])$/i);
    if (m) return { prefix: m[1], sep: m[2], num: m[3], side: m[5].toUpperCase(), trailSep: m[4] };
    // 无分隔符 + 侧别：前内饰一线01L
    m = title.match(/^(.*?)(\d+)([LRM])$/i);
    if (m) return { prefix: m[1], sep: '', num: m[2], side: m[3].toUpperCase(), trailSep: '' };
    // 带分隔符，无侧别：W04-010
    m = title.match(/^(.*?)([-_])(\d+)$/);
    if (m) return { prefix: m[1], sep: m[2], num: m[3], side: '', trailSep: '' };
    // 无分隔符，无侧别：前内饰一线01
    m = title.match(/^(.*?)(\d+)$/);
    if (m) return { prefix: m[1], sep: '', num: m[2], side: '', trailSep: '' };
    return null;
  }

  /** 根据解析结果 + 新序号拼出标题 */
  _buildStationTitle(parsed, numStr) {
    if (!parsed) return '';
    const { prefix, sep, side, trailSep } = parsed;
    if (side) return prefix + sep + numStr + trailSep + side;
    return prefix + sep + numStr;
  }

  /**
   * 创建"右侧新建兄弟工位"按钮：点击直接自动算下一个序号创建
   */
  _makeAddSiblingBtn(row) {
    const btn = document.createElement('button');
    btn.className = 'lv-fbtn lv-fbtn-right';
    btn.title = '在右侧新建兄弟工位';
    btn.textContent = '＋';
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const cf = this._data?.cf;
      if (!cf) return;
      const parsed     = this._parseStationTitle(row.title || '');
      const curNum     = parsed ? parseInt(parsed.num, 10) : 0;
      const pad        = parsed ? Math.max(parsed.num.length, 2) : 2;
      const nextNumStr = String(curNum + 1).padStart(pad, '0');
      const newTitle   = parsed ? this._buildStationTitle(parsed, nextNumStr) : (row.title || '') + nextNumStr;
      const parentGid  = row.parent_gid || null;
      const sortOrder  = (row.sort_order ?? 0) + 1;
      const versionGid = row.version_gid || this._data?.versionGid;
      try {
        await cf('/api/bop/entries', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ version_gid: versionGid, parent_gid: parentGid, node_type: 'station_process', title: newTitle, sort_order: sortOrder }),
        });
        this._data?.toast?.('已创建工位「' + newTitle + '」', 'ok');
        this._preserveView = true;
        await this._data?.reloadData?.();
      } catch (err) {
        this._data?.toast?.('创建工位失败: ' + err.message, 'error');
      }
    });
    return btn;
  }

  // ══════════════════════════════════════════════════════════════════
  // 工序卡片复制粘贴
  // ══════════════════════════════════════════════════════════════════

  /**
   * 将已复制的工序行粘贴到目标节点（新建 bop_entry，新 GID，不复制 links）
   * @param {object} srcRow   - 源工序行（process / operation）
   * @param {object} target   - 粘贴目标行（operator_process / station_process）
   */
  async _pasteEntry(srcRow, target) {
    const cf = this._data?.cf;
    if (!cf) return;

    // 目标版本：取 target 所属版本的 version_gid
    const targetVersionGid = target.version_gid || this._data.versionGid;

    try {
      await cf('/api/bop/entries', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          version_gid:      targetVersionGid,
          parent_gid:       target.gid,
          node_type:        srcRow.node_type,
          title:            srcRow.title      || '',
          vpps:             srcRow.vpps       || '',
          vpps_desc:        srcRow.vpps_desc  || '',
          sort_order:       0,
        }),
      });

      this._data?.toast?.(`已粘贴「${srcRow.title || srcRow.node_type}」`, 'ok');
      // 保留剪贴板，允许连续粘贴
      this._data?.reloadData?.();
    } catch (e) {
      this._data?.toast?.('粘贴失败: ' + e.message, 'error');
    }
  }

  // ══════════════════════════════════════════════════════════════════
  // 多项目对比（方案三）— 合并数据构建 + 合并渲染
  // ══════════════════════════════════════════════════════════════════

  /**
   * 构建合并数据：
   * - 按线体 title 分组，确定 canonical/secondary 线体
   * - 为每条 canonical 线体建立 mergedStations[] 列表
   * - 预计算每个合并工位的子节点总高度（供 _layoutMergedLineStations 使用）
   */
  _buildMergeData(projectVersions, projectColors, filteredLines) {
    const secondaryLineGids = new Set();
    const mergedLineMap     = new Map();  // canonicalGid → mergedStation[]

    // 按 title 分组线体
    const linesByTitle = new Map();
    for (const line of filteredLines) {
      const norm = (line.title || '').trim().toLowerCase();
      if (!linesByTitle.has(norm)) linesByTitle.set(norm, []);
      linesByTitle.get(norm).push(line);
    }

    for (const [, lines] of linesByTitle) {
      if (lines.length < 2) continue;  // 只有一条线体的无需合并

      // 主版本线体为 canonical
      const primaryVersionGid = projectVersions[0].versionGid;
      const canonical = lines.find(l => l.version_gid === primaryVersionGid) || lines[0];
      for (const l of lines) { if (l.gid !== canonical.gid) secondaryLineGids.add(l.gid); }

      // 收集所有项目在此线体下的工位
      const allItems = [];
      for (let pi = 0; pi < projectVersions.length; pi++) {
        const proj = projectVersions[pi];
        const matchedLine = lines.find(l => l.version_gid === proj.versionGid);
        if (!matchedLine) continue;
        const pc = projectColors.get(proj.versionGid) || { color: '#888', label: String.fromCharCode(65 + pi) };
        for (const stn of (this._data.childMap.get(matchedLine.gid) || [])) {
          // 解析侧别和编号（同 _layoutLineStations）
          const side    = this._parseLRMSuffix(stn.title) || 'none';
          const titleNum = parseInt(stn.title?.match(/(\d+)/)?.[1]) || 0;
          const sortNum  = (stn.sort_order != null && stn.sort_order > 0) ? stn.sort_order : titleNum;
          stn._effectiveSide = side;
          stn._stationNum    = titleNum > 0 ? titleNum : sortNum;
          stn._stationOrder  = sortNum;
          allItems.push({ row: stn, versionGid: proj.versionGid, color: pc.color, label: pc.label });
        }
      }

      // 按 mergeKey (titleNum + side) 分组
      const mergeMap = new Map();
      for (const item of allItems) {
        const key = (item.row._stationNum || 'x') + item.row._effectiveSide;
        if (!mergeMap.has(key)) {
          mergeMap.set(key, {
            mergeKey: key,
            side:     item.row._effectiveSide,
            stationNum:   item.row._stationNum,
            stationOrder: item.row._stationOrder,
            items:    [],
          });
        }
        mergeMap.get(key).items.push(item);
      }

      // 排序（同 _layoutLineStations isAsc 默认 true）
      const sorted = [...mergeMap.values()].sort((a, b) => a.stationOrder - b.stationOrder);

      // 预计算每个合并工位的内容高度
      const OP_HDR_H = 18, OP_ITEM_H = 14, DIV_H = 5, PAD_V = 4;
      for (const ms of sorted) {
        let totalH = PAD_V;
        for (let pi = 0; pi < ms.items.length; pi++) {
          if (pi > 0) totalH += DIV_H;
          const kids     = this._data.childMap.get(ms.items[pi].row.gid) || [];
          const ops      = kids.filter(r => r.node_type === 'operator_process');
          const dProcs   = kids.filter(r => r.node_type === 'process');
          let segH = OP_HDR_H + PAD_V;
          for (const op of ops) {
            segH += OP_ITEM_H;
            segH += (this._data.childMap.get(op.gid) || []).filter(r => r.node_type === 'process').length * OP_ITEM_H;
          }
          segH += dProcs.length * OP_ITEM_H;
          totalH += segH;
        }
        ms.totalH = Math.max(totalH, 40);
      }

      mergedLineMap.set(canonical.gid, sorted);
    }

    this._mergeData = { secondaryLineGids, mergedLineMap };
  }

  /**
   * 多项目模式下的工位布局（替代 _layoutLineStations 用于合并线体）
   * 使用 mergedStations 的 totalH 计算高度，其余逻辑与单项目版本相同
   */
  _layoutMergedLineStations(lineGid) {
    const mergedStations = this._mergeData.mergedLineMap.get(lineGid);
    const linePos = this._linePositions.get(lineGid);
    if (!linePos || !mergedStations) return;

    const flowDir = this._lineFlowDirs.get(lineGid) || 'right';

    // 构建列列表（L→top，R→bottom，同 _layoutLineStations）
    const numMap = new Map();
    for (const ms of mergedStations) {
      const num = ms.stationNum || 0;
      if (!numMap.has(num)) numMap.set(num, { L: null, R: null, M: null, none: [] });
      const g = numMap.get(num);
      if      (ms.side === 'L') g.L = ms;
      else if (ms.side === 'R') g.R = ms;
      else if (ms.side === 'M') g.M = ms;
      else                      g.none.push(ms);
    }
    const sortedNums = [...numMap.keys()].sort((a, b) => a - b);
    const columns = [];
    for (const num of sortedNums) {
      const g = numMap.get(num);
      if (g.L || g.R) columns.push({ top: g.L, bottom: g.R });
      if (g.M)        columns.push({ top: g.M, bottom: null });
      for (let i = 0; i < g.none.length; i++) {
        const ms = g.none[i];
        if (i % 2 === 0) {
          ms.side = 'L';
          const next = g.none[i + 1];
          if (next) { next.side = 'R'; columns.push({ top: ms, bottom: next }); i++; }
          else        columns.push({ top: ms, bottom: null });
        }
      }
    }

    // 高度：取所有合并工位 totalH 的最大值作为 childSpace
    let maxChildVert = 0;
    for (const ms of mergedStations) maxChildVert = Math.max(maxChildVert, ms.totalH || 0);
    const childSpace = Math.max(maxChildVert, 40);

    const lineH = childSpace + LL_LINE_PAD + LL_STATION_H + LL_CAR_AREA_H + LL_STATION_H + LL_LINE_PAD + childSpace;
    const totalCols = Math.max(columns.length, 1);
    const lineW = totalCols * LL_STATION_W + (totalCols - 1) * LL_STATION_GAP + LL_LINE_PAD * 2;
    linePos.w = lineW;
    linePos.h = Math.max(lineH, linePos.h || 200);

    const lineEl = this._world.querySelector(`.ll-line-box[data-gid="${lineGid}"]`);
    if (lineEl) {
      lineEl.style.width  = linePos.w + 'px';
      lineEl.style.height = linePos.h + 'px';
    }

    const topY    = childSpace + LL_LINE_PAD;
    const bottomY = childSpace + LL_LINE_PAD + LL_STATION_H + LL_CAR_AREA_H;

    // 存储车俯视图区域信息（传入 merged columns 供 _renderMergedLineCarArea 使用）
    this._lineCarAreas.set(lineGid, { topY, flowDir, columns, lineGid });

    for (let i = 0; i < columns.length; i++) {
      const col = columns[i];
      const cx  = LL_LINE_PAD + i * (LL_STATION_W + LL_STATION_GAP) + LL_STATION_W / 2;
      const topSlotY    = flowDir === 'right' ? topY    : bottomY;
      const bottomSlotY = flowDir === 'right' ? bottomY : topY;
      const topSlotDir    = flowDir === 'right' ? 'up'   : 'down';
      const bottomSlotDir = flowDir === 'right' ? 'down' : 'up';

      if (col.top) {
        const cGid = col.top.items[0].row.gid;
        this._stationPositions.set(cGid, { x: cx - LL_STATION_W / 2, y: topSlotY });
        this._stationDirection.set(cGid, topSlotDir);
        col.top._layoutDir = topSlotDir;
      }
      if (col.bottom) {
        const cGid = col.bottom.items[0].row.gid;
        this._stationPositions.set(cGid, { x: cx - LL_STATION_W / 2, y: bottomSlotY });
        this._stationDirection.set(cGid, bottomSlotDir);
        col.bottom._layoutDir = bottomSlotDir;
      }
    }
  }

  /**
   * 创建合并工位卡片（共用工位 = 青色边框 + 项目色点）
   */
  _createMergedStationCard(ms, direction) {
    const card = document.createElement('div');
    const side    = ms.side !== 'none' ? ms.side : null;
    const isShared = ms.items.length > 1;
    const sideCls = side ? ' station-side-' + side : ' station-side-none';
    card.className = 'll-station-card' + sideCls + (isShared ? ' ll-station-shared' : '');
    card.dataset.gid = ms.items[0].row.gid;
    card.style.width  = LL_STATION_W + 'px';
    card.style.height = LL_STATION_H + 'px';

    // 单行：[LR徽标] [标题] [高度/NA]
    const mainRow = document.createElement('div');
    mainRow.style.cssText = 'display:flex;align-items:center;gap:5px;width:100%;overflow:hidden;padding:0 6px';

    if (side) {
      const lrm = document.createElement('div');
      const sideColors = { L: '#89b4fa', R: '#f38ba8', M: '#94e2d5' };
      lrm.style.cssText = `background:${sideColors[side]||'#6c7086'};color:#1e1e2e;font-size:9px;font-weight:700;padding:1px 4px;border-radius:3px;flex-shrink:0;line-height:1.4`;
      lrm.textContent = side;
      mainRow.appendChild(lrm);
    }

    const titleDiv = document.createElement('div');
    titleDiv.className = 'lv-title';
    titleDiv.dataset.inlineTitle = '1';
    titleDiv.style.cssText = 'flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px;font-weight:600;color:var(--text,#cdd6f4)';
    const titleHL = this._highlightTitle(ms.items[0].row.title || '');
    if (titleHL) { titleDiv.innerHTML = titleHL; card.classList.add('ll-search-hit'); }
    else titleDiv.textContent = ms.items[0].row.title || '(未命名)';
    mainRow.appendChild(titleDiv);

    // 工位高度
    const row0 = ms.items[0].row;
    const heightVal = row0.entity_data?.height_mm ?? row0.entity_data?.height ?? null;
    const heightEl = document.createElement('div');
    heightEl.style.cssText = 'flex-shrink:0;font-size:10px;color:var(--subtext0,#a6adc8);white-space:nowrap';
    heightEl.textContent = heightVal != null ? '高度：' + String(heightVal) + 'mm' : '高度：NA';
    heightEl.title = '工位高度';
    mainRow.appendChild(heightEl);

    card.appendChild(mainRow);

    // 右上角项目色点
    const dots = document.createElement('div');
    dots.className = 'll-station-project-dots';
    for (const item of ms.items) {
      const dot = document.createElement('span');
      dot.className = 'll-pdot';
      dot.style.background = item.color;
      dot.title = item.label;
      dots.appendChild(dot);
    }
    card.appendChild(dots);

    // 点击透传到 canonical 站的 gid
    card.addEventListener('click', (e) => {
      if (this._data.applyActiveState) this._data.applyActiveState(ms.items[0].row.gid);
    });

    return card;
  }

  /**
   * 渲染合并工位的工序段（A段 → 分隔线 → B段，垂直堆叠）
   */
  _renderMergedStationChildren(ms, parentEl, sx, sy, direction) {
    if (!ms.items || ms.items.length === 0) return;
    const isDown = direction === 'down';
    const OP_HDR_H = 18, OP_ITEM_H = 14, DIV_H = 5, PAD_V = 4, BLOCK_GAP = 12;

    const container = document.createElement('div');
    container.className = 'll-mp-op-container';
    container.style.width = LL_STATION_W + 'px';
    container.style.left  = sx + 'px';

    let totalH = PAD_V;
    const segEls = [];

    for (let pi = 0; pi < ms.items.length; pi++) {
      const projItem = ms.items[pi];
      const kids     = this._data.childMap.get(projItem.row.gid) || [];
      const ops      = kids.filter(r => r.node_type === 'operator_process');
      const dProcs   = kids.filter(r => r.node_type === 'process');

      // 分隔线
      if (pi > 0) {
        const divEl = document.createElement('div');
        divEl.className = 'll-mp-seg-div';
        segEls.push({ el: divEl, h: DIV_H });
        totalH += DIV_H;
      }

      // 工序段
      const seg = document.createElement('div');
      seg.className = 'll-mp-op-seg';
      seg.style.borderColor = projItem.color;

      let segH = PAD_V;

      // 段标题
      const hd = document.createElement('div');
      hd.className = 'll-mp-op-seg-hd';
      hd.style.color = projItem.color;
      const opsCount = ops.reduce((n, op) => n + 1 + (this._data.childMap.get(op.gid) || []).filter(r => r.node_type === 'process').length, 0) + dProcs.length;
      const firstOpTitle = ops[0]?.title || (dProcs.length > 0 ? '工序' : '无作业');
      hd.textContent = projItem.label + ' · ' + firstOpTitle + (opsCount > 0 ? '  ·  ' + opsCount + ' 工序' : '');
      seg.appendChild(hd);
      segH += OP_HDR_H;

      // 岗位及其工序
      for (const op of ops) {
        const opDiv = document.createElement('div');
        opDiv.className = 'll-mp-op-item';
        opDiv.dataset.gid = op.gid;
        opDiv.textContent = op.title || '(岗位)';
        seg.appendChild(opDiv);
        segH += OP_ITEM_H;

        const procs = (this._data.childMap.get(op.gid) || []).filter(r => r.node_type === 'process');
        for (const proc of procs) {
          const pDiv = document.createElement('div');
          pDiv.className = 'll-mp-proc-item';
          pDiv.dataset.gid = proc.gid;
          pDiv.textContent = proc.title || '(工序)';
          seg.appendChild(pDiv);
          segH += OP_ITEM_H;
        }
      }
      // 直属工序
      for (const proc of dProcs) {
        const pDiv = document.createElement('div');
        pDiv.className = 'll-mp-proc-item';
        pDiv.dataset.gid = proc.gid;
        pDiv.textContent = proc.title || '(工序)';
        seg.appendChild(pDiv);
        segH += OP_ITEM_H;
      }

      segH += PAD_V;
      segEls.push({ el: seg, h: segH });
      totalH += segH;
    }

    // 向 container 追加并计算 top 位置
    for (const { el } of segEls) container.appendChild(el);

    if (isDown) {
      container.style.top = (sy + LL_STATION_H + BLOCK_GAP) + 'px';
      parentEl.appendChild(container);
    } else {
      // 先不设 top，插入 DOM 后读取 offsetHeight（强制同步回流），再精确定位
      container.style.visibility = 'hidden';
      container.style.position = 'absolute';
      container.style.top = '-9999px';  // 不影响可见区域
      parentEl.appendChild(container);
      // offsetHeight 强制同步 layout，不受 canvas transform(scale) 影响
      const actualH = container.offsetHeight || totalH;
      container.style.top = (sy - actualH - BLOCK_GAP) + 'px';
      container.style.visibility = '';
    }
  }

  /**
   * 多项目车周区：每项目一行岗位槽位
   */
  _renderMergedLineCarArea(layoutEl, { topY, flowDir, columns, lineGid }, mergedStations) {
    const carAreaTop = topY + LL_STATION_H;
    const rowH = Math.floor(LL_CAR_AREA_H / this._data.projectVersions.length);
    const isRight = flowDir === 'right';

    for (let pi = 0; pi < this._data.projectVersions.length; pi++) {
      const proj  = this._data.projectVersions[pi];
      const pc    = this._data.projectColors.get(proj.versionGid) || { color: '#888', label: String.fromCharCode(65 + pi) };
      const rowY  = carAreaTop + pi * rowH;
      const midY  = rowY + Math.floor(rowH / 2);

      for (let i = 0; i < columns.length; i++) {
        const cx = LL_LINE_PAD + i * (LL_STATION_W + LL_STATION_GAP) + Math.round(LL_STATION_W / 2);
        const col = columns[i];

        // 项目标签（第一列左侧）
        if (i === 0) {
          const lbl = document.createElement('div');
          lbl.className = 'll-mp-car-label';
          lbl.style.cssText = `position:absolute;left:${LL_LINE_PAD - 16}px;top:${midY - 7}px;color:${pc.color};font-size:9px;font-weight:700`;
          lbl.textContent = pc.label;
          layoutEl.appendChild(lbl);
        }

        // 收集该项目在本列的岗位占用
        const occupiedPos = new Set();
        for (const msSide of [col?.top, col?.bottom]) {
          if (!msSide) continue;
          const projItem = msSide.items.find(it => it.versionGid === proj.versionGid);
          if (!projItem) continue;
          for (const op of this._collectDeepByTypes(projItem.row.gid, ['operator_process'])) {
            const ext = op.entity_data?.ext || {};
            if (ext.position) occupiedPos.add(ext.position);
          }
        }

        // 6个岗位槽位
        const slotDefs = [
          { n: 'A', dx: isRight ?  41 : -63, dy: -8 },
          { n: 'B', dx: isRight ?   5 : -27, dy: -22 },
          { n: 'C', dx: isRight ? -27 :   5, dy: -22 },
          { n: 'D', dx: isRight ?   5 : -27, dy:  10 },
          { n: 'E', dx: isRight ? -27 :   5, dy:  10 },
          { n: 'F', dx: isRight ? -63 :  41, dy:  -8 },
        ];
        for (const { n, dx, dy } of slotDefs) {
          const slot = document.createElement('div');
          slot.className = 'll-op-slot' + (occupiedPos.has(n) ? ' ll-op-slot-occupied' : '');
          slot.dataset.position = n;
          slot.dataset.lineGid  = lineGid;
          slot.style.left = (cx + dx) + 'px';
          slot.style.top  = (midY + dy) + 'px';
          slot.style.borderColor = occupiedPos.has(n) ? pc.color : '';
          slot.textContent = n;
          slot.addEventListener('click', (e) => {
            e.stopPropagation();
            this._togglePositionHighlight(n, lineGid);
          });
          layoutEl.appendChild(slot);
        }
      }
    }
  }

  /**
   * 创建工位子卡片 — 复用列视图卡片结构（lv-card-main + lv-stats-box）
   */

  _createRingCard(row) {
    const el = document.createElement('div');
    el.className = 'll-ring-card' + (this._editMode ? ' ll-draggable' : '');
    el.dataset.gid = row.gid;

    const isProcess  = row.node_type === 'process';

    if (isProcess) {
      // ── 工序卡片专属布局 ──────────────────────────────────────────
      // 左侧：徽标+标题（可换行）+ 底部统计小字
      // 右侧：统计面板（保留，用于图片）
      el.style.cssText = 'display:flex;align-items:stretch;padding:0;overflow:hidden';

      const leftEl = document.createElement('div');
      leftEl.style.cssText = 'display:flex;flex-direction:column;justify-content:space-between;padding:5px 4px 4px 8px;flex:1;min-width:0;overflow:hidden';

      // 徽标 + 标题内联
      const titleRow = document.createElement('div');
      titleRow.style.cssText = 'display:flex;align-items:flex-start;gap:4px';

      const typeEl = document.createElement('span');
      typeEl.className = 'lv-type lv-nt-process';
      typeEl.style.cssText = 'flex-shrink:0;margin-top:1px;font-size:11px;line-height:1.35';
      typeEl.textContent = '序';
      titleRow.appendChild(typeEl);

      const titleEl = document.createElement('span');
      titleEl.className = 'lv-title';
      titleEl.dataset.inlineTitle = '1';
      titleEl.style.cssText = [
        'font-size:11px;font-weight:500;color:var(--text,#cdd6f4)',
        'line-height:1.35;overflow:hidden;flex:1',
        'display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical',
        'word-break:break-all',
      ].join(';');
      titleEl.title = row.title || '';
      const titleHL = this._highlightTitle(row.title || '');
      if (titleHL) { titleEl.innerHTML = titleHL; el.classList.add('ll-search-hit'); }
      else { titleEl.textContent = row.title || '(无名称)'; }
      titleRow.appendChild(titleEl);
      leftEl.appendChild(titleRow);

      // 底部统计小字 — 与右侧统计面板使用同一优先级列表（_PROCESS_STATS_PRIORITY）
      const desc = typeof _getDescendantStats === 'function' ? _getDescendantStats(row.gid) : {};
      const statOrder  = ['operation','man','equipment_factory','equipment_need','fixture_factory','fixture_need','tool_need','part'];
      const statLabels = {
        operation:'操作', man:'人',
        equipment_factory:'设备', equipment_need:'设需',
        fixture_factory:'工装', fixture_need:'装需',
        tool_need:'工具', part:'零件',
      };
      // 工时放第一位，始终显示（无值显示 NA）
      const stdTime = row.entity_data?.standard_time;
      const stdTimeText = (stdTime != null && stdTime !== '') ? String(stdTime) + 's' : 'NA';
      const statParts  = [`工时 ${stdTimeText}`, ...statOrder.filter(nt => desc[nt] > 0).map(nt => `${statLabels[nt]} ${desc[nt]}`)];
      {
        const statsRow = document.createElement('div');
        statsRow.style.cssText = 'font-size:9px;color:var(--subtext0,#a6adc8);margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis';
        statsRow.textContent = statParts.join('  ');
        leftEl.appendChild(statsRow);
      }

      el.appendChild(leftEl);

      // 右侧统计面板：只保留图片功能，无图时显示空面板
      const statsBox = document.createElement('div');
      statsBox.className = 'lv-stats-box';
      statsBox.dataset.statsGid = row.gid;
      if (typeof _collectProcessPics === 'function') {
        const pics = _collectProcessPics(row.gid);
        if (pics.length) {
          const fill = document.createElement('div');
          fill.className = 'lv-stats-thumb-fill';
          fill.title = '工艺流程图（点击灯箱）';
          const img = document.createElement('img');
          img.className = 'lv-thumb-fill';
          img.src = pics[0];
          img.alt = 'process_flow_pic';
          img.onerror = () => { fill.innerHTML = ''; };
          fill.appendChild(img);
          statsBox.appendChild(fill);
        }
      }
      el.appendChild(statsBox);

    } else {
      // ── 其他节点类型：原有两行布局 ───────────────────────────────
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

      // 岗位位置徽标（operator_process 专用）
      if (row.node_type === 'operator_process') {
        const ext = row.entity_data?.ext || {};
        if (ext.position) {
          const posBadge = document.createElement('span');
          posBadge.className = 'll-op-pos-badge';
          posBadge.textContent = ext.position;
          posBadge.dataset.position = ext.position;
          posBadge.style.marginLeft = row.bom_row_id ? '4px' : 'auto';
          row1El.appendChild(posBadge);
        }
      }

      // 行2：标题
      const row2El = document.createElement('div');
      row2El.className = 'lv-row2';
      const titleEl = document.createElement('span');
      titleEl.className = 'lv-title';
      titleEl.dataset.inlineTitle = '1';
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
    }

    // 悬浮 + 按钮（根据节点类型添加对应操作）
    if (row.node_type === 'operator_process') {
      // 岗位卡片：下侧 + 添加工序（add_child → process）
      el.appendChild(this._makeLayoutFBtn('lv-fbtn-bottom', 'add_child', row.gid));
    } else if (row.node_type === 'process') {
      // 工序卡片：上下各加一个 + 添加兄弟工序
      // L 工位（向上展开）：顶部=远离工位=add_below，底部=靠近工位=add_above
      // R 工位（向下展开）：顶部=靠近工位=add_above，底部=远离工位=add_below
      // 查父节点（operator_process 或 station_process）的展开方向
      const parentDir = this._stationDirection.get(row.parent_gid)
                     ?? this._stationDirection.get(
                          this._data?.rowByGid?.get(row.parent_gid)?.parent_gid
                        );
      const expandsUp = parentDir === 'up';
      el.appendChild(this._makeLayoutFBtn('lv-fbtn-top',    expandsUp ? 'add_below' : 'add_above', row.gid));
      el.appendChild(this._makeLayoutFBtn('lv-fbtn-bottom', expandsUp ? 'add_above' : 'add_below', row.gid));
    }

    return el;
  }

  /**
   * 在卡片标题元素上开启内联编辑（工序/岗位双击触发）。
   * 版本不可编辑时不调用此方法。
   */
  _startInlineTitleEdit(cardEl, gid) {
    const titleEl = cardEl.querySelector('[data-inline-title]');
    if (!titleEl) return;
    const row = this._data?.rowByGid?.get(gid);
    const origText = row?.title || titleEl.textContent || '';

    const inp = document.createElement('input');
    inp.type = 'text';
    inp.value = origText;
    inp.className = 'll-title-input';
    inp.style.cssText = [
      'width:100%;min-width:0;box-sizing:border-box',
      'border:none;outline:1px solid var(--blue,#89b4fa)',
      'border-radius:2px;padding:0 3px',
      'background:var(--surface1,#45475a);color:var(--text,#cdd6f4)',
      'font-size:inherit;font-weight:inherit;line-height:inherit',
    ].join(';');

    titleEl.style.display = 'none';
    titleEl.insertAdjacentElement('afterend', inp);
    inp.focus();
    inp.select();

    let done = false;
    const finish = async (save) => {
      if (done) return;
      done = true;
      inp.remove();
      titleEl.style.display = '';
      if (!save) return;
      const newTitle = inp.value.trim();
      if (!newTitle || newTitle === origText) return;
      titleEl.textContent = newTitle;
      if (row) row.title = newTitle;
      try {
        await this._data?.patchEntry?.(gid, { title: newTitle });
      } catch (_) {
        // rollback DOM on failure
        titleEl.textContent = origText;
        if (row) row.title = origText;
      }
    };

    inp.addEventListener('keydown', e => {
      if (e.key === 'Enter')  { e.stopPropagation(); finish(true); }
      if (e.key === 'Escape') { e.stopPropagation(); finish(false); }
    });
    inp.addEventListener('blur', () => finish(true));
    inp.addEventListener('dblclick',  e => e.stopPropagation());
    inp.addEventListener('mousedown', e => e.stopPropagation());
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
  _renderLineCarArea(layoutEl, { topY, flowDir, columns, lineGid }) {
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

      // 收集本列（L+R 两个工位）已占用的岗位位置
      const occupiedPos = new Set();
      const _col = columns[i];
      for (const stn of [_col?.top, _col?.bottom]) {
        if (!stn) continue;
        for (const op of this._collectDeepByTypes(stn.gid, ['operator_process'])) {
          const ext = op.entity_data?.ext || {};
          if (ext.position) occupiedPos.add(ext.position);
        }
      }

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
        slot.className = 'll-op-slot' + (occupiedPos.has(n) ? ' ll-op-slot-occupied' : '');
        slot.dataset.position = n;
        slot.dataset.lineGid  = lineGid;
        slot.style.left = (cx + dx) + 'px';
        slot.style.top  = (midY + dy) + 'px';
        slot.textContent = n;
        slot.addEventListener('click', (e) => {
          e.stopPropagation();
          this._togglePositionHighlight(n, lineGid);
        });
        layoutEl.appendChild(slot);
      }
    }
  }

  /**
   * 工序卡片统计区无图片时弹出图片上传/粘贴弹窗
   */
  async _openPicUploadDialog(gid, row) {
    const overlay = document.createElement('div');
    overlay.className = 'lv-dialog-overlay';
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.55);z-index:10000;display:flex;align-items:center;justify-content:center';

    const dlg = document.createElement('div');
    dlg.className = 'lv-modal';
    dlg.style.cssText = 'width:520px;max-height:80vh;overflow-y:auto';
    dlg.innerHTML = `
      <div class="lv-modal-title">工序图片管理</div>
      <div class="lv-modal-hint" style="margin-bottom:8px">
        可粘贴剪贴板图片（<kbd>Ctrl+V</kbd>）或点击 + 选择本地文件
      </div>
      <div style="font-size:11px;font-weight:600;color:var(--subtext0,#a6adc8);margin-bottom:4px">工艺流程图</div>
      <div id="_picDlgAreaFlow"></div>
      <div style="font-size:11px;color:var(--overlay0,#6c7086);margin-top:8px;padding:6px 8px;
           background:var(--base,#1e1e2e);border-radius:4px;border:1px dashed var(--surface2,#585b70);
           text-align:center;cursor:pointer" id="_picDlgPasteHintFlow">
        📋 点击此处后按 Ctrl+V 粘贴到工艺流程图
      </div>
      <div style="font-size:11px;font-weight:600;color:var(--subtext0,#a6adc8);margin:14px 0 4px">工艺卡图片</div>
      <div id="_picDlgAreaChart"></div>
      <div style="font-size:11px;color:var(--overlay0,#6c7086);margin-top:8px;padding:6px 8px;
           background:var(--base,#1e1e2e);border-radius:4px;border:1px dashed var(--surface2,#585b70);
           text-align:center;cursor:pointer" id="_picDlgPasteHintChart">
        📋 点击此处后按 Ctrl+V 粘贴到工艺卡图片
      </div>
      <div class="lv-modal-actions">
        <button class="lv-modal-btn-ghost" id="_picDlgCancel">取消</button>
        <button class="lv-modal-btn-primary" id="_picDlgOk">保存</button>
      </div>`;
    overlay.appendChild(dlg);
    document.body.appendChild(overlay);

    // 初始化图片区域
    const flowPics = Array.isArray(row.process_flow_pic) ? [...row.process_flow_pic]
                  : (row.process_flow_pic ? [row.process_flow_pic] : []);
    const chartPics = Array.isArray(row.process_chart_pic) ? [...row.process_chart_pic]
                   : (row.process_chart_pic ? [row.process_chart_pic] : []);
    let pendingFlowPics = [...flowPics];
    let pendingChartPics = [...chartPics];
    const flowAreaEl = dlg.querySelector('#_picDlgAreaFlow');
    const chartAreaEl = dlg.querySelector('#_picDlgAreaChart');

    const refresh = () => {
      this._data.renderPicArea(flowAreaEl, pendingFlowPics, 15, newList => {
        pendingFlowPics = newList;
        refresh();
      });
      this._data.renderPicArea(chartAreaEl, pendingChartPics, 15, newList => {
        pendingChartPics = newList;
        refresh();
      });
    };
    refresh();

    // 粘贴图片支持
    const onPaste = async (e) => {
      const items = e.clipboardData?.items;
      if (!items) return;
      const activeTarget = dlg.dataset.pasteTarget === 'chart' ? 'chart' : 'flow';
      for (const item of items) {
        if (item.type.startsWith('image/')) {
          const file = item.getAsFile();
          const targetList = activeTarget === 'chart' ? pendingChartPics : pendingFlowPics;
          const hintId = activeTarget === 'chart' ? '#_picDlgPasteHintChart' : '#_picDlgPasteHintFlow';
          if (!file || targetList.length >= 15) continue;
          const hint = dlg.querySelector(hintId);
          if (hint) hint.textContent = '上传中…';
          try {
            const pic = await (typeof _uploadBopPic === 'function' ? _uploadBopPic(file) : null);
            if (pic) {
              targetList.push(pic);
              if (activeTarget === 'chart') pendingChartPics = targetList;
              else pendingFlowPics = targetList;
              refresh();
            }
          } catch (err) { /* ignore */ }
          if (hint) hint.textContent = activeTarget === 'chart'
            ? '📋 点击此处后按 Ctrl+V 粘贴到工艺卡图片'
            : '📋 点击此处后按 Ctrl+V 粘贴到工艺流程图';
        }
      }
    };
    document.addEventListener('paste', onPaste);

    // 粘贴区域聚焦提示
    dlg.querySelector('#_picDlgPasteHintFlow').addEventListener('click', () => {
      dlg.dataset.pasteTarget = 'flow';
      dlg.querySelector('#_picDlgPasteHintFlow').focus?.();
    });
    dlg.querySelector('#_picDlgPasteHintChart').addEventListener('click', () => {
      dlg.dataset.pasteTarget = 'chart';
      dlg.querySelector('#_picDlgPasteHintChart').focus?.();
    });

    // 关闭
    const close = () => {
      document.removeEventListener('paste', onPaste);
      overlay.remove();
    };

    dlg.querySelector('#_picDlgCancel').addEventListener('click', close);
    overlay.addEventListener('click', e => { if (e.target === overlay) close(); });

    // 保存
    dlg.querySelector('#_picDlgOk').addEventListener('click', async () => {
      const btn = dlg.querySelector('#_picDlgOk');
      btn.disabled = true;
      btn.textContent = '保存中…';
      try {
        await this._data.patchEntry(gid, {
          process_flow_pic: pendingFlowPics,
          process_chart_pic: pendingChartPics,
        });
        // 更新内存中的 row 数据
        if (this._data?.rowByGid?.get(gid)) {
          this._data.rowByGid.get(gid).process_flow_pic = pendingFlowPics;
          this._data.rowByGid.get(gid).process_chart_pic = pendingChartPics;
        }
        if (this._data?.preserveView) this._data.preserveView();
        if (typeof _reload === 'function') _reload();
        close();
      } catch (e) {
        btn.disabled = false;
        btn.textContent = '保存';
        if (this._data?.toast) this._data.toast('保存失败: ' + e.message, 'error');
      }
    });
  }

  /**
   * 创建布局视图用的悬浮 + 按钮（样式复用列视图的 lv-fbtn）
   */
  _makeLayoutFBtn(posClass, action, gid) {
    const btn = document.createElement('button');
    btn.className = `lv-fbtn ${posClass}`;
    btn.textContent = '＋';
    btn.dataset.action = action;
    btn.addEventListener('click', e => {
      e.stopPropagation();
      if (typeof _handleFBtnAction === 'function') {
        _handleFBtnAction(action, gid);
      }
    });
    return btn;
  }

  /**
   * 清除所有位置高亮
   */
  _clearPositionHighlight() {
    this._world.querySelectorAll('.ll-op-slot.ll-slot-active')
      .forEach(el => el.classList.remove('ll-slot-active'));
    this._world.querySelectorAll('.ll-ring-card.ll-op-highlight')
      .forEach(el => el.classList.remove('ll-op-highlight'));
    this._activePosition     = null;
    this._activePositionLine = null;
  }

  /**
   * 点击 ABCDEF 槽位：高亮/取消高亮同位置的岗位工艺卡片
   */
  _togglePositionHighlight(position, lineGid) {
    const isActive = this._activePosition === position && this._activePositionLine === lineGid;

    this._clearPositionHighlight();

    if (!isActive) {
      this._activePosition     = position;
      this._activePositionLine = lineGid;

      // 高亮同位置的所有槽位
      this._world.querySelectorAll(`.ll-op-slot[data-position="${position}"][data-line-gid="${lineGid}"]`)
        .forEach(el => el.classList.add('ll-slot-active'));

      // 高亮所有 operator_process 环形卡片中 entity_data.ext.position 匹配的
      this._world.querySelectorAll('.ll-ring-card[data-gid]').forEach(cardEl => {
        const row = this._data.rowByGid?.get(cardEl.dataset.gid);
        if (!row || row.node_type !== 'operator_process') return;
        const ext = row.entity_data?.ext || {};
        if (ext.position === position) {
          cardEl.classList.add('ll-op-highlight');
        }
      });
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
    // 平移/缩放停止后检查虚拟渲染（100ms 防抖）
    clearTimeout(this._vrTimer);
    this._vrTimer = setTimeout(() => this._checkVirtualRender(), 100);
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
    const pct = Math.round(this._zoom * 100);
    if (this._zoomPctEl) this._zoomPctEl.textContent = pct + '%';
    const slider = this._container.querySelector('#llZoomSlider');
    if (slider) slider.value = pct;
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

    // ── 鼠标滚轮：Ctrl+滚轮=缩放，Shift+滚轮=水平平移，普通滚轮=上下平移 ──
    vp.addEventListener('wheel', e => {
      e.preventDefault();
      if (e.ctrlKey) {
        const factor = e.deltaY < 0 ? 1.1 : 0.9;
        this._zoomAt(factor, e.clientX, e.clientY);
      } else if (e.shiftKey) {
        const delta = e.deltaY !== 0 ? e.deltaY : e.deltaX;
        this._panX -= delta;
        this._setTransform();
        this._syncMinimapViewport();
      } else {
        this._panY -= e.deltaY;
        this._setTransform();
        this._syncMinimapViewport();
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

      // Ctrl+C：复制当前选中的工序/操作卡片
      if ((e.ctrlKey || e.metaKey) && e.key === 'c' && this._activeGid) {
        const row = this._data?.rowByGid.get(this._activeGid);
        if (row && (row.node_type === 'process' || row.node_type === 'operation')) {
          this._clipboard = { row };
          // 高亮被复制的卡片
          this._world.querySelectorAll('.ll-ring-card.ll-copied').forEach(el => el.classList.remove('ll-copied'));
          const el = this._world.querySelector(`.ll-ring-card[data-gid="${row.gid}"]`);
          if (el) el.classList.add('ll-copied');
          this._data?.toast?.(`已复制「${row.title || row.node_type}」`, 'ok');
          e.preventDefault();
        }
      }

      // Ctrl+V：粘贴工序到当前选中的岗位或工位
      if ((e.ctrlKey || e.metaKey) && e.key === 'v' && this._clipboard && this._activeGid) {
        const target = this._data?.rowByGid.get(this._activeGid);
        const validTargets = ['operator_process', 'station_process'];
        if (target && validTargets.includes(target.node_type)) {
          e.preventDefault();
          this._pasteEntry(this._clipboard.row, target);
        }
      }
    });
    document.addEventListener('keyup', e => {
      if (e.code === 'Space') {
        this._spaceDown = false;
      }
    });

    vp.addEventListener('mousedown', e => {
      // + 按钮（fbtn）点击不触发任何拖拽/卡片点击逻辑
      if (e.target.closest('.lv-fbtn')) return;

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

      // 通用 demote 拖拽：任意带 gid 的卡片（非编辑模式）
      if (e.button === 0 && !this._editMode) {
        const card = e.target.closest('[data-gid]');
        if (card && !e.target.closest('.ll-draggable')) {
          const gid = card.dataset.gid;
          const row = this._data?.rowByGid.get(gid);
          if (row) {
            // 先执行高亮
            this.highlightNode(gid);
            if (this._data.applyActiveState) this._data.applyActiveState(gid);
            this._data.refreshOverlayIfPinned?.(gid);
            // 记录 demote 拖拽 pending
            this._demotePending = { el: card, row, startX: e.clientX, startY: e.clientY };
          }
          return;
        }
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

    // ── 鼠标移动（平移/拖拽/重挂/demote） ──
    const onDocMouseMove = e => {
      this._edgeMouseClient.x = e.clientX;
      this._edgeMouseClient.y = e.clientY;

      // 有拖拽时启动边缘自动滚动
      if (this._dragState || this._reparentDrag || this._demoteDrag || this._stagingDrag) {
        this._startEdgeScroll();
      }

      if (this._panState) {
        const dx = e.clientX - this._panState.startX;
        const dy = e.clientY - this._panState.startY;
        this._panX = this._panState.origPanX + dx;
        this._panY = this._panState.origPanY + dy;
        this._setTransform();
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
        // 检查是否悬停在暂存箱上方
        this._updateStagingDropHighlight(e);
        return;
      }
      // demote 拖拽：超过阈值后激活 ghost
      if (this._demotePending) {
        const dx = e.clientX - this._demotePending.startX;
        const dy = e.clientY - this._demotePending.startY;
        if (Math.abs(dx) > 5 || Math.abs(dy) > 5) {
          this._activateDemoteDrag(this._demotePending);
          this._demotePending = null;
        }
        return;
      }
      if (this._demoteDrag) {
        this._onDemoteDragMove(e);
        return;
      }
      // 暂存箱拖入画布（复用 reparent 高亮机制）
      if (this._stagingDrag) {
        this._onStagingDragMove(e);
        return;
      }
    };
    document.addEventListener('mousemove', onDocMouseMove);

    // ── 鼠标释放（document 级别，确保在画布外也能捕获） ──
    const onDocMouseUp = e => {
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
        // 打开底部详情面板
        if (this._data?.layoutDetailPanel) this._data.layoutDetailPanel.open(row.gid);
        return;
      }
      // 重挂：active → 先检查是否在暂存箱上方
      if (this._reparentDrag) {
        if (this._isCursorOverStaging(e)) {
          this._commitDemoteFromReparent(e);
        } else {
          this._commitReparent();
        }
        return;
      }
      // demote：pending → 视为已完成的点击（高亮已在 mousedown 做了）
      if (this._demotePending) {
        const gid = this._demotePending.row.gid;
        this._demotePending = null;
        // 打开底部详情面板
        if (this._data?.layoutDetailPanel) this._data.layoutDetailPanel.open(gid);
        return;
      }
      // demote：active → 提交到暂存箱
      if (this._demoteDrag) {
        this._commitDemoteDrag(e);
        return;
      }
      // 暂存箱拖入画布：提交 promote
      if (this._stagingDrag) {
        this._commitStagingDrag(e);
        return;
      }
    };
    document.addEventListener('mouseup', onDocMouseUp);

    // ── 鼠标离开画布：只取消平移，不取消重挂/demote 拖拽（允许拖出到暂存箱） ──
    vp.addEventListener('mouseleave', () => {
      if (this._panState) {
        this._panState = null;
        vp.style.cursor = '';
      }
      // 注意：不再在这里取消 reparentDrag 和 demoteDrag
      // 它们现在由 document 级 mouseup 处理
    });

    // ── 双击卡片主体区打开底部详情面板（排除统计区） ──
    vp.addEventListener('dblclick', e => {
      // stats box 双击处理
      const box = e.target.closest('.lv-stats-box');
      if (box) {
        e.stopPropagation();
        const gid = box.dataset.statsGid;
        const row = this._data?.rowByGid?.get(gid);
        if (row?.node_type === 'process' && this._data?.renderPicArea && this._data?.patchEntry) {
          // 工序：有图→灯箱+底部「继续上传」；无图→直接上传弹窗
          if (box.querySelector('.lv-stats-thumb-fill')) {
            const pics = [];
            const _abs = s => window.AI00RuntimeConfig?.toAbsoluteBackendUrl?.(typeof s === 'string' ? s : '') || s;
            const _addPics = r => {
              for (const field of ['process_flow_pic', 'process_chart_pic']) {
                const val = r?.[field];
                if (Array.isArray(val)) val.forEach(p => { const s = _abs(typeof p === 'string' ? p : (p?.url || p?.src || '')); if (s) pics.push(s); });
                else if (typeof val === 'string' && val) pics.push(_abs(val));
              }
            };
            _addPics(row);
            for (const child of (this._data?.childMap?.get(gid) || [])) {
              if (child.node_type === 'operation') _addPics(child);
            }
            if (pics.length && this._data?.openImageLightbox) {
              this._data.openImageLightbox(pics, 0, {
                onAddMore: () => this._openPicUploadDialog(gid, row),
              });
            }
          } else {
            this._openPicUploadDialog(gid, row);
          }
          return;
        }
        // 其他节点 stats box 双击：有图→灯箱，无图→详情面板
        if (box.querySelector('.lv-stats-thumb-fill')) {
          const pics = [];
          const _abs = s => window.AI00RuntimeConfig?.toAbsoluteBackendUrl?.(typeof s === 'string' ? s : '') || s;
          const _addPics = r => {
            for (const field of ['process_flow_pic', 'process_chart_pic']) {
              const val = r?.[field];
              if (Array.isArray(val)) val.forEach(p => { const s = _abs(typeof p === 'string' ? p : (p?.url || p?.src || '')); if (s) pics.push(s); });
              else if (typeof val === 'string' && val) pics.push(_abs(val));
            }
          };
          _addPics(row);
          for (const child of (this._data?.childMap?.get(gid) || [])) {
            if (child.node_type === 'operation') _addPics(child);
          }
          if (pics.length && this._data?.openImageLightbox) this._data.openImageLightbox(pics);
        } else if (this._data?.layoutDetailPanel) {
          this._data.layoutDetailPanel.open(gid);
        }
        return;
      }

      // 非 stats box：双击卡片打开详情面板
      const card = e.target.closest('[data-gid]');
      if (card && this._data) {
        const gid = card.dataset.gid;
        // 工序 / 岗位：双击标题区触发内联编辑（版本可编辑时）
        const onTitleEl = e.target.closest('[data-inline-title]');
        if (onTitleEl && this._data.isEditable && this._data.startInlineRename) {
          e.stopPropagation();
          this._data.startInlineRename(card);
          return;
        }
        if (this._data.layoutDetailPanel) {
          this._data.layoutDetailPanel.open(gid);
        } else if (this._data.openOverlayPanel) {
          this._data.openOverlayPanel(gid);
        }
      }
    });

    // ── HTML5 拖拽：只接受关联面板的 drop（暂存箱改为自定义拖拽） ──
    vp.addEventListener('dragover', e => {
      const isAssoc = e.dataTransfer.types.includes('application/x-assoc-item');
      if (!isAssoc) return;

      e.preventDefault();

      // 用 getBoundingClientRect 命中检测
      const hitCard = this._hitTestCard(e.clientX, e.clientY);
      if (hitCard !== this._html5DragHovered) {
        if (this._html5DragHovered) this._html5DragHovered.classList.remove('ll-drop-target-hovered');
        this._html5DragHovered = hitCard;
        if (hitCard) hitCard.classList.add('ll-drop-target-hovered');
      }

      e.dataTransfer.dropEffect = hitCard ? 'copy' : 'none';
    });

    vp.addEventListener('dragleave', e => {
      if (!vp.contains(e.relatedTarget)) {
        if (this._html5DragHovered) {
          this._html5DragHovered.classList.remove('ll-drop-target-hovered');
          this._html5DragHovered = null;
        }
      }
    });

    vp.addEventListener('drop', async e => {
      e.preventDefault();
      if (this._html5DragHovered) {
        this._html5DragHovered.classList.remove('ll-drop-target-hovered');
        this._html5DragHovered = null;
      }
      if (!this._data) return;
      const { cf, assocPanel, versionGid, toast, reloadData } = this._data;

      // ── 关联面板 → 画布（Link-Only：必须拖到卡片上） ──
      const assocData = e.dataTransfer.getData('application/x-assoc-item');
      if (assocData && cf && versionGid) {
        const hitCard = this._hitTestCard(e.clientX, e.clientY);
        const targetGid = hitCard?.dataset.gid || null;
        if (!targetGid) {
          if (toast) toast('请拖到节点卡片上创建关联', 'warn');
          return;
        }
        try {
          const info = JSON.parse(assocData);
          if (!info.refGid || !info.linkType) throw new Error('缺少关联信息');
          await cf('/api/bop/entry-links', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              bop_entry_gid: targetGid,
              link_type:     info.linkType,
              ref_gid:       info.refGid,
              is_primary:    info.isPrimary ?? false,
            }),
          });
          if (toast) toast('已创建关联', 'ok');
          if (reloadData) await reloadData();
          if (assocPanel) assocPanel.refresh();
        } catch (ex) {
          if (toast) toast('关联失败: ' + ex.message, 'error');
        }
      }
    });

    // ── 统计区点击：有图片→灯箱预览；无图→统计浮框 ──
    vp.addEventListener('click', e => {
      // 点击非槽位区域 → 取消岗位位置高亮
      if (!e.target.closest('.ll-op-slot') && this._activePosition) {
        this._clearPositionHighlight();
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
   * 绑定画布内缩放滑条
   */
  _bindZoomControls() {
    const slider = this._container.querySelector('#llZoomSlider');
    if (!slider) return;
    slider.addEventListener('input', () => {
      const newZoom = Math.max(LL_MIN_ZOOM, Math.min(LL_MAX_ZOOM, parseInt(slider.value) / 100));
      const vpRect = this._viewport.getBoundingClientRect();
      const vpCX = vpRect.left + vpRect.width / 2;
      const vpCY = vpRect.top + vpRect.height / 2;
      const worldX = (vpCX - vpRect.left - this._panX) / this._zoom;
      const worldY = (vpCY - vpRect.top - this._panY) / this._zoom;
      this._zoom = newZoom;
      this._panX = vpCX - vpRect.left - worldX * newZoom;
      this._panY = vpCY - vpRect.top - worldY * newZoom;
      this._setTransform();
      this._syncZoomDependent();
      this._updateZoomLabel();
      this._syncMinimapViewport();
    });
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

  _startEdgeScroll() {
    if (this._edgeScrollRaf) return;
    const EDGE = 80;      // 距边缘触发范围 px
    const MAX_SPEED = 20; // 最大平移速度 px/帧
    const tick = () => {
      const hasDrag = this._dragState || this._reparentDrag || this._demoteDrag || this._stagingDrag;
      if (!hasDrag) { this._edgeScrollRaf = null; return; }
      const vr = this._viewport.getBoundingClientRect();
      const { x, y } = this._edgeMouseClient;
      let dx = 0, dy = 0;
      if (x - vr.left < EDGE)   dx =  (1 - (x - vr.left)  / EDGE) * MAX_SPEED;
      if (vr.right - x < EDGE)  dx = -(1 - (vr.right - x) / EDGE) * MAX_SPEED;
      if (y - vr.top < EDGE)    dy =  (1 - (y - vr.top)   / EDGE) * MAX_SPEED;
      if (vr.bottom - y < EDGE) dy = -(1 - (vr.bottom - y) / EDGE) * MAX_SPEED;
      if (dx !== 0 || dy !== 0) {
        this._panX += dx;
        this._panY += dy;
        this._setTransform();
        this._syncMinimapViewport();
      }
      this._edgeScrollRaf = requestAnimationFrame(tick);
    };
    this._edgeScrollRaf = requestAnimationFrame(tick);
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
  // 线体滚轮导航
  // ══════════════════════════════════════════════════════════════════

  /** 初始化滚轮导航（绑定事件，仅调用一次；后续只更新显示内容） */
  _renderLineNav() {
    const wheel = document.getElementById('llLineWheel');
    if (!wheel) return;

    // 事件只绑定一次
    if (!wheel.dataset.bound) {
      wheel.dataset.bound = '1';

      // 鼠标滚轮：改变焦点索引，不跳转
      wheel.addEventListener('wheel', e => {
        e.preventDefault();
        e.stopPropagation();
        const lines = this._filteredLines || [];
        if (!lines.length) return;
        this._wheelIdx = e.deltaY > 0
          ? Math.min(this._wheelIdx + 1, lines.length - 1)
          : Math.max(this._wheelIdx - 1, 0);
        this._updateWheelDisplay();
      }, { passive: false });

      // 点击上一条：先移动焦点再跳转
      document.getElementById('llWheelPrev')?.addEventListener('click', () => {
        const lines = this._filteredLines || [];
        if (!lines.length) return;
        this._wheelIdx = Math.max(this._wheelIdx - 1, 0);
        this._updateWheelDisplay();
        this._scrollToLine(lines[this._wheelIdx].gid);
      });

      // 点击当前条：直接跳转
      document.getElementById('llWheelCurrent')?.addEventListener('click', () => {
        const lines = this._filteredLines || [];
        if (!lines[this._wheelIdx]) return;
        this._scrollToLine(lines[this._wheelIdx].gid);
      });

      // 点击下一条：先移动焦点再跳转
      document.getElementById('llWheelNext')?.addEventListener('click', () => {
        const lines = this._filteredLines || [];
        if (!lines.length) return;
        this._wheelIdx = Math.min(this._wheelIdx + 1, lines.length - 1);
        this._updateWheelDisplay();
        this._scrollToLine(lines[this._wheelIdx].gid);
      });

      // 右键：显示多选菜单
      wheel.addEventListener('contextmenu', e => {
        e.preventDefault();
        e.stopPropagation();
        this._showLinePicker(e);
      });
    }

    // 重置焦点到第一条（每次重渲染数据时）
    this._wheelIdx = 0;
    this._updateWheelDisplay();
  }

  /** 刷新滚轮三格的文字内容，以及过滤徽标 */
  _updateWheelDisplay() {
    const lines = this._filteredLines || [];
    const idx   = this._wheelIdx;
    const setText = (id, row) => {
      const el = document.getElementById(id);
      if (!el) return;
      if (row) {
        el.textContent  = row.title || '(未命名)';
        el.title        = row.title || '';
        el.style.display = '';
      } else {
        el.textContent  = '';
        el.style.display = 'none';
      }
    };
    setText('llWheelPrev',    lines[idx - 1] || null);
    setText('llWheelCurrent', lines[idx]     || null);
    setText('llWheelNext',    lines[idx + 1] || null);

    // 过滤徽标：线体筛选激活（非全选）时显示"x/total"
    const badge = document.getElementById('llWheelBadge');
    if (badge) {
      const total = this._allLines.length;
      const filterActive = this._data?.level1Filter !== null && lines.length < total;
      if (filterActive) {
        badge.textContent = `${lines.length}/${total}`;
        badge.style.display = '';
      } else {
        badge.style.display = 'none';
      }
    }
  }

  // 保留空实现，避免遗留调用报错
  _setCurrentLineLabel() {}

  // ══════════════════════════════════════════════════════════════════
  // 线体多选菜单
  // ══════════════════════════════════════════════════════════════════

  _showLinePicker(mouseEvent) {
    this._hideLinePicker();
    const allLines = this._allLines || [];
    if (!allLines.length) return;

    const menu = document.createElement('div');
    menu.id = 'llLinePicker';
    menu.className = 'll-line-picker';

    // 主题从 documentElement 继承，保持与画布一致
    const theme = document.documentElement.dataset.lvTheme || 'dark';
    if (theme === 'light') menu.dataset.lvTheme = 'light';

    // 头部：标题 + 全选 + 清除
    const hdr = document.createElement('div');
    hdr.className = 'll-lp-header';
    hdr.innerHTML = `<span class="ll-lp-title">选择线体</span>
      <button class="ll-lp-btn" id="llLpAll">全选</button>
      <button class="ll-lp-btn" id="llLpNone">清除</button>`;
    menu.appendChild(hdr);

    // 列表
    const body = document.createElement('div');
    body.className = 'll-lp-body';
    for (const line of allLines) {
      const isChecked = this._data?.level1Filter === null || this._data?.level1Filter?.has(line.gid);
      const item = document.createElement('label');
      item.className = 'll-lp-item';
      item.innerHTML = `<input type="checkbox" data-gid="${line.gid}"${isChecked ? ' checked' : ''}><span>${line.title || '(未命名)'}</span>`;
      body.appendChild(item);
    }
    menu.appendChild(body);

    // 定位：在滚轮下方
    const wheelRect = document.getElementById('llLineWheel')?.getBoundingClientRect();
    if (wheelRect) {
      menu.style.left = wheelRect.left + 'px';
      menu.style.top  = (wheelRect.bottom + 6) + 'px';
    } else {
      menu.style.left = '14px';
      menu.style.top  = '120px';
    }
    document.body.appendChild(menu);

    // 按钮：全选 / 清除
    menu.querySelector('#llLpAll').addEventListener('click', () => {
      menu.querySelectorAll('input[type="checkbox"]').forEach(cb => { cb.checked = true; });
      this._applyLinePicker(menu);
    });
    menu.querySelector('#llLpNone').addEventListener('click', () => {
      menu.querySelectorAll('input[type="checkbox"]').forEach(cb => { cb.checked = false; });
      this._applyLinePicker(menu);
    });

    // 每次勾选立即生效
    menu.querySelectorAll('input[type="checkbox"]').forEach(cb => {
      cb.addEventListener('change', () => this._applyLinePicker(menu));
    });

    // 点击菜单外部关闭
    const onOutside = ev => {
      if (!menu.contains(ev.target)) {
        this._hideLinePicker();
        document.removeEventListener('mousedown', onOutside);
      }
    };
    setTimeout(() => document.addEventListener('mousedown', onOutside), 0);
  }

  _hideLinePicker() {
    document.getElementById('llLinePicker')?.remove();
  }

  _applyLinePicker(menu) {
    const checked = [...menu.querySelectorAll('input[type="checkbox"]:checked')].map(cb => cb.dataset.gid);
    const total   = this._allLines.length;
    const newFilter = checked.length === total ? null : new Set(checked);

    // 记住当前聚焦的线体，以便重渲染后恢复
    const prevGid = (this._filteredLines || [])[this._wheelIdx]?.gid;

    // 通知 lineage.js 更新 _level1Filter（触发工具栏下拉同步 + 重渲染）
    this._data?.onLineFilterChange?.(newFilter);

    // 重渲染后恢复焦点（onLineFilterChange 是同步的）
    const newIdx = prevGid ? (this._filteredLines || []).findIndex(l => l.gid === prevGid) : -1;
    this._wheelIdx = newIdx >= 0 ? newIdx : 0;
    this._updateWheelDisplay();
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
    // 立即渲染目标线体（不等防抖）
    clearTimeout(this._vrTimer);
    this._checkVirtualRender();
  }

  /**
   * 将画布视口平移到指定节点卡片中央（保持当前缩放）
   */
  scrollToNode(gid) {
    const el = this._world.querySelector(`[data-gid="${gid}"]`);
    if (!el) return;

    // 用 getBoundingClientRect 获取元素在视口中的实际位置，避免中间层坐标计算误差
    const rect   = el.getBoundingClientRect();
    const vpRect = this._viewport.getBoundingClientRect();

    // 元素中心在 viewport 内的坐标
    const ecx = rect.left - vpRect.left + rect.width  / 2;
    const ecy = rect.top  - vpRect.top  + rect.height / 2;

    // viewport 中心
    const vw = this._viewport.clientWidth;
    const vh = this._viewport.clientHeight;

    // 平移量：让元素中心移到 viewport 中心
    this._panX += vw / 2 - ecx;
    this._panY += vh / 2 - ecy;
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

  _lsKey() {
    const base = 'lv:layout:' + (this._data?.versionGid || 'default');
    try { const u = window.parent?._authUser || window.top?._authUser || window._authUser; const g = u?.gid || u?.user_gid || ''; return g ? `${g}:${base}` : base; } catch { return base; }
  }

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

  // ── Demote 拖拽方法（画布卡片 → 暂存箱）──────────────────────────

  /** 判断鼠标是否在暂存箱 body 上方 */
  _isCursorOverStaging(e) {
    const stagingBody = document.getElementById('llDsBody');
    if (!stagingBody) return false;
    const r = stagingBody.getBoundingClientRect();
    return e.clientX >= r.left && e.clientX <= r.right &&
           e.clientY >= r.top  && e.clientY <= r.bottom;
  }

  /** 暂存箱 drop 高亮（拖拽过程中） */
  _updateStagingDropHighlight(e) {
    const stagingBody = document.getElementById('llDsBody');
    if (!stagingBody) return;
    if (this._isCursorOverStaging(e)) {
      stagingBody.classList.add('drag-over');
    } else {
      stagingBody.classList.remove('drag-over');
    }
  }

  /** 激活 demote 拖拽（通用卡片 → 暂存箱） */
  _activateDemoteDrag({ el, row, startX, startY }) {
    const ghost = document.createElement('div');
    ghost.className = 'll-reparent-ghost';
    ghost.style.width  = el.offsetWidth + 'px';
    ghost.style.height = el.offsetHeight + 'px';
    ghost.style.maxWidth  = '200px';
    ghost.style.maxHeight = '60px';
    ghost.style.overflow  = 'hidden';
    ghost.innerHTML = `<div style="padding:4px 8px;font-size:11px;color:#cdd6f4;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${row.title || row.gid}</div>`;
    ghost.style.left = (startX - 40) + 'px';
    ghost.style.top  = (startY - 20) + 'px';
    document.body.appendChild(ghost);

    this._demoteDrag = { row, ghostEl: ghost };
  }

  /** demote 拖拽 mousemove */
  _onDemoteDragMove(e) {
    const drag = this._demoteDrag;
    drag.ghostEl.style.left = (e.clientX - 40) + 'px';
    drag.ghostEl.style.top  = (e.clientY - 20) + 'px';
    this._updateStagingDropHighlight(e);
  }

  /** demote 拖拽 mouseup：如在暂存箱上方则 demote */
  async _commitDemoteDrag(e) {
    const drag = this._demoteDrag;
    this._demoteDrag = null;
    if (drag.ghostEl) drag.ghostEl.remove();
    const stagingBody = document.getElementById('llDsBody');
    if (stagingBody) stagingBody.classList.remove('drag-over');

    if (this._isCursorOverStaging(e)) {
      const { stagingPanel, toast } = this._data || {};
      if (stagingPanel) {
        try {
          this._preserveView = true;
          await stagingPanel.demoteEntry(drag.row.gid);
        } catch (ex) {
          if (toast) toast('降级失败: ' + ex.message, 'error');
        }
      }
    }
  }

  /** 重挂拖拽释放在暂存箱上 → 取消重挂，改为 demote */
  async _commitDemoteFromReparent(e) {
    const drag = this._reparentDrag;
    this._reparentDrag = null;
    drag.ghostEl.remove();
    for (const t of drag.validTargets) {
      t.el.classList.remove(
        'll-drop-target', 'll-drop-target-hovered',
        'll-reorder-target', 'll-reorder-target-hovered'
      );
    }
    const stagingBody = document.getElementById('llDsBody');
    if (stagingBody) stagingBody.classList.remove('drag-over');

    const { stagingPanel, toast } = this._data || {};
    if (stagingPanel) {
      try {
        this._preserveView = true;
        await stagingPanel.demoteEntry(drag.row.gid);
      } catch (ex) {
        if (toast) toast('降级失败: ' + ex.message, 'error');
      }
    }
  }

  // ── 暂存箱拖入画布方法（复用 reparent 高亮体验）──────────────────

  /** 由 StagingPanel mousedown 调用，启动暂存箱→画布拖拽 */
  startStagingDrag(info, startX, startY) {
    const nodeType   = info.nodeType || 'process';
    // 与 reparent 相同的父级类型判定
    const parentTypes = nodeType === 'operator_process'
      ? ['station_process']
      : nodeType === 'process'
        ? ['operator_process', 'station_process']
        : ['station_process', 'operator_process', 'line_process']; // 其他类型宽泛接受

    const validTargets = [];
    this._world.querySelectorAll('.ll-station-card[data-gid], .ll-ring-card[data-gid]').forEach(targetEl => {
      const gid = targetEl.dataset.gid;
      const targetRow = this._data?.rowByGid.get(gid);
      if (!targetRow) return;

      if (parentTypes.includes(targetRow.node_type)) {
        targetEl.classList.add('ll-drop-target');
        validTargets.push({ gid, el: targetEl, kind: 'parent' });
      } else if (targetRow.node_type === nodeType) {
        targetEl.classList.add('ll-reorder-target');
        validTargets.push({ gid, el: targetEl, kind: 'sibling' });
      }
    });

    // Ghost 卡片
    const ghost = document.createElement('div');
    ghost.className = 'll-reparent-ghost';
    ghost.style.width  = '160px';
    ghost.style.height = '36px';
    ghost.innerHTML = `<div style="padding:4px 8px;font-size:11px;color:#cdd6f4;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${info.title || '暂存项'}</div>`;
    ghost.style.left = (startX - 80) + 'px';
    ghost.style.top  = (startY - 18) + 'px';
    document.body.appendChild(ghost);

    this._stagingDrag = { info, ghostEl: ghost, validTargets, hoveredGid: null, hoveredKind: null };
  }

  _onStagingDragMove(e) {
    const drag = this._stagingDrag;
    drag.ghostEl.style.left = (e.clientX - 80) + 'px';
    drag.ghostEl.style.top  = (e.clientY - 18) + 'px';

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

  async _commitStagingDrag(e) {
    const drag = this._stagingDrag;
    this._stagingDrag = null;
    if (drag.ghostEl) drag.ghostEl.remove();
    for (const t of drag.validTargets) {
      t.el.classList.remove(
        'll-drop-target', 'll-drop-target-hovered',
        'll-reorder-target', 'll-reorder-target-hovered'
      );
    }

    const targetGid = drag.hoveredGid;
    const { stagingPanel, toast } = this._data || {};
    if (!stagingPanel) return;

    // 非 demote 还原的暂存项必须有目标
    if (!targetGid && !drag.info.originalEntryGid) {
      if (toast) toast('请拖到节点卡片上挂靠', 'warn');
      return;
    }

    try {
      this._preserveView = true;

      if (drag.hoveredKind === 'sibling') {
        // 拖到同级卡片 → promote 到同级的父节点下，排在目标后面
        const siblingRow = this._data?.rowByGid.get(targetGid);
        const parentGid  = siblingRow?.parent_gid || null;
        // 计算 sort_order：目标的 sort_order + 1（promote 后 reload 会刷新布局）
        const seqNo = (siblingRow?.sort_order ?? 0) + 1;
        await stagingPanel.promoteItem(drag.info.stagingGid, parentGid, seqNo);
      } else {
        // 拖到父级卡片 → 直接 promote 为其子节点
        await stagingPanel.promoteItem(drag.info.stagingGid, targetGid, 0);
      }
    } catch (ex) {
      if (toast) toast('恢复失败: ' + ex.message, 'error');
    }
  }

  _cancelStagingDrag() {
    const drag = this._stagingDrag;
    if (!drag) return;
    if (drag.ghostEl) drag.ghostEl.remove();
    for (const t of drag.validTargets) {
      t.el.classList.remove(
        'll-drop-target', 'll-drop-target-hovered',
        'll-reorder-target', 'll-reorder-target-hovered'
      );
    }
    this._stagingDrag = null;
  }

  /** getBoundingClientRect 命中检测：找鼠标下方的卡片（排除线体框） */
  _hitTestCard(clientX, clientY) {
    const cards = this._world.querySelectorAll('.ll-station-card[data-gid], .ll-ring-card[data-gid]');
    for (const el of cards) {
      const r = el.getBoundingClientRect();
      if (clientX >= r.left && clientX <= r.right &&
          clientY >= r.top  && clientY <= r.bottom) {
        return el;
      }
    }
    return null;
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
      const lineGrantSet = this._data?.lineGrantSet || new Set();
      const lineReadOnly = !!this._data?.lineReadOnly;
      if (lineReadOnly) {
        const lineGid = this._findAncestorLineGid(drag.row.gid);
        if (lineGid && !lineGrantSet.has(lineGid)) {
          this._data?.toast?.('当前线体无编辑权限（只读）', 'warn');
          return;
        }
      }
      await _cf(`/api/bop/entries/${drag.row.gid}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ parent_gid: drag.hoveredGid }),
      });
      this._preserveView = true;
      if (this._data?.reloadData) await this._data.reloadData();
    } catch (err) {
      if (this._data?.toast) this._data.toast('移动失败: ' + err.message, 'error');
      else console.error('[LayoutMode] _commitParentChange error:', err);
    }
  }

  // 统一排位：同父 → 仅排序；跨父 → 先换挂再插到目标后面
  _findAncestorLineGid(gid) {
    let row = this._data?.rowByGid?.get(gid) || null;
    while (row) {
      if (row.node_type === 'line_process') return row.gid;
      row = row.parent_gid ? this._data?.rowByGid?.get(row.parent_gid) : null;
    }
    return null;
  }

  async _commitPositionAfter(drag) {
    const targetRow  = this._data?.rowByGid.get(drag.hoveredGid);
    if (!targetRow) return;

    const lineGrantSet = this._data?.lineGrantSet || new Set();
    const lineReadOnly = !!this._data?.lineReadOnly;
    if (lineReadOnly) {
      const lineGid = this._findAncestorLineGid(drag.row.gid);
      if (lineGid && !lineGrantSet.has(lineGid)) {
        this._data?.toast?.('当前线体无编辑权限（只读）', 'warn');
        return;
      }
    }

    const nodeType   = drag.row.node_type;
    const dragParent = drag.row.parent_gid || null;
    const destParent = targetRow.parent_gid || null;

    try {
      // Step 1：跨父时先换挂
      if (dragParent !== destParent) {
        await _cf(`/api/bop/entries/${drag.row.gid}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ parent_gid: targetRow.parent_gid }),
        });
      }

      // Step 2：在目标父级的同类子节点中计算新顺序
      // childMap 尚未刷新，跨父时手动排除拖拽行，再追加到末尾
      const destSiblings = (this._data?.childMap.get(destParent) || [])
        .filter(r => r.node_type === nodeType && r.gid !== drag.row.gid)
        .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));

      // 插到目标后面
      const targetIdx = destSiblings.findIndex(r => r.gid === drag.hoveredGid);
      destSiblings.splice(targetIdx + 1, 0, drag.row);

      // 只 PATCH 序号变化的行（拖拽行强制包含，以便在跨父时也写入新 seq_no）
      const patches = destSiblings
        .map((r, i) => ({ gid: r.gid, newSeq: i + 1, oldSeq: r.sort_order }))
        .filter(p => p.newSeq !== p.oldSeq || p.gid === drag.row.gid);

      if (patches.length) {
        await Promise.all(patches.map(p =>
          _cf(`/api/bop/entries/${p.gid}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sort_order: p.newSeq }),
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
  const base = 'lv:layout:' + (versionGid || 'default');
  try { const u = window.parent?._authUser || window.top?._authUser || window._authUser; const g = u?.gid || u?.user_gid || ''; localStorage.removeItem(g ? `${g}:${base}` : base); } catch { localStorage.removeItem(base); }
};
