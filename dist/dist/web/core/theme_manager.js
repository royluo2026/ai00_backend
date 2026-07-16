/**
 * ThemeManager — 主题系统
 * 覆盖 common.js 旧版，使用 data-theme 属性持久化。
 * 保留 window.setTheme / window.applyTheme 向后兼容别名。
 */
window.ThemeManager = {
  init() {
    const saved = localStorage.getItem('system.theme') || 'light';
    this.applyTheme(saved);
  },
  applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('system.theme', theme);
    // 通知所有 iframe 子页面同步主题
    document.querySelectorAll('iframe').forEach(f => {
      try { f.contentWindow?.postMessage({ type: 'theme', theme }, '*'); } catch(_) {}
    });
    if (typeof dbg !== 'undefined') dbg.log(`[Theme] 主题: ${theme}`);
  },
  toggleTheme() {
    const cur = document.documentElement.getAttribute('data-theme') || 'dark';
    this.applyTheme(cur === 'dark' ? 'light' : 'dark');
  },
};

// 兼容旧调用方式
window.setTheme = t => window.ThemeManager.applyTheme(t);
window.applyTheme = window.setTheme;

