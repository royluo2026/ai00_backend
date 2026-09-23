'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

const source = fs.readFileSync(path.join(__dirname, '..', 'org_mgmt', 'org_mgmt.js'), 'utf8');
const html = fs.readFileSync(path.join(__dirname, '..', 'org_mgmt', 'org_mgmt.html'), 'utf8')
  .replace(/<script[^>]+src=[^>]+><\/script>/g, '');

function boot() {
  const calls = [];
  const dom = new JSDOM(html, { runScripts: 'dangerously', url: 'http://localhost/' });
  dom.window.AI00Business = {
    available: () => true,
    request: async () => ({ success: true, data: { ok: true, data: { data: [] } } }),
    invoke: async (id, envelope) => {
      calls.push({ id, payload: envelope.payload });
      return id === 'base.team.create'
        ? { success: true, data: { gid: 'new-team', name: envelope.payload.name } }
        : { success: true };
    },
  };
  dom.window.eval(`${source}\nwindow.__showTeam = async (teams, gid) => { _allTeams = teams; _selectedTeamGid = gid; _renderStructTree(); await _loadTeamDetail(gid); };`);
  return { dom, calls };
}

(async () => {
  const { dom, calls } = boot();
  const { document, Event } = dom.window;
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.ok(document.getElementById('stManualAddBtn'),
    '组织为空时也必须保留新建入口');
  const teams = [
    { gid: 'root', name: '制造工程', parent_team_gid: null },
    { gid: 'child', name: '总装', parent_team_gid: 'root' },
    { gid: 'grandchild', name: '一线', parent_team_gid: 'child' },
  ];

  await dom.window.__showTeam(teams, 'child');
  const parent = document.getElementById('struct-parent-select');
  assert.ok(parent, '编辑组织必须提供上级组织选择');
  assert.equal(parent.value, 'root');
  assert.match(parent.options[0].textContent, /一级组织/);
  assert.deepEqual([...parent.options].map(option => option.value), ['', 'root'],
    '上级候选必须排除当前组织及其下级');

  parent.value = '';
  parent.dispatchEvent(new Event('change', { bubbles: true }));
  document.getElementById('struct-save-btn').click();
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(JSON.stringify(calls.at(-1)), JSON.stringify({
    id: 'base.team.update',
    payload: { team_gid: 'child', changes: { parent_team_gid: null } },
  }), '只调整上级也必须保存，空上级写为 null');

  document.getElementById('stManualAddBtn').click();
  const createParent = document.getElementById('stManualAddParent');
  assert.ok(createParent, '新建组织必须可以选择上级');
  assert.equal(createParent.value, '', '新建组织默认一级');
  createParent.value = 'root';
  document.getElementById('stManualAddInp').value = '焊装';
  document.getElementById('stManualAddOk').click();
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(JSON.stringify(calls.at(-1)), JSON.stringify({
    id: 'base.team.create',
    payload: { name: '焊装', parent_team_gid: 'root' },
  }));
  dom.window.close();
  console.log('org management parent selection behavior passed');
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
