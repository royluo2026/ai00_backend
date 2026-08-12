# Capability V2 Gitea RC Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Gitea-discoverable, fail-closed Capability V2 release-candidate path that safely provisions eleven isolated OceanBase domain databases, proves least-privilege grants, and produces current-run RC evidence for the approved three goals.

**Architecture:** A focused `rc_database_bootstrap` module owns validation, SQL planning, credential generation, reuse verification and secret-safe env serialization; a thin CLI supplies the explicit admin URL and Windows file protection. The Gitea workflow bootstraps an immutable test/RC tenant, applies all domain migrations, runs current-run process/database evidence producers, and then executes the same normalized release gates as GitHub. No database credential is discovered from local history or committed/uploaded as an artifact.

**Tech Stack:** Python 3.12, PyMySQL 1.1+, pytest, PyYAML, OceanBase CE 4.3.5+ MySQL mode, PowerShell on Windows, Gitea Actions, Node.js 22, .NET 8.

## Global Constraints

- Work only in `E:/Projects/ai00_v3/.worktrees/capability-v2-implementation` on `codex/capability-v2-implementation`.
- Do not modify or stage `CODEX-DESKTOP-HANDOFF.md` or either file under `docs/superpowers/reviews/`.
- Do not scan shell history, PowerShell history, desktop configuration or other non-standard locations for administrator credentials.
- Accept the administrator connection only through the environment variable named by `--admin-url-env`; never accept a plaintext URL argument.
- Before any `CREATE`, require OceanBase 4.3.5+, MySQL compatibility mode, strict SQL mode, an exact allowed host, and a non-`sys` tenant whose name contains `test` or `rc`; reject `prod` and `production` in both tenant and environment ID.
- Read the exact eleven domain/database/env declarations from `backend/capability_v2/official_domains.json`; never duplicate the domain list.
- Create one DDL and one runtime principal per domain. DDL is database-local migration/DML only; runtime is database-local `SELECT`, `INSERT`, `UPDATE`, `DELETE` only. Neither role gets global, cross-database, user-management or grant privileges.
- Passwords are cryptographically random and must never appear in stdout, stderr, exceptions, Git, snapshots or uploaded artifacts.
- Final RC requires real OceanBase grant probes and current-run process evidence. Fake connections are permitted only in unit tests.
- A mandatory case may not be skipped, xfailed, inferred from file existence or marked passed without its declared verifier succeeding.
- Use TDD for every implementation task and commit after each independently reviewable green task.

## File Structure

- Create `backend/capability_v2/rc_database_bootstrap.py`: pure bootstrap policy, validated data types, SQL plan construction, execution/reuse verification and env rendering.
- Create `backend/scripts/bootstrap_capability_v2_rc_databases.py`: CLI parsing, admin connection, atomic file writing and Windows ACL application.
- Create `backend/scripts/run_capability_v2_rc_database_setup.py`: load protected env, apply all eleven migration streams in manifest order, and emit a non-secret setup summary.
- Modify `backend/capability_v2/database_isolation.py`: prove runtime DDL denial in addition to owner read/write and 110 cross-domain denials.
- Modify `docs/acceptance/capability-v2-rc-evidence.schema.json`: require the runtime DDL-denial result.
- Create `backend/scripts/run_capability_v2_rc_runtime.py`: execute the current-run acceptance nodes and real component/provider probes, then emit runtime/provider evidence bound to environment, run and commit.
- Create `.gitea/workflows/capability-v2-release.yml`: Gitea-native bootstrap and RC entry point.
- Modify `backend/tests/test_capability_v2_release_workflow.py`: compare normalized GitHub/Gitea release gates and validate Gitea secret handling.
- Create `backend/tests/test_capability_v2_rc_database_bootstrap.py`: bootstrap policy, SQL, reuse and secret-leak tests.
- Create `backend/tests/test_capability_v2_rc_database_setup.py`: eleven-domain migration orchestration tests.
- Create `backend/tests/test_capability_v2_rc_runtime.py`: evidence binding, exact outcome and component-probe tests.
- Modify `backend/tests/test_domain_database_isolation_evidence.py`: runtime DDL-denial tests.
- Modify `backend/scripts/run_capability_v2_acceptance.py`: derive RC component status from current-run evidence and preserve Local Runtime's outbound-only boundary.
- Modify `backend/tests/acceptance/test_acceptance_runner.py`: assert the strengthened evidence schema and reject fabricated/incomplete runtime results.
- Create `docs/runbooks/capability-v2-gitea-rc.md`: one-time runner/tenant setup, dispatch, evidence review and recovery instructions.

