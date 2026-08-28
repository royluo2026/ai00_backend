-- Live-upgrade-safe tenant/digest hardening for Base structural aggregates.
-- Nullable columns are added first, production data is backfilled, then writes fail closed.

ALTER TABLE workmanship_app_view_configs ADD COLUMN IF NOT EXISTS tenant_gid VARCHAR(128) NULL AFTER gid;
-- AI00: RESUMABLE BACKFILL
UPDATE workmanship_app_view_configs v
LEFT JOIN workmanship_auth_users u ON u.gid=v.owner_gid
SET v.tenant_gid=COALESCE(NULLIF(u.team_id,''),CONCAT('user:',v.owner_gid))
WHERE v.tenant_gid IS NULL OR v.tenant_gid='';
ALTER TABLE workmanship_app_view_configs MODIFY COLUMN tenant_gid VARCHAR(128) NOT NULL;
CREATE INDEX IF NOT EXISTS idx_base_saved_view_tenant ON workmanship_app_view_configs (tenant_gid, gid);

ALTER TABLE workmanship_base_saved_view_states ADD COLUMN IF NOT EXISTS tenant_gid VARCHAR(128) NULL FIRST;
-- AI00: RESUMABLE BACKFILL
UPDATE workmanship_base_saved_view_states s
JOIN workmanship_app_view_configs v ON v.gid=s.view_gid
SET s.tenant_gid=v.tenant_gid WHERE s.tenant_gid IS NULL OR s.tenant_gid='';
ALTER TABLE workmanship_base_saved_view_states MODIFY COLUMN tenant_gid VARCHAR(128) NOT NULL;
ALTER TABLE workmanship_base_saved_view_states DROP PRIMARY KEY, ADD PRIMARY KEY (tenant_gid,view_gid);

ALTER TABLE workmanship_base_saved_view_idempotency
  ADD COLUMN IF NOT EXISTS tenant_gid VARCHAR(128) NULL FIRST;
ALTER TABLE workmanship_base_saved_view_idempotency
  ADD COLUMN IF NOT EXISTS command_digest CHAR(64) NULL AFTER idempotency_key;
-- AI00: RESUMABLE BACKFILL
UPDATE workmanship_base_saved_view_idempotency
SET tenant_gid=CONCAT('user:',actor_gid),command_digest=SHA2(CONCAT('legacy:',actor_gid,':',operation,':',idempotency_key),256)
WHERE tenant_gid IS NULL OR tenant_gid='' OR command_digest IS NULL OR command_digest='';
ALTER TABLE workmanship_base_saved_view_idempotency
  MODIFY COLUMN tenant_gid VARCHAR(128) NOT NULL;
ALTER TABLE workmanship_base_saved_view_idempotency
  MODIFY COLUMN command_digest CHAR(64) NOT NULL;
ALTER TABLE workmanship_base_saved_view_idempotency
  DROP PRIMARY KEY, ADD PRIMARY KEY (tenant_gid,actor_gid,operation,idempotency_key);

ALTER TABLE workmanship_base_saved_view_audit_events ADD COLUMN IF NOT EXISTS tenant_gid VARCHAR(128) NULL AFTER gid;
-- AI00: RESUMABLE BACKFILL
UPDATE workmanship_base_saved_view_audit_events SET tenant_gid=CONCAT('user:',actor_gid)
WHERE tenant_gid IS NULL OR tenant_gid='';
ALTER TABLE workmanship_base_saved_view_audit_events MODIFY COLUMN tenant_gid VARCHAR(128) NOT NULL;

