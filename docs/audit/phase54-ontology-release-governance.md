# Phase 54 — Ontology release publication and activation

Date: 2026-08-06
Branch: `codex/capability-wave-a`

## Implemented interfaces

- `ontology.release.publish`
- `ontology.release.get`
- `ontology.release.search`
- `ontology.release.diff`
- `ontology.release.activate`

## Separation of authority

Publication and activation are deliberately separate:

- Publish accepts one exact approved proposal revision, rechecks independent human approval, applies typed changes to its immutable base, writes and verifies an OIS snapshot, and appends an inactive release.
- Activate never creates content. It requires the target release GID and Hash, expected current active release, Base Gateway admin confirmation, `ontology.activate`, and four zero-blocker attestations: migration, rules, Capabilities, and plugins.
- Activation only permits a direct forward child of the expected active release. Direct rollback or an unrelated branch is rejected.
- The repository performs the final active-ref compare-and-swap under `SELECT ... FOR UPDATE` and re-verifies the target Hash.

## Semantic diff

Diffs are keyed by stable ontology identity and grouped into concepts, properties, relations, mappings, and constraints. Each group reports added, changed, deprecated, and removed objects. Compatibility is classified as `backward_compatible|migration_required|breaking`; raw JSON text diff is not exposed as the business result.

## Verification

Task 10 publish/activate separation and Capability kernel tests passed. Final combined Tasks 7–10 evidence is recorded at commit time.

No OIS call, database connection, activation, deployment, push, or remote mutation was performed.
