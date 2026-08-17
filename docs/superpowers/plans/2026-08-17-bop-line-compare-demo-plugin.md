# BOP Line Compare Demo Plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build, package, publish, and locally verify an installable `devteam.ai00.bop-line-compare` plugin that compares one BOP line across two vehicle projects and exposes its Capability V2 orchestration.

**Architecture:** Keep all business comparison logic in pure JavaScript modules and all platform access behind `Ai00PluginClient`. The sandboxed UI invokes only five declared read capabilities, projects their results into a normalized line model, and renders two-column process, part, and tool comparisons plus a safe orchestration trace.

**Tech Stack:** Vanilla JavaScript ES modules, HTML/CSS, AI00 Plugin SDK Manifest v2, Node.js built-in test runner, Python release tooling, Capability V2 Mount.

## Global Constraints

- Plugin ID is exactly `devteam.ai00.bop-line-compare`.
- The plugin is read-only and must not use direct REST, database access, Cookie access, host DOM access, OIS, Electron IPC, shell access, or secrets.
- The only business capabilities are `base.project.search@1`, `craft.bop.version.list@1`, `craft.bop.execution_structure.get@1`, `craft.bop.work_package.get@1`, and `craft.bop.linked_parts.get@1`.
- Matching precedence is exact VPPS, then explicitly labeled description similarity, then user-selected fuzzy-search candidates.
- Parts and tools are compared in the context of selected operations and do not require VPPS.
- Missing tool names are rendered as governed references; the plugin must not invent names.
- Use a high-contrast dark surface; do not use white backgrounds with gray text.
- Do not create a subagent, a new worktree, push, or merge.
- Preserve unrelated dirty files and the existing handoff/review directories.

---

## File Structure

- `packages/plugin-sdk/examples/bop-line-compare/plugin.json`: Manifest v2 identity, runtime, capability permissions, and uninstall policy.
- `packages/plugin-sdk/examples/bop-line-compare/compare-engine.js`: Pure normalization, matching, ranking, and common/unique set comparison.
- `packages/plugin-sdk/examples/bop-line-compare/bop-runtime.js`: Capability invocation orchestration and safe trace records.
- `packages/plugin-sdk/examples/bop-line-compare/app.js`: DOM controller, request-generation cancellation, selection flow, and rendering.
- `packages/plugin-sdk/examples/bop-line-compare/index.html`: Semantic plugin page and fixed UI regions.
- `packages/plugin-sdk/examples/bop-line-compare/style.css`: High-contrast responsive plugin presentation.
- `packages/plugin-sdk/examples/bop-line-compare/ai00-plugin-sdk.js`: Release-local SDK client copied from the existing example pattern.
- `packages/plugin-sdk/examples/bop-line-compare/README.md`: Build, install, usage, and capability-orchestration explanation.
- `packages/plugin-sdk/test/bop-line-compare.test.js`: Pure matching and comparison tests.
- `packages/plugin-sdk/test/bop-line-compare-runtime.test.js`: Manifest, orchestration order, partial failure, trace safety, and source-policy tests.
- `backend/scripts/bop_line_compare_acceptance.py`: Signed upload/review/install/enable/Mount/disable/uninstall smoke path, adapted from the existing project-readiness acceptance tool.

### Task 1: Pure line comparison engine

**Files:**
- Create: `packages/plugin-sdk/examples/bop-line-compare/compare-engine.js`
- Create: `packages/plugin-sdk/test/bop-line-compare.test.js`

**Interfaces:**
- Produces: `normalizeText(value): string`
- Produces: `operationSearchScore(query, operation): number`
- Produces: `alignOperations(leftOperations, rightOperations): { exact: Match[], fuzzy: Match[], unmatchedLeft: object[], unmatchedRight: object[] }`
- Produces: `searchOperationCandidates(query, operations, limit = 8): RankedOperation[]`
- Produces: `compareRefs(leftRefs, rightRefs): { common: string[], leftOnly: string[], rightOnly: string[] }`
- Match shape: `{ left, right, method: 'vpps'|'description', score: number, reasons: string[] }`

- [ ] **Step 1: Write failing tests for exact VPPS precedence**

