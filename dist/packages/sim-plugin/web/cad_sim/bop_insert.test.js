const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const { JSDOM } = require('jsdom');

async function setup() {
  const dom = new JSDOM(`<div id="bopInsertOverlay" class="hidden"><form id="bopInsertForm">
    <select id="bopInsertVersion"></select><select id="bopInsertLine"></select>
    <input id="bopInsertDepth" value="all"><input id="bopInsertName" value="BOP">
    <div id="bopInsertSummary"></div><div id="bopInsertError"></div>
    <button id="bopInsertSubmit"></button><button id="bopInsertCancel"></button></form></div>`, {runScripts:'outside-only'});
  const c = dom.getInternalVMContext();
  vm.runInContext(fs.readFileSync(path.join(__dirname, 'cad_sim.js'), 'utf8'), c);
  vm.runInContext(`document.removeEventListener('DOMContentLoaded', init);
    _bopVersions=[{version_gid:'20',name:'BOP'}];
    window.calls=[]; window.latest=9;
    window._simulationEnvironmentWorkspace={store:{state:{workspace:{workspace_gid:'10',row_version:3}},openWorkspace:async()=>{}}};
    _refreshAlternateHierarchies=async()=>{};_cmdShow=()=>{};
    _invokeCapability=async(id,payload,options)=>{calls.push({id,payload,options});
      if(id.endsWith('workspace.get')) {if(window.pendingRead)await window.pendingRead;return {workspace_gid:'10',row_version:latest};}
      if(window.failure)throw Error(window.failure);
      if(id.endsWith('.preview'))return {plan_hash:'hash',node_count:2,model_reference_count:0,resource_reference_count:0,source_revision:1};
      return {hierarchy_gid:'30'};
    };`, c);
  await vm.runInContext('_openBopInsert()', c);
  dom.window.document.getElementById('bopInsertVersion').value='20';
  return {dom,c,submit:()=>dom.window.document.getElementById('bopInsertForm').onsubmit({preventDefault(){}})};
}

test('preview reads authoritative version without replacing cached workspace; apply uses exactly previewed version', async()=>{
  const {dom,submit}=await setup();try {
    await submit();
    const preview=dom.window.calls.find(x=>x.id.endsWith('.preview'));
    assert.equal(preview.payload.expected_row_version,9);
    assert.equal(preview.options.expectedResourceVersion,9);
    assert.equal(dom.window._simulationEnvironmentWorkspace.store.state.workspace.row_version,3);
    dom.window._simulationEnvironmentWorkspace.store.state.workspace={workspace_gid:'10',row_version:11};
    await submit();
    const apply=dom.window.calls.find(x=>x.id.endsWith('.apply'));
    assert.equal(apply.payload.expected_row_version,9);
    assert.equal(apply.payload.plan_hash,'hash');
  }finally{dom.window.close();}
});

for(const failure of ['version_conflict','bop_projection_plan_changed'])test(`${failure} invalidates preview and next click only regenerates it`,async()=>{
  const {dom,submit}=await setup();try{
    await submit();dom.window.failure=failure;await submit();
    assert.equal(dom.window.document.getElementById('bopInsertSubmit').textContent,'生成预览');
    assert.match(dom.window.document.getElementById('bopInsertError').textContent,/重新.*预览/);
    dom.window.failure=null;dom.window.latest=12;await submit();
    assert.equal(dom.window.calls.filter(x=>x.id.endsWith('.apply')).length,1);
    assert.equal(dom.window.calls.filter(x=>x.id.endsWith('.preview')).at(-1).payload.expected_row_version,12);
  }finally{dom.window.close();}
});

test('switching environments while dialog is open cannot insert into the old environment',async()=>{
  const {dom,submit}=await setup();try{
    await submit();dom.window._simulationEnvironmentWorkspace.store.state.workspace={workspace_gid:'99',row_version:1};await submit();
    assert.equal(dom.window.calls.filter(x=>x.id.endsWith('.apply')).length,0);
    assert.match(dom.window.document.getElementById('bopInsertError').textContent,/环境.*切换/);
  }finally{dom.window.close();}
});

test('late workspace read after environment switch cannot generate a preview',async()=>{
  const {dom,submit}=await setup();try{
    let finish;dom.window.pendingRead=new Promise(resolve=>{finish=resolve;});const pending=submit();
    dom.window._simulationEnvironmentWorkspace.store.state.workspace={workspace_gid:'99',row_version:1};finish();await pending;
    assert.equal(dom.window.calls.filter(x=>x.id.endsWith('.preview')).length,0);
  }finally{dom.window.close();}
});

test('reopening while apply is pending retains the operation and clearly shows progress',async()=>{
  const {dom,c,submit}=await setup();try{
    await submit();
    let finish;dom.window.pendingApply=new Promise(resolve=>{finish=resolve;});
    vm.runInContext(`const originalInvoke=_invokeCapability;_invokeCapability=async(...args)=>{if(args[0].endsWith('.apply'))await window.pendingApply;return originalInvoke(...args);};`,c);
    const pending=submit();
    assert.match(dom.window.document.getElementById('bopInsertSubmit').textContent,/正在插入/);
    dom.window.document.getElementById('bopInsertCancel').click();
    await vm.runInContext('_openBopInsert()',c);
    assert.match(dom.window.document.getElementById('bopInsertSubmit').textContent,/正在插入/);
    assert.equal(dom.window.document.getElementById('bopInsertVersion').value,'20');
    assert.equal(dom.window.document.getElementById('bopInsertVersion').disabled,true);
    finish();await pending;
    assert.equal(dom.window.document.getElementById('bopInsertSubmit').disabled,false);
    assert.equal(dom.window.calls.filter(x=>x.id.endsWith('.apply')).length,1);
  }finally{dom.window.close();}
});

test('building visibility controls evaluates each new control once, not all earlier controls',async()=>{
  const {dom,c}=await setup();try{
    vm.runInContext(`window.evaluations=0;_alternateVisibilityState=()=>{evaluations++;return {keys:[],state:{checked:false,indeterminate:false,disabled:true}};};
      for(let i=0;i<200;i++)_wireAlternateVisibilityCheck(document.createElement('input'),{children:[]});`,c);
    assert.equal(dom.window.evaluations,200);
  }finally{dom.window.close();}
});

test('BOP nodes create child DOM only when expanded',async()=>{
  const {dom,c}=await setup();try{
    vm.runInContext(`_alternateVisibilityState=()=>({keys:[],state:{checked:false,disabled:true}});
      window.root=_buildAlternateTreeItem({kind:'node',node_gid:'1',children:[{kind:'node',node_gid:'2',children:[{kind:'node',node_gid:'3',children:[]}]}]},{hierarchy_gid:'10'});document.body.append(root);`,c);
    assert.equal(dom.window.root.querySelectorAll('.cs-alternate-tree-item').length,0);
    dom.window.root.querySelector('.cs-alternate-tree-toggle').click();
    assert.equal(dom.window.root.querySelectorAll('.cs-alternate-tree-item').length,1);
    dom.window.root.querySelector('.cs-alternate-tree-toggle').click();
    dom.window.root.querySelector('.cs-alternate-tree-toggle').click();
    assert.equal(dom.window.root.querySelectorAll('.cs-alternate-tree-item').length,1);
  }finally{dom.window.close();}
});
