'use strict';
/**
 * GridSystem — 统一网格布局系统
 *
 * 职责：
 *   - 管理 CSS 网格参数（列数、行高、间距）
 *   - 控制网格叠层可见性（与吸附解耦：不可见时吸附仍然有效）
 *   - 提供像素↔格子单位互转和吸附计算
 *   - 监听容器尺寸变化，自动 reflow
 *
 * 用法：
 *   const gs = new GridSystem(containerEl, { cols: 12, rowHeight: 80 });
 *   gs.setOverlayVisible(true);   // 编辑模式显示网格点
 *   gs.setOptions({ cols: 6 });   // 运行时修改列数
 */
class GridSystem {
  constructor(containerEl, options = {}) {
    this._el = containerEl;
    this._opts = {
      cols:           12,
      rowHeight:      80,
      gap:            12,
      minCols:        2,
      minRows:        2,
      overlayVisible: false,
      overlayOpacity: 0.18,   // 默认极淡，不抢视觉焦点
      overlayColor:   '#888888',
      snapEnabled:    true,
      ...options,
    };

    this._overlayEl = null;
    this._ro        = null;
    this._colWidth  = 0;  // 每列实际像素宽（动态计算）

    this._init();
  }

  // ── 初始化 ─────────────────────────────────────────────────────────────────
  _init() {
    // 在容器上挂 gs-container 类，注入 CSS 变量
    this._el.classList.add('gs-container');
    this._applyVars();

    // 先算列宽（overlay 渲染依赖像素列宽）
    this._computeColWidth();

    // 创建叠层 div，放在最前面（z-index:0，卡片在上）
    this._overlayEl = document.createElement('div');
    this._overlayEl.className = 'gs-overlay';
    this._el.prepend(this._overlayEl);
    this._updateOverlay();

    // 容器尺寸变化时自动 reflow
    this._ro = new ResizeObserver(() => this._computeColWidth());
    this._ro.observe(this._el);
  }

  // ── CSS 变量写入 ───────────────────────────────────────────────────────────
  _applyVars() {
    const o = this._opts;
    this._el.style.setProperty('--gs-cols',       String(o.cols));
    this._el.style.setProperty('--gs-row-height', o.rowHeight + 'px');
    this._el.style.setProperty('--gs-gap',        o.gap + 'px');
  }

  // ── 列宽计算（总宽度扣除间距后平均分配）─────────────────────────────────
  _computeColWidth() {
    const totalW = this._el.clientWidth;
    const { cols, gap } = this._opts;
    this._colWidth = (totalW - gap * (cols - 1)) / cols;
    // overlay 已创建时才刷新（_init 首次调用时 overlay 还未创建）
    if (this._overlayEl) this._updateOverlay();
  }

  // ── 叠层渲染 ──────────────────────────────────────────────────────────────
  _updateOverlay() {
    const { overlayVisible, overlayOpacity, overlayColor, gap, rowHeight } = this._opts;
    const ov = this._overlayEl;
    if (!ov) return;

    const colW = this._colWidth;
    if (colW > 0) {
      const r = parseInt(overlayColor.slice(1, 3), 16);
      const g = parseInt(overlayColor.slice(3, 5), 16);
      const b = parseInt(overlayColor.slice(5, 7), 16);
      const dotColor = `rgba(${r},${g},${b},1)`;
      const dotR     = Math.max(1.5, Math.min(3, gap / 4)); // 点半径随间距缩放

      const tileW = colW + gap;
      const tileH = rowHeight + gap;
      // 让点落在间隙正中央：
      // background-position = (colW/2, rowHeight/2)
      // 则每个 tile 中心（即点位）= (colW/2 + tileW/2, rowHeight/2 + tileH/2)
      //                           = (colW + gap/2, rowHeight + gap/2)  ← 间隙中心 ✓
      ov.style.backgroundImage    = `radial-gradient(circle, ${dotColor} ${dotR}px, transparent ${dotR}px)`;
      ov.style.backgroundSize     = `${tileW}px ${tileH}px`;
      ov.style.backgroundPosition = `${colW / 2}px ${rowHeight / 2}px`;
    }

    ov.style.opacity = overlayVisible ? String(overlayOpacity) : '0';
  }

  // ── 公开 API ──────────────────────────────────────────────────────────────

  /**
   * 动态更新参数，立即生效
   * @param {Partial<GridOptions>} partial
   */
  setOptions(partial) {
    Object.assign(this._opts, partial);
    this._applyVars();
    this._updateOverlay();
    this._computeColWidth();
  }

  /** 控制叠层可见性（不影响吸附）*/
  setOverlayVisible(bool) {
    this._opts.overlayVisible = bool;
    this._updateOverlay();
  }

