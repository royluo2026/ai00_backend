/**
 * web/core/global_search.js
 * ──────────────────────────
 * 全局快速搜索叠加层（Ctrl+O）
 * 支持跨数据源：飞书联系人/群聊/文档、BOP 工艺节点、任务/问题、知识库/规则
 */
const GlobalSearch = (() => {
  // ── 分类定义 ─────────────────────────────────────────────────────────────
  const CATEGORIES = [
    { id: 'all',    label: '全部',  badgeClass: 'gs-badge-all' },
    { id: 'feishu', label: '飞书',  badgeClass: 'gs-badge-feishu' },
    { id: 'bop',    label: 'BOP',   badgeClass: 'gs-badge-bop' },
    { id: 'tasks',  label: '任务',  badgeClass: 'gs-badge-tasks' },
    { id: 'know',   label: '知识库', badgeClass: 'gs-badge-know' },
    { id: 'cal',    label: '日程',  badgeClass: 'gs-badge-cal' },
  ];

  // ── 状态 ──────────────────────────────────────────────────────────────────
  let _activeCategory  = 'all';
  let _manualLock      = false;
  let _query           = '';
  let _debounceTimer   = null;
  let _abortCtrl       = null;
  let _results         = [];   // [{category, items:[...]}]
  let _flatItems       = [];   // 扁平列表，用于键盘导航
  let _selectedIdx     = -1;
  let _tabsVisible     = false;
  let _searchToken     = 0;    // 渐进渲染防竞态

  // ── DOM 引用（init 后赋值）────────────────────────────────────────────────
  let _overlay, _panel, _input, _badge, _tabs, _resultsEl, _footer;

  // ── 分类自动识别 ──────────────────────────────────────────────────────────
  function _detectCategory(q) {
    if (!q || q.length < 2) return 'all';
    if (/^@/.test(q)) return 'feishu';  // 仅 @ 前缀明确触发飞书联系人
    return 'all';  // 其余情况始终全局搜索，避免文档标题含工艺/任务等词被错误分流
  }

  function _setCategory(id, isManual = false) {
    _activeCategory = id;
    if (isManual) _manualLock = true;

    const cat = CATEGORIES.find(c => c.id === id) || CATEGORIES[0];
    _badge.textContent = cat.label + ' ▾';
    _badge.className   = 'gs-badge ' + cat.badgeClass;

    // 更新 Tab 高亮
    _tabs.querySelectorAll('.gs-tab').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.cat === id);
    });
  }

  // ── 搜索各数据源 ───────────────────────────────────────────────────────────
  async function _searchFeishu(q) {
    const authMode = window._authMode || 'none';
    if (authMode !== 'feishu') return [];
    try {
      const [usersRes, chatsRes, docsRes] = await Promise.allSettled([
        window._cloudFetch(`/feishu/search/users?q=${encodeURIComponent(q)}&limit=5`),
        window._cloudFetch(`/feishu/search/chats?q=${encodeURIComponent(q)}&limit=5`),
        window._cloudFetch(`/feishu/search/docs?q=${encodeURIComponent(q)}&limit=4`),
      ]);
      const items = [];
      if (usersRes.status === 'fulfilled' && usersRes.value?.data) {
        for (const u of usersRes.value.data) {
          items.push({ _cat: 'feishu', _subtype: 'user', ...u });
        }
      }
      if (chatsRes.status === 'fulfilled' && chatsRes.value?.data) {
        for (const c of chatsRes.value.data) {
          items.push({ _cat: 'feishu', _subtype: 'chat', ...c });
        }
      }
      if (docsRes.status === 'fulfilled' && docsRes.value?.data) {
        for (const d of docsRes.value.data) {
          items.push({ _cat: 'feishu', _subtype: 'doc', ...d });
        }
      }
      return items;
    } catch (_) {
      return [];
    }
  }

  async function _searchBop(q) {
    try {
      const res = await window._cloudFetch(`/api/bop/entries/search?q=${encodeURIComponent(q)}&limit=8`);
      return (res?.data || []).map(r => ({ _cat: 'bop', ...r }));
    } catch (_) {
      return [];
    }
  }

  async function _searchTasks(q) {
    try {
      const [tasksRes, issuesRes] = await Promise.allSettled([
        window._cloudFetch(`/api/tasks?q=${encodeURIComponent(q)}&page_size=5`),
        window._cloudFetch(`/api/issues?q=${encodeURIComponent(q)}&page_size=5`),
      ]);
      const items = [];
      if (tasksRes.status === 'fulfilled' && tasksRes.value?.data) {
        for (const t of tasksRes.value.data) items.push({ _cat: 'tasks', _subtype: 'task', ...t });
      }
      if (issuesRes.status === 'fulfilled' && issuesRes.value?.data) {
        for (const t of issuesRes.value.data) items.push({ _cat: 'tasks', _subtype: 'issue', ...t });
      }
      return items;
    } catch (_) {
      return [];
    }
  }

  async function _searchKnow(q) {
    try {
      const [knowRes, rulesRes] = await Promise.allSettled([
        window._cloudFetch(`/api/knowledge_hub/items?q=${encodeURIComponent(q)}&limit=5`),
        window._cloudFetch(`/api/rules?q=${encodeURIComponent(q)}&limit=5`),
      ]);
      const items = [];
      if (knowRes.status === 'fulfilled' && Array.isArray(knowRes.value)) {
        for (const k of knowRes.value) items.push({ _cat: 'know', _subtype: 'knowledge', ...k });
      }
      if (rulesRes.status === 'fulfilled' && rulesRes.value?.data) {
        for (const r of rulesRes.value.data) items.push({ _cat: 'know', _subtype: 'rule', ...r });
      }
      return items;
    } catch (_) {
      return [];
    }
  }

  async function _searchCal(q) {
    const authMode = window._authMode || 'none';
    if (authMode !== 'feishu') return [];
    try {
      const [evRes, mtRes] = await Promise.allSettled([
        window._cloudFetch(`/feishu/search/events?q=${encodeURIComponent(q)}&limit=5`),
        window._cloudFetch(`/feishu/search/meetings?q=${encodeURIComponent(q)}&limit=4`),
      ]);
      const items = [];
      if (evRes.status === 'fulfilled' && evRes.value?.data) {
        for (const e of evRes.value.data) items.push({ _cat: 'cal', _subtype: 'event', ...e });
      }
      if (mtRes.status === 'fulfilled' && mtRes.value?.data) {
        for (const m of mtRes.value.data) items.push({ _cat: 'cal', _subtype: 'meeting', ...m });
      }
      return items;
    } catch (_) {
      return [];
    }
  }

  async function _doSearch(q, cat) {
    if (_abortCtrl) { try { _abortCtrl.abort(); } catch (_) {} }
    _abortCtrl = new AbortController();

    const token = ++_searchToken;
    _showLoading();

    const sections = [];
    function _addGroup(label, items) {
      if (_searchToken !== token || !items.length) return;
      sections.push({ label, items });
      _render([...sections]);
    }

    const enc = encodeURIComponent(q);
    const authOk = (window._authMode || 'none') === 'feishu';

    // 根据分类决定发哪些请求，每条请求独立 .then() → 谁快谁先显示
    const all = [];

    if (cat === 'all' || cat === 'feishu') {
      if (authOk) {
        all.push(
          window._cloudFetch(`/feishu/search/users?q=${enc}&limit=5`).then(r =>
            _addGroup('飞书联系人', (r?.data || []).map(u => ({ _cat:'feishu', _subtype:'user', ...u })))
          ).catch(() => {}),
          window._cloudFetch(`/feishu/search/chats?q=${enc}&limit=5`).then(r =>
            _addGroup('飞书群聊', (r?.data || []).map(c => ({ _cat:'feishu', _subtype:'chat', ...c })))
          ).catch(() => {}),
          window._cloudFetch(`/feishu/search/docs?q=${enc}&limit=4`).then(r =>
            _addGroup('飞书文档', (r?.data || []).map(d => ({ _cat:'feishu', _subtype:'doc', ...d })))
          ).catch(() => {}),
        );
      }
    }
    if (cat === 'all') {
      all.push(
        window._cloudFetch(`/api/lists?q=${enc}`).then(r =>
          _addGroup('清单', (r?.data || []).map(l => ({ _cat:'lists', _subtype:'list', ...l })))
        ).catch(() => {}),
      );
    }
    if (cat === 'all' || cat === 'bop') {
      all.push(
        window._cloudFetch(`/api/bop/entries/search?q=${enc}&limit=8`).then(r =>
          _addGroup('BOP 工艺节点', (r?.data || []).map(b => ({ _cat:'bop', ...b })))
        ).catch(() => {}),
      );
    }
    if (cat === 'all' || cat === 'tasks') {
      all.push(
        window._cloudFetch(`/api/tasks?q=${enc}&page_size=5`).then(r =>
          _addGroup('任务', (r?.data || []).map(t => ({ _cat:'tasks', _subtype:'task', ...t })))
        ).catch(() => {}),
        window._cloudFetch(`/api/issues?q=${enc}&page_size=5`).then(r =>
          _addGroup('问题', (r?.data || []).map(i => ({ _cat:'tasks', _subtype:'issue', ...i })))
        ).catch(() => {}),
      );
    }
    if (cat === 'all' || cat === 'know') {
      all.push(
        window._cloudFetch(`/api/knowledge_hub/items?q=${enc}&limit=5`).then(r =>
          _addGroup('知识库', (Array.isArray(r) ? r : []).map(k => ({ _cat:'know', _subtype:'knowledge', ...k })))
        ).catch(() => {}),
        window._cloudFetch(`/api/rules?q=${enc}&limit=5`).then(r =>
          _addGroup('规则', (r?.data || []).map(r => ({ _cat:'know', _subtype:'rule', ...r })))
        ).catch(() => {}),
      );
    }
    if (cat === 'all' || cat === 'cal') {
      if (authOk) {
        all.push(
          window._cloudFetch(`/feishu/search/events?q=${enc}&limit=5`).then(r =>
            _addGroup('日程', (r?.data || []).map(e => ({ _cat:'cal', _subtype:'event', ...e })))
          ).catch(() => {}),
          window._cloudFetch(`/feishu/search/meetings?q=${enc}&limit=4`).then(r =>
            _addGroup('会议记录', (r?.data || []).map(m => ({ _cat:'cal', _subtype:'meeting', ...m })))
          ).catch(() => {}),
        );
      }
    }

    await Promise.allSettled(all);
    if (_searchToken === token && !sections.length) _render([]);
  }

  // ── 渲染 ──────────────────────────────────────────────────────────────────
  function _itemIcon(item) {
    if (item._cat === 'feishu') {
      if (item._subtype === 'user') {
        return item.avatar_url
          ? `<img class="gs-avatar" src="${_esc(item.avatar_url)}" alt="">`
          : `<div class="gs-icon">👤</div>`;
      }
      if (item._subtype === 'chat') return `<div class="gs-icon">💬</div>`;
      return `<div class="gs-icon">📄</div>`;
    }
    if (item._cat === 'lists') return `<div class="gs-icon" style="background:rgba(91,141,238,.15);color:#5b8dee;">≡</div>`;
    if (item._cat === 'bop')   return `<div class="gs-icon" style="background:rgba(21,128,61,.15);color:#15803d;">B</div>`;
    if (item._cat === 'tasks') {
      return item._subtype === 'issue'
        ? `<div class="gs-icon" style="background:rgba(194,65,12,.15);color:#c2410c;">!</div>`
        : `<div class="gs-icon" style="background:rgba(194,65,12,.1);color:#c2410c;">T</div>`;
    }
    if (item._cat === 'know') {
      return item._subtype === 'rule'
        ? `<div class="gs-icon" style="background:rgba(126,34,206,.15);color:#7e22ce;">R</div>`
        : `<div class="gs-icon" style="background:rgba(126,34,206,.1);color:#7e22ce;">K</div>`;
    }
    if (item._cat === 'cal') {
      return item._subtype === 'meeting'
        ? `<div class="gs-icon" style="background:rgba(2,132,199,.15);color:#0284c7;">M</div>`
        : `<div class="gs-icon" style="background:rgba(2,132,199,.1);color:#0284c7;">E</div>`;
    }
    return `<div class="gs-icon">○</div>`;
  }

  function _itemTitle(item) {
    return item.name || item.title || item.display_id || '(无标题)';
  }

  function _itemSub(item) {
    if (item._subtype === 'list') {
      const typeMap = { task: '任务清单', issue: '问题清单', knowledge: '知识库清单', rule: '规则清单' };
      return typeMap[item.item_type] || '清单';
    }
    if (item._subtype === 'user')  return item.email || '';
    if (item._subtype === 'chat')  return item.chat_type === 'p2p' ? '单聊' : '群聊';
    if (item._subtype === 'doc')   return item.owner_name ? `作者：${item.owner_name}` : '飞书文档';
    if (item._subtype === 'task')  return item.status || '';
    if (item._subtype === 'issue') return `严重度：${item.severity || '-'}`;
    if (item._subtype === 'rule')  return item.code || item.rule_type || '';
    if (item._subtype === 'event')   return item.start ? `${item.start}` : '日程';
    if (item._subtype === 'meeting') return item.meeting_no || '会议记录';
    if (item._cat === 'bop')       return item.node_type || '';
    return '';
  }

  function _esc(s) {
    return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  function _showLoading() {
    _resultsEl.innerHTML = `
      <div class="gs-loading">
        <div class="gs-loading-dot"></div>
        <div class="gs-loading-dot"></div>
        <div class="gs-loading-dot"></div>
      </div>`;
    _flatItems = [];
    _selectedIdx = -1;
  }

  function _render(sections) {
    _results  = sections;
    _flatItems = [];
    _selectedIdx = -1;

    if (!sections.length) {
      _resultsEl.innerHTML = `<div class="gs-empty">未找到相关结果</div>`;
      return;
    }

    let html = '';
    for (const sec of sections) {
      html += `<div class="gs-section-hdr">${_esc(sec.label)}</div>`;
      for (const item of sec.items) {
        const idx = _flatItems.length;
        _flatItems.push(item);
        const sub = _itemSub(item);
        html += `
          <div class="gs-item" data-idx="${idx}">
            ${_itemIcon(item)}
            <div class="gs-item-info">
              <div class="gs-item-name">${_esc(_itemTitle(item))}</div>
              ${sub ? `<div class="gs-item-sub">${_esc(sub)}</div>` : ''}
            </div>
            <span class="gs-item-meta">${_catLabel(item._cat)}</span>
          </div>`;
      }
    }
    _resultsEl.innerHTML = html;

    // 绑定点击
    _resultsEl.querySelectorAll('.gs-item').forEach(el => {
      el.addEventListener('click', () => {
        const i = parseInt(el.dataset.idx, 10);
        if (!isNaN(i)) _onSelect(_flatItems[i]);
      });
      el.addEventListener('mouseenter', () => {
        const i = parseInt(el.dataset.idx, 10);
        if (!isNaN(i)) _setSelected(i);
      });
    });
  }

  function _catLabel(catId) {
    const extra = { lists: '清单' };
    const c = CATEGORIES.find(c => c.id === catId);
    return c ? c.label : (extra[catId] || catId);
  }

  function _setSelected(idx) {
    _selectedIdx = idx;
    _resultsEl.querySelectorAll('.gs-item').forEach((el, i) => {
      el.classList.toggle('selected', i === idx);
    });
  }

  // ── 打开条目 ──────────────────────────────────────────────────────────────
  function _feishuOpen(httpsApplinkUrl) {
    // 转为 feishu:// native 协议，用静默 IPC 通道打开（避免 Windows 弹出中转窗口）
    const native = httpsApplinkUrl.replace(
      'https://applink.feishu.cn/',
      'feishu://applink/'
    );
    if (window.electronAPI?.openFeishuLink) {
      window.electronAPI?.openFeishuLink?.(native);
    } else {
      window.electronAPI?.openExternal?.(native) || window.open(httpsApplinkUrl, '_blank');
    }
  }

  function _onSelect(item) {
    if (!item) return;

    if (item._cat === 'feishu') {
      if (item._subtype === 'user') {
        if (item.open_id) {
          _feishuOpen(`https://applink.feishu.cn/client/chat/open?openId=${item.open_id}`);
        } else if (item.chat_id) {
          // p2p 单聊降级结果：直接用 chat_id 打开
          _feishuOpen(`https://applink.feishu.cn/client/chat/open?openChatId=${item.chat_id}`);
        }
      } else if (item._subtype === 'chat' && item.chat_id) {
        _feishuOpen(`https://applink.feishu.cn/client/chat/open?openChatId=${item.chat_id}`);
      } else if (item._subtype === 'doc' && item.url) {
        // 文档在新 Tab 页签里用 webview 打开
        window.TabManager?.open('container_card', {
          mode: 'webview', url: item.url, _tabTitle: item.name || item.title || '飞书文档',
        });
        hide();
        return;
      }
      hide();
      return;
    }

    // 日程/会议 → 直接用飞书 applink 打开
    if (item._cat === 'cal') {
      if (item._subtype === 'event' && item._entity_type === 'event') {
        // 日程没有直接 applink，用日历主入口
        _feishuOpen(`https://applink.feishu.cn/client/calendar/open`);
      } else if (item.meeting_url) {
        _feishuOpen(item.meeting_url);
      }
      hide();
      return;
    }

    // 站内跳转
    let tabId = null;
    if (item._cat === 'bop')   tabId = 'bop';
    if (item._subtype === 'task' || item._subtype === 'issue') tabId = item._subtype === 'task' ? 'task' : 'issue';
    if (item._cat === 'know')  tabId = item._subtype === 'rule' ? 'rule_mgmt' : 'knowledge';
    if (item._subtype === 'list') {
      const listTabMap = { task: 'task', issue: 'issue', knowledge: 'knowledge', rule: 'rule_mgmt' };
      tabId = listTabMap[item.item_type] || null;
    }

    if (tabId) {
      window._gsNav = { item_type: item._subtype || item._cat, gid: item.gid, title: _itemTitle(item) };
      try { window.TabManager?.open(tabId); } catch (_) {}
    }
    hide();
  }

  // ── 显示/隐藏 ─────────────────────────────────────────────────────────────
  function show() {
    _overlay.classList.remove('hidden');
    _input.value = '';
    _query = '';
    _manualLock = false;
    _setCategory('all');
    _resultsEl.innerHTML = `<div class="gs-empty">输入关键词开始搜索</div>`;
    _flatItems = [];
    _selectedIdx = -1;
    _showTabs(false);
    requestAnimationFrame(() => _input.focus());
  }

  function hide() {
    _overlay.classList.add('hidden');
    if (_debounceTimer) { clearTimeout(_debounceTimer); _debounceTimer = null; }
  }

  function _showTabs(visible) {
    _tabsVisible = visible;
    _tabs.classList.toggle('hidden', !visible);
  }

  // ── 初始化 ────────────────────────────────────────────────────────────────
  function init() {
    _overlay   = document.getElementById('gs-overlay');
    _panel     = document.getElementById('gs-panel');
    _input     = document.getElementById('gs-input');
    _badge     = document.getElementById('gs-category-badge');
    _tabs      = document.getElementById('gs-category-tabs');
    _resultsEl = document.getElementById('gs-results');
    _footer    = document.getElementById('gs-footer');

    if (!_overlay) return;

    // 渲染分类 Tabs
    _tabs.innerHTML = CATEGORIES.map(c =>
      `<button class="gs-tab${c.id === 'all' ? ' active' : ''}" data-cat="${c.id}">${c.label}</button>`
    ).join('');

    // 分类 Tab 点击
    _tabs.addEventListener('click', e => {
      const btn = e.target.closest('.gs-tab');
      if (!btn) return;
      _setCategory(btn.dataset.cat, true);
      if (_query.length >= 2) _triggerSearch();
    });

    // 标徽点击 → 切换 Tabs 显示
    _badge.addEventListener('click', () => _showTabs(!_tabsVisible));

    // IME 输入法组合状态标记（中文/日文/韩文输入时不提前触发搜索）
    let _composing = false;
    _input.addEventListener('compositionstart', () => { _composing = true; });
    _input.addEventListener('compositionend', () => {
      _composing = false;
      _query = _input.value.trim();
      if (!_manualLock) _setCategory(_detectCategory(_query));
      if (_query.length >= 2) _triggerSearch();
    });

    // 输入框
    _input.addEventListener('input', () => {
      if (_composing) return;   // IME 组合过程中不触发，等 compositionend
      _query = _input.value.trim();
      if (!_manualLock) {
        _setCategory(_detectCategory(_query));
      }
      if (!_query) {
        if (_debounceTimer) clearTimeout(_debounceTimer);
        _resultsEl.innerHTML = `<div class="gs-empty">输入关键词开始搜索</div>`;
        _flatItems = [];
        return;
      }
      _triggerSearch();
    });

    // 键盘导航
    _input.addEventListener('keydown', e => {
      if (e.key === 'Escape') { e.stopPropagation(); hide(); return; }
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        _setSelected(Math.min(_selectedIdx + 1, _flatItems.length - 1));
        _scrollSelectedIntoView();
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        _setSelected(Math.max(_selectedIdx - 1, 0));
        _scrollSelectedIntoView();
        return;
      }
      if (e.key === 'Enter') {
        if (_selectedIdx >= 0 && _flatItems[_selectedIdx]) {
          _onSelect(_flatItems[_selectedIdx]);
        }
        return;
      }
      if (e.key === 'Tab') {
        e.preventDefault();
        const cats = CATEGORIES.map(c => c.id);
        const cur = cats.indexOf(_activeCategory);
        const next = e.shiftKey
          ? (cur - 1 + cats.length) % cats.length
          : (cur + 1) % cats.length;
        _setCategory(cats[next], true);
        if (_query.length >= 2) _triggerSearch();
      }
    });

    // 点击遮罩关闭
    _overlay.addEventListener('click', e => {
      if (e.target === _overlay) hide();
    });
  }

  function _triggerSearch() {
    if (_debounceTimer) clearTimeout(_debounceTimer);
    if (_query.length < 2) return;
    _debounceTimer = setTimeout(() => {
      _doSearch(_query, _activeCategory);
    }, 280);
  }

  function _scrollSelectedIntoView() {
    const selected = _resultsEl.querySelector('.gs-item.selected');
    if (selected) selected.scrollIntoView({ block: 'nearest' });
  }

  return { show, hide, init };
})();

window.GlobalSearch = GlobalSearch;

