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


async function invokeCapability(id, payload = {}, options = {}) {
  if (!window.AI00Business?.available()) throw new Error('云端服务未连接');
  const response = await window.AI00Business.request(id, {
    version: 1, payload,
    idempotency_key: options.idempotencyKey,
    expected_resource_version: options.expectedResourceVersion,
  });
  const envelope = response?.data;
  if (response?.success !== true || envelope?.ok !== true) {
    const detail = envelope?.error || response?.error || {};
    throw new Error(detail.message || `能力调用失败：${id}@1`);
  }
  const value = envelope.data;
  return value?.data !== undefined && Object.keys(value).length === 1 ? value.data : value;
}

async function _runResponsibilityAction(action) {
  try {
    return await action();
  } catch (error) {
    console.error('[org_mgmt] responsibility action failed:', error);
    _toast(error?.message || '操作失败，请重试', 'err');
    return null;
  }
}

async function _baseCall(operation, args = {}, options = {}) {
  const client = window.top?.AI00ExistingCapabilityClient || window.parent?.AI00ExistingCapabilityClient || window.AI00ExistingCapabilityClient;
  if (!client) return null;
  try { return await client.call(operation, args, options); }
  catch (e) {
    if (e?.code === 'capability_confirmation_cancelled') return { cancelled: true };
    console.warn('[org_mgmt] capability failed:', e.message);
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
    _baseCall('base.orgTeams.list'),
    _allUsers.length ? Promise.resolve({ data: _allUsers }) : _baseCall('base.users.list'),
  ]);
  _allTeams = Array.isArray(teamsRes) ? teamsRes : (teamsRes?.data || []);
  if (usersRes?.data) _allUsers = usersRes.data;
  _renderStructTree();
}

// ── 展开状态（gid set） ────────────────────────────────────────
let _expandedTeams = new Set();
let _feishuFolded = true;  // 飞书组织默认折叠

