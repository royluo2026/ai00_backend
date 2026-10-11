'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const { JSDOM } = require('jsdom');

const root = path.resolve(__dirname, '../..');
const html = fs.readFileSync(path.join(root, 'web/index.html'), 'utf8');
const script = fs.readFileSync(path.join(__dirname, 'statusbar_build_info.js'), 'utf8');
const frontendVersion = require('../frontend-version.json').version;

async function render(backendUrl, { vite = false, release = null, envMap = {}, missingBridge = false, browser = false, clientType = 'browser', prefix } = {}) {
  const dom = new JSDOM(html, { runScripts: 'outside-only', url: 'http://127.0.0.1:5173/web/index.html' });
  if (!browser) dom.window.electronAPI = missingBridge ? {} : { getConfig: async () => ({ backendUrl, version: '9.9.9', clientType }) };
  dom.window.AI00RuntimeConfig = {
    getRuntimeBackendBase: async explicit => explicit,
    isViteDevServerLocation: () => vite,
    loadBackendEnvMapAsync: async () => envMap,
  };
  const requests = [];
  dom.window.fetch = async (url, options) => {
    requests.push({ url, options });
    if (url.endsWith('/api/runtime/data-environment')) return { ok: prefix !== undefined, json: async () => ({ prefix }) };
    return { ok: !!release, json: async () => release };
  };
  dom.window.eval(script);
  await new Promise(resolve => setImmediate(resolve));
  const version = dom.window.document.getElementById('sb-program-version').textContent;
  const environment = dom.window.document.getElementById('sb-runtime-environment').textContent;
  const title = dom.window.document.getElementById('sb-build-info').title;
  const database = dom.window.document.getElementById('data-environment-badge');
  const databaseLabel = database?.textContent;
  const databasePrefix = database?.dataset.prefix;
  dom.window.close();
  return { version, environment, title, requests, databaseLabel, databasePrefix };
}

test('status bar keeps the frontend version distinct from program and Electron versions', async () => {
  assert.match(html, new RegExp(`<meta name="app-version" content="${frontendVersion.replaceAll('.', '\\.')}">`));
  const info = await render('', { vite: true });
  assert.equal(info.version, '整体版本未标记');
  assert.match(info.title, new RegExp(`前端版本：v${frontendVersion.replaceAll('.', '\\.')}`));
  assert.match(info.title, /后端版本：未标记/);
  assert.equal(info.requests[0].url, '/api/system/version');
  assert.equal(info.requests[0].options.cache, 'no-store');
});

test('status bar reports the resolved backend environment without guessing unfamiliar hosts', async () => {
  for (const [url, expected] of [
    ['', '本机'],
    ['http://127.0.0.1:8080', '本机'],
    ['http://localhost:8080', '本机'],
    ['https://workmanship-backend-test.chehejia.com', 'workmanship-backend-test.chehejia.com'],
    ['https://workmanship-backend-staging.chehejia.com', 'workmanship-backend-staging.chehejia.com'],
    ['https://workmanship-backend.chehejia.com', '生产环境'],
    ['http://pc-pc2l7vve:8080', 'pc-pc2l7vve'],
    ['https://unknown.example.com', 'unknown.example.com'],
    ['', '后端地址未配置'],
  ]) {
    const info = await render(url, { vite: expected === '本机' && url === '' });
    assert.equal(info.environment, expected, `${url}: ${expected}`);
    if (url) assert.match(info.title, new RegExp(`后端地址：${url.replaceAll('.', '\\.')}`));
  }
  assert.equal((await render('https://internal.example.com', {
    envMap: { prod: 'https://internal.example.com' },
  })).environment, 'internal.example.com');
});

test('a missing desktop config bridge is not misreported as an unconfigured backend', async () => {
  const info = await render('', { missingBridge: true });
  assert.equal(info.environment, '桌面配置未加载');
  assert.match(info.title, /后端地址：未取得/);
  assert.equal(info.requests.length, 0);
});

