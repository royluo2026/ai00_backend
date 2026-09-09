# BOP Repository Collaboration Capability Change Record

## Change classification

- Type: new Capability set plus later consumer migration.
- Reason: the approved design introduces a Project-scoped BOP Repository, team and managed personal spaces, immutable space versions, two-stage Fork, ordered VPPS groups, three-way Diff and change proposals. Existing BOP-version capabilities do not carry those identities or invariants.
- Compatibility: additive while candidates are isolated. Existing BOP-version and Simulation workspace contracts remain unchanged. A later controlled migration moves consumers only after approval and runtime evidence.

## Authoritative context inspected

- Craft registration and descriptors: `plugins/craft/craft_backend/capabilities/__init__.py`, `provider.py`, `contracts.py`.
- Existing Craft BOP reads/writes/Fork: `bop_versions.py`, `bop_writes.py`, `bop_fork_change.py`, and `_bop/fork.py`.
- Simulation registration, workspace Provider and persistence: `plugins/simulation/simulation_backend/capabilities/__init__.py`, `capabilities/workspaces.py`, `data/workspace_repository.py`.
- Executed migrations: Craft `0001` through `0009`; Simulation `0001` through `0011`.
- Legacy BOP schema: `workmanship_bop_bop_versions`, `workmanship_bop_bop_entries`, and `workmanship_bop_bop_entry_links` in `backend/db/mysql_schema.sql`.
- Domain ownership: `backend/governance/domain_table_ownership.json`, table inventory and schema source map.
- Project source: `plugins/project_management/project_management_backend/capabilities/projects.py` registers `base.project.search@1` under Project Management owner.
- Current consumer surfaces: Craft BOP routers and `packages/sim-plugin/web/cad_sim` desktop renderer.
- Specifications: `docs/superpowers/specs/2026-09-08-digital-simulation-environment-redesign.md` and `2026-09-09-simulation-environment-collaboration-versioning-design.md`, approved by static review at commit `4ade7bd3518228428827550f9f9c6460e5ce161f`.

No trusted running Registry Snapshot GID, exact human decision, signed release or controlled runtime evidence was available during this inventory. Source inspection is advisory.

## Reuse, atomicity and ownership result

### Reuse decisions

- `base.project.search@1` remains the project candidate search surface. It does not authorize Repository creation. A Project Management owned project get/authorize contract must be found or added before Repository writes become callable.
- `craft.bop.version.get@1`, `craft.bop.version.list@1`, `craft.bop.version.compare@1`, `craft.bop.draft.change.preview@1`, `craft.bop.draft.change.apply@1`, `craft.bop.version.create@1` and `craft.bop.version.archive@1` remain legacy BOP-version contracts. They can support migration reads, but cannot represent Repository space identity or new state transitions.
- `craft.bop.fork.change.apply@1` combines fork, smart-fork and stage advance; it is non-idempotent and lacks Project unique slot, immutable space source, owner portability verdict, Preview/Apply split and recoverable workflow. It **不能复用为 Repository Fork** and its `@1` meaning will not be changed.
- Existing experimental private workspace create/search/get and structure/binding/freeze capabilities remain Simulation owned. Immutable version get/export, private Fork and private VPPS effects are additive candidates.
- Existing Artifact capabilities may be reused only after exact contract and lifecycle verification. OIS is storage implementation, not a domain owner.

### Ownership result

- **Craft owner:** BOP Repository, team space, managed personal space, logical node/binding identities and revisions, immutable space versions, Fork workflow, Craft VPPS groups, Diff, import projection and change proposals.
- **Simulation owner:** unlimited private environments, VM snapshots and occurrences, private VPPS groups, Simulation Context, private version export tokens and VisMockup/capture orchestration.
- **Project Management owner:** project identity, project read authorization and project manager/delete authorization used by Craft.
- **Knowledge owner:** VPPS identities and knowledge resource/model mappings.
- **Digital Model and Artifact owners:** immutable model versions and stored artifact references.
- Cross-domain composition uses Gateway/SDK Capability calls. The implementation **不跨域直表**, does not create cross-domain foreign keys and does not move owner rules into the renderer, Agent Skill or governance service.

### Findings

1. Project search exists, but an exact Project Management get/authorize Capability for Repository create/fork was not found in the inspected source. Repository write exposure remains blocked until this owner contract is resolved.
2. No BOP Repository/Fork/VPPS/proposal Task Tool exists in the Agent registry. `task.bop_repository_assistant` is a new orchestration candidate.
3. Current old BOP entry GID is scoped to an old `version_gid` and mixes identity with mutable content. Additive node/binding identity, revision and membership tables are required; renaming or reinterpreting old GIDs would be unsafe.
4. Candidate capabilities below are absent from the inspected stable release. They are `not_registered` until real definitions, GIDs and Provider bindings exist.
5. Simulation `0011_simulation_workspaces.sql` already defined 18 workspace/VM tables that were absent from the checked-in ownership and compiled schema documents. Task 2 registers them to the existing Simulation owner and regenerates schema metadata together with the new Craft tables; it does not change their runtime schema or ownership.

