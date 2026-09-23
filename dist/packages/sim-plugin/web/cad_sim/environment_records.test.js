const assert = require('assert');
const { JSDOM } = require('jsdom');

const dom = new JSDOM('<div id="records"></div>');
global.document = dom.window.document;
global.window = dom.window;
require('./environment_records.js');

const container = document.getElementById('records');
global.AI00SimulationEnvironmentRecords.render(container, [
  {
    kind: 'project_spaces', label: '项目空间', items: [
      { record_gid: '11', record_kind: 'team', display_label: 'X13-2026' },
      { record_kind: 'team', display_label: 'OC11-2026', unavailable: true },
    ],
  },
  { kind: 'personal_project_spaces', label: '个人项目空间', items: [
    { record_gid: '12', record_kind: 'managed_personal', display_label: 'X13-2026' },
    { record_kind: 'managed_personal', display_label: 'OC11-2026', unavailable: true },
  ] },
  { kind: 'private', label: '私人仿真环境', items: [
    { record_gid: '31', record_kind: 'private', status: 'active' },
    { record_gid: '32', record_kind: 'private', status: 'archived' },
    { record_gid: '33', workspace_gid: '33', version_gid: '34', record_kind: 'private', status: 'frozen' },
  ] },
], null);

const projects = container.querySelectorAll('details.cs-environment-project');
assert.equal(projects.length, 1, 'the environment library must not render Craft project spaces as Simulation environments');
assert.equal(projects[0].open, true, 'personal simulation environments are expanded initially');
assert.equal(container.querySelector('[data-record-kind="team"]'), null);
assert.equal(container.querySelector('[data-record-kind="managed_personal"]'), null);
const statuses = projects[0].querySelectorAll('details.cs-environment-status-group');
assert.equal(statuses.length, 3);
assert.equal(statuses[0].open, true, 'active private environments are expanded initially');
assert.equal(statuses[1].open, false, 'archived private environments are collapsed initially');
assert.equal(container.querySelector('[data-record-kind="private"] .name').textContent, '未命名环境');
assert.equal(container.querySelector('[data-action="replay"][data-record-gid="33"]').textContent, '在 VisMockup 重放');

console.log('environment records: PASS');
