'use strict';

/**
 * ViewManager — 通用视图管理器
 * 支持字段显隐/排序、筛选条件、排序，视图可保存/复制/重命名。
 *
 * 用法：
 *   const vm = new ViewManager({
 *     moduleId: 'craft_table',
 *     listGid: 'abc123',        // 可选：所属清单 gid，为 null 时加载全局模块视图
 *     columns: [
 *       { key: 'code',          label: '工序编号', type: 'text',    width: 120 },
 *       { key: 'standard_time', label: '标准工时', type: 'number',  width: 110 },
 *       { key: 'importance',    label: '重要度',   type: 'enum',    width: 90  },
 *       ...
 *     ],
 *     toolbarEl: document.getElementById('vmToolbar'),
 *     onChange: (viewState) => { renderTable(viewState); }
 *   });
 *   await vm.init();
 *
 * viewState = {
 *   columns: [{ key, label, type, visible, width, order }],  // 仅可见列
 *   filters: [{ id, field, op, value }],
 *   sorts:   [{ field, dir }]
 * }
 */
class ViewManager {
  constructor({ moduleId, listGid, columns, toolbarEl, onChange }) {
    this.moduleId  = moduleId;
    this._listGid  = listGid || null;
    this._colDefs  = columns;
    this._toolbarEl = toolbarEl;
    this._onChange  = onChange || (() => {});

    // Saved views list
    this._views          = [];
    this._activeViewGid  = null;
    this._activeViewName = '默认视图';
    this._isDirty        = false;

    // Working column config — 保留原始列定义所有属性，只 normalize visible / 追加 order
    this._cols = columns.map((c, i) => ({
      ...c,
      visible:       c.visible !== false,
      order:         i,
      alwaysVisible: c.alwaysVisible || false,
    }));

    this._filters       = [];
    this._filterMode    = 'and'; // 'and' | 'or'
    this._sorts         = [];
    this._groupBy       = null;   // field key or null
    this._openPanel     = null;
    this._panelEl       = null;
    this._filterIdCnt   = 0;

    // Tab bar (optional, rendered by renderTabBar())
    this._tabBarEl = null;
  }

  // ─── Init ───────────────────────────────────────────────────

  async init() {
    this._renderToolbar();
    await this._loadViews();
    this._emitChange();
  }

  // ─── Public API ─────────────────────────────────────────────

  /** 返回当前可见列（已按 order 排序） */
  getVisibleColumns() {
    return [...this._cols]
      .filter(c => c.visible)
      .sort((a, b) => a.order - b.order);
  }

  /** 返回当前激活视图的完整 config（含 viewType, treeParentField 等）*/
  getActiveViewConfig() {
    if (!this._activeViewGid) return { viewType: 'grid', treeParentField: null };
    const v = this._views.find(x => x.gid === this._activeViewGid);
    return v?.config || { viewType: 'grid', treeParentField: null };
  }

  /** 对行数据应用筛选 + 分组 + 排序，返回处理后的新数组。
   *  分组时注入 _isGroupHeader 哨兵对象，模块侧 render 需检测并跳过它。 */
  applyView(rows) {
    const filtered = this._applyFilters([...rows]);
    if (!this._groupBy) {
      return this._applySorts(filtered);
    }
    // Group mode: bucket → sort group keys → inject header + sort within group
    const groups = new Map();
    filtered.forEach(row => {
      const val = String(row[this._groupBy] ?? '');
      if (!groups.has(val)) groups.set(val, []);
      groups.get(val).push(row);
    });
    const sortedKeys = [...groups.keys()].sort((a, b) => a.localeCompare(b, 'zh'));
    const col = this._cols.find(c => c.key === this._groupBy);
    const result = [];
    sortedKeys.forEach(key => {
      const groupRows = this._applySorts(groups.get(key));
      result.push({
        _isGroupHeader: true,
        _groupKey:   this._groupBy,
        _groupVal:   key,
        _groupLabel: `${col?.label || this._groupBy}: ${key || '(空)'}`,
        _count:      groupRows.length,
      });
      result.push(...groupRows);
    });
    return result;
  }

  // ─── Toolbar ────────────────────────────────────────────────

  _renderToolbar() {
    // Toolbar buttons removed — controls are in tab right-click context menu
    if (this._toolbarEl) this._toolbarEl.innerHTML = '';
  }

  _togglePanel(name, triggerEl = null) {
    if (this._openPanel === name) { this._closePanel(); return; }
    this._closePanel();
    this._openPanel = name;

    const panel = document.createElement('div');
    panel.className = 'vm-panel';
    panel.style.cssText = 'position:fixed;z-index:9000';
    panel.addEventListener('click', e => e.stopPropagation());

    if      (name === 'views')  this._buildViewsPanel(panel);
    else if (name === 'fields') this._buildFieldsPanel(panel);
    else if (name === 'filter') this._buildFilterPanel(panel);
    else if (name === 'sort')   this._buildSortPanel(panel);
    else if (name === 'group')  this._buildGroupPanel(panel);

    document.body.appendChild(panel);
    this._panelEl = panel;

    // Position below trigger element
    if (triggerEl) {
      const rect    = triggerEl.getBoundingClientRect();
      const panelW  = panel.offsetWidth || 280;
      let   left    = rect.left;
      if (left + panelW > window.innerWidth - 8) left = window.innerWidth - panelW - 8;
      panel.style.left = Math.max(0, left) + 'px';
      panel.style.top  = (rect.bottom + 4) + 'px';
    }

    // Close panel on outside click (registered after current event loop to avoid self-close)
    const _dismiss = (e) => {
      if (this._panelEl && !this._panelEl.contains(e.target)) {
        this._closePanel();
        document.removeEventListener('click', _dismiss);
      }
    };
    setTimeout(() => document.addEventListener('click', _dismiss), 0);
  }

  _closePanel() {
    if (this._panelEl) { this._panelEl.remove(); this._panelEl = null; }
    this._openPanel = null;
  }

  // ─── Views Panel ────────────────────────────────────────────

  _buildViewsPanel(panel) {
    const isDefault = !this._activeViewGid;
    let html = '<div class="vm-panel-title">视图管理</div>';

    html += `<div class="vm-view-item${isDefault ? ' active' : ''}" data-gid="">
      <span class="vm-view-item-name">默认视图</span>
    </div>`;

    this._views.forEach(v => {
      const active = v.gid === this._activeViewGid;
      const sharedIcon = v.is_shared
        ? `<svg width="12" height="12" viewBox="0 0 16 16" style="opacity:.65;flex-shrink:0" title="已共享给团队"><path d="M12 12c0-2.21-1.79-4-4-4S4 9.79 4 12" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round"/><circle cx="8" cy="5" r="2" stroke="currentColor" stroke-width="1.5" fill="none"/></svg>`
        : '';
      html += `<div class="vm-view-item${active ? ' active' : ''}" data-gid="${v.gid}">
        <span class="vm-view-item-name" style="display:flex;align-items:center;gap:4px">${sharedIcon}${_he(v.name)}</span>
        <div class="vm-view-item-btns">
          <button class="vm-icon-btn" data-act="rename" title="重命名">
            <svg width="12" height="12" viewBox="0 0 16 16"><path d="M11.5 2.5l2 2-8 8H3.5v-2l8-8z" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </button>
          <button class="vm-icon-btn" data-act="copy" title="复制">
            <svg width="12" height="12" viewBox="0 0 16 16"><rect x="5" y="5" width="8" height="9" rx="1" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M3 11V3h8" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round"/></svg>
          </button>
          <button class="vm-icon-btn vm-icon-btn-del" data-act="delete" title="删除">
            <svg width="12" height="12" viewBox="0 0 16 16"><path d="M3 5h10M6 5V3h4v2M6 8v5M10 8v5" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round"/></svg>
          </button>
        </div>
      </div>`;
    });

    html += `<div class="vm-panel-footer">
      <button class="app-btn app-btn-sm app-btn-outline" id="vmBtnNewView">+ 新建视图</button>
    </div>`;
    panel.innerHTML = html;

    panel.querySelectorAll('.vm-view-item').forEach(item => {
      item.addEventListener('click', (e) => {
        if (e.target.closest('.vm-icon-btn')) return;
        this._activateView(item.dataset.gid);
        this._closePanel();
      });
    });
    panel.querySelectorAll('[data-act]').forEach(btn => {
      const gid = btn.closest('.vm-view-item').dataset.gid;
      if (btn.dataset.act === 'rename') btn.addEventListener('click', () => this._renameView(gid));
      if (btn.dataset.act === 'copy')   btn.addEventListener('click', () => this._copyView(gid));
      if (btn.dataset.act === 'delete') btn.addEventListener('click', () => this._deleteView(gid));
    });
    const nb = panel.querySelector('#vmBtnNewView');
    if (nb) nb.addEventListener('click', (e) => { e.stopPropagation(); this._newView(); });
  }

