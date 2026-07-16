'use strict';
/**
 * auto_canvas_type.js — 自动化画布类型插件
 *
 * 调色板元素后续细化。
 * 注册：window.CANVAS_TYPES['auto_canvas']
 */
(function () {
  window.CANVAS_TYPES = window.CANVAS_TYPES || {};

  window.CANVAS_TYPES['auto_canvas'] = {
    name: '自动化画布',

    /** 调色板渲染（后续细化） */
    renderPalette(paletteEl) {
      paletteEl.innerHTML = `
        <div class="cs-palette-section-title">触发</div>
        <div class="cs-palette-item" draggable="true" data-cs-type="trigger_manual">
          <svg class="icon" width="14" height="14"><use href="#icon-plus"/></svg>
          手动触发
        </div>
        <div class="cs-palette-item" draggable="true" data-cs-type="trigger_schedule">
          <svg class="icon" width="14" height="14"><use href="#icon-tool"/></svg>
          定时触发
        </div>

        <div class="cs-palette-section-title" style="margin-top:8px">处理</div>
        <div class="cs-palette-item" draggable="true" data-cs-type="action_script">
          <svg class="icon" width="14" height="14"><use href="#icon-doc"/></svg>
          脚本
        </div>
        <div class="cs-palette-item" draggable="true" data-cs-type="action_condition">
          <svg class="icon" width="14" height="14"><use href="#icon-shield"/></svg>
          条件分支
        </div>
        <div class="cs-palette-item" draggable="true" data-cs-type="action_notify">
          <svg class="icon" width="14" height="14"><use href="#icon-bell"/></svg>
          发送通知
        </div>
        <div class="cs-palette-item" draggable="true" data-cs-type="action_ai">
          <svg class="icon" width="14" height="14"><use href="#icon-robot"/></svg>
          AI 处理
        </div>

        <div class="cs-palette-section-title" style="margin-top:8px">输出</div>
        <div class="cs-palette-item" draggable="true" data-cs-type="output_update">
          <svg class="icon" width="14" height="14"><use href="#icon-save"/></svg>
          更新数据
        </div>
        <div class="cs-palette-item" draggable="true" data-cs-type="output_report">
          <svg class="icon" width="14" height="14"><use href="#icon-chart"/></svg>
          生成报表
        </div>
      `;

      // 拖拽事件
      paletteEl.querySelectorAll('.cs-palette-item[data-cs-type]').forEach(item => {
        item.addEventListener('dragstart', e => {
          e.dataTransfer.setData('cs/palette-type', item.dataset.csType);
          e.dataTransfer.setData('text/plain', '');
          e.dataTransfer.effectAllowed = 'copy';
        });
      });
    },

    /** 画布类型初始化回调（可选） */
    onInit(shell) {
      // 后续细化：注册自定义卡片渲染、连线规则等
    },
  };
})();
