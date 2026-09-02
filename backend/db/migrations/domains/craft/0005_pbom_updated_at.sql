-- Preserve the PBOM row revision timestamp required by governed BOP projections.
ALTER TABLE `workmanship_bop_pbom`
  ADD COLUMN IF NOT EXISTS `updated_at` DATETIME(6) NOT NULL
  DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6);
