'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { resolveCaptureLine, createCaptureWorkflow, resolveHierarchyCaptureSource, readCaptureExecutionSource } = require('./capture_workflow.js');

test('alternate hierarchy resolves source BOP identities rather than local workspace GIDs', () => {
  const hierarchy = { workspace_gid:'workspace',hierarchy_gid:'hierarchy',source_bop_version_gid:'version',nodes:[
    {node_gid:'local-line',node_type:'line_process',source_bop_node_gid:'bop-line',name:'车门分装线'},
    {node_gid:'local-process',node_type:'process',parent_gid:'local-line',source_bop_node_gid:'bop-process'},
  ] };
  assert.deepEqual(resolveHierarchyCaptureSource(hierarchy,'local-process'),{
    workspace_gid:'workspace',hierarchy_gid:'hierarchy',version_gid:'version',line_gid:'bop-line',name:'车门分装线',
  });
  assert.equal(resolveHierarchyCaptureSource(hierarchy,'missing'),null);
  assert.equal(resolveHierarchyCaptureSource({...hierarchy,source_bop_version_gid:null},'local-line'),null);
  hierarchy.nodes[0].source_bop_node_gid=null;
  assert.equal(resolveHierarchyCaptureSource(hierarchy,'local-process'),null);
});

test('execution source uses the authoritative published structure hash, not the alternate projection hash', async () => {
  const source={version_gid:'version',line_gid:'bop-line'};
  const contentHash='sha256:'+'a'.repeat(64);
  const structure={official:true,source:{bop_version_gid:'version',revision:2},content_hash:contentHash,nodes:[{node_id:'bop-line',kind:'line_process'}]};
  const calls=[];
  const result=await readCaptureExecutionSource(async(id,payload)=>{calls.push({id,payload});return structure;},source);
  assert.deepEqual(result,{version_gid:'version',revision:2,content_hash:contentHash});
  assert.deepEqual(calls,[{id:'craft.bop.execution_structure.get',payload:{version_gid:'version'}}]);
  for(const changed of [{official:false},{source:{bop_version_gid:'other',revision:2}},{nodes:[]},{content_hash:null}]) {
    await assert.rejects(readCaptureExecutionSource(async()=>({...structure,...changed}),source),/capture_execution_source_mismatch/);
  }
});

test('unpublished execution source fails without any snapshot or write fallback', async () => {
  const calls=[];
  await assert.rejects(readCaptureExecutionSource(async id=>{calls.push(id);throw Error('version_not_published');},
    {version_gid:'version',line_gid:'line'}),/version_not_published/);
  assert.deepEqual(calls,['craft.bop.execution_structure.get']);
});

test('capture resolves a station or operation to its owning line and rejects cycles', () => {
  const entries = {
    line: { gid: 'line', node_type: 'line_process' },
    station: { gid: 'station', node_type: 'station_process', parent_gid: 'line' },
    operation: { gid: 'operation', node_type: 'operation', parent_gid: 'station' },
  };
  assert.equal(resolveCaptureLine(entries, 'operation'), 'line');
  assert.equal(resolveCaptureLine(entries, 'line'), 'line');
  assert.equal(resolveCaptureLine(entries, { type: 'click' }), null);
  assert.equal(resolveCaptureLine(entries, 'missing'), null);
  entries.station.parent_gid = 'operation';
  assert.equal(resolveCaptureLine(entries, 'operation'), null);
});

test('changing environment invalidates the old device preflight and materialization', () => {
  const workflow = createCaptureWorkflow({ invoke: async () => ({}) });
  workflow.setEnvironment('first', 1);
  workflow.state.materializationRun = { run_id: 'old', status: 'completed' };
  workflow.state.captureRun = { capture_run_id: 'old-capture', status: 'completed' };
  workflow.state.preflight = { compatible: true };
  workflow.setEnvironment('second', 1);
  assert.equal(workflow.state.materializationRun, null);
  assert.equal(workflow.state.captureRun, null);
  assert.equal(workflow.canStartCapture(), false);
});

test('running capture cannot be replaced with another environment or duplicated', async () => {
  const workflow = createCaptureWorkflow({ invoke: async () => { throw Error('must not invoke'); } });
  workflow.setEnvironment('env', 1);
  workflow.state.deviceId = 'device';
  workflow.state.preflight = { compatible: true };
  workflow.state.captureRun = { capture_run_id: 'run', status: 'running' };
  assert.equal(workflow.canStartCapture(), false);
  assert.throws(() => workflow.setEnvironment('other', 1), /capture_run_active/);
  await assert.rejects(workflow.startCapture(), /capture_run_active/);
});

test('double click during materialization starts only one confirmed request', async () => {
  let release;
  let starts = 0;
  const pending = new Promise(resolve => { release = resolve; });
  const workflow = createCaptureWorkflow({ invoke: async id => {
    if (id === 'simulation.environment.preflight') return { compatible: true };
    if (id === 'simulation.environment.materialize') { starts++; return pending; }
    if (id === 'simulation.materialization_run.action.get') return { action: null };
    throw Error(id);
  }});
  workflow.setEnvironment('env', 1);
  await workflow.selectConnector('device');
  const first = workflow.startCapture();
  const second = workflow.startCapture();
  const rejected = assert.rejects(second, /capture_run_active/);
  release({ run_id: 'materialize', status: 'queued' });
  await first;
  await rejected;
  assert.equal(starts, 1);
  assert.equal(workflow.state.busy, false);
});
