-- Keep imported source tree depth (level) separate from the AI00 semantic level.
ALTER TABLE `workmanship_craft_standard_operations`
  ADD COLUMN IF NOT EXISTS `ai00_level` INT NULL AFTER `level`;
