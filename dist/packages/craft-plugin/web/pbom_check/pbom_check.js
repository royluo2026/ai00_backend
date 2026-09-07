'use strict';
/**
 * pbom_check.js — PBOM VPPS 核对独立窗口
 *
 * 左侧用 TreeListShell 展示 PBOM 零件（与 ebom 页面相同的列定义）。
 * 右侧展示 VPPS 核对结果（调后端 /api/ebom/vpps_check，服务端跑规则）。
 * 不重复规则逻辑，只做 UI 展示和 ignore/revert 操作。
 */

/* ── URL 参数 ─────────────────────────────────────────────── */
const _p       = new URLSearchParams(location.search);
const _initGid = _p.get('pbom_gid') || '';

function _cf(method, path, opts = {}) {
  const fn = window.parent?._cloudFetch || window._cloudFetch;
  if (!fn) return Promise.resolve(null);
  return fn(path, { ...opts, method }).catch(err => { console.warn('[PBOM check] fetch error', err); return null; });
}

async function _invokeCapability(id, payload) {
  const response = await _cf('POST', `/api/v1/capabilities/${id}:invoke`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ version: 1, payload }),
  });
  const result = response?.data;
  if (response?.success !== true || result?.ok !== true) throw new Error(`能力调用失败：${id}@1`);
  const value = result.data;
  return value?.data?.success !== undefined ? value.data : value;
}

/* ── 主题同步 ────────────────────────────────────────────── */
try {
  const t = window.parent?.document?.documentElement?.getAttribute('data-theme');
  if (t) document.documentElement.setAttribute('data-theme', t);
} catch (_) {}
window.addEventListener('message', e => {
  if (e.data?.type === 'theme')
    document.documentElement.setAttribute('data-theme', e.data.theme);
});

/* ── 列定义（与 ebom.js 保持一致）──────────────────────────── */
const PBOM_FULL_COLS = [
  { key: 'home',                  label: 'Home',         type: 'text',   width: 60  },
  { key: 'level',                 label: 'Level',        type: 'number', width: 46  },
  { key: 'vpps',                  label: 'VPPS',         type: 'text',   width: 130 },
  { key: 'vpps_desc',             label: 'VPPS描述',     type: 'text',   width: 160 },
  { key: 'parent_vpps',           label: '父级VPPS',     type: 'text',   width: 120 },
  { key: 'component_id',          label: '零组件ID',     type: 'text',   width: 130 },
  { key: 'name',                  label: '零组件名称',   type: 'text',   width: 200 },
  { key: 'quantity',              label: '数量',         type: 'number', width: 56  },
  { key: 'component_type',        label: '零组件类型',   type: 'text',   width: 100 },
  { key: 'bom_row',               label: 'BOM行',        type: 'text',   width: 110 },
  { key: 'parent_bom_row',        label: '父级BOM行',    type: 'text',   width: 110 },
  { key: 'torque',                label: '扭矩',         type: 'text',   width: 70  },
  { key: 'geo_main_part',         label: '几何推测主件', type: 'text',   width: 160 },
  { key: 'main_part_consistency', label: '主件一致性',   type: 'text',   width: 100 },
  { key: '_nok',                  label: '核对',         type: 'text',   width: 60  },
];

const PBOM_DEFAULT_COLS = ['name', 'component_id', 'quantity', 'component_type', 'vpps', 'vpps_desc', '_nok']
  .map(k => PBOM_FULL_COLS.find(c => c.key === k)).filter(Boolean);

const _DETAIL_KEYS = [
  { key: 'component_id',   label: '零组件ID' },
  { key: 'name',           label: '名称' },
  { key: 'vpps',           label: 'VPPS' },
  { key: 'vpps_desc',      label: 'VPPS描述' },
  { key: 'parent_vpps',    label: '父级VPPS' },
  { key: 'level',          label: '层级' },
  { key: 'quantity',       label: '数量' },
  { key: 'bom_row',        label: 'BOM行' },
  { key: 'component_type', label: '零组件类型' },
  { key: 'torque',         label: '扭矩' },
  { key: 'geo_main_part',  label: '几何推测主件' },
  { key: 'main_part_consistency', label: '主件一致性' },
];

/* ── 状态 ────────────────────────────────────────────────── */
let _tls          = null;   // TreeListShell 实例
let _versions     = [];
let _parts        = [];
let _nokMap       = new Map();   // gid → [errors]
let _ignoredGids  = new Set();   // rule4 已忽略 gid
let _checkResult  = null;
let _groupActive  = false;

