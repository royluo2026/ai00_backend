/**
 * float_ball.js — 悬浮球逻辑（Electron 版）
 * 拖拽：CSS -webkit-app-region:drag 交给 OS 处理，无需 JS 定位
 * IPC：通过 window.electronAPI 与主进程通信
 */

const menu = document.getElementById('contextMenu');

// 单击 → 显示主窗口
document.getElementById('floatBall').onclick = () => {
  window.electronAPI?.showMain?.();
};

// 右键菜单
document.getElementById('floatBall').oncontextmenu = (e) => {
  e.preventDefault();
  menu.style.left = e.clientX + 'px';
  menu.style.top  = e.clientY + 'px';
  menu.classList.remove('menu-hidden');
};

window.onclick = () => {
  menu.classList.add('menu-hidden');
};

// 菜单功能
function showMainWindow() { window.electronAPI?.showMain?.(); }
function openSidebar()    { window.electronAPI?.showSidebar?.(); }
function closeBall()      { window.electronAPI?.hideFloatBall?.(); }