---

### Task 1: Build the Fail-Closed Bootstrap Policy and SQL Plan

**Files:**
- Create: `backend/capability_v2/rc_database_bootstrap.py`
- Create: `backend/tests/test_capability_v2_rc_database_bootstrap.py`

**Interfaces:**
- Consumes: `load_domain_manifests(path: Path)` and `verify_live_server(connection) -> dict[str, str]`.
- Produces: `BootstrapRequest`, `BootstrapDomain`, `BootstrapPlan`, `BootstrapError`, `validate_bootstrap_target(...)`, `build_bootstrap_plan(...)`, and `execute_bootstrap_plan(...)`.

- [ ] **Step 1: Write failing target-safety tests**

Add table-driven tests proving that validation occurs before any mutation:

```python
@pytest.mark.parametrize(
    ("tenant", "environment_id", "host", "allowed", "message"),
    [
        ("sys", "capability-v2-rc", "127.0.0.1", None, "tenant_sys_forbidden"),
        ("customer", "capability-v2-rc", "127.0.0.1", None, "tenant_not_test_or_rc"),
        ("capability_test", "production-rc", "127.0.0.1", None, "production_environment_forbidden"),
        ("capability_test", "capability-v2-rc", "db.example", None, "host_not_allowed"),
        ("capability_test", "capability-v2-rc", "db.example", "other.example", "host_not_allowed"),
    ],
)
def test_validate_bootstrap_target_fails_before_mutation(
    tenant, environment_id, host, allowed, message
):
    connection = RecordingConnection(tenant=tenant)
    request = BootstrapRequest(environment_id=environment_id, host=host, allow_host=allowed)
    with pytest.raises(BootstrapError, match=message):
        validate_bootstrap_target(connection, request)
    assert connection.mutations == []
```

Also cover OceanBase 4.3.4, Oracle mode, missing strict SQL mode, URL/server tenant mismatch and a valid `capability_test` loopback connection.

- [ ] **Step 2: Run the target-safety tests and confirm red**

Run: `python -m pytest backend/tests/test_capability_v2_rc_database_bootstrap.py -q`

Expected: collection fails because `backend.capability_v2.rc_database_bootstrap` does not exist.

- [ ] **Step 3: Define immutable request/plan types and target validation**

Implement these exact public shapes:

```python
@dataclass(frozen=True)
class BootstrapRequest:
    environment_id: str
    host: str
    allow_host: str | None = None
    url_tenant: str = ""

@dataclass(frozen=True)
class BootstrapDomain:
    domain_id: str
    database_name: str
    runtime_env: str
    ddl_env: str
    runtime_user: str
    ddl_user: str
    runtime_password: str = field(repr=False)
    ddl_password: str = field(repr=False)

@dataclass(frozen=True)
class BootstrapPlan:
    schema_version: int
    environment_id: str
    tenant: str
    host: str
    port: int
    domains: tuple[BootstrapDomain, ...]
```

`validate_bootstrap_target` must call `verify_live_server`, query `SELECT TENANT_NAME, TENANT_TYPE, COMPATIBILITY_MODE FROM oceanbase.DBA_OB_TENANTS`, require exactly one `USER` row, compare its tenant name to the URL username tenant suffix, and return the normalized tenant. OceanBase documents that a user tenant sees only its current row in this view; more than one row therefore proves a `sys`/unexpected administrative context and must fail. Complete every safety query before calling `build_bootstrap_plan` or executing SQL.

- [ ] **Step 4: Write failing manifest/credential/grant-plan tests**

Assert exact manifest coverage, unique principals/passwords, identifier safety and minimum grants:

