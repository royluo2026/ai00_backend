function operationLabel(operation) {
  const vpps = operation?.parameters?.vpps || '无 VPPS';
  return `${operation?.name || operation?.operation_id} · ${vpps}`;
}

export function formatProjectIdentity(project) {
  if (!project) return '尚未选择项目';
  return `${project.title || '未命名项目'} · ${project.object_ref || '无项目引用'}`;
}

export function renderAlignedCandidateRows(matches, escapeHtml) {
  const esc = escapeHtml || (value => String(value ?? ''));
  return matches.map((match, index) => `<div class="candidate-pair" data-index="${index}">
      <button type="button" class="candidate" data-side="left" data-index="${index}">
        <span><strong>${esc(operationLabel(match.left))}</strong><small>${esc(match.method === 'vpps' ? 'VPPS 精确' : `描述相似 ${Math.round(match.score * 100)}%`)}</small></span>
      </button>
      <div class="candidate candidate-readonly" data-side="right">
        <span><strong>${esc(operationLabel(match.right))}</strong><small>${esc((match.reasons || []).join('、') || '已与左侧对齐')}</small></span>
      </div>
    </div>`).join('');
}
