/**
 * web/components/diff_manager.js
 * ────────────────────────────────
 * 通用数据对比分析工具
 *
 * 用法：
 *   const dm = new DiffManager({
 *     moduleId:        'ebom',
 *     columns:         EBOM_COLS,          // 过滤掉 _actions 列
 *     loaders:         [...],              // 数据源配置数组
 *     defaultMatchKey: 'part_no',          // 默认匹配键
 *   });
 *   document.getElementById('btnDiff').addEventListener('click', () => dm.showDiff());
 *
 * loaders 数组元素结构：
 *   {
 *     id:       string,
 *     label:    string,
 *     loadList: async () => [{ id, label }],   // 数据集下拉列表
 *     loadRows: async (itemId) => rows,         // 加载行数据
 *   }
 */
'use strict';

class DiffManager {
  constructor({ moduleId, columns, loaders, defaultMatchKey }) {
    this._moduleId       = moduleId;
    this._columns        = (columns || []).filter(c => c.key !== '_actions');
    this._loaders        = loaders || [];
    this._defaultMatchKey = defaultMatchKey || (this._columns[0]?.key || 'id');

    // 内部状态
    this._step       = 1;
    this._selA       = { loaderId: this._loaders[0]?.id || '', itemId: '', rows: null };
    this._selB       = { loaderId: this._loaders[0]?.id || '', itemId: '', rows: null };
    this._matchKey   = this._defaultMatchKey;
    this._diffRows   = [];
    this._viewMode   = 'unified';  // 'unified' | 'sbs'
    this._onlyDiff   = true;

    this._overlay    = null;
    this._listCacheA = {};  // loaderId → [{ id, label }]
    this._listCacheB = {};

    this._buildDOM();
  }

  // ── 公开 API ──────────────────────────────────────────────────────────────

  showDiff() {
    this._step = 1;
    this._selA = { loaderId: this._loaders[0]?.id || '', itemId: '', rows: null };
    this._selB = { loaderId: this._loaders[0]?.id || '', itemId: '', rows: null };
    this._matchKey = this._defaultMatchKey;
    this._overlay.classList.add('dm-show');
    this._renderStep1();
  }

  destroy() {
    this._overlay?.remove();
  }

  // ── DOM 构建 ──────────────────────────────────────────────────────────────

  _buildDOM() {
    this._overlay = document.createElement('div');
    this._overlay.className = 'dm-overlay';
    this._overlay.innerHTML = `
      <div class="dm-modal">
        <div class="dm-modal-header">
          <span class="dm-modal-title">数据对比分析</span>
          <button class="dm-modal-close" id="dm-close">✕</button>
        </div>
        <div id="dm-steps-wrap"></div>
        <div class="dm-modal-body" id="dm-body"></div>
        <div class="dm-modal-footer" id="dm-footer"></div>
      </div>
    `;
    document.body.appendChild(this._overlay);
    this._overlay.querySelector('#dm-close').addEventListener('click', () => this._close());
    this._overlay.addEventListener('click', e => {
      if (e.target === this._overlay) this._close();
    });
  }

  _close() {
    this._overlay.classList.remove('dm-show');
  }

  _setBody(html) {
    this._overlay.querySelector('#dm-body').innerHTML = html;
  }

  _setFooter(html) {
    this._overlay.querySelector('#dm-footer').innerHTML = html;
  }

  _setSteps(current) {
    const steps = ['选择数据集', '对比结果'];
    const wrap  = this._overlay.querySelector('#dm-steps-wrap');
    const parts = [];
    steps.forEach((label, i) => {
      const idx = i + 1;
      let cls = '';
      if (idx < current)       cls = 'done';
      else if (idx === current) cls = 'active';
      const dot = idx < current ? '✓' : String(idx);
      parts.push(`<div class="dm-step ${cls}"><div class="dm-step-dot">${dot}</div><span class="dm-step-label">${label}</span></div>`);
      if (i < steps.length - 1) parts.push('<div class="dm-step-line"></div>');
    });
    wrap.innerHTML = `<div class="dm-steps">${parts.join('')}</div>`;
  }

