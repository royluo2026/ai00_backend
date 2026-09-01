# Production Database Connection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the database settings connection check production-safe, diagnosable, and consistent with Capability V2 domain database isolation.

**Architecture:** Keep the existing three Base capabilities and the current Gateway route. Harden the Base provider at the connection boundary, keep production activation in deployment-owned environment variables, and make the web form an explicitly read-only connectivity check with no test-environment defaults.

**Tech Stack:** Python 3, PyMySQL, pytest, vanilla JavaScript, Node.js/jsdom test runner.

**Spec:** `docs/superpowers/specs/2026-09-01-production-database-connection-design.md`

## Global Constraints

- Production credentials must not be logged, returned, committed, or stored by browser code.
- The connection test may execute only `SELECT 1 AS ok`.
- Explicit `ENV_FILE` configuration remains authoritative.
- Domain runtime connections remain owned by `AI00_*_DB_URL`; DDL credentials remain outside this UI.
- Existing uncommitted changes in both repositories must be preserved.
- No new dependency is permitted.

---

### Task 1: Harden the Base database capabilities

**Files:**
- Modify: `backend/tests/test_base_runtime_database_capabilities.py`
- Modify: `backend/base/runtime_database_config.py`

**Interfaces:**
- Consumes: existing `base.runtime.database_config.get@1`, `base.runtime.database_config.change.apply@1`, and `base.runtime.database_connection.test@1` schemas.
- Produces: `test_database_connection(payload, context) -> {"connected": bool, "error_code"?: str}` using existing output fields; `save_database_config` returns `saved: false` under deployment-managed startup.

- [ ] **Step 1: Write failing backend tests**

Add focused tests proving:

```python
def test_connection_test_rejects_missing_password_without_connecting(monkeypatch):
    monkeypatch.setattr(runtime_database_config, "load_system_json", lambda: {})
    monkeypatch.setattr(runtime_database_config.pymysql, "connect", lambda **_: pytest.fail("must not connect"))
    result = runtime_database_config.test_database_connection(complete_payload(password=""), object())
    assert result == {"connected": False, "error_code": "password_required"}

@pytest.mark.parametrize((error, expected), [
    (pymysql.err.OperationalError(1045, "secret raw message"), "authentication_failed"),
    (pymysql.err.OperationalError(1049, "secret raw message"), "database_not_found"),
    (pymysql.err.OperationalError(2003, "secret raw message"), "network_unreachable"),
    (pymysql.err.OperationalError(2026, "secret raw message"), "tls_or_server_config_failed"),
])
def test_connection_test_returns_sanitized_error_codes(monkeypatch, error, expected):
    monkeypatch.setattr(runtime_database_config.pymysql, "connect", lambda **_: (_ for _ in ()).throw(error))
    result = runtime_database_config.test_database_connection(complete_payload(), object())
    assert result == {"connected": False, "error_code": expected}
    assert "secret raw message" not in str(result)

def test_deployment_managed_runtime_refuses_browser_save(monkeypatch):
    monkeypatch.setenv("ENV_FILE", "runtime.env")
    result = runtime_database_config.save_database_config(complete_payload(), object())
    assert result == {"saved": False, "password_configured": False}
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m pytest backend\tests\test_base_runtime_database_capabilities.py -q
```

Expected: the new missing-password, sanitized-mapping, and deployment-managed-save tests fail for the intended missing behavior.

- [ ] **Step 3: Implement the minimal provider hardening**

In `runtime_database_config.py`:

- Reject save when `os.getenv("ENV_FILE", "").strip()` is non-empty.
- Resolve the submitted/saved password before connecting and return `password_required` without calling PyMySQL when none exists.
- Map only known numeric PyMySQL error codes to the stable safe categories; return `connection_failed` for all unknown exceptions.
- Keep `SELECT 1 AS ok`, timeouts, and guaranteed close unchanged.

- [ ] **Step 4: Run backend tests and verify GREEN**

Run:

```powershell
python -m pytest backend\tests\test_base_runtime_database_capabilities.py -q
```

Expected: all tests pass and no raw exception text appears.

- [ ] **Step 5: Commit the backend behavior**

