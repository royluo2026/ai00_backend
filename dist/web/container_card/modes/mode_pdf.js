'use strict';
/**
 * mode_pdf.js — PDF 预览（本地 file:// 或云端 http://）
 *
 * ContainerMode 协议：
 *   renderInCard(containerEl, params, ctx)  → cleanup()
 *   renderFullPage(containerEl, urlParams)
 *
 * params / urlParams:
 *   path   : base64 编码的路径或 URL（本地绝对路径 或 http/https URL）
 *   title  : UTF-8 安全 base64 编码的文件名
 */
window.ContainerModes = window.ContainerModes || {};

window.ContainerModes['pdf'] = (() => {

  function _decodePath(b64) {
    if (!b64) return '';
    try {
      const binary = atob(b64);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      return new TextDecoder().decode(bytes);
    } catch { return b64; }
  }

  // UTF-8 安全解码（与 attachments_widget.js 的 _b64EncUtf8 配对）
  function _decodeTitle(b64) {
    if (!b64) return '';
    try {
      const binary = atob(b64);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      return new TextDecoder().decode(bytes);
    } catch { return b64; }
  }

  // 兼容 URLSearchParams Proxy（.get()）和普通对象（直接属性）
  function _getParam(p, key) {
    return (typeof p?.get === 'function' ? p.get(key) : null) ?? p?.[key] ?? '';
  }

  function _filename(p) {
    if (!p) return '';
    return p.replace(/\\/g, '/').split('/').pop() || p;
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

  // 构造可用于 iframe/webview 的 file:// URL
  function _toWebviewUrl(path) {
    if (!path) return '';
    if (/^https?:\/\//i.test(path)) return path;           // 云端 http URL 直接用
    if (/^file:\/\/\//i.test(path)) return path;            // 已经是 file:// URL，直接使用
    return 'file:///' + path.replace(/\\/g, '/');          // 本地原生路径加 file:// 前缀
  }

  // ── 全屏渲染 ─────────────────────────────────────────────────────────────
  function renderFullPage(containerEl, urlParams) {
    let filePath = _decodePath(_getParam(urlParams, 'path'));
    const rawTitle = _getParam(urlParams, 'title');
    const title  = rawTitle ? _decodeTitle(rawTitle) : _filename(filePath);
    console.log('[mode_pdf] renderFullPage, path param:', filePath, 'isHttp:', /^https?:\/\//i.test(filePath), 'isFile:', /^file:\/\//i.test(filePath));

    // 更新全局标题栏
    const ccTitle = document.getElementById('ccTitle');
    if (ccTitle) ccTitle.textContent = title || 'PDF 预览';

    containerEl.style.cssText = 'display:flex;flex-direction:column;height:100%;overflow:hidden;';

    const toolbar = document.createElement('div');
    toolbar.style.cssText = 'display:flex;align-items:center;gap:8px;padding:6px 10px;border-bottom:1px solid var(--border-color,#e5e7eb);flex-shrink:0;';
    toolbar.innerHTML = `
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted,#999)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
      </svg>
      <span id="pdfTitle" style="flex:1;font-size:12px;color:var(--text-primary,#333);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${_esc(title || '（未选择文件）')}</span>
      <button id="pdfBrowseBtn" style="padding:3px 10px;border:1px solid var(--border-color,#e5e7eb);border-radius:4px;background:var(--bg-surface,#fff);color:var(--text-primary,#333);cursor:pointer;font-size:12px;">选择文件</button>
      <button id="pdfOpenExtBtn" style="padding:3px 10px;border:1px solid var(--border-color,#e5e7eb);border-radius:4px;background:var(--bg-surface,#fff);color:var(--text-primary,#333);cursor:pointer;font-size:12px;">用系统应用打开</button>
    `;
    containerEl.appendChild(toolbar);

    const body = document.createElement('div');
    body.style.cssText = 'flex:1;overflow:hidden;position:relative;';
    containerEl.appendChild(body);

    function _loadFile(path) {
      body.innerHTML = '';
      filePath = path;
      const fname = _filename(path);
      toolbar.querySelector('#pdfTitle').textContent = fname || '（未选择文件）';

      if (!path) {
        body.innerHTML = '<div style="padding:20px;color:var(--text-muted,#999);">请选择 PDF 文件</div>';
        return;
      }

      const src = _toWebviewUrl(path);
      console.log('[mode_pdf] _loadFile, path:', path, '→ _toWebviewUrl:', src);
      // container_card 运行在 iframe 内，<webview> 在 iframe 里无效，统一用 <iframe>
      const frame = document.createElement('iframe');
      frame.src = src;
      frame.style.cssText = 'width:100%;height:100%;border:none;';
      body.appendChild(frame);
    }

    _loadFile(filePath);

    toolbar.querySelector('#pdfBrowseBtn').addEventListener('click', async () => {
      const api = window.electronAPI || window.top?.electronAPI || window.parent?.electronAPI;
      if (!api?.openFileDialog) return;
      const result = await api.openFileDialog([{ name: 'PDF 文件', extensions: ['pdf'] }]);
      if (result && result.length) _loadFile(result[0]);
    });

    toolbar.querySelector('#pdfOpenExtBtn').addEventListener('click', () => {
      if (!filePath) return;
      const api = window.electronAPI || window.top?.electronAPI || window.parent?.electronAPI;
      if (/^https?:\/\//i.test(filePath)) {
        window.open(filePath, '_blank');
      } else {
        api?.openPath?.(_toNativePath(filePath));
      }
    });
  }

  // ── 卡片渲染 ─────────────────────────────────────────────────────────────
  function renderInCard(containerEl, params, ctx) {
    const filePath = _decodePath(_getParam(params, 'path'));
    const rawTitle = _getParam(params, 'title');
    const title    = rawTitle ? _decodeTitle(rawTitle) : _filename(filePath);

    containerEl.innerHTML = '';
    containerEl.style.cssText = 'display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;gap:12px;padding:16px;';

    containerEl.innerHTML = `
      <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted,#999)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>
        <line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/>
      </svg>
      <div style="font-size:13px;color:var(--text-primary,#333);text-align:center;word-break:break-all;max-width:100%;">${_esc(title || '（未配置 PDF 路径）')}</div>
      <button class="pdf-popout-btn" style="padding:6px 16px;border:1px solid var(--border-color,#e5e7eb);border-radius:4px;background:var(--bg-surface,#fff);color:var(--text-primary,#333);cursor:pointer;font-size:12px;">打开预览</button>
    `;

    containerEl.querySelector('.pdf-popout-btn')?.addEventListener('click', () => {
      if (typeof window._ccPopOut === 'function') {
        window._ccPopOut('pdf', params);
      } else if (filePath) {
        if (/^https?:\/\//i.test(filePath)) {
          window.open(filePath, '_blank');
        } else {
          const api = window.electronAPI || window.top?.electronAPI || window.parent?.electronAPI;
          api?.openPath?.(_toNativePath(filePath));
        }
      }
    });

    return null;
  }

  function _esc(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  return { renderInCard, renderFullPage };
})();

