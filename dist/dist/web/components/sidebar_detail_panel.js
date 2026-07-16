'use strict';
/**
 * sidebar_detail_panel.js — 右侧滑出详情编辑面板（自动保存）
 *
 * 用法：
 *   const rdp = new RowDetailPanel(containerEl, columns, async (fields) => { ... }, context);
 *   rdp.open(row);   // 展开并填充字段
 *   rdp.close();     // 收起
 *   rdp.isOpen       // true / false
 *
 * containerEl 需要有 CSS class="ls-rdp"（或等价的 overflow:hidden + transition 样式）
 */
class RowDetailPanel {
  /**
   * @param {HTMLElement}  containerEl  面板容器（.ls-rdp）
   * @param {Array}        columns      列定义数组（同 GridEditor columns）
   * @param {Function}     onSave       async (fields: {gid, ...}) => void
   * @param {Object}       context      { itemType, currentUserGid, currentUserRole, gridRef, onEntriesSave, listOwnerGid, isCloud }
   */
  constructor(containerEl, columns, onSave, context = {}) {
    this._el          = containerEl;
    this._cols        = columns || [];
    this._onSave      = onSave  || null;
    this._context     = context;
    this._row         = null;
    this._debounce    = null;
    this._pendingFields = {};   // 批量收集待保存字段
    this._saving       = false; // 并发锁
    this._statusTimer = null;

    // ── 导航状态 ────────────────────────────────────────────────────────────
    this._rowList     = [];       // 当前清单的行数组引用
    this._currentGid  = null;     // 当前打开的行 gid
    this._itemType    = context.itemType || '';
    this._listGid     = context.listGid  || null;

    // ── EntryThread ──────────────────────────────────────────────────────────
    this._thread       = null;
    this._entriesTimer = null;
    this._onEntriesSave = context.onEntriesSave || null;
  }

  /** 检查当前用户是否可编辑附件（owner / admin / 同一团队 / 无限制模式）*/
  _canEditAttachments(row) {
    if (!row) return true; // 无行信息时默认允许
    const myGid  = this._context.currentUserGid || '';
    const myRole = this._context.currentUserRole || '';
    // admin 角色始终可编辑
    if (myRole === 'super_admin' || myRole === 'team_admin') return true;
    // 本地模式或未登录时：默认允许（本地模式无强权限隔离）
    if (!myGid || !myRole) return true;
    // 云端行：检查 owner_user_gid（owner 可编辑）
    if (row._source === 'cloud' && row.owner_user_gid) {
      if (row.owner_user_gid === myGid) return true;
      // 团队协作：share_scope 为 team 或 global → 允许同团队编辑
      if (row.share_scope === 'team' || row.share_scope === 'global') return true;
      return false;
    }
    // 本地行：宽松模式，始终允许编辑
    return true;
  }

  // ─── 公开 API ──────────────────────────────────────────────────────────────

  open(row) {
    this._row = row;
    this._currentGid = row?.gid || null;
    this._render();
    this._el.classList.add('open');
    this._updateNavButtons();
  }

  async close() {
    clearTimeout(this._debounce);
    clearTimeout(this._entriesTimer);
    // 关闭前刷新所有待保存字段
    await this._flushSave();
    if (this._saving) {
      // 等待正在进行的保存完成
      await new Promise(r => { this._closeSave = r; });
    }
    this._el.classList.remove('open');
    this._row = null;
    this._thread = null;
  }

  get isOpen() {
    return this._el.classList.contains('open');
  }

  /** 外部用最新数据刷新面板（不关闭）*/
  refresh(row) {
    if (!this.isOpen) return;
    this._row = row;
    this._currentGid = row?.gid || null;
    this._render();
    this._updateNavButtons();
  }

  /** 设置行列表（由 ListShell 在 setRows() 时调用）*/
  setRowList(rows) {
    this._rowList = rows || [];
    if (this.isOpen) this._updateNavButtons();
  }

  /** 设置当前行 gid */
  setCurrentGid(gid) {
    this._currentGid = gid;
    if (this.isOpen) this._updateNavButtons();
  }

