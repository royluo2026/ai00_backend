'use strict';

const assert = require('assert/strict');
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

function loadManager() {
  const dom = new JSDOM('<!doctype html><html><body></body></html>', {
    runScripts: 'dangerously',
    url: 'http://localhost',
  });
  const script = dom.window.document.createElement('script');
  script.textContent = fs.readFileSync(path.join(__dirname, 'auth_state.js'), 'utf8');
  dom.window.document.head.appendChild(script);
  return dom.window.AuthStateManager;
}

async function runAuthStateTests() {
  const manager = loadManager();
  const user = { gid: 'user-1', name: 'Test user' };
  const merged = manager.mergeUserProfile(user, {
    success: true,
    data: {
      permissions: ['system.capability.read', 'system.capability.govern'],
      grants: [{ grant_type: 'team_admin', scope_gid: 'team-1' }],
      org_role: 'team_admin',
      visible_panels: ['plugin-market'],
    },
  });
  assert.deepEqual(merged.permissions, ['system.capability.read', 'system.capability.govern']);
  assert.deepEqual(merged.grants, [{ grant_type: 'team_admin', scope_gid: 'team-1' }]);
  assert.equal(merged.org_role, 'team_admin');
  assert.deepEqual(merged.visible_panels, ['plugin-market']);
  assert.equal(user.permissions, undefined, 'profile merge must return a new object');

  const status = manager.formatUserStatus({
    name: '治理管理员',
    org_role: 'super_admin',
    permissions: ['system.capability.read', 'system.capability.govern'],
  }, 'feishu');
  assert.equal(status.authenticated, true);
  assert.match(status.text, /治理管理员/);
  assert.match(status.text, /super_admin/);
  assert.match(status.title, /已通过后端鉴权/);
}

module.exports = { runAuthStateTests };
