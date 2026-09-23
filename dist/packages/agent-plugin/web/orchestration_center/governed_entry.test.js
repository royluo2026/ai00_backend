const fs = require('fs');
const path = require('path');
const { bootstrapOrchestrationCenter } = require('./bootstrap.js');

async function runOrchestrationGovernedEntryTests(assert, assertAsync) {
  const index = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');
  const inspector = fs.readFileSync(path.join(__dirname, 'inspector.js'), 'utf8');
  const adminHub = fs.readFileSync(path.join(__dirname, '../../../../web/admin_hub/index.html'), 'utf8');
  const adminHubScope = require('../../../../web/admin_hub/scope.js');
  assert('orchestration admin entry is governed, not demo', adminHub.includes('source=governed') && !adminHub.includes('source=demo'));
  assert('admin shell sources project scope through the project Capability', adminHub.includes('projectScope') && adminHub.includes('project.project.read.atomic.projects_search') && adminHub.includes('AI00Business.request'));
  assert('governed entry defines a real scoped loader', index.includes('loadGovernedOrchestrationState') && index.includes('agent.orchestration.panorama.read'));
  assert('governed graph exposes tri-state governance evidence', inspector.includes('machine_passed') && inspector.includes('runtime_verified'));
  assert('admin shell unwraps nested Gateway project envelopes',
    adminHubScope.unwrapCapabilityProjects({ data: { success: true, data: [{ gid: 'p-1' }] } })[0].gid === 'p-1' &&
    adminHubScope.unwrapCapabilityProjects({ success: true, data: [{ gid: 'p-2' }] })[0].gid === 'p-2' &&
    adminHubScope.unwrapCapabilityProjects({ data: { data: { items: [{ gid: 'p-3' }] } } })[0].gid === 'p-3');
  assert('admin shell does not emit scope without authorized project',
    adminHubScope.buildOrchestrationScope({ team_id: 't-1' }, null) === null &&
    adminHubScope.buildOrchestrationScope({ team_id: 't-1' }, { gid: 'p-1' }).project_gid === 'p-1');
  let loaded = false;
  await assertAsync('bootstrap invokes governed loader', async () => {
    const target = {};
    await bootstrapOrchestrationCenter(target, {
      source: 'governed',
      app: { mountApp(_target, state, options) { loaded = state.ok && options.readOnly === true; } },
      loadGovernedState: async () => ({ ok: true }),
    });
    if (!loaded) throw new Error('governed loader was not mounted read-only');
  });
}

module.exports = { runOrchestrationGovernedEntryTests };
