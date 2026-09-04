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
  const { LineageProgressiveLoader } = require('./lineage_progressive_loader.js');

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
    await loader.loadScope({ version_gid: 'version-1', revision: loaded.revision, scope_kind: 'line', scope_gid: 'line-1' }, {
      onPage: value => scopeRows.push(value.rows.map(row => row.gid)),
    });
    assert.deepStrictEqual(scopeRows, [['line-1'], ['line-1', 'station-1']]);
    assert.strictEqual(calls.filter(call => call.id === 'craft.bop.work_package.get').length, 2);

    const detail = await loader.loadDetail(
      { version_gid: 'version-1', revision: 7, scope_kind: 'line', scope_gid: 'line-1' },
      'station-1',
    );
    assert.strictEqual(detail.entry.gid, 'station-1');
    assert.strictEqual(calls.filter(call => call.id === 'craft.bop.entry.detail.get').length, 1);
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

  const index = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');
  const coordinatorAt = index.indexOf('lineage_load_coordinator.js');
  const storeAt = index.indexOf('lineage_projection_store.js');
  const loaderAt = index.indexOf('lineage_progressive_loader.js');
  const lineageAt = index.indexOf('lineage.js');
  assert.ok(coordinatorAt >= 0 && coordinatorAt < lineageAt, 'coordinator must load before lineage.js');
  assert.ok(storeAt >= 0 && storeAt < lineageAt, 'projection store must load before lineage.js');
  assert.ok(loaderAt >= 0 && loaderAt < lineageAt, 'progressive loader must load before lineage.js');

  const lineage = fs.readFileSync(path.join(__dirname, 'lineage.js'), 'utf8');
  assert.ok(
    !/\/api\/bop\/versions\/\$\{[^}]+\}\/entries/.test(lineage),
    'lineage must not use the unbounded legacy version entries route',
  );
  assert.ok(lineage.includes('LineageProgressiveLoader'), 'lineage must use the progressive loader');
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
