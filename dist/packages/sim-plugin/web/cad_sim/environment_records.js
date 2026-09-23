(function (root) {
  'use strict';
  const expandedGroups = new Set(['personal_project_spaces']);
  expandedGroups.add('private');
  const expandedStatuses = new Set(['active']);
  function closeMenus(container, except) {
    container.querySelectorAll?.('.cs-environment-context-menu').forEach(menu => {
      if (menu !== except) menu.classList.add('hidden');
    });
  }

  function appendMenuAction(menu, label, action, kind, gid, options) {
    const item = document.createElement('button');
    item.type = 'button';
    item.className = `cs-environment-context-action${options?.danger ? ' danger' : ''}`;
    item.textContent = label;
    item.dataset.action = action;
    item.dataset.recordKind = kind;
    item.dataset.recordGid = gid;
    if (action === 'edit') item.dataset.workspaceGid = gid;
    if (options?.disabled) item.disabled = true;
    if (options?.title) item.title = options.title;
    menu.appendChild(item);
  }

  function render(container, groups, selectedGid) {
    if (!container) return;
    container.replaceChildren();
    const normalized = (groups.length && groups[0]?.kind
      ? groups.filter(group => group.kind === 'private')
      : [{ kind: 'private', label: '个人仿真环境', items: groups }])
      .map(group => ({ ...group, label: '个人仿真环境' }));
    normalized.forEach(group => {
      let target = container;
      if (group.kind === 'project_spaces' || group.kind === 'personal_project_spaces' || group.kind === 'private') {
        const key = group.kind;
        const details = document.createElement('details');
        details.className = 'cs-environment-project';
        details.dataset.projectKey = key;
        details.open = expandedGroups.has(key) || (group.items || []).some(item => String(item.record_gid) === String(selectedGid));
        const summary = document.createElement('summary');
        const label = document.createElement('span');
        label.className = 'name';
        label.textContent = group.label;
        const count = document.createElement('span');
        count.className = 'count';
        count.textContent = String((group.items || []).length);
        summary.append(label, count);
        details.appendChild(summary);
        details.addEventListener('toggle', () => details.open ? expandedGroups.add(key) : expandedGroups.delete(key));
        container.appendChild(details);
        target = details;
      }
      const statusTargets = new Map();
      (group.items || []).forEach(record => {
      let recordTarget = target;
      if (group.kind === 'private') {
        const statusKey = record.status || 'active';
        if (!statusTargets.has(statusKey)) {
          const statusDetails = document.createElement('details');
          statusDetails.className = 'cs-environment-status-group';
          statusDetails.open = expandedStatuses.has(statusKey) || (group.items || []).some(item =>
            (item.status || 'active') === statusKey && String(item.record_gid) === String(selectedGid));
          const statusSummary = document.createElement('summary');
          statusSummary.textContent = `${({ active: '活动', baseline: '基线', frozen: '冻结', archived: '归档' })[statusKey] || statusKey} (${(group.items || []).filter(item => (item.status || 'active') === statusKey).length})`;
          statusDetails.appendChild(statusSummary);
          statusDetails.addEventListener('toggle', () => statusDetails.open ? expandedStatuses.add(statusKey) : expandedStatuses.delete(statusKey));
          target.appendChild(statusDetails);
          statusTargets.set(statusKey, statusDetails);
        }
        recordTarget = statusTargets.get(statusKey);
      }
      const row = document.createElement('div');
      row.className = 'cs-environment-record-row';
      const button = document.createElement('button');
      button.type = 'button';
      const gid = record.record_gid || record.workspace_gid || record.space_gid;
      const kind = record.record_kind || group.kind;
      button.className = `cs-environment-record${gid === selectedGid ? ' active' : ''}`;
      if (gid) button.dataset.recordGid = gid;
      button.dataset.recordKind = record.record_kind || group.kind;
      button.disabled = record.unavailable === true;
      const name = document.createElement('span');
      name.className = 'name';
      name.textContent = record.display_label || record.name || record.project_name || (kind === 'team' ? '项目空间' : kind === 'managed_personal' ? '我的个人项目空间' : '未命名环境');
      const status = document.createElement('span');
      status.className = 'status';
      status.textContent = record.status || 'active';
      button.append(name, status);
      row.appendChild(button);
      if (record.unavailable) {
        recordTarget.appendChild(row);
        return;
      }
      const menu = document.createElement('div');
      menu.className = 'cs-environment-context-menu hidden';
      menu.setAttribute('role', 'menu');
      if (kind === 'private' && record.status === 'frozen' && record.version_gid) {
        appendMenuAction(menu, '在 VisMockup 重放', 'replay', kind, gid, {
          title: '按冻结版本生成运行包、打开并回读验证',
        });
      }
      if (kind === 'team' || kind === 'managed_personal' || kind === 'private') {
        appendMenuAction(menu, 'Fork', 'fork', kind, gid, { title: kind === 'team'
          ? '从不可变团队版本 Fork 新项目'
          : kind === 'managed_personal'
            ? '从不可变版本 Fork 个人项目空间'
            : '从不可变版本 Fork 新私人仿真环境' });
      }
      if (kind === 'private' && record.is_owner !== false) {
        appendMenuAction(menu, '编辑', 'edit', kind, gid, {
          disabled: record.status === 'frozen',
          title: record.status === 'frozen' ? '冻结环境不可编辑' : '编辑仿真环境',
        });
      }
      if (kind === 'team' || kind === 'managed_personal' || (kind === 'private' && record.is_owner !== false)) {
        appendMenuAction(menu, '删除', 'delete', kind, gid, {
          danger: true,
          title: kind === 'team' ? '删除项目 BOP Repository' : '删除此环境',
        });
      }
      row.appendChild(menu);
      row.addEventListener('contextmenu', event => {
        event.preventDefault();
        closeMenus(container, menu);
        menu.style.left = `${Math.min(event.clientX, window.innerWidth - 132)}px`;
        menu.style.top = `${Math.min(event.clientY, window.innerHeight - 112)}px`;
        menu.classList.remove('hidden');
      });
      menu.addEventListener('click', () => menu.classList.add('hidden'));
      menu.addEventListener('mouseleave', () => menu.classList.add('hidden'));
      recordTarget.appendChild(row);
      });
    });
  }
  root.AI00SimulationEnvironmentRecords = { render };
})(globalThis);
