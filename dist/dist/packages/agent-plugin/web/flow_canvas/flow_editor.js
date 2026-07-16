'use strict';
/**
 * Flow Canvas Editor — flow_editor.js
 * 基于 Drawflow.js 的流程编辑器
 * 读取 URL 参数 flow_gid，加载/保存 .flowdef YAML
 */

// ── API 调用 ──────────────────────────────────────────────────────────────────
const _cf  = () => window.parent?._cloudFetch || window._cloudFetch || null;

async function _apiCall(path, opts = {}) {
  const fn = _cf();
  if (!fn) throw new Error('云端服务未连接');
  return fn(path, opts);
}

// ── 状态 ─────────────────────────────────────────────────────────────────────
let _drawflow   = null;
let _flowGid    = null;
let _flowData   = null;  // {gid, name, flowdef, ...}
let _manifest   = [];    // 节点能力清单
let _selectedNode = null;
let _runGid     = null;
let _pollTimer  = null;
let _stepMode   = false;
let _pendingScriptNodeId = null;

const CATEGORY_COLORS = {
  data: 'cat-data', logic: 'cat-logic', notify: 'cat-notify',
  ai: 'cat-ai', script: 'cat-script', approval: 'cat-approval',
};
const CATEGORY_LABELS = {
  data: '数据', logic: '逻辑', notify: '通知', ai: 'AI', script: '脚本', approval: '审批',
};

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  _applyTheme();
  _bindButtons();

  const params = new URLSearchParams(location.search);
  _flowGid = params.get('flow_gid') || null;

  // Init Drawflow
  const el = document.getElementById('feDrawflow');
  _drawflow = new Drawflow(el);
  _drawflow.reroute = true;
  _drawflow.start();

  // Events
  _drawflow.on('nodeSelected', id => _onNodeSelected(id));
  _drawflow.on('nodeUnselected', () => _closeConfigPanel());
  _drawflow.on('nodeRemoved', () => _markDirty());
  _drawflow.on('connectionCreated', () => _markDirty());
  _drawflow.on('connectionRemoved', () => _markDirty());

  // Load manifest
  try {
    const res = await _apiCall('/api/flows/capability-manifest');
    _manifest = res?.manifest || [];
  } catch (e) {
    console.warn('[FlowEditor] manifest 加载失败:', e);
  }

  _renderNodePanel();

  if (_flowGid) {
    await _loadFlow(_flowGid);
  } else {
    // 新流程
    _flowData = { gid: null, name: '新建流程', description: '', flowdef: '', status: 'draft' };
    document.getElementById('feFlowName').value = '';
    document.getElementById('feFlowIntent').value = '';
    _setSaveStatus('未保存');
  }

  // Drag-and-drop from sidebar
  el.addEventListener('dragover', e => e.preventDefault());
  el.addEventListener('drop', e => _onCanvasDrop(e));

  // 主题同步
  window.addEventListener('message', e => {
    if (e.data?.type === 'theme') _applyTheme(e.data.theme);
  });
});

function _applyTheme(t) {
  const theme = t || localStorage.getItem('system.theme') || 'light';
  document.documentElement.setAttribute('data-theme', theme);
}

// ── 节点类型面板 ──────────────────────────────────────────────────────────────
function _renderNodePanel() {
  const list = document.getElementById('feNodeList');
  if (!list) return;
  list.innerHTML = '';

  // 按类别分组
  const groups = {};
  _manifest.forEach(m => {
    if (!groups[m.category]) groups[m.category] = [];
    groups[m.category].push(m);
  });

  const catOrder = ['data', 'logic', 'notify', 'ai', 'script', 'approval'];
  catOrder.concat(Object.keys(groups).filter(c => !catOrder.includes(c))).forEach(cat => {
    const items = groups[cat];
    if (!items?.length) return;

    const catEl = document.createElement('div');
    catEl.className = 'fe-node-category';
    catEl.textContent = CATEGORY_LABELS[cat] || cat;
    list.appendChild(catEl);

    items.forEach(m => {
      const el = document.createElement('div');
      el.className = 'fe-node-type';
      el.draggable = true;
      el.dataset.nodeType = m.name;
      el.title = m.description;
      el.innerHTML = `
        <div class="fe-node-cat-dot ${CATEGORY_COLORS[m.category] || 'cat-data'}"></div>
        <div>
          <div class="fe-node-type-name">${_esc(m.label)}</div>
          <div class="fe-node-type-desc">${_esc(m.description.slice(0, 40))}${m.description.length>40?'…':''}</div>
        </div>`;
      el.addEventListener('dragstart', e => {
        e.dataTransfer.setData('node-type', m.name);
      });
      // 双击直接添加到画布中心
      el.addEventListener('dblclick', () => _addNodeToCanvas(m.name, 200, 200));
      list.appendChild(el);
    });
  });
}

