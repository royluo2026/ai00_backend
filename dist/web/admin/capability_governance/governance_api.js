'use strict';

(function(root, factory) {
  const api = factory(root);
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.CapabilityGovernanceApi = api;
})(typeof window !== 'undefined' ? window : globalThis, function(hostWindow) {
  const COLLECTION_LIMIT = 100;
  const COLLECTION_MAX = 200;
  const GRAPH_DEPTH_MAX = 4;
  const GRAPH_NODES_MAX = 500;

  function gateway() {
    const fetcher = hostWindow && hostWindow.parent && hostWindow.parent._cloudFetch;
    if (typeof fetcher !== 'function') throw new Error('Authenticated parent _cloudFetch is unavailable');
    return fetcher;
  }

  function boundedInteger(value, fallback, maximum) {
    const requested = typeof value === 'number' && Number.isFinite(value) ? Math.floor(value) : fallback;
    return Math.min(Math.max(requested, 1), maximum);
  }

  function gid(value) {
    if (value === null || value === undefined || value === '') throw new Error('target_gid is required');
    return String(value);
  }

  function writeOptions(options, payload) {
    const idempotencyKey = options && options.idempotencyKey || payload && payload.idempotency_key;
    if (!idempotencyKey) throw new Error('idempotency_key is required');
    return {
      payload: Object.assign({}, payload, { idempotency_key: String(idempotencyKey) }),
      options: Object.assign({}, options, { idempotencyKey: String(idempotencyKey) }),
    };
  }

  async function invoke(capabilityId, payload, options = {}) {
    return gateway()(`/api/v1/capabilities/${capabilityId}:invoke`, {
      method: 'POST',
      body: JSON.stringify({
        version: 1,
        payload,
        idempotency_key: options.idempotencyKey,
        expected_resource_version: options.expectedResourceVersion,
        confirmation_token: options.confirmationToken,
      }),
    });
  }

  async function confirm(capabilityId, payload, options = {}) {
    return gateway()(`/api/v1/capabilities/${capabilityId}:confirm`, {
      method: 'POST',
      body: JSON.stringify({
        version: 1,
        payload,
        idempotency_key: options.idempotencyKey,
        expected_resource_version: options.expectedResourceVersion,
      }),
    });
  }

  function searchRegistry({ query = '', limit } = {}) {
    return invoke('base.capability_registry.search', { query: String(query), limit: boundedInteger(limit, COLLECTION_LIMIT, COLLECTION_MAX) });
  }

  function searchFindings({ query = '', targetGid } = {}) {
    const payload = { query: String(query) };
    if (targetGid !== null && targetGid !== undefined && targetGid !== '') payload.target_gid = String(targetGid);
    return invoke('base.capability_finding.search', payload);
  }

  const getCapability = ({ targetGid }) => invoke('base.capability_registry.get', { target_gid: gid(targetGid) });
  const getAnalysis = ({ targetGid }) => invoke('base.capability_analysis.get', { target_gid: gid(targetGid) });
  const getGraph = (targetGid, { maxDepth, maxNodes } = {}) => invoke('base.capability_graph.get', { target_gid: gid(targetGid), max_depth: boundedInteger(maxDepth, 2, GRAPH_DEPTH_MAX), max_nodes: boundedInteger(maxNodes, 100, GRAPH_NODES_MAX) });

  async function write(capabilityId, payload, options) {
    const request = writeOptions(options, payload);
    const confirmation = await confirm(capabilityId, request.payload, request.options);
    const confirmed = confirmation && confirmation.data ? confirmation.data : confirmation;
    const confirmationToken = confirmed && confirmed.confirmation_token;
    if (!confirmationToken) throw new Error('Gateway confirmation token is required');
    return invoke(capabilityId, request.payload, Object.assign({}, request.options, { confirmationToken }));
  }

  const runAnalysis = ({ targetGid }, options) => write('base.capability_analysis.run', { target_gid: gid(targetGid) }, options);
  const generateRepairPrompt = ({ targetGid }) => invoke('base.capability_repair_prompt.generate', { target_gid: gid(targetGid) });
  const runScan = ({ targetGid } = {}, options) => write('base.capability_scan.run', targetGid ? { target_gid: gid(targetGid) } : {}, options);
  const runTest = ({ targetGid }, options) => write('base.capability_test.run', { target_gid: gid(targetGid) }, options);
  const submitProposal = ({ targetGid }, options) => write('base.capability_proposal.submit', { target_gid: gid(targetGid) }, options);
  const grantWaiver = ({ targetGid }, options) => write('base.capability_waiver.grant', { target_gid: gid(targetGid) }, options);
  const decideReview = ({ targetGid, rowVersion }, options = {}) => {
    const version = String(rowVersion || options.expectedResourceVersion || '');
    if (!version) throw new Error('row_version is required');
    return write('base.capability_review.decide', { target_gid: gid(targetGid), row_version: version, expected_resource_version: version }, Object.assign({}, options, { expectedResourceVersion: version }));
  };
  const revokeWaiver = ({ targetGid, rowVersion }, options = {}) => {
    const version = String(rowVersion || options.expectedResourceVersion || '');
    if (!version) throw new Error('row_version is required');
    return write('base.capability_waiver.revoke', { target_gid: gid(targetGid), row_version: version, expected_resource_version: version }, Object.assign({}, options, { expectedResourceVersion: version }));
  };
  const evaluateReleaseGate = ({ targetGid } = {}) => invoke('base.capability_release_gate.evaluate', targetGid ? { target_gid: gid(targetGid) } : {});

  function toRow(item) {
    return {
      gid: String(item.capability_version_gid || item.gid),
      capabilityId: item.capability_id || item.capabilityId,
      domain: item.owner_domain || item.domain,
      businessEffect: item.business_effect || item.businessEffect,
      semanticClass: item.semantic_class || item.semanticClass,
      lifecycle: item.lifecycle_status || item.lifecycle,
      health: item.health,
      contract: item.contract_projection || item.contract,
    };
  }

  function isGovernanceExtension(row) { return String(row.capabilityId || '').startsWith('base.capability_'); }

  async function loadDashboard(filters = {}) {
    const [registry, findings] = await Promise.all([
      searchRegistry({ query: filters.query, limit: filters.limit }),
      searchFindings({ query: filters.query }),
    ]);
    const registryData = registry && registry.data ? registry.data : registry;
    const findingData = findings && findings.data ? findings.data : findings;
    const rows = ((registryData && registryData.items) || []).map(toRow);
    const extensionRows = rows.filter(isGovernanceExtension);
    return {
      rows,
      findings: (findingData && findingData.items) || [],
      productCapabilityCount: rows.length - extensionRows.length,
      governanceExtensionCapabilityCount: extensionRows.length,
      productCatalogRelease: null,
      governanceExtensionRelease: null,
    };
  }

  return { COLLECTION_LIMIT, COLLECTION_MAX, invoke, confirm, searchRegistry, getCapability, getGraph, searchFindings, runAnalysis, getAnalysis, runScan, runTest, submitProposal, decideReview, grantWaiver, revokeWaiver, generateRepairPrompt, evaluateReleaseGate, loadDashboard };
});
