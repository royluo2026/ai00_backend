# Fixed shared-cache model opening

User scope: shared cache is an additional model source. Open its frozen geometry without latest Teamcenter assembly launch; preserve the direct TC source separately. User chose partial loading: unsupported placement remains unknown with a reason.

## Implemented

- Read-only pinned assembly projection validates batch/generation/hash and initial/final node count. Only frozen PLMXML relative/absolute fields and rendering references are consumed.
- Synthetic logical groups preserve the original tree. Accepted geometry is placed once using its frozen absolute transform in a separate geometry child. Missing own relative transforms are never inferred from absolute placeholders.
- Inspect/open capabilities validate source ownership, exact immutable file receipts and artifact access. Heavy preparation precedes the workspace transaction; final version, identity and runtime checks fence admission. Outcome-unknown operations are never automatically reissued.
- Generated PLMXML dependencies and open@2 receipts are content-hashed. Main alone completes exact document binding and grants. Native reuse requires full cache identity/content plus registered process/start/handle/source evidence.
- Cache tree control uses generated occurrence identities. Excluded geometry and incomplete ancestors remain unknown. Native loaded-subset visibility is kept separately from tree completeness.
- UI shows materialization stages, file counts and excluded reasons. External context changes invalidate in-flight UI work. Confirmed no-effect failures may be retried only on another explicit intent.

## Evidence

Real frozen W10 v2: 16,750 logical nodes, 16 excluded geometry nodes, 3,330 unique JT references; maximum sibling count 195; no missing revision identity. Original repeated-path mapping would have been 14,206,662 bytes; compact parent mapping is 4,405,181 bytes. A serializer size test using synthetic test artifact refs produces 41,054,019 XML bytes (not a real published geometry package). `.runtime/cache-assembly-reader-evidence.json` records the read-only checks.

Focused tests: 27 selection/serializer; 25 provider/reader including complete descriptor registration; 99 native cache open/registry/preparation/materializer selection; frontend integration agent verified 228 relevant tests and root pipeline verified 11 cases. These are scoped checks, not a whole-repository release gate.

## Runtime status / limits

App and Connector were normally restarted with new native/Main code; original VisView process 64624 was preserved. Backend release loaded the coordinated bulk signed-receipt verifier (PID78164). Actual App Gateway inspection returned 16,750 nodes / 3,330 files / 16 exclusions; warm request1.67s. Cold inspection exposed the Main15s timeout; narrowly scoped600s-provider-compatible660s /9MiB client transport budgets were added and verified by93 Main tests. Full W10 native import, physical dimensions and generated occurrence metadata mapping have not yet been verified end to end. Native cached mapping has a 32,768-node / 20-second bound and 65,536 registry capacity; visibility remains conservative on oversized subtrees. Native artifact staging remains within the existing 300-second lease cap and uses four authenticated workers. Failed/unknown native results must remain visible rather than be declared successful.

Historical capture-time bytes are not asserted by current exact-file acquisition; captured_bytes_verified=false remains provenance. Original cached snapshots are never rewritten.

## Follow-up runtime evidence

- Actual fixed-source acquisition completed two JT file plans. No cached native assembly has yet been opened.
- File acquisition is serial to respect Gateway capacity; admission backpressure retries preserve the exact payload and idempotency key. Pipeline regression count is now 12.
- Gateway capacity admission now precedes durable reliability claims. Its 44 focused tests pass; the fix is deployed in local backend PID109076.
- Native open@2 shared byte-cache reuse still requires a fresh leased artifact grant and verifies content/size/media. Its 97 focused regression tests pass; updated Connector PID68324 and App PID106812 are running. VisView PID64624 remains preserved.
- A fresh actual App Gateway inspect succeeded after deployment and saved 100 source members for read-only recovery correlation.
- Two pre-fix capacity rejections left started/null durable claims. Automatic approval review rejected deletion without explicit user authorization. No database recovery mutation was performed. Exact evidence capture and member/plan correlation precede any requested recovery approval.
- Full W10 staging, import, placement and visibility remain unverified; these unit and inspect checks are not end-to-end completion evidence.
