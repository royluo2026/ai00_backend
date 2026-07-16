'use strict';
/**
 * ListShell — 清单类型通用壳
 *
 * 提供三栏布局（ListSidebar ＋ GridEditor ＋ RowDetailPanel）
 * 以及视图标签栏（ViewManager.renderTabBar）。
 *
 * 使用方式：
 *   const shell = new ListShell({
 *     mountEl:           document.getElementById('appRoot'),
 *     itemType:          'task',
 *     moduleId:          'task_list',
 *     columns:           TASK_COLS,
 *     cellRenderer:      { title: ..., status: ... },
 *     onRowsChange:      async (newRows) => { ... },
 *     extraContextItems: (row) => [...],
 *     onContextAction:   (action, row) => { ... },
 *     rowClass:          (row) => '...',
 *     ganttFields:       { startField: 'plan_start', endField: 'plan_end' },
 *     onListsChange:     (lists) => { _allLists = lists; },
 *     initListGid:       null,
 *   });
 *   await shell.init();
 *
 *   // 更新数据
 *   shell.setRows(combinedRows);
 *
 *   // 访问子组件
 *   shell.vm    // ViewManager
 *   shell.grid  // GridEditor
 */
class ListShell {
  constructor(opts) {
    this._mountEl          = opts.mountEl;
    this._itemType         = opts.itemType         || '';
    this._moduleId         = opts.moduleId         || '';
    this._colDefs          = opts.columns          || [];
    this._cellRenderer     = opts.cellRenderer     || {};
    this._onRowsChange     = opts.onRowsChange     || null;
    this._extraCtxItems    = opts.extraContextItems || null;
    this._onContextAction  = opts.onContextAction  || null;
    this._rowClass         = opts.rowClass         || null;
    this._ganttFields      = opts.ganttFields      || null;
    this._onListsChange    = opts.onListsChange    || null;
    this._onSelect         = opts.onSelect         || null;
    this._initListGid      = opts.initListGid      || null;
    this._extOnRowClick    = opts.onRowClick       || null;  // override default RDP open
    this._showSidebar      = opts.showSidebar !== false;    // 默认 true；false = 由外部（工作区侧边栏）管理清单导航
    this._sidebarExtraItemHtml = opts.sidebarExtraItemHtml || null;  // 透传给 ListSidebar
    this._sidebarOnCreate  = opts.sidebarOnCreate  || null;          // 透传给 ListSidebar
    this._sidebarOnContextMenu = opts.sidebarOnContextMenu || null;  // 透传给 ListSidebar
    this._sidebarDisableInlineRename = opts.sidebarDisableInlineRename || false; // 透传给 ListSidebar

    this._title          = opts.title          || '';
    this._titleIcon      = opts.titleIcon      || '';
    this._newLabel       = opts.newLabel       || '';
    this._onNew          = opts.onNew          || null;
    this._extraTbBtns    = opts.extraToolbarBtns || [];
    this._importExportCfg = opts.importExport  || null;
    this._diffManagerCfg  = opts.diffManager   || null;
    this._rdpSaveOpts     = opts.rdpSaveOpts   || null;  // { bridgeNs, bridgeMethod, cloudPath }
    this._toolbarEl       = null;
    this.ieMgr            = null;
    this.diffMgr          = null;
    this._bitableSyncCfg  = opts.bitableSync   || null;
    this.bitableSyncMgr   = null;

    this._currentList = this._initListGid;
    this._allRows     = [];
    this._searchText  = '';
    this._sidebarW    = 160;   // resizable sidebar width (px)
    // 分页（enablePagination: true 时生效）
    this._enablePagination = !!opts.enablePagination;
    this._pageSize    = opts.pageSize || 200;
    this._page        = 0;
    this._paginationEl = null;

    // Sub-components (public)
    this.vm      = null;
    this.grid    = null;
    this.sidebar = null;
    this.rdp     = null;

    // Private DOM refs
    this._tabBarEl  = null;
    this._vmBarEl   = null;
    this._sidebarEl = null;
    this._gridEl    = null;
    this._ganttEl   = null;
    this._rdpEl     = null;

    this._gantt = null;
    this._tree  = null;
  }

  // ─── 初始化 ──────────────────────────────────────────────────────────────────

  async init() {
    this._buildLayout();
    await this._buildSidebar();
    await this._buildViewManager();
    this._buildGrid(this._colDefs, []);
    this._buildRdp();

    // Initialize ImportExportManager
    if (this._importExportCfg && typeof ImportExportManager !== 'undefined') {
      this.ieMgr = new ImportExportManager({
        moduleId: this._importExportCfg.moduleId,
        columns:  this._cols || this._colDefs,
        getRows:  this._importExportCfg.getRows,
        onImport: this._importExportCfg.onImport,
      });
    }

    // Initialize DiffManager
    if (this._diffManagerCfg && typeof DiffManager !== 'undefined') {
      this.diffMgr = new DiffManager({
        moduleId:        this._diffManagerCfg.moduleId,
        columns:         this._cols || this._colDefs,
        defaultMatchKey: this._diffManagerCfg.defaultMatchKey,
        loaders:         this._diffManagerCfg.loaders,
      });
    }

    // Initialize BitableSyncManager
    if (this._bitableSyncCfg && this._bitableSyncCfg.enabled
        && typeof BitableSyncManager !== 'undefined') {
      this.bitableSyncMgr = new BitableSyncManager({
        listGid:        this._currentList || '',
        columns:        this._colDefs,
        getRows:        this._bitableSyncCfg.getRows || (() => this._allRows),
        onRemoteUpdate: this._bitableSyncCfg.onRemoteUpdate || (() => {}),
      });
      this.bitableSyncMgr._onStatusChange = (s) => this._updateSyncDot(s);
      this._buildSyncBtn();
      this.bitableSyncMgr.init().catch(e => console.error('[BitableSync] init:', e));
    }
  }

  // ─── 布局 ────────────────────────────────────────────────────────────────────