/* ── DOM ─────────────────────────────────────────────────── */
const $verSel     = document.getElementById('pcVerSel');
const $status     = document.getElementById('pcStatus');
const $resultBody = document.getElementById('pcResultBody');

/* ── 初始化 ─────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', async () => {
  await _loadVersions();
  _initTLS();
  $verSel.addEventListener('change', () => _onVerChange($verSel.value));
});

/* ── 版本列表 ────────────────────────────────────────────── */
async function _loadVersions() {
  const _cloudFetch = window._cloudFetch?.bind(window);
  try {
    _setStatus('加载版本…');
    const res = await _cloudFetch('/api/ebom/snapshots', { method: 'GET' });
    _versions = res?.data || [];
    $verSel.innerHTML = '<option value="">— 选择 PBOM 版本 —</option>' +
      _versions.map(v =>
        `<option value="${v.gid}">${v.name || v.version_tag || v.gid.slice(-8)}</option>`
      ).join('');
    _setStatus('');
  } catch (e) {
    _setStatus('版本加载失败: ' + e.message, true);
  }
}

/* ── 版本切换 ────────────────────────────────────────────── */
async function _onVerChange(gid) {
  if (!gid) {
    _parts = []; _nokMap.clear(); _ignoredGids.clear(); _checkResult = null;
    $resultBody.innerHTML = '<div class="pc-empty">点击工具栏"VPPS 核对"开始检查</div>';
    _setStatus('');
    return;
  }
  // 通知 TLS 切换版本（会触发 onLoadData）
  await _tls?.setSelectedList(gid);
}

/* ── TreeListShell 初始化 ─────────────────────────────────── */
function _initTLS() {
  const _cloudFetch = window._cloudFetch?.bind(window);
  const mountEl = document.getElementById('pcTlsMount');

  _tls = new TreeListShell({
    mountEl,
    title:          'PBOM',
    forcedItemType: 'pbom',
    itemTypes:      [{ value: 'pbom', label: 'PBOM' }],
    columns:        PBOM_DEFAULT_COLS,
    allColumns:     PBOM_FULL_COLS,
    priorityKeys:   ['name', 'component_id', 'quantity', 'component_type', 'vpps', 'vpps_desc', '_nok'],
    parentField:    'parent_bom_row',
    groupField:     'component_type',
    detailMode:     'readonly',
    detailFields:   _DETAIL_KEYS,
    moduleId:       'pbom_check',
    showListSelector: false,
    compactToolbar: false,

    // 版本列表（下拉由顶部 select 控制，TLS 不自己加载）
    onLoadLists: async () => _versions.map(v => ({
      gid:  v.gid,
      name: v.name || v.version_tag || v.gid.slice(-8),
    })),
    onLoadData: async (_type, listGid) => {
      if (!listGid) return [];
      // 同步顶部 select
      if ($verSel.value !== listGid) $verSel.value = listGid;
      try {
        const res = await _cloudFetch(`/api/ebom/snapshots/${listGid}/parts`, { method: 'GET' });
        _parts = res?.data || [];
        // 切换版本时清空上次核对结果
        _nokMap.clear(); _ignoredGids.clear(); _checkResult = null;
        $resultBody.innerHTML = '<div class="pc-empty">点击工具栏"VPPS 核对"开始检查</div>';
        _setStatus(`${_parts.length} 条零件`);
        return _parts;
      } catch (e) {
        _setStatus('零件加载失败: ' + e.message, true);
        return [];
      }
    },

    // _nok 列自定义渲染
    cellRenderer: {
      _nok: (row) => {
        const gid  = row.gid || '';
        const errs = _nokMap.get(gid) || [];
        const ign  = _ignoredGids.has(gid);
        if (ign)         return `<span class="pc-nok-cell"><span class="pc-dot pc-dot-ign" title="已忽略"></span></span>`;
        if (!errs.length) return '';
        return `<span class="pc-nok-cell">${[...new Set(errs.map(e => e.rule))].map(r =>
          `<span class="pc-dot pc-dot-r${r}" title="规则${r}"></span>`
        ).join('')}</span>`;
      },
    },

    // 工具栏额外按钮
    extraToolbarBtns: [
      {
        html: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg><span class="feat-label">VPPS核对</span>',
        title: 'VPPS 核对（四条规则）',
        active: false,
        onClick: _runCheck,
      },
      {
        html: '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M12 2v4m0 12v4m-7.07-3.93l2.83-2.83m8.48-8.48l2.83-2.83M2 12h4m12 0h4m-3.93 7.07l-2.83-2.83M6.76 6.76L3.93 3.93"/></svg><span class="feat-label">紧固件分组</span>',
        title: '按紧固件几何主件分组',
        active: false,
        onClick: function() {
          _groupActive = !_groupActive;
          this.active = _groupActive;
          _tls?.updateExtraButtons(_tls?._extraToolbarBtns);
          if (_groupActive) {
            _tls?.vm?.setGroup('geo_main_part');
          } else {
            _tls?.vm?.setGroup(null);
          }
        },
      },
    ],
  });

  _tls.init().then(async () => {
    // 如有 URL 参数预选版本
    if (_initGid && _versions.some(v => v.gid === _initGid)) {
      await _tls.setSelectedList(_initGid);
    }
  });
}

