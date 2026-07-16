'use strict';
/**
 * RowEditModal — 通用条目编辑弹窗组件
 *
 * 支持两种 EntryThread 模式：
 *   entryMode='ai'     — 人机沟通（bug_tracker），AI/人图标 + 已读状态 + 复制AI指令
 *   entryMode='human'  — 人与人沟通（RDP 弹出窗），作者名 + 权限控制 + 复制链接
 *
 * 用法：
 *   const modal = new RowEditModal({
 *     columns: [...],           // 字段定义 [{field,label,type,options,placeholder,datalist,advanced}]
 *     entryMode: 'ai',          // 'ai' | 'human'
 *     items: [],                // 完整条目数组（用于导航）
 *     getItemEntries: fn,       // (item) => entries[]
 *     getItemAttachments: fn,   // (item) => attachments[]
 *     getItemTitle: fn,         // (item) => string
 *     onSave: async (data) => updatedItem,
 *     onDelete: async (item) => {},
 *     onClose: () => {},
 *     // 可选
 *     entryIssueId: '',         // AI 模式下的问题编号字段（默认 'id'）
 *     entryCurrentUserGid: '',  // human 模式下的当前用户
 *     entryUserRole: '',        // human 模式下的角色
 *     isCloud: false,           // 附件上传模式
 *     itemType: '',             // 附件 itemType
 *     showDelete: true,
 *     extraFooterButtons: [],   // [{html, onclick}]
 *     datalists: {},            // { key: [{value,label}] }
 *     advancedGroupLabel: '高级字段',
 *   });
 *   modal.openAtIndex(idx);
 *   modal.openNew(defaults);
 *   modal.close();
 *   modal.setItems(items);
 */
class RowEditModal {
  constructor(opts) {
    // ── normalize columns（兼容 ListShell 的 key/[{value,label}]/editable:false 格式）──
    this._columns = (opts.columns || []).map(c => {
      const col = { ...c };
      // ListShell uses 'key', bug_tracker uses 'field' — normalize to 'field'
      if (!col.field) col.field = col.key;
      // ListShell options: [{value,label}] → [[value,label]]
      if (col.options && col.options.length && !Array.isArray(col.options[0])) {
        col.options = col.options.map(o => [o.value, o.label !== undefined ? o.label : o.value]);
      }
      // ListShell editable:false → type 'readonly'
      if (col.editable === false && col.type !== 'readonly') {
        col._readonly = true;
      }
      return col;
    });

    this._entryMode          = opts.entryMode || 'ai';
    this._items              = opts.items || [];
    this._getItemEntries     = opts.getItemEntries || (() => []);
    this._getItemAttachments = opts.getItemAttachments || (() => []);
    this._getItemTitle       = opts.getItemTitle || ((it) => it.title || '');
    this._onSave             = opts.onSave || (async () => {});
    this._onDelete           = opts.onDelete || (async () => {});
    this._onClose            = opts.onClose || (() => {});
    this._onNew              = opts.onNew || null;          // 右上角 + 号回调（清单级新建条目）
    this._entryIssueIdField    = opts.entryIssueId || 'id';
    this._entryCurrentUserGid  = opts.entryCurrentUserGid || '';
    this._entryCurrentUserName = opts.entryCurrentUserName || '';
    this._entryUserRole        = opts.entryUserRole || '';
    this._isCloud              = !!(opts.isCloud);           // 静态默认值
    this._getIsCloud         = opts.getIsCloud || null;    // dynamic: (item) => boolean
    this._currentItem        = null;                       // 当前正在编辑的条目引用
    this._itemType           = opts.itemType || '';
    this._showDelete         = opts.showDelete !== false;
    this._extraFooterButtons = opts.extraFooterButtons || [];
    this._datalists          = opts.datalists || {};
    this._advancedGroupLabel = opts.advancedGroupLabel || '高级字段';

    this._editIdx      = -1;
    this._thread       = null;
    this._threadEntries= [];
    this._attWidget    = null;
    this._attList      = [];
    this._linkState    = { links: [], adding: false };
    this._autoSaveTimer= null;
    this._autoSaveDirty= false;
    this._saving       = false;   // 并发锁：防止重复保存
    this._closeSave    = null;    // close() 等待最终保存的 Promise resolve

    this._buildDOM();
    this._bindEvents();
  }

