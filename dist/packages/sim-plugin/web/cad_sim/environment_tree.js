(function (root) {
  'use strict';
  function orderedChildren(nodes, parentGid) {
    return nodes.filter(node => node.parent_gid === parentGid)
      .sort((a, b) => (a.position || 0) - (b.position || 0) || String(a.node_gid).localeCompare(String(b.node_gid)));
  }
  function accessClass(node) {
    if (node?.access_mode === 'editable') return ' editable';
    if (node?.access_mode === 'read_only') return ' read-only';
    return '';
  }
  function accessLabel(node) {
    return node?.access_mode === 'read_only' ? ' 🔒' : '';
  }
  function environmentLabel(workspace, kind) {
    if (!workspace) return '当前仿真环境树';
    const name = workspace.display_label || workspace.name || workspace.project_name || '未命名环境';
    const prefix = kind === 'team' ? '项目空间'
      : kind === 'managed_personal' ? '个人项目空间'
        : '个人仿真环境';
    return `${prefix} · ${name}`;
  }
  function currentDocumentLabel(workspace, kind) {
    return workspace ? `当前仿真文档 · ${environmentLabel(workspace, kind)}` : '当前仿真文档 · 未选择环境';
  }
  function expandedForLevel(nodes, level) {
    const expanded = new Set();
    const target = Math.max(1, Math.min(5, Number(level) || 1));
    const visit = (parentGid, depth) => orderedChildren(nodes, parentGid).forEach(node => {
      const children = orderedChildren(nodes, node.node_gid);
      if (children.length && depth < target - 1) expanded.add(node.node_gid);
      visit(node.node_gid, depth + 1);
    });
    visit(null, 0);
    return expanded;
  }
  function render(container, nodes, selectedGid, options = {}) {
    if (!container) return;
    container.replaceChildren();
    const expanded = options.expandedNodeGids || new Set();
    const append = (parent, parentGid, rootLevel = false) => {
      const list = document.createElement('ul');
      list.className = rootLevel ? 'cs-environment-tree-root' : 'cs-environment-tree-children';
      orderedChildren(nodes, parentGid).forEach(node => {
      const item = document.createElement('li');
      item.className = 'cs-environment-tree-branch';
      const row = document.createElement('button');
      row.type = 'button';
      row.className = `cs-environment-node${accessClass(node)}${node.node_gid === selectedGid ? ' active' : ''}`;
      row.dataset.nodeGid = node.node_gid;
      row.dataset.accessMode = node.access_mode || '';
      const children = orderedChildren(nodes, node.node_gid);
      if (children.length) {
        const toggle = document.createElement('span');
        const isExpanded = expanded.has(node.node_gid);
        toggle.className = 'cs-environment-tree-toggle';
        toggle.dataset.treeToggle = node.node_gid;
        toggle.textContent = isExpanded ? '▾' : '▸';
        toggle.title = isExpanded ? '折叠此层级' : '展开此层级';
        row.setAttribute('aria-expanded', String(isExpanded));
        row.appendChild(toggle);
      } else {
        const spacer = document.createElement('span');
        spacer.className = 'cs-environment-tree-toggle placeholder';
        row.appendChild(spacer);
      }
      if (node.access_mode === 'read_only') {
        row.setAttribute('aria-readonly', 'true');
        row.title = '该线体由其他负责人维护，仅可查看';
      }
      const label = document.createElement('span');
      label.className = 'cs-environment-tree-label';
      label.textContent = `${node.name || node.node_type}${accessLabel(node)}`;
      row.appendChild(label);
      item.appendChild(row);
      if (children.length && expanded.has(node.node_gid)) append(item, node.node_gid);
      list.appendChild(item);
    });
      parent.appendChild(list);
    };
    append(container, null, true);
  }
  root.AI00SimulationEnvironmentTree = {
    accessClass, accessLabel, currentDocumentLabel, environmentLabel, expandedForLevel, orderedChildren, render,
  };
})(globalThis);