  // ── Step 1：选择数据集 ───────────────────────────────────────────────────

  _renderStep1() {
    this._setSteps(1);
    this._setBody(`
      <div class="dm-source-grid">
        ${this._renderSourcePanel('a', '数据集 A（基准）', 'dm-source-panel-a')}
        ${this._renderSourcePanel('b', '数据集 B（对比）', 'dm-source-panel-b')}
      </div>
      <div class="dm-match-key-row">
        <label>匹配键（用哪列判断"同一条记录"）：</label>
        <select class="dm-select" id="dm-match-key" style="max-width:260px">
          ${this._columns.map(c =>
            `<option value="${_dmEsc(c.key)}" ${c.key === this._matchKey ? 'selected' : ''}>${_dmEsc(c.label)}</option>`
          ).join('')}
        </select>
      </div>
      <div id="dm-step1-error"></div>
    `);

    this._setFooter(`
      <button class="dm-btn dm-btn-ghost" id="dm-cancel">取消</button>
      <button class="dm-btn dm-btn-primary" id="dm-compare">开始对比 →</button>
    `);

    // 绑定事件
    ['a', 'b'].forEach(side => this._bindPanelEvents(side));

    this._overlay.querySelector('#dm-match-key').addEventListener('change', e => {
      this._matchKey = e.target.value;
    });
    this._overlay.querySelector('#dm-cancel').addEventListener('click', () => this._close());
    this._overlay.querySelector('#dm-compare').addEventListener('click', () => this._doCompare());
  }

  _renderSourcePanel(side, title, extraClass) {
    const loaderOpts = this._loaders.map(l =>
      `<option value="${_dmEsc(l.id)}">${_dmEsc(l.label)}</option>`
    ).join('');
    return `
      <div class="dm-source-panel ${extraClass || ''}">
        <div class="dm-source-panel-title">${title}</div>
        <div class="dm-field-group">
          <label>来源</label>
          <select class="dm-select" id="dm-loader-${side}">${loaderOpts}</select>
        </div>
        <div id="dm-panel-extra-${side}"></div>
      </div>
    `;
  }

  _bindPanelEvents(side) {
    const loaderSel = this._overlay.querySelector(`#dm-loader-${side}`);
    if (!loaderSel) return;

    const sel = side === 'a' ? this._selA : this._selB;
    sel.loaderId = loaderSel.value || this._loaders[0]?.id || '';

    // 切换 loader
    loaderSel.addEventListener('change', async () => {
      sel.loaderId = loaderSel.value;
      sel.itemId   = '';
      sel.rows     = null;
      await this._loadListForPanel(side);
    });

    // 立刻加载初始列表
    this._loadListForPanel(side);
  }

