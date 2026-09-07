'use strict';

const assert = require('assert');
const path = require('path');

const MODULE_PATH = path.join(__dirname, 'lineage_projection_store.js');

function scope(version, revision, kind, gid) {
  return { version_gid: version, revision, scope_kind: kind, scope_gid: gid };
}

function gids(rows) {
  return rows.map(row => row.gid);
}

async function runLineageProjectionStoreTests() {
  const { LineageProjectionStore, utf8ByteLength } = require(MODULE_PATH);

  assert.strictEqual(utf8ByteLength('中'), 3, 'UTF-8 estimation must count multibyte text');

  {
    const store = new LineageProjectionStore();
    store.replaceOutline({ version_gid: 'v1', revision: 1 }, [{ gid: 'line-a' }]);
    store.replaceOutline({ version_gid: 'v1', revision: 1 }, [{ gid: 'line-b' }]);
    assert.deepStrictEqual(gids(store.outlineRows({ version_gid: 'v1', revision: 1 })), ['line-b']);
  }

  {
    const store = new LineageProjectionStore();
    const key = scope('v1', 1, 'line', 'line-a');
    store.appendScopePage(key, { cursor: null, rows: [{ gid: 'a' }, { gid: 'b' }], next_cursor: 'p2' });
    store.appendScopePage(key, { cursor: null, rows: [{ gid: 'a' }, { gid: 'b' }], next_cursor: 'p2' });
    store.appendScopePage(key, { cursor: 'p2', rows: [{ gid: 'b' }, { gid: 'c' }], next_cursor: null });
    assert.deepStrictEqual(gids(store.rowsForActiveScope(key)), ['a', 'b', 'c']);
  }

  {
    const store = new LineageProjectionStore({ maxScopes: 3 });
    const a = scope('v1', 1, 'line', 'a');
    const b = scope('v1', 1, 'line', 'b');
    const c = scope('v1', 1, 'line', 'c');
    const d = scope('v1', 1, 'line', 'd');
    for (const item of [a, b, c]) store.appendScopePage(item, { cursor: null, rows: [{ gid: item.scope_gid }] });
    store.touchScope(a);
    store.appendScopePage(d, { cursor: null, rows: [{ gid: 'd' }] });
    assert.deepStrictEqual(gids(store.rowsForActiveScope(a)), ['a']);
    assert.deepStrictEqual(store.rowsForActiveScope(b), [], 'least recently used scope must be evicted whole');
    assert.deepStrictEqual(gids(store.rowsForActiveScope(d)), ['d']);
  }

  {
    const store = new LineageProjectionStore({ maxNodes: 3 });
    const a = scope('v1', 1, 'line', 'a');
    const b = scope('v1', 1, 'line', 'b');
    store.appendScopePage(a, { cursor: null, rows: [{ gid: 'a1' }, { gid: 'a2' }] });
    store.appendScopePage(b, { cursor: null, rows: [{ gid: 'b1' }, { gid: 'b2' }] });
    assert.deepStrictEqual(store.rowsForActiveScope(a), []);
    assert.deepStrictEqual(gids(store.rowsForActiveScope(b)), ['b1', 'b2']);
  }

  {
    const store = new LineageProjectionStore({ maxScopes: 3, maxNodes: 12_000, maxBytes: 16 * 1024 * 1024 });
    const large = scope('v-large', 1, 'line', 'line-10k');
    for (let offset = 0; offset < 10_000; offset += 200) {
      store.appendScopePage(large, {
        cursor: offset ? `p-${offset}` : null,
        rows: Array.from({ length: 200 }, (_, index) => ({
          gid: `node-${offset + index}`,
          parent_gid: offset + index ? `node-${offset + index - 1}` : 'line-10k',
          node_type: 'operation',
          title: `N${offset + index}`,
        })),
      });
    }
    assert.strictEqual(store.rowsForActiveScope(large).length, 10_000, 'approved UI budget must retain one 10k scope');
  }

  {
    const store = new LineageProjectionStore({ maxBytes: 1_000 });
    const a = scope('v1', 1, 'line', 'a');
    const b = scope('v1', 1, 'line', 'b');
    store.appendScopePage(a, { cursor: null, rows: [{ gid: 'a', title: '甲'.repeat(220) }] });
    store.appendScopePage(b, { cursor: null, rows: [{ gid: 'b', title: '乙'.repeat(220) }] });
    assert.deepStrictEqual(store.rowsForActiveScope(a), [], 'byte pressure must evict the LRU scope');
    assert.deepStrictEqual(gids(store.rowsForActiveScope(b)), ['b']);
  }

  {
    const store = new LineageProjectionStore({ maxScopes: 1 });
    const a = scope('v1', 1, 'line', 'a');
    const b = scope('v1', 1, 'line', 'b');
    store.appendScopePage(a, { cursor: null, rows: [{ gid: 'a' }] });
    store.selectDetail(a, { gid: 'detail-a', payload: 'heavy' });
    assert.strictEqual(store.selectedDetail().gid, 'detail-a');
    store.appendScopePage(b, { cursor: null, rows: [{ gid: 'b' }] });
    assert.strictEqual(store.selectedDetail(), null, 'detail must leave with its evicted scope');
  }

  {
    const store = new LineageProjectionStore();
    const rev1 = scope('v1', 1, 'line', 'same');
    const rev2 = scope('v1', 2, 'line', 'same');
    const otherVersion = scope('v2', 1, 'line', 'same');
    store.appendScopePage(rev1, { cursor: null, rows: [{ gid: 'rev-1' }] });
    store.appendScopePage(rev2, { cursor: null, rows: [{ gid: 'rev-2' }] });
    store.appendScopePage(otherVersion, { cursor: null, rows: [{ gid: 'version-2' }] });
    assert.deepStrictEqual(gids(store.rowsForActiveScope(rev1)), ['rev-1']);
    assert.deepStrictEqual(gids(store.rowsForActiveScope(rev2)), ['rev-2']);
    assert.deepStrictEqual(gids(store.rowsForActiveScope(otherVersion)), ['version-2']);
  }

  {
    const store = new LineageProjectionStore();
    const key = scope('v1', 1, 'line', 'a');
    const outlineKey = { version_gid: 'v1', revision: 1 };
    store.replaceOutline(outlineKey, [{ gid: 'outline' }]);
    store.appendScopePage(key, { cursor: null, rows: [{ gid: 'row' }] });
    store.selectDetail(key, { gid: 'detail' });
    store.clearHeavyData();
    assert.deepStrictEqual(store.rowsForActiveScope(key), []);
    assert.strictEqual(store.selectedDetail(), null);
    assert.deepStrictEqual(gids(store.outlineRows(outlineKey)), ['outline'], 'outline survives heavy-data clear');
    store.dispose();
    assert.deepStrictEqual(store.outlineRows(outlineKey), []);
    assert.throws(() => store.appendScopePage(key, { cursor: null, rows: [] }), /disposed/);
  }
}

if (require.main === module) {
  runLineageProjectionStoreTests()
    .then(() => console.log('lineage_projection_store: all tests passed'))
    .catch(error => {
      console.error(error);
      process.exitCode = 1;
    });
}

module.exports = { runLineageProjectionStoreTests };