  _buildLayout() {
    this._mountEl.innerHTML = '';
    // height:100% handles normal block parent; flex:1;min-height:0 handles flex parent
    this._mountEl.style.cssText = 'display:flex;flex-direction:column;height:100%;flex:1;min-height:0;overflow:hidden';

    // ls-root: 横向排列，侧边栏在最左且贯穿全高
    const root = document.createElement('div');
    root.className = 'ls-root';
    root.style.cssText = 'flex:1;min-height:0;overflow:hidden';
    this._mountEl.appendChild(root);

    // 左侧：清单侧边栏（贯穿全高）
    if (this._showSidebar) {
      this._sidebarEl = document.createElement('div');
      this._sidebarEl.className = 'ls-sidebar';
      this._sidebarEl.style.width = this._sidebarW + 'px';
      root.appendChild(this._sidebarEl);

      // sidebar resize handle（独立 flex 子元素，在 sidebar 和 right-col 之间，
      // 不放在 sidebar 内部以避免被 ListSidebar.init() 的 innerHTML='' 清掉）
      const resizeHandle = document.createElement('div');
      resizeHandle.className = 'ls-sidebar-resize';
      root.appendChild(resizeHandle);
      this._bindSidebarResize(resizeHandle);
    }

    // 右侧主列（tab-bar + search-row + vm-bar + body）
    this._rightColEl = document.createElement('div');
    this._rightColEl.className = 'ls-right-col';
    root.appendChild(this._rightColEl);

    // Tab行: [tab-bar (flex:1)] + [tab-actions (右侧操作按钮)]
    const tabRow = document.createElement('div');
    tabRow.className = 'ls-tab-row';
    this._rightColEl.appendChild(tabRow);

    // Tab bar（由 ViewManager.renderTabBar 填充，不放任何自定义内容）
    this._tabBarEl = document.createElement('div');
    this._tabBarEl.className = 'ls-tab-bar';
    tabRow.appendChild(this._tabBarEl);

    // Tab actions（新建/导入/导出等按钮，位于 tab bar 右侧）
    this._tabActionsEl = document.createElement('div');
    this._tabActionsEl.className = 'ls-tab-actions';
    tabRow.appendChild(this._tabActionsEl);
    this._buildTabActions(this._tabActionsEl);

    // 主区域: [左列 (搜索行+表格)] [右列 (RDP，与导入导出按钮行顶部对齐)]
    const mainArea = document.createElement('div');
    mainArea.className = 'ls-main';
    this._rightColEl.appendChild(mainArea);

    // 左列: 搜索行 + 表格/甘特/树
    const leftCol = document.createElement('div');
    leftCol.className = 'ls-left-col';
    mainArea.appendChild(leftCol);

    // 搜索框移到 Tab 行（tab bar 右侧，tab actions 左侧）
    const searchWrap = document.createElement('div');
    searchWrap.className = 'ls-tab-search';
    searchWrap.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="opacity:.5;flex-shrink:0"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>`;
    const searchInput = document.createElement('input');
    searchInput.className = 'ls-tab-search-input';
    searchInput.type = 'text';
    searchInput.placeholder = '搜索…';
    searchWrap.appendChild(searchInput);
    searchInput.addEventListener('input', () => {
      this._searchText = searchInput.value.trim().toLowerCase();
      this._page = 0;   // 搜索时重置到第一页
      this._renderRows();
    });
    tabRow.insertBefore(searchWrap, this._tabActionsEl);

    // vmBarEl kept as detached element (passed to ViewManager but not in DOM)
    this._vmBarEl = document.createElement('div');

    // Body（grid/甘特/树，在左列内）
    const body = document.createElement('div');
    body.className = 'ls-body';
    leftCol.appendChild(body);

    // Center
    const center = document.createElement('div');
    center.className = 'ls-center';
    body.appendChild(center);

    // Grid wrap
    this._gridEl = document.createElement('div');
    this._gridEl.className = 'ls-grid-wrap';
    center.appendChild(this._gridEl);

    // 分页栏（enablePagination 时使用）
    if (this._enablePagination) {
      this._paginationEl = document.createElement('div');
      this._paginationEl.className = 'ls-pagination';
      center.appendChild(this._paginationEl);
    }

    // Gantt wrap (hidden by default)
    this._ganttEl = document.createElement('div');
    this._ganttEl.className = 'ls-gantt-wrap';
    center.appendChild(this._ganttEl);

    // Tree wrap (hidden by default)
    this._treeEl = document.createElement('div');
    this._treeEl.className = 'ls-tree-wrap';
    center.appendChild(this._treeEl);

    // Right detail panel（与 ls-tab-row 底边对齐，紧贴顶部）
    this._rdpEl = document.createElement('div');
    this._rdpEl.className = 'ls-rdp';
    mainArea.appendChild(this._rdpEl);

    // RDP resize handle（SDP 左边缘拖拽调宽，在 RDP 之前）
    const rdpResizeHandle = document.createElement('div');
    rdpResizeHandle.className = 'ls-rdp-resize';
    mainArea.insertBefore(rdpResizeHandle, this._rdpEl);  // 必须在 RDP 之前，确保左边缘可拖拽
    this._bindRdpResize(rdpResizeHandle);
  }

  _buildTabActions(container) {
    this._toolbarEl = container;  // getExtraBtn() 依赖此引用

    // New button — 有 onNew 则调回调，否则调 grid.addNewRow()（内联新行）
    if (this._newLabel) {
      const btn = document.createElement('button');
      btn.className = 'ls-tb-btn-primary';
      btn.textContent = this._newLabel;
      btn.addEventListener('click', () => {
        if (this._onNew) {
          this._onNew();
        } else if (this.grid) {
          this.grid.addNewRow();
        }
      });
      container.appendChild(btn);
    }

    // Extra toolbar buttons
    this._extraTbBtns.forEach(cfg => {
      if (cfg.sepBefore) {
        const sep = document.createElement('div');
        sep.className = 'ls-tb-sep';
        container.appendChild(sep);
      }
      const btn = document.createElement('button');
      btn.className = cfg.btnStyle === 'ie' ? 'ls-tb-ie-btn' : 'ls-tb-btn-ghost';
      btn.innerHTML = (cfg.icon || '') + (cfg.label || '');
      btn.dataset.btnId = cfg.id || '';
      if (cfg.visible === false) btn.style.display = 'none';
      if (cfg.onClick) btn.addEventListener('click', cfg.onClick);
      container.appendChild(btn);
    });

    // Separator + IE buttons (shown if importExport or diffManager configured)
    const hasIE = this._importExportCfg || this._diffManagerCfg;
    if (hasIE) {
      const sep = document.createElement('div');
      sep.className = 'ls-tb-sep';
      container.appendChild(sep);

      const IMPORT_SVG = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>`;
      const EXPORT_SVG = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>`;
      const DIFF_SVG   = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M12 5l7 7-7 7"/></svg>`;

      if (this._importExportCfg) {
        const btnImport = document.createElement('button');
        btnImport.className = 'ls-tb-ie-btn';
        btnImport.dataset.btnId = 'btn-import';
        btnImport.innerHTML = IMPORT_SVG + ' 导入';
        btnImport.addEventListener('click', () => this.ieMgr?.showImport());
        container.appendChild(btnImport);

        const btnExport = document.createElement('button');
        btnExport.className = 'ls-tb-ie-btn';
        btnExport.dataset.btnId = 'btn-export';
        btnExport.innerHTML = EXPORT_SVG + ' 导出';
        btnExport.addEventListener('click', () => this.ieMgr?.showExport());
        container.appendChild(btnExport);
      }

      if (this._diffManagerCfg) {
        const btnDiff = document.createElement('button');
        btnDiff.className = 'ls-tb-ie-btn';
        btnDiff.dataset.btnId = 'btn-diff';
        btnDiff.innerHTML = DIFF_SVG + ' 对比';
        btnDiff.addEventListener('click', () => this.diffMgr?.showDiff());
        container.appendChild(btnDiff);
      }
    }
  }

  _buildSyncBtn() {
    if (!this._toolbarEl) return;
    const wrap = document.createElement('div');
    wrap.className = 'bsm-sync-wrap';
    wrap.style.cssText = 'position:relative;display:inline-flex;align-items:center';

    const btn = document.createElement('button');
    btn.className = 'ls-tb-btn-ghost bsm-sync-btn';
    btn.title = '飞书多维表格同步';
    btn.innerHTML = `
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="pointer-events:none">
        <polyline points="1 4 1 10 7 10"/><polyline points="23 20 23 14 17 14"/>
        <path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"/>
      </svg>
      <span class="bsm-status-dot" style="
        width:7px;height:7px;border-radius:50%;background:var(--text-muted,#888);
        position:absolute;top:4px;right:4px;pointer-events:none
      "></span>`;

    const menu = document.createElement('div');
    menu.className = 'bsm-sync-menu';
    menu.style.cssText = `
      display:none;position:absolute;top:100%;right:0;z-index:9999;
      background:var(--bg-primary,#1e1e2e);border:1px solid var(--border-color,#313244);
      border-radius:6px;box-shadow:0 4px 12px rgba(0,0,0,.3);min-width:150px;padding:4px 0`;
    const items = [
      { label: '立即推送到飞书', action: 'push' },
      { label: '立即从飞书拉取', action: 'pull' },
      { label: '配置字段映射…',  action: 'config' },
      { label: '解除绑定',        action: 'unbind', style: 'color:var(--danger,#e06c75)' },
    ];
    items.forEach(({ label, action, style }) => {
      const item = document.createElement('div');
      item.className = 'bsm-menu-item';
      item.textContent = label;
      item.style.cssText = `padding:7px 14px;font-size:13px;cursor:pointer;
        color:var(--text-primary);${style || ''}`;
      item.onmouseenter = () => item.style.background = 'var(--bg-hover,rgba(255,255,255,.06))';
      item.onmouseleave = () => item.style.background = '';
      item.onclick = (e) => {
        e.stopPropagation();
        menu.style.display = 'none';
        if (!this.bitableSyncMgr) return;
        if (action === 'push')   this.bitableSyncMgr.pushAll().catch(console.error);
        if (action === 'pull')   this.bitableSyncMgr.pullAll().catch(console.error);
        if (action === 'config') this.bitableSyncMgr.openBindingModal();
        if (action === 'unbind') this.bitableSyncMgr.unbind().catch(console.error);
      };
      menu.appendChild(item);
    });

    btn.onclick = (e) => {
      e.stopPropagation();
      const open = menu.style.display === 'block';
      menu.style.display = open ? 'none' : 'block';
    };
    this._syncMenuClickHandler = () => { menu.style.display = 'none'; };
    document.addEventListener('click', this._syncMenuClickHandler);

    wrap.appendChild(btn);
    wrap.appendChild(menu);
    this._toolbarEl.insertBefore(wrap, this._toolbarEl.firstChild);
    this._syncDotEl = btn.querySelector('.bsm-status-dot');
  }

  _updateSyncDot(status) {
    if (!this._syncDotEl) return;
    const colorMap = {
      unbound: 'var(--text-muted,#888)',
      synced:  '#3cb371',
      pending: '#f0a500',
      error:   '#e06c75',
    };
    this._syncDotEl.style.background = colorMap[status] || colorMap.unbound;
    this._syncDotEl.title = { unbound:'未绑定', synced:'已同步', pending:'有待同步', error:'同步出错' }[status] || '';
  }

  _bindSidebarResize(handle) {
    let startX = 0, startW = 0;
    const onMove = (e) => {
      const dx = e.clientX - startX;
      const newW = Math.max(100, Math.min(360, startW + dx));
      this._sidebarW = newW;
      this._sidebarEl.style.width = newW + 'px';
    };
    const onUp = () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    handle.addEventListener('mousedown', (e) => {
      e.preventDefault();
      startX = e.clientX;
      startW = this._sidebarEl.offsetWidth;
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    });
  }

  _bindRdpResize(handle) {
    const LS_KEY = 'ls_rdp_w';
    // 从 localStorage 恢复用户设置的宽度，写入 CSS 变量（不影响关闭状态的 width:0）
    const saved = localStorage.getItem(LS_KEY);
    this._rdpW = saved ? parseInt(saved) : 280;
    this._rdpEl.style.setProperty('--rdp-w', this._rdpW + 'px');

    let startX = 0, startW = 0;
    const onMove = (e) => {
      const dx = startX - e.clientX; // 向左拖=变宽
      const newW = Math.max(200, Math.min(700, startW + dx));
      this._rdpW = newW;
      this._rdpEl.style.setProperty('--rdp-w', newW + 'px');
    };
    const onUp = () => {
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      localStorage.setItem(LS_KEY, this._rdpW);
    };
    handle.addEventListener('mousedown', (e) => {
      e.preventDefault();
      startX = e.clientX;
      startW = this._rdpEl.offsetWidth || this._rdpW;
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    });
  }

  async _buildSidebar() {
    if (!this._showSidebar || !window.ListSidebar || !this._itemType) return;
    this.sidebar = new ListSidebar({
      containerEl: this._sidebarEl,
      itemType: this._itemType,
      extraItemHtml: this._sidebarExtraItemHtml,
      onCreate: this._sidebarOnCreate,
      onContextMenu: this._sidebarOnContextMenu,
      disableInlineRename: this._sidebarDisableInlineRename,
      onSelect: (gid) => {
        this._currentList = gid;
        if (this.vm) this.vm.setListGid(gid);
        if (this.rdp) this.rdp.setListGid(gid);
        this._onSelect?.(gid);
      },
      onListsChange: (lists) => {
        this._onListsChange?.(lists);
      },
    });
    await this.sidebar.init();
  }

  async _buildViewManager() {
    this.vm = new ViewManager({
      moduleId:  this._moduleId,
      listGid:   this._currentList,
      columns:   this._colDefs,
      toolbarEl: null,
      onChange:  () => this._onVmChange(),
    });
    await this.vm.init();
    this.vm.renderTabBar(this._tabBarEl);
  }

  _buildGrid(columns, rows) {
    this._gridEl.innerHTML = '';
    const container = document.createElement('div');
    container.style.cssText = 'height:100%;display:flex;flex-direction:column';
    this._gridEl.appendChild(container);

    // display_id 的 openDetail 标记在 _renderRows 里统一处理（_buildGrid 仅初始化，后续 setColumns 会覆盖）

    // "移至清单"是 shell 内置的上下文菜单项，自动合并页面传入的 extraContextItems
    const _moveListItem = {
      label: '移至清单', action: '_shell_move_list',
      icon: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:4px"><path d="M4 20h16M4 12h16M4 4h16"/></svg>',
    };
    const mergedCtxItems = (row) => {
      const extra = this._extraCtxItems ? this._extraCtxItems(row) : [];
      if (!row.gid) return extra;
      // 云端条目只有 owner（owner_user_gid）才能移至清单
      if (row._source === 'cloud') {
        const myGid = window.top?._authUser?.gid || window._authUser?.gid || '';
        if (myGid && row.owner_user_gid && row.owner_user_gid !== myGid) return extra;
      }
      return [_moveListItem, ...extra];
    };
    const mergedCtxAction = (action, row) => {
      if (action === '_shell_move_list') { this._openMoveToListModal(row); return; }
      if (this._onContextAction) this._onContextAction(action, row);
    };

    this.grid = new GridEditor({
      containerEl:       container,
      columns:           columns,
      rows:              rows,
      draggableRows:     false,
      rowClass:          this._rowClass,
      cellRenderer:      this._cellRenderer,
      fieldTypeIcons:    true,
      showStats:         true,
      onRowClick:        (row) => this._onRowClick(row),
      onRowsChange:      async (rows) => {
        if (this._onRowsChange) await this._onRowsChange(rows);
        if (this.bitableSyncMgr) {
          this.bitableSyncMgr.pushRows(rows).catch(e => console.warn('[bsm] pushRows:', e));
        }
      },
      onDeleteRow:       (row) => this._handleDeleteRow(row),
      extraContextItems: mergedCtxItems,
      onContextAction:   mergedCtxAction,
      onColsChange: (cols) => {
        if (!this.vm) return;
        for (const c of cols) {
          const existing = this.vm._cols.find(vc => vc.key === c.key);
          if (existing && existing.width !== c.width) {
            existing.width = c.width;
            this.vm._isDirty = true;
            this.vm._updateSaveBtn();
          }
        }
      },
      onColHeaderAction: (action, colKey) => this._onColHeaderAction(action, colKey),
    });
  }

  // ── 删除行（软删除，owner 鉴权）───────────────────────────────────────────
  async _handleDeleteRow(row) {
    // 无 gid（未保存新行）：直接从 grid 移除即可
    if (!row.gid) {
      this.grid.setRows(this.grid.getRows().filter(r => r.gid !== row.gid));
      return;
    }
    const type = this._itemType;

    if (row._source === 'cloud') {
      // 云端条目：只有 owner（owner_user_gid）可以删除
      const myGid = window.top?._authUser?.gid || window._authUser?.gid || '';
      if (myGid && row.owner_user_gid && row.owner_user_gid !== myGid) {
        alert('只有创建者才能删除该条目。');
        return;
      }
      try {
        await this.cf(`/api/${type}s/${row.gid}`, { method: 'DELETE' });
        if (this._onSelect) this._onSelect(this._currentList);
      } catch (err) {
        console.error('[ListShell._handleDeleteRow cloud]', err);
        alert('删除失败：' + err.message);
      }
    } else {
      // 非云端条目也通过云端删除
      try {
        await this.cf(`/api/${type}s/${row.gid}`, { method: 'DELETE' });
        if (this._onSelect) this._onSelect(this._currentList);
      } catch (err) {
        console.error('[ListShell._handleDeleteRow]', err);
        alert('删除失败：' + err.message);
      }
    }
  }

  // ── 移至清单（内置，跨存储自动迁移）──────────────────────────────────────────
  _openMoveToListModal(row) {
    const type = this._itemType;   // 'task'|'issue'|'knowledge'|'rule'
    const allLists = this.sidebar?._lists || [];
    const sourceIsCloud = row._source === 'cloud';
    // 本地条目可移至任意清单（含云端）；云端条目只能移至云端清单
    const eligibleLists = sourceIsCloud
      ? allLists.filter(l => l._source === 'cloud')
      : allLists;
    const badge = l => l._source === 'cloud'
      ? `<span style="font-size:9px;padding:1px 4px;border-radius:3px;background:rgba(137,180,250,.12);color:#89b4fa;margin-left:4px">云端</span>`
      : `<span style="font-size:9px;padding:1px 4px;border-radius:3px;background:rgba(249,226,175,.12);color:#f9e2af;margin-left:4px">本地</span>`;
    const items = [
      `<label style="display:flex;align-items:center;gap:8px;padding:6px 0;cursor:pointer"><input type="radio" name="ml_list" value="" ${!row.list_gid ? 'checked' : ''}> <span>[无归属]${!row.list_gid ? ' <span style="color:var(--text-faint,#6c7086);font-size:11px">(当前)</span>' : ''}</span></label>`,
      ...eligibleLists.map(l => `<label style="display:flex;align-items:center;gap:8px;padding:6px 0;cursor:pointer"><input type="radio" name="ml_list" value="${l.gid}" ${row.list_gid === l.gid ? 'checked' : ''}> <span>${l.name || l.gid}${badge(l)}${row.list_gid === l.gid ? ' <span style="color:var(--text-faint,#6c7086);font-size:11px">(当前)</span>' : ''}</span></label>`),
    ].join('');
    const mask = document.createElement('div');
    mask.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:9999;display:flex;align-items:center;justify-content:center';
    mask.innerHTML = `
      <div style="background:var(--bg-surface,#24273a);border-radius:10px;width:320px;box-shadow:0 8px 32px rgba(0,0,0,.4)">
        <div style="padding:16px 20px 12px;border-bottom:1px solid var(--border-default,#313244);font-size:14px;font-weight:600">移至清单</div>
        <div style="padding:12px 20px;max-height:280px;overflow-y:auto">${items}</div>
        <div style="padding:12px 20px;border-top:1px solid var(--border-default,#313244);display:flex;justify-content:flex-end;gap:8px">
          <button id="ml-cancel" style="padding:5px 14px;border-radius:5px;border:1px solid var(--border-default,#313244);background:transparent;color:var(--text-muted,#a6adc8);cursor:pointer">取消</button>
          <button id="ml-confirm" style="padding:5px 14px;border-radius:5px;border:none;background:var(--color-accent,#89b4fa);color:#1e1e2e;cursor:pointer">确认</button>
        </div>
      </div>`;
    document.body.appendChild(mask);
    mask.querySelector('#ml-cancel').addEventListener('click', () => mask.remove());
    mask.addEventListener('click', e => { if (e.target === mask) mask.remove(); });
    mask.querySelector('#ml-confirm').addEventListener('click', async () => {
      const selected = mask.querySelector('input[name="ml_list"]:checked')?.value || null;
      mask.remove();
      try {
        // 直接改 list_gid（云端）
        const _cloudUpdateMap = {
          task:      { url: `/api/tasks/${row.gid}`,             method: 'PUT'   },
          issue:     { url: `/api/issues/${row.gid}`,            method: 'PUT'   },
          rule:      { url: `/api/rules/${row.gid}`,             method: 'PATCH' },
          knowledge: { url: `/api/knowledge_entries/${row.gid}`, method: 'PATCH' },
        };
        const opt = _cloudUpdateMap[type] || { url: `/api/${type}s/${row.gid}`, method: 'PATCH' };
        await this.cf(opt.url, { method: opt.method, body: JSON.stringify({ list_gid: selected || null }) });
        // 通知页面刷新
        if (this._onSelect) this._onSelect(this._currentList);
      } catch (err) {
        console.error('[ListShell._openMoveToListModal]', err);
        alert('移动失败：' + err.message);
      }
    });
  }

  async _saveEntries(gid, entries) {
    const row = this._allRows.find(r => r.gid === gid);
    if (!row) return;
    try {
      const resp = await ListShell._cf(`/api/item-entries/${this._itemType}/${gid}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ entries }),
      });
      // 使用后端返回的 entries（含生成的 gid 等字段）
      if (resp?.entries && Array.isArray(resp.entries)) {
        row.entries = resp.entries;
        // 同步 EntryThread 内部状态（确保后续编辑保留 gid）
        if (this.rdp?.isOpen && this.rdp._row?.gid === gid && this.rdp._thread) {
          this.rdp._thread.setEntries(resp.entries);
        }
      } else {
        row.entries = entries;
      }
    } catch (e) {
      console.error('[ListShell._saveEntries]', e);
    }
  }

  _buildRdp() {
    const authUser = (window.top?._authUser || window._authUser || {});
    this.rdp = new RowDetailPanel(this._rdpEl, this._colDefs, async (fields) => {
      if (!fields.gid) return;
      const row = this._allRows.find(r => r.gid === fields.gid);
      if (!row) throw new Error('条目不存在');

      // 仅提取非 gid 字段作为 patch
      const patch = {};
      for (const [k, v] of Object.entries(fields)) {
        if (k === 'gid') continue;
        patch[k] = v;
      }
      if (!Object.keys(patch).length) return;

      // 直接调用云端 API（不经过 _onRowsChange，确保报错能传播到 RDP 显示"保存失败"）
      const rawCp = this._rdpSaveOpts?.cloudPath;
      const cloudBase = typeof rawCp === 'function' ? rawCp(row) : (rawCp || `/api/${this._itemType}s`);
      await ListShell._cf(`${cloudBase}/${fields.gid}`, {
        method:  'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(patch),
      });

      // 更新缓存行
      Object.assign(row, patch);
      // 刷新 grid（列表中的行数据）
      this._renderRows();
      // 刷新 RDP 面板（如果正在查看同一行，需同步 update 后的字段值）
      if (this.rdp?.isOpen && this.rdp._row?.gid === fields.gid) {
        this.rdp.refresh({ ...this.rdp._row, ...patch });
      }
    }, {
      itemType: this._itemType,
      currentUserGid:  authUser.gid || '',
      currentUserName: authUser.name || '',
      currentUserRole: authUser.system_role || authUser.org_role || authUser.role || '',
      listGid: this._currentList,
      // EntryThread context fields
      onEntriesSave: (gid, entries) => this._saveEntries(gid, entries),
    });

    // RDP 导航回调：滚动 grid 到对应行并高亮
    this.rdp._onNavCallback = (row) => {
      if (!this.grid) return;
      const ri = this.grid.getRowIndex(row.gid);
      if (ri < 0) return;
      const tr = this._gridEl.querySelector(`tr[data-ri="${ri}"]`);
      if (tr) {
        // 移除之前的高亮
        this._gridEl.querySelectorAll('.ge-row-clicked').forEach(el => el.classList.remove('ge-row-clicked'));
        tr.classList.add('ge-row-clicked');
        tr.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }
    };

    // RDP 弹出回调：打开全屏 modal
    this.rdp._onPopoutCallback = (params) => {
      this._openPopoutModal(params);
    };

    // 点击非行、非面板区域时收起 RDP
    document.addEventListener('mousedown', (e) => {
      if (!this.rdp?.isOpen) return;
      if (this._rdpEl.contains(e.target)) return;   // 点在面板内
      if (e.target.closest('tr[data-ri]')) return;  // 点在数据行上
      this.rdp.close();
    });
  }

  // ─── 事件处理 ──────────────────────────────────────────────────────────────

  _onVmChange() {
    const viewType = this._getActiveViewType();
    if (viewType === 'gantt') {
      this._showGantt();
    } else if (viewType === 'tree') {
      this._showTree();
    } else {
      this._showGrid();
    }
    this._renderRows();
  }

  _onRowClick(row) {
    if (this._extOnRowClick) {
      this._extOnRowClick(row);
      return;
    }
    const mode = localStorage.getItem('list.row_click_action') || 'sidebar';
    if (mode === 'overlay') {
      // 覆盖弹窗模式：先关闭滑窗（如果开着），再弹覆盖弹窗
      if (this.rdp?.isOpen) this.rdp.close();
      if (!this._popoutModal) this._initPopoutModal();
      if (this._popoutModal) {
        const visible = this._visibleRows || this._allRows;
        this._popoutModal.setItems(visible);
        const idx = visible.findIndex(r => r.gid === row.gid);
        if (idx >= 0) this._popoutModal.openAtIndex(idx);
      }
      return;
    }
    if (this.rdp) {
      // 默认右侧滑窗模式
      this.rdp.open(row);
      this.rdp.setCurrentGid(row.gid);
    }
  }

  _onColHeaderAction(action, colKey) {
    if (!this.vm) return;
    if      (action === 'hide')   { this.vm.setColVisible(colKey, false); }
    else if (action === 'sort')   { this.vm.toggleSort(colKey); }
    else if (action === 'group')  { this.vm.setGroup(colKey); }
    else if (action === 'filter') { this.vm.openFilterPanel(colKey); }
  }

  // ─── 视图类型切换 ──────────────────────────────────────────────────────────

  _getActiveViewType() {
    if (!this.vm?._activeViewGid) return 'grid';
    const v = this.vm._views.find(v => v.gid === this.vm._activeViewGid);
    return v?.config?.viewType || 'grid';
  }

  _showGrid() {
    this._gridEl.style.display  = '';
    this._ganttEl.classList.remove('show');
    this._treeEl.classList.remove('show');
  }

  _showGantt() {
    this._gridEl.style.display = 'none';
    this._ganttEl.classList.add('show');
    this._treeEl.classList.remove('show');
    if (!this._gantt && this._ganttFields && window.GanttChart) {
      this._gantt = new GanttChart({ containerEl: this._ganttEl });
      this._gantt.render();
    }
  }

  _showTree() {
    this._gridEl.style.display = 'none';
    this._ganttEl.classList.remove('show');
    this._treeEl.classList.add('show');

    const cfg         = this.vm ? this.vm.getActiveViewConfig() : {};
    const parentField = cfg.treeParentField || null;

    // 若未配置父级字段，显示引导提示
    if (!parentField) {
      this._treeEl.innerHTML = `
        <div class="ls-tree-guide">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="opacity:.4">
            <line x1="6" y1="4" x2="6" y2="20"/><polyline points="6 8 12 8"/><polyline points="6 14 16 14"/><polyline points="6 20 10 20"/>
          </svg>
          <p>树形视图需要配置<strong>父级字段</strong></p>
          <p class="ls-tree-guide-hint">右键点击上方视图标签 → 选择"编辑配置"，指定哪个字段作为父级指针</p>
        </div>`;
      this._tree = null;
      return;
    }

    if (!this._tree && window.TreeView) {
      this._treeEl.innerHTML = '';
      this._tree = new TreeView({
        containerEl:  this._treeEl,
        columns:      this.vm ? this.vm.getVisibleColumns() : this._colDefs,
        cellRenderer: this._cellRenderer,
        onRowClick:   (row) => this._onRowClick(row),
        rowClass:     this._rowClass,
      });
    }
  }

  _ganttRows() {
    if (!this._ganttFields) return [];
    const { startField, endField } = this._ganttFields;
    const rows = this.vm ? this.vm.applyView(this._allRows) : this._allRows;
    return rows.filter(r => !r._isGroupHeader).map(r => ({
      id:           r.gid,
      label:        r.title || r.name || r.gid,
      plan_start:   r[startField]         || null,
      plan_end:     r[endField]           || null,
      actual_start: r['actual_start']     || null,
      actual_end:   r['actual_end']       || null,
    }));
  }

  // ─── 分页渲染 ─────────────────────────────────────────────────────────────

  _renderPagination(total, totalPages) {
    if (!this._paginationEl) return;
    const page      = this._page;
    const pageSize  = this._pageSize;
    const start     = page * pageSize + 1;
    const end       = Math.min((page + 1) * pageSize, total);
    const pageSizeOptions = [50, 100, 200, 500, 1000];

    this._paginationEl.innerHTML = `
      <div class="ls-pg-info">共 <b>${total}</b> 条，显示 ${start}–${end}</div>
      <div class="ls-pg-nav">
        <button class="ls-pg-btn" id="lsPgPrev" ${page === 0 ? 'disabled' : ''}>‹ 上一页</button>
        <span class="ls-pg-cur">第 ${page + 1} / ${totalPages} 页</span>
        <button class="ls-pg-btn" id="lsPgNext" ${page >= totalPages - 1 ? 'disabled' : ''}>下一页 ›</button>
      </div>
      <div class="ls-pg-size">
        每页
        <select class="ls-pg-size-sel">
          ${pageSizeOptions.map(n => `<option value="${n}" ${n === pageSize ? 'selected' : ''}>${n} 行</option>`).join('')}
        </select>
      </div>`;

    this._paginationEl.querySelector('#lsPgPrev')?.addEventListener('click', () => {
      if (this._page > 0) { this._page--; this._renderRows(); }
    });
    this._paginationEl.querySelector('#lsPgNext')?.addEventListener('click', () => {
      if (this._page < totalPages - 1) { this._page++; this._renderRows(); }
    });
    this._paginationEl.querySelector('.ls-pg-size-sel')?.addEventListener('change', e => {
      this._pageSize = parseInt(e.target.value) || 200;
      this._page = 0;
      this._renderRows();
    });
  }

  // ─── 搜索过滤 ─────────────────────────────────────────────────────────────

  _applySearch(rows) {
    if (!this._searchText) return rows;
    const q = this._searchText;
    return rows.filter(row => {
      if (row._isGroupHeader) return true;   // 保留分组标题行
      return Object.values(row).some(v => v != null && String(v).toLowerCase().includes(q));
    });
  }

  // ─── 数据渲染 ─────────────────────────────────────────────────────────────

  _renderRows() {
    if (!this.grid) return;
    const visCols  = this.vm ? this.vm.getVisibleColumns() : this._colDefs;
    // applyView 包含 filter + sort + group（分组时含 _isGroupHeader 哨兵行）
    const viewRows = this.vm ? this.vm.applyView(this._allRows) : this._allRows;
    // 本地搜索（在 viewRows 基础上叠加，不影响 VM filter）
    const showRows = this._applySearch(viewRows);

    // Merge: keep visible columns + any extra cols from rows not in colDefs
    const dataRows = showRows.filter(r => !r._isGroupHeader);
    // 记录当前视图可见行（供滑窗/弹窗的上下条导航用）
    this._visibleRows = dataRows;
    let allCols = visCols;
    if (typeof geMergeCols === 'function') {
      allCols = geMergeCols(visCols, dataRows, new Set(['gid', 'created_at', 'updated_at', 'user_gid']));
    }
    // display_id 列始终标记 openDetail（悬停/点击触发 RDP/REM），不需要模块手动设置
    // 列顺序固定为：序号 | display_id | _actions | 其余列（标题/状态/…）
    allCols = allCols.map(c => c.key === 'display_id' ? { ...c, openDetail: true } : c);
    {
      const idIdx  = allCols.findIndex(c => c.key === 'display_id');
      const actIdx = allCols.findIndex(c => c.key === '_actions');
      if (idIdx >= 0 && actIdx >= 0 && actIdx !== idIdx + 1) {
        const [actCol] = allCols.splice(actIdx, 1);
        const newIdIdx = allCols.findIndex(c => c.key === 'display_id');
        allCols.splice(newIdIdx + 1, 0, actCol);
      }
    }

    const viewType = this._getActiveViewType();

    if (viewType === 'tree' && this._tree) {
      const cfg         = this.vm ? this.vm.getActiveViewConfig() : {};
      const parentField = cfg.treeParentField || 'parent_gid';
      const filteredRows = this.vm ? this.vm._applyFilters([...this._allRows]) : this._allRows;
      this._tree.setColumns(allCols);
      this._tree.setRows(this._applySearch(filteredRows), parentField);
    } else {
      this.grid.setColumns(allCols);
      // 传入包含分组标题行的完整 showRows，由 GridEditor 负责渲染分组标题
      if (this._enablePagination) {
        const total     = showRows.length;
        const totalPages = Math.max(1, Math.ceil(total / this._pageSize));
        if (this._page >= totalPages) this._page = totalPages - 1;
        const start = this._page * this._pageSize;
        this.grid.setRows(showRows.slice(start, start + this._pageSize));
        this._renderPagination(total, totalPages);
      } else {
        this.grid.setRows(showRows);
      }
    }

    if (this._gantt && viewType === 'gantt') {
      this._gantt.setRows(this._ganttRows());
    }

    // 每次渲染后同步可见行到滑窗导航列表（跟随视图/搜索变化）
    if (this.rdp) this.rdp.setRowList(this._visibleRows || this._allRows);
  }

  // ─── 公开 API ─────────────────────────────────────────────────────────────

  /** 更新所有行（外部 load() 调用后传入合并后的行） */
  setRows(rows) {
    this._allRows = rows || [];
    this._page = 0;    // 新数据到来时回到第一页
    this._renderRows();
    // 同步可见行列表到 RDP（用于导航上下条，随视图/搜索变化）
    if (this.rdp) this.rdp.setRowList(this._visibleRows || this._allRows);
    // RDP 开着时用最新数据刷新（避免行内操作后面板仍显示旧值）
    if (this.rdp?.isOpen && this.rdp._row?.gid) {
      const updated = this._allRows.find(r => r.gid === this.rdp._row.gid);
      if (updated) this.rdp.refresh(updated);
    }
  }

  /** 获取当前 GridEditor 的所有行（包含未保存行） */
  getGridRows() {
    return this.grid ? this.grid.getRows() : [];
  }

  /** 获取当前清单 gid */
  get currentListGid() {
    return this._currentList;
  }

  /** 获取工具栏中指定 id 的按钮元素 */
  getExtraBtn(id) {
    return this._toolbarEl?.querySelector(`[data-btn-id="${id}"]`) || null;
  }

  /** 弹出居中 modal（RDP 弹出按钮触发，使用 RowEditModal 组件）*/
  async _openPopoutModal(params) {
    // 关闭侧边栏 RDP
    if (this.rdp) this.rdp.close();

    // 惰性初始化 RowEditModal
    if (!this._popoutModal) this._initPopoutModal();
    if (!this._popoutModal) return; // RowEditModal 未加载

    // 使用当前视图可见行（与滑窗导航一致的列表）
    const items = (Array.isArray(params.rowList) && params.rowList.length)
      ? params.rowList : (this._visibleRows || this._allRows);
    this._popoutModal.setItems(items);

    // 确定在行列表中的索引
    const idx = params.rowIndex >= 0
      ? params.rowIndex
      : items.findIndex(r => r.gid === params.gid);
    if (idx < 0) return;

    // 先打开弹窗（即使 entries 还没加载）
    this._popoutModal.openAtIndex(idx);

    // 预加载 entries（从 DB/API），加载完成后更新线程
    const row = items[idx];
    if (row && (!Array.isArray(row.entries) || !row.entries.length)) {
      try {
        const resp = await ListShell._cf(`/api/item-entries/${this._itemType}/${row.gid}`);
        const result = resp?.entries || [];
        if (Array.isArray(result) && result.length) {
          row.entries = result;
          // 更新已打开的弹窗中的 EntryThread
          if (this._popoutModal?._thread) {
            this._popoutModal._threadEntries = result;
            this._popoutModal._thread.setEntries(result);
          }
        }
      } catch (e) {
        console.warn('[ListShell._openPopoutModal] preload entries failed:', e.message || e);
      }
    }
  }

  /** 惰性初始化弹出编辑弹窗（RowEditModal，独立于 RDP）*/
  _initPopoutModal() {
    if (typeof RowEditModal === 'undefined') {
      console.warn('[ListShell] RowEditModal 未加载，弹窗功能不可用');
      return;
    }
    const authUser = (window.top?._authUser || window._authUser || {});
    const shell = this;

    this._popoutModal = new RowEditModal({
      columns: this._colDefs.map(c => c.field ? c : { ...c, field: c.key }),
      entryMode: 'human',
      items: this._allRows,
      getItemEntries: (item) => {
        if (Array.isArray(item.entries)) return item.entries;
        return [];
      },
      getItemAttachments: (item) => {
        const val = item.attachments;
        if (!val) return [];
        if (Array.isArray(val)) return val;
        try { return JSON.parse(val); } catch (_) { return []; }
      },
      getItemTitle: (item) => item.title || item.name || '',
      entryIssueId: 'gid',
      entryCurrentUserGid:  authUser.gid || '',
      entryCurrentUserName: authUser.name || '',
      entryUserRole:        authUser.system_role || authUser.org_role || authUser.role || '',
      getIsCloud: (item) => item._source === 'cloud',
      itemType: this._itemType,
      showDelete: false,
      onNew: () => {
        this._popoutModal?.close().then(() => {
          if (shell._onNew) {
            shell._onNew();
          } else if (shell.grid) {
            shell.grid.addNewRow();
          }
        });
      },

      onSave: async (data) => {
        const gid = data.gid;
        if (!gid) throw new Error('条目不存在');

        // 构建要保存的字段 patch（跳过只读字段和元数据）
        const patch = {};
        shell._colDefs.forEach(c => {
          const key = c.key || c.field;
          if (key === 'gid' || key === '_actions' || key === '_source' || key === 'entries') return;
          if (c.editable === false) return;
          const val = data[key];
          if (val === undefined) return;
          if (c.type === 'attachments') {
            patch[key] = JSON.stringify(val || []);
          } else {
            patch[key] = val;
          }
        });

        // 保存 entries（如果有变更）
        if (data._entries) {
          shell._saveEntries(gid, data._entries);
        }

        if (!Object.keys(patch).length) {
          return shell._allRows.find(r => r.gid === gid);
        }

        const row = shell._allRows.find(r => r.gid === gid);
        if (!row) throw new Error('条目不存在');

        const rawCp = shell._rdpSaveOpts?.cloudPath;
        const cloudBase = typeof rawCp === 'function' ? rawCp(row) : (rawCp || `/api/${shell._itemType}s`);
        await ListShell._cf(`${cloudBase}/${gid}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(patch),
        });

        Object.assign(row, patch);
        shell._renderRows();

        // 同步刷新 RDP（如果正在查看同一行）
        if (shell.rdp?.isOpen && shell.rdp._row?.gid === gid) {
          shell.rdp.refresh({ ...shell.rdp._row, ...patch });
        }

        return row;
      },

      onClose: () => {
        // 弹窗关闭时可在此清理状态
      },
    });
  }

  /**
   * 云端 Fetch 工具（供所有使用 ListShell 的页面调用，替代各页面的 _cf 函数）
   * 直接调用 window.top.electronAPI，避免跨 realm 调用 _cloudFetch 函数引用。
   * 用法：const res = await shell.cf('/api/lists', { method: 'POST', body: JSON.stringify({...}) });
   */
  async cf(path, opts = {}) {
    // 优先用主窗口的 _cloudFetch（已验证 task/issue CRUD 可用），避免 iframe 内 fetch() 跨域问题
    const cf = window.top?._cloudFetch || window.parent?._cloudFetch || window._cloudFetch;
    if (cf) return cf(path, opts);

    // 降级：直接使用 electronAPI
    const eAPI = window.top?.electronAPI || window.parent?.electronAPI || window.electronAPI;
    if (!eAPI) throw new Error('_cloudFetch 未就绪');
    const [config, state] = await Promise.all([
      (eAPI.getConfig?.() || Promise.resolve({})).catch(() => ({})),
      (eAPI.authGetState?.() || Promise.resolve({})).catch(() => ({})),
    ]);
    const runtimeBase = await window.AI00RuntimeConfig?.getRuntimeBackendBase?.(config?.backendUrl || '')
    const baseUrl = (runtimeBase || config?.backendUrl || '').replace(/\/$/, '');
    const token = state?.token || '';
    const res = await fetch(`${baseUrl}${path}`, {
      ...opts,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'X-AI00-Token': token } : {}),
        ...(opts.headers || {}),
      },
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    return res.json();
  }

  /**
   * 判断给定清单是否为云端清单（用于路由 create/update 到 PG 或 SQLite）
   * @param {object|null} listObj - 清单对象（来自 _allLists），null 时返回 false（默认走本地）
   */
  isCloudList(listObj) {
    return listObj?._source === 'cloud';
  }

  /**
   * 按清单 GID 过滤行数据——统一入口，代替各页面散落的 if/filter。
   * @param {any[]} rows     原始行数组
   * @param {string|null} listGid  null=全部；'__no_list__'=无清单条目；其余=具体清单（bridge 已过滤）
   */
  static filterByList(rows, listGid) {
    if (listGid === ListShell.NO_LIST) return rows.filter(r => !r.list_gid);
    return rows; // null(全部) 或具体 gid：直接返回
  }

  // ── 静态工具方法（各页面共用，不再各自重复定义）────────────────────────────

  /** 云端 fetch —— 与各页面的 _cf 等价 */
  static _cf(path, opts = {}) {
    const cf = window.top?._cloudFetch || window.parent?._cloudFetch || window._cloudFetch;
    if (!cf) return Promise.reject(new Error('_cloudFetch 未就绪'));
    return cf(path, opts);
  }

  /** 云端 fetch（异常静默，失败返回 null）*/
  static async _cfSafe(path, opts = {}) {
    try { return await ListShell._cf(path, opts); }
    catch (e) { console.warn('[ListShell._cfSafe]', e.message); return null; }
  }

  /**
   * 文件上传专用 fetch —— 绕过 contextBridge 的结构化克隆。
   * Electron contextBridge 不支持 FormData 序列化，_cf 传入的 FormData 会被
   * 克隆为空对象，导致 Content-Type 被错误设置为 application/json → 422。
   * 本方法直接调用 iframe 本地 fetch，FormData 不跨 contextBridge。
   */
  static async _cfUpload(path, formData) {
    const eAPI = window.top?.electronAPI || window.parent?.electronAPI || window.electronAPI;
    const config = (await eAPI?.getConfig?.().catch(() => null)) || {};
    const state  = (await eAPI?.authGetState?.().catch(() => null)) || {};
    const runtimeBase = await window.AI00RuntimeConfig?.getRuntimeBackendBase?.(config?.backendUrl || '')
    const baseUrl = (runtimeBase || config?.backendUrl || '').replace(/\/$/, '');
    const token   = state.token || '';
    const headers = {};
    if (token) headers['X-AI00-Token'] = token;
    const res = await fetch(`${baseUrl}${path}`, { method: 'POST', body: formData, headers });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const detail = err.detail;
      const msg = typeof detail === 'string' ? detail
        : Array.isArray(detail) ? detail.map(e => e.msg || JSON.stringify(e)).join('; ')
        : detail ? JSON.stringify(detail) : `HTTP ${res.status}`;
      throw new Error(msg);
    }
    if (res.status === 204 || res.headers.get('content-length') === '0') return null;
    return res.json();
  }

  /** HTML 转义 */
  static _esc(s) {
    return String(s ?? '').replace(/[&<>"']/g,
      c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  /** 当前是否飞书登录模式 */
  static isFeishu() {
    return (window.top?._authMode ?? window.parent?._authMode ?? 'local') === 'feishu';
  }

  /** 规范化清单 GID：null/全部/无清单 → null；否则原样返回 */
  static _canonListGid(listGid) {
    return (listGid && listGid !== ListShell.NO_LIST) ? listGid : null;
  }

  /**
   * 生成标准 load() 函数（云端模式）
   * @param {object} opts
   * @param {string}   [opts.cloudPath]        云端 API 路径前缀（e.g. '/api/rules'）
   * @param {()=>string|null} opts.getCurrentList  返回当前清单 GID
   * @param {()=>any[]}       opts.getAllLists      返回所有清单数组
   * @param {()=>ListShell}   opts.getShell         返回 ListShell 实例
   * @param {(rows:any[])=>void} opts.setData        设置数据变量
   */
  static buildLoadHandler({ cloudPath, getCurrentList, getShell, setData }) {
    return async function load() {
      const listGid  = getCurrentList?.();
      const canonGid = ListShell._canonListGid(listGid);

      let cloudData = [];
      if (cloudPath) {
        const qp = new URLSearchParams();
        if (canonGid) qp.set('list_gid', canonGid);
        const cr = await ListShell._cfSafe(`${cloudPath}?${qp}`);
        cloudData = (cr?.data || []).map(r => ({ ...r, _source: 'cloud' }));
      }

      const all = ListShell.filterByList(cloudData, listGid);
      setData?.(all);
      const shell = getShell?.();
      if (shell) shell.setRows(all);
    };
  }

  /**
   * 生成标准 onRowsChange() 函数（双路径：本地 Bridge / 云端 _cf）
   * @param {object} opts
   * @param {string[]} opts.editableKeys          可编辑列 key 列表
   * @param {string}   opts.primaryKey            新行创建所需的主字段（e.g. 'title'/'name'）
   * @param {string|((gid:string)=>string)} opts.cloudUpdatePath  云端更新路径（前缀或函数）
   * @param {string}   [opts.cloudCreatePath]     云端创建路径
   * @param {(row,canonListGid)=>object} [opts.buildCreateBody]  构造创建请求体
   * @param {()=>any[]} opts.getData               返回当前数据数组
   * @param {()=>string|null} opts.getCurrentList  返回当前清单 GID
   * @param {()=>ListShell}   opts.getShell         返回 ListShell 实例
   * @param {()=>Promise<void>} opts.load          load() 函数引用（保存后刷新）
   */
  static buildRowsChangeHandler({ editableKeys, primaryKey, cloudUpdatePath, cloudCreatePath, buildCreateBody, getData, getCurrentList, getShell, load }) {
    return async function onRowsChange(newRows) {
      let didSave = false;
      const data     = getData?.() || [];
      const listGid  = getCurrentList?.();
      const canonGid = ListShell._canonListGid(listGid);

      for (const row of newRows) {
        if (row.gid) {
          const orig = data.find(r => r.gid === row.gid);
          if (!orig) continue;
          const body = {};
          editableKeys.forEach(k => { if (String(row[k] ?? '') !== String(orig[k] ?? '')) body[k] = row[k]; });
          if (!Object.keys(body).length) continue;
          try {
            const path = typeof cloudUpdatePath === 'function'
              ? cloudUpdatePath(row.gid)
              : `${cloudUpdatePath}/${row.gid}`;
            await ListShell._cf(path, { method: 'PATCH', body: JSON.stringify(body) });
            didSave = true;
          } catch (err) { console.warn('[cloud save]', err); }
        } else if (primaryKey && row[primaryKey]) {
          try {
            const cb = buildCreateBody
              ? buildCreateBody(row, canonGid)
              : { [primaryKey]: row[primaryKey], list_gid: canonGid };
            if (cloudCreatePath) {
              await ListShell._cf(cloudCreatePath, { method: 'POST', body: JSON.stringify(cb) });
            }
            didSave = true;
          } catch (err) { console.warn('[cloud create]', err); }
        }
      }

      if (didSave) {
        const shell = getShell?.();
        if (shell?.grid) shell.grid.setRows(shell.grid.getRows().filter(r => r.gid));
        await load?.();
      }
    };
  }

  destroy() {
    if (this.bitableSyncMgr) this.bitableSyncMgr.destroy();
    if (this._syncMenuClickHandler) {
      document.removeEventListener('click', this._syncMenuClickHandler);
    }
  }
}

/** 虚拟 GID：代表"无清单条目"视图，选中时仅显示 list_gid 为空的条目 */
ListShell.NO_LIST = '__no_list__';

/**
 * makeImportExport / makeDiffManager — 清单模块配置工厂
 * 消除各模块重复的 importExport / diffManager 样板代码。
 */
ListShell.makeImportExport = function(moduleId, getRows, onImport) {
  return { moduleId, getRows, onImport };
};

ListShell.makeDiffManager = function(moduleId, getRows, matchKey = 'title') {
  return {
    moduleId,
    defaultMatchKey: matchKey,
    loaders: [
      dmCurrentLoader('当前视图', getRows),
      dmExcelLoader(),
    ],
  };
};


// ── 模块级主题同步 ────────────────────────────────────────────────────────────
// 所有引入 list_shell.js 的页面自动获得主题切换能力，无需各页面单独添加监听器。
// task/issue 页面自身的监听器与此重复执行（设置相同值），不影响功能。
(function _lsInitTheme() {
  // 初始主题：从 localStorage 读取，防止父窗口消息到来前的短暂闪烁
  const _t = localStorage.getItem('system.theme') || 'dark';
  document.documentElement.setAttribute('data-theme', _t);

  // 动态主题切换：监听父窗口广播的 {type:'theme', theme:'light'|'dark'} 消息
  window.addEventListener('message', function(e) {
    if (e.data && e.data.type === 'theme' && e.data.theme) {
      document.documentElement.setAttribute('data-theme', e.data.theme);
    }
  });
}());