function _onCanvasDrop(e) {
  e.preventDefault();
  const type = e.dataTransfer.getData('node-type');
  if (!type) return;
  const canvasRect = document.getElementById('feDrawflow').getBoundingClientRect();
  const x = (e.clientX - canvasRect.left) / _drawflow.zoom - _drawflow.canvas_x / _drawflow.zoom;
  const y = (e.clientY - canvasRect.top)  / _drawflow.zoom - _drawflow.canvas_y / _drawflow.zoom;
  _addNodeToCanvas(type, x, y);
}

function _addNodeToCanvas(type, x, y) {
  const nd = _manifest.find(m => m.name === type);
  if (!nd) return;
  const nodeId = _drawflow.addNode(
    type, 1, 1, x, y,
    `df-node-${type}`,
    { type, label: nd.label, description: '', config: _defaultNodeConfig(nd) },
    _buildNodeHTML(nd),
  );
  _markDirty();
  return nodeId;
}

function _defaultNodeConfig(nd) {
  const cfg = {};
  Object.entries(nd.inputs_schema || {}).forEach(([k, v]) => {
    if (v.default !== undefined) cfg[k] = v.default;
  });
  return cfg;
}

function _buildNodeHTML(nd) {
  return `<div class="title-box">${_esc(nd.label)}</div>
          <div class="box"><div class="fe-node-type-desc" style="font-size:10px;color:var(--fe-muted)">${_esc(nd.description.slice(0,50))}${nd.description.length>50?'…':''}</div></div>`;
}

