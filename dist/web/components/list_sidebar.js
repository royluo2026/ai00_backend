/**
 * ListSidebar — 清单侧边栏组件
 * 用于 task / issue / knowledge / rule 四个模块
 *
 * 使用方式：
 *   const sidebar = new ListSidebar({
 *     containerEl: document.getElementById('listSidebar'),
 *     itemType: 'task',          // 'task'|'issue'|'knowledge'|'rule'
 *     onSelect: (listGid) => {}, // null = 全部
 *     onListsChange: (lists) => {},
 *   });
 *   sidebar.init();
 */

class ListSidebar {
  constructor({ containerEl, itemType = 'task', onSelect, onListsChange,
                extraItemHtml, onCreate, onContextMenu, disableInlineRename = false }) {
    this._el        = containerEl;
    this._itemType  = itemType;
    this._onSelect  = onSelect      || (() => {});
    this._onListsChange = onListsChange || (() => {});
    this._extraItemHtml = extraItemHtml || null;
    this._onCreate  = onCreate      || null;
    this._onContextMenu = onContextMenu || null;           // 完全接管右键菜单
    this._disableInlineRename = disableInlineRename;       // 禁止双击改名（BOP版本等自管理侧边栏）
    this._selected  = null; // null = 全部
    this._lists     = [];
    this._editingGid = null;
    this._searchQ   = '';
    this._archivedOpen = false;
    this._scroll    = null;
    this._draggingGid = null;   // 当前正在拖拽的清单 GID
  }

  // ── localStorage helpers ─────────────────────────────────────────────────
  _lsk(base) { try { const u = window.parent?._authUser || window.top?._authUser || window._authUser; const g = u?.gid || u?.user_gid || ''; return g ? `${g}:${base}` : base; } catch { return base; } }
  _key(k)         { return this._lsk(`ls_${k}_${this._itemType}`); }
  _getPinned()    { return new Set(JSON.parse(localStorage.getItem(this._key('pin'))    || '[]')); }
  _getArchived()  { return new Set(JSON.parse(localStorage.getItem(this._key('arc'))    || '[]')); }
  _setPinned(s)   { localStorage.setItem(this._key('pin'),    JSON.stringify([...s])); }
  _setArchived(s) { localStorage.setItem(this._key('arc'),    JSON.stringify([...s])); }
  // 分组：{ [listGid]: groupName }
  _getGroups()    { return JSON.parse(localStorage.getItem(this._key('grp'))    || '{}'); }
  _setGroups(g)   { localStorage.setItem(this._key('grp'),    JSON.stringify(g)); }
  // 折叠的分组名集合
  _getGrpCollapsed() { return new Set(JSON.parse(localStorage.getItem(this._key('grpcol')) || '[]')); }
  _setGrpCollapsed(s){ localStorage.setItem(this._key('grpcol'), JSON.stringify([...s])); }

  // ── 初始化 ────────────────────────────────────────────────────────────────
  async init() {
    await this._loadLists();
    this._render();

    // 初始化时自动选中第一个清单（确保 _currentList 有值）
    if (!this._selected && this._lists.length > 0) {
      this._select(this._lists[0].gid);
    }

    // 监听主窗口认证状态变化（登录/登出），自动刷新清单列表
    if (!this._authListener) {
      this._authListener = (e) => {
        if (e.data?.type === 'auth-state') {
          console.log(`[ListSidebar:${this._itemType}] 收到 auth-state 变化，重新加载清单...`);
          this._loadLists().then(() => this._renderItems());
        }
      };
      window.addEventListener('message', this._authListener);
    }
  }

  /** 外部可调用：强制重新加载清单列表（如认证状态变化后） */
  async reload() {
    await this._loadLists();
    this._renderItems();
  }

  _cf(path, opts = {}) {
    // 优先用主窗口的 _cloudFetch（已验证 task/issue CRUD 可用），避免 iframe 内 fetch() 跨域问题
    const cf = window.top?._cloudFetch || window.parent?._cloudFetch || window._cloudFetch;
    if (cf) return cf(path, opts);

    // 降级：直接使用 electronAPI（本地模式或 _cloudFetch 未挂载时）
    const eAPI = window.top?.electronAPI || window.parent?.electronAPI || window.electronAPI;
    if (!eAPI) return Promise.reject(new Error('_cloudFetch 未就绪'));
    return (async () => {
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
    })();
  }

  async _loadLists() {
    // 云端 PG 清单
    let cloudLists = [];
    try {
      const res = await this._cf(`/api/lists?item_type=${this._itemType}`);
      cloudLists = (res?.data || []).map(l => ({ ...l, _source: 'cloud' }));
      console.log(`[ListSidebar:${this._itemType}] 云端清单结果:`, cloudLists.length);
    } catch (e) {
      if (!String(e?.message || e).includes('_cloudFetch 未就绪')) {
        console.warn('[ListSidebar] 云端清单加载失败:', e);
      }
    }

    // 去重（仅云端）
    const seen = new Set();
    this._lists = cloudLists.filter(l => {
      if (seen.has(l.gid)) return false;
      seen.add(l.gid);
      return true;
    });
    console.log(`[ListSidebar:${this._itemType}] 合并后 _lists:`, this._lists.length, this._lists.map(l => `${l.name}(${l.owner_type},${l.storage_scope})`));
    this._onListsChange(this._lists);
  }

