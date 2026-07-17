/**
 * web/components/export_template_editor.js
 * ──────────────────────────────────────────
 * 导出模板可视化编辑器
 *
 * 用法（在 ImportExportManager 内调用）：
 *   const editor = new ExportTemplateEditor({
 *     container: el,          // 挂载到此 DOM 元素内
 *     columns: COLS,          // [{key, label, width, ...}]
 *     initialConfig: {},      // 现有模板 config（可选）
 *     onSave: async (name, isShared, config) => { ... }
 *     onCancel: () => { ... }
 *   });
 */
'use strict';

class ExportTemplateEditor {
  constructor({ container, columns, initialConfig = {}, onSave, onCancel }) {
    this._container = container;
    this._columns   = columns.filter(c => c.key !== '_actions');
    this._onSave    = onSave;
    this._onCancel  = onCancel;

    // 从 initialConfig 初始化状态，或从 columns 构建默认值
    const savedCols = initialConfig.columns || [];
    this._colState  = this._columns.map(col => {
      const saved = savedCols.find(c => c.key === col.key);
      return {
        key:     col.key,
        label:   saved ? saved.label    : col.label,
        width:   saved ? saved.width    : (col.width ? Math.round(col.width / 8) : 15),
        include: saved ? saved.include  : true,
      };
    });

    const s = initialConfig.styles || {};
    this._styles = {
      headerBg:    s.headerBg    || '#2563EB',
      headerFg:    s.headerFg    || '#FFFFFF',
      altRowBg:    s.altRowBg    || '#EFF6FF',
      borderStyle: s.borderStyle || 'thin',
      fontSize:    s.fontSize    || 11,
    };

    this._render();
  }

  // ── 渲染整体结构 ──────────────────────────────────────────────────────────────

  _render() {
    this._container.innerHTML = `
      <div class="ete-container">

        <!-- 列配置 -->
        <div class="ete-section">
          <div class="ete-section-title">列配置</div>
          <div class="ete-col-list" id="ete-col-list"></div>
        </div>

        <!-- 样式配置 -->
        <div class="ete-section">
          <div class="ete-section-title">样式配置</div>
          <div class="ete-style-grid">
            ${this._styleField('headerBg',    '表头背景色')}
            ${this._styleField('headerFg',    '表头文字色')}
            ${this._styleField('altRowBg',    '交替行底色')}
            <div class="ete-style-item">
              <span class="ete-style-label">边框样式</span>
              <select class="ete-select" id="ete-borderStyle">
                ${['thin','medium','thick','dashed','dotted'].map(v =>
                  `<option value="${v}" ${this._styles.borderStyle===v?'selected':''}>${v}</option>`
                ).join('')}
              </select>
            </div>
            <div class="ete-style-item">
              <span class="ete-style-label">字号</span>
              <select class="ete-select" id="ete-fontSize">
                ${[9,10,11,12,14].map(v =>
                  `<option value="${v}" ${this._styles.fontSize==v?'selected':''}>${v}pt</option>`
                ).join('')}
              </select>
            </div>
          </div>
        </div>

        <!-- 实时预览 -->
        <div class="ete-preview-section">
          <div class="ete-preview-label">预览（模拟 Excel 外观）</div>
          <div class="ete-preview-table-wrap">
            <table class="ete-preview-table" id="ete-preview-table"></table>
          </div>
        </div>

        <!-- 底部：模板名 + 共享 -->
        <div class="ete-footer">
          <input class="ete-name-input" id="ete-tmpl-name" type="text"
            placeholder="模板名称（如：我的工厂资源模板）" />
          <label class="ete-shared-label">
            <input type="checkbox" id="ete-shared" />
            共享给团队
          </label>
        </div>

      </div>
    `;

    this._renderColList();
    this._bindStyleEvents();
    this._updatePreview();
  }

  // ── 列配置渲染 ────────────────────────────────────────────────────────────────

  _renderColList() {
    const list = this._container.querySelector('#ete-col-list');
    list.innerHTML = this._colState.map((col, i) => `
      <div class="ete-col-row" data-idx="${i}">
        <span class="ete-drag">☰</span>
        <input type="checkbox" ${col.include ? 'checked' : ''} data-idx="${i}" class="ete-chk" />
        <input class="ete-label-input" type="text" value="${_eteEsc(col.label)}"
          data-idx="${i}" data-field="label" placeholder="列标签" />
        <input class="ete-width-input" type="number" value="${col.width}"
          data-idx="${i}" data-field="width" min="5" max="100" title="列宽（字符数）" />
      </div>
    `).join('');

    // 事件：checkbox 切换
    list.querySelectorAll('.ete-chk').forEach(cb => {
      cb.addEventListener('change', e => {
        this._colState[+e.target.dataset.idx].include = e.target.checked;
        this._updatePreview();
      });
    });

    // 事件：label / width 输入
    list.querySelectorAll('.ete-label-input, .ete-width-input').forEach(inp => {
      inp.addEventListener('input', e => {
        const idx   = +e.target.dataset.idx;
        const field = e.target.dataset.field;
        this._colState[idx][field] = field === 'width' ? +e.target.value : e.target.value;
        if (field === 'label') this._updatePreview();
      });
    });

    // 拖拽排序（简单鼠标拖拽）
    this._initDragSort(list);
  }

