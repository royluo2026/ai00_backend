# Capability Governance Evidence Closure Design

## Status

- Date: 2026-08-26
- Backend baseline: `81337b3b1abab6548d51c51a54fc72d803058856`
- Frontend baseline: `dd67726d4881ec56eb8bb1df88b3c6e938166fa9`
- Governing specification: `docs/governance/atomic-capability-spec-v2.md`
- Scope: Catalog lifecycle integrity, complete Web API coverage, consumer evidence, orchestration ledgers, reproducible audit evidence, and authoritative runtime release evidence

## Problem Statement

The static Capability V2 gate currently passes while five governance gaps remain:

1. The Legacy Route Inventory contains 81 entries whose migration target exists only as a deprecated Capability.
2. The Web route scanner classifies only configured API prefix families, so `/api` routes outside those prefixes are absent from the stored evidence.
3. The latest checked-in audit report names obsolete backend and frontend revisions and therefore cannot attest the current source state.
4. The current source revision has no authoritative runtime Registry snapshot, test run, or signed release report.
5. Of 440 stable Catalog descriptors, 394 have no verified `consumer_refs`; the business, Task Tool, and BFF registries contain only 2, 1, and 1 entries respectively.

These are one evidence-integrity problem rather than five independent cleanup tasks. A signed release report is valid only for one exact combination of backend revision, frontend revision, Catalog release, Provider artifacts, consumer evidence, and test evidence. Runtime signing must therefore occur after all source and Catalog-changing work.

## Goals

- Require every stable route or Function mapping to resolve to a stable Capability owned by the expected domain.
- Discover every browser-side `/api/` invocation in governed source roots and require an explicit governance disposition.
- Generate consumer evidence from real source and registry references instead of maintaining hundreds of manual descriptor exceptions.
- Make static and runtime audit reports reproducible and bound to exact immutable inputs.
- Produce one final authoritative snapshot, test run, and signed release report after all Catalog-changing work is complete.

## Non-Goals

- Re-promoting deprecated generic Capabilities to stable.
- Creating replacement `operation + arguments` umbrella Capabilities.
- Migrating every Legacy REST endpoint to a new public interface in one release when an existing stable atomic Capability already represents its outcome.
- Treating every atomic Capability as a business ledger node or Task Tool.
- Using unit-test signers, in-memory stores, dirty worktrees, or self-reported test status as production release evidence.

## Baseline Evidence

### Deprecated migration targets

The 81 invalid Legacy Route Inventory entries group into five repair families:

| Deprecated target | Entries |
|---|---:|
| `craft.manufacturing_resource.change.apply` | 37 |
| `craft.manufacturing_resource.read` | 11 |
| `craft.gbop.change.apply` | 24 |
| `craft.gbop.read` | 8 |
| `project.craft_scope.read` | 1 |

The repair unit is a route family, not an individual evidence row. Each family will receive a deterministic method-and-resource mapping to existing stable atomic replacements. A route with no live business consumer will be retired or explicitly excluded instead of being mapped to a deprecated target.

### Web coverage

The configured scanner recognizes only these Legacy prefix families: BOP, GBOP, Ontology, Projects, Flows, Factory, Simulation, and Device. The stored Web inventory currently contains 43 classified occurrences. A broad source search finds approximately 469 source lines containing `/api/`, including Agent, Skills, Tasks, Lists, Knowledge, Canvas, admin, and other prefixes outside the scanner configuration. The implementation must calculate authoritative normalized route counts; the line count is only evidence of the coverage gap.

### Consumer and orchestration evidence

The current Catalog contains 440 stable descriptors: 46 have verified structured consumer references and 394 have an empty list. The current orchestration registries contain two business entries, one Task Tool entry, and one BFF entry. Coverage must be driven by real consumers and workflows, not arbitrary target counts.

## Design Principles

1. **Fail closed on unknown state.** Missing Catalog targets, unknown lifecycle, unclassified `/api` routes, stale evidence, and untrusted signatures are blockers.
2. **Generate evidence from authoritative sources.** Source discovery and checked-in reviewed dispositions feed Catalog generation; descriptor-local guesses do not.
3. **Separate exposure from consumption.** Web/plugin/agent exposure flags do not count as consumer evidence.
4. **Preserve domain ownership.** A route mapping must resolve to a stable Capability owned by the route's declared domain.
5. **Keep historical evidence immutable.** Deprecated descriptors and expired reports remain queryable but cannot satisfy a new stable release.
6. **Sign last.** Any source, Catalog, Provider, consumer evidence, or test change invalidates prior runtime release evidence.

