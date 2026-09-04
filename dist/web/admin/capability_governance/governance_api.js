'use strict';

(function(root, factory) {
  const api = factory(root);
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.CapabilityGovernanceApi = api;
})(typeof window !== 'undefined' ? window : globalThis, function(hostWindow) {
  const COLLECTION_LIMIT = 100;
  const COLLECTION_MAX = 200;
  const ANALYSIS_COLLECTIONS = ['review_queue', 'root_causes', 'unbound_entries', 'relations'];
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

  function _cf(method, path, options = {}) {
    return gateway()(path, Object.assign({}, options, { method }));
  }

  function boundedInteger(value, fallback, maximum) {
    const requested = typeof value === 'number' && Number.isFinite(value) ? Math.floor(value) : fallback;
    return Math.min(Math.max(requested, 1), maximum);
  }

  function boundedOffset(value) {
    const requested = typeof value === 'number' && Number.isFinite(value) ? Math.floor(value) : 0;
    return Math.min(Math.max(requested, 0), 100000);
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
    const result = await _cf('POST', `/api/v1/capabilities/${capabilityId}:invoke`, {
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

  function searchRegistry({ query = '', limit, offset = 0, domain = '' } = {}) {
    const payload = { query: String(query), limit: boundedInteger(limit, COLLECTION_LIMIT, COLLECTION_MAX) };
    const bounded = boundedOffset(offset);
    if (bounded) payload.offset = bounded;
    if (domain && domain !== 'all') payload.domain = String(domain);
    return invoke('base.capability_registry.search', payload);
  }

  function searchFindings({ query = '', targetGid, limit, offset = 0, domain = '', severity = '', status = '', reasonCode = '' } = {}) {
    const payload = { query: String(query) };
    if (targetGid !== null && targetGid !== undefined && targetGid !== '') payload.target_gid = String(targetGid);
    if (limit !== undefined) payload.limit = boundedInteger(limit, COLLECTION_LIMIT, COLLECTION_MAX);
    const bounded = boundedOffset(offset);
    if (bounded) payload.offset = bounded;
    if (domain && domain !== 'all') payload.domain = String(domain);
    if (severity && severity !== 'all') payload.severity = String(severity);
    if (status && status !== 'all') payload.status = String(status);
    if (reasonCode && reasonCode !== 'all') payload.reason_code = String(reasonCode);
    return invoke('base.capability_finding.search', payload);
  }

  const getCapability = ({ targetGid }) => invoke('base.capability_registry.get', { target_gid: gid(targetGid) });
  function getAnalysis({ targetGid, collection, cursor, limit } = {}) {
    const payload = { target_gid: gid(targetGid) };
    const selected = collection === undefined ? 'review_queue' : String(collection);
    if (!ANALYSIS_COLLECTIONS.includes(selected)) throw new Error('collection is invalid');
    if (collection !== undefined) payload.collection = selected;
    if (limit !== undefined) {
      if (!Number.isInteger(limit) || limit < 1 || limit > COLLECTION_MAX) throw new Error('limit is invalid');
      payload.limit = limit;
    }
    if (cursor !== undefined && cursor !== null && cursor !== '') {
      const value = String(cursor);
      if (!new RegExp(`^${selected}:\\d+$`).test(value)) throw new Error('cursor is invalid');
      payload.cursor = value;
    }
    return invoke('base.capability_analysis.get', payload);
  }
  const getGraph = (targetGid, { maxDepth, maxNodes } = {}) => invoke('base.capability_graph.get', { target_gid: gid(targetGid), max_depth: boundedInteger(maxDepth, 2, GRAPH_DEPTH_MAX), max_nodes: boundedInteger(maxNodes, 100, GRAPH_NODES_MAX) });

  async function requestConfirmation(capabilityId, payload, options) {
    const confirmation = await _cf('POST', `/api/v1/capabilities/${capabilityId}:confirm`, {
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

  const runAnalysis = ({ targetGid, webRevision } = {}, options) => {
    const payload = { target_gid: gid(targetGid) };
    if (webRevision !== undefined && webRevision !== null && webRevision !== '') {
      if (!/^[0-9a-f]{40}$/.test(String(webRevision))) throw new Error('web_revision is invalid');
      payload.web_revision = String(webRevision);
    }
    return write('base.capability_analysis.run', payload, options);
  };
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

  function businessAuditReport(response) {
    const data = normalizeEnvelope(response);
    const run = data.run && typeof data.run === 'object' ? data.run : null;
    const result = run && run.result && typeof run.result === 'object' ? run.result : null;
    if (
      data.capability_id !== 'base.capability_analysis.get'
      || data.status !== 'completed'
      || !run || run.kind !== 'analysis' || run.status !== 'completed'
      || !result || Object.keys(result).length !== 1
      || !result.business_audit || typeof result.business_audit !== 'object'
    ) throw new Error('business_review_binding_mismatch');
    return result.business_audit;
  }

  const MATURITY_KEYS = ['L0', 'L1', 'L2', 'L3', 'L4', 'L5', 'L6'];
  const LAYER_KEYS = ['A', 'B', 'C', 'D', 'E', 'F', 'G'];
  const AUDIT_SCALARS = [
    'snapshot_gid', 'source_revisions', 'catalog_binding', 'finding_count', 'root_cause_group_count',
    'affected_capability_count', 'affected_domains', 'shared_remediation_family_count',
    'shared_remediation_families', 'maturity_counts', 'layer_counts', 'machine_passed',
    'human_approved', 'runtime_verified', 'legacy_pending_review_count', 'root_cause_count',
    'relation_count', 'unbound_entry_count', 'review_queue_count', 'collection', 'limit', 'next_cursor',
  ];

  const exactKeys = (value, keys) => value && typeof value === 'object' && !Array.isArray(value)
    && Object.keys(value).length === keys.length && keys.every((key) => Object.prototype.hasOwnProperty.call(value, key));
  const count = (value) => Number.isInteger(value) && value >= 0;
  const sha = (value) => /^[0-9a-f]{40}$/.test(String(value || ''));

  function validateAuditReport(report, collection) {
    const allowed = AUDIT_SCALARS.concat(collection);
    if (!exactKeys(report, allowed) || report.collection !== collection || !Array.isArray(report[collection])) {
      throw new Error('business_review_binding_mismatch');
    }
    if (!String(report.snapshot_gid || '') || !exactKeys(report.source_revisions, ['backend', 'web', 'source'])
      || !Object.values(report.source_revisions).every(sha)
      || !exactKeys(report.catalog_binding, ['catalog_release_id', 'catalog_hash'])
      || !String(report.catalog_binding.catalog_release_id || '')
      || !/^sha256:[0-9a-f]{64}$/.test(String(report.catalog_binding.catalog_hash || ''))) {
      throw new Error('business_review_binding_mismatch');
    }
    const countFields = [
      'finding_count', 'root_cause_group_count', 'affected_capability_count',
      'shared_remediation_family_count', 'legacy_pending_review_count', 'root_cause_count',
      'relation_count', 'unbound_entry_count', 'review_queue_count',
    ];
    if (!countFields.every((field) => count(report[field]))
      || !['machine_passed', 'human_approved', 'runtime_verified'].every((field) => typeof report[field] === 'boolean')
      || !Array.isArray(report.affected_domains) || new Set(report.affected_domains).size !== report.affected_domains.length
      || !Array.isArray(report.shared_remediation_families)
      || report.shared_remediation_family_count !== report.shared_remediation_families.length
      || !report.shared_remediation_families.every((item) => exactKeys(item, ['family', 'count']) && String(item.family || '') && count(item.count))
      || !exactKeys(report.maturity_counts, MATURITY_KEYS) || !MATURITY_KEYS.every((key) => count(report.maturity_counts[key]))
      || !exactKeys(report.layer_counts, LAYER_KEYS) || !LAYER_KEYS.every((key) => count(report.layer_counts[key]))) {
      throw new Error('business_review_binding_mismatch');
    }
    const itemKeys = {
      review_queue: ['capability_key', 'capability_id', 'major_version', 'capability_version_gid', 'business_definition_hash', 'domain', 'owner_domains', 'maturity', 'priority', 'reason', 'governance_status', 'relationship_signals'],
      root_causes: ['root_cause_key', 'reason_code', 'capability_keys', 'domains', 'evidence_refs', 'finding_count', 'remediation_family', 'severity'],
      unbound_entries: ['entry_type', 'canonical_key', 'domain', 'location', 'source_path', 'source_symbol', 'http_method', 'route_path'],
      relations: ['candidate_hash', 'relation_type', 'source', 'capability_keys', 'evidence', 'status'],
    };
    if (report[collection].some((item) => !exactKeys(item, itemKeys[collection]))) {
      throw new Error('business_review_binding_mismatch');
    }
  }

  function auditBinding(report) {
    return JSON.stringify(AUDIT_SCALARS
      .filter((field) => !['collection', 'limit', 'next_cursor'].includes(field))
      .map((field) => report && report[field]));
  }

  function collectionIdentity(collection, item) {
    if (collection === 'review_queue') return item.capability_key;
    if (collection === 'root_causes') return item.root_cause_key;
    if (collection === 'relations') return item.candidate_hash;
    return `${item.entry_type || ''}:${item.canonical_key || ''}:${item.location || ''}`;
  }

  function analysisPage(response, { analysisRunGid, collection, cursor, limit, expectedReport }) {
    const data = normalizeEnvelope(response);
    const run = data.run && typeof data.run === 'object' ? data.run : null;
    const report = businessAuditReport(data);
    if (!run || String(run.run_gid || '') !== String(analysisRunGid) || !report || typeof report !== 'object') {
      throw new Error('business_review_binding_mismatch');
    }
    validateAuditReport(report, collection);
    if (String(run.snapshot_gid || '') !== String(report.snapshot_gid || '') || report.collection !== collection || !Array.isArray(report[collection])) {
      throw new Error('business_review_binding_mismatch');
    }
    if (expectedReport && auditBinding(report) !== auditBinding(expectedReport)) throw new Error('business_review_binding_mismatch');
    if (Number(report.limit) !== limit) throw new Error('business_review_pagination_invalid');
    const expectedCursor = cursor ? `${collection}:${Number(String(cursor).split(':')[1])}` : null;
    if ((cursor || null) !== expectedCursor) throw new Error('business_review_pagination_invalid');
    const offset = cursor ? Number(String(cursor).split(':')[1]) : 0;
    const nextCursor = report.next_cursor;
    if (nextCursor !== null && nextCursor !== `${collection}:${offset + report[collection].length}`) {
      throw new Error('business_review_pagination_invalid');
    }
    return { report, nextCursor };
  }

  async function loadAnalysisCollection({ analysisRunGid, collection, target = Infinity, expectedReport } = {}) {
    const countFields = { review_queue: 'review_queue_count', root_causes: 'root_cause_count', unbound_entries: 'unbound_entry_count', relations: 'relation_count' };
    const rows = [];
    const identities = new Set();
    const cursors = new Set();
    let cursor = null;
    let firstReport = null;
    do {
      const remaining = Number.isFinite(target) ? Math.max(1, target - rows.length) : COLLECTION_MAX;
      const limit = Math.min(COLLECTION_MAX, remaining);
      const response = await getAnalysis({ targetGid: analysisRunGid, collection, cursor, limit });
      const page = analysisPage(response, {
        analysisRunGid, collection, cursor, limit, expectedReport: expectedReport || firstReport,
      });
      if (!firstReport) firstReport = page.report;
      page.report[collection].forEach((item) => {
        const identity = String(collectionIdentity(collection, item) || '');
        if (!identity || identities.has(identity)) throw new Error('business_review_pagination_invalid');
        identities.add(identity);
        rows.push(item);
      });
      cursor = page.nextCursor;
      if (cursor && cursors.has(cursor)) throw new Error('business_review_pagination_invalid');
      if (cursor) cursors.add(cursor);
      const total = Number(firstReport[countFields[collection]]);
      if (!cursor && Number.isFinite(total) && rows.length !== total) throw new Error('business_review_pagination_invalid');
    } while (cursor && rows.length < target);
    return {
      report: Object.assign({}, firstReport, { [collection]: rows, next_cursor: cursor }),
      nextCursor: cursor,
    };
  }

  async function loadBusinessReviewQueue({
    analysisRunGid, query = '', domain = '', stage = '', limit, cursor,
    reviewQueueLimit = COLLECTION_MAX, includeUnboundEntries = true, includeProposals = true, expectedReport,
  } = {}) {
    if (!Number.isInteger(reviewQueueLimit) || reviewQueueLimit < 1 || reviewQueueLimit > 100000) throw new Error('review_queue_limit is invalid');
    const [queuePage, unboundPage, proposalPage] = await Promise.all([
      loadAnalysisCollection({ analysisRunGid, collection: 'review_queue', target: reviewQueueLimit, expectedReport }),
      includeUnboundEntries ? loadAnalysisCollection({ analysisRunGid, collection: 'unbound_entries', expectedReport }) : null,
      includeProposals ? loadProposals({ query, domain, stage, limit, cursor }) : null,
    ]);
    if (unboundPage && auditBinding(unboundPage.report) !== auditBinding(queuePage.report)) throw new Error('business_review_binding_mismatch');
    const report = Object.assign({}, expectedReport || {}, queuePage.report);
    if (unboundPage) report.unbound_entries = unboundPage.report.unbound_entries;
    const normalizedProposals = proposalPage ? normalizeEnvelope(proposalPage) : {};
    const meta = normalizedProposals.data && typeof normalizedProposals.data === 'object' ? normalizedProposals.data : normalizedProposals;
    return {
      report,
      proposals: Array.isArray(normalizedProposals.items) ? normalizedProposals.items : [],
      nextCursor: meta.next_cursor || meta.nextCursor || null,
      reviewQueueNextCursor: queuePage.nextCursor,
    };
  }

  function canonicalJson(value) {
    if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
    if (value && typeof value === 'object') return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(',')}}`;
    return JSON.stringify(value);
  }

  function validateBusinessProposal(proposal, report, authoritativeRelations) {
    const evidence = proposal && proposal.review_evidence;
    const major = proposal && proposal.major_version;
    const capabilityId = String(proposal && proposal.capability_id || '');
    const capabilityKey = `${capabilityId}@${major}`;
    const definitionHash = String(proposal && proposal.business_definition_hash || '');
    const proposedHash = String(proposal && proposal.proposed_descriptor_hash || '');
    const versionGid = String(proposal && proposal.capability_version_gid || '');
    const snapshotGid = String(proposal && proposal.base_snapshot_gid || '');
    const evidenceBinding = evidence && evidence.evidence;
    if (
      !proposal || proposal.review_type !== 'business_definition'
      || !Number.isInteger(major) || major < 1 || !versionGid || !snapshotGid
      || !/^sha256:[0-9a-f]{64}$/.test(definitionHash)
      || proposedHash !== definitionHash
      || !evidence || evidence.capability_key !== capabilityKey
      || evidence.major_version !== major
      || String(evidence.capability_version_gid || '') !== versionGid
      || String(evidence.definition_hash || '') !== definitionHash
      || snapshotGid !== String(report.snapshot_gid || '')
      || !evidenceBinding || String(evidenceBinding.snapshot_gid || '') !== snapshotGid
      || String(evidenceBinding.source_revision || '') !== String(report.source_revisions.source || '')
      || String(evidenceBinding.catalog_release_id || '') !== String(report.catalog_binding.catalog_release_id || '')
      || !Array.isArray(proposal.reviews) || !count(proposal.review_total)
      || typeof proposal.reviews_truncated !== 'boolean'
      || proposal.review_total < proposal.reviews.length
      || proposal.reviews_truncated !== (proposal.review_total > proposal.reviews.length)
      || proposal.reviews.length !== Math.min(proposal.review_total, 20)
    ) throw new Error('business_review_binding_mismatch');
    const relationLists = [
      [evidence.deterministic_relation_candidates, 'deterministic'],
      [evidence.ai_advisory_relation_candidates, 'advisory'],
    ];
    const relationFields = ['candidate_hash', 'relation_type', 'source', 'capability_keys', 'evidence', 'status'];
    const relationByHash = new Map();
    if (!Array.isArray(authoritativeRelations) || authoritativeRelations.some((item) => (
      !exactKeys(item, relationFields) || !String(item.candidate_hash || '')
      || !['deterministic', 'advisory'].includes(item.source) || relationByHash.has(item.candidate_hash)
      || (relationByHash.set(item.candidate_hash, item), false)
    ))) throw new Error('business_review_binding_mismatch');
    const embedded = relationLists.flatMap(([items]) => Array.isArray(items) ? items : []);
    if (relationLists.some(([items, source]) => !Array.isArray(items) || items.some((item) => item && item.source !== source))
      || new Set(embedded.map((item) => item && item.candidate_hash)).size !== embedded.length
      || embedded.some((item) => {
        const authoritative = item && relationByHash.get(item.candidate_hash);
        return !exactKeys(item, relationFields)
          || !Array.isArray(item.capability_keys) || !item.capability_keys.includes(capabilityKey)
          || !authoritative || canonicalJson(item) !== canonicalJson(authoritative);
      })) {
      throw new Error('business_review_binding_mismatch');
    }
    if (proposal.reviews.some((review) => (
      String(review.proposal_gid || '') !== String(proposal.proposal_gid || '')
      || review.capability_key !== capabilityKey
      || String(review.base_snapshot_gid || '') !== snapshotGid
      || String(review.definition_hash || '') !== definitionHash
    ))) throw new Error('business_review_binding_mismatch');
    const reviewIds = proposal.reviews.map((review) => String(review.review_gid || ''));
    if (reviewIds.some((value) => !/^[1-9][0-9]*$/.test(value))
      || new Set(reviewIds).size !== reviewIds.length
      || reviewIds.some((value, index) => index > 0 && BigInt(value) <= BigInt(reviewIds[index - 1]))) {
      throw new Error('business_review_binding_mismatch');
    }
    return Object.assign({}, proposal, { business_identity_verified: true });
  }

  async function loadBusinessReviewDetail({ analysisRunGid, proposalGid, expectedReport } = {}) {
    const proposalKey = gid(proposalGid);
    const [rootPage, relationPage, proposalPage] = await Promise.all([
      loadAnalysisCollection({ analysisRunGid, collection: 'root_causes', expectedReport }),
      loadAnalysisCollection({ analysisRunGid, collection: 'relations', expectedReport }),
      loadProposals({ query: proposalKey, limit: COLLECTION_MAX }),
    ]);
    if (auditBinding(rootPage.report) !== auditBinding(relationPage.report)) throw new Error('business_review_binding_mismatch');
    const proposal = (proposalPage.items || []).find((item) => String(item.proposal_gid || item.gid) === proposalKey);
    if (!proposal) throw new Error('business_review_proposal_not_found');
    const verifiedProposal = validateBusinessProposal(proposal, rootPage.report, relationPage.report.relations);
    return {
      report: Object.assign({}, expectedReport || {}, rootPage.report, {
        root_causes: rootPage.report.root_causes, relations: relationPage.report.relations,
      }),
      proposal: verifiedProposal,
    };
  }

  function decideBusinessReview({ proposalGid, rowVersion, definitionHash, decision, decisionReason } = {}, options = {}) {
    const version = String(rowVersion || '').trim();
    const hash = String(definitionHash || '').trim();
    const reason = String(decisionReason || '').trim();
    if (!version) throw new Error('row_version is required');
    if (!/^sha256:[0-9a-f]{64}$/.test(hash)) throw new Error('definition_hash is required');
    if (!['approved', 'rejected', 'changes_requested'].includes(decision)) throw new Error('decision is invalid');
    if (!reason) throw new Error('decision_reason is required');
    return write('base.capability_review.decide', {
      proposal_gid: gid(proposalGid), row_version: version, definition_hash: hash,
      decision, decision_reason: reason,
    }, Object.assign({}, options, { expectedResourceVersion: version }));
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
      searchRegistry({ query: filters.query, limit: filters.limit, offset: filters.inventoryOffset, domain: filters.domain }),
      searchFindings({ query: filters.query, offset: filters.findingOffset, limit: filters.findingLimit, domain: filters.domain, severity: filters.severity, status: filters.status, reasonCode: filters.reasonCode }),
    ]);
    const registryData = registry && registry.data ? registry.data : registry;
    const findingData = findings && findings.data ? findings.data : findings;
    const rows = ((registryData && registryData.items) || []).map(toRow);
    const extensionRows = rows.filter(isGovernanceExtension);
    const registryTotal = registryData && Number.isFinite(Number(registryData.total)) ? Number(registryData.total) : null;
    const productTotal = registryData && Number.isFinite(Number(registryData.product_capability_total))
      ? Number(registryData.product_capability_total) : null;
    const extensionTotal = registryData && Number.isFinite(Number(registryData.governance_extension_capability_total))
      ? Number(registryData.governance_extension_capability_total) : null;
    const findingTotal = findingData && Number.isFinite(Number(findingData.total)) ? Number(findingData.total) : null;
    return {
      rows,
      findings: (findingData && (findingData.findings || findingData.items)) || [],
      snapshot_gid: (registryData && (registryData.snapshot_gid || registryData.snapshotGid)) || null,
      productCapabilityCount: rows.length - extensionRows.length,
      governanceExtensionCapabilityCount: extensionRows.length,
      productCapabilityTotal: productTotal,
      governanceExtensionCapabilityTotal: extensionTotal,
      findingTotal,
      findingRootCauseTotal: findingData && Number.isFinite(Number(findingData.root_cause_total)) ? Number(findingData.root_cause_total) : null,
      registryTotal,
      productCatalogRelease: null,
      governanceExtensionRelease: null,
    };
  }

  return { COLLECTION_LIMIT, COLLECTION_MAX, invoke, searchRegistry, getCapability, getGraph, searchFindings, runAnalysis, getAnalysis, runScan, runTest, submitProposal, decideReview, decideBusinessReview, grantWaiver, revokeWaiver, generateRepairPrompt, evaluateReleaseGate, loadProposals, loadBusinessReviewQueue, loadBusinessReviewDetail, loadHealth, loadAudit, loadDashboard };
});
