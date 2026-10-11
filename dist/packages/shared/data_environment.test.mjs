import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { renderDataEnvironment, mountDataEnvironmentSettings } from './data_environment.mjs';
import { initializeEnvironmentSettings } from '../../web/core/data_environment_settings_entry.mjs';

test('expired session confirms actual switched prefix without granting privileged controls', async () => {
 const dom = new JSDOM('<section id="settings"></section>');
 const container = dom.window.document.getElementById('settings');
 let switched = false;
 const widget = mountDataEnvironmentSettings(dom.window.document, container, async id => {
   if (id.endsWith('change.apply')) { switched = true; return { accepted:true, prefix:'pp_', restarting:true }; }
   if (switched) throw Error('unauthorized');
   return { active_prefix:'test_', options:['test_','pp_'].map(prefix => ({prefix,available:true,reasons:[]})) };
 }, { visibleOnFailure:true, readActive: async () => ({prefix:'pp_'}) });
 await widget.load();
 const select = container.querySelector('select'); select.value='pp_'; select.dispatchEvent(new dom.window.Event('change'));
 container.querySelector('.de-primary').click(); await Promise.resolve(); await Promise.resolve();
 await widget.load();
 assert.equal(container.querySelector('progress').value,4);
 assert.match(container.querySelector('.de-current').textContent,/预生产数据库/);
 assert.match(container.textContent,/重新登录/);
 assert.equal(container.querySelector('.de-primary').disabled,true);
 assert.equal(select.disabled,true);
 widget.dispose(); dom.window.close();
});

test('public status with the old prefix does not confirm a switch', async () => {
 const dom = new JSDOM('<section id="settings"></section>');
 const container = dom.window.document.getElementById('settings');
 let switched = false;
 const widget = mountDataEnvironmentSettings(dom.window.document, container, async id => {
   if (id.endsWith('change.apply')) { switched = true; return {accepted:true,prefix:'pp_',restarting:true}; }
   if (switched) throw Error('unauthorized');
   return {active_prefix:'test_',options:['test_','pp_'].map(prefix=>({prefix,available:true,reasons:[]}))};
 }, {visibleOnFailure:true,readActive:async()=>({prefix:'test_'})});
 await widget.load();
 const select=container.querySelector('select'); select.value='pp_'; select.dispatchEvent(new dom.window.Event('change'));
 container.querySelector('.de-primary').click(); await Promise.resolve(); await Promise.resolve();
 await widget.load();
 assert.notEqual(container.querySelector('progress').value,4);
 assert.match(container.querySelector('.de-current').textContent,/测试数据库/);
 assert.equal(container.querySelector('.de-primary').disabled,true);
 widget.dispose(); dom.window.close();
});

test('accepted switch retries through backend downtime without reporting permission failure', async (t) => {
 t.mock.timers.enable({ apis: ['setTimeout'] });
 const dom = new JSDOM('<section id="settings"></section>');
 const container = dom.window.document.getElementById('settings');
 let switched = false, checks = 0;
 const widget = mountDataEnvironmentSettings(dom.window.document, container, async id => {
   if (id.endsWith('change.apply')) { switched = true; return {accepted:true,prefix:'pp_',restarting:true}; }
   if (switched && ++checks === 1) throw Error('network unavailable');
   return {active_prefix: switched ? 'pp_' : 'test_',pending:false,options:['test_','pp_',''].map(prefix => ({prefix,available:prefix!=='',reasons:[],difference_count:0}))};
 }, {visibleOnFailure:true});
 await widget.load();
 const select = container.querySelector('select'); select.value = 'pp_'; select.dispatchEvent(new dom.window.Event('change'));
 container.querySelector('.de-primary').click();
 await Promise.resolve(); await Promise.resolve();
 t.mock.timers.tick(6000); await Promise.resolve(); await Promise.resolve();
 assert.match(container.textContent, /自动重新检查/);
 assert.equal(container.querySelector('progress').value, 2);
 assert.doesNotMatch(container.textContent, /权限不足/);
 t.mock.timers.tick(6000); await Promise.resolve(); await Promise.resolve();
 assert.match(container.querySelector('.de-current').textContent, /预生产数据库/);
 assert.equal(select.value, 'pp_');
 assert.equal(container.querySelector('progress').value, 4);
 widget.dispose?.(); dom.window.close();
});