```python
plan = build_bootstrap_plan(ROOT, request, tenant="capability_test", port=2881)
assert len(plan.domains) == 11
assert {d.database_name for d in plan.domains} == {
    item.database.database_name for item in load_domain_manifests(MANIFEST).domains
}
assert len({d.runtime_user for d in plan.domains}) == 11
assert len({d.ddl_user for d in plan.domains}) == 11
assert len({d.runtime_password for d in plan.domains}) == 11
assert all(len(d.runtime_password) >= 32 for d in plan.domains)
```

The recording cursor must assert runtime SQL grants exactly `SELECT, INSERT, UPDATE, DELETE ON \`database\`.*` and assert DDL grants contain only `CREATE, ALTER, DROP, INDEX, REFERENCES, SELECT, INSERT, UPDATE, DELETE` on the owned database.

- [ ] **Step 5: Implement plan generation and ordered fail-stop execution**

Generate usernames as `ai00_<domain>_runtime` and `ai00_<domain>_ddl`, quote only identifiers passing `^[a-z][a-z0-9_]*$`, escape password literals through cursor parameters, and execute in this order per plan: preflight existence checks for all 11 databases and 22 principals, databases, principals, DDL grants, runtime grants. OceanBase DDL is not treated as transactional; on failure, stop, retain the non-secret created-object ledger and raise `BootstrapError("bootstrap_execution_failed:<phase>:<domain>")` without embedding the original SQL or password.

- [ ] **Step 6: Run focused tests and commit**

Run: `python -m pytest backend/tests/test_capability_v2_rc_database_bootstrap.py -q`

Expected: PASS, including assertions that `capsys.readouterr()` and exception text contain none of the generated passwords.

Commit:

```powershell
git add -- backend/capability_v2/rc_database_bootstrap.py backend/tests/test_capability_v2_rc_database_bootstrap.py
git commit -m "feat: add fail-closed RC database bootstrap policy"
```

### Task 2: Add the Secure Bootstrap CLI, Env Serialization and Reuse Contract

**Files:**
- Modify: `backend/capability_v2/rc_database_bootstrap.py`
- Create: `backend/scripts/bootstrap_capability_v2_rc_databases.py`
- Modify: `backend/tests/test_capability_v2_rc_database_bootstrap.py`

**Interfaces:**
- Consumes: Task 1 `BootstrapPlan` and `execute_bootstrap_plan`.
- Produces: `render_bootstrap_env(plan) -> str`, `parse_reuse_env(path, request, manifests) -> ReuseEnvironment`, `verify_reuse_environment(...)`, and CLI `main(argv, *, environ, connect, protect_file) -> int`.

- [ ] **Step 1: Write failing CLI and secret-boundary tests**

Cover direct execution, missing named env, forbidden plaintext flags, URL parsing without leakage, exact env keys, atomic replacement and safe summary:

```python
result = main(
    ["--admin-url-env", "AI00_RC_ADMIN_DB_URL", "--environment-id", "local-rc-42",
     "--output-env", str(output)],
    environ={"AI00_RC_ADMIN_DB_URL": "mysql://root%40capability_test:admin-secret@127.0.0.1:2881/oceanbase"},
    connect=fake_connect,
    protect_file=protected.append,
)
assert result == 0
assert "admin-secret" not in capsys.readouterr().out
assert protected == [output]
assert output.with_suffix(output.suffix + ".tmp").exists() is False
```

Assert the output contains metadata keys `AI00_RC_BOOTSTRAP_SCHEMA_VERSION`, `AI00_RC_ENVIRONMENT_ID`, `AI00_RC_TENANT`, `AI00_RC_HOST`, plus the 22 manifest-declared URL keys and nothing else secret-bearing.

- [ ] **Step 2: Run CLI tests and confirm red**

Run: `python -m pytest backend/tests/test_capability_v2_rc_database_bootstrap.py -q`

Expected: FAIL because the CLI and serializers are absent.

- [ ] **Step 3: Implement secret-safe URL/env serialization and atomic output**

Construct `BootstrapRequest.host`, port and `url_tenant` only from the parsed administrator URL; there is no CLI flag that can override them. Require the administrator URL database path to be `/oceanbase`. Use `urllib.parse.quote(..., safe="")` for usernames/passwords, and encode each connection username as `<local-principal>@<validated-tenant>` while `CREATE USER` uses only the local principal. Serialize LF-delimited `KEY=value` records, use `Path.replace` for atomic publication, and reject CR/LF/NUL in every value. The CLI prints only this shape:

