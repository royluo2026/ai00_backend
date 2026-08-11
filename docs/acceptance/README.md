# Capability V2 Acceptance Gates

The acceptance system has two deliberately different scopes.

- `offline` and `nightly` produce `validation_scope: contract`. Every stable
  Capability is bound to seven unique pytest verifier nodes. Missing, failed,
  skipped, xfailed or uncollected nodes fail strict mode. These gates validate
  frozen inputs, invalid-input rejection, authorization/resource-denial error
  contracts, output/consumer contracts and exact Catalog/version pins. They do
  not claim that every domain Provider was executed against production-like data.
- `release-candidate` produces `validation_scope: runtime_e2e` only after the
  same 609 contract nodes pass and an external isolated-environment harness
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
latest migration checksum, Provider artifact hashes and environment ID. It must
contain exactly the stable Capability keys and mark all seven runtime cases
`passed`. A stale document or a label without an executable external result is
rejected. The environment harness must rewrite the configured evidence path for
the current `AI00_ACCEPTANCE_RUN_ID`; a reusable static evidence document cannot
pass a later workflow run.

RC also requires:

- TLS-authenticated OceanBase plus a complete, checksum-matching migration ledger;
- OIS health JSON with `service: ois` and the exact `environment_id`;
- JWT and OAuth discovery JSON with configured exact issuers and HTTPS JWKS URIs;
- Local Runtime health JSON with `service: ai00-local-runtime`, protocol
  `ai00.local-operation.v2` and the exact environment ID;
- successful Agent, MCP and Windows .NET suites in the same sequential CI job;
- a clean Git working tree.

The repository does not fabricate RC evidence. The environment-owned E2E harness
must create it after exercising the real Gateway, Provider and consumer paths.
