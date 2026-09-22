-- Append-only issuance evidence; no backfill invents provenance for old grants.
CREATE TABLE IF NOT EXISTS `workmanship_sim_viewer_grant_evidence` (
  `grant_id` VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin PRIMARY KEY,
  `authorization_operation_id` VARCHAR(256) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `proof_digest` CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `proof_json` JSON NOT NULL,
  `created_at` DATETIME(6) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
