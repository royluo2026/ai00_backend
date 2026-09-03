'use strict';
/**
 * VisibilitySelector — 可见范围统一选择器组件
 *
 * 用法：
 *   VisibilitySelector.renderWidget(containerEl, opts)
 *   VisibilitySelector.getValue(containerEl)  → { visibility, shared_team_gid, shared_project_gid }
 *   VisibilitySelector.renderBadge(visibility, opts)  → HTML string
 *   VisibilitySelector.showDialog(item, onSave)  → 弹出可见范围对话框
 */
window.VisibilitySelector = (() => {

  // ── 颜色 / 图标 / 标签 ──────────────────────────────────────────────────────

  const VIS_META = {
    private: {
      label: '个人',
      desc:  '仅自己可见',
      color: '#6c7086',
      bg:    'rgba(108,112,134,.15)',
      svg:   `<svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><rect x="3" y="7" width="10" height="8" rx="2"/><path d="M5 7V5a3 3 0 016 0v2"/></svg>`,
    },
    team: {
      label: '团队',
      desc:  '指定团队成员可见',
      color: '#a6e3a1',
      bg:    'rgba(166,227,161,.15)',
      svg:   `<svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="6" cy="5" r="2.5"/><path d="M1 13c0-2.5 2-4 5-4s5 1.5 5 4"/><circle cx="12" cy="5" r="2"/><path d="M12 9c1.5.2 3 1 3 2.5"/></svg>`,
    },
    project: {
      label: '项目',
      desc:  '指定项目成员可见',
      color: '#89b4fa',
      bg:    'rgba(137,180,250,.15)',
      svg:   `<svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><rect x="2" y="3" width="12" height="10" rx="1"/><line x1="5" y1="7" x2="11" y2="7"/><line x1="5" y1="10" x2="9" y2="10"/></svg>`,
    },
    public: {
      label: '公开',
      desc:  '所有登录用户可见',
      color: '#fab387',
      bg:    'rgba(250,179,135,.15)',
      svg:   `<svg width="10" height="10" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="8" cy="8" r="6"/><path d="M8 2c1.5 2 2.5 3.5 2.5 6S9.5 12 8 14"/><path d="M8 2c-1.5 2-2.5 3.5-2.5 6S6.5 12 8 14"/><line x1="2" y1="8" x2="14" y2="8"/></svg>`,
    },
  };

  const _esc = s => String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  const _cf  = () => window._cloudFetch || window.top?._cloudFetch || window.parent?._cloudFetch;

  async function _invokeCapability(id, payload = {}) {
    const _cloudFetch = _cf();
    if (!_cloudFetch) throw new Error('云端服务未连接');
    const response = await _cloudFetch(`/api/v1/capabilities/${id}:invoke`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ version: 1, payload }),
    });
    const envelope = response?.data;
    if (response?.success !== true || envelope?.ok !== true) {
      const detail = envelope?.error || response?.error || {};
      throw new Error(detail.message || `能力调用失败：${id}@1`);
    }
    const value = envelope.data;
    return value?.data !== undefined && Object.keys(value).length === 1 ? value.data : value;
  }

  // ── 数据获取 ────────────────────────────────────────────────────────────────

  let _teamsCache    = null;
  let _projectsCache = null;

  async function _fetchTeams() {
    if (_teamsCache) return _teamsCache;
    try {
      const client = window.top?.AI00ExistingCapabilityClient || window.parent?.AI00ExistingCapabilityClient || window.AI00ExistingCapabilityClient;
      if (!client) return [];
      const data = await client.call('base.teams.list');
      _teamsCache = Array.isArray(data) ? data : (data?.data || data?.teams || []);
    } catch (_) { _teamsCache = []; }
    return _teamsCache;
  }

  async function _fetchUserProjects() {
    if (_projectsCache) return _projectsCache;
    try {
      const _cloudFetch = _cf();
      if (!_cloudFetch) return [];
      const data = await _invokeCapability('project.project.read.atomic.projects_search', {});
      const arr = Array.isArray(data) ? data : (data?.data || data?.projects || []);
      _projectsCache = arr;
    } catch (_) { _projectsCache = []; }
    return _projectsCache;
  }

  /** 返回当前用户所在小团队 + 所有直系父团队（链式上溯） */
  async function _getUserTeamChain() {
    const myTeamId = window.top?._authUser?.team_id || window._authUser?.team_id;
    if (!myTeamId) return [];
    const all = await _fetchTeams();
    const byGid = new Map(all.map(t => [t.gid, t]));
    const chain = [];
    let cur = byGid.get(myTeamId);
    while (cur) {
      chain.push(cur);
      cur = cur.parent_team_gid ? byGid.get(cur.parent_team_gid) : null;
    }
    return chain; // [小团队, 父团队, 祖父团队...]
  }

  // ── renderWidget ────────────────────────────────────────────────────────────

  /**
   * 在 containerEl 里渲染可见范围选择器。
   * opts: { initialVisibility, initialTeamGid, initialProjectGid, onChange }
   */
  async function renderWidget(containerEl, opts = {}) {
    const {
      initialVisibility  = 'team',
      initialTeamGid     = null,
      initialProjectGid  = null,
      onChange           = null,
    } = opts;

    containerEl.innerHTML = `
      <div class="vs-btns">
        <button type="button" class="vs-btn" data-vis="private">个人</button>
        <button type="button" class="vs-btn" data-vis="team">团队</button>
        <button type="button" class="vs-btn" data-vis="project">项目</button>
        <button type="button" class="vs-btn" data-vis="public">公开</button>
      </div>
      <div class="vs-sub" id="_vsSub" style="display:none"></div>`;

    _injectStyles();

    let _curVis     = initialVisibility;
    let _curTeamGid = initialTeamGid;
    let _curProjGid = initialProjectGid;

    const btns  = containerEl.querySelectorAll('.vs-btn');
    const subEl = containerEl.querySelector('#_vsSub');

    const _setActive = (v) => {
      btns.forEach(b => b.classList.toggle('vs-btn-active', b.dataset.vis === v));
    };

    const _showSub = async (v) => {
      subEl.style.display = 'none';
      subEl.innerHTML = '';
      if (v === 'team') {
        subEl.style.display = 'block';
        subEl.innerHTML = `<select class="vs-select" id="_vsTeamSel"><option value="">加载中…</option></select>`;
        const chain = await _getUserTeamChain();
        const sel   = subEl.querySelector('#_vsTeamSel');
        sel.innerHTML = chain.map((t, i) =>
          `<option value="${_esc(t.gid)}"${(i === 0 || t.gid === _curTeamGid) && !_curTeamGid ? (i===0 ? ' selected' : '') : (t.gid === _curTeamGid ? ' selected' : '')}>
            ${i === 0 ? '' : '└ '}${_esc(t.name)}${i === 0 ? '（我的团队）' : ''}
          </option>`
        ).join('');
        if (!_curTeamGid && chain.length) _curTeamGid = chain[0].gid;
        sel.value = _curTeamGid || '';
        sel.addEventListener('change', () => { _curTeamGid = sel.value; onChange?.(); });
      } else if (v === 'project') {
        subEl.style.display = 'block';
        subEl.innerHTML = `<select class="vs-select" id="_vsProjSel"><option value="">加载中…</option></select>`;
        const projects = await _fetchUserProjects();
        const sel = subEl.querySelector('#_vsProjSel');
        sel.innerHTML = `<option value="">— 选择项目 —</option>` +
          projects.map(p => `<option value="${_esc(p.gid)}" ${p.gid === _curProjGid ? 'selected' : ''}>${_esc(p.name || p.project_code || p.gid)}</option>`).join('');
        sel.value = _curProjGid || '';
        sel.addEventListener('change', () => { _curProjGid = sel.value; onChange?.(); });
      }
    };

    btns.forEach(btn => {
      btn.addEventListener('click', async () => {
        _curVis = btn.dataset.vis;
        _setActive(_curVis);
        await _showSub(_curVis);
        onChange?.();
      });
    });

    // 初始化
    _setActive(_curVis);
    await _showSub(_curVis);

    // 让外部可以 getValue
    containerEl._vsGetValue = () => ({
      visibility:         _curVis,
      shared_team_gid:    _curVis === 'team'    ? (_curTeamGid || null) : null,
      shared_project_gid: _curVis === 'project' ? (_curProjGid || null) : null,
    });
  }

  // ── getValue ────────────────────────────────────────────────────────────────

  function getValue(containerEl) {
    if (containerEl._vsGetValue) return containerEl._vsGetValue();
    // 降级：读取按钮激活状态
    const activeBtn = containerEl.querySelector('.vs-btn-active');
    const vis = activeBtn?.dataset.vis || 'team';
    return {
      visibility:         vis,
      shared_team_gid:    vis === 'team'    ? (containerEl.querySelector('#_vsTeamSel')?.value || null) : null,
      shared_project_gid: vis === 'project' ? (containerEl.querySelector('#_vsProjSel')?.value || null) : null,
    };
  }

  // ── renderBadge ─────────────────────────────────────────────────────────────

  /**
   * 返回可见范围小图标 HTML string。
   * opts: { title: '具体团队/项目名称', size: 10 }
   */
  function renderBadge(visibility, opts = {}) {
    const v    = visibility || 'team';
    const meta = VIS_META[v] || VIS_META.team;
    const title = opts.title ? `${meta.label}（${opts.title}）` : meta.label;
    _injectStyles();
    return `<span class="vs-badge vs-badge-${v}" title="${_esc(title)}" style="color:${meta.color}">${meta.svg}</span>`;
  }

  // ── showDialog ──────────────────────────────────────────────────────────────

  /**
   * 弹出可见范围设置对话框。
   * item: { gid, name/title, visibility, shared_team_gid, shared_project_gid }
   * onSave: async ({ visibility, shared_team_gid, shared_project_gid }) => void
   */
  async function showDialog(item, onSave) {
    document.getElementById('_vsDialog')?.remove();
    const dlg = document.createElement('div');
    dlg.id = '_vsDialog';
    dlg.style.cssText = 'position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,.5);display:flex;align-items:center;justify-content:center';
    const displayName = item.name || item.title || item.bop_name || item.gid || '';
    dlg.innerHTML = `
      <div style="background:var(--bg-secondary,#181825);border:1px solid var(--border-default,#313244);border-radius:10px;padding:20px;width:340px;box-shadow:0 8px 32px rgba(0,0,0,.4)">
        <div style="font-size:14px;font-weight:600;color:var(--text-normal,#cdd6f4);margin-bottom:4px">设置可见范围</div>
        <div style="font-size:11px;color:var(--text-muted,#a6adc8);margin-bottom:14px">${_esc(displayName)}</div>
        <div id="_vsWidgetMount"></div>
        <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:16px">
          <button id="_vsCancel" style="padding:5px 14px;border-radius:5px;border:1px solid var(--border-default,#313244);background:transparent;color:var(--text-muted,#a6adc8);cursor:pointer;font-size:12px">取消</button>
          <button id="_vsSave" style="padding:5px 14px;border-radius:5px;border:none;background:var(--color-accent,#89b4fa);color:var(--bg-primary,#1e1e2e);cursor:pointer;font-size:12px;font-weight:600">保存</button>
        </div>
      </div>`;
    document.body.appendChild(dlg);

    const mount = dlg.querySelector('#_vsWidgetMount');
    await renderWidget(mount, {
      initialVisibility:  item.visibility  || item.scope_type || 'team',
      initialTeamGid:     item.shared_team_gid    || item.team_gid    || null,
      initialProjectGid:  item.shared_project_gid || item.project_gid || null,
    });

    dlg.querySelector('#_vsCancel').onclick = () => dlg.remove();
    dlg.querySelector('#_vsSave').onclick = async () => {
      const val = getValue(mount);
      dlg.remove();
      await onSave?.(val);
    };
    dlg.addEventListener('click', e => { if (e.target === dlg) dlg.remove(); });
  }

  // ── CSS ─────────────────────────────────────────────────────────────────────

  let _stylesInjected = false;
  function _injectStyles() {
    if (_stylesInjected) return;
    _stylesInjected = true;
    const style = document.createElement('style');
    style.textContent = `
.vs-btns { display:flex; gap:4px; flex-wrap:wrap; }
.vs-btn {
  padding:4px 12px; border-radius:5px; font-size:12px; cursor:pointer;
  border:1px solid var(--border-default,#313244);
  background:transparent; color:var(--text-muted,#a6adc8);
  transition:all .12s;
}
.vs-btn:hover { border-color:var(--color-accent,#89b4fa); color:var(--text-normal,#cdd6f4); }
.vs-btn-active { background:var(--color-accent,#89b4fa); color:var(--bg-primary,#1e1e2e); border-color:var(--color-accent,#89b4fa); }
.vs-sub { margin-top:8px; }
.vs-select {
  width:100%; padding:6px 10px;
  background:var(--bg-primary,#1e1e2e);
  border:1px solid var(--border-default,#313244);
  border-radius:6px; color:var(--text-normal,#cdd6f4);
  font-size:12px; outline:none;
}
.vs-badge {
  display:inline-flex; align-items:center; justify-content:center;
  width:14px; height:14px; flex-shrink:0; opacity:.75;
  vertical-align:middle; margin-right:2px;
}
.vs-badge svg { display:block; }
[data-theme="light"] .vs-btn { color:var(--text-muted,#8c8fa1); }
[data-theme="light"] .vs-btn-active { color:var(--bg-primary,#eff1f5); }
    `;
    document.head.appendChild(style);
  }

  return { renderWidget, getValue, renderBadge, showDialog, VIS_META };
})();
