(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.AI00IframeShortcuts = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';

  function attach(iframe, topWindow) {
    let iframeDocument;
    try {
      iframeDocument = iframe.contentDocument || iframe.contentWindow?.document;
    } catch (_) {
      return false;
    }
    if (!iframeDocument) return false;
    iframeDocument.addEventListener('keydown', (event) => {
      if (!event.ctrlKey) return;
      if (event.key === 'o') { event.preventDefault(); topWindow.GlobalSearch?.show(); }
      if (event.key === 'p') { event.preventDefault(); topWindow.CmdPalette?.show(); }
      if (event.key === ',') { event.preventDefault(); topWindow.TabManager?.open('settings'); }
    }, true);
    return true;
  }

  return { attach };
});
