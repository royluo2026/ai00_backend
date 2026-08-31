# Task 2 Report — Bounded Agent canvas queries

## Outcome

Implemented the two query outcomes behind one `ProductionAgentCanvasRuntime` adapter:

- `agent.workflow.node.test.execute@1`
- `agent.canvas.options.resolve@1`

The adapter loads the persisted flow/skill and selected node/field before use, applies actor/team/private/team/global visibility rules, and gives missing, cross-team, and missing-node cases the same `resource_not_found` result. The provider remains fail closed when no adapter is composed.

Node testing constructs one bounded node for the existing `CanvasExecutor`; it does not add another executor. The finite allowed kinds are the executor's non-executable data/control/human kinds. Condition/eval, tool, agent/LLM, nested skill, source, import, environment, resolver, and arbitrary dynamic-option paths are not exposed by this query boundary.

Both queries validate submitted values against the persisted Task 1 input declaration. Graph node/edge/byte size, aggregate input bytes, output bytes/counts, options, and active concurrency are capped. Query work is wrapped by an asyncio timeout that waits for cancellation, and tests prove no pending task remains.

Outputs use the closed Task 1 dataclasses. Raw node values are deterministically ordered, nested structures are serialized canonically, sensitive and execution-control keys are recursively redacted, and option outputs expose only sorted `value`/`label` pairs. Query operations write no durable state. `start` and `resume` remain retryable unavailable for Task 3.

## TDD evidence

- Initial RED: 12 expected failures for the missing adapter and timeout gate; the existing absent-adapter assertion passed.
- Control-path RED: two failures proved `source_tool` was neither rejected nor recursively redacted.
- Declared-option-input RED: an undeclared option input incorrectly reached resolution.
- Command-boundary RED: the production adapter lacked explicit fail-closed Task 3 methods.
- GREEN focused: 16 query tests pass.

## Verification evidence

- Focused query suite: 16 passed.
- Complete Agent plugin suite: 96 passed.
- Task 1 query/provider/runtime combined suite: 89 passed before the final two regression tests were added.
- Changed modules compile successfully.
- Domain dependency gate: `Domain dependency check passed: 1 reviewed violations, no new dependencies`.

The shared `progress.md` ledger was not edited.
