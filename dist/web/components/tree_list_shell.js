'use strict';

// 分类渲染自动配色表（暗/亮色均可辨识）
const _TLS_CAT_PALETTE = [
  '#89b4fa', '#a6e3a1', '#fab387', '#cba6f7',
  '#94e2d5', '#f9e2af', '#89dceb', '#eba0ac',
  '#b4befe', '#f38ba8', '#a6d189', '#e5c890',
];

/**
 * TreeListShell — 树形清单通用组件
 *
 * 布局：类型+清单下拉 -> 工具栏 -> 树形表格 -> 状态栏
 * 提供字段右键菜单（排序/筛选/分组）、折叠/展开、分组/父级切换、
 * 字段配置、视图管理、右键详情面板（只读/可编辑）。
 *
 * 用法：
 *   const tls = new TreeListShell({
 *     mountEl,
 *     title: '目标 PBOM',
 *     itemTypes: [{ value:'pbom', label:'PBOM' }],
 *     forcedItemType: 'pbom',
 *     onLoadLists: async (itemType) => [{ gid, name }, ...],
 *     onLoadData:  async (itemType, listGid) => rows[],
 *     parentField: 'parent_vpps',
 *     columns:     [...],
 *     allColumns:  [...],
 *     detailMode:  'readonly',
 *     detailFields: ['field1', ...],
 *     onSave:       null,
 *     extraToolbarBtns: [...],
 *     groupField:   'component_type',
 *     moduleId:     'pbom_target',
 *     listGid:      null,
 *   });
 *   await tls.init();
 */
class TreeListShell {
  constructor(opts = {}) {
    this._mountEl          = opts.mountEl;
    this._title            = opts.title            || '';
    this._itemTypes        = opts.itemTypes        || [];
    this._forcedItemType   = opts.forcedItemType   || null;
    this._onLoadLists      = opts.onLoadLists      || null;
    this._onLoadData       = opts.onLoadData       || null;
    this._optsParentField  = opts.parentField      || 'parent_bom_row';
    this._columns          = opts.columns          || [];
    this._allColumns       = opts.allColumns       || opts.columns || [];
    // 可选列优先排序（默认不排序；PBOM 等传 priorityKeys 保持原有顺序）
    const priorityKeys = opts.priorityKeys || [];
    if (priorityKeys.length) {
      this._allColumns = [
        ...priorityKeys.map(k => this._allColumns.find(c => c.key === k)).filter(Boolean),
        ...this._allColumns.filter(c => !priorityKeys.includes(c.key)),
      ];
      this._columns = [
        ...priorityKeys.map(k => this._columns.find(c => c.key === k)).filter(Boolean),
        ...this._columns.filter(c => !priorityKeys.includes(c.key)),
      ];
    }
    this._detailMode       = opts.detailMode       || 'readonly';
    this._detailFields     = opts.detailFields     || [];
    this._onSave           = opts.onSave           || null;
    this._extraToolbarBtns = opts.extraToolbarBtns || [];
    this._optsGroupField   = opts.groupField       || 'component_type';
    this._moduleId         = opts.moduleId         || '';
    this._listGid          = opts.listGid          || null;
    this._cellRenderer     = opts.cellRenderer     || {};
    this._showListSelector = opts.showListSelector !== false; // 默认显示，传 false 隐藏
    this._rowContextMenu   = opts.rowContextMenu   || null;  // fn(row)=>items[] 或 items[]
    this._rowTitle         = opts.rowTitle         || null;  // fn(row)=>string
    this._rowActions       = opts.rowActions       || null;  // fn(row)=>string|Element，行尾操作容器
    this._onRowClick       = opts.onRowClick       || null;  // fn(row, e)，优先于内置 editable 左键
    this._moreMenuItems    = opts.moreMenuItems    || [];    // [{label, icon?, onClick(anchorEl)}] 固定追加到 more 菜单
    this._compactToolbar   = opts.compactToolbar   || false; // 精简工具栏：仅保留 collapse/group/search/views/more
    this._onViewChange     = opts.onViewChange     || null;  // fn(viewName) 视图切换时回调
    this._allowNewEntry    = opts.allowNewEntry    || false; // 显示新建条目按钮
    this._onCreateEntry    = opts.onCreateEntry    || null;  // async (data) => any，data 含 list_gid
    this._pageSize         = opts.pageSize !== undefined ? opts.pageSize : 0; // 0 = 全部
    this._currentPage      = 0;
    this._categoryField    = opts.categoryField    || null;  // 按哪个字段着色
    this._categoryColors   = opts.categoryColors   || {};   // { value: '#color' }
    this._catColorMap      = new Map();                     // 自动配色缓存
    this._autoFitCols      = opts.autoFitColumns   || false; // 宽度自适应列显示
    this._userAdjustedCols = false;                          // 用户手动调整过列，暂停自适应

    // State
    this._rows           = [];
    this._lists          = [];
    this._selectedType   = this._forcedItemType || (this._itemTypes[0]?.value || '');
    this._selectedListGid = this._listGid;
    this._collapseState  = new Set();
    this._searchText     = '';
    this._fieldConfig    = {
      parentField: this._optsParentField,
      groupMode: 'parent',
      groupField: this._optsGroupField,
      fields: (this._allColumns || this._columns || []).filter(c => c.defaultOn !== false).map(c => c.key),
    };

    // Sub-components (public)
    this.vm = null;

    // DOM refs (private, set in _render)
    this._typeSelectEl   = null;
    this._listSelectEl   = null;
    this._titleEl        = null;
    this._colBodyEl      = null;
    this._colFooterEl    = null;
    this._colStatEl      = null;
    this._searchBarEl    = null;
    this._searchInpEl    = null;
    this._searchClearEl  = null;
    this._collapseBtnEl  = null;
    this._groupBtnEl     = null;
    this._extraBtnsEl    = null;
    this._vmToolbarEl    = null;
    this._moreBtnEl      = null;
    this._toolbarEl      = null;
    this._newEntryBtnEl  = null;
    this._nepEl          = null;   // new-entry popover DOM node
    this._nepOutsideClick = null;  // outside-click handler reference
    this._pageBarEl      = null;
    this._pagePrevEl     = null;
    this._pageNextEl     = null;
    this._pageInfoEl     = null;
    this._pageSzEl       = null;

    // Floating panel singletons (per-instance)
    this._activePanel     = null;
    this._activeFieldMenu = null;
    this._activeMoreMenu  = null;

    // Tree cache — invalidated when rows/search/grouping change; reused on collapse/expand
    this._treeCache     = null;
    this._treeCacheKey  = null;
    this._dataVersion   = 0;

    // Debounced refresh
    this._debouncedRefresh = _tlsDebounce(() => this._renderTree(), 200);

    this._uid = '_tls_' + (++TreeListShell._nextId);
  }

  static _nextId = 0;

  // ==========================================================================
  //  Public API
  // ==========================================================================

  async init() {
    this._render();
    this._bindEvents();
    this._renderExtraButtons();
    await this._initViewManager();
    if (this._forcedItemType) {
      await this._loadLists();
    } else if (this._selectedType) {
      await this._loadLists();
    }
    if (this._lists.length && !this._selectedListGid) {
      await this._selectList(this._lists[0].gid);
    } else if (this._selectedListGid) {
      await this._loadData();
    }
    // 宽度自适应：监听容器尺寸变化，自动显示/隐藏列
    if (this._autoFitCols && window.ResizeObserver) {
      let _lastW = 0;
      this._resizeObs = new ResizeObserver(entries => {
        const w = Math.floor(entries[0]?.contentRect?.width || 0);
        if (Math.abs(w - _lastW) < 20) return;
        _lastW = w;
        if (!this._userAdjustedCols) this._autoFitColumns(w);
      });
      this._resizeObs.observe(this._mountEl);
    }
    document.addEventListener('mousedown', (e) => {
      if (!this._activePanel?.contains(e.target) &&
          !this._activePanel?.contains(document.activeElement) &&
          !this._activeFieldMenu?.contains(e.target) &&
          !this._activeMoreMenu?.contains(e.target)) {
        this._closeAllFloatMenus();
      }
    });
  }

  async refresh() { await this._loadData(); }

  /** 仅刷新清单下拉选项，不重新加载数据 */
  async refreshItems() { await this._loadLists(); }

  async setSelectedType(itemType) {
    if (this._forcedItemType) return;
    this._selectedType = itemType;
    if (this._typeSelectEl) this._typeSelectEl.value = itemType;
    this._selectedListGid = null;
    this._syncNewEntryBtn();
    await this._loadLists();
  }

  async setSelectedList(listGid) { await this._selectList(listGid); }

  getSelectedType() { return this._selectedType; }
  getSelectedList() { return this._selectedListGid; }
  getRows() { return this._rows; }

  /** 从外部（如 moreMenuItems）触发字段配置面板 */
  openFieldConfig(anchorEl) { this._openConfigPanel(anchorEl); }

  updateExtraButtons(btns) {
    this._extraToolbarBtns = btns;
    this._renderExtraButtons();
  }

