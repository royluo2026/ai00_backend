/**
 * lineage.test.js — BOP Lineage 数据层单元测试
 * 运行方式: node web/lineage_view/lineage.test.js
 * 依赖: Node.js 内置 assert，无需额外安装
 */

'use strict';
const assert = require('assert');

// ─────────────────────────────────────────────────────────────────────
// 把 lineage.js 里的纯逻辑函数复制到此文件，脱离 DOM 独立运行
// ─────────────────────────────────────────────────────────────────────

const STATS_PRIORITY = [
  'operation','step','role_req','equipment_req',
  'tooling_req','part','tool_req','station_process',
  'line_process','factory_bop','test_case',
  'role_ref','equipment_ref','tooling_ref','tool_ref',
  'station_ref','std_fastener',
];

// ── 复制自 lineage.js ──────────────────────────────────────────────

function _flattenMeta(rows) {
  return rows.map(r => {
    if (r.meta && typeof r.meta === 'object') return { ...r, ...r.meta };
    if (typeof r.meta === 'string') {
      try { return { ...r, ...JSON.parse(r.meta) }; } catch { return r; }
    }
    return r;
  });
}

let _rows = [], _rowByGid = new Map(), _childMap = new Map();
let _statsMap = new Map(), _collapsed = new Set();
let _typeFilter = [], _maxDepth = 4, _searchText = '';

function _buildIndexes(rows) {
  _rowByGid.clear(); _childMap.clear();
  for (const r of rows) _rowByGid.set(r.gid, r);
  for (const r of rows) {
    const pk = r.parent_bop_gid || null;
    if (!_childMap.has(pk)) _childMap.set(pk, []);
    _childMap.get(pk).push(r);
  }
  for (const [, arr] of _childMap) arr.sort((a, b) => (a.seq_no ?? 0) - (b.seq_no ?? 0));
}

function _buildStats() {
  _statsMap.clear();
  const sorted = [..._rows].sort((a, b) => (b.level ?? 0) - (a.level ?? 0));
  for (const r of sorted) {
    const myStats = {};
    if (r.node_type) myStats[r.node_type] = (myStats[r.node_type] || 0) + 1;
    for (const child of (_childMap.get(r.gid) || [])) {
      for (const [nt, cnt] of Object.entries(_statsMap.get(child.gid) || {}))
        myStats[nt] = (myStats[nt] || 0) + cnt;
    }
    _statsMap.set(r.gid, myStats);
  }
}

function _getDescendantStats(gid) {
  const selfStat = _statsMap.get(gid) || {};
  const self = _rowByGid.get(gid);
  const result = { ...selfStat };
  if (self?.node_type && result[self.node_type] > 0) {
    result[self.node_type]--;
    if (result[self.node_type] === 0) delete result[self.node_type];
  }
  return result;
}

function _getTop4Stats(desc) {
  const byPrio = STATS_PRIORITY.filter(nt => desc[nt]).map(nt => [nt, desc[nt]]);
  const others = Object.entries(desc).filter(([nt]) => !STATS_PRIORITY.includes(nt)).sort((a,b)=>b[1]-a[1]);
  return [...byPrio, ...others].slice(0, 4);
}

function _initCollapsed() {
  for (const r of _rows) {
    if ((r.level ?? 0) >= _maxDepth) _collapsed.add(r.parent_bop_gid || null);
  }
  _collapsed.delete(null);
}

function _passFilter(row) {
  if (_typeFilter.length > 0 && !_typeFilter.includes(row.node_type)) return false;
  if (_searchText && !(row.title || '').toLowerCase().includes(_searchText.toLowerCase())) return false;
  return true;
}

function _getDropPosition(relY, relX, h, w) {
  if (relY < h * 0.25) return 'up';
  if (relY > h * 0.75) return 'down';
  if (relX > w * 0.75) return 'right';
  return null;
}

// ─────────────────────────────────────────────────────────────────────
// 测试工具
// ─────────────────────────────────────────────────────────────────────

let _pass = 0, _fail = 0;

function test(name, fn) {
  try {
    fn();
    console.log(`  ✓ ${name}`);
    _pass++;
  } catch (e) {
    console.error(`  ✗ ${name}`);
    console.error(`    → ${e.message}`);
    _fail++;
  }
}

function describe(suite, fn) {
  console.log(`\n${suite}`);
  fn();
}

// ─────────────────────────────────────────────────────────────────────
// 测试数据
// ─────────────────────────────────────────────────────────────────────

/**
 * 构造一棵简单 BOP 树（5 节点）：
 *
 *   root (level 0, factory_bop)
 *   └── lineA (level 1, line_process)
 *       ├── stationA (level 2, station_process)
 *       │   └── op1 (level 3, operation)
 *       │       └── step1 (level 4, step)  ← 应被折叠
 *       └── stationB (level 2, station_process)
 */
