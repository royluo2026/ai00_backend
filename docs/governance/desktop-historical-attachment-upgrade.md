# Historical attachment upgrade

This implementation adds owner-scoped resolution for Project Task/Issue attachments, Knowledge entry attachments and document file references, Craft rule attachments, and BOP version pictures. Base owns the independent upload-provenance registry and immutable Artifact mapping. Each domain reads and authorizes its parent record, and Base separately requires trusted object ownership and an exact signed grant to that parent. A business parent containing an object key or file path is never upload ownership evidence. New writes continue to carry typed ArtifactRefs.

Apply `202609080001_base_legacy_artifact_bindings.sql` with the existing deployment-only Base migration runner. Independent Base databases use `domains/base/0003_legacy_artifact_bindings.sql`. Both create the same idempotent mapping table; neither copies caller-supplied business records.

Also apply `202609080002_base_historical_uploads.sql` (independent Base: `domains/base/0004_historical_uploads.sql`). Its UPDATE/DELETE triggers make provenance append-only. Use the existing versioned migration runner; it applies each trigger definition once.

Before resolving historical objects, a deployment administrator must assemble independent original upload transaction records or audited storage ownership evidence. Never derive ownership from caller-writable parent fields. The signed manifest must include storage backend/key, tenant, object owner, uploader, SHA-256, byte size, MIME, display name, original upload timestamp, and exact allowed `{owner_domain,parent_type,parent_gid}` grants. Allowed kinds are Project task/issue, Knowledge entry/item and Craft rule/bop_version. Different tenant/owner, changed content, unknown parent and missing provenance are rejected before storage I/O, including previously cached bindings.

The importer accepts `{manifest,signature}`. `manifest` has exactly `schema_version:1`, `signer_gid`, timezone-qualified `signed_at`, and 1¨C500 `objects`. Each object has exactly the fields in `backend/scripts/import_historical_upload_provenance.py:FIELDS`; `source_kind` is `upload_transaction` or `admin_migration_attestation`, and `source_ref` cites the independent audit evidence. Sign canonical UTF-8 JSON (`sort_keys=True`, `ensure_ascii=False`, compact separators, no NaN) with the deployment administrator's Ed25519 private key; `signature` is base64. Configure only the public PEM in `AI00_ATTACHMENT_BACKFILL_PUBLIC_KEY_PEM` outside request input. The signer must remain an active Base `super_admin`; owner and uploader must be active in the recorded tenant. No signing key, manifest generation from business rows, or public writer API is provided.

```powershell
python -m backend.scripts.import_historical_upload_provenance --manifest audited-uploads.signed.json
python -m backend.scripts.import_historical_upload_provenance --manifest audited-uploads.signed.json --apply
```

Default mode validates and previews. `--apply` only inserts; a repeated identical object is skipped and a conflicting immutable record is rejected. The signature, signer/key fingerprint, signed timestamp and manifest digest are retained with each object. Keep the signed source manifest in the deployment audit archive. Normal application writes cannot create this registry row. The existing typed Artifact upload tables cover new uploads; they do not supply provenance for arbitrary pre-Artifact OIS/MinIO/local keys, so they are not inferred as historical evidence.

After this trusted backfill, preview one bounded attachment migration batch for the deployment's actor and tenant:

```powershell
python -m backend.scripts.migrate_historical_attachments --owner project --parent-type task --actor-gid ACTOR_GID --tenant-gid TENANT_GID --limit 100
```

Add `--apply` to persist immutable artifacts and bindings. Use `next_after` as `--after` while `has_more` is true. Repeat for `project/issue`, `knowledge/entry`, `knowledge/item`, `craft/rule`, and `craft/bop_version`. Rerunning a batch returns the existing reference. If `rejected` is nonempty, correct the authoritative parent/storage metadata and rerun that batch; the script exits nonzero and does not treat rejected parents as migrated.

The script accepts no object key, download URL, arbitrary local path, or attachment manifest. It derives references from bounded owner queries, verifies active owner and tenant, rejects inaccessible or dangling parents, validates configured storage locations, and pins content hash, byte size and MIME. Content hash, size and MIME must match the independent registry; unregistered content remains inaccessible. Only paths below the fixed backend uploads directory or the configured owner object stores are eligible; arbitrary local files remain rejected. Each runtime resolve rechecks parent membership and the immutable artifact's integrity. Historical rows without independent upload provenance and an authorized parent grant require audited administrator backfill before migration.

Run the local fixture without any production service:

```powershell
python -m pytest backend/tests/test_desktop_historical_attachments.py -q
```

It executes actual owner SQL through SQLite, actual Artifact storage and actual Gateway/policy handlers. Only database dialect, storage transport and identity records are deterministic test ports. Production provenance backfill and data migration have not been executed; `runtime_verified=false` and `human_approved=false`.
