const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, 'cad_sim.js'), 'utf8');
const dialog = source.slice(source.indexOf('async function _teamcenterSourceDialog'), source.indexOf('async function _addTeamcenterSource'));
const add = source.slice(source.indexOf('async function _addTeamcenterSource'), source.indexOf('function _dependencyFilename'));

assert.match(dialog, /data-add disabled>添加到模型文件/);
assert.doesNotMatch(dialog, /data-open=/);
assert.doesNotMatch(dialog, /try\{const rules=await window\.AI00TeamcenterOnlineSource\.revisionRules/);
assert.match(dialog, /cachedRevisionRules\(\)/);
assert.match(dialog, /select\.addEventListener\('pointerdown',loadRules/);
assert.match(dialog, /clearRevisionRules\(\)/);
assert.doesNotMatch(add, /openOnline/);
assert.match(source, /disabled:Boolean\(documentRow\._onlineOpening\)\|\|\(mode==='insert'&&!_vmDocumentReady\)/);
assert.match(source, /当前 VisMockup 没有可插入的活动文档/);
assert.match(source, /if\(mode==='insert'&&!_vmDocumentReady\)/);
console.log('teamcenter_source_dialog tests passed');
