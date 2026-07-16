'use strict';
/**
 * TemplateLibrary — 模板库
 *
 * 右侧面板两个区域：
 *   1. 画布模板：系统预设 + 用户自定义（保存/删除/插入）
 *   2. 卡片模板：单张卡片拖拽或双击添加到画布（原有功能）
 *
 * 画布模板持久化：localStorage('cs:canvas-templates') → 用户自定义模板数组
 * 系统预设：硬编码在 _SYSTEM_CANVAS_TEMPLATES
 */

const _CS_CANVAS_TEMPLATES_KEY = 'cs:canvas-templates';
// localStorage 账号隔离
function _csTplLsk(base) {
  try { const u = window._authUser || window.parent?._authUser || window.top?._authUser; const g = u?.gid || u?.user_gid || ''; return g ? `${g}:${base}` : base; } catch { return base; }
}

// ── 系统预设画布模板 ──────────────────────────────────────────────────────────
const _SYSTEM_CANVAS_TEMPLATES = [
  {
    id:     'sys_tpl_overview',
    name:   '概览布局',
    desc:   '标题 + 四内容块',
    system: true,
    cards: [
      { id: 'sp_t',  type: 'note', label: '标题',   col_start:  1, row_start: 1, col_span: 24, row_span: 2, config: { text: '' } },
      { id: 'sp_c1', type: 'note', label: '内容 A', col_start:  1, row_start: 4, col_span:  6, row_span: 4, config: { text: '' } },
      { id: 'sp_c2', type: 'note', label: '内容 B', col_start:  7, row_start: 4, col_span:  6, row_span: 4, config: { text: '' } },
      { id: 'sp_c3', type: 'note', label: '内容 C', col_start: 13, row_start: 4, col_span:  6, row_span: 4, config: { text: '' } },
      { id: 'sp_c4', type: 'note', label: '内容 D', col_start: 19, row_start: 4, col_span:  6, row_span: 4, config: { text: '' } },
    ],
    connections: [],
  },
  {
    id:     'sys_tpl_flow',
    name:   '线性流程',
    desc:   '四步流程 + 箭头连线',
    system: true,
    cards: [
      { id: 'sf_1', type: 'note', label: '步骤 1', col_start:  1, row_start: 2, col_span: 4, row_span: 3, config: { text: '' } },
      { id: 'sf_2', type: 'note', label: '步骤 2', col_start:  7, row_start: 2, col_span: 4, row_span: 3, config: { text: '' } },
      { id: 'sf_3', type: 'note', label: '步骤 3', col_start: 13, row_start: 2, col_span: 4, row_span: 3, config: { text: '' } },
      { id: 'sf_4', type: 'note', label: '步骤 4', col_start: 19, row_start: 2, col_span: 4, row_span: 3, config: { text: '' } },
    ],
    connections: [
      { id: 'sfc_12', from: 'sf_1', fromPort: 'right', to: 'sf_2', toPort: 'left', label: '' },
      { id: 'sfc_23', from: 'sf_2', fromPort: 'right', to: 'sf_3', toPort: 'left', label: '' },
      { id: 'sfc_34', from: 'sf_3', fromPort: 'right', to: 'sf_4', toPort: 'left', label: '' },
    ],
  },
  {
    id:     'sys_tpl_2col',
    name:   '双列布局',
    desc:   '左右两栏 + 底部汇总',
    system: true,
    cards: [
      { id: 'sc_l1', type: 'note', label: '左栏 A', col_start:  1, row_start: 1, col_span: 11, row_span: 4, config: { text: '' } },
      { id: 'sc_l2', type: 'note', label: '左栏 B', col_start:  1, row_start: 6, col_span: 11, row_span: 4, config: { text: '' } },
      { id: 'sc_r1', type: 'note', label: '右栏 A', col_start: 13, row_start: 1, col_span: 12, row_span: 4, config: { text: '' } },
      { id: 'sc_r2', type: 'note', label: '右栏 B', col_start: 13, row_start: 6, col_span: 12, row_span: 4, config: { text: '' } },
      { id: 'sc_b',  type: 'note', label: '汇总',   col_start:  1, row_start: 11, col_span: 24, row_span: 3, config: { text: '' } },
    ],
    connections: [],
  },
];

// ── TemplateLibrary ───────────────────────────────────────────────────────────
class TemplateLibrary {
  constructor(shell) {
    this._shell    = shell;
    this._cardTpls = [];   // 卡片级模板
  }

