# Task 3 Report — Durable Agent canvas start and resume

## Outcome

Implemented durable production handling for `agent.canvas.execution.start@1` and
`agent.canvas.execution.resume@1` from backend commit `14efcb51`.

- Agent migration `0003_canvas_execution_control.sql` adds the run, invocation,
  and audit tables plus persisted Skill revisions. Task 2's
  `0002_canvas_query_tenant.sql` remains unchanged.
- Start persists one run per actor/team/idempotency key, hashes the exact
  capability plus closed payload, returns an opaque run token, conflicts on a
  changed replay, and replays the stored canonical result.
- Resume locks the run, requires the actor/team-bound run and pause tokens at
  the exact paused revision, consumes the pause transition once, and safely
  replays the winning invocation. Stale, used, foreign-actor, foreign-team, and
  missing transitions share the same non-disclosing denial.
- The Agent repository owns creation, resume transition, audit, lease claim,
  dispatch marker, terminal completion, uncertainty, and replay transactions.
  `FOR UPDATE SKIP LOCKED` plus a lease token prevents duplicate workers from
  executing one invocation.
- A crash before the dispatch marker is reclaimable. Once dispatch is marked,
  a reclaim uses the same persisted invocation identity through the
  reconciliation method and never blindly calls start/resume again. Unknown
  results remain replayable while bounded reconciliation is pending and become
  terminal `outcome_unknown` after the attempt ceiling.
- The worker restores the persisted actor/team principal. Results and resume
  checkpoints use the closed `RuntimeDispatch` projection, including recursive
  secret/control redaction, before database persistence.
- `ProductionAgentCanvasRuntime` extends Task 2's existing spawned-process,
  bounded-pipe worker path; it does not add a second executor. Resume rebuilds
  only the sanitized completed-node checkpoint and the approved human input.
- Production registration installs `agent.canvas-execution-worker` through the
  existing Capability Registry lifecycle health and signal methods. No Agent
  health capability or parallel health framework was added.

## TDD evidence

- RED 1: command tests failed at collection because the durable coordinator,
  dispatcher, and worker did not exist.
- GREEN 1: nine transaction, idempotency, token, crash, reconciliation,
  concurrency, replay, and lifecycle tests passed.
- RED 2: three production-runtime tests failed for the missing command engine
  and stable-invocation worker entry point.
- GREEN 2: twelve focused tests passed after extending the single production
  runtime/worker.
- RED 3: the SQL completion test exposed invalid `__dict__` serialization for
  the frozen/slotted runtime result.
- GREEN 3: thirteen focused tests passed with canonical dataclass-to-JSON
  serialization.
- Acceptance RED/GREEN: the release-binding inventory failed on the new Agent
  migration and passed after adding the exact `0003` binding.

## Verification evidence

- Focused durable command/runtime/repository suite: `13 passed`.
- Complete Agent suite: `120 passed`.
- Domain migration runner tests: `11 passed`.
- Domain database configuration tests: `6 passed`.
- Acceptance release-binding gate: `1 passed`.
- Agent migration check: `domain=agent migrations=3 mode=check`.
- Domain dependency gate: `Domain dependency check passed: 1 reviewed violations, no new dependencies`.
- Changed Agent modules compile successfully and `git diff --check` reports no
  whitespace errors.

The shared `progress.md` ledger was not edited.

## Review round 1

Addressed all three Important findings from `task-3-review.md`.

- Durable JSON now stores token-free response templates and token-free resume
  requests. Run and pause bearer values are deterministic HMACs of the opaque
  run identity, purpose, and revision under the existing deployment
  `JWT_SECRET`; only their hashes and control metadata are stored. Token and
  payload-hash verification uses constant-time comparison after the scoped DB
  lookup. Canonical replay injects the regenerated bearer values only at the
  response boundary.
- The stable invocation ID now reaches `CanvasExecutor`. The spawned command
  worker records the sanitized result in
  `workmanship_agent_canvas_runtime_results` before writing its pipe reply.
  Reconciliation queries that exact actor/team-bound invocation; a recovered
  completed, paused, halted, or error result is returned without invoking the
  executor again, while a missing result remains `outcome_unknown`.
- Added real PyMySQL repository tests for the concurrent idempotency unique-key
  race, `FOR UPDATE SKIP LOCKED`, dispatch lease expiry/reclaim, concurrent
  single-use resume, transaction rollback after injected failure, canonical
  replay, and bearer absence in every durable JSON column after accepted,
  paused, consumed/resumed, terminal, and replay states. These tests use the
  actual `AgentCapabilityRepository` methods and independent DB connections;
  no memory repository or source-text assertion supplies this evidence.

The controlled SQL gate is:

```powershell
$env:AI00_AGENT_TEST_DB_URL='mysql+pymysql://USER:PASSWORD@HOST:3306/ai00_agent_test'
$env:AI00_REQUIRE_AGENT_MYSQL_TESTS='1'
python -m pytest plugins/agent/tests/test_agent_canvas_repository_mysql.py -q
```

The URL must name a dedicated database containing `test`; its account needs
DDL and DML for the Agent tables. This workspace had no RC/test DB environment,
local MySQL/OceanBase listener, Docker, or MySQL binaries. The required gate
was therefore run without the URL and failed clearly with the provisioning
instruction, while the ordinary suite skipped its four external-DB cases.

Round-one verification:

- RED: focused suite failed 11 tests on the missing HMAC boundary, command
  invocation identity, durable result recorder/loader, and repository
  connection injection.
- GREEN: focused command/runtime/repository suite: `13 passed`.
- Complete Agent suite: `120 passed, 4 skipped` (only the external SQL gate).
- Required SQL gate without provisioning: `4 errors`, each explicitly stating
  that `AI00_AGENT_TEST_DB_URL` and a dedicated DDL+DML test database are
  required.
