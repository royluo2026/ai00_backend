(function (root, factory) {
  const exports = factory();
  if (typeof module === 'object' && module.exports) module.exports = exports;
  if (root) root.OrchestrationMetrics = exports;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  const percent = value => `${(Number(value) * 100).toFixed(1)}%`;
  const hours = value => Number(value).toLocaleString('zh-CN', { maximumFractionDigits: 2 });

  function renderMetricsPanel(container, result) {
    container.textContent = '';
    container.className = 'oc-metrics-panel';
    const title = document.createElement('h2');
    title.textContent = '有效智能作业率';
    const formula = document.createElement('div');
    formula.className = 'oc-metric-formula';
    formula.textContent = `${hours(result.effective_agent_workload_hours)} ÷ ${hours(result.total_workload_hours)} = ${percent(result.rate)}`;
    const definition = document.createElement('p');
    definition.textContent = 'Agent 安全承担且验收通过的等效工作量 ÷ 全部业务工作量';
    const list = document.createElement('div');
    list.className = 'oc-metric-tasks';
    const tasks = Array.isArray(result.tasks) ? result.tasks : [];
    if (!tasks.length) {
      list.appendChild(document.createTextNode('暂无任务级证据明细'));
    }
    tasks.forEach(task => {
      const row = document.createElement('article');
      row.dataset.taskContribution = task.task_key;
      const heading = document.createElement('strong');
      heading.textContent = task.task_key;
      const calculation = document.createElement('small');
      calculation.textContent = `${hours(task.workload_hours)}h × ${percent(task.agent_share)} × ${percent(task.acceptance_pass_rate)} = ${hours(task.effective_agent_workload_hours)}h`;
      row.append(heading, calculation);
      if (!task.safety_gate_passed) {
        const gate = document.createElement('span');
        gate.className = 'oc-safety-gate';
        gate.textContent = '安全门禁未通过 · Agent 承担按 0%';
        row.appendChild(gate);
      }
      list.appendChild(row);
    });
    container.append(title, formula, definition, list);
    return container;
  }

  return { renderMetricsPanel };
});
