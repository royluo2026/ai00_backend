const assert = require('node:assert/strict');
const { build } = require('./bop_vm_binding_draft');

const tree = (...nodes) => ({ children: [{ _synthetic: true, children: nodes }] });

{
  const draft = build([{ gid: '10', part_feed: true, parts: [{ catia_occ: 'P-1' }] }], tree({ key: '1', catia_name: 'P-1' }));
  assert.equal(draft.mode, 'parts');
  assert.equal(draft.auto_count, 1);
  assert.deepEqual(draft.bindings[0], {
    bop_node_gid: '10', vm_node_key: '1', role: 'load', disposition: 'auto',
    confidence_milli: 1000, match_basis: 'part_identity_exact',
  });
}
{
  const draft = build([{ gid: '10', vpps: 'VPPS-A', parts: [] }], tree({ key: '1', product_ref: 'VPPS-A' }));
  assert.equal(draft.mode, 'vpps');
  assert.equal(draft.bindings[0].match_basis, 'vpps_exact');
}
{
  const draft = build([{ gid: '10', vpps: 'VPPS-A', parts: [] }], tree({ key: '1', name: 'VPPS-A' }));
  assert.equal(draft.auto_count, 0, 'a matching display name must never auto-bind');
}
{
  const draft = build([{ gid: '10', parts: [] }], tree({ key: '1', name: 'P-1' }));
  assert.equal(draft.mode, 'structure_only');
  assert.equal(draft.bindings.length, 0);
  assert.deepEqual(draft.unmatched_vm_node_keys, ['1']);
}
console.log('bop_vm_binding_draft tests passed');