  async _loadListForPanel(side) {
    const sel     = side === 'a' ? this._selA : this._selB;
    const loader  = this._loaders.find(l => l.id === sel.loaderId);
    if (!loader) return;

    const extraEl = this._overlay.querySelector(`#dm-panel-extra-${side}`);
    if (!extraEl) return;

    if (loader.id === '__excel__') {
      // Excel 上传
      extraEl.innerHTML = `
        <div class="dm-field-group">
          <label>上传 Excel 文件</label>
          <div class="dm-upload-zone" id="dm-upload-zone-${side}" title="点击或拖拽上传">
            <div>📂 点击选择文件</div>
            <div id="dm-upload-hint-${side}" style="font-size:11px;margin-top:4px;"></div>
          </div>
          <input type="file" class="dm-upload-input" id="dm-file-input-${side}" accept=".xlsx,.xls" />
        </div>
      `;
      const zone  = extraEl.querySelector(`#dm-upload-zone-${side}`);
      const input = extraEl.querySelector(`#dm-file-input-${side}`);
      zone.addEventListener('click', () => input.click());
      input.addEventListener('change', async e => {
        const file = e.target.files[0];
        if (!file) return;
        const hint = extraEl.querySelector(`#dm-upload-hint-${side}`);
        hint.textContent = '解析中…';
        zone.classList.remove('has-file');
        try {
          const rows = await this._parseExcelFile(file);
          sel.rows   = rows;
          sel.itemId = '__excel__';
          zone.classList.add('has-file');
          hint.textContent = `✓ ${file.name}（${rows.length} 行）`;
        } catch (err) {
          hint.textContent = '解析失败：' + (err.message || String(err));
        }
      });
      // 拖拽支持
      zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('dragover'); });
      zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
      zone.addEventListener('drop', e => {
        e.preventDefault();
        zone.classList.remove('dragover');
        const file = e.dataTransfer.files[0];
        if (file) { input.files = e.dataTransfer.files; input.dispatchEvent(new Event('change')); }
      });
      return;
    }

    // 其他 loader：拉取列表
    let list = [];
    try {
      const cacheKey = loader.id;
      if (side === 'a' && this._listCacheA[cacheKey]) {
        list = this._listCacheA[cacheKey];
      } else if (side === 'b' && this._listCacheB[cacheKey]) {
        list = this._listCacheB[cacheKey];
      } else {
        extraEl.innerHTML = '<div class="dm-loading">加载列表中…</div>';
        list = await loader.loadList();
        if (side === 'a') this._listCacheA[cacheKey] = list;
        else              this._listCacheB[cacheKey] = list;
      }
    } catch (err) {
      extraEl.innerHTML = `<div class="dm-error">加载失败：${_dmEsc(err.message || String(err))}</div>`;
      return;
    }

    if (!list || !list.length) {
      extraEl.innerHTML = `<div style="font-size:12px;color:var(--text-faint,#6c7086);padding:6px 0">（暂无可用数据集）</div>`;
      return;
    }

    const opts = list.map(item =>
      `<option value="${_dmEsc(item.id)}">${_dmEsc(item.label)}</option>`
    ).join('');

    extraEl.innerHTML = `
      <div class="dm-field-group">
        <label>数据集</label>
        <select class="dm-select" id="dm-item-${side}">${opts}</select>
      </div>
    `;

    const itemSel = extraEl.querySelector(`#dm-item-${side}`);
    sel.itemId = list[0].id;
    itemSel.addEventListener('change', e => {
      sel.itemId = e.target.value;
      sel.rows   = null;  // 重置，等 compare 时再加载
    });
  }

  async _doCompare() {
    const btn = this._overlay.querySelector('#dm-compare');
    const errEl = this._overlay.querySelector('#dm-step1-error');
    btn.disabled = true;
    btn.textContent = '加载中…';
    if (errEl) errEl.innerHTML = '';

    try {
      // 加载两侧数据
      const [rowsA, rowsB] = await Promise.all([
        this._loadRows(this._selA),
        this._loadRows(this._selB),
      ]);

      this._diffRows = this._computeDiff(rowsA, rowsB, this._matchKey);
      this._step = 2;
      this._renderStep2();
    } catch (err) {
      if (errEl) errEl.innerHTML = `<div class="dm-error">${_dmEsc(err.message || '加载数据失败')}</div>`;
    } finally {
      btn.disabled = false;
      btn.textContent = '开始对比 →';
    }
  }

  async _loadRows(sel) {
    if (sel.rows !== null) return sel.rows;
    const loader = this._loaders.find(l => l.id === sel.loaderId);
    if (!loader) throw new Error('未找到数据源');
    if (!sel.itemId) throw new Error('请选择数据集');
    const rows = await loader.loadRows(sel.itemId);
    sel.rows = rows;
    return rows;
  }

  // ── Diff 算法 ─────────────────────────────────────────────────────────────

  _computeDiff(rowsA, rowsB, matchKey) {
    const mapB = new Map();
    rowsB.forEach(row => {
      const k = String(row[matchKey] ?? '');
      mapB.set(k, row);
    });
    const matchedKeys = new Set();
    const result = [];

    rowsA.forEach(rowA => {
      const k    = String(rowA[matchKey] ?? '');
      const rowB = mapB.get(k);
      if (!rowB) {
        result.push({ _diffStatus: 'removed', _rowA: rowA, _rowB: null, _changedFields: [] });
      } else {
        matchedKeys.add(k);
        const changedFields = this._columns
          .filter(c => String(rowA[c.key] ?? '') !== String(rowB[c.key] ?? ''))
          .map(c => c.key);
        if (changedFields.length === 0) {
          result.push({ _diffStatus: 'same', _rowA: rowA, _rowB: rowB, _changedFields: [] });
        } else {
          result.push({ _diffStatus: 'modified', _rowA: rowA, _rowB: rowB, _changedFields: changedFields });
        }
      }
    });

    // B 中新增的行
    rowsB.forEach(rowB => {
      const k = String(rowB[matchKey] ?? '');
      if (!matchedKeys.has(k)) {
        result.push({ _diffStatus: 'added', _rowA: null, _rowB: rowB, _changedFields: [] });
      }
    });

    return result;
  }

  // ── Step 2：对比结果 ──────────────────────────────────────────────────────

  _renderStep2() {
    this._setSteps(2);

    const counts = { added: 0, removed: 0, modified: 0, same: 0 };
    this._diffRows.forEach(r => counts[r._diffStatus]++);

    // 获取标签
    const labelA = this._getLabel(this._selA);
    const labelB = this._getLabel(this._selB);

    const summaryHtml = `
      <div class="dm-summary-bar">
        <span class="dm-summary-badge dm-badge-added">＋ ${counts.added} 新增</span>
        <span class="dm-summary-badge dm-badge-removed">－ ${counts.removed} 删除</span>
        <span class="dm-summary-badge dm-badge-modified">～ ${counts.modified} 变更</span>
        <span class="dm-summary-badge dm-badge-same">─ ${counts.same} 相同</span>
      </div>
    `;

    const toolbarHtml = `
      <div class="dm-view-toolbar">
        <div class="dm-view-group">
          <button class="dm-btn-sm ${this._viewMode === 'unified' ? 'active' : ''}" id="dm-view-unified">统一视图</button>
          <button class="dm-btn-sm ${this._viewMode === 'sbs'     ? 'active' : ''}" id="dm-view-sbs">并排视图</button>
        </div>
        <label class="dm-only-diff-label">
          <input type="checkbox" id="dm-only-diff" ${this._onlyDiff ? 'checked' : ''} />
          只看差异
        </label>
        <span class="dm-toolbar-spacer"></span>
        <div class="dm-dropdown-wrap">
          <button class="dm-btn-sm" id="dm-export-btn">导出报告 ▾</button>
          <div class="dm-dropdown-menu" id="dm-export-menu">
            <button class="dm-dropdown-item" id="dm-export-excel">📊 Excel (.xlsx)</button>
            <button class="dm-dropdown-item" id="dm-export-lark">📋 飞书电子表格</button>
          </div>
        </div>
      </div>
    `;

    this._setBody(summaryHtml + toolbarHtml + `<div id="dm-table-wrap"></div>`);
    this._setFooter(`<button class="dm-btn dm-btn-ghost" id="dm-back">← 重新选择</button>`);

    // 绑定工具栏事件
    this._overlay.querySelector('#dm-view-unified').addEventListener('click', () => {
      this._viewMode = 'unified';
      this._switchView();
    });
    this._overlay.querySelector('#dm-view-sbs').addEventListener('click', () => {
      this._viewMode = 'sbs';
      this._switchView();
    });
    this._overlay.querySelector('#dm-only-diff').addEventListener('change', e => {
      this._onlyDiff = e.target.checked;
      const wrap = this._overlay.querySelector('#dm-body');
      if (this._onlyDiff) wrap.classList.add('dm-hide-same');
      else                wrap.classList.remove('dm-hide-same');
    });

    // 导出下拉
    const exportBtn  = this._overlay.querySelector('#dm-export-btn');
    const exportMenu = this._overlay.querySelector('#dm-export-menu');
    exportBtn.addEventListener('click', e => {
      e.stopPropagation();
      exportMenu.classList.toggle('show');
    });
    document.addEventListener('click', () => exportMenu.classList.remove('show'), { once: false, capture: true });

    this._overlay.querySelector('#dm-export-excel').addEventListener('click', () => {
      exportMenu.classList.remove('show');
      this._exportExcel(labelA, labelB);
    });
    this._overlay.querySelector('#dm-export-lark').addEventListener('click', () => {
      exportMenu.classList.remove('show');
      this._exportLarkSheet(labelA, labelB);
    });

    this._overlay.querySelector('#dm-back').addEventListener('click', () => {
      this._step = 1;
      this._renderStep1();
    });

    // 应用只看差异状态
    const bodyEl = this._overlay.querySelector('#dm-body');
    if (this._onlyDiff) bodyEl.classList.add('dm-hide-same');
    else                bodyEl.classList.remove('dm-hide-same');

    this._renderTable();
  }

  _getLabel(sel) {
    const loader = this._loaders.find(l => l.id === sel.loaderId);
    if (!loader) return sel.loaderId;
    const cacheA = this._listCacheA[sel.loaderId] || [];
    const cacheB = this._listCacheB[sel.loaderId] || [];
    const list = cacheA.length ? cacheA : cacheB;
    const item = list.find(i => i.id === sel.itemId);
    return item ? `${loader.label} - ${item.label}` : loader.label;
  }

  _switchView() {
    // 切换按钮状态
    this._overlay.querySelector('#dm-view-unified')?.classList.toggle('active', this._viewMode === 'unified');
    this._overlay.querySelector('#dm-view-sbs')?.classList.toggle('active', this._viewMode === 'sbs');
    this._renderTable();
  }

  _renderTable() {
    const wrap = this._overlay.querySelector('#dm-table-wrap');
    if (!wrap) return;
    if (this._viewMode === 'unified') {
      wrap.innerHTML = this._buildUnifiedTable();
    } else {
      const labelA = this._getLabel(this._selA);
      const labelB = this._getLabel(this._selB);
      wrap.innerHTML = this._buildSideBySideTable(labelA, labelB);
    }
  }

  // ── Unified 视图 ──────────────────────────────────────────────────────────

  _buildUnifiedTable() {
    const STATUS_ICON = { added: '🟢', removed: '🔴', modified: '🟡', same: '─' };
    const cols = this._columns;

    const thCols = cols.map(c => `<th style="min-width:${c.width || 80}px">${_dmEsc(c.label)}</th>`).join('');

    const rows = this._diffRows.map(dr => {
      const s    = dr._diffStatus;
      const icon = STATUS_ICON[s] || '─';
      const cls  = `dm-${s}`;
      // 对于 removed/same，显示 A 侧；对于 added，显示 B 侧；modified 显示 B 侧（新值）
      const rowData = s === 'removed' ? dr._rowA : (dr._rowB || dr._rowA);
      const changed = new Set(dr._changedFields || []);

      const tds = cols.map(c => {
        const val = rowData ? String(rowData[c.key] ?? '') : '';
        const isChanged = s === 'modified' && changed.has(c.key);
        const tdClass = isChanged ? 'dm-changed' : '';
        // 对于 modified 行，显示 旧→新
        if (s === 'modified' && isChanged) {
          const oldVal = dr._rowA ? String(dr._rowA[c.key] ?? '') : '';
          const newVal = dr._rowB ? String(dr._rowB[c.key] ?? '') : '';
          return `<td class="${tdClass}" title="${_dmEsc(oldVal)} → ${_dmEsc(newVal)}">${_dmEsc(oldVal)} → ${_dmEsc(newVal)}</td>`;
        }
        return `<td class="${tdClass}">${_dmEsc(val)}</td>`;
      }).join('');

      return `<tr class="${cls}"><td class="dm-status-cell">${icon}</td>${tds}</tr>`;
    }).join('');

    return `
      <div class="dm-diff-table-wrap">
        <table class="dm-diff-table">
          <thead><tr>
            <th class="dm-status-th"></th>
            ${thCols}
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
  }

  // ── Side-by-side 视图 ─────────────────────────────────────────────────────

  _buildSideBySideTable(labelA, labelB) {
    const STATUS_ICON = { added: '🟢', removed: '🔴', modified: '🟡', same: '─' };
    const cols = this._columns;
    const colWidth = Math.max(80, Math.min(180, Math.floor(760 / cols.length)));

    // 标题行（合并左右各半宽）
    const thA = cols.map(c => `<th class="dm-sbs-header-a" style="min-width:${colWidth}px">${_dmEsc(c.label)}</th>`).join('');
    const thB = cols.map(c => `<th class="dm-sbs-header-b" style="min-width:${colWidth}px">${_dmEsc(c.label)}</th>`).join('');

    const rows = this._diffRows.map(dr => {
      const s    = dr._diffStatus;
      const icon = STATUS_ICON[s] || '─';
      const cls  = `dm-${s}`;
      const changed = new Set(dr._changedFields || []);

      const tdsA = cols.map(c => {
        const val = dr._rowA ? String(dr._rowA[c.key] ?? '') : '（空）';
        const isChanged = s === 'modified' && changed.has(c.key);
        return `<td class="dm-cell-a ${isChanged ? 'dm-cell-changed' : ''}">${_dmEsc(val)}</td>`;
      }).join('');

      const tdsB = cols.map(c => {
        const val = dr._rowB ? String(dr._rowB[c.key] ?? '') : '（空）';
        const isChanged = s === 'modified' && changed.has(c.key);
        return `<td class="dm-cell-b ${isChanged ? 'dm-cell-changed' : ''}">${_dmEsc(val)}</td>`;
      }).join('');

      return `<tr class="${cls}">
        ${tdsA}
        <td class="dm-sbs-divider dm-sbs-status">${icon}</td>
        ${tdsB}
      </tr>`;
    }).join('');

    return `
      <div class="dm-sbs-wrap">
        <table class="dm-sbs-table">
          <thead>
            <tr>
              <th colspan="${cols.length}" class="dm-sbs-header-a">${_dmEsc(labelA)}</th>
              <th class="dm-sbs-divider dm-sbs-header-a"></th>
              <th colspan="${cols.length}" class="dm-sbs-header-b">${_dmEsc(labelB)}</th>
            </tr>
            <tr>
              ${thA}
              <th class="dm-sbs-divider"></th>
              ${thB}
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
  }

  // ── 导出 Excel ────────────────────────────────────────────────────────────

  async _exportExcel(labelA, labelB) {
    const _cf = this._cf.bind(this);
    const exportBtn = this._overlay.querySelector('#dm-export-btn');
    if (exportBtn) { exportBtn.disabled = true; exportBtn.textContent = '导出中…'; }
    try {
      const body = {
        columns:   this._columns.map(c => ({ key: c.key, label: c.label, width: Math.round((c.width || 100) / 6) })),
        diff_rows: this._diffRows,
        label_a:   labelA,
        label_b:   labelB,
        filename:  `diff_${this._moduleId}_${_dmDateStr()}.xlsx`,
      };
      const resp = await _cf('POST', '/api/import-export/export/diff-report', body);
      if (!resp?.file_b64) throw new Error('后端未返回文件数据');
      _dmSaveBase64(resp.file_b64, resp.filename || body.filename);
    } catch (err) {
      alert('导出失败：' + (err.message || String(err)));
    } finally {
      if (exportBtn) { exportBtn.disabled = false; exportBtn.textContent = '导出报告 ▾'; }
    }
  }

  // ── 导出飞书电子表格 ──────────────────────────────────────────────────────

  async _exportLarkSheet(labelA, labelB) {
    const _cf = this._cf.bind(this);
    // 弹出简单输入对话框
    const token = prompt('请输入飞书电子表格 Token（URL 中 spreadsheets/ 后面的部分）：');
    if (!token) return;
    const sheetId = prompt('请输入 Sheet ID（默认 Sheet1）：', 'Sheet1') || 'Sheet1';

    const userToken = _getLarkToken();
    if (!userToken) { alert('请先飞书登录后再导出到飞书电子表格'); return; }

    const exportBtn = this._overlay.querySelector('#dm-export-btn');
    if (exportBtn) { exportBtn.disabled = true; exportBtn.textContent = '写入中…'; }
    try {
      const body = {
        user_access_token: userToken,
        spreadsheet_token: token,
        sheet_id:          sheetId,
        columns:           this._columns.map(c => ({ key: c.key, label: c.label })),
        diff_rows:         this._diffRows,
        label_a:           labelA,
        label_b:           labelB,
      };
      const resp = await _cf('POST', '/api/import-export/export/diff-lark-sheet', body);
      alert(`写入成功，共 ${resp?.written_rows || 0} 行`);
    } catch (err) {
      alert('写入失败：' + (err.message || String(err)));
    } finally {
      if (exportBtn) { exportBtn.disabled = false; exportBtn.textContent = '导出报告 ▾'; }
    }
  }

  // ── 解析 Excel 文件 ───────────────────────────────────────────────────────

  async _parseExcelFile(file) {
    const _cf = this._cf.bind(this);
    // 读取 file 为 base64
    const b64 = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = e => {
        const arr    = new Uint8Array(e.target.result);
        let binary   = '';
        for (let i = 0; i < arr.length; i++) binary += String.fromCharCode(arr[i]);
        resolve(btoa(binary));
      };
      reader.onerror = reject;
      reader.readAsArrayBuffer(file);
    });

    const data = await _cf('POST', '/api/import-export/import/parse-excel', {
      file_b64:  b64,
      filename:  file.name,
    });

    // data = { headers, rows, warnings }
    const { headers, rows } = data;
    // 转为对象数组（按列名匹配）
    return rows.map(row => {
      const obj = {};
      headers.forEach((h, i) => { obj[h] = row[i] ?? ''; });
      return obj;
    });
  }

  // ── 工具：云端 API ────────────────────────────────────────────────────────

  async _cf(method, path, body) {
    const fn = window.parent?._cloudFetch || window._cloudFetch;
    if (!fn) throw new Error('_cloudFetch 未就绪');
    const resp = await fn(path, { method, body: JSON.stringify(body) });
    if (!resp?.success) throw new Error(resp?.message || 'API 调用失败');
    return resp.data;
  }
}