  // ─── Fields Panel ────────────────────────────────────────────

  _buildFieldsPanel(panel) {
    const ordered = [...this._cols].sort((a, b) => a.order - b.order);
    let html = '<div class="vm-panel-title">字段显示</div><div class="vm-fields-list">';
    ordered.forEach((col, i) => {
      const dis = col.alwaysVisible ? 'disabled' : '';
      html += `<div class="vm-field-row" data-key="${col.key}">
        <input type="checkbox" id="vmf_${col.key}" class="vm-fld-cb" ${col.visible ? 'checked' : ''} ${dis}/>
        <label for="vmf_${col.key}">${_he(col.label)}</label>
        <div class="vm-field-arrows">
          <button class="vm-icon-btn" data-mv="up"   ${i === 0 ? 'disabled' : ''}>↑</button>
          <button class="vm-icon-btn" data-mv="down" ${i === ordered.length - 1 ? 'disabled' : ''}>↓</button>
        </div>
      </div>`;
    });
    html += '</div>';
    panel.innerHTML = html;

    panel.querySelectorAll('.vm-fld-cb').forEach(cb => {
      cb.addEventListener('change', () => {
        const key = cb.closest('.vm-field-row').dataset.key;
        const col = this._cols.find(c => c.key === key);
        if (col && !col.alwaysVisible) {
          col.visible = cb.checked;
          this._markDirty();
          this._emitChange();
        }
      });
    });

    panel.querySelectorAll('[data-mv]').forEach(btn => {
      btn.addEventListener('click', () => {
        if (btn.disabled) return;
        const key = btn.closest('.vm-field-row').dataset.key;
        this._moveField(key, btn.dataset.mv);
        this._buildFieldsPanel(panel);
      });
    });
  }

  _moveField(key, dir) {
    const sorted = [...this._cols].sort((a, b) => a.order - b.order);
    const idx    = sorted.findIndex(c => c.key === key);
    if (dir === 'up'   && idx > 0)                  { [sorted[idx].order, sorted[idx-1].order] = [sorted[idx-1].order, sorted[idx].order]; }
    if (dir === 'down' && idx < sorted.length - 1)  { [sorted[idx].order, sorted[idx+1].order] = [sorted[idx+1].order, sorted[idx].order]; }
    this._markDirty();
    this._emitChange();
  }

  // ─── Filter Panel ────────────────────────────────────────────

  _buildFilterPanel(panel) {
    const modeAnd = this._filterMode !== 'or';
    let html = `<div class="vm-panel-title">筛选条件</div>
      <div class="vm-filter-mode">
        <span class="vm-filter-mode-label">条件关系</span>
        <div class="vm-filter-mode-btns">
          <button class="vm-mode-btn${modeAnd  ? ' active' : ''}" data-mode="and">且（AND）</button>
          <button class="vm-mode-btn${!modeAnd ? ' active' : ''}" data-mode="or">或（OR）</button>
        </div>
      </div>
      <div class="vm-filter-list" id="vmFilterList">`;
    if (!this._filters.length)
      html += '<div class="vm-empty-tip">暂无筛选，点击下方添加</div>';
    this._filters.forEach(f => { html += this._filterRowHtml(f); });
    html += `</div>
      <div class="vm-panel-footer">
        <button class="app-btn app-btn-sm app-btn-outline" id="vmBtnAddF">+ 添加条件</button>
        ${this._filters.length ? `<button class="app-btn app-btn-sm" id="vmBtnClrF">清除全部</button>` : ''}
      </div>`;
    panel.innerHTML = html;
    this._bindFilterEvents(panel);
  }

  _filterRowHtml(f) {
    const col      = this._cols.find(c => c.key === f.field);
    const fieldOpts = this._cols.map(c =>
      `<option value="${c.key}" ${f.field === c.key ? 'selected' : ''}>${_he(c.label)}</option>`
    ).join('');
    const ops = this._opsForType(col?.type || 'text');
    const opOpts = ops.map(([val, lbl]) =>
      `<option value="${val}" ${f.op === val ? 'selected' : ''}>${lbl}</option>`
    ).join('');
    const noVal = ['empty', 'not_empty'].includes(f.op);
    let valInput = '';
    if (!noVal) {
      valInput = (col?.type === 'boolean')
        ? `<select class="vm-filter-val vm-sel-sm">
            <option value="true"  ${f.value === 'true'  ? 'selected' : ''}>是</option>
            <option value="false" ${f.value === 'false' ? 'selected' : ''}>否</option>
           </select>`
        : `<input class="vm-filter-val vm-inp-sm" type="${col?.type === 'number' ? 'number' : 'text'}"
             value="${_he(f.value || '')}" placeholder="值"/>`;
    }
    return `<div class="vm-filter-row" data-fid="${f.id}">
      <select class="vm-filter-field vm-sel-sm">${fieldOpts}</select>
      <select class="vm-filter-op   vm-sel-sm">${opOpts}</select>
      ${valInput}
      <button class="vm-icon-btn vm-icon-btn-del vm-filter-del" title="删除">×</button>
    </div>`;
  }

