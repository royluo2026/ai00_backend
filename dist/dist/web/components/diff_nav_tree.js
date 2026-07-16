'use strict';
/**
 * DiffNavTree — 紧凑树导航 + 可选差异比对组件
 *
 * 用法：
 *   const dnt = new DiffNavTree({ mountEl, title, idField, labelField, parentField,
 *     typeField, vppsField, compareFields, typeAbbr, typeColor,
 *     defaultExpandDepth, onActivate, onCompareRequest });
 *   dnt.setData(rows);
 *   // 外部激活：
 *   dnt.setActiveNode(gid);
 *   // 比对：
 *   dnt.setCompareData(rows, { primaryLabel, secondaryLabel });
 *   dnt.runCompare();
 */
class DiffNavTree {
  constructor(opts = {}) {
    this._mountEl      = opts.mountEl;
    this._title        = opts.title        || '树形导航';
    this._idField      = opts.idField      || 'gid';
    this._labelField   = opts.labelField   || 'title';
    this._parentField  = opts.parentField  || 'parent_gid';
    this._typeField    = opts.typeField    || 'node_type';
    this._vppsField    = opts.vppsField    || 'vpps';
    this._compareFields = opts.compareFields || [];
    this._typeAbbr     = opts.typeAbbr     || {};
    this._typeColor    = opts.typeColor    || {};
    this._defaultExpandDepth = opts.defaultExpandDepth != null ? opts.defaultExpandDepth : 1;
    this._onActivate   = opts.onActivate   || null;
    this._onCompareRequest = opts.onCompareRequest || null;

    // state
    this._rows         = [];
    this._rowById      = new Map();
    this._childMap     = new Map();   // id → children[]
    this._depthById    = new Map();
    this._collapsed    = new Set();   // id of nodes whose children are hidden
    this._activeId     = null;

    // compare state
    this._compareRows  = [];
    this._compareByVpps = new Map();  // vpps → compareRow
    this._diffMap      = new Map();   // id → { state, diffs }
    this._orphans      = [];          // rows in compare not in primary (少项)
    this._primaryLabel  = 'A';
    this._secondaryLabel = 'B';
    this._compareAt    = null;
    this._orphanSectionCollapsed = false;

    // tooltip
    this._tooltipEl = null;
    this._tooltipHideTimer = null;

    this._build();
  }

  // ══════════════════════════════════════════════════════════════
  // DOM 构建
  // ══════════════════════════════════════════════════════════════

  _build() {
    if (!this._mountEl) return;
    this._mountEl.innerHTML = '';
    this._mountEl.style.cssText = 'display:flex;flex-direction:column;height:100%;min-height:0;overflow:hidden';

    const root = document.createElement('div');
    root.className = 'dnt-root';

    // header
    const hdr = document.createElement('div');
    hdr.className = 'dnt-header';

    const titleEl = document.createElement('span');
    titleEl.className = 'dnt-title';
    titleEl.textContent = this._title;
    hdr.appendChild(titleEl);

    const cmpBtn = document.createElement('button');
    cmpBtn.className = 'dnt-compare-btn';
    cmpBtn.textContent = '比对';
    cmpBtn.addEventListener('click', () => this._onCompareClick());
    hdr.appendChild(cmpBtn);
    this._cmpBtn = cmpBtn;

    root.appendChild(hdr);

    // meta area
    const meta = document.createElement('div');
    meta.className = 'dnt-meta';
    this._metaEl = meta;

    this._metaLabelsEl = document.createElement('div');
    this._metaLabelsEl.className = 'dnt-meta-labels';
    meta.appendChild(this._metaLabelsEl);

    this._metaTimeEl = document.createElement('div');
    this._metaTimeEl.className = 'dnt-meta-time';
    meta.appendChild(this._metaTimeEl);

    this._metaStatsEl = document.createElement('div');
    this._metaStatsEl.className = 'dnt-meta-stats';
    meta.appendChild(this._metaStatsEl);

    root.appendChild(meta);

    // body
    const body = document.createElement('div');
    body.className = 'dnt-body';
    this._bodyEl = body;
    root.appendChild(body);

    // tooltip (fixed, appended to document.body to avoid overflow clip)
    const tooltip = document.createElement('div');
    tooltip.className = 'dnt-tooltip';
    tooltip.style.display = 'none';
    document.body.appendChild(tooltip);
    this._tooltipEl = tooltip;

    this._mountEl.appendChild(root);
    this._rootEl = root;
  }

