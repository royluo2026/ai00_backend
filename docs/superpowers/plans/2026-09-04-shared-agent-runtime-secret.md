# Shared Agent Runtime Secret Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a local-test `super_admin` save one encrypted model credential shared by every XiaoRou user.

**Architecture:** A small Windows DPAPI store owns encryption and atomic persistence. The existing Agent config resolver prefers deployment environment variables and otherwise reads that store; the existing admin-config compatibility route performs the gated write and never returns the secret. The existing AI Settings page becomes editable only when the server reports enrollment enabled.

**Tech Stack:** Python stdlib (`ctypes`, `json`, `os`, `pathlib`, `tempfile`), FastAPI, vanilla HTML/JavaScript, Node test runner, pytest.

---

### Task 1: DPAPI runtime secret store

**Files:**
- Create: `plugins/agent/agent_backend/infrastructure/runtime_secret_store.py`
- Create: `plugins/agent/tests/test_runtime_secret_store.py`
- Modify: `.gitignore`

- [ ] **Step 1: Write the failing store test**

Create tests that inject `protect` and `unprotect` callables, save `{"api_key":"secret-value","model":"gpt-4o","api_base":""}`, assert the file does not contain `secret-value`, assert load returns the original mapping, and assert a failed replacement preserves the previous readable file.

- [ ] **Step 2: Run the test and verify RED**

Run: `.venv/Scripts/python.exe -m pytest plugins/agent/tests/test_runtime_secret_store.py -q`
Expected: FAIL because `runtime_secret_store` does not exist.

- [ ] **Step 3: Implement the minimal store**

Implement `RuntimeSecretStore(path, protect=None, unprotect=None)` with `load()` and `save(config)`. Default protectors call Windows `CryptProtectData`/`CryptUnprotectData` through `ctypes`; `save` writes a same-directory temporary file and calls `os.replace`. Add `/.runtime/` to `.gitignore`.

- [ ] **Step 4: Run the test and verify GREEN**

Run: `.venv/Scripts/python.exe -m pytest plugins/agent/tests/test_runtime_secret_store.py -q`
Expected: PASS.

### Task 2: Runtime resolution and guarded save route

**Files:**
- Modify: `plugins/agent/agent_backend/routers/ai_chat.py`
- Modify: `plugins/agent/agent_backend/infrastructure/repository.py`
- Modify: `backend/tests/test_agent_runtime_config_capability_boundary.py`
- Modify: `plugins/agent/tests/test_catalog_tool_e2e.py`

- [ ] **Step 1: Write failing backend tests**

Test that environment values override the encrypted store, the store supplies config when environment keys are absent, runtime metadata reports `source="local_secret"` and never returns `api_key`, and POST save rejects disabled/non-loopback requests while an enabled loopback `super_admin` call returns masked metadata only.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `.venv/Scripts/python.exe -m pytest plugins/agent/tests/test_runtime_secret_store.py backend/tests/test_agent_runtime_config_capability_boundary.py plugins/agent/tests/test_catalog_tool_e2e.py -q`
Expected: FAIL on missing local-secret resolution and save behavior.

- [ ] **Step 3: Implement the route and resolver**

Add `_runtime_secret_store()`, resolve environment first and encrypted store second, and change `save_admin_config` to accept `Request`. Require `ALLOW_LOCAL_RUNTIME_SECRET_ADMIN=1`, `request.client.host` in `{"127.0.0.1","::1"}`, non-empty model, and a non-empty key when no saved key exists. Preserve the current key when the submitted key is empty. Return only `source`, `model`, `has_key`, `key_preview`, `is_admin`, `api_base`, and `secret_admin_enabled`.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the Step 2 command.
Expected: PASS.

### Task 3: Editable administrator UI

**Files:**
- Modify: `workmanship-web/packages/agent-plugin/web/automation_hub/ai_settings.html`
- Modify: `workmanship-web/scripts/test_agent_ai_settings.js`
- Modify: `workmanship-web/package.json`

- [ ] **Step 1: Write the failing browser-DOM test**

Assert that `secret_admin_enabled=true` enables model/base/key controls and a Save button, saving POSTs `{model, api_base, api_key}`, an empty key preserves the existing credential, and non-admin/disabled responses keep the form read-only.

- [ ] **Step 2: Run the test and verify RED**

Run: `npm run test:agent-ai-settings`
Expected: FAIL because the page has no save behavior.

- [ ] **Step 3: Implement the minimal UI**

Reuse the current form and `_cf`; add one Save button, enable inputs only for an authorized enabled response, clear the masked key into an empty replacement field, POST the form, then refresh the masked preview. Do not store the key in browser storage or log it.

- [ ] **Step 4: Run the test and verify GREEN**

Run: `npm run test:agent-ai-settings`
Expected: PASS.

### Task 4: Build, freeze, and runtime verification

**Files:**
- Modify: `backend/capability_v2/official_domains.json`
- Modify generated backend files under `dist/`
- Modify local ignored file: `backend/.env`

- [ ] **Step 1: Enable the local test control**

Add `ALLOW_LOCAL_RUNTIME_SECRET_ADMIN=1` to the ignored `backend/.env`; do not add a model key there.

- [ ] **Step 2: Run complete relevant checks**

Run backend focused tests, frontend `npm test`, and `npm run build:web:test-governance`.
Expected: all PASS.

- [ ] **Step 3: Copy the built frontend and freeze the Provider hash**

Copy the built AI Settings and workbench artifacts into backend `dist`, then run `.venv/Scripts/python.exe backend/scripts/freeze_official_domains.py` followed by the same command with `--check`.
Expected: identical printed manifest digest.

- [ ] **Step 4: Restart and verify**

Restart `scripts/run_debug_backend.py --port 8080`, verify `/health`, confirm logs show `TABLE_PREFIX active: ... test_workmanship_`, save a real key through AI Settings, run Test Connection, and send `请只回复：小柔连接正常` to XiaoRou.
Expected: XiaoRou replies `小柔连接正常`; if it does not, continue debugging from the redacted runtime error.