```powershell
git add -- backend/base/runtime_database_config.py backend/tests/test_base_runtime_database_capabilities.py
git commit -m "fix: harden governed database connection checks" -- backend/base/runtime_database_config.py backend/tests/test_base_runtime_database_capabilities.py
```

### Task 2: Make the web settings flow truthful and actionable

**Files:**
- Modify: `E:/Projects/ai00/workmanship-web/web/settings/index.html`
- Modify: `E:/Projects/ai00/workmanship-web/web/settings/settings.js`
- Modify: `E:/Projects/ai00/workmanship-web/web/tests/run_tests.js`

**Interfaces:**
- Consumes: existing safe `error_code` from `base.runtime.database_connection.test@1` and `saved` from `base.runtime.database_config.change.apply@1`.
- Produces: complete-field validation, Chinese diagnostic messages, empty initial fields, and browser-mode save disablement.

- [ ] **Step 1: Write failing web safety assertions**

Extend the existing `生产数据库配置全部通过 Base capability 治理` test to require:

```javascript
if (html.includes('value="sam-bdmsdb01-test.chj.cloud"')) throw new Error('仍预填测试主机');
if (src.includes("d.host || 'sam-bdmsdb01-test.chj.cloud'")) throw new Error('仍回退测试主机');
for (const code of ['password_required', 'authentication_failed', 'database_not_found', 'network_unreachable', 'tls_or_server_config_failed']) {
  if (!src.includes(code)) throw new Error(`缺少脱敏错误映射 ${code}`);
}
if (!src.includes("if (!window.electronAPI)")) throw new Error('Web 部署模式未禁止保存数据库配置');
```

Also assert that the settings copy contains `只读连接检测` and `AI00_*_DB_URL`.

- [ ] **Step 2: Run the web test and verify RED**

Run:

```powershell
node web\tests\run_tests.js
```

Expected: the database-settings safety assertion fails because test defaults and diagnostics are missing.

- [ ] **Step 3: Implement the minimal web changes**

- Remove test host, user, and database `value` attributes and fallback assignments.
- Keep port `2883` only as an OceanBase-friendly placeholder/default number, not an environment identity.
- Add a small error-code-to-Chinese-message map in `settings.js`.
- Validate host, port, user, database, and password-or-saved-password before invoking the capability.
- Disable `保存配置` when `window.electronAPI` is absent and show deployment-owned guidance.
- Change the heading/help copy from “配置后启用云同步” to “只读连接检测”; state that activation uses `USERS_DB_URL` and domain `AI00_*_DB_URL` followed by restart.

- [ ] **Step 4: Run the web test and verify GREEN**

Run:

```powershell
node web\tests\run_tests.js
node --check web\settings\settings.js
```

Expected: both commands exit zero.

- [ ] **Step 5: Commit the web behavior**

```powershell
git add -- web/settings/index.html web/settings/settings.js web/tests/run_tests.js
git commit -m "fix: make database connection settings production safe" -- web/settings/index.html web/settings/settings.js web/tests/run_tests.js
```

### Task 3: Run governed regression and local UI verification

**Files:**
- Verify only: backend and web files from Tasks 1-2.

**Interfaces:**
- Consumes: the hardened Base provider and revised settings form.
- Produces: evidence that Capability governance, contracts, and UI behavior remain intact.

- [ ] **Step 1: Run focused backend and contract regression**

```powershell
python -m pytest backend\tests\test_base_runtime_database_capabilities.py backend\tests\test_capability_v2_consumer_routes.py -q
python backend\scripts\build_capability_catalog.py --check
```

Expected: all tests pass and the catalog check reports no drift.

- [ ] **Step 2: Run focused web regression**

```powershell
node web\tests\run_tests.js
node --check web\settings\settings.js
```

Expected: both commands exit zero.

- [ ] **Step 3: Restart the local backend and refresh the existing Vite page**

Start the backend with the existing local test `ENV_FILE`, refresh the settings iframe, and verify:

- no test host/user/database is prefilled;
- save is disabled in browser mode;
- an incomplete test is rejected locally;
- no database request is emitted for incomplete input;
- the page identifies the operation as read-only and deployment-managed.

- [ ] **Step 4: Record the exact verification results**

Report command exit codes and the manual UI observations. Do not claim production connectivity because no production credential was used.
