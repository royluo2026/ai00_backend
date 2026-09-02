# Capability Governance Trust Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the Capability governance trust chain and regenerate truthful evidence for every stable Capability.

**Architecture:** Reuse the existing Catalog, parameterized acceptance suite, Gateway, governance store, and signed report. Remove self-attested evidence and make one fail-closed signed release decision consume all static and runtime inputs.

**Tech Stack:** Python 3, Pydantic, pytest, JSON Schema, existing Capability V2 modules.

**Spec:** `docs/superpowers/specs/2026-09-01-capability-governance-trust-closure-design.md`

## Global Constraints

- Preserve all existing worktree changes.
- Do not invent consumers, Provider bindings, test passes, approvals, or production evidence.
- Use TDD for every behavior change.
- Do not create one hand-written test file per Capability; use exact parameterized case identities.
- Missing authoritative persistence or signing remains a blocker.

---

### Task 1: Make Static Audit Fail Closed

**Files:** `backend/capability_v2/catalog_audit.py`, `backend/capability_v2/release_gate.py`, and their focused tests.

- [ ] Add failing tests showing every invalid count and failed test result blocks.
- [ ] Add explicit failed-evidence count and include every invalid counter in `passed`.
- [ ] Turn route-scan configuration failures into a structured blocking report.
- [ ] Run the focused audit and release-gate tests.

### Task 2: Separate Coverage Declarations from Test Results

**Files:** Catalog builder, acceptance manifest/runner, Catalog audit, and acceptance tests.

- [ ] Add failing tests rejecting Catalog-build-time `result=pass`.
- [ ] Generate exact mandatory coverage declarations from the acceptance manifest.
- [ ] Persist per-Capability case outcomes only in Test Run evidence.
- [ ] Validate test-node existence, source hash, Catalog release, code revision, and exact case coverage.

### Task 3: Bind Gateway Execution to the Release

**Files:** `backend/capability_v2/catalog.py`, `backend/capability_v2/gateway.py`, and focused tests.

- [ ] Add failing tests for old release selection, retired invocation, and Provider artifact drift.
- [ ] Enforce active/minimum release and lifecycle before Provider resolution.
- [ ] Resolve only a Provider whose artifact hash matches the Catalog release.

### Task 4: Bind Approval and Idempotency to Full Revision Identity

**Files:** `backend/capability_v2/reliability.py` and focused tests.

- [ ] Add failing cross-release and cross-Descriptor replay tests.
- [ ] Bind approval and idempotency scopes to release, Descriptor revision, Provider artifact, and payload hash.
- [ ] Validate stored replay output against the active output contract.

### Task 5: Enforce Runtime Policies

**Files:** Gateway, policies, durable audit, and focused tests.

- [ ] Add failing tests for deadline/timeout, auth freshness, unregistered consumer, strong write without a real transaction participant, and durable-audit failure.
- [ ] Implement the minimum shared Gateway enforcement needed to pass them.
- [ ] Validate consumer projection after projection.

### Task 6: Make the Signed Gate Authoritative

**Files:** governance service/release gate/bootstrap and focused governance tests.

- [ ] Add failing tests for memory fallback, missing persistent workflow/evidence ports, unverified signature, and stale static audit.
- [ ] Remove silent authoritative-store fallback.
- [ ] Require persisted readback and trusted-key verification before pass.
- [ ] Feed static audit and Capability acceptance Test Run into the same decision.

### Task 7: Rebuild and Verify

**Files:** generated Catalog, docs, acceptance manifest, Snapshot/Test Run/Release Report outputs.

- [ ] Regenerate Catalog and expected cases.
- [ ] Run all focused negative tests.
- [ ] Run offline strict acceptance and static gate.
- [ ] Run controlled persisted Snapshot/Test Run/signed gate when credentials are available.
- [ ] Publish exact remaining Findings; never convert unavailable external evidence into pass.
