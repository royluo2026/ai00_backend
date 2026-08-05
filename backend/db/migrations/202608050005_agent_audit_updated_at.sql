-- Keep Agent audit rows compatible with the declared runtime contract.
ALTER TABLE workmanship_app_ai_audit_logs
    ADD COLUMN IF NOT EXISTS updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6);
