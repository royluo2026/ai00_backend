-- Preserve signed outcomes while closing exactly one human-reviewed plan.
-- Add first: the old check continues protecting the table if execution stops here.
-- AI00: RESUMABLE ADD EXPANDED STATUS CHECK
ALTER TABLE workmanship_sim_connector_runtime_plans
ADD CONSTRAINT sim_runtime_plan_status_recovery
CHECK (status IN ('queued','leased','executing','succeeded','failed_without_effect','outcome_unknown','manual_review_required','expired','cancelled'));

-- The runner resolves this placeholder only after verifying the expanded check.
-- AI00: RESUMABLE RETIRE OLD STATUS CHECK
ALTER TABLE workmanship_sim_connector_runtime_plans DROP CHECK sim_runtime_plan_status_pre_recovery;
