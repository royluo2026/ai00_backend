'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');

const { LineageLoadCoordinator } = require('./lineage_load_coordinator.js');
const { LineageProjectionStore } = require('./lineage_projection_store.js');

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

async function tick() {
  await new Promise(resolve => setTimeout(resolve, 0));
}

async function runLineageProgressiveLoadingTests() {
  const { LineageProgressiveLoader, preloadFirstLineScopes } = require('./lineage_progressive_loader.js');

  {
    assert.strictEqual(typeof preloadFirstLineScopes, 'function', 'initial line preloader must be available');
    const first = deferred();
    const second = deferred();
    const started = [];
    const completion = preloadFirstLineScopes(
      [{ gid: 'line-1' }, { gid: 'line-2' }, { gid: 'line-3' }],
      line => {
        started.push(line.gid);
        return line.gid === 'line-1' ? first.promise : second.promise;
      },
    );
    await tick();
    assert.deepStrictEqual(started, ['line-1', 'line-2'], 'the first two lines must start before either finishes');
    first.resolve('first');
    second.resolve('second');
    assert.deepStrictEqual(
      (await completion).map(result => result.status),
      ['fulfilled', 'fulfilled'],
    );
  }

  {
    const started = [];
    await preloadFirstLineScopes(
      [
        { gid: 'hidden-1' },
        { gid: 'hidden-2' },
        { gid: 'visible-1' },
        { gid: 'visible-2' },
        { gid: 'visible-3' },
      ],
      async line => { started.push(line.gid); },
      new Set(['visible-1', 'visible-2', 'visible-3']),
    );
    assert.deepStrictEqual(
      started,
      ['visible-1', 'visible-2', 'visible-3'],
      'initial preload must target every line currently visible in the saved filter',
    );
  }

  {
    let attempts = 0;
    const results = await preloadFirstLineScopes(
      [{ gid: 'line-transient' }],
      async () => {
        attempts += 1;
        if (attempts < 3) throw new Error('invocation_unavailable');
        return 'loaded';
      },
      null,
      { retryDelays: [0, 0], sleep: async () => {} },
    );
    assert.strictEqual(attempts, 3, 'transient read failures must be retried twice');
    assert.deepStrictEqual(results, [{ status: 'fulfilled', value: 'loaded' }]);
  }

  {
    const results = await preloadFirstLineScopes(
      [{ gid: 'line-broken' }],
      async () => { throw new Error('provider_failed'); },
      null,
      { retryDelays: [0, 0], sleep: async () => {} },
    );
    assert.strictEqual(results[0].status, 'rejected', 'permanent failures must remain visible to the caller');
    assert.strictEqual(results[0].reason.message, 'provider_failed');
  }

  {
    const calls = [];
    const commits = [];
    const invoke = async (id, version, payload, options = {}) => {
      calls.push({ id, version, payload, signal: options.signal });
      if (id === 'craft.bop.version.get') {
        return { version_gid: payload.version_gid, revision: 7, status: 'active' };
      }
      if (id === 'craft.bop.structure.outline.get') {
        return {
          version_gid: payload.version_gid,
          revision: 7,
          root: { gid: 'root', parent_gid: null, node_type: 'factory_bop', sort_order: 0, title: 'Root' },
          lines: [{ gid: 'line-1', parent_gid: 'root', node_type: 'line_process', sort_order: 1, title: 'Line', counts: { stations: 2, roles: 1, processes: 3, operations: 4, parts: 5, resources: 6 } }],
          total_lines: 1,
          next_cursor: null,
        };
      }
      if (id === 'craft.bop.work_package.get') {
        assert.ok(payload.page_size <= 200, 'work package page must not exceed its contract');
        if (!payload.cursor) {
          return {
            version_gid: payload.version_gid, revision: 7,
            scope: { kind: 'line', gid: 'line-1' },
            nodes: [{ gid: 'line-1', parent_gid: 'root', node_type: 'line_process', sort_order: 1, title: 'Line', vpps: null, part_refs: [], tool_refs: [], fixture_refs: [], equipment_refs: [], knowledge_refs: [], rule_refs: [] }],
            links: [], total_count: 2, next_cursor: 'page-2',
          };
        }
        return {
          version_gid: payload.version_gid, revision: 7,
          scope: { kind: 'line', gid: 'line-1' },
          nodes: [{ gid: 'station-1', parent_gid: 'line-1', node_type: 'station_process', sort_order: 2, title: 'Station', vpps: null, part_refs: [], tool_refs: [], fixture_refs: [], equipment_refs: [], knowledge_refs: [], rule_refs: [] }],
          links: [], total_count: 2, next_cursor: null,
        };
      }
      if (id === 'craft.bop.entry.detail.get') {
        return { version_gid: payload.version_gid, revision: 7, entry: { gid: payload.entry_gid, version_gid: payload.version_gid, node_type: 'station_process', sort_order: 2, meta: {} }, links: [] };
      }
      throw new Error(`unexpected capability ${id}@${version}`);
    };
    const loader = new LineageProgressiveLoader({
      invokeCapability: invoke,
      coordinator: new LineageLoadCoordinator(),
      store: new LineageProjectionStore(),
    });

    const loaded = await loader.loadVersion('version-1', { onCommit: value => commits.push(value) });
    assert.deepStrictEqual(calls.map(call => `${call.id}@${call.version}`), [
      'craft.bop.version.get@1',
      'craft.bop.structure.outline.get@1',
    ], 'first paint may only require version and outline capabilities');
    assert.strictEqual(commits.length, 1);
    assert.deepStrictEqual(commits[0].rows.map(row => row.gid), ['root', 'line-1']);

    const scopeRows = [];
    const completedScopes = [];
    await loader.loadScope({ version_gid: 'version-1', revision: loaded.revision, scope_kind: 'line', scope_gid: 'line-1' }, {
      onPage: value => scopeRows.push(value.rows.map(row => row.gid)),
      onComplete: value => completedScopes.push(value.rows.map(row => row.gid)),
    });
    assert.deepStrictEqual(scopeRows, [['line-1'], ['line-1', 'station-1']]);
    assert.deepStrictEqual(
      completedScopes,
      [['line-1', 'station-1']],
      'a paged line load must expose one stable completion instead of asking the view to redraw for every page',
    );
    assert.strictEqual(calls.filter(call => call.id === 'craft.bop.work_package.get').length, 2);

    const detail = await loader.loadDetail(
      { version_gid: 'version-1', revision: 7, scope_kind: 'line', scope_gid: 'line-1' },
      'station-1',
    );
    assert.strictEqual(detail.entry.gid, 'station-1');
    assert.strictEqual(calls.filter(call => call.id === 'craft.bop.entry.detail.get').length, 1);
  }

  {
    const oldRead = deferred();
    const newRead = deferred();
    let reads = 0;
    const store = new LineageProjectionStore();
    const loader = new LineageProgressiveLoader({ store, invokeCapability: async (id) => {
      if (id === 'craft.bop.version.get') return { revision: 1 };
      if (id === 'craft.bop.structure.outline.get') return { lines: [], next_cursor: null };
      if (id === 'craft.bop.work_package.get') return { nodes: [{ gid: 'entry' }], next_cursor: null };
      reads++;
      return reads === 1 ? oldRead.promise : newRead.promise;
    }});
    await loader.loadVersion('v1');
    const scope = { version_gid: 'v1', revision: 1, scope_kind: 'line', scope_gid: 'line' };
    await loader.loadScope(scope);
    const beforeSave = loader.loadDetail(scope, 'entry');
    const afterSave = loader.loadDetail(scope, 'entry', { force: true });
    assert.equal(reads, 2, 'post-save read must not reuse a pre-save flight');
    const saved = { entry: { gid: 'entry' }, links: [{ link_gid: 'saved' }] };
    newRead.resolve(saved);
    assert.strictEqual(await afterSave, saved);
    oldRead.resolve({ entry: { gid: 'entry' }, links: [] });
    assert.equal((await beforeSave).cancelled, true, 'late old detail must not replace saved state');
    assert.strictEqual(store.selectedDetail(), saved);
  }

  {
    const oldOutline = deferred();
    const commits = [];
    let oldSignal;
    const invoke = async (id, _version, payload, options = {}) => {
      if (id === 'craft.bop.version.get') return { version_gid: payload.version_gid, revision: 1, status: 'active' };
      if (payload.version_gid === 'old') {
        oldSignal = options.signal;
        return oldOutline.promise;
      }
      return { version_gid: 'new', revision: 1, root: null, lines: [], total_lines: 0, next_cursor: null };
    };
    const loader = new LineageProgressiveLoader({ invokeCapability: invoke });
    const stale = loader.loadVersion('old', { onCommit: value => commits.push(value.version.version_gid) });
    await tick();
    const current = loader.loadVersion('new', { onCommit: value => commits.push(value.version.version_gid) });
    await current;
    assert.strictEqual(oldSignal.aborted, true, 'version switch must abort the older generation');
    oldOutline.resolve({ version_gid: 'old', revision: 1, root: null, lines: [], total_lines: 0, next_cursor: null });
    await stale;
    assert.deepStrictEqual(commits, ['new'], 'stale response must never commit');
  }

  {
    const versionResult = deferred();
    let versionCalls = 0;
    const invoke = async (id, _version, payload) => {
      if (id === 'craft.bop.version.get') { versionCalls += 1; return versionResult.promise; }
      return { version_gid: payload.version_gid, revision: 1, root: null, lines: [], total_lines: 0, next_cursor: null };
    };
    const loader = new LineageProgressiveLoader({ invokeCapability: invoke });
    const first = loader.loadVersion('same', { force: true });
    const second = loader.loadVersion('same', { force: true });
    assert.strictEqual(first, second, 'duplicate refresh must share one load chain');
    versionResult.resolve({ version_gid: 'same', revision: 1, status: 'active' });
    await first;
    assert.strictEqual(versionCalls, 1);
  }

  {
    const loader = new LineageProgressiveLoader({
      invokeCapability: async (id, _version, payload) => {
        if (id === 'craft.bop.version.get') return { version_gid: payload.version_gid, revision: 1 };
        return { version_gid: payload.version_gid, revision: 1, root: null, lines: [], total_lines: 0, next_cursor: null };
      },
    });
    await loader.loadVersion('dispose-me');
    loader.dispose();
    assert.throws(() => loader.loadVersion('after-dispose'), /disposed/);
  }

  {
    global.window ||= { parent: {}, top: {} };
    const { LayoutMode } = require('./layout_mode.js');
    const layoutEl = { dataset: {}, innerHTML: '', onclick: null,
      removeAttribute(name) { if (name === 'data-rendered') delete this.dataset.rendered; } };
    const lineEl = { querySelector: () => layoutEl };
    let calls = 0;
    const data = {
      rowByGid: new Map([['line-3', { gid: 'line-3', node_type: 'line_process' }]]),
      childMap: new Map(),
      isLineScopeLoaded: () => false,
      loadLineScope: async () => { calls += 1; throw new Error('scope failed'); },
    };
    const mode = { _data: data, _renderedLineGids: new Set(),
      _world: { querySelector: selector => selector.includes(' .ll-line-layout') ? layoutEl : lineEl },
      _renderLineCards: LayoutMode.prototype._renderLineCards };
    mode._renderLineCards('line-3');
    assert.match(layoutEl.innerHTML, /加载工位中/);
    assert.strictEqual(calls, 1, 'an unpreloaded visible line must request its station scope');
    await tick();
    assert.match(layoutEl.innerHTML, /工位加载失败，点击重试/);
    layoutEl.onclick();
    assert.strictEqual(calls, 2, 'failed line scope must be retryable');
  }

  const index = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');
  const coordinatorAt = index.indexOf('lineage_load_coordinator.js');
  const storeAt = index.indexOf('lineage_projection_store.js');
  const loaderAt = index.indexOf('lineage_progressive_loader.js');
  const lineageAt = index.indexOf('lineage.js');
  assert.ok(coordinatorAt >= 0 && coordinatorAt < lineageAt, 'coordinator must load before lineage.js');
  assert.ok(storeAt >= 0 && storeAt < lineageAt, 'projection store must load before lineage.js');
  assert.ok(loaderAt >= 0 && loaderAt < lineageAt, 'progressive loader must load before lineage.js');

  const lineage = fs.readFileSync(path.join(__dirname, 'lineage.js'), 'utf8');
  assert.match(lineage, /\blet _versionTag\s*=/, 'version switch must be able to update the current tag');
  assert.ok(
    !/\/api\/bop\/versions\/\$\{[^}]+\}\/entries/.test(lineage),
    'lineage must not use the unbounded legacy version entries route',
  );
  assert.ok(lineage.includes('LineageProgressiveLoader'), 'lineage must use the progressive loader');
  assert.ok(
    lineage.includes("preloadFailure?.status === 'rejected'"),
    'lineage must surface a failed selected-line preload instead of rendering it as no stations',
  );
  const loadStart = lineage.indexOf('async function _load(');
  const clearHeavyData = lineage.indexOf('_progressiveLoader.clearHeavyData()', loadStart);
  const showLoadingOverlay = lineage.indexOf("classList.remove('hidden')", loadStart);
  assert.ok(
    showLoadingOverlay > loadStart && showLoadingOverlay < clearHeavyData,
    'a reload must cover the cleared layout until selected line scopes finish loading',
  );
  const detailPanel = fs.readFileSync(path.join(__dirname, 'layout_detail_panel.js'), 'utf8');
  assert.ok(
    !/\/api\/bop\/versions\/\$\{[^}]+\}\/entries/.test(detailPanel),
    'detail panel must not reintroduce the unbounded legacy version entries route',
  );
  const loaderSource = fs.readFileSync(path.join(__dirname, 'lineage_progressive_loader.js'), 'utf8');
  for (const capability of [
    'craft.bop.version.get',
    'craft.bop.structure.outline.get',
    'craft.bop.work_package.get',
    'craft.bop.entry.detail.get',
  ]) {
    assert.ok(loaderSource.includes(capability), `progressive loader must invoke ${capability}`);
  }
}

if (require.main === module) {
  runLineageProgressiveLoadingTests()
    .then(() => console.log('lineage_progressive_loading: all tests passed'))
    .catch(error => {
      console.error(error);
      process.exitCode = 1;
    });
}

module.exports = { runLineageProgressiveLoadingTests };
