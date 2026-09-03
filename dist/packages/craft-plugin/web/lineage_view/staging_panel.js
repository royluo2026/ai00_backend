'use strict';
const _resourceResolvePayload = (item, resourceGid) => ({ resource_gid: resourceGid, expected_staging_version: item.resource_version });
const _resourceIgnorePayload = item => ({ expected_staging_version: item.resource_version });
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
    this._resourceItems = [];
    this._dragPending = null; // { item, startX, startY }

    this._initDropZone();
    this._initMouseDrag();
  }

  /** 设置/更新 LayoutMode 引用（延迟初始化时调用） */
  setLayoutMode(lm) { this._layoutMode = lm; }

  async _invokeCapability(id, payload) {
    const _cloudFetch = this._cf;
    const requestBody = {
      version: 1,
      payload,
      idempotency_key: `${id}-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    };
    const request = (suffix, body) => _cloudFetch(`/api/v1/capabilities/${id}:${suffix}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    let response = await request('invoke', requestBody);
    if (response?.data?.error?.code === 'confirmation_required') {
      const confirmation = await request('confirm', requestBody);
      const token = confirmation?.data?.confirmation_token;
      if (!token) throw new Error(`能力确认失败：${id}@1`);
      response = await request('invoke', { ...requestBody, confirmation_token: token });
    }
    const result = response?.data;
    if (response?.success !== true || result?.ok !== true) {
      const detail = result?.error || response?.error || {};
      const error = new Error(detail.message || `能力调用失败：${id}@1`);
      error.code = detail.code || 'capability_invocation_failed';
      throw error;
    }
    return result.data;
  }

  /** 加载暂存数据 */
  async load() {
    try {
      const res = await this._invokeCapability('craft.bop.staging.read', {
        operation: 'list',
        version_gid: this._versionGid,
      });
      this._items = res?.data || [];
    } catch (e) {
      this._items = [];
      console.warn('[StagingPanel] load failed:', e);
    }
    try {
      const response = await this._invokeCapability('craft.resource_requirement.staging.search', {
        version_gid: this._versionGid,
        match_status: 'pending',
        page_size: 200,
      });
      this._resourceItems = response?.items || [];
    } catch (e) {
      this._resourceItems = [];
      console.warn('[StagingPanel] resource staging load failed:', e);
    }
    this._render();
  }

  /** 渲染暂存项列表 */
  _render() {
    const total = this._items.length + this._resourceItems.length;
    this._countEl.textContent = total;
    this._onCountChange(total);
    this._bodyEl.innerHTML = '';

    if (total === 0) {
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
    this._renderResourceReviews();
  }

  _renderResourceReviews() {
    if (!this._resourceItems.length) return;
    const heading = document.createElement('div');
    heading.className = 'lv-staging-empty';
    heading.textContent = 'TC 资源待匹配';
    this._bodyEl.appendChild(heading);
    for (const item of this._resourceItems) {
      const el = document.createElement('div');
      el.className = 'lv-staging-item';
      const title = document.createElement('span');
      title.className = 'lv-stg-title';
      title.textContent = `${item.raw_name || '(未命名)'} · ${item.resource_type}`;
      el.appendChild(title);
      const resolve = document.createElement('button');
      resolve.className = 'lv-stg-del';
      resolve.textContent = '匹配';
      resolve.title = '选择同类型资源标准';
      resolve.addEventListener('click', () => this.resolveResourceItem(item));
      el.appendChild(resolve);
      const ignore = document.createElement('button');
      ignore.className = 'lv-stg-del';
      ignore.textContent = '忽略';
      ignore.title = '忽略此资源需求';
      ignore.addEventListener('click', () => this.ignoreResourceItem(item));
      el.appendChild(ignore);
      this._bodyEl.appendChild(el);
    }
  }

  async resolveResourceItem(item) {
    try {
      const response = await this._invokeCapability('craft.resource_requirement.search', {
        resource_type: item.resource_type,
        status: 'active',
        page_size: 200,
      });
      const candidates = response?.items || [];
      if (!candidates.length) return this._toast('没有可用的同类型资源标准', 'error');
      const choice = window.prompt(
        `输入资源代号或 GID：\n${candidates.map(value => `${value.code} · ${value.name} · ${value.gid}`).join('\n')}`,
        candidates[0].code,
      );
      if (!choice) return;
      const selected = candidates.find(value => value.gid === choice.trim() || value.code === choice.trim());
      if (!selected) return this._toast('未找到所选资源标准', 'error');
      await this._invokeCapability('craft.resource_requirement.staging.resolve', {
        staging_gid: item.gid,
        ..._resourceResolvePayload(item, selected.gid),
      });
      await this.load();
    } catch (error) {
      this._toast('资源匹配失败: ' + error.message, 'error');
    }
  }

  async ignoreResourceItem(item) {
    try {
      await this._invokeCapability('craft.resource_requirement.staging.ignore', {
        staging_gid: item.gid,
        ..._resourceIgnorePayload(item),
      });
      await this.load();
    } catch (error) {
      this._toast('忽略失败: ' + error.message, 'error');
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
    await this._invokeCapability('craft.bop.staging.change.apply', {
      operation:       'create',
      version_gid:     this._versionGid,
      node_type:       info.nodeType || 'process',
      title:           info.title || '',
      source_type:     info.listType || null,
      source_ref_gid:  info.refGid || null,
      meta:            { link_type: info.linkType || null, is_primary: info.isPrimary ?? false },
    });
    this._toast('已添加到暂存箱', 'ok');
    await this.load();
  }

  /** 主视图 entry → soft-delete + 创建暂存项 */
  async demoteEntry(entryGid) {
    await this._invokeCapability('craft.bop.staging.lifecycle.change.apply', {
      operation: 'demote',
      entry_gid: entryGid,
    });
    this._toast('已移至暂存箱', 'ok');
    await this.load();
    this._onDemote();
  }

  /** 暂存项 → promote 到主视图 bop_entry */
  async promoteItem(stagingGid, parentBopGid, seqNo = 0) {
    const res = await this._invokeCapability('craft.bop.staging.lifecycle.change.apply', {
      operation: 'promote',
      staging_gid: stagingGid,
      parent_gid: parentBopGid || null,
      sort_order: seqNo,
    });
    this._toast('已恢复到主视图', 'ok');
    await this.load();
    this._onPromote(res?.entry_gid);
    return res?.entry_gid;
  }

  /** 删除暂存项 */
  async removeItem(stagingGid) {
    try {
      await this._invokeCapability('craft.bop.staging.change.apply', {
        operation: 'delete',
        staging_gid: stagingGid,
      });
      this._toast('已删除暂存项', 'ok');
      await this.load();
    } catch (e) {
      this._toast('删除失败: ' + e.message, 'error');
    }
  }

  /** 手动新建暂存项 */
  async createManual(title = '新暂存项', nodeType = 'process') {
    await this._invokeCapability('craft.bop.staging.change.apply', {
      operation: 'create',
      version_gid: this._versionGid,
      title,
      node_type: nodeType,
    });
    await this.load();
  }
}

// 全局暴露
window.StagingPanel = StagingPanel;