/* ── VPPS 核对 ───────────────────────────────────────────── */
async function _runCheck() {
  const _cloudFetch = window._cloudFetch?.bind(window);
  const gid = _tls?.getSelectedList() || $verSel.value;
  if (!gid) { alert('请先选择 PBOM 版本'); return; }

  _setStatus('核对中…');
  $resultBody.innerHTML = '<div class="pc-empty">核对中，请稍候…</div>';

  try {
    const [checkRes, ignRes] = await Promise.all([
      _cloudFetch(`/api/ebom/vpps_check?snapshot_gid=${encodeURIComponent(gid)}`, { method: 'GET' }),
      _cloudFetch(`/api/vpps-operations/rule4-ignores?pbom_version_gid=${encodeURIComponent(gid)}`, { method: 'GET' }).catch(() => null),
    ]);

    _checkResult  = checkRes;
    _ignoredGids  = new Set(ignRes?.ignored_row_gids || []);
    _nokMap.clear();

    // 建立 gid → errors 映射（后端错误含 row index 和 vpps）
    const allErrors = [
      ...(checkRes.errors?.rule1 || []),
      ...(checkRes.errors?.rule2 || []),
      ...(checkRes.errors?.rule3 || []),
      ...(checkRes.errors?.rule4 || []),
    ];
    for (const e of allErrors) {
      // 优先用 row（1-based index），再用 vpps 匹配
      let part = null;
      if (e.row) part = _parts[e.row - 1];
      if (!part && e.vpps) part = _parts.find(p => p.vpps === e.vpps);
      if (part?.gid) {
        if (!_nokMap.has(part.gid)) _nokMap.set(part.gid, []);
        _nokMap.get(part.gid).push(e);
      }
    }

    // 刷新 TLS 行渲染（只重绘，不重新加载数据）
    _tls?._renderTree?.();

    // 核对后切换为 NOK 视图
    _showNokView();

    _renderResult(checkRes, ignRes);
    _saveStats(gid, checkRes);

    const s   = checkRes.summary;
    const nok = s.rule1_errors + s.rule2_errors + s.rule3_errors + s.rule4_errors;
    _setStatus(nok > 0
      ? `NOK ${nok} 条${s.rule4_ignored ? `（规则4已忽略 ${s.rule4_ignored}）` : ''}`
      : `✓ 全部通过（${_parts.length} 条）`);

  } catch (e) {
    $resultBody.innerHTML = `<div class="pc-empty" style="color:var(--red)">核对失败: ${_esc(e.message)}</div>`;
    _setStatus('核对失败', true);
  }
}

