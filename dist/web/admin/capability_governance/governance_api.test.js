'use strict';

const assert = require('assert/strict');
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

function makeApi() {
  const dom = new JSDOM('<!doctype html><body></body>', { runScripts: 'dangerously', url: 'http://localhost' });
  const calls = [];
  dom.window._cloudFetch = async (url, options) => {
    const body = JSON.parse(options.body);
    calls.push({ url, body });
    if (url.includes(':confirm')) {
      return { data: { confirmation_token: url.includes('base.capability_scan.run') ? 'issued-scan-token' : 'issued-write-token' } };
    }
    if (url.includes('base.capability_scan.run:invoke')) {
      return { data: { snapshot_gid: '1953048035824070998', scan_run_gid: '1953048035824070997' } };
    }
    if (url.includes('registry.search')) {
      return { data: { items: [
        { capability_version_gid: '1953048035824070656', capability_id: 'craft.factory.create', owner_domain: 'craft', business_effect: '创建工厂' },
        { capability_version_gid: '1953048035824070657', capability_id: 'base.capability_analysis.run', owner_domain: 'base', business_effect: '治理分析' },
      ], total: 264, product_capability_total: 250, governance_extension_capability_total: 14 } };
    }
    return { data: { findings: [{ finding_gid: '1953048035824070700', code: 'gap', status: 'open' }], total: 312 } };
  };
  const script = dom.window.document.createElement('script');
  script.textContent = fs.readFileSync(path.join(__dirname, 'governance_api.js'), 'utf8');
  dom.window.document.head.appendChild(script);
  return { api: dom.window.CapabilityGovernanceApi, calls };
}

function auditRows() {
  return {
    review_queue: Array.from({ length: 495 }, (_, index) => ({
      capability_key: `craft.review.item_${String(index).padStart(3, '0')}@1`,
      capability_id: `craft.review.item_${String(index).padStart(3, '0')}`,
      major_version: 1, capability_version_gid: String(1000 + index),
      business_definition_hash: `sha256:${index.toString(16).padStart(64, '0')}`,
      domain: 'craft', owner_domains: ['craft'], maturity: 'L1', priority: index + 1,
      reason: 'business_rules_missing', governance_status: 'legacy_pending_review',
      relationship_signals: index < 205 ? [`relation-${String(index).padStart(3, '0')}`] : [],
    })),
    root_causes: Array.from({ length: 495 }, (_, index) => ({
      root_cause_key: `business_rules_missing:craft.review.item_${String(index).padStart(3, '0')}@1`,
      reason_code: 'business_rules_missing',
      capability_keys: [`craft.review.item_${String(index).padStart(3, '0')}@1`],
      domains: ['craft'], evidence_refs: [`catalog:${index}`], finding_count: 1,
      remediation_family: 'declare_business_rule', severity: 'warning',
    })),
    unbound_entries: Array.from({ length: 205 }, (_, index) => ({
      entry_type: 'Provider', canonical_key: `provider:craft:${String(index).padStart(3, '0')}`,
      domain: 'craft', location: `plugins/craft/provider_${String(index).padStart(3, '0')}.py:${index + 1}`,
      source_path: `plugins/craft/provider_${String(index).padStart(3, '0')}.py`,
      source_symbol: `Provider${String(index).padStart(3, '0')}`, http_method: null, route_path: null,
    })),
    relations: Array.from({ length: 205 }, (_, index) => ({
      candidate_hash: `relation-${String(index).padStart(3, '0')}`, relation_type: 'overlap',
      source: index % 2 === 0 ? 'deterministic' : 'advisory',
      capability_keys: [`craft.review.item_${String(index).padStart(3, '0')}@1`],
      evidence: { entries: [{ key: 'reason', value_json: `"evidence-${index}"`, value_hash: `sha256:${'e'.repeat(64)}`, truncated: false }] },
      status: 'pending_review',
    })),
  };
}

