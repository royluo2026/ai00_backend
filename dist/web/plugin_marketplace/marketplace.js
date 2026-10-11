(() => {
  'use strict';
  const model = window.AI00Marketplace;
  const client = model.createClient(window.AI00ExistingCapabilityClient);
  const state = { view: 'catalog', query: '', items: [], next: null, canManage: false, busy: false, loading: false, valid: false, request: 0 };
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
  let searchTimer, toastTimer;

  function render() {
    $('plugin-list').innerHTML = state.items.map((item, index) => `
      <article class="plugin-card">
        <div class="plugin-content">
          <div class="plugin-title">${esc(item.name)} <small>v${esc(item.version)}</small><span class="plugin-state" data-state="${esc(item.state)}">${esc(model.labels[item.state])}</span></div>
          <p class="plugin-description">${esc(item.description || '暂无说明')}</p>
          <div class="plugin-meta">${esc(item.plugin_id)}${item.current_version ? ` · 当前 v${esc(item.current_version)}` : ''}${item.previous_version ? ` · 上一版本 v${esc(item.previous_version)}` : ''}</div>
          <details class="plugin-meta"><summary>能力权限</summary>${esc((state.view === 'catalog' ? item.requested_grants : item.granted_capabilities).join('、') || '无额外能力')}</details>
          ${item.last_error ? `<p class="market-error">${esc(item.last_error)}</p>` : ''}
        </div>
        <div class="plugin-actions">${model.actions(item, state.canManage, state.view).map(action => `<button class="market-button ${action === 'install' ? 'primary' : action === 'uninstall' ? 'danger' : ''}" data-action="${action}" data-index="${index}" ${state.busy || state.loading || !state.valid ? 'disabled' : ''}>${model.actionLabels[action]}</button>`).join('')}</div>
      </article>`).join('') || '<div class="empty">没有符合条件的插件</div>';
    $('load-more').hidden = state.next === null;
    $('load-more').disabled = state.busy || state.loading || !state.valid;
    $('refresh').disabled = state.busy || state.loading;
    $('search').disabled = state.busy;
    document.querySelectorAll('[data-view]').forEach(tab => { tab.disabled = state.busy; });
  }

  async function refresh(append = false) {
    const request = ++state.request;
    state.loading = true; state.valid = false;
    render();
    $('load-error').hidden = true;
    if (!state.items.length) $('plugin-list').innerHTML = '<div class="empty">正在加载插件…</div>';
    try {
      const result = await client.search(state.view, state.query, append ? state.next : 0);
      if (request !== state.request) return;
      state.items = append ? [...state.items, ...result.items] : result.items;
      state.next = result.next_offset;
      state.valid = true;
    } catch (error) {
      if (request !== state.request) return;
      $('load-error').textContent = `插件加载失败：${error.message}${state.items.length ? '。已保留上次列表，请刷新后再操作。' : '。请确认已登录后重试。'}`;
      $('load-error').hidden = false;
    } finally {
      if (request === state.request) {
        state.loading = false; render();
        if (!state.valid && !state.items.length) $('plugin-list').innerHTML = '<div class="empty">暂时无法获取插件列表</div>';
      }
    }
  }

  function confirmAction(action, item) {
    const dialog = $('confirm-dialog');
    $('confirm-title').textContent = `${model.actionLabels[action]} · ${item.name}`;
    $('confirm-action').textContent = model.actionLabels[action];
    $('confirm-message').textContent = action === 'uninstall' ? '将卸载插件并撤销运行授权，保留团队数据。'
      : action === 'finish' ? `请确认 v${item.current_version} 已通过实际可用性验证。确认后将启用此版本；如验证失败，请取消并回滚。`
      : ['install', 'upgrade'].includes(action) ? `目标版本：${item.version}\n将授权能力：${item.requested_grants.join('、') || '无'}${action === 'install' ? '\n安装后处于停用状态，可在“已安装”中启用。' : '\n更新后需确认可用，失败时可回滚。'}`
      : `将${model.actionLabels[action]}插件 ${item.plugin_id}${action === 'rollback' ? ` 至 v${item.previous_version}` : ''}。`;
    dialog.returnValue = 'cancel';
    return new Promise(resolve => {
      dialog.addEventListener('close', () => resolve(dialog.returnValue === 'confirm'), { once: true });
      dialog.showModal();
    });
  }

  async function runAction(button) {
    if (state.busy || state.loading || !state.valid || button.disabled) return;
    const item = state.items[Number(button.dataset.index)], action = button.dataset.action;
    if (!model.actions(item, state.canManage, state.view).includes(action)) return;
    if (action === 'open') {
      try { window.parent.TabManager.openPlugin(item.plugin_id, item.name); }
      catch (_) { $('load-error').textContent = '请在 App 工作台中打开插件。'; $('load-error').hidden = false; }
      return;
    }
    state.busy = true;
    clearTimeout(searchTimer);
    render();
    try {
      if (!await confirmAction(action, item)) return;
      state.valid = false;
      await client.run(action, item);
      $('feedback').textContent = `${model.actionLabels[action]}成功`;
      $('feedback').hidden = false;
      clearTimeout(toastTimer); toastTimer = setTimeout(() => { $('feedback').hidden = true; }, 4000);
      if (action === 'install') await selectView('installed');
      else await refresh();
    } catch (error) {
      state.valid = false;
      if (error.code === 'authentication_stale') {
        const login = window.electronAPI?.authFeishuLogin || window.parent?.electronAPI?.authFeishuLogin;
        $('feedback').textContent = '该操作需要最近完成身份认证，正在打开飞书登录…';
        $('feedback').hidden = false;
        const result = typeof login === 'function' ? await login() : null;
        if (result?.ok) {
          await refresh();
          if (state.valid) $('feedback').textContent = `认证已更新，请再次点击${model.actionLabels[action]}。`;
        } else {
          $('feedback').hidden = true;
          $('load-error').textContent = '认证未完成，请重新登录后再操作。';
          $('load-error').hidden = false;
        }
        return;
      }
      $('load-error').textContent = `操作未完成：${error.message}。请刷新状态后再操作。`;
      $('load-error').hidden = false;
    } finally { state.busy = false; render(); }
  }

  function selectView(view) {
    state.view = view; state.items = []; state.next = null;
    document.querySelectorAll('[data-view]').forEach(tab => {
      tab.classList.toggle('active', tab.dataset.view === view);
      tab.setAttribute('aria-selected', String(tab.dataset.view === view));
    });
    return refresh();
  }

  async function init() {
    const applyTheme = theme => {
      document.documentElement.dataset.theme = theme === 'dark' ? 'dark' : 'light';
      document.documentElement.classList.toggle('theme-dark', theme === 'dark');
    };
    applyTheme(localStorage.getItem('system.theme') || 'light');
    window.addEventListener('message', event => { if (event.source === window.parent && event.data?.type === 'theme') applyTheme(event.data.theme); });
    $('plugin-list').addEventListener('click', event => { const button = event.target.closest('[data-action]'); if (button) void runAction(button); });
    document.querySelectorAll('[data-view]').forEach(tab => tab.addEventListener('click', () => { if (!state.busy) void selectView(tab.dataset.view); }));
    $('search').addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => { if (!state.busy) { state.query = $('search').value.trim(); void selectView(state.view); } }, 250); });
    $('load-more').addEventListener('click', () => refresh(true));
    $('refresh').addEventListener('click', async () => { await access(); await refresh(); });
    await access(); await refresh();
  }

  async function access() {
    $('admin-entry').hidden = true;
    try { $('admin-entry').hidden = !(await client.adminAccess()).can_admin; } catch (_) { /* Fail closed; ordinary marketplace remains usable. */ }
    try { state.canManage = await client.access(); $('access-hint').textContent = state.canManage ? '管理团队插件；所有操作均需确认并记录审计。' : '可浏览团队插件。安装与生命周期管理需要插件管理权限。'; }
    catch (error) { state.canManage = false; $('access-hint').textContent = `暂时无法确认管理权限：${error.message}`; }
  }
  document.addEventListener('DOMContentLoaded', init);
})();
