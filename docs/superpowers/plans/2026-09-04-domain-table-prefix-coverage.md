# Domain Table Prefix Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure every plugin-owned database connection rewrites `workmanship_*` SQL to `test_workmanship_*` when `TABLE_PREFIX=test_`.

**Architecture:** Extend the existing cursor wrapper with an idempotent connection wrapper. Apply that wrapper immediately after each plugin pool returns a connection; leave pool configuration, transactions, credentials, and repository SQL unchanged.

**Tech Stack:** Python 3.14, PyMySQL, DBUtils `PooledDB`, pytest.

---

### Task 1: Shared connection wrapper

**Files:**
- Modify: `backend/db/prefixed_cursor.py`
- Create: `backend/tests/test_domain_table_prefix_connections.py`

- [ ] **Step 1: Write the failing unit test**

```python
from backend.db.prefixed_cursor import wrap_connection
from backend.db.table_prefix import configure_table_prefix


class Cursor:
    def __init__(self):
        self.query = None

    def execute(self, query, args=None):
        self.query = query


class Connection:
    def __init__(self):
        self.created = []

    def cursor(self):
        cursor = Cursor()
        self.created.append(cursor)
        return cursor


def test_wrap_connection_rewrites_once():
    configure_table_prefix("test_")
    connection = Connection()
    assert wrap_connection(connection) is connection
    assert wrap_connection(connection) is connection
    cursor = connection.cursor()
    cursor.execute("SELECT * FROM workmanship_proj_projects")
    assert cursor._inner.query == "SELECT * FROM test_workmanship_proj_projects"
```

- [ ] **Step 2: Run the test and verify RED**

Run: `.venv/Scripts/python.exe -m pytest backend/tests/test_domain_table_prefix_connections.py::test_wrap_connection_rewrites_once -q`

Expected: FAIL because `wrap_connection` is not defined.

- [ ] **Step 3: Implement the minimal helper**

```python
def wrap_connection(connection):
    if getattr(connection, "_ai00_prefix_wrapped", False):
        return connection
    original_cursor = connection.cursor
    connection.cursor = lambda *args, **kwargs: wrap_cursor(original_cursor(*args, **kwargs))
    connection._ai00_prefix_wrapped = True
    return connection
```

- [ ] **Step 4: Run the focused test and verify GREEN**

Run: `.venv/Scripts/python.exe -m pytest backend/tests/test_domain_table_prefix_connections.py::test_wrap_connection_rewrites_once -q`

Expected: `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/db/prefixed_cursor.py backend/tests/test_domain_table_prefix_connections.py
git commit -m "fix(db): add idempotent prefixed connection wrapper"
```

### Task 2: Cover every plugin database boundary

**Files:**
- Modify: `plugins/agent/agent_backend/data/connection.py`
- Modify: `plugins/craft/craft_backend/data/connection.py`
- Modify: `plugins/device/device_backend/data/connection.py`
- Modify: `plugins/digital_model/digital_model_backend/data/connection.py`
- Modify: `plugins/factory/factory_backend/infrastructure/connection.py`
- Modify: `plugins/integration/integration_backend/data/connection.py`
- Modify: `plugins/knowledge/knowledge_backend/data/connection.py`
- Modify: `plugins/ontology/ontology_backend/infrastructure/connection.py`
- Modify: `plugins/project_management/project_management_backend/data/connection.py`
- Modify: `plugins/simulation/simulation_backend/data/connection.py`
- Test: `backend/tests/test_domain_table_prefix_connections.py`

- [ ] **Step 1: Write the failing coverage test**

```python
from pathlib import Path


CONNECTION_FILES = (
    "plugins/agent/agent_backend/data/connection.py",
    "plugins/craft/craft_backend/data/connection.py",
    "plugins/device/device_backend/data/connection.py",
    "plugins/digital_model/digital_model_backend/data/connection.py",
    "plugins/factory/factory_backend/infrastructure/connection.py",
    "plugins/integration/integration_backend/data/connection.py",
    "plugins/knowledge/knowledge_backend/data/connection.py",
    "plugins/ontology/ontology_backend/infrastructure/connection.py",
    "plugins/project_management/project_management_backend/data/connection.py",
    "plugins/simulation/simulation_backend/data/connection.py",
)


def test_plugin_database_connections_use_prefix_wrapper():
    root = Path(__file__).resolve().parents[2]
    for relative in CONNECTION_FILES:
        source = (root / relative).read_text(encoding="utf-8")
        assert "wrap_connection" in source, relative
```

- [ ] **Step 2: Run the coverage test and verify RED**

Run: `.venv/Scripts/python.exe -m pytest backend/tests/test_domain_table_prefix_connections.py::test_plugin_database_connections_use_prefix_wrapper -q`

Expected: FAIL naming the first unwrapped plugin connection file.

- [ ] **Step 3: Wrap each acquired connection**

In every listed file, import the shared helper:

```python
from backend.db.prefixed_cursor import wrap_connection
```

Replace every pool acquisition form:

```python
conn = _get_pool().connection()
```

with:

```python
conn = wrap_connection(_get_pool().connection())
```

For the persistent Agent connection, assign the wrapped result:

```python
self._connection = wrap_connection(_get_pool().connection())
```

- [ ] **Step 4: Run focused tests and verify GREEN**

Run: `.venv/Scripts/python.exe -m pytest backend/tests/test_domain_table_prefix_connections.py -q`

Expected: all tests pass.

- [ ] **Step 5: Run existing boundary tests**

Run: `.venv/Scripts/python.exe -m pytest backend/tests/test_domain_database_config.py backend/tests/test_domain_database_isolation_evidence.py backend/tests/test_craft_data_boundary.py backend/tests/test_device_domain_boundary.py backend/tests/test_simulation_domain_boundary.py -q`

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/tests/test_domain_table_prefix_connections.py plugins/agent/agent_backend/data/connection.py plugins/craft/craft_backend/data/connection.py plugins/device/device_backend/data/connection.py plugins/digital_model/digital_model_backend/data/connection.py plugins/factory/factory_backend/infrastructure/connection.py plugins/integration/integration_backend/data/connection.py plugins/knowledge/knowledge_backend/data/connection.py plugins/ontology/ontology_backend/infrastructure/connection.py plugins/project_management/project_management_backend/data/connection.py plugins/simulation/simulation_backend/data/connection.py
git commit -m "fix(db): enforce test table prefix across domains"
```

### Task 3: Runtime verification

**Files:**
- No source changes.

- [ ] **Step 1: Run configuration preflight**

Run: `.venv/Scripts/python.exe backend/scripts/runtime_preflight.py --env-file backend/.env`

Expected: `Runtime preflight passed`.

- [ ] **Step 2: Start the backend with the verified environment**

Set `ENV_FILE` to the absolute `backend/.env` path and set `AI00_INTEGRATION_ADAPTER_FACTORY=integration_backend.infrastructure.production_adapters:build`, then start `uvicorn backend.main:app --host 127.0.0.1 --port 8080`.

Expected: `/health` returns HTTP 200.

- [ ] **Step 3: Verify authenticated Project and Workbench reads**

Refresh the browser login, then request `/api/tasks`, `/api/workbench/home`, and `/api/workbench/panel1` through the application.

Expected: no `provider_failed`, no missing domain DB URL, and SQL uses `test_workmanship_*` tables.

