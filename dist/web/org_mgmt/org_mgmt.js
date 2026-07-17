/**
 * web/org_mgmt/org_mgmt.js
 * 组织管理：组织架构 / 项目成员
 */
'use strict';

// ── 主题同步 ──────────────────────────────────────────────────
window.addEventListener('message', e => {
  if (e.data?.type === 'theme') document.documentElement.setAttribute('data-theme', e.data.theme);
});

// ── cloudFetch 桥接 ────────────────────────────────────────────
async function api(path, opts) {
  const cf = window.parent?._cloudFetch || window.top?._cloudFetch || window._cloudFetch;
  if (typeof cf !== 'function') {
    console.warn('[org_mgmt] _cloudFetch 不可用');
    return null;
  }
  try {
    return await cf(path, opts);
  } catch (e) {
    console.warn('[org_mgmt] API 失败:', e.message);
    return null;
  }
}

// ── 角色标签 ──────────────────────────────────────────────────
const ROLE_LABELS = {
  super_admin:    '超管',
  team_admin:     '团队管理员',
  project_admin:  '项目管理员',
  rule_admin:     '规则管理员',
  knowledge_admin:'知识管理员',
  member:         '成员',
  external:       '外部',
};

const PROJECT_ROLE_LABELS = {
  project_owner: '项目经理',
  section_lead:  'Section Owner',
  member:        '成员',
};

// ── 全局状态 ──────────────────────────────────────────────────
let _allUsers    = [];
let _allTeams    = [];
let _allProjects = [];
let _selectedTeamGid = null;
let _editingUserId   = null;

// ── Tab 切换 ──────────────────────────────────────────────────
document.querySelectorAll('.org-tab').forEach(btn => {
  btn.addEventListener('click', () => {
    const tab = btn.dataset.tab;
    document.querySelectorAll('.org-tab').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.querySelectorAll('.org-panel').forEach(p => {
      p.classList.remove('active');
      p.classList.add('hidden');
    });
    const panel = document.getElementById(`panel-${tab}`);
    if (panel) { panel.classList.remove('hidden'); panel.classList.add('active'); }
    if (tab === 'struct')  loadStruct();
    else if (tab === 'members') loadProjects();
  });
});


// ══════════════════════════════════════════════════════════════
// Tab 1 — 组织架构
// ══════════════════════════════════════════════════════════════

async function loadStruct() {
  const [teamsRes, usersRes] = await Promise.all([
    api('/api/org/teams'),
    _allUsers.length ? Promise.resolve({ data: _allUsers }) : api('/api/users/'),
  ]);
  _allTeams = Array.isArray(teamsRes) ? teamsRes : (teamsRes?.data || []);
  if (usersRes?.data) _allUsers = usersRes.data;
  _renderStructTree();
}

// ── 从飞书同步组织架构 ─────────────────────────────────────────
document.getElementById('btn-sync-feishu').addEventListener('click', async () => {
  const btn    = document.getElementById('btn-sync-feishu');
  const banner = document.getElementById('sync-result-banner');
  btn.disabled = true;
  btn.innerHTML = '<svg class="icon" width="13" height="13"><use href="#icon-refresh"/></svg> 同步中…';
  try {
    const res = await api('/feishu/sync/org', { method: 'POST' });
    if (res?.status === 'syncing' || res?.success) {
      banner.textContent = '组织架构与成员同步已在后台启动，完成后请刷新页面查看';
      banner.className = 'sync-banner sync-ok';
      setTimeout(() => loadStruct(), 3000);
    } else {
      banner.textContent = res?.detail || '同步失败';
      banner.className = 'sync-banner sync-err';
    }
  } catch (e) {
    banner.textContent = `同步出错：${e.message}`;
    banner.className = 'sync-banner sync-err';
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<svg class="icon" width="13" height="13"><use href="#icon-refresh"/></svg> 从飞书同步组织架构';
    setTimeout(() => { banner.className = 'sync-banner hidden'; }, 8000);
  }
});

// ── 展开状态（gid set） ────────────────────────────────────────
let _expandedTeams = new Set();
let _feishuFolded = true;  // 飞书组织默认折叠