/* ── 结果面板渲染 ─────────────────────────────────────────── */
function _renderResult(res, ignRes) {
  const _cloudFetch = window._cloudFetch?.bind(window);
  const s      = res.summary;
  const ign    = s.rule4_ignored || 0;
  const r4Errs = res.errors?.rule4 || [];
  const ignOps = ignRes?.operations || [];
  const frag   = document.createDocumentFragment();

  // ── 汇总数字 ─────────────────────────────────────────────
  const summary = document.createElement('div');
  summary.className = 'pc-summary';
  [
    { num: s.rule1_errors, lbl: '规则1',    cls: s.rule1_errors ? 'nok'  : 'ok' },
    { num: s.rule3_errors, lbl: '规则3',    cls: s.rule3_errors ? 'warn' : 'ok' },
    { num: s.rule4_errors, lbl: '规则4',    cls: s.rule4_errors ? 'warn' : 'ok' },
    { num: ign,            lbl: 'R4已忽略', cls: ign ? 'ign' : 'ok' },
  ].forEach(({ num, lbl, cls }) => {
    const cell = document.createElement('div');
    cell.className = `pc-sum-cell ${cls}`;
    cell.innerHTML = `<div class="pc-sum-num">${num}</div><div class="pc-sum-lbl">${lbl}</div>`;
    summary.appendChild(cell);
  });
  frag.appendChild(summary);

  // ── 批量操作区 ────────────────────────────────────────────
  const actionsWrap = document.createElement('div');
  actionsWrap.className = 'pc-batch-wrap';

  // 1. 批量提交无主数据
  const noDataErrs = (res.errors?.rule1 || []).filter(e => e.msg?.includes('不存在'));
  if (noDataErrs.length) {
    _appendBatchSection(actionsWrap, {
      numA: noDataErrs.length, lblA: '无主数据',
      numB: s.rule1_errors - noDataErrs.length, lblB: '描述不符',
      hint: '写入后成为知识库主数据，可被后续版本核对复用',
      btnText: `批量提交无主数据（${noDataErrs.length} 条）`,
      btnCls: 'warn',
      onRun: async (btn) => {
        if (!confirm(`将 ${noDataErrs.length} 条无主数据 VPPS 写入 vpps_parts 知识库？`)) return false;
        const verGid = _tls?.getSelectedList() || $verSel.value;
        const ver    = _versions.find(v => v.gid === verGid);
        const entries = noDataErrs.map(e => {
          const part = _parts.find(p => p.vpps === e.vpps);
          return { vpps: e.vpps, vpps_desc_cn: part?.vpps_desc || '', vpps_description: part?.vpps_desc || '' };
        });
        const r = await _cloudFetch('/api/craft_lib/part_names/batch_add_from_pbom', {
          method: 'POST',
          body: JSON.stringify({
            entries,
            meta: { added_by: window._authUser?.name || '', project: ver?.name || '', added_at: new Date().toISOString() },
          }),
        });
        if (!r?.success) throw new Error(r?.detail || '提交失败');
        btn.textContent = `✓ 已添加 ${r.added} 条，跳过 ${r.skipped} 条`;
        return true;
      },
    });
  }

  // 2. 批量接受别名
  const aliases = res.alias_matches || [];
  if (aliases.length) {
    _appendBatchSection(actionsWrap, {
      numA: aliases.length, lblA: '待接受别名',
      numB: 0, lblB: '',
      hint: '别名接受后永久写入知识库，下次核对自动通过',
      btnText: `批量接受别名（${aliases.length} 条）`,
      btnCls: 'warn',
      onRun: async (btn) => {
        if (!confirm(`批量接受全部 ${aliases.length} 条描述别名？`)) return false;
        btn.textContent = '查询中…';
        const items = [];
        for (const a of aliases) {
          try {
            const r = await _cloudFetch(`/api/craft_lib/part_names?vpps=${encodeURIComponent(a.vpps)}`, { method: 'GET' });
            const pn = (r?.data || [])[0];
            if (pn?.gid) {
              const pbomPart = _parts.find(p => p.vpps === a.vpps);
              items.push({ vpps_part_gid: pn.gid, alias: a.desc, pbom_part_gid: pbomPart?.gid || '' });
            }
          } catch (_) {}
        }
        if (!items.length) throw new Error('未找到可处理的别名条目');
        const ver = _versions.find(v => v.gid === (_tls?.getSelectedList() || $verSel.value));
        const r = await _cloudFetch('/api/craft_lib/part_names/batch_accept_alias', {
          method: 'POST',
          body: JSON.stringify({ items, meta: { added_by: window._authUser?.name || '', project: ver?.name || '' } }),
        });
        if (!r?.success) throw new Error(r?.detail || '提交失败');
        btn.textContent = `✓ 已处理 ${r.processed} 条，失败 ${r.failed} 条`;
        return true;
      },
    });
  }

  // 3. 规则4 批量忽略 / 集中撤销
  if (r4Errs.length || ignOps.length) {
    _appendBatchSection(actionsWrap, {
      numA: r4Errs.length, lblA: '待忽略',
      numB: ignOps.length, lblB: '已忽略',
      hint: ignOps.length > 0
        ? `已忽略 ${ignOps.length} 条，可集中撤销或在核对表中逐条撤销`
        : '忽略后下次核对不再显示，可随时撤销',
      btnText: r4Errs.length ? `暂时忽略规则4（${r4Errs.length} 条）` : '规则4已全部忽略',
      btnCls: 'ignore',
      btnDisabled: r4Errs.length === 0,
      onRun: async () => {
        if (!confirm(`将当前 ${r4Errs.length} 条规则4 NOK 标记为已忽略？`)) return false;
        await _bulkIgnoreR4(r4Errs);
        return true;
      },
      extraBtn: ignOps.length ? {
        text: `集中撤销（${ignOps.length} 条已忽略）`,
        cls: 'danger',
        onRun: async () => { await _revertAllR4(ignOps); },
      } : null,
    });
  }

  if (actionsWrap.children.length) frag.appendChild(actionsWrap);

  // ── 规则详情 ────────────────────────────────────────────────
  _appendRuleSection(frag, '规则1：主数据核对', res.errors?.rule1 || [], 'r1-tag', s.rule1_errors);
  _appendRuleSection(frag, '规则2：父级一致性', res.errors?.rule2 || [], 'r2-tag', s.rule2_errors);
  _appendRuleSection(frag, '规则3：层级前缀',   res.errors?.rule3 || [], 'r3-tag', s.rule3_errors);
  _appendRule4Section(frag, r4Errs, ignRes, s.rule4_errors, ign);

  $resultBody.innerHTML = '';
  $resultBody.appendChild(frag);
}

