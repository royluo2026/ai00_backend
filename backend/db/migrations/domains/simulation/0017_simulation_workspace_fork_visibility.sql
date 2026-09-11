-- Keep the requested private/shared scope bound to the immutable Fork plan.
ALTER TABLE `workmanship_sim_workspace_fork_plan_options`
  ADD COLUMN IF NOT EXISTS `visibility` VARCHAR(16) NOT NULL DEFAULT 'private' AFTER `fork_depth`;