test('restart timeout is shown explicitly and never presented as success', async (t) => {
 t.mock.timers.enable({apis:['Date','setTimeout']});
 const dom = new JSDOM('<section id="settings"></section>');
 const container = dom.window.document.getElementById('settings');
 let switched = false;
 const widget = mountDataEnvironmentSettings(dom.window.document, container, async id => {
   if (id.endsWith('change.apply')) { switched=true; return {accepted:true,prefix:'pp_',restarting:true}; }
   if (switched) throw Error('offline');
   return {active_prefix:'test_',pending:false,options:['test_','pp_'].map(prefix=>({prefix,available:true,reasons:[],difference_count:0}))};
 }, {visibleOnFailure:true});
 await widget.load();
 const select=container.querySelector('select'); select.value='pp_'; select.dispatchEvent(new dom.window.Event('change'));
 container.querySelector('.de-primary').click();
 await Promise.resolve(); await Promise.resolve();
 t.mock.timers.tick(123000); await Promise.resolve(); await Promise.resolve();
 assert.match(container.textContent,/后端重启超时/);
 assert.equal(container.querySelector('.de-progress').dataset.state,'error');
 assert.notEqual(container.querySelector('progress').value,4);
 widget.dispose(); dom.window.close();
});

test('legacy settings initializes controls without waiting for app configuration', async () => {
 const dom = new JSDOM('<section id="data-environment-settings">正在读取</section>');
 let finish;
 const request = new Promise(resolve => { finish = resolve; });
 const widget = initializeEnvironmentSettings(dom.window.document, { invoke: () => request });
 const container = dom.window.document.getElementById('data-environment-settings');
 assert.equal(container.querySelectorAll('button').length, 3);
 assert.match(container.textContent, /正在检查表结构/);
 finish({ active_prefix: 'test_', options: [{ prefix: 'test_', available: true, reasons: [] }] });
 await widget.load();
 assert.match(container.textContent, /当前连接.*测试数据库/);
 dom.window.close();
});

test('connection test uses backend runtime connection independently of selected target', async () => {
 const dom = new JSDOM('<section id="settings"></section>');
 const container = dom.window.document.getElementById('settings');
 const calls = [];
 const widget = mountDataEnvironmentSettings(dom.window.document, container, async (id, payload) => {
   calls.push({ id, payload });
   if (id.endsWith('connection.test')) return { connected: true, prefix: 'test_', elapsed_ms: 35, error_code: '' };
   return { active_prefix: 'test_', options: ['test_', 'pp_', ''].map(prefix => ({prefix, available: prefix !== '', reasons: [], difference_count: 0})) };
 });
 await widget.load();
 container.querySelector('select').value = 'pp_';
 const button = container.querySelector('[data-action="test-connection"]');
 assert.ok(button);
 button.click();
 await new Promise(resolve => setTimeout(resolve, 0));
 assert.match(container.querySelector('[data-connection-result]').textContent, /测试数据库.*35 ms/);
 assert.deepEqual(calls.at(-1), { id: 'base.runtime.data_environment.connection.test', payload: {} });
 dom.window.close();
});

test('effective prefix has a clear name and distinct color; failure clears stale status', () => {
  const dom = new JSDOM('<div id="badge"></div>');
  const badge = dom.window.document.getElementById('badge');
  const colors = new Set();
  for (const [prefix, label] of [['test_', '测试数据库'], ['pp_', '预生产数据库'], ['', '生产数据库']]) {
    renderDataEnvironment(badge, prefix);
    assert.equal(badge.textContent, label);
    colors.add(badge.style.color);
  }
  assert.equal(colors.size, 3);
  renderDataEnvironment(badge, null);
  assert.equal(badge.textContent, '数据库状态未知');
  dom.window.close();
});

test('unavailable environment cannot be submitted and switching keeps displayed active environment', async () => {
  const dom = new JSDOM('<section id="settings"></section>');
  const container = dom.window.document.getElementById('settings');
  const status = { active_prefix: 'test_', pending: false, options: [
    { prefix: 'test_', available: true, reasons: [] },
    { prefix: 'pp_', available: false, reasons: ['表结构不一致'] },
    { prefix: '', available: false, reasons: ['表缺失'] },
  ] };
  const calls = [];
  const widget = mountDataEnvironmentSettings(dom.window.document, container, async (id, payload) => {
    calls.push({ id, payload }); return status;
  });
  await widget.load();
  const select = container.querySelector('select');
  assert.equal(select.options[1].disabled, true);
  select.value = 'pp_'; select.dispatchEvent(new dom.window.Event('change'));
  const button = [...container.querySelectorAll('button')].find(e => e.textContent === '切换并重启后端');
  assert.equal(button.disabled, true);
  button.click();
  assert.ok(calls.every(call => call.id.endsWith('.get')));
  assert.match(container.textContent, /测试数据库/);
  dom.window.close();
});

test('authorized settings panel keeps its entry visible with retry when inspection fails', async () => {
 const dom = new JSDOM('<section id="settings"></section>');
 const container = dom.window.document.getElementById('settings');
 const widget = mountDataEnvironmentSettings(dom.window.document, container, async () => { throw Error('offline'); }, { visibleOnFailure: true });
 await widget.load();
 assert.equal(container.hidden, false);
 assert.match(container.textContent, /检查失败/);
 assert.equal([...container.querySelectorAll('button')].find(b => b.textContent === '切换并重启后端').disabled, true);
 assert.equal([...container.querySelectorAll('button')].find(b => b.textContent === '重新检查').disabled, false);
 dom.window.close();
});
