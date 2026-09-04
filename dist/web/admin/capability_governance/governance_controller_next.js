'use strict';

(function(root, factory) {
  const model = typeof require === 'function' ? require('./governance_model.js') : root.CapabilityGovernanceModel;
  const api = factory(root, model);
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.CapabilityGovernanceControllerNext = api.CapabilityGovernanceController;
})(typeof window !== 'undefined' ? window : globalThis, function(root, model) {
  const { DOMAINS, SECTIONS, actionsFor, createState, filterRows, mergeLoadFailure, normalizeGid } = model;
  const escapeHtml = (value) => String(value === null || value === undefined ? '' : value)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  const valueOf = (data, ...names) => {
    for (const name of names) if (data && data[name] !== undefined) return data[name];
    return null;
  };
  const rowGid = (row) => normalizeGid(valueOf(row, 'gid', 'proposal_gid', 'finding_gid', 'audit_event_gid', 'capability_version_gid'));
  const toInventoryRow = (item) => ({
    gid: String(item && (item.gid || item.capability_version_gid) || ''),
    capabilityId: item && (item.capabilityId || item.capability_id),
    domain: item && (item.domain || item.owner_domain),
    businessEffect: item && (item.businessEffect || item.business_effect),
    semanticClass: item && (item.semanticClass || item.semantic_class),
    lifecycle: item && (item.lifecycle || item.lifecycle_status),
    health: item && item.health,
    contract: item && (item.contract || item.contract_projection),
  });
  const statusLabel = (status) => {
    const normalized = String(status || 'unverified').toLowerCase();
    const icon = ['pass', 'healthy', 'active'].includes(normalized) ? '✓'
      : ['fail', 'blocked', 'broken'].includes(normalized) ? '!' : ['stale', 'expired', 'attention'].includes(normalized) ? '◷' : '•';
    return `<span class="status status-${escapeHtml(normalized)}"><span aria-hidden="true">${icon}</span> ${escapeHtml(normalized)}</span>`;
  };
  const REASON_LABELS = Object.freeze({
    provider_missing: '缺少 Provider',
    gap: '缺少实现绑定',
    exposure_without_capability: '入口未绑定能力',
    provider_without_descriptor: 'Provider 缺少目录描述',
    required_test_missing: '缺少测试证据',
    repository_table_migration_mismatch: '表与迁移不一致',
    transaction_participant_missing: '缺少事务参与者',
    permission_policy_mismatch: '权限策略不一致',
    confirmation_policy_mismatch: '确认策略不一致',
    catalog_schema_drift: '合约 Schema 漂移',
    lifecycle_incompatibility: '生命周期不兼容',
    duplicate: '疑似重复',
    semantic_overlap: '语义重叠',
    cross_domain_conflict: '跨域冲突',
    lifecycle_pair_gap: '缺少生命周期配套',
    non_atomic_facade: 'Facade 缺少事务证据',
    stale_evidence: '证据已过期',
  });
  const reasonLabel = (code) => REASON_LABELS[code] || code || '未分类';
  const unwrap = (response) => {
    const hasCollection = response && (Array.isArray(response.items) || Array.isArray(response.findings) || Array.isArray(response.events) || response.release);
    return hasCollection ? response : (response && response.data && typeof response.data === 'object' ? response.data : (response || {}));
  };
  const list = (value) => Array.isArray(value) ? value : [];
  const textValue = (value) => typeof value === 'string' ? value : JSON.stringify(value);
  const canonicalJson = (value) => {
    if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
    if (value && typeof value === 'object') return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(',')}}`;
    return JSON.stringify(value);
  };
  const businessIdentityMatches = (proposal, report) => {
    const evidence = proposal && proposal.review_evidence;
    const major = proposal && proposal.major_version;
    const capabilityKey = `${proposal && proposal.capability_id || ''}@${major}`;
    const hash = String(proposal && proposal.business_definition_hash || '');
    const version = String(proposal && proposal.capability_version_gid || '');
    const snapshot = String(proposal && proposal.base_snapshot_gid || '');
    const evidenceBinding = evidence && evidence.evidence;
    if (!proposal || proposal.business_identity_verified !== true || !report || !evidence
      || proposal.review_type !== 'business_definition'
      || !Number.isInteger(major) || major < 1 || !version || !snapshot
      || !/^sha256:[0-9a-f]{64}$/.test(hash)
      || String(proposal.proposed_descriptor_hash || '') !== hash
      || evidence.capability_key !== capabilityKey || evidence.major_version !== major
      || String(evidence.capability_version_gid || '') !== version
      || String(evidence.definition_hash || '') !== hash
      || snapshot !== String(report.snapshot_gid || '')
      || !evidenceBinding || String(evidenceBinding.snapshot_gid || '') !== snapshot
      || String(evidenceBinding.source_revision || '') !== String(report.source_revisions && report.source_revisions.source || '')
      || String(evidenceBinding.catalog_release_id || '') !== String(report.catalog_binding && report.catalog_binding.catalog_release_id || '')) return false;
    const authoritativeRelations = list(report.relations);
    if (authoritativeRelations.some((item) => !['deterministic', 'advisory'].includes(item && item.source))) return false;
    const relationByHash = new Map(authoritativeRelations.map((item) => [item.candidate_hash, item]));
    const deterministicRelations = list(evidence.deterministic_relation_candidates);
    const advisoryRelations = list(evidence.ai_advisory_relation_candidates);
    const embeddedRelations = deterministicRelations.concat(advisoryRelations);
    if (deterministicRelations.some((item) => !item || item.source !== 'deterministic')
      || advisoryRelations.some((item) => !item || item.source !== 'advisory')
      || new Set(embeddedRelations.map((item) => item && item.candidate_hash)).size !== embeddedRelations.length
      || embeddedRelations.some((item) => !list(item.capability_keys).includes(capabilityKey)
        || !relationByHash.has(item.candidate_hash)
        || canonicalJson(item) !== canonicalJson(relationByHash.get(item.candidate_hash)))) return false;
    const reviews = list(proposal.reviews);
    const reviewIds = reviews.map((review) => String(review.review_gid || ''));
    if (!Number.isInteger(proposal.review_total) || proposal.review_total < 0
      || typeof proposal.reviews_truncated !== 'boolean'
      || reviews.length !== Math.min(proposal.review_total, 20)
      || proposal.reviews_truncated !== (proposal.review_total > reviews.length)
      || reviewIds.some((value) => !/^[1-9][0-9]*$/.test(value))
      || new Set(reviewIds).size !== reviewIds.length
      || reviewIds.some((value, index) => index > 0 && BigInt(value) <= BigInt(reviewIds[index - 1]))) return false;
    return reviews.every((review) => (
      String(review.proposal_gid || '') === String(proposal.proposal_gid || '')
      && review.capability_key === capabilityKey
      && String(review.base_snapshot_gid || '') === snapshot
      && String(review.definition_hash || '') === hash
    ));
  };

  class CapabilityGovernanceController {
    constructor({ root: mount, api, state, location, window: browserWindow } = {}) {
      if (!mount) throw new Error('Governance UI requires a root element');
      this.root = mount;
      this.api = api || (root && root.CapabilityGovernanceApi);
      this.state = state || createState();
      this.location = location || (root && root.location);
      this.window = browserWindow || root;
      this.refreshGeneration = 0;
      this.sectionGenerations = {};
      this.businessDetailGeneration = 0;
      this.scanAttempt = 0;
      if (!this.state.businessReviewReport) this.state.businessReviewReport = null;
      if (!Array.isArray(this.state.businessReviewQueue)) this.state.businessReviewQueue = [];
      if (!this.state.businessReviewDraft) this.state.businessReviewDraft = { decision: 'approved', reason: '' };
      if (!Array.isArray(this.state.businessProposalCursorHistory)) this.state.businessProposalCursorHistory = [];
      if (!this.state.businessQueuePage) this.state.businessQueuePage = 1;
      if (!this.state.businessQueuePageLimit) this.state.businessQueuePageLimit = 50;
      if (this.state.businessReviewQueueNextCursor === undefined) this.state.businessReviewQueueNextCursor = null;
      this.onClick = this.onClick.bind(this);
      this.onInput = this.onInput.bind(this);
      this.onHashChange = this.onHashChange.bind(this);
      mount.addEventListener('click', this.onClick);
      mount.addEventListener('input', this.onInput);
      mount.addEventListener('change', this.onInput);
      if (this.window && this.window.addEventListener) this.window.addEventListener('hashchange', this.onHashChange);
      this.readHash();
    }

    destroy() {
      this.root.removeEventListener('click', this.onClick);
      this.root.removeEventListener('input', this.onInput);
      this.root.removeEventListener('change', this.onInput);
      if (this.window && this.window.removeEventListener) this.window.removeEventListener('hashchange', this.onHashChange);
    }

    readHash() {
      const section = String((this.location && this.location.hash) || '').replace(/^#/, '');
      if (SECTIONS.includes(section)) this.state.section = section;
    }

    onHashChange() { this.readHash(); this.render(); this.loadSection(this.state.section); }

    setSection(section) {
      this.state.section = SECTIONS.includes(section) ? section : 'overview';
      if (this.location) this.location.hash = this.state.section;
      this.render();
      this.loadSection(this.state.section);
    }

    onInput(event) {
      const target = event.target;
      if (target.matches('[data-business-decision]')) {
        this.state.businessReviewDraft = Object.assign({}, this.state.businessReviewDraft, { decision: target.value });
        return;
      }
      if (target.matches('[data-business-decision-reason]')) {
        this.state.businessReviewDraft = Object.assign({}, this.state.businessReviewDraft, { reason: target.value });
        return;
      }
      if (target.matches('[data-testid="governance-search"]')) {
        this.state.filters = Object.assign({}, this.state.filters, { query: target.value });
        this.state.inventoryPage = 1;
        this.render();
        if (this.api && typeof this.api.searchRegistry === 'function') void this.loadInventoryPage({ page: 1 });
        return;
      }
      const section = target.dataset && target.dataset.filterSection;
      const key = target.dataset && target.dataset.filterKey;
      if (section && key) {
        const previous = this.state.sectionFilters[section] || {};
        this.state.sectionFilters[section] = Object.assign({}, previous, { [key]: target.value });
        if (section === 'findings') this.state.findingPage = 1;
        this.render();
        if (section === 'findings') void this.loadSection('findings');
      }
    }

    onClick(event) {
      const healthDomain = event.target.closest('[data-health-domain]');
      if (healthDomain) {
        const domain = healthDomain.dataset.healthDomain || 'all';
        this.state.sectionFilters.findings = Object.assign({}, this.state.sectionFilters.findings, {
          domain, severity: 'all', status: 'all', reasonCode: 'all', query: '',
        });
        return this.setSection('findings');
      }
      const section = event.target.closest('[data-section]');
      if (section) return this.setSection(section.dataset.section);
      const domain = event.target.closest('[data-domain]');
      if (domain) {
        const selected = domain.dataset.domain || 'all';
        const current = this.state.filters.domain || 'all';
        this.state.filters = Object.assign({}, this.state.filters, { domain: selected !== 'all' && selected === current ? 'all' : selected });
        this.state.inventoryPage = 1;
        this.setSection('inventory');
        if (this.api && typeof this.api.searchRegistry === 'function') void this.loadInventoryPage({ page: 1 });
        return;
      }
      const row = event.target.closest('[data-row-gid]');
      if (row) return this.selectEntity(row.dataset.rowGid);
      const action = event.target.closest('[data-action]');
      if (action && !action.disabled) {
        if (action.dataset.action === 'refresh') return this.refresh();
        if (action.dataset.action === 'clear-domain-filter') {
          this.state.filters = Object.assign({}, this.state.filters, { domain: 'all' });
          this.state.inventoryPage = 1;
          this.setSection('inventory');
          if (this.api && typeof this.api.searchRegistry === 'function') void this.loadInventoryPage({ page: 1 });
          return;
        }
        if (action.dataset.action === 'inventory-next' || action.dataset.action === 'inventory-prev') {
          return this.changePage('inventory', action.dataset.action === 'inventory-next' ? 1 : -1);
        }
        if (action.dataset.action === 'findings-next' || action.dataset.action === 'findings-prev') {
          return this.changePage('findings', action.dataset.action === 'findings-next' ? 1 : -1);
        }
        if (action.dataset.action === 'business-queue-next' || action.dataset.action === 'business-queue-prev') {
          const delta = action.dataset.action === 'business-queue-next' ? 1 : -1;
          return this.changeBusinessQueuePage(delta);
        }
        if (action.dataset.action === 'business-proposals-next') {
          return this.loadBusinessReviewQueue({ cursor: this.state.businessProposalNextCursor, direction: 'next' });
        }
        if (action.dataset.action === 'business-proposals-prev') {
          const history = this.state.businessProposalCursorHistory || [];
          return this.loadBusinessReviewQueue({ cursor: history[history.length - 1] || null, direction: 'prev' });
        }
        if (action.dataset.action === 'load-business-review-detail') return this.loadBusinessReviewDetail(action.dataset.entityGid);
        if (action.dataset.action === 'close-business-review-detail') {
          this.state.selectedBusinessReview = null;
          return this.render();
        }
        if (action.dataset.action === 'decide-business-review') {
          const draft = this.state.businessReviewDraft || {};
          return this.decideBusinessReview(draft.decision, draft.reason);
        }
        if (action.dataset.action === 'clear-section-filter') {
          const sectionName = action.dataset.section || this.state.section;
          this.state.sectionFilters[sectionName] = Object.assign({}, this.state.sectionFilters[sectionName], { domain: 'all', severity: 'all', status: 'all', reasonCode: 'all', stage: 'all', query: '', actor: '', capability: '', eventType: '', result: '' });
          return this.render();
        }
        this.dispatchAction(action.dataset.action, action.dataset.entityGid);
      }
    }

    selectEntity(gid) {
      const key = normalizeGid(gid);
      this.state.selectedEntity = (this.state.rows || []).find((row) => rowGid(row) === key) || null;
      this.render();
    }

    async changePage(kind, delta) {
      const pageKey = kind === 'inventory' ? 'inventoryPage' : 'findingPage';
      const total = kind === 'inventory'
        ? Number(this.state.registryTotal || 0) || (Number(this.state.productCapabilityTotal || 0) + Number(this.state.governanceExtensionCapabilityTotal || 0))
        : Number(this.state.findingTotal || 0);
      const size = kind === 'inventory' ? Number(this.state.catalogPageLimit || 100) : Number(this.state.findingPageLimit || 200);
      const next = Math.max(1, Number(this.state[pageKey] || 1) + delta);
      if (next === Number(this.state[pageKey] || 1) || (total && (next - 1) * size >= total)) return false;
      this.state[pageKey] = next;
      if (kind === 'inventory') return this.loadInventoryPage({ page: next });
      return this.loadSection('findings');
    }

    async loadInventoryPage({ page = this.state.inventoryPage || 1 } = {}) {
      if (!this.api || typeof this.api.searchRegistry !== 'function') return false;
      const generation = (this.sectionGenerations.inventory || 0) + 1;
      this.sectionGenerations.inventory = generation;
      const pageSize = Number(this.state.catalogPageLimit || 100);
      this.state.sectionBusy = this.state.sectionBusy.includes('inventory') ? this.state.sectionBusy : this.state.sectionBusy.concat('inventory');
      this.render();
      try {
        const response = await this.api.searchRegistry({ query: this.state.filters.query, domain: this.state.filters.domain, limit: pageSize, offset: (page - 1) * pageSize });
        if (generation !== this.sectionGenerations.inventory) return false;
        const data = unwrap(response);
        this.state.rows = (valueOf(data, 'items', 'rows') || []).map(toInventoryRow);
        const total = valueOf(data, 'total', 'registryTotal');
        if (total !== null) this.state.registryTotal = Number(total);
        this.state.inventoryPage = page;
        this.state.sectionErrors.inventory = null;
        return true;
      } catch (error) {
        if (generation !== this.sectionGenerations.inventory) return false;
        this.state.sectionErrors.inventory = error && error.message ? error.message : String(error);
        return false;
      } finally {
        if (generation === this.sectionGenerations.inventory) this.state.sectionBusy = this.state.sectionBusy.filter((item) => item !== 'inventory');
        this.render();
      }
    }

    async refresh({ supersede = false } = {}) {
      const key = 'refresh:global';
      if (!this.api || typeof this.api.loadDashboard !== 'function' || (!supersede && this.state.busyActionKeys.includes(key))) return false;
      const generation = ++this.refreshGeneration;
      if (!this.state.busyActionKeys.includes(key)) this.state.busyActionKeys = this.state.busyActionKeys.concat(key);
      let dashboardLoaded = false;
      this.render();
      try {
        const response = await this.api.loadDashboard(Object.assign({}, this.state.filters, { limit: 100 }));
        if (generation !== this.refreshGeneration) return false;
        const data = unwrap(response);
        if (response && response.data && typeof response.data === 'object' && response.items) this.state.sectionMeta[section] = response.data;
        const snapshot = valueOf(data, 'snapshot_gid', 'snapshotGid');
        const productRelease = valueOf(data, 'product_catalog_release', 'productCatalogRelease');
        const extensionRelease = valueOf(data, 'governance_extension_release', 'governanceExtensionRelease');
        if (snapshot !== null) this.state.selectedSnapshotGid = normalizeGid(snapshot);
        if (productRelease !== null) this.state.productCatalogRelease = productRelease;
        if (extensionRelease !== null) this.state.governanceExtensionRelease = extensionRelease;
        const productCount = valueOf(data, 'product_capability_count', 'productCapabilityCount');
        const extensionCount = valueOf(data, 'governance_extension_capability_count', 'governanceExtensionCapabilityCount');
        const productTotal = valueOf(data, 'product_capability_total', 'productCapabilityTotal');
        const extensionTotal = valueOf(data, 'governance_extension_capability_total', 'governanceExtensionCapabilityTotal');
        const findingTotal = valueOf(data, 'finding_total', 'findingTotal');
        if (productCount !== null) this.state.productCapabilityCount = Number(productCount);
        if (extensionCount !== null) this.state.governanceExtensionCapabilityCount = Number(extensionCount);
        if (productTotal !== null) this.state.productCapabilityTotal = Number(productTotal);
        if (extensionTotal !== null) this.state.governanceExtensionCapabilityTotal = Number(extensionTotal);
        if (findingTotal !== null) this.state.findingTotal = Number(findingTotal);
        const registryTotal = valueOf(data, 'registry_total', 'registryTotal');
        const findingRootCauseTotal = valueOf(data, 'finding_root_cause_total', 'findingRootCauseTotal');
        if (registryTotal !== null) this.state.registryTotal = Number(registryTotal);
        if (findingRootCauseTotal !== null) this.state.findingRootCauseTotal = Number(findingRootCauseTotal);
        const catalogLimit = valueOf(data, 'catalog_page_limit', 'catalogPageLimit');
        const findingLimit = valueOf(data, 'finding_page_limit', 'findingPageLimit');
        if (catalogLimit !== null) this.state.catalogPageLimit = Number(catalogLimit);
        if (findingLimit !== null) this.state.findingPageLimit = Number(findingLimit);
        this.state.rows = valueOf(data, 'rows', 'items') || [];
        this.state.findings = valueOf(data, 'findings') || this.state.findings || [];
        this.state.inventoryPage = 1;
        this.state.findingPage = 1;
        this.state.proposals = valueOf(data, 'proposals') || this.state.proposals || [];
        this.state.staleData = false;
        this.state.lastError = null;
        this.state.dashboardLoaded = true;
        dashboardLoaded = true;
        return true;
      } catch (error) {
        if (generation !== this.refreshGeneration) return false;
        Object.assign(this.state, mergeLoadFailure(this.state.rows, error));
        return false;
      } finally {
        if (generation === this.refreshGeneration) this.state.busyActionKeys = this.state.busyActionKeys.filter((item) => item !== key);
        this.render();
        if (dashboardLoaded && generation === this.refreshGeneration && ['findings', 'changes', 'health', 'audit'].includes(this.state.section)) {
          void this.loadSection(this.state.section);
        }
      }
    }

    async loadSection(section) {
      if (!this.api || !['findings', 'changes', 'health', 'audit'].includes(section)) return false;
      if (section === 'changes' && this.state.selectedAnalysisRunGid && typeof this.api.loadBusinessReviewQueue === 'function') {
        return this.loadBusinessReviewQueue();
      }
      const methodMap = { findings: 'searchFindings', changes: 'loadProposals', health: 'loadHealth', audit: 'loadAudit' };
      const methodName = methodMap[section];
      if (typeof this.api[methodName] !== 'function') return false;
      if (this.state.sectionBusy.includes(section)) return false;
      const generation = (this.sectionGenerations[section] || 0) + 1;
      this.sectionGenerations[section] = generation;
      this.state.sectionBusy = this.state.sectionBusy.concat(section);
      this.render();
      try {
        const filters = this.state.sectionFilters[section] || {};
        let response;
        if (section === 'health') response = await this.api.loadHealth(DOMAINS.map((item) => item.id), { snapshotGid: this.state.selectedSnapshotGid });
        else if (section === 'findings') {
          const pageSize = Number(this.state.findingPageLimit || 200);
          response = await this.api.searchFindings({
            query: filters.query || this.state.filters.query,
            targetGid: this.state.selectedSnapshotGid,
            limit: pageSize,
            offset: (Number(this.state.findingPage || 1) - 1) * pageSize,
            domain: filters.domain,
            severity: filters.severity,
            status: filters.status,
            reasonCode: filters.reasonCode,
          });
        }
        else if (section === 'changes') response = await this.api.loadProposals(filters);
        else response = await this.api.loadAudit(filters);
        if (generation !== this.sectionGenerations[section]) return false;
        const data = unwrap(response);
        if (section === 'findings') {
          this.state.findings = valueOf(data, 'findings', 'items') || [];
          const findingTotal = valueOf(data, 'total', 'finding_total', 'findingTotal');
          if (findingTotal !== null) this.state.findingTotal = Number(findingTotal);
          const rootCauseTotal = valueOf(data, 'root_cause_total', 'finding_root_cause_total', 'findingRootCauseTotal');
          if (rootCauseTotal !== null) this.state.findingRootCauseTotal = Number(rootCauseTotal);
        }
        if (section === 'changes') this.state.proposals = valueOf(data, 'items', 'proposals') || [];
        if (section === 'health') this.state.health = valueOf(data, 'items', 'health') || [];
        if (section === 'audit') this.state.auditEvents = valueOf(data, 'items', 'events') || [];
        this.state.sectionErrors[section] = null;
        this.state.sectionStale[section] = false;
        return true;
      } catch (error) {
        if (generation !== this.sectionGenerations[section]) return false;
        this.state.sectionErrors[section] = error && error.message ? error.message : String(error);
        this.state.sectionStale[section] = true;
        return false;
      } finally {
        if (generation === this.sectionGenerations[section]) this.state.sectionBusy = this.state.sectionBusy.filter((item) => item !== section);
        this.render();
      }
    }

    async changeBusinessQueuePage(delta) {
      const current = Math.max(1, Number(this.state.businessQueuePage || 1));
      const total = Number(this.state.businessReviewReport && this.state.businessReviewReport.review_queue_count || this.state.businessReviewQueue.length);
      const pageSize = Number(this.state.businessQueuePageLimit || 50);
      const next = Math.min(Math.max(1, Math.ceil(total / pageSize)), Math.max(1, current + delta));
      if (next <= current || next * pageSize <= this.state.businessReviewQueue.length) {
        this.state.businessQueuePage = next;
        this.render();
        return true;
      }
      if (!this.state.businessReviewQueueNextCursor) return false;
      return this.loadBusinessReviewQueue({ direction: 'queue', queueTarget: next * pageSize, queuePage: next });
    }

    async loadBusinessReviewQueue({ cursor = null, direction = 'reset', queueTarget = null, queuePage = 1 } = {}) {
      if (!this.api || typeof this.api.loadBusinessReviewQueue !== 'function' || !this.state.selectedAnalysisRunGid) return false;
      if (this.state.sectionBusy.includes('changes')) return false;
      const generation = (this.sectionGenerations.changes || 0) + 1;
      this.sectionGenerations.changes = generation;
      this.state.sectionBusy = this.state.sectionBusy.concat('changes');
      this.render();
      let failed = false;
      try {
        const filters = this.state.sectionFilters.changes || {};
        const reviewQueueLimit = queueTarget || Math.max(200, this.state.businessReviewQueue.length);
        const response = await this.api.loadBusinessReviewQueue({
          analysisRunGid: this.state.selectedAnalysisRunGid,
          query: filters.query || '', domain: filters.domain === 'all' ? '' : filters.domain,
          stage: filters.stage === 'all' ? '' : filters.stage, limit: 200, cursor,
          reviewQueueLimit,
          includeUnboundEntries: direction === 'reset', includeProposals: direction !== 'queue',
          expectedReport: direction === 'reset' ? undefined : this.state.businessReviewReport,
        });
        if (generation !== this.sectionGenerations.changes) return false;
        this.state.businessReviewReport = Object.assign({}, this.state.businessReviewReport || {}, response.report || {});
        this.state.businessReviewQueue = list(response.report && response.report.review_queue);
        this.state.businessReviewQueueNextCursor = response.reviewQueueNextCursor || null;
        if (direction !== 'queue') {
          this.state.proposals = list(response.proposals);
          this.state.businessProposalNextCursor = response.nextCursor || null;
        }
        if (direction === 'next') {
          this.state.businessProposalCursorHistory = (this.state.businessProposalCursorHistory || []).concat(this.state.businessProposalCursor || null);
        } else if (direction === 'prev') {
          this.state.businessProposalCursorHistory = (this.state.businessProposalCursorHistory || []).slice(0, -1);
        } else {
          this.state.businessProposalCursorHistory = [];
        }
        if (direction !== 'queue') this.state.businessProposalCursor = cursor || null;
        if (direction === 'queue') this.state.businessQueuePage = queuePage;
        else if (direction === 'reset') this.state.businessQueuePage = 1;
        this.state.sectionErrors.changes = null;
        this.state.sectionStale.changes = false;
        return true;
      } catch (error) {
        if (generation !== this.sectionGenerations.changes) return false;
        failed = true;
        this.state.sectionErrors.changes = error && error.message ? error.message : String(error);
        this.state.lastError = this.state.sectionErrors.changes;
        this.state.sectionStale.changes = true;
        return false;
      } finally {
        if (generation === this.sectionGenerations.changes) this.state.sectionBusy = this.state.sectionBusy.filter((item) => item !== 'changes');
        this.render();
        if (failed) this.focusError();
      }
    }

    loadBusinessReviewDetail(proposalGid) {
      const proposal = (this.state.proposals || []).find((item) => rowGid(item) === normalizeGid(proposalGid));
      if (!proposal) return false;
      if (!this.api || typeof this.api.loadBusinessReviewDetail !== 'function' || !this.state.selectedAnalysisRunGid) {
        this.state.lastError = 'business_review_detail_unavailable';
        this.render();
        this.focusError();
        return false;
      }
      const generation = ++this.businessDetailGeneration;
      return this.runAction('load-business-review-detail', proposal, async () => {
        let detail;
        try {
          detail = await this.api.loadBusinessReviewDetail({
            analysisRunGid: this.state.selectedAnalysisRunGid, proposalGid: rowGid(proposal),
            expectedReport: this.state.businessReviewReport,
          });
        } catch (error) {
          if (generation !== this.businessDetailGeneration) return false;
          throw error;
        }
        if (generation !== this.businessDetailGeneration) return false;
        this.state.businessReviewReport = Object.assign({}, this.state.businessReviewReport || {}, detail.report || {});
        this.state.selectedBusinessReview = detail.proposal;
        this.state.businessReviewDraft = { decision: 'approved', reason: '' };
        return true;
      });
    }

    decideBusinessReview(decision, decisionReason) {
      const proposal = this.state.selectedBusinessReview;
      if (!proposal || !businessIdentityMatches(proposal, this.state.businessReviewReport)
        || !this.isSuperAdmin() || !this.api || typeof this.api.decideBusinessReview !== 'function') return false;
      const reason = String(decisionReason || '').trim();
      if (!reason) {
        this.state.lastError = 'decision_reason is required';
        this.render();
        this.focusError();
        return false;
      }
      const proposalGid = rowGid(proposal);
      const rowVersion = String(valueOf(proposal, 'row_version', 'rowVersion') || '');
      const evidence = proposal.review_evidence || proposal.reviewEvidence || {};
      const definitionHash = String(valueOf(proposal, 'business_definition_hash', 'businessDefinitionHash') || evidence.definition_hash || '');
      const idempotencyKey = `business-review-${proposalGid}-${rowVersion}-${decision}`;
      return this.runAction('decide-business-review', proposal, async () => {
        await this.api.decideBusinessReview({ proposalGid, rowVersion, definitionHash, decision, decisionReason: reason }, { idempotencyKey, expectedResourceVersion: rowVersion });
        if (this.state.selectedAnalysisRunGid && typeof this.api.loadBusinessReviewDetail === 'function') await this.loadBusinessReviewDetail(proposalGid);
        return true;
      });
    }

    trustedRoles() {
      return new Set(list(this.state.trustedRoles).map(String));
    }

    isSuperAdmin() { return this.trustedRoles().has('super_admin'); }

    focusError() {
      const error = this.root.querySelector('[data-testid="governance-error"]');
      if (error && typeof error.focus === 'function') error.focus();
    }

    async runAction(action, entity, executor) {
      const entityGid = normalizeGid(rowGid(entity) || (typeof entity === 'object' ? null : entity));
      const key = `${action}:${entityGid || 'global'}`;
      if (this.state.busyActionKeys.includes(key)) return false;
      this.state.busyActionKeys = this.state.busyActionKeys.concat(key);
      this.render();
      let failed = false;
      try { return await executor(); }
      catch (error) { failed = true; this.state.lastError = error && error.message ? error.message : String(error); return false; }
      finally { this.state.busyActionKeys = this.state.busyActionKeys.filter((item) => item !== key); this.render(); if (failed) this.focusError(); }
    }

    dispatchAction(action, entityGid) {
      const collections = [this.state.rows || [], this.state.proposals || [], this.state.findings || [], this.state.health || [], this.state.auditEvents || []];
      const entity = collections.flat().find((row) => rowGid(row) === normalizeGid(entityGid)) || { gid: entityGid };
      const snapshotGid = this.state.selectedSnapshotGid;
      const targetGid = ['run-analysis', 'generate-repair-prompt', 'evaluate-release'].includes(action) ? snapshotGid : normalizeGid(rowGid(entity));
      const methods = { 'run-scan': 'runScan', 'run-analysis': 'runAnalysis', 'generate-repair-prompt': 'generateRepairPrompt', 'create-proposal': 'submitProposal', 'grant-waiver': 'grantWaiver', 'revoke-waiver': 'revokeWaiver', 'decide-review': 'decideReview', 'evaluate-release': 'evaluateReleaseGate' };
      const method = methods[action];
      const targetRequired = action !== 'run-scan';
      if (!method || !this.api || typeof this.api[method] !== 'function' || (targetRequired && !targetGid)) return false;
      const rowVersion = valueOf(entity, 'rowVersion', 'row_version', 'expectedResourceVersion', 'expected_resource_version');
      if (['revoke-waiver', 'decide-review'].includes(action) && !rowVersion) {
        this.state.lastError = '当前资源版本不可用，不能执行治理操作。'; this.render(); return false;
      }
      const actionTarget = targetGid || 'global';
      const idempotencyKey = action === 'run-scan' ? `run-scan-global-${Date.now()}-${++this.scanAttempt}` : `${action}-${actionTarget}`;
      const options = { idempotencyKey, confirmationToken: entity.confirmationToken || entity.confirmation_token, expectedResourceVersion: rowVersion };
      const expectedWebRevision = this.state.businessReviewReport
        && this.state.businessReviewReport.source_revisions
        && this.state.businessReviewReport.source_revisions.web;
      const payload = action === 'run-scan' ? { codeRevision: 'test-governance-ui' }
        : action === 'run-analysis' && expectedWebRevision ? { targetGid, webRevision: expectedWebRevision }
          : (['revoke-waiver', 'decide-review'].includes(action) ? { targetGid, rowVersion } : { targetGid });
      return this.runAction(action, entity, async () => {
        const result = await this.api[method](payload, options);
        if (action === 'run-analysis') {
          const data = unwrap(result);
          const run = data.run || data;
          this.state.selectedAnalysisRunGid = normalizeGid(run.run_gid || run.runGid);
        }
        if (action === 'evaluate-release') this.state.releaseGate = unwrap(result).release || unwrap(result);
        if (action === 'run-scan') await this.refresh({ supersede: true });
        return true;
      });
    }

    renderNav() {
      const labels = { overview: '总览', inventory: '能力清单', findings: 'Finding 中心', changes: '变更与评审', health: '测试与健康', release: '发布闸门', audit: '审计' };
      return SECTIONS.map((section) => `<button class="nav-link${this.state.section === section ? ' active' : ''}" data-section="${section}" type="button">${labels[section]}</button>`).join('');
    }

    renderOverview() {
      const health = this.state.health || [];
      const attention = health.filter((item) => ['attention', 'blocked'].includes(String(item.status))).length;
      const loaded = Boolean(this.state.dashboardLoaded);
      const catalogCount = this.state.productCapabilityTotal === null ? '—' : this.state.productCapabilityTotal;
      const extensionCount = this.state.governanceExtensionCapabilityTotal === null ? '—' : this.state.governanceExtensionCapabilityTotal;
      const findingCount = !loaded || this.state.findingTotal === null ? '—' : this.state.findingTotal;
      const catalogNote = !loaded ? '未加载' : this.state.productCapabilityTotal === null ? '全量统计未返回' : `全量产品能力；清单展示最多 ${escapeHtml(this.state.catalogPageLimit)} 条`;
      const extensionNote = !loaded ? '未加载' : this.state.governanceExtensionCapabilityTotal === null ? '全量统计未返回' : `全量治理扩展；清单展示最多 ${escapeHtml(this.state.catalogPageLimit)} 条`;
      const findingNote = !loaded ? '未加载' : this.state.findingTotal === null ? '全量统计未返回' : `全量开放 Finding；中心展示最多 ${escapeHtml(this.state.findingPageLimit)} 条${attention ? ` · ${attention} 个领域需关注` : ''}`;
      const snapshotText = this.state.selectedSnapshotGid || '—';
      const snapshotNote = this.state.staleData ? '◷ 刷新失败，保留上次成功数据' : this.state.selectedSnapshotGid ? '✓ 已绑定治理快照' : loaded ? '⚠ 快照未返回（目录查询不提供快照 GID）' : '未加载';
      return `<section class="overview-grid"><article class="metric"><h2>Product Catalog</h2><strong>${escapeHtml(catalogCount)}</strong><p>${catalogNote}</p></article><article class="metric extension"><h2>Governance Extension</h2><strong>${escapeHtml(extensionCount)}</strong><p>${extensionNote}</p></article><article class="metric"><h2>Open Findings</h2><strong>${escapeHtml(findingCount)}</strong><p>${findingNote}</p></article><article class="metric"><h2>Snapshot</h2><strong class="gid">${escapeHtml(snapshotText)}</strong><p>${snapshotNote}</p></article></section><section class="domain-summary"><h2>11 个真实领域</h2>${DOMAINS.map((domain) => { const item = health.find((candidate) => candidate.domain === domain.id); return `<button type="button" data-domain="${domain.id}">${escapeHtml(domain.label)} ${item ? statusLabel(item.status) : ''}</button>`; }).join('')}</section>`;
    }

    renderInventory() {
      const rows = filterRows(this.state.rows, this.state.filters);
      const domain = this.state.filters.domain || 'all';
      const total = this.state.registryTotal === null || this.state.registryTotal === undefined
        ? Number(this.state.productCapabilityTotal || 0) + Number(this.state.governanceExtensionCapabilityTotal || 0)
        : Number(this.state.registryTotal || 0);
      const pageSize = Number(this.state.catalogPageLimit || 100);
      return `<section><div class="filters"><label>搜索 <input data-testid="governance-search" value="${escapeHtml(this.state.filters.query)}" placeholder="能力 ID、GID、业务效果"></label><div class="domain-filter"><button type="button" data-domain="all">全部领域</button>${DOMAINS.map((item) => `<button type="button" data-domain="${item.id}">${escapeHtml(item.label)}</button>`).join('')}<button type="button" data-action="clear-domain-filter"${domain === 'all' ? ' disabled' : ''}>清除领域筛选</button></div></div><div class="inventory-table" role="table"><div class="inventory-head" role="row"><span>GID / Capability</span><span>业务效果</span><span>领域</span><span>状态</span></div>${rows.map((row) => `<button type="button" class="inventory-row" data-row-gid="${escapeHtml(rowGid(row))}" role="row"><span class="gid">${escapeHtml(rowGid(row))}<br><b>${escapeHtml(row.capabilityId || row.capability_id)}</b></span><span>${escapeHtml(row.businessEffect || row.business_effect)}</span><span>${escapeHtml(row.domain)}</span>${statusLabel(row.health || row.lifecycle)}</button>`).join('') || '<p class="empty">没有符合筛选条件的能力。</p>'}</div>${this.renderPager('inventory', total, this.state.inventoryPage, pageSize)}${this.renderDrawer()}</section>`;
    }

    renderPager(kind, total, page, pageSize) {
      const safeTotal = Number(total || 0);
      const safePage = Math.max(1, Number(page || 1));
      const pages = Math.max(1, Math.ceil(safeTotal / Math.max(1, Number(pageSize || 1))));
      const label = kind === 'inventory' ? '能力清单' : 'Finding';
      return `<div class="pager" aria-label="${label}分页"><button type="button" data-action="${kind}-prev"${safePage <= 1 ? ' disabled' : ''}>上一页</button><span>第 ${safePage} 页 / 共 ${pages} 页 · 共 ${safeTotal} 条</span><button type="button" data-action="${kind}-next"${safePage >= pages ? ' disabled' : ''}>下一页</button></div>`;
    }

    renderDrawer() {
      const entity = this.state.selectedEntity;
      if (!entity) return '';
      const contract = entity.contract || entity.contract_projection || {};
      const fields = Object.entries(contract).map(([key, value]) => `<dt>${escapeHtml(key)}</dt><dd>${escapeHtml(typeof value === 'string' ? value : JSON.stringify(value))}</dd>`).join('') || '<dd>没有可用的合约投影。</dd>';
      const actions = actionsFor(this.state.permissions).filter((action) => action !== 'view' && action !== 'export' && action !== 'run-scan');
      return `<aside class="detail-drawer" data-testid="detail-drawer"><h2>能力详情</h2><p class="gid">${escapeHtml(rowGid(entity))}</p><h3>${escapeHtml(entity.capabilityId || entity.capability_id)}</h3><p>${escapeHtml(entity.businessEffect || entity.business_effect)}</p><h3>只读合约</h3><dl>${fields}</dl><div class="action-row">${actions.map((action) => `<button type="button" data-action="${action}" data-entity-gid="${escapeHtml(rowGid(entity))}">${escapeHtml(action)}</button>`).join('')}</div></aside>`;
    }

    renderFindings() {
      const filters = this.state.sectionFilters.findings || {};
      const reasonCodes = [...new Set((this.state.findings || []).map((finding) => String(finding.reason_code || finding.reasonCode || finding.code || '').trim()).filter(Boolean))].sort();
      const findings = (this.state.findings || []).filter((finding) => {
        const domains = finding.domains || finding.domain || [];
        const severity = String(finding.severity || 'warning');
        const status = String(finding.status || 'open');
        const reasonCode = String(finding.reason_code || finding.reasonCode || finding.code || '');
        const text = `${finding.code || finding.findingType || ''} ${finding.fingerprint || ''} ${reasonCode} ${finding.reason || ''} ${finding.subject_summary || finding.subjectSummary || ''}`.toLowerCase();
        return (filters.domain === 'all' || (Array.isArray(domains) ? domains.includes(filters.domain) : domains === filters.domain)) && (filters.severity === 'all' || filters.severity === severity) && (filters.status === 'all' || filters.status === status) && (filters.reasonCode === 'all' || filters.reasonCode === reasonCode) && (!filters.query || text.includes(filters.query.toLowerCase()));
      });
      const rootTotal = this.state.findingRootCauseTotal === null ? new Set(findings.map((finding) => finding.root_cause_key || finding.rootCauseKey || `${finding.reason_code || finding.code}:${finding.subject_summary || ''}`)).size : this.state.findingRootCauseTotal;
      const pageSize = Number(this.state.findingPageLimit || 200);
      return `<section><h2>Finding 中心</h2><p class="finding-summary">根因组 ${escapeHtml(rootTotal)} 个；当前页 ${escapeHtml(findings.length)} 条 Finding。根因键 = 原因类别 + 具体 Capability，便于定位修复对象。</p><div class="filters"><label>搜索 <input data-filter-section="findings" data-filter-key="query" value="${escapeHtml(filters.query || '')}" placeholder="规则、指纹、原因、Capability"></label><label>领域 <select data-filter-section="findings" data-filter-key="domain"><option value="all">全部领域</option>${DOMAINS.map((domain) => `<option value="${domain.id}"${filters.domain === domain.id ? ' selected' : ''}>${escapeHtml(domain.label)}</option>`).join('')}</select></label><label>级别 <select data-filter-section="findings" data-filter-key="severity"><option value="all">全部级别</option><option value="blocking"${filters.severity === 'blocking' ? ' selected' : ''}>blocking</option><option value="critical"${filters.severity === 'critical' ? ' selected' : ''}>critical</option><option value="error"${filters.severity === 'error' ? ' selected' : ''}>error</option><option value="warning"${filters.severity === 'warning' ? ' selected' : ''}>warning</option></select></label><label>NOK 原因类别 <select data-filter-section="findings" data-filter-key="reasonCode"><option value="all">全部原因</option>${reasonCodes.map((code) => `<option value="${escapeHtml(code)}"${filters.reasonCode === code ? ' selected' : ''}>${escapeHtml(reasonLabel(code))}</option>`).join('')}</select></label><button type="button" data-action="clear-section-filter" data-section="findings">清除筛选</button></div>${findings.map((finding) => { const reasonCode = String(finding.reason_code || finding.reasonCode || finding.code || ''); const subject = finding.subject_summary || finding.subjectSummary || (finding.subjectVersionGids || finding.subject_version_gids || []).map(normalizeGid).join('、') || '—'; const rootLabel = finding.root_cause_label || finding.rootCauseLabel || `${reasonLabel(reasonCode)} · ${subject}`; return `<article class="finding"><h3>${escapeHtml(finding.code || finding.findingType || 'finding')} ${statusLabel(finding.status)}</h3><p>根因：${escapeHtml(rootLabel)}${finding.root_cause_count ? `（影响 ${escapeHtml(finding.root_cause_count)} 条证据）` : ''}</p><p>主体：${escapeHtml(subject)}</p><p>领域：${(finding.domains || []).map(escapeHtml).join('、') || '跨领域'}</p><p>严重级别：${escapeHtml(finding.severity || 'warning')}</p><p>原因类别：${escapeHtml(reasonLabel(reasonCode))}</p><p>判定原因：${escapeHtml(finding.reason || '未提供判定原因')}</p><p>证据：${(finding.evidence || []).map(escapeHtml).join('、') || '—'}</p></article>`; }).join('') || '<p class="empty">没有符合条件的 Finding。</p>'}${this.renderPager('findings', Number(this.state.findingTotal || findings.length), this.state.findingPage, pageSize)}</section>`;
    }

    renderBusinessReviewSummary(report) {
      const sources = report.source_revisions || report.sourceRevisions || {};
      const maturity = report.maturity_counts || report.maturityCounts || {};
      const layers = report.layer_counts || report.layerCounts || {};
      const domains = list(report.affected_domains || report.affectedDomains);
      const unbound = list(report.unbound_entries || report.unboundEntries);
      const stateCard = (label, value, falseLabel) => {
        const known = typeof value === 'boolean';
        const status = !known ? 'unverified' : value ? 'pass' : falseLabel;
        const text = !known ? '未返回' : value ? '通过' : falseLabel === 'unverified' ? '未验证' : '未通过';
        return `<article class="review-state"><b>${label}</b>${statusLabel(status)}<small>${text}</small></article>`;
      };
      return `<section class="review-summary" aria-label="业务评审证据绑定"><h3>证据绑定</h3><dl class="review-binding"><dt>Snapshot</dt><dd class="gid">${escapeHtml(report.snapshot_gid || report.snapshotGid || '未返回')}</dd><dt>Backend revision</dt><dd class="gid">${escapeHtml(sources.backend || '未返回')}</dd><dt>Source revision</dt><dd class="gid">${escapeHtml(sources.source || '未返回')}</dd><dt>Web revision</dt><dd class="gid">${escapeHtml(sources.web || '未返回')}</dd></dl><p class="review-counts"><b>Finding 证据行 ${escapeHtml(report.finding_count ?? '未返回')} 条</b> · <b>根因组 ${escapeHtml(report.root_cause_group_count ?? '未返回')} 个</b></p><p class="review-warning">Finding 证据行不等于独立修复任务；请按根因组和共享修复族处理。</p><div class="review-states">${stateCard('机器检查', report.machine_passed, 'fail')}${stateCard('超管批准', report.human_approved, 'fail')}${stateCard('运行验证', report.runtime_verified, 'unverified')}</div><p class="review-warning">机器检查通过不代表整项 Capability 已合规；超管批准与运行验证必须独立满足。</p><div class="review-facts"><article><h4>领域状态</h4><p>${domains.map(escapeHtml).join('、') || '未返回'}</p></article><article><h4>成熟度 L0–L6</h4><p>${Object.entries(maturity).map(([key, value]) => `${escapeHtml(key)}：${escapeHtml(value)}`).join(' · ') || '未返回'}</p></article><article><h4>七层 A–G</h4><p>${Object.entries(layers).map(([key, value]) => `${escapeHtml(key)}：${escapeHtml(value)}`).join(' · ') || '未返回'}</p></article><article><h4>Legacy backlog</h4><p>legacy_pending_review ${escapeHtml(report.legacy_pending_review_count ?? '未返回')}</p></article></div><details class="unbound-entries"><summary>公开但未绑定的入口（${escapeHtml(unbound.length)}）</summary>${unbound.map((item) => `<article><b>${escapeHtml(item.canonical_key || item.canonicalKey)}</b><p>${escapeHtml(item.entry_type || item.entryType)} · ${escapeHtml(item.domain)} · ${escapeHtml(item.location || item.source_path || item.sourcePath)}</p></article>`).join('') || '<p>当前投影未返回条目。</p>'}</details></section>`;
    }

    renderBusinessReviewQueue() {
      const queue = this.state.businessReviewQueue || [];
      const pageSize = Number(this.state.businessQueuePageLimit || 50);
      const total = Number(this.state.businessReviewReport && this.state.businessReviewReport.review_queue_count || queue.length);
      const pages = Math.max(1, Math.ceil(total / pageSize));
      const page = Math.min(pages, Math.max(1, Number(this.state.businessQueuePage || 1)));
      const items = queue.slice((page - 1) * pageSize, page * pageSize);
      const busy = this.state.sectionBusy.includes('changes');
      return `<section class="review-queue" aria-busy="${busy ? 'true' : 'false'}"><h3>风险排序评审队列</h3>${items.map((item) => `<article><b>${escapeHtml(item.capability_key || item.capabilityKey)}</b><p>优先级 ${escapeHtml(item.priority)} · ${escapeHtml(item.domain)} · ${escapeHtml(item.maturity)} · ${escapeHtml(item.reason)}</p></article>`).join('') || '<p class="empty">当前分析未返回评审队列。</p>'}<div class="pager" aria-label="业务评审队列分页"><button type="button" data-action="business-queue-prev"${busy || page <= 1 ? ' disabled' : ''}>上一页</button><span>第 ${page} 页 / 共 ${pages} 页 · 共 ${total} 项</span><button type="button" data-action="business-queue-next"${busy || page >= pages ? ' disabled' : ''}>下一页</button></div></section>`;
    }

    renderBusinessReviewDetail(proposal) {
      if (!proposal) return '';
      if (!businessIdentityMatches(proposal, this.state.businessReviewReport)) {
        return '<aside class="business-review-detail"><p class="notice" role="alert">评审主体身份与固定 Snapshot 不一致，详情与决定控件已关闭。</p></aside>';
      }
      const evidence = proposal.review_evidence || proposal.reviewEvidence || {};
      const capabilityId = proposal.capability_id || proposal.capabilityId || '未返回';
      const major = valueOf(proposal, 'major_version', 'majorVersion') || valueOf(evidence, 'major_version', 'majorVersion') || '未返回';
      const versionGid = valueOf(proposal, 'capability_version_gid', 'capabilityVersionGid') || '未返回';
      const definitionHash = valueOf(proposal, 'business_definition_hash', 'businessDefinitionHash') || evidence.definition_hash || '未返回';
      const acceptance = list(evidence.business_acceptance_criteria || evidence.acceptance_criteria);
      const accepted = list(evidence.accepted_examples);
      const rejected = list(evidence.rejected_examples);
      const rules = list(evidence.business_rules);
      const capabilityKey = evidence.capability_key || `${capabilityId}@${major}`;
      const report = this.state.businessReviewReport || {};
      const roots = list(report.root_causes).filter((item) => list(item.capability_keys).includes(capabilityKey));
      const analysisRelations = list(report.relations).filter((item) => list(item.capability_keys).includes(capabilityKey));
      const uniqueRelations = (values) => Array.from(new Map(values.map((item) => [item.candidate_hash || item.candidateHash, item])).values());
      const deterministic = uniqueRelations(list(evidence.deterministic_relation_candidates).concat(analysisRelations.filter((item) => item.source === 'deterministic')));
      const advisory = uniqueRelations(list(evidence.ai_advisory_relation_candidates).concat(analysisRelations.filter((item) => item.source === 'advisory')));
      const reviews = list(proposal.reviews);
      const reviewTotal = Number(proposal.review_total || reviews.length);
      const historyWarning = proposal.reviews_truncated
        ? `<p class="review-warning">评审历史共 ${escapeHtml(reviewTotal)} 条；当前仅显示最新 20 条中的 ${escapeHtml(reviews.length)} 条。</p>` : '';
      const ownerDomains = list(evidence.owner_domains).length ? list(evidence.owner_domains) : [proposal.domain].filter(Boolean);
      const stale = ['stale', 'expired'].includes(String(proposal.status));
      const pending = this.state.busyActionKeys.includes(`decide-business-review:${rowGid(proposal)}`);
      const draft = this.state.businessReviewDraft || { decision: 'approved', reason: '' };
      const items = (values, empty) => values.length ? `<ul>${values.map((item) => `<li>${escapeHtml(textValue(item))}</li>`).join('')}</ul>` : `<p>${empty}</p>`;
      const relationCards = (values) => values.map((item) => `<article><b>${escapeHtml(item.relation_type || item.relationType)} · ${escapeHtml(item.candidate_hash || item.candidateHash)}</b><p>${list(item.capability_keys || item.capabilityKeys).map(escapeHtml).join(' ↔ ')}</p><pre>${escapeHtml(textValue(item.evidence || {}))}</pre></article>`).join('') || '<p>无候选。</p>';
      const decisionForm = this.isSuperAdmin() ? `<fieldset class="review-decision"${stale || pending ? ' disabled' : ''}><legend>超管批准（仅绑定当前 hash 与 row version）</legend><label>决定 <select data-business-decision><option value="approved"${draft.decision === 'approved' ? ' selected' : ''}>approved</option><option value="rejected"${draft.decision === 'rejected' ? ' selected' : ''}>rejected</option><option value="changes_requested"${draft.decision === 'changes_requested' ? ' selected' : ''}>changes_requested</option></select></label><label>理由 <textarea data-business-decision-reason required>${escapeHtml(draft.reason || '')}</textarea></label><button type="button" data-action="decide-business-review" data-entity-gid="${escapeHtml(rowGid(proposal))}"${pending ? ' aria-busy="true"' : ''}>${pending ? '提交中…' : '提交评审决定'}</button></fieldset>` : '<p class="review-warning">只有可信身份中的 super_admin 可以提交评审决定。</p>';
      return `<aside class="business-review-detail" data-testid="business-review-detail" aria-label="Capability 业务评审详情"><button type="button" class="detail-close" data-action="close-business-review-detail">关闭</button><h3>${escapeHtml(capabilityId)}@${escapeHtml(major)}</h3><p>Version GID ${escapeHtml(versionGid)} · Proposal ${escapeHtml(rowGid(proposal))} · Row version ${escapeHtml(proposal.row_version || proposal.rowVersion || '未返回')}</p><p class="gid">${escapeHtml(definitionHash)}</p>${stale ? '<p class="notice">当前提案已过期；服务端 CAS 会拒绝旧 hash/row version，不能批准。</p>' : ''}<section><h4>业务目的与效果</h4><p>${escapeHtml(evidence.business_effect || '未返回')}</p><h5>验收条件</h5>${items(acceptance, '未返回验收条件。')}<h5>接受示例</h5>${items(accepted, '未返回接受示例。')}<h5>拒绝示例</h5>${items(rejected, '未返回拒绝示例。')}</section><section><h4>不变量与规则</h4>${rules.map((rule) => `<article class="business-rule"><b>${escapeHtml(rule.rule_id)}</b><p>${escapeHtml(rule.statement)} · 适用：${escapeHtml(rule.applies_when)}</p><p>执行：${escapeHtml(rule.enforcement_ref)} · 错误码：${escapeHtml(rule.error_code)}</p><p>测试：${list(rule.test_refs).map(escapeHtml).join('、') || '未返回'}</p></article>`).join('') || `<p>${escapeHtml(evidence.no_business_invariant_reason || '未返回业务规则或无规则理由。')}</p>`}<h5>该版本根因组</h5>${roots.map((item) => `<article><b>${escapeHtml(item.root_cause_key)}</b><p>${escapeHtml(item.finding_count)} 条 Finding · ${escapeHtml(item.remediation_family)} · ${escapeHtml(item.severity)}</p></article>`).join('') || '<p>未返回该版本的根因组。</p>'}</section><section><h4>成熟度</h4><pre>${escapeHtml(textValue(evidence.business_maturity || {}))}</pre></section><section><h4>机器证据（只读 / 已脱敏投影）</h4><pre>${escapeHtml(textValue(evidence.evidence || evidence.redacted_evidence || {}))}</pre></section><section><h4>Owner domains</h4><p>${ownerDomains.map(escapeHtml).join('、') || '未返回'}</p></section><section><h4>确定性关系候选</h4>${relationCards(deterministic)}<p class="review-warning">关系提示只辅助人工判断，绝不会自动批准。</p><h4>AI 辅助建议（不参与自动批准）</h4>${relationCards(advisory)}</section><section><h4>既往追加式评审</h4>${historyWarning}${reviews.map((review) => `<article><b>${escapeHtml(review.decision)} · ${escapeHtml(review.review_gid)}</b><p>${escapeHtml(review.reviewer_gid)}：${escapeHtml(review.decision_reason)}</p></article>`).join('') || '<p>尚无既往评审。</p>'}</section>${decisionForm}</aside>`;
    }

    renderChanges() {
      const canReview = actionsFor(this.state.permissions).includes('decide-review');
      const filters = this.state.sectionFilters.changes || {};
      const proposals = (this.state.proposals || []).filter((proposal) => !filters.query || `${proposal.capability_id || proposal.capabilityId || ''} ${proposal.status || ''}`.toLowerCase().includes(filters.query.toLowerCase()));
      const availability = this.state.sectionMeta.changes;
      const metaNotice = availability && availability.available === false ? `<p class="notice">workflow 数据源未接入：${escapeHtml(availability.reason || 'governance_dependency_unavailable')}。当前仅显示已缓存提案。</p>` : '';
      const changesBusy = this.state.sectionBusy.includes('changes');
      const detailLoadBusy = this.state.busyActionKeys.some((key) => key.startsWith('load-business-review-detail:'));
      const proposalCards = proposals.map((proposal) => { const stale = ['stale', 'expired'].includes(String(proposal.status)); const gid = rowGid(proposal); const detailBusy = this.state.busyActionKeys.includes(`load-business-review-detail:${gid}`); const business = proposal.review_type === 'business_definition' || proposal.business_definition_hash || proposal.review_evidence; return `<article class="proposal"><h3>${escapeHtml(proposal.capability_id || proposal.capabilityId || proposal.title || gid)}</h3><p class="gid">Proposal ${escapeHtml(gid)}</p>${statusLabel(proposal.status)}<p>Snapshot：${escapeHtml(normalizeGid(proposal.base_snapshot_gid || proposal.snapshotGid || proposal.snapshot_gid) || this.state.selectedSnapshotGid || '—')}</p><p>版本：${escapeHtml(proposal.capability_version_gid || '—')} · Row version：${escapeHtml(proposal.row_version || proposal.rowVersion || '—')}</p>${stale ? '<p class="notice">哈希或证据已过期，需重新生成提案。</p>' : ''}${business ? `<button type="button" data-action="load-business-review-detail" data-entity-gid="${escapeHtml(gid)}"${changesBusy || detailBusy ? ` disabled${detailBusy ? ' aria-busy="true"' : ''}` : ''}>${detailBusy ? '加载中…' : '查看评审证据'}</button>` : canReview ? `<button type="button" data-action="decide-review" data-entity-gid="${escapeHtml(gid)}"${stale || changesBusy ? ' disabled title="当前不可审批"' : ''}>决定评审</button>` : ''}</article>`; }).join('') || '<p class="empty">没有待评审变更。</p>';
      const report = this.state.businessReviewReport;
      if (!report) return `<section><h2>变更与评审</h2>${metaNotice}<p class="review-warning">运行业务分析后，此处将显示绑定快照和源码修订的评审队列；当前仅显示提案投影。</p><div class="filters"><label>搜索 <input data-filter-section="changes" data-filter-key="query" value="${escapeHtml(filters.query || '')}" placeholder="能力或提案 GID"></label><button type="button" data-action="clear-section-filter" data-section="changes">清除筛选</button></div>${proposalCards}${this.state.selectedBusinessReview ? this.renderBusinessReviewDetail(this.state.selectedBusinessReview) : ''}</section>`;
      const proposalPage = (this.state.businessProposalCursorHistory || []).length + 1;
      return `<section><h2>业务治理评审工作台</h2>${metaNotice}${this.renderBusinessReviewSummary(report)}${this.renderBusinessReviewQueue()}<section class="review-proposals" aria-busy="${changesBusy || detailLoadBusy ? 'true' : 'false'}"><h3>可决定的业务定义提案</h3>${detailLoadBusy ? '<p role="status">正在加载评审详情…</p>' : ''}${proposalCards}<div class="pager" aria-label="业务定义提案分页"><button type="button" data-action="business-proposals-prev"${changesBusy || detailLoadBusy || proposalPage <= 1 ? ' disabled' : ''}>上一页</button><span>第 ${proposalPage} 页（稳定游标）</span><button type="button" data-action="business-proposals-next"${changesBusy || detailLoadBusy || !this.state.businessProposalNextCursor ? ' disabled' : ''}>下一页</button></div></section>${this.state.selectedBusinessReview ? this.renderBusinessReviewDetail(this.state.selectedBusinessReview) : ''}</section>`;
    }

    renderHealth() {
      const byDomain = new Map((this.state.health || []).map((item) => [item.domain, item]));
      const meta = this.state.sectionMeta.health;
      const metaNotice = meta && meta.available === false ? '<p class="notice">快照数据源不可用，以下状态为未验证。</p>' : '';
      return `<section><h2>测试与健康</h2><p>✓ 通过 · ◷ 需关注 · ! 阻塞 · • 未验证。结论来自后端固定快照；Finding 数是该领域的汇总，可点击进入明细。</p>${metaNotice}<div class="health-grid">${DOMAINS.map((domain) => { const item = byDomain.get(domain.id) || {}; const hasFindings = item.finding_count !== undefined; return `<article class="health-card" data-health-domain="${escapeHtml(domain.id)}"><b>${escapeHtml(domain.label)}</b><div class="health-card-status">${statusLabel(item.status)}</div><small class="health-card-count">${escapeHtml(item.finding_count === undefined ? '等待检查' : `${item.entry_count || 0} 项能力 · ${item.finding_count || 0} 条 Finding`)}</small>${hasFindings ? `<button type="button" class="health-card-link" data-health-domain="${escapeHtml(domain.id)}">查看该领域 Finding</button>` : ''}${item.reason ? `<small class="health-card-reason">原因：${escapeHtml(item.reason)}</small>` : ''}</article>`; }).join('')}</div>${this.state.sectionStale.health ? '<p class="notice">健康查询失败，正在显示上次成功数据。</p>' : ''}</section>`;
    }

    renderRelease() {
      const release = this.state.releaseGate || {};
      const canRelease = actionsFor(this.state.permissions).includes('evaluate-release');
      const busy = this.state.busyActionKeys.includes(`evaluate-release:${this.state.selectedSnapshotGid || 'global'}`);
      const blockers = release.blockers || [];
      return `<section><h2>发布闸门</h2><p>结论只来自服务端固定证据：代码修订、Catalog、Snapshot、测试、Finding、审批和签名。</p><div class="metric"><h3>当前结论</h3>${statusLabel(release.conclusion || release.status || 'unverified')}<p>Report：<span class="gid">${escapeHtml(release.report_gid || release.reportGid || '—')}</span></p>${blockers.length ? `<p>阻塞：${blockers.map(escapeHtml).join('、')}</p>` : '<p>未返回可通过证据。</p>'}</div>${canRelease && this.state.selectedSnapshotGid ? `<button type="button" data-action="evaluate-release" data-entity-gid="${escapeHtml(this.state.selectedSnapshotGid)}"${busy ? ' disabled aria-busy="true"' : ''}>${busy ? '评估中…' : '执行发布闸门评估'}</button>` : ''}</section>`;
    }

    renderAudit() {
      const filters = this.state.sectionFilters.audit || {};
      const meta = this.state.sectionMeta.audit;
      const metaNotice = meta && meta.available === false ? '<p class="notice">审计数据源不可用；未显示未经确认的空结果。</p>' : '';
      return `<section><h2>审计</h2><p>只读、脱敏、不可编辑或删除。每条记录带操作者、能力、请求和结果。</p>${metaNotice}<div class="filters"><label>操作者 <input data-filter-section="audit" data-filter-key="actor" value="${escapeHtml(filters.actor || '')}"></label><label>能力 <input data-filter-section="audit" data-filter-key="capability" value="${escapeHtml(filters.capability || '')}"></label><label>结果 <select data-filter-section="audit" data-filter-key="result"><option value="">全部结果</option><option value="succeeded"${filters.result === 'succeeded' ? ' selected' : ''}>succeeded</option><option value="failed"${filters.result === 'failed' ? ' selected' : ''}>failed</option></select></label><button type="button" data-action="clear-section-filter" data-section="audit">清除筛选</button></div><div class="audit-list">${(this.state.auditEvents || []).map((event) => `<article class="finding"><h3>${escapeHtml(event.operation || event.event_type || 'audit')} ${statusLabel(event.status)}</h3><p>操作者：${escapeHtml(event.actor_gid || event.user_gid || '—')} · 请求：${escapeHtml(event.request_gid || event.request_id || '—')}</p><p>能力：${escapeHtml(event.capability_id || '—')} · 时间：${escapeHtml(event.occurred_at || event.created_at || '—')}</p></article>`).join('') || '<p class="empty">没有符合条件的审计记录。</p>'}</div></section>`;
    }

    render() {
      const views = { overview: this.renderOverview(), inventory: this.renderInventory(), findings: this.renderFindings(), changes: this.renderChanges(), health: this.renderHealth(), release: this.renderRelease(), audit: this.renderAudit() };
      const canScan = actionsFor(this.state.permissions).includes('run-scan');
      const scanBusy = this.state.busyActionKeys.includes('run-scan:global');
      const scanLabel = scanBusy ? '扫描中…' : (this.state.selectedSnapshotGid ? '重新扫描' : '首次扫描');
      const sectionError = this.state.sectionErrors && this.state.sectionErrors[this.state.section];
      const detailBusy = this.state.section === 'changes' && this.state.busyActionKeys.some((key) => key.startsWith('load-business-review-detail:'));
      const sectionBusy = this.state.sectionBusy.includes(this.state.section) || detailBusy;
      this.root.innerHTML = `<div class="governance-shell"><header><div><p class="eyebrow">CAPABILITY GOVERNANCE CENTER</p><h1>能力治理中心</h1></div><div class="header-actions">${canScan ? `<button class="scan" type="button" data-action="run-scan"${scanBusy ? ' disabled aria-busy="true"' : ''}>${scanLabel}</button>` : ''}<button class="refresh" type="button" data-action="refresh"${sectionBusy ? ' disabled' : ''}>刷新</button></div></header><nav aria-label="治理中心导航">${this.renderNav()}</nav>${this.state.lastError ? `<p class="notice" role="alert" tabindex="-1" data-testid="governance-error">◷ ${escapeHtml(this.state.lastError)}；正在显示上次成功数据。</p>` : ''}${sectionError && sectionError !== this.state.lastError ? `<p class="notice" role="status">◷ ${escapeHtml(sectionError)}；正在显示上次成功数据。</p>` : ''}<main aria-busy="${sectionBusy ? 'true' : 'false'}">${views[this.state.section]}</main></div>`;
    }
  }

  return { CapabilityGovernanceController };
});
