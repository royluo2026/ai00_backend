const token = (localStorage.getItem('ai00_token') || '').trim();
const code = new URLSearchParams(location.search).get('code') || '';
const statusNode = document.getElementById('status');
const summaryNode = document.getElementById('summary');
const approveButton = document.getElementById('approve');
let resourceVersion = 0;

function message(value) { statusNode.textContent = value; }


async function invokeCapability(capabilityId,payload,{confirm=false}={}) { return window.AI00Business.invoke(capabilityId,{version:1,payload}); }

async function load() {

  if (!code) { message('缺少配对码，请从 Connector 重新发起绑定。'); return; }
  try {
    const data = await invokeCapability('simulation.connector.pairing.summary.get', { user_code: code });
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
    await invokeCapability('simulation.connector.pairing.approve', {
      user_code: code, expected_version: resourceVersion,
    }, { confirm: true });
    message('绑定已确认，可以关闭此页面。');
  } catch (error) { message(`绑定失败：${error.message}`); approveButton.disabled = false; }
});

load();
