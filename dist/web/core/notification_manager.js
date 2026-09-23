/**
 * notification_manager.js — 通知管理器
 * 处理应用内通知面板的拉取、展示与已读标记。
 * 依赖 window.AI00Business 的受控 Gateway 结果。
 */
const NotifManager = (() => {
  let _pollTimer = null;

  const TYPE_LABELS = {
    scope_approved: '范围提升通过',
    scope_rejected: '范围提升驳回',
    item_status:    '状态变更',
    new_follower:   '新关注者',
  };

  // The facade removes the atomic Provider wrapper; this is the application outcome.
  function notificationData(outcome) {
    if (outcome?.success !== true) throw new Error('notification_outcome_invalid');
    return outcome.data;
  }

  async function pollCount() {
    if (window._authMode !== 'feishu') return;
    try {
      const res = await (async (body,path,query) => { const result = await window.AI00Business.invoke("project.notification.read.atomic.notifications_unread_count", {version:1,payload:{arguments:Object.fromEntries(Object.entries(({arguments:{}}).arguments).filter(([k,v])=>v!=null||[].includes(k)))}}); return result; })({},{},new URLSearchParams());
      const count = notificationData(res)?.count || 0;
      const badge = document.getElementById('notif-badge');
      if (badge) {
        if (count > 0) {
          badge.textContent = count > 99 ? '99+' : String(count);
          badge.style.display = '';
        } else {
          badge.style.display = 'none';
        }
      }
      // Electron 原生任务栏/Dock badge
      window.electronAPI?.setBadgeCount?.(count);
    } catch(_) {}
  }

  async function loadPanel() {
    const list = document.getElementById('notif-list');
    if (!list) return;
    if (window._authMode !== 'feishu') {
      list.innerHTML = '<div style="padding:16px;text-align:center;color:var(--text-faint,#6c7086);font-size:12px;">请先飞书登录</div>';
      return;
    }
    list.innerHTML = '<div style="padding:16px;text-align:center;color:var(--text-faint);font-size:12px;">加载中...</div>';
    try {
      const res = await (async (body,path,query) => { const result = await window.AI00Business.invoke("project.notification.read.atomic.notifications_list", {version:1,payload:{arguments:Object.fromEntries(Object.entries(({arguments:{"unread_only":(query.has("unread_only")?['true','1','yes','on'].includes(query.get("unread_only").toLowerCase()):false)}}).arguments).filter(([k,v])=>v!=null||[].includes(k)))}}); return result; })({},{},new URLSearchParams());
      const items = notificationData(res) || [];
      if (!items.length) {
        list.innerHTML = '<div style="padding:16px;text-align:center;color:var(--text-faint,#6c7086);font-size:12px;">暂无通知</div>';
        return;
      }
      list.innerHTML = items.map(n => `
        <div class="notif-item${n.is_read ? '' : ' notif-unread'}" data-gid="${n.gid}"
             style="padding:10px 14px;border-bottom:1px solid var(--border-default,#313244);cursor:pointer;background:${n.is_read ? 'transparent' : 'rgba(137,180,250,0.06)'}">
          <div style="font-size:12px;color:var(--text-muted,#a6adc8);margin-bottom:2px">${TYPE_LABELS[n.type] || n.type}</div>
          <div style="font-size:13px;color:var(--text-normal,#cdd6f4)">${n.title}</div>
          ${n.body ? `<div style="font-size:11px;color:var(--text-faint,#6c7086);margin-top:2px">${n.body}</div>` : ''}
          <div style="font-size:10px;color:var(--text-faint,#6c7086);margin-top:4px">${n.created_at?.slice(0,16) || ''}</div>
        </div>
      `).join('');
      list.querySelectorAll('.notif-item').forEach(el => {
        el.addEventListener('click', async () => {
          const gid = el.dataset.gid;
          await (async (body,path,query) => { const result = await window.AI00Business.invoke("project.notification.change.apply.atomic.notifications_mark_read", {version:1,payload:{arguments:{"gid":path.gid}}}); return result; })({},{"gid":decodeURIComponent(String(gid))},new URLSearchParams()).catch(() => {});
          el.classList.remove('notif-unread');
          el.style.background = 'transparent';
          await pollCount();
        });
      });
      await pollCount();
    } catch(e) {
      list.innerHTML = `<div style="padding:16px;text-align:center;color:var(--text-faint);font-size:12px;">加载失败: ${e.message}</div>`;
    }
  }

  async function readAll() {
    if (window._authMode !== 'feishu') return;
    await (async (body,path,query) => { const result = await window.AI00Business.invoke("project.notification.change.apply.atomic.notifications_mark_all_read", {version:1,payload:{arguments:{}}}); return result; })({},{},new URLSearchParams()).catch(() => {});
    const badge = document.getElementById('notif-badge');
    if (badge) badge.style.display = 'none';
    // 同步清除任务栏角标
    window.electronAPI?.setBadgeCount?.(0);
  }

  function startPolling() {
    if (_pollTimer) return;
    pollCount();
    _pollTimer = setInterval(pollCount, 60_000);
    // 系统唤醒后立刻轮询（利用 Electron powerMonitor）
    window.electronAPI?.onPowerResume?.(() => pollCount());
  }

  return { pollCount, loadPanel, readAll, startPolling };
})();

window.NotifManager = NotifManager;

