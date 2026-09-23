const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {JSDOM}=require('jsdom');
const tick=()=>new Promise(resolve=>setImmediate(resolve));

function setup(){
  const dom=new JSDOM(`
    <div id="modelDocumentList"></div>
    <div id="csDetailPanel"><button id="dpClose"></button><span id="dpHandleLabel"></span><span id="dpSourceTag"></span><span id="dpTitle"></span>
      <div id="dpPlaceholder"></div><div id="dpBopContent"></div>
      <div id="dpVisContent" class="hidden"><div id="dpVisLeft"></div><div id="dpVisRight"></div></div>
    </div>`,{runScripts:'outside-only'});
  for(const file of ['model_document_collection.js','teamcenter_online_source.js','cad_sim.js'])
    vm.runInContext(fs.readFileSync(path.join(__dirname,file),'utf8'),dom.getInternalVMContext());
  vm.runInContext(`
    _modelDocumentCollection=window.AI00ModelDocumentCollection.createCollection();
    window.__requests=[];window.__loginCount=0;
    window.__document={document_gid:'2',role:'primary',media_type:'application/vnd.siemens.teamcenter.visualization-document',source_kind:'teamcenter_online',source_selector:{endpoint_id:'tc-production',object_uid:'obj',item_revision_uid:'root-rev',bom_view_uid:'',revision_rule:'Latest Working',configuration_date:'2026-09-17T00:00:00Z'},product_tree:{source:'teamcenter_children',pages:{},nodes:[]}};
    _modelDocumentCollection.replace([window.__document]);
    _requestVisMockupCommand=(id,payload)=>new Promise((resolve,reject)=>window.__requests.push({id,payload,resolve,reject}));
    _requireTeamcenterLogin=async()=>{window.__loginCount++;return {state:'ready'};};
    window.__node=(key,name,itemId,path)=>({node_key:key,name,item_id:itemId,revision:'00;1',component_type:'Part',occurrence_path:path,children:[],has_children:false});
    window.__append=node=>{const row=_buildProductTreeItem(node,'2');document.body.append(row);return row;};
    window.__outcome=(name,cacheHit,extra={})=>({steps:[{result:{source_identity_hash:'sha256:'+ 'a'.repeat(64),captured_at:'2026-09-17T00:00:00Z',cache_hit:cacheHit,properties:{name,item_id:null,revision_id:'00;1',component_type:'Part',owning_user:'owner',owning_group:null,weight_raw:'12.5',unit_weight_raw:null,torque_raw:'9',torque_importance:null,occurrence_uid:'occ',...extra}}}]});
  `,dom.getInternalVMContext());
  return dom;
}

test('click opens Teamcenter detail immediately, orders fields, hides empty values and labels cache source',async()=>{
  const dom=setup(),d=dom.window.document;
  const row=dom.window.__append(dom.window.__node('tc:first','First','W10-ENG00001',[{occurrence_uid:'occ',item_revision_uid:'rev'}]));
  row.querySelector('.cs-alternate-tree-name').click();
  assert.ok(d.getElementById('csDetailPanel').classList.contains('open'));
  assert.match(d.getElementById('dpVisRight').textContent,/First/);
  assert.match(d.getElementById('dpVisRight').textContent,/W10-ENG00001/);
  assert.match(d.getElementById('dpVisRight').textContent,/读取中/);
  dom.window.__requests[0].resolve(dom.window.__outcome('First full',true));await tick();
  const text=d.getElementById('dpVisRight').textContent;
  for(const label of ['名称','版本','对象类型','所有者','重量','扭矩','实例 UID'])assert.match(text,new RegExp(label));
  assert.doesNotMatch(text,/所属组|单位重量|扭矩重要度/);
  assert.ok(text.indexOf('名称')<text.indexOf('版本')&&text.indexOf('版本')<text.indexOf('对象类型'));
  assert.equal(d.getElementById('dpSourceTag').textContent,'本地缓存');
  dom.window.close();
});

test('late property response cannot replace a newer node selection',async()=>{
  const dom=setup(),d=dom.window.document;
  const first=dom.window.__append(dom.window.__node('tc:first','First','A',[{occurrence_uid:'one',item_revision_uid:'r1'}]));
  const second=dom.window.__append(dom.window.__node('tc:second','Second','B',[{occurrence_uid:'two',item_revision_uid:'r2'}]));
  first.querySelector('.cs-alternate-tree-name').click();
  second.querySelector('.cs-alternate-tree-name').click();
  dom.window.__requests[1].resolve(dom.window.__outcome('Second full',false));await tick();
  dom.window.__requests[0].resolve(dom.window.__outcome('First stale',true));await tick();
  assert.match(d.getElementById('dpVisRight').textContent,/Second full/);
  assert.doesNotMatch(d.getElementById('dpVisRight').textContent,/First stale/);
  assert.equal(d.getElementById('dpSourceTag').textContent,'Teamcenter');
  dom.window.close();
});

