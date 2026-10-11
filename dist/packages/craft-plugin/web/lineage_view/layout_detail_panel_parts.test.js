'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { test } = require('node:test');
const { JSDOM } = require('jsdom');

const source = fs.readFileSync(process.env.AI00_PARTS_PANEL_SOURCE || __dirname + '/layout_detail_panel.js', 'utf8');
const sandbox = { console, requestAnimationFrame: () => 0 };
vm.runInNewContext(source + '\nglobalThis.Panel = LayoutDetailPanel;', sandbox);
const Panel = sandbox.Panel;

function createPanel(typeFilter = null) {
  const dom = new JSDOM('<div id="tree"></div><div id="props"><div id="llPropsStatsArea"></div></div>');
  const rows = [
    { gid: 'line', node_type: 'line_process', title: 'Line' },
    { gid: 'station', parent_gid: 'line', node_type: 'station_process', title: 'Station' },
    { gid: 'process', parent_gid: 'station', node_type: 'process', title: 'Process' },
    { gid: 'operation', parent_gid: 'process', node_type: 'operation', title: 'Operation' },
    { gid: 'part', parent_gid: 'operation', node_type: 'part', title: 'Body <assembly>', vpps: '80.01.01.01.01' },
    { gid: 'non-standard', parent_gid: 'part', node_type: 'non_standard_part', title: 'Bracket' },
    { gid: 'standard', parent_gid: 'operation', node_type: 'standard_part', title: 'Bolt' },
    { gid: 'material', parent_gid: 'operation', node_type: 'support_material', title: 'Sealant' },
    { gid: 'deleted', parent_gid: 'operation', node_type: 'part', title: 'Deleted part', is_deleted: true },
  ];
  const data = { rows, rowByGid: new Map(rows.map(row => [row.gid, row])), childMap: new Map(), typeFilter };
  for (const row of rows) {
    const key = row.parent_gid || null;
    if (!data.childMap.has(key)) data.childMap.set(key, []);
    data.childMap.get(key).push(row);
  }
  const panel = Object.create(Panel.prototype);
  sandbox.document = dom.window.document;
  Object.assign(panel, {
    _el: dom.window.document.body,
    _getLineageData: () => data,
    _treeBody: dom.window.document.getElementById('tree'),
    _propsBody: dom.window.document.getElementById('props'),
    _treeExpanded: new Set(rows.map(row => row.gid)),
    _extraVersionData: new Map(),
    _isEditable: () => false,
    _loadEntryDetail: async () => {},
    _loadOntologySchema: async nodeType => ({ properties: [], relations: [
      { name: 'usesPart', link_type_binding: nodeType === 'process' ? 'usesPart' : 'pbom_part', label_zh: '装配零件', range_node_type: 'part', show_in_detail: true },
    ] }),
  });
  return { panel, data, document: dom.window.document };
}

async function selectProps(panel, data, gid) {
  let rendered;
  const renderRels = panel._renderRels.bind(panel);
  panel._renderRels = (...args) => (rendered = renderRels(...args));
  panel._renderProps(gid, data.rowByGid.get(gid));
  await rendered;
}

test('actual properties entry shows BOP descendant parts in relations without PBOM links', async () => {
  const { panel, data, document } = createPanel();
  await selectProps(panel, data, 'process');
  const header = document.querySelector('.ll-rg-hdr[data-key="link:usesPart"]');
  assert.ok(header, 'actual assembly relation must include existing BOP parts');
  assert.equal(header.querySelector('.ll-rg-name').textContent, '装配零件');
  assert.equal(header.querySelector('.ll-rg-cnt').textContent, '4');
  assert.ok(header.querySelector('.ll-rg-add'));
  assert.equal(document.querySelector('.ll-rg-hdr[data-key="bop_parts"]'), null);
  const items = [...document.querySelectorAll('.ll-ri[data-key="link:usesPart"]')];
  assert.ok(items.some(item => item.textContent.includes('80.01.01.01.01 · Body <assembly>')));
  assert.ok(!items.some(item => item.textContent.includes('Deleted part')));
  let opened, activated;
  panel.open = gid => { opened = gid; };
  panel._onNodeActivate = gid => { activated = gid; };
  items.find(item => item.textContent.includes('Body <assembly>')).click();
  assert.equal(opened, 'part');
  assert.equal(activated, 'part');
});

