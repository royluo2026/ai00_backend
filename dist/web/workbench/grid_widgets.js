/**
 * 可拖拽宫格组件核心逻辑
 * 功能：拖拽排序、尺寸切换、最大化/还原、布局持久化、主题适配
 */
document.addEventListener('DOMContentLoaded', () => {
  // 配置常量
  const STORAGE_KEY = 'craft_widget_layout';
  const SIZE_CLASSES = ['widget-small', 'widget-medium', 'widget-large'];
  const widgetGrid = document.getElementById('widgetGrid');
  const allWidgets = document.querySelectorAll('.widget-item');

  class WidgetManager {
    constructor() {
      this.sortable = null;
      this.layout = this.loadLayout();
      this.init();
    }

    // 初始化所有功能
    init() {
      this.initSortable();
      this.restoreLayout();
      this.bindEvents();
      this.syncGlobalTheme();
      console.log('✅ 可拖拽宫格组件初始化完成');
    }

    // 1. 初始化拖拽排序
    initSortable() {
      this.sortable = new Sortable(widgetGrid, {
        animation: 250,
        handle: '.widget-header',
        ghostClass: 'sortable-ghost',
        dragClass: 'sortable-drag',
        onEnd: (evt) => {
          this.saveLayout();
        }
      });
    }

    // 2. 绑定交互事件
    bindEvents() {
      // 尺寸切换
      document.querySelectorAll('.resize-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
          this.toggleWidgetSize(btn.closest('.widget-item'));
        });
      });

      // 最大化/还原
      document.querySelectorAll('.maximize-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
          this.toggleMaximize(btn.closest('.widget-item'));
        });
      });
    }

    // 3. 切换组件尺寸
    toggleWidgetSize(widget) {
      const currentClass = SIZE_CLASSES.find(cls => widget.classList.contains(cls));
      const currentIndex = SIZE_CLASSES.indexOf(currentClass);
      const nextIndex = (currentIndex + 1) % SIZE_CLASSES.length;

      widget.classList.remove(...SIZE_CLASSES);
      widget.classList.add(SIZE_CLASSES[nextIndex]);
      this.saveLayout();
    }

    // 4. 切换最大化/还原
    toggleMaximize(widget) {
      widget.classList.toggle('widget-maximized');
      this.saveLayout();
    }

    // 5. 保存布局到本地存储
    saveLayout() {
      const widgets = document.querySelectorAll('.widget-item');
      const layoutData = Array.from(widgets).map(widget => ({
        id: widget.dataset.id,
        size: SIZE_CLASSES.find(cls => widget.classList.contains(cls)),
        maximized: widget.classList.contains('widget-maximized'),
        order: Array.from(widget.parentElement.children).indexOf(widget)
      }));

      localStorage.setItem(STORAGE_KEY, JSON.stringify(layoutData));
    }

    // 6. 加载布局配置
    loadLayout() {
      try {
        const data = localStorage.getItem(STORAGE_KEY);
        return data ? JSON.parse(data) : [];
      } catch (e) {
        console.error('布局加载失败', e);
        return [];
      }
    }

    // 7. 恢复布局
    restoreLayout() {
      if (!this.layout.length) return;

      // 恢复排序
      const widgetArray = Array.from(allWidgets);
      this.layout.sort((a, b) => a.order - b.order).forEach(item => {
        const widget = widgetArray.find(w => w.dataset.id === item.id);
        if (widget) {
          widgetGrid.appendChild(widget);
          // 恢复尺寸
          widget.classList.remove(...SIZE_CLASSES);
          widget.classList.add(item.size);
          // 恢复最大化状态
          if (item.maximized) {
            widget.classList.add('widget-maximized');
          }
        }
      });
    }

    // 8. 同步全局主题
    syncGlobalTheme() {
      const savedTheme = localStorage.getItem('appTheme') || 'light';
      document.documentElement.setAttribute('data-theme', savedTheme);

      // 监听主题变化
      const observer = new MutationObserver(mutations => {
        mutations.forEach(mutation => {
          if (mutation.attributeName === 'data-theme') {
            const theme = document.documentElement.getAttribute('data-theme');
            document.documentElement.setAttribute('data-theme', theme);
          }
        });
      });
      observer.observe(document.documentElement, { attributes: true });
    }
  }

  // 启动组件
  new WidgetManager();
});