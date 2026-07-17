// 总装智能辅助工艺开发系统(AI00) - 全局主题管理器（正式版）
window.ThemeManager = {
  async init() {
    // 优先使用后端系统配置（后续UI开发完成后启用）
    const savedTheme = localStorage.getItem('system.theme') || 'light';
    this.applyTheme(savedTheme);
  },
  applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('system.theme', theme);
  },
  toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme');
    const newTheme = current === 'dark' ? 'light' : 'dark';
    this.applyTheme(newTheme);
  }
};

// 初始化
document.addEventListener('DOMContentLoaded', () => ThemeManager.init());
window.applyTheme = (theme) => ThemeManager.applyTheme(theme);