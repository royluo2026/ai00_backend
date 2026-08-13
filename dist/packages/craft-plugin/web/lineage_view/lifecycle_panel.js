'use strict';
/**
 * lifecycle_panel.js — BOP 生命周期面板
 *
 * 挂载到布局视图右侧边栏的 #lvLifecycleTop（上区）和 #lvLifecycleAction（下区）。
 * 依赖通过构造函数注入，不直接依赖 lineage.js 全局变量。
 */

const _LC_PHASE_LABELS = {
  init:          '新建',
  // refine:        '完善',            // 暂注释：完善已并入"升版"
  // publish_cycle: '发布/更新',       // 暂注释：发布/更新已并入"升版"
  promote:       '升版',
  snapshots:     '切片历史',
  archived:      '归档',
};
const _LC_PHASE_ORDER = ['init', 'promote', 'snapshots', 'archived'];

// 数据阶段序列（与后端一致，Pre-TG0→SOP）
const _LC_DATA_STAGES = ['Pre-TG0','TG0','TG1','PreTG2','TG2','EP1','EP2','PPV','PP','P','SOP'];

class BopLifecyclePanel {
  /**
   * @param {object} deps
   * @param {Function}    deps.cf         async fetch wrapper: cf(url, opts?) → json
   * @param {Function}    deps.toast      toast(msg, type)
   * @param {string}      deps.versionGid 当前 BOP 版本 gid
   * @param {HTMLElement} deps.mountEl    上区挂载点 #lvLifecycleTop
   * @param {HTMLElement} deps.actionEl   下区挂载点 #lvLifecycleAction
   */
  constructor({ cf, toast, versionGid, mountEl, actionEl, onBopTreeChange }) {
    this._cf          = cf;
    this._toast       = toast;
    this._versionGid  = versionGid;
    this._mountEl     = mountEl;
    this._actionEl    = actionEl;
    this._onBopTreeChange = onBopTreeChange || null;

    this._data         = null;
    this._viewPhase    = null;
    this._selectedLine = '';     // '' = 整体，gid = 某线体
    this._selectedItem = null;
    this._pillView     = 'publish';
    this._activeEntryGid = null;
    this._lastRefresh  = 0;
    this._creationMode = false;  // true = 新建模式（无 versionGid）
  }

  // ── 公开 API ───────────────────────────────────────────────────────────────

  async init() {
    if (!this._versionGid) return;
    this._bindKeys();
    await this._load();
  }