// ── 节点配置面板 ──────────────────────────────────────────────────────────────
function _onNodeSelected(nodeId) {
  _selectedNode = nodeId;
  const nodeData = _drawflow.getNodeFromId(nodeId);
  if (!nodeData) return;

  const nd = _manifest.find(m => m.name === nodeData.data?.type);
  const panel = document.getElementById('feConfigPanel');
  const title = document.getElementById('feConfigTitle');
  const body  = document.getElementById('feConfigBody');

  panel?.classList.remove('hidden');
  document.getElementById('feHistoryPanel')?.classList.add('hidden');
  if (title) title.textContent = `${nd?.label || nodeData.data?.type} 配置`;

  const nodeConfig = nodeData.data?.config || {};

  let html = `
    <div class="fe-field-group">
      <label>节点 ID</label>
      <input type="text" value="${_esc(String(nodeId))}" disabled style="opacity:.5">
    </div>
    <div class="fe-field-group">
      <label>描述 <span style="color:var(--fe-danger)">*</span></label>
      <textarea class="fe-node-desc-field" id="feNodeDesc" rows="2" placeholder="描述此节点的功能…">${_esc(nodeData.data?.description || '')}</textarea>
    </div>`;

  if (nd) {
    Object.entries(nd.inputs_schema || {}).forEach(([key, schema]) => {
      const val = nodeConfig[key] !== undefined ? nodeConfig[key] : (schema.default ?? '');
      const req  = schema.required ? '<span style="color:var(--fe-danger)">*</span>' : '';
      if (schema.enum) {
        const opts = schema.enum.map(v => `<option value="${_esc(v)}" ${v==val?'selected':''}>${_esc(v)}</option>`).join('');
        html += `<div class="fe-field-group"><label>${_esc(key)} ${req}</label>
                   <select id="feconf-${key}">${opts}</select></div>`;
      } else if (schema.type === 'object' || schema.type === 'array') {
        html += `<div class="fe-field-group"><label>${_esc(key)} ${req} <span style="font-weight:400;color:var(--fe-muted)">(JSON)</span></label>
                   <textarea id="feconf-${key}" rows="3">${_esc(typeof val==='string'?val:JSON.stringify(val,null,2))}</textarea></div>`;
      } else {
        const rows = schema.type === 'string' && (key.includes('prompt') || key.includes('template') || key.includes('script')) ? 'rows="4"' : '';
        html += `<div class="fe-field-group"><label>${_esc(key)} ${req}</label>
                   ${rows
                     ? `<textarea id="feconf-${key}" ${rows}>${_esc(String(val))}</textarea>`
                     : `<input type="text" id="feconf-${key}" value="${_esc(String(val))}">`
                   }</div>`;
      }
    });

    // Script 节点专属：审阅状态 + AI 生成按钮
    if (nd.name === 'script') {
      const reviewed = nodeConfig.reviewed_at || '';
      html += `<div class="fe-field-group">
                 <label>审阅状态</label>
                 ${reviewed
                   ? `<span class="fe-reviewed-tag">已审阅 ${_esc(reviewed)}</span>`
                   : `<span class="fe-not-reviewed-tag">未审阅（执行前必须审阅确认）</span>`}
               </div>
               <div style="display:flex;gap:6px;flex-wrap:wrap;">
                 <button class="fe-btn fe-btn-ghost" id="feBtnAiGen" onclick="_openGenScriptModal(${nodeId})">AI 生成脚本</button>
                 <button class="fe-btn fe-btn-accent" id="feBtnReview" onclick="_reviewScript(${nodeId})">审阅确认使用</button>
               </div>`;
    }
  }

  // 右键菜单占位
  html += `<div style="margin-top:8px;border-top:1px solid var(--fe-border);padding-top:8px;">
    <button class="fe-btn fe-btn-ghost" onclick="_testNode(${nodeId})" style="width:100%;justify-content:center">
      测试此节点
    </button>
  </div>`;

  if (body) body.innerHTML = html;

  // Change listeners → update drawflow node data
  ['feNodeDesc'].concat(nd ? Object.keys(nd.inputs_schema||{}).map(k=>`feconf-${k}`) : []).forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener('change', () => _saveNodeConfig(nodeId));
    el.addEventListener('blur',   () => _saveNodeConfig(nodeId));
  });
}

function _saveNodeConfig(nodeId) {
  const nodeData = _drawflow.getNodeFromId(nodeId);
  if (!nodeData) return;

  const descEl = document.getElementById('feNodeDesc');
  if (descEl) nodeData.data.description = descEl.value;

  const nd = _manifest.find(m => m.name === nodeData.data?.type);
  if (nd) {
    if (!nodeData.data.config) nodeData.data.config = {};
    Object.keys(nd.inputs_schema || {}).forEach(key => {
      const el = document.getElementById(`feconf-${key}`);
      if (!el) return;
      const schema = nd.inputs_schema[key];
      let val = el.value;
      if (schema.type === 'integer') val = parseInt(val) || 0;
      else if (schema.type === 'object' || schema.type === 'array') {
        try { val = JSON.parse(val); } catch (_) { val = val; }
      }
      nodeData.data.config[key] = val;
    });
  }

  _drawflow.drawflow.drawflow.Home.data[nodeId] = nodeData;
  _markDirty();
}

function _closeConfigPanel() {
  _selectedNode = null;
  document.getElementById('feConfigPanel')?.classList.add('hidden');
}

// ── .flowdef 序列化 / 反序列化 ───────────────────────────────────────────────

function _serializeToFlowdef() {
  const drawflowData = _drawflow.export();
  const dfNodes = drawflowData?.drawflow?.Home?.data || {};

  const intent = document.getElementById('feFlowIntent')?.value?.trim() || '';
  const schedule = _flowData?.schedule || '';

  const nodes = Object.entries(dfNodes).map(([nodeId, n]) => ({
    id:          n.data?.id || `node_${nodeId}`,
    type:        n.data?.type || 'data_fetch',
    description: n.data?.description || '',
    position:    { x: Math.round(n.pos_x), y: Math.round(n.pos_y) },
    config:      n.data?.config || {},
  }));

  const edges = [];
  Object.values(dfNodes).forEach(n => {
    const srcId = n.data?.id || `node_${Object.keys(dfNodes).find(k => dfNodes[k]===n)}`;
    Object.values(n.outputs || {}).forEach(out => {
      (out.connections || []).forEach(c => {
        const dstNode = dfNodes[c.node];
        if (dstNode) {
          edges.push({ from: srcId, to: dstNode.data?.id || `node_${c.node}` });
        }
      });
    });
  });

  const obj = { version: '1.0', intent, nodes, edges };
  if (schedule) obj.schedule = schedule;

  // Return YAML using simple serializer (no external dep in browser)
  return _objToYAML(obj);
}

