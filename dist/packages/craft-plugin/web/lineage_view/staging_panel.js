'use strict';
/**
 * staging_panel.js — BOP Lineage 暂存箱面板
 *
 * 版本级暂存区，卡片可从主视图 demote、从关联面板拖入，后续 promote 回主视图。
 */

class StagingPanel {
  /**
   * @param {Object} opts
   * @param {HTMLElement} opts.bodyEl    - 暂存箱 body 容器（#llDsBody）
   * @param {HTMLElement} opts.countEl   - 计数显示元素（#llDsCount）
   * @param {string}      opts.versionGid
   * @param {Function}    opts.cf        - _cloudFetch
   * @param {Function}    opts.onPromote - promote 成功后回调(entryGid)
   * @param {Function}    opts.onDemote  - demote 成功后回调()
   * @param {Function}    opts.toast     - toast 提示
   */
  constructor(opts) {
    this._bodyEl    = opts.bodyEl;
    this._countEl   = opts.countEl;
    this._versionGid = opts.versionGid;
    this._cf        = opts.cf;
    this._onPromote = opts.onPromote || (() => {});
    this._onDemote  = opts.onDemote  || (() => {});
    this._onDblClick = opts.onDblClick || (() => {});
    this._onCountChange = opts.onCountChange || (() => {});
    this._toast     = opts.toast     || (() => {});
    this._layoutMode = opts.layoutMode || null;
    this._showDetailPopover = opts.showDetailPopover || null; // LayoutMode 实例引用
    this._items     = [];
    this._dragPending = null; // { item, startX, startY }

    this._initDropZone();
    this._initMouseDrag();
  }

  /** 设置/更新 LayoutMode 引用（延迟初始化时调用） */
  setLayoutMode(lm) { this._layoutMode = lm; }

  /** 加载暂存数据 */
  async load() {
    try {
      const res = await this._cf(`/api/bop/versions/${this._versionGid}/staging`);
      this._items = res.data || [];
    } catch (e) {
      this._items = [];
      console.warn('[StagingPanel] load failed:', e);
    }
    this._render();
  }

  /** 渲染暂存项列表 */
  _render() {
    this._countEl.textContent = this._items.length;
    this._onCountChange(this._items.length);
    this._bodyEl.innerHTML = '';

    if (this._items.length === 0) {
      this._bodyEl.innerHTML = '<div class="lv-staging-empty">拖入卡片或点击 + 新建</div>';
      return;
    }

    for (const item of this._items) {
      const el = document.createElement('div');
      el.className = 'lv-staging-item';
      el.dataset.stagingGid = item.gid;

      // 类型圆点
      const dot = document.createElement('span');
      dot.className = `lv-nt-dot lv-nt-${item.node_type || 'process'}`;
      el.appendChild(dot);

      // 标题
      const title = document.createElement('span');
      title.className = 'lv-stg-title';
      title.textContent = item.title || '(未命名)';
      title.title = item.title || '';
      el.appendChild(title);

      // 子节点数
      if (item.child_count > 0) {
        const badge = document.createElement('span');
        badge.className = 'lv-stg-child-count';
        badge.textContent = `+${item.child_count}`;
        badge.title = `含 ${item.child_count} 个子节点`;
        el.appendChild(badge);
      }

      // 删除按钮
      const del = document.createElement('button');
      del.className = 'lv-stg-del';
      del.innerHTML = '&times;';
      del.title = '删除暂存项';
      del.addEventListener('click', e => {
        e.stopPropagation();
        this.removeItem(item.gid);
      });
      el.appendChild(del);

      // 鼠标按下：记录 pending，后续由 document mousemove 激活自定义拖拽
      el.addEventListener('mousedown', e => {
        if (e.button !== 0) return;
        if (e.target.closest('.lv-stg-del')) return; // 不拦截删除按钮
        this._dragPending = { item, startX: e.clientX, startY: e.clientY };
      });

      // 双击 → 打开详情面板
      el.addEventListener('dblclick', e => {
        e.stopPropagation();
        this._onDblClick(item);
      });

      // 右键 → 打开节点详情弹窗（有 original_entry_gid 才能查看）
      el.addEventListener('contextmenu', e => {
        e.preventDefault();
        const gid = item.original_entry_gid;
        if (gid && this._showDetailPopover) {
          this._showDetailPopover(gid, { x: e.clientX, y: e.clientY });
        }
      });

      this._bodyEl.appendChild(el);
    }
  }