```json
{"databases": 11, "environment_id": "local-rc-42", "principals": 22, "status": "created"}
```

On Windows, `protect_file` must invoke `icacls <exact-path> /inheritance:r /grant:r <current-user>:F SYSTEM:F`; test argument construction by dependency injection. On non-Windows, use mode `0600`.

- [ ] **Step 4: Implement fail-closed reuse**

Add `--reuse-env <path>`. Reuse must validate schema version, environment ID, host, port, tenant and exact 22 manifest keys; connect with every stored principal; compare normalized `SHOW GRANTS`; and perform no `CREATE`, `ALTER USER`, `GRANT` or password rotation. Reject a missing account, additional global grant, runtime DDL grant, cross-database grant, mismatched domain set or unreadable file.

- [ ] **Step 5: Run tests, syntax-check the CLI and commit**

Run:

```powershell
python -m pytest backend/tests/test_capability_v2_rc_database_bootstrap.py -q
python backend/scripts/bootstrap_capability_v2_rc_databases.py --help
python -m compileall -q backend/capability_v2/rc_database_bootstrap.py backend/scripts/bootstrap_capability_v2_rc_databases.py
```

Expected: PASS; help contains `--admin-url-env`, `--environment-id`, `--output-env`, `--allow-host`, `--reuse-env` and contains no `--admin-url` option.

Commit `feat: add secure RC database bootstrap CLI` with only the three task files.

### Task 3: Apply All Domain Migrations and Strengthen Live Grant Evidence

**Files:**
- Create: `backend/scripts/run_capability_v2_rc_database_setup.py`
- Create: `backend/tests/test_capability_v2_rc_database_setup.py`
- Modify: `backend/capability_v2/database_isolation.py`
- Modify: `backend/tests/test_domain_database_isolation_evidence.py`
- Modify: `docs/acceptance/capability-v2-rc-evidence.schema.json`
- Modify: `backend/tests/acceptance/test_acceptance_runner.py`

**Interfaces:**
- Consumes: protected Task 2 env file, `run_domain_migrations.main`, `load_probe_targets`, `verify_database_grants`.
- Produces: setup CLI `main(argv, *, root, environ, migrate) -> int`; optional `--export-job-env <GITHUB_ENV>` append of the exact 22 URL records; `owner_operations[domain].runtime_ddl == "denied"` in database and final RC evidence.

- [ ] **Step 1: Write failing eleven-domain setup tests**

Inject a `migrate(domain_id, env)` callback and assert sorted exact coverage and failure closure:

```python
assert main(["--env-file", str(env_file)], root=ROOT, environ={}, migrate=record) == 0
assert calls == sorted(domain.domain_id for domain in manifests.domains)

with pytest.raises(RcDatabaseSetupError, match="migration_failed:knowledge"):
    main(["--env-file", str(env_file)], root=ROOT, environ={}, migrate=fail_knowledge)
assert "ontology" not in calls
```

The loader must reject metadata mismatch, missing keys, duplicate keys, CR/LF injection and env-file values that attempt to override non-database process variables. A test for `--export-job-env` must assert that it appends exactly the 22 manifest-declared URL records, never metadata or unrelated process variables, without printing their values.

- [ ] **Step 2: Implement the setup orchestrator**

Load only the metadata and 22 exact URL keys, merge them over a copy of the supplied environment, and invoke the same underlying migration functions used by `run_domain_migrations.py --apply`. If `--export-job-env` is supplied, append only those 22 validated records to the exact runner-managed environment file. Print one non-secret line per domain and a final `{"domains":11,"status":"migrated"}` summary. Do not spawn a shell and do not echo env values.

- [ ] **Step 3: Write the failing runtime DDL-denial probe**

Extend the fake connection so runtime `CREATE TABLE ai00_rc_ddl_probe (...)` raises code 1142 and assert:

```python
result = verify_database_grants(targets, environment, ca_path="ca.pem", connect=connect)
assert all(row["runtime_ddl"] == "denied" for row in result["owner_operations"].values())
```

Add a negative test where one runtime principal can create the probe table; require `DatabaseIsolationError("runtime_ddl_allowed:<domain>")` and clean up the probe table through a fresh connection using that domain's DDL credential before failing.

