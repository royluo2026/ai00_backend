# Agent Runtime Capability Closure Design

## Scope

Close four Agent groups and five occurrences:

- flow node test
- skill canvas option resolution
- canvas execution start
- paused canvas execution resume

These are real UI workflows, so deleting them would remove intended product behavior. They require exact Agent-owned runtime contracts rather than aliases to generic run mutation.

## Capability model

Define four exact stable outcomes:

- `agent.workflow.node.test.execute@1` for bounded flow-node testing;
- `agent.canvas.options.resolve@1` for bounded canvas-option resolution;
- `agent.canvas.execution.start@1` for durable canvas-run start;
- `agent.canvas.execution.resume@1` for durable canvas-run resume.

The option and node-test capabilities are synchronous bounded operations. Start and resume are confirmed, idempotent writes that create or advance durable Agent run state and return accepted/terminal/reconcilable outcomes honestly.

## Runtime boundary

Agent owns a single production runtime port backed by the existing skill/flow runtime. Contracts carry only closed node/canvas identities, validated input values, execution mode, expected revision where applicable, and opaque pause/run tokens. They never carry Python/JavaScript source, import paths, arbitrary tool names, raw environment variables, credentials, or unbounded graphs.

Runtime composition fails closed when the adapter is absent. Time, graph-size, input-size, output-size, and retry limits are explicit. Output projection redacts secrets through the platform detector before both response and durable operation evidence.

## Durable start and resume

Run creation or transition, operation record, audit, and idempotency result share one transaction. A pause token is opaque, actor/team scoped, single-transition, and revision bound. Resume reauthorizes the stored run and uses the same production dispatcher/supervision surface as other Agent runs; cross-team tokens are indistinguishable from missing tokens.

`outcome_unknown` remains reconcilable with the same invocation identity. Retry cannot create a second run or repeat a completed transition.

## Failure behavior

- Unknown canvas/node or unauthorized scope: fail closed.
- Missing production adapter: structured unavailable result, no synthetic success.
- Timeout/crash after dispatch: durable reconcilable state.
- Invalid/used pause token or revision conflict: no transition.
- Oversized graph/input/output: rejected or bounded before durable evidence.

## Verification

Tests use the production composition path and shipped Web client, cover adapter absence, bounds, tenant isolation, idempotent replay, pause/resume, timeout reconciliation, lifecycle health, source/dist parity, and absence of the four legacy routes. Immutable evidence must reduce the Agent portion from four groups/five occurrences to zero.
