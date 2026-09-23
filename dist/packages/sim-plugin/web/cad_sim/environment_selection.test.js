const test = require('node:test');
const assert = require('node:assert/strict');
const { createEnvironmentStore } = require('./environment_store');

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

test('environment read backs off only on transient capacity rejection and stops after three attempts',async()=>{
  let calls=0;const delays=[];
  const store=createEnvironmentStore({wait:async ms=>delays.push(ms),invoke:async()=>{
    if(++calls<3) throw Object.assign(Error('capacity_unavailable'),{retryable:true});
    return {workspace_gid:'1'};
  }});
  await store.openWorkspace('1');
  assert.equal(calls,3);assert.deepEqual(delays,[300,900]);assert.equal(store.state.workspace.workspace_gid,'1');
  let failed=0;
  const unavailable=createEnvironmentStore({wait:async()=>{},invoke:async()=>{failed++;throw Error('capacity_unavailable');}});
  await assert.rejects(unavailable.openWorkspace('1'),/capacity_unavailable/);
  assert.equal(failed,3);assert.equal(unavailable.state.error.capabilityId,'simulation.environment.workspace.get');
});

test('capacity backoff cannot retry a superseded environment and never retries permission errors',async()=>{
  const pause=deferred();let calls=0;
  const store=createEnvironmentStore({wait:()=>pause.promise,invoke:async()=>{calls++;throw Error('capacity_unavailable');}});
  const pending=store.openWorkspace('1');await new Promise(resolve=>setImmediate(resolve));
  store.clearSelection();pause.resolve();assert.equal(await pending,null);assert.equal(calls,1);
  const denied=createEnvironmentStore({wait:()=>assert.fail('no retry'),invoke:async()=>{throw Error('permission_denied');}});
  await assert.rejects(denied.openWorkspace('1'),/permission_denied/);
});

test('late environment A cannot overwrite a more recent B selection', async () => {
  const a = deferred();
  const store = createEnvironmentStore({ invoke: async (_, payload) =>
    payload.workspace_gid === '1' ? a.promise : { workspace_gid: '2' } });
  const pending = store.openWorkspace('1');
  await store.openWorkspace('2');
  a.resolve({ workspace_gid: '1' });
  assert.equal(await pending, null);
  assert.equal(store.state.workspace.workspace_gid, '2');
});

test('adoption selection guard is checked after authoritative read before commit', async () => {
  const read = deferred();
  let current = true;
  const store = createEnvironmentStore({ invoke: () => read.promise });
  store.applyServerUpdate({ workspace: { workspace_gid: '2' } });
  const pending = store.openWorkspace('1', { isCurrent: () => current });
  current = false;
  read.resolve({ workspace_gid: '1' });
  assert.equal(await pending, null);
  assert.equal(store.state.workspace.workspace_gid, '2');
  assert.equal(store.state.loading, false);
});

test('late cached A cannot overwrite a newer team-space selection', async () => {
  const read = deferred();
  const store = createEnvironmentStore({ getAuthSubjectGid: () => '30',
    cache: { getWorkspace: () => read.promise },
    invoke: async (id) => id.endsWith('cache_lease.get') ? { read_lease: 'test' } : { space_gid: '2' } });
  const pending = store.openWorkspace('1');
  await Promise.resolve();
  await store.openRecord('team', '2');
  read.resolve({ workspace: { workspace_gid: '1' } });
  assert.equal(await pending, null);
  assert.equal(store.state.workspace.workspace_gid, '2');
  assert.equal(store.state.currentKind, 'team');
});

test('late failure of A cannot replace the current B error/loading state', async () => {
  const a = deferred();
  const store = createEnvironmentStore({ invoke: async (_, payload) =>
    payload.workspace_gid === '1' ? a.promise : { workspace_gid: '2' } });
  const pending = store.openWorkspace('1');
  await store.openWorkspace('2');
  a.reject(new Error('offline_A'));
  assert.equal(await pending, null);
  assert.equal(store.state.error, null);
  assert.equal(store.state.loading, false);
});

test('late team-space read cannot overwrite a newer private environment', async () => {
  const a = deferred();
  const store = createEnvironmentStore({ invoke: async (id) =>
    id.startsWith('craft.') ? a.promise : { workspace_gid: '2' } });
  const pending = store.openRecord('team', '1');
  await store.openWorkspace('2');
  a.resolve({ space_gid: '1' });
  assert.equal(await pending, null);
  assert.equal(store.state.workspace.workspace_gid, '2');
});

test('unbound native selection clears only UI state and fences pending environment read', async () => {
  const read = deferred();
  const store = createEnvironmentStore({ invoke: () => read.promise });
  const pending = store.openWorkspace('1');
  store.clearSelection();
  read.resolve({ workspace_gid: '1' });
  assert.equal(await pending, null);
  assert.equal(store.state.workspace, null);
  assert.equal(store.state.loading, false);
});
