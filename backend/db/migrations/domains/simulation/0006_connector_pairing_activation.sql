ALTER TABLE `workmanship_sim_connector_pairings`
  ADD COLUMN `activation_challenge_hash` CHAR(64) NULL AFTER `credential_envelope_hash`,
  ADD COLUMN `activation_status` VARCHAR(32) NOT NULL DEFAULT 'not_issued' AFTER `activation_challenge_hash`,
  ADD COLUMN `activated_at` DATETIME(6) NULL AFTER `completed_at`;

ALTER TABLE `workmanship_sim_connector_bindings`
  ADD COLUMN `activated_at` DATETIME(6) NULL AFTER `last_seen_at`;
