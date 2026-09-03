/**
 * web/components/import_export.js
 * ─────────────────────────────────
 * 通用导入导出管理器
 *
 * 用法：
 *   const mgr = new ImportExportManager({
 *     moduleId: 'factory_resource',
 *     columns:  FR_COLS,
 *     getRows:  () => vm.applyView(_all).filter(r => !r._isGroupHeader),
 *     onImport: async (rows, fieldMap, conflictMode) => { ... }
 *   });
 *   document.getElementById('btnImport').addEventListener('click', () => mgr.showImport());
 *   document.getElementById('btnExport').addEventListener('click', () => mgr.showExport());
 */
'use strict';

class ImportExportManager {
  constructor({ moduleId, columns, getRows, onImport, colAliasMap }) {
    this._moduleId = moduleId;
    this._columns  = (columns || []).filter(c => c.key !== '_actions');
    this._getRows  = getRows  || (() => []);
    this._onImport = onImport || (async () => {});
    this._colAliasMap = colAliasMap || {};

    this._overlay  = null;
    this._modal    = null;
    this._abortCtrl = null;

    // 导入流程状态
    this._importState = {
      step: 1,         // 1~4
      source: 'excel', // 'excel' | 'lark_sheet' | 'lark_bitable'
      parsed: null,    // { headers, rows, warnings }
      fieldMap: {},    // sourceHeader → targetKey | '__ignore__'
      conflict: 'skip',// 'skip' | 'overwrite' | 'append'
    };

    // 导出流程状态
    this._exportState = {
      format: 'excel',  // 'excel' | 'lark_sheet' | 'lark_bitable'
      templateGid: '__default__',
      templates: [],
      editingTemplate: null, // gid | null（null = 新建）
      templateEditor: null,
    };

    this._buildDOM();
  }

  // ────────────────────────────────────────────────────────────────────────────
  // 公开 API
  // ────────────────────────────────────────────────────────────────────────────

  showImport() {
    this._resetImport();
    this._showImportModal();
  }

  showExport() {
    this._loadTemplates().then(() => this._showExportModal());
  }

  destroy() {
    this._overlay?.remove();
  }

  // ────────────────────────────────────────────────────────────────────────────
  // DOM 构建
  // ────────────────────────────────────────────────────────────────────────────

  _buildDOM() {
    this._overlay = document.createElement('div');
    this._overlay.className = 'ie-overlay';
    this._overlay.innerHTML = `
      <div class="ie-modal" id="ie-modal-inner">
        <div class="ie-modal-header">
          <span class="ie-modal-title" id="ie-modal-title">导入</span>
          <button class="ie-modal-close" id="ie-close-btn">✕</button>
        </div>
        <div id="ie-steps-wrap"></div>
        <div class="ie-modal-body" id="ie-modal-body"></div>
        <div class="ie-modal-footer" id="ie-modal-footer"></div>
      </div>
    `;
    document.body.appendChild(this._overlay);

    this._overlay.querySelector('#ie-close-btn').addEventListener('click', () => this._close());
    this._overlay.addEventListener('click', e => {
      if (e.target === this._overlay) this._close();
    });
  }

  _close() {
    this._abortCtrl?.abort();
    this._abortCtrl = null;
    this._overlay.classList.remove('ie-show');
  }

  _setTitle(t) {
    this._overlay.querySelector('#ie-modal-title').textContent = t;
  }

  _setBody(html) {
    this._overlay.querySelector('#ie-modal-body').innerHTML = html;
  }

  _setFooter(html) {
    this._overlay.querySelector('#ie-modal-footer').innerHTML = html;
  }

  _setSteps(steps, current) {
    const wrap = this._overlay.querySelector('#ie-steps-wrap');
    if (!steps || !steps.length) { wrap.innerHTML = ''; return; }
    const parts = [];
    steps.forEach((label, i) => {
      const idx = i + 1;
      let cls = '';
      if (idx < current)      cls = 'done';
      else if (idx === current) cls = 'active';
      const dot = idx < current ? '✓' : idx;
      parts.push(`<div class="ie-step ${cls}"><div class="ie-step-dot">${dot}</div><span class="ie-step-label">${label}</span></div>`);
      if (i < steps.length - 1) parts.push('<div class="ie-step-line"></div>');
    });
    wrap.innerHTML = `<div class="ie-steps">${parts.join('')}</div>`;
  }

  // ────────────────────────────────────────────────────────────────────────────
  // 导入流程
  // ────────────────────────────────────────────────────────────────────────────

  _resetImport() {
    this._importState = {
      step: 1, source: 'excel', parsed: null,
      fieldMap: {}, conflict: 'skip',
      _browserFilePicked: null, _parsing: false,
    };
  }

  _showImportModal() {
    this._setTitle('导入数据');
    this._overlay.classList.add('ie-show');
    this._renderImportStep(1);
  }

