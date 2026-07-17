'use strict';
/**
 * mode_webview.js — 网页查看交互
 *
 * ContainerMode 协议：
 *   renderInCard(containerEl, params, ctx)  → cleanup()
 *   renderFullPage(containerEl, urlParams)
 *
 * params / urlParams:
 *   url     : 要嵌入的网页 URL（必须 http:// 或 https://）
 *   title   : 可选标题
 *   sandbox : 'true'（默认）| 'false'
 *
 * 安全限制：仅允许 http:// / https:// URL，拒绝 file:// 等协议。
 */
window.ContainerModes = window.ContainerModes || {};

window.ContainerModes['webview'] = (() => {

  function _isAllowedUrl(url) {
    if (!url) return false;
    try {
      const u = new URL(url);
      return u.protocol === 'http:' || u.protocol === 'https:';
    } catch { return false; }
  }

  // ── 全屏渲染（viewer.js 调用） ────────────────────────────────────────────
  function renderFullPage(containerEl, urlParams) {
    const rawUrl = urlParams.url ? decodeURIComponent(urlParams.url) : '';
    const title  = urlParams.title ? decodeURIComponent(urlParams.title) : rawUrl;

    containerEl.style.cssText = 'display:flex;flex-direction:column;height:100%;overflow:hidden;';

    // 工具栏
    const toolbar = document.createElement('div');
    toolbar.style.cssText = 'display:flex;align-items:center;gap:8px;padding:6px 10px;border-bottom:1px solid var(--border-color,#e5e7eb);flex-shrink:0;';
    toolbar.innerHTML = `
      <span style="flex:1;font-size:12px;color:var(--text-muted,#666);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" id="wvUrlLabel"></span>
      <button id="wvRefreshBtn" style="padding:3px 10px;border:1px solid var(--border-color,#e5e7eb);border-radius:4px;background:var(--bg-surface,#fff);color:var(--text-primary,#333);cursor:pointer;font-size:12px;">刷新</button>
    `;
    containerEl.appendChild(toolbar);

    const body = document.createElement('div');
    body.style.cssText = 'flex:1;overflow:hidden;position:relative;';
    containerEl.appendChild(body);

    function _loadUrl(url) {
      body.innerHTML = '';
      toolbar.querySelector('#wvUrlLabel').textContent = url;

      if (!_isAllowedUrl(url)) {
        body.innerHTML = `<div style="padding:20px;color:var(--text-danger,#e53e3e);">不支持的 URL 协议，仅允许 http:// 和 https://</div>`;
        return;
      }

      const wv = document.createElement('iframe');
      wv.src = url;
      wv.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;border:none;';
      wv.setAttribute('sandbox', 'allow-scripts allow-same-origin allow-forms allow-popups');
      body.appendChild(wv);
    }

    _loadUrl(rawUrl || '');

    toolbar.querySelector('#wvRefreshBtn').addEventListener('click', () => {
      const wv = body.querySelector('iframe');
      if (wv) wv.src = wv.src;
    });
  }

  // ── 卡片渲染（静态预览 + 弹出按钮） ──────────────────────────────────────
  function renderInCard(containerEl, params, ctx) {
    const rawUrl = params.url ? decodeURIComponent(params.url) : '';
    const title  = params.title ? decodeURIComponent(params.title) : rawUrl;

    containerEl.innerHTML = '';
    containerEl.style.cssText = 'display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;gap:12px;padding:16px;';

    // 网页图标
    containerEl.innerHTML = `
      <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted,#999)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10"/>
        <line x1="2" y1="12" x2="22" y2="12"/>
        <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
      </svg>
      <div style="font-size:13px;color:var(--text-primary,#333);text-align:center;word-break:break-all;max-width:100%;">${_esc(title || '（未配置 URL）')}</div>
      <button class="wv-popout-btn" style="padding:6px 16px;border:1px solid var(--border-color,#e5e7eb);border-radius:4px;background:var(--bg-surface,#fff);color:var(--text-primary,#333);cursor:pointer;font-size:12px;">打开网页</button>
    `;

    containerEl.querySelector('.wv-popout-btn')?.addEventListener('click', () => {
      // 触发 pop-out（向父窗口发消息或直接调用 viewer 的弹出逻辑）
      if (typeof window._ccPopOut === 'function') {
        window._ccPopOut('webview', params);
      } else {
        // 直接用 openExternal 降级
        if (rawUrl && window.electronAPI?.openExternal) {
          window.electronAPI.openExternal(rawUrl);
        }
      }
    });

    return null; // no cleanup needed
  }

  function _esc(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  return { renderInCard, renderFullPage };
})();
