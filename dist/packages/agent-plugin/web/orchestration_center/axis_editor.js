(function (root, factory) {
  const exports = factory();
  if (typeof module === 'object' && module.exports) module.exports = exports;
  if (root) root.AxisEditor = exports;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  class AxisReassignmentRequired extends Error {}
  const clone = value => JSON.parse(JSON.stringify(value));

  function applyAxisChange(axis, dimension, nextItems, nodes, reassignments = {}) {
    if (!['x', 'y'].includes(dimension) || !nextItems.length || new Set(nextItems).size !== nextItems.length) {
      throw new TypeError('axis must contain unique items');
    }
    const listKey = `${dimension}_items`;
    const nodeKey = `${dimension}_item_key`;
    const removed = axis[listKey].filter(item => !nextItems.includes(item));
    const occupied = removed.filter(item => nodes.some(node => node[nodeKey] === item));
    if (occupied.some(item => !nextItems.includes(reassignments[item]))) {
      throw new AxisReassignmentRequired(`Reassignment required for ${occupied.join(', ')}`);
    }
    const nextAxis = clone(axis);
    nextAxis[listKey] = [...nextItems];
    const nextNodes = nodes.map(node => removed.includes(node[nodeKey])
      ? { ...node, [nodeKey]: reassignments[node[nodeKey]] }
      : { ...node });
    return { axis: nextAxis, nodes: nextNodes };
  }

  return { applyAxisChange, AxisReassignmentRequired };
});