test('assembly relation combines BOP nodes with real links and retains link details', async () => {
  const { panel, data, document } = createPanel();
  data.rowByGid.get('operation').__governed_links = [
    { gid: 'link', link_type: 'pbom_part', entity_gid: 'pbom-clip', entity_title: 'Linked clip' },
  ];
  await selectProps(panel, data, 'operation');
  assert.equal(document.querySelector('.ll-rg-hdr[data-key="link:pbom_part"] .ll-rg-cnt')?.textContent, '5');
  const linked = [...document.querySelectorAll('.ll-ri[data-key="link:pbom_part"]')].find(item => item.textContent.includes('Linked clip'));
  assert.ok(linked.textContent.includes('Linked clip'));
  let selected;
  panel._openViewDetail = item => { selected = item; };
  linked.click();
  assert.equal(selected.link.gid, 'link');
});

test('manually attached assembly parts show part number and name instead of GID', async () => {
  const { panel, data, document } = createPanel();
  data.childMap.clear();
  data.rowByGid.get('operation').__governed_links = [
    { link_gid: 'l1', link_type: 'pbom_part', entity_gid: '230863332461154422', entity_part_no: 'P-100', entity_title: '安装<支架>' },
    { link_gid: 'l2', link_type: 'usesPart', entity_gid: 'p2', entity_part_no: 'P-200', entity_title: '螺栓' },
    { link_gid: 'l3', link_type: 'pbom_part', entity_gid: 'p3', entity_title: '只有名称' },
  ];
  await selectProps(panel, data, 'operation');
  const titles = [...document.querySelectorAll('.ll-ri-title')].map(el => el.textContent);
  assert.deepEqual(titles, ['P-100 · 安装<支架>', 'P-200 · 螺栓', '只有名称']);
  assert.equal(document.querySelector('.ll-ri-title 支架'), null);
});

for (const replaceDrawerDuringSave of [false, true]) test(`confirming an assembly link reads persisted detail without reloading the canvas (replace drawer: ${replaceDrawerDuringSave})`, async () => {
  const { panel, data, document } = createPanel();
  data.versionGid = 'version';
  data.childMap.clear();
  const row = data.rowByGid.get('operation');
  panel._currentGid = row.gid;
  panel._currentRow = row;
  panel._detailGeneration = 0;
  panel._detDrawerBody = document.createElement('div');
  document.body.append(panel._detDrawerBody);
  panel._openDetDrawer = () => {};
  let closes = 0;
  panel._closeDetDrawer = () => { closes++; };
  const calls = [];
  let saved = false;
  let saveComplete;
  const pendingSave = new Promise(resolve => { saveComplete = resolve; });
  panel._invokeCapability = async (id, payload) => {
    calls.push(id);
    if (payload.operation === 'pbom_snapshots') return { data: [{ gid: 'snapshot' }] };
    if (payload.operation === 'pbom_search') return { data: [{ gid: 'pbom', part_no: 'P-100', name: '安装支架' }] };
    assert.equal(payload.operation, 'attach');
    if (replaceDrawerDuringSave) await pendingSave;
    saved = true;
    return { data: { gid: 'link' } };
  };
  let reloads = 0, reads = 0;
  panel._reloadData = async () => { reloads++; };
  panel.refresh = () => {};
  panel._loadEntryDetail = async gid => {
    assert.equal(gid, 'operation');
    assert.equal(saved, true);
    reads++;
    return { entry: { ...row }, links: [{ link_gid: 'link', link_type: 'pbom_part', entity_gid: 'pbom', entity_part_no: 'P-100', entity_title: '安装支架' }] };
  };
  panel._renderAll = () => {};
  let finish;
  const done = new Promise(resolve => { finish = resolve; });
  panel._toast = message => finish(message);
  await panel._openAddDetail('pbom', row.gid, 'pbom_part', '装配零件');
  panel._detDrawerBody.querySelector('.ll-det-sr-item').click();
  panel._detDrawerBody.querySelector('#llAddConfirm').click();
  if (replaceDrawerDuringSave) {
    panel._detDrawerBody.innerHTML = '<button id="llAddConfirm">new drawer</button>';
    saveComplete();
  }
  assert.equal(await done, '已关联 PBOM 零件');
  assert.equal(reloads, 0);
  assert.equal(reads, 1);
  assert.equal(closes, replaceDrawerDuringSave ? 0 : 1);
  assert.equal(row.__governed_links[0].entity_part_no, 'P-100');
  await selectProps(panel, data, row.gid);
  assert.equal(document.querySelector('.ll-ri-title').textContent, 'P-100 · 安装支架');
});

