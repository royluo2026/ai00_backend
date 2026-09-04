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
    return envelope.data !== undefined ? envelope.data : envelope;
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

    async function gatewayPost(route, body) {
      return fetcher(route, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
    }

    async function confirm(
      capabilityId, version, payload, idempotencyKey, payloadHash = null,
    ) {
      if (!await approve(capabilityId, version, payload, {
        idempotencyKey, payloadHash,
      })) throw new Error('user_cancelled');
      const response = await gatewayPost(
        `/api/v1/capabilities/${encodeURIComponent(capabilityId)}:confirm`,
        { version, payload, idempotency_key: idempotencyKey },
      );
      return unwrap(response, capabilityId, version).confirmation_token;
    }

    async function confirmDownstream(action) {
      if (!action || !DOWNSTREAM_CALLS.has(action.capability_id)) {
        throw new Error('downstream_action_not_allowed');
      }
      return confirm(
        action.capability_id,
        Number(action.major_version),
        JSON.parse(action.payload_json),
        action.idempotency_key,
        action.payload_hash,
      );
    }

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
        let confirmationToken = invokeOptions.confirmationToken;
        if (invokeOptions.downstreamAction) {
          confirmationToken = await confirmDownstream(invokeOptions.downstreamAction);
        } else if (USER_CONFIRMED_CALLS.has(capabilityId)) {
          confirmationToken = await confirm(
            capabilityId, version, payload, idempotencyKey,
          );
        }
        const response = await gatewayPost(
          `/api/v1/capabilities/${encodeURIComponent(capabilityId)}:invoke`,
          {
            version, payload, idempotency_key: idempotencyKey,
            confirmation_token: confirmationToken,
          },
        );
        return unwrap(response, capabilityId, version);
      },
    };
  }

  function createCaptureWorkflow({ invoke, setTimer = setTimeout, onChange = () => {} } = {}) {
    if (typeof invoke !== 'function') throw new TypeError('invoke is required');
    const state = {
      environmentId: '', environmentVersion: 0, deviceId: '', preflight: null,
      snapshotRequest: null, materializationRun: null, captureRun: null,
      error: null, polling: false,
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
        try { await workflow.refresh(); } finally { schedulePoll(); }
      }, 2000);
    };
    const workflow = {
      state,
      setEnvironment(environmentId, environmentVersion) {
        state.environmentId = String(environmentId || '');
        state.environmentVersion = Number(environmentVersion || 0);
        state.preflight = null;
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
        return workflow.compose({
          ...payload,
          snapshot_request_id: state.snapshotRequest.snapshot_request_id,
        });
      },
      async selectConnector(deviceId) {
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
          && state.deviceId && state.preflight?.compatible,
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
        if (!workflow.canStartCapture()) throw new Error('connector_preflight_required');
        if (!state.materializationRun) {
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
        }
        state.captureRun = await call(
          'simulation.capture_run.start', environmentPayload(),
          { idempotencyKey: randomKey('capture') },
        );
        await workflow.dispatchNext();
        state.polling = !TERMINAL.has(state.captureRun.status);
        publish();
        schedulePoll();
        return state.captureRun;
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
        publish();
        return result;
      },
      async retry(operationId) {
        if (!state.captureRun?.capture_run_id) throw new Error('capture_run_required');
        const result = await call('simulation.capture_step.retry', {
          capture_run_id: state.captureRun.capture_run_id,
          operation_id: operationId,
        }, { idempotencyKey: randomKey('retry') });
        state.polling = true;
        schedulePoll();
        return result;
      },
    };
    return workflow;
  }

  return {
    ALLOWED_CALLS, CAPABILITY_VERSIONS, createCaptureWorkflow, createGatewayApi,
  };
});
