'use strict';
/**
 * CardFrame — 统一卡片容器框架
 *
 * 职责：
 *   - 管理卡片在 CSS Grid 中的位置（col_start/row_start）和尺寸（col_span/row_span）
 *   - 提供右下角 resize 手柄（编辑模式），吸附到 GridSystem 网格
 *   - 提供右上角"弹出为页签"按钮（使用模式）
 *   - 内容区 (.cf-content) 由外部填充，CardFrame 不关心内容
 *
 * 用法：
 *   const cf = new CardFrame({
 *     id: widget.id,
 *     colSpan: 4, rowSpan: 5,
 *     colStart: 1, rowStart: 1,   // null = 自动流
 *     grid: _gridSystem,
 *     onResize: (col, row) => saveWidgetSize(col, row),
 *     onPopOut: () => openAsTab(widget),
 *     onDelete: () => deleteWidget(widget.id),
 *   });
 *   cf.mount(document.getElementById('wbWidgetGrid'));
 *   cf.contentEl.innerHTML = '...自定义 HTML...';
 *   cf.setEditMode(true);   // 显示 resize 手柄
 */
class CardFrame {
  constructor(options = {}) {
    this._opts = {
      id:          null,
      colSpan:     3,
      rowSpan:     3,
      minColSpan:  2,
      minRowSpan:  2,
      colStart:    null,   // null = CSS Grid 自动流
      rowStart:    null,
      grid:        null,   // GridSystem 实例
      onResize:    null,   // (colSpan, rowSpan) => void
      onPopOut:    null,   // () => void
      onDelete:    null,   // () => void
      ...options,
    };

    this._el        = null;
    this._contentEl = null;
    this._editMode  = false;
    this._resizing  = false;

    this._build();
  }

