'use strict';
const fs = require('node:fs');
const path = require('node:path');
if (!process.versions.electron) {
  const env = { ...process.env };
  delete env.ELECTRON_RUN_AS_NODE;
  const result = require('node:child_process').spawnSync(require('electron'), [__filename], { env, encoding: 'utf8', timeout: 30000 });
  process.stdout.write(result.stdout || '');
  process.stderr.write(result.stderr || '');
  if (result.error) console.error(result.error);
  process.exit(result.status ?? 1);
} else {
  const { app, BrowserWindow } = require('electron');
  app.commandLine.appendSwitch('disable-background-timer-throttling');
  app.commandLine.appendSwitch('disable-renderer-backgrounding');
  app.whenReady().then(async () => {
    const win = new BrowserWindow({ show: false, width: 1200, height: 800, webPreferences: { backgroundThrottling: false } });
    try {
      const css = fs.readFileSync(path.join(__dirname, 'layout_mode.css'), 'utf8') + fs.readFileSync(path.join(__dirname, 'lineage.css'), 'utf8');
      await win.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent('<style>'+css+'</style><div id="lvLayoutCanvas" style="position:absolute;inset:0"><div id="llViewport" class="ll-viewport"><div id="llWorld" class="ll-world"></div></div></div>'));
      const layout = fs.readFileSync(path.join(__dirname, 'layout_mode.js'), 'utf8');
      const lineage = fs.readFileSync(path.join(__dirname, 'lineage.js'), 'utf8');
      const callbacks = lineage.slice(lineage.indexOf('    demoSetupView:'), lineage.indexOf('    onDemoPauseChange:'));
      const connect = lineage.slice(lineage.indexOf('  async function _runDemoRelationConnect('), lineage.indexOf('  async function _runDemoRelationReset('));
      const status = lineage.slice(lineage.indexOf('function _syncDemoStatusUI('), lineage.indexOf('function _setDemoPlayLabel('));
      const assoc = fs.readFileSync(path.join(__dirname, 'assoc_panel.js'), 'utf8');
      const results = await win.webContents.executeJavaScript('(async () => {' + layout + '\n' + assoc + '\n' + status + '\n' + connect + '\n' + fixture.toString() + '\nreturn await fixture({' + callbacks + '});\n})()');
      for (const result of results) console.log((result.passed ? 'PASS ' : 'FAIL ') + result.name + (result.error ? ': ' + result.error : ''));
      if (process.env.AI00_DEMO_SCREENSHOT) {
        await win.webContents.executeJavaScript("window.demoProgressPreview('loading')");
        await win.webContents.executeJavaScript("new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))");
        await new Promise(resolve => setTimeout(resolve, 300));
        fs.writeFileSync(process.env.AI00_DEMO_SCREENSHOT, (await win.webContents.capturePage()).toPNG());
      }
      app.exit(results.every(result => result.passed) ? 0 : 1);
    } catch (error) { console.error(error); app.exit(1); }
  });
}
async function fixture(demo) {
  const results = [];
  const layout = new LayoutMode(document.getElementById('lvLayoutCanvas'));
  globalThis._layoutMode = layout;
  globalThis._level1Filter = null;
  globalThis._demoLastLineGid = 'rear';
  globalThis._demoSpeed = 2;
  globalThis._demoPanFrame = null;
  globalThis._demoConnecting = false;
  globalThis._demoSelectionEpoch = 0;
  globalThis._demoStatusRequest = 0;
  globalThis._demoStepsVersionGid = 'demo-version';
  globalThis._viewMode = 'layout';
  globalThis._isSuperAdminUser = () => true;
  globalThis._activeGid = null;
  document.body.insertAdjacentHTML('beforeend', '<span id="lvDemoStatus"><em></em></span><button id="demoPlay"></button><button id="demoReset"></button><button id="demoConnect"></button>');
  globalThis.$demoPlayBtn = document.getElementById('demoPlay');
  globalThis.$demoResetBtn = document.getElementById('demoReset');
  globalThis.$demoRelationBtn = document.getElementById('demoConnect');
  globalThis.$l1DD = { style: { display: 'none' } };
  globalThis._buildLevel1Dropdown = () => {};
  let loadError = false;
  const rows = [
    { gid: 'chassis', title: '底盘一线', node_type: 'line_process' },
    { gid: 'rear', title: '后内饰一线', node_type: 'line_process' },
    { gid: 'rear2', title: '后内饰二线', node_type: 'line_process' },
    { gid: 'chassis01', parent_gid: 'chassis', title: '底盘一线01L', node_type: 'station_process' },
    { gid: 'rear01', parent_gid: 'rear', title: '后内饰一线01L', node_type: 'station_process' },
    { gid: 'rear02', parent_gid: 'rear', title: '后内饰一线02L', node_type: 'station_process' },
    { gid: 'rear201', parent_gid: 'rear2', title: '后内饰二线01L', node_type: 'station_process' }
  ];
  globalThis._rowByGid = new Map(rows.map(row => [row.gid, row]));
  const childMap = new Map();
  for (const row of rows) { const children = childMap.get(row.parent_gid) || []; children.push(row); childMap.set(row.parent_gid, children); }
  globalThis._render = () => {
    layout._preserveView = true;
    layout.render({ rows, rowByGid: _rowByGid, childMap, statsMap: new Map(), depthByGid: new Map(), typeFilter: null, level1Filter: _level1Filter });
  };
  globalThis._applyFilters = () => _render();
  globalThis._ensureScopeLoaded = async () => { if (loadError) throw new Error('scope load failed'); await Promise.resolve(); _render(); };
  layout._linePositions.set('chassis', { x: 32, y: 32, w: 1200, h: 660 });
  layout._linePositions.set('rear', { x: 900, y: 3000, w: 1200, h: 660 });
  layout._linePositions.set('rear2', { x: 1600, y: 6000, w: 1200, h: 660 });
  function assert(condition, message) { if (!condition) throw new Error(message); }
  async function check(name, action) { try { await action(); results.push({ name, passed: true }); } catch (error) { results.push({ name, passed: false, error: error.message }); } }
  function center(gid) {
    const card = layout._world.querySelector('[data-gid="'+gid+'"]');
    assert(card, 'Target station missing: '+gid);
    const rect = card.getBoundingClientRect(), viewport = layout._viewport.getBoundingClientRect();
    return { x: rect.left-viewport.left+rect.width/2, y: rect.top-viewport.top+rect.height/2 };
  }
  function centered(gid) {
    const point = center(gid);
    assert(Math.abs(point.x-layout._viewport.clientWidth/2)<1, 'Wrong canvas X: '+point.x+' expected: '+layout._viewport.clientWidth/2);
    assert(Math.abs(point.y-(layout._viewport.clientHeight/2-120))<1, 'Wrong canvas Y: '+point.y);
  }
  await check('setup includes nested line offsets', async () => { _render(); await demo.demoSetupView('rear01','rear'); centered('rear01'); });
  await check('selection reveals a line excluded by chassis filter', async () => { _level1Filter=new Set(['chassis']); _render(); await demo.demoSetupView('rear01','rear'); centered('rear01'); assert(_level1Filter.has('rear'),'Target still filtered'); });
  await check('switching and replaying targets the selected line', async () => {
    for (const [line,station] of [['rear2','rear201'],['chassis','chassis01'],['rear','rear01'],['rear','rear01']]) { await demo.demoSetupView(station,line); centered(station); }
  });
  await check('pan includes line X offset and preserves Y', async () => {
    _level1Filter=null; _render(); layout._renderLineCards('rear'); layout._zoom=0.61; layout._setTransform(); layout.scrollToNode('rear01');
    const before=center('rear02').y; demo.demoPanToStation('rear02');
    const deadline = performance.now() + 4000;
    while (Math.abs(center('rear02').x-layout._viewport.clientWidth/2) >= 1 && performance.now() < deadline) {
      await new Promise(resolve => setTimeout(resolve, 20));
    }
    const point=center('rear02'); assert(Math.abs(point.x-layout._viewport.clientWidth/2)<1,'Wrong pan X: '+point.x); assert(Math.abs(point.y-before)<1,'Pan changed Y');
  });
  await check('scope failure is surfaced instead of silent playback', async () => { loadError=true; let rejected=false; try { await demo.demoSetupView('rear01','rear'); } catch { rejected=true; } assert(rejected,'Scope error swallowed'); });
  await check('legacy station-only setup derives its own line rather than last demo line', async () => {
    loadError = false; _level1Filter = null; _render(); _demoLastLineGid = 'chassis';
    await demo.demoSetupView('rear201'); centered('rear201');
  });
  await check('a previous pan cannot move the canvas back after switching lines', async () => {
    await demo.demoSetupView('rear01', 'rear');
    demo.demoPanToStation('rear02');
    await demo.demoSetupView('rear201', 'rear2');
    await new Promise(resolve => setTimeout(resolve, 900));
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    centered('rear201');
  });
  await check('legacy playback waits for scope preparation before hiding and revealing', async () => {
    const events = [];
    const panel = Object.create(AssocPanel.prototype);
    panel._getBopLinkedNodes = () => [{ gid: 'process', node_type: 'process', parent_gid: 'rear01' }];
    panel._demoSetupView = async () => { await new Promise(resolve => setTimeout(resolve, 100)); events.push('ready'); };
    panel._demoHideNodes = () => events.push('hide');
    panel._demoRevealNode = () => { events.push('reveal'); return true; };
    panel._showDemoControl = () => {};
    panel._removeDemoControl = () => {};
    await panel._runDemoAnimation([]);
    assert(events.join(',') === 'ready,hide,reveal', 'Unexpected animation order: ' + events);
  });
  await check('connect selects target canvas before the user presses play', async () => {
    loadError = false;
    globalThis._versionGid = 'demo-version';
    globalThis._demoStepsByLine = {};
    globalThis._demoSteps = null;
    globalThis._assocPanel = { _demoSetupView: demo.demoSetupView };
    globalThis._toast = () => {};
    globalThis._demoVeil = () => () => {};
    globalThis._setDemoPlayLabel = () => {};
    globalThis._reload = async () => _render();
    globalThis._invokeCapability = async (id, version, payload) => {
      assert(id === 'craft.bop.demo.relation.change.apply' && version === 1 && payload.line_gid === 'rear', 'Wrong capability selector');
      return { data: { ok: true, line_gid: 'rear', steps: [{ station_gid: 'rear01', processes: [] }] } };
    };
    _level1Filter = new Set(['chassis']); _render();
    await _runDemoRelationConnect('rear', '后内饰一线');
    centered('rear01');
  });
  const statusLabel = () => document.querySelector('#lvDemoStatus em').textContent;
  await check('connected status names only the selected line, not every connected line', async () => {
    _demoLastLineGid = 'rear'; _demoConnecting = false;
    _syncDemoStatusUI([{ line_gid: 'chassis', line_title: '底盘一线', connected: true }, { line_gid: 'rear', line_title: '后内饰一线', connected: true }]);
    assert(statusLabel() === '已连接：后内饰一线', 'Accumulated status: ' + statusLabel());
  });
  await check('selection changes the visible canvas before the slow connect response', async () => {
    _demoStepsByLine = {}; _demoLastLineGid = 'chassis'; _level1Filter = new Set(['chassis']); _render();
    let release;
    const response = new Promise(resolve => { release = resolve; });
    _invokeCapability = async () => response;
    const pending = _runDemoRelationConnect('rear', '后内饰一线');
    const visible = layout._filteredLines.map(line => line.gid).join(',');
    const label = statusLabel();
    const disabled = $demoPlayBtn.disabled;
    release({ data: { ok: true, line_gid: 'rear', steps: [{ station_gid: 'rear01', processes: [] }] } });
    await pending;
    assert(visible === 'rear', 'Still showing old line while request pending: ' + visible);
    assert(label.includes('后内饰一线') && !label.includes('底盘'), 'Pending status kept old line: ' + label);
    assert(disabled, 'Playback remained enabled during switching');
  });
  await check('already connected line switches without write, reload or all-line status request', async () => {
    _demoStepsByLine = { rear: [{ station_gid: 'rear01', processes: [] }] };
    _level1Filter = new Set(['chassis']); _render();
    let calls = 0;
    _invokeCapability = async () => { calls++; throw new Error('Unexpected repeated capability invocation'); };
    const previousReload = _reload;
    _reload = async () => { calls++; throw new Error('Unexpected full reload'); };
    try { await _runDemoRelationConnect('rear', '后内饰一线'); } finally { _reload = previousReload; }
    assert(calls === 0, 'Cached switch repeated work'); centered('rear01');
    assert(statusLabel() === '已连接：后内饰一线', 'Wrong cached status: ' + statusLabel());
  });
  await check('status response started before selection cannot replace its new steps or label', async () => {
    _demoLastLineGid = 'chassis'; _demoConnecting = false;
    let release;
    _invokeCapability = async () => new Promise(resolve => { release = resolve; });
    const pending = _refreshDemoStatus();
    _demoSelectionEpoch++; _demoLastLineGid = 'rear';
    _demoStepsByLine = { rear: [{ station_gid: 'rear01', processes: [] }] };
    _demoSteps = _demoStepsByLine.rear;
    _syncDemoStatusUI([{ line_gid: 'rear', line_title: '后内饰一线', connected: true }]);
    release({ data: { ok: true, lines: [{ line_gid: 'chassis', line_title: '底盘一线', connected: true, steps: [{ station_gid: 'chassis01', processes: [] }] }] } });
    await pending;
    assert(_demoLastLineGid === 'rear' && _demoSteps[0].station_gid === 'rear01', 'Old response changed selected demo');
    assert(statusLabel() === '已连接：后内饰一线', 'Old response replaced current label');
  });
  await check('progress uses actual returned cards, not moved count, and waits for canvas before success', async () => {
    _demoStepsByLine = {};
    let respond, finishReload;
    _invokeCapability = async () => new Promise(resolve => { respond = resolve; });
    const previousReload = _reload;
    _reload = async options => {
      assert(options.demoLineGid === 'rear', 'Reload did not target selected line');
      await new Promise(resolve => { finishReload = resolve; });
      _render();
    };
    const pending = _runDemoRelationConnect('rear', '后内饰一线');
    const card = document.getElementById('lvDemoProgress');
    const initial = card?.textContent || '';
    const initialPhase = card?.dataset.phase;
    respond({ data: { ok: true, operation: 'connect', line_gid: 'rear', line_title: '后内饰一线', processes_moved: 0,
      steps: [{ station_gid: 'rear01', processes: [{ entry_gid: 'p1', operations: [] }, { entry_gid: 'p2', operations: [] }] }] } });
    await new Promise(resolve => setTimeout(resolve, 30));
    const preparing = card?.textContent || '';
    const preparingPhase = card?.dataset.phase;
    finishReload?.();
    try { await pending; } finally { _reload = previousReload; }
    assert(initialPhase === 'connecting' && initial.includes('正在统计') && initial.includes('后内饰一线'), 'Missing honest pending progress: ' + initial);
    assert(preparingPhase === 'loading' && preparing.includes('2 张工艺卡') && preparing.includes('1 个工位'), 'Incorrect total/progress: ' + preparing);
    assert(card.dataset.phase === 'ready' && card.textContent.includes('正在开始演示'), 'Missing ready progress');
    assert(!card.textContent.includes('%'), 'Progress invented a percentage');
  });
  await check('older status failure cannot erase newer success within the same selection', async () => {
    _demoConnecting = false; _demoLastLineGid = 'rear';
    let rejectOld;
    _invokeCapability = async () => new Promise((resolve, reject) => { rejectOld = reject; });
    const old = _refreshDemoStatus();
    _invokeCapability = async () => ({ data: { ok: true, lines: [{ line_gid: 'rear', connected: true, steps: [{ station_gid: 'rear01', processes: [] }] }] } });
    await _refreshDemoStatus();
    rejectOld(new Error('old timeout'));
    await old;
    assert(_demoSteps?.[0]?.station_gid === 'rear01', 'Old failure erased newer successful status');
  });
  await check('canvas failure keeps successful connection cached but not playable or green', async () => {
    _demoStepsByLine = {};
    _invokeCapability = async () => ({ data: { ok: true, operation: 'connect', line_gid: 'rear', processes_moved: 1, steps: [{ station_gid: 'rear01', processes: [] }] } });
    loadError = true;
    let rejected = false;
    try { await _runDemoRelationConnect('rear', '后内饰一线'); } catch { rejected = true; } finally { loadError = false; }
    assert(rejected, 'Canvas error swallowed');
    assert(_demoStepsByLine.rear?.length && !_demoSteps, 'Lost committed connection or kept failed playback');
    assert(!document.getElementById('lvDemoStatus').classList.contains('connected'), 'Failure shown green');
    assert(document.getElementById('lvDemoProgress')?.dataset.phase === 'error', 'Progress did not show failure');
    assert(!_demoConnecting && !$demoRelationBtn.disabled, 'Cannot retry after failure');
  });
  await check('connect hides cards while loading and auto starts playback after view preparation', async () => {
    _demoStepsByLine = { rear: [{ station_gid: 'rear01', processes: [{ entry_gid: 'p1', operations: [] }] }] };
    const originalPanel = _assocPanel;
    const events = [];
    _assocPanel = {
      _demoSetupView: async () => {
        assert(document.getElementById('lvLayoutCanvas').classList.contains('lv-demo-preparing'), 'Cards exposed during view preparation');
        events.push('prepared');
      },
      _runRelationDemoAnimation: async (steps, line, options) => {
        assert(line === 'rear' && steps[0].station_gid === 'rear01' && options.prepared, 'Auto playback uses wrong selection or reloads prepared view');
        events.push('play');
      },
    };
    try { await _runDemoRelationConnect('rear', '后内饰一线'); } finally { _assocPanel = originalPanel; }
    assert(events.join(',') === 'prepared,play', 'Playback did not follow preparation: ' + events);
    assert(!document.getElementById('lvLayoutCanvas').classList.contains('lv-demo-preparing'), 'Preparation veil remains after playback starts');
  });
  await check('prepared playback hides cards synchronously without setting up the canvas again', async () => {
    const panel = Object.create(AssocPanel.prototype), events = [];
    panel._demoSetupView = async () => { events.push('setup'); };
    panel._demoHideNodes = () => events.push('hide');
    panel._demoRevealNode = () => { events.push('reveal'); return true; };
    panel._showDemoControl = () => {};
    panel._removeDemoControl = () => {};
    const run = panel._runRelationDemoAnimation([{ station_gid: 'rear01', processes: [{ entry_gid: 'p1', operations: [] }] }], 'rear', { prepared: true });
    const immediate = events.join(',');
    await run;
    assert(immediate === 'hide', 'Already connected cards flash before hide: ' + immediate);
    assert(events.join(',') === 'hide,reveal', 'Unexpected playback path: ' + events);
  });
  await check('switching auto playback cancels the old loop without revealing or cleaning the new one', async () => {
    const panel = Object.create(AssocPanel.prototype), revealed = [];
    panel._demoHideNodes = () => {};
    panel._demoRevealNode = gid => { revealed.push(gid); return true; };
    panel._showDemoControl = () => {};
    panel._removeDemoControl = () => {};
    panel._demoCleanup = () => { throw new Error('Old loop cleaned the new canvas'); };
    const makeSteps = ids => [{ station_gid: 'rear01', processes: ids.map(entry_gid => ({ entry_gid, operations: [] })) }];
    const first = panel._runRelationDemoAnimation(makeSteps(['old1','old2']), 'rear', { prepared: true });
    while (!revealed.length) await new Promise(resolve => setTimeout(resolve, 10));
    panel.stopDemo();
    const second = panel._runRelationDemoAnimation(makeSteps(['new1','new2']), 'rear2', { prepared: true });
    await Promise.all([first,second]);
    assert(revealed.join(',') === 'old1,new1,new2', 'Old playback interfered: ' + revealed);
  });
  await check('failed animation preparation releases playback state for retry', async () => {
    const panel = Object.create(AssocPanel.prototype);
    panel._demoRevealNode = () => true;
    panel._demoSetupView = async () => { throw new Error('scope load failed'); };
    let rejected = false;
    try { await panel._runRelationDemoAnimation([{ station_gid: 'rear01', processes: [{ entry_gid: 'process', operations: [] }] }], 'rear'); }
    catch { rejected = true; }
    assert(rejected, 'Preparation failure was swallowed');
    assert(panel._demoRunning === false, 'Playback remains stuck running after failure');
  });
  window.demoProgressPreview = phase => {
    const progress = _showDemoConnectProgress('后内饰一线');
    progress.update(phase, [{ processes: Array.from({ length: 27 }, () => ({})) }, { processes: Array.from({ length: 18 }, () => ({})) }]);
  };
  return results;
}