## Architecture

### 1. Catalog-aware route and Function integrity

Route inventory auditing will consume a Catalog index keyed by `(capability_id, major_version)`. Migration targets will use an explicit versioned reference. For compatibility with the existing string field, unversioned entries may be parsed as major version 1 during migration, but the rewritten inventory must persist the major version explicitly.

For every stable route or Function mapping, the gate will validate:

- the Capability and major version exist in the current Catalog;
- lifecycle status is exactly `stable`;
- owner domain matches the route or Function owner;
- the Capability is not an expired atomicity replacement;
- the mapping has reviewed source evidence.

The same resolver will be shared by Legacy Route Inventory, BFF Inventory, User Function Registry, and orchestration registry audits so lifecycle rules cannot diverge.

The 81 entries will be repaired through five checked-in mapping tables derived from route method, normalized resource path, and current atomicity dispositions. Mapping tables must reject duplicate route keys and targets that are not stable. Routes without an appropriate stable outcome must be retired or receive a reviewed operations exclusion with owner, reason, approval reference, and expiry.

### 2. Complete Web API discovery and disposition

The Web scanner will discover every literal route beginning with `/api/`; configured legacy prefixes will no longer define scan coverage. Prefix configuration may remain only as classification metadata.

Every discovered occurrence will be normalized into:

```text
source path + line + method + normalized route template
```

It will then receive exactly one disposition:

- `capability`: a Capability Gateway invoke/confirm route;
- `legacy_registered`: method and normalized route exist in the Legacy Route Inventory;
- `bff_registered`: method and normalized route exist in the BFF Registry;
- `operations_excluded`: a reviewed non-business endpoint with owner, reason, approval, and expiry;
- `unresolved`: no valid disposition; release blocker.

The scanner will cover `web/` and `packages/` under the supplied frontend root. Only dependencies, tests, generated bundles, and build outputs are excluded. Template paths and dynamic suffixes will be normalized conservatively. If method inference or route parsing is ambiguous, the occurrence is unresolved rather than silently omitted.

The stored Web inventory will include counts for all five dispositions, its scan configuration, frontend commit, and a content hash. Release completion will compare a fresh scan with this artifact and fail on either drift or unresolved entries.

### 3. Verified consumer evidence pipeline

A checked-in consumer evidence artifact will be generated from four authoritative sources:

1. Web Capability Gateway occurrences from the complete Web scan.
2. Backend Domain Client, compatibility route, and internal Gateway invocations discovered by the existing Python boundary scanner.
3. Plugin, Agent, MCP, worker, and Local Runtime manifests or registries.
4. Task Tool, BFF, and business orchestration registries.

Each evidence record will contain:

```json
{
  "capability_id": "craft.bop.entry.change.apply",
  "major_version": 1,
  "consumer_id": "craft-plugin/lineage_view/layout_detail_panel.js",
  "consumer_type": "web",
  "version_constraint": ">=1 <2",
  "source_path": "packages/craft-plugin/web/lineage_view/layout_detail_panel.js",
  "source_hash": "sha256:..."
}
```

Catalog generation will join descriptors to this evidence. A stable descriptor must have at least one verified consumer or a structured `no_consumer_reason` with owner, category, review reference, and expiry. Empty `consumer_refs` without that reason will become blocking only after the initial evidence artifact and reviewed exception set are complete.

Business, Task Tool, and BFF registries will continue to serve different purposes:

- Business entries model user-recognizable outcomes composed from one or more stable atomic Capabilities.
- Task Tools model high-frequency Agent or workflow operations and declare bounded inputs and outputs.
- BFF entries model reviewed aggregation boundaries only.

Their audit will validate lifecycle, version, owner, duplicates, source evidence, and existence. Coverage targets will be based on discovered business workflows and callable orchestration entry points, not the total number of atomic Capabilities.

### 4. Reproducible static audit

The audit report generator will obtain all mutable facts from commands and artifacts rather than prose constants:

- backend and frontend full commit SHA;
- clean/dirty state;
- Catalog release ID and hash;
- Provider artifact hashes;
- stable, deprecated, consumer, route, and orchestration counts;
- exact validation commands and exit status;
- static Release Gate result;
- runtime evidence identifiers when available.

