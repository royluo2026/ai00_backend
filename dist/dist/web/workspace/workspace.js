/**
 * WorkspaceEngine — Obsidian 风格分屏工作台引擎
 *
 * 布局树：
 *   SplitNode { type:'split', dir:'h'|'v', ratio:0-1, a:LayoutNode, b:LayoutNode }
 *   PanelNode { type:'panel', id:string }
 *
 * 核心能力：
 *   - addTab(tabId, title, src, opts)  — 向当前聚焦面板添加 Tab
 *   - closeTab(tabId)                  — 关闭 Tab，面板空时自动收起
 *   - activateTab(tabId)               — 切换到指定 Tab
 *   - hasTab(tabId)                    — 判断 Tab 是否已存在
 *   - activeTabId()                    — 返回当前聚焦面板的活跃 Tab id
 *
 * 分屏交互：
 *   拖拽 Tab → 悬停至目标面板边缘 Drop Zone → 松手创建新分屏面板
 *   拖拽 Tab → 悬停至目标面板中央 Drop Zone → 移动 Tab 到该面板
 *   拖拽分割线 → 调整两侧面板比例
 */

'use strict';

const WorkspaceEngine = (() => {

  // ─── 状态 ────────────────────────────────────────────────────────────────────
  let _container    = null;       // #ws-content
  let _root         = null;       // LayoutNode 树根
  let _panels       = new Map();  // panelId → PanelState
  let _tabs         = new Map();  // tabId   → TabState
  let _focusedId    = null;       // 当前聚焦面板 id
  let _nextPanelIdx = 1;
  let _dragging     = null;       // { tabId, sourcePanelId } | null

  // ─── 数据结构 ─────────────────────────────────────────────────────────────────
  /**
   * PanelState { id, el, tabBarEl, contentEl, tabs:string[], activeTabId:string|null }
   * TabState   { panelId, tabEl, paneEl, title, closeable }
   */

  // ─── 初始化 ───────────────────────────────────────────────────────────────────
  function init(containerId) {
    _container = document.getElementById(containerId);
    if (!_container) { console.error('[WS] container not found:', containerId); return null; }

    const pid = _mkPid();
    _panels.set(pid, _mkPanelState(pid));
    _root = { type: 'panel', id: pid };

    _rerender();
    _focusPanel(pid);

    document.addEventListener('dragend', _onDragEnd);
    return pid;
  }

  function _mkPid() { return 'ws-p' + (_nextPanelIdx++); }

  function _mkPanelState(id) {
    return { id, el: null, tabBarEl: null, contentEl: null, tabs: [], activeTabId: null };
  }

  // ─── 布局树渲染 ───────────────────────────────────────────────────────────────
  function _rerender() {
    const el = _buildNodeEl(_root);
    _container.innerHTML = '';
    _container.appendChild(el);
  }

  function _buildNodeEl(node) {
    return node.type === 'panel'
      ? _buildPanelEl(node.id)
      : _buildSplitEl(node);
  }

  function _buildPanelEl(pid) {
    const ps = _panels.get(pid);
    if (!ps) return document.createElement('div'); // fallback

    const el = document.createElement('div');
    el.className = 'ws-panel';
    el.dataset.panelId = pid;

    // Tab bar
    const tabBar = document.createElement('div');
    tabBar.className = 'ws-tab-bar';
    tabBar.dataset.panelId = pid;

    const spacer = document.createElement('div');
    spacer.className = 'ws-tab-bar-spacer';

    // 右侧操作区（命令面板）
    const actions = document.createElement('div');
    actions.className = 'ws-tab-bar-actions';
    const cmdBtn = document.createElement('button');
    cmdBtn.className = 'ws-panel-action-btn';
    cmdBtn.title = '命令面板 (Ctrl+P)';
    cmdBtn.textContent = '⌘';
    cmdBtn.addEventListener('click', () => window.CmdPalette?.show());
    actions.appendChild(cmdBtn);

    // 窗口控制按钮：最小化 / 最大化 / 关闭（仅第一个面板渲染一次）
    if (!document.querySelector('.ws-win-controls')) {
      const winControls = document.createElement('div');
      winControls.className = 'ws-win-controls';
      winControls.innerHTML =
        '<button class="ws-win-btn" title="最小化" onclick="window.electronAPI?.minimize()">' +
          '<svg width="10" height="2" viewBox="0 0 10 2"><line x1="0" y1="1" x2="10" y2="1" stroke="currentColor" stroke-width="1.5"/></svg>' +
        '</button>' +
        '<button class="ws-win-btn" title="最大化/还原" onclick="window.electronAPI?.maximize()">' +
          '<svg width="10" height="10" viewBox="0 0 10 10"><rect x="1" y="1" width="8" height="8" rx="1.5" stroke="currentColor" stroke-width="1.5" fill="none"/></svg>' +
        '</button>' +
        '<button class="ws-win-btn danger" title="关闭" onclick="window.electronAPI?.close()">' +
          '<svg width="10" height="10" viewBox="0 0 10 10"><line x1="0" y1="0" x2="10" y2="10" stroke="currentColor" stroke-width="1.5"/><line x1="10" y1="0" x2="0" y2="10" stroke="currentColor" stroke-width="1.5"/></svg>' +
        '</button>';
      actions.appendChild(winControls);
    }

    // App logo（仅主面板，tab 区最左侧）
    if (!document.querySelector('.ws-app-logo')) {
      const logoEl = document.createElement('img');
      logoEl.className = 'ws-app-logo';
      const _webBase = window.electronAPI?._isElectron === false ? '/web/' : '';
      const _theme   = document.documentElement.getAttribute('data-theme') || 'light';
      logoEl.src = `${_webBase}assets/icons/logo/logo_${_theme}.svg`;
      logoEl.draggable = false;
      tabBar.appendChild(logoEl);
    }

    tabBar.appendChild(spacer);   // spacer between tabs and actions
    tabBar.appendChild(actions);  // actions at far right

    // Tab content area
    const content = document.createElement('div');
    content.className = 'ws-tab-content';
    content.dataset.panelId = pid;

    // Drop zones
    el.appendChild(tabBar);
    el.appendChild(content);
    el.appendChild(_buildDropZones(pid));

    // Update PanelState refs
    ps.el         = el;
    ps.tabBarEl   = tabBar;
    ps.contentEl  = content;

    // Re-inject existing tabs
    ps.tabs.forEach(tid => {
      const ts = _tabs.get(tid);
      if (!ts) return;
      tabBar.insertBefore(ts.tabEl, spacer); // keep spacer at end
      content.appendChild(ts.paneEl);
      // Restore active class
      const isActive = tid === ps.activeTabId;
      ts.tabEl.classList.toggle('active', isActive);
      ts.paneEl.classList.toggle('active', isActive);
    });

    el.addEventListener('mousedown', () => _focusPanel(pid));
    return el;
  }

  function _buildDropZones(pid) {
    const zones = document.createElement('div');
    zones.className = 'ws-drop-zones';

    [
      { cls: 'center', label: '移至此面板' },
      { cls: 'left',   label: '向左分屏'   },
      { cls: 'right',  label: '向右分屏'   },
      { cls: 'top',    label: '向上分屏'   },
      { cls: 'bottom', label: '向下分屏'   },
    ].forEach(({ cls, label }) => {
      const z = document.createElement('div');
      z.className = `ws-drop-zone ${cls}`;
      z.dataset.side = cls;
      z.dataset.panelId = pid;
      z.innerHTML = `<span class="ws-drop-zone-label">${label}</span>`;

      z.addEventListener('dragenter', e => { e.preventDefault(); z.classList.add('ws-dz-active'); });
      z.addEventListener('dragleave', () => z.classList.remove('ws-dz-active'));
      z.addEventListener('dragover',  e => e.preventDefault());
      z.addEventListener('drop', e => {
        e.preventDefault();
        e.stopPropagation();
        z.classList.remove('ws-dz-active');
        _panels.get(pid)?.el.classList.remove('ws-drag-over');
        _commitDrop(pid, cls);
      });

      zones.appendChild(z);
    });

    return zones;
  }

  function _buildSplitEl(node) {
    const el = document.createElement('div');
    el.className = `ws-split ws-split-${node.dir}`;
    node.el = el;

    const aEl = _buildNodeEl(node.a);
    const splitter = document.createElement('div');
    splitter.className = 'ws-splitter';
    const bEl = _buildNodeEl(node.b);

    _applyRatio(aEl, bEl, node.ratio ?? 0.5);
    _initSplitter(splitter, node, aEl, bEl);

    el.appendChild(aEl);
    el.appendChild(splitter);
    el.appendChild(bEl);
    return el;
  }

  function _applyRatio(aEl, bEl, r) {
    aEl.style.flex = `0 0 calc(${r * 100}% - 2px)`;
    bEl.style.flex = `0 0 calc(${(1 - r) * 100}% - 2px)`;
    aEl.style.minWidth = '0';
    aEl.style.minHeight = '0';
    bEl.style.minWidth = '0';
    bEl.style.minHeight = '0';
  }

  function _initSplitter(splitter, node, aEl, bEl) {
    let startPos, startRatio, totalSize;

    splitter.addEventListener('mousedown', e => {
      e.preventDefault();
      startPos   = node.dir === 'h' ? e.clientX : e.clientY;
      startRatio = node.ratio ?? 0.5;
      const rect = node.el.getBoundingClientRect();
      totalSize  = node.dir === 'h' ? rect.width : rect.height;
      splitter.classList.add('ws-splitter-dragging');
      document.querySelectorAll('iframe').forEach(f => { f.style.pointerEvents = 'none'; });

      const onMove = e => {
        const delta = (node.dir === 'h' ? e.clientX : e.clientY) - startPos;
        node.ratio  = Math.max(0.1, Math.min(0.9, startRatio + delta / totalSize));
        _applyRatio(aEl, bEl, node.ratio);
      };
      const onUp = () => {
        splitter.classList.remove('ws-splitter-dragging');
        document.querySelectorAll('iframe').forEach(f => { f.style.pointerEvents = ''; });
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
      };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    });
  }

  // ─── 拖拽处理 ────────────────────────────────────────────────────────────────
  function _onDragEnd() {
    document.querySelectorAll('.ws-panel').forEach(p => p.classList.remove('ws-drag-over'));
    _dragging = null;
  }

  function _commitDrop(targetPid, side) {
    if (!_dragging) return;
    const { tabId, sourcePanelId } = _dragging;
    _dragging = null;
    document.querySelectorAll('.ws-panel').forEach(p => p.classList.remove('ws-drag-over'));

    if (side === 'center') {
      if (targetPid !== sourcePanelId) _moveTab(tabId, sourcePanelId, targetPid);
    } else {
      const dir    = (side === 'left' || side === 'right') ? 'h' : 'v';
      const newPid = _mkPid();
      _panels.set(newPid, _mkPanelState(newPid));
      _insertSplit(targetPid, dir, side, newPid);
      _moveTab(tabId, sourcePanelId, newPid);
    }
  }

  // ─── 布局树操作 ───────────────────────────────────────────────────────────────
  /** 在 targetPid 所在位置插入 split，新面板 newPid 放在 side 侧 */
  function _insertSplit(targetPid, dir, side, newPid) {
    const found = _findPanel(_root, null, null, targetPid);
    if (!found) return;
    const { parent, key } = found;

    const oldNode = found.node;
    const newPanelNode = { type: 'panel', id: newPid };
    const [a, b] = (side === 'left' || side === 'top')
      ? [newPanelNode, oldNode]
      : [oldNode, newPanelNode];

    const splitNode = { type: 'split', dir, ratio: 0.5, a, b, el: null };

    if (!parent) {
      _root = splitNode;
    } else {
      parent[key] = splitNode;
    }
    _rerender();
    _focusPanel(newPid);
  }

  /** 移动 tab 到另一个面板 */
  function _moveTab(tabId, fromPid, toPid) {
    if (fromPid === toPid) return;
    const ts = _tabs.get(tabId);
    const fp = _panels.get(fromPid);
    const tp = _panels.get(toPid);
    if (!ts || !fp || !tp) return;

    // 从源面板移除
    fp.tabs = fp.tabs.filter(id => id !== tabId);
    ts.tabEl.remove();
    ts.paneEl.remove();
    if (fp.activeTabId === tabId) {
      fp.activeTabId = null;
      if (fp.tabs[0]) _activateInPanel(fp.tabs[0], fromPid);
    }

    // 插入目标面板
    const spacer = tp.tabBarEl.querySelector('.ws-tab-bar-spacer');
    tp.tabBarEl.insertBefore(ts.tabEl, spacer);
    tp.contentEl.appendChild(ts.paneEl);
    tp.tabs.push(tabId);
    ts.panelId = toPid;

    _activateInPanel(tabId, toPid);
    _focusPanel(toPid);

    // 源面板空了 → 收起
    if (fp.tabs.length === 0) _collapsePanel(fromPid);
  }

  /** 源面板已无 Tab，从布局树移除并 rerender */
  function _collapsePanel(pid) {
    const found = _findPanel(_root, null, null, pid);
    if (!found || !found.parent) return; // 根面板不能收起

    const { parent: splitNode, key: panelKey } = found;
    const sibKey  = panelKey === 'a' ? 'b' : 'a';
    const sibling = splitNode[sibKey];

    const gp = _findNode(_root, null, null, splitNode);
    if (!gp || !gp.parent) {
      _root = sibling;
    } else {
      gp.parent[gp.key] = sibling;
    }

    _panels.delete(pid);
    if (_focusedId === pid) _focusedId = null;
    _rerender();
  }

  // ─── 树遍历 ───────────────────────────────────────────────────────────────────
  function _findPanel(node, parent, key, pid) {
    if (node.type === 'panel') return node.id === pid ? { node, parent, key } : null;
    return _findPanel(node.a, node, 'a', pid)
        || _findPanel(node.b, node, 'b', pid);
  }

  function _findNode(node, parent, key, target) {
    if (node === target) return { node, parent, key };
    if (node.type === 'split') {
      return _findNode(node.a, node, 'a', target)
          || _findNode(node.b, node, 'b', target);
    }
    return null;
  }

  // ─── 面板焦点 ─────────────────────────────────────────────────────────────────
  function _focusPanel(pid) {
    document.querySelectorAll('.ws-panel').forEach(p => p.classList.remove('ws-panel-focused'));
    const ps = _panels.get(pid);
    if (ps?.el) ps.el.classList.add('ws-panel-focused');
    _focusedId = pid;
  }

  function _activePid() {
    if (_focusedId && _panels.has(_focusedId)) return _focusedId;
    return _panels.size > 0 ? _panels.keys().next().value : null;
  }

  // ─── Tab 激活 ────────────────────────────────────────────────────────────────
  function _activateInPanel(tabId, pid) {
    const ps = _panels.get(pid);
    if (!ps) return;
    ps.tabs.forEach(tid => {
      const ts = _tabs.get(tid);
      if (ts) {
        ts.tabEl.classList.toggle('active', tid === tabId);
        ts.paneEl.classList.toggle('active', tid === tabId);
      }
    });
    ps.activeTabId = tabId;
    // 同步左侧导航高亮
    document.querySelectorAll('.nav-item[data-view]').forEach(n =>
      n.classList.toggle('active', n.dataset.view === tabId));
  }

  // ─── 公开 API ─────────────────────────────────────────────────────────────────

  /**
   * addTab(tabId, title, src, opts)
   *   opts.closeable  boolean  是否可关闭，默认 true
   *   opts.html       string   内联 HTML（与 src 二选一，welcome 页面用）
   */
  function addTab(tabId, title, src, opts = {}) {
    const { closeable = true, html = null } = opts;
    const pid = _activePid();
    const ps  = _panels.get(pid);
    if (!ps) { console.error('[WS] no active panel'); return; }

    // ── Tab 按钮
    const tabEl = document.createElement('div');
    tabEl.className = 'ws-tab';
    tabEl.dataset.tabId = tabId;
    tabEl.draggable = closeable; // welcome tab 不可拖
    tabEl.innerHTML =
      `<span class="ws-tab-title">${_esc(title)}</span>` +
      (closeable
        ? `<span class="ws-tab-close" title="关闭">✕</span>` +
          `<span class="ws-tab-lock" title="已锁定">` +
          `<svg width="10" height="10" viewBox="0 0 10 10" fill="currentColor">` +
          `<path d="M7.5 4.5V3a2.5 2.5 0 0 0-5 0v1.5H1V9h8V4.5H7.5zm-1 0h-3V3a1.5 1.5 0 0 1 3 0v1.5z"/></svg></span>`
        : '');

    // 事件读 dataset.tabId，以便 replaceTab 后自动指向新 id
    tabEl.addEventListener('click', e => {
      const tid = tabEl.dataset.tabId;
      if (e.target.closest('.ws-tab-close')) { closeTab(tid); return; }
      activateTab(tid);
    });
    tabEl.addEventListener('contextmenu', e => _showTabCtxMenu(e, tabEl.dataset.tabId));

    // Drag start（用于分屏）
    if (closeable) {
      tabEl.addEventListener('dragstart', e => {
        const tid = tabEl.dataset.tabId;
        const ts  = _tabs.get(tid);
        if (!ts || ts.locked) { e.preventDefault(); return; }
        _dragging = { tabId: tid, sourcePanelId: ts.panelId };
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', tid);
        tabEl.classList.add('ws-tab-dragging');
        setTimeout(() => {
          document.querySelectorAll('.ws-panel').forEach(p => {
            if (p.dataset.panelId !== _dragging?.sourcePanelId) {
              p.classList.add('ws-drag-over');
            } else {
              // 在自己面板内也可拖到边缘分屏（不含 center）
              const zones = p.querySelectorAll('.ws-drop-zone:not(.center)');
              zones.forEach(z => z.closest('.ws-drop-zones')?.parentElement
                ?.classList.add('ws-drag-over'));
              p.classList.add('ws-drag-over');
            }
          });
          // iframe 期间屏蔽鼠标事件，避免吞掉 dragover
          document.querySelectorAll('iframe').forEach(f => { f.style.pointerEvents = 'none'; });
        }, 0);
      });
      tabEl.addEventListener('dragend', () => {
        tabEl.classList.remove('ws-tab-dragging');
        document.querySelectorAll('.ws-panel').forEach(p => p.classList.remove('ws-drag-over'));
        document.querySelectorAll('iframe').forEach(f => { f.style.pointerEvents = ''; });
        _dragging = null;
      });
    }

    // ── Tab 内容面板
    const paneEl = document.createElement('div');
    paneEl.className = 'ws-tab-pane';
    paneEl.dataset.tabId = tabId;

    if (html !== null) {
      paneEl.innerHTML = html;
    } else if (src) {
      // 网页版：相对路径需加 /web/ 前缀，否则被 SPA fallback 拦截返回 index.html
      if (window.electronAPI?._isElectron === false &&
          src && !src.startsWith('/') && !src.startsWith('http')) {
        src = '/web/' + src;
      }
      // 网页版：HTML 文件加会话级时间戳，防止浏览器加载缓存的旧版本
      if (window.electronAPI?._isElectron === false && src && src.endsWith('.html')) {
        const sep = src.includes('?') ? '&' : '?';
        src = src + sep + '_cb=' + (window._WS_SESSION_TS = window._WS_SESSION_TS || Date.now());
      }
      const iframe = document.createElement('iframe');
      iframe.src   = src;
      iframe.title = title;
      iframe.allow = 'clipboard-read; clipboard-write';

      // 遮罩：与主题背景同色，防止首次加载时白色闪烁
      iframe.addEventListener('load', () => {
        const theme = document.documentElement.getAttribute('data-theme') || 'light';
        try { iframe.contentWindow?.postMessage({ type: 'theme', theme }, '*'); } catch (_) {}
        // 遮罩淡出，iframe 淡入
        iframe.classList.add('ws-pane-iframe-ready');

        // 快捷键穿透：iframe 内按快捷键 → 转发给顶层主框架处理
        // 注意：handler 挂在 iframe 的 document 上，执行时 window 是 iframe 的 window，
        // 必须用 window.top 才能访问主框架里的 GlobalSearch / CmdPalette 等。
        const _doc = iframe.contentDocument || iframe.contentWindow?.document;
        if (_doc) {
          _doc.addEventListener('keydown', (e) => {
            if (!e.ctrlKey) return;
            const top = window.top;
            if (e.key === 'o') { e.preventDefault(); top.GlobalSearch?.show(); }
            if (e.key === 'p') { e.preventDefault(); top.CmdPalette?.show(); }
            if (e.key === ',') { e.preventDefault(); top.TabManager?.open('settings'); }
          }, true);
        }
      });

      paneEl.appendChild(iframe);
    }

    // 插入到 tab bar（spacer 之前）
    const spacer = ps.tabBarEl.querySelector('.ws-tab-bar-spacer');
    ps.tabBarEl.insertBefore(tabEl, spacer);
    ps.contentEl.appendChild(paneEl);
    ps.tabs.push(tabId);

    _tabs.set(tabId, { panelId: pid, tabEl, paneEl, title, closeable, locked: false, src: src || null });
    _activateInPanel(tabId, pid);
    _focusPanel(pid);
    // 将键盘焦点交给新 tab 的 iframe
    const newIframe = paneEl.querySelector('iframe');
    if (newIframe) setTimeout(() => { try { newIframe.contentWindow?.focus(); } catch(_){} }, 0);
  }

  function closeTab(tabId) {
    const ts = _tabs.get(tabId);
    if (!ts || !ts.closeable || ts.locked) return;
    const pid = ts.panelId;
    const ps  = _panels.get(pid);

    ts.tabEl.remove();
    ts.paneEl.remove();
    _tabs.delete(tabId);

    if (ps) {
      ps.tabs = ps.tabs.filter(id => id !== tabId);
      if (ps.activeTabId === tabId) {
        ps.activeTabId = null;
        const next = ps.tabs[0];
        if (next) {
          _activateInPanel(next, pid);
        } else if (ps.tabs.length === 0 && _panels.size > 1) {
          _collapsePanel(pid);
        } else {
          // 回退到 welcome（仅剩根面板）
          document.querySelectorAll('.nav-item[data-view]').forEach(n =>
            n.classList.remove('active'));
        }
      }
    }
    console.log('[WS] closeTab:', tabId);
  }

  function activateTab(tabId) {
    const ts = _tabs.get(tabId);
    if (!ts) return;
    _activateInPanel(tabId, ts.panelId);
    _focusPanel(ts.panelId);
    // 将键盘焦点交给 iframe，使 iframe 内快捷键（如工作台 1-7）可用
    const iframe = ts.paneEl?.querySelector('iframe');
    if (iframe) setTimeout(() => { try { iframe.contentWindow?.focus(); } catch(_){} }, 0);
  }

  function hasTab(tabId) { return _tabs.has(tabId); }

  function activeTabId() {
    const ps = _panels.get(_activePid());
    return ps?.activeTabId ?? null;
  }

  /** 供 SidebarManager._onDrop 使用：获取 tab 的 title/src/closeable */
  function getTabInfo(tabId) {
    const ts = _tabs.get(tabId);
    if (!ts) return null;
    return { title: ts.title, src: ts.src, closeable: ts.closeable };
  }

  // ─── 锁定 / 替换 ─────────────────────────────────────────────────────────────
  function lockTab(tabId) {
    const ts = _tabs.get(tabId);
    if (!ts || !ts.closeable) return;
    ts.locked = true;
    ts.tabEl.classList.add('ws-tab-locked');
    ts.tabEl.draggable = false;
  }

  function unlockTab(tabId) {
    const ts = _tabs.get(tabId);
    if (!ts) return;
    ts.locked = false;
    ts.tabEl.classList.remove('ws-tab-locked');
    ts.tabEl.draggable = true;
  }

  /** 当前 tab 是否可被新导航替换（未锁定且可关闭） */
  function canReplaceTab(tabId) {
    const ts = _tabs.get(tabId);
    return !!(ts && ts.closeable && !ts.locked);
  }

  /**
   * 原位替换 tab：更新标题/iframe src，重映射 _tabs key。
   * 由于 click/dragstart 事件均读 tabEl.dataset.tabId，替换后自动生效。
   */
  function replaceTab(oldTabId, newTabId, title, src) {
    const ts = _tabs.get(oldTabId);
    if (!ts) { addTab(newTabId, title, src); return; }

    // 更新 DOM 标题
    const titleEl = ts.tabEl.querySelector('.ws-tab-title');
    if (titleEl) titleEl.textContent = title;

    // 更新 iframe src
    const iframe = ts.paneEl.querySelector('iframe');
    if (iframe) {
      iframe.src   = src;
      iframe.title = title;
    } else if (!iframe && src) {
      // pane 是 inline html（welcome 不走这里，但防御一下）
      const f = document.createElement('iframe');
      f.src   = src; f.title = title;
      f.allow = 'clipboard-read; clipboard-write';
      f.addEventListener('load', () => {
        const theme = document.documentElement.getAttribute('data-theme') || 'light';
        try { f.contentWindow?.postMessage({ type: 'theme', theme }, '*'); } catch (_) {}
        try {
          f.contentDocument?.addEventListener('keydown', (e) => {
            if (!e.ctrlKey) return;
            const top = window.top;
            if (e.key === 'o') { e.preventDefault(); top.GlobalSearch?.show(); }
            if (e.key === 'p') { e.preventDefault(); top.CmdPalette?.show(); }
            if (e.key === ',') { e.preventDefault(); top.TabManager?.open('settings'); }
          }, true);
        } catch (_) {}
      });
      ts.paneEl.innerHTML = '';
      ts.paneEl.appendChild(f);
    }

    // 更新状态
    ts.title = title;
    ts.src   = src;
    _tabs.delete(oldTabId);
    _tabs.set(newTabId, ts);
    ts.tabEl.dataset.tabId  = newTabId;
    ts.paneEl.dataset.tabId = newTabId;

    const ps = _panels.get(ts.panelId);
    if (ps) {
      const idx = ps.tabs.indexOf(oldTabId);
      if (idx >= 0) ps.tabs[idx] = newTabId;
      if (ps.activeTabId === oldTabId) ps.activeTabId = newTabId;
    }

    _activateInPanel(newTabId, ts.panelId);
  }

  function _esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  // ─── Tab 右键菜单 ─────────────────────────────────────────────────────────────
  let _ctxMenu = null;

  function _ensureCtxMenu() {
    if (_ctxMenu) return _ctxMenu;
    const el = document.createElement('div');
    el.className = 'ws-ctx-menu hidden';
    document.body.appendChild(el);
    document.addEventListener('mousedown', e => {
      if (!el.contains(e.target)) _hideCtxMenu();
    });
    _ctxMenu = el;
    return el;
  }

  function _hideCtxMenu() {
    _ctxMenu?.classList.add('hidden');
  }

  function _showTabCtxMenu(e, tabId) {
    e.preventDefault();
    const ts  = _tabs.get(tabId);
    if (!ts) return;
    const pid = ts.panelId;
    const ps  = _panels.get(pid);

    const menu = _ensureCtxMenu();
    menu.innerHTML = '';

    const add = (label, action, disabled = false) => {
      const item = document.createElement('div');
      item.className = 'ws-ctx-item' + (disabled ? ' ws-ctx-disabled' : '');
      item.textContent = label;
      if (!disabled) item.addEventListener('mousedown', ev => {
        ev.preventDefault(); ev.stopPropagation();
        _hideCtxMenu(); action();
      });
      menu.appendChild(item);
    };
    const sep = () => {
      const s = document.createElement('div');
      s.className = 'ws-ctx-sep';
      menu.appendChild(s);
    };

    // 锁定 / 解锁
    add(ts.locked ? '解锁标签页' : '锁定标签页', () => {
      ts.locked ? unlockTab(tabId) : lockTab(tabId);
    }, !ts.closeable);

    sep();

    // 在新窗口打开（需要 src）—— 先关掉原 tab，再弹出
    const canPopOut = ts.closeable && !ts.locked && ts.src;
    add('在新窗口打开', () => {
      const popSrc   = ts.src;
      const popTitle = ts.title;
      closeTab(tabId);
      window.electronAPI?.wsPopOut(tabId, popTitle, popSrc);
    }, !canPopOut);

    sep();

    add('关闭', () => closeTab(tabId), !ts.closeable || ts.locked);

    // 关闭同面板其他标签
    const otherCloseable = (ps?.tabs || []).filter(id => id !== tabId && _tabs.get(id)?.closeable);
    add(`关闭其他 (${otherCloseable.length})`, () => {
      [...otherCloseable].forEach(id => closeTab(id));
    }, otherCloseable.length === 0);

    // 关闭同面板右侧标签
    const idx = ps?.tabs.indexOf(tabId) ?? -1;
    const rightCloseable = idx >= 0
      ? ps.tabs.slice(idx + 1).filter(id => _tabs.get(id)?.closeable)
      : [];
    add(`关闭右侧 (${rightCloseable.length})`, () => {
      [...rightCloseable].forEach(id => closeTab(id));
    }, rightCloseable.length === 0);

    // 定位
    menu.classList.remove('hidden');
    const { innerWidth: W, innerHeight: H } = window;
    const { offsetWidth: mw, offsetHeight: mh } = menu;
    menu.style.left = Math.min(e.clientX, W - mw - 4) + 'px';
    menu.style.top  = Math.min(e.clientY, H - mh - 4) + 'px';
  }

  // ─── 公开 ────────────────────────────────────────────────────────────────────

  /** Ctrl+Tab / Ctrl+Shift+Tab：在当前面板循环切换 tab */
  function switchTabByOffset(offset) {
    const pid = _activePid();
    const ps  = _panels.get(pid);
    if (!ps || ps.tabs.length <= 1) return;
    const cur = ps.tabs.indexOf(ps.activeTabId);
    if (cur < 0) return;
    const next = (cur + offset + ps.tabs.length) % ps.tabs.length;
    _activateInPanel(ps.tabs[next], pid);
  }

  /** Ctrl+1~9：切换到当前面板第 n 个 tab（1-based） */
  function switchTabByIndex(n) {
    const pid = _activePid();
    const ps  = _panels.get(pid);
    if (!ps) return;
    // Ctrl+9 固定跳到最后一个
    const idx = n >= 9 ? ps.tabs.length - 1 : n - 1;
    if (ps.tabs[idx]) _activateInPanel(ps.tabs[idx], pid);
  }

  /** 返回指定 tabId 的 <iframe> 元素（如果 tab 内容是 iframe 加载的） */
  function getTabIframe(tabId) {
    const ts = _tabs.get(tabId);
    if (!ts) return null;
    return ts.paneEl.querySelector('iframe') || null;
  }

  /**
   * 重载所有已打开 Tab 的 iframe（账户切换时调用，确保所有页面用新用户上下文刷新）。
   * 跳过无 src 的纯 HTML tab（欢迎页等）。
   */
  function reloadAllTabs() {
    _tabs.forEach((ts, tabId) => {
      const iframe = ts.paneEl.querySelector('iframe');
      if (!iframe || !iframe.src || iframe.src === window.location.href) return;
      try { iframe.contentWindow?.location?.reload(); } catch (_) {
        // fallback：直接重设 src
        try { const s = iframe.src; iframe.src = ''; iframe.src = s; } catch (_2) {}
      }
    });
  }

  /** 按 src 前缀查找已有 tabId（用于 container_card URL 去重复用） */
  function findTabIdBySrc(srcSubstr) {
    for (const [tid, ts] of _tabs) {
      if (ts.src && ts.src.includes(srcSubstr)) return tid;
    }
    return null;
  }

  return { init, addTab, closeTab, activateTab, hasTab, activeTabId,
           getTabInfo, lockTab, unlockTab, canReplaceTab, replaceTab,
           switchTabByOffset, switchTabByIndex, getTabIframe, reloadAllTabs,
           findTabIdBySrc };

})();

window.WorkspaceEngine = WorkspaceEngine;
