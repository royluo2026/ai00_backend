/**
 * sidebar.js — 快捷侧边栏逻辑（Electron 版）
 * IPC：通过 window.electronAPI 与主进程通信
 * 主题：从 localStorage 读取，监听 postMessage 同步
 */
'use strict';

let isPinned = true;
let isSnapped = false;

// 初始化
document.addEventListener('DOMContentLoaded', () => {
  // 应用主题
  const theme = localStorage.getItem('system.theme') || 'light';
  _applyTheme(theme);

  bindEvents();
  console.log('✅ 悬浮侧边栏初始化完成');
});

// 主题同步
function _applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
}

window.addEventListener('message', e => {
  if (e.data?.type === 'theme') _applyTheme(e.data.theme);
});

// 事件绑定
function bindEvents() {
  // 关闭按钮
  document.getElementById('closeBtn').onclick = () => window.electronAPI?.hideSidebar?.();

  // 置顶锁定（本地 UI 状态，无需 IPC）
  document.getElementById('pinBtn').onclick = () => {
    isPinned = !isPinned;
    document.getElementById('pinBtn').style.color = isPinned ? 'var(--accent-color, #7057ff)' : '';
  };

  // 贴边隐藏（本地 UI 状态）
  document.getElementById('snapBtn').onclick = () => {
    isSnapped = !isSnapped;
    document.body.classList.toggle('snapped', isSnapped);
  };

  // 双击标题栏最大化
  const dragHeader = document.querySelector('.drag-header');
  if (dragHeader) dragHeader.ondblclick = () => window.electronAPI?.maximize?.();
}
