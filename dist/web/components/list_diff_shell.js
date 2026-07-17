/**
 * list_diff_shell.js — 通用三栏 diff 组件
 *
 * 用法：
 *   const shell = new ListDiffShell({ mountEl, baseTlsOpts, targetTlsOpts,
 *     matchKeyFn, cmpFields, fieldLabels, treeParentField, moduleId, extraChecks,
 *     onCompareComplete });
 *   await shell.init();
 *
 * 依赖：TreeListShell（tree_list_shell.js）
 */
'use strict';

// localStorage 账号隔离
function _ldiffLsk(base) {
  try { const u = window.parent?._authUser || window.top?._authUser || window._authUser; const g = u?.gid || u?.user_gid || ''; return g ? `${g}:${base}` : base; } catch { return base; }
}

class ListDiffShell {
  /**
   * @param {object} opts
   * @param {HTMLElement} opts.mountEl           — 挂载根元素
   * @param {object}      opts.baseTlsOpts       — Base TreeListShell 构造参数（不含 mountEl）
   * @param {object}      opts.targetTlsOpts     — Target TreeListShell 构造参数
   * @param {function}    opts.matchKeyFn        — (row)=>string 匹配键函数
   * @param {string[]}    opts.cmpFields         — 参与 diff 的字段名
   * @param {object}      [opts.fieldLabels]     — { field: '中文名' }
   * @param {string}      [opts.treeParentField] — 'parent_bom_row'|'parent_vpps'|'level'
   * @param {string}      [opts.baseWidth]       — 默认 '30%'
   * @param {string}      [opts.targetWidth]     — 默认 '50%'
   * @param {string}      [opts.resultWidth]     — 默认 '20%'
   * @param {string}      [opts.moduleId]        — localStorage key 前缀
   * @param {Array}       [opts.extraChecks]     — [{ label, title, run }]
   * @param {function}    [opts.onCompareComplete] — fn(result)
   */
  constructor(opts) {
    this._opts = opts;
    this._baseTLS    = null;
    this._targetTLS  = null;
    this._lastResult = null;
    this._compareActive = false;
    this._activeCheckIdx = -1;  // -1=none, >=0=extraCheck index

    // layout
    this._layoutEl = null;
    this._resultBodyEl = null;
  }

  /* ── 初始化 ──────────────────────────────────────────────── */
  async init() {
    const { mountEl, baseWidth = '30%', targetWidth = '50%', resultWidth = '20%',
            moduleId = 'lds' } = this._opts;

    mountEl.style.setProperty('--lds-base-width',   baseWidth);
    mountEl.style.setProperty('--lds-target-width', targetWidth);
    mountEl.style.setProperty('--lds-result-width', resultWidth);

    // 注入三栏布局
    mountEl.innerHTML = this._buildLayoutHTML(baseWidth, targetWidth, resultWidth);
    this._layoutEl    = mountEl.querySelector('.lds-layout');
    this._resultBodyEl = mountEl.querySelector('.lds-result-body');

    // 折叠 状态恢复
    this._initCollapseHandlers(moduleId);

    // 构建 extra check 按钮列表（merge 进 targetTlsOpts.extraToolbarBtns）
    const checkBtns = (this._opts.extraChecks || []).map((chk, idx) => ({
      html: this._buildCheckBtnHtml(chk.label),
      title: chk.title || chk.label,
      active: false,
      onClick: () => this._toggleCheck(idx),
    }));

    const compareBtnDef = {
      html: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 3h5v5"/><path d="M8 3H3v5"/><path d="M21 3l-7 7"/><path d="M3 3l7 7"/><path d="M16 21h5v-5"/><path d="M8 21H3v-5"/><path d="M21 21l-7-7"/><path d="M3 21l7-7"/></svg><span class="feat-label">对比base</span>',
      title: '对比 Base',
      active: false,
      onClick: () => this._toggleCompare(),
    };

    const extraBtns = [...checkBtns, compareBtnDef,
      ...(this._opts.targetTlsOpts?.extraToolbarBtns || [])];

    // Base TLS
    const baseSlot   = mountEl.querySelector('.lds-col-base .lds-tls-slot');
    this._baseTLS    = new TreeListShell({
      ...this._opts.baseTlsOpts,
      mountEl: baseSlot,
    });
    await this._baseTLS.init();

    // Target TLS
    const targetSlot = mountEl.querySelector('.lds-col-target .lds-tls-slot');
    this._targetTLS  = new TreeListShell({
      ...this._opts.targetTlsOpts,
      mountEl: targetSlot,
      extraToolbarBtns: extraBtns,
    });
    await this._targetTLS.init();
    this._refreshTargetBtns(); // 初始化按钮态（inactive）

    // 结论面板导出按钮
    mountEl.querySelector('#lds-btn-result-export')
      ?.addEventListener('click', () => this._onExportResult());

    this._renderDefaultResult();
  }

  /* ── 公开方法 ─────────────────────────────────────────────── */

  /** 执行 diff，返回结构化结果 */
  async runCompare() {
    this._compareActive = true;
    this._activeCheckIdx = -1;
    this._refreshTargetBtns();
    const result = this._computeDiff();
    this._lastResult = result;
    this._renderCompareResult(result);
    this._renderBaseOverlay(result);
    this._renderTargetFold(result);
    this._opts.onCompareComplete?.(result);
    return result;
  }