  // ── 加载卡片模板（原有功能）────────────────────────────────────────────────
  load(canvasType) {
    this._cardTpls = [
      {
        id:      'tpl_note',
        name:    '备注卡片',
        desc:    '文本备注，3×2',
        cardDef: { type: 'note', label: '备注', col_span: 3, row_span: 2, config: { text: '' } },
      },
      {
        id:      'tpl_wide',
        name:    '宽卡片',
        desc:    '横跨 6 列、2 行',
        cardDef: { type: 'note', label: '宽卡片', col_span: 6, row_span: 2, config: { text: '' } },
      },
    ];

    const plugin = window.CANVAS_TYPES?.[canvasType];
    if (plugin?.templates) {
      this._cardTpls.push(...plugin.templates);
    }
  }

  // ── 渲染整个模板面板 ──────────────────────────────────────────────────────
  renderPanel(containerEl) {
    if (!containerEl) return;
    containerEl.innerHTML = '';

    // ── 画布模板区域 ─────────────────────────────────────────────────────
    const canvasSec = document.createElement('div');
    canvasSec.className = 'cs-tpl-section';

    const secHdr = document.createElement('div');
    secHdr.className = 'cs-tpl-sec-hdr';
    secHdr.innerHTML = `
      <span>画布模板</span>
      <button class="cs-btn-ghost cs-btn-xs cs-tpl-save-btn" title="保存当前画布为模板">
        <svg class="icon" width="11" height="11"><use href="#icon-plus"/></svg>
        保存
      </button>
    `;
    secHdr.querySelector('.cs-tpl-save-btn')?.addEventListener('click', () => this._saveCurrentAsTemplate(containerEl));

    const canvasList = document.createElement('div');
    canvasList.id = 'csTplCanvasList';
    canvasList.className = 'cs-tpl-canvas-list';

    canvasSec.appendChild(secHdr);
    canvasSec.appendChild(canvasList);
    containerEl.appendChild(canvasSec);
    this._renderCanvasTemplates(canvasList);

    // ── 分割线 ───────────────────────────────────────────────────────────
    const sep = document.createElement('div');
    sep.className = 'cs-tpl-sep';
    containerEl.appendChild(sep);

    // ── 卡片模板区域 ─────────────────────────────────────────────────────
    const cardSec = document.createElement('div');
    cardSec.className = 'cs-tpl-section';
    cardSec.innerHTML = `<div class="cs-tpl-sec-hdr"><span>卡片模板</span></div>`;

    if (this._cardTpls.length) {
      this._cardTpls.forEach(tpl => {
        const item = document.createElement('div');
        item.className = 'cs-template-item';
        item.draggable = true;
        item.dataset.tplId = tpl.id;
        item.innerHTML = `
          <div class="cs-template-name">${_escHtml(tpl.name)}</div>
          ${tpl.desc ? `<div class="cs-template-desc">${_escHtml(tpl.desc)}</div>` : ''}
        `;
        item.addEventListener('dblclick', () => {
          const def = this.instantiate(tpl.id);
          const { col, row } = this._shell._viewportCenterCell();
          this._shell.addCard(def, col, row);
        });
        item.addEventListener('dragstart', e => {
          e.dataTransfer.setData('text/plain', tpl.id);
          e.dataTransfer.effectAllowed = 'copy';
        });
        cardSec.appendChild(item);
      });
    } else {
      const empty = document.createElement('div');
      empty.className = 'cs-palette-empty';
      empty.textContent = '暂无卡片模板';
      cardSec.appendChild(empty);
    }
    containerEl.appendChild(cardSec);
  }

  // ── 渲染画布模板列表 ──────────────────────────────────────────────────────
  _renderCanvasTemplates(listEl) {
    if (!listEl) return;
    listEl.innerHTML = '';

    const userTpls = this._loadCanvasTemplates();
    const allTpls  = [..._SYSTEM_CANVAS_TEMPLATES, ...userTpls];

    if (!allTpls.length) {
      listEl.innerHTML = '<div class="cs-palette-empty">暂无画布模板</div>';
      return;
    }

    allTpls.forEach(tpl => {
      const item = document.createElement('div');
      item.className = 'cs-canvas-tpl-item';

      const info = document.createElement('div');
      info.className = 'cs-canvas-tpl-info';
      info.innerHTML = `
        <div class="cs-template-name">${_escHtml(tpl.name)}</div>
        ${tpl.desc ? `<div class="cs-template-desc">${_escHtml(tpl.desc)}</div>` : ''}
      `;

      const actions = document.createElement('div');
      actions.className = 'cs-canvas-tpl-actions';

      const applyBtn = document.createElement('button');
      applyBtn.className = 'cs-btn-ghost cs-btn-xs';
      applyBtn.title = '插入到当前画布';
      applyBtn.textContent = '插入';
      applyBtn.addEventListener('click', () => this._applyCanvasTemplate(tpl));
      actions.appendChild(applyBtn);

      if (!tpl.system) {
        const delBtn = document.createElement('button');
        delBtn.className = 'cs-btn-ghost cs-btn-xs cs-tpl-del-icon';
        delBtn.title = '删除此模板';
        delBtn.innerHTML = `<svg class="icon" width="10" height="10"><use href="#icon-x"/></svg>`;
        delBtn.addEventListener('click', e => {
          e.stopPropagation();
          this._deleteCanvasTemplate(tpl.id, listEl);
        });
        actions.appendChild(delBtn);
      }

      item.appendChild(info);
      item.appendChild(actions);
      listEl.appendChild(item);
    });
  }

