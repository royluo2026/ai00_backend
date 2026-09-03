'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');

const read = name => fs.readFileSync(path.join(__dirname, name), 'utf8');
const lineage = read('lineage.js');
const detail = read('layout_detail_panel.js');
const staging = read('staging_panel.js');
const index = read('index.html');
const detailCss = read('layout_detail_panel.css');
const layoutMode = read('layout_mode.js');
const scriptVersion = name => index.match(new RegExp(`<script src="${name}\\.js\\?v=([^"]+)"`))?.[1];
const constructorSetup = detail.slice(detail.indexOf('constructor('), detail.indexOf('this._bindResizeHandle();'));
const activeHandleSetup = detail.slice(detail.lastIndexOf('_bindHandleBar()'), detail.indexOf('_defaultTreeSettings()', detail.lastIndexOf('_bindHandleBar()')));
const activeKnowledgeRenderer = detail.slice(detail.lastIndexOf('async _renderKnowledge('));
const capabilityInvoker = lineage.slice(
  lineage.indexOf('async function _invokeCapability('),
  lineage.indexOf('const _progressiveLoader'),
);
const detailCapabilityInvoker = detail.slice(
  detail.indexOf('this._invokeCapability = async'),
  detail.indexOf('this._ontologySchemaCache'),
);
const layoutDestroy = layoutMode.slice(
  layoutMode.indexOf('destroyHeavyState('),
  layoutMode.indexOf('\n  /**', layoutMode.indexOf('destroyHeavyState(') + 1),
);
const lineGrantRefresh = lineage.slice(
  lineage.indexOf('_loadLineGrants(loaded.version?.project_gid || \'\').then(() => {'),
  lineage.indexOf('\n    _loadCloudConfig()', lineage.indexOf('_loadLineGrants(loaded.version?.project_gid || \'\').then(() => {')),
);
const progressiveLoad = lineage.slice(
  lineage.indexOf('async function _load()'),
  lineage.indexOf('function _capabilityLoadErrorMessage('),
);
const layoutRender = layoutMode.slice(
  layoutMode.indexOf('render(data)'),
  layoutMode.indexOf('\n  /**', layoutMode.indexOf('render(data)') + 1),
);
const virtualRender = layoutMode.slice(
  layoutMode.indexOf('_checkVirtualRender()'),
  layoutMode.indexOf('\n  /**', layoutMode.indexOf('_checkVirtualRender()') + 1),
);
const localMove = lineage.slice(lineage.indexOf('function _localMoveApply('), lineage.indexOf('// ── reload helper'));
const createdInsertion = lineage.slice(lineage.indexOf('function _insertCreatedEntry('), lineage.indexOf('function _createdEntryFromResult('));
const reloadHelper = lineage.slice(lineage.indexOf('async function _reload()'), lineage.indexOf('// ── 事件绑定'));
const dialogCreate = lineage.slice(lineage.indexOf('async function _createNodeFromDialog('), lineage.indexOf('async function _handleFBtnAction('));
const layoutSiblingCreate = layoutMode.slice(layoutMode.indexOf('_makeAddSiblingBtn('), layoutMode.indexOf('// ══════════════════════════════════════════════════════════════════\n  // 工序卡片复制粘贴'));
const layoutReparent = layoutMode.slice(layoutMode.indexOf('async _commitParentChange('), layoutMode.indexOf('  _saveLinePositions('));

assert.match(lineage, /profile\?\.profile\?\.actor_gid\s*\|\|\s*profile\?\.actor_gid/,
  'identity outcome must read the governed nested profile while tolerating the legacy projection');

for (const source of [detail, staging]) {
  assert.ok(!source.includes('/api/craft/resource-requirements'), 'resource standards must use their atomic capability');
  assert.ok(!source.includes('/api/craft/tc-resource-staging'), 'TC resource review must use its atomic capability');
}

