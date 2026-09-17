const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../src/Ai00.Connector.Adapters.VisMockup/teamcenter_readonly_worker.js'), 'utf8');
function run(path = [], mode = '') {
  const calls = [];
  const obj = (uid, occurrence) => ({getUid: () => uid, occurrence});
  const root = obj('runtime-root'), a = obj('runtime-a','edge-a'), b = obj('runtime-b','edge-b');
  const rev = obj('rev');
  const context = {
    observationTiming: () => {},
    Java: {from: x => x, to: x => x}, ExpandPSOneLevelInfo: function(){}, ExpandPSOneLevelPref: function(){},
    fail: code => {throw Error(code)}, serviceErrors: x => x || [],
    display: (o,k) => k === 'bl_occurrence_uid' ? (mode==='missing' ? '' : o.occurrence) : 'Same',
    modelObject: () => rev,
    dm: {getProperties: objects => {assert(objects.length<=500); return [];}},
    structure: {expandPSOneLevel: info => {
      assert.equal(info.excludeFilter, 'None2', '2008-06 expansion uses the versioned no-exclusion filter');
      const p=info.parentBomLines[0]; calls.push(p.getUid());
      return {serviceData:mode==='partial'?['error']:[], output:[{parent:{bomLine:p},children:p===root ? [{bomLine:a,objectOfBOMLine:rev},{bomLine:mode==='ambiguous'?a:b,objectOfBOMLine:rev}] : []}]};
    }}
  };
  vm.createContext(context);
  const start = source.indexOf('function readChildrenLevel(');
  assert(start >= 0, 'single-level children implementation missing');
  vm.runInContext(source.slice(start, source.indexOf('\nfunction ',start+1)),context);
  const value=context.readChildrenLevel(root,rev,path);
  return {value,calls};
}
assert.equal(run().value.nodes.length,2);
assert.deepEqual(run().calls,['runtime-root']);
assert.deepEqual(run([{occurrence_uid:'edge-b',item_revision_uid:'rev'}]).calls,['runtime-root','runtime-b']);
assert.throws(()=>run([{occurrence_uid:'edge-b',item_revision_uid:'wrong'}]),/teamcenter_parent_path_not_found/);
assert.throws(()=>run([],'partial'),/teamcenter_structure_expand_failed/);
assert.throws(()=>run([],'missing'),/teamcenter_occurrence_identity_invalid/);
assert.throws(()=>run([],'ambiguous'),/teamcenter_occurrence_identity_invalid/);
console.log('children single-level traversal, identity and failure tests passed');
