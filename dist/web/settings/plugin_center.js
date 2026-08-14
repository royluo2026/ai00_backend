/** Server-backed Capability V2 plugin center controller. */
(() => {
  'use strict';
  const model = window.AI00PluginCenterModel;
  const apiFactory = window.AI00PluginCenterApi;
  if (!model || !apiFactory) return;

  const state = { catalog: [], installed: [], metrics: [], canManage: false, error: null, loading: false, query: '', filterState: '' };
  const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[ch]));
  const labels = { available:'未安装', disabled:'已停用', enabled:'已启用', upgrading:'更新中', failed:'失败', rolled_back:'已回滚', revoked:'已撤销' };
  const actionLabels = { install:'安装', upgrade:'更新', enable:'启用', disable:'停用', uninstall:'卸载', rollback:'回滚', 'upgrade.finish':'验证通过' };
  const lastMonth = () => { const now = new Date(); const value = new Date(now.getFullYear(), now.getMonth(), 0); return `${value.getFullYear()}-${String(value.getMonth()+1).padStart(2,'0')}`; };
  let client;
  let dialogResolve = null;

  function toast(message, type = '') {
    const root = document.getElementById('pm-toast-region');
    const item = document.createElement('div'); item.className = `pm-toast ${type}`; item.textContent = message; root?.appendChild(item);
    setTimeout(() => item.remove(), 3600);
  }

  function ask({ title, message, input = false, confirmText = '确认' }) {
    const mask = document.getElementById('pm-dialog'); const field = document.getElementById('pm-dialog-input');
    document.getElementById('pm-dialog-title').textContent = title;
    document.getElementById('pm-dialog-message').textContent = message;
    document.getElementById('pm-dialog-confirm').textContent = confirmText;
    field.hidden = !input; field.value = ''; mask.hidden = false;
    if (input) setTimeout(() => field.focus(), 0);
    return new Promise(resolve => { dialogResolve = resolve; });
  }
  function closeDialog(confirmed) {
    const mask = document.getElementById('pm-dialog'); const field = document.getElementById('pm-dialog-input');
    mask.hidden = true; const resolve = dialogResolve; dialogResolve = null;
    resolve?.(confirmed ? (field.hidden ? true : field.value.trim()) : null);
  }

  const metricMap = () => new Map((state.metrics || []).map(item => [item.plugin_id, item]));
  function metricHtml(pluginId) {
    const item = metricMap().get(pluginId) || { current_usage:0, previous_usage:0, monthly_delta:0, success_rate:0 };
    const delta = Number(item.monthly_delta || 0);
    return `<div class="pm-metrics"><span>本月 <b>${item.current_usage || 0}</b></span><span>上月 <b>${item.previous_usage || 0}</b></span><span>增量 <b class="${delta>0?'positive':delta<0?'negative':''}">${delta>0?'+':''}${delta}</b></span><span>成功率 <b>${(Number(item.success_rate || 0)*100).toFixed(1)}%</b></span></div>`;
  }

  function combinedCatalog() {
    const active = new Map(state.installed.filter(item => item.state !== 'uninstalled').map(item => [item.plugin_id, item]));
    return model.latestCatalog(state.catalog).map(release => {
      const installation = active.get(release.plugin_id); const manifest = release.manifest || {};
      return { ...release, ...manifest, installation, state: installation?.state || 'available', current_version: installation?.current_version };
    });
  }

  function card(item, installedView = false) {
    const installation = item.installation || item;
    const permissions = installation.granted_capabilities || item.permissions || item.manifest?.permissions || [];
    const actions = installedView ? model.actionsForInstallation(installation, state.canManage) : [];
    if (!installedView && state.canManage && item.state === 'available') actions.push('install');
    if (!installedView && state.canManage && item.installation && item.current_version !== item.version && !['upgrading','revoked'].includes(item.state)) actions.push('upgrade');
    return `<article class="pm-card" tabindex="0" data-plugin="${esc(item.plugin_id)}" data-version="${esc(item.version || item.current_version)}"><div class="pm-card-main"><div class="pm-card-title">${esc(item.name || item.plugin_id)} <small>v${esc(item.version || item.current_version)}</small> <span class="pm-state">${esc(labels[item.state] || item.state)}</span></div><div class="pm-card-desc">${esc(item.description || (permissions.length ? `权限：${permissions.join('、')}` : '暂无说明'))}</div>${metricHtml(item.plugin_id)}</div><div class="pm-card-actions">${actions.map(action => `<button class="${action==='install'?'btn-primary':'btn-secondary'} pc-action" data-action="${action}">${actionLabels[action]}</button>`).join('')}</div></article>`;
  }

  function bindCards(root, installedView) {
    root.querySelectorAll('.pm-card').forEach(el => {
      const open = event => { if (!event.target.closest('button')) openDetail(el.dataset.plugin, el.dataset.version); };
      el.addEventListener('click', open); el.addEventListener('keydown', event => { if (event.key === 'Enter') open(event); });
      el.querySelectorAll('.pc-action').forEach(button => button.addEventListener('click', event => { event.stopPropagation(); runAction(button, el.dataset.plugin, el.dataset.version); }));
    });
  }

  function render() {
    const error = document.getElementById('pm-load-error'); error.hidden = !state.error; error.textContent = state.error ? `${state.error}；已保留上次成功数据。` : '';
    const available = model.filterPlugins(combinedCatalog(), { query:state.query, state:state.filterState });
    const availableRoot = document.getElementById('pm-available-list');
    availableRoot.innerHTML = state.loading && !state.catalog.length ? '<div class="empty-state">正在加载插件目录...</div>' : (available.map(item => card(item)).join('') || '<div class="empty-state">没有符合条件的插件</div>');
    bindCards(availableRoot, false);
    const installed = model.filterPlugins(state.installed.filter(item => item.state !== 'uninstalled').map(item => ({ ...item, description:`权限：${(item.granted_capabilities || []).join('、') || '无'}` })), { query:state.query, state:state.filterState });
    const installedRoot = document.getElementById('pm-installed-list');
    installedRoot.innerHTML = installed.map(item => card(item, true)).join('') || '<div class="empty-state">当前团队没有符合条件的已安装插件</div>';
    bindCards(installedRoot, true);
  }

  async function refresh() {
    state.loading = true; render();
    try { Object.assign(state, model.reduceLoad(state, { ok:true, ...(await client.loadAll(lastMonth())) })); }
    catch (error) { Object.assign(state, model.reduceLoad(state, { ok:false, error:error.message })); toast(error.message, 'error'); }
    render();
  }

  async function runAction(button, pluginId, version) {
    if (button.disabled) return;
    const action = button.dataset.action; const item = state.catalog.find(value => value.plugin_id===pluginId && value.version===version);
    const permissions = item?.manifest?.permissions || [];
    const message = action==='install' || action==='upgrade' ? `将授权：${permissions.join('、') || '无额外能力'}` : `将${actionLabels[action]}插件 ${pluginId}`;
    if (!await ask({ title:`确认${actionLabels[action]}`, message, confirmText:actionLabels[action] })) return;
    button.disabled = true;
    try {
      const payload = action==='install' || action==='upgrade' ? { plugin_id:pluginId, version, granted_capabilities:permissions } : { plugin_id:pluginId };
      if (action === 'upgrade.finish') await client.finishUpgrade(pluginId, true);
      else await client.invokeLifecycle(`plugin.${action}`, payload);
      toast(`${actionLabels[action]}成功`); await refresh();
    } catch (error) { toast(error.message, 'error'); button.disabled = false; }
  }

  async function openDetail(pluginId, version) {
    const release = state.catalog.find(item => item.plugin_id===pluginId && (!version || item.version===version)) || state.catalog.find(item => item.plugin_id===pluginId);
    const installation = state.installed.find(item => item.plugin_id===pluginId && item.state!=='uninstalled'); const manifest = release?.manifest || {};
    const body = document.getElementById('pm-detail-body'); document.getElementById('pm-detail-title').textContent = manifest.name || installation?.name || pluginId;
    body.innerHTML = `<section class="pm-detail-section"><h4>版本与状态</h4><div>发布版本：${esc(release?.version || '—')} · 当前版本：${esc(installation?.current_version || '未安装')} · ${esc(labels[installation?.state] || installation?.state || '未安装')}</div>${installation?.previous_version?`<div>上一版本：${esc(installation.previous_version)}</div>`:''}${installation?.last_error?`<div class="pm-load-error">${esc(installation.last_error)}</div>`:''}</section><section class="pm-detail-section"><h4>说明</h4><div>${esc(manifest.description || '暂无说明')}</div><div class="pm-hint">发布者：${esc(release?.publisher_id || installation?.publisher_id || '—')}</div></section><section class="pm-detail-section"><h4>授权能力</h4><div class="pm-capability-list">${(installation?.granted_capabilities || manifest.permissions || []).map(value=>`<span class="pm-capability">${esc(value)}</span>`).join('') || '无'}</div></section><section class="pm-detail-section"><h4>月度指标</h4>${metricHtml(pluginId)}</section><section class="pm-detail-section"><h4>生命周期</h4><div id="pm-detail-events" class="pm-hint">${state.canManage && installation?'加载中...':'仅管理员可查看生命周期记录'}</div></section>`;
    document.getElementById('pm-detail-drawer').classList.add('open'); document.getElementById('pm-detail-drawer').setAttribute('aria-hidden','false'); document.getElementById('pm-drawer-mask').hidden=false;
    if (state.canManage && installation) {
      try { const events=await client.events(pluginId); document.getElementById('pm-detail-events').innerHTML=events.length?`<ul class="pm-timeline">${events.map(event=>`<li><strong>${esc(labels[event.to_state] || event.to_state)}</strong><div>${esc(event.created_at || '')} · ${esc(event.actor_gid || '')}</div></li>`).join('')}</ul>`:'暂无生命周期记录'; }
      catch (error) { document.getElementById('pm-detail-events').textContent=error.message; }
    }
  }
  function closeDetail() { document.getElementById('pm-detail-drawer').classList.remove('open'); document.getElementById('pm-detail-drawer').setAttribute('aria-hidden','true'); document.getElementById('pm-drawer-mask').hidden=true; }

  async function loadReviews() {
    const root=document.getElementById('pm-review-list');
    try { const rows=await client.releases('submitted'); root.innerHTML=rows.map(item=>`<div class="pm-card"><div class="pm-card-main"><div class="pm-card-title">${esc(item.manifest?.name || item.plugin_id)} <small>v${esc(item.version)}</small></div><div class="pm-card-desc">发布者：${esc(item.publisher_id)} · SHA-256：${esc(item.artifact_sha256)}</div></div><div class="pm-card-actions"><button class="btn-primary pc-review" data-approved="true" data-plugin="${esc(item.plugin_id)}" data-version="${esc(item.version)}">批准</button><button class="btn-secondary pc-review" data-approved="false" data-plugin="${esc(item.plugin_id)}" data-version="${esc(item.version)}">拒绝</button></div></div>`).join('') || '<div class="empty-state">没有待审核版本</div>'; root.querySelectorAll('.pc-review').forEach(button=>button.addEventListener('click',()=>review(button))); }
    catch (error) { root.innerHTML=`<div class="pm-load-error">${esc(error.message)}</div>`; }
  }
  async function review(button) {
    const approved=button.dataset.approved==='true'; const note=await ask({ title:approved?'批准发布':'拒绝发布', message:`${button.dataset.plugin} v${button.dataset.version}`, input:!approved, confirmText:approved?'批准':'拒绝' }); if (!note) return;
    button.disabled=true; try { await client.review(button.dataset.plugin,button.dataset.version,approved,approved?'管理员审核通过':note); toast(approved?'已批准发布':'已拒绝发布'); await loadReviews(); await refresh(); } catch(error){toast(error.message,'error');button.disabled=false;}
  }

  async function upload(formData) {
    const config=(await window.electronAPI?.getConfig?.())||{}; const auth=(await window.electronAPI?.authGetState?.())||{}; const runtime=await window.AI00RuntimeConfig?.getRuntimeBackendBase?.(config.backendUrl||''); const base=(runtime||config.backendUrl||'').replace(/\/$/,''); const token=String(auth.token||localStorage.getItem('ai00_token')||'').trim(); if(!token)throw new Error('未登录');
    const response=await fetch(`${base}/api/v1/plugin-marketplace/releases`,{method:'POST',headers:{'X-AI00-Token':token},body:formData}); const data=await response.json().catch(()=>({})); if(!response.ok)throw new Error(apiFactory.errorText(data,`HTTP ${response.status}`)); return data;
  }

  async function init() {
    const panel=document.getElementById('panel-plugin-market'); if(!panel||panel.dataset.centerInitialized)return; panel.dataset.centerInitialized='true'; client=apiFactory.createPluginCenterApi({backendFetch:window._backendFetch});
    try { const access=await client.access(); state.canManage=access.canManage; } catch(error){state.canManage=false;toast(error.message,'error');}
    panel.querySelector('.pm-tab[data-tab="upload"]').hidden=!state.canManage;
    panel.querySelectorAll('.pm-tab').forEach(tab=>tab.addEventListener('click',async()=>{panel.querySelectorAll('.pm-tab').forEach(item=>item.classList.toggle('active',item===tab));panel.querySelectorAll('.pm-pane').forEach(item=>{item.hidden=item.id!==`pm-pane-${tab.dataset.tab}`;});if(tab.dataset.tab==='upload')await loadReviews();}));
    document.getElementById('pm-search').addEventListener('input',event=>{state.query=event.target.value;render();}); document.getElementById('pm-state-filter').addEventListener('change',event=>{state.filterState=event.target.value;render();}); document.getElementById('pm-btn-refresh').addEventListener('click',refresh);
    document.getElementById('pm-detail-close').addEventListener('click',closeDetail); document.getElementById('pm-drawer-mask').addEventListener('click',closeDetail); document.getElementById('pm-dialog-cancel').addEventListener('click',()=>closeDialog(false)); document.getElementById('pm-dialog-confirm').addEventListener('click',()=>closeDialog(true));
    document.getElementById('pm-btn-upload')?.addEventListener('click',async()=>{const zip=document.getElementById('pm-package')?.files?.[0];const manifest=document.getElementById('pm-manifest-file')?.files?.[0];const signature=document.getElementById('pm-publisher-signature')?.value?.trim();const feedback=document.getElementById('pm-upload-feedback');if(!zip||!manifest||!signature){feedback.textContent='请选择 ZIP、manifest 并填写签名';return;}try{const form=new FormData();form.append('package',zip);form.append('manifest_json',await manifest.text());form.append('publisher_signature',signature);feedback.textContent='校验并上传中...';await upload(form);feedback.textContent='已提交审核';await loadReviews();}catch(error){feedback.textContent=error.message;}});
    document.getElementById('pm-btn-close-month')?.addEventListener('click',async()=>{if(!await ask({title:'生成月度快照',message:`确认关闭 ${lastMonth()} 月使用数据？`}))return;try{const result=await client.closeMonth(lastMonth());toast(result?.already_closed?'该月快照已存在':'月度快照已生成');await refresh();}catch(error){toast(error.message,'error');}});
    document.getElementById('pm-month-label').textContent=`${lastMonth()} 月度使用情况`; await refresh();
  }
  document.addEventListener('DOMContentLoaded',init);
})();
