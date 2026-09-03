const token = (localStorage.getItem('ai00_token') || '').trim();
const code = new URLSearchParams(location.search).get('code') || '';
const statusNode = document.getElementById('status');
const summaryNode = document.getElementById('summary');
const approveButton = document.getElementById('approve');
let resourceVersion = 0;

function message(value) { statusNode.textContent = value; }
async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { 'Content-Type': 'application/json', 'X-AI00-Token': token, ...(options.headers || {}) },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body?.detail?.code || `HTTP ${response.status}`);
  return body.data;
}

async function load() {
  if (!token) { message('请先在 AI00 中使用飞书登录，再重新打开此页面。'); return; }
  if (!code) { message('缺少配对码，请从 Connector 重新发起绑定。'); return; }
  try {
    const data = await request(`/api/v1/simulation/connectors/pairings/${encodeURIComponent(code)}`);
    resourceVersion = data.resource_version;
    document.getElementById('code').textContent = data.user_code;
    document.getElementById('device').textContent = data.device_name;
    document.getElementById('windows-user').textContent = data.masked_windows_user;
    document.getElementById('version').textContent = data.runtime_version;
    summaryNode.hidden = false;
    approveButton.disabled = data.status !== 'pending';
    message(data.status === 'pending' ? '请核对下列信息。' : `当前状态：${data.status}`);
  } catch (error) { message(`无法读取配对请求：${error.message}`); }
}

approveButton.addEventListener('click', async () => {
  approveButton.disabled = true;
  try {
    await request(`/api/v1/simulation/connectors/pairings/${encodeURIComponent(code)}/approve`, {
      method: 'POST', body: JSON.stringify({ expected_version: resourceVersion }),
    });
    message('绑定已确认，可以关闭此页面。');
  } catch (error) { message(`绑定失败：${error.message}`); approveButton.disabled = false; }
});

load();