function _renderStructTree() {
  const body = document.getElementById('struct-tree-body');

  if (!_allTeams.length) {
    body.innerHTML = '<div class="empty-hint" style="padding:24px 16px">暂无团队<br>请先点击"从飞书同步组织架构"</div>';
    return;
  }

  // 拆分：手动团队 vs 飞书组织
  const manualTeams = _allTeams.filter(t => !t.feishu_dept_id);
  const feishuTeams = _allTeams.filter(t => !!t.feishu_dept_id);

  // 飞书组织按层级构建
  const feishuChildMap = {};
  feishuTeams.forEach(t => {
    const pid = t.parent_team_gid || '__root__';
    if (!feishuChildMap[pid]) feishuChildMap[pid] = [];
    feishuChildMap[pid].push(t);
  });
  Object.values(feishuChildMap).forEach(arr => arr.sort((a, b) => a.name.localeCompare(b.name, 'zh')));

  // 手动团队按名称排序
  manualTeams.sort((a, b) => a.name.localeCompare(b.name, 'zh'));

  let html = '';

  // ── 手动团队区域 ──────────────────────────────────────────────
  html += `<div class="st-section-hdr">
    <span>手动团队</span>
    <span class="st-section-cnt">${manualTeams.length}</span>
    <button class="st-section-add-btn" id="stManualAddBtn" title="新建团队">＋</button>
  </div>`;
  // 内联添加输入框（默认隐藏）
  html += `<div class="st-inline-add" id="stManualAddRow" style="display:none">
    <input type="text" id="stManualAddInp" placeholder="输入团队名称…" autocomplete="off" />
    <button id="stManualAddOk">确定</button>
    <button id="stManualAddCancel">取消</button>
  </div>`;
  if (manualTeams.length === 0) {
    html += '<div class="st-empty-sub">暂无手动创建的团队</div>';
  } else {
    manualTeams.forEach(t => {
      html += _renderNodeHtml(t, 0, feishuChildMap);
    });
  }

  // ── 飞书组织区域 ──────────────────────────────────────────────
  html += `<div class="st-section-hdr st-section-fs" id="stFeishuHdr">
    <span class="st-section-toggle">${_feishuFolded ? '▶' : '▼'}</span>
    <span>飞书组织</span>
    <span class="st-section-cnt">${feishuTeams.length}</span>
  </div>`;
  if (!_feishuFolded) {
    if (feishuTeams.length === 0) {
      html += '<div class="st-empty-sub">暂无飞书部门</div>';
    } else {
      (feishuChildMap['__root__'] || []).forEach(t => {
        html += _renderNodeHtml(t, 0, feishuChildMap);
      });
    }
  }

  body.innerHTML = html;

  // 手动团队内联添加
  const addBtn = document.getElementById('stManualAddBtn');
  const addRow = document.getElementById('stManualAddRow');
  const addInp = document.getElementById('stManualAddInp');
  if (addBtn) addBtn.addEventListener('click', e => {
    e.stopPropagation();
    addRow.style.display = 'flex';
    addInp.focus();
  });
  document.getElementById('stManualAddOk')?.addEventListener('click', async () => {
    const name = addInp.value.trim();
    if (!name) return _toast('请输入团队名称', 'err');
    const res = await api('/teams', { method: 'POST', body: JSON.stringify({ name }) });
    if (res?.success) {
      _toast('团队已创建');
      addRow.style.display = 'none'; addInp.value = '';
      await loadStruct();
    } else {
      _toast(res?.detail || '创建失败', 'err');
    }
  });
  document.getElementById('stManualAddCancel')?.addEventListener('click', () => {
    addRow.style.display = 'none'; addInp.value = '';
  });
  addInp?.addEventListener('keydown', e => {
    if (e.key === 'Enter') document.getElementById('stManualAddOk')?.click();
    if (e.key === 'Escape') { addRow.style.display = 'none'; addInp.value = ''; }
  });

  // 飞书组织折叠 toggle
  const fsHdr = document.getElementById('stFeishuHdr');
  if (fsHdr) {
    fsHdr.addEventListener('click', () => {
      _feishuFolded = !_feishuFolded;
      _renderStructTree();
    });
  }

  // 展开/折叠
  body.querySelectorAll('[data-toggle]').forEach(el => {
    el.addEventListener('click', e => {
      e.stopPropagation();
      const gid = el.dataset.toggle;
      if (!gid) return;
      if (_expandedTeams.has(gid)) _expandedTeams.delete(gid);
      else _expandedTeams.add(gid);
      _renderStructTree();
    });
  });

  // 选中节点
  body.querySelectorAll('.st-node').forEach(el => {
    el.addEventListener('click', () => {
      _selectedTeamGid = el.dataset.gid;
      _renderStructTree();
      _loadTeamDetail(_selectedTeamGid);
    });
    el.addEventListener('contextmenu', e => {
      e.preventDefault();
      const team = _allTeams.find(t => t.gid === el.dataset.gid);
      if (team) _showTreeCtxMenu(e.clientX, e.clientY, team);
    });
  });
}

