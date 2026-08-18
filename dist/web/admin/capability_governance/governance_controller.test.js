'use strict';

const assert = require('assert/strict');
const { JSDOM } = require('jsdom');
const { CapabilityGovernanceController } = require('./governance_controller.js');
const { DOMAINS, createState } = require('./governance_model.js');

function dashboard(rows) {
  return {
    snapshot_gid: '1953048035824070656', product_catalog_release: 'product-r17', governance_extension_release: 'governance-r3',
    product_capability_count: 42, governance_extension_capability_count: 14, rows: rows || [], findings: [], proposals: [],
  };
}

function makeController({ api, state } = {}) {
  const dom = new JSDOM('<!doctype html><body><main id="app"></main></body>', { url: 'http://localhost/#inventory' });
  const root = dom.window.document.querySelector('#app');
  const controller = new CapabilityGovernanceController({
    root,
    api: api || { loadDashboard: async () => dashboard([]) },
    state: state || createState({ permissions: ['system.capability.read', 'system.capability.analyze', 'system.capability.govern', 'system.capability.release'] }),
    location: dom.window.location,
    window: dom.window,
  });
  controller.render();
  return { dom, root, controller };
}

async function runGovernanceControllerTests() {
  assert.equal(DOMAINS.length, 11, 'real 11 domains must be visible to the governance UI');
  assert.deepEqual(DOMAINS.map((d) => d.id), ['base', 'agent', 'craft', 'digital-model', 'factory', 'integration', 'project-management', 'simulation', 'ontology', 'knowledge', 'device']);

  const rows = [
    { gid: '1953048035824070656', capabilityId: 'craft.factory.create', domain: 'craft', businessEffect: '创建工厂', lifecycle: 'active', health: 'healthy', semanticClass: 'command', findingCount: 1, contract: { input: 'FactoryCreate', output: 'Factory' } },
    { gid: '1953048035824070657', capabilityId: 'knowledge.article.read', domain: 'knowledge', businessEffect: '读取知识', lifecycle: 'active', health: 'healthy', semanticClass: 'query', findingCount: 0 },
  ];
  const { root, controller, dom } = makeController({ api: { loadDashboard: async () => dashboard(rows) } });
  await controller.refresh();
  assert.equal(root.querySelectorAll('[data-domain]').length, 12, 'renders an all-domains control plus every real domain filter');
  const search = root.querySelector('[data-testid="governance-search"]');
  search.value = '创建工厂';
  search.dispatchEvent(new dom.window.Event('input', { bubbles: true }));
  assert.equal(root.querySelectorAll('[data-row-gid]').length, 1, 'search filters inventory rows');
  root.querySelector('[data-row-gid]').click();
  assert.equal(controller.state.selectedEntity.gid, '1953048035824070656', 'selection retains snowflake GID as a string');
  assert.match(root.querySelector('[data-testid="detail-drawer"]').textContent, /FactoryCreate/, 'drawer displays read-only contract fields');

  controller.state.findings = [{ gid: '1953048035824070660', findingType: 'conflict', subjectVersionGids: ['1953048035824070656', '1953048035824070657'], domains: ['craft', 'knowledge'], confidence: 0.9, status: 'candidate' }];
  controller.setSection('findings');
  assert.match(root.textContent, /craft.*knowledge|knowledge.*craft/, 'cross-domain finding keeps every subject together');

  controller.state.proposals = [{ gid: '1953048035824070661', status: 'stale', title: 'Catalog mismatch' }];
  controller.setSection('changes');
  const review = root.querySelector('[data-action="decide-review"]');
  assert.equal(review.disabled, true, 'stale proposal disables review action');

  const retainedRows = [{ gid: '1953048035824070999', capabilityId: 'base.audit.read', domain: 'base', businessEffect: '读取审计' }];
  const failed = makeController({ state: createState({ rows: retainedRows, permissions: ['system.capability.read'] }), api: { loadDashboard: async () => { throw new Error('offline'); } } });
  await failed.controller.refresh();
  assert.equal(failed.controller.state.rows, retainedRows, 'refresh failure retains old successful data');
  assert.equal(failed.controller.state.staleData, true);

  let firstRefreshResolve;
  const firstRefresh = new Promise((resolve) => { firstRefreshResolve = resolve; });
  let refreshCalls = 0;
  const refreshing = makeController({ api: { loadDashboard: async () => { refreshCalls += 1; return firstRefresh; } } });
  const initialRefresh = refreshing.controller.refresh();
  const duplicateRefresh = refreshing.controller.refresh();
  assert.equal(await duplicateRefresh, false, 'rapid refresh clicks are suppressed while the refresh key is busy');
  firstRefreshResolve(dashboard([{ gid: '1953048035824070888', capabilityId: 'craft.factory.create', domain: 'craft', businessEffect: '创建工厂' }]));
  await initialRefresh;
  assert.equal(refreshCalls, 1);
  assert.equal(refreshing.controller.state.rows[0].gid, '1953048035824070888', 'the completed newest refresh owns state');

  const deferred = [];
  const racing = makeController({ api: { loadDashboard: () => new Promise((resolve) => deferred.push(resolve)) } });
  const older = racing.controller.refresh();
  const newer = racing.controller.refresh({ supersede: true });
  deferred[1](dashboard([{ gid: '1953048035824070002', capabilityId: 'knowledge.article.read', domain: 'knowledge', businessEffect: '读取知识' }]));
  await newer;
  deferred[0](dashboard([{ gid: '1953048035824070001', capabilityId: 'craft.factory.create', domain: 'craft', businessEffect: '创建工厂' }]));
  await older;
  assert.equal(racing.controller.state.rows[0].gid, '1953048035824070002', 'an older response cannot overwrite a newer refresh result');

  let calls = 0;
  let resolveAction;
  const pending = new Promise((resolve) => { resolveAction = resolve; });
  const busy = makeController();
  const entity = { gid: '1953048035824070777' };
  const first = busy.controller.runAction('run-analysis', entity, async () => { calls += 1; await pending; });
  const second = busy.controller.runAction('run-analysis', entity, async () => { calls += 1; });
  assert.equal(await second, false, 'duplicate action is suppressed while busy');
  resolveAction();
  await first;
  assert.equal(calls, 1);

  const readOnly = makeController({ state: createState({ permissions: ['system.capability.read'] }) });
  assert.equal(readOnly.root.querySelectorAll('[data-action="confirm-finding"]').length, 0, 'permission matrix hides governance actions for readers');
  assert.equal(readOnly.root.querySelectorAll('[data-action="edit-contract"], [data-action="delete-contract"]').length, 0, 'contract edit/delete is never offered');
  const governor = makeController({ state: createState({ permissions: ['system.capability.read', 'system.capability.govern'] }) });
  assert.equal(governor.root.querySelectorAll('[data-action="confirm-finding"], [data-action="reject-candidate"]').length, 0, 'unsupported finding mutations are not exposed as analysis calls');

  let repairPayload;
  let reviewPayload;
  const governed = makeController({
    state: createState({ selectedSnapshotGid: '1953048035824070880', proposals: [{ gid: '1953048035824070881', rowVersion: 'rv-3', confirmationToken: 'untrusted-row-token' }], permissions: ['system.capability.read', 'system.capability.analyze', 'system.capability.govern', 'system.capability.release'] }),
    api: { loadDashboard: async () => dashboard([]), generateRepairPrompt: async (payload) => { repairPayload = payload; }, decideReview: async (payload, options) => { reviewPayload = { payload, options }; } },
  });
  await governed.controller.dispatchAction('generate-repair-prompt', '1953048035824070881');
  assert.deepEqual(repairPayload, { targetGid: '1953048035824070880' }, 'repair prompt dispatches to its exact capability with the pinned snapshot');
  await governed.controller.dispatchAction('decide-review', '1953048035824070881');
  assert.deepEqual(reviewPayload.payload, { targetGid: '1953048035824070881', rowVersion: 'rv-3' }, 'review dispatch carries target and current row version');
  assert.equal(reviewPayload.options.idempotencyKey, 'decide-review-1953048035824070881');
  assert.equal(Object.hasOwn(reviewPayload.options, 'confirmationToken'), false, 'controller leaves confirmation acquisition to the Gateway-backed API');

  let nativeDialogs = 0;
  dom.window.alert = dom.window.confirm = dom.window.prompt = () => { nativeDialogs += 1; };
  root.querySelector('[data-section="overview"]').click();
  assert.equal(nativeDialogs, 0, 'navigation never calls native dialogs');
}

module.exports = { runGovernanceControllerTests };
