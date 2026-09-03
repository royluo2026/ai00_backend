'use strict';
/**
 * assoc_panel.js — BOP Lineage 关联面板
 *
 * 多 tab 清单面板，显示绑定状态，支持拖拽创建关联。
 * 不接受任何 drop（只输出 drag）。
 */

// localStorage 账号隔离
function _assocLsk(base) {
  try { const u = window.parent?._authUser || window.top?._authUser || window._authUser; const g = u?.gid || u?.user_gid || ''; return g ? `${g}:${base}` : base; } catch { return base; }
}

async function _assocInvoke(_cloudFetch, id, payload) {
  const response = await _cloudFetch(`/api/v1/capabilities/${id}:invoke`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ version: 1, payload }),
  });
  const result = response?.data;
  if (response?.success !== true || result?.ok !== true) {
    const detail = result?.error || response?.error || {};
    const error = new Error(detail.message || `能力调用失败：${id}@1`);
    error.code = detail.code || 'capability_invocation_failed';
    throw error;
  }
  return result.data;
}

/* ── 状态常量 ────────────────────────────────────────── */
const _TASK_STATUSES = [
  { value: 'open',        label: '待办' },
  { value: 'in_progress', label: '进行中' },
  { value: 'completed',   label: '已完成' },
  { value: 'cancelled',   label: '已取消' },
];
const _ISSUE_STATUSES = [
  { value: 'open',        label: '待处理' },
  { value: 'in_progress', label: '处理中' },
  { value: 'resolved',    label: '已解决' },
  { value: 'closed',      label: '已关闭' },
];