test('property and relation schema requests share one flight and retry failures', async () => {
  const dom = new JSDOM('<div></div>', { url: 'https://example.test' });
  sandbox.window = dom.window;
  sandbox.document = dom.window.document;
  sandbox.localStorage = dom.window.localStorage;
  const panel = new Panel({ containerEl: dom.window.document.body });
  const calls = [];
  let release;
  const pending = new Promise(resolve => { release = resolve; });
  panel._invokeCapability = async id => {
    calls.push(id);
    if (id === 'ontology.concept.resolve') {
      await pending;
      return { concept: { stable_gid: 'concept' }, release_gid: 'release' };
    }
    return { concept: { properties: [], relations: [] } };
  };
  const first = panel._loadOntologySchema('operation');
  const second = panel._loadOntologySchema('operation');
  release();
  assert.equal(await first, await second);
  assert.deepEqual(calls, ['ontology.concept.resolve', 'ontology.concept.get']);
  panel._ontologySchemaCache.clear();
  panel._invokeCapability = async () => { throw new Error('unavailable'); };
  await assert.rejects(panel._loadOntologySchema('operation'), /unavailable/);
  panel._invokeCapability = async () => ({ concept: null });
  assert.equal((await panel._loadOntologySchema('operation')).relations.length, 0);
});

test('a completed link on a previous selection leaves the current detail request and drawer intact', async () => {
  const { panel } = createPanel();
  panel._currentGid = 'process';
  panel._detailGeneration = 12;
  let closes = 0, reads = 0;
  panel._closeDetDrawer = () => { closes++; };
  panel._loadEntryDetail = async () => { reads++; return {}; };
  await panel._refreshLinkedEntry('operation');
  assert.equal(panel._detailGeneration, 12);
  assert.equal(closes, 0);
  assert.equal(reads, 0);
});

test('post-save detail refresh preserves a newer drawer opened on the same node', async () => {
  const { panel, document } = createPanel();
  panel._currentGid = 'operation';
  panel._detailGeneration = 0;
  panel._detDrawerBody = document.createElement('div');
  panel._detDrawerBody.innerHTML = '<button id="llAddConfirm">original</button>';
  panel._renderTree = () => {};
  panel._renderProps = () => {};
  let closes = 0, resolve;
  panel._closeDetDrawer = () => { closes++; };
  panel._loadEntryDetail = () => new Promise(done => { resolve = done; });
  const refresh = panel._refreshLinkedEntry('operation');
  panel._detDrawerBody.innerHTML = '<button id="llAddConfirm">new</button>';
  resolve({ links: [] });
  await refresh;
  assert.equal(closes, 0);
});

