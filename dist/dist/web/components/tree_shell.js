'use strict';

/**
 * TreeShell — 结构树页面类型组件（第9种页面类型）
 *
 * 左侧版本/配置选择器 + 右侧 TreeView 带列，
 * 适用于 BOP/BOM/工艺路线/组织架构等始终以树形呈现的数据。
 *
 * 用法：
 *   const shell = new TreeShell({
 *     mountEl,
 *     sidebarTitle:         'BOP 版本',
 *     emptyText:            '请在左侧选择版本',
 *     onLoadItems:          async () => [{ gid, ... }, ...],
 *     renderItem:           (item) => htmlString,
 *     renderSelectedInfo:   (item) => htmlString,      // 子工具栏左侧信息
 *     renderToolbarActions: (item) => htmlString,      // 子工具栏右侧按钮 HTML
 *     onToolbarReady:       (item, toolbarActionsEl) => void,  // 绑定事件
 *     onSelect:             async (item) => rows[],   // 加载树数据
 *     columns:              [...],                    // TreeView 列配置
 *     cellRenderer:         { key: (val, row) => html },
 *     parentField:          'parent_gid',
 *     onRowClick:           (row) => void,
 *     onRowContextMenu:     (row, x, y) => void,      // 右键菜单回调
 *     rowClass:             (row) => cssClass,
 *   });
 *   await shell.init();
 *
 * 公开属性：
 *   shell.selectedItem        当前选中项
 *   shell.treeView            内部 TreeView 实例
 *   shell.sidebarActionsEl    侧边栏标题右侧按钮区（可向内追加按钮）
 *   shell.selectorListEl      选择器列表容器
 *   shell.selectedInfoEl      子工具栏左侧信息区
 *   shell.toolbarActionsEl    子工具栏右侧按钮区
 *   shell.treeContainerEl     树形容器 div
 *
 * 公开方法：
 *   shell.init()              渲染并加载选择器列表
 *   shell.refreshItems()      重新加载选择器列表（保留当前选中）
 *   shell.refresh()           重新加载当前选中项的树数据
 *   shell.select(item)        编程式选中某项
 *   shell.setRows(rows)       直接设置树数据（不重新请求）
 */
class TreeShell {
  constructor(opts = {}) {
    this._opts        = opts;
    this._items       = [];
    this.selectedItem = null;
    this.treeView     = null;
    // 公开 DOM 引用（init 后有效）
    this.sidebarActionsEl  = null;
    this.selectorListEl    = null;
    this.emptyStateEl      = null;
    this.contentEl         = null;
    this.selectedInfoEl    = null;
    this.toolbarActionsEl  = null;
    this.treeContainerEl   = null;
    this._ctxMenu          = null;
  }

  // ─── Public API ──────────────────────────────────────────────

  async init() {
    this._render();
    this._opts.onRender?.(this);   // DOM 已就绪，可在此访问 sidebarActionsEl 等引用
    await this.refreshItems();
  }

  async refreshItems() {
    this.selectorListEl.innerHTML = '<div class="ts-hint">加载中…</div>';
    try {
      this._items = await this._opts.onLoadItems();
      this._renderItems();
      // 若已有选中项，保持高亮
      if (this.selectedItem) {
        const still = this._items.find(i => i.gid === this.selectedItem.gid);
        if (still) this.selectedItem = still;
        this._updateActiveItem();
      }
    } catch (e) {
      this.selectorListEl.innerHTML =
        `<div class="ts-hint ts-hint-error">${_tsHe(e.message)}</div>`;
    }
  }

  async select(item) {
    this.selectedItem = item;
    this._updateActiveItem();
    this._showContent(item);
    this.treeContainerEl.innerHTML = '<div class="ts-tree-hint">加载中…</div>';
    try {
      const rows = await this._opts.onSelect(item);
      this._renderTree(rows);
    } catch (e) {
      this.treeContainerEl.innerHTML =
        `<div class="ts-tree-hint ts-hint-error">加载失败: ${_tsHe(e.message)}</div>`;
    }
  }

  /** 重新加载当前选中项的树数据 */
  async refresh() {
    if (this.selectedItem) await this.select(this.selectedItem);
  }

  /** 直接设置树数据，不重新请求（用于导入/创建后局部刷新）*/
  setRows(rows) {
    this._renderTree(rows);
  }

  // ─── Private: DOM ────────────────────────────────────────────