/* ── 批量操作区块构建器 ──────────────────────────────────────── */
function _appendBatchSection(wrap, { numA, lblA, numB, lblB, hint, btnText, btnCls, btnDisabled, onRun, extraBtn }) {
  const sec = document.createElement('div');
  sec.className = 'pc-batch-sec';

  // 两格数字
  const cards = document.createElement('div');
  cards.className = 'pc-batch-cards';
  const _card = (num, lbl, type) => {
    const c = document.createElement('div');
    c.className = `pc-batch-card pc-batch-card-${type}`;
    c.innerHTML = `<div class="pc-batch-num">${num}</div><div class="pc-batch-lbl">${lbl}</div>`;
    return c;
  };
  cards.appendChild(_card(numA, lblA, btnCls === 'ignore' ? 'pending' : 'warn'));
  if (lblB) cards.appendChild(_card(numB, lblB, 'done'));
  sec.appendChild(cards);

  if (hint) {
    const hintEl = document.createElement('div');
    hintEl.className = 'pc-batch-hint';
    hintEl.textContent = hint;
    sec.appendChild(hintEl);
  }

  const btn = document.createElement('button');
  btn.className = `pc-act-btn pc-batch-btn${btnCls ? ' ' + btnCls : ''}`;
  btn.textContent = btnText;
  btn.disabled = !!btnDisabled;
  btn.addEventListener('click', async () => {
    btn.disabled = true;
    const orig = btn.textContent;
    btn.textContent = '处理中…';
    try {
      const done = await onRun(btn);
      if (!done) { btn.disabled = !!btnDisabled; btn.textContent = orig; }
      else setTimeout(() => _runCheck(), 600);
    } catch (e) {
      btn.disabled = !!btnDisabled; btn.textContent = orig;
      alert('操作失败: ' + e.message);
    }
  });
  sec.appendChild(btn);

  if (extraBtn) {
    const eb = document.createElement('button');
    eb.className = `pc-act-btn ${extraBtn.cls || ''}`;
    eb.style.marginTop = '4px';
    eb.textContent = extraBtn.text;
    eb.addEventListener('click', async () => {
      eb.disabled = true;
      try { await extraBtn.onRun(); setTimeout(() => _runCheck(), 400); }
      catch (e) { eb.disabled = false; alert('操作失败: ' + e.message); }
    });
    sec.appendChild(eb);
  }

  wrap.appendChild(sec);
}

