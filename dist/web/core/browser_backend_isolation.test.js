'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const { JSDOM } = require('jsdom');

const source = fs.readFileSync(path.join(__dirname, 'web_compat.js'), 'utf8');
const productionBackend = 'https://workmanship-backend.chehejia.com';
const publishedMap = require('../runtime-env.json').backendByEnv;

function browser(url, envMap) {
  const dom = new JSDOM('<meta name="app-version" content="1.0.3">', {
    url: `${url}/web/login/index.html`, runScripts: 'outside-only',
  });
  dom.window.fetch = async () => ({ ok: true, json: async () => ({ backendByEnv: envMap }) });
  dom.window.localStorage.setItem('ai00_backend_url', 'http://127.0.0.1:8082');
  dom.window.localStorage.setItem('ai00_backend_by_env', JSON.stringify({ prod: 'http://127.0.0.1:8082' }));
  dom.window.__AI00_BACKEND_BY_ENV = { prod: 'http://127.0.0.1:8082' };
  dom.window.eval(source);
  return dom;
}

test('Vite Browser requests remain relative despite stored or explicit production addresses', async () => {
  const dom = browser('http://127.0.0.1:5173', { prod: productionBackend });
  try {
    assert.equal(await dom.window.AI00RuntimeConfig.getRuntimeBackendBase(productionBackend), '');
    assert.equal(await dom.window.electronAPI.getConfig().then(config => config.backendUrl), '');
    assert.equal(dom.window.AI00RuntimeConfig.storeBackendBase(''), '');
    assert.equal(dom.window.localStorage.getItem('ai00_backend_url'), null);
  } finally {
    dom.window.close();
  }
});

test('production Browser ignores old localStorage, injected map and explicit test URL', async () => {
  assert.equal(publishedMap.prod, productionBackend);
  const dom = browser('https://workmanship-web.chehejia.com', publishedMap);
  try {
    const config = dom.window.AI00RuntimeConfig;
    assert.equal(await config.getRuntimeBackendBase('http://127.0.0.1:8080'), productionBackend);
    assert.equal(config.storeBackendBase(productionBackend), productionBackend);
    assert.equal(config.toAbsoluteBackendUrl('/api/system/version'), `${productionBackend}/api/system/version`);
  } finally {
    dom.window.close();
  }
});

test('an unknown Browser host cannot inherit a stored backend URL', async () => {
  const dom = browser('https://other.example.com', publishedMap);
  try {
    await assert.rejects(dom.window.AI00RuntimeConfig.getRuntimeBackendBase('http://127.0.0.1:8082'));
  } finally {
    dom.window.close();
  }
});

test('production Browser fails closed when its published map is absent or points at test', async () => {
  for (const map of [{}, { prod: 'https://workmanship-backend-test.chehejia.com' }]) {
    const dom = browser('https://workmanship-web.chehejia.com', map);
    try {
      await assert.rejects(dom.window.AI00RuntimeConfig.getRuntimeBackendBase('http://127.0.0.1:8080'));
    } finally {
      dom.window.close();
    }
  }
});
