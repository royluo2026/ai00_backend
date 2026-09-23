(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.AI00BopVmBindingDraft = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  const key = value => String(value || '').normalize('NFKC').trim().toLocaleLowerCase('en-US');

  function flatten(nodes, result = []) {
    for (const node of nodes || []) {
      if (!node?._synthetic) result.push(node);
      flatten(node?.children, result);
    }
    return result;
  }

  function build(entries, tree) {
    const vmNodes = flatten(tree?.children || []);
    const index = new Map();
    for (const node of vmNodes) {
      // Display names are hints, not identities. Automatic candidates must use
      // owner-supplied product / occurrence references, matching the Provider.
      for (const identity of new Set([key(node.catia_name), key(node.product_ref)])) {
        if (!identity) continue;
        if (!index.has(identity)) index.set(identity, []);
        index.get(identity).push(node);
      }
    }
    const hasParts = (entries || []).some(entry => (entry.parts || []).length);
    const hasVpps = (entries || []).some(entry => key(entry.vpps));
    const mode = hasParts ? 'parts' : hasVpps ? 'vpps' : 'structure_only';
    const bindings = [], unmatchedBop = [], claimed = new Set();
    for (const entry of entries || []) {
      const sources = mode === 'parts'
        ? (entry.parts || []).map(part => part.catia_occ).filter(Boolean)
        : mode === 'vpps' && entry.vpps ? [entry.vpps] : [];
      let matched = false;
      for (const identity of new Set(sources.map(key).filter(Boolean))) {
        const candidates = index.get(identity) || [];
        if (!candidates.length) continue;
        matched = true;
        for (const node of candidates) {
          claimed.add(String(node.key));
          bindings.push({
            bop_node_gid: String(entry.gid), vm_node_key: String(node.key),
            role: entry.part_feed ? 'load' : 'operate',
            disposition: candidates.length === 1 ? 'auto' : 'ambiguous',
            confidence_milli: candidates.length === 1 ? (mode === 'parts' ? 1000 : 960) : 800,
            match_basis: mode === 'parts' ? 'part_identity_exact' : 'vpps_exact',
          });
        }
      }
      if (!matched) unmatchedBop.push(String(entry.gid));
    }
    const loads = new Map();
    for (const item of bindings) {
      if (item.role !== 'load' || item.disposition !== 'auto') continue;
      if (!loads.has(item.vm_node_key)) loads.set(item.vm_node_key, []);
      loads.get(item.vm_node_key).push(item);
    }
    for (const items of loads.values()) if (items.length > 1) for (const item of items) {
      item.disposition = 'conflict'; item.confidence_milli = 0; item.conflict_code = 'multiple_load_claims';
    }
    return {
      mode, bindings,
      auto_count: bindings.filter(item => item.disposition === 'auto').length,
      review_count: bindings.filter(item => item.disposition !== 'auto').length,
      unmatched_bop_node_gids: [...new Set(unmatchedBop)],
      unmatched_vm_node_keys: vmNodes.map(node => String(node.key)).filter(value => value && !claimed.has(value)),
    };
  }

  return { build, flatten };
});
