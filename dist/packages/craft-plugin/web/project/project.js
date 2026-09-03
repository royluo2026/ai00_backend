// ===================== 项目管理前端逻辑 =====================
// 使用 _cloudFetch 直接调用云端 REST API

let _projects = [];          // 当前项目列表缓存
let _selectedProject = null; // 当前选中的项目
let _editingGid = null;       // 编辑中的项目 GID（null 表示新建）
let _vehicleModels = [];      // 车型列表缓存
let _factories = [];          // 工厂列表缓存

// ── Capability Gateway 封装 ───────────────────────────────
function _cloudFetchFn() {
  return window.parent?._cloudFetch || window._cloudFetch;
}
async function invokeCapability(id, payload = {}) {
  const _cloudFetch = _cloudFetchFn();
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

async function apiCapability(id, argumentsValue = {}) {
  return invokeCapability(id, { arguments: argumentsValue });
}

// ── 主题同步 ──────────────────────────────────────────────
window.addEventListener('message', e => {
  if (e.data?.type === 'theme') {
    document.documentElement.setAttribute('data-theme', e.data.theme);
    localStorage.setItem('system.theme', e.data.theme);
  }
});
(function applyTheme() {
  const t = localStorage.getItem('system.theme') || 'dark';
  document.documentElement.setAttribute('data-theme', t);
})();

// ── 状态徽章 ──────────────────────────────────────────────
const STATUS_LABELS = {
  preparing:   '筹备中',
  in_progress: '进行中',
  completed:   '已完成',
  archived:    '已归档',
};
function statusBadge(status) {
  const label = STATUS_LABELS[status] || status;
  return `<span class="status-badge status-${status}">${label}</span>`;
}

// ── 渲染项目列表 ──────────────────────────────────────────
function renderProjects(list) {
  const container = document.getElementById('projectList');
  const empty     = document.getElementById('emptyState');
  container.innerHTML = '';

  const q = document.getElementById('searchInput').value.trim().toLowerCase();
  const filtered = q ? list.filter(p => p.name.toLowerCase().includes(q)) : list;

  if (!filtered.length) {
    empty.classList.remove('hidden');
    container.classList.add('hidden');
    return;
  }
  empty.classList.add('hidden');
  container.classList.remove('hidden');

  filtered.forEach(p => {
    const card = document.createElement('div');
    card.className = 'project-card' + (_selectedProject?.gid === p.gid ? ' selected' : '');
    card.dataset.gid = p.gid;
    card.innerHTML = `
      <div class="card-name">${p.name}</div>
      <div class="card-vehicle">${p.vehicle_model_gid || '未绑定车型'}</div>
      <div class="card-meta">
        ${statusBadge(p.status)}
        <span style="font-size:11px;color:var(--text-muted);">${p.members?.length || 0} 人</span>
      </div>`;
    card.addEventListener('click', () => selectProject(p));
    container.appendChild(card);
  });
}

// ── 选中项目 ──────────────────────────────────────────────
async function selectProject(project) {
  _selectedProject = project;
  renderProjects(_projects);
  await openDetailPanel(project);
}

async function openDetailPanel(project) {
  const panel = document.getElementById('detailPanel');
  panel.classList.remove('hidden');

  document.getElementById('detailName').textContent    = project.name;
  document.getElementById('detailStatus').outerHTML   = statusBadge(project.status);
  document.getElementById('detailVehicle').textContent = project.vehicle_model_gid || '—';
  document.getElementById('detailMembers').textContent = (project.members?.length || 0) + ' 人';

  // 重新创建 statusBadge（因为 outerHTML 替换了元素）
  const statusEl = panel.querySelector('.status-badge');
  if (statusEl) {
    statusEl.id = 'detailStatus';
    statusEl.className = `status-badge status-${project.status}`;
    statusEl.textContent = STATUS_LABELS[project.status] || project.status;
  }

  await loadTasksForProject(project.gid);
  await loadIssuesForProject(project.gid);
  await loadProjectMembers(project.gid);
}

async function loadTasksForProject(projectGid) {
  const list = document.getElementById('taskList');
  list.innerHTML = '<div style="color:var(--text-muted);font-size:12px;">加载中…</div>';
  let tasks = [];
  try {
    tasks = (await apiCapability('project.task.read.atomic.tasks_search', { project_gid: projectGid }))?.data || [];
  } catch (_) {}
  list.innerHTML = '';
  if (!tasks || !tasks.length) {
    list.innerHTML = '<div style="color:var(--text-muted);font-size:12px;">暂无任务</div>';
    return;
  }
  tasks.forEach(t => {
    const div = document.createElement('div');
    div.className = 'task-item';
    div.innerHTML = `
      <div class="item-title">${t.title}</div>
      <div class="item-meta">${t.status} · ${t.priority}优先级${t.due_date ? ' · 截止 ' + t.due_date : ''}</div>`;
    list.appendChild(div);
  });
}

async function loadIssuesForProject(projectGid) {
  const list = document.getElementById('issueList');
  list.innerHTML = '<div style="color:var(--text-muted);font-size:12px;">加载中…</div>';
  let issues = [];
  try {
    issues = (await apiCapability('project.issue.read.atomic.issues_search', { project_gid: projectGid }))?.data || [];
  } catch (_) {}
  list.innerHTML = '';
  if (!issues || !issues.length) {
    list.innerHTML = '<div style="color:var(--text-muted);font-size:12px;">暂无问题</div>';
    return;
  }
  issues.forEach(i => {
    const div = document.createElement('div');
    div.className = 'issue-item';
    const sevColor = {A:'#ef4444',B:'#f97316',C:'#eab308'}[i.severity] || '#6b7280';
    div.innerHTML = `
      <div class="item-title"><span style="color:${sevColor}">●</span> ${i.title}</div>
      <div class="item-meta">${i.status} · ${i.severity}级</div>`;
    list.appendChild(div);
  });
}

// ── 新建/编辑项目对话框 ──────────────────────────────────
function openProjectDialog(project = null) {
  _editingGid = project?.gid || null;
  document.getElementById('dlgTitle').textContent   = project ? '编辑项目' : '新建项目';
  document.getElementById('inputName').value         = project?.name || '';
  document.getElementById('selectVehicle').value     = project?.vehicle_model_gid || '';
  document.getElementById('selectFactory').value     = project?.factory_gid || '';
  document.getElementById('dlgProject').classList.remove('hidden');
  document.getElementById('inputName').focus();
}
function closeProjectDialog() {
  document.getElementById('dlgProject').classList.add('hidden');
}
async function confirmProjectDialog() {
  const name = document.getElementById('inputName').value.trim();
  if (!name) { alert('项目名称不能为空'); return; }
  const vmGid = document.getElementById('selectVehicle').value;
  const factoryGid = document.getElementById('selectFactory').value;

  if (_editingGid) {
    await apiCapability('project.project.change.apply.atomic.projects_update', {
      gid: _editingGid, updates: { name, vehicle_model_gid: vmGid || null, factory_gid: factoryGid || null },
    });
  } else {
    await apiCapability('project.project.change.apply.atomic.projects_create', {
      name, vehicle_model_gid: vmGid || null, factory_gid: factoryGid || null,
    });
  }
  closeProjectDialog();
  await loadProjects();
}

// ── 新建任务对话框 ──────────────────────────────────────
function openTaskDialog() {
  if (!_selectedProject) return;
  document.getElementById('taskTitle').value    = '';
  document.getElementById('taskPriority').value = 'normal';
  document.getElementById('taskDue').value      = '';
  document.getElementById('dlgTask').classList.remove('hidden');
  document.getElementById('taskTitle').focus();
}
function closeTaskDialog() {
  document.getElementById('dlgTask').classList.add('hidden');
}
async function confirmTaskDialog() {
  const title = document.getElementById('taskTitle').value.trim();
  if (!title) { alert('任务标题不能为空'); return; }
  const priority = document.getElementById('taskPriority').value;
  const due      = document.getElementById('taskDue').value;

  try {
    await apiCapability('project.task.change.apply.atomic.tasks_create', {
      title, project_gid: _selectedProject.gid, priority, due_date: due || null,
    });
  } catch (e) { alert('创建失败: ' + (e?.message || e)); return; }
  closeTaskDialog();
  await loadTasksForProject(_selectedProject.gid);
}

// ── 加载数据 ─────────────────────────────────────────────
async function loadProjects() {
  const res = await apiCapability('project.project.read.atomic.projects_search');
  _projects = res?.data || [];
  renderProjects(_projects);
}

async function loadVehicleModels() {
  const res = await apiCapability('project.project.read.atomic.vehicle_models_list');
  _vehicleModels = res?.data || [];
  const sel = document.getElementById('selectVehicle');
  // 清除旧选项（保留第一个默认选项）
  while (sel.options.length > 1) sel.remove(1);
  _vehicleModels.forEach(vm => {
    const opt = new Option(`${vm.brand ? vm.brand + ' · ' : ''}${vm.name}`, vm.gid);
    sel.add(opt);
  });
}

async function loadFactories() {
  const res = await apiCapability('factory.asset.search', { asset_type: 'factory' });
  _factories = res?.data || [];
  const sel = document.getElementById('selectFactory');
  if (!sel) return;
  while (sel.options.length > 1) sel.remove(1);
  _factories.forEach(f => {
    const opt = new Option(f.name, f.gid);
    sel.add(opt);
  });
}

// ── 初始化 ───────────────────────────────────────────────
function _bindEvents() {
  // 搜索
  document.getElementById('searchInput').addEventListener('input', () => renderProjects(_projects));
  // 新建按钮
  document.getElementById('btnNew').addEventListener('click', () => openProjectDialog());
  // 对话框
  document.getElementById('btnDlgClose').addEventListener('click', closeProjectDialog);
  document.getElementById('btnCancel').addEventListener('click', closeProjectDialog);
  document.getElementById('btnConfirm').addEventListener('click', confirmProjectDialog);
  // 详情面板
  document.getElementById('btnCloseDetail').addEventListener('click', () => {
    document.getElementById('detailPanel').classList.add('hidden');
    _selectedProject = null;
    renderProjects(_projects);
  });
  document.getElementById('btnEditProject').addEventListener('click', () => openProjectDialog(_selectedProject));
  // 状态推进
  document.getElementById('btnAdvStatus').addEventListener('click', advanceProjectStatus);
  // 任务
  document.getElementById('btnNewTask').addEventListener('click', openTaskDialog);
  document.getElementById('btnTaskClose').addEventListener('click', closeTaskDialog);
  document.getElementById('btnTaskCancel').addEventListener('click', closeTaskDialog);
  document.getElementById('btnTaskConfirm').addEventListener('click', confirmTaskDialog);
  // 键盘
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      if (!document.getElementById('dlgProject').classList.contains('hidden')) closeProjectDialog();
      else if (!document.getElementById('dlgTask').classList.contains('hidden')) closeTaskDialog();
    }
  });
}

