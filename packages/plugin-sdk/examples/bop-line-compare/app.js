import { Ai00PluginClient } from './ai00-plugin-sdk.js';
import { compareRefs, searchOperationCandidates } from './compare-engine.js';
import {
  buildComparison, createTrace, loadBopChoices, loadBopStructure,
  loadLineContext, partsForOperation, searchProjects, toolsForOperation,
} from './bop-runtime.js';

const client = new Ai00PluginClient();
const trace = createTrace();
const state = {
  left: { generation: 0, project: null, bops: [], structure: null, lines: [], context: null, candidate: null },
  right: { generation: 0, project: null, bops: [], structure: null, lines: [], context: null, candidate: null },
  comparison: null,
  pair: null,
  view: 'process',
};
const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, character => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[character]));

function toast(message) {
  const node = $('#toast'); node.textContent = message; node.hidden = false;
  setTimeout(() => { node.hidden = true; }, 3200);
}

function setStatus(side, message, isError = false) {
  const node = $(`#${side}-status`); node.textContent = message; node.classList.toggle('error', isError);
}

function renderTrace() {
  $('#trace-list').innerHTML = trace.items.length ? trace.items.map(item => `
    <article class="trace-item ${item.status === 'failed' ? 'failed' : ''}">
      <strong>${esc(item.capability_id)}@${esc(item.major)}</strong>
      <span>${esc(item.purpose)}</span>
      <small>${esc(item.status)} · ${esc(item.duration_ms)} ms · ${esc(item.summary)}</small>
    </article>`).join('') : '<p class="empty">尚未调用 Capability</p>';
}

function resetAfterProject(side) {
  Object.assign(state[side], { bops: [], structure: null, lines: [], context: null, candidate: null });
  $(`#${side}-bop`).innerHTML = '<option value="">加载 BOP 中…</option>';
  $(`#${side}-bop`).disabled = true;
  $(`#${side}-line`).innerHTML = '<option value="">请先选择 BOP</option>';
  $(`#${side}-line`).disabled = true;
  clearComparison();
}

function clearComparison() {
  state.comparison = null; state.pair = null;
  $('#operation-query').disabled = !(state.left.context && state.right.context);
  $('#match-summary').textContent = state.left.context && state.right.context ? '左右线体已就绪' : '请先加载左右线体';
  $('#pair-banner').textContent = '请从自动对齐结果或左右搜索候选中选择一对操作。';
  ['left-process','right-process','left-parts','right-parts','left-tools','right-tools'].forEach(id => { $(`#${id}`).innerHTML = ''; });
}

async function runSide(side, work) {
  const generation = ++state[side].generation;
  try {
    const value = await work(generation);
    if (generation !== state[side].generation) return null;
    return value;
  } catch (error) {
    if (generation === state[side].generation) setStatus(side, `${error.code || 'error'}：${error.message}`, true);
    return null;
  } finally { renderTrace(); }
}

async function searchSide(side) {
  const query = $(`#${side}-project-query`).value.trim();
  if (!query) return toast('请输入项目名称或编码');
  setStatus(side, '搜索项目中…');
  const projects = await runSide(side, () => searchProjects(client, query, trace));
  if (!projects) return;
  const root = $(`#${side}-project-results`);
  root.innerHTML = projects.length ? projects.map((project, index) => `<button class="project-result" data-index="${index}"><strong>${esc(project.title)}</strong><small>${esc(project.object_ref)}</small></button>`).join('') : '<p class="empty">未找到可见项目</p>';
  root.querySelectorAll('button').forEach(button => button.addEventListener('click', () => selectProject(side, projects[Number(button.dataset.index)])));
  setStatus(side, `找到 ${projects.length} 个项目`);
}

async function selectProject(side, project) {
  state[side].project = project; resetAfterProject(side); setStatus(side, `已选择 ${project.title}，加载 BOP…`);
  const bops = await runSide(side, () => loadBopChoices(client, project.object_ref, trace));
  if (!bops) return;
  state[side].bops = bops;
  const select = $(`#${side}-bop`); select.disabled = false;
  select.innerHTML = '<option value="">选择 BOP 版本</option>' + bops.map(item => `<option value="${esc(item.version_gid)}">${esc(item.bop_name || 'BOP')} · ${esc(item.version_tag || item.revision || '')}</option>`).join('');
  setStatus(side, `已加载 ${bops.length} 个 BOP 版本`);
}