- [ ] **Step 4: Implement zero-impact DDL denial and schema enforcement**

For each runtime connection, execute a unique identifier-only `CREATE TABLE` inside its owned database. Access-denied codes count as denial; success triggers cleanup through a fresh connection using that domain's DDL credential and fails closed. Add required `runtime_ddl: {"const":"denied"}` to the RC schema and validation fixtures.

- [ ] **Step 5: Run focused tests and commit**

Run:

```powershell
python -m pytest backend/tests/test_capability_v2_rc_database_setup.py backend/tests/test_domain_database_isolation_evidence.py backend/tests/acceptance/test_acceptance_runner.py -q
python -m compileall -q backend/scripts/run_capability_v2_rc_database_setup.py backend/capability_v2/database_isolation.py
```

Expected: PASS with 11 migration calls, 11 runtime DDL denials and 110 cross-domain pairs.

Commit `feat: prove RC domain migration and grant isolation` with only Task 3 files.

### Task 4: Produce Current-Run Runtime and Provider Evidence

**Files:**
- Create: `backend/scripts/run_capability_v2_rc_runtime.py`
- Create: `backend/tests/test_capability_v2_rc_runtime.py`
- Modify: `backend/scripts/run_capability_v2_acceptance.py`
- Modify: `docs/acceptance/capability-v2-rc-evidence.schema.json`
- Modify: `backend/tests/test_assemble_capability_v2_rc_evidence.py`
- Modify: `backend/tests/acceptance/test_acceptance_runner.py`

**Interfaces:**
- Consumes: acceptance case manifest, pytest outcome plugin, current Catalog/manifest/migration binding helpers, explicit backend/Agent/MCP/Local Runtime endpoints, and the 22 domain URLs.
- Produces: `artifacts/runtime-evidence.json`, `artifacts/provider-crud.json`, and component results derived from probes rather than constant environment values.

- [ ] **Step 1: Write failing provenance and exact-outcome tests**

Define `RuntimeProbeResult(component: str, status: Literal["passed", "failed"], endpoint: str, checks: tuple[str, ...])` and test that the evidence writer rejects missing, skipped, xfailed, duplicated or extra mandatory node outcomes. It must also reject component results not produced by the current invocation and any environment/run/commit mismatch.

```python
evidence = build_runtime_evidence(
    root=ROOT,
    environment_id="capability-v2-test-42",
    run_id="gitea:42:1",
    git_commit="a" * 40,
    outcomes=all_passed_outcomes(manifest),
    probes=required_passed_probes(),
)
assert set(evidence["capabilities"]) == set(manifest["capabilities"])
assert evidence["component_results"] == {
    "backend_gateway": "passed", "plugin": "passed", "agent": "passed",
    "mcp": "passed", "local_runtime": "passed"
}
```

- [ ] **Step 2: Implement one current-run test execution and result capture**

Reuse `contract_test_command` and `backend.tests.acceptance.outcome_plugin`; do not call pytest once per capability. Run the acceptance suite once, require exit code 0 and exact node equality, then transform each passed node into the nested `capabilities[capability@major][case] = "passed"` map. Store command summary and SHA-256 of the raw outcome file as provenance; never accept a caller-supplied all-passed map in CLI mode.

- [ ] **Step 3: Implement explicit real component probes**

Require CLI options `--backend-url`, `--agent-url`, `--mcp-url`, `--provider-output`, `--runtime-output`. Probe separate running processes with bounded timeouts and execute the checked-in Local Runtime solution directly:

- Backend: `/health`, Catalog discovery, unauthenticated invoke denial, permitted service-token invoke and correlation/audit fields.
- Plugin Platform: mount-scoped Catalog discovery plus permitted, denied and approval-required Gateway invocations; assert server-derived plugin identity and no direct Provider path.
- Agent: `/health`, Catalog-derived tool list, one permitted read, one denied capability and one approval-required write lifecycle.
- MCP: initialize/list-tools over Streamable HTTP, one permitted tool call and one denied/non-exposed tool assertion.
- Local Runtime: run the .NET Release protocol tests and an outbound lease/heartbeat exchange against the Backend device endpoint. Do not add an inbound health port to Local Runtime.

