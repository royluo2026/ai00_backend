/**
 * self_annotation_panel.js — 自我标注浮动卡片（popover，全局单例）
 *
 * 用法：
 *   window.SelfAnnotationPanel.open(itemGid, itemTitle, anchorEl)
 *   window.SelfAnnotationPanel.close()
 *
 * 保存后派发 window 事件 'sap-saved'：
 *   { detail: { itemGid, status } }
 */
'use strict';

const SelfAnnotationPanel = (() => {
  let _panelEl           = null;
  let _currentGid        = null;
  let _currentTitle      = '';
  let _currentAttachments = [];   // 从后端加载，保存时原样写回

  /* ── 内部：通过宿主窗口 _cloudFetch 发请求 ─────────────────── */
  function _cf(path, opts) {
    const fn = window.parent?._cloudFetch || window._cloudFetch;
    return fn ? fn(path, opts).catch(() => null) : Promise.resolve(null);
  }

  /* ── 公开：打开面板 ─────────────────────────────────────────── */
  async function open(itemGid, itemTitle, anchorEl) {
    if (!itemGid) return;
    _build();

    // 同一 gid 再次点击 → 关闭
    if (_currentGid === itemGid && !_panelEl.classList.contains('sap-hidden')) {
      close();
      return;
    }

    _currentGid   = itemGid;
    _currentTitle = itemTitle || '';
    _panelEl.querySelector('.sap-item-title').textContent = _currentTitle;
    _panelEl.querySelector('.sap-save-msg').textContent   = '';

    // 先定位再显示，避免出现位置闪跳
    _positionNear(anchorEl);
    _panelEl.classList.remove('sap-hidden');
    await _load(itemGid);
  }

  /* ── 公开：关闭面板 ─────────────────────────────────────────── */
  function close() {
    _panelEl?.classList.add('sap-hidden');
    _currentGid = null;
  }

  /* ── 内部：定位到锚点附近 ──────────────────────────────────── */
  function _positionNear(anchor) {
    if (!_panelEl) return;
    const pw = 260;
    const ph = 220;   // 估算高度（渲染后可能更高，但方向已确定）
    const mg = 8;

    if (!anchor) {
      // 无锚点：固定在右下角
      _panelEl.style.right  = mg + 'px';
      _panelEl.style.bottom = '56px';
      _panelEl.style.left   = '';
      _panelEl.style.top    = '';
      return;
    }

    const rect = anchor.getBoundingClientRect();

    // 优先出现在右侧，溢出则在左侧
    let left = rect.right + mg;
    if (left + pw > window.innerWidth - mg) {
      left = rect.left - pw - mg;
    }
    if (left < mg) left = mg;

    // 顶部对齐锚点，溢出则上移
    let top = rect.top;
    if (top + ph > window.innerHeight - mg) {
      top = window.innerHeight - ph - mg;
    }
    if (top < mg) top = mg;

    _panelEl.style.left   = left + 'px';
    _panelEl.style.top    = top  + 'px';
    _panelEl.style.right  = '';
    _panelEl.style.bottom = '';
  }

  /* ── 内部：首次调用时创建 DOM ──────────────────────────────── */
  function _build() {
    if (_panelEl) return;

    _panelEl = document.createElement('div');
    _panelEl.id = 'sap-panel';
    _panelEl.className = 'sap-panel sap-hidden';
    _panelEl.innerHTML = `
      <div class="sap-header">
        <span class="sap-title">自我标注</span>
        <span class="sap-item-title"></span>
        <button class="sap-close" title="关闭">×</button>
      </div>
      <div class="sap-body">
        <label class="sap-field">
          <span>状态</span>
          <input list="sap-status-list" class="sap-status" placeholder="选择或输入…">
          <datalist id="sap-status-list">
            <option value="待关注"/>
            <option value="进行中"/>
            <option value="已完成"/>
            <option value="已搁置"/>
          </datalist>
        </label>
        <label class="sap-field">
          <span>排期</span>
          <input type="date" class="sap-schedule">
        </label>
        <label class="sap-field sap-field-col">
          <span>备注</span>
          <textarea class="sap-note" rows="3"></textarea>
        </label>
        <div class="sap-footer">
          <button class="sap-save">保存</button>
          <span class="sap-save-msg"></span>
        </div>
      </div>
    `;

    _panelEl.querySelector('.sap-close').addEventListener('click', close);
    _panelEl.querySelector('.sap-save').addEventListener('click', _save);

    // 点击面板外部关闭
    document.addEventListener('click', e => {
      if (_panelEl.classList.contains('sap-hidden')) return;
      if (_panelEl.contains(e.target)) return;
      if (e.target.closest?.('.sap-row-pin')) return;   // pin 图标自行处理
      close();
    });

    document.body.appendChild(_panelEl);
  }

  /* ── 内部：从后端加载数据填入表单 ─────────────────────────── */
  async function _load(gid) {
    const data = await _cf(`/api/self_ann/${gid}`);
    if (!data) return;

    _panelEl.querySelector('.sap-status').value   = data.self_status   || '';
    _panelEl.querySelector('.sap-schedule').value = data.self_schedule || '';
    _panelEl.querySelector('.sap-note').value     = data.self_note     || '';

    // 保存附件引用（不展示，但保存时原样写回以保留数据）
    _currentAttachments = Array.isArray(data.self_attachments) ? data.self_attachments : [];
  }

  /* ── 内部：保存 ────────────────────────────────────────────── */
  async function _save() {
    if (!_currentGid) return;
    const statusVal   = _panelEl.querySelector('.sap-status').value.trim();
    const scheduleVal = _panelEl.querySelector('.sap-schedule').value;
    const noteVal     = _panelEl.querySelector('.sap-note').value;

    const body = {
      item_title:       _currentTitle,
      self_status:      statusVal,
      self_schedule:    scheduleVal,
      self_note:        noteVal,
      self_attachments: _currentAttachments,   // 保留已有附件
    };

    const msgEl = _panelEl.querySelector('.sap-save-msg');
    msgEl.textContent = '保存中…';

    const res = await _cf(`/api/self_ann/${_currentGid}`, {
      method: 'PUT',
      body:   JSON.stringify(body),
    });

    if (res?.success) {
      msgEl.textContent = '已保存';
      setTimeout(() => { if (msgEl) msgEl.textContent = ''; }, 1800);
      window.dispatchEvent(new CustomEvent('sap-saved', {
        detail: { itemGid: _currentGid, status: statusVal },
      }));
    } else {
      msgEl.textContent = res === null ? '（离线）' : '保存失败';
    }
  }

  /* ── 内部：HTML 转义 ────────────────────────────────────────── */
  function _esc(s) {
    return String(s || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  return { open, close };
})();

window.SelfAnnotationPanel = SelfAnnotationPanel;

/* ═══════════════════════════════════════════════════════════════════════════
 * SapAnnotList — 模块内「已标注」列表覆层（单例）
 *
 * 用法：
 *   window.SapAnnotList.show({ module, title, offsetLeft, offsetTop });
 *   window.SapAnnotList.hide();
 *   window.SapAnnotList.refresh();
 * ═══════════════════════════════════════════════════════════════════════════ */
const SapAnnotList = (() => {
  let _el       = null;
  let _module   = '';
  let _filter   = '';
  let _allItems = [];

  const STATUS_FILTERS = ['', '待关注', '进行中', '已完成', '已搁置'];
  const STATUS_LABELS  = { '': '全部', '待关注': '待关注', '进行中': '进行中', '已完成': '已完成', '已搁置': '已搁置' };

  function _cf(path) {
    const fn = window.parent?._cloudFetch || window._cloudFetch;
    return fn ? fn(path).catch(() => null) : Promise.resolve(null);
  }

  function _esc(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function show(opts = {}) {
    _build();
    _module = opts.module || '';
    _filter = '';

    _el.querySelector('.sao-title').textContent = opts.title || '已标注';
    _el.style.left = (opts.offsetLeft || 0) + 'px';
    _el.style.top  = (opts.offsetTop  || 0) + 'px';

    _el.querySelectorAll('.sao-filter').forEach(f =>
      f.classList.toggle('active', f.dataset.filter === '')
    );

    _el.removeAttribute('hidden');
    _load();
  }

  function hide() {
    _el?.setAttribute('hidden', '');
  }

  function refresh() {
    if (_el && !_el.hasAttribute('hidden')) _load();
  }

  function _build() {
    if (_el) return;
    _el = document.createElement('div');
    _el.className = 'sao-overlay';
    _el.setAttribute('hidden', '');
    _el.innerHTML = `
      <div class="sao-header">
        <span class="sao-title"></span>
        <div class="sao-filters">
          ${STATUS_FILTERS.map(s =>
            `<span class="sao-filter${s === '' ? ' active' : ''}" data-filter="${s}">${STATUS_LABELS[s]}</span>`
          ).join('')}
        </div>
        <button class="sao-close" title="关闭">×</button>
      </div>
      <div class="sao-list"></div>
      <div class="sao-footer"><span class="sao-count"></span></div>
    `;

    _el.querySelector('.sao-close').addEventListener('click', hide);

    _el.querySelectorAll('.sao-filter').forEach(btn => {
      btn.addEventListener('click', () => {
        _filter = btn.dataset.filter;
        _el.querySelectorAll('.sao-filter').forEach(f =>
          f.classList.toggle('active', f.dataset.filter === _filter)
        );
        _render();
      });
    });

    document.body.appendChild(_el);
  }

  async function _load() {
    const listEl = _el.querySelector('.sao-list');
    listEl.innerHTML = '<div class="sao-loading">加载中…</div>';
    const url = _module
      ? `/api/self_ann/list?module=${encodeURIComponent(_module)}`
      : '/api/self_ann/list';
    const res = await _cf(url);
    _allItems = Array.isArray(res) ? res : [];
    _render();
  }

  function _render() {
    const listEl  = _el.querySelector('.sao-list');
    const countEl = _el.querySelector('.sao-count');
    const items = _filter ? _allItems.filter(a => a.self_status === _filter) : _allItems;

    countEl.textContent = `共 ${items.length} 条`;

    if (!items.length) {
      listEl.innerHTML = `<div class="sao-empty">${_filter ? '该状态下暂无标注' : '暂无标注'}</div>`;
      return;
    }

    listEl.innerHTML = '';
    items.forEach(ann => {
      const row = document.createElement('div');
      row.className = 'sao-item';
      row.dataset.gid = ann.item_gid;

      const schedule = ann.self_schedule
        ? `<span class="sao-meta-schedule"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg> ${_esc(ann.self_schedule)}</span>` : '';
      const noteSnip = ann.self_note
        ? `<span class="sao-meta-note" title="${ann.self_note.replace(/"/g, '&quot;')}"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg> ${_esc(ann.self_note.slice(0, 30))}${ann.self_note.length > 30 ? '…' : ''}</span>` : '';

      row.innerHTML = `
        <span class="sao-dot" data-status="${_esc(ann.self_status)}"></span>
        <div class="sao-item-body">
          <div class="sao-item-title">${_esc(ann.item_title || ann.item_gid)}</div>
          <div class="sao-item-meta">${schedule}${noteSnip}</div>
        </div>
        <button class="sao-open-btn" title="打开标注面板">编辑</button>
      `;

      row.querySelector('.sao-open-btn').addEventListener('click', e => {
        e.stopPropagation();
        window.SelfAnnotationPanel?.open(ann.item_gid, ann.item_title || '', e.currentTarget);
      });

      listEl.appendChild(row);
    });
  }

  window.addEventListener('sap-saved', () => refresh());

  return { show, hide, refresh };
})();

window.SapAnnotList = SapAnnotList;