function _deserializeFlowdef(yamlStr) {
  if (!yamlStr) return;
  try {
    // Simple YAML parse: try JSON-like parsing
    // Browser doesn't have js-yaml; we'll use a simple approach
    // For basic structure, parse line-by-line
    const parsed = _simpleYAMLParse(yamlStr);
    if (!parsed) return;

    _drawflow.clear();

    const nodes = parsed.nodes || [];
    const edges = parsed.edges || [];

    // Map logical node id → drawflow numeric id
    const idMap = {};

    nodes.forEach(n => {
      const nd = _manifest.find(m => m.name === n.type);
      const pos = n.position || { x: 100, y: 100 };
      const numId = _drawflow.addNode(
        n.type, 1, 1, pos.x, pos.y,
        `df-node-${n.type}`,
        { type: n.type, id: n.id, label: nd?.label || n.type, description: n.description || '', config: n.config || {} },
        nd ? _buildNodeHTML(nd) : `<div class="title-box">${_esc(n.type)}</div><div class="box">${_esc(n.id)}</div>`,
      );
      idMap[n.id] = numId;
    });

    // Connect edges
    edges.forEach(e => {
      const srcNum = idMap[e.from];
      const dstNum = idMap[e.to];
      if (srcNum !== undefined && dstNum !== undefined) {
        try {
          _drawflow.addConnection(srcNum, dstNum, 'output_1', 'input_1');
        } catch (_) {}
      }
    });

    // Set intent / schedule
    if (parsed.intent) {
      const intentEl = document.getElementById('feFlowIntent');
      if (intentEl) intentEl.value = parsed.intent;
    }
    if (parsed.schedule && _flowData) {
      _flowData.schedule = parsed.schedule;
    }
  } catch (e) {
    console.warn('[FlowEditor] flowdef 反序列化失败:', e);
  }
}

// ── 简单 YAML 解析（仅支持本 .flowdef 格式子集）─────────────────────────────
function _simpleYAMLParse(yaml) {
  // Try JSON-as-a-fallback first
  try { return JSON.parse(yaml); } catch (_) {}

  // Very minimal YAML parser for our flowdef format
  const lines = yaml.split('\n');
  const result = {};
  let currentList = null;
  let currentListKey = null;
  let currentItem = null;
  let inConfig = false;

  function parseValue(v) {
    v = v.trim();
    if (v === 'true') return true;
    if (v === 'false') return false;
    if (v === 'null' || v === '~') return null;
    if (/^-?\d+(\.\d+)?$/.test(v)) return parseFloat(v);
    if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) {
      return v.slice(1,-1);
    }
    if (v.startsWith('{')) { try { return JSON.parse(v); } catch(_) {} }
    if (v.startsWith('[')) { try { return JSON.parse(v); } catch(_) {} }
    return v;
  }

  lines.forEach(line => {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) return;

    const indent = line.match(/^(\s*)/)[1].length;

    if (indent === 0) {
      inConfig = false;
      const m = trimmed.match(/^(\w+):\s*(.*)/);
      if (m) {
        const key = m[1], val = m[2].trim();
        if (!val) { result[key] = []; currentListKey = key; currentList = result[key]; currentItem = null; }
        else result[key] = parseValue(val);
      }
    } else if (indent === 2 && trimmed.startsWith('- ')) {
      // New list item
      currentItem = {};
      if (currentList) currentList.push(currentItem);
      const rest = trimmed.slice(2);
      const m = rest.match(/^(\w+):\s*(.*)/);
      if (m) {
        const key = m[1], val = m[2].trim();
        currentItem[key] = val || {};
        if (!val) inConfig = (key === 'config' || key === 'position');
      }
    } else if (indent === 4 && currentItem) {
      const m = trimmed.match(/^(\w+):\s*(.*)/);
      if (m) {
        const key = m[1], val = m[2].trim();
        if (key === 'config' || key === 'position') { currentItem[key] = {}; inConfig = true; }
        else currentItem[key] = parseValue(val);
      }
    } else if (indent === 6 && currentItem && inConfig) {
      const m = trimmed.match(/^(\w+):\s*(.*)/);
      if (m) {
        const key = m[1], val = m[2];
        // find which subobject to put this in
        const lastConfigKey = Object.keys(currentItem).find(k => k === 'config' || k === 'position');
        if (lastConfigKey && typeof currentItem[lastConfigKey] === 'object') {
          currentItem[lastConfigKey][key] = parseValue(val);
        }
      }
    }
  });

  return result;
}

