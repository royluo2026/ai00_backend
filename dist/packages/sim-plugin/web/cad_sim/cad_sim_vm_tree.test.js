const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, 'cad_sim.js'), 'utf8');
const {
  projectNumberFromPlmxmlName,
  snapshotToVisTree,
  teamcenterOccurrencePathForNode,
} = require('./vm_snapshot_tree.js');

test('VM snapshot preserves live visibility and treats missing observation as unknown', () => {
  const tree = snapshotToVisTree({ nodes: [
    { node_key: 'root', name: 'Root', visible: true },
    { node_key: 'hidden', parent_node_key: 'root', visible: false },
    { node_key: 'unknown', parent_node_key: 'root' },
  ] });
  const root = tree.children[0].children[0];
  assert.equal(root.visible, true);
  assert.equal(root.children[0].visible, false);
  assert.equal(root.children[1].visible, null);
});

test('PLMXML source metadata extracts the project number without the view suffix', () => {
  assert.equal(
    projectNumberFromPlmxmlName('W10-ENG00001-00-1-工程分支(Top Engineering) (视图).plmxml'),
    'W10',
  );
  assert.equal(projectNumberFromPlmxmlName('工程分支.plmxml'), '未识别');
});

test('cad_sim entry script remains syntactically valid after feature merges', () => {
  assert.doesNotThrow(() => new vm.Script(source, { filename: 'cad_sim.js' }));
});

test('VM tree uses the lightweight governed Connector tree workflow instead of loopback bridge', () => {
  const loader = source.slice(source.indexOf('async function _loadVisTree'), source.indexOf('/** 构建 AI00 合成分区节点'));
  assert.doesNotMatch(loader, /_bridge\('vis_mockup',\s*'get_vis_tree'/);
  assert.match(loader, /simulation\.vismockup\.tree\.read\.request/);
  assert.match(loader, /_requestVisMockupCommand/);
  assert.match(source, /simulation\.vismockup\.command\.get/);
  assert.doesNotMatch(loader, /simulation\.document_snapshot\.request/);
});

test('VM tree always synchronizes the complete bounded tree and depth only changes display', () => {
  const binding = source.slice(source.indexOf('function _bindVisPanel'), source.indexOf('async function _loadVisTree'));
  const loader = source.slice(source.indexOf('async function _loadVisTree'), source.indexOf('/** 构建 AI00 合成分区节点'));

  assert.match(source, /const VM_FULL_SYNC_DEPTH = 8/);
  assert.match(binding, /vmTreeDepth[^\n]+_applyVisTreeOpenDepth\(\)/);
  assert.doesNotMatch(binding, /vmTreeDepth[^\n]+_loadVisTree/);
  assert.match(loader, /max_depth: VM_FULL_SYNC_DEPTH/);
  assert.match(loader, /force_refresh: Boolean\(force\)/);
  assert.match(loader, /cacheState: treeResult\.cache_state/);
  assert.match(loader, /cacheState === 'verifying'/);
  assert.doesNotMatch(loader, /await _loadVisTree\(true\)/);
  assert.match(loader, /点击刷新校验当前模型/);
  assert.doesNotMatch(loader, /Number\(\$\('vmTreeDepth'\)/);
});

test('manual PLMXML button loads the tree without requiring a live VisMockup connection', () => {
  const importer = source.slice(source.indexOf('async function _openPlmxmlTree'), source.indexOf('async function _loadVisTree'));
  assert.match(importer, /parsePlmxmlTree/);
  assert.match(importer, /_renderVisTreeSnapshot/);
  assert.doesNotMatch(importer, /_vmConnected/);
  assert.doesNotMatch(importer, /_requestVisMockupCommand/);
  assert.match(source, /btnOpenPlmxmlTree/);
  assert.match(importer, /plmxmlSourceBanner/);
  assert.match(importer, /file\.lastModified/);
});

test('flat bounded snapshot becomes the existing ordered VM tree model', () => {
  const tree = snapshotToVisTree({
    root_node_key: 'root',
    nodes: [
      { node_key: 'b', parent_key: 'root', child_order: 1, printable_name: '后悬架', occurrence_id: 'B' },
      { node_key: 'root', parent_key: null, child_order: 0, printable_name: '整车', occurrence_id: '' },
      { node_key: 'a', parent_key: 'root', child_order: 0, printable_name: '前悬架', occurrence_id: 'A' },
    ],
  });

  assert.equal(tree.name, '__virtual_root__');
  assert.deepEqual(tree.children[0].children.map(node => node.name), ['整车']);
  assert.deepEqual(tree.children[0].children[0].children.map(node => node.name), ['前悬架', '后悬架']);
  assert.equal(tree.children[0].children[0].children[0].catia_name, 'A');
});

test('lightweight Connector tree projection becomes the same VM tree model', () => {
  const tree = snapshotToVisTree({
    nodes: [
      { node_key: 'root', parent_node_key: null, name: '整车', catia_occurrence_name: '', has_more: false },
      { node_key: 'a', parent_node_key: 'root', name: '前悬架', catia_occurrence_name: 'A', has_more: true },
    ],
  });

  assert.equal(tree.children[0].children[0].name, '整车');
  assert.equal(tree.children[0].children[0].children[0].catia_name, 'A');
  assert.equal(tree.children[0].children[0].children[0].has_more, true);
});

test('VisMockup runtime key recovers the full Teamcenter occurrence path', () => {
  const occurrencePath = [
    { occurrence_uid: 'jZsVJyzkqHnArA', item_revision_uid: 'zBkVJyzkqHnArA' },
    { occurrence_uid: 'zFiVJyzkqHnArA', item_revision_uid: 'QSop1jb8qHnArA' },
    { occurrence_uid: 'h2rdEemIqHnArA', item_revision_uid: 'W5mJMeu7qHnArA' },
  ];

  assert.deepEqual(
    teamcenterOccurrencePathForNode([{
      node_key: 'tc:sha256:full-document-node-key',
      control_key: 'tc:h2rdEemIqHnArA',
      occurrence_path: occurrencePath,
    }], 'tc:h2rdEemIqHnArA'),
    occurrencePath,
  );
});
