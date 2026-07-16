'use strict';
/**
 * GridEditor — 类飞书多维表格编辑组件
 *
 * 10 项核心能力：
 *  1. 表格渲染（行号 + 数据列，支持 cellRenderer）
 *  2. 单元格选区（click 单选，shift+click 扩展，keyboard 导航）
 *  3. 内联编辑（双击 / Enter / 直接打字；Tab→右，Enter→下，Esc→取消）
 *  4. Ctrl+C 复制（TSV）
 *  5. 粘贴（TSV 解析，不足行自动追加）
 *  6. 键盘导航（Arrow / Tab；Delete / Backspace 清空）
 *  7. 行拖拽（HTML5 drag API）
 *  8. 列拖拽（thead 委托）
 *  9. 列宽调整（resize handle）
 * 10. 右键菜单（上/下插行，删除行，清空选区）
 */
class GridEditor {
  /**
   * @param {object} opts
   * @param {HTMLElement}   opts.containerEl      挂载容器
   * @param {Array}         opts.columns          [{ key, label, type, width, editable? }]
   * @param {Array}         opts.rows             初始行数据
   * @param {function}      [opts.onRowsChange]   行变更回调 (newRows) => void
   * @param {function}      [opts.onColsChange]   列变更回调 (newCols) => void
   * @param {boolean}       [opts.readOnly]       全局只读
   * @param {object}        [opts.cellRenderer]   { [colKey]: (val, row) => innerHTMLString }
   * @param {boolean}       [opts.draggableRows]  是否允许拖行（默认 true）
   * @param {function}      [opts.rowClass]       (row) => className string，用于 per-row 样式
   */
  constructor(opts) {
    this._el       = opts.containerEl;
    this._cols     = (opts.columns || []).map(c => ({ ...c }));
    this._rows     = (opts.rows || []).map(r => ({ ...r }));
    this._onRowsChange = opts.onRowsChange || null;
    this._onColsChange = opts.onColsChange || null;
    this._readOnly  = opts.readOnly || false;
    this._renderers = opts.cellRenderer || {};
    this._draggableRows = opts.draggableRows !== false;
    this._rowClass  = opts.rowClass || null;
    // 自定义右键菜单项：(row) => [{label, action, icon?, danger?}]
    this._extraCtxItems  = opts.extraContextItems || null;
    // 自定义右键动作回调：(action, row) => void
    this._onContextAction = opts.onContextAction || null;

    // ── 新增选项（向后兼容，默认关闭）────────────────────────────────────────
    /** 在列标题显示字段类型小图标（T / # / ≡ / ⊡ / ✓ / ⊘）*/
    this._fieldTypeIcons = opts.fieldTypeIcons || false;
    /** 在表头下方显示统计行（COUNT/SUM/AVG）*/
    this._showStats = opts.showStats || false;
    /** 覆盖每列统计类型：{ colKey: 'count'|'sum'|'avg'|'none' } */
    this._statsRow  = opts.statsRow  || null;
    /** 将 _actions 列移到序号列后面（而非末尾）*/
    this._actionColFirst = opts.actionColFirst || false;
    /** 行点击回调（非编辑状态、非按钮点击）: (row) => void */
    this._onRowClick = opts.onRowClick || null;
    /** 列表头右键动作回调：(action:'hide'|'filter'|'sort'|'group', colKey) => void */
    this._onColHeaderAction = opts.onColHeaderAction || null;
    /** 删除行拦截回调 (row) => void；若提供则完全替代默认 splice 行为 */
    this._onDeleteRow = opts.onDeleteRow || null;
    // ─────────────────────────────────────────────────────────────────────────

    // 选区状态
    this._anchor = null;  // { ri, ci }
    this._range  = null;  // { r1, c1, r2, c2 }（列索引不含行号列，即实际数据列索引）

    // 拖拽状态
    this._dragRowIdx = null;
    this._dragColIdx = null;
    this._resizingCol = null;
    this._resizeStartX = 0;
    this._resizeStartW = 0;

    // 编辑状态
    this._editCell = null;    // { ri, ci, td, input }
    this._editCommitTimer = null;

    // DOM
    this._wrapEl  = null;
    this._tableEl = null;
    this._tbodyEl = null;
    this._theadEl = null;
    this._statsRowEl = null;  // 统计行 tr

    // 右键菜单
    this._ctxMenu = null;
    this._ctxTargetRow = null;

    // actionColFirst: 移动 _actions 到首列
    if (this._actionColFirst) {
      const actIdx = this._cols.findIndex(c => c.key === '_actions');
      if (actIdx > 0) {
        const [actCol] = this._cols.splice(actIdx, 1);
        this._cols.unshift(actCol);
      }
    }

    this._build();
  }

  // ─── 公开 API ───────────────────────────────────────────────────────────────

  setRows(rows) {
    // 有 input 正在编辑时先提交，避免 _renderBody 强制销毁 input
    if (this._editCell) this._commitEdit(true);
    this._rows = (rows || []).map(r => ({ ...r }));
    this._clearSelection();
    this._renderBody();
    if (this._showStats) this._renderStatsRow();
  }

  setColumns(cols) {
    if (this._editCell) this._commitEdit(true);
    this._cols = (cols || []).map(c => ({ ...c }));
    // Re-apply actionColFirst if set
    if (this._actionColFirst) {
      const actIdx = this._cols.findIndex(c => c.key === '_actions');
      if (actIdx > 0) {
        const [actCol] = this._cols.splice(actIdx, 1);
        this._cols.unshift(actCol);
      }
    }
    this._clearSelection();
    this._renderHead();
    this._renderBody();
  }

  getRows() {
    return this._rows.map(r => ({ ...r }));
  }

