import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { JSDOM, VirtualConsole } from 'jsdom';

const __dirname = dirname(fileURLToPath(import.meta.url));
const compatSource = readFileSync(resolve(__dirname, '../core/web_compat.js'), 'utf8');

function boot(url = 'http://127.0.0.1:5173/web/index.html') {
  const virtualConsole = new VirtualConsole();
  virtualConsole.on('jsdomError', (error) => {
    if (!String(error?.message || '').includes('Not implemented: navigation')) {
      throw error;
    }
  });

  const dom = new JSDOM('<!doctype html><html><body><div id="_auth_gate"></div></body></html>', {
    url,
    runScripts: 'dangerously',
    virtualConsole,
  });

  dom.window.fetch = async () => ({
    ok: false,
    status: 401,
    json: async () => ({}),
  });

  dom.window.eval(compatSource);
  return dom.window;
}

test('local browser mode resolves backend to 127.0.0.1:8080', async () => {
  const win = boot();
  const base = await win.AI00RuntimeConfig.resolveBackendBase('');
  assert.equal(base, 'http://127.0.0.1:8080');
});

test('explicit backendUrl wins over inferred local default', async () => {
  const win = boot();
  const base = await win.AI00RuntimeConfig.resolveBackendBase('https://api.example.com/');
  assert.equal(base, 'https://api.example.com');
});

test('test frontend host rewrites to backend host when no override exists', async () => {
  const win = boot('https://workmanship-web-test.chehejia.com/web/index.html');
  const base = await win.AI00RuntimeConfig.resolveBackendBase('');
  assert.equal(base, 'https://workmanship-backend-test.chehejia.com');
});

test('dev frontend host rewrites to backend host when no override exists', async () => {
  const win = boot('https://workmanship-web-dev.chehejia.com/web/index.html');
  const base = await win.AI00RuntimeConfig.resolveBackendBase('');
  assert.equal(base, 'https://workmanship-backend-dev.chehejia.com');
});
