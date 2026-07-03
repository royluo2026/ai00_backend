BEGIN;

-- ── bop_entries.node_type 中文 → 英文（兼容大小写 / 全半角括号变体）─────────

UPDATE bop.bop_entries SET node_type = 'factory_bop'
  WHERE node_type IN ('总装产品bop','总装产品BOP','总装工厂BOP','总装BOP','工厂BOP','产品BOP','BOP');

UPDATE bop.bop_entries SET node_type = 'line_process'
  WHERE node_type IN ('总装线体工艺','产线工艺');

UPDATE bop.bop_entries SET node_type = 'station_process'
  WHERE node_type IN ('总装工位工艺','工位工艺');

UPDATE bop.bop_entries SET node_type = 'operator_process'
  WHERE node_type IN ('总装岗位工艺');

UPDATE bop.bop_entries SET node_type = 'process'
  WHERE node_type IN ('总装工序','工序');

-- 操作（Product）：兼容大写/小写 P，全角/半角括号
UPDATE bop.bop_entries SET node_type = 'operation'
  WHERE LOWER(node_type) IN (
    '总装操作（product）',   -- 全角括号
    '总装操作(product)',     -- 半角括号
    '总装操作'
  );

UPDATE bop.bop_entries SET node_type = 'part'
  WHERE node_type = '零部件';

UPDATE bop.bop_entries SET node_type = 'non_standard_part'
  WHERE node_type = '非标件';

UPDATE bop.bop_entries SET node_type = 'standard_part'
  WHERE node_type = '标准件';

UPDATE bop.bop_entries SET node_type = 'tool_need'
  WHERE node_type IN ('工具','工具（需求）');

UPDATE bop.bop_entries SET node_type = 'tool_factory'
  WHERE node_type IN ('工具（现有）');

UPDATE bop.bop_entries SET node_type = 'fixture_need'
  WHERE node_type IN ('工装','工装（需求）');

UPDATE bop.bop_entries SET node_type = 'fixture_factory'
  WHERE node_type IN ('工装（现有）');

UPDATE bop.bop_entries SET node_type = 'equipment_need'
  WHERE node_type IN ('设备（需求）','设备需求');

UPDATE bop.bop_entries SET node_type = 'equipment_factory'
  WHERE node_type = '设备';

UPDATE bop.bop_entries SET node_type = 'support_material'
  WHERE node_type = '辅料';

-- ── 同步修复 bop_entry_links.link_type ──────────────────────────────────────
-- 将 operation 条目对应的 link 更新到 bop_steps
UPDATE bop.bop_entry_links el
SET link_type = 'bop_steps'
FROM bop.bop_entries e
WHERE el.entry_gid = e.gid
  AND e.node_type = 'operation'
  AND el.link_type IN ('asm_operation','bop_operation','operation');

-- 已有 asm_operation 兜底（不依赖 bop_entries node_type）
UPDATE bop.bop_entry_links SET link_type = 'bop_steps'
  WHERE link_type = 'asm_operation';

COMMIT;
