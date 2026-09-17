const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const script = fs.readFileSync(path.join(__dirname, '../src/Ai00.Connector.Adapters.VisMockup/teamcenter_readonly_worker.js'), 'utf8');
const search = script.slice(script.indexOf('    var search=request.payload;'), script.indexOf('\n  } else {', script.indexOf('    var search=request.payload;')));
function run(serverError = false, exactHit = true, returnedRevision = '00') {
  let output, calls = 0, batchSizes = [];
  const item = { getUid: () => 'item-1' };
  const revision = { getUid: () => 'rev-1', getTypeObject: () => ({ getName: () => 'ItemRevision' }) };
  const fields = [['object_name', '名称'], ['items_tag.item_id', '零组件 ID'], ['item_revision_id', '版本']].map(([attributeName, entryName]) => ({ attributeName, entryName }));
  const queryService = {
    getSavedQueries: () => ({ queries: [{ name: '__Item_Revision_name_ID_and_rev', query: {} }] }),
    describeSavedQueries: () => ({ fieldLists: [{ fields }] }),
    executeSavedQueries: (inputs) => {
      calls++;
      batchSizes.push(inputs.length);
      inputs.forEach(input => {
        assert(['零组件 ID', '名称'].includes(input.entries[0]), 'must use server entryName, not attributeName');
        assert.equal(input.entries.length, 1, 'revision must be filtered from returned objects, not joined in Saved Query');
      });
      const objects = calls === 1 && !exactHit ? [] : [revision];
      return { serviceData: serverError ? [3031, 3006] : [], arrayOfResults: inputs.map(() => ({ objects })) };
    }
  };
  vm.runInNewContext(search, {
    request: { payload: { item_id: 'W10-ENG00001', revision_id: '00', revision_rule: 'Latest Working', configuration_date: '2026-09-16' } },
    closed: () => true, connection: {}, Java: { from: x => x, to: x => x },
    SavedQueryService: { getService: () => queryService }, SavedQueryInput: function () {},
    DataManagementService: { getService: () => ({ getProperties: () => ({}) }) },
    serviceErrors: value => value?.length ? [{ codes: value }] : [],
    fail: code => { throw Error(code); }, modelObject: () => item,
    display: (_, key) => ({ item_id: 'W10-ENG00001', item_revision_id: returnedRevision }[key] || ''),
    print: value => { output = JSON.parse(value); }
  });
  assert.deepEqual(batchSizes, exactHit ? [1] : [1, 2]);
  return output;
}
assert.equal(run().result.items[0].item_id, 'W10-ENG00001');
assert.equal(run(false, false).result.items[0].item_id, 'W10-ENG00001');
assert.equal(run(false, true, '01').result.items.length, 0);
assert.throws(() => run(true), /teamcenter_search_failed/);
console.log('Teamcenter saved-query entry mapping and errors passed');
