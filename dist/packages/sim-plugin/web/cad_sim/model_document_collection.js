(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.AI00ModelDocumentCollection = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const MEDIA = new Set(['application/plmxml+xml', 'model/vnd.jt', 'application/vnd.siemens.teamcenter.visualization-document']);
  const RUNTIME = new Set(['idle', 'staging', 'opening', 'inserting', 'reading_back', 'read_back', 'verified', 'failed', 'outcome_unknown']);
  const ENVIRONMENT = new Set(['draft', 'materializing', 'runtime_verified', 'runtime_drifted', 'unmaterializable', 'outcome_unknown']);
  const gid = (value, field) => {
    const text = String(value || '');
    if (!/^[1-9][0-9]*$/.test(text)) throw new Error(`${field}_invalid`);
    return text;
  };
  const normalizeDocument = value => {
    const document = { ...value, document_gid: gid(value.document_gid, 'document_gid') };
    if (!['primary', 'inserted'].includes(document.role)) throw new Error('model_document_role_invalid');
    if (!MEDIA.has(document.media_type)) throw new Error('model_document_media_type_invalid');
    document.portability = document.portability || 'portable';
    document.sync_state = document.sync_state || 'draft';
    return document;
  };

  function collectVisibilityLeaves(node) {
    const children = Array.from(node?.children || []);
    if (children.length) return children.flatMap(collectVisibilityLeaves);
    return node?.controllable === false || !String(node?.key || '') ? [] : [node];
  }

  function deriveVisibilityState(node) {
    const leaves = collectVisibilityLeaves(node);
    if (!leaves.length) return { checked: false, indeterminate: false, disabled: true, controllableCount: 0 };
    const unknown = leaves.some(item => typeof item.visible !== 'boolean');
    const visible = leaves.filter(item => item.visible === true).length;
    return {
      checked: !unknown && visible === leaves.length,
      indeterminate: !unknown && visible > 0 && visible < leaves.length,
      disabled: unknown,
      controllableCount: leaves.length,
    };
  }

  function buildHierarchyForest(value) {
    const nodes = Array.from(value?.nodes || [], item => ({
      ...item, kind: 'node', key: `node:${gid(item.node_gid, 'node_gid')}`, children: [],
    }));
    const placements = Array.from(value?.placements || [], item => ({
      ...item, kind: 'placement', key: `placement:${gid(item.placement_gid, 'placement_gid')}`, children: [],
    }));
    const nodeByGid = new Map(nodes.map(item => [String(item.node_gid), item]));
    const placementByGid = new Map(placements.map(item => [String(item.placement_gid), item]));
    const roots = [];
    nodes.forEach(item => {
      const parent = item.parent_gid == null ? null : nodeByGid.get(String(item.parent_gid));
      if (item.parent_gid != null && !parent) throw new Error('hierarchy_parent_missing');
      (parent?.children || roots).push(item);
    });
    placements.forEach(item => {
      const parentPlacement = item.parent_placement_gid == null ? null : placementByGid.get(String(item.parent_placement_gid));
      const target = nodeByGid.get(String(item.target_node_gid || ''));
      if (item.parent_placement_gid != null && !parentPlacement) throw new Error('placement_parent_missing');
      const parent = parentPlacement || target;
      (parent?.children || roots).push(item);
    });
    const sortTree = items => items.sort((left, right) =>
      Number(left.sort_order || 0) - Number(right.sort_order || 0)
      || left.key.localeCompare(right.key, 'en', { numeric: true }))
      .forEach(item => sortTree(item.children));
    sortTree(roots);
    return roots;
  }

  function buildProductForest(values) {
    const nodes = Array.from(values || [], item => ({ ...item, node_key: String(item.node_key || ''), children: [] }));
    const byKey = new Map(nodes.map(item => [item.node_key, item]));
    const roots = [];
    nodes.forEach(item => {
      const parent = item.parent_key == null ? null : byKey.get(String(item.parent_key));
      if (item.parent_key != null && !parent) throw new Error('product_parent_missing');
      (parent?.children || roots).push(item);
    });
    const sortTree = items => items.sort((left, right) =>
      Number(left.child_order || 0) - Number(right.child_order || 0)
      || left.node_key.localeCompare(right.node_key, 'en', { numeric: true }))
      .forEach(item => sortTree(item.children));
    sortTree(roots);
    return roots;
  }

  async function readAllProductTreePages(invoke, artifactRef, pageSize = 5000, dependencyArtifacts = [], documentGid = null) {
    const limit = Math.max(1, Math.min(5000, Number(pageSize) || 5000));
    const nodes = [];
    let offset = 0;
    let total = null;
    const pendingDependencies = [];
    while (true) {
      const payload = { artifact_ref: artifactRef, offset, limit };
      if (documentGid) payload.document_gid = documentGid;
      if (dependencyArtifacts.length) payload.dependency_artifacts = dependencyArtifacts;
      const page = await invoke('simulation.plmxml.model_tree.read', payload);
      if (page?.state !== 'ready') return page;
      const pageTotal = Number(page.node_count || 0);
      if (total == null) total = pageTotal;
      if (pageTotal !== total || pageTotal > 250000) throw new Error('product_tree_page_invalid');
      nodes.push(...Array.from(page.nodes || []));
      for (const location of page.dependency_locations || []) {
        if (!pendingDependencies.includes(location)) pendingDependencies.push(location);
      }
      if (page.next_offset == null) break;
      const nextOffset = Number(page.next_offset);
      if (!Number.isInteger(nextOffset) || nextOffset <= offset || nextOffset > total) {
        throw new Error('product_tree_page_invalid');
      }
      offset = nextOffset;
    }
    if (nodes.length !== total) throw new Error('product_tree_page_incomplete');
    return { state: 'ready', node_count: total, nodes, dependency_locations: pendingDependencies, next_offset: null };
  }

  function createCollection() {
    const state = { documents: [], selectedDocumentGid: null, hierarchies: [], selectedHierarchyGid: null, runtimeState: 'idle',
      environmentState: 'draft', runtimeDetail: null, failure: null, verificationSummary: null };
    return {
      state,
      replace(values) {
        const documents = Array.from(values || [], normalizeDocument)
          .sort((a, b) => (a.role === b.role ? a.document_gid.localeCompare(b.document_gid, 'en', { numeric: true }) : a.role === 'primary' ? -1 : 1));
        if (documents.length && documents.filter(item => item.role === 'primary').length !== 1) throw new Error('primary_model_document_required');
        if (new Set(documents.map(item => item.document_gid)).size !== documents.length) throw new Error('model_document_duplicate');
        state.documents = documents;
        if (!documents.some(item => item.document_gid === state.selectedDocumentGid)) state.selectedDocumentGid = documents[0]?.document_gid || null;
      },
      replaceHierarchies(values) {
        state.hierarchies = Array.from(values || [], value => ({
          ...value, hierarchy_gid: gid(value.hierarchy_gid, 'hierarchy_gid'),
          ...(Array.isArray(value.nodes) ? { nodes: Array.from(value.nodes) } : {}),
          ...(Array.isArray(value.placements) ? { placements: Array.from(value.placements) } : {}),
        }))
          .sort((a, b) => a.hierarchy_gid.localeCompare(b.hierarchy_gid, 'en', { numeric: true }));
        if (!state.hierarchies.some(item => item.hierarchy_gid === state.selectedHierarchyGid)) state.selectedHierarchyGid = state.hierarchies[0]?.hierarchy_gid || null;
      },
      selectHierarchy(hierarchyGid) {
        const selected = gid(hierarchyGid, 'hierarchy_gid');
        if (!state.hierarchies.some(item => item.hierarchy_gid === selected)) throw new Error('alternate_hierarchy_not_found');
        state.selectedHierarchyGid = selected;
      },
      addPlacement(hierarchyGid, placement) {
        const hierarchy = state.hierarchies.find(item => item.hierarchy_gid === gid(hierarchyGid, 'hierarchy_gid'));
        if (!hierarchy) throw new Error('alternate_hierarchy_not_found');
        const normalized = { ...placement, placement_gid: gid(placement.placement_gid, 'placement_gid') };
        if (hierarchy.placements.some(item => item.placement_gid === normalized.placement_gid)) throw new Error('placement_duplicate');
        hierarchy.placements.push(normalized);
      },
      setRuntimeProgress(value, detail = null) {
        if (!RUNTIME.has(value)) throw new Error('runtime_state_invalid');
        state.runtimeState = value; state.runtimeDetail = detail;
      },
      setEnvironmentState(value, failure = null) {
        if (!ENVIRONMENT.has(value)) throw new Error('environment_state_invalid');
        state.environmentState = value; state.failure = failure;
      },
    };
  }

  return { createCollection, collectVisibilityLeaves, deriveVisibilityState, buildHierarchyForest, buildProductForest, readAllProductTreePages };
});
