# Historical attachment upgrade

This implementation adds owner-scoped resolution for Project Task/Issue attachments, Knowledge entry attachments and document file references, Craft rule attachments, and BOP version pictures. Base owns only the immutable Artifact mapping; each domain reads and authorizes its own parent record before resolving a stored reference. New writes continue to carry typed ArtifactRefs.

Apply `202609080001_base_legacy_artifact_bindings.sql` with the existing deployment-only Base migration runner. Independent Base databases use `domains/base/0003_legacy_artifact_bindings.sql`. Both create the same idempotent mapping table; neither copies caller-supplied business records.

From the backend repository root, preview one bounded batch for the deployment's actor and tenant:

```powershell
python -m backend.scripts.migrate_historical_attachments --owner project --parent-type task --actor-gid ACTOR_GID --tenant-gid TENANT_GID --limit 100
```

Add `--apply` to persist immutable artifacts and bindings. Use `next_after` as `--after` while `has_more` is true. Repeat for `project/issue`, `knowledge/entry`, `knowledge/item`, `craft/rule`, and `craft/bop_version`. Rerunning a batch returns the existing reference. If `rejected` is nonempty, correct the authoritative parent/storage metadata and rerun that batch; the script exits nonzero and does not treat rejected parents as migrated.

The script accepts no object key, download URL, arbitrary local path, or attachment manifest. It derives references from bounded owner queries, verifies active owner and tenant, rejects inaccessible or dangling parents, validates configured storage locations, and pins content hash, byte size and MIME. Previously unlabelled content is verified and pinned when first migrated. Only paths below the fixed backend uploads directory or the configured owner object stores are eligible; arbitrary local files remain rejected. Each runtime resolve rechecks parent membership and the immutable artifact's integrity. Historical rows without authoritative owner/tenant proof require business-data repair before migration.

Run the local fixture without any production service:

```powershell
python -m pytest backend/tests/test_desktop_historical_attachments.py -q
```

It executes actual owner SQL through SQLite, actual Artifact storage and actual Gateway/policy handlers. Only database dialect, storage transport and identity records are deterministic test ports. Production data migration has not been executed; `runtime_verified=false` and `human_approved=false`.
