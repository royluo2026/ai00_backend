(function (root, factory) {
  const exports = factory();
  if (typeof module === 'object' && module.exports) module.exports = exports;
  if (root) root.OrchestrationStore = exports;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  const X_AXIS = ['TG0前', 'TG0', 'TG1', 'TG2', 'EP', 'PPV', 'PP', 'P', 'SOP'];
  const Y_AXIS = ['项目管理', '同步工程', '工艺规划', '设备规划'];
  class PublishedVersionError extends Error {}

  const clone = value => JSON.parse(JSON.stringify(value));

  function createOrchestrationStore(initial = {}) {
    let state = {
      panorama: null,
      version: { status: 'draft', revision: 1 },
      axis: { x_items: X_AXIS, y_items: Y_AXIS },
      nodes: [], edges: [], items: [], itemEdges: [],
      capabilityBindings: [], contextBindings: [],
      ui: { dirty: false, changes: [], suggestions: [] },
      ...clone(initial),
    };
    state.axis = { x_items: X_AXIS, y_items: Y_AXIS, ...(state.axis || {}) };
    state.ui = { dirty: false, changes: [], suggestions: [], ...(state.ui || {}) };

    function change(type, payload, mutate) {
      if (state.version.status === 'published') throw new PublishedVersionError('Published versions are immutable');
      const next = clone(state);
      mutate(next);
      next.ui.dirty = true;
      next.ui.changes.push({ type, payload: clone(payload) });
      state = next;
      return state;
    }

    return {
      getState: () => clone(state),
      moveNode(gid, coordinates) {
        if (!state.nodes.some(node => node.gid === gid)) return clone(state);
        return change('move_node', { gid, ...coordinates }, next => {
          next.nodes = next.nodes.map(node => node.gid === gid ? { ...node, ...coordinates } : node);
        });
      },
      setAxis(axis) {
        return change('set_axis', axis, next => { next.axis = clone(axis); });
      },
      upsertEdge(edge) {
        return change('upsert_edge', edge, next => {
          const index = next.edges.findIndex(item => item.gid === edge.gid);
          if (index < 0) next.edges.push(clone(edge)); else next.edges[index] = clone(edge);
        });
      },
      upsertBinding(binding) {
        return change('upsert_binding', binding, next => {
          const index = next.capabilityBindings.findIndex(item => item.gid === binding.gid);
          if (index < 0) next.capabilityBindings.push(clone(binding)); else next.capabilityBindings[index] = clone(binding);
        });
      },
      acceptSuggestion(id) {
        const suggestion = state.ui.suggestions.find(item => item.id === id);
        if (!suggestion) return clone(state);
        return change('accept_suggestion', { id }, next => {
          const patch = suggestion.patch || {};
          next.nodes.push(...clone(patch.add_nodes || []));
          next.edges.push(...clone(patch.add_edges || []));
          next.capabilityBindings.push(...clone(patch.add_bindings || []));
          next.ui.suggestions = next.ui.suggestions.filter(item => item.id !== id);
        });
      },
    };
  }

  return { createOrchestrationStore, PublishedVersionError, X_AXIS, Y_AXIS };
});
