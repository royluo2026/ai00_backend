-- Complete the Craft rule identity contract across legacy and governed schemas.
-- Existing owner identity is preserved; no team scope is inferred.

ALTER TABLE workmanship_know_craft_rules
  ADD COLUMN IF NOT EXISTS creator_gid CHAR(36) NULL AFTER owner_user_gid;

-- AI00: RESUMABLE BACKFILL
UPDATE workmanship_know_craft_rules
SET creator_gid=owner_user_gid
WHERE (creator_gid IS NULL OR creator_gid='')
  AND owner_user_gid IS NOT NULL AND owner_user_gid<>'';

-- AI00: RESUMABLE BACKFILL
UPDATE workmanship_know_craft_rules
SET owner_user_gid=creator_gid
WHERE (owner_user_gid IS NULL OR owner_user_gid='')
  AND creator_gid IS NOT NULL AND creator_gid<>'';
