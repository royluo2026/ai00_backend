(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.AI00PlmxmlTreeImport = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const refs = value => String(value || '').split(/\s+/).filter(Boolean).map(item => item.replace(/^#/, ''));
  const payload = (label, fn) => {
    const prefix = `#PLMXML(PS_API-doc/${fn}('`;
    return label.startsWith(prefix) && label.endsWith("'))") ? label.slice(prefix.length, -3) : '';
  };
  const pathFrom = label => {
    const values = payload(label, 'JT_PROP_NAME').split('\\0').filter(Boolean);
    return values[0]?.startsWith('CHLD') ? values.slice(1) : values;
  };
  const local = element => element.localName || String(element.nodeName || '').split(':').pop();
  const elements = document => Array.from(document.getElementsByTagName('*'));
  const attr = (element, name) => element?.getAttribute(name) || '';

  function parsePlmxmlTree(text, { DOMParser = globalThis.DOMParser, maxNodes = 250000 } = {}) {
    if (typeof DOMParser !== 'function') throw new Error('plmxml_parser_unavailable');
    if (!Number.isInteger(maxNodes) || maxNodes < 1) throw new Error('bom_snapshot_limit_invalid');
    const document = new DOMParser().parseFromString(String(text), 'application/xml');
    const all = elements(document);
    if (all.some(element => local(element) === 'parsererror')) throw new Error('plmxml_invalid');
    const graph = all.find(element => local(element) === 'InstanceGraph');
    const rootInstanceId = refs(attr(graph, 'rootRefs'))[0] || '';
    const productNames = new Map(all.filter(element => local(element) === 'ProductInstance')
      .map(element => [attr(element, 'id'), attr(element, 'name')]));
    const rootInstance = all.find(element => local(element) === 'ProductInstance' && attr(element, 'id') === rootInstanceId);
    const occurrences = all.filter(element => local(element) === 'Occurrence').map((element, ordinal) => {
      const applicationRefs = new Map();
      const values = new Map();
      Array.from(element.getElementsByTagName('*')).forEach(child => {
        if (local(child) === 'ApplicationRef') applicationRefs.set(attr(child, 'application'), attr(child, 'label'));
        if (local(child) === 'UserValue') values.set(attr(child, 'title'), attr(child, 'value'));
      });
      return { ordinal, instanceRefs: refs(attr(element, 'instanceRefs')), applicationRefs, values };
    });
    const rootOccurrence = occurrences.find(item => item.instanceRefs.length === 1 && item.instanceRefs[0] === rootInstanceId);
    const rootPdmUid = rootOccurrence?.values.get('__PLM_OCC_PDM_UID') || '';
    if (!rootInstanceId || !rootOccurrence || !rootPdmUid) throw new Error('plmxml_current_state_root_identity_missing');
    let paths = occurrences.map(occurrence => ({ occurrence, path: pathFrom(occurrence.applicationRefs.get('__TC-VIS_APP') || '') }))
      .filter(item => item.path.length).sort((left, right) => left.path.length - right.path.length || left.occurrence.ordinal - right.occurrence.ordinal);
    if (!paths.length) {
      paths = occurrences
        .filter(occurrence => occurrence.instanceRefs[0] === rootInstanceId && occurrence.values.get('__PLM_OCC_PDM_UID'))
        .map(occurrence => ({
          occurrence,
          path: occurrence.instanceRefs,
          printableName: productNames.get(occurrence.instanceRefs.at(-1)) || occurrence.instanceRefs.at(-1),
        }))
        .sort((left, right) => left.path.length - right.path.length || left.occurrence.ordinal - right.occurrence.ordinal);
    }
    if (!paths.length) throw new Error('plmxml_current_state_structure_missing');

    const rootPath = paths[0].path[0];
    const rootKey = `pdm:${rootPdmUid}`;
    const nodes = [{
      node_key: rootKey, parent_key: null, child_order: 0,
      printable_name: attr(rootInstance, 'name') || rootPath,
      occurrence_id: rootOccurrence.values.get('catiaOccurrenceName') || '', has_more: false,
    }];
    const pathKey = path => path.join('\u001f');
    const keys = new Map([[pathKey([rootPath]), rootKey]]);
    const pdmUids = new Set([rootPdmUid]);
    const childOrders = new Map();
    for (const entry of paths) {
      if (entry.path.length === 1) continue;
      if (nodes.length >= maxNodes) throw new Error('bom_snapshot_limit_exceeded');
      const pdmUid = entry.occurrence.values.get('__PLM_OCC_PDM_UID') || '';
      const currentPathKey = pathKey(entry.path);
      if (!pdmUid || pdmUids.has(pdmUid) || keys.has(currentPathKey)) throw new Error('plmxml_current_state_identity_ambiguous');
      const parentKey = keys.get(pathKey(entry.path.slice(0, -1)));
      if (!parentKey) throw new Error('plmxml_current_state_parent_missing');
      const order = childOrders.get(parentKey) || 0;
      childOrders.set(parentKey, order + 1);
      const key = `pdm:${pdmUid}`;
      nodes.push({
        node_key: key, parent_key: parentKey, child_order: order,
        printable_name: entry.printableName || entry.path.at(-1),
        occurrence_id: entry.occurrence.values.get('catiaOccurrenceName') || '', has_more: false,
      });
      keys.set(currentPathKey, key);
      pdmUids.add(pdmUid);
    }
    const parents = new Set(nodes.map(node => node.parent_key).filter(Boolean));
    nodes.forEach(node => { node.has_more = parents.has(node.node_key); });
    return { root_node_key: rootKey, nodes, source: 'manual_plmxml' };
  }

  return { parsePlmxmlTree };
});
