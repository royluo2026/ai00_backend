# Capability Governance Trust Closure Design

## Goal

Make the existing Capability governance stack produce one reproducible, fail-closed release decision whose evidence is bound to the exact Catalog, Descriptor revisions, Provider artifacts, source revisions, consumers, and executed tests.

## Scope

This design changes governance infrastructure and generated governance evidence. It does not redesign business Capability contracts or create one bespoke test file per Capability.

## Decisions

1. Reuse the existing Catalog, acceptance manifest, Gateway, governance snapshot/test service, and signed release report.
2. Treat Catalog `test_refs` as coverage declarations, never as self-asserted execution results.
3. Produce per-`Capability@major` parameterized case outcomes in a separate Test Run.
4. Make the signed governance Release Gate the sole release decision. The static gate becomes a required input report.
5. Bind invocation, approval, idempotency, and release evidence to active Catalog release, Descriptor revision, and Provider artifact hash.
6. Fail closed for strong-write audit or transaction evidence failures.
7. Convert scanner configuration failures into structured blocking results instead of unhandled exceptions.

## Data Flow

```text
source revisions + provider artifacts
        -> immutable Catalog release
        -> governance snapshot
        -> static audit + parameterized Test Run
        -> Findings + approvals + active waivers
        -> signed Release Report
        -> production artifact
```

## Identity Model

- `capability_id`: logical business identity.
- `major_version`: public breaking-contract version.
- `capability_version_gid`: persistent identity for `capability_id@major`.
- `descriptor_revision_gid`: immutable full Descriptor content revision.
- `catalog_release_id`: immutable set of Descriptor revisions and Provider artifacts.
- `provider_artifact_hash`: executable Provider content identity.

All public governance identities are opaque strings. Database numeric keys remain internal.

## Gate Semantics

The static audit must fail for every invalid/missing count and must validate coverage declarations and source hashes. It must not claim runtime pass. The final signed gate rereads persisted Snapshot, Test Run, Findings, approvals, waivers, static audit, and source bindings. Missing, failed, skipped, not-run, stale, unverifiable, or mismatched inputs block release.

## Test Strategy

- Unit negative tests for each gate bypass.
- Parameterized contract cases for every stable Capability.
- Write-specific parameterized reliability cases.
- Gateway tests for release/lifecycle/provider binding and cross-release token replay.
- One end-to-end controlled release test proving persisted report readback and signature verification.

## Completion

Completion requires a current Catalog/Snapshot/Test Run, zero unwaived blocking Findings, a verified signed Release Report, and a structured residual Finding list. A static green report alone is not completion.
