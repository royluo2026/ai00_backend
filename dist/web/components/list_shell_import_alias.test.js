const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

test('import configuration preserves module-specific Excel aliases', () => {
  const source = fs.readFileSync(path.join(__dirname, 'list_shell.js'), 'utf8');
  const context = {
    window: { addEventListener() {} },
    document: { documentElement: { setAttribute() {} } },
    localStorage: { getItem() { return null; } },
  };
  vm.runInNewContext(`${source}\n;globalThis.Shell = ListShell;`, context);

  const aliases = { VPPS: 'vpps', Level: 'level' };
  const config = context.Shell.makeImportExport('std_op_lib', () => [], async () => {}, aliases);

  assert.deepEqual(config.colAliasMap, aliases);
});
