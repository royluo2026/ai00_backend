'use strict';
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const source = fs.readFileSync(__dirname + '/staging_panel.js', 'utf8');
const sandbox = { module: { exports: {} }, console, window: {}, document: {} };
vm.runInNewContext(`${source}\nmodule.exports = { StagingPanel, _resourceResolvePayload, _resourceIgnorePayload };`, sandbox);
const { StagingPanel } = sandbox.module.exports;
const api = sandbox.module.exports;
assert.deepStrictEqual(
  JSON.parse(JSON.stringify(api._resourceResolvePayload({ gid: 's-1', resource_version: 3 }, 'r-1'))),
  { resource_gid: 'r-1', expected_staging_version: 3 },
);
assert.deepStrictEqual(
  JSON.parse(JSON.stringify(api._resourceIgnorePayload({ gid: 's-1', resource_version: 3 }))),
  { expected_staging_version: 3 },
);

async function run() {
  const panel = Object.create(StagingPanel.prototype);
  const calls = [];
  panel._versionGid = 'v 1';
  panel._invokeCapability = async (id, payload) => {
    calls.push({ id, payload });
    if (id === 'craft.bop.staging.read') return { data: [] };
    if (id === 'craft.resource_requirement.staging.search') return { items: [{ gid: 's-1' }], next_cursor: null };
    if (id === 'craft.resource_requirement.search') return { items: [{ gid: 'r-1', code: 'AS-01', name: 'Socket' }], next_cursor: null };
    return { gid: payload.staging_gid };
  };
  panel._render = () => {};
  panel._toast = () => {};
  panel._items = [];
  panel._resourceItems = [];
  await panel.load();
  assert.deepStrictEqual(JSON.parse(JSON.stringify(calls.slice(0, 2))), [
    { id: 'craft.bop.staging.read', payload: { operation: 'list', version_gid: 'v 1' } },
    { id: 'craft.resource_requirement.staging.search', payload: { version_gid: 'v 1', match_status: 'pending', page_size: 200 } },
  ]);
  assert.deepStrictEqual(panel._resourceItems, [{ gid: 's-1' }]);

  sandbox.window.prompt = () => 'AS-01';
  panel.load = async () => {};
  await panel.resolveResourceItem({ gid: 's-1', resource_type: 'socket', resource_version: 3 });
  assert.deepStrictEqual(JSON.parse(JSON.stringify(calls.slice(-2))), [
    { id: 'craft.resource_requirement.search', payload: { resource_type: 'socket', status: 'active', page_size: 200 } },
    { id: 'craft.resource_requirement.staging.resolve', payload: { staging_gid: 's-1', resource_gid: 'r-1', expected_staging_version: 3 } },
  ]);

  await panel.ignoreResourceItem({ gid: 's-2', resource_version: 4 });
  assert.deepStrictEqual(JSON.parse(JSON.stringify(calls.at(-1))), {
    id: 'craft.resource_requirement.staging.ignore',
    payload: { staging_gid: 's-2', expected_staging_version: 4 },
  });
  console.log('resource staging review contract: OK');
}

run().catch(error => { console.error(error); process.exitCode = 1; });
