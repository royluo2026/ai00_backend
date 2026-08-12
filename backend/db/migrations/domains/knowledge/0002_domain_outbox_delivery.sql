ALTER TABLE workmanship_know_domain_outbox ADD COLUMN IF NOT EXISTS last_error TEXT NULL AFTER attempts;
