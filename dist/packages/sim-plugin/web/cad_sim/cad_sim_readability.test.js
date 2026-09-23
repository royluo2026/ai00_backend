const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const { JSDOM } = require('jsdom');

const source = fs.readFileSync(path.join(__dirname, 'cad_sim.js'), 'utf8');
const css = fs.readFileSync(path.join(__dirname, 'cad_sim.css'), 'utf8');
const html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');

function page(markup) {
  const dom = new JSDOM(`<!doctype html><body>${markup}</body>`, { runScripts: 'outside-only', url: 'http://127.0.0.1/' });
  const addEventListener = dom.window.document.addEventListener.bind(dom.window.document);
  dom.window.document.addEventListener = (type, ...args) => {
    if (type !== 'DOMContentLoaded') addEventListener(type, ...args);
  };
  vm.runInContext(source, dom.getInternalVMContext());
  return dom;
}

test('hierarchy actions move to the right-click menu and full names remain available on hover', () => {
  const dom = page('<div id="alternateHierarchyList"></div><div id="modelDocumentList"></div>');
  vm.runInContext(`_modelDocumentCollection = { state: { selectedHierarchyGid: null } };
    _renderAlternateHierarchies([{ hierarchy_gid: '10', name: '前悬分装线很长的备选层次结构名称', placement_count: 73 }]);
    _renderModelDocuments([{ document_gid: '20', display_name: 'W10-2026-完整模型文件名称.plmxml', media_type: 'application/plmxml+xml', role: 'primary' }]);`, dom.getInternalVMContext());
  const row = dom.window.document.querySelector('.cs-alternate-hierarchy-row');
  assert.equal(row.querySelector('.cs-alternate-hierarchy-name').title, '前悬分装线很长的备选层次结构名称');
  assert.equal(dom.window.document.querySelector('.cs-model-document-name').title, 'W10-2026-完整模型文件名称.plmxml');
  assert.equal(row.querySelectorAll('button[data-hierarchy-action]').length, 0);
  row.dispatchEvent(new dom.window.MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: 20, clientY: 20 }));
  assert.deepEqual([...dom.window.document.querySelectorAll('.cs-alternate-context-menu button')].map(button => button.textContent), ['编辑名称', '删除（归档）']);
  dom.window.close();
});

test('placement removal is available from its own right-click menu', () => {
  const dom = page('');
  vm.runInContext(`window.AI00ModelDocumentCollection = { deriveVisibilityState: () => ({ checked: false, indeterminate: false, disabled: true }) };
    document.body.appendChild(_buildAlternateTreeItem({ kind: 'placement', placement_gid: '30', display_name: '很长的零件名称', children: [] }, { hierarchy_gid: '10' }));`, dom.getInternalVMContext());
  const line = dom.window.document.querySelector('.cs-alternate-tree-line');
  assert.equal(line.querySelector('.cs-alternate-tree-name').title, '很长的零件名称');
  assert.equal(line.querySelector('.cs-alternate-tree-remove'), null);
  line.dispatchEvent(new dom.window.MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: 20, clientY: 20 }));
  assert.equal(dom.window.document.querySelector('.cs-alternate-context-menu button').textContent, '删除放置');
  dom.window.close();
});

test('both pane handles resize horizontally while reserving room for the 3D view', () => {
  assert.match(html, /id="environmentWidthHandle"/);
  assert.match(html, /id="modelWidthHandle"/);
  assert.match(css, /\.cs-model-documents-panel \.cs-model-documents,\.cs-environment-stack \.cs-vis-panel \.cs-alternate-hierarchies\{overflow-x:auto\}/);
  const dom = page('<div class="cs-sim-shell"><div id="simulationEnvironmentPanel"><div id="visPanel"></div></div><div id="environmentWidthHandle"></div><div id="modelDocumentsPanel"></div><div id="modelWidthHandle"></div><div id="simulationFuturePanel"><div id="nativeViewportSlot" class="hidden"></div></div></div>');
  const shell = dom.window.document.querySelector('.cs-sim-shell');
  const environment = dom.window.document.getElementById('simulationEnvironmentPanel');
  const model = dom.window.document.getElementById('modelDocumentsPanel');
  const viewport = dom.window.document.getElementById('simulationFuturePanel');
  environment.getBoundingClientRect = () => ({ width: Number.parseInt(shell.style.getPropertyValue('--bop-panel-w')) || 248 });
  model.getBoundingClientRect = () => ({ width: Number.parseInt(shell.style.getPropertyValue('--model-panel-w')) || 248 });
  viewport.getBoundingClientRect = () => ({ width: 700 - (environment.getBoundingClientRect().width - 248) - (model.getBoundingClientRect().width - 248) });
  vm.runInContext('_bindPanelWidthHandles()', dom.getInternalVMContext());
  const handle = dom.window.document.getElementById('environmentWidthHandle');
  handle.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
  assert.equal(shell.style.getPropertyValue('--bop-panel-w'), '272px');
  handle.dispatchEvent(new dom.window.MouseEvent('pointerdown', { button: 0, clientX: 100, bubbles: true }));
  handle.dispatchEvent(new dom.window.MouseEvent('pointermove', { clientX: 160, bubbles: true }));
  handle.dispatchEvent(new dom.window.MouseEvent('pointerup', { bubbles: true }));
  assert.equal(shell.style.getPropertyValue('--bop-panel-w'), '332px');
  assert.equal(handle.getAttribute('aria-valuenow'), '332');
  const modelHandle = dom.window.document.getElementById('modelWidthHandle');
  modelHandle.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
  assert.equal(shell.style.getPropertyValue('--model-panel-w'), '272px');
  handle.dispatchEvent(new dom.window.MouseEvent('pointerdown', { button: 0, clientX: 100, bubbles: true }));
  handle.dispatchEvent(new dom.window.MouseEvent('pointermove', { clientX: 900, bubbles: true }));
  handle.dispatchEvent(new dom.window.MouseEvent('pointerup', { bubbles: true }));
  assert.equal(shell.style.getPropertyValue('--bop-panel-w'), '600px');
  assert.ok(viewport.getBoundingClientRect().width >= 320);
  dom.window.close();
});
