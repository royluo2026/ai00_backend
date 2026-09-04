'use strict';

const assert = require('assert/strict');
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');
const { CapabilityGovernanceController } = require('./governance_controller.js');
const { DOMAINS, createState, trustedRolesFromProfile } = require('./governance_model.js');

function dashboard(rows) {
  return {
    snapshot_gid: '1953048035824070656', product_catalog_release: 'product-r17', governance_extension_release: 'governance-r3',
    product_capability_count: 42, governance_extension_capability_count: 14,
    product_capability_total: 250, governance_extension_capability_total: 14, finding_total: 312,
    rows: rows || [], findings: [], proposals: [],
  };
}

function businessReviewFixture() {
  const definitionHash = `sha256:${'1'.repeat(64)}`;
  const proposal = {
    proposal_gid: '101', capability_id: 'craft.factory.create', major_version: 1, capability_version_gid: '202',
    base_snapshot_gid: '991', proposed_descriptor_hash: definitionHash,
    business_definition_hash: definitionHash,
    review_type: 'business_definition', business_identity_verified: true,
    status: 'pending_approval', row_version: '3', domain: 'craft',
    review_total: 21, reviews_truncated: true,
    reviews: Array.from({ length: 20 }, (_, index) => ({ review_gid: String(69 + index), proposal_gid: '101', capability_key: 'craft.factory.create@1', base_snapshot_gid: '991', definition_hash: definitionHash, decision: 'changes_requested', reviewer_gid: '7', decision_reason: index === 19 ? '补充边界测试' : `评审 ${index + 1}`, review_type: 'business_definition' })),
    review_evidence: {
      capability_key: 'craft.factory.create@1', major_version: 1, capability_version_gid: '202',
      definition_hash: definitionHash, business_effect: '创建可追溯的工厂主数据',
      business_acceptance_criteria: ['返回新工厂 GID'], accepted_examples: ['名称唯一时创建'], rejected_examples: ['名称重复时拒绝'],
      owner_domains: ['craft', 'factory'], business_maturity: { level: 'L3', reason_codes: ['rule_test_pending'] },
      business_rules: [{ rule_id: 'factory.name.unique', statement: '工厂名称必须唯一', applies_when: '创建工厂', enforcement_ref: 'factory.provider:create', error_code: 'factory_name_conflict', test_refs: ['tests/test_factory.py::test_duplicate'] }],
      evidence: { redacted: true, snapshot_gid: '991', source_revision: 'a'.repeat(40), catalog_release_id: 'catalog-r9' },
      deterministic_relation_candidates: [{ candidate_hash: 'rel-1', relation_type: 'overlap', source: 'deterministic', capability_keys: ['craft.factory.create@1', 'factory.structure.create@1'], evidence: { reason: 'write scope overlaps' }, status: 'pending_review' }],
      ai_advisory_relation_candidates: [{ candidate_hash: 'ai-1', relation_type: 'overlap', source: 'advisory', capability_keys: ['craft.factory.create@1'], evidence: { summary: '可能边界重叠' }, status: 'pending_review' }],
    },
  };
  return {
    proposal,
    report: {
      snapshot_gid: '991', source_revisions: { backend: 'a'.repeat(40), web: 'b'.repeat(40), source: 'a'.repeat(40) },
      catalog_binding: { catalog_release_id: 'catalog-r9', catalog_hash: `sha256:${'d'.repeat(64)}` },
      finding_count: 495, root_cause_group_count: 27, affected_domains: ['craft', 'factory'],
      maturity_counts: { L0: 0, L1: 494, L3: 1 }, layer_counts: { A: 495, B: 495, C: 25, D: 10, E: 8, F: 495, G: 495 },
      machine_passed: true, human_approved: false, runtime_verified: false, legacy_pending_review_count: 495,
      root_cause_count: 27, relation_count: 2, unbound_entry_count: 1, review_queue_count: 495,
      unbound_entries: [{ canonical_key: 'provider:craft:FactoryProvider', entry_type: 'Provider', domain: 'craft', location: 'plugins/craft/provider.py:17' }],
      root_causes: [{ root_cause_key: 'business_rules_missing:craft.factory.create@1', reason_code: 'business_rules_missing', capability_keys: ['craft.factory.create@1'], domains: ['craft'], evidence_refs: ['catalog:factory'], finding_count: 2, remediation_family: 'declare_business_rule', severity: 'warning' }],
      relations: [
        { candidate_hash: 'rel-1', relation_type: 'overlap', source: 'deterministic', capability_keys: ['craft.factory.create@1', 'factory.structure.create@1'], evidence: { reason: 'write scope overlaps' }, status: 'pending_review' },
        { candidate_hash: 'ai-1', relation_type: 'overlap', source: 'advisory', capability_keys: ['craft.factory.create@1'], evidence: { summary: '可能边界重叠' }, status: 'pending_review' },
      ],
      review_queue: Array.from({ length: 51 }, (_, index) => ({ capability_key: `craft.factory.${index}@1`, domain: 'craft', maturity: 'L1', priority: index + 1, reason: 'write_pending_review' })),
    },
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
  const governanceCss = fs.readFileSync(path.join(__dirname, 'governance.css'), 'utf8');
  assert.match(indexHtml, /data-testid="auth-status"/, '治理中心必须显示当前鉴权状态');
  assert.match(indexHtml, /已通过后端鉴权/, '治理中心必须明确显示后端鉴权结果');
  assert.match(indexHtml, /trustedRoles:\s*\[\]/, 'standalone startup grants no trusted role before /users/me succeeds');
  assert.match(indexHtml, /controller\.state\.trustedRoles\s*=\s*readTrustedRoles\(profile\)/, 'trusted roles are populated only from the server profile response');
  assert.match(governanceCss, /\.health-grid\s*\{[^}]*grid-template-columns:repeat\(5,minmax\(0,1fr\)/, 'health cards use a readable desktop column count');
  assert.doesNotMatch(governanceCss, /\.health-card-count[^}]*overflow-wrap:anywhere/, 'health counts must not wrap one character per line');
  assert.equal(DOMAINS.length, 11, 'real 11 domains must be visible to the governance UI');
  assert.deepEqual(DOMAINS.map((d) => d.id), ['base', 'agent', 'craft', 'digital_model', 'factory', 'integration', 'project_management', 'simulation', 'ontology', 'knowledge', 'device']);
  assert.deepEqual(trustedRolesFromProfile({ active_roles: ['super_admin'] }), ['super_admin']);
  assert.deepEqual(trustedRolesFromProfile({ org_role: 'super_admin' }), ['super_admin']);
  assert.deepEqual(trustedRolesFromProfile({ system_role: 'super_admin' }), ['super_admin']);
  assert.deepEqual(trustedRolesFromProfile({ role: 'super_admin', roles: ['super_admin'], permissions: ['system.capability.release'] }), [], 'untrusted profile aliases and grants cannot create a governance role');

  const rows = [
    { gid: '1953048035824070656', capabilityId: 'craft.factory.create', domain: 'craft', businessEffect: '创建工厂', lifecycle: 'active', health: 'healthy', semanticClass: 'command', findingCount: 1, contract: { input: 'FactoryCreate', output: 'Factory' } },
    { gid: '1953048035824070657', capabilityId: 'knowledge.article.read', domain: 'knowledge', businessEffect: '读取知识', lifecycle: 'active', health: 'healthy', semanticClass: 'query', findingCount: 0 },
  ];
  const { root, controller, dom } = makeController({ api: { loadDashboard: async () => dashboard(rows) } });
  await controller.refresh();
  controller.state.selectedSnapshotGid = null;
  controller.setSection('overview');
  assert.match(root.textContent, /全量产品能力/, 'overview labels the authoritative product total');
  assert.match(root.textContent, /全量治理扩展/, 'overview labels the authoritative extension total');
  assert.match(root.textContent, /全量开放 Finding/, 'overview labels the authoritative finding total');
  assert.match(root.textContent, /快照未返回/, 'overview explains missing snapshot metadata');
  controller.setSection('inventory');
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

  controller.state.findings = [
    { finding_gid: '1953048035824070662', code: 'exposure_without_capability', severity: 'blocking', status: 'open', domains: ['craft'], reason_code: 'exposure_without_capability', reason: '发现公开入口，但没有找到它通过已声明 Capability 或 Gateway 暴露的证据。', subject_summary: 'REST 路由：read_factory', evidence: ['route:evidence'] },
    { finding_gid: '1953048035824070663', code: 'gap', severity: 'warning', status: 'open', domains: ['craft'], reason_code: 'gap', reason: '该 Capability 没有可验证的实现绑定，无法证明它可以执行。', subject_summary: 'Capability：craft.example@1', evidence: ['cap:evidence'] },
  ];
  controller.render();
  const reasonFilter = root.querySelector('[data-filter-key="reasonCode"]');
  assert.ok(reasonFilter, 'finding center exposes NOK reason category filter');
  assert.equal(reasonFilter.options.length, 3, 'reason filter includes all and observed categories');
  reasonFilter.value = 'gap';
  reasonFilter.dispatchEvent(new dom.window.Event('change', { bubbles: true }));
  assert.equal(root.querySelectorAll('.finding').length, 1, 'reason category filter narrows findings');
  assert.match(root.textContent, /判定原因：.*没有可验证的实现绑定/, 'finding explains why it is NOK');
  assert.match(root.textContent, /主体：Capability：craft\.example@1/, 'finding shows a readable subject summary');

  controller.state.findings = [
    { finding_gid: 'f-1', code: 'gap', reason_code: 'gap', root_cause_key: 'gap:craft.example@1', root_cause_label: '缺少实现绑定 · craft.example@1', root_cause_count: 2, domains: ['craft'], status: 'open', severity: 'blocking' },
    { finding_gid: 'f-2', code: 'gap', reason_code: 'gap', root_cause_key: 'gap:craft.example@1', root_cause_label: '缺少实现绑定 · craft.example@1', root_cause_count: 2, domains: ['craft'], status: 'open', severity: 'blocking' },
  ];
  controller.state.findingTotal = 2;
  controller.state.findingRootCauseTotal = 1;
  controller.render();
  assert.match(root.textContent, /根因：缺少实现绑定 · craft\.example@1/, 'finding center identifies the concrete capability root cause');
  assert.match(root.textContent, /根因组 1 个/, 'finding center reports distinct actionable root-cause groups');

  const paged = makeController({
    state: createState({ rows: [{ gid: 'r-1', capabilityId: 'craft.one', domain: 'craft' }], productCapabilityTotal: 250, catalogPageLimit: 1 }),
    api: { loadDashboard: async () => dashboard([{ gid: 'r-1', capabilityId: 'craft.one', domain: 'craft' }]), searchRegistry: async () => ({ items: [{ capability_version_gid: 'r-2', capability_id: 'craft.two', owner_domain: 'craft' }], total: 250 }) },
  });
  paged.controller.setSection('inventory');
  assert.ok(paged.root.querySelector('[data-action="inventory-next"]'), 'inventory exposes a next-page control');
  assert.match(paged.root.textContent, /第 1 页/, 'inventory displays its current page');

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
  sectionController.controller.state.health = [{ domain: 'craft', status: 'blocked', entry_count: 12, finding_count: 47, reason: 'blocking_findings' }];
  sectionController.controller.render();
  const craftHealthCard = sectionController.root.querySelector('.health-card[data-health-domain="craft"]');
  const craftHealthLink = sectionController.root.querySelector('.health-card-link[data-health-domain="craft"]');
  assert.ok(craftHealthLink, 'health card exposes a drill-down to domain findings');
  assert.match(craftHealthCard.textContent, /47 条 Finding/, 'health card displays the aggregated finding count');
  craftHealthLink.click();
  assert.equal(sectionController.controller.state.section, 'findings', 'health card opens Finding center');
  assert.equal(sectionController.controller.state.sectionFilters.findings.domain, 'craft', 'health drill-down keeps domain filter');

  let initialHealthLoads = 0;
  const initialHealth = makeController({
    state: createState({ section: 'health' }),
    api: {
      loadDashboard: async () => dashboard([]),
      loadHealth: async () => { initialHealthLoads += 1; return { items: [{ domain: 'craft', status: 'blocked', entry_count: 1, finding_count: 2 }] }; },
    },
  });
  initialHealth.controller.state.section = 'health';
  await initialHealth.controller.refresh();
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.ok(initialHealthLoads >= 1, 'direct health entry loads health data after dashboard refresh');
  assert.match(initialHealth.root.textContent, /2 条 Finding/, 'direct health entry renders loaded counts');

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

  const fixture = businessReviewFixture();
  const reviewController = makeController({
    state: createState({
      section: 'changes', selectedAnalysisRunGid: 'run-9', trustedRoles: ['super_admin'],
      permissions: ['system.capability.read', 'system.capability.release'],
    }),
    api: { loadDashboard: async () => dashboard([]) },
  });
  reviewController.controller.state.businessReviewReport = fixture.report;
  reviewController.controller.state.businessReviewQueue = fixture.report.review_queue;
  reviewController.controller.state.proposals = [fixture.proposal];
  reviewController.controller.state.section = 'changes';
  reviewController.controller.render();
  assert.match(reviewController.root.textContent, /Snapshot991/);
  assert.match(reviewController.root.textContent, /Finding 证据行 495 条.*根因组 27 个/s, 'queue never implies every finding is an independent fix');
  assert.match(reviewController.root.textContent, /机器检查.*通过.*超管批准.*未通过.*运行验证.*未验证/s, 'machine, human and runtime states render independently');
  assert.match(reviewController.root.textContent, /机器检查通过不代表整项 Capability 已合规/);
  assert.match(reviewController.root.textContent, /legacy_pending_review 495/);
  assert.match(reviewController.root.textContent, /provider:craft:FactoryProvider/);
  assert.match(reviewController.root.textContent, /L1：494/);
  assert.match(reviewController.root.textContent, /A：495/);
  assert.ok(reviewController.root.querySelector('[data-action="business-queue-next"]'), 'risk queue exposes stable pagination');
  assert.match(reviewController.root.textContent, /第 1 页 \/ 共 10 页 · 共 495 项/, 'risk pagination uses the authoritative queue total instead of the loaded slice');
  const currentBackendSummary = reviewController.controller.renderBusinessReviewSummary({ run_gid: '900', snapshot_gid: '991', kind: 'analysis', status: 'completed' });
  assert.match(currentBackendSummary, /机器检查[\s\S]*未返回[\s\S]*超管批准[\s\S]*未返回[\s\S]*运行验证[\s\S]*未返回/, 'missing current-backend audit states remain unknown instead of becoming false compliance claims');

  const lazyRows = Array.from({ length: 200 }, (_, index) => ({ capability_key: `craft.lazy.${index}@1`, domain: 'craft', maturity: 'L1', priority: index + 1, reason: 'pending' }));
  let lazyRequest;
  const lazyQueue = makeController({
    state: createState({ section: 'changes', selectedAnalysisRunGid: 'run-9', trustedRoles: ['super_admin'] }),
    api: {
      loadDashboard: async () => dashboard([]),
      loadBusinessReviewQueue: async (payload) => {
        lazyRequest = payload;
        return {
          report: Object.assign({}, fixture.report, {
            review_queue: Array.from({ length: 250 }, (_, index) => ({ capability_key: `craft.lazy.${index}@1`, domain: 'craft', maturity: 'L1', priority: index + 1, reason: 'pending' })),
          }),
          reviewQueueNextCursor: 'review_queue:250',
        };
      },
    },
  });
  lazyQueue.controller.state.businessReviewReport = Object.assign({}, fixture.report, { review_queue: lazyRows });
  lazyQueue.controller.state.businessReviewQueue = lazyRows;
  lazyQueue.controller.state.businessReviewQueueNextCursor = 'review_queue:200';
  lazyQueue.controller.state.businessQueuePage = 4;
  lazyQueue.controller.state.section = 'changes';
  await lazyQueue.controller.changeBusinessQueuePage(1);
  assert.equal(lazyRequest.reviewQueueLimit, 250, 'opening page five requests only enough governed queue rows for that visible page');
  assert.equal(lazyRequest.includeUnboundEntries, false, 'queue growth does not blindly reload the independent unbound collection');
  assert.equal(lazyRequest.includeProposals, false, 'queue growth does not reload proposal pagination');
  assert.equal(lazyRequest.expectedReport.snapshot_gid, '991', 'queue growth carries the existing snapshot/source binding');
  assert.equal(lazyQueue.controller.state.businessQueuePage, 5);
  assert.match(lazyQueue.root.textContent, /craft\.lazy\.200@1/, 'the newly loaded fifth page renders without omission');

  const detailHtml = reviewController.controller.renderBusinessReviewDetail(fixture.proposal);
  assert.match(detailHtml, /craft\.factory\.create@1/);
  assert.match(detailHtml, /Version GID 202/);
  assert.match(detailHtml, new RegExp(fixture.proposal.business_definition_hash));
  assert.match(detailHtml, /创建可追溯的工厂主数据/);
  assert.match(detailHtml, /返回新工厂 GID.*名称唯一时创建.*名称重复时拒绝/s);
  assert.match(detailHtml, /factory\.name\.unique.*factory\.provider:create.*test_duplicate/s);
  assert.match(detailHtml, /business_rules_missing:craft\.factory\.create@1.*2 条 Finding/s, 'detail uses the analysis root-cause collection for the exact capability major');
  assert.match(detailHtml, /rel-1/, 'detail uses the authoritative analysis relation collection for the exact capability major');
  assert.match(detailHtml, /机器证据/);
  assert.match(detailHtml, /AI 辅助建议（不参与自动批准）/);
  assert.match(detailHtml, /关系提示只辅助人工判断，绝不会自动批准/);
  assert.match(detailHtml, /补充边界测试/);
  assert.match(detailHtml, /仅显示最新 20 条中的 20 条|评审历史共 21 条/, 'truncated append-only history is explicit instead of silently hiding older reviews');
  assert.match(detailHtml, /craft、factory/);
  assert.match(detailHtml, /data-action="decide-business-review"/, 'trusted super_admin receives the business decision control');

  const swappedCategory = JSON.parse(JSON.stringify(fixture.proposal));
  swappedCategory.review_evidence.ai_advisory_relation_candidates = swappedCategory.review_evidence.deterministic_relation_candidates;
  swappedCategory.review_evidence.deterministic_relation_candidates = [];
  assert.doesNotMatch(
    reviewController.controller.renderBusinessReviewDetail(swappedCategory),
    /data-action="decide-business-review"/,
    'category-swapped authoritative relations close the detail and decision controls',
  );

  const nonAdmin = makeController({ state: createState({ trustedRoles: ['team_admin'], permissions: ['system.capability.read', 'system.capability.release'] }) });
  assert.doesNotMatch(nonAdmin.controller.renderBusinessReviewDetail(fixture.proposal), /data-action="decide-business-review"/, 'release permission without trusted super_admin role cannot decide');

  let stalePayload;
  const staleDecision = makeController({
    state: createState({ section: 'changes', trustedRoles: ['super_admin'], permissions: ['system.capability.read', 'system.capability.release'] }),
    api: {
      loadDashboard: async () => dashboard([]),
      decideBusinessReview: async (payload, options) => {
        stalePayload = { payload, options };
        throw Object.assign(new Error('proposal_row_version_mismatch: stale review'), { code: 'proposal_row_version_mismatch' });
      },
    },
  });
  staleDecision.controller.state.proposals = [fixture.proposal];
  staleDecision.controller.state.selectedBusinessReview = fixture.proposal;
  staleDecision.controller.state.businessReviewReport = fixture.report;
  const decided = await staleDecision.controller.decideBusinessReview('approved', '目的、规则和证据一致');
  assert.equal(decided, false);
  assert.deepEqual(stalePayload.payload, {
    proposalGid: '101', rowVersion: '3', definitionHash: fixture.proposal.business_definition_hash,
    decision: 'approved', decisionReason: '目的、规则和证据一致',
  }, 'decision binds exact proposal, row version, hash, decision and reason');
  assert.match(stalePayload.options.idempotencyKey, /business-review-101-3-approved/);
  assert.equal(fixture.proposal.status, 'pending_approval', 'stale failure never fakes an approved state');
  assert.match(staleDecision.root.textContent, /proposal_row_version_mismatch/);
  assert.equal(staleDecision.root.querySelector('[data-testid="governance-error"]'), staleDecision.dom.window.document.activeElement, 'stale failure moves focus to the visible error status');

  let rejectQueue;
  const pendingQueue = makeController({
    state: createState({ section: 'changes', selectedAnalysisRunGid: 'run-9' }),
    api: {
      loadDashboard: async () => dashboard([]),
      loadBusinessReviewQueue: () => new Promise((_resolve, reject) => { rejectQueue = reject; }),
    },
  });
  pendingQueue.controller.state.section = 'changes';
  const pendingLoad = pendingQueue.controller.loadBusinessReviewQueue();
  assert.equal(pendingQueue.root.querySelector('main').getAttribute('aria-busy'), 'true', 'queue loading is exposed as semantic busy state');
  assert.equal(pendingQueue.root.querySelector('[data-action="refresh"]').disabled, true, 'relevant refresh control is disabled while the section is pending');
  rejectQueue(new Error('business_review_binding_mismatch'));
  assert.equal(await pendingLoad, false);
  const loadError = pendingQueue.root.querySelector('[data-testid="governance-error"]');
  assert.equal(loadError.getAttribute('role'), 'alert');
  assert.equal(loadError, pendingQueue.dom.window.document.activeElement, 'queue contract failure moves focus to the visible alert');

  let resolvePage;
  let pageCalls = 0;
  const pendingPager = makeController({
    state: createState({ section: 'changes', selectedAnalysisRunGid: 'run-9' }),
    api: {
      loadDashboard: async () => dashboard([]),
      loadBusinessReviewQueue: () => { pageCalls += 1; return new Promise((resolve) => { resolvePage = resolve; }); },
    },
  });
  pendingPager.controller.state.businessReviewReport = fixture.report;
  pendingPager.controller.state.businessReviewQueue = fixture.report.review_queue;
  pendingPager.controller.state.businessProposalNextCursor = 'next-proposals';
  pendingPager.controller.state.businessReviewQueueNextCursor = 'review_queue:51';
  pendingPager.controller.state.section = 'changes';
  const firstPage = pendingPager.controller.loadBusinessReviewQueue({ cursor: 'next-proposals', direction: 'next' });
  assert.equal(pendingPager.root.querySelector('[data-action="business-queue-next"]').disabled, true, 'queue pager is disabled during its governed load');
  assert.equal(pendingPager.root.querySelector('[data-action="business-proposals-next"]').disabled, true, 'proposal pager is disabled during its governed load');
  assert.equal(await pendingPager.controller.loadBusinessReviewQueue({ cursor: 'next-proposals', direction: 'next' }), false, 'double pager activation is suppressed');
  resolvePage({ report: fixture.report, proposals: [fixture.proposal], nextCursor: null, reviewQueueNextCursor: null });
  await firstPage;
  assert.equal(pageCalls, 1);

  const detailResolvers = new Map();
  const secondProposal = Object.assign({}, fixture.proposal, {
    proposal_gid: '102', reviews: fixture.proposal.reviews.map((review) => Object.assign({}, review, { proposal_gid: '102' })),
  });
  const detailRace = makeController({
    state: createState({ section: 'changes', selectedAnalysisRunGid: 'run-9', trustedRoles: ['super_admin'] }),
    api: {
      loadDashboard: async () => dashboard([]),
      loadBusinessReviewDetail: ({ proposalGid }) => new Promise((resolve) => detailResolvers.set(proposalGid, resolve)),
    },
  });
  detailRace.controller.state.businessReviewReport = fixture.report;
  detailRace.controller.state.proposals = [fixture.proposal, secondProposal];
  detailRace.controller.state.section = 'changes';
  const olderDetail = detailRace.controller.loadBusinessReviewDetail('101');
  const newerDetail = detailRace.controller.loadBusinessReviewDetail('102');
  assert.equal(detailRace.root.querySelector('main').getAttribute('aria-busy'), 'true', 'detail load exposes semantic busy state');
  assert.match(detailRace.root.textContent, /正在加载评审详情/);
  detailResolvers.get('102')({ report: fixture.report, proposal: secondProposal });
  await newerDetail;
  detailResolvers.get('101')({ report: fixture.report, proposal: fixture.proposal });
  await olderDetail;
  assert.equal(detailRace.controller.state.selectedBusinessReview.proposal_gid, '102', 'an older detail response cannot overwrite the newer selection');
}

module.exports = { runGovernanceControllerTests };