```js
test('alignOperations prefers exact non-empty VPPS', () => {
  const result = alignOperations(
    [{ operation_id:'l1', name:'拧紧后副车架', parameters:{vpps:'TA-340'} }],
    [{ operation_id:'r1', name:'后副车架拧紧', parameters:{vpps:'TA-340'} }],
  );
  assert.equal(result.exact.length, 1);
  assert.equal(result.exact[0].method, 'vpps');
  assert.equal(result.fuzzy.length, 0);
});
```

- [ ] **Step 2: Write failing tests for description and manual fuzzy search**

```js
test('description match is labeled fuzzy and manual query ranks both variants', () => {
  const left = {operation_id:'l1', name:'安装前门线束', parameters:{vpps:null}};
  const right = {operation_id:'r1', name:'前门线束装配', parameters:{vpps:null}};
  const aligned = alignOperations([left], [right]);
  assert.equal(aligned.fuzzy[0].method, 'description');
  assert.ok(aligned.fuzzy[0].score < 1);
  assert.equal(searchOperationCandidates('前门 线束', [left], 8)[0].operation.operation_id, 'l1');
});
```

- [ ] **Step 3: Write failing tests for common and side-only resource references**

```js
test('compareRefs returns deterministic common and side-only sets', () => {
  assert.deepEqual(compareRefs(['part:a','part:b'], ['part:b','part:c']), {
    common:['part:b'], leftOnly:['part:a'], rightOnly:['part:c'],
  });
});
```

- [ ] **Step 4: Run the focused test and verify it fails**

Run: `node --test packages/plugin-sdk/test/bop-line-compare.test.js`

Expected: FAIL because `compare-engine.js` does not yet exist.

- [ ] **Step 5: Implement deterministic normalization, bigram similarity, matching, ranking, and reference-set comparison**

Implementation rules:

```js
const vppsOf = operation => String(operation?.parameters?.vpps || '').trim();
const matchThreshold = 0.46;
// Exact matches consume operations first. Fuzzy matching may only consume each
// remaining operation once and must preserve the score and visible reasons.
// Sorting ties: score descending, then operation_id ascending.
```

- [ ] **Step 6: Run the focused test and verify it passes**

Run: `node --test packages/plugin-sdk/test/bop-line-compare.test.js`

Expected: all tests PASS.

- [ ] **Step 7: Commit the engine slice**

```powershell
git add -- packages/plugin-sdk/examples/bop-line-compare/compare-engine.js packages/plugin-sdk/test/bop-line-compare.test.js
git commit -m "feat(plugin): add BOP line comparison engine"
```

### Task 2: Capability orchestration runtime and manifest

**Files:**
- Create: `packages/plugin-sdk/examples/bop-line-compare/plugin.json`
- Create: `packages/plugin-sdk/examples/bop-line-compare/bop-runtime.js`
- Create: `packages/plugin-sdk/test/bop-line-compare-runtime.test.js`

**Interfaces:**
- Consumes: `alignOperations`, `searchOperationCandidates`, and `compareRefs` from Task 1.
- Produces: `createTrace(): TraceCollector`
- Produces: `searchProjects(client, query, trace): Promise<ProjectRef[]>`
- Produces: `loadBopChoices(client, projectRef, trace): Promise<BopChoice[]>`
- Produces: `loadBopStructure(client, versionGid, trace): Promise<{ lines, structure }>`
- Produces: `loadLineContext(client, versionGid, lineGid, trace): Promise<LineContext>`
- Produces: `buildComparison(leftContext, rightContext): ComparisonModel`
- Trace item shape: `{ capability_id, major, purpose, status, duration_ms, summary, error_code? }`; raw payloads and tokens are forbidden.

- [ ] **Step 1: Write a failing manifest contract test**

Assert exact plugin ID, `sandbox: 'allow-scripts'`, version `1.0.0`, and equality between permissions and the five required capability IDs with `major: 1`.

- [ ] **Step 2: Write failing runtime tests with a fake Mount client**

The fake client records `invoke(id, payload)` and returns fixtures for project search, BOP list, execution structure, work package, and linked parts. Assert that selecting two lines produces calls only to the five allowlisted IDs and returns a comparison model with non-empty process, part, and tool material.

- [ ] **Step 3: Write failing partial-failure and trace-safety tests**

Reject the right-side work-package call with `{code:'permission_denied'}`. Assert the left context remains available, the right error is typed, and serialized trace text contains neither `token` nor the fake raw secret `DO_NOT_LEAK`.