  // ── 渲染骨架（只在初始化时调用一次）─────────────────────────────────────
  _render() {
    if (!this._el) return;
    this._el.innerHTML = '';

    const style = document.createElement('style');
    style.textContent = `
      .ls-wrap { height:100%; display:flex; flex-direction:column; overflow:hidden; }
      .ls-header { padding:8px 8px 4px; display:flex; flex-direction:column; gap:4px; }
      .ls-btn-new { width:100%; padding:5px 8px; background:transparent;
        border:1px dashed var(--border-default,#313244); border-radius:5px;
        color:var(--text-muted,#a6adc8); cursor:pointer; font-size:12px;
        display:flex; align-items:center; justify-content:center; gap:5px; }
      .ls-btn-new:hover { border-color:var(--color-accent,#89b4fa); color:var(--color-accent,#89b4fa); }
      .ls-search { width:100%; box-sizing:border-box; padding:4px 7px; font-size:12px;
        background:var(--bg-secondary,#181825); border:1px solid var(--border-default,#313244);
        border-radius:5px; color:var(--text-normal,#cdd6f4); outline:none; }
      .ls-search:focus { border-color:var(--color-accent,#89b4fa); }
      .ls-search::placeholder { color:var(--text-faint,#6c7086); }
      .ls-divider { height:1px; background:var(--border-default,#313244); margin:3px 0; }
      .ls-scroll { flex:1; overflow-y:auto; padding:0 4px 8px; }
      .ls-item { display:flex; align-items:center; gap:5px; padding:5px 6px;
        border-radius:5px; cursor:pointer; user-select:none; }
      .ls-item:hover { background:rgba(255,255,255,.05); }
      .ls-item.active { background:rgba(137,180,250,.12); color:var(--color-accent,#89b4fa); }
      [data-theme="light"] .ls-item:hover { background:rgba(0,0,0,.04); }
      [data-theme="light"] .ls-item.active { background:rgba(30,102,245,.08); }
      .ls-dot  { width:7px; height:7px; border-radius:50%; flex-shrink:0; }
      .ls-name { flex:1; font-size:12px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
      .ls-count { font-size:10px; color:var(--text-faint,#6c7086); flex-shrink:0; }
      .ls-pin-icon { flex-shrink:0; color:var(--text-faint,#6c7086); line-height:1; }
      .ls-item.active .ls-pin-icon { color:var(--color-accent,#89b4fa); opacity:.7; }
      .ls-ctx-menu { position:fixed; z-index:9999; background:var(--bg-surface,#24273a);
        border:1px solid var(--border-default,#313244); border-radius:7px;
        box-shadow:0 4px 16px rgba(0,0,0,.3); padding:4px 0; min-width:110px; }
      .ls-ctx-item { padding:6px 14px; font-size:13px; cursor:pointer; white-space:nowrap; }
      .ls-ctx-item:hover { background:rgba(255,255,255,.06); }
      .ls-ctx-item.danger { color:#f38ba8; }
      .ls-ctx-sep { height:1px; background:var(--border-default,#313244); margin:3px 0; }
      [data-theme="light"] .ls-ctx-item:hover { background:rgba(0,0,0,.05); }
      /* ── 转让 Owner 弹层 ── */
      .ls-owner-modal { position:fixed; inset:0; z-index:10000; background:rgba(0,0,0,.45);
        display:flex; align-items:center; justify-content:center; }
      .ls-om-box { background:var(--bg-surface,#24273a); border:1px solid var(--border-default,#313244);
        border-radius:10px; width:340px; max-height:420px; display:flex; flex-direction:column;
        box-shadow:0 20px 50px rgba(0,0,0,.4); padding:16px; gap:10px; }
      .ls-om-title { font-size:14px; font-weight:700; color:var(--text-normal,#cdd6f4); }
      .ls-om-sub { font-size:11px; color:var(--text-faint,#6c7086); }
      .ls-om-input { padding:6px 10px; border:1px solid var(--border-default,#313244); border-radius:6px;
        background:var(--bg-secondary,#181825); color:var(--text-normal,#cdd6f4); font-size:12px; outline:none; }
      .ls-om-input:focus { border-color:var(--color-accent,#89b4fa); }
      .ls-om-list { flex:1; overflow-y:auto; display:flex; flex-direction:column; gap:2px; }
      .ls-om-user { display:flex; align-items:center; gap:8px; padding:6px 8px; border-radius:6px;
        cursor:pointer; }
      .ls-om-user:hover { background:rgba(255,255,255,.06); }
      .ls-om-user.selected { background:rgba(137,180,250,.12); }
      .ls-om-avatar { width:24px; height:24px; border-radius:50%; background:var(--color-accent,#89b4fa);
        color:var(--bg-primary,#1e1e2e); display:flex; align-items:center; justify-content:center;
        font-size:11px; font-weight:700; flex-shrink:0; }
      .ls-om-uname { font-size:12px; color:var(--text-normal,#cdd6f4); flex:1; }
      .ls-om-uemail { font-size:10px; color:var(--text-faint,#6c7086); }
      .ls-om-empty { font-size:12px; color:var(--text-faint,#6c7086); padding:8px; text-align:center; }
      .ls-om-footer { display:flex; justify-content:flex-end; }
      .ls-om-btn { padding:4px 12px; border-radius:5px; font-size:12px; cursor:pointer;
        border:1px solid var(--border-default,#313244); background:transparent;
        color:var(--text-muted,#a6adc8); }
      /* ── 可见范围弹层 ── */
      .ls-vis-pop { position:fixed; z-index:10000; background:var(--bg-surface,#24273a);
        border:1px solid var(--border-default,#313244); border-radius:8px;
        box-shadow:0 8px 24px rgba(0,0,0,.35); padding:4px 0; min-width:200px; }
      .ls-vis-item { padding:8px 14px; cursor:pointer; }
      .ls-vis-item:hover { background:rgba(255,255,255,.06); }
      .ls-vis-item.active { background:rgba(137,180,250,.1); }
      .ls-vis-label { font-size:13px; color:var(--text-normal,#cdd6f4); }
      .ls-vis-desc { font-size:10px; color:var(--text-faint,#6c7086); margin-top:1px; }
      [data-theme="light"] .ls-om-user:hover { background:rgba(0,0,0,.04); }
      [data-theme="light"] .ls-vis-item:hover { background:rgba(0,0,0,.04); }
      .ls-edit-input { flex:1; padding:2px 5px; min-width:0; font-size:12px; outline:none;
        background:var(--bg-secondary,#181825); border:1px solid var(--color-accent,#89b4fa);
        border-radius:4px; color:var(--text-normal,#cdd6f4); }
      .ls-new-row { display:flex; align-items:center; gap:3px; padding:3px 4px; }
      .ls-new-input { flex:1; padding:3px 6px; min-width:0; font-size:12px; outline:none;
        background:var(--bg-secondary,#181825); color:var(--text-normal,#cdd6f4);
        border:1px solid var(--color-accent,#89b4fa); border-radius:4px; }
      .ls-new-ok { padding:2px 6px; font-size:11px; border-radius:3px; cursor:pointer;
        border:none; background:var(--color-accent,#89b4fa); color:var(--bg-primary,#1e1e2e); flex-shrink:0; }
      .ls-new-cancel { padding:2px 5px; font-size:11px; border-radius:3px; cursor:pointer; flex-shrink:0;
        background:transparent; border:1px solid var(--border-default,#313244); color:var(--text-faint,#6c7086); }
      .ls-section-label { font-size:10px; font-weight:600; letter-spacing:.05em;
        text-transform:uppercase; color:var(--text-faint,#6c7086); padding:6px 8px 2px; }
      .ls-arc-hdr { display:flex; align-items:center; gap:5px; padding:5px 8px;
        cursor:pointer; user-select:none; color:var(--text-faint,#6c7086); font-size:11px; }
      .ls-arc-hdr:hover { color:var(--text-muted,#a6adc8); }
      .ls-arc-arrow { font-size:9px; display:inline-block; transition:transform .15s; }
      .ls-arc-arrow.open { transform:rotate(90deg); }
      .ls-scope-badge { font-size:9px; padding:1px 4px; border-radius:3px; flex-shrink:0;
        background:rgba(108,112,134,.2); color:var(--text-faint,#6c7086); }
      .ls-scope-badge.local { background:rgba(249,226,175,.15); color:#f9e2af; }
      [data-theme="light"] .ls-scope-badge.local { background:rgba(223,142,29,.1); color:#df8e1d; }
      .ls-scope-toggle { padding:2px 6px; font-size:10px; border-radius:3px; cursor:pointer;
        flex-shrink:0; border:1px solid var(--border-default,#313244);
        background:rgba(249,226,175,.1); color:#f9e2af; transition:background .12s,color .12s; }
      .ls-scope-toggle.cloud { background:rgba(137,180,250,.1); color:var(--color-accent,#89b4fa); }
      [data-theme="light"] .ls-scope-toggle { color:#df8e1d; }
      [data-theme="light"] .ls-scope-toggle.cloud { color:var(--color-accent,#1e66f5); }
      .ls-scope-group { display:flex; gap:2px; flex-shrink:0; }
      .ls-scope-opt { padding:2px 6px; font-size:10px; border-radius:3px; cursor:pointer;
        border:1px solid var(--border-default,#313244);
        background:transparent; color:var(--text-faint,#6c7086);
        transition:background .12s,color .12s,border-color .12s; }
      .ls-scope-opt:hover { border-color:var(--text-muted,#a6adc8); color:var(--text-muted,#a6adc8); }
      .ls-scope-opt.selected-local { background:rgba(249,226,175,.15); color:#f9e2af; border-color:#f9e2af; }
      .ls-scope-opt.selected-cloud { background:rgba(137,180,250,.12); color:var(--color-accent,#89b4fa); border-color:var(--color-accent,#89b4fa); }
      [data-theme="light"] .ls-scope-opt.selected-local { color:#df8e1d; border-color:#df8e1d; background:rgba(223,142,29,.08); }
      [data-theme="light"] .ls-scope-opt.selected-cloud { color:var(--color-accent,#1e66f5); border-color:var(--color-accent,#1e66f5); }
      .ls-new-ok:disabled { opacity:.4; cursor:not-allowed; }
      /* ── 拖拽 ── */
      .ls-item.ls-dragging { opacity:.3; }
      .ls-arc-hdr.ls-grp-drop-target { background:rgba(137,180,250,.18); border-radius:5px;
        color:var(--color-accent,#89b4fa); }
      [data-theme="light"] .ls-arc-hdr.ls-grp-drop-target { background:rgba(30,102,245,.1); }
      /* ── 新建清单 Popover ── */
      .ls-create-pop { position:fixed; z-index:99999; background:var(--bg-surface,#24273a);
        border:1px solid var(--border-default,#313244); border-radius:10px;
        box-shadow:0 8px 30px rgba(0,0,0,.4); width:260px; padding:14px;
        display:flex; flex-direction:column; gap:10px; }
      .ls-cp-title { font-size:13px; font-weight:700; color:var(--text-normal,#cdd6f4); }
      .ls-cp-label { font-size:11px; color:var(--text-muted,#a6adc8); margin-bottom:4px; display:block; }
      .ls-cp-input { width:100%; box-sizing:border-box; padding:5px 8px; font-size:12px;
        background:var(--bg-secondary,#181825); border:1px solid var(--border-default,#313244);
        border-radius:5px; color:var(--text-normal,#cdd6f4); outline:none; }
      .ls-cp-input:focus { border-color:var(--color-accent,#89b4fa); }
      .ls-cp-colors { display:flex; align-items:center; gap:5px; flex-wrap:wrap; }
      .ls-cp-swatch { width:18px; height:18px; border-radius:4px; cursor:pointer; flex-shrink:0;
        border:2px solid transparent; transition:transform .1s,border-color .1s; box-sizing:border-box; }
      .ls-cp-swatch:hover { transform:scale(1.15); }
      .ls-cp-swatch.selected { border-color:var(--text-normal,#cdd6f4); transform:scale(1.05); }
      .ls-cp-vis { display:flex; gap:3px; }
      .ls-cp-vis-btn { flex:1; padding:4px 0; font-size:11px; border-radius:4px; cursor:pointer;
        border:1px solid var(--border-default,#313244); background:transparent;
        color:var(--text-muted,#a6adc8); text-align:center;
        transition:background .12s,color .12s,border-color .12s; }
      .ls-cp-vis-btn:hover { border-color:var(--text-muted,#a6adc8); color:var(--text-muted,#a6adc8); }
      .ls-cp-vis-btn.active { background:rgba(137,180,250,.15); color:var(--color-accent,#89b4fa);
        border-color:var(--color-accent,#89b4fa); }
      [data-theme="light"] .ls-cp-vis-btn.active { background:rgba(30,102,245,.1);
        color:var(--color-accent,#1e66f5); border-color:var(--color-accent,#1e66f5); }
      .ls-cp-select { width:100%; box-sizing:border-box; padding:4px 8px; font-size:12px;
        background:var(--bg-secondary,#181825); border:1px solid var(--border-default,#313244);
        border-radius:5px; color:var(--text-normal,#cdd6f4); outline:none; height:28px; }
      .ls-cp-select:focus { border-color:var(--color-accent,#89b4fa); }
      .ls-cp-error { font-size:11px; color:#f38ba8; }
      .ls-cp-footer { display:flex; justify-content:flex-end; gap:8px; }
      .ls-cp-btn-cancel { padding:4px 12px; font-size:12px; border-radius:5px; cursor:pointer;
        border:1px solid var(--border-default,#313244); background:transparent;
        color:var(--text-muted,#a6adc8); }
      .ls-cp-btn-ok { padding:4px 12px; font-size:12px; border-radius:5px; cursor:pointer;
        border:none; background:var(--color-accent,#89b4fa); color:var(--bg-primary,#1e1e2e); font-weight:600; }
      .ls-cp-btn-ok:disabled { opacity:.4; cursor:not-allowed; }
      [data-theme="light"] .ls-create-pop { background:#fff; box-shadow:0 8px 30px rgba(0,0,0,.15); }
      [data-theme="light"] .ls-cp-input,[data-theme="light"] .ls-cp-select {
        background:#f3f4f6; border-color:#d1d5db; color:#374151; }
    `;
    this._el.appendChild(style);

    const wrap = document.createElement('div');
    wrap.className = 'ls-wrap';

    // 新建按钮
    const header = document.createElement('div');
    header.className = 'ls-header';

    const btnNew = document.createElement('button');
    btnNew.className = 'ls-btn-new';
    btnNew.innerHTML = `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>新建清单`;
    btnNew.addEventListener('click', () => {
      if (this._onCreate) { this._onCreate(); return; }
      this._openCreatePopover(btnNew);
    });
    header.appendChild(btnNew);

    // 搜索框
    const searchEl = document.createElement('input');
    searchEl.className = 'ls-search';
    searchEl.placeholder = '搜索清单…';
    searchEl.value = this._searchQ;
    searchEl.addEventListener('input', () => { this._searchQ = searchEl.value; this._renderItems(); });
    header.appendChild(searchEl);

    wrap.appendChild(header);

    const divider = document.createElement('div');
    divider.className = 'ls-divider';
    wrap.appendChild(divider);

    const scroll = document.createElement('div');
    scroll.className = 'ls-scroll';
    wrap.appendChild(scroll);

    this._el.appendChild(wrap);
    this._scroll = scroll;
    this._renderItems();
  }