test('relation part traversal omits deleted subtrees and does not duplicate repeated nodes', async () => {
  const { panel, data, document } = createPanel();
  data.rowByGid.get('part').is_deleted = true;
  data.childMap.get('operation').push(data.rowByGid.get('standard'));
  await selectProps(panel, data, 'operation');
  assert.equal(document.querySelector('.ll-rg-hdr[data-key="link:pbom_part"] .ll-rg-cnt')?.textContent, '2');
  assert.ok(!document.querySelector('#llPropsRelsArea').textContent.includes('Bracket'));
});

test('assembly relation recognizes both usesPart and pbom_part link storage aliases', async () => {
  const { panel, data, document } = createPanel();
  data.childMap.clear();
  data.rowByGid.get('process').__governed_links = [
    { gid: 'pbom-link', link_type: 'pbom_part', entity_gid: 'clip', entity_title: 'PBOM clip' },
    { gid: 'uses-link', link_type: 'usesPart', entity_gid: 'bolt', entity_title: 'Uses bolt' },
  ];
  await selectProps(panel, data, 'process');
  assert.equal(document.querySelector('.ll-rg-hdr[data-key="link:usesPart"] .ll-rg-cnt')?.textContent, '2');
  assert.ok(document.querySelector('#llPropsRelsArea').textContent.includes('PBOM clip'));
  assert.ok(document.querySelector('#llPropsRelsArea').textContent.includes('Uses bolt'));
});

test('hidden assembly relation remains hidden for BOP nodes and real links', async () => {
  const { panel, data, document } = createPanel();
  panel._loadOntologySchema = async () => ({ properties: [], relations: [
    { name: 'usesPart', link_type_binding: 'pbom_part', show_in_detail: false },
  ] });
  await selectProps(panel, data, 'process');
  assert.equal(document.querySelector('.ll-rg-hdr[data-key="link:pbom_part"]'), null);
  assert.equal(document.querySelector('.ll-rg-hdr[data-key="bop_parts"]'), null);
});

test('TC assembly includes support materials and uses the source part number', async () => {
  const { panel, data, document } = createPanel();
  data.childMap.clear();
  const material = data.rowByGid.get('material');
  material.meta = { tc_key: 'GLUE-100' };
  data.childMap.set('operation', [material]);
  await selectProps(panel, data, 'operation');
  assert.equal(document.querySelector('.ll-rg-hdr[data-key="link:pbom_part"] .ll-rg-cnt').textContent, '1');
  assert.equal(document.querySelector('.ll-ri-title').textContent, 'GLUE-100 · Sealant');
});

test('explicit alias visibility and separately configured relations remain effective', async () => {
  for (const usesVisible of [false, true]) {
    const { panel, data, document } = createPanel();
    data.childMap.clear();
    data.rowByGid.get('process').__governed_links = [
      { link_type: 'pbom_part', entity_gid: 'clip', entity_title: 'PBOM clip' },
      { link_type: 'usesPart', entity_gid: 'bolt', entity_title: 'Uses bolt' },
    ];
    panel._loadOntologySchema = async () => ({ properties: [], relations: [
      { name: 'usesPart', link_type_binding: 'pbom_part', show_in_detail: true },
      { name: 'usesPart', link_type_binding: 'usesPart', show_in_detail: usesVisible },
    ] });
    await selectProps(panel, data, 'process');
    assert.equal(document.querySelector('.ll-rg-hdr[data-key="link:pbom_part"] .ll-rg-cnt').textContent, '1');
    assert.equal(document.querySelectorAll('.ll-ri').length, usesVisible ? 2 : 1);
    assert.equal(document.querySelector('#llPropsRelsArea').textContent.includes('Uses bolt'), usesVisible);
  }
});

test('PBOM-only selection does not create an empty structural parts group', async () => {
  const { panel, data, document } = createPanel();
  data.childMap.clear();
  await selectProps(panel, data, 'operation');
  assert.equal(document.querySelector('.ll-rg-hdr[data-key="bop_parts"]'), null);
  assert.ok(document.querySelector('.ll-rg-hdr[data-key="link:pbom_part"]'));
});

