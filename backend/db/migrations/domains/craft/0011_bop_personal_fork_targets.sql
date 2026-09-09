CREATE TABLE IF NOT EXISTS `workmanship_craft_bop_personal_fork_targets` (
  `plan_gid` BIGINT UNSIGNED NOT NULL,
  `target_repository_gid` BIGINT UNSIGNED NOT NULL,
  `expected_target_slot` BIGINT UNSIGNED NOT NULL DEFAULT 0,
  `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`plan_gid`),
  KEY `idx_craft_personal_fork_target` (`target_repository_gid`),
  CONSTRAINT `fk_craft_personal_fork_plan` FOREIGN KEY (`plan_gid`) REFERENCES `workmanship_craft_bop_fork_plans` (`gid`),
  CONSTRAINT `fk_craft_personal_fork_repository` FOREIGN KEY (`target_repository_gid`) REFERENCES `workmanship_craft_bop_repositories` (`gid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
