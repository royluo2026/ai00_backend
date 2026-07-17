/**
 * 审批中心脚本 — 调用云端 REST API
 */

// ── 云端 API 封装 ──────────────────────────────────────────────────────────────
async function api(path, opts) {
  try {
    const fn = window.parent?._cloudFetch || window._cloudFetch;
    if (!fn) throw new Error('_cloudFetch 未就绪');
    return await fn(path, opts);
  } catch (e) {
    console.error(`[approval] API ${path} error:`, e.message);
    return { success: false, error: String(e), data: {} };
  }
}

// ── 主题同步 ──────────────────────────────────────────────────────────────────
window.addEventListener('message', e => {
  if (e.data?.type === 'theme') {
    document.documentElement.setAttribute('data-theme', e.data.theme);
  }
});

// ── 状态 ──────────────────────────────────────────────────────────────────────
let _orders = [];
let _selected = null;

const STATUS_LABEL = {
  pending:   '待提交',
  in_review: '审批中',
  approved:  '已通过',
  rejected:  '已驳回',
  withdrawn: '已撤回',
};
const STATUS_CLS = {
  pending:   'badge-pending',
  in_review: 'badge-review',
  approved:  'badge-ok',
  rejected:  'badge-err',
  withdrawn: 'badge-gray',
};

// ── 加载列表 ──────────────────────────────────────────────────────────────────
async function loadOrders() {
  const res = await api('/api/approval/orders');
  _orders = res?.data || [];
  renderList();
}

function renderList() {
  const el = document.getElementById('order-list');
  if (!_orders.length) {
    el.innerHTML = '<div class="empty-tip">暂无审批单</div>';
    return;
  }
  el.innerHTML = _orders.map(o => `
    <div class="order-item ${_selected?.gid === o.gid ? 'active' : ''}"
         data-gid="${o.gid}" onclick="selectOrder('${o.gid}')">
      <div class="order-type">${o.order_type}</div>
      <div class="order-meta">${o.applicant_gid || '—'}</div>
      <span class="badge ${STATUS_CLS[o.status] || ''}">${STATUS_LABEL[o.status] || o.status}</span>
    </div>
  `).join('');
}

// ── 选择审批单 ────────────────────────────────────────────────────────────────
async function selectOrder(gid) {
  const res = await api(`/api/approval/orders/${gid}`);
  if (!res?.data) { console.error('获取审批单失败'); return; }
  _selected = res.data;
  renderDetail();
  renderList();
}

function renderDetail() {
  const o = _selected;
  if (!o) return;

  document.getElementById('detail-title').textContent =
    `${o.order_type} — ${STATUS_LABEL[o.status] || o.status}`;

  document.getElementById('detail-body').innerHTML = `
    <table class="info-table">
      <tr><th>申请人</th><td>${o.applicant_gid || '—'}</td></tr>
      <tr><th>项目</th><td>${o.project_gid || '—'}</td></tr>
      <tr><th>类型</th><td>${o.order_type}</td></tr>
      <tr><th>来源</th><td>${JSON.stringify(o.source_ref)}</td></tr>
      <tr><th>状态</th><td><span class="badge ${STATUS_CLS[o.status] || ''}">${STATUS_LABEL[o.status] || o.status}</span></td></tr>
    </table>
  `;

  // 流程步骤条
  const steps = ['待提交', '审批中', '完结'];
  const stepIdx = { pending: 0, in_review: 1, approved: 2, rejected: 2, withdrawn: 2 };
  const curStep = stepIdx[o.status] ?? 0;
  document.getElementById('flow-steps').innerHTML = steps.map((s, i) => `
    <div class="step ${i < curStep ? 'done' : i === curStep ? 'active' : ''}">
      <div class="step-dot"></div>
      <div class="step-label">${s}</div>
    </div>
  `).join('<div class="step-line"></div>');

  // 操作区：仅 pending/in_review 时显示
  const actionArea = document.getElementById('action-area');
  actionArea.style.display = o.is_finished ? 'none' : '';

  // 意见区
  const opinionsArea = document.getElementById('opinions-area');
  const opinionsList = document.getElementById('opinions-list');
  if (o.opinions?.length) {
    opinionsArea.style.display = '';
    opinionsList.innerHTML = o.opinions.map(op => `
      <div class="opinion-item">
        <span class="op-decision ${op.decision === 'approve' ? 'op-ok' : 'op-err'}">
          ${op.decision === 'approve' ? svgIcon('icon-check', 13) + ' 通过' : svgIcon('icon-x', 13) + ' 驳回'}
        </span>
        <span class="op-user">${op.approver_gid}</span>
        <span class="op-comment">${op.comment || ''}</span>
      </div>
    `).join('');
  } else {
    opinionsArea.style.display = 'none';
  }
}

// ── 审批操作 ──────────────────────────────────────────────────────────────────
async function approveOrder() {
  if (!_selected) return;
  const comment = document.getElementById('approval-remark').value.trim();
  if (_selected.status === 'pending') {
    await api(`/api/approval/orders/${_selected.gid}/start`, { method: 'POST' });
  }
  const res = await api(`/api/approval/orders/${_selected.gid}/approve`, {
    method: 'POST',
    body: JSON.stringify({ comment }),
  });
  if (res?.success !== false) {
    document.getElementById('approval-remark').value = '';
    await loadOrders();
    await selectOrder(_selected.gid);
  } else {
    alert('操作失败：' + (res?.error || '未知错误'));
  }
}

async function rejectOrder() {
  if (!_selected) return;
  const comment = document.getElementById('approval-remark').value.trim();
  if (!comment) { alert('驳回请填写审批意见'); return; }
  if (_selected.status === 'pending') {
    await api(`/api/approval/orders/${_selected.gid}/start`, { method: 'POST' });
  }
  const res = await api(`/api/approval/orders/${_selected.gid}/reject`, {
    method: 'POST',
    body: JSON.stringify({ comment }),
  });
  if (res?.success !== false) {
    document.getElementById('approval-remark').value = '';
    await loadOrders();
    await selectOrder(_selected.gid);
  } else {
    alert('操作失败：' + (res?.error || '未知错误'));
  }
}

async function withdrawOrder() {
  if (!_selected) return;
  const res = await api(`/api/approval/orders/${_selected.gid}/withdraw`, { method: 'POST' });
  if (res?.success !== false) {
    await loadOrders();
    await selectOrder(_selected.gid);
  } else {
    alert('操作失败：' + (res?.error || '未知错误'));
  }
}

// ── 事件绑定 ──────────────────────────────────────────────────────────────────
function bindEvents() {
  document.getElementById('btn-refresh')?.addEventListener('click', loadOrders);
  document.getElementById('btn-approve')?.addEventListener('click', approveOrder);
  document.getElementById('btn-reject')?.addEventListener('click', rejectOrder);
  document.getElementById('btn-withdraw')?.addEventListener('click', withdrawOrder);
}

// ── 启动 ──────────────────────────────────────────────────────────────────────
function init() {
  bindEvents();
  loadOrders();
}

document.addEventListener('DOMContentLoaded', init);