/** 适配器：每种清单类型的数据获取和渲染 */
const ASSOC_ADAPTERS = {
  pbom: {
    label: 'PBOM',
    icon:  '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/></svg>',
    hasLinkedFilter: true,
    linkedFilterRequiresSelection: true,  // 默认模式只返回已关联零件，必须选了具体版本才有意义
    filter: {
      type: 'version',
      fetchOptions: async (cf) => {
        const res = await _assocInvoke(cf, 'craft.pbom.version.search', { limit: 200 });
        return (res?.items || []).map(v => ({
          gid: v.gid || v.version_gid,
          name: v.name || v.version_tag || v.gid || v.version_gid,
        }));
      },
      allLabel: '已关联零件',
    },
    treeParent: 'parent_gid',
    groupFields: null,
    filterFields: null,
    fetchData: async (cf, versionGid, filterGid) => {
      if (filterGid) {
        // 选了具体 PBOM 版本 → 直接获取该版本的全部零件
        const res = await _assocInvoke(cf, 'craft.pbom.part.search', {
          version_gid: filterGid,
          limit: 500,
        });
        return res?.items || [];
      }
      // 默认：显示已关联到当前 BOP 版本的零件
      if (!versionGid) return [];
      const res = await _assocInvoke(cf, 'craft.bop.linked_parts.get', {
        version_gid: versionGid,
      });
      return res?.items || [];
    },
    getLinkType: () => 'pbom_part',
    getRefGid:   item => item.gid,
    getTitle:    item => item.name || item.part_no || '(无名称)',
    getVpps:     item => item.vpps || item.part_no || '',
    getNodeType: () => 'part',
    getIsPrimary: () => true,
  },
  issue: {
    label: '问题',
    icon:  '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>',
    filter: {
      type: 'list',
      itemType: 'issue',
      allLabel: '全部问题',
    },
    treeParent: null,
    groupFields: [
      { key: 'none',   label: '不分组' },
      { key: 'status', label: '按状态' },
    ],
    filterFields: [
      { key: 'status', label: '状态', options: _ISSUE_STATUSES },
    ],
    fetchData: async (cf, _vgid, filterGid) => {
      const q = filterGid ? `?list_gid=${filterGid}&limit=500` : '?limit=500';
      const res = await _assocInvoke(cf, 'project.issue.read.atomic.issues_search', {
        ...(filterGid ? { list_gid: filterGid } : {}), page_size: 500,
      });
      return res?.data || [];
    },
    getLinkType: () => 'issue',
    getRefGid:   item => item.gid,
    getTitle:    item => item.title || '(无标题)',
    getVpps:     () => '',
    getNodeType: () => 'issue',
    getIsPrimary: () => false,
    getStatus:   item => item.status || 'open',
    getDate:     item => item.plan_start || item.created_at || '',
  },
  task: {
    label: '任务',
    icon:  '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg>',
    filter: {
      type: 'list',
      itemType: 'task',
      allLabel: '全部任务',
    },
    treeParent: null,
    groupFields: [
      { key: 'none',     label: '不分组' },
      { key: 'status',   label: '按状态' },
      { key: 'priority', label: '按优先级' },
    ],
    filterFields: [
      { key: 'status', label: '状态', options: _TASK_STATUSES },
    ],
    fetchData: async (cf, _vgid, filterGid) => {
      const q = filterGid ? `?list_gid=${filterGid}&limit=500` : '?limit=500';
      const res = await _assocInvoke(cf, 'project.task.read.atomic.tasks_search', {
        ...(filterGid ? { list_gid: filterGid } : {}), page_size: 500,
      });
      return res?.data || [];
    },
    getLinkType: () => 'task_custom',
    getRefGid:   item => item.gid,
    getTitle:    item => item.title || '(无标题)',
    getVpps:     () => '',
    getNodeType: () => 'non_standard_task',
    getIsPrimary: () => false,
    getStatus:   item => item.status || 'open',
    getDate:     item => item.plan_start || item.due_date || item.created_at || '',
  },
  factory_tool: {
    label: '工具',
    icon:  '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z"/></svg>',
    filter: null,
    treeParent: null,
    groupFields: null,
    filterFields: null,
    fetchData: async (cf) => {
      const res = await _assocInvoke(cf, 'factory.asset.search', {
        asset_type: 'tool',
        limit: 500,
      });
      return res?.data || res?.items || [];
    },
    getLinkType: () => 'physical_tool',
    getRefGid:   item => item.gid,
    getTitle:    item => item.name || item.asset_no || '(无名称)',
    getVpps:     item => item.asset_no || '',
    getNodeType: () => 'tool_factory',
    getIsPrimary: () => true,
  },
  gbop: {
    label: 'GBOP',
    icon:  '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/></svg>',
    hasLinkedFilter: true,
    filter: {
      type: 'version',
      fetchOptions: async (cf) => {
        const res = await _assocInvoke(cf, 'craft.gbop.release.search', { include_archived: false });
        return (res?.items || [])
          .filter(v => !v.archived_at)
          .map(v => ({ gid: v.gid, name: v.name || v.gid }));
      },
      allLabel: '全部版本',
    },
    treeParent: 'parent_gid',
    groupFields: null,
    filterFields: null,
    fetchData: async (cf, _vgid, filterGid) => {
      if (filterGid) {
        const res = await _assocInvoke(cf, 'craft.gbop.catalog.read', {
          operation: 'entries.list', version_gid: filterGid,
        });
        return res?.items || res?.data || [];
      }
      const vRes = await _assocInvoke(cf, 'craft.gbop.release.search', { include_archived: false });
      const versions = (vRes?.items || []).filter(v => !v.archived_at);
      const all = [];
      for (const v of versions) {
        try {
          const eRes = await _assocInvoke(cf, 'craft.gbop.catalog.read', {
            operation: 'entries.list', version_gid: v.gid,
          });
          const entries = eRes?.items || eRes?.data || [];
          entries.forEach(e => { e._gbop_version_name = v.name || v.gid; });
          all.push(...entries);
        } catch (_) { /* skip */ }
      }
      return all;
    },
    getLinkType: () => 'gbop',
    getRefGid:   item => item.gid,
    getTitle:    item => item.vpps_desc || item.vpps || item.title || item.name || '(无名称)',
    getVpps:     item => item.vpps || '',
    getNodeType: () => 'operation',
    getIsPrimary: () => true,
  },
  /** gbop_nav — 车型工序导航卡专用，linkMap 来自 gbop_nav_bindings */
  gbop_nav: {
    label: 'GBOP',
    icon:  '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/></svg>',
    hasLinkedFilter: true,
    filter: {
      type: 'version',
      fetchOptions: async (cf) => {
        const res = await _assocInvoke(cf, 'craft.gbop.release.search', { include_archived: false });
        return (res?.items || []).filter(v => !v.archived_at).map(v => ({ gid: v.gid, name: v.name || v.gid }));
      },
      allLabel: '全部版本',
    },
    treeParent: 'parent_gid',
    groupFields: null,
    filterFields: null,
    fetchData: async (cf, _vgid, filterGid) => {
      if (filterGid) {
        const res = await _assocInvoke(cf, 'craft.gbop.catalog.read', {
          operation: 'entries.list', version_gid: filterGid,
        });
        return res?.items || res?.data || [];
      }
      const vRes = await _assocInvoke(cf, 'craft.gbop.release.search', { include_archived: false });
      const versions = (vRes?.items || []).filter(v => !v.archived_at);
      const all = [];
      for (const v of versions) {
        try {
          const eRes = await _assocInvoke(cf, 'craft.gbop.catalog.read', {
            operation: 'entries.list', version_gid: v.gid,
          });
          const entries = eRes?.items || eRes?.data || [];
          entries.forEach(e => { e._gbop_version_name = v.name || v.gid; });
          all.push(...entries);
        } catch (_) {}
      }
      return all;
    },
    getLinkType: () => 'gbop',
    getRefGid:   item => item.gid,
    getTitle:    item => item.vpps_desc || item.vpps || item.title || item.name || '(无名称)',
    getVpps:     item => item.vpps || '',
    getNodeType: () => 'operation',
    getIsPrimary: () => true,
    /** 使用 gbop_nav_bindings 作为 linkMap 数据源（keyed by gbop_op_entry_gid） */
    getLinkSummary: async (cf, versionGid) => {
      if (!versionGid || versionGid === 'bn_nav') return {};
      try {
        const res = await _assocInvoke(cf, 'craft.gbop.navigation.read', {
          operation: 'link_summary',
          pbom_version_gid: versionGid,
        });
        return res?.data || {};
      } catch (_) { return {}; }
    },
  },

  /** pbom_nav — 车型工序导航卡零件视图，工序视图看 PBOM 专用
   *  versionGid = 已在主 UI 选好的 PBOM 版本 GID（来自 bop_nav.js）
   *  linkMap 来自 gbop_nav_bindings（转置为 pbom_entry_gid 为键） */
  pbom_nav: {
    label: 'PBOM零件',
    icon:  '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/></svg>',
    hasLinkedFilter: true,
    // 版本已由主 UI（bop_nav）选好，无需额外版本筛选下拉
    filter: null,
    treeParent: 'parent_gid',
    groupFields: null,
    filterFields: null,
    fetchData: async (cf, vgid, filterGid) => {
      const gid = filterGid || vgid;
      if (!gid || gid === 'bn_nav') return [];
      const res = await _assocInvoke(cf, 'craft.pbom.part.search', {
        version_gid: gid,
        limit: 500,
      });
      return res?.items || [];
    },
    getLinkType: () => 'pbom_part',
    getRefGid:   item => item.gid,
    getTitle:    item => item.name || item.part_no || '(无名称)',
    getVpps:     item => item.vpps || item.part_no || '',
    getNodeType: () => 'part',
    getIsPrimary: () => true,
    /** 从 gbop_nav_bindings 推导 pbom_entry_gid 关联状态（versionGid = PBOM 版本 GID） */
    getLinkSummary: async (cf, versionGid) => {
      if (!versionGid || versionGid === 'bn_nav') return {};
      try {
        const res = await _assocInvoke(cf, 'craft.gbop.navigation.read', {
          operation: 'link_summary',
          pbom_version_gid: versionGid,
        });
        const gbopMap = res?.data || {};
        // 转置：以 pbom_entry_gid 为键（原 bop_entry_gid 字段存的是 pbom_entry_gid）
        const pbomMap = {};
        for (const v of Object.values(gbopMap)) {
          if (v.bop_entry_gid) pbomMap[v.bop_entry_gid] = { is_valid: true };
        }
        return pbomMap;
      } catch (_) { return {}; }
    },
  },
  bop_working: {
    label: '车型工序',
    icon:  '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><path d="M14 17.5h7M17.5 14v7"/></svg>',
    filter: null,
    /** 启用树形渲染：item.parent_gid 作为父节点键 */
    treeParent: 'parent_gid',
    /** 支持线体（line_process）筛选 */
    hasLineFilter: true,
    groupFields: null,
    filterFields: null,
    /** 获取 PBOM 版本名 + 项目名，或 need_select 信息（BOP 未绑定 PBOM 时） */
    getHeader: async (cf, versionGid, panel) => {
      if (!versionGid) return null;
      try {
        const override = panel?._bopPbomGid ? `?pbom_version_gid=${panel._bopPbomGid}` : '';
        const res = await _assocInvoke(cf, 'craft.gbop.station_autolink.preview', {
          operation: 'preview',
          bop_gid: versionGid,
          ...(panel?._bopPbomGid ? { pbom_version_gid: panel._bopPbomGid } : {}),
        });
        if (res?.need_select) return { need_select: true, pbom_versions: res.pbom_versions || [] };
        return res?.pbom_version || null;
      } catch (_) { return null; }
    },
    fetchData: async (cf, versionGid, _filterGid, panel) => {
      if (!versionGid) return [];
      const override = panel?._bopPbomGid ? `?pbom_version_gid=${panel._bopPbomGid}` : '';
      const res = await _assocInvoke(cf, 'craft.gbop.station_autolink.preview', {
        operation: 'preview',
        bop_gid: versionGid,
        ...(panel?._bopPbomGid ? { pbom_version_gid: panel._bopPbomGid } : {}),
      });
      if (res?.need_select) return [];
      // 存线体列表供筛选条渲染
      if (panel && Array.isArray(res?.lines)) panel._availableLines = res.lines;
      return res?.data || [];
    },
    getLinkType: () => 'process_station',
    getRefGid:   item => item.gid,
    getTitle:    item => item.title || item.vpps || item.gid,
    getVpps:     item => item.vpps || '',
    getNodeType: item => item.type || 'process',
    getIsPrimary: () => true,
    getStatus:   item => item.linked ? 'confirmed' : 'pending',
    /** linkMap：直接从 fetchData 结果中读取 linked 字段（跳过默认 link-summary 请求） */
    getLinkSummary: async (cf, versionGid, panel) => {
      if (!versionGid) return {};
      try {
        const override = panel?._bopPbomGid ? `?pbom_version_gid=${panel._bopPbomGid}` : '';
        const res = await _assocInvoke(cf, 'craft.gbop.station_autolink.preview', {
          operation: 'preview',
          bop_gid: versionGid,
          ...(panel?._bopPbomGid ? { pbom_version_gid: panel._bopPbomGid } : {}),
        });
        const map = {};
        for (const item of res?.data || []) {
          if (item.linked) map[item.gid] = { is_valid: true };
        }
        return map;
      } catch (_) { return {}; }
    },
    actions: [
      {
        label: 'Auto-Link → 工序绑工位',
        execute: async (cf, versionGid, toast, panel) => {
          const bodyObj = panel?._bopPbomGid ? { pbom_version_gid: panel._bopPbomGid } : {};
          if (panel?._selectedLineGids?.size > 0) {
            bodyObj.line_gids = [...panel._selectedLineGids];
          }
          const res = await _assocInvoke(cf, 'craft.gbop.station_autolink.change.apply', {
            operation: 'apply',
            bop_gid: versionGid,
            pbom_version_gid: bodyObj.pbom_version_gid || null,
            line_gids: bodyObj.line_gids || null,
          });
          // 若是通过面板选择的 PBOM（未写入 BOP），Auto-Link 成功后清除 override（已写入 bop_versions）
          if (panel && bodyObj.pbom_version_gid && res?.ok) panel._bopPbomGid = null;
          const lineInfo = bodyObj.line_gids ? `（${bodyObj.line_gids.length} 条线体）` : '';
          toast(`Auto-Link 完成${lineInfo}：创建 ${res?.created || 0} 个节点，跳过 ${res?.skipped || 0}`, 'ok');
        },
      },
      {
        label: '撤销关联',
        danger: true,
        execute: async (cf, versionGid, toast) => {
          if (!confirm('确定撤销所有已关联的工序、操作和零件节点？此操作不可恢复。')) return;
          const res = await _assocInvoke(cf, 'craft.gbop.station_autolink.change.apply', {
            operation: 'undo',
            bop_gid: versionGid,
            mode: 'soft',
          });
          toast(`已撤销：删除 ${res?.deleted || 0} 个节点`, 'ok');
        },
      },
      {
        label: '【超管】硬删除关联',
        danger: true,
        superAdminOnly: true,
        execute: async (cf, versionGid, toast) => {
          if (!confirm('【超管】硬删除：将彻底删除所有工序/操作/零件节点及其链接，无法恢复！确定继续？')) return;
          const res = await _assocInvoke(cf, 'craft.gbop.station_autolink.change.apply', {
            operation: 'undo',
            bop_gid: versionGid,
            mode: 'hard',
          });
          toast(`硬删除完成：永久删除 ${res?.deleted || 0} 个节点`, 'ok');
        },
      },
      {
        label: '📷 工序截图',
        skipPostRefresh: true,
        execute: async (cf, versionGid, toast, panel) => {
          const lineGids = [...(panel._selectedLineGids || [])];
          if (lineGids.length !== 1) { toast('请选择恰好一条线体', 'warn'); return; }
          const lineGid = [...lineGids][0];
          // lineage_view 可能嵌套在 craft_hub 内（window.parent=craft_hub 而非 workspace），
          // 需用 window.top 到达 workspace 层拿到 cad_sim 注册的入口
          const capture = (window.top || window.parent)?._cadSimCapture;
          if (!capture) {
            toast('数模仿真面板未初始化，请先打开并连接数模仿真', 'warn');
            return;
          }
          toast('工序截图已启动…');
          // progressCb：每完成一个工序即更新状态栏 + 内联刷新缩略图
          let captureCount = 0;
          capture(lineGid, (op, url) => {
            captureCount++;
            const topWin = window.top || window.parent;
            topWin?._showCaptureProgress?.(`工序截图 ${captureCount} ✓  ${op.title}`);
            // 直接更新 picMap 并重渲行，无需重载数据
            panel._picMap.set(op.bop_entry_gid, url);
            panel._reRenderBody();
          });
        },
      },
      {
        label: '🗑 清除附图',
        danger: true,
        execute: async (cf, versionGid, toast, panel) => {
          const lineGids = [...(panel._selectedLineGids || [])];
          if (lineGids.length !== 1) { toast('请先选择一条线体', 'warn'); return; }
          const lineGid = lineGids[0];
          if (!confirm('确定清除该线体所有工序的流程图片（process_flow_pic）？')) return;

          const opsRes = await _assocInvoke(cf, 'craft.bop.line_operation_catia.read', {
            line_entry_gid: lineGid,
          });
          const ops = opsRes?.data || [];
          if (!ops.length) { toast('未找到工序节点', 'warn'); return; }

          let cleared = 0;
          for (const op of ops) {
            try {
              await _assocInvoke(cf, 'craft.bop.entry.change.apply', {
                operation: 'update',
                entry_gid: op.bop_entry_gid,
                updates: { process_flow_pic: [] },
              });
              cleared++;
            } catch (e) { console.error('[清除附图]', op.bop_entry_gid, e); }
          }
          toast(`已清除 ${cleared} 个工序的流程图片`, 'ok');
        },
      },
      {
        label: '▶ 演示关联',
        skipPostRefresh: true,   // 演示不修改数据，结束后不触发 _reload
        execute: async (cf, versionGid, toast, panel) => {
          const override = panel?._bopPbomGid ? `?pbom_version_gid=${panel._bopPbomGid}` : '';
          const res = await _assocInvoke(cf, 'craft.gbop.station_autolink.preview', {
            operation: 'preview',
            bop_gid: versionGid,
            ...(panel?._bopPbomGid ? { pbom_version_gid: panel._bopPbomGid } : {}),
          });
          const allItems = res?.data || [];
          const hasLinked = allItems.some(it => it.linked);
          if (!hasLinked) { toast('暂无已关联节点，请先运行 Auto-Link', 'warn'); return; }
          await panel._runDemoAnimation(allItems);  // 等待演示完成
        },
      },
    ],
  },
};

