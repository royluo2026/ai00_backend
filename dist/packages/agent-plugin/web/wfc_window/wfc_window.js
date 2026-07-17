/**
 * web/wfc_window/wfc_window.js
 * 工作流画布独立窗口逻辑（精简版）
 *
 * 架构：纯可视化画布窗口，对话在 AI 助手主窗口。
 * 两窗口通过 IPC 保持上下文联动：
 *   - AI→画布：wfc:receive-data
 *   - 画布→AI：wfc:inject-to-chat
 *   - 状态缓存：wfc:push-canvas-state
 */

(function () {
  'use strict';

  /* ── 工具函数 ─────────────────────────────────────────────────────────── */
  // localStorage 账号隔离
  function _lsk(base) {
    try { const u = window._authUser || window.parent?._authUser || window.top?._authUser; const g = u?.gid || u?.user_gid || ''; return g ? `${g}:${base}` : base; } catch { return base; }
  }
  function _genId(prefix = 'e') {
    return prefix + Date.now() + '_' + Math.random().toString(36).slice(2, 7);
  }
  function _esc(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  /* ── Skill 执行沙盘 ────────────────────────────────────────────────────── */
  class SkillSandbox {
    constructor({ containerEl, fetchOptions, onApprove, onReject }) {
      this._el = containerEl;
      this._fetchOptions = fetchOptions;
      this._onApprove = onApprove;
      this._onReject  = onReject;
    }
    show() { this._el?.classList.remove('hidden'); }
    hide() {
      this._el?.classList.add('hidden');
      document.getElementById('wfcwCanvasEmpty')?.classList.remove('hidden');
    }
    clearForInteraction(_opts) {
      if (!this._el) return;
      this._el.innerHTML = '';
      this._el.scrollTop = 0;
      this.show();
      document.getElementById('wfcwCanvasEmpty')?.classList.add('hidden');
      document.getElementById('wfcwHaltedBar')?.classList.add('hidden');
    }
    addNode(type, label, _col, _step, params) {
      if (!this._el) return;
      console.debug('[SkillSandbox] addNode', type, label, params);
      let card = null;
      if (type === 'human_approval' || type === 'human') card = this._buildApprovalCard(label, params);
      else if (type === 'result_list') card = this._buildResultCard(label, params);
      else if (type === 'agent')       card = this._buildStatusCard(label, params);
      if (card) {
        this._el.appendChild(card);
        requestAnimationFrame(() => { this._el.scrollTop = this._el.scrollHeight; });
      }
    }
    _buildApprovalCard(label, params) {
      const token = params._pause_token;
      const ctx   = params._context || '';
      let fields  = [];
      try { fields = JSON.parse(params._collect_fields || '[]'); } catch (_) {}
      const card = document.createElement('div');
      card.className = 'wfcw-sb-card wfcw-sb-approval';
      const hdr = document.createElement('div');
      hdr.className = 'wfcw-sb-hdr';
      hdr.innerHTML = `<span class="wfcw-sb-hdr-label">${_esc(label)}</span><span class="wfcw-sb-badge wfcw-sb-badge-wait">等待确认</span>`;
      card.appendChild(hdr);
      const body = document.createElement('div');
      body.className = 'wfcw-sb-body';
      if (ctx) { const c = document.createElement('div'); c.className = 'wfcw-sb-ctx'; c.textContent = ctx; body.appendChild(c); }
      const formState = {};
      if (fields.length) body.appendChild(this._buildFormFields(fields, formState));
      const btnRow = document.createElement('div');
      btnRow.className = 'wfcw-sb-btns';
      const btnOk = document.createElement('button'); btnOk.className = 'wfcw-sb-btn wfcw-sb-btn-ok'; btnOk.textContent = '确认';
      const btnNo = document.createElement('button'); btnNo.className = 'wfcw-sb-btn wfcw-sb-btn-no'; btnNo.textContent = '拒绝';
      const disable = () => { btnOk.disabled = true; btnNo.disabled = true; card.classList.add('wfcw-sb-submitted'); hdr.querySelector('.wfcw-sb-badge')?.remove(); };
      btnOk.addEventListener('click', () => {
        const ud = {};
        card.querySelectorAll('.wfcw-sb-radio-group[data-key]').forEach(g => { const c = g.querySelector('input[type=radio]:checked'); if (c) ud[g.dataset.key] = c.value; });
        card.querySelectorAll('.wfcw-sb-select[data-key]').forEach(s => { if (s.value) ud[s.dataset.key] = s.value; });
        card.querySelectorAll('.wfcw-sb-checklist[data-key]').forEach(cl => { const v = [...cl.querySelectorAll('input[type=checkbox]:checked')].map(c => c.value); if (v.length) ud[cl.dataset.key] = v; });
        console.debug('[SkillSandbox] confirm userData', ud);
        disable(); this._onApprove?.(token, ud);
      });
      btnNo.addEventListener('click', () => { disable(); this._onReject?.(token); });
      btnRow.append(btnOk, btnNo);
      body.appendChild(btnRow);
      card.appendChild(body);
      return card;
    }
    _buildFormFields(fields, formState) {
      const form = document.createElement('div');
      form.className = 'wfcw-sb-form';
      const fieldEls = {};
      fields.forEach(f => {
        if (f.type === 'hidden') return;
        const row = document.createElement('div');
        row.className = 'wfcw-sb-field';
        if (f.label) { const l = document.createElement('div'); l.className = 'wfcw-sb-field-label'; l.textContent = f.label; row.appendChild(l); }
        if (f.type === 'radio') {
          const grp = document.createElement('div'); grp.className = 'wfcw-sb-radio-group'; grp.dataset.key = f.key;
          const def = f.default ?? f.options?.[0]?.value;
          (f.options || []).forEach(opt => {
            const lbl = document.createElement('label'); lbl.className = 'wfcw-sb-radio-item';
            const inp = document.createElement('input'); inp.type = 'radio'; inp.name = 'sbf_' + f.key + '_' + Math.random().toString(36).slice(2); inp.value = opt.value;
            if (opt.value === def) inp.checked = true;
            inp.addEventListener('change', () => { formState[f.key] = inp.value; this._updateShowWhen(fields, fieldEls, formState); });
            lbl.append(inp, document.createTextNode(' ' + (opt.label || opt.value))); grp.appendChild(lbl);
          });
          row.appendChild(grp); formState[f.key] = def;
        } else if (f.type === 'select' || f.type === 'cascade') {
          const sel = document.createElement('select'); sel.className = 'wfcw-sb-select'; sel.dataset.key = f.key;
          sel.innerHTML = '<option value="">加载中…</option>';
          if (f.depends_on) { sel.disabled = true; row.dataset.dependsOn = f.depends_on; }
          row.appendChild(sel);
          const p = f._resolved_source_param || {};
          if (f.source_tool) {
            this._fetchOptions(f.source_tool, p).then(res => {
              sel.innerHTML = '<option value="">请选择…</option>';
              (res?.options || []).forEach(o => { const op = document.createElement('option'); op.value = o.value; op.textContent = o.label || o.value; sel.appendChild(op); });
            });
          } else if (f.options?.length) {
            sel.innerHTML = '<option value="">请选择…</option>';
            f.options.forEach(o => { const op = document.createElement('option'); op.value = o.value; op.textContent = o.label || o.value; sel.appendChild(op); });
          }
          sel.addEventListener('change', () => { formState[f.key] = sel.value; this._updateShowWhen(fields, fieldEls, formState); });
        } else if (f.type === 'select_multi') {
          const cl = document.createElement('div'); cl.className = 'wfcw-sb-checklist'; cl.dataset.key = f.key;
          cl.innerHTML = '<div class="wfcw-sb-loading">加载中…</div>'; row.appendChild(cl);
          const p = f._resolved_source_param || {};
          if (f.source_tool) {
            this._fetchOptions(f.source_tool, p).then(res => {
              cl.innerHTML = '';
              (res?.options || []).forEach(o => { const lbl = document.createElement('label'); lbl.className = 'wfcw-sb-chk-item'; const inp = document.createElement('input'); inp.type = 'checkbox'; inp.value = o.value; lbl.append(inp, document.createTextNode(' ' + (o.label || o.value))); cl.appendChild(lbl); });
              if (!cl.children.length) cl.innerHTML = '<div class="wfcw-sb-empty">（暂无数据）</div>';
            });
          }
        }
        if (f.show_when) row.dataset.showWhen = JSON.stringify(f.show_when);
        form.appendChild(row); fieldEls[f.key] = row;
      });
      this._updateShowWhen(fields, fieldEls, formState);
      // cascade: wire parent→child
      fields.forEach(f => {
        if (!f.depends_on || !f.source_tool) return;
        const pSel = fieldEls[f.depends_on]?.querySelector('select');
        const cSel = fieldEls[f.key]?.querySelector('select');
        if (!pSel || !cSel) return;
        pSel.addEventListener('change', async () => {
          const pv = pSel.value;
          if (!pv) { cSel.innerHTML = '<option value="">请先选上级</option>'; cSel.disabled = true; return; }
          cSel.innerHTML = '<option value="">加载中…</option>'; cSel.disabled = false;
          const res = await this._fetchOptions(f.source_tool, { ...(f._resolved_source_param || {}), [f.depends_on]: pv });
          cSel.innerHTML = '<option value="">请选择…</option>';
          (res?.options || []).forEach(o => { const op = document.createElement('option'); op.value = o.value; op.textContent = o.label || o.value; cSel.appendChild(op); });
        });
      });
      return form;
    }
    _updateShowWhen(fields, fieldEls, formState) {
      fields.forEach(f => {
        if (!f.show_when) return;
        const el = fieldEls[f.key]; if (!el) return;
        el.style.display = Object.entries(f.show_when).every(([k, v]) => formState[k] === v) ? '' : 'none';
      });
    }
    _buildResultCard(label, params) {
      const items = params._items || [];
      const text  = params._text  || '';
      const hasErr  = items.some(i => i.level === 'error');
      const hasWarn = items.some(i => i.level === 'warn');
      const bcls = hasErr ? 'wfcw-sb-badge-error' : hasWarn ? 'wfcw-sb-badge-warn' : 'wfcw-sb-badge-ok';
      const btxt = hasErr ? '有错误' : hasWarn ? '有警告' : '正常';
      const card = document.createElement('div');
      card.className = 'wfcw-sb-card wfcw-sb-result';
      const hdr = document.createElement('div'); hdr.className = 'wfcw-sb-hdr';
      hdr.innerHTML = `<span class="wfcw-sb-hdr-label">${_esc(label)}</span><span class="wfcw-sb-badge ${bcls}">${btxt}</span>`;
      card.appendChild(hdr);
      if (text || items.length) {
        const body = document.createElement('div'); body.className = 'wfcw-sb-body';
        if (text) { const t = document.createElement('div'); t.className = 'wfcw-sb-text'; t.textContent = text; body.appendChild(t); }
        if (items.length) {
          const list = document.createElement('div'); list.className = 'wfcw-sb-items';
          items.forEach(it => {
            const r = document.createElement('div'); r.className = `wfcw-sb-item wfcw-sb-item-${it.level || 'info'}`;
            const l = document.createElement('span'); l.className = 'wfcw-sb-item-label'; l.textContent = it.label || ''; r.appendChild(l);
            if (it.desc) { const d = document.createElement('span'); d.className = 'wfcw-sb-item-desc'; d.textContent = it.desc; r.appendChild(d); }
            list.appendChild(r);
          });
          body.appendChild(list);
        }
        card.appendChild(body);
      }
      return card;
    }
    _buildStatusCard(label, params) {
      const note = params.note || params.summary || '';
      const isOk = label.includes('完成') || label.includes('✅');
      const card = document.createElement('div');
      card.className = `wfcw-sb-card wfcw-sb-status ${isOk ? 'wfcw-sb-ok-status' : 'wfcw-sb-halt'}`;
      const hdr = document.createElement('div'); hdr.className = 'wfcw-sb-hdr';
      hdr.innerHTML = `<span class="wfcw-sb-hdr-label">${_esc(label)}</span>`;
      card.appendChild(hdr);
      if (note) {
        const body = document.createElement('div'); body.className = 'wfcw-sb-body';
        note.split('\n').filter(l => l.trim()).forEach(line => { const el = document.createElement('div'); el.className = 'wfcw-sb-note'; el.textContent = line; body.appendChild(el); });
        card.appendChild(body);
      }
      return card;
    }
    /** BOP 结构可视化卡片：线体→工位→工序，颜色区分关联状态 */
    /** BOP 结构可视化卡片：线体框 + L/R 工位列对布局 + 工序 chips */
    addBopCanvas(label, treeData) {
      if (!this._el) return;
      const { lines = [], linked_count = 0, total_ops = 0 } = treeData;
      const pct      = total_ops > 0 ? Math.round(linked_count / total_ops * 100) : 0;
      const badgeCls = pct === 100 ? 'wfcw-sb-badge-ok' : pct > 0 ? 'wfcw-sb-badge-warn' : 'wfcw-sb-badge-error';

      /** 按 L/R/M 后缀将工位配对成 {top, bot} 列数组 */
      function buildCols(stations) {
        const sfx = t => { const m = (t || '').match(/[-_]([LRM])$/i); return m ? m[1].toUpperCase() : null; };
        const Ls = [], Rs = [], Ns = [];
        for (const s of stations) {
          const f = sfx(s.title);
          if (f === 'L' || f === 'M') Ls.push(s);
          else if (f === 'R') Rs.push(s);
          else Ns.push(s);
        }
        const usedR = new Set(), cols = [];
        for (const l of Ls) {
          const r = Rs.find(r => r.sort_order === l.sort_order && !usedR.has(r.gid));
          if (r) usedR.add(r.gid);
          cols.push({ top: l, bot: r || null });
        }
        for (const r of Rs) if (!usedR.has(r.gid)) cols.push({ top: null, bot: r });
        for (const s of Ns) cols.push({ top: s, bot: null });
        cols.sort((a, b) => ((a.top || a.bot).sort_order || 0) - ((b.top || b.bot).sort_order || 0));
        return cols;
      }

      function buildStEl(st, cls) {
        const el = document.createElement('div');
        el.className = st ? `wfcw-sb-bop-st ${cls}` : `wfcw-sb-bop-st ${cls} wfcw-sb-bop-st-empty`;
        if (!st) return el;
        const hdr = document.createElement('div'); hdr.className = 'wfcw-sb-bop-st-hdr';
        hdr.textContent = st.title; el.appendChild(hdr);
        if (st.operations?.length) {
          const ops = document.createElement('div'); ops.className = 'wfcw-sb-bop-ops';
          for (const op of st.operations) {
            const o = document.createElement('div');
            o.className = `wfcw-sb-bop-op wfcw-sb-bop-op-${op.link_status || 'none'}`;
            o.title = `${op.vpps ? op.vpps + ' · ' : ''}${op.title}`;
            o.textContent = op.title;
            ops.appendChild(o);
          }
          el.appendChild(ops);
        }
        return el;
      }

      const card = document.createElement('div');
      card.className = 'wfcw-sb-card wfcw-sb-bop-canvas-card';

      const hdr = document.createElement('div'); hdr.className = 'wfcw-sb-hdr';
      hdr.innerHTML = `<span class="wfcw-sb-hdr-label">${_esc(label)}</span>
        <span class="wfcw-sb-badge ${badgeCls}">${linked_count}/${total_ops} 已关联 ${pct}%</span>`;
      card.appendChild(hdr);

      const scroll = document.createElement('div'); scroll.className = 'wfcw-sb-bop-scroll';
      if (!lines.length) {
        scroll.innerHTML = '<div class="wfcw-sb-empty">无线体数据</div>';
      } else {
        for (const line of lines) {
          const lineEl  = document.createElement('div'); lineEl.className = 'wfcw-sb-bop-line';
          const lineHdr = document.createElement('div'); lineHdr.className = 'wfcw-sb-bop-line-hdr';
          lineHdr.textContent = line.title; lineEl.appendChild(lineHdr);

          const cols = buildCols(line.stations);
          const grid = document.createElement('div'); grid.className = 'wfcw-sb-bop-grid';
          for (const col of cols) {
            const colEl = document.createElement('div'); colEl.className = 'wfcw-sb-bop-col';
            colEl.appendChild(buildStEl(col.top, 'wfcw-sb-bop-st-top'));
            colEl.appendChild(buildStEl(col.bot, 'wfcw-sb-bop-st-bot'));
            grid.appendChild(colEl);
          }
          lineEl.appendChild(grid);
          scroll.appendChild(lineEl);
        }
      }
      card.appendChild(scroll);

      const legend = document.createElement('div'); legend.className = 'wfcw-sb-bop-legend';
      legend.innerHTML = `
        <span class="wfcw-sb-bop-leg wfcw-sb-bop-op-linked">已关联</span>
        <span class="wfcw-sb-bop-leg wfcw-sb-bop-op-none">未关联</span>`;
      card.appendChild(legend);

      this._el.appendChild(card);
      requestAnimationFrame(() => { this._el.scrollTop = this._el.scrollHeight; });
    }
  }
  let _skillSandbox = null;

  /* ── 画布模式状态 ──────────────────────────────────────────────────────── */
  let _ctxOn    = false;   // 上下文感知开关
  let _wfcMode  = 'explore'; // 'explore' | 'fixed'
  let _fixedSkill = null;    // 当前激活的固定 Skill（固定模式时有值）
  let _skillsList = [];      // 缓存的 Skill 列表（供 @ mention 搜索）

  /* ── WorkflowCanvas 初始化 ────────────────────────────────────────────── */
  let _wfCanvas  = null;   // 下层：交互画布（接收 generate_canvas 结果）
  let _topCanvas = null;   // 上层：Skill 流程总览（只读）

  function _initCanvas() {
    // 下层：交互画布
    _wfCanvas = new WorkflowCanvas({
      paletteEl: document.getElementById('wfcwPaletteEl'),
      svgEl:     document.getElementById('wfcwSvg'),
      lanesEl:   document.getElementById('wfcwLanes'),
      statsEl:   document.getElementById('wfcwStats'),
      qaQEl:     null,
      qaAEl:     null,
      onNodeAdded:    _onNodeAdded,
      onNodeRemoved:  _onNodeRemoved,
      onNodeSelected: null,
      onHumanApprovalAction: _onCanvasApprovalAction,
      fetchApprovalOptions:  _fetchApprovalOptions,
    });
    _wfCanvas.init();

    // 上层：Skill 流程总览（只读，palette 用隐藏占位 div 避免初始化报错）
    const _topPaletteEl = document.createElement('div');
    _topPaletteEl.style.display = 'none';
    document.body.appendChild(_topPaletteEl);
    _topCanvas = new WorkflowCanvas({
      paletteEl: _topPaletteEl,
      svgEl:     document.getElementById('wfcwTopSvg'),
      lanesEl:   document.getElementById('wfcwTopLanes'),
      statsEl:   null,
      qaQEl:     null,
      qaAEl:     null,
      onNodeAdded:    null,
      onNodeRemoved:  null,
      onNodeSelected: null,
    });
    _topCanvas.init();

    // 初始化 Skill 执行沙盘
    _skillSandbox = new SkillSandbox({
      containerEl: document.getElementById('wfcwSandbox'),
      fetchOptions: _fetchApprovalOptions,
      onApprove: (tok, ud) => _resumeSkillCanvas(tok, true, ud),
      onReject:  (tok)     => _resumeSkillCanvas(tok, false, {}),
    });

    // 关闭流程总览按钮
    document.getElementById('wfcwFlowPanelClose')?.addEventListener('click', _hideFlowPanel);
  }

  /* ── 流程总览面板显隐 ──────────────────────────────────────────────────── */
  function _showFlowPanel(title) {
    const $panel   = document.getElementById('wfcwFlowPanel');
    const $divider = document.getElementById('wfcwHDivider');
    const $title   = document.getElementById('wfcwFlowPanelTitle');
    if ($panel)   $panel.classList.add('visible');
    if ($divider) $divider.classList.add('visible');
    if ($title && title) $title.textContent = title;
    // 恢复上次调整的高度（至少 180px）
    const savedH = localStorage.getItem(_lsk('wfcw.flowPanelH'));
    if (savedH && $panel) $panel.style.height = Math.max(180, parseInt(savedH)) + 'px';
  }

  function _hideFlowPanel() {
    document.getElementById('wfcwFlowPanel')?.classList.remove('visible');
    document.getElementById('wfcwHDivider')?.classList.remove('visible');
  }

  /* ── 模式管理 ─────────────────────────────────────────────────────────── */

  /** 更新 header 上的模式徽章，同步"更新 Skill"按钮显隐 */
  function _updateModeIndicator() {
    const $badge = document.getElementById('wfcwModeBadge');
    const $label = document.getElementById('wfcwModeBadgeLabel');
    const $icon  = document.getElementById('wfcwModeBadgeIcon');
    const $updateBtn = document.getElementById('wfcUpdateSkillBtn');
    const $fsActions = document.getElementById('wfcwFsActions');
    const $fsUpdate  = document.getElementById('wfcwFsUpdateSkill');
    if (!$badge) return;
    $badge.dataset.mode = _wfcMode;
    if (_wfcMode === 'fixed') {
      if ($label) $label.textContent = `固定：${_fixedSkill?.title || ''}`;
      // 锁定图标
      if ($icon) $icon.innerHTML = '<rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>';
      if ($updateBtn) $updateBtn.style.display = '';
      if ($fsActions) $fsActions.style.display = '';
      if ($fsUpdate)  $fsUpdate.style.display  = '';
    } else {
      if ($label) $label.textContent = '探索模式';
      // 搜索图标
      if ($icon) $icon.innerHTML = '<circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>';
      if ($updateBtn) $updateBtn.style.display = 'none';
      if ($fsActions) $fsActions.style.display = 'none';
    }
  }

  /** 进入固定模式（Skill 有预定义画布） */
  function _enterFixedMode(skill, canvasData) {
    _wfcMode    = 'fixed';
    _fixedSkill = skill;
    _topCanvas.fromJSON(canvasData);
    requestAnimationFrame(_syncTopColumnWidths);
    _updateModeIndicator();
    _showToast(`已进入固定模式：${skill.title}`);
    // 展开流程 sidebar 并渲染步骤
    _renderFlowSidebar(_topCanvas);
    const $fSb = document.getElementById('wfcwFlowSidebar');
    if ($fSb) {
      $fSb.classList.remove('ns-collapsed');
      localStorage.setItem(_lsk('wfcw.flowSidebarCollapsed'), 'false');
    }
  }

  /** 自动扩展上层流程画布中节点数 > 1 的步骤列宽 */
  function _syncTopColumnWidths() {
    if (!_topCanvas) return;
    const lanesEl = document.getElementById('wfcwTopLanes');
    if (!lanesEl) return;
    const steps  = _topCanvas._steps;
    const NODE_W = 116;  // .wfc-node width
    const GAP    = 8;    // horizontal gap between side-by-side nodes
    const PAD    = 18;   // total cell horizontal padding
    const MIN_W  = 140;  // --canvas-step-w

    // 先重置之前可能设置的内联宽度
    lanesEl.querySelectorAll('.wfc-lane-cell, .wfc-step-headers .wfc-step-hdr')
      .forEach(el => { el.style.width = ''; });

    const hdrs = lanesEl.querySelectorAll('.wfc-step-headers .wfc-step-hdr');
    for (let s = 1; s <= steps; s++) {
      let maxNodes = 0;
      _topCanvas._lanes.forEach((_, laneIdx) => {
        const cnt = _topCanvas._nodes.filter(n => n.laneIdx === laneIdx && n.step === s).length;
        maxNodes = Math.max(maxNodes, cnt);
      });
      if (maxNodes <= 1) continue;
      const colW = maxNodes * NODE_W + (maxNodes - 1) * GAP + PAD;
      lanesEl.querySelectorAll(`.wfc-lane-cell[data-step="${s}"]`).forEach(cell => {
        cell.style.width = colW + 'px';
      });
      if (hdrs[s - 1]) hdrs[s - 1].style.width = colW + 'px';
    }
  }

  /** 进入探索模式（手动或 Skill 无预定义画布） */
  function _enterExploreMode(skill) {
    _wfcMode    = 'explore';
    _fixedSkill = null;
    _hideFlowPanel();
    _updateModeIndicator();
    if (skill) _showToast(`探索模式：${skill.title}`);
    // 收起流程 sidebar
    const $fSb = document.getElementById('wfcwFlowSidebar');
    $fSb?.classList.add('ns-collapsed');
    localStorage.setItem(_lsk('wfcw.flowSidebarCollapsed'), 'true');
    const $fsBody = document.getElementById('wfcwFsSidebarBody');
    if ($fsBody) $fsBody.innerHTML = '<div class="wfcw-fs-empty">选中 Skill 后显示流程</div>';

    // 有 skill 时，自动让小柔生成初步流程画布
    if (skill) {
      const $inp = document.getElementById('wfcwAiInp');
      if ($inp) {
        $inp.value = `请为「${skill.title}」设计一个初步的工作流程画布`;
        setTimeout(_sendAiMsg, 200);
      }
    }
  }

  /** 手动切换模式（点击徽章触发） */
  function _initModeBadge() {
    document.getElementById('wfcwModeBadge')?.addEventListener('click', () => {
      if (_wfcMode === 'fixed') {
        // 固定 → 探索：询问确认
        if (confirm(`退出固定模式「${_fixedSkill?.title || ''}」并进入探索模式？\n（流程总览将关闭）`)) {
          _enterExploreMode(null);
        }
      } else {
        // 探索模式下点击：提示用途
        _showToast('请在 Skill 库中点击有预定义流程的 Skill 进入固定模式');
      }
    });
    _updateModeIndicator();
  }

  /* ── 加载 Skill 画布（分两路：固定/探索） ─────────────────────────────── */
  function _loadSkillCanvas(skill) {
    if (!_topCanvas) return;
    let canvasData = null;
    try {
      const content = typeof skill.content === 'string'
        ? JSON.parse(skill.content)
        : (skill.content || {});
      if (content.canvas) {
        canvasData = typeof content.canvas === 'string'
          ? JSON.parse(content.canvas)
          : content.canvas;
      }
    } catch (_) {}

    if (canvasData) {
      // Skill 有预定义画布 → 自动进入固定模式
      _enterFixedMode(skill, canvasData);
    } else {
      // Skill 无预定义画布 → 询问是否进入探索模式
      if (confirm(
        `Skill「${skill.title}」没有预定义流程画布。\n` +
        `是否进入探索模式，开始为此 Skill 设计新流程？\n\n` +
        `（设计完成后可点击「转 Skill」保存）`
      )) {
        _enterExploreMode(skill);
      }
    }
  }

  /* ── 水平分隔条拖拽调整高度 ───────────────────────────────────────────── */
  function _initHDivider() {
    const $handle = document.getElementById('wfcwHDivider');
    const $panel  = document.getElementById('wfcwFlowPanel');
    if (!$handle || !$panel) return;

    let _dragging = false;
    let _startY   = 0;
    let _startH   = 0;

    $handle.addEventListener('mousedown', e => {
      e.preventDefault();
      _dragging = true;
      _startY   = e.clientY;
      _startH   = $panel.offsetHeight;
      $handle.classList.add('dragging');
      document.body.style.cursor    = 'row-resize';
      document.body.style.userSelect = 'none';
    });

    document.addEventListener('mousemove', e => {
      if (!_dragging) return;
      const delta = e.clientY - _startY;
      const newH  = Math.max(100, Math.min(450, _startH + delta));
      $panel.style.height = newH + 'px';
    });

    document.addEventListener('mouseup', () => {
      if (!_dragging) return;
      _dragging = false;
      $handle.classList.remove('dragging');
      document.body.style.cursor    = '';
      document.body.style.userSelect = '';
      localStorage.setItem(_lsk('wfcw.flowPanelH'), $panel.style.height);
    });
  }

  /* ── 画布节点事件回调 ─────────────────────────────────────────────────── */
  function _onNodeAdded(_node) {
    _pushState();
  }

  function _onNodeRemoved(_node) {
    _pushState();
  }

  /* ── 推送画布状态到主进程缓存 ─────────────────────────────────────────── */
  function _pushState() {
    if (!_wfCanvas || !_ctxOn) return;
    const nodes = _wfCanvas._nodes || [];
    if (nodes.length === 0) {
      window.electronAPI?.wfcPushCanvasState?.(null);
      return;
    }
    const nodeNames = nodes.slice(0, 4).map(n => n.label || n.type).join('|');
    const state = `画布:${nodes.length}节点; 节点:${nodeNames}${nodes.length > 4 ? '…' : ''}`;
    window.electronAPI?.wfcPushCanvasState?.(state);
  }

  /* ── 上下文感知开关 ───────────────────────────────────────────────────── */
  function _initCtxToggle() {
    const btn   = document.getElementById('wfcCtxToggle');
    const label = document.getElementById('wfcCtxLabel');
    if (!btn) return;
    btn.addEventListener('click', () => {
      _ctxOn = !_ctxOn;
      btn.classList.toggle('ctx-on', _ctxOn);
      if (label) label.textContent = _ctxOn ? '上下文 开' : '上下文 关';
      if (_ctxOn) _pushState();
      else window.electronAPI?.wfcPushCanvasState?.(null);
    });
  }

  /* ── Auth 状态（独立窗口，通过 IPC 获取，不能依赖 window.parent） ──────── */
  let _cachedAuth = { mode: 'none', token: null, user: null };

  async function _initAuth() {
    try {
      const state = await window.electronAPI?.authGetState?.();
      if (state) _cachedAuth = state;
    } catch (_) {}
    window.electronAPI?.onAuthStateChanged?.(state => {
      _cachedAuth = state;
      _syncAuthGlobals();
    });
    _syncAuthGlobals();
  }

  function _getUserGid()   { return _cachedAuth?.user?.gid || ''; }
  function _getAuthMode()  { return _cachedAuth?.mode || 'none'; }
  function _getAuthToken() { return _cachedAuth?.token || null; }

  /* ── SSE 流式 AI 对话 helpers ────────────────────────────────────────── */

  async function _fetchAiChatStreamRaw(endpoint, body, signal, callbacks) {
    const eAPI = window.electronAPI;
    if (!eAPI) { callbacks.onError?.('electronAPI 未就绪'); return; }
    const config  = await eAPI.getConfig?.().catch?.(() => ({})) || {};
    const state   = await eAPI.authGetState?.().catch?.(() => ({})) || {};
    const runtimeBase = await window.AI00RuntimeConfig?.getRuntimeBackendBase?.(config.backendUrl || '')
    const baseUrl = (runtimeBase || config.backendUrl || '').replace(/\/$/, '');
    const token   = state.token || '';

    let res;
    try {
      res = await fetch(`${baseUrl}${endpoint}`, {
        method:  'POST',
        headers: {
          'Content-Type':  'application/json',
          ...(token ? { 'Authorization': `Bearer ${token}`, 'X-AI00-Token': token } : {}),
        },
        body:   JSON.stringify(body),
        signal: signal || undefined,
      });
    } catch (e) {
      if (e.name === 'AbortError') return;
      callbacks.onError?.(e.message || '网络错误');
      return;
    }

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      callbacks.onError?.(err.detail || `HTTP ${res.status}`);
      return;
    }

    const reader  = res.body.getReader();
    const decoder = new TextDecoder();
    let   buf     = '';

    while (true) {
      let done, value;
      try { ({ done, value } = await reader.read()); } catch (_) { break; }
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split('\n');
      buf = lines.pop() ?? '';
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        let evt;
        try { evt = JSON.parse(line.slice(6)); } catch (_) { continue; }
        const t = evt.type;
        if      (t === 'token')            callbacks.onToken?.(evt.content || '');
        else if (t === 'tool_start')       callbacks.onToolStart?.(evt.name);
        else if (t === 'tool_end')         callbacks.onToolEnd?.(evt.name, evt.ok, evt.result);
        else if (t === 'done')             callbacks.onDone?.(evt.session_id);
        else if (t === 'confirm_required') callbacks.onConfirmRequired?.(evt);
        else if (t === 'error')            callbacks.onError?.(evt.message || '未知错误');
      }
    }
  }

  async function _fetchAiChatStream(text, sessionGid, ctxObj, signal, callbacks) {
    return _fetchAiChatStreamRaw('/api/ai/chat/stream', {
      message:    text,
      session_id: sessionGid || '',
      user_gid:   _getUserGid(),
      auth_token: _getAuthToken() || '',
      context:    ctxObj || {},
    }, signal, callbacks);
  }

  /* ── 为底部容器 iframe 子页面暴露 _cloudFetch 和 _authMode ─────────────── */
  // 子页面通过 window.top._cloudFetch / window.top._authMode 访问
  function _syncAuthGlobals() {
    window._authMode = _cachedAuth?.mode || 'local';
    window._authUser = _cachedAuth?.user || null;
  }

  /* ── injectToAI：沙盘节点调用此函数将用户操作结果注入 AI 对话 ─────────── */
  window.injectToAI = function(text) {
    if (!text) return;
    window.electronAPI?.wfcInjectToChat?.(text).catch(() => {});
  };

  // window._cloudFetch 已由 preload.js 的 contextBridge.exposeInMainWorld('_cloudFetch', ...)
  // 注入为只读属性，此处不再重复赋值（strict mode 下会抛 TypeError）。

  /* ── 当前画布 GID ────────────────────────────────────────────────────── */
  let _currentCanvasGid = null;

  /* ── Toast 提示 ─────────────────────────────────────────────────────── */
  function _showToast(msg) {
    const t = document.createElement('div');
    t.style.cssText = `position:fixed;bottom:48px;left:50%;transform:translateX(-50%);
      background:var(--bg2);border:1px solid var(--border);color:var(--text);
      padding:6px 14px;border-radius:6px;font-size:11px;z-index:9999;
      box-shadow:0 2px 8px rgba(0,0,0,.3);pointer-events:none;`;
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 2200);
  }

  /* ── 画布操作栏按钮 ──────────────────────────────────────────────────── */

  // 注入到 AI 对话
  document.getElementById('wfcInjectBtn')?.addEventListener('click', () => {
    if (!_wfCanvas) return;
    const txt = _wfCanvas.toInjectText?.() || '';
    if (!txt) { _showToast('画布为空'); return; }
    window.electronAPI?.wfcInjectToChat?.(txt)
      .then(() => _showToast('已发送到对话'))
      .catch(() => _showToast('发送失败，请先打开 AI 助手窗口'));
  });

  // ── 工具函数：从上层流程面板提取 canvas JSON ─────────────────────────
  function _getFlowCanvasJSON() {
    if (!_topCanvas) return null;
    try { return _topCanvas.toJSON(); } catch (_) { return null; }
  }

  // 转 Skill（从当前执行流程另存为新 Skill）
  document.getElementById('wfcToSkillBtn')?.addEventListener('click', async () => {
    const canvasData = _getFlowCanvasJSON();
    if (!canvasData || (canvasData.nodes || []).length === 0) {
      _showToast('执行流程为空，无法转 Skill');
      return;
    }
    const title = prompt('请输入新 Skill 名称（显示名）：',
      _fixedSkill ? `${_fixedSkill.title} (副本)` : '新 Skill');
    if (!title?.trim()) return;
    const name = title.trim().toLowerCase().replace(/\s+/g, '_').replace(/[^\w\u4e00-\u9fa5]/g, '');
    const content = JSON.stringify({ canvas: canvasData });
    const res = await window._cloudFetch?.('/api/skills', {
      method: 'POST',
      body: JSON.stringify({
      name, title: title.trim(),
      skill_type: 'prompt',
      scope: 'private',
      content,
      owner_gid: _getUserGid(),
    })});
    if (res?.error) { _showToast(`保存失败：${res.error}`); return; }
    _showToast(`已创建 Skill「${title.trim()}」`);
    // 刷新侧边栏 Skill 列表
    _initSkillsPanel();
  });

  // 更新 Skill（将本次调整写回原 Skill，仅固定模式下可用）
  document.getElementById('wfcUpdateSkillBtn')?.addEventListener('click', async () => {
    if (!_fixedSkill) { _showToast('未加载任何 Skill'); return; }
    const canvasData = _getFlowCanvasJSON();
    if (!canvasData) { _showToast('执行流程为空'); return; }
    if (!confirm(`将本次执行流程的修改更新到 Skill「${_fixedSkill.title}」？\n（原 Skill 内容将被覆盖）`)) return;

    // 解析原有 content，替换 canvas 字段
    let contentObj = {};
    try {
      contentObj = typeof _fixedSkill.content === 'string'
        ? JSON.parse(_fixedSkill.content)
        : (_fixedSkill.content || {});
    } catch (_) {}
    contentObj.canvas = canvasData;

    const res = await window._cloudFetch?.(`/api/skills/${_fixedSkill.gid}`, {
      method: 'PUT',
      body: JSON.stringify({
      gid: _fixedSkill.gid,
      content: JSON.stringify(contentObj),
    })});
    if (res?.error) { _showToast(`更新失败：${res.error}`); return; }
    // 同步本地 _fixedSkill 引用
    _fixedSkill = { ..._fixedSkill, content: JSON.stringify(contentObj) };
    _showToast(`Skill「${_fixedSkill.title}」已更新`);
    _initSkillsPanel();
  });

  // 清空
  document.getElementById('wfcClearBtn')?.addEventListener('click', () => {
    if (!_wfCanvas) return;
    if (_wfCanvas._nodes.length === 0 && _wfCanvas._conns.length === 0) return;
    if (confirm('确认清空画布？')) {
      _wfCanvas._clear();
      _wfCanvas._addLane('主流程');
      _pushState();
    }
  });

  // 保存
  document.getElementById('wfcSaveBtn')?.addEventListener('click', async () => {
    if (!_wfCanvas) return;
    const name = prompt('请输入画布名称：', '未命名画布');
    if (!name) return;
    const res = await _wfCanvas.save(name, _getUserGid(), _currentCanvasGid);
    if (res?.gid) {
      _currentCanvasGid = res.gid;
      _showToast('已保存：' + (res.title || name));
    } else {
      _showToast('保存失败，请重试');
    }
  });

  // 加载
  document.getElementById('wfcLoadBtn')?.addEventListener('click', async () => {
    if (!_wfCanvas) return;
    const saves = await _wfCanvas.listSaves(_getUserGid());
    if (!saves || saves.length === 0) { _showToast('暂无保存的画布'); return; }
    const names = saves.map((s, i) => `${i + 1}. ${s.title || s.gid}`).join('\n');
    const idx = prompt(`请选择要加载的画布（输入序号）：\n${names}`);
    const n = parseInt(idx) - 1;
    if (isNaN(n) || n < 0 || n >= saves.length) return;
    const res = await _wfCanvas.load(saves[n].gid);
    if (res?.data) {
      _currentCanvasGid = saves[n].gid;
      _showToast('已加载：' + (saves[n].title || saves[n].gid));
      _pushState();
    } else {
      _showToast('加载失败');
    }
  });

  // 模式切换（探索/执行）
  const $modeBtn = document.getElementById('wfcwModeBtn');
  $modeBtn?.addEventListener('click', () => {
    if (!_wfCanvas) return;
    _wfCanvas._mode = _wfCanvas._mode === 'explore' ? 'execute' : 'explore';
    $modeBtn.dataset.mode = _wfCanvas._mode;
    $modeBtn.textContent  = _wfCanvas._mode === 'execute' ? '执行模式' : '探索模式';
  });

  /* ── 从 AI 助手接收 generate_canvas / bop_to_canvas 数据（IPC 路径） ──── */
  window.electronAPI?.onWfcReceiveData?.(data => {
    if (!_wfCanvas || !data) return;
    _wfCanvas.fromJSON(data);
    _pushState();
    _showToast('画布已更新');
    document.getElementById('wfcwCanvasEmpty')?.classList.add('hidden');
  });

  /* ── 从 AI 助手接收 open_in_container 指令：在底部容器新增 iframe 标签页 ── */
  window.electronAPI?.onWfcAddBottomTab?.(opts => {
    if (!_wfCanvas || !opts?.tabId || !opts?.url) return;
    _wfCanvas.addBottomTab(opts.tabId, opts.title || opts.tabId, 'local', { url: opts.url });
    _showToast('已打开：' + (opts.title || opts.tabId));
  });

  /* ── 容器卡片覆盖面板 ─────────────────────────────────────────────────── */
  let _ccCurrentNode  = null;
  let _ccConfigNode   = null;

  const _CC_MODE_LABELS = {
    row_detail: '行详情', markdown: 'MD 文档', webview: '网页预览',
    pdf: 'PDF', image_gallery: '图片集', richtext: '富文本',
  };
  const _CC_MODE_FIELDS = {
    row_detail:    [
      { key: 'item_type', label: '条目类型', type: 'select',
        options: ['task','issue','knowledge','rule','craft_element','factory_resource'] },
      { key: 'gid',    label: 'GID',   type: 'text', placeholder: '条目 GID' },
      { key: 'source', label: '数据源', type: 'select', options: ['local','cloud'] },
    ],
    markdown:      [
      { key: 'path',    label: '文件路径', type: 'text',     placeholder: '本地 .md 路径（可选）' },
      { key: 'content', label: '直接内容', type: 'textarea', placeholder: '直接输入 Markdown（可选）' },
    ],
    webview:       [
      { key: 'url',   label: 'URL',  type: 'text', placeholder: 'https://...' },
      { key: 'title', label: '标题', type: 'text', placeholder: '（可选）' },
    ],
    pdf:           [
      { key: 'path',  label: '文件路径', type: 'text', placeholder: '本地 PDF 路径' },
      { key: 'title', label: '标题',     type: 'text', placeholder: '（可选）' },
    ],
    image_gallery: [
      { key: 'urls', label: '图片 URL（每行/逗号分隔）', type: 'textarea', placeholder: 'https://... ' },
    ],
    richtext:      [
      { key: 'item_gid', label: '条目 GID', type: 'text', placeholder: '富文本记录 GID' },
      { key: 'scope',    label: 'Scope',    type: 'text', placeholder: 'general' },
    ],
  };

  function _buildCcUrl(params) {
    if (!params || !params.mode) return 'about:blank';
    const base = '../container_card/index.html';
    const p    = new URLSearchParams({ mode: params.mode });
    const b64  = s => { try { return btoa(unescape(encodeURIComponent(s))); } catch { return ''; } };
    switch (params.mode) {
      case 'row_detail':
        p.set('item_type', params.item_type || 'task');
        p.set('gid',    params.gid    || '');
        p.set('source', params.source || 'local');
        break;
      case 'markdown':
        if (params.path)    p.set('path',    b64(params.path));
        if (params.content) p.set('content', b64(params.content));
        p.set('editable', 'true');
        break;
      case 'webview':
        p.set('url',   params.url   || '');
        p.set('title', b64(params.title || params.url || ''));
        break;
      case 'pdf':
        p.set('path',  b64(params.path  || ''));
        p.set('title', b64(params.title || ''));
        break;
      case 'image_gallery': {
        const imgs = (params.urls || '').split(/[\n,]/).map(u => u.trim()).filter(Boolean).map(url => ({ url }));
        p.set('attachments', btoa(JSON.stringify(imgs)));
        p.set('editable', 'false');
        break;
      }
      case 'richtext':
        p.set('item_gid', params.item_gid || '');
        p.set('scope',    params.scope    || 'general');
        break;
    }
    return `${base}?${p.toString()}`;
  }

  function _openCcPanel(node) {
    _ccCurrentNode = node;
    const params = node.params || {};
    const modeLabel = _CC_MODE_LABELS[params.mode] || params.mode || '内容预览';
    document.getElementById('wfcwCcPanelTitle').textContent = node.label || modeLabel;
    document.getElementById('wfcwCcModeBadge').textContent  = (params.mode || 'CC').slice(0, 6).toUpperCase();
    const $iframe = document.getElementById('wfcwCcIframe');
    if (params.mode) {
      $iframe.src = _buildCcUrl(params);
    } else {
      $iframe.srcdoc = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#888;font-family:sans-serif;font-size:12px">尚未配置内容，请点击 ⚙ 进行配置</div>';
    }
    document.getElementById('wfcwCcPanel').classList.add('open');
  }

  function _closeCcPanel() {
    document.getElementById('wfcwCcPanel')?.classList.remove('open');
    setTimeout(() => {
      const $p = document.getElementById('wfcwCcPanel');
      if (!$p?.classList.contains('open'))
        document.getElementById('wfcwCcIframe').src = 'about:blank';
    }, 300);
  }

  function _openCcConfig(node) {
    _ccConfigNode = node;
    const params  = node.params || {};
    document.getElementById('wfcwCcCfgLabel').value = node.label || '';
    const $mode = document.getElementById('wfcwCcCfgMode');
    $mode.value = params.mode || 'row_detail';
    _renderCcCfgFields(params.mode || 'row_detail', params);
    document.getElementById('wfcwCcCfgOverlay').classList.add('open');
  }

  function _closeCcConfig() {
    document.getElementById('wfcwCcCfgOverlay')?.classList.remove('open');
    _ccConfigNode = null;
  }

  function _renderCcCfgFields(mode, params) {
    const $fields = document.getElementById('wfcwCcCfgFields');
    if (!$fields) return;
    $fields.innerHTML = '';
    (_CC_MODE_FIELDS[mode] || []).forEach(f => {
      const row = document.createElement('div');
      row.className = 'wfcw-cc-cfg-row';
      const lbl = document.createElement('label');
      lbl.textContent = f.label;
      row.appendChild(lbl);
      let inp;
      if (f.type === 'select') {
        inp = document.createElement('select');
        f.options.forEach(o => {
          const opt = document.createElement('option');
          opt.value = o; opt.textContent = o;
          if ((params || {})[f.key] === o) opt.selected = true;
          inp.appendChild(opt);
        });
      } else if (f.type === 'textarea') {
        inp = document.createElement('textarea');
        inp.rows = 3;
        inp.placeholder = f.placeholder || '';
        inp.value = (params || {})[f.key] || '';
      } else {
        inp = document.createElement('input');
        inp.type = 'text';
        inp.placeholder = f.placeholder || '';
        inp.value = (params || {})[f.key] || '';
      }
      inp.id = `wfcwCcF_${f.key}`;
      row.appendChild(inp);
      $fields.appendChild(row);
    });
  }

  function _saveCcConfig() {
    if (!_ccConfigNode || !_wfCanvas) return;
    const mode  = document.getElementById('wfcwCcCfgMode')?.value || 'row_detail';
    const label = document.getElementById('wfcwCcCfgLabel')?.value.trim();
    const params = { mode };
    (_CC_MODE_FIELDS[mode] || []).forEach(f => {
      const el = document.getElementById(`wfcwCcF_${f.key}`);
      if (el) params[f.key] = el.value;
    });
    _ccConfigNode.label  = label || _CC_MODE_LABELS[mode] || mode;
    _ccConfigNode.params = params;
    _wfCanvas._sbRender?.();
    _closeCcConfig();
    // 若面板已打开该节点则刷新
    if (_ccCurrentNode?.id === _ccConfigNode.id) _openCcPanel(_ccConfigNode);
    else _openCcPanel(_ccConfigNode);
    _showToast('已保存');
  }

  function _initCcPanel() {
    // 事件委托：监听底部容器面板冒泡来的 container 事件
    document.getElementById('wfcBcPanes')?.addEventListener('wfc:container-open',   e => _openCcPanel(e.detail.node));
    document.getElementById('wfcBcPanes')?.addEventListener('wfc:container-config',  e => _openCcConfig(e.detail.node));
    // 面板按钮
    document.getElementById('wfcwCcClose')?.addEventListener('click', _closeCcPanel);
    document.getElementById('wfcwCcCfgBtn')?.addEventListener('click', () => { if (_ccCurrentNode) _openCcConfig(_ccCurrentNode); });
    // 配置弹窗
    document.getElementById('wfcwCcCfgClose')?.addEventListener('click', _closeCcConfig);
    document.getElementById('wfcwCcCfgCancel')?.addEventListener('click', _closeCcConfig);
    document.getElementById('wfcwCcCfgSave')?.addEventListener('click', _saveCcConfig);
    document.getElementById('wfcwCcCfgMode')?.addEventListener('change', e => {
      _renderCcCfgFields(e.target.value, _ccConfigNode?.params || {});
    });
    document.getElementById('wfcwCcCfgOverlay')?.addEventListener('click', e => {
      if (e.target === document.getElementById('wfcwCcCfgOverlay')) _closeCcConfig();
    });
  }

  /* ── 话题讨论左边栏 ───────────────────────────────────────────────────── */
  let _wfcTopics = [];

  function _initTopicPanel() {
    const $org = document.getElementById('wfcwTopicOrganize');

    // "→ 对话"：把话题选择状态序列化，注入 AI 对话输入框
    $org?.addEventListener('click', () => {
      if (_wfcTopics.length === 0) { _showToast('暂无话题讨论内容'); return; }
      const lines = ['【话题讨论摘要】'];
      _wfcTopics.forEach(t => {
        lines.push(`\n${t.title}`);
        (t.questions || []).forEach(q => {
          const sel = (q.options || []).filter(o => o.selected).map(o => o.label).join('、');
          lines.push(`  Q: ${q.text}`);
          if (sel) lines.push(`  A: ${sel}`);
          if (q.freeText) lines.push(`  (${q.freeText})`);
        });
      });
      lines.push('\n请根据以上话题讨论结果生成工作流画布。');
      window.electronAPI?.wfcInjectToChat?.(lines.join('\n'))
        .then(() => _showToast('已发送到对话'))
        .catch(() => _showToast('请先打开 AI 助手窗口'));
    });

    // 监听从 AI 助手推送来的话题
    window.electronAPI?.onWfcReceiveTopic?.(topic => {
      if (!topic) return;
      _importWfcTopic(topic);
      _showToast('新话题讨论已到达');
    });
  }

  function _importWfcTopic(data) {
    const topic = {
      id:        'wt_' + Date.now(),
      title:     data.title || '话题',
      questions: (data.questions || []).map(q => ({
        id:       q.id || ('q' + Math.random().toString(36).slice(2, 6)),
        text:     q.text || q.question || '',
        options:  (q.options || []).map(o => ({
          label:    typeof o === 'string' ? o : (o.label || o.text || String(o)),
          selected: false,
        })),
        freeText: '',
      })),
    };
    _wfcTopics.push(topic);

    // 隐藏空状态提示
    const $empty = document.getElementById('wfcwTopicEmpty');
    if ($empty) $empty.style.display = 'none';

    // 自动展开话题讨论区
    document.getElementById('wfcwTopicSection')?.classList.remove('collapsed');

    _renderWfcTopics();
    _updateTopicBadge();
  }

  function _updateTopicBadge() {
    const $badge = document.getElementById('wfcwTopicBadge');
    if (!$badge) return;
    if (_wfcTopics.length > 0) {
      $badge.textContent = _wfcTopics.length;
      $badge.style.display = '';
    } else {
      $badge.style.display = 'none';
    }
  }

  function _renderWfcTopics() {
    const $body = document.getElementById('wfcwTopicBody');
    if (!$body) return;
    $body.innerHTML = '';
    _wfcTopics.forEach(topic => {
      const $t = document.createElement('div');
      $t.className = 'wfcw-tp-topic';
      const $title = document.createElement('div');
      $title.className = 'wfcw-tp-topic-title';
      $title.textContent = topic.title;
      $t.appendChild($title);

      const $qs = document.createElement('div');
      $qs.className = 'wfcw-tp-questions';
      (topic.questions || []).forEach(q => {
        const $q = document.createElement('div');
        $q.className = 'wfcw-tp-question';
        const $qt = document.createElement('div');
        $qt.className = 'wfcw-tp-q-text';
        $qt.textContent = q.text;
        $q.appendChild($qt);
        const $opts = document.createElement('div');
        $opts.className = 'wfcw-tp-opts';
        (q.options || []).forEach(opt => {
          const $o = document.createElement('button');
          $o.className = 'wfcw-tp-opt' + (opt.selected ? ' selected' : '');
          $o.textContent = opt.label;
          $o.addEventListener('click', () => {
            opt.selected = !opt.selected;
            $o.classList.toggle('selected', opt.selected);
          });
          $opts.appendChild($o);
        });
        $q.appendChild($opts);
        $qs.appendChild($q);
      });
      $t.appendChild($qs);
      $body.appendChild($t);
    });
  }

  /* ── AI 对话面板（精简版） ───────────────────────────────────────────────── */
  let _apSending = false;
  let _apSessionGid = null;  // 与 ai_chat_bridge 保持同一 session
  let _streamAbortCtrl    = null;  // 当前流式请求的 AbortController（用于停止按钮）
  let _streamAbortFinalize = null; // 当前流气泡的 finalize 函数（中断时调用）

  // 工具名友好显示映射
  const _TOOL_LABELS = {
    search:              '全文搜索',
    list_tasks:          '列出任务',
    get_task:            '获取任务',
    list_issues:         '列出问题',
    get_issue:           '获取问题',
    list_projects:       '列出项目',
    list_bop_versions:   '列出 BOP 版本',
    get_bop_entries:     '获取工艺条目',
    search_bop_entries:  '搜索工艺条目',
    web_search:          '网络搜索',
    fetch_webpage:       '读取网页',
    calculate:           '数学计算',
    save_preference:     '保存偏好',
    list_preferences:    '查询偏好',
    read_log:            '读取日志',
    read_file:           '读取文件',
    search_code:         '搜索代码',
    generate_canvas:     '生成画布',
    bop_to_canvas:       'BOP 可视化',
    create_discussion_topic: '创建话题讨论',
    open_in_container:   '打开页面',
  };

  function _appendAiMsg(role, content) {
    const $msgs = document.getElementById('wfcwAiMsgs');
    if (!$msgs) return null;
    const $wrap = document.createElement('div');
    $wrap.className = 'wfc-apm ' + role;

    if (role === 'assistant') {
      const $av = document.createElement('div');
      $av.className = 'wfc-apm-av';
      $av.innerHTML = `<svg viewBox="0 0 32 32" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg">
        <circle cx="16" cy="16" r="16" fill="#CBA6F7"/>
        <text x="16" y="21" text-anchor="middle" font-size="15" font-family="system-ui,sans-serif" font-weight="600" fill="#fff">柔</text>
      </svg>`;
      $wrap.appendChild($av);
    }

    const $bub = document.createElement('div');
    $bub.className = 'wfc-apm-bub';
    if (role === 'assistant' && typeof marked !== 'undefined') {
      $bub.innerHTML = marked.parse(content);
    } else {
      $bub.textContent = content;
    }
    $wrap.appendChild($bub);
    $msgs.appendChild($wrap);
    $msgs.scrollTop = $msgs.scrollHeight;
    // 未读计数（聊天窗关闭时）
    if (role === 'assistant') {
      const $chat  = document.getElementById('wfcwFloatChat');
      const $badge = document.getElementById('wfcwFbBadge');
      const $ball  = document.getElementById('wfcwFloatBall');
      if ($chat?.style.display === 'none' && $badge) {
        const n = (parseInt($badge.textContent) || 0) + 1;
        $badge.textContent = n; $badge.style.display = '';
        $ball?.classList.add('pulsing');
      }
    }
    return $bub;
  }

  async function _sendAiMsg() {
    if (_apSending) return;
    const $inp = document.getElementById('wfcwAiInp');
    let text = ($inp?.value || '').trim();
    if (!text) return;
    $inp.value = '';

    // @skill 检测：消息中含 @技能名 时自动加载对应 Skill 画布，并从文本中剔除该 @mention
    let _skillMentionLoaded = false;
    const atMatches = [...text.matchAll(/@([\u4e00-\u9fa5\w\s·—\-]+?)(?=[\s,，.。!！?？@]|$)/g)];
    for (const m of atMatches) {
      const q = m[1].trim().toLowerCase();
      if (!q) continue;
      const found = _skillsList.find(s =>
        s.title.toLowerCase() === q || (s.name || '').toLowerCase() === q
      );
      if (found) {
        _loadSkillCanvas(found);
        text = text.replace(m[0], '').trim();   // 从发送文本中剔除 @mention
        _skillMentionLoaded = true;
        break; // 只处理第一个匹配的 @skill
      }
    }
    // 若输入内容仅是 @skill 且画布已加载，不再向 AI 发送空消息
    if (_skillMentionLoaded && !text) {
      _showToast(`已加载「${_fixedSkill?.title || '执行流程'}」，点击「执行」开始运行`);
      return;
    }

    _apSending = true;
    const $stopBtn = document.getElementById('wfcwAiStop');
    if ($stopBtn) $stopBtn.style.display = 'inline-flex';

    _appendAiMsg('user', text);

    // 上下文感知：始终带 current_page=wfc_canvas，让系统提示注入 WFC 模式指令
    let ctxObj = { current_page: 'wfc_canvas' };
    if (_ctxOn && _wfCanvas) {
      const nodes = _wfCanvas._nodes || [];
      if (nodes.length > 0) {
        ctxObj.canvas_context = `当前工作流画布共有 ${nodes.length} 个节点：${
          nodes.slice(0, 6).map(n => n.label || n.type).join('、')
        }${nodes.length > 6 ? '…' : ''}`;
      }
      if (_fixedSkill) {
        ctxObj.canvas_context = (ctxObj.canvas_context ? ctxObj.canvas_context + '；' : '')
          + `当前 Skill：${_fixedSkill.title}`;
      }
    }

    // 创建流式 assistant 气泡
    const $msgs = document.getElementById('wfcwAiMsgs');
    const $wrap = document.createElement('div');
    $wrap.className = 'wfc-apm assistant';
    const $av = document.createElement('div');
    $av.className = 'wfc-apm-av';
    $av.innerHTML = `<svg viewBox="0 0 32 32" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg">
      <circle cx="16" cy="16" r="16" fill="#CBA6F7"/>
      <text x="16" y="21" text-anchor="middle" font-size="15" font-family="system-ui,sans-serif" font-weight="600" fill="#fff">柔</text>
    </svg>`;
    $wrap.appendChild($av);
    const $bub = document.createElement('div');
    $bub.className = 'wfc-apm-bub';
    // 光标占位
    const $cursor = document.createElement('span');
    $cursor.className = 'wfc-stream-cursor';
    $bub.appendChild($cursor);
    $wrap.appendChild($bub);
    $msgs?.appendChild($wrap);
    $msgs && ($msgs.scrollTop = $msgs.scrollHeight);

    let streamText = '';
    let toolRows = {};  // name → element

    function _appendToolRow(name, state) {
      const label = _TOOL_LABELS[name] || name;
      if (!toolRows[name]) {
        const $row = document.createElement('div');
        $row.className = 'wfc-tool-row';
        $bub.insertBefore($row, $cursor);
        toolRows[name] = $row;
      }
      const $row = toolRows[name];
      if (state === 'running') {
        $row.innerHTML = `<span class="wfc-tool-spin">⚙</span> ${_esc(label)}…`;
        $row.className = 'wfc-tool-row running';
      } else if (state === 'ok') {
        $row.innerHTML = `<span class="wfc-tool-ok">✓</span> ${_esc(label)}`;
        $row.className = 'wfc-tool-row done';
      } else {
        $row.innerHTML = `<span class="wfc-tool-err">✗</span> ${_esc(label)}`;
        $row.className = 'wfc-tool-row error';
      }
    }

    function _finalizeMarkdown() {
      // 移除光标，渲染 markdown
      $cursor.remove();
      if (streamText) {
        const textNode = document.createElement('div');
        textNode.className = 'wfc-stream-text';
        if (typeof marked !== 'undefined') {
          textNode.innerHTML = marked.parse(streamText);
        } else {
          textNode.textContent = streamText;
        }
        $bub.appendChild(textNode);
      }
      $msgs && ($msgs.scrollTop = $msgs.scrollHeight);
    }

    // 暴露给停止按钮：用于中断时渲染已收到的部分文本
    _streamAbortFinalize = () => {
      const $live = $bub.querySelector('.wfc-stream-text-live');
      if ($live) $live.remove();
      _finalizeMarkdown();
    };

    // SSE 流式调用（云端 REST API）
    _streamAbortCtrl = new AbortController();
    await _fetchAiChatStream(
      text, _apSessionGid, ctxObj,
      _streamAbortCtrl.signal,
      {
        onToken(chunk) {
          streamText += chunk;
          let $t = $bub.querySelector('.wfc-stream-text-live');
          if (!$t) {
            $t = document.createElement('span');
            $t.className = 'wfc-stream-text-live';
            $bub.insertBefore($t, $cursor);
          }
          $t.textContent = streamText;
          $msgs && ($msgs.scrollTop = $msgs.scrollHeight);
        },
        onToolStart(name) { _appendToolRow(name, 'running'); },
        onToolEnd(name, ok, result) {
          _appendToolRow(name, ok ? 'ok' : 'error');
          if (!result) return;
          if ((name === 'generate_canvas' || name === 'bop_to_canvas') &&
              result.status === 'canvas_generated' && result.canvas) {
            if (_wfCanvas) {
              _wfCanvas.fromJSON(result.canvas);
              _pushState();
              _showToast('画布已更新');
              document.getElementById('wfcwCanvasEmpty')?.classList.add('hidden');
            }
          }
          if (name === 'run_skill_canvas' && result.node_results) {
            _updateSidebarStatus(result.node_results);
            if (result.status === 'paused' && result.pause_token) {
              _appendHumanApprovalCard(
                result.halted_label || '人工步骤',
                result.pause_token,
                result.skill_title,
                result.node_results,
                result.context_summary,
                result.collect_fields || null,
                result.canvas_layout  || null,
              );
            } else {
              _showToast(result.status === 'completed' ? '✅ Skill 执行完成' : `⚠️ Skill 执行${result.status}`);
            }
          }
          if (name === 'open_in_container' && result.page_id && _wfCanvas?.addBottomTab) {
            const pageUrls = {
              task: '/web/task/index.html', issue: '/web/issue/index.html',
              bop: '/web/bop/index.html', bop_lineage: '/web/lineage_view/index.html',
              canvas: '/web/canvas/canvas_shell.html', knowledge_hub: '/web/knowledge_hub/index.html',
            };
            const url = result.url || pageUrls[result.page_id] || '';
            if (url) _wfCanvas.addBottomTab(result.page_id, result.title || result.page_id, 'local', { url });
          }
          if (name === 'create_discussion_topic' && result.status === 'topic_created' && result.topic) {
            _importWfcTopic(result.topic);
          }
        },
        onDone(sessionId) {
          if (sessionId) _apSessionGid = sessionId;
          _streamAbortCtrl    = null;
          _streamAbortFinalize = null;
          const $live = $bub.querySelector('.wfc-stream-text-live');
          if ($live) $live.remove();
          _finalizeMarkdown();
        },
        onConfirmRequired(evt) {
          if (evt.session_id) _apSessionGid = evt.session_id;
          const $live = $bub.querySelector('.wfc-stream-text-live');
          if ($live) $live.remove();
          _finalizeMarkdown();
          _appendConfirmBubble(evt);
        },
        onError(msg) {
          _streamAbortCtrl    = null;
          _streamAbortFinalize = null;
          $cursor.remove();
          $bub.innerHTML = `<span style="color:var(--red,#f38ba8)">❌ ${_esc(msg)}</span>`;
          $msgs && ($msgs.scrollTop = $msgs.scrollHeight);
        },
      }
    );

    _apSending = false;
    const $stopBtnEnd = document.getElementById('wfcwAiStop');
    if ($stopBtnEnd) $stopBtnEnd.style.display = 'none';
  }

  function _appendConfirmBubble(evt) {
    // 复用现有确认逻辑（在 AI 对话页面中可能有 _renderPendingConfirm，此处简单提示）
    const $msgs = document.getElementById('wfcwAiMsgs');
    if (!$msgs) return;
    const $wrap = document.createElement('div');
    $wrap.className = 'wfc-apm assistant';
    const $bub = document.createElement('div');
    $bub.className = 'wfc-apm-bub wfc-confirm-bub';
    $bub.innerHTML = `⚠️ 即将执行：<b>${_esc(evt.preview || evt.tool_name)}</b><br>
      <button class="wfc-confirm-btn" style="margin-top:6px;background:var(--green,#a6e3a1);color:#1e1e2e;border:none;padding:3px 10px;border-radius:5px;cursor:pointer">确认执行</button>
      <button class="wfc-confirm-btn-cancel" style="margin-left:6px;background:var(--surface0,#313244);color:var(--text);border:none;padding:3px 10px;border-radius:5px;cursor:pointer">取消</button>`;
    $wrap.appendChild($bub);
    $msgs.appendChild($wrap);
    $msgs.scrollTop = $msgs.scrollHeight;
    $bub.querySelector('.wfc-confirm-btn')?.addEventListener('click', async () => {
      $bub.innerHTML = '⏳ 执行中…';
      try {
        const cf = window._cloudFetch;
        if (!cf) { $bub.innerHTML = '❌ _cloudFetch 未就绪'; return; }
        await new Promise(resolveConfirm => {
          _fetchAiChatStreamRaw('/api/ai/confirm', {
            session_gid:   _apSessionGid,
            confirm_token: evt.confirm_token,
            tool_name:     evt.tool_name,
            tool_use_id:   evt.tool_use_id,
            auth_token:    _getAuthToken() || '',
          }, null, {
            onToken(chunk)    { /* ignore tokens from confirm continuation */ },
            onToolStart()     {},
            onToolEnd()       {},
            onDone(sessionId) {
              if (sessionId) _apSessionGid = sessionId;
              $bub.remove(); $wrap.remove();
              resolveConfirm();
            },
            onConfirmRequired(e2) { _appendConfirmBubble(e2); resolveConfirm(); },
            onError(msg)      { $bub.innerHTML = `❌ 执行失败: ${_esc(msg)}`; resolveConfirm(); },
          });
        });
      } catch(e) {
        $bub.innerHTML = `❌ 执行失败: ${_esc(e.message)}`;
      }
    });
    $bub.querySelector('.wfc-confirm-btn-cancel')?.addEventListener('click', () => {
      $wrap.remove();
    });
  }

  /* ── 重置交互画布 ──────────────────────────────────────────────────────── */

  function _showResetBtn(haltMsg) {
    const $bar = document.getElementById('wfcwHaltedBar');
    const $msg = document.getElementById('wfcwHaltedMsg');
    if (!$bar) return;
    if ($msg) $msg.textContent = haltMsg ? haltMsg.slice(0, 60) : '流程已中止';
    $bar.classList.remove('hidden');
  }

  function _resetInteractionCanvas() {
    _skillSandbox?.hide();
    document.getElementById('wfcwHaltedBar')?.classList.add('hidden');
    _approvalStep = 1;
    _injectedResultNodes = new Set();
    _pendingResultNodes  = [];
    _lastNodeResults     = {};
    document.getElementById('wfcwFsRunBtn')?.classList.remove('running');
  }

  document.getElementById('wfcwResetBtn')?.addEventListener('click', _resetInteractionCanvas);

  /* ── Human 节点暂停：在交互画布里渲染 human_approval 节点 ──────────────── */

  // 下一个审批节点插入的步骤列（每步骤内部递增，切换步骤时重置为 1）
  let _approvalStep = 1;
  // 已注入结果节点的 nodeId 集合（防重复注入，整次运行内不重置）
  let _injectedResultNodes = new Set();
  // 当前步骤的上下文结果节点缓冲（两次 human_approval 之间积累，切换时重播）
  let _pendingResultNodes = [];  // [{label, params}]
  // 跨步骤积累的节点结果（用于 BOP Canvas 渲染时获取 version_gid 等上下文）
  let _lastNodeResults = {};

  /** 模板表达式解析：{{n5.gid||u0.version_gid}} → 第一个非空值 */
  function _resolveTemplate(tpl, nodeResults) {
    if (typeof tpl !== 'string') return tpl;
    return tpl.replace(/\{\{([^}]+)\}\}/g, (_, expr) => {
      for (const seg of expr.split('||')) {
        const parts = seg.trim().split('.');
        const nodeId = parts[0];
        const field  = parts.slice(1).join('.');
        const val = nodeResults?.[nodeId]?.[field];
        if (val) return val;
      }
      return '';
    });
  }

  /** 预解析 collect_fields 中 source_param 的模板占位符 */
  function _resolveCollectFields(collectFields, nodeResults) {
    if (!Array.isArray(collectFields) || !nodeResults) return collectFields;
    return collectFields.map(f => {
      if (!f.source_param) return f;
      const resolved = {};
      for (const [k, v] of Object.entries(f.source_param)) {
        resolved[k] = _resolveTemplate(v, nodeResults);
      }
      return { ...f, _resolved_source_param: resolved };
    });
  }

  function _appendHumanApprovalCard(nodeLabel, pauseToken, skillTitle, nodeResults, contextSummary, collectFields, canvasLayout) {
    if (!_skillSandbox) return;

    // 切换步骤：清空沙盘，重播上下文结果节点
    _skillSandbox.clearForInteraction(canvasLayout || {});
    _approvalStep = 1;

    // 有多列（column_labels）时结果放第 1 列，审批放最后列；否则全部堆在第 1 列
    const columns = canvasLayout?.column_labels;
    const hasCols = Array.isArray(columns) && columns.length > 0;
    const approvalStep = hasCols ? columns.length : 1;

    for (const n of _pendingResultNodes) {
      _skillSandbox.addNode('result_list', n.label, 0, hasCols ? 1 : _approvalStep++, n.params);
    }
    _pendingResultNodes = [];

    // 构建 context 文字
    const ctxItems = Array.isArray(contextSummary) && contextSummary.length
      ? contextSummary
      : _buildLocalContextSummary(nodeResults);
    const contextText = ctxItems.map(it => it.text || '').filter(Boolean).join('\n').slice(0, 200);

    // 预解析 collect_fields 中 source_param 的模板占位符
    const resolvedFields = _resolveCollectFields(collectFields, nodeResults);

    _approvalStep = approvalStep + 1;
    _skillSandbox.addNode('human_approval', nodeLabel, 0, approvalStep, {
      _pause_token:    pauseToken,
      _skill_title:    skillTitle || '',
      _context:        contextText,
      _collect_fields: resolvedFields?.length ? JSON.stringify(resolvedFields) : '[]',
    });
  }

  /** WorkflowCanvas 审批操作回调 */
  function _onCanvasApprovalAction(nodeId, approved, userData) {
    const node = _wfCanvas?._nodes?.find(n => n.id === nodeId);
    const pauseToken = node?.params?._pause_token;
    if (!pauseToken) return;
    _resumeSkillCanvas(pauseToken, approved, userData);
  }

  /** WorkflowCanvas 审批表单选项加载回调 */
  async function _fetchApprovalOptions(toolName, params) {
    try {
      return await window._cloudFetch?.('/api/skills/canvas-options', {
        method: 'POST',
        body: JSON.stringify({
          tool_name:  toolName,
          params:     params || {},
          auth_token: _getAuthToken?.() || '',
        }),
      }) ?? { options: [] };
    } catch (_) {
      return { options: [] };
    }
  }

  async function _resumeSkillCanvas(pauseToken, approved, userData = {}) {
    try {
      const res = await window._cloudFetch?.('/api/skills/resume-canvas', {
        method: 'POST',
        body: JSON.stringify({
          pause_token: pauseToken,
          approved:    approved,
          owner_gid:   _getUserGid(),
          user_data:   approved ? userData : {},
        }),
      });

      if (res?.error) {
        _showToast(`❌ ${res.error}`);
        return;
      }

      // 更新左侧边栏步骤状态
      const nodeResults = res?.node_results || {};
      _updateSidebarStatus(nodeResults);
      // 注入结果节点到交互画布（n2 vpps核对 / n6 预览关联）
      for (const [nid, nr] of Object.entries(nodeResults)) {
        if (!_injectedResultNodes.has(nid)) {
          _injectResultNode(nid, nr);
          _injectedResultNodes.add(nid);
        }
      }

      // 如果还有下一个 human 节点需要确认
      if (res?.status === 'paused' && res.pause_token) {
        _appendHumanApprovalCard(res.halted_label || '人工步骤', res.pause_token, res.skill_title, nodeResults, res.context_summary, res.collect_fields || null, res.canvas_layout || null);
        return;
      }

      // 流程结束（completed / halted / error）
      const isOk     = res.status === 'completed';
      const isHalted = res.status === 'halted';
      const statusText = isOk ? '✅ 执行完成'
                       : isHalted ? '⛔ 流程已中止'
                       : `⚠️ 执行异常（${res.status}）`;
      const summary = res.summary || res.halt_reason || '';

      // halted 时在沙盘加状态卡片
      if (isHalted && _skillSandbox) {
        _skillSandbox.addNode('agent', '⛔ ' + statusText, 0, _approvalStep++, { note: summary });
        _showResetBtn(summary);
      }

      _appendAiMsg('assistant', `**${statusText}**\n\n${summary}`);
      _showToast(isOk ? '✅ Skill 执行完成' : isHalted ? '⛔ 流程已中止' : `⚠️ Skill 执行${res.status}`);
      if (res.log_path) _appendLogLink(res.log_path);

    } catch (e) {
      _showToast(`❌ 请求失败: ${e.message || e}`);
    }
  }

  /** 在聊天框追加"查看日志"链接行 */
  function _appendLogLink(logPath) {
    if (!logPath) return;
    const $msgs = document.getElementById('wfcwAiMsgs');
    if (!$msgs) return;
    const $link = document.createElement('div');
    $link.className = 'wfc-log-link';
    $link.innerHTML = `<span class="wfc-log-link-icon">📄</span>
      <a href="#" class="wfc-log-link-text">查看执行日志</a>
      <span class="wfc-log-link-path">${_esc(logPath)}</span>`;
    $link.querySelector('a').addEventListener('click', e => {
      e.preventDefault();
      const api = window.electronAPI || window.parent?.electronAPI || window.top?.electronAPI;
      api?.openPath?.(logPath);
    });
    $msgs.appendChild($link);
    $msgs.scrollTop = $msgs.scrollHeight;
  }

  /** 客户端降级：从 nodeResults 提取最近 ok 节点的文本摘要 */
  function _buildLocalContextSummary(nodeResults) {
    if (!nodeResults || typeof nodeResults !== 'object') return [];
    const items = [];
    for (const [, res] of Object.entries(nodeResults)) {
      if (res?._status === 'ok' && res._summary) {
        items.push({ text: res._summary });
      }
    }
    return items.slice(-6);
  }

  /** 获取指定版本的所有 BOP 条目（去重：因 LEFT JOIN 可能产生重复行） */
  async function _fetchBopEntries(versionGid) {
    try {
      const res = await window._cloudFetch(`/api/bop/versions/${versionGid}/entries`);
      const raw = Array.isArray(res) ? res : (res?.data || res?.items || []);
      // 按 gid 去重，保留 primary_link_count 最高的行
      const byGid = {};
      for (const e of raw) {
        if (!byGid[e.gid] || (e.primary_link_count || 0) > (byGid[e.gid].primary_link_count || 0)) {
          byGid[e.gid] = e;
        }
      }
      const entries = Object.values(byGid);
      console.debug('[_fetchBopEntries]', versionGid, 'raw:', raw.length, 'deduped:', entries.length);
      return entries;
    } catch (e) {
      console.error('[_fetchBopEntries]', e);
      return [];
    }
  }

  /** 从条目列表构建 线体→工位→工序 树（用于 BOP Canvas 渲染） */
  function _buildBopTree(entries, filterLineGids) {
    // 兼容新旧两种节点类型命名（asm_* 前缀 vs 无前缀）
    const isLine    = t => t === 'asm_line_process'     || t === 'line_process';
    const isStation = t => t === 'asm_station_process'  || t === 'station_process';
    const isOp      = t => t === 'asm_operation'        || t === 'operation';
    const isOper    = t => t === 'asm_operator_process' || t === 'operator_process';

    const childrenOf = {};
    for (const e of entries) childrenOf[e.gid] = [];
    for (const e of entries) {
      if (e.parent_gid && childrenOf[e.parent_gid]) childrenOf[e.parent_gid].push(e);
    }
    function collectOps(parentGid) {
      const ops = [];
      for (const ch of (childrenOf[parentGid] || [])) {
        if (isOp(ch.node_type)) ops.push(ch);
        else if (isOper(ch.node_type))
          for (const sub of (childrenOf[ch.gid] || []))
            if (isOp(sub.node_type)) ops.push(sub);
      }
      return ops.sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
    }
    const lines = entries
      .filter(e => isLine(e.node_type))
      .filter(e => !filterLineGids.length || filterLineGids.includes(e.gid))
      .sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
    console.debug('[_buildBopTree] total entries:', entries.length,
      'lines found:', lines.length, 'filterLineGids:', filterLineGids);
    let linked = 0, total = 0;
    const result = lines.map(line => ({
      gid: line.gid, title: line.title,
      stations: (childrenOf[line.gid] || [])
        .filter(e => isStation(e.node_type))
        .sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0))
        .map(st => ({
          gid: st.gid, title: st.title,
          operations: collectOps(st.gid).map(op => {
            total++;
            // link_gid 是 LEFT JOIN 返回的主关联 gid；primary_link_count 是子查询计数
            const ls = (op.primary_link_count > 0 || op.link_gid) ? 'linked' : 'none';
            if (ls === 'linked') linked++;
            return { gid: op.gid, title: op.title, vpps: op.vpps, link_status: ls };
          }),
        })),
    }));
    return { lines: result, linked_count: linked, total_ops: total };
  }

  /** 异步渲染 BOP Canvas 卡片（n9 执行完成后调用） */
  async function _renderBopCanvasAsync(nodeId, _result) {
    console.debug('[BopCanvas] _lastNodeResults:', JSON.stringify(_lastNodeResults));
    const versionGid = _lastNodeResults?.n5?.gid || _lastNodeResults?.u0?.version_gid;
    if (!versionGid) { console.warn('[BopCanvas] no version_gid in _lastNodeResults'); return; }
    const scope    = _lastNodeResults?.u8?.line_scope;
    const lineGids = scope === 'selected'
      ? [].concat(_lastNodeResults?.u8?.line_gids || []).filter(Boolean)
      : [];
    console.debug('[BopCanvas] version:', versionGid, 'scope:', scope, 'lineGids:', lineGids);
    const entries  = await _fetchBopEntries(versionGid);
    if (!entries.length) { console.warn('[BopCanvas] empty entries for version', versionGid); return; }
    const treeData = _buildBopTree(entries, lineGids);
    const label    = nodeId === 'n6' ? '预览关联结构' : 'Auto-Link 关联结果';
    _skillSandbox.addBopCanvas(label, treeData);
    _approvalStep++;
  }

  /** 将节点结果注入沙盘，同时存入当前步骤缓冲 */
  function _injectResultNode(nodeId, result) {
    if (!_skillSandbox) return;
    console.debug('[_injectResultNode]', nodeId, result);

    let label = null;
    let params = null;

    if (nodeId === 'n2') {
      const nok      = (result.nok_items || []).slice(0, 30);
      const items    = nok.map(i => ({ level: i.level === 'error' ? 'error' : 'warn', label: i.label || '', desc: i.desc || '' }));
      const critical = result.critical_errors ?? 0;
      const r4       = result.rule4_flag ? '，规则4需让步' : '';
      const status   = critical > 0 ? `严重错误 ${critical} 项${r4}` : items.length ? `警告 ${items.length} 项，可继续` : '全部通过';
      label  = `PBOM核对：${status}`;
      params = { _items: items, _text: result.text || '' };
    }
    if (nodeId === 'n_r4') {
      label  = '规则4让步完成';
      params = { _items: [], _text: result.text || result.summary || '' };
    }
    if (nodeId === 'n6') {
      const items = _buildPreviewSummary(result);
      label  = '预览关联摘要';
      params = { _items: items, _text: '' };
    }
    if (nodeId === 'n9') {
      label  = 'Auto-Link 执行完成';
      params = { _items: [], _text: result.text || result.summary || '' };
      // 异步渲染 BOP 结构可视化画布
      _renderBopCanvasAsync('n9', result).catch(e => console.error('[BopCanvas n9]', e));
    }
    if (nodeId === 'n10') {
      const items = _buildPreviewSummary(result);
      label  = '执行结果';
      params = { _items: items, _text: result.text || result.summary || '' };
    }

    if (label && params) {
      _skillSandbox.addNode('result_list', label, 0, _approvalStep++, params);
      _pendingResultNodes.push({ label, params });
    }
  }

  function _buildPreviewSummary(result) {
    const lines = (result.text || '').split('\n').filter(l => l.trim()).slice(0, 10);
    return lines.map(l => ({ level: 'info', label: l, desc: '' }));
  }

  function _addTopicNote() {
    const $inp = document.getElementById('wfcwTopicNote');
    const text = ($inp?.value || '').trim();
    if (!text) return;
    $inp.value = '';

    const $body = document.getElementById('wfcwTopicBody');
    if (!$body) return;

    const $empty = document.getElementById('wfcwTopicEmpty');
    if ($empty) $empty.style.display = 'none';

    const now = new Date();
    const timeStr = now.getHours().toString().padStart(2, '0') + ':'
                  + now.getMinutes().toString().padStart(2, '0');

    const $entry = document.createElement('div');
    $entry.className = 'wfc-tpm';

    const $time = document.createElement('div');
    $time.className = 'wfc-tpm-time';
    $time.textContent = timeStr;

    const $text = document.createElement('div');
    $text.className = 'wfc-tpm-text';
    $text.textContent = text;

    $entry.appendChild($time);
    $entry.appendChild($text);
    $body.appendChild($entry);
    $body.scrollTop = $body.scrollHeight;
  }

  function _initAiPanel() {
    const panel  = document.getElementById('wfcwAiPanel');
    const hdr    = document.getElementById('wfcwApHdr');
    const toggle = document.getElementById('wfcwApToggle');
    if (!panel) return;

    function _toggle() {
      const willCollapse = !panel.classList.contains('collapsed');
      if (willCollapse) {
        // 折叠前保存当前宽度，清除内联宽度让 CSS .collapsed { width:28px } 生效
        const curW = panel.style.width;
        if (curW) localStorage.setItem(_lsk('wfcw.apWidth'), curW);
        panel.style.width = '';
        panel.classList.add('collapsed');
      } else {
        panel.classList.remove('collapsed');
        // 展开后恢复保存的宽度
        const saved = localStorage.getItem(_lsk('wfcw.apWidth'));
        if (saved) panel.style.width = saved;
      }
    }

    // 点击 header 区域（避开内部按钮）切换折叠
    hdr.addEventListener('click', e => {
      if (e.target.closest('button')) return;
      _toggle();
    });
    toggle.addEventListener('click', _toggle);

    // 话题讨论区折叠切换
    document.getElementById('wfcwTopicToggle')?.addEventListener('click', () => {
      document.getElementById('wfcwTopicSection')?.classList.toggle('collapsed');
    });

    // AI 发送
    document.getElementById('wfcwAiSend')?.addEventListener('click', _sendAiMsg);
    document.getElementById('wfcwAiInp')?.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) {
        if (document.querySelector('.wfcw-at-drop')) return; // @mention 下拉优先处理
        e.preventDefault(); _sendAiMsg();
      }
    });

    // 停止生成
    document.getElementById('wfcwAiStop')?.addEventListener('click', () => {
      // 立即中断 SSE fetch 连接
      _streamAbortCtrl?.abort();
      _streamAbortCtrl = null;
      // 渲染已收到的部分文本
      _streamAbortFinalize?.();
      _streamAbortFinalize = null;
      // 恢复发送状态
      _apSending = false;
      const $sb = document.getElementById('wfcwAiStop');
      if ($sb) $sb.style.display = 'none';
      // 同步通知服务端（工具调用轮次间的兜底）
      if (_apSessionGid) {
        window._cloudFetch?.('/api/ai/abort', {
          method: 'POST',
          body: JSON.stringify({ session_gid: _apSessionGid }),
        }).catch(() => {});
      }
    });

    // 欢迎消息
    _appendAiMsg('assistant', '你好！我是小柔，你的 AI 工作流助手。有什么关于这个画布或工作流的问题，随时告诉我 ✦');
  }

  /* ── 工具库面板 ───────────────────────────────────────────────────────── */
  function _initToolsPanel() {
    const $sec  = document.getElementById('wfcwToolsSection');
    const $hdr  = document.getElementById('wfcwToolsHdr');
    const $body = document.getElementById('wfcwToolsBody');
    if (!$sec) return;

    $hdr.addEventListener('click', () => $sec.classList.toggle('collapsed'));

    window._cloudFetch?.('/api/ai/tools').then(data => {
      if (!data || !$body) return;
      const all = [
        ...(data.read || []),
        ...(data.write_confirm || []),
        ...(data.write_no_confirm || []),
        ...(data.system || []),
      ];
      if (!all.length) {
        $body.innerHTML = '<div class="wfcw-ns-empty">暂无工具</div>';
        return;
      }
      $body.innerHTML = '';
      all.forEach(t => {
        const el = document.createElement('div');
        el.className = 'wfcw-ns-tool-item';
        el.title = t.description || t.name;
        el.draggable = true;
        el.innerHTML = `<span class="wfcw-ns-tool-name">${_esc(t.name)}</span>`;
        el.addEventListener('dragstart', e => {
          const nodeType = t.need_confirm ? 'tool_write' : 'tool_read';
          e.dataTransfer.setData('wfc-node-type', nodeType);
          e.dataTransfer.setData('wfc-node-params', JSON.stringify({
            name:        t.name,
            description: t.description || '',
          }));
          e.dataTransfer.effectAllowed = 'copy';
        });
        $body.appendChild(el);
      });
    }).catch(() => {
      if ($body) $body.innerHTML = '<div class="wfcw-ns-empty">加载失败</div>';
    });
  }

  /* ── Skill 库面板（悬浮聊天窗内） ───────────────────────────────────── */
  function _initSkillsPanel() {
    const $body = document.getElementById('wfcwSkillsBody');
    if (!$body) return;

    window._cloudFetch?.('/api/skills?scope_filter=all').then(list => {
      if (!$body) return;
      const skills = Array.isArray(list) ? list.filter(s => s.status === 'active') : [];
      _skillsList = skills;   // 缓存供 @ mention 使用
      if (!skills.length) {
        $body.innerHTML = '<div class="wfcw-ns-empty">暂无 Skill</div>';
        return;
      }
      $body.innerHTML = '';
      skills.forEach(s => {
        const card = document.createElement('div');
        card.className = 'wfcw-ns-skill-card';
        card.dataset.gid = s.gid;
        card.title = s.description || s.title;
        card.draggable = true;
        card.innerHTML = `<span class="wfcw-ns-skill-name">${_esc(s.title)}</span>`;
        card.addEventListener('dragstart', e => {
          e.dataTransfer.setData('wfc-node-type', 'skill_call');
          e.dataTransfer.setData('wfc-node-params', JSON.stringify({
            skill_gid:   s.gid,
            skill_name:  s.name,
            skill_title: s.title,
            name:        s.title,
          }));
          e.dataTransfer.effectAllowed = 'copy';
        });
        card.addEventListener('click', () => {
          // 高亮选中
          $body.querySelectorAll('.wfcw-ns-skill-card').forEach(c => c.classList.remove('selected'));
          card.classList.add('selected');
          // 加载 Skill 预定义流程画布
          _loadSkillCanvas(s);
          // 关闭浮球聊天窗，让画布可见
          const $chat = document.getElementById('wfcwFloatChat');
          if ($chat && $chat.style.display !== 'none') $chat.style.display = 'none';
          // 在输入框预填 @skill，下次打开聊天时可见
          const $inp = document.getElementById('wfcwAiInp');
          if ($inp) { $inp.value = `@${s.title} `; }
        });
        $body.appendChild(card);
      });
    }).catch(() => {
      if ($body) $body.innerHTML = '<div class="wfcw-ns-empty">加载失败</div>';
    });
  }

  /* ── AI 输入框 @ mention Skill 搜索 ──────────────────────────────────── */
  function _initAtMention() {
    const $inp = document.getElementById('wfcwAiInp');
    if (!$inp) return;

    let $drop = null;

    function _closeDrop() {
      if ($drop) { $drop.remove(); $drop = null; }
    }

    function _getAtQuery() {
      const val = $inp.value;
      const pos = $inp.selectionStart;
      const before = val.slice(0, pos);
      const m = before.match(/@([^@\s]*)$/);
      return m ? { query: m[1], atPos: pos - m[0].length } : null;
    }

    function _showDrop(query, atPos) {
      _closeDrop();
      const q = query.toLowerCase();
      const matched = _skillsList.filter(s =>
        !q || s.title.toLowerCase().includes(q) || (s.name || '').toLowerCase().includes(q)
      ).slice(0, 8);
      if (!matched.length) return;

      $drop = document.createElement('div');
      $drop.className = 'wfcw-at-drop';
      matched.forEach(s => {
        const item = document.createElement('div');
        item.className = 'wfcw-at-item';
        const hi = s.title.replace(new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi'),
          '<mark>$1</mark>');
        item.innerHTML = `<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="flex-shrink:0;opacity:.6"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg><span>${hi}</span>`;
        item.addEventListener('mousedown', e => {
          e.preventDefault();
          const before = $inp.value.slice(0, atPos);
          const after  = $inp.value.slice($inp.selectionStart);
          $inp.value = before + '@' + s.title + ' ' + after;
          const newPos = atPos + s.title.length + 2;
          $inp.setSelectionRange(newPos, newPos);
          $inp.focus();
          _closeDrop();
          // 选中 @skill 立即加载流程画布（与点击 Skill 卡片效果一致）
          _loadSkillCanvas(s);
        });
        $drop.appendChild(item);
      });

      // 定位到输入框上方
      const rect = $inp.getBoundingClientRect();
      $drop.style.left   = rect.left + 'px';
      $drop.style.bottom = (window.innerHeight - rect.top + 4) + 'px';
      $drop.style.width  = rect.width + 'px';
      document.body.appendChild($drop);
    }

    $inp.addEventListener('input', () => {
      const hit = _getAtQuery();
      if (hit) _showDrop(hit.query, hit.atPos);
      else _closeDrop();
    });

    $inp.addEventListener('keydown', e => {
      if (!$drop) return;
      if (e.key === 'Escape') { _closeDrop(); e.stopPropagation(); }
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        const items = $drop.querySelectorAll('.wfcw-at-item');
        const cur = $drop.querySelector('.wfcw-at-item.active');
        const idx = cur ? [...items].indexOf(cur) : -1;
        cur?.classList.remove('active');
        items[Math.min(idx + 1, items.length - 1)]?.classList.add('active');
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        const items = $drop.querySelectorAll('.wfcw-at-item');
        const cur = $drop.querySelector('.wfcw-at-item.active');
        const idx = cur ? [...items].indexOf(cur) : items.length;
        cur?.classList.remove('active');
        items[Math.max(idx - 1, 0)]?.classList.add('active');
      }
      if (e.key === 'Enter' || e.key === 'Tab') {
        const active = $drop?.querySelector('.wfcw-at-item.active');
        if (active) {
          e.preventDefault();
          e.stopImmediatePropagation(); // 阻止同一元素上后续注册的 keydown（_initFloatChat 的 _sendAiMsg）
          active.dispatchEvent(new MouseEvent('mousedown'));
        }
      }
    });

    $inp.addEventListener('blur', () => setTimeout(_closeDrop, 150));
  }

  /* ── 流程总览 sidebar ─────────────────────────────────────────────────── */
  let _canvasSnapshot = null;   // 临时保存原有画布内容（放入画布预览时）

  function _initFlowSidebar() {
    const $sb  = document.getElementById('wfcwFlowSidebar');
    const $btn = document.getElementById('wfcwFsCollapseBtn');
    const $hdr = document.getElementById('wfcwFsHdr');
    if (!$sb) return;

    // 默认收起（除非用户明确展开）
    if (localStorage.getItem(_lsk('wfcw.flowSidebarCollapsed')) !== 'false') {
      $sb.classList.add('ns-collapsed');
    }

    $btn?.addEventListener('click', () => {
      const c = $sb.classList.toggle('ns-collapsed');
      localStorage.setItem(_lsk('wfcw.flowSidebarCollapsed'), c);
    });
    $hdr?.addEventListener('click', e => {
      if (!$sb.classList.contains('ns-collapsed')) return;
      if (e.target.closest('.wfcw-fs-collapse-btn')) return;
      if (e.target.closest('.wfcw-fs-edit-btn')) return;
      $sb.classList.remove('ns-collapsed');
      localStorage.setItem(_lsk('wfcw.flowSidebarCollapsed'), 'false');
    });

    // 放入画布（临时预览）
    document.getElementById('wfcwFsEditBtn')?.addEventListener('click', () => {
      if (!_topCanvas || !_wfCanvas) return;
      if (_canvasSnapshot !== null) {
        // 已在预览中 → 还原
        _exitCanvasPreview();
      } else {
        // 进入预览
        _canvasSnapshot = _wfCanvas.toJSON();
        _wfCanvas.fromJSON(_topCanvas.toJSON());
        _showCanvasPreviewBar();
      }
    });

    // 流程 sidebar：转 Skill
    document.getElementById('wfcwFsToSkill')?.addEventListener('click', async () => {
      const canvasData = _getFlowCanvasJSON();
      if (!canvasData || (canvasData.nodes || []).length === 0) {
        _showToast('执行流程为空，无法转 Skill'); return;
      }
      const title = prompt('请输入新 Skill 名称：',
        _fixedSkill ? `${_fixedSkill.title} (副本)` : '新 Skill');
      if (!title?.trim()) return;
      const name = title.trim().toLowerCase().replace(/\s+/g, '_').replace(/[^\w\u4e00-\u9fa5]/g, '');
      const res = await window.call_bridge?.('skill', 'create_skill', {
        name, title: title.trim(), skill_type: 'prompt', scope: 'private',
        content: JSON.stringify({ canvas: canvasData }), owner_gid: _getUserGid(),
      });
      if (res?.error) { _showToast(`保存失败：${res.error}`); return; }
      _showToast(`已创建 Skill「${title.trim()}」`);
      _initSkillsPanel();
    });

    // 流程 sidebar：更新 Skill
    document.getElementById('wfcwFsUpdateSkill')?.addEventListener('click', async () => {
      if (!_fixedSkill) { _showToast('未加载任何 Skill'); return; }
      const canvasData = _getFlowCanvasJSON();
      if (!canvasData) { _showToast('执行流程为空'); return; }
      if (!confirm(`将当前执行流程更新到 Skill「${_fixedSkill.title}」？`)) return;
      let contentObj = {};
      try { contentObj = JSON.parse(_fixedSkill.content || '{}'); } catch (_) {}
      contentObj.canvas = canvasData;
      const res = await window._cloudFetch?.(`/api/skills/${_fixedSkill.gid}`, {
        method: 'PUT', body: JSON.stringify({ gid: _fixedSkill.gid, content: JSON.stringify(contentObj) }),
      });
      if (res?.error) { _showToast(`更新失败：${res.error}`); return; }
      _fixedSkill = { ..._fixedSkill, content: JSON.stringify(contentObj) };
      _showToast(`Skill「${_fixedSkill.title}」已更新`);
      _initSkillsPanel();
    });

    // 流程 sidebar：▶ 执行
    document.getElementById('wfcwFsRunBtn')?.addEventListener('click', () => {
      _runSkillCanvas();
    });
  }

  /* ── 自主执行 Skill Canvas ─────────────────────────────────────────────── */

  async function _runSkillCanvas() {
    if (!_fixedSkill?.gid) {
      _showToast('请先选中一个 Skill'); return;
    }
    const $btn = document.getElementById('wfcwFsRunBtn');
    if ($btn?.classList.contains('running')) return;
    $btn?.classList.add('running');

    _showToast(`▶ 开始执行「${_fixedSkill.title}」…`);

    // 清空上一次的执行状态
    _skillSandbox?.clearForInteraction({});
    document.getElementById('wfcwHaltedBar')?.classList.add('hidden');
    _clearSidebarStatus();
    _approvalStep = 1;
    _injectedResultNodes  = new Set();
    _pendingResultNodes   = [];
    _lastNodeResults      = {};

    try {
      const res = await window._cloudFetch?.('/api/skills/execute-canvas', {
        method: 'POST',
        body: JSON.stringify({
          gid:        _fixedSkill.gid,
          auth_token: _getAuthToken(),
          owner_gid:  _getUserGid(),
        }),
      });

      if (res?.error) {
        _showToast(`执行失败：${res.error}`); return;
      }

      // 根据返回的 node_results 更新左侧边栏步骤状态
      const nodeResults = res?.node_results || {};
      _updateSidebarStatus(nodeResults);
      // 注入结果节点到交互画布（n2 vpps核对 / n6 预览关联）
      for (const [nid, nr] of Object.entries(nodeResults)) {
        if (!_injectedResultNodes.has(nid)) {
          _injectResultNode(nid, nr);
          _injectedResultNodes.add(nid);
        }
      }

      // 流程暂停等待人工确认
      if (res?.status === 'paused' && res.pause_token) {
        _appendHumanApprovalCard(
          res.halted_label || '人工步骤',
          res.pause_token,
          _fixedSkill?.title,
          nodeResults,
          res.context_summary,
          res.collect_fields || null,
          res.canvas_layout  || null,
        );
        if (res.log_path) _appendLogLink(res.log_path);
        return;
      }

      // 在聊天框追加执行结果摘要
      const isRunHalted = res?.status === 'halted';
      const summary = res?.summary || res?.halt_reason || '执行完成';
      if (isRunHalted) {
        // halted 时在沙盘加状态卡片
        if (_skillSandbox) {
          _skillSandbox.addNode('agent', '⛔ 流程已中止', 0, _approvalStep++, { note: summary });
          _showResetBtn(summary);
        }
        _showToast('⛔ 流程已中止');
        _appendAiMsg('assistant', `**⛔ 流程已中止**\n\n${summary}`);
      } else {
        _appendAiMsg('assistant', `**✅ Skill「${_fixedSkill.title}」自主执行完成**\n\n${summary}`);
        if (_skillSandbox) {
          _skillSandbox.addNode('agent', `✅ ${_fixedSkill.title} 执行完成`, 0, _approvalStep++, { note: summary });
        }
      }
      if (res?.log_path) _appendLogLink(res.log_path);

      // 如果聊天窗是开着的，切到 AI 对话 tab
      const $chat = document.getElementById('wfcwFloatChat');
      if ($chat && $chat.style.display !== 'none') {
        const chatTab = $chat.querySelector('.wfcw-fc-tab[data-tab="chat"]');
        chatTab?.click();
      }
    } catch (e) {
      _showToast(`执行出错：${e.message || e}`);
    } finally {
      $btn?.classList.remove('running');
    }
  }

  function _showCanvasPreviewBar() {
    let $bar = document.getElementById('wfcwPreviewBar');
    if ($bar) { $bar.style.display = ''; return; }
    $bar = document.createElement('div');
    $bar.id = 'wfcwPreviewBar';
    $bar.className = 'wfcw-preview-bar';
    $bar.innerHTML = `<span>预览：${_esc(_fixedSkill?.title || 'Skill 流程')}</span>
      <button id="wfcwPreviewBarExit">退出预览</button>`;
    const $wrap = document.querySelector('.wfcw-canvas-main');
    if ($wrap) $wrap.insertBefore($bar, $wrap.querySelector('.wfc-header').nextSibling);
    document.getElementById('wfcwPreviewBarExit')?.addEventListener('click', _exitCanvasPreview);
  }

  function _exitCanvasPreview() {
    if (_canvasSnapshot !== null) {
      _wfCanvas.fromJSON(_canvasSnapshot);
      _canvasSnapshot = null;
    }
    const $bar = document.getElementById('wfcwPreviewBar');
    if ($bar) $bar.style.display = 'none';
    // 更新编辑按钮提示
    const $editBtn = document.getElementById('wfcwFsEditBtn');
    if ($editBtn) $editBtn.title = '放入画布编辑';
  }

  /** 清除侧边栏执行状态（新一轮执行前调用） */
  function _clearSidebarStatus() {
    const $body = document.getElementById('wfcwFsSidebarBody');
    if (!$body) return;
    $body.querySelectorAll('.wfcw-fs-step-num').forEach($n => { $n.className = 'wfcw-fs-step-num'; });
    $body.querySelectorAll('.wfcw-fs-node[data-status]').forEach($n => { delete $n.dataset.status; });
  }

  /** 根据 node_results 更新左侧执行流程面板中各步骤的颜色状态 */
  function _updateSidebarStatus(nodeResults) {
    if (nodeResults) _lastNodeResults = { ..._lastNodeResults, ...nodeResults };
    const $body = document.getElementById('wfcwFsSidebarBody');
    if (!$body || !nodeResults) return;
    const priorityOf = { error: 4, warning: 3, running: 2, success: 1, skipped: 0 };
    const stepStatus = {};   // step# → highest-priority status string

    for (const [nodeId, nr] of Object.entries(nodeResults)) {
      if (!nr?._status) continue;
      const status = nr._status === 'ok'              ? 'success'
                   : nr._status === 'warning'          ? 'warning'
                   : nr._status === 'pending_approval' ? 'running'
                   : nr._status === 'skipped'          ? 'skipped'
                   : nr._status === 'error'            ? 'error'
                   : null;
      if (!status) continue;
      const $chip = $body.querySelector(`.wfcw-fs-node[data-nodeid="${nodeId}"]`);
      if (!$chip) continue;
      $chip.dataset.status = status;
      const $step = $chip.closest('.wfcw-fs-step');
      const $num  = $step?.querySelector('.wfcw-fs-step-num');
      if (!$num) continue;
      const stepN = parseInt($num.textContent) || 0;
      if ((priorityOf[status] ?? -1) > (priorityOf[stepStatus[stepN]] ?? -1)) {
        stepStatus[stepN] = status;
      }
    }
    $body.querySelectorAll('.wfcw-fs-step-num').forEach($num => {
      const stepN = parseInt($num.textContent) || 0;
      const st = stepStatus[stepN];
      $num.className = 'wfcw-fs-step-num' + (st ? ` status-${st}` : '');
    });
  }

  function _renderFlowSidebar(canvas) {
    const $body = document.getElementById('wfcwFsSidebarBody');
    if (!$body || !canvas) return;
    const nodes = canvas._nodes || [];
    if (!nodes.length) {
      $body.innerHTML = '<div class="wfcw-fs-empty">暂无步骤</div>';
      return;
    }
    const stepMap = {};
    nodes.forEach(n => {
      const s = n.step || 1;
      (stepMap[s] = stepMap[s] || []).push(n);
    });
    const steps = Object.keys(stepMap).map(Number).sort((a, b) => a - b);
    $body.innerHTML = steps.map((s, idx) => {
      const nodesHtml = stepMap[s].map(n => {
        const def = WFC_NODE_TYPES[n.type] || {};
        const badge = def.badgeText || n.type.slice(0, 2).toUpperCase();
        const label = n.label || def.label || n.type;
        return `<div class="wfcw-fs-node" data-nodeid="${n.id}" title="${_esc(label)}">
          <span class="wfc-badge wfc-badge-${n.type}"
                style="font-size:9px;padding:1px 3px;line-height:1">${_esc(badge)}</span>
          <span class="wfcw-fs-node-label">${_esc(label)}</span>
        </div>`;
      }).join('');
      const conn = idx < steps.length - 1
        ? '<div class="wfcw-fs-connector"></div>' : '';
      return `<div class="wfcw-fs-step">
        <div class="wfcw-fs-step-row">
          <div class="wfcw-fs-step-num">${s}</div>
          <div class="wfcw-fs-nodes">${nodesHtml}</div>
        </div>${conn}
      </div>`;
    }).join('');

    $body.querySelectorAll('.wfcw-fs-node').forEach(chipEl => {
      chipEl.addEventListener('click', () => {
        const nodeId = chipEl.dataset.nodeid;
        const node = canvas._nodes.find(n => n.id === nodeId);
        if (node) canvas._openNodePopover(node, chipEl);
      });
    });
  }

  /* ── 悬浮球 ───────────────────────────────────────────────────────────── */
  function _initFloatBall() {
    const $ball = document.getElementById('wfcwFloatBall');
    if (!$ball) return;
    const saved = JSON.parse(localStorage.getItem(_lsk('wfcw.ballPos')) || 'null');
    if (saved) {
      const BALL = 48;
      const maxR = Math.max(8, window.innerWidth  - BALL - 8);
      const maxB = Math.max(8, window.innerHeight - BALL - 8);
      $ball.style.right  = Math.min(Math.max(8, saved.right),  maxR) + 'px';
      $ball.style.bottom = Math.min(Math.max(8, saved.bottom), maxB) + 'px';
    }

    let _dragged = false, _sx = 0, _sy = 0, _or = 0, _ob = 0;
    $ball.addEventListener('mousedown', e => {
      if (e.button !== 0) return;
      _dragged = false; _sx = e.clientX; _sy = e.clientY;
      const r = $ball.getBoundingClientRect();
      _or = window.innerWidth  - r.right;
      _ob = window.innerHeight - r.bottom;
      const onMove = ev => {
        if (Math.abs(ev.clientX - _sx) > 3 || Math.abs(ev.clientY - _sy) > 3) _dragged = true;
        if (!_dragged) return;
        $ball.style.right  = Math.max(8, _or + (_sx - ev.clientX)) + 'px';
        $ball.style.bottom = Math.max(8, _ob + (_sy - ev.clientY)) + 'px';
      };
      const onUp = () => {
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
        if (!_dragged) { _toggleFloatChat(); return; }
        localStorage.setItem(_lsk('wfcw.ballPos'), JSON.stringify({
          right: parseInt($ball.style.right), bottom: parseInt($ball.style.bottom),
        }));
      };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    });
  }

  /* ── 悬浮聊天窗 ───────────────────────────────────────────────────────── */
  function _initFloatChat() {
    const $chat = document.getElementById('wfcwFloatChat');
    if (!$chat) return;

    // 恢复位置，并将坐标限制在当前视口内
    const savedPos = JSON.parse(localStorage.getItem(_lsk('wfcw.chatPos')) || 'null');
    if (savedPos) {
      const W = 360, H = 500;   // 聊天窗固定尺寸
      const left = Math.min(Math.max(0, savedPos.left), window.innerWidth  - W);
      const top  = Math.min(Math.max(0, savedPos.top),  window.innerHeight - H);
      $chat.style.left = left + 'px';
      $chat.style.top  = top  + 'px';
    }

    // Tab 切换
    $chat.querySelectorAll('.wfcw-fc-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        const p = tab.dataset.tab;
        $chat.querySelectorAll('.wfcw-fc-tab').forEach(t => t.classList.remove('active'));
        $chat.querySelectorAll('.wfcw-fc-pane').forEach(pane => {
          pane.style.display = pane.dataset.pane === p ? '' : 'none';
        });
        tab.classList.add('active');
        // 切回 AI 对话 tab 时自动聚焦输入框
        if (p === 'chat') {
          document.getElementById('wfcwAiInp')?.focus();
        }
      });
    });

    // 关闭
    document.getElementById('wfcwFcClose')?.addEventListener('click', () => {
      $chat.style.display = 'none';
    });

    // 拖拽标题栏
    const $hdr = document.getElementById('wfcwFcHdr');
    let _ox = 0, _oy = 0, _dragging = false;
    $hdr.addEventListener('mousedown', e => {
      if (e.target.closest('button')) return;
      const r = $chat.getBoundingClientRect();
      _ox = e.clientX - r.left; _oy = e.clientY - r.top; _dragging = true;
      const onMove = ev => {
        if (!_dragging) return;
        $chat.style.left   = Math.max(0, ev.clientX - _ox) + 'px';
        $chat.style.top    = Math.max(0, ev.clientY - _oy) + 'px';
        $chat.style.right  = ''; $chat.style.bottom = '';
      };
      const onUp = () => {
        _dragging = false;
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
        localStorage.setItem(_lsk('wfcw.chatPos'),
          JSON.stringify({ left: parseInt($chat.style.left), top: parseInt($chat.style.top) }));
      };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    });

    // AI 对话绑定
    document.getElementById('wfcwAiSend')?.addEventListener('click', _sendAiMsg);
    document.getElementById('wfcwAiInp')?.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) {
        if (document.querySelector('.wfcw-at-drop')) return; // @mention 下拉优先处理
        e.preventDefault(); _sendAiMsg();
      }
    });

    // 停止生成
    document.getElementById('wfcwAiStop')?.addEventListener('click', () => {
      // 立即中断 SSE fetch 连接
      _streamAbortCtrl?.abort();
      _streamAbortCtrl = null;
      // 渲染已收到的部分文本
      _streamAbortFinalize?.();
      _streamAbortFinalize = null;
      // 恢复发送状态
      _apSending = false;
      const $sb = document.getElementById('wfcwAiStop');
      if ($sb) $sb.style.display = 'none';
      // 同步通知服务端（工具调用轮次间的兜底）
      if (_apSessionGid) {
        window._cloudFetch?.('/api/ai/abort', {
          method: 'POST',
          body: JSON.stringify({ session_gid: _apSessionGid }),
        }).catch(() => {});
      }
    });

    // 欢迎消息
    _appendAiMsg('assistant', '你好！我是小柔，你的 AI 工作流助手。有什么关于这个画布或工作流的问题，随时告诉我 ✦');
  }

  function _toggleFloatChat() {
    const $chat = document.getElementById('wfcwFloatChat');
    const $ball = document.getElementById('wfcwFloatBall');
    if (!$chat) return;
    const show = $chat.style.display === 'none';
    $chat.style.display = show ? '' : 'none';
    if (show) {
      if (!$chat.style.left) {
        _positionChatNearBall();
      } else {
        // 每次打开时检查坐标是否仍在视口内（防止切屏后消失）
        const W = 360, H = 500;
        const left = Math.min(Math.max(0, parseInt($chat.style.left) || 0), window.innerWidth  - W);
        const top  = Math.min(Math.max(0, parseInt($chat.style.top)  || 0), window.innerHeight - H);
        $chat.style.left = left + 'px';
        $chat.style.top  = top  + 'px';
      }
      $chat.classList.add('appearing');
      setTimeout(() => $chat.classList.remove('appearing'), 200);
      // 清除未读徽标
      const $b = document.getElementById('wfcwFbBadge');
      if ($b) $b.style.display = 'none';
      $ball?.classList.remove('pulsing');
    }
  }

  function _positionChatNearBall() {
    const $chat = document.getElementById('wfcwFloatChat');
    const $ball = document.getElementById('wfcwFloatBall');
    if (!$chat || !$ball) return;
    const br = $ball.getBoundingClientRect();
    $chat.style.left   = Math.max(8, br.right - 360) + 'px';
    $chat.style.top    = Math.max(8, br.top - 508)   + 'px';
    $chat.style.right  = ''; $chat.style.bottom = '';
  }

  /* ── 左侧节点库折叠 ───────────────────────────────────────────────────── */
  function _initNsCollapse() {
    const $btn     = document.getElementById('wfcwNsCollapseBtn');
    const $sidebar = document.getElementById('wfcwNodeSidebar');
    if (!$btn || !$sidebar) return;

    if (localStorage.getItem(_lsk('wfcw.nsSidebarCollapsed')) === 'true') {
      $sidebar.classList.add('ns-collapsed');
    }

    $btn.addEventListener('click', () => {
      const collapsed = $sidebar.classList.toggle('ns-collapsed');
      localStorage.setItem(_lsk('wfcw.nsSidebarCollapsed'), collapsed);
      $btn.title = collapsed ? '展开面板' : '收起面板';
    });

    // 折叠状态下点击整个 header 区域也可展开
    const $hdr = $sidebar.querySelector('.wfcw-ns-hdr');
    if ($hdr) {
      $hdr.addEventListener('click', e => {
        if (!$sidebar.classList.contains('ns-collapsed')) return;
        if (e.target.closest('.wfcw-ns-collapse-btn')) return;
        $sidebar.classList.remove('ns-collapsed');
        localStorage.setItem(_lsk('wfcw.nsSidebarCollapsed'), 'false');
        $btn.title = '收起面板';
      });
    }
  }

  /* ── 左侧节点库拖拽调宽 ───────────────────────────────────────────────── */
  function _initNsResize() {
    const $handle  = document.getElementById('wfcwNsResize');
    const $sidebar = document.getElementById('wfcwNodeSidebar');
    if (!$handle || !$sidebar) return;

    // 恢复保存的宽度
    const saved = localStorage.getItem(_lsk('wfcw.nsWidth'));
    if (saved) $sidebar.style.width = saved;

    let _dragging = false, _startX = 0, _startW = 0;

    $handle.addEventListener('mousedown', e => {
      _dragging = true;
      _startX   = e.clientX;
      _startW   = $sidebar.offsetWidth;
      $handle.classList.add('dragging');
      document.body.style.cursor     = 'col-resize';
      document.body.style.userSelect = 'none';
      e.preventDefault();
    });

    document.addEventListener('mousemove', e => {
      if (!_dragging) return;
      const dx   = e.clientX - _startX;           // 向右拖 → 变宽
      const newW = Math.min(260, Math.max(80, _startW + dx));
      $sidebar.style.width = newW + 'px';
    });

    document.addEventListener('mouseup', () => {
      if (!_dragging) return;
      _dragging = false;
      $handle.classList.remove('dragging');
      document.body.style.cursor     = '';
      document.body.style.userSelect = '';
      localStorage.setItem(_lsk('wfcw.nsWidth'), $sidebar.style.width);
    });
  }

  /* ── 右侧面板拖拽调宽 ─────────────────────────────────────────────────── */
  function _initApResize() {
    const $handle = document.getElementById('wfcwApResize');
    const $panel  = document.getElementById('wfcwAiPanel');
    if (!$handle || !$panel) return;

    // 恢复保存的宽度（折叠状态下不设置，让 CSS 控制 28px）
    const saved = localStorage.getItem(_lsk('wfcw.apWidth'));
    if (saved && !$panel.classList.contains('collapsed')) $panel.style.width = saved;

    let _dragging = false, _startX = 0, _startW = 0;

    $handle.addEventListener('mousedown', e => {
      _dragging = true;
      _startX   = e.clientX;
      _startW   = $panel.offsetWidth;
      $handle.classList.add('dragging');
      document.body.style.cursor    = 'col-resize';
      document.body.style.userSelect = 'none';
      e.preventDefault();
    });

    document.addEventListener('mousemove', e => {
      if (!_dragging) return;
      const dx   = _startX - e.clientX;          // 向左拖 → 变宽
      const newW = Math.min(520, Math.max(160, _startW + dx));
      $panel.style.width = newW + 'px';
    });

    document.addEventListener('mouseup', () => {
      if (!_dragging) return;
      _dragging = false;
      $handle.classList.remove('dragging');
      document.body.style.cursor    = '';
      document.body.style.userSelect = '';
      localStorage.setItem(_lsk('wfcw.apWidth'), $panel.style.width);
    });
  }

  /* ── 启动 ────────────────────────────────────────────────────────────── */
  function _init() {
    _initAuth();
    _initCanvas();
    _initCtxToggle();
    _initTopicPanel();
    _initCcPanel();
    _initFlowSidebar();
    _initFloatBall();
    _initFloatChat();
    _initToolsPanel();
    _initSkillsPanel();
    _initAtMention();
    _initNsCollapse();
    _initNsResize();
    _initHDivider();
    _initModeBadge();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _init);
  } else {
    _init();
  }

})();
