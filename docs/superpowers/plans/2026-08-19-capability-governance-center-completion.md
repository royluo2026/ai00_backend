# Capability Governance Center Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将治理中心六个页面全部接通真实治理能力，补齐提案、健康、审计和发布证据链，并完成测试环境部署验收。

**Architecture:** 保留现有 Vanilla JS + Capability Gateway。后端扩展闭合只读契约和 Service/Provider 适配器，前端按 section 拆分加载与状态模型；所有状态都由服务端证据驱动，依赖缺失 fail-closed。

**Tech Stack:** Python/FastAPI service, OceanBase-compatible SQL store, Vanilla JavaScript, existing governance CSS, pytest, Node test runner.

**Spec:** `docs/superpowers/specs/2026-08-19-capability-governance-center-completion-design.md`

## Global Constraints

- 只部署 `test-governance`，不改生产、不推送远端、不修改旧服务。
- 不增加跨领域业务 SQL、插件业务表或特殊读取 API。
- 所有查询默认最多 50、最大 200；所有写操作使用权限检查、确认和幂等键。
- 不输出密码、Token、Cookie、数据库 URL 或内部异常堆栈。
- 每项实现先写失败测试，再写最小实现，再运行定向测试。

### Task 1: 固化契约和状态模型

**Files:**
- Modify: `backend/capability_governance_test/contracts.py`
- Modify: `backend/capability_governance_test/models.py`
- Modify: `backend/capability_governance_test/provider.py`
- Test: `backend/tests/test_capability_governance_provider.py`

**Interfaces:**
- Produces closed schemas and DTOs for proposal search, health summary, and audit search.

- [ ] **Step 1: Write failing contract tests**

```python
def test_new_read_capabilities_have_closed_input_and_output_schemas():
    assert "base.capability_proposal.search@1" in READ_IDS
    assert "base.capability_health.get@1" in READ_IDS
    assert "base.capability_audit.search@1" in READ_IDS
    assert set(PROPOSAL_SEARCH_INPUT) == {"query", "domain", "stage", "limit", "cursor"}
```

- [ ] **Step 2: Run `python -m pytest backend/tests/test_capability_governance_provider.py -q -p no:cacheprovider` and verify failure.**
- [ ] **Step 3: Add contracts, bounded DTOs, and provider registration without exposing internal fields.**
- [ ] **Step 4: Run the focused provider tests and verify pass.**
- [ ] **Step 5: Commit `feat: add governance query capability contracts`.**

### Task 2: Add Service read handlers and fail-closed release evidence

**Files:**
- Modify: `backend/capability_governance_test/service.py`
- Modify: `backend/capability_governance_test/bootstrap.py`
- Modify: `backend/capability_governance_test/store.py`
- Test: `backend/tests/test_capability_governance_service_workflow.py`
- Test: `backend/tests/test_capability_governance_store.py`

**Interfaces:**
- `base_capability_proposal_search(input, identity) -> dict`
- `base_capability_health_get(input, identity) -> dict`
- `base_capability_audit_search(input, identity) -> dict`

- [ ] **Step 1: Add red tests for proposal filtering, health status calculation, audit redaction, and dependency-unavailable behavior.**
- [ ] **Step 2: Run the two focused test files and confirm failure.**
- [ ] **Step 3: Implement bounded handlers using workflow/audit/evidence ports; return structured dependency errors when ports are absent.**
- [ ] **Step 4: Make release evaluation load authoritative evidence only and reject caller-supplied pass fields.**
- [ ] **Step 5: Run focused tests and compile the changed modules.**
- [ ] **Step 6: Commit `feat: expose governance queries and authoritative release evidence`.**

### Task 3: Wire Gateway/provider and permission matrix

**Files:**
- Modify: `backend/capability_governance_test/provider.py`
- Modify: `backend/capability_governance_test/contracts.py`
- Modify: `backend/tests/test_capability_governance_provider.py`
- Modify: `backend/tests/test_capability_governance_service_workflow.py`

- [ ] **Step 1: Add tests for ordinary-member read access and management-action denial.**
- [ ] **Step 2: Run tests and confirm the new capability IDs are rejected or missing.**
- [ ] **Step 3: Register handlers, closed schemas, and read-only scopes; keep proposal/review/release writes admin-only.**
- [ ] **Step 4: Run focused provider/service tests and commit `fix: enforce governance query permissions`.**