async function selectBop(side, versionGid) {
  state[side].context = null; state[side].candidate = null; clearComparison();
  if (!versionGid) return;
  setStatus(side, '读取正式执行结构…');
  const value = await runSide(side, () => loadBopStructure(client, versionGid, trace));
  if (!value) return;
  state[side].structure = value.structure; state[side].lines = value.lines;
  const select = $(`#${side}-line`); select.disabled = false;
  select.innerHTML = '<option value="">选择线体</option>' + value.lines.map(line => `<option value="${esc(line.node_id)}">${esc(line.name || line.node_id)}</option>`).join('');
  setStatus(side, `执行结构已受控发布，发现 ${value.lines.length} 条线体`);
}

async function selectLine(side, lineGid) {
  state[side].context = null; state[side].candidate = null; clearComparison();
  if (!lineGid) return;
  const versionGid = $(`#${side}-bop`).value; setStatus(side, '投影线体工作包…');
  const context = await runSide(side, () => loadLineContext(client, versionGid, lineGid, trace));
  if (!context) return;
  state[side].context = context; setStatus(side, `线体已就绪：${context.operations.length} 个操作`);
  if (state.left.context && state.right.context) {
    state.comparison = buildComparison(state.left.context, state.right.context);
    $('#operation-query').disabled = false;
    $('#match-summary').textContent = `${state.comparison.alignment.exact.length} 对 VPPS · ${state.comparison.alignment.fuzzy.length} 对描述候选`;
    renderAligned(false);
  }
}

function operationLabel(operation) {
  const vpps = operation?.parameters?.vpps || '无 VPPS';
  return `${operation?.name || operation?.operation_id} · ${vpps}`;
}

function choosePair(left, right, method, score = 1, reasons = []) {
  state.pair = { left, right, method, score, reasons };
  state.left.candidate = left; state.right.candidate = right;
  $('#pair-banner').textContent = `${method === 'vpps' ? 'VPPS 精确匹配' : method === 'manual' ? '手工选择' : '描述模糊匹配'}：${operationLabel(left)} ↔ ${operationLabel(right)}${method === 'description' ? ` · 相似度 ${Math.round(score * 100)}%` : ''}`;
  renderCurrentView(); renderManualCandidates($('#operation-query').value.trim());
}

function renderAligned(vppsOnly) {
  if (!state.comparison) return;
  const matches = vppsOnly ? state.comparison.alignment.exact : [...state.comparison.alignment.exact, ...state.comparison.alignment.fuzzy];
  $('#left-candidates').innerHTML = matches.length ? matches.map((match, index) => `<button class="candidate" data-index="${index}"><span><strong>${esc(operationLabel(match.left))}</strong><small>${esc(match.method === 'vpps' ? 'VPPS 精确' : `描述相似 ${Math.round(match.score * 100)}%`)}</small></span></button>`).join('') : '<p class="empty">没有匹配结果</p>';
  $('#right-candidates').innerHTML = matches.length ? matches.map(match => `<div class="candidate"><span><strong>${esc(operationLabel(match.right))}</strong><small>${esc(match.reasons.join('、'))}</small></span></div>`).join('') : '<p class="empty">没有匹配结果</p>';
  $('#left-candidates').querySelectorAll('button').forEach(button => button.addEventListener('click', () => { const match = matches[Number(button.dataset.index)]; choosePair(match.left, match.right, match.method, match.score, match.reasons); }));
  if (matches.length) choosePair(matches[0].left, matches[0].right, matches[0].method, matches[0].score, matches[0].reasons);
}