test('program release must bind this frontend and a separately reported backend version', async () => {
  const valid = await render('http://127.0.0.1:8080', {
    release: { frontendVersions: { browser: frontendVersion, desktop: '1.1.0' }, backendVersion: '0.1.0-dev', programVersion: '2.0.0' },
  });
  assert.equal(valid.version, '整体 v2.0.0');
  assert.match(valid.title, /整体版本：v2.0.0\n前端版本：v1.0.3\n后端版本：v0.1.0-dev/);
  const stale = await render('http://127.0.0.1:8080', {
    release: { frontendVersions: { browser: '1.0.7', desktop: frontendVersion }, backendVersion: '0.1.0-dev', programVersion: '2.0.0' },
  });
  assert.equal(stale.version, '整体版本未标记');
  assert.match(stale.title, /后端版本：v0.1.0-dev/);
  const desktop = await render('http://127.0.0.1:8080', {
    clientType: 'desktop',
    release: { frontendVersions: { browser: '1.0.7', desktop: frontendVersion }, backendVersion: '0.1.0-dev', programVersion: '2.0.0' },
  });
  assert.equal(desktop.version, '整体 v2.0.0');
  const unidentified = await render('http://127.0.0.1:8080', {
    clientType: '',
    release: { frontendVersions: { browser: frontendVersion, desktop: frontendVersion }, backendVersion: '0.1.0-dev', programVersion: '2.0.0' },
  });
  assert.equal(unidentified.version, '整体版本未标记');
});

test('status bar does not display malformed backend or overall versions', async () => {
  const invalidBackend = await render('http://127.0.0.1:8080', {
    release: { frontendVersions: { browser: frontendVersion }, backendVersion: 'v1.2.0', programVersion: '2.0.0' },
  });
  assert.equal(invalidBackend.version, '整体版本未标记');
  assert.match(invalidBackend.title, /后端版本：未标记/);
  const invalidOverall = await render('http://127.0.0.1:8080', {
    release: { frontendVersions: { browser: frontendVersion }, backendVersion: '1.2.0', programVersion: 'release-candidate' },
  });
  assert.equal(invalidOverall.version, '整体版本未标记');
  assert.match(invalidOverall.title, /后端版本：v1\.2\.0/);
});

test('Browser without an Electron bridge binds its own frontend version to the overall release', async () => {
  const info = await render('', { browser: true, vite: true, release: {
    frontendVersions: { browser: frontendVersion, desktop: '0.1.0-dev' },
    backendVersion: '1.2.0', programVersion: '2.0.0',
  } });
  assert.equal(info.environment, '本机');
  assert.equal(info.version, '整体 v2.0.0');
  assert.equal(info.requests[0].url, '/api/system/version');
});

 test('database status sits beside the runtime location and reads the effective backend without a login token', async () => {
  const dom = new JSDOM(html);
  const badge = dom.window.document.getElementById('data-environment-badge');
  assert.equal(badge.parentElement.id, 'sb-build-info');
  assert.equal(badge.previousElementSibling.previousElementSibling.id, 'sb-runtime-environment');
  dom.window.close();
  for (const [prefix, label] of [['test_', '测试数据库'], ['pp_', '预生产数据库'], ['', '生产数据库']]) {
    const info = await render('http://127.0.0.1:8080', { prefix });
    assert.equal(info.databaseLabel, label);
    assert.equal(info.databasePrefix, prefix);
    assert.ok(info.requests.some(r => r.url === 'http://127.0.0.1:8080/api/runtime/data-environment'));
  }
 });

test('Desktop status uses its existing capability bridge instead of blocked renderer HTTP', async () => {
 const dom = new JSDOM(html, { runScripts: 'outside-only', url: 'app://root/web/index.html' });
 dom.window.electronAPI = { getConfig: async () => ({ backendUrl: 'http://127.0.0.1:8080', clientType: 'desktop' }) };
 dom.window.AI00RuntimeConfig = { getRuntimeBackendBase: async value => value };
 const calls = [];
 dom.window.AI00Business = { invoke: async (id, body) => { calls.push([id,body]); return { prefix: 'test_' }; } };
 dom.window.fetch = async () => { throw Error('renderer_network_blocked'); };
 dom.window.eval(script);
 await new Promise(resolve => setImmediate(resolve));
 const label = dom.window.document.getElementById('data-environment-badge').textContent;
 dom.window.close();
 assert.equal(label, '测试数据库');
 assert.equal(calls[0][0], 'base.runtime.data_environment.active.get');
});