  /** 清除 diff 状态 */
  async clearCompare() {
    this._compareActive  = false;
    this._activeCheckIdx = -1;
    this._refreshTargetBtns();
    this._renderDefaultResult();
    await this._baseTLS?.refresh();
    await this._targetTLS?.refresh();
  }

  getLastResult() { return this._lastResult; }
  getBaseTLS()    { return this._baseTLS; }
  getTargetTLS()  { return this._targetTLS; }

  register(moduleId, cfg) {
    window.DataRegistry?.register(moduleId, cfg);
  }

  /* ── 内部：DOM 构建 ──────────────────────────────────────── */
  _buildLayoutHTML() {
    return `
<div class="lds-layout">
  <div class="lds-col-wrap lds-col-base">
    <button class="lds-collapse-btn" data-col="base" title="折叠/展开">
      <svg class="lds-chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
    </button>
    <div class="lds-collapse-label">${this._opts.baseTlsOpts?.title || 'Base'}</div>
    <div class="lds-tls-slot"></div>
  </div>

  <div class="lds-divider"></div>

  <div class="lds-col-wrap lds-col-target">
    <button class="lds-collapse-btn" data-col="target" title="折叠/展开">
      <svg class="lds-chevron" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
    </button>
    <div class="lds-collapse-label">${this._opts.targetTlsOpts?.title || 'Target'}</div>
    <div class="lds-tls-slot"></div>
  </div>

  <div class="lds-divider"></div>

  <div class="lds-col-result">
    <div class="lds-result-header">
      <span class="lds-result-title">对比结论</span>
      <button class="col-btn" id="lds-btn-result-export" title="导出结论">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
      </button>
    </div>
    <div class="lds-result-body"></div>
  </div>
</div>`;
  }

  _buildCheckBtnHtml(label) {
    return `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg><span class="feat-label">${label}</span>`;
  }

  /* ── 自动折叠 Base（extraCheck 启动时调用）──────────────── */
  _autoCollapseBase() {
    const moduleId = this._opts.moduleId || 'lds';
    const lsKey    = _ldiffLsk(`${moduleId}:col-collapse`);
    const baseWrap = this._layoutEl?.querySelector('.lds-col-base');
    if (baseWrap && !baseWrap.hasAttribute('data-collapsed')) {
      baseWrap.setAttribute('data-collapsed', '');
      const stored = JSON.parse(localStorage.getItem(lsKey) || '{}');
      stored['base'] = true;
      localStorage.setItem(lsKey, JSON.stringify(stored));
    }
  }

  /* ── 折叠 ────────────────────────────────────────────────── */
  _initCollapseHandlers(moduleId) {
    const lsKey = _ldiffLsk(`${moduleId}:col-collapse`);
    const stored = JSON.parse(localStorage.getItem(lsKey) || '{}');
    const layout = this._layoutEl;
    ['base', 'target'].forEach(col => {
      const wrap = layout.querySelector(`.lds-col-${col}`);
      if (!wrap) return;
      if (stored[col]) wrap.setAttribute('data-collapsed', '');
      wrap.querySelector('.lds-collapse-btn')?.addEventListener('click', () => {
        if (wrap.hasAttribute('data-collapsed')) {
          wrap.removeAttribute('data-collapsed');
          stored[col] = false;
        } else {
          wrap.setAttribute('data-collapsed', '');
          stored[col] = true;
        }
        localStorage.setItem(lsKey, JSON.stringify(stored));
      });
    });
  }

  /* ── 按钮刷新 ────────────────────────────────────────────── */
  _refreshTargetBtns() {
    if (!this._targetTLS) return;
    const { extraChecks = [] } = this._opts;
    const checkBtns = extraChecks.map((chk, idx) => ({
      html: this._buildCheckBtnHtml(chk.label),
      title: chk.title || chk.label,
      active: this._activeCheckIdx === idx,
      onClick: () => this._toggleCheck(idx),
    }));
    const compareBtnDef = {
      html: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 3h5v5"/><path d="M8 3H3v5"/><path d="M21 3l-7 7"/><path d="M3 3l7 7"/><path d="M16 21h5v-5"/><path d="M8 21H3v-5"/><path d="M21 21l-7-7"/><path d="M3 21l7-7"/></svg><span class="feat-label">对比base</span>',
      title: '对比 Base',
      active: this._compareActive,
      onClick: () => this._toggleCompare(),
    };
    const staticBtns = this._opts.targetTlsOpts?.extraToolbarBtns || [];
    this._targetTLS.updateExtraButtons([...checkBtns, compareBtnDef, ...staticBtns]);
  }

  /* ── toggle 对比 / check ─────────────────────────────────── */
  async _toggleCompare() {
    if (this._compareActive) {
      await this.clearCompare();
    } else {
      this._activeCheckIdx = -1;
      await this.runCompare();
    }
  }