### Task 4: Extend frontend API and pure state model

**Files:**
- Modify: `E:/Projects/ai00/workmanship-web/web/admin/capability_governance/governance_api.js`
- Modify: `E:/Projects/ai00/workmanship-web/web/admin/capability_governance/governance_model.js`
- Test: `E:/Projects/ai00/workmanship-web/web/admin/capability_governance/governance_api.test.js`
- Test: `E:/Projects/ai00/workmanship-web/web/admin/capability_governance/governance_controller.test.js`

**Interfaces:**
- `loadProposals(filters)`
- `loadHealth(domains)`
- `loadAudit(filters)`
- `loadSection(section, filters)`
- `reduceSectionResult(state, section, result, requestId)`

- [ ] **Step 1: Add failing tests for new API calls, stale-data retention, request-generation cancellation, and clearable filters.**
- [ ] **Step 2: Run `node web/tests/run_tests.js` and verify red tests.**
- [ ] **Step 3: Implement API methods with `unwrapInvocation`, bounded query params, one retry, and stale fallback.**
- [ ] **Step 4: Extend pure model state and reducers; ensure old responses cannot overwrite newer requests.**
- [ ] **Step 5: Run the governance JS tests and commit `feat: add governance section data model`.**

### Task 5: Complete controller views and interactions

**Files:**
- Modify: `E:/Projects/ai00/workmanship-web/web/admin/capability_governance/governance_controller.js`
- Modify: `E:/Projects/ai00/workmanship-web/web/admin/capability_governance/index.html`
- Modify: `E:/Projects/ai00/workmanship-web/web/admin/capability_governance/governance.css`
- Test: `E:/Projects/ai00/workmanship-web/web/admin/capability_governance/governance_controller.test.js`

- [ ] **Step 1: Add failing controller tests for each section's loading/empty/error states, filter clear/replace, drawer details, and no native dialogs.**
- [ ] **Step 2: Run the controller test file and confirm failure.**
- [ ] **Step 3: Add per-section loaders and renderers for overview, findings, changes, health, release, and audit.**
- [ ] **Step 4: Add application confirmation dialog, toast, busy-state suppression, and permission-aware actions.**
- [ ] **Step 5: Add dark-theme cards/tables/drawers and explicit `unverified`/`dependency unavailable` styling.**
- [ ] **Step 6: Run all frontend tests and commit `feat: complete governance center views`.**

### Task 6: Build, synchronize, and deploy test frontend

**Files:**
- Generated: backend `dist/` assets from the frontend build only.
- Modify: none outside generated build output.

- [ ] **Step 1: Run `npm test` in `E:/Projects/ai00/workmanship-web` and fix all failures.**
- [ ] **Step 2: Run `npm run build:web` and verify the governance assets exist.**
- [ ] **Step 3: Copy only generated governance-related assets into backend `dist/`, preserving unrelated user files.**
- [ ] **Step 4: Run `python backend/scripts/check_frontend_deployment.py --base-url http://127.0.0.1:8094`.**
- [ ] **Step 5: Restart only `AI00Backend-CapabilityV2` with administrator approval if required.**
- [ ] **Step 6: Commit frontend source and deployment artifacts separately.**

### Task 7: End-to-end browser and backend acceptance

**Files:**
- Test/update: `backend/tests/test_capability_governance_acceptance.py`
- Documentation: `docs/governance/test-extension/capability-governance-center-acceptance.md`

- [ ] **Step 1: Run focused backend governance tests and full `python -m pytest -q`.**
- [ ] **Step 2: Verify authenticated administrator and ordinary-member views in the browser.**
- [ ] **Step 3: Verify each page loads real data or an explicit empty/dependency state; verify filters clear and replace.**
- [ ] **Step 4: Verify release gate cannot pass without authoritative evidence and audit entries are redacted.**
- [ ] **Step 5: Record URLs, report IDs, test commands, and any expected unavailable dependencies without recording secrets.**
- [ ] **Step 6: Commit `test: accept governance center end to end`.**