  // ==========================================================================
  //  Layout
  // ==========================================================================

  _render() {
    const m = this._mountEl;
    const isForced = !!this._forcedItemType;
    const typeOpts = this._itemTypes.map(t =>
      `<option value="${_tlsHe(t.value)}"${t.value === this._selectedType ? ' selected' : ''}>${_tlsHe(t.label)}</option>`
    ).join('');

    m.innerHTML = `
      <div class="tls-root">
        <div class="col-header">
          ${isForced
            ? `<span class="col-title" id="${this._uid}_title">${_tlsHe(this._title)}</span>`
            : `<div class="col-selector-wrap"><select class="col-select tls-type-select" id="${this._uid}_typesel">${typeOpts}</select></div>`
          }
          <div class="col-selector-wrap"><select class="col-select tls-list-select" id="${this._uid}_listsel"><option value="">选择清单</option></select></div>
          <div class="col-toolbar" id="${this._uid}_toolbar">
            <button class="col-btn" id="${this._uid}_collapse" title="全部折叠">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="8" y1="12" x2="16" y2="12"/></svg>
            </button>
            ${this._allowNewEntry && this._onCreateEntry ? `
            <button class="col-btn tls-new-entry-btn" id="${this._uid}_newentry" title="新建条目">
              <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="8" y1="2" x2="8" y2="14"/><line x1="2" y1="8" x2="14" y2="8"/></svg>
              <span>新建</span>
            </button>` : ''}
            <button class="col-btn" id="${this._uid}_group" title="切换分组显示">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
            </button>
            <button class="col-btn" id="${this._uid}_searchbtn" title="搜索">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            </button>
            <button class="col-btn" id="${this._uid}_config" title="字段设置">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="21" y1="4" x2="14" y2="4"/><line x1="10" y1="4" x2="3" y2="4"/><line x1="21" y1="12" x2="12" y2="12"/><line x1="8" y1="12" x2="3" y2="12"/><line x1="21" y1="20" x2="16" y2="20"/><line x1="12" y1="20" x2="3" y2="20"/><circle cx="12" cy="4" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="16" cy="20" r="2"/></svg>
            </button>
            <div class="col-separator"></div>
            <div class="tls-extra-btns" id="${this._uid}_extra"></div>
          </div>
          <button class="col-btn col-btn-more hidden" id="${this._uid}_more" title="更多">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
          </button>
        </div>
        <div class="col-search-bar hidden" id="${this._uid}_searchbar">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;color:var(--text-muted)"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input type="text" class="col-search-inp" id="${this._uid}_searchinp" placeholder="">
          <button class="col-search-clear hidden" id="${this._uid}_searchclear" title="清除">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div class="tls-vm-toolbar" id="${this._uid}_vmtoolbar"></div>
        <div class="col-body" id="${this._uid}_body"><div class="col-empty">请在左侧选择清单</div></div>
        <div class="col-footer" id="${this._uid}_footer">
          <span class="col-stat" id="${this._uid}_stat">0 条</span>
          <div class="tls-page-bar" id="${this._uid}_pagebar">
            <button class="tls-page-btn" id="${this._uid}_pprev" title="上一页">‹</button>
            <span class="tls-page-info" id="${this._uid}_pinfo"></span>
            <button class="tls-page-btn" id="${this._uid}_pnext" title="下一页">›</button>
            <div class="tls-page-size-wrap">
              <span class="tls-page-size-label">每页</span>
              <select class="col-select tls-page-size-sel" id="${this._uid}_psz">
                <option value="0">全部</option>
                <option value="200">200</option>
                <option value="500">500</option>
                <option value="1000">1000</option>
              </select>
            </div>
          </div>
        </div>
      </div>`;

    this._typeSelectEl  = document.getElementById(`${this._uid}_typesel`);
    this._listSelectEl  = document.getElementById(`${this._uid}_listsel`);
    if (!this._showListSelector) {
      this._listSelectEl.closest('.col-selector-wrap').style.display = 'none';
    }
    this._titleEl       = document.getElementById(`${this._uid}_title`);
    this._colBodyEl     = document.getElementById(`${this._uid}_body`);
    this._colFooterEl   = document.getElementById(`${this._uid}_footer`);
    this._colStatEl     = document.getElementById(`${this._uid}_stat`);
    this._searchBarEl   = document.getElementById(`${this._uid}_searchbar`);
    this._searchInpEl   = document.getElementById(`${this._uid}_searchinp`);
    this._searchClearEl = document.getElementById(`${this._uid}_searchclear`);
    this._collapseBtnEl = document.getElementById(`${this._uid}_collapse`);
    this._groupBtnEl    = document.getElementById(`${this._uid}_group`);
    this._newEntryBtnEl = document.getElementById(`${this._uid}_newentry`) || null;
    this._extraBtnsEl   = document.getElementById(`${this._uid}_extra`);
    this._vmToolbarEl   = document.getElementById(`${this._uid}_vmtoolbar`);
    this._moreBtnEl     = document.getElementById(`${this._uid}_more`);
    this._toolbarEl     = document.getElementById(`${this._uid}_toolbar`);
    this._pageBarEl     = document.getElementById(`${this._uid}_pagebar`);
    this._pagePrevEl    = document.getElementById(`${this._uid}_pprev`);
    this._pageNextEl    = document.getElementById(`${this._uid}_pnext`);
    this._pageInfoEl    = document.getElementById(`${this._uid}_pinfo`);
    this._pageSzEl      = document.getElementById(`${this._uid}_psz`);
    if (this._pageSize) this._pageSzEl.value = String(this._pageSize);

    // 精简工具栏：隐藏分隔符、extra 区和更多按钮；collapse/group/search/config/views 全部保留
    if (this._compactToolbar) {
      this._toolbarEl.querySelector('.col-separator').style.display = 'none';
      this._extraBtnsEl.style.display = 'none';
      this._moreBtnEl.style.display   = 'none';
    }
  }

  // ==========================================================================
  //  Events
  // ==========================================================================

  _bindEvents() {
    // Type select
    if (this._typeSelectEl) {
      this._typeSelectEl.addEventListener('change', async () => {
        this._selectedType = this._typeSelectEl.value;
        this._selectedListGid = null;
        this._rows = [];
        this._colBodyEl.innerHTML = '<div class="col-empty">请在左侧选择清单</div>';
        this._colStatEl.textContent = '0 条';
        await this._loadLists();
      });
    }

    // List select
    this._listSelectEl.addEventListener('change', async () => {
      const gid = this._listSelectEl.value;
      if (gid) await this._selectList(gid);
      else {
        this._rows = [];
        this._colBodyEl.innerHTML = '<div class="col-empty">请在左侧选择清单</div>';
        this._colStatEl.textContent = '0 条';
      }
    });

    // Collapse toggle
    this._collapseBtnEl.addEventListener('click', () => this._toggleCollapse());

    // New entry
    if (this._newEntryBtnEl) {
      this._newEntryBtnEl.addEventListener('click', () => this._showNewEntryPopover(this._newEntryBtnEl));
    }

    // Group mode toggle
    this._groupBtnEl.addEventListener('click', () => {
      const cfg = this._fieldConfig;
      cfg.groupMode = cfg.groupMode === 'group' ? 'parent' : 'group';
      if (!cfg.groupField) cfg.groupField = this._optsGroupField;
      // 切换到分组模式时同步 VM groupBy
      if (cfg.groupMode === 'group' && this.vm) {
        this.vm.setGroup(cfg.groupField);
      } else if (cfg.groupMode === 'parent' && this.vm) {
        this.vm.setGroup(null);
      }
      this._collapseState.clear();
      this._updateGroupBtn();
      this._renderTree();
    });

    // Config panel
    const self = this;
    document.getElementById(`${this._uid}_config`).addEventListener('click', e => {
      e.stopPropagation();
      self._openConfigPanel(e.currentTarget);
    });

    // Search
    const searchBtn = document.getElementById(`${this._uid}_searchbtn`);
    searchBtn.addEventListener('click', () => {
      const opening = self._searchBarEl.classList.toggle('hidden');
      searchBtn.classList.toggle('col-btn-active', !opening);
      if (!opening) self._searchInpEl.focus();
    });
    this._searchInpEl.addEventListener('input', () => {
      self._searchText = self._searchInpEl.value;
      self._searchClearEl.classList.toggle('hidden', !self._searchText);
      self._debouncedRefresh();
    });
    this._searchClearEl.addEventListener('click', () => {
      self._searchInpEl.value = '';
      self._searchText = '';
      self._searchClearEl.classList.add('hidden');
      self._renderTree();
      self._searchInpEl.focus();
    });

    // Overflow menu
    this._initOverflowMenu();

    // Pagination
    const self2 = this;
    this._pagePrevEl.addEventListener('click', () => {
      if (self2._currentPage > 0) { self2._currentPage--; self2._renderTree(); }
    });
    this._pageNextEl.addEventListener('click', () => {
      if (self2._currentPage < self2._lastTotalPages - 1) { self2._currentPage++; self2._renderTree(); }
    });
    this._pageSzEl.addEventListener('change', () => {
      self2._pageSize = parseInt(self2._pageSzEl.value) || 0;
      self2._currentPage = 0;
      self2._renderTree();
    });

    // Close floating menus on body scroll
    this._colBodyEl.addEventListener('scroll', () => this._closeAllFloatMenus());
  }

