'use strict';
/**
 * flow_type.js — 流程画布类型插件
 *
 * 注册到 window.CANVAS_TYPES['flow']，由 CanvasShell 在 init() 时动态加载。
 *
 * 实现接口：
 *   renderPalette(paletteEl)            — 渲染左侧节点面板
 *   cardTypes                           — 节点类型定义（renderContent / renderDetail）
 *   toolbarActions                      — 工具栏按钮（意图 / 运行 / 调试 / 历史）
 *   onInit(shell)                       — 初始化：加载 manifest + flowdef + reloadCards
 *   onSave(shell)                       — 保存：序列化 flowdef YAML → bridge
 */

(function () {

  // ── 节点颜色映射 ──────────────────────────────────────────────────────────
  const NODE_COLORS = {
    data_fetch:    '#74c7ec',
    transform:     '#89b4fa',
    condition:     '#f9e2af',
    notify:        '#a6e3a1',
    ai_agent:      '#cba6f7',
    script:        '#f38ba8',
    update_entity: '#89dceb',
    approval:      '#fab387',
  };

  // ── YAML 工具（移植自 flow_editor.js）────────────────────────────────────
  function _yamlVal(v) {
    if (v === null || v === undefined) return 'null';
    if (typeof v === 'boolean') return v ? 'true' : 'false';
    if (typeof v === 'number')  return String(v);
    const s = String(v);
    if (/[:\n\r#\[\]{},|>&*!'"@`]/.test(s) || s.trim() !== s) return JSON.stringify(s);
    return s;
  }

  function _objToYAML(obj, indent = 0) {
    if (obj === null || obj === undefined) return 'null';
    if (typeof obj !== 'object') return _yamlVal(obj);
    const pad = '  '.repeat(indent);
    if (Array.isArray(obj)) {
      if (!obj.length) return '[]';
      return obj.map(item => {
        if (typeof item === 'object' && item !== null) {
          const lines = _objToYAML(item, indent + 1).split('\n');
          return `${pad}- ${lines[0].trimStart()}\n${lines.slice(1).join('\n')}`;
        }
        return `${pad}- ${_yamlVal(item)}`;
      }).join('\n');
    }
    return Object.entries(obj).map(([k, v]) => {
      if (typeof v === 'object' && v !== null && !Array.isArray(v)) {
        return `${pad}${k}:\n${_objToYAML(v, indent + 1)}`;
      }
      if (Array.isArray(v)) {
        if (!v.length) return `${pad}${k}: []`;
        return `${pad}${k}:\n${_objToYAML(v, indent + 1)}`;
      }
      return `${pad}${k}: ${_yamlVal(v)}`;
    }).join('\n');
  }

  function _simpleYAMLParse(text) {
    try { return JSON.parse(text); } catch {}
    const lines = text.split('\n');
    const root  = {};
    const stack = [{ obj: root, indent: -1 }];
    let lastKey = null;
    for (const rawLine of lines) {
      if (!rawLine.trim() || rawLine.trim().startsWith('#')) continue;
      const indent = rawLine.search(/\S/);
      const line   = rawLine.trim();
      while (stack.length > 1 && stack[stack.length - 1].indent >= indent) stack.pop();
      const cur = stack[stack.length - 1].obj;
      if (line.startsWith('- ')) {
        const val = line.slice(2).trim();
        if (!Array.isArray(cur[lastKey])) cur[lastKey] = [];
        const parsed = val.startsWith('{') ? JSON.parse(val) : val;
        cur[lastKey].push(parsed);
      } else if (line.includes(': ')) {
        const ci = line.indexOf(': ');
        const k  = line.slice(0, ci).trim();
        const v  = line.slice(ci + 2).trim();
        if (v === '') {
          cur[k] = {};
          stack.push({ obj: cur[k], indent });
          lastKey = k;
        } else {
          cur[k] = v === 'null' ? null
                 : v === 'true' ? true
                 : v === 'false' ? false
                 : isNaN(v) ? v.replace(/^["']|["']$/g, '') : Number(v);
        }
        lastKey = k;
      } else if (line.endsWith(':')) {
        const k = line.slice(0, -1).trim();
        cur[k] = {};
        stack.push({ obj: cur[k], indent });
        lastKey = k;
      }
    }
    return root;
  }

  // ── Bridge 调用（云端 REST）─────────────────────────────────────────────
  async function _bridge(method, args) {
    const cf = _cf()?._cloudFetch;
    if (!cf) throw new Error('cloudFetch not available');
    const gid = args?.gid;
    const runGid = args?.run_gid;
    switch (method) {
      case 'get_node_manifest':
        return cf('/api/flows/capability-manifest');
      case 'get_flow':
        return cf(`/api/flows/${gid}`);
      case 'create_flow':
        return cf('/api/flows', { method: 'POST', body: JSON.stringify(args) });
      case 'update_flow':
        return cf(`/api/flows/${gid}`, { method: 'PUT', body: JSON.stringify(args) });
      case 'run_flow':
        return cf(`/api/flows/${gid}/run`, { method: 'POST', body: JSON.stringify({ mode: args.mode }) });
      case 'step_flow':
        return cf(`/api/flows/runs/${runGid}/step`, { method: 'POST' });
      case 'get_run_state':
        return cf(`/api/flows/runs/${runGid}`);
      case 'list_run_history':
        return cf(`/api/flows/${gid}/runs?limit=${args.limit || 10}`);
      case 'test_node':
        return cf('/api/flows/test-node', { method: 'POST', body: JSON.stringify(args) });
      default:
        throw new Error(`Unknown flow method: ${method}`);
    }
  }

  function _cf() {
    return window.parent?._cloudFetch ? window.parent
         : (window._cloudFetch       ? window : null);
  }

  // ── flowdef ↔ canvas 转换 ─────────────────────────────────────────────────
  function _flowdefToCanvas(flowdef, shell) {
    const gs = shell._gridSystem;
    if (!gs) return { cards: [], connections: [] };

    const { rowHeight = 80, gap = 12 } = gs._opts || {};
    const colW = gs._colWidth || 80;

    const cards = (flowdef.nodes || []).map((node, idx) => {
      const col = node.position?.x != null
        ? Math.max(1, Math.round(node.position.x / (colW + gap)) + 1)
        : 1 + (idx % 4) * 5;
      const row = node.position?.y != null
        ? Math.max(1, Math.round(node.position.y / (rowHeight + gap)) + 1)
        : 1 + Math.floor(idx / 4) * 4;

      return {
        id:        `fn_${node.id}`,
        type:      node.type || 'script',
        label:     node.description || node.type,
        col_start: col,
        row_start: row,
        col_span:  4,
        row_span:  3,
        layer_id:  'layer_default',
        config: {
          node_id:     node.id,
          node_type:   node.type,
          description: node.description || '',
          ...(node.config || {}),
        },
      };
    });

    const connections = (flowdef.edges || []).map((edge, idx) => ({
      id:       `fe_${idx}`,
      from:     `fn_${edge.from}`,
      fromPort: 'right',
      to:       `fn_${edge.to}`,
      toPort:   'left',
      label:    '',
    }));

    return { cards, connections };
  }

  function _canvasToFlowdef(shell) {
    const intent = shell._flowIntent || '';
    const gs     = shell._gridSystem;
    const colW   = gs?._colWidth || 80;
    const { rowHeight = 80, gap = 12 } = gs?._opts || {};

    const nodes = [];
    shell._cards.forEach(card => {
      const { col_start, row_start, config = {} } = card;
      const { node_id, node_type, description, ...rest } = config;
      nodes.push({
        id:          node_id || card.id,
        type:        node_type || card.type,
        description: description || card.label || '',
        position: {
          x: (col_start - 1) * (colW + gap),
          y: (row_start - 1) * (rowHeight + gap),
        },
        config: rest,
      });
    });

    const edges = [];
    shell._connection._connections.forEach(conn => {
      edges.push({
        from: conn.from.replace(/^fn_/, ''),
        to:   conn.to.replace(/^fn_/, ''),
      });
    });

    return { version: '1.0', intent, nodes, edges };
  }

  // ── 插件对象 ──────────────────────────────────────────────────────────────
  const FlowPlugin = {

    // 内部状态
    _manifest:           [],
    _runGid:             null,
    _runMode:            null,
    _pollTimer:          null,
    _shell:              null,
    _flowGid:            null,
    _genScriptOnUpdate:  null,
    _genScriptConfig:    null,

    // ── cardTypes（动态构建后填充）──────────────────────────────────────────
    cardTypes: {},

    // ── toolbarActions（在插件注册时定义，onInit 前已可用）─────────────────
    toolbarActions: [
      {
        label: '意图',
        icon:  '#icon-note',
        handler: async (sh) => {
          const intent = await sh._promptText('编辑流程意图', '描述此流程要实现什么目标', sh._flowIntent || '');
          if (intent !== null) { sh._flowIntent = intent; sh._markDirty(); }
        },
      },
      {
        label: '运行',
        icon:  '#icon-check-circle',
        handler: (sh) => FlowPlugin._runFlow(sh, 'auto'),
      },
      {
        label: '调试',
        icon:  '#icon-tool',
        handler: (sh) => FlowPlugin._runFlow(sh, 'step'),
      },
      {
        label: '历史',
        icon:  '#icon-book-open',
        handler: () => FlowPlugin._toggleHistoryPanel(),
      },
    ],

    // ── 调色板渲染 ──────────────────────────────────────────────────────────
    renderPalette(paletteEl) {
      paletteEl.innerHTML = '';
      if (!FlowPlugin._manifest.length) {
        paletteEl.innerHTML = '<div style="padding:8px 12px;font-size:11px;color:var(--text-faint)">节点加载中…</div>';
        return;
      }

      const groups = {};
      FlowPlugin._manifest.forEach(n => {
        const cat = n.category || '其他';
        if (!groups[cat]) groups[cat] = [];
        groups[cat].push(n);
      });

      Object.entries(groups).forEach(([cat, nodes]) => {
        const title = document.createElement('div');
        title.className = 'cs-palette-section-title';
        title.textContent = cat;
        paletteEl.appendChild(title);

        nodes.forEach(n => {
          const color = NODE_COLORS[n.name] || '#888';
          const item  = document.createElement('div');
          item.className   = 'cs-palette-item';
          item.draggable   = true;
          item.dataset.paletteType = n.name;
          item.innerHTML = `
            <span class="cs-flow-node-dot" style="background:${color}"></span>
            ${n.label || n.name}
          `;
          item.addEventListener('dragstart', e => {
            e.dataTransfer.setData('cs/palette-type', n.name);
            e.dataTransfer.setData('text/plain', '');
            e.dataTransfer.effectAllowed = 'copy';
          });
          item.addEventListener('dblclick', () => {
            const { col, row } = FlowPlugin._shell._viewportCenterCell();
            FlowPlugin._shell.addCard({
              type:     n.name,
              label:    n.label || n.name,
              col_span: 4,
              row_span: 3,
              config:   { node_type: n.name },
            }, col, row);
          });
          paletteEl.appendChild(item);
        });
      });
    },

    // ── onInit ─────────────────────────────────────────────────────────────
    async onInit(shell) {
      FlowPlugin._shell   = shell;
      FlowPlugin._flowGid = shell._canvasGid;

      // 注入 Flow 专属 DOM（历史面板、调试底栏、测试/生成脚本 Modal）
      FlowPlugin._injectFlowUI();

      // 加载节点 manifest
      try {
        const manifest = await _bridge('get_node_manifest', {});
        FlowPlugin._manifest = Array.isArray(manifest) ? manifest : [];
      } catch {
        FlowPlugin._manifest = [];
      }

      // 构建 cardTypes
      FlowPlugin._buildCardTypes();

      // 重渲染调色板（manifest 已就绪）
      shell._renderPalette();

      // 加载 flowdef 数据
      try {
        const flowData = await _bridge('get_flow', { gid: FlowPlugin._flowGid });
        if (flowData?.flowdef) {
          const yaml   = typeof flowData.flowdef === 'string'
            ? flowData.flowdef
            : _objToYAML(flowData.flowdef);
          shell._flowIntent  = flowData.intent || '';
          shell._flowdefYaml = yaml;
          const { cards, connections } = _flowdefToCanvas(_simpleYAMLParse(yaml), shell);
          shell.reloadCards(cards, connections);
        }
      } catch {
        // 新建画布：不加载数据，使用空状态
      }
    },

    // ── onSave ─────────────────────────────────────────────────────────────
    async onSave(shell) {
      const flowdef = _canvasToFlowdef(shell);
      const yaml    = _objToYAML(flowdef);

      // localStorage 保底
      localStorage.setItem(`cs:canvas:${shell._canvasGid}`, JSON.stringify({
        gid:         shell._canvasGid,
        name:        shell._canvasName,
        canvas_type: 'flow',
        cards:       shell._serializeCards(),
        connections: shell._connection?.serialize() || [],
        layers:      shell._layers?.serialize()     || [],
      }));

      try {
        const existing = await _bridge('get_flow', { gid: FlowPlugin._flowGid }).catch(() => null);
        if (existing?.gid) {
          await _bridge('update_flow', {
            gid:     FlowPlugin._flowGid,
            flowdef: yaml,
            intent:  flowdef.intent,
          });
        } else {
          await _bridge('create_flow', {
            gid:     FlowPlugin._flowGid,
            name:    shell._canvasName,
            intent:  flowdef.intent,
            flowdef: yaml,
          });
        }
      } catch { /* 离线时静默失败 */ }

      shell._dirty = false;
      document.getElementById('csUnsavedDot')?.classList.add('hidden');
      FlowPlugin._toast('已保存');
    },

    // ── 构建 cardTypes（manifest 加载后调用）──────────────────────────────
    _buildCardTypes() {
      FlowPlugin.cardTypes = {};
      FlowPlugin._manifest.forEach(n => {
        const color = NODE_COLORS[n.name] || '#888';
        FlowPlugin.cardTypes[n.name] = {
          label:          n.label || n.name,
          defaultColSpan: 4,
          defaultRowSpan: 3,

          renderContent(bodyEl, config) {
            bodyEl.innerHTML = `
              <div class="cs-flow-node-body" style="border-left:3px solid ${color}">
                <div class="cs-flow-node-type">${n.label || n.name}</div>
                <div class="cs-flow-node-desc">${config.description || ''}</div>
              </div>
            `;
          },

          renderDetail(extEl, config, onUpdate) {
            FlowPlugin._renderNodeDetail(extEl, config, onUpdate, n);
          },
        };
      });
    },

    // ── 节点详情面板 ───────────────────────────────────────────────────────
    _renderNodeDetail(extEl, config, onUpdate, manifest) {
      extEl.innerHTML = '';

      // 描述字段
      const descRow = document.createElement('div');
      descRow.className = 'cs-prop-row';
      descRow.innerHTML = `
        <span class="cs-prop-label">描述</span>
        <input class="cs-prop-value-edit" id="csFlowNodeDesc" value="${config.description || ''}">
      `;
      extEl.appendChild(descRow);
      descRow.querySelector('#csFlowNodeDesc')?.addEventListener('change', e => {
        onUpdate({ description: e.target.value.trim() });
      });

      // inputs_schema 动态表单
      const schema = manifest?.inputs_schema || {};
      Object.entries(schema).forEach(([key, spec]) => {
        const row = document.createElement('div');
        row.className = 'cs-prop-row';
        const val = config[key] ?? spec.default ?? '';
        row.innerHTML = `
          <span class="cs-prop-label">${spec.label || key}</span>
          <input class="cs-prop-value-edit" data-key="${key}" value="${String(val)}"
            placeholder="${spec.description || ''}">
        `;
        extEl.appendChild(row);
        row.querySelector(`[data-key="${key}"]`)?.addEventListener('change', e => {
          onUpdate({ [key]: e.target.value });
        });
      });

      // Script 节点专属：AI 生成脚本 + 审阅标记
      if (manifest?.name === 'script') {
        const scriptBtn = document.createElement('button');
        scriptBtn.className = 'cs-btn-ghost';
        scriptBtn.style.cssText = 'margin-top:8px;font-size:11px;';
        scriptBtn.innerHTML = `
          <svg class="icon" width="11" height="11"><use href="#icon-robot"/></svg>
          AI 生成脚本
        `;
        scriptBtn.addEventListener('click', () => FlowPlugin._openGenScript(config, onUpdate));
        extEl.appendChild(scriptBtn);

        if (config.reviewed_at) {
          const tag = document.createElement('span');
          tag.style.cssText = 'font-size:10px;color:var(--text-faint);margin-left:8px;';
          tag.textContent = `已审阅 ${new Date(config.reviewed_at).toLocaleString()}`;
          extEl.appendChild(tag);
        }
      }

      // 单节点测试按钮
      const testBtn = document.createElement('button');
      testBtn.className = 'cs-btn-ghost';
      testBtn.style.cssText = 'margin-top:8px;font-size:11px;';
      testBtn.innerHTML = `
        <svg class="icon" width="11" height="11"><use href="#icon-check"/></svg>
        测试此节点
      `;
      testBtn.addEventListener('click', () => FlowPlugin._openTestNode(config, manifest));
      extEl.appendChild(testBtn);
    },

    // ── 注入 Flow 专属 DOM ─────────────────────────────────────────────────
    _injectFlowUI() {
      // 执行历史面板
      if (!document.getElementById('csFlowHistPanel')) {
        const histPanel = document.createElement('div');
        histPanel.id = 'csFlowHistPanel';
        histPanel.className = 'cs-flow-hist-panel hidden';
        histPanel.innerHTML = `
          <div class="cs-flow-hist-hdr">
            <span>执行历史</span>
            <button class="cs-modal-close" id="csFlowHistClose">
              <svg class="icon" width="12" height="12"><use href="#icon-x"/></svg>
            </button>
          </div>
          <div class="cs-flow-hist-list" id="csFlowHistList">
            <div style="padding:12px;font-size:11px;color:var(--text-faint)">暂无执行记录</div>
          </div>
        `;
        document.body.appendChild(histPanel);
        document.getElementById('csFlowHistClose')?.addEventListener('click', () => {
          histPanel.classList.add('hidden');
        });
      }

      // 调试底栏
      if (!document.getElementById('csFlowDebugBar')) {
        const debugBar = document.createElement('div');
        debugBar.id = 'csFlowDebugBar';
        debugBar.className = 'cs-flow-debug-bar hidden';
        debugBar.innerHTML = `
          <span id="csFlowDebugStatus" class="cs-flow-debug-status">等待中…</span>
          <button class="cs-btn-ghost cs-tb-btn" id="csFlowStepBtn">
            <svg class="icon" width="11" height="11"><use href="#icon-check"/></svg>
            下一步
          </button>
          <button class="cs-btn-ghost cs-tb-btn" id="csFlowStopBtn">停止</button>
        `;
        document.body.appendChild(debugBar);
        document.getElementById('csFlowStepBtn')?.addEventListener('click', () => FlowPlugin._stepFlow());
        document.getElementById('csFlowStopBtn')?.addEventListener('click', () => FlowPlugin._stopRun());
      }

      // 测试节点 Modal
      if (!document.getElementById('csFlowTestModal')) {
        const testModal = document.createElement('div');
        testModal.id = 'csFlowTestModal';
        testModal.className = 'cs-modal-overlay hidden';
        testModal.innerHTML = `
          <div class="cs-modal" style="max-width:480px">
            <div class="cs-modal-hdr">
              <span class="cs-modal-title">测试节点</span>
              <button class="cs-modal-close" id="csFlowTestClose">
                <svg class="icon" width="12" height="12"><use href="#icon-x"/></svg>
              </button>
            </div>
            <div class="cs-modal-body">
              <textarea id="csFlowTestInput" rows="6"
                style="width:100%;box-sizing:border-box;font-family:monospace;font-size:12px;resize:vertical;background:var(--bg-secondary);border:1px solid var(--border-default);border-radius:4px;padding:8px;color:var(--text-normal);"
                placeholder='{"key": "value"}'></textarea>
              <div id="csFlowTestResult"
                style="margin-top:8px;font-size:12px;white-space:pre-wrap;max-height:180px;overflow:auto;background:var(--bg-secondary);border-radius:4px;padding:8px;display:none;"></div>
            </div>
            <div style="padding:0 16px 16px;display:flex;gap:8px;justify-content:flex-end">
              <button class="cs-btn-ghost cs-tb-btn" id="csFlowTestClose2">取消</button>
              <button class="cs-btn-accent cs-tb-btn" id="csFlowTestRun">运行</button>
            </div>
          </div>
        `;
        document.body.appendChild(testModal);
        document.getElementById('csFlowTestClose')?.addEventListener('click',  () => testModal.classList.add('hidden'));
        document.getElementById('csFlowTestClose2')?.addEventListener('click', () => testModal.classList.add('hidden'));
      }

      // AI 生成脚本 Modal
      if (!document.getElementById('csFlowGenModal')) {
        const genModal = document.createElement('div');
        genModal.id = 'csFlowGenModal';
        genModal.className = 'cs-modal-overlay hidden';
        genModal.innerHTML = `
          <div class="cs-modal" style="max-width:560px">
            <div class="cs-modal-hdr">
              <span class="cs-modal-title">AI 生成脚本</span>
              <button class="cs-modal-close" id="csFlowGenClose">
                <svg class="icon" width="12" height="12"><use href="#icon-x"/></svg>
              </button>
            </div>
            <div class="cs-modal-body">
              <textarea id="csFlowGenPrompt" rows="3"
                style="width:100%;box-sizing:border-box;font-family:inherit;font-size:12px;resize:vertical;background:var(--bg-secondary);border:1px solid var(--border-default);border-radius:4px;padding:8px;color:var(--text-normal);"
                placeholder="描述脚本要实现的功能…"></textarea>
              <div id="csFlowGenResult" style="margin-top:8px;display:none">
                <pre id="csFlowGenCode"
                  style="font-size:12px;background:var(--bg-secondary);border-radius:4px;padding:8px;overflow:auto;max-height:280px;white-space:pre-wrap;margin:0;"></pre>
                <label style="font-size:11px;color:var(--text-faint);margin-top:4px;display:block">
                  ⚠️ 请审阅代码后再使用
                </label>
              </div>
            </div>
            <div style="padding:0 16px 16px;display:flex;gap:8px;justify-content:flex-end">
              <button class="cs-btn-ghost cs-tb-btn" id="csFlowGenClose2">取消</button>
              <button class="cs-btn-ghost cs-tb-btn" id="csFlowGenGenerate">生成</button>
              <button class="cs-btn-accent cs-tb-btn hidden" id="csFlowGenUse">审阅确认使用</button>
            </div>
          </div>
        `;
        document.body.appendChild(genModal);
        document.getElementById('csFlowGenClose')?.addEventListener('click',    () => genModal.classList.add('hidden'));
        document.getElementById('csFlowGenClose2')?.addEventListener('click',   () => genModal.classList.add('hidden'));
        document.getElementById('csFlowGenGenerate')?.addEventListener('click', () => FlowPlugin._generateScript());
      }
    },

    // ── 运行流程 ───────────────────────────────────────────────────────────
    async _runFlow(shell, mode) {
      if (!FlowPlugin._flowGid) return;

      // 先保存
      await shell.save();

      FlowPlugin._runMode = mode;
      FlowPlugin._shell   = shell;
      shell.clearNodeHighlights();

      try {
        const res = await _bridge('run_flow', { gid: FlowPlugin._flowGid, mode });
        FlowPlugin._runGid = res?.run_gid || res;

        if (mode === 'step') {
          document.getElementById('csFlowDebugBar')?.classList.remove('hidden');
          const statusEl = document.getElementById('csFlowDebugStatus');
          if (statusEl) statusEl.textContent = '调试模式 — 准备运行';
        }
        FlowPlugin._startPoll();
      } catch (err) {
        FlowPlugin._toast(`运行失败: ${err}`, 'error');
      }
    },

    async _stepFlow() {
      if (!FlowPlugin._runGid) return;
      try {
        await _bridge('step_flow', { run_gid: FlowPlugin._runGid });
      } catch (err) {
        FlowPlugin._toast(`步进失败: ${err}`, 'error');
      }
    },

    _stopRun() {
      FlowPlugin._clearPoll();
      FlowPlugin._runGid = null;
      document.getElementById('csFlowDebugBar')?.classList.add('hidden');
      FlowPlugin._shell?.clearNodeHighlights();
    },

    _startPoll() {
      FlowPlugin._clearPoll();
      FlowPlugin._pollTimer = setInterval(async () => {
        if (!FlowPlugin._runGid) { FlowPlugin._clearPoll(); return; }
        try {
          const state = await _bridge('get_run_state', { run_gid: FlowPlugin._runGid });
          FlowPlugin._applyRunState(state);
          if (['completed', 'failed', 'error'].includes(state?.status)) {
            FlowPlugin._clearPoll();
            document.getElementById('csFlowDebugBar')?.classList.add('hidden');
            FlowPlugin._runGid = null;
          }
        } catch { FlowPlugin._clearPoll(); }
      }, 1000);
    },

    _clearPoll() {
      if (FlowPlugin._pollTimer) {
        clearInterval(FlowPlugin._pollTimer);
        FlowPlugin._pollTimer = null;
      }
    },

    _applyRunState(state) {
      if (!state || !FlowPlugin._shell) return;
      const shell = FlowPlugin._shell;

      shell.clearNodeHighlights();
      const nodeStates = state.node_states || {};
      Object.entries(nodeStates).forEach(([nodeId, ns]) => {
        const status = ns.status === 'running' ? 'running'
                     : ns.status === 'done'    ? 'done'
                     : ns.status === 'fail'    ? 'fail'
                     : '';
        if (status) shell.highlightNode(`fn_${nodeId}`, status);
      });

      if (FlowPlugin._runMode === 'step') {
        const statusEl = document.getElementById('csFlowDebugStatus');
        if (statusEl) {
          const cur = state.current_node || '';
          statusEl.textContent = cur ? `当前节点: ${cur}` : `状态: ${state.status || '运行中'}`;
        }
      }
    },

    // ── 执行历史面板 ───────────────────────────────────────────────────────
    async _toggleHistoryPanel() {
      const panel = document.getElementById('csFlowHistPanel');
      if (!panel) return;
      if (!panel.classList.contains('hidden')) { panel.classList.add('hidden'); return; }
      panel.classList.remove('hidden');

      const listEl = document.getElementById('csFlowHistList');
      if (listEl) listEl.innerHTML = '<div style="padding:12px;font-size:11px;color:var(--text-faint)">加载中…</div>';

      try {
        const runs = await _bridge('list_run_history', { gid: FlowPlugin._flowGid, limit: 10 });
        if (!runs?.length) {
          listEl.innerHTML = '<div style="padding:12px;font-size:11px;color:var(--text-faint)">暂无执行记录</div>';
          return;
        }
        listEl.innerHTML = (runs || []).map(r => `
          <div class="cs-flow-hist-item">
            <span class="cs-flow-hist-status cs-flow-hist-${r.status}">${r.status}</span>
            <span style="flex:1;font-size:11px">${new Date(r.started_at).toLocaleString()}</span>
            <span style="font-size:10px;color:var(--text-faint)">${r.mode || 'auto'}</span>
          </div>
        `).join('');
      } catch {
        if (listEl) listEl.innerHTML = '<div style="padding:12px;font-size:11px;color:var(--color-danger)">加载失败</div>';
      }
    },

    // ── 测试节点 ───────────────────────────────────────────────────────────
    _openTestNode(config, manifest) {
      const modal = document.getElementById('csFlowTestModal');
      if (!modal) return;
      modal.classList.remove('hidden');

      const schema = manifest?.inputs_schema || {};
      document.getElementById('csFlowTestInput').value = JSON.stringify(
        Object.fromEntries(Object.keys(schema).map(k => [k, ''])),
        null, 2
      );
      const resultEl = document.getElementById('csFlowTestResult');
      if (resultEl) { resultEl.style.display = 'none'; resultEl.textContent = ''; }

      // 替换运行按钮，避免重复绑定
      const runBtn  = document.getElementById('csFlowTestRun');
      const newBtn  = runBtn.cloneNode(true);
      runBtn.parentNode.replaceChild(newBtn, runBtn);
      newBtn.addEventListener('click', async () => {
        let inputs = {};
        try { inputs = JSON.parse(document.getElementById('csFlowTestInput').value); } catch {}
        try {
          const res = await _bridge('test_node', {
            node_type: config.node_type || config.type,
            config,
            inputs,
          });
          resultEl.textContent    = JSON.stringify(res, null, 2);
          resultEl.style.display  = 'block';
        } catch (err) {
          resultEl.textContent   = `错误: ${err}`;
          resultEl.style.display = 'block';
        }
      });
    },

    // ── AI 生成脚本 ────────────────────────────────────────────────────────
    _openGenScript(config, onUpdate) {
      FlowPlugin._genScriptOnUpdate = onUpdate;
      FlowPlugin._genScriptConfig   = config;
      const modal = document.getElementById('csFlowGenModal');
      if (!modal) return;
      modal.classList.remove('hidden');
      document.getElementById('csFlowGenPrompt').value = '';
      document.getElementById('csFlowGenResult').style.display = 'none';
      document.getElementById('csFlowGenUse').classList.add('hidden');
    },

    async _generateScript() {
      const prompt = document.getElementById('csFlowGenPrompt')?.value.trim();
      if (!prompt) return;
      const genBtn = document.getElementById('csFlowGenGenerate');
      if (genBtn) genBtn.textContent = '生成中…';

      try {
        const cfObj = _cf();
        if (!cfObj) throw new Error('cloudFetch 不可用');
        const res = await cfObj._cloudFetch('/api/flows/gen-script', {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({ prompt, context: FlowPlugin._genScriptConfig }),
        });
        const data = await res.json();
        const code = data?.script || data?.code || '';
        document.getElementById('csFlowGenCode').textContent    = code;
        document.getElementById('csFlowGenResult').style.display = 'block';

        const useBtn = document.getElementById('csFlowGenUse');
        useBtn.classList.remove('hidden');
        // 替换，避免重复绑定
        const newUse = useBtn.cloneNode(true);
        useBtn.parentNode.replaceChild(newUse, useBtn);
        newUse.addEventListener('click', () => {
          FlowPlugin._genScriptOnUpdate?.({
            script:      code,
            reviewed_at: new Date().toISOString(),
          });
          document.getElementById('csFlowGenModal').classList.add('hidden');
        });
      } catch (err) {
        document.getElementById('csFlowGenCode').textContent     = `生成失败: ${err}`;
        document.getElementById('csFlowGenResult').style.display = 'block';
      } finally {
        if (genBtn) genBtn.textContent = '生成';
      }
    },

    // ── Toast 通知 ─────────────────────────────────────────────────────────
    _toast(msg, type = 'info') {
      const el = document.createElement('div');
      el.className = `cs-flow-toast${type === 'error' ? ' cs-flow-toast-error' : ''}`;
      el.textContent = msg;
      document.body.appendChild(el);
      setTimeout(() => el.remove(), 2500);
    },
  };

  // ── 注册 ──────────────────────────────────────────────────────────────────
  window.CANVAS_TYPES         = window.CANVAS_TYPES || {};
  window.CANVAS_TYPES['flow'] = FlowPlugin;

})();
