# Simulation Environment Redesign Verification Draft

Date: 2026-09-09
Branch: `test`
Scope: development evidence only; no approval or release promotion

## Implemented and locally verified

- Safe streaming PLMXML projection, including hostile XML rejection and hard resource limits.
- Real 21 MB PLMXML sample parse: 214,205 elements, 14,170 product instances, 138,791 references, 7.032 seconds, 53.0 MiB peak memory.
- VM occurrence identity and snapshot persistence rules for part movement, repeated resources, reload, upgrade, ambiguity, CAS, tenant scope, and soft deletion.
- Private workspace schema, pure aggregate, owner-scoped repository reads, atomic CAS/idempotency mutation repository, and local UI patches.
- Canonical workspace freeze manifest, Base Artifact finalization, transactional version freeze, and orphan/unavailable reconciliation records.
- Knowledge reverse model-number lookup unit behavior for tool, fixture, equipment, and socket. Real data remains unverified because the test mapping table is empty.
- Craft `part_feed` to normalized `parameters.is_load_part` projection.
- Deterministic per-process reverse capture planning, selective BOP publication planning, and Simulation-owned publish plan/map/outbox persistence.
- Four-column desktop UI shell, record/store/tree modules, decimal-string GID checks, view-state preservation, and guarded Capability invocation.
- VisMockup process-running versus automation-connected status distinction.

## Current verification evidence

| Area | Result | Evidence |
| --- | --- | --- |
| Consolidated backend focused suite | passed | 171 passed, 37 skipped on 2026-09-09; skips are environment/integration dependent |
| Workspace/freeze/publish focused suite | passed | 20 tests covering schema, aggregate, candidate contracts, Artifact failure branches, and domain ownership |
| Process capture planner | passed | 4 tests |
| Knowledge reverse lookup | passed | 4 unit tests |
| Selective publish planner | passed | 4 tests |
| Connector VisMockup Release tests | passed | 13 focused xUnit tests covering snapshot status, bounded ExportEx staging, and DPAPI scene recovery journal |
| Frontend cad_sim Node suites and static boundary checks | passed | All focused suites passed on 2026-09-09: 2 visibility, 3 VM tree, 7 capture, 4 onboarding, environment state/workspace, layout and P0 boundary |
| Production web build | passed with existing warnings | Vite production build completed; legacy non-module script tags continue to emit repository-wide warnings |

## Open or blocked evidence

- G0 runtime Registry/Catalog Snapshot readback is unverified. Static Catalog evidence only.
- Teamcenter-launched VisMockup cannot currently be attached through the discovered out-of-process COM route. `GetActiveObject` is unavailable and `Dispatch` creates another instance. G3 requires an official attachment interface or governed in-process Adapter.
- Knowledge resource/model mapping table has no test rows. Runtime reverse classification is unverified.
- Craft `draft.change.preview@1` accepts concrete `parent_gid` commands but has no contract for Simulation `client_ref` / `parent_client_ref` correlation. Selective publish dispatch must remain disabled until Craft adds that owner-side contract; Simulation will not resolve or write Craft tables itself.
- Capture worker recovery, actual selective Craft dispatch, and full UI workflows remain incomplete. Freeze and publish persistence are locally implemented but have no live cross-domain evidence.
- Packaged Windows x64 screenshots and the full manual smoke matrix have not run.

## Governance status

- `machine_passed`: unverified
- `human_approved`: unverified
- `runtime_verified`: unverified

Candidate Capability handlers are experimental/advisory and remain outside the registered release until the user's later consolidated approval workflow.