  /** 设置清单 gid（用于弹出时传递）*/
  setListGid(gid) {
    this._listGid = gid;
  }

  // ─── 导航 ──────────────────────────────────────────────────────────────────

  _navigate(direction) {
    if (!this._rowList.length) return;
    const idx = this._rowList.findIndex(r => r.gid === this._currentGid);
    if (idx < 0) return;
    const newIdx = idx + direction;
    if (newIdx < 0 || newIdx >= this._rowList.length) return;
    const nextRow = this._rowList[newIdx];
    this.open(nextRow);
    // 通知外部（ListShell）高亮 grid 中对应的行
    if (this._onNavCallback) this._onNavCallback(nextRow);
  }

  _popOut() {
    const rowList = this._rowList || [];
    const idx = rowList.findIndex(r => r.gid === this._currentGid);
    const params = {
      mode: 'row_detail',
      item_type: this._itemType,
      gid: this._currentGid,
      source: this._row?._source || 'local',
      rowList: rowList,
      rowIndex: idx >= 0 ? idx : 0,
      listGid: this._listGid || '',
      title: this._row?.title || this._row?.name || '',
    };
    if (this._onPopoutCallback) {
      this._onPopoutCallback(params);
    }
  }

  _updateNavButtons() {
    const prevBtn = this._el.querySelector('#rdpNavPrev');
    const nextBtn = this._el.querySelector('#rdpNavNext');
    const label   = this._el.querySelector('#rdpNavLabel');
    if (!prevBtn || !nextBtn) return;
    const idx = this._rowList.findIndex(r => r.gid === this._currentGid);
    const total = this._rowList.length;
    if (label) label.textContent = total > 0 ? `${idx + 1}/${total}` : '';
    prevBtn.disabled = idx <= 0;
    nextBtn.disabled = idx >= total - 1 || total === 0;
  }

  // ─── 自动保存 ──────────────────────────────────────────────────────────────

  _showStatus(state) {
    const el = this._el.querySelector('#rdpSaveStatus');
    if (!el) return;
    clearTimeout(this._statusTimer);
    el.className = 'rdp-save-status ' + state;
    el.textContent = state === 'saving' ? '保存中…' : state === 'saved' ? '已保存' : '保存失败';
    if (state === 'saved') {
      this._statusTimer = setTimeout(() => {
        el.textContent = '';
        el.className = 'rdp-save-status';
      }, 1800);
    }
  }

  _scheduleFlush(fields, delayMs = 800) {
    // 批量收集字段
    Object.assign(this._pendingFields, fields);
    clearTimeout(this._debounce);
    this._debounce = setTimeout(() => this._flushSave(), delayMs);
  }

  async _flushSave() {
    const fields = { ...this._pendingFields };
    this._pendingFields = {};
    const hasFields = Object.keys(fields).length > 0;
    if (!hasFields) return;
    if (!this._row?.gid) return;
    if (!this._onSave) { console.warn('[RDP flushSave] _onSave not set, skip save'); return; }

    // 并发锁：如果上次保存还在进行中，只标记脏数据，不启动新保存
    if (this._saving) {
      // 将未保存的字段合并回去，等当前保存完成后再试
      Object.assign(this._pendingFields, fields);
      return;
    }

    this._saving = true;
    this._showStatus('saving');
    try {
      await this._onSave({ gid: this._row.gid, ...fields });
      this._showStatus('saved');
    } catch (e) {
      const msg = e?.message || String(e || '未知错误');
      this._showStatus('error');
      const statusEl = this._el.querySelector('#rdpSaveStatus');
      if (statusEl) {
        statusEl.title = msg;
        statusEl.textContent = '保存失败: ' + (msg.length > 30 ? msg.slice(0, 30) + '…' : msg);
      }
      console.error('[RDP flushSave]', e);
    } finally {
      this._saving = false;
      if (this._closeSave) { this._closeSave(); this._closeSave = null; }
      // 如果在保存期间又产生了新的脏数据，重新调度
      if (Object.keys(this._pendingFields).length > 0) {
        this._debounce = setTimeout(() => this._flushSave(), 400);
      }
    }
  }