  // ── 渲染列表内容（搜索/置顶/归档变化时调用）──────────────────────────────
  _renderItems() {
    const scroll = this._scroll;
    if (!scroll) return;
    // Custom render hook (allows modules to completely override item rendering)
    if (typeof this._customRender === 'function') {
      this._customRender(scroll);
      return;
    }
    scroll.innerHTML = '';

    const q        = this._searchQ.toLowerCase().trim();
    const pinned   = this._getPinned();
    const archived = this._getArchived();
    const isFeishu = (window.top?._authMode || window.parent?._authMode || window._authMode) === 'feishu';
    const myGid    = window.top?._authUser?.gid || window.parent?._authUser?.gid || '';

    // 全部 + 无清单条目（搜索时隐藏）
    if (!q) {
      scroll.appendChild(this._makeItem(null,           '全部',     '#6c7086', null));
      scroll.appendChild(this._makeItem('__no_list__',  '无清单条目','#a6adc8', null));
      const d = document.createElement('div');
      d.className = 'ls-divider';
      d.style.marginBottom = '2px';
      scroll.appendChild(d);
    }

    const active  = this._lists.filter(l => !archived.has(l.gid));
    const arcList = this._lists.filter(l =>  archived.has(l.gid));
    const visible = q ? active.filter(l => l.name.toLowerCase().includes(q)) : active;

    const pinnedItems = visible.filter(l => pinned.has(l.gid));

    // 我的清单：本地 OR 云端中属于自己的个人清单（myGid 未知时全归我的清单）
    const myPersonal = visible.filter(l =>
      !pinned.has(l.gid) &&
      (l._source === 'local' ||
       (l.owner_type === 'user' && (!myGid || !l.owner_gid || l.owner_gid === myGid)))
    );
    // 分享给我：云端他人的个人清单，必须知道自己的 gid 才能判断
    const sharedWithMe = visible.filter(l =>
      !pinned.has(l.gid) &&
      myGid &&
      l._source !== 'local' &&
      l.owner_type === 'user' &&
      l.owner_gid && l.owner_gid !== myGid
    );
    // 团队清单
    const team = visible.filter(l =>
      !pinned.has(l.gid) && l.owner_type === 'team' && l._source !== 'local'
    );

    // 已置顶
    if (pinnedItems.length) {
      this._appendSection(scroll, '已置顶', pinnedItems, true, false);
    }

    // 我的清单（含分组）
    if (myPersonal.length) {
      const lbl = document.createElement('div');
      lbl.className = 'ls-section-label';
      lbl.textContent = '我的清单';
      scroll.appendChild(lbl);
      this._renderGroupedLists(scroll, myPersonal);
    } else if (!q && this._lists.length === 0) {
      const emptyEl = document.createElement('div');
      emptyEl.style.cssText = 'font-size:11px;color:var(--text-faint,#6c7086);padding:8px 10px;';
      emptyEl.textContent = '暂无清单，点击上方新建';
      scroll.appendChild(emptyEl);
    }

    // 分享给我（飞书模式）
    if (sharedWithMe.length && isFeishu) {
      const d = document.createElement('div');
      d.className = 'ls-divider';
      d.style.margin = '5px 0 2px';
      scroll.appendChild(d);
      this._appendSection(scroll, '分享给我', sharedWithMe, false, false);
    }

    // 团队清单
    if (team.length && isFeishu) {
      const d = document.createElement('div');
      d.className = 'ls-divider';
      d.style.margin = '5px 0 2px';
      scroll.appendChild(d);
      this._appendSection(scroll, '团队清单', team, false, false);
    }

    // 已归档（折叠区，搜索时隐藏）
    if (arcList.length && !q) {
      const d = document.createElement('div');
      d.className = 'ls-divider';
      d.style.margin = '5px 0 2px';
      scroll.appendChild(d);

      const arcHdr = document.createElement('div');
      arcHdr.className = 'ls-arc-hdr';
      const arrow = document.createElement('span');
      arrow.className = 'ls-arc-arrow' + (this._archivedOpen ? ' open' : '');
      arrow.textContent = '▶';
      const arcLbl = document.createElement('span');
      arcLbl.textContent = `已归档 (${arcList.length})`;
      arcHdr.append(arrow, arcLbl);
      scroll.appendChild(arcHdr);

      const arcBody = document.createElement('div');
      arcBody.style.display = this._archivedOpen ? '' : 'none';
      arcList.forEach(l => arcBody.appendChild(this._makeItem(l.gid, l.name, l.color, l, false, true)));
      scroll.appendChild(arcBody);

      arcHdr.addEventListener('click', () => {
        this._archivedOpen = !this._archivedOpen;
        arrow.classList.toggle('open', this._archivedOpen);
        arcBody.style.display = this._archivedOpen ? '' : 'none';
      });
    }
  }

