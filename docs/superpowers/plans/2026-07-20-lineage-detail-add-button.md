# Lineage Detail Add Button Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify add-button enablement in the lineage detail relationship cards so schema-driven groups like `需求工具` and `需求工装` can be added consistently.

**Architecture:** Keep the fix inside `layout_detail_panel.js` and align all detail-panel relationship render paths to the same group model. Remove the stale add-support whitelist from the new schema-driven renderer, preserve child-node handling, and add regression tests in `dist/web/tests/run_tests.js` to lock the behavior.

**Tech Stack:** Vanilla JavaScript, DOM-based UI rendering, existing Node-based frontend regression tests in `dist/web/tests/run_tests.js`

---

### Task 1: Update the schema-driven relationship renderer

**Files:**
- Modify: `dist/packages/craft-plugin/web/lineage_view/layout_detail_panel.js:3928-4099`
- Test: `dist/web/tests/run_tests.js`

- [ ] **Step 1: Write the failing regression test for schema-driven add buttons**

Add this test near the existing `layout_detail_panel` tests in `dist/web/tests/run_tests.js`:

```js
  await _assertAsync('layout_detail_panel schema relation add button stays enabled for valid link types', async () => {
    const { window: w, document: d } = createDom(`
      <div id="llDpTreeBody"></div>
      <div id="llDpPropsBody"></div>
      <div id="llDpRelsBody"></div>
      <div id="llDpDetBody"></div>
      <div id="llDpDetTitle"></div>
    `);
    const LayoutDetailPanel = loadLayoutDetailPanel(w);
    const panel = new LayoutDetailPanel({
      mount: d.body,
      open: () => {},
      getLineageData: () => ({
        rowByGid: new Map([
          ['gid-1', { gid: 'gid-1', node_type: 'process', title: '工序 A', parent_gid: 'line-1' }],
          ['line-1', { gid: 'line-1', node_type: 'line_process', title: '线体 A', parent_gid: null }],
        ]),
        childMap: new Map([['gid-1', []]]),
        lineGrantSet: new Set(['line-1']),
        lineReadOnly: false,
      }),
      cloudFetch: async (url) => {
        if (url.includes('/api/ontology/schema/process')) {
          return {
            relations: [
              { link_type_binding: 'project_tools', label_zh: '需求工具', range_node_type: 'tool_factory', sort_order: 10, show_in_detail: true },
            ],
          };
        }
        if (url.includes('/api/bop/entry-links')) return { data: [] };
        throw new Error(`unexpected url: ${url}`);
      },
      toast: () => {},
      reloadData: () => {},
      getVersionInfo: () => ({}),
    });

    panel._currentRow = { gid: 'gid-1', node_type: 'process' };
    await panel._renderRels('gid-1', d.getElementById('llDpRelsBody'));

    const addBtn = d.querySelector('.ll-rg-add');
    if (!addBtn) throw new Error('未渲染新增按钮');
    if (addBtn.disabled) throw new Error('有效 linkType 的 schema 分组不应禁用新增按钮');
    if (!addBtn.title.includes('添加需求工具')) throw new Error(`按钮标题异常: ${addBtn.title}`);
  });
```

- [ ] **Step 2: Run the test to verify it fails before the fix**

Run:

```bash
node dist/web/tests/run_tests.js
```

Expected: FAIL in the new `layout_detail_panel schema relation add button stays enabled for valid link types` assertion because `project_tools` is still gated by the stale add-support logic.

- [ ] **Step 3: Replace the stale whitelist in the new renderer with linkType-based enablement**

In `dist/packages/craft-plugin/web/lineage_view/layout_detail_panel.js`, change the add-button support block inside `_renderRels(gid, mountEl = this._relsBody)` to this:

```js
      const isOpen = !items.length ? false : true;
      const addSupported = grp.key === 'child' || !!grp.linkType;
      html += `
        <div class="ll-rg">
          <div class="ll-rg-hdr" data-key="${_he(grp.key)}">
            <span class="ll-rg-tog">${isOpen ? '▼' : '▶'}</span>
            <span class="lv-nt-dot lv-nt-${_he(grp.ntType)}"></span>
            <span class="ll-rg-name">${_he(grp.name)}</span>
            <span class="ll-rg-cnt">${items.length}</span>
            <button class="ll-rg-add" data-key="${_he(grp.key)}" title="${_he(addSupported ? `添加${grp.name}` : `${grp.name} 暂不支持在此处新增`)}"${canEditCurrentLine && addSupported ? '' : ' disabled style="opacity:.45;cursor:not-allowed"'}>＋</button>
          </div>
```
```