// ── 模块级工具函数 ─────────────────────────────────────────────────────────

function _dmEsc(s) {
  if (s === null || s === undefined) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function _dmDateStr() {
  const d = new Date();
  return `${d.getFullYear()}${String(d.getMonth()+1).padStart(2,'0')}${String(d.getDate()).padStart(2,'0')}`;
}

function _getLarkToken() {
  const authUser = window.parent?._authUser || window._authUser;
  return authUser?.access_token || null;
}

function _dmSaveBase64(b64, filename) {
  try {
    const byteStr = atob(b64);
    const ab = new ArrayBuffer(byteStr.length);
    const ia = new Uint8Array(ab);
    for (let i = 0; i < byteStr.length; i++) ia[i] = byteStr.charCodeAt(i);
    const blob = new Blob([ab], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 1000);
  } catch (e) {
    console.error('[DiffManager] 文件保存失败:', e);
  }
}

/**
 * 便利工厂函数：创建一个「Excel 上传」loader
 * （DiffManager 内置支持，loaderId = '__excel__'）
 */
function dmExcelLoader() {
  return {
    id:       '__excel__',
    label:    'Excel 文件',
    loadList: async () => [{ id: '__excel__', label: 'Excel 文件' }],
    loadRows: async () => [],   // 实际由 UI 上传流程填充 sel.rows
  };
}

/**
 * 便利工厂函数：创建一个「当前视图」loader
 */
function dmCurrentLoader(label, getRows) {
  return {
    id:       '__current__',
    label:    label || '当前视图',
    loadList: async () => [{ id: '__current__', label: label || '当前视图' }],
    loadRows: async () => getRows(),
  };
}

