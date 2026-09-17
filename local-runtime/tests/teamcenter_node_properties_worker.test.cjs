const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const source = fs.readFileSync(path.join(
  __dirname,
  '../src/Ai00.Connector.Adapters.VisMockup/teamcenter_readonly_worker.js',
), 'utf8');

assert.match(source, /request\.command === 'node_properties'/);
assert.match(source, /\['status', 'revision_rules', 'search', 'observe', 'children', 'node_properties'\]/);
for (const property of [
  'bl_line_name', 'bl_occurrence_uid', 'C9_bl_torque', 'C9_bl_torqueimpor',
  'object_name', 'item_id', 'item_revision_id', 'owning_user', 'owning_group',
  'c9_weight', 'c9_unitweight',
]) assert.match(source, new RegExp(property));
assert.doesNotMatch(source, /payload\.property_names/);
for (const forbidden of [
  'setProperties', 'saveBOMWindows', 'createObjects', 'deleteObjects',
  'setDatasetFile', 'getFileWriteTickets', 'commitDatasetFiles',
]) assert.doesNotMatch(source, new RegExp(`\\.${forbidden}\\s*\\(`));

console.log('node property worker command and fixed projection checks passed');
