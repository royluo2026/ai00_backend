const assert = require('node:assert/strict');
require('./teamcenter_session.js');

const session = globalThis.AI00TeamcenterSession;

assert.deepEqual(session.projectSearchInput(' W10 ', 'Latest Working', '2026-09-16T00:00:00.000Z'), {
  endpoint_id: 'tc-production', query: 'W10-ENG00001', revision_id: '00',
  revision_rule: 'Latest Working', configuration_date: '2026-09-16T00:00:00.000Z', limit: 20,
});
assert.throws(() => session.projectSearchInput('W10-ENG00001', 'Latest Working', '2026-09-16T00:00:00.000Z'), /teamcenter_project_number_only/);
assert.throws(() => session.projectSearchInput('W10-ENG0001', 'Latest Working', '2026-09-16T00:00:00.000Z'), /teamcenter_project_number_only/);
assert.deepEqual(session.fuzzySearchInput(' eng ', '', 'Latest Working', '2026-09-16T00:00:00.000Z'), {
  endpoint_id: 'tc-production', query: 'eng', revision_id: '', revision_rule: 'Latest Working',
  configuration_date: '2026-09-16T00:00:00.000Z', limit: 20,
});
assert.equal(session.isReady({ state: 'ready', masked_username: 'u***r' }), true);
assert.equal(session.isReady({ state: 'logged_out', masked_username: '' }), false);
console.log('teamcenter_session tests passed');