  // ==========================================================================
  //  Data Loading
  // ==========================================================================

  async _loadLists() {
    if (!this._onLoadLists) return;
    this._listSelectEl.innerHTML = '<option value="">加载中…</option>';
    try {
      this._lists = await this._onLoadLists(this._selectedType);
      this._renderListOptions();
    } catch (e) {
      this._listSelectEl.innerHTML = '<option value="">加载失败</option>';
    }
  }

  _renderListOptions() {
    this._listSelectEl.innerHTML = '<option value="">选择清单</option>';
    this._lists.forEach(l => {
      this._listSelectEl.appendChild(_tlsOpt(l.gid, l.name || l.gid));
    });
    if (this._selectedListGid) this._listSelectEl.value = this._selectedListGid;
  }

  async _selectList(gid) {
    this._selectedListGid = gid;
    this._listSelectEl.value = gid;
    if (this.vm) {
      try { await this.vm.setListGid(gid); } catch (_) {}
    }
    await this._loadData();
  }

  async _loadData() {
    if (!this._onLoadData || !this._selectedListGid) return;
    this._colBodyEl.innerHTML = '<div class="col-empty">加载中…</div>';
    this._collapseState.clear();
    this._currentPage = 0;
    this._searchText = '';
    if (this._searchInpEl) this._searchInpEl.value = '';
    if (this._searchClearEl) this._searchClearEl.classList.add('hidden');
    try {
      this._rows = await this._onLoadData(this._selectedType, this._selectedListGid);
      this._dataVersion++;
      this._treeCache = null;
      this._treeCacheKey = null;
      this._collapseToFirstLevel();
      this._renderTree();
    } catch (e) {
      this._colBodyEl.innerHTML = `<div class="col-empty">加载失败: ${_tlsHe(e.message)}</div>`;
      this._colStatEl.textContent = '0 条';
    }
  }

  /** 折叠所有有子节点的一级节点，使初始只展示第一层 */
  _collapseToFirstLevel() {
    this._collapseState.clear();
    const tree = this._buildTreeForSide(this._rows);
    tree.roots.forEach(r => {
      const key = this._nodeKey(r);
      if ((tree.childrenMap.get(key) || []).length > 0) {
        this._collapseState.add(key);
      }
    });
  }

  // ==========================================================================
  //  Auto-Fit Columns (ResizeObserver)
  // ==========================================================================

  /** 根据容器宽度自动决定显示哪些列（不写 localStorage，不覆盖用户手动设置）*/
  _autoFitColumns(containerW) {
    const all = this._allColumns;
    if (!all?.length) return;
    const TITLE_MIN = 80;  // 标题列最小宽度
    const COL_PAD   = 10;  // 每列左右 padding 估算
    const TREE_W    = 28;  // 树形缩进列宽
    let budget = containerW - TREE_W;
    const fields = [];
    for (const col of all) {
      if (!col.width) {
        // 弹性列（标题）：占 TITLE_MIN，一定放入
        fields.push(col.key);
        budget -= TITLE_MIN;
      } else if (budget >= col.width + COL_PAD) {
        fields.push(col.key);
        budget -= col.width + COL_PAD;
      }
    }
    if (!fields.length) return;
    const cur  = (this._fieldConfig.fields || []).join(',');
    const next = fields.join(',');
    if (cur === next) return;
    this._fieldConfig.fields = fields;
    this._renderTree();
  }

  // ==========================================================================
  //  Tree Building
  // ==========================================================================

  _nodeKey(p) {
    return ((p.vpps || p.component_id || p.part_no || p.gid) || '').trim();
  }

