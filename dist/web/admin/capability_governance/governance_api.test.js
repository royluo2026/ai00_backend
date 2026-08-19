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
      ] } };
    }
    return { data: { findings: [{ finding_gid: '1953048035824070700', code: 'gap', status: 'open' }] } };
  };
  const script = dom.window.document.createElement('script');
  script.textContent = fs.readFileSync(path.join(__dirname, 'governance_api.js'), 'utf8');
  dom.window.document.head.appendChild(script);
  return { api: dom.window.CapabilityGovernanceApi, calls };
}

async function runGovernanceApiTests() {
  const { api, calls } = makeApi();
  const dashboard = await api.loadDashboard({ query: 'craft', domain: 'craft', limit: 999 });
  assert.equal(calls.length, 2);
  assert.deepEqual(calls[0].body.payload, { query: 'craft', limit: 200 }, 'registry search sends only closed-schema fields and caps its explicit limit');
  assert.deepEqual(calls[1].body.payload, { query: 'craft' }, 'finding search does not receive unsupported domain or limit fields');
  assert.deepEqual(dashboard.rows.map((row) => row.gid), ['1953048035824070656', '1953048035824070657']);
  assert.equal(dashboard.productCapabilityCount, 1, 'product count is derived from registry entries');
  assert.equal(dashboard.governanceExtensionCapabilityCount, 1, 'governance extension count is derived from registry entries');
  assert.equal(dashboard.productCatalogRelease, null, 'unavailable releases are not invented from a search response');
  assert.deepEqual(dashboard.findings, [{ finding_gid: '1953048035824070700', code: 'gap', status: 'open' }], 'finding responses use the declared findings envelope');

  const snapshotDom = new JSDOM('<!doctype html><body></body>', { runScripts: 'dangerously', url: 'http://localhost' });
  snapshotDom.window._cloudFetch = async () => ({ data: { snapshot_gid: '1953048035824070999', items: [] } });
  const snapshotScript = snapshotDom.window.document.createElement('script');
  snapshotScript.textContent = fs.readFileSync(path.join(__dirname, 'governance_api.js'), 'utf8');
  snapshotDom.window.document.head.appendChild(snapshotScript);
  const snapshotDashboard = await snapshotDom.window.CapabilityGovernanceApi.loadDashboard();
  assert.equal(snapshotDashboard.snapshot_gid, '1953048035824070999', 'dashboard retains the authoritative snapshot gid');

  await api.getGraph('1953048035824070656', { maxDepth: 9, maxNodes: 999 });
  assert.deepEqual(calls[2].body.payload, { target_gid: '1953048035824070656', max_depth: 4, max_nodes: 500 }, 'graph mapping uses the exact bounded Gateway schema');

  await api.decideReview({ targetGid: '1953048035824070656', rowVersion: 'rv-7' }, { idempotencyKey: 'review-1', confirmationToken: 'confirm-1' });
  assert.deepEqual(calls[3].body, {
    version: 1,
    payload: { target_gid: '1953048035824070656', idempotency_key: 'review-1', row_version: 'rv-7', expected_resource_version: 'rv-7' },
    idempotency_key: 'review-1', expected_resource_version: 'rv-7', confirmation_token: 'confirm-1',
  }, 'review carries payload idempotency, target and current resource version');

  await api.generateRepairPrompt({ targetGid: '1953048035824070656' });
  assert.equal(calls[4].url.includes('base.capability_repair_prompt.generate:invoke'), true, 'repair prompt uses its governed capability');
  assert.deepEqual(calls[4].body.payload, { target_gid: '1953048035824070656' });

  await api.evaluateReleaseGate(
    { targetGid: '1953048035824070656' },
    { idempotencyKey: 'release-1', confirmationToken: 'confirm-release-1' },
  );
  assert.deepEqual(calls[5].body, {
    version: 1,
    payload: { target_gid: '1953048035824070656', idempotency_key: 'release-1' },
    idempotency_key: 'release-1',
    confirmation_token: 'confirm-release-1',
  }, 'release evaluation uses the governed confirmation and idempotency flow');

  await api.runScan({}, { idempotencyKey: 'scan-1', codeRevision: 'backend-rev-1' });
  assert.equal(calls[6].url.includes('base.capability_scan.run:confirm'), true, '首次扫描先申请 Gateway 确认令牌');
  assert.deepEqual(calls[6].body, {
    version: 1,
    payload: { code_revision: 'backend-rev-1', idempotency_key: 'scan-1' },
    idempotency_key: 'scan-1',
  }, '扫描确认请求使用闭合合约字段');
  assert.equal(calls[7].url.includes('base.capability_scan.run:invoke'), true, '首次扫描随后调用 Gateway');
  assert.deepEqual(calls[7].body, {
    version: 1,
    payload: { code_revision: 'backend-rev-1', idempotency_key: 'scan-1' },
    idempotency_key: 'scan-1',
    confirmation_token: 'issued-scan-token',
  }, '首次扫描调用携带一次性确认令牌');

  await api.evaluateReleaseGate({ targetGid: '1953048035824070656' }, { idempotencyKey: 'release-2' });
  assert.equal(calls[8].url.includes('base.capability_release_gate.evaluate:confirm'), true, '其他治理写操作也先申请 Gateway 确认令牌');
  assert.equal(calls[9].url.includes('base.capability_release_gate.evaluate:invoke'), true, '其他治理写操作随后调用 Gateway');
  assert.equal(calls[9].body.confirmation_token, 'issued-write-token', '其他治理写操作携带一次性确认令牌');

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
}

module.exports = { runGovernanceApiTests };