  _bindAutoSave(el, col) {
    if (el.type === 'checkbox') {
      el.addEventListener('change', () => this._scheduleFlush({ [col.key]: el.checked }, 0));
    } else if (col.type === 'enum' || col.type === 'date') {
      el.addEventListener('change', () => this._scheduleFlush({ [col.key]: el.value }, 0));
    } else {
      // text / number / textarea：防抖 800ms，批量收集
      el.addEventListener('input', () => {
        this._scheduleFlush({ [col.key]: el.value }, 800);
      });
    }
  }

  // ─── 渲染 ─────────────────────────────────────────────────────────────────

  _render() {
    const row = this._row;
    if (!row) { this._el.innerHTML = ''; this._thread = null; return; }

    const _SKIP = new Set(['_actions', '_isGroupHeader', '_source',
      '_groupKey', '_groupVal', '_groupLabel', '_count']);
    const editableCols = this._cols.filter(c => !_SKIP.has(c.key));

    const idx = this._rowList.findIndex(r => r.gid === this._currentGid);
    const total = this._rowList.length;
    const titleText = row.title || row.name || (row.gid ? '#' + row.gid.slice(-8) : '行详情');

    // ── header（合并 navbar + 标题 + ID + 操作按钮）───────────────────────
    const header = document.createElement('div');
    header.className = 'rdp-header';
    header.innerHTML = `
      <button class="rdp-nav-btn" id="rdpNavPrev" title="上一条" ${idx <= 0 ? 'disabled' : ''}>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <polyline points="18 15 12 9 6 15"/>
        </svg>
      </button>
      <span class="rdp-nav-label" id="rdpNavLabel">${total > 0 ? `${idx + 1}/${total}` : ''}</span>
      <button class="rdp-nav-btn" id="rdpNavNext" title="下一条" ${idx >= total - 1 || total === 0 ? 'disabled' : ''}>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </button>
      <span class="rdp-header-id">#${_escRdp(row.gid ? row.gid.slice(-8) : '?')}</span>
      <span class="rdp-header-sep">|</span>
      <span class="rdp-header-title" title="${_escRdp(titleText)}">${_escRdp(titleText)}</span>
      <span class="rdp-save-status" id="rdpSaveStatus"></span>
      <span class="rdp-hdr-spacer"></span>
      <button class="rdp-nav-btn" id="rdpNewEntry" title="新建沟通条目">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
        </svg>
      </button>
      <button class="rdp-popout-btn" id="rdpPopout" title="弹出为全屏页面">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <polyline points="15 3 21 3 21 9"/>
          <polyline points="9 21 3 21 3 15"/>
          <line x1="21" y1="3" x2="14" y2="10"/>
          <line x1="3" y1="21" x2="10" y2="14"/>
        </svg>
      </button>
      <button class="rdp-close-btn" id="rdpClose" title="关闭">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
      </button>`;

    // ── image preview strip ───────────────────────────────────────────────
    const imgStrip = this._renderImageStrip(row);

    // ── body ──
    const body = document.createElement('div');
    body.className = 'rdp-body';

    // meta 行
    const meta = document.createElement('div');
    meta.className = 'rdp-meta';
    if (row._source) {
      const badge = document.createElement('span');
      badge.className = `rdp-source-badge ${row._source}`;
      badge.textContent = row._source === 'cloud' ? '云端' : '本地';
      meta.appendChild(badge);
    }
    body.appendChild(meta);

    // 字段行
    editableCols.forEach(col => {
      const val = row[col.key];
      const isEditable = col.editable !== false;

      const fieldRow = document.createElement('div');
      fieldRow.className = 'rdp-field-row';

      const labelEl = document.createElement('div');
      labelEl.className = 'rdp-field-label';
      labelEl.textContent = col.label || col.key;
      fieldRow.appendChild(labelEl);

      if (!isEditable) {
        const input = document.createElement('input');
        input.className = 'rdp-field-input';
        input.setAttribute('readonly', '');
        input.value = val != null ? String(val) : '';
        fieldRow.appendChild(input);
      } else if (col.type === 'enum' && col.options?.length) {
        const select = document.createElement('select');
        select.className = 'rdp-field-select';
        select.dataset.key = col.key;
        col.options.forEach(opt => {
          const o = document.createElement('option');
          o.value       = typeof opt === 'object' ? opt.value : String(opt);
          o.textContent = typeof opt === 'object' ? (opt.label || opt.value) : String(opt);
          if (String(val ?? '') === o.value) o.selected = true;
          select.appendChild(o);
        });
        this._bindAutoSave(select, col);
        fieldRow.appendChild(select);
      } else if (col.type === 'date') {
        const input = document.createElement('input');
        input.className = 'rdp-field-input';
        input.type = 'date';
        input.dataset.key = col.key;
        input.value = val ? String(val).slice(0, 10) : '';
        this._bindAutoSave(input, col);
        fieldRow.appendChild(input);
      } else if (col.type === 'boolean') {
        const label = document.createElement('label');
        label.style.cssText = 'display:flex;align-items:center;gap:6px;cursor:pointer;font-size:12px;color:var(--text-normal,#cdd6f4)';
        const input = document.createElement('input');
        input.type = 'checkbox';
        input.dataset.key = col.key;
        input.checked = !!val;
        this._bindAutoSave(input, col);
        label.appendChild(input);
        label.appendChild(document.createTextNode(col.label || col.key));
        fieldRow.appendChild(label);
      } else if (col.type === 'text' && col.multiline) {
        const textarea = document.createElement('textarea');
        textarea.className = 'rdp-field-input rdp-textarea';
        textarea.dataset.key = col.key;
        textarea.value = val != null ? String(val) : '';
        this._bindAutoSave(textarea, col);
        fieldRow.appendChild(textarea);
      } else if (col.type === 'attachments') {
        const attList = (() => {
          if (!val) return [];
          if (Array.isArray(val)) return val;
          try { return JSON.parse(val); } catch (_) { return []; }
        })();
        if (typeof AttachmentsWidget !== 'undefined') {
          const readonly = !this._canEditAttachments(this._row);
          const w = new AttachmentsWidget({
            el:          fieldRow,
            attachments: attList,
            isCloud:     this._row?._source === 'cloud',
            itemType:    this._context.itemType || '',
            itemGid:     this._row?.gid || '',
            readonly,
            onSave:      readonly ? null : (list) => this._scheduleFlush({ [col.key]: JSON.stringify(list) }, 0),
          });
          w.render();
        } else {
          const span = document.createElement('span');
          span.style.cssText = 'font-size:11px;color:var(--text-muted,#a6adc8)';
          span.textContent = attList.length ? `${attList.length} 个附件` : '无附件';
          fieldRow.appendChild(span);
        }
      } else if (col.type === 'feishu_user') {
        const wrap = document.createElement('div');
        wrap.style.cssText = 'display:flex;align-items:center;gap:6px';
        const chip = document.createElement('span');
        chip.style.cssText = 'flex:1;font-size:12px;color:var(--text-normal,#cdd6f4)';
        const openId = row.feishu_assignee_open_id || '';
        const uname  = row.feishu_assignee_name    || '';
        const avatar = row.feishu_assignee_avatar_url || '';
        chip.innerHTML = openId && window.FeishuMentionChip
          ? FeishuMentionChip.renderUser(openId, uname, avatar || null)
          : (uname || '未设置');
        const btn = document.createElement('button');
        btn.className = 'rdp-field-btn';
        btn.textContent = openId ? '更换' : '选择';
        btn.addEventListener('click', () => {
          if (!window.FeishuMentionChip) return;
          FeishuMentionChip.openPicker({
            mode: 'user',
            onSelect: async (result) => {
              const patch = { feishu_assignee_open_id: result.open_id, feishu_assignee_name: result.name, feishu_assignee_avatar_url: result.avatar_url || '' };
              Object.assign(this._row, patch);
              chip.innerHTML = FeishuMentionChip.renderUser(result.open_id, result.name, result.avatar_url || null);
              btn.textContent = '更换';
              this._scheduleFlush(patch, 0);
            },
            onClear: async () => {
              const patch = { feishu_assignee_open_id: null, feishu_assignee_name: null, feishu_assignee_avatar_url: null };
              Object.assign(this._row, patch);
              chip.innerHTML = '未设置'; btn.textContent = '选择';
              this._scheduleFlush(patch, 0);
            },
          });
        });
        wrap.appendChild(chip); wrap.appendChild(btn);
        fieldRow.appendChild(wrap);
      } else if (col.type === 'feishu_group') {
        const wrap = document.createElement('div');
        wrap.style.cssText = 'display:flex;align-items:center;gap:6px';
        const chip = document.createElement('span');
        chip.style.cssText = 'flex:1;font-size:12px;color:var(--text-normal,#cdd6f4)';
        const chatId = row.feishu_group_chat_id || '';
        const gname  = row.feishu_group_name    || '';
        chip.innerHTML = chatId && window.FeishuMentionChip
          ? FeishuMentionChip.renderGroup(chatId, gname)
          : (gname || '未设置');
        const btn = document.createElement('button');
        btn.className = 'rdp-field-btn';
        btn.textContent = chatId ? '更换' : '选择';
        btn.addEventListener('click', () => {
          if (!window.FeishuMentionChip) return;
          FeishuMentionChip.openPicker({
            mode: 'group',
            onSelect: async (result) => {
              const patch = { feishu_group_chat_id: result.chat_id, feishu_group_name: result.name };
              Object.assign(this._row, patch);
              chip.innerHTML = FeishuMentionChip.renderGroup(result.chat_id, result.name);
              btn.textContent = '更换';
              this._scheduleFlush(patch, 0);
            },
            onClear: async () => {
              const patch = { feishu_group_chat_id: null, feishu_group_name: null };
              Object.assign(this._row, patch);
              chip.innerHTML = '未设置'; btn.textContent = '选择';
              this._scheduleFlush(patch, 0);
            },
          });
        });
        wrap.appendChild(chip); wrap.appendChild(btn);
        fieldRow.appendChild(wrap);
      } else {
        const input = document.createElement('input');
        input.className = 'rdp-field-input';
        input.type = col.type === 'number' ? 'number' : 'text';
        input.dataset.key = col.key;
        input.value = val != null ? String(val) : '';
        this._bindAutoSave(input, col);
        fieldRow.appendChild(input);
      }
    });

    // ── EntryThread 挂载点 ────────────────────────────────────────────────
    const etWrap = document.createElement('div');
    etWrap.className = 'rdp-entries-wrap';
    etWrap.innerHTML = `
      <div class="et-section">
        <div class="et-section-hdr"><span class="et-section-title">具体详情</span><span class="et-section-count" id="etDetailCount"></span></div>
        <div class="et-section-body" id="etDetailEntries"></div>
      </div>
      <div class="et-section">
        <div class="et-section-hdr"><span class="et-section-title">沟通历史</span><span class="et-section-count" id="etHistoryCount"></span></div>
        <div class="et-section-body" id="etHistoryEntries"></div>
      </div>
      <div class="et-section" id="rdpChangeLogSection" style="display:none">
        <div class="et-section-hdr">
          <span class="et-section-title">变更历史</span>
          <span class="et-section-count" id="rdpChangeLogCount"></span>
        </div>
        <div class="et-section-body" id="rdpChangeLogList" style="font-size:12px;color:var(--text-muted)">加载中…</div>
      </div>`;
    body.appendChild(etWrap);

    // ── assemble ─────────────────────────────────────────────────────────
    this._el.innerHTML = '';
    this._el.appendChild(header);
    if (imgStrip) this._el.appendChild(imgStrip);
    this._el.appendChild(body);

    // 事件绑定
    this._el.querySelector('#rdpClose')?.addEventListener('click', () => this.close());
    this._el.querySelector('#rdpNavPrev')?.addEventListener('click', () => this._navigate(-1));
    this._el.querySelector('#rdpNavNext')?.addEventListener('click', () => this._navigate(1));
    this._el.querySelector('#rdpPopout')?.addEventListener('click', () => this._popOut());
    this._el.querySelector('#rdpNewEntry')?.addEventListener('click', () => this._addNewEntry());

    // 初始化 EntryThread（延迟确保 DOM 就绪）
    setTimeout(() => this._initEntries(row), 0);

    // 变更历史（飞书/云端行）
    const clSection = this._el.querySelector('#rdpChangeLogSection');
    if (clSection) {
      const isCloud = row._source === 'cloud' || (window._authMode === 'feishu');
      const itemGid = row.gid || row.cloud_gid || '';
      if (isCloud && itemGid && this._itemType) {
        clSection.style.display = '';
        this._loadChangeLogs(itemGid);
      } else {
        clSection.style.display = 'none';
      }
    }
  }