function _renderNodeHtml(team, depth, childMap) {
  const children = childMap[team.gid] || [];
  const hasChildren = children.length > 0;
  const isExpanded = _expandedTeams.has(team.gid);
  const isSelected = _selectedTeamGid === team.gid;
  const indent = depth * 16 + 10;
  const isFeishu = !!team.feishu_dept_id;

  let html = `<div class="st-node${isSelected ? ' selected' : ''}" data-gid="${team.gid}" style="padding-left:${indent}px">
    <span class="st-toggle" data-toggle="${team.gid}">
      ${hasChildren
        ? (isExpanded
            ? '<svg width="10" height="10" viewBox="0 0 10 10" fill="currentColor"><path d="M1 3 L5 7 L9 3"/></svg>'
            : '<svg width="10" height="10" viewBox="0 0 10 10" fill="currentColor"><path d="M3 1 L7 5 L3 9"/></svg>')
        : ''}
    </span>
    <svg class="st-node-icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      ${isFeishu
        ? '<circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/>'
        : '<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/>'}
    </svg>
    <span class="st-node-name">${_esc(team.name)}</span>
    ${isFeishu ? '<span class="st-node-tag">飞书</span>' : ''}
    ${hasChildren ? `<span class="st-node-count">${children.length}</span>` : ''}
  </div>`;

  if (isExpanded) {
    children.forEach(child => { html += _renderNodeHtml(child, depth + 1, childMap); });
  }
  return html;
}

// ── 右键菜单 ──────────────────────────────────────────────────
let _ctxMenu = null;

function _showTreeCtxMenu(x, y, team) {
  if (_ctxMenu) { _ctxMenu.remove(); _ctxMenu = null; }
  if (!team.feishu_dept_id) return;

  const menu = document.createElement('div');
  menu.className = 'org-ctx-menu';
  menu.style.cssText = `position:fixed;left:${x}px;top:${y}px;z-index:500`;
  menu.innerHTML = `
    <div class="org-ctx-item" id="ctx-sync-members">
      <svg class="icon" width="13" height="13"><use href="#icon-refresh"/></svg>
      <span>同步该组织成员</span>
    </div>`;

  document.body.appendChild(menu);
  _ctxMenu = menu;

  menu.querySelector('#ctx-sync-members').addEventListener('click', () => {
    menu.remove(); _ctxMenu = null;
    _syncTeamMembers(team);
  });

  const dismiss = e => {
    if (!menu.contains(e.target)) {
      menu.remove(); _ctxMenu = null;
      document.removeEventListener('mousedown', dismiss);
    }
  };
  setTimeout(() => document.addEventListener('mousedown', dismiss), 10);
}

// ── 同步该组织成员（不重载树，只刷新成员列表）────────────────────
async function _syncTeamMembers(team) {
  const banner = document.getElementById('sync-result-banner');
  banner.textContent = `正在同步「${team.name}」的成员…`;
  banner.className = 'sync-banner sync-ok';

  try {
    const res = await api('/api/org/sync-from-feishu', {
      method: 'POST',
      body: JSON.stringify({ dept_id: team.feishu_dept_id }),
    });
    if (res?.ok || res?.created != null) {
      const { created = 0, updated = 0 } = res;
      banner.textContent = `「${team.name}」同步完成：新建 ${created} 人，更新 ${updated} 人`;
      banner.className = 'sync-banner sync-ok';
      // 只刷新成员列表，不重载整棵树（避免展开状态丢失）
      if (_selectedTeamGid === team.gid) {
        // 先更新 _allUsers 缓存再刷新列表
        const usersRes = await api('/api/users/');
        if (usersRes?.data) _allUsers = usersRes.data;
        _loadTeamMembers(team.gid);
      }
    } else {
      banner.textContent = res?.detail || '同步失败';
      banner.className = 'sync-banner sync-err';
    }
  } catch (e) {
    banner.textContent = `同步出错：${e.message}`;
    banner.className = 'sync-banner sync-err';
  }
  setTimeout(() => { banner.className = 'sync-banner hidden'; }, 6000);
}

async function _loadTeamDetail(gid) {
  const team = _allTeams.find(t => t.gid === gid);
  if (!team) return;

  document.getElementById('struct-detail-empty').classList.add('hidden');
  document.getElementById('struct-detail-form').classList.remove('hidden');

  document.getElementById('struct-name-input').value = team.name;

  const badge = document.getElementById('struct-type-badge');
  badge.textContent = team.feishu_dept_id ? '飞书部门' : '手动创建';
  badge.className = `struct-type-badge ${team.feishu_dept_id ? 'badge-big' : 'badge-small'}`;

  await _loadTeamMembers(gid);
}

