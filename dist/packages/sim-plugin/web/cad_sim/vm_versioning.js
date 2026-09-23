(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.AI00VmVersioning = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const preferenceKey = (subject, workspace) => `ai00.simulation.vm-versioning:${subject}:${workspace}`;
  const key = prefix => `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;

  function createVmVersioningController({ invoke, captureSnapshot, cache = null, getAuthSubjectGid = () => null,
    storage = typeof localStorage !== 'undefined' ? localStorage : null, onChange = () => {} } = {}) {
    if (typeof invoke !== 'function') throw new TypeError('invoke is required');
    const state = { lastSnapshot: null, lastCheckpoint: null, report: null, items: [], error: null, busy: false };
    const publish = () => onChange({ ...state, items: [...state.items] });
    const subject = () => String(getAuthSubjectGid() || 'anonymous');
    const readPreference = workspace => {
      try { return JSON.parse(storage?.getItem(preferenceKey(subject(), workspace)) || '{}'); }
      catch (_) { return {}; }
    };
    const writePreference = (workspace, patch) => {
      const value = { ...readPreference(workspace), ...patch };
      storage?.setItem(preferenceKey(subject(), workspace), JSON.stringify(value));
      return value;
    };
    const call = async (id, payload) => invoke(id, payload, { version: 1,
      ...(id.endsWith('.get') || id.endsWith('.search') ? {} : { idempotencyKey: payload.idempotency_key }) });
    const controller = {
      state,
      isAutomaticComparisonEnabled(workspaceGid) { return readPreference(String(workspaceGid)).automatic === true; },
      setAutomaticComparison({ workspaceGid, enabled }) {
        writePreference(String(workspaceGid), { automatic: enabled === true }); publish();
      },
      async listCheckpoints(workspaceGid) {
        return call('simulation.vm_checkpoint.search', { workspace_gid: String(workspaceGid), page_size: 200 });
      },
      async createCheckpoint({ workspaceGid, scope = 'personal', name, note = '', snapshot = null }) {
        state.busy = true; state.error = null; publish();
        try {
          const fresh = snapshot || await captureSnapshot?.();
          if (!fresh?.snapshot_request_id || !fresh?.snapshot_hash) throw new Error('fresh_vm_snapshot_required');
          state.lastSnapshot = fresh;
          const checkpoint = await call('simulation.vm_checkpoint.create', { workspace_gid: String(workspaceGid),
            snapshot_request_id: fresh.snapshot_request_id, snapshot_hash: fresh.snapshot_hash, scope,
            name: String(name || '').trim(), note: String(note || '').trim(), idempotency_key: key('vm-checkpoint') });
          state.lastCheckpoint = checkpoint; publish();
          cache?.putSnapshotSummary?.({ authSubjectGid: subject(), workspaceGid: String(workspaceGid), snapshot: checkpoint }).catch?.(() => {});
          return { ...checkpoint, snapshot_request_id: fresh.snapshot_request_id, snapshot_hash: fresh.snapshot_hash };
        } catch (error) { state.error = { code: error.code || error.message, message: error.message }; publish(); throw error; }
        finally { state.busy = false; publish(); }
      },
      async loadReport(reportGid, cursor = null) {
        const report = await call('simulation.vm_diff_report.get', { report_gid: String(reportGid) });
        const page = await call('simulation.vm_diff_item.search', { report_gid: String(reportGid), page_size: 200,
          ...(cursor ? { cursor } : {}) });
        state.report = report; state.items = page.items || []; publish();
        cache?.putDiffSummary?.({ authSubjectGid: subject(), workspaceGid: String(report.workspace_gid), report }).catch?.(() => {});
        return { report, items: state.items, nextCursor: page.next_cursor };
      },
      async compareNow({ beforeCheckpointGid, afterCheckpointGid }) {
        const report = await call('simulation.vm_diff_report.generate', {
          before_checkpoint_gid: String(beforeCheckpointGid), after_checkpoint_gid: String(afterCheckpointGid),
          report_kind: 'manual', algorithm_version: 'vm-diff-v1', idempotency_key: key('vm-diff'),
        });
        return controller.loadReport(report.report_gid);
      },
      async onFreshSnapshot(snapshot) {
        const workspace = String(snapshot.workspaceGid || snapshot.workspace_gid || '');
        state.lastSnapshot = snapshot; publish();
        if (!workspace || !controller.isAutomaticComparisonEnabled(workspace)) return null;
        const preference = readPreference(workspace);
        const checkpoint = await controller.createCheckpoint({ workspaceGid: workspace, scope: 'personal',
          name: `自动快照 ${new Date().toLocaleString()}`, snapshot });
        writePreference(workspace, { lastCheckpointGid: checkpoint.checkpoint_gid });
        if (!preference.lastCheckpointGid) return checkpoint;
        const report = await call('simulation.vm_diff_report.generate', {
          before_checkpoint_gid: preference.lastCheckpointGid, after_checkpoint_gid: checkpoint.checkpoint_gid,
          report_kind: 'automatic', algorithm_version: 'vm-diff-v1', idempotency_key: key('vm-diff-auto'),
        });
        return controller.loadReport(report.report_gid);
      },
    };
    return controller;
  }

  return { createVmVersioningController };
});
