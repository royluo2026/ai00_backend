/**
 * GanttView — 通用甘特图组件
 *
 * 用法：
 *   const gantt = new GanttView({
 *     containerEl: document.getElementById('ganttContainer'),
 *     rows: [{
 *       id: 'xxx',
 *       label: '任务标题',
 *       color: '#89b4fa',          // 标签圆点颜色
 *       plan_start: '2026-05-01',  // 可空
 *       plan_end:   '2026-05-15',  // 可空
 *       actual_start: '2026-05-02',
 *       actual_end:   '2026-05-18',
 *     }],
 *   });
 *   gantt.render();
 *   gantt.setRows(newRows);  // 更新数据
 */
'use strict';

class GanttView {
  /**
   * @param {Object} opts
   * @param {HTMLElement} opts.containerEl
   * @param {Array}       opts.rows
   */
  constructor(opts) {
    this._el   = opts.containerEl;
    this._rows = opts.rows || [];
    this._zoom = 'week';   // 'day' | 'week' | 'month'
    this._startDate = null; // Date — 当前视口起点
    this._tip  = null;      // tooltip element
    this._resizeObs = null;
    this._rendered = false;

    // 列宽（每个时间单元格的像素宽度）
    this._COL_W = { day: 36, week: 48, month: 64 };

    // 今天
    this._today = new Date();
    this._today.setHours(0, 0, 0, 0);
  }

  // ── 公开 API ──────────────────────────────────────

  setRows(rows) {
    this._rows = rows || [];
    if (this._rendered) this._redraw();
  }

  render() {
    this._rendered = true;
    this._buildSkeleton();
    this._initStartDate();
    this._redraw();

    // 监听容器尺寸变化，自动重绘
    if (window.ResizeObserver) {
      this._resizeObs = new ResizeObserver(() => this._redraw());
      this._resizeObs.observe(this._el);
    }
  }

  destroy() {
    this._resizeObs?.disconnect();
  }

  // ── 私有：骨架构建 ────────────────────────────────