const TREE = [
  { gid: 'root',    parent_bop_gid: null,      level: 0, seq_no: 1, node_type: 'factory_bop',     title: '工厂BOP',    status: 'released' },
  { gid: 'lineA',   parent_bop_gid: 'root',    level: 1, seq_no: 1, node_type: 'line_process',    title: '总装线A',    status: 'planned' },
  { gid: 'stationA',parent_bop_gid: 'lineA',   level: 2, seq_no: 1, node_type: 'station_process', title: '工位A',      status: 'concept' },
  { gid: 'stationB',parent_bop_gid: 'lineA',   level: 2, seq_no: 2, node_type: 'station_process', title: '工位B',      status: 'concept' },
  { gid: 'op1',     parent_bop_gid: 'stationA',level: 3, seq_no: 1, node_type: 'operation',       title: '安装发动机盖', status: 'concept' },
  { gid: 'step1',   parent_bop_gid: 'op1',     level: 4, seq_no: 1, node_type: 'step',            title: '拧紧螺栓',   status: 'concept' },
];

// ─────────────────────────────────────────────────────────────────────
// 测试套件
// ─────────────────────────────────────────────────────────────────────

describe('_flattenMeta()', () => {
  test('无 meta 字段时原样返回', () => {
    const rows = [{ gid: 'a', title: 'A' }];
    const result = _flattenMeta(rows);
    assert.strictEqual(result[0].title, 'A');
  });

  test('meta 是对象时字段提升到顶层', () => {
    const rows = [{ gid: 'a', title: 'A', meta: { vpps: 'P001', quantity: 3 } }];
    const [r] = _flattenMeta(rows);
    assert.strictEqual(r.vpps, 'P001');
    assert.strictEqual(r.quantity, 3);
    assert.strictEqual(r.title, 'A');  // 原字段保留
  });

  test('meta 是 JSON 字符串时正确解析', () => {
    const rows = [{ gid: 'b', meta: '{"torque":25,"torque_importance":"A"}' }];
    const [r] = _flattenMeta(rows);
    assert.strictEqual(r.torque, 25);
    assert.strictEqual(r.torque_importance, 'A');
  });

  test('meta 是非法 JSON 字符串时不崩溃', () => {
    const rows = [{ gid: 'c', title: 'C', meta: '{broken json' }];
    const [r] = _flattenMeta(rows);
    assert.strictEqual(r.title, 'C');  // 原始 row 原样返回
  });
});

describe('_buildIndexes()', () => {
  test('_rowByGid 包含所有节点', () => {
    _rows = [...TREE];
    _buildIndexes(_rows);
    assert.strictEqual(_rowByGid.size, 6);
    assert.ok(_rowByGid.has('root'));
    assert.ok(_rowByGid.has('step1'));
  });

  test('根节点的父 key 为 null', () => {
    assert.ok(_childMap.has(null));
    assert.strictEqual(_childMap.get(null).length, 1);
    assert.strictEqual(_childMap.get(null)[0].gid, 'root');
  });

  test('lineA 有 2 个子节点，按 seq_no 升序', () => {
    const children = _childMap.get('lineA');
    assert.strictEqual(children.length, 2);
    assert.strictEqual(children[0].gid, 'stationA');
    assert.strictEqual(children[1].gid, 'stationB');
  });

  test('叶子节点无子节点', () => {
    assert.strictEqual(_childMap.get('step1') ?? null, null);
  });
});

describe('_buildStats()', () => {
  test('叶子节点 step1 统计仅含自身', () => {
    _rows = [...TREE];
    _buildIndexes(_rows);
    _buildStats();
    const stats = _statsMap.get('step1');
    assert.deepStrictEqual(stats, { step: 1 });
  });

  test('op1 统计包含自身(operation:1) + step1(step:1)', () => {
    const stats = _statsMap.get('op1');
    assert.strictEqual(stats.operation, 1);
    assert.strictEqual(stats.step, 1);
  });

  test('root 聚合所有后代类型', () => {
    const stats = _statsMap.get('root');
    assert.strictEqual(stats.factory_bop, 1);
    assert.strictEqual(stats.line_process, 1);
    assert.strictEqual(stats.station_process, 2);
    assert.strictEqual(stats.operation, 1);
    assert.strictEqual(stats.step, 1);
  });
});

describe('_getDescendantStats()', () => {
  test('root 的后代统计不含 root 自身', () => {
    const desc = _getDescendantStats('root');
    // factory_bop 是 root 自身，应从统计中减去
    assert.strictEqual(desc.factory_bop, undefined);
    assert.strictEqual(desc.line_process, 1);
    assert.strictEqual(desc.station_process, 2);
    assert.strictEqual(desc.operation, 1);
    assert.strictEqual(desc.step, 1);
  });

  test('叶子节点 step1 后代统计为空', () => {
    const desc = _getDescendantStats('step1');
    assert.deepStrictEqual(desc, {});
  });

  test('stationA 后代含 operation + step 各1', () => {
    const desc = _getDescendantStats('stationA');
    assert.strictEqual(desc.operation, 1);
    assert.strictEqual(desc.step, 1);
    assert.strictEqual(desc.station_process, undefined);
  });
});