Formal report generation will reject dirty worktrees. The report will carry an input manifest hash. A verification command will recompute the inputs and report `stale` when either repository, Catalog, Provider manifest, evidence artifact, or test result differs.

The report has two independently generated sections: static code audit and runtime attestation. The static section may be generated before deployment; it must state runtime status as pending until authoritative evidence exists. The final published report requires both sections to match the same immutable input manifest.

### 5. Authoritative runtime release evidence

The controlled release environment will run after the preceding source and Catalog changes are committed:

1. Verify clean repositories and pin backend SHA, frontend SHA, Catalog release/hash, Provider hashes, and consumer evidence hash.
2. Run the official Registry scan through `base.capability_scan.run` and persist immutable snapshot rows.
3. Run `base.capability_test.run` for that exact snapshot and persist component-level results and result hashes.
4. Reject any required component with `not_run`, `skipped`, stale, or mismatched evidence.
5. Reload snapshot, test run, Findings, waivers, and approvals from the authoritative store.
6. Evaluate `base.capability_release_gate.evaluate` server-side.
7. Sign the canonical report with a configured release key whose public key is in the production trust allowlist.
8. Read the persisted report back and verify its hash and signature before packaging.
9. Bind the production artifact to the exact signed input manifest.

The production path must not use the default development signer, the unit-test signer, caller-supplied pass/fail values, or an in-memory governance store. A later source, Catalog, Provider, consumer evidence, test, waiver, or approval change expires the report.

## Failure Semantics

The following conditions are release blockers:

- stable route or Function targets a missing, deprecated, experimental, retired, or cross-domain Capability;
- a Web `/api/` occurrence is unresolved or omitted from the stored scan artifact;
- checked-in scan or consumer evidence differs from fresh discovery;
- a stable Capability has neither verified consumers nor an approved no-consumer reason after enforcement activation;
- orchestration registries reference missing or non-stable Capabilities;
- audit inputs are dirty or do not match the report manifest;
- runtime evidence is absent, stale, skipped, self-reported, unsigned, signed by an untrusted key, or bound to different inputs.

Errors will report a stable machine-readable reason plus the exact route, Function, Capability, evidence record, or report identifier that failed. Counts remain secondary to actionable identities.

## Rollout Sequence

### Work package A: Lifecycle integrity and 81 mappings

- Add the shared versioned Catalog target resolver.
- Strengthen route, Function, and orchestration audits.
- Repair the five deprecated target families in batches.
- Establish zero invalid stable targets before expanding other gates.

### Work package B: Complete Web scan

- Discover every `/api/` route.
- Add disposition joins and reviewed operations exclusions.
- Regenerate the Web inventory and make unresolved routes blocking.

### Work package C: Consumer and orchestration evidence

- Generate verified consumer evidence from source and registries.
- Populate Catalog `consumer_refs` deterministically.
- Review bounded no-consumer reasons.
- Expand business, Task Tool, and BFF registries from real workflows.
- Activate the empty-consumer blocking rule.

### Work package D: Reproducible static audit

- Generate the audit report from the final committed source and evidence.
- Verify the report input manifest and static Release Gate.

### Work package E: Runtime attestation

- Run the authoritative snapshot, test, and release-gate workflow once against the final inputs.
- Verify and attach the signed runtime report.
- Build only from the verified report.

Each work package ends with its own tests and reviewable commit. Work package E cannot start until A through D are committed and the target repositories are clean.

## Acceptance Criteria

- Legacy and BFF route entries targeting non-stable Capabilities: 0.
- Stable User Functions targeting non-stable Capabilities: 0.
- Unresolved browser `/api/` occurrences: 0.
- Fresh Web scan equals the checked-in inventory for the exact frontend commit.
- Stable descriptors with neither verified consumers nor approved no-consumer reason: 0.
- Invalid or non-stable business, Task Tool, and BFF references: 0.
- Static audit report verifies against exact backend/frontend commits and evidence hashes.
- Runtime component results contain no required `not_run`, `skipped`, stale, or mismatched result.
- Persisted release report conclusion is `pass`, its signature verifies against a trusted key, and every input matches the production artifact.

## Security and Operational Constraints

- No production database mutation is authorized by the static remediation work.
- Runtime governance execution uses a controlled test or release environment and the official Capability Gateway.
- Release private keys remain outside the repository and are available only to the release signer.
- Reports and logs must not include database passwords, tokens, private keys, confirmation tokens, or authenticated remote URLs.
- No force push is required; evidence binds to immutable commits after normal review and integration.
