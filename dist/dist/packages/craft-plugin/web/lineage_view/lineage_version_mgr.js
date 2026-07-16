'use strict';
/**
 * lineage_version_mgr.js — BOP 版本管理模块
 *
 * 从 lineage.js 提取：版本选择器、新建/Fork/导入弹窗、版本生命周期操作。
 * 依赖：无外部库，通过 constructor deps 注入 cf / toast / 回调函数。
 * 加载顺序：必须在 lineage.js 之前加载（index.html 中已排序）。
 */

// ── 版本状态颜色/标签（供 lineage.js 的 _updateVersionStatusUI 使用）────────
const _STATUS_COLORS = {
  active:   { bg: '#40a02b', label: '活动' },
  baseline: { bg: '#df8e1d', label: '基线' },
  M:        { bg: '#1e66f5', label: '发布' },
  archived: { bg: '#7c7f93', label: '归档' },
};

// ── TC CSV 字段定义 ─────────────────────────────────────────────────────────
const _TC_FIELD_DEFS = [
  { key: '_level',                label: 'Level（层级）',          required: true  },
  { key: 'bom_row_label',         label: 'BOM 行',                required: false },
  { key: '_tc_raw_type',          label: '零组件类型',              required: true  },
  { key: 'bom_row_id',            label: '零组件 ID',               required: false },
  { key: 'title',                 label: '零组件名称',              required: true  },
  { key: 'parent_bop_label',      label: '父级',                   required: false },
  { key: 'bom_row_owner',         label: '所有权用户',              required: false },
  { key: 'vpps',                  label: 'VPPS',                   required: false },
  { key: 'vpps_part',             label: 'VPPS(零件)',              required: false },
  { key: 'vpps_desc',             label: 'VPPS描述',               required: false },
  { key: '_parent_vpps',          label: '父级VPPS',               required: false },
  { key: 'parent_vpps_name',      label: '父级VPPS名称',            required: false },
  { key: 'catia_occurrence_name', label: 'catiaOccurrenceName',    required: false },
  { key: 'torque',                label: '扭矩',                   required: false },
  { key: 'torque_importance',     label: '扭矩重要度',              required: false },
  { key: 'quantity',              label: '数量',                   required: false },
  { key: '__ignore__',            label: '— 忽略此列 —',           required: false },
];

// TC CSV 列名 → 后端字段名 自动识别表
const _TC_COL_MAP = {
  'Level': '_level', '级别': '_level', '层级': '_level', '层次': '_level',
  'BOM 行': 'bom_row_label', 'BOM行': 'bom_row_label', 'BOM_行': 'bom_row_label',
  '零组件类型': '_tc_raw_type', '组件类型': '_tc_raw_type', 'Item Type': '_tc_raw_type',
  '零组件 ID': 'bom_row_id', '零组件ID': 'bom_row_id', 'Item ID': 'bom_row_id', 'ID': 'bom_row_id',
  '零组件名称': 'title', '名称': 'title', 'Name': 'title', 'Item Name': 'title',
  '父级': 'parent_bop_label', 'Parent': 'parent_bop_label', '父节点': 'parent_bop_label',
  '零组件版本所有权用户': 'bom_row_owner', '所有权用户': 'bom_row_owner', 'Owner': 'bom_row_owner',
  'VPPS': 'vpps', 'VPPS(零件)': 'vpps_part', 'VPPS描述': 'vpps_desc',
  '父级VPPS': '_parent_vpps',
  '父级VPPS名称': 'parent_vpps_name', '父级Vpps名称': 'parent_vpps_name',
  'catiaOccurrenceName': 'catia_occurrence_name',
  'catiaOccurenceName': 'catia_occurrence_name',
  'CATIA Occurrence Name': 'catia_occurrence_name',
  '数量': 'quantity', 'Qty': 'quantity', 'Quantity': 'quantity',
  '扭矩': 'torque', 'Torque': 'torque',
  '扭矩重要度': 'torque_importance',
};

const _TC_TYPE_MAP = {
  'Total Assembly': 'factory_bop', 'Line Process': 'line_process',
  'Station Process': 'station_process', 'Operator Process': 'operator_process',
  'Process': 'process', 'Operation': 'operation',
  'Manufacturing Operation': 'operation', 'Station Operation': 'operation',
  'Shop Operation': 'operation', 'Assembly Operation': 'operation',
  'Part': 'part', 'Non Standard Part': 'non_standard_part', 'Standard Part': 'standard_part',
  'Tool': 'tool_need', 'Fixture': 'fixture_need', 'Equipment': 'equipment_need',
  'Manufacturing Tool': 'tool_need', 'Manufacturing Fixture': 'fixture_need',
  'Manufacturing Equipment': 'equipment_need',
  '总装工厂BOP': 'factory_bop', '整车BOP': 'factory_bop', '总装': 'factory_bop',
  '总装线体工艺': 'line_process', '线体工艺': 'line_process', '线体': 'line_process',
  '总装工位工艺': 'station_process', '工位工艺': 'station_process', '工位': 'station_process',
  '总装岗位工艺': 'operator_process', '岗位工艺': 'operator_process',
  '总装工序': 'process', '工艺过程': 'process', '工序': 'process',
  '总装操作': 'operation', '操作': 'operation',
  '零件': 'part', '零组件': 'part', '零部件': 'part',
  '非标零件': 'non_standard_part', '非标件': 'non_standard_part',
  '标准零件': 'standard_part', '标准件': 'standard_part',
  '辅料': 'support_material',
  '工具': 'tool_need', '工装': 'fixture_need', '设备': 'equipment_need',
  '工具需求': 'tool_need', '工装需求': 'fixture_need', '设备需求': 'equipment_need',
};

// ── LineageVersionManager ──────────────────────────────────────────────────

class LineageVersionManager {
  /**
   * @param {object} deps
   * @param {Function} deps.cf          - async fetch wrapper: cf(url, opts?) → json
   * @param {Function} deps.toast       - toast(msg, type, dur?)
   * @param {Function} deps.onVersionSelected  - (gid, tag) → void，版本被选中时调用
   * @param {Function} deps.onStatusChange     - (status) → void，版本状态变更时调用
   * @param {Function} deps.onReloadNeeded     - () → void，需要重新加载数据时调用（TC/GBOP 导入后）
   * @param {Function} [deps.onNewBtnClick]    - 覆盖「新建」按钮默认行为；若提供则不再打开创建弹窗
   */
  constructor({ cf, toast, onVersionSelected, onStatusChange, onReloadNeeded, onNewBtnClick }) {
    this._cf = cf;
    this._toast = toast;
    this._onVersionSelected = onVersionSelected;
    this._onStatusChange = onStatusChange;
    this._onReloadNeeded = onReloadNeeded || (() => {});
    this._onNewBtnClick  = onNewBtnClick  || null;

    // 公开状态
    this.currentVersionGid = null;
    this.currentVersionStatus = 'active';

    // 内部状态
    this._allVersions    = [];
    this._familyCollapsed = new Set();  // 折叠的族群 key
    this._arcOpen        = false;       // 是否显示已归档
    this._showArchived   = false;       // 搜索栏旁的归档开关
    this._recentVersions = [];          // 最近使用的版本 gid（最多5条）
    this._searchQuery    = '';
    this._projectsCache  = [];
    this._factoriesCache = [];
    this._parsedTcRows   = [];
    this._tcRawHeaders   = [];
    this._tcRawLines     = [];
    this._tcFieldMap     = {};

    // DOM refs
    this._$vpSelect   = document.getElementById('lvVersionSelect');
    this._$vpMenu     = document.getElementById('lvVersionMenu');
    this._$vpNewBtn   = document.getElementById('lvNewVersionBtn');
    this._$versionLbl = document.getElementById('lvVersionLabel');
  }

  get allVersions() { return this._allVersions; }

  // ── 版本列表 ───────────────────────────────────────────────────────────

  async loadVersions() {
    try {
      const res = await this._cf('/api/bop/versions?include_archived=true');
      this._allVersions = res.data || [];
    } catch (e) {
      this._toast('加载版本列表失败: ' + e.message, 'error');
    }
  }

  // ── 版本菜单渲染 ───────────────────────────────────────────────────────

  renderMenu() {
    const $menu = this._$vpMenu;
    $menu.innerHTML = '';
    if (!this._allVersions.length) {
      $menu.innerHTML = '<div style="padding:8px 12px;font-size:12px;color:var(--subtext0,#a6adc8)">暂无版本</div>';
      return;
    }

    // ── 搜索栏 + 归档开关 ─────────────────────────────────────────────
    const toolbar = document.createElement('div');
    toolbar.className = 'lv-vp-toolbar';
    toolbar.innerHTML = `
      <div class="lv-vp-search-wrap">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"
             style="flex-shrink:0;opacity:.5"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        <input class="lv-vp-search-inp" id="lvVpSearchInp" placeholder="搜索项目或版本…" value="${this._searchQuery}">
      </div>
      <button class="lv-vp-arc-toggle${this._showArchived ? ' active' : ''}" id="lvVpArcToggle" title="显示已归档版本">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5"/><line x1="10" y1="12" x2="14" y2="12"/>
        </svg>
      </button>`;
    $menu.appendChild(toolbar);

    toolbar.querySelector('#lvVpSearchInp')?.addEventListener('input', e => {
      e.stopPropagation();
      this._searchQuery = e.target.value;
      this._renderMenuContent($menu);
    });
    toolbar.querySelector('#lvVpSearchInp')?.addEventListener('click', e => e.stopPropagation());
    toolbar.querySelector('#lvVpArcToggle')?.addEventListener('click', e => {
      e.stopPropagation();
      this._showArchived = !this._showArchived;
      this.renderMenu();
    });

    this._renderMenuContent($menu);
  }

