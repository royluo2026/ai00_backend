'use strict';

(function(root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.SimulationCaptureWorkflow = api;
})(typeof window !== 'undefined' ? window : globalThis, function() {
  const CAPABILITY_VERSIONS = Object.freeze({
    'simulation.document_snapshot.request': 2,
    'simulation.document_snapshot.get': 1,
    'simulation.document_snapshot.action.get': 1,
    'simulation.document_snapshot.dispatch': 1,
    'simulation.environment.bop_vm_binding_draft.preview': 1,
    'simulation.environment.compose': 2,
    'simulation.environment.preflight': 1,
    'simulation.environment.materialize': 2,
    'simulation.materialization_run.action.get': 1,
    'simulation.materialization_run.dispatch': 1,
    'simulation.capture_run.start': 2,
    'simulation.capture_run.get': 1,
    'simulation.capture_run.action.get': 1,
    'simulation.capture_run.dispatch': 1,
    'simulation.capture_run.cancel': 1,
    'simulation.capture_step.retry': 1,
  });
  const ALLOWED_CALLS = Object.freeze(Object.keys(CAPABILITY_VERSIONS));
  const WRITE_CALLS = new Set([
    'simulation.document_snapshot.request', 'simulation.document_snapshot.dispatch',
    'simulation.environment.compose', 'simulation.environment.materialize',
    'simulation.materialization_run.dispatch', 'simulation.capture_run.start',
    'simulation.capture_run.dispatch', 'simulation.capture_run.cancel',
    'simulation.capture_step.retry',
  ]);
  const USER_CONFIRMED_CALLS = new Set([
    'simulation.document_snapshot.request', 'simulation.environment.compose',
    'simulation.environment.materialize', 'simulation.capture_run.start',
    'simulation.capture_run.cancel', 'simulation.capture_step.retry',
  ]);
  const DOWNSTREAM_CALLS = new Set([
    'simulation.connector.plan.queue', 'craft.process_screenshot.attach',
  ]);
  const TERMINAL = new Set([
    'completed', 'failed', 'partial', 'cancelled', 'outcome_unknown',
  ]);

  function resolveCaptureLine(entries, selectedGid) {
    if (typeof selectedGid !== 'string') return null;
    const visited = new Set();
    let current = selectedGid;
    while (current && !visited.has(current) && visited.size < 256) {
      visited.add(current);
      const entry = entries[current];
      if (!entry) return null;
      if (entry.node_type === 'line_process') return String(entry.gid);
      current = entry.parent_gid;
    }
    return null;
  }

  function unwrap(response, capabilityId, version) {
    const envelope = response && response.success === true ? response.data : response;
    if (!envelope || response?.success === false || envelope.ok === false) {
      const detail = envelope?.error || response?.detail || response?.error || {};
      const error = new Error(
        detail.message || detail.code || `能力调用失败：${capabilityId}@${version}`,
      );
      error.code = detail.code || 'capability_invocation_failed';
      error.retryable = detail.retryable === true;
      throw error;
    }
    if (envelope.status === 'accepted' && envelope.operation_ref) return envelope.operation_ref;
    return envelope.data !== undefined ? envelope.data : envelope;
  }

  function resolveHierarchyCaptureSource(hierarchy, selectedNodeGid) {
    if (!hierarchy?.source_bop_version_gid || !Array.isArray(hierarchy.nodes)) return null;
    const entries = Object.fromEntries(hierarchy.nodes.map(node => [node.node_gid, { ...node, gid: node.node_gid }]));
    const lineGid = resolveCaptureLine(entries, selectedNodeGid);
    const line = entries[lineGid];
    if (!line?.source_bop_node_gid) return null;
    return { version_gid: hierarchy.source_bop_version_gid, line_gid: line.source_bop_node_gid,
      workspace_gid: hierarchy.workspace_gid, hierarchy_gid: hierarchy.hierarchy_gid, name: line.name };
  }

  async function readCaptureExecutionSource(invoke, source) {
    const structure = await invoke('craft.bop.execution_structure.get', { version_gid: source.version_gid });
    if (structure?.official !== true || structure.source?.bop_version_gid !== source.version_gid
        || !Number.isInteger(structure.source?.revision) || structure.source.revision < 1
        || !/^sha256:[0-9a-f]{64}$/.test(structure.content_hash || '')
        || !Array.isArray(structure.nodes)
        || !structure.nodes.some(node => node.node_id === source.line_gid && node.kind === 'line_process')) {
      throw new Error('capture_execution_source_mismatch');
    }
    return { version_gid: source.version_gid, revision: structure.source.revision, content_hash: structure.content_hash };
  }

  function randomKey(prefix) {
    const suffix = globalThis.crypto?.randomUUID?.()
      || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    return `${prefix}-${suffix}`;
  }

  function createGatewayApi(fetcher, options = {}) {
    if (typeof fetcher !== 'function') {
      throw new TypeError('authenticated gateway fetcher is required');
    }
    const approve = typeof options.approve === 'function'
      ? options.approve : (async () => false);

    return {
      async invoke(capabilityId, payload, invokeOptions = {}) {
        if (!ALLOWED_CALLS.includes(capabilityId)) {
          throw new Error(`capability_not_allowed:${capabilityId}`);
        }
        const version = Number(
          invokeOptions.version || CAPABILITY_VERSIONS[capabilityId],
        );
        const idempotencyKey = WRITE_CALLS.has(capabilityId)
          ? (invokeOptions.idempotencyKey || randomKey(capabilityId)) : undefined;
        if(invokeOptions.confirmationToken)throw new Error('raw_confirmation_not_allowed');
        const handle=invokeOptions.downstreamAction?.confirmation_handle;
        if(invokeOptions.downstreamAction&&!handle)throw new Error('capture_receipt_required');
        const response = await fetcher(capabilityId,
          { version, payload, idempotency_key: idempotencyKey, ...(handle?{capture_receipt:{handle}}:{}) },
          () => approve(capabilityId, version, payload, { idempotencyKey }),
        );
        return unwrap(response, capabilityId, version);
      },
    };
  }

  function createCaptureWorkflow({ invoke, setTimer = setTimeout, onChange = () => {} } = {}) {
    if (typeof invoke !== 'function') throw new TypeError('invoke is required');
    const state = {
      environmentId: '', environmentVersion: 0, deviceId: '', preflight: null,
      snapshotRequest: null, bindingDraft: null, materializationRun: null, captureRun: null,
      error: null, polling: false, busy: false,
    };
    const publish = () => onChange({ ...state });
    const call = async (id, payload, options = {}) => {
      if (!ALLOWED_CALLS.includes(id)) throw new Error(`capability_not_allowed:${id}`);
      try {
        state.error = null;
        const result = await invoke(id, payload, {
          version: CAPABILITY_VERSIONS[id], ...options,
        });
        publish();
        return result;
      } catch (error) {
        state.error = {
          code: error.code || 'capability_invocation_failed', message: error.message,
        };
        publish();
        throw error;
      }
    };
    const wait = () => new Promise(resolve => setTimer(resolve, 2000));
    const active = () => state.busy || Boolean(state.captureRun && !TERMINAL.has(state.captureRun.status));
    const environmentPayload = () => ({
      environment_id: state.environmentId,
      environment_version: state.environmentVersion,
      device_id: state.deviceId,
    });
    const dispatchPrepared = async (actionId, actionPayload, dispatchId, dispatchPayload) => {
      const actionResult = await call(actionId, actionPayload);
      if (!actionResult.action) return null;
      return call(dispatchId, dispatchPayload, {
        downstreamAction: actionResult.action,
        idempotencyKey: `dispatch:${actionResult.action.idempotency_key}`,
      });
    };
    const schedulePoll = () => {
      if (!state.polling || !state.captureRun || TERMINAL.has(state.captureRun.status)) return;
      setTimer(async () => {
        try { await workflow.refresh(); } catch (_) { state.polling = false; publish(); }
        finally { schedulePoll(); }
      }, 2000);
    };
    const workflow = {
      state,
      setEnvironment(environmentId, environmentVersion) {
        if (state.environmentId === String(environmentId || '')
            && state.environmentVersion === Number(environmentVersion || 0)) return;
        if (active()) throw new Error('capture_run_active');
        state.environmentId = String(environmentId || '');
        state.environmentVersion = Number(environmentVersion || 0);
        state.preflight = null;
        state.materializationRun = null;
        state.captureRun = null;
        state.polling = false;
        publish();
      },
      async compose(payload) {
        if (!payload?.snapshot_request_id) throw new Error('active_document_snapshot_required');
        const result = await call('simulation.environment.compose', payload, {
          idempotencyKey: randomKey('compose'),
        });
        if (result.status === 'composed') {
          workflow.setEnvironment(result.environment_id, result.environment_version);
        }
        return result;
      },
      async composeFromActiveDocument(payload) {
        if (active()) throw new Error('capture_run_active');
        const deviceId = String(payload?.device_id || '');
        if (!deviceId) throw new Error('connector_required');
        state.deviceId = deviceId;
        state.snapshotRequest = await call('simulation.document_snapshot.request', {
          device_id: deviceId, request_key: randomKey('document-snapshot'),
        }, { idempotencyKey: randomKey('document-snapshot-request') });
        state.snapshotRequest = await dispatchPrepared(
          'simulation.document_snapshot.action.get',
          { snapshot_request_id: state.snapshotRequest.snapshot_request_id },
          'simulation.document_snapshot.dispatch',
          { snapshot_request_id: state.snapshotRequest.snapshot_request_id },
        ) || state.snapshotRequest;
        let polls = 0;
        while (state.snapshotRequest.status === 'queued' && polls++ < 150) {
          await wait();
          state.snapshotRequest = await call('simulation.document_snapshot.get', {
            snapshot_request_id: state.snapshotRequest.snapshot_request_id,
          });
        }
        if (state.snapshotRequest.status !== 'completed') {
          const error = new Error(
            state.snapshotRequest.failure_code || 'active_document_snapshot_required',
          );
          error.code = state.snapshotRequest.failure_code || 'active_document_snapshot_required';
          throw error;
        }
        state.bindingDraft = await call(
          'simulation.environment.bop_vm_binding_draft.preview', {
            execution_plan_ref: payload.execution_plan_ref,
            snapshot_request_id: state.snapshotRequest.snapshot_request_id,
          },
        );
        return workflow.compose({
          ...payload,
          snapshot_request_id: state.snapshotRequest.snapshot_request_id,
        });
      },
      async selectConnector(deviceId) {
        if (String(deviceId || '') !== state.deviceId) {
          if (active()) throw new Error('capture_run_active');
          state.materializationRun = null;
          state.captureRun = null;
        }
        state.deviceId = String(deviceId || '');
        if (!state.environmentId || !state.environmentVersion || !state.deviceId) {
          state.preflight = null;
          publish();
          return null;
        }
        state.preflight = await call(
          'simulation.environment.preflight', environmentPayload(),
        );
        publish();
        return state.preflight;
      },
      canStartCapture() {
        return Boolean(
          state.environmentId && state.environmentVersion
          && state.deviceId && state.preflight?.compatible && !active(),
        );
      },
      async dispatchNext() {
        if (!state.captureRun?.capture_run_id) return null;
        const captureRunId = state.captureRun.capture_run_id;
        const dispatched = await dispatchPrepared(
          'simulation.capture_run.action.get',
          { capture_run_id: captureRunId },
          'simulation.capture_run.dispatch',
          { capture_run_id: captureRunId },
        );
        if (dispatched) state.captureRun = dispatched;
        return dispatched;
      },
      async startCapture() {
        if (active()) throw new Error('capture_run_active');
        if (!workflow.canStartCapture()) throw new Error('connector_preflight_required');
        state.busy = true;
        publish();
        try {
        const prepareMaterialization = async () => {
          state.materializationRun = await call(
            'simulation.environment.materialize', environmentPayload(),
            { idempotencyKey: randomKey('materialize') },
          );
          state.materializationRun = await dispatchPrepared(
            'simulation.materialization_run.action.get',
            { run_id: state.materializationRun.run_id },
            'simulation.materialization_run.dispatch',
            { run_id: state.materializationRun.run_id },
          ) || state.materializationRun;
          publish();
          return { phase: 'materializing', ...state.materializationRun };
        };
        if (!state.materializationRun) {
          return await prepareMaterialization();
        }
        try {
          state.captureRun = await call(
            'simulation.capture_run.start', environmentPayload(),
            { idempotencyKey: randomKey('capture') },
          );
        } catch (error) {
          if (error.code !== 'simulation_result_not_ready') throw error;
          state.materializationRun = null;
          return await prepareMaterialization();
        }
        await workflow.dispatchNext();
        state.polling = !TERMINAL.has(state.captureRun.status);
        publish();
        schedulePoll();
        return state.captureRun;
        } finally { state.busy = false; publish(); }
      },
      async refresh() {
        if (!state.captureRun?.capture_run_id) return null;
        state.captureRun = await call('simulation.capture_run.get', {
          capture_run_id: state.captureRun.capture_run_id,
        });
        if (!TERMINAL.has(state.captureRun.status)) await workflow.dispatchNext();
        state.polling = !TERMINAL.has(state.captureRun.status);
        publish();
        return state.captureRun;
      },
      async cancel() {
        if (!state.captureRun?.capture_run_id) return null;
        const result = await call('simulation.capture_run.cancel', {
          capture_run_id: state.captureRun.capture_run_id,
        }, { idempotencyKey: randomKey('cancel') });
        state.polling = result.status === 'cancelling';
        state.captureRun = { ...state.captureRun, status: result.status };
        publish();
        return result;
      },
      async retry(operationId) {
        if (!state.captureRun?.capture_run_id) throw new Error('capture_run_required');
        const result = await call('simulation.capture_step.retry', {
          capture_run_id: state.captureRun.capture_run_id,
          operation_id: operationId,
        }, { idempotencyKey: randomKey('retry') });
        state.captureRun = { ...state.captureRun, status: result.status };
        state.polling = true;
        schedulePoll();
        return result;
      },
      async captureActiveDocument(deviceId) {
        deviceId = String(deviceId || '');
        if (!deviceId) throw new Error('connector_required');
        state.deviceId = deviceId;
        state.snapshotRequest = await call('simulation.document_snapshot.request', {
          device_id: deviceId, request_key: randomKey('document-snapshot'),
        }, { idempotencyKey: randomKey('document-snapshot-request') });
        state.snapshotRequest = await dispatchPrepared(
          'simulation.document_snapshot.action.get',
          { snapshot_request_id: state.snapshotRequest.snapshot_request_id },
          'simulation.document_snapshot.dispatch',
          { snapshot_request_id: state.snapshotRequest.snapshot_request_id },
        ) || state.snapshotRequest;
        let polls = 0;
        while (state.snapshotRequest.status === 'queued' && polls++ < 150) {
          await wait();
          state.snapshotRequest = await call('simulation.document_snapshot.get', {
            snapshot_request_id: state.snapshotRequest.snapshot_request_id,
          });
        }
        if (state.snapshotRequest.status !== 'completed') {
          const error = new Error(state.snapshotRequest.failure_code || 'active_document_snapshot_required');
          error.code = state.snapshotRequest.failure_code || 'active_document_snapshot_required';
          throw error;
        }
        return state.snapshotRequest;
      },
    };
    return workflow;
  }

  return {
    ALLOWED_CALLS, CAPABILITY_VERSIONS, createCaptureWorkflow, createGatewayApi, resolveCaptureLine,
    resolveHierarchyCaptureSource, readCaptureExecutionSource,
  };
});