  /** 动态调整叠层透明度 0~1 */
  setOverlayOpacity(val) {
    this._opts.overlayOpacity = Math.max(0, Math.min(1, Number(val)));
    this._updateOverlay();
  }

  /** 动态调整叠层颜色（hex，如 '#aabbcc'）*/
  setOverlayColor(hex) {
    this._opts.overlayColor = hex;
    this._updateOverlay();
  }

  /** 启用/禁用吸附（禁用后 snapResize 返回像素级结果）*/
  setSnapEnabled(bool) {
    this._opts.snapEnabled = !!bool;
  }

  // ── 像素 ↔ 格子互转 ───────────────────────────────────────────────────────

  pxToGridCols(px) {
    const { gap, minCols, cols } = this._opts;
    if (this._colWidth <= 0) return minCols;
    const n = Math.round((px + gap) / (this._colWidth + gap));
    return Math.max(minCols, Math.min(cols, n));
  }

  pxToGridRows(px) {
    const { rowHeight, gap, minRows } = this._opts;
    const n = Math.round((px + gap) / (rowHeight + gap));
    return Math.max(minRows, n);
  }

  gridColsToPx(cols) {
    const { gap } = this._opts;
    return cols * this._colWidth + (cols - 1) * gap;
  }

  gridRowsToPx(rows) {
    const { rowHeight, gap } = this._opts;
    return rows * rowHeight + (rows - 1) * gap;
  }

  /**
   * 给定当前 span 和拖拽增量，返回新的 span（已吸附）
   */
  snapResize(currentColSpan, currentRowSpan, deltaX, deltaY) {
    const { minCols, minRows, cols, snapEnabled } = this._opts;

    if (!snapEnabled) {
      // 像素级自由调整
      const cw = this._colWidth || 80;
      const rh = this._opts.rowHeight || 80;
      return {
        colSpan: Math.max(minCols, Math.min(cols, currentColSpan + Math.round(deltaX / cw))),
        rowSpan: Math.max(minRows, currentRowSpan + Math.round(deltaY / rh)),
      };
    }

    const currentW = this.gridColsToPx(currentColSpan);
    const currentH = this.gridRowsToPx(currentRowSpan);
    return {
      colSpan: this.pxToGridCols(currentW + deltaX),
      rowSpan: this.pxToGridRows(currentH + deltaY),
    };
  }

  /** 手动触发重算（通常由 ResizeObserver 自动调用）*/
  reflow() {
    this._computeColWidth();
    this._applyVars();
    this._updateOverlay();
  }

  /**
   * 返回 grid cell 的像素矩形（相对于容器左上角，1-indexed）
   * @returns {{ x, y, w, h }}
   */
  cellPixelRect(colStart, rowStart, colSpan, rowSpan) {
    const { gap, rowHeight } = this._opts;
    return {
      x: (colStart - 1) * (this._colWidth + gap),
      y: (rowStart  - 1) * (rowHeight + gap),
      w: this.gridColsToPx(colSpan),
      h: this.gridRowsToPx(rowSpan),
    };
  }

  /**
   * 根据屏幕坐标返回对应的 grid 列/行（1-indexed）
   * @param {number} clientX
   * @param {number} clientY
   * @returns {{ col: number, row: number }}
   */
  hitTest(clientX, clientY) {
    this._computeColWidth();
    const rect  = this._el.getBoundingClientRect();
    const x     = Math.max(0, clientX - rect.left);
    const y     = Math.max(0, clientY - rect.top);
    const { cols, rowHeight, gap } = this._opts;
    const cellW = this._colWidth + gap;
    const cellH = rowHeight + gap;
    const col   = Math.max(1, Math.min(cols, Math.floor(x / cellW) + 1));
    const row   = Math.max(1, Math.floor(y / cellH) + 1);
    return { col, row };
  }

  // ── 序列化 ────────────────────────────────────────────────────────────────

  toConfig() {
    const { cols, rowHeight, gap, overlayVisible, overlayOpacity, overlayColor, snapEnabled } = this._opts;
    return { cols, rowHeight, gap, overlayVisible, overlayOpacity, overlayColor, snapEnabled };
  }

  fromConfig(c) {
    this.setOptions(c);
  }

  // ── 销毁 ──────────────────────────────────────────────────────────────────

  destroy() {
    this._ro?.disconnect();
    this._overlayEl?.remove();
    this._el.classList.remove('gs-container');
    this._el.style.removeProperty('--gs-cols');
    this._el.style.removeProperty('--gs-row-height');
    this._el.style.removeProperty('--gs-gap');
  }
}

window.GridSystem = GridSystem;

