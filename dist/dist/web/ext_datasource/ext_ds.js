/**
 * web/ext_datasource/ext_ds.js
 * 外部数据源 — 三栏布局：连接列表 | 映射列表 | 字段映射 + 预览
 */
'use strict';

const _cf = (path, opts) => {
  const fn = window.top?._cloudFetch || window.parent?._cloudFetch || window._cloudFetch;
  if (!fn) throw new TypeError('_cloudFetch 未就绪');
  return fn(path, opts);
};
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

  document.getElementById('addDsBtn').addEventListener('click', _showNewDsModal);
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
    const [clsResp, propResp] = await Promise.all([
      _cf('/api/ontology/classes'),
      _cf('/api/ontology/graph'),
    ]);
    _ontoClasses = _flatClasses(clsResp.data || []);
    _ontoProps   = []; // 按需加载
  } catch { /* silent */ }
}

function _flatClasses(nodes, res=[]) {
  for (const n of nodes) {
    res.push({ gid: n.gid, name: n.name, label_zh: n.label_zh || n.name, node_type_binding: n.node_type_binding });
    _flatClasses(n.children || [], res);
  }
  return res;
}

async function _loadPropsForClass(classGid) {
  try {
    const resp = await _cf(`/api/ontology/schema/${encodeURIComponent(
      _ontoClasses.find(c => c.gid === classGid)?.node_type_binding || classGid
    )}`);
    _ontoProps = resp.properties || [];
  } catch { _ontoProps = []; }
}

