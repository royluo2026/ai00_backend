# Task 2 — Base self-annotation and identity owner services

## Scope delivered

- Added the closed, actor-bound `SelfAnnotationService` (`get`, `search`, and
  `apply_change`) with revision conflict detection, idempotency replay, an
  explicit deleted tombstone, an audit event, and a finite attachment grammar:
  `attachment_gid`, `media_type`, `display_name`, `size`, `checksum`.
- Added the closed allowlisted `IdentityProfileService.get_current` projection.
  It never returns arbitrary user-model data, credentials, tokens, or auth
  headers.
- Added the SQL migration for annotation state, idempotency, and audit records;
  retained the REST routes as adapters to the same service.
- Registered the exact Gateway targets `base.self_annotation.record.get@1`,
  `base.self_annotation.search@1`, `base.self_annotation.change.apply@1`, and
  `base.identity.session.profile.get@1`. The annotation write is a strong,
  transactional write and requires confirmed user intent plus an idempotency key.
- Migrated the required frontend consumers (self annotation panel, knowledge
  hub, and Craft lineage); no corresponding REST fallback remains.
- Rebuilt capability, migration, root-cause, route-inventory, and Base
  structural-remediation artifacts from their generators.

## TDD evidence

Red (before the services existed):

```text
python -m pytest backend/tests/test_base_self_annotation_service.py backend/tests/test_base_identity_profile_service.py -q
1 failed, 4 errors
ModuleNotFoundError: backend.base.self_annotations
ModuleNotFoundError: backend.base.identity_profile
```

Minimal-green service run:

```text
..... [100%]
5 passed in 0.79s
```

Final green verification:

```text
python -m pytest backend/tests/test_base_self_annotation_service.py backend/tests/test_base_identity_profile_service.py backend/tests/test_base_structural_web_capabilities.py backend/tests/test_atomic_web_gateway_policy.py backend/tests/test_atomic_web_capability_contracts.py -q
23 passed in 2.27s

python -m pytest backend/tests/test_base_structural_remediation_manifest.py::test_saved_view_routes_have_exact_owner_contract_and_frontend_source_evidence -q
1 passed in 19.75s

python -m pytest backend/tests/test_base_structural_remediation_manifest.py::test_annotation_and_identity_routes_have_exact_owner_service_contract_and_frontend_evidence -q
1 passed in 21.06s

python -m pytest backend/tests/test_mysql_migration.py -q
38 passed in 0.74s
```

Authoritative checks passed for atomic contracts, frozen official domains,
catalog/docs generation, existing migrations, root-cause ledger, Base
structural remediation, and the frontend route inventory.

## Artifact-count delta

| Artifact | Before Task 2 | After Task 2 | Delta |
| --- | ---: | ---: | ---: |
| Base structural migrated groups / occurrences | 10 / 25 | 14 / 31 | +4 / +6 |
| Base structural unresolved groups / occurrences | 6 / 8 | 2 / 2 | -4 / -6 |
| Canonical unresolved groups / occurrences | 32 / 37 | 28 / 31 | -4 / -6 |

The only remaining Base structural unresolved groups are the two Craft plugin
groups (two occurrences); this task did not reclassify or exclude them.

## Files

Backend owner services and migration:

- `backend/base/self_annotations.py`
- `backend/base/identity_profile.py`
- `backend/db/migrations/202608280002_base_self_annotation_governance.sql`
- `backend/base/web_atomic.py`, `backend/base/provider.py`
- `backend/routers/self_annotations.py`, `backend/routers/users.py`

Contracts, evidence, tests, and generators:

- `backend/capability_v2/atomic_web_contracts.py`
- `backend/capability_v2/existing_capability_migration_decisions.py`
- `backend/capability_v2/official_domains.json`
- `backend/scripts/build_base_structural_web_remediation.py`
- `backend/scripts/build_existing_capability_web_migrations.py`
- `backend/tests/test_base_self_annotation_service.py`
- `backend/tests/test_base_identity_profile_service.py`
- `backend/tests/test_base_structural_web_capabilities.py`
- regenerated `docs/capabilities/` and `docs/governance/` truth artifacts

Frontend migration (separate worktree/commit):

- `web/core/existing_capability_client.js`
- `web/components/self_annotation_panel.js`
- `web/knowledge_hub/knowledge_hub.js`
- `packages/craft-plugin/web/lineage_view/lineage.js`

## Self-review and concerns

- Schemas are closed and bounded. The UI sends only the documented attachment
  grammar, and the service rejects unexpected attachment fields and unauthorized
  attachment identifiers rather than preserving opaque JSON.
- Read and write handlers target the exact capability IDs. The UI explicitly
  confirms annotation writes; its client supplies a revision and idempotency key.
- REST and Gateway call the same owner service; none of the four migrations uses
  a BFF/operations exclusion or a manual evidence hash edit.
- Attachment authorization deliberately fails closed until a concrete attachment
  visibility port supplies `visible_attachment_gids` in the caller context. That
  is safer than accepting an unverified attachment and should be wired by the
  eventual attachment/asset owner integration.
- Backend commit: `feat: govern Base annotations and identity profile`.
  Frontend commit: `feat: route Base annotations and identity through capability gateway`.