async function _loadTeamMembers(gid) {
  // 先刷新 _allUsers 缓存，确保新添加的成员可用
  try {
    const usersRes = await api('/api/users/');
    if (usersRes?.data) _allUsers = usersRes.data;
  } catch {}
  const res = await api(`/teams/${gid}/members`);
  const members = res?.data || [];
  document.getElementById('struct-members-count').textContent = `成员（${members.length} 人）`;

  const list = document.getElementById('struct-members-list');
  if (!members.length) {
    list.innerHTML = '<div style="color:var(--text-faint);font-size:12px;padding:8px 0">暂无成员</div>';
    return;
  }
  list.innerHTML = members.map(m => {
    // API 返回 org_role；修改角色后从 _allUsers 缓存取最新值
    const cached = _allUsers.find(u => u.gid === m.gid);
    const role = cached?.system_role || m.org_role || 'member';
    const roleLabel = ROLE_LABELS[role] || role || '—';
    const isAdmin = role === 'team_admin';
    return `
    <div class="struct-member-row">
      <div class="struct-member-info">
        ${m.avatar_url
          ? `<img src="${_esc(m.avatar_url)}" class="struct-member-avatar" />`
          : `<div class="struct-member-avatar-placeholder"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/></svg></div>`}
        <span class="struct-member-name">${_esc(m.name || m.email)}</span>
      </div>
      <div style="display:flex;align-items:center;gap:6px;flex-shrink:0">
        <span class="role-badge ${role}"
              style="${isAdmin ? '' : 'opacity:.55;font-size:10px'}">${roleLabel}</span>
        <button class="btn-edit-sm" onclick="openRoleModal('${m.gid}','${gid}')">修改角色</button>
        <button class="btn-danger-sm" onclick="removeTeamMember('${gid}','${m.gid}')">移除</button>
      </div>
    </div>`;
  }).join('');
}

window.removeTeamMember = async function(teamGid, userGid) {
  if (!confirm('确定将该成员移出团队？')) return;
  const res = await api(`/teams/${teamGid}/members/${userGid}`, { method: 'DELETE' });
  if (res?.success) _loadTeamMembers(teamGid);
};

// 保存团队名称
document.getElementById('struct-save-btn').addEventListener('click', async () => {
  if (!_selectedTeamGid) return;
  const team = _allTeams.find(t => t.gid === _selectedTeamGid);
  if (!team) return;
  const newName = document.getElementById('struct-name-input').value.trim();
  if (!newName) return _toast('团队名称不能为空', 'err');
  if (newName === team.name) return _toast('未做任何修改');
  const res = await api(`/teams/${_selectedTeamGid}`, {
    method: 'PATCH',
    body: JSON.stringify({ name: newName }),
  });
  if (res?.success) {
    team.name = newName;
    _toast('保存成功');
    _renderStructTree();
  } else {
    _toast(res?.detail || '保存失败，请重试', 'err');
  }
});

// 删除团队
document.getElementById('struct-delete-btn').addEventListener('click', async () => {
  if (!_selectedTeamGid) return;
  if (!confirm('确定删除该团队？此操作不可恢复。')) return;
  const res = await api(`/teams/${_selectedTeamGid}`, { method: 'DELETE' });
  if (res?.success) {
    _expandedTeams.delete(_selectedTeamGid);
    _selectedTeamGid = null;
    document.getElementById('struct-detail-form').classList.add('hidden');
    document.getElementById('struct-detail-empty').classList.remove('hidden');
    await loadStruct();
  }
});

// ── 修改用户角色（全局，从成员行调用）───────────────────────────

// openRoleModal(userGid, teamGid) — teamGid 用于保存后刷新成员列表
window.openRoleModal = function(userGid, teamGid) {
  const user = _allUsers.find(u => u.gid === userGid);
  if (!user) return;
  _editingUserId  = userGid;
  _editingTeamGid = teamGid || null;

  document.getElementById('role-user-preview').innerHTML = `
    <div>
      <div class="user-name">${_esc(user.name || user.email)}</div>
      <div class="user-email">${_esc(user.email || '')}</div>
    </div>`;
  document.getElementById('select-new-role').value = user.system_role || user.org_role || 'member';
  document.getElementById('external-subtype-row').classList.toggle('hidden', (user.system_role || user.org_role) !== 'external');
  document.getElementById('select-ext-subtype').value = user.external_subtype || '';
  document.getElementById('modal-edit-role').classList.remove('hidden');
};

let _editingTeamGid = null;

