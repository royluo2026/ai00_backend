const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

test('standard operation import maps supported source columns and keeps their values', () => {
  const source = fs.readFileSync(path.join(__dirname, 'std_op_lib.js'), 'utf8');
  const context = {
    window: { parent: {} },
    document: { readyState: 'loading', addEventListener() {} },
    ListShell: {
      _cf() {},
      buildLoadHandler() { return async () => {}; },
      buildRowsChangeHandler() { return () => {}; },
      makeImportExport() { return {}; },
      makeDiffManager() { return {}; },
    },
    alert() {},
    confirm() { return false; },
    console,
  };
  vm.runInNewContext(
    `${source}\n;globalThis.aliases = STD_OP_COL_ALIASES; globalThis.buildBody = _buildImportBody;`,
    context,
  );

  assert.equal(context.aliases.VPPS, 'vpps');
  assert.equal(context.aliases.Level, 'level');
  assert.equal(context.aliases.ai00_level, 'ai00_level');
  assert.equal(context.aliases['零组件名称'], 'name');
  assert.equal(context.aliases['零组件类型'], 'component_type');
  assert.equal(context.aliases['BOM 行'], 'bom_row');
  assert.equal(context.aliases['父级'], 'parent_bom_row');
  assert.equal(context.aliases['工序VPPS'], 'process_vpps');
  assert.equal(context.aliases['操作VPPS'], 'operation_vpps');
  assert.equal(context.aliases['标记'], 'match_tag');
  assert.equal(context.aliases['零组件描述'], 'description');
  assert.equal(context.aliases['父级VPPS'], 'parent_vpps');
  assert.equal(context.aliases['扭矩重要度'], 'torque_importance');

  assert.deepEqual(
    JSON.parse(JSON.stringify(context.buildBody({
      vpps: 'V100', level: '7', ai00_level: '4', name: '安装支架', vpps_desc: '安装支架描述',
      parent_vpps: 'V010', torque_importance: 'A', component_type: '总装操作',
      bom_row: 'B-2', parent_bom_row: 'B-1', process_vpps: 'P100', operation_vpps: 'O100',
      match_tag: 'part_feed',
    }))),
    {
      code: 'O100', name: '安装支架', standard_time: 0, level: '7', ai00_level: 4, vpps: 'V100',
      vpps_desc: '安装支架描述', torque_importance: 'A', parent_vpps: 'V010',
      component_type: '总装操作', bom_row: 'B-2', parent_bom_row: 'B-1',
      process_vpps: 'P100', operation_vpps: 'O100', match_tag: 'part_feed', part_feed: true,
    },
  );
});