  async _toggleCheck(idx) {
    if (this._activeCheckIdx === idx) {
      // 关闭
      this._activeCheckIdx = -1;
      this._compareActive  = false;
      this._refreshTargetBtns();
      this._renderDefaultResult();
      await this._targetTLS?.refresh();
    } else {
      this._activeCheckIdx = idx;
      this._compareActive  = false;
      this._refreshTargetBtns();
      this._autoCollapseBase();   // 自动折叠 Base，让核对表格有更多空间
      const chk = this._opts.extraChecks[idx];
      if (!chk) return;
      const targetRows = this._targetTLS ? this._targetTLS.getRows() : [];
      const baseRows   = this._baseTLS   ? this._baseTLS.getRows()   : [];
      this._resultBodyEl.innerHTML = `<div class="col-empty">正在执行 ${chk.label}…</div>`;
      const checkResult = await chk.run(targetRows, baseRows);
      this._renderCheckResult(checkResult);
    }
  }

  async rerunCheck(idx) {
    const chk = this._opts.extraChecks?.[idx];
    if (!chk) return;
    const targetRows = this._targetTLS ? this._targetTLS.getRows() : [];
    const baseRows   = this._baseTLS   ? this._baseTLS.getRows()   : [];
    this._resultBodyEl.innerHTML = `<div class="col-empty">正在执行 ${chk.label}…</div>`;
    const checkResult = await chk.run(targetRows, baseRows);
    this._renderCheckResult(checkResult);
  }

  /* ── diff 算法 ───────────────────────────────────────────── */
  _computeDiff() {
    const { matchKeyFn, cmpFields = [] } = this._opts;
    const baseParts   = this._baseTLS   ? this._baseTLS.getRows()   : [];
    const targetParts = this._targetTLS ? this._targetTLS.getRows() : [];

    const baseMap   = new Map();
    const targetMap = new Map();

    { const cnt = new Map();
      baseParts.forEach(p => {
        let k = matchKeyFn(p);
        if (!k) return;
        const n = (cnt.get(k) || 0); cnt.set(k, n + 1);
        if (n > 0) k += '#' + n;
        p._cmpKey = k; baseMap.set(k, p);
      });
    }
    { const cnt = new Map();
      targetParts.forEach(p => {
        let k = matchKeyFn(p);
        if (!k) return;
        const n = (cnt.get(k) || 0); cnt.set(k, n + 1);
        if (n > 0) k += '#' + n;
        p._cmpKey = k; targetMap.set(k, p);
      });
    }

    const added = [], deleted = [], modified = [], same = [];
    const baseDiff   = new Map();
    const targetDiff = new Map();

    targetParts.forEach(p => {
      const k = p._cmpKey;
      if (!k || baseMap.has(k)) return;
      added.push(p); targetDiff.set(k, 'add');
    });
    baseParts.forEach(p => {
      const k = p._cmpKey;
      if (!k || targetMap.has(k)) return;
      deleted.push(p); baseDiff.set(k, 'del');
    });
    targetParts.forEach(p => {
      const k = p._cmpKey;
      if (!k) return;
      const bp = baseMap.get(k);
      if (!bp) return;
      const cf = this._diffRow(bp, p, cmpFields);
      if (cf.length) {
        modified.push({ base: bp, target: p, changedFields: cf });
        baseDiff.set(k, 'mod'); targetDiff.set(k, 'mod');
      } else {
        same.push(p);
      }
    });

    return { added, deleted, modified, same, baseDiff, targetDiff, baseParts, targetParts, sameCount: same.length };
  }

  _diffRow(base, target, fields) {
    const changes = [];
    for (const f of fields) {
      if (this._norm(base[f]) !== this._norm(target[f])) changes.push(f);
    }
    return changes;
  }

  _norm(v) {
    if (v === null || v === undefined) return '';
    if (typeof v === 'number') return String(parseFloat(v.toFixed(6)));
    const s = String(v).trim();
    if (s !== '' && !isNaN(Number(s))) return String(parseFloat(Number(s).toFixed(6)));
    return s;
  }

  /* ── 树形工具 ────────────────────────────────────────────── */
  _cmpNodeKey(p) {
    const { matchKeyFn } = this._opts;
    return (matchKeyFn(p) || p.gid || '').trim();
  }

  _cmpBuildTree(parts) {
    const parentField = this._opts.treeParentField || 'parent_vpps';
    if (parentField === 'level') {
      const roots = [], childrenMap = new Map(), stack = [];
      parts.forEach(p => {
        const lv = parseInt(p.level) || 1;
        while (stack.length && stack[stack.length-1].level >= lv) stack.pop();
        if (!stack.length) { roots.push(p); }
        else {
          const pk = this._cmpNodeKey(stack[stack.length-1].part);
          if (!childrenMap.has(pk)) childrenMap.set(pk, []);
          childrenMap.get(pk).push(p);
        }
        stack.push({ part: p, level: lv });
      });
      return { roots, childrenMap };
    }
    if (parentField === 'parent_bom_row') {
      const byBomRow = new Map();
      parts.forEach(p => {
        if (p.bom_row)       byBomRow.set(p.bom_row.trim(), p);
        if (p.bom_row_label) byBomRow.set(p.bom_row_label.trim(), p);
      });
      const roots = [], childrenMap = new Map();
      parts.forEach(p => {
        const pr = (p.parent_bom_row || '').trim();
        const parent = pr ? byBomRow.get(pr) : null;
        if (parent && parent !== p) {
          const pk = this._cmpNodeKey(parent);
          if (!childrenMap.has(pk)) childrenMap.set(pk, []);
          childrenMap.get(pk).push(p);
        } else {
          roots.push(p);
        }
      });
      return { roots, childrenMap };
    }
    // default: parent_vpps
    const byVpps = new Map();
    parts.forEach(p => { if (p.vpps) byVpps.set(p.vpps.trim(), p); });
    const roots = [], childrenMap = new Map();
    parts.forEach(p => {
      const pv = (p.parent_vpps || '').trim();
      const parent = pv ? byVpps.get(pv) : null;
      if (parent && parent !== p) {
        const pk = this._cmpNodeKey(parent);
        if (!childrenMap.has(pk)) childrenMap.set(pk, []);
        childrenMap.get(pk).push(p);
      } else {
        roots.push(p);
      }
    });
    return { roots, childrenMap };
  }