function renderManualCandidates(query) {
  if (!query || !state.left.context || !state.right.context) return;
  for (const side of ['left','right']) {
    const items = searchOperationCandidates(query, state[side].context.operations, 8);
    const root = $(`#${side}-candidates`);
    root.innerHTML = items.length ? items.map((item, index) => `<button class="candidate ${state[side].candidate?.operation_id === item.operation.operation_id ? 'selected' : ''}" data-index="${index}"><span><strong>${esc(item.operation.name)}</strong><small>${esc(item.operation.parameters?.vpps || '无 VPPS')} · ${Math.round(item.score * 100)}%</small></span></button>`).join('') : '<p class="empty">没有候选</p>';
    root.querySelectorAll('button').forEach(button => button.addEventListener('click', () => {
      state[side].candidate = items[Number(button.dataset.index)].operation;
      renderManualCandidates(query);
      if (state.left.candidate && state.right.candidate) choosePair(state.left.candidate, state.right.candidate, 'manual');
    }));
  }
}

function rows(values) {
  return values.map(([key, value]) => `<div class="detail-row"><span class="detail-key">${esc(key)}</span><span class="detail-value">${value}</span></div>`).join('');
}

function operationRows(operation) {
  if (!operation) return '<p class="empty">未选择操作</p>';
  return rows([
    ['操作名称', esc(operation.name || operation.operation_id)],
    ['VPPS', esc(operation.parameters?.vpps || '缺失')],
    ['顺序', esc(operation.sequence ?? '未提供')],
    ['所属节点', esc(operation.parameters?.parent_node_id || '未提供')],
    ['前置操作', esc((operation.predecessor_ids || []).join('、') || '无')],
    ['工艺参数', `<code>${esc(JSON.stringify(operation.parameters || {}))}</code>`],
  ]);
}

function partRows(context, operation) {
  const parts = partsForOperation(context, operation);
  if (!parts.length) return '<p class="empty">该操作没有关联零件</p>';
  return parts.map(part => `<span class="resource"><strong>${esc(part.part_no || part.part_gid)}</strong> · ${esc(part.name || '名称未提供')}<br><small>part:${esc(part.part_gid)}</small></span>`).join('');
}

function toolRows(operation) {
  const tools = toolsForOperation(operation);
  return tools.length ? tools.map(ref => `<span class="resource">${esc(ref)}<br><small>当前 Capability 未提供工具名称，展示受控引用</small></span>`).join('') : '<p class="empty">该操作没有关联工具</p>';
}

function renderCurrentView() {
  const pair = state.pair;
  $('#left-process').innerHTML = operationRows(pair?.left); $('#right-process').innerHTML = operationRows(pair?.right);
  $('#left-parts').innerHTML = partRows(state.left.context, pair?.left); $('#right-parts').innerHTML = partRows(state.right.context, pair?.right);
  $('#left-tools').innerHTML = toolRows(pair?.left); $('#right-tools').innerHTML = toolRows(pair?.right);
  const suffixes = { process: ['process-view','right-process-view'], parts: ['parts-view','right-parts-view'], tools: ['tools-view','right-tools-view'] };
  Object.entries(suffixes).forEach(([view, ids]) => ids.forEach(id => { $(`#${id}`).hidden = view !== state.view; }));
}

for (const side of ['left','right']) {
  $(`#${side}-project-search`).addEventListener('click', () => searchSide(side));
  $(`#${side}-project-query`).addEventListener('keydown', event => { if (event.key === 'Enter') searchSide(side); });
  $(`#${side}-bop`).addEventListener('change', event => selectBop(side, event.target.value));
  $(`#${side}-line`).addEventListener('change', event => selectLine(side, event.target.value));
}
$('#auto-align').addEventListener('click', () => renderAligned(false));
$('#vpps-only').addEventListener('click', () => renderAligned(true));
$('#operation-query').addEventListener('input', event => renderManualCandidates(event.target.value.trim()));
document.querySelectorAll('.tab').forEach(button => button.addEventListener('click', () => {
  state.view = button.dataset.view;
  document.querySelectorAll('.tab').forEach(tab => { tab.classList.toggle('active', tab === button); tab.setAttribute('aria-selected', tab === button ? 'true' : 'false'); });
  renderCurrentView();
}));

try {
  await client.ready(); $('#connection').textContent = 'Mount 已连接';
} catch (error) {
  $('#connection').textContent = '平台连接失败'; toast(error.message);
}