test('late Teamcenter response cannot reopen a closed panel or overwrite VM detail',async()=>{
  const dom=setup(),d=dom.window.document;
  vm.runInContext('_initDetailPanel()',dom.getInternalVMContext());
  const row=dom.window.__append(dom.window.__node('tc:first','First','A',[{occurrence_uid:'one',item_revision_uid:'r1'}]));
  row.querySelector('.cs-alternate-tree-name').click();
  vm.runInContext("_showVisDetail({key:'vm-1',name:'VM current'})",dom.getInternalVMContext());
  dom.window.__requests[0].resolve(dom.window.__outcome('First stale',true));await tick();
  assert.equal(d.getElementById('dpTitle').textContent,'VM current');
  d.getElementById('dpClose').click();
  assert.equal(d.getElementById('csDetailPanel').classList.contains('open'),false);
  assert.doesNotMatch(d.getElementById('dpVisRight').textContent,/First stale/);
  dom.window.close();
});

test('failed read keeps basics and retries after Teamcenter login',async()=>{
  const dom=setup(),d=dom.window.document;
  const row=dom.window.__append(dom.window.__node('tc:first','First','W10-ENG00001',[{occurrence_uid:'occ',item_revision_uid:'rev'}]));
  row.querySelector('.cs-alternate-tree-name').click();
  dom.window.__requests[0].reject(Error('teamcenter_login_required'));await tick();
  assert.match(d.getElementById('dpVisRight').textContent,/First/);
  const retry=d.querySelector('[data-teamcenter-detail-retry]');assert.ok(retry);retry.click();await tick();
  assert.equal(dom.window.__loginCount,1);assert.equal(dom.window.__requests.length,2);
  dom.window.__requests[1].resolve(dom.window.__outcome('Retried',false));await tick();
  assert.match(d.getElementById('dpVisRight').textContent,/Retried/);
  dom.window.close();
});

test('old cached node refreshes its parent before reading Teamcenter properties',async()=>{
  const dom=setup(),d=dom.window.document;
  vm.runInContext(`
    const currentDocument=_modelDocumentCollection.state.documents[0];
    const rawParent={occurrence_id:'root',parent_occurrence_id:null,occurrence_path:[],has_children:true,name:'Root',depth:0,child_order:0};
    const rawChild={occurrence_id:'child',parent_occurrence_id:'root',occurrence_path:[{occurrence_uid:'occ',item_revision_uid:'rev'}],has_children:false,name:'Old cached',item_id:'W10-OLD',depth:1,child_order:0};
    const parent=window.AI00TeamcenterOnlineSource.productNode(rawParent);
    const stale=window.AI00TeamcenterOnlineSource.productNode(rawChild);
    delete stale.occurrence_path;
    stale.control_key='tc:sha256:old';
    currentDocument.product_tree.nodes=[parent,stale];
    window.__refreshCount=0;
    _requestVisMockupCommand=(id,payload)=>{
      if(id.endsWith('children.read.request')){
        __refreshCount++;
        if(JSON.stringify(payload.parent_path)!=='[]'||payload.refresh!==true)throw Error('unexpected_refresh');
        return Promise.resolve({steps:[{result:{parent:rawParent,nodes:[rawChild],cursor:0,next_cursor:null,child_count:1,complete:false,generation:'a'.repeat(32),source_identity_hash:'source',captured_at:'2026-09-18T00:00:00Z',cache_hit:false}}]});
      }
      return new Promise((resolve,reject)=>window.__requests.push({id,payload,resolve,reject}));
    };
  `,dom.getInternalVMContext());
  vm.runInContext(`window.__detailPromise=_selectTeamcenterNodeDetail(
    _modelDocumentCollection.state.documents[0],
    _modelDocumentCollection.state.documents[0].product_tree.nodes[1]);`,dom.getInternalVMContext());
  await tick();
  assert.equal(dom.window.__refreshCount,1);
  assert.equal(dom.window.__requests.length,1);
  assert.deepEqual(JSON.parse(JSON.stringify(dom.window.__requests[0].payload.occurrence_path)),[{occurrence_uid:'occ',item_revision_uid:'rev'}]);
  dom.window.__requests[0].resolve(dom.window.__outcome('Recovered detail',false));await tick();
  await dom.window.__detailPromise;
  assert.match(d.getElementById('dpVisRight').textContent,/Recovered detail/);
  dom.window.close();
});
