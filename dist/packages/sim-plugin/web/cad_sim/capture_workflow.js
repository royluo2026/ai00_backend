'use strict';

(function(root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.SimulationCaptureWorkflow = api;
})(typeof window !== 'undefined' ? window : globalThis, function() {
  const ALLOWED_CALLS = Object.freeze([
    'simulation.environment.preflight', 'simulation.environment.compose',
    'simulation.environment.materialize', 'simulation.capture_run.start',
    'simulation.capture_run.get', 'simulation.capture_run.cancel',
    'simulation.capture_step.retry',
  ]);
  const WRITE_CALLS = new Set([
    'simulation.environment.compose', 'simulation.environment.materialize',
    'simulation.capture_run.start', 'simulation.capture_run.cancel',
    'simulation.capture_step.retry',
  ]);
  const TERMINAL = new Set(['completed', 'failed', 'cancelled', 'outcome_unknown']);

  function unwrap(response, capabilityId) {
    const envelope = response && response.success === true ? response.data : response;
    if (!envelope || response?.success === false || envelope.ok === false) {
      const detail = envelope?.error || response?.detail || response?.error || {};
      const error = new Error(detail.message || detail.code || `能力调用失败：${capabilityId}@1`);
      error.code = detail.code || 'capability_invocation_failed';
      error.retryable = detail.retryable === true;
      throw error;
    }
    return envelope.data !== undefined ? envelope.data : envelope;
  }

  function randomKey(prefix) {
    const suffix = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    return `${prefix}-${suffix}`;
  }

  function createGatewayApi(fetcher, options = {}) {
    if (typeof fetcher !== 'function') throw new TypeError('authenticated gateway fetcher is required');
    const approve = options.approve || (async () => true);
    return {
      async invoke(capabilityId, payload, invokeOptions = {}) {
        if (!ALLOWED_CALLS.includes(capabilityId)) throw new Error(`capability_not_allowed:${capabilityId}`);
        const idempotencyKey = WRITE_CALLS.has(capabilityId)
          ? (invokeOptions.idempotencyKey || randomKey(capabilityId)) : undefined;
        let confirmationToken;
        if (WRITE_CALLS.has(capabilityId)) {
          if (!await approve(capabilityId, payload)) throw new Error('user_cancelled');
          const confirmation = await fetcher(`/api/v1/capabilities/${encodeURIComponent(capabilityId)}:confirm`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ version: 1, payload, idempotency_key: idempotencyKey }),
          });
          confirmationToken = unwrap(confirmation, capabilityId).confirmation_token;
        }
        const response = await fetcher(`/api/v1/capabilities/${encodeURIComponent(capabilityId)}:invoke`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            version: 1, payload, idempotency_key: idempotencyKey,
            confirmation_token: confirmationToken,
          }),
        });
        return unwrap(response, capabilityId);
      },
    };
  }

  function createCaptureWorkflow({ invoke, setTimer = setTimeout, onChange = () => {} } = {}) {
    if (typeof invoke !== 'function') throw new TypeError('invoke is required');
    const state = {
      environmentId: '', environmentVersion: 0, deviceId: '', preflight: null,
      captureRun: null, error: null, polling: false,
    };
    const publish = () => onChange({ ...state });
    const call = async (id, payload, options) => {
      if (!ALLOWED_CALLS.includes(id)) throw new Error(`capability_not_allowed:${id}`);
      try {
        state.error = null;
        const result = await invoke(id, payload, options);
        publish();
        return result;
      } catch (error) {
        state.error = { code: error.code || 'capability_invocation_failed', message: error.message };
        publish();
        throw error;
      }
    };
    const environmentPayload = () => ({
      environment_id: state.environmentId, environment_version: state.environmentVersion,
      device_id: state.deviceId,
    });
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
        const result = await call('simulation.environment.compose', payload, { idempotencyKey: randomKey('compose') });
        if (result.status === 'composed') workflow.setEnvironment(result.environment_id, result.environment_version);
        return result;
      },
      async selectConnector(deviceId) {
        state.deviceId = String(deviceId || '');
        if (!state.environmentId || !state.environmentVersion || !state.deviceId) {
          state.preflight = null; publish(); return null;
        }
        state.preflight = await call('simulation.environment.preflight', environmentPayload());
        publish();
        return state.preflight;
      },
      canStartCapture() {
        return Boolean(state.environmentId && state.environmentVersion && state.deviceId && state.preflight?.compatible);
      },
      async startCapture() {
        if (!workflow.canStartCapture()) throw new Error('connector_preflight_required');
        await call('simulation.environment.materialize', environmentPayload(), { idempotencyKey: randomKey('materialize') });
        state.captureRun = await call('simulation.capture_run.start', environmentPayload(), { idempotencyKey: randomKey('capture') });
        state.polling = !TERMINAL.has(state.captureRun.status);
        publish();
        schedulePoll();
        return state.captureRun;
      },
      async refresh() {
        if (!state.captureRun?.capture_run_id) return null;
        state.captureRun = await call('simulation.capture_run.get', { capture_run_id: state.captureRun.capture_run_id });
        if (TERMINAL.has(state.captureRun.status)) state.polling = false;
        publish();
        return state.captureRun;
      },
      async cancel() {
        if (!state.captureRun?.capture_run_id) return null;
        const result = await call('simulation.capture_run.cancel', { capture_run_id: state.captureRun.capture_run_id }, { idempotencyKey: randomKey('cancel') });
        state.polling = result.status === 'cancelling'; publish(); return result;
      },
      async retry(operationId) {
        if (!state.captureRun?.capture_run_id) throw new Error('capture_run_required');
        const result = await call('simulation.capture_step.retry', {
          capture_run_id: state.captureRun.capture_run_id, operation_id: operationId,
        }, { idempotencyKey: randomKey('retry') });
        state.polling = true; schedulePoll(); return result;
      },
    };
    return workflow;
  }

  return { ALLOWED_CALLS, createCaptureWorkflow, createGatewayApi };
});
