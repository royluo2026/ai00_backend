import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { JSDOM } from 'jsdom';

const __dirname = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(resolve(__dirname, '../core/auth_state.js'), 'utf8');

function boot() {
  const dom = new JSDOM('<!doctype html><html><body></body></html>', {
    url: 'https://workmanship-web-dev.chehejia.com/web/index.html',
    runScripts: 'dangerously',
  });

  let fetchedUrl = null;
  dom.window.fetch = async (url) => {
    fetchedUrl = url;
    return {
      ok: true,
      json: async () => ({ grants: ['team_admin'], org_role: 'member' }),
    };
  };

  dom.window.AI00RuntimeConfig = {
    defaultLocalBackend: 'http://127.0.0.1:8080',
    resolveBackendBase: async () => 'https://workmanship-backend-dev.chehejia.com',
  };

  dom.window.electronAPI = {
    authGetState: async () => ({
      mode: 'feishu',
      token: 'token-123',
      user: { gid: 'u1', org_role: 'external', grants: [] },
    }),
  };

  dom.window.eval(source);
  return { window: dom.window, getFetchedUrl: () => fetchedUrl };
}

test('auth state refresh uses runtime resolver when backend base is not stored yet', async () => {
  const { window, getFetchedUrl } = boot();
  await window.AuthStateManager.init();
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(getFetchedUrl(), 'https://workmanship-backend-dev.chehejia.com/users/me');
});
