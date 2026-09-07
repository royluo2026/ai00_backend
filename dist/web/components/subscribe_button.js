/**
 * web/components/subscribe_button.js
 * ────────────────────────────────────
 * 通用订阅/关注按钮组件
 *
 * 使用方式：
 *   // 渲染 HTML（在 cellRenderer / 静态 HTML 中）
 *   SubscribeButton.html(gid, followed, title, itemType)
 *
 *   // 点击事件委托
 *   container.addEventListener('click', ev => {
 *     const btn = ev.target.closest('.sub-btn');
 *     if (btn) SubscribeButton.open(btn, { ...state });
 *   });
 *
 *   // 打开面板（也可用于非委托场景）
 *   SubscribeButton.open(anchorEl, {
 *     itemType, itemGid, itemTitle,
 *     followed, followGid, conditions,
 *     cf,           // cloudFetch 函数
 *     onSave,       // (newState: { followed, followGid, conditions }) => void
 *   });
 */
(function () {
  'use strict';

  const CONDITIONS = [
    { key: 'any_change',     label: '任何更新' },
    { key: 'status_change',  label: '状态变更' },
    { key: 'comment_added',  label: '新评论' },
    { key: 'resolved',       label: '已解决/关闭' },
    { key: 'assigned_to_me', label: '分配给我' },
    { key: 'mentioned',      label: '@提及我' },
  ];

  const DEFAULT_CONDITIONS = ['status_change', 'resolved'];

  // ── SVG 铃铛图标（filled & outline）───────────────────────────────────────
  function _bellSvg(filled) {
    return filled
      ? `<svg width="13" height="13" viewBox="0 0 16 16" fill="currentColor" xmlns="http://www.w3.org/2000/svg"><path d="M8 1a5 5 0 0 1 5 5v2.5l1.5 2H1.5L3 8.5V6a5 5 0 0 1 5-5zm0 14a2 2 0 0 1-2-2h4a2 2 0 0 1-2 2z"/></svg>`
      : `<svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" xmlns="http://www.w3.org/2000/svg"><path d="M8 1a5 5 0 0 1 5 5v2.5l1.5 2H1.5L3 8.5V6a5 5 0 0 1 5-5z"/><path d="M6 14a2 2 0 0 0 4 0"/></svg>`;
  }

  // ── 面板 DOM（单例）──────────────────────────────────────────────────────
  let _panel = null;
  let _backdrop = null;
  let _ctx = null;   // current open context

  function _ensurePanel() {
    if (_panel) return;

    _backdrop = document.createElement('div');
    _backdrop.className = 'sub-backdrop';
    _backdrop.addEventListener('click', () => SubscribeButton.close());

    _panel = document.createElement('div');
    _panel.className = 'sub-panel';
    _panel.addEventListener('click', e => e.stopPropagation());

    document.body.appendChild(_backdrop);
    document.body.appendChild(_panel);
  }

  function _render() {
    if (!_ctx) return;
    const { itemTitle, followed, conditions } = _ctx;
    const checks = conditions.length ? conditions : DEFAULT_CONDITIONS;

    const condHtml = CONDITIONS.map(c => `
      <label class="sub-cond-item">
        <input type="checkbox" class="sub-cond-chk" value="${c.key}"
          ${checks.includes(c.key) ? 'checked' : ''}
        > ${c.label}
      </label>
    `).join('');

    const headerLabel = itemTitle ? `<span class="sub-panel-title" title="${_esc(itemTitle)}">${_esc(itemTitle.length > 20 ? itemTitle.slice(0, 20) + '…' : itemTitle)}</span>` : '';

    _panel.innerHTML = `
      <div class="sub-panel-head">
        <span class="sub-panel-icon">${_bellSvg(followed)}</span>
        ${headerLabel}
        <button class="sub-close-btn" id="subCloseBtn" title="关闭">
          <svg width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.8" xmlns="http://www.w3.org/2000/svg"><line x1="1" y1="1" x2="11" y2="11"/><line x1="11" y1="1" x2="1" y2="11"/></svg>
        </button>
      </div>
      <div class="sub-panel-sec">通知条件</div>
      <div class="sub-cond-list">${condHtml}</div>
      <div class="sub-panel-footer">
        ${followed
          ? `<button class="sub-btn-unfollow" id="subUnfollowBtn">取消关注</button>`
          : ''}
        <button class="sub-btn-save" id="subSaveBtn">${followed ? '保存' : '关注'}</button>
      </div>
    `;

    _panel.querySelector('#subCloseBtn').onclick = () => SubscribeButton.close();
    _panel.querySelector('#subSaveBtn').onclick = () => _onSave();
    const uf = _panel.querySelector('#subUnfollowBtn');
    if (uf) uf.onclick = () => _onUnfollow();
  }

  async function _onSave() {
    if (!_ctx) return;
    const checks = [..._panel.querySelectorAll('.sub-cond-chk:checked')].map(c => c.value);
    const { itemType, itemGid, itemTitle, followed, followGid, cf: _cloudFetch, onSave } = _ctx;

    _setLoading(true);
    try {
      if (followed && followGid) {
        // 更新条件
        await _cloudFetch(`/api/follows/${followGid}`, {
          method: 'PATCH',
          body: JSON.stringify({ notify_on: checks }),
        });
        onSave({ followed: true, followGid, conditions: checks });
      } else {
        // 新建关注
        const res = await _cloudFetch('/api/follows', {
          method: 'POST',
          body: JSON.stringify({ item_type: itemType, item_gid: itemGid, item_title: itemTitle, notify_on: checks }),
        });
        const newGid = res?.data?.gid || null;
        onSave({ followed: true, followGid: newGid, conditions: checks });
      }
      SubscribeButton.close();
    } catch (err) {
      console.warn('[subscribe_button] save failed', err);
    } finally {
      _setLoading(false);
    }
  }

  async function _onUnfollow() {
    if (!_ctx) return;
    const { followGid, cf: _cloudFetch, onSave } = _ctx;
    if (!followGid) { SubscribeButton.close(); return; }

    _setLoading(true);
    try {
      await _cloudFetch(`/api/follows/${followGid}`, { method: 'DELETE' });
      onSave({ followed: false, followGid: null, conditions: [] });
      SubscribeButton.close();
    } catch (err) {
      console.warn('[subscribe_button] unfollow failed', err);
    } finally {
      _setLoading(false);
    }
  }

  function _setLoading(v) {
    _panel.querySelectorAll('button').forEach(b => b.disabled = v);
  }

  function _position(anchorEl) {
    const rect = anchorEl.getBoundingClientRect();
    const panelW = 200;
    const panelH = 280;
    let left = rect.right + 6;
    let top  = rect.top;

    if (left + panelW > window.innerWidth - 8) left = rect.left - panelW - 6;
    if (top + panelH > window.innerHeight - 8)  top  = window.innerHeight - panelH - 8;
    if (top < 8) top = 8;

    _panel.style.left = left + 'px';
    _panel.style.top  = top  + 'px';
  }

  function _esc(s) {
    return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  // ── 公共 API ──────────────────────────────────────────────────────────────
  const SubscribeButton = {
    /**
     * 渲染按钮 HTML（用于 cellRenderer / innerHTML）
     * @param {string}   gid      - item gid（存在 data-gid 上）
     * @param {boolean}  followed
     * @param {string}   title
     * @param {string}   itemType
     */
    html(gid, followed, title, itemType) {
      return `<button class="sub-btn${followed ? ' sub-followed' : ''}" data-gid="${_esc(gid)}" data-title="${_esc(title)}" data-itype="${_esc(itemType)}" title="${followed ? '订阅中 — 点击修改' : '关注/订阅'}">${_bellSvg(followed)}</button>`;
    },

    /**
     * 打开订阅面板
     * @param {HTMLElement} anchorEl  - 触发按钮元素（用于定位）
     * @param {Object}      opts
     *   - itemType, itemGid, itemTitle
     *   - followed {boolean}
     *   - followGid {string|null}
     *   - conditions {string[]}
     *   - cf {function}    cloudFetch(url, init) → Promise<any>
     *   - onSave {function}  ({ followed, followGid, conditions }) => void
     */
    open(anchorEl, opts) {
      _ensurePanel();
      _ctx = { ...opts };
      _ctx.conditions = _ctx.conditions || [];
      _render();
      _position(anchorEl);
      _panel.classList.add('sub-panel-visible');
      _backdrop.classList.add('sub-panel-visible');
    },

    close() {
      if (!_panel) return;
      _panel.classList.remove('sub-panel-visible');
      _backdrop.classList.remove('sub-panel-visible');
      _ctx = null;
    },
  };

  window.SubscribeButton = SubscribeButton;
})();