function _appendRuleSection(frag, title, errors, tagCls, count) {
  const sec = document.createElement('div');
  sec.className = 'pc-rule-section';
  const badgeCls = count ? 'nok' : 'ok';
  sec.innerHTML = `<div class="pc-rule-hdr">
    <span>${title}</span>
    <span class="pc-rule-badge ${badgeCls}">${count ? `${count} NOK` : '✓ 通过'}</span>
  </div>`;

  if (errors.length) {
    const body = document.createElement('div');
    body.className = 'pc-rule-body';
    body.innerHTML = errors.map(e =>
      `<div class="pc-err-row">
        <span class="pc-err-vpps" title="${_esc(e.vpps || '')}">${_esc(e.vpps || '')}</span>
        <span class="pc-err-msg">${_esc(e.msg || e.brief || '')}</span>
        <span class="pc-rule-tag ${tagCls}">R${e.rule}</span>
      </div>`
    ).join('');

    let open = true;
    sec.querySelector('.pc-rule-hdr').addEventListener('click', () => {
      open = !open;
      body.style.display = open ? '' : 'none';
    });
    sec.appendChild(body);
  }
  frag.appendChild(sec);
}

function _appendRule4Section(frag, errors, ignRes, count, ignCount) {
  const sec = document.createElement('div');
  sec.className = 'pc-rule-section';
  sec.innerHTML = `<div class="pc-rule-hdr">
    <span>规则4：紧固件主件一致性</span>
    <span class="pc-rule-badge ${count ? 'warn' : 'ok'}">${count ? `${count} NOK` : '✓ 通过'}</span>
    ${ignCount ? `<span class="pc-rule-badge ign" style="margin-left:4px">${ignCount} 已忽略</span>` : ''}
  </div>`;

  const body = document.createElement('div');
  body.className = 'pc-rule-body';

  if (errors.length) {
    body.innerHTML = errors.map(e =>
      `<div class="pc-err-row">
        <span class="pc-err-vpps" title="${_esc(e.vpps || '')}">${_esc(e.vpps || '')}</span>
        <span class="pc-err-msg">${_esc(e.msg || e.brief || '')}</span>
        <span class="pc-rule-tag r4-tag">R4</span>
      </div>`
    ).join('');
  }

  // 操作按钮
  const actionRow = document.createElement('div');
  actionRow.className = 'pc-action-row';

  if (errors.length) {
    const bulkBtn = document.createElement('button');
    bulkBtn.className = 'pc-act-btn';
    bulkBtn.textContent = `忽略全部 ${errors.length} 条`;
    bulkBtn.addEventListener('click', () => _bulkIgnoreR4(errors));
    actionRow.appendChild(bulkBtn);
  }

  const ignOps = ignRes?.operations || [];
  if (ignOps.length) {
    const revertBtn = document.createElement('button');
    revertBtn.className = 'pc-act-btn danger';
    revertBtn.textContent = `撤销全部忽略（${ignOps.length} 条）`;
    revertBtn.addEventListener('click', () => _revertAllR4(ignOps));
    actionRow.appendChild(revertBtn);
  }

  if (actionRow.children.length) body.appendChild(actionRow);

  let open = true;
  sec.querySelector('.pc-rule-hdr').addEventListener('click', () => {
    open = !open;
    body.style.display = open ? '' : 'none';
  });
  sec.appendChild(body);
  frag.appendChild(sec);
}

/* ── Rule4 操作 ──────────────────────────────────────────── */
async function _bulkIgnoreR4(errors) {
  const _cloudFetch = window._cloudFetch?.bind(window);
  const gid  = _tls?.getSelectedList() || $verSel.value;
  const user = window._authUser || {};
  try {
    await _cloudFetch('/api/vpps-operations/rule4-bulk-ignore', {
      method: 'POST',
      body: JSON.stringify({
        pbom_version_gid: gid,
        rows: errors.map(e => ({ pbom_row_gid: e.gid || '', original_vpps_desc: e.vpps || '' })),
        actor_gid:  user.gid  || '',
        actor_name: user.name || '',
      }),
    });
    await _runCheck();
  } catch (e) { alert('忽略失败: ' + e.message); }
}

async function _revertAllR4(ops) {
  const _cloudFetch = window._cloudFetch?.bind(window);
  if (!confirm(`确认撤销全部 ${ops.length} 条让步？`)) return;
  let failed = 0;
  for (const op of ops) {
    try { await _cloudFetch(`/api/vpps-operations/${op.gid}/revert`, { method: 'POST' }); }
    catch (_) { failed++; }
  }
  if (failed) alert(`${failed} 条撤销失败`);
  await _runCheck();
}