function _renderStructTree() {
  const body = document.getElementById('struct-tree-body');

  // 所有已有节点统一进入一棵树；来源不再决定维护方式。
  const knownTeamGids = new Set(_allTeams.map(team => team.gid));
  let manualTeams = _allTeams.filter(team => !team.parent_team_gid || !knownTeamGids.has(team.parent_team_gid) || team.parent_team_gid === team.gid);
  if (!manualTeams.length) manualTeams = [..._allTeams]; // cycle-safe fallback
  const feishuTeams = _allTeams;

  // 飞书组织按层级构建
  const feishuChildMap = {};
  feishuTeams.forEach(t => {
    const pid = t.parent_team_gid && t.parent_team_gid !== t.gid ? t.parent_team_gid : '__root__';
    if (!feishuChildMap[pid]) feishuChildMap[pid] = [];
    feishuChildMap[pid].push(t);
  });
  Object.values(feishuChildMap).forEach(arr => arr.sort((a, b) => a.name.localeCompare(b.name, 'zh')));

  // 手动团队按名称排序
  manualTeams.sort((a, b) => a.name.localeCompare(b.name, 'zh'));

  let html = '';

  // ── 手动团队区域 ──────────────────────────────────────────────
  html += `<div class="st-section-hdr">
    <span>全部组织</span>
    <span class="st-section-cnt">${_allTeams.length}</span>
    <button class="st-section-add-btn" id="stManualAddBtn" title="新建团队">＋</button>
  </div>`;
  // 内联添加输入框（默认隐藏）
  html += `<div class="st-inline-add" id="stManualAddRow" style="display:none">
    <input type="text" id="stManualAddInp" placeholder="输入团队名称…" autocomplete="off" />
    <select id="stManualAddParent" title="上级组织">${_parentOptionsHtml()}</select>
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
    const parentTeamGid = document.getElementById('stManualAddParent').value || null;
    try {
      const res = await window.AI00Business.invoke('base.team.create', {
        version: 1, payload: { name, parent_team_gid: parentTeamGid },
      });
      if (!res?.success) throw new Error(res?.detail || '创建失败');
      _toast('团队已创建');
      addRow.style.display = 'none'; addInp.value = '';
      if (parentTeamGid) _expandedTeams.add(parentTeamGid);
      await loadStruct();
    } catch (error) {
      _toast(error?.message || '创建失败，请重试', 'err');
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
  // 飞书仅用于添加人员时搜索，不再提供整树同步入口。

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
  });
}

function _descendantTeamGids(gid) {
  const excluded = new Set(gid ? [gid] : []);
  let changed = true;
  while (changed) {
    changed = false;
    _allTeams.forEach(team => {
      if (excluded.has(team.parent_team_gid) && !excluded.has(team.gid)) {
        excluded.add(team.gid);
        changed = true;
      }
    });
  }
  return excluded;
}

function _parentOptionsHtml(selectedGid = '', excludedGid = null) {
  const excluded = _descendantTeamGids(excludedGid);
  const options = _allTeams
    .filter(team => !excluded.has(team.gid))
    .sort((a, b) => a.name.localeCompare(b.name, 'zh'))
    .map(team => `<option value="${_esc(team.gid)}"${team.gid === selectedGid ? ' selected' : ''}>${_esc(team.name)}</option>`)
    .join('');
  return `<option value=""${selectedGid ? '' : ' selected'}>无上级（一级组织）</option>${options}`;
}

function _renderNodeHtml(team, depth, childMap, ancestors = new Set()) {
  if (ancestors.has(team.gid)) return '';
  const branch = new Set(ancestors); branch.add(team.gid);
  const children = (childMap[team.gid] || []).filter(child => !branch.has(child.gid));
  const hasChildren = children.length > 0;
  const isExpanded = _expandedTeams.has(team.gid);
  const isSelected = _selectedTeamGid === team.gid;
  const indent = depth * 16 + 10;
  const isFeishu = false;

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
    children.forEach(child => { html += _renderNodeHtml(child, depth + 1, childMap, branch); });
  }
  return html;
}

async function _loadTeamDetail(gid) {
  const team = _allTeams.find(t => t.gid === gid);
  if (!team) return;

  document.getElementById('struct-detail-empty').classList.add('hidden');
  document.getElementById('struct-detail-form').classList.remove('hidden');

  document.getElementById('struct-name-input').value = team.name;
  document.getElementById('struct-parent-select').innerHTML = _parentOptionsHtml(team.parent_team_gid || '', team.gid);

  const badge = document.getElementById('struct-type-badge');
  badge.textContent = '人工维护';
  badge.className = 'struct-type-badge badge-small';

  await _loadTeamMembers(gid);
}

async function _loadTeamMembers(gid) {
  // 先刷新 _allUsers 缓存，确保新添加的成员可用
  try {
    const usersRes = await _baseCall('base.users.list');
    if (usersRes?.data) _allUsers = usersRes.data;
  } catch {}
  const res = await (async (body,path,query) => { const result = await window.AI00Business.invoke("base.team.member.list", {version:1,payload:({team_gid:path.gid})}); return result; })({},{"gid":decodeURIComponent(String(gid))},new URLSearchParams());
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
  const res = await (async (body,path,query) => { const result = await window.AI00Business.invoke("base.team.member.remove", {version:1,payload:({team_gid:path.gid,user_gid:path.user_gid})}); return result; })({},{"gid":decodeURIComponent(String(teamGid)),"user_gid":decodeURIComponent(String(userGid))},new URLSearchParams());
  if (res?.success) _loadTeamMembers(teamGid);
};

// 保存团队名称和上级组织
document.getElementById('struct-save-btn').addEventListener('click', async () => {
  if (!_selectedTeamGid) return;
  const team = _allTeams.find(t => t.gid === _selectedTeamGid);
  if (!team) return;
  const newName = document.getElementById('struct-name-input').value.trim();
  if (!newName) return _toast('团队名称不能为空', 'err');
  const newParentTeamGid = document.getElementById('struct-parent-select').value || null;
  const changes = {};
  if (newName !== team.name) changes.name = newName;
  if (newParentTeamGid !== (team.parent_team_gid || null)) changes.parent_team_gid = newParentTeamGid;
  if (!Object.keys(changes).length) return _toast('未做任何修改');
  try {
    const res = await window.AI00Business.invoke('base.team.update', {
      version: 1, payload: { team_gid: _selectedTeamGid, changes },
    });
    if (!res?.success) throw new Error(res?.detail || '保存失败');
    Object.assign(team, changes);
    if (newParentTeamGid) _expandedTeams.add(newParentTeamGid);
    _toast('保存成功');
    _renderStructTree();
  } catch (error) {
    _toast(error?.message || '保存失败，请重试', 'err');
  }
});

// 删除团队
document.getElementById('struct-delete-btn').addEventListener('click', async () => {
  if (!_selectedTeamGid) return;
  if (!confirm('确定删除该团队？此操作不可恢复。')) return;
  const res = await (async (body,path,query) => { const result = await window.AI00Business.invoke("base.team.archive", {version:1,payload:({team_gid:path.gid})}); return result; })({},{"gid":decodeURIComponent(String(_selectedTeamGid))},new URLSearchParams());
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

  const res = await _baseCall('base.users.assignRole', {
    userGid: _editingUserId, newRole, externalSubtype: body.external_subtype || null,
  }, {
    confirm: () => window.confirm(`确认将该成员的角色修改为「${newRole}」？`),
  });
  if (res?.cancelled) return;
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
    const res = await (async (body,path,query) => { const result = await window.AI00Business.invoke("base.feishu.organization_user.search", {version:1,payload:({query:query.get("q")||""})}); return result; })({},{},new URLSearchParams((`/feishu/org/users/search?q=${encodeURIComponent(q)}`).split("?")[1]||""));
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
  const res = await (async (body,path,query) => { const result = await window.AI00Business.invoke("base.team.member.add", {version:1,payload:({team_gid:path.gid,member:body})}); return result; })(body,{"gid":decodeURIComponent(String(_selectedTeamGid))},new URLSearchParams());
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
      _baseCall('base.orgTeams.list'),
      _baseCall('base.users.list'),
    ]);
    _allTeams = Array.isArray(teamsRes) ? teamsRes : (teamsRes?.data || []);
    if (usersRes?.data) _allUsers = usersRes.data;
  }
  _computeTsoSubtree();

  const value = await invokeCapability('project.project.read.atomic.projects_search', { arguments: {} }).catch(() => []);
  _allProjects = Array.isArray(value) ? value : (value?.data || value?.projects || []);
}

// ── 项目配置视图 ───────────────────────────────────────────────

async function _loadProjectConfig(projectGid) {
  _selectedProjectGid = projectGid;
  const body = document.getElementById('pm-config-body');
  body.innerHTML = '<div class="empty-hint">加载中…</div>';

  // 确保 teams/users 已加载
  if (!_allTeams.length || !_allUsers.length) {
    const [teamsRes, usersRes] = await Promise.all([
      _baseCall('base.orgTeams.list'),
      _baseCall('base.users.list'),
    ]);
    _allTeams = Array.isArray(teamsRes) ? teamsRes : (teamsRes?.data || []);
    if (usersRes?.data) _allUsers = usersRes.data;
    _computeTsoSubtree();
  }

  const [linesRes, membersRes] = await Promise.all([
    invokeCapability('craft.bop.entry.legacy_read', {
      operation: 'project_bop_lines', project_gid: projectGid, limit: 500,
    }).catch(() => []),
    invokeCapability('project.member.read', {
      arguments: { operation: 'members.list', arguments: { project_gid: projectGid } },
    }).catch(() => []),
  ]);
  _projectBopLines  = Array.isArray(linesRes) ? linesRes : (linesRes?.data || linesRes?.items || []);
  _projectMembers   = Array.isArray(membersRes) ? membersRes : (membersRes?.data || membersRes?.members || []);
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
  const res = await invokeCapability('project.member.change.apply', {
    operation: 'members.line_assignment.replace',
    arguments: {
      project_gid: _selectedProjectGid,
      line_gid: sectionGid || null,
      user_gid: userGid || null,
    },
  });
  if (res?.success || res === true) {
    const membersRes = await invokeCapability('project.member.read', {
      arguments: { operation: 'members.list', arguments: { project_gid: _selectedProjectGid } },
    });
    _projectMembers = Array.isArray(membersRes)
      ? membersRes
      : (membersRes?.data || membersRes?.items || membersRes?.members || []);
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

  // Compose the matrix from governed project/member/line capabilities.  The
  // former aggregate REST endpoint is only a compatibility projection and
  // cannot be called from a capability-only consumer.
  const projectCatalog = _allProjects.length
    ? _allProjects
    : await invokeCapability('project.project.read.atomic.projects_search', { arguments: {} })
      .then(value => Array.isArray(value) ? value : (value?.data || value?.projects || []))
      .catch(() => []);
  const projectRows = await Promise.all(projectCatalog.map(async project => {
    const [members, lines] = await Promise.all([
      invokeCapability('project.member.read', {
        arguments: { operation: 'members.list', arguments: { project_gid: project.gid } },
      }).catch(() => []),
      invokeCapability('craft.bop.entry.legacy_read', {
        operation: 'project_bop_lines', project_gid: project.gid, limit: 500,
      }).catch(() => []),
    ]);
    const memberRows = Array.isArray(members) ? members : (members?.data || members?.members || []);
    const lineRows = Array.isArray(lines) ? lines : (lines?.data || lines?.items || []);
    const lineTitles = new Map(lineRows.map(line => [line.gid, line.title || line.name || line.code || line.gid]));
    return memberRows.map(member => ({
      ...member,
      project_name: project.name,
      project_role: member.project_role || member.role,
      line_title: lineTitles.get(member.scope_gid) || member.line_title || '',
    }));
  }));
  const data = projectRows.flat();

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


// ── 人工项目责任树（覆盖旧的自动 BOP 单人槽位实现）────────────
let _responsibilityProjects = [];
const _expandedResponsibilityProjects = new Set();

async function _loadAllResponsibilityProjects() {
  const projectValue = await invokeCapability('project.project.read.atomic.projects_search', { arguments: {} });
  const projects = Array.isArray(projectValue)
    ? projectValue
    : (projectValue?.items || projectValue?.projects || projectValue?.data || []);
  const configured = [];
  let cursor = null;
  do {
    const page = await invokeCapability('project.org_management.read', {
      operation: 'responsibility_tree.search',
      arguments: { project_gid: null, cursor, page_size: 100, operation_gid: null },
    });
    configured.push(...(page?.items || []));
    cursor = page?.next_cursor || null;
  } while (cursor);
  const configuredByGid = new Map(configured.map(item => [String(item.gid), item]));
  return projects.map(project => {
    const state = configuredByGid.get(String(project.gid));
    return {
      ...project,
      revision: state?.revision || 0,
      lines: state?.lines || [],
      managerState: { project_gid: project.gid, revision: 0, managed: false, managers: [] },
      members: [],
      bopLines: [],
      detailsLoaded: false,
      detailsLoading: false,
      detailsError: '',
    };
  });
}

async function _loadResponsibilityBopLines(projectGid) {
  const values = [];
  let cursor = null;
  do {
    const page = await invokeCapability('craft.bop.active_line.search', {
      project_gid: projectGid, cursor, page_size: 100,
    });
    values.push(...(page?.items || []));
    cursor = page?.next_cursor || null;
  } while (cursor);
  return values;
}

async function _loadResponsibilityProjectDetails(project) {
  if (!project || project.detailsLoaded || project.detailsLoading) return;
  project.detailsLoading = true;
  project.detailsError = '';
  _renderProjectConfig();
  try {
    const [managerState, memberData, bopLines, usersRes] = await Promise.all([
      invokeCapability('base.project_manager.read', { project_gid: project.gid }),
      invokeCapability('project.member.read', {
        operation: 'members.list', arguments: { project_gid: project.gid },
      }),
      project.lines.length ? _loadResponsibilityBopLines(project.gid) : Promise.resolve([]),
      _allUsers.length ? Promise.resolve(null) : _baseCall('base.users.list'),
    ]);
    if (usersRes?.data) _allUsers = usersRes.data;
    project.managerState = managerState || project.managerState;
    project.members = Array.isArray(memberData)
      ? memberData
      : (memberData?.data || memberData?.items || memberData?.members || []);
    project.bopLines = bopLines;
    project.detailsLoaded = true;
  } catch (error) {
    project.detailsError = error?.message || '详情加载失败';
  } finally {
    project.detailsLoading = false;
    _renderProjectConfig();
  }
}

async function _toggleResponsibilityProject(projectGid) {
  const project = _responsibilityProjects.find(item => String(item.gid) === String(projectGid));
  if (!project) return;
  if (_expandedResponsibilityProjects.has(String(project.gid))) {
    _expandedResponsibilityProjects.delete(String(project.gid));
    _renderProjectConfig();
    return;
  }
  _expandedResponsibilityProjects.clear();
  _expandedResponsibilityProjects.add(String(project.gid));
  _renderProjectConfig();
  await _loadResponsibilityProjectDetails(project);
}

async function loadProjects() {
  const body = document.getElementById('pm-config-body');
  body.innerHTML = '<div class="empty-hint">加载全部项目责任树…</div>';
  try {
    _responsibilityProjects = await _loadAllResponsibilityProjects();
  } catch (error) {
    body.innerHTML = `<div class="empty-hint pm-load-error">项目加载失败：${_esc(error.message)}<br><button class="btn-ghost btn-sm" data-retry-projects>重试</button></div>`;
    body.querySelector('[data-retry-projects]')?.addEventListener('click', loadProjects);
    return;
  }
  const matrixFilter = document.getElementById('matrix-project-filter');
  const selected = matrixFilter.value;
  matrixFilter.innerHTML = '<option value="">全部项目</option>' + _responsibilityProjects
    .map(project => `<option value="${_esc(project.gid)}">${_esc(project.name)}</option>`).join('');
  matrixFilter.value = selected;
  _renderProjectConfig();
  const expandedProject = _responsibilityProjects.find(project => _expandedResponsibilityProjects.has(String(project.gid)));
  if (expandedProject) await _loadResponsibilityProjectDetails(expandedProject);
}

function _person(gid) {
  return _allUsers.find(user => user.gid === gid) || { gid, name: gid, avatar_url: '' };
}

function _personChips(gids) {
  if (!gids?.length) return '<span class="pm-empty-value">未设置</span>';
  return gids.map(gid => `<span class="pm-person-chip">${_esc(_person(gid).name || gid)}</span>`).join('');
}

function _removablePersonChips(gids, attributes) {
  if (!gids?.length) return '<span class="pm-empty-value">未设置</span>';
  return gids.map(gid => `<span class="pm-person-chip">${_esc(_person(gid).name || gid)}<button type="button" title="移除" ${attributes(gid)}>×</button></span>`).join('');
}

function _renderProjectConfig() {
  const body = document.getElementById('pm-config-body');
  if (!_responsibilityProjects.length) {
    body.innerHTML = '<div class="empty-hint">暂无项目</div>';
    return;
  }
  body.innerHTML = `<div class="pm-project-tree">${_responsibilityProjects.map(project => {
    const managers = project.managerState?.managers || [];
    const members = (project.members || []).filter(item => item.role === 'member');
    const expanded = _expandedResponsibilityProjects.has(String(project.gid));
    const summary = project.detailsLoaded
      ? `<span class="pm-summary-chip">经理 ${managers.length}</span><span class="pm-summary-chip">成员 ${members.length}</span>`
      : '<span class="pm-summary-chip pm-summary-pending">详情按需加载</span>';
    return `<section class="pm-project-node" data-project="${_esc(project.gid)}">
      <header class="pm-project-header">
        <button type="button" class="pm-project-toggle" data-toggle-project="${_esc(project.gid)}" aria-expanded="${expanded}">
          <span class="pm-tree-caret">${expanded ? '▼' : '▶'}</span><strong>${_esc(project.name)}</strong>
          <span class="pm-project-summary">${summary}<span class="pm-summary-chip">人工线体 ${project.lines?.length || 0}</span></span>
        </button><span class="pm-revision">r${project.revision || 0}</span>
      </header>
      ${!expanded ? '' : project.detailsLoading
        ? '<div class="pm-project-detail-state">正在加载项目详情…</div>'
        : project.detailsError
          ? `<div class="pm-project-detail-state pm-load-error">详情加载失败：${_esc(project.detailsError)} <button class="btn-ghost btn-sm" data-retry-project-detail="${_esc(project.gid)}">重试</button></div>`
          : `<div class="pm-project-detail-grid"><div class="pm-manager-node">
        <div class="pm-node-title"><span>项目经理（${managers.length}）</span>
          <button class="btn-ghost btn-sm" data-add-manager="${_esc(project.gid)}">＋ 添加经理</button></div>
        <div class="pm-chip-list">${_removablePersonChips(managers.map(item => item.gid), gid => `data-project="${_esc(project.gid)}" data-remove-manager="${_esc(gid)}"`)}</div>
      </div>
      <div class="pm-manager-node pm-members-node">
        <div class="pm-node-title"><span>项目成员（${members.length}）</span>
          <button class="btn-ghost btn-sm" data-add-member="${_esc(project.gid)}">＋ 添加成员</button></div>
        <div class="pm-chip-list">${members.map(item => `<span class="pm-person-chip">${_esc(item.name || item.email || item.user_gid)}<button type="button" title="移除" data-project="${_esc(project.gid)}" data-remove-member="${_esc(item.gid)}">×</button></span>`).join('') || '<span class="pm-empty-value">未设置</span>'}</div>
      </div>
      <div class="pm-lines-node">
        <div class="pm-node-title"><span>人工线体（${project.lines?.length || 0}）</span>
          <button class="btn-ghost btn-sm" data-add-line="${_esc(project.gid)}">＋ 新增线体</button></div>
        ${(project.lines || []).map(line => _manualLineHtml(project, line)).join('') || '<div class="pm-no-lines">暂无人工线体</div>'}
      </div></div>`}
    </section>`;
  }).join('')}</div>`;
  body.querySelectorAll('[data-toggle-project]').forEach(button => button.addEventListener('click', () => _toggleResponsibilityProject(button.dataset.toggleProject)));
  body.querySelectorAll('[data-retry-project-detail]').forEach(button => button.addEventListener('click', () => {
    const project = _responsibilityProjects.find(item => String(item.gid) === String(button.dataset.retryProjectDetail));
    _loadResponsibilityProjectDetails(project);
  }));
  body.querySelectorAll('[data-add-manager]').forEach(button => button.addEventListener('click', () => _openProjectPersonPicker({ type: 'manager', projectGid: button.dataset.addManager })));
  body.querySelectorAll('[data-remove-manager]').forEach(button => button.addEventListener('click', () => _runResponsibilityAction(() => _removeManager(button.dataset.project, button.dataset.removeManager))));
  body.querySelectorAll('[data-add-member]').forEach(button => button.addEventListener('click', () => _openProjectPersonPicker({ type: 'member', projectGid: button.dataset.addMember })));
  body.querySelectorAll('[data-remove-member]').forEach(button => button.addEventListener('click', () => _runResponsibilityAction(() => _removeProjectMember(button.dataset.project, button.dataset.removeMember))));
  body.querySelectorAll('[data-add-line]').forEach(button => button.addEventListener('click', () => _runResponsibilityAction(() => _createManualLine(button.dataset.addLine))));
  body.querySelectorAll('[data-edit-line]').forEach(button => button.addEventListener('click', () => _runResponsibilityAction(() => _editManualLine(button.dataset.project, button.dataset.editLine))));
  body.querySelectorAll('[data-add-line-leader]').forEach(button => button.addEventListener('click', () => _openProjectPersonPicker({ type: 'line', projectGid: button.dataset.project, lineGid: button.dataset.addLineLeader })));
  body.querySelectorAll('[data-remove-line-leader]').forEach(button => button.addEventListener('click', () => _runResponsibilityAction(() => _removeLineLeader(button.dataset.project, button.dataset.line, button.dataset.removeLineLeader))));
  body.querySelectorAll('[data-delete-line]').forEach(button => button.addEventListener('click', () => _runResponsibilityAction(() => _deleteManualLine(button.dataset.project, button.dataset.deleteLine))));
  body.querySelectorAll('[data-map-line]').forEach(select => select.addEventListener('change', () => _runResponsibilityAction(() => _mapManualLine(select.dataset.project, select.dataset.mapLine, select.value || null))));
}

function _manualLineHtml(project, line) {
  const options = (project.bopLines || []).map(item => `<option value="${_esc(item.gid)}" ${item.gid === line.bop_line_gid ? 'selected' : ''}>${_esc(item.path || item.title)}</option>`).join('');
  return `<div class="pm-manual-line" data-line="${_esc(line.gid)}">
    <div class="pm-line-main"><span class="pm-tree-branch">└</span><strong>${_esc(line.name)}</strong>
      <span class="pm-chip-list">${_removablePersonChips(line.leader_user_gids, gid => `data-project="${_esc(project.gid)}" data-line="${_esc(line.gid)}" data-remove-line-leader="${_esc(gid)}"`)}</span></div>
    <div class="pm-line-actions">
      <select class="form-select pm-bop-select" data-project="${_esc(project.gid)}" data-map-line="${_esc(line.gid)}">
        <option value="">未映射 BOP 节点</option>${options}</select>
      <button class="btn-ghost btn-sm" data-project="${_esc(project.gid)}" data-add-line-leader="${_esc(line.gid)}">＋ 添加负责人</button>
      <button class="btn-ghost btn-sm" data-project="${_esc(project.gid)}" data-edit-line="${_esc(line.gid)}">编辑名称</button>
      <button class="btn-danger-sm" data-project="${_esc(project.gid)}" data-delete-line="${_esc(line.gid)}">删除</button>
    </div>
  </div>`;
}

function _promptPeople(currentGids) {
  const current = (currentGids || []).map(gid => _person(gid).name || gid).join('、');
  const value = prompt('输入负责人姓名或 GID，多个用逗号分隔；清空即移除全部负责人', current);
  if (value === null) return null;
  const tokens = value.split(/[，,、]/).map(item => item.trim()).filter(Boolean);
  const gids = tokens.map(token => _allUsers.find(user => user.gid === token || user.name === token)?.gid || token);
  return [...new Set(gids)].slice(0, 50);
}

async function _editManagers(projectGid) {
  const project = _responsibilityProjects.find(item => item.gid === projectGid);
  const gids = _promptPeople((project.managerState?.managers || []).map(item => item.gid));
  if (gids === null) return;
  const revision = project.managerState?.revision || 0;
  const idempotencyKey = crypto.randomUUID();
  await invokeCapability('base.project_manager.replace', { project_gid: projectGid, user_gids: gids,
    expected_revision: revision, idempotency_key: idempotencyKey }, { idempotencyKey });
  await loadProjects();
}

let _projectPersonTarget = null;
let _selectedProjectPerson = null;
const _projectPersonSearch = _makeUserSearchWidget({
  inputId: 'search-project-person-input',
  resultsId: 'search-project-person-results',
  selectedId: 'search-project-person-selected',
  onSelect: value => { _selectedProjectPerson = value; },
});

function _openProjectPersonPicker(target) {
  _projectPersonTarget = target;
  _selectedProjectPerson = null;
  _projectPersonSearch.reset();
  const labels = { manager: '添加项目经理', member: '添加项目成员', line: '添加线体负责人' };
  document.getElementById('project-person-title').textContent = labels[target.type];
  document.getElementById('modal-project-person').classList.remove('hidden');
  setTimeout(() => document.getElementById('search-project-person-input').focus(), 50);
}

function _closeProjectPersonPicker() {
  document.getElementById('modal-project-person').classList.add('hidden');
}

document.getElementById('btn-close-project-person').addEventListener('click', _closeProjectPersonPicker);
document.getElementById('btn-cancel-project-person').addEventListener('click', _closeProjectPersonPicker);
document.getElementById('btn-confirm-project-person').addEventListener('click', async () => {
  const person = _selectedProjectPerson;
  const target = _projectPersonTarget;
  if (!person?.gid) return _toast('请选择已注册的飞书用户；新用户请先加入组织架构', 'err');
  const project = _responsibilityProjects.find(item => item.gid === target.projectGid);
  const button = document.getElementById('btn-confirm-project-person');
  button.disabled = true;
  const completed = await _runResponsibilityAction(async () => {
    if (target.type === 'manager') {
      const gids = [...new Set([...(project.managerState?.managers || []).map(item => item.gid), person.gid])];
      await _replaceManagers(project, gids);
    } else if (target.type === 'member') {
      await invokeCapability('project.member.change.apply', {
        operation: 'members.add', arguments: { project_gid: project.gid, user_gid: person.gid, project_role: 'member' },
      });
      await loadProjects();
    } else {
      const line = project.lines.find(item => item.gid === target.lineGid);
      await _changeLine(project, 'managed_line.update', {
        line_gid: line.gid, leader_user_gids: [...new Set([...line.leader_user_gids, person.gid])],
      });
    }
    return true;
  });
  button.disabled = false;
  if (completed) _closeProjectPersonPicker();
});

async function _replaceManagers(project, gids) {
  const idempotencyKey = crypto.randomUUID();
  await invokeCapability('base.project_manager.replace', {
    project_gid: project.gid, user_gids: gids, expected_revision: project.managerState?.revision || 0,
    idempotency_key: idempotencyKey,
  }, { idempotencyKey });
  await loadProjects();
}

async function _removeManager(projectGid, userGid) {
  const project = _responsibilityProjects.find(item => item.gid === projectGid);
  await _replaceManagers(project, (project.managerState?.managers || []).map(item => item.gid).filter(gid => gid !== userGid));
}

async function _removeProjectMember(projectGid, memberGid) {
  await invokeCapability('project.member.change.apply', {
    operation: 'members.remove', arguments: { project_gid: projectGid, member_gid: memberGid },
  });
  await loadProjects();
}

async function _removeLineLeader(projectGid, lineGid, userGid) {
  const project = _responsibilityProjects.find(item => item.gid === projectGid);
  const line = project.lines.find(item => item.gid === lineGid);
  await _changeLine(project, 'managed_line.update', {
    line_gid: line.gid, leader_user_gids: line.leader_user_gids.filter(gid => gid !== userGid),
  });
}

async function _changeLine(project, operation, changeArguments) {
  const idempotencyKey = crypto.randomUUID();
  const result = await invokeCapability('project.org_management.change.apply', { operation,
    arguments: { project_gid: project.gid, ...changeArguments }, expected_revision: project.revision || 0,
    idempotency_key: idempotencyKey }, {
      idempotencyKey, expectedResourceVersion: String(project.revision || 0),
    });
  _toast(result?.status === 'pending_projection' ? '已保存，BOP 权限正在同步' : '已保存');
  await loadProjects();
}

async function _createManualLine(projectGid) {
  const project = _responsibilityProjects.find(item => item.gid === projectGid);
  const name = prompt('新线体名称');
  if (!name?.trim()) return;
  await _changeLine(project, 'managed_line.create', { name: name.trim(), leader_user_gids: [], bop_line_gid: null });
}

async function _editManualLine(projectGid, lineGid) {
  const project = _responsibilityProjects.find(item => item.gid === projectGid);
  const line = project.lines.find(item => item.gid === lineGid);
  const name = prompt('线体名称', line.name);
  if (name === null || !name.trim()) return;
  await _changeLine(project, 'managed_line.update', { line_gid: lineGid, name: name.trim() });
}

async function _mapManualLine(projectGid, lineGid, bopLineGid) {
  const project = _responsibilityProjects.find(item => item.gid === projectGid);
  await _changeLine(project, 'managed_line.update', { line_gid: lineGid, bop_line_gid: bopLineGid });
}

async function _deleteManualLine(projectGid, lineGid) {
  if (!confirm('确定删除这条人工线体及其责任映射？')) return;
  const project = _responsibilityProjects.find(item => item.gid === projectGid);
  await _changeLine(project, 'managed_line.delete', { line_gid: lineGid });
}

async function _loadMatrix() {
  if (!_responsibilityProjects.length) _responsibilityProjects = await _loadAllResponsibilityProjects();
  const selectedProject = document.getElementById('matrix-project-filter')?.value || '';
  const visibleProjects = selectedProject
    ? _responsibilityProjects.filter(project => project.gid === selectedProject)
    : _responsibilityProjects;
  const people = new Map();
  visibleProjects.forEach(project => {
    (project.managerState?.managers || []).forEach(person => people.set(person.gid, person));
    (project.members || []).filter(item => item.role === 'member').forEach(item => people.set(item.user_gid, {
      gid: item.user_gid, name: item.name || item.email || item.user_gid, avatar_url: item.avatar_url || '',
    }));
    (project.lines || []).forEach(line => line.leader_user_gids.forEach(gid => people.set(gid, _person(gid))));
  });
  const wrap = document.getElementById('pm-matrix-wrap');
  if (!people.size) { wrap.innerHTML = '<div class="empty-hint">暂无责任人数据</div>'; return; }
  wrap.innerHTML = `<table class="pm-matrix-table"><thead><tr><th class="pm-matrix-th-user">责任人</th>${visibleProjects.map(p => `<th>${_esc(p.name)}</th>`).join('')}</tr></thead><tbody>
    ${[...people.values()].map(person => `<tr><td class="pm-matrix-td-user">${_esc(person.name || person.gid)}</td>${visibleProjects.map(project => {
      const labels = [];
      if ((project.managerState?.managers || []).some(item => item.gid === person.gid)) labels.push('项目经理');
      if ((project.members || []).some(item => item.role === 'member' && item.user_gid === person.gid)) labels.push('项目成员');
      (project.lines || []).filter(line => line.leader_user_gids.includes(person.gid)).forEach(line => labels.push(line.name));
      return `<td>${labels.map(label => `<span class="pm-matrix-chip">${_esc(label)}</span>`).join('')}</td>`;
    }).join('')}</tr>`).join('')}</tbody></table>`;
  }

document.getElementById('matrix-project-filter')?.addEventListener('change', _loadMatrix);


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
