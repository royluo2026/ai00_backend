(function (root, factory) {
  const router = typeof module === 'object' && module.exports
    ? require('./orthogonal_router')
    : root.OrthogonalRouter;
  const exports = factory(router);
  if (typeof module === 'object' && module.exports) module.exports = exports;
  if (root) root.PanoramaCanvas = exports;
})(typeof window !== 'undefined' ? window : globalThis, function ({ routeOrthogonal, toSvgPath }) {
  const FLOW_META = {
    business: ['业务流', '#2563eb'],
    data: ['数据流', '#0f9f73'],
    command: ['命令流', '#d97706'],
    semantic: ['本体/知识/规则流', '#8b5cf6'],
  };
  const STATUS = {
    pending: ['待运行', '#94a3b8'],
    running: ['运行中', '#2563eb'],
    waiting_human: ['等待人工', '#d97706'],
    succeeded: ['已完成', '#0f9f73'],
    failed: ['失败', '#dc2626'],
  };

  function nodeRect(node, axis) {
    const column = Math.max(axis.x_items.indexOf(node.x_item_key), 0);
    const row = Math.max(axis.y_items.indexOf(node.y_item_key), 0);
    return { x: 154 + column * 190, y: 70 + row * 150, w: 150, h: 70 };
  }

  function element(tag, className, text) {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (text !== undefined) item.textContent = text;
    return item;
  }

  function mountPanorama(container, state, options = {}) {
    container.textContent = '';
    const shell = element('section', 'oc-panorama');
    const toolbar = element('div', 'oc-flow-toolbar');
    Object.entries(FLOW_META).forEach(([type, [label, color]]) => {
      const button = element('button', 'oc-flow-toggle', label);
      button.type = 'button';
      button.dataset.flowToggle = type;
      button.style.setProperty('--flow-color', color);
      toolbar.appendChild(button);
    });
    shell.appendChild(toolbar);

    const viewport = element('div', 'oc-canvas-viewport');
    const canvas = element('div', 'oc-canvas');
    canvas.style.minHeight = '70vh';
    const width = 154 + state.axis.x_items.length * 190;
    const height = 70 + state.axis.y_items.length * 150;
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;

    state.axis.x_items.forEach((stage, index) => {
      const header = element('div', 'oc-stage', stage);
      header.dataset.stage = stage;
      header.style.left = `${154 + index * 190}px`;
      canvas.appendChild(header);
    });
    state.axis.y_items.forEach((lane, index) => {
      const label = element('div', 'oc-lane-label', lane);
      label.dataset.lane = lane;
      label.style.top = `${70 + index * 150}px`;
      canvas.appendChild(label);
      const row = element('div', 'oc-lane-row');
      row.style.top = `${70 + index * 150}px`;
      row.style.width = `${state.axis.x_items.length * 190}px`;
      canvas.appendChild(row);
    });

    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.classList.add('oc-flow-layer');
    svg.setAttribute('width', String(width));
    svg.setAttribute('height', String(height));
    Object.entries(FLOW_META).forEach(([type, [, color]]) => {
      const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      group.dataset.flowType = type;
      group.setAttribute('stroke', color);
      state.edges.filter(edge => edge.edge_type === type).forEach(edge => {
        const source = state.nodes.find(node => node.gid === edge.source_node_gid);
        const target = state.nodes.find(node => node.gid === edge.target_node_gid);
        if (!source || !target) return;
        const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        path.dataset.edgeId = edge.gid;
        path.setAttribute('d', toSvgPath(routeOrthogonal(nodeRect(source, state.axis), nodeRect(target, state.axis), [])));
        path.setAttribute('fill', 'none');
        path.setAttribute('stroke-width', '2');
        path.setAttribute('marker-end', 'url(#ocArrow)');
        group.appendChild(path);
      });
      svg.appendChild(group);
    });
    canvas.appendChild(svg);

    const inspector = element('aside', 'oc-inspector is-collapsed');
    inspector.setAttribute('aria-live', 'polite');
    state.nodes.forEach(node => {
      const rect = nodeRect(node, state.axis);
      const card = element('button', 'oc-node');
      card.type = 'button';
      card.dataset.nodeId = node.gid;
      card.style.left = `${rect.x}px`;
      card.style.top = `${rect.y}px`;
      const title = element('strong', 'oc-node-title', node.title);
      const meta = element('span', 'oc-node-meta', `${node.x_item_key} · ${node.y_item_key}`);
      card.append(title, meta);
      card.addEventListener('click', () => {
        inspector.classList.remove('is-collapsed');
        if (options.renderInspector) {
          options.renderInspector(inspector, node);
        } else {
          const [statusLabel, statusColor] = STATUS[node.status] || STATUS.pending;
          inspector.textContent = '';
          inspector.append(
            element('h2', '', node.title),
            element('p', 'oc-inspector-kicker', '节点运行状态'),
          );
          const status = element('div', 'oc-status', statusLabel);
          status.style.setProperty('--status-color', statusColor);
          inspector.appendChild(status);
        }
        options.onSelect?.(node);
      });
      canvas.appendChild(card);
    });

    toolbar.querySelectorAll('[data-flow-toggle]').forEach(button => {
      button.addEventListener('click', () => {
        button.classList.toggle('is-off');
        const group = svg.querySelector(`[data-flow-type="${button.dataset.flowToggle}"]`);
        if (group) group.style.display = button.classList.contains('is-off') ? 'none' : '';
      });
    });

    viewport.appendChild(canvas);
    shell.append(viewport, inspector);
    container.appendChild(shell);
    return { canvas, inspector };
  }

  return { mountPanorama, nodeRect, FLOW_META };
});