  _renderMenuContent($menu) {
    while ($menu.lastChild && !$menu.lastChild.classList?.contains('lv-vp-toolbar')) {
      $menu.removeChild($menu.lastChild);
    }

    const q = (this._searchQuery || '').trim().toLowerCase();

    const familyMap = new Map();
    for (const ver of this._allVersions) {
      const groupKey = ver.version_family_gid || ver.gid;
      if (!familyMap.has(groupKey)) {
        familyMap.set(groupKey, { bop_name: ver.bop_name || '未命名BOP', archived: true, versions: [], isTemplate: false });
      }
      const fam = familyMap.get(groupKey);
      if (!ver.archived_at) fam.bop_name = ver.bop_name || fam.bop_name;
      fam.versions.push(ver);
      if (!ver.archived_at) fam.archived = false;
      if (ver.version_type === 'template') fam.isTemplate = true;
    }
    for (const fam of familyMap.values()) {
      fam.versions.sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''));
    }

    const matchesQuery = (fam) => {
      if (!q) return true;
      if (fam.bop_name.toLowerCase().includes(q)) return true;
      return fam.versions.some(v => (v.version_tag || '').toLowerCase().includes(q));
    };

    if (!q && this._recentVersions.length > 0) {
      const recentVers = this._recentVersions
        .map(gid => this._allVersions.find(v => v.gid === gid))
        .filter(Boolean);
      if (recentVers.length) {
        const sec = document.createElement('div');
        sec.className = 'lv-vp-sec-label';
        sec.textContent = '最近使用';
        $menu.appendChild(sec);
        recentVers.forEach(ver => this._renderVerItem($menu, ver, null));
        const sep = document.createElement('div');
        sep.className = 'lv-vp-sep';
        $menu.appendChild(sep);
      }
    }

    const working = [...familyMap.entries()].filter(([, f]) =>
      !f.isTemplate && (this._showArchived || !f.archived) && matchesQuery(f)
    );

    if (working.length) {
      working.forEach(([key, fam]) => this._renderFamGroup($menu, key, fam, q));
    }

    if (!working.length) {
      const empty = document.createElement('div');
      empty.style.cssText = 'padding:8px 12px;font-size:12px;color:var(--subtext0,#a6adc8)';
      empty.textContent = q ? '无匹配结果' : '暂无版本';
      $menu.appendChild(empty);
    }
  }

  _renderFamGroup($menu, groupKey, fam, q) {
    const hasCurrent = fam.versions.some(v => v.gid === this.currentVersionGid);
    const hasExplicitCurrent = !!this.currentVersionGid;
    const defaultCollapsed = hasExplicitCurrent && !hasCurrent && !q;
    const explicitExpand = this._familyCollapsed.has('exp:' + groupKey);
    const explicitCollapse = this._familyCollapsed.has('col:' + groupKey);
    const isCollapsed = explicitCollapse ? true : explicitExpand ? false : defaultCollapsed;

    const hdr = document.createElement('div');
    hdr.className = 'lv-vp-fam-hdr';
    hdr.innerHTML = `
      <svg class="lv-vp-fam-arrow${isCollapsed ? '' : ' open'}" width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <polyline points="9 18 15 12 9 6"/>
      </svg>
      <span class="lv-vp-fam-name">${fam.bop_name}${fam.archived ? ' <span style="opacity:.5;font-size:9px">已归档</span>' : ''}</span>`;
    hdr.addEventListener('click', e => {
      e.stopPropagation();
      if (isCollapsed) {
        this._familyCollapsed.delete('col:' + groupKey);
        this._familyCollapsed.add('exp:' + groupKey);
      } else {
        this._familyCollapsed.delete('exp:' + groupKey);
        this._familyCollapsed.add('col:' + groupKey);
      }
      this._renderMenuContent($menu);
    });
    $menu.appendChild(hdr);
    if (isCollapsed) return;

    const versToShow = q
      ? fam.versions.filter(v => (v.version_tag || '').toLowerCase().includes(q) || fam.bop_name.toLowerCase().includes(q))
      : fam.versions.filter(v => this._showArchived || !v.archived_at);

    versToShow.forEach(ver => this._renderVerItem($menu, ver, groupKey));
  }

  _renderVerItem($menu, ver, groupKey) {
    const st = ver.status || 'active';
    const item = document.createElement('div');
    item.className = 'lv-vp-ver-item' + (ver.gid === this.currentVersionGid ? ' active' : '') + (ver.archived_at ? ' archived' : '');
    item.innerHTML = `
      <span class="lv-vp-ver-dot ${st !== 'active' ? st : ''}"></span>
      <span class="lv-vp-ver-tag">
        ${ver.version_tag || ver.gid.slice(-6)}
        ${ver.data_stage ? `<span class="lv-vp-ver-stage">${ver.data_stage}</span>` : ''}
        <span class="lv-vp-ver-status lv-st-${st}">${_STATUS_COLORS[st]?.label || st}</span>
        ${ver.frozen_at ? '<span class="lv-vp-ver-ts">' + (ver.frozen_at||'').slice(0,10) + '</span>' : ''}
        ${ver.published_at && !ver.frozen_at ? '<span class="lv-vp-ver-ts">' + (ver.published_at||'').slice(0,10) + '</span>' : ''}
      </span>`;
    item.addEventListener('click', () => {
      this.selectVersion(ver.gid, ver.version_tag || ver.gid.slice(-6));
      this._closeMenu();
    });
    item.addEventListener('contextmenu', e => {
      e.preventDefault();
      e.stopPropagation();
      this._showVerCtxMenu(e.clientX, e.clientY, ver, groupKey);
    });
    $menu.appendChild(item);
  }


  // ── 版本右键菜单（版本生命周期操作入口）──────────────────────────────

  _showVerCtxMenu(x, y, ver, familyGid) {
    const existing = document.getElementById('lv-ver-ctx-menu');
    if (existing) existing.remove();

    const st = ver.status || 'active';
    const menu = document.createElement('div');
    menu.id = 'lv-ver-ctx-menu';
    menu.className = 'lv-ctx-menu';
    menu.style.cssText = `position:fixed;left:${x}px;top:${y}px;z-index:9999`;

    const items = [];
    if (st === 'active') {
      items.push({ action: 'freeze',   label: '冻结为基线（baseline）' });
    }
    if (st === 'baseline') {
      items.push({ action: 'unfreeze', label: '解冻（回到活动）' });
      items.push({ action: 'publish',  label: '发布为 M 版本' });
    }
    items.push({ action: 'fork',  label: 'Fork 此版本…' });
    items.push({ action: 'edit_stage', label: `编辑数据阶段${ver.data_stage ? '（当前：' + ver.data_stage + '）' : ''}` });
    if (!ver.archived_at) {
      items.push({ action: 'archive',   label: '归档版本族' });
    } else {
      items.push({ action: 'unarchive', label: '恢复版本族' });
    }
    // 超管专属：清空条目
    const _u = window.parent?._authUser || window._authUser;
    if ((_u?.role || _u?.system_role) === 'super_admin') {
      items.push({ action: 'purge_soft', label: '【超管】清空所有条目（软删）', cls: 'warn' });
      items.push({ action: 'purge_hard', label: '【超管】清空所有条目（硬删）', cls: 'danger' });
    }

    menu.innerHTML = items.map(it =>
      `<div class="lv-ctx-item${it.cls ? ' lv-ctx-' + it.cls : ''}" data-action="${it.action}">${it.label}</div>`
    ).join('');

    menu.addEventListener('click', async e => {
      const item = e.target.closest('.lv-ctx-item');
      if (!item) return;
      menu.remove();
      const action = item.dataset.action;
      if (action === 'freeze')      await this.freeze(ver.gid);
      if (action === 'unfreeze')    await this.unfreeze(ver.gid);
      if (action === 'publish')     await this.publish(ver.gid);
      if (action === 'archive')     await this.archiveFamily(familyGid);
      if (action === 'unarchive')   await this.unarchiveFamily(familyGid);
      if (action === 'fork')        this.openForkModal(ver.gid);
      if (action === 'edit_stage')  await this._editDataStage(ver);
      if (action === 'purge_soft')  await this._purgeEntries(ver, 'soft');
      if (action === 'purge_hard')  await this._purgeEntries(ver, 'hard');
    });

    document.body.appendChild(menu);
    const closer = () => { menu.remove(); document.removeEventListener('click', closer); };
    setTimeout(() => document.addEventListener('click', closer), 0);
  }

  // ── 版本生命周期操作 ──────────────────────────────────────────────────

  async freeze(gid) {
    try {
      const res = await this._cf(`/api/bop/versions/${gid}/freeze`, { method: 'POST' });
      await this.loadVersions();
      if (gid === this.currentVersionGid) {
        this.currentVersionStatus = res.data?.status || 'baseline';
        this._onStatusChange(this.currentVersionStatus);
      }
      this.renderMenu();
      this._toast('版本已冻结为基线', 'ok');
    } catch (e) { this._toast('冻结失败: ' + e.message, 'error'); }
  }

  async unfreeze(gid) {
    try {
      const res = await this._cf(`/api/bop/versions/${gid}/unfreeze`, { method: 'POST' });
      await this.loadVersions();
      if (gid === this.currentVersionGid) {
        this.currentVersionStatus = res.data?.status || 'active';
        this._onStatusChange(this.currentVersionStatus);
      }
      this.renderMenu();
      this._toast('版本已解冻', 'ok');
    } catch (e) { this._toast('解冻失败: ' + e.message, 'error'); }
  }

  async publish(gid) {
    try {
      const res = await this._cf(`/api/bop/versions/${gid}/publish`, { method: 'POST' });
      await this.loadVersions();
      if (gid === this.currentVersionGid) {
        this.currentVersionStatus = res.data?.status || 'M';
        this._onStatusChange(this.currentVersionStatus);
      }
      this.renderMenu();
      this._toast('版本已发布', 'ok');
    } catch (e) { this._toast('发布失败: ' + e.message, 'error'); }
  }

  async archiveFamily(familyGid) {
    if (!confirm('确认归档此版本族？归档后不可编辑，可恢复。')) return;
    try {
      await this._cf(`/api/bop/version-families/${familyGid}/archive`, { method: 'POST' });
      await this.loadVersions();
      this.renderMenu();
      this._toast('版本族已归档', 'ok');
    } catch (e) { this._toast('归档失败: ' + e.message, 'error'); }
  }

  async unarchiveFamily(familyGid) {
    try {
      await this._cf(`/api/bop/version-families/${familyGid}/archive`, { method: 'DELETE' });
      await this.loadVersions();
      this.renderMenu();
      this._toast('版本族已恢复', 'ok');
    } catch (e) { this._toast('恢复失败: ' + e.message, 'error'); }
  }

  async _purgeEntries(ver, mode) {
    const modeLabel = mode === 'hard' ? '硬删（永久不可恢复）' : '软删（可数据库恢复）';
    if (!confirm(`确认对版本「${ver.version_tag}」执行 ${modeLabel}？\n将清空全部条目及关联私有实体。`)) return;
    if (mode === 'hard' && !confirm('⚠️ 再次确认：硬删将永久清除所有数据，是否继续？')) return;
    try {
      const res = await this._cf(`/api/bop/versions/${ver.gid}/purge-entries`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode }),
      });
      const c = res.counts || {};
      this._toast(`清空完成（条目 ${c.entries ?? 0} 条，链接 ${c.links ?? 0} 条）`, 'ok');
    } catch (e) { this._toast('清空失败: ' + e.message, 'error'); }
  }

  async _editDataStage(ver) {
    const _DATA_STAGES = ['Pre-TG0','TG0','TG1','PreTG2','TG2','EP1','EP2','PPV','PP','P','SOP'];
    const overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:9999;display:flex;align-items:center;justify-content:center';
    const box = document.createElement('div');
    box.style.cssText = 'background:var(--surface0,#313244);border:1px solid var(--surface2,#585b70);border-radius:8px;padding:16px;min-width:220px';
    box.innerHTML =
      `<div style="font-size:12px;font-weight:600;color:var(--text,#cdd6f4);margin-bottom:10px">编辑数据阶段</div>` +
      `<select id="_ds-sel" style="width:100%;padding:5px 8px;font-size:12px;background:var(--base,#1e1e2e);color:var(--text,#cdd6f4);border:1px solid var(--surface2,#585b70);border-radius:4px;margin-bottom:12px">` +
      `<option value="">— 清空 —</option>` +
      _DATA_STAGES.map(s => `<option value="${s}"${s===ver.data_stage?' selected':''}>${s}</option>`).join('') +
      `</select>` +
      `<div style="display:flex;gap:8px;justify-content:flex-end">` +
      `<button id="_ds-cancel" style="padding:4px 12px;font-size:12px;background:transparent;border:1px solid var(--surface2,#585b70);border-radius:4px;color:var(--text,#cdd6f4);cursor:pointer">取消</button>` +
      `<button id="_ds-ok" style="padding:4px 12px;font-size:12px;background:var(--blue,#89b4fa);border:none;border-radius:4px;color:var(--base,#1e1e2e);font-weight:600;cursor:pointer">保存</button>` +
      `</div>`;
    overlay.appendChild(box);
    document.body.appendChild(overlay);
    box.querySelector('#_ds-cancel').addEventListener('click', () => overlay.remove());
    box.querySelector('#_ds-ok').addEventListener('click', async () => {
      const stage = box.querySelector('#_ds-sel').value || null;
      overlay.remove();
      try {
        await this._cf(`/api/bop/versions/${ver.gid}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ data_stage: stage }),
        });
        await this.loadVersions();
        this.renderMenu();
        this._toast('数据阶段已更新', 'ok');
      } catch (e) { this._toast('保存失败: ' + e.message, 'error'); }
    });
  }

  // ── 菜单控制 ────────────────────────────────────────────────────────

  toggleMenu() {
    const isOpen = this._$vpMenu.style.display !== 'none';
    if (isOpen) {
      this._closeMenu();
    } else {
      this.renderMenu();
      this._$vpMenu.style.display = '';
      document.getElementById('lvVersionSelect')?.querySelector('.lv-vp-arrow')?.classList.add('open');
    }
  }

  _closeMenu() {
    this._$vpMenu.style.display = 'none';
    this._$vpSelect?.querySelector('.lv-vp-arrow')?.classList.remove('open');
  }

  // ── 版本标签（完整显示：bop_name / version_tag）──────────────────────
  _versionLabel(gid, fallbackTag) {
    const ver = this._allVersions.find(v => v.gid === gid);
    const tag = ver?.version_tag || fallbackTag || (gid || '').slice(-6);
    const name = ver?.bop_name || '';
    return name ? `${name} / ${tag}` : tag;
  }

  // ── 版本选择 ─────────────────────────────────────────────────────────

  selectVersion(gid, tag) {
    this.currentVersionGid = gid;
    localStorage.setItem('lv:lastVersionGid', gid);
    // 最近使用记录（最多保留5条，去重）
    this._recentVersions = [gid, ...this._recentVersions.filter(g => g !== gid)].slice(0, 5);
    if (this._$versionLbl) this._$versionLbl.textContent = this._versionLabel(gid, tag);
    this._onVersionSelected(gid, tag);
  }

  // ── 版本选择器初始化 ───────────────────────────────────────────────

  initPicker(initialGid = null, initialTag = null) {
    // 点击选择按钮开关菜单
    this._$vpSelect?.addEventListener('click', () => this.toggleMenu());

    // 点击外部关闭菜单
    document.addEventListener('click', e => {
      if (this._$vpMenu.style.display !== 'none' &&
          !this._$vpSelect?.contains(e.target) && !this._$vpMenu?.contains(e.target)) {
        this._closeMenu();
      }
    });

    // 新建版本按钮
    this._$vpNewBtn?.addEventListener('click', () => {
      if (this._onNewBtnClick) {
        this._onNewBtnClick();
      } else {
        this.openCreateModal();
      }
    });

    // 模板按钮 + 下拉菜单
    const tmplBtn  = document.getElementById('lvTmplBtn');
    const tmplMenu = document.getElementById('lvTmplMenu');
    if (tmplBtn && tmplMenu) {
      tmplBtn.addEventListener('click', e => {
        e.stopPropagation();
        const isOpen = tmplMenu.style.display !== 'none';
        tmplMenu.style.display = isOpen ? 'none' : 'block';
      });
      document.addEventListener('click', e => {
        if (!tmplBtn.contains(e.target) && !tmplMenu.contains(e.target)) {
          tmplMenu.style.display = 'none';
        }
      });
      document.getElementById('lvTmplFromTemplate')?.addEventListener('click', () => {
        tmplMenu.style.display = 'none';
        this.openFromTmplModal();
      });
      document.getElementById('lvTmplSaveAsTemplate')?.addEventListener('click', () => {
        tmplMenu.style.display = 'none';
        this.openSaveTmplModal();
      });
    }

    // 创建版本弹窗内的快捷按钮
    document.getElementById('lv-sc-tc')?.addEventListener('click', () => {
      this._closeCreateModal(); this.openImportTcModal();
    });
    document.getElementById('lv-sc-fork')?.addEventListener('click', () => {
      this._closeCreateModal(); this.openForkModal();
    });
    document.getElementById('lv-sc-gbop')?.addEventListener('click', () => {
      this._closeCreateModal(); this.openImportGbopModal();
    });

    // 各弹窗按钮
    document.getElementById('lv-create-cancel')?.addEventListener('click',  () => this._closeCreateModal());
    document.getElementById('lv-create-confirm')?.addEventListener('click', () => this.createVersion());
    document.getElementById('lv-tc-cancel')?.addEventListener('click',      () => document.getElementById('lv-modal-import-tc').classList.add('hidden'));
    document.getElementById('lv-tc-next')?.addEventListener('click',        () => { this._tcGoStep(2); this._tcRenderColMap(); });
    document.getElementById('lv-tc-back')?.addEventListener('click',        () => this._tcGoStep(1));
    document.getElementById('lv-tc-confirm')?.addEventListener('click',     () => this.importTc());
    document.getElementById('lv-fork-cancel')?.addEventListener('click',    () => document.getElementById('lv-modal-fork').classList.add('hidden'));
    document.getElementById('lv-fork-confirm')?.addEventListener('click',   () => this.forkBop());
    document.getElementById('lv-fork-type')?.addEventListener('change',     () => this._onForkTypeChange());
    document.getElementById('lv-gbop-cancel')?.addEventListener('click',    () => document.getElementById('lv-modal-import-gbop').classList.add('hidden'));
    document.getElementById('lv-gbop-confirm')?.addEventListener('click',   () => this.importGbop());

    // 保存为模板
    document.getElementById('lv-st-cancel')?.addEventListener('click',  () => document.getElementById('lv-modal-save-tmpl').classList.add('hidden'));
    document.getElementById('lv-st-confirm')?.addEventListener('click', () => this.saveTmpl());
    document.getElementById('lv-st-src')?.addEventListener('change',    () => this._updateStNamePreview());
    document.getElementById('lv-st-factory')?.addEventListener('change',() => this._updateStNamePreview());

    // 从模板新建
    document.getElementById('lv-ft-cancel1')?.addEventListener('click', () => document.getElementById('lv-modal-from-tmpl').classList.add('hidden'));
    document.getElementById('lv-ft-cancel2')?.addEventListener('click', () => document.getElementById('lv-modal-from-tmpl').classList.add('hidden'));
    document.getElementById('lv-ft-next')?.addEventListener('click',    () => this._ftStep2());
    document.getElementById('lv-ft-back')?.addEventListener('click',    () => this._ftShowStep(1));
    document.getElementById('lv-ft-confirm')?.addEventListener('click', () => this.forkFromTmpl());
    document.getElementById('lv-ft-project')?.addEventListener('change',() => this._updateFtNamePreview());
    document.getElementById('lv-ft-family')?.addEventListener('change', () => this._updateFtNamePreview());
    document.getElementById('lv-ft-search')?.addEventListener('input',  e => this._filterFtList(e.target.value));

    // 新建版本表单联动
    document.getElementById('lv-inp-project')?.addEventListener('change', () => {
      this._updateBopNamePreview();
      const projGid = document.getElementById('lv-inp-project')?.value.trim() || null;
      // 重置 PBOM 选择
      const pbomSel = document.getElementById('lv-inp-pbom');
      if (pbomSel) pbomSel.innerHTML = '<option value="">— 请先选择项目 —</option>';
      this._loadPbomVersions(projGid);
    });
    document.getElementById('lv-inp-tag')?.addEventListener('input',      () => this._updateBopNamePreview());
    document.getElementById('lv-inp-suffix')?.addEventListener('input',   () => this._updateBopNamePreview());

    // TC CSV 文件选择
    document.getElementById('lv-inp-tc-file')?.addEventListener('change', e => this._handleTcFile(e));

    // 从初始参数恢复版本标签
    if (initialGid) {
      this.currentVersionGid = initialGid;
      if (this._$versionLbl) {
        this._$versionLbl.textContent = this._versionLabel(initialGid, initialTag);
      }
    }
  }

  // ── 新建版本弹窗 ──────────────────────────────────────────────────────

  _closeCreateModal() {
    document.getElementById('lv-modal-create')?.classList.add('hidden');
  }

  async openCreateModal(prefillFamilyGid = null) {
    if (this._projectsCache.length === 0) {
      try {
        const res = await this._cf('/api/projects?limit=200');
        this._projectsCache = (res.data || []).filter(p => !p.is_deleted && p.project_type !== 'gbop');
      } catch (_) { this._projectsCache = []; }
    }
    if (this._factoriesCache.length === 0) {
      try {
        const res = await this._cf('/api/bop/factories');
        this._factoriesCache = res.data || [];
      } catch (_) { this._factoriesCache = []; }
    }

    const projSel = document.getElementById('lv-inp-project');
    projSel.innerHTML = '<option value="">— 请选择项目 —</option>';
    for (const p of this._projectsCache) {
      const opt = document.createElement('option');
      opt.value = p.gid;
      opt.dataset.factoryGid  = p.factory_gid || '';
      opt.dataset.projectName = p.name || p.gid;
      opt.dataset.jph         = p.jph != null ? p.jph : '';
      const fac = this._factoriesCache.find(f => f.gid === p.factory_gid);
      opt.dataset.factoryName = fac ? (fac.name || fac.gid) : '';
      opt.textContent = p.name || p.gid;
      projSel.appendChild(opt);
    }

    document.getElementById('lv-inp-tag').value    = '';
    document.getElementById('lv-inp-suffix').value = '';
    document.getElementById('lv-inp-factory').value = '';
    document.getElementById('lv-inp-factory-display').value = '';
    document.getElementById('lv-inp-bop-name').value = '';

    const familyHint = document.getElementById('lv-inp-family-hint');
    const famGidEl   = document.getElementById('lv-inp-family-gid');
    if (prefillFamilyGid) {
      famGidEl.value = prefillFamilyGid;
      familyHint.classList.remove('lv-hidden');
    } else {
      famGidEl.value = '';
      familyHint.classList.add('lv-hidden');
    }

    this._updateBopNamePreview();
    document.getElementById('lv-modal-create').classList.remove('hidden');
  }

  _updateBopNamePreview() {
    const projSel    = document.getElementById('lv-inp-project');
    const familyGid  = document.getElementById('lv-inp-family-gid')?.value.trim();
    const previewEl  = document.getElementById('lv-inp-preview');
    const hidName    = document.getElementById('lv-inp-bop-name');
    const hidTag     = document.getElementById('lv-inp-tag');
    const factDispEl = document.getElementById('lv-inp-factory-display');
    const factHidEl  = document.getElementById('lv-inp-factory');

    const selectedOpt = projSel?.options[projSel.selectedIndex];
    if (selectedOpt?.value) {
      factDispEl.value = selectedOpt.dataset.factoryName || '';
      factHidEl.value  = selectedOpt.dataset.factoryGid  || '';
      const jph = selectedOpt.dataset.jph;
      const taktEl = document.getElementById('lv-inp-takt');
      if (taktEl && jph) taktEl.value = jph;
    }

    const projName = selectedOpt?.dataset?.projectName || '';
    if (!projName) {
      if (previewEl) previewEl.textContent = '请先选择项目';
      if (hidName) hidName.value = '';
      if (hidTag)  hidTag.value  = '';
      return;
    }

    // 族群名 = 项目名（简洁，同族共享）
    const bopName = projName;

    // 版本号自动递增：族内现有版本数 + 1
    let nextNum = 1;
    if (familyGid) {
      const familyVers = this._allVersions.filter(v =>
        (v.version_family_gid || v.gid) === familyGid && !v.archived_at
      );
      const maxN = familyVers.reduce((m, v) => {
        const n = parseInt((v.version_tag || '').replace(/^v/i, ''));
        return isNaN(n) ? m : Math.max(m, n);
      }, 0);
      nextNum = maxN + 1;
    }
    const autoTag = `v${nextNum}`;

    if (hidName) hidName.value = bopName;
    if (hidTag)  hidTag.value  = autoTag;
    if (previewEl) {
      previewEl.textContent = familyGid
        ? `${bopName}  ·  ${autoTag}（族内递增）`
        : `${bopName}  ·  ${autoTag}（新族首版）`;
    }
  }

  async createVersion() {
    const tag       = document.getElementById('lv-inp-tag').value.trim();
    const bopName   = document.getElementById('lv-inp-bop-name').value.trim();
    const familyGid = document.getElementById('lv-inp-family-gid').value.trim() || null;
    const project   = document.getElementById('lv-inp-project').value.trim() || null;
    const factory   = document.getElementById('lv-inp-factory').value.trim() || null;
    const pbomGid   = document.getElementById('lv-inp-pbom')?.value.trim() || null;
    if (!project)  { this._toast('请先选择所属项目', 'warn'); return; }
    if (!tag)      { this._toast('版本号生成失败，请刷新重试', 'warn'); return; }
    if (!bopName)  { this._toast('族群名生成失败，请选择项目', 'warn'); return; }
    try {
      const res = await this._cf('/api/bop/versions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ version_tag: tag, bop_name: bopName, version_family_gid: familyGid,
                               status: 'active', project_gid: project, factory_gid: factory,
                               pbom_version_gid: pbomGid || null }),
      });
      this._closeCreateModal();
      await this.loadVersions();
      const newGid = res.data?.gid || res.gid;
      if (newGid) this.selectVersion(newGid, tag);
      this._toast('版本创建成功', 'ok');
    } catch (e) { this._toast('创建失败: ' + e.message, 'error'); }
  }

  async _loadPbomVersions(projectGid) {
    const sel  = document.getElementById('lv-inp-pbom');
    const hint = document.getElementById('lv-inp-pbom-hint');
    if (!sel) return;
    if (!projectGid) {
      sel.innerHTML = '<option value="">— 请先选择项目 —</option>';
      if (hint) hint.style.display = 'none';
      return;
    }
    sel.innerHTML = '<option value="">— 加载中… —</option>';
    try {
      const res = await this._cf(`/api/bop/pbom-versions?project_gid=${encodeURIComponent(projectGid)}`);
      const versions = (res?.data || []).filter(v => !v.archived_at);
      if (!versions.length) {
        sel.innerHTML = '<option value="">（无已就绪 PBOM 版本）</option>';
        if (hint) hint.style.display = '';
      } else {
        sel.innerHTML = '<option value="">— 可选，不绑定 —</option>';
        for (const v of versions) {
          const opt = document.createElement('option');
          opt.value = v.gid;
          opt.textContent = v.title || v.bop_name || v.version_tag || v.gid;
          sel.appendChild(opt);
        }
        if (hint) hint.style.display = 'none';
      }
    } catch {
      sel.innerHTML = '<option value="">（加载失败）</option>';
    }
  }

  // ── TC CSV 导入弹窗 ───────────────────────────────────────────────────
  openImportTcModal() {
    if (!this.currentVersionGid) { this._toast('请先选择 BOP 版本', 'warn'); return; }
    const ver = this._allVersions.find(v => v.gid === this.currentVersionGid);
    document.getElementById('lv-tc-ver-name').value = ver
      ? (ver.version_tag || ver.gid.slice(-6))
      : this.currentVersionGid.slice(-6);
    document.getElementById('lv-inp-tc-file').value = '';
    document.getElementById('lv-tc-s1-status').style.display = 'none';
    document.getElementById('lv-tc-next').disabled    = true;
    document.getElementById('lv-tc-confirm').disabled = true;
    this._parsedTcRows = [];
    this._tcRawHeaders = [];
    this._tcRawLines   = [];
    this._tcFieldMap   = {};
    this._tcSep        = null;
    this._tcGoStep(1);
    document.getElementById('lv-modal-import-tc').classList.remove('hidden');
  }

  _tcGoStep(n) {
    document.getElementById('lv-tc-step1').style.display = n === 1 ? '' : 'none';
    document.getElementById('lv-tc-step2').style.display = n === 2 ? '' : 'none';
    [1, 2, 3].forEach(i => {
      const el = document.getElementById(`lv-tc-step-ind-${i}`);
      if (!el) return;
      el.classList.toggle('active', i === n);
      el.classList.toggle('done',   i < n);
    });
  }

  _handleTcFile(e) {
    const file = e.target.files[0];
    if (!file) return;
    const statusEl = document.getElementById('lv-tc-s1-status');
    statusEl.style.display = '';
    statusEl.className = 'lv-tc-s1-status lv-tc-s1-loading';
    statusEl.textContent = '解析中…';
    document.getElementById('lv-tc-next').disabled = true;

    const reader = new FileReader();
    reader.onload = ev => {
      try {
        const text = ev.target.result;
        const firstLine = text.split(/\r?\n/)[0] || '';
        const sep = this._detectSep(firstLine);
        this._tcSep = sep;
        const lines = text.split(/\r?\n/).filter(l => l.trim());
        if (lines.length < 2) {
          statusEl.className = 'lv-tc-s1-status lv-tc-s1-error';
          statusEl.textContent = '文件内容为空或只有表头，请检查文件。';
          return;
        }
        const headers = this._parseCsvLine(lines[0], sep).map(h => h.trim().replace(/^"|"$/g, ''));
        this._tcRawHeaders = headers;
        this._tcRawLines   = lines.slice(1);

        const fieldMap = {};
        const recognized = [], unrecognized = [];
        headers.forEach(h => {
          const mapped = _TC_COL_MAP[h];
          if (mapped) { fieldMap[h] = mapped; recognized.push(h); }
          else         { fieldMap[h] = '__ignore__'; unrecognized.push(h); }
        });
        this._tcFieldMap = fieldMap;

        const total = headers.length;
        const recCnt = recognized.length;
        let html = `<div class="lv-tc-s1-summary">检测到 <b>${total}</b> 列，自动识别 <b>${recCnt}</b> 列`;
        if (unrecognized.length)
          html += `，<span class="lv-tc-warn">${unrecognized.length} 列未识别</span>（可在下一步手动指定）`;
        html += `</div>`;
        html += `<div class="lv-tc-s1-cols">`;
        headers.slice(0, 8).forEach(h => {
          const mapped = fieldMap[h];
          const fd = _TC_FIELD_DEFS.find(f => f.key === mapped);
          const label = fd && mapped !== '__ignore__' ? fd.label : null;
          html += mapped !== '__ignore__'
            ? `<span class="lv-tc-col-tag ok">${h} → ${label}</span>`
            : `<span class="lv-tc-col-tag unknown">${h}</span>`;
        });
        if (headers.length > 8) html += `<span class="lv-tc-col-tag more">+${headers.length - 8} 列…</span>`;
        html += `</div>`;

        statusEl.className = 'lv-tc-s1-status lv-tc-s1-ok';
        statusEl.innerHTML = html;
        document.getElementById('lv-tc-next').disabled = false;
      } catch (err) {
        statusEl.className = 'lv-tc-s1-status lv-tc-s1-error';
        statusEl.textContent = '解析失败：' + err.message;
      }
    };
    reader.readAsText(file, 'UTF-8');
  }

  _tcRenderColMap() {
    const wrap = document.getElementById('lv-tc-col-map-wrap');
    const fieldOpts = _TC_FIELD_DEFS.map(f =>
      `<option value="${f.key}"${f.required ? ' data-req="1"' : ''}>${f.label}${f.required ? ' *' : ''}</option>`
    ).join('');

    const rows = this._tcRawHeaders.map(h => {
      const curVal = this._tcFieldMap[h] || '__ignore__';
      const isUnknown = curVal === '__ignore__';
      return `<tr class="${isUnknown ? 'lv-tc-row-unknown' : ''}">
        <td class="lv-tc-cm-src">${h}</td>
        <td class="lv-tc-cm-arrow">→</td>
        <td class="lv-tc-cm-dst">
          <select data-csv-col="${h}">
            ${fieldOpts.replace(`value="${curVal}"`, `value="${curVal}" selected`)}
          </select>
        </td>
        <td class="lv-tc-cm-sample">${this._tcGetSample(h)}</td>
      </tr>`;
    }).join('');

    wrap.innerHTML = `
      <div class="lv-tc-cm-legend">
        <span class="lv-tc-col-tag ok">已识别</span>
        <span class="lv-tc-col-tag unknown">未识别（请手动选择）</span>
      </div>
      <table class="lv-tc-cm-table">
        <thead><tr>
          <th>CSV 列名</th><th></th><th>系统字段</th><th>示例值</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>`;

    wrap.querySelectorAll('select').forEach(sel => {
      sel.addEventListener('change', () => {
        this._tcFieldMap[sel.dataset.csvCol] = sel.value;
        sel.closest('tr').classList.toggle('lv-tc-row-unknown', sel.value === '__ignore__');
        this._tcValidateStep2();
      });
    });
    this._tcValidateStep2();
  }

  _tcGetSample(csvHeader) {
    const samples = [];
    for (const line of this._tcRawLines) {
      if (samples.length >= 2) break;
      const sep = line.includes('\t') ? '\t' : ',';
      const cols = line.split(sep).map(c => c.trim().replace(/^"|"$/g, ''));
      const idx  = this._tcRawHeaders.indexOf(csvHeader);
      const v    = idx >= 0 ? (cols[idx] || '') : '';
      if (v) samples.push(v);
    }
    return `<span class="lv-tc-cm-sample-val">${samples.join(' / ') || '—'}</span>`;
  }

  _tcValidateStep2() {
    const required = ['_level', 'title', '_tc_raw_type'];
    const mapped   = new Set(Object.values(this._tcFieldMap));
    const ok = required.every(k => mapped.has(k));
    document.getElementById('lv-tc-confirm').disabled = !ok;

    const hint = document.getElementById('lv-tc-s2-hint');
    if (!ok) {
      const missing = required.filter(k => !mapped.has(k))
        .map(k => _TC_FIELD_DEFS.find(f => f.key === k)?.label || k);
      hint.innerHTML = `<span class="lv-tc-warn">请为以下必须字段指定列：${missing.join('、')}</span>`;
    } else {
      const ignoreCnt = Object.values(this._tcFieldMap).filter(v => v === '__ignore__').length;
      hint.textContent = `必须字段已就绪。${ignoreCnt ? `（${ignoreCnt} 列将被忽略）` : ''}`;
    }
  }

  /** 检测 CSV 分隔符：优先 tab，其次分号，最后逗号 */
  _detectSep(line) {
    if (line.includes('\t')) return '\t';
    if (line.includes(';'))  return ';';
    return ',';
  }

  /** 正确解析一行 CSV，支持双引号包裹含分隔符的字段 */
  _parseCsvLine(line, sep) {
    if (sep === '\t' || sep === ';') {
      return line.split(sep).map(c => c.trim().replace(/^"|"$/g, ''));
    }
    // 逗号分隔时使用完整 quoted-field 解析
    const result = [];
    let i = 0;
    while (i < line.length) {
      if (line[i] === '"') {
        let field = '';
        i++;
        while (i < line.length) {
          if (line[i] === '"' && line[i + 1] === '"') { field += '"'; i += 2; }
          else if (line[i] === '"') { i++; break; }
          else { field += line[i++]; }
        }
        result.push(field.trim());
        if (line[i] === ',') i++;
      } else {
        const end = line.indexOf(',', i);
        if (end === -1) { result.push(line.slice(i).trim()); break; }
        result.push(line.slice(i, end).trim());
        i = end + 1;
      }
    }
    return result;
  }

  _tcApplyColMap() {
    const sep = this._tcSep || this._detectSep(this._tcRawLines[0] || '');
    const rows = [];
    for (const line of this._tcRawLines) {
      const cols = this._parseCsvLine(line, sep);
      if (cols.some(c => c.includes('PFMEA'))) continue;

      const raw = {};
      this._tcRawHeaders.forEach((h, idx) => { raw[h] = cols[idx] || ''; });

      const row = {};
      for (const [csvH, fieldKey] of Object.entries(this._tcFieldMap)) {
        if (fieldKey === '__ignore__') continue;
        row[fieldKey] = raw[csvH] || '';
      }

      const lvParsed = parseInt(row._level ?? '', 10);
      if (isNaN(lvParsed) || lvParsed <= 0) continue;
      row._level = lvParsed;

      if (row._tc_raw_type) {
        const raw = row._tc_raw_type.trim();
        // 先精确匹配，再去掉括号后缀（如"总装操作（Product）"→"总装操作"）后重试
        const stripped = raw.replace(/[（(][^）)]*[）)]\s*$/g, '').trim();
        const nt = _TC_TYPE_MAP[raw] || _TC_TYPE_MAP[stripped];
        if (!nt) {
          console.warn('[TC import] 未识别的零组件类型，已跳过:', raw, row);
          continue;
        }
        row.node_type = nt;
      } else {
        continue; // 无类型字段，跳过
      }
      delete row._tc_raw_type;

      // 父级 VPPS 链接
      if (row._parent_vpps) {
        row.parent_vpps = row._parent_vpps;
        delete row._parent_vpps;
      }

      rows.push(row);
    }
    return rows;
  }

  async importTc() {
    if (!this.currentVersionGid) return;
    const rows = this._tcApplyColMap();
    if (!rows.length) { this._toast('无有效数据行', 'warn'); return; }
    const btn = document.getElementById('lv-tc-confirm');
    const origText = btn.textContent;
    btn.textContent = '导入中…';
    btn.disabled = true;
    try {
      const resp = await this._cf(`/api/bop/versions/${this.currentVersionGid}/import-tc`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rows }),
      });
      document.getElementById('lv-modal-import-tc').classList.add('hidden');
      await this.loadVersions();
      this._onReloadNeeded();
      const skipMsg = resp.skipped ? `，跳过重复 ${resp.skipped} 行` : '';
      this._toast(`导入完成，共 ${resp.count ?? rows.length} 条${skipMsg}`, 'ok');
    } catch (e) {
      this._toast('导入失败: ' + e.message, 'error');
      btn.textContent = origText;
      btn.disabled = false;
    }
  }

  // ── Fork 类型切换 ─────────────────────────────────────────────────────
  _onForkTypeChange() {
    const type = document.getElementById('lv-fork-type')?.value;
    const isTmpl     = type === 'save-as-template';
    const isFromTmpl = type === 'fork-from-template';

    const _show = (id, visible) => {
      const el = document.getElementById(id);
      if (el) el.style.display = visible ? '' : 'none';
    };
    _show('lv-fork-tag-row',       !isTmpl);
    _show('lv-fork-tmpl-name-row',  isTmpl);
    _show('lv-fork-bop-name-row',  !isTmpl);
    _show('lv-fork-family-row',    !isTmpl);
    _show('lv-fork-factory-row',    isTmpl);
    _show('lv-fork-copy-op-row',    isTmpl);

    const btn = document.getElementById('lv-fork-confirm');
    if (btn) btn.textContent = isTmpl ? '保存为模板' : isFromTmpl ? '从模板新建' : '执行 Fork';

    const titleEl = document.querySelector('#lv-modal-fork .lv-modal-title');
    if (titleEl) {
      titleEl.textContent = isTmpl ? '保存为工厂 BOP 模板'
        : isFromTmpl ? '从工厂 BOP 模板新建 working BOP'
        : 'BOP Fork / 克隆';
    }

    const noteInput = document.getElementById('lv-fork-note');
    if (noteInput) {
      noteInput.placeholder = isFromTmpl ? '如：基于X12工厂模板，适配X15车型'
        : isTmpl ? ''
        : '如：从X11 fork，适配X12新工位布局';
    }

    this._rebuildSrcDropdown(type);
  }

  /** 根据操作类型过滤来源版本下拉，保留当前选中值 */
  _rebuildSrcDropdown(type) {
    const srcSel = document.getElementById('lv-fork-src');
    if (!srcSel) return;
    const prevVal = srcSel.value || this._pendingForkSrc || '';
    srcSel.innerHTML = '<option value="">-- 选择来源 BOP 版本 --</option>';
    const filtered = type === 'fork-from-template'
      ? this._allVersions.filter(v => v.version_type === 'template')
      : type === 'fork'
      ? this._allVersions.filter(v => v.version_type !== 'template')
      : this._allVersions;   // save-as-template: 所有版本均可
    for (const ver of filtered) {
      const opt = document.createElement('option');
      opt.value = ver.gid;
      const prefix = ver.version_type === 'template' ? '[模板] ' : '';
      opt.textContent = prefix + (ver.bop_name || '') + ' / ' + (ver.version_tag || ver.gid.slice(-6));
      srcSel.appendChild(opt);
    }
    if (prevVal) srcSel.value = prevVal;
  }

  // ── BOP Fork 弹窗 ──────────────────────────────────────────────────────

  async openForkModal(srcGid = null) {
    // 确保工厂缓存已加载（save-as-template 需要工厂下拉）
    if (this._factoriesCache.length === 0) {
      try {
        const res = await this._cf('/api/bop/factories');
        this._factoriesCache = res.data || [];
      } catch (_) { this._factoriesCache = []; }
    }

    const famSel = document.getElementById('lv-fork-family');
    const facSel = document.getElementById('lv-fork-factory');
    famSel.innerHTML = '<option value="">-- 自成新版本族 --</option>';
    facSel.innerHTML = '<option value="">-- 选择工厂 --</option>';

    const famSeen = new Set();
    for (const ver of this._allVersions) {
      const fgid = ver.version_family_gid || ver.gid;
      if (!famSeen.has(fgid)) {
        famSeen.add(fgid);
        const fopt = document.createElement('option');
        fopt.value = fgid;
        fopt.textContent = ver.bop_name || `族 ${fgid.slice(-6)}`;
        famSel.appendChild(fopt);
      }
    }
    for (const fac of (this._factoriesCache || [])) {
      const opt = document.createElement('option');
      opt.value = fac.gid;
      opt.textContent = fac.name || fac.gid;
      facSel.appendChild(opt);
    }

    this._pendingForkSrc = srcGid || this.currentVersionGid;
    // 若由模板按钮触发，预设操作类型
    const forkType = this._pendingForkType || 'fork';
    this._pendingForkType = null;
    document.getElementById('lv-fork-type').value       = forkType;
    document.getElementById('lv-fork-tag').value        = '';
    document.getElementById('lv-fork-tmpl-name').value  = '';
    document.getElementById('lv-fork-bop-name').value   = '';
    document.getElementById('lv-fork-note').value       = '';
    document.getElementById('lv-fork-copy-op').checked  = false;
    this._onForkTypeChange();
    document.getElementById('lv-modal-fork').classList.remove('hidden');
  }

  async forkBop() {
    const type    = document.getElementById('lv-fork-type').value;
    const srcGid  = document.getElementById('lv-fork-src').value;
    if (!srcGid) { this._toast('请选择来源版本', 'warn'); return; }

    if (type === 'save-as-template') {
      const tmplName  = document.getElementById('lv-fork-tmpl-name').value.trim();
      const factoryGid = document.getElementById('lv-fork-factory').value;
      const copyOp    = document.getElementById('lv-fork-copy-op').checked;
      if (!tmplName)   { this._toast('模板名称不能为空', 'warn'); return; }
      if (!factoryGid) { this._toast('请选择目标工厂', 'warn'); return; }
      try {
        const res = await this._cf(`/api/bop/versions/${srcGid}/save-as-template`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ factory_gid: factoryGid, template_name: tmplName, copy_operator: copyOp }),
        });
        document.getElementById('lv-modal-fork').classList.add('hidden');
        await this.loadVersions();
        this._toast(`工厂模板"${tmplName}"已创建，共 ${res.entries_count ?? '?'} 条`, 'ok');
      } catch (e) { this._toast('保存模板失败: ' + e.message, 'error'); }
      return;
    }

    const famGid  = document.getElementById('lv-fork-family').value || null;
    const noteInput = document.getElementById('lv-fork-note').value.trim();

    // 版本号自动递增
    const targetFamGid = famGid || null;
    const familyVers = targetFamGid
      ? this._allVersions.filter(v => (v.version_family_gid || v.gid) === targetFamGid && !v.archived_at)
      : this._allVersions.filter(v => {
          const srcVer = this._allVersions.find(x => x.gid === srcGid);
          return srcVer && (v.version_family_gid || v.gid) === (srcVer.version_family_gid || srcVer.gid) && !v.archived_at;
        });
    const maxN = familyVers.reduce((m, v) => {
      const n = parseInt((v.version_tag || '').replace(/^v/i, ''));
      return isNaN(n) ? m : Math.max(m, n);
    }, 0);
    const tag = `v${maxN + 1}`;

    // change_note：用户备注 + 时间戳
    const now = new Date();
    const ts = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')} ${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`;
    const note = noteInput ? `${noteInput}（${ts}）` : `Fork at ${ts}`;

    // bop_name 来自源版本的族群名（项目名）
    const srcVer = this._allVersions.find(v => v.gid === srcGid);
    const bopName = srcVer?.bop_name || null;
    try {
      const res = await this._cf(`/api/bop/versions/${srcGid}/fork`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_version_tag: tag, target_bop_name: bopName || '', target_version_family_gid: famGid, change_note: note }),
      });
      document.getElementById('lv-modal-fork').classList.add('hidden');
      await this.loadVersions();
      const newGid = res.data?.gid || res.gid;
      if (newGid) this.selectVersion(newGid, tag);
      this._toast('Fork 成功', 'ok');
    } catch (e) { this._toast('Fork 失败: ' + e.message, 'error'); }
  }

  // ── 保存为模板弹窗 ──────────────────────────────────────────────────────────

  async openSaveTmplModal() {
    if (this._factoriesCache.length === 0) {
      try {
        const res = await this._cf('/api/bop/factories');
        this._factoriesCache = res.data || [];
      } catch (_) { this._factoriesCache = []; }
    }

    const srcSel = document.getElementById('lv-st-src');
    srcSel.innerHTML = '<option value="">-- 选择来源 BOP 版本 --</option>';
    for (const ver of this._allVersions.filter(v => v.version_type !== 'template' && !v.archived_at)) {
      const opt = document.createElement('option');
      opt.value = ver.gid;
      opt.textContent = (ver.bop_name || '') + ' / ' + (ver.version_tag || ver.gid.slice(-6));
      if (ver.gid === this.currentVersionGid) {
        opt.textContent += '（当前）';
        opt.selected = true;
      }
      srcSel.appendChild(opt);
    }

    const facSel = document.getElementById('lv-st-factory');
    facSel.innerHTML = '<option value="">-- 选择工厂 --</option>';
    for (const fac of this._factoriesCache) {
      const opt = document.createElement('option');
      opt.value = fac.gid;
      opt.textContent = fac.name || fac.gid;
      facSel.appendChild(opt);
    }

    document.getElementById('lv-st-copy-op').checked = false;
    this._updateStNamePreview();
    document.getElementById('lv-modal-save-tmpl').classList.remove('hidden');
  }

  _updateStNamePreview() {
    const srcGid    = document.getElementById('lv-st-src')?.value;
    const facSel    = document.getElementById('lv-st-factory');
    const facGid    = facSel?.value;
    const previewEl = document.getElementById('lv-st-name-preview');
    if (!previewEl) return;

    if (!srcGid || !facGid) {
      previewEl.textContent = '请先选择来源版本和工厂';
      previewEl.style.color = 'var(--subtext0,#a6adc8)';
      return;
    }

    const facName = facSel.options[facSel.selectedIndex]?.textContent || facGid;
    const srcVer  = this._allVersions.find(v => v.gid === srcGid);
    const famGid  = srcVer ? (srcVer.version_family_gid || srcVer.gid) : srcGid;
    const familyVers = this._allVersions.filter(v => (v.version_family_gid || v.gid) === famGid);
    const maxN = familyVers.reduce((m, v) => {
      const n = parseInt((v.version_tag || '').replace(/^v/i, ''));
      return isNaN(n) ? m : Math.max(m, n);
    }, 0);
    const today = new Date();
    const yyyymmdd = `${today.getFullYear()}${String(today.getMonth()+1).padStart(2,'0')}${String(today.getDate()).padStart(2,'0')}`;
    previewEl.textContent = `${facName}_tmpl_v${maxN + 1}_${yyyymmdd}`;
    previewEl.style.color = 'var(--accent,#89b4fa)';
  }

  async saveTmpl() {
    const srcGid   = document.getElementById('lv-st-src')?.value;
    const facGid   = document.getElementById('lv-st-factory')?.value;
    const copyOp   = document.getElementById('lv-st-copy-op')?.checked;
    const tmplName = document.getElementById('lv-st-name-preview')?.textContent;

    if (!srcGid)  { this._toast('请选择来源版本', 'warn'); return; }
    if (!facGid)  { this._toast('请选择目标工厂', 'warn'); return; }
    if (!tmplName || tmplName.startsWith('请先')) { this._toast('模板名称生成失败', 'warn'); return; }

    const btn = document.getElementById('lv-st-confirm');
    const orig = btn.textContent;
    btn.textContent = '保存中…';
    btn.disabled = true;
    try {
      const res = await this._cf(`/api/bop/versions/${srcGid}/save-as-template`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ factory_gid: facGid, template_name: tmplName, copy_operator: copyOp }),
      });
      document.getElementById('lv-modal-save-tmpl').classList.add('hidden');
      await this.loadVersions();
      this._toast(`模板「${tmplName}」已创建，共 ${res.entries_count ?? '?'} 条`, 'ok');
    } catch (e) {
      this._toast('保存模板失败: ' + e.message, 'error');
    } finally {
      btn.textContent = orig;
      btn.disabled = false;
    }
  }

  // ── 从模板新建 Working BOP 弹窗 ────────────────────────────────────────────

  _selectedTmplGid = null;

  async openFromTmplModal() {
    this._selectedTmplGid = null;
    this._ftShowStep(1);

    const listEl = document.getElementById('lv-ft-list');
    listEl.innerHTML = '<div style="padding:20px;text-align:center;color:var(--subtext0,#a6adc8);font-size:12px">加载中…</div>';
    document.getElementById('lv-ft-next').disabled = true;
    document.getElementById('lv-ft-search').value  = '';
    document.getElementById('lv-modal-from-tmpl').classList.remove('hidden');

    this._ftRenderList(this._allVersions.filter(v => v.version_type === 'template' && !v.archived_at));
  }

  _ftShowStep(n) {
    document.getElementById('lv-ft-step1').style.display = n === 1 ? '' : 'none';
    document.getElementById('lv-ft-step2').style.display = n === 2 ? '' : 'none';
  }

  _ftRenderList(templates) {
    const listEl = document.getElementById('lv-ft-list');
    if (!templates.length) {
      listEl.innerHTML = '<div style="padding:20px;text-align:center;color:var(--subtext0,#a6adc8);font-size:12px">暂无可用模板</div>';
      return;
    }
    listEl.innerHTML = '';
    for (const tmpl of templates) {
      const div = document.createElement('div');
      div.dataset.gid = tmpl.gid;
      div.style.cssText = 'padding:10px 12px;border-bottom:1px solid var(--border,#45475a);cursor:pointer;transition:background .1s';
      const facName = this._factoriesCache.find(f => f.gid === tmpl.factory_gid)?.name || tmpl.factory_gid || '工厂未知';
      div.innerHTML = `
        <div style="font-weight:600;font-size:12px">${tmpl.bop_name || tmpl.version_tag || tmpl.gid.slice(-6)}</div>
        <div style="font-size:11px;color:var(--subtext0,#a6adc8);margin-top:3px">${facName}</div>
        <div style="font-size:10px;color:var(--overlay0,#6c7086);margin-top:2px">${(tmpl.created_at || '').slice(0,10)} 保存</div>
      `;
      div.addEventListener('click', () => {
        listEl.querySelectorAll('[data-gid]').forEach(el => {
          el.style.background = '';
          el.style.borderLeft = '';
        });
        div.style.background  = 'var(--surface0,#313244)';
        div.style.borderLeft  = '3px solid var(--accent,#89b4fa)';
        this._selectedTmplGid = tmpl.gid;
        document.getElementById('lv-ft-next').disabled = false;
      });
      listEl.appendChild(div);
    }
  }

  _filterFtList(q) {
    const templates = this._allVersions.filter(v => v.version_type === 'template' && !v.archived_at);
    const filtered  = q.trim()
      ? templates.filter(t => (t.bop_name || '').toLowerCase().includes(q.toLowerCase()))
      : templates;
    this._ftRenderList(filtered);
    if (this._selectedTmplGid) {
      const el = document.querySelector(`#lv-ft-list [data-gid="${this._selectedTmplGid}"]`);
      if (el) {
        el.style.background = 'var(--surface0,#313244)';
        el.style.borderLeft = '3px solid var(--accent,#89b4fa)';
      } else {
        document.getElementById('lv-ft-next').disabled = true;
      }
    }
  }

  async _ftStep2() {
    if (!this._selectedTmplGid) return;

    if (this._projectsCache.length === 0) {
      try {
        const res = await this._cf('/api/projects?limit=200');
        this._projectsCache = (res.data || []).filter(p => !p.is_deleted && p.project_type !== 'gbop');
      } catch (_) { this._projectsCache = []; }
    }
    if (this._factoriesCache.length === 0) {
      try {
        const res = await this._cf('/api/bop/factories');
        this._factoriesCache = res.data || [];
      } catch (_) { this._factoriesCache = []; }
    }

    const tmpl = this._allVersions.find(v => v.gid === this._selectedTmplGid);
    const infoEl = document.getElementById('lv-ft-tmpl-info');
    if (infoEl && tmpl) {
      infoEl.textContent = `来源模板：${tmpl.bop_name || tmpl.version_tag}`;
    }

    const projSel = document.getElementById('lv-ft-project');
    projSel.innerHTML = '<option value="">— 请选择项目 —</option>';
    for (const p of this._projectsCache) {
      const opt = document.createElement('option');
      opt.value = p.gid;
      opt.dataset.factoryGid  = p.factory_gid || '';
      opt.dataset.projectName = p.name || p.gid;
      const fac = this._factoriesCache.find(f => f.gid === p.factory_gid);
      opt.dataset.factoryName = fac ? (fac.name || fac.gid) : '';
      opt.textContent = p.name || p.gid;
      projSel.appendChild(opt);
    }

    const famSel = document.getElementById('lv-ft-family');
    famSel.innerHTML = '<option value="">-- 自成新版本族 --</option>';
    const famSeen = new Set();
    for (const ver of this._allVersions.filter(v => v.version_type !== 'template' && !v.archived_at)) {
      const fgid = ver.version_family_gid || ver.gid;
      if (!famSeen.has(fgid)) {
        famSeen.add(fgid);
        const opt = document.createElement('option');
        opt.value = fgid;
        opt.textContent = ver.bop_name || `族 ${fgid.slice(-6)}`;
        famSel.appendChild(opt);
      }
    }

    document.getElementById('lv-ft-factory-display').value = '';
    document.getElementById('lv-ft-factory').value = '';
    document.getElementById('lv-ft-tag').value = '';
    document.getElementById('lv-ft-bop-name').value = '';
    document.getElementById('lv-ft-note').value = '';
    this._updateFtNamePreview();
    this._ftShowStep(2);
  }

  _updateFtNamePreview() {
    const projSel   = document.getElementById('lv-ft-project');
    const famGidVal = document.getElementById('lv-ft-family')?.value;
    const previewEl = document.getElementById('lv-ft-preview');
    const hidName   = document.getElementById('lv-ft-bop-name');
    const hidTag    = document.getElementById('lv-ft-tag');
    const factDisp  = document.getElementById('lv-ft-factory-display');
    const factHid   = document.getElementById('lv-ft-factory');

    const selectedOpt = projSel?.options[projSel.selectedIndex];
    if (selectedOpt?.value) {
      factDisp.value = selectedOpt.dataset.factoryName || '';
      factHid.value  = selectedOpt.dataset.factoryGid  || '';
    }

    const projName = selectedOpt?.dataset?.projectName || '';
    if (!projName) {
      if (previewEl) { previewEl.textContent = '请先选择项目'; previewEl.style.color = 'var(--subtext0,#a6adc8)'; }
      if (hidName)   hidName.value = '';
      if (hidTag)    hidTag.value  = '';
      return;
    }

    const bopName = projName;
    let nextNum = 1;
    if (famGidVal) {
      const famVers = this._allVersions.filter(v =>
        (v.version_family_gid || v.gid) === famGidVal && !v.archived_at
      );
      const maxN = famVers.reduce((m, v) => {
        const n = parseInt((v.version_tag || '').replace(/^v/i, ''));
        return isNaN(n) ? m : Math.max(m, n);
      }, 0);
      nextNum = maxN + 1;
    }
    const autoTag = `v${nextNum}`;

    if (hidName) hidName.value = bopName;
    if (hidTag)  hidTag.value  = autoTag;
    if (previewEl) {
      previewEl.textContent = famGidVal
        ? `${bopName}  ·  ${autoTag}（族内递增）`
        : `${bopName}  ·  ${autoTag}（新族首版）`;
      previewEl.style.color = 'var(--accent,#89b4fa)';
    }
  }

  async forkFromTmpl() {
    const tag     = document.getElementById('lv-ft-tag')?.value.trim();
    const bopName = document.getElementById('lv-ft-bop-name')?.value.trim();
    const famGid  = document.getElementById('lv-ft-family')?.value.trim() || null;
    const project = document.getElementById('lv-ft-project')?.value.trim() || null;
    const note    = document.getElementById('lv-ft-note')?.value.trim();

    if (!this._selectedTmplGid) { this._toast('请先选择模板', 'warn'); return; }
    if (!project)  { this._toast('请选择所属项目', 'warn'); return; }
    if (!tag)      { this._toast('版本号生成失败，请重选项目', 'warn'); return; }
    if (!bopName)  { this._toast('BOP 名称生成失败，请重选项目', 'warn'); return; }

    const now = new Date();
    const ts  = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')} ${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`;
    const changeNote = note ? `${note}（${ts}）` : `fork-from-template at ${ts}`;

    const btn  = document.getElementById('lv-ft-confirm');
    const orig = btn.textContent;
    btn.textContent = '创建中…';
    btn.disabled = true;
    try {
      const res = await this._cf(`/api/bop/versions/${this._selectedTmplGid}/fork`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_version_tag:        tag,
          target_bop_name:           bopName,
          target_version_family_gid: famGid,
          change_note:               changeNote,
          version_type:              'working',
        }),
      });
      document.getElementById('lv-modal-from-tmpl').classList.add('hidden');
      await this.loadVersions();
      const newGid = res.data?.gid || res.gid;
      if (newGid) this.selectVersion(newGid, tag);
      this._toast(`Working BOP「${bopName} / ${tag}」创建成功`, 'ok');
    } catch (e) {
      this._toast('创建失败: ' + e.message, 'error');
    } finally {
      btn.textContent = orig;
      btn.disabled = false;
    }
  }

  // ── 从 GBOP 导入弹窗 ───────────────────────────────────────────────────

  async openImportGbopModal() {
    if (!this.currentVersionGid) { this._toast('请先选择 BOP 版本', 'warn'); return; }
    const ver = this._allVersions.find(v => v.gid === this.currentVersionGid);
    document.getElementById('lv-gbop-target-name').value = ver
      ? (ver.version_tag || ver.gid.slice(-6))
      : this.currentVersionGid.slice(-6);

    const gbopSel = document.getElementById('lv-gbop-src');
    gbopSel.innerHTML = '<option value="">-- 加载中… --</option>';
    try {
      const res = await this._cf('/api/gbop/versions?limit=100');
      const gbopVers = res.data || [];
      gbopSel.innerHTML = '<option value="">-- 选择 GBOP 版本 --</option>';
      for (const v of gbopVers) {
        const opt = document.createElement('option');
        opt.value = v.gid;
        opt.textContent = v.version_tag || v.gid.slice(-6);
        gbopSel.appendChild(opt);
      }
    } catch (_) {
      gbopSel.innerHTML = '<option value="">-- 加载失败 --</option>';
    }
    document.getElementById('lv-modal-import-gbop').classList.remove('hidden');
  }

  async importGbop() {
    if (!this.currentVersionGid) return;
    const gbopGid = document.getElementById('lv-gbop-src').value;
    if (!gbopGid) { this._toast('请选择 GBOP 来源版本', 'warn'); return; }
    try {
      console.log('[Import-GBOP] target:', this.currentVersionGid, 'src:', gbopGid);
      const resp = await this._cf(`/api/bop/versions/${this.currentVersionGid}/copy-from-gbop/${gbopGid}`, {
        method: 'POST',
      });
      console.log('[Import-GBOP] response:', resp);
      document.getElementById('lv-modal-import-gbop').classList.add('hidden');
      await this.loadVersions();
      this._onReloadNeeded();
      this._toast('GBOP导入完成', 'ok');
    } catch (e) {
      console.error('[Import-GBOP] error:', e);
      this._toast('导入失败: ' + e.message, 'error');
    }
  }
}
