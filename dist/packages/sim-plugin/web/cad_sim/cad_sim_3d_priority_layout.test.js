const assert = require('assert');
const fs = require('fs');
const path = require('path');

const html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');
const css = fs.readFileSync(path.join(__dirname, 'cad_sim.css'), 'utf8');
const js = fs.readFileSync(path.join(__dirname, 'cad_sim.js'), 'utf8');

for (const id of [
  'simulationShell', 'resourceLibraryPanel', 'btnResourceMode', 'btnFocus3d',
  'btnToggleBopPanel', 'btnToggleVisPanel', 'nativeViewportSlot',
  'simulationObjectPanel', 'simulationEnvironmentPanel', 'btnToggleResourceSection', 'btnToggleEnvironmentPanel',
  'vmCommandRail', 'ai00ActionBar', 'ai00StatusBar', 'xiaorouDock', 'xiaorouBall',
]) {
  assert.match(html, new RegExp(`id=["']${id}["']`), `missing ${id}`);
}
for (const id of ['bopInsertOverlay', 'bopInsertVersion', 'bopInsertLine', 'bopInsertDepth', 'bopInsertName', 'bopInsertSummary']) {
  assert.match(html, new RegExp(`id=["']${id}["']`), `missing governed BOP insert control: ${id}`);
}

for (const tab of ['三维工作区', '节点详情', '任务与结果', '操作记录', '问题提报', '工艺文件']) {
  assert.ok(html.includes(tab), `missing workspace tab: ${tab}`);
}

