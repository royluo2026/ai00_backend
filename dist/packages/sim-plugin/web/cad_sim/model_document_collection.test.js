const test = require('node:test');
const assert = require('node:assert/strict');
const { createCollection, collectVisibilityLeaves, deriveVisibilityState, buildHierarchyForest, buildProductForest, readAllProductTreePages } = require('./model_document_collection');
const fs = require('node:fs');

test('collection keeps exactly one primary and deterministic document order', () => {
  const collection = createCollection();
  collection.replace([
    { document_gid: '3', role: 'inserted', display_name: 'Tool.jt', media_type: 'model/vnd.jt', portability: 'portable' },
    { document_gid: '1', role: 'primary', display_name: 'W10.plmxml', media_type: 'application/plmxml+xml', portability: 'portable' },
    { document_gid: '2', role: 'inserted', display_name: 'Fixture.jt', media_type: 'model/vnd.jt', portability: 'device_bound' },
  ]);
  assert.deepEqual(collection.state.documents.map(item => item.document_gid), ['1', '2', '3']);
  assert.equal(collection.state.documents.filter(item => item.role === 'primary').length, 1);
});

test('collection exposes empty hierarchies and does not duplicate source documents as placements', () => {
  const collection = createCollection();
  collection.replaceHierarchies([{ hierarchy_gid: '10', name: 'ALT Hier #1', placements: [] }]);
  collection.addPlacement('10', { placement_gid: '20', source_ref: { document_gid: '3' }, target_node_gid: '4' });
  collection.addPlacement('10', { placement_gid: '21', source_ref: { document_gid: '3' }, target_node_gid: '5' });
  assert.equal(collection.state.hierarchies[0].placements.length, 2);
  assert.equal(collection.state.documents.length, 0);
  assert.equal(collection.state.selectedHierarchyGid, '10');
});

test('hierarchy search rows remain unloaded until detail is fetched', () => {
  const collection = createCollection();
  collection.replaceHierarchies([{ hierarchy_gid: '10', name: '前悬分装线' }]);
  assert.equal(collection.state.hierarchies[0].nodes, undefined);
  assert.equal(collection.state.hierarchies[0].placements, undefined);
  collection.replaceHierarchies([{ hierarchy_gid: '10', name: '前悬分装线',
    nodes: [{ node_gid: '11', parent_gid: null }], placements: [] }]);
  assert.equal(collection.state.hierarchies[0].nodes.length, 1);
});

test('alternate hierarchy selection remains explicit and rejects unknown rows', () => {
  const collection = createCollection();
  collection.replaceHierarchies([
    { hierarchy_gid: '11', name: 'ALT 2', placements: [] },
    { hierarchy_gid: '10', name: 'ALT 1', placements: [] },
  ]);
  collection.selectHierarchy('11');
  assert.equal(collection.state.selectedHierarchyGid, '11');
  assert.throws(() => collection.selectHierarchy('99'), /alternate_hierarchy_not_found/);
});

test('alternate hierarchy nodes and placements form a deterministic editable tree', () => {
  const forest = buildHierarchyForest({
    nodes: [
      { node_gid: '12', parent_gid: '10', name: '工位', sort_order: 2 },
      { node_gid: '10', parent_gid: null, name: 'ALT Hier', sort_order: 0 },
      { node_gid: '11', parent_gid: '10', name: '工序', sort_order: 1 },
    ],
    placements: [
      { placement_gid: '22', target_node_gid: '11', parent_placement_gid: '21', display_name: '螺栓', sort_order: 1 },
      { placement_gid: '21', target_node_gid: '11', parent_placement_gid: null, display_name: '车身', sort_order: 0 },
      { placement_gid: '23', target_node_gid: '12', parent_placement_gid: null, display_name: '工具', sort_order: 0 },
    ],
  });
  assert.deepEqual(forest.map(item => item.key), ['node:10']);
  assert.deepEqual(forest[0].children.map(item => item.key), ['node:11', 'node:12']);
  assert.deepEqual(forest[0].children[0].children.map(item => item.key), ['placement:21']);
  assert.deepEqual(forest[0].children[0].children[0].children.map(item => item.key), ['placement:22']);
  assert.equal(forest[0].children[1].children[0].kind, 'placement');
  assert.throws(() => buildHierarchyForest({ nodes: [{ node_gid: '1', parent_gid: '9' }], placements: [] }), /hierarchy_parent_missing/);
});