  // ─── Image Strip ────────────────────────────────────────────────────────────

  _renderImageStrip(row) {
    const attList = this._parseAttachments(row.attachments);
    const images = attList.filter(a => {
      const name = (a.name || a.filename || '').toLowerCase();
      const type = (a.type || a.mime_type || '');
      return /\.(png|jpg|jpeg|gif|webp|svg|bmp)$/i.test(name) || type.startsWith('image/');
    });
    if (!images.length) return null;

    const strip = document.createElement('div');
    strip.className = 'rdp-img-strip';
    images.forEach(img => {
      const src = img.url || img.path || '';
      const name = img.name || img.filename || 'image';
      const thumb = document.createElement('div');
      thumb.className = 'rdp-img-thumb';
      thumb.title = name;
      thumb.innerHTML = src
        ? `<img src="${_escRdp(src)}" alt="${_escRdp(name)}" loading="lazy" onerror="this.parentElement.remove()">`
        : `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>`;
      thumb.addEventListener('click', () => {
        if (src && window.electronAPI?.shellOpenExternal) {
          // Electron: open file
          window.electronAPI.openPath ? window.electronAPI.openPath(src) : window.open(src, '_blank');
        } else {
          window.open(src, '_blank');
        }
      });
      strip.appendChild(thumb);
    });
    return strip;
  }

