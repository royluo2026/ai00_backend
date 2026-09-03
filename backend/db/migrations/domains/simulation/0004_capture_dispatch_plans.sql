ALTER TABLE `workmanship_sim_capture_steps`
  ADD COLUMN IF NOT EXISTS `plan_json` JSON NULL AFTER `expected_scene_hash`;

ALTER TABLE `workmanship_sim_materialization_runs`
  ADD COLUMN IF NOT EXISTS `plan_json` JSON NULL AFTER `plan_id`;

ALTER TABLE `workmanship_sim_document_snapshot_requests`
  ADD COLUMN IF NOT EXISTS `plan_json` JSON NULL AFTER `plan_id`,
  ADD COLUMN IF NOT EXISTS `dispatched_at` DATETIME(6) NULL AFTER `plan_json`;