/* ── 状态标签工具 ────────────────────────────────────── */
const _STATUS_LABELS = {};
for (const s of _TASK_STATUSES) _STATUS_LABELS[s.value] = s.label;
for (const s of _ISSUE_STATUSES) _STATUS_LABELS[s.value] = s.label;

const _PRIORITY_LABELS = {
  urgent: '紧急', high: '高', normal: '普通', low: '低',
};


class AssocPanel {
  constructor(opts) {
    this._tabsEl    = opts.tabsEl;
    this._bodyEl    = opts.bodyEl;
    this._versionGid = opts.versionGid;
    this._cf        = opts.cf;
    this._onEntityClick = opts.onEntityClick || (() => {});
    this._resolveStation = opts.resolveStation || (() => null);
    this._showDetailPopover = opts.showDetailPopover || null;
    this._showEntityDetailPopover = opts.showEntityDetailPopover || null;
    this._toast     = opts.toast || (() => {});
    this._onActionComplete  = opts.onActionComplete  || null;
    this._applyActiveState  = opts.applyActiveState  || null;
    // Demo 动画回调（由 lineage.js 传入）
    this._getBopLinkedNodes = opts.getBopLinkedNodes || null;
    this._demoHideNodes     = opts.demoHideNodes     || null;
    this._demoRevealNode    = opts.demoRevealNode    || null;
    this._demoCleanup       = opts.demoCleanup       || null;
    this._demoSetupView     = opts.demoSetupView     || null;
    this._demoPanToStation  = opts.demoPanToStation  || null;

    this._tabs      = [];
    this._activeIdx = -1;
    this._cache     = new Map();
    this._CACHE_TTL = 30000;

    this._filterSelections = {};   // listType → filterGid
    this._viewConfigs = {};        // listType → { groupBy, statusFilter[] }
    this._filterBarEl = null;
    this._configBarEl = null;
    this._actionBarEl = null;
    this._headerBarEl = null;
    this._lineBarEl   = null;      // 线体筛选条（bop_working 专用）
    this._lineBarCollapsed = false;// 线体筛选条折叠状态
    this._linkedFilter = {};       // listType → 'all'|'linked'|'unlinked'
    this._linkedFilterBarEl = null;
    this._bopPbomGid  = null;      // bop_working: 用户临时选择的 PBOM 版本 gid（未写入 BOP 时）
    this._selectedLineGids = new Set();  // bop_working: 选中的线体 gid（空=全选）
    this._availableLines   = [];         // bop_working: 当前 BOP 版本中有匹配工序的线体列表
    this._filterOptionsCache = new Map();
    this._demoRunning  = false;
    this._demoPaused   = false;
    this._demoControlEl = null;
    this._picMap       = new Map();  // bop_entry_gid → url（工序截图内联缩略图）

    this._loadTabConfig();
    this._loadFilterSelections();
    this._loadViewConfigs();
    this._renderTabs();
    if (this._tabs.length > 0) this.activateTab(0);
  }

  /* ── 持久化 ───────────────────────────────────────── */

  _loadTabConfig() {
    const key = _assocLsk(`lv:assocTabs:${this._versionGid}`);
    try {
      const saved = JSON.parse(localStorage.getItem(key));
      if (Array.isArray(saved) && saved.length > 0) {
        this._tabs = saved.filter(t => ASSOC_ADAPTERS[t.listType]);
        return;
      }
    } catch (_) {}
    this._tabs = [{ listType: 'pbom', label: 'PBOM' }];
  }

  _saveTabConfig() {
    localStorage.setItem(_assocLsk(`lv:assocTabs:${this._versionGid}`), JSON.stringify(this._tabs));
  }

  _loadFilterSelections() {
    try {
      const saved = JSON.parse(localStorage.getItem(_assocLsk(`lv:assocFilters:${this._versionGid}`)));
      if (saved && typeof saved === 'object') { this._filterSelections = saved; return; }
    } catch (_) {}
    this._filterSelections = {};
  }

  _saveFilterSelections() {
    localStorage.setItem(_assocLsk(`lv:assocFilters:${this._versionGid}`), JSON.stringify(this._filterSelections));
  }

  _loadViewConfigs() {
    try {
      const saved = JSON.parse(localStorage.getItem(_assocLsk(`lv:assocViewCfg:${this._versionGid}`)));
      if (saved && typeof saved === 'object') { this._viewConfigs = saved; return; }
    } catch (_) {}
    this._viewConfigs = {};
  }

  _saveViewConfigs() {
    localStorage.setItem(_assocLsk(`lv:assocViewCfg:${this._versionGid}`), JSON.stringify(this._viewConfigs));
  }

  _getViewCfg(listType) {
    if (!this._viewConfigs[listType]) {
      this._viewConfigs[listType] = { groupBy: 'none', statusFilter: [] };
    }
    return this._viewConfigs[listType];
  }

  /* ── Tab 栏 ───────────────────────────────────────── */

  _renderTabs() {
    this._tabsEl.innerHTML = '';
    for (let i = 0; i < this._tabs.length; i++) {
      const tab = this._tabs[i];
      const adapter = ASSOC_ADAPTERS[tab.listType];
      const btn = document.createElement('button');
      btn.className = 'lv-assoc-tab' + (i === this._activeIdx ? ' active' : '');
      btn.innerHTML = `${adapter?.icon || ''} <span>${tab.label}</span>`;

      const close = document.createElement('button');
      close.className = 'lv-atab-close';
      close.innerHTML = '&times;';
      close.addEventListener('click', e => { e.stopPropagation(); this.removeTab(i); });
      btn.appendChild(close);

      btn.addEventListener('click', () => this.activateTab(i));
      this._tabsEl.appendChild(btn);
    }

    if (this._tabs.length < 5) {
      const add = document.createElement('button');
      add.className = 'lv-assoc-tab-add';
      add.innerHTML = '+';
      add.title = '添加关联面板';
      add.addEventListener('click', e => this._showAddMenu(e));
      this._tabsEl.appendChild(add);
    }
  }

  _showAddMenu(e) {
    document.querySelectorAll('.lv-assoc-add-menu').forEach(m => m.remove());
    const existing = new Set(this._tabs.map(t => t.listType));
    const available = Object.entries(ASSOC_ADAPTERS).filter(([k]) => !existing.has(k));
    if (available.length === 0) { this._toast('所有类型均已添加', 'ok'); return; }

    const menu = document.createElement('div');
    menu.className = 'lv-assoc-add-menu';
    for (const [key, adapter] of available) {
      const item = document.createElement('div');
      item.className = 'lv-assoc-add-item';
      item.textContent = adapter.label;
      item.addEventListener('click', () => { menu.remove(); this.addTab(key); });
      menu.appendChild(item);
    }

    const r = e.currentTarget.getBoundingClientRect();
    menu.style.position = 'fixed';
    menu.style.left = Math.max(0, r.right - 120) + 'px';
    menu.style.top = r.bottom + 2 + 'px';
    menu.style.zIndex = '999';
    document.body.appendChild(menu);

    const closeHandler = ev => {
      if (!menu.contains(ev.target)) { menu.remove(); document.removeEventListener('click', closeHandler, true); }
    };
    setTimeout(() => document.addEventListener('click', closeHandler, true), 0);
  }

  addTab(listType) {
    if (this._tabs.length >= 5) return;
    const adapter = ASSOC_ADAPTERS[listType];
    if (!adapter) return;
    this._tabs.push({ listType, label: adapter.label });
    this._saveTabConfig();
    this.activateTab(this._tabs.length - 1);
  }