  _parseAttachments(val) {
    if (!val) return [];
    if (Array.isArray(val)) return val;
    try { return JSON.parse(val); } catch (_) { return []; }
  }

  // ─── EntryThread ────────────────────────────────────────────────────────────

  _initEntries(row) {
    const mountEl = this._el.querySelector('.rdp-entries-wrap');
    if (!mountEl) { console.warn('[RowDetailPanel] mountEl not found'); return; }
    if (!mountEl.id) mountEl.id = 'rdpEntriesMount';

    let entries = row.entries;
    if (!Array.isArray(entries) || !entries.length) {
      // 从旧字段迁移作为临时数据（DB 加载完成后会替换）
      if (typeof EntryThread !== 'undefined' && EntryThread.migrate) {
        entries = EntryThread.migrate(row);
      }
      // 始终尝试从 DB 懒加载（DB 是权威数据源）
      this._loadEntriesAsync(row, mountEl);
      // 如果迁移也没产出条目，给空数组
      if (!entries.length) entries = [];
    }

    const isCloud = row._source === 'cloud';
    const ownerGid = row.owner_user_gid || row.owner_gid || '';

    // 每次 _render() 都会重建 DOM，旧 thread 的 mountEl 已失效，必须重建
    this._thread = null;
    this._thread = new EntryThread({
      mountEl,
      mode: 'human',
      entries,
      currentUserGid: this._context.currentUserGid || '',
      currentUserName: this._context.currentUserName || '',
      userRole: this._context.currentUserRole || '',
      listOwnerGid: ownerGid,
      isCloud,
      onChange: (ents) => { this._onEntriesChange(row, ents); },
      onSave: () => {},
      onStatusMsg: () => {},
    });
    this._thread._bindGlobal(mountEl.id);
    // 构造函数不渲染，setEntries 才渲染（即使 entries 为空也要渲染结构）
    this._thread.setEntries(entries);
  }

