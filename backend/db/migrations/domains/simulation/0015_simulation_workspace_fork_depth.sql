-- Persist the immutable copy boundary without rewriting the existing plan table.
CREATE TABLE IF NOT EXISTS `workmanship_sim_workspace_fork_plan_options` (
  `plan_gid` BIGINT UNSIGNED NOT NULL,
  `fork_depth` VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`plan_gid`),
  CONSTRAINT `fk_sim_workspace_fork_option_plan`
    FOREIGN KEY (`plan_gid`) REFERENCES `workmanship_sim_workspace_fork_plans` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
