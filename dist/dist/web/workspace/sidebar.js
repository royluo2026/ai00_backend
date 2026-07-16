/**
 * SidebarManager — Tab 式左/右侧边栏
 *
 * 结构：
 *   .ws-sidebar
 *     .ws-sidebar-tab-bar
 *       .ws-sb-tab[data-leaf-id] × N
 *       .ws-sb-add-btn
 *     .ws-sidebar-leaf[data-leaf-id] × N   (active = 显示, 其余 display:none)
 *       iframe
 *     .ws-sidebar-drop-zone
 *     .ws-sidebar-resize-handle
 *
 * 公开 API：
 *   init()
 *   toggle(sideId)
 *   addLeaf(sideId, {title, src})   → leafId
 *   removeLeaf(sideId, leafId)
 *   activateLeaf(sideId, leafId)
 *   setDragTarget(sideId, active)
 *   renameLeaf(sideId, srcFragment, newTitle)
 */

'use strict';

const SidebarManager = (() => {

  // ── 可添加的面板预设 ──────────────────────────────────────────────────
  const PANEL_PRESETS = [
    { title: '内容树',  src: 'content_tree/index.html' },
    { title: '清单树',  src: 'components/list_tree.html' },
  ];

  // ── 状态 ─────────────────────────────────────────────────────────────
  const _sides = {
    left:  { id: 'left',  el: null, leavesEl: null, tabBarEl: null, leaves: [], activeId: null, width: 240, open: false },
    right: { id: 'right', el: null, leavesEl: null, tabBarEl: null, leaves: [], activeId: null, width: 240, open: false },
  };
  let _leafCounter = 1;
  let _isRestoring = false;

  // ── Init ─────────────────────────────────────────────────────────────
  function init() {
    for (const side of Object.values(_sides)) {
      side.el       = document.getElementById(`${side.id}-sidebar`);
      side.leavesEl = document.getElementById(`${side.id}-sidebar-leaves`);
      if (!side.el || !side.leavesEl) continue;

      // 插入 tab bar 到 leavesEl 最前面
      const tabBar = document.createElement('div');
      tabBar.className = 'ws-sidebar-tab-bar';
      side.tabBarEl = tabBar;

      // "+" 按钮
      const addBtn = document.createElement('button');
      addBtn.className = 'ws-sb-add-btn';
      addBtn.title = '添加面板';
      addBtn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>';
      addBtn.addEventListener('click', e => _showAddMenu(e, side.id));
      tabBar.appendChild(addBtn);

      side.leavesEl.insertBefore(tabBar, side.leavesEl.firstChild);

      _initResizeHandle(side);
      _initDropZone(side);
    }
    _restoreFromLocalStorage();
  }

  // ── Toggle / Open ─────────────────────────────────────────────────────
  function toggle(sideId) {
    const s = _sides[sideId];
    if (!s?.el) return;
    if (s.open) {
      s.open = false;
      s.el.classList.add('collapsed');
    } else {
      if (s.leaves.length === 0) return;
      s.open = true;
      s.el.classList.remove('collapsed');
    }
    localStorage.setItem(`ws.sidebar.${sideId}.open`, s.open ? 'true' : 'false');
    _updateToggleBtnState(sideId);
  }

  function _open(sideId) {
    const s = _sides[sideId];
    if (!s?.el || s.open) return;
    s.open = true;
    s.el.classList.remove('collapsed');
    localStorage.setItem(`ws.sidebar.${sideId}.open`, 'true');
    _updateToggleBtnState(sideId);
  }

  function _updateToggleBtnState(sideId) {
    const s = _sides[sideId];
    document.querySelectorAll(`[data-sidebar-toggle="${sideId}"]`).forEach(btn => {
      btn.classList.toggle('active', s.open);
    });
  }

  // ── Leaf 管理 ─────────────────────────────────────────────────────────
  function addLeaf(sideId, { title, src }) {
    const s = _sides[sideId];
    if (!s?.el) return null;

    // 去重（相同 src 复用，仅激活）
    const existing = s.leaves.find(l => l.src === src);
    if (existing) {
      activateLeaf(sideId, existing.id);
      if (!_isRestoring) _open(sideId);
      return existing.id;
    }

    const leafId = 'sb-leaf-' + (_leafCounter++);

    // ── Tab 标签
    const tab = document.createElement('div');
    tab.className = 'ws-sb-tab';
    tab.dataset.leafId = leafId;
    tab.title = title;

    const tabTitle = document.createElement('span');
    tabTitle.className = 'ws-sb-tab-title';
    tabTitle.textContent = title;

    const closeBtn = document.createElement('button');
    closeBtn.className = 'ws-sb-tab-close';
    closeBtn.title = '关闭';
    closeBtn.innerHTML = '<svg width="9" height="9" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="2"><line x1="1" y1="1" x2="11" y2="11"/><line x1="11" y1="1" x2="1" y2="11"/></svg>';
    closeBtn.addEventListener('click', e => { e.stopPropagation(); removeLeaf(sideId, leafId); });

    tab.appendChild(tabTitle);
    tab.appendChild(closeBtn);
    tab.addEventListener('click', () => activateLeaf(sideId, leafId));
    tab.addEventListener('contextmenu', e => { e.preventDefault(); _showTabCtxMenu(e, sideId, leafId); });

    // 插在 addBtn 前
    s.tabBarEl.insertBefore(tab, s.tabBarEl.querySelector('.ws-sb-add-btn'));

    // ── Leaf 内容（iframe）
    const leafEl = document.createElement('div');
    leafEl.className = 'ws-sidebar-leaf';
    leafEl.dataset.leafId = leafId;
    leafEl.style.display = 'none';

    const iframe = document.createElement('iframe');
    iframe.src   = src;
    iframe.title = title;
    iframe.allow = 'clipboard-read; clipboard-write';
    iframe.addEventListener('load', () => {
      const theme = document.documentElement.getAttribute('data-theme') || 'dark';
      try { iframe.contentWindow?.postMessage({ type: 'theme', theme }, '*'); } catch (_) {}
    });
    leafEl.appendChild(iframe);

    // 追加到 leavesEl 末尾（tab bar 之后）
    s.leavesEl.appendChild(leafEl);

    const leaf = { id: leafId, title, src, tabEl: tab, leafEl, iframeEl: iframe };
    s.leaves.push(leaf);

    activateLeaf(sideId, leafId);
    if (!_isRestoring) _open(sideId);
    _saveLeaves(sideId);
    return leafId;
  }

  function removeLeaf(sideId, leafId) {
    const s = _sides[sideId];
    if (!s) return;
    const idx = s.leaves.findIndex(l => l.id === leafId);
    if (idx < 0) return;
    const leaf = s.leaves[idx];

    leaf.tabEl.remove();
    leaf.leafEl.remove();
    s.leaves.splice(idx, 1);

    if (s.leaves.length === 0) {
      s.activeId = null;
      s.open = false;
      s.el.classList.add('collapsed');
      localStorage.setItem(`ws.sidebar.${sideId}.open`, 'false');
      _updateToggleBtnState(sideId);
    } else {
      // 激活相邻的叶
      const nextIdx = Math.min(idx, s.leaves.length - 1);
      activateLeaf(sideId, s.leaves[nextIdx].id);
    }
    _saveLeaves(sideId);
  }

  function activateLeaf(sideId, leafId) {
    const s = _sides[sideId];
    if (!s) return;
    s.activeId = leafId;

    s.leaves.forEach(l => {
      const isActive = l.id === leafId;
      l.leafEl.style.display = isActive ? 'flex' : 'none';
      l.tabEl.classList.toggle('active', isActive);
    });

    localStorage.setItem(`ws.sidebar.${sideId}.active`, leafId);
  }

  // ── Drag Target ───────────────────────────────────────────────────────
  function setDragTarget(sideId, active) {
    const s = _sides[sideId];
    if (!s?.el) return;
    s.el.classList.toggle('ws-drag-target', active);
  }

  // ── Drop 处理 ─────────────────────────────────────────────────────────
  function _onDrop(sideId, e) {
    e.preventDefault();
    e.stopPropagation();
    setDragTarget(sideId, false);
    const tabId = e.dataTransfer.getData('text/plain');
    if (!tabId) return;
    const info = window.WorkspaceEngine?.getTabInfo?.(tabId);
    if (!info?.src) return;
    window.WorkspaceEngine.closeTab(tabId);
    addLeaf(sideId, { title: info.title, src: info.src });
  }

  // ── 添加面板菜单 ──────────────────────────────────────────────────────
  function _showAddMenu(e, sideId) {
    const existing = document.getElementById('ws-sb-add-menu');
    if (existing) existing.remove();

    const menu = document.createElement('div');
    menu.id = 'ws-sb-add-menu';
    menu.className = 'ws-sb-add-menu';

    PANEL_PRESETS.forEach(p => {
      const item = document.createElement('div');
      item.className = 'ws-sb-add-menu-item';
      item.textContent = p.title;
      item.addEventListener('click', () => {
        menu.remove();
        addLeaf(sideId, { title: p.title, src: p.src });
      });
      menu.appendChild(item);
    });

    document.body.appendChild(menu);

    // 定位在按钮下方
    const rect = e.currentTarget.getBoundingClientRect();
    let x = rect.left, y = rect.bottom + 4;
    if (x + 160 > window.innerWidth) x = window.innerWidth - 165;
    menu.style.left = x + 'px';
    menu.style.top  = y + 'px';

    setTimeout(() => {
      document.addEventListener('mousedown', function close(ev) {
        if (!menu.contains(ev.target)) { menu.remove(); document.removeEventListener('mousedown', close); }
      });
    }, 10);
  }

  // ── Tab 右键菜单 ─────────────────────────────────────────────────────
  function _showTabCtxMenu(e, sideId, leafId) {
    const existing = document.getElementById('ws-sb-ctx-menu');
    if (existing) existing.remove();

    const menu = document.createElement('div');
    menu.id = 'ws-sb-ctx-menu';
    menu.className = 'ws-sb-add-menu';

    const otherSide = sideId === 'left' ? 'right' : 'left';
    const s = _sides[sideId];
    const leaf = s.leaves.find(l => l.id === leafId);
    if (!leaf) return;

    const items = [
      { label: '重命名', action: () => _renameLeafById(sideId, leafId) },
      null,
      { label: `移到${otherSide === 'left' ? '左' : '右'}侧边栏`, action: () => {
          const { title, src } = leaf;
          removeLeaf(sideId, leafId);
          addLeaf(otherSide, { title, src });
      }},
      null,
      { label: '关闭', action: () => removeLeaf(sideId, leafId), danger: true },
    ];

    items.forEach(it => {
      if (it === null) {
        const sep = document.createElement('div');
        sep.className = 'ws-sb-add-menu-sep';
        menu.appendChild(sep);
        return;
      }
      const item = document.createElement('div');
      item.className = 'ws-sb-add-menu-item' + (it.danger ? ' danger' : '');
      item.textContent = it.label;
      item.addEventListener('click', () => { menu.remove(); it.action(); });
      menu.appendChild(item);
    });

    document.body.appendChild(menu);

    let x = e.clientX, y = e.clientY;
    if (x + 165 > window.innerWidth) x = window.innerWidth - 170;
    menu.style.left = x + 'px';
    menu.style.top  = y + 'px';

    setTimeout(() => {
      document.addEventListener('mousedown', function close(ev) {
        if (!menu.contains(ev.target)) { menu.remove(); document.removeEventListener('mousedown', close); }
      });
    }, 10);
  }

  // ── 宽度调整 Handle ──────────────────────────────────────────────────
  function _initResizeHandle(side) {
    const handle = side.el.querySelector('.ws-sidebar-resize-handle');
    if (!handle) return;
    let startX, startWidth;
    handle.addEventListener('mousedown', e => {
      e.preventDefault();
      startX     = e.clientX;
      startWidth = side.el.getBoundingClientRect().width;
      side.width = startWidth;
      side.el.style.transition = 'none';
      document.querySelectorAll('iframe').forEach(f => { f.style.pointerEvents = 'none'; });
      handle.classList.add('dragging');

      const onMove = mv => {
        const delta = side.id === 'left' ? mv.clientX - startX : startX - mv.clientX;
        side.width = Math.max(160, Math.min(480, startWidth + delta));
        side.el.style.width = side.width + 'px';
      };
      const onUp = () => {
        handle.classList.remove('dragging');
        side.el.style.transition = '';
        document.querySelectorAll('iframe').forEach(f => { f.style.pointerEvents = ''; });
        localStorage.setItem(`ws.sidebar.${side.id}.width`, String(Math.round(side.width)));
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
      };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    });
  }

  // ── Drop Zone ─────────────────────────────────────────────────────────
  function _initDropZone(side) {
    const dz = side.el.querySelector('.ws-sidebar-drop-zone');
    if (!dz) return;
    dz.addEventListener('dragover',  e => e.preventDefault());
    dz.addEventListener('dragenter', e => { e.preventDefault(); dz.classList.add('ws-dz-active'); });
    dz.addEventListener('dragleave', () => dz.classList.remove('ws-dz-active'));
    dz.addEventListener('drop', e => { dz.classList.remove('ws-dz-active'); _onDrop(side.id, e); });
  }

  // ── 持久化 ───────────────────────────────────────────────────────────
  function _saveLeaves(sideId) {
    const s = _sides[sideId];
    const data = s.leaves.map(l => ({ title: l.title, src: l.src }));
    localStorage.setItem(`ws.sidebar.${sideId}.leaves`, JSON.stringify(data));
  }

  function renameLeaf(sideId, srcFragment, newTitle) {
    const s = _sides[sideId];
    if (!s) return;
    const leaf = s.leaves.find(l => l.src.includes(srcFragment));
    if (!leaf) return;
    leaf.title = newTitle;
    leaf.tabEl.querySelector('.ws-sb-tab-title').textContent = newTitle;
    leaf.tabEl.title = newTitle;
    _saveLeaves(sideId);
  }

  function _renameLeafById(sideId, leafId) {
    const s = _sides[sideId];
    const leaf = s?.leaves.find(l => l.id === leafId);
    if (!leaf) return;
    const titleEl = leaf.tabEl.querySelector('.ws-sb-tab-title');
    const input = document.createElement('input');
    input.value = leaf.title;
    input.style.cssText = 'width:80px;background:var(--bg-tertiary,#313244);border:1px solid var(--color-primary,#89b4fa);border-radius:3px;color:inherit;font-size:11px;padding:1px 4px;outline:none;';
    titleEl.replaceWith(input);
    input.focus(); input.select();
    const done = () => {
      const v = input.value.trim();
      if (v) { leaf.title = v; _saveLeaves(sideId); }
      const span = document.createElement('span');
      span.className = 'ws-sb-tab-title';
      span.textContent = leaf.title;
      input.replaceWith(span);
      leaf.tabEl.title = leaf.title;
    };
    input.addEventListener('blur', done);
    input.addEventListener('keydown', e => { if (e.key === 'Enter') input.blur(); if (e.key === 'Escape') { input.value = leaf.title; input.blur(); } });
  }

  function _restoreFromLocalStorage() {
    _isRestoring = true;
    for (const sideId of ['left', 'right']) {
      const s = _sides[sideId];
      if (!s.el) continue;

      // 恢复宽度
      const rawW = localStorage.getItem(`ws.sidebar.${sideId}.width`);
      const w = rawW ? parseInt(rawW, 10) : 240;
      s.width = isNaN(w) ? 240 : Math.max(160, Math.min(480, w));
      s.el.style.width = s.width + 'px';

      // 恢复 leaves
      try {
        const leaves = JSON.parse(localStorage.getItem(`ws.sidebar.${sideId}.leaves`) || '[]');
        if (Array.isArray(leaves)) leaves.forEach(l => addLeaf(sideId, l));
      } catch (_) {}

      // 恢复激活的 leaf
      const savedActive = localStorage.getItem(`ws.sidebar.${sideId}.active`);
      if (savedActive) {
        const leaf = s.leaves.find(l => l.id === savedActive);
        if (leaf) activateLeaf(sideId, leaf.id);
      } else if (s.leaves.length > 0) {
        activateLeaf(sideId, s.leaves[0].id);
      }

      // 恢复展开状态
      const wasOpen = localStorage.getItem(`ws.sidebar.${sideId}.open`) === 'true';
      if (wasOpen && s.leaves.length > 0) {
        s.open = true;
        s.el.classList.remove('collapsed');
      } else {
        s.open = false;
        s.el.classList.add('collapsed');
      }
      _updateToggleBtnState(sideId);
    }
    _isRestoring = false;
  }

  // ── 公开 API ─────────────────────────────────────────────────────────
  return { init, toggle, addLeaf, removeLeaf, activateLeaf, setDragTarget, renameLeaf };

})();

window.SidebarManager = SidebarManager;