  // ── 持久化 ────────────────────────────────────────────────────────────────
  _loadCanvasTemplates() {
    try {
      return JSON.parse(localStorage.getItem(_csTplLsk(_CS_CANVAS_TEMPLATES_KEY)) || '[]');
    } catch { return []; }
  }

  async _saveCurrentAsTemplate(panelEl) {
    const shell = this._shell;
    const name  = await shell._promptText('保存为画布模板', '模板名称', `模板 ${new Date().toLocaleDateString()}`);
    if (!name) return;

    const cards       = shell._serializeCards ? shell._serializeCards() : [];
    const connections = shell._connection?.serialize ? shell._connection.serialize() : [];

    const tpl = {
      id:          `utpl_${Date.now().toString(36)}`,
      name,
      desc:        `${cards.length} 张卡片`,
      cards:       JSON.parse(JSON.stringify(cards)),
      connections: JSON.parse(JSON.stringify(connections)),
    };

    const tpls = this._loadCanvasTemplates();
    tpls.push(tpl);
    localStorage.setItem(_csTplLsk(_CS_CANVAS_TEMPLATES_KEY), JSON.stringify(tpls));

    // 刷新画布模板列表
    const listEl = panelEl?.querySelector('#csTplCanvasList');
    if (listEl) this._renderCanvasTemplates(listEl);
  }

  _deleteCanvasTemplate(id, listEl) {
    const tpls = this._loadCanvasTemplates().filter(t => t.id !== id);
    localStorage.setItem(_csTplLsk(_CS_CANVAS_TEMPLATES_KEY), JSON.stringify(tpls));
    this._renderCanvasTemplates(listEl);
  }

  // ── 应用画布模板（插入到当前画布）────────────────────────────────────────
  _applyCanvasTemplate(tpl) {
    const shell = this._shell;
    const cards = tpl.cards || [];
    if (!cards.length) return;

    // 计算偏移量：以视口中央为插入锚点
    const { col: centerCol, row: centerRow } = shell._viewportCenterCell();
    const minCol = cards.reduce((m, c) => Math.min(m, c.col_start || 1), Infinity);
    const minRow = cards.reduce((m, c) => Math.min(m, c.row_start || 1), Infinity);
    const offsetC = centerCol - minCol;
    const offsetR = centerRow - minRow;

    // 生成新 ID 映射（避免与现有卡片 ID 冲突）
    const idMap = {};
    cards.forEach(c => {
      idMap[c.id] = `c_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 6)}`;
    });

    // 插入卡片：传 null/null 使 addCard 使用 def 内的 col_start/row_start
    cards.forEach(c => {
      const newDef = {
        ...c,
        id:        idMap[c.id],
        col_start: Math.max(1, (c.col_start || 1) + offsetC),
        row_start: Math.max(1, (c.row_start || 1) + offsetR),
        config:    JSON.parse(JSON.stringify(c.config || {})),
      };
      shell.addCard(newDef, null, null);
    });

    // 插入连线（重映射 ID，追加到现有连线）
    if (tpl.connections?.length && shell._connection) {
      tpl.connections.forEach(conn => {
        const newId = `conn_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 6)}`;
        shell._connection.addConnection({
          id:       newId,
          from:     idMap[conn.from] || conn.from,
          fromPort: conn.fromPort,
          to:       idMap[conn.to]   || conn.to,
          toPort:   conn.toPort,
          label:    conn.label || '',
        });
      });
      shell._connection.refresh(shell._cardFrames);
    }

    shell._markDirty?.();
  }

  // ── 卡片模板实例化 ────────────────────────────────────────────────────────
  instantiate(templateId) {
    const tpl = this._cardTpls.find(t => t.id === templateId);
    if (!tpl) return null;
    return {
      ...tpl.cardDef,
      id:     `c_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
      config: JSON.parse(JSON.stringify(tpl.cardDef.config || {})),
    };
  }
}

function _escHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

window.TemplateLibrary = TemplateLibrary;