// ── 简单 YAML 序列化 ──────────────────────────────────────────────────────────
function _objToYAML(obj, indent = 0) {
  const pad = ' '.repeat(indent);
  let yaml = '';
  for (const [k, v] of Object.entries(obj)) {
    if (Array.isArray(v)) {
      if (!v.length) { yaml += `${pad}${k}: []\n`; continue; }
      yaml += `${pad}${k}:\n`;
      v.forEach(item => {
        if (typeof item === 'object' && item !== null) {
          const entries = Object.entries(item);
          yaml += `${pad}  - ${entries[0][0]}: ${_yamlVal(entries[0][1])}\n`;
          entries.slice(1).forEach(([ik, iv]) => {
            if (typeof iv === 'object' && iv !== null) {
              yaml += `${pad}    ${ik}:\n`;
              Object.entries(iv).forEach(([sk, sv]) => {
                yaml += `${pad}      ${sk}: ${_yamlVal(sv)}\n`;
              });
            } else {
              yaml += `${pad}    ${ik}: ${_yamlVal(iv)}\n`;
            }
          });
        } else {
          yaml += `${pad}  - ${_yamlVal(item)}\n`;
        }
      });
    } else if (typeof v === 'object' && v !== null) {
      yaml += `${pad}${k}:\n${_objToYAML(v, indent + 2)}`;
    } else {
      yaml += `${pad}${k}: ${_yamlVal(v)}\n`;
    }
  }
  return yaml;
}