  // ── 分组渲染（我的清单专用）───────────────────────────────────────────────
  _renderGroupedLists(scroll, lists) {
    const groups    = this._getGroups();
    const collapsed = this._getGrpCollapsed();
    const groupMap  = {};   // { groupName: [list] }
    const ungrouped = [];

    lists.forEach(l => {
      const g = groups[l.gid];
      if (g) { if (!groupMap[g]) groupMap[g] = []; groupMap[g].push(l); }
      else ungrouped.push(l);
    });

    const sortedGroups = Object.keys(groupMap).sort();
    sortedGroups.forEach(gName => {
      const isCollapsed = collapsed.has(gName);

      const grpHdr = document.createElement('div');
      grpHdr.className = 'ls-arc-hdr';
      grpHdr.style.paddingLeft = '10px';
      const arrow = document.createElement('span');
      arrow.className = 'ls-arc-arrow' + (isCollapsed ? '' : ' open');
      arrow.textContent = '▶';
      const nameLbl = document.createElement('span');
      nameLbl.textContent = gName;
      nameLbl.style.cssText = 'font-size:11px;font-weight:600;';
      grpHdr.title = '双击可修改分组名称';
      grpHdr.append(arrow, nameLbl);
      scroll.appendChild(grpHdr);

      const body = document.createElement('div');
      body.style.cssText = `display:${isCollapsed ? 'none' : ''};padding-left:6px;`;
      groupMap[gName].forEach(l => body.appendChild(this._makeItem(l.gid, l.name, l.color, l)));
      scroll.appendChild(body);

      grpHdr.addEventListener('click', () => {
        const c = this._getGrpCollapsed();
        if (c.has(gName)) { c.delete(gName); arrow.classList.add('open'); body.style.display = ''; }
        else              { c.add(gName);    arrow.classList.remove('open'); body.style.display = 'none'; }
        this._setGrpCollapsed(c);
      });

      // 双击改名
      grpHdr.addEventListener('dblclick', e => {
        e.stopPropagation();
        const input = document.createElement('input');
        input.className = 'ls-edit-input';
        input.value = gName;
        input.style.cssText = 'font-size:11px;font-weight:600;width:100%;';
        nameLbl.replaceWith(input);
        input.focus(); input.select();
        const commit = () => {
          const newName = input.value.trim();
          if (newName && newName !== gName) {
            const g = this._getGroups();
            Object.keys(g).forEach(k => { if (g[k] === gName) g[k] = newName; });
            this._setGroups(g);
            // 折叠状态迁移
            const c = this._getGrpCollapsed();
            if (c.has(gName)) { c.delete(gName); c.add(newName); this._setGrpCollapsed(c); }
            this._renderItems();
          } else {
            input.replaceWith(nameLbl);
          }
        };
        input.addEventListener('blur', commit);
        input.addEventListener('keydown', e2 => {
          if (e2.key === 'Enter')  { e2.preventDefault(); input.blur(); }
          if (e2.key === 'Escape') { input.value = gName; input.blur(); }
        });
      });

      // 拖拽放入分组
      grpHdr.addEventListener('dragenter', e => {
        if (!this._draggingGid) return;
        e.preventDefault();
        grpHdr.classList.add('ls-grp-drop-target');
      });
      grpHdr.addEventListener('dragover', e => {
        if (!this._draggingGid) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
      });
      grpHdr.addEventListener('dragleave', e => {
        // 只在鼠标真正离开整个 header 时取消高亮（忽略移到子元素的 leave）
        if (!grpHdr.contains(e.relatedTarget)) {
          grpHdr.classList.remove('ls-grp-drop-target');
        }
      });
      grpHdr.addEventListener('drop', e => {
        e.preventDefault();
        grpHdr.classList.remove('ls-grp-drop-target');
        const dragging = this._draggingGid;
        if (!dragging) return;
        const g = this._getGroups();
        g[dragging] = gName;
        this._setGroups(g);
        this._renderItems();
      });
    });

    ungrouped.forEach(l => scroll.appendChild(this._makeItem(l.gid, l.name, l.color, l)));
  }

