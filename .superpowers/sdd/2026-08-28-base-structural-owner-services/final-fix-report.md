# Base structural owner-services final-fix report

Date: 2026-08-28

Status: **DONE_WITH_CONCERNS**

Binding review: `.superpowers/sdd/2026-08-28-base-structural-owner-services/final-review.md`

## Commits

- Backend product, migrations, tests, generated Catalog/docs/evidence: `a7bf669f` (`fix: close Base structural owner service findings`)
- Frontend, Electron, regression tests, selected checked-in production assets: `0647ee87ab48c8e6fb4092e5fa708d675767b41c` (`fix: govern Base web and Electron owner services`)
- Backend report: the commit containing this file (created after the product commit so this report can name the immutable product SHA).

## Outcome

All 2 Critical, 8 Important, and 2 practical Minor findings from the binding final review were addressed in one TDD wave.

| Finding | Resolution |
| --- | --- |
| Critical 1: saved-view tenant/idempotency authority | Repository reads/writes, lifecycle state, audit, replay, visibility, and admin access are tenant-bound. Idempotency is tenant + actor + operation + key + canonical command digest. Existing finite AND/grid configs have explicit typed compatibility; unsupported legacy shapes fail closed and audit. |
| Critical 2: Electron install/uninstall authority | Removed URL install and local destructive uninstall from preload, IPC, registry, and the dormant bridge manager. Supported install/uninstall is the signed, confirmed Capability path; installed projections carry revision. |
| Important 1: annotation tenant/attachment authority | Annotation state, replay, audit, reads, and batch are tenant-bound. The artifact store transaction now produces typed reference-registry rows; migration backfills valid historical artifacts. Legacy attachment projection validates every immutable field and drops malformed values; exact persisted legacy references can be registered once. |
| Important 2: split batch owner | REST and Gateway both delegate to `SelfAnnotationService.batch`; the single SQL path suppresses tombstones. |
| Important 3: trusted identity | REST `/me` and Gateway use the same `IdentityProfileService` and Base-owned SQL effective-identity port. The port reloads the active user, verifies tenant, loads unexpired grants, and builds the shared effective permission projection. |
| Important 4: frontend closure | Saved-view writes fail visibly and never synthesize local authority. The official production build was regenerated. The deployable scanner covers production web/package roots and the complete Electron root. |
| Important 5: dependency resolver | Required Capability dependencies resolve by exact major from the active immutable Catalog release and must be stable plus plugin-exposed; missing descriptors fail as `release_not_verified`. |
| Important 6: table ownership | All new Base tables are registered. Canonical inventory/ownership is 234/234 with zero unowned tables or ownership violations. |
| Important 7: grammar/pagination | Saved views use the approved conjunction-only finite grammar. REST/Gateway share `limit`/`offset`, output is deterministically bounded at 500, and the frontend requests 500 explicitly. |
| Important 8: errors | Every structural Base Capability declares its exact domain-error set; the generated Catalog and docs were rebuilt. |
| Minor 1: annotation SQL filtering | `status`, `module`, tenant, actor, tombstone, ordering, and limit are applied in SQL. Batch uses one bounded `IN` query. |
| Minor 2: timestamps/audit | Saved-view and annotation tombstones persist real UTC deletion timestamps. Write audits carry tenant, idempotency key, revision/deletion state, and canonical command digest. |

## TDD evidence

### Initial red

Backend security/behavior regressions were added first and run before implementation:

```text
python -m pytest <Base final-finding focused files> -q
21 failed, 69 passed in 7.16s
```

The failures covered tenant isolation and digest conflicts, attachment registry/backfill, typed legacy projection, shared batch/tombstones, trusted identity, Catalog exact-major/stability, exact domain errors, table ownership/migration registration, bounded saved-view grammar/pagination, SQL filtering, and real deletion timestamps.

The new deployable scanner test was separately red before the scanner existed:

```text
python -m pytest backend/tests/test_base_deployable_surface_scan.py -q
1 failed (ModuleNotFoundError: backend.scripts.check_base_deployable_surfaces)
```

Frontend reds were recorded before implementation:

```text
node scripts/test_saved_view_capability_migrations.js
AssertionError: saved-view configuration must use the governed finite grammar and writes must not fall back locally

node scripts/test_electron_plugin_lifecycle_security.js
AssertionError: renderer must not receive arbitrary URL installation privilege

node scripts/test_atomic_web_migrations.js
AssertionError: annotation/plugin production migrations were stale
```

Evidence-generation and review found additional integration reds, which were fixed before proceeding:

```text
provider_artifact_mismatch: base

python -m pytest ... test_versioned_migration_files.py
1 failed, 414 passed in 6.99s
MigrationError: 202608280004_base_plugin_lifecycle_idempotency_scope.sql contains non-resumable migration SQL

python -m pytest ... test_existing_capability_web_migrations.py
4 failed, 13 passed in 110.22s

node scripts/test_electron_plugin_lifecycle_security.js
AssertionError: Electron must not retain a bridge installation bypass
```

### Final green

Frontend source/Electron regressions and syntax:

```text
node scripts/test_saved_view_capability_migrations.js
saved-view capability migration tests passed
node scripts/test_electron_plugin_lifecycle_security.js
electron plugin lifecycle security tests passed
node scripts/test_atomic_web_migrations.js
atomic web migration tests passed
node --check <view-manager, web-compat, settings, main, preload, plugin-registry, plugin-manager>
exit 0
```

Official production build:

```text
npm run build:web
vite v4.5.14 building for production...
✓ 172 modules transformed.
✓ built in 1.15s
```