/* ── 保存统计 ──────────────────────────────────────────────── */
function _saveStats(gid, checkRes) {
  const s   = checkRes.summary;
  const nok = s.rule1_errors + s.rule2_errors + s.rule3_errors + s.rule4_errors;
  _invokeCapability('craft.ebom.snapshot.vpps_stats.update', {
    snapshot_gid: gid, nok, ignored: s.rule4_ignored || 0, total: _parts.length,
  }).catch(() => {});
}

/* ── NOK 专用视图（核对后替换 TLS 区域）──────────────────────── */
const _NOK_COLS = [
  { key: 'vpps',                  label: 'VPPS',         w: 120 },
  { key: 'vpps_desc',             label: 'VPPS描述',     w: 150 },
  { key: 'parent_vpps',           label: '父级VPPS',     w: 110 },
  { key: 'parent_vpps_name',      label: '父级VPPS描述', w: 130 },
  { key: 'ref_main_vpps',         label: '参考主件VPPS', w: 110 },
  { key: 'ref_main_vpps_desc',    label: '参考主件描述', w: 150 },
  { key: 'main_part_consistency', label: '主件一致性',   w: 90  },
  { key: '_nok_msg',              label: 'NOK说明',      w: 220 },
  { key: '_action',               label: '操作',         w: 80  },
];