function _yamlVal(v) {
  if (v === null || v === undefined) return 'null';
  if (typeof v === 'boolean') return v ? 'true' : 'false';
  if (typeof v === 'number') return String(v);
  if (typeof v === 'object') return JSON.stringify(v);
  const s = String(v);
  if (/[:{}[\],#&*?|<>=!%@`]/.test(s) || /^\s|\s$/.test(s)) return `"${s.replace(/"/g,'\\"')}"`;
  return s;
}

// ── Load / Save ───────────────────────────────────────────────────────────────

async function _loadFlow(gid) {
  try {
    const res = await _apiCall(`/api/flows/${gid}`);
    if (!res) { _setSaveStatus('加载失败'); return; }
    _flowData = res.data || res;

    document.getElementById('feFlowName').value = _flowData.name || '';
    document.title = `${_flowData.name || '流程'} — 流程编辑器`;

    if (_flowData.flowdef) {
      _deserializeFlowdef(_flowData.flowdef);
    }

    _setSaveStatus('已加载');
    _loadHistory();
  } catch (e) {
    _setSaveStatus('加载出错');
    console.error('[FlowEditor] load error:', e);
  }
}

async function _saveFlow() {
  const name = document.getElementById('feFlowName')?.value?.trim() || '未命名流程';

  // 校验：每个节点必须有 description
  const dfData = _drawflow.export()?.drawflow?.Home?.data || {};
  const missing = Object.values(dfData).filter(n => !(n.data?.description?.trim()));
  if (missing.length) {
    const warn = missing.map(n => n.data?.type || n.name).join(', ');
    console.warn(`[FlowEditor] 节点缺少 description: ${warn}`);
  }

  const intent = document.getElementById('feFlowIntent')?.value?.trim() || '';
  if (!intent) {
    alert('请填写流程意图（intent 字段必填）');
    document.getElementById('feFlowIntent')?.focus();
    return;
  }

  const flowdef = _serializeToFlowdef();

  try {
    if (!_flowGid) {
      // 新建
      const res = await _apiCall('/api/flows', { method: 'POST', body: JSON.stringify({ name, flowdef, description: intent }) });
      if (res) {
        _flowGid = res.gid || res.data?.gid;
        _flowData = { ..._flowData, gid: _flowGid, name, flowdef };
        _setSaveStatus('已保存');
        history.replaceState(null, '', `?flow_gid=${_flowGid}`);
      } else {
        alert('保存失败');
      }
    } else {
      await _apiCall(`/api/flows/${_flowGid}`, { method: 'PUT', body: JSON.stringify({ name, flowdef, description: intent }) });
      if (_flowData) _flowData.name = name;
      _setSaveStatus('已保存');
    }
  } catch (e) {
    alert('保存出错: ' + e);
  }
}

let _dirty = false;
function _markDirty() {
  if (!_dirty) { _dirty = true; _setSaveStatus('未保存 *'); }
}
function _setSaveStatus(text) {
  const el = document.getElementById('feSaveStatus');
  if (el) el.textContent = text;
}

// ── 运行 / 调试 ───────────────────────────────────────────────────────────────

async function _runFlow() {
  if (!_flowGid) { alert('请先保存流程'); return; }

  const btn = document.getElementById('feBtnRun');
  if (btn) { btn.disabled = true; btn.textContent = '运行中…'; }

  try {
    const res = await _apiCall(`/api/flows/${_flowGid}/run`, { method: 'POST', body: JSON.stringify({ mode: 'auto' }) });
    if (res) {
      _runGid = res.run_gid || res.data?.run_gid;
      _startPolling();
    } else {
      alert('启动失败');
    }
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '运行'; }
  }
}

async function _runFlowStep() {
  if (!_flowGid) { alert('请先保存流程'); return; }
  _stepMode = true;

  try {
    const res = await _apiCall(`/api/flows/${_flowGid}/run`, { method: 'POST', body: JSON.stringify({ mode: 'step' }) });
    if (res) {
      _runGid = res.run_gid || res.data?.run_gid;
      document.getElementById('feDebugBar')?.classList.remove('hidden');
      _startPolling();
    }
  } catch (e) {
    alert('调试启动失败: ' + e);
  }
}

async function _stepFlow() {
  if (!_runGid) return;
  try {
    const res = await _apiCall(`/api/flows/runs/${_runGid}/step`, { method: 'POST' });
    _updateRunState(res?.data || res);
  } catch (e) {
    console.error('[FlowEditor] step error:', e);
  }
}

function _startPolling() {
  _stopPolling();
  _pollTimer = setInterval(_pollRunState, 1000);
}

function _stopPolling() {
  if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
}

async function _pollRunState() {
  if (!_runGid) { _stopPolling(); return; }
  try {
    const res = await _apiCall(`/api/flows/runs/${_runGid}`);
    _updateRunState(res);
    if (res?.status === 'completed' || res?.status === 'failed') {
      _stopPolling();
      _loadHistory();
    }
  } catch (_) {}
}

function _updateRunState(state) {
  if (!state) return;
  const currentNode = state.current_node_id;

  // 清除所有节点状态高亮
  document.querySelectorAll('.drawflow-node').forEach(el => {
    el.classList.remove('node-running', 'node-done', 'node-fail');
  });

  if (currentNode) {
    // 找对应 drawflow node 的 DOM
    const dfData = _drawflow.export()?.drawflow?.Home?.data || {};
    Object.entries(dfData).forEach(([numId, n]) => {
      if ((n.data?.id === currentNode || numId === currentNode) && state.status === 'running') {
        document.querySelector(`.drawflow-node[id="node-${numId}"]`)?.classList.add('node-running');
      }
    });
  }

  // 调试模式状态栏
  if (_stepMode) {
    const statusEl = document.getElementById('feDebugStatus');
    const nodeEl   = document.getElementById('feDebugNode');
    if (statusEl) statusEl.textContent = `调试模式 — 状态: ${state.status}`;
    if (nodeEl)   nodeEl.textContent   = currentNode || '—';

    if (state.status === 'completed' || state.status === 'failed') {
      document.getElementById('feDebugBar')?.classList.add('hidden');
      _stepMode = false;
    }
  }
}

// ── 执行历史 ──────────────────────────────────────────────────────────────────

async function _loadHistory() {
  if (!_flowGid) return;
  try {
    const res = await _apiCall(`/api/flows/runs?flow_gid=${_flowGid}&limit=10`);
    _renderHistory(res?.items || []);
  } catch (_) {}
}

function _renderHistory(runs) {
  const list = document.getElementById('feHistoryList');
  if (!list) return;
  if (!runs.length) { list.innerHTML = '<div style="padding:12px;font-size:12px;color:var(--fe-muted)">暂无执行记录</div>'; return; }

  list.innerHTML = runs.map(r => {
    const cls = r.status === 'completed' ? 'fe-run-ok'
               : r.status === 'failed'   ? 'fe-run-fail'
               : r.status === 'running'  ? 'fe-run-running' : 'fe-run-pending';
    const ts = r.started_at ? new Date(parseFloat(r.started_at) * 1000).toLocaleString('zh-CN') : '—';
    const dur = (r.started_at && r.completed_at)
      ? `${((parseFloat(r.completed_at) - parseFloat(r.started_at)).toFixed(1))}s`
      : '';
    return `<div class="fe-run-item">
      <div class="fe-run-item-header">
        <span class="fe-run-status ${cls}">${_esc(r.status)}</span>
        <span style="font-size:10px;color:var(--fe-muted)">${dur}</span>
      </div>
      <div class="fe-run-time">${ts}</div>
      ${r.error_msg ? `<div class="fe-run-error">${_esc(r.error_msg.slice(0,80))}</div>` : ''}
    </div>`;
  }).join('');
}

// ── 单节点测试 ────────────────────────────────────────────────────────────────
function _testNode(nodeId) {
  const nodeData = _drawflow.getNodeFromId(nodeId);
  if (!nodeData) return;

  const modal = document.getElementById('feTestModal');
  const typeEl = document.getElementById('feTestNodeType');
  if (!modal || !typeEl) return;

  typeEl.textContent = nodeData.data?.type || nodeId;
  const inputsEl = document.getElementById('feTestInputs');
  if (inputsEl) inputsEl.value = JSON.stringify(nodeData.data?.config || {}, null, 2);

  document.getElementById('feTestResult')?.classList.add('hidden');
  modal.dataset.nodeType   = nodeData.data?.type || '';
  modal.dataset.nodeConfig = JSON.stringify(nodeData.data?.config || {});
  modal.classList.remove('hidden');
}

async function _runTest() {
  const modal = document.getElementById('feTestModal');
  const type   = modal?.dataset.nodeType;
  const config = JSON.parse(modal?.dataset.nodeConfig || '{}');
  const inputsEl = document.getElementById('feTestInputs');

  let inputs = {};
  try { inputs = JSON.parse(inputsEl?.value || '{}'); } catch (_) {}

  const btn = document.getElementById('feBtnRunTest');
  if (btn) { btn.disabled = true; btn.textContent = '执行中…'; }

  try {
    const res = await _apiCall('/api/flows/test-node', { method: 'POST', body: JSON.stringify({ type, config, inputs }) });
    const outEl = document.getElementById('feTestOutput');
    const resEl = document.getElementById('feTestResult');
    if (outEl) outEl.textContent = JSON.stringify(res?.output || res, null, 2);
    resEl?.classList.remove('hidden');
  } catch (e) {
    alert('测试失败: ' + e);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '执行测试'; }
  }
}