ALTER TABLE workmanship_base_self_annotations ADD COLUMN IF NOT EXISTS tenant_gid VARCHAR(128) NULL FIRST;
-- AI00: RESUMABLE BACKFILL
UPDATE workmanship_base_self_annotations a
LEFT JOIN workmanship_auth_users u ON u.gid=a.user_gid
SET a.tenant_gid=COALESCE(NULLIF(u.team_id,''),CONCAT('user:',a.user_gid))
WHERE a.tenant_gid IS NULL OR a.tenant_gid='';
ALTER TABLE workmanship_base_self_annotations MODIFY COLUMN tenant_gid VARCHAR(128) NOT NULL;
ALTER TABLE workmanship_base_self_annotations DROP PRIMARY KEY, ADD PRIMARY KEY (tenant_gid,item_gid,user_gid);

ALTER TABLE workmanship_base_self_annotation_states ADD COLUMN IF NOT EXISTS tenant_gid VARCHAR(128) NULL FIRST;
-- AI00: RESUMABLE BACKFILL
UPDATE workmanship_base_self_annotation_states s
JOIN workmanship_base_self_annotations a ON a.item_gid=s.item_gid AND a.user_gid=s.user_gid
SET s.tenant_gid=a.tenant_gid WHERE s.tenant_gid IS NULL OR s.tenant_gid='';
ALTER TABLE workmanship_base_self_annotation_states MODIFY COLUMN tenant_gid VARCHAR(128) NOT NULL;
ALTER TABLE workmanship_base_self_annotation_states DROP PRIMARY KEY, ADD PRIMARY KEY (tenant_gid,item_gid,user_gid);

ALTER TABLE workmanship_base_self_annotation_idempotency
  ADD COLUMN IF NOT EXISTS tenant_gid VARCHAR(128) NULL FIRST;
ALTER TABLE workmanship_base_self_annotation_idempotency
  ADD COLUMN IF NOT EXISTS command_digest CHAR(64) NULL AFTER idempotency_key;
-- AI00: RESUMABLE BACKFILL
UPDATE workmanship_base_self_annotation_idempotency
SET tenant_gid=CONCAT('user:',actor_gid),command_digest=SHA2(CONCAT('legacy:',actor_gid,':',operation,':',idempotency_key),256)
WHERE tenant_gid IS NULL OR tenant_gid='' OR command_digest IS NULL OR command_digest='';
ALTER TABLE workmanship_base_self_annotation_idempotency
  MODIFY COLUMN tenant_gid VARCHAR(128) NOT NULL;
ALTER TABLE workmanship_base_self_annotation_idempotency
  MODIFY COLUMN command_digest CHAR(64) NOT NULL;
ALTER TABLE workmanship_base_self_annotation_idempotency
  DROP PRIMARY KEY, ADD PRIMARY KEY (tenant_gid,actor_gid,operation,idempotency_key);

ALTER TABLE workmanship_base_self_annotation_audit_events ADD COLUMN IF NOT EXISTS tenant_gid VARCHAR(128) NULL AFTER gid;
-- AI00: RESUMABLE BACKFILL
UPDATE workmanship_base_self_annotation_audit_events SET tenant_gid=CONCAT('user:',actor_gid)
WHERE tenant_gid IS NULL OR tenant_gid='';
ALTER TABLE workmanship_base_self_annotation_audit_events MODIFY COLUMN tenant_gid VARCHAR(128) NOT NULL;

-- The artifact owner is the authoritative producer for typed annotation references.
-- AI00: RESUMABLE BACKFILL
INSERT INTO workmanship_base_attachment_references
  (attachment_gid,actor_gid,tenant_gid,media_type,display_name,size,checksum)
SELECT artifact_id,actor_id,tenant_id,media_type,SUBSTRING_INDEX(object_key,'/',-1),byte_size,CONCAT('sha256:',sha256)
FROM workmanship_base_artifacts
WHERE byte_size<=52428800 AND (media_type LIKE 'image/%' OR media_type='application/pdf' OR media_type LIKE 'text/%')
ON DUPLICATE KEY UPDATE media_type=VALUES(media_type),display_name=VALUES(display_name),size=VALUES(size),checksum=VALUES(checksum);
