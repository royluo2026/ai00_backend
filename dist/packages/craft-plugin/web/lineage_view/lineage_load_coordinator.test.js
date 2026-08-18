'use strict';

const assert = require('assert');
const path = require('path');

const MODULE_PATH = path.join(__dirname, 'lineage_load_coordinator.js');

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

async function runLineageLoadCoordinatorTests() {
  const { LineageLoadCoordinator } = require(MODULE_PATH);

  {
    const coordinator = new LineageLoadCoordinator();
    const first = coordinator.begin('version-a');
    const second = coordinator.begin('version-b');
    assert.strictEqual(first.signal.aborted, true, 'new generation must abort the previous request');
    assert.strictEqual(second.signal.aborted, false);
    assert.strictEqual(second.generation, first.generation + 1);
  }

  {
    const coordinator = new LineageLoadCoordinator();
    const stale = coordinator.begin('version-a');
    const pending = deferred();
    const commits = [];
    const completion = pending.promise.then(value => {
      if (coordinator.isCurrent(stale)) commits.push(value);
    });
    const current = coordinator.begin('version-b');
    coordinator.setRevision(current, 7);
    pending.resolve('stale-value');
    await completion;
    assert.deepStrictEqual(commits, [], 'stale completion must not commit');
    assert.strictEqual(coordinator.isCurrent(current, 7), true);
    assert.strictEqual(coordinator.isCurrent(current, 8), false, 'wrong revision must be stale');
  }

  {
    const coordinator = new LineageLoadCoordinator();
    const pending = deferred();
    let calls = 0;
    const first = coordinator.runSingleFlight('refresh:version-a', () => {
      calls += 1;
      return pending.promise;
    });
    const second = coordinator.runSingleFlight('refresh:version-a', () => {
      calls += 1;
      return Promise.resolve('duplicate');
    });
    assert.strictEqual(first, second, 'duplicate refreshes must share the same promise');
    assert.strictEqual(calls, 1);
    pending.resolve('done');
    assert.strictEqual(await first, 'done');
  }

  {
    const coordinator = new LineageLoadCoordinator();
    let calls = 0;
    await assert.rejects(
      coordinator.runSingleFlight('refresh:version-a', () => {
        calls += 1;
        return Promise.reject(new Error('failed'));
      }),
      /failed/,
    );
    const retry = coordinator.runSingleFlight('refresh:version-a', () => {
      calls += 1;
      return Promise.resolve('recovered');
    });
    assert.strictEqual(await retry, 'recovered', 'rejection must clear the single-flight slot');
    assert.strictEqual(calls, 2);
  }

  {
    const coordinator = new LineageLoadCoordinator();
    const first = coordinator.begin('version-a');
    const second = coordinator.begin('version-b');
    coordinator.dispose();
    assert.strictEqual(first.signal.aborted, true);
    assert.strictEqual(second.signal.aborted, true, 'dispose must abort every outstanding generation');
    assert.strictEqual(coordinator.isCurrent(second), false);
  }
}

if (require.main === module) {
  runLineageLoadCoordinatorTests()
    .then(() => console.log('lineage_load_coordinator: all tests passed'))
    .catch(error => {
      console.error(error);
      process.exitCode = 1;
    });
}

module.exports = { runLineageLoadCoordinatorTests };