## Candidate Capability inventory

All rows are new, atomic business effects. `@1` is the proposed major version and is not evidence of registration.

| Owner | Candidate IDs |
|---|---|
| Craft | `craft.bop.repository.search@1`, `craft.bop.repository.get@1`, `craft.bop.repository.create@1`, `craft.bop.repository.archive@1`, `craft.bop.repository.restore@1`, `craft.bop.repository.delete@1`, `craft.bop.repository_baseline.set@1` |
| Craft | `craft.bop.space.search@1`, `craft.bop.space.get@1`, `craft.bop.space_version.search@1`, `craft.bop.space_version.get@1`, `craft.bop.space_version.save@1`, `craft.bop.space_version.freeze@1` |
| Craft | `craft.bop.repository.fork.preview@1`, `craft.bop.repository.fork.apply@1`, `craft.bop.managed_personal_space.fork.preview@1`, `craft.bop.managed_personal_space.fork.apply@1`, `craft.bop.fork_run.get@1`, `craft.bop.fork_workflow.get@1` |
| Craft | `craft.bop.managed_personal_space.delete@1`, `craft.bop.managed_personal_space.sync.preview@1`, `craft.bop.managed_personal_space.sync.apply@1`, `craft.bop.managed_personal_space.import.preview@1`, `craft.bop.managed_personal_space.import.apply@1` |
| Craft | `craft.bop.vpps_group.initial.generate@1`, `craft.bop.vpps_group.adjustment.create@1`, `craft.bop.vpps_group.current.set@1` |
| Craft | `craft.bop.change_proposal.create@1`, `craft.bop.change_proposal.submit@1`, `craft.bop.change_proposal.get@1`, `craft.bop.change_proposal.review@1`, `craft.bop.change_proposal.apply@1`, `craft.bop.change_proposal.cancel@1`, `craft.bop.change_proposal.withdraw@1`, `craft.bop.change_proposal.supersede@1` |
| Craft | `craft.bop.repository_diff.start@1`, `craft.bop.repository_diff.get@1`, `craft.bop.operation.get@1`, `craft.bop.operation.reconcile@1` |
| Simulation | `simulation.environment.workspace.fork.preview@1`, `simulation.environment.workspace.fork.apply@1`, `simulation.environment.workspace.delete@1`, `simulation.environment.workspace_version.get@1`, `simulation.environment.workspace_version.export_for_import@1` |
| Simulation | `simulation.environment.vpps_group.get@1`, `simulation.environment.vpps_group.initial.generate@1`, `simulation.environment.vpps_group.adjustment.create@1`, `simulation.environment.vpps_group.current.set@1` |
| Agent Platform | `task.bop_repository_assistant` with fixed `craft_repository` and `simulation_private_environment` profiles |

## Implementation boundary

- Craft owner paths: `backend/db/migrations/domains/craft`, `plugins/craft/craft_backend/data`, `plugins/craft/craft_backend/capabilities`, and Craft tests.
- Simulation owner paths: `backend/db/migrations/domains/simulation`, `plugins/simulation/simulation_backend`, and Simulation tests.
- Agent owner paths: `plugins/agent/agent_backend/orchestration` and Agent tests.
- Desktop consumer paths: `packages/sim-plugin/web/cad_sim` in the frontend repository.
- Approved shared paths are limited to governance inventory/schema metadata and generic Gateway/SDK registration hooks. No domain logic is added to shared kernel paths.
- Implementation order is persistence and identity, read/write Provider candidates, immutable Simulation export, Fork, VPPS, Diff/import/proposals, migration fence/backfill, desktop, then Agent.

## Release and approval boundary

- Every new identity starts as `not_registered` in this document.
- Development registration may use experimental lifecycle for contract and Provider tests.
- These candidates **不加入 stable Catalog Release** and are not product-routable until deterministic checks, exact-hash human approval, consumer migration and runtime evidence independently pass.
- Per user direction, Capability approval is deferred for later unified review: **用户后续统一审批**. Deferral does not count as approval and does not waive any gate.

## Verification evidence

- commands actually run: source searches over the paths above; `python -m pytest backend/tests/test_bop_repository_governance_inventory.py -q` is the Task 1 acceptance command.
- raw outcomes: recorded in implementation commits; no runtime execution was used for this inventory.
- code revision at inventory start: `382f62fd45c66f8f88ce06e87df1d285aea052f2`.
- snapshot_gid: unverified.
- test_run_gid: unverified.
- result_hash: unverified.
- skipped or unavailable: trusted running Registry snapshot, exact Capability version GIDs, Project authorization contract, controlled runtime and production release evaluation.

## Governance status

- machine_passed: unverified
- human_approved: unverified
- runtime_verified: unverified
- advisory: true

## Required later decisions

- Project Management owner must supply or approve the exact project authorization effect.
- Each domain owner must review business definitions, closed schemas, stable errors, permissions, idempotency, audit and consumer exposure.
- A trusted server-authenticated `super_admin` must decide against exact version GIDs, business definition hashes and a current Snapshot.
- Release Gate and controlled runtime evidence remain separate after human approval.