  _cmpFlattenVisible(tree, collapsed) {
    const result = [];
    const walk = (p, depth, ancestors) => {
      const key = this._cmpNodeKey(p);
      const children = tree.childrenMap.get(key) || [];
      result.push({ part: p, depth, hasChildren: children.length > 0,
                    isCollapsed: collapsed.has(key), key, ancestors });
      if (!collapsed.has(key)) children.forEach(c => walk(c, depth + 1, [...ancestors, key]));
    };
    tree.roots.forEach(r => walk(r, 0, []));
    return result;
  }

  /* ── 零件行 DOM ──────────────────────────────────────────── */
  _cmpPartRow(p, extraClass, prefix, opts) {
    const { depth = 0, hasChildren = false, isCollapsed = false, ancestors = [] } = opts || {};
    const div = document.createElement('div');
    div.className = 'part-row' + (extraClass ? ' ' + extraClass : '');
    const _esc = s => { if (!s) return ''; const d = document.createElement('div'); d.textContent = s; return d.innerHTML; };
    let html = '';
    if (prefix) html += `<span class="pr-prefix">${prefix}</span>`;
    html += `<span class="pr-tree-cell">`;
    if (ancestors.length > 0) {
      ancestors.forEach((ancKey, idx) => {
        const d = ancestors.length - 1 - idx;
        html += `<span class="pr-tree-seg" data-depth="${d}" data-anc-key="${_esc(ancKey)}"></span>`;
      });
    } else if (depth > 0) {
      html += `<span style="flex:0 0 ${depth*14}px"></span>`;
    }
    const chevron = `<svg class="pr-chevron${isCollapsed?' collapsed':''}" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>`;
    const leafDot = ancestors.length ? ' pr-leaf-dot' : '';
    html += `<span class="pr-node-seg${ancestors.length?' has-parent':''}">` +
      (hasChildren ? `<span class="pr-toggle">${chevron}</span>` : `<span class="pr-toggle-ph${leafDot}"></span>`) +
      `</span></span>`;
    html += `<span class="pr-f pr-f-component_id pr-no pr-f-first">${_esc(p.component_id || p.part_no || '-')}</span>`;
    html += `<span class="pr-f pr-f-name pr-name">${_esc(p.name || '')}</span>`;
    html += `<span class="pr-f pr-f-quantity pr-qty">${p.quantity ?? ''}</span>`;
    html += `<span class="pr-f pr-f-component_type pr-type">${_esc(p.component_type || '')}</span>`;
    // vpps — caller may add temp-vpps-badge by overriding via subclass or cellRenderer
    const vppsHtml = this._opts.renderVppsCell
      ? this._opts.renderVppsCell(p)
      : `${_esc(p.vpps || '')}`;
    html += `<span class="pr-f pr-f-vpps pr-vpps">${vppsHtml}</span>`;
    div.innerHTML = html;
    div.style.setProperty('--tree-w', `${(ancestors.length || depth) * 12 + 12}px`);
    return div;
  }

  _highlightChangedCells(row, changedFields) {
    for (const f of changedFields) {
      const el = row.querySelector(`.pr-f-${f}`);
      if (el) el.classList.add('diff-cell-changed');
    }
  }

  /* ── Base 着色 ───────────────────────────────────────────── */
  _renderBaseOverlay({ baseDiff, baseParts }) {
    const bodyEl = this._baseTLS?.getBodyEl?.() ||
                   this._baseTLS?._mountEl?.querySelector('.col-body');
    if (!bodyEl) return;
    const tree = this._cmpBuildTree(baseParts);
    const collapsed = new Set();
    tree.childrenMap.forEach((_, k) => collapsed.add(k));
    const wrap = document.createElement('div');
    wrap.className = 'pr-rows-wrap';
    this._cmpFlattenVisible(tree, collapsed).forEach(({ part, depth, hasChildren, isCollapsed, ancestors }) => {
      const t = baseDiff.get(part._cmpKey);
      const cls = t === 'del' ? 'row-del' : t === 'mod' ? 'row-mod' : '';
      wrap.appendChild(this._cmpPartRow(part, cls, '', { depth, hasChildren, isCollapsed, ancestors }));
    });
    bodyEl.innerHTML = '';
    bodyEl.appendChild(wrap);
  }

