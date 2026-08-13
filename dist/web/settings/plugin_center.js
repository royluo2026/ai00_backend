/** Lightweight server-backed plugin center. */
(() => {
  let catalog = [];
  let installed = [];
  let metrics = new Map();
  let canManage = false;

  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const errorText = (result, fallback='操作失败') => {
    const detail = result?.detail || result?.msg;
    return typeof detail === 'string' ? detail : (detail?.message || detail?.code || fallback);
  };
  const lastMonth = () => {
    const now = new Date();
    const value = new Date(now.getFullYear(), now.getMonth(), 0);
    return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}`;
  };

  async function invoke(capabilityId, payload) {
    const headers = {'X-AI00-Source':'web'};
    const confirmed = await _backendFetch(`/api/v1/capabilities/${encodeURIComponent(capabilityId)}:confirm`, {method:'POST', headers, body:JSON.stringify({payload})});
    if (!confirmed.success) throw new Error(errorText(confirmed));
    const result = await _backendFetch(`/api/v1/capabilities/${encodeURIComponent(capabilityId)}:invoke`, {method:'POST', headers, body:JSON.stringify({payload, confirmation_token:confirmed.data?.confirmation_token})});
    if (!result.success) throw new Error(errorText(result));
  }

  async function upload(formData) {
    const config = (await window.electronAPI?.getConfig?.()) || {};
    const state = (await window.electronAPI?.authGetState?.()) || {};
    const runtimeBase = await window.AI00RuntimeConfig?.getRuntimeBackendBase?.(config.backendUrl || '');
    const base = (runtimeBase || config.backendUrl || '').replace(/\/$/, '');
    const token = String(state.token || localStorage.getItem('ai00_token') || '').trim();
    if (!token) throw new Error('未登录');
    const response = await fetch(`${base}/api/v1/plugin-marketplace/releases`, {method:'POST', headers:{'X-AI00-Token':token}, body:formData});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(errorText(data, `HTTP ${response.status}`));
  }

  const metric = id => metrics.get(id) || {current_usage:0,previous_usage:0,monthly_delta:0,success_rate:0};
  function metricHtml(id) {
    const item = metric(id); const delta = Number(item.monthly_delta || 0);
    return `<div class="pm-metrics"><span>本月 <b>${item.current_usage || 0}</b></span><span>上月 <b>${item.previous_usage || 0}</b></span><span>增量 <b class="${delta > 0 ? 'positive' : delta < 0 ? 'negative' : ''}">${delta > 0 ? '+' : ''}${delta}</b></span><span>成功率 <b>${(Number(item.success_rate || 0) * 100).toFixed(1)}%</b></span></div>`;
  }
  function latestCatalog() {
    const result = new Map();
    catalog.forEach(item => { if (!result.has(item.plugin_id)) result.set(item.plugin_id, item); });
    return [...result.values()];
  }

  function renderAvailable() {
    const root = document.getElementById('pm-available-list'); if (!root) return;
    const active = new Map(installed.filter(x => x.state !== 'uninstalled').map(x => [x.plugin_id, x]));
    const rows = latestCatalog();
    if (!rows.length) { root.innerHTML='<div class="empty-state">暂无已发布插件</div>'; return; }
    root.innerHTML = rows.map(item => {
      const manifest=item.manifest || {}; const current=active.get(item.plugin_id);
      let action='<span class="pm-state">已安装</span>';
      if (!current && !canManage) action='<span class="pm-state">可用</span>';
      else if (!current) action=`<button class="btn-primary pc-catalog-action" data-action="install" data-plugin="${esc(item.plugin_id)}" data-version="${esc(item.version)}">安装</button>`;
      else if (current.current_version !== item.version && !['upgrading','revoked'].includes(current.state)) action=`<button class="btn-secondary pc-catalog-action" data-action="upgrade" data-plugin="${esc(item.plugin_id)}" data-version="${esc(item.version)}">更新</button>`;
      return `<div class="pm-card"><div class="pm-card-main"><div class="pm-card-title">${esc(manifest.name || item.plugin_id)} <small>v${esc(item.version)}</small></div><div class="pm-card-desc">${esc(manifest.description || '暂无说明')}</div>${metricHtml(item.plugin_id)}</div><div>${action}</div></div>`;
    }).join('');
    root.querySelectorAll('.pc-catalog-action').forEach(btn => btn.addEventListener('click', () => catalogAction(btn)));
  }

  function renderInstalled() {
    const root=document.getElementById('pm-installed-list'); if (!root) return;
    const rows=installed.filter(x => x.state !== 'uninstalled');
    if (!rows.length) { root.innerHTML='<div class="empty-state">当前团队尚未安装插件</div>'; return; }
    root.innerHTML=rows.map(item => {
      const actions=[];
      if (!canManage) return `<div class="pm-card"><div class="pm-card-main"><div class="pm-card-title">${esc(item.name || item.plugin_id)} <small>v${esc(item.current_version)}</small> <span class="pm-state">${esc(item.state)}</span></div><div class="pm-card-desc">权限：${(item.granted_capabilities || []).map(esc).join('、') || '无'}</div>${metricHtml(item.plugin_id)}</div></div>`;
      if (['disabled','failed','rolled_back'].includes(item.state)) actions.push(['enable','启用']);
      if (['enabled','rolled_back'].includes(item.state)) actions.push(['disable','停用']);
      if (['disabled','revoked'].includes(item.state)) actions.push(['uninstall','卸载']);
      if (['upgrading','failed'].includes(item.state) && item.previous_version) actions.push(['rollback','回滚']);
      if (item.state === 'upgrading') actions.push(['upgrade.finish','验证通过']);
      return `<div class="pm-card"><div class="pm-card-main"><div class="pm-card-title">${esc(item.name || item.plugin_id)} <small>v${esc(item.current_version)}</small> <span class="pm-state">${esc(item.state)}</span></div><div class="pm-card-desc">权限：${(item.granted_capabilities || []).map(esc).join('、') || '无'}</div>${metricHtml(item.plugin_id)}</div><div class="pm-card-actions">${actions.map(([action,label])=>`<button class="btn-secondary pc-installed-action" data-action="${action}" data-plugin="${esc(item.plugin_id)}">${label}</button>`).join('')}</div></div>`;
    }).join('');
    root.querySelectorAll('.pc-installed-action').forEach(btn => btn.addEventListener('click', () => installedAction(btn)));
  }

  async function catalogAction(btn) {
    const item=catalog.find(x => x.plugin_id===btn.dataset.plugin && x.version===btn.dataset.version); if (!item) return;
    const label=btn.dataset.action==='install'?'安装':'更新';
    if (!confirm(`确认${label}「${item.manifest?.name || item.plugin_id}」？\n将授权：${(item.manifest?.permissions || []).join('、') || '无额外能力'}`)) return;
    btn.disabled=true;
    try { await invoke(`plugin.${btn.dataset.action}`, {plugin_id:item.plugin_id,version:item.version,granted_capabilities:item.manifest?.permissions || []}); await load(); }
    catch (error) { alert(error.message); btn.disabled=false; }
  }
  async function installedAction(btn) {
    if (!confirm(`确认${btn.textContent.trim()}插件「${btn.dataset.plugin}」？`)) return;
    btn.disabled=true;
    const payload=btn.dataset.action==='upgrade.finish'?{plugin_id:btn.dataset.plugin,healthy:true}:{plugin_id:btn.dataset.plugin};
    try { await invoke(`plugin.${btn.dataset.action}`,payload); await load(); }
    catch (error) { alert(error.message); btn.disabled=false; }
  }

  async function loadReviews() {
    const root=document.getElementById('pm-review-list'); if (!root) return;
    const result=await _backendFetch('/api/v1/plugin-marketplace/releases?status=submitted');
    if (!result.success) { root.innerHTML=`<div class="empty-state">${esc(errorText(result,'仅管理员可查看'))}</div>`; return; }
    const rows=result.data || [];
    if (!rows.length) { root.innerHTML='<div class="empty-state">没有待审核版本</div>'; return; }
    root.innerHTML=rows.map(item=>`<div class="pm-card"><div class="pm-card-main"><div class="pm-card-title">${esc(item.manifest?.name || item.plugin_id)} <small>v${esc(item.version)}</small></div><div class="pm-card-desc">发布者：${esc(item.publisher_id)} · SHA-256：${esc(item.artifact_sha256)}</div></div><div class="pm-card-actions"><button class="btn-primary pc-review" data-approved="true" data-plugin="${esc(item.plugin_id)}" data-version="${esc(item.version)}">批准</button><button class="btn-secondary pc-review" data-approved="false" data-plugin="${esc(item.plugin_id)}" data-version="${esc(item.version)}">拒绝</button></div></div>`).join('');
    root.querySelectorAll('.pc-review').forEach(btn=>btn.addEventListener('click',()=>review(btn)));
  }
  async function review(btn) {
    const approved=btn.dataset.approved==='true';
    const note=approved?'管理员审核通过':(prompt('请输入拒绝原因') || '管理员拒绝');
    if (approved && !confirm(`确认发布 ${btn.dataset.plugin} v${btn.dataset.version}？`)) return;
    btn.disabled=true;
    const result=await _backendFetch(`/api/v1/plugin-marketplace/releases/${encodeURIComponent(btn.dataset.plugin)}/${encodeURIComponent(btn.dataset.version)}/review`,{method:'POST',body:JSON.stringify({approved,note})});
    if (!result.success) { alert(errorText(result)); btn.disabled=false; return; }
    await load(); await loadReviews();
  }

  async function load() {
    const month=lastMonth();
    const [available,installations,usage]=await Promise.all([_backendFetch('/api/v1/plugin-marketplace/catalog'),_backendFetch('/api/v1/plugin-marketplace/installations'),_backendFetch(`/api/v1/plugin-marketplace/usage/months/${month}`)]);
    catalog=available.success?(available.data || []):[];
    installed=installations.success?(installations.data || []):[];
    metrics=new Map((usage.success?(usage.data?.items || []):[]).map(x=>[x.plugin_id,x]));
    const label=document.getElementById('pm-month-label'); if (label) label.textContent=`${month} 月度使用情况`;
    renderAvailable(); renderInstalled();
  }

  async function init() {
    const panel=document.getElementById('panel-plugin-market'); if (!panel || panel.dataset.centerInitialized) return;
    panel.dataset.centerInitialized='true';
    const access=await _backendFetch('/api/v1/plugin-marketplace/releases?status=submitted');
    canManage=access.success;
    const uploadTab=panel.querySelector('.pm-tab[data-tab="upload"]'); if (uploadTab) uploadTab.hidden=!canManage;
    panel.querySelectorAll('.pm-tab').forEach(tab=>tab.addEventListener('click',async()=>{
      panel.querySelectorAll('.pm-tab').forEach(x=>x.classList.toggle('active',x===tab));
      panel.querySelectorAll('.pm-pane').forEach(x=>{x.hidden=x.id!==`pm-pane-${tab.dataset.tab}`;});
      if (tab.dataset.tab==='upload') await loadReviews();
    }));
    document.getElementById('pm-btn-refresh')?.addEventListener('click',load);
    document.getElementById('pm-btn-upload')?.addEventListener('click',async()=>{
      const zip=document.getElementById('pm-package')?.files?.[0];
      const manifest=document.getElementById('pm-manifest-file')?.files?.[0];
      const signature=document.getElementById('pm-publisher-signature')?.value?.trim();
      const feedback=document.getElementById('pm-upload-feedback');
      if (!zip || !manifest || !signature) { feedback.textContent='请选择 ZIP、manifest 并填写签名'; return; }
      try { const form=new FormData(); form.append('package',zip); form.append('manifest_json',await manifest.text()); form.append('publisher_signature',signature); feedback.textContent='校验并上传中...'; await upload(form); feedback.textContent='已提交审核'; await loadReviews(); }
      catch (error) { feedback.textContent=error.message; }
    });
    document.getElementById('pm-btn-close-month')?.addEventListener('click',async()=>{
      const month=lastMonth(); const result=await _backendFetch(`/api/v1/plugin-marketplace/usage/months/${month}/close`,{method:'POST',body:'{}'});
      if (!result.success) { alert(errorText(result)); return; }
      alert(result.data?.already_closed?`${month} 已生成且不可修改`:`${month} 月度快照已生成`); await load();
    });
    await load();
  }
  document.addEventListener('DOMContentLoaded',init);
})();