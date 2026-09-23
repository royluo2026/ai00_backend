const assert = require('node:assert/strict');
const test = require('node:test');
const { JSDOM } = require('jsdom');

globalThis.AI00SimulationEnvironmentTree = undefined;
require('./environment_tree.js');

test('line access uses a visible editable/read-only distinction', () => {
  const tree = globalThis.AI00SimulationEnvironmentTree;
  assert.equal(tree.accessClass({ access_mode: 'editable' }), ' editable');
  assert.equal(tree.accessClass({ access_mode: 'read_only' }), ' read-only');
  assert.equal(tree.accessLabel({ access_mode: 'read_only' }), ' 🔒');
  assert.equal(tree.accessLabel({ access_mode: 'editable' }), '');
});

test('current tree title identifies the opened environment kind', () => {
  const tree = globalThis.AI00SimulationEnvironmentTree;
  assert.equal(tree.environmentLabel({ display_label: 'W10' }, 'team'), '项目空间 · W10');
  assert.equal(tree.environmentLabel({ display_label: 'W10' }, 'managed_personal'), '个人项目空间 · W10');
  assert.equal(tree.environmentLabel({ name: '方案评审' }, 'private'), '个人仿真环境 · 方案评审');
  assert.equal(tree.environmentLabel(null, null), '当前仿真环境树');
  assert.equal(tree.currentDocumentLabel({ name: '方案评审' }, 'private'), '当前仿真文档 · 个人仿真环境 · 方案评审');
  assert.equal(tree.currentDocumentLabel(null, null), '当前仿真文档 · 未选择环境');
});

test('open level expands only the requested hierarchy depth', () => {
  const tree = globalThis.AI00SimulationEnvironmentTree;
  const nodes = [
    { node_gid: '1', parent_gid: null },
    { node_gid: '2', parent_gid: '1' },
    { node_gid: '3', parent_gid: '2' },
  ];
  assert.deepEqual([...tree.expandedForLevel(nodes, 1)], []);
  assert.deepEqual([...tree.expandedForLevel(nodes, 2)], ['1']);
  assert.deepEqual([...tree.expandedForLevel(nodes, 3)], ['1', '2']);
});

test('rendered hierarchy is collapsible and exposes connector structure', () => {
  const tree = globalThis.AI00SimulationEnvironmentTree;
  const dom = new JSDOM('<div id="tree"></div>');
  global.document = dom.window.document;
  const container = document.getElementById('tree');
  const nodes = [
    { node_gid: '1', parent_gid: null, name: '线体' },
    { node_gid: '2', parent_gid: '1', name: '工位' },
  ];
  tree.render(container, nodes, null, { expandedNodeGids: new Set() });
  assert.equal(container.querySelectorAll('[data-node-gid]').length, 1);
  assert.equal(container.querySelector('[data-tree-toggle]').textContent, '▸');
  tree.render(container, nodes, null, { expandedNodeGids: new Set(['1']) });
  assert.equal(container.querySelectorAll('[data-node-gid]').length, 2);
  assert.ok(container.querySelector('.cs-environment-tree-children > .cs-environment-tree-branch'));
  delete global.document;
});
