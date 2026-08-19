'use strict';

const assert = require('assert/strict');
const fs = require('fs');
const path = require('path');
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
  const indexHtml = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');
  assert.match(indexHtml, /data-testid="auth-status"/, '治理中心必须显示当前鉴权状态');
  assert.match(indexHtml, /已通过后端鉴权/, '治理中心必须明确显示后端鉴权结果');
  assert.equal(DOMAINS.length, 11, 'real 11 domains must be visible to the governance UI');
  assert.deepEqual(DOMAINS.map((d) => d.id), ['base', 'agent', 'craft', 'digital_model', 'factory', 'integration', 'project_management', 'simulation', 'ontology', 'knowledge', 'device']);

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
  let releasePayload;
  const governed = makeController({
    state: createState({ selectedSnapshotGid: '1953048035824070880', proposals: [{ gid: '1953048035824070881', rowVersion: 'rv-3' }], permissions: ['system.capability.read', 'system.capability.analyze', 'system.capability.govern', 'system.capability.release'] }),
    api: { loadDashboard: async () => dashboard([]), generateRepairPrompt: async (payload) => { repairPayload = payload; }, decideReview: async (payload, options) => { reviewPayload = { payload, options }; }, evaluateReleaseGate: async (payload, options) => { releasePayload = { payload, options }; } },
  });
  await governed.controller.dispatchAction('generate-repair-prompt', '1953048035824070881');
  assert.deepEqual(repairPayload, { targetGid: '1953048035824070880' }, 'repair prompt dispatches to its exact capability with the pinned snapshot');
  await governed.controller.dispatchAction('decide-review', '1953048035824070881');
  assert.deepEqual(reviewPayload.payload, { targetGid: '1953048035824070881', rowVersion: 'rv-3' }, 'review dispatch carries target and current row version');
  assert.equal(reviewPayload.options.idempotencyKey, 'decide-review-1953048035824070881');
  await governed.controller.dispatchAction('evaluate-release', '1953048035824070880');
  assert.deepEqual(releasePayload.payload, { targetGid: '1953048035824070880' }, 'release dispatch uses the pinned snapshot');
  assert.equal(releasePayload.options.idempotencyKey, 'evaluate-release-1953048035824070880', 'release dispatch is idempotent');

  let scanPayload;
  let scanOptions;
  let scanRefreshes = 0;
  const scanController = makeController({
    state: createState({ permissions: ['system.capability.read', 'system.capability.govern'] }),
    api: {
      loadDashboard: async () => { scanRefreshes += 1; return dashboard([{ gid: '1953048035824070882', capabilityId: 'base.project.search', domain: 'base', businessEffect: '搜索项目' }]); },
      runScan: async (payload, options) => { scanPayload = payload; scanOptions = options; },
    },
  });
  const scanButton = scanController.root.querySelector('[data-action="run-scan"]');
  assert.ok(scanButton, '管理员看到首次扫描入口');
  let resolveScan;
  scanController.controller.api.runScan = async (payload, options) => { scanPayload = payload; scanOptions = options; await new Promise((resolve) => { resolveScan = resolve; }); };
  const pendingScan = scanController.controller.dispatchAction('run-scan');
  const busyScanButton = scanController.root.querySelector('[data-action="run-scan"]');
  assert.equal(busyScanButton.disabled, true, '扫描请求进行中时按钮被禁用');
  assert.equal(busyScanButton.textContent, '扫描中…', '扫描请求进行中时显示明确进度');
  resolveScan();
  await pendingScan;
  assert.deepEqual(scanPayload, { codeRevision: 'test-governance-ui' }, '首次扫描使用受控代码修订标识');
  assert.match(scanOptions.idempotencyKey, /^run-scan-global-\d+-1$/, '每次扫描使用新的幂等键，失败后可重试');
  assert.ok(scanRefreshes >= 1, '首次扫描完成后刷新治理快照');

  const filterController = makeController({ api: { loadDashboard: async () => dashboard(rows) } });
  await filterController.controller.refresh();
  filterController.root.querySelector('[data-domain="craft"]').click();
  assert.equal(filterController.controller.state.filters.domain, 'craft', '选择领域后保留领域筛选');
  filterController.root.querySelector('[data-domain="craft"]').click();
  assert.equal(filterController.controller.state.filters.domain, 'all', '再次点击当前领域可清除筛选');
  filterController.root.querySelector('[data-domain="knowledge"]').click();
  assert.equal(filterController.controller.state.filters.domain, 'knowledge', '可直接切换到另一个领域');
  filterController.root.querySelector('[data-action="clear-domain-filter"]').click();
  assert.equal(filterController.controller.state.filters.domain, 'all', '清除按钮恢复全部领域');

  let nativeDialogs = 0;
  dom.window.alert = dom.window.confirm = dom.window.prompt = () => { nativeDialogs += 1; };
  root.querySelector('[data-section="overview"]').click();
  assert.equal(nativeDialogs, 0, 'navigation never calls native dialogs');

  let sectionLoads = [];
  const sectionController = makeController({
    api: {
      loadDashboard: async () => dashboard(rows),
      loadHealth: async (domains) => { sectionLoads.push(['health', domains]); return { items: [{ domain: 'craft', status: 'healthy', entry_count: 2, finding_count: 0, checked_at: 'now' }] }; },
      loadAudit: async (filters) => { sectionLoads.push(['audit', filters]); return { items: [{ audit_event_gid: 'a-1', operation: 'scan', actor_gid: '42', status: 'succeeded' }] }; },
      loadProposals: async (filters) => { sectionLoads.push(['changes', filters]); return { items: [{ proposal_gid: 'p-1', capability_id: 'craft.factory.create', status: 'submitted', row_version: '1' }] }; },
    },
  });
  sectionController.controller.setSection('health');
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(sectionLoads[0][0], 'health', 'health section loads its real capability');
  assert.match(sectionController.root.textContent, /healthy/, 'health section renders returned status');
  sectionController.controller.setSection('changes');
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.match(sectionController.root.textContent, /craft\.factory\.create/, 'changes section renders proposal data');
  sectionController.controller.setSection('audit');
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.match(sectionController.root.textContent, /scan/, 'audit section renders returned audit data');

  const staleSection = makeController({
    state: createState({ health: [{ domain: 'craft', status: 'healthy' }] }),
    api: { loadDashboard: async () => dashboard([]), loadHealth: async () => { throw Object.assign(new Error('governance_dependency_unavailable'), { code: 'governance_dependency_unavailable' }); } },
  });
  staleSection.controller.setSection('health');
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(staleSection.controller.state.health[0].status, 'healthy', 'section failure retains last successful health data');
  assert.match(staleSection.root.textContent, /governance_dependency_unavailable/, 'section failure is visible');
}

module.exports = { runGovernanceControllerTests };
