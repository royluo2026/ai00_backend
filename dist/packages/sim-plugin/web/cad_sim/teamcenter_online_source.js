(function (global) {
  'use strict';
  const resultOf = outcome => outcome?.steps?.at(-1)?.result;
  const controlKey = node => {
    const path=node?.occurrence_path;
    const occurrenceUid=Array.isArray(path)&&path.length ? path[path.length-1]?.occurrence_uid : '';
    return typeof occurrenceUid==='string'&&occurrenceUid ? `tc:${occurrenceUid}` : null;
  };
  const hydrateControlKeys = tree => {
    for(const node of tree?.nodes||[])node.control_key=controlKey(node);
    return tree;
  };
  const productNode = node => ({
    node_key: `tc:${node.occurrence_id}`, occurrence_id: node.occurrence_id,
    control_key: controlKey(node),
    parent_key: node.parent_occurrence_id == null ? null : `tc:${node.parent_occurrence_id}`, depth: node.depth, child_order: node.child_order,
    occurrence_path: node.occurrence_path, has_children: node.has_children,
    name: node.name, item_uid: node.item_uid, item_id: node.item_id,
    item_revision_uid: node.item_revision_uid, revision: node.revision_id,
    component_type: node.component_type, owning_user: node.owning_user,
    owning_group: node.owning_group, transform: node.transform, bbox: node.bbox,
    absolute_transform: node.absolute_transform, transform_unit: node.transform_unit,
    transform_convention: node.transform_convention, bbox_unit: node.bbox_unit,
    torque_raw: node.torque_raw, torque_importance: node.torque_importance,
    catia_occurrence_name: node.catia_occurrence_name, catia_file_name: node.catia_file_name,
    vpps: node.vpps, vpps_desc: node.vpps_desc, catia_parent_part_name: node.catia_parent_part_name,
    parent_name: node.parent_name, parent_vpps: node.parent_vpps, parent_vpps_name: node.parent_vpps_name,
    weight_raw: node.weight_raw, unit_weight_raw: node.unit_weight_raw,
    geometry_refs: node.geometry_refs || [], visible: null,
  });

  const pendingReads = new WeakMap();
  const trace=(stage,detail)=>{try{global._simulationDebug?.(stage,detail);}catch{}};
  function partialTree() {
    return {state:'ready',source:'teamcenter_children',complete:false,node_count:0,nodes:[],pages:{}};
  }
  function readChildren(requestConnector, document, tree, parentPath = [], {more=false,refresh=false,isCurrent=()=>true} = {}) {
    hydrateControlKeys(tree);
    const key=JSON.stringify(parentPath), old=tree.pages[key];
    let pending=pendingReads.get(tree);
    if(!pending){pending=new Map();pendingReads.set(tree,pending);}
    if(pending.has(key)){trace('tc_page_shared',{document_gid:document.document_gid,depth:parentPath.length});return pending.get(key).promise;}
    const cursor=more ? old?.next_cursor : 0;
    if(more && cursor==null)return Promise.resolve();
    const request={valid:true,promise:null};
    const started=Date.now(),trace_id=global.crypto?.randomUUID?.();
    const report=(stage,detail={})=>trace(stage,{trace_id,document_gid:document.document_gid,depth:parentPath.length,cursor,force_refresh:refresh,elapsed_ms:Date.now()-started,...detail});
    report('tc_page_started',{capability_id:'simulation.teamcenter.product_structure.children.read.request',capability_version:1});
    pending.set(key,request);
    const current=()=>request.valid&&isCurrent();
    tree.pages[key]={...old,state:'loading',error:null};
    const task=(async()=>{
      try {
        const page=resultOf(await requestConnector('simulation.teamcenter.product_structure.children.read.request',{
          source_selector:document.source_selector,parent_path:parentPath,cursor,page_size:200,
          refresh:!more&&refresh,generation:more?old.generation:null,
        },{confirmation:false,waitAttempts:750}));
        if(!current()){report('tc_page_stale');return;}
        // Online registration stores the selector digest in content_sha256;
        // source_identity_hash identifies this insertion (selector + insertion ID).
        // Do not compare that insertion identity with a Connector source page.
        const sourceHash=document.source_kind==='teamcenter_online'&&document.content_sha256
          ? document.content_sha256 : document.source_identity_hash;
        const checks={parent:!!page?.parent,nodes:Array.isArray(page?.nodes),cursor:page?.cursor===cursor,complete:page?.complete===false,
          generation:/^[a-f0-9]{32}$/.test(page?.generation),parent_path:JSON.stringify(page?.parent?.occurrence_path)===key,
          source_identity:!sourceHash||page?.source_identity_hash===sourceHash,pinned_generation:!more||page?.generation===old.generation};
        if(Object.values(checks).some(value=>!value)){report('tc_page_rejected',{reason:Object.keys(checks).filter(key=>!checks[key]).join(','),error_code:'teamcenter_children_page_invalid'});throw Error('teamcenter_children_page_invalid');}
        report('tc_page_validated',{generation:page.generation,node_count:page.nodes.length,cache_hit:page.cache_hit,next_cursor:page.next_cursor});
        const parent=productNode(page.parent);
        // A new generation replaces the requested subtree, including previously loaded descendants.
        const retainGeneration=!more&&!refresh&&page.cache_hit&&old?.generation===page.generation&&!old.restart_required;
        if(!more&&!retainGeneration){
          const removed=new Set([parent.node_key]);
          let changed=true;
          while(changed){changed=false;for(const node of tree.nodes)if(removed.has(node.parent_key)&&!removed.has(node.node_key)){removed.add(node.node_key);changed=true;}}
          tree.nodes=tree.nodes.filter(node=>!removed.has(node.node_key));
          const descendant=pageKey=>{const path=JSON.parse(pageKey);return path.length>parentPath.length&&JSON.stringify(path.slice(0,parentPath.length))===key;};
          for(const pageKey of Object.keys(tree.pages))if(descendant(pageKey))delete tree.pages[pageKey];
          for(const [pageKey,inflight] of pending)if(descendant(pageKey)){inflight.valid=false;pending.delete(pageKey);}
        }
        const nodes=new Map(tree.nodes.map(node=>[node.node_key,node]));
        for(const node of [parent,...page.nodes.map(productNode)])nodes.set(node.node_key,node);
        tree.nodes=[...nodes.values()];tree.node_count=tree.nodes.length;
        tree.pages[key]={state:'loaded',generation:page.generation,next_cursor:retainGeneration?old.next_cursor:page.next_cursor,child_count:page.child_count,captured_at:page.captured_at,cache_hit:page.cache_hit};
        report('tc_page_applied',{generation:page.generation,node_count:tree.node_count,cache_hit:page.cache_hit,next_cursor:tree.pages[key].next_cursor,reason:retainGeneration?'retained_generation':more?'appended_page':'replaced_subtree'});
      } catch(error) {
        report('tc_page_failed',{capability_id:'simulation.teamcenter.product_structure.children.read.request',capability_version:1,error_code:error?.message||'teamcenter_children_unavailable'});
        if(current())tree.pages[key]={...old,state:'failed',error:error?.message||'teamcenter_children_unavailable',
          restart_required:old?.restart_required||/teamcenter_children_generation_stale/.test(error?.message||'')};
        throw error;
      } finally {if(pending.get(key)===request)pending.delete(key);}
    })();
    request.promise=task;return task;
  }

  async function bindSource({invoke,workspace,source}) {
    return invoke('simulation.environment.online_source.bind',{
      workspace_gid:workspace.workspace_gid,expected_row_version:workspace.row_version,
      display_name:source.display_name,insertion_instance_id:source.insertion_instance_id,source_selector:source.source_selector,
    },{idempotency:true,idempotencyKey:`tc-source-${source.insertion_instance_id}`});
  }

  async function refreshAncestor(requestConnector,document,tree,path,isCurrent) {
    for(let depth=Math.max(0,path.length-1);depth>=0;depth--){
      if(!isCurrent())return false;
      const ancestor=path.slice(0,depth),key=JSON.stringify(ancestor),pending=pendingReads.get(tree);
      // Do not mistake a shared in-flight "load more" for the requested refresh.
      while(pending?.has(key)&&isCurrent())await pending.get(key).promise.catch(()=>{});
      if(!isCurrent())return false;
      try{await readChildren(requestConnector,document,tree,ancestor,{refresh:true,isCurrent});return isCurrent();}
      catch(error){if(error.message!=='teamcenter_parent_path_not_found'||depth===0)throw error;}
    }
    return false;
  }

  async function readSnapshot(invoke, observationId, pageSize = 1000) {
    const nodes = []; let cursor = 0; let total = 0;
    do {
      const page = await invoke('simulation.product_structure.snapshot.page.get', {
        observation_id: observationId, cursor, page_size: pageSize,
      });
      total = page.node_count; nodes.push(...page.nodes.map(productNode));
      cursor = page.next_cursor;
    } while (cursor !== null);
    return { state: 'ready', source: 'teamcenter_snapshot', observation_id: observationId,
      node_count: total, complete: nodes.length === total, nodes };
  }

  async function observeAndPersist({ invoke, requestConnector, workspace, source, progress = () => {} }) {
    const binding = await invoke('simulation.environment.online_source.bind', {
      workspace_gid: workspace.workspace_gid, expected_row_version: workspace.row_version,
      display_name: source.display_name, insertion_instance_id: source.insertion_instance_id,
      source_selector: source.source_selector,
    }, { idempotency: true, idempotencyKey: `tc-source-${source.insertion_instance_id}` });
    progress('observing', 0, 0);
    const outcome = await requestConnector('simulation.teamcenter.product_structure.observe.request', {
      source_selector: source.source_selector, max_nodes: 250000, max_depth: 128,
      property_projection: 'simulation-default-v1',
    }, { confirmation: false, waitAttempts: 7500 });
    const manifest = resultOf(outcome);
    if (!manifest?.complete || !manifest.observation_id) throw new Error('teamcenter_observation_incomplete');
    if (binding.source_identity_hash && manifest.source_identity_hash !== binding.source_identity_hash)
      throw new Error('teamcenter_source_identity_mismatch');
    const begun = await invoke('simulation.product_structure.observation.begin', {
      workspace_gid: workspace.workspace_gid, source_gid: binding.source_gid,
      observation_id: manifest.observation_id, captured_at: manifest.captured_at,
      node_count: manifest.node_count, page_count: manifest.page_count,
    }, { idempotency: true, idempotencyKey: `tc-observe-${manifest.observation_id}` });
    let cursor = 0, pageIndex = 0;
    while (cursor !== null) {
      const pageOutcome = await requestConnector('simulation.teamcenter.product_structure.page.read.request', {
        observation_id: manifest.observation_id, cursor, page_size: 1000,
      }, { confirmation: false, waitAttempts: 750 });
      const page = resultOf(pageOutcome);
      if (!page || page.cursor !== cursor) throw new Error('teamcenter_observation_page_invalid');
      await invoke('simulation.product_structure.observation.page.append', {
        observation_gid: begun.observation_gid, page_index: pageIndex,
        cursor: page.cursor, next_cursor: page.next_cursor, nodes: page.nodes,
      }, { idempotency: true, idempotencyKey: `tc-page-${manifest.observation_id}-${pageIndex}` });
      progress('persisting', Math.min(manifest.node_count, cursor + page.nodes.length), manifest.node_count);
      cursor = page.next_cursor; pageIndex += 1;
      await new Promise(resolve => setTimeout(resolve, 0));
    }
    await invoke('simulation.product_structure.observation.publish', { observation_gid: begun.observation_gid },
      { idempotency: true, idempotencyKey: `tc-publish-${manifest.observation_id}` });
    progress('complete', manifest.node_count, manifest.node_count);
    return { ...binding, ...manifest };
  }

  async function openOnline(requestConnector, document, mode = 'new', cacheSource = null) {
    if (!cacheSource && !document?.source_selector) throw new Error('teamcenter_source_selector_missing');
    if (cacheSource && (!/^[a-f0-9]{32}$/.test(cacheSource.batch_id || '')
        || typeof cacheSource.node_key !== 'string' || !cacheSource.node_key))
      throw new Error('teamcenter_cache_source_missing');
    const capability = mode === 'new' ? 'simulation.teamcenter.visualization.launch.request'
      : mode === 'insert' ? 'simulation.teamcenter.visualization.insert.request' : null;
    if (!capability) throw new Error('teamcenter_visualization_action_invalid');
    return requestConnector(capability, {
      ...(cacheSource ? {cache_source:cacheSource} : {source_selector:document.source_selector}),
      expected_visdoc_uid: '',
    }, { confirmation: true, waitAttempts: 1000,
      ...(cacheSource ? {version:mode==='new'?3:2} : {}) });
  }

  async function search(requestConnector, query) {
    const outcome = await requestConnector('simulation.teamcenter.product.search.request', query,
      { confirmation: false, waitAttempts: 750 });
    const result = resultOf(outcome);
    if (!result || !Array.isArray(result.items)) throw new Error('teamcenter_search_result_invalid');
    return result.items;
  }

  async function readNodeProperties(requestConnector, document, node) {
    if (!document?.source_selector || !Array.isArray(node?.occurrence_path))
      throw new Error('teamcenter_node_properties_input_invalid');
    const outcome = await requestConnector(
      'simulation.teamcenter.node_properties.read.request',
      { source_selector: document.source_selector, occurrence_path: node.occurrence_path },
      { confirmation: false, waitAttempts: 750 },
    );
    const result = resultOf(outcome);
    if (!result || !result.properties || typeof result.properties !== 'object'
        || typeof result.cache_hit !== 'boolean')
      throw new Error('teamcenter_node_properties_invalid');
    return result;
  }

  let revisionRulesCache = null;
  let revisionRulesPending = null;
  let revisionRulesGeneration = 0;

  function cachedRevisionRules() {
    return revisionRulesCache ? [...revisionRulesCache] : null;
  }

  function clearRevisionRules() {
    revisionRulesGeneration += 1;
    revisionRulesCache = null;
    revisionRulesPending = null;
  }

  async function revisionRules(requestConnector) {
    if (revisionRulesCache) return [...revisionRulesCache];
    if (!revisionRulesPending) {
      const generation = revisionRulesGeneration;
      revisionRulesPending = (async () => {
        const outcome = await requestConnector('simulation.teamcenter.revision_rule.search.request',
          { endpoint_id: 'tc-production' }, { confirmation: false, waitAttempts: 750 });
        const result = resultOf(outcome);
        if (!result || !Array.isArray(result.rules) || !result.rules.length)
          throw new Error('teamcenter_revision_rules_unavailable');
        const rules = [...result.rules];
        if (revisionRulesGeneration === generation) revisionRulesCache = Object.freeze(rules);
        return rules;
      })();
    }
    const pending = revisionRulesPending;
    try { return [...await pending]; }
    finally { if (revisionRulesPending === pending) revisionRulesPending = null; }
  }

  global.AI00TeamcenterOnlineSource = Object.freeze({
    launchOnline: (requestConnector, document) => openOnline(requestConnector, document, 'new'),
    bindSource, cachedRevisionRules, clearRevisionRules, partialTree, hydrateControlKeys, readChildren, refreshAncestor, readNodeProperties, observeAndPersist, openOnline, productNode, readSnapshot, resultOf, revisionRules, search,
    searchExact: search,
  });
})(typeof window !== 'undefined' ? window : globalThis);