// ── Script 节点：AI 生成 ─────────────────────────────────────────────────────
function _openGenScriptModal(nodeId) {
  _pendingScriptNodeId = nodeId;
  const modal = document.getElementById('feGenScriptModal');
  if (modal) {
    document.getElementById('feGenDesc').value = '';
    document.getElementById('feGenCode').value = '';
    modal.classList.remove('hidden');
  }
}

function _reviewScript(nodeId) {
  const nodeData = _drawflow.getNodeFromId(nodeId);
  if (!nodeData) return;
  if (!nodeData.data.config) nodeData.data.config = {};
  nodeData.data.config.reviewed_at = new Date().toISOString();
  _drawflow.drawflow.drawflow.Home.data[nodeId] = nodeData;
  _markDirty();
  // Refresh config panel
  _onNodeSelected(nodeId);
}

async function _generateScript() {
  const desc = document.getElementById('feGenDesc')?.value?.trim();
  if (!desc) { alert('请输入需求描述'); return; }

  const btn = document.getElementById('feBtnGenScript');
  if (btn) { btn.disabled = true; btn.textContent = 'AI 生成中…'; }

  try {
    const res = await _apiCall('/api/flows/gen-script', {
      method: 'POST',
      body: JSON.stringify({ description: desc, inputs_schema: {}, outputs_schema: {} }),
    });
    const code = res?.code || '';
    const codeEl = document.getElementById('feGenCode');
    if (codeEl) codeEl.value = code;
  } catch (e) {
    alert('生成失败: ' + e);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'AI 生成'; }
  }
}

