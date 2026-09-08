-- Preserve Teamcenter GBOP identity, hierarchy, and part-feed matching fields.
ALTER TABLE `workmanship_craft_standard_operations`
  ADD COLUMN IF NOT EXISTS `component_type` VARCHAR(255) NOT NULL DEFAULT '' AFTER `description`;
ALTER TABLE `workmanship_craft_standard_operations`
  ADD COLUMN IF NOT EXISTS `bom_row` VARCHAR(255) NOT NULL DEFAULT '' AFTER `component_type`;
ALTER TABLE `workmanship_craft_standard_operations`
  ADD COLUMN IF NOT EXISTS `parent_bom_row` VARCHAR(255) NOT NULL DEFAULT '' AFTER `bom_row`;
ALTER TABLE `workmanship_craft_standard_operations`
  ADD COLUMN IF NOT EXISTS `process_vpps` VARCHAR(255) NOT NULL DEFAULT '' AFTER `parent_vpps`;
ALTER TABLE `workmanship_craft_standard_operations`
  ADD COLUMN IF NOT EXISTS `operation_vpps` VARCHAR(255) NOT NULL DEFAULT '' AFTER `process_vpps`;
ALTER TABLE `workmanship_craft_standard_operations`
  ADD COLUMN IF NOT EXISTS `vpps_part` VARCHAR(255) NOT NULL DEFAULT '' AFTER `operation_vpps`;
ALTER TABLE `workmanship_craft_standard_operations`
  ADD COLUMN IF NOT EXISTS `match_tag` VARCHAR(64) NOT NULL DEFAULT '' AFTER `vpps_part`;
ALTER TABLE `workmanship_craft_standard_operations`
  ADD COLUMN IF NOT EXISTS `part_feed` BOOLEAN NOT NULL DEFAULT FALSE AFTER `match_tag`;
