# TC assembly parts recovery

Goal: show W10-2026 v2 imported parts under their actual operations, and prevent deduplication from disconnecting future imports.

Scope: Craft-owned import implementation, assembly relation renderer, and a source-backed local test-data repair. Reuse existing tree nodes and existing PBOM links; do not create duplicate parts or infer parents from names alone. Preserve concurrent changes.

- [x] Add failing tests for skipped existing parents, ambiguous parent labels, and assembly materials.
- [x] Preserve exact TC labels across import deduplication; resolve unique existing parents and reject ambiguous references. Store source part numbers in metadata and render all four part types.
- [x] Prepare a repair preview from the original TC CSV and existing parent-reference evidence. Validate full parent graph, use an explicit version scope, before-image backup, frozen/version checks, transaction, and rollback on conflict. Apply only proven repairs.
- [x] Run focused tests and real-data readback, review changes, rebuild/deploy the local frontend and rehash/reload the unpublished backend. Verify served cache behavior; report UI verification limits accurately.

Evidence: `.runtime/bop-entry-link-fix-20260930` in the workspace contains the read-only database snapshots and original CSV normalization. The original CSV is `D:/Temp/tc_1790664718376 W10 0926.csv`.

Governance: implementation fix; Craft owns import, links, and projections. Formal Catalog/approval evidence remains unchanged. Machine tests, local runtime verification, and user authorization are recorded separately.