const STATUS_ADV = { preparing: 'in_progress', in_progress: 'completed', completed: 'archived' };
async function advanceProjectStatus() {
  if (!_selectedProject) return;
  const nextStatus = STATUS_ADV[_selectedProject.status];
  if (!nextStatus) { alert('当前状态无法继续推进'); return; }
  await apiCapability('project.project.change.apply.atomic.projects_update', {
    gid: _selectedProject.gid, updates: { status: nextStatus },
  });
  await loadProjects();
  const updated = _projects.find(p => p.gid === _selectedProject.gid);
  if (updated) await openDetailPanel(updated);
}

async function _start() {
  await loadVehicleModels();
  await loadFactories();
  await loadProjects();
  // 若 URL 携带 project_gid，自动选中该项目
  const urlGid = new URLSearchParams(location.search).get('project_gid');
  if (urlGid) {
    const target = _projects.find(p => p.gid === urlGid);
    if (target) selectProject(target);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  _bindEvents();
  _start();
});

// ── 成员管理 ───────────────────────────────────────────────
async function loadProjectMembers(projectGid) {
  const section = document.getElementById('memberSection');
  const listEl  = document.getElementById('projectMemberList');
  const addBtn  = document.getElementById('btnAddProjectMember');
  if (!section || !listEl) return;

  const isCloud = (window.parent?._authMode || window._authMode || 'local') === 'feishu';
  if (!isCloud) { section.style.display = 'none'; return; }
  section.style.display = '';
  const _cloudFetch = cloudFetch;

  let isOwner = false;
  try {
    const me = await _cloudFetch('/users/me', { method: 'GET' }).then(r => r.json());
    const grants = me.grants || [];
    const orgRole = me.org_role || me.system_role || '';
    isOwner = orgRole === 'super_admin' ||
      grants.some(g => g.grant_type === 'project_owner' && g.scope_gid === projectGid);
    if (addBtn) addBtn.style.display = isOwner ? '' : 'none';
  } catch (_) {}

  listEl.innerHTML = '<div style="color:var(--text-muted)">加载中…</div>';
  try {
    const [memberResp, lineResp, grantResp] = await Promise.all([
      apiCapability('project.member.read', { operation: 'members.list', arguments: { project_gid: projectGid } }),
      invokeCapability('craft.bop.entry.legacy_read', {
        operation: 'project_bop_lines', project_gid: projectGid, limit: 500,
      }),
      (window.top?.AI00ExistingCapabilityClient || window.AI00ExistingCapabilityClient).call('base.grants.list', { userGid: null }).catch(() => ({ grants: [] })),
    ]);
    const members = Array.isArray(memberResp) ? memberResp : (memberResp?.members || memberResp?.data || []);
    const lines = Array.isArray(lineResp) ? lineResp : (lineResp?.data || lineResp?.items || []);
    const grants = Array.isArray(grantResp?.grants) ? grantResp.grants : [];
    const lineLeadsByLine = new Map();
    for (const grant of grants) {
      if (grant.grant_type !== 'section_lead') continue;
      const user = members.find(m => m.user_gid === grant.grantee_gid);
      if (!user) continue;
      lineLeadsByLine.set(grant.scope_gid, {
        grant_gid: grant.gid,
        user_gid: grant.grantee_gid,
        name: user.name || user.user_gid,
      });
    }

    if (!members.length && !lines.length) {
      listEl.innerHTML = '<div style="color:var(--text-muted)">暂无成员</div>';
      return;
    }

    const memberRows = members.map(m => `
      <div style="display:flex;align-items:center;gap:8px;padding:5px 0;border-bottom:1px solid var(--border-light,#313244)">
        <span style="flex:1">${_escP(m.name || m.user_gid || m.gid)}</span>
        <span style="font-size:11px;color:var(--text-muted)">${m.project_role || m.scope_type || ''}</span>
      </div>`).join('');

    const lineRows = lines.map(line => {
      const assigned = lineLeadsByLine.get(line.gid);
      return `<div style="display:flex;align-items:center;gap:8px;padding:5px 0;border-bottom:1px solid var(--border-light,#313244)">
        <span style="min-width:120px;color:var(--text-muted)">${_escP(line.title || '（未命名线体）')}</span>
        <span style="flex:1">${assigned ? _escP(assigned.name) : '<span style="color:var(--text-muted)">未设置</span>'}</span>
        <span style="padding:1px 7px;border-radius:8px;font-size:10px;background:rgba(166,227,161,.15);color:#a6e3a1">line_admin</span>
        ${isOwner ? `<button onclick="_assignLineLead('${_escP(projectGid)}','${_escP(line.gid)}','${assigned?.user_gid || ''}','${assigned?.grant_gid || ''}')"
          style="padding:2px 8px;border-radius:4px;border:1px solid var(--border);background:transparent;color:var(--text-muted);font-size:11px;cursor:pointer">
          ${assigned ? '变更/清空' : '设为线体管理员'}
        </button>` : ''}
      </div>`;
    }).join('');

    listEl.innerHTML = `
      <div style="font-size:11px;color:var(--text-muted);margin-bottom:6px">项目成员</div>
      ${memberRows || '<div style="color:var(--text-muted);margin-bottom:8px">暂无项目成员</div>'}
      <div style="font-size:11px;color:var(--text-muted);margin:10px 0 6px">按线体管理员</div>
      ${lineRows || '<div style="color:var(--text-muted)">暂无线体</div>'}`;
  } catch (_) {
    listEl.innerHTML = '<div style="color:var(--text-muted)">加载失败</div>';
  }
}

window._assignLineLead = async function (projectGid, lineGid, currentUserGid, currentGrantGid) {
  if (!projectGid || !lineGid) return;
  try {
    let nextUserGid = currentUserGid || '';
    if (currentUserGid) {
      const clear = confirm('确定清空当前线体管理员吗？点击“取消”可改派他人。');
      if (clear) {
        await apiCapability('project.member.change.apply', {
          operation: 'members.line_assignment.replace',
          arguments: { project_gid: projectGid, line_gid: lineGid, user_gid: null },
        });
        await loadProjectMembers(projectGid);
        return;
      }
    }
    nextUserGid = prompt('输入要设为线体管理员的 user_gid') || '';
    if (!nextUserGid.trim()) return;
    await apiCapability('project.member.change.apply', {
      operation: 'members.line_assignment.replace',
      arguments: { project_gid: projectGid, line_gid: lineGid, user_gid: nextUserGid.trim() },
    });
    await loadProjectMembers(projectGid);
  } catch (e) {
    alert('授权失败：' + (e.message || String(e)));
  }
};

function _escP(s) {
  return String(s ?? '').replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
  );
}