  // ── 简单行拖拽排序 ────────────────────────────────────────────────────────────

  _initDragSort(list) {
    let dragging = null;
    list.querySelectorAll('.ete-drag').forEach(handle => {
      handle.addEventListener('mousedown', e => {
        e.preventDefault();
        const row = handle.closest('.ete-col-row');
        dragging = row;
        row.style.opacity = '0.5';
      });
    });

    list.addEventListener('mousemove', e => {
      if (!dragging) return;
      const target = e.target.closest('.ete-col-row');
      if (target && target !== dragging) {
        const rows = [...list.querySelectorAll('.ete-col-row')];
        const fromIdx = rows.indexOf(dragging);
        const toIdx   = rows.indexOf(target);
        if (fromIdx !== -1 && toIdx !== -1) {
          // 重排 colState
          const [item] = this._colState.splice(fromIdx, 1);
          this._colState.splice(toIdx, 0, item);
          this._renderColList();
          this._updatePreview();
          dragging = null;
        }
      }
    });

    document.addEventListener('mouseup', () => {
      if (dragging) { dragging.style.opacity = ''; dragging = null; }
    });
  }

  // ── 样式字段辅助 ──────────────────────────────────────────────────────────────

  _styleField(key, label) {
    const val = this._styles[key];
    return `
      <div class="ete-style-item">
        <span class="ete-style-label">${label}</span>
        <div class="ete-color-row">
          <div class="ete-color-swatch" id="ete-sw-${key}"
            style="background:${val}" title="${label}"></div>
          <input class="ete-color-input" id="ete-${key}" type="text"
            value="${val}" placeholder="#RRGGBB" maxlength="7" />
        </div>
      </div>
    `;
  }

  _bindStyleEvents() {
    ['headerBg', 'headerFg', 'altRowBg'].forEach(key => {
      const inp = this._container.querySelector(`#ete-${key}`);
      const sw  = this._container.querySelector(`#ete-sw-${key}`);
      if (!inp) return;
      inp.addEventListener('input', e => {
        const v = e.target.value;
        if (/^#[0-9A-Fa-f]{6}$/.test(v)) {
          this._styles[key] = v;
          if (sw) sw.style.background = v;
          this._updatePreview();
        }
      });
      // 点色块弹原生 color picker（需 input[type=color]）
      sw?.addEventListener('click', () => {
        const picker = document.createElement('input');
        picker.type = 'color';
        picker.value = this._styles[key];
        picker.style.display = 'none';
        document.body.appendChild(picker);
        picker.click();
        picker.addEventListener('input', pe => {
          this._styles[key] = pe.target.value;
          inp.value = pe.target.value;
          sw.style.background = pe.target.value;
          this._updatePreview();
        });
        picker.addEventListener('blur', () => picker.remove());
      });
    });

    const borderSel = this._container.querySelector('#ete-borderStyle');
    const fontSel   = this._container.querySelector('#ete-fontSize');
    borderSel?.addEventListener('change', e => {
      this._styles.borderStyle = e.target.value;
    });
    fontSel?.addEventListener('change', e => {
      this._styles.fontSize = +e.target.value;
    });
  }

  // ── 实时预览更新 ──────────────────────────────────────────────────────────────

  _updatePreview() {
    const table   = this._container.querySelector('#ete-preview-table');
    if (!table) return;
    const visCols = this._colState.filter(c => c.include);
    if (!visCols.length) { table.innerHTML = '<tr><td style="padding:8px;color:#888">（无可见列）</td></tr>'; return; }

    const { headerBg, headerFg, altRowBg, borderStyle } = this._styles;
    const bdr = `1px ${borderStyle === 'dashed' ? 'dashed' : borderStyle === 'dotted' ? 'dotted' : 'solid'} #ccc`;

    const thead = `<thead><tr>${visCols.map(c => `
      <th style="
        background:${headerBg};
        color:${headerFg};
        padding:6px 10px;
        border:${bdr};
        font-size:${this._styles.fontSize}px;
        font-weight:600;
        white-space:nowrap;
      ">${_eteEsc(c.label)}</th>
    `).join('')}</tr></thead>`;

    // 2 行示例数据
    const sampleRows = [
      visCols.map(c => _eteEsc(c.key)),
      visCols.map(c => '示例数据'),
    ];
    const tbody = `<tbody>${sampleRows.map((row, ri) => `
      <tr>${row.map(cell => `
        <td style="
          padding:5px 10px;
          border:${bdr};
          font-size:${this._styles.fontSize}px;
          background:${ri % 2 === 1 ? altRowBg : 'transparent'};
        ">${cell}</td>
      `).join('')}</tr>
    `).join('')}</tbody>`;

    table.innerHTML = thead + tbody;
  }

  // ── 获取当前 config ───────────────────────────────────────────────────────────

  getConfig() {
    return {
      columns: this._colState.map(c => ({ ...c })),
      styles:  { ...this._styles },
    };
  }

  getName()     { return this._container.querySelector('#ete-tmpl-name')?.value.trim() || ''; }
  getIsShared() { return this._container.querySelector('#ete-shared')?.checked || false; }
}

// 简单转义
function _eteEsc(s) {
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