  _appendSection(scroll, label, items, isPinned, isArchived) {
    const lbl = document.createElement('div');
    lbl.className = 'ls-section-label';
    lbl.textContent = label;
    scroll.appendChild(lbl);
    items.forEach(l => scroll.appendChild(this._makeItem(l.gid, l.name, l.color, l, isPinned, isArchived)));
  }

  // ── 新建清单 Popover ──────────────────────────────────────────────────────
  async _openCreatePopover(anchorEl) {
    document.querySelector('.ls-create-pop')?.remove();

    const COLORS = ['#5b8dee','#89b4fa','#a6e3a1','#f38ba8','#fab387','#f9e2af','#cba6f7','#74c7ec'];
    let selectedColor = COLORS[0];

    const pop = document.createElement('div');
    pop.className = 'ls-create-pop';
    pop.innerHTML = `
      <div class="ls-cp-title">新建清单</div>
      <div>
        <label class="ls-cp-label">清单名称 <span style="color:#ef4444">*</span></label>
        <input class="ls-cp-input" id="lsCpName" type="text" placeholder="输入清单名称…" autocomplete="off">
      </div>
      <div>
        <label class="ls-cp-label">颜色</label>
        <div class="ls-cp-colors" id="lsCpColors">
          ${COLORS.map((c, i) => `<span class="ls-cp-swatch${i === 0 ? ' selected' : ''}" data-color="${c}" style="background:${c}"></span>`).join('')}
        </div>
      </div>
      <div>
        <label class="ls-cp-label">可见范围</label>
        <div id="lsCpVisMount"></div>
      </div>
      <div class="ls-cp-error" id="lsCpError" style="display:none"></div>
      <div class="ls-cp-footer">
        <button type="button" class="ls-cp-btn-cancel" id="lsCpCancel">取消</button>
        <button type="button" class="ls-cp-btn-ok" id="lsCpOk">创建</button>
      </div>
    `;
    document.body.appendChild(pop);

    // Position near anchor button
    const rect = anchorEl.getBoundingClientRect();
    const winW  = window.innerWidth;
    const winH  = window.innerHeight;
    let left = rect.left;
    let top  = rect.bottom + 6;
    if (left + 260 > winW - 10) left = winW - 270;
    if (top  + 380 > winH - 10) top  = rect.top - 386;
    if (top < 10) top = 10;
    pop.style.left = `${Math.max(10, left)}px`;
    pop.style.top  = `${top}px`;

    const nameInput = pop.querySelector('#lsCpName');
    const errEl     = pop.querySelector('#lsCpError');
    const visMount  = pop.querySelector('#lsCpVisMount');

    // Color swatches
    pop.querySelector('#lsCpColors').addEventListener('click', e => {
      const sw = e.target.closest('.ls-cp-swatch');
      if (!sw) return;
      pop.querySelectorAll('.ls-cp-swatch').forEach(s => s.classList.remove('selected'));
      sw.classList.add('selected');
      selectedColor = sw.dataset.color;
    });

    // VisibilitySelector
    if (window.VisibilitySelector) {
      await VisibilitySelector.renderWidget(visMount, { initialVisibility: 'team' });
    }

    const _close = () => {
      pop.remove();
      document.removeEventListener('click', _outsideClick, true);
      document.removeEventListener('keydown', _keydown);
    };

    const _submit = async () => {
      const name = nameInput.value.trim();
      if (!name) { errEl.textContent = '请输入清单名称'; errEl.style.display = ''; nameInput.focus(); return; }
      const visVal = window.VisibilitySelector ? VisibilitySelector.getValue(visMount) : { visibility: 'team', shared_team_gid: null, shared_project_gid: null };
      if (visVal.visibility === 'project' && !visVal.shared_project_gid) {
        errEl.textContent = '请选择关联项目'; errEl.style.display = ''; return;
      }
      errEl.style.display = 'none';
      const okBtn = pop.querySelector('#lsCpOk');
      okBtn.disabled = true;
      okBtn.textContent = '创建中…';
      try {
        await this._doCreateList(name, selectedColor, visVal.visibility, visVal.shared_project_gid || null, visVal.shared_team_gid || null);
        _close();
      } catch (e) {
        errEl.textContent = '创建失败：' + (e?.message || e);
        errEl.style.display = '';
        okBtn.disabled = false;
        okBtn.textContent = '创建';
      }
    };

    pop.querySelector('#lsCpCancel').addEventListener('click', _close);
    pop.querySelector('#lsCpOk').addEventListener('click', _submit);

    const _outsideClick = (e) => { if (!pop.contains(e.target) && e.target !== anchorEl) _close(); };
    const _keydown = (e) => {
      if (e.key === 'Escape') { e.stopPropagation(); _close(); }
      if (e.key === 'Enter' && e.target === nameInput) { e.preventDefault(); _submit(); }
    };
    setTimeout(() => {
      document.addEventListener('click', _outsideClick, true);
      document.addEventListener('keydown', _keydown);
    }, 0);
    requestAnimationFrame(() => nameInput.focus());
  }

  async _doCreateList(name, color = '#5b8dee', visibility = 'team', projectGid = null, sharedTeamGid = null) {
    const uid = window.top?._authUser?.gid || window.parent?._authUser?.gid || '';
    const body = { name, color, storage_scope: 'cloud', owner_type: 'user',
                   item_type: this._itemType, visibility, owner_gid: uid };
    if (projectGid)    body.project_gid     = projectGid;
    if (sharedTeamGid) body.shared_team_gid = sharedTeamGid;
    const res = await this._cf('/api/lists', { method: 'POST', body: JSON.stringify(body) });
    const newGid = res?.data?.gid || null;
    await this._loadLists();
    this._renderItems();
    if (newGid) this._select(newGid);
  }