  /* ── Target 折叠展示 ────────────────────────────────────── */
  _renderTargetFold({ added, deleted, modified, targetParts, targetDiff }) {
    const bodyEl = this._targetTLS?.getBodyEl?.() ||
                   this._targetTLS?._mountEl?.querySelector('.col-body');
    if (!bodyEl) return;

    const { matchKeyFn } = this._opts;
    const addedKeys    = new Set(targetParts.filter(p => p._cmpKey && !this._lastResult?.baseParts.some(b => matchKeyFn(b) === matchKeyFn(p))).map(p => p._cmpKey));
    const modifiedKeys = new Set(modified.map(m => m.target._cmpKey).filter(Boolean));
    const modMap       = new Map(modified.map(m => [m.target._cmpKey, m]).filter(([k]) => k));

    const tgtStatus = node => {
      const k = node._cmpKey;
      if (!k) return 'same';
      if (addedKeys.has(k)) return 'add';
      if (modifiedKeys.has(k)) return 'mod';
      return 'same';
    };

    const tree = this._cmpBuildTree(targetParts);

    const tgtAllSame = node => {
      if (tgtStatus(node) !== 'same') return false;
      const children = tree.childrenMap.get(this._cmpNodeKey(node)) || [];
      return children.every(c => tgtAllSame(c));
    };

    const wrap = document.createElement('div');
    wrap.className = 'pr-rows-wrap';

    const walkTgt = (node, depth) => {
      if (tgtAllSame(node)) return 1;
      const mk       = node._cmpKey;
      const status   = tgtStatus(node);
      const children = tree.childrenMap.get(this._cmpNodeKey(node)) || [];

      if (status === 'add') {
        wrap.appendChild(this._cmpPartRow(node, 'diff-add', '+', { depth }));
      } else if (status === 'mod') {
        const m = modMap.get(mk);
        wrap.appendChild(this._cmpPartRow(m.base, 'diff-del', '-', { depth }));
        const row = this._cmpPartRow(node, 'diff-add', '+', { depth });
        if (m?.changedFields?.length) this._highlightChangedCells(row, m.changedFields);
        wrap.appendChild(row);
      } else {
        wrap.appendChild(this._cmpPartRow(node, 'diff-ctx', '', { depth }));
      }

      let sameCh = 0;
      children.forEach(c => { sameCh += walkTgt(c, depth + 1); });

      if (sameCh > 0) {
        const s = document.createElement('div');
        s.className = 'part-row diff-same-summary';
        s.style.paddingLeft = `${(depth + 1) * 14 + 12}px`;
        s.innerHTML = `<span style="color:var(--text-muted);font-size:10px;font-style:italic">▶ ${sameCh} 个相同</span>`;
        wrap.appendChild(s);
      }
      return 0;
    };

    let rootSame = 0;
    tree.roots.forEach(r => { rootSame += walkTgt(r, 0); });
    if (rootSame > 0) {
      const s = document.createElement('div');
      s.className = 'part-row diff-same-summary';
      s.innerHTML = `<span style="color:var(--text-muted);font-size:10px;font-style:italic">▶ ${rootSame} 个顶层项相同</span>`;
      wrap.appendChild(s);
    }

    deleted.forEach(p => {
      const depth = Math.max(0, (parseInt(p.level) || 1) - 1);
      wrap.appendChild(this._cmpPartRow(p, 'diff-del', '-', { depth }));
    });

    bodyEl.innerHTML = '';
    bodyEl.appendChild(wrap);
  }

  /* ── 结果面板渲染 ────────────────────────────────────────── */
  _renderDefaultResult() {
    this._resultBodyEl.innerHTML = `
      <div class="lds-result-rules">
        <span style="color:var(--success)">● 新增</span> — Target 中存在，Base 中不存在<br>
        <span style="color:var(--danger)">● 删除</span> — Base 中存在，Target 中不存在<br>
        <span style="color:var(--warning)">● 变更</span> — 两侧均存在，字段有差异<br>
        <span style="color:var(--text-muted)">● 相同</span> — 所有对比字段完全一致
      </div>
      <div class="lds-result-summary">
        <div class="lds-result-card lds-result-card-add"><div class="lds-result-card-num">0</div><div class="lds-result-card-label">新增</div></div>
        <div class="lds-result-card lds-result-card-del"><div class="lds-result-card-num">0</div><div class="lds-result-card-label">删除</div></div>
        <div class="lds-result-card lds-result-card-mod"><div class="lds-result-card-num">0</div><div class="lds-result-card-label">变更</div></div>
        <div class="lds-result-card lds-result-card-same"><div class="lds-result-card-num">0</div><div class="lds-result-card-label">相同</div></div>
      </div>
      <div class="lds-result-detail-list">
        <div class="col-empty">选择两个版本后点击「对比base」</div>
      </div>`;
  }

