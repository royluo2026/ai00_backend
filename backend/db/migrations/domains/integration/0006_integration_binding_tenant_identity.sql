ALTER TABLE `workmanship_int_mapping_target_bindings`
  ADD COLUMN IF NOT EXISTS `binding_gid` VARCHAR(255) NULL FIRST;

ALTER TABLE `workmanship_int_mapping_target_bindings`
  ADD COLUMN IF NOT EXISTS `semantic_key` VARCHAR(255) NULL AFTER `binding_gid`;

-- Preserve every historical opaque binding identifier before changing the physical key.
-- AI00: RESUMABLE BACKFILL
UPDATE `workmanship_int_mapping_target_bindings`
SET `binding_gid` = COALESCE(NULLIF(`binding_gid`, ''), `binding_id`),
    `semantic_key` = COALESCE(NULLIF(`semantic_key`, ''), `binding_id`)
WHERE `binding_gid` IS NULL OR `binding_gid` = ''
   OR `semantic_key` IS NULL OR `semantic_key` = '';

ALTER TABLE `workmanship_int_mapping_target_bindings`
  MODIFY COLUMN `binding_gid` VARCHAR(255) NOT NULL;

ALTER TABLE `workmanship_int_mapping_target_bindings`
  MODIFY COLUMN `semantic_key` VARCHAR(255) NOT NULL;

ALTER TABLE `workmanship_int_mapping_target_bindings`
  DROP PRIMARY KEY,
  ADD PRIMARY KEY (`binding_gid`);

CREATE UNIQUE INDEX IF NOT EXISTS `uk_int_target_binding_tenant_semantic`
  ON `workmanship_int_mapping_target_bindings` (`team_gid`, `semantic_key`);

-- workmanship_int_ext_mappings.target_binding_id remains the tenant-scoped semantic key.
-- Migration 0003 intentionally declared no physical foreign key, so no legacy reference is rewritten.
