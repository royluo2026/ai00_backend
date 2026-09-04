'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  ALLOWED_CALLS,
  CAPABILITY_VERSIONS,
  createCaptureWorkflow,
  createGatewayApi,
} = require('./capture_workflow.js');

const action = capabilityId => ({
  capability_id: capabilityId,
  major_version: 1,
  payload_json: JSON.stringify({ plan: { plan_id: 'plan-1' } }),
  payload_hash: `sha256:${'a'.repeat(64)}`,
  idempotency_key: 'plan-1',
});

test('gateway pins v2 prepare capabilities and confirms exact downstream action', async () => {
  const requests = [];
  const approvals = [];
  const api = createGatewayApi(async (url, options) => {
    requests.push([url, JSON.parse(options.body)]);
    if (url.endsWith(':confirm')) {
      return { success: true, data: { confirmation_token: 'confirm-1' } };
    }
    return { success: true, data: { ok: true, data: { status: 'ok' } } };
  }, {
    approve: async (id, version, payload, metadata) => {
      approvals.push([id, version, Object.keys(payload).sort(), metadata.payloadHash]);
      return true;
    },
  });

  await api.invoke('simulation.document_snapshot.request', { device_id: 'd', request_key: 'r' });
  await api.invoke('simulation.document_snapshot.dispatch', { snapshot_request_id: 's' }, {
    downstreamAction: action('simulation.connector.plan.queue'),
    idempotencyKey: 'dispatch:plan-1',
  });

  assert.equal(requests[0][1].version, 2);
  assert.deepEqual(approvals, [
    ['simulation.document_snapshot.request', 2, ['device_id', 'request_key'], null],
    ['simulation.connector.plan.queue', 1, ['plan'], `sha256:${'a'.repeat(64)}`],
  ]);
  assert.equal(requests[3][1].confirmation_token, 'confirm-1');
  assert.equal(requests[3][1].version, 1);
});

test('gateway fails closed when no user approval callback is installed', async () => {
  let calls = 0;
  const api = createGatewayApi(async () => { calls += 1; return {}; });

  await assert.rejects(
    api.invoke('simulation.capture_run.start', {
      environment_id: 'env-1', environment_version: 1, device_id: 'device-1',
    }),
    /user_cancelled/,
  );
  assert.equal(calls, 0);
});

test('gateway performs no request when the user rejects the exact action', async () => {
  let calls = 0;
  const approvals = [];
  const api = createGatewayApi(async () => { calls += 1; return {}; }, {
    approve: async (id, version, payload, metadata) => {
      approvals.push([id, version, Object.keys(payload).sort(), metadata.payloadHash]);
      return false;
    },
  });

  await assert.rejects(
    api.invoke('simulation.capture_run.dispatch', { capture_run_id: 'run-1' }, {
      downstreamAction: action('craft.process_screenshot.attach'),
    }),
    /user_cancelled/,
  );
  assert.deepEqual(approvals, [[
    'craft.process_screenshot.attach', 1, ['plan'], `sha256:${'a'.repeat(64)}`,
  ]]);
  assert.equal(calls, 0);
});

test('start is disabled until connector preflight passes', async () => {
  const calls = [];
  const workflow = createCaptureWorkflow({
    invoke: async (id, _payload, options) => {
      calls.push([id, options.version]);
      if (id === 'simulation.environment.preflight') {
        return { compatible: false, problems: [{ code: 'adapter_unavailable' }] };
      }
      throw new Error(`unexpected ${id}`);
    },
  });
  workflow.setEnvironment('env-1', 1);

  await workflow.selectConnector('device-1');

  assert.equal(workflow.canStartCapture(), false);
  assert.deepEqual(calls, [['simulation.environment.preflight', 1]]);
});

test('environment composition uses prepare action dispatch before polling snapshot', async () => {
  const calls = [];
  const workflow = createCaptureWorkflow({
    invoke: async (id, payload, options) => {
      calls.push([id, payload, options]);
      if (id === 'simulation.document_snapshot.request') {
        return { snapshot_request_id: 'snapshot-1', status: 'queued' };
      }
      if (id === 'simulation.document_snapshot.action.get') {
        return { action: action('simulation.connector.plan.queue') };
      }
      if (id === 'simulation.document_snapshot.dispatch') {
        return { snapshot_request_id: 'snapshot-1', status: 'queued' };
      }
      if (id === 'simulation.document_snapshot.get') {
        return { snapshot_request_id: 'snapshot-1', status: 'completed' };
      }
      if (id === 'simulation.environment.compose') {
        return { status: 'composed', environment_id: 'env-1', environment_version: 1 };
      }
      throw new Error(`unexpected ${id}`);
    },
    setTimer: callback => { callback(); return 1; },
  });

  await workflow.composeFromActiveDocument({ device_id: 'device-1', name: 'environment' });

  assert.deepEqual(calls.map(item => [item[0], item[2].version]), [
    ['simulation.document_snapshot.request', 2],
    ['simulation.document_snapshot.action.get', 1],
    ['simulation.document_snapshot.dispatch', 1],
    ['simulation.document_snapshot.get', 1],
    ['simulation.environment.compose', 2],
  ]);
  assert.equal(calls[2][2].downstreamAction.capability_id, 'simulation.connector.plan.queue');
});

test('start waits for a second user action after materialization is dispatched', async () => {
  const calls = [];
  const timers = [];
  const workflow = createCaptureWorkflow({
    invoke: async (id, _payload, options) => {
      calls.push([id, options.version]);
      if (id === 'simulation.environment.preflight') return { compatible: true, problems: [] };
      if (id === 'simulation.environment.materialize') return { run_id: 'mat-1', status: 'queued' };
      if (id === 'simulation.materialization_run.action.get') {
        return { action: action('simulation.connector.plan.queue') };
      }
      if (id === 'simulation.materialization_run.dispatch') return { run_id: 'mat-1', status: 'running' };
      if (id === 'simulation.capture_run.start') return { capture_run_id: 'run-1', status: 'queued' };
      if (id === 'simulation.capture_run.action.get') {
        return { action: action('simulation.connector.plan.queue') };
      }
      if (id === 'simulation.capture_run.dispatch') return { capture_run_id: 'run-1', status: 'running' };
      throw new Error(`unexpected ${id}`);
    },
    setTimer: (_callback, milliseconds) => { timers.push(milliseconds); return 1; },
  });
  workflow.setEnvironment('env-1', 1);
  await workflow.selectConnector('device-1');

  const materializing = await workflow.startCapture();

  assert.deepEqual(calls.slice(1).map(item => item[0]), [
    'simulation.environment.materialize',
    'simulation.materialization_run.action.get',
    'simulation.materialization_run.dispatch',
  ]);
  assert.equal(materializing.phase, 'materializing');
  assert.equal(calls[1][1], 2);

  await workflow.startCapture();

  assert.deepEqual(calls.slice(4).map(item => item[0]), [
    'simulation.capture_run.start',
    'simulation.capture_run.action.get',
    'simulation.capture_run.dispatch',
  ]);
  assert.equal(calls[4][1], 2);
  assert.equal(timers[0], 2000);
});

test('workflow allows only governed gateway capabilities', () => {
  assert.equal(ALLOWED_CALLS.includes('simulation.capture_run.action.get'), true);
  assert.equal(ALLOWED_CALLS.includes('simulation.capture_run.dispatch'), true);
  assert.equal(CAPABILITY_VERSIONS['simulation.capture_run.start'], 2);
  assert.equal(CAPABILITY_VERSIONS['simulation.environment.compose'], 2);
});
