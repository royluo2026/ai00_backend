'use strict';
/**
 * mode_spreadsheet.js — CSV / XLSX 在线查看与编辑
 *
 * ContainerMode 协议：
 *   renderInCard(containerEl, params, ctx)  → cleanup()
 *   renderFullPage(containerEl, urlParams)
 *
 * params / urlParams:
 *   path  : base64 编码的文件路径或 http URL
 *   title : UTF-8 安全 base64 编码的文件名
 *
 * 依赖：web/assets/lib/xlsx.full.min.js（SheetJS）
 */
window.ContainerModes = window.ContainerModes || {};

window.ContainerModes['spreadsheet'] = (() => {

  // ── 工具函数 ──────────────────────────────────────────────────────────────

  function _decodePath(b64) {
    if (!b64) return '';
    try {
      const binary = atob(b64);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      return new TextDecoder().decode(bytes);
    } catch { return b64; }
  }

  function _decodeTitle(b64) {
    if (!b64) return '';
    try {
      const binary = atob(b64);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      return new TextDecoder().decode(bytes);
    } catch { return b64; }
  }

  function _getParam(p, key) {
    return (typeof p?.get === 'function' ? p.get(key) : null) ?? p?.[key] ?? '';
  }

  function _filename(p) {
    return (p || '').replace(/\\/g, '/').split('/').pop() || p;
  }

  function _getCf() {
    return window._cf?.() || window.top?._cloudFetch || window.parent?._cloudFetch || window._cloudFetch || null;
  }

  // 直接 fetch PUT（/api/uploads 用 optional auth，无需 _cloudFetch）
  async function _putUpload(path, body) {
    const filename = path.split('/').pop();
    const baseUrl  = path.match(/^https?:\/\/[^/]+/)?.[0] || window.AI00RuntimeConfig?.toAbsoluteBackendUrl?.('') || window._AI00_BASE || localStorage.getItem('ai00_backend_url') || '';
    const res = await fetch(`${baseUrl}/api/uploads/${filename}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
  }

  function _ext(name) {
    return (name || '').split('.').pop().toLowerCase();
  }

  // file:// URL → 原生系统路径（Node fs 可读）
  function _toNativePath(p) {
    if (!p) return p;
    let native = p.replace(/^file:\/\/\//, '');
    if (native.match(/^[a-zA-Z]:/)) {
      native = native.replace(/\//g, '\\');
    }
    return native;
  }

  function _esc(s) {
    return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  // ── SheetJS 懒加载 ────────────────────────────────────────────────────────

  let _xlsxReady = null;
  function _loadXLSX() {
    if (window.XLSX) return Promise.resolve(window.XLSX);
    if (_xlsxReady) return _xlsxReady;
    _xlsxReady = new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = '../assets/lib/xlsx.full.min.js';
      s.onload  = () => resolve(window.XLSX);
      s.onerror = () => reject(new Error('xlsx.full.min.js 加载失败，请确认文件已放入 web/assets/lib/'));
      document.head.appendChild(s);
    });
    return _xlsxReady;
  }

  // ── 数据加载 ──────────────────────────────────────────────────────────────

  // 返回 { headers: string[], rows: string[][], sheetName: string }
  async function _loadData(path) {
    const ext = _ext(_filename(path));
    const isHttp = /^https?:\/\//i.test(path);

    if (ext === 'csv') {
      const nativePath = _toNativePath(path);
      console.log('[mode_spreadsheet] _loadData csv, path:', path, '→ nativePath:', nativePath, 'isHttp:', isHttp);
      let text = '';
      try {
        if (isHttp) {
          const res = await fetch(path);
          console.log('[mode_spreadsheet] fetch response, ok:', res.ok, 'status:', res.status);
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          text = await res.text();
          console.log('[mode_spreadsheet] fetched text length:', text.length, 'first 100 chars:', text.substring(0, 100));
        } else {
          text = await (window.electronAPI || window.top?.electronAPI || window.parent?.electronAPI)?.readTextFile(nativePath) || '';
        }
      } catch (e) {
        console.error('[mode_spreadsheet] _loadData csv error:', e);
        throw e;
      }
      return _parseCSV(text || '');
    }

    // xlsx / xls：需要 SheetJS
    const XLSX = await _loadXLSX();
    let buf;
    if (isHttp) {
      buf = await fetch(path).then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.arrayBuffer(); });
    } else {
      // 本地：暂不支持（IPC 没有 readBinaryFile，可后续扩展）
      throw new Error('本地 xlsx 暂不支持，请通过云端上传后预览');
    }
    const wb = XLSX.read(new Uint8Array(buf), { type: 'array' });
    const sheetName = wb.SheetNames[0];
    const ws = wb.Sheets[sheetName];
    const raw = XLSX.utils.sheet_to_json(ws, { header: 1, defval: '' });
    const headers = raw[0]?.map(String) || [];
    const rows = raw.slice(1).map(r => headers.map((_, i) => String(r[i] ?? '')));
    return { headers, rows, sheetName, wb, ws };
  }

  // ── CSV 解析 / 序列化 ─────────────────────────────────────────────────────

  function _parseCSV(text) {
    const lines = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n');
    const parse = line => {
      const cells = [];
      let cur = '', inQ = false;
      for (let i = 0; i < line.length; i++) {
        const c = line[i];
        if (c === '"') {
          if (inQ && line[i+1] === '"') { cur += '"'; i++; }
          else inQ = !inQ;
        } else if (c === ',' && !inQ) { cells.push(cur); cur = ''; }
        else cur += c;
      }
      cells.push(cur);
      return cells;
    };
    const allRows = lines.filter((l, i) => i < lines.length - 1 || l.trim()).map(parse);
    const headers = allRows[0] || [];
    const rows = allRows.slice(1);
    return { headers, rows, sheetName: 'Sheet1' };
  }

  function _toCSV(headers, rows) {
    const q = v => /[,"\n\r]/.test(v) ? `"${v.replace(/"/g,'""')}"` : v;
    return [headers, ...rows].map(r => r.map(q).join(',')).join('\r\n');
  }

  // ── 保存 ──────────────────────────────────────────────────────────────────

  async function _save(path, headers, rows, xlsxMeta) {
    const ext = _ext(_filename(path));
    const isHttp = /^https?:\/\//i.test(path);

    if (ext === 'csv') {
      const content = _toCSV(headers, rows);
      if (isHttp) {
        const filename = path.split('/').pop();
        await _putUpload(path, { content });
      } else {
        const api = window.electronAPI || window.top?.electronAPI || window.parent?.electronAPI;
        if (!api?.writeTextFile) throw new Error('electronAPI.writeTextFile 不可用');
        await api.writeTextFile(_toNativePath(path), content);
      }
      return;
    }

    // xlsx：用 SheetJS 序列化后 base64 上传
    const XLSX = await _loadXLSX();
    const { wb, ws, sheetName } = xlsxMeta;
    // 更新 worksheet 数据
    const newData = [headers, ...rows];
    const newWs = XLSX.utils.aoa_to_sheet(newData);
    wb.Sheets[sheetName] = newWs;
    const wbout = XLSX.write(wb, { bookType: 'xlsx', type: 'array' });
    const bytes = new Uint8Array(wbout);
    let binary = '';
    bytes.forEach(b => binary += String.fromCharCode(b));
    const data_b64 = btoa(binary);

    if (isHttp) {
      const filename = path.split('/').pop();
      await _putUpload(path, { data_b64 });
    } else {
      throw new Error('本地 xlsx 写入暂不支持');
    }
  }

  // ── 表格渲染 ──────────────────────────────────────────────────────────────

  function _buildSpreadsheet(containerEl, data, filePath, editable) {
    let { headers, rows, sheetName, wb, ws } = data;
    // 保持 xlsxMeta 引用供保存用
    const xlsxMeta = { wb, ws, sheetName };

    containerEl.innerHTML = '';
    containerEl.style.cssText = 'display:flex;flex-direction:column;height:100%;overflow:hidden;font-size:12px;';

    // ── 工具栏 ──
    const toolbar = document.createElement('div');
    toolbar.style.cssText = 'display:flex;align-items:center;gap:8px;padding:5px 10px;border-bottom:1px solid var(--cc-border,#dcdcdc);flex-shrink:0;background:var(--cc-bg,#fff);';

    const titleSpan = document.createElement('span');
    titleSpan.style.cssText = 'flex:1;color:var(--cc-text,#2e2e2e);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';
    titleSpan.textContent = _filename(filePath) + (sheetName ? ` [${sheetName}]` : '');
    toolbar.appendChild(titleSpan);

    const info = document.createElement('span');
    info.style.cssText = 'color:var(--cc-muted,#6e6e6e);font-size:11px;';
    info.textContent = `${rows.length} 行 × ${headers.length} 列`;
    toolbar.appendChild(info);

    let saveBtn = null;
    if (editable && filePath) {
      saveBtn = document.createElement('button');
      saveBtn.textContent = '保存';
      saveBtn.style.cssText = 'padding:3px 10px;border-radius:4px;border:none;background:var(--color-accent,#7b61ff);color:#fff;cursor:pointer;font-size:12px;';
      saveBtn.addEventListener('click', async () => {
        saveBtn.disabled = true;
        saveBtn.textContent = '保存中…';
        try {
          await _save(filePath, headers, rows, xlsxMeta);
          saveBtn.textContent = '已保存';
          setTimeout(() => { saveBtn.textContent = '保存'; saveBtn.disabled = false; }, 1500);
        } catch (e) {
          alert('保存失败：' + e.message);
          saveBtn.textContent = '保存';
          saveBtn.disabled = false;
        }
      });
      toolbar.appendChild(saveBtn);
    }

    containerEl.appendChild(toolbar);

    // ── Sheet 标签页（xlsx 多 sheet 时显示）──
    const sheetNames = wb?.SheetNames || [];
    let activeSheet = sheetName;

    if (sheetNames.length > 1) {
      const tabBar = document.createElement('div');
      tabBar.style.cssText = 'display:flex;flex-shrink:0;border-bottom:1px solid var(--cc-border,#dcdcdc);background:var(--cc-bg2,#f7f6f3);overflow-x:auto;gap:0;';

      function _refreshTabs() {
        tabBar.querySelectorAll('button[data-sheet]').forEach(t => {
          const active = t.dataset.sheet === activeSheet;
          t.style.borderBottom = active ? '2px solid var(--color-accent,#7b61ff)' : '2px solid transparent';
          t.style.color = active ? 'var(--color-accent,#7b61ff)' : 'var(--cc-text,#2e2e2e)';
          t.style.fontWeight = active ? '500' : '400';
        });
      }

      sheetNames.forEach(name => {
        const tab = document.createElement('button');
        tab.textContent = name;
        tab.dataset.sheet = name;
        tab.style.cssText = 'padding:4px 14px;border:none;background:none;cursor:pointer;font-size:11px;white-space:nowrap;flex-shrink:0;';
        tab.addEventListener('click', () => {
          if (name === activeSheet) return;
          activeSheet = name;
          const newWs = wb.Sheets[name];
          const raw = window.XLSX.utils.sheet_to_json(newWs, { header: 1, defval: '' });
          headers = raw[0]?.map(String) || [];
          rows = raw.slice(1).map(r => headers.map((_, i) => String(r[i] ?? '')));
          xlsxMeta.ws = newWs;
          xlsxMeta.sheetName = name;
          titleSpan.textContent = _filename(filePath) + ` [${name}]`;
          _refreshTabs();
          _renderSheet();
        });
        tabBar.appendChild(tab);
      });

      containerEl.appendChild(tabBar);
      _refreshTabs();
    }

    // ── 表格容器 ──
    const wrap = document.createElement('div');
    wrap.style.cssText = 'flex:1;overflow:auto;';
    containerEl.appendChild(wrap);

    // ── 表格渲染（切换 sheet 时重调）──
    function _renderSheet() {
      wrap.innerHTML = '';
      info.textContent = `${rows.length} 行 × ${headers.length} 列`;

      const table = document.createElement('table');
      table.style.cssText = 'border-collapse:collapse;min-width:100%;white-space:nowrap;';

      // 表头
      const thead = document.createElement('thead');
      const trh = document.createElement('tr');
      const th0 = document.createElement('th');
      th0.style.cssText = _thStyle() + 'width:40px;min-width:40px;color:var(--cc-muted,#6e6e6e);font-weight:400;';
      th0.textContent = '#';
      trh.appendChild(th0);
      headers.forEach((h, hi) => {
        const th = document.createElement('th');
        th.style.cssText = _thStyle();
        if (editable) {
          th.contentEditable = 'true';
          th.addEventListener('blur', () => { headers[hi] = th.textContent; });
        }
        th.textContent = h;
        trh.appendChild(th);
      });
      thead.appendChild(trh);
      table.appendChild(thead);

      // 表体
      const tbody = document.createElement('tbody');
      rows.forEach((row, ri) => {
        const tr = document.createElement('tr');
        const td0 = document.createElement('td');
        td0.style.cssText = _tdStyle() + 'color:var(--cc-muted,#6e6e6e);text-align:center;background:var(--cc-bg2,#f7f6f3);';
        td0.textContent = ri + 1;
        tr.appendChild(td0);

        row.forEach((cell, ci) => {
          const td = document.createElement('td');
          td.style.cssText = _tdStyle();
          td.textContent = cell;
          if (editable) {
            td.contentEditable = 'true';
            td.addEventListener('blur', () => { rows[ri][ci] = td.textContent; });
            td.addEventListener('keydown', e => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                const nextTr = tr.nextElementSibling;
                if (nextTr) nextTr.children[ci + 1]?.focus();
              }
              if (e.key === 'Tab') {
                e.preventDefault();
                const nextTd = e.shiftKey ? td.previousElementSibling : td.nextElementSibling;
                nextTd?.focus();
              }
            });
          }
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      wrap.appendChild(table);
    }

    _renderSheet();

    // Ctrl+S 保存
    if (editable && saveBtn) {
      containerEl.addEventListener('keydown', e => {
        if (e.ctrlKey && e.key === 's') { e.preventDefault(); saveBtn.click(); }
      });
    }
  }

  function _thStyle() {
    return 'position:sticky;top:0;z-index:1;padding:5px 8px;border:1px solid var(--cc-border,#dcdcdc);background:var(--cc-bg2,#f7f6f3);color:var(--cc-text,#2e2e2e);font-weight:500;text-align:left;';
  }
  function _tdStyle() {
    return 'padding:4px 8px;border:1px solid var(--cc-border,#dcdcdc);color:var(--cc-text,#2e2e2e);min-width:80px;max-width:300px;overflow:hidden;text-overflow:ellipsis;outline:none;';
  }

  // ── renderFullPage ────────────────────────────────────────────────────────

  async function renderFullPage(containerEl, urlParams) {
    const filePath = _decodePath(_getParam(urlParams, 'path'));
    const rawTitle = _getParam(urlParams, 'title');
    const title    = rawTitle ? _decodeTitle(rawTitle) : _filename(filePath);
    console.log('[mode_spreadsheet] renderFullPage, path param:', filePath, 'isHttp:', /^https?:\/\//i.test(filePath), 'isFile:', /^file:\/\//i.test(filePath));

    containerEl.innerHTML = '<div class="cc-loading" style="padding:20px;color:var(--cc-muted,#6e6e6e);">加载中…</div>';

    const titleEl = document.getElementById('ccTitle');
    if (titleEl) titleEl.textContent = title || '表格预览';

    try {
      const data = await _loadData(filePath);
      _buildSpreadsheet(containerEl, data, filePath, true);
    } catch (e) {
      containerEl.innerHTML = `<div style="padding:20px;color:var(--color-danger,#f38ba8);">加载失败：${_esc(e.message)}</div>`;
    }
  }

  // ── renderInCard ──────────────────────────────────────────────────────────

  function renderInCard(containerEl, params, ctx) {
    const filePath = _decodePath(_getParam(params, 'path'));
    const rawTitle = _getParam(params, 'title');
    const title    = rawTitle ? _decodeTitle(rawTitle) : _filename(filePath);

    containerEl.innerHTML = '';
    containerEl.style.cssText = 'display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;gap:10px;padding:16px;';
    containerEl.innerHTML = `
      <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#a6e3a1" stroke-width="1.5">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
        <polyline points="14 2 14 8 20 8"/>
        <line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="16" y2="17"/>
        <line x1="10" y1="9" x2="14" y2="9"/>
      </svg>
      <div style="font-size:12px;color:var(--cc-text,#2e2e2e);text-align:center;word-break:break-all;max-width:100%;">${_esc(title || '表格文件')}</div>
      <button class="ss-popout-btn" style="padding:5px 14px;border:1px solid var(--cc-border,#dcdcdc);border-radius:4px;background:var(--cc-bg2,#f7f6f3);color:var(--cc-text,#2e2e2e);cursor:pointer;font-size:12px;">打开编辑</button>
    `;
    containerEl.querySelector('.ss-popout-btn')?.addEventListener('click', () => {
      if (typeof window._ccPopOut === 'function') window._ccPopOut('spreadsheet', params);
    });
    return null;
  }

  return { renderInCard, renderFullPage };
})();
