'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const lineage = fs.readFileSync(path.join(__dirname, 'lineage.js'), 'utf8');
const panelSource = fs.readFileSync(path.join(__dirname, 'assoc_panel.js'), 'utf8');
const artifact = { artifact_id: 'artifact_' + '1'.repeat(32), media_type: 'image/png', sha256: 'a'.repeat(64), byte_size: 2048, version: 1 };

function context() {
  const refreshes = [];
  const rows = new Map([
    ['process', { gid: 'process', node_type: 'process', version_gid: 'version', process_flow_pic: [] }],
    ['other', { gid: 'other', node_type: 'process', version_gid: 'version', process_flow_pic: ['unchanged'] }],
  ]);
  const business = {
    artifactPath: item => 'artifact:' + encodeURIComponent(JSON.stringify(item.artifact_ref)) + '/' + item.name,
    parseArtifactPath: value => ({ artifact_ref: JSON.parse(decodeURIComponent(value.slice(9, value.indexOf('/')))) }),
  };
  const runtime = vm.createContext({
    console, Map, Set, _versionGid: 'version', _rowByGid: rows, _viewMode: 'layout',
    _layoutMode: { refreshProcessCard: gid => refreshes.push(gid) },
    window: { AI00Business: business, top: { electronAPI: { artifactContentUrl: ref => 'preview:' + ref.artifact_id } } },
  });
  vm.runInContext(lineage.slice(lineage.indexOf('async function _applyCapturePicture('), lineage.indexOf('const _pictureObserverData')), runtime);
  vm.runInContext(lineage.slice(lineage.indexOf('async function _resolvePicItem('), lineage.indexOf('async function _pictureReferenceHash(')), runtime);
  return { runtime, rows, refreshes };
}

test('stored wrappers and canonical artifact paths resolve through the authenticated bridge', async () => {
  const { runtime } = context();
  const picture = runtime._normalizePicItems([{ artifact_ref: artifact }])[0];
  assert.ok(picture.url.startsWith('artifact:'));
  const fromWrapper = await runtime._resolvePictureDisplay({ artifact_ref: artifact });
  assert.equal(fromWrapper, 'preview:' + artifact.artifact_id);
  assert.equal(await runtime._resolvePictureDisplay(picture), fromWrapper);
  const second = { ...artifact, artifact_id: 'artifact_' + '2'.repeat(32) };
  assert.notEqual(runtime._pictureCacheKey({ artifact_ref: artifact }), runtime._pictureCacheKey({ artifact_ref: second }));
});

test('completion refreshes only the exact process card without a BOP reload', async () => {
  const { runtime, rows, refreshes } = context();
  await runtime._applyCapturePicture({ bop_entry_gid: 'process', bop_version_gid: 'version' }, artifact, 'version');
  assert.equal(rows.get('process').process_flow_pic.length, 1);
  assert.deepEqual(rows.get('other').process_flow_pic, ['unchanged']);
  assert.deepEqual(refreshes, ['process']);
  await runtime._applyCapturePicture({ bop_entry_gid: 'other', bop_version_gid: 'different' }, artifact, 'version');
  assert.deepEqual(rows.get('other').process_flow_pic, ['unchanged']);
});

test('operation fallback updates its owning process card and rejects late replies after version switch', async () => {
  const { runtime, rows, refreshes } = context();
  rows.set('operation', { gid: 'operation', node_type: 'operation', parent_gid: 'process' });
  await runtime._applyCapturePicture({ bop_entry_gid: 'operation' }, artifact, 'version');
  assert.deepEqual(refreshes, ['operation', 'process']);
  let resolve;
  runtime._resolvePictureDisplay = () => new Promise(done => { resolve = done; });
  const pending = runtime._applyCapturePicture({ bop_entry_gid: 'other' }, artifact, 'version');
  runtime._versionGid = 'new-version';
  resolve('preview');
  await pending;
  assert.deepEqual(rows.get('other').process_flow_pic, ['unchanged']);
});

test('association thumbnails read process pictures and resolve artifact URLs rather than using them as image src', async () => {
  const { runtime } = context();
  vm.runInContext(panelSource + '\nglobalThis.Panel = AssocPanel;', runtime);
  const picture = runtime._normalizePicItems([{ artifact_ref: artifact }])[0];
  runtime._assocInvoke = async () => ({ data: [{ bop_entry_gid: 'process', process_flow_pic: [picture] }] });
  const panel = Object.create(runtime.Panel.prototype);
  Object.assign(panel, { _versionGid: 'version', _selectedLineGids: new Set(['line']), _picMap: new Map() });
  let renders = 0;
  panel._reRenderBody = () => renders++;
  await panel._refreshPicMap();
  assert.equal(panel._picMap.get('process'), 'preview:' + artifact.artifact_id);
  runtime._assocInvoke = async () => ({ data: [] });
  await panel._refreshPicMap();
  assert.equal(panel._picMap.size, 0);
  assert.equal(renders, 2);
});