document.getElementById('select-new-role').addEventListener('change', function() {
  document.getElementById('external-subtype-row').classList.toggle('hidden', this.value !== 'external');
});
document.getElementById('btn-close-role-modal').addEventListener('click', () => {
  document.getElementById('modal-edit-role').classList.add('hidden');
});
document.getElementById('btn-cancel-role').addEventListener('click', () => {
  document.getElementById('modal-edit-role').classList.add('hidden');
});
document.getElementById('btn-confirm-role').addEventListener('click', async () => {
  if (!_editingUserId) return;
  const newRole    = document.getElementById('select-new-role').value;
  const extSubtype = document.getElementById('select-ext-subtype').value || null;
  const body = { new_role: newRole };
  if (newRole === 'external' && extSubtype) body.external_subtype = extSubtype;

  const res = await api(`/api/users/${_editingUserId}/role`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
  if (res?.success) {
    document.getElementById('modal-edit-role').classList.add('hidden');
    // 更新本地缓存
    const u = _allUsers.find(u => u.gid === _editingUserId);
    if (u) { u.system_role = newRole; if (extSubtype) u.external_subtype = extSubtype; }
    // 刷新成员列表
    if (_editingTeamGid) _loadTeamMembers(_editingTeamGid);
  } else {
    _toast(res?.detail || res?.message || '修改角色失败，请检查权限', 'err');
  }
});

// ── 用户搜索组件工厂 ───────────────────────────────────────────

function _makeUserSearchWidget({ inputId, resultsId, selectedId, onSelect }) {
  const input    = document.getElementById(inputId);
  const results  = document.getElementById(resultsId);
  const selected = document.getElementById(selectedId);
  if (!input || !results || !selected) {
    console.warn('[UserSearch] elements not found:', inputId, resultsId, selectedId);
    return { reset: () => {} };
  }
  let _timer = null;

  input.addEventListener('input', () => {
    clearTimeout(_timer);
    const q = input.value.trim();
    if (!q) { results.classList.add('hidden'); return; }
    results.innerHTML = '<div class="user-search-empty">搜索中…</div>';
    results.classList.remove('hidden');
    _timer = setTimeout(() => _doSearch(q), 300);
  });

  document.addEventListener('mousedown', e => {
    if (!input.contains(e.target) && !results.contains(e.target)) {
      results.classList.add('hidden');
    }
  });

  async function _doSearch(q) {
    const res = await api(`/feishu/org/users/search?q=${encodeURIComponent(q)}`);
    const users = res?.data || [];
    if (!users.length) {
      results.innerHTML = '<div class="user-search-empty">未找到用户</div>';
      return;
    }
    results.innerHTML = users.map(u => {
      const inSys = !!u.db_gid;
      const avatar = u.avatar_url
        ? `<img src="${_esc(u.avatar_url)}" />`
        : `<div class="usr-avatar-ph"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/></svg></div>`;
      const openId = u.open_id || '';
      return `
        <div class="user-search-result-item"
             data-gid="${_esc(u.db_gid || '')}"
             data-open-id="${_esc(openId)}"
             data-name="${_esc(u.name || '')}"
             data-email="${_esc(u.email || '')}"
             data-avatar="${_esc(u.avatar_url || '')}">
          ${avatar}
          <div class="user-search-result-info">
            <div class="user-search-result-name">${_esc(u.name || '')}</div>
            ${u.email ? `<div class="user-search-result-email">${_esc(u.email)}</div>` : ''}
          </div>
          <span class="user-search-result-badge ${inSys ? 'in-sys' : 'no-sys'}">${inSys ? '已注册' : '未注册'}</span>
        </div>`;
    }).join('');

    results.querySelectorAll('.user-search-result-item').forEach(el => {
      el.addEventListener('mousedown', e => {
        e.preventDefault();
        // 转为普通对象，避免 DOMStringMap 引用失效
        const ds = el.dataset;
        _selectUser({
          gid: ds.gid || '',
          openId: ds.openId || '',
          name: ds.name || '',
          email: ds.email || '',
          avatar: ds.avatar || '',
        });
      });
    });
  }

  function _selectUser(ds) {
    results.classList.add('hidden');
    input.value = '';
    selected.classList.remove('hidden');
    const clearId = `${selectedId}-clear`;
    const name = ds.name || '';
    const avatarUrl = ds.avatar || '';
    selected.innerHTML = `
      ${avatarUrl ? `<img src="${_esc(avatarUrl)}" />` : ''}
      <span class="user-search-selected-name">${_esc(name)}</span>
      <span style="font-size:10px;color:var(--subtext0);margin-left:4px">${ds.gid ? '已注册' : '新用户'}</span>
      <button class="user-search-clear" id="${clearId}">×</button>`;
    document.getElementById(clearId)?.addEventListener('click', () => reset());
    onSelect(ds);
  }

  function reset() {
    input.value = '';
    results.classList.add('hidden');
    selected.classList.add('hidden');
    selected.innerHTML = '';
    onSelect(null);
  }

  return { reset, setSelected: _selectUser };
}

// ── 添加团队成员 ───────────────────────────────────────────────

let _selectedTeamMemberData = null;
const _teamMemberSearch = _makeUserSearchWidget({
  inputId:    'search-team-member-input',
  resultsId:  'search-team-member-results',
  selectedId: 'search-team-member-selected',
  onSelect:   ds => { _selectedTeamMemberData = ds; },
});

document.getElementById('struct-add-member-btn').addEventListener('click', () => {
  _teamMemberSearch.reset();
  document.getElementById('modal-add-team-member').classList.remove('hidden');
  setTimeout(() => document.getElementById('search-team-member-input').focus(), 50);
});
document.getElementById('btn-close-team-member-modal').addEventListener('click', () => {
  document.getElementById('modal-add-team-member').classList.add('hidden');
});
document.getElementById('btn-cancel-team-member').addEventListener('click', () => {
  document.getElementById('modal-add-team-member').classList.add('hidden');
});
document.getElementById('btn-confirm-team-member').addEventListener('click', async () => {
  const d = _selectedTeamMemberData;
  if (!d) return _toast('请先搜索并选择用户', 'err');
  const body = d.gid
    ? { user_gid: d.gid }
    : { feishu_open_id: d.openId || '', name: d.name || '', email: d.email || '', avatar_url: d.avatar || '' };
  const res = await api(`/teams/${_selectedTeamGid}/members`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
  if (res?.success) {
    document.getElementById('modal-add-team-member').classList.add('hidden');
    _loadTeamMembers(_selectedTeamGid);
  }
});


// ══════════════════════════════════════════════════════════════
// Tab 2 — 项目成员
// ══════════════════════════════════════════════════════════════

// ── 子标签切换 ─────────────────────────────────────────────────
document.querySelectorAll('.pm-subtab').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.pm-subtab').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    const view = btn.dataset.view;
    document.querySelectorAll('.pm-view').forEach(v => {
      v.classList.remove('active');
      v.classList.add('hidden');
    });
    const el = document.getElementById(`pm-view-${view}`);
    if (el) { el.classList.remove('hidden'); el.classList.add('active'); }
  });
});

