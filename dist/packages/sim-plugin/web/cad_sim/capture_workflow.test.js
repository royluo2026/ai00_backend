'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const {
  ALLOWED_CALLS,
  createCaptureWorkflow,
} = require('./capture_workflow.js');


test('start is disabled until connector preflight passes', async () => {
  const calls = [];
  const workflow = createCaptureWorkflow({
    invoke: async (id) => {
      calls.push(id);
      if (id === 'simulation.environment.preflight') return { compatible: false, problems: [{ code: 'adapter_unavailable' }] };
      throw new Error(`unexpected ${id}`);
    },
  });
  workflow.setEnvironment('env-1', 1);

  await workflow.selectConnector('device-1');

  assert.equal(workflow.canStartCapture(), false);
  assert.deepEqual(calls, ['simulation.environment.preflight']);
});


test('browser only calls governed gateway capabilities', () => {
  assert.deepEqual(ALLOWED_CALLS, [
    'simulation.document_snapshot.request', 'simulation.document_snapshot.get',
    'simulation.environment.preflight', 'simulation.environment.compose',
    'simulation.environment.materialize', 'simulation.capture_run.start',
    'simulation.capture_run.get', 'simulation.capture_run.cancel',
    'simulation.capture_step.retry',
  ]);
  const source = fs.readFileSync(path.join(__dirname, 'capture_workflow.js'), 'utf8');
  assert.equal(source.includes('127.0.0.1'), false);
  assert.equal(source.includes('/bridge/'), false);
});


test('environment composition waits for a confirmed active document snapshot', async () => {
  const calls = [];
  const workflow = createCaptureWorkflow({
    invoke: async (id, payload) => {
      calls.push([id, payload]);
      if (id === 'simulation.document_snapshot.request') return { snapshot_request_id: 'snapshot-1', status: 'queued' };
      if (id === 'simulation.document_snapshot.get') return { snapshot_request_id: 'snapshot-1', status: 'completed' };
      if (id === 'simulation.environment.compose') return { status: 'composed', environment_id: 'env-1', environment_version: 1 };
      throw new Error(`unexpected ${id}`);
    },
    setTimer: callback => { callback(); return 1; },
  });

  await workflow.composeFromActiveDocument({ device_id: 'device-1', name: 'environment' });

  assert.deepEqual(calls.map(item => item[0]), [
    'simulation.document_snapshot.request', 'simulation.document_snapshot.get',
    'simulation.environment.compose',
  ]);
  assert.equal(calls[2][1].snapshot_request_id, 'snapshot-1');
});


test('start queues materialization before reverse capture and polls no faster than two seconds', async () => {
  const calls = [];
  const timers = [];
  const workflow = createCaptureWorkflow({
    invoke: async (id) => {
      calls.push(id);
      if (id === 'simulation.environment.preflight') return { compatible: true, problems: [] };
      if (id === 'simulation.environment.materialize') return { status: 'queued' };
      if (id === 'simulation.capture_run.start') return { capture_run_id: 'run-1', status: 'queued' };
      if (id === 'simulation.capture_run.get') return { capture_run_id: 'run-1', status: 'running', steps: [] };
      throw new Error(`unexpected ${id}`);
    },
    setTimer: (callback, milliseconds) => { timers.push(milliseconds); return 1; },
  });
  workflow.setEnvironment('env-1', 1);
  await workflow.selectConnector('device-1');

  await workflow.startCapture();

  assert.deepEqual(calls.slice(1), [
    'simulation.environment.materialize', 'simulation.capture_run.start',
  ]);
  assert.equal(timers[0], 2000);
});
