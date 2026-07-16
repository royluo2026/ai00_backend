/**
 * HubShell — 通用 Hub 二级页签管理器
 *
 * 功能：
 *   - 渲染二级横排页签，支持右键上移/下移/隐藏
 *   - 隐藏的页签通过末尾 ⋯ 按钮的溢出面板恢复
 *   - 状态持久化到 localStorage（顺序 + 隐藏集合）
 *   - 主题同步到 iframe 子页面
 *
 * 用法：
 *   const hub = new HubShell({
 *     hubId: 'knowledge_hub',
 *     tabs: [{ key, title, src, webSrc }],
 *     tabsEl: 'hubTabs',   // element id 或 HTMLElement
 *     frameEl: 'hubFrame', // element id 或 HTMLElement
 *   });
 *   hub.boot();
 */
// localStorage 账号隔离
function _hubLsk(base) {
  try { const u = window.parent?._authUser || window._authUser; const g = u?.gid || u?.user_gid || ''; return g ? `${g}:${base}` : base; } catch { return base; }
}

class HubShell {
  constructor({ hubId, tabs, tabsEl, frameEl }) {
    this._hubId  = hubId;
    this._TABS   = tabs; // [{ key, title, src, webSrc }]
    this._tabsEl = typeof tabsEl  === 'string' ? document.getElementById(tabsEl)  : tabsEl;
    this._frameEl= typeof frameEl === 'string' ? document.getElementById(frameEl) : frameEl;
    this._state  = null; // { order: [...keys], hidden: Set<key> }
    this._ctxKey = null;
    this._lsKey  = _hubLsk(`hub:${hubId}`);
    this._injectCSS();
  }

  // ── 公开 API ────────────────────────────────────────────

  boot() {
    this._state = this._loadState();
    this._render();

    // ── 将祖先窗口的 _authMode / _cloudFetch 桥接到本 Hub 页面 ──────────────
    // Task/Issue 等子 iframe 用 window.parent._cloudFetch / _authMode 读取这些值
    this._bridgeAuthFromAncestors();

    // 监听来自主窗口的认证状态广播，更新并转发给当前子 iframe
    window.addEventListener('message', e => {
      if (e.data?.type === 'auth-state') {
        window._authMode  = e.data.mode  || 'local';
        window._authUser  = e.data.user  || null;
        window._authToken = e.data.token || null;
        // 复制主窗口的 _cloudFetch（首次广播后主窗口应已设好）
        if (!window._cloudFetch) this._bridgeAuthFromAncestors();
        // 转发给当前激活的子 iframe
        try { this._frameEl.contentWindow?.postMessage(e.data, '*'); } catch (_) {}
      }
      // 外部（活动面板）远程切换子页签
      if (e.data?.type === 'hub:activate' && e.data.key) this.activate(e.data.key);
    });

    const urlKey   = new URLSearchParams(location.search).get('tabKey');
    const savedKey = !urlKey && localStorage.getItem(`${this._lsKey}:active`);
    const initKey  = urlKey || savedKey || this._state.order.find(k => !this._state.hidden.has(k));
    if (initKey) this.activate(initKey);
  }

  // 从祖先窗口把 _authMode 和 _cloudFetch 复制到本 Hub 页面
  _bridgeAuthFromAncestors() {
    try {
      let w = window;
      while (w.parent && w.parent !== w) {
        w = w.parent;
        if (!window._authMode  && w._authMode)   window._authMode  = w._authMode;
        if (!window._authUser  && w._authUser)    window._authUser  = w._authUser;
        if (!window._authToken && w._authToken)   window._authToken = w._authToken;
        if (!window._cloudFetch && w._cloudFetch) window._cloudFetch = w._cloudFetch;
      }
    } catch (_) { /* cross-origin guard */ }
  }