for (const id of ['llDpTree', 'llDpProps', 'llDpRels']) {
  assert.ok(index.includes(`id="${id}"`), `${id} must remain a first-class detail column`);
}
assert.match(index, /id="llDpTree"[\s\S]*?id="llDpVDivider"[\s\S]*?id="llDpInspector"[\s\S]*?id="llDpProps"[\s\S]*?id="llDpPropsRelsDivider"[\s\S]*?id="llDpRels"/,
  'the single sidebar must stack tree, properties, and relations vertically');
assert.ok(!index.includes('ll-dp-tab'), 'properties and relations must not use tabs');
assert.deepStrictEqual(
  ['lineage', 'layout_mode', 'layout_detail_panel'].map(scriptVersion),
  Array(3).fill(scriptVersion('lineage')),
  'the coupled lineage scripts must share one cache version so a refresh cannot mix old and new viewport logic',
);
assert.match(detailCss, /\.ll-dp-columns\s*\{[^}]*flex-direction:\s*column/,
  'the detail sidebar must use one vertical column');
assert.match(detailCss, /\.ll-dp-inspector\s*>\s*\.ll-dp-col\s*\{[^}]*display:\s*flex/,
  'property and relation sections must both remain visible');
assert.ok(detail.includes('id="llPropsLocateBtn"'), 'the property panel must restore locate-in-canvas');
assert.ok(index.includes('搜索节点（名称/零件号/VPPS…）'), 'tree search must describe the supported reference fields');
assert.match(detail, /this\._renderRels\(gid,\s*this\._relsBody\)/,
  'relations must render in the dedicated relation column');
assert.match(detail, /openEmpty\(\)[\s\S]*?rowByGid\?\.size[\s\S]*?_renderTree\(null\)/,
  'opening details without a selection must still render the loaded BOP tree');
assert.ok(activeHandleSetup.includes('this.openEmpty()'),
  'the effective toolbar detail toggle must render the loaded BOP tree without a selection');
assert.match(detail, /toggle\(\)[\s\S]*?else\s+this\.openEmpty\(\)/,
  'the public detail toggle must render the loaded BOP tree without a selection');
assert.ok(!constructorSetup.includes("this._toolbarToggle.addEventListener"),
  'the toolbar toggle must be bound exactly once by _bindHandleBar');
