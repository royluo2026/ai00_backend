-- Editable metadata for private/shared simulation environments.
ALTER TABLE `workmanship_sim_workspaces`
  ADD COLUMN IF NOT EXISTS `review_type` VARCHAR(32) NOT NULL DEFAULT 'other' AFTER `name`;
ALTER TABLE `workmanship_sim_workspaces`
  ADD COLUMN IF NOT EXISTS `version_label` VARCHAR(128) NOT NULL DEFAULT 'V1' AFTER `review_type`;
ALTER TABLE `workmanship_sim_workspaces`
  ADD COLUMN IF NOT EXISTS `visibility` VARCHAR(16) NOT NULL DEFAULT 'private' AFTER `status`;
ALTER TABLE `workmanship_sim_workspaces`
  ADD COLUMN IF NOT EXISTS `primary_project_gid` BIGINT UNSIGNED NULL AFTER `visibility`;

CREATE TABLE IF NOT EXISTS `workmanship_sim_workspace_projects` (
  `workspace_gid` BIGINT UNSIGNED NOT NULL,
  `project_gid` BIGINT UNSIGNED NOT NULL,
  `sort_order` INT UNSIGNED NOT NULL DEFAULT 0,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`workspace_gid`,`project_gid`),
  KEY `idx_sim_workspace_project` (`project_gid`,`workspace_gid`),
  CONSTRAINT `fk_sim_workspace_project_workspace`
    FOREIGN KEY (`workspace_gid`) REFERENCES `workmanship_sim_workspaces` (`gid`)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
