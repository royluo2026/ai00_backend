'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { JSDOM } = require('jsdom');

const lineage = fs.readFileSync(path.join(__dirname, 'lineage.js'), 'utf8');
const layout = fs.readFileSync(path.join(__dirname, 'layout_mode.js'), 'utf8');

assert.ok(
  lineage.includes('parseArtifactPath(record.url).artifact_ref'),
  'artifact previews must pass the immutable ArtifactRef to Electron',
);
assert.ok(
  !lineage.includes("pasteButton.textContent = '粘贴图片'"),
  'the picture area must not render a duplicate paste button beside Add picture',
);
assert.ok(
  lineage.includes("area.addEventListener('ai00:paste-image'"),
  'the picture area must expose its paste action to the upload panel',
);
const pictureArea = lineage.slice(
  lineage.indexOf('function _renderPicArea('),
  lineage.indexOf('// ── 内联对话框', lineage.indexOf('function _renderPicArea(')),
);
assert.ok(
  pictureArea.includes('_openImageLightbox([pic.url])'),
  'clicking a managed thumbnail must use the in-app lightbox',
);
assert.ok(
  !pictureArea.includes('window.open('),
  'managed thumbnails must not open an Electron popup window',
);
assert.ok(
  layout.includes("new CustomEvent('ai00:paste-image')"),
  'the upload panel paste controls must invoke the picture area paste action',
);

const saveHandler = layout.slice(
  layout.indexOf("dlg.querySelector('#_picDlgOk').addEventListener"),
  layout.indexOf("  /**\n   * 创建布局视图用的悬浮", layout.indexOf("dlg.querySelector('#_picDlgOk').addEventListener")),
);
assert.ok(
  saveHandler.includes('this.refreshProcessCard(gid)'),
  'saving pictures must refresh only the affected process card',
);
assert.ok(
  !saveHandler.includes('_reload()'),
  'saving pictures must not reload the BOP or reset the current viewport',
);

async function testOptimisticPictureSave() {
  const dom = new JSDOM('<!doctype html><body></body>', { url: 'http://localhost/' });
  const context = vm.createContext({
    window: dom.window,
    document: dom.window.document,
    CustomEvent: dom.window.CustomEvent,
    setTimeout,
    clearTimeout,
    console,
  });
  vm.runInContext(`${layout}\nglobalThis.__LayoutMode = LayoutMode;`, context);

  const row = { gid: 'process-1', node_type: 'process', process_flow_pic: ['old'], process_chart_pic: [] };
  let finishPersistence;
  let patchCalls = 0;
  const persistence = new Promise(resolve => { finishPersistence = resolve; });
  const mode = Object.create(context.__LayoutMode.prototype);
  mode._data = {
    rowByGid: new Map([[row.gid, row]]),
    renderPicArea(el) { el.innerHTML = '<div class="lv-pic-area"></div>'; },
    patchEntry: async () => { patchCalls += 1; await persistence; },
    toast() {},
  };
  let cardRefreshes = 0;
  mode.refreshProcessCard = () => { cardRefreshes += 1; return true; };

  await mode._openPicUploadDialog(row.gid, row);
  dom.window.document.querySelector('#_picDlgOk').click();
  assert.equal(dom.window.document.querySelector('#_picDlgOk'), null, 'the dialog must close before persistence finishes');
  assert.equal(patchCalls, 1, 'save must issue exactly one persistence call');
  assert.equal(cardRefreshes, 1, 'save must optimistically refresh only the current card');
  finishPersistence();
  await persistence;
}

testOptimisticPictureSave()
  .then(() => console.log('lineage artifact preview, paste controls, and local save: OK'))
  .catch(error => { console.error(error); process.exitCode = 1; });
