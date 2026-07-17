/**
 * cad_sim.js — 数模仿真控制界面 v3
 * VisMockup 作为独立窗口运行，此页面负责：连接控制、BOP 结构树、文件打开、节点高亮
 */

// ── VisMockup Bridge（127.0.0.1:7654，由 Electron 在 Windows 启动时 spawn）──────
const _VM_BRIDGE_PORT = 7654;

/**
 * 调用本地 VisMockup Bridge HTTP 服务。
 * 支持两种模式：
 *   kwargs: _bridge('vis_mockup', 'highlight_nodes_by_catia', { catia_names: [...] })
 *   positional: _bridge('vis_mockup', 'color_and_screenshot_op', gid, names)
 */
async function _bridge(ns, method, ...args) {
  let payload;
  if (args.length === 0) {
    payload = {};
  } else if (args.length === 1 && args[0] !== null && args[0] !== undefined
             && typeof args[0] === 'object' && !Array.isArray(args[0])) {
    payload = args[0];
  } else {
    payload = { _args: args };
  }
  try {
    const res = await fetch(`http://127.0.0.1:${_VM_BRIDGE_PORT}/bridge/${ns}/${method}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) return { success: false, error: `HTTP ${res.status}`, data: {} };
    return res.json();
  } catch (e) {
    return { success: false, error: `VisMockup Bridge 未运行 (127.0.0.1:${_VM_BRIDGE_PORT}): ${e.message}`, data: {} };
  }
}

const _eAPI = () => window.electronAPI || window.parent?.electronAPI;
const $ = id => document.getElementById(id);

// ── VisMockup 状态 ────────────────────────────────────────────────────────────
let _vmConnected = false;
let _catiaScanDone = false;   // scan_vis_catia_map 是否完成

// ── Vis 结构树状态 ─────────────────────────────────────────────────────────────
let _visExpandedKeys = new Set();
let _visNodeMap      = {};   // key → { node, nodeEl, eyeEl }
let _visCtxMenu      = null;
let _visTreeLoaded   = false; // 是否已成功加载过结构树（缓存命中时跳过加载指示）

// ── BOP 状态 ──────────────────────────────────────────────────────────────────
let _bopVersions      = [];
let _bopEntries       = [];
let _bopEntryIndex    = {};   // gid → entry（含完整 parts 数组）
let _bopChildMap      = {};   // parent_gid → [entry...]（按 sort_order 排序）
let _bopSubtreeParts  = {};   // gid → 子树内唯一 catia_occ 总数
let _bopSubtreeMatched = {};  // gid → 子树内与 VM 已匹配的唯一 catia_occ 数
let _vmCatiaSet       = new Set();  // scan 后 VM 中存在的所有 catiaOccurrenceName
let _selectedBopGid   = null;
let _tasks          = [];

// ── 详情面板状态 ──────────────────────────────────────────────────────────────
let _dpOpen         = false;
let _dpBopRootGid   = null;   // 当前详情面板的 BOP 树根 gid
let _dpBopSelGid    = null;   // 当前选中的树节点 gid
let _dpExpandedGids = new Set(); // 已展开的 gid

// BOP 节点类型标签
const _BOP_NT_MAP = {
  'line_process':     { label: '线体',   color: '#89b4fa' },
  'station_process':  { label: '工位',   color: '#74c7ec' },
  'operator_process': { label: '岗位',   color: '#a6e3a1' },
  'operation':        { label: '工序',   color: '#fab387' },
  'knowledge':        { label: '知识',   color: '#2d9444' },
  'rule':             { label: '规则',   color: '#d4a017' },
};

// ── 初始化 ───────────────────────────────────────────────────────────────────
async function init() {
  _applyTheme();
  _bindToolbar();
  _bindCmdBar();
  _bindModal();
  _bindBopPanel();
  _bindVisPanel();
  _initDetailPanel();
  await _tryAutoConnect();
  await _loadBopVersions();
  await _loadTasks();
}

function _applyTheme() {
  try {
    const t = window.parent?.document?.documentElement?.getAttribute('data-theme') || 'dark';
    document.documentElement.setAttribute('data-theme', t);
  } catch(_) {}
}

// ── VisMockup 连接 ────────────────────────────────────────────────────────────

/** 页面加载时自动尝试连接已运行的 VisMockup（不启动新进程） */
async function _tryAutoConnect() {
  const st = await _bridge('vis_mockup', 'get_status');
  if (st?.data?.platform === 'non-windows') {
    _setVmStatus('unavailable', '非 Windows 平台');
    return;
  }
  // 尝试附着已运行实例
  const r = await _bridge('vis_mockup', 'launch_vismockup', {});
  if (r?.success && r?.data?.status === 'already_running') {
    _onConnected();
  } else if (r?.success && r?.data?.status === 'starting') {
    _setVmStatus('connecting', '正在连接…');
    _pollConnection();
  } else {
    _setVmStatus('disconnected', 'VisMockup 未运行');
  }
}

/** 工具栏"启动 VisMockup"按钮 */
async function _launchAndConnect() {
  if (_vmConnected) { _showBanner('VisMockup 已连接', 'info'); return; }
  _setVmStatus('connecting', '正在启动…');
  const r = await _bridge('vis_mockup', 'launch_vismockup', {});
  if (!r?.success) {
    _setVmStatus('error', r?.error || '启动失败');
    return;
  }
  if (r.data?.status === 'already_running') {
    _onConnected();
  } else {
    _pollConnection();
  }
}

/** 轮询等待后台连接（最多 150 秒） */
async function _pollConnection() {
  for (let i = 0; i < 300; i++) {
    await new Promise(r => setTimeout(r, 500));
    const st = await _bridge('vis_mockup', 'get_status');
    if (st?.data?.connected) { _onConnected(); return; }
    if (!st?.data?.launching) break;
  }
  _setVmStatus('error', '连接超时，请确认 VisMockup 已正常运行');
}

function _onConnected() {
  _vmConnected = true;
  _setVmStatus('connected', 'VisMockup 已连接');
  // 更新占位区显示
  const ph = $('vmPlaceholder');
  if (ph) {
    ph.innerHTML = `
      <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="var(--green)" stroke-width="1.5">
        <path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/>
        <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
        <line x1="12" y1="22.08" x2="12" y2="12"/>
      </svg>
      <p style="color:var(--green);font-weight:500">VisMockup 已连接</p>
      <p style="font-size:11px;opacity:.6;margin-top:4px">3D 查看器在 VisMockup 独立窗口中运行</p>
      <p style="font-size:11px;opacity:.5;margin-top:2px">点击 BOP 树节点可高亮对应零件</p>
    `;
  }
  // 有缓存时自动加载结构树（不重新遍历，立即返回）
  _loadVisTree(false);
}

// ── VisMockup 状态 UI ─────────────────────────────────────────────────────────

const _VM_STATUS = {
  connected:   { color: 'var(--green)',    title: 'VisMockup 已连接' },
  connecting:  { color: 'var(--yellow)',   title: '正在连接…' },
  error:       { color: 'var(--red)',      title: '连接错误' },
  disconnected:{ color: 'var(--text-dim)', title: '未连接' },
  unavailable: { color: 'var(--text-dim)', title: '不可用' },
};

function _setVmStatus(state, msg) {
  const info = _VM_STATUS[state] || _VM_STATUS.error;
  const dot  = $('vmStatusDot');
  const lbl  = $('vmStatusLabel');
  if (dot) { dot.style.background = info.color; dot.title = info.title; }
  if (lbl) lbl.textContent = msg || info.title;
  if (msg && state !== 'connected') _showBanner(msg, state === 'error' ? 'error' : 'info');
}

function _showBanner(msg, type = 'info') {
  const banner = $('vmBanner'), text = $('vmBannerText');
  if (!banner || !text) return;
  text.textContent = msg;
  banner.classList.remove('hidden');
  banner.classList.toggle('cs-vm-banner-error', type === 'error');
  clearTimeout(banner._hideTimer);
  banner._hideTimer = setTimeout(() => banner.classList.add('hidden'), 6000);
}

// ── 工具栏绑定 ────────────────────────────────────────────────────────────────

function _bindToolbar() {
  $('btnLaunchVm')?.addEventListener('click', _launchAndConnect);
  $('btnOpenFile')?.addEventListener('click', _openFileInViewer);
  $('btnResetCamera')?.addEventListener('click', _resetCamera);
  $('btnNewTask')?.addEventListener('click', () => _openTaskModal());
}

// ── 测试命令条 ────────────────────────────────────────────────────────────────

function _cmdShow(msg, type = 'ok') {
  const el = $('cmdResult');
  if (!el) return;
  el.textContent = msg;
  el.className = `cs-cmd-result ${type}`;
}

function _bindCmdBar() {
  const cmds = [
    ['cmdAllOn',     () => _bridge('vis_mockup', 'all_nodes_on'),  r => { _syncAllVisibility(true);  return `全显 ✓`; }],
    ['cmdAllOff',    () => _bridge('vis_mockup', 'all_nodes_off'), r => { _syncAllVisibility(false); return `全隐 ✓`; }],
    ['cmdSelVisible',() => _bridge('vis_mockup', 'select_visible_nodes'),   r => `选可见 ✓`],
    ['cmdDesel',     () => _bridge('vis_mockup', 'deselect_all_nodes'),     r => `取消选 ✓`],
    ['cmdDynHlOn',   () => _bridge('vis_mockup', 'set_dynamic_highlight', { on: true }),  r => `动态高亮 ON ✓`],
    ['cmdDynHlOff',  () => _bridge('vis_mockup', 'set_dynamic_highlight', { on: false }), r => `动态高亮 OFF ✓`],
    ['cmdDocInfo',   () => _bridge('vis_mockup', 'get_doc_info'),
      r => {
        const d = r.data;
        const name = (d.path || '').split(/[\\/]/).pop() || d.path;
        return `${name} | 可见:${d.num_visible} 加载:${d.num_loaded} 选中:${d.num_selected}`;
      }
    ],
    ['cmdCapture',   () => _bridge('vis_mockup', 'capture_image'),
      r => r.data.exists ? `截图 ✓ ${r.data.path.split(/[\\/]/).pop()}` : `截图写入失败`
    ],
    ['cmdLoadAllGeo', () => _bridge('vis_mockup', 'load_all_geometry'),
      r => `全量几何已加载：${r.data.loaded} 个节点`
    ],
  ];

  for (const [id, fn, fmt] of cmds) {
    $(id)?.addEventListener('click', async () => {
      if (!_vmConnected) { _cmdShow('未连接 VisMockup', 'err'); return; }
      _cmdShow('…');
      try {
        const r = await fn();
        if (r?.success) _cmdShow(fmt(r), 'ok');
        else            _cmdShow(r?.error || '失败', 'err');
      } catch(e) {
        _cmdShow(String(e), 'err');
      }
    });
  }

  $('cmdDebugTree')?.addEventListener('click', async () => {
    console.log('[AI00] Debug树 clicked, _vmConnected=', _vmConnected);
    if (!_vmConnected) { _cmdShow('未连接 VisMockup', 'err'); return; }
    _cmdShow('读取原始树结构…');
    try {
      const r = await _bridge('vis_mockup', 'debug_vis_tree');
      console.log('[AI00] debug_vis_tree response:', r);
      if (r?.success) {
        console.group('[AI00] debug_vis_tree');
        console.log('doc_count:', r.data.doc_count);
        console.log('root_key:', r.data.root_key);
        // 汇总打印 small_key_nodes（太多就只打前20和后20）
        const skn = r.data.small_key_nodes || {};
        const sknKeys = Object.keys(skn).map(Number).sort((a,b)=>a-b);
        console.log(`small_key_nodes 共找到 ${sknKeys.length} 个节点，key 范围: ${sknKeys[0]} ~ ${sknKeys[sknKeys.length-1]}`);
        // 只打印 key 最小的20个和最大的20个，帮助定位 AH 节点位置
        const showKeys = sknKeys.length <= 40 ? sknKeys :
          [...sknKeys.slice(0, 20), '...', ...sknKeys.slice(-20)];
        showKeys.forEach(k => {
          if (k === '...') { console.log('  ...'); return; }
          console.log(`  key=${k}  name="${skn[k].name}"  nc=${skn[k].nc}`);
        });
        if (r.data.parent_tree) {
          console.log('parent_tree (key=RootNode-2):\n' + JSON.stringify(r.data.parent_tree, null, 2));
        }
        if (r.data.viewlist_debug) {
          const vd = r.data.viewlist_debug;
          console.log('viewlist_debug:', JSON.stringify({
            num_views: vd.num_views, av_handle_raw: vd.av_handle_raw,
            doc_handle: vd.doc_handle, av_handle_err: vd.av_handle_err,
          }));
          if (vd.handle_probe) {
            console.log('handle_probe (found views):');
            Object.entries(vd.handle_probe).forEach(([h,v]) =>
              console.log(`  h=${h}: root="${v.root}" nc=${v.nc}`));
          }
          if (vd.export_results) {
            console.log('ExportEx results:');
            Object.entries(vd.export_results).forEach(([k,v]) => {
              if (v.err) console.log(`  ${k}: ERR ${v.err}`);
              else console.log(`  ${k}: exists=${v.exists} size=${v.size}`);
            });
          }
        }
        if (r.data.all_views_info?.length) {
          console.log('all_views_info:');
          r.data.all_views_info.forEach(v => console.log(' ', JSON.stringify(v)));
        } else {
          console.log('all_views_info: []');
        }
        if (r.data.all_nodes_debug) {
          const and = r.data.all_nodes_debug;
          console.log(`all_nodes total=${and.total}`, and.error || '');
          if (and.sample) {
            const si = Object.keys(and.sample).map(Number).sort((a,b)=>a-b);
            si.forEach(i => {
              const s = and.sample[String(i)];
              if (s.err) console.log(`  [${i}] ERR: ${s.err}`);
              else console.log(`  [${i}] key=${s.key} nc=${s.nc} "${s.name}"`);
            });
          }
        }
        if (r.data.hier_debug) {
          console.log('hier_debug:', JSON.stringify(r.data.hier_debug, null, 2));
        }
        console.groupEnd();
        _cmdShow(`Debug完成，共 ${sknKeys.length} 个节点，key 范围 ${sknKeys[0]}~${sknKeys[sknKeys.length-1]}，详见 D:\\Temp\\debug_vis_auto.json`, 'ok');
      } else {
        console.error('[AI00] debug_vis_tree failed:', r);
        _cmdShow(r?.error || 'debug失败', 'err');
      }
    } catch(e) {
      console.error('[AI00] debug_vis_tree exception:', e);
      _cmdShow(String(e), 'err');
    }
  });

  // 诊断 catia 匹配
  $('cmdDebugCatiaMatch')?.addEventListener('click', _debugCatiaMatch);
}

async function _debugCatiaMatch() {
  // 0a. 用已有的 _visNodeMap 检查 VM 节点 name 字段格式
  const vmNodeNames = Object.values(_visNodeMap).map(v => v.node?.name).filter(Boolean);
  if (vmNodeNames.length) {
    console.group('[AI00] VM 节点 name 样本（来自已加载结构树）');
    vmNodeNames.slice(0, 15).forEach((n, i) => console.log(`  VM name[${i}] len=${n.length} | "${n}"`));
    console.groupEnd();
  } else {
    console.log('[AI00] _visNodeMap 为空，请先刷新 VM 结构树');
  }

  // 0b. 打出 DISPID 6/7/8/19 及 MetaDataProperties
  if (_vmConnected) {
    const pr = await _bridge('vis_mockup', 'debug_catia_props');
    if (pr?.success) {
      console.group('[AI00] VM 节点 DISPID 诊断（找哪个字段存了 catiaOccurrenceName）');
      (pr.data.samples || []).forEach((s, i) => {
        const d = s.dispids || {};
        console.log(`节点[${i}] key=${s.key} depth=${s.depth} nc=${s.nc}`);
        console.log(`  Name(7)         = "${d.Name}"`);
        console.log(`  Fullname(8)     = "${d.Fullname}"`);
        console.log(`  DataStoreName(6)= "${d.DataStoreName}"`);
        console.log(`  CADID(19)       = "${d.CADID}"`);
        const pkeys = Object.keys(s.props || {});
        if (pkeys.length) pkeys.forEach(k => console.log(`  MetaData.${k} = "${s.props[k]}"`));
        else console.log('  MetaData: (空)');
      });
      console.groupEnd();
    }
  }
  // 收集 BOP 侧所有非空 catia_occ（去重）
  const bopAllSet = new Set(
    _bopEntries.flatMap(e => (e.parts || []).map(p => p.catia_occ).filter(Boolean))
  );
  const bopSample = [...bopAllSet].slice(0, 10);

  // ── 用 VM 树 node.name 做交叉比对（不依赖扫描）──────────────────
  if (vmNodeNames.length && bopSample.length) {
    const vmNameSet   = new Set(vmNodeNames);
    const vmNameLower = new Set(vmNodeNames.map(n => n.toLowerCase()));
    console.group('[AI00] BOP catia_occ vs VM node.name 交叉比对');
    let exactHit = 0, caseHit = 0;
    bopSample.forEach((v, i) => {
      const exact = vmNameSet.has(v);
      const ci    = !exact && vmNameLower.has(v.toLowerCase());
      if (exact) exactHit++;
      if (ci)    caseHit++;
      console.log(`  BOP[${i}] ${exact ? '✅exact' : ci ? '⚠️case' : '❌'} | "${v}"`);
    });
    // 也打几个 VM name 样本做肉眼对比
    console.log(`VM node.name 样本（共 ${vmNodeNames.length} 个）：`);
    vmNodeNames.slice(0, 8).forEach((n, i) => console.log(`  VM[${i}] "${n}"`));
    console.log(`结论：${exactHit} 精确命中，${caseHit} 大小写差异命中`);
    console.groupEnd();
  }
  // ────────────────────────────────────────────────────────────────

  // 如果还没扫描，先扫描
  if (!_vmCatiaSet.size) {
    if (!_vmConnected) { _cmdShow('未连接 VM，无法诊断', 'err'); return; }
    _cmdShow('正在扫描 VM 节点…');
    const sr = await _bridge('vis_mockup', 'scan_vis_catia_map');
    if (sr?.success) { _catiaScanDone = true; await _refreshVmMatchCounts(); }
    else { _cmdShow(sr?.error || '扫描失败', 'err'); return; }
  }
  const vmSample = [..._vmCatiaSet].slice(0, 10);

  console.group('[AI00] Catia 匹配诊断');
  console.log(`BOP catia_occ 唯一值共 ${bopAllSet.size} 个，取前${bopSample.length}个样本：`);
  bopSample.forEach((v, i) => {
    const hit = _vmCatiaSet.has(v);
    console.log(`  BOP[${i}] ${hit ? '✅' : '❌'} len=${v.length} | "${v}"`);
  });
  console.log(`VM catiaOccurrenceName 唯一值共 ${_vmCatiaSet.size} 个，取前${vmSample.length}个样本：`);
  vmSample.forEach((v, i) => console.log(`  VM[${i}]  len=${v.length} | "${v}"`));

  // 大小写不敏感匹配
  const vmLower = new Map([..._vmCatiaSet].map(v => [v.toLowerCase(), v]));
  const caseHits = bopSample.filter(v => !_vmCatiaSet.has(v) && vmLower.has(v.toLowerCase()));
  if (caseHits.length) {
    console.warn('大小写不匹配的值（BOP → VM实际值）：');
    caseHits.forEach(v => console.warn(`  "${v}" → "${vmLower.get(v.toLowerCase())}"`));
  }
  // 去空格匹配
  const vmTrim = new Map([..._vmCatiaSet].map(v => [v.trim(), v]));
  const trimHits = bopSample.filter(v => !_vmCatiaSet.has(v) && vmTrim.has(v.trim()));
  if (trimHits.length) console.warn('首尾空格导致不匹配：', trimHits);

  console.groupEnd();
  _cmdShow(
    `BOP ${bopAllSet.size} 值 / VM ${_vmCatiaSet.size} 值` +
    (caseHits.length ? ` ⚠️ 大小写不匹配${caseHits.length}个` : '') +
    (trimHits.length ? ` ⚠️ 空格问题${trimHits.length}个` : '') +
    ' — 详见F12控制台',
    caseHits.length || trimHits.length ? 'warn' : 'ok'
  );
}

async function _openFileInViewer() {
  const eAPI = _eAPI();
  if (!eAPI) { _showBanner('需要 Electron 环境', 'error'); return; }
  if (!_vmConnected) { _showBanner('请先连接 VisMockup', 'error'); return; }
  try {
    const paths = await eAPI.showOpenDialog({
      title: '选择 PLMXML / JT 文件',
      properties: ['openFile'],
      filters: [
        { name: 'PLMXML 文件', extensions: ['xml', 'plmxml'] },
        { name: 'JT 文件', extensions: ['jt'] },
        { name: '所有文件', extensions: ['*'] },
      ],
    });
    if (!paths?.length) return;
    _setVmStatus('connecting', '打开文件中…');
    const r = await _bridge('vis_mockup', 'open_file', { file_path: paths[0] });
    if (r?.success) {
      _setVmStatus('connected', 'VisMockup 已连接');
    } else {
      _setVmStatus('error', r?.error || '打开文件失败');
    }
  } catch(e) {
    console.error('[cad_sim] open file error:', e);
  }
}

async function _resetCamera() {
  if (!_vmConnected) return;
  await _bridge('vis_mockup', 'reset_view', {});
}

// ── BOP 版本面板 ──────────────────────────────────────────────────────────────

function _bindBopPanel() {
  $('btnRefreshVers')?.addEventListener('click', _loadBopVersions);
  $('btnLoadBopVer')?.addEventListener('click', () => {
    const sel = $('bopVersionSel');
    if (sel?.value) _loadBopTree(sel.value);
  });
  $('bopVersionSel')?.addEventListener('change', () => {
    const gid = $('bopVersionSel')?.value;
    if (gid) _loadBopTree(gid);
  });
  $('btnToggleManual')?.addEventListener('click', () => {
    const row = $('bopManualRow');
    if (row) {
      const hidden = row.classList.toggle('hidden');
      $('btnToggleManual').textContent = hidden ? '手动输入 GID' : '收起';
    }
  });
  $('btnLoadBopGid')?.addEventListener('click', () => {
    const gid = $('bopGidInput')?.value?.trim();
    if (gid) _loadBopTree(gid);
  });
  $('bopGidInput')?.addEventListener('keydown', e => {
    if (e.key === 'Enter') { const gid = e.target.value.trim(); if (gid) _loadBopTree(gid); }
  });
}

async function _loadBopVersions() {
  const cf = window.parent?._cloudFetch || window._cloudFetch;
  if (!cf) return;
  try {
    const data = await cf('/api/bop/versions?limit=100');
    _bopVersions = data?.data || data?.versions || data?.items || [];
    _renderVersionSelector();
  } catch(e) { console.warn('[cad_sim] loadBopVersions:', e); }
}

function _renderVersionSelector() {
  const sel = $('bopVersionSel');
  if (!sel) return;
  const prev = sel.value;
  sel.innerHTML = '<option value="">-- 选择 BOP 版本 --</option>' +
    _bopVersions.map(v => {
      const label = v.bop_name || v.name || v.gid;
      const status = v.status ? ` [${v.status}]` : '';
      return `<option value="${v.gid}">${_esc(label + status)}</option>`;
    }).join('');
  if (prev && _bopVersions.some(v => v.gid === prev)) sel.value = prev;
}

async function _loadBopTree(versionGid) {
  if (!versionGid) return;
  _selectedBopGid = versionGid;
  $('bopTreeLoading').classList.remove('hidden');
  $('bopTreeEmpty').classList.add('hidden');
  $('bopTreeBody').innerHTML = '';
  $('bopVerStatus').classList.add('hidden');

  const cf = window.parent?._cloudFetch || window._cloudFetch;
  if (!cf) {
    $('bopTreeLoading').classList.add('hidden');
    $('bopTreeEmpty').textContent = '需要飞书登录才能加载 BOP 数据';
    $('bopTreeEmpty').classList.remove('hidden');
    return;
  }
  try {
    // 用 alt-hier 端点：返回带 parts（catia_occ）的完整条目列表
    const data = await cf(`/api/bop/versions/${versionGid}/alt-hier`);
    _bopEntries = data?.entries || [];
    _bopEntryIndex = Object.fromEntries(_bopEntries.map(e => [e.gid, e]));
    // 构建父子映射（parent_gid → children[]，按 sort_order 排序）
    _bopChildMap = {};
    for (const e of _bopEntries) {
      const key = e.parent_gid || '__root__';
      (_bopChildMap[key] = _bopChildMap[key] || []).push(e);
    }
    for (const arr of Object.values(_bopChildMap)) {
      arr.sort((a, b) => (a.sort_order ?? 999) - (b.sort_order ?? 999));
    }
    _computeSubtreeParts();

    const ver = _bopVersions.find(v => v.gid === versionGid);
    if (ver?.status) {
      const statusEl = $('bopVerStatus');
      statusEl.textContent = `状态: ${ver.status}`;
      statusEl.className = `cs-bop-ver-status cs-bop-ver-${ver.status}`;
      statusEl.classList.remove('hidden');
    }

    const roots = _buildTree(_bopEntries);
    $('bopTreeBody').innerHTML = _renderBopNodes(roots, 0);
    _bindBopTreeEvents();
  } catch(e) {
    $('bopTreeEmpty').textContent = `加载失败: ${e.message}`;
    $('bopTreeEmpty').classList.remove('hidden');
  } finally {
    $('bopTreeLoading').classList.add('hidden');
  }
}

/** 计算每个 BOP 节点子树内唯一 catia_occ 数量，存入 _bopSubtreeParts。 */
function _computeSubtreeParts() {
  _bopSubtreeParts = {};
  const cache = {};  // gid → Set<catia_occ>
  function _collect(gid) {
    if (cache[gid]) return cache[gid];
    const entry = _bopEntryIndex[gid];
    if (!entry) return (cache[gid] = new Set());
    const set = new Set();
    for (const p of (entry.parts || [])) {
      if (p.catia_occ) set.add(p.catia_occ);
    }
    for (const child of (_bopChildMap[gid] || [])) {
      for (const occ of _collect(child.gid)) set.add(occ);
    }
    cache[gid] = set;
    return set;
  }
  for (const e of _bopEntries) {
    _bopSubtreeParts[e.gid] = _collect(e.gid).size;
  }
}

/** 计算每个节点子树内与 VM _vmCatiaSet 匹配的唯一 catia_occ 数，存入 _bopSubtreeMatched。 */
function _computeSubtreeMatched() {
  _bopSubtreeMatched = {};
  if (!_vmCatiaSet.size) return;
  const cache = {};
  function _collect(gid) {
    if (cache[gid]) return cache[gid];
    const entry = _bopEntryIndex[gid];
    if (!entry) return (cache[gid] = new Set());
    const set = new Set();
    for (const p of (entry.parts || [])) {
      if (p.catia_occ && _vmCatiaSet.has(p.catia_occ)) set.add(p.catia_occ);
    }
    for (const child of (_bopChildMap[gid] || [])) {
      for (const occ of _collect(child.gid)) set.add(occ);
    }
    cache[gid] = set;
    return set;
  }
  for (const e of _bopEntries) {
    _bopSubtreeMatched[e.gid] = _collect(e.gid).size;
  }
}

/** 扫描完成后从 Python 拉取 catia 键集合，重算匹配数，更新 BOP 树徽标（不重建 DOM）。 */
async function _refreshVmMatchCounts() {
  const r = await _bridge('vis_mockup', 'get_catia_map_keys');
  if (!r?.success) return;
  _vmCatiaSet = new Set(r.data.keys || []);
  _computeSubtreeMatched();
  _updateBopBadges();
}

/** 就地更新 BOP 树中所有 [data-badge-gid] 徽标，显示 matched/total 格式。 */
function _updateBopBadges() {
  const hasScan = _vmCatiaSet.size > 0;
  $('bopTreeBody')?.querySelectorAll('[data-badge-gid]').forEach(el => {
    const gid     = el.dataset.badgeGid;
    const total   = _bopSubtreeParts[gid]  || 0;
    const matched = _bopSubtreeMatched[gid] || 0;
    if (total === 0) { el.style.display = 'none'; return; }
    el.style.display = '';
    if (hasScan) {
      el.innerHTML = `<span style="color:${matched===total?'var(--green)':matched>0?'var(--yellow)':'var(--red)'}">${matched}</span><span style="opacity:.5">/${total}</span>`;
      el.title = `VM 已匹配 ${matched} / 子树共 ${total} 个零件`;
      el.className = 'cs-bop-part-badge' + (matched===total?' cs-bop-badge-full':matched>0?' cs-bop-badge-partial':' cs-bop-badge-none');
    } else {
      el.textContent = String(total);
      el.title = `子树共 ${total} 个零件（按 catiaOccurrenceName 统计）`;
      el.className = 'cs-bop-part-badge';
    }
  });
}

function _buildTree(entries) {
  const map = {}, roots = [];
  entries.forEach(e => { map[e.gid] = { ...e, children: [] }; });
  entries.forEach(e => {
    if (e.parent_gid && map[e.parent_gid]) map[e.parent_gid].children.push(map[e.gid]);
    else roots.push(map[e.gid]);
  });
  const sort = arr => {
    arr.sort((a, b) => (a.seq_no ?? 999) - (b.seq_no ?? 999));
    arr.forEach(n => sort(n.children));
  };
  sort(roots);
  return roots;
}

function _renderBopNodes(nodes, depth) {
  return nodes.map(n => {
    const hasChildren = n.children?.length > 0;
    const indent = depth * 14 + 8;
    const typeClass = `cs-bop-type-${n.node_type || 'other'}`;
    const subtreeCount = _bopSubtreeParts[n.gid] || 0;
    const partBadge = `<span class="cs-bop-part-badge" data-badge-gid="${n.gid}"
        title="子树共 ${subtreeCount} 个零件（按 catiaOccurrenceName 统计）"
        style="${subtreeCount === 0 ? 'display:none' : ''}">${subtreeCount}</span>`;
    return `
      <div class="cs-bop-row" data-gid="${n.gid}" data-title="${_esc(n.title || '')}"
           data-parts="${_esc(JSON.stringify((n.parts||[]).map(p=>p.catia_occ).filter(Boolean)))}">
        <div class="cs-bop-node ${typeClass}" style="padding-left:${indent}px">
          <span class="cs-bop-toggle ${hasChildren ? '' : 'cs-bop-leaf'}" data-gid="${n.gid}">
            ${hasChildren ? '▶' : '·'}
          </span>
          <span class="cs-bop-label">${_esc(n.title || n.gid)}</span>
          ${partBadge}
        </div>
        ${hasChildren ? `<div class="cs-bop-children" data-parent="${n.gid}" style="display:none">
          ${_renderBopNodes(n.children, depth + 1)}
        </div>` : ''}
      </div>
    `;
  }).join('');
}

function _bindBopTreeEvents() {
  $('bopTreeBody').querySelectorAll('.cs-bop-node').forEach(el => {
    el.addEventListener('click', async e => {
      const row   = el.closest('.cs-bop-row');
      const gid   = row?.dataset?.gid;
      const title = row?.dataset?.title || '';
      if (!gid) return;

      $('bopTreeBody').querySelectorAll('.cs-bop-node').forEach(n => n.classList.remove('active'));
      el.classList.add('active');

      const children = el.parentElement.querySelector(`.cs-bop-children[data-parent="${gid}"]`);
      const toggle   = el.querySelector('.cs-bop-toggle');
      if (children) {
        const isOpen = children.style.display !== 'none';
        children.style.display = isOpen ? 'none' : '';
        if (toggle) toggle.textContent = isOpen ? '▶' : '▼';
      }

      $('nodePathLabel').textContent = title || gid;

      // 详情面板
      _showBopDetail(_bopEntryIndex[gid]);

      // 取该节点（及其所有子孙）的全部 catia_occ，批量高亮 VM 节点
      if (_vmConnected) {
        const allParts = _collectBopRowParts(row);
        if (allParts.length > 0) {
          if (!_catiaScanDone) {
            _cmdShow('正在扫描 VM 节点…');
            const sr = await _bridge('vis_mockup', 'scan_vis_catia_map');
            if (sr?.success) { _catiaScanDone = true; _refreshVmMatchCounts(); }
          }
          const r = await _bridge('vis_mockup', 'highlight_nodes_by_catia',
            { catia_names: allParts, mode: 'highlight' });
          if (r?.success) {
            const inTree = r.data.keys?.length > 0 ? _selectVisTreeNodes(r.data.keys) : 0;
            const treeHint = inTree > 0 ? `，VM树已选中 ${inTree} 个` : '';
            _cmdShow(`高亮 ${r.data.matched}/${allParts.length} 个零件${treeHint}`, 'ok');
          } else {
            _cmdShow(r?.error || '高亮失败', 'err');
          }
        }
      }
    });
  });
}

/** 收集一个 BOP 行及其所有展开子孙行的全部 catia_occ */
function _collectBopRowParts(row) {
  const parts = new Set();
  const _collect = el => {
    try {
      const raw = el.dataset?.parts;
      if (raw) JSON.parse(raw).forEach(p => { if (p) parts.add(p); });
    } catch(_) {}
    el.querySelectorAll('.cs-bop-row').forEach(_collect);
  };
  _collect(row);
  return [...parts];
}

/** 在 VM 结构树 UI 中选中（高亮）指定 node key 列表，返回实际找到的数量，并滚动到第一个 */
function _selectVisTreeNodes(keys) {
  $('visTreeBody').querySelectorAll('.cs-vis-node.cs-vis-active')
    .forEach(n => n.classList.remove('cs-vis-active'));
  let firstEl = null;
  let count = 0;
  for (const key of keys) {
    const entry = _visNodeMap[key];
    if (!entry) continue;
    entry.nodeEl.classList.add('cs-vis-active');
    count++;
    if (!firstEl) firstEl = entry.nodeEl;
  }
  if (firstEl) firstEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  return count;
}

// ── 底部详情面板 ───────────────────────────────────────────────────────────────

function _initDetailPanel() {
  const panel  = $('csDetailPanel');
  const handle = $('dpHandle');
  const resize = $('dpResize');
  const close  = $('dpClose');
  if (!panel) return;

  handle?.addEventListener('click', () => {
    _dpOpen = true;
    panel.classList.add('open');
    // 补充渲染（面板关闭时发生的点击会记录 root，打开时补渲染）
    if (_dpBopRootGid && $('dpBopContent') && !$('dpBopContent').classList.contains('hidden')) {
      _renderBopTree();
      _renderBopNodeDetail(_dpBopSelGid || _dpBopRootGid);
    }
  });
  close?.addEventListener('click', () => {
    _dpOpen = false;
    panel.classList.remove('open');
  });

  // BOP 树点击事件委托（持久绑定，innerHTML 变化不影响）
  $('dpBopTree')?.addEventListener('click', e => {
    const item = e.target.closest('.cs-dp-tree-item');
    if (!item) return;
    const gid = item.dataset.gid;
    const toggle = e.target.closest('.cs-dp-tree-toggle');
    if (toggle && !toggle.classList.contains('leaf')) {
      if (_dpExpandedGids.has(gid)) _dpExpandedGids.delete(gid);
      else _dpExpandedGids.add(gid);
      _renderBopTree();
      return;
    }
    _dpBopSelGid = gid;
    $('dpBopTree').querySelectorAll('.cs-dp-tree-item.selected')
      .forEach(el => el.classList.remove('selected'));
    item.classList.add('selected');
    _renderBopNodeDetail(gid);
  });

  // 拖拽调高
  let _dragging = false, _startY = 0, _startH = 240;
  resize?.addEventListener('mousedown', e => {
    _dragging = true;
    _startY = e.clientY;
    _startH = panel.offsetHeight;
    resize.classList.add('active');
    document.body.style.cursor = 'ns-resize';
    document.body.style.userSelect = 'none';
  });
  document.addEventListener('mousemove', e => {
    if (!_dragging) return;
    const newH = Math.max(120, Math.min(window.innerHeight * 0.6,
      _startH + (_startY - e.clientY)));
    panel.style.setProperty('--dp-h', newH + 'px');
  });
  document.addEventListener('mouseup', () => {
    if (!_dragging) return;
    _dragging = false;
    resize.classList.remove('active');
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  });
}

function _showBopDetail(entry) {
  if (!entry) return;

  // 始终更新把手标签
  const handleLabel = $('dpHandleLabel');
  if (handleLabel) handleLabel.textContent = `BOP: ${entry.title || entry.gid} ▲`;

  // 面板关闭时不更新内容
  if (!_dpOpen) return;

  // 头部
  const srcTag = $('dpSourceTag');
  if (srcTag) { srcTag.textContent = 'BOP'; srcTag.style.cssText = 'background:rgba(137,180,250,.15);color:#89b4fa'; }
  const titleEl = $('dpTitle');
  if (titleEl) titleEl.textContent = entry.title || entry.gid;

  // 显隐
  $('dpPlaceholder')?.classList.add('hidden');
  $('dpVisContent')?.classList.add('hidden');
  $('dpBopContent')?.classList.remove('hidden');

  // 初始化树状态（如果是新的根节点则重置）
  if (_dpBopRootGid !== entry.gid) {
    _dpBopRootGid  = entry.gid;
    _dpBopSelGid   = entry.gid;
    _dpExpandedGids.clear();
    _dpExpandedGids.add(entry.gid);
    // 默认也展开第一层子节点（工位以下）
    (_bopChildMap[entry.gid] || []).forEach(c => _dpExpandedGids.add(c.gid));
  }

  _renderBopTree();
  _renderBopNodeDetail(_dpBopSelGid);
}

/** 渲染 BOP 子树（左侧树，从 _dpBopRootGid 开始） */
function _renderBopTree() {
  const treeEl = $('dpBopTree');
  if (!treeEl || !_dpBopRootGid) return;

  const html = [];
  _renderBopTreeNode(_dpBopRootGid, 0, html);
  treeEl.innerHTML = html.join('');
  // 事件由 _initDetailPanel 中通过事件委托统一处理
}

function _renderBopTreeNode(gid, depth, html) {
  const entry = _bopEntryIndex[gid];
  if (!entry) return;
  const children   = _bopChildMap[gid] || [];
  const hasChildren = children.length > 0;
  const isExpanded  = _dpExpandedGids.has(gid);
  const isSelected  = _dpBopSelGid === gid;
  const indent      = depth * 16 + 8;
  const nt = _BOP_NT_MAP[entry.node_type] || { label: '?', color: '#6c7086' };

  html.push(`<div class="cs-dp-tree-item${isSelected ? ' selected' : ''}" data-gid="${gid}" style="padding-left:${indent}px">`);
  html.push(`<span class="cs-dp-tree-toggle${hasChildren ? (isExpanded ? ' expanded' : '') : ' leaf'}">▶</span>`);
  html.push(`<span class="cs-dp-tree-dot" style="background:${nt.color}"></span>`);
  html.push(`<span class="cs-dp-tree-label">${_esc(entry.title || entry.gid)}</span>`);
  const subCount  = _bopSubtreeParts[gid]   || 0;
  const subMatch  = _bopSubtreeMatched[gid] || 0;
  if (subCount > 0) {
    const hasScan = _vmCatiaSet.size > 0;
    const badgeInner = hasScan
      ? `<span style="color:${subMatch===subCount?'var(--green)':subMatch>0?'var(--yellow)':'var(--red)'}">${subMatch}</span><span style="opacity:.5">/${subCount}</span>`
      : String(subCount);
    const badgeTitle = hasScan
      ? `VM 已匹配 ${subMatch} / 子树共 ${subCount} 个零件`
      : `子树共 ${subCount} 个零件`;
    const cls = hasScan
      ? (subMatch===subCount ? 'cs-bop-badge-full' : subMatch>0 ? 'cs-bop-badge-partial' : 'cs-bop-badge-none')
      : '';
    html.push(`<span class="cs-dp-tree-partbadge ${cls}" title="${badgeTitle}">${badgeInner}</span>`);
  }
  html.push('</div>');

  if (hasChildren && isExpanded) {
    for (const child of children) _renderBopTreeNode(child.gid, depth + 1, html);
  }
}

/** 渲染右侧：字段 + 零件表（针对树中选中的节点） */
function _renderBopNodeDetail(gid) {
  const right = $('dpBopRight');
  if (!right) return;
  const entry = _bopEntryIndex[gid];
  if (!entry) { right.innerHTML = '<div class="cs-dp-empty-hint">未找到节点</div>'; return; }

  const nt = _BOP_NT_MAP[entry.node_type] || { label: entry.node_type || '节点', color: '#6c7086' };
  let html = `
    <div class="cs-dp-section-title">基本信息</div>
    <div class="cs-dp-field-row">
      <span class="cs-dp-field-label">类型</span>
      <span class="cs-dp-nt-badge" style="background:${nt.color}">${_esc(nt.label)}</span>
    </div>
    <div class="cs-dp-field-row">
      <span class="cs-dp-field-label">标题</span>
      <span class="cs-dp-field-val">${_esc(entry.title || '—')}</span>
    </div>
    ${entry.vpps ? `<div class="cs-dp-field-row">
      <span class="cs-dp-field-label">VPPS</span>
      <span class="cs-dp-field-val mono">${_esc(entry.vpps)}</span>
    </div>` : ''}
    ${entry.level != null ? `<div class="cs-dp-field-row">
      <span class="cs-dp-field-label">Level</span>
      <span class="cs-dp-field-val">${_esc(String(entry.level))}</span>
    </div>` : ''}
    ${entry.ai00_level != null ? `<div class="cs-dp-field-row">
      <span class="cs-dp-field-label">AI00 L</span>
      <span class="cs-dp-field-val">${_esc(String(entry.ai00_level))}</span>
    </div>` : ''}
    ${entry.sort_order != null ? `<div class="cs-dp-field-row">
      <span class="cs-dp-field-label">顺序</span>
      <span class="cs-dp-field-val">${_esc(String(entry.sort_order))}</span>
    </div>` : ''}
    <div class="cs-dp-field-row" style="margin-top:4px">
      <span class="cs-dp-field-label" style="opacity:.5">GID</span>
      <span class="cs-dp-field-val mono" style="opacity:.4;font-size:9px">${_esc(entry.gid)}</span>
    </div>
  `;

  const parts = entry.parts || [];
  if (parts.length === 0) {
    html += `<div class="cs-dp-section-title" style="margin-top:10px">关联零件</div>
      <div class="cs-dp-empty-hint">无关联零件</div>`;
  } else {
    html += `<div class="cs-dp-section-title" style="margin-top:10px">关联零件（${parts.length}）</div>
      <table class="cs-dp-parts-table">
        <thead><tr><th>图号</th><th>名称</th><th>Catia Occ</th><th>数量</th></tr></thead>
        <tbody>${parts.map(p => `<tr>
          <td class="mono">${_esc(p.part_no || '—')}</td>
          <td>${_esc(p.name || '—')}</td>
          <td class="mono">${_esc(p.catia_occ || '—')}</td>
          <td>${p.quantity != null ? _esc(String(p.quantity)) : '—'}</td>
        </tr>`).join('')}</tbody>
      </table>`;
  }
  right.innerHTML = html;
}

function _showVisDetail(node) {
  const panel = $('csDetailPanel');
  if (!panel || !node) return;

  // 把手标签
  const handleLabel = $('dpHandleLabel');
  if (handleLabel) handleLabel.textContent = `VM: ${node.name || 'node:' + node.key} ▲`;

  if (!_dpOpen) return;

  // 头部
  const srcTag = $('dpSourceTag');
  if (srcTag) {
    srcTag.textContent = 'VM';
    srcTag.style.cssText = 'background:rgba(166,227,161,.15);color:#a6e3a1';
  }
  const titleEl = $('dpTitle');
  if (titleEl) titleEl.textContent = node.name || `node:${node.key}`;

  // 显隐
  $('dpPlaceholder')?.classList.add('hidden');
  $('dpBopContent')?.classList.add('hidden');
  $('dpVisContent')?.classList.remove('hidden');

  // LEFT: 节点基本信息
  const left = $('dpVisLeft');
  if (left) {
    left.innerHTML = `
      <div class="cs-dp-section-title">节点信息</div>
      ${node.catia_name ? `<div class="cs-dp-field-row">
        <span class="cs-dp-field-label">Catia名</span>
        <span class="cs-dp-field-val mono">${_esc(node.catia_name)}</span>
      </div>` : ''}
      <div class="cs-dp-field-row">
        <span class="cs-dp-field-label">Key</span>
        <span class="cs-dp-field-val mono">${_esc(String(node.key || ''))}</span>
      </div>
      <div class="cs-dp-field-row">
        <span class="cs-dp-field-label">可见性</span>
        <span class="cs-dp-field-val">${node.visible ? '✓ 可见' : '✗ 隐藏'}</span>
      </div>
      <div class="cs-dp-field-row">
        <span class="cs-dp-field-label">子节点</span>
        <span class="cs-dp-field-val">${node.children?.length ?? 0}${node.has_more ? '+' : ''}</span>
      </div>
    `;
  }

  // RIGHT: PLM 元数据（按需加载）
  const right = $('dpVisRight');
  if (!right) return;
  right.innerHTML = `
    <div class="cs-dp-section-title">PLM 元数据</div>
    <button class="cs-dp-meta-btn" id="dpVisMetaBtn">加载元数据</button>
  `;
  right.querySelector('#dpVisMetaBtn')?.addEventListener('click', async () => {
    const btn = right.querySelector('#dpVisMetaBtn');
    if (btn) btn.textContent = '加载中…';
    if (!_vmConnected) { if (btn) btn.textContent = '未连接 VisMockup'; return; }
    const r = await _bridge('vis_mockup', 'get_node_metadata', { node_key: node.key });
    if (!r?.success) {
      right.innerHTML = `<div class="cs-dp-section-title">PLM 元数据</div>
        <div class="cs-dp-empty-hint">${_esc(r?.error || '加载失败')}</div>`;
      return;
    }
    const d = r.data;
    let html = '<div class="cs-dp-section-title">节点属性</div>';
    for (const [k, label] of [['PrintableName','名称'],['Fullname','全称'],
        ['DataStoreName','文件名'],['CADID','CADID']]) {
      if (d[k]) html += `<div class="cs-dp-field-row">
        <span class="cs-dp-field-label">${label}</span>
        <span class="cs-dp-field-val mono">${_esc(d[k])}</span>
      </div>`;
    }
    const meta = d['_metadata'] || {};
    const mkeys = Object.keys(meta).sort((a, b) => {
      const pri = ['catiaoccurrencename','__PLM_INST_UID'];
      const ia = pri.indexOf(a), ib = pri.indexOf(b);
      if (ia >= 0 && ib >= 0) return ia - ib;
      if (ia >= 0) return -1; if (ib >= 0) return 1;
      return a.localeCompare(b);
    });
    if (mkeys.length > 0) {
      html += `<div class="cs-dp-section-title">MetaData (${mkeys.length})</div>`;
      for (const k of mkeys) {
        html += `<div class="cs-dp-field-row">
          <span class="cs-dp-field-label" title="${_esc(k)}" style="overflow:hidden;text-overflow:ellipsis;max-width:100px">${_esc(k)}</span>
          <span class="cs-dp-field-val mono">${_esc(String(meta[k]))}</span>
        </div>`;
      }
    }
    right.innerHTML = html || '<div class="cs-dp-empty-hint">无可读元数据</div>';
  });
}



async function _loadTasks() {
  const cf = window.parent?._cloudFetch || window._cloudFetch;
  if (!cf) return;
  try {
    const data = await cf('/api/tasks?list_gid=sim_eval&limit=200');
    _tasks = data?.items || data?.data || [];
  } catch(e) { console.warn('[cad_sim] loadTasks:', e); }
}

function _bindModal() {
  $('taskModalCancel')?.addEventListener('click', _closeTaskModal);
  $('taskModalSave')?.addEventListener('click', _saveTask);
  $('taskModalOverlay')?.addEventListener('click', e => {
    if (e.target === $('taskModalOverlay')) _closeTaskModal();
  });
}

function _openTaskModal() {
  $('taskModalGid').value = '';
  $('taskModalTitle').value = '';
  $('taskModalType').value = 'early_eval';
  $('taskModalWorkPlan').value = '';
  $('taskModalOverlay').classList.remove('hidden');
  $('taskModalTitle').focus();
}

function _closeTaskModal() { $('taskModalOverlay').classList.add('hidden'); }

async function _saveTask() {
  const title = $('taskModalTitle').value.trim();
  if (!title) { alert('请输入任务标题'); return; }
  const cf = window.parent?._cloudFetch || window._cloudFetch;
  if (!cf) { alert('需要飞书登录才能创建任务'); return; }
  try {
    await cf('/api/tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title,
        list_gid:        'sim_eval',
        bop_version_gid: _selectedBopGid || null,
        task_type:       $('taskModalType').value,
        work_plan_gid:   $('taskModalWorkPlan').value.trim() || null,
      }),
    });
    _closeTaskModal();
    await _loadTasks();
  } catch(e) { alert('创建失败: ' + e.message); }
}

// ── VisMockup 结构树 ──────────────────────────────────────────────────────────

/**
 * 对选中 BOP 树节点的所有子 operation，按 sort_order 倒序执行：
 *   着蓝 → 截图 → 上传 → PATCH bop_steps.process_flow_pic → 隐藏 → 下一个
 * 参考：vis_tree_v7.py（每步严格串行，hide 无论成功与否必须执行）
 *
 * @param {string|null} overrideRootGid  由外部传入的 lineGid（assoc_panel 跨面板调用时使用）；
 *                                        为 null 时从 BOP 树 UI 选中状态读取
 * @param {Function|null} progressCb     每张截图上传成功后的回调 (op, uploadUrl) => void；
 *                                        assoc_panel 用此实现缩略图逐张飞入
 */
async function _captureOpSequence(overrideRootGid = null, progressCb = null) {
  if (!_vmConnected) { _cmdShow('请先连接 VisMockup', 'err'); return; }

  // 1. 获取 BOP 树选中节点 gid（优先使用外部传入的 overrideRootGid）
  let rootGid = overrideRootGid;
  if (!rootGid) {
    const activeRow = $('bopTreeBody')?.querySelector('.cs-bop-node.active')
                          ?.closest('.cs-bop-row');
    rootGid = activeRow?.dataset?.gid;
    if (!rootGid) { _cmdShow('请在 BOP 树中选中一个节点（线体/工位）', 'warn'); return; }
  }
  if (!_bopEntryIndex || !_bopEntryIndex[rootGid]) {
    _cmdShow('BOP 数据未加载，请先在数模仿真面板加载 BOP', 'warn'); return;
  }

  // 2. 递归收集所有 operation 子条目 + catia_names
  const ops = [];
  const _collect = gid => {
    const entry = _bopEntryIndex[gid];
    if (!entry) return;
    if (entry.node_type === 'operation') {
      const names = new Set();
      for (const p of (entry.parts || [])) { if (p.catia_occ) names.add(p.catia_occ); }
      for (const child of (_bopChildMap[gid] || [])) {
        if (child.node_type === 'part') {
          for (const p of (child.parts || [])) { if (p.catia_occ) names.add(p.catia_occ); }
        }
      }
      ops.push({ bop_entry_gid: gid, sort_order: entry.sort_order ?? 0, catia_names: [...names] });
    }
    for (const child of (_bopChildMap[gid] || [])) _collect(child.gid);
  };
  _collect(rootGid);

  // 3. sort_order 倒序（最后装的最先拆）
  ops.sort((a, b) => (b.sort_order ?? 0) - (a.sort_order ?? 0));
  const opsWithParts = ops.filter(o => o.catia_names.length > 0);
  if (!opsWithParts.length) { _cmdShow('选中节点下无已关联零件的工序', 'warn'); return; }

  _cmdShow(`开始截图（${opsWithParts.length} 个工序）…`);

  // 4. 确保 catia_map 已扫描
  if (!_catiaScanDone) {
    const sr = await _bridge('vis_mockup', 'scan_vis_catia_map');
    if (sr?.success) { _catiaScanDone = true; _refreshVmMatchCounts(); }
    else { _cmdShow('catia_map 扫描失败，请先点"扫描映射"', 'err'); return; }
  }

  const cf   = window.parent?._cloudFetch || window._cloudFetch;
  const eAPI = window.electronAPI || window.parent?.electronAPI;
  if (!cf) { _cmdShow('cloudFetch 不可用', 'err'); return; }

  // 5. 准备视图：只显示本线体所有工序的零件，隐藏其余
  const allNames = new Set();
  for (const op of opsWithParts) op.catia_names.forEach(n => allNames.add(n));
  _cmdShow('正在隔离线体零件视图…');
  const prepRes = await _bridge('vis_mockup', 'prepare_line_view', [...allNames]);
  if (!prepRes?.success) {
    _cmdShow(`视图准备失败: ${prepRes?.error || '未知'}`, 'err');
    return;
  }
  _cmdShow(`视图就绪（显示 ${prepRes.data?.shown ?? 0} 个节点，隐藏 ${prepRes.data?.hidden ?? 0} 个）`);

  let saved = 0;

  // 6. 严格串行：着蓝 → 截图 → 上传 → PATCH → 隐藏 → 下一个
  for (let i = 0; i < opsWithParts.length; i++) {
    const op = opsWithParts[i];
    _cmdShow(`[${i + 1}/${opsWithParts.length}] 处理 ${op.bop_entry_gid.slice(-8)}…`);
    (window.top || window.parent)?._showCaptureProgress?.(`工序截图 [${i + 1}/${opsWithParts.length}] ${_bopEntryIndex?.[op.bop_entry_gid]?.title || op.bop_entry_gid.slice(-8)}…`);

    // a. 当前工序着蓝 + 截图（灰色已在 prepare_line_view 一次性完成，此处不重置）
    const capRes = await _bridge('vis_mockup', 'color_and_screenshot_op',
                                 op.bop_entry_gid, op.catia_names);
    // debug 信息输出到 F12 console
    if (capRes?.data?.debug) {
      console.log(`[capOp ${op.bop_entry_gid.slice(-8)}]`, capRes.data.debug.join(' | '));
    } else {
      console.log(`[capOp ${op.bop_entry_gid.slice(-8)}] raw:`, JSON.stringify(capRes));
    }
    if (capRes?.success && capRes.data?.screenshot_path) {
      // b. 上传
      try {
        const b64 = await eAPI?.readFileBase64(capRes.data.screenshot_path);
        if (b64) {
          const filename  = capRes.data.screenshot_path.split(/[\\/]/).pop();
          const uploadRes = await cf('/api/bop/pics/upload', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename, mime: 'image/png', data_b64: b64 }),
          });
          if (uploadRes?.url) {
            const picItem = {
              url: uploadRes.url,
              object_key: uploadRes.object_key || '',
              storage: uploadRes.storage || '',
            };
            // c. PATCH → 写入 bop_entries.process_flow_pic
            await cf(`/api/bop/entries/${op.bop_entry_gid}`, {
              method: 'PATCH',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ process_flow_pic: [picItem] }),
            });
            saved++;
          _cmdShow(`  [${i + 1}] 已保存`);
          // 实时进度回调：通知 assoc_panel 追加缩略图（每张上传完立刻飞入）
          progressCb?.({ bop_entry_gid: op.bop_entry_gid,
                          title: _bopEntryIndex?.[op.bop_entry_gid]?.title || '' },
                        uploadRes.url);
          } else {
            _cmdShow(`  [${i + 1}] 上传返回无 URL`, 'warn');
          }
        } else {
          _cmdShow(`  [${i + 1}] 读取截图失败（eAPI=${!!eAPI}）`, 'warn');
        }
      } catch (e) {
        _cmdShow(`  [${i + 1}] 上传/保存出错: ${e?.message || e}`, 'warn');
        console.error('[截图上传]', op.bop_entry_gid, e);
      }
    } else {
      _cmdShow(`  [${i + 1}] 截图失败: ${capRes?.error || '未知'}`, 'warn');
    }

    // d. 隐藏（无论截图/上传是否成功，都必须隐藏）
    const hideRes = await _bridge('vis_mockup', 'hide_op', op.bop_entry_gid, op.catia_names);
    console.log(`[hideOp ${op.bop_entry_gid.slice(-8)}]`, JSON.stringify(hideRes?.data || hideRes));
  }

  _cmdShow(`截图完成：${saved}/${opsWithParts.length} 个工序已保存`, 'ok');
  (window.top || window.parent)?._showCaptureProgress?.(`截图完成 ${saved}/${opsWithParts.length} ✓`);
}

function _bindVisPanel() {
  // force=true：强制重新遍历（忽略缓存）
  $('btnRefreshVisTree')?.addEventListener('click', () => _loadVisTree(true));
  $('btnScanCatiaMap')?.addEventListener('click', async () => {
    if (!_vmConnected) { _cmdShow('未连接 VisMockup', 'err'); return; }
    _cmdShow('扫描中…');
    const r = await _bridge('vis_mockup', 'scan_vis_catia_map');
    if (r?.success) {
      _catiaScanDone = true;
      _cmdShow(`扫描完成：${r.data.count} 个映射节点`, 'ok');
      _refreshVmMatchCounts();
    } else {
      _cmdShow(r?.error || '扫描失败', 'err');
    }
  });
  $('btnCaptureOps')?.addEventListener('click', _captureOpSequence);

  // 跨面板入口：assoc_panel 通过 window.top._cadSimCapture(lineGid, progressCb) 触发
  // 注意：lineage_view 可能嵌套在 craft_hub 内，window.parent 不是 workspace，需用 window.top
  const _topWin = window.top || window.parent || window;
  _topWin._cadSimCapture = (lineGid, progressCb) =>
    _captureOpSequence(lineGid, progressCb);
}

async function _loadVisTree(force = false) {
  if (!_vmConnected) {
    $('visTreeEmpty').textContent = '请先连接 VisMockup';
    $('visTreeEmpty').classList.remove('hidden');
    return;
  }

  // force=true 时重建 DOM；force=false 且已加载过则跳过（防止重复渲染）
  if (!force && _visTreeLoaded) return;

  $('visTreeLoading').classList.remove('hidden');
  $('visTreeEmpty').classList.add('hidden');
  if (force) {
    $('visTreeBody').innerHTML = '';
    _visNodeMap = {};
    _visExpandedKeys.clear();
    _visTreeLoaded = false;
  }

  // 提示整车数模首次遍历耗时较长
  if (force) {
    const loadingEl = $('visTreeLoading');
    if (loadingEl) loadingEl.title = '整车数模首次遍历可能需要数分钟，请耐心等待';
  }

  const r = await _bridge('vis_mockup', 'get_vis_tree', { max_depth: 1, force: !!force });
  $('visTreeLoading').classList.add('hidden');

  // ── DEBUG: 打印原始树数据，排查节点截断问题 ──────────────────────────────────
  console.group('[AI00] get_vis_tree raw response');
  console.log('success:', r?.success, ' cached:', r?.data?.cached);
  if (r?.data?.tree) {
    const t = r.data.tree;
    console.log('virtual_root.name:', t.name, ' children.length:', t.children?.length);
    (t.children || []).forEach((sec, si) => {
      console.log(`  section[${si}] name="${sec.name}" _synthetic=${sec._synthetic} children.length=${sec.children?.length}`);
      (sec.children || []).slice(0, 5).forEach((ch, ci) => {
        console.log(`    child[${ci}] name="${ch.name}" key=${ch.key} nc=${ch.children?.length}`);
      });
      if ((sec.children?.length || 0) > 5)
        console.log(`    ... (${sec.children.length - 5} more not shown)`);
    });
  } else {
    console.log('tree is null/undefined, error:', r?.error);
  }
  console.groupEnd();
  // ────────────────────────────────────────────────────────────────────────────

  // Backend 返回 r.data.tree = av.RootNode（VisMockup 内部虚拟根，不显示）
  // 其 children 是实际的顶层产品组件，支持多个根节点
  if (!r?.success || !r.data?.tree) {
    $('visTreeEmpty').textContent = r?.error || '加载失败，请确认 VisMockup 已打开文件';
    $('visTreeEmpty').classList.remove('hidden');
    return;
  }

  $('visTreeEmpty').classList.add('hidden');
  const virtualRoot = r.data.tree;
  const roots = virtualRoot.children || [];

  if (roots.length === 0 && !virtualRoot.has_more) {
    $('visTreeEmpty').textContent = '结构树为空';
    $('visTreeEmpty').classList.remove('hidden');
    return;
  }

  // 清空（非 force 时可能已有内容，但走到这里代表 force=true 或首次）
  if (!force) $('visTreeBody').innerHTML = '';
  const frag = document.createDocumentFragment();
  roots.forEach(rootNode => frag.appendChild(_buildVisNodeEl(rootNode, 0)));
  // 若 virtualRoot.has_more（深度限制导致根级子节点未完全加载，理论上极少发生）
  if (virtualRoot.has_more) {
    const moreRow = document.createElement('div');
    moreRow.className = 'cs-vis-more-row';
    moreRow.style.paddingLeft = '22px';
    moreRow.textContent = '⋯ 部分根节点未加载，点击强制刷新';
    moreRow.addEventListener('click', () => _loadVisTree(true));
    frag.appendChild(moreRow);
  }
  $('visTreeBody').appendChild(frag);
  _visTreeLoaded = true;

  // 顶层节点默认展开（模型 section 展开，AH section 视内容而定）
  roots.forEach(rootNode => {
    if (!rootNode._synthetic) return;
    const entry = _visNodeMap[rootNode.name + '__section__'];
    if (!entry) return;
    const row = entry.nodeEl.parentElement;
    if (!row) return;
    const childWrap = row.querySelector('.cs-vis-children');
    const toggle    = entry.nodeEl.querySelector('.cs-vis-toggle');
    if (childWrap && (childWrap.children.length > 0 || rootNode.name === '模型')) {
      childWrap.style.display = '';
      if (toggle) toggle.textContent = '▼';
    }
  });

  if (r.data.cached) {
    _cmdShow('结构树已从缓存加载', 'ok');
  }
}

/** 构建 AI00 合成分区节点（模型 / 备选层次结构）*/
function _buildVisSectionEl(node) {
  const section = document.createElement('div');
  section.className = 'cs-vis-section';

  // ── 分区标题行 ──
  const hdr = document.createElement('div');
  hdr.className = 'cs-vis-section-hdr';

  const toggle = document.createElement('span');
  toggle.className = 'cs-vis-toggle';
  toggle.textContent = '▶';
  hdr.appendChild(toggle);

  const label = document.createElement('span');
  label.className = 'cs-vis-section-label';
  label.textContent = node.name;
  hdr.appendChild(label);

  // 子节点计数徽标
  const cnt = node.children?.length || 0;
  const badge = document.createElement('span');
  badge.className = 'cs-vis-section-count';
  badge.textContent = cnt > 0 ? cnt : (node.name === '备选层次结构' ? '空' : '0');
  badge.title = cnt > 0 ? `${cnt} 个节点` : (node.name === '备选层次结构' ? '暂无备选层次结构（BOP 数据将在此显示）' : '');
  hdr.appendChild(badge);

  section.appendChild(hdr);

  // ── 子节点容器 ──
  const childWrap = document.createElement('div');
  childWrap.className = 'cs-vis-children';
  childWrap.style.display = 'none';

  if (cnt > 0) {
    node.children.forEach(child => childWrap.appendChild(_buildVisNodeEl(child, 1)));
  } else if (node.name === '备选层次结构') {
    const placeholder = document.createElement('div');
    placeholder.className = 'cs-vis-section-empty';
    placeholder.textContent = '暂无备选层次结构';
    childWrap.appendChild(placeholder);
  }
  section.appendChild(childWrap);

  // ── 折叠 / 展开 ──
  hdr.addEventListener('click', () => {
    const isOpen = childWrap.style.display !== 'none';
    childWrap.style.display = isOpen ? 'none' : '';
    toggle.textContent = isOpen ? '▶' : '▼';
  });

  // 存入 _visNodeMap 以便 default-expand 代码查找
  _visNodeMap[node.name + '__section__'] = { node, nodeEl: hdr, eyeEl: null };

  return section;
}

/** 构建一个节点 DOM 元素（含子节点容器）*/
function _buildVisNodeEl(node, depth) {
  // 合成分区节点（模型 / 备选层次结构）：渲染为可折叠分区标题
  if (node._synthetic) {
    return _buildVisSectionEl(node);
  }

  const row = document.createElement('div');
  row.className = 'cs-vis-row';
  row.dataset.key   = node.key || '';
  row.dataset.depth = depth;

  const hasChildren = node.children?.length > 0 || node.has_more;
  const indent = depth * 16 + 6;

  // ── 节点行 ──
  const nodeEl = document.createElement('div');
  nodeEl.className = 'cs-vis-node' + (node.visible ? '' : ' cs-vis-hidden');
  nodeEl.style.paddingLeft = indent + 'px';

  // toggle arrow
  const toggle = document.createElement('span');
  toggle.className = 'cs-vis-toggle' + (hasChildren ? '' : ' cs-vis-leaf');
  toggle.textContent = hasChildren ? '▶' : '·';
  nodeEl.appendChild(toggle);

  // eye icon
  const eyeEl = document.createElement('span');
  eyeEl.className = 'cs-vis-eye';
  eyeEl.innerHTML = node.visible ? _eyeOpenSvg() : _eyeOffSvg();
  eyeEl.title = node.visible ? '点击隐藏' : '点击显示';
  eyeEl.addEventListener('click', e => {
    e.stopPropagation();
    if (node.key) _visNodeAction(node.key, 'toggle_visible');
  });
  nodeEl.appendChild(eyeEl);

  // label
  const label = document.createElement('span');
  label.className = 'cs-vis-label';
  label.textContent = node.name;
  label.title = node.catia_name ? `${node.name}\n${node.catia_name}` : node.name;
  nodeEl.appendChild(label);

  // catia occurrence name (secondary line)
  if (node.catia_name) {
    const sub = document.createElement('span');
    sub.className = 'cs-vis-catia';
    sub.textContent = node.catia_name;
    nodeEl.appendChild(sub);
  }

  row.appendChild(nodeEl);

  // ── 子节点容器 ──
  const childWrap = document.createElement('div');
  childWrap.className = 'cs-vis-children';
  childWrap.style.display = 'none';

  // pre-populate already-loaded children
  if (node.children?.length > 0) {
    node.children.forEach(child => childWrap.appendChild(_buildVisNodeEl(child, depth + 1)));
  }
  if (node.has_more) {
    childWrap.appendChild(_makeVisMoreRow(node.key, depth + 1));
  }
  row.appendChild(childWrap);

  // ── 事件：展开/折叠 ──
  if (hasChildren) {
    toggle.addEventListener('click', e => {
      e.stopPropagation();
      _toggleVisExpand(node, depth, toggle, childWrap);
    });
    nodeEl.addEventListener('dblclick', e => {
      e.stopPropagation();
      _toggleVisExpand(node, depth, toggle, childWrap);
    });
  }

  // ── 事件：单击高亮 ──
  nodeEl.addEventListener('click', () => {
    $('visTreeBody').querySelectorAll('.cs-vis-node.cs-vis-active')
      .forEach(n => n.classList.remove('cs-vis-active'));
    nodeEl.classList.add('cs-vis-active');
    if (node.key) _visNodeAction(node.key, 'highlight');
    _showVisDetail(node);
  });

  // ── 事件：右键菜单 ──
  nodeEl.addEventListener('contextmenu', e => {
    e.preventDefault();
    _showVisCtxMenu(e, node);
  });

  // 存入 map 供后续更新
  if (node.key) _visNodeMap[node.key] = { node, nodeEl, eyeEl };

  return row;
}

/** 展开 / 折叠一个节点 */
async function _toggleVisExpand(node, depth, toggleEl, childWrap) {
  const isOpen = childWrap.style.display !== 'none';
  if (isOpen) {
    childWrap.style.display = 'none';
    toggleEl.textContent = '▶';
    _visExpandedKeys.delete(node.key);
    return;
  }

  // 展开
  childWrap.style.display = '';
  toggleEl.textContent = '▼';
  _visExpandedKeys.add(node.key);

  // 若子节点尚未加载，通过 bridge 惰性加载
  if (childWrap.children.length === 0 ||
      (childWrap.children.length === 1 && childWrap.firstChild?.classList?.contains('cs-vis-more-row'))) {
    const placeholder = document.createElement('div');
    placeholder.className = 'cs-vis-more-row';
    placeholder.style.paddingLeft = (depth + 1) * 16 + 22 + 'px';
    placeholder.textContent = '加载中…';
    childWrap.innerHTML = '';
    childWrap.appendChild(placeholder);

    const r = await _bridge('vis_mockup', 'get_vis_node_children', { node_key: node.key });
    childWrap.innerHTML = '';
    if (r?.success) {
      node.children = r.data.children || [];
      node.has_more = false;
      node.children.forEach(child => childWrap.appendChild(_buildVisNodeEl(child, depth + 1)));
    } else {
      const err = document.createElement('div');
      err.className = 'cs-vis-more-row';
      err.style.paddingLeft = (depth + 1) * 16 + 22 + 'px';
      err.textContent = '加载失败';
      childWrap.appendChild(err);
    }
  }
}

/** "展开更多" 占位行（depth limit 超出时） */
function _makeVisMoreRow(parentKey, depth) {
  const el = document.createElement('div');
  el.className = 'cs-vis-more-row';
  el.style.paddingLeft = depth * 16 + 22 + 'px';
  el.textContent = '⋯ 点击加载';
  el.addEventListener('click', async () => {
    el.textContent = '加载中…';
    const r = await _bridge('vis_mockup', 'get_vis_node_children', { node_key: parentKey });
    if (r?.success) {
      const parent = el.parentElement;
      el.remove();
      (r.data.children || []).forEach(child => parent.appendChild(_buildVisNodeEl(child, depth)));
    } else {
      el.textContent = '加载失败，点击重试';
    }
  });
  return el;
}

/** 调用 bridge 执行节点操作，并更新 eye 图标 */
async function _visNodeAction(nodeKey, action) {
  if (!nodeKey || !_vmConnected) return;
  const r = await _bridge('vis_mockup', 'vis_node_action', { node_key: nodeKey, action });
  if (!r?.success) {
    _cmdShow(r?.error || `${action} 失败`, 'err');
    return;
  }
  // 如果有可见性变化，更新 eye 图标
  if (r.data?.visible !== undefined) {
    const entry = _visNodeMap[nodeKey];
    if (entry) {
      const v = r.data.visible;
      entry.eyeEl.innerHTML = v ? _eyeOpenSvg() : _eyeOffSvg();
      entry.eyeEl.title = v ? '点击隐藏' : '点击显示';
      entry.nodeEl.classList.toggle('cs-vis-hidden', !v);
    }
  }
}

/** 右键上下文菜单 */
function _showVisCtxMenu(e, node) {
  _hideVisCtxMenu();
  const menu = document.createElement('div');
  menu.className = 'cs-ctx-menu';
  _visCtxMenu = menu;

  const items = [
    { label: '高亮',     action: 'highlight' },
    { label: '取消高亮', action: 'unhighlight' },
    { sep: true },
    { label: '显示',     action: 'show' },
    { label: '隐藏',     action: 'hide' },
    { label: '单独显示', action: 'isolate' },
    { sep: true },
    { label: '选中',     action: 'select' },
    { label: '取消选中', action: 'deselect' },
    { sep: true },
    { label: '加载此节点几何…', action: '_load_geometry' },
    { label: '查看元数据…', action: '_metadata' },
  ];

  items.forEach(it => {
    if (it.sep) {
      const sep = document.createElement('div');
      sep.className = 'cs-ctx-sep';
      menu.appendChild(sep);
    } else {
      const btn = document.createElement('div');
      btn.className = 'cs-ctx-item';
      btn.textContent = it.label;
      btn.addEventListener('click', () => {
        _hideVisCtxMenu();
        if (it.action === '_metadata') {
          _showNodeMetadata(node);
        } else if (it.action === '_load_geometry') {
          _loadNodeGeometry(node.key);
        } else if (node.key) {
          _visNodeAction(node.key, it.action);
        }
      });
      menu.appendChild(btn);
    }
  });

  document.body.appendChild(menu);
  const mx = Math.min(e.clientX, window.innerWidth  - menu.offsetWidth  - 8);
  const my = Math.min(e.clientY, window.innerHeight - menu.offsetHeight - 8);
  menu.style.left = mx + 'px';
  menu.style.top  = my + 'px';

  setTimeout(() => document.addEventListener('click', _hideVisCtxMenu, { once: true }), 0);
}

function _hideVisCtxMenu() {
  _visCtxMenu?.remove();
  _visCtxMenu = null;
}

/** 元数据弹窗：加载节点完整信息并分区展示 */
async function _showNodeMetadata(node) {
  if (!node.key) return;
  document.getElementById('visMetaPopup')?.remove();

  const overlay = document.createElement('div');
  overlay.id = 'visMetaPopup';
  overlay.className = 'cs-meta-overlay';
  overlay.innerHTML = `
    <div class="cs-meta-dialog">
      <div class="cs-meta-title">
        <span>${_esc(node.name)}</span>
        <button class="cs-meta-close" title="关闭">✕</button>
      </div>
      ${node.catia_name ? `<div class="cs-meta-catia">${_esc(node.catia_name)}</div>` : ''}
      <div class="cs-meta-body" id="visMetaBody">
        <span style="color:var(--text-muted);font-size:12px">加载中…</span>
      </div>
    </div>`;
  document.body.appendChild(overlay);
  overlay.querySelector('.cs-meta-close').addEventListener('click', () => overlay.remove());
  overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });

  const r = await _bridge('vis_mockup', 'get_node_metadata', { node_key: node.key });
  const body = document.getElementById('visMetaBody');
  if (!body) return;

  if (!r?.success) {
    body.innerHTML = `<span style="color:var(--red)">${_esc(r?.error || '获取失败')}</span>`;
    return;
  }

  const d = r.data;
  const sections = [];

  // ── 固定属性 ──
  const fixedKeys = ['PrintableName','Fullname','DataStoreName','DataStoreLocation','CADID','IsPart','IsLoaded'];
  const fixed = fixedKeys.filter(k => d[k] != null && d[k] !== '').map(k =>
    `<div class="cs-meta-row"><span class="cs-meta-key">${_esc(k)}</span><span class="cs-meta-val">${_esc(String(d[k]))}</span></div>`
  ).join('');
  if (fixed) sections.push(`<div class="cs-meta-section-hdr">节点属性</div>${fixed}`);

  // ── 变换矩阵 ──
  for (const [label, key] of [['全局变换矩阵','GlobalTransform'],['局部变换矩阵','LocalTransform']]) {
    const m = d[key];
    if (!m) continue;
    if (typeof m === 'string') {
      sections.push(`<div class="cs-meta-section-hdr">${label}</div>
        <div class="cs-meta-row"><span class="cs-meta-key">状态</span><span class="cs-meta-val">${_esc(m)}</span></div>`);
    } else if (Array.isArray(m) && m.length >= 12) {
      // 格式化为 4×4 矩阵
      const fmt = n => (typeof n === 'number' ? n.toFixed(6) : String(n)).padStart(14);
      const rows = [0,4,8,12].map(i =>
        `<span class="cs-mat-row">${[0,1,2,3].map(j => fmt(m[i+j])).join('  ')}</span>`
      ).join('\n');
      // 平移向量单独标注
      const tx = m[12], ty = m[13], tz = m[14];
      sections.push(`<div class="cs-meta-section-hdr">${label}</div>
        <div class="cs-meta-matrix">${rows}</div>
        <div class="cs-meta-row" style="margin-top:4px">
          <span class="cs-meta-key">平移 (x,y,z)</span>
          <span class="cs-meta-val">${typeof tx==='number'?tx.toFixed(4):tx},  ${typeof ty==='number'?ty.toFixed(4):ty},  ${typeof tz==='number'?tz.toFixed(4):tz}</span>
        </div>`);
    }
  }

  // ── PLM 元数据（MetaDataProperties）──
  const meta = d['_metadata'] || {};
  const metaKeys = Object.keys(meta).sort((a, b) => {
    const pri = ['catiaoccurrencename','__PLM_INST_UID','__PLM_CLONE_STABLE_INST_UID','__PLM_INST_TH_UID'];
    const ia = pri.indexOf(a), ib = pri.indexOf(b);
    if (ia >= 0 && ib >= 0) return ia - ib;
    if (ia >= 0) return -1;
    if (ib >= 0) return 1;
    return a.localeCompare(b);
  });
  if (metaKeys.length > 0) {
    const rows = metaKeys.map(k =>
      `<div class="cs-meta-row"><span class="cs-meta-key">${_esc(k)}</span><span class="cs-meta-val">${_esc(meta[k])}</span></div>`
    ).join('');
    sections.push(`<div class="cs-meta-section-hdr">MetaDataProperties (${metaKeys.length})</div>${rows}`);
  }

  // ── 几何数据（按需加载，避免自动触发 JT shape 载入）──
  const geoId = `visGeo_${(node.key || 'x').replace(/[^a-z0-9]/gi, '_')}`;
  sections.push(`<div class="cs-meta-section-hdr">几何数据（JT Shape）</div>
    <div id="${geoId}">
      <div class="cs-meta-row" style="gap:8px">
        <button class="cs-btn cs-btn-xs" onclick="window._loadNodeGeoInline('${node.key}','${geoId}')">加载几何数据</button>
        <span style="font-size:11px;color:var(--text-muted)">触发后 VisMockup 将载入该节点 JT shape</span>
      </div>
    </div>`);

  body.innerHTML = sections.length
    ? sections.join('')
    : `<span style="color:var(--text-muted);font-size:12px">暂无可读数据</span>`;
}

/** 全量同步显隐状态（全显/全隐命令后批量更新 eye 图标）*/
function _syncAllVisibility(visible) {
  for (const [key, entry] of Object.entries(_visNodeMap)) {
    if (!entry.eyeEl) continue;  // 合成分区节点无 eye 图标，跳过
    entry.eyeEl.innerHTML = visible ? _eyeOpenSvg() : _eyeOffSvg();
    entry.eyeEl.title = visible ? '点击隐藏' : '点击显示';
    entry.nodeEl.classList.toggle('cs-vis-hidden', !visible);
    if (entry.node) entry.node.visible = visible;
  }
}

// SVG helpers
function _eyeOpenSvg() {
  return `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>`;
}
function _eyeOffSvg() {
  return `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>`;
}

// ── utils ─────────────────────────────────────────────────────────────────────

/** 后台触发 catia 全树扫描，静默完成（不阻塞 UI） */
async function _scanCatiaMap() {
  if (!_vmConnected) return;
  const r = await _bridge('vis_mockup', 'scan_vis_catia_map');
  if (r?.success) {
    _catiaScanDone = true;
    _cmdShow(`VM 扫描完成：${r.data.count} 个零件节点`, 'ok');
    _refreshVmMatchCounts();
  }
}

/** 单节点几何加载：显示在 cmdResult 条 */
async function _loadNodeGeometry(nodeKey) {
  if (!nodeKey || !_vmConnected) { _cmdShow('未连接 VisMockup', 'err'); return; }
  _cmdShow('加载节点几何中…');
  const r = await _bridge('vis_mockup', 'get_node_geometry', { node_key: nodeKey });
  if (!r?.success) { _cmdShow(r?.error || '加载失败', 'err'); return; }
  const d = r.data;
  const parts = [];
  if (d.bbox && typeof d.bbox === 'object' && d.bbox.min) {
    const fv = v => Array.isArray(v) ? v.map(n => typeof n === 'number' ? n.toFixed(3) : n).join(', ') : String(v);
    parts.push(`BBox [${fv(d.bbox.min)}]~[${fv(d.bbox.max)}]`);
  }
  if (d.area   != null) parts.push(`面积:${d.area.toFixed(4)}`);
  if (d.volume != null) parts.push(`体积:${d.volume.toFixed(4)}`);
  _cmdShow(parts.join(' | ') || '已加载（无几何数据）', 'ok');
}

/** 元数据弹窗内按需加载几何数据区块 */
window._loadNodeGeoInline = async (nodeKey, sectionId) => {
  const el = document.getElementById(sectionId);
  if (!el) return;
  el.innerHTML = '<div class="cs-meta-row" style="color:var(--text-muted);font-size:12px">加载中…</div>';
  const r = await _bridge('vis_mockup', 'get_node_geometry', { node_key: nodeKey });
  if (!r?.success) {
    el.innerHTML = `<div class="cs-meta-row"><span style="color:var(--red)">${_esc(r?.error || '加载失败')}</span></div>`;
    return;
  }
  const d = r.data;
  const rows = [];
  if (d.bbox && typeof d.bbox === 'object' && d.bbox.min) {
    const fv = v => Array.isArray(v) ? v.map(n => typeof n === 'number' ? n.toFixed(4) : n).join(', ') : String(v);
    rows.push(`<div class="cs-meta-row"><span class="cs-meta-key">BBox Min</span><span class="cs-meta-val">${_esc(fv(d.bbox.min))}</span></div>`);
    rows.push(`<div class="cs-meta-row"><span class="cs-meta-key">BBox Max</span><span class="cs-meta-val">${_esc(fv(d.bbox.max))}</span></div>`);
  } else if (d.bbox) {
    rows.push(`<div class="cs-meta-row"><span class="cs-meta-key">BBox</span><span class="cs-meta-val">${_esc(String(d.bbox))}</span></div>`);
  }
  if (d.area   != null) rows.push(`<div class="cs-meta-row"><span class="cs-meta-key">面积</span><span class="cs-meta-val">${d.area.toFixed(6)}</span></div>`);
  if (d.volume != null) rows.push(`<div class="cs-meta-row"><span class="cs-meta-key">体积</span><span class="cs-meta-val">${d.volume.toFixed(6)}</span></div>`);
  el.innerHTML = rows.length
    ? rows.join('')
    : '<div class="cs-meta-row" style="color:var(--text-muted);font-size:12px">暂无几何数据</div>';
};

function _esc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

window.addEventListener('message', e => {
  if (e.data?.type === 'theme')
    document.documentElement.setAttribute('data-theme', e.data.theme || 'dark');
});

document.addEventListener('DOMContentLoaded', init);