The provider probe invokes one manifest-owned smoke capability through the Backend Gateway per domain and writes exactly eleven `domains[domain_id] = "passed"` entries. It must not import Provider classes or call repositories directly. Each probe records only endpoint origin, status, check names, duration and correlation IDs—never tokens or response bodies containing business data.

- [ ] **Step 4: Bind the schema to component provenance**

Add required top-level `component_results` and `probe_provenance` objects to `capability-v2-rc-evidence.schema.json`. In `run_capability_v2_acceptance.py`, stop accepting `AI00_ACCEPTANCE_AGENT_RESULT`, `MCP_RESULT` and `LOCAL_RUNTIME_RESULT` as RC proof; validate all five component statuses from the bound evidence instead. Remove Local Runtime from inbound URL health probes in release-candidate mode because its approved architecture is outbound-only; retain the outbound exchange provenance in evidence.

- [ ] **Step 5: Run focused tests and commit**

Run:

```powershell
python -m pytest backend/tests/test_capability_v2_rc_runtime.py backend/tests/test_assemble_capability_v2_rc_evidence.py backend/tests/acceptance/test_acceptance_runner.py -q
python backend/scripts/run_capability_v2_rc_runtime.py --help
```

Expected: PASS; tests prove exact 1848-node mapping for the frozen current manifest and fail if any real process probe is absent.

Commit `feat: generate current-run capability RC evidence` with only Task 4 files.

### Task 5: Add the Gitea-Native RC Workflow and Parity Gate

**Files:**
- Create: `.gitea/workflows/capability-v2-release.yml`
- Modify: `.github/workflows/capability-v2-release.yml`
- Modify: `backend/tests/test_capability_v2_release_workflow.py`

**Interfaces:**
- Consumes: Tasks 2–4 CLIs, Gitea `workflow_dispatch.inputs.environment_id`, protected runner labels and service/admin secrets.
- Produces: a Gitea-discoverable RC workflow whose normalized release gates match GitHub.

- [ ] **Step 1: Write failing dual-workflow tests**

Parse both YAML files and normalize each step to `(name, run, working-directory)`. Assert Gitea exists, uses `[self-hosted, test-server, capability-v2-rc]`, and contains this ordered gate sequence:

```python
REQUIRED_GATES = (
    "freeze-domains", "catalog-check", "docs-check", "registry-strict",
    "acceptance-manifest-check", "dependency-check", "boundary-audit",
    "python-tests", "agent-tests", "mcp-tests", "local-runtime-tests",
    "database-bootstrap", "domain-migrations", "runtime-evidence",
    "database-isolation", "evidence-assembly", "strict-acceptance",
    "completion-recheck", "artifact-upload",
)
```

Assert Gitea references `secrets.CAPABILITY_V2_RC_ADMIN_DB_URL` but does not reference 22 domain URL secrets, does not upload `.runtime/**/*.env`, and imports all 22 exact manifest URL names from the protected env file.

- [ ] **Step 2: Run workflow tests and confirm red**

Run: `python -m pytest backend/tests/test_capability_v2_release_workflow.py -q`

Expected: FAIL because `.gitea/workflows/capability-v2-release.yml` is absent.

- [ ] **Step 3: Implement the Gitea workflow**

Use `workflow_dispatch` only, a required immutable `environment_id`, `permissions: contents: read`, and the dedicated runner labels. Set `AI00_ACCEPTANCE_RUN_ID` from the Gitea-compatible run ID/attempt context and call:

```powershell
python backend/scripts/bootstrap_capability_v2_rc_databases.py --admin-url-env AI00_RC_ADMIN_DB_URL --environment-id "$env:AI00_ACCEPTANCE_ENVIRONMENT_ID" --output-env .runtime/capability-v2-rc.env
python backend/scripts/run_capability_v2_rc_database_setup.py --env-file .runtime/capability-v2-rc.env --export-job-env "$env:GITHUB_ENV"
python backend/scripts/run_capability_v2_rc_runtime.py --backend-url "$env:AI00_RC_BACKEND_URL" --agent-url "$env:AI00_RC_AGENT_URL" --mcp-url "$env:AI00_RC_MCP_URL" --provider-output artifacts/provider-crud.json --runtime-output artifacts/runtime-evidence.json
```

