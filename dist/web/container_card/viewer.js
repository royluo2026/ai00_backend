'use strict';
/**
 * viewer.js — container_card 全屏入口
 *
 * 职责：
 * 1. 解析 URLSearchParams，提取 mode + 其他参数
 * 2. 应用主题
 * 3. 渲染标题栏
 * 4. 调用 ContainerModes[mode].renderFullPage(bodyEl, urlParams)
 *
 * 参数传递策略（两条路径）：
 * A. URL query string：TabManager 将 params 序列化为 ?mode=...&gid=... 附加到 src
 *    → 适合短参数（gid、item_type、source 等）
 * B. postMessage (cc:params)：TabManager 在 iframe load 后发送
 *    → 适合长参数（attachments base64）
 *    → 收到后若 body 已初始化则重新渲染
 */

(function () {
  let _initialized = false;
  let _renderedFromUrl = false;  // 已通过 URL params 渲染，避免 cc:params 重复渲染

  // ── 工具函数（供 mode 文件引用）──────────────────────────────────────────
  /** 获取 cloudFetch 函数（供 mode_field_detail 等使用）*/
  window._cf = function() {
    return window.top?._cloudFetch || window.parent?._cloudFetch || window._cloudFetch || null;
  };

  // ── B64 标题解码（UTF-8 安全，与 attachments_widget _b64EncUtf8 配对）───
  function _tryDecodeTitle(raw) {
    if (!raw) return raw;
    try {
      const binary = atob(raw);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      const decoded = new TextDecoder().decode(bytes);
      // 检查是否像有效文本（至少包含一些可打印字符）
      if (/[\u4e00-\u9fff\w]/.test(decoded)) return decoded;
    } catch (_) {}
    return raw;
  }

  // ── 主题 ─────────────────────────────────────────────────────────────────
  function _applyTheme() {
    const theme = localStorage.getItem('system.theme') || 'light';
    document.documentElement.setAttribute('data-theme', theme);
  }

  // ── 渲染入口 ─────────────────────────────────────────────────────────────
  function _render(extraParams) {
    const urlParams = new URLSearchParams(window.location.search);
    const stored    = extraParams || window._ccParams || {};

    const mode  = stored.mode  || urlParams.get('mode')  || 'row_detail';
    const rawTitle = stored.title || urlParams.get('title') || '';
    const title = rawTitle ? _tryDecodeTitle(rawTitle) : '内容详情';

    const titleEl = document.getElementById('ccTitle');
    if (titleEl) titleEl.textContent = title;

    const bodyEl = document.getElementById('ccBody');
    if (!bodyEl) { console.error('[viewer] #ccBody not found!'); return; }

    // 合并：stored 优先，fallback 到 urlParams
    const mergedParams = new Proxy(urlParams, {
      get(target, prop) {
        if (prop === 'get') {
          return key => (stored[key] != null ? String(stored[key]) : target.get(key));
        }
        // 支持直接属性访问（如 urlParams.url）：stored → URLSearchParams → 原生属性
        if (typeof prop === 'string') {
          if (stored[prop] != null) return String(stored[prop]);
          const fromSearch = target.get?.(prop);
          if (fromSearch !== null && fromSearch !== undefined) return fromSearch;
        }
        return typeof target[prop] === 'function' ? target[prop].bind(target) : target[prop];
      },
    });

    const renderer = window.ContainerModes?.[mode];
    if (!renderer) {
      bodyEl.innerHTML = `<div class="cc-empty">未知模式: ${mode}</div>`;
      return;
    }

    bodyEl.innerHTML = '';
    try {
      renderer.renderFullPage(bodyEl, mergedParams);
    } catch (e) {
      console.error('[ContainerCard] renderFullPage error:', e);
      bodyEl.innerHTML = `<div class="cc-empty">渲染失败: ${e}</div>`;
    }
  }

  // ── 初始化（DOMContentLoaded 时调用）────────────────────────────────────
  function init() {
    _applyTheme();

    // 返回按钮
    const backBtn = document.getElementById('ccBackBtn');
    if (backBtn && !backBtn._bound) {
      backBtn._bound = true;
      backBtn.addEventListener('click', () => {
        // 通知父窗口关闭当前 tab
        if (window.parent && window.parent !== window) {
          window.parent.postMessage({ type: 'cc:close-tab', tabId: window._ccTabId }, '*');
        }
      });
    }

    // 如果 URL 中有 mode，立即渲染（path A）
    const urlMode = new URLSearchParams(window.location.search).get('mode');
    if (urlMode) {
      _render();
      _renderedFromUrl = true;  // 标记已渲染，阻止 cc:params 重复渲染
    }
    // 否则等待 cc:params postMessage（path B）
    _initialized = true;
  }

  // ── 消息监听 ─────────────────────────────────────────────────────────────
  window.addEventListener('message', e => {
    if (e.data?.type === 'theme') {
      document.documentElement.setAttribute('data-theme', e.data.theme);
      localStorage.setItem('system.theme', e.data.theme);
    }

    if (e.data?.type === 'cc:params') {
      window._ccParams = e.data.params || {};
      window._ccTabId  = e.data.tabId  || null;
      // 若页面已初始化（DOMContentLoaded 已过），立即重新渲染
      // 但若已通过 URL params 渲染过（path A），跳过以避免重复渲染（会打断正在加载的 webview）
      if (_initialized && !_renderedFromUrl) {
        _render(e.data.params);
      }
      // 否则 init() 会在 DOMContentLoaded 时读取 window._ccParams
    }
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
