ALTER TABLE `workmanship_sim_workspace_hierarchies`
  ADD COLUMN IF NOT EXISTS `source_refs_json` JSON NULL AFTER `source_bop_content_hash`;
