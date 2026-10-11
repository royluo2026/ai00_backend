export function groupCraftNodes(nodes) {
  const byGid = new Map(nodes.map(node => [node.gid, node]));
  const children = new Map();
  const roots = [];
  const cycleNodes = new Set();
  for (const node of nodes) {
    const parent = node.parent_gid;
    const ancestors = new Set([node.gid]);
    let current = parent;
    while (current && byGid.has(current) && !ancestors.has(current)) {
      ancestors.add(current);
      current = byGid.get(current).parent_gid;
    }
    if (parent && byGid.has(parent) && !ancestors.has(current)) {
      if (!children.has(parent)) children.set(parent, []);
      children.get(parent).push(node);
    } else {
      roots.push(node);
      if (current && ancestors.has(current)) cycleNodes.add(node.gid);
    }
  }
  return { byGid, children, roots, cycleNodes };
}
