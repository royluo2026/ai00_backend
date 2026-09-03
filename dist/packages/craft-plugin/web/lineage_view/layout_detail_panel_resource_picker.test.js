'use strict';
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const source = fs.readFileSync(__dirname + '/layout_detail_panel.js', 'utf8');
const sandbox = { module: { exports: {} }, console };
vm.runInNewContext(`${source}\nmodule.exports = { LayoutDetailPanel, _buildRuntimeRelationGroups, _candidatePrimary, _candidateSearchText };`, sandbox);
const { LayoutDetailPanel, _buildRuntimeRelationGroups: groupsFor, _candidatePrimary, _candidateSearchText } = sandbox.module.exports;

const groups = groupsFor([
  { link_type_binding: 'resource_socket', label_zh: '需求套筒', range_node_type: 'tool_need' },
  { link_type_binding: 'needsTool', label_zh: '需求工具', range_node_type: 'tool_need' },
  { link_type_binding: 'needsFixture', label_zh: '需求工装', range_node_type: 'fixture_need' },
  { link_type_binding: 'needsEquipment', label_zh: '需求设备', range_node_type: 'equipment_need' },
  { link_type_binding: 'physical_tool', label_zh: '工具', range_node_type: 'tool_factory' },
]);

for (const [resourceType, linkType] of [
  ['socket', 'resource_socket'], ['tool', 'resource_tool'],
  ['fixture', 'resource_fixture'], ['equipment', 'resource_equipment'],
]) {
  const group = groups.find(item => item.resourceType === resourceType);
  assert.ok(group, `${resourceType} group exists`);
  assert.strictEqual(group.linkType, linkType);
  assert.strictEqual(group.ntType, resourceType === 'socket' ? 'socket_need' : `${resourceType === 'equipment' ? 'equipment' : resourceType}_need`);
}

const physical = groups.find(item => item.linkTypes.includes('physical_tool'));
assert.ok(physical && !physical.resourceType, 'physical tools remain a separate group');
assert.strictEqual(_candidatePrimary({ code: 'AS-01', name: 'Socket' }), 'AS-01');
assert.ok(_candidateSearchText({ code: 'AS-01', name: 'Socket' }).includes('as-01'));

const panel = Object.create(LayoutDetailPanel.prototype);
let requests = 0;
panel._invokeCapability = (id, payload) => {
  requests += 1;
  assert.strictEqual(id, 'craft.resource_requirement.search');
  assert.deepStrictEqual(JSON.parse(JSON.stringify(payload)), { status: 'active', page_size: 200 });
  return Promise.resolve({ items: [] });
};
assert.strictEqual(panel._getCraftResourceRequirements(), panel._getCraftResourceRequirements());
assert.strictEqual(requests, 1);
console.log('runtime resource picker mapping: OK');