function _useGeneratedScript() {
  const code = document.getElementById('feGenCode')?.value?.trim();
  if (!code) { alert('请先生成或输入脚本'); return; }
  if (_pendingScriptNodeId === null) return;

  const nodeData = _drawflow.getNodeFromId(_pendingScriptNodeId);
  if (!nodeData) return;
  if (!nodeData.data.config) nodeData.data.config = {};
  nodeData.data.config.script = code;
  nodeData.data.config.reviewed_at = new Date().toISOString();
  _drawflow.drawflow.drawflow.Home.data[_pendingScriptNodeId] = nodeData;
  _markDirty();

  document.getElementById('feGenScriptModal')?.classList.add('hidden');
  _onNodeSelected(_pendingScriptNodeId);  // refresh config panel
}

// ── 按钮绑定 ──────────────────────────────────────────────────────────────────
function _bindButtons() {
  document.getElementById('feBack')        ?.addEventListener('click', () => window.parent?.TabManager?.close?.('flow_canvas') || history.back());
  document.getElementById('feBtnSave')     ?.addEventListener('click', _saveFlow);
  document.getElementById('feBtnRun')      ?.addEventListener('click', _runFlow);
  document.getElementById('feBtnStepMode') ?.addEventListener('click', _runFlowStep);
  document.getElementById('feBtnStep')     ?.addEventListener('click', _stepFlow);
  document.getElementById('feBtnStopDebug')?.addEventListener('click', () => {
    _stopPolling(); _stepMode = false;
    document.getElementById('feDebugBar')?.classList.add('hidden');
  });
  document.getElementById('feBtnHistory')  ?.addEventListener('click', () => {
    document.getElementById('feHistoryPanel')?.classList.toggle('hidden');
    document.getElementById('feConfigPanel')?.classList.add('hidden');
    _loadHistory();
  });
  document.getElementById('feConfigClose') ?.addEventListener('click', _closeConfigPanel);
  document.getElementById('feHistoryClose')?.addEventListener('click', () => {
    document.getElementById('feHistoryPanel')?.classList.add('hidden');
  });
  document.getElementById('feFlowName')    ?.addEventListener('change', _markDirty);
  document.getElementById('feFlowIntent')  ?.addEventListener('change', _markDirty);

  // Test modal
  document.getElementById('feBtnRunTest')  ?.addEventListener('click', _runTest);
  document.getElementById('feTestClose')   ?.addEventListener('click', () => document.getElementById('feTestModal')?.classList.add('hidden'));

  // Gen script modal
  document.getElementById('feBtnGenScript')?.addEventListener('click', _generateScript);
  document.getElementById('feBtnUseScript')?.addEventListener('click', _useGeneratedScript);
  document.getElementById('feGenScriptClose')?.addEventListener('click', () => document.getElementById('feGenScriptModal')?.classList.add('hidden'));
  document.getElementById('feGenScriptCancel')?.addEventListener('click', () => document.getElementById('feGenScriptModal')?.classList.add('hidden'));

  // Keyboard
  document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); _saveFlow(); }
    if (e.key === 'Escape') {
      document.querySelectorAll('.fe-modal-overlay:not(.hidden)').forEach(m => m.classList.add('hidden'));
    }
  });
}

// ── Utility ───────────────────────────────────────────────────────────────────
function _esc(s) {
  if (!s && s !== 0) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// Expose for inline onclick
window._testNode        = _testNode;
window._openGenScriptModal = _openGenScriptModal;
window._reviewScript    = _reviewScript;