  // ── 列表项 ────────────────────────────────────────────────────────────────
  _makeItem(gid, name, color, listObj, isPinned = false, isArchived = false) {
    const item = document.createElement('div');
    item.className = 'ls-item' + (this._selected === gid ? ' active' : '');
    item.dataset.gid = gid ?? '';

    const dot = document.createElement('div');
    dot.className = 'ls-dot';
    dot.style.background = color || '#6c7086';

    // 可见范围徽标
    if (listObj && window.VisibilitySelector) {
      const badgeWrap = document.createElement('span');
      badgeWrap.innerHTML = VisibilitySelector.renderBadge(listObj.visibility || 'team');
      item.appendChild(badgeWrap.firstChild || badgeWrap);
    }

    const lbl = document.createElement('div');
    lbl.className = 'ls-name';
    lbl.textContent = name;

    item.append(dot, lbl);

    // 本地清单显示 "本地" 小标签
    if (listObj && listObj.storage_scope === 'local') {
      const badge = document.createElement('span');
      badge.className = 'ls-scope-badge local';
      badge.textContent = '本地';
      item.appendChild(badge);
    }

    // 额外 HTML（由调用方注入，如 BOP 成熟度徽章）
    if (this._extraItemHtml && listObj) {
      item.insertAdjacentHTML('beforeend', this._extraItemHtml(listObj));
    }

    if (isPinned) {
      const pi = document.createElement('span');
      pi.className = 'ls-pin-icon';
      // Bootstrap Icons pin-angle style
      pi.innerHTML = `<svg width="9" height="9" viewBox="0 0 16 16" fill="currentColor"><path d="M9.828.722a.5.5 0 0 1 .354.146l4.95 4.95a.5.5 0 0 1 0 .707c-.48.48-1.072.588-1.503.588-.177 0-.335-.018-.46-.039l-3.134 3.134a5.927 5.927 0 0 1 .16 1.013c.046.702-.032 1.687-.72 2.375a.5.5 0 0 1-.707 0l-2.829-2.828-3.182 3.182c-.195.195-1.219.902-1.414.707-.195-.195.512-1.22.707-1.414l3.182-3.182-2.828-2.829a.5.5 0 0 1 0-.707c.688-.688 1.673-.767 2.375-.72a5.922 5.922 0 0 1 1.013.16l3.134-3.133a2.772 2.772 0 0 1-.04-.461c0-.43.108-1.022.589-1.503a.5.5 0 0 1 .353-.146z"/></svg>`;
      item.appendChild(pi);
    }

    item.addEventListener('click', () => this._select(gid));

    // 拖拽到分组（本地和云端清单均支持）
    if (listObj && !isArchived) {
      item.draggable = true;
      item.addEventListener('dragstart', (e) => {
        this._draggingGid = gid;
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', gid);   // Chromium 必须调用 setData 才会触发 drop
        setTimeout(() => item.classList.add('ls-dragging'), 0);
      });
      item.addEventListener('dragend', () => {
        this._draggingGid = null;
        item.classList.remove('ls-dragging');
      });
    }

    if (listObj) {
      if (!this._disableInlineRename) {
        item.addEventListener('dblclick', e => { e.stopPropagation(); this._inlineRename(item, lbl, listObj); });
      }
      item.addEventListener('contextmenu', e => { e.preventDefault(); this._showCtxMenu(e.clientX, e.clientY, listObj, isArchived); });
    }

    return item;
  }

  _select(gid) {
    this._selected = gid;
    this._el.querySelectorAll('.ls-item').forEach(el =>
      el.classList.toggle('active', el.dataset.gid === (gid ?? ''))
    );
    this._onSelect(gid);
  }