  async _loadEntriesAsync(row, mountEl) {
    const itemType = this._context.itemType || '';
    const gid = row.gid;
    if (!itemType || !gid) { console.warn('[RowDetailPanel._loadEntriesAsync] missing itemType or gid'); return; }
    try {
      let result;
      const cf = window.top?._cloudFetch || window.parent?._cloudFetch || window._cloudFetch;
      if (cf) {
        const resp = await cf(`/api/item-entries/${itemType}/${gid}`);
        result = resp?.entries || [];
      }
      // 防竞争：如果已切换到其他行，丢弃过期结果
      if (this._currentGid !== gid) { return; }
      if (Array.isArray(result) && result.length) {
        row.entries = result;
        if (this._thread) {
          this._thread.setEntries(result);
        }
      }
    } catch (e) {
      console.warn('[RowDetailPanel._loadEntriesAsync] failed:', e.message || e);
    }
  }

  _onEntriesChange(row, entries) {
    // 写到行对象上
    row.entries = entries;
    // 延迟自动保存
    clearTimeout(this._entriesTimer);
    this._entriesTimer = setTimeout(() => {
      if (this._onEntriesSave) {
        this._onEntriesSave(row.gid, entries);
      }
    }, 800);
  }

  _addNewEntry() {
    // 在详情区创建新条目
    if (this._thread) {
      this._thread._addEntry('detail', null);
    }
  }

