const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const script = fs.readFileSync(path.join(__dirname, 'bop.js'), 'utf8');
const html = fs.readFileSync(path.join(__dirname, 'bop.html'), 'utf8');

test('project fork uses governed repository preview/apply and retires legacy fork', () => {
  assert.match(script, /craft\.bop\.repository\.fork\.preview/);
  assert.match(script, /craft\.bop\.repository\.fork\.apply/);
  assert.doesNotMatch(script, /craft\.bop\.fork\.change\.apply/);
  assert.doesNotMatch(html, /inp-fork-preset|inp-fork-tag|fork-field-rules/);
});

test('project fork is visible only to super admin and offers five copy depths', () => {
  assert.match(script, /\.\.\.\(_isSuperAdmin\(\) \? \[\{/);
  assert.match(script, /只有超级管理员可以 Fork 主项目/);
  for (const depth of ['all', 'operation', 'process', 'role', 'station']) {
    assert.match(html, new RegExp(`value="${depth}"`));
  }
});
