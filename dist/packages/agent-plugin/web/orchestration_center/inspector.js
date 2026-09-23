(function (root, factory) {
  const exports = factory();
  if (typeof module === 'object' && module.exports) module.exports = exports;
  if (root) root.OrchestrationInspector = exports;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  const STATUS = {
    pending: '待运行', running: '运行中', waiting_human: '等待人工',
    succeeded: '已完成', failed: '失败',
  };
  const AUTHORITIES = {
    capability_governance: 'Capability 治理中心修改', rule_governance: '规则中心修改',
    ontology: '本体中心修改', knowledge: '知识中心修改', code: '代码层修改', data: '数据治理中心修改',
  };

  function textElement(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    el.textContent = text;
    return el;
  }

  function renderInspector(container, selected, actions = {}) {
    container.textContent = '';
    container.classList.add('oc-detail-panel');
    container.append(
      textElement('p', 'oc-detail-kicker', '节点详情'),
      textElement('h2', '', selected.title),
    );
    const tabs = textElement('div', 'oc-detail-tabs', '四流关系　分解　运行');
    container.appendChild(tabs);
    container.appendChild(textElement('div', 'oc-detail-status', STATUS[selected.status] || STATUS.pending));

    const governance = selected.governance || selected.governance_status;
    if (governance && typeof governance === 'object') {
      const section = textElement('section', 'oc-governance-status', '治理状态');
      [['machine_passed', '机器校验'], ['human_approved', '人工批准'], ['runtime_verified', '运行验证']].forEach(([key, label]) => {
        const value = governance[key];
        const row = textElement('div', 'oc-governance-row', '');
        row.append(textElement('span', '', label), textElement('strong', value === true ? 'is-pass' : 'is-pending', value === true ? '通过' : value === false ? '未通过' : '未提供'));
        section.appendChild(row);
      });
      container.appendChild(section);
    }

    const references = textElement('section', 'oc-reference-list', '');
    (selected.references || []).forEach(reference => {
      const card = textElement('article', 'oc-reference-card', '');
      card.append(
        textElement('strong', '', reference.label),
        textElement('small', '', AUTHORITIES[reference.edit_authority] || '外部模块修改'),
      );
      if (reference.deep_link) {
        const link = textElement('a', '', '前往权威模块');
        link.href = reference.deep_link;
        link.target = '_top';
        card.appendChild(link);
      }
      references.appendChild(card);
    });
    container.appendChild(references);

    if (selected.suggestion) {
      const suggestion = textElement('section', 'oc-suggestion', '');
      suggestion.append(
        textElement('span', 'oc-advisory-badge', 'AI 建议 · advisory'),
        textElement('strong', '', selected.suggestion.summary),
      );
      const preview = textElement('button', 'oc-button', '预览差异');
      preview.type = 'button';
      preview.dataset.action = 'preview-suggestion';
      preview.addEventListener('click', () => {
        if (suggestion.querySelector('.oc-suggestion-diff')) return;
        const diff = textElement('ul', 'oc-suggestion-diff', '');
        selected.suggestion.changes.forEach(change => {
          diff.appendChild(textElement('li', '', change));
        });
        if (typeof actions.acceptSuggestion === 'function') {
          const accept = textElement('button', 'oc-button oc-button-primary', '提交审批');
          accept.type = 'button';
          accept.dataset.action = 'accept-suggestion';
          accept.addEventListener('click', () => actions.acceptSuggestion(selected.suggestion.id));
          suggestion.append(diff, accept);
        } else {
          const advisory = textElement('span', 'oc-advisory-note', 'AI 仅提供建议；变更需进入治理审批后执行');
          suggestion.append(diff, advisory);
        }
      });
      suggestion.appendChild(preview);
      container.appendChild(suggestion);
    }
    return container;
  }

  return { renderInspector };
});
