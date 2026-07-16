/**
 * web/team_space/team_space.js
 * ────────────────────────────
 * 团队空间页面逻辑（PT-WB 类型）
 * 仅飞书登录模式可见（由 nav_manager grantCheck:'team_admin' 门控）
 */
'use strict';

// ── 主题同步 ──────────────────────────────────────────────────────────────────
function _applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme || 'dark');
}
(function () {
  try {
    const cfg = JSON.parse(localStorage.getItem('ai00:system-config') || '{}');
    _applyTheme(cfg['system.theme'] || 'dark');
  } catch (_) {}
  try {
    if (window.electronAPI?.onThemeChanged) {
      window.electronAPI.onThemeChanged(t => _applyTheme(t));
    }
  } catch (_) {}
})();

// ── 云端 fetch ────────────────────────────────────────────────────────────────
function _cf(path, opts) {
  const fetch = window._cloudFetch || window.parent?._cloudFetch;
  if (!fetch) return Promise.reject(new Error('no cloud fetch'));
  return fetch(path, opts);
}

// ── State ─────────────────────────────────────────────────────────────────────
let _teams      = [];      // 所有可见团队
let _currentTeam = null;   // 当前选中团队 {gid, name, parent_team_gid}
let _members    = [];      // 当前团队成员
let _teamLists  = [];      // 当前团队相关清单
let _myGrants   = [];      // 当前用户 grants
let _myGid      = '';

// ── Boot ──────────────────────────────────────────────────────────────────────
async function init() {
  // 获取当前用户信息
  try {
    const me = await _cf('/users/me');
    const meData = me.data || me;
    _myGid    = meData.gid || '';
    _myGrants = meData.grants || [];
  } catch (_) {}

  await _loadTeams();
  _bindActions();
}

// ── Load teams ────────────────────────────────────────────────────────────────
async function _loadTeams() {
  try {
    const data = await _cf('/teams');
    _teams = Array.isArray(data) ? data : (data.data || data.teams || []);
  } catch (_) {
    _teams = [];
  }
  _renderTeamTree();
}

function _renderTeamTree() {
  const treeEl = document.getElementById('tsTeamTree');
  if (!treeEl) return;

  // 构建树（parent_team_gid 为空 = 根节点）
  const childMap = {};
  _teams.forEach(t => {
    const pid = t.parent_team_gid || '__root__';
    if (!childMap[pid]) childMap[pid] = [];
    childMap[pid].push(t);
  });

  function renderNode(team, depth) {
    const active = _currentTeam?.gid === team.gid;
    const indent = depth * 12;
    const childCount = (childMap[team.gid] || []).length;
    const div = document.createElement('div');
    div.className = 'ts-team-item' + (active ? ' active' : '');
    div.dataset.gid = team.gid;
    div.innerHTML = `
      <span class="ts-indent" style="width:${indent}px"></span>
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>
        <path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>
      </svg>
      <span class="ts-name">${_esc(team.name || team.gid)}</span>
      ${childCount ? `<span class="ts-count">${childCount}</span>` : ''}
    `;
    div.addEventListener('click', () => _selectTeam(team));
    treeEl.appendChild(div);
    (childMap[team.gid] || []).forEach(child => renderNode(child, depth + 1));
  }

  treeEl.innerHTML = '';
  (childMap['__root__'] || []).forEach(t => renderNode(t, 0));

  // 有 team_admin grant → 显示新建子团队
  const hasAdmin = _isTeamAdmin();
  const addBtn = document.getElementById('tsAddTeam');
  if (addBtn) addBtn.style.display = hasAdmin ? '' : 'none';
}

