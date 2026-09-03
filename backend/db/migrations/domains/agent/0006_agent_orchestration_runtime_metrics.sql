-- Agent-owned orchestration runtime projections and business KPI evidence.
-- Cross-domain identities remain soft versioned references by governance rule.

CREATE TABLE IF NOT EXISTS workmanship_agent_orch_workload_baselines (
    gid CHAR(36) NOT NULL,
    panorama_gid CHAR(36) NOT NULL,
    version_gid CHAR(36) NOT NULL,
    business_node_gid CHAR(36) NULL,
    task_key VARCHAR(128) NOT NULL,
    period_key VARCHAR(64) NOT NULL,
    annual_task_volume DECIMAL(18,4) NOT NULL,
    standard_manual_hours DECIMAL(18,4) NOT NULL,
    agent_share DECIMAL(7,6) NOT NULL,
    authorization_policy_ref VARCHAR(255) NOT NULL,
    mandatory_human TINYINT(1) NOT NULL,
    frozen_at DATETIME(6) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (gid),
    UNIQUE KEY uq_agent_orch_baseline_period (panorama_gid, version_gid, task_key, period_key),
    KEY idx_agent_orch_baseline_node (business_node_gid, task_key)
);

CREATE TABLE IF NOT EXISTS workmanship_agent_orch_runs (
    gid CHAR(36) NOT NULL,
    panorama_gid CHAR(36) NOT NULL,
    version_gid CHAR(36) NOT NULL,
    status VARCHAR(32) NOT NULL,
    frozen_context_json JSON NULL,
    started_at DATETIME(6) NOT NULL,
    finished_at DATETIME(6) NULL,
    started_by VARCHAR(128) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (gid),
    KEY idx_agent_orch_run_version (version_gid, started_at),
    KEY idx_agent_orch_run_panorama (panorama_gid, status, started_at)
);

CREATE TABLE IF NOT EXISTS workmanship_agent_orch_run_events (
    gid CHAR(36) NOT NULL,
    run_gid CHAR(36) NOT NULL,
    sequence_no BIGINT NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    item_gid CHAR(36) NULL,
    actor_type VARCHAR(32) NOT NULL,
    actor_gid VARCHAR(128) NULL,
    payload_json JSON NULL,
    capability_call_id VARCHAR(128) NULL,
    evidence_id VARCHAR(128) NULL,
    occurred_at DATETIME(6) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (gid),
    UNIQUE KEY uq_agent_orch_run_event_seq (run_gid, sequence_no)
);

CREATE TABLE IF NOT EXISTS workmanship_agent_orch_acceptance_facts (
    gid CHAR(36) NOT NULL,
    panorama_gid CHAR(36) NOT NULL,
    version_gid CHAR(36) NOT NULL,
    run_gid CHAR(36) NULL,
    business_node_gid CHAR(36) NULL,
    task_key VARCHAR(128) NOT NULL,
    period_key VARCHAR(64) NOT NULL,
    agent_share DECIMAL(7,6) NOT NULL,
    acceptance_pass_rate DECIMAL(7,6) NOT NULL,
    safety_gate_passed TINYINT(1) NOT NULL,
    acceptance_evidence_ref VARCHAR(255) NOT NULL,
    recorded_by VARCHAR(128) NOT NULL,
    recorded_at DATETIME(6) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (gid),
    KEY idx_agent_orch_acceptance_node (business_node_gid, task_key),
    KEY idx_agent_orch_acceptance_period (panorama_gid, period_key)
);

CREATE TABLE IF NOT EXISTS workmanship_agent_orch_metric_snapshots (
    gid CHAR(36) NOT NULL,
    panorama_gid CHAR(36) NOT NULL,
    version_gid CHAR(36) NOT NULL,
    period_key VARCHAR(64) NOT NULL,
    total_workload_hours DECIMAL(20,4) NOT NULL,
    effective_agent_workload_hours DECIMAL(20,4) NOT NULL,
    effective_intelligent_work_rate DECIMAL(9,8) NOT NULL,
    automated_workflow_count INT NOT NULL,
    total_workflow_count INT NOT NULL,
    automation_ratio DECIMAL(9,8) NOT NULL,
    evidence_json JSON NULL,
    calculated_at DATETIME(6) NOT NULL,
    created_at DATETIME(6) NOT NULL,
    PRIMARY KEY (gid),
    UNIQUE KEY uq_agent_orch_metric_period (panorama_gid, version_gid, period_key)
);