  _renderCompareResult({ added, deleted, modified, same, targetParts, baseParts }) {
    const _esc = s => { if (!s) return ''; const d = document.createElement('div'); d.textContent = s; return d.innerHTML; };
    const fieldLabels = this._opts.fieldLabels || {};

    this._resultBodyEl.innerHTML = `
      <div class="lds-result-rules">
        <span style="color:var(--success)">● 新增</span> — Target 中存在，Base 中不存在<br>
        <span style="color:var(--danger)">● 删除</span> — Base 中存在，Target 中不存在<br>
        <span style="color:var(--warning)">● 变更</span> — 两侧均存在，字段有差异<br>
        <span style="color:var(--text-muted)">● 相同</span> — 所有对比字段完全一致
      </div>
      <div class="lds-result-summary">
        <div class="lds-result-card lds-result-card-add"><div class="lds-result-card-num" id="lds-num-add">${added.length}</div><div class="lds-result-card-label">新增</div></div>
        <div class="lds-result-card lds-result-card-del"><div class="lds-result-card-num" id="lds-num-del">${deleted.length}</div><div class="lds-result-card-label">删除</div></div>
        <div class="lds-result-card lds-result-card-mod"><div class="lds-result-card-num" id="lds-num-mod">${modified.length}</div><div class="lds-result-card-label">变更</div></div>
        <div class="lds-result-card lds-result-card-same"><div class="lds-result-card-num" id="lds-num-same">${same.length}</div><div class="lds-result-card-label">相同</div></div>
      </div>
      <div class="lds-result-detail-list" id="lds-result-detail-list"></div>`;

    const container = this._resultBodyEl.querySelector('#lds-result-detail-list');
    if (!added.length && !deleted.length && !modified.length) {
      container.innerHTML = '<div class="col-empty">两个版本完全一致</div>';
      return;
    }

    const addedKeys    = new Set(added.map(p => p._cmpKey).filter(Boolean));
    const modifiedKeys = new Set(modified.map(m => m.target._cmpKey).filter(Boolean));
    const modMap       = new Map(modified.map(m => [m.target._cmpKey, m]).filter(([k]) => k));

    const getStatus = node => {
      const k = node._cmpKey;
      if (!k) return 'same';
      if (addedKeys.has(k)) return 'add';
      if (modifiedKeys.has(k)) return 'mod';
      return 'same';
    };

    const tree = this._cmpBuildTree(targetParts);

    const allSame = node => {
      if (getStatus(node) !== 'same') return false;
      const children = tree.childrenMap.get(this._cmpNodeKey(node)) || [];
      return children.every(c => allSame(c));
    };

    const resultItem = (type, badge, partNo, text) => {
      const div = document.createElement('div');
      div.className = 'lds-result-item' + (type === 'ctx' ? ' lds-result-item-ctx' : '');
      div.innerHTML =
        `<span class="ri-badge ri-badge-${type}">${badge}</span>` +
        `<span class="ri-text"><span class="ri-partno">${_esc(partNo)}</span> ${_esc(text)}</span>`;
      return div;
    };

    const walkNode = (node, depth) => {
      if (allSame(node)) return 1;
      const mk       = node._cmpKey;
      const status   = getStatus(node);
      const nk       = this._cmpNodeKey(node);
      const children = tree.childrenMap.get(nk) || [];

      if (status === 'add') {
        const item = resultItem('add', '新增', mk || '', node.name || '');
        item.style.paddingLeft = `${depth * 14 + 6}px`;
        container.appendChild(item);
      } else if (status === 'mod') {
        const m = modMap.get(mk);
        const details = m ? m.changedFields.map(f => {
          const label = fieldLabels[f] || f;
          return `${label}: ${this._norm(m.base[f]) || '-'} → ${this._norm(m.target[f]) || '-'}`;
        }).join('; ') : '';
        const item = resultItem('mod', '变更', mk || '', details);
        item.style.paddingLeft = `${depth * 14 + 6}px`;
        container.appendChild(item);
      } else {
        const item = resultItem('ctx', '·', mk || (node.name || ''), node.name || '');
        item.style.paddingLeft = `${depth * 14 + 6}px`;
        container.appendChild(item);
      }

      let sameCh = 0;
      children.forEach(c => { sameCh += walkNode(c, depth + 1); });
      if (sameCh > 0) {
        const div = document.createElement('div');
        div.className = 'lds-result-item lds-result-item-same-summary';
        div.style.paddingLeft = `${(depth + 1) * 14 + 6}px`;
        div.innerHTML = `<span style="color:var(--text-muted);font-size:10px;font-style:italic">▶ ${sameCh} 个子项相同</span>`;
        container.appendChild(div);
      }
      return 0;
    };

    let rootSame = 0;
    tree.roots.forEach(r => { rootSame += walkNode(r, 0); });
    if (rootSame > 0) {
      const div = document.createElement('div');
      div.className = 'lds-result-item';
      div.innerHTML = `<span style="color:var(--text-muted);font-size:10px;font-style:italic">▶ ${rootSame} 个顶层项相同</span>`;
      container.appendChild(div);
    }

    if (deleted.length) {
      const _esc2 = s => { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; };
      const hdr = document.createElement('div');
      hdr.style.cssText = 'font-size:10px;font-weight:600;color:var(--danger);padding:4px 6px;margin-top:4px;border-top:1px solid var(--border)';
      hdr.textContent = `已删除 (${deleted.length})`;
      container.appendChild(hdr);
      deleted.forEach(p => {
        container.appendChild(resultItem('del', '删除', p._cmpKey || this._opts.matchKeyFn(p), p.name || ''));
      });
    }
  }

