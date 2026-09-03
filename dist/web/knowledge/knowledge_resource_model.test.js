'use strict';
const assert = require('assert');
const model = require('./knowledge_resource_model.js');

assert.strictEqual(model.resourceTypeForSection('vpps_sockets'), 'socket');
assert.strictEqual(model.resourceTypeForSection('vpps_tools'), 'tool');
assert.strictEqual(model.resourceTypeForSection('vpps_fixtures'), 'fixture');
assert.strictEqual(model.resourceTypeForSection('vpps_equipments'), 'equipment');
assert.deepStrictEqual(
  model.resourcePatchBody(
    { resource_version: 4 },
    { resource_type: 'tool', code: 'T-1', name: 'Tool', attributes: { torque: 8 }, source: 'manual' },
  ),
  { expected_resource_version: 4, code: 'T-1', name: 'Tool', attributes: { torque: 8 } },
);
assert.deepStrictEqual(model.resourceRetireBody({ resource_version: 4 }), { expected_resource_version: 4 });
assert.strictEqual(model.canManageResources('knowledge_admin'), true);
assert.strictEqual(model.canManageResources('member'), false);
console.log('knowledge resource model: OK');
