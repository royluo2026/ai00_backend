-- Human-readable Fork name; project identity remains project_gid.
ALTER TABLE `workmanship_craft_bop_repositories`
  ADD COLUMN IF NOT EXISTS `display_name` VARCHAR(255) NULL AFTER `project_gid`;

ALTER TABLE `workmanship_craft_bop_fork_workflows`
  ADD COLUMN IF NOT EXISTS `target_name` VARCHAR(255) NULL AFTER `target_project_gid`;
