# Teamcenter Bulk Cache Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan inline, task by task. Review independent changes before the controlled rollout.

**Goal:** Cache a 10000-occurrence vehicle using bulk TC reads and bounded durable snapshot pages, while continuing existing data and retaining all model links/fields.

**Architecture:** Bulk-expand the exact configured BOM once, persist a flat occurrence table locally, fill properties using set-based TC reads, and commit complete row pages and continuation receipts in the cloud. Version the existing local cache read contract to @2; preserve @1 and domain ownership.

**Tech Stack:** Existing Teamcenter Java SOA/Nashorn worker, .NET Connector, SQLite and Simulation Python repository/Gateway.

**Spec:** ../specs/2026-09-28-teamcenter-bulk-cache-design.md

## 1. Native bulk structure and property collection

- [ ] Add failing native tests proving one `expandPSAllLevels` for 10000 occurrences, bounded grouped `getProperties`/geometry calls, zero TC calls during row formatting, exact paths and root/parent ordering.
- [ ] Extract existing raw-field projection from TC fetching without changing legacy behavior; add bulk collection helpers and private bounded structure-manifest/page/property commands.
- [ ] Validate required service errors, optional unavailable fields, complete occurrence paths, cycle/depth/node bounds and topology fingerprint; retain source/date/session fencing.
- [ ] Run native session and metadata regressions plus the scale test; record actual counts and timing separately from mocked evidence.

## 2. Durable Connector snapshot and @2 contract

- [ ] Add @2 closed read input/output and hash binding while preserving @1 advertisement/dispatch.
- [ ] Add local SQLite snapshot metadata/flat rows, structure checkpoint and complete property pages. Reuse the existing credential gate and private read session.
- [ ] Add tests for cold capture, replay after restart, unfinished structure/property pages, principal/source/fingerprint drift, cancellation, missing paths and byte-limited pagination.
- [ ] Update Host read-operation classification and version/hash tests; run relevant .NET tests and build from the active test source preserving unrelated changes.

## 3. Cloud flat page checkpoint and legacy batch upgrade

- [ ] Add failing actual repository/Gateway tests for page receipt/upsert/continuation atomicity, replay, malformed IDs/count/generation, rollback, final graph and a legacy batch with an admitted operation.
- [ ] Add internal snapshot/superseded task handling; choose @2 only when the bound Connector contract is supported. Preserve old rows/receipts and reject incompatible topology.
- [ ] Update Simulation Provider Descriptor/dependencies, Catalog generation and governed consumer evidence; keep trusted-super-admin/manual-only policy and transaction enlistment.
- [ ] Verify a synthetic 10000-node transfer requires bounded page tasks, not per-node work, and pause/resume cannot queue new work outside the locked state.

## 4. App integration, controlled W10 evidence and monitoring

- [ ] Finish progress polling regression (last rendered version, no overlap, low-frequency/hidden-page behavior) and run existing frontend model-cache tests.
- [ ] Independently review the bulk implementation, fix actionable findings and rerun relevant checks.
- [ ] Integrate only Simulation/required Host changes into test with backups and concurrent-edit guards; prepare new contract/artifact evidence through existing test-governance tooling.
- [ ] Load the verified artifacts into the current App's Connector at a settled operation boundary; preserve user App state and coordinate backend availability without taking over the Agent repair.
- [ ] Continue original W10 batch; record TC expansion/property/JT request counts, cloud page count, rows per page, bytes, completed throughput, receipts and errors. Verify important raw values/model links against actual TC samples.
- [ ] Update the read-only heartbeat and snapshot for page progress/superseded work; keep notifications quiet except actionable changes. State machine/runtime/human evidence separately.

## Review focus

Existing observe has weaker UID/configuration/error handling than cloud children: reuse APIs, not those semantics. Old accepted rows must not disappear during upgrade. Snapshot generation and exact occurrence identity must be checked both locally and before cloud publication. A local page replay may not receive new capture timestamps/body hashes. Cap native frames and escaped cloud envelopes independently. No claim of wall-clock speedup before the actual W10 run.
