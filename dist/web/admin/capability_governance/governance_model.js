'use strict';

(function(root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.CapabilityGovernanceModel = api;
})(typeof window !== 'undefined' ? window : globalThis, function() {
  const DOMAINS = Object.freeze([
    { id: 'base', label: 'Base Platform' },
    { id: 'agent', label: 'Agent' },
    { id: 'craft', label: 'Craft' },
    { id: 'digital_model', label: 'Digital Model' },
    { id: 'factory', label: 'Factory' },
    { id: 'integration', label: 'Integration' },
    { id: 'project_management', label: 'Project Management' },
    { id: 'simulation', label: 'Simulation' },
    { id: 'ontology', label: 'Ontology' },
    { id: 'knowledge', label: 'Knowledge' },
    { id: 'device', label: 'Device' },
  ]);

  const SECTIONS = Object.freeze(['overview', 'inventory', 'findings', 'changes', 'health', 'release', 'audit']);

  function normalizeGid(value) {
    if (value === null || value === undefined || value === '') return null;
    return String(value);
  }

  function actionsFor(permissions) {
    const granted = new Set(permissions || []);
    if (!granted.has('system.capability.read')) return [];
    const actions = ['view', 'export'];
    if (granted.has('system.capability.analyze')) actions.push('run-analysis', 'generate-repair-prompt');
    if (granted.has('system.capability.govern')) actions.push('run-scan', 'create-proposal', 'grant-waiver', 'revoke-waiver');
    if (granted.has('system.capability.release')) actions.push('decide-review', 'evaluate-release');
    return actions;
  }

  function filterRows(rows, filters) {
    const domain = filters && filters.domain ? String(filters.domain) : 'all';
    const query = (filters && filters.query ? String(filters.query) : '').trim().toLocaleLowerCase();
    return (rows || []).filter((row) => {
      if (domain !== 'all' && row.domain !== domain) return false;
      if (!query) return true;
      return [row.gid, row.capabilityId, row.businessEffect, row.domain, row.semanticClass, row.lifecycle]
        .filter(Boolean).join(' ').toLocaleLowerCase().includes(query);
    });
  }

  function mergeLoadFailure(previousRows, error) {
    return { rows: previousRows || [], staleData: true, lastError: error && error.message ? error.message : String(error || 'load failed') };
  }

  function createState(overrides) {
    return Object.assign({
      selectedSnapshotGid: null,
      dashboardLoaded: false,
      productCatalogRelease: null,
      governanceExtensionRelease: null,
      productCapabilityCount: null,
      governanceExtensionCapabilityCount: null,
      catalogPageLimit: 100,
      findingPageLimit: 200,
      filters: { domain: 'all', query: '' },
      rows: [],
      findings: [],
      proposals: [],
      health: [],
      auditEvents: [],
      releaseGate: null,
      sectionBusy: [],
      sectionErrors: {},
      sectionStale: {},
      sectionMeta: {},
      sectionFilters: {
        findings: { domain: 'all', severity: 'all', status: 'all', reasonCode: 'all', query: '' },
        changes: { domain: 'all', stage: 'all', query: '' },
        audit: { actor: '', capability: '', eventType: '', result: '' },
      },
      selectedEntity: null,
      staleData: false,
      busyActionKeys: [],
      lastError: null,
      permissions: [],
      section: 'overview',
    }, overrides || {});
  }

  return { DOMAINS, SECTIONS, normalizeGid, actionsFor, filterRows, mergeLoadFailure, createState };
});
