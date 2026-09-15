# Live tree read performance — test implementation

Classification: implementation optimization, simulation-owned Provider/Connector adapter and simulation UI consumer. No new Capability, contract, migration, model mutation, or production release.

Observed baseline: signed vismockup.tree.read@2 plan c25c0516759d16fb4722d86cffd75d8adb05586c674c957459d84ba85ccee896 leased at 06:50:35.919236 UTC and completed at 06:53:38.986978 UTC on 2026-09-15 (183 seconds). Result: 10,089 unique nodes, max_depth 8, 80 boundary nodes with unexpanded descendants. This is not a claim of a complete unlimited tree.

Root cause of avoidable work: fresh TreeAsync traversed COM children to build topology, wrote/read SQLite, then traversed COM children again to read visibility. The UI adapter could also issue overlapping force-refresh commands for the same workspace.

Changes: collect visibility during the fresh traversal and return those same nodes directly after cache persistence. Cached reads still verify live visibility/topology. Share only in-flight same-workspace reads; later refreshes query live again. Before/after document identity and workspace binding checks remain intact. No PLMXML export or geometry metadata acquisition added.

Verification: regression first failed for repeated traversal, then all 35 VisMockupSnapshotTests passed. Frontend concurrent-read regression first failed with two reads, then 34 adapter/bootstrap/collection/tree tests passed. These are machine tests, not a measured user-document speedup. Runtime performance after replacement is pending; no signed release/human governance approval is claimed.
