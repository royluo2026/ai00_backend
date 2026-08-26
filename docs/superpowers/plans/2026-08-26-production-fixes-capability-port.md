# Production Fixes Capability Port Plan

**Goal:** Port the behavior shipped on the production `deploy` branches into the local backend and frontend `test` branches without restoring direct mutable REST or cross-domain persistence.

**Source baselines:** backend `production/deploy` at `2899f890`; frontend `production/deploy` at `06e855e`.

## Architecture mapping

- `craft.bop.entry.change.apply@1` remains the only public write boundary for BOP entry edits. Add a `properties` update mode whose Craft Provider resolves the active Ontology property projection and routes each value to an allowlisted entity column, entity `ext`, or BOP entry `meta`. SQL identifiers come only from verified schema metadata; user values remain parameters.
- Base owns cloud database runtime configuration. Add separate read, save, and connection-test outcomes. The existing Admin REST endpoints become Gateway compatibility adapters; the settings UI invokes the capabilities directly.
- `ontology.schema.change.apply@1` remains proposal-only. Validate property `name` and `mapped_column` before proposal persistence with `^[A-Za-z_][A-Za-z0-9_]*$`; do not mutate an active release directly.
- Frontend schema reads continue through `ontology.concept.resolve@1` plus `ontology.concept.get@1`, cached by `node_type`. Successful schema proposal submission invalidates the cache through the existing storage event key.
- Process-card presentation is a pure projection of governed entry/entity data. Sequence-color persistence uses `craft.bop.entry.change.apply@1`; successful edits repaint only the affected card.

## Implementation slices

### 1. Craft dynamic properties

- Add failing provider tests for fixed-column, `ext`, `meta`, denied/unknown/derived fields, JSON `null`, and transactional audit behavior.
- Extend the Craft input contract with an explicit `properties` object while keeping existing `updates` callers compatible.
- Implement mapping and validation inside the Craft Provider; do not revive `/api/bop/entries/{gid}/entity-props`.
- Update generated Catalog, docs, manifests, and consumer evidence.

### 2. Base runtime database configuration

- Add failing tests for blank/masked password reuse, redacted reads, URL encoding, connection testing, and role/permission contracts.
- Implement Base-owned read/save/test providers with no secret output or logging.
- Register three atomic capabilities and convert Admin endpoints to Gateway adapters.
- Change the settings UI to invoke those capabilities and leave the password input blank with a configured-state placeholder.

### 3. Ontology identifiers

- Add failing tests at `normalize_changes` / Capability entry for invalid property names and mapped columns.
- Implement identical validation in both official Ontology runtime copies used by the repository until the duplication is removed separately.
- Add frontend immediate validation for create/edit forms and invalidate the schema cache after successful proposal submission.

### 4. Frontend behavior

- Port save de-duplication, local row snapshots, targeted relation refresh, process-card styling, critical marker, and sequence-color picker.
- Replace all production REST writes with existing Gateway helpers.
- Add or extend JS contract tests proving no direct entity-props route and exact capability IDs/payloads.

### 5. Verification and delivery

- Run focused backend and frontend tests after each slice.
- Run frontend build, then synchronize the governed backend web artifact using the repository build process.
- Regenerate capability artifacts and run catalog/docs/manifest checks, domain dependency checks, strict offline acceptance, and the static Release Gate.
- Commit only task-owned tracked changes to local backend and frontend `test`; preserve unrelated untracked files and do not push.
