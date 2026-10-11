import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';

const source = readFileSync(new URL('../workspace/nav_manager.js', import.meta.url), 'utf8');
const tabSource = readFileSync(new URL('../workspace/tab_manager.js', import.meta.url), 'utf8');
const workbenchSource = readFileSync(new URL('../workbench/workbench.js', import.meta.url), 'utf8');
const paletteSource = readFileSync(new URL('../core/cmd_palette.js', import.meta.url), 'utf8');
const contentCardSource = readFileSync(new URL('../container_card/viewer.js', import.meta.url), 'utf8');

test('reachable legacy content card renders untrusted mode and errors as text', () => {
  for (const [mode, renderer, expected] of [
    ['<img src=x onerror="window.__injected=1">', {}, '未知模式: <img'],
    ['thrower', { thrower: { renderFullPage() { throw Error('<svg onload="window.__injected=1">'); } } }, '渲染失败'],
  ]) {
    const dom = new JSDOM('<span id="ccTitle"></span><div id="ccBody"></div>', {
      url: 'http://localhost/web/container_card/index.html?mode=' + encodeURIComponent(mode),
      runScripts: 'dangerously',
    });
    const { window } = dom;
    try {
      window.console.error = () => {};
      window.ContainerModes = renderer;
      window.eval(contentCardSource);
      window.document.dispatchEvent(new window.Event('DOMContentLoaded'));
      const body = window.document.getElementById('ccBody');
      assert.ok(body.textContent.startsWith(expected));
      assert.equal(body.querySelector('img, svg'), null);
      assert.equal(window.__injected, undefined);
    } finally {
      window.close();
    }
  }
});

test('content card message path rejects injected mode and retains valid renderer', () => {
  const dom = new JSDOM('<span id="ccTitle"></span><div id="ccBody"></div>', {
    url: 'http://localhost/web/container_card/index.html', runScripts: 'dangerously',
  });
  const { window } = dom;
  try {
    window.ContainerModes = { safe: { renderFullPage(body, params) { body.textContent = params.get('title'); } } };
    window.eval(contentCardSource);
    window.document.dispatchEvent(new window.Event('DOMContentLoaded'));
    window.dispatchEvent(new window.MessageEvent('message', { data: {
      type: 'cc:params', params: { mode: '<svg onload="window.__injected=1">' },
    } }));
    const body = window.document.getElementById('ccBody');
    assert.equal(body.querySelector('svg'), null);
    assert.equal(window.__injected, undefined);
    window.dispatchEvent(new window.MessageEvent('message', { data: {
      type: 'cc:params', params: { mode: 'safe', title: '<b>safe text</b>' },
    } }));
    assert.equal(body.textContent, '<b>safe text</b>');
    assert.equal(body.querySelector('b'), null);
  } finally {
    window.close();
  }
});

function navigation(isElectron) {
  const dom = new JSDOM('<div id="nav-items-top"></div><button id="nav-more-btn"></button><div id="nav-more-panel" class="hidden"><div class="more-panel-list"></div></div>', {
    url: 'http://localhost/web/index.html',
    runScripts: 'dangerously',
  });
  const { window } = dom;
  window.electronAPI = { _isElectron: isElectron };
  window._authMode = 'feishu';
  window._hasTabPerm = () => true;
  window.TabManager = { activeId: () => 'workbench', open() {} };
  window.localStorage.setItem('ui.nav.state', JSON.stringify({
    defaultsVersion: 2,
    visible: ['workbench', 'project_hub', 'craft_hub', 'knowledge_hub'],
    hidden: ['automation_hub'],
  }));
  window.eval(source);
  return window;
}

