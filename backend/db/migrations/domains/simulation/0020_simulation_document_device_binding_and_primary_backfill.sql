-- Preserve the exact Connector device for device-bound model documents.
ALTER TABLE `workmanship_sim_vm_documents`
  ADD COLUMN IF NOT EXISTS `connector_device_id` VARCHAR(191) CHARACTER SET ascii COLLATE ascii_bin NULL AFTER `portability`;
CREATE INDEX IF NOT EXISTS `idx_sim_vm_document_device`
  ON `workmanship_sim_vm_documents` (`tenant_gid`,`connector_device_id`,`removed_at`);

-- AI00: RESUMABLE BACKFILL
-- Existing single-document workspaces predate document_role. Choose their oldest
-- active document only when no primary already exists; never replace an explicit primary.
UPDATE `workmanship_sim_vm_documents`
SET `document_role`='primary', `primary_slot`=1
WHERE `gid` IN (
  SELECT `primary_gid` FROM (
    SELECT MIN(`gid`) AS `primary_gid`
    FROM `workmanship_sim_vm_documents`
    WHERE `removed_at` IS NULL
    GROUP BY `workspace_gid`
    HAVING MAX(COALESCE(`primary_slot`,0))=0
  ) AS `oldest_without_primary`
);
