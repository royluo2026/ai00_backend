(() => {
  'use strict';
  const client = window.AI00Marketplace.createClient(window.AI00ExistingCapabilityClient);
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const labels = { submitted: '待审核', published: '已发布', rejected: '已拒绝', revoked: '已撤销' };
  const actions = { approve: '审核并发布', reject: '拒绝发布', revoke: '撤销版本', publisher: '登记发布者', install: '安装到当前团队', submit: '提交插件包' };
  let items = [], next = null, valid = false, busy = false, allowed = false;

  function render() {
    $('admin-panel').hidden = !allowed;
    $('release-list').innerHTML = items.map((item, index) => `<article class="plugin-card"><div class="plugin-content">
      <div class="plugin-title">${esc(item.name)} <small>v${esc(item.version)}</small><span class="plugin-state">${labels[item.status]}</span></div>
      <p>${esc(item.description)}</p><div class="plugin-meta">${esc(item.plugin_id)} · 发布者 ${esc(item.publisher_id)}</div>
      <details class="plugin-meta"><summary>版本与审核信息</summary><p>摘要：${esc(item.release_sha256)}</p><p>申请能力：${esc(item.requested_grants.join('、') || '无')}</p><p>提交人：${esc(item.submitted_by)} · 审核人：${esc(item.reviewed_by || '暂无')}</p><p>审核意见：${esc(item.review_note || '暂无')}</p><p>更新于 ${esc(item.updated_at)}</p></details>
      </div><div class="plugin-actions">${(item.status === 'submitted' ? ['approve', 'reject'] : item.status === 'published' ? ['install', 'revoke'] : []).map(action => `<button class="market-button ${action === 'revoke' ? 'danger' : ''}" data-action="${action}" data-index="${index}" ${busy || !valid ? 'disabled' : ''}>${actions[action]}</button>`).join('')}</div></article>`).join('') || '<div class="empty">暂无符合条件的版本</div>';
    $('admin-more').hidden = next === null;
    $('admin-more').disabled = busy || !valid;
    $('upload-package').disabled = busy || !allowed || !valid;
    ['admin-refresh', 'release-status', 'release-query'].forEach(id => { $(id).disabled = busy; });
    $('publisher-form').querySelectorAll('input,textarea,button').forEach(node => { node.disabled = busy || !allowed; });
  }
  function error(message) { $('admin-error').textContent = message; $('admin-error').hidden = false; }
  async function load(append = false) {
    valid = false; render();
    const access = await client.adminAccess();
    allowed = access.can_admin === true;
    if (!allowed) { items = []; next = null; throw new Error('当前账号没有超管权限'); }
    const result = await client.releases($('release-status').value, $('release-query').value.trim(), append ? next : 0);
    items = append ? [...items, ...result.items] : result.items;
    next = result.next_offset; valid = true;
  }
  async function refresh(append = false) {
    if (busy) return;
    busy = true; $('admin-error').hidden = true; render();
    try { await load(append); $('admin-access').textContent = '平台管理范围：审核并发布签名版本；撤销将影响所有租户中使用此版本的插件。'; }
    catch (e) { allowed = false; valid = false; error(`加载失败：${e.message}。请重新打开或刷新页面重试。`); }
    finally { busy = false; render(); }
  }
  function confirm(action, item) {
    const dialog = $('admin-confirm'), reason = $('admin-reason');
    $('admin-confirm-title').textContent = actions[action];
    $('admin-confirm-button').textContent = actions[action];
    $('admin-confirm-message').textContent = action === 'publisher' ? `登记发布者 ${item.publisher_id}，绑定所填公钥。`
      : action === 'submit' ? `提交文件：${item.name}\n服务端将验证签名、包内容及版本，成功后进入待审核列表。`
      : action === 'install' ? `${item.plugin_id} · v${item.version}\n将授权能力：${item.requested_grants.join('、') || '无'}\n安装后处于停用状态，可在市场“已安装”中启用。`
      : `${item.plugin_id} · v${item.version}\n${item.release_sha256}\n${action === 'revoke' ? '将撤销此版本，并停用所有租户中使用此版本的安装。' : action === 'approve' ? '通过审核后，服务端将签名并向市场发布此版本。' : '拒绝此版本的发布申请。'}`;
    $('reason-label').hidden = ['publisher', 'submit', 'install'].includes(action); reason.required = !$('reason-label').hidden; reason.value = '';
    dialog.returnValue = 'cancel';
    return new Promise(resolve => { dialog.addEventListener('close', () => resolve(dialog.returnValue === 'confirm'), { once: true }); dialog.showModal(); });
  }
  async function mutate(action, item) {
    if (busy || !allowed || (action !== 'publisher' && !valid)) return;
    busy = true; render(); $('admin-error').hidden = true; $('admin-feedback').textContent = '';
    try {
      if (!await confirm(action, item)) return;
      const note = $('admin-reason').value.trim();
      if (['approve', 'reject', 'revoke'].includes(action) && !note) throw new Error('请填写审核意见或撤销原因');
      valid = false;
      const payload = action === 'publisher' ? item : { plugin_id: item.plugin_id, version: item.version, release_sha256: item.release_sha256, note,
        ...(action === 'revoke' ? {} : { approved: action === 'approve' }) };
      if (action === 'install') await client.run('install', item);
      else await client.administer(action === 'publisher' || action === 'revoke' ? action : 'review', payload);
      $('admin-feedback').textContent = `${actions[action]}成功`;
      if (action === 'publisher') $('publisher-form').reset();
      if (action === 'approve') $('release-status').value = 'published';
      await load();
    } catch (e) { valid = false; error(`操作未完成：${e.message}。请刷新后再操作。`); }
    finally { busy = false; render(); }
  }
  async function upload() {
    if (busy || !allowed || !valid) return;
    let focusPublisher = false;
    busy = true; render(); $('admin-error').hidden = true; $('admin-feedback').textContent = '正在选择并上传插件文件…';
    try {
      const selected = await window.AI00Business.invoke('base.artifact.import', { version: 1, payload: {}, native_io: { select: 'plugin_package' } });
      if (!await confirm('submit', selected)) { $('admin-feedback').textContent = '已取消提交'; return; }
      valid = false;
      $('admin-feedback').textContent = '正在校验签名并保存插件资源，请等待完成…';
      const result = await client.administer('submit', { artifact_ref: selected.artifact_ref });
      $('release-status').value = 'submitted'; $('release-query').value = result.plugin_id;
      $('admin-feedback').textContent = `上传成功：${result.plugin_id} v${result.version}。请审核发布，然后安装到当前团队。`;
      await load();
    } catch (e) {
      $('admin-feedback').textContent = '';
      if (e.code !== 'native_selection_cancelled') {
        valid = false;
        if (e.code === 'marketplace_state_conflict') {
          const publisher = $('publisher-form').closest('details');
          publisher.open = true;
          focusPublisher = true;
          error('上传未完成：提交被市场状态校验拒绝。请先确认发布者已登记且公钥匹配；同一插件版本不可重复提交。');
        } else error(`上传未完成：${e.message}。请刷新后重试。`);
      }
    } finally {
      busy = false; render();
      if (focusPublisher) $('publisher-form').elements.publisher_id.focus();
    }
  }
  document.addEventListener('DOMContentLoaded', () => {
    const theme = value => { document.documentElement.dataset.theme = value === 'dark' ? 'dark' : 'light'; document.documentElement.classList.toggle('theme-dark', value === 'dark'); };
    theme(localStorage.getItem('system.theme'));
    window.addEventListener('message', e => { if (e.source === window.parent && e.data?.type === 'theme') theme(e.data.theme); });
    $('admin-refresh').addEventListener('click', () => refresh());
    $('upload-package').addEventListener('click', upload);
    $('release-status').addEventListener('change', () => refresh());
    $('release-query').addEventListener('search', () => refresh());
    $('release-query').addEventListener('keydown', e => { if (e.key === 'Enter') void refresh(); });
    $('admin-more').addEventListener('click', () => refresh(true));
    $('release-list').addEventListener('click', e => { const button = e.target.closest('[data-action]'); if (button && !button.disabled) void mutate(button.dataset.action, items[Number(button.dataset.index)]); });
    $('publisher-form').addEventListener('submit', e => { e.preventDefault(); void mutate('publisher', Object.fromEntries(new FormData(e.target))); });
    void refresh();
  });
})();