// ── 状态 ───────────────────────────────────────────────────────
let _selectedProjectGid = null;
let _projectBopLines    = [];
let _projectMembers     = [];
let _tsoTeamGids        = new Set();  // "总装" 子树 team gid
let _tsoUsers           = [];          // 总装子树用户列表

// 计算"总装"子树
function _computeTsoSubtree() {
  const root = _allTeams.find(t => t.name === '总装');
  if (!root) { _tsoTeamGids = new Set(); _tsoUsers = []; return; }
  _tsoTeamGids = new Set();
  const queue = [root.gid];
  while (queue.length) {
    const gid = queue.shift();
    _tsoTeamGids.add(gid);
    _allTeams.filter(t => t.parent_team_gid === gid).forEach(t => queue.push(t.gid));
  }
  _tsoUsers = _allUsers.filter(u => _tsoTeamGids.has(u.team_id));
}

async function loadProjects() {
  // 确保 teams/users 已加载（供 person picker 使用）
  if (!_allTeams.length || !_allUsers.length) {
    const [teamsRes, usersRes] = await Promise.all([
      api('/api/org/teams'),
      api('/api/users/'),
    ]);
    _allTeams = Array.isArray(teamsRes) ? teamsRes : (teamsRes?.data || []);
    if (usersRes?.data) _allUsers = usersRes.data;
  }
  _computeTsoSubtree();

  const res = await api('/api/projects');
  _allProjects = res?.data || [];
  const sel = document.getElementById('filter-project');
  sel.innerHTML = '<option value="">— 选择项目 —</option>';
  _allProjects.forEach(p => {
    const opt = document.createElement('option');
    opt.value = p.gid;
    opt.textContent = p.name;
    sel.appendChild(opt);
  });
}

document.getElementById('filter-project').addEventListener('change', async function() {
  const gid = this.value;
  if (!gid) {
    _selectedProjectGid = null;
    document.getElementById('pm-config-body').innerHTML = '<div class="empty-hint">请在上方选择项目</div>';
    return;
  }
  await _loadProjectConfig(gid);
});

// ── 项目配置视图 ───────────────────────────────────────────────

async function _loadProjectConfig(projectGid) {
  _selectedProjectGid = projectGid;
  const body = document.getElementById('pm-config-body');
  body.innerHTML = '<div class="empty-hint">加载中…</div>';

  // 确保 teams/users 已加载
  if (!_allTeams.length || !_allUsers.length) {
    const [teamsRes, usersRes] = await Promise.all([
      api('/api/org/teams'),
      api('/api/users/'),
    ]);
    _allTeams = Array.isArray(teamsRes) ? teamsRes : (teamsRes?.data || []);
    if (usersRes?.data) _allUsers = usersRes.data;
    _computeTsoSubtree();
  }

  const [linesRes, membersRes] = await Promise.all([
    api(`/api/projects/${projectGid}/bop-lines`),
    api(`/api/projects/${projectGid}/members`),
  ]);
  _projectBopLines  = linesRes?.data  || [];
  _projectMembers   = membersRes?.data || [];
  _renderProjectConfig();
}

