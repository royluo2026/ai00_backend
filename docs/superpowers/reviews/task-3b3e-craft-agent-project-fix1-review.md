# Task 3B.3e Craft / Agent / Project Fix R1 review

**Verdict: PASS** — no Critical or Important findings.

Reviewed backend `84699dc5f6d8deda41e2eb4974630f07fbe35ecf..a8569286062ad22ef83e9cd2b61b38c3f6376890`.  The frontend worktree remains exactly `6dd62900c9a82173adcbbe277bb38846ab556031` with no diff.

## Original findings resolved

- BOP GET/DELETE now carry line-range plus complete-source and snippet hashes.  The evidence binds the `bop_version` selector, `craft.bop.version.list`, and the archive operation's required `expected_revision`; its write envelope binds idempotency and approval forwarding.  Any altered lifecycle evidence fails closed.
- Approval reject records that the route is unregistered, then binds the reject function, compatibility-notification adapter, Project operation declaration, and Project's standard audit policy.  It remains unresolved and does not introduce a replacement capability.
- The focused module now completes independently: **3 passed, exit 0, 21.9 s**.  It covers all four Agent endpoints (including `canvas-options`) and mutations for BOP/approval evidence, occurrence ID/path/line/column/source hash, and ledger revision/hash.

## Reproduced checks

- Manifest `--check`: exit 0; 14 groups / 17 occurrences; all 14/17 unresolved.
- Atomic web contracts: **6 passed**; Catalog `--check`: exit 0 (`rel_a4a5a17ebc77419f6a12eec1f32fcbea`).
- Strict offline acceptance: exit 0; 3,178/3,178 validated, failed=0, skipped=0; its acceptance pytest reports 3,189 passed in 7.74 s.

The R1 diff changes only remediation evidence, tests, generated manifest, and task report: no Catalog, permission, BFF, Provider implementation, or frontend drift.  The report's substantive claims match the reproduced results.
