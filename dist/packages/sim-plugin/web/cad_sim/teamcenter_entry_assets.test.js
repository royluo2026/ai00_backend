const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = __dirname;
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const script = fs.readFileSync(path.join(root, 'cad_sim.js'), 'utf8');

test('Teamcenter entry loads the script and styles from its own cache-busted release', () => {
  assert.match(html, /id="btnAddTeamcenterSource"/);
  assert.match(html, /id="btnTeamcenterSession"[^>]+data-state="checking"/);
  assert.match(html, /teamcenter_session\.js\?v=20260917-teamcenter-search-fix-v2/);
  assert.match(script, /btnAddTeamcenterSource.*addEventListener\('click'/);
  assert.match(script, /btnTeamcenterSession.*addEventListener\('click'/);
  assert.match(script, /_refreshTeamcenterSessionButton\(\)/);
  assert.match(script, /async function _openTeamcenterSessionControl\(\)[\s\S]+?await _requireConnectorRuntime\(\)/);
  assert.match(script, /新文档打开/);
  assert.match(script, /插入当前 VisMockup 文档/);
  assert.doesNotMatch(script, /await window\.AI00TeamcenterOnlineSource\.launchOnline\(_requestVisMockupCommand,source\)/);
  assert.match(html, /cad_sim\.css\?rev=20260918-teamcenter-session-button-1/);
  assert.match(html, /cad_sim\.js\?rev=20260921-online-model-occurrence-path-3/);
  assert.match(fs.readFileSync(path.join(root, 'cad_sim.css'), 'utf8'), /data-state="ready"[^}]+#2d9444/);
  assert.match(html, /teamcenter_online_source\.js\?v=20260917-teamcenter-runtime-controls-2/);
  assert.match(html, /live_document_adoption\.js\?v=20260918-online-occurrence-locator-fix/);
  assert.match(html, /tree_projection_cache\.js\?v=20260916-model-load-state-3/);
});