  _buildTree(parts, parentField) {
    if (parentField === 'level') return this._buildTreeByLevel(parts);

    if (parentField === 'parent_bom_row') {
      const byBomRow = new Map();
      parts.forEach(p => {
        if (p.bom_row) byBomRow.set(p.bom_row.trim(), p);
        if (p.bom_row_label) byBomRow.set(p.bom_row_label.trim(), p);
      });
      const roots = [];
      const childrenMap = new Map();
      parts.forEach(p => {
        const pr = (p.parent_bom_row || '').trim();
        const parent = pr ? byBomRow.get(pr) : null;
        if (parent && parent !== p) {
          const pk = this._nodeKey(parent);
          if (!childrenMap.has(pk)) childrenMap.set(pk, []);
          childrenMap.get(pk).push(p);
        } else {
          roots.push(p);
        }
      });
      return { roots, childrenMap };
    }

    // gid-based mode: parentField 值直接作为行上的字段名，节点用 gid 唯一标识
    // 适用于 parent_gid、parent_section_gid 等所有以 _gid 结尾的父字段
    if (parentField && (parentField === 'parent_gid' || parentField.endsWith('_gid'))) {
      const byGid = new Map();
      parts.forEach(p => { if (p.gid) byGid.set(p.gid, p); });
      const roots = [];
      const childrenMap = new Map();
      parts.forEach(p => {
        const pg = p[parentField] || null;
        const parent = pg ? byGid.get(pg) : null;
        if (parent && parent !== p) {
          const pk = this._nodeKey(parent); // 与 _flattenVisible/_collapseToFirstLevel 保持一致
          if (!childrenMap.has(pk)) childrenMap.set(pk, []);
          childrenMap.get(pk).push(p);
        } else {
          roots.push(p);
        }
      });
      // 如果有 sort_order 字段，对每层子节点排序
      childrenMap.forEach(children => children.sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0)));
      roots.sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));
      return { roots, childrenMap };
    }

    const byVpps = new Map();
    parts.forEach(p => { if (p.vpps) byVpps.set(p.vpps.trim(), p); });

    const roots = [];
    const childrenMap = new Map();
    let anyParent = false;

    parts.forEach(p => {
      const pv = (p.parent_vpps || '').trim();
      const parent = pv ? byVpps.get(pv) : null;
      if (parent && parent !== p) {
        anyParent = true;
        const pk = this._nodeKey(parent);
        if (!childrenMap.has(pk)) childrenMap.set(pk, []);
        childrenMap.get(pk).push(p);
      } else {
        roots.push(p);
      }
    });

    if (!anyParent && parts.some(p => (parseInt(p.level) || 1) > 1)) {
      return this._buildTreeByLevel(parts);
    }
    return { roots, childrenMap };
  }

  _buildTreeByLevel(parts) {
    const roots = [];
    const childrenMap = new Map();
    const stack = [];

    parts.forEach(p => {
      const lv = parseInt(p.level) || 1;
      while (stack.length && stack[stack.length - 1].level >= lv) stack.pop();
      if (!stack.length) {
        roots.push(p);
      } else {
        const pk = this._nodeKey(stack[stack.length - 1].part);
        if (!childrenMap.has(pk)) childrenMap.set(pk, []);
        childrenMap.get(pk).push(p);
      }
      stack.push({ part: p, level: lv });
    });

    return { roots, childrenMap };
  }

  _wrapWithGroups(parts, groupField) {
    const groupMap = new Map();
    parts.forEach(p => {
      const gv = ((p[groupField] ?? '') + '').trim() || '未分类';
      if (!groupMap.has(gv)) groupMap.set(gv, []);
      groupMap.get(gv).push(p);
    });

    const roots = [];
    const childrenMap = new Map();

    const sortedGroups = [...groupMap.entries()].sort(([a], [b]) => {
      if (a === '未分类') return 1;
      if (b === '未分类') return -1;
      return a.localeCompare(b, 'zh-CN');
    });

    for (const [gv, children] of sortedGroups) {
      const gid = `_grp_${gv}`;
      roots.push({
        _isGroup: true,
        _groupValue: gv,
        _groupCount: children.length,
        name: gv,
        gid,
      });
      childrenMap.set(gid, children);
    }

    return { roots, childrenMap };
  }

  _buildTreeForSide(parts) {
    const cfg = this._fieldConfig;
    if (cfg.groupMode === 'group' && cfg.groupField) {
      return this._wrapWithGroups(parts, cfg.groupField);
    }
    return this._buildTree(parts, cfg.parentField);
  }

  _flattenVisible(tree) {
    const collapsed = this._collapseState;
    const result = [];
    const self = this;
    function walk(p, depth, ancestors) {
      const key = self._nodeKey(p);
      const children = tree.childrenMap.get(key) || [];
      const hasChildren = children.length > 0;
      const isCollapsed = collapsed.has(key);
      result.push({ part: p, depth, hasChildren, isCollapsed, key, ancestors });
      if (!isCollapsed) children.forEach(c => walk(c, depth + 1, [...ancestors, key]));
    }
    tree.roots.forEach(r => walk(r, 0, []));
    return result;
  }

  // ==========================================================================
  //  Tree Rendering
  // ==========================================================================

  _getDisplayParts() {
    let parts = [...this._rows];

    // 本地全局搜索（独立于 VM 筛选）
    const q = this._searchText;
    if (q) {
      const ql = q.toLowerCase();
      parts = parts.filter(p =>
        (p.name || '').toLowerCase().includes(ql) ||
        (p.component_id || '').toLowerCase().includes(ql) ||
        (p.vpps || '').toLowerCase().includes(ql) ||
        (p.part_no || '').toLowerCase().includes(ql)
      );
    }

    // VM 筛选 + 排序（不使用 applyView 以避免 VM 分组干扰 TLS 分组模式）
    if (this.vm) {
      parts = this.vm._applyFilters(parts);
      parts = this.vm._applySorts(parts);
    }
    return parts;
  }

  _makeFieldHeader() {
    const cfg = this._fieldConfig;
    const allFields = this._allColumns;
    const div = document.createElement('div');
    div.className = 'part-row pr-col-header';

    const fieldKeys = this._visibleFieldKeys || (cfg.fields || []);

    // 从 VM 读取排序/筛选/分组状态
    const sorts = this.vm?._sorts || [];
    const filters = this.vm?._filters || [];
    const groupBy = this.vm?._groupBy || null;

    let html = `<span class="pr-tree-cell pr-tree-cell-hdr"></span>`;
    fieldKeys.forEach((key, idx) => {
      const def = allFields.find(f => f.key === key);
      const w = (def?.width && key !== 'name')
        ? ` style="width:${def.width}px;min-width:${def.width}px"`
        : '';
      const sortObj = sorts.find(s => s.field === key);
      const sortMark = sortObj ? `<small class="pr-sort-ind">${sortObj.dir === 'asc' ? '↑' : '↓'}</small>` : '';
      const isFiltered = filters.some(f => f.field === key);
      const isGrouped = cfg.groupMode === 'group' && groupBy === key;
      const filterMark = isFiltered ? `<small class="pr-filter-ind" title="已设置筛选">▽</small>` : '';
      const groupMark = isGrouped ? `<small class="pr-group-ind" title="按此字段分组"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg></small>` : '';
      const hdrClass = (isFiltered ? ' has-filter' : '') + (isGrouped ? ' has-group' : '');
      html += `<span class="pr-f pr-f-hdr pr-f-${key}${hdrClass}${idx === 0 ? ' pr-f-first' : ''}"${w} data-key="${key}" data-label="${def?.label || key}">${def?.label || key}${sortMark}${filterMark}${groupMark}</span>`;
    });
    div.innerHTML = html;

    const self = this;
    div.querySelectorAll('.pr-f-hdr').forEach(span => {
      span.addEventListener('contextmenu', e => {
        e.preventDefault();
        e.stopPropagation();
        self._openFieldMenu(span.dataset.key, span.dataset.label, e);
      });
    });

    return div;
  }

  _partRow(p, extraClass, prefix, opts = {}) {
    const {
      depth = 0, hasChildren = false, isCollapsed = false,
      onToggle = null, ancestors = [], onToggleAncestor = null,
    } = opts;
    const div = document.createElement('div');

    if (p._isGroup) {
      div.className = 'part-row part-row-group part-row-category' + (extraClass ? ' ' + extraClass : '');
      const catColor = this._getCategoryColor(p._groupValue);
      if (catColor) div.style.setProperty('--cat-color', catColor);
      const chevron = `<svg class="pr-chevron${isCollapsed ? ' collapsed' : ''}" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>`;
      div.innerHTML =
        `<span class="pr-tree-cell"><span class="pr-node-seg"><span class="pr-toggle">${chevron}</span></span></span>` +
        `<span class="pr-f pr-f-first pr-group-label">${_tlsHe(p._groupValue)}<span class="pr-group-count">${p._groupCount}</span></span>`;
      div.style.setProperty('--tree-w', '12px');
      if (hasChildren && onToggle) {
        div.querySelector('.pr-toggle')?.addEventListener('click', e => { e.stopPropagation(); onToggle(); });
        div.addEventListener('click', () => onToggle());
      }
      return div;
    }

    div.className = 'part-row' + (extraClass ? ' ' + extraClass : '');

    // 分类着色：按 categoryField 字段或 groupMode 下的 groupField 给数据行加色条
    if (this._categoryField) {
      const catVal = (p[this._categoryField] ?? '') + '';
      const catColor = this._getCategoryColor(catVal);
      if (catColor) {
        div.classList.add('has-cat-color');
        div.style.setProperty('--cat-color', catColor);
      }
    }

    let html = '';
    if (prefix) html += `<span class="pr-prefix">${prefix}</span>`;

    html += `<span class="pr-tree-cell">`;

    if (ancestors.length > 0) {
      ancestors.forEach((ancKey, idx) => {
        const d = ancestors.length - 1 - idx;
        html += `<span class="pr-tree-seg" data-depth="${d}" data-anc-key="${_tlsHe(ancKey)}"></span>`;
      });
    } else if (depth > 0) {
      html += `<span style="flex:0 0 ${depth * 14}px"></span>`;
    }

    const chevron = `<svg class="pr-chevron${isCollapsed ? ' collapsed' : ''}" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>`;
    const leafDot = ancestors.length ? ' pr-leaf-dot' : '';
    html += `<span class="pr-node-seg${ancestors.length ? ' has-parent' : ''}">` +
      (hasChildren ? `<span class="pr-toggle">${chevron}</span>` : `<span class="pr-toggle-ph${leafDot}"></span>`) +
      `</span>`;

    html += `</span>`;

    const fields = this._visibleFieldKeys || this._fieldConfig.fields || [];
    const allFields = this._allColumns;
    if (fields.length) {
      fields.forEach((key, idx) => {
        const def = allFields.find(f => f.key === key);
        const w = (def?.width && key !== 'name')
          ? ` style="width:${def.width}px;min-width:${def.width}px"`
          : '';
        const customRenderer = this._cellRenderer[key];
        const cellHtml = customRenderer ? customRenderer(p) : _tlsHe((p[key] ?? '') + '');
        html += `<span class="pr-f pr-f-${key}${idx === 0 ? ' pr-f-first' : ''}"${w}>${cellHtml}</span>`;
      });
    } else {
      html +=
        `<span class="pr-f pr-f-component_id pr-no pr-f-first">${_tlsHe(p.component_id || p.part_no || '-')}</span>` +
        `<span class="pr-f pr-f-name pr-name">${_tlsHe(p.name || '')}</span>` +
        `<span class="pr-f pr-f-quantity pr-qty">${p.quantity ?? ''}</span>` +
        `<span class="pr-f pr-f-component_type pr-type">${_tlsHe(p.component_type || '')}</span>` +
        `<span class="pr-f pr-f-vpps pr-vpps">${_tlsHe(p.vpps || '')}</span>`;
    }

    div.innerHTML = html;

    // 行尾操作容器（rowActions 选项，悬停可见，position:absolute 不影响列宽）
    if (this._rowActions && !p._isGroup) {
      const actEl = document.createElement('span');
      actEl.className = 'pr-row-actions';
      const content = this._rowActions(p);
      if (content instanceof Element) actEl.appendChild(content);
      else if (typeof content === 'string' && content) actEl.innerHTML = content;
      div.appendChild(actEl);
    }

    const treeW = ancestors.length > 0
      ? ancestors.length * 12 + 12
      : depth * 12 + 12;
    div.style.setProperty('--tree-w', `${treeW}px`);

    if (onToggleAncestor) {
      div.querySelectorAll('.pr-tree-seg').forEach(seg => {
        const ancKey = seg.dataset.ancKey;
        if (ancKey) seg.addEventListener('click', e => { e.stopPropagation(); onToggleAncestor(ancKey); });
      });
    }
    if (hasChildren && onToggle) {
      div.querySelector('.pr-toggle')?.addEventListener('click', e => { e.stopPropagation(); onToggle(); });
    }
    const self = this;
    // 左键：onRowClick 优先；否则 editable 模式打开编辑面板
    if (!p._isGroup) {
      const rowClickHandler = this._onRowClick
        ? (p, e) => this._onRowClick(p, e)
        : (this._detailMode === 'editable' ? (p, e) => self._openPartDetail(p, e) : null);
      if (rowClickHandler) {
        div.addEventListener('click', e => {
          if (e.target.closest('.pr-toggle, .pr-tree-seg, .pr-row-actions')) return;
          rowClickHandler(p, e);
        });
      }
    }
    // 右键：优先走 rowContextMenu，否则走只读面板（editable 模式已有左键，右键不重复）
    div.addEventListener('contextmenu', e => {
      e.preventDefault();
      if (self._rowContextMenu) self._showRowCtxMenu(p, e);
      else if (!p._isGroup && self._detailMode !== 'editable') self._openPartDetail(p, e);
    });
    return div;
  }

  _renderTree() {
    // 取消上一次未完成的分块渲染
    if (this._renderRafId) { cancelAnimationFrame(this._renderRafId); this._renderRafId = null; }

    const container = this._colBodyEl;
    container.innerHTML = '';
    const parts = this._getDisplayParts();
    if (!parts.length) {
      container.innerHTML = '<div class="col-empty">暂无数据</div>';
      this._colStatEl.textContent = '0 条';
      this._updatePageBar(0, 0, 0);
      return;
    }
    // 统一计算可见列：顺序以 fieldConfig 为准（字段配置拖拽顺序），可视性以 VM 为准
    const visCols = this.vm ? this.vm.getVisibleColumns() : null;
    this._visibleFieldKeys = visCols
      ? (this._fieldConfig.fields || []).filter(k => visCols.some(c => c.key === k))
      : (this._fieldConfig.fields || []);
    const cacheKey = `${this._dataVersion}:${this._searchText}:${this._fieldConfig.groupMode}:${this._fieldConfig.groupField}:${this._fieldConfig.parentField}:${this._vmStateVer || 0}`;
    if (this._treeCacheKey !== cacheKey) {
      this._treeCache = this._buildTreeForSide(parts);
      this._treeCacheKey = cacheKey;
    }
    const tree = this._treeCache;
    const onToggleKey = (key) => {
      if (this._collapseState.has(key)) this._collapseState.delete(key);
      else this._collapseState.add(key);
      this._renderTree();
    };
    const wrap = document.createElement('div');
    wrap.className = 'pr-rows-wrap';
    wrap.appendChild(this._makeFieldHeader());
    container.appendChild(wrap);

    const visible = this._flattenVisible(tree);
    const totalVisible = visible.length;
    const totalPages = this._pageSize ? Math.max(1, Math.ceil(totalVisible / this._pageSize)) : 1;
    // clamp page
    if (this._currentPage >= totalPages) this._currentPage = Math.max(0, totalPages - 1);
    this._lastTotalPages = totalPages;

    const pageSlice = this._pageSize
      ? visible.slice(this._currentPage * this._pageSize, (this._currentPage + 1) * this._pageSize)
      : visible;

    // 分块渲染：每帧最多渲染 CHUNK 行，避免大数据量时阻塞主线程
    const CHUNK = 80;
    let i = 0;
    const self = this;
    const renderChunk = () => {
      const end = Math.min(i + CHUNK, pageSlice.length);
      for (; i < end; i++) {
        const { part, depth, hasChildren, isCollapsed, key, ancestors } = pageSlice[i];
        wrap.appendChild(self._partRow(part, '', '', {
          depth, hasChildren, isCollapsed, ancestors,
          onToggle: () => onToggleKey(key),
          onToggleAncestor: onToggleKey,
        }));
      }
      if (i < pageSlice.length) {
        self._renderRafId = requestAnimationFrame(renderChunk);
      } else {
        self._renderRafId = null;
      }
    };
    renderChunk();

    const raw = this._rows;
    const cnt = parts.length === raw.length
      ? `${raw.length} 条`
      : `${parts.length} / ${raw.length} 条（已筛选）`;
    this._colStatEl.textContent = cnt;
    this._updatePageBar(totalVisible, totalPages, this._currentPage);
    this._updateCollapseBtn();
  }

  // ==========================================================================
  //  Field Menu
  // ==========================================================================

  _closeFieldMenu() {
    this._activeFieldMenu?.remove();
    this._activeFieldMenu = null;
  }

  _openFieldMenu(key, label, e) {
    this._closeFieldMenu();
    this._closePanel();

    if (!this.vm) return;

    // 保存触发元素（字段头 span），供 VM 面板定位
    const triggerEl = e.target?.closest('.pr-f-hdr') || e.target;

    const sorts = this.vm._sorts || [];
    const filters = this.vm._filters || [];
    const sortObj = sorts.find(s => s.field === key);
    const ascActive  = sortObj && sortObj.dir === 'asc';
    const descActive = sortObj && sortObj.dir === 'desc';
    const isFiltered = filters.some(f => f.field === key);
    const isGroupMode = this._fieldConfig.groupMode === 'group';
    const isGroupField = isGroupMode && this.vm._groupBy === key;

    const menu = document.createElement('div');
    menu.className = 'fh-menu';
    menu.innerHTML = `
      <div class="fh-menu-item${ascActive  ? ' fh-active' : ''}" data-action="sort">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="18 15 12 9 6 15"/></svg>
        排序 (${ascActive ? '升序' : descActive ? '点击降序' : '点击升序'})
      </div>
      <div class="fh-menu-sep"></div>
      <div class="fh-menu-item${isFiltered ? ' fh-active' : ''}" data-action="filter">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/></svg>
        按本字段筛选${isFiltered ? ' (已设置)' : ''}
      </div>
      <div class="fh-menu-sep"></div>
      <div class="fh-menu-item${isGroupField ? ' fh-active' : ''}${!isGroupMode ? ' fh-disabled' : ''}" data-action="group-by">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
        按本字段分组
      </div>`;

    document.body.appendChild(menu);
    this._activeFieldMenu = menu;
    menu.addEventListener('mousedown', e => e.stopPropagation());

    let left = e.clientX, top = e.clientY + 4;
    const mw = menu.offsetWidth, mh = menu.offsetHeight;
    if (left + mw > window.innerWidth  - 8) left = window.innerWidth  - mw - 8;
    if (top  + mh > window.innerHeight - 8) top  = e.clientY - mh - 4;
    menu.style.left = Math.max(8, left) + 'px';
    menu.style.top  = Math.max(8, top)  + 'px';

    const self = this;
    menu.querySelector('[data-action="sort"]').addEventListener('click', () => {
      self.vm.toggleSort(key);
      self._closeFieldMenu();
    });
    menu.querySelector('[data-action="filter"]').addEventListener('click', () => {
      self._closeFieldMenu();
      // 手动加筛选规则 + 用 triggerEl 定位打开 VM 筛选面板
      const col = self.vm._cols.find(c => c.key === key);
      if (col) {
        self.vm._filters.push({
          id:    'f' + (++self.vm._filterIdCnt),
          field: col.key,
          op:    self.vm._opsForType(col.type || 'text')[0][0],
          value: '',
        });
        self.vm._updateFilterBadge();
        self.vm._markDirty();
      }
      // 已有同字段规则则直接开面板，不追加
      self.vm._togglePanel('filter', triggerEl);
    });
    menu.querySelector('[data-action="group-by"]').addEventListener('click', () => {
      if (!isGroupMode) return;
      // 同步到 VM 的 groupBy（用于视图保存/恢复）和 TLS 的 groupField（用于实际渲染）
      self.vm.setGroup(key);
      self._fieldConfig.groupField = key;
      self._closeFieldMenu();
    });

    setTimeout(() => {
      document.addEventListener('mousedown', function h(ev) {
        if (!menu.contains(ev.target)) {
          self._closeFieldMenu();
          document.removeEventListener('mousedown', h);
        }
      });
    }, 0);
  }

  // ==========================================================================
  //  Config Panel
  // ==========================================================================

  _openConfigPanel(anchor) {
    this._closePanel();
    const cfg = this._fieldConfig;
    const allFields = this._allColumns;

    const fieldsHtml = allFields.map(fd => {
      const on = (cfg.fields || []).includes(fd.key);
      return `
        <div class="fc-field-row" draggable="true" data-key="${fd.key}">
          <span class="fc-drag-handle">⠿</span>
          <label class="fc-check-label">
            <input type="checkbox" class="fc-field-chk" data-key="${fd.key}"${on ? ' checked' : ''}>
            <span>${fd.label}</span>
          </label>
        </div>`;
    }).join('');

    const groupFieldOpts = allFields.map(fd =>
      `<option value="${fd.key}"${fd.key === (cfg.groupField || this._optsGroupField) ? ' selected' : ''}>${fd.label}</option>`
    ).join('');

    const panel = document.createElement('div');
    panel.className = 'fp-panel fc-panel';
    panel.style.cssText = 'position:fixed;z-index:9999;width:240px';
    panel.innerHTML = `
      <div class="fp-title">字段设置</div>
      <div class="fp-section">
        <div class="fp-label">层级依据</div>
        <select class="fp-inp" id="cp-parent-${this._uid}">
          <option value="parent_gid"${cfg.parentField === 'parent_gid' || cfg.parentField?.endsWith('_gid') ? ' selected' : ''}>父级GID（parent_gid → gid）</option>
          <option value="parent_bom_row"${cfg.parentField === 'parent_bom_row' ? ' selected' : ''}>父级BOM行（parent_bom_row → bom_row）</option>
          <option value="parent_vpps"${(!cfg.parentField || cfg.parentField === 'parent_vpps') ? ' selected' : ''}>父级VPPS（parent_vpps → vpps）</option>
          <option value="level"${cfg.parentField === 'level' ? ' selected' : ''}>level（数字推断）</option>
        </select>
      </div>
      <div class="fp-section">
        <div class="fp-label">显示模式</div>
        <select class="fp-inp" id="cp-group-mode-${this._uid}">
          <option value="parent"${(cfg.groupMode || 'parent') === 'parent' ? ' selected' : ''}>按父级显示</option>
          <option value="group"${cfg.groupMode === 'group' ? ' selected' : ''}>按分组显示</option>
        </select>
      </div>
      <div class="fp-section" id="cp-group-field-section-${this._uid}"${(cfg.groupMode || 'parent') !== 'group' ? ' style="display:none"' : ''}>
        <div class="fp-label">分组字段</div>
        <select class="fp-inp" id="cp-group-field-${this._uid}">${groupFieldOpts}</select>
      </div>
      <div class="fp-section">
        <div class="fp-label">显示字段（拖拽调序）</div>
        <div class="fc-field-list" id="cp-fields-${this._uid}">${fieldsHtml}</div>
      </div>
      <div class="fp-actions">
        <button class="cp-btn-reset" id="cp-reset-${this._uid}">重置</button>
        <button class="fp-btn-apply" id="cp-apply-${this._uid}">应用</button>
      </div>`;

    document.body.appendChild(panel);
    this._activePanel = panel;
    this._positionPanel(panel, anchor);

    // Drag sort
    const fieldList = panel.querySelector(`#cp-fields-${this._uid}`);
    let dragSrc = null;
    fieldList.querySelectorAll('.fc-field-row').forEach(row => {
      row.addEventListener('dragstart', e => { dragSrc = row; row.classList.add('fc-dragging'); e.dataTransfer.effectAllowed = 'move'; });
      row.addEventListener('dragend',   () => { dragSrc?.classList.remove('fc-dragging'); dragSrc = null; });
      row.addEventListener('dragover',  e => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; });
      row.addEventListener('drop', e => {
        e.preventDefault();
        if (!dragSrc || dragSrc === row) return;
        const allRows = [...fieldList.querySelectorAll('.fc-field-row')];
        if (allRows.indexOf(dragSrc) < allRows.indexOf(row)) row.after(dragSrc); else row.before(dragSrc);
      });
    });

    // Group mode toggle
    const groupModeSel = panel.querySelector(`#cp-group-mode-${this._uid}`);
    const groupFieldSection = panel.querySelector(`#cp-group-field-section-${this._uid}`);
    groupModeSel?.addEventListener('change', () => {
      groupFieldSection.style.display = groupModeSel.value === 'group' ? '' : 'none';
    });

    const self = this;
    panel.querySelector(`#cp-apply-${this._uid}`).addEventListener('click', () => {
      const parentField = panel.querySelector(`#cp-parent-${this._uid}`).value;
      const groupMode = panel.querySelector(`#cp-group-mode-${this._uid}`).value;
      const groupField = panel.querySelector(`#cp-group-field-${this._uid}`).value;
      const orderedKeys = [...fieldList.querySelectorAll('.fc-field-row')].map(r => r.dataset.key);
      const fields = orderedKeys.filter(k => fieldList.querySelector(`.fc-field-chk[data-key="${k}"]`)?.checked);
      if (!fields.length) return;
      // 保留现有 VM 筛选/排序，只更新 TLS 显示设置
      self._applyState({
        parentField, groupMode, groupField, fields,
        search:       self._searchText,
        vmFilters:    self.vm?._filters    || [],
        vmSorts:      self.vm?._sorts      || [],
        vmFilterMode: self.vm?._filterMode || 'and',
        vmGroupBy:    self.vm?._groupBy    || null,
      });
      self._closePanel();
      self._renderTree();
    });

    panel.querySelector(`#cp-reset-${this._uid}`).addEventListener('click', () => {
      self._applyState({
        parentField:  self._optsParentField,
        groupMode:    'parent',
        groupField:   self._optsGroupField,
        fields:       self._allColumns.filter(fd => fd.defaultOn !== false).map(fd => fd.key),
        search:       '',
        vmFilters:    [],
        vmSorts:      [],
        vmFilterMode: 'and',
        vmGroupBy:    null,
      });
      self._userAdjustedCols = false; // 重置后恢复自适应
      if (self._searchInpEl) self._searchInpEl.value = '';
      self._closePanel();
      self._renderTree();
    });

    this._registerOutsideClick(panel, anchor);
  }

  // ==========================================================================
  //  Collapse / Group
  // ==========================================================================

  _toggleCollapse() {
    if (this._collapseState.size > 0) {
      this._collapseState.clear();
    } else {
      const parts = this._getDisplayParts();
      const tree  = this._treeCache || this._buildTreeForSide(parts);
      tree.childrenMap.forEach((_, key) => this._collapseState.add(key));
    }
    this._renderTree();
    this._updateCollapseBtn();
  }

  _updateCollapseBtn() {
    const btn = this._collapseBtnEl;
    if (!btn) return;
    const anyCollapsed = this._collapseState.size > 0;
    btn.title = anyCollapsed ? '全部展开' : '全部折叠';
    btn.querySelector('svg').innerHTML = anyCollapsed
      ? '<rect x="3" y="3" width="18" height="18" rx="2"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/>'
      : '<rect x="3" y="3" width="18" height="18" rx="2"/><line x1="8" y1="12" x2="16" y2="12"/>';
  }

  // ── 新建条目 Popover ────────────────────────────────────────────────────────
  // 系统字段不在弹窗中展示
  static get _NEP_SKIP_KEYS() {
    return new Set(['id', 'gid', 'created_at', 'updated_at', 'deleted_at',
                    'list_gid', 'owner_gid', 'assignee_gid', 'author_gid']);
  }

  _syncNewEntryBtn() {
    if (!this._newEntryBtnEl) return;
    this._newEntryBtnEl.style.display = (this._allowNewEntry && this._onCreateEntry) ? '' : 'none';
  }

  _showNewEntryPopover(anchorEl) {
    if (!this._onCreateEntry) return;
    const listGid = this._selectedListGid;
    if (!listGid) return;

    this._closeNewEntryPopover();

    // 从自身列定义提取可填字段（defaultOn 且非系统字段）
    const skip = TreeListShell._NEP_SKIP_KEYS;
    const fields = (this._columns || []).filter(c => c.defaultOn && !skip.has(c.key));
    if (!fields.length) return;

    const uid = this._uid;
    const fieldsHtml = fields.map((f, i) => {
      const id  = `tls_nep_${uid}_${f.key}`;
      const isDate = /(_date|_at)$/.test(f.key) && f.key !== 'created_at' && f.key !== 'updated_at';
      const ctrl = isDate
        ? `<input class="tls-nep-control" type="date" id="${id}" data-key="${f.key}">`
        : `<input class="tls-nep-control${i === 0 ? ' tls-nep-primary' : ''}" type="text" id="${id}" data-key="${f.key}" placeholder="${f.label}" autocomplete="off">`;
      return `<div class="tls-nep-row">
        <label class="tls-nep-label" for="${id}">${f.label}${i === 0 ? '<span class="tls-nep-req">*</span>' : ''}</label>
        ${ctrl}</div>`;
    }).join('');

    const pop = document.createElement('div');
    pop.className = 'tls-nep-pop';
    pop.innerHTML = `
      <div class="tls-nep-header">
        <span class="tls-nep-title">新建条目</span>
        <button class="tls-nep-close" title="关闭">
          <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="2" y1="2" x2="14" y2="14"/><line x1="14" y1="2" x2="2" y2="14"/></svg>
        </button>
      </div>
      <div class="tls-nep-body">${fieldsHtml}</div>
      <div class="tls-nep-footer">
        <button class="tls-nep-btn-cancel">取消</button>
        <button class="tls-nep-btn-ok">确认创建</button>
      </div>`;

    document.body.appendChild(pop);
    this._nepEl = pop;

    // 定位到按钮下方，防右溢
    const rect = anchorEl.getBoundingClientRect();
    pop.style.top  = (rect.bottom + 6) + 'px';
    pop.style.left = rect.left + 'px';
    requestAnimationFrame(() => {
      const pr = pop.getBoundingClientRect();
      if (pr.right > window.innerWidth - 8)
        pop.style.left = Math.max(8, window.innerWidth - pr.width - 8) + 'px';
    });

    const firstInp = pop.querySelector('input[type="text"]');
    if (firstInp) requestAnimationFrame(() => firstInp.focus());

    const submit = async () => {
      const primaryEl  = pop.querySelector(`[data-key="${fields[0].key}"]`);
      if (!primaryEl?.value.trim()) {
        primaryEl?.focus();
        primaryEl?.classList.add('tls-nep-error');
        return;
      }
      const data = { list_gid: listGid };
      pop.querySelectorAll('[data-key]').forEach(el => {
        const v = el.value.trim();
        if (v) data[el.dataset.key] = v;
      });

      const okBtn = pop.querySelector('.tls-nep-btn-ok');
      okBtn.disabled = true;
      okBtn.textContent = '创建中…';
      try {
        await this._onCreateEntry(data);
        this._closeNewEntryPopover();
        await this._loadData();
      } catch (e) {
        console.error('[TLS] 新建条目失败', e);
        okBtn.disabled = false;
        okBtn.textContent = '确认创建';
      }
    };

    pop.querySelector('.tls-nep-btn-ok').addEventListener('click', submit);
    pop.querySelector('.tls-nep-btn-cancel').addEventListener('click', () => this._closeNewEntryPopover());
    pop.querySelector('.tls-nep-close').addEventListener('click', () => this._closeNewEntryPopover());
    pop.addEventListener('keydown', e => {
      if (e.key === 'Enter' && e.target.tagName !== 'SELECT') { e.preventDefault(); submit(); }
      if (e.key === 'Escape') { e.stopPropagation(); this._closeNewEntryPopover(); }
    });
    pop.querySelectorAll('.tls-nep-control').forEach(el =>
      el.addEventListener('input', () => el.classList.remove('tls-nep-error'))
    );

    const outsideClick = e => {
      if (!pop.contains(e.target) && e.target !== anchorEl) {
        this._closeNewEntryPopover();
        document.removeEventListener('mousedown', outsideClick, true);
      }
    };
    document.addEventListener('mousedown', outsideClick, true);
    this._nepOutsideClick = outsideClick;
  }

  _closeNewEntryPopover() {
    if (this._nepEl) { this._nepEl.remove(); this._nepEl = null; }
    if (this._nepOutsideClick) {
      document.removeEventListener('mousedown', this._nepOutsideClick, true);
      this._nepOutsideClick = null;
    }
  }

  _updateGroupBtn() {
    const btn = this._groupBtnEl;
    if (!btn) return;
    const isGroup = this._fieldConfig.groupMode === 'group';
    btn.classList.toggle('col-btn-active', isGroup);
    btn.title = isGroup ? '切换到父级显示' : '切换到分组显示';
  }

  // ==========================================================================
  //  Runtime Config Application
  // ==========================================================================

  /**
   * Apply the field-config panel's in-memory TLS + VM state without emitting
   * intermediate renders for every ViewManager setter.
   */
  _applyState(state) {
    if (!state) return;

    // 1. 字段列表：保留已知列，新增列追加到末尾
    const validKeys = new Set(this._allColumns.map(c => c.key));
    const savedFields = (state.fields || []).filter(k => validKeys.has(k));
    const newKeys = this._allColumns.map(c => c.key).filter(k => !savedFields.includes(k));
    const fields = savedFields.length
      ? [...savedFields, ...newKeys]
      : this._allColumns.filter(c => c.defaultOn !== false).map(c => c.key);

    this._fieldConfig = {
      parentField: state.parentField || this._optsParentField,
      groupMode:   state.groupMode   || 'parent',
      groupField:  state.groupField  || this._optsGroupField,
      fields,
    };
    this._userAdjustedCols = true;

    // 2. 搜索框
    if (state.search !== undefined) {
      this._searchText = state.search || '';
      if (this._searchInpEl) this._searchInpEl.value = this._searchText;
      const hasSearch = !!this._searchText;
      this._searchBarEl?.classList.toggle('hidden', !hasSearch);
      document.getElementById(`${this._uid}_searchbtn`)?.classList.toggle('col-btn-active', hasSearch);
    }

    // 3. VM 同步——用 _restoringConfig 阻止 onChange 的重复渲染
    this._restoringConfig = true;
    try {
      if (this.vm) {
        // 可见列
        this._allColumns.forEach(c => this.vm.setColVisible(c.key, fields.includes(c.key)));

        // 分组
        const gm = this._fieldConfig.groupMode;
        const gf = this._fieldConfig.groupField;
        this.vm.setGroup((gm === 'group' && gf) ? gf : null);

        // 筛选
        const vf = Array.isArray(state.vmFilters) ? state.vmFilters : [];
        this.vm._filters    = vf;
        this.vm._filterMode = state.vmFilterMode || 'and';
        this.vm._filterIdCnt = vf.reduce(
          (m, f) => Math.max(m, parseInt((f.id || '').replace(/\D/g, '')) || 0), 0
        );
        this.vm._updateFilterBadge?.();

        // 排序
        const vs = Array.isArray(state.vmSorts) ? state.vmSorts : [];
        this.vm._sorts = vs;
        this.vm._updateSortBadge?.();

        // VM 分组
        this.vm._groupBy = state.vmGroupBy || null;
        this.vm._updateGroupBadge?.();
      }
    } finally {
      this._restoringConfig = false;
    }

    // 版本号递增让树缓存失效
    this._vmStateVer = (this._vmStateVer || 0) + 1;
    this._updateGroupBtn();
  }

  _updatePageBar(totalVisible, totalPages, currentPage) {
    if (!this._pageSzEl) return;
    this._pageSzEl.value = String(this._pageSize);
    if (!this._pageSize || totalPages <= 1) {
      this._pageInfoEl.textContent = '';
      this._pagePrevEl.disabled = true;
      this._pageNextEl.disabled = true;
    } else {
      const start = currentPage * this._pageSize + 1;
      const end   = Math.min((currentPage + 1) * this._pageSize, totalVisible);
      this._pageInfoEl.textContent = `${start}–${end} / ${totalVisible}`;
      this._pagePrevEl.disabled = currentPage === 0;
      this._pageNextEl.disabled = currentPage >= totalPages - 1;
    }
  }

  _getCategoryColor(val) {
    const s = (val ?? '') + '';
    if (!s) return null;
    if (this._categoryColors[s]) return this._categoryColors[s];
    if (!this._catColorMap.has(s)) {
      this._catColorMap.set(s, _TLS_CAT_PALETTE[this._catColorMap.size % _TLS_CAT_PALETTE.length]);
    }
    return this._catColorMap.get(s);
  }

  // ==========================================================================
  //  Overflow Menu
  // ==========================================================================

  _initOverflowMenu() {
    // 精简工具栏模式：所有按钮始终可见，不需要溢出检测
    if (this._compactToolbar) return;

    const toolbar = this._toolbarEl;
    const moreBtn = this._moreBtnEl;
    if (!toolbar || !moreBtn) return;

    const self = this;
    function check() {
      // 有固定菜单项时 more 按钮始终可见
      if (self._moreMenuItems.length) { moreBtn.classList.remove('hidden'); return; }
      const children = [...toolbar.children];
      if (!children.length) { moreBtn.classList.add('hidden'); return; }
      const last = children[children.length - 1];
      const tRect = toolbar.getBoundingClientRect();
      const lRect = last.getBoundingClientRect();
      moreBtn.classList.toggle('hidden', lRect.right <= tRect.right + 1);
    }

    new ResizeObserver(check).observe(toolbar);
    moreBtn.addEventListener('click', e => { e.stopPropagation(); self._openMoreMenu(moreBtn); });
  }

  _openMoreMenu(anchor) {
    this._activeMoreMenu?.remove();
    this._activeMoreMenu = null;

    const toolbar = this._toolbarEl;
    if (!toolbar) return;

    const tRect = toolbar.getBoundingClientRect();
    const overflowing = [...toolbar.children].filter(el => {
      const r = el.getBoundingClientRect();
      return r.right > tRect.right + 1 || r.left > tRect.right;
    });

    // 若溢出项和固定项都没有则退出
    if (!overflowing.length && !this._moreMenuItems.length) return;

    const menu = document.createElement('div');
    menu.className = 'more-menu';

    overflowing.forEach(el => {
      if (el.classList.contains('col-separator')) {
        const sep = document.createElement('div');
        sep.className = 'more-menu-sep';
        menu.appendChild(sep);
        return;
      }
      const item = document.createElement('div');
      const isActive = el.classList.contains('col-btn-active');
      item.className = 'more-menu-item' + (isActive ? ' is-active' : '');
      const svgEl = el.querySelector('svg');
      const labelEl = el.querySelector('.feat-label');
      const label = el.title || (labelEl?.textContent.trim()) || el.textContent.trim();
      item.innerHTML = (svgEl ? svgEl.outerHTML : '') + `<span>${_tlsHe(label)}</span>`;
      item.addEventListener('click', () => { el.click(); menu.remove(); this._activeMoreMenu = null; });
      menu.appendChild(item);
    });

    // 追加固定菜单项（moreMenuItems 选项）
    if (this._moreMenuItems.length) {
      if (menu.children.length) {
        const sep = document.createElement('div');
        sep.className = 'more-menu-sep';
        menu.appendChild(sep);
      }
      this._moreMenuItems.forEach(it => {
        const item = document.createElement('div');
        item.className = 'more-menu-item';
        item.innerHTML = (it.icon || '') + `<span>${_tlsHe(it.label)}</span>`;
        item.addEventListener('click', () => {
          menu.remove(); this._activeMoreMenu = null;
          it.onClick?.(anchor);
        });
        menu.appendChild(item);
      });
    }

    if (!menu.children.length) return;
    document.body.appendChild(menu);
    this._activeMoreMenu = menu;
    menu.addEventListener('mousedown', e => e.stopPropagation());

    const r = anchor.getBoundingClientRect();
    let left = r.right - menu.offsetWidth, top = r.bottom + 4;
    if (top + menu.offsetHeight > window.innerHeight - 8) top = r.top - menu.offsetHeight - 4;
    menu.style.top  = Math.max(8, top)  + 'px';
    menu.style.left = Math.max(8, left) + 'px';

    const self = this;
    setTimeout(() => {
      document.addEventListener('mousedown', function h(ev) {
        if (!menu.contains(ev.target)) {
          menu.remove(); self._activeMoreMenu = null;
          document.removeEventListener('mousedown', h);
        }
      });
    }, 0);
  }

  // ==========================================================================
  //  Row Context Menu (rowContextMenu option)
  // ==========================================================================

  _showRowCtxMenu(p, e) {
    this._closeFieldMenu();
    this._closePanel();
    document.querySelector('.tls-row-ctx-menu')?.remove();

    const items = typeof this._rowContextMenu === 'function'
      ? this._rowContextMenu(p)
      : this._rowContextMenu;

    const menu = document.createElement('div');
    menu.className = 'tls-row-ctx-menu';
    menu.innerHTML = items.map((it, idx) =>
      it.separator
        ? '<div class="tls-ctx-sep"></div>'
        : `<div class="tls-ctx-item${it.danger ? ' danger' : ''}" data-idx="${idx}">${_tlsHe(it.label)}</div>`
    ).join('');

    const left = Math.min(e.clientX, window.innerWidth - 150);
    const top  = Math.min(e.clientY, window.innerHeight - 100);
    menu.style.cssText = `position:fixed;z-index:9999;left:${left}px;top:${top}px`;
    document.body.appendChild(menu);

    menu.querySelectorAll('.tls-ctx-item').forEach(el => {
      const idx = +el.dataset.idx;
      el.addEventListener('click', () => { menu.remove(); items[idx].onClick?.(p); });
    });

    setTimeout(() => {
      document.addEventListener('mousedown', function h(ev) {
        if (!menu.contains(ev.target)) { menu.remove(); document.removeEventListener('mousedown', h); }
      });
    }, 0);
  }

  // ==========================================================================
  //  Detail Panel (readonly / editable)
  // ==========================================================================

  _openPartDetail(p, e) {
    this._closeFieldMenu();
    this._closePanel();

    // 字段来源：detailFields 白名单 > allColumns 全量
    const detailFields = this._detailFields?.length ? this._detailFields : this._allColumns;
    const canSave = !!this._onSave;

    const panelTitle = this._rowTitle ? this._rowTitle(p) : (p.name || p.component_id || p.part_no || '详情');

    const fieldsHtml = detailFields.map(f => {
      const key   = f.key   || f;
      const label = f.label || key;
      const val   = (p[key] ?? '') + '';
      if (canSave) {
        return `<div class="tls-dp-row">
          <span class="tls-dp-label">${_tlsHe(label)}</span>
          <input class="fp-inp tls-detail-inp" data-key="${_tlsHe(key)}" value="${_tlsHe(val)}">
        </div>`;
      } else {
        return `<div class="tls-dp-row">
          <span class="tls-dp-label">${_tlsHe(label)}</span>
          <span class="tls-dp-value${!val ? ' is-empty' : ''}">${val ? _tlsHe(val) : '—'}</span>
        </div>`;
      }
    }).join('');

    const panel = document.createElement('div');
    panel.className = 'fp-panel tls-detail-panel';
    panel.innerHTML = `
      <div class="tls-dp-hdr">
        <span class="tls-dp-title">${_tlsHe(panelTitle)}</span>
        <button class="tls-dp-close" title="关闭">
          <svg width="9" height="9" viewBox="0 0 10 10"><line x1="0" y1="0" x2="10" y2="10" stroke="currentColor" stroke-width="1.5"/><line x1="10" y1="0" x2="0" y2="10" stroke="currentColor" stroke-width="1.5"/></svg>
        </button>
      </div>
      <div class="tls-dp-body">${fieldsHtml || '<span style="color:var(--muted);font-size:11px">暂无字段</span>'}</div>
      ${canSave ? `<div class="fp-actions tls-dp-footer">
        <button class="fp-btn-clear tls-detail-cancel">取消</button>
        <button class="fp-btn-apply tls-detail-save">保存</button>
      </div>` : ''}`;

    document.body.appendChild(panel);
    this._activePanel = panel;

    // 定位：靠近点击位置，防止超出视口
    let left = e.clientX + 12, top = e.clientY - 20;
    const pw = panel.offsetWidth, ph = panel.offsetHeight;
    if (left + pw > window.innerWidth  - 8) left = e.clientX - pw - 12;
    if (top  + ph > window.innerHeight - 8) top  = window.innerHeight - ph - 8;
    panel.style.top  = Math.max(8, top)  + 'px';
    panel.style.left = Math.max(8, left) + 'px';

    const self = this;
    panel.querySelector('.tls-dp-close').addEventListener('click', () => self._closePanel());

    if (canSave) {
      panel.querySelector('.tls-detail-cancel').addEventListener('click', () => self._closePanel());
      panel.querySelector('.tls-detail-save').addEventListener('click', async () => {
        const updated = { ...p };
        panel.querySelectorAll('.tls-detail-inp').forEach(inp => {
          updated[inp.dataset.key] = inp.value;
        });
        try {
          const result = await self._onSave(updated);
          if (result) {
            self._closePanel();
            const idx = self._rows.findIndex(r => r.gid === result.gid);
            if (idx >= 0) self._rows[idx] = result;
            self._renderTree();
          }
        } catch (err) {
          alert('保存失败: ' + err.message);
        }
      });
    }

    this._registerOutsideClick(panel, null);
  }

  // ==========================================================================
  //  Panel Helpers
  // ==========================================================================

  _closePanel() {
    this._activePanel?.remove();
    this._activePanel = null;
    // 清除已注册的外部点击 handler，防止关闭后 handler 泄漏到下一个面板
    if (this._outsideClickH) {
      document.removeEventListener('mousedown', this._outsideClickH);
      this._outsideClickH = null;
    }
  }

  _positionPanel(panel, anchor) {
    const r = anchor.getBoundingClientRect();
    let top = r.bottom + 4, left = r.left;
    const pw = panel.offsetWidth, ph = panel.offsetHeight;
    if (left + pw > window.innerWidth  - 8) left = window.innerWidth  - pw - 8;
    if (top  + ph > window.innerHeight - 8) top  = r.top - ph - 4;
    top  = Math.max(8, top);
    left = Math.max(8, left);
    panel.style.cssText += `;top:${top}px;left:${left}px`;
  }

  _registerOutsideClick(panel, anchor) {
    const self = this;
    // 先清除上一个 handler（如果有），避免泄漏
    if (self._outsideClickH) {
      document.removeEventListener('mousedown', self._outsideClickH);
      self._outsideClickH = null;
    }
    setTimeout(() => {
      self._outsideClickH = function h(e) {
        if (!panel.contains(e.target) && e.target !== anchor && !panel.contains(document.activeElement)) {
          self._closePanel();
        }
      };
      document.addEventListener('mousedown', self._outsideClickH);
    }, 0);
  }

  _closeAllFloatMenus() {
    this._closePanel();
    this._closeFieldMenu();
    this._activeMoreMenu?.remove();
    this._activeMoreMenu = null;
  }

  // ==========================================================================
  //  ViewManager
  // ==========================================================================

  async _initViewManager() {
    if (!this._moduleId || typeof ViewManager === 'undefined') return;
    const self = this;
    // 把 allColumns 全部传给 VM，初始可见性由 this._columns 决定
    // 这样 setColVisible 对所有字段（包括非默认列）都能生效
    const _initVisibleKeys = new Set(this._columns.map(c => c.key));
    this.vm = new ViewManager({
      moduleId: this._moduleId,
      listGid: this._listGid || null,
      columns: this._allColumns.map(c => ({ ...c, visible: _initVisibleKeys.has(c.key) })),
      toolbarEl: this._vmToolbarEl,
      onChange: () => {
        // _restoringConfig 期间（_applyState 内部）完全跳过，避免多次渲染
        if (self._restoringConfig) return;
        self._vmStateVer = (self._vmStateVer || 0) + 1;
        const activeView = self.vm?._views?.find(view => view.gid === self.vm?._activeViewGid);
        if (activeView) self._onViewChange?.(activeView.name);
        self._renderTree();
      },
    });
    await this.vm.init();
    this.vm.renderTabBar(this._vmToolbarEl);
  }

  // ==========================================================================
  //  Extra Buttons
  // ==========================================================================

  _renderExtraButtons() {
    if (!this._extraBtnsEl) return;
    this._extraBtnsEl.innerHTML = '';
    this._extraToolbarBtns.forEach(btn => {
      const el = document.createElement('button');
      el.className = 'col-btn feat-btn';
      if (btn.html) el.innerHTML = btn.html;
      if (btn.title) el.title = btn.title;
      if (btn.active) el.classList.add('col-btn-active');
      if (btn.onClick) el.addEventListener('click', btn.onClick);
      this._extraBtnsEl.appendChild(el);
    });
  }
}

//  Helper Functions
// ============================================================================

function _tlsHe(s) {
  return String(s ?? '').replace(/[&<>"']/g,
    c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function _tlsDebounce(fn, ms) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

function _tlsOpt(value, label) {
  const o = document.createElement('option');
  o.value = value; o.textContent = label;
  return o;
}