// ── Select team ───────────────────────────────────────────────────────────────
async function _selectTeam(team) {
  _currentTeam = team;

  // 更新树高亮
  document.querySelectorAll('.ts-team-item').forEach(el => {
    el.classList.toggle('active', el.dataset.gid === team.gid);
  });

  // 更新 topbar
  const nameEl = document.getElementById('tsTeamName');
  if (nameEl) nameEl.textContent = team.name || team.gid;

  const hasAdmin = _isTeamAdmin(team.gid);
  const adminBadge = document.getElementById('tsAdminBadge');
  if (adminBadge) adminBadge.style.display = hasAdmin ? '' : 'none';
  ['tsBtnAddMember', 'tsBtnTransfer'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = hasAdmin ? '' : 'none';
  });

  // 删除按钮仅超管可见
  const isSuperAdmin = _isSuperAdmin();
  const delBtn = document.getElementById('tsBtnDelete');
  if (delBtn) delBtn.style.display = isSuperAdmin ? '' : 'none';

  // quick actions widget 仅 team_admin 或 super_admin 可见
  const qaWidget = document.getElementById('tsQuickActionsWidget');
  if (qaWidget) qaWidget.style.display = hasAdmin ? '' : 'none';

  // 隐藏空提示，显示 widgets
  document.getElementById('tsEmptyHint').style.display = 'none';
  document.getElementById('tsWidgets').style.display = '';

  await Promise.all([_loadMembers(team.gid), _loadTeamLists(team.gid)]);
}

// ── Load members ──────────────────────────────────────────────────────────────
async function _loadMembers(teamGid) {
  try {
    const data = await _cf(`/teams/${encodeURIComponent(teamGid)}/members`);
    _members = Array.isArray(data) ? data : (data.data || data.members || []);
  } catch (_) {
    _members = [];
  }
  _renderMembers();
}

function _renderMembers() {
  const listEl = document.getElementById('tsMemberList');
  const countEl = document.getElementById('tsMemberCount');
  if (!listEl) return;
  if (countEl) countEl.textContent = `(${_members.length})`;
  const badge = document.getElementById('tsMemberCountBadge');
  if (badge) { badge.textContent = `${_members.length} 人`; badge.style.display = ''; }

  const hasAdmin = _isTeamAdmin(_currentTeam?.gid);
  if (_members.length === 0) {
    listEl.innerHTML = '<div class="ts-empty"><p>暂无成员</p></div>';
    return;
  }

  const ORG_ROLE_LABELS = { super_admin: '超级管理员', member: '成员', external: '外部' };
  listEl.innerHTML = _members.map(m => {
    const initials = (m.name || m.email || '?').slice(0, 2).toUpperCase();
    const orgLabel = ORG_ROLE_LABELS[m.org_role || m.system_role] || '成员';
    const grants = (m.grants || []).filter(g => g.grant_type === 'team_admin' && g.scope_gid === _currentTeam?.gid);
    const isAdmin = grants.length > 0;
    const joinDate = m.created_at ? new Date(m.created_at).toLocaleDateString('zh-CN') : '';
    const avatarHtml = m.avatar_url
      ? `<img class="ts-avatar ts-avatar-img" src="${_escAttr(m.avatar_url)}" alt="${_esc(initials)}" onerror="this.outerHTML='<div class=\\'ts-avatar\\'>${_esc(initials)}</div>'">`
      : `<div class="ts-avatar">${_esc(initials)}</div>`;
    return `<div class="ts-member-row" data-gid="${_escAttr(m.gid || '')}">
      ${avatarHtml}
      <div class="ts-member-name">${_esc(m.name || m.email || m.gid)}</div>
      ${isAdmin ? `<span class="ts-grant-tag">team_admin</span>` : ''}
      <span class="ts-member-role">${_esc(orgLabel)}</span>
      <span class="ts-member-role" style="margin-left:8px">${joinDate}</span>
      ${hasAdmin && m.gid !== _myGid ? `
        <div class="ts-member-actions">
          <button class="ts-icon-btn" title="分配 team_admin grant" data-action="grant-admin" data-user="${_escAttr(m.gid || '')}">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
          </button>
          <button class="ts-icon-btn ts-danger" title="移除成员" data-action="remove-member" data-user="${_escAttr(m.gid || '')}">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
      ` : ''}
    </div>`;
  }).join('');

  // bind action buttons
  listEl.querySelectorAll('[data-action="grant-admin"]').forEach(btn => {
    btn.addEventListener('click', () => _grantTeamAdmin(btn.dataset.user));
  });
  listEl.querySelectorAll('[data-action="remove-member"]').forEach(btn => {
    btn.addEventListener('click', () => _removeMember(btn.dataset.user));
  });
}

