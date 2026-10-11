'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { webcrypto, createHash } = require('node:crypto');
const source = fs.readFileSync(__dirname + '/lineage.js', 'utf8');
const bytes = Buffer.from('test picture bytes');
const ref = { access_grant: 'authorized-grant', media_type: 'image/png', byte_size: bytes.length,
  sha256: createHash('sha256').update(bytes).digest('hex') };
let calls = [], responseBytes = bytes, responseType = 'image/png', responseStatus = 200, bridge = {};
const scope = { _versionGid: 'v1', window: { top: { get electronAPI() { return bridge; } } },
  localStorage: { getItem: () => 'session-token' }, crypto: webcrypto, Blob, AbortSignal,
  URL: { createObjectURL: () => 'blob:verified-picture' },
  fetch: async (url, options) => { calls.push({url, options}); return new Response(responseBytes, {status: responseStatus, headers: {'Content-Type': responseType}}); },
  _pictureReferenceHash: async () => 'hash', _loadPictureAccess: async () => new Map([['hash', ref]]) };
const start = source.includes('let _browserPictureActive =')
  ? source.indexOf('let _browserPictureActive =') : source.indexOf('async function _resolvePicItem(');
vm.createContext(scope);
vm.runInContext(source.slice(start, source.indexOf('async function _pictureReferenceHash(', start)), scope);
(async () => {
  const result = await scope._resolvePicItem({ object_key: 'stored-picture' });
  assert.equal(result.url, 'blob:verified-picture');
  assert.equal(calls[0].url, '/api/v2/capability-artifacts/historical-picture/content');
  assert.equal(calls[0].options.headers['X-AI00-Token'], 'session-token');
  assert.equal(JSON.parse(calls[0].options.body).access_grant, ref.access_grant);
  responseBytes = Buffer.from('corrupt bytes');
  await assert.rejects(scope._resolvePicItem({object_key: 'stored-picture'}), /artifact_integrity_failed/);
  responseBytes = bytes; responseType = 'text/html';
  await assert.rejects(scope._resolvePicItem({object_key: 'stored-picture'}), /picture_transport_failed/);
  responseType = 'image/png'; responseStatus = 403;
  await assert.rejects(scope._resolvePicItem({object_key: 'stored-picture'}), /picture_transport_failed/);
  responseStatus = 200;
  const artifact = {...ref, artifact_id: 'artifact_' + 'a'.repeat(32), version: 1};
  assert.equal((await scope._resolvePicItem({artifact_ref: artifact})).url, 'blob:verified-picture');
  assert.equal(calls.at(-1).url, '/api/v2/capability-artifacts/' + artifact.artifact_id + '/content');
  assert.equal(calls.at(-1).options.body, undefined);
  const fetchPicture = scope.fetch;
  let active = 0, maximumActive = 0;
  scope.fetch = async (...args) => {
    maximumActive = Math.max(maximumActive, ++active);
    await new Promise(resolve => setTimeout(resolve, 5));
    try { return await fetchPicture(...args); } finally { active--; }
  };
  assert.equal((await Promise.all(Array.from({length: 12}, () => scope._resolvePicItem({object_key: 'stored-picture'})))).length, 12);
  assert.equal(maximumActive, 4, 'bulk pictures must wait for an available download slot');
  calls = []; bridge = { _isElectron: true, pictureContentUrl: () => 'ai00-artifact://picture/id' };
  assert.equal((await scope._resolvePicItem({object_key: 'stored-picture'})).url, 'ai00-artifact://picture/id');
  assert.equal(calls.length, 0);
  console.log('Browser picture transport and Electron regression checks passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