- [ ] **Step 4: Run the focused tests and verify they fail**

Run: `node --test packages/plugin-sdk/test/bop-line-compare-runtime.test.js`

Expected: FAIL because the manifest and runtime do not exist.

- [ ] **Step 5: Implement the exact Manifest v2 contract**

Use these required entries and no optional entries:

```json
[
  {"id":"base.project.search","major":1},
  {"id":"craft.bop.version.list","major":1},
  {"id":"craft.bop.execution_structure.get","major":1},
  {"id":"craft.bop.work_package.get","major":1},
  {"id":"craft.bop.linked_parts.get","major":1}
]
```

- [ ] **Step 6: Implement bounded invocations and safe tracing**

Use `page_size: 50` for BOP discovery. Select lines only from execution-structure nodes whose normalized kind contains `line`. Resolve the selected line with one work-package call and one linked-parts call per side. Convert failed `CapabilityResultV2` values to `{code,message,retryable}` without copying internal details.

- [ ] **Step 7: Run focused runtime and engine tests**

Run: `node --test packages/plugin-sdk/test/bop-line-compare.test.js packages/plugin-sdk/test/bop-line-compare-runtime.test.js`

Expected: all tests PASS.

- [ ] **Step 8: Commit the runtime slice**

```powershell
git add -- packages/plugin-sdk/examples/bop-line-compare/plugin.json packages/plugin-sdk/examples/bop-line-compare/bop-runtime.js packages/plugin-sdk/test/bop-line-compare-runtime.test.js
git commit -m "feat(plugin): orchestrate governed BOP line reads"
```

### Task 3: Sandboxed two-column plugin UI

**Files:**
- Create: `packages/plugin-sdk/examples/bop-line-compare/index.html`
- Create: `packages/plugin-sdk/examples/bop-line-compare/style.css`
- Create: `packages/plugin-sdk/examples/bop-line-compare/app.js`
- Create: `packages/plugin-sdk/examples/bop-line-compare/ai00-plugin-sdk.js`
- Create: `packages/plugin-sdk/examples/bop-line-compare/README.md`
- Modify: `packages/plugin-sdk/test/bop-line-compare-runtime.test.js`

**Interfaces:**
- Consumes: Task 2 runtime functions and `Ai00PluginClient`.
- Produces: `renderOperationPair(pair, method)`, `renderPartComparison(model)`, `renderToolComparison(model)`, and `renderTrace(items)` in the DOM controller.

- [ ] **Step 1: Add failing static-policy tests**

Read the UI source files as text and assert absence of `fetch(`, `XMLHttpRequest`, `document.cookie`, `.contentDocument`, `window.parent.document`, and `crypto.randomUUID`. Assert the HTML provides two project/BOP/line selectors, one fuzzy-search input, matching-mode controls, process/part/tool tabs, two comparison columns, and an orchestration trace region.

- [ ] **Step 2: Run the runtime test and verify it fails**

Run: `node --test packages/plugin-sdk/test/bop-line-compare-runtime.test.js`

Expected: FAIL because the UI files do not exist.

- [ ] **Step 3: Implement the semantic page and responsive dark styling**

Use native `button`, `input`, `select`, and tab buttons. At widths below 760px stack the two comparison columns. Essential text must use high-contrast foreground colors; muted labels remain readable against the dark surfaces.

- [ ] **Step 4: Implement selection and request-generation control**

Maintain independent left/right state with `generation` counters. Every async side load captures the current generation and discards its render if the generation changed. Changing project clears BOP, line, context, and current pair on that side; changing BOP clears line and context.

- [ ] **Step 5: Implement the three matching interactions**

`自动对齐` renders exact VPPS pairs first and description candidates second. `仅看 VPPS` hides fuzzy pairs. Typing a query renders ranked left and right candidates; clicking one candidate on each side creates a `method:'manual'` pair.

- [ ] **Step 6: Implement the three comparison tabs and trace panel**

Process rows show name, VPPS, sequence, station/parent, predecessors, available parameters, and match reason. Parts use linked-part details where available and otherwise show governed refs. Tools show common/left-only/right-only refs and never invent display names. Trace rows show capability ID, purpose, status, duration, and summary.

- [ ] **Step 7: Copy the SDK client and document the example**

