'use strict';
// Exercise the real load/reload orchestration with controlled outline/scope reads.
const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const vm = require('node:vm');
const { preloadFirstLineScopes } = require('./lineage_progressive_loader.js');
const source = fs.readFileSync(__dirname + '/lineage.js', 'utf8');
const loadSource = source.slice(source.indexOf('async function _load('), source.indexOf('// ── 渲染层'));
const reloadSource = source.slice(source.indexOf('async function _reload('), source.indexOf('// ── 事件绑定'));
function fixture({ failScope = false } = {}) {
  const lines = [{ gid: 'chassis' }, { gid: 'rear' }];
  const loaded = [], highlighted = [];
  let cloudReads = 0;
  const noop = () => {};
  const context = {
    _versionGid: 'demo', _demoStepsVersionGid: 'demo', _demoSelectionEpoch: 1, _versionTag: 'P v2',
    _projectVersions: [{ versionGid: 'demo' }], _comparisonLoaders: new Map(),
    _outlineRowsByVersion: new Map(), _scopeRowsByKey: new Map(), _scopeLinksByKey: new Map(),
    _versionTagMap: new Map(), _loadedVersionGids: new Set(['demo']),
    _verMgr: {}, _activeGid: 'chassis01', _viewMode: 'layout', _layoutDetailPanel: null,
    _layoutMode: { destroyHeavyState: noop, highlightNode: gid => highlighted.push(gid) },
    _level1Filter: new Set(['rear']), _moveQueue: Promise.resolve(),
    _progressiveLoader: {
      clearHeavyData: noop,
      loadVersion: async (gid, { onCommit }) => {
        assert.equal(gid, 'demo');
        onCommit({ revision: 'r1', version: {}, rows: lines });
        return { lines, version: {} };
      },
    },
    document: { querySelector: () => null, getElementById: () => null },
    $columns: {}, _params: { bop_version_gid: 'demo' },
    _updateVersionStatusUI: noop, _rebuildProjectionRows: noop, _initCollapsed: noop,
    _restoreView: () => { context._level1Filter = new Set(['chassis']); },
    _ensureScopeLoaded: async row => { loaded.push(row.gid); if (failScope) throw new Error('scope unavailable'); },
    preloadFirstLineScopes, _render: noop, _refreshDemoStatus: async () => {},
    _loadLineGrants: async () => {}, _loadCloudConfig: () => { cloudReads++; },
    _toast: noop, _syncLayoutUI: noop, _closeOverlayPanel: noop,
    _renderLinkAlerts: noop, _collectLinkAlerts: () => [], _addVersionRoots: async () => {},
  };
  vm.createContext(context);
  vm.runInContext(loadSource + '\n' + reloadSource, context);
  return { context, loaded, highlighted, cloudReads: () => cloudReads };
}
test('demo reload preloads only selected line, ignoring saved chassis filter and old active station', async () => {
  const f = fixture();
  await f.context._reload({ silent: true, demoLineGid: 'rear' });
  assert.deepEqual(f.loaded, ['rear']);
  assert.deepEqual(f.highlighted, ['rear']);
  assert.equal(f.cloudReads(), 0);
});
test('ordinary reload still restores saved selection and cloud layout', async () => {
  const f = fixture();
  await f.context._reload({ silent: true });
  assert.deepEqual(f.loaded, ['chassis']);
  assert.deepEqual(f.highlighted, ['chassis01']);
  assert.equal(f.cloudReads(), 1);
});
test('demo reload propagates failed scope load so progress cannot report success', async () => {
  const f = fixture({ failScope: true });
  await assert.rejects(f.context._reload({ silent: true, demoLineGid: 'rear' }), /scope unavailable/);
  assert.deepEqual(f.highlighted, []);
});
test('queued demo reload cannot touch a newly selected version', async () => {
  const f = fixture();
  let release;
  let loads = 0;
  f.context._load = async () => { loads++; };
  f.context._moveQueue = new Promise(resolve => { release = resolve; });
  const pending = f.context._reload({ silent: true, demoLineGid: 'rear' });
  f.context._versionGid = 'other';
  f.context._activeGid = 'other-line';
  release();
  await pending;
  assert.equal(loads, 0, 'Old queued reload started loading the new version');
  assert.deepEqual(f.loaded, []);
  assert.deepEqual(f.highlighted, []);
  assert.equal(f.context._activeGid, 'other-line');
});
test('comparison restore cannot highlight the old demo after a version switch', async () => {
  const f = fixture();
  f.context._loadedVersionGids.add('comparison');
  let release;
  const comparison = new Promise(resolve => { release = resolve; });
  f.context._addVersionRoots = async () => { f.context._versionGid = 'other'; f.context._activeGid = 'other-line'; await comparison; };
  const pending = f.context._reload({ silent: true, demoLineGid: 'rear' });
  release();
  await pending;
  assert.deepEqual(f.highlighted, []);
  assert.equal(f.context._activeGid, 'other-line');
});
