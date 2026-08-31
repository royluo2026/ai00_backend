# Task 2 Report — Bounded Agent canvas queries

## Outcome

Implemented `agent.workflow.node.test.execute@1` and `agent.canvas.options.resolve@1` behind the single shipped `ProductionAgentCanvasRuntime`. Default provider registration now composes that runtime from the existing `AgentCapabilityRepository`; explicit absence still fails closed. Registered-handler tests cover both query capabilities through the production process boundary.

The runtime performs the database/resource load and the existing `CanvasExecutor` call in one spawned worker. Request and result envelopes are JSON-only. Internal and application timeouts both terminate and join the process, close process/queue handles, and leave no late marker or growing active-worker set across repeated timeouts. No thread-backed blocking work or second executor was added.

Agent domain migration `0002_canvas_query_tenant.sql` adds nullable `team_gid` bindings and tenant/owner indexes to flows and skills. New flow, skill, and seeded-skill writes persist the context team. Repository reads and mutations require the persisted team plus the applicable actor/visibility rule; legacy NULL rows, cross-team rows, and missing rows fail closed. **Task 3 must use Agent migration `0003` or later.**

Node/input/graph/output/option/concurrency bounds, Task 1 declared-input validation, finite non-executable node kinds, deterministic option ordering, closed output projection, and recursive canonical secret/control redaction remain enforced. Query paths do not write durable execution state; `start` and `resume` remain retryable unavailable for Task 3.

## TDD evidence

- RED: the default registered handler remained adapter-less; the repository lacked persisted tenant lookup; team skill creation was blocked; migration `0002` did not exist.
- RED: the production adapter had no spawned-worker/timeout surface.
- GREEN: real repository SQL tests prove actor/team predicates, create-time tenant persistence, and legacy-NULL denial.
- GREEN: registered handlers prove same-team node/options success and uniform cross-team/missing denial.
- GREEN: production process tests prove JSON result transport, internal timeout cleanup, application-cancellation cleanup, repeated-timeout worker stability, and concurrency capping.

## Verification evidence

- Focused canvas query suites: `25 passed`.
- Complete Agent provider/runtime/domain suite: `105 passed`.
- Agent domain migration check: `domain=agent migrations=2 mode=check`.
- Domain migration runner plus release bindings: `12 passed`.
- Domain dependency gate: `Domain dependency check passed: 1 reviewed violations, no new dependencies`.
- Changed Agent modules compile successfully.

Migration ruling: Task 2 owns `0002_canvas_query_tenant.sql`; Task 3's first available Agent migration number is `0003`.
