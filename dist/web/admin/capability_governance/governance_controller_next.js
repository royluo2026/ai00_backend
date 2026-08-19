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
  const statusLabel = (status) => {
    const normalized = String(status || 'unverified').toLowerCase();
    const icon = ['pass', 'healthy', 'active'].includes(normalized) ? '✓'
      : ['fail', 'blocked', 'broken'].includes(normalized) ? '!' : ['stale', 'expired', 'attention'].includes(normalized) ? '◷' : '•';
    return `<span class="status status-${escapeHtml(normalized)}"><span aria-hidden="true">${icon}</span> ${escapeHtml(normalized)}</span>`;
  };
  const unwrap = (response) => response && response.data && typeof response.data === 'object' ? response.data : (response || {});

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
      this.scanAttempt = 0;
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
      if (target.matches('[data-testid="governance-search"]')) {
        this.state.filters = Object.assign({}, this.state.filters, { query: target.value });
        this.render();
        return;
      }
      const section = target.dataset && target.dataset.filterSection;
      const key = target.dataset && target.dataset.filterKey;
      if (section && key) {
        const previous = this.state.sectionFilters[section] || {};
        this.state.sectionFilters[section] = Object.assign({}, previous, { [key]: target.value });
        this.render();
      }
    }

    onClick(event) {
      const section = event.target.closest('[data-section]');
      if (section) return this.setSection(section.dataset.section);
      const domain = event.target.closest('[data-domain]');
      if (domain) {
        const selected = domain.dataset.domain || 'all';
        const current = this.state.filters.domain || 'all';
        this.state.filters = Object.assign({}, this.state.filters, { domain: selected !== 'all' && selected === current ? 'all' : selected });
        return this.setSection('inventory');
      }
      const row = event.target.closest('[data-row-gid]');
      if (row) return this.selectEntity(row.dataset.rowGid);
      const action = event.target.closest('[data-action]');
      if (action && !action.disabled) {
        if (action.dataset.action === 'refresh') return this.refresh();
        if (action.dataset.action === 'clear-domain-filter') {
          this.state.filters = Object.assign({}, this.state.filters, { domain: 'all' });
          return this.setSection('inventory');
        }
        if (action.dataset.action === 'clear-section-filter') {
          const sectionName = action.dataset.section || this.state.section;
          this.state.sectionFilters[sectionName] = Object.assign({}, this.state.sectionFilters[sectionName], { domain: 'all', severity: 'all', status: 'all', stage: 'all', query: '', actor: '', capability: '', eventType: '', result: '' });
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

    async refresh({ supersede = false } = {}) {
      const key = 'refresh:global';
      if (!this.api || typeof this.api.loadDashboard !== 'function' || (!supersede && this.state.busyActionKeys.includes(key))) return false;
      const generation = ++this.refreshGeneration;
      if (!this.state.busyActionKeys.includes(key)) this.state.busyActionKeys = this.state.busyActionKeys.concat(key);
      this.render();
      try {
        const response = await this.api.loadDashboard(Object.assign({}, this.state.filters, { limit: 100 }));
        if (generation !== this.refreshGeneration) return false;
        const data = unwrap(response);
        const snapshot = valueOf(data, 'snapshot_gid', 'snapshotGid');
        const productRelease = valueOf(data, 'product_catalog_release', 'productCatalogRelease');
        const extensionRelease = valueOf(data, 'governance_extension_release', 'governanceExtensionRelease');
        if (snapshot !== null) this.state.selectedSnapshotGid = normalizeGid(snapshot);
        if (productRelease !== null) this.state.productCatalogRelease = productRelease;
        if (extensionRelease !== null) this.state.governanceExtensionRelease = extensionRelease;
        this.state.productCapabilityCount = valueOf(data, 'product_capability_count', 'productCapabilityCount') || 0;
        this.state.governanceExtensionCapabilityCount = valueOf(data, 'governance_extension_capability_count', 'governanceExtensionCapabilityCount') || 0;
        this.state.rows = valueOf(data, 'rows', 'items') || [];
        this.state.findings = valueOf(data, 'findings') || this.state.findings || [];
        this.state.proposals = valueOf(data, 'proposals') || this.state.proposals || [];
        this.state.staleData = false;
        this.state.lastError = null;
        return true;
      } catch (error) {
        if (generation !== this.refreshGeneration) return false;
        Object.assign(this.state, mergeLoadFailure(this.state.rows, error));
        return false;
      } finally {
        if (generation === this.refreshGeneration) this.state.busyActionKeys = this.state.busyActionKeys.filter((item) => item !== key);
        this.render();
      }
    }

    async loadSection(section) {
      if (!this.api || !['findings', 'changes', 'health', 'audit'].includes(section)) return false;
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
        else if (section === 'findings') response = await this.api.searchFindings({ query: filters.query || this.state.filters.query, targetGid: this.state.selectedSnapshotGid });
        else if (section === 'changes') response = await this.api.loadProposals(filters);
        else response = await this.api.loadAudit(filters);
        if (generation !== this.sectionGenerations[section]) return false;
        const data = unwrap(response);
        if (section === 'findings') this.state.findings = valueOf(data, 'findings', 'items') || [];
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

    async runAction(action, entity, executor) {
      const entityGid = normalizeGid(rowGid(entity) || (typeof entity === 'object' ? null : entity));
      const key = `${action}:${entityGid || 'global'}`;
      if (this.state.busyActionKeys.includes(key)) return false;
      this.state.busyActionKeys = this.state.busyActionKeys.concat(key);
      this.render();
      try { return await executor(); }
      catch (error) { this.state.lastError = error && error.message ? error.message : String(error); return false; }
      finally { this.state.busyActionKeys = this.state.busyActionKeys.filter((item) => item !== key); this.render(); }
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
      const payload = action === 'run-scan' ? { codeRevision: 'test-governance-ui' } : (['revoke-waiver', 'decide-review'].includes(action) ? { targetGid, rowVersion } : { targetGid });
      return this.runAction(action, entity, async () => {
        const result = await this.api[method](payload, options);
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
      return `<section class="overview-grid"><article class="metric"><h2>Product Catalog</h2><strong>${escapeHtml(this.state.productCapabilityCount)}</strong><p>${escapeHtml(this.state.productCatalogRelease || '未加载')}</p></article><article class="metric extension"><h2>Governance Extension</h2><strong>${escapeHtml(this.state.governanceExtensionCapabilityCount)}</strong><p>${escapeHtml(this.state.governanceExtensionRelease || '未加载')}</p></article><article class="metric"><h2>Open Findings</h2><strong>${escapeHtml((this.state.findings || []).length)}</strong><p>${attention ? `${attention} 个领域需关注` : '跨域、可追溯'}</p></article><article class="metric"><h2>Snapshot</h2><strong class="gid">${escapeHtml(this.state.selectedSnapshotGid || '—')}</strong><p>${this.state.staleData ? '◷ 保留旧数据，刷新失败' : '✓ 当前数据'}</p></article></section><section class="domain-summary"><h2>11 个真实领域</h2>${DOMAINS.map((domain) => { const item = health.find((candidate) => candidate.domain === domain.id); return `<button type="button" data-domain="${domain.id}">${escapeHtml(domain.label)} ${item ? statusLabel(item.status) : ''}</button>`; }).join('')}</section>`;
    }

    renderInventory() {
      const rows = filterRows(this.state.rows, this.state.filters);
      const domain = this.state.filters.domain || 'all';
      return `<section><div class="filters"><label>搜索 <input data-testid="governance-search" value="${escapeHtml(this.state.filters.query)}" placeholder="能力 ID、GID、业务效果"></label><div class="domain-filter"><button type="button" data-domain="all">全部领域</button>${DOMAINS.map((item) => `<button type="button" data-domain="${item.id}">${escapeHtml(item.label)}</button>`).join('')}<button type="button" data-action="clear-domain-filter"${domain === 'all' ? ' disabled' : ''}>清除领域筛选</button></div></div><div class="inventory-table" role="table"><div class="inventory-head" role="row"><span>GID / Capability</span><span>业务效果</span><span>领域</span><span>状态</span></div>${rows.map((row) => `<button type="button" class="inventory-row" data-row-gid="${escapeHtml(rowGid(row))}" role="row"><span class="gid">${escapeHtml(rowGid(row))}<br><b>${escapeHtml(row.capabilityId || row.capability_id)}</b></span><span>${escapeHtml(row.businessEffect || row.business_effect)}</span><span>${escapeHtml(row.domain)}</span>${statusLabel(row.health || row.lifecycle)}</button>`).join('') || '<p class="empty">没有符合筛选条件的能力。</p>'}</div>${this.renderDrawer()}</section>`;
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
      const findings = (this.state.findings || []).filter((finding) => {
        const domains = finding.domains || finding.domain || [];
        const severity = String(finding.severity || 'warning');
        const status = String(finding.status || 'open');
        const text = `${finding.code || finding.findingType || ''} ${finding.fingerprint || ''}`.toLowerCase();
        return (filters.domain === 'all' || (Array.isArray(domains) ? domains.includes(filters.domain) : domains === filters.domain)) && (filters.severity === 'all' || filters.severity === severity) && (filters.status === 'all' || filters.status === status) && (!filters.query || text.includes(filters.query.toLowerCase()));
      });
      return `<section><h2>Finding 中心</h2><div class="filters"><label>搜索 <input data-filter-section="findings" data-filter-key="query" value="${escapeHtml(filters.query || '')}" placeholder="规则、指纹"></label><label>领域 <select data-filter-section="findings" data-filter-key="domain"><option value="all">全部领域</option>${DOMAINS.map((domain) => `<option value="${domain.id}"${filters.domain === domain.id ? ' selected' : ''}>${escapeHtml(domain.label)}</option>`).join('')}</select></label><label>级别 <select data-filter-section="findings" data-filter-key="severity"><option value="all">全部级别</option><option value="error"${filters.severity === 'error' ? ' selected' : ''}>error</option><option value="warning"${filters.severity === 'warning' ? ' selected' : ''}>warning</option></select></label><button type="button" data-action="clear-section-filter" data-section="findings">清除筛选</button></div>${findings.map((finding) => `<article class="finding"><h3>${escapeHtml(finding.code || finding.findingType || 'finding')} ${statusLabel(finding.status)}</h3><p>主体：${(finding.subjectVersionGids || finding.subject_version_gids || []).map(normalizeGid).map(escapeHtml).join('、') || '—'}</p><p>领域：${(finding.domains || []).map(escapeHtml).join('、') || '跨领域'}</p><p>严重级别：${escapeHtml(finding.severity || 'warning')}</p><p>证据：${(finding.evidence || []).map(escapeHtml).join('、') || '—'}</p></article>`).join('') || '<p class="empty">没有符合条件的 Finding。</p>'}</section>`;
    }

    renderChanges() {
      const canReview = actionsFor(this.state.permissions).includes('decide-review');
      const filters = this.state.sectionFilters.changes || {};
      const proposals = (this.state.proposals || []).filter((proposal) => !filters.query || `${proposal.capability_id || proposal.capabilityId || ''} ${proposal.status || ''}`.toLowerCase().includes(filters.query.toLowerCase()));
      return `<section><h2>变更与评审</h2><div class="filters"><label>搜索 <input data-filter-section="changes" data-filter-key="query" value="${escapeHtml(filters.query || '')}" placeholder="能力或提案 GID"></label><button type="button" data-action="clear-section-filter" data-section="changes">清除筛选</button></div>${proposals.map((proposal) => { const stale = ['stale', 'expired'].includes(String(proposal.status)); const gid = rowGid(proposal); return `<article class="proposal"><h3>${escapeHtml(proposal.capability_id || proposal.capabilityId || proposal.title || gid)}</h3><p class="gid">Proposal ${escapeHtml(gid)}</p>${statusLabel(proposal.status)}<p>Snapshot：${escapeHtml(normalizeGid(proposal.base_snapshot_gid || proposal.snapshotGid || proposal.snapshot_gid) || this.state.selectedSnapshotGid || '—')}</p><p>版本：${escapeHtml(proposal.capability_version_gid || '—')} · Row version：${escapeHtml(proposal.row_version || proposal.rowVersion || '—')}</p>${stale ? '<p class="notice">哈希或证据已过期，需重新生成提案。</p>' : ''}${canReview ? `<button type="button" data-action="decide-review" data-entity-gid="${escapeHtml(gid)}"${stale ? ' disabled title="哈希已变更，不能审批"' : ''}>决定评审</button>` : ''}</article>`; }).join('') || '<p class="empty">没有待评审变更；若数据源未接入，会在上方显示依赖状态。</p>'}</section>`;
    }

    renderHealth() {
      const byDomain = new Map((this.state.health || []).map((item) => [item.domain, item]));
      return `<section><h2>测试与健康</h2><p>✓ 通过 · ◷ 需关注 · ! 阻塞 · • 未验证。结论来自后端固定快照。</p><div class="health-grid">${DOMAINS.map((domain) => { const item = byDomain.get(domain.id) || {}; return `<article><b>${escapeHtml(domain.label)}</b><div>${statusLabel(item.status)}<small>${escapeHtml(item.finding_count === undefined ? '等待检查' : `${item.entry_count || 0} 能力 · ${item.finding_count || 0} Finding`)}</small></div></article>`; }).join('')}</div>${this.state.sectionStale.health ? '<p class="notice">健康查询失败，正在显示上次成功数据。</p>' : ''}</section>`;
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
      return `<section><h2>审计</h2><p>只读、脱敏、不可编辑或删除。每条记录带操作者、能力、请求和结果。</p><div class="filters"><label>操作者 <input data-filter-section="audit" data-filter-key="actor" value="${escapeHtml(filters.actor || '')}"></label><label>能力 <input data-filter-section="audit" data-filter-key="capability" value="${escapeHtml(filters.capability || '')}"></label><label>结果 <select data-filter-section="audit" data-filter-key="result"><option value="">全部结果</option><option value="succeeded"${filters.result === 'succeeded' ? ' selected' : ''}>succeeded</option><option value="failed"${filters.result === 'failed' ? ' selected' : ''}>failed</option></select></label><button type="button" data-action="clear-section-filter" data-section="audit">清除筛选</button></div><div class="audit-list">${(this.state.auditEvents || []).map((event) => `<article class="finding"><h3>${escapeHtml(event.operation || event.event_type || 'audit')} ${statusLabel(event.status)}</h3><p>操作者：${escapeHtml(event.actor_gid || event.user_gid || '—')} · 请求：${escapeHtml(event.request_gid || event.request_id || '—')}</p><p>能力：${escapeHtml(event.capability_id || '—')} · 时间：${escapeHtml(event.occurred_at || event.created_at || '—')}</p></article>`).join('') || '<p class="empty">没有符合条件的审计记录。</p>'}</div></section>`;
    }

    render() {
      const views = { overview: this.renderOverview(), inventory: this.renderInventory(), findings: this.renderFindings(), changes: this.renderChanges(), health: this.renderHealth(), release: this.renderRelease(), audit: this.renderAudit() };
      const canScan = actionsFor(this.state.permissions).includes('run-scan');
      const scanBusy = this.state.busyActionKeys.includes('run-scan:global');
      const scanLabel = scanBusy ? '扫描中…' : (this.state.selectedSnapshotGid ? '重新扫描' : '首次扫描');
      const sectionError = this.state.sectionErrors && this.state.sectionErrors[this.state.section];
      this.root.innerHTML = `<div class="governance-shell"><header><div><p class="eyebrow">TEST-ONLY GOVERNANCE CENTER</p><h1>能力治理中心</h1></div><div class="header-actions">${canScan ? `<button class="scan" type="button" data-action="run-scan"${scanBusy ? ' disabled aria-busy="true"' : ''}>${scanLabel}</button>` : ''}<button class="refresh" type="button" data-action="refresh">刷新</button></div></header><nav aria-label="治理中心导航">${this.renderNav()}</nav>${this.state.lastError ? `<p class="notice" role="status">◷ ${escapeHtml(this.state.lastError)}；正在显示上次成功数据。</p>` : ''}${sectionError ? `<p class="notice" role="status">◷ ${escapeHtml(sectionError)}；正在显示上次成功数据。</p>` : ''}<main>${views[this.state.section]}</main></div>`;
    }
  }

  return { CapabilityGovernanceController };
});
