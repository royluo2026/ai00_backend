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

  async function standaloneFetch(path, options = {}) {
    const state = await hostWindow?.electronAPI?.authGetState?.() || {};
    const config = await hostWindow?.electronAPI?.getConfig?.() || {};
    const base = String(config.backendUrl || hostWindow?._AI00_BASE || hostWindow?.location?.origin || '').replace(/\/$/, '');
    const fetcher = hostWindow && typeof hostWindow.fetch === 'function' ? hostWindow.fetch.bind(hostWindow) : null;
    if (!fetcher) throw new Error('浏览器 Fetch 不可用');
    const response = await fetcher(`${base}${path}`, Object.assign({}, options, {
      headers: Object.assign({
        'Content-Type': 'application/json',
        ...(state.token ? { 'X-AI00-Token': state.token } : {}),
      }, options.headers || {}),
    }));
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = data && data.detail;
      const message = typeof detail === 'string' ? detail : detail && detail.message || `HTTP ${response.status}`;
      throw new Error(message);
    }
    return data;
  }

  function gateway() {
    try {
      const fetcher = hostWindow && hostWindow.parent && hostWindow.parent._cloudFetch;
      if (typeof fetcher === 'function') return fetcher;
    } catch (_) { /* cross-origin parent; use the local authenticated fallback */ }
    if (typeof hostWindow?._cloudFetch === 'function') return hostWindow._cloudFetch;
    return standaloneFetch;
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

  function unwrapInvocation(result) {
    if (!result || typeof result !== 'object') return result;
    // The HTTP route returns {success, data: CapabilityResultV2}; the
    // CapabilityResultV2 itself then carries the provider projection in its
    // own `data` field.  Tests and compatibility adapters may already return
    // the inner `{data: projection}` shape, so support both without inventing
    // fields or changing read envelopes.
    const envelope = result.success === true && result.data && typeof result.data === 'object'
      ? result.data
      : result;
    const failed = result.success === false || envelope.ok === false;
    if (failed) {
      const data = envelope.data || {};
      const error = envelope.error || data.error || data;
      const code = error && error.code ? String(error.code) : '';
      const message = (error && error.message) || code || '治理操作失败';
      const failure = new Error(code && message !== code ? `${code}: ${message}` : String(message));
      if (code) failure.code = code;
      if (error && error.details) failure.details = error.details;
      throw failure;
    }
    if (result.success === true && envelope.data !== undefined) return envelope.data;
    if (result.success === undefined && result.data !== undefined) return result.data;
    return result;
  }

  async function invoke(capabilityId, payload, options = {}) {
    const result = await gateway()(`/api/v1/capabilities/${capabilityId}:invoke`, {
      method: 'POST',
      body: JSON.stringify({
        version: 1,
        payload,
        idempotency_key: options.idempotencyKey,
        expected_resource_version: options.expectedResourceVersion,
        confirmation_token: options.confirmationToken,
      }),
    });
    // The HTTP endpoint deliberately keeps business failures at HTTP 200 so
    // callers can inspect the complete CapabilityResultV2 envelope.  Do not
    // silently treat {success:false} as a successful scan/action: surface the
    // stable error code and readable message to the controller.
    return unwrapInvocation(result);
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

  async function requestConfirmation(capabilityId, payload, options) {
    const confirmation = await gateway()(`/api/v1/capabilities/${capabilityId}:confirm`, {
      method: 'POST',
      body: JSON.stringify({
        version: 1,
        payload,
        idempotency_key: options.idempotencyKey,
        expected_resource_version: options.expectedResourceVersion,
      }),
    });
    const confirmed = confirmation && confirmation.data ? confirmation.data : confirmation;
    const confirmationToken = confirmed && confirmed.confirmation_token;
    if (!confirmationToken) throw new Error('Gateway 未返回治理操作确认令牌');
    return confirmationToken;
  }

  async function write(capabilityId, payload, options) {
    const request = writeOptions(options, payload);
    if (request.options.confirmationToken) return invoke(capabilityId, request.payload, request.options);
    const confirmationToken = await requestConfirmation(capabilityId, request.payload, request.options);
    return invoke(capabilityId, request.payload, Object.assign({}, request.options, { confirmationToken }));
  }

  const runAnalysis = ({ targetGid }, options) => write('base.capability_analysis.run', { target_gid: gid(targetGid) }, options);
  const generateRepairPrompt = ({ targetGid }) => invoke('base.capability_repair_prompt.generate', { target_gid: gid(targetGid) });
  const runScan = ({ targetGid, codeRevision } = {}, options) => write(
    'base.capability_scan.run',
    Object.assign({ code_revision: String(codeRevision || options && options.codeRevision || 'test-governance-ui') }, targetGid ? { target_gid: gid(targetGid) } : {}),
    options,
  );
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
  const evaluateReleaseGate = ({ targetGid } = {}, options) => write(
    'base.capability_release_gate.evaluate',
    targetGid ? { target_gid: gid(targetGid) } : {},
    options,
  );

  function normalizeEnvelope(result) {
    const hasCollection = result && (Array.isArray(result.items) || Array.isArray(result.findings) || Array.isArray(result.events) || result.release);
    const value = hasCollection ? result : (result && result.data && typeof result.data === 'object' ? result.data : result);
    return value && typeof value === 'object' ? value : {};
  }

  function boundedList(value, maximum = 11) {
    if (!Array.isArray(value)) return [];
    return value.map((item) => String(item || '').trim()).filter(Boolean).slice(0, maximum);
  }

  function loadProposals({ query = '', domain = '', stage = '', limit, cursor } = {}) {
    const payload = { query: String(query || '') };
    if (domain) payload.domain = String(domain);
    if (stage) payload.stage = String(stage);
    if (limit !== undefined) payload.limit = boundedInteger(limit, COLLECTION_LIMIT, COLLECTION_MAX);
    if (cursor) payload.cursor = String(cursor);
    return invoke('base.capability_proposal.search', payload).then(normalizeEnvelope);
  }

  function loadHealth(domains, { snapshotGid } = {}) {
    const payload = {};
    const selected = boundedList(domains, 11);
    if (selected.length) payload.domains = selected;
    if (snapshotGid !== null && snapshotGid !== undefined && snapshotGid !== '') payload.snapshot_gid = gid(snapshotGid);
    return invoke('base.capability_health.get', payload).then(normalizeEnvelope);
  }

  function loadAudit({ from, to, actor, capability, eventType, result, limit, cursor } = {}) {
    const payload = {};
    for (const [key, value] of Object.entries({ from, to, actor, capability, event_type: eventType, result, cursor })) {
      if (value !== null && value !== undefined && String(value).trim()) payload[key] = String(value).trim();
    }
    if (limit !== undefined) payload.limit = boundedInteger(limit, COLLECTION_LIMIT, COLLECTION_MAX);
    return invoke('base.capability_audit.search', payload).then(normalizeEnvelope);
  }

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
      findings: (findingData && (findingData.findings || findingData.items)) || [],
      snapshot_gid: (registryData && (registryData.snapshot_gid || registryData.snapshotGid)) || null,
      productCapabilityCount: rows.length - extensionRows.length,
      governanceExtensionCapabilityCount: extensionRows.length,
      productCatalogRelease: null,
      governanceExtensionRelease: null,
    };
  }

  return { COLLECTION_LIMIT, COLLECTION_MAX, invoke, searchRegistry, getCapability, getGraph, searchFindings, runAnalysis, getAnalysis, runScan, runTest, submitProposal, decideReview, grantWaiver, revokeWaiver, generateRepairPrompt, evaluateReleaseGate, loadProposals, loadHealth, loadAudit, loadDashboard };
});
