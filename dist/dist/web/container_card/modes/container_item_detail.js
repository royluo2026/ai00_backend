'use strict';
/**
 * container_item_detail.js — 容器卡片模式：清单条目详情（可编辑）
 *
 * ContainerMode 协议：
 *   renderInCard(containerEl, params, ctx)  → cleanup()
 *   renderFullPage(containerEl, urlParams)
 *
 * params / urlParams:
 *   item_type  : 'task' | 'issue' | 'knowledge' | 'rule'
 *   gid        : 条目 GID
 *   source     : 'cloud' | 'local'
 *   rowList    : 完整行数组（全屏导航用）
 *   rowIndex   : 当前行在 rowList 中的索引
 */
window.ContainerModes = window.ContainerModes || {};

window.ContainerModes['row_detail'] = (() => {

  // ── 字段配置 ──────────────────────────────────────────────────────────────

  const TASK_FIELDS = [
    { key: 'title',        label: '标题',    ctrl: 'input',    type: 'text'   },
    { key: 'status',       label: '状态',    ctrl: 'select',   opts: ['pending','in_progress','blocked','completed','cancelled'], labels: ['待处理','进行中','阻塞','已完成','已取消'] },
    { key: 'priority',     label: '优先级',  ctrl: 'select',   opts: ['high','normal','low'], labels: ['高','中','低'] },
    { key: 'due_date',     label: '截止日期',ctrl: 'input',    type: 'date'   },
    { key: 'plan_start',   label: '计划开始',ctrl: 'input',    type: 'date'   },
    { key: 'plan_end',     label: '计划结束',ctrl: 'input',    type: 'date'   },
    { key: 'actual_start', label: '实际开始',ctrl: 'input',    type: 'date'   },
    { key: 'actual_end',   label: '实际结束',ctrl: 'input',    type: 'date'   },
    { key: 'description',  label: '描述',    ctrl: 'textarea'                 },
    { key: 'created_at',   label: '创建时间',ctrl: 'readonly'                 },
    { key: 'updated_at',   label: '更新时间',ctrl: 'readonly'                 },
    { key: 'attachments',  label: '附件',    ctrl: 'attach'                   },
  ];

  const ISSUE_FIELDS = [
    { key: 'title',        label: '标题',    ctrl: 'input',    type: 'text'   },
    { key: 'status',       label: '状态',    ctrl: 'select',   opts: ['open','in_progress','resolved','closed'], labels: ['开放','处理中','已解决','已关闭'] },
    { key: 'severity',     label: '严重程度',ctrl: 'select',   opts: ['critical','major','minor','trivial'], labels: ['严重','重要','一般','轻微'] },
    { key: 'due_date',     label: '截止日期',ctrl: 'input',    type: 'date'   },
    { key: 'description',  label: '描述',    ctrl: 'textarea'                 },
    { key: 'created_at',   label: '创建时间',ctrl: 'readonly'                 },
    { key: 'updated_at',   label: '更新时间',ctrl: 'readonly'                 },
    { key: 'attachments',  label: '附件',    ctrl: 'attach'                   },
  ];

  const KNOWLEDGE_FIELDS = [
    { key: 'title',   label: '标题',  ctrl: 'input',    type: 'text' },
    { key: 'content', label: '内容',  ctrl: 'textarea'               },
    { key: 'tags',    label: '标签',  ctrl: 'input',    type: 'text' },
    { key: 'status',  label: '状态',  ctrl: 'select',   opts: ['draft','published'], labels: ['草稿','已发布'] },
    { key: 'created_at', label: '创建时间', ctrl: 'readonly' },
  ];

  const RULE_FIELDS = [
    { key: 'code',      label: '规则编号', ctrl: 'input',  type: 'text' },
    { key: 'name',      label: '规则名称', ctrl: 'input',  type: 'text' },
    { key: 'rule_type', label: '规则类型', ctrl: 'input',  type: 'text' },
    { key: 'status',    label: '状态',     ctrl: 'select', opts: ['active','inactive'], labels: ['激活','停用'] },
    { key: 'created_at', label: '创建时间', ctrl: 'readonly' },
  ];

  function _getFields(itemType) {
    return { task: TASK_FIELDS, issue: ISSUE_FIELDS, knowledge: KNOWLEDGE_FIELDS, rule: RULE_FIELDS }[itemType] || TASK_FIELDS;
  }

  // ── 云端请求（直接 fetch，避免跨 realm 函数引用问题）───────────────
  //    与 ListShell.cf 降级路径一致：优先用 window.top._cloudFetch 函数引用，
  //    若不可用则直接 fetch（从 electronAPI 获取 backendUrl + token）

  function _getCF() {
    return window.top?._cloudFetch || window.parent?._cloudFetch || window._cloudFetch || null;
  }

  async function _cf(path, opts = {}) {
    // 优先用主窗口的 _cloudFetch 函数（与 ListShell._cf 完全一致）
    const cf = _getCF();
    if (cf) return cf(path, opts);

    // 降级：直接使用 electronAPI 构建 fetch
    const eAPI = window.top?.electronAPI || window.parent?.electronAPI || window.electronAPI;
    if (!eAPI) throw new Error('electronAPI 不可用');
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

  async function _load(itemType, gid, source) {
    const res = await _cf(`/api/${itemType}s/${gid}`);
    return res?.data || res || null;
  }

  // ── 数据保存 ─────────────────────────────────────────────────────────────

  // ── entries 持久化（调用 item_entries API，非 task/issue 字段）───

  async function _loadPopoutEntries(itemType, gid, source) {
    const resp = await _cf(`/api/item-entries/${itemType}/${gid}`);
    return resp?.entries || [];
  }

  async function _savePopoutEntries(itemType, gid, source, entries) {
    await _cf(`/api/item-entries/${itemType}/${gid}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ entries }),
    });
  }

  async function _save(itemType, gid, source, changes) {
    await _cf(`/api/${itemType}s/${gid}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(changes),
    });
  }

  // ── 新建条目 ─────────────────────────────────────────────────────────────

  async function _createItem(itemType, fields, source, listGid) {
    const body = { title: fields.title, list_gid: listGid || null };
    if (itemType === 'task') {
      body.priority = fields.priority || 'normal';
      body.status = 'pending';
    } else if (itemType === 'issue') {
      body.severity = fields.severity || 'minor';
      body.status = 'open';
    }
    body.description = fields.description || '';
    const res = await _cf(`/api/${itemType}s`, { method: 'POST', body: JSON.stringify(body) });
    return res?.data || res || null;
  }

  // ── 全屏导航状态 ─────────────────────────────────────────────────────────

  let _fullRowList    = [];
  let _fullRowIndex   = -1;
  let _fullGid        = null;
  let _fullItemType   = '';
  let _fullSource     = 'local';
  let _fullListGid    = '';
  let _fullScrollEl   = null;   // 滚动区域引用（导航后滚动到顶部）
  let _fullFormEl     = null;   // 表单容器引用
  let _fullDebounce   = null;   // 自动保存防抖
  let _fullStatusTimer = null;  // 保存状态自动清除
  let _fullThread     = null;   // EntryThread 实例
  let _fullEntriesTimer = null; // entries 自动保存防抖
  let _fullData        = null;  // 当前完整数据（含 entries）

  // ── 渲染表单 ─────────────────────────────────────────────────────────────

  function _buildForm(containerEl, data, fields, isCard) {
    const wrap = document.createElement('div');
    wrap.style.cssText = 'display:flex;flex-direction:column;height:100%;overflow:hidden;';

    const scrollArea = document.createElement('div');
    scrollArea.style.cssText = 'flex:1;overflow-y:auto;padding:12px 16px;';

    fields.forEach(f => {
      const val = data[f.key];
      if (val === undefined && f.ctrl !== 'input' && f.ctrl !== 'textarea' && f.ctrl !== 'select') return;

      const row = document.createElement('div');
      row.className = 'cc-field-row';
      row.style.cssText = 'display:grid;grid-template-columns:100px 1fr;gap:8px;align-items:start;margin-bottom:8px;';

      const label = document.createElement('div');
      label.className = 'cc-field-label';
      label.textContent = f.label;
      label.style.cssText = 'font-size:12px;font-weight:500;color:var(--cc-muted,#6e6e6e);text-align:right;padding-top:6px;';

      let ctrl;

      if (f.ctrl === 'readonly') {
        ctrl = document.createElement('div');
        ctrl.className = 'cc-field-readonly';
        ctrl.textContent = val ? String(val).slice(0, 100) : '—';
        ctrl.style.cssText = 'font-size:13px;color:var(--cc-text,#2e2e2e);padding:5px 0;';
        ctrl.dataset.rdKey = f.key;

      } else if (f.ctrl === 'attach') {
        ctrl = document.createElement('div');
        ctrl.className = 'cc-attach-list';
        ctrl.style.cssText = 'display:flex;flex-wrap:wrap;gap:6px;padding:4px 0;';
        if (Array.isArray(val) && val.length) {
          val.forEach(a => {
            const chip = document.createElement('span');
            chip.style.cssText = 'display:inline-flex;align-items:center;gap:4px;padding:3px 8px;background:var(--cc-bg2,#f7f6f3);border:1px solid var(--cc-border,#dcdcdc);border-radius:4px;font-size:11px;color:var(--cc-text,#2e2e2e);cursor:pointer;';
            chip.textContent = a.name || a.url || '附件';
            chip.title = a.url || '';
            chip.addEventListener('click', () => {
              const url = a.url || '';
              if (a.type === 'file' || a.link_type === 'md') {
                (window.parent?.electronAPI || window.electronAPI)?.openPath?.(url);
              } else {
                (window.parent?.electronAPI || window.electronAPI)?.openExternal?.(url)
                  || window.open(url, '_blank');
              }
            });
            ctrl.appendChild(chip);
          });
        } else {
          ctrl.innerHTML = '<span style="font-size:12px;color:var(--cc-muted,#6e6e6e)">暂无附件</span>';
        }

      } else if (f.ctrl === 'select') {
        ctrl = document.createElement('select');
        ctrl.className = 'cc-field-select';
        ctrl.style.cssText = 'padding:5px 8px;background:var(--cc-bg2,#f7f6f3);border:1px solid var(--cc-border,#dcdcdc);border-radius:6px;color:var(--cc-text,#2e2e2e);font-size:13px;outline:none;';
        ctrl.dataset.key = f.key;
        f.opts.forEach((o, i) => {
          const opt = document.createElement('option');
          opt.value = o;
          opt.textContent = (f.labels || [])[i] || o;
          if (val === o) opt.selected = true;
          ctrl.appendChild(opt);
        });

      } else if (f.ctrl === 'textarea') {
        ctrl = document.createElement('textarea');
        ctrl.className = 'cc-field-input';
        ctrl.rows = isCard ? 2 : 4;
        ctrl.value = val != null ? String(val) : '';
        ctrl.style.cssText = 'padding:5px 8px;background:var(--cc-bg2,#f7f6f3);border:1px solid var(--cc-border,#dcdcdc);border-radius:6px;color:var(--cc-text,#2e2e2e);font-size:13px;outline:none;resize:vertical;font-family:inherit;width:100%;';
        ctrl.dataset.key = f.key;

      } else {
        ctrl = document.createElement('input');
        ctrl.type = f.type || 'text';
        ctrl.className = 'cc-field-input';
        ctrl.value = val != null ? String(val) : '';
        ctrl.style.cssText = 'padding:5px 8px;background:var(--cc-bg2,#f7f6f3);border:1px solid var(--cc-border,#dcdcdc);border-radius:6px;color:var(--cc-text,#2e2e2e);font-size:13px;outline:none;width:100%;';
        ctrl.dataset.key = f.key;
      }

      row.appendChild(label);
      row.appendChild(ctrl);
      scrollArea.appendChild(row);
    });

    wrap.appendChild(scrollArea);
    containerEl.innerHTML = '';
    containerEl.appendChild(wrap);
    return wrap;
  }

  function _collectChanges(formEl, fields) {
    const changes = {};
    fields.forEach(f => {
      if (f.ctrl === 'readonly' || f.ctrl === 'attach') return;
      const ctrl = formEl.querySelector(`[data-key="${f.key}"]`);
      if (!ctrl) return;
      changes[f.key] = ctrl.tagName === 'SELECT' ? ctrl.value : ctrl.value;
    });
    return changes;
  }

  // ── 附件解析 ─────────────────────────────────────────────────────────────

  function _parseAttachments(row) {
    const val = row?.attachments;
    if (!val) return [];
    if (Array.isArray(val)) return val;
    try { return JSON.parse(val); } catch (_) { return []; }
  }

  // ── renderInCard ─────────────────────────────────────────────────────────

  function renderInCard(containerEl, params, ctx) {
    const { item_type = 'task', gid, source = 'local' } = params || {};

    if (!gid) {
      containerEl.innerHTML = '<div style="padding:12px;font-size:12px;color:var(--cc-muted,#6e6e6e)">未指定条目</div>';
      return () => {};
    }

    containerEl.innerHTML = '<div style="padding:12px;font-size:12px;color:var(--cc-muted,#6e6e6e)">加载中…</div>';

    let destroyed = false;
    const fields = _getFields(item_type);
    // 卡片模式只显示前几个重要字段
    const cardFields = fields.slice(0, 5);

    _load(item_type, gid, source).then(data => {
      if (destroyed) return;
      if (!data) {
        containerEl.innerHTML = '<div style="padding:12px;font-size:12px;color:var(--cc-muted)">未找到条目</div>';
        return;
      }

      const wrap = _buildForm(containerEl, data, cardFields, true);
      const scrollArea = wrap.querySelector('div');

      // 保存按钮
      const saveBar = document.createElement('div');
      saveBar.style.cssText = 'display:flex;align-items:center;justify-content:flex-end;gap:8px;padding:6px 16px;border-top:1px solid var(--cc-border,#dcdcdc);';

      const saveBtn = document.createElement('button');
      saveBtn.textContent = '保存';
      saveBtn.style.cssText = 'padding:4px 12px;border-radius:4px;border:none;background:var(--cc-accent,#7b61ff);color:#fff;font-size:12px;cursor:pointer;';
      saveBtn.addEventListener('click', async () => {
        saveBtn.disabled = true; saveBtn.textContent = '保存中…';
        try {
          const changes = _collectChanges(scrollArea, cardFields);
          await _save(item_type, gid, source, changes);
          saveBtn.textContent = '已保存';
          setTimeout(() => { if (!destroyed) { saveBtn.textContent = '保存'; saveBtn.disabled = false; } }, 1500);
        } catch (e) {
          saveBtn.textContent = '失败';
          setTimeout(() => { if (!destroyed) { saveBtn.textContent = '保存'; saveBtn.disabled = false; } }, 2000);
        }
      });
      saveBar.appendChild(saveBtn);
      wrap.appendChild(saveBar);

      // 展开按钮
      const expandBtn = document.createElement('button');
      expandBtn.className = 'cc-expand-btn';
      expandBtn.style.cssText = 'width:100%;padding:6px;text-align:center;font-size:11px;color:var(--cc-accent,#7b61ff);background:none;border:none;border-top:1px solid var(--cc-border,#dcdcdc);cursor:pointer;';
      expandBtn.textContent = '展开全部字段 →';
      expandBtn.addEventListener('click', () => {
        const parent = window.parent;
        if (parent?.TabManager) {
          parent.TabManager.open('container_card', {
            mode: 'row_detail',
            item_type,
            gid,
            source,
            title: data.title || '条目详情',
          });
        }
      });
      wrap.appendChild(expandBtn);

    }).catch(e => {
      if (!destroyed) {
        containerEl.innerHTML = `<div style="padding:12px;font-size:12px;color:var(--cc-muted)">加载失败: ${String(e)}</div>`;
      }
    });

    return () => { destroyed = true; };
  }

  // ── renderFullPage ───────────────────────────────────────────────────────

  function renderFullPage(containerEl, urlParams) {
    // 优先读 window.parent 上的临时全局变量（popout modal 场景），降级到 _ccParams
    const stored = window._ccParams || {};
    const fromParent = (() => {
      try { return window.parent?.__popoutRowList; } catch (_) { return null; }
    })();

    const item_type = stored.item_type || urlParams.get('item_type') || 'task';
    const gid       = stored.gid       || urlParams.get('gid');
    const source    = stored.source    || urlParams.get('source') || 'local';
    const listGid   = stored.listGid   || urlParams.get('listGid') || '';

    // 行列表（全屏导航用）— 优先从 parent 读取
    let rowList = fromParent || stored.rowList || [];
    if (!Array.isArray(rowList)) {
      try { rowList = JSON.parse(rowList); } catch (_) { rowList = []; }
    }
    const rowIndex = parseInt(stored.rowIndex ?? urlParams.get('rowIndex'), 10) || 0;

    // 更新全局状态
    _fullRowList  = rowList;
    _fullItemType = item_type;
    _fullSource   = source;
    _fullListGid  = listGid;

    if (!gid && !rowList.length) {
      containerEl.innerHTML = '<div class="cc-empty">未指定条目 GID</div>';
      return;
    }

    // 确定当前 gid 和索引
    const initialGid = gid || (rowList[rowIndex]?.gid);
    _fullGid = initialGid;
    _fullRowIndex = rowList.findIndex(r => r.gid === initialGid);
    if (_fullRowIndex < 0) _fullRowIndex = rowIndex;

    if (!_fullGid) {
      containerEl.innerHTML = '<div class="cc-empty">未指定条目 GID</div>';
      return;
    }

    containerEl.innerHTML = '<div class="cc-loading">加载中…</div>';
    const fields = _getFields(item_type);

    // 获取当前行数据（优先从 rowList 取，否则从 API 加载）
    const loadRow = () => {
      const localRow = _fullRowList[_fullRowIndex];
      if (localRow && localRow.gid === _fullGid) {
        return Promise.resolve(localRow);
      }
      return _load(item_type, _fullGid, source);
    };

    loadRow().then(data => {
      if (!data) { containerEl.innerHTML = '<div class="cc-empty">未找到条目</div>'; return; }
      _renderFullPage(containerEl, data, fields);
    }).catch(e => {
      containerEl.innerHTML = `<div class="cc-empty">加载失败: ${String(e)}</div>`;
    });
  }

  function _renderFullPage(containerEl, data, fields) {
    containerEl.innerHTML = '';
    containerEl.style.cssText = 'display:flex;flex-direction:column;height:100%;overflow:hidden;';

    // ── 顶部导航栏 ────────────────────────────────────────────────────────
    const nav = document.createElement('div');
    nav.className = 'cc-popout-nav';
    const total = _fullRowList.length;
    const idxLabel = total > 0 ? `第 ${_fullRowIndex + 1} / ${total} 条` : '';
    nav.innerHTML = `
      <button class="cc-nav-btn" id="ccNavPrev" title="上一条" ${_fullRowIndex <= 0 ? 'disabled' : ''}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <polyline points="15 18 9 12 15 6"/>
        </svg>
        上一条
      </button>
      <span class="cc-nav-info">${idxLabel}</span>
      <span class="cc-save-status" id="ccSaveStatus"></span>
      <button class="cc-nav-btn" id="ccNavNext" title="下一条" ${_fullRowIndex >= total - 1 || total === 0 ? 'disabled' : ''}>
        下一条
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <polyline points="9 18 15 12 9 6"/>
        </svg>
      </button>
      <button class="cc-nav-btn" id="ccNavNew" title="新建条目">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
        </svg>
        新建
      </button>`;
    containerEl.appendChild(nav);

    // ── 图片 strip（附件中的图片预览）────────────────────────────────────
    const atts = _parseAttachments(data);
    const imgAtts = atts.filter(a => a.type?.startsWith('image/') || a.name?.match(/\.(png|jpg|jpeg|gif|webp|svg|bmp)$/i));
    if (imgAtts.length) {
      const imgStrip = document.createElement('div');
      imgStrip.className = 'cc-img-strip';

      // 图片预览 overlay（单例，在 containerEl 作用域内）
      let _previewOverlay = null;
      const _closePreview = () => {
        if (_previewOverlay) { _previewOverlay.remove(); _previewOverlay = null; }
      };
      const _openImagePreview = (images, startIdx) => {
        _closePreview();
        let curIdx = startIdx;

        const overlay = document.createElement('div');
        overlay.className = 'cc-img-preview-overlay';

        // 关闭按钮
        const closeBtn = document.createElement('button');
        closeBtn.className = 'cc-img-preview-close';
        closeBtn.innerHTML = '&#10005;';
        closeBtn.addEventListener('click', _closePreview);
        overlay.appendChild(closeBtn);

        // 图片
        const img = document.createElement('img');
        img.className = 'cc-img-preview-img';
        const updateImg = () => {
          const src = images[curIdx]?.url || images[curIdx]?.data || '';
          img.src = src || '';
          counterEl.textContent = `${curIdx + 1} / ${images.length}`;
          prevArrow.disabled = curIdx <= 0;
          nextArrow.disabled = curIdx >= images.length - 1;
        };
        overlay.appendChild(img);

        // 左箭头
        const prevArrow = document.createElement('button');
        prevArrow.className = 'cc-img-preview-arrow left';
        prevArrow.innerHTML = '&#10094;';
        prevArrow.addEventListener('click', e => {
          e.stopPropagation();
          if (curIdx > 0) { curIdx--; updateImg(); }
        });
        overlay.appendChild(prevArrow);

        // 右箭头
        const nextArrow = document.createElement('button');
        nextArrow.className = 'cc-img-preview-arrow right';
        nextArrow.innerHTML = '&#10095;';
        nextArrow.addEventListener('click', e => {
          e.stopPropagation();
          if (curIdx < images.length - 1) { curIdx++; updateImg(); }
        });
        overlay.appendChild(nextArrow);

        // 计数器
        const counterEl = document.createElement('span');
        counterEl.className = 'cc-img-preview-counter';
        overlay.appendChild(counterEl);

        // 点击背景关闭
        overlay.addEventListener('click', e => {
          if (e.target === overlay) _closePreview();
        });

        // Escape 关闭
        const onKey = e => { if (e.key === 'Escape') { _closePreview(); document.removeEventListener('keydown', onKey); } };
        document.addEventListener('keydown', onKey);

        containerEl.appendChild(overlay);
        _previewOverlay = overlay;
        updateImg();
      };

      imgAtts.forEach((att, i) => {
        const src = att.url || att.data || '';
        if (!src) return;
        const img = document.createElement('img');
        img.className = 'cc-img-thumb';
        img.src = src;
        img.title = att.name || `图片 ${i + 1}`;
        img.addEventListener('click', () => _openImagePreview(imgAtts, i));
        img.addEventListener('error', () => {
          img.style.display = 'none';
        });
        imgStrip.appendChild(img);
      });
      containerEl.appendChild(imgStrip);
    }

    // ── 新建条目表单（默认隐藏）──────────────────────────────────────────
    const newForm = document.createElement('div');
    newForm.className = 'cc-new-form';
    newForm.style.display = 'none';
    const isTask = _fullItemType === 'task';
    const isIssue = _fullItemType === 'issue';
    newForm.innerHTML = `
      <input class="cc-new-title" placeholder="标题..." style="flex:1;min-width:120px;padding:5px 8px;background:var(--cc-bg2,#f7f6f3);border:1px solid var(--cc-border,#dcdcdc);border-radius:6px;color:var(--cc-text,#2e2e2e);font-size:13px;outline:none;" />
      ${isTask ? '<select class="cc-new-prio" style="padding:5px 8px;background:var(--cc-bg2,#f7f6f3);border:1px solid var(--cc-border,#dcdcdc);border-radius:6px;color:var(--cc-text,#2e2e2e);font-size:13px;outline:none;"><option value="normal">中</option><option value="high">高</option><option value="low">低</option></select>' : ''}
      ${isIssue ? '<select class="cc-new-severity" style="padding:5px 8px;background:var(--cc-bg2,#f7f6f3);border:1px solid var(--cc-border,#dcdcdc);border-radius:6px;color:var(--cc-text,#2e2e2e);font-size:13px;outline:none;"><option value="minor">轻微</option><option value="major">重要</option><option value="critical">严重</option><option value="trivial">一般</option></select>' : ''}
      <button class="cc-new-submit" style="padding:5px 12px;background:var(--cc-accent,#7b61ff);border:none;border-radius:6px;color:#fff;font-size:12px;cursor:pointer;">创建</button>
      <button class="cc-new-cancel" style="padding:5px 12px;background:transparent;border:1px solid var(--cc-border,#dcdcdc);border-radius:6px;color:var(--cc-muted,#6e6e6e);font-size:12px;cursor:pointer;">取消</button>`;
    containerEl.appendChild(newForm);

    // ── 滚动区域（字段表单）─────────────────────────────────────────────
    const scrollArea = document.createElement('div');
    scrollArea.style.cssText = 'flex:1;overflow-y:auto;padding:16px;';
    _fullScrollEl = scrollArea;

    fields.forEach(f => {
      const val = data[f.key];

      const row = document.createElement('div');
      row.style.cssText = 'display:grid;grid-template-columns:110px 1fr;gap:10px;align-items:start;margin-bottom:10px;';

      const label = document.createElement('div');
      label.className = 'cc-field-label';
      label.textContent = f.label;
      label.style.cssText = 'font-size:12px;font-weight:500;color:var(--cc-muted,#6e6e6e);text-align:right;padding-top:6px;';

      let ctrl;

      if (f.ctrl === 'readonly') {
        ctrl = document.createElement('div');
        ctrl.textContent = val ? String(val) : '—';
        ctrl.style.cssText = 'font-size:13px;color:var(--cc-text,#2e2e2e);padding:5px 0;';

      } else if (f.ctrl === 'attach') {
        ctrl = document.createElement('div');
        ctrl.style.cssText = 'display:flex;flex-wrap:wrap;gap:6px;padding:4px 0;';
        if (Array.isArray(val) && val.length) {
          val.forEach(a => {
            const chip = document.createElement('span');
            chip.className = 'cc-attach-chip';
            chip.textContent = a.name || a.url || '附件';
            chip.title = a.url || '';
            chip.addEventListener('click', () => {
              const eAPI = window.electronAPI || null;
              const url = a.url || '';
              if (a.type === 'file' || a.link_type === 'md') {
                eAPI?.openPath?.(url);
              } else {
                eAPI?.openExternal?.(url) || window.open(url, '_blank');
              }
            });
            ctrl.appendChild(chip);
          });
        } else {
          ctrl.innerHTML = '<span style="font-size:12px;color:var(--cc-muted,#6e6e6e)">暂无附件</span>';
        }

      } else if (f.ctrl === 'select') {
        ctrl = document.createElement('select');
        ctrl.className = 'cc-field-select';
        ctrl.dataset.key = f.key;
        f.opts.forEach((o, i) => {
          const opt = document.createElement('option');
          opt.value = o;
          opt.textContent = (f.labels || [])[i] || o;
          if (val === o) opt.selected = true;
          ctrl.appendChild(opt);
        });

      } else if (f.ctrl === 'textarea') {
        ctrl = document.createElement('textarea');
        ctrl.className = 'cc-field-input';
        ctrl.rows = 4;
        ctrl.style.cssText = 'width:100%;resize:vertical;font-family:inherit;padding:5px 8px;background:var(--cc-bg2,#f7f6f3);border:1px solid var(--cc-border,#dcdcdc);border-radius:6px;color:var(--cc-text,#2e2e2e);font-size:13px;outline:none;';
        ctrl.value = val != null ? String(val) : '';
        ctrl.dataset.key = f.key;

      } else {
        ctrl = document.createElement('input');
        ctrl.type = f.type || 'text';
        ctrl.className = 'cc-field-input';
        ctrl.style.cssText = 'width:100%;padding:5px 8px;background:var(--cc-bg2,#f7f6f3);border:1px solid var(--cc-border,#dcdcdc);border-radius:6px;color:var(--cc-text,#2e2e2e);font-size:13px;outline:none;';
        ctrl.value = val != null ? String(val) : '';
        ctrl.dataset.key = f.key;
      }

      row.appendChild(label);
      row.appendChild(ctrl);
      scrollArea.appendChild(row);
    });

    // ── EntryThread 挂载点 ──────────────────────────────────────────────
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
      </div>`;
    scrollArea.appendChild(etWrap);
    containerEl.appendChild(scrollArea);

    // 保存当前数据引用
    _fullData = data;

    // 初始化 EntryThread
    setTimeout(() => {
      const mountEl = etWrap;
      if (!mountEl.id) mountEl.id = 'ccEntriesMount';
      let entries = data.entries;
      if (!Array.isArray(entries) || !entries.length) {
        entries = typeof EntryThread !== 'undefined' && EntryThread.migrate
          ? EntryThread.migrate(data) : [];
      }
      // 从 DB 懒加载 entries（DB 是权威数据源）
      _loadPopoutEntries(_fullItemType, _fullGid, _fullSource).then(dbEntries => {
        if (Array.isArray(dbEntries) && dbEntries.length) {
          entries = dbEntries;
          if (_fullData) _fullData.entries = dbEntries;
          if (_fullThread) _fullThread.setEntries(dbEntries);
        }
      }).catch(() => {});
      const isCloud = _fullSource === 'cloud' || _fullSource === 'feishu';
      const ownerGid = data.owner_user_gid || data.owner_gid || '';

      if (_fullThread) {
        _fullThread.setEntries(entries);
      } else {
        _fullThread = new EntryThread({
          mountEl,
          mode: 'human',
          entries,
          currentUserGid: '',
          userRole: '',
          listOwnerGid: ownerGid,
          isCloud,
          onChange: (ents) => {
            if (_fullData) _fullData.entries = ents;
            clearTimeout(_fullEntriesTimer);
            _fullEntriesTimer = setTimeout(async () => {
              try {
                await _savePopoutEntries(_fullItemType, _fullGid, _fullSource, ents);
              } catch (e) { console.error('[popout save entries]', e); }
            }, 800);
          },
          onSave: () => {},
          onStatusMsg: () => {},
        });
        _fullThread._bindGlobal(mountEl.id);
      }
    }, 50);

    // ── 自动保存状态显示 ────────────────────────────────────────────────
    function _showSaveStatus(state, msg) {
      const el = document.getElementById('ccSaveStatus');
      if (!el) return;
      clearTimeout(_fullStatusTimer);
      el.className = 'cc-save-status ' + state;
      el.textContent = state === 'saving' ? '保存中…' : state === 'saved' ? '已保存' : (msg || '保存失败');
      if (state === 'saved') {
        _fullStatusTimer = setTimeout(() => {
          el.textContent = '';
          el.className = 'cc-save-status';
        }, 1800);
      }
    }

    async function _autoSaveField(key, value) {
      if (!_fullGid) return;
      _showSaveStatus('saving');
      try {
        await _save(_fullItemType, _fullGid, _fullSource, { [key]: value });
        const cachedRow = _fullRowList[_fullRowIndex];
        if (cachedRow) cachedRow[key] = value;
        // 通知父窗口更新 grid 行数据（对象引用已更新，触发重渲染即可）
        window.parent?.postMessage({ type: 'cc:row-updated', gid: _fullGid, key, value }, '*');
        _showSaveStatus('saved');
      } catch (e) {
        const msg = e?.message || String(e || '未知错误');
        _showSaveStatus('error', '保存失败: ' + (msg.length > 20 ? msg.slice(0, 20) + '…' : msg));
      }
    }

    // 给每个可编辑字段绑定自动保存（匹配 RDP _bindAutoSave 的行为）
    scrollArea.querySelectorAll('input[data-key]:not([readonly]), textarea[data-key], select[data-key]').forEach(el => {
      const key = el.dataset.key;
      if (el.type === 'checkbox') {
        el.addEventListener('change', () => _autoSaveField(key, el.checked));
      } else if (el.tagName === 'SELECT' || el.type === 'date') {
        el.addEventListener('change', () => _autoSaveField(key, el.value));
      } else {
        el.addEventListener('input', () => {
          clearTimeout(_fullDebounce);
          _fullDebounce = setTimeout(() => _autoSaveField(key, el.value), 800);
        });
      }
    });

    // ── 事件绑定 ────────────────────────────────────────────────────────

    // 导航：上一条
    containerEl.querySelector('#ccNavPrev')?.addEventListener('click', () => {
      clearTimeout(_fullDebounce);
      if (_fullRowIndex <= 0) return;
      _fullRowIndex--;
      _fullGid = _fullRowList[_fullRowIndex]?.gid;
      _navigateToCurrent(containerEl, fields);
    });

    // 导航：下一条
    containerEl.querySelector('#ccNavNext')?.addEventListener('click', () => {
      clearTimeout(_fullDebounce);
      if (_fullRowIndex >= _fullRowList.length - 1) return;
      _fullRowIndex++;
      _fullGid = _fullRowList[_fullRowIndex]?.gid;
      _navigateToCurrent(containerEl, fields);
    });

    // 新建
    containerEl.querySelector('#ccNavNew')?.addEventListener('click', () => {
      const form = containerEl.querySelector('.cc-new-form');
      if (form) form.style.display = form.style.display === 'none' ? 'flex' : 'none';
    });

    // 新建表单：取消
    containerEl.querySelector('.cc-new-cancel')?.addEventListener('click', () => {
      const form = containerEl.querySelector('.cc-new-form');
      if (form) form.style.display = 'none';
      const titleInput = containerEl.querySelector('.cc-new-title');
      if (titleInput) titleInput.value = '';
    });

    // 新建表单：提交
    containerEl.querySelector('.cc-new-submit')?.addEventListener('click', async () => {
      const titleInput = containerEl.querySelector('.cc-new-title');
      const title = titleInput?.value?.trim();
      if (!title) { alert('请输入标题'); return; }

      const prioEl = containerEl.querySelector('.cc-new-prio');
      const sevEl  = containerEl.querySelector('.cc-new-severity');
      const fields_ = { title, priority: prioEl?.value, severity: sevEl?.value };

      const submitBtn = containerEl.querySelector('.cc-new-submit');
      submitBtn.disabled = true; submitBtn.textContent = '创建中…';
      try {
        const newRow = await _createItem(_fullItemType, fields_, _fullSource, _fullListGid);
        if (newRow) {
          newRow._source = _fullSource;
          _fullRowList.push(newRow);
          _fullRowIndex = _fullRowList.length - 1;
          _fullGid = newRow.gid;
        }
        const form = containerEl.querySelector('.cc-new-form');
        if (form) form.style.display = 'none';
        if (titleInput) titleInput.value = '';
        _navigateToCurrent(containerEl, fields_);
      } catch (e) {
        alert('创建失败: ' + (e?.message || e));
        submitBtn.disabled = false; submitBtn.textContent = '创建';
      }
    });

    // 更新页面标题
    const titleEl = document.getElementById('ccTitle');
    if (titleEl) titleEl.textContent = data.title || '条目详情';
  }

  function _navigateToCurrent(containerEl, fields) {
    const data = _fullRowList[_fullRowIndex];
    if (!data || !data.gid) return;
    clearTimeout(_fullDebounce);
    clearTimeout(_fullEntriesTimer);
    _fullThread = null;  // force recreate EntryThread for new DOM
    _renderFullPage(containerEl, data, fields);
    if (_fullScrollEl) _fullScrollEl.scrollTop = 0;
  }

  return { renderInCard, renderFullPage };
})();