  removeTab(idx) {
    if (idx < 0 || idx >= this._tabs.length) return;
    const removed = this._tabs.splice(idx, 1)[0];
    for (const k of this._cache.keys()) { if (k.startsWith(removed.listType + ':')) this._cache.delete(k); }
    this._filterOptionsCache.delete(removed.listType);
    delete this._filterSelections[removed.listType];
    delete this._viewConfigs[removed.listType];
    this._saveTabConfig();
    this._saveFilterSelections();
    this._saveViewConfigs();

    if (this._tabs.length === 0) {
      this._activeIdx = -1;
      this._renderTabs();
      this._removeFilterBar();
      this._removeConfigBar();
      this._removeActionBar();
      this._removeHeaderBar();
      this._removeLineBar();
      this._bodyEl.innerHTML = '<div class="lv-assoc-empty">点击 + 添加关联面板</div>';
      return;
    }
    this.activateTab(Math.min(idx, this._tabs.length - 1));
  }

  /* ── 筛选条（清单/版本选择） ────────────────────────── */

  async _renderFilterBar(listType) {
    const adapter = ASSOC_ADAPTERS[listType];
    const filterCfg = adapter?.filter;

    // 切换 tab 时清理线体筛选条并重置状态
    this._removeLineBar();
    this._removeLinkedFilterBar();
    if (!adapter?.hasLineFilter) {
      this._selectedLineGids.clear();
      this._availableLines = [];
    }

    // action 按钮（支持 adapter.actions 数组 或 adapter.action 单对象）
    this._removeActionBar();
    const _authUser = (window.top || window.parent)?._authUser || window._authUser;
    const _isSuperAdmin = (_authUser?.role || _authUser?.system_role) === 'super_admin';
    const actionsArr = (adapter.actions
      ? adapter.actions
      : (adapter.action ? [adapter.action] : [])
    ).filter(act => !act.superAdminOnly || _isSuperAdmin);
    if (actionsArr.length > 0) {
      this._actionBarEl = document.createElement('div');
      this._actionBarEl.className = 'lv-assoc-action-bar';
      const triggerBtn = document.createElement('button');
      triggerBtn.className = 'lv-assoc-action-btn lv-assoc-action-trigger';
      triggerBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="5" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="19" cy="12" r="1.5"/></svg> 操作';
      triggerBtn.title = '展开操作命令窗口';
      triggerBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        this._toggleActionsPopup(actionsArr, triggerBtn);
      });
      this._actionBarEl.appendChild(triggerBtn);
      this._bodyEl.parentNode.insertBefore(this._actionBarEl, this._bodyEl);
    }

    // header 标识（如 PBOM 版本名 + 项目名）
    this._removeHeaderBar();
    if (adapter?.getHeader && this._versionGid) {
      this._headerBarEl = document.createElement('div');
      this._headerBarEl.className = 'lv-assoc-header-bar';
      this._headerBarEl.textContent = '加载中…';
      this._bodyEl.parentNode.insertBefore(this._headerBarEl, this._bodyEl);
      // 异步加载，不阻塞面板渲染
      adapter.getHeader(this._cf, this._versionGid, this).then(hdr => {
        if (!this._headerBarEl) return;
        if (!hdr) { this._removeHeaderBar(); return; }
        this._headerBarEl.innerHTML = '';

        if (hdr.need_select) {
          // BOP 未绑定 PBOM：渲染选择下拉
          const hint = document.createElement('span');
          hint.className = 'lv-assoc-hdr-hint';
          hint.textContent = '请选择 PBOM 版本：';
          this._headerBarEl.appendChild(hint);
          const sel = document.createElement('select');
          sel.className = 'lv-assoc-hdr-select';
          const blank = document.createElement('option');
          blank.value = '';
          blank.textContent = '— 选择 —';
          sel.appendChild(blank);
          for (const pv of (hdr.pbom_versions || [])) {
            const opt = document.createElement('option');
            opt.value = pv.gid;
            opt.textContent = pv.display_name || pv.gid;
            if (pv.gid === this._bopPbomGid) opt.selected = true;
            sel.appendChild(opt);
          }
          sel.addEventListener('change', () => {
            this._bopPbomGid = sel.value || null;
            this._cache.clear();
            this._loadAndRender();
          });
          this._headerBarEl.appendChild(sel);
          return;
        }

        const nameEl = document.createElement('span');
        nameEl.className = 'lv-assoc-hdr-name';
        nameEl.textContent = hdr.name || hdr.gid || '';
        this._headerBarEl.appendChild(nameEl);
        if (hdr.project_name) {
          const projEl = document.createElement('span');
          projEl.className = 'lv-assoc-hdr-proj';
          projEl.textContent = hdr.project_name;
          this._headerBarEl.appendChild(projEl);
        }
      }).catch(() => this._removeHeaderBar());
    }

    // 已关联/未关联 页签（仅限支持的适配器，且满足条件时才显示）
    // 注意：必须在 filterCfg 检查之前，filter=null 的适配器（如 pbom_nav）也需要此 tab
    this._removeLinkedFilterBar();
    const _hasValidVersion = this._versionGid && this._versionGid !== 'bn_nav';
    const canShowLinkedFilter = adapter.hasLinkedFilter && _hasValidVersion &&
      (!adapter.linkedFilterRequiresSelection || !!this._filterSelections[listType]);
    if (canShowLinkedFilter) {
      this._linkedFilterBarEl = document.createElement('div');
      this._linkedFilterBarEl.className = 'lv-lf-tabs';
      const cur = this._linkedFilter[listType] || 'all';
      for (const [val, text] of [['all','全部'], ['linked','已关联'], ['unlinked','未关联']]) {
        const btn = document.createElement('button');
        btn.className = 'lv-lf-tab' + (cur === val ? ' active' : '');
        btn.dataset.val = val;
        btn.textContent = text;
        btn.addEventListener('click', () => {
          this._linkedFilter[listType] = val;
          this._linkedFilterBarEl.querySelectorAll('.lv-lf-tab').forEach(b => {
            b.classList.toggle('active', b.dataset.val === val);
          });
          this._reRenderBody();
        });
        this._linkedFilterBarEl.appendChild(btn);
      }
      this._bodyEl.parentNode.insertBefore(this._linkedFilterBarEl, this._bodyEl);
    }

    if (!filterCfg) { this._removeFilterBar(); return; }

    let options = this._filterOptionsCache.get(listType);
    if (!options) {
      try {
        if (filterCfg.type === 'list') {
          const _cloudFetch = this._cf;
          const res = await (window.top?.AI00ExistingCapabilityClient || window.AI00ExistingCapabilityClient)
            .call('project.lists.search', { itemType: filterCfg.itemType });
          options = (res.data || []).map(l => ({ gid: l.gid, name: l.name || l.gid }));
        } else if (filterCfg.type === 'version') {
          options = await filterCfg.fetchOptions(this._cf);
        }
      } catch (_) { options = []; }
      this._filterOptionsCache.set(listType, options || []);
    }

    if (!this._filterBarEl) {
      this._filterBarEl = document.createElement('div');
      this._filterBarEl.className = 'lv-assoc-filter-bar';
      this._bodyEl.parentNode.insertBefore(this._filterBarEl, this._bodyEl);
    }

    const currentVal = this._filterSelections[listType] || '';
    this._filterBarEl.innerHTML = '';

    const select = document.createElement('select');
    select.className = 'lv-assoc-filter-select';
    const allOpt = document.createElement('option');
    allOpt.value = '';
    allOpt.textContent = filterCfg.allLabel || '全部';
    select.appendChild(allOpt);
    for (const opt of (options || [])) {
      const o = document.createElement('option');
      o.value = opt.gid;
      o.textContent = opt.name;
      if (opt.gid === currentVal) o.selected = true;
      select.appendChild(o);
    }
    select.addEventListener('change', async () => {
      this._filterSelections[listType] = select.value;
      this._saveFilterSelections();
      // 如果版本选择清空且该适配器需要版本才能显示已关联/未关联，重置 linked filter
      if (!select.value && adapter.linkedFilterRequiresSelection) {
        this._linkedFilter[listType] = 'all';
      }
      for (const k of this._cache.keys()) { if (k.startsWith(listType + ':')) this._cache.delete(k); }
      // 重新渲染筛选条（已关联/未关联 tabs 的显隐由 filterGid 决定）
      await this._renderFilterBar(listType);
      await this._loadAndRender();
    });
    this._filterBarEl.appendChild(select);
  }

  _removeFilterBar() {
    if (this._filterBarEl) { this._filterBarEl.remove(); this._filterBarEl = null; }
  }

  _removeLinkedFilterBar() {
    if (this._linkedFilterBarEl) { this._linkedFilterBarEl.remove(); this._linkedFilterBarEl = null; }
  }

  _removeActionBar() {
    this._closeActionsPopup();
    if (this._actionBarEl) { this._actionBarEl.remove(); this._actionBarEl = null; }
  }

  _removeHeaderBar() {
    if (this._headerBarEl) { this._headerBarEl.remove(); this._headerBarEl = null; }
  }

  _removeLineBar() {
    if (this._lineBarEl) { this._lineBarEl.remove(); this._lineBarEl = null; }
  }

  /** 创建单张缩略图 DOM（供 _showPicThumbnails 和 _addCaptureThumbnail 复用） */
  _makeThumbEl(url, title) {
    const fullUrl = window.AI00RuntimeConfig?.toAbsoluteBackendUrl?.(url) || url;
    const thumb = document.createElement('div');
    thumb.className = 'lv-pic-thumb';
    thumb.title = title || '';
    const img = document.createElement('img');
    img.src = fullUrl;
    img.loading = 'lazy';
    thumb.appendChild(img);
    thumb.addEventListener('click', () => window.open(img.src, '_blank'));
    return thumb;
  }

  /** 初始化空的缩略图条（工序截图开始前调用，清除旧内容） */
  _initCaptureThumbnailStrip() {
    this._bodyEl?.querySelector('.lv-pic-strip')?.remove();
    const strip = document.createElement('div');
    strip.className = 'lv-pic-strip';
    this._bodyEl?.appendChild(strip);
    this._captureStrip = strip;
  }

  /** 追加一张缩略图并触发飞入动画（工序截图进度回调，每上传一张调一次） */
  _addCaptureThumbnail(op, url) {
    let strip = this._captureStrip || this._bodyEl?.querySelector('.lv-pic-strip');
    if (!strip) { this._initCaptureThumbnailStrip(); strip = this._captureStrip; }
    strip.appendChild(this._makeThumbEl(url, op.title || op.bop_entry_gid));
  }

  /** 展示工序截图缩略图条（飞入动画） */
  _showPicThumbnails(ops) {
    this._bodyEl?.querySelector('.lv-pic-strip')?.remove();
    const strip = document.createElement('div');
    strip.className = 'lv-pic-strip';
    this._bodyEl?.appendChild(strip);
    this._captureStrip = strip;

    ops.forEach((op, i) => {
      const pics = op.process_flow_pic || [];
      if (!pics.length) return;
      const raw = pics[0];
      if (!raw) return;
      const picUrl = typeof raw === 'string' ? raw : raw?.url;
      if (!picUrl) return;
      setTimeout(() => strip.appendChild(this._makeThumbEl(picUrl, op.title || op.bop_entry_gid)),
                 i * 300);
    });
  }

  /** 演示关联过程：列视图工序卡片逐个出现，面板点逐个变绿 */
  async _runDemoAnimation(previewItems) {
    if (this._demoRunning) return;
    this._demoRunning = true;
    this._demoPaused  = false;

    const sleep = ms => new Promise(r => setTimeout(r, ms));
    const waitWhilePaused = async () => {
      while (this._demoPaused && this._demoRunning) await sleep(80);
    };

    // 1. 重置面板所有绑定点为灰
    this._bodyEl?.querySelectorAll('.lv-bind-dot.bound').forEach(dot => {
      dot.classList.remove('bound'); dot.classList.add('unbound');
    });

    // 2. 取 BOP 树中已创建的 process/operation/part 节点（按工位顺序）
    const bopRows = this._getBopLinkedNodes?.() || [];
    if (bopRows.length > 0) {
      this._demoHideNodes?.(bopRows.map(r => r.gid));
      // 设置初始视图：缩放 61%，定位到第一个工位
      const firstProcess = bopRows.find(r => r.node_type === 'process');
      if (firstProcess?.parent_gid) {
        this._demoSetupView?.(firstProcess.parent_gid);
      }
      // 等待两帧，确保浏览器已渲染隐藏状态再开始逐个出现
      await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
    }

    // 3. 建立 vpps+type → GBOP preview GID 列表映射（用于点亮面板点）
    const vppsMap = new Map();
    for (const it of previewItems) {
      const key = `${it.type}:${it.vpps || ''}`;
      if (!vppsMap.has(key)) vppsMap.set(key, []);
      vppsMap.get(key).push(it.gid);
    }

    // 4. 显示演示控制栏
    this._showDemoControl();

    // 5. 逐步展示
    let _currentStationGid = null;
    for (const row of bopRows) {
      if (!this._demoRunning) break;
      await waitWhilePaused();
      if (!this._demoRunning) break;

      // 进入新工位时平滑平移画布（fire-and-forget）
      if (row.node_type === 'process' && row.parent_gid && row.parent_gid !== _currentStationGid) {
        _currentStationGid = row.parent_gid;
        this._demoPanToStation?.(_currentStationGid);
      }

      // 列视图/布局视图：显示卡片（返回 true 表示该视图有对应 DOM）
      const revealed = this._demoRevealNode?.(row.gid);

      // 面板：点亮匹配的 dot（by vpps+type）
      const key = `${row.node_type}:${row.vpps || ''}`;
      for (const pgid of (vppsMap.get(key) || [])) {
        this._flashAndBindDot(pgid);
      }

      // 有可见卡片时停留久一点；否则快速过（如布局视图中看不见的 operation/part）
      const delay = revealed
        ? (row.node_type === 'process' ? 160 : row.node_type === 'operation' ? 80 : 50)
        : (row.node_type === 'process' ? 40 : 15);
      await sleep(delay);
    }

    const stoppedEarly = !this._demoRunning;
    this._demoRunning = false;
    this._removeDemoControl();

    if (stoppedEarly) {
      // 用户手动停止：恢复卡片可见，刷新面板
      this._demoCleanup?.();
      this._cache.clear();
      this._loadAndRender();
    }
  }

  /** 点亮指定 gid 的面板绑定点（闪烁后变绿） */
  _flashAndBindDot(gid) {
    const rowEl = this._bodyEl?.querySelector(`[data-ref-gid="${gid}"]`);
    if (!rowEl) return;
    rowEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    const dot = rowEl.querySelector('.lv-bind-dot');
    if (!dot) return;
    dot.classList.remove('lv-demo-flash');
    void dot.offsetWidth; // restart animation
    dot.classList.add('lv-demo-flash');
    setTimeout(() => {
      dot.classList.remove('lv-demo-flash', 'unbound');
      dot.classList.add('bound');
    }, 350);
  }

  /** 显示演示控制栏（暂停/停止） */
  _showDemoControl() {
    this._removeDemoControl();
    const bar = document.createElement('div');
    bar.className = 'lv-demo-control-bar';

    const label = document.createElement('span');
    label.className = 'lv-demo-ctrl-label';
    label.textContent = '演示中…';

    const pauseBtn = document.createElement('button');
    pauseBtn.className = 'lv-demo-ctrl-btn';
    pauseBtn.title = '暂停';
    pauseBtn.innerHTML = '<svg viewBox="0 0 16 16" fill="currentColor" width="12" height="12"><rect x="3" y="2" width="4" height="12" rx="1"/><rect x="9" y="2" width="4" height="12" rx="1"/></svg>';
    pauseBtn.addEventListener('click', () => {
      this._demoPaused = !this._demoPaused;
      pauseBtn.title = this._demoPaused ? '继续' : '暂停';
      pauseBtn.innerHTML = this._demoPaused
        ? '<svg viewBox="0 0 16 16" fill="currentColor" width="12" height="12"><polygon points="3,2 13,8 3,14"/></svg>'
        : '<svg viewBox="0 0 16 16" fill="currentColor" width="12" height="12"><rect x="3" y="2" width="4" height="12" rx="1"/><rect x="9" y="2" width="4" height="12" rx="1"/></svg>';
    });

    const stopBtn = document.createElement('button');
    stopBtn.className = 'lv-demo-ctrl-btn lv-demo-ctrl-stop';
    stopBtn.title = '停止演示';
    stopBtn.innerHTML = '<svg viewBox="0 0 16 16" fill="currentColor" width="12" height="12"><rect x="2" y="2" width="12" height="12" rx="1"/></svg>';
    stopBtn.addEventListener('click', () => {
      this._demoRunning = false;
      this._demoPaused  = false;
    });

    bar.appendChild(label);
    bar.appendChild(pauseBtn);
    bar.appendChild(stopBtn);
    this._bodyEl.parentNode.insertBefore(bar, this._bodyEl);
    this._demoControlEl = bar;
  }

  _removeDemoControl() {
    if (this._demoControlEl) { this._demoControlEl.remove(); this._demoControlEl = null; }
  }

  stopDemo() {
    this._demoRunning = false;
    this._demoPaused  = false;
  }

  /* ── 操作命令弹出窗口 ──────────────────────────────── */

  _toggleActionsPopup(actionsArr, anchorBtn) {
    if (this._actionsPopupEl) { this._closeActionsPopup(); return; }

    const popup = document.createElement('div');
    popup.className = 'lv-actions-popup';
    popup.setAttribute('role', 'dialog');
    popup.setAttribute('aria-label', '操作命令');

    const header = document.createElement('div');
    header.className = 'lv-actions-popup-header';
    header.innerHTML = '<span>操作命令</span>';
    const closeBtn = document.createElement('button');
    closeBtn.className = 'lv-actions-popup-close';
    closeBtn.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>';
    closeBtn.addEventListener('click', () => this._closeActionsPopup());
    header.appendChild(closeBtn);
    popup.appendChild(header);

    const list = document.createElement('div');
    list.className = 'lv-actions-popup-list';

    for (const act of actionsArr) {
      const row = document.createElement('button');
      row.className = 'lv-actions-popup-item' + (act.danger ? ' lv-actions-popup-item-danger' : '');
      row.textContent = act.label;
      row.addEventListener('click', async () => {
        if (row.disabled) return;
        row.disabled = true;
        row.textContent = '执行中…';
        try {
          await act.execute(this._cf, this._versionGid, this._toast, this);
          if (!act.skipPostRefresh) {
            this._cache.clear();
            await this._loadAndRender();
            this._onActionComplete?.();
          }
        } catch (e) {
          this._toast('执行失败: ' + e.message, 'error');
        } finally {
          row.disabled = false;
          row.textContent = act.label;
        }
      });
      list.appendChild(row);
    }
    popup.appendChild(list);

    // 定位：相对 anchorBtn 的文档坐标
    document.body.appendChild(popup);
    const rect = anchorBtn.getBoundingClientRect();
    popup.style.left = Math.max(4, rect.left) + 'px';
    popup.style.top  = (rect.bottom + 4) + 'px';
    // 若超出右边界则向左对齐
    const pw = popup.offsetWidth || 200;
    if (rect.left + pw > window.innerWidth - 8) {
      popup.style.left = Math.max(4, window.innerWidth - pw - 8) + 'px';
    }

    this._actionsPopupEl = popup;
    anchorBtn.classList.add('lv-assoc-action-trigger--open');

    // 点击外部关闭
    this._actionsPopupOutside = (e) => {
      if (!popup.contains(e.target) && e.target !== anchorBtn) this._closeActionsPopup();
    };
    this._actionsPopupKeydown = (e) => {
      if (e.key === 'Escape') this._closeActionsPopup();
    };
    setTimeout(() => {
      document.addEventListener('click', this._actionsPopupOutside, true);
      document.addEventListener('keydown', this._actionsPopupKeydown, true);
    }, 0);
  }

  _closeActionsPopup() {
    if (!this._actionsPopupEl) return;
    this._actionsPopupEl.remove();
    this._actionsPopupEl = null;
    document.removeEventListener('click',   this._actionsPopupOutside, true);
    document.removeEventListener('keydown', this._actionsPopupKeydown, true);
    this._actionsPopupOutside = null;
    this._actionsPopupKeydown = null;
    this._actionBarEl?.querySelector('.lv-assoc-action-trigger--open')?.classList.remove('lv-assoc-action-trigger--open');
  }

  /** 渲染/更新线体筛选条（bop_working 专用，支持折叠） */
  _updateLineBar() {
    const lines = this._availableLines;
    if (!lines || lines.length === 0) { this._removeLineBar(); return; }

    if (!this._lineBarEl) {
      this._lineBarEl = document.createElement('div');
      this._lineBarEl.className = 'lv-assoc-line-bar';
      this._bodyEl.parentNode.insertBefore(this._lineBarEl, this._bodyEl);
    }
    this._lineBarEl.innerHTML = '';

    // 标题行（始终可见）
    const headerRow = document.createElement('div');
    headerRow.className = 'lv-assoc-line-header-row';

    const toggleBtn = document.createElement('button');
    toggleBtn.className = 'lv-assoc-line-toggle';
    toggleBtn.innerHTML = this._lineBarCollapsed
      ? '<svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" width="10" height="10"><polyline points="3,4 6,7 9,4"/></svg>'
      : '<svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" width="10" height="10"><polyline points="3,7 6,4 9,7"/></svg>';
    toggleBtn.title = this._lineBarCollapsed ? '展开线体选择' : '折叠线体选择';
    toggleBtn.addEventListener('click', () => {
      this._lineBarCollapsed = !this._lineBarCollapsed;
      this._updateLineBar();
    });
    headerRow.appendChild(toggleBtn);

    const labelEl = document.createElement('span');
    labelEl.className = 'lv-assoc-line-label';
    labelEl.textContent = '线体';
    headerRow.appendChild(labelEl);

    if (this._lineBarCollapsed) {
      const count = this._selectedLineGids.size;
      const summary = document.createElement('span');
      summary.className = 'lv-assoc-line-summary';
      summary.textContent = count > 0 ? `已选 ${count} 条` : '全部';
      headerRow.appendChild(summary);
    }

    this._lineBarEl.appendChild(headerRow);

    if (this._lineBarCollapsed) return;

    // 展开时：chips 行
    const chipsRow = document.createElement('div');
    chipsRow.className = 'lv-assoc-line-chips-row';

    const allChip = document.createElement('button');
    allChip.className = 'lv-assoc-line-chip' + (this._selectedLineGids.size === 0 ? ' active' : '');
    allChip.textContent = '全部';
    allChip.addEventListener('click', () => {
      this._selectedLineGids.clear();
      this._lineBarCollapsed = true;
      this._updateLineBar();
      this._reRenderBody();
    });
    chipsRow.appendChild(allChip);

    for (const line of lines) {
      const chip = document.createElement('button');
      const isActive = this._selectedLineGids.has(line.gid);
      chip.className = 'lv-assoc-line-chip' + (isActive ? ' active' : '');
      chip.title = line.vpps ? `${line.title}（${line.vpps}）` : line.title;
      const label2 = document.createElement('span');
      label2.textContent = line.title || line.gid;
      chip.appendChild(label2);
      if (line.process_count > 0) {
        const badge = document.createElement('span');
        badge.className = 'lv-assoc-line-badge';
        badge.textContent = line.process_count;
        chip.appendChild(badge);
      }
      chip.addEventListener('click', () => {
        if (this._selectedLineGids.has(line.gid)) {
          this._selectedLineGids.delete(line.gid);
        } else {
          this._selectedLineGids.add(line.gid);
        }
        this._lineBarCollapsed = true;
        this._updateLineBar();
        this._reRenderBody();
      });
      chipsRow.appendChild(chip);
    }

    this._lineBarEl.appendChild(chipsRow);
  }

  /* ── 配置条（分组 + 状态筛选） ─────────────────────── */

  _renderConfigBar(listType) {
    const adapter = ASSOC_ADAPTERS[listType];
    if (!adapter.groupFields && !adapter.filterFields) {
      this._removeConfigBar();
      return;
    }

    if (!this._configBarEl) {
      this._configBarEl = document.createElement('div');
      this._configBarEl.className = 'lv-assoc-config-bar';
      // 插入到 filterBar 之后、bodyEl 之前
      this._bodyEl.parentNode.insertBefore(this._configBarEl, this._bodyEl);
    }

    const cfg = this._getViewCfg(listType);
    this._configBarEl.innerHTML = '';

    // 分组下拉
    if (adapter.groupFields) {
      const grpSel = document.createElement('select');
      grpSel.className = 'lv-assoc-cfg-select';
      for (const gf of adapter.groupFields) {
        const o = document.createElement('option');
        o.value = gf.key;
        o.textContent = gf.label;
        if (gf.key === cfg.groupBy) o.selected = true;
        grpSel.appendChild(o);
      }
      grpSel.addEventListener('change', () => {
        cfg.groupBy = grpSel.value;
        this._saveViewConfigs();
        this._reRenderBody();
      });
      this._configBarEl.appendChild(grpSel);
    }

    // 状态筛选 chips
    if (adapter.filterFields) {
      for (const ff of adapter.filterFields) {
        const wrap = document.createElement('div');
        wrap.className = 'lv-assoc-cfg-chips';
        for (const opt of ff.options) {
          const chip = document.createElement('button');
          chip.className = 'lv-assoc-cfg-chip';
          chip.textContent = opt.label;
          const isActive = !cfg.statusFilter || cfg.statusFilter.length === 0 || cfg.statusFilter.includes(opt.value);
          chip.classList.toggle('active', isActive);
          chip.addEventListener('click', () => {
            if (!cfg.statusFilter || cfg.statusFilter.length === 0) {
              // 从"全选"→ 只选点击的这个
              cfg.statusFilter = [opt.value];
            } else if (cfg.statusFilter.includes(opt.value)) {
              cfg.statusFilter = cfg.statusFilter.filter(v => v !== opt.value);
              if (cfg.statusFilter.length === 0) cfg.statusFilter = []; // 空=全不选
            } else {
              cfg.statusFilter.push(opt.value);
            }
            // 全选 → 清空数组（表示不筛选）
            const allValues = ff.options.map(o => o.value);
            if (allValues.every(v => cfg.statusFilter.includes(v))) {
              cfg.statusFilter = [];
            }
            this._saveViewConfigs();
            this._renderConfigBar(listType);
            this._reRenderBody();
          });
          wrap.appendChild(chip);
        }
        this._configBarEl.appendChild(wrap);
      }
    }
  }

  _removeConfigBar() {
    if (this._configBarEl) { this._configBarEl.remove(); this._configBarEl = null; }
  }

  /* ── Tab 激活 + 数据加载 ──────────────────────────── */

  async activateTab(idx) {
    if (idx < 0 || idx >= this._tabs.length) return;
    this._activeIdx = idx;
    this._renderTabs();

    const tab = this._tabs[idx];
    await this._renderFilterBar(tab.listType);
    this._renderConfigBar(tab.listType);
    await this._loadAndRender();
  }

  async _loadAndRender() {
    if (this._activeIdx < 0) return;
    const tab = this._tabs[this._activeIdx];
    const adapter = ASSOC_ADAPTERS[tab.listType];
    if (!adapter) return;

    // PBOM 默认模式（已关联零件）需要 BOP 版本；选了 PBOM 版本后不需要
    const filterGid = this._filterSelections[tab.listType] || '';
    if (!this._versionGid && adapter.getLinkType() === 'pbom_part' && !filterGid) {
      this._bodyEl.innerHTML = '<div class="lv-assoc-empty">请先在上方选择 BOP 版本</div>';
      return;
    }

    this._bodyEl.innerHTML = '<div class="lv-assoc-empty">加载中...</div>';

    try {
      const cacheKey = `${tab.listType}:${filterGid}`;
      const cached = this._cache.get(cacheKey);
      let items, linkMap;

      if (cached && (Date.now() - cached.ts < this._CACHE_TTL)) {
        items = cached.data;
        linkMap = cached.linkMap;
      } else {
        items = await adapter.fetchData(this._cf, this._versionGid, filterGid, this);
        try {
          if (adapter.getLinkSummary) {
            linkMap = await adapter.getLinkSummary(this._cf, this._versionGid, this);
          } else {
            const summaryRes = await _assocInvoke(this._cf, 'craft.bop.entry.legacy_read', {
              operation: 'link_summary',
              version_gid: this._versionGid,
              link_type: adapter.getLinkType(),
            });
            linkMap = summaryRes.data || {};
          }
        } catch (_) { linkMap = {}; }
        this._cache.set(cacheKey, { data: items, linkMap, ts: Date.now() });
      }

      this._lastItems = items;
      this._lastLinkMap = linkMap;
      // 若适配器支持线体筛选，数据加载后更新线体筛选条
      if (adapter.hasLineFilter) this._updateLineBar();
      this._reRenderBody();
      if (adapter.hasLineFilter) this._refreshPicMap();  // fire-and-forget：载入已保存截图
    } catch (e) {
      this._bodyEl.innerHTML = `<div class="lv-assoc-empty">加载失败: ${e.message}</div>`;
    }
  }

  /** 重新渲染 body（不重新请求数据，用于 groupBy/filter 切换） */
  _reRenderBody() {
    if (!this._lastItems || this._activeIdx < 0) return;
    const tab = this._tabs[this._activeIdx];
    const adapter = ASSOC_ADAPTERS[tab.listType];
    const items = this._lastItems;
    const linkMap = this._lastLinkMap || {};
    const cfg = this._getViewCfg(tab.listType);

    // 筛选
    let filtered = items;
    if (cfg.statusFilter && cfg.statusFilter.length > 0 && adapter.getStatus) {
      filtered = items.filter(item => cfg.statusFilter.includes(adapter.getStatus(item)));
    }
    // 线体筛选（bop_working 专用）
    if (adapter.hasLineFilter && this._selectedLineGids.size > 0) {
      const selectedLines = this._selectedLineGids;
      const inclProcGids = new Set(
        filtered.filter(it => it.type === 'process' && it.line_gids?.some(lg => selectedLines.has(lg))).map(it => it.gid)
      );
      const inclOpGids = new Set(
        filtered.filter(it => it.type === 'operation' && inclProcGids.has(it.parent_gid)).map(it => it.gid)
      );
      filtered = filtered.filter(it =>
        (it.type === 'process'   && inclProcGids.has(it.gid)) ||
        (it.type === 'operation' && inclOpGids.has(it.gid))   ||
        (it.type === 'part'      && inclOpGids.has(it.parent_gid))
      );
    }
    // bop_working：按工位顺序排序工序（与演示动画顺序一致，灯从上往下点亮）
    if (adapter.hasLineFilter && this._getBopLinkedNodes) {
      const bopRows = this._getBopLinkedNodes();
      const sortMap = new Map();
      bopRows.forEach((row, i) => {
        if (row.vpps) sortMap.set(`${row.node_type}:${row.vpps}`, i);
      });
      filtered = [...filtered].sort((a, b) => {
        const ka = `${a.type || 'process'}:${a.vpps || ''}`;
        const kb = `${b.type || 'process'}:${b.vpps || ''}`;
        return (sortMap.get(ka) ?? 9999) - (sortMap.get(kb) ?? 9999);
      });
    }

    // 已关联/未关联 过滤
    const linkedFilterVal = this._linkedFilter[tab.listType] || 'all';
    if (adapter.hasLinkedFilter && linkedFilterVal !== 'all') {
      filtered = filtered.filter(item => {
        const linked = !!linkMap[adapter.getRefGid(item)];
        return linkedFilterVal === 'linked' ? linked : !linked;
      });
    }

    // 分组 or 树形 or 平铺
    // 当已关联/未关联筛选激活时强制平铺（树形父级会丢失）
    const forceFlat = adapter.hasLinkedFilter && linkedFilterVal !== 'all';
    if (!forceFlat && adapter.treeParent && filtered.length > 0 && filtered[0][adapter.treeParent] !== undefined) {
      this._renderTree(tab, adapter, filtered, linkMap);
    } else if (!forceFlat && cfg.groupBy && cfg.groupBy !== 'none' && adapter.getStatus) {
      this._renderGrouped(tab, adapter, filtered, linkMap, cfg.groupBy);
    } else {
      this._renderList(tab, adapter, filtered, linkMap);
    }
    // 统计未绑定数并更新 alert 提示
    this._updateUnlinkedAlert(tab, adapter, items, linkMap);
  }

  /** 从 line-operations 端点加载已保存截图，填充 _picMap（bop_working 内联缩略图） */
  async _refreshPicMap() {
    if (!this._versionGid || this._selectedLineGids.size !== 1) return;
    const lineGid = [...this._selectedLineGids][0];
    try {
      const res = await _assocInvoke(this._cf, 'craft.bop.line_operation_catia.read', {
        line_entry_gid: lineGid,
      });
      const ops = res?.data || [];
      this._picMap.clear();
      for (const op of ops) {
        const pics = op.process_flow_pic || [];
        if (!pics.length) continue;
        const raw = pics[0];
        const url = typeof raw === 'string' ? raw : raw?.url;
        if (url) this._picMap.set(op.bop_entry_gid, url);
      }
      if (this._picMap.size > 0) this._reRenderBody();
    } catch (_) {}
  }

  /** 统计未绑定条目并更新关联面板内联提示行 */
  _updateUnlinkedAlert(tab, adapter, items, linkMap) {
    const alertEl = document.getElementById('lvAssocUnlinked');
    if (!alertEl) return;
    if (!items || items.length === 0) {
      alertEl.style.display = 'none';
      return;
    }
    const unlinked = items.filter(item => !linkMap[adapter.getRefGid(item)]).length;
    if (unlinked === 0) {
      alertEl.style.display = 'none';
      return;
    }
    alertEl.style.display = '';
    alertEl.innerHTML =
      `<span class="lv-au-icon">⚠</span>` +
      `<span>${tab.label}：${unlinked} 条未绑定到任何 BOP 节点</span>`;
  }

  /* ── 平铺列表渲染 ──────────────────────────────────── */

  _renderList(tab, adapter, items, linkMap) {
    this._bodyEl.innerHTML = '';
    if (!items || items.length === 0) {
      this._bodyEl.innerHTML = `<div class="lv-assoc-empty">暂无${tab.label}数据</div>`;
      return;
    }
    for (const item of items) {
      this._bodyEl.appendChild(this._buildItemRow(tab, adapter, item, linkMap, 0));
    }
  }

  /* ── 分组渲染 ──────────────────────────────────────── */

  _renderGrouped(tab, adapter, items, linkMap, groupBy) {
    this._bodyEl.innerHTML = '';
    if (!items || items.length === 0) {
      this._bodyEl.innerHTML = `<div class="lv-assoc-empty">暂无${tab.label}数据</div>`;
      return;
    }

    const groups = new Map();
    for (const item of items) {
      let key;
      if (groupBy === 'status') {
        key = adapter.getStatus ? adapter.getStatus(item) : 'unknown';
      } else if (groupBy === 'priority') {
        key = item.priority || 'normal';
      } else {
        key = 'other';
      }
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(item);
    }

    for (const [key, groupItems] of groups) {
      const label = (groupBy === 'status')
        ? (_STATUS_LABELS[key] || key)
        : (groupBy === 'priority' ? (_PRIORITY_LABELS[key] || key) : key);

      const hdr = document.createElement('div');
      hdr.className = 'lv-assoc-group-hdr';
      hdr.innerHTML = `<span class="lv-assoc-grp-label">${label}</span><span class="lv-assoc-grp-count">${groupItems.length}</span>`;
      this._bodyEl.appendChild(hdr);

      for (const item of groupItems) {
        this._bodyEl.appendChild(this._buildItemRow(tab, adapter, item, linkMap, 0));
      }
    }
  }

  /* ── 树形渲染 ──────────────────────────────────────── */

  _renderTree(tab, adapter, items, linkMap) {
    this._bodyEl.innerHTML = '';
    if (!items || items.length === 0) {
      this._bodyEl.innerHTML = `<div class="lv-assoc-empty">暂无${tab.label}数据</div>`;
      return;
    }

    const parentField = adapter.treeParent;
    const byId = new Map();
    const childMap = new Map();
    const childSet = new Set();

    for (const item of items) byId.set(adapter.getRefGid(item), item);
    for (const item of items) {
      const gid = adapter.getRefGid(item);
      const pg = item[parentField] || null;
      if (pg && byId.has(pg)) {
        if (!childMap.has(pg)) childMap.set(pg, []);
        childMap.get(pg).push(item);
        childSet.add(gid);
      }
    }
    const roots = items.filter(item => !childSet.has(adapter.getRefGid(item)));

    const renderNode = (item, depth) => {
      this._bodyEl.appendChild(this._buildItemRow(tab, adapter, item, linkMap, depth));
      const children = childMap.get(adapter.getRefGid(item));
      if (children) for (const child of children) renderNode(child, depth + 1);
    };
    for (const root of roots) renderNode(root, 0);
  }

  /* ── 单行构建 ──────────────────────────────────────── */

  _buildItemRow(tab, adapter, item, linkMap, depth) {
    const refGid = adapter.getRefGid(item);
    const binding = linkMap[refGid];
    const vpps = adapter.getVpps ? adapter.getVpps(item) : '';

    const el = document.createElement('div');
    el.className = 'lv-assoc-item';
    if (binding && binding.bop_entry_gid) el.classList.add('clickable');
    if (depth > 0) el.classList.add('lv-assoc-tree-node');
    el.dataset.refGid = refGid;
    el.draggable = true;

    if (depth > 0) {
      const indent = 6 + depth * 14;
      el.style.paddingLeft = indent + 'px';
      el.style.setProperty('--tree-line-left', (indent - 10) + 'px');
    }

    // 绑定状态圆点：绿色=已关联, 红色=关联目标失效, 灰色=未关联
    const dot = document.createElement('span');
    dot.className = 'lv-bind-dot';
    if (binding) {
      dot.classList.add(binding.is_valid ? 'bound' : 'invalid');
      dot.title = binding.is_valid ? '已关联' : '关联目标已失效';
    } else {
      dot.classList.add('unbound');
      dot.title = '未关联';
    }
    el.appendChild(dot);

    // 标题
    const title = document.createElement('span');
    title.className = 'lv-assoc-title';
    title.textContent = adapter.getTitle(item);
    title.title = adapter.getTitle(item);
    el.appendChild(title);

    // vpps 标签
    if (vpps) {
      const tag = document.createElement('span');
      tag.className = 'lv-assoc-vpps';
      tag.textContent = vpps;
      tag.title = 'VPPS: ' + vpps;
      el.appendChild(tag);
    }

    // 关联节点标签（有绑定时显示关联的 bop_entry 名称）
    if (binding && binding.bop_entry_gid && this._resolveStation) {
      const nodeName = this._resolveStation(binding.bop_entry_gid);
      if (nodeName) {
        const stag = document.createElement('span');
        stag.className = 'lv-assoc-station-tag';
        stag.textContent = nodeName;
        stag.title = '关联节点: ' + nodeName;
        el.appendChild(stag);
      }
    }

    // 快照标识（冻结/发布版本时 link 上携带 snapshot_data）
    if (binding && binding.snapshot_data) {
      const snap = typeof binding.snapshot_data === 'string'
        ? JSON.parse(binding.snapshot_data) : binding.snapshot_data;
      const snapTag = document.createElement('span');
      snapTag.className = 'lv-assoc-snapshot-tag';
      const snapName = snap.name || snap.title || snap.part_name || '';
      snapTag.textContent = '快照' + (snapName ? ': ' + snapName : '');
      snapTag.title = '冻结时快照数据: ' + JSON.stringify(snap, null, 2);
      el.appendChild(snapTag);
    }

    // 工序截图内联缩略图（bop_working 专用，绑定到对应 BOP 条目时查 _picMap）
    if (binding?.bop_entry_gid) {
      const picUrl = this._picMap?.get(binding.bop_entry_gid);
      if (picUrl) {
        const thumb = this._makeThumbEl(picUrl, adapter.getTitle(item));
        thumb.classList.add('lv-pic-thumb-inline');
        el.appendChild(thumb);
      }
    }

    // 点击
    el.addEventListener('click', () => {
      if (binding && binding.bop_entry_gid) this._onEntityClick(binding.bop_entry_gid, el);
    });

    // 拖拽
    el.addEventListener('dragstart', e => {
      e.dataTransfer.effectAllowed = 'copy';
      e.dataTransfer.setData('application/x-assoc-item', JSON.stringify({
        listType: tab.listType, refGid, title: adapter.getTitle(item),
        nodeType: adapter.getNodeType(item), linkType: adapter.getLinkType(),
        isPrimary: adapter.getIsPrimary ? adapter.getIsPrimary() : false,
      }));
      e.dataTransfer.setData('text/plain', refGid);
    });

    // 右键菜单 → "查看详情" + "关联到节点"
    el.addEventListener('contextmenu', e => {
      e.preventDefault();
      this._showAssocCtxMenu(e.clientX, e.clientY, {
        refGid, title: adapter.getTitle(item),
        nodeType: adapter.getNodeType(item),
        linkType: adapter.getLinkType(),
        isPrimary: adapter.getIsPrimary ? adapter.getIsPrimary() : false,
        bopEntryGid: binding?.bop_entry_gid || null,
        linkGid: binding?.link_gid || null,
      });
    });

    return el;
  }

  /* ── 右键菜单："查看详情" + "关联到节点" ──────────────── */

  _showAssocCtxMenu(x, y, info) {
    // 移除旧菜单
    document.querySelectorAll('.lv-assoc-ctx-menu').forEach(m => m.remove());

    const menu = document.createElement('div');
    menu.className = 'lv-ctx-menu lv-assoc-ctx-menu';
    menu.style.cssText = `display:block;position:fixed;left:${x}px;top:${y}px;z-index:9999`;

    // "查看详情"（显示外部实体字段，可编辑/删除关联）
    if (info.refGid && info.linkType && this._showEntityDetailPopover) {
      const detailItem = document.createElement('div');
      detailItem.className = 'lv-ctx-item';
      detailItem.textContent = '查看详情';
      detailItem.addEventListener('click', () => {
        menu.remove();
        this._showEntityDetailPopover(info.linkType, info.refGid, { x, y }, info.linkGid);
      });
      menu.appendChild(detailItem);
    }

    // "关联到节点"
    const item = document.createElement('div');
    item.className = 'lv-ctx-item';
    item.textContent = '关联到节点…';
    item.addEventListener('click', async () => {
      menu.remove();
      if (typeof _openParentPicker !== 'function') {
        this._toast('选择器不可用', 'error'); return;
      }
      const picked = await _openParentPicker({ title: '选择关联目标节点' });
      if (!picked) return;
      try {
        await _assocInvoke(this._cf, 'craft.bop.entry_link.change.apply', {
          operation: 'attach',
          entry_gid: picked.gid,
          link_type: info.linkType,
          entity_gid: info.refGid,
          is_primary: info.isPrimary ?? false,
        });
        this._toast('已创建关联', 'ok');
        await this.refresh();
      } catch (ex) {
        this._toast('关联失败: ' + ex.message, 'error');
      }
    });
    menu.appendChild(item);
    document.body.appendChild(menu);

    const closeHandler = ev => {
      if (!menu.contains(ev.target)) {
        menu.remove();
        document.removeEventListener('click', closeHandler, true);
      }
    };
    setTimeout(() => document.addEventListener('click', closeHandler, true), 0);
  }

  /* ── 公开 API ─────────────────────────────────────── */

  highlightLinkedEntity(bopEntryGid) {
    this._bodyEl.querySelectorAll('.lv-assoc-item.highlighted')
      .forEach(el => el.classList.remove('highlighted'));
    if (!bopEntryGid || this._activeIdx < 0) return;

    const tab = this._tabs[this._activeIdx];
    const filterGid = this._filterSelections[tab.listType] || '';
    const cached = this._cache.get(`${tab.listType}:${filterGid}`);
    if (!cached) return;

    const linkedRefGids = new Set();
    for (const [refGid, info] of Object.entries(cached.linkMap || {})) {
      if (info.bop_entry_gid === bopEntryGid) linkedRefGids.add(refGid);
    }
    for (const refGid of linkedRefGids) {
      const el = this._bodyEl.querySelector(`.lv-assoc-item[data-ref-gid="${refGid}"]`);
      if (el) { el.classList.add('highlighted'); el.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); }
    }
  }

  async refresh() {
    if (this._activeIdx < 0) return;
    const tab = this._tabs[this._activeIdx];
    for (const k of this._cache.keys()) { if (k.startsWith(tab.listType + ':')) this._cache.delete(k); }
    this._filterOptionsCache.delete(tab.listType);
    await this._renderFilterBar(tab.listType);
    this._renderConfigBar(tab.listType);
    await this._loadAndRender();
  }

  setVersionGid(gid) {
    if (this._versionGid === gid) return;
    this._versionGid = gid;
    this._cache.clear();
    this._filterOptionsCache.clear();
    if (this._activeIdx >= 0) this._loadAndRender();
  }

  /** 独占切换：将 tab 列表替换为仅含指定 listType 的单个 tab，并激活 */
  async setExclusiveTab(listType) {
    const adapter = ASSOC_ADAPTERS[listType];
    if (!adapter) return;
    this._tabs = [{ listType, label: adapter.label }];
    this._activeIdx = -1;
    this._saveTabConfig();
    await this.activateTab(0);
  }

  clearCache() {
    this._cache.clear();
    this._filterOptionsCache.clear();
  }
}

window.AssocPanel = AssocPanel;

/*
 * 规则结果展示区（预留）
 * Auto-Link 规则校验结果（entry_result.rule_results）通过 lineage.js 的
 * _renderLinkAlerts() 展示在右侧边栏规则判定面板 #lvRuleBody，
 * 此处为未来扩展预留（如在每行显示规则徽标）。
 */
