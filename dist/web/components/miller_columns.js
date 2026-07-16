'use strict';

/**
 * MillerCentering — Miller Columns 居中滚动组件
 *
 * 全部手动计算 scrollLeft / scrollTop，不用 scrollIntoView，
 * 避免「元素已经可见就不滚动」的浏览器行为。
 */
class MillerCentering {

  constructor(opts = {}) {
    this._scrollContainer = opts.scrollContainer || null;
    this._getCardByGid    = opts.getCardByGid    || (() => null);
    this._childMap        = opts.childMap        || new Map();
    this._rowByGid        = opts.rowByGid        || new Map();
    this._depthByGid      = opts.depthByGid      || new Map(); // gid → tree depth
  }

  centerOnCard(activeGid) {
    const chain = this._buildChain(activeGid);
    if (chain.length === 0) return;

    const container = this._scrollContainer;
    if (!container) return;

    // 等一帧确保 DOM 稳定
    requestAnimationFrame(() => {
      // ── 收集所有唯一的列 ──
      const cols = [];
      const seen = new Set();
      for (const item of chain) {
        const card = this._getCardByGid(item.gid);
        if (!card) continue;
        const col = card.closest('.lv-col');
        if (col && !seen.has(col)) { seen.add(col); cols.push(col); }
      }
      if (cols.length === 0) return;

      // ── 水平：用 offsetLeft/offsetWidth 计算（不依赖 viewport 坐标）──
      const colOffsets = cols.map(c => ({ left: c.offsetLeft, right: c.offsetLeft + c.offsetWidth }));
      const minL = colOffsets[0].left;
      const maxR = colOffsets[colOffsets.length - 1].right;
      const hTarget = (minL + maxR) / 2 - (container.clientWidth / 2);
      container.scrollTo({ left: Math.max(0, hTarget), behavior: 'smooth' });

      // ── 垂直：用每个卡片的 getBoundingClientRect 计算 ──
      // （这里需要在水平滚动后立即读，所以先读 offset 再做垂直）
      for (const item of chain) {
        const card = this._getCardByGid(item.gid);
        if (!card) continue;
        const col = card.closest('.lv-col');
        if (!col) continue;
        const body = col.querySelector('.lv-col-body') || col;
        const cardRect = card.getBoundingClientRect();
        const bodyRect  = body.getBoundingClientRect();
        const relTop   = cardRect.top - bodyRect.top;
        const targetV  = body.scrollTop + relTop + (cardRect.height / 2) - (body.clientHeight / 2);
        body.scrollTo({ top: Math.max(0, targetV), behavior: 'smooth' });
      }
    });
  }

  _buildChain(activeGid) {
    // 这个方法的目的是收集所有需要居中的列所对应的卡片。
    // 不是只追第一个子节点，而是把所有级别都包含进来。
    //
    // 策略：从 activeGid 往上收集所有祖先卡片，
    //       往下找出 activeGid 子树内所有层级的第一个可见卡片（每级取一张）。
    const activeRow = this._rowByGid.get(activeGid);
    if (!activeRow) return [];
    const chain = [];

    // 1. 向上找到所有祖先
    const ancestors = [];
    let cur = activeRow;
    while (cur?.parent_bop_gid) {
      const parent = this._rowByGid.get(cur.parent_bop_gid);
      if (!parent) break;
      ancestors.unshift({ gid: parent.gid });
      cur = parent;
    }
    chain.push(...ancestors);

    // 2. 自身
    chain.push({ gid: activeGid });

    // 3. 向下找出所有深度的「代表卡片」
    //    遍历 activeGid 的所有后代，按树深度分组，每组取第一个有卡片的
    const activeDepth = this._depthByGid.get(activeGid) ?? 0;
    const descendantsByDepth = new Map();  // depth → first gid

    const walk = (gid) => {
      for (const kid of (this._childMap.get(gid) || [])) {
        const depth = this._depthByGid.get(kid.gid) ?? 0;
        if (depth > activeDepth && !descendantsByDepth.has(depth)) {
          descendantsByDepth.set(depth, kid.gid);
        }
        walk(kid.gid);
      }
    };
    walk(activeGid);

    // 按 depth 排序加入链
    const sortedDepths = [...descendantsByDepth.keys()].sort((a, b) => a - b);
    for (const depth of sortedDepths) {
      chain.push({ gid: descendantsByDepth.get(depth) });
    }

    return chain;
  }
}