// ── Load team lists ────────────────────────────────────────────────────────────
async function _loadTeamLists(teamGid) {
  try {
    const data = await _cf(`/api/lists?owner_team_gid=${encodeURIComponent(teamGid)}&read_scope=team`);
    _teamLists = Array.isArray(data) ? data : (data.lists || data.data || []);
  } catch (_) {
    _teamLists = [];
  }
  _renderTeamLists();
}

function _renderTeamLists() {
  const el = document.getElementById('tsTeamLists');
  const countEl = document.getElementById('tsListCount');
  if (!el) return;
  if (countEl) countEl.textContent = `(${_teamLists.length})`;
  if (_teamLists.length === 0) {
    el.innerHTML = '<div class="ts-empty"><p>暂无团队清单</p></div>';
    return;
  }
  el.innerHTML = _teamLists.map(l => `
    <div class="ts-list-item" data-gid="${_escAttr(l.gid || '')}" data-type="${_escAttr(l.item_type || 'task')}">
      <div class="ts-list-dot" style="background:${_listColor(l.item_type)}"></div>
      <div class="ts-list-title">${_esc(l.name || l.title || l.gid)}</div>
      <div class="ts-list-meta">${_esc(l.item_type || '')} · ${l.read_scope || ''}</div>
    </div>
  `).join('');

  el.querySelectorAll('.ts-list-item').forEach(item => {
    item.addEventListener('click', () => {
      const itemType = item.dataset.type;
      const listGid  = item.dataset.gid;
      const p = window.parent;
      if (p && p.TabManager) {
        p.TabManager.open(itemType === 'issue' ? 'issue' : 'task', { list_gid: listGid });
      }
    });
  });
}

function _listColor(itemType) {
  const m = { task: '#89b4fa', issue: '#f38ba8', knowledge: '#a6e3a1', rule: '#f9e2af' };
  return m[itemType] || '#6c7086';
}

// ── Grant / remove helpers ────────────────────────────────────────────────────
async function _grantTeamAdmin(userGid) {
  if (!userGid || !_currentTeam) return;
  try {
    await _cf('/api/grants', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ grantee_gid: userGid, grant_type: 'team_admin', scope_gid: _currentTeam.gid }),
    });
    await _loadMembers(_currentTeam.gid);
  } catch (e) {
    alert('授权失败：' + (e.message || String(e)));
  }
}

async function _removeMember(userGid) {
  if (!userGid || !_currentTeam) return;
  if (!confirm('确认从团队移除该成员？')) return;
  try {
    await _cf(`/teams/${encodeURIComponent(_currentTeam.gid)}/members/${encodeURIComponent(userGid)}`, { method: 'DELETE' });
    await _loadMembers(_currentTeam.gid);
  } catch (e) {
    alert('移除失败：' + (e.message || String(e)));
  }
}

// ── Delete team ───────────────────────────────────────────────────────────────
async function _deleteCurrentTeam() {
  if (!_currentTeam) return;
  if (!confirm(`确认软删除团队「${_currentTeam.name || _currentTeam.gid}」？\n\n团队将从列表隐藏，成员数据不受影响。`)) return;
  try {
    await _cf(`/teams/${encodeURIComponent(_currentTeam.gid)}`, { method: 'DELETE' });
    _currentTeam = null;
    document.getElementById('tsTeamName').textContent = '选择团队';
    document.getElementById('tsAdminBadge').style.display = 'none';
    document.getElementById('tsBtnDelete').style.display = 'none';
    ['tsBtnAddMember', 'tsBtnTransfer'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.style.display = 'none';
    });
    document.getElementById('tsEmptyHint').style.display = '';
    document.getElementById('tsWidgets').style.display = 'none';
    await _loadTeams();
  } catch (e) {
    alert('删除失败：' + (e.message || String(e)));
  }
}