  _buildSkeleton() {
    this._el.innerHTML = '';
    this._el.classList.add('gantt-root');

    // 工具栏
    const tb = document.createElement('div');
    tb.className = 'gantt-toolbar';
    tb.innerHTML = `
      <span class="gantt-toolbar-label">视图</span>
      <button class="gantt-zoom-btn${this._zoom === 'day' ? ' active' : ''}"   data-zoom="day">日</button>
      <button class="gantt-zoom-btn${this._zoom === 'week' ? ' active' : ''}"  data-zoom="week">周</button>
      <button class="gantt-zoom-btn${this._zoom === 'month' ? ' active' : ''}" data-zoom="month">月</button>
      <button class="gantt-nav-btn" id="_ganttPrev">‹</button>
      <button class="gantt-nav-btn" id="_ganttNext">›</button>
      <button class="gantt-today-btn" id="_ganttToday">今天</button>
      <span class="gantt-date-label" id="_ganttDateLabel"></span>
      <span class="gantt-legend">
        <span class="gantt-legend-item"><span class="gantt-legend-swatch" style="background:#89b4fa;opacity:.7"></span>计划</span>
        <span class="gantt-legend-item"><span class="gantt-legend-swatch" style="background:#a6e3a1"></span>实际</span>
      </span>
    `;
    this._el.appendChild(tb);
    tb.querySelectorAll('.gantt-zoom-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        this._zoom = btn.dataset.zoom;
        tb.querySelectorAll('.gantt-zoom-btn').forEach(b => b.classList.toggle('active', b.dataset.zoom === this._zoom));
        this._redraw();
      });
    });
    tb.querySelector('#_ganttPrev').addEventListener('click',  () => this._navigate(-1));
    tb.querySelector('#_ganttNext').addEventListener('click',  () => this._navigate(1));
    tb.querySelector('#_ganttToday').addEventListener('click', () => { this._initStartDate(); this._redraw(); });

    // 主体
    const body = document.createElement('div');
    body.className = 'gantt-body';

    // 左侧标签
    const labelsWrap = document.createElement('div');
    labelsWrap.className = 'gantt-labels';
    labelsWrap.innerHTML = `<div class="gantt-labels-header">任务</div><div class="gantt-labels-rows" id="_ganttLabels"></div>`;

    // 右侧图表
    const chartWrap = document.createElement('div');
    chartWrap.className = 'gantt-chart';
    chartWrap.innerHTML = `<div class="gantt-chart-scroll" id="_ganttScroll"><div class="gantt-timeline-header" id="_ganttHeader"></div><div class="gantt-rows-area" id="_ganttRows"></div></div>`;

    body.appendChild(labelsWrap);
    body.appendChild(chartWrap);
    this._el.appendChild(body);

    this._domLabels = labelsWrap.querySelector('#_ganttLabels');
    this._domHeader = chartWrap.querySelector('#_ganttHeader');
    this._domRows   = chartWrap.querySelector('#_ganttRows');
    this._domScroll = chartWrap.querySelector('#_ganttScroll');
    this._domLabel  = tb.querySelector('#_ganttDateLabel');

    // 同步滚动：标签行和图表行竖向一致
    this._domRows.addEventListener('scroll', () => {
      this._domLabels.scrollTop = this._domRows.scrollTop;
    }, { passive: true });
  }

  // ── 私有：日期计算 ────────────────────────────────

  _initStartDate() {
    // 让今天大约在视口左侧 1/4 处
    const cols = this._visibleCols();
    const offset = Math.floor(cols / 4);
    const d = new Date(this._today);
    this._shiftDate(d, -offset);
    this._startDate = d;
  }

  _visibleCols() {
    const w = (this._domScroll?.offsetWidth || 600) - 0;
    return Math.max(1, Math.floor(w / this._colW()));
  }

  _colW() { return this._COL_W[this._zoom]; }

  /** offset: +/- 步 */
  _navigate(dir) {
    const d = new Date(this._startDate);
    const steps = Math.max(1, Math.floor(this._visibleCols() / 2));
    this._shiftDate(d, dir * steps);
    this._startDate = d;
    this._redraw();
  }

  _shiftDate(d, n) {
    if (this._zoom === 'day') {
      d.setDate(d.getDate() + n);
    } else if (this._zoom === 'week') {
      d.setDate(d.getDate() + n * 7);
    } else {
      d.setMonth(d.getMonth() + n);
    }
  }

  _colStartDate(index) {
    const d = new Date(this._startDate);
    this._shiftDate(d, index);
    return d;
  }

  /** 总共渲染多少列（足够填满容器 + buffer）*/
  _totalCols() {
    const w = (this._domScroll?.offsetWidth || 600);
    return Math.ceil(w / this._colW()) + 2;
  }

  /** 将日期字符串映射到列偏移量（像素） */
  _dateToX(dateStr) {
    if (!dateStr) return null;
    const d = _parseDate(dateStr);
    if (!d) return null;
    const msPerCol = this._msPerUnit();
    const dx = (d - this._startDate) / msPerCol;
    return dx * this._colW();
  }

  _msPerUnit() {
    if (this._zoom === 'day')   return 86400000;
    if (this._zoom === 'week')  return 86400000 * 7;
    return 86400000 * 30.4375; // average month
  }

  // ── 私有：渲染 ────────────────────────────────────

  _redraw() {
    if (!this._domHeader) return;
    const cols  = this._totalCols();
    const colW  = this._colW();
    const totalW = cols * colW;

    // ─ 表头 ─
    this._domHeader.style.width = totalW + 'px';
    let headerHtml = '';
    for (let i = 0; i < cols; i++) {
      const d = this._colStartDate(i);
      const label = this._colLabel(d, i);
      const isToday = this._isTodayCol(d);
      headerHtml += `<div class="gantt-header-cell${isToday ? ' today-col' : ''}" style="left:${i * colW}px;width:${colW}px;">${label}</div>`;
    }
    this._domHeader.innerHTML = headerHtml;

    // ─ 行区域 ─
    const rowH = 36;
    const rowCount = this._rows.length;
    this._domRows.style.width  = totalW + 'px';
    this._domRows.style.height = (rowH * rowCount) + 'px';
    this._domLabels.style.height = (rowH * rowCount) + 'px';

    if (!rowCount) {
      this._domRows.innerHTML   = '<div class="gantt-empty">暂无任务数据</div>';
      this._domLabels.innerHTML = '';
      this._domLabel.textContent = '';
      return;
    }

    // 网格线 + 今日线
    let gridHtml = '';
    for (let i = 0; i < cols; i++) {
      const d = this._colStartDate(i);
      const isToday = this._isTodayCol(d);
      gridHtml += `<div class="gantt-grid-line${isToday ? ' today-line' : ''}" style="left:${i * colW}px"></div>`;
    }

    // 行背景
    for (let r = 0; r < rowCount; r++) {
      gridHtml += `<div class="gantt-row-bg${r % 2 === 1 ? ' alt' : ''}" style="top:${r * rowH}px"></div>`;
    }

    // 甘特条
    for (let r = 0; r < rowCount; r++) {
      const row = this._rows[r];
      const top = r * rowH;

      const planX1 = this._dateToX(row.plan_start);
      const planX2 = this._dateToX(row.plan_end);
      if (planX1 !== null && planX2 !== null) {
        const w = Math.max(4, planX2 - planX1);
        gridHtml += `<div class="gantt-bar gantt-bar-plan" style="left:${planX1}px;width:${w}px;top:${top + 7}px;"
          data-rid="${_esc(row.id)}" data-type="plan"
          title="${_esc(row.label)}: 计划 ${_esc(row.plan_start)} ~ ${_esc(row.plan_end)}"></div>`;
      }

      const actX1 = this._dateToX(row.actual_start);
      const actX2 = this._dateToX(row.actual_end);
      if (actX1 !== null && actX2 !== null) {
        const w = Math.max(4, actX2 - actX1);
        const overrun = row.actual_end > (row.plan_end || '') ? ' overrun' : '';
        gridHtml += `<div class="gantt-bar gantt-bar-actual${overrun}" style="left:${actX1}px;width:${w}px;top:${top + 17}px;"
          data-rid="${_esc(row.id)}" data-type="actual"
          title="${_esc(row.label)}: 实际 ${_esc(row.actual_start)} ~ ${_esc(row.actual_end)}"></div>`;
      }
    }

    this._domRows.innerHTML = gridHtml;

    // 标签列
    let labelsHtml = '';
    for (const row of this._rows) {
      labelsHtml += `<div class="gantt-label-row">
        <span class="gantt-label-dot" style="background:${_esc(row.color || '#89b4fa')}"></span>
        <span class="gantt-label-text" title="${_esc(row.label)}">${_esc(row.label)}</span>
      </div>`;
    }
    this._domLabels.innerHTML = labelsHtml;

    // 日期标签
    const start = this._colStartDate(0);
    const end   = this._colStartDate(cols - 1);
    this._domLabel.textContent = _fmtDate(start) + ' – ' + _fmtDate(end);

    // 绑定 tooltip
    this._domRows.querySelectorAll('.gantt-bar').forEach(bar => {
      bar.addEventListener('mouseenter', e => this._showTip(e));
      bar.addEventListener('mouseleave', () => this._hideTip());
    });
  }

  _colLabel(d, i) {
    if (this._zoom === 'day') {
      return _pad(d.getMonth() + 1) + '/' + _pad(d.getDate());
    } else if (this._zoom === 'week') {
      // 仅在每月第一周或首列显示月份
      if (i === 0 || d.getDate() <= 7) {
        return (d.getMonth() + 1) + '月';
      }
      return 'W' + _isoWeek(d);
    } else {
      return (d.getFullYear() % 100) + '/' + _pad(d.getMonth() + 1);
    }
  }

  _isTodayCol(d) {
    if (this._zoom === 'day') {
      return d.toDateString() === this._today.toDateString();
    } else if (this._zoom === 'week') {
      const w1 = _isoWeek(d);
      const w2 = _isoWeek(this._today);
      return w1 === w2 && d.getFullYear() === this._today.getFullYear();
    } else {
      return d.getMonth() === this._today.getMonth() && d.getFullYear() === this._today.getFullYear();
    }
  }

  _showTip(e) {
    const title = e.currentTarget.getAttribute('title');
    if (!title) return;
    if (!this._tip) {
      this._tip = document.createElement('div');
      this._tip.className = 'gantt-bar-tip';
      this._domRows.appendChild(this._tip);
    }
    this._tip.textContent = title;
    this._tip.style.display = 'block';
    const bar = e.currentTarget;
    const barLeft = parseInt(bar.style.left);
    const barW    = parseInt(bar.style.width);
    this._tip.style.left = (barLeft + barW / 2) + 'px';
    this._tip.style.top  = parseInt(bar.style.top) + 'px';
  }

  _hideTip() {
    if (this._tip) this._tip.style.display = 'none';
  }
}

// ── 辅助函数 ──────────────────────────────────────

function _parseDate(s) {
  if (!s) return null;
  const d = new Date(s + 'T00:00:00');
  return isNaN(d) ? null : d;
}

function _fmtDate(d) {
  return d.getFullYear() + '/' + _pad(d.getMonth() + 1) + '/' + _pad(d.getDate());
}

function _pad(n) { return String(n).padStart(2, '0'); }

function _isoWeek(d) {
  const jan4 = new Date(d.getFullYear(), 0, 4);
  const startOfWeek1 = new Date(jan4);
  startOfWeek1.setDate(jan4.getDate() - ((jan4.getDay() + 6) % 7));
  const diff = d - startOfWeek1;
  return Math.ceil(diff / 604800000) + 1;
}

function _esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

window.GanttView = GanttView;

