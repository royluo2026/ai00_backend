(function (root) {
  'use strict';

  function unwrap(result) {
    return result && typeof result === 'object' && result.data ? result.data : result;
  }

  function defaultName() {
    const now = new Date();
    const value = [now.getFullYear(), now.getMonth() + 1, now.getDate(), now.getHours(), now.getMinutes(), now.getSeconds()]
      .map(item => String(item).padStart(2, '0')).join('');
    return `仿真环境 ${value}`;
  }

  function deriveWorkspaceActions({ workspace, hasBopSource = false } = {}) {
    if (!workspace) return {
      insert: false, save: false, sync: false, export: false, writeback: false,
      reason: '请先新建或打开个人仿真环境',
    };
    const writable = workspace.is_owner !== false && workspace.status !== 'frozen' && workspace.status !== 'archived';
    return {
      insert: writable, save: writable, sync: writable, export: true,
      writeback: false,
      reason: writable ? '' : '当前环境不可编辑',
    };
  }

  function createElapsedIndicator(element, label, clock = {}) {
    const now = clock.now || Date.now;
    const schedule = clock.setInterval || root.setInterval;
    const cancel = clock.clearInterval || root.clearInterval;
    const startedAt = now();
    const elapsedSeconds = () => Math.max(0, Math.floor((now() - startedAt) / 1000));
    const render = () => { if (element) element.textContent = `${label} · 已用 ${elapsedSeconds()}s`; };
    render();
    const timer = schedule(render, 1000);
    return { elapsedSeconds, stop() { cancel(timer); } };
  }

  function createPanelToggle({ panel, button, storage = root.localStorage }) {
    const key = 'ai00.simulation.environment-panel-collapsed';
    const apply = collapsed => {
      panel.classList.toggle('collapsed', collapsed);
      button.setAttribute('aria-expanded', String(!collapsed));
      const icon = button.querySelector?.('[data-toggle-icon]');
      if (icon) icon.textContent = collapsed ? '⌄' : '⌃';
      else button.textContent = collapsed ? '›' : '‹';
      button.title = collapsed ? '展开仿真环境' : '收起仿真环境';
    };
    const saved = storage?.getItem(key);
    apply(saved == null ? panel.classList.contains('collapsed') : saved === '1');
    const onClick = () => {
      const collapsed = !panel.classList.contains('collapsed');
      apply(collapsed);
      storage?.setItem(key, collapsed ? '1' : '0');
    };
    button.addEventListener('click', onClick);
    return { destroy() { button.removeEventListener('click', onClick); } };
  }

  function createController({ invoke, recordsView, treeView, elements, dialogView, forkDialogView, cache = null,
    getAuthSubjectGid = () => null,
    openFrozen = record => root._openFrozenSimulationEnvironment?.(record),
    confirmDelete = async message => (await root.AI00Dialogs.confirm(message)) !== false }) {
    const store = root.AI00SimulationEnvironmentStore.createEnvironmentStore({
      invoke: async (capability, payload) => unwrap(await invoke(capability, {
        version: 1, payload,
        ...(payload?.idempotency_key ? { idempotency_key: payload.idempotency_key } : {}),
      })),
      cache,
      getAuthSubjectGid,
    });
    let openLevel = 1;
    let expandedNodeGids = new Set();
    let renderedWorkspaceKey = null;
    let openingRecordKey = null;
    const render = state => {
      const workspaceKey = state.workspace ? `${state.currentKind}:${state.workspace.workspace_gid}` : null;
      if (workspaceKey !== renderedWorkspaceKey) {
        renderedWorkspaceKey = workspaceKey;
        expandedNodeGids = treeView.expandedForLevel?.(state.workspace?.nodes || [], openLevel) || new Set();
      }
      recordsView.render(elements.records, state.groups, state.workspace?.workspace_gid || null);
      treeView.render(elements.tree, state.workspace?.nodes || [], state.view.selectedNodeGid, { expandedNodeGids });
      if (elements.treeTitle) elements.treeTitle.textContent = treeView.environmentLabel?.(state.workspace, state.currentKind) || '当前仿真环境树';
      if (elements.documentLabel) elements.documentLabel.textContent = treeView.currentDocumentLabel?.(state.workspace, state.currentKind) || '当前仿真文档 · 未选择环境';
      if (elements.status) {
        elements.status.textContent = state.error
          ? `${state.errorAction || '操作失败'}：${state.error.code || state.error.message || 'unknown_error'}`
          : state.loading ? '正在校验…'
            : state.cacheStatus === 'offline' ? '离线缓存（只读）'
              : state.cacheStatus === 'validated' ? '缓存已校验'
                : state.workspace ? '已同步' : '尚未选择环境';
      }
      const hasBopSource = Boolean(state.workspace?.source_bop_version_gid || state.workspace?.source_repository_gid);
      const actions = deriveWorkspaceActions({
        workspace: state.workspace,
        hasBopSource,
      });
      for (const [name, enabled] of Object.entries(actions)) {
        if (name === 'reason' || !elements.actions?.[name]) continue;
        elements.actions[name].disabled = !enabled;
        elements.actions[name].title = enabled ? '' : (name === 'writeback'
          ? (hasBopSource ? '第一阶段仅提供回传差异准备；Craft 精确写回能力尚未发布' : '当前环境没有 BOP 来源')
          : actions.reason || '当前操作不可用');
      }
    };
    store.subscribe(render);

    let startPromise = null;
    function start() {
      if (!startPromise) startPromise = (async () => {
        try { await store.load(); } catch (_) { render(store.state); }
      })();
      return startPromise;
    }
    elements.records?.addEventListener('click', async event => {
      const replay = event.target.closest('[data-action="replay"]');
      if (replay) {
        try {
          const record = store.state.records.find(item => String(item.workspace_gid) === String(replay.dataset.recordGid));
          if (!record?.version_gid) throw new Error('frozen_workspace_version_not_found');
          await openFrozen(record);
        } catch (error) {
          store.state.error = error; store.state.errorAction = '重放失败'; render(store.state);
        }
        return;
      }
      const fork = event.target.closest('[data-action="fork"]');
      if (fork) {
        try {
          const kind = fork.dataset.recordKind;
          const record = kind === 'private'
            ? store.state.records.find(item => item.workspace_gid === fork.dataset.recordGid)
            : store.state.spaces.find(item => item.space_gid === fork.dataset.recordGid);
          if (!record) throw new Error('fork_source_not_found');
          const versionsPromise = kind === 'private'
            ? store.ensurePrivateForkVersions(record) : store.ensureForkVersions(record);
          const projectsPromise = store.loadProjectCandidates();
          const choice = await forkDialogView.open({
            kind, record, versions: [], projects: store.state.projects,
            repositories: store.state.repositories, versionsPromise, projectsPromise,
          });
          if (!choice) return;
          if (kind === 'team') await store.forkRepository(choice);
          else if (kind === 'managed_personal') await store.forkPersonal(choice);
          else await store.forkPrivate(choice);
        } catch (error) { store.state.error = error; store.state.errorAction = 'Fork 失败'; render(store.state); }
        return;
      }
      const remove = event.target.closest('[data-action="delete"]');
      if (remove) {
        try {
          const kind = remove.dataset.recordKind;
          const gid = remove.dataset.recordGid;
          const record = kind === 'private'
            ? store.state.records.find(item => item.workspace_gid === gid)
            : store.state.spaces.find(item => item.space_gid === gid);
          if (!record || !await confirmDelete('确认删除？该操作保留历史证据，但环境将不再显示。')) return;
          await store.deleteRecord(kind, record);
        } catch (_) { render(store.state); }
        return;
      }
      const edit = event.target.closest('[data-action="edit"]');
      if (edit) {
        try {
          const gid = edit.dataset.workspaceGid;
          const summary = store.state.records.find(item => item.workspace_gid === gid);
          const workspacePromise = store.state.workspace?.workspace_gid === gid
            ? Promise.resolve(store.state.workspace) : store.openWorkspace(gid);
          const projectsPromise = store.loadProjectCandidates();
          const draft = await dialogView.open({ mode: 'edit', workspace: summary || store.state.workspace || {}, projects: store.state.projects, projectsPromise });
          if (draft) { await workspacePromise; await store.updateWorkspace(draft); }
        } catch (_) { render(store.state); }
        return;
      }
      const button = event.target.closest('[data-record-gid],[data-workspace-gid]');
      if (!button) return;
      const kind = button.dataset.recordKind || 'private';
      const gid = button.dataset.recordGid || button.dataset.workspaceGid;
      const record = store.state.groups.flatMap(group => group.items || [])
        .find(item => String(item.record_gid || item.workspace_gid || item.space_gid) === String(gid) && (item.record_kind || 'private') === kind);
      if (openingRecordKey) return;
      openingRecordKey = `${kind}:${gid}`;
      const label = record?.display_label || record?.name || record?.project_name || gid;
      const timer = createElapsedIndicator(elements.treeLoadingText, `正在加载：${label}`);
      elements.treeLoading?.classList.remove('hidden');
      elements.tree?.replaceChildren?.();
      let succeeded = false;
      try { await store.openRecord(kind, record || gid); succeeded = true; }
      catch (_) { render(store.state); }
      finally {
        timer.stop();
        elements.treeLoading?.classList.add('hidden');
        openingRecordKey = null;
        if (succeeded && elements.status) elements.status.textContent = `已同步 · ${timer.elapsedSeconds()}s`;
      }
    });
    elements.newButton?.addEventListener('click', async () => {
      try {
        start();
        const projectsPromise = store.loadProjectCandidates();
        const draft = await dialogView.open({ mode: 'create', projects: store.state.projects, projectsPromise, workspace: { name: defaultName(), review_type: 'scattered_review', version_label: 'V1', status: 'active', visibility: 'private', project_gids: [], primary_project_gid: null } });
        if (draft) await store.createWorkspace(draft);
      } catch (_) { render(store.state); }
    });
    elements.tree?.addEventListener('click', event => {
      const toggle = event.target.closest('[data-tree-toggle]');
      if (toggle) {
        event.preventDefault?.();
        const gid = toggle.dataset.treeToggle;
        if (expandedNodeGids.has(gid)) expandedNodeGids.delete(gid); else expandedNodeGids.add(gid);
        render(store.state);
        return;
      }
      const button = event.target.closest('[data-node-gid]');
      if (!button) return;
      store.rememberView({ selectedNodeGid: button.dataset.nodeGid, treeScrollTop: elements.tree.scrollTop });
      render(store.state);
    });
    elements.treeDepth?.addEventListener('change', event => {
      openLevel = Math.max(1, Math.min(5, Number(event.target.value) || 1));
      expandedNodeGids = treeView.expandedForLevel?.(store.state.workspace?.nodes || [], openLevel) || new Set();
      render(store.state);
    });
    elements.vmTree?.addEventListener('dragstart', event => {
      const row = event.target.closest('[data-occurrence-gid]');
      if (!row?.dataset.occurrenceGid) return;
      event.dataTransfer?.setData('application/x-ai00-vm-occurrence', row.dataset.occurrenceGid);
    });
    elements.tree?.addEventListener('dragover', event => {
      if (event.dataTransfer?.types?.includes('application/x-ai00-vm-occurrence')) event.preventDefault();
    });
    elements.tree?.addEventListener('drop', async event => {
      const target = event.target.closest('[data-node-gid]');
      const occurrenceGid = event.dataTransfer?.getData('application/x-ai00-vm-occurrence');
      if (!target || !occurrenceGid) return;
      event.preventDefault();
      store.rememberView({ selectedNodeGid: target.dataset.nodeGid, treeScrollTop: elements.tree.scrollTop, modelScrollTop: elements.vmTree?.scrollTop || 0 });
      try { await store.bindOccurrence({ nodeGid: target.dataset.nodeGid, occurrenceGid, idempotencyKey: `bind-${Date.now()}-${occurrenceGid}` }); }
      catch (_) { render(store.state); }
    });
    return { store, start, render };
  }

  function createForkDialog(elements) {
    let resolveOpen = null;
    const close = value => { elements.overlay.classList.add('hidden'); const resolve = resolveOpen; resolveOpen = null; resolve?.(value); };
    elements.cancel.addEventListener('click', () => close(null));
    elements.form.addEventListener('submit', event => {
      event.preventDefault();
      const kind = elements.form.dataset.kind;
      const sourceVersionGid = elements.sourceVersion.value;
      const base = { sourceVersionGid, forkDepth: elements.depth.value, expectedTargetSlot: 0 };
      const selectedOptionLabel = select => {
        const option = select?.selectedOptions?.[0]
          || select?.options?.[select.selectedIndex]
          || (select?.children || []).find(item => String(item.value) === String(select.value));
        return String(option?.textContent || '').trim();
      };
      if (kind === 'team') {
        const targetProjectGid = String(elements.targetProject.value || '').trim();
        const targetName = String(elements.targetName.value || '').trim();
        if (!targetProjectGid) { elements.error.textContent = '请选择目标项目'; return; }
        if (!targetName) { elements.error.textContent = '请输入新的 BOP Repository 名称'; return; }
        close({ ...base, targetProjectGid, targetName,
          targetProjectName: selectedOptionLabel(elements.targetProject) || targetProjectGid,
          includePersonalMigration: elements.includePersonal.checked });
      } else if (kind === 'managed_personal') close({ ...base, targetRepositoryGid: elements.targetRepository.value });
      else {
        const targetName = String(elements.targetName.value || '').trim();
        if (!targetName) { elements.error.textContent = '请输入新的环境名称'; return; }
        close({ ...base, sourceWorkspaceGid: elements.form.dataset.sourceWorkspaceGid,
          targetName, targetVersionLabel: elements.targetVersion.value.trim() });
      }
    });
    return { open({ kind, record, versions, projects, repositories, versionsPromise, projectsPromise }) {
      elements.form.dataset.kind = kind;
      elements.form.dataset.sourceWorkspaceGid = record?.workspace_gid || '';
      const fillVersions = items => elements.sourceVersion.replaceChildren(...(items || []).map(item => new Option(
        item.version_label || item.version_kind || item.version_gid, item.version_gid)));
      const fillProjects = items => elements.targetProject.replaceChildren(...(items || []).map(item => {
        const gid = String(item.gid || item.project_gid || item.id || '').trim();
        return new Option(item.name || item.project_name || item.project_code || gid, gid);
      }).filter(option => option.value));
      fillVersions(versions);
      fillProjects(projects);
      elements.targetRepository.replaceChildren(...(repositories || []).map(item => new Option(
        item.project_name || item.project_gid || item.repository_gid, item.repository_gid)));
      elements.targetProjectField.classList.toggle('hidden', kind !== 'team');
      elements.targetRepositoryField.classList.toggle('hidden', kind !== 'managed_personal');
      elements.includePersonalField.classList.toggle('hidden', kind !== 'team');
      elements.depthField.classList.remove('hidden');
      // Team Fork also needs an explicit Repository name. Without showing it,
      // the governed preview schema rejects the request as invalid_input.
      elements.privateFields.classList.toggle('hidden', kind !== 'team' && kind !== 'private');
      if (elements.targetVersionField) elements.targetVersionField.classList.toggle('hidden', kind !== 'private');
      if (elements.targetNameLabel) elements.targetNameLabel.textContent = kind === 'team' ? '新 BOP Repository 名称' : '新环境名称';
      elements.targetName.value = `${record?.name || '仿真环境'} Fork`;
      elements.targetVersion.value = record?.version_label || 'V1';
      elements.summary.textContent = '正在加载来源不可变版本…';
      elements.error.textContent = '';
      const submit = elements.form.querySelector('button[type="submit"]');
      submit.disabled = true;
      elements.overlay.classList.remove('hidden');
      const opened = new Promise(resolve => { resolveOpen = resolve; });
      Promise.all([Promise.resolve(versionsPromise || versions || []), Promise.resolve(projectsPromise || projects || [])])
        .then(([loadedVersions, loadedProjects]) => {
          if (!resolveOpen) return;
          fillVersions(loadedVersions);
          fillProjects(loadedProjects);
          const missingTarget = kind === 'team' ? !loadedProjects?.length
            : kind === 'managed_personal' ? !(repositories || []).length : false;
          submit.disabled = !loadedVersions?.length || missingTarget;
          elements.summary.textContent = loadedVersions?.length
            ? '选择复制深度后，将先生成预览，再按同一计划执行 Fork。'
            : '来源空间尚无可用的不可变版本。';
        })
        .catch(error => {
          if (!resolveOpen) return;
          submit.disabled = true;
          elements.summary.textContent = '来源版本加载失败';
          elements.error.textContent = error?.code || error?.message || 'fork_source_load_failed';
        });
      return opened;
    } };
  }

  function createDialog(elements) {
    let resolveOpen = null;
    const close = value => { elements.overlay.classList.add('hidden'); const resolve = resolveOpen; resolveOpen = null; resolve?.(value); };
    elements.cancel.addEventListener('click', () => close(null));
    elements.form.addEventListener('submit', event => {
      event.preventDefault();
      const primary_project_gid = String(elements.primary.value || '').trim() || null;
      if (primary_project_gid && !/^[1-9][0-9]*$/.test(primary_project_gid)) {
        elements.error.textContent = '主项目标识无效，请重新选择'; return;
      }
      if (elements.reviewType.value === 'node_review' && !primary_project_gid) {
        elements.error.textContent = '节点评审必须选择一个主项目'; return;
      }
      const project_gids = primary_project_gid ? [primary_project_gid] : [];
      close({ name: elements.name.value.trim(), review_type: elements.reviewType.value,
        version_label: elements.version.value.trim(), status: elements.workspaceStatus.value,
        visibility: elements.visibility.value, project_gids, primary_project_gid });
    });
    const fillProjects = (projects, workspace) => {
      elements.primary.replaceChildren(new Option('— 无 —', ''));
      (projects || []).forEach(project => {
        const gid = String(project.gid || project.project_gid || project.id || '').trim(); if (!/^[1-9][0-9]*$/.test(gid)) return;
        elements.primary.add(new Option(project.name || project.project_name || project.project_code || gid, gid));
      });
      elements.primary.value = String(workspace.primary_project_gid || '');
    };
    return { open({ mode, workspace, projects, projectsPromise }) {
      elements.title.textContent = mode === 'edit' ? '编辑个人仿真环境' : '新建个人仿真环境';
      elements.name.value = workspace.name || '';
      elements.reviewType.value = workspace.review_type || 'scattered_review';
      elements.version.value = workspace.version_label || 'V1';
      elements.workspaceStatus.value = workspace.status || 'active';
      elements.visibility.value = workspace.visibility || 'private';
      fillProjects(projects, workspace);
      elements.updated.value = workspace.updated_at ? new Date(workspace.updated_at).toLocaleString() : '保存后自动生成';
      elements.error.textContent = '';
      const frozen = mode === 'edit' && workspace.status === 'frozen';
      elements.save.disabled = frozen; elements.error.textContent = frozen ? '冻结环境不可编辑' : '';
      elements.overlay.classList.remove('hidden');
      Promise.resolve(projectsPromise).then(value => { if (resolveOpen) fillProjects(value, workspace); }).catch(() => {});
      return new Promise(resolve => { resolveOpen = resolve; });
    } };
  }

  function bootstrap() {
    if (!root.AI00Business?.invoke || !root.AI00SimulationEnvironmentStore) return null;
    const dialogView = createDialog({
      overlay: document.getElementById('environmentModalOverlay'), form: document.getElementById('environmentModalForm'),
      title: document.getElementById('environmentModalTitle'), name: document.getElementById('environmentModalName'),
      primary: document.getElementById('environmentModalPrimaryProject'),
      reviewType: document.getElementById('environmentModalReviewType'), version: document.getElementById('environmentModalVersion'),
      workspaceStatus: document.getElementById('environmentModalStatus'), visibility: document.getElementById('environmentModalVisibility'),
      updated: document.getElementById('environmentModalUpdated'), error: document.getElementById('environmentModalError'),
      cancel: document.getElementById('environmentModalCancel'), save: document.getElementById('environmentModalSave'),
    });
    const forkDialogView = createForkDialog({
      overlay: document.getElementById('forkModalOverlay'), form: document.getElementById('forkModalForm'),
      sourceVersion: document.getElementById('forkModalSourceVersion'),
      targetProject: document.getElementById('forkModalTargetProject'),
      targetRepository: document.getElementById('forkModalTargetRepository'),
      targetProjectField: document.getElementById('forkModalTargetProjectField'),
      targetRepositoryField: document.getElementById('forkModalTargetRepositoryField'),
      depth: document.getElementById('forkModalDepth'), depthField: document.getElementById('forkModalDepthField'),
      privateFields: document.getElementById('forkModalPrivateFields'), targetName: document.getElementById('forkModalTargetName'),
      targetNameLabel: document.getElementById('forkModalTargetNameLabel'), targetVersionField: document.getElementById('forkModalTargetVersionField'),
      targetVersion: document.getElementById('forkModalTargetVersion'), includePersonal: document.getElementById('forkModalIncludePersonal'),
      includePersonalField: document.getElementById('forkModalIncludePersonalField'),
      summary: document.getElementById('forkModalSummary'), error: document.getElementById('forkModalError'),
      cancel: document.getElementById('forkModalCancel'),
    });
    createPanelToggle({
      panel: document.getElementById('environmentRecordsPanel'),
      button: document.getElementById('btnToggleEnvironmentPanel'),
    });
    const controller = createController({
      invoke: root.AI00Business.invoke.bind(root.AI00Business),
      recordsView: root.AI00SimulationEnvironmentRecords,
      treeView: root.AI00SimulationEnvironmentTree,
      dialogView,
      forkDialogView,
      cache: (() => {
        try {
          return root.AI00SimulationCache && root.indexedDB
            ? root.AI00SimulationCache.createSimulationCache({ indexedDB: root.indexedDB }) : null;
        } catch (_) { return null; }
      })(),
      getAuthSubjectGid: () => {
        const user = root.parent?._authUser || root._authUser;
        if (user?.gid || user?.user_gid) return user.gid || user.user_gid;
        try {
          const stored = JSON.parse(root.localStorage?.getItem('ai00_user') || 'null');
          return stored?.gid || stored?.user_gid || null;
        } catch (_) { return null; }
      },
      elements: {
        records: document.getElementById('environmentRecordsBody'),
        tree: document.getElementById('bopTreeBody'),
        treeTitle: document.getElementById('environmentTreeTitle'),
        documentLabel: document.getElementById('currentDocumentLabel'),
        treeDepth: document.getElementById('environmentTreeDepth'),
        treeLoading: document.getElementById('bopTreeLoading'),
        treeLoadingText: document.getElementById('bopTreeLoadingText'),
        status: document.getElementById('environmentSyncStatus'),
        newButton: document.getElementById('btnNewEnvironment'),
        vmTree: document.getElementById('visTreeBody'),
        actions: {
          insert: document.getElementById('btnEnvironmentInsert'),
          save: document.getElementById('btnEnvironmentSave'),
          sync: document.getElementById('btnEnvironmentSync'),
          export: document.getElementById('btnEnvironmentExport'),
          writeback: document.getElementById('btnEnvironmentWriteback'),
        },
      },
    });
    root._simulationEnvironmentWorkspace = controller;
    controller.start();
    return controller;
  }

  root.AI00SimulationEnvironmentWorkspace = { bootstrap, createController, createDialog, createElapsedIndicator, createForkDialog, createPanelToggle, defaultName, deriveWorkspaceActions, unwrap };
  if (typeof document !== 'undefined') document.addEventListener('DOMContentLoaded', bootstrap, { once: true });
})(typeof globalThis !== 'undefined' ? globalThis : this);