Copy the release-safe `ai00-plugin-sdk.js` used by the existing project-readiness example. README must include build commands, declared capabilities, orchestration order, matching semantics, and the deliberate tool-name degradation.

- [ ] **Step 8: Run all Plugin SDK tests**

Run: `npm test --prefix packages/plugin-sdk`

Expected: all tests PASS with no skipped tests.

- [ ] **Step 9: Commit the UI slice**

```powershell
git add -- packages/plugin-sdk/examples/bop-line-compare packages/plugin-sdk/test/bop-line-compare-runtime.test.js
git commit -m "feat(plugin): add BOP line compare demo UI"
```

### Task 4: Release, local lifecycle acceptance, and deployment proof

**Files:**
- Create: `backend/scripts/bop_line_compare_acceptance.py`
- Create at runtime only: `.runtime/bop-line-compare-release/` artifacts; never commit runtime keys, tokens, packages, or credentials.

**Interfaces:**
- Consumes: signed plugin package, existing local publisher credentials, admin token, and `http://127.0.0.1:8094`.
- Produces: JSON acceptance summary containing release ID, installation ID, Mount resource result, lifecycle steps, and cleanup outcome without secrets.

- [ ] **Step 1: Add a failing script-shape test to the runtime test file**

Assert the acceptance script contains upload, approve, install, enable, Mount resource check, disable, and uninstall steps and does not contain embedded passwords or tokens.

- [ ] **Step 2: Run the test and verify it fails**

Run: `node --test packages/plugin-sdk/test/bop-line-compare-runtime.test.js`

Expected: FAIL because the acceptance script does not exist.

- [ ] **Step 3: Adapt the existing project-readiness acceptance workflow**

Use the same HTTP client and confirmation-token protocol as `backend/scripts/project_readiness_acceptance.py`, but target `devteam.ai00.bop-line-compare`. Verify the mounted `index.html`, `app.js`, `bop-runtime.js`, `compare-engine.js`, `style.css`, and `ai00-plugin-sdk.js` resources.

- [ ] **Step 4: Build and validate the release package**

Run:

```powershell
python packages/plugin-sdk/tools/build_release.py packages/plugin-sdk/examples/bop-line-compare --output-dir .runtime/bop-line-compare-release
```

Expected: a Manifest v2 package for version `1.0.0` with only the declared five permissions.

- [ ] **Step 5: Run all Plugin SDK and relevant backend contract tests**

Run:

```powershell
npm test --prefix packages/plugin-sdk
python -m pytest backend/tests/test_plugin_mount.py backend/tests/test_plugin_marketplace.py backend/tests/test_plugin_acceptance_tooling.py -q
```

Expected: all selected tests PASS, with no failures.

- [ ] **Step 6: Execute the local lifecycle acceptance using runtime-only credentials**

Run the acceptance script with the existing `.runtime` publisher key and short-lived admin token. Do not echo arguments or secret material. Expected lifecycle: upload -> approve -> install -> enable -> verify Mount resources -> disable -> uninstall, with cleanup succeeding.

- [ ] **Step 7: Reinstall and leave the approved demo plugin enabled for the user**

Run the acceptance script in its explicit `--leave-enabled` mode. Verify the marketplace installation is enabled and the workspace registry contains `devteam.ai00.bop-line-compare`.

- [ ] **Step 8: Verify deployed HTTP resources and service health**

Request the root page, plugin workspace entry, and mounted plugin resources through `http://127.0.0.1:8094`. Check the current service log for new Traceback, static 404, Mount 403, or JavaScript syntax errors.

- [ ] **Step 9: Commit the acceptance tooling**

```powershell
git add -- backend/scripts/bop_line_compare_acceptance.py packages/plugin-sdk/test/bop-line-compare-runtime.test.js
git commit -m "test(plugin): verify BOP compare lifecycle"
```

## Self-Review

- Spec coverage: all three matching modes, three comparison dimensions, five Capability calls, safe trace, partial failure, responsive high-contrast UI, packaging, and lifecycle acceptance map to Tasks 1–4.
- Placeholder scan: no `TBD`, `TODO`, “implement later”, or unspecified error/test steps remain.
- Type consistency: `Match`, `LineContext`, `ComparisonModel`, and trace field names are defined before their UI consumers; capability IDs and majors match the design and manifest.
- Scope control: tool-detail enrichment, AI semantic matching, history, export, write-back, and complete-version diff remain excluded.