  activate(key) {
    const tab = this._getTab(key);
    if (!tab) return;

    // 若页签处于隐藏状态，先取消隐藏
    if (this._state.hidden.has(key)) {
      this._state.hidden.delete(key);
      this._saveState();
      this._render();
    }

    this._tabsEl.querySelectorAll('.hub-tab-item').forEach(el => el.classList.remove('active'));
    this._tabsEl.querySelector(`.hub-tab-item[data-key="${key}"]`)?.classList.add('active');

    if (this._frameEl.dataset.current !== tab.src) {
      this._frameEl.dataset.current = tab.src;
      // 网页版：给 HTML URL 加会话级时间戳，防止浏览器缓存旧版本
      let finalSrc = tab.src;
      if (window.parent?.electronAPI?._isElectron === false) {
        const sep = finalSrc.includes('?') ? '&' : '?';
        finalSrc = finalSrc + sep + '_cb=' + HubShell._sessionTs;
      }
      this._frameEl.src = finalSrc;
    }
    localStorage.setItem(`${this._lsKey}:active`, key);
    this._syncTheme();
  }

  applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme || 'dark');
    this._syncTheme();
  }

  // ── 内部：状态 ──────────────────────────────────────────

  _loadState() {
    try {
      const raw = localStorage.getItem(this._lsKey);
      if (raw) {
        const s = JSON.parse(raw);
        if (Array.isArray(s.order) && Array.isArray(s.hidden)) {
          const allKeys = this._TABS.map(t => t.key);
          // 补充新页签
          allKeys.filter(k => !s.order.includes(k) && !s.hidden.includes(k))
            .forEach(k => s.order.push(k));
          // 过滤已删除的页签
          s.order  = s.order.filter(k => allKeys.includes(k));
          s.hidden = s.hidden.filter(k => allKeys.includes(k));
          return { order: s.order, hidden: new Set(s.hidden) };
        }
      }
    } catch (_) {}
    return { order: this._TABS.map(t => t.key), hidden: new Set() };
  }

  _saveState() {
    localStorage.setItem(this._lsKey, JSON.stringify({
      order:  this._state.order,
      hidden: [...this._state.hidden],
    }));
  }

  _getTab(key) { return this._TABS.find(t => t.key === key); }

  // ── 内部：渲染 ─────────────────────────────────────────

  _render() {
    this._tabsEl.innerHTML = '';
    const visKeys = this._state.order.filter(k => !this._state.hidden.has(k));

    visKeys.forEach(key => {
      const tab = this._getTab(key);
      if (!tab) return;
      const el = document.createElement('div');
      el.className = 'hub-tab-item';
      el.dataset.key = key;
      const popSVG = `<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>`;
      el.innerHTML = `${tab.title}<button class="hub-tab-out" title="在新页签中打开">${popSVG}</button>`;

      el.addEventListener('click', e => {
        if (e.target.closest('.hub-tab-out')) return;
        this.activate(key);
      });
      el.querySelector('.hub-tab-out').addEventListener('click', e => {
        e.stopPropagation();
        this._popoutAsTab(key);
      });
      el.addEventListener('contextmenu', e => {
        e.preventDefault();
        this._showCtxMenu(e, key);
      });
      this._tabsEl.appendChild(el);
    });

    // ⋯ 溢出按钮（仅有隐藏页签时显示）
    if (this._state.hidden.size > 0) {
      const moreBtn = document.createElement('div');
      moreBtn.className = 'hub-tab-more';
      moreBtn.title = '显示隐藏的页签';
      moreBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 20 20" fill="currentColor"><circle cx="4" cy="10" r="1.5"/><circle cx="10" cy="10" r="1.5"/><circle cx="16" cy="10" r="1.5"/></svg>`;
      moreBtn.addEventListener('click', e => { e.stopPropagation(); this._showOverflowPanel(moreBtn); });
      this._tabsEl.appendChild(moreBtn);
    }

    // 保持当前激活项高亮
    const savedActive = localStorage.getItem(`${this._lsKey}:active`);
    if (savedActive) {
      this._tabsEl.querySelector(`.hub-tab-item[data-key="${savedActive}"]`)?.classList.add('active');
    }
  }

  // ── 内部：右键菜单 ─────────────────────────────────────

  _showCtxMenu(e, key) {
    this._ctxKey = key;
    const ctx = this._ensureCtxMenu();
    const visKeys = this._state.order.filter(k => !this._state.hidden.has(k));
    const idx = visKeys.indexOf(key);
    const tab = this._getTab(key);

    ctx.innerHTML = `
      <div class="hub-ctx-item${idx === 0 ? ' disabled' : ''}" data-action="up">↑ 上移</div>
      <div class="hub-ctx-item${idx === visKeys.length - 1 ? ' disabled' : ''}" data-action="down">↓ 下移</div>
      <div class="hub-ctx-sep"></div>
      <div class="hub-ctx-item" data-action="activate">在此处打开</div>
      <div class="hub-ctx-item" data-action="newtab">在新页签中打开</div>
      <div class="hub-ctx-item" data-action="float">在悬浮窗中打开</div>
      <div class="hub-ctx-sep"></div>
      <div class="hub-ctx-item" data-action="hide">隐藏「${tab.title}」</div>`;

    ctx.querySelectorAll('.hub-ctx-item:not(.disabled)').forEach(item => {
      item.addEventListener('click', () => {
        this._execCtxAction(item.dataset.action);
        ctx.classList.remove('open');
      });
    });

    const x = Math.min(e.clientX, window.innerWidth  - 190);
    const y = Math.min(e.clientY, window.innerHeight - 200);
    ctx.style.left = x + 'px';
    ctx.style.top  = y + 'px';
    ctx.classList.add('open');
  }

  _execCtxAction(action) {
    const key = this._ctxKey;
    if (!key) return;

    const visKeys = this._state.order.filter(k => !this._state.hidden.has(k));
    const idx = visKeys.indexOf(key);

    if (action === 'up' && idx > 0) {
      const oIdx = this._state.order.indexOf(key);
      const prevIdx = this._state.order.indexOf(visKeys[idx - 1]);
      [this._state.order[oIdx], this._state.order[prevIdx]] = [this._state.order[prevIdx], this._state.order[oIdx]];
    } else if (action === 'down' && idx < visKeys.length - 1) {
      const oIdx = this._state.order.indexOf(key);
      const nextIdx = this._state.order.indexOf(visKeys[idx + 1]);
      [this._state.order[oIdx], this._state.order[nextIdx]] = [this._state.order[nextIdx], this._state.order[oIdx]];
    } else if (action === 'hide') {
      this._state.hidden.add(key);
    } else if (action === 'activate') {
      this.activate(key); return;
    } else if (action === 'newtab') {
      this._popoutAsTab(key); return;
    } else if (action === 'float') {
      const tab = this._getTab(key);
      window.parent?.postMessage({ type: 'float:open', webSrc: tab.webSrc }, '*');
      return;
    } else {
      return;
    }

    this._saveState();
    this._render();

    // 如果当前激活页签被隐藏，切换到第一个可见的
    const activeKey = localStorage.getItem(`${this._lsKey}:active`);
    if (!activeKey || this._state.hidden.has(activeKey)) {
      const first = this._state.order.find(k => !this._state.hidden.has(k));
      if (first) this.activate(first);
    }
  }

  _ensureCtxMenu() {
    let ctx = document.getElementById('hubCtxMenu');
    if (!ctx) {
      ctx = document.createElement('div');
      ctx.id = 'hubCtxMenu';
      ctx.className = 'hub-ctx';
      document.body.appendChild(ctx);
    }
    ctx.classList.remove('open');
    document.addEventListener('click', () => ctx.classList.remove('open'), { once: true });
    return ctx;
  }

  // ── 内部：溢出面板 ─────────────────────────────────────

  _showOverflowPanel(anchorEl) {
    let panel = document.getElementById('hubOverflowPanel');
    if (!panel) {
      panel = document.createElement('div');
      panel.id = 'hubOverflowPanel';
      panel.className = 'hub-overflow-panel';
      document.body.appendChild(panel);
    }

    panel.innerHTML = '';
    const hiddenKeys = this._state.order.filter(k => this._state.hidden.has(k));
    hiddenKeys.forEach(k => {
      const tab = this._getTab(k);
      if (!tab) return;
      const el = document.createElement('div');
      el.className = 'hub-overflow-item';
      el.innerHTML = `<span>${tab.title}</span><button class="hub-overflow-pin" title="固定到页签栏">+</button>`;
      el.querySelector('button').addEventListener('click', e => {
        e.stopPropagation();
        this._state.hidden.delete(k);
        this._saveState();
        this._render();
        this.activate(k);
        panel.classList.remove('open');
      });
      el.addEventListener('click', () => {
        this.activate(k);
        panel.classList.remove('open');
      });
      panel.appendChild(el);
    });

    if (!panel.children.length) return;

    const rect = anchorEl.getBoundingClientRect();
    panel.style.left = Math.min(rect.left, window.innerWidth - 180) + 'px';
    panel.style.top  = (rect.bottom + 4) + 'px';
    panel.classList.add('open');

    const close = evt => {
      if (!panel.contains(evt.target) && evt.target !== anchorEl) {
        panel.classList.remove('open');
        document.removeEventListener('mousedown', close);
      }
    };
    setTimeout(() => document.addEventListener('mousedown', close), 10);
  }

  // ── 内部：popout / 主题 ────────────────────────────────

  _popoutAsTab(key) {
    window.parent?.postMessage({ type: 'tab:open', id: this._hubId, tabKey: key }, '*');
  }

  _syncTheme() {
    try {
      this._frameEl.contentWindow?.postMessage(
        { type: 'theme', theme: document.documentElement.dataset.theme || 'dark' }, '*');
    } catch (_) {}
  }

  // ── 内部：注入 CSS ────────────────────────────────────

  _injectCSS() {
    if (document.getElementById('hub-shell-style')) return;
    const style = document.createElement('style');
    style.id = 'hub-shell-style';
    style.textContent = `
      .hub-tab-more {
        display: flex; align-items: center; justify-content: center;
        width: 26px; height: 28px; cursor: pointer; border-radius: 4px;
        color: var(--text-muted); flex-shrink: 0;
        transition: background .15s, color .15s;
      }
      .hub-tab-more:hover { background: var(--hover); color: var(--text); }

      .hub-ctx {
        position: fixed; background: var(--bg2); border: 1px solid var(--border);
        border-radius: 6px; padding: 4px 0; z-index: 9999; min-width: 160px;
        box-shadow: 0 4px 16px rgba(0,0,0,.3); display: none;
      }
      .hub-ctx.open { display: block; }
      .hub-ctx-item {
        padding: 7px 16px; cursor: pointer; font-size: 13px;
        white-space: nowrap; color: var(--text);
      }
      .hub-ctx-item:hover { background: var(--hover); }
      .hub-ctx-item.disabled { opacity: .38; pointer-events: none; }
      .hub-ctx-sep { height: 1px; background: var(--border); margin: 4px 0; }

      .hub-overflow-panel {
        position: fixed; background: var(--bg2); border: 1px solid var(--border);
        border-radius: 6px; padding: 4px 0; z-index: 9999; min-width: 160px;
        box-shadow: 0 4px 16px rgba(0,0,0,.3); display: none;
      }
      .hub-overflow-panel.open { display: block; }
      .hub-overflow-item {
        display: flex; align-items: center; justify-content: space-between;
        padding: 7px 12px 7px 16px; cursor: pointer; font-size: 13px;
        color: var(--text); gap: 8px;
      }
      .hub-overflow-item:hover { background: var(--hover); }
      .hub-overflow-pin {
        flex-shrink: 0; width: 20px; height: 20px; border: none;
        background: none; color: var(--text-muted); cursor: pointer;
        border-radius: 3px; font-size: 15px; line-height: 1;
        display: flex; align-items: center; justify-content: center;
        transition: background .1s, color .1s;
      }
      .hub-overflow-pin:hover { background: rgba(137,180,250,.15); color: var(--accent); }
    `;
    document.head.appendChild(style);
  }
}


// 会话级时间戳：同一次页面加载内所有 hub tab 使用相同的 cache-buster
HubShell._sessionTs = Date.now();