  _render() {
    const m = this._opts.mountEl;
    m.innerHTML = `
      <div class="ts-layout">
        <div class="ts-sidebar">
          <div class="ts-sidebar-header">
            <span class="ts-sidebar-title">${_tsHe(this._opts.sidebarTitle || '')}</span>
            <div class="ts-sidebar-actions"></div>
          </div>
          <div class="ts-selector-list"></div>
        </div>
        <div class="ts-main">
          <div class="ts-empty-state" id="_ts_empty">
            <p>${_tsHe(this._opts.emptyText || '请在左侧选择项目')}</p>
          </div>
          <div class="ts-content hidden" id="_ts_content">
            <div class="ts-sub-toolbar">
              <div class="ts-selected-info"></div>
              <div class="ts-toolbar-actions"></div>
            </div>
            <div class="ts-tree-container"></div>
          </div>
        </div>
      </div>`;

    this.sidebarActionsEl  = m.querySelector('.ts-sidebar-actions');
    this.selectorListEl    = m.querySelector('.ts-selector-list');
    this.emptyStateEl      = m.querySelector('#_ts_empty');
    this.contentEl         = m.querySelector('#_ts_content');
    this.selectedInfoEl    = m.querySelector('.ts-selected-info');
    this.toolbarActionsEl  = m.querySelector('.ts-toolbar-actions');
    this.treeContainerEl   = m.querySelector('.ts-tree-container');

    // 点击空白关闭右键菜单
    document.addEventListener('click', () => this._closeCtxMenu());
  }

  _renderItems() {
    if (!this._items.length) {
      this.selectorListEl.innerHTML = '<div class="ts-hint">暂无数据</div>';
      return;
    }
    const render = this._opts.renderItem || (i => _tsHe(i.name || i.gid));
    this.selectorListEl.innerHTML = this._items.map(item =>
      `<div class="ts-selector-item${this.selectedItem?.gid === item.gid ? ' active' : ''}"
            data-gid="${_tsHe(item.gid)}">${render(item)}</div>`
    ).join('');

    this.selectorListEl.querySelectorAll('.ts-selector-item').forEach(el => {
      el.addEventListener('click', () => {
        const item = this._items.find(i => i.gid === el.dataset.gid);
        if (item) this.select(item);
      });
    });
  }

  _updateActiveItem() {
    this.selectorListEl.querySelectorAll('.ts-selector-item').forEach(el => {
      el.classList.toggle('active', el.dataset.gid === this.selectedItem?.gid);
    });
  }

  _showContent(item) {
    this.emptyStateEl.classList.add('hidden');
    this.contentEl.classList.remove('hidden');

    if (this._opts.renderSelectedInfo) {
      this.selectedInfoEl.innerHTML = this._opts.renderSelectedInfo(item);
    }
    if (this._opts.renderToolbarActions) {
      this.toolbarActionsEl.innerHTML = this._opts.renderToolbarActions(item);
      this._opts.onToolbarReady?.(item, this.toolbarActionsEl);
    }
  }

  // ─── Private: Tree ───────────────────────────────────────────

  _renderTree(rows) {
    this.treeContainerEl.innerHTML = '';
    this.treeView = new TreeView({
      containerEl:  this.treeContainerEl,
      columns:      this._opts.columns      || [],
      cellRenderer: this._opts.cellRenderer || {},
      onRowClick:   this._opts.onRowClick   || null,
      rowClass:     this._opts.rowClass     || null,
    });
    this.treeView.setRows(rows, this._opts.parentField || 'parent_gid');

    if (this._opts.onRowContextMenu) {
      this.treeContainerEl.addEventListener('contextmenu', e => {
        const rowEl = e.target.closest('.tv-row');
        if (!rowEl) return;
        e.preventDefault();
        const gid = rowEl.dataset.gid;
        const row = rows.find(r => r.gid === gid);
        if (row) this._opts.onRowContextMenu(row, e.clientX, e.clientY);
      });
    }
  }

  // ─── Context menu helpers（供外部使用）────────────────────────

  /**
   * 显示右键菜单
   * items: [{ label, action, danger? } | 'sep']
   */
  showCtxMenu(x, y, items) {
    this._closeCtxMenu();
    const menu = document.createElement('div');
    menu.className = 'ts-ctx-menu';
    items.forEach(it => {
      if (it === 'sep') {
        menu.insertAdjacentHTML('beforeend', '<div class="ts-ctx-sep"></div>');
        return;
      }
      const div = document.createElement('div');
      div.className = 'ts-ctx-item' + (it.danger ? ' danger' : '');
      div.textContent = it.label;
      div.addEventListener('click', e => { e.stopPropagation(); this._closeCtxMenu(); it.action(); });
      menu.appendChild(div);
    });
    document.body.appendChild(menu);
    // 防止超出视口
    const vw = window.innerWidth, vh = window.innerHeight;
    const mx = Math.min(x, vw - 160), my = Math.min(y, vh - menu.offsetHeight - 8);
    menu.style.left = mx + 'px';
    menu.style.top  = my + 'px';
    this._ctxMenu = menu;
  }

  _closeCtxMenu() {
    if (this._ctxMenu) { this._ctxMenu.remove(); this._ctxMenu = null; }
  }
}

function _tsHe(s) {
  return String(s ?? '').replace(/[&<>"']/g,
    c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

