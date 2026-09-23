(function (root, factory) {
  const isCommonJs = typeof module === 'object' && module.exports;
  const dependencies = isCommonJs ? {
    canvas: require('./panorama_canvas'),
    decomposition: require('./decomposition_view'),
    inspector: require('./inspector'),
    axis: require('./axis_editor'),
    metrics: require('./metrics'),
  } : {
    canvas: root.PanoramaCanvas,
    decomposition: root.DecompositionView,
    inspector: root.OrchestrationInspector,
    axis: root.AxisEditor,
    metrics: root.OrchestrationMetrics,
  };
  const exports = factory(dependencies);
  if (isCommonJs) module.exports = exports;
  if (root) root.OrchestrationCenterApp = exports;
})(typeof window !== 'undefined' ? window : globalThis, function ({ canvas, decomposition, inspector, axis, metrics }) {
  const el = (tag, className, text) => {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (text !== undefined) item.textContent = text;
    return item;
  };

  function createDemoState() {
    const references = [
      { label: 'craft.bop.validation.run@1', edit_authority: 'capability_governance', deep_link: '/web/admin/capabilities.html?id=craft.bop.validation.run' },
      { label: 'BOP 主数据 S-20931', edit_authority: 'data', deep_link: '/web/ext_datasource/index.html' },
      { label: '工艺规划规则集 v8', edit_authority: 'rule_governance', deep_link: '/web/rule_mgmt/rule_mgmt.html' },
      { label: 'BOP 核心本体 r17', edit_authority: 'ontology', deep_link: '/web/ontology/index.html' },
      { label: '历史决策案例集 v6', edit_authority: 'knowledge', deep_link: '/web/knowledge_hub/index.html' },
    ];
    return {
      mode: 'fixed',
      axis: {
        x_items: ['TG0前', 'TG0', 'TG1', 'TG2', 'EP', 'PPV', 'PP', 'P', 'SOP'],
        y_items: ['项目管理', '同步工程', '工艺规划', '设备规划'],
      },
      nodes: [
        { gid: 'n1', title: '项目目标与边界', x_item_key: 'TG0前', y_item_key: '项目管理', status: 'succeeded' },
        { gid: 'n2', title: '跨专业方案同步', x_item_key: 'TG0', y_item_key: '同步工程', status: 'succeeded' },
        { gid: 'n3', title: '总装 BOP 规划', x_item_key: 'TG1', y_item_key: '工艺规划', status: 'running', references,
          suggestion: { id: 's-quality-gate', summary: '建议增加质量门禁', changes: ['在发布前增加 BOP 完整性校验', '复用 craft.bop.validation.run@1'] } },
        { gid: 'n4', title: '设备需求定义', x_item_key: 'TG2', y_item_key: '设备规划', status: 'pending' },
        { gid: 'n5', title: '工艺验证与冻结', x_item_key: 'PPV', y_item_key: '工艺规划', status: 'waiting_human' },
        { gid: 'n6', title: '量产放行', x_item_key: 'SOP', y_item_key: '项目管理', status: 'pending' },
      ],
      edges: [
        { gid: 'business-1', edge_type: 'business', source_node_gid: 'n1', target_node_gid: 'n2', label: '业务目标' },
        { gid: 'business-2', edge_type: 'business', source_node_gid: 'n2', target_node_gid: 'n3', label: '方案输入' },
        { gid: 'business-3', edge_type: 'business', source_node_gid: 'n3', target_node_gid: 'n5', label: 'BOP 基线' },
        { gid: 'data-1', edge_type: 'data', source_node_gid: 'n2', target_node_gid: 'n4', label: '结构与资源数据' },
        { gid: 'command-1', edge_type: 'command', source_node_gid: 'n3', target_node_gid: 'n4', label: '规划任务下达' },
        { gid: 'semantic-1', edge_type: 'semantic', source_node_gid: 'n1', target_node_gid: 'n3', label: '规则与本体约束' },
        { gid: 'business-4', edge_type: 'business', source_node_gid: 'n5', target_node_gid: 'n6', label: '人工放行' },
      ],
      items: [
        { gid: 'large', item_type: 'large_flow', title: '整车项目策划到量产' },
        { gid: 'medium', item_type: 'medium_flow', title: '总装工艺规划' },
        { gid: 'workflow', item_type: 'standard_workflow', title: 'BOP 编制与验证标准工作流' },
        { gid: 'workflow-node', item_type: 'workflow_node', title: '生成、校验与发布 BOP 节点' },
        { gid: 'tool', item_type: 'task_tool', title: 'BOP 生成与治理校验 Task Tool' },
      ],
      itemEdges: [
        { source_item_gid: 'large', target_item_gid: 'medium', relation_type: 'contains' },
        { source_item_gid: 'medium', target_item_gid: 'workflow', relation_type: 'contains' },
        { source_item_gid: 'workflow', target_item_gid: 'workflow-node', relation_type: 'contains' },
        { source_item_gid: 'workflow-node', target_item_gid: 'tool', relation_type: 'realized_by' },
      ],
      capabilityBindings: [
        { gid: 'cb1', source_item_gid: 'tool', capability_id: 'craft.bop.entry.detail.get', capability_version_gid: 'cv2_read', purpose: '读取 BOP', gateway_ref: 'agent.gateway.v1', provider_ref: 'craft.provider' },
        { gid: 'cb2', source_item_gid: 'tool', capability_id: 'craft.bop.validation.run', capability_version_gid: 'cv2_validate', purpose: '校验 BOP', gateway_ref: 'agent.gateway.v1', provider_ref: 'craft.provider' },
        { gid: 'cb3', source_item_gid: 'tool', capability_id: 'craft.bop.version.publish', capability_version_gid: 'cv2_publish', purpose: '发布 BOP', gateway_ref: 'agent.gateway.v1', provider_ref: 'craft.provider' },
      ],
      contextBindings: ['data', 'rule', 'knowledge', 'ontology'].map(type => ({
        gid: `ctx-${type}`, source_item_gid: 'tool', ref_type: type, ref_gid: `${type}-source-v1`, purpose: `${type} context`,
      })),
      effectiveRate: {
        total_workload_hours: 1000,
        effective_agent_workload_hours: 515,
        rate: 0.515,
        tasks: [
          { task_key: '数据收集整理', workload_hours: 500, agent_share: 0.8, acceptance_pass_rate: 0.95, safety_gate_passed: true, effective_agent_workload_hours: 380 },
          { task_key: '异常原因分析', workload_hours: 300, agent_share: 0.5, acceptance_pass_rate: 0.9, safety_gate_passed: true, effective_agent_workload_hours: 135 },
          { task_key: '最终放行审批', workload_hours: 200, agent_share: 0, acceptance_pass_rate: 1, safety_gate_passed: false, effective_agent_workload_hours: 0 },
        ],
      },
      automationRatio: { rate: 0.62 },
    };
  }

  function mountApp(container, initialState, options = {}) {
    let state = JSON.parse(JSON.stringify(initialState));
    container.textContent = '';
    const shell = el('div', 'oc-app');
    const header = el('header', 'oc-topbar');
    const identity = el('div', 'oc-identity');
    identity.append(el('span', 'oc-eyebrow', '编排中心 · 项目全景'), el('h1', '', '业务全景'));
    if (options.demo) {
      const badge = el('span', 'oc-demo-badge', '测试环境 · 演示数据');
      badge.dataset.demoState = 'true';
      identity.appendChild(badge);
    }
    const kpis = el('div', 'oc-kpis');
    const percent = value => Number.isFinite(Number(value)) ? `${(Number(value) * 100).toFixed(1).replace('.0', '')}%` : '—';
    [['自动化流程', percent(state.automationRatio?.rate), 'show-automation-ratio'], ['有效智能作业率', percent(state.effectiveRate?.rate), 'show-effective-rate']].forEach(([label, value, action]) => {
      const kpi = el('button', 'oc-kpi');
      kpi.dataset.action = action;
      kpi.append(el('span', '', label), el('strong', '', value));
      kpis.appendChild(kpi);
    });
    const actions = el('div', 'oc-actions');
    const fixed = el('button', 'oc-mode is-active', '固定模式'); fixed.dataset.mode = 'fixed';
    const explore = el('button', 'oc-mode', '探索模式'); explore.dataset.mode = 'exploration';
    const editX = el('button', 'oc-action', '编辑横轴'); editX.dataset.action = 'edit-x-axis';
    const editY = el('button', 'oc-action', '编辑纵轴'); editY.dataset.action = 'edit-y-axis';
    [fixed, explore, editX, editY].forEach(button => { button.disabled = Boolean(options.readOnly); });
    actions.append(fixed, explore, editX, editY);
    header.append(identity, kpis, actions);

    const nav = el('nav', 'oc-view-nav');
    const panoramaButton = el('button', 'is-active', '业务全景'); panoramaButton.dataset.view = 'panorama';
    const decompositionButton = el('button', '', '全链路透视'); decompositionButton.dataset.view = 'decomposition';
    nav.append(panoramaButton, decompositionButton);
    const workspace = el('section', 'oc-workspace');
    shell.append(header, nav, workspace);
    container.appendChild(shell);

    kpis.addEventListener('click', event => {
      if (event.target.closest('[data-action="show-effective-rate"]')) {
        shell.querySelector('.oc-metrics-panel')?.remove();
        const panel = el('aside');
        if (state.effectiveRate) {
          metrics.renderMetricsPanel(panel, state.effectiveRate);
        } else {
          panel.className = 'oc-metrics-panel';
          panel.appendChild(el('p', 'oc-advisory-note', '当前项目暂无经过治理校验的指标证据。'));
        }
        const close = el('button', 'oc-panel-close', '关闭');
        close.addEventListener('click', () => panel.remove());
        panel.prepend(close);
        shell.appendChild(panel);
      }
    });

    function renderPanorama() {
      canvas.mountPanorama(workspace, state, {
        renderInspector(target, node) {
          inspector.renderInspector(target, node, {
            acceptSuggestion: options.acceptSuggestion,
          });
        },
      });
    }
    function show(view) {
      [...nav.querySelectorAll('button')].forEach(button => button.classList.toggle('is-active', button.dataset.view === view));
      if (view === 'decomposition') {
        workspace.className = 'oc-workspace oc-decomposition';
        decomposition.renderDecomposition(workspace, 'large', state.items, state.itemEdges, state.capabilityBindings, state.contextBindings);
      } else {
        workspace.className = 'oc-workspace';
        renderPanorama();
      }
    }

    function openAxisEditor(dimension) {
      shell.querySelector('.oc-axis-editor')?.remove();
      const key = `${dimension}_items`;
      const nodeKey = `${dimension}_item_key`;
      const panel = el('aside', 'oc-axis-editor');
      const close = el('button', 'oc-panel-close', '关闭');
      const title = el('h2', '', `编辑${dimension === 'x' ? '横' : '纵'}轴`);
      const hint = el('p', '', '用逗号分隔；顺序就是画布显示顺序。删除已有坐标时需迁移其中节点。');
      const input = el('textarea');
      input.dataset.axisItems = dimension;
      input.value = state.axis[key].join(',');
      const mappings = el('div', 'oc-axis-mappings');
      const error = el('div', 'oc-axis-error');
      const apply = el('button', 'oc-button oc-button-primary', '应用');
      apply.dataset.action = 'apply-axis';
      close.addEventListener('click', () => panel.remove());
      apply.addEventListener('click', () => {
        const nextItems = input.value.split(',').map(item => item.trim()).filter(Boolean);
        const removed = state.axis[key].filter(item => !nextItems.includes(item));
        const occupied = removed.filter(item => state.nodes.some(node => node[nodeKey] === item));
        const existingSelects = [...mappings.querySelectorAll('select')];
        if (occupied.length && !existingSelects.length) {
          mappings.textContent = '';
          occupied.forEach(item => {
            const row = el('label', '', `${item} 中的节点迁移到`);
            const select = el('select');
            select.dataset.reassignFrom = item;
            select.appendChild(el('option', '', '请选择'));
            nextItems.forEach(target => {
              const option = el('option', '', target);
              option.value = target;
              select.appendChild(option);
            });
            row.appendChild(select);
            mappings.appendChild(row);
          });
          error.textContent = '请先为被删除坐标中的节点选择新位置。';
          return;
        }
        const reassignments = Object.fromEntries(existingSelects.map(select => [select.dataset.reassignFrom, select.value]));
        try {
          const result = axis.applyAxisChange(state.axis, dimension, nextItems, state.nodes, reassignments);
          state = { ...state, ...result };
          panel.remove();
          show('panorama');
        } catch (reason) {
          error.textContent = reason.message;
        }
      });
      panel.append(close, title, hint, input, mappings, error, apply);
      shell.appendChild(panel);
    }
    nav.addEventListener('click', event => event.target.dataset.view && show(event.target.dataset.view));
    actions.addEventListener('click', event => {
      if (event.target.dataset.mode) {
        state.mode = event.target.dataset.mode;
        [...actions.querySelectorAll('[data-mode]')].forEach(button => button.classList.toggle('is-active', button.dataset.mode === state.mode));
      }
      const dimension = event.target.dataset.action === 'edit-x-axis' ? 'x' : event.target.dataset.action === 'edit-y-axis' ? 'y' : null;
      if (dimension) openAxisEditor(dimension);
    });
    show('panorama');
    return shell;
  }

  return { mountApp, createDemoState };
});