function _getSlotUser(slot, sectionGid) {
  if (slot === 'project_owner') {
    return _projectMembers.find(m => m.project_role === 'project_manager') || null;
  }
  if (slot === 'section_lead') {
    return _projectMembers.find(m => m.scope_type === 'line' && m.scope_gid === sectionGid) || null;
  }
  return null;
}

function _renderProjectConfig() {
  const body = document.getElementById('pm-config-body');
  if (!_selectedProjectGid) {
    body.innerHTML = '<div class="empty-hint">请选择项目</div>';
    return;
  }

  let html = '<div class="pm-assign-list">';

  // 项目经理行
  const ownerUser = _getSlotUser('project_owner', null);
  html += _renderSlotRow('项目经理', 'project_owner', null, ownerUser);

  // 线体 Section Owner
  if (_projectBopLines.length) {
    html += '<div class="pm-lines-divider">线体 Section Owner</div>';
    _projectBopLines.forEach(line => {
      const lineUser = _getSlotUser('section_lead', line.gid);
      html += _renderSlotRow(line.title, 'section_lead', line.gid, lineUser);
    });
  } else {
    html += '<div class="pm-no-lines">该项目暂无 BOP 线体（可先在 BOP 模块建立线体）</div>';
  }

  html += '</div>';
  body.innerHTML = html;

  // 绑定点击
  body.querySelectorAll('.pm-slot-empty, .pm-slot-filled').forEach(el => {
    el.addEventListener('click', e => {
      e.stopPropagation();
      const row     = el.closest('[data-slot]');
      const slot    = row.dataset.slot;
      const section = row.dataset.section || null;
      _openPersonPicker(slot, section, el);
    });
  });
  body.querySelectorAll('.pm-slot-clear').forEach(el => {
    el.addEventListener('click', async e => {
      e.stopPropagation();
      const row     = el.closest('[data-slot]');
      const slot    = row.dataset.slot;
      const section = row.dataset.section || null;
      await _assignSlot(slot, section, null);
    });
  });
}

function _renderSlotRow(label, slot, sectionGid, user) {
  const dataAttrs = `data-slot="${slot}"${sectionGid ? ` data-section="${_esc(sectionGid)}"` : ''}`;
  let chip;
  if (user) {
    chip = `<div class="pm-slot-filled">
      ${user.avatar_url
        ? `<img src="${_esc(user.avatar_url)}" class="pm-slot-avatar" />`
        : `<div class="pm-slot-avatar pm-slot-avatar-ph"></div>`}
      <span class="pm-slot-name">${_esc(user.name || user.email)}</span>
      <button class="pm-slot-clear" title="清除">×</button>
    </div>`;
  } else {
    chip = `<div class="pm-slot-empty">点击选人…</div>`;
  }
  return `<div class="pm-slot-row" ${dataAttrs}>
    <span class="pm-slot-label">${_esc(label)}</span>
    ${chip}
  </div>`;
}

// ── Person Picker ─────────────────────────────────────────────

let _pickerEl      = null;
let _pickerSlot    = null;
let _pickerSection = null;

function _openPersonPicker(slot, sectionGid, anchorEl) {
  _closePersonPicker();
  _pickerSlot    = slot;
  _pickerSection = sectionGid;

  const picker = document.createElement('div');
  picker.className = 'pm-person-picker';
  _pickerEl = picker;

  const users = _tsoUsers.length ? _tsoUsers : _allUsers;

  picker.innerHTML = `
    <input type="text" class="pm-picker-input" placeholder="搜索姓名…" autocomplete="off" />
    <div class="pm-picker-list"></div>`;

  document.body.appendChild(picker);

  // 定位到锚点元素下方
  const rect = anchorEl.getBoundingClientRect();
  picker.style.cssText = `position:fixed;left:${rect.left}px;top:${rect.bottom + 4}px;z-index:600`;

  const input = picker.querySelector('.pm-picker-input');
  const list  = picker.querySelector('.pm-picker-list');

  function _renderList(q) {
    const filtered = users.filter(u =>
      !q || (u.name || '').includes(q) || (u.email || '').includes(q)
    ).slice(0, 30);

    if (!filtered.length) {
      list.innerHTML = '<div class="pm-picker-empty">无匹配用户</div>';
      return;
    }
    list.innerHTML = filtered.map(u => `
      <div class="pm-picker-item" data-gid="${_esc(u.gid)}">
        ${u.avatar_url
          ? `<img src="${_esc(u.avatar_url)}" class="pm-picker-item-avatar" />`
          : `<div class="pm-picker-item-avatar pm-picker-item-avatar-ph"></div>`}
        <span class="pm-picker-item-name">${_esc(u.name || u.email)}</span>
      </div>`).join('');

    list.querySelectorAll('.pm-picker-item').forEach(el => {
      el.addEventListener('mousedown', e => {
        e.preventDefault();
        _assignSlot(_pickerSlot, _pickerSection, el.dataset.gid);
        _closePersonPicker();
      });
    });
  }

  _renderList('');
  input.addEventListener('input', () => _renderList(input.value.trim()));
  setTimeout(() => input.focus(), 50);

  const dismiss = e => {
    if (!picker.contains(e.target)) {
      _closePersonPicker();
      document.removeEventListener('mousedown', dismiss);
    }
  };
  setTimeout(() => document.addEventListener('mousedown', dismiss), 10);
}