  _renderImportStep(step) {
    this._importState.step = step;
    const STEPS = ['选择来源', '字段映射', '冲突处理', '确认导入'];
    this._setSteps(STEPS, step);

    switch (step) {
      case 1: this._renderImportStep1(); break;
      case 2: this._renderImportStep2(); break;
      case 3: this._renderImportStep3(); break;
      case 4: this._renderImportStep4(); break;
    }
  }

  // Step 1：来源选择
  _renderImportStep1() {
    const src = this._importState.source;
    this._setBody(`
      <p style="font-size:13px;color:var(--text-muted,#a6adc8);margin:0 0 14px">选择数据来源：</p>
      <div class="ie-source-grid">
        <div class="ie-source-card ${src==='excel'?'selected':''}" data-src="excel">
          <div class="ie-source-icon"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 3v18"/></svg></div>
          <div class="ie-source-label">Excel / CSV 文件</div>
          <div class="ie-source-desc">.xlsx / .xls / .xlsm / .csv</div>
        </div>
        <div class="ie-source-card ${src==='lark_sheet'?'selected':''}" data-src="lark_sheet">
          <div class="ie-source-icon"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 4h16v16H4z"/><path d="M4 9h16M4 14h16M9 4v16"/></svg></div>
          <div class="ie-source-label">飞书电子表格</div>
          <div class="ie-source-desc">需飞书登录</div>
        </div>
        <div class="ie-source-card ${src==='lark_bitable'?'selected':''}" data-src="lark_bitable">
          <div class="ie-source-icon"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="8" height="8" rx="1"/><rect x="13" y="3" width="8" height="8" rx="1"/><rect x="3" y="13" width="8" height="8" rx="1"/><rect x="13" y="13" width="8" height="8" rx="1"/></svg></div>
          <div class="ie-source-label">飞书多维表</div>
          <div class="ie-source-desc">需飞书登录</div>
        </div>
      </div>

      <div id="ie-src-extra" style="margin-top:16px;"></div>
    `);

    // 来源卡片选择
    this._overlay.querySelectorAll('.ie-source-card').forEach(card => {
      card.addEventListener('click', () => {
        this._overlay.querySelectorAll('.ie-source-card').forEach(c => c.classList.remove('selected'));
        card.classList.add('selected');
        this._importState.source = card.dataset.src;
        this._renderStep1Extra();
      });
    });

    this._renderStep1Extra();

    this._setFooter(`
      <button class="ie-btn ie-btn-ghost" id="ie-cancel-btn">取消</button>
      <button class="ie-btn ie-btn-primary" id="ie-next-btn">下一步</button>
    `);
    this._overlay.querySelector('#ie-cancel-btn').addEventListener('click', () => this._close());
    this._overlay.querySelector('#ie-next-btn').addEventListener('click', () => this._step1Next());
  }

  _renderStep1Extra() {
    const wrap = this._overlay.querySelector('#ie-src-extra');
    if (!wrap) return;
    const src = this._importState.source;
    if (src === 'excel') {
      wrap.innerHTML = `
        <div style="margin-top:4px">
          <div style="position:relative;display:inline-block;width:100%">
            <input type="file" accept=".xlsx,.xls,.xlsm,.csv"
                   id="ie-excel-file-input"
                   style="position:absolute;inset:0;opacity:0;cursor:pointer;width:100%">
            <button class="ie-btn ie-btn-primary"
                    style="width:100%;padding:10px 0;font-size:14px;pointer-events:none">
              选择 Excel / CSV 文件
            </button>
          </div>
          <p style="font-size:11px;color:var(--text-muted,#a6adc8);margin:6px 0 0">支持 .xlsx / .xls / .xlsm / .csv</p>
        </div>
      `;
      // 选完文件自动解析上传 → 跳过下一步按钮，直接在这个 handler 里完成
      const fileInput = wrap.querySelector('#ie-excel-file-input');
      const _cf = this._cf.bind(this);
      fileInput.addEventListener('change', async () => {
        const file = fileInput.files?.[0];
        fileInput.value = '';
        if (!file) return;
        if (this._importState._parsing) return;
        this._importState._parsing = true;
        this._showBodyStatus('正在读取并解析文件…');
        try {
          const b64 = await _readBrowserFile(file);
          if (!b64) throw new Error('文件读取结果为空');
          const data = await _cf('POST', '/api/import-export/import/parse-excel', {
            file_b64: b64,
            filename: file.name,
          });
          this._importState.parsed = data;
          this._renderImportStep(2);
        } catch (e) {
          this._showError(e.message || '读取失败');
        } finally {
          this._importState._parsing = false;
        }
      });
    } else if (src === 'lark_sheet') {
      wrap.innerHTML = `
        <div class="ie-field-group">
          <label>飞书电子表格 Token（URL 中 spreadsheets/ 后面的部分）</label>
          <input class="ie-input" id="ie-lark-token" type="text" placeholder="e.g. shtcnxxxxxxxxxxxxx" />
        </div>
        <div class="ie-field-group">
          <label>读取范围（默认第一个 sheet 前1000行）</label>
          <input class="ie-input" id="ie-lark-range" type="text" value="Sheet1!A1:Z1000" />
        </div>
      `;
    } else if (src === 'lark_bitable') {
      wrap.innerHTML = `
        <div class="ie-field-group">
          <label>多维表 App Token（URL 中 base/ 后面的部分）</label>
          <input class="ie-input" id="ie-bitable-app" type="text" placeholder="e.g. bascnxxxxxxxxxxxxx" />
        </div>
        <div class="ie-field-group">
          <label>Table ID（多维表中的数据表 ID）</label>
          <input class="ie-input" id="ie-bitable-table" type="text" placeholder="e.g. tblxxxxxxxxxxxxx" />
        </div>
      `;
    } else {
      wrap.innerHTML = '';
    }
  }

