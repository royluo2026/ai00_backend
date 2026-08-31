# Craft Structural Capability Closure Design

## Scope

Close seven Craft groups and nine occurrences:

- equipment delete
- fixture delete
- rule-entry check
- mutable-rule activate
- rule deviation creation
- mutable-rule suspend
- rule update

## Semantic disposition

The repository has no provider for equipment delete, fixture delete, mutable-rule activate, mutable-rule suspend, or the legacy deviation model. Similar archive, immutable-release activation, and release-waiver capabilities are not equivalent. Those five dead UI actions are removed or rendered explicitly unavailable; no replacement Capability is invented.

Two real functions remain:

1. Rule-entry validation becomes `craft.rule.entry.evaluate@1`, an exact bounded read/compute Capability owned by Craft.
2. Rule update becomes `craft.rule.definition.change.apply@1`, replacing the non-invocable generic contract with one exact closed mutation.

## Rule-entry validation

The input identifies a governed rule revision and a bounded entry projection. The provider loads the actor/team-visible rule, evaluates only the existing approved expression engine with time/input/output limits, and returns a closed result containing pass/fail, bounded diagnostics, and the evaluated revision. It does not accept arbitrary executable source, database expressions, or provider selection.

## Rule update

The update contract permits only the existing supported mutable fields, expressed as a closed nested record. It requires actor/team scope, expected revision, confirmation, and idempotency. Rule identity, tenant ownership, immutable release fields, compiled artifacts, and audit fields cannot be supplied by the browser.

Mutation, new revision, operation result, and audit record are one transaction. Reusing an idempotency key with another canonical payload conflicts. Provider output is a closed rule projection.

## Dead-entry removal

Deleting a dead action is part of governance, not a hidden feature change:

- remove the event path and legacy REST literal;
- remove the interactive affordance; where the layout must explain the missing action, render a non-interactive unsupported-state label;
- add a regression proving no network call occurs;
- do not silently map delete to archive, mutable activation to release activation, or deviation to waiver.

## Failure behavior

- Missing or cross-team rule: indistinguishable not-found.
- Unsupported update field: Gateway schema rejection before provider execution.
- Evaluation timeout/limit: structured non-success outcome with no persisted secret or raw expression dump.
- Revision conflict: no partial update or audit.

## Verification

Tests cover the real Gateway, expression bounds, rule update red/green/replay/conflict behavior, dead-action non-invocation, Web source/dist parity, and absence of all seven legacy route identities. Immutable evidence must reduce the Craft portion from seven groups/nine occurrences to zero.