  /** 返回尚未保存到服务器的新行（无 gid 字段），供 render() 在刷新时保留它们 */
  getUnsavedRows() {
    return this._rows.filter(r => !r.gid).map(r => ({ ...r }));
  }

  destroy() {
    this._removeDocListeners();
    this._destroyCtxMenu();
    this._el.innerHTML = '';
  }

  // ─── 构建 DOM ───────────────────────────────────────────────────────────────

  _build() {
    // 容器
    this._el.classList.add('ge-container');

    // 滚动包裹
    this._wrapEl = document.createElement('div');
    this._wrapEl.className = 'ge-table-wrap';
    this._el.appendChild(this._wrapEl);

    // 表格
    this._tableEl = document.createElement('table');
    this._tableEl.className = 'ge-table';

    this._theadEl = document.createElement('thead');
    this._theadEl.className = 'ge-thead';
    this._tableEl.appendChild(this._theadEl);

    this._tbodyEl = document.createElement('tbody');
    this._tableEl.appendChild(this._tbodyEl);

    this._wrapEl.appendChild(this._tableEl);

    // 添加行按钮
    if (!this._readOnly) {
      const addBtn = document.createElement('button');
      addBtn.className = 'ge-add-row-btn';
      addBtn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg> 添加行`;
      addBtn.addEventListener('click', () => this._addRow());
      this._el.appendChild(addBtn);
    }

    this._renderHead();
    this._renderBody();
    this._bindEvents();
  }

  // ─── 渲染表头 ────────────────────────────────────────────────────────────────

  _renderHead() {
    this._theadEl.innerHTML = '';
    this._statsRowEl = null;
    const tr = document.createElement('tr');

    // 行号列
    const thNum = document.createElement('th');
    thNum.className = 'ge-th ge-th-num';
    tr.appendChild(thNum);

    // 字段类型图标表
    const _FIELD_ICON = { text: 'T', number: '#', enum: '≡', date: '⊡', boolean: '✓', readonly: '⊘' };
    const _FIELD_CLS  = { text: 'ge-fi-text', number: 'ge-fi-num', enum: 'ge-fi-enum', date: 'ge-fi-date', boolean: 'ge-fi-bool', readonly: 'ge-fi-ro' };

    // 数据列
    this._cols.forEach((col, ci) => {
      const th = document.createElement('th');
      th.className = 'ge-th';
      th.style.width  = (col.width || 120) + 'px';
      th.dataset.ci   = ci;
      th.draggable    = true;

      const inner = document.createElement('div');
      inner.className = 'ge-th-inner';

      // 字段类型图标
      if (this._fieldTypeIcons) {
        const colType = col.editable === false ? 'readonly' : (col.type || 'text');
        const iconChar = _FIELD_ICON[colType] || 'T';
        const iconCls  = _FIELD_CLS[colType]  || 'ge-fi-text';
        const icon = document.createElement('span');
        icon.className = 'ge-field-icon ' + iconCls;
        icon.textContent = iconChar;
        inner.appendChild(icon);
      }

      const label = document.createElement('span');
      label.className = 'ge-th-label';
      label.textContent = col.label || col.key;
      inner.appendChild(label);
      th.appendChild(inner);

      // 列宽 resize handle
      const resizer = document.createElement('div');
      resizer.className = 'ge-col-resize';
      resizer.dataset.ci = ci;
      th.appendChild(resizer);

      // 列表头右键菜单
      if (this._onColHeaderAction) {
        th.addEventListener('contextmenu', e => {
          e.preventDefault();
          e.stopPropagation();
          this._showColCtxMenu(e, col.key);
        });
      }

      tr.appendChild(th);
    });

    this._theadEl.appendChild(tr);

    // 统计行
    if (this._showStats) {
      this._renderStatsRow();
    }
  }

  // ─── 统计行 ──────────────────────────────────────────────────────────────────

  _renderStatsRow() {
    if (this._statsRowEl) { this._statsRowEl.remove(); this._statsRowEl = null; }
    const tr = document.createElement('tr');
    tr.className = 'ge-stats-row';

    const tdNum = document.createElement('td');
    tdNum.innerHTML = `<span class="ge-stats-label">共</span><span class="ge-stats-val">${this._rows.length}</span>`;
    tr.appendChild(tdNum);

    this._cols.forEach((col) => {
      const td = document.createElement('td');
      const statType = this._statsRow?.[col.key] || (col.type === 'number' ? 'sum' : 'count');
      if (statType === 'none') { tr.appendChild(td); return; }
      const val = this._calcStat(col.key, statType);
      if (val !== null) {
        const label = statType === 'sum' ? '合计' : (statType === 'avg' ? '均值' : '');
        td.innerHTML = `${label ? `<span class="ge-stats-label">${label}</span>` : ''}<span class="ge-stats-val">${val}</span>`;
      }
      tr.appendChild(td);
    });

    this._statsRowEl = tr;
    this._theadEl.appendChild(tr);
  }

  _calcStat(key, type) {
    if (type === 'none') return null;
    const vals = this._rows.map(r => r[key]).filter(v => v != null && v !== '');
    if (type === 'count') return vals.length > 0 ? String(vals.length) : null;
    if (type === 'sum') {
      const nums = vals.map(v => parseFloat(v)).filter(v => !isNaN(v));
      return nums.length ? String(nums.reduce((a, b) => a + b, 0)) : null;
    }
    if (type === 'avg') {
      const nums = vals.map(v => parseFloat(v)).filter(v => !isNaN(v));
      return nums.length ? (nums.reduce((a, b) => a + b, 0) / nums.length).toFixed(1) : null;
    }
    return null;
  }

  // ─── 渲染 tbody ─────────────────────────────────────────────────────────────

  _renderBody() {
    this._tbodyEl.innerHTML = '';

    this._rows.forEach((row, ri) => {
      // ── 分组标题行 ──────────────────────────────────────────────
      if (row._isGroupHeader) {
        const tr = document.createElement('tr');
        tr.className = 'ge-group-header-row';
        tr.dataset.ri = ri;
        // 行号格列（空）
        const tdNum = document.createElement('td');
        tdNum.className = 'ge-td-num';
        tr.appendChild(tdNum);
        // 跨所有数据列
        const td = document.createElement('td');
        td.className = 'ge-group-header-cell';
        td.colSpan = this._cols.length;
        td.innerHTML = `<span class="ge-group-label">${row._groupLabel || ''}</span><span class="ge-group-count">${row._count ?? ''}</span>`;
        tr.appendChild(td);
        this._tbodyEl.appendChild(tr);
        return;
      }
      // ── 普通数据行 ──────────────────────────────────────────────
      const tr = document.createElement('tr');
      tr.dataset.ri = ri;
      if (this._rowClass) {
        const cls = this._rowClass(row);
        if (cls) tr.className = cls;
      }
      if (this._draggableRows) tr.draggable = true;

      // 行号 + 拖把手 / 详情入口
      const tdNum = document.createElement('td');
      tdNum.className = 'ge-td-num';

      if (this._draggableRows && !this._readOnly) {
        const handle = document.createElement('span');
        handle.className = 'ge-row-drag-handle';
        handle.title = '拖动排序';
        handle.innerHTML = `<svg width="10" height="14" viewBox="0 0 10 14" fill="none"><circle cx="3" cy="3" r="1.2" fill="currentColor"/><circle cx="7" cy="3" r="1.2" fill="currentColor"/><circle cx="3" cy="7" r="1.2" fill="currentColor"/><circle cx="7" cy="7" r="1.2" fill="currentColor"/><circle cx="3" cy="11" r="1.2" fill="currentColor"/><circle cx="7" cy="11" r="1.2" fill="currentColor"/></svg>`;
        tdNum.appendChild(handle);
      } else if (this._onRowClick && row.gid) {
        // 有详情面板：行号 + hover 时显示展开图标
        tdNum.className = 'ge-td-num ge-td-num-open';
        tdNum.innerHTML = `<span class="ge-row-num">${ri + 1}</span><span class="ge-row-open-icon"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg></span>`;
      } else {
        tdNum.textContent = ri + 1;
      }
      tr.appendChild(tdNum);

      // 数据列
      this._cols.forEach((col, ci) => {
        const td = document.createElement('td');
        td.className = 'ge-td';
        td.dataset.ri = ri;
        td.dataset.ci = ci;
        this._renderCell(td, col, row);
        tr.appendChild(td);
      });

      this._tbodyEl.appendChild(tr);
    });

    this._restoreSelection();
  }

  _renderCell(td, col, row) {
    const val = row[col.key];
    let content;
    if (this._renderers[col.key]) {
      td.innerHTML = this._renderers[col.key](val, row);
      content = null; // already set via innerHTML
    } else if (col.type === 'enum' && col.options?.length) {
      const opt = col.options.find(o => String(typeof o === 'object' ? o.value : o) === String(val ?? ''));
      const label = opt ? (typeof opt === 'object' ? (opt.label || opt.value) : opt) : (val ?? '');
      content = label == null ? '' : String(label);
    } else {
      content = val == null ? '' : String(val);
    }

    // openDetail 列（display_id）：静默触发器，鼠标变指针，点击打开详情面板
    // 不在本格显示图标——图标只在行号格显示（tr:hover .ge-td-num-open 已处理）
    if (col.openDetail && this._onRowClick && row.gid) {
      td.classList.add('ge-td-silent-trigger');
      if (content !== null) td.textContent = content;
    } else if (content !== null) {
      td.textContent = content;
    }
  }

  // ─── 事件绑定 ────────────────────────────────────────────────────────────────

  _bindEvents() {
    // 选区 — 委托在 tbody
    this._tbodyEl.addEventListener('mousedown', e => this._onTbodyMousedown(e));

    // 双击编辑
    this._tbodyEl.addEventListener('dblclick', e => this._onTbodyDblclick(e));

    // 行号展开图标 / ID 列单击 → 打开详情面板（onRowClick 模式）
    if (this._onRowClick) {
      this._tbodyEl.addEventListener('click', e => {
        const trigger = e.target.closest('.ge-td-num-open, .ge-td-silent-trigger');
        if (!trigger) return;
        const tr = trigger.closest('tr');
        if (!tr) return;
        const ri = +tr.dataset.ri;
        const row = this._rows[ri];
        if (!row || row._isGroupHeader || !row.gid) return;
        this._tbodyEl.querySelectorAll('.ge-row-clicked').forEach(r => r.classList.remove('ge-row-clicked'));
        tr.classList.add('ge-row-clicked');
        this._onRowClick(row);
      });
    }

    // enum 字段单击直接打开下拉（不需要双击）
    this._tbodyEl.addEventListener('click', e => {
      if (e.target.closest('input,select,button,a,.ge-row-drag-handle')) return;
      const td = e.target.closest('.ge-td');
      if (!td) return;
      const ci = +td.dataset.ci;
      const col = this._cols[ci];
      if (!col) return;
      if (col.type !== 'enum') return;
      if (!col.options?.length) return;
      if (!this._isEditable(ci)) return;
      const ri = +td.dataset.ri;
      const row = this._rows[ri];
      if (!row || row._isGroupHeader) return;
      this._startEdit(ri, ci, td);
    });

    // 粘贴
    this._el.setAttribute('tabindex', '-1');
    this._el.addEventListener('paste', e => this._onPaste(e));

    // 复制
    this._el.addEventListener('copy', e => this._onCopy(e));

    // 键盘
    this._el.addEventListener('keydown', e => this._onKeydown(e));

    // 右键
    this._tbodyEl.addEventListener('contextmenu', e => this._onContextMenu(e));

    // 列拖拽
    this._theadEl.addEventListener('dragstart', e => this._onColDragStart(e));
    this._theadEl.addEventListener('dragover',  e => this._onColDragOver(e));
    this._theadEl.addEventListener('dragleave', e => this._onColDragLeave(e));
    this._theadEl.addEventListener('drop',      e => this._onColDrop(e));
    this._theadEl.addEventListener('dragend',   e => this._onColDragEnd(e));

    // 行拖拽
    this._tbodyEl.addEventListener('dragstart', e => this._onRowDragStart(e));
    this._tbodyEl.addEventListener('dragover',  e => this._onRowDragOver(e));
    this._tbodyEl.addEventListener('dragleave', e => this._onRowDragLeave(e));
    this._tbodyEl.addEventListener('drop',      e => this._onRowDrop(e));
    this._tbodyEl.addEventListener('dragend',   e => this._onRowDragEnd(e));

    // 列宽调整
    this._theadEl.addEventListener('mousedown', e => this._onResizeMousedown(e));

    // 关闭右键菜单
    this._docClickHandler = () => this._destroyCtxMenu();
    document.addEventListener('click', this._docClickHandler);
  }

  _removeDocListeners() {
    document.removeEventListener('click', this._docClickHandler);
    document.removeEventListener('mousemove', this._resizeMoveHandler);
    document.removeEventListener('mouseup',   this._resizeUpHandler);
  }

  // ─── 选区 ────────────────────────────────────────────────────────────────────

  _onTbodyMousedown(e) {
    // 正在与 input / select / button 交互时不抢焦点
    if (e.target.closest('input, select, button')) return;
    // display_id 静默触发列点击用于打开详情，不做单元格选区
    if (e.target.closest('.ge-td-silent-trigger')) return;
    const td = e.target.closest('.ge-td');
    if (!td) return;
    const ri = +td.dataset.ri;
    const ci = +td.dataset.ci;

    if (e.shiftKey && this._anchor) {
      this._range = this._makeRange(this._anchor.ri, this._anchor.ci, ri, ci);
    } else {
      this._anchor = { ri, ci };
      this._range  = { r1: ri, c1: ci, r2: ri, c2: ci };
    }
    this._applySelection();
    // 焦点给容器以接收键盘事件
    this._el.focus({ preventScroll: true });
  }

  _makeRange(r1, c1, r2, c2) {
    return {
      r1: Math.min(r1, r2), c1: Math.min(c1, c2),
      r2: Math.max(r1, r2), c2: Math.max(c1, c2),
    };
  }

  _applySelection() {
    // 清除旧选区
    this._tbodyEl.querySelectorAll('.ge-anchor, .ge-in-range').forEach(el => {
      el.classList.remove('ge-anchor', 'ge-in-range');
    });
    if (!this._anchor || !this._range) return;

    const { r1, c1, r2, c2 } = this._range;
    const { ri: ar, ci: ac } = this._anchor;

    for (let ri = r1; ri <= r2; ri++) {
      for (let ci = c1; ci <= c2; ci++) {
        const td = this._getTd(ri, ci);
        if (!td) continue;
        td.classList.add('ge-in-range');
        if (ri === ar && ci === ac) td.classList.add('ge-anchor');
      }
    }
  }

  _clearSelection() {
    this._anchor = null;
    this._range  = null;
  }

  _restoreSelection() {
    // 行重排后 anchor 可能超出范围，清理
    if (this._anchor && this._anchor.ri >= this._rows.length) this._clearSelection();
    this._applySelection();
  }

  _getTd(ri, ci) {
    const tr = this._tbodyEl.rows[ri];
    if (!tr) return null;
    // ci 是数据列索引，+1 是因为第 0 列是行号
    return tr.cells[ci + 1] || null;
  }

  // ─── 编辑 ────────────────────────────────────────────────────────────────────

  _onTbodyDblclick(e) {
    const td = e.target.closest('.ge-td');
    if (!td) return;
    const ri = +td.dataset.ri;
    const ci = +td.dataset.ci;
    this._startEdit(ri, ci, td);
  }

  _isEditable(ci) {
    if (this._readOnly) return false;
    const col = this._cols[ci];
    if (!col) return false;
    return col.editable !== false;
  }

  _startEdit(ri, ci, td, initChar) {
    if (!this._isEditable(ci)) return;
    if (this._editCell) this._commitEdit(true);

    const row = this._rows[ri];
    const col = this._cols[ci];

    // ── enum 列：<select> 下拉 ──────────────────────────────────────────────
    const colType = col.type;
    const colOpts = col.options;
    if (colType === 'enum' && colOpts?.length) {
      const select = document.createElement('select');
      select.className = 'ge-cell-input ge-cell-select';
      colOpts.forEach(opt => {
        const o = document.createElement('option');
        o.value       = typeof opt === 'object' ? opt.value : opt;
        o.textContent = typeof opt === 'object' ? (opt.label || opt.value) : opt;
        if (o.value === String(row[col.key] ?? '')) o.selected = true;
        select.appendChild(o);
      });
      td.classList.add('ge-editing');
      td.appendChild(select);
      select.focus();
      this._editCell = { ri, ci, td, input: select };

      select.addEventListener('blur', () => {
        this._editCommitTimer = setTimeout(() => this._commitEdit(true), 80);
      });
      select.addEventListener('change', () => {
        clearTimeout(this._editCommitTimer);
        this._commitEdit(true);
      });
      select.addEventListener('keydown', e => {
        if (e.key === 'Escape') {
          clearTimeout(this._editCommitTimer);
          this._commitEdit(false);
          e.preventDefault();
          e.stopPropagation();
        } else if (e.key === 'Tab') {
          clearTimeout(this._editCommitTimer);
          this._commitEdit(true);
          this._moveSelection(0, e.shiftKey ? -1 : 1);
          e.preventDefault();
          e.stopPropagation();
        }
      });
      return;
    }

    // ── 普通 input（text / number）──────────────────────────────────────────
    const input = document.createElement('input');
    input.type      = col.type === 'number' ? 'number' : 'text';
    input.className = 'ge-cell-input';
    if (col.maxLength) input.maxLength = col.maxLength;
    input.value = initChar != null ? initChar : (row[col.key] == null ? '' : String(row[col.key]));
    if (initChar != null) {
      requestAnimationFrame(() => { input.selectionStart = input.selectionEnd = input.value.length; });
    } else {
      requestAnimationFrame(() => input.select());
    }

    td.classList.add('ge-editing');
    td.appendChild(input);
    input.focus();

    this._editCell = { ri, ci, td, input };

    input.addEventListener('blur', () => {
      this._editCommitTimer = setTimeout(() => this._commitEdit(true), 80);
    });

    input.addEventListener('keydown', e => {
      if (e.key === 'Escape') {
        clearTimeout(this._editCommitTimer);
        this._commitEdit(false);
        e.preventDefault();
        e.stopPropagation();
      } else if (e.key === 'Enter') {
        clearTimeout(this._editCommitTimer);
        this._commitEdit(true);
        this._moveSelection(1, 0);
        e.preventDefault();
        e.stopPropagation();
      } else if (e.key === 'Tab') {
        clearTimeout(this._editCommitTimer);
        this._commitEdit(true);
        this._moveSelection(0, e.shiftKey ? -1 : 1);
        e.preventDefault();
        e.stopPropagation();
      }
    });

    // 阻止非处理键冒泡到容器
    input.addEventListener('keydown', e => {
      if (!['Escape','Enter','Tab'].includes(e.key)) e.stopPropagation();
    });
  }

  _commitEdit(save) {
    if (!this._editCell) return;
    const { ri, ci, td, input } = this._editCell;
    this._editCell = null;
    clearTimeout(this._editCommitTimer);

    td.classList.remove('ge-editing');
    if (td.contains(input)) td.removeChild(input);

    if (save) {
      const col = this._cols[ci];
      const raw = input.value;

      // required 校验
      if (col.required && !raw.trim()) {
        td.classList.add('ge-cell-error');
        setTimeout(() => td.classList.remove('ge-cell-error'), 1500);
        // 仍然渲染空值（不阻止提交，让业务层决定是否保存）
      } else {
        td.classList.remove('ge-cell-error');
      }

      let val = raw;
      if (col.type === 'number') val = parseFloat(raw) || 0;

      const oldVal = this._rows[ri][col.key];
      if (String(oldVal ?? '') !== String(val)) {
        this._rows[ri] = { ...this._rows[ri], [col.key]: val };
        this._fireRowsChange();
      }
    }

    // 重新渲染该格
    const col = this._cols[ci];
    const row = this._rows[ri];
    if (td) this._renderCell(td, col, row);

    this._restoreSelection();
    this._el.focus({ preventScroll: true });
  }

  // ─── 键盘导航 ────────────────────────────────────────────────────────────────

  _onKeydown(e) {
    if (this._editCell) return; // 编辑中由 input 内部处理

    const { key, ctrlKey, metaKey, shiftKey } = e;
    const ctrl = ctrlKey || metaKey;

    if (!this._anchor) return;
    const { ri, ci } = this._anchor;

    switch (key) {
      case 'ArrowUp':
        this._moveSelection(-1, 0, shiftKey);
        e.preventDefault();
        break;
      case 'ArrowDown':
        this._moveSelection(1, 0, shiftKey);
        e.preventDefault();
        break;
      case 'ArrowLeft':
        this._moveSelection(0, -1, shiftKey);
        e.preventDefault();
        break;
      case 'ArrowRight':
        this._moveSelection(0, 1, shiftKey);
        e.preventDefault();
        break;
      case 'Tab':
        this._commitEdit(true);
        this._moveSelection(0, shiftKey ? -1 : 1);
        e.preventDefault();
        break;
      case 'Enter':
        this._startEdit(ri, ci, this._getTd(ri, ci));
        e.preventDefault();
        break;
      case 'Delete':
      case 'Backspace':
        this._clearSelectedCells();
        e.preventDefault();
        break;
      default:
        // 直接打字触发编辑（可打印字符）
        if (!ctrl && key.length === 1) {
          const td = this._getTd(ri, ci);
          if (td) this._startEdit(ri, ci, td, key);
          e.preventDefault();
        }
        break;
    }
  }

  _moveSelection(dr, dc, extend) {
    if (!this._anchor) return;
    let { ri, ci } = this._anchor;
    const maxR = this._rows.length - 1;
    const maxC = this._cols.length - 1;

    if (extend) {
      // 扩展选区：移动 range 的另一端
      let { r1, c1, r2, c2 } = this._range;
      // 判断 anchor 在哪端
      const anchorAtBottom = this._anchor.ri === r2;
      const anchorAtRight  = this._anchor.ci === c2;

      if (dr !== 0) {
        if (anchorAtBottom) r1 = Math.max(0, Math.min(maxR, r1 + dr));
        else                r2 = Math.max(0, Math.min(maxR, r2 + dr));
      }
      if (dc !== 0) {
        if (anchorAtRight) c1 = Math.max(0, Math.min(maxC, c1 + dc));
        else               c2 = Math.max(0, Math.min(maxC, c2 + dc));
      }
      this._range = { r1: Math.min(r1,r2), c1: Math.min(c1,c2), r2: Math.max(r1,r2), c2: Math.max(c1,c2) };
    } else {
      ri = Math.max(0, Math.min(maxR, ri + dr));
      ci = Math.max(0, Math.min(maxC, ci + dc));
      this._anchor = { ri, ci };
      this._range  = { r1: ri, c1: ci, r2: ri, c2: ci };
      // 滚动可见
      const td = this._getTd(ri, ci);
      td?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' });
    }
    this._applySelection();
  }

  _clearSelectedCells() {
    if (!this._range || this._readOnly) return;
    const { r1, c1, r2, c2 } = this._range;
    let changed = false;
    for (let ri = r1; ri <= r2; ri++) {
      for (let ci = c1; ci <= c2; ci++) {
        const col = this._cols[ci];
        if (!col || col.editable === false) continue;
        if (this._rows[ri][col.key] !== '' && this._rows[ri][col.key] != null) {
          this._rows[ri] = { ...this._rows[ri], [col.key]: '' };
          changed = true;
        }
      }
    }
    if (changed) {
      this._renderBody();
      this._fireRowsChange();
    }
  }

  // ─── 复制 Ctrl+C ─────────────────────────────────────────────────────────────

  _onCopy(e) {
    if (!this._range) return;
    e.preventDefault();
    const tsv = this._selectionToTSV();
    e.clipboardData.setData('text/plain', tsv);
  }

  _selectionToTSV() {
    if (!this._range) return '';
    const { r1, c1, r2, c2 } = this._range;
    const lines = [];
    for (let ri = r1; ri <= r2; ri++) {
      const cells = [];
      for (let ci = c1; ci <= c2; ci++) {
        const col = this._cols[ci];
        if (!col) { cells.push(''); continue; }
        const val = this._rows[ri]?.[col.key];
        cells.push(val == null ? '' : String(val).replace(/\t/g,' ').replace(/\n/g,' '));
      }
      lines.push(cells.join('\t'));
    }
    return lines.join('\n');
  }

  // ─── 粘贴 ────────────────────────────────────────────────────────────────────

  _onPaste(e) {
    if (this._readOnly || !this._anchor) return;
    e.preventDefault();
    const text = e.clipboardData.getData('text/plain');
    if (!text) return;

    // 解析 TSV
    const dataRows = text.split('\n').map(line => line.split('\t'));

    const startRi = this._anchor.ri;
    const startCi = this._anchor.ci;
    let changed = false;

    dataRows.forEach((dataRow, dr) => {
      const ri = startRi + dr;
      // 不足时追加行
      while (ri >= this._rows.length) {
        this._rows.push({});
        changed = true;
      }
      dataRow.forEach((val, dc) => {
        const ci = startCi + dc;
        const col = this._cols[ci];
        if (!col || col.editable === false) return;
        const typedVal = col.type === 'number' ? (parseFloat(val) || 0) : val;
        if (this._rows[ri][col.key] !== typedVal) {
          this._rows[ri] = { ...this._rows[ri], [col.key]: typedVal };
          changed = true;
        }
      });
    });

    if (changed) {
      this._renderBody();
      this._fireRowsChange();
    }
  }

  // ─── 右键菜单 ────────────────────────────────────────────────────────────────

  _onContextMenu(e) {
    e.preventDefault();
    const tr = e.target.closest('tr');
    if (!tr || !tr.dataset.ri) return;
    this._ctxTargetRow = +tr.dataset.ri;

    this._destroyCtxMenu();
    const menu = document.createElement('div');
    menu.className = 'ge-ctx-menu';

    // 计算自定义菜单项
    const row = this._rows[this._ctxTargetRow] || {};
    const extras = this._extraCtxItems ? this._extraCtxItems(row) : [];
    const extraHtml = extras.map(item => `
      <div class="ge-ctx-item${item.danger ? ' danger' : ''}" data-action="custom:${item.action}">
        ${item.icon || ''}${item.label}
      </div>
    `).join('');

    menu.innerHTML = `
      <div class="ge-ctx-item" data-action="insert-above">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        上方插行
      </div>
      <div class="ge-ctx-item" data-action="insert-below">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        下方插行
      </div>
      <div class="ge-ctx-sep"></div>
      <div class="ge-ctx-item" data-action="clear">清空选区</div>
      <div class="ge-ctx-sep"></div>
      <div class="ge-ctx-item danger" data-action="delete-row">删除行</div>
      ${extras.length ? '<div class="ge-ctx-sep"></div>' + extraHtml : ''}
    `;
    menu.style.left = e.clientX + 'px';
    menu.style.top  = e.clientY + 'px';
    document.body.appendChild(menu);
    this._ctxMenu = menu;

    menu.addEventListener('click', ev => {
      const action = ev.target.closest('[data-action]')?.dataset.action;
      this._destroyCtxMenu();
      if (!action) return;
      ev.stopPropagation();
      if (action === 'insert-above') this._insertRow(this._ctxTargetRow);
      else if (action === 'insert-below') this._insertRow(this._ctxTargetRow + 1);
      else if (action === 'delete-row') this._deleteRow(this._ctxTargetRow);
      else if (action === 'clear') this._clearSelectedCells();
      else if (action.startsWith('custom:') && this._onContextAction) {
        const customAction = action.slice(7);
        this._onContextAction(customAction, { ...row });
      }
    });
  }

  _destroyCtxMenu() {
    if (this._ctxMenu) {
      this._ctxMenu.remove();
      this._ctxMenu = null;
    }
  }

  // ─── 行增删 ──────────────────────────────────────────────────────────────────

  /** 公开方法：在顶部插入空行并自动聚焦第一个可编辑格，供外部（ListShell 新建按钮）调用 */
  addNewRow() {
    this._rows.unshift({});
    this._clearSelection();
    this._renderBody();
    this._fireRowsChange();
    // 自动聚焦：跳过 display_id / _actions / editable:false，找第一个内容列
    const ci = this._firstEditableColIdx();
    if (ci < 0) return;
    requestAnimationFrame(() => {
      const tr = this._tbodyEl.querySelector('tr[data-ri="0"]');
      if (!tr) return;
      const td = tr.querySelector(`td[data-ci="${ci}"]`);
      if (td) td.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
    });
  }

  _addRow() {
    this._rows.push({});
    this._renderBody();
    this._fireRowsChange();
    // 底部新行同样自动聚焦标题列
    const ci = this._firstEditableColIdx();
    if (ci < 0) return;
    const lastRi = this._rows.length - 1;
    requestAnimationFrame(() => {
      const tr = this._tbodyEl.querySelector(`tr[data-ri="${lastRi}"]`);
      if (!tr) return;
      const td = tr.querySelector(`td[data-ci="${ci}"]`);
      if (td) td.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
    });
  }

  /** 找第一个值得聚焦的内容列：跳过 editable:false、display_id 和下划线开头的内部列 */
  _firstEditableColIdx() {
    return this._cols.findIndex(c =>
      c.editable !== false &&
      c.key !== 'display_id' &&
      !c.key.startsWith('_')
    );
  }

  _insertRow(atIdx) {
    const idx = Math.max(0, Math.min(atIdx, this._rows.length));
    this._rows.splice(idx, 0, {});
    this._clearSelection();
    this._renderBody();
    this._fireRowsChange();
  }

  _deleteRow(ri) {
    if (ri < 0 || ri >= this._rows.length) return;
    const row = this._rows[ri];
    if (this._onDeleteRow) {
      this._onDeleteRow({ ...row });
      return;  // 交给调用方处理，不直接 splice
    }
    this._rows.splice(ri, 1);
    this._clearSelection();
    this._renderBody();
    this._fireRowsChange();
  }

  // ─── 行拖拽 ──────────────────────────────────────────────────────────────────

  _onRowDragStart(e) {
    const tr = e.target.closest('tr[data-ri]');
    if (!tr || e.target.closest('.ge-row-drag-handle') === null && !e.target.closest('.ge-row-drag-handle')) {
      // 只允许从拖把手发起
      if (!e.target.classList.contains('ge-row-drag-handle') && !e.target.closest('.ge-row-drag-handle')) {
        e.preventDefault();
        return;
      }
    }
    this._dragRowIdx = +tr.dataset.ri;
    tr.classList.add('ge-dragging');
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', 'ge-row');
  }

  _onRowDragOver(e) {
    if (this._dragRowIdx == null) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    const tr = e.target.closest('tr[data-ri]');
    this._tbodyEl.querySelectorAll('.ge-drag-over-row').forEach(el => el.classList.remove('ge-drag-over-row'));
    if (tr) tr.classList.add('ge-drag-over-row');
  }

  _onRowDragLeave(e) {
    const tr = e.target.closest('tr[data-ri]');
    if (tr) tr.classList.remove('ge-drag-over-row');
  }

  _onRowDrop(e) {
    if (this._dragRowIdx == null) return;
    e.preventDefault();
    const tr = e.target.closest('tr[data-ri]');
    if (!tr) return;
    const targetIdx = +tr.dataset.ri;
    if (targetIdx !== this._dragRowIdx) {
      this._moveRow(this._dragRowIdx, targetIdx);
    }
    this._onRowDragEnd(e);
  }

  _onRowDragEnd(e) {
    this._dragRowIdx = null;
    this._tbodyEl.querySelectorAll('.ge-dragging, .ge-drag-over-row').forEach(el => {
      el.classList.remove('ge-dragging', 'ge-drag-over-row');
    });
  }

  _moveRow(fromIdx, toIdx) {
    const row = this._rows.splice(fromIdx, 1)[0];
    const insertAt = toIdx > fromIdx ? toIdx - 1 : toIdx;
    this._rows.splice(insertAt, 0, row);
    this._clearSelection();
    this._renderBody();
    this._fireRowsChange();
  }

  // ─── 列拖拽 ──────────────────────────────────────────────────────────────────

  _onColDragStart(e) {
    const th = e.target.closest('th[data-ci]');
    if (!th) { e.preventDefault(); return; }
    // 如果点的是 resize handle 则不触发列拖
    if (e.target.classList.contains('ge-col-resize')) { e.preventDefault(); return; }
    this._dragColIdx = +th.dataset.ci;
    th.classList.add('ge-dragging-col');
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', 'ge-col');
  }

  _onColDragOver(e) {
    if (this._dragColIdx == null) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    const th = e.target.closest('th[data-ci]');
    this._theadEl.querySelectorAll('.ge-drag-over-col').forEach(el => el.classList.remove('ge-drag-over-col'));
    if (th && th.dataset.ci != null) th.classList.add('ge-drag-over-col');
  }

  _onColDragLeave(e) {
    const th = e.target.closest('th[data-ci]');
    if (th) th.classList.remove('ge-drag-over-col');
  }

  _onColDrop(e) {
    if (this._dragColIdx == null) return;
    e.preventDefault();
    const th = e.target.closest('th[data-ci]');
    if (!th || th.dataset.ci == null) return;
    const targetIdx = +th.dataset.ci;
    if (targetIdx !== this._dragColIdx) {
      this._moveCol(this._dragColIdx, targetIdx);
    }
    this._onColDragEnd(e);
  }

  _onColDragEnd(e) {
    this._dragColIdx = null;
    this._theadEl.querySelectorAll('.ge-dragging-col, .ge-drag-over-col').forEach(el => {
      el.classList.remove('ge-dragging-col', 'ge-drag-over-col');
    });
  }

  _moveCol(fromIdx, toIdx) {
    const col = this._cols.splice(fromIdx, 1)[0];
    const insertAt = toIdx > fromIdx ? toIdx - 1 : toIdx;
    this._cols.splice(insertAt, 0, col);
    this._clearSelection();
    this._renderHead();
    this._renderBody();
    if (this._onColsChange) this._onColsChange([...this._cols]);
  }

  // ─── 列宽调整 ────────────────────────────────────────────────────────────────

  _onResizeMousedown(e) {
    const handle = e.target.closest('.ge-col-resize');
    if (!handle) return;
    e.preventDefault();
    e.stopPropagation();

    const ci = +handle.dataset.ci;
    const th = this._theadEl.querySelector(`th[data-ci="${ci}"]`);
    if (!th) return;

    this._resizingCol  = ci;
    this._resizeStartX = e.clientX;
    this._resizeStartW = th.offsetWidth;
    handle.classList.add('resizing');

    this._resizeMoveHandler = (ev) => {
      const dx = ev.clientX - this._resizeStartX;
      const newW = Math.max(40, this._resizeStartW + dx);
      this._cols[ci] = { ...this._cols[ci], width: newW };
      th.style.width = newW + 'px';
    };

    this._resizeUpHandler = () => {
      handle.classList.remove('resizing');
      document.removeEventListener('mousemove', this._resizeMoveHandler);
      document.removeEventListener('mouseup',   this._resizeUpHandler);
      this._resizingCol = null;
      if (this._onColsChange) this._onColsChange([...this._cols]);
    };

    document.addEventListener('mousemove', this._resizeMoveHandler);
    document.addEventListener('mouseup',   this._resizeUpHandler);
  }

  // ─── 回调 ────────────────────────────────────────────────────────────────────

  _fireRowsChange() {
    if (this._onRowsChange) this._onRowsChange(this._rows.map(r => ({ ...r })));
  }

  // ─── 列表头右键菜单 ───────────────────────────────────────────────────────────

  _showColCtxMenu(e, colKey) {
    document.querySelector('.ge-col-ctx-menu')?.remove();
    const menu = document.createElement('div');
    menu.className = 'ge-col-ctx-menu ge-ctx-menu';
    menu.style.cssText = `position:fixed;left:${e.clientX}px;top:${e.clientY}px;z-index:9990`;
    const items = [
      { label: '隐藏字段', action: 'hide',
        icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>' },
      { label: '按本字段筛选', action: 'filter',
        icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>' },
      { label: '按本字段排序', action: 'sort',
        icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>' },
      { label: '按本字段分组', action: 'group',
        icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>' },
    ];
    items.forEach(item => {
      const el = document.createElement('div');
      el.className = 'ge-ctx-item';
      el.innerHTML = `<span class="ge-ctx-icon">${item.icon}</span>${item.label}`;
      el.addEventListener('mousedown', (ev) => {
        ev.stopPropagation();
        menu.remove();
        this._onColHeaderAction(item.action, colKey);
      });
      menu.appendChild(el);
    });
    document.body.appendChild(menu);
    // 边界修正
    const rect = menu.getBoundingClientRect();
    if (rect.right  > window.innerWidth)  menu.style.left = (e.clientX - rect.width)  + 'px';
    if (rect.bottom > window.innerHeight) menu.style.top  = (e.clientY - rect.height) + 'px';
    const close = (ev) => { if (!menu.contains(ev.target)) { menu.remove(); document.removeEventListener('mousedown', close); } };
    setTimeout(() => document.addEventListener('mousedown', close), 0);
  }

  /** 根据 gid 查找行在 _rows 中的索引（-1 表示未找到）*/
  getRowIndex(gid) {
    return (this._rows || []).findIndex(r => r.gid === gid);
  }

  /** 根据索引获取行数据（越界返回 null）*/
  getRowByIndex(idx) {
    return (this._rows || [])[idx] || null;
  }
}

/**
 * geMergeCols — 自动合并后端数据中未在 baseCols 定义的列
 * 当数据库新增字段时，表格列头自动出现；字段消失时自动不再显示。
 *
 * @param {Array} baseCols  基础列定义（模块固定列）
 * @param {Array} rows      本次加载的实际数据行
 * @param {Set}   skipKeys  需跳过的内部字段（如 gid、外键等）
 * @returns {Array}         合并后的列定义
 */
function geMergeCols(baseCols, rows, skipKeys = new Set()) {
  if (!rows || !rows.length) return baseCols;
  const knownKeys = new Set(baseCols.map(c => c.key));
  // _actions 列始终保持在最后
  const actionIdx = baseCols.findIndex(c => c.key === '_actions');
  const extra = [];
  rows.forEach(r => {
    Object.keys(r).forEach(k => {
      if (knownKeys.has(k)) return;
      if (skipKeys.has(k)) return;
      if (k.startsWith('_')) return;
      if (k === 'gid') return;
      if (extra.some(e => e.key === k)) return;
      extra.push({ key: k, label: k, type: 'text', width: 120 });
      knownKeys.add(k);
    });
  });
  if (!extra.length) return baseCols;
  const insertAt = actionIdx >= 0 ? actionIdx : baseCols.length;
  return [
    ...baseCols.slice(0, insertAt),
    ...extra,
    ...baseCols.slice(insertAt),
  ];
}

