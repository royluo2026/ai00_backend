ALTER TABLE `workmanship_int_ext_mappings`
 ADD COLUMN IF NOT EXISTS `target_binding_id` VARCHAR(255) NULL,
 ADD COLUMN IF NOT EXISTS `target_input_contract` VARCHAR(128) NULL,
 ADD COLUMN IF NOT EXISTS `target_resource_gid` VARCHAR(128) NULL,
 ADD COLUMN IF NOT EXISTS `target_expected_version` BIGINT NULL;

ALTER TABLE `workmanship_int_sync_runs`
 ADD COLUMN IF NOT EXISTS `target_invocation_json` JSON NULL;
