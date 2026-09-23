'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { createConnectorOnboarding, createGatewayInvoker } = require('./connector_onboarding.js');

test('gateway invoker sends an idempotency key for bootstrap writes', async () => {
  let body;
  const host={crypto:{randomUUID:()=> 'operation-one'},electronAPI:{invokeCapability:async (_id, envelope) => {
    body = envelope;
    return { success: true, data: { ok: true, data: { bootstrap_id: 'bootstrap-1' } } };
  }}};
  const {createBusinessFacade}=require('../../../../web/core/business_facade');
  const invoke = createGatewayInvoker(createBusinessFacade(host).request);

  await invoke('simulation.connector.pairing.bootstrap.create', {});

  assert.equal(body.idempotency_key, 'simulation.connector.pairing.bootstrap.create:operation-one');
});

test('connect launches installed connector without exposing code or device id', async () => {
  const calls = [];
  let opened = '';
  const onboarding = createConnectorOnboarding({
    invoke: async (id) => {
      calls.push(id);
      if (id === 'simulation.connector.pairing.bootstrap.create') return {
        bootstrap_id: 'bootstrap-1', bootstrap_token: 'secret', status: 'created',
        expires_at: '2026-09-07T12:00:00Z', resource_version: 1,
      };
      return { connector_id: null, installation_id: null };
    },
    openProtocol: uri => { opened = uri; },
    gatewayUrl: 'https://ai00.example',
  });

  await onboarding.connect();

  assert.deepEqual(calls, ['simulation.connector.pairing.bootstrap.create']);
  assert.equal(opened, '');
  onboarding.launch();
  assert.match(opened, /^ai00connector:\/\/pair\?/);
  assert.equal(onboarding.state.kind, 'waiting_for_connector');
  assert.equal('userCode' in onboarding.state, false);
  assert.equal('connectorDeviceId' in onboarding.state, false);
});

test('claimed ticket shows workstation summary and approval uses exact version', async () => {
  const calls = [];
  const onboarding = createConnectorOnboarding({
    invoke: async (id, payload, options) => {
      calls.push([id, payload, options]);
      if (id === 'simulation.connector.pairing.bootstrap.get') return {
        bootstrap_id: 'bootstrap-1', status: 'claimed', pairing_id: 'pair-1',
        expires_at: '2026-09-07T12:00:00Z', resource_version: 2,
      };
      if (id === 'simulation.connector.pairing.summary.get') return {
        pairing_id: 'pair-1', user_code: 'hidden-code', device_name: '工位 A',
        runtime_version: '1.0.0', masked_windows_user: 'l***8', status: 'pending',
        expires_at: '2026-09-07T12:00:00Z', resource_version: 1,
      };
      return {};
    },
    openProtocol: () => {}, gatewayUrl: 'https://ai00.example',
  });
  onboarding.restore({ bootstrapId: 'bootstrap-1', resourceVersion: 1 });

  await onboarding.refresh();
  assert.equal(onboarding.state.kind, 'awaiting_confirmation');
  assert.equal(onboarding.state.deviceName, '工位 A');
  await onboarding.approve();
  assert.deepEqual(calls.at(-1), [
    'simulation.connector.pairing.approve',
    { pairing_id: 'pair-1', expected_version: 1 },
    { confirmation: 'user' },
  ]);
});

test('existing binding is selected instead of starting another pairing', async () => {
  const calls = [];
  const onboarding = createConnectorOnboarding({
    invoke: async id => {
      calls.push(id);
      return { connector_id: 'connector-1', installation_id: 'installation-1' };
    },
    openProtocol: () => {}, gatewayUrl: 'https://ai00.example',
  });

  await onboarding.refresh();

  assert.equal(onboarding.state.kind, 'bound');
  assert.equal(onboarding.state.connectorId, 'connector-1');
  assert.deepEqual(calls, ['simulation.connector.binding.get']);
});
