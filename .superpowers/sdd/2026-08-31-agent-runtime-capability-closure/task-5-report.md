# Task 5 Report — Zero-remainder structural governance

## Outcome

The source-derived structural closure is complete. The canonical manifest
conserves all 14 groups / 17 occurrences from immutable backend and frontend
Git objects and reports unresolved 0 groups / 0 occurrences.

- Project remains 3 groups / 3 occurrences migrated.
- Craft remains 7 groups / 9 occurrences closed: 2 groups / 4 occurrences
  migrated and 5 groups / 5 occurrences removed as dead entries.
- Agent closes the final 4 groups / 5 occurrences through exactly four stable
  capabilities:
  - `POST /api/flows/test-node` (2 occurrences) →
    `agent.workflow.node.test.execute@1`
  - `POST /api/skills/canvas-options` (1) →
    `agent.canvas.options.resolve@1`
  - `POST /api/skills/execute-canvas` (1) →
    `agent.canvas.execution.start@1`
  - `POST /api/skills/resume-canvas` (1) →
    `agent.canvas.execution.resume@1`

Every Agent row carries pinned provider, closed contract, bounded runtime,
durable repository/migration, shared Gateway, and exact frontend call-site
anchors. Both node-test callers also carry their source-derived
`idempotencyKey` anchors. The four retired route strings are absent from the
six source and production caller files and no compatibility fallback exists.

## Frozen identities

- Reviewed Agent backend source revision:
  `d56c743dee03112b2a3211a4ccb659ebed9cfda5`
- Agent backend source tree: `9ec7401102fc337bd2b1a77361eae9e52b817478`
- Reviewed frontend revision:
  `08359de59e756ce73c61df9818c7e7bcaeb86975`
- Frontend tree: `3c3156841af0d4bf2833dba8184b071265993965`
- Agent frontend scanner materialization: 224 Git-tree documents,
  `sha256:2fe79af7f2d8b15397230b0c5383ea421e4ccff9e4581959e8da03ef206df992`
- Reviewed product implementation commit:
  `f8600159eb57b49e51a54929cdba813bd99752f3`
  (`docs: close remaining structural capability governance`).
- Clean source checkpoint:
  `d56c743dee03112b2a3211a4ccb659ebed9cfda5`.
- Governance evidence/acceptance commit:
  `3bfbd3f6498364a248b6253e0362c3a087c6a1f4`
  (`docs: freeze reviewed Agent capability governance`).
- Structural manifest content identity:
  `sha256:3e4daf840b1ab4e98786f602e8a9271ec38deb9a6c32db5639ac97a69fdc1cc8`
- Structural manifest file identity:
  `sha256:09c31126cfc0ae0619892548db1b5fd81bdb7fb37a08f93716adf3c4f274d3dc`
- Deployable frontend scan: 219 committed files, zero findings, content identity
  `eb04a871878f77bf700a332dd568c6293e0f3f79de2e21acc21cebaef34b0ab1`;
  report file identity
  `sha256:b08457954e6ee66071db84e3d4024776eb2d2c50dd2760a34b1925f49675b7d3`.

## Evidence chain

The established chain was regenerated and checked serially in dependency
order: wrapper contracts, pinned route inventory, root-cause ledger, atomic
contracts, canonical Craft/Agent/Project remediation, historical migrations,
Base and Integration remediation, structural plan, special residuals,
official-domain provider trust, Catalog, capability docs, normal and strict
User Function Registry, and acceptance manifest.

- Pinned route inventory: 369 occurrences; 38 capability, 310 registered
  legacy, 2 BFF, 19 operations-excluded, 0 unresolved.
- Canonical structural remediation: 14/17 closed, 0/0 unresolved.
- Base remains 16 groups / 33 occurrences migrated.
- Integration remains 12 groups / 12 occurrences migrated.
- Historical plan remains 37 groups / 45 occurrences.
- Existing migrations remain 53/80 (22 migrated, 31 reclassified).
- Atomic contracts remain 48/71 (36 migrated, 12 reclassified).
- Provider trust manifest:
  `sha256:ba5483b5bfb0713e95556ae7360abdd95a33df86035e3cc871b8e4891b285ff2`.
- Catalog: `rel_b79f7e734da4b72dbf4af4adbf91bb37`, 495 descriptors,
  `sha256:b79f7e734da4b72dbf4af4adbf91bb3715b3ffe41e3c6252f0b2165152c211e5`.
- Acceptance manifest: 479 stable capabilities.

The reviewed backend checkpoint freezes the confirmed-write idempotency policy
for `agent.workflow.node.test.execute@1`; the regenerated Agent evidence also
binds both frontend node-test callers that supply the idempotency key.

## Verification

- Complete Agent suite: 120 passed, 4 skipped; the four skips are only the
  controlled external SQL cases.
- Focused Project/Craft/Web governance batch: 83 passed.
- Focused structural manifest batch: 29 passed.
- Agent migration check: `domain=agent migrations=3 mode=check`.
- Dependency gate: one reviewed historical violation, no new dependencies.
- Agent frontend idempotency behavior: 14 passed.
- Full frontend runner: Web 134/134 plus all surrounding governance scripts.
- Production frontend build: passed; source/dist caller hashes match.
- All generator check modes and `git diff --check`: passed serially.

## Strict offline acceptance and machine evidence

Strict offline acceptance ran on clean governance commit
`3bfbd3f6498364a248b6253e0362c3a087c6a1f4`.

- Status/scope: `passed` / `contract`; clean tracked tree: true.
- Stable capabilities: 479.
- Declared/validated: 3,353 / 3,353.
- Failed/skipped/blockers: 0 / 0 / 0.
- Acceptance tests: 3,364 passed in 7.98 seconds.
- Report ID:
  `sha256:e1fca15d22cad6b65c06d4868aca9a5a960d7661e2b1cb6cfb221610dbd84c59`.
- Raw snapshot:
  `docs/acceptance/agent-runtime-capability-closure.json`,
  `sha256:34ec7283af428e6fefd3297badd3b494660df1416a129b8cabe5500d718ca425`.
- Replay-stable normalized projection:
  `docs/acceptance/agent-runtime-capability-closure.normalized.json`,
  `sha256:1f2a9992ae121c4b3390b34b875240975e93fa2950b27c9126eb84f4ce43f56e`.
- Identity manifest:
  `docs/acceptance/agent-runtime-capability-closure-evidence.json`,
  `sha256:c2add19bdc21e1fcdc1276aeaba329de60f61807c8be34f38279b5269553c2c1`.

## Explicit pending and retained debt

The controlled real MySQL/OceanBase Agent concurrency gate is **pending** for
tomorrow's runtime acceptance. This host has no `AI00_AGENT_TEST_DB_URL` or
dedicated DDL+DML test database. Mandatory mode failed closed with exactly four
setup errors; the gate is neither passed nor suppressed.

The repository-wide completion advisory remains separate and unchanged:
`coverage_invariant:stable_functions:922!=920`.

Reviewed-disposition debt also remains separate: 151 `target_replaced`, 142
`target_not_stable`, 14 missing reviewed dispositions, and 6 Integration
source-evidence mismatches. Normal registry generation/check passes; strict
review linkage exits non-zero and was not relabelled or suppressed.