  _bindFilterEvents(panel) {
    panel.querySelectorAll('.vm-mode-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        this._filterMode = btn.dataset.mode;
        this._buildFilterPanel(panel);
        this._markDirty(); this._emitChange();
      });
    });
    panel.querySelectorAll('.vm-filter-del').forEach(btn => {
      btn.addEventListener('click', () => {
        const fid = btn.closest('.vm-filter-row').dataset.fid;
        this._filters = this._filters.filter(f => f.id !== fid);
        this._buildFilterPanel(panel);
        this._updateFilterBadge();
        this._markDirty(); this._emitChange();
      });
    });
    panel.querySelectorAll('.vm-filter-field').forEach(sel => {
      sel.addEventListener('change', () => {
        const fid = sel.closest('.vm-filter-row').dataset.fid;
        const f   = this._filters.find(x => x.id === fid);
        if (f) { f.field = sel.value; f.op = this._opsForType(this._colType(sel.value))[0][0]; f.value = ''; }
        this._buildFilterPanel(panel);
        this._markDirty(); this._emitChange();
      });
    });
    panel.querySelectorAll('.vm-filter-op').forEach(sel => {
      sel.addEventListener('change', () => {
        const fid = sel.closest('.vm-filter-row').dataset.fid;
        const f   = this._filters.find(x => x.id === fid);
        if (f) f.op = sel.value;
        this._buildFilterPanel(panel);
        this._markDirty(); this._emitChange();
      });
    });
    panel.querySelectorAll('.vm-filter-val').forEach(inp => {
      inp.addEventListener('input', () => {
        const fid = inp.closest('.vm-filter-row').dataset.fid;
        const f   = this._filters.find(x => x.id === fid);
        if (f) f.value = inp.value;
        this._markDirty(); this._emitChange();
      });
    });
    const addBtn = panel.querySelector('#vmBtnAddF');
    if (addBtn) addBtn.addEventListener('click', () => {
      const firstCol = this._cols[0];
      this._filters.push({
        id: 'f' + (++this._filterIdCnt),
        field: firstCol.key,
        op:    this._opsForType(firstCol.type || 'text')[0][0],
        value: '',
      });
      this._buildFilterPanel(panel);
      this._updateFilterBadge();
      this._markDirty(); this._emitChange();
    });
    const clrBtn = panel.querySelector('#vmBtnClrF');
    if (clrBtn) clrBtn.addEventListener('click', () => {
      this._filters = [];
      this._buildFilterPanel(panel);
      this._updateFilterBadge();
      this._markDirty(); this._emitChange();
    });
  }

  // ─── Sort Panel ──────────────────────────────────────────────

  _buildSortPanel(panel) {
    let html = `<div class="vm-panel-title">排序</div>
      <div class="vm-sort-list" id="vmSortList">`;
    if (!this._sorts.length)
      html += '<div class="vm-empty-tip">暂无排序，点击下方添加</div>';
    this._sorts.forEach((s, i) => {
      const fieldOpts = this._cols.map(c =>
        `<option value="${c.key}" ${s.field === c.key ? 'selected' : ''}>${_he(c.label)}</option>`
      ).join('');
      html += `<div class="vm-sort-row" data-sidx="${i}">
        <select class="vm-sort-field vm-sel-sm">${fieldOpts}</select>
        <select class="vm-sort-dir vm-sel-sm">
          <option value="asc"  ${s.dir === 'asc'  ? 'selected' : ''}>升序</option>
          <option value="desc" ${s.dir === 'desc' ? 'selected' : ''}>降序</option>
        </select>
        <button class="vm-icon-btn vm-icon-btn-del vm-sort-del" data-sidx="${i}" title="删除">×</button>
      </div>`;
    });
    html += `</div>
      <div class="vm-panel-footer">
        <button class="app-btn app-btn-sm app-btn-outline" id="vmBtnAddS">+ 添加排序</button>
        ${this._sorts.length ? `<button class="app-btn app-btn-sm" id="vmBtnClrS">清除</button>` : ''}
      </div>`;
    panel.innerHTML = html;

    panel.querySelectorAll('.vm-sort-field').forEach(sel => {
      sel.addEventListener('change', () => {
        const i = +sel.closest('.vm-sort-row').dataset.sidx;
        this._sorts[i].field = sel.value;
        this._markDirty(); this._emitChange();
      });
    });
    panel.querySelectorAll('.vm-sort-dir').forEach(sel => {
      sel.addEventListener('change', () => {
        const i = +sel.closest('.vm-sort-row').dataset.sidx;
        this._sorts[i].dir = sel.value;
        this._markDirty(); this._emitChange();
      });
    });
    panel.querySelectorAll('.vm-sort-del').forEach(btn => {
      btn.addEventListener('click', () => {
        this._sorts.splice(+btn.dataset.sidx, 1);
        this._buildSortPanel(panel);
        this._updateSortBadge();
        this._markDirty(); this._emitChange();
      });
    });
    const addBtn = panel.querySelector('#vmBtnAddS');
    if (addBtn) addBtn.addEventListener('click', () => {
      const usedFields = new Set(this._sorts.map(s => s.field));
      const nextCol    = this._cols.find(c => !usedFields.has(c.key)) || this._cols[0];
      this._sorts.push({ field: nextCol.key, dir: 'asc' });
      this._buildSortPanel(panel);
      this._updateSortBadge();
      this._markDirty(); this._emitChange();
    });
    const clrBtn = panel.querySelector('#vmBtnClrS');
    if (clrBtn) clrBtn.addEventListener('click', () => {
      this._sorts = [];
      this._buildSortPanel(panel);
      this._updateSortBadge();
      this._markDirty(); this._emitChange();
    });
  }

  // ─── Group Panel ─────────────────────────────────────────────

  _buildGroupPanel(panel) {
    const noGroup = !this._groupBy;
    let html = '<div class="vm-panel-title">分组方式</div><div class="vm-group-list">';
    html += `<div class="vm-view-item${noGroup ? ' active' : ''}" data-gf="">
      <span class="vm-view-item-name">不分组</span>
    </div>`;
    this._cols.forEach(c => {
      const active = this._groupBy === c.key;
      html += `<div class="vm-view-item${active ? ' active' : ''}" data-gf="${c.key}">
        <span class="vm-view-item-name">${_he(c.label)}</span>
      </div>`;
    });
    html += '</div>';
    panel.innerHTML = html;

    panel.querySelectorAll('.vm-view-item[data-gf]').forEach(item => {
      item.addEventListener('click', () => {
        const gf = item.dataset.gf || null;
        this._groupBy = gf;
        this._updateGroupBadge();
        this._markDirty();
        this._emitChange();
        this._closePanel();
      });
    });
  }

  _updateGroupBadge() {
    const el = document.getElementById('vmGroupBadge');
    if (el) { el.classList.toggle('hidden', !this._groupBy); }
    const btn = document.getElementById('vmBtnGroup');
    if (btn) btn.style.color = this._groupBy ? 'var(--app-accent, var(--primary))' : '';
  }

  // ─── Apply view ──────────────────────────────────────────────

  _applyFilters(rows) {
    if (!this._filters.length) return rows;
    const test = (row, f) => {
      const val = row[f.field];
      const v   = String(val ?? '');
      switch (f.op) {
        case 'contains':     return v.toLowerCase().includes(f.value.toLowerCase());
        case 'not_contains': return !v.toLowerCase().includes(f.value.toLowerCase());
        case 'eq':           return v === f.value;
        case 'not_eq':       return v !== f.value;
        case 'empty':        return val == null || val === '';
        case 'not_empty':    return val != null && val !== '';
        case 'gt':           return parseFloat(val) >  parseFloat(f.value);
        case 'gte':          return parseFloat(val) >= parseFloat(f.value);
        case 'lt':           return parseFloat(val) <  parseFloat(f.value);
        case 'lte':          return parseFloat(val) <= parseFloat(f.value);
        default:             return true;
      }
    };
    if (this._filterMode === 'or') {
      return rows.filter(row => this._filters.some(f => test(row, f)));
    }
    return rows.filter(row => this._filters.every(f => test(row, f)));
  }

  _applySorts(rows) {
    if (!this._sorts.length) return rows;
    return [...rows].sort((a, b) => {
      for (const s of this._sorts) {
        const av = a[s.field] ?? '', bv = b[s.field] ?? '';
        let cmp = (typeof av === 'number' || typeof bv === 'number')
          ? (parseFloat(av) || 0) - (parseFloat(bv) || 0)
          : String(av).localeCompare(String(bv), 'zh');
        if (cmp !== 0) return s.dir === 'desc' ? -cmp : cmp;
      }
      return 0;
    });
  }

  // ─── View management ─────────────────────────────────────────

  async _loadViews() {
    // Try API
    try {
      const fn = window.parent?._cloudFetch || window._cloudFetch;
      if (fn) {
        let url = `/api/views?module=${this.moduleId}`;
        if (this._listGid) url += `&list_gid=${encodeURIComponent(this._listGid)}`;
        const res = await fn(url);
        if (res?.data) {
          this._views = res.data;
          this._syncLS();
          return;
        }
      }
    } catch (_) {}
    // Fallback: localStorage
    try {
      const raw = localStorage.getItem(this._lsKey());
      if (raw) this._views = JSON.parse(raw);
    } catch (_) {}
  }

  _activateView(gid) {
    if (!gid) {
      this._activeViewGid  = null;
      this._activeViewName = '默认视图';
      this._isDirty        = false;
      this._resetToDefault();
      this._updateName();
      this._rerenderTabBar();
      this._emitChange();
      return;
    }
    const v = this._views.find(x => x.gid === gid);
    if (!v) return;
    this._activeViewGid  = gid;
    this._activeViewName = v.name;
    this._isDirty        = false;
    this._applyConfig(v.config || {});
    this._updateName();
    this._rerenderTabBar();
    this._emitChange();
  }

  _applyConfig(cfg) {
    if (cfg.columns) {
      cfg.columns.forEach(cc => {
        const col = this._cols.find(c => c.key === cc.key);
        if (col) {
          col.visible = cc.visible !== false;
          if (cc.order !== undefined) col.order = cc.order;
          if (cc.width)               col.width = cc.width;
        }
      });
    }
    this._filters        = cfg.filters    ? [...cfg.filters]    : [];
    this._filterMode     = cfg.filterMode || 'and';
    this._sorts          = cfg.sorts      ? [...cfg.sorts]      : [];
    this._groupBy        = cfg.groupBy    || null;
    this._treeParentField = cfg.treeParentField || null;
    this._updateFilterBadge();
    this._updateSortBadge();
    this._updateGroupBadge();
  }

  _resetToDefault() {
    this._cols = this._colDefs.map((c, i) => ({
      ...c,
      visible:       c.visible !== false,
      order:         i,
      alwaysVisible: c.alwaysVisible || false,
    }));
    this._filters         = [];
    this._filterMode      = 'and';
    this._sorts           = [];
    this._groupBy         = null;
    this._treeParentField = null;
    this._updateFilterBadge();
    this._updateSortBadge();
    this._updateGroupBadge();
    this._updateSaveBtn();
  }

  async _saveCurrentView(directOpts = null) {
    let name, isShared = false;
    if (this._activeViewGid) {
      name = this._activeViewName;
    } else if (directOpts) {
      name     = directOpts.name || '默认视图';
      isShared = directOpts.isShared || false;
    } else {
      // Show inline dialog for name + shared option
      const result = await this._promptSaveView();
      if (!result) return;
      name     = result.name;
      isShared = result.isShared;
    }

    // Preserve viewType / treeParentField from existing view config so a re-save doesn't strip them
    const existingConfig = this._activeViewGid
      ? (this._views.find(x => x.gid === this._activeViewGid)?.config || {})
      : {};
    const config = {
      columns:         this._cols.map(c => ({ key: c.key, visible: c.visible, order: c.order, width: c.width })),
      filters:         [...this._filters],
      filterMode:      this._filterMode,
      sorts:           [...this._sorts],
      groupBy:         this._groupBy || null,
      viewType:        existingConfig.viewType || 'grid',
      treeParentField: existingConfig.treeParentField || null,
    };

    // Try API
    try {
      const fn = window.parent?._cloudFetch || window._cloudFetch;
      if (fn) {
        if (this._activeViewGid && !this._activeViewGid.startsWith('local_')) {
          await fn(`/api/views/${this._activeViewGid}`, {
            method: 'PATCH', body: JSON.stringify({ name, config }),
          });
          const v = this._views.find(x => x.gid === this._activeViewGid);
          if (v) { v.name = name; v.config = config; }
        } else {
          const res = await fn('/api/views', {
            method: 'POST', body: JSON.stringify({ name, module: this.moduleId, list_gid: this._listGid, config, is_shared: isShared }),
          });
          if (res?.data?.gid) {
            // Replace local ID with server ID
            if (this._activeViewGid) {
              const old = this._views.find(x => x.gid === this._activeViewGid);
              if (old) { old.gid = res.data.gid; old.is_shared = isShared; }
            } else {
              this._views.push({ gid: res.data.gid, name, config, is_shared: isShared });
            }
            this._activeViewGid = res.data.gid;
          }
        }
        this._activeViewName = name;
        this._isDirty        = false;
        this._syncLS();
        this._updateName();
        this._updateSaveBtn();
        return;
      }
    } catch (_) {}

    // Local fallback
    if (!this._activeViewGid) {
      const newGid = 'local_' + Date.now();
      this._views.push({ gid: newGid, name, config });
      this._activeViewGid = newGid;
    } else {
      const v = this._views.find(x => x.gid === this._activeViewGid);
      if (v) { v.name = name; v.config = config; }
    }
    this._activeViewName = name;
    this._isDirty        = false;
    this._syncLS();
    this._updateName();
    this._updateSaveBtn();
  }

  async _newView() {
    const result = await this._promptNewView();
    if (!result) return;
    const { name, viewType, treeParentField } = result;
    const config = {
      columns:         this._cols.map(c => ({ key: c.key, visible: c.visible, order: c.order, width: c.width })),
      filters:         [...this._filters],
      filterMode:      this._filterMode,
      sorts:           [...this._sorts],
      groupBy:         this._groupBy || null,
      viewType:        viewType || 'grid',
      treeParentField: treeParentField || null,
    };
    let gid = 'local_' + Date.now();
    try {
      const fn = window.parent?._cloudFetch || window._cloudFetch;
      if (fn) {
        const res = await fn('/api/views', {
          method: 'POST', body: JSON.stringify({ name, module: this.moduleId, list_gid: this._listGid, config }),
        });
        if (res?.data?.gid) gid = res.data.gid;
      }
    } catch (_) {}
    this._views.push({ gid, name, config });
    this._activeViewGid  = gid;
    this._activeViewName = name;
    this._isDirty        = false;
    this._syncLS();
    this._updateName();
    this._updateSaveBtn();
    this._rerenderTabBar();
    this._closePanel();
  }

  /** 新建视图对话框：name + viewType + 字段/筛选/排序/分组配置 */
  _promptNewView() {
    // Snapshot current state for cancel restoration
    const _snap = {
      filters: JSON.parse(JSON.stringify(this._filters)),
      filterMode: this._filterMode,
      sorts: JSON.parse(JSON.stringify(this._sorts)),
      groupBy: this._groupBy,
      cols: this._cols.map(c => ({ ...c })),
    };

    return new Promise(resolve => {
      const colOpts = this._cols.map(c =>
        `<option value="${_he(c.key)}">${_he(c.label)}</option>`
      ).join('');
      const _S = (tag, style, html = '') => `<${tag} style="${style}">${html}</${tag}>`;

      const overlay = document.createElement('div');
      overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:9998;display:flex;align-items:flex-start;justify-content:center;padding-top:60px;overflow-y:auto';
      overlay.innerHTML = `
        <div style="background:var(--bg-secondary,#181825);border:1px solid var(--border-default,#313244);border-radius:10px;padding:20px 24px;min-width:340px;max-width:420px;width:100%;margin-bottom:40px">
          <div style="font-size:14px;font-weight:600;margin-bottom:14px;color:var(--text-normal,#cdd6f4)">新建视图</div>

          <label style="font-size:12px;color:var(--text-muted,#a6adc8);display:block;margin-bottom:4px">视图名称</label>
          <input id="_vnName" type="text" value="新视图"
            style="width:100%;box-sizing:border-box;padding:6px 10px;border:1px solid var(--border-default,#313244);border-radius:6px;background:var(--bg-surface,#24273a);color:var(--text-normal,#cdd6f4);font-size:13px;outline:none;margin-bottom:12px"/>

          <label style="font-size:12px;color:var(--text-muted,#a6adc8);display:block;margin-bottom:4px">视图类型</label>
          <select id="_vnType"
            style="width:100%;padding:6px 10px;border:1px solid var(--border-default,#313244);border-radius:6px;background:var(--bg-surface,#24273a);color:var(--text-normal,#cdd6f4);font-size:13px;margin-bottom:12px">
            <option value="grid">表格</option>
            <option value="gantt">甘特图</option>
            <option value="tree">树形</option>
            <option value="card" disabled style="color:var(--text-faint,#6c7086)">卡片（暂未实现）</option>
            <option value="report" disabled style="color:var(--text-faint,#6c7086)">报表（暂未实现）</option>
          </select>

          <div id="_vnTreeRow" style="display:none;margin-bottom:12px">
            <label style="font-size:12px;color:var(--text-muted,#a6adc8);display:block;margin-bottom:4px">父级指针字段</label>
            <select id="_vnParentField"
              style="width:100%;padding:6px 10px;border:1px solid var(--border-default,#313244);border-radius:6px;background:var(--bg-surface,#24273a);color:var(--text-normal,#cdd6f4);font-size:13px">
              ${colOpts}
            </select>
          </div>

          <!-- Collapsible config sections -->
          <div id="_vnSections" style="border-top:1px solid var(--border-default,#313244);margin-top:4px;padding-top:8px;display:flex;flex-direction:column;gap:2px">

            <div class="_vn-sec" data-sec="fields">
              <div class="_vn-sec-hdr" style="display:flex;align-items:center;justify-content:space-between;padding:5px 6px;border-radius:4px;cursor:pointer;font-size:12px;color:var(--text-muted,#a6adc8);user-select:none">
                <span>字段显示</span>
                <span class="_vn-chevron" style="font-size:10px;transition:transform .15s">▶</span>
              </div>
              <div class="_vn-sec-body" style="display:none;padding:0 4px 8px"></div>
            </div>

            <div class="_vn-sec" data-sec="filter">
              <div class="_vn-sec-hdr" style="display:flex;align-items:center;justify-content:space-between;padding:5px 6px;border-radius:4px;cursor:pointer;font-size:12px;color:var(--text-muted,#a6adc8);user-select:none">
                <span>筛选条件 <span class="_vn-filter-cnt" style="display:none;background:var(--color-accent,#89b4fa);color:var(--bg-primary,#1e1e2e);border-radius:10px;padding:0 5px;font-size:10px;margin-left:4px"></span></span>
                <span class="_vn-chevron" style="font-size:10px;transition:transform .15s">▶</span>
              </div>
              <div class="_vn-sec-body" style="display:none;padding:0 4px 8px"></div>
            </div>

            <div class="_vn-sec" data-sec="sort">
              <div class="_vn-sec-hdr" style="display:flex;align-items:center;justify-content:space-between;padding:5px 6px;border-radius:4px;cursor:pointer;font-size:12px;color:var(--text-muted,#a6adc8);user-select:none">
                <span>排序 <span class="_vn-sort-cnt" style="display:none;background:var(--color-accent,#89b4fa);color:var(--bg-primary,#1e1e2e);border-radius:10px;padding:0 5px;font-size:10px;margin-left:4px"></span></span>
                <span class="_vn-chevron" style="font-size:10px;transition:transform .15s">▶</span>
              </div>
              <div class="_vn-sec-body" style="display:none;padding:0 4px 8px"></div>
            </div>

            <div class="_vn-sec" data-sec="group">
              <div class="_vn-sec-hdr" style="display:flex;align-items:center;justify-content:space-between;padding:5px 6px;border-radius:4px;cursor:pointer;font-size:12px;color:var(--text-muted,#a6adc8);user-select:none">
                <span>分组</span>
                <span class="_vn-chevron" style="font-size:10px;transition:transform .15s">▶</span>
              </div>
              <div class="_vn-sec-body" style="display:none;padding:0 4px 8px"></div>
            </div>

          </div>

          <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:14px">
            <button id="_vnCancel" style="padding:5px 16px;border:1px solid var(--border-default,#313244);border-radius:6px;background:transparent;color:var(--text-muted,#a6adc8);font-size:12px;cursor:pointer">取消</button>
            <button id="_vnConfirm" style="padding:5px 16px;border:none;border-radius:6px;background:var(--color-accent,#89b4fa);color:var(--bg-primary,#1e1e2e);font-size:12px;font-weight:600;cursor:pointer">创建</button>
          </div>
        </div>
      `;
      document.body.appendChild(overlay);

      const nameEl        = overlay.querySelector('#_vnName');
      const typeEl        = overlay.querySelector('#_vnType');
      const treeRow       = overlay.querySelector('#_vnTreeRow');
      const parentFieldEl = overlay.querySelector('#_vnParentField');

      nameEl.focus(); nameEl.select();

      typeEl.addEventListener('change', () => {
        treeRow.style.display = typeEl.value === 'tree' ? '' : 'none';
      });

      // — Collapsible sections —
      const _rebuildSection = (sec) => {
        const body = sec.querySelector('._vn-sec-body');
        const name = sec.dataset.sec;
        if (name === 'fields') this._buildFieldsPanel(body);
        else if (name === 'filter') { this._buildFilterPanel(body); _updateCounts(); }
        else if (name === 'sort')   { this._buildSortPanel(body);   _updateCounts(); }
        else if (name === 'group')  this._buildGroupPanel(body);
      };
      const _updateCounts = () => {
        const fc = overlay.querySelector('._vn-filter-cnt');
        if (fc) { fc.textContent = this._filters.length; fc.style.display = this._filters.length ? '' : 'none'; }
        const sc = overlay.querySelector('._vn-sort-cnt');
        if (sc) { sc.textContent = this._sorts.length; sc.style.display = this._sorts.length ? '' : 'none'; }
      };

      // Patch panel builders to update counts and re-render sections on change
      const _origMark = this._markDirty.bind(this);
      this._markDirty = () => { _origMark(); _updateCounts(); };

      overlay.querySelectorAll('._vn-sec').forEach(sec => {
        const hdr     = sec.querySelector('._vn-sec-hdr');
        const body    = sec.querySelector('._vn-sec-body');
        const chevron = sec.querySelector('._vn-chevron');
        hdr.addEventListener('mouseenter', () => { hdr.style.background = 'rgba(255,255,255,.04)'; });
        hdr.addEventListener('mouseleave', () => { hdr.style.background = ''; });
        hdr.addEventListener('click', () => {
          const open = body.style.display !== 'none';
          body.style.display = open ? 'none' : '';
          chevron.style.transform = open ? '' : 'rotate(90deg)';
          if (!open) _rebuildSection(sec);
        });
      });

      const _restore = () => {
        this._markDirty = _origMark;
        this._filters    = _snap.filters;
        this._filterMode = _snap.filterMode;
        this._sorts      = _snap.sorts;
        this._groupBy    = _snap.groupBy;
        this._cols.forEach((c, i) => {
          const s = _snap.cols[i];
          if (s) { c.visible = s.visible; c.order = s.order; }
        });
        this._emitChange();
      };

      const confirm = () => {
        const name = nameEl.value.trim();
        if (!name) return;
        this._markDirty = _origMark;
        const viewType        = typeEl.value;
        const treeParentField = viewType === 'tree' ? parentFieldEl.value : null;
        overlay.remove();
        resolve({ name, viewType, treeParentField });
      };

      overlay.querySelector('#_vnConfirm').addEventListener('click', confirm);
      overlay.querySelector('#_vnCancel').addEventListener('click', () => {
        _restore();
        overlay.remove();
        resolve(null);
      });
      nameEl.addEventListener('keydown', e => {
        if (e.key === 'Enter') confirm();
        if (e.key === 'Escape') { _restore(); overlay.remove(); resolve(null); }
      });
    });
  }

  // ─── 模态辅助（替代 prompt / confirm，Electron renderer 不支持原生弹窗）────────

  _vmPromptText(title, defaultVal = '') {
    return new Promise(resolve => {
      const overlay = document.createElement('div');
      overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:9999;display:flex;align-items:center;justify-content:center';
      overlay.innerHTML = `
        <div style="background:var(--bg-secondary,#181825);border:1px solid var(--border-default,#313244);border-radius:10px;padding:20px 24px;min-width:280px;max-width:360px">
          <div style="font-size:13px;font-weight:600;margin-bottom:12px;color:var(--text-normal,#cdd6f4)">${_he(title)}</div>
          <input id="_vmpInput" type="text" value="${_he(defaultVal)}"
            style="width:100%;box-sizing:border-box;padding:6px 10px;border:1px solid var(--border-default,#313244);border-radius:6px;background:var(--bg-surface,#24273a);color:var(--text-normal,#cdd6f4);font-size:13px;outline:none;margin-bottom:14px"/>
          <div style="display:flex;justify-content:flex-end;gap:8px">
            <button id="_vmpCancel" style="padding:4px 14px;border:1px solid var(--border-default,#313244);border-radius:6px;background:transparent;color:var(--text-muted,#a6adc8);font-size:12px;cursor:pointer">取消</button>
            <button id="_vmpOk" style="padding:4px 14px;border:none;border-radius:6px;background:var(--color-accent,#89b4fa);color:var(--bg-primary,#1e1e2e);font-size:12px;font-weight:600;cursor:pointer">确认</button>
          </div>
        </div>`;
      document.body.appendChild(overlay);
      const inp = overlay.querySelector('#_vmpInput');
      inp.focus(); inp.select();
      const ok = () => { const v = inp.value.trim(); overlay.remove(); resolve(v || null); };
      const cancel = () => { overlay.remove(); resolve(null); };
      overlay.querySelector('#_vmpOk').addEventListener('click', ok);
      overlay.querySelector('#_vmpCancel').addEventListener('click', cancel);
      inp.addEventListener('keydown', e => { if (e.key === 'Enter') ok(); if (e.key === 'Escape') cancel(); });
    });
  }

  _vmConfirm(msg) {
    return new Promise(resolve => {
      const overlay = document.createElement('div');
      overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:9999;display:flex;align-items:center;justify-content:center';
      overlay.innerHTML = `
        <div style="background:var(--bg-secondary,#181825);border:1px solid var(--border-default,#313244);border-radius:10px;padding:20px 24px;min-width:260px;max-width:340px">
          <div style="font-size:13px;color:var(--text-normal,#cdd6f4);margin-bottom:16px;line-height:1.5">${_he(msg)}</div>
          <div style="display:flex;justify-content:flex-end;gap:8px">
            <button id="_vmcCancel" style="padding:4px 14px;border:1px solid var(--border-default,#313244);border-radius:6px;background:transparent;color:var(--text-muted,#a6adc8);font-size:12px;cursor:pointer">取消</button>
            <button id="_vmcOk" style="padding:4px 14px;border:none;border-radius:6px;background:#f38ba8;color:#1e1e2e;font-size:12px;font-weight:600;cursor:pointer">确认</button>
          </div>
        </div>`;
      document.body.appendChild(overlay);
      overlay.querySelector('#_vmcOk').addEventListener('click', () => { overlay.remove(); resolve(true); });
      overlay.querySelector('#_vmcCancel').addEventListener('click', () => { overlay.remove(); resolve(false); });
    });
  }

  // ─────────────────────────────────────────────────────────────────────────────

  _renameView(gid) {
    const v = this._views.find(x => x.gid === gid);
    if (!v) return;
    this._vmPromptText('重命名视图', v.name).then(name => {
      if (!name || name === v.name) return;
      v.name = name;
      if (this._activeViewGid === gid) {
        this._activeViewName = name;
        this._updateName();
      }
      this._syncLS();
      this._apiPatch(gid, { name });
      this._rerenderTabBar();
      this._closePanel();
    });
  }

  _copyView(gid) {
    const v = this._views.find(x => x.gid === gid);
    if (!v) return;
    const copyGid = 'local_' + Date.now();
    const copyName = v.name + ' - 副本';
    const copy     = { gid: copyGid, name: copyName, config: JSON.parse(JSON.stringify(v.config || {})) };
    this._views.push(copy);
    this._syncLS();
    // try to persist on server
    (async () => {
      try {
        const fn = window.parent?._cloudFetch || window._cloudFetch;
        if (fn && !gid.startsWith('local_')) {
          const res = await fn(`/api/views/${gid}/copy`, { method: 'POST' });
          if (res?.data?.gid) { copy.gid = res.data.gid; this._syncLS(); }
        }
      } catch (_) {}
    })();
    this._closePanel();
  }

  async _deleteView(gid) {
    const ok = await this._vmConfirm('确认删除此视图？');
    if (!ok) return;
    this._views = this._views.filter(v => v.gid !== gid);
    if (this._activeViewGid === gid) {
      this._activeViewGid  = null;
      this._activeViewName = '默认视图';
      this._resetToDefault();
      this._updateName();
      this._emitChange();
    }
    this._syncLS();
    this._rerenderTabBar();
    try {
      const fn = window.parent?._cloudFetch || window._cloudFetch;
      if (fn && !gid.startsWith('local_'))
        await fn(`/api/views/${gid}`, { method: 'DELETE' });
    } catch (_) {}
    this._closePanel();
  }

  async _apiPatch(gid, body) {
    try {
      const fn = window.parent?._cloudFetch || window._cloudFetch;
      if (fn && !gid.startsWith('local_'))
        await fn(`/api/views/${gid}`, { method: 'PATCH', body: JSON.stringify(body) });
    } catch (_) {}
  }

  /** 新视图保存对话框（name + 共享给团队 checkbox） */
  _promptSaveView() {
    return new Promise(resolve => {
      const overlay = document.createElement('div');
      overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:9998;display:flex;align-items:center;justify-content:center';
      overlay.innerHTML = `
        <div style="background:var(--bg-secondary,#181825);border:1px solid var(--border-default,#313244);border-radius:10px;padding:20px 24px;min-width:280px;max-width:360px">
          <div style="font-size:14px;font-weight:600;margin-bottom:14px;color:var(--text-normal,#cdd6f4)">保存视图</div>
          <label style="font-size:12px;color:var(--text-muted,#a6adc8);display:block;margin-bottom:4px">视图名称</label>
          <input id="_vmSaveName" type="text" value="新视图" style="width:100%;padding:6px 10px;border:1px solid var(--border-default,#313244);border-radius:6px;background:var(--bg-surface,#24273a);color:var(--text-normal,#cdd6f4);font-size:13px;outline:none;margin-bottom:12px"/>
          <label style="display:flex;align-items:center;gap:8px;font-size:12px;color:var(--text-muted,#a6adc8);cursor:pointer;margin-bottom:16px">
            <input type="checkbox" id="_vmShareCb" style="width:14px;height:14px;cursor:pointer"/>
            共享给团队（其他成员可见此视图）
          </label>
          <div style="display:flex;justify-content:flex-end;gap:8px">
            <button id="_vmSaveCancel" style="padding:5px 16px;border:1px solid var(--border-default,#313244);border-radius:6px;background:transparent;color:var(--text-muted,#a6adc8);font-size:12px;cursor:pointer">取消</button>
            <button id="_vmSaveConfirm" style="padding:5px 16px;border:none;border-radius:6px;background:var(--color-accent,#89b4fa);color:var(--bg-primary,#1e1e2e);font-size:12px;font-weight:600;cursor:pointer">保存</button>
          </div>
        </div>
      `;
      document.body.appendChild(overlay);
      const nameEl = overlay.querySelector('#_vmSaveName');
      nameEl.focus();
      nameEl.select();
      const confirm = () => {
        const name = nameEl.value.trim();
        if (!name) return;
        const isShared = overlay.querySelector('#_vmShareCb').checked;
        overlay.remove();
        resolve({ name, isShared });
      };
      overlay.querySelector('#_vmSaveConfirm').addEventListener('click', confirm);
      overlay.querySelector('#_vmSaveCancel').addEventListener('click', () => { overlay.remove(); resolve(null); });
      nameEl.addEventListener('keydown', e => { if (e.key === 'Enter') confirm(); if (e.key === 'Escape') { overlay.remove(); resolve(null); } });
    });
  }

  // ─── Helpers ─────────────────────────────────────────────────

  _opsForType(type) {
    if (type === 'number')  return [['eq','='],['not_eq','≠'],['gt','>'],['gte','≥'],['lt','<'],['lte','≤']];
    if (type === 'boolean') return [['eq','等于']];
    if (type === 'enum')    return [['eq','等于'],['not_eq','不等于']];
    return [['contains','包含'],['not_contains','不包含'],['eq','等于'],['not_eq','不等于'],['empty','为空'],['not_empty','不为空']];
  }

  _colType(key) { return this._cols.find(c => c.key === key)?.type || 'text'; }

  _markDirty() {
    this._isDirty = true;
    this._updateSaveBtn();
    if (this._spRefreshBadges) this._spRefreshBadges();
  }

  _updateName() {
    if (!this._tabBarEl) return;
    const activeTab = this._tabBarEl.querySelector('.ls-view-tab.active span:last-child');
    if (activeTab) activeTab.textContent = this._activeViewName + (this._isDirty ? ' *' : '');
  }

  _updateSaveBtn() {
    this._updateName();
  }

  _updateFilterBadge() {
    const el = document.getElementById('vmFilterBadge');
    if (el) { el.textContent = this._filters.length; el.classList.toggle('hidden', !this._filters.length); }
  }

  _updateSortBadge() {
    const el = document.getElementById('vmSortBadge');
    if (el) { el.textContent = this._sorts.length; el.classList.toggle('hidden', !this._sorts.length); }
  }

  _syncLS() {
    try { localStorage.setItem(this._lsKey(), JSON.stringify(this._views)); } catch (_) {}
  }

  _lsKey() {
    return `vm_views_${this.moduleId}_${this._listGid || 'global'}`;
  }

  // ─── 公开快捷操作（供列表头右键菜单调用）────────────────────────────────────

  /** 切换某列可见性 */
  setColVisible(key, visible) {
    const col = this._cols.find(c => c.key === key);
    if (!col) return;
    col.visible = visible;
    this._markDirty();
    this._emitChange();
  }

  /** 切换某字段排序（无→asc→desc→无） */
  toggleSort(key) {
    const existing = this._sorts.find(s => s.field === key);
    if (!existing) {
      this._sorts.push({ field: key, dir: 'asc' });
    } else if (existing.dir === 'asc') {
      existing.dir = 'desc';
    } else {
      this._sorts = this._sorts.filter(s => s.field !== key);
    }
    this._updateSortBadge();
    this._markDirty();
    this._emitChange();
  }

  /** 设置分组字段（传 null 取消分组） */
  setGroup(key) {
    this._groupBy = key || null;
    this._updateGroupBadge();
    this._markDirty();
    this._emitChange();
  }

  /** 打开筛选面板，并为指定字段追加一条筛选规则 */
  openFilterPanel(key) {
    const col = this._cols.find(c => c.key === key);
    if (col) {
      this._filters.push({
        id:    'f' + (++this._filterIdCnt),
        field: col.key,
        op:    this._opsForType(col.type || 'text')[0][0],
        value: '',
      });
      this._updateFilterBadge();
      this._markDirty();
    }
    this._togglePanel('filter');
  }

  // ─────────────────────────────────────────────────────────────────────────────

  /** 切换到新清单，重新加载该清单的视图并重置到默认视图 */
  async setListGid(gid) {
    this._listGid = gid || null;
    this._activateView(null);
    this._views = [];
    await this._loadViews();
    this._rerenderTabBar();
    this._closePanel();
    this._emitChange();
  }

  _emitChange() {
    this._onChange({
      columns:         this.getVisibleColumns(),
      filters:         [...this._filters],
      sorts:           [...this._sorts],
      viewType:        this.getActiveViewConfig().viewType || 'grid',
      treeParentField: this.getActiveViewConfig().treeParentField || null,
    });
  }

  // ─── Tab Bar ─────────────────────────────────────────────────

  /** 在 containerEl 中渲染视图标签栏（可选调用，与现有 toolbar 共存）*/
  renderTabBar(containerEl) {
    this._tabBarEl = containerEl;
    this._rerenderTabBar();
  }

  _rerenderTabBar() {
    if (!this._tabBarEl) return;
    const el = this._tabBarEl;
    el.innerHTML = '';

    const gridIcon   = `<svg class="ls-tab-type-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="3" y1="15" x2="21" y2="15"/><line x1="9" y1="3" x2="9" y2="21"/></svg>`;
    const ganttIcon  = `<svg class="ls-tab-type-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="6" x2="15" y2="6"/><line x1="3" y1="12" x2="20" y2="12"/><line x1="3" y1="18" x2="12" y2="18"/></svg>`;
    const cardIcon   = `<svg class="ls-tab-type-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="5" width="20" height="14" rx="2"/><line x1="2" y1="10" x2="22" y2="10"/></svg>`;
    const reportIcon = `<svg class="ls-tab-type-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 20V10M12 20V4M6 20v-6"/></svg>`;
    const treeIcon   = `<svg class="ls-tab-type-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="6" y1="4" x2="6" y2="20"/><polyline points="6 8 12 8"/><polyline points="6 14 16 14"/><polyline points="6 20 10 20"/></svg>`;

    const _makeTab = (gid, name, viewType, isActive) => {
      const tab = document.createElement('div');
      tab.className = 'ls-view-tab' + (isActive ? ' active' : '');
      tab.dataset.gid = gid;
      const iconMap = { gantt: ganttIcon, card: cardIcon, report: reportIcon, tree: treeIcon };
      const icon = iconMap[viewType] || gridIcon;
      const displayName = isActive && this._isDirty ? name + ' *' : name;
      tab.innerHTML = `${icon}<span>${_he(displayName)}</span>`;
      tab.addEventListener('click', (e) => {
        if (e.target.closest('.ls-tab-ctx-btn')) return;
        this._activateView(gid);
        this._closePanel();
      });
      // Right-click → persistent settings panel
      tab.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        this._showViewSettingsPanel(tab, gid, name);
      });
      return tab;
    };

    // Default view tab
    el.appendChild(_makeTab('', '默认视图', 'grid', !this._activeViewGid));

    // Named views
    this._views.forEach(v => {
      const viewType = v.config?.viewType || 'grid';
      el.appendChild(_makeTab(v.gid, v.name, viewType, v.gid === this._activeViewGid));
    });

    // "+" add button
    const addBtn = document.createElement('button');
    addBtn.className = 'ls-tab-add-btn';
    addBtn.title = '新建视图';
    addBtn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>`;
    addBtn.addEventListener('click', (e) => { e.stopPropagation(); this._newView(); });
    el.appendChild(addBtn);

    // Save button — always visible, highlighted when dirty
    const saveBtn = document.createElement('button');
    saveBtn.className = 'ls-tab-save-btn' + (this._isDirty ? ' dirty' : '');
    saveBtn.title = this._isDirty ? '视图有未保存改动，点击保存' : '保存当前视图';
    saveBtn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg><span>保存</span>`;
    saveBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      // Skip name prompt — use current active view name directly
      const opts = this._activeViewGid ? null : { name: this._activeViewName || '默认视图', isShared: false };
      this._saveCurrentView(opts);
    });
    el.appendChild(saveBtn);
  }

  // ─── View Settings Panel（右键 tab → 持久化设置面板）────────

  _showViewSettingsPanel(tabEl, gid, name) {
    this._closeViewSettingsPanel();

    // Snapshot current state so Cancel can restore
    const snap = {
      cols:       this._cols.map(c => ({ ...c })),
      filters:    JSON.parse(JSON.stringify(this._filters)),
      filterMode: this._filterMode,
      sorts:      JSON.parse(JSON.stringify(this._sorts)),
      groupBy:    this._groupBy,
      isDirty:    this._isDirty,
    };

    const panel = document.createElement('div');
    panel.className = 'vm-sp';

    // ── Header ──────────────────────────────────────────────────
    const hdr = document.createElement('div');
    hdr.className = 'vm-sp-hdr';
    const titleEl = document.createElement('span');
    titleEl.className = 'vm-sp-title';
    titleEl.textContent = name || '默认视图';
    hdr.appendChild(titleEl);

    if (gid) {
      const acts = document.createElement('div');
      acts.className = 'vm-sp-hdr-acts';
      const _ab = (ttl, svg, fn, danger = false) => {
        const b = document.createElement('button');
        b.className = 'vm-icon-btn' + (danger ? ' vm-icon-btn-del' : '');
        b.title = ttl;
        b.innerHTML = svg;
        b.addEventListener('click', () => { this._closeViewSettingsPanel(); fn(); });
        return b;
      };
      acts.appendChild(_ab('重命名',
        `<svg width="13" height="13" viewBox="0 0 16 16"><path d="M11.5 2.5l2 2-8 8H3.5v-2l8-8z" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
        () => this._renameView(gid)));
      acts.appendChild(_ab('复制',
        `<svg width="13" height="13" viewBox="0 0 16 16"><rect x="5" y="5" width="8" height="9" rx="1" stroke="currentColor" stroke-width="1.5" fill="none"/><path d="M3 11V3h8" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round"/></svg>`,
        () => this._copyView(gid)));
      acts.appendChild(_ab('删除',
        `<svg width="13" height="13" viewBox="0 0 16 16"><path d="M3 5h10M6 5V3h4v2M6 8v5M10 8v5" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round"/></svg>`,
        () => this._deleteView(gid), true));
      hdr.appendChild(acts);
    }

    const closeX = document.createElement('button');
    closeX.className = 'vm-icon-btn';
    closeX.title = '取消并关闭';
    closeX.innerHTML = `<svg width="13" height="13" viewBox="0 0 16 16"><line x1="3" y1="3" x2="13" y2="13" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><line x1="13" y1="3" x2="3" y2="13" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>`;
    closeX.addEventListener('click', () => this._cancelViewSettings(snap));
    hdr.appendChild(closeX);
    panel.appendChild(hdr);

    // ── Sub-tab nav ──────────────────────────────────────────────
    const subTabs = [
      { key: 'fields', label: '字段',  badge: () => 0 },
      { key: 'filter', label: '筛选',  badge: () => this._filters.length },
      { key: 'sort',   label: '排序',  badge: () => this._sorts.length },
      { key: 'group',  label: '分组',  badge: () => this._groupBy ? 1 : 0 },
    ];

    const nav     = document.createElement('div');
    nav.className = 'vm-sp-nav';
    const content = document.createElement('div');
    content.className = 'vm-sp-body';

    const _refreshBadges = () => {
      nav.querySelectorAll('.vm-sp-tab').forEach(tb => {
        const st = subTabs.find(s => s.key === tb.dataset.key);
        if (!st) return;
        const n = st.badge();
        let badge = tb.querySelector('.vm-sp-badge');
        if (n) {
          if (!badge) { badge = document.createElement('span'); badge.className = 'vm-sp-badge'; tb.appendChild(badge); }
          badge.textContent = n;
        } else if (badge) {
          badge.remove();
        }
      });
    };
    this._spRefreshBadges = _refreshBadges;

    const _switchSubTab = (key) => {
      nav.querySelectorAll('.vm-sp-tab').forEach(tb => tb.classList.toggle('active', tb.dataset.key === key));
      content.innerHTML = '';
      if      (key === 'fields') this._buildFieldsPanel(content);
      else if (key === 'filter') this._buildFilterPanel(content);
      else if (key === 'sort')   this._buildSortPanel(content);
      else if (key === 'group')  this._buildGroupPanel(content);
    };

    subTabs.forEach(st => {
      const tb = document.createElement('button');
      tb.className = 'vm-sp-tab';
      tb.dataset.key = st.key;
      tb.textContent = st.label;
      const n = st.badge();
      if (n) {
        const b = document.createElement('span');
        b.className = 'vm-sp-badge';
        b.textContent = n;
        tb.appendChild(b);
      }
      tb.addEventListener('click', () => _switchSubTab(st.key));
      nav.appendChild(tb);
    });

    panel.appendChild(nav);
    panel.appendChild(content);
    _switchSubTab('fields');  // open on 字段 by default

    // ── Footer ──────────────────────────────────────────────────
    const footer = document.createElement('div');
    footer.className = 'vm-sp-footer';

    const cancelBtn = document.createElement('button');
    cancelBtn.className = 'vm-sp-btn vm-sp-btn-cancel';
    cancelBtn.textContent = '取消';
    cancelBtn.addEventListener('click', () => this._cancelViewSettings(snap));

    const saveBtn = document.createElement('button');
    saveBtn.className = 'vm-sp-btn vm-sp-btn-save';
    saveBtn.textContent = '保存视图';
    saveBtn.addEventListener('click', async () => {
      // If on default view (no gid), skip the name prompt and use current name directly
      const opts = gid ? null : { name: name || '默认视图', isShared: false };
      await this._saveCurrentView(opts);
      this._closeViewSettingsPanel();
    });

    footer.appendChild(cancelBtn);
    footer.appendChild(saveBtn);
    panel.appendChild(footer);

    // ── Position below the right-clicked tab ────────────────────
    document.body.appendChild(panel);
    this._settingsPanelEl = panel;

    const rect   = tabEl.getBoundingClientRect();
    const panelW = panel.offsetWidth || 320;
    let   left   = rect.left;
    if (left + panelW > window.innerWidth - 8) left = window.innerWidth - panelW - 8;
    panel.style.left = Math.max(0, left) + 'px';
    panel.style.top  = (rect.bottom + 4) + 'px';
  }

  _cancelViewSettings(snap) {
    this._cols       = snap.cols;
    this._filters    = snap.filters;
    this._filterMode = snap.filterMode;
    this._sorts      = snap.sorts;
    this._groupBy    = snap.groupBy;
    this._isDirty    = snap.isDirty;
    this._closeViewSettingsPanel();
    this._updateName();
    this._emitChange();
  }

  _closeViewSettingsPanel() {
    if (this._settingsPanelEl) { this._settingsPanelEl.remove(); this._settingsPanelEl = null; }
    this._spRefreshBadges = null;
  }

  // ─── Tab context menu（保留，目前仅内部使用）─────────────────
  _showTabCtxMenu(tabEl, gid, name) {
    document.querySelectorAll('.ls-tab-ctx-menu').forEach(m => m.remove());
    this._closePanel();

    const menu = document.createElement('div');
    menu.className = 'ls-tab-ctx-menu';
    menu.style.cssText = 'position:fixed;background:var(--bg-surface,#24273a);border:1px solid var(--border-default,#313244);border-radius:6px;padding:4px;z-index:9999;min-width:140px;box-shadow:0 4px 16px rgba(0,0,0,.4)';

    const _item = (html, action, danger = false) => {
      const btn = document.createElement('button');
      btn.style.cssText = `display:flex;align-items:center;justify-content:space-between;gap:8px;width:100%;padding:5px 10px;background:transparent;border:none;border-radius:4px;font-size:12px;cursor:pointer;color:${danger ? 'var(--color-danger,#f38ba8)' : 'var(--text-normal,#cdd6f4)'};text-align:left`;
      btn.innerHTML = html;
      btn.addEventListener('mouseenter', () => { btn.style.background = 'rgba(255,255,255,.06)'; });
      btn.addEventListener('mouseleave', () => { btn.style.background = 'transparent'; });
      btn.addEventListener('click', () => { menu.remove(); action(); });
      return btn;
    };
    const _sep = () => {
      const d = document.createElement('div');
      d.style.cssText = 'height:1px;background:var(--border-default,#313244);margin:3px 0';
      return d;
    };
    const _badge = (n) => n ? `<span style="background:var(--color-accent,#89b4fa);color:var(--bg-primary,#1e1e2e);border-radius:10px;padding:0 5px;font-size:10px;font-weight:600">${n}</span>` : '';

    // — View controls (always shown) —
    menu.appendChild(_item('字段', () => this._togglePanel('fields', tabEl)));
    menu.appendChild(_item(`筛选${_badge(this._filters.length)}`, () => this._togglePanel('filter', tabEl)));
    menu.appendChild(_item(`排序${_badge(this._sorts.length)}`, () => this._togglePanel('sort', tabEl)));
    menu.appendChild(_item(`分组${_badge(this._groupBy ? 1 : 0)}`, () => this._togglePanel('group', tabEl)));
    menu.appendChild(_item('保存视图', () => this._saveCurrentView()));

    // — Per-view actions (non-default views only) —
    if (gid) {
      menu.appendChild(_sep());
      menu.appendChild(_item('重命名', () => this._renameView(gid)));
      menu.appendChild(_item('复制',   () => this._copyView(gid)));
      menu.appendChild(_item('删除',   () => this._deleteView(gid), true));
    }

    const rect = tabEl.getBoundingClientRect();
    menu.style.left = rect.left + 'px';
    menu.style.top  = (rect.bottom + 4) + 'px';
    document.body.appendChild(menu);

    const _dismiss = (e) => {
      if (!menu.contains(e.target)) { menu.remove(); document.removeEventListener('click', _dismiss); }
    };
    setTimeout(() => document.addEventListener('click', _dismiss), 0);
  }
}

// Module-level HTML escape helper
function _he(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