describe('_getTop4Stats()', () => {
  test('按 STATS_PRIORITY 顺序取优先项', () => {
    const desc = { operation: 5, step: 3, role_req: 1, equipment_req: 2, part: 10 };
    const top4 = _getTop4Stats(desc);
    assert.strictEqual(top4.length, 4);
    // operation > step > role_req > equipment_req（按优先级，不是按数量）
    assert.strictEqual(top4[0][0], 'operation');
    assert.strictEqual(top4[1][0], 'step');
    assert.strictEqual(top4[2][0], 'role_req');
    assert.strictEqual(top4[3][0], 'equipment_req');
    // part 虽然数量最多(10)，但优先级低，被挤掉
  });

  test('后代种类不足4种时只返回实际数量', () => {
    const desc = { operation: 1, step: 2 };
    const top4 = _getTop4Stats(desc);
    assert.strictEqual(top4.length, 2);
  });

  test('不在优先列表中的类型按数量降序排在后面', () => {
    const desc = { unknown_type_z: 100, unknown_type_a: 50, operation: 1 };
    const top4 = _getTop4Stats(desc);
    assert.strictEqual(top4[0][0], 'operation');   // 优先项先
    assert.strictEqual(top4[1][0], 'unknown_type_z'); // 剩余按数量降序
    assert.strictEqual(top4[2][0], 'unknown_type_a');
  });
});

describe('_initCollapsed()', () => {
  test('level=4 的节点之父（op1）应被加入 _collapsed', () => {
    _rows = [...TREE];
    _maxDepth = 4;
    _buildIndexes(_rows);
    _collapsed.clear();
    _initCollapsed();
    // step1.parent_bop_gid = 'op1'，level(step1)=4 >= maxDepth=4 → op1 折叠
    assert.ok(_collapsed.has('op1'));
  });

  test('null（根节点）不被加入 _collapsed', () => {
    assert.ok(!_collapsed.has(null));
  });

  test('maxDepth=99 时没有节点被折叠', () => {
    _rows = [...TREE];
    _maxDepth = 99;
    _buildIndexes(_rows);
    _collapsed.clear();
    _initCollapsed();
    assert.strictEqual(_collapsed.size, 0);
  });

  test('maxDepth=2 时 level>=2 的节点之父被折叠', () => {
    _rows = [...TREE];
    _maxDepth = 2;
    _buildIndexes(_rows);
    _collapsed.clear();
    _initCollapsed();
    // stationA(lv2).parent=lineA → lineA 折叠
    // stationB(lv2).parent=lineA → lineA 折叠（重复无影响）
    // op1(lv3).parent=stationA → stationA 折叠
    // step1(lv4).parent=op1 → op1 折叠
    assert.ok(_collapsed.has('lineA'));
    assert.ok(_collapsed.has('stationA'));
    assert.ok(_collapsed.has('op1'));
    assert.ok(!_collapsed.has(null));
  });
});

describe('_passFilter()', () => {
  test('无筛选时全部通过', () => {
    _typeFilter = []; _searchText = '';
    assert.ok(_passFilter({ node_type: 'operation', title: '安装' }));
    assert.ok(_passFilter({ node_type: 'step', title: '拧紧' }));
  });

  test('类型筛选：匹配通过，不匹配拒绝', () => {
    _typeFilter = ['operation']; _searchText = '';
    assert.ok(_passFilter({ node_type: 'operation', title: '安装' }));
    assert.ok(!_passFilter({ node_type: 'step', title: '拧紧' }));
  });

  test('搜索文本：包含则通过（大小写不敏感）', () => {
    _typeFilter = []; _searchText = '发动机';
    assert.ok(_passFilter({ node_type: 'operation', title: '安装发动机盖' }));
    assert.ok(!_passFilter({ node_type: 'operation', title: '拧紧螺栓' }));
  });

  test('搜索与类型筛选同时生效（AND 逻辑）', () => {
    _typeFilter = ['operation']; _searchText = '安装';
    assert.ok(_passFilter({ node_type: 'operation', title: '安装发动机盖' }));
    assert.ok(!_passFilter({ node_type: 'step',      title: '安装螺栓' }));   // 类型不对
    assert.ok(!_passFilter({ node_type: 'operation', title: '拧紧螺栓' }));   // 文本不对
  });
});

describe('_getDropPosition()', () => {
  // 参数：(relY, relX, height, width)
  test('y 在上 1/4 区域 → up', () => {
    assert.strictEqual(_getDropPosition(10, 50, 60, 200), 'up');
  });

  test('y 在下 1/4 区域 → down', () => {
    assert.strictEqual(_getDropPosition(50, 50, 60, 200), 'down');
  });

  test('x 在右 1/4 区域（中间高度）→ right', () => {
    assert.strictEqual(_getDropPosition(30, 160, 60, 200), 'right');
  });

  test('中间区域（无强方向）→ null', () => {
    assert.strictEqual(_getDropPosition(30, 80, 60, 200), null);
  });
});

// ─────────────────────────────────────────────────────────────────────
// 汇总
// ─────────────────────────────────────────────────────────────────────
console.log(`\n${'─'.repeat(50)}`);
if (_fail === 0) {
  console.log(`✅ 全部通过  ${_pass} 个测试`);
} else {
  console.log(`❌ ${_fail} 个失败，${_pass} 个通过`);
  process.exit(1);
}