  async _step1Next() {
    if (this._importState._parsing) return;
    const src = this._importState.source;
    const btn = this._overlay.querySelector('#ie-next-btn');
    this._importState._parsing = true;
    btn.disabled = true;
    btn.textContent = '读取中…';

    try {
      if (src === 'excel') {
        await this._parseExcelFile();
      } else if (src === 'lark_sheet') {
        await this._parseLarkSheet();
      } else if (src === 'lark_bitable') {
        await this._parseLarkBitable();
      }
      this._renderImportStep(2);
    } catch (e) {
      this._showError(e.message || '读取失败');
    } finally {
      this._importState._parsing = false;
      btn.disabled = false;
      btn.textContent = '下一步';
    }
  }

  async _parseExcelFile() {
    const _cf = this._cf.bind(this);
    const eAPI = _getElectronAPI();
    let fileB64  = null;
    let filename = 'unknown.xlsx';

    if (eAPI?.openFileDialog) {
      // Electron 环境：系统文件对话框
      const filePath = await eAPI.openFileDialog([
        { name: 'Excel / CSV 文件', extensions: ['xlsx', 'xls', 'xlsm', 'csv'] },
        { name: '所有文件', extensions: ['*'] },
      ]);
      if (!filePath) throw new Error('未选择文件');
      fileB64  = await _readFileAsBase64(filePath);
      filename = filePath.split(/[\\/]/).pop();
    } else {
      // 浏览器环境：由「选择文件」按钮同步触发，数据存入了 _browserFilePicked
      if (!this._importState._browserFilePicked) throw new Error('请先点击「选择 Excel / CSV 文件」按钮');
      fileB64  = this._importState._browserFilePicked.b64;
      filename = this._importState._browserFilePicked.name;
    }

    if (!fileB64) throw new Error('无法读取文件');

    const data = await _cf('POST', '/api/import-export/import/parse-excel', {
      file_b64: fileB64,
      filename,
    });
    this._importState.parsed = data;
  }

  async _parseLarkSheet() {
    const _cf = this._cf.bind(this);
    const token = this._overlay.querySelector('#ie-lark-token')?.value.trim();
    const range = this._overlay.querySelector('#ie-lark-range')?.value.trim() || 'Sheet1!A1:Z1000';
    if (!token) throw new Error('请输入飞书电子表格 Token');
    const userToken = _getLarkToken();
    if (!userToken) throw new Error('请先飞书登录后再导入飞书表格');
    const data = await _cf('POST', '/api/import-export/lark-sheets/read', {
      user_access_token: userToken,
      spreadsheet_token: token,
      sheet_range: range,
    });
    this._importState.parsed = data;
  }

  async _parseLarkBitable() {
    const _cf = this._cf.bind(this);
    const appToken   = this._overlay.querySelector('#ie-bitable-app')?.value.trim();
    const tableId    = this._overlay.querySelector('#ie-bitable-table')?.value.trim();
    if (!appToken || !tableId) throw new Error('请填写 App Token 和 Table ID');
    const userToken = _getLarkToken();
    if (!userToken) throw new Error('请先飞书登录后再导入飞书多维表');
    const data = await _cf('POST', '/api/import-export/lark-bitable/read', {
      user_access_token: userToken,
      app_token: appToken,
      table_id: tableId,
    });
    this._importState.parsed = data;
  }