  _loadChangeLogs(itemGid) {
    const listEl  = this._el.querySelector('#rdpChangeLogList');
    const countEl = this._el.querySelector('#rdpChangeLogCount');
    if (!listEl) return;
    listEl.textContent = '加载中…';
    const cf = window._cloudFetch || window.parent?._cloudFetch || window.top?._cloudFetch;
    if (!cf) { listEl.textContent = '（无云端连接）'; return; }
    cf(`/api/change-logs?item_type=${encodeURIComponent(this._itemType)}&item_gid=${encodeURIComponent(itemGid)}&limit=50`)
      .then(rows => {
        if (!Array.isArray(rows) || rows.length === 0) {
          listEl.innerHTML = '<div style="padding:6px 0">暂无变更记录</div>';
          if (countEl) countEl.textContent = '';
          return;
        }
        if (countEl) countEl.textContent = ` (${rows.length})`;
        const FIELD_LABELS = {
          title: '标题', status: '状态', priority: '优先级', description: '描述',
          due_date: '截止', plan_start: '计划开始', plan_end: '计划结束',
          actual_start: '实际开始', actual_end: '实际完成', severity: '严重程度',
          assignee_team_gid: '负责人', list_gid: '所在清单',
        };
        listEl.innerHTML = rows.map(r => {
          const label = FIELD_LABELS[r.field_name] || r.field_name;
          const oldV = r.old_value != null ? r.old_value : '—';
          const newV = r.new_value != null ? r.new_value : '—';
          const dt = r.changed_at ? new Date(r.changed_at).toLocaleString('zh-CN', { hour12: false }) : '';
          return `<div style="display:grid;grid-template-columns:100px 60px 1fr;gap:4px;padding:3px 0;border-bottom:1px solid var(--border-light,#e0e0e0);font-size:11px">
            <span style="color:var(--text-muted)">${dt}</span>
            <span style="color:var(--accent,#5b9bd5)">${label}</span>
            <span><del style="color:var(--text-muted)">${oldV}</del> → ${newV}</span>
          </div>`;
        }).join('');
      })
      .catch(() => { listEl.textContent = '加载失败'; });
  }
}

function _escRdp(s) {
  return String(s ?? '').replace(/[&<>"']/g, c =>
    ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c]));
}