  /* ── extraCheck 结果渲染 ────────────────────────────────── */
  _renderCheckResult(checkResult) {
    const { rules = [], summary = [], errorGroups = [] } = checkResult;
    const _esc = s => { if (!s) return ''; const d = document.createElement('div'); d.textContent = s; return d.innerHTML; };

    const rulesHtml = rules.map(r => `<span style="color:${r.color}">● ${_esc(r.text)}</span>`).join('<br>');

    const summaryHtml = summary.map(s => {
      const cls = `lds-result-card lds-result-card-${s.type || 'same'}`;
      const ruleAttr = s.rule != null ? ` data-rule="${s.rule}"` : '';
      return `<div class="${cls}"${ruleAttr}><div class="lds-result-card-num">${s.count}</div><div class="lds-result-card-label">${_esc(s.label)}</div></div>`;
    }).join('');

    this._resultBodyEl.innerHTML = `
      <div class="lds-result-rules-wrap">
        <button class="lds-rules-toggle">
          <svg class="lds-rules-chevron" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
          规则说明
        </button>
        <div class="lds-result-rules">${rulesHtml}</div>
      </div>
      <div class="lds-result-summary">${summaryHtml}</div>
      <div class="lds-result-detail-list" id="lds-check-detail"></div>`;

    // 规则说明折叠
    const toggleBtn  = this._resultBodyEl.querySelector('.lds-rules-toggle');
    const rulesEl    = this._resultBodyEl.querySelector('.lds-result-rules');
    toggleBtn?.addEventListener('click', () => {
      const open = rulesEl.classList.toggle('lds-result-rules-open');
      toggleBtn.querySelector('.lds-rules-chevron').style.transform = open ? 'rotate(180deg)' : '';
    });

    // 绑定 summary card 点击筛选
    if (checkResult.onFilterByRule) {
      this._resultBodyEl.querySelectorAll('.lds-result-card[data-rule]').forEach(card => {
        card.addEventListener('click', () => {
          const rule = parseInt(card.dataset.rule);
          const isActive = card.classList.contains('lds-result-card-active');
          this._resultBodyEl.querySelectorAll('.lds-result-card').forEach(c => c.classList.remove('lds-result-card-active'));
          if (!isActive) { card.classList.add('lds-result-card-active'); checkResult.onFilterByRule(rule); }
          else { checkResult.onFilterByRule(null); }
        });
      });
    }

    const list = this._resultBodyEl.querySelector('#lds-check-detail');

    // Helper: 构建「两格子 + 提示行 + 按钮」操作区块，插在 detail list 之前
    const _makeActionSection = ({ cardA, cardB, hint, btnEl }) => {
      const sec = document.createElement('div');
      sec.className = 'lds-action-section';
      sec.innerHTML =
        `<div class="lds-action-cards">` +
        `<div class="lds-action-card lds-action-card-${cardA.type}"><div class="lds-action-card-num">${cardA.count}</div><div class="lds-action-card-label">${_esc(cardA.label)}</div></div>` +
        `<div class="lds-action-card lds-action-card-${cardB.type}"><div class="lds-action-card-num">${cardB.count}</div><div class="lds-action-card-label">${_esc(cardB.label)}</div></div>` +
        `</div>` +
        (hint ? `<div class="lds-action-hint">${_esc(hint)}</div>` : '');
      sec.appendChild(btnEl);
      this._resultBodyEl.insertBefore(sec, list);
    };

    // 提交处理措施按钮
    if (checkResult.submitPendingActions) {
      const btn = document.createElement('button');
      btn.className = 'lds-submit-pending-btn';
      const _upd = n => { btn.textContent = `提交处理措施（${n} 条未提交）`; btn.disabled = n === 0; };
      _upd(checkResult.getPendingCount?.() || 0);
      btn.onclick = async () => { btn.disabled = true; btn.textContent = '提交中…'; await checkResult.submitPendingActions(); };
      this._resultBodyEl.insertBefore(btn, list);
      checkResult.onPendingBtnRender?.(_upd);
    }

    // 批量提交无主数据
    if (checkResult.batchAddNoData) {
      const { count, existingCount = 0, run } = checkResult.batchAddNoData;
      const btn = document.createElement('button');
      btn.className = 'lds-submit-pending-btn lds-batch-btn-warn';
      btn.textContent = `批量提交无主数据处理（共 ${count} 条）`;
      btn.onclick = async () => {
        if (!confirm(`将 ${count} 条无主数据零件写入 vpps_parts 知识库（已存在的将跳过）？`)) return;
        btn.disabled = true; btn.textContent = '提交中…';
        try {
          const res = await run();
          btn.textContent = `✓ 已添加 ${res.added} 条，跳过 ${res.skipped} 条`;
          await checkResult.rerunCheck?.();
        } catch (e) { btn.disabled = false; btn.textContent = `批量提交无主数据处理（共 ${count} 条）`; alert('操作失败: ' + e.message); }
      };
      _makeActionSection({
        cardA: { count, label: '无主数据', type: 'pending' },
        cardB: { count: existingCount, label: '已有主数据', type: 'done' },
        hint: '写入后成为知识库主数据，可被后续版本核对复用',
        btnEl: btn,
      });
    }

    // 批量提交可接受别名
    if (checkResult.batchAcceptAliases) {
      const { count, acceptedCount = 0, run } = checkResult.batchAcceptAliases;
      const btn = document.createElement('button');
      btn.className = 'lds-submit-pending-btn lds-batch-btn-warn';
      btn.textContent = `批量提交可接受别名（共 ${count} 条）`;
      btn.onclick = async () => {
        if (!confirm(`批量接受全部 ${count} 条描述别名？`)) return;
        btn.disabled = true; btn.textContent = '提交中…';
        try {
          const res = await run();
          btn.textContent = `✓ 已处理 ${res.processed} 条，失败 ${res.failed} 条`;
          await checkResult.rerunCheck?.();
        } catch (e) { btn.disabled = false; btn.textContent = `批量提交可接受别名（共 ${count} 条）`; alert('操作失败: ' + e.message); }
      };
      _makeActionSection({
        cardA: { count, label: '待接受别名', type: 'pending' },
        cardB: { count: acceptedCount, label: '已接受别名', type: 'done' },
        hint: '别名接受后永久写入知识库，下次核对自动通过',
        btnEl: btn,
      });
    }

    // 暂时忽略规则4（VPPS 专用）
    if (checkResult.ignoreRule4 && (checkResult.ignoreRule4.count > 0 || checkResult.ignoreRule4.ignoredCount > 0)) {
      const { count, ignoredCount = 0, run, revertAll } = checkResult.ignoreRule4;
      const btn = document.createElement('button');
      btn.className = 'lds-submit-pending-btn lds-batch-btn-ignore-r4';
      btn.disabled = count === 0;
      btn.textContent = count > 0 ? `暂时忽略规则4（${count} 条零件）` : '规则4已全部忽略';
      btn.onclick = async () => {
        if (!confirm(`将当前 ${count} 条规则4 NOK 零件标记为已忽略？下次核对时不再显示，可通过审计记录撤销。`)) return;
        btn.disabled = true; btn.textContent = '忽略中…';
        try {
          await run();
        } catch (e) { btn.disabled = false; btn.textContent = `暂时忽略规则4（${count} 条零件）`; alert('操作失败: ' + e.message); }
      };

      // 集中撤销按钮
      let revertBtn = null;
      if (ignoredCount > 0 && revertAll) {
        revertBtn = document.createElement('button');
        revertBtn.className = 'lds-submit-pending-btn lds-batch-btn-revert-ignored';
        revertBtn.textContent = `集中撤销（${ignoredCount} 条已忽略）`;
        revertBtn.onclick = async () => {
          if (!confirm(`撤销全部 ${ignoredCount} 条已忽略的规则4记录，恢复为 NOK 状态？`)) return;
          revertBtn.disabled = true; revertBtn.textContent = '撤销中…';
          try {
            await revertAll();
          } catch (e) {
            revertBtn.disabled = false;
            revertBtn.textContent = `集中撤销（${ignoredCount} 条已忽略）`;
            alert('撤销失败: ' + e.message);
          }
        };
      }

      _makeActionSection({
        cardA: { count, label: '待忽略', type: 'pending' },
        cardB: { count: ignoredCount, label: '已忽略', type: 'done' },
        hint: ignoredCount > 0 ? `已忽略 ${ignoredCount} 条，可集中撤销或逐条在核对表里撤销` : '忽略后下次核对不再显示，可随时撤销',
        btnEl: btn,
      });
      if (revertBtn) list.appendChild(revertBtn);
    }

    if (!errorGroups.length || errorGroups.every(g => !g.items?.length)) {
      list.innerHTML = '<div class="col-empty lds-check-ok">核对通过，无异常</div>';
      return;
    }

    errorGroups.forEach(group => {
      if (!group.items?.length) return;
      const hdr = document.createElement('div');
      hdr.className = 'lds-check-hdr lds-check-hdr-collapsible';
      hdr.innerHTML = `<span class="lds-check-hdr-chevron">▶</span> ${_esc(group.title)} <span class="lds-check-hdr-count">(${group.items.length})</span>`;
      const itemsWrap = document.createElement('div');
      itemsWrap.className = 'lds-check-group-items lds-check-group-collapsed';
      hdr.addEventListener('click', () => {
        const collapsed = itemsWrap.classList.toggle('lds-check-group-collapsed');
        hdr.querySelector('.lds-check-hdr-chevron').textContent = collapsed ? '▶' : '▼';
      });
      list.appendChild(hdr);
      group.items.forEach(item => {
        const div = document.createElement('div');
        div.className = 'lds-result-item';
        div.innerHTML =
          `<span class="ri-badge ${item.badge === '已忽略' ? 'ri-badge-muted' : 'ri-badge-del'}">${_esc(item.badge || '异常')}</span>` +
          `<span class="ri-text"><span class="ri-partno">${_esc(item.vpps || item.key || '')}</span>` +
          `${item.row ? `<span class="lds-check-err-row">行${item.row}</span>` : ''} ${_esc(item.msg)}</span>`;
        if (item.onAction) {
          const btn = document.createElement('button');
          btn.className = 'lds-check-action-btn';
          btn.textContent = item.actionLabel || '操作';
          btn.onclick = item.onAction;
          div.appendChild(btn);
        }
        itemsWrap.appendChild(div);
      });
      list.appendChild(itemsWrap);
    });
  }

  /* ── 导出结论（stub） ────────────────────────────────────── */
  _onExportResult() {
    console.log('[ListDiffShell] export result — not implemented');
  }
}