  // Step 2：预览 + 字段映射
  _renderImportStep2() {
    const { parsed } = this._importState;
    const { headers, rows, warnings } = parsed;
    const targetOpts = [
      '<option value="__ignore__">忽略</option>',
      ...this._columns.map(c => `<option value="${c.key}">${c.label}</option>`),
    ].join('');

    // 初始化 fieldMap：尝试按名称自动匹配
    const fieldMap = {};
    headers.forEach(h => {
      const match = this._columns.find(c =>
        c.label === h || c.key === h ||
        c.label?.toLowerCase() === h?.toLowerCase()
      );
      if (match) { fieldMap[h] = match.key; return; }
      // fallback: colAliasMap（Excel 中文列名 → DB 字段 key）
      const aliasKey = this._colAliasMap[h];
      if (aliasKey && this._columns.some(c => c.key === aliasKey)) {
        fieldMap[h] = aliasKey; return;
      }
      fieldMap[h] = '__ignore__';
    });
    this._importState.fieldMap = fieldMap;

    const warningBlock = warnings.length ? `
      <button class="ie-warnings-toggle" id="ie-warn-toggle">${warnings.length} 条警告 ▾</button>
      <div class="ie-warnings-list" id="ie-warn-list">
        ${warnings.map(w => `<div>• ${_ieEsc(w)}</div>`).join('')}
      </div>
    ` : '';

    this._setBody(`
      <div class="ie-preview-stat">
        <span class="ie-stat-badge ok">共 ${rows.length} 行</span>
        ${warnings.length ? `<span class="ie-stat-badge warn">${warnings.length} 条警告</span>` : ''}
        ${warningBlock}
      </div>
      <table class="ie-mapping-table">
        <thead><tr>
          <th style="width:28px"></th>
          <th>源列名</th>
          <th>映射到目标字段</th>
        </tr></thead>
        <tbody id="ie-mapping-body">
          ${headers.map(h => `
            <tr>
              <td class="ie-drag-handle">☰</td>
              <td><label style="display:flex;align-items:center;gap:8px">
                <input type="checkbox" class="ie-map-chk" data-hdr="${_ieEsc(h)}" checked
                  style="accent-color:var(--color-accent,#89b4fa)" />
                ${_ieEsc(h)}
              </label></td>
              <td><select class="ie-mapping-select" data-hdr="${_ieEsc(h)}">
                ${targetOpts}
              </select></td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `);

    // 设置已匹配的 select 值
    this._overlay.querySelectorAll('.ie-mapping-select').forEach(sel => {
      const h = sel.dataset.hdr;
      sel.value = fieldMap[h] || '__ignore__';
      sel.addEventListener('change', e => {
        this._importState.fieldMap[e.target.dataset.hdr] = e.target.value;
      });
    });

    // 警告折叠
    const toggle = this._overlay.querySelector('#ie-warn-toggle');
    const list   = this._overlay.querySelector('#ie-warn-list');
    toggle?.addEventListener('click', () => list.classList.toggle('show'));

    this._setFooter(`
      <button class="ie-btn ie-btn-ghost" id="ie-back-btn">上一步</button>
      <button class="ie-btn ie-btn-primary" id="ie-next-btn">下一步</button>
    `);
    this._overlay.querySelector('#ie-back-btn').addEventListener('click', () => this._renderImportStep(1));
    this._overlay.querySelector('#ie-next-btn').addEventListener('click', () => this._renderImportStep(3));
  }

  // Step 3：冲突处理
  _renderImportStep3() {
    const cur = this._importState.conflict;
    const opts = [
      { val: 'skip',      label: '跳过已存在',    desc: '若目标已有相同主键记录，则跳过，不修改' },
      { val: 'overwrite', label: '覆盖已存在',    desc: '若目标已有相同主键记录，则用新数据覆盖' },
      { val: 'append',    label: '全部追加（新增）', desc: '不检查重复，所有行均作为新记录追加' },
    ];
    this._setBody(`
      <p style="font-size:13px;color:var(--text-muted,#a6adc8);margin:0 0 12px">当导入数据与现有记录冲突时：</p>
      <div class="ie-conflict-options">
        ${opts.map(o => `
          <label class="ie-conflict-option ${cur===o.val?'selected':''}" data-val="${o.val}">
            <input type="radio" name="ie-conflict" value="${o.val}" ${cur===o.val?'checked':''}/>
            <div>
              <div class="ie-conflict-option-label">${o.label}</div>
              <div class="ie-conflict-option-desc">${o.desc}</div>
            </div>
          </label>
        `).join('')}
      </div>
    `);

    this._overlay.querySelectorAll('.ie-conflict-option').forEach(opt => {
      opt.addEventListener('click', () => {
        this._importState.conflict = opt.dataset.val;
        this._overlay.querySelectorAll('.ie-conflict-option').forEach(o => o.classList.remove('selected'));
        opt.classList.add('selected');
        opt.querySelector('input').checked = true;
      });
    });

    this._setFooter(`
      <button class="ie-btn ie-btn-ghost" id="ie-back-btn">上一步</button>
      <button class="ie-btn ie-btn-primary" id="ie-next-btn">下一步</button>
    `);
    this._overlay.querySelector('#ie-back-btn').addEventListener('click', () => this._renderImportStep(2));
    this._overlay.querySelector('#ie-next-btn').addEventListener('click', () => this._renderImportStep(4));
  }

  // Step 4：确认
  _renderImportStep4() {
    const { parsed, fieldMap, conflict } = this._importState;
    const mappedCount = Object.values(fieldMap).filter(v => v !== '__ignore__').length;
    const conflictLabel = { skip: '跳过已存在', overwrite: '覆盖已存在', append: '全部追加' }[conflict];

    this._setBody(`
      <p style="font-size:13px;color:var(--text-muted,#a6adc8);margin:0 0 12px">请确认以下导入信息：</p>
      <div class="ie-confirm-summary">
        <div class="ie-summary-row">
          <span class="ie-summary-label">数据来源</span>
          <span class="ie-summary-value">${{ excel:'Excel 文件', lark_sheet:'飞书电子表格', lark_bitable:'飞书多维表' }[this._importState.source]}</span>
        </div>
        <div class="ie-summary-row">
          <span class="ie-summary-label">数据行数</span>
          <span class="ie-summary-value">${parsed.rows.length} 行</span>
        </div>
        <div class="ie-summary-row">
          <span class="ie-summary-label">已映射字段</span>
          <span class="ie-summary-value">${mappedCount} 个</span>
        </div>
        <div class="ie-summary-row">
          <span class="ie-summary-label">冲突处理</span>
          <span class="ie-summary-value">${conflictLabel}</span>
        </div>
      </div>
      <div id="ie-import-progress" style="display:none;margin-top:14px">
        <div class="ie-progress-wrap"><div class="ie-progress-bar" id="ie-prog-bar" style="width:0%"></div></div>
        <div class="ie-progress-label" id="ie-prog-label">准备中…</div>
      </div>
      <div id="ie-import-error" style="display:none;color:#f38ba8;font-size:13px;margin-top:10px;"></div>
    `);

    this._setFooter(`
      <button class="ie-btn ie-btn-ghost" id="ie-back-btn">上一步</button>
      <button class="ie-btn ie-btn-primary" id="ie-confirm-btn">开始导入</button>
    `);
    this._overlay.querySelector('#ie-back-btn').addEventListener('click', () => this._renderImportStep(3));
    this._overlay.querySelector('#ie-confirm-btn').addEventListener('click', () => this._doImport());
  }

  async _doImport() {
    const { parsed, fieldMap, conflict } = this._importState;
    const confirmBtn = this._overlay.querySelector('#ie-confirm-btn');
    const backBtn    = this._overlay.querySelector('#ie-back-btn');
    const progWrap   = this._overlay.querySelector('#ie-import-progress');
    const progBar    = this._overlay.querySelector('#ie-prog-bar');
    const progLabel  = this._overlay.querySelector('#ie-prog-label');
    const errEl      = this._overlay.querySelector('#ie-import-error');

    confirmBtn.disabled = true;
    backBtn.disabled    = true;
    progWrap.style.display = '';
    errEl.style.display = 'none';

    // 将 parsed rows 转换为 { key: value } 对象
    const { headers, rows } = parsed;
    const mappedRows = rows.map(row => {
      const obj = {};
      headers.forEach((h, i) => {
        const targetKey = fieldMap[h];
        if (targetKey && targetKey !== '__ignore__') {
          obj[targetKey] = row[i];
        }
      });
      return obj;
    });

    try {
      this._abortCtrl = new AbortController();
      const signal = this._abortCtrl.signal;
      const total = mappedRows.length;
      progLabel.textContent = `正在导入 ${total} 条数据…`;
      progBar.style.width = '50%';
      const outcome = await this._onImport(mappedRows, fieldMap, conflict, signal);
      if (signal.aborted) return;
      if (outcome && Number.isInteger(outcome.created_count)) {
        progLabel.textContent = `导入完成：新增 ${outcome.created_count} 条，更新 ${outcome.updated_count || 0} 条，跳过 ${outcome.skipped_count || 0} 条`;
      } else {
        progLabel.textContent = `导入完成，共 ${total} 条`;
      }
      progBar.style.width = '100%';
      this._setFooter(`<button class="ie-btn ie-btn-primary" id="ie-done-btn">完成</button>`);
      this._overlay.querySelector('#ie-done-btn').addEventListener('click', () => this._close());
    } catch (e) {
      errEl.style.display = '';
      errEl.textContent = '导入出错：' + (e.message || String(e));
      confirmBtn.disabled = false;
      backBtn.disabled    = false;
    }
  }

  // ────────────────────────────────────────────────────────────────────────────
  // 导出流程
  // ────────────────────────────────────────────────────────────────────────────

  async _loadTemplates() {
    const _cf = this._cf.bind(this);
    try {
      const data = await _cf('GET', `/api/import-export/templates?module=${encodeURIComponent(this._moduleId)}`);
      this._exportState.templates = data || [];
    } catch {
      this._exportState.templates = [];
    }
  }

  _showExportModal() {
    this._setTitle('导出数据');
    this._overlay.classList.add('ie-show');
    this._setSteps([], 0);
    this._renderExportMain();
  }

  _renderExportMain() {
    const { format, templateGid, templates } = this._exportState;
    const rows = this._getRows();

    const tmplItems = [
      `<label class="ie-template-item ${templateGid==='__default__'?'selected':''}">
        <input type="radio" name="ie-tmpl" value="__default__" ${templateGid==='__default__'?'checked':''}/>
        <span class="ie-template-name">默认（当前可见列，无额外样式）</span>
      </label>`,
      ...templates.map(t => `
        <label class="ie-template-item ${templateGid===t.gid?'selected':''}" data-gid="${t.gid}">
          <input type="radio" name="ie-tmpl" value="${t.gid}" ${templateGid===t.gid?'checked':''}/>
          <span class="ie-template-name">${_ieEsc(t.name)}</span>
          ${t.is_shared ? '<span class="ie-template-badge">共享</span>' : ''}
          <button class="ie-template-edit-btn" data-gid="${t.gid}" data-action="edit">编辑</button>
        </label>
      `),
    ].join('');

    this._setBody(`
      <!-- 格式选择 -->
      <div class="ie-format-row">
        <button class="ie-format-btn ${format==='excel'?'selected':''}" data-fmt="excel">
          <div>📊</div>Excel (.xlsx)
        </button>
        <button class="ie-format-btn ${format==='lark_sheet'?'selected':''}" data-fmt="lark_sheet">
          <div>📋</div>飞书电子表格
        </button>
        <button class="ie-format-btn ${format==='lark_bitable'?'selected':''}" data-fmt="lark_bitable">
          <div>⊞</div>飞书多维表
        </button>
      </div>

      <!-- 飞书额外参数 -->
      <div id="ie-export-lark-extra"></div>

      <!-- 模板选择 -->
      <div class="ete-section-title" style="margin-bottom:8px">导出模板</div>
      <div class="ie-template-list">${tmplItems}</div>
      <button class="ie-add-template-btn" id="ie-new-tmpl-btn">＋ 新建模板</button>

      <!-- 数据范围 -->
      <div class="ie-range-hint" style="margin-top:14px">
        当前视图数据：共 <strong>${rows.length}</strong> 行（已含 ViewManager 筛选条件）
      </div>
    `);

    // 格式选择
    this._overlay.querySelectorAll('.ie-format-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        this._overlay.querySelectorAll('.ie-format-btn').forEach(b => b.classList.remove('selected'));
        btn.classList.add('selected');
        this._exportState.format = btn.dataset.fmt;
        this._renderExportLarkExtra();
      });
    });

    // 模板选择
    this._overlay.querySelectorAll('input[name="ie-tmpl"]').forEach(radio => {
      radio.addEventListener('change', e => {
        this._exportState.templateGid = e.target.value;
        this._overlay.querySelectorAll('.ie-template-item').forEach(i => i.classList.remove('selected'));
        e.target.closest('.ie-template-item')?.classList.add('selected');
      });
    });

    // 编辑模板按钮
    this._overlay.querySelectorAll('[data-action="edit"]').forEach(btn => {
      btn.addEventListener('click', e => {
        e.preventDefault(); e.stopPropagation();
        const gid = btn.dataset.gid;
        const tmpl = this._exportState.templates.find(t => t.gid === gid);
        this._showTemplateEditor(gid, tmpl?.config || {}, tmpl?.name || '');
      });
    });

    // 新建模板
    this._overlay.querySelector('#ie-new-tmpl-btn').addEventListener('click', () => {
      this._showTemplateEditor(null, {}, '');
    });

    this._renderExportLarkExtra();

    this._setFooter(`
      <button class="ie-btn ie-btn-ghost" id="ie-cancel-btn">取消</button>
      <button class="ie-btn ie-btn-primary" id="ie-export-btn">导出</button>
    `);
    this._overlay.querySelector('#ie-cancel-btn').addEventListener('click', () => this._close());
    this._overlay.querySelector('#ie-export-btn').addEventListener('click', () => this._doExport());
  }

  _renderExportLarkExtra() {
    const wrap = this._overlay.querySelector('#ie-export-lark-extra');
    if (!wrap) return;
    const fmt = this._exportState.format;
    if (fmt === 'lark_sheet') {
      wrap.innerHTML = `
        <div class="ie-field-group">
          <label>飞书电子表格 Token</label>
          <input class="ie-input" id="ie-exp-lark-token" type="text" placeholder="spreadsheet token" />
        </div>
        <div class="ie-field-group">
          <label>Sheet ID（如 "Sheet1"）</label>
          <input class="ie-input" id="ie-exp-lark-sheet" type="text" value="Sheet1" />
        </div>
      `;
    } else if (fmt === 'lark_bitable') {
      wrap.innerHTML = `
        <div class="ie-field-group">
          <label>多维表 App Token</label>
          <input class="ie-input" id="ie-exp-bitable-app" type="text" placeholder="app token" />
        </div>
        <div class="ie-field-group">
          <label>Table ID</label>
          <input class="ie-input" id="ie-exp-bitable-table" type="text" placeholder="tbl..." />
        </div>
      `;
    } else {
      wrap.innerHTML = '';
    }
  }

  // 模板编辑器（内嵌在 modal body 内切换视图）
  _showTemplateEditor(gid, initialConfig, initialName) {
    this._setTitle(gid ? '编辑模板' : '新建模板');
    this._setSteps([], 0);

    const editorContainer = document.createElement('div');
    this._overlay.querySelector('#ie-modal-body').innerHTML = '';
    this._overlay.querySelector('#ie-modal-body').appendChild(editorContainer);

    const editor = new ExportTemplateEditor({
      container: editorContainer,
      columns:   this._columns,
      initialConfig,
      onSave:    null,
      onCancel:  null,
    });

    // 如果有初始名称
    if (initialName) {
      const nameInp = editorContainer.querySelector('#ete-tmpl-name');
      if (nameInp) nameInp.value = initialName;
    }

    this._setFooter(`
      <button class="ie-btn ie-btn-ghost" id="ie-tmpl-cancel">取消</button>
      <button class="ie-btn ie-btn-primary" id="ie-tmpl-save">保存模板</button>
    `);
    this._overlay.querySelector('#ie-tmpl-cancel').addEventListener('click', async () => {
      await this._loadTemplates();
      this._renderExportMain();
      this._setTitle('导出数据');
    });
    this._overlay.querySelector('#ie-tmpl-save').addEventListener('click', async () => {
      const _cf = this._cf.bind(this);
      const config   = editor.getConfig();
      const name     = editor.getName() || '未命名模板';
      const isShared = editor.getIsShared();
      try {
        if (gid) {
          await _cf('PATCH', `/api/import-export/templates/${gid}`, { name, config, is_shared: isShared });
        } else {
          const resp = await _cf('POST', '/api/import-export/templates', {
            name, module: this._moduleId, config, is_shared: isShared,
          });
          if (resp?.gid) this._exportState.templateGid = resp.gid;
        }
        await this._loadTemplates();
        this._renderExportMain();
        this._setTitle('导出数据');
      } catch (e) {
        this._showError(e.message || '保存模板失败');
      }
    });
  }

  async _doExport() {
    const { format, templateGid, templates } = this._exportState;
    const rows    = this._getRows();
    const expBtn  = this._overlay.querySelector('#ie-export-btn');
    expBtn.disabled = true;
    expBtn.textContent = '导出中…';

    try {
      // 构建 template_config
      let tmplConfig;
      if (templateGid === '__default__') {
        tmplConfig = {
          columns: this._columns.map(c => ({
            key: c.key, label: c.label,
            width: Math.round((c.width || 100) / 8),
            include: true,
          })),
          styles: { headerBg: '#2563EB', headerFg: '#FFFFFF', altRowBg: '#EFF6FF', borderStyle: 'thin', fontSize: 11 },
        };
      } else {
        const tmpl = templates.find(t => t.gid === templateGid);
        tmplConfig = tmpl?.config || {};
      }

      if (format === 'excel') {
        await this._exportToExcel(tmplConfig, rows);
      } else if (format === 'lark_sheet') {
        await this._exportToLarkSheet(tmplConfig, rows);
      } else if (format === 'lark_bitable') {
        await this._exportToLarkBitable(tmplConfig, rows);
      }
      this._close();
    } catch (e) {
      this._showError(e.message || '导出失败');
    } finally {
      expBtn.disabled = false;
      expBtn.textContent = '导出';
    }
  }

  async _exportToExcel(tmplConfig, rows) {
    const _cf = this._cf.bind(this);
    const resp = await _cf('POST', '/api/import-export/export/excel', {
      template_config: tmplConfig,
      rows,
    });
    if (!resp?.file_b64) throw new Error('后端未返回文件数据');

    const eAPI = _getElectronAPI();
    const filename = resp.filename || 'export.xlsx';
    let savePath = null;
    if (eAPI?.saveFileDialog) {
      savePath = await eAPI.saveFileDialog({
        title: '保存 Excel 文件',
        defaultPath: filename,
        filters: [{ name: 'Excel 文件', extensions: ['xlsx'] }],
      });
    }
    if (!savePath) return; // 用户取消

    // base64 → 二进制写文件
    // 通过 writeTextFile 不行（utf-8），需要 Electron IPC 写 binary
    // 改用临时方案：base64 to blob → download link（适用于 Electron renderer）
    _saveBase64AsFile(resp.file_b64, savePath, eAPI);
  }

  async _exportToLarkSheet(tmplConfig, rows) {
    const _cf = this._cf.bind(this);
    const token   = this._overlay.querySelector('#ie-exp-lark-token')?.value.trim();
    const sheetId = this._overlay.querySelector('#ie-exp-lark-sheet')?.value.trim() || 'Sheet1';
    if (!token) throw new Error('请输入飞书电子表格 Token');
    const userToken = _getLarkToken();
    if (!userToken) throw new Error('请先飞书登录');

    const columns = (tmplConfig.columns || []).filter(c => c.include !== false);
    const headers = columns.map(c => c.label || c.key);
    const dataRows = rows.map(r => columns.map(c => {
      const v = r[c.key];
      return typeof v === 'object' ? JSON.stringify(v) : (v ?? '');
    }));

    await _cf('POST', '/api/import-export/lark-sheets/write', {
      user_access_token: userToken,
      spreadsheet_token: token,
      sheet_id: sheetId,
      headers,
      rows: dataRows,
    });
  }

  async _exportToLarkBitable(tmplConfig, rows) {
    const _cf = this._cf.bind(this);
    const appToken = this._overlay.querySelector('#ie-exp-bitable-app')?.value.trim();
    const tableId  = this._overlay.querySelector('#ie-exp-bitable-table')?.value.trim();
    if (!appToken || !tableId) throw new Error('请填写 App Token 和 Table ID');
    const userToken = _getLarkToken();
    if (!userToken) throw new Error('请先飞书登录');

    const columns = (tmplConfig.columns || []).filter(c => c.include !== false);
    const records = rows.map(r => {
      const fields = {};
      columns.forEach(c => { fields[c.label || c.key] = r[c.key] ?? ''; });
      return fields;
    });

    await _cf('POST', '/api/import-export/lark-bitable/write', {
      user_access_token: userToken,
      app_token: appToken,
      table_id: tableId,
      records,
    });
  }

  // ────────────────────────────────────────────────────────────────────────────
  // 工具：云端 API 调用
  // ────────────────────────────────────────────────────────────────────────────

  async _cf(method, path, body) {
    const fn = window.top?._cloudFetch || window.parent?._cloudFetch || window._cloudFetch;
    if (!fn) throw new Error('_cloudFetch 未就绪');
    const opts = { method };
    if (body !== undefined) opts.body = JSON.stringify(body);
    const resp = await fn(path, opts);
    if (!resp?.success) throw new Error(resp?.message || 'API 调用失败');
    return resp.data;
  }

  // ────────────────────────────────────────────────────────────────────────────
  // 错误提示
  // ────────────────────────────────────────────────────────────────────────────

  _showError(msg) {
    const body = this._overlay.querySelector('#ie-modal-body');
    const existing = body?.querySelector('.ie-inline-error');
    if (existing) existing.remove();
    if (!body) return;
    const err = document.createElement('div');
    err.className = 'ie-inline-error';
    err.style.cssText = 'color:#f38ba8;font-size:13px;margin-top:10px;padding:8px 12px;background:rgba(243,139,168,0.1);border-radius:6px;border:1px solid rgba(243,139,168,0.3)';
    err.textContent = msg;
    body.appendChild(err);
  }

  _showBodyStatus(msg) {
    const body = this._overlay.querySelector('#ie-modal-body');
    const er = body?.querySelector('.ie-inline-error');
    if (er) er.remove();
    if (body) {
      body.innerHTML = `<p style="color:var(--text-muted,#a6adc8);text-align:center;padding:20px;font-size:14px">${msg}</p>`;
    }
  }
}

// ── 模块级工具函数 ─────────────────────────────────────────────────────────────

function _ieEsc(s) {
  if (!s) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/** 浏览器环境：FileReader 读取 File 对象为 base64 字符串 */
function _readBrowserFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload  = () => resolve((reader.result || '').split(',')[1]);
    reader.onerror = () => reject(new Error('FileReader 读取失败'));
    reader.readAsDataURL(file);
  });
}

/** 沿 iframe 链查找 electronAPI（支持多层嵌套） */
function _getElectronAPI() {
  let w = window;
  for (let i = 0; i < 5; i++) {
    if (w.electronAPI) return w.electronAPI;
    if (w === w.parent) break;
    try { w = w.parent; } catch { break; }
  }
  return null;
}

/** 获取已登录飞书用户的 access_token */
function _getLarkToken() {
  const authUser = window.parent?._authUser || window._authUser;
  return authUser?.access_token || null;
}

/** 读取本地文件为 base64（通过 Electron IPC fs:read-binary，降级用 FileReader） */
async function _readFileAsBase64(filePath) {
  const eAPI = _getElectronAPI();
  // 优先使用 Electron IPC（在 iframe 中 file:// fetch 不可用）
  if (eAPI?.readFileBase64) {
    const b64 = await eAPI.readFileBase64(filePath);
    if (b64) return b64;
  }
  // 降级：fetch file:// 协议（仅主窗口中可用）
  try {
    const resp = await fetch('file://' + filePath.replace(/\\/g, '/'));
    const buf  = await resp.arrayBuffer();
    const bytes = new Uint8Array(buf);
    let binary = '';
    for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i]);
    return btoa(binary);
  } catch {
    throw new Error('无法读取文件，请确认文件路径有效');
  }
}

/** 将 base64 文件数据保存到指定路径（Electron 环境） */
function _saveBase64AsFile(b64, filePath, eAPI) {
  // 利用 blob URL + a.click 触发下载（适用于 Electron renderer）
  try {
    const byteStr = atob(b64);
    const ab = new ArrayBuffer(byteStr.length);
    const ia = new Uint8Array(ab);
    for (let i = 0; i < byteStr.length; i++) ia[i] = byteStr.charCodeAt(i);
    const blob = new Blob([ab], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    // Electron 中 download attribute 会使用 saveFileDialog 返回的路径
    a.download = filePath.split(/[\\/]/).pop();
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 1000);
  } catch (e) {
    console.error('[ImportExport] 文件保存失败:', e);
  }
}

