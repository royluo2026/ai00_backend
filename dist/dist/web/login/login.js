'use strict';

// 登录页上来就读已保存的主题，避免闪白/闪黑
const _savedTheme = localStorage.getItem('system.theme') || 'light';
document.documentElement.setAttribute('data-theme', _savedTheme);

const btnFeishu = document.getElementById('btn-feishu');
const btnClose  = document.getElementById('btn-close');
const statusEl  = document.getElementById('login-status');
const statusMsg = document.getElementById('status-msg');
const statusIcon= document.getElementById('status-icon');

// ── 标题栏关闭按钮 ─────────────────────────────────────────────────────────
btnClose?.addEventListener('click', () => {
  window.electronAPI?.close?.();
});

// ── 状态提示工具 ──────────────────────────────────────────────────────────────
function showStatus(msg, type = 'loading') {
  statusEl.className = 'login-status';
  statusEl.classList.remove('hidden');
  statusMsg.textContent = msg;

  if (type === 'loading') {
    statusIcon.textContent = '⏳';
    statusIcon.className = 'status-icon spinning';
  } else if (type === 'success') {
    statusIcon.textContent = '✅';
    statusIcon.className = 'status-icon';
    statusEl.classList.add('success');
  } else if (type === 'error') {
    statusIcon.textContent = '❌';
    statusIcon.className = 'status-icon';
    statusEl.classList.add('error');
  }
}

function hideStatus() {
  statusEl.classList.add('hidden');
}

function setButtonsDisabled(disabled) {
  btnFeishu.disabled = disabled;
}

// ── 飞书登录 ──────────────────────────────────────────────────────────────────
btnFeishu?.addEventListener('click', async () => {
  setButtonsDisabled(true);
  showStatus('正在打开飞书扫码窗口...', 'loading');

  try {
    const result = await window.electronAPI?.authFeishuLogin?.() || {};
    if (result.success || result.ok) {
      showStatus('登录成功，正在进入系统...', 'success');
      // Electron：主进程自动关闭登录窗口并显示主窗口
      // 网页版：跳转到主页
      if (!window.electronAPI?._isElectron) {
        setTimeout(() => { window.location.href = '/web/index.html'; }, 800);
      }
    } else {
      showStatus(result.error || '登录失败，请重试', 'error');
      setButtonsDisabled(false);
    }
  } catch (e) {
    showStatus('发生错误：' + e.message, 'error');
    setButtonsDisabled(false);
  }
});