  // ══════════════════════════════════════════════════════════════
  // 公开 API
  // ══════════════════════════════════════════════════════════════

  /** 设置主数据，重建索引 + 渲染 */
  setData(rows) {
    this._rows = rows || [];
    this._buildIndexes();
    this._initCollapsed();
    this._renderTree();
  }

  /** 设置对比数据（不自动比对） */
  setCompareData(rows, { primaryLabel, secondaryLabel } = {}) {
    this._compareRows = rows || [];
    if (primaryLabel)   this._primaryLabel   = primaryLabel;
    if (secondaryLabel) this._secondaryLabel = secondaryLabel;
    this._buildCompareIndex();
  }

  /** 执行差异计算 + 刷新 */
  runCompare() {
    if (!this._compareRows.length) return;
    this._calcDiff();
    this._compareAt = new Date();
    this._updateMeta();
    this._renderTree();
  }

  /** 外部 → 树高亮（不触发 onActivate） */
  setActiveNode(id) {
    this._activeId = id;
    // ensure visible
    this._ensureVisible(id);
    this._applyActiveClass();
    this._scrollToActive();
  }

  // ══════════════════════════════════════════════════════════════
  // 数据层
  // ══════════════════════════════════════════════════════════════

  _buildIndexes() {
    this._rowById.clear();
    this._childMap.clear();
    this._depthById.clear();

    const id = this._idField;
    const pid = this._parentField;

    for (const r of this._rows) {
      this._rowById.set(r[id], r);
    }
    for (const r of this._rows) {
      const pk = r[pid] || null;
      if (!this._childMap.has(pk)) this._childMap.set(pk, []);
      this._childMap.get(pk).push(r);
    }

    // sort children by seq_no if available
    for (const [, arr] of this._childMap) {
      arr.sort((a, b) => (a.seq_no ?? 0) - (b.seq_no ?? 0));
    }

    // precompute depths
    const calcDepth = (gid, cache) => {
      if (cache.has(gid)) return cache.get(gid);
      const r = this._rowById.get(gid);
      if (!r || !r[pid]) { cache.set(gid, 0); return 0; }
      const d = calcDepth(r[pid], cache) + 1;
      cache.set(gid, d);
      return d;
    };
    for (const r of this._rows) calcDepth(r[id], this._depthById);
  }

  _buildCompareIndex() {
    this._compareByVpps.clear();
    const vf = this._vppsField;
    for (const r of this._compareRows) {
      if (r[vf]) this._compareByVpps.set(r[vf], r);
    }
  }

  _initCollapsed() {
    this._collapsed.clear();
    const depthLimit = this._defaultExpandDepth;
    for (const r of this._rows) {
      const d = this._depthById.get(r[this._idField]) ?? 0;
      if (d > depthLimit) this._collapsed.add(r[this._idField]);
    }
    // Reset active
    this._activeId = null;
    // Reset compare state on new data
    this._diffMap.clear();
    this._orphans = [];
    this._compareAt = null;
  }

  _calcDiff() {
    this._diffMap.clear();
    this._orphans = [];

    const vf = this._vppsField;
    const id = this._idField;

    // primary vpps set
    const primaryVppsSet = new Set();
    for (const r of this._rows) {
      if (r[vf]) primaryVppsSet.add(r[vf]);
    }

    // calc diff for each primary row
    for (const r of this._rows) {
      const vpps = r[vf];
      if (!vpps) continue;

      const cmp = this._compareByVpps.get(vpps);
      if (!cmp) {
        // slot_mismatch: in primary, not in compare
        this._diffMap.set(r[id], { state: 'slot_mismatch', diffs: [] });
        continue;
      }

      // compare fields
      const diffs = [];
      for (const { key, label } of this._compareFields) {
        const v1 = r[key];
        const v2 = cmp[key];
        if (String(v1 ?? '') !== String(v2 ?? '')) {
          diffs.push({ key, label, from: v1, to: v2 });
        }
      }
      this._diffMap.set(r[id], {
        state: diffs.length > 0 ? 'content_mismatch' : 'match',
        diffs,
      });
    }

    // orphans: in compare, not in primary
    for (const r of this._compareRows) {
      const vpps = r[vf];
      if (vpps && !primaryVppsSet.has(vpps)) {
        this._orphans.push(r);
      }
    }
  }