  // ── DOM 构建 ───────────────────────────────────────────────────────────────
  _build() {
    const { id, colSpan, rowSpan, colStart, rowStart } = this._opts;

    // 卡片根元素
    const el = document.createElement('div');
    el.className      = 'cf-card';
    el.dataset.cfId   = id || '';
    el.style.gridColumn = colStart ? `${colStart} / span ${colSpan}` : `span ${colSpan}`;
    el.style.gridRow    = rowStart ? `${rowStart} / span ${rowSpan}` : `span ${rowSpan}`;

    // 内容区（由外部填充）
    const contentEl = document.createElement('div');
    contentEl.className = 'cf-content';
    el.appendChild(contentEl);

    // 弹出为页签按钮（右上角，使用模式可见）
    const popoutBtn = document.createElement('button');
    popoutBtn.className = 'cf-popout-btn';
    popoutBtn.title     = '弹出为页签';
    popoutBtn.innerHTML = `<svg viewBox="0 0 16 16" fill="none"
      stroke="currentColor" stroke-width="1.8"
      stroke-linecap="round" stroke-linejoin="round"
      width="11" height="11">
      <path d="M7 3H3a1 1 0 00-1 1v9a1 1 0 001 1h9a1 1 0 001-1V9"/>
      <polyline points="10 2 14 2 14 6"/>
      <line x1="14" y1="2" x2="8" y2="8"/>
    </svg>`;
    popoutBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      this._opts.onPopOut?.();
    });
    el.appendChild(popoutBtn);

    // Resize 手柄（右下角，编辑模式可见）
    const resizeHandle = document.createElement('div');
    resizeHandle.className = 'cf-resize-handle';
    resizeHandle.title     = '拖拽调整大小';
    resizeHandle.innerHTML = `<svg viewBox="0 0 10 10" fill="none"
      stroke="currentColor" stroke-width="1.8"
      stroke-linecap="round" width="10" height="10">
      <line x1="3" y1="9" x2="9" y2="3"/>
      <line x1="6" y1="9" x2="9" y2="6"/>
    </svg>`;
    this._attachResizeEvents(resizeHandle);
    el.appendChild(resizeHandle);

    this._el        = el;
    this._contentEl = contentEl;
  }

  // ── Resize 事件绑定 ────────────────────────────────────────────────────────
  _attachResizeEvents(handle) {
    let startX, startY, startCol, startRow, startColStart, startRowStart;

    const onMouseMove = (e) => {
      if (!this._resizing) return;
      const deltaX = e.clientX - startX;
      const deltaY = e.clientY - startY;
      const grid   = this._opts.grid;

      let newCol, newRow;
      if (grid) {
        ({ colSpan: newCol, rowSpan: newRow } =
          grid.snapResize(startCol, startRow, deltaX, deltaY));
      } else {
        newCol = Math.max(this._opts.minColSpan, startCol + Math.round(deltaX / 80));
        newRow = Math.max(this._opts.minRowSpan, startRow + Math.round(deltaY / 80));
      }
      // 保留起始坐标（若有）
      this._el.style.gridColumn = startColStart ? `${startColStart} / span ${newCol}` : `span ${newCol}`;
      this._el.style.gridRow    = startRowStart ? `${startRowStart} / span ${newRow}` : `span ${newRow}`;
    };

    const onMouseUp = () => {
      if (!this._resizing) return;
      this._resizing = false;
      this._el.classList.remove('cf-resizing');
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup',   onMouseUp);

      const colSpan = this._currentColSpan();
      const rowSpan = this._currentRowSpan();
      this._opts.onResize?.(colSpan, rowSpan);
    };

    handle.addEventListener('mousedown', (e) => {
      e.preventDefault();
      e.stopPropagation();
      this._resizing   = true;
      startX           = e.clientX;
      startY           = e.clientY;
      startCol         = this._currentColSpan();
      startRow         = this._currentRowSpan();
      startColStart    = this._currentColStart();  // 保存起始列
      startRowStart    = this._currentRowStart();  // 保存起始行
      this._el.classList.add('cf-resizing');
      document.addEventListener('mousemove', onMouseMove);
      document.addEventListener('mouseup',   onMouseUp);
    });
  }

  // ── 内部辅助 ──────────────────────────────────────────────────────────────

  /** 从 gridColumn 样式解析 colSpan（兼容 "span N" 和 "X / span N"）*/
  _currentColSpan() {
    const v = this._el.style.gridColumn;
    const m = v.match(/span\s+(\d+)/);
    return m ? parseInt(m[1]) : this._opts.colSpan;
  }

  /** 从 gridRow 样式解析 rowSpan */
  _currentRowSpan() {
    const v = this._el.style.gridRow;
    const m = v.match(/span\s+(\d+)/);
    return m ? parseInt(m[1]) : this._opts.rowSpan;
  }

  /** 从 gridColumn 样式解析 colStart（返回 null 表示 auto）*/
  _currentColStart() {
    const v = this._el.style.gridColumn;
    const m = v.match(/^(\d+)\s*\//);
    return m ? parseInt(m[1]) : null;
  }

  /** 从 gridRow 样式解析 rowStart */
  _currentRowStart() {
    const v = this._el.style.gridRow;
    const m = v.match(/^(\d+)\s*\//);
    return m ? parseInt(m[1]) : null;
  }

  // ── 公开 API ──────────────────────────────────────────────────────────────

  /** 挂载到父容器 */
  mount(parentEl) {
    parentEl.appendChild(this._el);
  }

  /** 从 DOM 移除 */
  unmount() {
    this._el?.remove();
  }

  /** 卡片根 DOM 元素 */
  get el() { return this._el; }

  /** 内容区 DOM 元素（由外部填充） */
  get contentEl() { return this._contentEl; }

  /** 切换编辑模式（显示/隐藏 resize 手柄，隐藏/显示弹出按钮） */
  setEditMode(bool) {
    this._editMode = bool;
    this._el.classList.toggle('cf-edit-mode', bool);
  }

  /** 设置 colSpan（保留现有 colStart）*/
  setColSpan(n) {
    const start = this._currentColStart();
    this._el.style.gridColumn = start ? `${start} / span ${n}` : `span ${n}`;
  }

  /** 设置 rowSpan（保留现有 rowStart）*/
  setRowSpan(n) {
    const start = this._currentRowStart();
    this._el.style.gridRow = start ? `${start} / span ${n}` : `span ${n}`;
  }

  /** 设置显式位置（colStart, rowStart），保留当前 span */
  setPosition(colStart, rowStart) {
    const cs = this._currentColSpan();
    const rs = this._currentRowSpan();
    this._el.style.gridColumn = colStart ? `${colStart} / span ${cs}` : `span ${cs}`;
    this._el.style.gridRow    = rowStart ? `${rowStart} / span ${rs}` : `span ${rs}`;
  }

  /** 序列化当前 span 和位置（用于持久化） */
  toConfig() {
    return {
      col_span:  this._currentColSpan(),
      row_span:  this._currentRowSpan(),
      col_start: this._currentColStart(),
      row_start: this._currentRowStart(),
    };
  }
}

window.CardFrame = CardFrame;

