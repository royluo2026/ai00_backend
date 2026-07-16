'use strict';
/**
 * FeishuMentionChip
 * 飞书联系人 / 群聊 chip 渲染 + picker 弹窗。
 * 无依赖，暴露为 window.FeishuMentionChip。
 */
window.FeishuMentionChip = (() => {

  // ── 工具 ──────────────────────────────────────────────────────────────────

  function _esc(s) {
    return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  function _cf(url, opts) {
    const cf = window._cloudFetch || window.top?._cloudFetch || window.parent?._cloudFetch;
    if (cf) return cf(url, opts);
    return fetch(url, opts).then(r => r.json());
  }

  // ── Chip HTML ─────────────────────────────────────────────────────────────

  /**
   * 渲染用户 chip。
   * @param {string} openId
   * @param {string} name
   * @param {string|null} avatarUrl  当前未使用，预留
   * @returns {string} HTML
   */
  function renderUser(openId, name, avatarUrl) {
    const initial = (name || '?')[0].toUpperCase();
    const link = `feishu://applink/client/chat/open?openId=${encodeURIComponent(openId)}`;
    const avatarHtml = avatarUrl
      ? `<img class="fm-chip-avatar-img" src="${_esc(avatarUrl)}" alt="${_esc(initial)}" onerror="this.style.display='none';this.nextSibling.style.display='inline-flex'">`
        + `<span class="fm-chip-avatar" style="display:none">${_esc(initial)}</span>`
      : `<span class="fm-chip-avatar">${_esc(initial)}</span>`;
    return `<span class="fm-chip fm-chip-user" data-feishu-link="${_esc(link)}" title="${_esc(name)}">
      ${avatarHtml}
      <span class="fm-chip-name">${_esc(name || openId)}</span>
      <svg class="fm-chip-jump" viewBox="0 0 16 16" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 12L12 4M7 4h5v5"/></svg>
    </span>`;
  }

  /**
   * 渲染群聊 chip。
   * @param {string} chatId
   * @param {string} name
   * @returns {string} HTML
   */
  function renderGroup(chatId, name) {
    const link = `feishu://applink/client/chat/open?openChatId=${encodeURIComponent(chatId)}`;
    return `<span class="fm-chip fm-chip-group" data-feishu-link="${_esc(link)}" title="${_esc(name)}">
      <svg class="fm-chip-icon" viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><circle cx="6" cy="6" r="2.5"/><circle cx="11" cy="5" r="2"/><path d="M1 13c0-2.2 2-3.5 5-3.5s5 1.3 5 3.5"/><path d="M11 10c1.5.3 3 1.2 3 2.5"/></svg>
      <span class="fm-chip-name">${_esc(name || chatId)}</span>
      <svg class="fm-chip-jump" viewBox="0 0 16 16" width="11" height="11" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 12L12 4M7 4h5v5"/></svg>
    </span>`;
  }

  // ── Picker 弹窗 ───────────────────────────────────────────────────────────

  let _pickerEl = null;

  function _ensurePicker() {
    if (_pickerEl) return _pickerEl;
    _pickerEl = document.createElement('div');
    _pickerEl.id = 'fm-picker-overlay';
    _pickerEl.innerHTML = `
      <div id="fm-picker-box">
        <div id="fm-picker-tabs">
          <button class="fm-tab active" data-tab="user">联系人</button>
          <button class="fm-tab" data-tab="group">群聊</button>
          <button class="fm-tab" data-tab="doc">文档</button>
        </div>
        <input id="fm-picker-search" placeholder="搜索…" autocomplete="off">
        <div id="fm-picker-list"></div>
        <div id="fm-picker-footer">
          <button id="fm-picker-clear">清除</button>
          <button id="fm-picker-cancel">取消</button>
        </div>
      </div>
    `;
    document.body.appendChild(_pickerEl);
    _injectStyles();
    return _pickerEl;
  }

  let _currentMode = 'both';   // 'user' | 'group' | 'both'
  let _activeTab   = 'user';
  let _searchTimer = null;
  let _onSelectCb  = null;
  let _onClearCb   = null;

  function openPicker({ title, mode = 'both', onSelect, onClear }) {
    _currentMode = mode;
    _onSelectCb  = onSelect;
    _onClearCb   = onClear;

    const el     = _ensurePicker();
    const tabs   = el.querySelector('#fm-picker-tabs');
    const search = el.querySelector('#fm-picker-search');
    const list   = el.querySelector('#fm-picker-list');

    // 显示/隐藏 tab
    const showUser  = mode === 'user'  || mode === 'both';
    const showGroup = mode === 'group' || mode === 'both';
    const showDoc   = mode === 'doc';
    tabs.querySelector('[data-tab="user"]').style.display  = showUser  ? '' : 'none';
    tabs.querySelector('[data-tab="group"]').style.display = showGroup ? '' : 'none';
    tabs.querySelector('[data-tab="doc"]').style.display   = showDoc   ? '' : 'none';

    _activeTab = mode === 'doc' ? 'doc' : mode === 'group' ? 'group' : 'user';
    _setActiveTab(_activeTab);

    search.value = '';
    list.innerHTML = '';
    el.classList.add('show');

    // 自动获焦
    setTimeout(() => search.focus(), 50);

    // 绑定事件（每次重新绑）
    const newEl = el.cloneNode(true);
    el.parentNode.replaceChild(newEl, el);
    _pickerEl = newEl;
    _bindPickerEvents();

    _doSearch('');
  }

  function _bindPickerEvents() {
    const el     = _pickerEl;
    const tabs   = el.querySelectorAll('.fm-tab');
    const search = el.querySelector('#fm-picker-search');

    tabs.forEach(btn => {
      btn.addEventListener('click', () => {
        _activeTab = btn.dataset.tab;
        _setActiveTab(_activeTab);
        _doSearch(search.value.trim());
      });
    });

    search.addEventListener('input', () => {
      clearTimeout(_searchTimer);
      _searchTimer = setTimeout(() => _doSearch(search.value.trim()), 300);
    });

    el.querySelector('#fm-picker-clear').addEventListener('click', () => {
      _closePicker();
      _onClearCb?.();
    });

    el.querySelector('#fm-picker-cancel').addEventListener('click', _closePicker);

    el.addEventListener('click', e => {
      if (e.target === el) _closePicker();
    });

    // 结果行点击（委托）
    el.querySelector('#fm-picker-list').addEventListener('click', e => {
      const item = e.target.closest('.fm-pick-item');
      if (!item) return;
      const type = item.dataset.type;
      const result = type === 'user'
        ? { type: 'user', open_id: item.dataset.openId, name: item.dataset.name, avatar_url: item.dataset.avatar || '' }
        : type === 'doc'
          ? { type: 'doc', url: item.dataset.url, name: item.dataset.name, doc_type: item.dataset.docType || '' }
          : { type: 'group', chat_id: item.dataset.chatId, name: item.dataset.name };
      _closePicker();
      _onSelectCb?.(result);
    });
  }

  function _setActiveTab(tab) {
    if (!_pickerEl) return;
    _pickerEl.querySelectorAll('.fm-tab').forEach(b => {
      b.classList.toggle('active', b.dataset.tab === tab);
    });
  }

  function _closePicker() {
    if (_pickerEl) _pickerEl.classList.remove('show');
  }

  async function _doSearch(q) {
    const list = _pickerEl?.querySelector('#fm-picker-list');
    if (!list) return;
    list.innerHTML = '<div class="fm-pick-loading">搜索中…</div>';
    try {
      if (_activeTab === 'doc') {
        if (!q) { list.innerHTML = '<div class="fm-pick-empty">输入关键词搜索飞书文档</div>'; return; }
        const res = await _cf(`/feishu/search/docs?q=${encodeURIComponent(q)}&limit=10`).catch(() => null);
        const items = res?.data || [];
        if (!items.length) {
          list.innerHTML = '<div class="fm-pick-empty">无匹配文档</div>';
          return;
        }
        const _docTypeIcon = (t) => ({
          doc: `<svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 2h7l3 3v9H3z"/><polyline points="10,2 10,5 13,5"/></svg>`,
          docx: `<svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 2h7l3 3v9H3z"/><polyline points="10,2 10,5 13,5"/></svg>`,
          sheet: `<svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="2" y="2" width="12" height="12" rx="1"/><line x1="2" y1="6" x2="14" y2="6"/><line x1="6" y1="2" x2="6" y2="14"/></svg>`,
          bitable: `<svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="2" y="2" width="12" height="12" rx="1"/><line x1="2" y1="6" x2="14" y2="6"/><line x1="2" y1="10" x2="14" y2="10"/><line x1="6" y1="2" x2="6" y2="14"/></svg>`,
        }[t] || `<svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 2h7l3 3v9H3z"/></svg>`);
        list.innerHTML = items.map(d => `
          <div class="fm-pick-item" data-type="doc"
               data-url="${_esc(d.url||'')}"
               data-name="${_esc(d.name||'')}"
               data-doc-type="${_esc(d.type||'')}">
            <span class="fm-pick-avatar fm-pick-avatar-doc">${_docTypeIcon(d.type)}</span>
            <span class="fm-pick-info">
              <span class="fm-pick-name">${_esc(d.name||d.url||'')}</span>
              ${d.owner_name ? `<span class="fm-pick-sub">${_esc(d.owner_name)}</span>` : ''}
            </span>
          </div>
        `).join('');
        return;
      } else if (_activeTab === 'user') {
        const res = await _cf(`/feishu/search/users?q=${encodeURIComponent(q)}&limit=10`).catch(() => null);
        const items = res?.data || [];
        if (!items.length) {
          list.innerHTML = '<div class="fm-pick-empty">无匹配联系人</div>';
          return;
        }
        list.innerHTML = items.map(u => `
          <div class="fm-pick-item" data-type="user"
               data-open-id="${_esc(u.open_id||'')}"
               data-name="${_esc(u.name||'')}"
               data-avatar="${_esc(u.avatar_url||'')}">
            ${u.avatar_url
              ? `<img class="fm-pick-avatar fm-pick-avatar-img" src="${_esc(u.avatar_url)}" alt="${_esc((u.name||'?')[0])}" onerror="this.outerHTML='<span class=\\'fm-pick-avatar\\'>${_esc((u.name||'?')[0].toUpperCase())}</span>'">`
              : `<span class="fm-pick-avatar">${_esc((u.name||'?')[0].toUpperCase())}</span>`}
            <span class="fm-pick-info">
              <span class="fm-pick-name">${_esc(u.name||u.open_id||'')}</span>
              ${u.email ? `<span class="fm-pick-sub">${_esc(u.email)}</span>` : ''}
            </span>
          </div>
        `).join('');
      } else {
        const res = await _cf(`/feishu/search/chats?q=${encodeURIComponent(q)}&limit=10`).catch(() => null);
        const items = res?.data || [];
        if (!items.length) {
          list.innerHTML = '<div class="fm-pick-empty">无匹配群聊</div>';
          return;
        }
        list.innerHTML = items.map(c => `
          <div class="fm-pick-item" data-type="group"
               data-chat-id="${_esc(c.chat_id||c.id||'')}"
               data-name="${_esc(c.name||'')}">
            <span class="fm-pick-avatar fm-pick-avatar-group">#</span>
            <span class="fm-pick-info">
              <span class="fm-pick-name">${_esc(c.name||c.chat_id||'')}</span>
            </span>
          </div>
        `).join('');
      }
    } catch (e) {
      list.innerHTML = `<div class="fm-pick-empty">搜索失败</div>`;
    }
  }

  // ── 点击跳转委托 ──────────────────────────────────────────────────────────

  function bindClickDelegate(containerEl) {
    containerEl.addEventListener('click', e => {
      const chip = e.target.closest('[data-feishu-link]');
      if (!chip) return;
      // 不是点 jump 图标或 chip 主体本身时忽略（避免触发行选中等其他事件）
      const link = chip.dataset.feishuLink;
      if (!link) return;
      e.stopPropagation();
      _feishuOpen(link);
    });
  }

  function _feishuOpen(nativeUrl) {
    if (window.electronAPI?.openFeishuLink) {
      window.electronAPI.openFeishuLink(nativeUrl);
    } else if (window.electronAPI?.shellOpenExternal) {
      window.electronAPI.shellOpenExternal(nativeUrl);
    } else {
      window.open(nativeUrl, '_blank');
    }
  }

  // ── 样式注入（只注入一次）───────────────────────────────────────────────

  let _stylesInjected = false;
  function _injectStyles() {
    if (_stylesInjected) return;
    _stylesInjected = true;
    const style = document.createElement('style');
    style.textContent = `
/* FeishuMentionChip — chip styles */
.fm-chip {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 1px 6px 1px 3px;
  border-radius: 4px;
  font-size: 11px;
  cursor: pointer;
  white-space: nowrap;
  max-width: 130px;
  overflow: hidden;
  vertical-align: middle;
  user-select: none;
}
.fm-chip:hover { opacity: .8; }
.fm-chip-user {
  background: rgba(137,180,250,.18);
  color: #89b4fa;
  border: 1px solid rgba(137,180,250,.3);
}
.fm-chip-group {
  background: rgba(203,166,247,.18);
  color: #cba6f7;
  border: 1px solid rgba(203,166,247,.3);
}
.fm-chip-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px; height: 16px;
  border-radius: 50%;
  background: #89b4fa;
  color: #1e1e2e;
  font-size: 10px;
  font-weight: 600;
  flex-shrink: 0;
}
.fm-chip-group .fm-chip-avatar { background: #cba6f7; }
.fm-chip-avatar-img {
  width: 16px; height: 16px;
  border-radius: 50%;
  object-fit: cover;
  flex-shrink: 0;
}
.fm-chip-icon { flex-shrink: 0; }
.fm-chip-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 80px;
}
.fm-chip-jump { opacity: .6; flex-shrink: 0; }

/* picker overlay */
#fm-picker-overlay {
  display: none;
  position: fixed;
  inset: 0;
  z-index: 99999;
  align-items: center;
  justify-content: center;
  background: rgba(0,0,0,.45);
}
#fm-picker-overlay.show { display: flex; }
#fm-picker-box {
  background: var(--bg-primary, #1e1e2e);
  border: 1px solid var(--border-default, #313244);
  border-radius: 10px;
  width: 360px;
  max-height: 520px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 8px 32px rgba(0,0,0,.5);
}
#fm-picker-tabs {
  display: flex;
  border-bottom: 1px solid var(--border-default, #313244);
  padding: 0 12px;
}
.fm-tab {
  padding: 8px 12px;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text-muted, #a6adc8);
  font-size: 12px;
  cursor: pointer;
  margin-bottom: -1px;
}
.fm-tab.active {
  color: var(--color-accent, #89b4fa);
  border-bottom-color: var(--color-accent, #89b4fa);
}
#fm-picker-search {
  margin: 10px 12px 6px;
  padding: 7px 10px;
  background: var(--bg-secondary, #181825);
  border: 1px solid var(--border-default, #313244);
  border-radius: 6px;
  color: var(--text-normal, #cdd6f4);
  font-size: 12px;
  outline: none;
}
#fm-picker-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px 8px;
  min-height: 80px;
  max-height: 340px;
}
.fm-pick-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 8px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
}
.fm-pick-item:hover { background: var(--bg-hover, rgba(137,180,250,.08)); }
.fm-pick-avatar {
  width: 24px; height: 24px;
  border-radius: 50%;
  background: rgba(137,180,250,.2);
  color: #89b4fa;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 600;
  flex-shrink: 0;
}
.fm-pick-avatar-img {
  width: 24px; height: 24px;
  border-radius: 50%;
  object-fit: cover;
  flex-shrink: 0;
}
.fm-pick-avatar-group {
  background: rgba(203,166,247,.2);
  color: #cba6f7;
}
.fm-pick-avatar-doc {
  background: rgba(166,227,161,.2);
  color: #a6e3a1;
}
.fm-pick-info {
  display: flex;
  flex-direction: column;
  gap: 1px;
  overflow: hidden;
}
.fm-pick-name {
  color: var(--text-normal, #cdd6f4);
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.fm-pick-sub {
  color: var(--text-muted, #a6adc8);
  font-size: 10px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.fm-pick-loading, .fm-pick-empty {
  padding: 12px 8px;
  color: var(--text-muted, #a6adc8);
  font-size: 12px;
}
#fm-picker-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 8px 12px;
  border-top: 1px solid var(--border-default, #313244);
}
#fm-picker-footer button {
  padding: 4px 14px;
  border-radius: 5px;
  font-size: 12px;
  cursor: pointer;
  border: 1px solid var(--border-default, #313244);
  background: var(--bg-secondary, #181825);
  color: var(--text-muted, #a6adc8);
}
#fm-picker-footer button:hover { color: var(--text-normal, #cdd6f4); }

/* pick / edit buttons inside grid cells */
.fm-pick-btn, .fm-edit-btn {
  font-size: 11px;
  padding: 1px 7px;
  border-radius: 4px;
  border: 1px dashed var(--border-default, #313244);
  background: none;
  color: var(--text-muted, #a6adc8);
  cursor: pointer;
  vertical-align: middle;
  margin-left: 2px;
}
.fm-pick-btn:hover, .fm-edit-btn:hover {
  border-style: solid;
  color: var(--text-normal, #cdd6f4);
}
    `;
    document.head.appendChild(style);
  }

  // ── 公开 API ──────────────────────────────────────────────────────────────
  return { renderUser, renderGroup, openPicker, bindClickDelegate };

})();