function _closePersonPicker() {
  if (_pickerEl) { _pickerEl.remove(); _pickerEl = null; }
}

async function _assignSlot(slot, sectionGid, userGid) {
  if (!_selectedProjectGid) return;
  const res = await api(`/api/projects/${_selectedProjectGid}/line-assignment`, {
    method: 'PUT',
    body: JSON.stringify({ line_gid: sectionGid || null, user_gid: userGid || null }),
  });
  if (res?.success) {
    const membersRes = await api(`/api/projects/${_selectedProjectGid}/members`);
    _projectMembers = membersRes?.data || [];
    _renderProjectConfig();
  } else {
    _toast(res?.detail || '操作失败', 'err');
  }
}

// ── 总览矩阵 ───────────────────────────────────────────────────

document.getElementById('btn-refresh-matrix').addEventListener('click', _loadMatrix);

async function _loadMatrix() {
  const wrap = document.getElementById('pm-matrix-wrap');
  wrap.innerHTML = '<div class="empty-hint">加载中…</div>';

  const res  = await api('/api/projects/members/matrix');
  const data = res?.data || [];

  if (!data.length) {
    wrap.innerHTML = '<div class="empty-hint">暂无项目成员数据</div>';
    return;
  }

  // 构建 user → project → [labels] 映射
  const userMap    = new Map();  // user_gid → {name, email, avatar_url}
  const projectMap = new Map();  // project_gid → project_name
  const cellMap    = new Map();  // "user_gid:project_gid" → [label, ...]

  data.forEach(r => {
    if (!userMap.has(r.user_gid)) {
      userMap.set(r.user_gid, { name: r.name, email: r.email, avatar_url: r.avatar_url });
    }
    if (!projectMap.has(r.project_gid)) {
      projectMap.set(r.project_gid, r.project_name);
    }
    const key = `${r.user_gid}:${r.project_gid}`;
    if (!cellMap.has(key)) cellMap.set(key, []);
    if (r.project_role === 'project_owner') {
      cellMap.get(key).push('项目经理');
    } else if (r.scope_type === 'line' && r.line_title) {
      cellMap.get(key).push(r.line_title);
    }
  });

  const projects = [...projectMap.entries()];
  const users    = [...userMap.entries()];

  let html = '<table class="pm-matrix-table"><thead><tr>';
  html += '<th class="pm-matrix-th-user">成员</th>';
  projects.forEach(([, pname]) => {
    html += `<th class="pm-matrix-th-proj">${_esc(pname)}</th>`;
  });
  html += '</tr></thead><tbody>';

  users.forEach(([ugid, uinfo]) => {
    html += '<tr>';
    html += `<td class="pm-matrix-td-user">
      <div style="display:flex;align-items:center;gap:6px">
        ${uinfo.avatar_url ? `<img src="${_esc(uinfo.avatar_url)}" class="pm-matrix-avatar" />` : ''}
        <span>${_esc(uinfo.name || uinfo.email)}</span>
      </div>
    </td>`;
    projects.forEach(([pgid]) => {
      const labels = cellMap.get(`${ugid}:${pgid}`) || [];
      html += `<td class="pm-matrix-td-cell">${labels.map(l => `<span class="pm-matrix-chip">${_esc(l)}</span>`).join('')}</td>`;
    });
    html += '</tr>';
  });

  html += '</tbody></table>';
  wrap.innerHTML = html;
}


// ── 工具函数 ──────────────────────────────────────────────────

function _esc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function _toast(msg, type) {
  const t = document.createElement('div');
  t.className = `sync-banner ${type === 'err' ? 'sync-err' : 'sync-ok'}`;
  t.style.cssText = 'position:fixed;bottom:20px;right:20px;z-index:9999;max-width:300px';
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 2500);
}

// ── 初始化 ────────────────────────────────────────────────────
loadStruct();
