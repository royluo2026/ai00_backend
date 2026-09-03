/**
 * web/ext_datasource/ext_ds.js
 * 外部数据源 — 三栏布局：连接列表 | 映射列表 | 字段映射 + 预览
 */
'use strict';

const _cf = (method, path, opts = {}) => {
  const fn = window.top?._cloudFetch || window.parent?._cloudFetch || window._cloudFetch;
  if (!fn) throw new TypeError('_cloudFetch 未就绪');
  return fn(path, { ...opts, method });
};
async function _invokeCapability(id, payload = {}) {
  const response = await _cf('POST', `/api/v1/capabilities/${id}:invoke`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ version: 1, payload }),
  });
  const envelope = response?.data;
  if (response?.success !== true || envelope?.ok !== true) {
    const detail = envelope?.error || response?.error || {};
    throw new Error(detail.message || `能力调用失败：${id}@1`);
  }
  const value = envelope.data;
  return value?.data !== undefined && Object.keys(value).length === 1 ? value.data : value;
}
function _connectorCapabilityClient() {
  const client = window.top?.AI00ExistingCapabilityClient
    || window.parent?.AI00ExistingCapabilityClient
    || window.AI00ExistingCapabilityClient;
  if (!client?.invoke) throw new TypeError('Capability 客户端未就绪');
  return client;
}
function _connectorIdempotencyKey(capabilityId) {
  const nonce = globalThis.crypto?.randomUUID?.()
    || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${capabilityId}:${nonce}`;
}
async function _invokeConnectorCapability(
  capabilityId, payload, { write = false, confirmation = '', idempotencyKey = '' } = {}
) {
  if (!write) return _connectorCapabilityClient().invoke(capabilityId, payload);
  if (!window.confirm(confirmation)) {
    const error = new Error('操作已取消');
    error.code = 'capability_confirmation_cancelled';
    throw error;
  }
  idempotencyKey = idempotencyKey || _connectorIdempotencyKey(capabilityId);
  return _connectorCapabilityClient().invoke(
    capabilityId,
    { ...payload, idempotency_key: idempotencyKey },
    { write: true, idempotencyKey, confirmed: true },
  );
}
function _operationMessage(operationRef, labels) {
  const status = operationRef?.status;
  if (status === 'accepted') return { kind: 'pending', text: `${labels.subject}已受理，正在等待执行` };
  if (status === 'outcome_unknown') return { kind: 'pending', text: `${labels.subject}结果未知，正在协调确认` };
  if (status === 'failed') return { kind: 'failed', text: `${labels.subject}执行失败` };
  if (status === 'succeeded') return { kind: 'succeeded', text: '' };
  return { kind: 'failed', text: `${labels.subject}返回了未知状态` };
}
async function _listOntologyObjects(kinds) {
  const items = [];
  let offset = 0;
  let total = 0;
  do {
    const page = await _invokeCapability('ontology.object.list', { kinds, limit: 100, offset });
    const rows = page?.items || [];
    items.push(...rows);
    total = Number(page?.total || items.length);
    offset += rows.length;
    if (!rows.length) break;
  } while (offset < total);
  return items.map(item => ({ ...item, gid: item.gid || item.stable_gid }));
}
const _esc = s => String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const _gid = () => Math.random().toString(36).slice(2);

// ── 状态 ──────────────────────────────────────────────────────────────────────
let _datasources  = [];
let _mappings     = [];
let _fieldMaps    = [];
let _ontoClasses  = [];
let _ontoProps    = [];
let _extColumns   = [];   // 当前映射的外部表列
let _previewData  = [];
let _selectedDs   = null;
let _selectedMap  = null;
let _infoStats    = {};
let _dirty        = false; // 字段映射有未保存改动
const _importIdempotencyStorageKey = mappingGid => `ai00:integration:import-idempotency:${mappingGid}`;
function _importIdempotencyKey(mappingGid) {
  const storageKey = _importIdempotencyStorageKey(mappingGid);
  const existing = window.localStorage.getItem(storageKey);
  if (existing) return existing;
  const created = _connectorIdempotencyKey('integration.mapping.import.start');
  window.localStorage.setItem(storageKey, created);
  return created;
}

// ── BOP 直接字段（不走 onto_properties，直接写 bop_entries 列）────────────────
const BOP_DIRECT_FIELDS = [
  { value: 'title',    label: 'title（标题）' },
  { value: 'vpps',     label: 'vpps（稳定标识）' },
  { value: 'seq_no',   label: 'seq_no（序号）' },
  { value: 'vpps_desc',label: 'vpps_desc（描述）' },
];

// ── 初始化 ────────────────────────────────────────────────────────────────────
async function _init() {
  document.getElementById('appRoot').innerHTML = `
    <div class="eds-topbar">
      <span class="eds-topbar-title">外部数据源</span>
      <span class="eds-topbar-path" id="edsPath"></span>
      <div class="eds-spacer"></div>
      <button class="eds-btn-ghost" id="edsSaveBtn" style="display:none">保存字段映射</button>
      <button class="eds-btn-ghost" id="edsPreviewBtn" style="display:none">🔄 刷新预览</button>
      <button class="eds-btn" id="edsImportBtn" style="display:none">▶ 导入</button>
    </div>
    <div class="eds-body">
      <div class="eds-col1">
        <div class="eds-col-hdr">连接 <a id="addDsBtn" title="新建连接">+</a></div>
        <div class="eds-col-list" id="dsList"></div>
      </div>
      <div class="eds-col2">
        <div class="eds-col-hdr">映射 <a id="addMapBtn" title="新建映射" style="display:none">+</a></div>
        <div class="eds-col-list" id="mapList"></div>
      </div>
      <div class="eds-right" id="edsRight">
        <div class="eds-right-empty">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
            <path d="M4 7h16M4 12h10M4 17h7"/><circle cx="19" cy="17" r="3"/>
            <path d="M21 21l-1.5-1.5"/>
          </svg>
          <span>选择左侧映射后编辑字段</span>
        </div>
      </div>
    </div>`;

  document.getElementById('addDsBtn').addEventListener('click', () => _showNewDsModal());
  document.getElementById('addMapBtn').addEventListener('click', _showNewMapModal);
  document.getElementById('edsSaveBtn').addEventListener('click', _saveFieldMaps);
  document.getElementById('edsPreviewBtn').addEventListener('click', () => _loadPreview(true));
  document.getElementById('edsImportBtn').addEventListener('click', _executeImport);

  // 从 URL params 读取跳转过来的 filter_class_gid
  const params = new URLSearchParams(window.location.search);
  const filterClassGid = params.get('filter_class_gid') || null;

  await Promise.all([_loadDatasources(), _loadOntoData()]);
  if (filterClassGid) _highlightMappingByClass(filterClassGid);
}

// ── 本体数据 ──────────────────────────────────────────────────────────────────
async function _loadOntoData() {
  try {
    const classes = _flatClasses(await _listOntologyObjects(['concept']));
    let bindings = [];
    if (classes.length) {
      try {
        bindings = await _listMappingTargets(classes.map(item => item.gid));
      } catch { /* target projection remains fail-closed */ }
    }
    const byOntologyObject = new Map(
      bindings.filter(binding => _validMappingTarget(binding, classes)).map(binding => [binding.ontology_object_gid, binding])
    );
    _ontoClasses = classes.map(item => ({
      ...item,
      integration_target_binding: byOntologyObject.get(item.gid) || null,
    }));
    _ontoProps   = []; // 按需加载
  } catch { /* silent */ }
}

async function _listMappingTargets(ontologyObjectGids) {
  const items = [];
  const uniqueGids = [...new Set(ontologyObjectGids)];
  for (let offset = 0; offset < uniqueGids.length; offset += 200) {
    const projection = await _invokeConnectorCapability('integration.mapping_target.search', {
      ontology_object_gids: uniqueGids.slice(offset, offset + 200),
    });
    items.push(...(projection?.items || []));
  }
  return items;
}

function _validMappingTarget(binding, classes) {
  return binding
    && classes.some(item => item.gid === binding.ontology_object_gid)
    && typeof binding.binding_id === 'string' && binding.binding_id.length > 0
    && typeof binding.target_domain === 'string' && binding.target_domain.length > 0
    && typeof binding.target_capability_id === 'string'
    && binding.target_capability_id.startsWith(`${binding.target_domain}.`)
    && Number.isInteger(binding.target_major_version) && binding.target_major_version > 0
    && typeof binding.minimum_catalog_release === 'string' && binding.minimum_catalog_release.length > 0;
}

function _flatClasses(nodes, res=[]) {
  for (const n of nodes) {
    res.push({
      gid: n.gid || n.stable_gid,
      name: n.name,
      label_zh: n.label_zh || n.name,
      node_type_binding: n.node_type_binding,
    });
    _flatClasses(n.children || [], res);
  }
  return res;
}

async function _loadPropsForClass(classGid) {
  try {
    const classRow = _ontoClasses.find(c => c.gid === classGid);
    const resolved = await _invokeCapability('ontology.concept.resolve', {
      term: classRow?.node_type_binding || classGid,
    });
    const conceptRef = resolved?.concept?.concept_ref || {};
    const stableGid = conceptRef.concept_id || resolved?.concept?.stable_gid;
    if (!stableGid) throw new Error('ontology concept could not be resolved');
    const schema = await _invokeCapability('ontology.concept.get', {
      stable_gid: stableGid,
      kind: 'concept',
      view: 'schema',
      release_gid: resolved?.release_gid,
    });
    const concept = schema?.concept || schema?.data?.concept || schema;
    _ontoProps = concept?.properties || [];
  } catch { _ontoProps = []; }
}

// ── 连接列表 ──────────────────────────────────────────────────────────────────
async function _loadDatasources() {
  try {
    const result = await _invokeConnectorCapability('integration.connector.search', { limit: 200 });
    _datasources = result.items || [];
  } catch (error) {
    _datasources = [];
    _showToast(`连接加载失败：${error?.message || error}`, 'err');
  }
  _renderDsList();
}

function _renderDsList() {
  const el = document.getElementById('dsList');
  if (!el) return;
  if (!_datasources.length) {
    el.innerHTML = '<div style="padding:12px;font-size:12px;color:var(--text-muted,#6c7086)">暂无连接，点 + 新建</div>';
    return;
  }
  el.innerHTML = _datasources.map(ds => {
    const dotCls = ds.status === 'ok' ? 'eds-dot-ok' : ds.status === 'error' ? 'eds-dot-err' : 'eds-dot-unk';
    const active = _selectedDs?.gid === ds.gid ? ' active' : '';
    return `<div class="eds-conn-item${active}" data-gid="${_esc(ds.gid)}">
      <div class="eds-conn-name"><span class="eds-dot ${dotCls}"></span>${_esc(ds.name)}
        <button type="button" class="eds-btn-ghost eds-conn-edit" aria-label="编辑连接 ${_esc(ds.name)}"
          style="margin-left:auto;padding:1px 6px;font-size:10px">编辑</button>
      </div>
      <div class="eds-conn-type">${_esc(ds.connector_type)} · ${_esc(ds.host)}</div>
    </div>`;
  }).join('');
  el.querySelectorAll('.eds-conn-item').forEach(item => {
    item.addEventListener('click', () => _selectDs(item.dataset.gid));
    item.querySelector('.eds-conn-edit').addEventListener('click', event => {
      event.stopPropagation();
      const connector = _datasources.find(value => value.gid === item.dataset.gid);
      if (connector) _showNewDsModal(connector);
    });
  });
}

async function _selectDs(gid) {
  _selectedDs  = _datasources.find(d => d.gid === gid) || null;
  _selectedMap = null;
  _renderDsList();
  document.getElementById('addMapBtn').style.display = _selectedDs ? '' : 'none';
  await _loadMappings();
  _renderRightEmpty();
}

// ── 映射列表 ──────────────────────────────────────────────────────────────────
async function _loadMappings() {
  if (!_selectedDs) { _mappings = []; _renderMapList(); return; }
  try {
    const result = await _invokeConnectorCapability(
      'integration.mapping.search',
      { datasource_gid: _selectedDs.gid, limit: 200 },
    );
    _mappings = result.items || [];
  } catch (error) {
    _mappings = [];
    _showToast(`映射加载失败：${error?.message || error}`, 'err');
  }
  _renderMapList();
}

function _renderMapList() {
  const el = document.getElementById('mapList');
  if (!el) return;
  if (!_selectedDs) { el.innerHTML = ''; return; }
  if (!_mappings.length) {
    el.innerHTML = '<div style="padding:12px;font-size:12px;color:var(--text-muted,#6c7086)">暂无映射，点 + 新建</div>';
    return;
  }
  el.innerHTML = _mappings.map(m => {
    const active = _selectedMap?.gid === m.gid ? ' active' : '';
    const activeMapping = m.status === 'active';
    const tagCls = activeMapping ? 'eds-tag-ok' : 'eds-tag-warn';
    const tagTxt = activeMapping ? '生效中' : m.status;
    return `<div class="eds-map-item${active}" data-gid="${_esc(m.gid)}">
      <div class="eds-map-ext">${_esc(m.source_object)}</div>
      <div class="eds-map-to">↓ 映射到</div>
      <div class="eds-map-cls">${_esc(m.target_capability_id)}</div>
      <span class="eds-tag ${tagCls}">${tagTxt}</span>
    </div>`;
  }).join('');
  el.querySelectorAll('.eds-map-item').forEach(item =>
    item.addEventListener('click', () => _selectMap(item.dataset.gid))
  );
}

async function _selectMap(gid) {
  _selectedMap = _mappings.find(m => m.gid === gid) || null;
  _renderMapList();
  if (!_selectedMap) { _renderRightEmpty(); return; }
  _updatePath();
  _ontoProps = [];
  await _loadExtColumns();
  await _loadFieldMaps();
  await _loadInfoStats();
  _renderRight();
  _loadPreview(false);
  document.getElementById('edsSaveBtn').style.display = '';
  document.getElementById('edsPreviewBtn').style.display = '';
  document.getElementById('edsImportBtn').style.display = '';
}

function _updatePath() {
  const p = document.getElementById('edsPath');
  if (!p || !_selectedDs || !_selectedMap) { if (p) p.innerHTML = ''; return; }
  p.innerHTML = `
    <span>${_esc(_selectedDs.name)}</span>
    <span class="sep">/</span>
    <span>${_esc(_selectedMap.source_object)}</span>
    <span class="sep">→</span>
    <span class="cur">${_esc(_selectedMap.target_capability_id)}</span>`;
}

// ── 右侧面板 ──────────────────────────────────────────────────────────────────
function _renderRightEmpty() {
  document.getElementById('edsRight').innerHTML = `
    <div class="eds-right-empty">
      <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
        <path d="M4 7h16M4 12h10M4 17h7"/><circle cx="19" cy="17" r="3"/><path d="M21 21l-1.5-1.5"/>
      </svg>
      <span>选择左侧映射后编辑字段</span>
    </div>`;
  document.getElementById('edsSaveBtn').style.display = 'none';
  document.getElementById('edsPreviewBtn').style.display = 'none';
  document.getElementById('edsImportBtn').style.display = 'none';
  document.getElementById('edsPath').innerHTML = '';
}

function _renderRight() {
  const right = document.getElementById('edsRight');
  right.innerHTML = `
    <div class="eds-info-strip" id="edsInfoStrip">
      <div class="eds-info-cell"><div class="eds-info-label">外部表行数</div><div class="eds-info-val" id="iRows">—</div></div>
      <div class="eds-info-cell"><div class="eds-info-label">字段映射进度</div><div class="eds-info-val" id="iProgress">—</div></div>
      <div class="eds-info-cell"><div class="eds-info-label">唯一键</div><div class="eds-info-val ok" id="iKey">—</div></div>
      <div class="eds-info-cell"><div class="eds-info-label">上次导入</div><div class="eds-info-val" id="iLastImport">—</div></div>
      <div class="eds-info-cell"><div class="eds-info-label">已导入记录数</div><div class="eds-info-val" id="iImportCount">—</div></div>
    </div>
    <div class="eds-fm-toolbar">
      <span style="font-size:12px;color:var(--text-muted,#6c7086)">字段映射</span>
      <div style="flex:1"></div>
      <button class="eds-btn-ghost" style="font-size:11px;padding:3px 10px" id="edsAutoMapBtn">✨ 智能匹配</button>
    </div>
    <div class="eds-fm-wrap">
      <table class="eds-fm-table">
        <thead><tr>
          <th style="width:170px">外部字段</th>
          <th style="width:70px">类型</th>
          <th style="width:20px"></th>
          <th>本体属性 / BOP字段</th>
          <th style="width:130px">转换表达式</th>
          <th style="width:40px;text-align:center">状态</th>
        </tr></thead>
        <tbody id="edsFmBody"></tbody>
      </table>
    </div>
    <div class="eds-preview-zone">
      <div class="eds-preview-hdr">
        数据预览（前 5 行）
        <span class="eds-preview-live">实时</span>
        <div style="flex:1"></div>
        <span style="font-size:10px;color:var(--accent-color,#89b4fa);cursor:pointer" id="edsExpandPreview">展开 ↗</span>
      </div>
      <div class="eds-preview-scroll" id="edsPreviewScroll">
        <div class="eds-preview-empty">加载中…</div>
      </div>
    </div>`;

  _renderFmBody();
  _updateInfoStrip();
  document.getElementById('edsAutoMapBtn').addEventListener('click', _autoMap);
}

// ── 信息条 ────────────────────────────────────────────────────────────────────
async function _loadInfoStats() {
  if (!_selectedMap) return;
  try {
    // 行数从预览接口统计
    _infoStats = {
      rows: '—',
      key:  '—',
      lastImport: '—',
      importCount: '—',
    };
  } catch { _infoStats = {}; }
}

function _updateInfoStrip() {
  const mapped = _fieldMaps.filter(f => (f.target_field || f.onto_property_gid || f.bop_field) && !f.is_ignored).length;
  const total  = _extColumns.length;
  const progEl = document.getElementById('iProgress');
  if (progEl) {
    progEl.textContent = total ? `${mapped} / ${total}` : '—';
    progEl.className = 'eds-info-val ' + (mapped === total && total > 0 ? 'ok' : 'warn');
  }
  if (document.getElementById('iRows'))        document.getElementById('iRows').textContent = _infoStats.rows || '—';
  if (document.getElementById('iKey'))         document.getElementById('iKey').textContent  = _infoStats.key  || '—';
  if (document.getElementById('iLastImport'))  document.getElementById('iLastImport').textContent = _infoStats.lastImport || '—';
  if (document.getElementById('iImportCount')) document.getElementById('iImportCount').textContent = _infoStats.importCount ?? '—';
}

// ── 字段映射表格 ──────────────────────────────────────────────────────────────
async function _loadExtColumns() {
  if (!_selectedMap) { _extColumns = []; return; }
  try {
    const result = await _invokeConnectorCapability(
      'integration.mapping.source_columns.discover',
      { mapping_gid: _selectedMap.gid, limit: 200 },
    );
    const operation = _operationMessage(result.operation_ref, { subject: '字段发现' });
    if (operation.kind !== 'succeeded') {
      _extColumns = [];
      _showToast(operation.text, operation.kind === 'failed' ? 'err' : 'warn');
      return;
    }
    _extColumns = result.columns || [];
  } catch (error) {
    _extColumns = [];
    _showToast(`字段发现失败：${error?.message || error}`, 'err');
  }
}

async function _loadFieldMaps() {
  if (!_selectedMap) { _fieldMaps = []; return; }
  try {
    const result = await _invokeConnectorCapability(
      'integration.field_mapping.search',
      { mapping_gid: _selectedMap.gid, limit: 200 },
    );
    _fieldMaps = (result.items || []).map(item => {
      const target = item.target_field || '';
      return {
        ...item,
        mapping_gid: _selectedMap.gid,
        ext_column: item.source_field,
        target_type: target.startsWith('bop:') ? 'bop_field' : 'property',
        bop_field: target.startsWith('bop:') ? target.slice(4) : null,
        onto_property_gid: target.startsWith('prop:') ? target.slice(5) : null,
        transform_expr: item.transform_expression || null,
        is_ignored: false,
      };
    });
  } catch (error) {
    _fieldMaps = [];
    _showToast(`字段映射加载失败：${error?.message || error}`, 'err');
  }
  // 确保每个外部列都有一行（新列补空行）
  for (const col of _extColumns) {
    if (!_fieldMaps.find(f => f.ext_column === col.name)) {
      _fieldMaps.push({
        gid: null, mapping_gid: _selectedMap.gid,
        ext_column: col.name, target_type: 'property',
        target_field: null,
        onto_property_gid: null, bop_field: null,
        transform_expr: null, is_ignored: false,
        sort_order: _fieldMaps.length,
      });
    }
  }
}

function _renderFmBody() {
  const tbody = document.getElementById('edsFmBody');
  if (!tbody) return;
  const colMap = Object.fromEntries(_extColumns.map(c => [c.name, c.data_type]));

  // 属性选项
  const propOpts = [
    '<option value="">— 未映射 —</option>',
    '<optgroup label="BOP 直接字段">',
    ...BOP_DIRECT_FIELDS.map(f => `<option value="bop:${f.value}">${_esc(f.label)}</option>`),
    '</optgroup>',
    '<optgroup label="本体属性">',
    ..._ontoProps.map(p => `<option value="prop:${p.gid}">${_esc(p.label_zh || p.name)}（${p.name}）</option>`),
    '</optgroup>',
  ].join('');

  tbody.innerHTML = _fieldMaps.map((fm, idx) => {
    const col      = fm.ext_column;
    const dtype    = colMap[col] || '';
    const isKey    = false;
    const curVal   = fm.target_field || (fm.onto_property_gid ? `prop:${fm.onto_property_gid}` : fm.bop_field ? `bop:${fm.bop_field}` : '');
    const hasProp  = !!curVal;
    const statusCls = fm.is_ignored ? 'none' : hasProp ? 'ok' : 'warn';
    const currentAvailable = curVal.startsWith('bop:')
      ? BOP_DIRECT_FIELDS.some(field => `bop:${field.value}` === curVal)
      : _ontoProps.some(property => `prop:${property.gid}` === curVal);
    const currentOption = curVal && !currentAvailable
      ? `<option value="${_esc(curVal)}">${_esc(curVal)}</option>` : '';

    return `<tr data-idx="${idx}">
      <td class="eds-fm-col">${_esc(col)}${isKey ? ' <span class="eds-fm-key">唯一键</span>' : ''}</td>
      <td><span class="eds-fm-type">${_esc(dtype)}</span></td>
      <td class="eds-fm-arrow">→</td>
      <td>
        <select class="eds-fm-sel" data-idx="${idx}" data-role="prop" ${fm.is_ignored ? 'disabled' : ''}>
          ${propOpts}${currentOption}
        </select>
      </td>
      <td>
        <input class="eds-fm-tx" placeholder="value / 3600" data-idx="${idx}" data-role="tx"
          value="${_esc(fm.transform_expr || '')}" ${fm.is_ignored ? 'disabled' : ''}>
      </td>
      <td style="text-align:center">
        <span class="eds-fm-status ${statusCls}" title="${fm.is_ignored ? '已忽略' : hasProp ? '已映射' : '未映射'}"></span>
      </td>
    </tr>`;
  }).join('');

  // 设置 select 当前值
  tbody.querySelectorAll('[data-role="prop"]').forEach(sel => {
    const fm = _fieldMaps[+sel.dataset.idx];
    const val = fm?.target_field || (fm?.onto_property_gid ? `prop:${fm.onto_property_gid}` : fm?.bop_field ? `bop:${fm.bop_field}` : '');
    sel.value = val;
    sel.addEventListener('change', _onFmChange);
  });
  tbody.querySelectorAll('[data-role="tx"]').forEach(inp =>
    inp.addEventListener('input', _onFmChange)
  );
}

function _onFmChange(e) {
  const idx = +e.target.dataset.idx;
  const fm  = _fieldMaps[idx];
  if (!fm) return;
  const role = e.target.dataset.role;
  if (role === 'prop') {
    const val = e.target.value;
    fm.target_field = val || null;
    if (!val) { fm.onto_property_gid = null; fm.bop_field = null; fm.target_type = 'property'; }
    else if (val.startsWith('bop:')) { fm.bop_field = val.slice(4); fm.onto_property_gid = null; fm.target_type = 'bop_field'; }
    else if (val.startsWith('prop:')) { fm.onto_property_gid = val.slice(5); fm.bop_field = null; fm.target_type = 'property'; }
  } else if (role === 'tx') {
    fm.transform_expr = e.target.value.trim() || null;
  }
  _dirty = true;
  _updateInfoStrip();
  // 更新状态圆点
  const row = e.target.closest('tr');
  if (row) {
    const hasProp = !!(fm.onto_property_gid || fm.bop_field);
    const dot = row.querySelector('.eds-fm-status');
    if (dot) { dot.className = 'eds-fm-status ' + (fm.is_ignored ? 'none' : hasProp ? 'ok' : 'warn'); }
  }
}

async function _saveFieldMaps() {
  if (!_selectedMap) return;
  const items = _fieldMaps.filter(fm => !fm.is_ignored && (
    fm.target_field || fm.onto_property_gid || fm.bop_field
  )).map(fm => ({
    source_field: fm.ext_column,
    target_field: fm.target_field
      || (fm.onto_property_gid ? `prop:${fm.onto_property_gid}` : `bop:${fm.bop_field}`),
    ...(fm.transform_expr ? { transform_expression: fm.transform_expr } : {}),
  }));
  if (!items.length) { _showToast('至少配置一个字段映射后再保存', 'warn'); return; }
  try {
    const result = await _invokeConnectorCapability(
      'integration.field_mapping.batch.update',
      { mapping_gid: _selectedMap.gid, expected_revision: _selectedMap.revision, items },
      { write: true, confirmation: `确认保存“${_selectedMap.name}”的字段映射？` },
    );
    _selectedMap.revision = result.revision;
    _dirty = false;
    _showToast('字段映射已保存', 'ok');
    await _loadMappings();
    _renderMapList();
  } catch (e) { _showToast('保存失败：' + e, 'err'); }
}

// ── 智能匹配 ──────────────────────────────────────────────────────────────────
function _autoMap() {
  let matched = 0;
  for (const fm of _fieldMaps) {
    if (fm.onto_property_gid || fm.bop_field) continue; // 已有映射跳过
    const col = fm.ext_column.toLowerCase().replace(/[-_\s]/g, '');
    // 匹配本体属性
    const prop = _ontoProps.find(p => {
      const pn = p.name.toLowerCase().replace(/[-_\s]/g, '');
      return pn === col || p.label_zh?.replace(/\s/g,'') === fm.ext_column;
    });
    if (prop) { fm.onto_property_gid = prop.gid; fm.target_type = 'property'; matched++; continue; }
    // 匹配 BOP 直接字段
    const bf = BOP_DIRECT_FIELDS.find(f => f.value.toLowerCase() === col || col.includes(f.value));
    if (bf) { fm.bop_field = bf.value; fm.target_type = 'bop_field'; matched++; }
  }
  _renderFmBody();
  _updateInfoStrip();
  _dirty = true;
  _showToast(`智能匹配完成，${matched} 个字段已自动对应`, 'ok');
}

// ── 数据预览 ──────────────────────────────────────────────────────────────────
async function _loadPreview(forceRefresh = false) {
  if (!_selectedMap) return;
  const scroll = document.getElementById('edsPreviewScroll');
  if (!scroll) return;
  scroll.innerHTML = '<div class="eds-preview-empty">加载中…</div>';
  try {
    const result = await _invokeConnectorCapability(
      'integration.mapping.preview',
      { gid: _selectedMap.gid, limit: 5 },
    );
    const operation = _operationMessage(result.operation_ref, { subject: '数据预览' });
    if (operation.kind !== 'succeeded') {
      _previewData = [];
      scroll.innerHTML = `<div class="eds-preview-empty${operation.kind === 'failed' ? ' err' : ''}">${_esc(operation.text)}</div>`;
      return;
    }
    _previewData = (result.rows || []).slice(0, 5);
    const mapped  = _fieldMaps.filter(f => (f.target_field || f.onto_property_gid || f.bop_field) && !f.is_ignored);
    const columns = mapped.slice(0, 6); // 最多显示6列

    if (!_previewData.length) { scroll.innerHTML = '<div class="eds-preview-empty">暂无数据</div>'; return; }

    const getLabel = fm => {
      if (fm.bop_field) return BOP_DIRECT_FIELDS.find(f=>f.value===fm.bop_field)?.label || fm.bop_field;
      const p = _ontoProps.find(p => p.gid === fm.onto_property_gid);
      return p ? `${p.label_zh || p.name}` : fm.target_field || fm.ext_column;
    };

    let html = '<table class="eds-preview-table"><thead><tr>';
    for (const fm of columns) {
      html += `<th>${_esc(fm.ext_column)} → ${_esc(getLabel(fm))}</th>`;
    }
    html += '</tr></thead><tbody>';

    for (const row of _previewData) {
      const cells = Object.fromEntries((row.values || []).map(cell => [cell.field, cell]));
      html += '<tr>';
      for (const fm of columns) {
        const cell = cells[fm.ext_column];
        html += `<td${cell?.redacted ? ' class="tx-val"' : ''}>${_esc(String(cell?.value ?? '—'))}</td>`;
      }
      html += '</tr>';
    }
    html += '</tbody></table>';
    scroll.innerHTML = html;

    // 更新行数
    if (document.getElementById('iRows')) {
      document.getElementById('iRows').textContent = `≥ ${_previewData.length}`;
    }
  } catch (e) {
    scroll.innerHTML = `<div class="eds-preview-empty" style="color:#f38ba8">预览失败：${_esc(String(e))}</div>`;
  }
}

// ── 执行导入 ──────────────────────────────────────────────────────────────────
async function _executeImport() {
  if (!_selectedMap) return;
  if (_dirty) { _showToast('请先保存字段映射', 'warn'); return; }
  const btn = document.getElementById('edsImportBtn');
  btn.disabled = true; btn.textContent = '导入中…';
  const idempotencyKey = _importIdempotencyKey(_selectedMap.gid);
  try {
    const result = await _invokeConnectorCapability(
      'integration.mapping.import.start',
      { mapping_gid: _selectedMap.gid },
      { write: true, confirmation: `确认开始导入“${_selectedMap.name}”？`, idempotencyKey },
    );
    const operation = _operationMessage(result.operation_ref, { subject: '导入' });
    if (operation.kind === 'succeeded' || operation.kind === 'failed') {
      window.localStorage.removeItem(_importIdempotencyStorageKey(_selectedMap.gid));
    }
    _showToast(operation.text || `导入任务 ${result.run_id} 已完成`, operation.kind === 'failed' ? 'err' : operation.kind === 'succeeded' ? 'ok' : 'warn');
  } catch (e) {
    _showToast('导入失败：' + e, 'err');
  } finally {
    btn.disabled = false; btn.textContent = '▶ 导入';
  }
}

// ── 新建连接 Modal ────────────────────────────────────────────────────────────
function _showNewDsModal(ds = null) {
  const isEdit = !!ds;
  const overlay = document.createElement('div');
  overlay.className = 'eds-modal-overlay';
  overlay.innerHTML = `
    <div class="eds-modal">
      <div class="eds-modal-title">${isEdit ? '编辑连接' : '新建连接'}</div>
      <div class="eds-field"><label>连接名称</label>
        <input class="eds-input" id="dsName" value="${_esc(ds?.name||'')}" placeholder="如：MES_DB"></div>
      <div class="eds-field"><label>数据库类型</label>
        <select class="eds-input eds-select" id="dsType">
          <option value="postgresql" ${ds?.connector_type==='postgresql'?'selected':''}>PostgreSQL</option>
          <option value="mysql" ${ds?.connector_type==='mysql'?'selected':''}>MySQL</option>
          <option value="sqlserver" ${ds?.connector_type==='sqlserver'?'selected':''}>SQL Server</option>
        </select></div>
      <div class="eds-row2">
        <div class="eds-field"><label>主机</label>
          <input class="eds-input" id="dsHost" value="${_esc(ds?.host||'')}" placeholder="192.168.1.10"></div>
        <div class="eds-field"><label>端口</label>
          <input class="eds-input" id="dsPort" type="number" value="${ds?.port||5432}"></div>
      </div>
      <div class="eds-field"><label>数据库名</label>
        <input class="eds-input" id="dsDb" value="${_esc(ds?.database_name||'')}" placeholder="mes_production"></div>
      <div class="eds-row2">
        <div class="eds-field"><label>用户名</label>
          <input class="eds-input" id="dsUser" value="${_esc(ds?.username||'')}"></div>
        <div class="eds-field"><label>一次性凭据注册句柄${isEdit?' (留空不轮换)':''}</label>
          <input class="eds-input" id="dsCredentialEnrollmentHandle" autocomplete="off" spellcheck="false"
            placeholder="${isEdit?'粘贴预先创建的句柄以轮换':'粘贴预先创建的句柄'}"></div>
      </div>
      <div id="dsTestResult"></div>
      <div class="eds-modal-actions">
        <button class="eds-btn-ghost" id="dsCancelBtn">取消</button>
        <button class="eds-btn-ghost" id="dsTestBtn">测试连接</button>
        <button class="eds-btn" id="dsSaveBtn2">${isEdit ? '保存' : '创建'}</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);

  overlay.querySelector('#dsCancelBtn').addEventListener('click', () => overlay.remove());
  overlay.querySelector('#dsTestBtn').addEventListener('click', async () => {
    if (!isEdit) { _showToast('请先创建连接后再测试', 'warn'); return; }
    const resEl = document.getElementById('dsTestResult');
    try {
      const result = await _invokeConnectorCapability(
        'integration.connector.connection.test',
        { gid: ds.gid },
        { write: true, confirmation: `确认测试连接“${ds.name}”？` },
      );
      const operation = _operationMessage(result.operation_ref, { subject: '连接测试' });
      if (operation.kind === 'pending') {
        if (resEl) resEl.innerHTML = `<div class="eds-test-result">${_esc(operation.text)}</div>`;
        return;
      }
      if (operation.kind === 'failed' || result.reachable !== true) {
        if (resEl) resEl.innerHTML = `<div class="eds-test-result err">✕ ${_esc(result.message || operation.text)}</div>`;
        return;
      }
      const latency = Number.isInteger(result.latency_ms) ? ` (${result.latency_ms}ms)` : '';
      if (resEl) resEl.innerHTML = `<div class="eds-test-result ok">✓ 连接正常${latency}</div>`;
    } catch (error) {
      if (resEl) resEl.innerHTML = `<div class="eds-test-result err">✕ ${_esc(error?.message || error)}</div>`;
    }
  });
  overlay.querySelector('#dsSaveBtn2').addEventListener('click', async () => {
    const enrollmentHandle = document.getElementById('dsCredentialEnrollmentHandle').value.trim();
    const payload = {
      name: document.getElementById('dsName').value.trim(),
      connector_type: document.getElementById('dsType').value,
      host: document.getElementById('dsHost').value.trim(),
      port: +document.getElementById('dsPort').value,
      database_name: document.getElementById('dsDb').value.trim(),
      username: document.getElementById('dsUser').value.trim(),
      ...(enrollmentHandle ? { credential_enrollment_handle: enrollmentHandle } : {}),
    };
    if (!payload.name || !payload.host || !payload.database_name || (!isEdit && !enrollmentHandle)) {
      _showToast('请填写必填字段和预先创建的一次性凭据注册句柄', 'warn');
      return;
    }
    try {
      if (isEdit) {
        await _invokeConnectorCapability(
          'integration.connector.update',
          { gid: ds.gid, expected_revision: ds.revision, ...payload },
          { write: true, confirmation: `确认更新连接“${ds.name}”？` },
        );
      } else {
        await _invokeConnectorCapability(
          'integration.connector.create',
          payload,
          { write: true, confirmation: `确认创建连接“${payload.name}”？` },
        );
      }
      overlay.remove();
      await _loadDatasources();
      _showToast(isEdit ? '已更新' : '连接已创建', 'ok');
    } catch (e) { _showToast('操作失败：' + e, 'err'); }
  });
}

