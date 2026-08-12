# Capability V2 Acceptance Gates

The acceptance system has two deliberately different scopes.

- `offline` and `nightly` produce `validation_scope: contract`. Every stable
  Capability is bound to seven unique pytest verifier nodes. Missing, failed,
  skipped, xfailed or uncollected nodes fail strict mode. These gates validate
  frozen inputs, invalid-input rejection, authorization/resource-denial error
  contracts, output/consumer contracts and exact Catalog/version pins. They do
  not claim that every domain Provider was executed against production-like data.
- `release-candidate` produces `validation_scope: runtime_e2e` only after the
  same manifest-declared contract nodes pass and an external isolated-environment harness
  supplies exact runtime results for every Capability and case type.

## Commands

```powershell
python backend/scripts/build_capability_acceptance_manifest.py --check
python backend/scripts/run_capability_v2_acceptance.py --mode offline --strict
```

The checked-in report schema is `capability-v2-report.schema.json`. The runner
validates the report, recomputes its content hash, validates the immutable
Catalog model/hash and rejects any passed report with blockers, failed cases,
skips, a nonzero pytest status or an incomplete case count.

## Release-candidate evidence

The protected RC runner requires `AI00_ACCEPTANCE_RC_EVIDENCE` to point to JSON
matching `capability-v2-rc-evidence.schema.json`. Evidence must bind the exact
Git commit, workflow run identity, recent generation time, Catalog Release/hash,
latest platform migration checksum, the DomainManifest digest, every domain
migration checksum/artifact version, Provider artifact hashes and environment ID. It must
contain exactly the stable Capability keys and mark all seven runtime cases
`passed`. It must also contain exactly eleven successful owner-operation rows
and all 110 ordered cross-domain credential pairs with both reads and writes
marked `denied`. A stale document or a label without an executable external result is
rejected. The environment harness must rewrite the configured evidence path for
the current `AI00_ACCEPTANCE_RUN_ID`; a reusable static evidence document cannot
pass a later workflow run.

RC also requires:

- TLS-authenticated OceanBase plus a complete, checksum-matching migration ledger;
- all manifest-declared runtime and DDL database URLs (`AI00_<DOMAIN>_DB_URL`
  and `AI00_<DOMAIN>_DDL_DB_URL`) for the eleven domains;
- Provider CRUD evidence for every domain plus live owner-table read/zero-impact
  write probes and all 110 cross-domain database grant denials;
- OIS health JSON with `service: ois` and the exact `environment_id`;
- JWT and OAuth discovery JSON with configured exact issuers and HTTPS JWKS URIs;
- Local Runtime health JSON with `service: ai00-local-runtime`, protocol
  `ai00.local-operation.v2` and the exact environment ID;
- successful Agent, MCP and Windows .NET suites in the same sequential CI job;
- a clean Git working tree.

The repository does not fabricate RC evidence. The environment-owned E2E harness
must create it after exercising the real Gateway, Provider and consumer paths.

After the harness writes a Provider CRUD document bound to the current
`environment_id`, `run_id` and Git commit, generate the database evidence with:

```powershell
python backend/scripts/verify_domain_database_isolation.py `
  --provider-evidence .runtime/provider-crud.json `
  --output .runtime/database-isolation.json
```

The Provider document contains `schema_version: 1` and a `domains` object whose
keys are exactly the eleven domain IDs and whose values are all `passed`. Merge
the generated document's `database_isolation` member into the final
`AI00_ACCEPTANCE_RC_EVIDENCE` JSON. The verifier uses TLS, never prints database
secrets, rolls back owner probes and performs writes with `WHERE 1=0`.
