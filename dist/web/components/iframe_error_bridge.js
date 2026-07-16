/**
 * iframe_error_bridge.js
 * ──────────────────────
 * 在 iframe 子页面中引入此脚本，可将未捕获的 JS 错误和 Promise 拒绝
 * 通过 postMessage 气泡到父窗口 dbg 面板（type: 'iframe:error'）。
 *
 * 用法：在各 iframe HTML 页面的 <head> 末尾引入：
 *   <script src="../components/iframe_error_bridge.js"></script>
 * 或视相对路径调整。
 */
(function () {
  // 从 URL 中提取当前页面名称作为来源标识
  const _src = location.pathname.split('/').pop() || location.pathname;

  function _postError(msg, stack) {
    try {
      if (window.parent && window.parent !== window) {
        window.parent.postMessage(
          { type: 'iframe:error', msg: String(msg), stack: stack || '', src: _src },
          '*'
        );
      }
    } catch (_) {
      // 跨域 postMessage 失败时静默忽略
    }
  }

  window.addEventListener('error', function (ev) {
    const loc = ev.filename ? `(${ev.filename.split('/').pop()}:${ev.lineno})` : '';
    _postError(`${ev.message} ${loc}`, ev.error?.stack || '');
  });

  window.addEventListener('unhandledrejection', function (ev) {
    const reason = ev.reason;
    _postError(
      reason instanceof Error ? reason.message : String(reason),
      reason instanceof Error ? reason.stack : ''
    );
  });
})();