// ── 连接列表 ──────────────────────────────────────────────────────────────────
async function _loadDatasources() {
  try {
    const resp = await _cf('/api/ext-datasources');
    _datasources = resp.data || [];
  } catch { _datasources = []; }
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
      <div class="eds-conn-name"><span class="eds-dot ${dotCls}"></span>${_esc(ds.name)}</div>
      <div class="eds-conn-type">${_esc(ds.db_type)} · ${_esc(ds.host)}</div>
    </div>`;
  }).join('');
  el.querySelectorAll('.eds-conn-item').forEach(item =>
    item.addEventListener('click', () => _selectDs(item.dataset.gid))
  );
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
    const resp = await _cf(`/api/ext-mappings?datasource_gid=${_selectedDs.gid}`);
    _mappings = resp.data || [];
  } catch { _mappings = []; }
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
    const mapped = (m.mapped_count || 0);
    const total  = (m.total_count || 0);
    const tagCls = !total ? 'eds-tag-none' : mapped >= total ? 'eds-tag-ok' : 'eds-tag-warn';
    const tagTxt = !total ? '未配置' : `${mapped}/${total} 已映射`;
    return `<div class="eds-map-item${active}" data-gid="${_esc(m.gid)}">
      <div class="eds-map-ext">${_esc(m.ext_table)}</div>
      <div class="eds-map-to">↓ 映射到</div>
      <div class="eds-map-cls">${_esc(m.class_label || m.onto_class_gid)}</div>
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
  // 并行加载：本体属性、外部列、字段映射
  await Promise.all([
    _loadPropsForClass(_selectedMap.onto_class_gid),
    _loadExtColumns(),
    _loadFieldMaps(),
  ]);
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
    <span>${_esc(_selectedMap.ext_table)}</span>
    <span class="sep">→</span>
    <span class="cur">${_esc(_selectedMap.class_label || '')}</span>`;
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
      key:  _selectedMap.unique_key_col || '—',
      lastImport: _selectedMap.last_import_at ? _selectedMap.last_import_at.slice(0,10) : '—',
      importCount: _selectedMap.last_import_count ?? '—',
    };
  } catch { _infoStats = {}; }
}

function _updateInfoStrip() {
  const mapped = _fieldMaps.filter(f => (f.onto_property_gid || f.bop_field) && !f.is_ignored).length;
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
    const resp = await _cf(`/api/ext-mappings/${_selectedMap.gid}/columns`);
    _extColumns = resp.data || [];
  } catch { _extColumns = []; }
}

async function _loadFieldMaps() {
  if (!_selectedMap) { _fieldMaps = []; return; }
  try {
    const resp = await _cf(`/api/ext-field-mappings?mapping_gid=${_selectedMap.gid}`);
    _fieldMaps = resp.data || [];
  } catch { _fieldMaps = []; }
  // 确保每个外部列都有一行（新列补空行）
  for (const col of _extColumns) {
    if (!_fieldMaps.find(f => f.ext_column === col.column_name)) {
      _fieldMaps.push({
        gid: null, mapping_gid: _selectedMap.gid,
        ext_column: col.column_name, target_type: 'property',
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
  const colMap = Object.fromEntries(_extColumns.map(c => [c.column_name, c.data_type]));

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
    const isKey    = col === (_selectedMap?.unique_key_col || '');
    const curVal   = fm.onto_property_gid ? `prop:${fm.onto_property_gid}` : fm.bop_field ? `bop:${fm.bop_field}` : '';
    const hasProp  = !!curVal;
    const statusCls = fm.is_ignored ? 'none' : hasProp ? 'ok' : 'warn';

    return `<tr data-idx="${idx}">
      <td class="eds-fm-col">${_esc(col)}${isKey ? ' <span class="eds-fm-key">唯一键</span>' : ''}</td>
      <td><span class="eds-fm-type">${_esc(dtype)}</span></td>
      <td class="eds-fm-arrow">→</td>
      <td>
        <select class="eds-fm-sel" data-idx="${idx}" data-role="prop" ${fm.is_ignored ? 'disabled' : ''}>
          ${propOpts}
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
    const val = fm?.onto_property_gid ? `prop:${fm.onto_property_gid}` : fm?.bop_field ? `bop:${fm.bop_field}` : '';
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
    if (!val) { fm.onto_property_gid = null; fm.bop_field = null; fm.target_type = 'property'; }
    else if (val.startsWith('bop:')) { fm.bop_field = val.slice(4); fm.onto_property_gid = null; fm.target_type = 'bop_field'; }
    else { fm.onto_property_gid = val.slice(5); fm.bop_field = null; fm.target_type = 'property'; }
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
  const items = _fieldMaps.map((fm, i) => ({
    ext_column:        fm.ext_column,
    target_type:       fm.target_type || 'property',
    onto_property_gid: fm.onto_property_gid || null,
    bop_field:         fm.bop_field || null,
    transform_expr:    fm.transform_expr || null,
    is_ignored:        fm.is_ignored || false,
    sort_order:        i,
  }));
  try {
    await _cf(`/api/ext-field-mappings/batch?mapping_gid=${_selectedMap.gid}`, {
      method: 'PUT', body: JSON.stringify(items),
    });
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
    const resp = await _cf(`/api/ext-mappings/${_selectedMap.gid}/preview?limit=5`);
    _previewData = resp.raw_rows || [];
    const mapped  = _fieldMaps.filter(f => (f.onto_property_gid || f.bop_field) && !f.is_ignored);
    const columns = mapped.slice(0, 6); // 最多显示6列

    if (!_previewData.length) { scroll.innerHTML = '<div class="eds-preview-empty">暂无数据</div>'; return; }

    const colMap = Object.fromEntries(_extColumns.map(c => [c.column_name, c]));
    const getLabel = fm => {
      if (fm.bop_field) return BOP_DIRECT_FIELDS.find(f=>f.value===fm.bop_field)?.label || fm.bop_field;
      const p = _ontoProps.find(p => p.gid === fm.onto_property_gid);
      return p ? `${p.label_zh || p.name}` : fm.ext_column;
    };

    let html = '<table class="eds-preview-table"><thead><tr>';
    for (const fm of columns) {
      html += `<th>${_esc(fm.ext_column)} → ${_esc(getLabel(fm))}</th>`;
    }
    html += '</tr></thead><tbody>';

    for (const raw of _previewData) {
      html += '<tr>';
      for (const fm of columns) {
        const rawVal = raw[fm.ext_column];
        const mapped2 = resp.data?.find(d => d[fm.ext_column]);
        const tx = fm.transform_expr;
        if (tx && rawVal !== undefined && rawVal !== null) {
          html += `<td>${_esc(String(rawVal))} → <span class="tx-val">${_esc(String(mapped2?.[fm.ext_column]?.transformed ?? rawVal))}</span></td>`;
        } else {
          html += `<td>${_esc(String(rawVal ?? '—'))}</td>`;
        }
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
  try {
    const resp = await _cf(`/api/ext-mappings/${_selectedMap.gid}/import`, { method: 'POST' });
    const { imported=0, updated=0, skipped=0, errors=[] } = resp;
    _showToast(`导入完成：新增 ${imported}，更新 ${updated}，跳过 ${skipped}${errors.length ? `，错误 ${errors.length}` : ''}`, 'ok');
    await _loadMappings();
    _renderMapList();
    await _loadInfoStats();
    _updateInfoStrip();
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
          <option value="postgresql" ${ds?.db_type==='postgresql'?'selected':''}>PostgreSQL</option>
          <option value="mysql" ${ds?.db_type==='mysql'?'selected':''}>MySQL</option>
          <option value="sqlserver" ${ds?.db_type==='sqlserver'?'selected':''}>SQL Server</option>
        </select></div>
      <div class="eds-row2">
        <div class="eds-field"><label>主机</label>
          <input class="eds-input" id="dsHost" value="${_esc(ds?.host||'')}" placeholder="192.168.1.10"></div>
        <div class="eds-field"><label>端口</label>
          <input class="eds-input" id="dsPort" type="number" value="${ds?.port||5432}"></div>
      </div>
      <div class="eds-field"><label>数据库名</label>
        <input class="eds-input" id="dsDb" value="${_esc(ds?.database||'')}" placeholder="mes_production"></div>
      <div class="eds-row2">
        <div class="eds-field"><label>用户名</label>
          <input class="eds-input" id="dsUser" value="${_esc(ds?.username||'')}"></div>
        <div class="eds-field"><label>密码${isEdit?' (留空不修改)':''}</label>
          <input class="eds-input" id="dsPwd" type="password" placeholder="${isEdit?'留空不修改':''}"></div>
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
    const r = await _cf(`/api/ext-datasources/${ds.gid}/test`, { method: 'POST' });
    const resEl = document.getElementById('dsTestResult');
    if (resEl) resEl.innerHTML = `<div class="eds-test-result ${r.status==='ok'?'ok':'err'}">${r.status==='ok'?`✓ 连接正常 (${r.latency_ms}ms)`:`✕ ${_esc(r.error||'未知错误')}`}</div>`;
    await _loadDatasources();
  });
  overlay.querySelector('#dsSaveBtn2').addEventListener('click', async () => {
    const payload = {
      name: document.getElementById('dsName').value.trim(),
      db_type: document.getElementById('dsType').value,
      host: document.getElementById('dsHost').value.trim(),
      port: +document.getElementById('dsPort').value,
      database: document.getElementById('dsDb').value.trim(),
      username: document.getElementById('dsUser').value.trim(),
      password: document.getElementById('dsPwd').value,
    };
    if (!payload.name || !payload.host || !payload.database) { _showToast('请填写必填字段', 'warn'); return; }
    try {
      if (isEdit) {
        await _cf(`/api/ext-datasources/${ds.gid}`, { method: 'PATCH', body: JSON.stringify(payload) });
      } else {
        await _cf('/api/ext-datasources', { method: 'POST', body: JSON.stringify(payload) });
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
    const resp = await _cf(`/api/ext-datasources/${_selectedDs.gid}/tables`);
    tables = resp.data || [];
  } catch (e) { _showToast('获取表列表失败：' + e, 'err'); return; }

  const tableOpts = tables.map(t => `<option value="${_esc(t.full_name)}">${_esc(t.full_name)}</option>`).join('');
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
      <div class="eds-field"><label>过滤条件（可选 SQL WHERE 子句）</label>
        <input class="eds-input" id="mapFilter" placeholder="如：status = 'active'"></div>
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
    const filter   = document.getElementById('mapFilter').value.trim();
    if (!extTable || !classGid) { _showToast('请选择外部表和本体类', 'warn'); return; }
    try {
      await _cf('/api/ext-mappings', { method: 'POST', body: JSON.stringify({
        datasource_gid: _selectedDs.gid,
        ext_table: extTable,
        onto_class_gid: classGid,
        unique_key_col: key || null,
        filter_sql: filter || null,
      })});
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
