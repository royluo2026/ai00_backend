const ENVIRONMENTS = {
  test_: { text: '测试数据库', color: '#2563eb', background: '#dbeafe' },
  pp_: { text: '预生产数据库', color: '#9a3412', background: '#ffedd5' },
  '': { text: '生产数据库', color: '#b91c1c', background: '#fee2e2' },
};

export function renderDataEnvironment(element, prefix) {
  if (!element) return;
  const item = ENVIRONMENTS[prefix];
  element.textContent = item?.text || '数据库状态未知';
  element.style.cssText = `color:${item?.color || '#475569'};background:${item?.background || '#e2e8f0'};padding:8px 10px;border-radius:6px;font-size:12px;font-weight:600;white-space:normal;text-align:center`;
  element.title = item ? `当前后端实际表前缀：${prefix || '无前缀'}` : '无法读取后端当前数据库环境';
}

export function unwrapEnvironmentResponse(response) {
  if (response?.success === true && response.data?.ok === true) return response.data.data;
  throw Error(response?.error?.message || response?.data?.error?.message || '无权操作或数据库环境检查失败');
}

export function mountDataEnvironmentSettings(document, container, invoke, { visibleOnFailure = false, readActive = () => invoke('base.runtime.data_environment.active.get', {}) } = {}) {
  if (!container) return;
  container.hidden = !visibleOnFailure;
  container.replaceChildren();
  let status;
  let restartTarget = null, restartDeadline = 0, retryTimer, disposed = false;
  container.classList.add('data-environment-settings');
  const element = (tag, text, className) => {
    const node = document.createElement(tag); node.textContent = text || '';
    if (className) node.className = className;
    return node;
  };
  const currentCard = element('div', '', 'de-card');
  const current = element('p', '正在检查数据库环境…', 'de-current'); current.setAttribute('aria-live', 'polite');
  currentCard.append(element('h3', '当前连接'), current,
    element('p', '环境切换作用于此后端的所有用户。', 'de-description'));
  const switchCard = element('div', '', 'de-card');
  switchCard.append(element('h3', '环境切换（仅超管）'),
    element('p', '选择结构检查通过的环境。确认切换后，后端会重启。', 'de-description'));
  const select = element('select'); select.setAttribute('aria-label', '目标数据库环境'); select.disabled = true;
  const change = element('button', '切换并重启后端', 'de-primary'); change.type = 'button'; change.disabled = true;
  const actions = element('div', '', 'de-actions'); actions.append(select, change);
  const reasons = element('p', '', 'de-status'); reasons.setAttribute('aria-live', 'polite');
  switchCard.append(actions, reasons);
  const progressBox = element('div', '', 'de-progress'); progressBox.hidden = true;
  const progress = element('progress'); progress.max = 4; progress.value = 0;
  progress.setAttribute('aria-label', '数据库切换与重启进度');
  const progressLabel = element('p', '', 'de-status'); progressLabel.setAttribute('aria-live', 'polite');
  progressBox.append(progress, progressLabel,
    element('p', '提交切换 → 后端重启 → 恢复连接 → 确认环境', 'de-description'));
  switchCard.append(progressBox);
  function showProgress(step, text, failed = false) {
    progressBox.hidden = false; progress.value = step;
    progressLabel.textContent = `${step}/4 · ${text}`;
    progressBox.dataset.state = failed ? 'error' : step === 4 ? 'done' : 'running';
  }
  function retryRestart() {
    if (disposed) return;
    if (Date.now() >= restartDeadline) {
      restartTarget = null;
      reasons.textContent = '后端重启超时，切换尚未确认。请重新检查当前连接，或检查后端启动日志。';
      reasons.dataset.state = 'error'; showProgress(progress.value, '重启超时', true);
      return;
    }
    clearTimeout(retryTimer); retryTimer = setTimeout(load, 3000);
  }
  const checkCard = element('div', '', 'de-card');
  const refresh = element('button', '重新检查'); refresh.type = 'button';
  const unavailable = element('div', '', 'de-grid');
  checkCard.append(element('h3', '表结构检测'),
    element('p', '以 test_ 为基准：pp_ 必须与 test_ 一致；生产必须同时与 test_、pp_ 一致。', 'de-description'),
    unavailable);
  const checkActions = element('div', '', 'de-actions'); checkActions.append(refresh); checkCard.append(checkActions);
  const connectionCard = element('div', '', 'de-card');
  const testConnection = element('button', '测试连接'); testConnection.type = 'button'; testConnection.dataset.action = 'test-connection';
  const connectionResult = element('p', '尚未测试', 'de-status'); connectionResult.setAttribute('data-connection-result', ''); connectionResult.setAttribute('aria-live', 'polite');
  connectionCard.append(element('h3', '连接测试'),
    element('p', '检测后端当前使用的数据库连接，执行只读查询 SELECT 1。', 'de-description'), testConnection, connectionResult);
  container.append(currentCard, switchCard, checkCard, connectionCard);
  testConnection.addEventListener('click', async () => {
    testConnection.disabled = true; connectionResult.textContent = '正在测试当前后端连接…'; connectionResult.dataset.state = '';
    try {
      const result = await invoke('base.runtime.data_environment.connection.test', {});
      const errors = { authentication_failed: '数据库认证失败', database_not_found: '数据库不存在', network_unreachable: '数据库网络不可达', tls_or_server_config_failed: '数据库安全连接配置异常' };
      connectionResult.textContent = `${result.connected ? '连接成功' : '连接失败'} · ${ENVIRONMENTS[result.prefix]?.text || '未知环境'} · ${result.elapsed_ms} ms` +
        (result.connected ? '' : ` · ${errors[result.error_code] || '数据库连接异常'}`);
      connectionResult.dataset.state = result.connected ? 'ok' : 'error';
    } catch (error) {
      connectionResult.textContent = '连接测试失败：' + (error.message || '后端不可达或权限不足');
      connectionResult.dataset.state = 'error';
    } finally { testConnection.disabled = false; }
  });
  function update() {
    reasons.dataset.state = '';
    const option = status?.options.find(item => item.prefix === select.value);
    reasons.textContent = option?.reasons.join('\n') || '表结构一致';
    change.disabled = restartTarget !== null || !option?.available || status?.pending || select.value === status?.active_prefix;
  }
  async function load() {
    change.disabled = true; refresh.disabled = true; select.disabled = true;
    reasons.textContent = '正在检查表结构…';
    try {
      status = await invoke('base.runtime.data_environment.get', {});
      if (disposed) return;
      container.hidden = false;
      if (restartTarget !== null && status.pending) {
        showProgress(2, '后端正在关闭旧连接，自动重新检查…');
        reasons.textContent = '切换已接受，后端重启中，自动重新检查…';
        retryRestart(); return;
      }
      if (restartTarget !== null) {
        showProgress(3, '后端连接已恢复，正在确认目标环境');
        if (status.active_prefix === restartTarget) showProgress(4, '切换完成，已连接' + ENVIRONMENTS[restartTarget].text);
        else showProgress(3, '目标环境未生效，当前仍连接' + ENVIRONMENTS[status.active_prefix].text, true);
        restartTarget = null;
      }
      current.replaceChildren();
      const badge = element('span', ENVIRONMENTS[status.active_prefix]?.text || '未知', 'de-current-badge');
      const palette = ENVIRONMENTS[status.active_prefix];
      if (palette) { badge.style.color = palette.color; badge.style.background = palette.background; }
      current.append(badge, element('span', '表前缀：' + (status.active_prefix || '无前缀')));
      select.disabled = false;
      select.replaceChildren();
      for (const item of status.options) {
        const option = document.createElement('option'); option.value = item.prefix;
        option.textContent = ENVIRONMENTS[item.prefix].text + (item.available ? '' : '（不可用）');
        option.disabled = !item.available;
        option.title = item.reasons.join('\n');
        select.append(option);
      }
      select.value = status.active_prefix;
      unavailable.replaceChildren();
      for (const item of status.options) {
        const card = element('div', '', 'de-environment'); card.dataset.available = String(item.available);
        card.append(element('strong', ENVIRONMENTS[item.prefix].text),
          element('small', '表前缀：' + (item.prefix || '无前缀')),
          element('p', item.available ? '可用 · 表结构一致' : '不可用' + (item.difference_count ? ` · ${item.difference_count} 项结构差异` : ''), 'de-status de-availability'));
        if (item.reasons.length) {
          const details = element('details'); const list = element('ul');
          for (const reason of item.reasons) list.append(element('li', reason));
          details.append(element('summary', '查看差异与原因'), list); card.append(details);
        }
        unavailable.append(card);
      }
      update();
    } catch (error) {
      status = null; change.disabled = true; unavailable.replaceChildren();
      if (visibleOnFailure) container.hidden = false;
      // Session storage is scoped to the selected prefix. Confirm the public
      // runtime status separately; it never enables privileged controls.
      let active;
      try { active = await readActive(); } catch (_) {}
      if (disposed) return;
      if (Object.hasOwn(ENVIRONMENTS, active?.prefix)) {
        renderDataEnvironment(current, active.prefix);
        if (restartTarget !== null && active.prefix === restartTarget) {
          clearTimeout(retryTimer); restartTarget = null;
          showProgress(4, '切换完成，已连接' + ENVIRONMENTS[active.prefix].text + '，请重新登录');
          reasons.textContent = '后端已恢复，当前登录会话失效或无权检查表结构，请重新登录后检查。';
          reasons.dataset.state = ''; return;
        }
      }
      if (restartTarget !== null) {
        showProgress(2, '后端重启中，等待重新连接');
        reasons.textContent = '切换已接受，等待后端恢复，自动重新检查…'; reasons.dataset.state = '';
        retryRestart();
      } else if (!container.hidden) { reasons.textContent = '数据库环境检查失败：' + (error.message || '后端不可达') + '。请点击重新检查。'; reasons.dataset.state = 'error'; }
    } finally { refresh.disabled = false; }
  }
  select.addEventListener('change', update);
  refresh.addEventListener('click', load);
  change.addEventListener('click', async () => {
    if (change.disabled || !status) return;
    change.disabled = true; refresh.disabled = true;
    select.disabled = true; showProgress(0, '正在提交切换并重新核验表结构');
    try {
      const result = await invoke('base.runtime.data_environment.change.apply', { prefix: select.value, expected_prefix: status.active_prefix });
      if (!result?.accepted) throw Error('切换未被接受');
      current.textContent = result.restarting ? '后端正在重启，正在自动检测当前连接…' : '当前环境已生效';
      status.pending = result.restarting;
      if (result.restarting) {
        restartTarget = result.prefix; restartDeadline = Date.now() + 120000;
        showProgress(1, '切换已接受，准备重启后端'); reasons.textContent = '正在等待后端重启…';
        retryRestart();
      } else { showProgress(4, '当前环境已生效'); select.disabled = false; }
    } catch (error) {
      reasons.textContent = error.message || '切换失败，请重新检查';
      showProgress(0, reasons.textContent, true);
      status = null;
    } finally { refresh.disabled = false; }
  });
  void load();
  return { load, dispose() { disposed = true; clearTimeout(retryTimer); } };
}

export function monitorDataEnvironment(element, invoke, interval = 15000) {
  async function refresh() {
    try { renderDataEnvironment(element, (await invoke('base.runtime.data_environment.active.get', {})).prefix); }
    catch (_) { renderDataEnvironment(element, null); }
  }
  void refresh();
  const timer = setInterval(refresh, interval);
  return () => clearInterval(timer);
}
