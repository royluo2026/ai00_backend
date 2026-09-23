const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

test('nested iframe import uses the top window cloud transport', async () => {
  const calls = [];
  const host = {
    _cloudFetch: async (requestPath, options) => {
      calls.push({ requestPath, options });
      return { success: true, data: { headers: [], rows: [] } };
    },
  };
  const frame = { parent: {}, top: host };
  frame.window = frame;

  const source = fs.readFileSync(path.join(__dirname, 'import_export.js'), 'utf8');
  const context = { window: frame, console, setTimeout };
  vm.runInNewContext(`${source}\n;globalThis.Manager = ImportExportManager;`, context);

  const parsed = await context.Manager.prototype._cf.call(
    {}, 'POST', '/api/import-export/import/parse-excel', { file_b64: 'AA==' },
  );

  assert.deepEqual(parsed, { headers: [], rows: [] });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].requestPath, '/api/import-export/import/parse-excel');
});