assert.match(html, /id="btnResourceMode"[^>]*>[\s\S]*?产品资源[\s\S]*?<\/button>/, 'bottom action must identify the whole product/resource column');
assert.match(html, /id="btnToggleBopPanel"[^>]*>[\s\S]*?仿真环境[\s\S]*?<\/button>/, 'bottom action must identify the whole environment column');
assert.equal((html.match(/当前产品结构/g) || []).length, 0, 'product capsule must not be repeated by an inner VM tree heading');
assert.doesNotMatch(html, /id="btnToggleCurrentEnvironmentPanel"/, 'current environment must not duplicate the current document section');
assert.match(html, /id="currentDocumentLabel"[^>]*>当前仿真文档 · 未选择环境</, 'current document must visibly identify the selected environment');
assert.match(html, /id="plmxmlSourceBanner"[\s\S]*id="plmxmlProjectCode"[\s\S]*id="plmxmlStoredAt"/, 'PLMXML banner must expose project number and stored time as separate fields');
assert.match(html, /id="bopTreeLoading"[\s\S]*id="bopTreeLoadingText"/, 'environment loading must expose elapsed status in the BOP tree');
assert.match(html, /id="visTreeLoading"[\s\S]*id="visTreeLoadingText"/, 'VisMockup loading must expose elapsed status in the VM tree');
assert.match(html, /id="simulationObjectPanel"[\s\S]*id="simulationEnvironmentPanel"[\s\S]*id="simulationFuturePanel"/, 'personal environments/resources must remain first and the document stack must be second');
assert.match(js, /objectPanel\.append\(environmentToggle, environmentRecords, resourceToggle, resourcePanel\)/, 'the first column must contain personal environments above resources');
assert.match(js, /environmentPanel\.append\(documentToggle, visPanel\)/, 'the second column must contain the current document workspace');
assert.match(html, /id="modelDocumentsPanel"[\s\S]*aria-label="模型文件"[\s\S]*id="visPanel"[\s\S]*aria-label="备选层次结构"/, 'model files and alternate hierarchies must remain separate draggable columns');
assert.match(html, /class="[^"]*legacy-environment-tree[^"]*"[^>]*id="environmentTreePanel"/, 'legacy BOP projection must not remain a primary visible column');
assert.match(js, /btnResourceMode[\s\S]*setObjectPanelOpen/, 'bottom product/resource action must control the whole object column');
assert.match(js, /actionBar\.insertBefore\(vmTreeActions, actionSpacer\)/, 'VM tree actions must live in the bottom action bar');
assert.match(html, /id="resourceLibraryPanel"[^>]*collapsed/, 'resource section must support compact folding');
assert.match(html, /id="environmentRecordsPanel"[^>]*collapsed/, 'environment library must default collapsed');
assert.match(css, /\.cs-environment-stack\s*\{[^}]*width:\s*var\(--bop-panel-w\)/, 'the second document column must keep the current environment width');
assert.match(css, /\.cs-environment-stack[\s\S]*\.cs-object-capsule/, 'the second column must reuse the first column folding UI');
assert.match(css, /\.cs-alternate-hierarchies:has\(\.cs-model-document-empty\)/, 'empty document sections must stay compact');
assert.match(html, /id="vmCommandRail"[\s\S]*id="cmdAllOn"[\s\S]*id="cmdCapture"/, 'VM commands must live in the right rail');
for (const obsoleteId of ['btnOpenFile', 'btnCloseFile', 'btnNewTask', 'btnGovernedCapture']) {
  assert.doesNotMatch(html, new RegExp(`id=["']${obsoleteId}["']`), `obsolete action remains visible: ${obsoleteId}`);
}
const viewerToolbarStart = html.indexOf('class="cs-viewer-toolbar"');
const viewportStart = html.indexOf('id="nativeViewportSlot"');
const runtimeStatusStart = html.indexOf('id="ai00StatusBar"');
assert.ok(viewerToolbarStart < runtimeStatusStart && runtimeStatusStart < viewportStart, 'runtime status must live at the top of the 3D viewport');
assert.equal((html.match(/id="vmDocumentLabel"/g) || []).length, 1, 'VisMockup document name must render only once');
assert.match(html, /id="viewerContextInfo"[\s\S]*id="viewerEnvironmentLabel"[\s\S]*id="vmDocumentLabel"[\s\S]*id="viewerEmbedStatus"[\s\S]*id="vmStatusDot"[\s\S]*id="vmStatusLabel"/, 'top toolbar must separate centered context from right-aligned embed state');
assert.match(css, /\.cs-viewer-toolbar\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+minmax\(0,\s*auto\)\s+minmax\(0,\s*1fr\)/, 'viewer context must be centered with a balanced three-column grid');
assert.match(css, /\.cs-viewer-embed-status\s*\{[^}]*justify-self:\s*end/, 'embed state must remain right aligned');
assert.match(js, /function _setViewerEnvironmentLabel\(/, 'selected environment must update the 3D status bar');
assert.doesNotMatch(js, /_setVmStatus\('connected', status\.documentName \? `已内嵌/, 'embed state must not repeat the document name');
assert.match(html, /id="vmCommandRail"[\s\S]*id="xiaorouDock"/, 'Xiaorou dock must sit to the right of the VisMockup command rail');
assert.match(css, /--xiaorou-dock-collapsed-w:\s*36px/, 'collapsed Xiaorou dock must retain a narrow right-side entry');
assert.match(css, /--xiaorou-dock-open-w:\s*360px/, 'expanded Xiaorou dock must reserve a stable workspace column');
assert.match(css, /\.cs-sim-shell\.xiaorou-open\s*\{[^}]*--xiaorou-dock-w:\s*var\(--xiaorou-dock-open-w\)/, 'opening Xiaorou must resize the layout in flow');
assert.match(css, /\.cs-sim-shell \.cs-cmd-bar\s*\{[^}]*right:\s*var\(--xiaorou-dock-w\)/, 'VisMockup rail must remain immediately left of Xiaorou');
assert.doesNotMatch(css, /\.cs-xiaorou-(?:ball|chat)\s*\{[^}]*position:\s*absolute/, 'Xiaorou must not float over the native viewport');
assert.match(css, /\.cs-xiaorou-ball\s*\{[^}]*background:\s*var\(--surface\)[^}]*color:\s*#1e66f5/i, 'collapsed Xiaorou entry must use a light surface with blue emphasis');
assert.doesNotMatch(css, /\.cs-xiaorou-ball\s*\{[^}]*background:\s*#1e66f5/i, 'collapsed Xiaorou entry must not render as a full-height saturated blue strip');
assert.match(js, /function _openXiaorou\(/, 'Xiaorou dock must have a real open action');
assert.match(js, /form\.onchange\s*=\s*syncMode/, 'PLMXML hierarchy choices must follow every insert-mode change');
assert.match(js, /buildHierarchyForest/, 'alternate hierarchy nodes and placements must render as one real tree');
assert.match(js, /data-node-gid/, 'editable hierarchy nodes must be visible placement drop targets');
assert.match(js, /cs-alternate-tree-check/, 'alternate hierarchy visibility must use VisMockup-style checkboxes');
assert.match(js, /const targetTree = \$\('alternateHierarchyList'\)/, 'drag and drop must target the visible alternate hierarchy tree');
assert.doesNotMatch(js, /addEventListener\('change',\s*syncMode,\s*\{\s*once:\s*true\s*\}\)/, 'PLMXML mode handling must not stop after the first change');
for (const id of ['xiaorouChat', 'xiaorouChatClose', 'xiaorouChatMessages', 'xiaorouChatInput', 'xiaorouChatSend']) {
  assert.match(html, new RegExp(`id=["']${id}["']`), `missing inline Xiaorou control: ${id}`);
}
assert.match(js, /simulationShell[\s\S]*classList\.toggle\('xiaorou-open'/, 'Xiaorou must toggle a docked layout state');
assert.match(js, /_setXiaorouOpen[\s\S]*_notifyNativeViewportBounds\(\)/, 'Xiaorou resizing must update the native viewport bounds');
assert.doesNotMatch(js, /openAiChatWindow|window\.open\([^)]*ai_chat/, 'Xiaorou ball must not leave the simulation page');
assert.doesNotMatch(js, /if \(msg && state !== 'connected'\) _showBanner/, 'VisMockup detection status must not open the top banner');
assert.match(html, /id="cmdAllOn"[^>]*cs-cmd-green/, 'visibility commands need VisMockup green semantics');
assert.match(html, /id="cmdSelVisible"[^>]*cs-cmd-purple/, 'selection commands need VisMockup purple semantics');
assert.match(html, /id="cmdDocInfo"[^>]*cs-cmd-blue/, 'navigation commands need VisMockup blue semantics');
assert.match(html, /id="cmdLoadAllGeo"[^>]*cs-cmd-orange/, 'analysis commands need VisMockup orange semantics');
assert.match(css, /--vm-command-rail-w:\s*48px/, 'native viewport must reserve a 48px command rail');
for (const token of ['--font-title', '--font-body', '--font-control', '--font-meta']) {
  assert.match(css, new RegExp(`${token}:`), `missing typography token ${token}`);
}
assert.match(css, /html, body\s*\{[^}]*font-size:\s*var\(--font-body\)/, 'page copy must use the shared body type scale');
assert.match(css, /\.cs-environment-node\s*\{[^}]*font-size:\s*var\(--font-body\)[^}]*min-height:\s*22px/, 'BOP environment rows must use compact body typography');
assert.match(css, /\.cs-bop-label\s*\{[^}]*font-size:\s*var\(--font-body\)/, 'legacy BOP labels must use the same tree typography');
assert.match(css, /\.hidden\s*\{\s*display:\s*none\s*!important/, 'hidden utility must remove inactive overlays and file inputs');
assert.match(css, /\.cs-sim-shell\.resource-mode[\s\S]*\.cs-resource-library/, 'resource mode layout missing');
assert.match(css, /\.cs-sim-shell\.focus-mode[\s\S]*#environmentTreePanel/, 'focus mode must collapse BOP');
assert.match(css, /\.cs-object-panel\.collapsed\s*\{[^}]*width:\s*var\(--object-rail-w\)/, 'object column must collapse in flow instead of becoming an overlay');
assert.match(css, /\.cs-object-capsule\s*\{[^}]*border-radius:\s*[0-6]px/, 'section toggles must align with rectangular content panels');
assert.match(css, /\.cs-object-capsule\[aria-expanded="true"\][^{]*\{[^}]*background:/, 'expanded section state must be visually explicit');
assert.doesNotMatch(css, /\.cs-sim-shell \.cs-vis-panel\s*\{[^}]*position:\s*absolute/, 'VM tree must not use a popup overlay');
assert.match(js, /function _initWorkspaceLayout\(/, 'workspace layout state is not initialized');
assert.match(js, /ResizeObserver/, 'native viewport bounds must react to layout changes');
assert.match(js, /visMockupNativeView\?\.attach/, 'connected VisMockup must attach to the reserved native viewport');
assert.match(js, /visMockupNativeView\?\.onStatus/, 'native document and lifecycle status must update the UI');
assert.match(js, /visMockupNativeView\?\.focus/, 'clicking the native viewport must restore VisMockup focus');
assert.match(js, /visMockupNativeView\?\.detach/, 'leaving the simulation page must detach the native child window');
assert.match(js, /frameElement\.getBoundingClientRect/, 'native bounds must include the host iframe offset');
assert.match(js, /workspace:visibility/, 'simulation iframe must react to workspace tab visibility');

const workspaceSource = fs.readFileSync(path.join(__dirname, '../../../../web/workspace/workspace.js'), 'utf8');
assert.match(workspaceSource, /workspace:visibility/, 'workspace tab activation must notify child frames about visibility');

console.log('cad sim 3D priority layout: PASS');
