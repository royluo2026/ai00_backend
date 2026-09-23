(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.AI00VmSnapshotTree = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  function projectNumberFromPlmxmlName(fileName) {
    const stem = String(fileName || '').replace(/\.(?:plmxml|xml)$/i, '');
    return stem.match(/^([A-Za-z]+\d+)(?:-|$)/)?.[1] || '未识别';
  }

  function snapshotToVisTree(snapshot) {
    const nodes = Array.isArray(snapshot?.nodes) ? snapshot.nodes : [];
    const byKey = new Map(nodes.map(item => [String(item.node_key), {
      name: item.name || item.printable_name || item.product_ref || String(item.node_key),
      key: String(item.node_key),
      catia_name: item.catia_occurrence_name || item.occurrence_id || '',
      occurrence_gid: item.occurrence_gid || '',
      visible: typeof item.visible === 'boolean' ? item.visible : null,
      children: [],
      has_more: Boolean(item.has_more),
      _order: Number(item.child_order) || 0,
    }]));
    const roots = [];
    for (const item of nodes) {
      const node = byKey.get(String(item.node_key));
      const parentKey = item.parent_key ?? item.parent_node_key;
      const parent = parentKey == null ? null : byKey.get(String(parentKey));
      (parent ? parent.children : roots).push(node);
    }
    const sort = items => {
      items.sort((left, right) => left._order - right._order);
      for (const item of items) {
        delete item._order;
        sort(item.children);
      }
    };
    sort(roots);
    return {
      name: '__virtual_root__', key: null, visible: true, has_more: false,
      children: [{
        name: '模型', key: null, visible: true, has_more: false,
        _synthetic: true, children: roots,
      }],
    };
  }

  function teamcenterOccurrencePathForNode(nodes, nodeKey) {
    const targetKey = String(nodeKey || '');
    const match = (Array.isArray(nodes) ? nodes : []).find(node => {
      if (String(node?.control_key || '') === targetKey || String(node?.node_key || '') === targetKey) return true;
      const path = node?.occurrence_path;
      const occurrenceUid = Array.isArray(path) && path.length ? path.at(-1)?.occurrence_uid : '';
      return occurrenceUid && `tc:${occurrenceUid}` === targetKey;
    });
    const path = match?.occurrence_path;
    return Array.isArray(path) && path.length ? path : null;
  }

  return { projectNumberFromPlmxmlName, snapshotToVisTree, teamcenterOccurrencePathForNode };
});
