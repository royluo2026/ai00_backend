ALTER TABLE `workmanship_sim_capture_steps`
  ADD COLUMN `plan_json` JSON NULL AFTER `expected_scene_hash`;

ALTER TABLE `workmanship_sim_materialization_runs`
  ADD COLUMN `plan_json` JSON NULL AFTER `plan_id`;

ALTER TABLE `workmanship_sim_document_snapshot_requests`
  ADD COLUMN `plan_json` JSON NULL AFTER `plan_id`,
  ADD COLUMN `dispatched_at` DATETIME(6) NULL AFTER `plan_json`;