function _showNokView() {
  const _cloudFetch = window._cloudFetch?.bind(window);
  const col = document.getElementById('pcTlsMount');
  if (!col) return;

  // 隐藏 TLS，创建 NOK 专用容器
  const tlsEl = col.querySelector('.tls-root') || col.firstElementChild;
  if (tlsEl) tlsEl.style.display = 'none';

  let nokWrap = document.getElementById('pcNokWrap');
  if (!nokWrap) {
    nokWrap = document.createElement('div');
    nokWrap.id = 'pcNokWrap';
    nokWrap.style.cssText = 'display:flex;flex-direction:column;flex:1;overflow:hidden;height:100%';
    col.appendChild(nokWrap);
  }
  nokWrap.style.display = 'flex';

  // 顶部 bar
  const bar = document.createElement('div');
  bar.style.cssText =
    'display:flex;align-items:center;gap:8px;padding:4px 10px;' +
    'background:var(--surface0);border-bottom:1px solid var(--border);flex-shrink:0;font-size:11px';

  const nokParts = _parts.filter(p => {
    const gid = p.gid || '';
    return _nokMap.has(gid) || _ignoredGids.has(gid);
  });
  const cntSpan = document.createElement('span');
  cntSpan.style.cssText = 'color:var(--muted)';
  cntSpan.textContent = `NOK / 已忽略：${nokParts.length} 行`;
  bar.appendChild(cntSpan);

  const spacer = document.createElement('span'); spacer.style.flex = '1';
  bar.appendChild(spacer);

  const allBtn = document.createElement('button');
  allBtn.className = 'pc-act-btn';
  allBtn.style.fontSize = '11px';
  allBtn.textContent = '显示全部零件';
  allBtn.addEventListener('click', () => {
    nokWrap.style.display = 'none';
    if (tlsEl) tlsEl.style.display = '';
  });
  bar.appendChild(allBtn);

  nokWrap.innerHTML = '';
  nokWrap.appendChild(bar);

  // 表体
  const tableWrap = document.createElement('div');
  tableWrap.style.cssText = 'flex:1;overflow:auto';

  if (!nokParts.length) {
    tableWrap.innerHTML = '<div class="pc-empty" style="color:var(--green)">✓ 全部通过，无 NOK 行</div>';
    nokWrap.appendChild(tableWrap);
    return;
  }

  // ── 建立父子映射（gid → 对象），用于 L1/L2 分组头 ──────────
  const byGid = Object.fromEntries(_parts.map(p => [p.gid, p]));
  const byBomRow = {};
  _parts.forEach(p => { if (p.bom_row) byBomRow[p.bom_row] = p; });

  // L1/L2 祖先关系（根据 parent_bom_row 逐级向上）
  const _getAncestors = (p) => {
    const chain = [];
    let cur = p;
    for (let i = 0; i < 5; i++) {
      const par = byBomRow[cur.parent_bom_row];
      if (!par || par.gid === cur.gid) break;
      chain.unshift(par);
      cur = par;
    }
    return chain;
  };

  // 已渲染过的组头 gid 集合
  const renderedGroups = new Set();

  let html = `<table class="pc-nok-table">
    <thead><tr>${_NOK_COLS.map(c =>
      `<th style="width:${c.w}px">${_esc(c.label)}</th>`
    ).join('')}</tr></thead><tbody>`;

  nokParts.forEach(p => {
    const gid   = p.gid || '';
    const errs  = _nokMap.get(gid) || [];
    const ign   = _ignoredGids.has(gid);

    // 插入祖先组头（L1/L2）
    _getAncestors(p).forEach(anc => {
      if (!renderedGroups.has(anc.gid)) {
        renderedGroups.add(anc.gid);
        const lvCls = anc.level === 1 ? 'pc-grp-l1' : 'pc-grp-l2';
        html += `<tr class="${lvCls}"><td colspan="${_NOK_COLS.length}">` +
          `<span class="pc-grp-name">${_esc(anc.name || anc.vpps || '')}</span>` +
          (anc.vpps ? ` <span class="pc-grp-vpps">${_esc(anc.vpps)}</span>` : '') +
          `</td></tr>`;
      }
    });

    // 数据行
    const rowCls = ign ? 'pc-nok-ign' : errs.some(e => e.rule === 1) ? 'pc-nok-r1' : 'pc-nok-r3';
    const nokMsgs = errs.map(e =>
      `<span class="pc-err-tag pc-err-r${e.rule}">R${e.rule}</span> ${_esc(e.msg || e.brief || '')}`
    ).join('<br>');
    const ignMsg = ign ? '<span class="pc-err-tag pc-err-ign">已忽略</span>' : '';

    // 操作列
    let actionHtml = '';
    const r4Errs = errs.filter(e => e.rule === 4);
    const ignOp  = _checkResult && r4Errs.length ? true : false;
    if (r4Errs.length) {
      actionHtml = `<button class="pc-act-btn pc-ign-row-btn" data-gid="${_esc(gid)}" style="font-size:10px;padding:2px 6px">忽略</button>`;
    } else if (ign) {
      actionHtml = `<button class="pc-act-btn danger pc-rev-row-btn" data-gid="${_esc(gid)}" style="font-size:10px;padding:2px 6px">撤销</button>`;
    }

    html += `<tr class="${rowCls}" data-gid="${_esc(gid)}">`;
    _NOK_COLS.forEach(c => {
      if (c.key === '_nok_msg') {
        html += `<td class="pc-nok-msg-cell">${nokMsgs || ignMsg}</td>`;
      } else if (c.key === '_action') {
        html += `<td>${actionHtml}</td>`;
      } else {
        const val = p[c.key] || '';
        html += `<td title="${_esc(String(val))}">${_esc(String(val))}</td>`;
      }
    });
    html += '</tr>';
  });

  html += '</tbody></table>';
  tableWrap.innerHTML = html;

  // 行内忽略按钮
  tableWrap.querySelectorAll('.pc-ign-row-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const verGid = _tls?.getSelectedList() || $verSel.value;
      const rowGid = btn.dataset.gid;
      const part   = _parts.find(p => p.gid === rowGid);
      const user   = window._authUser || {};
      try {
        await _cloudFetch('/api/vpps-operations/rule4-bulk-ignore', {
          method: 'POST',
          body: JSON.stringify({
            pbom_version_gid: verGid,
            rows: [{ pbom_row_gid: rowGid, original_vpps_desc: part?.vpps_desc || '' }],
            actor_gid:  user.gid  || '',
            actor_name: user.name || '',
          }),
        });
        await _runCheck();
      } catch (e) { alert('忽略失败: ' + e.message); }
    });
  });

  // 行内撤销按钮
  tableWrap.querySelectorAll('.pc-rev-row-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const ignRes = await _cloudFetch(
        `/api/vpps-operations?pbom_row_gid=${btn.dataset.gid}`
      , { method: 'GET' }).catch(() => null);
      const ops = ignRes?.data || [];
      if (!ops.length) { alert('未找到可撤销的操作'); return; }
      try {
        await _cloudFetch(`/api/vpps-operations/${ops[0].gid}/revert`, { method: 'POST' });
        await _runCheck();
      } catch (e) { alert('撤销失败: ' + e.message); }
    });
  });

  nokWrap.appendChild(tableWrap);
}

/* ── 工具函数 ─────────────────────────────────────────────── */
function _setStatus(msg, isErr = false) {
  const el = document.getElementById('pcStatus');
  el.textContent = msg;
  el.style.color = isErr ? 'var(--red)' : '';
}

function _esc(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