The setup CLI performs the Gitea job-environment import from its already validated env document; workflow shell code must not parse or echo the secret records itself.

Then run database isolation, evidence assembly, strict acceptance and completion recheck. Upload only `provider-crud.json`, `runtime-evidence.json`, `database-isolation.json`, `capability-v2-rc-evidence.json` and the final report with `if: always()`; perform a secret-schema scan before upload.

- [ ] **Step 4: Make GitHub/Gitea gate parity structural**

Give every mandatory step the stable names in `REQUIRED_GATES`. Platform-specific credential setup may differ, but tests must compare normalized mandatory gate order and commands after substituting the credential-source step. Remove constant `AI00_ACCEPTANCE_*_RESULT: passed`; obtain those values only from Task 4 output.

- [ ] **Step 5: Run workflow tests and commit**

Run:

```powershell
python -m pytest backend/tests/test_capability_v2_release_workflow.py -q
python -c "import pathlib,yaml; [yaml.safe_load(p.read_text(encoding='utf-8')) for p in map(pathlib.Path, ['.github/workflows/capability-v2-release.yml','.gitea/workflows/capability-v2-release.yml'])]"
```

Expected: PASS and both files parse successfully.

Commit `ci: add Gitea capability RC workflow` with only Task 5 files.

### Task 6: Add the Operations Runbook and Execute the Local RC Trial

**Files:**
- Create: `docs/runbooks/capability-v2-gitea-rc.md`
- Runtime only, do not commit: `.runtime/capability-v2-rc.env`, `.runtime/capability-v2-rc-*.json`, `artifacts/*.json`.

**Interfaces:**
- Consumes: dedicated OceanBase test/rc tenant admin URL supplied explicitly by the operator, protected Gitea runner configuration and Tasks 1–5 commands.
- Produces: reproducible setup/dispatch/review instructions and a local current-HEAD strict RC report.

- [ ] **Step 1: Write the runbook with exact safe commands**

Document: OceanBase test/rc tenant creation prerequisite; process-scoped WSL `ulimit -n 65535`; TLS CA requirement; runner label registration; Gitea environment and secret names; bootstrap; migration; service startup; local trial; workflow dispatch; artifact schema review; retry with `--reuse-env`; and explicit cleanup ownership. State that a missing dedicated admin URL, TLS CA or protected runner label is an environment blocker and must never be bypassed with `sys`, production, mock evidence or generic runner labels.

- [ ] **Step 2: Run the bootstrap against the explicitly supplied test/rc tenant**

Run only after `AI00_RC_ADMIN_DB_URL` and `AI00_ACCEPTANCE_OCEANBASE_SSL_CA` are explicitly present in the current process:

```powershell
python backend/scripts/bootstrap_capability_v2_rc_databases.py --admin-url-env AI00_RC_ADMIN_DB_URL --environment-id capability-v2-local-rc --output-env .runtime/capability-v2-rc.env
python backend/scripts/run_capability_v2_rc_database_setup.py --env-file .runtime/capability-v2-rc.env
```

Expected: 11 databases, 22 principals, 11 migration streams and no secret values in console output.

- [ ] **Step 3: Run current-process and database evidence**

Start the Backend, Agent, MCP and Local Runtime with the generated domain env and explicit service secrets, then run Task 4's CLI and `verify_domain_database_isolation.py`. Expected: four component probes passed, eleven Provider smoke invocations passed, eleven owner runtime DDL attempts denied and all 110 cross-domain pairs denied.

- [ ] **Step 4: Run strict RC acceptance on current HEAD**

Run:

```powershell
python backend/scripts/assemble_capability_v2_rc_evidence.py --runtime-evidence artifacts/runtime-evidence.json --database-evidence artifacts/database-isolation.json --output artifacts/capability-v2-rc-evidence.json
python backend/scripts/run_capability_v2_acceptance.py --mode release-candidate --strict --report .runtime/capability-v2-release-candidate.json
python backend/scripts/check_capability_v2_completion.py --mode strict --report .runtime/capability-v2-release-candidate.json
```

Expected: `status: passed`, `validation_scope: runtime_e2e`, 1848/1848, failed 0, skipped 0, 11/11 independent domains, Gateway-only Plugin/Agent true, synchronous and asynchronous sharing each at least one, and zero boundary/bypass counts.

