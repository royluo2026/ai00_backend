(function (root, factory) {
  const exports = factory();
  if (typeof module === 'object' && module.exports) module.exports = exports;
  if (root) root.DecompositionView = exports;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  const TYPE_LABELS = {
    large_flow: '大流程', medium_flow: '中流程', standard_workflow: '标准工作流',
    skill: 'Skill', workflow_node: '工作流节点', task_tool: 'Task Tool',
    human_task: '人工任务', human_approval: '人工审批', capability: 'Capability',
    gateway: 'Gateway / SDK', provider: 'Provider',
  };
  const CONTEXT_LABELS = { data: '数据源', rule: '规则源', knowledge: '知识源', ontology: '本体' };

  function card(level, title, subtitle) {
    const row = document.createElement('div');
    row.className = `oc-decomposition-level level-${level}`;
    row.dataset.lineageLevel = level;
    const badge = document.createElement('span');
    badge.className = 'oc-lineage-badge';
    badge.textContent = TYPE_LABELS[level] || level;
    const body = document.createElement('div');
    body.className = 'oc-lineage-card';
    const strong = document.createElement('strong');
    strong.textContent = title;
    const note = document.createElement('small');
    note.textContent = subtitle || '';
    body.append(strong, note);
    row.append(badge, body);
    return row;
  }

  function renderDecomposition(container, rootGid, items, edges, capabilityBindings, contextBindings) {
    container.textContent = '';
    const itemMap = new Map(items.map(item => [item.gid, item]));
    const visited = new Set();
    let current = rootGid;
    while (current && !visited.has(current)) {
      visited.add(current);
      const item = itemMap.get(current);
      if (!item) break;
      container.appendChild(card(item.item_type, item.title));
      const edge = edges.find(candidate => candidate.source_item_gid === current
        && ['contains', 'realized_by', 'implements'].includes(candidate.relation_type));
      current = edge?.target_item_gid;
    }

    const toolIds = new Set([...visited].filter(gid => itemMap.get(gid)?.item_type === 'task_tool'));
    const capabilities = capabilityBindings.filter(binding => toolIds.has(binding.source_item_gid));
    if (capabilities.length) {
      const row = document.createElement('div');
      row.className = 'oc-decomposition-level level-capability';
      row.dataset.lineageLevel = 'capability';
      const badge = document.createElement('span');
      badge.className = 'oc-lineage-badge';
      badge.textContent = 'Capability';
      const stack = document.createElement('div');
      stack.className = 'oc-lineage-stack';
      capabilities.forEach(binding => {
        const item = document.createElement('div');
        item.className = 'oc-lineage-card';
        item.dataset.capabilityGid = binding.capability_version_gid;
        const title = document.createElement('strong');
        title.textContent = binding.capability_id;
        const note = document.createElement('small');
        note.textContent = `只读治理对象 · ${binding.purpose || ''}`;
        item.append(title, note);
        stack.appendChild(item);
      });
      row.append(badge, stack);
      container.appendChild(row);

      const gatewayRefs = [...new Set(capabilities.map(binding => binding.gateway_ref).filter(Boolean))];
      const providerRefs = [...new Set(capabilities.map(binding => binding.provider_ref).filter(Boolean))];
      if (gatewayRefs.length) container.appendChild(card('gateway', gatewayRefs.join(' · '), '编排中心调用边界'));
      if (providerRefs.length) container.appendChild(card('provider', providerRefs.join(' · '), '能力治理中心维护 · 只读引用'));
    }
    contextBindings.filter(binding => toolIds.has(binding.source_item_gid)).forEach(binding => {
      const row = card('context', CONTEXT_LABELS[binding.ref_type] || binding.ref_type, `${binding.ref_gid} · 只读引用`);
      row.dataset.contextType = binding.ref_type;
      container.appendChild(row);
    });
    return container;
  }

  return { renderDecomposition };
});
