# Phase 50 — Knowledge Capability contract alignment

Date: 2026-08-06
Branch: `codex/capability-wave-a`

## Scope implemented

- Registered the approved Knowledge interfaces: space search/create, document get/create/revise/diff/history/restore, and bounded context retrieval.
- Retained `knowledge.space.list`, `knowledge.document.revisions`, and `knowledge.document.rollback` only as deprecated, non-plugin-callable aliases with explicit replacements.
- Removed document ACL management operations from the public Capability registry. The legacy helper functions and existing SQL enforcement remain internal pending the separately acknowledged team-open-collaboration access migration.
- Added optimistic concurrency to revise/restore via mandatory `base_revision_gid` and stable `revision_conflict` failures before OIS writes.
- Added immutable revision attribution for channel, delegated user, Agent run, plugin identity/version, request ID, before/after SHA-256, and change summary.
- Added bounded context retrieval with a hard maximum of 10 immutable document/revision references. It does not return full Markdown bodies by default.

## Retrieval ladder status

1. Explicit attachments: implemented.
2. Ontology relations: intentionally returns no fabricated candidates until ontology Tasks 7–10 provide governed release reads.
3. Tenant-scoped metadata search: implemented.
4. Full text: reserved retrieval-method value; no dedicated index is claimed yet.
5. Semantic similarity: intentionally returns no candidates until a governed semantic index exists.

## Access-control decision checkpoint

The approved product model is team-open collaboration inside one tenant: all authenticated tenant members can read and revise, with immutable attribution. This commit does not yet remove legacy document ACL SQL predicates because that is an access-expanding migration. Tenant scoping remains mandatory. The final switch must be applied as an explicit governance change and verified with cross-tenant denial tests.

## OceanBase MySQL evidence

- Migration `202608060002_knowledge_revision_attribution.sql` uses replay-safe `ADD COLUMN IF NOT EXISTS` statements.
- No PostgreSQL casts, JSONB, RETURNING, or schema creation is introduced.
- The original immutable migration `202608040003_knowledge_markdown_revisions.sql` was not edited, preserving migration checksums.

## Verification

Command:

```text
.\.venv\Scripts\python.exe -m pytest backend\tests\test_knowledge_contract_alignment.py backend\tests\test_knowledge_document_capabilities.py backend\tests\test_knowledge_revision_store.py backend\tests\test_versioned_migration_files.py backend\tests\test_oceanbase_compatibility.py backend\tests\test_knowledge_migration_control.py backend\tests\test_knowledge_migration_preflight.py backend\tests\test_capability_kernel_contract.py -q
```

Result: `43 passed in 4.48s`.

Compile verification completed for all modified Knowledge Capability and preflight Python modules.

No database connection, deployment, push, or remote mutation was performed.
