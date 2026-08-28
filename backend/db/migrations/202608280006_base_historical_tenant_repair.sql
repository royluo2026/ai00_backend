-- Reconcile historical 0005 replay/audit rows without mutating migration history.
-- The versioned ledger is the explicit completion marker: on a manual replay after
-- success, every statement is a no-op; after a partial failure, each assignment is
-- deterministic and can resume safely.

-- AI00: RESUMABLE BACKFILL
UPDATE workmanship_base_saved_view_idempotency i
LEFT JOIN workmanship_app_view_configs v ON v.gid=i.view_gid
LEFT JOIN workmanship_auth_users u ON u.gid=i.actor_gid
SET i.tenant_gid=COALESCE(
  NULLIF(v.tenant_gid,''),
  NULLIF(u.team_id,''),
  CASE WHEN u.gid IS NOT NULL THEN CONCAT('user:',i.actor_gid)
       ELSE CONCAT('legacy-unresolved:',SHA2(CONCAT_WS(':',i.actor_gid,i.operation,i.idempotency_key),256)) END
)
WHERE (i.tenant_gid IS NULL OR i.tenant_gid='' OR i.tenant_gid LIKE 'user:%')
  AND NOT EXISTS (
    SELECT 1 FROM workmanship_base_schema_migrations m
    WHERE m.migration_id='202608280006' AND m.status='applied'
  );

-- AI00: RESUMABLE BACKFILL
UPDATE workmanship_base_saved_view_audit_events e
LEFT JOIN workmanship_app_view_configs v ON v.gid=e.view_gid
LEFT JOIN workmanship_auth_users u ON u.gid=e.actor_gid
SET e.tenant_gid=COALESCE(
  NULLIF(v.tenant_gid,''),
  NULLIF(u.team_id,''),
  CASE WHEN u.gid IS NOT NULL THEN CONCAT('user:',e.actor_gid)
       ELSE CONCAT('legacy-unresolved:',SHA2(e.gid,256)) END
)
WHERE (e.tenant_gid IS NULL OR e.tenant_gid='' OR e.tenant_gid LIKE 'user:%')
  AND NOT EXISTS (
    SELECT 1 FROM workmanship_base_schema_migrations m
    WHERE m.migration_id='202608280006' AND m.status='applied'
  );

-- AI00: RESUMABLE BACKFILL
UPDATE workmanship_base_self_annotation_idempotency i
LEFT JOIN workmanship_base_self_annotations a
  ON a.item_gid=i.item_gid AND a.user_gid=i.actor_gid
LEFT JOIN workmanship_auth_users u ON u.gid=i.actor_gid
SET i.tenant_gid=COALESCE(
  NULLIF(a.tenant_gid,''),
  NULLIF(u.team_id,''),
  CASE WHEN u.gid IS NOT NULL THEN CONCAT('user:',i.actor_gid)
       ELSE CONCAT('legacy-unresolved:',SHA2(CONCAT_WS(':',i.actor_gid,i.operation,i.idempotency_key),256)) END
)
WHERE (i.tenant_gid IS NULL OR i.tenant_gid='' OR i.tenant_gid LIKE 'user:%')
  AND NOT EXISTS (
    SELECT 1 FROM workmanship_base_schema_migrations m
    WHERE m.migration_id='202608280006' AND m.status='applied'
  );

-- AI00: RESUMABLE BACKFILL
UPDATE workmanship_base_self_annotation_audit_events e
LEFT JOIN workmanship_base_self_annotations a
  ON a.item_gid=e.item_gid AND a.user_gid=e.actor_gid
LEFT JOIN workmanship_auth_users u ON u.gid=e.actor_gid
SET e.tenant_gid=COALESCE(
  NULLIF(a.tenant_gid,''),
  NULLIF(u.team_id,''),
  CASE WHEN u.gid IS NOT NULL THEN CONCAT('user:',e.actor_gid)
       ELSE CONCAT('legacy-unresolved:',SHA2(e.gid,256)) END
)
WHERE (e.tenant_gid IS NULL OR e.tenant_gid='' OR e.tenant_gid LIKE 'user:%')
  AND NOT EXISTS (
    SELECT 1 FROM workmanship_base_schema_migrations m
    WHERE m.migration_id='202608280006' AND m.status='applied'
  );