assert.match(activeKnowledgeRenderer, /async _renderKnowledge\(gid\)\s*\{\s*if \(!this\._knowBody\) return;/,
  'removed optional detail columns must be safe to render');
assert.match(lineage, /_ensureScopeLoaded\(row\)/,
  'activating a line from the detail tree must trigger its bounded work-package load');
assert.match(lineage, /ensureScopeLoaded:\s*_ensureScopeLoaded/,
  'layout mode must receive the governed bounded scope loader');
assert.match(virtualRender, /_requestVisibleLineData\(line\)/,
  'zooming or panning a line into view must request its bounded work-package data');
assert.ok(
  virtualRender.indexOf('_requestVisibleLineData(line)') < virtualRender.indexOf('_renderedLineGids.has(line.gid)'),
  'already-rendered empty line shells must still be eligible for progressive data loading',
);
assert.match(capabilityInvoker, /await _lineageVersionCf\(/,
  'all lineage capability calls must complete the governed confirmation handshake');
assert.match(capabilityInvoker, /_isLayoutMutationCapability\(id\)[\s\S]*?_preserveLayoutViewport\(\)/,
  'every successful main-view node mutation must preserve the current layout viewport');
assert.match(detailCapabilityInvoker, /_isLayoutMutationCapability\(id\)[\s\S]*?this\._preserveLayoutView\(\)/,
  'every successful detail-panel node mutation must preserve the current layout viewport');
assert.match(lineage, /const preserveLayoutView\s*=\s*_viewMode\s*===\s*'layout'\s*&&\s*_layoutMode\?\._preserveView/,
  'a refresh must capture a requested layout viewport preservation before clearing heavy state');
assert.match(lineage, /destroyHeavyState\(\{\s*preserveView:\s*preserveLayoutView\s*}\)/,
  'a refresh must carry the viewport preservation request through heavy-state cleanup');
assert.match(layoutDestroy, /destroyHeavyState\(\{\s*preserveView\s*=\s*false\s*}\s*=\s*{}\)/,
  'heavy-state cleanup must accept the explicit viewport preservation request');
assert.match(layoutDestroy, /this\._preserveView\s*=\s*preserveView/,
  'heavy-state cleanup must retain the requested viewport preservation for the next render');
assert.match(lineGrantRefresh, /if \(_viewMode === 'layout' && _layoutMode\) _layoutMode\._preserveView = true;\s*\n\s*if \(_viewMode === 'layout'\) _render\(\);/,
  'the asynchronous line-permission refresh must preserve the layout viewport before its second render');
assert.match(progressiveLoad, /if \(!preserveLayoutView\) _restoreView\(\);/,
  'a mutation refresh must not overwrite the live viewport with a stale session snapshot');
assert.match(layoutMode, /this\._hasRendered\s*=\s*false;/,
  'layout mode must distinguish its first render from same-version data redraws');
assert.match(layoutRender, /if \(this\._hasRendered \|\| this\._preserveView\)/,
  'same-version data redraws must keep the current viewport without caller-specific flags');
assert.match(layoutRender, /this\._hasRendered\s*=\s*true;/,
  'layout mode must mark the viewport initialized after its first render');
assert.match(reloadHelper, /async function _reload\(\)\s*\{\s*if \(_viewMode === 'layout' && _layoutMode\)\s*\{\s*_layoutMode\._preserveView = true;/,
  'the shared data refresh boundary must preserve the current layout viewport for every caller');
assert.match(layoutDestroy, /this\._hasRendered\s*=\s*preserveView;/,
  'switching BOP must reset first-render fitting while mutation refreshes retain initialization');
assert.match(localMove, /if \(_viewMode === 'layout' && _layoutMode\) _layoutMode\._preserveView = true;\s*\n\s*_render\(\);/,
  'a local drag move must preserve the layout viewport before redrawing the changed projection');
assert.match(lineage, /function _insertCreatedEntry\(rawRow\)/,
  'the consumer must be able to merge a governed create result into the current projection');
assert.match(createdInsertion, /_layoutMode\._refreshAfterPositionChange\(new Set\(\[lineGid\]\)\)/,
  'a created child must immediately redraw its loaded line instead of waiting for a page reload');
assert.match(lineage, /function _createdEntryFromResult\(result\)/,
  'the consumer must adapt the governed create envelope before merging it into the projection');
assert.match(dialogCreate, /const createdEntry = _createdEntryFromResult\(resp\);[\s\S]*?if \(!_insertCreatedEntry\(createdEntry\)\) await _reload\(\);/,
  'dialog creation must use the returned governed entry before falling back to a full reload');
assert.match(layoutSiblingCreate, /const created = await _layoutInvokeCapability\('craft\.bop\.entry\.bulk\.change\.apply'/,
  'layout station creation must retain the governed create result');
assert.match(layoutSiblingCreate, /if \(!this\._data\?\.insertCreatedEntry\?\.\(_createdEntryFromResult\(created\)\)\) await this\._data\?\.reloadData\?\.\(\);/,
  'layout station creation must merge its returned entry before falling back to a full reload');
assert.match(layoutReparent, /_moveRowLocally\(drag\.row, body\.parent_gid, body\.sort_order\)/,
  'moving a process card must update only the affected lines in the live projection');
assert.match(layoutMode, /_restackLineBoxes\(lines\s*=\s*this\._world\.querySelectorAll\('\.ll-line-box'\)\)/,
  'the incremental move renderer must provide the line restacking helper it invokes');
assert.match(layoutReparent, /_queuePositionSave\(drag\.row, body, previous/,
  'moving a process card must persist its optimistic local move through the serial save queue');
assert.match(layoutReparent, /_layoutInvokeCapability\('craft\.bop\.entry\.change\.apply'/,
  'the position save queue must still persist through the governed atomic capability');
assert.ok(!layoutReparent.includes('reloadData'),
  'moving a process card must not rebuild the full BOP projection and reset the viewport');

console.log('lineage reference parity: OK');