// ── Dialog: add member ────────────────────────────────────────────────────────
function _openAddMemberDlg() {
  document.getElementById('dlgMemberSearch').value = '';
  document.getElementById('dlgMemberResults').innerHTML = '';
  document.getElementById('dlgAddMember').classList.add('open');
}

document.getElementById('dlgMemberSearch')?.addEventListener('input', _debounce(async (e) => {
  const q = e.target.value.trim();
  if (q.length < 2) { document.getElementById('dlgMemberResults').innerHTML = ''; return; }
  try {
    const data = await _cf(`/users/search?q=${encodeURIComponent(q)}&limit=8`);
    const users = Array.isArray(data) ? data : (data.data || data.users || []);
    const resultsEl = document.getElementById('dlgMemberResults');
    resultsEl.innerHTML = users.map(u => `
      <div style="display:flex;align-items:center;gap:8px;padding:8px 12px;cursor:pointer;border-radius:4px"
           class="ts-member-row" data-gid="${_escAttr(u.gid)}" data-name="${_escAttr(u.name || '')}">
        ${u.avatar_url
          ? `<img class="ts-avatar ts-avatar-img" style="width:22px;height:22px" src="${_escAttr(u.avatar_url)}" alt="${_esc((u.name||'?')[0])}" onerror="this.outerHTML='<div class=\\'ts-avatar\\" style=\\"width:22px;height:22px;font-size:9px\\">${_esc((u.name||'?').slice(0,2).toUpperCase())}</div>'">`
          : `<div class="ts-avatar" style="width:22px;height:22px;font-size:9px">${_esc((u.name || '?').slice(0, 2).toUpperCase())}</div>`}
        <span>${_esc(u.name || u.email || u.gid)}</span>
        <span style="color:var(--text-muted);font-size:11px">${_esc(u.email || '')}</span>
      </div>
    `).join('');
    resultsEl.querySelectorAll('.ts-member-row').forEach(row => {
      row.addEventListener('click', () => {
        resultsEl.querySelectorAll('.ts-member-row').forEach(r => r.style.background = '');
        row.style.background = 'var(--active)';
        row.dataset.selected = '1';
      });
    });
  } catch (_) {}
}, 300));

document.getElementById('dlgMemberCancel')?.addEventListener('click', () => {
  document.getElementById('dlgAddMember').classList.remove('open');
});
document.getElementById('dlgMemberConfirm')?.addEventListener('click', async () => {
  const selected = document.querySelector('#dlgMemberResults [data-selected="1"]');
  if (!selected || !_currentTeam) { alert('请先选择一个用户'); return; }
  const userGid = selected.dataset.gid;
  const role = document.getElementById('dlgMemberRole').value;
  try {
    await _cf(`/teams/${encodeURIComponent(_currentTeam.gid)}/members`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_gid: userGid }),
    });
    if (role === 'team_admin') {
      await _grantTeamAdmin(userGid);
    } else {
      await _loadMembers(_currentTeam.gid);
    }
    document.getElementById('dlgAddMember').classList.remove('open');
  } catch (e) {
    alert('添加失败：' + (e.message || String(e)));
  }
});

// ── Dialog: create sub-team ───────────────────────────────────────────────────
function _openCreateSubDlg() {
  document.getElementById('dlgSubTeamName').value = '';
  document.getElementById('dlgCreateSub').classList.add('open');
}
document.getElementById('dlgSubCancel')?.addEventListener('click', () => {
  document.getElementById('dlgCreateSub').classList.remove('open');
});
document.getElementById('dlgSubConfirm')?.addEventListener('click', async () => {
  const name = document.getElementById('dlgSubTeamName').value.trim();
  if (!name) { alert('请输入团队名称'); return; }
  try {
    await _cf('/teams', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, parent_team_gid: _currentTeam?.gid || null }),
    });
    document.getElementById('dlgCreateSub').classList.remove('open');
    await _loadTeams();
  } catch (e) {
    alert('创建失败：' + (e.message || String(e)));
  }
});

// ── Dialog: transfer admin ────────────────────────────────────────────────────
function _openTransferDlg() {
  const sel = document.getElementById('dlgTransferTarget');
  if (!sel) return;
  sel.innerHTML = _members.filter(m => m.gid !== _myGid).map(m =>
    `<option value="${_escAttr(m.gid)}">${_esc(m.name || m.email || m.gid)}</option>`
  ).join('');
  document.getElementById('dlgTransfer').classList.add('open');
}
document.getElementById('dlgTransferCancel')?.addEventListener('click', () => {
  document.getElementById('dlgTransfer').classList.remove('open');
});
document.getElementById('dlgTransferConfirm')?.addEventListener('click', async () => {
  const targetGid = document.getElementById('dlgTransferTarget').value;
  if (!targetGid || !_currentTeam) return;
  if (!confirm('确认转让？此操作将撤销您在该团队的 team_admin 权限。')) return;
  try {
    await _cf('/api/grants', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ grantee_gid: targetGid, grant_type: 'team_admin', scope_gid: _currentTeam.gid }),
    });
    const ownGrant = _myGrants.find(g => g.grant_type === 'team_admin' && g.scope_gid === _currentTeam.gid);
    if (ownGrant) {
      await _cf(`/api/grants/${encodeURIComponent(ownGrant.gid)}`, { method: 'DELETE' }).catch(() => {});
    }
    document.getElementById('dlgTransfer').classList.remove('open');
    await _loadTeams();
    if (_currentTeam) await _loadMembers(_currentTeam.gid);
  } catch (e) {
    alert('转让失败：' + (e.message || String(e)));
  }
});

// ── Bind button actions ────────────────────────────────────────────────────────
function _bindActions() {
  document.getElementById('tsBtnAddMember')?.addEventListener('click', _openAddMemberDlg);
  document.getElementById('tsQaBtnAddMember')?.addEventListener('click', _openAddMemberDlg);
  document.getElementById('tsBtnTransfer')?.addEventListener('click', _openTransferDlg);
  document.getElementById('tsQaBtnTransfer')?.addEventListener('click', _openTransferDlg);
  document.getElementById('tsAddTeam')?.addEventListener('click', _openCreateSubDlg);
  document.getElementById('tsQaBtnCreateSub')?.addEventListener('click', _openCreateSubDlg);
  document.getElementById('tsBtnDelete')?.addEventListener('click', _deleteCurrentTeam);

  // Close overlays on backdrop click
  ['dlgAddMember', 'dlgCreateSub', 'dlgTransfer'].forEach(id => {
    const el = document.getElementById(id);
    el?.addEventListener('click', e => {
      if (e.target === el) el.classList.remove('open');
    });
  });
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function _isSuperAdmin() {
  const me = window.parent?._authUser || {};
  return me.org_role === 'super_admin' || me.system_role === 'super_admin';
}

function _isTeamAdmin(teamGid) {
  // super_admin 无限制
  const me = window.parent?._authUser || {};
  if (me.org_role === 'super_admin' || me.system_role === 'super_admin') return true;
  // check grants
  const grants = _myGrants.length ? _myGrants : (me.grants || []);
  return grants.some(g => g.grant_type === 'team_admin' && (!teamGid || g.scope_gid === teamGid));
}

function _esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
  );
}
function _escAttr(s) { return _esc(s); }

function _debounce(fn, ms) {
  let t;
  return function (...args) {
    clearTimeout(t);
    t = setTimeout(() => fn.apply(this, args), ms);
  };
}

// ── Start ─────────────────────────────────────────────────────────────────────
// 等待 _cloudFetch 就绪（Electron 模式下可能需要等待 python:ready）
(function waitAndInit(attempts) {
  const fetch = window._cloudFetch || window.parent?._cloudFetch;
  if (fetch) { init(); return; }
  if (attempts > 0) setTimeout(() => waitAndInit(attempts - 1), 400);
})(15);

// 监听主题变化（跨窗口广播）
window.addEventListener('message', e => {
  if (e.data?.type === 'theme-change') _applyTheme(e.data.theme);
});