// ── 新建映射 Modal ────────────────────────────────────────────────────────────
async function _showNewMapModal() {
  if (!_selectedDs) return;
  // 拉取外部表列表
  let tables = [];
  try {
    const result = await _invokeConnectorCapability(
      'integration.connector.schema.discover',
      { gid: _selectedDs.gid, limit: 200 },
    );
    const operation = _operationMessage(result.operation_ref, { subject: '结构发现' });
    if (operation.kind !== 'succeeded') {
      _showToast(operation.text, operation.kind === 'failed' ? 'err' : 'warn');
      return;
    }
    tables = result.objects || [];
  } catch (e) { _showToast('获取表列表失败：' + e, 'err'); return; }

  const tableOpts = tables.map(t => `<option value="${_esc(t.name)}">${_esc(t.name)} (${_esc(t.kind)})</option>`).join('');
  const classOpts = _ontoClasses.map(c =>
    `<option value="${_esc(c.gid)}">${_esc(c.label_zh)} (${_esc(c.name)})</option>`
  ).join('');

  const overlay = document.createElement('div');
  overlay.className = 'eds-modal-overlay';
  overlay.innerHTML = `
    <div class="eds-modal">
      <div class="eds-modal-title">新建映射</div>
      <div class="eds-field"><label>外部表</label>
        <select class="eds-input eds-select" id="mapTable"><option value="">— 选择外部表 —</option>${tableOpts}</select></div>
      <div class="eds-field"><label>本体类</label>
        <select class="eds-input eds-select" id="mapClass"><option value="">— 选择本体类 —</option>${classOpts}</select></div>
      <div class="eds-field"><label>唯一键列（用于去重，通常是 ID 列）</label>
        <input class="eds-input" id="mapKey" placeholder="如：op_id、station_code"></div>
      <div class="eds-modal-actions">
        <button class="eds-btn-ghost" id="mapCancelBtn">取消</button>
        <button class="eds-btn" id="mapSaveBtn">创建映射</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);

  overlay.querySelector('#mapCancelBtn').addEventListener('click', () => overlay.remove());
  overlay.querySelector('#mapSaveBtn').addEventListener('click', async () => {
    const extTable = document.getElementById('mapTable').value;
    const classGid = document.getElementById('mapClass').value;
    const key      = document.getElementById('mapKey').value.trim();
    if (!extTable || !classGid) { _showToast('请选择外部表和本体类', 'warn'); return; }
    const selectedClass = _ontoClasses.find(item => item.gid === classGid);
    if (!selectedClass?.integration_target_binding) {
      _showToast('所选本体类尚未绑定可执行的稳定目标能力', 'warn');
      return;
    }
    try {
      await _invokeConnectorCapability(
        'integration.mapping.create',
        {
          datasource_gid: _selectedDs.gid,
          name: `${extTable} → ${selectedClass?.label_zh || selectedClass?.name || classGid}`,
          source_object: extTable,
          target_binding_id: selectedClass.integration_target_binding.binding_id,
          field_mappings: key ? [{ source_field: key, target_field: 'code' }] : [],
        },
        { write: true, confirmation: `确认创建“${extTable}”映射？` },
      );
      overlay.remove();
      await _loadMappings();
      _renderMapList();
      _showToast('映射已创建，请配置字段映射', 'ok');
    } catch (e) { _showToast('创建失败：' + e, 'err'); }
  });
}

// ── 跳转过滤 ─────────────────────────────────────────────────────────────────
function _highlightMappingByClass(classGid) {
  const map = _mappings.find(m => m.onto_class_gid === classGid);
  if (map) _selectMap(map.gid);
}

// ── Toast ──────────────────────────────────────────────────────────────────────
function _showToast(msg, type = 'ok') {
  const d = document.createElement('div');
  d.className = `eds-toast ${type}`;
  d.textContent = msg;
  document.body.appendChild(d);
  setTimeout(() => d.remove(), 3000);
}

document.addEventListener('DOMContentLoaded', _init);