test('imported PLMXML hierarchy renders a free-standing root placement tree', () => {
  const forest = buildHierarchyForest({
    nodes: [],
    placements: [
      { placement_gid: '20', parent_placement_gid: '19', target_node_gid: null, display_name: 'Part', sort_order: 1 },
      { placement_gid: '19', parent_placement_gid: null, target_node_gid: null, display_name: 'Assembly', sort_order: 0 },
    ],
  });

  assert.equal(forest.length, 1);
  assert.equal(forest[0].placement_gid, '19');
  assert.equal(forest[0].children[0].placement_gid, '20');
});

test('model document product nodes form a deterministic read-only forest', () => {
  const forest = buildProductForest([
    { node_key: 'child-b', parent_key: 'root', name: 'B', child_order: 2 },
    { node_key: 'root', parent_key: null, name: 'Root', child_order: 0 },
    { node_key: 'child-a', parent_key: 'root', name: 'A', child_order: 1 },
  ]);
  assert.deepEqual(forest.map(item => item.node_key), ['root']);
  assert.deepEqual(forest[0].children.map(item => item.node_key), ['child-a', 'child-b']);
  assert.throws(() => buildProductForest([{ node_key: 'child', parent_key: 'missing' }]), /product_parent_missing/);
});

test('model document product tree is fetched in bounded pages before indexing', async () => {
  const calls = [];
  const pages = [
    { state: 'ready', node_count: 2, nodes: [{ node_key: 'root', parent_key: null }], dependency_locations: [], next_offset: 1 },
    { state: 'ready', node_count: 2, nodes: [{ node_key: 'child', parent_key: 'root' }], dependency_locations: [], next_offset: null },
  ];
  const result = await readAllProductTreePages(async (capabilityId, payload) => {
    calls.push({ capabilityId, payload });
    return pages.shift();
  }, { artifact_id: 'artifact-1' }, 1);

  assert.deepEqual(calls, [
    { capabilityId: 'simulation.plmxml.model_tree.read', payload: { artifact_ref: { artifact_id: 'artifact-1' }, offset: 0, limit: 1 } },
    { capabilityId: 'simulation.plmxml.model_tree.read', payload: { artifact_ref: { artifact_id: 'artifact-1' }, offset: 1, limit: 1 } },
  ]);
  assert.equal(result.node_count, 2);
  assert.deepEqual(result.nodes.map(item => item.node_key), ['root', 'child']);
  assert.equal(result.next_offset, null);
});

test('imported product tree pages carry the database document identity', async () => {
  const calls = [];
  await readAllProductTreePages(async (_capabilityId, payload) => {
    calls.push(payload);
    return { state: 'ready', node_count: 1, nodes: [{ node_key: 'part' }], dependency_locations: [], next_offset: null };
  }, { artifact_id: 'artifact-1' }, 5000, [], '44');
  assert.equal(calls[0].document_gid, '44');
});

test('model document product tree forwards matched dependency artifacts and preserves pending references', async () => {
  const calls = [];
  const pages = [
    { state: 'ready', node_count: 1, nodes: [{ node_key: 'root', parent_key: null }], dependency_locations: ['part.jt'], next_offset: null },
  ];
  const result = await readAllProductTreePages(async (capabilityId, payload) => {
    calls.push({ capabilityId, payload });
    return pages.shift();
  }, { artifact_id: 'artifact-primary' }, 5000, [
    { location: 'base.plmxml', artifact_ref: { artifact_id: 'artifact-dependency' } },
  ]);

  assert.deepEqual(calls[0], {
    capabilityId: 'simulation.plmxml.model_tree.read',
    payload: {
      artifact_ref: { artifact_id: 'artifact-primary' }, offset: 0, limit: 5000,
      dependency_artifacts: [{ location: 'base.plmxml', artifact_ref: { artifact_id: 'artifact-dependency' } }],
    },
  });
  assert.deepEqual(result.dependency_locations, ['part.jt']);
});

test('runtime progress and environment state preserve specific failure outcomes', () => {
  const collection = createCollection();
  collection.setRuntimeProgress('reading_back', { elapsedSeconds: 4 });
  collection.setRuntimeProgress('read_back', { elapsedSeconds: 5 });
  collection.setEnvironmentState('runtime_drifted', { domainCode: 'document_set_mismatch', reportRef: 'artifact_report' });
  assert.equal(collection.state.runtimeState, 'read_back');
  assert.equal(collection.state.environmentState, 'runtime_drifted');
  assert.equal(collection.state.failure.domainCode, 'document_set_mismatch');
  collection.setEnvironmentState('outcome_unknown', { domainCode: 'local_execution_outcome_unknown' });
  assert.equal(collection.state.environmentState, 'outcome_unknown');
});