test('all types shows nested parts without PBOM associations', () => {
  const { panel } = createPanel();
  panel._renderTree('operation');
  for (const gid of ['part', 'non-standard', 'standard', 'material']) {
    assert.ok(panel._treeBody.querySelector(`[data-gid="${gid}"]`), `${gid} should be visible`);
  }
  assert.equal(panel._treeBody.querySelector('[data-gid="deleted"]'), null);
  assert.ok(panel._treeBody.textContent.includes('Body <assembly>'));
});

test('explicit type filters remain effective', () => {
  const { panel } = createPanel(['line_process', 'station_process', 'process', 'operation']);
  panel._renderTree('operation');
  assert.ok(panel._treeBody.querySelector('[data-gid="operation"]'));
  assert.equal(panel._treeBody.querySelector('[data-gid="part"]'), null);
});

test('no selected types renders no tree nodes', () => {
  const { panel } = createPanel([]);
  panel._renderTree('operation');
  assert.equal(panel._treeBody.querySelectorAll('.ll-tn').length, 0);
});

test('descendant statistics count part nodes and support navigation', async () => {
  const { panel, document } = createPanel();
  await panel._renderStats('operation');
  assert.equal(document.querySelector('.ll-stats-name')?.textContent, '零件');
  assert.equal(document.querySelector('.ll-stats-cnt')?.textContent, '4');
  assert.ok(document.querySelector('#llPropsStatsArea').textContent.includes('80.01.01.01.01'));
  assert.equal(document.querySelector('[data-nav-gid="deleted"]'), null);
  let activated;
  panel.open = gid => { activated = gid; };
  document.querySelector('[data-nav-gid="part"]').click();
  assert.equal(activated, 'part');
});

test('part statistics combine independent PBOM links without double counting bound nodes', async () => {
  const { panel, data, document } = createPanel();
  data.rowByGid.get('part').__governed_links = [
    { link_type: 'pbom_part', entry_gid: 'part', entity_gid: 'pbom-body', entity_title: 'Duplicate body', is_primary: true },
  ];
  data.rowByGid.get('operation').__governed_links = [
    { link_type: 'pbom_part', entry_gid: 'operation', entity_gid: 'pbom-clip', entity_title: 'Linked clip', entity_vpps: '40.01' },
  ];
  await panel._renderStats('operation');
  const area = document.querySelector('#llPropsStatsArea');
  assert.equal(area.querySelector('.ll-stats-cnt')?.textContent, '5');
  assert.ok(area.textContent.includes('40.01 · Linked clip'));
  assert.ok(!area.textContent.includes('Duplicate body'));
  assert.equal(area.querySelectorAll('.ll-stats-item-nav').length, 4);
});

test('PBOM-only statistics still display linked parts', async () => {
  const { panel, data, document } = createPanel();
  data.childMap.clear();
  data.rowByGid.get('operation').__governed_links = [
    { link_type: 'pbom_part', entry_gid: 'operation', entity_gid: 'pbom-clip', entity_title: 'Linked clip' },
  ];
  await panel._renderStats('operation');
  assert.equal(document.querySelector('.ll-stats-cnt')?.textContent, '1');
  assert.ok(document.querySelector('#llPropsStatsArea').textContent.includes('Linked clip'));
});

test('additional PBOM references on a part remain visible', async () => {
  const { panel, data, document } = createPanel();
  data.rowByGid.get('part').__governed_links = [
    { link_type: 'pbom_part', entry_gid: 'part', entity_gid: 'pbom-body', is_primary: true },
    { link_type: 'pbom_part', entry_gid: 'part', entity_gid: 'pbom-clip', entity_title: 'Additional clip', is_primary: false },
  ];
  await panel._renderStats('operation');
  assert.equal(document.querySelector('.ll-stats-cnt')?.textContent, '5');
  assert.ok(document.querySelector('#llPropsStatsArea').textContent.includes('Additional clip'));
});
