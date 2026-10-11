(function (root) {
  'use strict';

  const SEARCH = 'simulation.connector.recovery.search';
  const RESOLVE = 'simulation.connector.recovery.resolve';
  const STOP_CODES = /authentication|permission|forbidden|confirmation|stale|conflict|expected_|resource_version|recovery_state_changed|runtime_owner_mismatch|runtime_session_invalid/i;
  const UNCERTAIN_CODES = /outcome_unknown|outcome_persistence_failed|invocation_unavailable|request_timeout|runtime_timeout|invalid_response|network|transport/i;
  const SAFE_CONTINUE_CODES = /^(validation_error|invalid_request)$/i;

  function mount({ document = root.document, invoke, refreshConnection, openDocumentChooser } = {}) {
    const get = id => document.getElementById(id);
    const entry = get('btnConnectorRecovery');
    const overlay = get('connectorRecoveryOverlay');
    const items = get('connectorRecoveryItems');
    const status = get('connectorRecoveryStatus');
    const reason = get('connectorRecoveryReason');
    const confirmButton = get('connectorRecoveryConfirm');
    const cancelButton = get('connectorRecoveryCancel');
    const selectAll = get('connectorRecoverySelectAll');
    const deselectAll = get('connectorRecoveryDeselectAll');
    const progress = get('connectorRecoveryProgress');
    const results = get('connectorRecoveryResults');
    const chooserButton = get('connectorRecoveryChooseDocument');
    const prevPage = get('connectorRecoveryPrevPage');
    const nextPage = get('connectorRecoveryNextPage');
    const pageInfo = get('connectorRecoveryPageInfo');
    if (!entry || !overlay) return;

    const call = invoke || ((id, envelope, confirmation) => root.AI00Business.invoke(id, envelope, confirmation));
    const refresh = refreshConnection || (() => root._tryAutoConnect?.());
    const chooseDocument = openDocumentChooser || (() => get('btnSwitchVmDocument')?.click());
    const selected = new Map();
    const visible = new Map();
    const completed = new Set();
    let submitting = false;
    let loading = false;
    let loadError = '';
    let generation = 0;
    let stopRequested = false;
    let page = 1;
    const pageSize = 5;
    let pageCount = 0;
    let total = 0;

    const key = operation => `${operation.plan_id}\n${operation.device_id}`;
    const identity = operation => `operation=${operation.operation_id || '—'} · plan=${operation.plan_id} · device=${operation.device_id}`;
    const decision = () => document.querySelector('input[name="connectorRecoveryDecision"]:checked')?.value;
    const active = intent => !stopRequested && intent === generation && !overlay.classList.contains('hidden');
    const decisionLabels = { executed: '已执行', not_executed: '未执行', abandoned: '放弃并归档' };
    const validFence = value => typeof value === 'string' && /^sha256:[a-f0-9]{64}$/i.test(value);
    const selectable = operation => operation.eligible === true && validFence(operation.recovery_fingerprint) && Array.isArray(operation.allowed_decisions) && operation.allowed_decisions.length > 0;
    const allows = (operation, selectedDecision) => selectable(operation) && operation.allowed_decisions.includes(selectedDecision);

    function updateSelectionStatus() {
      const selectedDecision = decision();
      if (!selectedDecision) return;
      const available = Array.from(visible.values()).filter(operation => allows(operation, selectedDecision) && !completed.has(key(operation))).length;
      setStatus(`已选 ${selected.size}/${available} 项，可提交“${decisionLabels[selectedDecision]}”结论`);
    }

    function sync() {
      const length = reason.value.trim().length;
      confirmButton.disabled = submitting || loading || Boolean(loadError) || !selected.size || !decision() || length < 1 || length > 1024;
      reason.disabled = submitting;
      document.querySelectorAll('input[name="connectorRecoveryDecision"]').forEach(node => { node.disabled = submitting; });
      const selectedDecision = decision();
      const available = Array.from(visible.values()).filter(operation => selectedDecision && allows(operation, selectedDecision) && !completed.has(key(operation))).length;
      items.querySelectorAll('[data-recovery-plan]').forEach(node => {
        const operation = visible.get(node.dataset.recoveryKey);
        node.disabled = submitting || node.dataset.eligible !== 'true' || completed.has(node.dataset.recoveryKey) || Boolean(selectedDecision && !allows(operation, selectedDecision));
      });
      if (selectAll) {
        selectAll.textContent = selectedDecision ? `全选当前结论可处理项（${available}）` : '请先选择结论';
        selectAll.disabled = submitting || loading || Boolean(loadError) || !selectedDecision || available === 0;
      }
      if (deselectAll) deselectAll.disabled = submitting || !selected.size;
      if (prevPage) prevPage.disabled = submitting || loading || Boolean(loadError) || page <= 1;
      if (nextPage) nextPage.disabled = submitting || loading || Boolean(loadError) || pageCount === 0 || page >= pageCount;
    }

    function updatePagination() {
      if (pageInfo) pageInfo.textContent = `第 ${pageCount ? page : 0} / ${pageCount} 页 · 共 ${total} 项`;
      sync();
    }

    function setStatus(message, error = false) {
      status.textContent = message;
      status.dataset.state = error ? 'error' : 'info';
    }

    function render(found) {
      items.replaceChildren();
      selected.clear();
      visible.clear();
      for (const operation of found) {
        const operationKey = key(operation);
        const button = document.createElement('button');
        visible.set(operationKey, operation);
        button.type = 'button';
        button.className = 'cs-recovery-item';
        button.dataset.recoveryPlan = operation.plan_id;
        button.dataset.recoveryKey = operationKey;
        button.dataset.eligible = String(selectable(operation));
        button.setAttribute('aria-pressed', 'false');
        const checkbox = document.createElement('span');
        checkbox.className = 'cs-recovery-check';
        checkbox.setAttribute('aria-hidden', 'true');
        const body = document.createElement('span');
        body.className = 'cs-recovery-item-body';
        const heading = document.createElement('strong');
        heading.textContent = `未完成操作 · ${operation.operation_id || '—'}`;
        const metadata = document.createElement('span');
        metadata.textContent = `plan ${operation.plan_id} · device ${operation.device_id}`;
        const detail = document.createElement('span');
        const hashlessAbandonOnly = !validFence(operation.outcome_hash) && operation.allowed_decisions?.length === 1 && operation.allowed_decisions[0] === 'abandoned';
        detail.textContent = hashlessAbandonOnly
          ? '缺少结果摘要，仅可放弃并归档'
          : completed.has(operationKey)
          ? '本次已处理，不会重复提交'
          : `状态 ${operation.status || 'unknown'} · 错误 ${operation.error_code || '—'} · 运行代 ${operation.runtime_generation}`;
        const allowed = document.createElement('span');
        allowed.textContent = `可选结论：${(operation.allowed_decisions || []).map(value => decisionLabels[value] || value).join('、') || '无'}`;
        body.append(heading, metadata, detail, allowed);
        button.append(checkbox, body);
        button.onclick = () => {
          if (button.disabled) return;
          if (selected.has(operationKey)) selected.delete(operationKey);
          else selected.set(operationKey, operation);
          button.setAttribute('aria-pressed', String(selected.has(operationKey)));
          sync();
          updateSelectionStatus();
        };
        items.append(button);
      }
      sync();
    }

    async function load(message = '', requestedPage = page, allowFallback = true) {
      const token = ++generation;
      selected.clear();
      loading = true;
      loadError = '';
      setStatus('正在读取未完成操作…');
      items.replaceChildren();
      sync();
      try {
        const result = await call(SEARCH, { version: 1, payload: { page: requestedPage, page_size: pageSize } });
        if (token !== generation || overlay.classList.contains('hidden')) return { state: 'stale' };
        if (!Array.isArray(result?.items) || result.items.length > pageSize || !Number.isInteger(result.page) || !Number.isInteger(result.page_size) || !Number.isInteger(result.total) || !Number.isInteger(result.page_count)) throw Error('recovery_search_result_invalid');
        if (allowFallback && requestedPage > result.page_count && result.page_count > 0 && result.items.length === 0) {
          page = result.page_count;
          return load(message, page, false);
        }
        page = result.page_count === 0 ? 1 : requestedPage;
        pageCount = result.page_count;
        total = result.total;
        loading = false;
        render(result.items);
        updatePagination();
        setStatus(message || (result.total ? `当前账号有 ${result.total} 项待人工核对` : '当前账号没有待人工核对项'));
        return { state: 'loaded', items: result.items, total: result.total, page: page, page_count: pageCount };
      } catch (error) {
        if (token !== generation || overlay.classList.contains('hidden')) return { state: 'stale' };
        loading = false;
        loadError = error?.message || 'unknown_error';
        setStatus(`读取失败：${loadError}`, true);
        sync();
        return { state: 'failed', error: loadError };
      }
    }

    async function open() {
      if (submitting) return;
      stopRequested = false;
      page = 1;
      pageCount = 0;
      total = 0;
      overlay.classList.remove('hidden');
      reason.value = '';
      if (progress) progress.textContent = '';
      results?.replaceChildren();
      chooserButton?.classList.add('hidden');
      document.querySelectorAll('input[name="connectorRecoveryDecision"]').forEach(node => { node.checked = false; });
      updatePagination();
      await load('', 1);
    }

    function close() {
      stopRequested = true;
      ++generation;
      selected.clear();
      loading = false;
      loadError = '';
      overlay.classList.add('hidden');
      sync();
      entry.focus();
    }

    function addResult(operation, label, detail = '') {
      if (!results) return;
      const row = document.createElement('div');
      row.className = 'cs-recovery-result';
      row.textContent = `${identity(operation)}：${label}${detail ? `（${detail}）` : ''}`;
      results.append(row);
    }

    async function resolveBatch() {
      if (submitting || loadError) return;
      const selectedDecision = decision();
      const explanation = reason.value.trim();
      const batch = Array.from(selected.values());
      if (!batch.length || !selectedDecision || !explanation) {
        setStatus('请选择可处理操作、处理结果并填写原因', true);
        return;
      }
      if (explanation.length > 1024) {
        setStatus('原因不能超过 1024 个字符', true);
        return;
      }
      const identities = batch.map(identity).join('\n');
      const prompt = `确认批量提交 ${batch.length} 项人工核对结果？\ndecision=${selectedDecision}\nreason=${explanation}\n${identities}`;
      const intent = generation;
      if (!(await root.AI00Dialogs.confirm(prompt))) {
        setStatus('已取消提交，未作更改');
        return;
      }

      if (intent !== generation || submitting) return;
      submitting = true;
      stopRequested = false;
      results?.replaceChildren();
      chooserButton?.classList.add('hidden');
      sync();
      let successes = 0;
      let failures = 0;
      let stopped = '';
      let executedSuccess = false;

      for (let index = 0; index < batch.length; index++) {
        if (!active(intent)) break;
        const operation = batch[index];
        if (progress) progress.textContent = `正在处理 ${index + 1}/${batch.length}：${identity(operation)}`;
        const payload = {
          plan_id: operation.plan_id,
          device_id: operation.device_id,
          expected_generation: operation.runtime_generation,
          expected_recovery_fingerprint: operation.recovery_fingerprint,
          decision: selectedDecision,
          reason: explanation,
        };
        if (validFence(operation.outcome_hash)) payload.expected_outcome_hash = operation.outcome_hash;
        if (validFence(operation.plan_hash)) payload.expected_plan_hash = operation.plan_hash;
        const nonce = root.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
        try {
          const result = await call(RESOLVE, { version: 1, payload, idempotency_key: `${RESOLVE}:${nonce}` }, async () => active(intent));
          completed.add(key(operation));
          if (!active(intent)) break;
          successes++;
          executedSuccess ||= selectedDecision === 'executed';
          addResult(operation, '已记录', result.audit_ref || '');
        } catch (error) {
          if (!active(intent)) break;
          const code = error?.code || error?.message || 'unknown_error';
          failures++;
          if (UNCERTAIN_CODES.test(code) || (!STOP_CODES.test(code) && !SAFE_CONTINUE_CODES.test(code))) {
            addResult(operation, '结果不确定', code);
            stopped = `${code}，结果不确定，已停止后续提交`;
            break;
          }
          addResult(operation, '失败', code);
          if (STOP_CODES.test(code)) {
            stopped = `${code}，已停止后续提交`;
            break;
          }
        }
      }

      if (!active(intent)) {
        submitting = false;
        sync();
        return;
      }
      let refreshError = '';
      try {
        await Promise.resolve(refresh());
      } catch (error) {
        refreshError = error?.message || 'unknown_error';
      }
      if (!active(intent)) {
        submitting = false;
        sync();
        return;
      }
      const remaining = await load();
      if (remaining.state === 'stale') {
        submitting = false;
        sync();
        return;
      }
      submitting = false;
      sync();
      const pending = remaining.state === 'failed'
        ? `待核对列表刷新失败：${remaining.error}`
        : `当前账号仍有 ${remaining.total} 项待人工核对`;
      const summary = `批量处理完成：成功 ${successes} 项，失败 ${failures} 项${stopped ? `；${stopped}` : ''}${refreshError ? `；连接状态刷新失败：${refreshError}` : ''}；${pending}`;
      setStatus(summary, Boolean(stopped) || remaining.state === 'failed');
      if (progress) progress.textContent = '';
      if (executedSuccess) {
        chooserButton?.classList.remove('hidden');
        root._cmdShow?.(`${summary}；可主动打开文档选择器另行核对关联`, 'info');
      }
    }

    entry.addEventListener('click', open);
    cancelButton.addEventListener('click', close);
    confirmButton.addEventListener('click', resolveBatch);
    chooserButton?.addEventListener('click', chooseDocument);
    prevPage?.addEventListener('click', () => { if (!submitting && !loading && page > 1) load('', page - 1); });
    nextPage?.addEventListener('click', () => { if (!submitting && !loading && page < pageCount) load('', page + 1); });
    reason.addEventListener('input', sync);
    document.querySelectorAll('input[name="connectorRecoveryDecision"]').forEach(node => node.addEventListener('change', () => {
      const selectedDecision = decision();
      for (const [operationKey, operation] of selected) {
        if (!allows(operation, selectedDecision)) selected.delete(operationKey);
      }
      items.querySelectorAll('[data-recovery-plan]').forEach(node => node.setAttribute('aria-pressed', String(selected.has(node.dataset.recoveryKey))));
      sync();
      updateSelectionStatus();
    }));
    selectAll?.addEventListener('click', () => {
      const selectedDecision = decision();
      if (!selectedDecision) return;
      for (const [operationKey, operation] of visible) {
        if (allows(operation, selectedDecision) && !completed.has(operationKey)) selected.set(operationKey, operation);
      }
      items.querySelectorAll('[data-recovery-plan]').forEach(node => node.setAttribute('aria-pressed', String(selected.has(node.dataset.recoveryKey))));
      sync();
      updateSelectionStatus();
    });
    deselectAll?.addEventListener('click', () => {
      selected.clear();
      items.querySelectorAll('[data-recovery-plan]').forEach(node => node.setAttribute('aria-pressed', 'false'));
      sync();
      if (decision()) setStatus(`已选 0/${Array.from(visible.values()).filter(operation => allows(operation, decision()) && !completed.has(key(operation))).length} 项`);
    });
    sync();
    return { open, close };
  }

  root.AI00ConnectorRecovery = { mount };
})(window);
