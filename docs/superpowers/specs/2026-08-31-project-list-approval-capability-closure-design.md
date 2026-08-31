# Project/List and Approval Capability Closure Design

## Scope

Close the three remaining Project-facing structural groups:

- `GET /api/lists`
- `DELETE /api/lists/{gid}`
- `POST /api/approval/orders/{gid}/reject`

The first two routes are shared Web entry points whose BOP-version branch belongs to Craft while ordinary list behavior belongs to Project Management. The approval route belongs entirely to Project Management.

## Decisions

### Shared list dispatch

The Web compatibility client becomes a finite dispatcher, not a REST fallback. It selects an exact owner Capability from the already-known item type:

- BOP version list/archive uses `craft.bop.version.list@1` and `craft.bop.version.archive@1`.
- Project list search/delete uses `project.list.read.atomic.lists_search@1` and `project.list.change.apply.atomic.lists_delete@1`.
- Unknown item types fail closed with `capability_not_bound`; they do not call `/api/lists`.

No Capability may branch into another domain after Gateway authorization. The Web chooses the owner before invocation, and each provider owns only its own tables and policy.

### Approval rejection

Project Management owns `project.approval.order.reject@1` as the exact rejection outcome. The mutation, optimistic revision check, operation result, audit record, and notification outbox event commit atomically. Notification delivery is asynchronous and retryable; rejection success does not depend on a live notification transport.

The command requires authenticated actor/team scope, an expected revision, confirmation, and an idempotency key. Replay returns the byte-equivalent prior result. A changed payload under the same key conflicts.

## Contracts

Read DTOs are bounded and exclude internal SQL/filter expressions. Delete/archive outputs identify the affected resource and terminal lifecycle state. Approval output contains the order identity, revision, rejection state, and durable notification event identity; it does not expose recipient secrets or transport payloads.

## Failure behavior

- Unknown list item type: fail closed before provider selection.
- Cross-team or non-owner access: indistinguishable not-found outcome.
- Revision conflict: no mutation, audit, or notification event.
- Notification transport failure: outbox remains retryable; the rejection is not repeated.
- Duplicate command: replay the original result without a second mutation or event.

## Verification

Tests must drive the shipped Web client through the real Gateway policy, cover both Craft and Project list branches, prove `/api/lists` fallback absence, and prove approval mutation/outbox atomicity and idempotent replay. Immutable evidence must reduce these three groups and three occurrences to zero without changing unrelated domain counts.