test('browser navigation exposes only workbench and craft even with saved modules', async () => {
  const window = navigation(false);
  window.NavManager.render();
  assert.deepEqual(
    [...window.document.querySelectorAll('#nav-items-top [data-view]')].map(el => el.dataset.view),
    ['workbench', 'craft_hub'],
  );
  assert.equal(window.NavManager.isTopLevelAllowed('project_hub'), false);
  assert.equal(window.NavManager.isTopLevelAllowed('container_card'), true);
  window.NavManager.boot();
  window.document.getElementById('nav-more-btn').click();
  assert.equal(window.document.querySelector('.more-panel-list').textContent.includes('自动化与AI'), false);
  await new Promise(resolve => window.setTimeout(resolve, 0));
  window.close();
});

test('desktop navigation keeps other modules', () => {
  const window = navigation(true);
  window.NavManager.render();
  assert.deepEqual(
    [...window.document.querySelectorAll('#nav-items-top [data-view]')].map(el => el.dataset.view),
    ['workbench', 'project_hub', 'craft_hub', 'knowledge_hub', 'model_cache', 'plugin_marketplace', 'cad_sim', 'handbook'],
  );
  window.close();
});

test('browser shows both modules despite a saved hidden layout', () => {
  const window = navigation(false);
  window.localStorage.setItem('ui.nav.state', JSON.stringify({ defaultsVersion: 2, visible: ['project_hub'], hidden: ['workbench', 'craft_hub'] }));
  window.NavManager.render();
  assert.deepEqual([...window.document.querySelectorAll('#nav-items-top [data-view]')].map(el => el.dataset.view), ['workbench', 'craft_hub']);
  assert.equal(window.document.getElementById('nav-more-btn').style.display, 'none');
  window.close();
});

test('browser welcome offers two modules while desktop keeps project quick action', () => {
  for (const isElectron of [false, true]) {
    const dom = new JSDOM('', { url: 'http://localhost/web/index.html', runScripts: 'dangerously' });
    const { window } = dom;
    let welcome = '';
    window.electronAPI = { _isElectron: isElectron };
    window._authMode = 'none';
    window.WorkspaceEngine = { init() {}, addTab(_id, _title, _src, opts) { welcome = opts.html; } };
    window.eval(tabSource);
    window.TabManager.boot();
    assert.match(welcome, /TabManager\.open\('workbench'\)/);
    assert.match(welcome, /TabManager\.open\('craft_hub'\)/);
    assert.equal(welcome.includes("TabManager.open('project_hub')"), isElectron);
    window.close();
  }
});

test('browser retains craft hub and internal detail page opening', () => {
  const dom = new JSDOM('', { url: 'http://localhost/web/index.html', runScripts: 'dangerously' });
  const { window } = dom;
  const opened = [];
  window.electronAPI = { _isElectron: false };
  window._authMode = 'feishu';
  window._hasTabPerm = () => true;
  window.WorkspaceEngine = { hasTab: () => false, addTab(id, _title, src) { opened.push([id, src]); } };
  window.eval(tabSource);
  window.TabManager.registerTab('project', { title: '项目清单', src: '../packages/craft-plugin/web/project/project.html' });
  window.TabManager.open('craft_hub');
  window.TabManager.open('container_card');
  window.TabManager.open('project');
  window.TabManager.open('project_hub');
  window.TabManager.open('knowledge_hub');
  assert.deepEqual(opened, [
    ['craft_hub', '../packages/craft-plugin/web/craft_hub/index.html'],
    ['container_card', 'container_card/index.html'],
    ['project', '../packages/craft-plugin/web/project/project.html'],
  ]);
  window.close();
});

