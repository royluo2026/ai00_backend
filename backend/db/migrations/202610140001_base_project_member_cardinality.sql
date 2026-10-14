-- Multiple ordinary members and line leaders are maintained as explicit sets.
-- Preserve existing data; remove historical one-person-per-role restrictions.
DROP INDEX IF EXISTS idx_pm_unique_global ON workmanship_auth_project_members;
DROP INDEX IF EXISTS idx_pm_unique_scoped ON workmanship_auth_project_members;
CREATE INDEX IF NOT EXISTS idx_pm_global ON workmanship_auth_project_members (project_gid, role(64));
CREATE INDEX IF NOT EXISTS idx_pm_scoped ON workmanship_auth_project_members (project_gid, role(64), scope_gid(191));
