/* ======================================
   系统通用UI组件交互逻辑
   功能：下拉框控制、主题同步、组件初始化
 ====================================== */
const AppUI = {
  // 初始化所有组件
  init() {
    this.initSelect();
    this.syncTheme();
  },

  // 下拉框组件交互
  initSelect() {
    const triggers = document.querySelectorAll('.app-select-trigger');
    
    triggers.forEach(trigger => {
      trigger.addEventListener('click', (e) => {
        e.stopPropagation();
        const options = trigger.nextElementSibling;
        const isOpen = options.classList.contains('show');
        
        document.querySelectorAll('.app-select-options.show').forEach(item => {
          item.classList.remove('show');
          item.previousElementSibling.classList.remove('active');
        });
        
        if (!isOpen) {
          options.classList.add('show');
          trigger.classList.add('active');
        }
      });

      const options = trigger.nextElementSibling.querySelectorAll('.app-select-option');
      options.forEach(option => {
        option.addEventListener('click', () => {
          const value = option.getAttribute('data-value');
          const label = option.textContent;
          trigger.querySelector('span').textContent = label;
          
          options.forEach(o => o.classList.remove('active'));
          option.classList.add('active');
          
          trigger.dispatchEvent(new CustomEvent('change', { detail: { value, label } }));
        });
      });
    });

    document.addEventListener('click', () => {
      document.querySelectorAll('.app-select-options.show').forEach(item => {
        item.classList.remove('show');
        item.previousElementSibling.classList.remove('active');
      });
    });
  },

  // 同步系统主题
  syncTheme() {
    window.applyTheme = (theme) => {
      document.documentElement.className = `theme-${theme}`;
    };

    // Theme is now managed via localStorage / ThemeManager
  }
};

// 自动初始化
document.addEventListener('DOMContentLoaded', () => {
  AppUI.init();
});

window.AppUI = AppUI;