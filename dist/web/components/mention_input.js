/**
 * web/components/mention_input.js
 * ────────────────────────────────
 * @mention 输入增强组件
 *
 * 用法：
 *   const mi = new MentionInput({
 *     containerEl,   // 挂载容器（组件在其中创建 textarea）
 *     placeholder,   // textarea placeholder（默认"描述…"）
 *     rows,          // textarea 行数（默认 3）
 *     cf,            // cloudFetch(url, init)→Promise；本地模式传 null 禁用 @ 搜索
 *     onChange,      // (text) => void，文字变化时回调（可选）
 *   });
 *
 *   mi.getValue()     // 原始文本（@DisplayName 保持不变）
 *   mi.getMentions()  // [{user_gid, name}] 去重后的有效提及列表
 *   mi.setValue(str)  // 设置初始值（不触发 onChange）
 *   mi.focus()
 *   mi.destroy()
 *
 * 文本格式：纯文本，@ 选人后插入 `@显示名 `（空格结尾）。
 * getMentions() 通过检查文本中是否仍含 `@name` 来过滤已删除的提及。
 */
(function () {
  'use strict';

  // ── 全局单例下拉层 ──────────────────────────────────────────────────────────
  let _drop = null;          // 下拉 DOM
  let _currentMI = null;     // 当前激活的 MentionInput 实例
  let _dropTimer = null;

  function _ensureDrop() {
    if (_drop) return;
    _drop = document.createElement('div');
    _drop.className = 'mi-drop';
    _drop.addEventListener('mousedown', e => e.preventDefault()); // 防止 textarea 失焦
    document.body.appendChild(_drop);
  }

  function _hideDrop() {
    if (_drop) {
      _drop.innerHTML = '';
      _drop.style.display = 'none';
    }
    _currentMI = null;
  }

  // ── MentionInput 类 ────────────────────────────────────────────────────────
  class MentionInput {
    constructor(opts = {}) {
      this._cf          = opts.cf || null;
      this._onChange    = opts.onChange || null;
      this._mentions    = [];   // [{user_gid, name}]
      this._atStart     = -1;   // 当前 @ 触发点在 textarea 中的索引
      this._searching   = false;

      // 创建 wrapper + textarea
      this._wrap = document.createElement('div');
      this._wrap.className = 'mi-wrap';

      this._ta = document.createElement('textarea');
      this._ta.className = 'mi-textarea';
      this._ta.placeholder = opts.placeholder || '描述…';
      this._ta.rows = opts.rows || 3;
      this._ta.spellcheck = false;

      this._wrap.appendChild(this._ta);
      if (opts.containerEl) opts.containerEl.appendChild(this._wrap);

      this._bindEvents();
    }

    // ── 公共 API ────────────────────────────────────────────────────────────

    getValue() { return this._ta.value; }

    getMentions() {
      const text = this._ta.value;
      return this._mentions.filter(m => text.includes('@' + m.name));
    }

    setValue(v) { this._ta.value = v || ''; }

    focus() { this._ta.focus(); }

    destroy() {
      this._ta.removeEventListener('input',   this._onInput);
      this._ta.removeEventListener('keydown', this._onKeydown);
      this._ta.removeEventListener('blur',    this._onBlur);
      if (this._wrap.parentNode) this._wrap.parentNode.removeChild(this._wrap);
      if (_currentMI === this) _hideDrop();
    }

    // ── 内部事件 ────────────────────────────────────────────────────────────

    _bindEvents() {
      this._onInput   = this._handleInput.bind(this);
      this._onKeydown = this._handleKeydown.bind(this);
      this._onBlur    = () => { setTimeout(_hideDrop, 150); };

      this._ta.addEventListener('input',   this._onInput);
      this._ta.addEventListener('keydown', this._onKeydown);
      this._ta.addEventListener('blur',    this._onBlur);
    }

    _handleInput() {
      if (this._onChange) this._onChange(this._ta.value);
      if (!this._cf) return;   // 本地模式，不搜索

      const pos  = this._ta.selectionStart;
      const text = this._ta.value.slice(0, pos);
      const atIdx = text.lastIndexOf('@');

      if (atIdx === -1) { _hideDrop(); return; }

      // @ 之前必须是空格/换行/行首
      const before = text[atIdx - 1];
      if (atIdx > 0 && before !== ' ' && before !== '\n') { _hideDrop(); return; }

      const query = text.slice(atIdx + 1);
      // 如果 query 含空格说明 @ 已结束
      if (query.includes(' ') || query.includes('\n')) { _hideDrop(); return; }

      this._atStart = atIdx;
      _currentMI = this;
      this._search(query);
    }

    _handleKeydown(e) {
      if (!_currentMI || _currentMI !== this || !_drop || _drop.style.display === 'none') return;

      const items = _drop.querySelectorAll('.mi-drop-item');
      const active = _drop.querySelector('.mi-drop-item.active');

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        const next = active ? (active.nextElementSibling || items[0]) : items[0];
        active?.classList.remove('active');
        next?.classList.add('active');
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        const prev = active ? (active.previousElementSibling || items[items.length - 1]) : items[items.length - 1];
        active?.classList.remove('active');
        prev?.classList.add('active');
      } else if (e.key === 'Enter' || e.key === 'Tab') {
        if (active) {
          e.preventDefault();
          this._selectUser(active.dataset.gid, active.dataset.name);
        }
      } else if (e.key === 'Escape') {
        _hideDrop();
      }
    }

    // ── 搜索 ────────────────────────────────────────────────────────────────

    _search(q) {
      clearTimeout(_dropTimer);
      _dropTimer = setTimeout(() => this._doSearch(q), 180);
    }

    async _doSearch(q) {
      if (!this._cf) return;
      _ensureDrop();
      try {
        const res = await this._cf(`/users/search?q=${encodeURIComponent(q)}&limit=8`);
        if (_currentMI !== this) return;   // 已被其他实例接管
        const users = res?.data || [];
        this._showDrop(users);
      } catch (_) {
        _hideDrop();
      }
    }

    _showDrop(users) {
      _ensureDrop();
      if (!users.length) { _hideDrop(); return; }

      _drop.innerHTML = users.map(u => `
        <div class="mi-drop-item" data-gid="${_esc(u.gid)}" data-name="${_esc(u.name)}">
          ${u.avatar_url
            ? `<img class="mi-drop-avatar mi-drop-avatar-img" src="${_esc(u.avatar_url)}" alt="${_esc((u.name||'?')[0])}" onerror="this.outerHTML='<span class=\\'mi-drop-avatar\\'>${_esc((u.name||'?')[0].toUpperCase())}</span>'">`
            : `<span class="mi-drop-avatar">${_esc((u.name || '?')[0].toUpperCase())}</span>`}
          <span class="mi-drop-name">${_esc(u.name)}</span>
          ${u.email ? `<span class="mi-drop-email">${_esc(u.email)}</span>` : ''}
        </div>
      `).join('');

      // 第一项默认高亮
      _drop.querySelector('.mi-drop-item')?.classList.add('active');

      // 点击选择
      _drop.querySelectorAll('.mi-drop-item').forEach(el => {
        el.addEventListener('mousedown', e => {
          e.preventDefault();
          this._selectUser(el.dataset.gid, el.dataset.name);
        });
      });

      // 定位（textarea 下方）
      const rect = this._ta.getBoundingClientRect();
      const dropH = Math.min(users.length * 40 + 8, 200);
      let top = rect.bottom + 4;
      if (top + dropH > window.innerHeight - 8) top = rect.top - dropH - 4;
      _drop.style.left    = `${rect.left}px`;
      _drop.style.top     = `${top}px`;
      _drop.style.width   = `${Math.max(rect.width, 200)}px`;
      _drop.style.display = 'block';
    }

    _selectUser(gid, name) {
      _hideDrop();
      if (this._atStart < 0) return;

      const before = this._ta.value.slice(0, this._atStart);
      const after  = this._ta.value.slice(this._ta.selectionStart);
      const insert = `@${name} `;
      this._ta.value = before + insert + after;

      // 移动光标到插入点后
      const newPos = this._atStart + insert.length;
      this._ta.setSelectionRange(newPos, newPos);
      this._ta.focus();

      // 记录提及（去重）
      if (!this._mentions.some(m => m.user_gid === gid)) {
        this._mentions.push({ user_gid: gid, name });
      }
      this._atStart = -1;
      if (this._onChange) this._onChange(this._ta.value);
    }
  }

  function _esc(s) {
    return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  // 点击页面其他地方关闭下拉
  document.addEventListener('click', e => {
    if (!_drop || _drop.style.display === 'none') return;
    if (!_drop.contains(e.target)) _hideDrop();
  });

  window.MentionInput = MentionInput;
})();

