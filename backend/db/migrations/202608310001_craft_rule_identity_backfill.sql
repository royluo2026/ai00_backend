-- Preserve only derivable Craft rule identity; never invent a team scope.
-- AI00: RESUMABLE BACKFILL
UPDATE workmanship_know_craft_rules
SET owner_user_gid = creator_gid
WHERE (owner_user_gid IS NULL OR owner_user_gid = '')
  AND creator_gid IS NOT NULL AND creator_gid <> '';

-- AI00: RESUMABLE BACKFILL
UPDATE workmanship_know_craft_rules
SET rule_definition = JSON_SET(COALESCE(rule_definition, JSON_OBJECT()), '$._revision', 1)
WHERE JSON_EXTRACT(COALESCE(rule_definition, JSON_OBJECT()), '$._revision') IS NULL;
