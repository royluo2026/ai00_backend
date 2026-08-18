'use strict';

const assert = require('assert/strict');
const {
  normalizeGid,
  actionsFor,
  filterRows,
  mergeLoadFailure,
} = require('./governance_model.js');

function runGovernanceModelTests() {
  const rows = [
    { gid: '1953048035824070656', capabilityId: 'craft.factory.create', domain: 'craft', businessEffect: '创建工厂' },
    { gid: '1953048035824070657', capabilityId: 'base.audit.read', domain: 'base', businessEffect: '读取审计' },
  ];

  assert.equal(normalizeGid(1953048035824070656n), '1953048035824070656');
  assert.equal(normalizeGid('1953048035824070656'), '1953048035824070656');
  assert.deepEqual(actionsFor(['system.capability.read']), ['view', 'export']);
  assert.ok(!actionsFor(['system.capability.govern']).includes('edit-contract'));
  assert.ok(!actionsFor(['system.capability.govern']).includes('delete-contract'));
  assert.ok(!actionsFor(['system.capability.govern']).includes('confirm-finding'));
  assert.ok(!actionsFor(['system.capability.govern']).includes('reject-candidate'));
  assert.equal(filterRows(rows, { domain: 'craft', query: '创建工厂' }).length, 1);

  const previousRows = [rows[0]];
  const failed = mergeLoadFailure(previousRows, new Error('offline'));
  assert.equal(failed.rows, previousRows);
  assert.equal(failed.staleData, true);
  assert.equal(failed.lastError, 'offline');
}

module.exports = { runGovernanceModelTests };
