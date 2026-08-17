# BOP Line Compare Draft Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade `devteam.ai00.bop-line-compare` to 1.0.1 so published and unpublished BOP revisions can both be compared.

**Architecture:** Replace the published-only execution-structure read with the exact-revision preview capability. Carry the selected BOP summary's positive integer `revision` from the selector into the Mount invocation and fail closed when it is absent.

**Tech Stack:** Vanilla JavaScript ES modules, Node.js test runner, Manifest v2, Capability V2 Mount, Python release/signing tools.

## Global Constraints

- Keep exactly five declared capabilities; replace `craft.bop.execution_structure.get@1` with `craft.bop.execution_structure.preview@1`.
- Every structure preview must include `version_gid` and positive integer `expected_revision`.
- Do not modify the Craft Provider or weaken revision checks.
- Do not use subagents, create a worktree, push, merge, or disturb unrelated dirty files.
- Publish immutable version `1.0.1` and upgrade the existing local installation.

---

### Task 1: Exact-revision draft structure loading

**Files:**
- Modify: `packages/plugin-sdk/test/bop-line-compare-runtime.test.js`
- Modify: `packages/plugin-sdk/examples/bop-line-compare/plugin.json`
- Modify: `packages/plugin-sdk/examples/bop-line-compare/bop-runtime.js`
- Modify: `packages/plugin-sdk/examples/bop-line-compare/app.js`
- Modify: `packages/plugin-sdk/examples/bop-line-compare/README.md`

**Interfaces:**
- Change: `loadBopStructure(client, versionGid, expectedRevision, trace)`
- Consumes: BOP summary `{ version_gid, revision }` returned by `loadBopChoices`.
- Produces: the same `{ structure, lines }` result while invoking `craft.bop.execution_structure.preview@1`.

- [ ] **Step 1: Write the failing contract test**

```js
test('unpublished BOP loads an exact revision through preview', async () => {
  const client = fixtureClient();
  const trace = runtime.createTrace();
  await runtime.loadBopStructure(client, 'draft-bop', 7, trace);
  assert.deepEqual(client.calls.at(-1), {
    id: 'craft.bop.execution_structure.preview',
    payload: { version_gid: 'draft-bop', expected_revision: 7 },
  });
});
```

- [ ] **Step 2: Add a failing invalid-revision test**

```js
await assert.rejects(
  runtime.loadBopStructure(fixtureClient(), 'draft-bop', null, runtime.createTrace()),
  error => error.code === 'revision_required',
);
```

- [ ] **Step 3: Run the focused test and verify RED**

Run: `node --test --test-isolation=none packages/plugin-sdk/test/bop-line-compare-runtime.test.js`

Expected: FAIL because the runtime still invokes `craft.bop.execution_structure.get` and ignores revision.

- [ ] **Step 4: Implement the minimal runtime and Manifest change**

Use exactly this payload:

```js
{
  version_gid: versionGid,
  expected_revision: expectedRevision,
}
```

Reject non-integer or `< 1` revisions before invoking Mount with a public error whose `code` is `revision_required`.

- [ ] **Step 5: Pass the selected BOP revision from the DOM controller**

Resolve the selected summary from `state[side].bops` by `version_gid`, then call:

```js
loadBopStructure(client, selected.version_gid, Number(selected.revision), trace)
```

Change visible wording from “正式执行结构” to “指定修订版执行结构”.

- [ ] **Step 6: Update documentation and run GREEN verification**

Run:

```powershell
npm test --prefix packages/plugin-sdk
node --check packages/plugin-sdk/examples/bop-line-compare/app.js
node --check packages/plugin-sdk/examples/bop-line-compare/bop-runtime.js
```

Expected: all SDK tests pass and both syntax checks exit 0.

- [ ] **Step 7: Commit the product change**

```powershell
git add -- packages/plugin-sdk/examples/bop-line-compare packages/plugin-sdk/test/bop-line-compare-runtime.test.js
git commit -m "fix(plugin): compare unpublished BOP revisions"
```

### Task 2: Build, publish, and verify 1.0.1

**Files:**
- Runtime only: `.runtime/bop-line-compare-release/`; do not commit packages, signatures, tokens, or keys.

**Interfaces:**
- Consumes: the existing Devteam publisher key and runtime-only admin identity.
- Produces: approved and enabled plugin version `1.0.1` with exactly five Mount grants.

- [ ] **Step 1: Build immutable version 1.0.1**

```powershell
python packages/plugin-sdk/tools/build_release.py packages/plugin-sdk/examples/bop-line-compare --output-dir E:\Projects\ai00_v3\.runtime\bop-line-compare-release --version 1.0.1
```

- [ ] **Step 2: Sign without logging private key or token material**

Sign the detached release envelope with the existing runtime-only Ed25519 publisher private key and write only the signature file under `.runtime/bop-line-compare-release`.

- [ ] **Step 3: Upload, approve, and upgrade**

Use the existing local acceptance client and confirmation-token lifecycle to upload/review 1.0.1, invoke `plugin.upgrade`, then mark upgrade health as healthy.

- [ ] **Step 4: Verify the live Mount**

Assert registry version `1.0.1`, grant count `5`, presence of `craft.bop.execution_structure.preview: 1`, absence of `craft.bop.execution_structure.get`, and HTTP 200 for all six mounted assets.

## Self-Review

- Spec coverage: preview capability, exact revision, failure on missing revision, UI wording, tests, packaging, upgrade, and Mount validation are all mapped.
- Placeholder scan: no incomplete implementation or test steps remain.
- Type consistency: every caller uses the new four-argument `loadBopStructure` signature.
