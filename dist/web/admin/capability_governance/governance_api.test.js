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
    if (url.includes('registry.search')) {
      return { data: { items: [
        { capability_version_gid: '1953048035824070656', capability_id: 'craft.factory.create', owner_domain: 'craft', business_effect: '创建工厂' },
        { capability_version_gid: '1953048035824070657', capability_id: 'base.capability_analysis.run', owner_domain: 'base', business_effect: '治理分析' },
      ] } };
    }
    return { data: { items: [] } };
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
}

module.exports = { runGovernanceApiTests };