function auditMetadata(collection, limit, nextCursor, overrides = {}) {
  return Object.assign({
    snapshot_gid: '991',
    source_revisions: { backend: 'a'.repeat(40), web: 'b'.repeat(40), source: 'a'.repeat(40) },
    catalog_binding: { catalog_release_id: 'catalog-r9', catalog_hash: `sha256:${'d'.repeat(64)}` },
    finding_count: 495, root_cause_group_count: 495, affected_capability_count: 495,
    affected_domains: ['craft'], shared_remediation_family_count: 1,
    shared_remediation_families: [{ family: 'declare_business_rule', count: 495 }],
    maturity_counts: { L0: 0, L1: 495, L2: 0, L3: 0, L4: 0, L5: 0, L6: 0 },
    layer_counts: { A: 0, B: 0, C: 495, D: 0, E: 0, F: 0, G: 0 },
    machine_passed: false, human_approved: false, runtime_verified: false,
    legacy_pending_review_count: 495, root_cause_count: 495, relation_count: 205,
    unbound_entry_count: 205, review_queue_count: 495, collection, limit, next_cursor: nextCursor,
  }, overrides);
}

async function runGovernanceApiTests() {
  const { api, calls } = makeApi();
  const dashboard = await api.loadDashboard({ query: 'craft', domain: 'craft', limit: 999 });
  assert.equal(calls.length, 2);
  assert.deepEqual(calls[0].body.payload, { query: 'craft', limit: 200, domain: 'craft' }, 'registry search forwards the server-side domain filter and caps its explicit limit');
  assert.deepEqual(calls[1].body.payload, { query: 'craft', domain: 'craft' }, 'finding search forwards the server-side domain filter');
  assert.deepEqual(dashboard.rows.map((row) => row.gid), ['1953048035824070656', '1953048035824070657']);
  assert.equal(dashboard.productCapabilityCount, 1, 'product count is derived from registry entries');
  assert.equal(dashboard.governanceExtensionCapabilityCount, 1, 'governance extension count is derived from registry entries');
  assert.equal(dashboard.productCapabilityTotal, 250, 'dashboard uses the authoritative full product total');
  assert.equal(dashboard.governanceExtensionCapabilityTotal, 14, 'dashboard uses the authoritative full extension total');
  assert.equal(dashboard.findingTotal, 312, 'dashboard uses the authoritative full finding total');
  assert.equal(dashboard.productCatalogRelease, null, 'unavailable releases are not invented from a search response');
  assert.deepEqual(dashboard.findings, [{ finding_gid: '1953048035824070700', code: 'gap', status: 'open' }], 'finding responses use the declared findings envelope');

  await api.searchRegistry({ query: 'craft', domain: 'craft', offset: 200, limit: 200 });
  assert.deepEqual(calls[2].body.payload, { query: 'craft', limit: 200, offset: 200, domain: 'craft' }, 'registry pages use bounded offset and limit');
  await api.searchFindings({ query: 'gap', targetGid: 'snap-1', offset: 200, limit: 200, domain: 'craft', severity: 'blocking', status: 'open', reasonCode: 'gap' });
  assert.deepEqual(calls[3].body.payload, { query: 'gap', target_gid: 'snap-1', limit: 200, offset: 200, domain: 'craft', severity: 'blocking', status: 'open', reason_code: 'gap' }, 'finding pages forward all server-side filters');

  const snapshotDom = new JSDOM('<!doctype html><body></body>', { runScripts: 'dangerously', url: 'http://localhost' });
  snapshotDom.window._cloudFetch = async () => ({ data: { snapshot_gid: '1953048035824070999', items: [] } });
  const snapshotScript = snapshotDom.window.document.createElement('script');
  snapshotScript.textContent = fs.readFileSync(path.join(__dirname, 'governance_api.js'), 'utf8');
  snapshotDom.window.document.head.appendChild(snapshotScript);
  const snapshotDashboard = await snapshotDom.window.CapabilityGovernanceApi.loadDashboard();
  assert.equal(snapshotDashboard.snapshot_gid, '1953048035824070999', 'dashboard retains the authoritative snapshot gid');

  await api.getGraph('1953048035824070656', { maxDepth: 9, maxNodes: 999 });
  assert.deepEqual(calls[4].body.payload, { target_gid: '1953048035824070656', max_depth: 4, max_nodes: 500 }, 'graph mapping uses the exact bounded Gateway schema');

  await api.decideReview({ targetGid: '1953048035824070656', rowVersion: 'rv-7' }, { idempotencyKey: 'review-1', confirmationToken: 'confirm-1' });
  assert.deepEqual(calls[5].body, {
    version: 1,
    payload: { target_gid: '1953048035824070656', idempotency_key: 'review-1', row_version: 'rv-7', expected_resource_version: 'rv-7' },
    idempotency_key: 'review-1', expected_resource_version: 'rv-7', confirmation_token: 'confirm-1',
  }, 'review carries payload idempotency, target and current resource version');

  await api.generateRepairPrompt({ targetGid: '1953048035824070656' });
  assert.equal(calls[6].url.includes('base.capability_repair_prompt.generate:invoke'), true, 'repair prompt uses its governed capability');
  assert.deepEqual(calls[6].body.payload, { target_gid: '1953048035824070656' });

  await api.evaluateReleaseGate(
    { targetGid: '1953048035824070656' },
    { idempotencyKey: 'release-1', confirmationToken: 'confirm-release-1' },
  );
  assert.deepEqual(calls[7].body, {
    version: 1,
    payload: { target_gid: '1953048035824070656', idempotency_key: 'release-1' },
    idempotency_key: 'release-1',
    confirmation_token: 'confirm-release-1',
  }, 'release evaluation uses the governed confirmation and idempotency flow');

  await api.runScan({}, { idempotencyKey: 'scan-1', codeRevision: 'backend-rev-1' });
  assert.equal(calls[8].url.includes('base.capability_scan.run:confirm'), true, '首次扫描先申请 Gateway 确认令牌');
  assert.deepEqual(calls[8].body, {
    version: 1,
    payload: { code_revision: 'backend-rev-1', idempotency_key: 'scan-1' },
    idempotency_key: 'scan-1',
  }, '扫描确认请求使用闭合合约字段');
  assert.equal(calls[9].url.includes('base.capability_scan.run:invoke'), true, '首次扫描随后调用 Gateway');
  assert.deepEqual(calls[9].body, {
    version: 1,
    payload: { code_revision: 'backend-rev-1', idempotency_key: 'scan-1' },
    idempotency_key: 'scan-1',
    confirmation_token: 'issued-scan-token',
  }, '首次扫描调用携带一次性确认令牌');

  await api.evaluateReleaseGate({ targetGid: '1953048035824070656' }, { idempotencyKey: 'release-2' });
  assert.equal(calls[10].url.includes('base.capability_release_gate.evaluate:confirm'), true, '其他治理写操作也先申请 Gateway 确认令牌');
  assert.equal(calls[11].url.includes('base.capability_release_gate.evaluate:invoke'), true, '其他治理写操作随后调用 Gateway');
  assert.equal(calls[11].body.confirmation_token, 'issued-write-token', '其他治理写操作携带一次性确认令牌');

  const failedDom = new JSDOM('<!doctype html><body></body>', { runScripts: 'dangerously', url: 'http://localhost' });
  failedDom.window._cloudFetch = async () => ({ success: false, data: {
    ok: false,
    status: 'failed',
    error: { code: 'transaction_participant_required', message: 'Strong writes require a transactional capability provider.' },
  } });
  const failedScript = failedDom.window.document.createElement('script');
  failedScript.textContent = fs.readFileSync(path.join(__dirname, 'governance_api.js'), 'utf8');
  failedDom.window.document.head.appendChild(failedScript);
  await assert.rejects(
    failedDom.window.CapabilityGovernanceApi.runScan({}, { idempotencyKey: 'scan-failed', confirmationToken: 'confirm-failed' }),
    (error) => error && error.code === 'transaction_participant_required'
      && /transaction_participant_required/.test(error.message)
      && /transactional capability provider/.test(error.message),
    'HTTP 200 CapabilityResultV2 failures must reject with a visible stable error',
  );

  const standaloneDom = new JSDOM('<!doctype html><body></body>', { runScripts: 'dangerously', url: 'http://localhost:8094' });
  const standaloneCalls = [];
  standaloneDom.window.electronAPI = {
    authGetState: async () => ({ token: 'session-token' }),
    getConfig: async () => ({ backendUrl: 'http://localhost:8094' }),
  };
  standaloneDom.window.fetch = async (url, options) => {
    standaloneCalls.push({ url, options });
    return { ok: true, json: async () => ({ data: { items: [] } }) };
  };
  const standaloneScript = standaloneDom.window.document.createElement('script');
  standaloneScript.textContent = fs.readFileSync(path.join(__dirname, 'governance_api.js'), 'utf8');
  standaloneDom.window.document.head.appendChild(standaloneScript);
  await standaloneDom.window.CapabilityGovernanceApi.searchRegistry({ query: 'direct' });
  assert.equal(standaloneCalls[0].url, 'http://localhost:8094/api/v1/capabilities/base.capability_registry.search:invoke', '独立打开治理页使用当前后端地址');
  assert.equal(standaloneCalls[0].options.headers['X-AI00-Token'], 'session-token', '独立打开治理页复用登录 token');

  const nestedDom = new JSDOM('<!doctype html><body></body>', { runScripts: 'dangerously', url: 'http://localhost' });
  nestedDom.window._cloudFetch = async (url) => {
    const capabilityId = url.includes('registry.search') ? 'base.capability_registry.search' : 'base.capability_finding.search';
    const data = capabilityId.endsWith('registry.search')
      ? { capability_id: capabilityId, status: 'completed', items: [{ capability_version_gid: 'nested-1', capability_id: 'craft.factory.create', owner_domain: 'craft', business_effect: '创建工厂' }] }
      : { capability_id: capabilityId, status: 'completed', findings: [] };
    return { success: true, data: { ok: true, status: 'completed', data } };
  };
  const nestedScript = nestedDom.window.document.createElement('script');
  nestedScript.textContent = fs.readFileSync(path.join(__dirname, 'governance_api.js'), 'utf8');
  nestedDom.window.document.head.appendChild(nestedScript);
  const nestedDashboard = await nestedDom.window.CapabilityGovernanceApi.loadDashboard();
  assert.equal(nestedDashboard.rows.length, 1, '真实 Gateway 的 CapabilityResultV2.data.items 会解包到能力清单');
  assert.equal(nestedDashboard.rows[0].capabilityId, 'craft.factory.create');

  const queryDom = new JSDOM('<!doctype html><body></body>', { runScripts: 'dangerously', url: 'http://localhost' });
  const queryCalls = [];
  queryDom.window._cloudFetch = async (url, options) => {
    queryCalls.push({ url, body: JSON.parse(options.body) });
    if (url.includes('proposal.search')) return { data: { items: [{ proposal_gid: 'p-1', capability_id: 'craft.factory.create', status: 'submitted' }], next_cursor: null } };
    if (url.includes('health.get')) return { data: { items: [{ domain: 'craft', status: 'healthy', entry_count: 2, finding_count: 0 }] } };
    return { data: { items: [{ audit_event_gid: 'a-1', operation: 'scan', actor_gid: '42', status: 'succeeded' }] } };
  };
  const queryScript = queryDom.window.document.createElement('script');
  queryScript.textContent = fs.readFileSync(path.join(__dirname, 'governance_api.js'), 'utf8');
  queryDom.window.document.head.appendChild(queryScript);
  const queryApi = queryDom.window.CapabilityGovernanceApi;
  const proposals = await queryApi.loadProposals({ query: 'craft', domain: 'craft', stage: 'submitted', limit: 500 });
  const health = await queryApi.loadHealth(['craft']);
  const audit = await queryApi.loadAudit({ actor: '42', result: 'succeeded', limit: 500 });
  assert.equal(proposals.items[0].proposal_gid, 'p-1');
  assert.equal(health.items[0].status, 'healthy');
  assert.equal(audit.items[0].audit_event_gid, 'a-1');
  assert.deepEqual(queryCalls[0].body.payload, { query: 'craft', domain: 'craft', stage: 'submitted', limit: 200 });
  assert.deepEqual(queryCalls[1].body.payload, { domains: ['craft'] });
  assert.deepEqual(queryCalls[2].body.payload, { actor: '42', result: 'succeeded', limit: 200 });

  const reviewDom = new JSDOM('<!doctype html><body></body>', { runScripts: 'dangerously', url: 'http://localhost' });
  const reviewCalls = [];
  const collections = auditRows();
  const definitionHash = `sha256:${'1'.repeat(64)}`;
  const proposal = {
    proposal_gid: '101', capability_id: 'craft.review.item_000', capability_version_gid: '202',
    major_version: 1,
    base_snapshot_gid: '991', proposed_descriptor_hash: definitionHash,
    business_definition_hash: definitionHash, review_type: 'business_definition',
    status: 'pending_approval', row_version: '3', review_total: 0, reviews_truncated: false, reviews: [],
    review_evidence: {
      capability_key: 'craft.review.item_000@1', major_version: 1, capability_version_gid: '202',
      business_effect: 'Operators receive one exact governed result.', definition_hash: definitionHash,
      business_acceptance_criteria: ['The result is schema-valid.'],
      accepted_examples: ['A governed result is required.'], rejected_examples: ['The requested major is not one.'],
      owner_domains: ['craft'], business_rules: [{
        rule_id: 'factory.name.unique', version: 1, statement: 'Factory names are unique.',
        applies_when: 'creating a factory', enforcement_ref: 'factory.provider:create',
        error_code: 'factory_name_conflict', test_refs: ['tests/test_factory.py::test_duplicate'],
      }],
      business_maturity: { level: 'L3', reason_codes: ['runtime_pending'] },
      evidence: { redacted: true, snapshot_gid: '991', source_revision: 'a'.repeat(40), catalog_release_id: 'catalog-r9' },
      deterministic_relation_candidates: [Object.assign({}, collections.relations[0])], ai_advisory_relation_candidates: [],
    },
  };
  reviewDom.window.fetch = async () => { throw new Error('business review must use the governed cloud gateway'); };
  reviewDom.window._cloudFetch = async (url, options) => {
    const body = JSON.parse(options.body);
    reviewCalls.push({ url, body });
    if (url.includes(':confirm')) return { data: { confirmation_token: 'review-token' } };
    if (url.includes('capability_analysis.run')) return { data: { run_gid: 'run-10', run_status: 'completed' } };
    if (url.includes('capability_analysis.get')) {
      const collection = body.payload.collection || 'review_queue';
      const limit = body.payload.limit || 200;
      const offset = body.payload.cursor ? Number(body.payload.cursor.split(':')[1]) : 0;
      const rows = collections[collection];
      const nextCursor = offset + limit < rows.length ? `${collection}:${offset + limit}` : null;
      const report = Object.assign(
        auditMetadata(collection, limit, nextCursor),
        { [collection]: rows.slice(offset, offset + limit) },
      );
      return { success: true, data: { ok: true, status: 'completed', data: {
        capability_id: 'base.capability_analysis.get', status: 'completed',
        run: { run_gid: 'run-9', snapshot_gid: '991', kind: 'analysis', status: 'completed', result: { business_audit: report } },
      } } };
    }
    if (url.includes('capability_proposal.search')) {
      return { success: true, data: { ok: true, status: 'completed', data: {
        capability_id: 'base.capability_proposal.search', status: 'completed', items: [proposal],
        data: { available: true, checked_at: '2026-09-02T00:00:00Z', next_cursor: body.payload.query ? null : '101' },
      } } };
    }
    if (url.includes('capability_review.decide')) return { data: { proposal: { proposal_gid: '101', status: 'approved', row_version: '4' } } };
    throw new Error(`unexpected governed capability ${url}`);
  };
  const reviewScript = reviewDom.window.document.createElement('script');
  reviewScript.textContent = fs.readFileSync(path.join(__dirname, 'governance_api.js'), 'utf8');
  reviewDom.window.document.head.appendChild(reviewScript);
  const reviewApi = reviewDom.window.CapabilityGovernanceApi;

  await reviewApi.runAnalysis({ targetGid: '991', webRevision: 'b'.repeat(40) }, { idempotencyKey: 'analysis-web-bound' });
  const analysisRunCall = reviewCalls.findLast((call) => call.url.includes('capability_analysis.run:invoke'));
  assert.equal(analysisRunCall.body.payload.web_revision, 'b'.repeat(40), 'analysis.run forwards only the server-projected Web revision expectation');

  assert.throws(() => reviewApi.getAnalysis({ targetGid: 'run-9', collection: 'unknown' }), /collection is invalid/);
  assert.throws(() => reviewApi.getAnalysis({ targetGid: 'run-9', collection: 'review_queue', limit: 0 }), /limit is invalid/);
  assert.throws(() => reviewApi.getAnalysis({ targetGid: 'run-9', collection: 'review_queue', limit: 201 }), /limit is invalid/);
  assert.throws(() => reviewApi.getAnalysis({ targetGid: 'run-9', collection: 'root_causes', cursor: 'review_queue:200' }), /cursor is invalid/);
  assert.throws(() => reviewApi.getAnalysis({ targetGid: 'run-9', collection: 'relations', cursor: 'relations:not-a-number' }), /cursor is invalid/);

  const queue = await reviewApi.loadBusinessReviewQueue({
    analysisRunGid: 'run-9', domain: 'craft', stage: 'pending_approval', limit: 500,
    cursor: '100', reviewQueueLimit: 495,
  });
  assert.equal(queue.report.review_queue.length, 495, 'all three requested review pages are joined without truncation');
  assert.equal(new Set(queue.report.review_queue.map((item) => item.capability_key)).size, 495, 'joined review pages contain no duplicates');
  assert.equal(queue.report.review_queue[0].capability_key, 'craft.review.item_000@1');
  assert.equal(queue.report.review_queue[494].capability_key, 'craft.review.item_494@1', 'joined review pages omit no tail row');
  assert.equal(queue.report.unbound_entries.length, 205, 'the displayed unbound list exhausts its own collection cursor');
  assert.equal(queue.reviewQueueNextCursor, null);
  assert.equal(queue.report.finding_count, 495);
  assert.equal(queue.report.root_cause_group_count, 495, 'evidence rows and root-cause groups remain independent fields');
  assert.equal(queue.nextCursor, '101');
  const queueAnalysisCalls = reviewCalls.filter((call) => call.url.includes('capability_analysis.get') && call.body.payload.collection === 'review_queue');
  assert.deepEqual(queueAnalysisCalls.map((call) => call.body.payload), [
    { target_gid: 'run-9', collection: 'review_queue', limit: 200 },
    { target_gid: 'run-9', collection: 'review_queue', cursor: 'review_queue:200', limit: 200 },
    { target_gid: 'run-9', collection: 'review_queue', cursor: 'review_queue:400', limit: 95 },
  ], '495 visible review rows traverse three collection-scoped pages');
  assert.ok(reviewCalls.every((call) => /\/api\/v1\/capabilities\//.test(call.url)), 'business review uses governed capability routes only');

  await assert.rejects(
    Promise.resolve().then(() => reviewApi.loadBusinessReviewQueue({
      analysisRunGid: 'run-9', includeUnboundEntries: false, includeProposals: false,
      expectedReport: Object.assign({}, queue.report, { affected_capability_count: 494 }),
    })),
    /business_review_binding_mismatch/,
    'every aggregate metadata field participates in the stable page binding',
  );

  const detail = await reviewApi.loadBusinessReviewDetail({ analysisRunGid: 'run-9', proposalGid: '101', expectedReport: queue.report });
  assert.equal(detail.proposal.business_definition_hash, definitionHash);
  assert.equal(detail.proposal.row_version, '3');
  assert.equal(detail.proposal.review_evidence.major_version, 1);
  assert.deepEqual(detail.proposal.review_evidence.business_acceptance_criteria, ['The result is schema-valid.']);
  assert.deepEqual(detail.proposal.review_evidence.owner_domains, ['craft']);
  assert.equal(detail.report.root_causes.length, 495, 'detail exhausts the root-cause collection');
  assert.equal(detail.report.relations.length, 205, 'detail exhausts the relation collection');
  const analysisCursors = reviewCalls
    .filter((call) => call.url.includes('capability_analysis.get') && call.body.payload.cursor)
    .map((call) => call.body.payload.cursor);
  assert.ok(['review_queue:200', 'root_causes:200', 'unbound_entries:200', 'relations:200'].every((cursor) => analysisCursors.includes(cursor)), 'all four collection cursors stay collection-scoped');
  const detailProposalCall = reviewCalls.findLast((call) => call.url.includes('capability_proposal.search'));
  assert.deepEqual(detailProposalCall.body.payload, { query: '101', limit: 200 }, 'detail resolves its proposal through the governed search projection');

  const mismatchedProposal = Object.assign({}, proposal, { capability_version_gid: 'wrong-version' });
  proposal.capability_version_gid = 'wrong-version';
  await assert.rejects(
    reviewApi.loadBusinessReviewDetail({ analysisRunGid: 'run-9', proposalGid: '101', expectedReport: queue.report }),
    /business_review_binding_mismatch/,
    'proposal and review evidence version identity must match before rendering',
  );
  Object.assign(proposal, mismatchedProposal, { capability_version_gid: '202' });

  proposal.proposed_descriptor_hash = `sha256:${'2'.repeat(64)}`;
  await assert.rejects(
    reviewApi.loadBusinessReviewDetail({ analysisRunGid: 'run-9', proposalGid: '101', expectedReport: queue.report }),
    /business_review_binding_mismatch/,
    'top-level proposed descriptor hash must equal the exact review evidence definition hash',
  );
  proposal.proposed_descriptor_hash = definitionHash;

  const canonicalRelation = proposal.review_evidence.deterministic_relation_candidates[0];
  canonicalRelation.status = 'approved';
  await assert.rejects(
    reviewApi.loadBusinessReviewDetail({ analysisRunGid: 'run-9', proposalGid: '101', expectedReport: queue.report }),
    /business_review_binding_mismatch/,
    'embedded relation immutable fields must match the authoritative analysis relation page',
  );
  canonicalRelation.status = collections.relations[0].status;

  proposal.review_evidence.deterministic_relation_candidates = [];
  proposal.review_evidence.ai_advisory_relation_candidates = [canonicalRelation];
  await assert.rejects(
    reviewApi.loadBusinessReviewDetail({ analysisRunGid: 'run-9', proposalGid: '101', expectedReport: queue.report }),
    /business_review_binding_mismatch/,
    'a deterministic authoritative relation cannot be moved into the advisory category',
  );
  proposal.review_evidence.deterministic_relation_candidates = [canonicalRelation];
  proposal.review_evidence.ai_advisory_relation_candidates = [];

  canonicalRelation.source = 'advisory';
  collections.relations[0].source = 'advisory';
  await assert.rejects(
    reviewApi.loadBusinessReviewDetail({ analysisRunGid: 'run-9', proposalGid: '101', expectedReport: queue.report }),
    /business_review_binding_mismatch/,
    'an advisory authoritative relation cannot be moved into the deterministic category',
  );
  canonicalRelation.source = 'unknown';
  collections.relations[0].source = 'unknown';
  await assert.rejects(
    reviewApi.loadBusinessReviewDetail({ analysisRunGid: 'run-9', proposalGid: '101', expectedReport: queue.report }),
    /business_review_binding_mismatch/,
    'unknown authoritative relation sources fail closed',
  );
  canonicalRelation.source = 'deterministic';
  collections.relations[0].source = 'deterministic';

  proposal.review_total = 2;
  proposal.reviews = [
    { review_gid: '2', proposal_gid: '101', capability_key: 'craft.review.item_000@1', base_snapshot_gid: '991', definition_hash: definitionHash },
    { review_gid: '1', proposal_gid: '101', capability_key: 'craft.review.item_000@1', base_snapshot_gid: '991', definition_hash: definitionHash },
  ];
  await assert.rejects(
    reviewApi.loadBusinessReviewDetail({ analysisRunGid: 'run-9', proposalGid: '101', expectedReport: queue.report }),
    /business_review_binding_mismatch/,
    'append-only review history rejects reversed or duplicate review windows',
  );
  proposal.review_total = 0;
  proposal.reviews = [];

  const decisionStart = reviewCalls.length;
  await reviewApi.decideBusinessReview({
    proposalGid: '101', rowVersion: '3', definitionHash,
    decision: 'approved', decisionReason: '目的、规则和证据一致',
  }, { idempotencyKey: 'business-review-101-3-approved' });
  const decisionCalls = reviewCalls.slice(decisionStart);
  assert.equal(decisionCalls.length, 2, 'business decision uses the existing confirmation and invocation flow');
  assert.ok(decisionCalls.every((call) => call.url.includes('/api/v1/capabilities/base.capability_review.decide:')), 'business decision never bypasses the governed capability');
  assert.deepEqual(decisionCalls[1].body.payload, {
    proposal_gid: '101', row_version: '3', definition_hash: definitionHash,
    decision: 'approved', decision_reason: '目的、规则和证据一致',
    idempotency_key: 'business-review-101-3-approved',
  });
  assert.equal(decisionCalls[1].body.expected_resource_version, '3', 'CAS binds the exact current proposal row version');
  assert.throws(
    () => reviewApi.decideBusinessReview({ proposalGid: '101', rowVersion: '3', definitionHash, decision: 'approved', decisionReason: '   ' }, { idempotencyKey: 'bad' }),
    /decision_reason is required/,
  );
  await assert.rejects(
    reviewApi.loadBusinessReviewQueue({ analysisRunGid: 'run-other', includeUnboundEntries: false, includeProposals: false }),
    /business_review_binding_mismatch/,
    'a page from another governed analysis run cannot enter the queue',
  );

  const staleDom = new JSDOM('<!doctype html><body></body>', { runScripts: 'dangerously', url: 'http://localhost' });
  let stalePage = 0;
  staleDom.window.fetch = async () => { throw new Error('stale analysis must not fall back to direct fetch'); };
  staleDom.window._cloudFetch = async (_url, options) => {
    const body = JSON.parse(options.body);
    if (_url.includes('proposal.search')) return { data: { items: [], data: { next_cursor: null } } };
    stalePage += 1;
    const offset = body.payload.cursor ? 200 : 0;
    const metadata = auditMetadata('review_queue', 200, offset ? null : 'review_queue:200', stalePage === 2 ? {
      source_revisions: { backend: 'a'.repeat(40), web: 'c'.repeat(40), source: 'a'.repeat(40) },
    } : {});
    return { data: { run: {
      run_gid: 'run-9', snapshot_gid: '991', kind: 'analysis', status: 'completed',
      result: { business_audit: Object.assign(metadata, { review_queue: collections.review_queue.slice(offset, offset + 200) }) },
    } } };
  };
  const staleScript = staleDom.window.document.createElement('script');
  staleScript.textContent = fs.readFileSync(path.join(__dirname, 'governance_api.js'), 'utf8');
  staleDom.window.document.head.appendChild(staleScript);
  await assert.rejects(
    staleDom.window.CapabilityGovernanceApi.loadBusinessReviewQueue({ analysisRunGid: 'run-9', reviewQueueLimit: 400, includeUnboundEntries: false }),
    /business_review_binding_mismatch/,
    'a changed source/snapshot/catalog binding rejects the mixed page set',
  );

  const aliasDom = new JSDOM('<!doctype html><body></body>', { runScripts: 'dangerously', url: 'http://localhost' });
  aliasDom.window._cloudFetch = async () => ({ data: {
    capability_id: 'base.capability_analysis.get', status: 'completed',
    run: { run_gid: 'run-9', snapshot_gid: '991', kind: 'analysis', status: 'completed', result: {
      business_review: Object.assign(auditMetadata('review_queue', 200, null), { review_queue: collections.review_queue.slice(0, 200) }),
    } },
  } });
  const aliasScript = aliasDom.window.document.createElement('script');
  aliasScript.textContent = fs.readFileSync(path.join(__dirname, 'governance_api.js'), 'utf8');
  aliasDom.window.document.head.appendChild(aliasScript);
  await assert.rejects(
    aliasDom.window.CapabilityGovernanceApi.loadBusinessReviewQueue({ analysisRunGid: 'run-9', includeUnboundEntries: false, includeProposals: false }),
    /business_review_binding_mismatch/,
    'planned aliases cannot substitute for run.result.business_audit',
  );
}

module.exports = { runGovernanceApiTests };