  _bindKeys() {
    const handler = e => {
      // 只响应全局按键，不拦截文本框内输入
      const tag = document.activeElement?.tagName?.toLowerCase();
      if (tag === 'input' || tag === 'textarea' || tag === 'select' ||
          document.activeElement?.isContentEditable) return;

      if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) {
        e.preventDefault();
        this._doUndo();
      }
      if ((e.ctrlKey || e.metaKey) && (e.key === 'Z' || (e.key === 'z' && e.shiftKey))) {
        e.preventDefault();
        this._doRedo();
      }
    };
    document.addEventListener('keydown', handler);
    // 弱引用销毁入口：panel 销毁时移除
    this._keyHandler = handler;
  }

  async _doUndo() {
    const lineGid = this._selectedLine || '';
    if (!lineGid) { this._toast?.('请先选择线体', 'warn'); return; }
    try {
      const resp = await this._cf(
        `/api/bop/versions/${this._versionGid}/lifecycle/lines/${lineGid}/undo`,
        { method: 'POST' }
      );
      this._toast?.('已撤销', 'ok');
      if (resp.operation_log) this._lastOperationLog = resp.operation_log;
      this._renderSideHistoryPanel();
      await this._load();
      if (this._onBopTreeChange) this._onBopTreeChange();
    } catch (e) {
      this._toast?.('撤销失败: ' + e.message, 'error');
    }
  }

  async _doRedo() {
    const lineGid = this._selectedLine || '';
    if (!lineGid) { this._toast?.('请先选择线体', 'warn'); return; }
    try {
      const resp = await this._cf(
        `/api/bop/versions/${this._versionGid}/lifecycle/lines/${lineGid}/redo`,
        { method: 'POST' }
      );
      this._toast?.('已重做', 'ok');
      if (resp.operation_log) this._lastOperationLog = resp.operation_log;
      this._renderSideHistoryPanel();
      await this._load();
      if (this._onBopTreeChange) this._onBopTreeChange();
    } catch (e) {
      this._toast?.('重做失败: ' + e.message, 'error');
    }
  }

  /** 进入新建模式：展示路线选择，不依赖任何已有版本 */
  enterCreationMode() {
    this._creationMode = true;
    this._versionGid   = null;
    this._data         = null;
    this._viewPhase    = 'init';
    this._selectedItem = null;
    if (this._actionEl) {
      // lvLifecycleAction starts with display:none in HTML. When the page is
      // already in layout mode, entering creation mode does not run
      // _syncLayoutUI again, so make the creation area visible explicitly.
      this._actionEl.style.display = '';
      this._actionEl.innerHTML =
        '<div class="lv-cpanel-empty">请在上方选择一种新建路线</div>';
    }
    const historyPanel = document.getElementById('lvHistorySidePanel');
    if (historyPanel) {
      this._historyDisplayBeforeCreation = historyPanel.style.display;
      historyPanel.style.display = 'none';
    }
    this._renderCreationMode();
    // 工具栏“新建”的主路径就是创建空白版本：右侧栏打开后立即展示
    // 可填写表单；上方路线按钮仍可切换到模板、现有版本或 TC 导入。
    void this._handleRouteSelect('blank');
  }

  _renderCreationMode() {
    if (!this._mountEl) return;
    const wrap = document.createElement('div');
    wrap.style.cssText = 'padding:10px 12px';

    const hdr = document.createElement('div');
    hdr.style.cssText =
      'font-size:10px;color:var(--overlay0,#6c7086);letter-spacing:.08em;' +
      'text-transform:uppercase;margin-bottom:6px';
    hdr.textContent = 'BOP 生命周期 — 新建';
    wrap.appendChild(hdr);

    // Init card（此时 lifecycle_state 为 null，_renderInitCard 会走路线选择分支）
    const card = document.createElement('div');
    card.className = 'lv-lc-card';
    card.appendChild(this._renderInitCard());
    wrap.appendChild(card);

    this._mountEl.innerHTML = '';
    this._mountEl.appendChild(wrap);
  }

  async refresh(force = false) {
    const now = Date.now();
    if (!force && now - this._lastRefresh < 10 * 60 * 1000) return;
    try {
      await this._cf(
        `/api/bop/versions/${this._versionGid}/lifecycle/refresh-stats`,
        { method: 'POST' }
      );
      await this._load();
      this._lastRefresh = Date.now();
    } catch (e) {
      this._toast('刷新失败: ' + e.message, 'error');
    }
  }


  setActiveEntry(gid) {
    this._activeEntryGid = gid || null;
  }

  setActiveLine(gid) {
    this._selectedLine = gid || '';
    this._renderSideHistoryPanel();
  }

  setVersionGid(gid) {
    this._creationMode = false;
    this._versionGid   = gid;
    this._data         = null;
    this._viewPhase    = null;
    this._selectedLine = '';
    this._selectedItem = null;
    this._activeEntryGid = null;
    this._lastRefresh  = 0;
    const historyPanel = document.getElementById('lvHistorySidePanel');
    if (historyPanel && this._historyDisplayBeforeCreation !== undefined) {
      historyPanel.style.display = this._historyDisplayBeforeCreation;
      this._historyDisplayBeforeCreation = undefined;
    }
    this._renderSideHistoryPanel();
    if (gid) {
      this.init();
    } else {
      if (this._mountEl)  this._mountEl.innerHTML  = '';
      if (this._actionEl) this._actionEl.innerHTML = '';
    }
  }


  async _load() {
    try {
      this._data = await this._cf(
        `/api/bop/versions/${this._versionGid}/lifecycle`
      );
      // 兼容老 lifecycle_phase：refine/publish_cycle 视为 promote
      let ph = this._data.lifecycle_phase;
      if (ph && !_LC_PHASE_ORDER.includes(ph)) {
        if (ph === 'refine' || ph === 'publish_cycle') ph = 'promote';
        else ph = 'init';
      }
      if (!this._viewPhase || !_LC_PHASE_ORDER.includes(this._viewPhase)) {
        this._viewPhase = ph || 'init';
      }
      this._render();
    } catch (e) {
      if (this._mountEl) {
        this._mountEl.innerHTML =
          `<div style="padding:12px;font-size:11px;color:#f38ba8">加载失败: ${e.message}</div>`;
      }
    }
  }

  // ── 渲染入口 ───────────────────────────────────────────────────────────────

  _render() {
    if (!this._data || !this._mountEl) return;

    const wrap = document.createElement('div');
    wrap.style.cssText = 'padding:10px 12px;';

    // 标题行
    const hdr = document.createElement('div');
    hdr.style.cssText =
      'font-size:12px;color:var(--text,#cdd6f4);letter-spacing:.08em;' +
      'text-transform:uppercase;margin-bottom:6px;display:flex;align-items:center;justify-content:space-between';
    const bopLabel = [this._data.bop_name, this._data.version_tag, this._data.data_stage].filter(Boolean).join(' · ');
    hdr.innerHTML =
      `<span>BOP 生命周期${bopLabel ? `<span style="font-size:11px;font-weight:400;letter-spacing:0;text-transform:none;color:var(--subtext1,#bac2de);margin-left:8px">${bopLabel}</span>` : ''}</span>` +
      '<button id="lv-lc-refresh" title="刷新指标" style="background:transparent;border:none;' +
      'cursor:pointer;color:var(--subtext0,#a6adc8);font-size:12px;padding:0;line-height:1">↻</button>';
    hdr.querySelector('#lv-lc-refresh').addEventListener('click', () => this.refresh(true));
    wrap.appendChild(hdr);

    wrap.appendChild(this._renderPhaseBar(this._data.lifecycle_phase));
    wrap.appendChild(this._renderPhaseCard(this._viewPhase));

    this._mountEl.innerHTML = '';
    this._mountEl.appendChild(wrap);
    this._renderSideHistoryPanel();
  }

  // ── 阶段条 ─────────────────────────────────────────────────────────────────

  _renderPhaseBar(currentPhase) {
    const bar = document.createElement('div');
    bar.className = 'lv-lc-phase-bar';
    // 兼容老 lifecycle_phase：refine/publish_cycle 视为 promote
    let cp = currentPhase;
    if (cp && !_LC_PHASE_ORDER.includes(cp)) {
      if (cp === 'refine' || cp === 'publish_cycle') cp = 'promote';
      else cp = 'init';
    }
    const currentIdx = _LC_PHASE_ORDER.indexOf(cp);

    _LC_PHASE_ORDER.forEach((ph, i) => {
      const seg = document.createElement('div');
      seg.className = 'lv-lc-phase-seg';
      if (i < currentIdx) {
        seg.classList.add('done');
        seg.textContent = '✓ ' + _LC_PHASE_LABELS[ph];
      } else if (ph === cp) {
        seg.classList.add('active');
        seg.textContent = '▶ ' + _LC_PHASE_LABELS[ph];
      } else {
        seg.classList.add('locked');
        seg.textContent = '🔒 ' + _LC_PHASE_LABELS[ph];
      }
      seg.addEventListener('click', () => {
        this._viewPhase    = ph;
        this._selectedItem = null;
        this._render();
      });
      bar.appendChild(seg);
    });
    return bar;
  }

  // ── 阶段卡片分派 ──────────────────────────────────────────────────────────

  _renderPhaseCard(phase) {
    const card = document.createElement('div');
    card.className = 'lv-lc-card';
    switch (phase) {
      case 'init':          card.appendChild(this._renderInitCard());         break;
      // refine / publish_cycle 已注释，由 promote 替代
      // case 'refine':        card.appendChild(this._renderRefineCard());  break;
      // case 'publish_cycle': card.appendChild(this._renderPublishCard()); break;
      case 'promote':       card.appendChild(this._renderPromoteCard());      break;
      case 'snapshots':     card.appendChild(this._renderSnapshotsListCard()); break;
      case 'archived':      card.appendChild(this._renderArchivedCard());    break;
    }
    return card;
  }

  // ── 升版卡片 ────────────────────────────────────────────────────────────
  // 替代原"完善" + "发布/更新"两个 Tab：用户选择目标数据阶段（或本阶段仅升版本号）后，
  // 调用后端 /promote（=freeze-snapshot 别名）创建快照副本 + 活动版本原地推进。
  _renderPromoteCard() {
    const frag = document.createDocumentFragment();
    const d    = this._data || {};
    const ver  = {
      data_stage:  d.data_stage,
      version_tag: d.version_tag,
    };
    const curStage = ver.data_stage || '';
    const curTag   = ver.version_tag || '';
    const stageIdx = _LC_DATA_STAGES.indexOf(curStage);

    // 当前信息
    const info = document.createElement('div');
    info.style.cssText = 'font-size:12px;color:var(--text,#cdd6f4);margin-bottom:10px;line-height:1.6';
    info.innerHTML =
      `<div>当前版本：<b>${this._esc(curTag) || '—'}</b>` +
      ` &nbsp;数据阶段：<b style="color:var(--blue,#89b4fa)">${this._esc(curStage) || '—'}</b></div>` +
      `<div style="font-size:11px;color:var(--subtext0,#a6adc8);margin-top:4px">` +
      `升版会把当前状态冻结为快照（保留旧 data_stage、用新 gid），活动版本 gid 不变。</div>`;
    frag.appendChild(info);

    // 目标数据阶段下拉
    const lbl = document.createElement('div');
    lbl.style.cssText = 'font-size:11px;color:var(--subtext0,#a6adc8);margin:8px 0 4px';
    lbl.textContent = '目标数据阶段';
    frag.appendChild(lbl);

    const stageSel = document.createElement('select');
    stageSel.style.cssText = 'width:100%;padding:6px 8px;font-size:12px;margin-bottom:12px';
    stageSel.innerHTML = `<option value="">— 仅升版本号（保持 ${this._esc(curStage)}） —</option>` +
      _LC_DATA_STAGES
        .slice(stageIdx + 1)   // 只能选当前阶段之后
        .map(s => `<option value="${s}">${s}</option>`).join('');
    frag.appendChild(stageSel);

    // change_note
    const noteLbl = document.createElement('div');
    noteLbl.style.cssText = 'font-size:11px;color:var(--subtext0,#a6adc8);margin:4px 0';
    noteLbl.textContent = '变更备注（可选）';
    frag.appendChild(noteLbl);
    const noteInput = document.createElement('input');
    noteInput.type = 'text';
    noteInput.placeholder = '说明本次升版原因…';
    noteInput.style.cssText = 'width:100%;padding:6px 8px;font-size:12px;margin-bottom:12px;box-sizing:border-box';
    frag.appendChild(noteInput);

    // 升版按钮
    const btn = document.createElement('button');
    btn.textContent = '升版';
    btn.className = 'lv-lc-btn lv-lc-btn-primary';
    btn.style.cssText = 'width:100%;padding:8px;font-size:13px;cursor:pointer';
    btn.onclick = async () => {
      const target = stageSel.value;
      const sameStage = !target;
      btn.disabled = true;
      const orig = btn.textContent;
      btn.textContent = '升版中…';
      try {
        const resp = await this._cf(`/api/bop/versions/${this._versionGid}/promote`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            target_data_stage: target || null,
            same_stage: sameStage,
            change_note: noteInput.value || null,
            bump_version_tag: true,
            promote_to_m: false,
          }),
        });
        const msg = sameStage
          ? `已升版至 ${resp.new_version_tag}（保留 ${resp.new_data_stage}）`
          : `已升版至 ${resp.new_version_tag}（${resp.new_data_stage}）`;
        this._toast?.(msg, 'ok');
        await this._load();
        if (this._onBopTreeChange) this._onBopTreeChange();
      } catch (e) {
        this._toast?.('升版失败: ' + e.message, 'error');
      } finally {
        btn.disabled = false;
        btn.textContent = orig;
      }
    };
    frag.appendChild(btn);
    return frag;
  }

  // ── 切片历史卡片（独立 Tab）────────────────────────────────────────────
  // 列出本版本族所有 baseline/M 快照，提供入口
  _renderSnapshotsListCard() {
    const frag = document.createDocumentFragment();
    const d    = this._data || {};
    const famGid = d.version_family_gid || this._versionGid;
    const allVers = d.all_versions_in_family || [];

    let snaps = [];
    try {
      snaps = allVers.filter(v =>
        (v.version_family_gid || v.gid) === famGid &&
        v.status !== 'active' && !v.archived_at
      );
    } catch {}

    const hdr = document.createElement('div');
    hdr.style.cssText = 'font-size:12px;color:var(--subtext0,#a6adc8);margin-bottom:8px';
    hdr.textContent = `共 ${snaps.length} 个历史快照`;
    frag.appendChild(hdr);

    if (!snaps.length) {
      const empty = document.createElement('div');
      empty.style.cssText = 'font-size:12px;color:var(--overlay0,#6c7086);padding:10px 0';
      empty.textContent = '暂无快照。升版时会自动保留快照。';
      frag.appendChild(empty);
      return frag;
    }

    snaps.forEach(s => {
      const row = document.createElement('div');
      row.style.cssText = 'display:flex;align-items:center;gap:6px;padding:6px 8px;' +
        'border:1px solid var(--surface1,#313244);border-radius:6px;margin-bottom:6px;cursor:pointer';
      const statusLbl = s.status === 'M' ? '发布' : (s.status === 'baseline' ? '基线' : s.status);
      row.innerHTML =
        `<span style="font-size:12px;font-weight:600;min-width:48px">${this._esc(s.version_tag || '')}</span>` +
        `<span style="font-size:11px;padding:1px 5px;border-radius:3px;` +
        `background:rgba(137,180,250,.15);color:var(--blue,#89b4fa)">${this._esc(s.data_stage || '')}</span>` +
        `<span style="font-size:11px;padding:1px 5px;border-radius:3px;` +
        `background:rgba(64,160,43,.12);color:var(--green,#40a02b)">${statusLbl}</span>` +
        `<span style="font-size:10px;color:var(--subtext0,#a6adc8);margin-left:auto">` +
        `${this._esc((s.change_note || '').slice(0, 30))}</span>`;
      row.onclick = () => {
        if (s.gid && confirm(`查看快照 ${s.version_tag}(${s.data_stage})?\n（历史快照为只读）`)) {
          // 让宿主（lineage.js）通过版本切换菜单处理快照查看
          if (this._onViewSnapshot) this._onViewSnapshot(s.gid);
        }
      };
      row.onmouseenter = () => row.style.background = 'var(--surface1,#313244)';
      row.onmouseleave = () => row.style.background = '';
      frag.appendChild(row);
    });
    return frag;
  }

  // 简单 HTML 转义（避免重复依赖外部）
  _esc(s) {
    if (s == null) return '';
    return String(s).replace(/[&<>"']/g, c =>
      ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
  }

  // ── 新建初版卡片（完整向导） ────────────────────────────────────────────

  // 每个路线的步骤定义：key/label/action
  // 四条路线共用的 PBOM 三步骤
  _PBOM_COMMON_STEPS = [
    { key: 'vpps_imported',     label: 'PBOM 导入',       action: 'open_vpps_import' },
    { key: 'pbom_vpps_checked', label: 'PBOM VPPS 核对',  action: 'open_pbom_check'  },
    { key: 'pbom_linked',       label: 'PBOM 连接工序',   action: 'guide_pbom_link'  },
  ];

  _ROUTE_STEPS = {
    blank: [
      { key: 'version_created',    label: '创建版本',   action: 'auto'     },
      { key: 'lines_added',        label: '添加线体/工位/工序', action: 'add_line', hint: '添加线体后，右键节点可继续添加工位和工序子节点' },
      { key: 'vpps_imported',      label: 'PBOM 导入', action: 'open_vpps_import' },
    ],
    from_template: [
      { key: 'template_selected',  label: '选择模板并创建版本', action: 'open_from_tmpl'   },
      ...this._PBOM_COMMON_STEPS,
      { key: 'vehicle_ops_prep',   label: '车型工序准备',       action: 'open_vehicle_ops' },
      { key: 'vehicle_ops_linked', label: '车型工序链接',       action: 'guide', hint: '将工序节点与车型 BOM 零件关联' },
    ],
    from_existing: [
      { key: 'source_selected',    label: '选择来源版本并创建', action: 'open_fork'        },
      ...this._PBOM_COMMON_STEPS,
      { key: 'vehicle_ops_prep',   label: '车型工序准备',       action: 'open_vehicle_ops' },
      { key: 'vehicle_ops_linked', label: '车型工序链接',       action: 'guide', hint: '将工序节点与车型 BOM 零件关联' },
    ],
    tc_import: [
      { key: 'tc_imported',        label: 'TC Excel 导入', action: 'open_tc_import' },
      ...this._PBOM_COMMON_STEPS,
    ],
  };

  _ROUTE_LABELS = {
    blank:         '新建空白',
    from_template: '从模板新建',
    from_existing: '从现有版本新建',
    tc_import:     'TC 导入',
  };

  _renderInitCard() {
    const frag      = document.createDocumentFragment();
    const initState = this._data?.lifecycle_state?.init || {};
    const route     = initState.route || null;

    if (!route) {
      // ── 路线选择界面 ──────────────────────────────────────────────────
      const title = document.createElement('div');
      title.style.cssText =
        'font-size:11px;font-weight:600;color:var(--text,#cdd6f4);margin-bottom:10px';
      title.textContent = '选择新建路线';
      frag.appendChild(title);

      const grid = document.createElement('div');
      grid.style.cssText = 'display:grid;grid-template-columns:1fr 1fr;gap:6px';

      [
        { id: 'blank',         icon: '📄', label: '新建空白' },
        { id: 'from_template', icon: '📋', label: '从模板新建' },
        { id: 'from_existing', icon: '🔀', label: '从现有版本' },
        { id: 'tc_import',     icon: '📥', label: 'TC 导入' },
      ].forEach(({ id, icon, label }) => {
        const btn = document.createElement('button');
        btn.style.cssText =
          'padding:8px 4px;background:var(--surface1,#45475a);border:1px solid var(--surface2,#585b70);' +
          'border-radius:5px;cursor:pointer;font-size:10px;color:var(--text,#cdd6f4);' +
          'display:flex;flex-direction:column;align-items:center;gap:3px;transition:background .1s';
        btn.innerHTML =
          `<span style="font-size:16px">${icon}</span><span>${label}</span>`;
        btn.addEventListener('mouseenter', () => btn.style.background = 'var(--surface2,#585b70)');
        btn.addEventListener('mouseleave', () => btn.style.background = 'var(--surface1,#45475a)');
        btn.addEventListener('click', () => this._handleRouteSelect(id));
        grid.appendChild(btn);
      });
      frag.appendChild(grid);

    } else {
      // ── 步骤列表界面（路线已选定）────────────────────────────────────
      const routeRow = document.createElement('div');
      routeRow.style.cssText =
        'display:flex;align-items:center;justify-content:space-between;' +
        'margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid var(--surface1,#45475a)';

      const routeLabel = document.createElement('span');
      routeLabel.style.cssText = 'font-size:10px;font-weight:600;color:var(--blue,#89b4fa)';
      routeLabel.textContent = '路线：' + (this._ROUTE_LABELS[route] || route);

      const resetBtn = document.createElement('button');
      resetBtn.style.cssText =
        'background:transparent;border:1px solid var(--overlay0,#6c7086);border-radius:3px;' +
        'cursor:pointer;font-size:9px;color:var(--subtext0,#a6adc8);padding:2px 7px;' +
        'transition:border-color .1s,color .1s';
      resetBtn.textContent = '重置路线';
      resetBtn.title = '卡住了？重置路线和步骤进度重新开始（版本数据不受影响）';
      resetBtn.addEventListener('mouseenter', () => {
        resetBtn.style.borderColor = 'var(--red,#f38ba8)';
        resetBtn.style.color = 'var(--red,#f38ba8)';
      });
      resetBtn.addEventListener('mouseleave', () => {
        resetBtn.style.borderColor = 'var(--overlay0,#6c7086)';
        resetBtn.style.color = 'var(--subtext0,#a6adc8)';
      });
      resetBtn.addEventListener('click', () => {
        if (confirm('确认重置路线？当前步骤进度将清空，版本本身不受影响。')) {
          this._saveInitState({ route: null, checklist: {} });
        }
      });

      routeRow.appendChild(routeLabel);
      routeRow.appendChild(resetBtn);
      frag.appendChild(routeRow);

      const steps     = this._ROUTE_STEPS[route] || [];
      const checklist = initState.checklist || {};
      const firstPendingIdx = steps.findIndex(s => !checklist[s.key]);

      steps.forEach((step, idx) => {
        const done    = !!checklist[step.key];
        const current = idx === firstPendingIdx;

        const itemWrap = document.createElement('div');
        itemWrap.style.cssText = 'margin-bottom:6px';

        const row = document.createElement('div');
        row.style.cssText =
          `display:flex;align-items:center;gap:6px;padding:4px 6px;border-radius:4px;` +
          `background:${current ? 'var(--base,#1e1e2e)' : 'transparent'};` +
          `${current ? 'border-left:2px solid var(--blue,#89b4fa);' : ''}`;

        const dot = document.createElement('div');
        dot.style.cssText =
          `width:8px;height:8px;border-radius:50%;flex-shrink:0;` +
          `background:${done ? 'var(--green,#a6e3a1)' : current ? 'var(--blue,#89b4fa)' : 'var(--surface2,#585b70)'}`;

        const stepLabel = document.createElement('span');
        stepLabel.style.cssText =
          `flex:1;font-size:10px;` +
          `color:${done ? 'var(--green,#a6e3a1)' : current ? 'var(--text,#cdd6f4)' : 'var(--overlay0,#6c7086)'}`;
        stepLabel.textContent = (done ? '✓ ' : '') + step.label;

        row.appendChild(dot);
        row.appendChild(stepLabel);

        // 已完成步骤显示撤销按钮
        if (done && step.action !== 'auto') {
          const undoBtn = document.createElement('button');
          undoBtn.textContent = '↩';
          undoBtn.title = '撤销此步骤';
          undoBtn.style.cssText =
            'padding:1px 5px;font-size:10px;background:transparent;' +
            'border:1px solid var(--surface2,#585b70);border-radius:3px;' +
            'color:var(--subtext0,#a6adc8);cursor:pointer;flex-shrink:0;' +
            'line-height:1.4';
          undoBtn.addEventListener('click', e => {
            e.stopPropagation();
            this._undoStep(step.key);
          });
          row.appendChild(undoBtn);
        }

        itemWrap.appendChild(row);

        // 当前步骤在下部操作区显示（点击步骤行可切换）
        if (current) {
          row.style.cursor = 'pointer';
          row.addEventListener('click', () => this._showStepAction(step, initState));
          this._showStepAction(step, initState); // 自动打开当前步骤
        } else if (done && step.action !== 'auto') {
          // 已完成步骤也可点击切换操作区
          row.style.cursor = 'pointer';
          row.addEventListener('click', () => this._showStepAction(step, initState));
        }

        frag.appendChild(itemWrap);
      });

      const allDone = steps.every(s => !!checklist[s.key]);
      if (allDone) {
        const done = document.createElement('div');
        done.style.cssText =
          'text-align:center;font-size:11px;color:var(--green,#a6e3a1);padding:6px 0;margin-bottom:4px';
        done.textContent = '✓ 所有步骤已完成';
        frag.appendChild(done);
      }

    }

    this._appendConfirmBtn(frag, 'init');
    return frag;
  }

  // 路线选择按钮处理
  async _handleRouteSelect(routeId) {
    const flows = {
      blank:         () => this._showBlankCreationForm(),
      from_template: () => this._showFromTemplateFlow(),
      from_existing: () => this._showFromExistingFlow(),
      tc_import:     () => this._showTcImportFlow(),
    };
    const openFlow = flows[routeId];
    if (!openFlow) return;
    try {
      await openFlow();
    } catch (e) {
      if (this._actionEl) {
        this._actionEl.innerHTML =
          '<div class="lv-cpanel-empty">新建内容加载失败，请重试</div>';
      }
      this._toast?.('新建内容加载失败: ' + e.message, 'error');
    }
  }

  // 当前步骤在下部操作区显示
  _showStepAction(step, initState) {
    if (!this._actionEl) return;
    this._actionEl.innerHTML = '';

    const title = document.createElement('div');
    title.className   = 'lv-lc-action-title';
    title.textContent = step.label;
    this._actionEl.appendChild(title);

    if (step.action === 'auto') {
      this._markStepDone(step.key);
      return;
    }

    if (step.action === 'add_line') {
      const addBtn = this._makeActionBtn('＋ 新建空白线体', () => {
        if (typeof _addBlankLine === 'function') _addBlankLine();
      });
      this._actionEl.appendChild(addBtn);
      this._actionEl.appendChild(this._makeMarkDoneBtn(step.key));
      return;
    }

    if (step.action === 'guide' && step.hint) {
      const hint = document.createElement('div');
      hint.style.cssText =
        'font-size:10px;color:var(--subtext0,#a6adc8);line-height:1.6;margin-bottom:8px';
      hint.textContent = step.hint;
      this._actionEl.appendChild(hint);
      this._actionEl.appendChild(this._makeMarkDoneBtn(step.key));
    } else if (step.action === 'open_pbom_check' || step.action === 'jump_pbom') {
      // 显示 VPPS 核对统计（从 _data.pbom_vpps_check 读取）
      const vc = this._data?.pbom_vpps_check || {};
      if (vc.total > 0) {
        const statsDiv = document.createElement('div');
        statsDiv.style.cssText =
          'background:var(--base,#1e1e2e);border-radius:6px;padding:8px 10px;margin-bottom:8px;font-size:11px';
        const nokColor = vc.nok > 0 ? 'var(--red,#f38ba8)' : 'var(--green,#a6e3a1)';
        statsDiv.innerHTML =
          `<div style="display:flex;justify-content:space-between;margin-bottom:3px">` +
          `<span style="color:var(--subtext0,#a6adc8)">PBOM 总数</span><span>${vc.total}</span></div>` +
          `<div style="display:flex;justify-content:space-between;margin-bottom:3px">` +
          `<span style="color:var(--subtext0,#a6adc8)">NOK</span>` +
          `<span style="color:${nokColor};font-weight:600">${vc.nok}</span></div>` +
          `<div style="display:flex;justify-content:space-between">` +
          `<span style="color:var(--subtext0,#a6adc8)">已忽略</span><span>${vc.ignored}</span></div>`;
        if (vc.checked_at) {
          const ts = document.createElement('div');
          ts.style.cssText = 'font-size:10px;color:var(--overlay0,#6c7086);margin-top:4px';
          ts.textContent = '最后核对：' + vc.checked_at.slice(0, 16).replace('T', ' ');
          statsDiv.appendChild(ts);
        }
        this._actionEl.appendChild(statsDiv);
      }
      this._actionEl.appendChild(this._makeActionBtn('📦 打开 VPPS 核对窗口', async () => {
        const api = window.top?.electronAPI || window.parent?.electronAPI || window.electronAPI;
        if (api?.showPbomCheckWindow) {
          // 优先用本 BOP 版本在 PBOM 导入流程里创建的版本
          let pbomGid = '';
          try {
            const saved = JSON.parse(localStorage.getItem(`lc:pbom_import:${this._versionGid}`) || 'null');
            pbomGid = saved?.gid || '';
          } catch (_) {}
          // 降级：读 BOP 版本关联的 pbom_version_gid
          if (!pbomGid) {
            try {
              const res = await (window.parent?._cloudFetch || window._cloudFetch)?.(
                `/api/bop/versions/${this._versionGid}`
              );
              pbomGid = res?.data?.pbom_version_gid || '';
            } catch (_) {}
          }
          api.showPbomCheckWindow({ pbomGid, bopGid: this._versionGid || '' });
        } else {
          const top = window.top || window.parent || window;
          if (top.TabManager) top.TabManager.open('ebom');
        }
      }));
      this._actionEl.appendChild(this._makeMarkDoneBtn(step.key));
    } else if (step.action === 'guide_pbom_link') {
      this._renderPbomLinkStats();
    } else if (step.action === 'open_tc_import') {
      this._actionEl.appendChild(this._makeActionBtn('📥 开始 TC 导入', () => {
        if (typeof _verMgr !== 'undefined' && _verMgr?.openImportTcModal) {
          _verMgr.openImportTcModal();
        }
      }));
      this._actionEl.appendChild(this._makeMarkDoneBtn(step.key));
    } else if (step.action === 'open_from_tmpl') {
      this._actionEl.appendChild(this._makeActionBtn('📋 从模板新建版本', () => {
        if (typeof _verMgr !== 'undefined' && _verMgr?.openFromTmplModal) {
          _verMgr.openFromTmplModal();
        }
      }));
      this._actionEl.appendChild(this._makeMarkDoneBtn(step.key));
    } else if (step.action === 'open_fork') {
      this._actionEl.appendChild(this._makeActionBtn('🔀 从现有版本新建', () => {
        if (typeof _verMgr !== 'undefined' && _verMgr?.openForkModal) {
          _verMgr.openForkModal();
        }
      }));
      this._actionEl.appendChild(this._makeMarkDoneBtn(step.key));
    } else if (step.action === 'open_vehicle_ops') {
      this._renderVehicleOpsStep(step.key);
    } else if (step.action === 'open_vpps_import') {
      this._renderPbomImportFlow(step.key);
    }
  }

  // 新建空白版本表单（在下部操作区）
  async _showBlankCreationForm() {
    if (!this._actionEl) return;
    this._actionEl.innerHTML =
      '<div style="font-size:10px;color:var(--subtext0,#a6adc8)">加载项目列表…</div>';
    await this._ensureCaches();

    this._actionEl.innerHTML = '';
    const title = document.createElement('div');
    title.className   = 'lv-lc-action-title';
    title.textContent = '新建空白 BOP 版本';
    this._actionEl.appendChild(title);

    this._buildVersionForm(this._actionEl, {
      getSourceGid:   () => null,
      route:          'blank',
      submitLabel:    '创建空白版本',
      extraChecklist: { version_created: true },
    });
  }

  // ── 从模板新建（下部操作区）────────────────────────────────────────────

  async _showFromTemplateFlow() {
    if (!this._actionEl) return;
    this._actionEl.innerHTML =
      '<div style="font-size:10px;color:var(--subtext0,#a6adc8)">加载模板列表…</div>';
    await this._ensureCaches();

    this._actionEl.innerHTML = '';
    const title = document.createElement('div');
    title.className = 'lv-lc-action-title';
    title.textContent = '从模板新建';
    this._actionEl.appendChild(title);

    // 搜索框
    const searchBox = document.createElement('input');
    searchBox.type = 'search';
    searchBox.placeholder = '搜索模板名称…';
    searchBox.style.cssText =
      'width:100%;box-sizing:border-box;padding:4px 8px;font-size:10px;margin-bottom:6px;' +
      'background:var(--base,#1e1e2e);color:var(--text,#cdd6f4);' +
      'border:1px solid var(--surface2,#585b70);border-radius:4px';
    this._actionEl.appendChild(searchBox);

    // 模板列表
    const templates = (this._allVersionsCache || [])
      .filter(v => v.version_type === 'template' && !v.archived_at);
    const listEl = document.createElement('div');
    listEl.style.cssText =
      'border:1px solid var(--surface2,#585b70);border-radius:4px;' +
      'max-height:140px;overflow-y:auto;margin-bottom:8px';
    this._actionEl.appendChild(listEl);

    let selectedTmplGid = null;
    const renderList = (q) => {
      const filtered = q
        ? templates.filter(t => (t.bop_name||'').toLowerCase().includes(q.toLowerCase()))
        : templates;
      listEl.innerHTML = '';
      if (!filtered.length) {
        listEl.innerHTML =
          '<div style="padding:10px;font-size:10px;color:var(--subtext0,#a6adc8);text-align:center">暂无可用模板</div>';
        return;
      }
      filtered.forEach(tmpl => {
        const row = document.createElement('div');
        row.dataset.gid = tmpl.gid;
        row.style.cssText =
          'padding:6px 10px;border-bottom:1px solid var(--surface1,#45475a);' +
          'cursor:pointer;font-size:10px;transition:background .1s';
        const fac = (this._factoriesCache||[]).find(f => f.gid === tmpl.factory_gid);
        row.innerHTML =
          `<div style="font-weight:600;color:var(--text,#cdd6f4)">${tmpl.bop_name||tmpl.version_tag}</div>` +
          `<div style="font-size:9px;color:var(--subtext0,#a6adc8)">${fac?.name||'工厂未知'} · ${(tmpl.created_at||'').slice(0,10)}</div>`;
        row.addEventListener('click', () => {
          listEl.querySelectorAll('[data-gid]').forEach(el => {
            el.style.background = '';
            el.style.borderLeft = '';
          });
          row.style.background = 'var(--surface1,#45475a)';
          row.style.borderLeft = '2px solid var(--blue,#89b4fa)';
          selectedTmplGid = tmpl.gid;
          formEl.style.display = '';
        });
        listEl.appendChild(row);
      });
    };
    renderList('');
    searchBox.addEventListener('input', e => renderList(e.target.value));

    // 项目/命名表单（选模板后才显示）
    const formEl = document.createElement('div');
    formEl.style.display = 'none';
    this._buildVersionForm(formEl, {
      getSourceGid: () => selectedTmplGid,
      route: 'from_template',
      submitLabel: '从模板新建',
      extraChecklist: { template_selected: true },
    });
    this._actionEl.appendChild(formEl);
  }

  // ── 从现有版本新建（下部操作区）──────────────────────────────────────────

  async _showFromExistingFlow() {
    if (!this._actionEl) return;
    this._actionEl.innerHTML =
      '<div style="font-size:10px;color:var(--subtext0,#a6adc8)">加载版本列表…</div>';
    await this._ensureCaches();

    this._actionEl.innerHTML = '';
    const title = document.createElement('div');
    title.className = 'lv-lc-action-title';
    title.textContent = '从现有版本新建';
    this._actionEl.appendChild(title);

    // 来源版本选择
    const srcLabel = document.createElement('div');
    srcLabel.style.cssText = 'font-size:9px;color:var(--subtext0,#a6adc8);margin-bottom:3px';
    srcLabel.textContent = '来源版本 *';
    this._actionEl.appendChild(srcLabel);

    const srcSel = document.createElement('select');
    srcSel.style.cssText =
      'width:100%;padding:4px 6px;font-size:10px;background:var(--base,#1e1e2e);' +
      'color:var(--text,#cdd6f4);border:1px solid var(--surface2,#585b70);border-radius:4px;margin-bottom:10px';
    srcSel.innerHTML = '<option value="">— 选择来源版本 —</option>';
    (this._allVersionsCache||[])
      .filter(v => v.version_type !== 'template' && !v.archived_at)
      .forEach(v => {
        const opt = document.createElement('option');
        opt.value = v.gid;
        opt.textContent = (v.bop_name||'') + ' / ' + (v.version_tag||v.gid.slice(-6));
        srcSel.appendChild(opt);
      });
    this._actionEl.appendChild(srcSel);

    // 节点类型复选区（选来源后才显示）
    const nodeSection = document.createElement('div');
    nodeSection.style.display = 'none';
    this._actionEl.appendChild(nodeSection);

    // 保留的节点类型（全部选中的 keys）
    const NODE_GROUPS = [
      { label: 'L1 线体',   types: [
        { key: 'line_process',     zh: '线体工艺' },
      ]},
      { label: 'L2 工位',   types: [
        { key: 'station_process',  zh: '工位工艺' },
      ]},
      { label: 'L3 岗位',   types: [
        { key: 'operator_process', zh: '岗位工艺' },
      ]},
      { label: 'L4 工序层', types: [
        { key: 'process',          zh: '工序' },
        { key: 'man',              zh: '人员' },
        { key: 'station_factory',  zh: '工位节点' },
      ]},
      { label: 'L5 资源/工作项', types: [
        { key: 'operation',        zh: '操作步骤' },
        { key: 'equipment_factory',zh: '设备（现有）' },
        { key: 'tool_factory',     zh: '工具（现有）' },
        { key: 'equipment_need',   zh: '设备需求' },
        { key: 'fixture_factory',  zh: '工装（现有）' },
        { key: 'contral_plan',     zh: '控制计划' },
        { key: 'process_chart',    zh: '工艺卡' },
        { key: 'floor_height_factory', zh: '地面高度' },
        { key: 'issue',            zh: '问题' },
        { key: 'standard_task',    zh: '标准任务' },
        { key: 'non_standard_task',zh: '非标任务' },
        { key: 'knowledge',        zh: '知识' },
        { key: 'rule',             zh: '规则' },
      ]},
      { label: 'L6 零件/工具', types: [
        { key: 'part',             zh: '零部件' },
        { key: 'non_standard_part',zh: '非标件' },
        { key: 'standard_part',    zh: '标准件' },
        { key: 'support_material', zh: '辅料' },
        { key: 'tool_need',        zh: '工具需求' },
        { key: 'fixture_need',     zh: '工装需求' },
        { key: 'jack_pos',         zh: '人机姿态' },
      ]},
    ];

    const allCheckboxes = [];

    const nodeHdr = document.createElement('div');
    nodeHdr.style.cssText =
      'display:flex;align-items:center;justify-content:space-between;' +
      'font-size:9px;color:var(--subtext0,#a6adc8);margin-bottom:5px';
    nodeHdr.innerHTML =
      '<span>保留节点类型（默认全选）</span>' +
      '<span style="display:flex;gap:6px">' +
      '<button id="lc-check-all" style="font-size:9px;padding:1px 6px;background:transparent;border:1px solid var(--surface2,#585b70);border-radius:3px;color:var(--subtext0,#a6adc8);cursor:pointer">全选</button>' +
      '<button id="lc-check-none" style="font-size:9px;padding:1px 6px;background:transparent;border:1px solid var(--surface2,#585b70);border-radius:3px;color:var(--subtext0,#a6adc8);cursor:pointer">清空</button>' +
      '</span>';
    nodeSection.appendChild(nodeHdr);

    const checkWrap = document.createElement('div');
    checkWrap.style.cssText =
      'background:var(--base,#1e1e2e);border-radius:4px;padding:6px 8px;margin-bottom:8px;' +
      'max-height:180px;overflow-y:auto';
    nodeSection.appendChild(checkWrap);

    NODE_GROUPS.forEach(group => {
      const groupCbs = [];   // 本组的所有 checkbox

      // 组标题行（含全组复选框）
      const grpRow = document.createElement('div');
      grpRow.style.cssText =
        'display:flex;align-items:center;gap:5px;margin:6px 0 4px;' +
        (checkWrap.children.length > 0
          ? 'border-top:1px solid var(--surface1,#45475a);padding-top:6px' : '');

      const grpCb = document.createElement('input');
      grpCb.type    = 'checkbox';
      grpCb.checked = true;
      grpCb.style.cssText = 'margin:0;cursor:pointer;flex-shrink:0';
      grpCb.title = `全选/取消 ${group.label}`;

      const grpLabel = document.createElement('span');
      grpLabel.style.cssText =
        'font-size:9px;color:var(--subtext0,#a6adc8);text-transform:uppercase;' +
        'letter-spacing:.05em;cursor:pointer;user-select:none';
      grpLabel.textContent = group.label;
      grpLabel.addEventListener('click', () => {
        grpCb.checked = !grpCb.checked;
        grpCb.dispatchEvent(new Event('change'));
      });

      grpRow.appendChild(grpCb);
      grpRow.appendChild(grpLabel);
      checkWrap.appendChild(grpRow);

      // 子项行
      const itemsRow = document.createElement('div');
      itemsRow.style.cssText = 'display:flex;flex-wrap:wrap;gap:4px;padding-left:16px';
      group.types.forEach(({ key, zh }) => {
        const lbl = document.createElement('label');
        lbl.style.cssText =
          'display:flex;align-items:center;gap:3px;font-size:10px;color:var(--text,#cdd6f4);' +
          'cursor:pointer;padding:2px 5px;border-radius:3px;' +
          'border:1px solid var(--surface2,#585b70);white-space:nowrap';
        const cb = document.createElement('input');
        cb.type    = 'checkbox';
        cb.value   = key;
        cb.checked = true;
        cb.style.margin = '0';

        // 子项变化 → 更新组级状态
        cb.addEventListener('change', () => {
          const checkedCount = groupCbs.filter(c => c.checked).length;
          grpCb.indeterminate = checkedCount > 0 && checkedCount < groupCbs.length;
          grpCb.checked       = checkedCount === groupCbs.length;
        });

        lbl.appendChild(cb);
        lbl.appendChild(document.createTextNode(zh));
        itemsRow.appendChild(lbl);
        groupCbs.push(cb);
        allCheckboxes.push(cb);
      });
      checkWrap.appendChild(itemsRow);

      // 组级变化 → 整层开关
      grpCb.addEventListener('change', () => {
        groupCbs.forEach(cb => cb.checked = grpCb.checked);
      });
    });

    // 全选/清空
    nodeHdr.querySelector('#lc-check-all').addEventListener('click',
      () => allCheckboxes.forEach(cb => cb.checked = true));
    nodeHdr.querySelector('#lc-check-none').addEventListener('click',
      () => allCheckboxes.forEach(cb => cb.checked = false));

    const getSelectedTypes = () => {
      const checked = allCheckboxes.filter(cb => cb.checked).map(cb => cb.value);
      // 全选时传 null（fork API 默认行为），否则传选中列表
      return checked.length === allCheckboxes.length ? null : checked;
    };

    // 项目/命名表单
    const formEl = document.createElement('div');
    formEl.style.display = 'none';
    this._buildVersionForm(formEl, {
      getSourceGid:       () => srcSel.value || null,
      route:              'from_existing',
      submitLabel:        '从现有版本新建',
      extraChecklist:     { source_selected: true, layers_selected: true },
      getExtraForkParams: () => {
        const types = getSelectedTypes();
        return types ? { include_node_types: types } : {};
      },
    });
    nodeSection.appendChild(formEl);

    srcSel.addEventListener('change', () => {
      nodeSection.style.display = srcSel.value ? '' : 'none';
      formEl.style.display = srcSel.value ? '' : 'none';
    });
  }

  // ── TC 导入（下部操作区）────────────────────────────────────────────────

  async _showTcImportFlow() {
    if (!this._actionEl) return;
    this._actionEl.innerHTML =
      '<div style="font-size:10px;color:var(--subtext0,#a6adc8)">加载项目列表…</div>';
    await this._ensureCaches();

    this._actionEl.innerHTML = '';
    const title = document.createElement('div');
    title.className = 'lv-lc-action-title';
    title.textContent = 'TC 导入';
    this._actionEl.appendChild(title);

    // 流程说明
    const steps = ['PBOM 预处理', 'TC Excel 导入', 'PBOM 绑定'];
    const stepsEl = document.createElement('div');
    stepsEl.style.cssText =
      'display:flex;gap:4px;align-items:center;margin-bottom:8px;font-size:9px;color:var(--subtext0,#a6adc8)';
    steps.forEach((s, i) => {
      stepsEl.innerHTML += `<span style="background:var(--base,#1e1e2e);padding:2px 6px;border-radius:3px">${i+1}. ${s}</span>`;
      if (i < steps.length - 1) stepsEl.innerHTML += '<span>→</span>';
    });
    this._actionEl.appendChild(stepsEl);

    const hint = document.createElement('div');
    hint.style.cssText =
      'font-size:9px;color:var(--subtext0,#a6adc8);margin-bottom:8px;line-height:1.5';
    hint.textContent = '先创建空白版本，再按步骤完成 TC 导入流程。';
    this._actionEl.appendChild(hint);

    // 项目/命名表单（直接创建空白版本，保存 tc_import 路线）
    const formEl = document.createElement('div');
    this._buildVersionForm(formEl, {
      getSourceGid: () => null,          // 创建空白版本（无来源）
      route: 'tc_import',
      submitLabel: '创建版本并开始导入',
      extraChecklist: { pbom_preprocessed: false },
    });
    this._actionEl.appendChild(formEl);
  }

  // ── 公共：项目/族/命名表单构建器 ─────────────────────────────────────────

  /**
   * @param {HTMLElement} container   注入目标容器
   * @param {object} opts
   *   getSourceGid  () => string|null    来源版本/模板 gid（null = 创建空白版本）
   *   route         string               路线标识
   *   submitLabel   string               创建按钮文字
   *   extraChecklist object              额外的 checklist 初始状态
   */
  _buildVersionForm(container, { getSourceGid, route, submitLabel, extraChecklist = {}, getExtraForkParams }) {
    const allVers = this._allVersionsCache || [];

    const _sel = (placeholder) => {
      const s = document.createElement('select');
      s.style.cssText =
        'width:100%;padding:4px 6px;font-size:10px;background:var(--base,#1e1e2e);' +
        'color:var(--text,#cdd6f4);border:1px solid var(--surface2,#585b70);border-radius:4px;margin-bottom:8px';
      s.innerHTML = `<option value="">${placeholder}</option>`;
      return s;
    };
    const _label = (text) => {
      const l = document.createElement('div');
      l.style.cssText = 'font-size:9px;color:var(--subtext0,#a6adc8);margin-bottom:3px';
      l.textContent = text;
      return l;
    };
    const _DATA_STAGES = ['Pre-TG0','TG0','TG1','PreTG2','TG2','EP1','EP2','PPV','PP','P','SOP'];

    // 项目选择器
    container.appendChild(_label('所属项目 *'));
    const projSel = _sel('— 请选择项目 —');
    (this._projectsCache||[]).forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.gid;
      opt.dataset.projectName = p.name || p.gid;
      opt.dataset.factoryGid  = p.factory_gid || '';
      const fac = (this._factoriesCache||[]).find(f => f.gid === p.factory_gid);
      opt.dataset.factoryName = fac ? (fac.name || fac.gid) : '';
      opt.textContent = p.name || p.gid;
      projSel.appendChild(opt);
    });
    container.appendChild(projSel);

    container.appendChild(_label('所属版本族'));
    const famHint = document.createElement('div');
    famHint.style.cssText =
      'font-size:10px;padding:4px 6px;border-radius:4px;margin-bottom:8px;' +
      'background:var(--base,#1e1e2e);color:var(--subtext0,#a6adc8);min-height:20px';
    famHint.textContent = '请先选择项目';
    container.appendChild(famHint);
    const famSel = document.createElement('input'); famSel.type = 'hidden'; famSel.value = '';
    container.appendChild(famSel);
    const refreshFamilyByProject = () => {
      const selOpt = projSel.options[projSel.selectedIndex];
      const projName = selOpt?.dataset?.projectName || '';
      if (!projName) {
        famSel.value = '';
        famHint.textContent = '请先选择项目';
        famHint.style.color = 'var(--subtext0,#a6adc8)';
        return;
      }
      const match = allVers.find(v =>
        v.version_type !== 'template' && !v.archived_at &&
        (v.bop_name || '') === projName
      );
      if (match) {
        famSel.value = match.version_family_gid || match.gid;
        const cnt = allVers.filter(v =>
          (v.version_family_gid || v.gid) === famSel.value && !v.archived_at
        ).length;
        famHint.textContent = `加入已有版本族「${projName}」（现有 ${cnt} 个版本）`;
        famHint.style.color = 'var(--green,#40a02b)';
      } else {
        famSel.value = '';
        famHint.textContent = `将成为新版本族「${projName}」`;
        famHint.style.color = 'var(--blue,#89b4fa)';
      }
    };

    container.appendChild(_label('数据阶段 *（同族已用过的阶段会被禁用）'));
    const stageSel = _sel('— 请选择数据阶段 —');
    _DATA_STAGES.forEach(s => {
      const opt = document.createElement('option');
      opt.value = s; opt.textContent = s;
      stageSel.appendChild(opt);
    });
    container.appendChild(stageSel);

    // 同族已用过的 data_stage 选项禁用
    const refreshStageOptions = () => {
      const famGid = famSel.value;
      const usedStages = new Set(
        allVers
          .filter(v => famGid && (v.version_family_gid || v.gid) === famGid && !v.archived_at && v.data_stage)
          .map(v => v.data_stage)
      );
      Array.from(stageSel.options).forEach(opt => {
        if (!opt.value) return;
        const used = usedStages.has(opt.value);
        opt.disabled = used;
        opt.textContent = used ? `${opt.value}（已有）` : opt.value;
      });
      if (stageSel.value && stageSel.options[stageSel.selectedIndex]?.disabled) {
        stageSel.value = '';
      }
    };
    refreshStageOptions();

    const previewBox = document.createElement('div');
    previewBox.style.cssText =
      'background:var(--base,#1e1e2e);border-radius:4px;padding:5px 8px;margin-bottom:10px;font-size:10px';
    previewBox.innerHTML =
      '<span style="color:var(--overlay0,#6c7086)">命名预览：</span>' +
      '<span id="lc-form-preview" style="color:var(--subtext0,#a6adc8)">请先选择项目</span>';
    container.appendChild(previewBox);

    const hidTag     = document.createElement('input'); hidTag.type = 'hidden';
    const hidName    = document.createElement('input'); hidName.type = 'hidden';
    const hidFactory = document.createElement('input'); hidFactory.type = 'hidden';
    container.appendChild(hidTag);
    container.appendChild(hidName);
    container.appendChild(hidFactory);

    const updatePreview = () => {
      const preview = previewBox.querySelector('#lc-form-preview');
      const selOpt  = projSel.options[projSel.selectedIndex];
      if (!selOpt?.value) {
        preview.textContent = '请先选择项目';
        preview.style.color = 'var(--subtext0,#a6adc8)';
        hidTag.value = ''; hidName.value = ''; hidFactory.value = '';
        return;
      }
      const projName      = selOpt.dataset.projectName || '';
      const factoryGidVal = selOpt.dataset.factoryGid  || '';
      const stageVal  = stageSel.value;
      const famGidVal = famSel.value;
      let nextNum = 1;
      if (famGidVal) {
        const maxN = allVers
          .filter(v => (v.version_family_gid || v.gid) === famGidVal && !v.archived_at)
          .reduce((m, v) => {
            const n = parseInt((v.version_tag || '').replace(/^v/i, ''));
            return isNaN(n) ? m : Math.max(m, n);
          }, 0);
        nextNum = maxN + 1;
      }
      const tag     = `v${nextNum}`;
      // 版本族名只用项目名（不含数据阶段）；data_stage 单独存储
      const bopName = projName;
      hidTag.value     = tag;
      hidName.value    = bopName;
      hidFactory.value = factoryGidVal;
      preview.textContent = `${bopName}${stageVal ? " · " + stageVal : ""}  ·  ${tag}` + (famGidVal ? '（族内递增）' : '（新族首版）');
      preview.style.color = 'var(--blue,#89b4fa)';
    };
    if (projSel) {
      projSel.addEventListener('change', refreshFamilyByProject);
      projSel.addEventListener('change', refreshStageOptions);
      projSel.addEventListener('change', updatePreview);
    }
    stageSel.addEventListener('change', updatePreview);
    refreshFamilyByProject();
    refreshStageOptions();

    const createBtn = document.createElement('button');
    createBtn.className   = 'lv-lc-confirm-btn';
    createBtn.textContent  = submitLabel;
    createBtn.style.marginTop = '0';
    createBtn.addEventListener('click', async () => {
      const projGid   = projSel?.value || '';
      refreshFamilyByProject();
      const famGid    = famSel.value || null;
      const facGid    = hidFactory.value.trim() || null;
      const dataStage = stageSel.value || null;
      const srcGid    = getSourceGid();

      if (!projGid)   { this._toast('请先选择所属项目', 'warn'); return; }
      if (!dataStage) { this._toast('请选择数据阶段', 'warn'); return; }

      // 临时禁用，实时获取最新版本列表重新计算版本号
      createBtn.disabled    = true;
      createBtn.textContent = '检测版本号…';
      let tag, bopName, effectiveFamGid;
      try {
        const freshRes = await this._cf('/api/bop/versions?include_archived=true');
        const freshVers = freshRes.data || [];
        this._allVersionsCache = freshVers;   // 更新缓存

        let projName;
        const selOpt = projSel?.options[projSel.selectedIndex];
        projName = selOpt?.dataset.projectName || '';
        bopName = projName ? projName : '';
        if (!bopName) { this._toast('版本名称获取失败，请重选项目', 'warn'); createBtn.disabled = false; createBtn.textContent = submitLabel; return; }

        // 用 freshVers 重新判定版本族（覆盖提交时可能过期的闭包 famGid）
        const freshMatch = freshVers.find(v =>
          v.version_type !== 'template' && !v.archived_at && (v.bop_name || '') === projName
        );
        const freshFamGid = freshMatch ? (freshMatch.version_family_gid || freshMatch.gid) : null;
        if (freshFamGid !== famGid) {
          famSel.value = freshFamGid || '';
        }
        effectiveFamGid = freshFamGid;

        let nextNum = 1;
        if (effectiveFamGid) {
          const maxN = freshVers
            .filter(v => (v.version_family_gid || v.gid) === effectiveFamGid && !v.archived_at)
            .reduce((m, v) => {
              const n = parseInt((v.version_tag || '').replace(/^v/i, ''));
              return isNaN(n) ? m : Math.max(m, n);
            }, 0);
          nextNum = maxN + 1;
        }
        tag = `v${nextNum}`;
        // 更新预览显示
        const preview = previewBox.querySelector('#lc-form-preview');
        if (preview) {
          preview.textContent = `${bopName}${dataStage ? " · " + dataStage : ""}  ·  ${tag}` + (effectiveFamGid ? '（族内递增）' : '（新族首版）');
          preview.style.color = 'var(--blue,#89b4fa)';
        }
      } catch (e) {
        this._toast('版本号检测失败: ' + e.message, 'error');
        createBtn.disabled = false; createBtn.textContent = submitLabel;
        return;
      }
      createBtn.textContent = '创建中…';
      try {
        let newGid;
        if (srcGid) {
          // Fork from source (template or existing version)
          const extraParams = typeof getExtraForkParams === 'function'
            ? getExtraForkParams() : {};
          const res = await this._cf(`/api/bop/versions/${srcGid}/fork`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              target_version_tag:        tag,
              target_bop_name:           bopName,
              target_version_family_gid: effectiveFamGid,
              version_type:              'working',
              ...extraParams,
            }),
          });
          newGid = res.data?.gid || res.gid;
        } else {
          // Create blank version
          const res = await this._cf('/api/bop/versions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              version_tag: tag, bop_name: bopName,
              version_family_gid: effectiveFamGid,
              project_gid: projGid, factory_gid: facGid,
              data_stage: dataStage,
            }),
          });
          newGid = res.data?.gid || res.gid;
        }

        // 保存路线到新版本
        if (newGid) {
          await this._cf(`/api/bop/versions/${newGid}/lifecycle/init-state`, {
            method: 'PATCH', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              route: route,
              checklist: { version_created: true, ...extraChecklist },
            }),
          });
        }

        this._toast(`版本「${bopName} / ${tag}」已创建`, 'ok');
        // 清空版本缓存，强制下次重新获取（防止版本号重复）
        this._allVersionsCache = null;
        // 刷新版本选择器并选中新版本
        if (typeof _verMgr !== 'undefined' && _verMgr?.loadVersions) {
          await _verMgr.loadVersions();
          if (newGid && _verMgr.selectVersion) _verMgr.selectVersion(newGid, tag);
          if (route === 'tc_import' && _verMgr.openImportTcModal) {
            _verMgr.openImportTcModal();
          }
        }
        if (this._actionEl) this._actionEl.innerHTML = '';
      } catch (e) {
        this._toast('创建失败: ' + e.message, 'error');
        createBtn.disabled    = false;
        createBtn.textContent = submitLabel;
      }
    });
    container.appendChild(createBtn);
  }

  // ── 缓存确保加载 ──────────────────────────────────────────────────────────

  async _ensureCaches() {
    const [projRes, facRes, verRes] = await Promise.allSettled([
      this._projectsCache ? null : this._cf('/api/projects?limit=200'),
      this._factoriesCache ? null : this._cf('/api/bop/factories'),
      this._allVersionsCache ? null : this._cf('/api/bop/versions?include_archived=true'),
    ]);
    if (!this._projectsCache && projRes.status === 'fulfilled' && projRes.value) {
      this._projectsCache = (projRes.value.data || []).filter(
        p => !p.is_deleted && p.project_type !== 'gbop'
      );
    }
    if (!this._factoriesCache && facRes.status === 'fulfilled' && facRes.value) {
      this._factoriesCache = facRes.value.data || [];
    }
    if (!this._allVersionsCache && verRes.status === 'fulfilled' && verRes.value) {
      this._allVersionsCache = verRes.value.data || [];
    }
    if (!this._projectsCache)    this._projectsCache    = [];
    if (!this._factoriesCache)   this._factoriesCache   = [];
    if (!this._allVersionsCache) this._allVersionsCache = [];
  }

  _makeActionBtn(label, onClick) {
    const btn = document.createElement('button');
    btn.className = 'lv-lc-jump-btn';
    btn.style.fontSize = '10px';
    btn.innerHTML =
      `${label} <span style="margin-left:auto;color:var(--overlay0,#6c7086)">→</span>`;
    btn.addEventListener('click', onClick);
    return btn;
  }

  _makeMarkDoneBtn(stepKey) {
    const btn = document.createElement('button');
    btn.style.cssText =
      'padding:3px 8px;font-size:9px;background:transparent;' +
      'border:1px solid var(--green,#a6e3a1);border-radius:3px;' +
      'color:var(--green,#a6e3a1);cursor:pointer;align-self:flex-start';
    btn.textContent = '标记此步骤完成';
    btn.addEventListener('click', () => this._markStepDone(stepKey));
    return btn;
  }

  async _markStepDone(stepKey) {
    await this._saveInitState({ checklist: { [stepKey]: true } });
  }

  async _undoStep(stepKey) {
    const _STEP_WARN = {
      lines_added:     '将软删除所有线体条目及其子节点（工位/工序）和关联链接',
      stations_added:  '将软删除所有工位条目及其子节点和关联链接',
      processes_added: '将软删除所有工序条目及其关联链接',
      vpps_imported:   '将软删除该 BOP 版本中所有 PBOM 零件绑定链接（PBOM 数据本身保留）',
    };

    const warn = _STEP_WARN[stepKey];
    const msg  = warn
      ? `确认撤销此步骤？\n\n⚠️ ${warn}\n\n此操作不可直接恢复。`
      : '确认撤销此步骤？';
    if (!confirm(msg)) return;

    // PBOM 导入步骤：获取关联的 PBOM 版本 GID
    let pbomVersionGid = '';
    if (stepKey === 'vpps_imported') {
      try {
        const saved = JSON.parse(localStorage.getItem(`lc:pbom_import:${this._versionGid}`) || 'null');
        pbomVersionGid = saved?.gid || '';
      } catch (_) {}
      // 同时清除 localStorage 缓存
      localStorage.removeItem(`lc:pbom_import:${this._versionGid || 'unknown'}`);
    }

    try {
      const res = await this._cf(
        `/api/bop/versions/${this._versionGid}/lifecycle/undo-step`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ step_key: stepKey, pbom_version_gid: pbomVersionGid || null }),
        }
      );
      const d = res?.deleted_entries || 0;
      const l = res?.deleted_links   || 0;
      const detail = (d || l) ? `（条目 ${d} 条，链接 ${l} 条已软删）` : '';
      this._toast(`步骤已撤销${detail}`, 'ok');
      await this._load();
    } catch (e) {
      this._toast('撤销失败: ' + e.message, 'error');
    }
  }

  async _saveInitState(updates) {
    try {
      const body = {};
      if ('route' in updates)     body.route     = updates.route;
      if ('checklist' in updates) body.checklist  = updates.checklist;
      const res = await this._cf(
        `/api/bop/versions/${this._versionGid}/lifecycle/init-state`,
        { method: 'PATCH', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body) }
      );
      // 更新本地缓存
      if (this._data) this._data.lifecycle_state = res.lifecycle_state;
      this._render();
    } catch (e) {
      this._toast('保存失败: ' + e.message, 'error');
    }
  }

  // ── 完善细节卡片 ──────────────────────────────────────────────────────────

  // ── 共用"持续完善"面板（refine 和 publish_cycle 都使用）─────────────────────

  _renderRefineCard() {
    return this._renderContinuousRefineUI('refine');
  }

  _renderContinuousRefineUI(phase) {
    const frag = document.createDocumentFragment();
    const overall = this._data.stats || {};
    const currentPhase = this._data?.lifecycle_phase;

    // ── data_stage 徽标 + 上次切片信息 ──────────────────────────────────────
    const ds = this._data?.data_stage || '';
    const headerEl = document.createElement('div');
    headerEl.style.cssText =
      'display:flex;align-items:center;gap:8px;margin-bottom:8px;' +
      'padding:6px 8px;background:var(--base,#1e1e2e);border-radius:4px';
    headerEl.innerHTML =
      `<span style="font-size:11px;font-weight:600;padding:2px 8px;border-radius:3px;` +
      `background:rgba(137,180,250,.15);color:var(--blue,#89b4fa)">${ds || '未设置'}</span>` +
      `<span style="font-size:10px;color:var(--subtext0,#a6adc8)">当前数据阶段</span>`;

    // 显示上次切片时间（从 history 里找最新的 freeze 记录）
    const snapshots = (this._data?.history || []).filter(h => h.phase === 'snapshot' || h.confirmed_at);
    if (snapshots.length) {
      const last = snapshots[snapshots.length - 1];
      const ts = (last.confirmed_at || last.entered_at || '').slice(0, 10);
      headerEl.innerHTML +=
        `<span style="margin-left:auto;font-size:10px;color:var(--overlay0,#6c7086)">上次切片：${ts}</span>`;
    }
    frag.appendChild(headerEl);

    // ── PBOM 差异工作队列（可折叠）──────────────────────────────────────────
    const diffPending = this._data?.pbom_diff_queue_pending || 0;
    const diffBlock = document.createElement('div');
    diffBlock.style.cssText =
      'border:1px solid var(--surface1,#45475a);border-radius:4px;margin-bottom:8px;overflow:hidden';

    const diffHdr = document.createElement('div');
    diffHdr.style.cssText =
      'display:flex;align-items:center;gap:6px;padding:5px 8px;cursor:pointer;' +
      'background:var(--base,#1e1e2e);font-size:10px;';
    diffHdr.innerHTML =
      `<span style="flex:1;font-weight:600;color:var(--text,#cdd6f4)">PBOM 差异工作队列</span>` +
      (diffPending > 0
        ? `<span style="padding:1px 6px;border-radius:10px;background:rgba(249,226,175,.15);` +
          `color:var(--yellow,#f9e2af)">${diffPending} 待处理</span>`
        : `<span style="color:var(--overlay0,#6c7086)">无待处理</span>`);

    const diffBody = document.createElement('div');
    diffBody.style.cssText = 'padding:6px 8px;display:none';
    diffBody.innerHTML =
      `<div style="font-size:10px;color:var(--subtext0,#a6adc8);margin-bottom:6px">` +
      `选择新 PBOM 版本，系统对比后生成差异件待处理列表。</div>`;

    // 生成差异队列的触发器
    const diffTrigger = document.createElement('div');
    diffTrigger.style.cssText = 'display:flex;gap:6px;align-items:center;margin-bottom:6px';
    const pbomSel = document.createElement('select');
    pbomSel.style.cssText =
      'flex:1;padding:3px 6px;font-size:11px;background:var(--base,#1e1e2e);' +
      'color:var(--text,#cdd6f4);border:1px solid var(--surface2,#585b70);border-radius:4px';
    pbomSel.innerHTML = '<option value="">— 选择新 PBOM 版本 —</option>';
    const genBtn = document.createElement('button');
    genBtn.style.cssText =
      'padding:3px 8px;font-size:11px;background:transparent;border:1px solid var(--surface2,#585b70);' +
      'border-radius:4px;color:var(--text,#cdd6f4);cursor:pointer;white-space:nowrap';
    genBtn.textContent = '生成差异队列';
    diffTrigger.appendChild(pbomSel);
    diffTrigger.appendChild(genBtn);
    diffBody.appendChild(diffTrigger);

    // 加载 PBOM 版本列表
    const cf = window.parent?._cloudFetch || window._cloudFetch;
    if (cf) {
      cf('/api/ebom/snapshots').then(res => {
        (res?.data || []).forEach(v => {
          const opt = document.createElement('option');
          opt.value = v.gid;
          opt.textContent = v.name || v.version_tag || v.gid.slice(-8);
          pbomSel.appendChild(opt);
        });
      }).catch(() => {});

      genBtn.addEventListener('click', async () => {
        const targetGid = pbomSel.value;
        if (!targetGid) { this._toast('请选择 PBOM 版本', 'warn'); return; }
        genBtn.disabled = true; genBtn.textContent = '生成中…';
        try {
          const baseMeta = this._data?.pbom_match?.pbom_version_gid || '';
          await cf(`/api/bop/versions/${this._versionGid}/pbom-diff-queue`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pbom_base_gid: baseMeta || null, pbom_target_gid: targetGid }),
          });
          this._toast('差异队列已生成', 'ok');
          await this._load();
        } catch (e) {
          this._toast('生成失败: ' + e.message, 'error');
          genBtn.disabled = false; genBtn.textContent = '生成差异队列';
        }
      });
    }

    // 显示现有差异队列列表（仅 pending）
    if (diffPending > 0 && cf) {
      const listEl = document.createElement('div');
      listEl.innerHTML = '<div style="font-size:10px;color:var(--subtext0,#a6adc8)">加载中…</div>';
      diffBody.appendChild(listEl);
      cf(`/api/bop/versions/${this._versionGid}/pbom-diff-queue?status=pending`).then(res => {
        const items = res?.data || [];
        if (!items.length) { listEl.innerHTML = ''; return; }
        listEl.innerHTML = items.slice(0, 10).map(it => {
          const typeColor = it.diff_type === 'added' ? 'var(--green,#a6e3a1)' : 'var(--yellow,#f9e2af)';
          return `<div style="display:flex;gap:6px;padding:3px 0;border-bottom:1px solid var(--surface1,#45475a);font-size:11px">
            <span style="font-family:monospace;color:var(--blue,#89b4fa);flex:0 0 120px;overflow:hidden;text-overflow:ellipsis">${it.vpps || ''}</span>
            <span style="flex:1;color:var(--text,#cdd6f4);overflow:hidden;text-overflow:ellipsis">${it.vpps_desc || ''}</span>
            <span style="color:${typeColor};flex-shrink:0">${it.diff_type === 'added' ? '新增' : '变更'}</span>
          </div>`;
        }).join('') + (items.length > 10 ? `<div style="font-size:10px;color:var(--overlay0,#6c7086);padding-top:4px">还有 ${items.length - 10} 条…</div>` : '');
      }).catch(() => { listEl.innerHTML = ''; });
    }

    let diffOpen = diffPending > 0;
    diffBody.style.display = diffOpen ? 'block' : 'none';
    diffHdr.addEventListener('click', () => {
      diffOpen = !diffOpen;
      diffBody.style.display = diffOpen ? 'block' : 'none';
    });
    diffBlock.appendChild(diffHdr);
    diffBlock.appendChild(diffBody);
    frag.appendChild(diffBlock);

    // ── PBOM 继承状态 ────────────────────────────────────────────────────────
    const vc = this._data.pbom_vpps_check || {};
    const pm = this._data.pbom_match      || {};
    if (vc.total > 0 || pm.pbom_version_gid) {
      const pbomBlock = document.createElement('div');
      pbomBlock.style.cssText =
        'margin-bottom:8px;padding:6px 8px;border-radius:4px;' +
        'background:var(--base,#1e1e2e);border-left:2px solid var(--blue,#89b4fa)';
      const nokColor = (vc.nok || 0) > 0 ? 'var(--red,#f38ba8)' : 'var(--green,#a6e3a1)';
      pbomBlock.innerHTML =
        `<div style="font-size:10px;color:var(--subtext0,#a6adc8);margin-bottom:4px">PBOM 核对状态</div>` +
        (vc.total > 0
          ? `<div class="lv-lc-progress-row"><span>VPPS NOK</span>` +
            `<span style="color:${nokColor}">${vc.nok} / ${vc.total} 总</span></div>`
          : '') +
        (vc.ignored > 0
          ? `<div class="lv-lc-progress-row"><span>VPPS 已忽略</span>` +
            `<span style="color:var(--yellow,#f9e2af)">${vc.ignored}</span></div>`
          : '') +
        ((pm.unlinked_ignored || 0) > 0
          ? `<div class="lv-lc-progress-row"><span>未关联已忽略</span>` +
            `<span style="color:var(--yellow,#f9e2af)">${pm.unlinked_ignored}</span></div>`
          : '');
      frag.appendChild(pbomBlock);
    }

    // ── 整体进度条 ────────────────────────────────────────────────────────────
    const craftPct  = this._craftPct(overall);
    const projPct   = this._projPct(overall);
    const delPct    = this._deliverablePct(overall);
    const progBlock = document.createElement('div');
    progBlock.style.cssText = 'margin-bottom:8px;padding-bottom:8px;border-bottom:1px solid var(--surface1,#45475a)';
    progBlock.innerHTML =
      `<div class="lv-lc-progress-row"><span>工艺准备</span><span style="color:var(--blue,#89b4fa)">${craftPct}%</span></div>` +
      `<div class="lv-lc-bar"><div class="lv-lc-bar-fill craft" style="width:${craftPct}%"></div></div>` +
      `<div class="lv-lc-progress-row"><span>工艺交付物</span><span style="color:var(--peach,#fab387)">${delPct}%</span></div>` +
      `<div class="lv-lc-bar"><div class="lv-lc-bar-fill" style="width:${delPct}%;background:var(--peach,#fab387)"></div></div>` +
      `<div class="lv-lc-progress-row"><span>项目准备</span><span style="color:var(--mauve,#cba6f7)">${projPct}%</span></div>` +
      `<div class="lv-lc-bar"><div class="lv-lc-bar-fill project" style="width:${projPct}%"></div></div>`;
    frag.appendChild(progBlock);

    frag.appendChild(this._renderLineSelector());
    const stats = this._getActiveStats();

    // 工艺准备（8项）
    const cl = document.createElement('div');
    cl.className = 'lv-lc-section-label';
    cl.textContent = '工艺准备';
    frag.appendChild(cl);
    [
      { key: 'nok_vpps',          label: 'PBOM vpps 核对',     type: 'nok',       val: () => stats.nok_vpps || 0 },
      { key: 'nok_unbound_parts', label: '未绑车型工序零件',   type: 'nok',       val: () => stats.nok_unbound_parts || 0 },
      { key: 'nok_unbound_ops',   label: '未绑工位车型工序',   type: 'nokorange', val: () => stats.nok_unbound_ops || 0 },
      { key: 'tools',     label: '工具需求绑定', type: 'ratio', val: () => `${stats.tools_bound||0}/${stats.tools_total||0}` },
      { key: 'fixtures',  label: '工装需求绑定', type: 'ratio', val: () => `${stats.fixtures_bound||0}/${stats.fixtures_total||0}` },
      { key: 'equipment', label: '设备需求绑定', type: 'ratio', val: () => `${stats.equipment_bound||0}/${stats.equipment_total||0}` },
      { key: 'coverage',  label: '产品覆盖关系校核', type: 'bool', val: () => stats.coverage_ok },
      { key: 'balance',   label: '工艺平衡',     type: 'bool', val: () => stats.balance_ok },
    ].forEach(item => frag.appendChild(this._renderSubItem(item)));

    // 工艺交付物（1项，新增）
    const dl = document.createElement('div');
    dl.className = 'lv-lc-section-label';
    dl.style.marginTop = '4px';
    dl.textContent = '工艺交付物';
    frag.appendChild(dl);
    frag.appendChild(this._renderSubItem({
      key: 'deliverable', label: '工艺卡/控制计划/人机姿态',
      type: 'ratio',
      val: () => `${stats.deliverable_bound||0}/${stats.deliverable_total||0}`,
    }));

    // 项目准备（3项）
    const pl = document.createElement('div');
    pl.className = 'lv-lc-section-label';
    pl.style.marginTop = '4px';
    pl.textContent = '项目准备';
    frag.appendChild(pl);
    [
      { key: 'tasks',  label: '任务完成度',    type: 'ratio',  val: () => `${stats.tasks_done||0}/${stats.tasks_total||0}` },
      { key: 'issues', label: '开放问题',       type: 'issues', val: () => stats.issues_open || 0 },
      { key: 'rules',  label: '规则警告/阻碍',  type: 'rules',  val: () => ({ warn: stats.rules_warn||0, block: stats.rules_block||0 }) },
    ].forEach(item => frag.appendChild(this._renderSubItem(item)));

    // refine 阶段：确认推进到发布循环
    if (phase === 'refine') {
      this._appendConfirmBtn(frag, 'refine');
    }

    return frag;
  }

  _craftPct(s) {
    if (!s) return 0;
    const done = [
      s.nok_vpps === 0,
      s.nok_unbound_parts === 0,
      s.nok_unbound_ops === 0,
      !s.tools_total  || s.tools_bound      >= s.tools_total,
      !s.fixtures_total || s.fixtures_bound  >= s.fixtures_total,
      !s.equipment_total || s.equipment_bound >= s.equipment_total,
      s.coverage_ok,
      s.balance_ok,
    ].filter(Boolean).length;
    return Math.round(done / 8 * 100);
  }

  _deliverablePct(s) {
    if (!s || !s.deliverable_total) return 0;
    return Math.round((s.deliverable_bound || 0) / s.deliverable_total * 100);
  }

  _projPct(s) {
    if (!s) return 0;
    const done = [
      !s.tasks_total || s.tasks_done >= s.tasks_total,
      s.issues_open === 0,
      s.rules_block === 0 && s.rules_warn === 0,
    ].filter(Boolean).length;
    return Math.round(done / 3 * 100);
  }

  _renderSubItem(item) {
    const el = document.createElement('div');
    el.className = 'lv-lc-item' + (this._selectedItem === item.key ? ' selected' : '');

    let dotClass  = 'gray';
    let badgeHtml = '';
    const v = item.val();

    if (item.type === 'nok') {
      dotClass  = v > 0 ? 'red' : 'green';
      badgeHtml = v > 0
        ? `<span class="lv-lc-badge nok">NOK ${v}</span>`
        : '<span class="lv-lc-badge num">✓</span>';
    } else if (item.type === 'nokorange') {
      dotClass  = v > 0 ? 'orange' : 'green';
      badgeHtml = v > 0
        ? `<span class="lv-lc-badge warn">NOK ${v}</span>`
        : '<span class="lv-lc-badge num">✓</span>';
    } else if (item.type === 'ratio') {
      const [b, t] = String(v).split('/').map(Number);
      const ok = t === 0 || b >= t;
      dotClass  = ok ? 'green' : 'orange';
      badgeHtml = `<span class="lv-lc-badge num">${v}</span>`;
    } else if (item.type === 'bool') {
      dotClass  = v ? 'green' : 'orange';
      badgeHtml = v
        ? '<span class="lv-lc-badge num">✓</span>'
        : '<span class="lv-lc-badge warn">NOK</span>';
    } else if (item.type === 'issues') {
      dotClass  = v > 0 ? 'red' : 'green';
      badgeHtml = v > 0
        ? `<span class="lv-lc-badge nok">${v} 开放</span>`
        : '<span class="lv-lc-badge num">✓</span>';
    } else if (item.type === 'rules') {
      dotClass  = v.block > 0 ? 'red' : v.warn > 0 ? 'orange' : 'green';
      badgeHtml = `<span class="lv-lc-badge ${v.block > 0 ? 'nok' : 'warn'}">⚠${v.warn} ✕${v.block}</span>`;
    }

    el.innerHTML =
      `<div class="lv-lc-dot ${dotClass}"></div>` +
      `<span class="lv-lc-item-label">${item.label}</span>` +
      badgeHtml;

    el.addEventListener('click', () => {
      this._selectedItem = item.key;
      this._render();
      this._renderActionZone(item);
    });
    return el;
  }

  // ── 线体选择器 ────────────────────────────────────────────────────────────


  _renderLineSelector() {
    const wrap = document.createElement('div');
    wrap.className = 'lv-lc-line-sel';

    const lbl = document.createElement('span');
    lbl.style.cssText = 'font-size:9px;color:var(--overlay0,#6c7086);flex-shrink:0';
    lbl.textContent = '视角：';
    wrap.appendChild(lbl);

    const sel = document.createElement('select');
    const optAll = document.createElement('option');
    optAll.value = '';
    optAll.textContent = '整体（全部线体）';
    if (!this._selectedLine) optAll.selected = true;
    sel.appendChild(optAll);

    (this._data?.lines || []).forEach(line => {
      const opt = document.createElement('option');
      opt.value = line.gid;
      opt.textContent = line.title || line.gid.slice(-6);
      if (this._selectedLine === line.gid) opt.selected = true;
      sel.appendChild(opt);
    });

    sel.addEventListener('change', () => {
      this._selectedLine = sel.value;
      this._render();
      this._renderSideHistoryPanel();
    });
    wrap.appendChild(sel);
    return wrap;
  }

  _resolveCurrentLineGid() {
    return this._selectedLine || '';
  }

  _renderSideHistoryPanel() {
    const host = document.getElementById('lvActionHistoryBody');
    if (!host) return;
    host.innerHTML = '';

    const lineGid = this._selectedLine || '';
    if (!lineGid) {
      const hint = document.createElement('div');
      hint.className = 'lv-cpanel-empty';
      hint.textContent = '请选择线体或节点';
      host.appendChild(hint);
      return;
    }

    const actions = document.createElement('div');
    actions.className = 'lv-lc-history-actions';

    const undoBtn = document.createElement('button');
    undoBtn.className = 'lv-lc-jump-btn';
    undoBtn.textContent = '↶ 撤销最近一步';
    undoBtn.addEventListener('click', () => this._doUndo());

    const redoBtn = document.createElement('button');
    redoBtn.className = 'lv-lc-jump-btn';
    redoBtn.textContent = '↷ 重做最近一步';
    redoBtn.addEventListener('click', () => this._doRedo());

    actions.appendChild(undoBtn);
    actions.appendChild(redoBtn);
    host.appendChild(actions);

    const logEl = document.createElement('div');
    logEl.innerHTML = '<div style="font-size:10px;color:var(--subtext0,#a6adc8)">加载中…</div>';
    host.appendChild(logEl);
    this._loadUpdateLog(lineGid, logEl);
  }

  _getActiveStats() {
    if (!this._selectedLine) return this._data?.stats || {};
    return (this._data?.line_stats || []).find(s => s.line_gid === this._selectedLine) || {};
  }

  // ── 发布/更新卡片（两 Tab：当前完善 + 切片历史）────────────────────────────

  _renderPublishCard() {
    const frag = document.createDocumentFragment();

    const pillRow = document.createElement('div');
    pillRow.className = 'lv-lc-pill-row';
    [['refine','当前完善'], ['snapshots','切片历史'], ['update','更新日志']].forEach(([v, label]) => {
      const pill = document.createElement('div');
      pill.className = 'lv-lc-pill' + (this._pillView === v ? ' active' : '');
      pill.textContent = label;
      pill.addEventListener('click', () => { this._pillView = v; this._render(); });
      pillRow.appendChild(pill);
    });
    frag.appendChild(pillRow);

    if (this._pillView === 'refine' || !this._pillView || this._pillView === 'publish') {
      // 完善面板（含冻结切片按钮）
      frag.appendChild(this._renderContinuousRefineUI('publish_cycle'));
      frag.appendChild(this._renderFreezeSnapshotBtn());
    } else if (this._pillView === 'snapshots') {
      frag.appendChild(this._renderSnapshotHistory());
    } else {
      frag.appendChild(this._renderUpdateLog());
    }
    return frag;
  }

  _renderFreezeSnapshotBtn() {
    const wrap = document.createElement('div');
    wrap.style.cssText = 'margin-top:8px;border-top:1px solid var(--surface1,#45475a);padding-top:8px';

    const _DATA_STAGES = ['Pre-TG0','TG0','TG1','PreTG2','TG2','EP1','EP2','PPV','PP','P','SOP'];
    const isActive = this._data?.lifecycle_phase !== 'archived';
    if (!isActive) return wrap;

    const lbl = document.createElement('div');
    lbl.style.cssText = 'font-size:10px;color:var(--subtext0,#a6adc8);margin-bottom:6px';
    lbl.textContent = '冻结切片（fork 副本为 baseline，活动版本继续）';
    wrap.appendChild(lbl);

    // 目标 data_stage 选择器
    const stageSel = document.createElement('select');
    stageSel.style.cssText =
      'width:100%;padding:4px 6px;font-size:11px;background:var(--base,#1e1e2e);' +
      'color:var(--text,#cdd6f4);border:1px solid var(--surface2,#585b70);border-radius:4px;margin-bottom:6px';
    stageSel.innerHTML = '<option value="">— 选择本次目标数据阶段 —</option>' +
      _DATA_STAGES.map(s => `<option value="${s}">${s}</option>`).join('');
    wrap.appendChild(stageSel);

    // 变更说明
    const noteInp = document.createElement('input');
    noteInp.type = 'text'; noteInp.placeholder = '变更说明（可选）';
    noteInp.style.cssText =
      'width:100%;padding:4px 6px;font-size:11px;background:var(--base,#1e1e2e);' +
      'color:var(--text,#cdd6f4);border:1px solid var(--surface2,#585b70);border-radius:4px;margin-bottom:6px';
    wrap.appendChild(noteInp);

    // 直接发布为 M 选项
    const mRow = document.createElement('label');
    mRow.style.cssText = 'display:flex;align-items:center;gap:6px;font-size:11px;color:var(--subtext0,#a6adc8);margin-bottom:8px;cursor:pointer';
    const mChk = document.createElement('input'); mChk.type = 'checkbox';
    mRow.appendChild(mChk);
    mRow.appendChild(document.createTextNode('直接发布为 M'));
    wrap.appendChild(mRow);

    const btn = document.createElement('button');
    btn.className = 'lv-lc-confirm-btn';
    btn.textContent = '冻结切片';
    btn.addEventListener('click', async () => {
      if (!stageSel.value) { this._toast('请选择目标数据阶段', 'warn'); return; }
      if (!confirm(`确认冻结切片？活动版本将继续，副本变为 ${mChk.checked ? 'M' : 'baseline'}。`)) return;
      btn.disabled = true; btn.textContent = '冻结中…';
      try {
        const cf = window.parent?._cloudFetch || window._cloudFetch;
        await cf(`/api/bop/versions/${this._versionGid}/freeze-snapshot`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            target_data_stage: stageSel.value,
            change_note: noteInp.value || null,
            promote_to_m: mChk.checked,
          }),
        });
        this._toast(`切片已完成，data_stage 推进到 ${stageSel.value}`, 'ok');
        await this._load();
      } catch (e) {
        this._toast('冻结失败: ' + e.message, 'error');
        btn.disabled = false; btn.textContent = '冻结切片';
      }
    });
    wrap.appendChild(btn);
    return wrap;
  }

  _renderSnapshotHistory() {
    const frag = document.createDocumentFragment();
    const lbl = document.createElement('div');
    lbl.className = 'lv-lc-section-label';
    lbl.textContent = '切片历史';
    frag.appendChild(lbl);

    const listEl = document.createElement('div');
    listEl.innerHTML = '<div style="font-size:10px;color:var(--subtext0,#a6adc8)">加载中…</div>';
    frag.appendChild(listEl);
    this._loadSnapshotHistory(listEl);
    return frag;
  }

  async _loadSnapshotHistory(container) {
    try {
      const cf = window.parent?._cloudFetch || window._cloudFetch;
      const res = await cf('/api/bop/versions?include_archived=true');
      const allVers = res?.data || [];
      const curVer  = allVers.find(v => v.gid === this._versionGid);
      const famGid  = curVer?.version_family_gid || this._versionGid;
      const snapshots = allVers
        .filter(v => (v.version_family_gid || v.gid) === famGid && v.status !== 'active')
        .sort((a, b) => (b.frozen_at || b.created_at || '').localeCompare(a.frozen_at || a.created_at || ''));

      container.innerHTML = '';
      if (!snapshots.length) {
        container.innerHTML = '<div style="font-size:10px;color:var(--subtext0,#a6adc8)">暂无切片记录</div>';
        return;
      }
      snapshots.forEach(v => {
        const statusColor = { baseline: '#e8a22a', M: '#74b0ff', archived: '#9ba8d0' }[v.status] || '#9ba8d0';
        const item = document.createElement('div');
        item.className = 'lv-lc-ver-item';
        item.innerHTML =
          `<div class="lv-lc-ver-row">` +
          `<span style="font-weight:600;font-size:11px;color:var(--text,#cdd6f4)">${v.version_tag}</span>` +
          (v.data_stage ? `<span style="font-size:11px;padding:1px 5px;border-radius:3px;background:rgba(137,180,250,.15);color:var(--blue,#89b4fa);margin-left:4px">${v.data_stage}</span>` : '') +
          `<span style="font-size:11px;padding:1px 5px;border-radius:3px;background:${statusColor}28;color:${statusColor};margin-left:4px">${v.status}</span>` +
          `<span style="font-size:11px;color:var(--subtext0,#a6adc8);margin-left:auto">${(v.frozen_at||v.created_at||'').slice(0,10)}</span>` +
          `</div>` +
          (v.change_note ? `<div style="font-size:11px;color:var(--subtext0,#a6adc8);margin-top:2px">${v.change_note}</div>` : '');
        container.appendChild(item);
      });
    } catch (e) {
      container.innerHTML = `<div style="font-size:10px;color:#f38ba8">加载失败: ${e.message}</div>`;
    }
  }

  _renderPublishList() {
    const frag = document.createDocumentFragment();
    const lbl = document.createElement('div');
    lbl.className = 'lv-lc-section-label';
    lbl.textContent = '已发布版本';
    frag.appendChild(lbl);

    const listEl = document.createElement('div');
    listEl.innerHTML = '<div style="font-size:10px;color:var(--subtext0,#a6adc8)">加载中…</div>';
    frag.appendChild(listEl);
    this._loadPublishedVersions(listEl);

    const currentPhase  = this._data?.lifecycle_phase;
    const isPublishPhase = currentPhase === 'publish_cycle';
    const btn = document.createElement('button');
    btn.className   = 'lv-lc-confirm-btn';
    btn.textContent = isPublishPhase ? '发布当前版本' : '🔒 请先完成前置阶段';
    btn.disabled    = !isPublishPhase;
    if (!isPublishPhase) btn.style.opacity = '0.45';
    btn.addEventListener('click', () => isPublishPhase && this._publishCurrentVersion());
    frag.appendChild(btn);
    return frag;
  }

  async _loadPublishedVersions(container) {
    try {
      const res = await this._cf('/api/bop/versions?include_archived=true');
      const allVers = res.data || [];
      const curVer  = allVers.find(v => v.gid === this._versionGid);
      const famGid  = curVer?.version_family_gid || this._versionGid;
      const published = allVers
        .filter(v => (v.version_family_gid || v.gid) === famGid)
        .sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''));

      container.innerHTML = '';
      if (!published.length) {
        container.innerHTML =
          '<div style="font-size:10px;color:var(--subtext0,#a6adc8)">暂无发布版本</div>';
        return;
      }
      published.forEach(v => {
        const isActive = v.status === 'active';
        const isCur    = v.gid === this._versionGid;
        const statusColor = {
          active:'#89b4fa', M:'#74b0ff', baseline:'#e8a22a', archived:'#9ba8d0'
        }[v.status] || '#9ba8d0';
        const item = document.createElement('div');
        item.className = 'lv-lc-ver-item' + (isActive ? ' active-ver' : '');
        item.innerHTML =
          `<div class="lv-lc-ver-row">` +
          `<span style="font-weight:600;font-size:11px;color:${isCur ? '#cdd6f4' : '#bac2de'}">${v.version_tag}</span>` +
          `<span style="font-size:11px;padding:1px 5px;border-radius:3px;background:${statusColor}28;color:${statusColor};margin-left:4px">${v.status}</span>` +
          `<span style="font-size:11px;color:var(--subtext0,#a6adc8);margin-left:auto">${(v.published_at||v.created_at||'').slice(0,10)}</span>` +
          `</div>` +
          (v.change_note ? `<div style="font-size:11px;color:var(--subtext0,#a6adc8);margin-top:2px">${v.change_note}</div>` : '');
        container.appendChild(item);
      });
    } catch (e) {
      container.innerHTML = `<div style="font-size:10px;color:#f38ba8">加载失败: ${e.message}</div>`;
    }
  }

  async _publishCurrentVersion() {
    if (!confirm('确认冻结并发布当前版本？')) return;
    try {
      await this._cf(`/api/bop/versions/${this._versionGid}/freeze`,  { method: 'POST' });
      await this._cf(`/api/bop/versions/${this._versionGid}/publish`, { method: 'POST' });
      this._toast('版本已发布（M 状态）', 'ok');
      await this._load();
    } catch (e) {
      this._toast('发布失败: ' + e.message, 'error');
    }
  }

  _renderUpdateLog() {
    const frag  = document.createDocumentFragment();
    const lineGid = this._selectedLine;

    if (!lineGid) {
      const hint = document.createElement('div');
      hint.style.cssText = 'font-size:10px;color:var(--subtext0,#a6adc8);padding:6px 0';
      hint.textContent = '请先在上方选择一条线体';
      frag.appendChild(hint);
      return frag;
    }

    const logEl = document.createElement('div');
    logEl.innerHTML = '<div style="font-size:10px;color:var(--subtext0,#a6adc8)">加载中…</div>';
    frag.appendChild(logEl);
    this._loadUpdateLog(lineGid, logEl);

    const ckptBtn = document.createElement('button');
    ckptBtn.className = 'lv-lc-jump-btn';
    ckptBtn.style.marginTop = '8px';
    ckptBtn.innerHTML =
      '📸 打快照（Checkpoint）<span style="margin-left:auto;color:var(--overlay0,#6c7086)">+</span>';
    ckptBtn.addEventListener('click', () => this._promptCheckpoint(lineGid));
    frag.appendChild(ckptBtn);
    return frag;
  }

  async _loadUpdateLog(lineGid, container) {
    try {
      // 如果已有缓存的操作日志（来自 undo/redo 响应），优先使用
      let logs;
      if (this._lastOperationLog) {
        logs = this._lastOperationLog;
        this._lastOperationLog = null;
      } else {
        const [logRes, ckptRes] = await Promise.all([
          this._cf(`/api/bop/versions/${this._versionGid}/lifecycle/lines/${lineGid}/operation-log`),
          this._cf(`/api/bop/versions/${this._versionGid}/lifecycle/lines/${lineGid}/checkpoints`),
        ]);
        logs  = logRes.data  || [];
        var ckpts = ckptRes.data || [];
      }
      if (typeof ckpts === 'undefined') {
        try { ckpts = (await this._cf(`/api/bop/versions/${this._versionGid}/lifecycle/lines/${lineGid}/checkpoints`)).data || []; } catch { ckpts = []; }
      }

      container.innerHTML = '';
      if (!logs.length && !ckpts.length) {
        container.innerHTML =
          '<div style="font-size:10px;color:var(--subtext0,#a6adc8)">暂无操作记录</div>';
        return;
      }

      const items = [
        ...ckpts.map(c => ({ _t: 'ckpt', ...c })),
        ...logs.map(l  => ({ _t: 'log',  ...l  })),
      ].sort((a, b) => {
        const ta = a._t === 'ckpt' ? a.created_at   : a.performed_at;
        const tb = b._t === 'ckpt' ? b.created_at   : b.performed_at;
        return new Date(tb) - new Date(ta);
      });

      items.forEach(item => {
        if (item._t === 'ckpt') {
          const row = document.createElement('div');
          row.className = 'lv-lc-log-ckpt';
          row.innerHTML =
            `<span style="color:var(--blue,#89b4fa)">◉</span>` +
            `<span style="flex:1;color:var(--text,#cdd6f4)">${item.label || '快照'}</span>` +
            `<span style="color:var(--subtext0,#a6adc8)">${(item.created_at||'').slice(0,16).replace('T',' ')}</span>` +
            `<button data-gid="${item.gid}" style="font-size:11px;padding:1px 5px;background:transparent;` +
            `border:1px solid var(--surface2,#585b70);border-radius:3px;` +
            `color:var(--text,#cdd6f4);cursor:pointer">回滚</button>`;
          row.querySelector('[data-gid]').addEventListener('click', () =>
            this._rollback(lineGid, item.gid, item.label || '快照')
          );
          container.appendChild(row);
        } else {
          const OP = {
            create_entry:'新增', update_entry:'修改', delete_entry:'删除',
            add_link:'绑定', remove_link:'解绑',
          };
          const isUndone = item.batch_status === 'undone';
          const isInvalidated = item.batch_status === 'redo_invalidated';
          const row = document.createElement('div');
          row.className = 'lv-lc-log-line';
          if (isUndone || isInvalidated) {
            row.style.opacity = '0.45';
          }
          const statusTag = isUndone
            ? '<span style="color:#f38ba8;flex-shrink:0;font-size:10px;margin-left:4px">[已撤销]</span>'
            : isInvalidated
              ? '<span style="color:#fab387;flex-shrink:0;font-size:10px;margin-left:4px">[已失效]</span>'
              : '';
          row.innerHTML =
            `<span style="color:var(--subtext0,#a6adc8);flex-shrink:0">${(item.performed_at||'').slice(0,16).replace('T',' ')}</span>` +
            `<span style="color:var(--subtext1,#bac2de);flex-shrink:0">${item.performed_by_name||''}</span>` +
            `<span style="color:var(--text,#cdd6f4);flex:1${isUndone||isInvalidated ? ';text-decoration:line-through' : ''}">${OP[item.op_type]||item.op_type} ${item.entity_title||''}</span>` +
            statusTag;
          container.appendChild(row);
        }
      });
    } catch (e) {
      container.innerHTML =
        `<div style="font-size:10px;color:#f38ba8">加载失败: ${e.message}</div>`;
    }
  }

  // ── 归档卡片 ───────────────────────────────────────────────────────────────

  _renderArchivedCard() {
    const frag = document.createDocumentFragment();
    const rec  = (this._data?.history || []).find(h => h.phase === 'archived');
    const info = document.createElement('div');
    info.style.cssText = 'font-size:11px;color:var(--subtext0,#a6adc8);padding:4px 0';
    if (rec?.confirmed_at) {
      info.innerHTML =
        `<div style="margin-bottom:4px">归档日期：<span style="color:var(--text,#cdd6f4)">${rec.confirmed_at.slice(0,10)}</span></div>` +
        `<div>执行人：<span style="color:var(--text,#cdd6f4)">${rec.confirmed_by_name || '–'}</span></div>`;
    } else {
      info.textContent = '尚未归档';
    }
    frag.appendChild(info);
    return frag;
  }

  // ── 下区操作 ───────────────────────────────────────────────────────────────

  _renderActionZone(item) {
    if (!this._actionEl) return;
    this._actionEl.innerHTML = '';

    const title = document.createElement('div');
    title.className  = 'lv-lc-action-title';
    title.textContent = item.label;
    this._actionEl.appendChild(title);

    const lines = this._data?.lines || [];
    const activeLines = this._selectedLine
      ? lines.filter(l => l.gid === this._selectedLine)
      : lines;

    if (['nok_vpps','nok_unbound_parts','nok_unbound_ops'].includes(item.key)) {
      if (activeLines.length) {
        const groupEl = document.createElement('div');
        groupEl.style.cssText =
          'background:var(--base,#1e1e2e);border-radius:4px;padding:6px;margin-bottom:8px;font-size:9px';
        activeLines.forEach(line => {
          const ls = (this._data?.line_stats||[]).find(s => s.line_gid === line.gid) || {};
          const v  = ls[item.key] || 0;
          const row = document.createElement('div');
          row.style.cssText = 'display:flex;align-items:center;gap:4px;margin-bottom:2px';
          row.innerHTML =
            `<span style="flex:1;color:var(--subtext0,#a6adc8)">${line.title||line.gid.slice(-6)}</span>` +
            `<span style="color:${v > 0 ? '#f38ba8' : '#a6e3a1'}">NOK ${v}</span>`;
          groupEl.appendChild(row);
        });
        this._actionEl.appendChild(groupEl);
      }
      this._addJumpBtn('📦 打开 PBOM 页面', 'ebom');
      return;
    }

    if (['tools','fixtures','equipment'].includes(item.key)) {
      this._addJumpBtn('⚙ 打开工厂实物资源', 'factory_resource');
      return;
    }

    const jumpMap = {
      tasks:  { label: '📋 打开任务清单', tab: 'task'      },
      issues: { label: '🔴 打开问题清单', tab: 'issue'     },
      rules:  { label: '📐 打开规则管理', tab: 'rule_mgmt' },
    };
    const j = jumpMap[item.key];
    if (j) this._addJumpBtn(j.label, j.tab);
  }

  _addJumpBtn(label, tabId) {
    const btn = document.createElement('button');
    btn.className = 'lv-lc-jump-btn';
    btn.innerHTML =
      `${label} <span style="margin-left:auto;color:var(--overlay0,#6c7086)">→</span>`;
    btn.addEventListener('click', () => {
      const top = window.top || window.parent || window;
      if (top.TabManager) top.TabManager.open(tabId);
    });
    this._actionEl.appendChild(btn);
  }

  // ── 车型工序准备步骤 ────────────────────────────────────────────────────────

  async _renderVehicleOpsStep(stepKey) {
    const el  = this._actionEl;
    const api = window.top?.electronAPI || window.parent?.electronAPI || window.electronAPI;
    const cf  = window.parent?._cloudFetch || window._cloudFetch;

    // 获取 PBOM 版本 GID
    const _getPbomGid = async () => {
      try {
        const saved = JSON.parse(localStorage.getItem(`lc:pbom_import:${this._versionGid}`) || 'null');
        if (saved?.gid) return saved.gid;
        const res = await cf?.(`/api/bop/versions/${this._versionGid}`);
        return res?.data?.pbom_version_gid || '';
      } catch { return ''; }
    };

    // 显示统计（从 meta 读取）
    const stats = this._data?.vehicle_ops_prep || {};
    if (stats.total > 0) {
      const pct = Math.round((stats.confirmed || 0) / stats.total * 100);
      const color = pct === 100 ? 'var(--green,#a6e3a1)' : pct > 0 ? 'var(--blue,#89b4fa)' : 'var(--subtext0,#a6adc8)';
      const statsEl = document.createElement('div');
      statsEl.style.cssText =
        'background:var(--base,#1e1e2e);border-radius:6px;padding:8px 10px;margin-bottom:8px;font-size:11px';
      statsEl.innerHTML =
        `<div style="display:flex;justify-content:space-between;margin-bottom:4px">` +
        `<span style="color:var(--subtext0,#a6adc8)">已确认匹配</span>` +
        `<span style="color:${color};font-weight:600">${stats.confirmed} / ${stats.total}</span></div>` +
        `<div style="height:4px;background:var(--surface1,#45475a);border-radius:2px">` +
        `<div style="height:100%;width:${pct}%;background:${color};border-radius:2px;transition:width .3s"></div></div>` +
        (stats.skipped > 0
          ? `<div style="margin-top:4px;font-size:10px;color:var(--overlay0,#6c7086)">已跳过 ${stats.skipped} 条</div>`
          : '');
      el.appendChild(statsEl);
    } else {
      const hint = document.createElement('div');
      hint.style.cssText = 'font-size:11px;color:var(--subtext0,#a6adc8);margin-bottom:8px';
      hint.textContent = '在车型工序窗口中，将 PBOM 零件与 GBOP 工序匹配并确认。';
      el.appendChild(hint);
    }

    el.appendChild(this._makeActionBtn('🚗 打开车型工序窗口', async () => {
      if (!api?.showVehicleOpsWindow) {
        this._toast('功能不可用（需 Electron 环境）', 'warn'); return;
      }
      const pbomGid = await _getPbomGid();
      api.showVehicleOpsWindow({ pbomVersionGid: pbomGid, bopVersionGid: this._versionGid || '' });
    }));

    el.appendChild(this._makeMarkDoneBtn(stepKey));
  }

  // ── PBOM 连接统计展示 ──────────────────────────────────────────────────────

  async _renderPbomLinkStats() {
    const el = this._actionEl;

    const descEl = document.createElement('div');
    descEl.style.cssText = 'font-size:11px;color:var(--subtext0,#a6adc8);margin-bottom:8px;line-height:1.5';
    descEl.textContent = '将 PBOM 零件与 BOP 工序/操作节点关联。在工艺流程图中拖拽关联面板条目到工序节点完成绑定。';
    el.appendChild(descEl);

    // 统计区（先占位，加载后更新）
    const statsEl = document.createElement('div');
    statsEl.style.cssText =
      'background:var(--base,#1e1e2e);border-radius:6px;padding:8px 10px;margin-bottom:8px;font-size:11px';
    statsEl.innerHTML = '<span style="color:var(--subtext0,#a6adc8)">统计加载中…</span>';
    el.appendChild(statsEl);

    // 刷新统计
    const _refresh = async () => {
      try {
        const res = await this._cf(`/api/bop/versions/${this._versionGid}/pbom-link-stats`);
        const linked = res?.linked ?? 0;
        const total  = res?.total  ?? 0;
        const pct    = total > 0 ? Math.round(linked / total * 100) : 0;
        const color  = pct === 100 ? 'var(--green,#a6e3a1)' : pct > 0 ? 'var(--blue,#89b4fa)' : 'var(--subtext0,#a6adc8)';
        statsEl.innerHTML =
          `<div style="display:flex;justify-content:space-between;margin-bottom:4px">` +
          `<span>已关联 PBOM</span>` +
          `<span style="color:${color};font-weight:600">${linked} / ${total}</span>` +
          `</div>` +
          `<div style="height:4px;background:var(--surface1,#45475a);border-radius:2px">` +
          `<div style="height:100%;width:${pct}%;background:${color};border-radius:2px;transition:width .3s"></div>` +
          `</div>`;
      } catch {
        statsEl.innerHTML = '<span style="color:var(--subtext0,#a6adc8)">统计读取失败</span>';
      }
    };
    await _refresh();

    // 忽略未关联的操作
    const ignoreRow = document.createElement('div');
    ignoreRow.style.cssText = 'display:flex;gap:6px;margin-bottom:8px';
    const ignoreInp = document.createElement('input');
    ignoreInp.type = 'number'; ignoreInp.min = '0'; ignoreInp.placeholder = '忽略未关联数';
    ignoreInp.style.cssText = 'flex:1;padding:3px 6px;font-size:11px;background:var(--base,#1e1e2e);color:var(--text,#cdd6f4);border:1px solid var(--surface2,#585b70);border-radius:4px';
    const saveIgnoreBtn = document.createElement('button');
    saveIgnoreBtn.textContent = '保存忽略数';
    saveIgnoreBtn.style.cssText = 'padding:3px 8px;font-size:11px;background:transparent;border:1px solid var(--surface2,#585b70);border-radius:4px;color:var(--text,#cdd6f4);cursor:pointer';
    saveIgnoreBtn.addEventListener('click', async () => {
      const n = parseInt(ignoreInp.value) || 0;
      const lsKey = `lc:pbom_import:${this._versionGid || 'unknown'}`;
      const saved = JSON.parse(localStorage.getItem(lsKey) || 'null');
      if (saved?.gid) {
        try {
          await this._cf(`/api/bop/versions/${this._versionGid}/pbom-match`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pbom_version_gid: saved.gid, unlinked_ignored: n }),
          });
          this._toast('忽略数已保存', 'ok');
        } catch (e) { this._toast('保存失败: ' + e.message, 'error'); }
      } else {
        this._toast('未找到关联 PBOM 版本', 'warn');
      }
    });
    ignoreRow.appendChild(ignoreInp);
    ignoreRow.appendChild(saveIgnoreBtn);
    el.appendChild(ignoreRow);

    const refreshBtn = document.createElement('button');
    refreshBtn.textContent = '↻ 刷新统计';
    refreshBtn.style.cssText = 'width:100%;padding:4px;font-size:11px;background:transparent;border:1px solid var(--surface2,#585b70);border-radius:4px;color:var(--subtext0,#a6adc8);cursor:pointer;margin-bottom:6px';
    refreshBtn.addEventListener('click', _refresh);
    el.appendChild(refreshBtn);

    el.appendChild(this._makeMarkDoneBtn('pbom_linked'));
  }

  // ── PBOM 内联导入向导 ──────────────────────────────────────────────────────

  _renderPbomImportFlow(stepKey) {
    const el  = this._actionEl;
    el.innerHTML = '';

    const cf  = window.parent?._cloudFetch || window._cloudFetch;
    const api = window.top?.electronAPI || window.parent?.electronAPI || window.electronAPI;

    // localStorage 持久化：避免切出再切回重新创建
    const _lsKey  = `lc:pbom_import:${this._versionGid || 'unknown'}`;
    const _save   = (gid, name) => localStorage.setItem(_lsKey, JSON.stringify({ gid, name }));
    const _load   = () => { try { return JSON.parse(localStorage.getItem(_lsKey) || 'null'); } catch { return null; } };
    const _clear  = () => localStorage.removeItem(_lsKey);

    const _DATA_STAGES = ['Pre-TG0','TG0','TG1','PreTG2','TG2','EP1','EP2','PPV','PP','P','SOP'];

    // 时间戳精确到分钟
    const _ts = () => {
      const d = new Date();
      return `${d.getFullYear()}${String(d.getMonth()+1).padStart(2,'0')}${String(d.getDate()).padStart(2,'0')}-${String(d.getHours()).padStart(2,'0')}${String(d.getMinutes()).padStart(2,'0')}`;
    };

    // ── UI 工具函数 ────────────────────────────────────────
    const _s    = (css) => { const d = document.createElement('div'); d.style.cssText = css; return d; };
    const _lbl  = (text) => { const d = _s('font-size:10px;color:var(--subtext0,#a6adc8);margin-bottom:3px'); d.textContent = text; return d; };
    const _sel  = () => { const s = document.createElement('select'); s.style.cssText = 'width:100%;padding:4px 6px;font-size:11px;background:var(--base,#1e1e2e);color:var(--text,#cdd6f4);border:1px solid var(--surface2,#585b70);border-radius:4px;margin-bottom:8px'; return s; };
    const _btn  = (label, primary) => {
      const b = document.createElement('button'); b.textContent = label;
      b.style.cssText = `width:100%;padding:5px 8px;font-size:11px;border-radius:4px;cursor:pointer;margin-bottom:6px;font-weight:${primary?'600':'400'};` +
        (primary ? 'background:var(--blue,#89b4fa);color:var(--base,#1e1e2e);border:none;'
                 : 'background:transparent;color:var(--text,#cdd6f4);border:1px solid var(--surface2,#585b70);');
      return b;
    };
    const _toast = (msg, ok) => this._toast(msg, ok ? 'ok' : 'error');
    const _sep   = () => { const d = _s('border-top:1px solid var(--surface1,#45475a);margin:8px 0'); return d; };

    // ── 检查持久化状态 ─────────────────────────────────────
    let _pbomVersionGid = '';
    const saved = _load();

    if (saved?.gid) {
      // 已有版本：显示摘要，直接进入步骤 2
      _pbomVersionGid = saved.gid;
      const resumeEl = _s('margin-bottom:8px');
      const tag = document.createElement('div');
      tag.style.cssText = 'font-size:11px;font-weight:600;color:var(--green,#a6e3a1);margin-bottom:4px';
      tag.textContent = `✓ PBOM 版本已创建：${saved.name}`;
      resumeEl.appendChild(tag);
      const resetLink = document.createElement('span');
      resetLink.style.cssText = 'font-size:10px;color:var(--subtext0,#a6adc8);cursor:pointer;text-decoration:underline';
      resetLink.textContent = '重新创建新版本';
      resetLink.addEventListener('click', () => { _clear(); this._renderPbomImportFlow(stepKey); });
      resumeEl.appendChild(resetLink);
      el.appendChild(resumeEl);
      el.appendChild(_sep());
      _renderPhase2();
    } else {
      _renderPhase1();
    }

    // ── 第一步：新建 PBOM 版本 ─────────────────────────────
    function _renderPhase1() {
      const phase1 = _s('');
      const t1 = _s('font-size:11px;font-weight:600;color:var(--blue,#89b4fa);margin-bottom:8px');
      t1.textContent = '① 新建 PBOM 版本';
      phase1.appendChild(t1);

      phase1.appendChild(_lbl('所属项目 *'));
      const projSel = _sel();
      projSel.innerHTML = '<option value="">— 加载中… —</option>';
      phase1.appendChild(projSel);

      phase1.appendChild(_lbl('数据阶段 *'));
      const stageSel = _sel();
      stageSel.innerHTML = '<option value="">— 请选择 —</option>' +
        _DATA_STAGES.map(s => `<option value="${s}">${s}</option>`).join('');
      phase1.appendChild(stageSel);

      const verPreview = _s('font-size:10px;color:var(--subtext0,#a6adc8);margin-bottom:8px;min-height:14px');
      phase1.appendChild(verPreview);

      const createVerBtn = _btn('创建 PBOM 版本', true);
      createVerBtn.disabled = true;
      phase1.appendChild(createVerBtn);
      el.appendChild(phase1);

      const _updatePreview = () => {
        const pName = projSel?.options[projSel.selectedIndex]?.dataset.name || '';
        const stage = stageSel.value;
        if (pName && stage) {
          verPreview.textContent = `版本名：${pName}-${stage}-${_ts()}`;
          verPreview.style.color = 'var(--blue,#89b4fa)';
          createVerBtn.disabled = false;
        } else {
          verPreview.textContent = (pName || stage) ? '请同时选择项目和数据阶段' : '';
          verPreview.style.color = 'var(--subtext0,#a6adc8)';
          createVerBtn.disabled = true;
        }
      };

      cf?.('/api/projects').then(res => {
        const projects = (res?.data || []).filter(p => !p.is_deleted);
        projSel.innerHTML = '<option value="">— 请选择项目 —</option>' +
          projects.map(p => `<option value="${p.gid}" data-name="${p.name}">${p.name}</option>`).join('');
        projSel.addEventListener('change', _updatePreview);
        stageSel.addEventListener('change', _updatePreview);
      }).catch(() => { projSel.innerHTML = '<option value="">加载失败</option>'; });

      createVerBtn.addEventListener('click', async () => {
        const projGid  = projSel?.value || '';
        const projName = projSel?.options[projSel.selectedIndex]?.dataset.name || '';
        const stage    = stageSel.value;
        if (!projGid) { _toast('请选择项目', false); return; }
        if (!stage)   { _toast('请选择数据阶段', false); return; }
        createVerBtn.disabled = true;
        createVerBtn.textContent = '创建中…';
        try {
          const verName = `${projName}-${stage}-${_ts()}`;
          const res = await cf('/api/ebom/snapshots', {
            method: 'POST',
            body: JSON.stringify({ name: verName, version_tag: verName, project_gid: projGid, source_type: 'import' }),
          });
          if (!res?.success) throw new Error(res?.detail || '创建失败');
          _pbomVersionGid = res.data?.gid;
          _save(_pbomVersionGid, verName);
          createVerBtn.textContent = `✓ 已创建：${verName}`;
          if (projSel) { projSel.disabled = true; }
          stageSel.disabled = true;
          el.appendChild(_sep());
          _renderPhase2();
        } catch (e) {
          _toast('创建版本失败: ' + e.message, false);
          createVerBtn.disabled = false;
          createVerBtn.textContent = '创建 PBOM 版本';
        }
      });
    }

    // ── 第二步：选择 Excel 文件 ────────────────────────────
    function _renderPhase2() {
      const phase2 = _s('');
      const t2 = _s('font-size:11px;font-weight:600;color:var(--blue,#89b4fa);margin-bottom:8px');
      t2.textContent = '② 选择 Excel 文件';
      phase2.appendChild(t2);

      const pickBtn = _btn('📂 选择 .xlsx / .csv 文件', false);
      phase2.appendChild(pickBtn);

      const fileLabel = _s('font-size:10px;color:var(--subtext0,#a6adc8);margin-bottom:6px;min-height:14px');
      phase2.appendChild(fileLabel);
      el.appendChild(phase2);

      // 通用文件读取：Electron 用 showOpenDialog+readFileBase64，Web 用 <input type=file>
      const _pickAndParse = async () => {
        const _apiObj = window.top?.electronAPI || window.parent?.electronAPI || window.electronAPI;
        const _isWeb  = _apiObj?._isElectron === false;
        let fileName = '', b64 = '';

        if (_isWeb) {
          // Web 模式：用隐藏 <input type="file">
          const inp = document.createElement('input');
          inp.type = 'file'; inp.accept = '.xlsx,.xls,.xlsm,.csv';
          inp.style.display = 'none'; document.body.appendChild(inp);
          const file = await new Promise(res => {
            inp.addEventListener('change', () => { res(inp.files[0] || null); }, { once: true });
            inp.addEventListener('cancel', () => res(null), { once: true });
            inp.click();
          });
          document.body.removeChild(inp);
          if (!file) return;
          fileName = file.name;
          b64 = await new Promise((res, rej) => {
            const fr = new FileReader();
            fr.onload = () => res(fr.result.split(',')[1]);
            fr.onerror = rej;
            fr.readAsDataURL(file);
          });
        } else {
          // Electron 模式：showOpenDialog + readFileBase64
          const paths = await api?.showOpenDialog({
            filters: [{ name: 'Excel/CSV', extensions: ['xlsx','xls','xlsm','csv'] }],
            properties: ['openFile'],
          });
          if (!paths?.length) return;
          const filePath = paths[0];
          fileName = filePath.split(/[/\\]/).pop();
          b64 = await api.readFileBase64(filePath);
        }

        fileLabel.textContent = fileName;
        fileLabel.style.color = 'var(--text,#cdd6f4)';
        pickBtn.disabled = true; pickBtn.textContent = '解析中…';
        try {
          if (!window.XLSX) {
            await new Promise((resolve, reject) => {
              const s = document.createElement('script');
              s.src = '../assets/lib/xlsx.full.min.js';
              s.onload = resolve; s.onerror = reject;
              document.head.appendChild(s);
            });
          }
          const wb   = window.XLSX.read(b64, { type: 'base64' });
          const ws   = wb.Sheets[wb.SheetNames[0]];
          const rows = window.XLSX.utils.sheet_to_json(ws, { defval: '' });
          if (!rows.length) throw new Error('文件为空或无法解析');
          el.appendChild(_sep());
          _renderPhase3(rows, Object.keys(rows[0]), fileName);
        } catch (e) {
          _toast('解析失败: ' + e.message, false);
          pickBtn.disabled = false; pickBtn.textContent = '📂 重新选择文件';
        }
      };
      pickBtn.addEventListener('click', _pickAndParse);
    }

    // ── 第三步：字段映射 ───────────────────────────────────
    const _KEY_FIELDS = [
      { db: 'vpps',         label: 'VPPS',      required: true  },
      { db: 'vpps_desc',    label: 'VPPS描述',   required: false },
      { db: 'component_id', label: '零组件ID',   required: false },
      { db: 'name',         label: '零组件名称',  required: false },
      { db: 'level',        label: 'Level',      required: false },
      { db: 'bom_row',      label: 'BOM行',      required: false },
      { db: 'parent_vpps',  label: '父级VPPS',   required: false },
      { db: 'quantity',     label: '数量',        required: false },
    ];
    const _EXCEL_COL_MAP = {
      'VPPS':'vpps','VPPS描述':'vpps_desc','父级VPPS':'parent_vpps',
      'BOM 行':'bom_row','BOM行':'bom_row','零组件 ID':'component_id',
      '零组件ID':'component_id','零组件名称':'name','Level':'level','数量':'quantity',
    };

    function _renderPhase3(rows, headers, fileName) {
      const phase3 = _s('');
      const t3 = _s('font-size:11px;font-weight:600;color:var(--blue,#89b4fa);margin-bottom:6px');
      t3.textContent = `③ 字段映射（${fileName}，${rows.length} 行）`;
      phase3.appendChild(t3);

      const selects = {};
      _KEY_FIELDS.forEach(f => {
        const row = _s('display:flex;align-items:center;gap:6px;margin-bottom:5px');
        const lbl = document.createElement('span');
        lbl.style.cssText = `font-size:10px;width:72px;flex-shrink:0;color:${f.required?'var(--text,#cdd6f4)':'var(--subtext0,#a6adc8)'}`;
        lbl.textContent = f.label + (f.required ? ' *' : '');
        const sel = document.createElement('select');
        sel.style.cssText = 'flex:1;padding:2px 4px;font-size:10px;background:var(--base,#1e1e2e);color:var(--text,#cdd6f4);border:1px solid var(--surface2,#585b70);border-radius:3px';
        sel.innerHTML = '<option value="">— 不映射 —</option>' +
          headers.map(h => `<option value="${h}">${h}</option>`).join('');
        const autoMatch = headers.find(h => _EXCEL_COL_MAP[h] === f.db || h === f.db);
        if (autoMatch) sel.value = autoMatch;
        selects[f.db] = sel;
        row.appendChild(lbl); row.appendChild(sel);
        phase3.appendChild(row);
      });

      phase3.appendChild(_sep());
      const importBtn = _btn('导入', true);
      phase3.appendChild(importBtn);
      el.appendChild(phase3);

      importBtn.addEventListener('click', async () => {
        if (!selects['vpps'].value) { _toast('VPPS 字段必须映射', false); return; }
        importBtn.disabled = true; importBtn.textContent = '导入中…';
        try {
          const mapped = rows.map(raw => {
            const out = {};
            for (const f of _KEY_FIELDS) {
              const col = selects[f.db].value;
              if (col && raw[col] !== undefined && raw[col] !== '') out[f.db] = raw[col];
            }
            if (out.quantity !== undefined) out.quantity = parseFloat(out.quantity) || 1;
            if (out.level    !== undefined) { const lv = parseInt(out.level); out.level = isNaN(lv) ? null : lv; }
            if (!out.name) out.name = '';
            return out;
          }).filter(r => r.vpps);
          if (!mapped.length) throw new Error('没有含 VPPS 的有效行');
          const BATCH = 100;
          let inserted = 0;
          for (let i = 0; i < mapped.length; i += BATCH) {
            const res = await cf(`/api/ebom/snapshots/${_pbomVersionGid}/parts/batch`, {
              method: 'POST', body: JSON.stringify(mapped.slice(i, i + BATCH)),
            });
            if (!res?.success) throw new Error(`批量导入失败: ${res?.detail || ''}`);
            inserted += res.data?.inserted || 0;
          }
          importBtn.textContent = `✓ 导入完成（${inserted} 行）`;
          // 将 PBOM 版本绑定到 BOP 版本（pbom_version_gid），便于关系面板关联
          if (this._versionGid && _pbomVersionGid) {
            try {
              await cf(`/api/bop/versions/${this._versionGid}`, {
                method: 'PATCH',
                body: JSON.stringify({ pbom_version_gid: _pbomVersionGid }),
              });
            } catch (bindErr) {
              this._toast('PBOM 绑定到 BOP 版本失败: ' + bindErr.message, 'warn');
            }
          }
          el.appendChild(_sep());
          _renderDone(inserted);
        } catch (e) {
          _toast('导入失败: ' + e.message, false);
          importBtn.disabled = false; importBtn.textContent = '重试导入';
        }
      });
    }

    // ── 完成 ───────────────────────────────────────────────
    const _renderDone = (count) => {
      const done = _s('');
      const msg  = _s('font-size:11px;color:var(--green,#a6e3a1);margin-bottom:8px');
      msg.textContent = `✓ PBOM 已导入 ${count} 行，请标记完成。`;
      done.appendChild(msg);
      done.appendChild(this._makeMarkDoneBtn(stepKey));
      el.appendChild(done);
    };
  }

  // ── PM 确认阶段 ────────────────────────────────────────────────────────────

  _appendConfirmBtn(frag, phase) {
    // 创建模式尚无版本和生命周期数据，不能参与“阶段推进”判断。
    // 否则管理员会看到误导性的“请先完成前置阶段”锁定按钮。
    if (this._creationMode || !this._versionGid || !this._data) return;
    const authUser = window.parent?._authUser || window._authUser;
    const role     = authUser?.org_role || authUser?.system_role || authUser?.role || 'member';
    const canConfirm = ['project_admin','team_admin','super_admin'].includes(role);
    if (!canConfirm) return;

    const currentPhase = this._data?.lifecycle_phase;
    const currentIdx   = _LC_PHASE_ORDER.indexOf(currentPhase);
    const phaseIdx     = _LC_PHASE_ORDER.indexOf(phase);

    // 已完成阶段无需再确认
    if (phaseIdx < currentIdx) return;

    const isActive = currentPhase === phase;
    const btn = document.createElement('button');
    btn.className   = 'lv-lc-confirm-btn';
    btn.textContent = isActive ? '✓ 确认本阶段完成' : '🔒 请先完成前置阶段';
    btn.disabled    = !isActive;
    btn.style.marginTop = '10px';
    if (!isActive) btn.style.opacity = '0.45';

    if (isActive) {
      btn.addEventListener('click', async () => {
        if (!confirm('确认将本阶段标记为完成并推进到下一阶段？')) return;
        btn.disabled    = true;
        btn.textContent = '推进中…';
        try {
          const res = await this._cf(
            `/api/bop/versions/${this._versionGid}/lifecycle/confirm-phase`,
            { method: 'POST', headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ note: null }) }
          );
          this._viewPhase = res.lifecycle_phase;
          this._toast('阶段已推进：' + (_LC_PHASE_LABELS[res.lifecycle_phase] || res.lifecycle_phase), 'ok');
          await this._load();
        } catch (e) {
          this._toast('确认失败: ' + e.message, 'error');
          btn.disabled    = false;
          btn.textContent = '✓ 确认本阶段完成';
        }
      });
    }
    frag.appendChild(btn);
  }

  // ── Checkpoint ─────────────────────────────────────────────────────────────

  async _promptCheckpoint(lineGid) {
    const label = prompt('快照标签（可留空）：');
    if (label === null) return;
    try {
      await this._cf(
        `/api/bop/versions/${this._versionGid}/lifecycle/lines/${lineGid}/checkpoints`,
        { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ label }) }
      );
      this._toast('快照已创建', 'ok');
      this._render();
    } catch (e) {
      this._toast('快照失败: ' + e.message, 'error');
    }
  }

  async _rollback(lineGid, checkpointGid, label) {
    if (!confirm(`确认回滚到快照「${label}」？当前修改将丢失。`)) return;
    try {
      const res = await this._cf(
        `/api/bop/versions/${this._versionGid}/lifecycle/lines/${lineGid}/rollback/${checkpointGid}`,
        { method: 'POST' }
      );
      this._toast(`已回滚：恢复 ${res.restored_entries} 条节点`, 'ok');
      // 触发 lineage.js 重新加载（全局函数）
      if (typeof _load === 'function') _load();
      await this._load();
    } catch (e) {
      this._toast('回滚失败: ' + e.message, 'error');
    }
  }
}
