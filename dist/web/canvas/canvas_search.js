'use strict';
/**
 * CanvasSearch — 画布全局搜索
 *
 * 在所有卡片的标题和内容文本中搜索关键词：
 *   - 高亮匹配卡片（金色边框）
 *   - 淡化非匹配卡片
 *   - 上一个/下一个导航（pan 使目标居中）
 *   - 渲染搜索框到指定容器
 */
class CanvasSearch {
  constructor(shell) {
    this._shell   = shell;   // CanvasShell 实例
    this._matches = [];      // 匹配的 cardId[]
    this._cursor  = -1;      // 当前高亮索引
    this._keyword = '';
    this._active  = false;
  }

  // ── 渲染搜索框 ─────────────────────────────────────────────────────────────
  renderSearchBar(containerEl) {
    containerEl.innerHTML = `
      <div class="cs-search-wrap" id="csSearchWrap">
        <svg class="icon" width="12" height="12" style="color:var(--text-faint);flex-shrink:0">
          <use href="#icon-note"/>
        </svg>
        <input class="cs-search-input" id="csSearchInput"
          type="text" placeholder="搜索画布…" autocomplete="off">
        <div class="cs-search-nav hidden" id="csSearchNav">
          <span id="csSearchCount" style="min-width:28px;text-align:center">0/0</span>
          <button class="cs-search-nav-btn" id="csSearchPrev" title="上一个">↑</button>
          <button class="cs-search-nav-btn" id="csSearchNext" title="下一个">↓</button>
          <button class="cs-search-nav-btn" id="csSearchClear" title="清除">✕</button>
        </div>
      </div>
    `;

    const input   = containerEl.querySelector('#csSearchInput');
    const nav     = containerEl.querySelector('#csSearchNav');
    const countEl = containerEl.querySelector('#csSearchCount');
    const prevBtn = containerEl.querySelector('#csSearchPrev');
    const nextBtn = containerEl.querySelector('#csSearchNext');
    const clearBtn= containerEl.querySelector('#csSearchClear');

    let debounce = null;
    input.addEventListener('input', () => {
      clearTimeout(debounce);
      debounce = setTimeout(() => {
        this.search(input.value.trim());
        const hasResults = this._matches.length > 0;
        nav.classList.toggle('hidden', !input.value);
        if (input.value) this._updateCountLabel(countEl);
      }, 150);
    });

    input.addEventListener('keydown', e => {
      if (e.key === 'Enter')  { e.shiftKey ? this.prev() : this.next(); this._updateCountLabel(countEl); }
      if (e.key === 'Escape') { this.clear(); input.value = ''; nav.classList.add('hidden'); }
    });

    prevBtn.addEventListener('click', () => { this.prev(); this._updateCountLabel(countEl); });
    nextBtn.addEventListener('click', () => { this.next(); this._updateCountLabel(countEl); });
    clearBtn.addEventListener('click', () => {
      this.clear();
      input.value = '';
      nav.classList.add('hidden');
    });
  }

  _updateCountLabel(el) {
    if (!el) return;
    el.textContent = this._matches.length
      ? `${this._cursor + 1}/${this._matches.length}`
      : '无结果';
  }

  // ── 搜索 ──────────────────────────────────────────────────────────────────
  search(keyword) {
    this._keyword = keyword;
    this.clearHighlight();

    if (!keyword) return;

    const kw = keyword.toLowerCase();
    const matches = [];

    this._shell._cards.forEach((card, id) => {
      const text = [
        card.label || '',
        card.type  || '',
        JSON.stringify(card.config || {}),
      ].join(' ').toLowerCase();

      if (text.includes(kw)) matches.push(id);
    });

    this._matches = matches;
    this._cursor  = matches.length > 0 ? 0 : -1;
    this._applyHighlight();
    if (this._cursor >= 0) this.navigateTo(matches[0]);
    return matches;
  }

  // ── 导航 ──────────────────────────────────────────────────────────────────
  next() {
    if (!this._matches.length) return;
    this._cursor = (this._cursor + 1) % this._matches.length;
    this._applyHighlight();
    this.navigateTo(this._matches[this._cursor]);
  }

  prev() {
    if (!this._matches.length) return;
    this._cursor = (this._cursor - 1 + this._matches.length) % this._matches.length;
    this._applyHighlight();
    this.navigateTo(this._matches[this._cursor]);
  }

  navigateTo(cardId) {
    const cf = this._shell._cardFrames.get(cardId);
    if (!cf) return;

    // 计算卡片在 world 坐标中的中心
    const gs   = this._shell._gridSystem;
    const card = this._shell._cards.get(cardId);
    if (!card || !gs) return;

    const rect = gs.cellPixelRect(
      card.col_start || 1, card.row_start || 1,
      card.col_span  || 3, card.row_span  || 3,
    );
    const worldCX = rect.x + rect.w / 2;
    const worldCY = rect.y + rect.h / 2;

    const vp    = document.getElementById('csViewport');
    if (!vp) return;
    const vpW   = vp.clientWidth;
    const vpH   = vp.clientHeight;
    const zoom  = this._shell._zoom;

    // pan 使卡片中心落在视口中央
    this._shell._panX = vpW / 2 - worldCX * zoom;
    this._shell._panY = vpH / 2 - worldCY * zoom;
    this._shell._setTransform();
  }

  // ── 高亮 ──────────────────────────────────────────────────────────────────
  _applyHighlight() {
    const matchSet = new Set(this._matches);
    this._shell._cardFrames.forEach((cf, cardId) => {
      const isMatch   = matchSet.has(cardId);
      const isCurrent = this._matches[this._cursor] === cardId;
      cf.el.classList.toggle('cs-search-match', isCurrent);
      cf.el.classList.toggle('cs-search-dim',   !isMatch && this._matches.length > 0);
    });
  }

  clearHighlight() {
    this._shell._cardFrames.forEach(cf => {
      cf.el.classList.remove('cs-search-match', 'cs-search-dim');
    });
    this._matches = [];
    this._cursor  = -1;
  }

  clear() {
    this.clearHighlight();
    this._keyword = '';
  }
}

window.CanvasSearch = CanvasSearch;