test('workbench app grid and its more menu omit other modules only in browser', () => {
  // Exercise the real workbench renderer without starting its unrelated data-fetching dashboard.
  const instrumented = workbenchSource.replace(
    /  if \(document\.readyState === 'loading'\) \{[\s\S]*?\r?\n  \}\r?\n\r?\n\}\)\(\);\s*$/,
    '  window.__renderAppPanelForTest = _renderAppPanel;\n})();',
  );
  assert.ok(instrumented !== workbenchSource, 'workbench renderer test hook did not match');
  for (const isElectron of [false, true]) {
    const dom = new JSDOM('<div id="wbAppGrid"></div>', { url: 'http://localhost/web/workbench/workbench.html', runScripts: 'dangerously' });
    const { window } = dom;
    try {
      window.electronAPI = { _isElectron: isElectron };
      window._authMode = 'feishu';
      window._hasTabPerm = () => true;
      window.eval(source);
      window.localStorage.setItem('wb:app-items-v1', JSON.stringify(isElectron
        ? { visible: ['workbench', 'project_hub', 'craft_hub'], hidden: ['automation_hub'] }
        : { visible: ['project_hub'], hidden: ['workbench', 'craft_hub', 'automation_hub'] }));
      window.eval(instrumented);
      window.__renderAppPanelForTest();
      const ids = [...window.document.querySelectorAll('#wbAppGrid [data-app-id]')].map(el => el.dataset.appId);
      assert.equal(ids.includes('project_hub'), isElectron);
      assert.ok(ids.includes('workbench') && ids.includes('craft_hub'));
      if (isElectron) {
        window.document.querySelector('.wb-app-more').click();
        assert.ok(window.document.getElementById('_wbAppMore').textContent.includes('自动化与AI'));
      } else {
        assert.equal(window.document.querySelector('.wb-app-more'), null);
      }
    } finally {
      window.close();
    }
  }
});

test('browser command palette shows workbench and craft but not other top-level modules', () => {
  for (const isElectron of [false, true]) {
    const dom = new JSDOM('<div id="cmd-overlay" class="hidden"></div><input id="cmd-input"><div id="cmd-results"></div>', {
      url: 'http://localhost/web/index.html', runScripts: 'dangerously',
    });
    const { window } = dom;
    window.electronAPI = { _isElectron: isElectron };
    window.requestAnimationFrame = () => {};
    window.eval(paletteSource);
    window.CmdPalette.show();
    const names = window.document.getElementById('cmd-results').textContent;
    assert.ok(names.includes('工作台'));
    assert.equal(names.includes('项目管理'), isElectron);
    assert.equal(names.includes('自动化与AI'), isElectron);
    if (!isElectron) assert.ok(names.includes('工艺规划'));
    window.close();
  }
});

test('legacy workbench follows keep untrusted types inert and do not open arbitrary tabs', () => {
  const initStart = workbenchSource.lastIndexOf("  if (document.readyState === 'loading')");
  assert.ok(initStart > 0);
  const instrumented = workbenchSource.slice(0, initStart) +
    '  window.__renderFollowsForTest = _renderPanelFollows;\n})();';
  const dom = new JSDOM('<div id="wb-body-4"></div>', {
    url: 'http://localhost/web/workbench/workbench.html', runScripts: 'dangerously',
  });
  const { window } = dom;
  const opened = [];
  window.TabManager = { open: type => opened.push(type) };
  window.HTMLElement.prototype.scrollIntoView = () => {};
  try {
    window.eval(instrumented);
    window.__renderFollowsForTest([
      { item_gid: 'x" onclick="window.__pwned=1', item_type: '"><img src=x onerror=alert(1)>', item_title: '<script>unsafe</script>' },
      { item_gid: 'proto-1', item_type: 'constructor', item_title: '未知类型' },
      ...['task', 'issue', 'knowledge', 'rule'].map(type => ({ item_gid: type + '-1', item_type: type, item_title: type })),
    ]);
    const rows = [...window.document.querySelectorAll('#wb-body-4 .wb-row')];
    assert.equal(rows.length, 6);
    assert.equal(window.document.querySelector('#wb-body-4 img, #wb-body-4 script'), null);
    assert.match(rows[0].textContent, /<script>unsafe<\/script>/);
    assert.match(rows[0].textContent, /详情待核/);
    assert.match(rows[1].textContent, /详情待核/);
    rows.forEach(row => row.click());
    assert.deepEqual(opened, ['task', 'issue', 'knowledge', 'rule']);
    assert.equal(window.__pwned, undefined);
  } finally {
    window.close();
  }
});