  /** 动态判断当前条目是否为云端 */
  _isCloudForItem() {
    if (this._getIsCloud && this._currentItem) return this._getIsCloud(this._currentItem);
    return this._isCloud;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // 公开 API
  // ═══════════════════════════════════════════════════════════════════════════

  setItems(items) {
    this._items = items || [];
    this._updateNavHeader();
  }

  openAtIndex(idx) {
    if (idx < 0 || idx >= this._items.length) return;
    this._editIdx = idx;
    const it = this._items[idx];
    this._populateFields(it);
    this._updateNavHeader();
    this._el.btnDelete.style.display = 'inline-flex';
    this._resetAutoSave();
    this._setupAutoSave();
    this._open();
  }

  openNew(defaults) {
    this._editIdx = -1;
    this._resetFields(defaults || {});
    this._updateNavHeader();
    this._el.btnDelete.style.display = 'none';
    this._resetAutoSave();
    this._setupAutoSave();
    this._open();
  }

  async close() {
    if (this._autoSaveTimer) { clearTimeout(this._autoSaveTimer); this._autoSaveTimer = null; }
    if (this._autoSaveDirty) {
      // 等待最终保存完成再关闭，避免 DOM 销毁后异步保存失败
      await this._doAutoSave();
    } else if (this._saving) {
      // 正在保存中，等待完成
      await new Promise(resolve => { this._closeSave = resolve; });
    }
    this._el.overlay.classList.remove('open');
    document.removeEventListener('keydown', this._boundKeydown);
    this._onClose();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // DOM 构建
  // ═══════════════════════════════════════════════════════════════════════════

  _buildDOM() {
    const self = this;

    // overlay
    const overlay = document.createElement('div');
    overlay.className = 'rem-overlay';
    overlay.setAttribute('tabindex', '-1');
    overlay.addEventListener('click', (e) => { if (e.target === overlay) self.close(); });

    // datalists
    let dlHtml = '';
    Object.entries(this._datalists).forEach(([key, opts]) => {
      dlHtml += `<datalist id="rem-dl-${key}">${opts.map(o =>
        `<option value="${REM_escAttr(o.value || o)}">${REM_escAttr(o.label || '')}</option>`
      ).join('')}</datalist>`;
    });

    // build left panel fields
    const mainFields = this._columns.filter(c => !c.advanced);
    const advFields  = this._columns.filter(c => c.advanced);
    const hasAdvanced = advFields.length > 0;

    let fieldsHtml = mainFields.map(c => this._renderFieldHTML(c)).join('');

    let advHtml = '';
    if (hasAdvanced) {
      advHtml = `
        <div class="rem-adv-toggle collapsed" id="remAdvToggle">
          <span class="rem-adv-chevron"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg></span>
          ${REM_esc(this._advancedGroupLabel)}
        </div>
        <div class="rem-adv-group collapsed" id="remAdvGroup">
          ${advFields.map(c => this._renderFieldHTML(c)).join('')}
        </div>`;
    }

    // entry section HTML (for EntryThread)
    const entrySectionHTML = `
      <div class="entry-section">
        <div class="entry-sec-hdr">具体详情 <span class="entry-sec-count" id="etDetailCount"></span><button class="entry-sec-add-btn" onclick="window._etAdd(event,'detail',null)" title="添加详情条目">+</button></div>
        <div id="etDetailEntries"></div>
        <button class="entry-add-btn" onclick="window._etAdd(event,'detail',null)">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          添加详情
        </button>
      </div>
      <div class="entry-section" style="margin-top:12px">
        <div class="entry-sec-hdr collapsible collapsed" id="historyHeader">
          沟通历史 <span class="entry-sec-count" id="etHistoryCount"></span>
          <span class="entry-sec-chevron"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg></span>
        </div>
        <div class="entry-sec-body collapsed" id="historyBody">
          <div id="etHistoryEntries"></div>
          <button class="entry-add-btn" onclick="window._etAdd(event,'history',null)">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            添加沟通记录
          </button>
        </div>
      </div>
      <div class="entry-section" style="margin-top:12px" id="remChangeLogSection" style="display:none">
        <div class="entry-sec-hdr collapsible collapsed" id="remChangeLogHeader">
          变更历史 <span class="entry-sec-count" id="remChangeLogCount"></span>
          <span class="entry-sec-chevron"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg></span>
        </div>
        <div class="entry-sec-body collapsed" id="remChangeLogBody">
          <div id="remChangeLogList" style="font-size:12px;color:var(--text-muted)">加载中…</div>
        </div>
      </div>`;

    // extra footer buttons
    const extraBtnsHtml = this._extraFooterButtons.map((b, i) =>
      `<button class="btn" id="remExtraBtn${i}">${b.html || ''}</button>`
    ).join('');

    // build modal
    const modalHTML = `
      <div class="rem-modal">
        <div class="rem-head">
          <span class="rem-head-id" id="remHeadId"></span>
          <span class="rem-head-sep">|</span>
          <span class="rem-head-title" id="remTitle">新增条目</span>
          <span class="rem-head-spacer"></span>
          <button class="rem-nav-btn rem-nav-big" id="remNavPrev" title="上一条">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="18 15 12 9 6 15"/></svg>
          </button>
          <span class="rem-nav-label" id="remNavLabel"></span>
          <button class="rem-nav-btn rem-nav-big" id="remNavNext" title="下一条">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
          </button>
          <button class="rem-nav-btn" id="remBtnNewEntry" title="新增条目">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          </button>
          <button class="rem-close-btn" id="remCloseBtn">&times;</button>
        </div>
        <div class="rem-body">
          <div class="rem-left">
            ${fieldsHtml}
            ${advHtml}
          </div>
          <div class="rem-right">
            <div class="rem-img-strip" id="remImgStrip"></div>
            <div id="remEtMount">${entrySectionHTML}</div>
          </div>
        </div>
        <div class="rem-foot">
          <button class="btn rem-btn-danger" id="remBtnDelete" style="display:none">删除</button>
          <span class="rem-save-status" id="remSaveStatus"></span>
          <div class="spacer" style="flex:1"></div>
          ${extraBtnsHtml}
          <button class="btn" id="remBtnClose">关闭</button>
        </div>
        ${dlHtml}
      </div>`;

    overlay.innerHTML = modalHTML;
    document.body.appendChild(overlay);

    // cache element refs
    this._el = {
      overlay,
      headId:    overlay.querySelector('#remHeadId'),
      title:     overlay.querySelector('#remTitle'),
      navLabel:  overlay.querySelector('#remNavLabel'),
      navPrev:   overlay.querySelector('#remNavPrev'),
      navNext:   overlay.querySelector('#remNavNext'),
      btnDelete: overlay.querySelector('#remBtnDelete'),
      saveStatus:overlay.querySelector('#remSaveStatus'),
      imgStrip:  overlay.querySelector('#remImgStrip'),
      etMount:   overlay.querySelector('#remEtMount'),
      advToggle: overlay.querySelector('#remAdvToggle'),
      advGroup:  overlay.querySelector('#remAdvGroup'),
    };

    // extra footer button refs
    this._extraFooterButtons.forEach((b, i) => {
      const btn = overlay.querySelector('#remExtraBtn' + i);
      if (btn && b.onclick) btn.addEventListener('click', b.onclick);
    });

    // cache field input refs
    this._inputEls = {};
    this._columns.forEach(c => {
      const el = overlay.querySelector('[data-rem-field="' + c.field + '"]');
      if (el) this._inputEls[c.field] = el;
    });
  }

  _renderFieldHTML(col) {
    const f = col.field;
    const label = col.label || f;
    const ph = col.placeholder || '';
    const dlId = col.datalist ? `rem-dl-${col.datalist}` : '';
    const dlAttr = dlId ? ` list="${dlId}"` : '';
    const autocomplete = col.autocomplete || (dlId ? 'off' : '');
    const readonlyAttr = col._readonly ? ' readonly' : '';
    const readonlyStyle = col._readonly ? ' style="color:var(--faint);font-size:11px;cursor:default"' : '';

    switch (col.type) {
      case 'enum':
        const opts = col.options || [];
        return `<div class="rem-field">
          <label>${REM_esc(label)}</label>
          <select data-rem-field="${REM_escAttr(f)}"${col._readonly ? ' disabled' : ''}>${opts.map(([v, label2]) =>
            `<option value="${REM_escAttr(v)}">${REM_esc(label2 || v)}</option>`
          ).join('')}</select>
        </div>`;

      case 'textarea':
        return `<div class="rem-field">
          <label>${REM_esc(label)}</label>
          <textarea data-rem-field="${REM_escAttr(f)}" placeholder="${REM_escAttr(ph)}" rows="3"${readonlyAttr}${readonlyStyle}></textarea>
        </div>`;

      case 'date':
        return `<div class="rem-field">
          <label>${REM_esc(label)}</label>
          <input data-rem-field="${REM_escAttr(f)}" type="date"${dlAttr} autocomplete="${autocomplete}"${readonlyAttr}${readonlyStyle}>
        </div>`;

      case 'boolean':
        return `<div class="rem-field">
          <label style="display:flex;align-items:center;gap:6px">
            <input data-rem-field="${REM_escAttr(f)}" type="checkbox" style="width:auto"${col._readonly ? ' disabled' : ''}>
            ${REM_esc(label)}
          </label>
        </div>`;

      case 'attachments':
        return `<div class="rem-field">
          <label>${REM_esc(label)}</label>
          <div data-rem-field="${REM_escAttr(f)}" id="remAttMount-${f}"></div>
        </div>`;

      case 'links':
        return `<div class="rem-field">
          <label>${REM_esc(label)}</label>
          <div class="rem-links-editor" data-rem-field="${REM_escAttr(f)}" id="remLinksEditor-${f}"></div>
          <button class="rem-lk-add-link" data-rem-link-add="${f}">+ 链接</button>
        </div>`;

      case 'readonly':
        return `<div class="rem-field">
          <label>${REM_esc(label)}</label>
          <input data-rem-field="${REM_escAttr(f)}" readonly style="color:var(--faint);font-size:11px">
        </div>`;

      default: // text
        return `<div class="rem-field">
          <label>${REM_esc(label)}</label>
          <input data-rem-field="${REM_escAttr(f)}" placeholder="${REM_escAttr(ph)}"${dlAttr} autocomplete="${autocomplete}"${readonlyAttr}${readonlyStyle}>
        </div>`;
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // 事件绑定
  // ═══════════════════════════════════════════════════════════════════════════

  _bindEvents() {
    const self = this;

    // close buttons
    this._el.overlay.querySelector('#remCloseBtn').addEventListener('click', () => self.close());
    this._el.overlay.querySelector('#remBtnClose').addEventListener('click', () => self.close());

    // navigation
    this._el.navPrev.addEventListener('click', () => self._navPrev());
    this._el.navNext.addEventListener('click', () => self._navNext());

    // delete
    this._el.btnDelete.addEventListener('click', () => self._deleteItem());

    // new entry button in header（清单级新建条目）
    const btnNewEntry = this._el.overlay.querySelector('#remBtnNewEntry');
    if (this._onNew) {
      btnNewEntry.addEventListener('click', () => self._onNew());
    } else {
      btnNewEntry.style.display = 'none';
    }

    // advanced toggle
    if (this._el.advToggle) {
      this._el.advToggle.addEventListener('click', () => {
        const collapsed = this._el.advToggle.classList.toggle('collapsed');
        this._el.advGroup.classList.toggle('collapsed', collapsed);
      });
    }

    // history toggle
    const historyHeader = this._el.overlay.querySelector('#historyHeader');
    const historyBody   = this._el.overlay.querySelector('#historyBody');
    if (historyHeader && historyBody) {
      historyHeader.addEventListener('click', () => {
        const collapsed = historyHeader.classList.toggle('collapsed');
        historyBody.classList.toggle('collapsed', collapsed);
      });
    }

    // change-log toggle
    const clHeader = this._el.overlay.querySelector('#remChangeLogHeader');
    const clBody   = this._el.overlay.querySelector('#remChangeLogBody');
    if (clHeader && clBody) {
      clHeader.addEventListener('click', () => {
        const collapsed = clHeader.classList.toggle('collapsed');
        clBody.classList.toggle('collapsed', collapsed);
      });
    }

    // link add buttons
    this._el.overlay.querySelectorAll('[data-rem-link-add]').forEach(btn => {
      btn.addEventListener('click', () => {
        self._linkState.adding = true;
        self._renderLinkPills(btn.previousElementSibling);
      });
    });

    // keyboard
    this._boundKeydown = (e) => self._onKeydown(e);
  }

  _onKeydown(e) {
    if (e.key === 'Escape') {
      const ae = document.activeElement;
      if (ae && (ae.tagName === 'INPUT' || ae.tagName === 'TEXTAREA' || ae.tagName === 'SELECT')) {
        ae.blur();
      } else {
        this.close();
      }
    } else if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      window._etAdd({ target: this._el.etMount }, 'detail', null);
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // 打开/关闭
  // ═══════════════════════════════════════════════════════════════════════════

  _open() {
    this._el.overlay.classList.add('open');
    document.addEventListener('keydown', this._boundKeydown);
    // 让 overlay 夺走键盘焦点，防止底层 grid 继续接收 keydown 事件
    requestAnimationFrame(() => {
      const firstInput = this._el.overlay.querySelector('input:not([disabled]),textarea:not([disabled]),select:not([disabled])');
      if (firstInput) firstInput.focus();
      else this._el.overlay.focus();
    });
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // 导航
  // ═══════════════════════════════════════════════════════════════════════════

  _navPrev() {
    if (this._editIdx > 0) this.openAtIndex(this._editIdx - 1);
  }

  _navNext() {
    if (this._editIdx >= 0 && this._editIdx < this._items.length - 1) {
      this.openAtIndex(this._editIdx + 1);
    }
  }

  _updateNavHeader() {
    const idx = this._editIdx;
    const total = this._items.length;
    if (idx >= 0 && idx < total) {
      const it = this._items[idx];
      // 优先用 display_id（清单中的短ID），否则用 entryIssueIdField 并截取末8位
      const rawId = it.display_id != null ? String(it.display_id) : '';
      const id    = rawId || it[this._entryIssueIdField] || it.id || '';
      this._el.headId.textContent = id ? '#' + (rawId ? id : String(id).slice(-8)) : '';
      const title = this._getItemTitle(it);
      this._el.title.textContent = title || '';
      this._el.navLabel.textContent = total > 0 ? `${idx + 1}/${total}` : '';
      this._el.navPrev.disabled = idx <= 0;
      this._el.navNext.disabled = idx >= total - 1 || total === 0;
    } else {
      this._el.headId.textContent = '';
      this._el.title.textContent = '新增条目';
      this._el.navLabel.textContent = '';
      this._el.navPrev.disabled = true;
      this._el.navNext.disabled = true;
    }
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // 字段填充/重置
  // ═══════════════════════════════════════════════════════════════════════════

  _populateFields(item) {
    const it = item || {};
    this._currentItem = it;
    this._columns.forEach(c => {
      if (c.type === 'attachments') {
        const attachments = this._getItemAttachments(it);
        this._renderAttachmentsWidget(attachments);
        this._renderImgStrip(attachments);
        return;
      }
      if (c.type === 'links') {
        this._linkState.links = (it[c.field] || []).map(l => ({
          type: l.type || REM_detectLinkType(l.url || ''),
          url: l.url || '',
          title: l.title || ''
        }));
        const editorEl = this._el.overlay.querySelector('[data-rem-field="' + c.field + '"]');
        if (editorEl) this._renderLinkPills(editorEl);
        return;
      }
      const el = this._inputEls[c.field];
      if (!el) return;
      let val = it[c.field];
      if (val === undefined || val === null) val = '';
      if (c.type === 'boolean') {
        el.checked = !!val;
      } else if (el.tagName === 'SELECT') {
        el.value = String(val);
      } else {
        el.value = String(val);
      }
    });

    // entries
    const entries = this._getItemEntries(it);
    this._threadEntries = JSON.parse(JSON.stringify(entries || []));
    if (this._entryMode === 'ai') {
      this._threadEntries.forEach(e => {
        if (!e.ai_status) e.ai_status = 'unread';
        if (e.read_by_ai !== undefined) { e.ai_status = e.read_by_ai ? 'read' : 'unread'; delete e.read_by_ai; }
        // 人加载了 REM = 已读，AI 条目自动标为 human 已读
        if (e.author === 'ai') e.read_by_human = true;
      });
    }
    const issueId = String(it[this._entryIssueIdField] || it.id || '');
    this._initThread(this._threadEntries, issueId);

    // 变更历史（飞书模式 + 有 gid 时显示）
    const clSection = this._el.overlay.querySelector('#remChangeLogSection');
    if (clSection) {
      const isCloud = this._isCloudForItem();
      const itemGid = it.gid || it.cloud_gid || '';
      if (isCloud && itemGid && this._itemType) {
        clSection.style.display = '';
        this._loadChangeLogs(this._itemType, itemGid);
      } else {
        clSection.style.display = 'none';
      }
    }
  }

  _loadChangeLogs(itemType, itemGid) {
    const listEl  = this._el.overlay.querySelector('#remChangeLogList');
    const countEl = this._el.overlay.querySelector('#remChangeLogCount');
    if (!listEl) return;
    listEl.textContent = '加载中…';
    const fetch = window._cloudFetch || window.parent?._cloudFetch;
    if (!fetch) { listEl.textContent = '（无云端连接）'; return; }
    fetch(`/api/change-logs?item_type=${encodeURIComponent(itemType)}&item_gid=${encodeURIComponent(itemGid)}&limit=50`)
      .then(r => r.json())
      .then(rows => {
        if (!Array.isArray(rows) || rows.length === 0) {
          listEl.innerHTML = '<div style="color:var(--text-muted);padding:6px 0">暂无变更记录</div>';
          if (countEl) countEl.textContent = '';
          return;
        }
        if (countEl) countEl.textContent = rows.length > 0 ? ` (${rows.length})` : '';
        const FIELD_LABELS = {
          title: '标题', status: '状态', priority: '优先级', description: '描述',
          due_date: '截止日期', plan_start: '计划开始', plan_end: '计划结束',
          actual_start: '实际开始', actual_end: '实际完成', severity: '严重程度',
          assignee_team_gid: '负责人', list_gid: '所在清单',
        };
        listEl.innerHTML = rows.map(r => {
          const label = FIELD_LABELS[r.field_name] || r.field_name;
          const oldV = r.old_value != null ? r.old_value : '—';
          const newV = r.new_value != null ? r.new_value : '—';
          const dt = r.changed_at ? new Date(r.changed_at).toLocaleString('zh-CN', { hour12: false }) : '';
          return `<div style="display:flex;gap:6px;padding:4px 0;border-bottom:1px solid var(--border-light,#e0e0e0)">
            <span style="color:var(--text-muted);min-width:110px;flex-shrink:0">${dt}</span>
            <span style="color:var(--accent,#5b9bd5);min-width:60px;flex-shrink:0">${label}</span>
            <span style="color:var(--text-muted)"><del>${oldV}</del> → </span>
            <span>${newV}</span>
          </div>`;
        }).join('');
      })
      .catch(() => { listEl.textContent = '加载失败'; });
  }

  _resetFields(defaults) {
    this._currentItem = null;
    const def = defaults || {};
    this._columns.forEach(c => {
      if (c.type === 'attachments') {
        this._renderAttachmentsWidget(def[c.field] || []);
        this._renderImgStrip(def[c.field] || []);
        return;
      }
      if (c.type === 'links') {
        this._linkState.links = (def[c.field] || []).map(l => ({
          type: l.type || REM_detectLinkType(l.url || ''),
          url: l.url || '',
          title: l.title || ''
        }));
        const editorEl = this._el.overlay.querySelector('[data-rem-field="' + c.field + '"]');
        if (editorEl) this._renderLinkPills(editorEl);
        return;
      }
      const el = this._inputEls[c.field];
      if (!el) return;
      let val = def[c.field];
      if (val === undefined || val === null) val = c.default !== undefined ? c.default : '';
      if (c.type === 'boolean') {
        el.checked = !!val;
      } else if (el.tagName === 'SELECT') {
        el.value = String(val);
        // if value not in options, use first option
        if (el.selectedIndex < 0 && el.options.length > 0) el.selectedIndex = 0;
      } else {
        el.value = String(val);
      }
    });

    this._threadEntries = [];
    this._initThread([], '');
    this._el.imgStrip.classList.remove('show');
    this._el.imgStrip.innerHTML = '';
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // 收集表单数据
  // ═══════════════════════════════════════════════════════════════════════════

  _collectData() {
    if (this._thread) this._thread.collectTexts();

    const data = {};
    this._columns.forEach(c => {
      if (c.type === 'attachments') {
        data[c.field] = [...this._attList];
      } else if (c.type === 'links') {
        data[c.field] = this._linkState.links.filter(l => l.url);
      } else {
        const el = this._inputEls[c.field];
        if (!el) { data[c.field] = ''; return; }
        if (c.type === 'boolean') {
          data[c.field] = el.checked;
        } else {
          data[c.field] = el.value;
        }
      }
    });
    data._entries = this._threadEntries;
    data._idx = this._editIdx;
    data._isNew = this._editIdx < 0;
    // 附带 gid（从当前编辑的条目获取，用于回调中定位）
    if (this._editIdx >= 0 && this._items[this._editIdx]) {
      data.gid = this._items[this._editIdx].gid || this._items[this._editIdx].id || '';
    }
    return data;
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // 自动保存
  // ═══════════════════════════════════════════════════════════════════════════

  _resetAutoSave() {
    this._autoSaveDirty = false;
    if (this._autoSaveTimer) { clearTimeout(this._autoSaveTimer); this._autoSaveTimer = null; }
  }

  _scheduleAutoSave() {
    if (this._editIdx < 0) {
      // 新建条目：检查是否有值得保存的内容
      const data = this._collectData();
      const hasContent = this._columns.some(c => {
        if (c.type === 'boolean') return false;
        const val = data[c.field];
        return val !== '' && val !== null && val !== undefined && (!Array.isArray(val) || val.length > 0);
      });
      if (!hasContent) return;
    }
    this._autoSaveDirty = true;
    if (this._saving) {
      // 正在保存中，只标记脏，保存完成后会自动重试
      this._el.saveStatus.textContent = '未保存';
      return;
    }
    this._el.saveStatus.textContent = '未保存';
    if (this._autoSaveTimer) clearTimeout(this._autoSaveTimer);
    this._autoSaveTimer = setTimeout(() => this._doAutoSave(), 1500);
  }

  async _doAutoSave() {
    if (!this._autoSaveDirty) return;
    if (this._saving) return;   // 已有保存在进行中
    this._saving = true;
    this._autoSaveDirty = false;
    if (this._autoSaveTimer) { clearTimeout(this._autoSaveTimer); this._autoSaveTimer = null; }
    this._el.saveStatus.className = 'rem-save-status';
    this._el.saveStatus.textContent = '保存中…';
    try {
      const data = this._collectData();
      const updated = await this._onSave(data);
      // 如果 onSave 返回 falsy（如空标题被拒绝），保持 _editIdx 不变
      if (!updated) {
        this._el.saveStatus.textContent = '已保存';
        this._saving = false;
        return;
      }
      this._el.saveStatus.textContent = '已保存';
      this._currentItem = updated;

      // 新建条目创建成功 → 更新索引
      if (this._editIdx < 0) {
        const foundIdx = this._items.findIndex(it => it === updated);
        if (foundIdx >= 0) {
          this._editIdx = foundIdx;
          this._updateNavHeader();
          this._el.btnDelete.style.display = 'inline-flex';
        }
        this._refreshReadonlyFields(updated);
      }
      // 同步回 entries（内容或数量变化时刷新线程）
      const freshEntries = this._getItemEntries(updated);
      if (freshEntries && freshEntries.length !== this._threadEntries.length) {
        this._threadEntries = JSON.parse(JSON.stringify(freshEntries));
        if (this._entryMode === 'ai') {
          this._threadEntries.forEach(e => {
            if (!e.ai_status) e.ai_status = 'unread';
          });
        }
        if (this._thread) {
          const issueId = String(updated[this._entryIssueIdField] || updated.id || '');
          this._thread.setEntries(this._threadEntries, issueId);
        }
      }
    } catch(e) {
      this._el.saveStatus.textContent = '保存失败';
      this._el.saveStatus.className = 'rem-save-status error';
      console.error('[RowEditModal._doAutoSave]', e);
    } finally {
      this._saving = false;
      // 通知 close() 等待者
      if (this._closeSave) { this._closeSave(); this._closeSave = null; }
      // 保存期间有新变更 → 安排下一次保存
      if (this._autoSaveDirty) this._scheduleAutoSave();
    }
  }

  _setupAutoSave() {
    const self = this;
    // Wire change events to all form fields
    this._columns.forEach(c => {
      if (c.type === 'attachments' || c.type === 'links') return; // handled separately
      if (c._readonly) return; // readonly fields don't auto-save
      const el = this._inputEls[c.field];
      if (!el) return;
      const handler = () => self._scheduleAutoSave();
      // Replace element to remove old listeners
      const parent = el.parentNode;
      const clone = el.cloneNode(true);
      clone.value = el.value;
      if (c.type === 'boolean') clone.checked = el.checked;
      // Preserve data-rem-field attribute
      clone.setAttribute('data-rem-field', c.field);
      if (c.datalist) clone.setAttribute('list', 'rem-dl-' + c.datalist);
      parent.replaceChild(clone, el);
      this._inputEls[c.field] = clone;
      clone.addEventListener('change', handler);
      if (clone.tagName === 'INPUT' && clone.type === 'text') {
        clone.addEventListener('input', handler);
      }
    });
  }

  _refreshReadonlyFields(item) {
    this._columns.forEach(c => {
      if (c.type === 'readonly') {
        const el = this._inputEls[c.field];
        if (el) el.value = item[c.field] || '';
      }
    });
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // EntryThread
  // ═══════════════════════════════════════════════════════════════════════════

  _initThread(entries, issueId) {
    const mountEl = this._el.etMount;
    if (!mountEl) return;
    const self = this;
    if (this._thread) {
      this._thread.setEntries(entries, issueId);
    } else {
      this._thread = new EntryThread({
        mountEl,
        mode: this._entryMode,
        entries,
        issueId,
        currentUserGid: this._entryCurrentUserGid,
        currentUserName: this._entryCurrentUserName,
        userRole: this._entryUserRole,
        isCloud: this._isCloudForItem(),
        onChange: (ents) => { self._threadEntries = ents; self._scheduleAutoSave(); },
        onSave: () => {},
        onStatusMsg: (msg) => {
          if (self._el.saveStatus) {
            self._el.saveStatus.textContent = msg;
            setTimeout(() => { self._el.saveStatus.textContent = '已保存'; }, 1500);
          }
        },
      });
      this._thread._bindGlobal('remEtMount');
      this._thread.setEntries(entries, issueId);
    }
    this._threadEntries = this._thread.getEntries();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // AttachmentsWidget
  // ═══════════════════════════════════════════════════════════════════════════

  _renderAttachmentsWidget(attachments) {
    // find the attachments mount point
    const attCol = this._columns.find(c => c.type === 'attachments');
    if (!attCol) return;
    const el = document.getElementById('remAttMount-' + attCol.field);
    if (!el) return;
    if (typeof AttachmentsWidget === 'undefined') {
      el.innerHTML = '<span style="font-size:11px;color:var(--faint)">附件组件未加载</span>';
      return;
    }
    const itemId = this._editIdx >= 0
      ? (this._items[this._editIdx]?.[this._entryIssueIdField] || this._items[this._editIdx]?.id || '')
      : '';
    const list = Array.isArray(attachments) ? [...attachments] : [];
    this._attList = list;
    const self = this;
    const isCloud = this._isCloudForItem();
    this._attWidget = new AttachmentsWidget({
      el,
      attachments: list,
      isCloud,
      itemType: this._itemType,
      itemGid: itemId,
      readonly: false,
      onSave: (newList) => {
        self._attList = newList;
        self._renderImgStrip(newList);
        self._scheduleAutoSave();
      },
    });
    this._attWidget.render();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // 图片 strip
  // ═══════════════════════════════════════════════════════════════════════════

  _renderImgStrip(attachments) {
    const strip = this._el.imgStrip;
    if (!strip) return;
    const arr = Array.isArray(attachments) ? attachments : [];
    const images = arr.filter(a => {
      const name = (a.name || a.filename || '').toLowerCase();
      const mime = a.mime || a.mime_type || '';
      return /\.(png|jpg|jpeg|gif|webp|svg|bmp)$/i.test(name) || mime.startsWith('image/');
    });
    if (!images.length) { strip.classList.remove('show'); strip.innerHTML = ''; return; }
    strip.innerHTML = '';
    strip.classList.add('show');
    const allImages = images; // 保存完整图片列表供点击时传给画廊
    images.forEach((att, i) => {
      const src = att.url || att.path || '';
      const name = att.name || att.filename || 'image';
      const thumb = document.createElement('div');
      thumb.className = 'rem-img-thumb';
      thumb.title = name;
      thumb.innerHTML = src
        ? `<img src="${REM_escAttr(src)}" alt="${REM_escAttr(name)}" loading="lazy" onerror="this.parentElement.innerHTML='<svg width=&quot;22&quot; height=&quot;22&quot; viewBox=&quot;0 0 24 24&quot; fill=&quot;none&quot; stroke=&quot;#a6e3a1&quot; stroke-width=&quot;1.5&quot;><rect x=&quot;3&quot; y=&quot;3&quot; width=&quot;18&quot; height=&quot;18&quot; rx=&quot;2&quot;/><circle cx=&quot;8.5&quot; cy=&quot;8.5&quot; r=&quot;1.5&quot;/><polyline points=&quot;21 15 16 10 5 21&quot;/></svg>'">`
        : '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#a6e3a1" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>';
      thumb.addEventListener('click', (e) => {
        e.stopPropagation();
        if (src && typeof AttachmentsWidget !== 'undefined' && typeof _b64EncUtf8 !== 'undefined') {
          // 传递全部图片列表 + 当前索引，让画廊支持多图导航
          const attJson = _b64EncUtf8(JSON.stringify(allImages));
          const titleB64 = _b64EncUtf8(name);
          AttachmentsWidget._openCardOverlay('image_gallery', {
            attachments: attJson,
            title: titleB64,
            idx: String(i),
          });
        }
      });
      strip.appendChild(thumb);
    });
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // 链接编辑器
  // ═══════════════════════════════════════════════════════════════════════════

  _renderLinkPills(el) {
    if (!el) return;
    const self = this;
    const arr = this._linkState.links;
    let html = arr.map((l, i) => {
      const type = l.type || 'web';
      const icon = REM_LINK_ICONS[type] || REM_LINK_ICONS['web'];
      const title = l.title || l.url || '';
      return `<span class="rem-lk-pill" title="${REM_escAttr(title)}" data-lk-idx="${i}">
        <span class="rem-lk-pill-icon">${icon}</span>
        <span class="rem-lk-pill-title">${REM_esc(title.slice(0, 20))}</span>
        <span class="rem-lk-pill-del" data-lk-del="${i}">&times;</span>
      </span>`;
    }).join('');
    if (this._linkState.adding) {
      html += '<span class="rem-lk-inline-input">'
        + '<input id="remLkNewUrl" placeholder="输入URL…">'
        + '<input id="remLkNewTitle" placeholder="标题" style="width:70px">'
        + '<button class="btn" data-lk-cancel style="font-size:10px;padding:2px 6px;color:var(--faint)">&times;</button>'
        + '</span>';
    }
    el.innerHTML = html;

    // bind pill click → edit
    el.querySelectorAll('.rem-lk-pill').forEach(pill => {
      pill.addEventListener('click', (e) => {
        if (e.target.closest('[data-lk-del]')) return;
        const idx = parseInt(pill.dataset.lkIdx);
        self._editLinkPill(el, idx);
      });
    });
    // bind delete buttons
    el.querySelectorAll('[data-lk-del]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const idx = parseInt(btn.dataset.lkDel);
        self._linkState.links.splice(idx, 1);
        self._renderLinkPills(el);
        self._scheduleAutoSave();
      });
    });
    // cancel new link
    const cancelBtn = el.querySelector('[data-lk-cancel]');
    if (cancelBtn) {
      cancelBtn.addEventListener('click', () => {
        self._linkState.adding = false;
        self._renderLinkPills(el);
      });
    }

    if (this._linkState.adding) {
      setTimeout(() => {
        const inp = el.querySelector('#remLkNewUrl');
        if (inp) {
          inp.focus();
          inp.addEventListener('change', () => self._commitNewLink(el));
          inp.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') self._commitNewLink(el); });
        }
        const titleInp = el.querySelector('#remLkNewTitle');
        if (titleInp) {
          titleInp.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') self._commitNewLink(el); });
        }
      }, 50);
    }
  }

  _editLinkPill(el, idx) {
    const l = this._linkState.links[idx];
    if (!l) return;
    const self = this;
    el.innerHTML = '<span class="rem-lk-inline-input">'
      + '<input id="remLkEditUrl" value="' + REM_escAttr(l.url) + '">'
      + '<input id="remLkEditTitle" value="' + REM_escAttr(l.title || '') + '" placeholder="标题" style="width:70px">'
      + '<button class="btn" data-lk-cancel-edit style="font-size:10px;padding:2px 6px;color:var(--faint)">&times;</button>'
      + '</span>';
    const cancelBtn = el.querySelector('[data-lk-cancel-edit]');
    if (cancelBtn) {
      cancelBtn.addEventListener('click', () => { self._renderLinkPills(el); });
    }
    setTimeout(() => {
      const inp = el.querySelector('#remLkEditUrl');
      if (inp) {
        inp.focus(); inp.select();
        const commit = () => {
          const urlEl = el.querySelector('#remLkEditUrl');
          const titleEl = el.querySelector('#remLkEditTitle');
          const url = (urlEl?.value || '').trim();
          if (!url) { self._renderLinkPills(el); return; }
          self._linkState.links[idx] = { type: REM_detectLinkType(url), url, title: (titleEl?.value || '').trim() };
          self._renderLinkPills(el);
          self._scheduleAutoSave();
        };
        inp.addEventListener('change', commit);
        inp.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') commit(); });
        const titleInp = el.querySelector('#remLkEditTitle');
        if (titleInp) titleInp.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') commit(); });
      }
    }, 50);
  }

  _commitNewLink(el) {
    const urlEl = el.querySelector('#remLkNewUrl');
    const titleEl = el.querySelector('#remLkNewTitle');
    const url = (urlEl?.value || '').trim();
    if (!url) { this._linkState.adding = false; this._renderLinkPills(el); return; }
    this._linkState.links.push({ type: REM_detectLinkType(url), url, title: (titleEl?.value || '').trim() });
    this._linkState.adding = false;
    this._renderLinkPills(el);
    this._scheduleAutoSave();
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // 删除
  // ═══════════════════════════════════════════════════════════════════════════

  async _deleteItem() {
    if (this._editIdx < 0) return;
    const it = this._items[this._editIdx];
    const title = this._getItemTitle(it);
    const id = it[this._entryIssueIdField] || it.id || '';
    if (!confirm(`确认删除 ${id}「${title}」？`)) return;
    try {
      await this._onDelete(it);
      this.close();
    } catch(e) {
      console.error('[RowEditModal._deleteItem]', e);
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 静态工具函数
// ═══════════════════════════════════════════════════════════════════════════

const REM_LINK_ICONS = {
  web: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10"/></svg>`,
  file: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><polyline points="13 2 13 9 20 9"/></svg>`,
  obsidian: `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 22 12 12 22 2 12"/></svg>`,
};

function REM_detectLinkType(url) {
  const u = (url || '').trim().toLowerCase();
  if (u.startsWith('obsidian://')) return 'obsidian';
  if (u.startsWith('file://') || u.match(/^[a-z]:[\\/]/i) || u.startsWith('/')) return 'file';
  return 'web';
}

function REM_esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function REM_escAttr(s) {
  return String(s ?? '').replace(/[&<>\"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