- [ ] **Step 5: Commit only the runbook**

Verify no `.runtime` or `artifacts` secret file is staged, then commit `docs: add capability RC operations runbook`.

### Task 7: Run Full Regression, Audit Artifacts and Dispatch Gitea RC

**Files:**
- Modify only if a test exposes a defect: the owning Task 1–5 file and its focused test.
- Do not modify or stage the three preserved user files.

**Interfaces:**
- Consumes: all prior task commits and the protected Gitea environment.
- Produces: clean tracked worktree, full regression evidence, a dispatched current-commit Gitea run and downloadable secret-free RC artifacts.

- [ ] **Step 1: Run generated-artifact and boundary gates**

```powershell
python backend/scripts/freeze_official_domains.py --check
python backend/scripts/build_capability_catalog.py --check
python backend/scripts/generate_capability_docs.py --check
python backend/scripts/build_capability_acceptance_manifest.py --check
python backend/scripts/build_user_function_registry.py --strict
python backend/scripts/check_domain_dependencies.py
python backend/scripts/audit_domain_boundaries.py --json
```

Expected: all exit 0; 11 official domains; zero cross-domain SQL, internal imports and consumer bypasses.

- [ ] **Step 2: Run every repository test surface**

```powershell
python -m pytest backend/tests plugins -q
npm ci --prefix services/agent-runtime
npm test --prefix services/agent-runtime
npm ci --prefix services/mcp-gateway
npm test --prefix services/mcp-gateway
dotnet test local-runtime/Ai00.LocalRuntime.sln -c Release
```

Expected: no failures, skips or xfails in mandatory Capability V2/RC suites; Agent, MCP and Local Runtime all pass.

- [ ] **Step 3: Audit tracked cleanliness and artifact secrets**

Run `git status --short --untracked-files=all` with the known preserved files explicitly excluded from any add command. Scan artifact JSON keys and schemas for forbidden names (`password`, `authorization`, `admin_url`, `private_key`) without printing values. Require `git diff --check` and a clean tracked worktree.

- [ ] **Step 4: Push the exact branch and dispatch Gitea workflow**

Push `codex/capability-v2-implementation`, dispatch `.gitea/workflows/capability-v2-release.yml` with a new immutable test/rc environment ID, and verify the run is assigned only to a runner carrying `capability-v2-rc`. Do not merge or deploy production code as part of this step.

- [ ] **Step 5: Verify final Gitea artifacts and completion**

Download the five allowlisted JSON artifacts. Verify run ID, attempt, commit, Catalog release/hash, manifest hash, migration bindings, environment ID and report ID all match. Run the completion CLI against the downloaded report; require `complete: true` and preserve the report path/hash in the handoff.

- [ ] **Step 6: Commit any evidence-free final correction and report**

If Step 1–5 exposed a code defect, return to the owning focused test, make the minimum TDD fix, rerun the full task and commit it. Do not commit RC credentials or generated runtime artifacts. Report completion only after the remote Gitea report passes; otherwise name the exact external blocker and retain fail-closed status.

## Execution Checkpoints

- After Task 2: inspect CLI help, exception paths and captured output for secret leakage.
- After Task 3: confirm the database evidence schema requires runtime DDL denial and exact 110-pair coverage.
- After Task 4: review evidence provenance; no constant `passed` component result or caller-supplied all-pass map is acceptable.
- After Task 5: use the Gitea API to confirm the workflow is discoverable before configuring or dispatching it.
- After Task 6: retain `.runtime` evidence outside Git and stop if the explicit test/rc tenant, TLS or service credentials are missing.
- After Task 7: invoke `superpowers:verification-before-completion` and cite fresh command outputs and the remote report ID.

## Final Completion Statement

Do not claim the three goals are complete merely because the bootstrap unit tests, offline acceptance or local workflow parsing pass. Completion requires a Gitea-discovered current-commit RC run with real process/database evidence, 1848/1848 cases, zero failed/skipped, 11/11 independent domain databases, Gateway-only Plugin/Agent consumption, at least one synchronous and one asynchronous sharing path, zero boundary debt, and a strict completion result of `complete: true`.