Focused final owner-service/route/artifact/ownership/scanner suite:

```text
python -m pytest <10 focused Base final-fix files> -q -p no:cacheprovider
92 passed in 6.78s
```

Required Base behavior/contract suite from the plan:

```text
python -m pytest -q -p no:cacheprovider <8 Base behavior/contract files>
78 passed in 4.13s
```

Migration and ownership suite:

```text
python -m pytest -q -p no:cacheprovider \
  backend/tests/test_domain_table_ownership.py \
  backend/tests/test_application_migration_boundary.py \
  backend/tests/test_domain_migration_runner.py \
  backend/tests/test_mysql_migration.py \
  backend/tests/test_schema_migration_static.py \
  backend/tests/test_versioned_migration_files.py
417 passed in 7.07s
```

Independent generated-evidence suite:

```text
python -m pytest -q -p no:cacheprovider \
  backend/tests/test_base_structural_remediation_manifest.py \
  backend/tests/test_structural_remediation_plan.py \
  backend/tests/test_existing_capability_web_migrations.py
17 passed in 110.13s
```

## Migration details

### `202608280004_base_plugin_lifecycle_idempotency_scope.sql`

- Split multi-column ADD into separately resumable `ADD COLUMN IF NOT EXISTS` statements.
- Primary-key replacement is now accepted only through the metadata-preflighted replay-safe runner path.

### `202608280005_base_structural_owner_hardening.sql`

- Adds/backfills/enforces `tenant_gid` for saved views, saved-view state/audit/replay, annotations, annotation state/audit/replay.
- Adds/backfills canonical command digests for saved views and annotations.
- Replaces aggregate/replay primary keys with tenant-scoped keys.
- Backfills typed attachment references from the authoritative artifact registry producer.
- Uses separate replay-safe DDL statements, `IF NOT EXISTS` indexes/columns, explicit idempotent-backfill markers, metadata-preflighted NOT NULL transitions, and metadata-preflighted primary-key transitions.
- No production row is dropped; unmatched historical ownership maps to an actor-personal tenant and remains fail closed across tenants.

The migration runner now skips already-completed NOT NULL and primary-key steps by inspecting `information_schema`, permitting safe retry after OceanBase implicit commits. Tests prove completed steps are skipped and unmarked DML remains rejected.

## Generated artifacts and counts

Source-derived checks after frontend commit `0647ee87ab48c8e6fb4092e5fa708d675767b41c`:

```text
Base remediation: groups=16 migrated_groups=16 migrated_occurrences=33 occurrences=33 unresolved_groups=0 unresolved_occurrences=0
Canonical ledger: final_groups=26 final_unresolved=29
Structural plan: groups=37 occurrences=45
Deployable surfaces: scanned_files=220 findings=[]
Table ownership: tables=234 unowned=[] violations=0
```

Official artifact check mode:

```text
freeze_official_domains.py --check
sha256:5840cfb8b1824cb862c0e6baa55f0a88203bee4a73ec2c6d9cffe7af2a8f4f78
build_capability_catalog.py --check
Catalog release check passed: rel_9618bda183d820aa83b56a9e47500f2b, 481 descriptors
generate_capability_docs.py --check
Capability docs check passed: rel_9618bda183d820aa83b56a9e47500f2b, 481 pages
build_capability_acceptance_manifest.py --check
Acceptance manifest check passed: 465 stable capabilities
check_structural_remediation_plan.py --check
groups=37 occurrences=45
check_domain_dependencies.py
Domain dependency check passed: 0 reviewed violations, no new dependencies
```

Post-product-commit strict acceptance:

```text
status            : passed
release           : rel_9618bda183d820aa83b56a9e47500f2b
stable            : 465
declared          : 3255
validated         : 3255
failed            : 0
skipped           : 0
inner             : 3266 passed in 7.64s
report_id         : sha256:23ac1487a91bf9fc43b6807754811e2d1c5839b2f65b43358228d2820ed44f70
```

## Self-review

- Tenant predicates are present in every aggregate, state, replay, audit, visibility, and admin path changed in this wave.
- Replays compare canonical command digests before returning a prior result.
- REST and Capability transports call the same saved-view, annotation, identity, and plugin owner services.
- No Electron renderer/main/registry/manager path retains local install/uninstall authority.
- Saved-view frontend failures are visible; no local identifier or success result is fabricated.
- The deployable scanner has no BFF/count/exclusion workaround and scans production web/packages plus all Electron JavaScript/HTML.
- Catalog resolution never consults the mutable runtime registry and never treats experimental/non-plugin descriptors as dependency-ready.
- `git diff --check` was clean before the backend product commit.

## Remaining concerns (not hidden)

1. Strict acceptance exits successfully with all declared cases validated, but its separate repository-wide completion advisory remains `false` because of the pre-existing non-Base invariant `coverage_invariant:stable_functions:922!=920`. This wave did not edit that invariant or its counts.
2. Standalone `build_user_function_registry.py --strict` reports broad pre-existing replaced/non-stable target drift outside this Base batch. It was not rewritten or suppressed. The full strict offline acceptance command still passes.
3. `npm ci` reported 36 existing dependency advisories (9 low, 1 moderate, 25 high, 1 critical). The Vite build also emits existing non-module-script warnings. Neither changed the successful build result, but dependency remediation remains separate work.
4. Migration safety was verified by static policy, metadata-preflight unit tests, ownership checks, and the complete mock/static migration suite; this wave did not apply the migration to a live production OceanBase instance.
