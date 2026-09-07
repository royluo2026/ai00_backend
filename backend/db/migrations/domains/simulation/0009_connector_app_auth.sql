-- Authentication data stays separate from legacy v1 connector bindings.
ALTER TABLE `workmanship_sim_connector_runtime_devices`
  ADD COLUMN IF NOT EXISTS `device_credential_hash` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL CHECK (`device_credential_hash` IS NULL OR LENGTH(`device_credential_hash`) = 64);
ALTER TABLE `workmanship_sim_connector_runtime_devices`
  ADD COLUMN IF NOT EXISTS `runtime_type` VARCHAR(32) NOT NULL DEFAULT 'electron' CHECK (`runtime_type` = 'electron');
ALTER TABLE `workmanship_sim_connector_runtime_devices`
  ADD COLUMN IF NOT EXISTS `heartbeat_at` DATETIME(6) NULL;
ALTER TABLE `workmanship_sim_connector_app_pairings`
  ADD COLUMN IF NOT EXISTS `signing_challenge_hash` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NULL;
ALTER TABLE `workmanship_sim_connector_app_pairings`
  ADD COLUMN IF NOT EXISTS `challenge_expires_at` DATETIME(6) NULL;
ALTER TABLE `workmanship_sim_connector_app_pairings`
  ADD COLUMN IF NOT EXISTS `challenge_consumed_at` DATETIME(6) NULL;
ALTER TABLE `workmanship_sim_connector_app_pairings`
  ADD COLUMN IF NOT EXISTS `runtime_type` VARCHAR(32) NOT NULL DEFAULT 'electron' CHECK (`runtime_type` = 'electron');

CREATE TABLE IF NOT EXISTS `workmanship_sim_connector_runtime_challenges` (
  `challenge_hash` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
  `protocol` VARCHAR(64) NOT NULL,
  `device_id` VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `runtime_generation` BIGINT NOT NULL,
  `runtime_instance_id` VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `runtime_type` VARCHAR(32) NOT NULL,
  `device_key_id` VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `plan_id` VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin NULL,
  `expires_at` DATETIME(6) NOT NULL,
  `consumed_at` DATETIME(6) NULL,
  KEY `idx_sim_runtime_challenge_device` (`device_id`,`expires_at`),
  CHECK (`protocol` = 'ai00.connector.execution-plan.v2'),
  CHECK (`runtime_generation` >= 1),
  CHECK (`runtime_type` = 'electron')
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
ALTER TABLE `workmanship_sim_connector_runtime_devices`
  ADD COLUMN IF NOT EXISTS `takeover_instance_id` VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin NULL;
