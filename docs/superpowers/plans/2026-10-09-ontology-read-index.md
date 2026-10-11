# Ontology read index

User approved continuation of the semantic workspace performance package on 2026-10-09.

Scope: actual plugin provider in plugins/ontology/ontology_backend. Keep ontology read v1 and v2 schemas and business hashes unchanged. No deployment or database migration.

1. Add a process-local immutable-release index: exact GID lookup, inheritance ownership, sorted kind pages and bidirectional concept adjacency. Cache bounded by entries and estimated bytes; coalesce concurrent builds, isolate connection factory, database configuration, table prefix, release GID and content hash. Do not cache active pointers or failed builds. Return copies.
2. Route v2 schema inheritance through the indexed lineage instead of repeated release scans. Keep v1 projection unchanged.
3. Register ontology.object.list@3: lightweight graph projection, optional around_gid for all incoming/outgoing one-hop connections. Bounded deterministic pages with total, release identity and hash. Keep existing versions available. Declare provider business invariants.
4. Update semantic workspace to v3 graph reads and on-demand adjacent summaries; retain domain filters, focus labels and stale-selection guards.
5. Verify inheritance parity, cache eviction/isolation/concurrency/retry, reverse adjacency, pagination, closed contracts and immutable legacy hashes. Measure synthetic 1k/5k/10k indexes separately from database/network latency.

Cold access still reads one whole immutable release. Warm queries reuse the index; very large releases exceeding the cache byte budget are returned without retention. Persisted summary tables and WebGL/LOD remain later stages requiring actual cold-start measurements.

Governance status: source and local test evidence only; no human release approval or deployed runtime verification is claimed.

## Verification

- Backend focused regression: 52 passed (index, immutable read versions, legacy concept capability and release repository suites).
- Frontend focused regression: 26 passed (model, app, graph and Desktop entry).
- Desktop local production bundle built successfully; this is a local artifact, not installation or deployment.
- Independent review found alias-search regression and multi-edge focus deduplication; both reproduced with failing tests and fixed.
- Synthetic 1k/5k/10k entities (3 objects per entity): cold verified index construction ~56/283/559 ms; warm detail plus neighbourhood median ~0.069 ms. 100 warm reads each reuse the one full-release load. Benchmark excludes DB, HTTP, gateway, render and reference envelopes. Estimated 10k index size ~39.6 MB, not a measured memory ceiling. Source: backend/scripts/benchmark_ontology_read_index.py; output: E:/Projects/ai00_v3/output/ontology-read-performance.json.
- Whole-system candidate catalog generation is blocked by existing provider_artifact_mismatch: agent. Official trust manifests were not rewritten or bypassed. Ontology v3 descriptor validated through focused registration/schema/business-definition tests; deployed runtime remains unverified.
- Neighbour fetching is bounded to 2000 graph objects and explicitly reports truncation. Overview retains the 500 entity / 1500 relation display range; switching focus removes previous additions rather than accumulating an unbounded graph.

## Local runtime follow-up

The live local catalog had no ontology.object.list@3, so the new frontend failed catalog resolution. Updated the existing unpublished local runner's artifact pin scope to include ontology, retaining the normal artifact verification. Preflight built an 871-descriptor local catalog, then restarted only the loopback 8080 backend with the existing test_ selection. No checked-in official release or remote deployment changed.

Real authenticated Desktop bridge reads succeeded for release.get@1, object.list@3, concept.get@2 and selected neighbourhood list@3. A full shared workspace loaded through the same authenticated parent bridge: 44 nodes, selected entity details and no graph error. Evidence: E:/Projects/ai00_v3/output/ontology-runtime-verification.json. This confirms the local test runtime only.

Frontend now retains structured error codes and falls back to object.list@2 only for v3 catalog_resolution_failed. Legacy mode explicitly says neighbourhood completion is unavailable; authorization and release/hash mismatches still fail. Refresh clears this negotiated version so a newly available v3 can be tried again.