  // ── 内联改名 ──────────────────────────────────────────────────────────────
  _inlineRename(itemEl, lblEl, listObj) {
    if (this._editingGid === listObj.gid) return;
    this._editingGid = listObj.gid;
    const input = document.createElement('input');
    input.className = 'ls-edit-input';
    input.value = listObj.name;
    lblEl.replaceWith(input);
    input.focus(); input.select();

    const commit = async () => {
      this._editingGid = null;
      const n = input.value.trim();
      if (n && n !== listObj.name) {
        await this._updateList(listObj.gid, { name: n });
      } else {
        input.replaceWith(lblEl);
      }
    };
    input.addEventListener('blur', commit);
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter')  { e.preventDefault(); commit(); }
      if (e.key === 'Escape') { this._editingGid = null; input.replaceWith(lblEl); }
    });
  }

  // ── 右键菜单 ──────────────────────────────────────────────────────────────
  _showCtxMenu(x, y, listObj, isArchived) {
    // 外部完全接管右键菜单
    if (this._onContextMenu) {
      this._onContextMenu(x, y, listObj, isArchived);
      return;
    }
    document.querySelectorAll('.ls-ctx-menu').forEach(m => m.remove());
    const menu = document.createElement('div');
    menu.className = 'ls-ctx-menu';
    const pinned = this._getPinned();
    const isOwnerOrAdmin = this._isOwnerOrAdmin(listObj);
    const isCloud = listObj._source !== 'local';

    const add = (text, cls, fn) => {
      const el = document.createElement('div');
      el.className = 'ls-ctx-item' + (cls ? ` ${cls}` : '');
      el.textContent = text;
      el.addEventListener('click', () => { menu.remove(); fn(); });
      menu.appendChild(el);
    };
    const addSep = () => {
      const sep = document.createElement('div');
      sep.className = 'ls-ctx-sep';
      menu.appendChild(sep);
    };

    if (!isArchived) {
      add('改名', '', () => {
        const itemEl = this._scroll.querySelector(`[data-gid="${listObj.gid}"]`);
        if (itemEl) this._inlineRename(itemEl, itemEl.querySelector('.ls-name'), listObj);
      });
      add(pinned.has(listObj.gid) ? '取消置顶' : '置顶', '', () => this._togglePin(listObj.gid));
      // 只允许本地→云端迁移；云端清单不允许迁移到本地
      if (listObj._source === 'local') {
        add('迁移到云端…', '', () => this._migrateListScope(listObj, 'cloud'));
      }
      add('归档', '', () => this._toggleArchive(listObj.gid));

      // 分组（所有清单均可分组）
      add('设置分组…', '', () => this._setGroupFor(listObj));

      // owner 命令：云端清单才有意义
      if (isCloud && isOwnerOrAdmin) {
        addSep();
        add('转让 Owner…', '', () => this._transferOwner(listObj));
        add('设置可见范围…', '', () => this._setVisibility(listObj));
        if (typeof window.openListShareDialog === 'function') {
          add('分享设置…', '', () => window.openListShareDialog(listObj.gid, listObj.name));
        }
      }

      // 绑定项目：task/issue 云端清单可关联项目
      if (isCloud && (listObj.item_type === 'task' || listObj.item_type === 'issue')) {
        addSep();
        add('绑定项目…', '', () => this._bindProject(listObj));
      }
    } else {
      add('恢复', '', () => this._toggleArchive(listObj.gid));
    }

    // 删除：本地清单不做 owner 检查（本地单用户）；云端需是 owner 或 admin
    if (!isCloud || isOwnerOrAdmin) {
      addSep();
      add('删除', 'danger', async () => {
        if (!confirm(`确认删除清单"${listObj.name}"？清单内条目将变为未归类。`)) return;
        await this._deleteList(listObj.gid);
      });
    }

    menu.style.left = x + 'px';
    menu.style.top  = y + 'px';
    document.body.appendChild(menu);

    const close = e => {
      if (!menu.contains(e.target)) { menu.remove(); document.removeEventListener('click', close); }
    };
    setTimeout(() => document.addEventListener('click', close), 10);
  }

  /** 判断当前用户是否为清单 owner 或 admin */
  _isOwnerOrAdmin(listObj) {
    const myGid  = window._authUser?.gid  || window.parent?._authUser?.gid  || 'local';
    if (!myGid) return true;
    const isOwner = listObj.owner_gid === myGid;
    const _au  = window._authUser || window.parent?._authUser;
    const role    = _au?.system_role || _au?.org_role || _au?.role || '';
    const isAdmin = ['super_admin', 'team_admin'].includes(role);
    return isOwner || isAdmin;
  }

  /** 绑定项目：从 /api/projects 选择一个项目关联到清单 */
  async _bindProject(listObj) {
    document.querySelectorAll('.ls-bind-proj-modal').forEach(m => m.remove());

    // 加载项目列表
    let projects = [];
    try {
      const res = await this._cf('/api/projects');
      projects = res?.data || res || [];
    } catch (e) {
      alert('加载项目列表失败：' + e.message);
      return;
    }

    const overlay = document.createElement('div');
    overlay.className = 'ls-bind-proj-modal';
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:10000;display:flex;align-items:center;justify-content:center;';

    const currentProjGid = listObj.project_gid || '';
    const projOptions = projects.map(p =>
      `<option value="${p.gid}"${p.gid === currentProjGid ? ' selected' : ''}>${p.name || p.project_code || p.gid}</option>`
    ).join('');

    overlay.innerHTML = `
      <div style="background:var(--bg-secondary);border:1px solid var(--border-default);border-radius:8px;padding:20px;min-width:320px;max-width:420px;">
        <div style="font-size:13px;font-weight:600;color:var(--text-normal);margin-bottom:14px;">绑定项目</div>
        <div style="font-size:12px;color:var(--text-muted);margin-bottom:8px;">清单：${listObj.name}</div>
        <select id="lsBpSelect" style="width:100%;padding:7px 10px;background:var(--bg-primary);border:1px solid var(--border-default);border-radius:5px;color:var(--text-normal);font-size:13px;outline:none;margin-bottom:14px;">
          <option value="">— 不绑定 —</option>
          ${projOptions}
        </select>
        <div style="display:flex;gap:8px;justify-content:flex-end;">
          <button id="lsBpCancel" style="padding:5px 14px;background:transparent;border:1px solid var(--border-default);border-radius:5px;color:var(--text-muted);font-size:12px;cursor:pointer;">取消</button>
          <button id="lsBpOk" style="padding:5px 14px;background:var(--accent-color,#89b4fa);border:none;border-radius:5px;color:#1e1e2e;font-size:12px;font-weight:600;cursor:pointer;">确认</button>
        </div>
      </div>`;

    document.body.appendChild(overlay);
    overlay.querySelector('#lsBpCancel').addEventListener('click', () => overlay.remove());
    overlay.querySelector('#lsBpOk').addEventListener('click', async () => {
      const projGid = overlay.querySelector('#lsBpSelect').value || null;
      overlay.remove();
      await this._updateList(listObj.gid, { project_gid: projGid });
    });
  }

  /** 转让 Owner 弹层 */
  async _transferOwner(listObj) {
    document.querySelectorAll('.ls-owner-modal').forEach(m => m.remove());
    const overlay = document.createElement('div');
    overlay.className = 'ls-owner-modal';
    overlay.innerHTML = `
      <div class="ls-om-box">
        <div class="ls-om-title">转让清单 Owner</div>
        <div class="ls-om-sub">清单：${listObj.name}</div>
        <input class="ls-om-input" id="lomSearch" placeholder="搜索用户姓名…" autocomplete="off">
        <div class="ls-om-list" id="lomList"></div>
        <div class="ls-om-footer">
          <button class="ls-om-btn" id="lomCancel">取消</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);

    const input   = overlay.querySelector('#lomSearch');
    const listEl  = overlay.querySelector('#lomList');
    let _selGid = '', _selName = '';

    const renderUsers = (users) => {
      listEl.innerHTML = '';
      if (!users.length) {
        listEl.innerHTML = '<div class="ls-om-empty">无匹配用户</div>';
        return;
      }
      users.forEach(u => {
        const row = document.createElement('div');
        row.className = 'ls-om-user' + (u.gid === _selGid ? ' selected' : '');
        row.innerHTML = `<span class="ls-om-avatar">${(u.name||'?')[0]}</span>
          <span class="ls-om-uname">${u.name}</span>
          <span class="ls-om-uemail">${u.email||''}</span>`;
        row.addEventListener('click', async () => {
          _selGid = u.gid; _selName = u.name;
          if (!confirm(`确认将"${listObj.name}"的 Owner 转让给 ${_selName}？`)) return;
          overlay.remove();
          await this._updateList(listObj.gid, { owner_gid: _selGid });
        });
        listEl.appendChild(row);
      });
    };

    let _timer;
    input.addEventListener('input', () => {
      clearTimeout(_timer);
      _timer = setTimeout(async () => {
        const q = input.value.trim();
        try {
          const res = await this._cf(`/api/users/search?q=${encodeURIComponent(q)}&limit=10`);
          renderUsers(res?.data || []);
        } catch { listEl.innerHTML = '<div class="ls-om-empty">搜索失败</div>'; }
      }, 250);
    });

    overlay.querySelector('#lomCancel').addEventListener('click', () => overlay.remove());
    overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });
    input.focus();

    // 初始加载空搜索
    try {
      const res = await this._cf('/api/users/search?q=&limit=20');
      renderUsers(res?.data || []);
    } catch {}
  }

  /** 设置可见范围弹层 */
  async _setVisibility(listObj) {
    if (window.VisibilitySelector) {
      await VisibilitySelector.showDialog(listObj, async (val) => {
        await this._updateList(listObj.gid, {
          visibility:         val.visibility,
          shared_team_gid:    val.shared_team_gid    || null,
          project_gid:        val.shared_project_gid || listObj.project_gid || null,
        });
        listObj.visibility      = val.visibility;
        listObj.shared_team_gid = val.shared_team_gid;
        this._renderItems();
      });
      return;
    }
    // 降级：旧版简单弹层
    document.querySelectorAll('.ls-vis-pop').forEach(m => m.remove());
    const OPTS = [
      { v: 'private',  label: '私人',   desc: '只有你能看到此清单' },
      { v: 'project',  label: '关联项目', desc: '项目成员均可查看（需已关联项目）', needProject: true },
      { v: 'team',     label: '我的团队', desc: '团队成员均可查看' },
      { v: 'public',   label: '全公司',  desc: '所有登录用户可见' },
    ];
    const pop = document.createElement('div');
    pop.className = 'ls-vis-pop';
    OPTS.forEach(opt => {
      if (opt.needProject && !listObj.project_gid) return;
      const row = document.createElement('div');
      const isCur = (listObj.visibility || 'team') === opt.v;
      row.className = 'ls-vis-item' + (isCur ? ' active' : '');
      row.innerHTML = `<div class="ls-vis-label">${opt.label}</div>
        <div class="ls-vis-desc">${opt.desc}</div>`;
      row.addEventListener('click', async () => {
        pop.remove();
        if (!isCur) await this._updateList(listObj.gid, { visibility: opt.v });
      });
      pop.appendChild(row);
    });
    document.body.appendChild(pop);
    pop.style.position = 'fixed';
    pop.style.left = '50%';
    pop.style.top  = '50%';
    pop.style.transform = 'translate(-50%,-50%)';
    const close = e => {
      if (!pop.contains(e.target)) { pop.remove(); document.removeEventListener('mousedown', close); }
    };
    setTimeout(() => document.addEventListener('mousedown', close), 10);
  }

  // ── 置顶 / 归档 ───────────────────────────────────────────────────────────
  _togglePin(gid) {
    const s = this._getPinned();
    s.has(gid) ? s.delete(gid) : s.add(gid);
    this._setPinned(s);
    this._renderItems();
  }

  _toggleArchive(gid) {
    const s = this._getArchived();
    const wasArchived = s.has(gid);
    wasArchived ? s.delete(gid) : s.add(gid);
    this._setArchived(s);
    // 归档时若正好选中该清单，切换到全部
    if (!wasArchived && this._selected === gid) {
      this._selected = null;
      this._onSelect(null);
    }
    this._renderItems();
  }

  async _updateList(gid, fields) {
    try {
      await this._cf(`/api/lists/${gid}`, {
        method: 'PATCH',
        body: JSON.stringify(fields),
      });
    } catch (e) { console.warn('[ListSidebar] 更新清单失败:', e); }
    await this._loadLists();
    this._renderItems();
    if (this._selected) this._select(this._selected);
  }

  async _migrateListScope(listObj, newScope) {
    // 纯云端模式：无本地存储，迁移功能不可用
    alert('当前为云端模式，清单迁移功能不适用。');
  }

  async _deleteList(gid) {
    try {
      await this._cf(`/api/lists/${gid}`, { method: 'DELETE' });
    } catch (e) { console.warn('[ListSidebar] 删除清单失败:', e); }
    const p = this._getPinned();   p.delete(gid); this._setPinned(p);
    const a = this._getArchived(); a.delete(gid); this._setArchived(a);
    if (this._selected === gid) { this._selected = null; this._onSelect(null); }
    await this._loadLists();
    this._renderItems();
  }

  /** 设置/切换列表所属分组 */
  _setGroupFor(listObj) {
    document.querySelectorAll('.ls-grp-pop').forEach(m => m.remove());
    const groups   = this._getGroups();
    const existing = [...new Set(Object.values(groups))].sort();
    const curGroup = groups[listObj.gid] || '';

    const pop = document.createElement('div');
    pop.className = 'ls-vis-pop ls-grp-pop';

    const hdr = document.createElement('div');
    hdr.style.cssText = 'padding:6px 14px 4px;font-size:11px;color:var(--text-faint,#6c7086);';
    hdr.textContent = '选择分组';
    pop.appendChild(hdr);

    if (!existing.length) {
      const emptyHint = document.createElement('div');
      emptyHint.style.cssText = 'padding:4px 14px 2px;font-size:11px;color:var(--text-faint,#6c7086);';
      emptyHint.textContent = '暂无分组，点击下方新建';
      pop.appendChild(emptyHint);
    }

    existing.forEach(gName => {
      const row = document.createElement('div');
      row.className = 'ls-vis-item' + (curGroup === gName ? ' active' : '');
      row.innerHTML = `<div class="ls-vis-label">${gName}</div>`;
      row.addEventListener('click', () => {
        pop.remove();
        const g = this._getGroups();
        if (curGroup === gName) delete g[listObj.gid]; else g[listObj.gid] = gName;
        this._setGroups(g); this._renderItems();
      });
      pop.appendChild(row);
    });

    if (curGroup) {
      const sep = document.createElement('div'); sep.className = 'ls-ctx-sep'; pop.appendChild(sep);
      const removeRow = document.createElement('div');
      removeRow.className = 'ls-vis-item';
      removeRow.innerHTML = '<div class="ls-vis-label" style="color:var(--text-faint,#6c7086)">移出分组</div>';
      removeRow.addEventListener('click', () => {
        pop.remove();
        const g = this._getGroups(); delete g[listObj.gid];
        this._setGroups(g); this._renderItems();
      });
      pop.appendChild(removeRow);
    }

    // 新建分组（名称创建后不可修改）
    const sep2 = document.createElement('div'); sep2.className = 'ls-ctx-sep'; pop.appendChild(sep2);
    const newGrpRow = document.createElement('div');
    newGrpRow.className = 'ls-vis-item';
    newGrpRow.innerHTML = `<div class="ls-vis-label" style="color:var(--color-accent,#89b4fa)">
      <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="margin-right:4px;vertical-align:-1px"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>新建分组…</div>`;
    pop.appendChild(newGrpRow);

    // 点击"新建分组"后展开输入行（替换该行）
    newGrpRow.addEventListener('click', () => {
      newGrpRow.innerHTML = '';
      const inputWrap = document.createElement('div');
      inputWrap.style.cssText = 'display:flex;gap:4px;width:100%;padding:0 4px;box-sizing:border-box;';
      const inp = document.createElement('input');
      inp.style.cssText = 'flex:1;padding:3px 6px;font-size:12px;background:var(--bg-secondary,#181825);border:1px solid var(--color-accent,#89b4fa);border-radius:4px;color:var(--text-normal,#cdd6f4);outline:none;min-width:0;';
      inp.placeholder = '分组名称（不可修改）…';
      const okBtn = document.createElement('button');
      okBtn.textContent = '确定';
      okBtn.style.cssText = 'padding:2px 8px;font-size:11px;border-radius:3px;border:none;background:var(--color-accent,#89b4fa);color:var(--bg-primary,#1e1e2e);cursor:pointer;flex-shrink:0;';
      const commit = () => {
        const name = inp.value.trim();
        if (!name) return;
        pop.remove();
        const g = this._getGroups(); g[listObj.gid] = name;
        this._setGroups(g); this._renderItems();
      };
      okBtn.addEventListener('click', commit);
      inp.addEventListener('keydown', e => {
        if (e.key === 'Enter')  commit();
        if (e.key === 'Escape') pop.remove();
      });
      inputWrap.append(inp, okBtn);
      newGrpRow.appendChild(inputWrap);
      requestAnimationFrame(() => inp.focus());
    });

    document.body.appendChild(pop);
    pop.style.cssText += ';position:fixed;left:50%;top:50%;transform:translate(-50%,-50%);';
    const close = e => { if (!pop.contains(e.target)) { pop.remove(); document.removeEventListener('mousedown', close); } };
    setTimeout(() => document.addEventListener('mousedown', close), 10);
  }

  /** 外部可调用：刷新条目计数 */
  updateCounts(countMap) {
    Object.entries(countMap).forEach(([gid, count]) => {
      const item = this._el.querySelector(`[data-gid="${gid}"]`);
      if (!item) return;
      let badge = item.querySelector('.ls-count');
      if (!badge) { badge = document.createElement('div'); badge.className = 'ls-count'; item.appendChild(badge); }
      badge.textContent = count > 0 ? count : '';
    });
  }
}

window.ListSidebar = ListSidebar;
/** 虚拟 GID：代表"无清单条目"视图，选中时仅显示 list_gid 为空的条目 */
ListSidebar.NO_LIST = '__no_list__';