- [ ] **Step 4: Re-run the test suite to verify the regression is fixed**

Run:

```bash
node dist/web/tests/run_tests.js
```

Expected: PASS for the new schema relation add-button assertion and no regressions in the existing `layout_detail_panel` checks.

- [ ] **Step 5: Commit the focused renderer fix**

```bash
git add dist/packages/craft-plugin/web/lineage_view/layout_detail_panel.js dist/web/tests/run_tests.js
git commit -m "fix: enable schema relation add buttons in detail panel"
```

### Task 2: Align the legacy detail-panel relationship renderers in the same file

**Files:**
- Modify: `dist/packages/craft-plugin/web/lineage_view/layout_detail_panel.js:1429-1633`
- Modify: `dist/packages/craft-plugin/web/lineage_view/layout_detail_panel.js:2729-2928`
- Test: `dist/web/tests/run_tests.js`

- [ ] **Step 1: Write a guard test that the file no longer contains the stale whitelist block**

Add this assertion in `dist/web/tests/run_tests.js` after the add-button test from Task 1:

```js
  await _assertAsync('layout_detail_panel no longer uses stale add whitelist logic', async () => {
    const code = fs.readFileSync(path.join(ROOT, 'packages/craft-plugin/web/lineage_view/layout_detail_panel.js'), 'utf-8');
    if (code.includes("const addSupported = grp.key === 'child' || [")) {
      throw new Error('仍然存在旧的 addSupported 白名单逻辑');
    }
  });
```

- [ ] **Step 2: Run the tests to confirm the guard fails before the cleanup**

Run:

```bash
node dist/web/tests/run_tests.js
```

Expected: FAIL in `layout_detail_panel no longer uses stale add whitelist logic` until all stale whitelist branches are removed.

- [ ] **Step 3: Keep the older renderers on the same enablement rule**

In both older `_renderRels(gid)` implementations in `dist/packages/craft-plugin/web/lineage_view/layout_detail_panel.js`, make the add-button render line explicitly compute support from the group itself instead of any hand-maintained whitelist. Use this pattern:

```js
      const addSupported = grp.key === 'child' || !!grp.linkTypes?.[0];
      html += `
        <div class="ll-rg">
          <div class="ll-rg-hdr" data-key="${_he(grp.key)}">
            <span class="ll-rg-tog">${isOpen ? '▼' : '▶'}</span>
            <span class="lv-nt-dot lv-nt-${_he(grp.ntType)}"></span>
            <span class="ll-rg-name">${_he(grp.name)}</span>
            <span class="ll-rg-cnt">${items.length}</span>
            <button class="ll-rg-add" data-key="${_he(grp.key)}" title="${_he(addSupported ? `添加${grp.name}` : `${grp.name} 暂不支持在此处新增`)}"${canEditCurrentLine && addSupported ? '' : ' disabled style="opacity:.45;cursor:not-allowed"'}>＋</button>
          </div>
```
```

Do not change their existing click routing other than continuing to use `grp.linkTypes?.[0]` for non-child groups.

- [ ] **Step 4: Re-run the frontend regression tests**

Run:

```bash
node dist/web/tests/run_tests.js
```

Expected: PASS for the new whitelist-removal guard and the existing `layout_detail_panel` regression tests.

- [ ] **Step 5: Commit the follow-up consistency cleanup**

```bash
git add dist/packages/craft-plugin/web/lineage_view/layout_detail_panel.js dist/web/tests/run_tests.js
git commit -m "fix: align detail panel add button rules"
```

### Task 3: Perform final verification on the working tree

**Files:**
- Modify: none
- Test: `dist/web/tests/run_tests.js`

- [ ] **Step 1: Search for remaining stale add-button whitelist patterns**

Run:

```bash
grep -n "const addSupported = grp.key === 'child' || \[" dist/packages/craft-plugin/web/lineage_view/layout_detail_panel.js
```

Expected: no output.

- [ ] **Step 2: Run the full frontend regression script one more time**

Run:

```bash
node dist/web/tests/run_tests.js
```

Expected: PASS with the `layout_detail_panel` assertions still green.

- [ ] **Step 3: Review the final diff before handoff**

Run:

```bash
git diff -- dist/packages/craft-plugin/web/lineage_view/layout_detail_panel.js dist/web/tests/run_tests.js docs/superpowers/specs/2026-07-20-lineage-detail-add-button-design.md
```

Expected: only the planned add-button rule updates and regression tests appear.

- [ ] **Step 4: Commit the verification checkpoint if needed**

```bash
git status --short
```

Expected: clean working tree for the planned files, or only unrelated pre-existing changes outside this task.