  _updateMeta() {
    if (!this._compareAt) return;

    let matchCnt = 0, mismatchCnt = 0, slotCnt = 0;
    for (const [, { state }] of this._diffMap) {
      if (state === 'match') matchCnt++;
      else if (state === 'content_mismatch') mismatchCnt++;
      else if (state === 'slot_mismatch') slotCnt++;
    }
    const orphanCnt = this._orphans.length;

    this._metaLabelsEl.textContent = `${this._primaryLabel} vs ${this._secondaryLabel}`;
    const d = this._compareAt;
    this._metaTimeEl.textContent = `比对于 ${d.getMonth()+1}/${d.getDate()} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;

    this._metaStatsEl.innerHTML = `
      <span class="dnt-stat-match">✓ ${matchCnt}</span>
      <span class="dnt-stat-mismatch">≠ ${mismatchCnt}</span>
      <span class="dnt-stat-slot">! ${slotCnt}</span>
      <span class="dnt-stat-orphan">少 ${orphanCnt}</span>
    `;
    this._metaEl.classList.add('visible');
  }

  // ══════════════════════════════════════════════════════════════
  // 渲染层
  // ══════════════════════════════════════════════════════════════

  _renderTree() {
    if (!this._bodyEl) return;
    this._bodyEl.innerHTML = '';

    // build visible rows list (DFS, skip collapsed subtrees)
    const visibleRows = this._buildVisibleList();

    for (const { row, depth } of visibleRows) {
      this._bodyEl.appendChild(this._createRow(row, depth));
    }

    // orphan section
    if (this._orphans.length > 0 && this._compareAt) {
      this._bodyEl.appendChild(this._createOrphanSection());
    }

    // restore active class
    this._applyActiveClass();
  }

  _buildVisibleList() {
    const result = [];
    const id = this._idField;
    const pid = this._parentField;

    const roots = this._childMap.get(null) || [];

    const walk = (arr, depth) => {
      for (const row of arr) {
        result.push({ row, depth });
        if (!this._collapsed.has(row[id])) {
          const children = this._childMap.get(row[id]) || [];
          walk(children, depth + 1);
        }
      }
    };
    walk(roots, 0);
    return result;
  }

  _createRow(row, depth) {
    const id = this._idField;
    const gid = row[id];
    const hasChildren = (this._childMap.get(gid) || []).length > 0;
    const isCollapsed = this._collapsed.has(gid);

    const rowEl = document.createElement('div');
    rowEl.className = 'dnt-row';
    rowEl.dataset.gid = gid;
    rowEl.style.paddingLeft = `${6 + depth * 14}px`;

    // indent lines (optional visual, depth guides)
    // (lightweight — just extra left padding, no actual lines needed for clean look)

    // toggle
    const toggleEl = document.createElement('span');
    toggleEl.className = 'dnt-toggle' + (hasChildren ? '' : ' leaf') + (hasChildren && !isCollapsed ? ' open' : '');
    toggleEl.innerHTML = '<svg width="8" height="8" viewBox="0 0 8 8"><polyline points="2,1 6,4 2,7" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg>';
    if (hasChildren) {
      toggleEl.addEventListener('click', e => {
        e.stopPropagation();
        this._toggleCollapse(gid);
      });
    }
    rowEl.appendChild(toggleEl);

    // type badge
    const tf = this._typeField;
    const nt = row[tf] || '';
    const abbr = typeof this._typeAbbr === 'function' ? this._typeAbbr(nt) : (this._typeAbbr[nt] || nt || '—');
    const color = typeof this._typeColor === 'function' ? this._typeColor(nt) : (this._typeColor[nt] || '');
    const badge = document.createElement('span');
    badge.className = 'dnt-type-badge';
    badge.textContent = abbr;
    if (color) {
      badge.style.background = color + '33';
      badge.style.color = color;
    }
    rowEl.appendChild(badge);

    // label
    const labelEl = document.createElement('span');
    labelEl.className = 'dnt-label';
    labelEl.textContent = row[this._labelField] || '(无名称)';
    labelEl.title = row[this._labelField] || '';
    rowEl.appendChild(labelEl);

    // diff badge (only if compare has been run)
    if (this._compareAt && this._diffMap.has(gid)) {
      const { state, diffs } = this._diffMap.get(gid);
      const diffBadge = document.createElement('span');
      diffBadge.className = 'dnt-diff-badge';

      if (state === 'match') {
        diffBadge.textContent = '✓';
        diffBadge.classList.add('dnt-diff-match');
        diffBadge.title = '内容一致';
      } else if (state === 'content_mismatch') {
        diffBadge.textContent = '≠';
        diffBadge.classList.add('dnt-diff-content');
        diffBadge.title = '内容有差异（hover查看详情）';
        diffBadge.addEventListener('mouseenter', e => this._showTooltip(e, diffs, row));
        diffBadge.addEventListener('mouseleave', () => this._hideTooltip());
      } else if (state === 'slot_mismatch') {
        diffBadge.textContent = '!';
        diffBadge.classList.add('dnt-diff-slot');
        const vf = this._vppsField;
        diffBadge.title = `此节点(vpps:${row[vf]||'—'})在「${this._secondaryLabel}」中无对应槽位`;
        diffBadge.addEventListener('mouseenter', e => this._showTooltipText(e, `此节点在「${this._secondaryLabel}」中无对应槽位\nvpps: ${row[vf]||'(无)'}`));
        diffBadge.addEventListener('mouseleave', () => this._hideTooltip());
      }

      rowEl.appendChild(diffBadge);
    }

    // click row → activate
    rowEl.addEventListener('click', () => {
      this._activeId = gid;
      this._applyActiveClass();
      if (this._onActivate) this._onActivate(gid, row);
    });

    return rowEl;
  }

  _createOrphanSection() {
    const section = document.createElement('div');
    section.className = 'dnt-orphan-section' + (this._orphanSectionCollapsed ? ' collapsed' : '');

    const hdr = document.createElement('div');
    hdr.className = 'dnt-orphan-header';

    const hdrLabel = document.createElement('span');
    hdrLabel.textContent = `仅在「${this._secondaryLabel}」中`;
    hdr.appendChild(hdrLabel);

    const countBadge = document.createElement('span');
    countBadge.className = 'dnt-orphan-count';
    countBadge.textContent = this._orphans.length;
    hdr.appendChild(countBadge);

    const toggleIcon = document.createElement('span');
    toggleIcon.className = 'dnt-orphan-toggle-icon';
    toggleIcon.textContent = '▼';
    hdr.appendChild(toggleIcon);

    hdr.addEventListener('click', () => {
      this._orphanSectionCollapsed = !this._orphanSectionCollapsed;
      section.classList.toggle('collapsed', this._orphanSectionCollapsed);
    });
    section.appendChild(hdr);

    const body = document.createElement('div');
    body.className = 'dnt-orphan-body';

    for (const r of this._orphans) {
      const rowEl = document.createElement('div');
      rowEl.className = 'dnt-orphan-row';
      rowEl.title = `此项目在主数据（${this._primaryLabel}）中无对应槽位`;

      const badge = document.createElement('span');
      badge.className = 'dnt-orphan-badge';
      badge.textContent = '!';
      rowEl.appendChild(badge);

      const tf = this._typeField;
      const nt = r[tf] || '';
      const abbr = typeof this._typeAbbr === 'function' ? this._typeAbbr(nt) : (this._typeAbbr[nt] || nt || '—');
      const typeSpan = document.createElement('span');
      typeSpan.className = 'dnt-type-badge';
      typeSpan.textContent = abbr;
      typeSpan.style.cssText = 'font-size:9px;padding:0 3px;margin-right:2px;flex-shrink:0';
      rowEl.appendChild(typeSpan);

      const nameEl = document.createElement('span');
      nameEl.className = 'dnt-orphan-name';
      nameEl.textContent = r[this._labelField] || '(无名称)';
      rowEl.appendChild(nameEl);

      const vf = this._vppsField;
      if (r[vf]) {
        const vppsEl = document.createElement('span');
        vppsEl.className = 'dnt-orphan-vpps';
        vppsEl.textContent = r[vf];
        rowEl.appendChild(vppsEl);
      }

      // click → try to find in primary by vpps
      rowEl.addEventListener('click', () => {
        const vpps = r[vf];
        if (!vpps) return;
        const primaryRow = [...this._rowById.values()].find(pr => pr[vf] === vpps);
        if (primaryRow) {
          const pid = primaryRow[this._idField];
          this._activeId = pid;
          this._ensureVisible(pid);
          this._applyActiveClass();
          this._scrollToActive();
          if (this._onActivate) this._onActivate(pid, primaryRow);
        }
      });

      body.appendChild(rowEl);
    }
    section.appendChild(body);
    return section;
  }

  _applyActiveClass() {
    if (!this._bodyEl) return;
    this._bodyEl.querySelectorAll('.dnt-row.dnt-active').forEach(el => el.classList.remove('dnt-active'));
    if (!this._activeId) return;
    const el = this._bodyEl.querySelector(`.dnt-row[data-gid="${this._activeId}"]`);
    if (el) el.classList.add('dnt-active');
  }

  _scrollToActive() {
    if (!this._bodyEl || !this._activeId) return;
    const el = this._bodyEl.querySelector(`.dnt-row[data-gid="${this._activeId}"]`);
    if (el) el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  // ══════════════════════════════════════════════════════════════
  // 折叠逻辑
  // ══════════════════════════════════════════════════════════════

  _toggleCollapse(gid) {
    if (this._collapsed.has(gid)) {
      this._collapsed.delete(gid);
    } else {
      this._collapsed.add(gid);
    }
    this._renderTree();
  }

  /** 确保节点 gid 可见（展开祖先链） */
  _ensureVisible(gid) {
    if (!gid) return;
    const row = this._rowById.get(gid);
    if (!row) return;
    let cur = row;
    while (cur) {
      const pid = cur[this._parentField];
      if (!pid) break;
      this._collapsed.delete(pid);
      cur = this._rowById.get(pid);
    }
  }

  // ══════════════════════════════════════════════════════════════
  // 比对按钮
  // ══════════════════════════════════════════════════════════════

  async _onCompareClick() {
    if (this._compareRows.length > 0) {
      // already has data → just run
      this.runCompare();
      return;
    }
    if (this._onCompareRequest) {
      this._cmpBtn.classList.add('loading');
      this._cmpBtn.textContent = '加载中…';
      try {
        await this._onCompareRequest();
        this.runCompare();
      } catch (e) {
        console.error('[DiffNavTree] onCompareRequest error:', e);
      } finally {
        this._cmpBtn.classList.remove('loading');
        this._cmpBtn.textContent = '比对';
      }
    } else {
      // no handler, no data
      this._metaLabelsEl.textContent = '无比对数据源';
      this._metaEl.classList.add('visible');
    }
  }

  // ══════════════════════════════════════════════════════════════
  // Tooltip
  // ══════════════════════════════════════════════════════════════

  _showTooltip(e, diffs, row) {
    clearTimeout(this._tooltipHideTimer);
    const el = this._tooltipEl;
    if (!el) return;

    const lines = diffs.map(d => {
      const from = d.from != null ? String(d.from) : '(空)';
      const to   = d.to   != null ? String(d.to)   : '(空)';
      return `<div class="dnt-tooltip-row">
        <span class="dnt-tooltip-key">${d.label||d.key}:</span>
        <span class="dnt-tooltip-from">${_escHtml(from)}</span>
        <span class="dnt-tooltip-arrow"> → </span>
        <span class="dnt-tooltip-to">${_escHtml(to)}</span>
      </div>`;
    });
    el.innerHTML = '<div style="font-weight:600;margin-bottom:4px;font-size:11px">字段差异：</div>' + lines.join('');

    this._positionTooltip(e);
    el.style.display = 'block';

    e.currentTarget?.addEventListener('mousemove', ev => this._positionTooltip(ev));
  }

  _showTooltipText(e, text) {
    clearTimeout(this._tooltipHideTimer);
    const el = this._tooltipEl;
    if (!el) return;
    el.textContent = text;
    this._positionTooltip(e);
    el.style.display = 'block';
  }

  _positionTooltip(e) {
    const el = this._tooltipEl;
    if (!el || el.style.display === 'none') return;
    const x = e.clientX + 12;
    const y = e.clientY + 12;
    el.style.left = Math.min(x, window.innerWidth - 320) + 'px';
    el.style.top  = Math.min(y, window.innerHeight - 200) + 'px';
  }

  _hideTooltip() {
    this._tooltipHideTimer = setTimeout(() => {
      if (this._tooltipEl) this._tooltipEl.style.display = 'none';
    }, 80);
  }

  /** 销毁组件时清理 tooltip DOM */
  destroy() {
    this._tooltipEl?.remove();
    this._tooltipEl = null;
  }
}

// helper: escape html
function _escHtml(str) {
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// 全局导出
if (typeof module !== 'undefined') module.exports = DiffNavTree;
else window.DiffNavTree = DiffNavTree;

