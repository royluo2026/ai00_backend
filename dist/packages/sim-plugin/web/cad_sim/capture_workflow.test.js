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

const {createBusinessFacade}=require('../../../../web/core/business_facade');
function port(requests){return createBusinessFacade({electronAPI:{invokeCapability:async(id,envelope)=>{requests.push([id,envelope]);return envelope.confirmation?{success:true,data:{ok:true,data:{status:'ok'}}}:{success:false,error:{code:'confirmation_required',confirmation_challenge:'exact-challenge'}};}}}).request;}
test('gateway pins v2 and confirms the exact same request, refusing downstream receipts',async()=>{
 const requests=[],approvals=[];const api=createGatewayApi(port(requests),{approve:async(id,version,payload)=>{approvals.push([id,version,payload]);return true;}});
 await api.invoke('simulation.document_snapshot.request',{device_id:'d',request_key:'r'});
 assert.equal(requests[0][1].version,2);assert.equal(requests.length,2);assert.equal(requests[0][1].idempotency_key,requests[1][1].idempotency_key);assert.equal(approvals.length,1);
 await assert.rejects(api.invoke('simulation.document_snapshot.dispatch',{snapshot_request_id:'s'},{downstreamAction:action('simulation.connector.plan.queue')}),/capture_receipt_required/);assert.equal(requests.length,2);
});
test('gateway cannot replay a challenge without explicit user approval',async()=>{
 const requests=[];const api=createGatewayApi(port(requests));await assert.rejects(api.invoke('simulation.capture_run.start',{}),/cancelled/);assert.equal(requests.length,1);assert.equal(requests[0][1].confirmation,undefined);
});
test('downstream confirmation fails before invoking or prompting for another effect',async()=>{
 const requests=[];let approvals=0;const api=createGatewayApi(port(requests),{approve:async()=>{approvals++;return true;}});await assert.rejects(api.invoke('simulation.capture_run.dispatch',{}, {downstreamAction:action('craft.process_screenshot.attach')}),/capture_receipt_required/);assert.equal(requests.length,0);assert.equal(approvals,0);
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
      if (id === 'simulation.environment.bop_vm_binding_draft.preview') {
        return { mode: 'parts', auto_count: 2, review_count: 0, bindings: [] };
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
    ['simulation.environment.bop_vm_binding_draft.preview', 1],
    ['simulation.environment.compose', 2],
  ]);
  assert.equal(workflow.state.bindingDraft.auto_count, 2);
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

test('a restarted desktop session prepares fresh materialization before another capture', async () => {
  const calls = [];
  let materializations = 0;
  const workflow = createCaptureWorkflow({
    invoke: async (id, _payload, options) => {
      calls.push(id);
      if (id === 'simulation.environment.preflight') return { compatible: true, problems: [] };
      if (id === 'simulation.environment.materialize') {
        materializations++;
        return { run_id: `mat-${materializations}`, status: 'queued' };
      }
      if (id === 'simulation.materialization_run.action.get') return { action: action('simulation.connector.plan.queue') };
      if (id === 'simulation.materialization_run.dispatch') return { run_id: `mat-${materializations}`, status: 'running' };
      if (id === 'simulation.capture_run.start') {
        const error = new Error('materialization belongs to previous runtime session');
        error.code = 'simulation_result_not_ready';
        throw error;
      }
      throw new Error(`unexpected ${id}`);
    },
  });
  workflow.setEnvironment('env-1', 1);
  await workflow.selectConnector('device-1');
  await workflow.startCapture();

  const restarted = await workflow.startCapture();

  assert.equal(restarted.phase, 'materializing');
  assert.equal(restarted.run_id, 'mat-2');
  assert.equal(workflow.state.error, null);
  assert.equal(materializations, 2);
  assert.deepEqual(calls.slice(-4), [
    'simulation.capture_run.start',
    'simulation.environment.materialize',
    'simulation.materialization_run.action.get',
    'simulation.materialization_run.dispatch',
  ]);
});

test('workflow allows only governed gateway capabilities', () => {
  assert.equal(ALLOWED_CALLS.includes('simulation.capture_run.action.get'), true);
  assert.equal(ALLOWED_CALLS.includes('simulation.capture_run.dispatch'), true);
  assert.equal(CAPABILITY_VERSIONS['simulation.capture_run.start'], 2);
  assert.equal(CAPABILITY_VERSIONS['simulation.environment.compose'], 2);
});
