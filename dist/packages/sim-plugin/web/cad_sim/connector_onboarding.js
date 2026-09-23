'use strict';

(function(root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.SimulationConnectorOnboarding = api;
})(typeof window !== 'undefined' ? window : globalThis, function() {
  const TERMINAL = new Set(['bound', 'cancelled', 'expired']);
  const WRITES = new Set([
    'simulation.connector.pairing.bootstrap.create',
    'simulation.connector.pairing.approve',
    'simulation.connector.pairing.cancel',
  ]);

  function randomKey() {
    return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
  }

  function unwrap(response, capabilityId) {
    const envelope = response?.success === true ? response.data : response;
    if (!envelope || response?.success === false || envelope.ok === false) {
      const detail = envelope?.error || response?.error || response?.detail || {};
      const error = new Error(detail.message || detail.code || `能力调用失败：${capabilityId}@1`);
      error.code = detail.code || 'capability_invocation_failed';
      throw error;
    }
    if (envelope.status === 'accepted' && envelope.operation_ref) return envelope.operation_ref;
    return envelope.data !== undefined ? envelope.data : envelope;
  }

  function createGatewayInvoker(invoke, confirmUser = async () => false) { return async (capabilityId,payload={},options={}) => unwrap(await invoke(capabilityId,{version:1,payload},()=>confirmUser(capabilityId,payload)),capabilityId); }

  function createConnectorOnboarding({
    invoke, openProtocol, gatewayUrl, setTimer = setTimeout, clearTimer = clearTimeout,
    onChange = () => {},
  } = {}) {
    if (typeof invoke !== 'function' || typeof openProtocol !== 'function')
      throw new TypeError('invoke and openProtocol are required');
    let ticket = null;
    let pendingProtocolUri = '';
    let timer = null;
    let pollingStartedAt = 0;
    const state = { kind: 'loading', error: null, connectorId: '' };
    const publish = values => {
      Object.keys(state).forEach(key => delete state[key]);
      Object.assign(state, values, { error: values.error || null });
      onChange({ ...state });
    };

    async function call(id, payload = {}, options = {}) {
      try {
        return await invoke(id, payload, options);
      } catch (error) {
        publish({ kind: 'error', error: {
          code: error.code || 'capability_invocation_failed', message: error.message,
        }});
        throw error;
      }
    }

    const api = {
      state,
      restore(value) { ticket = value ? { ...value } : null; },
      async connect() {
        const created = await call('simulation.connector.pairing.bootstrap.create');
        ticket = {
          bootstrapId: created.bootstrap_id,
          resourceVersion: created.resource_version,
        };
        pendingProtocolUri = 'ai00connector://pair?' + new URLSearchParams({
          gateway: gatewayUrl, bootstrap_id: created.bootstrap_id,
          bootstrap_token: created.bootstrap_token,
        }).toString();
        publish({ kind: 'waiting_for_connector', bootstrapId: created.bootstrap_id });
        return { bootstrapId: created.bootstrap_id, resourceVersion: created.resource_version };
      },
      launch() {
        if (!pendingProtocolUri) throw new Error('connector_launch_not_ready');
        openProtocol(pendingProtocolUri);
      },
      async refresh() {
        if (!ticket) {
          const binding = await call('simulation.connector.binding.get');
          publish(binding.connector_id
            ? { kind: 'bound', connectorId: binding.connector_id }
            : { kind: 'unbound', connectorId: '' });
          return state;
        }
        const bootstrap = await call('simulation.connector.pairing.bootstrap.get', {
          bootstrap_id: ticket.bootstrapId,
        });
        ticket.resourceVersion = bootstrap.resource_version;
        if (bootstrap.status === 'active') {
          ticket = null;
          pendingProtocolUri = '';
          return api.refresh();
        }
        if (bootstrap.status === 'cancelled' || bootstrap.status === 'expired') {
          publish({ kind: bootstrap.status, connectorId: '' });
          return state;
        }
        if (!bootstrap.pairing_id) {
          publish({ kind: 'waiting_for_connector', bootstrapId: ticket.bootstrapId });
          return state;
        }
        const summary = await call('simulation.connector.pairing.summary.get', {
          pairing_id: bootstrap.pairing_id,
        });
        publish({
          kind: summary.status === 'pending' ? 'awaiting_confirmation' : 'activating',
          pairingId: summary.pairing_id, deviceName: summary.device_name,
          windowsUser: summary.masked_windows_user, runtimeVersion: summary.runtime_version,
          resourceVersion: summary.resource_version, connectorId: '',
        });
        return state;
      },
      async approve() {
        if (state.kind !== 'awaiting_confirmation')
          throw new Error('connector_pairing_not_ready');
        await call('simulation.connector.pairing.approve', {
          pairing_id: state.pairingId, expected_version: state.resourceVersion,
        }, { confirmation: 'user' });
        publish({ ...state, kind: 'activating' });
      },
      async cancel() {
        if (!ticket) return;
        await call('simulation.connector.pairing.cancel', {
          bootstrap_id: ticket.bootstrapId, expected_version: ticket.resourceVersion,
        });
        ticket = null;
        pendingProtocolUri = '';
        publish({ kind: 'cancelled', connectorId: '' });
      },
      startPolling() {
        api.stopPolling();
        pollingStartedAt = Date.now();
        const poll = async () => {
          try { await api.refresh(); } catch (_) {}
          if (!TERMINAL.has(state.kind) && Date.now() - pollingStartedAt < 120000)
            timer = setTimer(poll, 1500);
        };
        timer = setTimer(poll, 250);
      },
      stopPolling() { if (timer !== null) clearTimer(timer); timer = null; },
    };
    return api;
  }

  return { createConnectorOnboarding, createGatewayInvoker };
});
