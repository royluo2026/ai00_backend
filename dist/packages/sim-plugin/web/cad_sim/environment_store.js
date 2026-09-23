(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.AI00SimulationEnvironmentStore = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  function asGid(value, field) {
    if (typeof value !== 'string' || !/^\d+$/.test(value)) throw new Error(`${field || 'gid'}_invalid`);
    return value;
  }

  function createEnvironmentStore({ invoke, cache = null, getAuthSubjectGid = () => null, wait = ms => new Promise(resolve => setTimeout(resolve,ms)) }) {
    if (typeof invoke !== 'function') throw new TypeError('invoke_required');
    const listeners = new Set();
    let projectLoadPromise = null;
    let selectionGeneration = 0;
    let pendingWorkspaceGid = null;
    const state = {
      records: [], groups: [], workspace: null, currentKind: null, loading: false, error: null, errorAction: null,
      cacheStatus: 'idle', readOnly: false,
      projects: [], repositories: [], spaces: [],
      repositoryLoadError: null, failedRepositoryGids: new Set(),
      view: { selectedNodeGid: null, treeScrollTop: 0, modelScrollTop: 0 },
    };

    const emit = () => listeners.forEach(listener => listener(state));
    async function readSelectedWorkspace(capability, payload, current) {
      // Only the two read operations below use this helper; never replay writes.
      for (let attempt=0; attempt<3; attempt++) {
        if (!current()) return null;
        try { return await invoke(capability,payload); }
        catch (error) {
          const capacity = (error?.code || error?.message) === 'capacity_unavailable';
          if (!capacity || error.retryable === false || attempt === 2) {
            if (error && typeof error === 'object') error.capabilityId = capability;
            throw error;
          }
          if (!current()) return null;
          await wait(attempt === 0 ? 300 : 900);
        }
      }
    }
    const persistWorkspaceCache = async () => {
      const authSubjectGid = String(getAuthSubjectGid() || '');
      const workspace = state.workspace;
      if (!cache || !authSubjectGid || !workspace?.workspace_gid || !workspace.cache_revision_hash) return;
      try {
        const lease = await invoke('simulation.environment.workspace.cache_lease.get', {
          workspace_gid: workspace.workspace_gid,
        });
        await cache.putWorkspace({ authSubjectGid, workspaceGid: workspace.workspace_gid,
          rowVersion: workspace.row_version, cacheRevisionHash: workspace.cache_revision_hash,
          lease, workspace });
      } catch (error) {
        console.warn?.('[simulation-cache] mutation cache write ignored:', error?.message || error);
      }
    };
    const applyPatch = patch => {
      if (!state.workspace || !patch) return;
      const nodes = state.workspace.nodes || (state.workspace.nodes = []);
      const bindings = state.workspace.bindings || (state.workspace.bindings = []);
      if (patch.op === 'create') nodes.push({
        node_gid: asGid(patch.node_gid, 'node_gid'), parent_gid: patch.parent_gid,
        name: patch.name || '', node_type: patch.node_type || '', position: patch.position || 0,
      });
      if (patch.op === 'move') {
        const node = nodes.find(item => item.node_gid === patch.node_gid);
        if (node) node.parent_gid = patch.parent_gid;
      }
      if (patch.op === 'remove') {
        const removed = new Set(patch.removed_node_gids || []);
        state.workspace.nodes = nodes.filter(item => !removed.has(item.node_gid));
        state.workspace.bindings = bindings.filter(item => !removed.has(item.node_gid));
      }
      if (patch.op === 'bind') bindings.push({ ...patch });
      if (patch.op === 'unbind') state.workspace.bindings = bindings.filter(item => item.binding_gid !== patch.binding_gid);
      if (patch.op === 'update_workspace') Object.assign(state.workspace, patch);
    };
    const rebuildGroups = (repositories = [], spaces = []) => {
      state.repositories = repositories;
      state.spaces = spaces;
      const statusOrder = { active: 0, baseline: 1, frozen: 2, archived: 3 };
      const privateItems = state.records.map(item => ({ ...item, record_kind: 'private', record_gid: item.workspace_gid }))
        .sort((left, right) => (statusOrder[left.status] ?? 9) - (statusOrder[right.status] ?? 9));
      const projectByGid = new Map(state.projects.map(project => [
        String(project.gid || project.project_gid || project.id || ''), project,
      ]));
      const repositoryByProject = new Map(repositories.map(repository => [String(repository.project_gid || ''), repository]));
      const projectGids = [...new Set([...projectByGid.keys(), ...repositoryByProject.keys()].filter(Boolean))];
      const projectSpaces = [];
      const personalProjectSpaces = [];
      projectGids.forEach(projectGid => {
        const repository = repositoryByProject.get(projectGid);
        const project = projectByGid.get(projectGid) || {};
        const projectLabel = project.project_name || project.name || project.project_code || `项目 ${projectGid}`;
        const found = repository ? spaces.filter(item => String(item.repository_gid) === String(repository.repository_gid)) : [];
        const team = found.find(item => item.space_kind === 'team');
        const personal = found.find(item => item.space_kind === 'managed_personal');
        const lookupFailed = Boolean(state.repositoryLoadError)
          || Boolean(repository && state.failedRepositoryGids.has(String(repository.repository_gid)));
        const slot = (item, kind) => item
          ? { ...item, record_kind: kind, record_gid: item.space_gid, display_label: projectLabel, project_gid: projectGid }
          : { record_kind: kind, display_label: projectLabel, project_gid: projectGid,
            unavailable: true, status: lookupFailed ? '加载失败' : '待创建' };
        projectSpaces.push(slot(team, 'team'));
        personalProjectSpaces.push(slot(personal, 'managed_personal'));
      });
      state.groups = [
        { kind: 'project_spaces', label: '项目空间', items: projectSpaces },
        { kind: 'personal_project_spaces', label: '个人项目空间', items: personalProjectSpaces },
        { kind: 'private', label: '私人仿真环境', items: privateItems },
      ];
    };

    return {
      state,
      subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
      clearSelection() {
        ++selectionGeneration;
        pendingWorkspaceGid = null;
        Object.assign(state, { workspace: null, currentKind: null, loading: false, error: null,
          errorAction: null, cacheStatus: 'idle', readOnly: true });
        emit();
      },
      rememberView(next) { state.view = { ...state.view, ...next }; },
      applyOpenedDocument(workspaceGid,expectedRowVersion,result) {
        const workspace=state.workspace;
        if(workspace?.workspace_gid!==workspaceGid || pendingWorkspaceGid && pendingWorkspaceGid!==workspaceGid
          || workspace.row_version!==expectedRowVersion || !Number.isSafeInteger(result?.workspace_row_version)
          || result.workspace_row_version<expectedRowVersion || !result.document_gid || !result.document_session)return false;
        ++selectionGeneration;pendingWorkspaceGid=null;
        workspace.row_version=result.workspace_row_version;
        workspace.live_document={document_gid:result.document_gid,document_session:result.document_session,state:'bound'};
        delete workspace.cache_revision_hash;
        state.loading=false;state.readOnly=false;state.cacheStatus='authoritative';emit();return true;
      },
      applyServerUpdate(next) {
        const view = { ...state.view };
        if (next?.workspace) state.workspace = next.workspace;
        if (next?.records) state.records = next.records;
        if (next?.groups) state.groups = next.groups;
        state.view = view; emit();
      },
      async load() {
        await Promise.all([this.loadRecords(), this.loadProjectCandidates()]);
        let repositories = [], spaces = [];
        state.repositoryLoadError = null;
        state.failedRepositoryGids = new Set();
        try {
          const result = await invoke('craft.bop.repository.search', { page_size: 100 });
          repositories = result.items || [];
          for (const repository of repositories) {
            try {
              const page = await invoke('craft.bop.space.search', { repository_gid: repository.repository_gid, page_size: 100 });
              spaces.push(...(page.items || []));
            } catch (_) {
              state.failedRepositoryGids.add(String(repository.repository_gid));
            }
          }
        } catch (error) {
          state.repositoryLoadError = error;
        }
        rebuildGroups(repositories, spaces); emit();
        return state;
      },
      async loadSpaceVersions(spaceGid) {
        const space_gid = asGid(spaceGid, 'space_gid');
        const data = await invoke('craft.bop.space_version.search', { space_gid, page_size: 100 });
        return data.items || [];
      },
      async ensureForkVersions(record) {
        const existing = await this.loadSpaceVersions(record.space_gid);
        if (existing.length) return existing;
        const saved = await invoke('craft.bop.space_version.save', {
          space_gid: asGid(record.space_gid, 'space_gid'),
          expected_head_version: Number(record.head_row_version || record.row_version || 1),
          version_kind: 'saved', source_refs: [], algorithm_versions: {},
          idempotency_key: `space-save-for-fork-${Date.now()}-${record.space_gid}`,
        });
        return [saved];
      },
      async ensurePrivateForkVersions(record) {
        const workspace_gid = asGid(record.workspace_gid, 'workspace_gid');
        const found = await invoke('simulation.environment.workspace_version.search', { workspace_gid });
        if (found.items?.length) return found.items;
        if (record.is_owner === false) throw new Error('source_version_not_immutable');
        const frozen = await invoke('simulation.environment.version.freeze', {
          workspace_gid, expected_row_version: Number(record.row_version), algorithms: {},
          idempotency_key: `workspace-freeze-for-fork-${Date.now()}-${workspace_gid}`,
        });
        record.row_version += 1;
        if (state.workspace?.workspace_gid === workspace_gid) state.workspace.row_version = record.row_version;
        return [{ version_gid: asGid(frozen.version_gid, 'version_gid'), workspace_gid,
          status: 'frozen', content_hash: frozen.content_hash, sequence: 1 }];
      },
      async forkRepository({ sourceVersionGid, targetProjectGid, targetName, targetProjectName, forkDepth,
        includePersonalMigration = false, expectedTargetSlot = 0 }) {
        const normalizedTargetName = String(targetName || '').trim();
        if (!normalizedTargetName) throw new Error('fork_name_required');
        const normalizedProjectName = String(targetProjectName || targetProjectGid || '').trim();
        if (!normalizedProjectName) throw new Error('fork_target_project_required');
        const preview = await invoke('craft.bop.repository.fork.preview', {
          source_version_gid: asGid(sourceVersionGid, 'source_version_gid'),
          target_project_gid: asGid(targetProjectGid, 'target_project_gid'),
          target_name: normalizedTargetName,
          target_project_name: normalizedProjectName,
          fork_depth: forkDepth, include_personal_migration: !!includePersonalMigration,
          expected_target_slot: expectedTargetSlot,
          idempotency_key: `repository-fork-preview-${Date.now()}-${sourceVersionGid}`,
        });
        const result = await invoke('craft.bop.repository.fork.apply', {
          preview_gid: asGid(preview.preview_gid, 'preview_gid'), plan_hash: preview.plan_hash,
          allowed_decisions: preview.allowed_decisions || [], expected_target_slot: expectedTargetSlot,
          idempotency_key: `repository-fork-apply-${Date.now()}-${preview.preview_gid}`,
        });
        const repository = { repository_gid: asGid(result.repository_gid, 'repository_gid'),
          project_gid: String(targetProjectGid), row_version: 1, lifecycle_status: 'active' };
        const team = { space_gid: asGid(result.team_space_gid, 'team_space_gid'),
          repository_gid: repository.repository_gid, space_kind: 'team', row_version: 1 };
        rebuildGroups([repository, ...state.repositories], [team, ...state.spaces]);
        state.error = null; state.errorAction = null; emit();
        return result;
      },
      async forkPersonal({ sourceVersionGid, targetRepositoryGid, forkDepth,
        workflowGid = null, expectedTargetSlot = 0 }) {
        const preview = await invoke('craft.bop.managed_personal_space.fork.preview', {
          source_version_gid: asGid(sourceVersionGid, 'source_version_gid'),
          target_repository_gid: asGid(targetRepositoryGid, 'target_repository_gid'),
          fork_depth: forkDepth, ...(workflowGid ? { workflow_gid: asGid(workflowGid, 'workflow_gid') } : {}),
          expected_target_slot: expectedTargetSlot,
          idempotency_key: `personal-fork-preview-${Date.now()}-${sourceVersionGid}`,
        });
        const result = await invoke('craft.bop.managed_personal_space.fork.apply', {
          preview_gid: asGid(preview.preview_gid, 'preview_gid'), plan_hash: preview.plan_hash,
          allowed_decisions: preview.allowed_decisions || [], expected_target_slot: expectedTargetSlot,
          idempotency_key: `personal-fork-apply-${Date.now()}-${preview.preview_gid}`,
        });
        const personal = { space_gid: asGid(result.personal_space_gid, 'personal_space_gid'),
          repository_gid: String(targetRepositoryGid), space_kind: 'managed_personal', row_version: 1 };
        rebuildGroups(state.repositories, [personal, ...state.spaces]);
        state.error = null; state.errorAction = null; emit();
        return result;
      },
      async forkPrivate({ sourceWorkspaceGid, sourceVersionGid, targetName, targetVersionLabel, forkDepth }) {
        const preview = await invoke('simulation.environment.workspace.fork.preview', {
          source_workspace_gid: asGid(sourceWorkspaceGid, 'source_workspace_gid'),
          source_version_gid: asGid(sourceVersionGid, 'source_version_gid'),
          fork_depth: String(forkDepth || ''),
          target_name: String(targetName || '').trim(), target_version_label: String(targetVersionLabel || 'V1').trim(),
        });
        const result = await invoke('simulation.environment.workspace.fork.apply', {
          preview_gid: asGid(preview.preview_gid, 'preview_gid'), plan_hash: preview.plan_hash,
          idempotency_key: `workspace-fork-apply-${Date.now()}-${preview.preview_gid}`,
        });
        result.workspace_gid = asGid(result.workspace_gid, 'workspace_gid');
        state.records = [result, ...state.records.filter(item => item.workspace_gid !== result.workspace_gid)];
        state.workspace = result; state.currentKind = 'private';
        rebuildGroups(state.repositories, state.spaces);
        state.error = null; state.errorAction = null; emit();
        return result;
      },
      async deleteRecord(kind, record) {
        if (!record) throw new Error('record_required');
        let capability, payload;
        if (kind === 'private') {
          capability = 'simulation.environment.workspace.delete';
          payload = { workspace_gid: asGid(record.workspace_gid, 'workspace_gid'),
            expected_row_version: record.row_version,
            idempotency_key: `workspace-delete-${Date.now()}-${record.workspace_gid}` };
        } else if (kind === 'managed_personal') {
          capability = 'craft.bop.managed_personal_space.delete';
          payload = { space_gid: asGid(record.space_gid, 'space_gid'),
            expected_row_version: record.row_version,
            idempotency_key: `personal-delete-${Date.now()}-${record.space_gid}` };
        } else if (kind === 'team') {
          const repository = state.repositories.find(item => item.repository_gid === record.repository_gid);
          if (!repository) throw new Error('repository_required');
          capability = 'craft.bop.repository.delete';
          payload = { repository_gid: asGid(repository.repository_gid, 'repository_gid'),
            expected_row_version: repository.row_version, reason: 'owner_requested_cleanup',
            idempotency_key: `repository-delete-${Date.now()}-${repository.repository_gid}` };
        } else throw new Error('record_kind_invalid');
        try {
          const result = await invoke(capability, payload);
          if (kind === 'private') state.records = state.records.filter(item => item.workspace_gid !== record.workspace_gid);
          if (kind === 'managed_personal') state.spaces = state.spaces.filter(item => item.space_gid !== record.space_gid);
          if (kind === 'team') {
            state.repositories = state.repositories.filter(item => item.repository_gid !== record.repository_gid);
            state.spaces = state.spaces.filter(item => item.repository_gid !== record.repository_gid);
          }
          const selected = state.workspace?.workspace_gid;
          if (selected === record.workspace_gid || selected === record.space_gid) {
            state.workspace = null; state.currentKind = null;
          }
          rebuildGroups(state.repositories, state.spaces);
          state.error = null; state.errorAction = null; emit();
          return result;
        } catch (error) { state.error = error; state.errorAction = '删除失败'; emit(); throw error; }
      },
      async loadRecords(cursor) {
        const workspaceAtStart = state.workspace?.workspace_gid || null;
        state.loading = true; emit();
        try {
          const data = await invoke('simulation.environment.workspace.search', { page_size: 50, ...(cursor ? { cursor } : {}) });
          const items = data.items || [];
          const current = state.currentKind === 'private'
            && state.workspace?.workspace_gid
            && state.workspace.workspace_gid !== workspaceAtStart
            ? state.workspace : null;
          state.records = current
            ? [current, ...items.filter(item => item.workspace_gid !== current.workspace_gid)]
            : items;
          rebuildGroups(state.repositories || [], state.spaces || []);
          state.error = null; state.errorAction = null;
          return state.records;
        } catch (error) { state.error = error; state.errorAction = '加载失败'; throw error; }
        finally { state.loading = false; emit(); }
      },
      async loadProjectCandidates() {
        if (state.projects.length) return state.projects;
        if (!projectLoadPromise) projectLoadPromise = (async () => {
          try {
            const data = await invoke('project.project.read.atomic.projects_search', { arguments: {} });
            state.projects = Array.isArray(data) ? data : (data?.data || data?.items || []);
          } catch (_) { state.projects = []; }
          finally { projectLoadPromise = null; }
          return state.projects;
        })();
        return projectLoadPromise;
      },
      async createWorkspace(draft) {
        const payload = { ...draft, name: String(draft?.name || '').trim() };
        if (!payload.name || payload.name.length > 255) throw new Error('workspace_name_invalid');
        state.loading = true; emit();
        try {
          const data = await invoke('simulation.environment.workspace.create', payload);
          data.workspace_gid = asGid(data.workspace_gid, 'workspace_gid');
          data.nodes = data.nodes || [];
          data.bindings = data.bindings || [];
          state.records = [data, ...state.records.filter(item => item.workspace_gid !== data.workspace_gid)];
          state.workspace = data;
          state.currentKind = 'private';
          rebuildGroups(state.repositories || [], state.spaces || []);
          state.view = { selectedNodeGid: null, treeScrollTop: 0, modelScrollTop: 0 };
          state.error = null; state.errorAction = null;
          await persistWorkspaceCache();
          return data;
        } catch (error) { state.error = error; state.errorAction = '创建失败'; throw error; }
        finally { state.loading = false; emit(); }
      },
      async updateWorkspace(draft) {
        if (state.currentKind !== 'private' || !state.workspace?.is_owner) throw new Error('workspace_owner_required');
        const payload = {
          ...draft, workspace_gid: state.workspace.workspace_gid,
          expected_row_version: state.workspace.row_version,
          idempotency_key: `workspace-edit-${Date.now()}-${state.workspace.workspace_gid}`,
        };
        const result = await this.mutate('simulation.environment.workspace.update', payload);
        const index = state.records.findIndex(item => item.workspace_gid === state.workspace.workspace_gid);
        if (index >= 0) state.records[index] = { ...state.records[index], ...draft, row_version: result.row_version };
        rebuildGroups(state.repositories || [], state.spaces || []);
        emit();
        return result;
      },
      async openWorkspace(workspaceGid, { isCurrent = () => true } = {}) {
        const workspace_gid = asGid(workspaceGid, 'workspace_gid');
        if (!isCurrent()) return null;
        const generation = ++selectionGeneration;
        pendingWorkspaceGid = workspace_gid;
        const current = () => generation === selectionGeneration && isCurrent();
        const authSubjectGid = String(getAuthSubjectGid() || '');
        state.loading = true; state.cacheStatus = 'validating'; state.readOnly = true; emit();
        try {
          let lease = null;
          if (cache && authSubjectGid) {
            try {
              lease = await readSelectedWorkspace('simulation.environment.workspace.cache_lease.get', { workspace_gid }, current);
              if (!current()) return null;
            } catch (error) {
              if (!current()) return null;
              const code = error?.code || error?.message || '';
              if (['permission_denied', 'resource_scope_denied', 'workspace_not_found'].includes(code)) {
                try { await cache.clearLocal?.({ authSubjectGid }); } catch (_) {}
                if (!current()) return null;
                state.workspace = null; state.currentKind = null; state.cacheStatus = 'denied';
                throw error;
              }
              if (code !== 'cache_lease_signing_key_unavailable') {
                try {
                  const offline = await cache.getWorkspace({ authSubjectGid, workspaceGid: workspace_gid });
                  if (!current()) return null;
                  if (offline?.workspace) {
                    state.workspace = offline.workspace; state.currentKind = 'private';
                    state.cacheStatus = 'offline'; state.error = null; state.errorAction = null;
                    return state.workspace;
                  }
                } catch (_) { /* cache failure falls through to the original error */ }
                throw error;
              }
              console.warn?.('[simulation-cache] lease unavailable; using authoritative workspace read');
            }
            if (lease) {
              try {
                const cached = await cache.getWorkspace({ authSubjectGid, workspaceGid: workspace_gid, lease });
                if (!current()) return null;
                if (cached?.workspace) {
                  state.workspace = cached.workspace; state.currentKind = 'private';
                  state.cacheStatus = 'validated'; state.readOnly = false;
                  state.error = null; state.errorAction = null;
                  return state.workspace;
                }
              } catch (error) {
                console.warn?.('[simulation-cache] read ignored:', error?.message || error);
              }
            }
          }
          const data = await readSelectedWorkspace('simulation.environment.workspace.get', { workspace_gid }, current);
          if (!current()) return null;
          data.workspace_gid = asGid(data.workspace_gid, 'workspace_gid');
          state.workspace = data;
          state.currentKind = 'private';
          state.cacheStatus = 'authoritative'; state.readOnly = false;
          state.error = null; state.errorAction = null;
          if (cache && authSubjectGid && lease && data.cache_revision_hash) {
            try {
              await cache.putWorkspace({ authSubjectGid, workspaceGid: workspace_gid,
                rowVersion: data.row_version, cacheRevisionHash: data.cache_revision_hash,
                lease, workspace: data });
            } catch (error) {
              console.warn?.('[simulation-cache] write ignored:', error?.message || error);
            }
          }
          return current() ? data : null;
        } catch (error) {
          if (!current()) return null;
          state.error = error; state.errorAction = '加载失败'; throw error;
        } finally {
          if (generation === selectionGeneration) { pendingWorkspaceGid=null;state.loading = false; emit(); }
        }
      },
      async openRecord(kind, recordOrGid, { isCurrent = () => true } = {}) {
        const record = typeof recordOrGid === 'object' && recordOrGid ? recordOrGid : null;
        const gid = record?.record_gid || record?.workspace_gid || record?.space_gid || recordOrGid;
        if (kind === 'private') return this.openWorkspace(gid, { isCurrent });
        const space_gid = asGid(gid, 'space_gid');
        if (!isCurrent()) return null;
        const generation = ++selectionGeneration;
        let data;
        try { data = await invoke('craft.bop.space.get', { space_gid }); }
        catch (error) {
          if (generation !== selectionGeneration || !isCurrent()) return null;
          throw error;
        }
        if (generation !== selectionGeneration || !isCurrent()) return null;
        state.workspace = {
          ...data, workspace_gid: space_gid, display_label: record?.display_label || data.display_label,
          nodes: data.nodes || [], bindings: data.bindings || [],
        };
        state.currentKind = kind; state.loading = false; state.error = null; emit();
        return state.workspace;
      },
      async mutate(capability, payload) {
        if (!state.workspace) throw new Error('workspace_required');
        if (state.readOnly) throw new Error('workspace_read_only');
        const workspace_gid = asGid(payload.workspace_gid, 'workspace_gid');
        if (workspace_gid !== state.workspace.workspace_gid) throw new Error('workspace_mismatch');
        const result = await invoke(capability, payload);
        applyPatch(result.patch);
        state.workspace.row_version = result.row_version;
        if (result.cache_revision_hash) state.workspace.cache_revision_hash = result.cache_revision_hash;
        await persistWorkspaceCache();
        state.error = null; state.errorAction = null;
        emit();
        return result;
      },
      async bindOccurrence({ nodeGid, occurrenceGid, role = 'operate', idempotencyKey }) {
        if (state.currentKind !== 'private' || !state.workspace) throw new Error('editable_private_workspace_required');
        return this.mutate('simulation.environment.binding.create', {
          workspace_gid: state.workspace.workspace_gid,
          expected_row_version: state.workspace.row_version,
          idempotency_key: idempotencyKey,
          node_gid: asGid(nodeGid, 'node_gid'), occurrence_gid: asGid(occurrenceGid, 'occurrence_gid'), role,
        });
      },
      applyPatch,
    };
  }

  return { asGid, createEnvironmentStore };
});
