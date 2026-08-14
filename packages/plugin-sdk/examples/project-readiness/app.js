import { Ai00PluginClient } from './ai00-plugin-sdk.js';
import { loadHistory, runReadinessCheck, saveHistory } from './readiness-runtime.js';

const client = new Ai00PluginClient();
const labels = { ready:'就绪', attention:'需关注', blocked:'阻塞', inaccessible:'无权限或服务异常', ok:'正常' };
const domainNames = { project:'项目', craft:'工艺', digital_model:'数模', simulation:'仿真' };
let selected = null; let requestGeneration = 0;
const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));

function capabilityData(result) {
  if (!result?.ok || result.status !== 'completed') throw new Error(result?.error?.message || result?.error?.code || '能力调用失败');
  return result.data;
}
function toast(message) { const node=$('#toast');node.textContent=message;node.hidden=false;setTimeout(()=>{node.hidden=true;},3500); }
function reportStatus(status) { return labels[status] || status; }

async function searchProjects() {
  const query=$('#project-query').value.trim(); if(!query){toast('请输入项目名称或编码');return;}
  const button=$('#project-search');button.disabled=true;
  try { const data=capabilityData(await client.invoke('base.project.search',{query,limit:20})); const root=$('#project-results'); root.innerHTML=(data.items||[]).map((item,index)=>`<button class="project-result" data-index="${index}"><strong>${esc(item.title)}</strong><small>${esc(item.object_ref)} · ${esc(item.summary||'')}</small></button>`).join('')||'<div class="empty">没有找到可见项目</div>'; root.querySelectorAll('.project-result').forEach(node=>node.addEventListener('click',()=>selectProject(data.items[Number(node.dataset.index)]))); }
  catch(error){toast(error.message);} finally{button.disabled=false;}
}
function selectProject(project){requestGeneration+=1;selected=project;$('#selected-title').textContent=project.title;$('#selected-ref').textContent=project.object_ref;$('#selected-project').hidden=false;}

function renderReport(report){
  $('#report').hidden=false; const overall=$('#overall');overall.className=`overall ${report.overall_status}`;overall.innerHTML=`<h2>${reportStatus(report.overall_status)}</h2><div>检查时间：${esc(report.checked_at)}</div>`;
  $('#domains').innerHTML=Object.entries(report.domains).map(([key,item])=>`<article class="domain-card ${esc(item.status)}"><h3>${domainNames[key]||key}</h3><strong>${reportStatus(item.status)}</strong><p>${esc(item.error || (item.matching!=null?`精确匹配 ${item.matching} 项`:item.total!=null?`共 ${item.total} 项`:'已获得受控引用'))}</p></article>`).join('');
  $('#evidence-list').innerHTML=Object.entries(report.evidence_refs).filter(([,value])=>value).map(([key,value])=>`<dt>${esc(key)}</dt><dd>${esc(value)}</dd>`).join('')||'<div class="empty">暂无可用关联证据</div>';
  const suggestions=[];
  if(report.domains.craft?.status==='blocked')suggestions.push('发布至少一个可执行 BOP，并确认它已归属当前项目。');
  if(report.domains.digital_model?.status==='blocked')suggestions.push('为当前项目模型创建最新的不可变数模快照。');
  if(report.domains.simulation?.status==='blocked')suggestions.push('使用上方工艺提交引用和数模快照哈希创建仿真环境并启动运行。');
  if(report.overall_status==='attention')suggestions.push('检查匹配仿真的排队、运行或失败详情，完成后重新体检。');
  if(report.overall_status==='inaccessible')suggestions.push('联系管理员检查插件授权、Mount 会话及对应领域 Provider。');
  if(!suggestions.length)suggestions.push('四域引用一致，项目可进入下一阶段。');
  $('#recommendations').innerHTML=suggestions.map(item=>`<li>${esc(item)}</li>`).join('');
}
async function runCheck(){if(!selected)return;const generation=++requestGeneration;const button=$('#run-check');button.disabled=true;button.textContent='体检中…';try{const report=await runReadinessCheck(client,selected);if(generation!==requestGeneration)return;renderReport(report);await saveHistory(client,report);await renderHistory();}catch(error){if(generation===requestGeneration)toast(error.message);}finally{if(generation===requestGeneration){button.disabled=false;button.textContent='开始体检';}}}
async function renderHistory(){try{const items=await loadHistory(client);$('#history-list').innerHTML=items.map(item=>`<div class="history-item"><div><strong>${esc(item.project?.title||item.project?.object_ref||'未知项目')}</strong><small>${esc(item.checked_at||'')}</small></div><div class="status-pill ${esc(item.overall_status)}"><span>${reportStatus(item.overall_status)}</span></div></div>`).join('')||'<div class="empty">暂无记录</div>';}catch(error){$('#history-list').innerHTML=`<div class="empty">${esc(error.message)}</div>`;}}

$('#project-search').addEventListener('click',searchProjects);$('#project-query').addEventListener('keydown',event=>{if(event.key==='Enter')searchProjects();});$('#run-check').addEventListener('click',runCheck);$('#history-refresh').addEventListener('click',renderHistory);
try{await client.ready();$('#connection').textContent='已连接受控插件运行时';await renderHistory();}catch(error){$('#connection').textContent='平台连接失败';toast(error.message);}
