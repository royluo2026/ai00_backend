# Simulation Environment Round-trip Readiness — 2026-09-10

## Delivered engineering slices

- Streaming, bounded PLMXML import/export with dependency and cycle checks.
- Database model for primary/inserted documents, alternate hierarchies,
  placements, session documents and materialization verification.
- Deterministic single-entry runtime-package builder and semantic readback
  verifier.
- App v2 lease-scoped Artifact download for VisMockup open/insert/attach, with
  size and SHA-256 verification and atomic local publication.
- Governed `simulation.vismockup.model.insert.request@1` and local
  `vismockup.model.insert@1` binding.
- Desktop model-document UI: first PLMXML is primary; later PLMXML/JT documents
  are persisted and synchronized to VisMockup.
- Craft Fork now exposes an immutable governed projection and Simulation can
  idempotently materialize or repair a BOP-derived alternate hierarchy without
  cross-domain SQL.
- Frozen environments expose a replay action that stages the complete package,
  opens exactly one generated top-level PLMXML and performs a dependent VM-tree
  readback in the same signed Connector plan.
- Alternate hierarchies can be created, selected, renamed and archived; model
  documents can be placed on BOP-derived nodes and placements can be removed.
- Equipment, fixture, tool and socket requirements are loaded through the
  governed Craft resource search and can be placed into the active hierarchy.
- Frozen replay outcomes now use a dedicated plan-bound projection. Successful
  open/tree readback is persisted as `read_back`, never as semantic runtime
  verification.
- Frozen runtime replay is reconstructed only from the hash-verified frozen
  manifest, so later edits to the live workspace cannot change a saved version.
- Device-bound documents retain their Connector device binding and fail closed
  when replayed through a different device.

## Verification run

| Check | Result |
|---|---|
| Simulation + Connector outcome + Craft Fork focused suite | PASS — 172 tests |
| Connector AppHost/materializer/recovery/VisMockup focused suite | PASS — 88 tests |
| Simulation P0 browser boundary | PASS |
| Electron security boundary | PASS |
| Production web build | PASS |
| Frozen Provider/Catalog/docs deterministic checks | PASS — 762 descriptors/pages |
| Single database schema compile | PASS — 334 tables, 3,857 columns, no unsupported statements |
| Simulation domain migration policy | PASS — 20 resumable migrations |
| Offline governance scan | PASS — `completed`, snapshot `sha256:689dd6a9eb18b8541dad78bbea27688b33a498b4bdb4201b7b945c382bb02c01` |

## Blocking gaps before product approval

1. Runtime-package replay currently proves exact Artifact staging, one-root open
   and a complete VM-tree readback. Persisted semantic verification of every
   hierarchy name, document hash and sampled scene operation remains pending a
   real VisMockup pilot; unit evidence must not be interpreted as runtime approval.
2. Imported external PLMXML/JT references are persisted as unresolved
   dependencies until a governed Artifact/device-token resolution workflow is
   completed; such drafts correctly remain unmaterializable.
3. Placement targets are hierarchy/workspace/tenant checked, but external Craft
   resource references still require exact owner-domain version/hash resolution
   before stable promotion.
4. App v2 capture Artifact upload remains fail-closed as
   `v2_artifact_upload_unavailable`; document open/insert is supported.
5. No post-change real end-to-end VisMockup replay/readback and interruption
   recovery pilot has been recorded.
6. The clean-tree business-rule audit is intentionally unavailable while this
   shared worktree contains uncommitted work. A commit/review boundary is needed
   before that proof can be generated.

## Decision

Engineering milestone: **ready for local integration and VisMockup pilot testing**.
Production/stable promotion: **blocked** by the six items above. No human or
runtime approval is inferred from unit tests or the offline scan.