  /** 初始化 drop zone */
  _initDropZone() {
    this._bodyEl.addEventListener('dragover', e => {
      // 接受：主视图卡片 or 关联面板项
      if (e.dataTransfer.types.includes('application/x-bop-entry') ||
          e.dataTransfer.types.includes('application/x-assoc-item') ||
          e.dataTransfer.types.includes('text/plain')) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        this._bodyEl.classList.add('drag-over');
      }
    });

    this._bodyEl.addEventListener('dragleave', e => {
      if (!this._bodyEl.contains(e.relatedTarget)) {
        this._bodyEl.classList.remove('drag-over');
      }
    });

    this._bodyEl.addEventListener('drop', async e => {
      e.preventDefault();
      this._bodyEl.classList.remove('drag-over');

      // 来自关联面板
      const assocData = e.dataTransfer.getData('application/x-assoc-item');
      if (assocData) {
        try {
          const info = JSON.parse(assocData);
          await this.addFromAssociation(info);
        } catch (err) {
          this._toast('添加暂存项失败: ' + err.message, 'error');
        }
        return;
      }

      // 来自主视图卡片
      const bopEntry = e.dataTransfer.getData('application/x-bop-entry');
      if (bopEntry) {
        try {
          await this.demoteEntry(bopEntry);
        } catch (err) {
          this._toast('降级失败: ' + err.message, 'error');
        }
        return;
      }
    });
  }

  /** 自定义鼠标拖拽：暂存项 → 画布（复用 LayoutMode 的 reparent 高亮） */
  _initMouseDrag() {
    const THRESHOLD = 5;
    document.addEventListener('mousemove', e => {
      if (!this._dragPending) return;
      const dx = e.clientX - this._dragPending.startX;
      const dy = e.clientY - this._dragPending.startY;
      if (Math.abs(dx) > THRESHOLD || Math.abs(dy) > THRESHOLD) {
        const { item, startX, startY } = this._dragPending;
        this._dragPending = null;
        // 委托给 LayoutMode 的暂存箱拖拽系统
        if (this._layoutMode) {
          this._layoutMode.startStagingDrag({
            stagingGid: item.gid,
            nodeType:   item.node_type,
            title:      item.title,
            originalEntryGid: item.original_entry_gid,
          }, startX, startY);
        }
      }
    });

    document.addEventListener('mouseup', () => {
      // 如果没超过阈值就释放了，取消 pending
      this._dragPending = null;
    });
  }

  /** 从关联面板拖入 → 创建暂存项 */
  async addFromAssociation(info) {
    await this._cf(`/api/bop/versions/${this._versionGid}/staging`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        node_type:      info.nodeType || 'process',
        title:          info.title || '',
        source_type:    info.listType || null,
        source_ref_gid: info.refGid || null,
        meta:           { link_type: info.linkType || null, is_primary: info.isPrimary ?? false },
      }),
    });
    this._toast('已添加到暂存箱', 'ok');
    await this.load();
  }

  /** 主视图 entry → soft-delete + 创建暂存项 */
  async demoteEntry(entryGid) {
    await this._cf(`/api/bop/entries/${entryGid}/demote`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    });
    this._toast('已移至暂存箱', 'ok');
    await this.load();
    this._onDemote();
  }

  /** 暂存项 → promote 到主视图 bop_entry */
  async promoteItem(stagingGid, parentBopGid, seqNo = 0) {
    const res = await this._cf(`/api/bop/staging/${stagingGid}/promote`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        parent_bop_gid: parentBopGid || null,
        seq_no: seqNo,
      }),
    });
    this._toast('已恢复到主视图', 'ok');
    await this.load();
    this._onPromote(res.data?.entry_gid);
    return res.data?.entry_gid;
  }

  /** 删除暂存项 */
  async removeItem(stagingGid) {
    try {
      await this._cf(`/api/bop/staging/${stagingGid}`, { method: 'DELETE' });
      this._toast('已删除暂存项', 'ok');
      await this.load();
    } catch (e) {
      this._toast('删除失败: ' + e.message, 'error');
    }
  }

  /** 手动新建暂存项 */
  async createManual(title = '新暂存项', nodeType = 'process') {
    await this._cf(`/api/bop/versions/${this._versionGid}/staging`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, node_type: nodeType }),
    });
    await this.load();
  }
}

// 全局暴露
window.StagingPanel = StagingPanel;
