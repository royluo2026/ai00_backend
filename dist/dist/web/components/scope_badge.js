/**
 * web/components/scope_badge.js — 数据共享范围徽标 + 升级对话框
 *
 * 用法：在页面中引入此脚本后可调用：
 *   window.renderScopeBadge(scope)        → HTML 字符串（inline badge）
 *   window.openScopeUpgradeDialog(...)    → 弹出升级对话框
 *
 * 依赖：页面中已存在 window.parent._cloudFetch 或 window._cloudFetch（云端请求）
 */
(function () {
  // ── 颜色配置（Catppuccin 调色板）────────────────────────────────
  const SCOPE_COLORS = {
    personal:{ bg: 'rgba(108,112,134,0.18)', border: '#6c7086', text: '#a6adc8' },
    local:   { bg: 'rgba(108,112,134,0.18)', border: '#6c7086', text: '#a6adc8' },
    project: { bg: 'rgba(137,180,250,0.15)', border: '#89b4fa', text: '#89b4fa' },
    team:    { bg: 'rgba(166,227,161,0.15)', border: '#a6e3a1', text: '#a6e3a1' },
    global:  { bg: 'rgba(250,179,135,0.15)', border: '#fab387', text: '#fab387' },
  };

  const SCOPE_LABELS = {
    personal:'仅自己',
    local:   '本人',
    project: '项目',
    team:    '团队',
    global:  '全局',
  };

  const SCOPE_ORDER = ['personal', 'local', 'project', 'team', 'global'];

  /**
   * 渲染 scope badge HTML（span 元素）
   * @param {string} scope - local|project|team|global
   * @param {Object} [opts] - { clickable, itemType, itemGid, itemTitle }
   */
  function renderScopeBadge(scope, opts = {}) {
    const c = SCOPE_COLORS[scope] || SCOPE_COLORS.local;
    const label = SCOPE_LABELS[scope] || scope;
    const style = [
      `display:inline-flex`,
      `align-items:center`,
      `gap:3px`,
      `padding:2px 7px`,
      `border-radius:10px`,
      `border:1px solid ${c.border}`,
      `background:${c.bg}`,
      `color:${c.text}`,
      `font-size:11px`,
      `font-weight:500`,
      `line-height:1.4`,
      opts.clickable ? 'cursor:pointer;user-select:none' : '',
    ].filter(Boolean).join(';');

    const dataAttrs = opts.clickable
      ? ` data-scope-badge="1" data-scope="${scope}" data-item-type="${opts.itemType||''}" data-item-gid="${opts.itemGid||''}" data-item-title="${(opts.itemTitle||'').replace(/"/g,'&quot;')}"`
      : '';

    return `<span class="scope-badge" style="${style}"${dataAttrs}>${label}</span>`;
  }

  /**
   * 弹出 share_scope 升级对话框
   */
  function openScopeUpgradeDialog(itemType, itemGid, itemTitle, currentScope) {
    // 移除已有对话框
    document.getElementById('_scope-upgrade-dialog')?.remove();

    const currentIdx = SCOPE_ORDER.indexOf(currentScope);
    const higherScopes = SCOPE_ORDER.slice(currentIdx + 1);

    if (higherScopes.length === 0) {
      _showToast('该数据已是最高共享范围（全局）', 'info');
      return;
    }

    const scopeOptions = higherScopes.map(s =>
      `<label style="display:flex;align-items:center;gap:8px;cursor:pointer;padding:6px 8px;border-radius:6px;border:1px solid var(--border-default,#313244)">
        <input type="radio" name="target_scope" value="${s}">
        ${renderScopeBadge(s)} ${_scopeDesc(s)}
      </label>`
    ).join('');

    const dlg = document.createElement('div');
    dlg.id = '_scope-upgrade-dialog';
    dlg.style.cssText = [
      'position:fixed','inset:0','z-index:99999',
      'background:rgba(0,0,0,0.55)',
      'display:flex','align-items:center','justify-content:center',
    ].join(';');
    dlg.innerHTML = `
      <div style="background:var(--bg-secondary,#181825);border:1px solid var(--border-default,#313244);border-radius:12px;padding:24px;min-width:340px;max-width:480px;box-shadow:0 8px 32px rgba(0,0,0,0.4)">
        <h3 style="margin:0 0 8px;font-size:15px;color:var(--text-normal,#cdd6f4)">申请提升共享范围</h3>
        <p style="margin:0 0 16px;font-size:13px;color:var(--text-muted,#a6adc8)">
          <b>${itemTitle}</b><br>
          当前范围：${renderScopeBadge(currentScope)}
        </p>
        <div style="display:flex;flex-direction:column;gap:8px;margin-bottom:16px">
          ${scopeOptions}
        </div>
        <div style="margin-bottom:14px">
          <label style="font-size:12px;color:var(--text-muted,#a6adc8)">申请理由（可选）</label>
          <textarea id="_scope-reason" rows="2" style="width:100%;margin-top:4px;padding:6px 8px;background:var(--bg-primary,#1e1e2e);border:1px solid var(--border-default,#313244);border-radius:6px;color:var(--text-normal,#cdd6f4);font-size:13px;resize:none;box-sizing:border-box" placeholder="说明提升原因..."></textarea>
        </div>
        <div style="display:flex;gap:10px;justify-content:flex-end">
          <button id="_scope-cancel" style="padding:6px 14px;background:transparent;border:1px solid var(--border-default,#313244);color:var(--text-muted,#a6adc8);border-radius:6px;cursor:pointer;font-size:13px">取消</button>
          <button id="_scope-submit" style="padding:6px 14px;background:var(--color-accent,#89b4fa);color:var(--bg-primary,#1e1e2e);border:none;border-radius:6px;cursor:pointer;font-size:13px;font-weight:500">提交申请</button>
        </div>
      </div>
    `;
    document.body.appendChild(dlg);

    dlg.querySelector('#_scope-cancel').onclick = () => dlg.remove();
    dlg.addEventListener('click', e => { if (e.target === dlg) dlg.remove(); });

    dlg.querySelector('#_scope-submit').onclick = async () => {
      const selected = dlg.querySelector('input[name="target_scope"]:checked');
      if (!selected) { _showToast('请选择目标范围', 'warning'); return; }
      const reason = dlg.querySelector('#_scope-reason').value.trim();
      const btn = dlg.querySelector('#_scope-submit');
      btn.disabled = true;
      btn.textContent = '提交中...';
      try {
        const cf = (window.parent && window.parent._cloudFetch) || window._cloudFetch;
        if (!cf) throw new Error('_cloudFetch 未初始化');
        await cf('/api/approval/orders/scope_upgrade', {
          method: 'POST',
          body: JSON.stringify({
            item_type: itemType,
            item_gid: itemGid,
            item_title: itemTitle,
            current_scope: currentScope,
            target_scope: selected.value,
            reason,
          }),
        });
        _showToast('范围提升申请已提交，等待审批', 'success');
        dlg.remove();
      } catch (e) {
        _showToast('提交失败：' + e.message, 'error');
        btn.disabled = false;
        btn.textContent = '提交申请';
      }
    };
  }

  function _scopeDesc(scope) {
    return {
      project: '项目内所有成员可见',
      team:    '团队内所有成员可见',
      global:  '所有已登录用户可见',
    }[scope] || '';
  }

  function _showToast(msg, type = 'info') {
    if (typeof window.parent?._showToast === 'function') {
      window.parent._showToast(msg, type);
    } else if (typeof window._showToast === 'function') {
      window._showToast(msg, type);
    } else {
      alert(msg);
    }
  }

  // ── 全局委托：点击 [data-scope-badge="1"] 触发升级对话框 ──────────
  document.addEventListener('click', e => {
    const el = e.target.closest('[data-scope-badge="1"]');
    if (!el) return;
    e.stopPropagation();
    openScopeUpgradeDialog(
      el.dataset.itemType,
      el.dataset.itemGid,
      el.dataset.itemTitle,
      el.dataset.scope,
    );
  });

  window.renderScopeBadge = renderScopeBadge;
  window.openScopeUpgradeDialog = openScopeUpgradeDialog;

  /**
   * 弹出清单分享管理对话框（点对点，仅 Owner 可见）
   * @param {string} listGid
   * @param {string} listName
   */
  function openListShareDialog(listGid, listName) {
    document.getElementById('_list-share-dialog')?.remove();
    const dlg = document.createElement('div');
    dlg.id = '_list-share-dialog';
    dlg.style.cssText = 'position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,0.55);display:flex;align-items:center;justify-content:center';
    dlg.innerHTML = `
      <div style="background:var(--bg-secondary,#181825);border:1px solid var(--border-default,#313244);border-radius:12px;padding:24px;min-width:380px;max-width:540px;box-shadow:0 8px 32px rgba(0,0,0,0.4)">
        <h3 style="margin:0 0 12px;font-size:15px;color:var(--text-normal,#cdd6f4)">分享设置 — ${_esc(listName || listGid)}</h3>
        <div id="_lsd-share-list" style="max-height:200px;overflow-y:auto;margin-bottom:14px"></div>
        <div style="display:flex;gap:8px;align-items:center;margin-bottom:14px">
          <input id="_lsd-user-search" placeholder="搜索用户（姓名或邮箱）" style="flex:1;padding:6px 10px;background:var(--bg-primary,#1e1e2e);border:1px solid var(--border-default,#313244);border-radius:6px;color:var(--text-normal,#cdd6f4);font-size:13px">
          <select id="_lsd-perm-select" style="padding:6px 8px;background:var(--bg-primary,#1e1e2e);border:1px solid var(--border-default,#313244);border-radius:6px;color:var(--text-normal,#cdd6f4);font-size:13px">
            <option value="read">可查看</option>
            <option value="write">可编辑</option>
          </select>
          <button id="_lsd-add-btn" style="padding:6px 12px;background:var(--color-accent,#89b4fa);color:var(--bg-primary,#1e1e2e);border:none;border-radius:6px;cursor:pointer;font-size:13px;font-weight:500">添加</button>
        </div>
        <div id="_lsd-candidates" style="max-height:120px;overflow-y:auto;border:1px solid var(--border-default,#313244);border-radius:6px;display:none"></div>
        <div style="display:flex;justify-content:flex-end;margin-top:12px">
          <button id="_lsd-close" style="padding:6px 14px;background:transparent;border:1px solid var(--border-default,#313244);color:var(--text-muted,#a6adc8);border-radius:6px;cursor:pointer;font-size:13px">关闭</button>
        </div>
      </div>
    `;
    document.body.appendChild(dlg);

    const cf = (window.parent && window.parent._cloudFetch) || window._cloudFetch;
    const shareList = dlg.querySelector('#_lsd-share-list');
    const search   = dlg.querySelector('#_lsd-user-search');
    const permSel  = dlg.querySelector('#_lsd-perm-select');
    const addBtn   = dlg.querySelector('#_lsd-add-btn');
    const cands    = dlg.querySelector('#_lsd-candidates');

    let _selectedUser = null;

    async function loadShares() {
      if (!cf) return;
      try {
        const data = await cf(`/api/shares/lists/${listGid}`);
        shareList.innerHTML = !data.shares?.length
          ? '<p style="color:var(--text-muted);font-size:12px;margin:0">暂无分享</p>'
          : data.shares.map(s => `
              <div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border-default,#313244)">
                <span style="flex:1;font-size:13px;color:var(--text-normal)">${_esc(s.shared_to_name||s.shared_to)}</span>
                <span style="font-size:12px;color:var(--text-muted)">${s.permission==='write'?'可编辑':'可查看'}</span>
                <button data-share-gid="${s.gid}" style="padding:2px 8px;background:transparent;border:1px solid #f38ba8;color:#f38ba8;border-radius:4px;cursor:pointer;font-size:12px">移除</button>
              </div>`).join('');
        shareList.querySelectorAll('[data-share-gid]').forEach(btn => {
          btn.onclick = async () => {
            await cf(`/api/shares/lists/${listGid}/${btn.dataset.shareGid}`, { method: 'DELETE' });
            loadShares();
          };
        });
      } catch(_) {}
    }
    loadShares();

    let _searchTimer;
    search.addEventListener('input', () => {
      clearTimeout(_searchTimer);
      _searchTimer = setTimeout(async () => {
        const q = search.value.trim();
        if (!q || !cf) { cands.style.display='none'; return; }
        try {
          const data = await cf(`/api/users/search?q=${encodeURIComponent(q)}&limit=8`);
          const users = data.users || data.data || [];
          if (!users.length) { cands.style.display='none'; return; }
          cands.style.display = 'block';
          cands.innerHTML = users.map(u =>
            `<div data-gid="${u.gid}" data-name="${_esc(u.name||u.email)}" style="padding:6px 10px;cursor:pointer;font-size:13px;color:var(--text-normal)">${_esc(u.name||u.email)} <span style="color:var(--text-muted);font-size:11px">${_esc(u.email||'')}</span></div>`
          ).join('');
          cands.querySelectorAll('[data-gid]').forEach(el => {
            el.onmouseenter = () => el.style.background = 'var(--bg-hover,#313244)';
            el.onmouseleave = () => el.style.background = '';
            el.onclick = () => {
              _selectedUser = { gid: el.dataset.gid, name: el.dataset.name };
              search.value = el.dataset.name;
              cands.style.display = 'none';
            };
          });
        } catch(_) { cands.style.display='none'; }
      }, 300);
    });

    addBtn.onclick = async () => {
      if (!_selectedUser) { _showToast('请选择用户', 'warning'); return; }
      if (!cf) return;
      addBtn.disabled = true;
      try {
        await cf(`/api/shares/lists/${listGid}`, {
          method: 'POST',
          body: JSON.stringify({ shared_to: _selectedUser.gid, permission: permSel.value }),
        });
        _selectedUser = null;
        search.value = '';
        _showToast('已添加分享', 'success');
        loadShares();
      } catch(e) {
        _showToast('添加失败：' + e.message, 'error');
      } finally {
        addBtn.disabled = false;
      }
    };

    dlg.querySelector('#_lsd-close').onclick = () => dlg.remove();
    dlg.addEventListener('click', e => { if (e.target === dlg) dlg.remove(); });
  }

  function _esc(s) {
    return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  window.openListShareDialog = openListShareDialog;
})();

