import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

const engineUrl = new URL('../examples/bop-line-compare/compare-engine.js', import.meta.url);
const engine = fs.existsSync(fileURLToPath(engineUrl)) ? await import(engineUrl) : {};

test('alignOperations prefers exact non-empty VPPS', () => {
  assert.equal(typeof engine.alignOperations, 'function');
  const result = engine.alignOperations(
    [{ operation_id: 'l1', name: '拧紧后副车架', parameters: { vpps: 'TA-340' } }],
    [{ operation_id: 'r1', name: '后副车架拧紧', parameters: { vpps: 'TA-340' } }],
  );

  assert.equal(result.exact.length, 1);
  assert.equal(result.exact[0].method, 'vpps');
  assert.equal(result.exact[0].score, 1);
  assert.equal(result.fuzzy.length, 0);
});

test('alignOperations labels description-only matches as fuzzy', () => {
  const result = engine.alignOperations(
    [{ operation_id: 'l1', name: '安装前门线束', parameters: { vpps: null } }],
    [{ operation_id: 'r1', name: '前门线束安装', parameters: { vpps: null } }],
  );

  assert.equal(result.exact.length, 0);
  assert.equal(result.fuzzy.length, 1);
  assert.equal(result.fuzzy[0].method, 'description');
  assert.ok(result.fuzzy[0].score >= 0.46 && result.fuzzy[0].score < 1);
  assert.ok(result.fuzzy[0].reasons.includes('操作描述相似'));
});

test('searchOperationCandidates ranks a manual fuzzy query deterministically', () => {
  const operations = [
    { operation_id: 'op-2', name: '安装蓄电池托盘', parameters: { vpps: 'EL-100' } },
    { operation_id: 'op-1', name: '拧紧后副车架', parameters: { vpps: 'TA-340' } },
    { operation_id: 'op-3', name: '后副车架定位', parameters: { vpps: 'TA-330' } },
  ];

  const result = engine.searchOperationCandidates('副车架 拧紧', operations, 2);

  assert.equal(result.length, 2);
  assert.equal(result[0].operation.operation_id, 'op-1');
  assert.ok(result[0].score > result[1].score);
});

test('alignOperations never fuzzy-pairs an operation already consumed by VPPS', () => {
  const result = engine.alignOperations(
    [
      { operation_id: 'l1', name: '拧紧后副车架', parameters: { vpps: 'TA-340' } },
      { operation_id: 'l2', name: '后副车架拧紧复检', parameters: { vpps: null } },
    ],
    [{ operation_id: 'r1', name: '后副车架拧紧', parameters: { vpps: 'TA-340' } }],
  );

  assert.equal(result.exact.length, 1);
  assert.equal(result.fuzzy.length, 0);
  assert.equal(result.unmatchedLeft[0].operation_id, 'l2');
});

test('compareRefs returns deterministic common and side-only sets', () => {
  assert.equal(typeof engine.compareRefs, 'function');
  assert.deepEqual(
    engine.compareRefs(['part:b', 'part:a', 'part:b'], ['part:c', 'part:b']),
    { common: ['part:b'], leftOnly: ['part:a'], rightOnly: ['part:c'] },
  );
});
