-- Close the compatibility window opened by 0009.  Operators must backfill
-- existing rows with an approved project identity before this migration runs;
-- the NOT NULL change then makes NULL scope impossible at the database layer.

ALTER TABLE workmanship_agent_orch_panoramas
  MODIFY COLUMN project_gid VARCHAR(128) NOT NULL;