test('invalid primary cardinality and unsupported media fail closed', () => {
  const collection = createCollection();
  collection.replace([{ document_gid: '2', role: 'primary', display_name: 'live', media_type: 'application/vnd.siemens.teamcenter.visualization-document' }]);
  collection.replace([]);
  assert.deepEqual(collection.state.documents, []);
  assert.equal(collection.state.selectedDocumentGid, null);
  assert.throws(() => collection.replace([{ document_gid: '1', role: 'inserted', display_name: 'a.jt', media_type: 'model/vnd.jt' }]), /primary_model_document_required/);
  assert.throws(() => collection.replace([{ document_gid: '1', role: 'primary', display_name: 'a.exe', media_type: 'application\/x-msdownload' }]), /model_document_media_type_invalid/);
});

test('visibility state includes collapsed descendants and supports checked mixed and disabled', () => {
  const tree = { key: 'root', visible: true, children: [
    { key: 'a', visible: true, children: [] },
    { key: 'branch', visible: true, children: [
      { key: 'b', visible: false, children: [] },
      { key: '', visible: true, controllable: false, children: [] },
    ] },
  ] };
  assert.deepEqual(collectVisibilityLeaves(tree).map(item => item.key), ['a', 'b']);
  assert.deepEqual(deriveVisibilityState(tree), { checked: false, indeterminate: true, disabled: false, controllableCount: 2 });
  assert.deepEqual(deriveVisibilityState({ children: [{ key: '', controllable: false, children: [] }] }),
    { checked: false, indeterminate: false, disabled: true, controllableCount: 0 });
});

test('unknown visibility is unavailable instead of assumed visible', () => {
  assert.deepEqual(deriveVisibilityState({ children: [{ key: 'a', visible: null, children: [] }] }),
    { checked: false, indeterminate: false, disabled: true, controllableCount: 1 });
  assert.deepEqual(deriveVisibilityState({ children: [
    { key: 'a', visible: true, children: [] }, { key: 'b', visible: false, children: [] },
  ] }), { checked: false, indeterminate: true, disabled: false, controllableCount: 2 });
});

test('cad simulation wires governed persistence and keeps VisMockup synchronization explicit', () => {
  const html = fs.readFileSync(require.resolve('./index.html'), 'utf8');
  const source = fs.readFileSync(require.resolve('./cad_sim.js'), 'utf8');
  const collectionSource = fs.readFileSync(require.resolve('./model_document_collection.js'), 'utf8');
  const electronClientSource = fs.readFileSync(require.resolve('../../../core/electron/capability_client.js'), 'utf8');
  assert.match(html, /model_document_collection\.js/);
  assert.match(html, /id="modelDocumentList"/);
  assert.match(source, /simulation\.environment\.model_document\.search/);
  assert.match(source, /simulation\.environment\.alternate_hierarchy\.search/);
  assert.match(source, /simulation\.environment\.placement\.create/);
  assert.match(source, /simulation\.environment\.placement\.remove/);
  assert.match(source, /simulation\.environment\.alternate_hierarchy\.update/);
  assert.match(source, /simulation\.environment\.alternate_hierarchy\.archive/);
  assert.match(source, /craft\.resource_requirement\.search/);
  assert.match(source, /application\/x-ai00-resource/);
  assert.match(source, /simulation\.plmxml\.environment\.inspect/);
  assert.match(source, /readAllProductTreePages/);
  assert.match(source, /matchedModelDependencyArtifacts/);
  assert.match(collectionSource, /simulation\.plmxml\.model_tree\.read/);
  assert.match(collectionSource, /dependency_artifacts/);
  assert.match(electronClientSource, /simulation\.plmxml\.model_tree\.read\'?\s*\?\s*60000/);
  assert.match(source, /simulation\.environment\.plmxml\.insert/);
  assert.match(source, /simulation\.environment\.bop_projection\.preview/);
  assert.match(source, /simulation\.environment\.bop_projection\.apply/);
  assert.match(source, /model_reference_count/);
  assert.match(source, /resource_reference_count/);
  assert.match(source, /confirmation \? async \(\) => true : undefined/, 'confirmed modal actions must pass the exact UI confirmation into the governance gateway');
  assert.match(source, /btnEnvironmentSync/);
  assert.match(source, /simulation\.environment\.runtime_package\.open\.request/);
  assert.match(source, /setRuntimeProgress\('reading_back'/);
  assert.match(source, /setRuntimeProgress\('read_back'/);
  assert.doesNotMatch(source, /setEnvironmentState\('runtime_verified'/);
  assert.match(source, /snapshotToVisTree\(treeResult\)/);
});
