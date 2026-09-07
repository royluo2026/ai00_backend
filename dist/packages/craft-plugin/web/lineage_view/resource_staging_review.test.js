'use strict';
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const source = fs.readFileSync(__dirname + '/staging_panel.js', 'utf8');
const sandbox = { module: { exports: {} }, console, window: {}, document: {} };
vm.runInNewContext(`${source}\nmodule.exports = { _resourceStagingUrl, _resourceCandidateUrl, _resourceResolvePayload, _resourceIgnorePayload };`, sandbox);
const api = sandbox.module.exports;

assert.strictEqual(api._resourceStagingUrl('v 1'), '/api/craft/tc-resource-staging?version_gid=v%201');
assert.strictEqual(api._resourceCandidateUrl('socket'), '/api/craft/resource-requirements?resource_type=socket');
assert.deepStrictEqual(
  JSON.parse(JSON.stringify(api._resourceResolvePayload({ gid: 's-1', resource_version: 3 }, 'r-1'))),
  { resource_gid: 'r-1', expected_staging_version: 3 },
);
assert.deepStrictEqual(
  JSON.parse(JSON.stringify(api._resourceIgnorePayload({ gid: 's-1', resource_version: 3 }))),
  { expected_staging_version: 3 },
);
console.log('resource staging review contract: OK');
