CREATE TABLE IF NOT EXISTS workmanship_base_capability_runtime_fence (
  fence_id BIGINT NOT NULL,
  PRIMARY KEY (fence_id)
);
-- AI00: RESUMABLE BACKFILL - the singleton is a lock row, not an approval.
INSERT INTO workmanship_base_capability_runtime_fence (fence_id)
VALUES (1) ON DUPLICATE KEY UPDATE fence_id=fence_id;
